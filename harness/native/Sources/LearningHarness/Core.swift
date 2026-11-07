import Foundation
import Security
import AppKit
import Combine
import UniformTypeIdentifiers

indirect enum JSON: Codable, Equatable, Hashable {
    case object([String: JSON]), array([JSON]), string(String), number(Double), bool(Bool), null
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let v = try? c.decode(Bool.self) { self = .bool(v) }
        else if let v = try? c.decode(Double.self) { self = .number(v) }
        else if let v = try? c.decode(String.self) { self = .string(v) }
        else if let v = try? c.decode([JSON].self) { self = .array(v) }
        else { self = .object(try c.decode([String: JSON].self)) }
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .object(let v): try c.encode(v)
        case .array(let v): try c.encode(v)
        case .string(let v): try c.encode(v)
        case .number(let v): try c.encode(v)
        case .bool(let v): try c.encode(v)
        case .null: try c.encodeNil()
        }
    }
    subscript(_ key: String) -> JSON { if case .object(let v) = self { return v[key] ?? .null }; return .null }
    var array: [JSON] { if case .array(let v) = self { return v }; return [] }
    var object: [String: JSON] { if case .object(let v) = self { return v }; return [:] }
    /// String values of an object, ignoring non-string entries.
    var stringMap: [String: String] {
        var out: [String: String] = [:]
        for (key, value) in object where !value.string.isEmpty { out[key] = value.string }
        return out
    }
    var string: String {
        switch self { case .string(let v): return v; case .number(let v): return v.formatted(); default: return "" }
    }
    var double: Double { if case .number(let v) = self { return v }; return Double(string) ?? 0 }
    var int: Int { let v = double; return v.isFinite && abs(v) < Double(Int.max) ? Int(v) : 0 }
    var bool: Bool { if case .bool(let v) = self { return v }; return false }
    var isNull: Bool { self == .null }
    func text(_ key: String, fallback: String = "") -> String { let v = self[key].string; return v.isEmpty ? fallback : v }
    static func make(_ value: [String: Any]) throws -> JSON { try JSONDecoder().decode(JSON.self, from: JSONSerialization.data(withJSONObject: value)) }
}

struct AppFailure: LocalizedError {
    let message: String
    let status: Int?
    var errorDescription: String? { message }
}

/// One Server-Sent Event: the wire name plus the decoded JSON payload.
///
/// Both halves travel because a client that only reads the data cannot tell an
/// ``error`` from a ``tool_result``, and both matter: one is a failure to report and
/// the other is work the tutor did.
struct ServerEvent: Equatable {
    let name: String
    let payload: JSON
}

/// One line of "what the tutor is doing", from the agent loop's ``label`` field.
///
/// The state machine is deliberately three-valued: ``running`` until the tool reports,
/// then ``done`` or ``failed``. A chip that never settles would leave a learner
/// wondering whether the tutor is still working, and a chip that only ever shows
/// success would hide the refusals that are part of an honest turn.
struct ChatActivity: Identifiable, Equatable {
    enum State: String, Equatable { case running, done, failed }
    let id: String
    let label: String
    var state: State
}

enum SecureSession {
    private static let service = "com.luminfest.learning-harness.session"
    static func read(endpoint: String) -> String? {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
            kSecAttrAccount as String: endpoint, kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess, let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }
    static func write(_ token: String, endpoint: String) throws {
        remove(endpoint: endpoint)
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
            kSecAttrAccount as String: endpoint, kSecValueData as String: Data(token.utf8),
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly]
        let status = SecItemAdd(query as CFDictionary, nil)
        guard status == errSecSuccess else { throw AppFailure(message: "Keychain could not save your session (\(status)).", status: nil) }
    }
    static func remove(endpoint: String) {
        SecItemDelete([kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                      kSecAttrAccount as String: endpoint] as CFDictionary)
    }
}

