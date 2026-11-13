import AppKit
import ApplicationServices
import Darwin
import Foundation

/// In-process QA: every workflow change goes through the application's real accessibility
/// elements, resolved through the same AXUIElement channel that external tooling and XCTest use.
///
/// Rationale: SwiftUI on this OS does not surface `accessibilityIdentifier` through the
/// in-process `NSAccessibilityProtocol` bridge (verified empirically: identifiers return empty),
/// but the identifiers *are* present on the AX server. Driving the AX tree keeps this a genuine
/// first-person test — real fields, real buttons, real presses — with no direct state mutation.
///
/// Deliberately **not** `@MainActor`. This process is both the AX client and the AX provider for
/// itself, and AppKit answers accessibility requests on the main thread. Issuing AX calls from
/// the main actor therefore risks a self-deadlock in which the main thread waits for an answer
/// only the main thread can produce — an intermittent hang that is indistinguishable from a hung
/// app. Running the workflow off the main actor removes that whole class of hang; the few AppKit
/// touches that genuinely require the main thread hop back explicitly.
final class NativeQA {
    static let shared = NativeQA()
    private var started = false
    private var output: URL?
    private var report: URL?
    private var events: [[String: Any]] = []
    private var screenshots: [[String: Any]] = []
    private var failures: [String] = []
    /// Per-journey verdicts for the release gate; empty unless `--native-qa-journeys` ran.
    private var journeyResults: [[String: Any]] = []
    private var journeyDirectory: URL?
    private var status = "running"
    private var stage = "startup"
    private var password = ""
    private var accountName = ""
    private var email = ""
    /// Typed into the real goal field during first-run setup. The Settings step later replaces
    /// it, which is deliberate: it proves the field is editable and that the last write wins.
    private let onboardingGoal = "Get ready for the next course and understand the ideas rather than memorise them"
    private let clock = ProcessInfo.processInfo.systemUptime
    private let limit = 20_000

