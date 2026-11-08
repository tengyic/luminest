import SwiftUI
import AppKit

// THE LESSON PROCEDURE. The 9-moves card (`HarnessPlanCard`) names the decision for *one
// turn*; this names the run of show those turns sit inside. The sequence is compiled on
// the server from the learner's own evidence and the artifacts that actually exist for
// the concept, so nothing here decides what comes next - the app renders the plan it was
// given and reports which block finished.
//
// Two rules are visible in this file on purpose:
//
//  * **The plan is not the evidence.** "Done" records that the learner did the activity.
//    It never moves mastery; only submitted answers and playground runs do that. The card
//    says so rather than implying progress equals learning.
//  * **A refusal is content.** Every activity the harness declined to schedule arrives
//    with the reason it was declined, and the card shows them. A learner who wonders why
//    there is no video gets the answer instead of a gap.

/// Mirror of one `ProcedureBlock.to_dict()` entry. Lenient by design: a field the backend
/// did not send renders as absent rather than blocking the row.
struct ProcedureStep: Identifiable {
    let order: Int
    let kind: String
    let label: String
    let minutes: Int
    let title: String
    let purpose: String
    let why: String
    let artifact: JSON
    let done: Bool
    var answers: JSON = .null

    var id: Int { order }
    var isScored: Bool { kind == "diagnostic" || kind == "practice" }
    var answersComplete: Bool { answers["complete"].bool }
    var completionReason: String {
        guard isScored, !answersComplete else { return "" }
        if answers.isNull {
            return "Answer progress has not been verified. Open the questions or retry loading; Skip remains available."
        }
        return "Answer all scheduled questions before Done (\(answers["answered"].int) of \(answers["total"].int) answered). Skip remains available."
    }

    /// The interactive this block plays, when it is a first-party playground game.
    ///
    /// The playground is the one artifact the app opens as a *hosted page* rather than
    /// rendering itself: the gallery owns the sandboxed iframe and the outcome POST that
    /// makes a run observable, and a native re-implementation would be a second copy of
    /// that trust boundary. A deck and a video are different - their content is data in the
    /// block, so they are rendered in the app (see `presentation`).
    var playgroundSlug: String {
        guard artifact.text("mode") == "playground" else { return "" }
        return artifact.text("slug")
    }

    var artifactKind: String { artifact.text("kind") }

    // ---------------------------------------------------------- what it can show
    //
    // The card can only say that a block happened. These read the artifact the block is
    // bound to, so a block that names a specific deck, video or worked example has a way to
    // open exactly that one. Every value comes from the run payload the server sent, never
    // from a lookup the app performs itself: the procedure is the harness's decision, and a
    // second source of truth for "which slides" is a second answer waiting to disagree.

    /// The deck's actual slides, as the server composed them.
    ///
    /// Rendered natively rather than fetched. The materialised HTML sits behind the bearer
    /// token, and a web view handed that URL has no session to send; the sections are the
    /// same content the HTML and the `.pptx` twin hold, so presenting them here needs no
    /// token, no web view and no network at all.
    var deckSections: [DeckSection] {
        artifact["sections"].array.map { row in
            DeckSection(heading: row.text("heading"),
                        bullets: row.array.map(\.string).filter { !$0.isEmpty },
                        notes: row.text("notes"),
                        image: DeckImage.parse(row["image"]),
                        imageUnavailable: row.text("image_unavailable"))
        }
    }

    /// The built artifact's id. Present only once the deck has actually been generated.
    var artifactID: String { artifact.text("artifact_id") }

    /// The `.pptx` twin's file name, present only when the build produced one.
    var pptxName: String { artifact.text("pptx_file") }

    /// Provider-embedded player, or nil when the title is not on the curated allowlist.
    var videoEmbedURL: URL? { MediaEmbed.url(artifact.text("embed_url")) }

    /// The provider's own page, for the one case the embed refuses: a title the provider
    /// will not play inside another app. Still allowlisted - never a bare link.
    var videoWatchURL: URL? { MediaEmbed.url(artifact.text("watch_url")) }

    var workedExampleBody: String { artifact.text("body") }

    /// What this block can actually show, if anything.
    ///
    /// Decided from the artifact rather than from the block kind on purpose: a deck whose
    /// sections failed to compose, or a video whose URL is not on the allowlist, has nothing
    /// to present, and a button that opens an empty sheet is worse than no button.
    var presentation: BlockPresentation? {
        if !deckSections.isEmpty { return .deck }
        if videoEmbedURL != nil || videoWatchURL != nil { return .video }
        if !workedExampleBody.isEmpty { return .reading }
        if artifact.text("mode") == "exploratory", !artifact.text("expression").isEmpty {
            return .simulation
        }
        return nil
    }
}

/// One slide of the bound deck.
///
/// `notes` is the authored body the bullets were drawn from. It is carried because it is the
/// source text a presenter would want, and it is hidden by default because a slide that
/// repeats its own bullets as prose is not a slide.
struct DeckSection {
    let heading: String
    let bullets: [String]
    let notes: String
    /// A real picture for this slide, when the harness cleared one. Absent whenever the
    /// media pipeline found nothing licence-cleared — the slide is still a slide.
    let image: DeckImage?
    /// Why there is no picture, when the harness looked and could not clear one. Shown
    /// quietly under the heading instead of an empty frame: a learner who sees "no
    /// picture" and no reason learns to distrust the deck, whereas one line naming the
    /// cause (offline, nothing cleared) is honest about what the harness could deliver.
    let imageUnavailable: String
}

/// The picture a deck slide carries: a content hash the backend serves, plus the credit
/// line that makes it publishable. The bytes route is bearer-protected, so the app fetches
/// through `APIClient` (see `ImageCache`); a miss renders as "unavailable", never a
/// substitute — the same rule the board's image nodes follow.
struct DeckImage {
    let sha256: String
    let alt: String
    let title: String
    let credit: String
    let licence: String
    let sourceURL: String

