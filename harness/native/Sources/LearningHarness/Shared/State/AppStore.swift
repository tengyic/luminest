import Foundation
import AppKit
import Combine

@MainActor final class AppStore: ObservableObject {
    @Published var page: Page = .today
    @Published var user: JSON = .null
    @Published var dashboard: JSON = .null
    @Published var curriculum: JSON = .null
    @Published var graph: JSON = .null
    @Published var lesson: JSON = .null
    @Published var reviews: JSON = .null
    @Published var projects: JSON = .null
    @Published var analytics: JSON = .null
    /// Unit-level grade book. Declared standards are returned with their evidence, so the
    /// UI can show "no grade yet" for a unit rather than an invented percentage.
    @Published var gradebook: JSON = .null
    /// Written rubric observations and their published measurement definitions. Never a
    /// score inferred from foreground activity.
    @Published var perspectives: JSON = .null
    /// The course catalogue and the learner's own study plan. Both are re-derived on the
    /// server from the course graph and this learner's recorded responses.
    @Published var courses: JSON = .null
    @Published var plan: JSON = .null
    @Published var showCourseSetup = false
    @Published var setupBusy = false
    @Published var setupError: String?
    @Published var setupDismissed = false
    @Published var messages: [JSON] = []
    @Published var selectedConcept = ""
    @Published var question: JSON = .null
    @Published var attempt: JSON = .null
    @Published var showQuestion = false
    @Published var questionBusy = false
    @Published var busy = false
    @Published var authBusy = false
    @Published var chatBusy = false
    /// Licence-cleared image candidates the tutor's tools surfaced in the latest turn
    /// (`thumb_url` / `title` / `licence` / `source_page`). Rendered under the transcript.
    @Published var chatMedia: [[String: String]] = []
    /// What the tutor is doing right now, one entry per tool call, in order.
    ///
    /// Each entry arrives on the ``tool_call`` event - before there is any result - so
    /// the chip appears while the work happens rather than after it is finished, which
    /// is the one moment it would be useless. The label is the server's own sentence
    /// ("Drawing on the whiteboard"), never the tool's name: a chip that says
    /// ``whiteboard_apply`` teaches the learner the API instead of the concept.
    @Published var chatActivities: [ChatActivity] = []
    /// Whether the tutor's replies are spoken aloud by the local VoiceStudio backend.
    /// Off by default: it is a product decision, and an unexpected voice in a quiet
    /// library is worse than no voice at all. Persisted, because a learner who chose to
    /// be taught out loud should not have to choose again every session.
    @Published var speakEnabled = UserDefaults.standard.bool(forKey: "luminfest.tutor.speak") {
        didSet { UserDefaults.standard.set(speakEnabled, forKey: "luminfest.tutor.speak") }
    }
    /// Why the voice is not playing, when it is not. Empty means nothing to report.
    @Published var speechStatus = ""

    // ------------------------------------------------------- silent supervision
    //
    // The other half of the teacher: nobody asked anything, and the harness decides whether
    // there is something worth saying. Three timestamps, because the three questions are
    // different and collapsing them is how a check becomes a nag:
    //
    //   lastLearnerAction - when the learner last did something visible. The server's
    //     "drifting" threshold is 90 s and "away" is 300 s, so an interval tick that fires
    //     before 90 s can only ever be told "nothing to say". Asking earlier just spends
    //     requests to be refused.
    //   lastCheckAt - when we last asked. Separate from the above because the check must
    //     keep running *while* the learner is idle, and must not run in a tight loop when
    //     they are not.
    //   lastNoticeAt - the last notice's timestamp, round-tripped so the server enforces its
    //     own cooldown. A client that forgets it would be told the same thing every minute,
    //     which is exactly the failure the cooldown exists to prevent.
    private var lastLearnerAction = Date()
    private var lastCheckAt = Date.distantPast
    private var lastNoticeAt: Double?
    /// The line the supervisor chose to say, for the companion to show. Kept out of
    /// ``notice`` because that channel means "saved" and drives a celebration animation;
    /// a supervision line is neither a reward nor an error.
    @Published var supervisionNotice: String?

