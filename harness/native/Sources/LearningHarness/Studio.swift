import SwiftUI
import AVKit

struct SimulationParameter: Identifiable, Equatable {
    let id: String
    let label: String
    let range: ClosedRange<Double>
    var value: Double
    static func parse(_ json: JSON) -> SimulationParameter? {
        let id = json["id"].string, lo = json["min"].double, hi = json["max"].double, value = json["value"].double
        guard !id.isEmpty, !json["min"].isNull, !json["max"].isNull, lo.isFinite, hi.isFinite, value.isFinite, lo < hi, abs(lo) <= 1_000_000, abs(hi) <= 1_000_000 else { return nil }
        return SimulationParameter(id: id, label: json.text("label", fallback: id), range: lo...hi, value: min(hi, max(lo, value)))
    }
}
enum PlotMath {
    static let kinds: Set<String> = ["linear", "quadratic", "systems", "equations", "expression", "balance", "slope", "polynomial", "ratio", "probability"]
    static func value(kind: String, x: Double, parameters: [String: Double], secondary: Bool = false) -> Double? {
        guard x.isFinite, kinds.contains(kind), parameters.values.allSatisfy(\.isFinite) else { return nil }
        let y: Double
        switch kind {
        case "linear": y = (parameters["m"] ?? parameters["slope"] ?? parameters["a"] ?? 3) * x + (parameters["b"] ?? parameters["intercept"] ?? -2)
        case "quadratic": y = (parameters["a"] ?? 1) * x * x + (parameters["b"] ?? -5) * x + (parameters["c"] ?? 6)
        case "systems", "equations": y = secondary ? (parameters["m2"] ?? 1) * x + (parameters["b2"] ?? -1) : (parameters["m1"] ?? -1) * x + (parameters["b1"] ?? 7)
        case "expression": y = secondary ? 3 * (x + 2) + 2 * x : 5 * x + 6
        case "balance": y = secondary ? 19 : 4 * x + 3
        case "polynomial": y = secondary ? (x + 2) * (x + 3) : x * x + 5 * x + 6
        case "ratio": y = 4 * x
        case "slope":
            let dx = parameters["deltaX"] ?? parameters["value"] ?? 3
            guard dx != 0 else { return nil }
            y = 2 + (6 / dx) * (x - 1)
        case "probability":
            // Compatibility numeric API only; native probability uses discrete bars, never a continuous function plot.
            guard x == x.rounded(), abs(x) <= 1000 else { return nil }
            return SimulationMath.binomial(k: Int(x), parameters: parameters)
        default: return nil
        }
        return y.isFinite ? y : nil
    }
}

struct StudioView: View {
    @EnvironmentObject var store: AppStore
    @StateObject private var speech = LessonSpeech()
    @State private var presenting = false
    @State private var activeSection = 0
    @State private var showBoard = false

