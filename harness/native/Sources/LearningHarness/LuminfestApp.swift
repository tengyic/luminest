import SwiftUI
import AppKit

/// Opt-in presentation mode for screenshots meant for people outside the harness.
///
/// Only the operational chrome of a test session is affected: the backend status pill in the
/// header and the transient notice banner. No learner-facing surface, layout, state or behaviour
/// changes, and the flag is never passed by a normal launch, so the shipped app is untouched.
enum CapturePresentation {
    static let isEnabled = ProcessInfo.processInfo.arguments.contains("--capture-mode")
}

@MainActor final class AppDelegate: NSObject, NSApplicationDelegate {
    weak var store: AppStore?
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        DispatchQueue.main.async {
            if let iconURL = Bundle.main.url(forResource: "Luminfest", withExtension: "icns"), let icon = NSImage(contentsOf: iconURL) { NSApp.applicationIconImage = icon }
            NSApp.windows.first?.title = "Luminfest"
            NSApp.windows.first?.minSize = NSSize(width: SidebarLayout.minimumWindowWidth, height: 700)
        }
    }
    func applicationWillTerminate(_ notification: Notification) {
        // Falls back to the store itself: the delegate's own reference is only populated once the
        // root view appears, and quitting during launch would otherwise skip the shutdown that
        // cancels in-flight requests and stops an owned backend process.
        WindowFrameReporter.shared.stop()
        (store ?? AppStore.current)?.shutdown()
        BackendLauncher.shared.stopOwnedProcess()
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

@main struct LuminfestApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject private var store = AppStore()
    var body: some Scene {
        WindowGroup("Luminfest") {
            RootView().environmentObject(store).preferredColorScheme(.light)
                .onAppear {
                    delegate.store = store
                    NativeQA.shared.runIfRequested()
                    // The browser view at `/app` presents this window, so it needs to know
                    // where the window is. Reporting is silent when the instance has
                    // streaming switched off.
                    WindowFrameReporter.shared.start(store: store)
                }
        }
        .defaultSize(width: 1320, height: 860)
        .windowStyle(.hiddenTitleBar)
        .commands {
            CommandGroup(replacing: .newItem) {}
            CommandMenu("Learning") {
                ForEach(Array(Page.allCases.enumerated()), id: \.element) { index, page in
                    Button(page.title) { store.navigate(page) }.keyboardShortcut(KeyEquivalent(Character(String(index + 1))), modifiers: .command)
                }
                Divider()
                Button("Start diagnostic") { store.run { await store.startQuestion(mode: "diagnostic") } }.disabled(!store.authenticated).keyboardShortcut("d", modifiers: [.command, .shift])
                Button("Refresh") { store.run { await store.loadPage() } }.disabled(!store.authenticated).keyboardShortcut("r", modifiers: .command)
            }
        }
    }
}

struct RootView: View {
    @EnvironmentObject var store: AppStore
    var body: some View {
        Group {
            if store.restoring { VStack(spacing: 20) { Image(systemName: "sun.max.fill").font(.system(size: 38)).foregroundStyle(Palette.forest); ProgressView("Opening your learning space…") }.frame(maxWidth: .infinity, maxHeight: .infinity) }
            else if store.authenticated {
                // First run is a branch, not a sheet. See `AppStore.inCourseSetup` for why: a sheet
                // raised in the same update cycle as this swap is intermittently dropped, which
                // silently enrolled new learners in the default course.
                if store.inCourseSetup { CourseSetupView().preferredColorScheme(.light) }
                else { AppShell() }
            }
            else { OnboardingView() }
        }
        .foregroundStyle(Palette.ink).font(.system(size: 13))
        .background(Palette.background).frame(minWidth: SidebarLayout.minimumWindowWidth, minHeight: 700)
        // The practice surface is an overlay inside the one window rather than a sheet. A sheet is a
        // presentation attached to a host view, and SwiftUI intermittently drops a presentation that
        // is raised while its host's content is being swapped -- the same failure that used to skip
        // first-run setup and silently enrol learners in the default course. An overlay has no
        // presentation machinery to drop: it is a plain function of `showQuestion`, so it is either
        // there or it is not, and it is reachable through the same accessibility tree as the shell.
        .overlay {
            if store.showQuestion {
                ZStack {
                    // The scrim swallows clicks instead of dismissing. A session ends through Finish
                    // (which is confirmed when an answer is still unsaved), so a stray click cannot
                    // silently discard work in progress.
                    Color.black.opacity(0.26).ignoresSafeArea()
                    QuestionView()
                        .environmentObject(store)
                        .preferredColorScheme(.light)
                        .background(Palette.background, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
                        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous).strokeBorder(Color.white.opacity(0.65), lineWidth: 1))
                        .shadow(color: Palette.ink.opacity(0.20), radius: 44, x: 0, y: 20)
                        .padding(26)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .transition(.opacity)
            }
        }
        .animation(.easeInOut(duration: 0.18), value: store.showQuestion)
        // Rewards sit above everything, including a practice card: a milestone that lands
        // while a question is open should still be seen, and the overlay takes no clicks
        // for the two lighter tiers.
        .overlay { RewardOverlay(center: store.rewards) }
        .task(id: store.authenticated) { await pollRewards() }
    }

