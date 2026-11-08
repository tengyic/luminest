import Foundation

extension AppStore {
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
            projects = .null; analytics = .null; gradebook = .null; perspectives = .null
            messages = []; selectedConcept = ""
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

    /// The map page needs both layers: the authored lessons and the full course graph.
    func loadMap() async {
        await load("/curriculum") { self.curriculum = $0 }
        await load("/knowledge-graph") { self.graph = $0 }
    }
}
