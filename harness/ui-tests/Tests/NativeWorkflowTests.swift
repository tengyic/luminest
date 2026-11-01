import XCTest
import Foundation

@MainActor
final class NativeWorkflowTests: XCTestCase {
    private var app: XCUIApplication!
    private var output: URL!
    private var events: [[String: String]] = []
    private var screenshotNumber = 0
    private var workflowCompleted = false
    private let email = "ui-\(UUID().uuidString.lowercased())@example.com"
    private let password = "Luminfest-Native-UI!2026-Strong"
    private let goal = "Understand fractions through real native practice"

    override func setUpWithError() throws {
        continueAfterFailure = false
        let environment = ProcessInfo.processInfo.environment
        output = URL(fileURLWithPath: environment["HARNESS_UI_OUTPUT"] ?? RunnerConfiguration.output)
        let startup = ["output": output.path, "configuration": environment["XCTestConfigurationFilePath"] ?? "not supplied", "bundle": Bundle.main.bundlePath]
        try JSONSerialization.data(withJSONObject: startup, options: [.prettyPrinted]).write(to: output.appendingPathComponent("runner-startup.json"), options: .atomic)
        var directory: ObjCBool = false
        XCTAssertTrue(FileManager.default.fileExists(atPath: output.path, isDirectory: &directory) && directory.boolValue,
                      "The launcher must verify and create outputs/ui before XCTest starts")
        app = XCUIApplication()
        app.launchArguments = ["--ui-test"]
        app.launch()
        record("I launched the native macOS application with --ui-test.")
        try capture("native-launch")
    }

    override func tearDownWithError() throws {
        if app != nil, app.state == .runningForeground || app.state == .runningBackground {
            try capture("final-state")
            app.terminate()
        }
        try writeEvents()
    }

    private func record(_ action: String, observed: String = "") {
        events.append(["time": ISO8601DateFormatter().string(from: Date()), "action": action, "observed": observed])
        try? writeEvents()
    }

    private func writeEvents() throws {
        guard output != nil else { return }
        let evidence: [String: Any] = ["accountEmail": email, "driver": "native macOS XCTest / XCUIApplication",
                                       "events": events, "workflowCompleted": workflowCompleted]
        try JSONSerialization.data(withJSONObject: evidence, options: [.prettyPrinted, .sortedKeys])
            .write(to: output.appendingPathComponent("workflow-events.json"), options: .atomic)
    }