    /// Record that the learner did something the harness can see.
    ///
    /// Deliberately not called on every mouse move: scrolling is not evidence of working, and
    /// treating it as such would keep the check permanently silent for a learner who is
    /// scrolling past what they do not understand. Only actions with meaning are counted -
    /// asking, answering, and drawing.
    func noteLearnerAction() { lastLearnerAction = Date() }

    /// Ask the harness whether anything is worth saying, without a prompt.
    ///
    /// Runs on the app's one-second tick and is gated to a 45-second cadence. It stays quiet
    /// while a turn is in flight, while an answer is being submitted, and while the tutor is
    /// speaking - ``idle_only`` delivery means a notice must never cut across a sentence or
    /// an answer in progress. What it sends is only what the client actually knows: it has no
    /// lesson-plan progress metric, and inventing one would feed the supervisor a number that
    /// reads as "behind the plan" and produces exactly the wrong interruption.
    private func silentCheckIfDue() {
        guard authenticated, !selectedConcept.isEmpty, !chatBusy, !questionBusy,
              !speech.playing, NSApp.isActive else { return }
        let idle = Date().timeIntervalSince(lastLearnerAction)
        guard idle >= 90, Date().timeIntervalSince(lastCheckAt) >= 45 else { return }
        lastCheckAt = Date()
        var body: [String: Any] = [
            "concept_id": selectedConcept,
            "idle_seconds": idle,
            "window_seconds": 300,
            "active_seconds": min(300, max(0, activeSeconds)),
        ]
        if let last = lastNoticeAt { body["last_notice_at"] = last }
        let version = epoch, id = selectedConcept
        run { [weak self] in
            guard let self, self.epoch == version, self.selectedConcept == id,
                  self.authenticated else { return }
            guard let reading = try? await self.api.json("/supervision/assess", method: "POST",
                                                         body: body) else { return }
            let notice = reading["notice"]
            // ``say`` is the harness's decision, not a suggestion: when it is false the
            // notice carries a reason and no sentence, and speaking the reason would be
            // saying the thought it chose to keep to itself.
            let line = notice["text"].string
            guard notice["say"].bool, !line.isEmpty else { return }
            self.lastNoticeAt = Date().timeIntervalSince1970
            self.supervisionNotice = line
            // Cleared on a timer rather than by the view: a notice is a moment, not state,
            // and a view that owned the clearing would leave a stale line on screen
            // whenever it happened to be off-screen when the next one arrived.
            Task { @MainActor [weak self] in
                try? await Task.sleep(nanoseconds: 9_000_000_000)
                if self?.supervisionNotice == line { self?.supervisionNotice = nil }
            }
            // The line is shown either way; it is only *spoken* when the learner asked to be
            // taught out loud. A supervision notice must not turn the voice on by itself.
            if self.speakEnabled, !notice["speech"].isNull {
                self.playSpeech(notice["speech"], version: version)
            }
        }
    }
    /// Teacher-clone style preferences are held in memory only and sent per tutor turn.
    /// Raw transcripts and quoted evidence never enter the chat request or UserDefaults.
    @Published var teacherStyleProfile: [String: [String]] = [:]
    @Published var error: String?
    /// The HTTP status behind ``error``, when there was one.
    ///
    /// `error` is a `String`, so by the time a view renders it the code is gone and a 422
    /// — the server *refusing a request it parsed*, on a connection that worked — is
    /// indistinguishable from a dropped socket. That is not a cosmetic difference: it is
    /// the difference between "the app and the server disagree about the request format,
    /// check the versions" and "cannot reach the backend, restart it", and the second
    /// message sends the reader to a fix that cannot work. Kept separate rather than
    /// embedded in the string so the presentation layer classifies instead of parsing.
    @Published var errorStatus: Int?
    @Published var questionError: String?
    @Published var notice: String?
    @Published var connected = false
    @Published var restoring = true
    @Published var endpoint: String
    @Published var questionElapsed: Double = 0
    @Published var questionPaused = false
    @Published var answerOption = ""
    @Published var answerText = ""
    @Published var reasoning = ""
    @Published var confidence = 0.5
    @Published var answerFrozen = false
    private(set) var pendingQuestionMode = "practice"
    private(set) var pendingQuestionConcept: String?
    /// The client every request goes through. ``var`` only because the bundled server can
    /// land on a fallback port when 8765 is taken (see ``BackendLauncher.choosePort``), and
    /// a client bound to a port nothing listens on answers every call with a network error.
    var api: APIClient
    /// `internal`, not `private`: the AppStore extensions in `Shared/State/` guard their
    /// late replies against it. See ADR-0003, "access-level changes".
    var epoch = UUID()
    private var tasks: [UUID: Task<Void, Never>] = [:]
    private var retryAction: (() async -> Void)?
    private var timer: AnyCancellable?
    private var lastTick = ProcessInfo.processInfo.systemUptime
    /// `internal`, not `private`: `updateSettings` in `AppStore+Account.swift` resets it.
    /// See ADR-0003, "access-level changes".
    var activeSeconds: Double = 0
    private var heartbeatStart = ProcessInfo.processInfo.systemUptime
    private var eventID = UUID().uuidString
    private var questionGeneration = UUID()
    /// App-wide interaction telemetry (click / key / window focus). Owned here so it is
    /// started and stopped with the store's auth + consent state, and torn down on exit.
    private var clickTelemetry: ClickTelemetry?
    private var telemetryArmed = false
    private var frozenAnswer: [String: Any]?
    /// Plays the tutor's spoken reply. Owned here so a turn that is interrupted by a
    /// course switch stops talking.
    let speech = ClipPlayer()
    /// Milestones the backend says this learner has earned. Owned by the store because the
    /// shell presents them once, over everything, rather than inside one page.
    let rewards = RewardCenter()
    var authenticated: Bool { !user["id"].string.isEmpty }
    var concepts: [JSON] { curriculum["concepts"].array }
    var currentConcept: JSON { concepts.first { $0["id"].string == selectedConcept } ?? .null }

