import Foundation

// -------------------------------------------------- harness agent surfaces
//
// The 9-MOVES loop (backend harness/loop.py) was fully built but dark: no UI called
// it, so the learner's "next step" came from the simpler planner. These loaders wire
// the decision surface in. Degradation is visible by construction: a failed plan
// fetch records the error and the card says the harness is unavailable instead of
// silently reusing the planner output.

extension AppStore {
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
}
