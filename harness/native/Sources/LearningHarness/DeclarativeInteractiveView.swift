import SwiftUI

/// Native renderer for the backend's declarative interactive vocabulary.
///
/// This view never sees JavaScript, markup, a URL or a file path. It receives a validated
/// spec, switches on the component types the backend publishes, and recomputes readouts
/// locally from learner state. The backend evaluator remains the authority for recorded
/// evidence; this local frame is what makes the interaction feel immediate.
struct DeclarativeInteractiveView: View {
    private struct FeedbackLine: Identifiable {
        let id: String
        let passed: Bool
        let text: String
    }

    let spec: JSON
    /// Backend artifact id, supplied when this view is rendered inline in tutor chat.
    /// When present together with `onEvidence`, input changes are debounced and posted
    /// to `/interactive/evidence`. Both are optional so the playground's local preview
    /// (which has no artifact to record against) keeps working unchanged.
    let artifactID: String?
    let onEvidence: (([String: JSON]) -> Void)?

    @State private var values: [String: JSON] = [:]
    @State private var touched: Set<String> = []

    init(spec: JSON, artifactID: String? = nil,
         onEvidence: (([String: JSON]) -> Void)? = nil) {
        self.spec = spec
        self.artifactID = artifactID
        self.onEvidence = onEvidence
        var initial: [String: JSON] = [:]
        for component in spec["components"].array {
            let id = component["id"].string
            guard !id.isEmpty else { continue }
            switch component.text("type") {
            case "slider", "number":
                initial[id] = .number(Self.initialNumber(component))
            case "choice":
                let options = component["options"].array.map(\.string)
                let fallback = component["initial"].string.isEmpty
                    ? (options.first ?? "") : component["initial"].string
                initial[id] = .string(fallback)
            default:
                break
            }
        }
        _values = State(initialValue: initial)
    }