    /// The narrated deck for the selected concept, wrapped as a tool result
    /// (`ok` / `data` / `notes`).
    @Published var deck: JSON = .null
    @Published var deckBusy = false
    @Published var showDeck = false
    /// Presents the slide editor (``DeckEditorView``) for the assembled deck.
    @Published var showDeckEditor = false
    /// External simulations matched to the selected concept (PhET embeds, Gizmos deep links).
    @Published var conceptSimulations: JSON = .null
    @Published var conceptSimulationsBusy = false
    /// The playground gallery: the bundled first-party games, from `GET /api/v1/playground`.
    /// Unlike `conceptSimulations` this is not scoped to one concept - the games span the
    /// whole catalogue - so it is loaded once and reused.
    @Published var playground: JSON = .null
    @Published var playgroundBusy = false
    /// Whether the gallery sheet is up, and which game (if any) it should open on arrival.
    @Published var showPlayground = false
    @Published var playgroundSlug: String?
    /// Whether the backend reports media providers as reachable (HARNESS_MEDIA_ENABLED).
    @Published var mediaOnline = false

    /// The live harness decision for the recommended concept, or the reason there is none.
    @Published var harnessPlanState = HarnessPlanState()
    @Published var harnessOutcomeBusy = false

    @Published var lessonProcedure = LessonProcedureState()
    @Published var lessonProcedureBusy = false

    /// The live store, for the in-process QA driver.
    ///
    /// This exists because `NSApp.delegate as? AppDelegate` does not round-trip: the adaptor hands
    /// AppKit an instance whose dynamic type is named `AppDelegate` but which the existential cast
    /// rejects, so a QA readback through the delegate always failed and every failure looked like
    /// "the app has no state" rather than "the read is broken". A weak reference is enough — the
    /// app has exactly one window and one store, and `weak` means an abandoned store is never kept
    /// alive by this.
    static weak var current: AppStore?

