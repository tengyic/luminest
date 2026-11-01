import SwiftUI

// The 9-MOVES decision surface. The harness loop (backend harness/loop.py) scores every
// move against gathered evidence and records the run; this view renders the *decision*
// the way the backend reports it: the chosen move, its reason, the runner-up it beat,
// and the evidence scope. Nothing here is inferred client-side - if the plan endpoint
// did not answer, the card says so and the simpler planner recommendation stays visible.

/// Mirror of `Decision.to_dict()` (loop.py). Built from the app's dynamic JSON value,
/// lenient by design: an evidence field the backend did not send renders as absent, it
/// never blocks the card.
struct HarnessDecision {
    struct Candidate {
        let move: String
        let score: Double?
        let reason: String
    }
    let runID: String
    let move: String
    let reason: String
    let conceptID: String
    let candidates: [Candidate]
    let alternatives: [String]

    init(json: JSON) {
        runID = json.text("run_id")
        move = json.text("move")
        reason = json.text("reason")
        conceptID = json.text("concept_id")
        candidates = json["candidates"].array.map { c in
            Candidate(move: c.text("move"),
                      score: c["score"].isNull ? nil : c["score"].double,
                      reason: c.text("reason"))
        }
        alternatives = json["alternatives"].array.map(\.string)
    }

    /// The runner-up: the highest-scoring move that was not chosen. The backend orders
    /// candidates by score, so the first non-chosen entry is the honest "why not X".
    var runnerUp: Candidate? {
        candidates.first { $0.move != move }
    }
}

struct HarnessPlanState {
    var decision: HarnessDecision?
    var explanation: String = ""
    var error: String = ""
}

/// The decision card for the Today hero. Renders the chosen move with its reason, the
/// runner-up it beat, and explicit outcome buttons that feed the loop's procedural
/// memory (`POST /harness/plan/{run_id}/outcome`).
struct HarnessPlanCard: View {
    @EnvironmentObject var store: AppStore
    @State private var showCandidates = false

    var body: some View {
        let state = store.harnessPlanState
        VStack(alignment: .leading, spacing: 10) {
            if let decision = state.decision {
                HStack(spacing: 8) {
                    Text("run \(String(decision.runID.suffix(6))) · scored against \(decision.candidates.count) moves")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(Palette.tertiary)
                    Spacer()
                }
                if let runner = decision.runnerUp {
                    Button {
                        showCandidates.toggle()
                    } label: {
                        Label("Why not \(runner.move)?", systemImage: showCandidates ? "chevron.down" : "chevron.right")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(Palette.forest)
                    }.buttonStyle(.plain)
                    if showCandidates {
                        VStack(alignment: .leading, spacing: 6) {
                            ForEach(decision.candidates, id: \.move) { candidate in
                                HStack(alignment: .firstTextBaseline, spacing: 8) {
                                    Text(candidate.move)
                                        .font(.system(size: 11, weight: .semibold, design: .monospaced))
                                        .frame(width: 84, alignment: .leading)
                                    if let score = candidate.score {
                                        Text(String(format: "%.3f", score))
                                            .font(.system(size: 10, design: .monospaced))
                                            .foregroundStyle(Palette.tertiary)
                                    }
                                    Text(candidate.reason)
                                        .font(.system(size: 10))
                                        .foregroundStyle(Palette.secondary)
                                        .lineSpacing(3)
                                }
                            }
                            Text(state.explanation)
                                .font(.system(size: 10))
                                .foregroundStyle(Palette.tertiary)
                                .lineSpacing(3)
                        }
                        .padding(10)
                        .background(Palette.sage.opacity(0.45), in: RoundedRectangle(cornerRadius: 10))
                    }
                }
                HStack(spacing: 10) {
                    Button("Helpful") { store.run { await store.submitHarnessOutcome(runID: decision.runID, outcome: "helpful") } }
                        .buttonStyle(LuminfestButtonStyle(primary: false)).disabled(store.harnessOutcomeBusy)
                    Button("Confusing") { store.run { await store.submitHarnessOutcome(runID: decision.runID, outcome: "confusing") } }
                        .buttonStyle(LuminfestButtonStyle(primary: false)).disabled(store.harnessOutcomeBusy)
                    Text("Your feedback trains this learner's own move preferences - it stays on this device's backend.")
                        .font(.system(size: 9))
                        .foregroundStyle(Palette.tertiary)
                }
            } else if !state.error.isEmpty {
                Text(state.error)
                    .font(.system(size: 11))
                    .foregroundStyle(Palette.secondary)
            }
        }
    }
}
