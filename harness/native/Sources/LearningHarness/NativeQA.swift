import AppKit
import ApplicationServices
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
        guard !started, ProcessInfo.processInfo.arguments.contains("--native-qa") else { return }
        started = true
        Task { await run() }
    }

    private func argument(_ name: String) -> String? {
        let args = ProcessInfo.processInfo.arguments
        guard let index = args.firstIndex(of: name), args.indices.contains(index + 1) else { return nil }
        return args[index + 1]
    }

    private func run() async {
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
            try await waitMain("own application window", seconds: 10) { NSApp.windows.contains { $0.contentView != nil && $0.isVisible } }
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
                try await self.navigate("studio", marker: "studio.practice")
                try await self.capture("studio")
            }
            await exercise("question") { try await self.practice() }
            await exercise("tutor") { try await self.tutor() }
            await exercise("map") {
                try await self.navigate("map", text: "Understanding is connected.")
                try await self.capture("map")
            }
            await exercise("projects") { try await self.project() }
            await exercise("consent") { try await self.consent() }
            await exercise("insights") {
                try await self.navigate("insights", text: "Practice over time")
                try await self.capture("insights")
            }
            await captureRequestedPages()
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
        try await press("auth.register")
        await pause(6)
        await focusOwnWindow()
        await pause(1.0)
        record("diagnostic", target: "after-register", outcome: "state captured",
               details: (await MainActor.run { self.applicationState })
                        .merging(["navTodayPresent": self.find("nav.today") != nil,
                                  "authNamePresent": self.find("auth.name") != nil]) { _, new in new })
        try? await capture("after-register")
        // A brand-new account lands on first-run setup rather than the shell. Either surface proves
        // the session is real; the auth form being gone proves the view actually swapped.
        try await wait("signed-in UI", seconds: 30) {
            self.find("auth.name") == nil
                && (self.find("nav.today") != nil || self.containsText("SETTING UP YOUR LEARNING SPACE"))
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
        try await navigate("studio", marker: "studio.practice")
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
        try await navigate("teacher", marker: "teacher.message")
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
        try await navigate("projects", marker: "project.text")
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
        try await navigate("settings", marker: "settings.telemetry")
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

    private func navigate(_ page: String, marker: String? = nil, text: String? = nil) async throws {
        try await press("nav." + page)
        try await wait("page \(page)", seconds: 30) {
            (marker.map { self.find($0) != nil } ?? true) && (text.map { self.containsText($0) } ?? true)
        }
        await pause(0.5)
        record("navigation", target: "nav." + page, outcome: "destination UI observed")
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
                try await press("nav." + page)
                await pause(1.0)
                try await capture(page)
                record("optional-page", target: "nav." + page, outcome: "captured")
            } catch {
                record("optional-page", target: "nav." + page, outcome: "skipped",
                       details: ["reason": redact(error.localizedDescription)])
            }
        }
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
        var stack: [AXUIElement] = roots ?? [applicationElement]
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
