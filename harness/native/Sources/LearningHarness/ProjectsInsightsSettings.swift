import SwiftUI
import Charts

struct ProjectsView: View {
    @EnvironmentObject var store: AppStore
    @State private var selected = ""
    var items: [JSON] { store.projects["items"].array }
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Card(color: Palette.peach) { HStack { VStack(alignment: .leading, spacing: 10) { Eyebrow(text: "BUILD SOMETHING THAT SHOWS YOUR THINKING", tint: Palette.accentClay.deep.opacity(0.9)); Text("A project is an idea, made tangible.").font(.system(size: 24, weight: .semibold)).tracking(-0.7); Text("Write in your own words. Reflect on your process. Be clear about AI assistance.").font(.system(size: 12)).foregroundStyle(Palette.secondary) }; Spacer(); Image(systemName: "square.stack.3d.up").font(.system(size: 35, weight: .light)).foregroundStyle(Palette.accentClay.deep) } }
                .spotlight(cornerRadius: 22, tint: Palette.peachDeep, intensity: 0.15)
            if items.isEmpty { Card { EmptyState(icon: "pencil.and.outline", title: "Your next creation is ahead", message: "Project briefs will appear when the backend curriculum provides them.") } }
            else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 12) {
                        ForEach(items, id: \.["id"].string) { item in
                            Button { selected = item["id"].string } label: { VStack(alignment: .leading, spacing: 10) { Tag(text: item.text("status", fallback: "Not started").capitalized, color: Palette.accent(for: item.text("status", fallback: "Not started")).soft); Text(item["title"].string).font(.system(size: 14, weight: .semibold)).lineLimit(2); Text("Open project →").font(.system(size: 10)).foregroundStyle(Palette.secondary) }.padding(18).frame(width: 215, height: 125, alignment: .leading).background(selected == item["id"].string ? Palette.accentSky.soft : .white, in: RoundedRectangle(cornerRadius: 17)) }.buttonStyle(.plain)
                        }
                    }
                }
                if let item = items.first(where: { $0["id"].string == selected }) { ProjectEditor(project: item).id(selected) }
            }
        }.onChange(of: items) { _, values in if selected.isEmpty { selected = values.first?["id"].string ?? "" } }.onAppear { if selected.isEmpty { selected = items.first?["id"].string ?? "" } }
    }
}
struct ProjectEditor: View {
    @EnvironmentObject var store: AppStore
    let project: JSON
    @State private var text = ""
    @State private var reflection = ""
    @State private var usedAI = false
    @State private var disclosureConfirmed = false
    /// A draft belongs to an account, not to a window. Scoping it to the signed-in
    /// user id keeps two learners on one Mac from reading each other's unsubmitted
    /// writing; the endpoint is the fallback before the account payload has loaded.
    private var draftAccount: String {
        let id = store.user["id"].string
        return id.isEmpty ? store.endpoint : id
    }
    private var projectID: String { project["id"].string }
    private func saveDraft() {
        ProjectDrafts.save(account: draftAccount, project: projectID,
                           draft: .init(text: text, reflection: reflection,
                                        usedAI: usedAI, confirmed: disclosureConfirmed,
                                        updatedAt: Date().timeIntervalSinceReferenceDate))
    }
    var body: some View {
        HStack(alignment: .top, spacing: 20) {
            Card {
                VStack(alignment: .leading, spacing: 17) {
                    Text(project["title"].string).font(.system(size: 22, weight: .semibold))
                    Text(project["prompt"].string).font(.system(size: 13)).lineSpacing(5).textSelection(.enabled)
                    Text("Your submission").font(.system(size: 12, weight: .semibold))
                    TextEditor(text: $text).font(.system(size: 13)).scrollContentBackground(.hidden).padding(12).frame(height: 210).background(Palette.background, in: RoundedRectangle(cornerRadius: 12)).accessibilityIdentifier("project.text")
                    Text("Reflect on your process").font(.system(size: 12, weight: .semibold))
                    Text("What changed in your understanding? What would you try differently?").font(.system(size: 11)).foregroundStyle(Palette.secondary)
                    TextEditor(text: $reflection).font(.system(size: 12)).scrollContentBackground(.hidden).padding(10).frame(height: 90).background(Palette.background, in: RoundedRectangle(cornerRadius: 12)).accessibilityIdentifier("project.reflection")
                    Toggle("I used AI assistance in this project", isOn: $usedAI).toggleStyle(.checkbox).font(.system(size: 12)).accessibilityIdentifier("project.ai_disclosure")
                    Toggle("I confirm this declaration reflects my process", isOn: $disclosureConfirmed).toggleStyle(.checkbox).font(.system(size: 11)).foregroundStyle(Palette.secondary)
                    Button("Submit project") { store.run { await store.submitProject(id: project["id"].string, text: text, disclosure: usedAI, reflection: reflection) } }.buttonStyle(LuminfestButtonStyle()).disabled(store.busy || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || reflection.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !disclosureConfirmed).accessibilityIdentifier("project.submit")
                }
            }
            VStack(spacing: 17) {
                Card(color: Palette.accentOchre.soft.opacity(0.75), padding: 20) { VStack(alignment: .leading, spacing: 15) { Eyebrow(text: "WHAT GOOD LOOKS LIKE", tint: Palette.accentOchre.deep.opacity(0.9)); ForEach(Array(project["rubric"].array.enumerated()), id: \.offset) { index, item in HStack(alignment: .top, spacing: 9) { Text("0\(index+1)").font(.system(size: 10, weight: .semibold, design: .monospaced)).foregroundStyle(Palette.accentOchre.deep); Text(item.string).font(.system(size: 12)).lineSpacing(4) } } } }
                if !project["feedback"].isNull {
                    Card(color: Palette.lavender, padding: 20) { VStack(alignment: .leading, spacing: 13) { Eyebrow(text: "PROJECT FEEDBACK"); Text(project["feedback"].text("summary", fallback: project["feedback"].text("text", fallback: project["feedback"].string))).font(.system(size: 12)).lineSpacing(4).textSelection(.enabled); ForEach(Array(project["feedback"]["rubric"].array.enumerated()), id: \.offset) { _, row in Text(row.text("feedback", fallback: row.string)).font(.system(size: 11)) } } }
                }
            }.frame(width: 245)
        }.onChange(of: project) { _, updated in
            if !updated["feedback"].isNull { disclosureConfirmed = false }
        }.onAppear {
            // A saved draft wins over the last *submission*: the latter is graded work,
            // not what the learner is writing now. With no draft, a submitted project
            // still opens showing what was handed in.
            if let draft = ProjectDrafts.load(account: draftAccount, project: projectID) {
                text = draft.text
                reflection = draft.reflection
                usedAI = draft.usedAI
                disclosureConfirmed = draft.confirmed
            } else {
                text = project["submission"].text("text", fallback: project["submission"].string)
                reflection = project["reflection"].string
                usedAI = project["ai_disclosure"].string.hasPrefix("AI assistance was used")
            }
        }
        .onChange(of: text) { _, _ in saveDraft() }
        .onChange(of: reflection) { _, _ in saveDraft() }
        .onChange(of: usedAI) { _, _ in saveDraft() }
        .onChange(of: disclosureConfirmed) { _, _ in saveDraft() }
    }
}
struct InsightsView: View {
    @EnvironmentObject var store: AppStore
    var daily: [JSON] { store.analytics["daily"].array }
    var body: some View {
        VStack(spacing: 21) {
            Card(color: Palette.accentIndigo.soft) { HStack { VStack(alignment: .leading, spacing: 10) { Eyebrow(text: "YOUR EVIDENCE, IN PERSPECTIVE", tint: Palette.accentIndigo.deep.opacity(0.9)); Text(store.analytics.text("focus_note", fallback: "Progress needs evidence, not a prediction.")).font(.system(size: 19, weight: .medium)).fixedSize(horizontal: false, vertical: true); Text("Foreground activity is only a focus proxy. Empty dimensions mean there is not enough evidence yet.").font(.system(size: 11)).foregroundStyle(Palette.secondary) }; Spacer(); Tag(text: "\(store.analytics["streak"].int) DAY STREAK", color: Palette.accentOchre.soft) } }
                .spotlight(cornerRadius: 22, tint: Palette.accentIndigo.deep, intensity: 0.12)
            Card {
                VStack(alignment: .leading, spacing: 21) {
                    SectionHeading(title: "Practice over time", detail: "SUBMITTED ANSWERS ONLY")
                    if daily.isEmpty { EmptyState(icon: "chart.xyaxis.line", title: "A clearer picture will emerge", message: "Complete some practice to see measured activity here. No sample data is used.") }
                    else {
                        Chart(Array(daily.enumerated()), id: \.offset) { _, item in
                            BarMark(x: .value("Day", String(item["date"].string.suffix(5))), y: .value("Attempts", item["attempts"].int)).foregroundStyle(LinearGradient(colors: [Palette.accentTeal.deep, Palette.accentTeal.deep.opacity(0.58)], startPoint: .top, endPoint: .bottom)).cornerRadius(5)
                            LineMark(x: .value("Day", String(item["date"].string.suffix(5))), y: .value("Correct", item["correct"].int)).foregroundStyle(Palette.accentPlum.deep).lineStyle(StrokeStyle(lineWidth: 2))
                            PointMark(x: .value("Day", String(item["date"].string.suffix(5))), y: .value("Correct", item["correct"].int)).foregroundStyle(Palette.accentPlum.deep).symbolSize(24)
                        }.chartYAxis { AxisMarks(position: .leading) }.frame(height: 220)
                        HStack(spacing: 18) { Label("Attempts", systemImage: "square.fill").foregroundStyle(Palette.accentTeal.deep); Label("Correct answers", systemImage: "circle.fill").foregroundStyle(Palette.accentPlum.deep) }.font(.system(size: 10))
                    }
                }
            }
            HStack(alignment: .top, spacing: 20) {
                Card {
                    VStack(alignment: .leading, spacing: 17) {
                        SectionHeading(title: "Learning dimensions")
                        if store.analytics["dimensions"].array.isEmpty { Text("No dimension evidence yet.").font(.system(size: 12)).foregroundStyle(Palette.secondary).padding(.vertical, 30) }
                        ForEach(Array(store.analytics["dimensions"].array.enumerated()), id: \.offset) { index, item in
                            VStack(alignment: .leading, spacing: 9) {
                                HStack { Text(item["name"].string).font(.system(size: 12, weight: .medium)); Spacer(); Text(percent(item["value"])).font(.system(size: 12, weight: .semibold)).foregroundStyle(Palette.accent(at: index).deep) }
                                if !item["value"].isNull { ProgressView(value: max(0, min(1, item["value"].double > 1 ? item["value"].double / 100 : item["value"].double))).tint(Palette.accent(at: index).deep) }
                                Text(item.text("evidence", fallback: item.text("status", fallback: "Insufficient evidence"))).font(.system(size: 10)).foregroundStyle(Palette.secondary)
                            }.padding(.vertical, 7)
                        }
                    }
                }
                Card(color: Palette.peach.opacity(0.6)) {
                    VStack(alignment: .leading, spacing: 17) {
                        SectionHeading(title: "Places to look closer")
                        if store.analytics["errors"].array.isEmpty { EmptyState(icon: "lightbulb", title: "Nothing to diagnose yet", message: "Error patterns are based only on submitted answers.") }
                        else {
                            Chart(Array(store.analytics["errors"].array.enumerated()), id: \.offset) { _, item in BarMark(x: .value("Count", item["count"].int), y: .value("Category", item["category"].string.replacingOccurrences(of: "_", with: " "))).foregroundStyle(Palette.accentClay.deep.opacity(0.8)).cornerRadius(4) }.frame(height: 190)
                        }
                    }
                }
            }
            GradebookCard()
            PerspectiveCard()
        }
    }
}
struct SettingsPage: View {
    @EnvironmentObject var store: AppStore
    /// Injected once at the scene root. Declared here because the picker itself has to
    /// repaint on a language change: `L10n.t` is a static lookup, so a view that never
    /// observes the store would keep its old labels until something else invalidated it.
    @EnvironmentObject var localization: Localization
    /// Theme and text size live in the same two defaults keys the scene root reads, so a
    /// choice made here is what the next window is built with — there is no second copy of
    /// the preference to drift out of sync.
    @AppStorage("luminfest.appearance") private var appearanceRaw = AppearancePreference.system.rawValue
    @AppStorage("luminfest.textScale") private var textScaleRaw = TextScale.system.rawValue
    /// Increase Contrast is a system preference, not an app preference. It is read from
    /// AppKit rather than mirrored into `@AppStorage` on purpose: a per-app copy would let
    /// the row claim a state that `Palette` is not actually drawing with.
    @State private var increasesContrast = NSWorkspace.shared.accessibilityDisplayShouldIncreaseContrast
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    /// Used to re-read Increase Contrast when the learner comes back from System Settings;
    /// unlike Reduce Motion there is no environment value that updates it for us.
    @Environment(\.scenePhase) private var scenePhase
    @State private var goal = ""
    @State private var minutes = 20
    @State private var consent = false
    @State private var server = ""
    @State private var deletePrompt = false
    @State private var logoutPrompt = false
    @State private var endpointPrompt = false
    @State private var deletePhrase = ""
    @State private var realtimeKey = ""
    @State private var realtimeError: String?
    /// Whether the backend is launched with ``HARNESS_STREAM_ENABLED=1``. The value is still
    /// stored, so the next launch starts with the same answer, but it is no longer *only* read
    /// at launch: turning the switch tells the running server directly (see
    /// ``applyStreamSwitch``). Requiring a quit and relaunch was indistinguishable from a
    /// button that does nothing.
    @AppStorage("luminfest.streamEnabled") private var streamEnabled = false
    /// What the last attempt to change the switch produced, in the app rather than in a log.
    @State private var streamNote: String?
    @State private var streamNoteFailed = false