    /// Indices of lesson blocks that carry a heading — these are the "sections" the
    /// reading rail steps through, mirroring Learn Your Way's chunk paginator.
    private var sectionBlockIndices: [Int] {
        store.lesson["blocks"].array.enumerated().compactMap { index, block in
            block["title"].string.isEmpty ? nil : index
        }
    }
    private var lessonSections: [String] {
        store.lesson["blocks"].array.compactMap { block in
            let title = block["title"].string
            return title.isEmpty ? nil : title
        }
    }
    private var sectionProgress: Double {
        guard sectionBlockIndices.count > 1 else { return 1 }
        return Double(activeSection + 1) / Double(sectionBlockIndices.count)
    }
    private func isActiveSectionBlock(_ index: Int) -> Bool {
        sectionBlockIndices.indices.contains(activeSection) && sectionBlockIndices[activeSection] == index
    }
    private var lessonKeyIdea: String {
        for block in store.lesson["blocks"].array where block["kind"].string == "concept" {
            let title = block["title"].string
            if !title.isEmpty { return title }
        }
        return lessonSections.first ?? ""
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            ConceptPicker()
            LevelCard()
            // The Stage: one big preview surface the lesson, the tutor and the student all
            // share — whiteboard / deck / web / assets. It sits between the concept and the
            // transcript because it IS the shared object of attention during teaching.
            StageView()
            if store.lesson.isNull {
                Card { EmptyState(icon: "book.pages", title: store.concepts.isEmpty ? "Your studio is ready" : "Choose an idea to begin", message: "Lessons come from the backend curriculum, with source material and validated native experiments.") }
            } else {
                HStack(alignment: .top, spacing: 20) {
                    lessonBody.frame(maxWidth: .infinity)
                    TutorPanel(compact: true).frame(width: 245)
                }
            }
        }
        .sheet(isPresented: $presenting) { LessonPresentation(lesson: store.lesson) }
        .sheet(isPresented: $store.showDeck) { NarratedDeckView() }
        .sheet(isPresented: $store.showDeckEditor) { DeckEditorView(deckID: store.selectedConcept, store: store).frame(minWidth: 900, minHeight: 620) }
        .sheet(isPresented: $store.showPlayground) { PlaygroundSheet() }
        .sheet(isPresented: $showBoard) { BoardSheet(conceptID: store.selectedConcept) }
        .onChange(of: store.selectedConcept) { _, _ in speech.stop(); presenting = false; activeSection = 0 }
        .onChange(of: store.page) { _, _ in speech.stop(); presenting = false }
        .onAppear { speech.bind(api: store.api) }
        .onDisappear { speech.stop() }
    }
    var lessonBody: some View {
        VStack(alignment: .leading, spacing: 18) {
            Card {
                VStack(alignment: .leading, spacing: 16) {
                    HStack { Tag(text: store.lesson["unit"].string.uppercased()); Spacer(); Text("READ · EXPLORE · PRACTICE").font(.system(size: 9, weight: .medium)).tracking(1).foregroundStyle(Palette.secondary) }
                    Text(store.lesson["title"].string).font(.system(size: 27, weight: .semibold)).tracking(-0.8)
                    if lessonSections.count > 1 {
                        VStack(alignment: .leading, spacing: 7) {
                            SegmentedProgressBar(progress: sectionProgress, tint: Palette.peachDeep, track: Palette.peach.opacity(0.4))
                            Text("Section \(activeSection + 1) of \(lessonSections.count)")
                                .font(.system(size: 11, weight: .medium))
                                .foregroundStyle(Palette.secondary)
                        }
                    }
                    HStack {
                        Button { if speech.isSpeaking { speech.stop() } else { speech.read(lesson: store.lesson) } } label: { Label(speech.isSpeaking ? "Stop reading" : "Read lesson aloud", systemImage: "speaker.wave.2") }.buttonStyle(LuminfestButtonStyle(primary: false)).accessibilityIdentifier("lesson.read")
                        Button { speech.stop(); presenting = true } label: { Label("Explain mode", systemImage: "rectangle.on.rectangle") }.buttonStyle(LuminfestButtonStyle(primary: false)).accessibilityIdentifier("lesson.present")
                        Button { store.run { await store.buildDeck() } } label: { Label(store.deckBusy ? "Assembling deck…" : "Narrated deck", systemImage: "film.stack") }.buttonStyle(LuminfestButtonStyle(primary: false)).disabled(store.deckBusy || store.selectedConcept.isEmpty).accessibilityIdentifier("lesson.deck")
                        Button { showBoard = true } label: { Label("Board", systemImage: "square.and.pencil") }.buttonStyle(LuminfestButtonStyle(primary: false)).disabled(store.selectedConcept.isEmpty).accessibilityIdentifier("lesson.board")
                    }
                    // Which engine is actually talking. VoiceStudio when the local
                    // backend answers, this Mac's voice when it does not — said out
                    // loud rather than implied, because "no third-party AI" stops
                    // being true the moment the backend is up.
                    Text(speech.usingBackendVoice
                         ? "Read by the local VoiceStudio voice backend — the same voice the tutor uses."
                         : "Read by this Mac's built-in voice. Start VoiceStudio for the tutor's voice; the button falls back to this one when it is not running.")
                        .font(.system(size: 10)).foregroundStyle(Palette.secondary)
                    HStack(alignment: .top, spacing: 22) {
                        VStack(alignment: .leading, spacing: 16) {
                            ForEach(Array(store.lesson["blocks"].array.enumerated()), id: \.offset) { index, block in
                                LessonBlock(block: block)
                                    .padding(.horizontal, 9)
                                    .padding(.vertical, 4)
                                    .background(isActiveSectionBlock(index) ? Palette.surfaceSubtle : Color.clear, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                            }
                            Button { store.run { await store.startQuestion(mode: "practice", concept: store.selectedConcept) } } label: { Label("Put it into practice", systemImage: "arrow.right") }.buttonStyle(LuminfestButtonStyle()).accessibilityIdentifier("practice.start")
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        if lessonSections.count > 1 { readingRail }
                    }
                }
            }
            if !store.lesson["simulation"].isNull { SimulationView(schema: store.lesson["simulation"]).id(store.selectedConcept) }
            if !store.lesson["project"].isNull {
                Card(color: Palette.peach) {
                    VStack(alignment: .leading, spacing: 14) {
                        Eyebrow(text: "TRY IT IN THE REAL WORLD")
                        Text(store.lesson["project"]["title"].string).font(.system(size: 20, weight: .semibold))
                        Text(store.lesson["project"]["prompt"].string).font(.system(size: 13)).lineSpacing(4)
                        ForEach(Array(store.lesson["project"]["rubric"].array.enumerated()), id: \.offset) { _, row in Label(row.string, systemImage: "checkmark").font(.system(size: 11)).foregroundStyle(Palette.secondary) }
                        Button("Open projects") { store.navigate(.projects) }.buttonStyle(LuminfestButtonStyle(primary: false))
                    }
                }
            }
            Card { LocalMediaChooser() }
            if !store.lesson["media"].array.isEmpty {
                Card {
                    VStack(alignment: .leading, spacing: 14) {
                        SectionHeading(title: "Watch & listen")
                        ForEach(Array(store.lesson["media"].array.enumerated()), id: \.offset) { _, media in NativeMediaView(media: media) }
                    }
                }
            }
            Card { ExternalSimulationsCard() }
            Card { PlaygroundCard() }
        }
    }

    /// The reading rail: a section paginator, a key-idea note and a section outline.
    /// Adapted from Learn Your Way's `.immersive-text-page-content-margin`.
    private var readingRail: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 6) {
                Spacer()
                RailIconButton(icon: "chevron.left", enabled: activeSection > 0, help: "Previous section") {
                    activeSection = max(0, activeSection - 1)
                }
                RailIconButton(icon: "chevron.right", enabled: activeSection < lessonSections.count - 1, help: "Next section") {
                    activeSection = min(lessonSections.count - 1, activeSection + 1)
                }
            }
            if !lessonKeyIdea.isEmpty {
                MarginNote(title: "Key idea", icon: "lightbulb.fill", tint: Palette.peachDeep) {
                    Text(lessonKeyIdea)
                }
            }
            MarginNote(title: "Sections in this lesson") {
                VStack(alignment: .leading, spacing: 9) {
                    ForEach(Array(lessonSections.enumerated()), id: \.offset) { index, title in
                        Button { activeSection = index } label: {
                            HStack(alignment: .top, spacing: 8) {
                                Image(systemName: index == activeSection ? "largecircle.fill.circle" : "circle")
                                    .font(.system(size: 10))
                                    .foregroundStyle(index == activeSection ? Palette.forest : Palette.tertiary)
                                    .padding(.top, 1)
                                Text(title)
                                    .font(.system(size: 12, weight: index == activeSection ? .semibold : .regular))
                                    .foregroundStyle(index == activeSection ? Palette.ink : Palette.secondary)
                                    .multilineTextAlignment(.leading)
                                    .fixedSize(horizontal: false, vertical: true)
                                Spacer(minLength: 0)
                            }
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .frame(width: 196)
    }
}
/// The learner-facing level, derived from their own answer history
/// (`GET /api/v1/ability`). The backend maps the internal IRT ability (a logit) onto a
/// CEFR band and a school grade; this view shows those bands without over-claiming
/// precision. It refreshes when the analytics snapshot changes (i.e. after practice).
struct LevelCard: View {
    @EnvironmentObject var store: AppStore
    @State private var level: JSON = .null
    @State private var loading = false
    @State private var error: String?

    var body: some View {
        Card(color: Palette.accentIndigo.soft.opacity(0.6)) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 9) {
                    Image(systemName: "rosette").font(.system(size: 18)).foregroundStyle(Palette.accentIndigo.deep)
                    Text("Your level").font(.system(size: 15, weight: .semibold))
                    Spacer()
                    if loading { ProgressView().controlSize(.small) }
                }
                if level.isNull, error == nil {
                    Text("Answer a few practice questions and your level appears here. It is a rough band, not a certificate.")
                        .font(.system(size: 11)).foregroundStyle(Palette.secondary).lineSpacing(4)
                } else if let error {
                    Text(error).font(.system(size: 11)).foregroundStyle(.red)
                } else if !level["known"].bool {
                    // The backend refuses to name a band before enough calibrated items
                    // exist, because theta starts at the prior and the prior maps cleanly
                    // onto "A2 / Grade 5" - a confident claim about a learner it has never
                    // seen answer anything. Show the refusal, not a number.
                    Text(level["label"].string.isEmpty ? "Not yet measured" : level["label"].string)
                        .font(.system(size: 15, weight: .semibold)).foregroundStyle(Palette.accentIndigo.deep)
                    Text(level["note"].string).font(.system(size: 11)).foregroundStyle(Palette.secondary).lineSpacing(4)
                } else {
                    HStack(spacing: 18) {
                        // CEFR is a language-proficiency scale, so it is only present for a
                        // language course. For every other subject the honest headline is the
                        // grade band; showing an empty "CEFR" column would read as a bug.
                        if !level["cefr"].isNull {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(level["cefr"].string).font(.system(size: 26, weight: .semibold)).foregroundStyle(Palette.accentIndigo.deep)
                                Text("CEFR").font(.system(size: 9)).tracking(1).foregroundStyle(Palette.secondary)
                            }
                        }
                        if !level["grade_label"].isNull {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(level["grade_label"].string).font(.system(size: level["cefr"].isNull ? 26 : 14, weight: .semibold))
                                    .foregroundStyle(level["cefr"].isNull ? Palette.accentIndigo.deep : Palette.ink)
                                    .fixedSize(horizontal: true, vertical: false)
                                Text("School grade").font(.system(size: 9)).tracking(1).foregroundStyle(Palette.secondary)
                            }
                        }
                        if !level["success_on_average_item"].isNull {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(percent(level["success_on_average_item"])).font(.system(size: 14, weight: .semibold))
                                Text("On an average question").font(.system(size: 9)).tracking(1).foregroundStyle(Palette.secondary)
                            }
                        }
                        Spacer()
                    }
                    Text(level["note"].string).font(.system(size: 9)).foregroundStyle(Palette.tertiary).lineSpacing(3)
                }
            }
        }
        .task { await load() }
        .onChange(of: store.analytics) { _, _ in Task { await load() } }
    }

    func load() async {
        guard store.authenticated else { return }
        loading = true; error = nil
        do {
            let j = try await store.api.json("/ability")
            level = j["level"]
        } catch {
            self.error = (error as? AppFailure)?.message ?? error.localizedDescription
        }
        loading = false
    }
}