    static func parse(_ json: JSON) -> DeckImage? {
        let sha = json.text("sha256")
        guard sha.count == 64 else { return nil }
        return DeckImage(sha256: sha,
                         alt: json.text("alt"),
                         title: json.text("title"),
                         credit: json.text("credit"),
                         licence: json.text("licence"),
                         sourceURL: json.text("source_url"))
    }
}

/// How a block's artifact is shown, when it can be shown at all.
enum BlockPresentation {
    case deck, video, reading, simulation

    /// The verb on the row's button. Each one says what opening it will do, so the learner
    /// is not surprised by a player when they expected a page of text.
    var actionTitle: String {
        switch self {
        case .deck: return "Present"
        case .video: return "Watch"
        case .reading: return "Read"
        case .simulation: return "Explore"
        }
    }
}

/// Mirror of `run_to_dict()` plus the preview shape from `GET /api/v1/procedure/{id}`.
struct LessonProcedureState {
    var runID: String = ""
    var conceptID: String = ""
    var conceptTitle: String = ""
    var status: String = ""
    var budgetMinutes: Int = 0
    var totalMinutes: Int = 0
    var blocks: [ProcedureStep] = []
    var skipped: [(kind: String, label: String, reason: String)] = []
    var currentOrder: Int = 0
    var rationale: String = ""
    var error: String = ""

    var isRunning: Bool { !runID.isEmpty && status == "active" }
    var isComplete: Bool { status == "completed" }
    var doneCount: Int { blocks.filter(\.done).count }
    var progress: Double {
        blocks.isEmpty ? 0 : Double(doneCount) / Double(blocks.count)
    }
    var current: ProcedureStep? { blocks.first { $0.order == currentOrder } }

    init() {}

    /// The preview envelope: `{plan, evidence, active}`. An active run wins, because the
    /// lesson the learner is *in* is not a proposal.
    init(preview: JSON) {
        let active = preview["active"]
        let source = active.isNull ? preview["plan"] : active
        conceptID = source.text("concept_id")
        conceptTitle = source.text("concept_title", fallback: conceptID)
        runID = source.text("run_id")
        status = source.text("status", fallback: active.isNull ? "preview" : "")
        budgetMinutes = source["budget_minutes"].int
        totalMinutes = source["total_minutes"].int
        rationale = source.text("rationale")
        let done = Set(source["completed"].array.map { $0["order"].int })
        blocks = source["blocks"].array.map { row in
            ProcedureStep(order: row["order"].int,
                        kind: row.text("kind"),
                        label: row.text("label", fallback: row.text("kind")),
                        minutes: row["minutes"].int,
                        title: row.text("title"),
                        purpose: row.text("purpose"),
                        why: row.text("why"),
                        artifact: row["artifact"],
                        done: done.contains(row["order"].int),
                        answers: row["answers"])
        }
        currentOrder = blocks.first { !$0.done }?.order ?? 0
        skipped = source["skipped"].array.map {
            (kind: $0.text("kind"), label: $0.text("label", fallback: $0.text("kind")),
             reason: $0.text("reason"))
        }
    }

    /// A run response from `/start`, `/advance` or `/runs/{id}`.
    init(run: JSON) {
        conceptID = run.text("concept_id")
        runID = run.text("run_id")
        status = run.text("status")
        budgetMinutes = run["budget_minutes"].int
        totalMinutes = run["total_minutes"].int
        rationale = run.text("rationale")
        // The server resolves the authored title; deriving one from the id is only the
        // fallback, because "Fraction Equivalence" is not what the course calls the lesson.
        let given = run.text("concept_title")
        conceptTitle = given.isEmpty
            ? conceptID.replacingOccurrences(of: "_", with: " ").capitalized
            : given
        let done = Set(run["completed"].array.map { $0["order"].int })
        blocks = run["blocks"].array.map { row in
            ProcedureStep(order: row["order"].int,
                        kind: row.text("kind"),
                        label: row.text("label", fallback: row.text("kind")),
                        minutes: row["minutes"].int,
                        title: row.text("title"),
                        purpose: row.text("purpose"),
                        why: row.text("why"),
                        artifact: row["artifact"],
                        done: done.contains(row["order"].int),
                        answers: row["answers"])
        }
        currentOrder = blocks.first { !$0.done }?.order ?? 0
        skipped = run["skipped"].array.map {
            (kind: $0.text("kind"), label: $0.text("label", fallback: $0.text("kind")),
             reason: $0.text("reason"))
        }
    }
}

@MainActor
final class ProcedureQuestionStore: ObservableObject {
    @Published private(set) var question: JSON = .null
    @Published private(set) var attempt: JSON = .null
    @Published private(set) var loading = false
    @Published private(set) var submitting = false
    @Published private(set) var error = ""
    @Published private(set) var reason = ""
    @Published private(set) var frozen = false
    @Published private(set) var elapsed: Double = 0
    @Published var optionID = ""
    @Published var answerText = ""
    @Published var explanation = ""
    @Published var confidence = 0.5
    private var runID = ""
    private var order = 0
    private var version = UUID()
    private var eventID = UUID().uuidString
    private var payload: [String: Any]?
    private var lastTick = ProcessInfo.processInfo.systemUptime

    func isBound(runID: String, order: Int) -> Bool {
        self.runID == runID && self.order == order
    }

    func reset(runID: String = "", order: Int = 0) {
        version = UUID()
        self.runID = runID; self.order = order
        question = .null; attempt = .null; error = ""; reason = ""
        loading = false; submitting = false; frozen = false; payload = nil
        optionID = ""; answerText = ""; explanation = ""; confidence = 0.5; elapsed = 0
        eventID = UUID().uuidString
        lastTick = ProcessInfo.processInfo.systemUptime
    }