    var body: some View {
        let reading = frame()
        VStack(alignment: .leading, spacing: 15) {
            Text(spec.text("title", fallback: "Interactive probe"))
                .font(.system(size: 17, weight: .semibold))
            ForEach(Array(spec["components"].array.enumerated()), id: \.offset) { _, component in
                componentView(component, readouts: reading.readouts,
                              feedback: reading.feedback)
            }
            Divider()
            Text("Interaction evidence: \(touched.count) input(s) moved, "
                 + "\(reading.feedback.filter(\.passed).count)/\(reading.feedback.count) "
                 + "authored checks passing. This is not a grade or a receipt-bound attempt.")
                .font(.system(size: 10))
                .foregroundStyle(Palette.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityIdentifier("declarative.interactive")
        // Debounce evidence to the backend after the learner changes an input.
        // `values` is the id so rapid adjustments cancel the pending send and only
        // the settled state is posted. The empty `touched` guard keeps the initial
        // mount (which has not been interacted with) from recording a frame.
        .task(id: values) {
            guard !touched.isEmpty, artifactID != nil, let onEvidence else { return }
            try? await Task.sleep(nanoseconds: 350_000_000)
            guard !Task.isCancelled, !touched.isEmpty else { return }
            // Only the learner's input values travel - never readouts or feedback.
            onEvidence(values)
        }
    }

    @ViewBuilder
    private func componentView(_ component: JSON, readouts: [String: JSON],
                               feedback: [FeedbackLine]) -> some View {
        let id = component["id"].string
        switch component.text("type") {
        case "text":
            Text(component.text("content"))
                .font(.system(size: 12))
                .foregroundStyle(Palette.secondary)
                .fixedSize(horizontal: false, vertical: true)
        case "slider":
            let lowerBound = component["min"].double
            let upperBound = component["max"].double
            let step = Swift.max(0.01, component["step"].double)
            let binding = Binding<Double>(
                get: { Self.clamped(values[id]?.double ?? Self.initialNumber(component),
                                    min: lowerBound, max: upperBound) },
                set: { values[id] = .number($0); touched.insert(id) })
            VStack(alignment: .leading, spacing: 5) {
                HStack {
                    Text(component.text("label")).font(.system(size: 12, weight: .medium))
                    Spacer()
                    Text(Self.format(.number(binding.wrappedValue)))
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(Palette.accentTeal.deep)
                }
                Slider(value: binding, in: lowerBound...upperBound, step: step)
                    .accessibilityIdentifier("declarative.input." + id)
            }
        case "number":
            let lowerBound = component["min"].double
            let upperBound = component["max"].double
            let step = Swift.max(1, component["step"].double)
            let binding = Binding<Double>(
                get: { Self.clamped(values[id]?.double ?? Self.initialNumber(component),
                                    min: lowerBound, max: upperBound) },
                set: { values[id] = .number($0); touched.insert(id) })
            HStack {
                Text(component.text("label")).font(.system(size: 12, weight: .medium))
                Spacer()
                Stepper(value: binding, in: lowerBound...upperBound, step: step) {
                    Text(Self.format(.number(binding.wrappedValue)))
                        .font(.system(size: 11, design: .monospaced))
                }
                .accessibilityIdentifier("declarative.input." + id)
            }
        case "choice":
            let options = component["options"].array.map(\.string)
            let fallback = component["initial"].string.isEmpty
                ? (options.first ?? "") : component["initial"].string
            let binding = Binding<String>(
                get: { values[id]?.string.isEmpty == false ? (values[id]?.string ?? fallback) : fallback },
                set: { values[id] = .string($0); touched.insert(id) })
            VStack(alignment: .leading, spacing: 5) {
                Text(component.text("label")).font(.system(size: 12, weight: .medium))
                Picker(component.text("label"), selection: binding) {
                    ForEach(options, id: \.self) { Text($0).tag($0) }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .accessibilityIdentifier("declarative.input." + id)
            }
        case "readout":
            let value = readouts[id] ?? .number(0)
            HStack {
                Text(component.text("label")).font(.system(size: 12))
                Spacer()
                Text(Self.format(value))
                    .font(.system(size: 14, weight: .semibold, design: .monospaced))
                    .foregroundStyle(Palette.accentIndigo.deep)
            }
            .accessibilityIdentifier("declarative.readout." + id)
        case "feedback":
            if let line = feedback.first(where: { $0.id == id }) {
                feedbackView(line)
            } else {
                EmptyView()
            }
        case "reset":
            Button(component.text("label", fallback: "Reset")) { reset() }
                .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
                .accessibilityIdentifier("declarative.reset")
        default:
            EmptyView()
        }
    }

    private func feedbackView(_ line: FeedbackLine) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: line.passed ? "checkmark.circle" : "arrow.triangle.2.circlepath")
                .foregroundStyle(line.passed ? Palette.forest : Palette.accentOchre.deep)
            Text(line.text)
                .font(.system(size: 11))
                .foregroundStyle(Palette.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(10)
        .background((line.passed ? Palette.sage : Palette.accentOchre.soft).opacity(0.35),
                    in: RoundedRectangle(cornerRadius: 10))
        .accessibilityIdentifier("declarative.feedback." + line.id)
    }

    private func frame() -> (readouts: [String: JSON], feedback: [FeedbackLine]) {
        var readouts: [String: JSON] = [:]
        var feedback: [FeedbackLine] = []
        for component in spec["components"].array {
            let id = component["id"].string
            switch component.text("type") {
            case "readout":
                readouts[id] = evaluate(component["expr"], readouts)
            case "feedback":
                let passed = evaluate(component["when"], readouts).bool
                feedback.append(FeedbackLine(
                    id: id, passed: passed,
                    text: passed ? component.text("correct") : component.text("incorrect")))
            default:
                break
            }
        }
        return (readouts, feedback)
    }

    private func evaluate(_ node: JSON, _ readouts: [String: JSON]) -> JSON {
        switch node {
        case .number, .string, .bool:
            return node
        case .null:
            return .number(0)
        case .array, .object:
            break
        }
        if !node["const"].isNull { return node["const"] }
        let ref = node["ref"].string
        if !ref.isEmpty { return readouts[ref] ?? values[ref] ?? .number(0) }
        let args = node["args"].array.map { evaluate($0, readouts) }
        switch node.text("op") {
        case "add": return .number(args.reduce(0.0) { $0 + Self.number($1) })
        case "sub": return .number(Self.number(args[0]) - Self.number(args[1]))
        case "mul": return .number(args.reduce(1.0) { $0 * Self.number($1) })
        case "div":
            let denominator = Self.number(args[1])
            return .number(abs(denominator) < 1e-12 ? 0 : Self.number(args[0]) / denominator)
        case "min": return .number(args.map(Self.number).min() ?? 0)
        case "max": return .number(args.map(Self.number).max() ?? 0)
        case "abs": return .number(abs(Self.number(args[0])))
        case "eq": return .bool(args[0] == args[1])
        case "ne": return .bool(args[0] != args[1])
        case "lt": return .bool(Self.number(args[0]) < Self.number(args[1]))
        case "le": return .bool(Self.number(args[0]) <= Self.number(args[1]))
        case "gt": return .bool(Self.number(args[0]) > Self.number(args[1]))
        case "ge": return .bool(Self.number(args[0]) >= Self.number(args[1]))
        case "and": return .bool(args.allSatisfy { $0.bool })
        case "or": return .bool(args.contains { $0.bool })
        case "not": return .bool(!args[0].bool)
        default: return .number(0)
        }
    }

    private func reset() {
        for component in spec["components"].array {
            let id = component["id"].string
            guard !id.isEmpty else { continue }
            switch component.text("type") {
            case "slider", "number":
                values[id] = .number(Self.initialNumber(component))
            case "choice":
                values[id] = .string(component["initial"].string)
            default:
                break
            }
        }
        touched = []
    }

    private static func initialNumber(_ component: JSON) -> Double {
        let min = component["min"].double
        let max = component["max"].double
        let fallback = component["initial"].isNull ? min : component["initial"].double
        return clamped(fallback, min: min, max: max)
    }

    private static func clamped(_ value: Double, min: Double, max: Double) -> Double {
        Swift.min(max, Swift.max(min, value))
    }

    private static func number(_ value: JSON) -> Double {
        switch value {
        case .number(let n): return n
        case .bool(let b): return b ? 1 : 0
        case .string(let s): return Double(s) ?? 0
        default: return 0
        }
    }

    private static func format(_ value: JSON) -> String {
        switch value {
        case .number(let n): return String(format: "%g", n)
        case .bool(let b): return b ? "true" : "false"
        default: return value.string
        }
    }
}