@MainActor final class APIClient {
    var endpoint: String
    var token: String?
    private var session: URLSession
    /// A session for the tutor's streamed turn. Its own on purpose: a turn runs a tool
    /// and then a provider call and then another tool, so it can take minutes, and the
    /// default 45 s resource timeout would abort a healthy lesson mid-sentence.
    private let streamSession: URLSession
    init(endpoint: String) {
        self.endpoint = endpoint
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 25
        config.timeoutIntervalForResource = 45
        session = URLSession(configuration: config)
        let streamConfig = URLSessionConfiguration.ephemeral
        streamConfig.timeoutIntervalForRequest = 300
        streamConfig.timeoutIntervalForResource = 900
        streamSession = URLSession(configuration: streamConfig)
    }
    func cancelAll() {
        session.invalidateAndCancel()
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 25
        session = URLSession(configuration: config)
    }
    static func validateEndpoint(_ text: String) throws -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard let u = URL(string: trimmed), let scheme = u.scheme, ["http", "https"].contains(scheme),
              let host = u.host, u.user == nil, u.password == nil, u.query == nil, u.fragment == nil,
              u.path.isEmpty || u.path == "/" else {
            throw AppFailure(message: "Use a server origin such as http://127.0.0.1:8765 (no path or credentials).", status: nil)
        }
        if scheme == "http" && !["127.0.0.1", "localhost", "::1"].contains(host) {
            throw AppFailure(message: "Remote servers must use HTTPS to protect your account.", status: nil)
        }
        return trimmed
    }
    func data(_ path: String, method: String = "GET", body: [String: Any]? = nil, query: [URLQueryItem] = []) async throws -> Data {
        guard var components = URLComponents(string: endpoint + "/api/v1" + path) else { throw AppFailure(message: "Invalid server address.", status: nil) }
        if !query.isEmpty { components.queryItems = query }
        guard let url = components.url else { throw AppFailure(message: "Invalid request URL.", status: nil) }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        // Telling the server which language the learner is reading is what makes generated
        // questions, tutor turns and decks come back in that language rather than English.
        request.setValue(Self.acceptLanguage(preference: UserDefaults.standard.string(forKey: "luminfest.language")),
                         forHTTPHeaderField: "Accept-Language")
        if let token { request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization") }
        if let body { request.httpBody = try JSONSerialization.data(withJSONObject: body); request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw AppFailure(message: "The server returned an invalid response.", status: nil) }
        guard (200..<300).contains(response.statusCode) else {
            let j = (try? JSONDecoder().decode(JSON.self, from: data)) ?? .null
            throw AppFailure(message: Self.failureDetail(j, status: response.statusCode),
                             status: response.statusCode)
        }
        return data
    }
    /// The `Accept-Language` this app sends.
    ///
    /// Read from the stored preference rather than from `Localization.shared`: request
    /// paths run off the main actor, and a background `Task` must not crash on an isolated
    /// access or quietly fall back to English. `nil` means "follow the system", which is
    /// the same promise the language picker makes.
    nonisolated static func acceptLanguage(preference: String?,
                                           system: [String] = Locale.preferredLanguages) -> String {
        switch preference {
        case AppLanguage.simplifiedChinese.rawValue:
            // The q-values are not decoration: without them a server that honours
            // preference order can pick `en` from the tail of the list.
            return "zh-Hans,zh;q=0.9,en;q=0.5"
        case AppLanguage.english.rawValue:
            return "en"
        default:
            return system.first ?? "en"
        }
    }

    func json(_ path: String, method: String = "GET", body: [String: Any]? = nil, query: [URLQueryItem] = []) async throws -> JSON {
        let d = try await data(path, method: method, body: body, query: query)
        return d.isEmpty ? .null : try JSONDecoder().decode(JSON.self, from: d)
    }

    /// The server's own explanation for a non-2xx, or a sentence naming the status.
    ///
    /// A failed validation arrives as ``detail`` = a *list* of `{loc, msg}` objects. Reading
    /// only the string form collapsed every one of them to "Request failed (HTTP 422)",
    /// which is indistinguishable from "the server is down" and sends the reader looking for
    /// a network fault that does not exist. The per-field join is shared by the JSON and the
    /// SSE path on purpose: `/agent/stream` is the endpoint the tutor chat uses, so leaving
    /// the stream on the old code meant the one screen a learner actually stares at kept the
    /// useless message.
    private static func failureDetail(_ body: JSON, status: Int) -> String {
        let problems = body["detail"].array.compactMap { item -> String? in
            let message = item.text("msg", fallback: "")
            guard !message.isEmpty else { return nil }
            let field = item["loc"].array.map(\.string).last(where: { !$0.isEmpty }) ?? ""
            return field.isEmpty ? message : "\(field): \(message)"
        }
        if !problems.isEmpty { return problems.joined(separator: "; ") }
        return body.text("detail", fallback: body["detail"].text("message", fallback: body.text("error", fallback: body.text("message", fallback: "Request failed (HTTP \(status))."))))
    }

    /// POST a body and read the reply as a Server-Sent Events stream.
    ///
    /// ``/agent/stream`` emits one ``event:``/``data:`` pair per agent-loop event, and
    /// the server sends each one at the moment the loop produced it. That is what lets
    /// the tutor chat show "Drawing on the whiteboard" while the tutor is drawing,
    /// instead of a finished transcript that appears all at once. Token-level streaming
    /// would need a streaming provider path; the server does not fake it and neither
    /// does this reader.
    ///
    /// A non-2xx is reported with the server's own sentence, exactly as the JSON path
    /// does, because "the stream failed" tells the learner nothing they can act on.
    func serverEvents(_ path: String, body: [String: Any]) -> AsyncThrowingStream<ServerEvent, Error> {
        AsyncThrowingStream(ServerEvent.self) { continuation in
            guard let components = URLComponents(string: endpoint + "/api/v1" + path),
                  let url = components.url else {
                continuation.finish(throwing: AppFailure(message: "Invalid server address.", status: nil))
                return
            }
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
            request.setValue(Self.acceptLanguage(preference: UserDefaults.standard.string(forKey: "luminfest.language")),
                             forHTTPHeaderField: "Accept-Language")
            if let token { request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization") }
            request.httpBody = try? JSONSerialization.data(withJSONObject: body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            let work = Task {
                do {
                    let (bytes, response) = try await streamSession.bytes(for: request)
                    guard let http = response as? HTTPURLResponse else {
                        throw AppFailure(message: "The server returned an invalid response.", status: nil)
                    }
                    guard (200..<300).contains(http.statusCode) else {
                        var buffer = Data()
                        for try await byte in bytes { buffer.append(byte) }
                        let j = (try? JSONDecoder().decode(JSON.self, from: buffer)) ?? .null
                        throw AppFailure(message: Self.failureDetail(j, status: http.statusCode),
                                         status: http.statusCode)
                    }
                    var name = "message"
                    var dataLines: [String] = []
                    for try await line in bytes.lines {
                        if line.isEmpty {
                            // A blank line dispatches. A comment line (": keep-alive")
                            // carries no data and is skipped rather than dispatched.
                            if !dataLines.isEmpty {
                                continuation.yield(ServerEvent(name: name, payload: decode(dataLines)))
                            }
                            name = "message"
                            dataLines = []
                            continue
                        }
                        if line.hasPrefix(":") { continue }
                        if line.hasPrefix("event:") {
                            name = String(line.dropFirst("event:".count)).trimmingCharacters(in: .whitespaces)
                        } else if line.hasPrefix("data:") {
                            dataLines.append(String(line.dropFirst("data:".count)).trimmingCharacters(in: .whitespaces))
                        }
                    }
                    // A final event with no terminating blank line still happened.
                    if !dataLines.isEmpty {
                        continuation.yield(ServerEvent(name: name, payload: decode(dataLines)))
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in work.cancel() }
        }
    }

    private func decode(_ dataLines: [String]) -> JSON {
        let text = dataLines.joined(separator: "\n")
        return (try? JSONDecoder().decode(JSON.self, from: Data(text.utf8))) ?? .null
    }

    /// The bytes of a server-relative artifact path, e.g.
    /// `/api/v1/sims/deck-abc/download/v1.pptx`.
    ///
    /// Every artifact route is bearer-protected, so a web view or a browser pointed straight
    /// at the URL gets a 401 and shows the learner nothing. The only way the app can hand
    /// over a file the server actually built is to fetch it through this client, which is
    /// what this does. The path must sit under `/api/v1/`: a server-supplied string cannot
    /// turn this into a request to another host, because an absolute URL does not start with
    /// that prefix.
    func artifact(_ path: String) async throws -> Data {
        guard path.hasPrefix("/api/v1/") else {
            throw AppFailure(message: "That address is not an artifact on this backend.", status: nil)
        }
        return try await data(String(path.dropFirst("/api/v1".count)))
    }
}

enum Page: String, CaseIterable, Identifiable {
    case today, studio, map, review, teacher, projects, insights, settings
    var id: String { rawValue }
    /// Localized through `L10n` rather than a switch over English literals.
    ///
    /// The sidebar, the window title and the `Learning` menu all render this one
    /// property, so a single lookup keeps three surfaces in step when the language
    /// changes — a switch here would leave the menu in English after a switch to Chinese.
    /// Keys are `nav.<case>`; see Localizable.strings.
    var title: String { L10n.t("nav.\(rawValue)") }
    var icon: String {
        switch self { case .today: return "sun.max"; case .studio: return "book.closed"; case .map: return "point.3.connected.trianglepath.dotted"; case .review: return "arrow.trianglehead.clockwise"; case .teacher: return "bubble.left.and.text.bubble.right"; case .projects: return "square.stack.3d.up"; case .insights: return "chart.xyaxis.line"; case .settings: return "slider.horizontal.3" }
    }
    var eyebrow: String {
        switch self { case .today: return "YOUR LEARNING, IN FOCUS"; case .studio: return "UNDERSTAND. EXPLORE. APPLY."; case .map: return "CONNECT THE IDEAS"; case .review: return "MAKE IT STICK"; case .teacher: return "A LITTLE GUIDANCE"; case .projects: return "FROM KNOWING TO MAKING"; case .insights: return "EVIDENCE, NOT ASSUMPTIONS"; case .settings: return "MAKE LUMINFEST YOURS" }
    }
    var subtitle: String {
        switch self { case .today: return "Small steps. Deeper understanding. A little progress, every day."; case .studio: return "A quiet space to read, experiment, and work through an idea."; case .map: return "See how your understanding grows, one connection at a time."; case .review: return "Revisit the right ideas at the right time."; case .teacher: return "Ask a question. Find a grounded explanation."; case .projects: return "Put your learning into something you can call your own."; case .insights: return "An honest picture of the practice you have actually done."; case .settings: return "Your goals, your privacy, and your learning environment." }
    }
}

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
    private var epoch = UUID()
    private var tasks: [UUID: Task<Void, Never>] = [:]
    private var retryAction: (() async -> Void)?
    private var timer: AnyCancellable?
    private var lastTick = ProcessInfo.processInfo.systemUptime
    private var activeSeconds: Double = 0
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

    // MARK: Course and plan
    /// Every course the harness ships, with the learner's enrolment marked.
    var courseList: [JSON] { courses["courses"].array }
    var enrolledCourseID: String { user["course_id"].string }
    var currentCourse: JSON { courseList.first { $0["id"].string == enrolledCourseID } ?? .null }
    var courseTitle: String { currentCourse.text("title", fallback: "Your course") }
    var courseSubject: String { currentCourse.text("subject", fallback: "Learning") }
    /// First run only. A learner who has never chosen a course is shown the setup flow once.
    ///
    /// The native QA suite drives both the first-run path and the returning-learner path from one
    /// binary, so it needs a supported way to suppress the sheet. This is the same
    /// `NATIVE_QA_*` channel the account details already arrive on; it is inert in normal use.
    private var setupSuppressed: Bool { ProcessInfo.processInfo.environment["NATIVE_QA_SKIP_SETUP"] == "1" }
    var needsCourseSetup: Bool { authenticated && !user["onboarding_complete"].bool && !setupDismissed && !setupSuppressed }

    /// Whether the shell should be replaced by first-run setup.
    ///
    /// Deliberately derived rather than latched. Raising a sheet in the same update cycle that
    /// swaps `OnboardingView` for `AppShell` is racy: SwiftUI intermittently drops the
    /// presentation, and the learner is silently dropped onto a course they never chose. A view
    /// branch has no presentation to lose, and it still reads as a first-run flow because it
    /// disappears the moment the course is saved.
    var inCourseSetup: Bool { authenticated && !restoring && (needsCourseSetup || showCourseSetup) }

    /// Today's session, as the server derived it from the goal, the pace and the evidence.
    var planToday: [JSON] { plan["today"]["concepts"].array }
    var planPace: JSON { plan["pace"] }
    var planProgress: JSON { plan["progress"] }

    // MARK: Knowledge graph
    /// Every concept node in the course, in the backend's topological order.
    var graphNodes: [JSON] { graph["nodes"].array }
    var graphEdges: [JSON] { graph["edges"].array }
    var graphStats: JSON { graph["stats"] }
    /// Strand -> unit -> topic skeleton, in teaching order.
    var graphTaxonomy: JSON { graph["taxonomy"] }
    /// Reviewed join from an authored lesson id to the course node it teaches.
    var lessonTargets: [String: String] { graph["lesson_targets"].stringMap }
    /// Course node id -> authored lesson id, the reverse join.
    var nodeToLesson: [String: String] {
        var map: [String: String] = [:]
        for (lesson, node) in lessonTargets { map[node] = lesson }
        return map
    }
    func graphNode(_ id: String) -> JSON { graphNodes.first { $0["id"].string == id } ?? .null }
    func graphTitle(_ id: String) -> String { graphNode(id).text("title", fallback: id) }

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

    /// Save the first-run choices: the course, the goal in the learner's own words, the pace.
    ///
    /// All three travel in one request, because a course without a pace and a goal is not
    /// yet a plan. The server marks onboarding complete when the course changes, so this
    /// flow appears once rather than on every launch.
    func saveSetup(courseID: String, goal: String, minutes: Int) async {
        guard !setupBusy else { return }
        setupBusy = true; setupError = nil; error = nil
        let version = epoch
        defer { if epoch == version { setupBusy = false } }
        var body: [String: Any] = ["course_id": courseID, "daily_minutes": max(1, min(240, minutes))]
        let trimmed = goal.trimmingCharacters(in: .whitespacesAndNewlines)
        // The server rejects an empty goal rather than storing a blank one, so it is omitted.
        if !trimmed.isEmpty { body["goal"] = trimmed }
        do {
            let result = try await api.json("/me", method: "PATCH", body: body)
            guard epoch == version else { return }
            user = result["user"].isNull ? result : result["user"]
            connected = true
            // The curriculum, the map and the plan all belong to the previous course, so
            // nothing from it may be left on screen.
            curriculum = .null; graph = .null; lesson = .null; reviews = .null
            projects = .null; analytics = .null; messages = []; selectedConcept = ""
            showCourseSetup = false
            await refresh()
            guard epoch == version else { return }
            let title = currentCourse.text("title", fallback: "")
            if !title.isEmpty { notice = "You are enrolled in \(title). Your plan is ready on Today." }
        } catch { if epoch == version { setupError = error.localizedDescription } }
    }

    /// Switch course from Settings, keeping the learner's goal and pace.
    func switchCourse(_ courseID: String) async {
        await saveSetup(courseID: courseID, goal: user["goal"].string,
                        minutes: max(1, user["daily_minutes"].int))
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
        case .insights: await load("/analytics") { self.analytics = $0 }
        case .settings: await load("/me") { self.user = $0["user"].isNull ? $0 : $0["user"] }
        }
        if epoch == version { busy = false }
    }
    func retry() { error = nil; if let retryAction { run { await retryAction() } } }
    /// The map page needs both layers: the authored lessons and the full course graph.
    func loadMap() async {
        await load("/curriculum") { self.curriculum = $0 }
        await load("/knowledge-graph") { self.graph = $0 }
    }
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
    func loadChat() async {
        let id = selectedConcept, version = epoch
        guard !id.isEmpty else { return }
        do {
            let result = try await api.json("/chat", query: [URLQueryItem(name: "concept_id", value: id)])
            guard version == epoch, id == selectedConcept, authenticated else { return }
            messages = result["messages"].isNull ? result.array : result["messages"].array
            chatMedia = []
        } catch { if epoch == version && id == selectedConcept { record(error) } }
    }
    func sendMessage(_ text: String) async {
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, !selectedConcept.isEmpty, !chatBusy else { return }
        // Asking is the clearest evidence there is that the learner is here; without this
        // the interval check would keep asking the server about someone who is talking.
        noteLearnerAction()
        let version = epoch, id = selectedConcept
        chatBusy = true
        chatActivities = []
        speechStatus = ""
        speech.stop()
        defer { if epoch == version { chatBusy = false } }
        do {
            // The agentic turn: the tutor runs the full tool loop (curriculum lookups,
            // licence-cleared image search, workspace, ...) and the response carries the
            // media it surfaced, so the chat can show real pictures instead of prose-only.
            //
            // `board_id` names the Stage's shared whiteboard for this concept, which is
            // what tells the tutor it has a board to draw on; without it the draw-aloud
            // section of its instructions never fires and the lesson stays text.
            var request: [String: Any] = ["message": text, "developer_mode": false,
                                          "context": ["concept_id": id, "role": "learner",
                                                      "board_id": "wb-\(id)"],
                                          "speak": speakEnabled]
            if !teacherStyleProfile.isEmpty { request["teacher_profile"] = teacherStyleProfile }

            // The streamed turn first: each event arrives as the loop produces it, so the
            // activity chips are live rather than a finished trace. `/agent/chat` is the
            // fallback for a backend without the SSE route - same reply, no live chips.
            var reply = ""
            var reason = ""
            var speechDescriptor: JSON = .null
            var events: [JSON] = []
            var streamed = false
            do {
                for try await event in api.serverEvents("/agent/stream", body: request) {
                    guard epoch == version, id == selectedConcept else { return }
                    events.append(event.payload)
                    switch event.name {
                    case "tool_call":
                        let label = event.payload["label"].string
                        if !label.isEmpty {
                            chatActivities.append(ChatActivity(id: event.payload["id"].string,
                                                               label: label, state: .running))
                        }
                    case "tool_result":
                        if let index = chatActivities.lastIndex(where: { $0.id == event.payload["id"].string }) {
                            chatActivities[index].state = event.payload["ok"].bool ? .done : .failed
                        }
                    case "message_delta":
                        reply += event.payload["text"].string
                    case "turn_end":
                        reason = event.payload["reason"].string
                        speechDescriptor = event.payload["speech"]
                    default:
                        break
                    }
                }
                streamed = true
            } catch {
                // A backend without `/agent/stream`, or a connection that dropped
                // mid-turn. The JSON route carries the same answer, so fall through to
                // it rather than reporting a failure the learner does not have.
            }
            if !streamed {
                let result = try await api.json("/agent/chat", method: "POST", body: request)
                guard epoch == version, id == selectedConcept else { return }
                reply = result["message"].string
                reason = result["finish_reason"].string
                speechDescriptor = result["speech"]
                events = result["events"].array
                for event in events {
                    switch event["type"].string {
                    case "tool_call":
                        let label = event["label"].string
                        if !label.isEmpty {
                            chatActivities.append(ChatActivity(id: event["id"].string,
                                                               label: label, state: .running))
                        }
                    case "tool_result":
                        if let index = chatActivities.lastIndex(where: { $0.id == event["id"].string }) {
                            chatActivities[index].state = event["ok"].bool ? .done : .failed
                        }
                    default:
                        break
                    }
                }
            }
            guard epoch == version, id == selectedConcept else { return }
            messages.append(try JSON.make(["role": "user", "content": text]))
            if !reply.isEmpty {
                messages.append(try JSON.make(["role": "assistant", "content": reply]))
            }
            // The media the tutor's own tools surfaced, read off the turn's events.
            // Taken from the events rather than a second search: what the trace says the
            // tutor found is what the learner should be shown, and re-searching would
            // produce a different list than the one the reply is grounded in.
            chatMedia = mediaFromTurnEvents(events)
            if reply.isEmpty && reason != "completed" {
                record(AppFailure(message: "The tutor turn finished without a reply (finish_reason: \(reason.isEmpty ? "unknown" : reason)).", status: nil))
            }
            connected = true
            if !speechDescriptor.isNull { playSpeech(speechDescriptor, version: version) }
        } catch { if epoch == version { record(error) } }
    }

    /// The licence-cleared media a turn surfaced, from its own event trace.
    ///
    /// Two shapes arrive: ``image_search`` returns an ``images`` list of embed-posture
    /// URLs, and ``find_image`` returns one ``asset`` this instance already downloaded.
    /// Both are rendered from the trace so the grid can never show a picture the tutor
    /// did not actually find.
    private func mediaFromTurnEvents(_ events: [JSON]) -> [[String: String]] {
        var out: [[String: String]] = []
        var seen = Set<String>()
        for event in events where event["type"].string == "tool_result" && event["ok"].bool {
            let inner = event["data"]["data"]
            guard !inner.isNull else { continue }
            for candidate in inner["images"].array {
                let url = candidate["thumb_url"].string.isEmpty ? candidate["file_url"].string : candidate["thumb_url"].string
                guard !url.isEmpty, !seen.contains(url) else { continue }
                seen.insert(url)
                out.append(["thumb_url": url, "title": candidate["title"].string,
                            "licence": candidate["licence"].string,
                            "source_page": candidate["landing_page_url"].string])
            }
            let asset = inner["asset"]
            if !asset.isNull, !asset["title"].isNull {
                let url = asset["file_url"].string
                guard !url.isEmpty, !seen.contains(url) else { continue }
                seen.insert(url)
                out.append(["thumb_url": url, "title": asset["title"].string,
                            "licence": asset["licence_code"].string,
                            "source_page": asset["landing_page_url"].string])
            }
        }
        return Array(out.prefix(8))
    }

    /// Speak the tutor's reply through the local VoiceStudio backend.
    ///
    /// The clip is rendered off the request path - a local synthesis costs 20-40 s for a
    /// paragraph, and a learner must not wait that long to read the answer - so the
    /// descriptor usually says ``pending`` and this polls until the bytes exist. A
    /// refusal (voice output switched off, an engine that is not running) is reported
    /// with the server's own sentence rather than silently doing nothing.
    private func playSpeech(_ descriptor: JSON, version: UUID) {
        let url = descriptor["url"].string
        guard !url.isEmpty else { return }
        switch descriptor["state"].string {
        case "ready":
            loadAndSpeak(url, version: version)
        case "unavailable", "failed":
            speechStatus = descriptor["reason"].string
        default:
            speechStatus = "Preparing the tutor's voice…"
            Task { [weak self] in
                guard let self else { return }
                for _ in 0..<120 {           // up to ~60 s, one poll every half second
                    if self.epoch != version { return }
                    if let data = try? await self.api.artifact(url), !data.isEmpty {
                        self.speechStatus = ""
                        self.speech.play(data)
                        return
                    }
                    try? await Task.sleep(nanoseconds: 500_000_000)
                }
                self.speechStatus = "The tutor's voice did not finish rendering."
            }
        }
    }

    private func loadAndSpeak(_ url: String, version: UUID) {
        Task { [weak self] in
            guard let self else { return }
            guard let data = try? await self.api.artifact(url), !data.isEmpty else {
                if self.epoch == version { self.speechStatus = "The recording could not be read." }
                return
            }
            if self.epoch == version { self.speech.play(data) }
        }
    }
    // -------------------------------------------------- external media surfaces
    //
    // Three concept-scoped media surfaces beyond the lesson payload: the narrated deck
    // (NotebookLM-style, assembled server-side), the external simulation map for this
    // concept, and curated video. All three are data from the same licence-gated
    // pipeline; the client renders status honestly and never upgrades a withheld card.

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

    var deckData: JSON { deck["ok"].bool ? deck["data"] : .null }

    func buildDeck() async {
        guard authenticated, !selectedConcept.isEmpty, !deckBusy else { return }
        let version = epoch, id = selectedConcept
        deckBusy = true
        defer { if epoch == version { deckBusy = false } }
        do {
            let result = try await api.json("/presentations", method: "POST",
                                            body: ["concept_id": id, "options": [String: Any]()])
            guard epoch == version, id == selectedConcept else { return }
            deck = result
            showDeck = result["ok"].bool
            connected = true
        } catch { if epoch == version { record(error) } }
    }

    func loadConceptSimulations() async {
        guard authenticated, !selectedConcept.isEmpty, !conceptSimulationsBusy else { return }
        let version = epoch, id = selectedConcept
        conceptSimulationsBusy = true
        defer { if epoch == version { conceptSimulationsBusy = false } }
        do {
            let path = "/simulations/" + id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed)! + "/external"
            let result = try await api.json(path)
            guard epoch == version, id == selectedConcept else { return }
            conceptSimulations = result
            connected = true
        } catch { if epoch == version { record(error) } }
    }

    /// Load the playground catalogue, so the entry point can list real games rather than
    /// describe them in the abstract. The gallery page fetches the same endpoint for itself;
    /// this copy is for the native card, and the two cannot disagree because they read the
    /// one catalogue.
    func loadPlayground() async {
        guard authenticated, !playgroundBusy else { return }
        let version = epoch
        playgroundBusy = true
        defer { if epoch == version { playgroundBusy = false } }
        do {
            let result = try await api.json("/playground")
            guard epoch == version else { return }
            playground = result
            connected = true
        } catch { if epoch == version { record(error) } }
    }

    /// Open the gallery sheet, optionally on one game. The slug is only a hint for the page;
    /// if it cannot be honoured the gallery is shown on its own list.
    func openPlayground(slug: String? = nil) {
        playgroundSlug = slug
        showPlayground = true
    }

    /// The one honest telemetry fact about an external simulation: the learner opened it.
    /// A PhET embed reports no parameters back, so this event carries only the concept id -
    /// it never fabricates an interaction value the app cannot observe. Consent-gated like
    /// every other telemetry path; rejected outright when consent is off.
    func recordExternalSimulationOpened(concept: String) async {
        guard authenticated, user["telemetry_consent"].bool, !concept.isEmpty else { return }
        let body: [String: Any] = ["events": [["id": UUID().uuidString,
                                               "type": "external_simulation_opened",
                                               "occurred_at": ISO8601DateFormatter().string(from: Date()),
                                               "payload": ["concept_id": concept]]]]
        do { _ = try await api.json("/events", method: "POST", body: body) }
        catch { record(error) }
    }

    // -------------------------------------------------- harness agent surfaces
    //
    // The 9-MOVES loop (backend harness/loop.py) was fully built but dark: no UI called
    // it, so the learner's "next step" came from the simpler planner. These loaders wire
    // the decision surface in. Degradation is visible by construction: a failed plan
    // fetch records the error and the card says the harness is unavailable instead of
    // silently reusing the planner output.

    /// The live harness decision for the recommended concept, or the reason there is none.
    @Published var harnessPlanState = HarnessPlanState()
    @Published var harnessOutcomeBusy = false

    func loadHarnessPlan(conceptID: String) async {
        guard authenticated, !conceptID.isEmpty else { return }
        do {
            let path = "/harness/plan?concept_id=" + conceptID.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed)!
            // The plan endpoint returns {decision, explanation} directly (no ok/data envelope).
            let result = try await api.json(path)
            let decision = result["decision"]
            if decision.isNull {
                harnessPlanState = HarnessPlanState(error: "The harness returned no decision for this concept.")
            } else {
                harnessPlanState = HarnessPlanState(
                    decision: HarnessDecision(json: decision),
                    explanation: result["explanation"].string)
            }
            connected = true
        } catch {
            harnessPlanState = HarnessPlanState(
                error: "The harness planner is unreachable (\(error.localizedDescription)). The simpler planner recommendation below is the fallback, clearly labelled.")
            record(error)
        }
    }

    /// Feed the learner's verdict back into the loop's procedural memory. The backend
    /// records the outcome against the run.
    ///
    /// The route takes `progress` (a *measured* change in [-1, 1]) and a free-text `note`.
    /// It does not take an `outcome` verdict, and the request used to send exactly that —
    /// `{"outcome": "helpful", "notes": ""}` — which the schema rejected with 422 because
    /// `progress` was missing and both field names were unknown. The button never worked.
    ///
    /// A self-report is not a measurement, so `progress` stays 0 and the verdict goes in the
    /// note. Sending +1 here would make the loop write "this move was followed by progress
    /// (measured change +1.00)" about a learner who pressed a button, which is a claim the
    /// evidence does not support.
    func submitHarnessOutcome(runID: String, outcome: String) async {
        guard authenticated, !harnessOutcomeBusy else { return }
        harnessOutcomeBusy = true
        defer { harnessOutcomeBusy = false }
        do {
            _ = try await api.json("/harness/plan/" + runID + "/outcome", method: "POST",
                                   body: ["progress": 0,
                                          "note": "Learner self-report, not a measurement: this move was "
                                              + outcome + "."])
            notice = "Recorded your read on this move: \(outcome). It is kept as your own report, not as measured progress."
        } catch { record(error) }
    }

    // ------------------------------------------------------- lesson procedure
    //
    // The 9-moves card names the decision for one turn; this is the run of show those
    // turns sit inside. The sequence is compiled on the server from this learner's own
    // evidence and the artifacts this instance actually holds, so the app never decides
    // what comes next - it renders the plan it was given and reports which block
    // finished. Advancing a block records *that the activity happened*, never that it
    // went well: mastery still moves only through submitted answers and playground runs.

    @Published var lessonProcedure = LessonProcedureState()
    @Published var lessonProcedureBusy = false

    /// The concept the Today card is about: the planner's recommendation, or the harness
    /// decision when the 9-moves view is driving.
    var lessonConceptID: String {
        let recommended = dashboard["recommendation"]["concept_id"].string
        if !recommended.isEmpty { return recommended }
        return harnessPlanState.decision?.conceptID ?? ""
    }

    /// Compile (or fetch) this concept's lesson without starting it.
    func loadLessonProcedure(conceptID: String) async {
        guard authenticated, !conceptID.isEmpty else { return }
        do {
            let path = "/procedure/" + conceptID.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed)!
            let result = try await api.json(path)
            lessonProcedure = LessonProcedureState(preview: result)
            connected = true
        } catch {
            // A failed compile is reported, not hidden behind an empty card: the learner
            // should know the harness could not plan rather than assume there is no plan.
            var failed = LessonProcedureState()
            failed.error = "The harness could not compile a lesson (\(error.localizedDescription))."
            lessonProcedure = failed
            record(error)
        }
    }

    /// Persist the plan and build the deck it promises, then show the run.
    func startLessonProcedure(conceptID: String) async {
        guard authenticated, !conceptID.isEmpty, !lessonProcedureBusy else { return }
        lessonProcedureBusy = true
        defer { lessonProcedureBusy = false }
        do {
            let path = "/procedure/" + conceptID.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed)! + "/start"
            let result = try await api.json(path, method: "POST")
            lessonProcedure = LessonProcedureState(run: result)
            notice = "Lesson started: \(lessonProcedure.blocks.count) activities, about \(lessonProcedure.totalMinutes) minutes."
            connected = true
        } catch { record(error) }
    }

    /// Mark one block done (or skipped) and move the card on.
    func advanceLessonProcedure(order: Int, outcome: String) async {
        guard authenticated, !lessonProcedureBusy, !lessonProcedure.runID.isEmpty else { return }
        lessonProcedureBusy = true
        defer { lessonProcedureBusy = false }
        do {
            let result = try await api.json("/procedure/runs/" + lessonProcedure.runID + "/advance",
                                            method: "POST",
                                            body: ["order": order, "outcome": outcome])
            lessonProcedure = LessonProcedureState(run: result)
            if lessonProcedure.isComplete {
                notice = "Lesson complete. Your mastery is unchanged until you answer the practice questions."
                await refresh()
            }
        } catch { record(error) }
    }

    /// Save the lesson deck's `.pptx` twin, the file the procedure's deck block advertises.
    ///
    /// The twin is built on the server and served behind the bearer token, so it is fetched
    /// through the API client and written wherever the learner chooses. Offering the URL
    /// instead would be a promise the app cannot keep: the browser has no session, so the
    /// download would fail with 401 and the deck block would have claimed a file nobody
    /// could open. A refusal from the panel is silence, not an error - the learner changed
    /// their mind.
    func saveLessonDeckPPTX(artifactID: String, fileName: String, suggestedName: String) async {
        guard authenticated, !artifactID.isEmpty, !fileName.isEmpty else { return }
        do {
            let bytes = try await api.artifact("/api/v1/sims/\(artifactID)/download/\(fileName)")
            let panel = NSSavePanel()
            panel.allowedContentTypes = [UTType(filenameExtension: "pptx") ?? .data]
            panel.nameFieldStringValue = suggestedName
            guard panel.runModal() == .OK, let url = panel.url else { return }
            try bytes.write(to: url, options: .atomic)
            notice = "Deck saved to " + url.lastPathComponent
        } catch { record(error) }
    }

    func loadMediaPosture() async {
        guard authenticated else { return }
        let version = epoch
        do {
            let result = try await api.json("/media/sources")
            guard epoch == version else { return }
            // The image pipeline reports whether network media is enabled at all; the
            // client uses it to say "offline by configuration" rather than guessing.
            mediaOnline = result["image_pipeline"]["enabled"].bool
        } catch { if epoch == version { record(error) } }
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
    func updateTrainingConsent(_ enabled: Bool) async {
        let version = epoch
        do {
            _ = try await api.json("/training/consent", method: "POST", body: ["enabled": enabled])
            guard epoch == version else { return }
            await load("/me") { self.user = $0["user"].isNull ? $0 : $0["user"] }
            notice = enabled ? "Training consent recorded. New model candidates require offline validation before activation." : "Future training exports exclude this account. Existing models cannot be claimed to be untrained."
        } catch { if epoch == version { record(error) } }
    }
    func signOut() async {
        do { _ = try await api.data("/auth/logout", method: "POST") }
        catch { notice = "The server could not revoke the session. The local Keychain session was removed." }
        logout()
    }
    func updateSettings(goal: String, minutes: Int, consent: Bool) async {
        let version = epoch
        busy = true; error = nil
        defer { if epoch == version { busy = false } }
        let trimmed = goal.trimmingCharacters(in: .whitespacesAndNewlines)
        var body: [String: Any] = ["daily_minutes": max(1, min(240, minutes)), "telemetry_consent": consent]
        // A blank goal is rejected by the server rather than stored, so an empty field keeps
        // the goal already on record instead of failing the whole save.
        if !trimmed.isEmpty { body["goal"] = trimmed }
        do {
            let result = try await api.json("/me", method: "PATCH", body: body)
            guard epoch == version else { return }
            user = result["user"].isNull ? result : result["user"]
            activeSeconds = 0
            notice = trimmed.isEmpty && user["goal"].string.isEmpty
                ? "Your pace has been saved. Add a goal whenever you want one."
                : "Your preferences have been saved. Your plan has been re-derived."
            await refresh()
        } catch { if epoch == version { record(error) } }
    }
    func submitProject(id: String, text: String, disclosure: Bool, reflection: String) async {
        let version = epoch
        busy = true; error = nil
        defer { if epoch == version { busy = false } }
        do {
            _ = try await api.json("/projects/" + id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed)! + "/submit", method: "POST", body: ["text": text, "ai_disclosure": disclosure ? "AI assistance was used; the learner remains responsible for the submitted explanation." : "No AI assistance was used in this project.", "reflection": reflection])
            guard epoch == version else { return }
            await load("/projects") { self.projects = $0 }
            guard epoch == version, authenticated else { return }
            notice = "Project submitted. Your feedback is ready."
        } catch { if epoch == version { record(error) } }
    }
    func exportAccount() async {
        let version = epoch
        do {
            let data = try await api.data("/export")
            guard epoch == version, authenticated else { return }
            let panel = NSSavePanel(); panel.nameFieldStringValue = "luminfest-learning-export.json"; panel.allowedContentTypes = [.json]
            guard panel.runModal() == .OK, let url = panel.url else { return }
            try data.write(to: url, options: .atomic)
            notice = "Your learning data was exported."
        } catch { if epoch == version { record(error) } }
    }
    /// A support report the learner can paste into a message.
    ///
    /// The service's `/diagnostics` route is deliberately narrow — configuration and the
    /// tail of the local log, never the learner's work — and this adds the two facts only
    /// the client knows: which build is running, and which macOS it runs on. Without this
    /// there is no support channel at all, which is what the legal text used to promise
    /// and the app did not have.
    func copyDiagnosticReport() async {
        let version = epoch
        do {
            let data = try await api.data("/diagnostics")
            guard epoch == version, authenticated else { return }
            let body = String(data: data, encoding: .utf8) ?? "(the service returned no report)"
            let build = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown"
            let system = ProcessInfo.processInfo.operatingSystemVersionString
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString("Luminfest \(build) on \(system)\n\n" + body, forType: .string)
            notice = "A diagnostic report was copied to the clipboard."
        } catch { if epoch == version { record(error) } }
    }

    func deleteAccount() async {
        let version = epoch
        do { _ = try await api.json("/me", method: "DELETE", body: ["confirmation": "DELETE MY ACCOUNT"]); if epoch == version { logout() } }
        catch { if epoch == version { record(error) } }
    }
    func changeEndpoint(_ value: String) throws {
        let origin = try APIClient.validateEndpoint(value)
        guard origin != endpoint else { return }
        logout(); endpoint = origin; api.endpoint = origin
        UserDefaults.standard.set(origin, forKey: "luminfest.endpoint")
    }
    func logout() {
        epoch = UUID(); tasks.values.forEach { $0.cancel() }; tasks = [:]; api.cancelAll()
        SecureSession.remove(endpoint: endpoint); api.token = nil
        user = .null; dashboard = .null; curriculum = .null; graph = .null; lesson = .null; reviews = .null; projects = .null; analytics = .null; messages = []; teacherStyleProfile = [:]
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