struct ConceptPicker: View {
    @EnvironmentObject var store: AppStore
    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: "books.vertical").foregroundStyle(Palette.forest)
            Picker("Learning concept", selection: Binding(get: { store.selectedConcept }, set: { id in store.run { await store.selectConcept(id) } })) {
                if store.concepts.isEmpty { Text("No curriculum loaded").tag("") }
                ForEach(store.concepts, id: \.["id"].string) { concept in Text(concept["title"].string).tag(concept["id"].string) }
            }.labelsHidden().frame(maxWidth: 310).accessibilityIdentifier("studio.concept")
            Spacer()
            if !store.currentConcept["mastery"].isNull { Tag(text: "Mastery " + percent(store.currentConcept["mastery"]), color: Palette.lavender) }
            if !store.selectedConcept.isEmpty { Button("Practice") { store.run { await store.startQuestion(mode: "practice", concept: store.selectedConcept) } }.buttonStyle(LuminfestButtonStyle(primary: false)).accessibilityIdentifier("studio.practice") }
        }.padding(15).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 15))
    }
}
struct LessonBlock: View {
    static let kinds: Set<String> = ["concept", "worked_example", "retrieval", "reflection", "text", "diagram", "equation", "photograph"]
    let block: JSON
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if Self.kinds.contains(block["kind"].string) || block["kind"].string.isEmpty {
            if block["kind"].string == "photograph" {
                CachedPhotograph(block: block)
            } else {
            if !block["title"].string.isEmpty {
                // Key ideas get the warm highlight; worked examples get the dotted
                // "personalised" underline; review prompts get the margin annotation.
                switch block["kind"].string {
                case "concept":
                    KeyHighlight(text: block["title"].string)
                case "worked_example":
                    PersonalizedExample(text: block["title"].string, tip: "This worked example is written for this lesson and ties the idea to one concrete case.")
                case "retrieval":
                    KeyHighlight(text: block["title"].string, annotated: true)
                default:
                    Text(block["title"].string).font(.system(size: 17, weight: .semibold))
                }
            }
            Text(block["body"].string).font(.system(size: 13)).lineSpacing(6).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
            if !block["formula"].string.isEmpty { Text(block["formula"].string).font(.system(size: 19, weight: .medium, design: .serif)).textSelection(.enabled).padding(18).frame(maxWidth: .infinity).background(Palette.sage.opacity(0.6), in: RoundedRectangle(cornerRadius: 13)) }
            SafeLessonLink(title: "Source material", rawURL: block["source_url"].string)
            }
            } else { Text("This lesson component is not in the native text/diagram whitelist. No supplied code is executed.").font(.system(size: 11)).foregroundStyle(Palette.secondary) }
        }.padding(.vertical, 10)
    }
}

