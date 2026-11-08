import Foundation
import AppKit
import UniformTypeIdentifiers

// ------------------------------------------------------- lesson procedure
//
// The 9-moves card names the decision for one turn; this is the run of show those
// turns sit inside. The sequence is compiled on the server from this learner's own
// evidence and the artifacts this instance actually holds, so the app never decides
// what comes next - it renders the plan it was given and reports which block
// finished. Advancing a block records *that the activity happened*, never that it
// went well: mastery still moves only through submitted answers and playground runs.

extension AppStore {
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

    /// Re-read the stored run after scoring; a local submission is not proof of completion.
    func refreshLessonProcedure(runID: String) async throws {
        let version = epoch
        let result = try await api.json("/procedure/runs/" + runID)
        guard epoch == version, authenticated, lessonProcedure.runID == runID else { return }
        guard result.text("run_id") == runID else {
            throw AppFailure(message: "The server returned a different lesson run; progress was not applied.", status: nil)
        }
        lessonProcedure = LessonProcedureState(run: result)
        connected = true
    }

    /// Mark one block done (or skipped) and move the card on.
    func advanceLessonProcedure(order: Int, outcome: String) async {
        guard authenticated, !lessonProcedureBusy, lessonProcedure.isRunning,
              let current = lessonProcedure.current, current.order == order else { return }
        if outcome == "done", current.isScored, !current.answersComplete {
            lessonProcedure.error = current.completionReason
            return
        }
        let runID = lessonProcedure.runID, version = epoch
        lessonProcedure.error = ""
        lessonProcedureBusy = true
        defer { if epoch == version { lessonProcedureBusy = false } }
        do {
            let result = try await api.json("/procedure/runs/" + runID + "/advance",
                                            method: "POST",
                                            body: ["order": order, "outcome": outcome])
            guard epoch == version, authenticated, lessonProcedure.runID == runID else { return }
            lessonProcedure = LessonProcedureState(run: result)
            if lessonProcedure.isComplete {
                notice = "Lesson complete. Recorded answers and simulation outcomes determine mastery; advancing does not add credit."
                await refresh()
            }
        } catch {
            guard epoch == version, lessonProcedure.runID == runID else { return }
            lessonProcedure.error = "The block could not advance: " + error.localizedDescription
            record(error)
        }
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
}