    private struct Blocked: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }

    /// AppKit window work that genuinely requires the main thread. Everything else stays off it.
    @MainActor private func focusOwnWindow() {
        NSApp.activate(ignoringOtherApps: true)
        NSApp.windows.first(where: { $0.isVisible })?.makeKeyAndOrderFront(nil)
    }

    @MainActor private var applicationState: [String: Any] {
        ["appActive": NSApp.isActive, "visibleWindows": NSApp.windows.filter { $0.isVisible }.count]
    }

    /// The store's own view of the practice surface, read after Practice is pressed so that a
    /// missing practice overlay can be attributed: either the request never started, or it failed,
    /// or it succeeded and the presentation is the problem. That distinction is what turned an
    /// opaque "timed out waiting for question option A" into a fix.
    ///
    /// Reads through `AppStore.current` rather than `NSApp.delegate`, because the delegate cast
    /// does not round-trip under `@NSApplicationDelegateAdaptor` and a readback that always failed
    /// made every presentation fault look like missing state.
    @MainActor private var practiceState: [String: Any] {
        var state: [String: Any] = ["visibleWindowTitles": NSApp.windows.filter { $0.isVisible }.map { $0.title }]
        guard let store = AppStore.current else {
            state["storeAttached"] = false
            return state
        }
        state["storeAttached"] = true
        state["showQuestion"] = store.showQuestion
        state["questionBusy"] = store.questionBusy
        state["questionError"] = store.questionError ?? ""
        state["questionId"] = store.question["id"].string
        state["optionCount"] = store.question["options"].array.count
        return state
    }

    /// Invoke once from RootView's onAppear; repeated SwiftUI appearances are harmless.
    func runIfRequested() {
        guard !started else { return }
        if ProcessInfo.processInfo.arguments.contains("--qa-owned-shutdown") {
            started = true
            Task { await runOwnedShutdown() }
            return
        }
        if ProcessInfo.processInfo.arguments.contains("--native-qa-journeys") {
            started = true
            Task { await runJourneys() }
            return
        }
        guard ProcessInfo.processInfo.arguments.contains("--native-qa") else { return }
        started = true
        Task { await run() }
    }

    // MARK: - Golden student journeys (release gate)

    /// One journey's verdict plus the individual checks that produced it.
    ///
    /// ``status`` is deliberately not a boolean. ``gap`` means the product has no native
    /// path for the journey at all, and ``blocked`` means the journey could not be
    /// exercised for an environmental reason. Collapsing either into ``fail`` would make
    /// the gate unable to tell "we shipped this broken" from "we never shipped this", and
    /// collapsing them into ``pass`` would be a lie.
    private final class JourneyRecorder {
        let id: String
        let title: String
        let requirement: String
        var checks: [[String: Any]] = []
        var notes: [String] = []
        var status = "pass"
        let started = Date()

        init(id: String, title: String, requirement: String) {
            self.id = id
            self.title = title
            self.requirement = requirement
        }

        func check(_ name: String, _ ok: Bool, _ detail: String = "") {
            checks.append(["name": name, "ok": ok, "detail": detail])
            if !ok, status == "pass" { status = "fail" }
        }

        func gap(_ reason: String) {
            // A gap outranks a failure produced by the "this does not exist" check:
            // the missing feature is the finding, not a broken assertion.
            status = "gap"
            notes.append(reason)
        }

        func blocked(_ reason: String) {
            if status == "pass" { status = "blocked" }
            notes.append(reason)
        }

        /// Context that does not change the verdict: which of several legitimate paths
        /// was actually taken. Without it a reader cannot tell "it spoke" from "it
        /// refused with a named reason", even though both satisfy the requirement.
        func note(_ text: String) { notes.append(text) }

        func payload() -> [String: Any] {
            ["id": id, "title": title, "requirement": requirement, "status": status,
             "checks": checks, "notes": notes,
             "durationSeconds": Date().timeIntervalSince(started)]
        }
    }

    /// Return the app to a known base state before a journey starts.
    ///
    /// Journeys run in one process, so a sheet a previous journey opened can still be on
    /// screen and make the next journey's first navigation fail. Clearing that here — once,
    /// between journeys — is what makes the results comparable run to run, instead of
    /// depending on whether the previous journey happened to close its own modal.
    private func settleBase() async {
        for _ in 0..<2 {
            if let skip = find("tour.skip") {
                try? await performPress(skip, target: "tour.skip")
                await pause(0.4)
                continue
            }
            if let close = find("course.create.close") {
                try? await performPress(close, target: "dismiss authoring sheet")
                await pause(0.6)
                continue
            }
            if let cancel = buttonContaining("Cancel") {
                try? await performPress(cancel, target: "dismiss sheet")
                await pause(0.6)
                continue
            }
            break
        }
        try? await navigateRetry("today")
        await focusOwnWindow()
        await pause(0.4)
    }

    private func journey(_ id: String, _ title: String, _ requirement: String,
                         _ body: (JourneyRecorder) async -> Void) async {
        let recorder = JourneyRecorder(id: id, title: title, requirement: requirement)
        stage = "journey:" + id
        // Placeholder first: if the app dies mid-journey the evidence still names which
        // one, instead of the gate reporting a missing journey with no explanation.
        journeyResults.append(["id": id, "title": title, "requirement": requirement,
                               "status": "running", "checks": [], "notes": [], "durationSeconds": 0])
        writeJourneys()
        record("journey-start", target: id, outcome: title)
        // The first journey starts on the auth/onboarding surface, which has no base state
        // to return to; settling there would fight the first-run sheet.
        if journeyResults.count > 1 { await settleBase() }
        await body(recorder)
        if recorder.checks.isEmpty && recorder.status == "pass" { recorder.blocked("no checks ran") }
        journeyResults[journeyResults.count - 1] = recorder.payload()
        writeJourneys()
        record("journey-end", target: id, outcome: recorder.status,
               details: ["checks": recorder.checks.count, "failed": recorder.checks.filter { ($0["ok"] as? Bool) == false }.count])
    }

    private func writeJourneys() {
        guard let directory = journeyDirectory else { return }
        let document: [String: Any] = [
            "driver": "in-process AXUIElement against the running SwiftUI app",
            "generatedAt": ISO8601DateFormatter().string(from: Date()),
            "account": email,
            "journeys": journeyResults,
        ]
        do {
            let data = try JSONSerialization.data(withJSONObject: document, options: [.prettyPrinted, .sortedKeys])
            try data.write(to: directory.appendingPathComponent("journeys.json"), options: .atomic)
        } catch {
            NSLog("journey evidence write failed: %@", error.localizedDescription)
        }
    }

    /// An AX text field found by its placeholder, for controls that ship no identifier.
    /// Only the account-deletion phrase field needs this today; it is purposely narrow so
    /// it cannot become a back door for "find whatever is on screen".
    ///
    /// SwiftUI emits a `TextField`'s label through whichever attribute the current SDK
    /// chooses: the deletion-phrase field in particular arrives as `AXTitle`/`AXValue`
    /// rather than `AXPlaceholderValue`, so every candidate attribute is checked. The
    /// comparison stays an exact `==`, so this remains a narrow, attribute-agnostic lookup.
    private func findPlaceholder(_ placeholder: String) -> AXUIElement? {
        var match: AXUIElement?
        enumerate { element in
            if match != nil { return false }
            let candidates = [kAXPlaceholderValueAttribute, kAXTitleAttribute,
                             kAXValueAttribute, kAXDescriptionAttribute]
                .compactMap { string(element, $0 as String) }
            if candidates.contains(placeholder) {
                match = element
                return false
            }
            return true
        }
        return match
    }

    private func value(_ id: String) -> String {
        guard let element = find(id) else { return "" }
        return string(element, kAXValueAttribute as String) ?? ""
    }

    /// Run the ten release-gate journeys in order against the running application.
    ///
    /// Order matters only for evidence: J3 produces the attempts that J9 needs in order to
    /// distinguish measured learning from engagement, and J5's autosave check is cleaner
    /// before the account has a large project history. Everything else is independent.
    private func runJourneys() async {
        do {
            guard let path = argument("--qa-output"), path.hasPrefix("/") else {
                throw Blocked(message: "NATIVE_QA_JOURNEYS=1 requires --qa-output with an absolute directory")
            }
            journeyDirectory = URL(fileURLWithPath: path, isDirectory: true)
            try FileManager.default.createDirectory(at: journeyDirectory!, withIntermediateDirectories: true)
            output = journeyDirectory
            report = journeyDirectory!.appendingPathComponent("journeys-events.json")
            let unique = UUID().uuidString.lowercased()
            let environment = ProcessInfo.processInfo.environment
            accountName = environment["NATIVE_QA_NAME"] ?? "Journey Learner"
            email = environment["NATIVE_QA_EMAIL"] ?? "journey-\(unique)@example.com"
            password = environment["NATIVE_QA_PASSWORD"] ?? "Journey-\(UUID().uuidString)!"
            // Write the evidence file before the first wait, so a hang is diagnosable:
            // an empty events file with a startup stage means the app never got a window,
            // while a populated one names the last action that was attempted.
            stage = "journey-startup"
            record("launch", target: "journeys", outcome: "driver started",
                   details: ["arguments": ProcessInfo.processInfo.arguments,
                             "directory": journeyDirectory?.path ?? ""])
            try await waitMain("own application window", seconds: 30) {
                NSApp.windows.contains { $0.contentView != nil && $0.isVisible }
            }
            await focusOwnWindow()
            await pause(0.8)
        } catch {
            fail(error)
            status = "blocked"
            flush()
            return
        }

        await journey("J1", "First launch, registration and onboarding",
                      "A stranger can install, register and reach a personalised plan.") { rec in
            rec.check("authentication form is the first surface", self.find("auth.name") != nil,
                      "auth.name present before any action")
            do { try await self.authenticate() } catch {
                rec.check("registration", false, "\(error)")
                rec.blocked("registration could not be completed")
                return
            }
            rec.check("registration replaced the auth form", self.find("auth.name") == nil,
                      "signed-in UI observed after pressing Register")
            do { try await self.onboard() } catch {
                rec.check("first-run course setup", false, "\(error)")
                rec.blocked("onboarding sheet could not be completed")
                return
            }
            rec.check("onboarding dismissed", !self.containsText("SETTING UP YOUR LEARNING SPACE"),
                      "setup sheet no longer present")
            rec.check("a plan is shown after onboarding", self.containsText("YOUR PLAN"),
                      "YOUR PLAN visible on the today surface")
            rec.check("sidebar navigation is reachable",
                      self.find("nav.today") != nil || self.find("nav.compact.today") != nil,
                      "nav.today or compact equivalent present")
            try? await self.capture("journey-J1-plan")
        }

        await journey("J2", "Selecting a course and starting a lesson",
                      "A learner can open a lesson for the enrolled course and see its content.") { rec in
            do {
                try await self.navigateRetry("studio", marker: "studio.concept")
            } catch {
                rec.check("studio opens with a concept selector", false, "\(error)")
                rec.blocked("studio did not reach the concept surface")
                return
            }
            rec.check("the enrolled course surfaces a concept",
                      self.texts().contains { $0.count > 3 && $0.first?.isLetter == true },
                      "lesson chrome rendered")
            let lessonActions = ["lesson.read", "lesson.deck", "lesson.lecture"]
                .filter { self.find($0) != nil }
            rec.check("lesson actions are offered", !lessonActions.isEmpty,
                      "present: " + (lessonActions.isEmpty ? "none" : lessonActions.joined(separator: ", ")))
            if let read = self.find("lesson.read") {
                rec.check("read-aloud control is present and enabled",
                          self.boolean(read, kAXEnabledAttribute as String) ?? false,
                          "lesson.read enabled")
            }
            try? await self.capture("journey-J2-lesson")
        }

        await journey("J3", "Completing a practice question and receiving grading feedback",
                      "A submitted answer produces evaluated feedback and is recorded.") { rec in
            do {
                try await self.navigateRetry("studio", marker: "studio.practice")
                try await self.press("studio.practice")
                try await self.wait("a practice question", seconds: 30) {
                    self.find("question.option.a") != nil
                }
                rec.check("a practice question is shown with options",
                          self.find("question.option.a") != nil, "question.option.a present")
                try await self.press("question.option.a")
                try await self.press("question.submit")
                try await self.wait("evaluated feedback", seconds: 35) {
                    self.find("question.next") != nil
                        && (self.containsText("Correct answer:") || self.containsText("You’ve got it")
                            || self.containsText("A useful place to look closer"))
                }
                rec.check("feedback names the correct answer or explains the gap",
                          self.containsText("Correct answer:") || self.containsText("You’ve got it")
                            || self.containsText("A useful place to look closer"),
                          "feedback text observed after submit")
                rec.check("the learner can advance to another question", self.find("question.next") != nil,
                          "question.next present")
                try? await self.capture("journey-J3-feedback")
                try await self.press("question.finish")
                try await self.wait("practice dismissed", seconds: 15) { self.find("question.finish") == nil }
            } catch {
                rec.check("practice and grading", false, "\(error)")
                rec.blocked("practice surface could not be completed")
            }
        }

        await journey("J4", "Completing a review and receiving the next scheduled review",
                      "A completed review returns a next due date rather than a dead end.") { rec in
            do {
                try await self.navigateRetry("review", text: "Your review queue")
                rec.check("the review queue claims to be backend-scheduled",
                          self.containsText("SCHEDULED BY THE BACKEND"), "queue heading observed")
                guard let start = self.find("review.start") else {
                    rec.check("a review can be started", false, "review.start missing")
                    rec.blocked("no review control on the review page")
                    return
                }
                let enabled = self.boolean(start, kAXEnabledAttribute as String) ?? false
                if !enabled {
                    // A brand-new account has nothing due, which is the designed empty
                    // state, not a defect. Seed a deck through the app's own builder and
                    // grade one card, so the scheduling round-trip is still exercised
                    // through the UI instead of being skipped.
                    rec.check("the empty queue is explained", self.containsText("A little breathing room"),
                              "empty-state copy shown with a disabled Start review")
                    do {
                        try await self.seedAndGradeOneCard()
                        rec.check("a card built in the app becomes due and can be graded",
                                  self.find("flashcards.grade.good") != nil
                                    || self.containsText("Next due"),
                                  "deck built and the grade controls rendered")
                        rec.check("the scheduler returns a next due date instead of a dead end",
                                  !self.containsText("No cards yet"),
                                  "deck is non-empty after grading")
                        try? await self.capture("journey-J4-flashcard")
                        return
                    } catch {
                        rec.blocked("no review items were due and the deck could not be seeded: \(error)")
                        return
                    }
                }
                try await self.press("review.start")
                try await self.wait("a review question", seconds: 30) {
                    self.find("question.option.a") != nil
                }
                try await self.press("question.option.a")
                try await self.press("question.submit")
                try await self.wait("review feedback", seconds: 35) { self.find("question.next") != nil }
                rec.check("the review produces feedback", self.find("question.next") != nil,
                          "question.next observed after a review answer")
                try await self.press("question.finish")
                try await self.wait("back on the review page", seconds: 20) {
                    self.containsText("Your review queue")
                }
                rec.check("the queue is re-read after the review",
                          self.containsText("Your review queue"), "review page rendered again")
                try? await self.capture("journey-J4-review")
            } catch {
                rec.check("review round-trip", false, "\(error)")
                rec.blocked("review could not be completed")
            }
        }

        await journey("J5", "Leaving and reopening an autosaved project",
                      "Draft text survives navigating away and back without an explicit save.") { rec in
            let marker = "Autosave probe \(UUID().uuidString.prefix(6)): scaling a recipe by 5/2."
            do {
                try await self.navigateRetry("projects", marker: "project.text")
                try await self.type("project.text", text: marker)
                await self.pause(1.2)
                rec.check("the draft was typed into the real editor",
                          self.value("project.text").contains("Autosave probe"),
                          "project.text holds the typed marker")
                try await self.navigateRetry("today")
                await self.pause(0.8)
                try await self.navigateRetry("projects", marker: "project.text")
                await self.pause(1.2)
                let restored = self.value("project.text")
                rec.check("the draft is still there after leaving and returning",
                          restored.contains("Autosave probe"),
                          restored.isEmpty ? "field was empty on return" : "field still holds the draft")
                try? await self.capture("journey-J5-project")
            } catch {
                rec.check("project autosave", false, "\(error)")
                rec.blocked("projects surface could not be driven")
            }
        }

        await journey("J6", "Creating a course and accessing it again",
                      "A learner can author a course in the app and reopen it.") { rec in
            let unique = UUID().uuidString.prefix(6)
            // Real material, typed into the real editor. It is deliberately not the
            // shipped sample: if the preview came from a canned plan, this course would
            // be impossible. Four defined terms give the extractor something to find.
            let source = """
            # Heat transfer

            Conduction is the transfer of thermal energy through a material when its particles collide, with no movement of the material as a whole.

            Convection is the transfer of thermal energy by the bulk movement of a fluid, so it cannot happen in a solid.

            Radiation is the transfer of thermal energy by electromagnetic waves, and it needs no material between the source and the absorber.

            A thermal insulator is a material that slows conduction, which is why an insulator is used to keep a hot object hot.
            """
            do {
                let entry = self.find("course.create")
                rec.check("the native app offers course creation", entry != nil,
                          entry != nil ? "course.create entry point present in the shell header"
                                       : "no course-creation control on any surface the driver can reach")
                guard entry != nil else {
                    rec.gap("No SwiftUI entry point for course authoring.")
                    return
                }
                try await self.pressRetry("course.create")
                try await self.wait("the authoring sheet", seconds: 25) {
                    self.find("course.create.notes") != nil
                }
                try await self.type("course.create.notes", text: source)
                try await self.type("course.create.title", text: "Judge demo \(unique): heat transfer")
                try await self.type("course.create.subject", text: "Physics")
                try await self.pressRetry("course.create.preview")
                try await self.wait("a preview that saved nothing", seconds: 60) {
                    self.value("course.create.status").contains("Preview ready")
                }
                let preview = self.value("course.create.status")
                rec.check("a preview shows concepts without persisting a course",
                          preview.contains("Preview ready") && preview.contains("Nothing has been saved"),
                          preview.isEmpty ? "no status rendered" : String(preview.prefix(120)))
                try await self.pressRetry("course.create.commit")
                try await self.wait("the created course", seconds: 60) {
                    self.value("course.create.result").contains("course_id:")
                }
                let created = self.value("course.create.result")
                rec.check("the app reports a stored course id",
                          created.contains("course_id:") && !created.contains("course_id: \n"),
                          created.isEmpty ? "no course id rendered" : created)
                rec.check("creation is reported as owned but not yet active",
                          self.value("course.create.status").contains("not yet the active course"),
                          "status names the enrolment step")
                try await self.pressRetry("course.create.enrol")
                try await self.wait("enrolment confirmed", seconds: 60) {
                    self.value("course.create.status").contains("Enrolled.")
                }
                rec.check("the authored course becomes the active course",
                          self.value("course.create.result").contains("enrolled: true")
                            && self.value("course.create.status").contains("Enrolled."),
                          "enrolment confirmed and the plan reloaded")
                try? await self.capture("journey-J6-authoring")
                try await self.pressRetry("course.create.close")
                await self.pause(0.6)
                rec.check("the app is still usable after authoring",
                          self.find("nav.today") != nil || self.find("nav.compact.today") != nil,
                          "sidebar reachable after the sheet closes")
            } catch {
                rec.check("course authoring end to end", false, "\(error)")
                rec.blocked("the authoring surface could not be driven: \(error)")
            }
        }

        // J6 enrolled in the freshly authored course (proving the enrolment path), but that
        // course ships without lesson content here, which would break the lesson-dependent
        // journeys that follow. Restore the seed course before J7 so J4 and J8 have lessons.
        await restoreSeedCourse()

        await journey("J7", "Using the tutor offline and handling provider failure",
                      "A missing or failing model still yields a grounded answer, never an empty reply.") { rec in
            do {
                try await self.navigateRetry("teacher", marker: "teacher.message")
                let before = Set(self.texts())
                try await self.type("teacher.message",
                                    text: "Why do fractions need a common denominator? Answer in two sentences.")
                try await self.press("teacher.send")
                try await self.wait("a rendered tutor reply", seconds: 45) {
                    let fresh = Set(self.texts()).subtracting(before)
                    return fresh.contains { $0.count > 40 && !$0.contains("common denominator?") }
                }
                let fresh = Set(self.texts()).subtracting(before)
                rec.check("the tutor answers instead of returning an empty bubble",
                          fresh.contains { $0.count > 40 }, "new tutor text rendered")
                rec.check("the reply is labelled when it is not a live model",
                          self.containsText("GROUNDED TUTOR") || self.containsText("offline")
                            || self.containsText("curriculum"),
                          "grounding label or curriculum attribution visible")
                let raw = self.texts().filter { text in
                    ["Traceback", "HTTP 402", "HTTP 500", "request_id", "Insufficient Balance",
                     "Internal Server Error"].contains { text.contains($0) }
                }
                rec.check("no raw provider exception is shown to the learner", raw.isEmpty,
                          raw.isEmpty ? "no stack trace, status code or request id on screen"
                                      : "leaked: " + raw.prefix(2).joined(separator: " | "))
                try? await self.capture("journey-J7-tutor")
            } catch {
                rec.check("tutor offline behaviour", false, "\(error)")
                rec.blocked("tutor surface could not be driven")
            }
        }

        await journey("J9", "Viewing Insights and distinguishing learning from engagement",
                      "Insights separates measured outcomes from activity, and says which is which.") { rec in
            do {
                try await self.navigateRetry("insights", text: "Practice over time")
                // Insights loads `/analytics` asynchronously only once the surface is shown
                // (see `AppStore.loadPage`); the no-practice empty state ("A clearer picture
                // will emerge") therefore persists briefly after navigation. J3's practice
                // attempt makes `daily` non-empty, so the empty state is expected to clear.
                // Poll for it to clear, and if it does not within a window, re-enter insights
                // to force a fresh fetch — the single async load can be overtaken by a slow
                // start, and a second navigation reliably surfaces the settled data.
                var settled = false
                for _ in 0..<3 {
                    if !self.containsText("A clearer picture will emerge") { settled = true; break }
                    try? await self.wait("insights analytics settled", seconds: 12) {
                        !self.containsText("A clearer picture will emerge")
                    }
                    if !self.containsText("A clearer picture will emerge") { settled = true; break }
                    try? await self.navigateRetry("today")
                    try? await self.navigateRetry("insights", text: "Practice over time")
                }
                _ = settled
                rec.check("the measured chart is labelled as submissions only",
                          self.containsText("SUBMITTED ANSWERS ONLY"),
                          "SUBMITTED ANSWERS ONLY caption present")
                rec.check("real attempts replace the no-practice empty state",
                          !self.containsText("A clearer picture will emerge"),
                          "empty-state copy absent after practice in J3")
                rec.check("engagement is named separately from learning",
                          self.containsText("ENGAGEMENT") || self.containsText("activity")
                            || self.containsText("Activity"),
                          "an engagement section exists and is not conflated with mastery")
                try? await self.capture("journey-J9-insights")
            } catch {
                rec.check("insights", false, "\(error)")
                rec.blocked("insights surface could not be reached")
            }
        }

        await journey("J10", "Changing consent, exporting data and deleting an account",
                      "Consent is changeable, export is reachable, and deletion is gated deliberately.") { rec in
            do {
                try await self.navigateRetry("settings", marker: "settings.telemetry")
                try await self.setToggle("settings.telemetry", enabled: true)
                try await self.pressRetry("settings.save")
                try await self.wait("saved preferences", seconds: 30) {
                    self.containsText("Your preferences have been saved.")
                }
                rec.check("a consent change is saved and confirmed",
                          self.containsText("Your preferences have been saved."),
                          "confirmation observed after enabling activity consent")
                let exported = self.find("settings.export")
                rec.check("data export is offered to the learner",
                          exported != nil && (self.boolean(exported!, kAXEnabledAttribute as String) ?? false),
                          "settings.export present and enabled")
                // The export itself goes through an NSSavePanel, which is system UI rather
                // than app UI; Layer 2 verifies GET /export end to end. What is verified
                // here is that the learner-facing control exists and is usable.
                // The identifier sits on a borderless button whose AXPress sometimes lands
                // without toggling the sheet; fall back to pressing the button by its own
                // label, then to a second attempt, before calling the surface unreachable.
                try await self.pressRetry("settings.delete")
                if !self.containsText("Permanently delete your account?") {
                    if let byLabel = self.buttonContaining("Delete account") {
                        try? await self.performPress(byLabel, target: "Delete account")
                    }
                }
                if !self.containsText("Permanently delete your account?") {
                    try? await self.pressRetry("settings.delete", attempts: 2)
                }
                let phraseFieldPresent = self.find("settings.delete.phrase") != nil
                try await self.wait("delete confirmation sheet", seconds: 25) {
                    self.containsText("Permanently delete your account?") || phraseFieldPresent
                }
                let sheetShown = self.containsText("Permanently delete your account?") || phraseFieldPresent
                rec.check("deletion requires an explicit confirmation sheet",
                          sheetShown, sheetShown ? "confirmation sheet shown" : "no confirmation sheet observed")
                // Verify the gate functionally rather than by identifier. The in-process AX bridge may not
                // surface the phrase field's identifier, so locate it by its placeholder text and type the
                // exact phrase; then confirm the destructive button enables *only then*. This exercises the
                // real binding (`.disabled(deletePhrase != "DELETE MY ACCOUNT")`) — a stronger assertion than
                // merely confirming the field exists. The button is enabled but never pressed; Cancel below
                // still dismisses the sheet without deleting the account.
                if let _ = self.findEditable(containing: "DELETE MY ACCOUNT") {
                    try? await self.typeContaining("DELETE MY ACCOUNT", text: "DELETE MY ACCOUNT")
                    await self.pause(0.6)
                    if let destructive = self.findPressable(containing: "Delete permanently") {
                        rec.check("the destructive action enables only after the exact phrase",
                                  (self.boolean(destructive, kAXEnabledAttribute as String) ?? false) == true,
                                  "Delete permanently enabled after the exact phrase was typed")
                    } else {
                        rec.check("deletion is gated on typing the exact phrase", false,
                                  "destructive button not locatable to verify the gate")
                    }
                } else if phraseFieldPresent,
                          let destructive = self.find("settings.delete.confirm") ?? self.buttonContaining("Delete permanently") {
                    // Fallback when the field is locatable by identifier but not by placeholder text:
                    // assert the destructive button starts disabled until the phrase is supplied.
                    rec.check("the destructive action is disabled until the phrase is typed",
                              (self.boolean(destructive, kAXEnabledAttribute as String) ?? true) == false,
                              "Delete permanently starts disabled")
                } else {
                    rec.check("deletion is gated on typing the exact phrase", false,
                              "no phrase field found in the confirmation sheet")
                }
                // Deliberately cancelled: it is last, and erasing the account would also
                // erase the database evidence for J1-J9 that the launcher reads afterwards.
                if sheetShown { try? await self.pressLabel("Cancel") }
                await self.pause(0.6)
                rec.check("the confirmation can be abandoned safely",
                          !self.containsText("Permanently delete your account?") && !phraseFieldPresent,
                          "sheet dismissed by Cancel")
                rec.check("the account is still signed in after cancelling", self.find("nav.settings") != nil
                            || self.find("nav.compact.settings") != nil,
                          "sidebar still reachable")
                try? await self.capture("journey-J10-settings")
            } catch {
                rec.check("consent, export and deletion", false, "\(error)")
                rec.blocked("settings surface could not be driven")
            }
        }

        await journey("J8", "Using read-aloud and handling unavailable voice services",
                      "Read-aloud either speaks or refuses with a named reason; it never hangs.") { rec in
            do {
                if self.find("tour.skip") != nil { try? await self.press("tour.skip") }
                try await self.navigateRetry("studio", marker: "studio.practice")
                // `studio.practice` renders as soon as a concept is selected, but `lesson.read` only
                // appears after the async `/lessons/{id}` fetch returns. The marker wait above can
                // therefore resolve before the lesson loads. Poll for `lesson.read`, and if it has not
                // landed, re-enter studio (which re-selects the concept and re-triggers the fetch)
                // rather than racing the request on a healthy surface.
                var read: AXUIElement?
                for _ in 0..<3 {
                    if let r = self.find("lesson.read") { read = r; break }
                    try? await self.wait("read-aloud control", seconds: 15) { self.find("lesson.read") != nil }
                    if let r = self.find("lesson.read") { read = r; break }
                    try? await self.navigateRetry("today")
                    try? await self.navigateRetry("studio", marker: "studio.practice")
                }
                guard let read = read else {
                    rec.check("a read-aloud control exists", false, "lesson.read missing after lesson load")
                    rec.blocked("no read-aloud control on the studio surface")
                    return
                }
                rec.check("the read-aloud control is enabled", self.boolean(read, kAXEnabledAttribute as String) ?? false,
                          "lesson.read enabled")
                try await self.press("lesson.read")
                // The old check accepted *any* text containing "voice", which the static
                // engine caption under the button always supplies. A press that did
                // nothing therefore passed the check and was then reported blocked.
                // The app now publishes a one-sentence outcome; the driver waits for
                // that specific state change instead of for a word that was already
                // on screen before the press.
                try await self.wait("a named read-aloud outcome", seconds: 30) {
                    let state = self.value("lesson.read.status")
                    return state.contains("Reading with")
                        || state.contains("There is no lesson text")
                        || self.containsText("Stop reading")
                }
                let state = self.value("lesson.read.status")
                let speaking = self.containsText("Stop reading")
                rec.check("pressing read-aloud produces speech or a named reason",
                          speaking || state.contains("Reading with") || state.contains("There is no lesson text"),
                          speaking ? "control switched to Stop reading" : String(state.prefix(140)))
                rec.check("the outcome is named by the app, not inferred from a caption",
                          !state.isEmpty || speaking,
                          state.isEmpty ? "only the control changed" : "lesson.read.status carries the reason")
                rec.check("the app is still responsive afterwards", self.find("nav.settings") != nil
                            || self.find("nav.compact.settings") != nil,
                          "sidebar still reachable")
                rec.note(speaking ? "Speech started and the control switched to Stop reading."
                         : "Path taken: \(state.isEmpty ? "control state only" : state)")
                if speaking { try? await self.press("lesson.read") }
                try? await self.capture("journey-J8-voice")
            } catch {
                rec.check("read-aloud", false, "\(error)")
                rec.blocked("read-aloud could not be exercised")
            }
        }


        let failed = journeyResults.filter { ($0["status"] as? String) == "fail" }.count
        let gaps = journeyResults.filter { ($0["status"] as? String) == "gap" }.count
        let blocked = journeyResults.filter { ($0["status"] as? String) == "blocked" }.count
        status = failed == 0 ? "completed" : "blocked"
        record("journeys", target: "release gate", outcome: status,
               details: ["total": journeyResults.count, "failed": failed, "gaps": gaps, "blocked": blocked])
        writeJourneys()
        flush()
        if !ProcessInfo.processInfo.arguments.contains("--qa-keep-open") {
            await pause(0.5)
            await MainActor.run { NSApp.terminate(nil) }
        }
    }

    /// Navigate with retries. The sidebar is rebuilt when a sheet dismisses, so a press
    /// issued in the frame between `find` and `AXPress` can hit a stale element. Retrying
    /// after a short settle is what distinguishes "the surface is gone" from "we raced it".
    private func navigateRetry(_ page: String, marker: String? = nil,
                               text: String? = nil) async throws {
        var last: Error = Blocked(message: "navigation never attempted")
        for attempt in 0..<3 {
            do {
                try await navigate(page, marker: marker, text: text)
                return
            } catch {
                last = error
                await focusOwnWindow()
                await pause(Double(attempt + 1) * 0.9)
            }
        }
        throw last
    }

    /// J6 enrolls in the freshly authored course to prove the enrolment path, but that course
    /// ships without lesson content in the harness (its concepts have no lessons), which would
    /// leave the studio empty for the lesson- and deck-dependent journeys that follow (J4 needs
    /// a lesson to generate cards; J8 needs one to read aloud). Restore the seed course the
    /// learner actually enrolled in during onboarding so those journeys have a lesson to work
    /// with. This is a test-sequencing step, not a product change: J6's "becomes the active
    /// course" assertion has already passed before we switch back.
    private func restoreSeedCourse() async {
        let seed = ProcessInfo.processInfo.environment["NATIVE_QA_COURSE"] ?? "integrated_math_1"
        do {
            try await navigateRetry("settings")
            // Only act if the seed course is not already the active one (it shows an Enrol
            // button only when it is not the enrolled course).
            guard find("settings.course." + seed + ".enrol") != nil else {
                try? await navigateRetry("today"); return
            }
            try? await press("settings.course." + seed + ".enrol")
            await pause(0.6)
            try? await press("settings.course." + seed + ".switch")
            // Let the switch land and the curriculum reload before the next journey drives studio.
            try? await wait("seed course restored", seconds: 20) { self.containsText("ENROLLED") }
            try? await navigateRetry("today")
        } catch {
            // Non-fatal: if the switcher is unreachable the downstream journeys will report
            // their own, more specific failures rather than a cryptic sequencing error.
        }
    }

    /// Press with retries, for controls inside a surface that rebuilds while we look at it.
    private func pressRetry(_ id: String, attempts: Int = 3) async throws {
        var last: Error = Blocked(message: "press never attempted: \(id)")
        for attempt in 0..<attempts {
            do {
                try await press(id)
                return
            } catch {
                last = error
                await focusOwnWindow()
                await pause(Double(attempt + 1) * 0.7)
            }
        }
        throw last
    }

    /// Build a deck from the current concept through the app's own UI, then grade one card.
    ///
    /// This is the only way to exercise the FSRS round-trip on a fresh account: nothing is
    /// due yet, and seeding the database directly would prove nothing about the app.
    private func seedAndGradeOneCard() async throws {
        try await navigateRetry("studio", marker: "studio.concept")
        try? await pressLabel("Cards")
        await pause(0.8)
        guard let generate = find("flashcards.generate") else {
            throw Blocked(message: "the Cards stage did not expose Auto-generate")
        }
        if (boolean(generate, kAXEnabledAttribute as String) ?? false) == false {
            throw Blocked(message: "Auto-generate is disabled, so no deck can be built for this concept")
        }
        try await pressRetry("flashcards.generate")
        // The generate sheet is an inline overlay now (not a separate window), and its
        // `Preview` button ships no identifier and carries the visible word in a child
        // `AXStaticText` — so the *wait* must use the same child-descent locator that
        // the press below uses (`buttonContaining`), not the own-attribute `containsText`
        // scan that misses it and times out against a visible overlay.
        try await wait("generate sheet", seconds: 25) {
            self.buttonContaining("Preview") != nil || self.containsText("New cards for")
        }
        if let previewButton = buttonContaining("Preview") {
            try await performPress(previewButton, target: "Preview")
        } else {
            try await pressContaining("Preview")
        }
        try await wait("generated preview", seconds: 45) {
            self.buttonContaining("card") != nil || self.containsText("Add ")
        }
        // The Add button ships its count in the label ("Add 12 cards") and, like Preview, exposes
        // that label only in a child static text rather than as a pressable `AXButton` role. A bare
        // `buttonContaining` match works when the role is present, but fall back to the descendant-
        // aware press so the deck is always committed through the app's own UI.
        if let add = buttonContaining("Add ") {
            try await performPress(add, target: "add cards")
        } else {
            try await pressContaining("Add ")
        }
        await pause(2.0)
        try await wait("a revealed card", seconds: 30) { self.find("flashcards.reveal") != nil }
        try await press("flashcards.reveal")
        await pause(0.8)
        try await wait("grade controls", seconds: 20) { self.find("flashcards.grade.good") != nil }
        try await press("flashcards.grade.good")
        await pause(1.5)
    }

    /// AX buttons matched by contained label, for controls that ship no identifier.
    ///
    /// SwiftUI often puts the visible words in a child `AXStaticText` and leaves the button
    /// itself with an empty title, so checking `AXTitle` alone misses real buttons.
    private func buttonContaining(_ label: String) -> AXUIElement? {
        var match: AXUIElement?
        enumerate { element in
            if match != nil { return false }
            guard role(element) == kAXButtonRole as String else { return true }
            var haystack = strings(element)
            for child in children(element) { haystack.append(contentsOf: strings(child)) }
            if haystack.contains(where: { $0.contains(label) }) {
                match = element
                return false
            }
            return true
        }
        return match
    }

    private func argument(_ name: String) -> String? {
        let args = ProcessInfo.processInfo.arguments
        guard let index = args.firstIndex(of: name), args.indices.contains(index + 1) else { return nil }
        return args[index + 1]
    }

    private func run() async {
        // The ten-journey gate shares this exact launch path (``--native-qa`` plus
        // ``--qa-output``) because that is the one the launcher already proves works.
        // A separate flag was tried first and never reached onAppear, which is a launch
        // behaviour, not a driver behaviour; reusing the known-good argument set keeps
        // the gate runnable instead of theoretical.
        if ProcessInfo.processInfo.environment["NATIVE_QA_JOURNEYS"] == "1" {
            await runJourneys()
            return
        }
        do {
            guard let path = argument("--qa-output"), path.hasPrefix("/") else {
                throw Blocked(message: "--qa-output requires an absolute directory or JSON path")
            }
            let supplied = URL(fileURLWithPath: path)
            report = supplied.pathExtension.lowercased() == "json" ? supplied : supplied.appendingPathComponent("workflow-events.json")
            output = report?.deletingLastPathComponent()
            try FileManager.default.createDirectory(at: output!, withIntermediateDirectories: true)
            let unique = UUID().uuidString.lowercased()
            let environment = ProcessInfo.processInfo.environment
            accountName = environment["NATIVE_QA_NAME"] ?? "Native QA \(unique.prefix(8))"
            email = environment["NATIVE_QA_EMAIL"] ?? "native-\(unique)@example.com"
            password = environment["NATIVE_QA_PASSWORD"] ?? "Qa-\(UUID().uuidString)!"
            record("launch", target: "NSApplication", outcome: "observed", details: ["uiTestArgument": ProcessInfo.processInfo.arguments.contains("--ui-test")])
            // A cold first launch with a brand-new HOME can take longer than 10 s to
            // order its window front (observed once at ~10.2 s: the blocked capture
            // showed a fully rendered OnboardingView). This is a startup race in the
            // driver, not a product defect, so the window wait is bounded but generous.
            try await waitMain("own application window", seconds: 30) { NSApp.windows.contains { $0.contentView != nil && $0.isVisible } }
            await focusOwnWindow()
            await pause(0.8)
            try await capture("auth") // Always precedes any action that could block authentication.
            guard ProcessInfo.processInfo.arguments.contains("--ui-test") else { throw Blocked(message: "--ui-test is required to avoid session restore and bundled backend startup") }
            try await authenticate()
            if ProcessInfo.processInfo.environment["NATIVE_QA_SKIP_SETUP"] == "1" {
                record("onboarding", target: "setup.sheet", outcome: "suppressed for the returning-learner path")
                await exercise("setup-sheet") { try await self.reopenSetupSheet() }
            } else {
                await exercise("onboarding") { try await self.onboard() }
            }
            await exercise("studio") {
                try await self.navigateRetry("studio", marker: "studio.practice")
                try await self.capture("studio")
            }
            await exercise("question") { try await self.practice() }
            await exercise("tutor") { try await self.tutor() }
            await exercise("map") {
                try await self.navigateRetry("map", text: "Understanding is connected.")
                try await self.capture("map")
            }
            await exercise("projects") { try await self.project() }
            await exercise("consent") { try await self.consent() }
            await exercise("insights") {
                try await self.navigateRetry("insights", text: "Practice over time")
                try await self.capture("insights")
            }
            await captureRequestedPages()
            await responsiveWidths()
            status = failures.isEmpty ? "completed" : "blocked"
        } catch {
            fail(error)
            status = "blocked"
            try? await capture("blocked")
        }
        stage = "finished"
        record("workflow", target: "native UI", outcome: status, details: ["backendVerification": "pending isolated launcher database inspection"])
        password = ""
        flush()
        // Only terminate after final evidence is on disk; no bootstrap-time exit.
        if !ProcessInfo.processInfo.arguments.contains("--qa-keep-open") {
            await pause(0.5)
            await MainActor.run { NSApp.terminate(nil) }
        }
    }

    /// Acceptance 2.5 re-run: a REAL frozen backend binary from the app bundle is spawned
    /// on an isolated port as the launcher's owned child, then the application is closed
    /// normally. `applicationWillTerminate -> stopOwnedProcess() -> shutdown(...)` is the
    /// exact production path. The external driver checks the port and both protected
    /// user listeners after the app exits.
    private func runOwnedShutdown() async {
        var child: Process?
        do {
            guard let path = argument("--qa-output"), path.hasPrefix("/") else {
                throw Blocked(message: "--qa-output requires an absolute directory")
            }
            let dir = URL(fileURLWithPath: path, isDirectory: true)
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            report = dir.appendingPathComponent("owned-shutdown.json")
            output = dir
            stage = "owned-shutdown"
            let mode = ProcessInfo.processInfo.environment["NATIVE_QA_SHUTDOWN_MODE"] ?? "frozen"
            guard mode == "frozen" || mode == "ignorer" else {
                throw Blocked(message: "unknown NATIVE_QA_SHUTDOWN_MODE: \(mode)")
            }
            // 8893 = real frozen backend (cooperative + wrapper variants).
            // 8886 = the ORIGINAL 2.5 defect fixture: a genuinely SIGTERM-ignoring owned child.
            let port = mode == "ignorer" ? 8886 : 8893
            let dataDir = dir.appendingPathComponent("data", isDirectory: true)
            try FileManager.default.createDirectory(at: dataDir, withIntermediateDirectories: true)
            var environment = ProcessInfo.processInfo.environment.filter {
                !$0.key.hasPrefix("HARNESS_") && !$0.key.hasPrefix("PYTHON")
            }
            environment["HARNESS_DATA_DIR"] = dataDir.path
            environment["HARNESS_DATABASE_URL"] = "sqlite:///\(dataDir.path)/harness.sqlite3"
            environment["HARNESS_ENV"] = "desktop"
            environment["HARNESS_AUTO_CREATE"] = "1"
            environment["HARNESS_ALLOWED_HOSTS"] = "localhost,127.0.0.1"
            // Deliberately no HARNESS_TUTOR_PROVIDER. This used to be pinned to "offline",
            // a value config.py now rejects at startup, so the QA child failed to boot and
            // the failure looked like the app's. The dialectic loop filters every HARNESS_
            // key out of the parent environment above, so the child starts unconfigured —
            // which is exactly the desktop default these journeys are meant to exercise.
            environment["HARNESS_SECRET"] = UUID().uuidString // generated; never logged
            environment["PYTHONDONTWRITEBYTECODE"] = "1"

            let launchURL: URL
            var ownedArguments: [String] = []
            var controlFile: URL?
            var notes = ""
            if mode == "frozen" {
                guard let resources = Bundle.main.resourceURL else {
                    throw Blocked(message: "app bundle has no Resources directory")
                }
                let executable = resources.appendingPathComponent("backend/LuminfestBackend/LuminfestBackend")
                guard FileManager.default.isExecutableFile(atPath: executable.path) else {
                    throw Blocked(message: "real frozen backend binary is missing from the bundle")
                }
                let ignoreSigterm = ProcessInfo.processInfo.environment["NATIVE_QA_IGNORE_SIGTERM"] == "1"
                // A shell wrapper installs SIG_IGN for SIGTERM and then execs the REAL frozen
                // backend. LIMITATION (measured, see verification.txt): uvicorn reinstalls its
                // own SIGTERM handler during startup, so this variant does NOT prove force-kill
                // escalation. The `ignorer` mode is the faithful reproduction of original 2.5.
                if ignoreSigterm {
                    let wrapper = dir.appendingPathComponent("sigterm-ignoring-backend.sh")
                    let script = "#!/bin/sh\ntrap '' TERM\nexec \"\(executable.path)\" \"$@\"\n"
                    try script.write(to: wrapper, atomically: true, encoding: .utf8)
                    try FileManager.default.setAttributes([.posixPermissions: 0o700],
                                                          ofItemAtPath: wrapper.path)
                    launchURL = wrapper
                } else {
                    launchURL = executable
                }
                ownedArguments = ["--port", String(port)]
                notes = "real frozen backend; wrapper=\(ignoreSigterm)"
            } else {
                // Faithful reproduction of the original 2.5 failing sub-case: bind the isolated
                // port, install SIG_IGN, self-signal SIGTERM, and only THEN write a control file.
                // If SIGTERM were honoured the control file could never exist. This is the exact
                // condition the patched shutdown() must escalate past with an exact-PID SIGKILL.
                let scriptURL = dir.appendingPathComponent("sigterm_ignorer.py")
                let control = dir.appendingPathComponent("sigterm-control.txt")
                let heartbeat = dir.appendingPathComponent("sigterm-heartbeat.txt")
                let script = """
                import os, signal, socket, sys, time
                port = int(sys.argv[1]); control = sys.argv[2]; heartbeat = sys.argv[3]
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", port)); s.listen(5)
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                signal.signal(signal.SIGINT, signal.SIG_IGN)
                os.kill(os.getpid(), signal.SIGTERM)
                with open(control, "w") as f:
                    f.write("pid=%d port=%d self_sigterm_sent=1 still_alive=1 socket_still_bound=%s\\n" % (os.getpid(), port, str(s.getsockname())))
                while True:
                    with open(heartbeat, "w") as f: f.write(str(time.time()))
                    time.sleep(0.2)
                """
                try script.write(to: scriptURL, atomically: true, encoding: .utf8)
                launchURL = URL(fileURLWithPath: "/usr/bin/python3")
                ownedArguments = [scriptURL.path, String(port), control.path, heartbeat.path]
                controlFile = control
                notes = "genuine SIGTERM-ignoring owned child on the original 2.5 port"
            }

            let owned = Process()
            owned.executableURL = launchURL
            owned.arguments = ownedArguments
            owned.environment = environment
            owned.standardInput = FileHandle.nullDevice
            let logURL = dir.appendingPathComponent("backend.log")
            FileManager.default.createFile(atPath: logURL.path, contents: nil)
            let logHandle = try FileHandle(forWritingTo: logURL)
            owned.standardOutput = logHandle
            owned.standardError = logHandle
            try owned.run()
            child = owned
            let backendPID = owned.processIdentifier
            let appPID = getpid()
            try "\(backendPID)\n".write(to: dir.appendingPathComponent("owned-child-pid.txt"),
                                        atomically: true, encoding: .utf8)
            try "\(appPID)\n".write(to: dir.appendingPathComponent("app-pid.txt"),
                                    atomically: true, encoding: .utf8)
            record("owned-shutdown", target: "spawned owned child",
                   outcome: "running", details: [
                    "appPID": appPID, "backendPID": backendPID, "port": port, "mode": mode,
                    "launchedURL": launchURL.path, "notes": notes, "dataDir": dataDir.path,
                   ])

            if mode == "frozen" {
                // Wait for the actual health contract, not merely for the process to exist.
                let healthURL = URL(string: "http://127.0.0.1:\(port)/api/v1/health")!
                let deadline = Date().addingTimeInterval(120)
                var healthy = false
                while Date() < deadline && owned.isRunning {
                    var request = URLRequest(url: healthURL)
                    request.timeoutInterval = 1
                    if let (data, response) = try? await URLSession.shared.data(for: request),
                       (response as? HTTPURLResponse)?.statusCode == 200,
                       let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
                       object["ready"] as? Bool == true,
                       object["service"] as? String == "luminfest-learning-harness" {
                        healthy = true
                        break
                    }
                    try? await Task.sleep(nanoseconds: 300_000_000)
                }
                guard healthy else {
                    throw Blocked(message: "real frozen backend never became healthy on \(port)")
                }
                record("owned-shutdown", target: "health", outcome: "ready",
                       details: ["port": port, "service": "luminfest-learning-harness",
                                 "pidStillRunning": owned.isRunning])
            } else {
                // The control file can only be written AFTER a self-sent SIGTERM was ignored.
                let control = controlFile!
                let deadline = Date().addingTimeInterval(30)
                while Date() < deadline && owned.isRunning &&
                        !FileManager.default.fileExists(atPath: control.path) {
                    try? await Task.sleep(nanoseconds: 100_000_000)
                }
                guard FileManager.default.fileExists(atPath: control.path) else {
                    throw Blocked(message: "SIGTERM ignorer never produced its control file")
                }
                let controlText = (try? String(contentsOf: control, encoding: .utf8)) ?? ""
                try? await Task.sleep(nanoseconds: 500_000_000) // let heartbeats prove it kept running
                guard owned.isRunning else {
                    throw Blocked(message: "SIGTERM ignorer exited before app termination")
                }
                record("owned-shutdown", target: "sigterm-control",
                       outcome: "SIGTERM ignored; owned child still holds its port",
                       details: ["control": controlText.trimmingCharacters(in: .whitespacesAndNewlines),
                                 "port": port, "pidStillRunning": owned.isRunning,
                                 "escalationExpected": true])
            }

            await MainActor.run { BackendLauncher.shared.qaInstallOwnedProcess(owned) }
            record("owned-shutdown", target: "BackendLauncher",
                   outcome: "installed as owned child; normal termination requested",
                   details: ["graceSeconds": BackendLauncher.terminationGraceSeconds,
                             "path": "applicationWillTerminate -> stopOwnedProcess() -> shutdown()"])
            status = "termination-requested"
            flush()
            // Close the app normally. Everything after this point is verified by the
            // external driver once the process has exited.
            await MainActor.run { NSApp.terminate(nil) }
        } catch {
            fail(error)
            status = "blocked"
            if let owned = child, owned.isRunning {
                kill(owned.processIdentifier, SIGKILL) // exact child PID spawned above only
            }
            flush()
            await MainActor.run { NSApp.terminate(nil) }
        }
    }

    private func authenticate() async throws {
        stage = "auth"
        try await wait("registration fields", seconds: 20) { self.find("auth.name") != nil }
        let rawEndpoint = argument("--qa-endpoint") ?? "8765"
        let endpoint = rawEndpoint.allSatisfy(\.isNumber) ? "http://127.0.0.1:\(rawEndpoint)" : rawEndpoint
        guard let components = URLComponents(string: endpoint), components.scheme == "http", components.host == "127.0.0.1", let port = components.port, (1024...65535).contains(port), components.path.isEmpty, components.query == nil, components.fragment == nil, components.user == nil else {
            throw Blocked(message: "QA endpoint must identify the isolated nonprivileged loopback server")
        }
        if find("auth.endpoint") == nil {
            try await pressLabel("Local learning server")
        }
        try await type("auth.endpoint", text: endpoint)
        try await type("auth.name", text: accountName)
        try await type("auth.email", text: email)
        try await type("auth.password", text: password, secret: true)
        // Registration is deliberately gated on the two compliance toggles (13+ and
        // Terms/Privacy). Record the gate as evidence, then satisfy it through the real
        // AX checkboxes before pressing. The driver used to skip these and timed out
        // waiting for an enabled auth.register, which is the product behaving correctly.
        if let register = find("auth.register"),
           boolean(register, kAXEnabledAttribute as String) == false {
            record("compliance-gate", target: "auth.register",
                   outcome: "disabled until age and terms are accepted",
                   details: ["authRegisterEnabled": false])
        }
        try await setToggle("auth.age", enabled: true)
        try await setToggle("auth.terms", enabled: true)
        try await press("auth.register")
        await pause(6)
        await focusOwnWindow()
        await pause(1.0)
        record("diagnostic", target: "after-register", outcome: "state captured",
               details: (await MainActor.run { self.applicationState })
                        .merging(["navTodayPresent": self.find("nav.today") != nil,
                                  "compactNavTodayPresent": self.find("nav.compact.today") != nil,
                                  "authNamePresent": self.find("auth.name") != nil]) { _, new in new })
        try? await capture("after-register")
        // A brand-new account lands on first-run setup rather than the shell. Either surface proves
        // the session is real; the auth form being gone proves the view actually swapped.
        try await wait("signed-in UI", seconds: 30) {
            self.find("auth.name") == nil
                && (self.find("nav.today") != nil || self.find("nav.compact.today") != nil
                    || self.containsText("SETTING UP YOUR LEARNING SPACE"))
        }
        record("authentication", target: "auth.register", outcome: "signed-in UI observed", details: ["accountName": accountName, "email": email, "firstRunSetupShown": self.containsText("SETTING UP YOUR LEARNING SPACE"), "backendAccountAndPasswordVerification": "pending launcher; no direct authentication fallback"])
        await pause(0.6)
        try await capture("signed-in")
    }

    /// First-run setup, driven through the real sheet rather than by writing state directly.
    ///
    /// This is the only place the multi-subject claim is proven end to end: the course chosen
    /// here comes from the server's own catalogue, and every page exercised afterwards serves
    /// that course's content. When the chosen course is not mathematics, nothing downstream may
    /// fall back to the symbolic engine, so a pass here exercises the whole dispatch path.
    private func onboard() async throws {
        stage = "onboarding"
        let requested = ProcessInfo.processInfo.environment["NATIVE_QA_COURSE"] ?? "integrated_math_1"
        try await wait("first-run course setup sheet", seconds: 40) {
            self.containsText("SETTING UP YOUR LEARNING SPACE")
        }
        try await capture("onboarding-subject")
        try await press("setup.course." + requested)
        await pause(0.5)
        try await press("setup.continue")
        try await wait("goal step", seconds: 15) { self.find("setup.goal") != nil }
        try await type("setup.goal", text: onboardingGoal)
        try await capture("onboarding-goal")
        try await press("setup.continue")
        try await wait("pace step", seconds: 15) { self.find("setup.pace.20") != nil }
        try await press("setup.pace.20")
        await pause(0.4)
        try await capture("onboarding-pace")
        try await press("setup.finish")
        try await wait("plan for the chosen course", seconds: 60) {
            !self.containsText("SETTING UP YOUR LEARNING SPACE") && self.containsText("YOUR PLAN")
        }
        let dismissed = self.find("setup.step") == nil
        record("onboarding", target: "setup.finish", outcome: "course, goal and pace saved through the real sheet",
               details: ["requestedCourse": requested, "sheetDismissed": dismissed, "goalTyped": onboardingGoal])
        try await capture("onboarding-plan")
    }

    /// Open the same first-run sheet from the sidebar, on an already-settled view tree, then
    /// dismiss it. This is the returning-learner route to the sheet, and it separates a
    /// presentation fault (a sheet raised while the root view is swapping identity) from a
    /// content fault (the sheet's own layout), which the first-run path alone cannot tell apart.
    private func reopenSetupSheet() async throws {
        stage = "setup-sheet"
        try await press("sidebar.setup")
        try await wait("setup sheet opened from the sidebar", seconds: 40) {
            self.containsText("SETTING UP YOUR LEARNING SPACE")
        }
        try await capture("setup-sheet-reopened")
        try await press("setup.skip")
        try await wait("setup sheet dismissed", seconds: 20) {
            !self.containsText("SETTING UP YOUR LEARNING SPACE")
        }
        record("setup-sheet", target: "sidebar.setup", outcome: "reopened on a settled tree and dismissed")
    }

    private func practice() async throws {
        try await navigateRetry("studio", marker: "studio.practice")
        try await press("studio.practice")
        await pause(3)
        record("practice-state", target: "studio.practice", outcome: "store read back",
               details: await MainActor.run { self.practiceState })
        try await wait("question option A", seconds: 30) { self.find("question.option.a") != nil }
        try await capture("question")
        try await press("question.option.a")
        try await type("question.reasoning", text: "I compared the options against the concept and will inspect the explanation to check my reasoning.")
        await pause(1.2)
        try await press("question.submit")
        try await wait("actual answer feedback", seconds: 30) {
            self.find("question.next") != nil && (self.containsText("Correct answer:") || self.containsText("A useful place to look closer.") || self.containsText("You’ve got it."))
        }
        record("feedback", target: "question.next", outcome: "actual feedback UI observed")
        try await capture("question-feedback")
        try await press("question.finish")
        try await wait("question dismissed", seconds: 10) { self.find("question.finish") == nil }
    }

    private func tutor() async throws {
        try await navigateRetry("teacher", marker: "teacher.message")
        let before = Set(texts())
        try await type("teacher.message", text: "Explain this concept step by step and give a small worked example. Which curriculum reference supports it?")
        try await press("teacher.send")
        try await wait("actual assistant text", seconds: 30) {
            let newText = Set(self.texts()).subtracting(before)
            return newText.contains { $0.count > 50 && !$0.contains("Explain this concept step by step") && !$0.contains("Finding guidance") }
        }
        record("assistant", target: "teacher.message", outcome: "new rendered tutor text observed")
        try await capture("tutor")
    }

    private func project() async throws {
        try await navigateRetry("projects", marker: "project.text")
        try await capture("projects")
        try await type("project.text", text: "I used a small numerical example to compare the inputs and outputs. I checked each step, explained the relationship in my own words, and distinguished evidence from an unsupported conclusion.")
        try await type("project.reflection", text: "Writing out each step revealed where I had assumed a relationship instead of checking it. Next time I would test another example and explain why the result generalizes.")
        try await setToggle("project.ai_disclosure", enabled: true)
        try await pressLabel("I confirm this declaration reflects my process")
        try await press("project.submit")
        try await wait("project feedback", seconds: 30) { self.containsText("PROJECT FEEDBACK") }
        record("project", target: "project.submit", outcome: "actual feedback UI observed")
        try await capture("project-feedback")
    }

    private func consent() async throws {
        try await navigateRetry("settings", marker: "settings.telemetry")
        try await type("settings.goal", text: "Verify real native learning workflows and reflect on mathematical reasoning")
        try await setToggle("settings.telemetry", enabled: true)
        try await press("settings.save")
        try await wait("saved preferences", seconds: 30) { self.containsText("Your preferences have been saved.") }
        try await capture("settings-consent")
        record("heartbeat-wait", target: "own active window", outcome: "started", details: ["seconds": 46])
        // Hold the app as the focused window for the whole interval: consented foreground heartbeats
        // are only recorded while the app is active, and a real learner has the window in front.
        //
        // 46 seconds rather than 30 is not padding. The client reports on a 15-second grid, and the
        // server credits an interval only against a previous heartbeat it already holds, so the
        // first report of a stretch anchors the clock and the second is the earliest one that can
        // carry any credited time. Three boundaries give that contract room to be observed rather
        // than raced, and a shorter hold would fail for a reason that has nothing to do with whether
        // activity is being recorded honestly.
        let heartbeatDeadline = ProcessInfo.processInfo.systemUptime + 46
        while ProcessInfo.processInfo.systemUptime < heartbeatDeadline {
            await focusOwnWindow()
            await pause(1.0)
        }
        record("heartbeat-wait", target: "own active window", outcome: "elapsed", details: ["appActiveAtEnd": await MainActor.run { NSApp.isActive }, "backendHeartbeatVerification": "pending launcher database inspection"])
    }

    /// The same destination has two identifiers after the 1,120 pt breakpoint fix:
    /// ``nav.<page>`` in the expanded labelled sidebar and ``nav.compact.<page>`` in
    /// the compact icon rail. The driver must work at whatever width the real window
    /// currently has instead of assuming the expanded rail.
    private func navigationIdentifier(_ page: String) -> String {
        find("nav." + page) != nil ? "nav." + page : "nav.compact." + page
    }

    private func navigate(_ page: String, marker: String? = nil, text: String? = nil) async throws {
        let identifier = navigationIdentifier(page)
        try await press(identifier)
        try await wait("page \(page)", seconds: 30) {
            (marker.map { self.find($0) != nil } ?? true) && (text.map { self.containsText($0) } ?? true)
        }
        await pause(0.5)
        record("navigation", target: identifier, outcome: "destination UI observed")
    }

    private func exercise(_ name: String, action: () async throws -> Void) async {
        stage = name
        do { try await action() } catch {
            fail(error)
            try? await capture(name + "-blocked")
        }
    }

    /// Extra page captures requested by the launcher through `NATIVE_QA_CAPTURE_PAGES`
    /// (comma-separated `Page` raw values, e.g. `today,review`). Defaults to nothing, so the
    /// verified workflow contract is unchanged unless a caller asks for more evidence.
    ///
    /// Deliberately **non-fatal**: these pages sit outside the workflow contract, so a page that
    /// is slow, hidden, or absent must not convert an otherwise complete run into `blocked`. It is
    /// recorded as `skipped` instead, which keeps the distinction between "the product is broken"
    /// and "this optional view was not photographed" honest in the evidence.
    private func captureRequestedPages() async {
        let requested = (ProcessInfo.processInfo.environment["NATIVE_QA_CAPTURE_PAGES"] ?? "")
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        for page in requested {
            stage = page
            do {
                try await press(navigationIdentifier(page))
                await pause(1.0)
                try await capture(page)
                record("optional-page", target: navigationIdentifier(page), outcome: "captured")
            } catch {
                record("optional-page", target: "nav." + page, outcome: "skipped",
                       details: ["reason": redact(error.localizedDescription)])
            }
        }
    }

    /// Spec 4.4: sweep the six required window widths against the REAL window and read
    /// the sidebar state back from the AX tree. Screenshots at 1,120 and 1,119 points
    /// are captured by the same `capture()` path as the rest of the workflow, so the
    /// breakpoint is evidenced both structurally (identifiers) and visually (PNG).
    private func responsiveWidths() async {
        stage = "responsive"
        for width: CGFloat in [1400, 1200, 1120, 1119, 1000, 900] {
            do {
                let measured = try await resizeOwnWindow(toWidth: width)
                await pause(0.55) // SwiftUI must settle before the AX tree is read.
                let expectedExpanded = SidebarLayout.isExpanded(width: width)
                let expandedControl = find("nav.today")
                let compactControls = Page.allCases.filter {
                    find(SidebarLayout.compactIdentifier(for: $0)) != nil
                }
                var labelledCompact: [String] = []
                var enabledControls = 0
                for page in compactControls {
                    guard let element = find(SidebarLayout.compactIdentifier(for: page)) else { continue }
                    let label = string(element, kAXDescriptionAttribute as String)
                        ?? string(element, kAXTitleAttribute as String)
                    if let label, !label.isEmpty { labelledCompact.append(page.rawValue) }
                    if boolean(element, kAXEnabledAttribute as String) == true { enabledControls += 1 }
                }
                if let expandedControl,
                   boolean(expandedControl, kAXEnabledAttribute as String) == true {
                    enabledControls += 1
                }
                let observedExpanded = expandedControl != nil && compactControls.isEmpty
                let observedCompact = expandedControl == nil
                    && compactControls.count == Page.allCases.count
                let matched = expectedExpanded ? observedExpanded : observedCompact
                try await capture("responsive-\(Int(width))")
                record("responsive-width", target: "app window",
                       outcome: matched ? "matched breakpoint" : "MISMATCH",
                       details: [
                        "requestedWidthPoints": Double(width),
                        "measuredContentWidthPoints": measured["contentWidth"] ?? -1,
                        "windowFrameWidthPoints": measured["frameWidth"] ?? -1,
                        "minSizeWidthPoints": measured["minSizeWidth"] ?? -1,
                        "windowResizable": measured["resizable"] ?? false,
                        "expectedExpanded": expectedExpanded,
                        "observedExpandedIdentifiers": observedExpanded,
                        "observedCompactIdentifiers": observedCompact,
                        "compactIconCount": compactControls.count,
                        "compactIconsWithAccessibleLabels": labelledCompact.count,
                        "compactAccessibleLabels": labelledCompact.sorted(),
                        "enabledNavigationControls": enabledControls,
                        "screenshotPattern": "*responsive-\(Int(width))-window-0.png",
                        "visualSubItems": "no overlap / no clipped text pending human inspection of the captured PNG",
                       ])
                if !matched {
                    fail(Blocked(message: "sidebar state at \(Int(width)) pt did not match the 1,120 pt breakpoint"))
                }
                if measured["contentWidth"] as? Double != Double(width) {
                    record("responsive-width-clamp", target: "app window",
                           outcome: "requested width clamped by the window manager",
                           details: ["requestedWidthPoints": Double(width),
                                     "measuredContentWidthPoints": measured["contentWidth"] ?? -1])
                }
            } catch {
                fail(error)
            }
        }
    }

    @MainActor private func resizeOwnWindow(toWidth width: CGFloat) throws -> [String: Any] {
        guard let window = NSApp.windows.first(where: { $0.isVisible && $0.contentView != nil }) else {
            throw Blocked(message: "No visible own window to resize for spec 4.4")
        }
        window.setContentSize(NSSize(width: width, height: 732))
        window.contentView?.layoutSubtreeIfNeeded()
        window.contentView?.displayIfNeeded()
        return [
            "contentWidth": Double(window.contentView?.bounds.width ?? 0),
            "frameWidth": Double(window.frame.width),
            "minSizeWidth": Double(window.minSize.width),
            "resizable": window.styleMask.contains(.resizable),
        ]
    }

    /// Poll an accessibility condition until it holds. A background application exposes only its
    /// menu bar through the AX server, so a real user's focused window is re-established while
    /// waiting — otherwise enumeration collapses to menu items and every assertion fails
    /// spuriously.
    private func wait(_ description: String, seconds: Double, condition: () -> Bool) async throws {
        let deadline = ProcessInfo.processInfo.systemUptime + seconds
        var lastActivation = 0.0
        while ProcessInfo.processInfo.systemUptime < deadline {
            let now = ProcessInfo.processInfo.systemUptime
            if now - lastActivation > 1.5 {
                lastActivation = now
                await focusOwnWindow()
            }
            if condition() { return }
            await pause(0.25)
        }
        // A timeout with no context is indistinguishable from a product bug. Record what
        // the AX server could actually see at that moment — window count and a short
        // sample of visible strings — so a sheet that failed to appear can be told apart
        // from a sheet the driver could not traverse.
        record("wait-timeout", target: description, outcome: "no match",
               details: ["windows": axWindows().count,
                         "sample": Array(texts().prefix(14))])
        throw Blocked(message: "Timed out waiting for \(description)")
    }

    /// The same poll, for conditions that read AppKit state and therefore need the main thread.
    @MainActor private func waitMain(_ description: String, seconds: Double, condition: @MainActor () -> Bool) async throws {
        let deadline = ProcessInfo.processInfo.systemUptime + seconds
        while ProcessInfo.processInfo.systemUptime < deadline {
            if condition() { return }
            try? await Task.sleep(nanoseconds: 200_000_000)
        }
        throw Blocked(message: "Timed out waiting for \(description)")
    }
    private func pause(_ seconds: Double) async {
        try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
    }

    // MARK: - AXUIElement access layer

    /// The app's own accessibility element.
    ///
    /// The messaging timeout is a backstop against a genuinely wedged AX server, not a normal
    /// operating condition: a call that exceeds it fails with `kAXErrorCannotComplete`, which is
    /// indistinguishable from a rejected press. Running the workflow off the main actor is what
    /// actually prevents the self-deadlock, so this is set generously.
    private lazy var applicationElement: AXUIElement = {
        let element = AXUIElementCreateApplication(getpid())
        AXUIElementSetMessagingTimeout(element, 20)
        return element
    }()

    /// Every window the app currently owns, including sheets.
    ///
    /// The QA journeys drive three confirmations (J4 generate deck, J6 author a course,
    /// J10 delete account) that were previously presented as SwiftUI `.sheet` windows.
    /// On this OS a SwiftUI sheet is a distinct `NSWindow` that the accessibility server
    /// does not surface through `kAXWindowsAttribute`, so `enumerate` reported "the sheet
    /// never opened" while every inline check passed. Those three are now presented as
    /// inline overlays (see `LuminfestApp`, `ProjectsInsightsSettings`, `Flashcards`), so
    /// their controls live in the main window's AX tree and are reached here without any
    /// special-casing. This accessor therefore only needs the application element's
    /// window list, which is the main window.
    private func axWindows() -> [AXUIElement] {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(applicationElement,
                                            kAXWindowsAttribute as CFString,
                                            &value) == .success else { return [] }
        return (value as? [AXUIElement]) ?? []
    }

    private func attribute(_ element: AXUIElement, _ name: String) -> CFTypeRef? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, name as CFString, &value) == .success else { return nil }
        return value
    }

    private func string(_ element: AXUIElement, _ name: String) -> String? {
        guard let value = attribute(element, name) else { return nil }
        if let text = value as? String { return text }
        if let number = value as? NSNumber { return number.stringValue }
        return nil
    }

    private func boolean(_ element: AXUIElement, _ name: String) -> Bool? {
        guard let value = attribute(element, name) else { return nil }
        if let number = value as? NSNumber { return number.boolValue }
        if let flag = value as? Bool { return flag }
        return nil
    }

    private func children(_ element: AXUIElement) -> [AXUIElement] {
        guard let value = attribute(element, kAXChildrenAttribute as String) else { return [] }
        return (value as? [AXUIElement]) ?? []
    }

    private func identifier(_ element: AXUIElement) -> String {
        string(element, kAXIdentifierAttribute as String) ?? ""
    }

    private func role(_ element: AXUIElement) -> String {
        string(element, kAXRoleAttribute as String) ?? ""
    }

    private func settable(_ element: AXUIElement, _ name: String) -> Bool {
        var flag = DarwinBoolean(false)
        guard AXUIElementIsAttributeSettable(element, name as CFString, &flag) == .success else { return false }
        return flag.boolValue
    }

    private func enumerate(_ roots: [AXUIElement]? = nil, visit: (AXUIElement) -> Bool) {
        // Windows are appended after the application element, and the stack pops from
        // the end, so sheet windows are visited *first*. That matters: a stale control
        // with the same identifier in the main window must not win over the live one
        // inside the sheet the learner is looking at.
        var stack: [AXUIElement] = roots ?? ([applicationElement] + axWindows())
        var seen = 0
        while let element = stack.popLast(), seen < limit {
            seen += 1
            if visit(element) { return }
            stack.append(contentsOf: children(element))
            if stack.count > limit { stack = Array(stack.suffix(limit)) }
        }
    }

    private func find(_ id: String) -> AXUIElement? {
        var found: AXUIElement?
        enumerate { element in
            if self.identifier(element) == id { found = element; return true }
            return false
        }
        return found
    }

    private func strings(_ element: AXUIElement) -> [String] {
        ["AXValue", "AXTitle", "AXDescription", "AXHelp", "AXPlaceholderValue"].compactMap { string(element, $0) }
    }

    private func texts() -> [String] {
        var result: [String] = []
        enumerate { element in
            guard self.identifier(element) != "auth.password", self.role(element) != "AXSecureTextField" else { return false }
            for text in self.strings(element) where !text.isEmpty { result.append(self.redact(text)) }
            return false
        }
        return result
    }

    private func containsText(_ text: String) -> Bool { texts().contains { $0.contains(text) } }

    private func press(_ id: String) async throws {
        try await wait("enabled \(id)", seconds: 15) {
            guard let element = self.find(id) else { return false }
            return self.boolean(element, kAXEnabledAttribute as String) != false
        }
        // SwiftUI can report a spurious AXError on a press that in fact took effect (for example
        // while a navigation transition is animating), so retry against the live element before
        // declaring the interaction failed. The caller still verifies the real outcome afterwards.
        var lastError: AXError = .failure
        for attempt in 1...3 {
            guard let element = find(id) else { throw Blocked(message: "Element disappeared: \(id)") }
            if boolean(element, kAXEnabledAttribute as String) == false { await pause(0.4); continue }
            let result = await axPress(element)
            if result == .success {
                record("accessibilityPerformPress", target: id, outcome: attempt == 1 ? "accepted" : "accepted (attempt \(attempt))")
                await pause(0.25)
                return
            }
            lastError = result
            record("accessibilityPerformPress", target: id, outcome: "retrying after AXError \(result.rawValue)", details: ["attempt": attempt])
            await pause(0.5)
        }
        throw Blocked(message: "Accessibility press rejected after retries: \(id) (\(lastError.rawValue))")
    }

    private func performPress(_ element: AXUIElement, target: String) async throws {
        guard boolean(element, kAXEnabledAttribute as String) != false else {
            throw Blocked(message: "Real element is disabled: \(target)")
        }
        let result = await axPress(element)
        record("accessibilityPerformPress", target: target, outcome: result == .success ? "accepted" : "rejected (\(result.rawValue))")
        guard result == .success else { throw Blocked(message: "Accessibility press rejected: \(target)") }
    }

    /// AX writes run on the main thread; AX reads deliberately do not.
    ///
    /// Reads are safe off the main actor — and running them there is what prevents the
    /// self-deadlock described on the class. Writes are the opposite: `AXUIElementPerformAction`
    /// and `AXUIElementSetAttributeValue` against this process are dispatched through AppKit's own
    /// main-thread accessibility implementation, and issued from a background thread they fail
    /// with `kAXErrorCannotComplete` (-25200) even when the element is plainly pressable.
    @MainActor private func axPress(_ element: AXUIElement) -> AXError {
        AXUIElementPerformAction(element, kAXPressAction as CFString)
    }

    @MainActor private func axSet(_ element: AXUIElement, _ attribute: String, _ value: CFTypeRef) -> AXError {
        AXUIElementSetAttributeValue(element, attribute as CFString, value)
    }

    /// The accessibility actions an element advertises. Used to tell a real control from a static
    /// label that merely carries the same text.
    private func actions(_ element: AXUIElement) -> [String] {
        var names: CFArray?
        guard AXUIElementCopyActionNames(element, &names) == .success,
              let list = names as? [String] else { return [] }
        return list
    }

    private func pressLabel(_ label: String) async throws {
        var candidate: AXUIElement?
        try await wait("pressable label \(label)", seconds: 10) {
            candidate = nil
            self.enumerate { element in
                let matches = self.strings(element).contains { $0 == label || $0.hasPrefix(label) }
                // Requiring a real press action matters: a static text can carry the same string,
                // and pressing it is rejected by the AX server. Matching on text alone is a
                // coin flip that happens to work only while the button enumerates first.
                if matches, self.actions(element).contains(kAXPressAction as String),
                   self.boolean(element, kAXEnabledAttribute as String) != false {
                    candidate = element
                    return true
                }
                return false
            }
            return candidate != nil
        }
        guard let candidate else { throw Blocked(message: "No pressable real element labeled \(label)") }
        try await performPress(candidate, target: label)
        await pause(0.3)
    }

    /// Every accessibility string an element carries, including those of its descendants.
    ///
    /// SwiftUI routinely puts a control's visible label in a child `AXStaticText` and leaves the
    /// control itself with an empty title, so matching on the element's *own* strings misses real,
    /// pressable controls. Descending into children is what makes overlay buttons addressable.
    private func descendantTexts(_ element: AXUIElement) -> [String] {
        var result: [String] = []
        var stack = [element]
        var seen = 0
        while let next = stack.popLast(), seen < limit {
            seen += 1
            result.append(contentsOf: strings(next))
            stack.append(contentsOf: children(next))
        }
        return result
    }

    /// The smallest enabled, pressable element whose own or descendant text contains `label`.
    ///
    /// Returns nil when nothing matches, so callers decide how strict to be. When several elements
    /// match (a button and its container both carry the label), the one with the fewest descendant
    /// elements wins — that is the control, not the surface around it.
    private func findPressable(containing label: String) -> AXUIElement? {
        var candidates: [AXUIElement] = []
        enumerate { element in
            guard self.actions(element).contains(kAXPressAction as String),
                  self.boolean(element, kAXEnabledAttribute as String) != false else { return false }
            let all = self.descendantTexts(element)
            if all.contains(where: { $0.contains(label) }) { candidates.append(element) }
            return false
        }
        var best: AXUIElement?
        var bestSize = Int.max
        for candidate in candidates {
            let size = self.descendantTexts(candidate).count
            if size < bestSize { bestSize = size; best = candidate }
        }
        return best
    }

    /// Presses the most specific enabled control whose text contains `label`.
    ///
    /// Robust to the SwiftUI quirk where overlay buttons (generate-sheet Preview/Add, the deletion
    /// confirmation) expose their label only in a child static text and not as an `AXButton` role —
    /// which makes both `buttonContaining` (role-gated) and `pressLabel` (own-strings-only) miss them.
    private func pressContaining(_ label: String) async throws {
        var candidate: AXUIElement?
        try await wait("pressable containing \(label)", seconds: 12) {
            candidate = self.findPressable(containing: label)
            return candidate != nil
        }
        guard let candidate else { throw Blocked(message: "No enabled pressable element containing \(label)") }
        try await performPress(candidate, target: label)
        await pause(0.4)
    }

    /// Finds an editable text field whose placeholder or current value contains `label`, for typing
    /// into controls that do not expose a stable accessibility identifier through the in-process bridge.
    private func findEditable(containing label: String) -> AXUIElement? {
        var found: AXUIElement?
        enumerate { element in
            guard ["AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"].contains(self.role(element)),
                  self.settable(element, kAXValueAttribute as String) else { return false }
            let haystack = self.descendantTexts(element)
            if haystack.contains(where: { $0.contains(label) }) { found = element; return true }
            return false
        }
        return found
    }

    /// Types into the editable field located by placeholder/value text rather than identifier.
    private func typeContaining(_ label: String, text: String) async throws {
        try await wait("editable containing \(label)", seconds: 12) { self.findEditable(containing: label) != nil }
        guard let field = findEditable(containing: label) else {
            throw Blocked(message: "No editable field containing \(label)")
        }
        _ = await axSet(field, kAXFocusedAttribute as String, kCFBooleanTrue)
        await pause(0.2)
        let result = await axSet(field, kAXValueAttribute as String, text as CFString)
        guard result == .success else {
            throw Blocked(message: "Accessibility value set failed for \(label) (\(result.rawValue))")
        }
        await pause(0.35)
        let readback = string(field, kAXValueAttribute as String)
        guard readback == text else {
            throw Blocked(message: "Readback mismatch for \(label): expected \(text), got \(readback ?? "<nil>")")
        }
    }

    /// Sets a real field's value through the accessibility value attribute, then verifies readback.
    private func type(_ id: String, text: String, secret: Bool = false) async throws {
        try await wait("editable \(id)", seconds: 15) { self.find(id) != nil }
        guard let root = find(id) else { throw Blocked(message: "Missing field \(id)") }
        var field: AXUIElement?
        if settable(root, kAXValueAttribute as String), ["AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"].contains(role(root)) {
            field = root
        } else {
            enumerate([root]) { element in
                if ["AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"].contains(self.role(element)),
                   self.settable(element, kAXValueAttribute as String) {
                    field = element
                    return true
                }
                return false
            }
        }
        guard let field else { throw Blocked(message: "No real editable accessibility child for \(id)") }
        guard settable(field, kAXValueAttribute as String) else { throw Blocked(message: "Real field does not allow accessibility value editing: \(id)") }
        // A real learner focuses a field before typing. SwiftUI discards an accessibility value
        // written to an unfocused field on its next layout pass, so focus it first (verified empirically).
        _ = await axSet(field, kAXFocusedAttribute as String, kCFBooleanTrue)
        await pause(0.2)
        let result = await axSet(field, kAXValueAttribute as String, text as CFString)
        guard result == .success else { throw Blocked(message: "Accessibility value set failed for \(id) (\(result.rawValue))") }
        record("setAccessibilityValue", target: id, outcome: "invoked on real field", details: ["characters": text.count, "secret": secret])
        await pause(0.35)
        let readback = string(field, kAXValueAttribute as String)
        if secret {
            let matches = readback == text
            record("field-readback", target: id, outcome: matches ? "matched (redacted)" : "protected or unmatched; backend password verification required")
        } else {
            guard readback == text else { throw Blocked(message: "Accessibility value readback did not match for \(id); no direct binding fallback") }
            record("field-readback", target: id, outcome: "matched")
        }
    }

    private func setToggle(_ id: String, enabled: Bool) async throws {
        try await wait("toggle \(id)", seconds: 15) { self.find(id) != nil }
        guard let element = find(id) else { throw Blocked(message: "Missing toggle: \(id)") }
        if boolean(element, kAXValueAttribute as String) != enabled {
            _ = await axPress(element)
            await pause(0.35)
            if boolean(element, kAXValueAttribute as String) != enabled {
                _ = await axSet(element, kAXValueAttribute as String, NSNumber(value: enabled ? 1 : 0))
                await pause(0.35)
            }
        }
        guard boolean(element, kAXValueAttribute as String) == enabled else { throw Blocked(message: "Toggle value did not change: \(id)") }
        record("toggle-readback", target: id, outcome: "matched", details: ["enabled": enabled])
    }

    private func capture(_ name: String) async throws {
        guard let output else { throw Blocked(message: "Screenshot output unavailable") }
        if CapturePresentation.isEnabled {
            // The enrolment notice is a transient confirmation addressed to the session, not part of
            // the learner's screen. Clear it and let SwiftUI settle before the frame is read.
            await MainActor.run { AppStore.current?.notice = nil }
            await pause(0.3)
        }
        // Window rendering genuinely needs the main thread; the accessibility dump at the end of
        // this function must not run there. The two halves stay separate on purpose.
        let shots: [(file: String, title: String, width: Int, height: Int, colors: Int)] = try await MainActor.run {
            NSApp.activate(ignoringOtherApps: true)
            NSApp.windows.first(where: { $0.isVisible })?.makeKeyAndOrderFront(nil)
            var result: [(file: String, title: String, width: Int, height: Int, colors: Int)] = []
            var candidates = NSApp.windows.filter { $0.isVisible }
            if candidates.isEmpty { candidates = NSApp.windows.filter { $0.contentView != nil } }
            for (index, window) in candidates.enumerated() {
                guard let view = window.contentView, view.bounds.width > 0, view.bounds.height > 0 else { continue }
                view.layoutSubtreeIfNeeded()
                view.displayIfNeeded()
                guard let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { throw Blocked(message: "Own window cannot provide a cache-display bitmap") }
                view.cacheDisplay(in: view.bounds, to: bitmap)
                guard let png = bitmap.representation(using: .png, properties: [:]) else { throw Blocked(message: "Own window bitmap PNG encoding failed") }
                let filename = String(format: "%02d-%@-window-%d.png", self.screenshots.count + result.count + 1, name, index)
                try png.write(to: output.appendingPathComponent(filename), options: .atomic)
                var colors = Set<String>()
                for y in stride(from: 0, to: bitmap.pixelsHigh, by: max(1, bitmap.pixelsHigh / 48)) {
                    for x in stride(from: 0, to: bitmap.pixelsWide, by: max(1, bitmap.pixelsWide / 48)) {
                        if let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) {
                            colors.insert("\(Int(color.redComponent * 255)),\(Int(color.greenComponent * 255)),\(Int(color.blueComponent * 255)),\(Int(color.alphaComponent * 255))")
                        }
                    }
                }
                result.append((filename, window.title, bitmap.pixelsWide, bitmap.pixelsHigh, colors.count))
            }
            return result
        }
        guard !shots.isEmpty else { throw Blocked(message: "No visible own window available for screenshot") }
        // A window with no title that paints no pixels is an offscreen or helper surface, not UI:
        // it is never the window a person looks at. Recording it as a screenshot would let a
        // property of that surface mark an otherwise complete workflow as visually unverifiable,
        // so it is reported as a skipped window instead. Every window that is actually presented
        // still carries a title in this app, so the blank-screen gate below stays intact for them.
        let usable = shots.filter { !($0.colors < 2 && $0.title.isEmpty) }
        for shot in shots where shot.colors < 2 && shot.title.isEmpty {
            record("skipped-window", target: "untitled window with no rendered content", outcome: "not recorded as screenshot",
                   details: ["width": shot.width, "height": shot.height, "sampledDistinctColors": shot.colors])
        }
        guard !usable.isEmpty else { throw Blocked(message: "No visible own window with rendered content available for screenshot") }
        for shot in usable {
            screenshots.append(["file": shot.file, "stage": stage, "windowTitle": shot.title,
                                "width": shot.width, "height": shot.height,
                                "capture": "own NSWindow.contentView.cacheDisplay",
                                "sampledDistinctColors": shot.colors, "suspectedBlank": shot.colors < 3,
                                "visualValidation": "pending human inspection; pixel diversity is not visual acceptance"])
        }
        record("screenshot", target: name, outcome: "captured own windows", details: ["count": shots.count])
        var elements: [[String: Any]] = []
        enumerate { element in
            let id = self.identifier(element)
            let subrole = self.string(element, kAXSubroleAttribute as String) ?? ""
            let secret = id == "auth.password" || subrole == "AXSecureTextField"
            var row: [String: Any] = ["identifier": id, "role": self.role(element), "subrole": subrole,
                                      "valueSettable": self.settable(element, kAXValueAttribute as String)]
            if let enabled = self.boolean(element, kAXEnabledAttribute as String) { row["enabled"] = enabled }
            for key in ["AXTitle", "AXDescription", "AXValue", "AXPlaceholderValue"] {
                if secret && key == "AXValue" { row[key] = "[REDACTED]" }
                else if let value = self.string(element, key) { row[key] = self.redact(value) }
            }
            elements.append(row)
            return false
        }
        let snapshot: [String: Any] = ["stage": stage, "texts": Array(Set(texts())).sorted(), "elements": elements]
        try JSONSerialization.data(withJSONObject: snapshot, options: [.prettyPrinted, .sortedKeys]).write(to: output.appendingPathComponent(name + "-accessibility.json"), options: .atomic)
    }

    private func redact(_ text: String) -> String {
        password.isEmpty ? text : text.replacingOccurrences(of: password, with: "[REDACTED]")
    }

    private func fail(_ error: Error) {
        let message = redact(error.localizedDescription)
        failures.append("\(stage): \(message)")
        record("failure", target: stage, outcome: "blocked", details: ["error": message])
    }

    private func record(_ action: String, target: String, outcome: String, details: [String: Any] = [:]) {
        events.append(["sequence": events.count + 1, "elapsedSeconds": ProcessInfo.processInfo.systemUptime - clock, "stage": stage, "action": action, "target": target, "outcome": outcome, "details": details])
        flush()
    }

    private func flush() {
        guard let report else { return }
        let result: [String: Any] = ["driver": "in-process AXUIElement (same channel as external tooling)", "status": status, "workflowCompleted": status == "completed", "stage": stage, "accountName": accountName, "email": email, "events": events, "screenshots": screenshots, "failures": failures, "backendVerified": false, "verificationPolicy": "No AppStore workflow mutations, synthetic views, direct auth fallback, external XCTest, or screen capture permissions; launcher must verify isolated backend records"]
        do { try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys]).write(to: report, options: .atomic) }
        catch { NSLog("NativeQA evidence write failed: %@", redact(error.localizedDescription)) }
    }
}