/// A licence-cleared photograph the backend cached locally. The image is read from the
/// backend's own media cache — the same file whose licence, author and attribution string
/// the manifest already validated — and the credit travels with the picture, because an
/// unattributed CC image is not a cleared image.
struct CachedPhotograph: View {
    let block: JSON
    @State private var image: NSImage?
    @State private var missing = false
    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            if let image {
                Image(nsImage: image).resizable().scaledToFit()
                    .frame(maxHeight: 330).frame(maxWidth: .infinity)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Palette.line))
                    .accessibilityLabel(block.text("alt", fallback: block["title"].string))
            } else if missing {
                Label("The cached photograph could not be read; it is left out rather than replaced with a placeholder image.", systemImage: "photo.badge.exclamationmark")
                    .font(.system(size: 11)).foregroundStyle(Palette.secondary)
            }
            if !block.text("caption", fallback: block["title"].string).isEmpty {
                Text(block.text("caption", fallback: block["title"].string)).font(.system(size: 11)).foregroundStyle(Palette.secondary)
            }
            if !block["credit"].string.isEmpty {
                Text(block["credit"].string + (block["licence"].string.isEmpty ? "" : " · " + block["licence"].string))
                    .font(.system(size: 9)).foregroundStyle(Palette.tertiary)
            }
        }
        .onAppear(perform: load)
    }
    private func load() {
        guard image == nil, !missing else { return }
        let path = block["src"].string
        guard !path.isEmpty, FileManager.default.fileExists(atPath: path),
              let loaded = NSImage(contentsOfFile: path) else { missing = true; return }
        image = loaded
    }
}
struct SimulationView: View {
    let schema: JSON
    @State private var parameters: [SimulationParameter] = []
    @State private var checkX = "2"
    @State private var prediction = ""
    @State private var result: String?
    var kind: String { schema["kind"].string.lowercased() }
    var values: [String: Double] { Dictionary(parameters.map { ($0.id, $0.value) }, uniquingKeysWith: { first, _ in first }) }
    var valid: Bool { SimulationMath.kinds.contains(kind) && !parameters.isEmpty && parameters.count == schema["parameters"].array.count && Set(parameters.map(\.id)).count == parameters.count }
    var checkLabel: String {
        switch kind {
        case "fraction": return "Predicted fraction sum (decimal)"
        case "number_line": return "Predicted endpoint"
        case "ratio": return "Predicted total cost"
        case "slope": return "Predicted slope (or undefined)"
        case "statistics": return "Predicted mean"
        case "sampling": return "Predicted standard error"
        case "probability": return "Predicted P(X = k)"
        case "balance": return "Predicted left side"
        default: return "Predicted y (first line)"
        }
    }
    var usesCheckX: Bool { ["linear", "quadratic", "systems", "equations", "expression", "balance", "polynomial", "probability"].contains(kind) }
    var body: some View {
        Card(color: Palette.lavender.opacity(0.55)) {
            VStack(alignment: .leading, spacing: 18) {
                HStack { Eyebrow(text: "THE EXPLORATION LAB", tint: Palette.accentLavender.deep.opacity(0.9)); Spacer(); Tag(text: "LIVE NATIVE SIMULATION", color: Palette.accentLavender.soft) }
                Text(schema.text("title", fallback: "See the idea move.")).font(.system(size: 20, weight: .semibold))
                if valid {
                    SimulationDetail(kind: kind, parameters: values)
                    ForEach($parameters) { $parameter in
                        HStack(spacing: 15) {
                            Text(parameter.label).font(.system(size: 11, weight: .medium)).frame(width: 100, alignment: .leading)
                            if let step = SimulationMath.step(kind: kind, id: parameter.id) {
                                Slider(value: $parameter.value, in: parameter.range, step: step).tint(Palette.forest).accessibilityIdentifier("simulation." + parameter.id)
                            } else {
                                Slider(value: $parameter.value, in: parameter.range).tint(Palette.forest).accessibilityIdentifier("simulation." + parameter.id)
                            }
                            Text(parameter.value.formatted(.number.precision(.fractionLength(2)))).font(.system(size: 11, design: .monospaced)).frame(width: 48)
                        }
                    }
                    Divider()
                    Text("Predict, then check").font(.system(size: 13, weight: .semibold))
                    HStack {
                        if usesCheckX { Text(kind == "probability" ? "k =" : "x =").font(.system(size: 12)); TextField("Input", text: $checkX).textFieldStyle(.roundedBorder).frame(width: 55) }
                        TextField(checkLabel, text: $prediction).textFieldStyle(.roundedBorder)
                        Button("Check") { check() }.buttonStyle(LuminfestButtonStyle(primary: false)).accessibilityIdentifier("simulation.check")
                    }
                    if let result { Text(result).font(.system(size: 12)).foregroundStyle(Palette.forest) }
                    Text("This is a local exploration, not a graded attempt. Changing a slider changes only the plotted mathematics.").font(.system(size: 10)).foregroundStyle(Palette.secondary).lineSpacing(3)
                } else { Text("This simulation schema is unsupported or has invalid parameter bounds. The lesson is still available; no generated code is executed.").font(.system(size: 12)).foregroundStyle(Palette.secondary) }
            }
        }
        .spotlight(cornerRadius: 22, tint: Palette.lavenderDeep, intensity: 0.13)
        .onAppear { parameters = SimulationMath.parameters(schema) }
        .onChange(of: parameters) { _, _ in result = nil }
    }
    func check() {
        if kind == "slope", (values["deltaX"] ?? SimulationMath.input(values)) == 0 {
            result = prediction.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() == "undefined" ? "Correct: zero horizontal run means undefined slope." : "The line is vertical. Its slope is undefined; enter undefined, not infinity."
            return
        }
        let x = usesCheckX ? Double(checkX) : nil
        guard !usesCheckX || x != nil, let expected = SimulationMath.result(kind: kind, parameters: values, x: x), let predicted = Double(prediction), predicted.isFinite else { result = "Enter finite numbers; a binomial success count k must be an integer."; return }
        let tolerance = max(0.00005, abs(expected) * 0.001)
        result = abs(expected - predicted) <= tolerance ? "Your prediction matches the current model." : "The current model gives \(SimulationMath.number(expected)). Check the equation and diagram above."
    }
}
struct NativePlot: View {
    let kind: String
    let parameters: [String: Double]
    var body: some View {
        Canvas { context, size in
            let rect = CGRect(x: 32, y: 14, width: max(1, size.width - 50), height: max(1, size.height - 40))
            let isProbability = kind == "probability"
            let probe = parameters["value"] ?? 5
            let dx = parameters["deltaX"] ?? probe
            let upperX = isProbability ? min(100, max(1, parameters["n"] ?? parameters["trials"] ?? 10)) : max(6, probe + 2, kind == "slope" ? 3 + dx : 6)
            let lowerX = isProbability ? -0.5 : (kind == "ratio" ? 0 : min(-6, probe - 2, kind == "slope" ? dx - 1 : -6))
            let sampleYs = (0...60).flatMap { i in
                [false, true].compactMap { secondary in PlotMath.value(kind: kind, x: lowerX + Double(i)/60*(upperX-lowerX), parameters: parameters, secondary: secondary) }
            }.filter { $0.isFinite && abs($0) < 1e9 }
            let rawMin = min(0, sampleYs.min() ?? 0), rawMax = max(8, sampleYs.max() ?? 8)
            let padding = max(2, (rawMax - rawMin)*0.08)
            let lowerY = isProbability ? 0.0 : rawMin - padding, upperY = isProbability ? 1.0 : rawMax + padding
            func point(_ x: Double, _ y: Double) -> CGPoint { CGPoint(x: rect.minX + (x - lowerX) / (upperX - lowerX + (isProbability ? 0.5 : 0)) * rect.width, y: rect.maxY - (y - lowerY) / (upperY - lowerY) * rect.height) }
            for i in 0...4 {
                let x = rect.minX + CGFloat(i) * rect.width / 4, y = rect.minY + CGFloat(i) * rect.height / 4
                var grid = Path(); grid.move(to: CGPoint(x: x, y: rect.minY)); grid.addLine(to: CGPoint(x: x, y: rect.maxY)); grid.move(to: CGPoint(x: rect.minX, y: y)); grid.addLine(to: CGPoint(x: rect.maxX, y: y))
                context.stroke(grid, with: .color(Palette.line), lineWidth: 0.8)
            }
            var axes = Path(); axes.move(to: point(lowerX, 0)); axes.addLine(to: point(upperX, 0)); axes.move(to: point(0, lowerY)); axes.addLine(to: point(0, upperY))
            context.stroke(axes, with: .color(Palette.secondary.opacity(0.65)), lineWidth: 1)
            context.draw(Text(isProbability ? "k" : "x").font(.system(size: 10)).foregroundColor(Palette.secondary), at: CGPoint(x: rect.maxX + 9, y: point(0,0).y))
            context.draw(Text(isProbability ? "P(X=k)" : "y").font(.system(size: 10)).foregroundColor(Palette.secondary), at: CGPoint(x: point(0,0).x, y: 5))
            context.draw(Text(String(Int(lowerX))).font(.system(size: 9)).foregroundColor(Palette.secondary), at: CGPoint(x: rect.minX, y: rect.maxY + 13))
            context.draw(Text(String(Int(upperX))).font(.system(size: 9)).foregroundColor(Palette.secondary), at: CGPoint(x: rect.maxX, y: rect.maxY + 13))
            var clipped = context; clipped.clip(to: Path(rect))
            for secondary in (["equations", "systems", "balance", "expression", "polynomial"].contains(kind) ? [true, false] : [false]) {
                if isProbability {
                    for k in 0...Int(upperX) {
                        if let y = PlotMath.value(kind: kind, x: Double(k), parameters: parameters) {
                            let p = point(Double(k), y), base = point(Double(k),0)
                            clipped.fill(Path(roundedRect: CGRect(x: p.x - rect.width / (upperX + 1) * 0.27, y: p.y, width: rect.width / (upperX + 1) * 0.54, height: max(0, base.y-p.y)), cornerRadius: 3), with: .color(Palette.forest.opacity(0.75)))
                        }
                    }
                } else {
                    var curve = Path(), started = false
                    for i in 0...400 {
                        let x = lowerX + Double(i)/400 * (upperX-lowerX)
                        guard let y = PlotMath.value(kind: kind, x: x, parameters: parameters, secondary: secondary), abs(y) < 1e9 else { started = false; continue }
                        let p = point(x,y)
                        if started { curve.addLine(to: p) } else { curve.move(to: p); started = true }
                    }
                    clipped.stroke(curve, with: .color(secondary ? Color(hex: 0xA18CAD) : Palette.forest), style: StrokeStyle(lineWidth: secondary ? 5 : 2.8, lineCap: .round, dash: secondary ? [7, 5] : []))
                    if let x = parameters["value"], let y = PlotMath.value(kind: kind, x: x, parameters: parameters, secondary: secondary) {
                        let p = point(x, y)
                        clipped.fill(Path(ellipseIn: CGRect(x: p.x - 5, y: p.y - 5, width: 10, height: 10)), with: .color(Palette.forest))
                    }
                }
            }
            if kind == "ratio" {
                let cost = 4 * max(0, probe), width = rect.width * max(0, probe) / upperX
                context.fill(Path(CGRect(x:rect.minX,y:rect.minY+4,width:width,height:12)),with:.color(Palette.forest.opacity(0.3)))
                context.draw(Text("cost \(SimulationMath.number(cost)) · count \(SimulationMath.number(max(0,probe)))").font(.system(size:10)).foregroundColor(Palette.forest),at:CGPoint(x:rect.midX,y:rect.minY+28))
            }
            if kind == "slope" {
                let a = point(1,2), b = point(1+dx,8), corner = point(1+dx,2)
                var triangle = Path(); triangle.move(to:a); triangle.addLine(to:corner); triangle.addLine(to:b)
                clipped.stroke(triangle,with:.color(Palette.secondary),style:StrokeStyle(lineWidth:2,dash:[4,4]))
                var segment = Path(); segment.move(to:a); segment.addLine(to:b); clipped.stroke(segment,with:.color(Palette.forest),lineWidth:3)
                for p in [a,b] { clipped.fill(Path(ellipseIn:CGRect(x:p.x-5,y:p.y-5,width:10,height:10)),with:.color(Palette.forest)) }
            }
            if ["systems", "equations"].contains(kind), let intersection = SimulationMath.intersection(parameters) {
                let p = point(intersection.x,intersection.y)
                clipped.fill(Path(ellipseIn:CGRect(x:p.x-6,y:p.y-6,width:12,height:12)),with:.color(Color(hex:0xB56E4B)))
            }
            context.draw(Text("y range \(SimulationMath.number(lowerY))…\(SimulationMath.number(upperY))").font(.system(size:9)).foregroundColor(Palette.secondary),at:CGPoint(x:rect.midX,y:rect.maxY+25))
        }.accessibilityLabel("Live \(kind) plot. " + SimulationMath.equation(kind:kind,p:parameters))
    }
}
struct NativeMediaView: View {
    /// One media reference card, dispatched by kind and by the rights status the backend
    /// already evaluated. The client renders the status honestly and never upgrades it:
    /// a withheld card shows its reason and no link, a link-only card never becomes an
    /// embed, and only a host on the embed allowlist renders in place.
    let media: JSON
    var body: some View {
        switch media["kind"].string {
        case "video": videoCard
        case "simulation": simulationCard
        default: linkCard(reading: media["kind"].string == "reading" || media["status"].string == "reference_link")
        }
    }