    init() {
        let origin = UserDefaults.standard.string(forKey: "luminfest.endpoint") ?? "http://127.0.0.1:8765"
        endpoint = origin
        api = APIClient(endpoint: origin)
        timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect().sink { [weak self] _ in self?.tick() }
        AppStore.current = self
        if ProcessInfo.processInfo.arguments.contains("--ui-test") { restoring = false }
        else { run { [weak self] in
            await BackendLauncher.shared.startIfBundled()
            if let failure = BackendLauncher.shared.failure { self?.error = failure }
            // The server took a fallback port because 8765 was occupied. Follow it, or
            // every request below would be sent to a port this app is not on.
            if let self, BackendLauncher.shared.origin != self.endpoint {
                self.endpoint = BackendLauncher.shared.origin
                self.api = APIClient(endpoint: BackendLauncher.shared.origin)
            }
            await self?.restore()
        } }
    }
    func run(_ action: @escaping () async -> Void) {
        let id = UUID()
        tasks[id] = Task { [weak self] in await action(); self?.tasks[id] = nil }
    }
    func restore() async {
        let version = epoch
        defer { if epoch == version { restoring = false } }
        guard let token = SecureSession.read(endpoint: endpoint) else { return }
        api.token = token
        do {
            let me = try await api.json("/me")
            guard epoch == version else { return }
            user = me["user"].isNull ? me : me["user"]
            connected = true
            await refresh()
        } catch {
            guard epoch == version else { return }
            api.token = nil
            if (error as? AppFailure)?.status == 401 { SecureSession.remove(endpoint: endpoint) }
            self.error = "Your session could not be restored. Sign in again or check the server. " + error.localizedDescription
        }
    }
    func authenticate(register: Bool, name: String, email: String, password: String, server: String,
                      ageConfirmed: Bool = false, acceptedTerms: Bool = false) async {
        guard !authBusy else { return }
        authBusy = true; error = nil
        let version = epoch
        defer { if epoch == version { authBusy = false } }
        do {
            let origin = try APIClient.validateEndpoint(server)
            api.endpoint = origin; api.token = nil
            var body: [String: Any] = ["email": email.trimmingCharacters(in: .whitespacesAndNewlines), "password": password]
            if register { body["name"] = name.trimmingCharacters(in: .whitespacesAndNewlines) }
            // The launch gate. The desktop server refuses an account that has not attested
            // 13+ and accepted the Terms (`main.py`, `require_launch_gate`), and until now
            // the client never sent either field - so the gate could only ever be off. The
            // server records the timestamps and writes the consent ledger from these two
            // booleans; sending `true` without asking would be a false attestation, which
            // is why the UI requires both boxes rather than defaulting them on.
            if register {
                body["age_confirmed"] = ageConfirmed
                body["accept_terms"] = acceptedTerms
            }
            let result = try await api.json(register ? "/auth/register" : "/auth/login", method: "POST", body: body)
            guard epoch == version else { return }
            let token = result["token"].string
            guard !token.isEmpty, !result["user"]["id"].string.isEmpty else { throw AppFailure(message: "The server did not return a valid account session.", status: nil) }
            // Persisting the session is a convenience, not a condition of signing in. A managed or
            // headless macOS session may expose no default keychain; in that case keep the real
            // authenticated session in memory for this run and say so plainly.
            do {
                try SecureSession.write(token, endpoint: origin)
                notice = nil
            } catch {
                notice = "Signed in for this session only. macOS Keychain could not store the session, so you will need to sign in again next time you open Luminfest."
            }
            endpoint = origin; UserDefaults.standard.set(origin, forKey: "luminfest.endpoint")
            api.token = token; user = result["user"]; connected = true
            // New accounts opt in only through the explicit settings control.
            if register && user["telemetry_consent"].bool {
                let updated = try await api.json("/me", method: "PATCH", body: ["telemetry_consent": false])
                guard epoch == version else { return }
                user = updated["user"].isNull ? updated : updated["user"]
            }
            guard epoch == version else { return }
            await refresh()
        } catch { if epoch == version { record(error) } }
    }
    func record(_ failure: Error) {
        if failure is CancellationError || (failure as? URLError)?.code == .cancelled { return }
        if let e = failure as? AppFailure {
            connected = true
            errorStatus = e.status
            if e.status == 401 && authenticated { logout(); error = "Your session expired. Please sign in again."; return }
        } else if failure is URLError { connected = false; errorStatus = nil }
        else { errorStatus = nil }
        error = failure.localizedDescription
    }
    func load(_ path: String, apply: @escaping (JSON) -> Void) async {
        let version = epoch
        do { let value = try await api.json(path); guard epoch == version, authenticated, !Task.isCancelled else { return }; connected = true; apply(value) }
        catch { if epoch == version { record(error) } }
    }
    func refresh() async {
        guard authenticated else { return }
        let version = epoch
        busy = true; error = nil; errorStatus = nil
        retryAction = { [weak self] in await self?.refresh() }
        await load("/dashboard") { self.dashboard = $0; if !$0["user"].isNull { self.user = $0["user"] } }
        await load("/curriculum") { self.curriculum = $0; if self.selectedConcept.isEmpty { self.selectedConcept = $0["concepts"].array.first?["id"].string ?? "" } }
        await load("/courses") { self.courses = $0 }
        await load("/plan") { self.plan = $0 }
        if epoch == version { busy = false }
        // First-run setup is not latched here: `inCourseSetup` derives it from the account and the
        // loaded catalogue, so the flow survives a dropped presentation and never re-opens once
        // the server has recorded the chosen course.
    }
    func navigate(_ value: Page) {
        page = value; error = nil
        run { [weak self] in await self?.loadPage() }
    }
    func loadPage() async {
        guard authenticated else { return }
        let version = epoch
        busy = true
        retryAction = { [weak self] in await self?.loadPage() }
        switch page {
        case .today: await refresh()
        case .map: await loadMap()
        case .studio: await selectConcept(selectedConcept)
        case .teacher: await loadChat()
        case .review: await load("/reviews") { self.reviews = $0 }
        case .projects: await load("/projects") { self.projects = $0 }
        case .insights:
            await load("/analytics") { self.analytics = $0 }
            await load("/gradebook") { self.gradebook = $0 }
            await load("/perspectives") { self.perspectives = $0 }
            // A self-observation must be attached to a real project artifact, so the
            // insights page needs the same project list the Projects page uses.
            await load("/projects") { self.projects = $0 }
        case .settings: await load("/me") { self.user = $0["user"].isNull ? $0 : $0["user"] }
        }
        if epoch == version { busy = false }
    }
    func retry() { error = nil; if let retryAction { run { await retryAction() } } }
    func selectConcept(_ id: String) async {
        guard !id.isEmpty else { return }
        selectedConcept = id; lesson = .null; messages = []
        // A new concept is a new classroom: the previous board's trace, the previous
        // reply's voice and the previous turn's media all belong to it.
        chatActivities = []
        chatMedia = []
        speechStatus = ""
        // And a new classroom starts its own clock. Carrying the previous concept's idle
        // time or notice cooldown across would open the next lesson with a notice about the
        // last one - or silence the first minute of it.
        lastLearnerAction = Date()
        lastCheckAt = .distantPast
        lastNoticeAt = nil
        supervisionNotice = nil
        speech.stop()
        let version = epoch
        do {
            let value = try await api.json("/lessons/" + id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed)!)
            guard epoch == version, selectedConcept == id, authenticated else { return }
            lesson = value; connected = true
            await loadChat()
        } catch { if epoch == version && selectedConcept == id { record(error) } }
    }
    func startQuestion(mode: String, concept: String? = nil) async {
        guard authenticated, !questionBusy else { return }
        questionGeneration = UUID()
        let generation = questionGeneration
        pendingQuestionMode = mode; pendingQuestionConcept = concept
        questionBusy = true; questionError = nil; showQuestion = true
        question = .null; attempt = .null; answerOption = ""; answerText = ""; reasoning = ""; confidence = 0.5
        frozenAnswer = nil; answerFrozen = false; questionElapsed = 0; questionPaused = false; eventID = UUID().uuidString
        let version = epoch
        defer { if epoch == version && questionGeneration == generation { questionBusy = false } }
        var query = [URLQueryItem(name: "mode", value: mode)]
        if let concept, !concept.isEmpty { query.append(URLQueryItem(name: "concept_id", value: concept)) }
        do {
            let value = try await api.json("/questions/next", query: query)
            guard epoch == version, questionGeneration == generation, authenticated, showQuestion else { return }
            question = value; connected = true; lastTick = ProcessInfo.processInfo.systemUptime
        } catch { if epoch == version && questionGeneration == generation { questionError = error.localizedDescription; record(error) } }
    }
    func submitAnswer() async {
        guard !questionBusy, attempt.isNull, !question["id"].string.isEmpty else { return }
        noteLearnerAction()
        if frozenAnswer == nil {
            frozenAnswer = ["question_id": question["id"].string, "option_id": answerOption.isEmpty ? NSNull() : answerOption as Any,
                "answer_text": answerText.isEmpty ? NSNull() : answerText as Any, "reasoning": reasoning.isEmpty ? NSNull() : reasoning as Any,
                "receipt": question["receipt"].string, "client_event_id": eventID, "elapsed_seconds": questionElapsed, "confidence": confidence]
        }
        answerFrozen = true; questionBusy = true; questionError = nil
        let version = epoch, generation = questionGeneration
        defer { if epoch == version && questionGeneration == generation { questionBusy = false } }
        do {
            let value = try await api.json("/attempts", method: "POST", body: frozenAnswer)
            guard epoch == version, questionGeneration == generation, authenticated else { return }
            attempt = value; connected = true
            if question["mode"].string != "exam" || value["exam_complete"].bool { await refresh() }
            if page == .review { await load("/reviews") { self.reviews = $0 } }
        } catch {
            if epoch == version && questionGeneration == generation {
                if let rejection = error as? AppFailure, let status = rejection.status, [400, 422].contains(status) {
                    frozenAnswer = nil; answerFrozen = false
                }
                questionError = error.localizedDescription; record(error)
            }
        }
    }
    func finishQuestion() { questionGeneration = UUID(); showQuestion = false; questionBusy = false; questionPaused = false; question = .null; frozenAnswer = nil }
    func requestFinishQuestion() {
        let shouldEndExam = question["mode"].string == "exam" && !attempt["exam_complete"].bool
        guard shouldEndExam else { finishQuestion(); return }
        run { [weak self] in
            guard let self else { return }
            do {
                _ = try await self.api.json("/assessments/exam/end", method: "POST", body: ["abandoned": true])
                self.finishQuestion(); await self.refresh()
            } catch { self.questionError = error.localizedDescription; self.record(error) }
        }
    }
    func logout() {
        epoch = UUID(); tasks.values.forEach { $0.cancel() }; tasks = [:]; api.cancelAll()
        SecureSession.remove(endpoint: endpoint); api.token = nil
        user = .null; dashboard = .null; curriculum = .null; graph = .null; lesson = .null; reviews = .null; projects = .null; analytics = .null; gradebook = .null; perspectives = .null; messages = []; teacherStyleProfile = [:]
        courses = .null; plan = .null; showCourseSetup = false; setupBusy = false; setupError = nil; setupDismissed = false
        selectedConcept = ""; page = .today; showQuestion = false; question = .null; attempt = .null
        playground = .null; playgroundSlug = nil; showPlayground = false
        busy = false; authBusy = false; chatBusy = false; questionBusy = false; restoring = false
        answerOption = ""; answerText = ""; reasoning = ""; frozenAnswer = nil; activeSeconds = 0; error = nil; notice = nil; retryAction = nil
    }
    func shutdown() { tasks.values.forEach { $0.cancel() }; api.cancelAll(); timer?.cancel(); clickTelemetry?.stop() }
    /// The one-second foreground clock. Two quantities are counted separately: time on the
    /// current question, and consented active time that is reported in 15-second heartbeats.
    ///
    /// The heartbeat deliberately does *not* re-test foreground state when it dispatches the
    /// request. `activeSeconds` only accumulates while the app is frontmost and consent is on, so
    /// a second check could only contradict the interval it is describing — and when it did, the
    /// interval had already been consumed, so real foreground time vanished with no notice and the
    /// next heartbeat arrived past the server's 30-second tolerance, which discarded that interval
    /// too. A learner could sit in front of the app for a minute and be recorded as having done
    /// nothing, in a feature whose whole promise is honest, consented activity accounting.
    private func tick() {
        let now = ProcessInfo.processInfo.systemUptime
        refreshTelemetryMonitor()
        // Before the heartbeat guard below, which returns on most ticks: the silent check
        // does its own cadencing and must not inherit the 15-second heartbeat interval.
        silentCheckIfDue()
        let elapsed = max(0, min(2, now - lastTick)); lastTick = now
        let foreground = NSApp.isActive
        if foreground && showQuestion && !questionPaused && attempt.isNull && !question.isNull && !answerFrozen && !questionBusy { questionElapsed += elapsed }
        if authenticated && foreground && user["telemetry_consent"].bool && !questionPaused { activeSeconds += elapsed }
        guard now - heartbeatStart >= 15 else { return }
        // Advance the grid first so the cadence stays anchored even when an interval is empty.
        heartbeatStart = now
        // Nothing accumulated means nothing to report: the app was in the background or consent is
        // off, and in both cases the accumulator is already zero. The interval is consumed only
        // when a send is actually dispatched, so a skipped boundary cannot destroy real time.
        let seconds = min(15, activeSeconds)
        guard authenticated, user["telemetry_consent"].bool, seconds > 0 else { return }
        activeSeconds -= seconds
        let version = epoch
        let body: [String: Any] = ["events": [["id": UUID().uuidString, "type": "heartbeat", "occurred_at": ISO8601DateFormatter().string(from: Date()), "payload": ["window_active": true, "interval_seconds": seconds]]]]
        run { [weak self] in
            guard let self, self.epoch == version, self.user["telemetry_consent"].bool else { return }
            do { _ = try await self.api.json("/events", method: "POST", body: body) }
            catch { if self.epoch == version { self.notice = "Activity could not be recorded. Learning still works; no missing interval is claimed." } }
        }
    }

    /// Start or stop the app-wide interaction monitor to match the current auth + consent
    /// state. The monitor is installed once and stays until consent is revoked or the
    /// learner signs out, at which point it is torn down so no interaction is recorded.
    private func refreshTelemetryMonitor() {
        let shouldArm = authenticated && user["telemetry_consent"].bool
        if shouldArm, !telemetryArmed {
            if clickTelemetry == nil { clickTelemetry = ClickTelemetry() }
            clickTelemetry?.start(store: self)
            telemetryArmed = true
        } else if !shouldArm, telemetryArmed {
            clickTelemetry?.stop()
            telemetryArmed = false
        }
    }

    /// Record that the learner touched a named control.
    ///
    /// The event monitor can only say "a click happened on the Studio page"; a call site that
    /// knows the learner opened the deck can say `stage.tab.deck`, which is what makes the
    /// interaction summary worth reading. Consent, vocabulary and batching are all handled by
    /// ``ClickTelemetry`` - a call site that forgets to check consent cannot leak, because the
    /// check is not the call site's to make.
    func recordInteraction(_ target: String, kind: String = "click") {
        clickTelemetry?.record(kind: kind, target: target)
    }
}