    /// Ask for milestones at sign-in, then every 60 s.
    ///
    /// Polling rather than pushing: `GET /rewards/events` recomputes the answer from stored
    /// rows on every call, so a timer is the entire protocol and the server holds no queue.
    /// A minute is short enough that a milestone lands while the learner is still in the
    /// session that earned it, and long enough that it costs nothing.
    private func pollRewards() async {
        while !Task.isCancelled {
            await store.rewards.refresh(store.authenticated ? store.api : nil)
            try? await Task.sleep(nanoseconds: 60_000_000_000)
        }
    }
}

struct OnboardingView: View {
    @EnvironmentObject var store: AppStore
    @State private var registering = true
    @State private var name = ""
    @State private var email = ""
    @State private var password = ""
    @State private var server = ""
    @State private var showServer = false
    @State private var ageConfirmed = false
    @State private var acceptedTerms = false
    /// Every rule the server would refuse, named in the learner's words.
    ///
    /// The submit button used to be disabled on a boolean this view never explained, so an
    /// address typed without an `@` produced a button that did nothing and said nothing - the
    /// learner cannot tell a validation rule from a broken app, and the server log shows no
    /// request at all because none was ever sent. The rules below are the server's own
    /// (``schemas.Login``: a local part, an `@`, a dotted domain, and a password of 10-128
    /// characters), so the hint names exactly what the request would have hit.
    var unmet: [String] {
        var out: [String] = []
        if registering && name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            out.append("Add your name.")
        }
        if !Self.emailLooksValid(email) {
            out.append("The email needs an @ and a domain, like you@example.com.")
        }
        if password.count < 10 {
            out.append("The password needs at least 10 characters.")
        }
        if registering && !ageConfirmed {
            out.append("Confirm that you are 13 or older.")
        }
        if registering && !acceptedTerms {
            out.append("Accept the Terms of Use and Privacy Policy.")
        }
        return out
    }
    var valid: Bool { unmet.isEmpty }

    /// The server's address rule, checked locally so the button can explain itself.
    static func emailLooksValid(_ value: String) -> Bool {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.contains(" "), let at = trimmed.firstIndex(of: "@") else { return false }
        let local = trimmed[trimmed.startIndex..<at]
        let domain = trimmed[trimmed.index(after: at)...]
        return !local.isEmpty && !domain.isEmpty && !domain.contains("@")
            && domain.contains(".") && !domain.hasPrefix(".") && !domain.hasSuffix(".")
    }
    var body: some View {
        HStack(spacing: 0) {
            ZStack {
                GoogleLabMeshAura()
                    .opacity(0.4)

                OpenAIDotsCanvas(
                    spacing: 24,
                    baseRadius: 1.8,
                    maxRadius: 5.2,
                    influenceRadius: 120,
                    primaryColor: Palette.forest,
                    glowColor: Palette.peachDeep
                )
                .opacity(0.55)

                VStack(alignment: .leading, spacing: 26) {
                    HStack(spacing: 12) {
                        Image(systemName: "sun.max.fill").font(.system(size: 26))
                        Text("luminfest").font(.system(size: 32, weight: .semibold, design: .rounded)).tracking(-1.2)
                    }.foregroundStyle(Palette.forest)

                    HStack(spacing: 8) {
                        Tag(text: "ADAPTIVE ENGINE", color: Palette.sage)
                        Tag(text: "KNOWLEDGE GRAPH", color: Palette.lavender)
                        Tag(text: "MULTIMODAL AI", color: Palette.peach)
                    }

                    Spacer(minLength: 12)
                    Eyebrow(text: "A BRIGHTER WAY TO LEARN")
                    Text("Make room\nfor understanding.")
                        .font(.system(size: 48, weight: .medium, design: .serif))
                        .tracking(-1.8)
                        .lineSpacing(2)
                    Text("Your own learning studio. Thoughtful practice.\nIdeas that connect, and progress you can see.")
                        .font(.system(size: 15))
                        .foregroundStyle(Palette.secondary)
                        .lineSpacing(6)

                    OrbitArtwork().frame(height: 195)

                    HStack(spacing: 22) {
                        Label("Native by design", systemImage: "macwindow")
                        Label("Private by choice", systemImage: "lock.shield")
                    }
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(Palette.forest)

                    Spacer(minLength: 10)
                    HStack {
                        Text("LUMINFEST LEARNING HARNESS")
                            .font(.system(size: 9, weight: .semibold))
                            .tracking(2.2)
                            .foregroundStyle(Palette.secondary)
                        Spacer()
                        Text("AGENTIC ADAPTATION")
                            .font(.system(size: 8, weight: .medium))
                            .tracking(1.4)
                            .foregroundStyle(Palette.secondary.opacity(0.8))
                    }
                }
                .padding(48)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .background(Palette.sage.opacity(0.35))

            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    Tag(text: "YOUR NEXT CHAPTER", color: Palette.lavender)
                    Text(registering ? "Start with curiosity." : "Welcome back.")
                        .font(.system(size: 32, weight: .semibold, design: .rounded))
                        .tracking(-1)
                    Text(registering ? "Create an account to keep your learning, your own." : "Sign in to pick up where you left off.")
                        .font(.system(size: 13))
                        .foregroundStyle(Palette.secondary)

                    Picker("Account", selection: $registering) {
                        Text("Create account").tag(true)
                        Text("Sign in").tag(false)
                    }
                    .pickerStyle(.segmented)
                    .padding(.vertical, 4)

                    VStack(alignment: .leading, spacing: 17) {
                        if registering {
                            field("Your name") {
                                TextField("Alex Morgan", text: $name).accessibilityIdentifier("auth.name")
                            }
                        }
                        field("Email address") {
                            TextField("you@example.com", text: $email).accessibilityIdentifier("auth.email")
                        }
                        field("Password") {
                            SecureField("Enter your password", text: $password).accessibilityIdentifier("auth.password")
                        }
                        // The launch gate, asked rather than assumed. Both boxes start
                        // unchecked: a pre-ticked 13+ attestation is not an attestation,
                        // and the server records these as consent evidence.
                        if registering {
                            VStack(alignment: .leading, spacing: 9) {
                                Toggle(isOn: $ageConfirmed) {
                                    Text("I am 13 years or older")
                                        .font(.system(size: 12))
                                        .foregroundStyle(Palette.secondary)
                                }
                                .toggleStyle(.checkbox)
                                .accessibilityIdentifier("auth.age")
                                Toggle(isOn: $acceptedTerms) {
                                    Text("I accept the Terms of Use and Privacy Policy")
                                        .font(.system(size: 12))
                                        .foregroundStyle(Palette.secondary)
                                }
                                .toggleStyle(.checkbox)
                                .accessibilityIdentifier("auth.terms")
                            }
                            .padding(.top, 2)
                        }
                    }

                    if let error = store.error {
                        Text(error).font(.system(size: 12)).foregroundStyle(.red).textSelection(.enabled)
                    } else if let next = unmet.first {
                        // One requirement at a time, in the order the fields are laid out. A
                        // list of five at once reads as a wall of complaint before anything has
                        // been typed; the first unmet rule reads as the next thing to do.
                        Label(next, systemImage: "info.circle")
                            .font(.system(size: 11))
                            .foregroundStyle(Palette.secondary)
                            .labelStyle(.titleAndIcon)
                            .accessibilityIdentifier("auth.hint")
                    }

                    Button {
                        store.run { await store.authenticate(register: registering, name: name, email: email, password: password, server: server, ageConfirmed: ageConfirmed, acceptedTerms: acceptedTerms) }
                    } label: {
                        HStack {
                            Spacer()
                            if store.authBusy { ProgressView().controlSize(.small).padding(.trailing, 4) }
                            Text(registering ? "Create my learning space" : "Sign in to Luminfest")
                            Image(systemName: "arrow.right")
                            Spacer()
                        }
                    }
                    .buttonStyle(LuminfestButtonStyle())
                    .disabled(!valid || store.authBusy)
                    .accessibilityIdentifier(registering ? "auth.register" : "auth.login")

                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: "lock.shield").foregroundStyle(Palette.forest)
                        Text("Your session is protected by macOS Keychain. Activity tracking is off by default; you can explicitly enable it in Settings.")
                            .font(.system(size: 11))
                            .foregroundStyle(Palette.secondary)
                            .lineSpacing(3)
                    }

                    Divider().overlay(Palette.line)

                    DisclosureGroup("Local learning server", isExpanded: $showServer) {
                        VStack(alignment: .leading, spacing: 10) {
                            TextField("http://127.0.0.1:8765", text: $server)
                                .textFieldStyle(.roundedBorder)
                                .accessibilityIdentifier("auth.endpoint")
                            Text("Connects to your configured backend. No demo account or simulated progress is created.")
                                .font(.system(size: 10))
                                .foregroundStyle(Palette.secondary)
                        }.padding(.top, 10)
                    }.font(.system(size: 12))
                }
                .frame(maxWidth: 375)
                .padding(.horizontal, 48)
                .padding(.vertical, 60)
                .frame(maxWidth: .infinity)
            }
            .frame(maxWidth: .infinity)
            .background(Color.white.opacity(0.85))
        }
        .onAppear { server = store.endpoint }
        .onChange(of: store.authenticated) { _, authenticated in if authenticated { password = "" } }
    }

    func field<V: View>(_ label: String, @ViewBuilder content: @escaping () -> V) -> some View {
        FormFieldContainer(label: label, content: content)
    }
}