    // ---- video ------------------------------------------------------------------
    private var videoCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            header(icon: "play.rectangle", badge: badge)
            switch media["status"].string {
            case "verified_embed":
                if let url = MediaEmbed.url(media["embed_url"].string) {
                    EmbeddedLessonWebView(url: url)
                        .frame(height: 300)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Palette.line))
                        .accessibilityLabel("Embedded video: " + media["title"].string)
                    Text("Played through the provider's own player. Nothing is downloaded, re-hosted or transcribed.")
                        .font(.system(size: 10)).foregroundStyle(Palette.secondary)
                } else {
                    Text("The verified embed URL did not pass the client's own host allowlist, so it is offered as a link instead.")
                        .font(.system(size: 11)).foregroundStyle(Palette.secondary)
                    SafeLessonLink(title: "Open the video", rawURL: media.text("url", fallback: media["watch_url"].string))
                }
            case "withheld":
                withheldNote
            default:
                Text("Embedding could not be verified for this video, so it opens in your browser rather than in the lesson.")
                    .font(.system(size: 11)).foregroundStyle(Palette.secondary)
                SafeLessonLink(title: "Open the video", rawURL: media.text("url", fallback: media["watch_url"].string))
            }
            rightsLine
            if !media["why_this_video"].string.isEmpty {
                Text(media["why_this_video"].string).font(.system(size: 11)).foregroundStyle(Palette.secondary).lineSpacing(3)
            }
            if !media["notice"].string.isEmpty {
                Text(media["notice"].string).font(.system(size: 9)).foregroundStyle(Palette.tertiary)
            }
        }
    }

    // ---- simulation -------------------------------------------------------------
    private var simulationCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            header(icon: "laboratory", badge: badge)
            if media["status"].string == "withheld" {
                withheldNote
            } else if media["open_mode"].string == "embed_in_lesson",
                      let url = MediaEmbed.url(media["launch_url"].string) {
                EmbeddedLessonWebView(url: url)
                    .frame(height: 420)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Palette.line))
                    .accessibilityLabel("Embedded simulation: " + media["title"].string)
                Text("Simulation by PhET Interactive Simulations, University of Colorado Boulder. It runs on the provider's own site; nothing is copied.")
                    .font(.system(size: 10)).foregroundStyle(Palette.secondary)
            } else {
                Text(media.text("note", fallback: "This simulation opens in your own signed-in browser session; it is never embedded."))
                    .font(.system(size: 11)).foregroundStyle(Palette.secondary)
                SafeLessonLink(title: "Open the simulation", rawURL: media["launch_url"].string)
            }
            if !media["why_this_sim"].string.isEmpty {
                Text(media["why_this_sim"].string).font(.system(size: 11)).foregroundStyle(Palette.secondary).lineSpacing(3)
            }
            if !media["telemetry_note"].string.isEmpty {
                Text(media["telemetry_note"].string).font(.system(size: 9)).foregroundStyle(Palette.tertiary)
            }
        }
    }

    // ---- shared pieces ----------------------------------------------------------
    private var badge: String {
        switch media["status"].string {
        case "verified_embed": return "EMBEDDED · PROVIDER PLAYER"
        case "link_only": return "LINK ONLY · NOT VERIFIED"
        case "withheld": return "WITHHELD"
        case "ready": return media["open_mode"].string == "embed_in_lesson" ? "EMBEDDED · PROVIDER PLAYER" : "OPENS IN BROWSER"
        default: return media.text("status", fallback: "REFERENCE")
        }
    }
    private var withheldNote: some View {
        Text(media.text("withheld_reason", fallback: "This source is withheld under the current rights position."))
            .font(.system(size: 11, weight: .medium)).foregroundStyle(Palette.secondary)
            .padding(10).frame(maxWidth: .infinity, alignment: .leading)
            .background(Palette.surfaceSubtle, in: RoundedRectangle(cornerRadius: 10))
    }
    private var rightsLine: some View {
        HStack(spacing: 10) {
            Label("No download", systemImage: "arrow.down.circle.slash")
            Label("No transcript extraction", systemImage: "text.bubble.slash")
            Label("No model ingestion", systemImage: "brain.slash")
        }
        .font(.system(size: 9)).foregroundStyle(Palette.tertiary)
    }
    private func linkCard(reading: Bool) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack { Label(media["title"].string, systemImage: reading ? "book" : (media["kind"].string == "audio" ? "waveform" : "play.rectangle")).font(.system(size: 12, weight: .medium)); Spacer(); Tag(text: reading ? "REFERENCE READING" : media.text("status", fallback: "Unverified media"), color: Palette.muted) }
            if SafeLessonLink.url(media["url"].string) != nil {
                Text(reading ? "Reference reading opens in your browser; it is not a missing audio or video asset." : "Open the source in your browser. To play an asset locally, choose a file yourself above; no remote media is downloaded automatically.").font(.system(size: 11)).foregroundStyle(Palette.secondary)
                SafeLessonLink(title: reading ? "Open reference reading" : "Open source media", rawURL: media["url"].string)
            } else { Text("No safe HTTPS source is supplied. Backend file links cannot access local assets; use the local chooser.").font(.system(size: 11)).foregroundStyle(Palette.secondary) }
        }
    }
    private func header(icon: String, badge: String) -> some View {
        HStack(alignment: .top) {
            Label(media["title"].string, systemImage: icon).font(.system(size: 12, weight: .medium))
            Spacer()
            Tag(text: badge, color: media["status"].string == "withheld" ? Palette.peachDeep : Palette.muted)
        }
    }
}
struct TeacherPage: View {
    var body: some View { VStack(spacing: 20) { ConceptPicker(); TutorPanel(compact: false) } }
}