    func load(store: AppStore, runID: String, order: Int) async {
        guard store.authenticated, store.lessonProcedure.isRunning,
              store.lessonProcedure.runID == runID,
              store.lessonProcedure.currentOrder == order else { return }
        if !isBound(runID: runID, order: order) { reset(runID: runID, order: order) }
        guard !loading, !submitting, !frozen || !attempt.isNull else { return }
        let generation = version, epoch = store.epoch
        loading = true; error = ""
        defer { if version == generation { loading = false } }
        do {
            try await store.refreshLessonProcedure(runID: runID)
            guard version == generation, store.epoch == epoch, store.authenticated,
                  store.lessonProcedure.isRunning, store.lessonProcedure.runID == runID,
                  store.lessonProcedure.currentOrder == order else { return }
            let result = try await store.api.json("/procedure/runs/" + runID + "/next-item",
                                                 query: [URLQueryItem(name: "order", value: String(order))])
            guard version == generation, store.epoch == epoch, store.authenticated,
                  store.lessonProcedure.runID == runID,
                  store.lessonProcedure.currentOrder == order, !Task.isCancelled else { return }
            guard result.text("run_id") == runID, result["block_order"].int == order else {
                throw AppFailure(message: "The server returned a different lesson block. No question was opened; refresh the lesson and retry.", status: nil)
            }
            let next = result["question"]
            if !next.isNull, next.text("id").isEmpty || next.text("receipt").isEmpty || next.text("prompt").isEmpty {
                throw AppFailure(message: "The scheduled question is missing its prompt or signed receipt. Retry loading, or skip this block.", status: nil)
            }
            question = next
            attempt = .null; optionID = ""; answerText = ""; explanation = ""; confidence = 0.5
            frozen = false; payload = nil; eventID = UUID().uuidString; elapsed = 0
            lastTick = ProcessInfo.processInfo.systemUptime
            reason = result.text("reason", fallback: next.isNull
                                 ? (result["progress"]["complete"].bool ? "All scheduled answers are recorded. You can mark this block Done." : "No scheduled question could be served. Retry loading, or skip this block.") : "")
            try await store.refreshLessonProcedure(runID: runID)
        } catch {
            guard version == generation, store.epoch == epoch else { return }
            self.error = "The scheduled question could not be loaded: " + error.localizedDescription
            store.record(error)
        }
    }

    func tick() {
        let now = ProcessInfo.processInfo.systemUptime
        defer { lastTick = now }
        guard NSApp.isActive, !question.isNull, attempt.isNull, !frozen, !loading, !submitting else { return }
        elapsed = min(7200, elapsed + max(0, min(2, now - lastTick)))
    }

    func submit(store: AppStore) async {
        guard store.authenticated, store.lessonProcedure.isRunning,
              store.lessonProcedure.runID == runID, store.lessonProcedure.currentOrder == order,
              !loading, !submitting, attempt.isNull, !question.isNull else { return }
        if payload == nil {
            let text = answerText.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !optionID.isEmpty || !text.isEmpty else { return }
            tick()
            let why = explanation.trimmingCharacters(in: .whitespacesAndNewlines)
            payload = ["question_id": question.text("id"), "receipt": question.text("receipt"),
                       "client_event_id": eventID, "elapsed_seconds": elapsed, "confidence": confidence]
            if question["options"].array.isEmpty { payload?["answer_text"] = text }
            else { payload?["option_id"] = optionID }
            if !why.isEmpty { payload?["self_explanation"] = why; payload?["reasoning"] = why }
        }
        let generation = version, epoch = store.epoch, boundRun = runID
        frozen = true; submitting = true; error = ""
        store.noteLearnerAction()
        defer { if version == generation { submitting = false } }
        do {
            let result = try await store.api.json("/attempts", method: "POST", body: payload)
            guard version == generation, store.epoch == epoch, store.authenticated,
                  store.lessonProcedure.runID == boundRun else { return }
            guard !result.text("id").isEmpty else {
                throw AppFailure(message: "The server did not return an attempt confirmation. Retry the same submission to check whether it was recorded.", status: nil)
            }
            attempt = result
            try await store.refreshLessonProcedure(runID: boundRun)
            await store.refresh()
            await store.load("/reviews") { store.reviews = $0 }
        } catch {
            guard version == generation, store.epoch == epoch else { return }
            if attempt.isNull, let status = (error as? AppFailure)?.status {
                if [400, 422].contains(status) { payload = nil; frozen = false }
                if status == 410 {
                    payload = nil; frozen = false; question = .null
                    reason = "The signed question expired or was withdrawn. Reload this block for a new receipt, or skip it."
                }
            }
            self.error = attempt.isNull
                ? "The answer was not confirmed: " + error.localizedDescription
                : "Your answer was scored, but live lesson progress could not be refreshed: " + error.localizedDescription
            store.record(error)
        }
    }
}

struct ProcedureQuestionView: View {
    @EnvironmentObject var store: AppStore
    @ObservedObject var questions: ProcedureQuestionStore
    let runID: String
    let order: Int

    private var current: ProcedureStep? {
        guard store.authenticated, store.lessonProcedure.isRunning,
              store.lessonProcedure.runID == runID,
              store.lessonProcedure.currentOrder == order else { return nil }
        return store.lessonProcedure.current
    }
    private var canSubmit: Bool {
        !questions.optionID.isEmpty || !questions.answerText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let current, questions.isBound(runID: runID, order: order) {
                    Text("\(current.answers["answered"].int) of \(current.answers["total"].int) scheduled questions answered")
                        .font(.system(size: 12)).foregroundStyle(Palette.secondary)
                        .accessibilityIdentifier("procedure.question.progress")
                    if questions.loading { ProgressView("Loading this block's question…") }
                    else if !questions.question.isNull { answerForm }
                    if !questions.reason.isEmpty {
                        Text(questions.reason).font(.system(size: 12))
                            .accessibilityIdentifier("procedure.question.reason")
                    }
                    if !questions.attempt.isNull { feedback }
                    if !questions.error.isEmpty {
                        Text(questions.error + (questions.frozen && questions.attempt.isNull
                             ? "\nRetry sends the same frozen answer and event ID; it cannot create a second attempt." : ""))
                            .font(.system(size: 12)).foregroundStyle(.red).textSelection(.enabled)
                            .accessibilityIdentifier("procedure.question.error")
                    }
                    HStack(spacing: 10) {
                        if !questions.question.isNull, questions.attempt.isNull {
                            Button(questions.frozen ? "Retry submission" : "Submit answer") {
                                store.run { await questions.submit(store: store) }
                            }
                            .buttonStyle(LuminfestButtonStyle(primary: true))
                            .disabled(!canSubmit || questions.loading || questions.submitting || store.lessonProcedureBusy)
                            .accessibilityIdentifier("procedure.question.submit")
                        } else if !current.answersComplete || !questions.error.isEmpty {
                            Button(questions.attempt.isNull ? "Retry loading question" : "Next scheduled question / refresh") {
                                store.run { await questions.load(store: store, runID: runID, order: order) }
                            }
                            .buttonStyle(LuminfestButtonStyle(primary: false))
                            .disabled(questions.loading || questions.submitting || store.lessonProcedureBusy)
                            .accessibilityIdentifier("procedure.question.next")
                        }
                        if questions.submitting { ProgressView("Scoring answer…").controlSize(.small) }
                    }
                } else {
                    Text("This is no longer the current lesson block. Close this sheet and open the current activity; no future question will be shown.")
                        .font(.system(size: 12)).accessibilityIdentifier("procedure.question.not-current")
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(18)
        }
        .task {
            while !Task.isCancelled {
                if current != nil { questions.tick() }
                do { try await Task.sleep(nanoseconds: 1_000_000_000) } catch { break }
            }
        }
    }