private struct FormFieldContainer<V: View>: View {
    let label: String
    @ViewBuilder let content: () -> V
    @State private var isHovered = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(label)
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(isHovered ? Palette.ink : Palette.secondary)
            content()
                .textFieldStyle(.plain)
                .padding(13)
                .background(Color.white, in: RoundedRectangle(cornerRadius: 11, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 11, style: .continuous)
                        .stroke(isHovered ? Palette.forest.opacity(0.4) : Palette.line, lineWidth: isHovered ? 1.2 : 1)
                )
                .shadow(color: Palette.ink.opacity(isHovered ? 0.05 : 0.01), radius: isHovered ? 6 : 2, x: 0, y: 1)
                .onHover { hovering in
                    withAnimation(.easeInOut(duration: 0.2)) {
                        isHovered = hovering
                    }
                }
        }
    }
}

/// Spec 4.4: the full labelled sidebar is shown at 1,120 points of window width and
/// above; below it the shell uses a compact icon rail. Kept as pure, testable values so
/// the breakpoint has an XCTest rather than only a screenshot, and so the window's
/// minimum width cannot silently make the 900 pt case unreachable.
enum SidebarLayout {
    static let expandedBreakpoint: CGFloat = 1120
    static let expandedWidth: CGFloat = 207
    static let compactWidth: CGFloat = 68
    /// The spec asks for a 900 pt window, so the shell must not demand 1,000 pt.
    static let minimumWindowWidth: CGFloat = 900