/// One licence-cleared image the tutor surfaced. A `local_path` means the backend already
/// downloaded a licence-cleared copy onto this machine — render that file directly; the
/// URL form is the embed posture and loads remotely with attribution kept beside it.
struct TutorMediaThumbnail: View {
    let item: [String: String]
    @State private var localImage: NSImage?
    @State private var failed = false

    var height: CGFloat = 96

    var body: some View {
        Group {
            if let localImage {
                Image(nsImage: localImage).resizable().scaledToFill()
                    .frame(height: height).clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            } else if let path = item["local_path"], !path.isEmpty {
                VStack(spacing: 6) {
                    if failed {
                        Label("The cached copy could not be read; use the Source link.", systemImage: "photo.badge.exclamationmark")
                            .font(.system(size: 9))
                    } else {
                        ProgressView().controlSize(.small)
                    }
                }.frame(height: height).frame(maxWidth: .infinity)
                    .background(Palette.muted, in: RoundedRectangle(cornerRadius: 10))
                    .onAppear { loadLocal(path) }
            } else if let url = URL(string: item["thumb_url"] ?? "") {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image.resizable().scaledToFill()
                            .frame(height: height).clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                    case .failure:
                        Label("The image could not be loaded; the source page is linked below instead.", systemImage: "photo.badge.exclamationmark")
                            .font(.system(size: 9)).frame(height: height).frame(maxWidth: .infinity)
                            .background(Palette.muted, in: RoundedRectangle(cornerRadius: 10))
                    default:
                        RoundedRectangle(cornerRadius: 10).fill(Palette.muted).frame(height: height)
                            .overlay(ProgressView().controlSize(.small))
                    }
                }
            } else {
                Label("No image is available for this result.", systemImage: "photo")
                    .font(.system(size: 9)).frame(height: height).frame(maxWidth: .infinity)
                    .background(Palette.muted, in: RoundedRectangle(cornerRadius: 10))
            }
        }
    }

    private func loadLocal(_ path: String) {
        guard localImage == nil, !failed else { return }
        if let image = NSImage(contentsOfFile: path) { localImage = image }
        else { failed = true }
    }
}
struct TutorPanel: View {
    @EnvironmentObject var store: AppStore
    var compact = false
    @State private var draft = ""
    @State private var showTeacherProfile = false
    var provider: String { store.messages.last(where: { $0["role"].string != "user" })?["provider"].string ?? "" }
    var offline: Bool { provider.isEmpty || provider.lowercased().contains("offline") }