    private var answerForm: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(questions.question.text("prompt"))
                .font(.system(size: 21, weight: .medium)).lineSpacing(5)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("procedure.question.prompt")
            if questions.question["options"].array.isEmpty {
                TextField("Your written or numeric answer", text: $questions.answerText, axis: .vertical)
                    .lineLimit(2...5).textFieldStyle(.roundedBorder)
                    .disabled(questions.frozen || !questions.attempt.isNull)
                    .accessibilityIdentifier("procedure.question.answer")
            } else {
                ForEach(questions.question["options"].array, id: \.["id"].string) { option in
                    Button { questions.optionID = option.text("id") } label: {
                        HStack(alignment: .top, spacing: 10) {
                            Image(systemName: questions.optionID == option.text("id") ? "largecircle.fill.circle" : "circle")
                            Text(option.text("text")).multilineTextAlignment(.leading)
                            Spacer()
                        }
                        .padding(12).frame(maxWidth: .infinity, alignment: .leading)
                        .background(questions.optionID == option.text("id") ? Palette.sage : Palette.surface,
                                    in: RoundedRectangle(cornerRadius: 10))
                    }
                    .buttonStyle(.plain).disabled(questions.frozen || !questions.attempt.isNull)
                    .accessibilityIdentifier("procedure.question.option." + option.text("id"))
                    .accessibilityAddTraits(questions.optionID == option.text("id") ? .isSelected : [])
                }
            }
            Text("Explain why your answer works (required when the lesson's self-explanation gate is enabled).")
                .font(.system(size: 11)).foregroundStyle(Palette.secondary)
            TextEditor(text: $questions.explanation).font(.system(size: 12))
                .frame(height: 80).padding(8).background(Palette.surface, in: RoundedRectangle(cornerRadius: 10))
                .disabled(questions.frozen || !questions.attempt.isNull)
                .accessibilityIdentifier("procedure.question.self-explanation")
            HStack {
                Text("Confidence").font(.system(size: 11))
                Slider(value: $questions.confidence, in: 0...1).frame(maxWidth: 220)
                    .disabled(questions.frozen || !questions.attempt.isNull)
                    .accessibilityIdentifier("procedure.question.confidence")
                Text("\(Int(questions.confidence * 100))% · \(Int(questions.elapsed))s active")
                    .font(.system(size: 11, design: .monospaced))
            }
        }
    }

    private var feedback: some View {
        let result = questions.attempt
        return Card(color: result["correct"].bool ? Palette.sage : Palette.peach, padding: 16) {
            VStack(alignment: .leading, spacing: 9) {
                Text(result["correct"].isNull ? "Answer recorded; feedback withheld." : (result["correct"].bool ? "Correct" : "Not quite — review the explanation"))
                    .font(.system(size: 16, weight: .semibold))
                    .accessibilityIdentifier("procedure.question.correctness")
                if !result["correct_answer"].isNull { Text("Correct answer: " + result.text("correct_answer")) }
                Text(result.text("explanation")).lineSpacing(4).textSelection(.enabled)
                    .accessibilityIdentifier("procedure.question.explanation")
                if !result["diagnosis"].isNull {
                    Divider()
                    Text(result["diagnosis"].text("category").replacingOccurrences(of: "_", with: " ").capitalized)
                        .fontWeight(.semibold).accessibilityIdentifier("procedure.question.diagnosis")
                    Text(result["diagnosis"].text("reason"))
                    Text(result["diagnosis"].text("next_action"))
                        .accessibilityIdentifier("procedure.question.next-action")
                }
                if !result["mastery"].isNull {
                    Text("Estimated mastery: " + percent(result["mastery"]))
                        .accessibilityIdentifier("procedure.question.mastery")
                }
                if !result["review_at"].isNull {
                    Text("Review: " + friendlyDate(result.text("review_at")))
                        .accessibilityIdentifier("procedure.question.review")
                }
            }.font(.system(size: 12))
        }
        .accessibilityIdentifier("procedure.question.feedback")
    }
}

/// The run-of-show card: what this lesson will do, in order, and which block is now.
struct LessonProcedureCard: View {
    @EnvironmentObject var store: AppStore
    @State private var showRefusals = false
    @State private var showWhy = false
    /// The block whose artifact is open. Held as the step itself, not an order number, so
    /// the sheet shows what was on screen when the learner clicked rather than whatever the
    /// run has moved on to since.
    @State private var presenting: ProcedureStep?
    @State private var presentingRunID = ""
    @StateObject private var questions = ProcedureQuestionStore()