    static func isExpanded(width: CGFloat) -> Bool { width >= expandedBreakpoint }

    static func sidebarWidth(for width: CGFloat) -> CGFloat {
        isExpanded(width: width) ? expandedWidth : compactWidth
    }

    static func compactIdentifier(for page: Page) -> String {
        "nav.compact." + page.rawValue
    }
}

struct AppShell: View {
    @EnvironmentObject var store: AppStore
    /// The current destination's hue, used for the page eyebrow, title and aura.
    var pageAccent: Accent { Palette.accent(at: Page.allCases.firstIndex(of: store.page) ?? 0) }
    var body: some View {
        GeometryReader { geometry in
            let availableWidth = geometry.size.width
            HStack(spacing: 0) {
                if SidebarLayout.isExpanded(width: availableWidth) {
                    sidebar.frame(width: SidebarLayout.expandedWidth)
                } else {
                    compactSidebar.frame(width: SidebarLayout.compactWidth)
                }
                Rectangle().fill(Palette.line).frame(width: 1)
            VStack(spacing: 0) {
                header
                ScrollView {
                    VStack(alignment: .leading, spacing: 26) {
                        HStack(alignment: .top) {
                            VStack(alignment: .leading, spacing: 9) {
                                Eyebrow(text: store.page.eyebrow, tint: pageAccent.deep.opacity(0.9))
                                GradientText(text: store.page == .today ? "A good day to grow." : store.page.title, size: 32, weight: .semibold, from: pageAccent.deep, to: pageAccent.deep.opacity(0.55))
                                    .tracking(-1.1)
                                Text(store.page.subtitle).font(.system(size: 13)).foregroundStyle(Palette.secondary)
                            }
                            Spacer()
                            if store.busy { ProgressView().controlSize(.small).padding(.top, 10) }
                        }
                        .background(alignment: .topLeading) {
                            AmbientAura(tint: pageAccent.soft, opacity: 0.7)
                                .frame(width: 340, height: 200)
                                .offset(x: -70, y: -70)
                        }
                        if let error = store.error {
                            HStack { Image(systemName: "exclamationmark.circle"); Text(error).font(.system(size: 12)).textSelection(.enabled); Spacer(); Button("Retry") { store.retry() }.buttonStyle(.borderless); Button { store.error = nil } label: { Image(systemName: "xmark") }.buttonStyle(.plain) }.foregroundStyle(Color(hex: 0x965D42)).padding(14).background(Palette.peach, in: RoundedRectangle(cornerRadius: 12))
                        }
                        if let notice = store.notice {
                            HStack { Image(systemName: "checkmark.circle"); Text(notice); Spacer(); Button { store.notice = nil } label: { Image(systemName: "xmark") }.buttonStyle(.plain) }.font(.system(size: 12)).padding(13).background(Palette.sage, in: RoundedRectangle(cornerRadius: 12))
                        }
                        switch store.page {
                        case .today: TodayView()
                        case .studio: StudioView()
                        case .map: KnowledgeView()
                        case .review: ReviewView()
                        case .teacher: TeacherPage()
                        case .projects: ProjectsView()
                        case .insights: InsightsView()
                        case .settings: SettingsPage()
                        }
                        HStack { Text("Designed for understanding, not just completion."); Spacer(); Text("LUMINFEST / LEARNING HARNESS").tracking(1.2) }.font(.system(size: 9)).foregroundStyle(Palette.secondary.opacity(0.8)).padding(.top, 6)
                    }.padding(.horizontal, 32).padding(.top, 27).padding(.bottom, 25)
                }
            }.frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    /// Below 1,120 pt the labelled sidebar becomes an icon rail. Every icon keeps an
    /// accessibility label, an accessibility identifier and a tooltip, so the compact
    /// shell is still usable with a keyboard, VoiceOver or a pointer.
    private var compactSidebar: some View {
        VStack(spacing: 0) {
            Image(systemName: "sun.max.fill")
                .font(.system(size: 21))
                .foregroundStyle(Palette.forest)
                .frame(height: 62)
                .accessibilityLabel("Luminfest")
            ForEach(Page.allCases) { page in
                let accent = Palette.accent(at: Page.allCases.firstIndex(of: page) ?? 0)
                let selected = store.page == page
                Button {
                    store.navigate(page)
                } label: {
                    Image(systemName: page.icon)
                        .font(.system(size: 16))
                        .foregroundStyle(accent.deep.opacity(selected ? 1 : 0.72))
                        .frame(width: 40, height: 40)
                        .background(
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .fill(selected ? accent.soft : Color.clear)
                        )
                }
                .buttonStyle(.plain)
                .accessibilityLabel(page.title)
                .accessibilityIdentifier(SidebarLayout.compactIdentifier(for: page))
                .help(page.title)
                .padding(.bottom, 4)
            }
            // The course/goal action must stay reachable in the compact shell too.
            Button {
                store.setupDismissed = false
                store.showCourseSetup = true
            } label: {
                Image(systemName: "book.closed")
                    .font(.system(size: 16))
                    .foregroundStyle(Palette.forest)
                    .frame(width: 40, height: 40)
                    .background(
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .fill(Palette.sage.opacity(0.5))
                    )
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Change course or goal")
            .accessibilityIdentifier("sidebar.setup")
            .help("Change course or goal")
            .padding(.bottom, 4)
            Spacer(minLength: 8)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(hex: 0xF1F2EC))
    }

    var sidebar: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 10) {
                Image(systemName: "sun.max.fill").font(.system(size: 24))
                Text("luminfest").font(.system(size: 24, weight: .semibold, design: .rounded)).tracking(-1)
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
                    .foregroundStyle(LinearGradient(colors: [Palette.deepForest, Palette.softForest], startPoint: .top, endPoint: .bottom))
            }
            .foregroundStyle(Palette.forest)
            .padding(.top, 40)
            .padding(.bottom, 7)

            Text("A SPACE TO UNDERSTAND")
                .font(.system(size: 8, weight: .semibold))
                .tracking(1.5)
                .foregroundStyle(Palette.secondary)
                .padding(.bottom, 35)

            Eyebrow(text: "LEARN").padding(.leading, 12).padding(.bottom, 12)

            ForEach(Page.allCases.filter { $0 != .settings }) { page in
                SidebarItemButton(page: page, isSelected: store.page == page) {
                    store.navigate(page)
                }
            }

            Spacer(minLength: 20)

            // Lumi sits above the course card rather than in a corner: she is the thing
            // that speaks to the learner, so she belongs next to the one block that also
            // speaks to them (goal, pace, change course).
            LumiSidebarSlot()
                .padding(.bottom, 12)

            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 7) {
                    Image(systemName: "book.closed").font(.system(size: 15)).foregroundStyle(Palette.forest)
                    Text(store.courseTitle)
                        .font(.system(size: 12, weight: .semibold))
                        .lineLimit(1)
                }
                Text("\(max(1, store.user["daily_minutes"].int)) intentional minutes.\nOne idea at a time.")
                    .font(.system(size: 11))
                    .foregroundStyle(Palette.secondary)
                    .lineSpacing(4)
                Button {
                    store.setupDismissed = false
                    store.showCourseSetup = true
                } label: {
                    Text("Change course or goal")
                        .font(.system(size: 10.5, weight: .medium))
                        .foregroundStyle(Palette.forest)
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("sidebar.setup")
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                LinearGradient(
                    colors: [Palette.sage.opacity(0.48), Palette.lavender.opacity(0.28)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                ),
                in: RoundedRectangle(cornerRadius: 15, style: .continuous)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 15, style: .continuous)
                    .stroke(Color.white.opacity(0.8), lineWidth: 1)
            )
            .shadow(color: Palette.ink.opacity(0.02), radius: 6, x: 0, y: 2)
            .padding(.bottom, 18)

            SidebarSettingsButton(isSelected: store.page == .settings) {
                store.navigate(.settings)
            }
        }
        .padding(.horizontal, 18)
        .padding(.bottom, 20)
        .background(Color(hex: 0xF1F2EC))
    }