    /// One-tap prompts for the moves a learner actually asks for. They are ordinary
    /// messages, not a second protocol: the tutor answers them through the same turn,
    /// so the draw-aloud and procedure rules apply to them too.
    private let quickActions: [(label: String, icon: String, prompt: String)] = [
        ("Draw it", "pencil.tip", "Draw it for me on the whiteboard, one step at a time."),
        ("Step by step", "list.number", "Walk me through this one step at a time."),
        ("Quiz me", "questionmark.circle", "Ask me one question about this to check I have it."),
        ("Simplify", "arrow.down.right.and.arrow.up.left", "Explain this more simply, with a picture if it helps."),
    ]

    var body: some View {
        Card(padding: compact ? 18 : 24) {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Image(systemName: "bubble.left.and.text.bubble.right").foregroundStyle(Palette.forest).font(.system(size: 18))
                    Text("A little guidance").font(.system(size: 15, weight: .semibold))
                    Spacer()
                    Button { showTeacherProfile = true } label: {
                        Image(systemName: store.teacherStyleProfile.isEmpty ? "person.text.rectangle" : "person.text.rectangle.fill")
                    }
                    .buttonStyle(.plain).foregroundStyle(Palette.forest)
                    .help(store.teacherStyleProfile.isEmpty ? "Personalize this tutor from an authorized teacher transcript" : "Review or clear the teacher-style profile")
                    .accessibilityIdentifier("teacher.profile")
                    // Speak the reply aloud, through the local VoiceStudio backend. The
                    // label says which voice it is, because the on-device reader on each
                    // transcript row is a different one and the two are not
                    // interchangeable.
                    Button {
                        store.speakEnabled.toggle()
                    } label: {
                        Image(systemName: store.speakEnabled ? "speaker.wave.3.fill" : "speaker.wave.2")
                    }
                    .buttonStyle(.plain).foregroundStyle(store.speakEnabled ? Palette.forest : Palette.secondary)
                    .help(store.speakEnabled ? "The tutor speaks its replies aloud (VoiceStudio). Click to turn it off." : "Speak the tutor's replies aloud (VoiceStudio)")
                    .accessibilityIdentifier("tutor.speak")
                }
                Tag(text: provider.isEmpty ? "offline · provider not reported" : "Provider: " + provider, color: Palette.sage)
                if !store.teacherStyleProfile.isEmpty {
                    HStack(spacing: 7) {
                        Tag(text: "TEACHER STYLE ACTIVE", color: Palette.lavender)
                        Button("Clear") { store.teacherStyleProfile = [:] }.buttonStyle(.plain).font(.system(size: 9)).foregroundStyle(Palette.secondary)
                    }
                }
                Text(offline ? "Offline curriculum guidance; no live AI provider is claimed. Check citations and use your own judgment." : "The provider label is reported by the backend, not independently verified. Check citations and use your own judgment.").font(.system(size: 10)).foregroundStyle(Palette.secondary).lineSpacing(3)
                Divider()
                if !store.chatActivities.isEmpty {
                    ActivityStrip(activities: store.chatActivities, busy: store.chatBusy)
                }
                if !store.speechStatus.isEmpty {
                    HStack(spacing: 6) {
                        Image(systemName: store.speech.playing ? "speaker.wave.3.fill" : "speaker.slash")
                            .font(.system(size: 9))
                        Text(store.speechStatus).font(.system(size: 9)).lineSpacing(3)
                        Spacer()
                        if store.speech.playing {
                            Button { store.speech.stop() } label: { Image(systemName: "stop.fill").font(.system(size: 8)) }
                                .buttonStyle(.plain).foregroundStyle(Palette.secondary)
                        }
                    }
                    .foregroundStyle(Palette.secondary)
                    .padding(.horizontal, 10).padding(.vertical, 7)
                    .background(Palette.surfaceSubtle, in: RoundedRectangle(cornerRadius: 10))
                }
                if !compact {
                    quickActionRow
                }
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        if store.messages.isEmpty { VStack(alignment: .leading, spacing: 12) { Text("What would you like to understand?").font(.system(size: 15, weight: .medium)); Text("Ask about this idea, an unfamiliar term, or a step that doesn’t quite click.").font(.system(size: 12)).foregroundStyle(Palette.secondary).lineSpacing(4) }.padding(.vertical, 20) }
                        ForEach(Array(store.messages.enumerated()), id: \.offset) { _, message in
                            VStack(alignment: .leading, spacing: 9) {
                                HStack(spacing: 6) {
                                    Text(message["role"].string == "user" ? "YOU" : "GROUNDED TUTOR").font(.system(size: 8, weight: .semibold)).tracking(1.3).foregroundStyle(Palette.secondary)
                                    Spacer()
                                    if message["role"].string != "user" {
                                        // On-device read-aloud; the "robotic" complaint is a
                                        // known limit — the live-voice provider is sequenced.
                                        SpeakerButton(text: message.text("content", fallback: message.text("message", fallback: message.text("text"))))
                                    }
                                }
                                // The reply is markdown. Drawing it as one `Text` showed the
                                // learner the asterisks and hashes the tutor wrote; this
                                // parses the blocks and draws them as blocks.
                                MarkdownText(message.text("content", fallback: message.text("message", fallback: message.text("text"))), size: 12)
                                ForEach(Array((message["citations"].isNull ? message["grounding"].array : message["citations"].array).enumerated()), id: \.offset) { _, source in SafeLessonLink(title: source.text("title", fallback: "Source"), rawURL: source.text("url", fallback: source.string)) }
                                if message["role"].string != "user" && message["grounding"].isNull && message["citations"].isNull {
                                    ForEach(Array(store.lesson["blocks"].array.prefix(1).enumerated()), id: \.offset) { _, block in SafeLessonLink(title: "Current curriculum reference", rawURL: block["source_url"].string) }
                                }
                            }.padding(13).frame(maxWidth: .infinity, alignment: .leading).background(message["role"].string == "user" ? Palette.sage.opacity(0.5) : Palette.background, in: RoundedRectangle(cornerRadius: 13))
                        }
                        if !store.chatMedia.isEmpty {
                            VStack(alignment: .leading, spacing: 9) {
                                Text("SOURCES THE TUTOR FOUND").font(.system(size: 8, weight: .semibold)).tracking(1.3).foregroundStyle(Palette.secondary)
                                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 10), count: 3), spacing: 10) {
                                    ForEach(Array(store.chatMedia.enumerated()), id: \.offset) { _, item in
                                        VStack(alignment: .leading, spacing: 5) {
                                            TutorMediaThumbnail(item: item)
                                            Text(item["title"] ?? "").font(.system(size: 9, weight: .medium)).lineLimit(2)
                                            HStack(spacing: 5) {
                                                Tag(text: (item["licence"] ?? "").uppercased(), color: Palette.accentTeal.soft)
                                                if let page = item["source_page"], let url = URL(string: page) {
                                                    Link("Source", destination: url).font(.system(size: 9, weight: .semibold)).foregroundStyle(Palette.forest)
                                                }
                                            }
                                        }
                                        .padding(8).frame(maxWidth: .infinity, alignment: .leading)
                                        .background(Color.white.opacity(0.92), in: RoundedRectangle(cornerRadius: 13))
                                        .overlay(RoundedRectangle(cornerRadius: 13).strokeBorder(Palette.line, lineWidth: 1))
                                    }
                                }
                                Text("Licence-cleared results from the tutor's image tools (embed posture). Nothing is copied into lessons without its attribution.")
                                    .font(.system(size: 9)).foregroundStyle(Palette.tertiary)
                            }.padding(13).frame(maxWidth: .infinity, alignment: .leading)
                                .background(Palette.surfaceSubtle, in: RoundedRectangle(cornerRadius: 13))
                        }
                    }
                }.frame(height: compact ? 310 : 400)
                TextEditor(text: $draft).font(.system(size: 12)).scrollContentBackground(.hidden).padding(7).frame(height: 76).background(Palette.background, in: RoundedRectangle(cornerRadius: 10)).overlay(RoundedRectangle(cornerRadius: 10).stroke(Palette.line)).accessibilityIdentifier("teacher.message")
                Button {
                    let text = draft
                    store.run { await store.sendMessage(text); if store.error == nil { draft = "" } }
                } label: { HStack { Text(store.chatBusy ? "Finding guidance…" : "Ask the tutor"); Spacer(); if store.chatBusy { ProgressView().controlSize(.small) } else { Image(systemName: "arrow.up") } } }.buttonStyle(LuminfestButtonStyle()).disabled(store.chatBusy || draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || store.selectedConcept.isEmpty).accessibilityIdentifier("teacher.send")
                // A failed turn used to be invisible here: `store.error` was only ever drawn
                // on the Settings page, so the learner saw their message, an empty space and
                // their own text still sitting in the composer. If a turn cannot answer,
                // this is where it says why.
                if let error = store.error {
                    Label(error, systemImage: "exclamationmark.triangle")
                        .font(.system(size: 10))
                        .foregroundStyle(Palette.peachDeep)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("tutor.error")
                }
                Text("No answers or tutor help are available inside an exam.").font(.system(size: 9)).foregroundStyle(Palette.secondary)
            }
        }
        .sheet(isPresented: $showTeacherProfile) {
            TeacherProfileSheet().environmentObject(store)
        }
    }

    /// The one-tap prompts. Hidden in the narrow side rail (245 pt) because four chips
    /// and a composer do not fit there; the wide panel is where a learner browses them.
    private var quickActionRow: some View {
        HStack(spacing: 7) {
            ForEach(quickActions, id: \.label) { action in
                Button {
                    store.run { await store.sendMessage(action.prompt) }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: action.icon).font(.system(size: 9))
                        Text(action.label).font(.system(size: 10, weight: .medium))
                    }
                    .padding(.horizontal, 9).padding(.vertical, 5)
                    .background(Palette.background, in: Capsule())
                    .overlay(Capsule().strokeBorder(Palette.line, lineWidth: 1))
                }
                .buttonStyle(.plain).foregroundStyle(Palette.forest)
                .disabled(store.chatBusy || store.selectedConcept.isEmpty)
                .accessibilityIdentifier("tutor.quick.\(action.label)")
            }
            Spacer(minLength: 0)
        }
    }
}