    private func element(_ identifier: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: identifier).firstMatch
    }

    private func wait(_ target: XCUIElement, _ description: String, timeout: TimeInterval = 25) throws {
        guard target.waitForExistence(timeout: timeout) else {
            record("I could not find \(description).", observed: "XCTest existence wait failed")
            try capture("missing-element")
            XCTFail("Missing native element: \(description). See exported screenshot and AX tree.")
            throw NSError(domain: "NativeWorkflow", code: 1)
        }
    }

    private func reveal(_ target: XCUIElement) throws {
        if target.isHittable { return }
        let sheetScroll = app.sheets.firstMatch.scrollViews.firstMatch
        let scroll = sheetScroll.exists ? sheetScroll : app.scrollViews.firstMatch
        for _ in 0..<9 {
            if target.isHittable { return }
            if scroll.exists { scroll.scroll(byDeltaX: 0, deltaY: -450) }
        }
        XCTAssertTrue(target.isHittable, "Native element is not hittable: \(target.identifier)")
    }

    private func click(_ identifier: String) throws {
        let target = element(identifier)
        try wait(target, identifier)
        try reveal(target)
        XCTAssertTrue(target.isEnabled, "Native element is disabled: \(identifier)")
        target.click()
    }

    private func fill(_ identifier: String, _ text: String) throws {
        let target: XCUIElement
        if app.secureTextFields[identifier].exists { target = app.secureTextFields[identifier] }
        else if app.textViews[identifier].exists { target = app.textViews[identifier] }
        else if app.textFields[identifier].exists { target = app.textFields[identifier] }
        else { target = element(identifier) }
        try wait(target, identifier)
        try reveal(target)
        target.click()
        target.typeKey("a", modifierFlags: .command)
        target.typeText(text)
    }

    private func textContaining(_ text: String) -> XCUIElement {
        app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] %@", text)).firstMatch
    }

    private func navigate(_ page: String) throws {
        try click("nav." + page)
        record("I opened the \(page) page using its native sidebar button.")
    }

    private func capture(_ name: String) throws {
        screenshotNumber += 1
        let basename = String(format: "%02d-%@", screenshotNumber, name)
        let screenshot = app.screenshot()
        let attachment = XCTAttachment(screenshot: screenshot)
        attachment.name = basename
        attachment.lifetime = .keepAlways
        add(attachment)
        try screenshot.pngRepresentation.write(to: output.appendingPathComponent(basename + ".png"), options: .atomic)
        try app.debugDescription.write(to: output.appendingPathComponent(basename + "-ax.txt"), atomically: true, encoding: .utf8)
    }

    private func submitVisibleOption(_ mode: String) throws {
        let options = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "question.option."))
        try wait(options.firstMatch, "a visible \(mode) answer option")
        let choice = options.firstMatch
        let label = choice.label
        choice.click()
        record("I selected an available \(mode) answer option.", observed: "\(choice.identifier): \(label). This is a flow test, not a claim of mathematical correctness; no hidden answer or server oracle was read.")
        try click("question.submit")
        try wait(element("question.next"), "real backend feedback and Next question", timeout: 35)
        let feedback = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Correct answer:")).firstMatch
        try wait(feedback, "the real evaluated answer feedback")
        try reveal(feedback)
        record("I submitted my \(mode) answer and saw evaluated feedback.", observed: feedback.label)
        try capture(mode + "-feedback")
    }

    func testNativeLearnerWorkflow() throws {
        try wait(element("auth.name"), "registration form")
        try fill("auth.name", "Test Learner")
        try fill("auth.email", email)
        try fill("auth.password", password)
        if !element("auth.endpoint").isHittable {
            let disclosure = app.disclosureTriangles.firstMatch
            if disclosure.exists { disclosure.click() }
            else { try wait(textContaining("Local learning server"), "server disclosure"); textContaining("Local learning server").click() }
        }
        try fill("auth.endpoint", ProcessInfo.processInfo.environment["HARNESS_UI_ENDPOINT"] ?? RunnerConfiguration.endpoint)
        try capture("registration")
        try click("auth.register")
        try wait(element("nav.today"), "authenticated Today sidebar", timeout: 40)
        try wait(textContaining("Backend connected"), "connected backend status")
        record("I registered Test Learner with a new process UUID email and a strong password.", observed: "Authenticated dashboard and Backend connected are visible; no account or progress was injected.")
        try capture("new-dashboard")

        try navigate("settings")
        try fill("settings.goal", goal)
        let stepper = element("settings.minutes")
        try wait(stepper, "daily minutes stepper")
        let increment = stepper.incrementArrows.firstMatch
        if increment.exists { increment.click() }
        else {
            stepper.click()
            stepper.typeKey(XCUIKeyboardKey.upArrow.rawValue, modifierFlags: [])
        }
        try wait(textContaining("25 minutes"), "daily goal changed from 20 to 25 minutes")
        try click("settings.telemetry")
        try click("settings.save")
        try wait(textContaining("Your preferences have been saved."), "saved preferences")
        record("I changed my learning goal, increased the daily time to 25 minutes, explicitly enabled activity consent, and saved.", observed: "Your preferences have been saved.")
        try capture("saved-settings")

        try navigate("today")
        try click("diagnostic.start")
        try submitVisibleOption("diagnostic")
        try click("question.finish")
        try wait(element("nav.today"), "dashboard after finishing partial diagnostic")
        record("I finished after one diagnostic answer.", observed: "I did not complete all 15 diagnostic questions or claim diagnostic completion.")

        try navigate("studio")
        try wait(element("studio.practice"), "native studio practice button")
        try click("studio.practice")
        try submitVisibleOption("practice")
        try click("question.next")
        try wait(element("question.submit"), "next real practice question")
        try submitVisibleOption("practice-next")
        try click("question.finish")
        record("I answered two real practice questions, used Next question, and finished the session.")

        let slider = app.sliders.matching(NSPredicate(format: "identifier BEGINSWITH %@", "simulation.")).firstMatch
        try wait(slider, "native simulation slider")
        try reveal(slider)
        let before = String(describing: slider.value)
        slider.adjust(toNormalizedSliderPosition: 0.75)
        let after = String(describing: slider.value)
        XCTAssertNotEqual(before, after, "The actual native slider value must change")
        record("I adjusted the native studio slider to 75% of its range.", observed: "AX value changed from \(before) to \(after); local exploration is not a graded attempt.")
        let prediction = app.textFields.matching(NSPredicate(format: "placeholderValue BEGINSWITH %@", "Predicted")).firstMatch
        try wait(prediction, "simulation prediction field")
        try reveal(prediction)
        prediction.click()
        prediction.typeText("0")
        try click("simulation.check")
        let checkResult = app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] %@ OR label CONTAINS[c] %@", "current model", "prediction matches")).firstMatch
        try wait(checkResult, "native simulation model feedback")
        record("I entered a prediction and pressed the native simulation Check button.", observed: checkResult.label)
        try capture("studio-simulation")

        try navigate("teacher")
        try fill("teacher.message", "Why do fractions need a common denominator? Please explain with one example.")
        try click("teacher.send")
        try wait(app.staticTexts["GROUNDED TUTOR"].firstMatch, "real grounded tutor response", timeout: 40)
        record("I asked the teacher about common denominators and saw a grounded tutor response.", observed: "The native UI identifies this as offline curriculum guidance, not a live AI provider.")
        try capture("teacher-response")

        try navigate("projects")
        try fill("project.text", "For two servings I use 1/2 cup of rice and 1/4 cup of sauce. Scaling to five servings multiplies each amount by 5/2: rice is 5/4 cups and sauce is 5/8 cup. I verify the scale factor by dividing five servings by two. Both ingredients preserve the original ratio.")
        try fill("project.reflection", "I checked the common whole and multiplied numerator and denominator carefully. I would verify each ingredient with a diagram next time. This test submission was written with AI assistance, which I disclose explicitly.")
        try click("project.ai_disclosure")
        let declaration = app.checkBoxes["I confirm this declaration reflects my process"]
        try wait(declaration, "project declaration checkbox")
        try reveal(declaration)
        declaration.click()
        try click("project.submit")
        try wait(textContaining("Project submitted. Your feedback is ready."), "real project feedback", timeout: 40)
        record("I submitted a recipe-scaling project and reflection, disclosed AI assistance, and confirmed the declaration.", observed: "Project submitted. Your feedback is ready.")
        try capture("project-feedback")

        try navigate("insights")
        try wait(textContaining("SUBMITTED ANSWERS ONLY"), "measured practice chart")
        try wait(app.staticTexts["Attempts"].firstMatch, "measured attempt chart legend")
        XCTAssertFalse(textContaining("A clearer picture will emerge").exists, "Actual submissions should replace the no-practice state")
        record("I opened Insights after three actual answer submissions.", observed: "Practice chart and Attempts legend are visible; backend database evidence independently verifies the exact submitted attempt count.")
        try capture("measured-insights")

        try navigate("settings")
        try click("settings.logout")
        let confirm = app.buttons.matching(NSPredicate(format: "label == %@ AND identifier != %@", "Sign out", "settings.logout")).firstMatch
        try wait(confirm, "sign-out confirmation")
        confirm.click()
        try wait(element("auth.email"), "signed-out authentication form")
        record("I signed out using Settings and confirmed the sign-out dialog.")
        let loginTab = app.buttons["Sign in"].firstMatch
        try wait(loginTab, "Sign in account segment")
        loginTab.click()
        try fill("auth.email", email)
        try fill("auth.password", password)
        try click("auth.login")
        try wait(element("nav.today"), "dashboard after signing back in", timeout: 40)
        try navigate("settings")
        try wait(element("settings.goal"), "persisted learning goal")
        let savedGoal = app.textViews["settings.goal"].exists ? app.textViews["settings.goal"] : element("settings.goal")
        XCTAssertEqual(savedGoal.value as? String, goal)
        try wait(textContaining("25 minutes"), "persisted daily time")
        let consent = element("settings.telemetry")
        let consentValue = try XCTUnwrap(consent.value)
        XCTAssertTrue(["1", "true", "on"].contains(String(describing: consentValue).lowercased()), "Saved consent must remain enabled: \(consentValue)")
        record("I signed back in to the same account and verified my saved goal, 25-minute daily time, and enabled consent.")
        try capture("persisted-settings")
        try navigate("today")
        try capture("persisted-dashboard")
        workflowCompleted = true
        record("I completed the native UI workflow.", observed: "One partial diagnostic, two practice attempts, one project, real tutor response, changed local slider, and persisted preferences.")
    }
}