    /// Tell the running server, then let the reporter catch up immediately.
    ///
    /// The server has the final word: on a hosted deployment the switch belongs to the
    /// operator and this returns 403, which is shown here rather than swallowed. Locally the
    /// person at the Mac is the operator, so their click is the decision.
    @MainActor
    private func applyStreamSwitch(_ wanted: Bool) async {
        do {
            _ = try await store.api.data("/stream/enable", method: "POST",
                                         body: ["enabled": wanted])
            streamNoteFailed = false
            streamNote = wanted
                ? "Streaming is on for the running app. Open the browser tab — the first frame arrives in about a second. macOS asks once for Screen Recording (to capture the window) and Accessibility (to send your clicks and typing back); grant them in System Settings, then reload the page."
                : "Streaming is off. Nothing is captured, and an open browser tab says so instead of going blank."
            // The reporter backs off for a minute after a refusal. The refusal has just been
            // withdrawn, so make it report now rather than a minute from now.
            if wanted { WindowFrameReporter.shared.reportNow() }
        } catch {
            streamNoteFailed = true
            streamNote = (error as? AppFailure)?.message
                ?? "The running server did not accept the change: " + error.localizedDescription
        }
    }

    // MARK: - Display preference sections
    //
    // Language, theme and text size are the display preferences this app can actually
    // honour. Contrast and Reduce Motion deliberately stay read-only status rows: both are
    // macOS-owned get-only environment values that `Palette` and `Typography` already
    // resolve against, so a per-app switch could only change a stored bool that no
    // renderer reads — a lie the learner can catch by toggling it and seeing nothing move.