/// What the tutor is doing, one chip per tool call, in the order it made them.
///
/// Each chip arrives while its tool is still running, so the row reads as a live
/// account of the work rather than a summary written after the fact. The label is the
/// server's sentence ("Drawing on the whiteboard"), never the tool's name.
struct ActivityStrip: View {
    let activities: [ChatActivity]
    let busy: Bool
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 5) {
                Text("WHAT THE TUTOR IS DOING").font(.system(size: 8, weight: .semibold)).tracking(1.2).foregroundStyle(Palette.secondary)
                if busy { ProgressView().controlSize(.mini) }
            }
            // A turn can make a dozen calls; showing all of them buries the reply. The
            // most recent six are the ones a learner is still watching happen.
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(Array(activities.suffix(6))) { activity in
                        HStack(spacing: 5) {
                            Group {
                                if activity.state == .running {
                                    ProgressView().controlSize(.mini)
                                } else {
                                    Image(systemName: activity.state == .done ? "checkmark" : "exclamationmark.triangle.fill")
                                        .font(.system(size: 8))
                                }
                            }
                            .frame(width: 10)
                            Text(activity.label).font(.system(size: 9, weight: .medium))
                                .lineLimit(1)
                        }
                        .padding(.horizontal, 8).padding(.vertical, 4)
                        .background(activity.state == .failed ? Palette.peach.opacity(0.35) : Palette.background,
                                    in: Capsule())
                        .overlay(Capsule().strokeBorder(Palette.line, lineWidth: 1))
                        .foregroundStyle(activity.state == .running ? Palette.forest : Palette.secondary)
                    }
                }
            }
        }
        .padding(.horizontal, 10).padding(.vertical, 8)
        .background(Palette.surfaceSubtle, in: RoundedRectangle(cornerRadius: 10))
        .accessibilityIdentifier("tutor.activities")
    }
}