    var header: some View {
        HStack(spacing: 18) {
            Text("Your learning space").font(.system(size: 12, weight: .medium)).foregroundStyle(Palette.secondary)
            Spacer()
            if !CapturePresentation.isEnabled {
                HStack(spacing: 7) {
                    ZStack {
                        Circle().fill(store.connected ? Palette.forest : Color.orange).frame(width: 6, height: 6)
                        if store.connected {
                            Circle().stroke(Palette.forest.opacity(0.35), lineWidth: 1).frame(width: 12, height: 12)
                        }
                    }
                    Text(store.connected ? "Backend connected" : "Backend offline")
                        .font(.system(size: 10, weight: .medium))
                }
                .foregroundStyle(Palette.secondary)
                .padding(.horizontal, 11)
                .padding(.vertical, 7)
                .background(Color.white.opacity(0.8), in: Capsule())
                .overlay(Capsule().stroke(Palette.line, lineWidth: 0.8))
            }

            HeaderRefreshButton {
                store.run { await store.loadPage() }
            }

            Rectangle().fill(Palette.line).frame(width: 1, height: 24)

            HStack(spacing: 9) {
                Text(String(store.user.text("name", fallback: "Learner").prefix(1)).uppercased())
                    .font(.system(size: 12, weight: .semibold))
                    .frame(width: 30, height: 30)
                    .background(
                        LinearGradient(colors: [Palette.lavender, Palette.peach], startPoint: .topLeading, endPoint: .bottomTrailing),
                        in: Circle()
                    )
                    .overlay(Circle().stroke(Color.white, lineWidth: 1))
                    .shadow(color: Palette.ink.opacity(0.04), radius: 3, x: 0, y: 1)
                Text(store.user.text("name", fallback: "Learner"))
                    .font(.system(size: 11, weight: .medium))
                    .lineLimit(1)
            }
        }
        .padding(.horizontal, 32)
        .frame(height: 66)
        .background(Color.white.opacity(0.65))
        .overlay(alignment: .bottom) { Rectangle().fill(Palette.line).frame(height: 1) }
    }
}