    private var languageBinding: Binding<AppLanguage> {
        Binding(get: { localization.language }, set: { localization.set($0) })
    }

    /// Both bindings resolve the raw string rather than storing the enum: `@AppStorage`
    /// can only persist a plist scalar, and a corrupt or older value falls back to
    /// "follow the system" instead of an empty selection.
    private var appearanceBinding: Binding<AppearancePreference> {
        Binding(get: { AppearancePreference(rawValue: appearanceRaw) ?? .system },
                set: { appearanceRaw = $0.rawValue })
    }

    private var textScaleBinding: Binding<TextScale> {
        Binding(get: { TextScale(rawValue: textScaleRaw) ?? .system },
                set: { textScaleRaw = $0.rawValue })
    }

    private var languageCard: some View {
        Card {
            VStack(alignment: .leading, spacing: 16) {
                SectionHeading(title: L10n.t("language.title"))
                Picker(L10n.t("language.title"), selection: languageBinding) {
                    ForEach(AppLanguage.allCases) { language in
                        // Each option is written in its own language, so the picker stays
                        // readable to exactly the person who cannot read the current one.
                        Text(language == .system ? L10n.t("language.system") : language.endonym)
                            .tag(language)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .accessibilityLabel(L10n.t("a11y.languagePicker"))
                .accessibilityIdentifier("settings.language")
                // Only "follow the system" needs an explanation; picking English or
                // Chinese is self-describing, and a line saying so would be noise.
                if localization.language == .system {
                    Text(L10n.t("language.systemDetail"))
                        .font(Typography.footnote)
                        .foregroundStyle(Palette.secondary)
                }
                Text(L10n.t("language.subtitle"))
                    .font(Typography.caption)
                    .foregroundStyle(Palette.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var appearanceCard: some View {
        Card {
            VStack(alignment: .leading, spacing: 18) {
                SectionHeading(title: L10n.t("settings.section.appearance"))
                VStack(alignment: .leading, spacing: 9) {
                    Text(L10n.t("settings.appearance.title")).font(Typography.bodyEmphasis)
                    Picker(L10n.t("settings.appearance.title"), selection: appearanceBinding) {
                        ForEach(AppearancePreference.allCases) { option in
                            Text(L10n.t(option.labelKey)).tag(option)
                        }
                    }
                    .pickerStyle(.segmented)
                    .labelsHidden()
                    .accessibilityIdentifier("settings.appearance")
                    Text(L10n.t("settings.appearance.detail"))
                        .font(Typography.caption)
                        .foregroundStyle(Palette.secondary)
                        .lineSpacing(3)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Divider()
                VStack(alignment: .leading, spacing: 9) {
                    Text(L10n.t("settings.text.title")).font(Typography.bodyEmphasis)
                    Picker(L10n.t("settings.text.title"), selection: textScaleBinding) {
                        ForEach(TextScale.allCases) { option in
                            Text(L10n.t(option.labelKey)).tag(option)
                        }
                    }
                    .pickerStyle(.segmented)
                    .labelsHidden()
                    .accessibilityIdentifier("settings.textScale")
                    Text(L10n.t("settings.text.detail"))
                        .font(Typography.caption)
                        .foregroundStyle(Palette.secondary)
                        .lineSpacing(3)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private var accessibilityCard: some View {
        Card {
            VStack(alignment: .leading, spacing: 18) {
                SectionHeading(title: L10n.t("settings.section.accessibility"))
                accessibilityRow(titleKey: "settings.contrast.title",
                                 detailKey: "settings.contrast.detail",
                                 stateOnKey: "settings.contrast.state.on",
                                 stateOffKey: "settings.contrast.state.off",
                                 isOn: increasesContrast,
                                 pane: "Seeing_Display",
                                 identifier: "settings.contrast")
                Divider()
                accessibilityRow(titleKey: "settings.motion.title",
                                 detailKey: "settings.motion.detail",
                                 stateOnKey: "settings.motion.state.on",
                                 stateOffKey: "settings.motion.state.off",
                                 isOn: reduceMotion,
                                 pane: "Seeing_Motion",
                                 identifier: "settings.motion")
            }
        }
    }

    /// One macOS-owned accessibility setting: what it does, whether it is on right now,
    /// and the button that opens the pane where it can be changed. The button exists
    /// because knowing a setting is off is useless without the place to turn it on.
    private func accessibilityRow(titleKey: String, detailKey: String,
                                  stateOnKey: String, stateOffKey: String,
                                  isOn: Bool, pane: String, identifier: String) -> some View {
        HStack(alignment: .top, spacing: 18) {
            VStack(alignment: .leading, spacing: 7) {
                Text(L10n.t(titleKey)).font(Typography.bodyEmphasis)
                Text(L10n.t(detailKey))
                    .font(Typography.footnote)
                    .foregroundStyle(Palette.secondary)
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 16)
            VStack(alignment: .trailing, spacing: 10) {
                Tag(text: L10n.t(isOn ? stateOnKey : stateOffKey),
                    color: isOn ? Palette.sage : Palette.muted)
                    .accessibilityIdentifier(identifier + ".state")
                Button(L10n.t("action.openSystemSettings")) { openAccessibilityPane(pane) }
                    .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
                    .accessibilityIdentifier(identifier + ".open")
            }
        }
    }

    /// The `x-apple.systempreferences:` scheme is the only supported way to land on a
    /// specific Accessibility pane; opening the pane URL is also why this is a button and
    /// not a toggle — the setting belongs to macOS, and only macOS may change it.
    private func openAccessibilityPane(_ pane: String) {
        guard let url = URL(string: "x-apple.systempreferences:com.apple.preference.universalaccess?" + pane) else { return }
        NSWorkspace.shared.open(url)
    }

    var body: some View {
        VStack(spacing: 21) {
            // Display preferences come first: they apply to every other card on this page,
            // so reading them after the account and server blocks would mean changing them
            // and scrolling back up to judge the result.
            languageCard
            appearanceCard
            accessibilityCard
            // The model is a hard dependency, so its configuration sits above the
            // optional settings: an unconfigured instance must say "Model required"
            // where a learner will actually see it, not in a support document.
            ModelSettingsCard()
            VoiceSettingsCard()
            HStack(alignment: .top, spacing: 20) {
                Card {
                    VStack(alignment: .leading, spacing: 20) {
                        SectionHeading(title: "Your daily intention")
                        VStack(alignment: .leading, spacing: 9) { Text("What are you learning toward?").font(.system(size: 12, weight: .medium)); TextField("A goal that matters to you", text: $goal, axis: .vertical).lineLimit(2...4).textFieldStyle(.roundedBorder).accessibilityIdentifier("settings.goal") }
                        Stepper(value: $minutes, in: 5...180, step: 5) { HStack { Text("Daily learning time"); Spacer(); Text("\(minutes) minutes").fontWeight(.semibold).foregroundStyle(Palette.forest) } }.font(.system(size: 12)).accessibilityIdentifier("settings.minutes")
                        Divider()
                        HStack(alignment: .top, spacing: 11) { Image(systemName: "hand.raised").font(.system(size: 22, weight: .light)).foregroundStyle(Palette.forest); VStack(alignment: .leading, spacing: 10) { Text("Transparent, optional activity tracking").font(.system(size: 13, weight: .semibold)); Text("If enabled, Luminfest sends a foreground activity heartbeat at most every 15 seconds. It pauses when the app is inactive or a question is paused. It does not track your screen, keystrokes, clipboard, or other apps.").font(.system(size: 11)).foregroundStyle(Palette.secondary).lineSpacing(4); Toggle("I consent to foreground activity tracking", isOn: $consent).toggleStyle(.switch).tint(Palette.accentTeal.deep).font(.system(size: 11)).accessibilityIdentifier("settings.telemetry"); Text("Foreground presence is not proof of attention. Turning this off stops collection after saving.").font(.system(size: 10)).foregroundStyle(Palette.secondary) } }
                        Button("Save preferences") { store.run { await store.updateSettings(goal: goal, minutes: minutes, consent: consent) } }.buttonStyle(LuminfestButtonStyle()).disabled(store.busy).accessibilityIdentifier("settings.save")
                    }
                }
                Card(color: Palette.accentSky.soft.opacity(0.8)) {
                    VStack(alignment: .leading, spacing: 17) {
                        Image(systemName: "person.crop.circle").font(.system(size: 32, weight: .light)).foregroundStyle(Palette.accentSky.deep)
                        Text(store.user["name"].string).font(.system(size: 19, weight: .semibold))
                        Text(store.user["email"].string).font(.system(size: 11)).foregroundStyle(Palette.secondary).textSelection(.enabled)
                        Divider()
                        Text("Your session token stays in macOS Keychain. Learning records live on your configured backend, scoped to your account.").font(.system(size: 11)).foregroundStyle(Palette.secondary).lineSpacing(4)
                        Button { logoutPrompt = true } label: { Label("Sign out", systemImage: "rectangle.portrait.and.arrow.right") }.buttonStyle(LuminfestButtonStyle(primary: false)).accessibilityIdentifier("settings.logout")
                    }
                }.frame(width: 260)
            }
            Card {
                VStack(alignment: .leading, spacing: 17) {
                    SectionHeading(title: "Use this app in a browser", detail: "THIS MAC ONLY")
                    Text("Opens this app's own window in a browser tab — the same lesson, the same backend, nothing rebuilt. It captures this Mac's screen, so it is off unless you turn it on, and only a teacher account can open it.")
                        .font(.system(size: 11))
                        .foregroundStyle(Palette.secondary)
                        .lineSpacing(4)
                        .fixedSize(horizontal: false, vertical: true)
                    Toggle("Present this app in a browser tab", isOn: $streamEnabled)
                        .toggleStyle(.switch)
                        .font(.system(size: 11))
                        .accessibilityIdentifier("settings.stream")
                        .onChange(of: streamEnabled) { _, wanted in
                            Task { await applyStreamSwitch(wanted) }
                        }
                    if let streamNote {
                        Label(streamNote,
                              systemImage: streamNoteFailed ? "exclamationmark.triangle"
                                                            : "checkmark.circle")
                            .font(.system(size: 10))
                            .foregroundStyle(streamNoteFailed ? Palette.peachDeep : Palette.secondary)
                            .lineSpacing(3)
                            .fixedSize(horizontal: false, vertical: true)
                            .accessibilityIdentifier("settings.stream.note")
                    } else if streamEnabled {
                        Text("Takes effect immediately, and stays on for the next launch. macOS will also ask once for Screen Recording (to capture the window) and Accessibility (to send your clicks and typing back) — grant them in System Settings, then reload the page.")
                            .font(.system(size: 10))
                            .foregroundStyle(Palette.secondary)
                            .lineSpacing(3)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Button {
                        if let url = URL(string: store.endpoint + "/app") {
                            NSWorkspace.shared.open(url)
                        }
                    } label: {
                        Label("Open in browser", systemImage: "safari")
                    }
                    .buttonStyle(LuminfestButtonStyle(primary: false))
                    .accessibilityIdentifier("settings.stream.open")
                }
            }
            Card {
                VStack(alignment: .leading, spacing: 17) {
                    SectionHeading(title: "Your course", detail: "SUBJECT")
                    Text("Changing course changes the knowledge map, the practice items and the figures. Everything you have already recorded stays attached to the concept it was recorded on, so switching back restores your progress - nothing is mixed between subjects.")
                        .font(.system(size: 11))
                        .foregroundStyle(Palette.secondary)
                        .lineSpacing(4)
                        .fixedSize(horizontal: false, vertical: true)
                    CourseSwitcher()
                }
            }
            Card {
                VStack(alignment: .leading, spacing: 17) {
                    SectionHeading(title: "Learning environment")
                    HStack(alignment: .top, spacing: 30) {
                        VStack(alignment: .leading, spacing: 10) { Text("Backend endpoint").font(.system(size: 12, weight: .semibold)); TextField("http://127.0.0.1:8765", text: $server).textFieldStyle(.roundedBorder).accessibilityIdentifier("settings.endpoint"); Text("Changing servers signs you out and clears the current account from memory. Remote servers require HTTPS.").font(.system(size: 10)).foregroundStyle(Palette.secondary); Button("Change server") { endpointPrompt = true }.buttonStyle(LuminfestButtonStyle(primary: false)) }
                        VStack(alignment: .leading, spacing: 11) { Text("Tutor provider").font(.system(size: 12, weight: .semibold)); Tag(text: "offline grounded tutor", color: Palette.lavender); Text("Uses backend curriculum and citations. External AI provider configuration will be available later; no AI connection is implied.").font(.system(size: 11)).foregroundStyle(Palette.secondary).lineSpacing(4) }
                    }
                }
            }
            Card {
                VStack(alignment: .leading, spacing: 15) {
                    SectionHeading(title: "Duplex voice (OpenAI Realtime)")
                    Text("Connect a live, two-way voice conversation with the tutor. Your API key is stored only in the macOS Keychain; the app talks to OpenAI directly. Create one at platform.openai.com/api-keys.")
                        .font(.system(size: 11)).foregroundStyle(Palette.secondary).lineSpacing(4)
                    SecureField("sk-…", text: $realtimeKey).textFieldStyle(.roundedBorder).accessibilityIdentifier("settings.realtime.key")
                    HStack(spacing: 10) {
                        Button("Save key") { store.run { await saveRealtimeKey() } }
                            .buttonStyle(LuminfestButtonStyle(primary: false))
                            .disabled(realtimeKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || store.busy)
                            .accessibilityIdentifier("settings.realtime.save")
                        if RealtimeKey.isConfigured {
                            Button("Clear key") { clearRealtimeKey() }
                                .buttonStyle(.borderless)
                                .foregroundStyle(Color(hex: 0xA16456))
                                .font(.system(size: 11))
                                .accessibilityIdentifier("settings.realtime.clear")
                        }
                        Spacer()
                        Tag(text: RealtimeKey.isConfigured ? "KEY SAVED" : "NO KEY", color: RealtimeKey.isConfigured ? Palette.sage : Palette.muted)
                    }
                    if let realtimeError {
                        Text(realtimeError).font(.system(size: 11)).foregroundStyle(.red)
                    }
                }
            }
            Card(padding: 22) {
                HStack(alignment: .center) {
                    VStack(alignment: .leading, spacing: 8) { Text("Your data belongs to you.").font(.system(size: 16, weight: .semibold)); Text("Export a JSON copy, permanently delete your account and its learning records, or copy a diagnostic report to paste wherever you report a problem.").font(.system(size: 11)).foregroundStyle(Palette.secondary) }
                    Spacer()
                    Button { store.run { await store.exportAccount() } } label: { Label("Export data", systemImage: "square.and.arrow.up") }.buttonStyle(LuminfestButtonStyle(primary: false)).accessibilityIdentifier("settings.export")
                    Button { store.run { await store.copyDiagnosticReport() } } label: { Label("Report a problem", systemImage: "exclamationmark.bubble") }.buttonStyle(LuminfestButtonStyle(primary: false)).accessibilityIdentifier("settings.report")
                    Button("Delete account") { deletePrompt = true }.buttonStyle(.borderless).foregroundStyle(Color(hex: 0xA16456)).font(.system(size: 11)).accessibilityIdentifier("settings.delete")
                }
            }
            Card {
                VStack(alignment: .leading, spacing: 14) {
                    SectionHeading(title: "Separate consent for model improvement")
                    Text("Activity consent does not authorize model training. Only explicitly opted-in, pseudonymized responses can be exported into the offline training pipeline. New models require held-out validation and manual promotion; no live training or unlearning guarantee is implied.").font(.system(size: 11)).foregroundStyle(Palette.secondary).lineSpacing(4)
                    Toggle("I allow my responses to be used for model improvement", isOn: Binding(get: { store.user["training_consent"].bool }, set: { enabled in store.run { await store.updateTrainingConsent(enabled) } })).toggleStyle(.switch).tint(Palette.accentPlum.deep).accessibilityIdentifier("settings.training")
                }
            }
            Button("Start a curriculum practice exam") { store.run { await store.startQuestion(mode: "exam") } }.buttonStyle(LuminfestButtonStyle(primary: false)).accessibilityIdentifier("exam.start")
        }.onAppear { sync() }.onChange(of: store.user) { _, _ in sync() }
            // Re-read on return from System Settings. There is no environment value for
            // Increase Contrast, so without this the row would keep saying "Off" after the
            // learner followed its own button and turned it on.
            .onChange(of: scenePhase) { _, phase in
                if phase == .active {
                    increasesContrast = NSWorkspace.shared.accessibilityDisplayShouldIncreaseContrast
                }
            }
            .confirmationDialog("Sign out of Luminest?", isPresented: $logoutPrompt, titleVisibility: .visible) { Button("Sign out") { store.run { await store.signOut() } }; Button("Cancel", role: .cancel) {} }
            .confirmationDialog("Change the backend and sign out?", isPresented: $endpointPrompt, titleVisibility: .visible) { Button("Change server") { do { try store.changeEndpoint(server) } catch { store.error = error.localizedDescription } }; Button("Cancel", role: .cancel) {} }
            .sheet(isPresented: $deletePrompt) {
                VStack(alignment: .leading, spacing: 20) {
                    Text("Permanently delete your account?").font(.system(size: 22, weight: .semibold))
                    // Fourth revision. The previous one got the direction of the caveat
                    // wrong: the erasure record has a second copy *outside* the data
                    // folder, so removing or replacing that folder does not lose it —
                    // measured, that case still answers 401. What actually defeats the
                    // record is deleting it, or replacing the folder that contains both.
                    // "up to four rollback copies" is added because the newest-of-each-kind
                    // clause alone understated what is kept.
                    Text("This removes your account and its learning records from the backend immediately, and signs it out everywhere on this Mac. The deletion is recorded outside the database, so restoring an old snapshot does not let the account sign back in. Recovery snapshots of the data can stay on this Mac until you remove them — the newest snapshot of each kind, and up to four rollback copies, are kept. If the deletion record itself is removed, or the whole folder the app keeps its data in is replaced from an older backup, the app can no longer tell that the account was deleted. Export your data first if you want a copy.").font(.system(size: 13)).foregroundStyle(Palette.secondary)
                    TextField("Type DELETE MY ACCOUNT", text: $deletePhrase).textFieldStyle(.roundedBorder)
                    HStack { Button("Cancel") { deletePrompt = false }.buttonStyle(LuminfestButtonStyle(primary: false)); Spacer(); Button("Delete permanently", role: .destructive) { store.run { await store.deleteAccount(); if !store.authenticated { deletePrompt = false } } }.buttonStyle(LuminfestButtonStyle()).disabled(deletePhrase != "DELETE MY ACCOUNT") }
                    if let error = store.error { Text(error).font(.system(size: 11)).foregroundStyle(.red) }
                }.padding(30).frame(width: 520).background(Palette.background)
            }
    }
    func sync() { goal = store.user["goal"].string; minutes = max(5, min(210, store.user["daily_minutes"].int)); consent = store.user["telemetry_consent"].bool; server = store.endpoint }
    func saveRealtimeKey() async {
        let key = realtimeKey.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !key.isEmpty else { return }
        do { try RealtimeKey.save(key); realtimeError = nil; realtimeKey = "" }
        catch { realtimeError = (error as? AppFailure)?.message ?? error.localizedDescription }
    }
    func clearRealtimeKey() { RealtimeKey.remove(); realtimeError = nil }
}

/// The teacher's voice. One selection, stored on this Mac, sent as the resolved
/// ``voice``/``tone`` of every speech request — the tutor's reply, the auto-lecture,
/// supervision notices and both read-aloud buttons. Keeping it out of the account is
/// deliberate: it describes this machine's VoiceStudio profiles, not the learner.
///
/// The preview button is not decoration. A picker whose effect can only be heard by
/// waiting for the tutor to say something is a picker nobody can verify; speaking one
/// line through the same ``/voice/speak`` route exercises the whole selection end to end.
private struct VoiceSettingsCard: View {
    @EnvironmentObject var store: AppStore
    @StateObject private var preview = VoiceIO()

    private var selectedNote: String {
        store.voiceOptions.first(where: { $0.id == store.selectedVoiceID })?.note ?? ""
    }

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: 15) {
                SectionHeading(title: "Teaching voice", detail: "VOICESTUDIO")
                Text("Choose the voice the tutor, the auto-lecture and read-aloud all use. The choice stays on this Mac and takes effect the next time something is spoken.")
                    .font(.system(size: 11))
                    .foregroundStyle(Palette.secondary)
                    .lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true)
                HStack(alignment: .top, spacing: 12) {
                    Picker("Teaching voice", selection: $store.selectedVoiceID) {
                        ForEach(store.voiceOptions) { option in
                            Text(option.label).tag(option.id)
                        }
                    }
                    .labelsHidden()
                    .accessibilityIdentifier("settings.voice")
                    Button {
                        if preview.speaking {
                            preview.stopSpeaking()
                        } else {
                            preview.speakThroughVoiceStudio(
                                "This is the voice your tutor will use.")
                        }
                    } label: {
                        Label(preview.speaking ? "Stop preview" : "Preview voice",
                              systemImage: preview.speaking ? "stop.fill" : "play.fill")
                    }
                    .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
                    .accessibilityIdentifier("settings.voice.preview")
                }
                if store.selectedVoiceID == "custom" {
                    TextField("VoiceStudio profile name", text: $store.customVoice)
                        .textFieldStyle(.roundedBorder)
                        .accessibilityIdentifier("settings.voice.custom")
                    Text("Enter a profile name installed in this instance's VoiceStudio. The name is sent unchanged with every speech request; leave it blank to use the instance default. Use Preview voice to hear whether it resolves.")
                        .font(.system(size: 10))
                        .foregroundStyle(Palette.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                } else if !selectedNote.isEmpty {
                    Text(selectedNote)
                        .font(.system(size: 10))
                        .foregroundStyle(Palette.secondary)
                }
                Divider()
                Toggle("Speak the tutor's replies aloud", isOn: $store.speakEnabled)
                    .toggleStyle(.switch)
                    .tint(Palette.accentTeal.deep)
                    .font(.system(size: 11))
                    .accessibilityIdentifier("settings.voice.speak")
                // A muted instance, a failed list fetch and a refused preview each say so.
                // None of them may look like a selection that quietly worked.
                if !store.voiceStatus.isEmpty {
                    Label(store.voiceStatus, systemImage: "exclamationmark.triangle")
                        .font(.system(size: 10))
                        .foregroundStyle(Palette.peachDeep)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("settings.voice.status")
                }
                if !preview.status.isEmpty {
                    Text(preview.status)
                        .font(.system(size: 10))
                        .foregroundStyle(Palette.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("settings.voice.previewStatus")
                }
            }
        }
        .onAppear { store.refreshVoices() }
    }
}