    private var state: LessonProcedureState { store.lessonProcedure }

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: 16) {
                HStack(alignment: .firstTextBaseline) {
                    Eyebrow(text: "TODAY'S LESSON")
                    Spacer()
                    if state.totalMinutes > 0 {
                        Tag(text: "\(state.totalMinutes) OF \(state.budgetMinutes) MIN",
                            color: Palette.accentTeal.soft)
                    }
                    if state.isComplete {
                        Tag(text: "COMPLETE", color: Palette.accentMoss.soft)
                    }
                }
                SectionHeading(
                    title: state.conceptTitle.isEmpty ? "Your lesson" : state.conceptTitle,
                    detail: state.blocks.isEmpty ? "" : "\(state.doneCount) OF \(state.blocks.count) DONE")

                if !state.error.isEmpty {
                    Text(state.error)
                        .font(.system(size: 11))
                        .foregroundStyle(Palette.secondary)
                        .lineSpacing(3)
                }
                if state.blocks.isEmpty {
                    EmptyState(icon: "list.bullet.rectangle",
                               title: "No lesson compiled yet",
                               message: "Pick a concept and the harness will compile a lesson from your own evidence and the material this course actually holds.")
                        .frame(maxHeight: 220)
                } else {
                    if state.totalMinutes > 0 { ProgressView(value: state.progress)
                        .tint(Palette.forest) }
                    VStack(spacing: 8) {
                        ForEach(state.blocks) { block in
                            row(block)
                        }
                    }
                    controls
                    if state.isRunning, let current = state.current, !current.completionReason.isEmpty {
                        Text(current.completionReason).font(.system(size: 11)).foregroundStyle(Palette.secondary)
                            .accessibilityIdentifier("procedure.done.reason")
                    }
                    if !state.skipped.isEmpty { refusals }
                    Text("Advancing a block records that you did the activity. It does not raise your mastery — only answers and simulations do.")
                        .font(.system(size: 10))
                        .foregroundStyle(Palette.tertiary)
                        .lineSpacing(3)
                }
            }
        }
        .sheet(item: $presenting) { step in
            LessonBlockSheet(step: step, conceptTitle: state.conceptTitle,
                             runID: presentingRunID, questions: questions)
                .environmentObject(store)
        }
        .task(id: "\(store.epoch):\(state.runID):\(state.currentOrder):\(state.isRunning)") {
            guard store.authenticated, state.isRunning, let current = state.current, current.isScored else {
                questions.reset()
                return
            }
            await questions.load(store: store, runID: state.runID, order: current.order)
        }
    }

    // ---------------------------------------------------------------- one row

    private func row(_ block: ProcedureStep) -> some View {
        let isNow = block.order == state.currentOrder && !block.done
        return HStack(alignment: .top, spacing: 12) {
            ZStack {
                Circle()
                    .fill(block.done ? Palette.forest.opacity(0.16)
                          : (isNow ? Palette.accentTeal.soft : Palette.surfaceSubtle))
                    .frame(width: 26, height: 26)
                if block.done {
                    Image(systemName: "checkmark")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(Palette.forest)
                } else {
                    Text("\(block.order)")
                        .font(.system(size: 11, weight: .semibold, design: .rounded))
                        .foregroundStyle(isNow ? Palette.accentTeal.deep : Palette.tertiary)
                }
            }
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(block.title.isEmpty ? block.label : block.title)
                        .font(.system(size: 12, weight: isNow ? .semibold : .medium))
                        .foregroundStyle(block.done ? Palette.secondary : Palette.ink)
                        .lineLimit(1)
                    Text("\(block.minutes) min")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(Palette.tertiary)
                }
                Text(block.purpose)
                    .font(.system(size: 10))
                    .foregroundStyle(Palette.secondary)
                    .lineSpacing(2)
                    .fixedSize(horizontal: false, vertical: true)
                if isNow {
                    Text(block.why)
                        .font(.system(size: 10))
                        .foregroundStyle(Palette.tertiary)
                        .lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 2)
                }
            }
            Spacer(minLength: 4)
            if block.isScored, isNow, state.isRunning {
                Button("Answer questions") { presentingRunID = state.runID; presenting = block }
                    .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
                    .accessibilityIdentifier("procedure.questions.open.\(block.order)")
            } else if let presentation = block.presentation, isNow || block.done {
                // A finished block stays openable: the deck a learner read on Monday is
                // still the right thing to re-read before Thursday's practice, and the
                // procedure does not have to re-schedule it to make it reachable.
                Button(isNow ? presentation.actionTitle : "Review") { presentingRunID = state.runID; presenting = block }
                    .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
            } else if isNow, !block.playgroundSlug.isEmpty {
                Button("Open") { store.openPlayground(slug: block.playgroundSlug) }
                    .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
            }
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 8)
        .background(isNow ? Palette.accentTeal.soft.opacity(0.35) : Color.clear,
                    in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    // -------------------------------------------------------------- controls

    private var controls: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 10) { buttons }
            VStack(alignment: .leading, spacing: 10) { buttons }
        }
    }

    @ViewBuilder
    private var buttons: some View {
        if !state.isRunning && !state.isComplete {
            Button("Start this lesson") {
                store.run { await store.startLessonProcedure(conceptID: store.lessonConceptID) }
            }
            .buttonStyle(LuminfestButtonStyle(primary: true))
            .disabled(store.lessonProcedureBusy)
        }
        if let current = state.current {
            Button("Done: \(current.label.lowercased())") {
                store.run { await store.advanceLessonProcedure(order: current.order, outcome: "done") }
            }
            .buttonStyle(LuminfestButtonStyle(primary: state.isRunning))
            .disabled(!state.isRunning || store.lessonProcedureBusy || questions.submitting ||
                      (current.isScored && !current.answersComplete))
            .accessibilityIdentifier("procedure.done")
            Button("Skip it") {
                store.run { await store.advanceLessonProcedure(order: current.order, outcome: "skipped") }
            }
            .buttonStyle(LuminfestButtonStyle(primary: false))
            .disabled(!state.isRunning || store.lessonProcedureBusy || questions.submitting)
            .accessibilityIdentifier("procedure.skip")
        }
        if state.isComplete {
            Button("Plan another lesson") {
                store.run { await store.startLessonProcedure(conceptID: store.lessonConceptID) }
            }
            .buttonStyle(LuminfestButtonStyle(primary: true))
            .disabled(store.lessonProcedureBusy)
        }
        Button(showWhy ? "Hide the reasoning" : "Why this sequence?") {
            showWhy.toggle()
        }
        .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
        if showWhy, !state.rationale.isEmpty {
            Text(state.rationale)
                .font(.system(size: 10))
                .foregroundStyle(Palette.tertiary)
                .lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // ------------------------------------------------------------- refusals

    private var refusals: some View {
        VStack(alignment: .leading, spacing: 6) {
            Button {
                showRefusals.toggle()
            } label: {
                Label("What this lesson leaves out (\(state.skipped.count))",
                      systemImage: showRefusals ? "chevron.down" : "chevron.right")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(Palette.forest)
            }.buttonStyle(.plain)
            if showRefusals {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(Array(state.skipped.enumerated()), id: \.offset) { _, item in
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(item.label)
                                .font(.system(size: 10, weight: .semibold, design: .monospaced))
                                .frame(width: 96, alignment: .leading)
                                .foregroundStyle(Palette.secondary)
                            Text(item.reason)
                                .font(.system(size: 10))
                                .foregroundStyle(Palette.tertiary)
                                .lineSpacing(2)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
                .padding(10)
                .background(Palette.sage.opacity(0.35),
                            in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
        }
    }
}

// MARK: - The artifact a block is bound to

/// One activity's artifact, opened from the run of show.
///
/// The card can only report *that* a block happened; this is where the learner does the
/// looking, watching, exploring or reading. It renders whatever the artifact is - the deck's
/// own slides, the curated video in the app's own player, the exploratory interactive the
/// engine draws, or the worked example's text - so a block that names a specific artifact
/// always has a way to open exactly that artifact.
///
/// Two decisions are visible here:
///
///  * **Nothing is fetched to show a deck.** The slides are in the block, so they are drawn
///    natively. The materialised HTML and the `.pptx` twin are real and downloadable, but
///    both sit behind the bearer token, and a web view or a browser pointed at them has no
///    session to send. The `.pptx` is therefore fetched *through the API client* and written
///    to a file the learner chooses, which is the only version of that offer the app can
///    actually keep.
///  * **Advancing is available but never implied.** "Done" is offered only while this block
///    is the current one, because advancing a block out of order is a 409 on the server. A
///    finished block opens in review mode, with no button that pretends to move the lesson.
///
/// An *exploratory* interactive is the one artifact the app draws from the engine rather
/// than from the block: `SimulationLab` holds no formula of its own and re-asks the backend
/// on every slider move, so presenting it is presenting the harness's artifact. It reports
/// nothing back, which is why the compiler prices such a lesson with an extra practice item.
/// The shared slide cursor: the tutor moves the deck, the learner moves it back.
///
/// The deck is rendered from the run's blocks, so the server cannot see which slide is on
/// screen. This is the one value both sides write. A `deck_control` tool call moves it -
/// the sheet advances while the tutor is still talking - and the learner's own Back/Next
/// reports it, so the tutor's "next" starts from what is actually showing rather than from
/// wherever the server last guessed.
///
/// Polling rather than a push channel is deliberate: it is the same 2.5s pattern the board
/// uses, it survives the turn ending, and it costs one tiny GET per sheet. A push would
/// have to be wired into the SSE turn stream, which only exists while a reply is streaming
/// - exactly the wrong lifetime for a deck the learner keeps open afterwards.
@MainActor
final class DeckCursorStore: ObservableObject {
    @Published private(set) var slide = 0
    @Published private(set) var count = 0

    private var api: APIClient?
    private var conceptID = ""
    private var task: Task<Void, Never>?
    /// The last value the server reported. A poll that echoes a value we already applied
    /// must not fight a learner who is mid-tap, so only a *change* on the wire moves us.
    private var lastServerSlide = -1

    func bind(api: APIClient, conceptID: String) {
        self.api = api
        self.conceptID = conceptID
    }

    func start() {
        task?.cancel()
        guard api != nil, !conceptID.isEmpty else { return }
        task = Task { [weak self] in
            while !Task.isCancelled {
                await self?.poll()
                try? await Task.sleep(nanoseconds: 1_500_000_000)
            }
        }
    }

    func stop() {
        task?.cancel()
        task = nil
    }

    private func poll() async {
        guard let api, !conceptID.isEmpty else { return }
        guard let value = try? await api.json("/procedure/" + conceptID + "/deck-cursor") else {
            return
        }
        count = value["count"].int
        let remote = value["slide"].int
        guard remote != lastServerSlide else { return }
        lastServerSlide = remote
        if remote != slide { slide = remote }
    }

    /// The learner moved the deck. Adopt it at once, then tell the server so the tutor's
    /// next instruction is relative to this slide.
    func moved(to index: Int) {
        slide = max(0, index)
        guard let api, !conceptID.isEmpty else { return }
        let target = slide
        Task {
            _ = try? await api.json("/procedure/" + conceptID + "/deck-cursor",
                                    method: "PUT", body: ["slide": target])
        }
    }
}

struct LessonBlockSheet: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss
    let step: ProcedureStep
    let conceptTitle: String
    let runID: String
    @ObservedObject var questions: ProcedureQuestionStore

    @StateObject private var deckCursor = DeckCursorStore()
    @State private var showNotes = false
    @State private var saving = false

    /// The concept this deck belongs to. The block carries the authored lesson id; the
    /// store's own selection is the fallback for a run compiled before that field existed.
    private var deckConceptID: String {
        let bound = step.artifact.text("concept_id")
        return bound.isEmpty ? store.lessonConceptID : bound
    }

    private var isCurrent: Bool {
        store.lessonProcedure.isRunning && store.lessonProcedure.runID == runID &&
            store.lessonProcedure.currentOrder == step.order
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            header
            content
            Divider()
            footer
        }
        .padding(26)
        .frame(minWidth: 720, minHeight: 560)
        .background(Palette.background)
        .onAppear {
            // Only a deck has a cursor worth following. Binding for every block would
            // poll a deck that is not on screen and let the tutor's "next" land nowhere.
            guard step.presentation == .deck else { return }
            deckCursor.bind(api: store.api, conceptID: deckConceptID)
            deckCursor.start()
        }
        .onDisappear { deckCursor.stop() }
    }

    // ---------------------------------------------------------------- header

    private var header: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 5) {
                Eyebrow(text: "\(step.label.uppercased()) · \(step.minutes) MIN")
                Text(step.title.isEmpty ? step.label : step.title)
                    .font(.system(size: 23, weight: .semibold))
                    .tracking(-0.5)
                if !conceptTitle.isEmpty {
                    Text(conceptTitle)
                        .font(.system(size: 11))
                        .foregroundStyle(Palette.secondary)
                }
            }
            Spacer()
            if step.presentation == .deck, !step.pptxName.isEmpty {
                Button { saveDeck() } label: {
                    Label(saving ? "Saving…" : "Save .pptx", systemImage: "square.and.arrow.down")
                }
                .buttonStyle(LuminfestButtonStyle(primary: false))
                .disabled(saving)
            }
            Button("Close") { dismiss() }.keyboardShortcut(.cancelAction)
        }
    }

    // ---------------------------------------------------------------- content

    @ViewBuilder
    private var content: some View {
        if step.isScored {
            ProcedureQuestionView(questions: questions, runID: runID, order: step.order)
        } else {
            switch step.presentation {
            case .deck: deck
            case .video: video
            case .reading: reading
            case .simulation: exploration
            case nil: unavailable
            }
        }
    }

    /// The exploratory interactive, drawn by the same renderer the lesson uses.
    ///
    /// `SimulationLab` re-asks the backend engine for this concept's figure on every slider
    /// move and holds no formula of its own, so this is the harness's interactive and not a
    /// re-implementation of it. It reports nothing back, which is exactly why the compiler
    /// priced this lesson with an extra practice item: the harness still sees nothing inside
    /// this block, and the schedule says so.
    private var exploration: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if !step.artifact.text("prompt").isEmpty {
                    Text(step.artifact.text("prompt"))
                        .font(.system(size: 12))
                        .foregroundStyle(Palette.ink)
                        .lineSpacing(4)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(14)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Palette.sage.opacity(0.45),
                                    in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
                SimulationLab(conceptID: simulationConceptID, store: store)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    /// The concept the interactive belongs to. The artifact carries it, so the lab asks the
    /// engine for the concept the procedure bound rather than for whatever the learner is
    /// looking at on the Today page.
    private var simulationConceptID: String {
        let bound = step.artifact.text("concept_id")
        return bound.isEmpty ? store.lessonConceptID : bound
    }

    /// The deck, one slide at a time.
    ///
    /// Arrow keys move between slides, the same gesture the narrated deck uses, so the two
    /// decks in the app behave alike. The slide is a card rather than a full-bleed page
    /// because it sits inside a sheet that also has to say what the activity is.
    private var deck: some View {
        let sections = step.deckSections
        let index = min(max(deckCursor.slide, 0), max(sections.count - 1, 0))
        return VStack(alignment: .leading, spacing: 12) {
            if sections.indices.contains(index) {
                let section = sections[index]
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        Text(section.heading)
                            .font(.system(size: 26, weight: .semibold))
                            .tracking(-0.6)
                            .fixedSize(horizontal: false, vertical: true)
                        if let image = section.image {
                            // A real photograph for the concept, fetched through the
                            // authenticated client. Without this every deck was a
                            // mock-up of headings and bullets.
                            DeckImageView(image: image, api: store.api)
                        } else if !section.imageUnavailable.isEmpty {
                            // No picture, and the server said why. A one-line note is
                            // better than a blank frame the learner cannot account for.
                            Label(section.imageUnavailable, systemImage: "photo")
                                .font(.system(size: 10))
                                .foregroundStyle(Palette.tertiary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        VStack(alignment: .leading, spacing: 9) {
                            ForEach(Array(section.bullets.enumerated()), id: \.offset) { _, bullet in
                                Label(bullet, systemImage: "circle.fill")
                                    .labelStyle(TinyDotLabelStyle())
                                    .font(.system(size: 14))
                                    .foregroundStyle(Palette.ink)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                        if !section.notes.isEmpty {
                            // The authored body the bullets were drawn from. Collapsed by
                            // default: a slide that reprints its own bullets as prose is a
                            // worse slide, but the source text is what a presenter reads.
                            DisclosureGroup(isExpanded: $showNotes) {
                                Text(section.notes)
                                    .font(.system(size: 11))
                                    .lineSpacing(4)
                                    .foregroundStyle(Palette.secondary)
                                    .fixedSize(horizontal: false, vertical: true)
                                    .padding(.top, 4)
                            } label: {
                                Text("Source text")
                                    .font(.system(size: 10, weight: .medium))
                                    .foregroundStyle(Palette.forest)
                            }
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(24)
                    .background(Palette.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .strokeBorder(Palette.line))
                }
            }
            HStack(spacing: 12) {
                Button("Back") { deckCursor.moved(to: max(0, index - 1)) }
                    .keyboardShortcut(.leftArrow, modifiers: [])
                    .disabled(index == 0)
                Spacer()
                Text("Slide \(index + 1) of \(sections.count)")
                    .font(.system(size: 11))
                    .foregroundStyle(Palette.secondary)
                Spacer()
                Button("Next") { deckCursor.moved(to: min(sections.count - 1, index + 1)) }
                    .keyboardShortcut(.rightArrow, modifiers: [])
                    .disabled(index >= sections.count - 1)
            }
        }
    }

    /// A deck slide's picture, loaded through the authenticated image cache.
///
/// The fetch is asynchronous and the result is held in state, so a slow or missing asset
/// leaves the slide readable while it loads and degrades to a note if it never arrives —
/// the picture is an addition to the slide, never a requirement for it.
struct DeckImageView: View {
    let image: DeckImage
    let api: APIClient
    @State private var loaded: NSImage?
    @State private var failed = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Group {
                if let loaded {
                    Image(nsImage: loaded)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                } else if failed {
                    EmptyState(icon: "photo",
                               title: "Picture unavailable",
                               message: "The harness cleared this image but its bytes are not in the local cache any more. The slide stands on its own.")
                        .frame(maxHeight: 180)
                } else {
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(Palette.surface)
                        .frame(height: 180)
                        .overlay(ProgressView().controlSize(.small))
                }
            }
            .frame(maxWidth: .infinity)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(Palette.line))
            .accessibilityLabel(image.alt.isEmpty ? image.title : image.alt)
            if !image.credit.isEmpty {
                // A credit line under a figure is what makes a scraped picture
                // publishable; hiding it would make the image unusable.
                Text(image.credit)
                    .font(.system(size: 9))
                    .foregroundStyle(Palette.tertiary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .task(id: image.sha256) {
            // ImageCache blocks its caller while it fetches, so the wait happens
            // off the main actor; a bound client is what makes the fetch possible.
            ImageCache.shared.bind(api: api)
            let data: Data? = await Task.detached(priority: .utility) {
                ImageCache.shared.data(sha: image.sha256)
            }.value
            if let data, let picture = NSImage(data: data) {
                loaded = picture
            } else {
                failed = true
            }
        }
    }
}

/// The curated video, played by the provider in the app's own web view.
    ///
    /// `MediaEmbed` has already refused anything that is not an allowlisted provider over
    /// HTTPS, so an empty embed here means "the provider will not embed this title", not
    /// "the harness forgot the link" - and the sheet says which.
    private var video: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let url = step.videoEmbedURL {
                EmbeddedLessonWebView(url: url)
                    .frame(minHeight: 380)
                    .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Palette.line))
                    .clipShape(RoundedRectangle(cornerRadius: 12))
            } else {
                EmptyState(icon: "play.slash",
                           title: "This title does not play in place",
                           message: "The provider does not allow an embedded player for it. Open it on the provider instead — the link is the curated one, not a search result.")
                    .frame(maxHeight: 300)
            }
            HStack(spacing: 10) {
                if !step.artifact.text("channel").isEmpty {
                    Text(step.artifact.text("channel"))
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(Palette.secondary)
                }
                let licence = step.artifact.text("licence_class")
                if !licence.isEmpty {
                    Tag(text: licence.uppercased().replacingOccurrences(of: "_", with: " "),
                        color: Palette.lavender)
                }
                Spacer()
                if let watch = step.videoWatchURL {
                    Button { NSWorkspace.shared.open(watch) } label: {
                        Label("Open on the provider", systemImage: "arrow.up.right.square")
                    }
                    .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
                }
            }
            if !step.artifact.text("attribution").isEmpty {
                Text(step.artifact.text("attribution"))
                    .font(.system(size: 10))
                    .foregroundStyle(Palette.tertiary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// The authored worked example, as text.
    private var reading: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                Text(step.workedExampleBody)
                    .font(.system(size: 13))
                    .lineSpacing(5)
                    .foregroundStyle(Palette.ink)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
                Text("This is the course's own worked example. The tutor can stop it at the step your recorded errors point at.")
                    .font(.system(size: 10))
                    .foregroundStyle(Palette.tertiary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(20)
            .background(Palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(Palette.line))
        }
    }

    private var unavailable: some View {
        EmptyState(icon: "questionmark.square.dashed",
                   title: "Nothing to open",
                   message: "This activity happens in the conversation: the tutor runs it, and your answer is what it records. There is no artifact behind it.")
            .frame(maxHeight: 260)
    }

    // ---------------------------------------------------------------- footer

    private var footer: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Text(!store.lessonProcedure.error.isEmpty ? store.lessonProcedure.error : (isCurrent
                 ? (step.isScored && !(store.lessonProcedure.current?.answersComplete ?? false)
                    ? store.lessonProcedure.current?.completionReason ?? "Answer all scheduled questions before Done. Skip remains available."
                    : "Advancing records that you did the activity. It does not raise your mastery.")
                 : "This block is not the current one, so it opens for review only."))
                .font(.system(size: 10))
                .foregroundStyle(Palette.tertiary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 8)
            if isCurrent {
                Button("Done: \(step.label.lowercased())") { finish() }
                    .buttonStyle(LuminfestButtonStyle(primary: true))
                    .disabled(store.lessonProcedureBusy || questions.submitting ||
                              (step.isScored && !(store.lessonProcedure.current?.answersComplete ?? false)))
                    .accessibilityIdentifier("procedure.sheet.done")
                Button("Skip it") { finish(outcome: "skipped") }
                    .buttonStyle(LuminfestButtonStyle(primary: false))
                    .disabled(store.lessonProcedureBusy || questions.submitting)
                    .accessibilityIdentifier("procedure.sheet.skip")
            }
        }
    }

    /// Advance, and close only if the run actually moved.
    ///
    /// `advanceLessonProcedure` records a failure rather than throwing it, so success is
    /// read from the state it left behind. Closing unconditionally would hide a rejected
    /// advance behind a dismissed sheet, which is exactly the case the learner needs to see.
    private func finish(outcome: String = "done") {
        guard isCurrent else { return }
        let before = store.lessonProcedure.doneCount
        store.run {
            await store.advanceLessonProcedure(order: step.order, outcome: outcome)
            if store.lessonProcedure.doneCount > before { dismiss() }
        }
    }

    /// Fetch the `.pptx` twin through the authenticated client, then save it.
    private func saveDeck() {
        saving = true
        let name = (step.title.isEmpty ? conceptTitle : step.title)
            .replacingOccurrences(of: "/", with: "-")
        let suggested = (name.isEmpty ? "lesson deck" : name) + ".pptx"
        store.run {
            await store.saveLessonDeckPPTX(artifactID: step.artifactID,
                                           fileName: step.pptxName,
                                           suggestedName: suggested)
            saving = false
        }
    }
}