private struct SidebarItemButton: View {
    let page: Page
    let isSelected: Bool
    let action: () -> Void
    @State private var isHovered = false

    /// Each destination keeps its own Morandi hue, so the sidebar reads as a spectrum
    /// rather than a column of green.
    private var accent: Accent { Palette.accent(at: Page.allCases.firstIndex(of: page) ?? 0) }

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                Image(systemName: page.icon)
                    .font(.system(size: 15))
                    .foregroundStyle(accent.deep.opacity(isSelected ? 1 : (isHovered ? 0.95 : 0.72)))
                    .frame(width: 20)
                Text(page.title)
                    .font(.system(size: 12, weight: isSelected ? .semibold : .regular))
                    .foregroundStyle(isSelected ? accent.deep : (isHovered ? Palette.ink : Palette.secondary))
                Spacer()
                if isSelected {
                    Circle().fill(accent.deep).frame(width: 5, height: 5)
                }
            }
            .padding(.horizontal, 13)
            .padding(.vertical, 12)
            .background {
                RoundedRectangle(cornerRadius: 11, style: .continuous)
                    .fill(isSelected ? accent.soft : (isHovered ? accent.soft.opacity(0.45) : Color.clear))
            }
            .overlay(
                RoundedRectangle(cornerRadius: 11, style: .continuous)
                    .stroke(isSelected ? accent.deep.opacity(0.22) : Color.clear, lineWidth: 1)
            )
            .overlay(alignment: .leading) {
                if isSelected {
                    RoundedRectangle(cornerRadius: 2, style: .continuous)
                        .fill(LinearGradient(colors: [accent.deep, accent.soft], startPoint: .top, endPoint: .bottom))
                        .frame(width: 3, height: 20)
                        .padding(.leading, 3)
                        .transition(.opacity)
                }
            }
            .scaleEffect(isHovered ? 1.015 : 1.0)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("nav." + page.rawValue)
        .onHover { hovering in
            withAnimation(.spring(response: 0.25, dampingFraction: 0.75)) {
                isHovered = hovering
            }
        }
        .padding(.bottom, 4)
    }
}

private struct SidebarSettingsButton: View {
    let isSelected: Bool
    let action: () -> Void
    @State private var isHovered = false

    var body: some View {
        Button(action: action) {
            Label("Settings", systemImage: "slider.horizontal.3")
                .font(.system(size: 12))
                .foregroundStyle(isSelected ? Palette.accentSky.deep : (isHovered ? Palette.ink : Palette.secondary))
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background {
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(isSelected ? Palette.accentSky.soft : (isHovered ? Palette.accentSky.soft.opacity(0.45) : Color.clear))
                }
                .scaleEffect(isHovered ? 1.015 : 1.0)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("nav.settings")
        .onHover { hovering in
            withAnimation(.spring(response: 0.25, dampingFraction: 0.75)) {
                isHovered = hovering
            }
        }
    }
}

private struct HeaderRefreshButton: View {
    let action: () -> Void
    @State private var isHovered = false

    var body: some View {
        Button(action: action) {
            Image(systemName: "arrow.clockwise")
                .font(.system(size: 12))
                .foregroundStyle(isHovered ? Palette.forest : Palette.secondary)
                .rotationEffect(.degrees(isHovered ? 180 : 0))
                .padding(7)
                .background(isHovered ? Palette.sage.opacity(0.4) : Color.clear, in: Circle())
        }
        .buttonStyle(.plain)
        .help("Refresh current page")
        .onHover { hovering in
            withAnimation(.spring(response: 0.35, dampingFraction: 0.7)) {
                isHovered = hovering
            }
        }
    }
}
