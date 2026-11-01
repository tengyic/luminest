import SwiftUI
import AppKit

// The board canvas: SwiftUI node views over a Canvas ink layer, with an AppKit event
// bridge underneath that owns the gestures SwiftUI cannot express well on macOS —
// scroll-wheel panning, ⌘-scroll and pinch zoom at the cursor, and tablet pressure.
//
// NOTE: `BoardKit.swift` declares a richer `BoardTool` for the new editor model. This is the
// canvas's own tighter tool set, so it is scoped as `CanvasTool` to keep both compiling while
// the canvas is being migrated onto the shared model. Do not re-merge them here.

enum CanvasTool: String, CaseIterable, Identifiable {
    case select, pen, highlighter, eraser, text, shape, lasso
    var id: String { rawValue }
    var icon: String {
        switch self {
        case .select: return "cursorarrow"
        case .pen: return "pencil.tip"
        case .highlighter: return "highlighter"
        case .eraser: return "eraser"
        case .text: return "textformat"
        case .shape: return "square.on.circle"
        case .lasso: return "lasso"
        }
    }
    var label: String {
        switch self {
        case .select: return "Select & move"
        case .pen: return "Pen"
        case .highlighter: return "Highlighter"
        case .eraser: return "Eraser"
        case .text: return "Text"
        case .shape: return "Shape"
        case .lasso: return "Circle & ask"
        }
    }
}

struct CanvasView: View {
    @ObservedObject var board: BoardStore
    let conceptID: String

    // viewport: board coordinates at the centre of the view, plus a zoom factor.
    @State private var centre = CGPoint(x: 3000, y: 2000)
    @State private var zoom: CGFloat = 1
    @State private var tool: CanvasTool = .select
    @State private var inkColour = Color(hexString: "#1d4ed8")
    @State private var shapeKind = "rect"

    // in-progress stroke / lasso / shape, in board coordinates
    @State private var livePoints: [CGPoint] = []
    @State private var livePressure: [CGFloat] = []
    @State private var liveShape: CGRect?
    @State private var lassoPath: [CGPoint] = []
    @State private var draggingNodeID: String?
    @State private var dragOrigin: CGPoint?
    @State private var nodeDragStart: CGPoint?

    @State private var askingQuestion = false
    @State private var questionDraft = ""
    @State private var textDraft = ""
    @State private var pendingTextPoint: CGPoint?
    @State private var pendingLasso: (points: [CGPoint], rect: CGRect)?
    @State private var askingBusy = false

    private let inkWidth: CGFloat = 2.6

    var body: some View {
        VStack(spacing: 0) {
            toolbar
            Divider()
            ZStack {
                // The bridge is the interaction surface; the SwiftUI layers above it
                // are pure renderers fed by the same state the bridge mutates.
                EventBridge(
                    onScroll: handleScroll,
                    onMagnify: handleMagnify,
                    onPress: handlePress,
                    onDrag: handleDrag,
                    onRelease: handleRelease
                )
                nodeLayer.allowsHitTesting(false)
                inkLayer.allowsHitTesting(false)
                overlayLayer.allowsHitTesting(false)
                if askingBusy { ProgressView("The tutor is reading your selection…") }
            }
            .background(Color.white)
            .clipped()
            .overlay(RoundedRectangle(cornerRadius: 0).stroke(Palette.line))
        }
        .sheet(isPresented: $askingQuestion, onDismiss: { pendingLasso = nil }) { askSheet }
        .sheet(isPresented: Binding(get: { pendingTextPoint != nil },
                                    set: { if !$0 { pendingTextPoint = nil } })) { textSheet }
    }

    // ---------------------------------------------------------------- toolbar

    private var toolbar: some View {
        HStack(spacing: 8) {
            ForEach(CanvasTool.allCases) { candidate in
                Button {
                    tool = candidate
                } label: {
                    Label(candidate.label, systemImage: candidate.icon)
                        .labelStyle(IconOnlyLabelStyle())
                        .padding(6)
                        .background(tool == candidate ? Palette.sage.opacity(0.7) : Color.clear,
                                    in: RoundedRectangle(cornerRadius: 8))
                }
                .buttonStyle(.plain)
                .help(candidate.label)
            }
            Divider().frame(height: 18)
            if tool == .pen || tool == .highlighter {
                Circle().fill(inkColour).frame(width: 16, height: 16)
                ColorPicker("", selection: $inkColour, supportsOpacity: false).labelsHidden().frame(width: 30)
            }
            if tool == .shape {
                Picker("", selection: $shapeKind) {
                    Text("Rectangle").tag("rect")
                    Text("Ellipse").tag("ellipse")
                    Text("Arrow").tag("arrow")
                }.labelsHidden().frame(width: 110)
            }
            Spacer()
            if !board.rollup.isNull && board.rollup["share_alike"].bool {
                Tag(text: "MIXED BOARD · SA", color: Palette.peachDeep)
            }
            Text(String(format: "%.2f×", zoom))
                .font(.system(size: 10, design: .monospaced)).foregroundStyle(Palette.secondary)
        }
        .padding(.horizontal, 10).padding(.vertical, 7)
        .background(.regularMaterial)
    }

    // ---------------------------------------------------------------- transforms

    /// board point → view point
    private func toView(_ point: CGPoint, in size: CGSize) -> CGPoint {
        CGPoint(x: (point.x - centre.x) * zoom + size.width / 2,
                y: (point.y - centre.y) * zoom + size.height / 2)
    }

    /// view point → board point
    private func toBoard(_ point: CGPoint, in size: CGSize) -> CGPoint {
        CGPoint(x: (point.x - size.width / 2) / zoom + centre.x,
                y: (point.y - size.height / 2) / zoom + centre.y)
    }

    private func handleScroll(delta: CGVector, location: CGPoint, size: CGSize, command: Bool) {
        if command {
            // Zoom at the cursor: keep the board point under the cursor fixed.
            let before = toBoard(location, in: size)
            let factor = delta.dy > 0 ? 0.9 : 1.1
            zoom = min(6, max(0.2, zoom * factor))
            let after = toBoard(location, in: size)
            centre = CGPoint(x: centre.x + (before.x - after.x), y: centre.y + (before.y - after.y))
        } else {
            centre = CGPoint(x: centre.x - delta.dx / zoom, y: centre.y - delta.dy / zoom)
        }
    }

    private func handleMagnify(scale: CGFloat, location: CGPoint, size: CGSize) {
        let before = toBoard(location, in: size)
        zoom = min(6, max(0.2, zoom * scale))
        let after = toBoard(location, in: size)
        centre = CGPoint(x: centre.x + (before.x - after.x), y: centre.y + (before.y - after.y))
    }

    // ---------------------------------------------------------------- pointer

    private func handlePress(location: CGPoint, size: CGSize, pressure: CGFloat) {
        let boardPoint = toBoard(location, in: size)
        switch tool {
        case .select:
            // Topmost node under the cursor (nodes render in ascending z; hit-test backwards).
            if let hit = board.nodes.last(where: { $0.hitTest(boardPoint) }) {
                draggingNodeID = hit.id
                dragOrigin = boardPoint
                nodeDragStart = CGPoint(x: hit.x, y: hit.y)
            }
        case .pen, .highlighter:
            livePoints = [boardPoint]
            livePressure = [pressure]
        case .eraser:
            if let hit = board.nodes.last(where: { $0.hitTest(boardPoint) }) {
                board.delete(id: hit.id)
            }
        case .text:
            pendingTextPoint = boardPoint
            textDraft = ""
        case .shape:
            liveShape = CGRect(origin: boardPoint, size: .zero)
        case .lasso:
            lassoPath = [boardPoint]
        }
    }

    private func handleDrag(location: CGPoint, size: CGSize, pressure: CGFloat) {
        let boardPoint = toBoard(location, in: size)
        switch tool {
        case .select:
            if let draggingNodeID, let dragOrigin, let nodeDragStart,
               let index = board.nodes.firstIndex(where: { $0.id == draggingNodeID }) {
                board.nodes[index].x = nodeDragStart.x + (boardPoint.x - dragOrigin.x)
                board.nodes[index].y = nodeDragStart.y + (boardPoint.y - dragOrigin.y)
            }
        case .pen, .highlighter:
            guard let last = livePoints.last, hypot(last.x - boardPoint.x, last.y - boardPoint.y) > 1 else { return }
            livePoints.append(boardPoint)
            livePressure.append(pressure)
        case .lasso:
            guard let last = lassoPath.last, hypot(last.x - boardPoint.x, last.y - boardPoint.y) > 2 else { return }
            lassoPath.append(boardPoint)
        case .shape:
            if let origin = liveShape?.origin {
                liveShape = CGRect(x: min(origin.x, boardPoint.x), y: min(origin.y, boardPoint.y),
                                   width: abs(boardPoint.x - origin.x), height: abs(boardPoint.y - origin.y))
            }
        default: break
        }
    }

    private func handleRelease(location: CGPoint, size: CGSize) {
        let boardPoint = toBoard(location, in: size)
        defer {
            livePoints = []; livePressure = []; liveShape = nil
            lassoPath = []; draggingNodeID = nil; dragOrigin = nil; nodeDragStart = nil
        }
        switch tool {
        case .select:
            if let draggingNodeID, let index = board.nodes.firstIndex(where: { $0.id == draggingNodeID }) {
                let node = board.nodes[index]
                let startX = nodeDragStart.map { Double($0.x) } ?? node.x
                let startY = nodeDragStart.map { Double($0.y) } ?? node.y
                let didMove = abs(node.x - startX) > 0.5 || abs(node.y - startY) > 0.5
                if didMove {
                    board.move(id: node.id, to: CGPoint(x: node.x, y: node.y),
                               size: CGSize(width: node.w, height: node.h))
                }
            }
        case .pen, .highlighter:
            guard livePoints.count > 2 else { return }
            let simplified = RDP.simplify(livePoints)
            let averagePressure = livePressure.reduce(0, +) / CGFloat(livePressure.count)
            var payload: [String: Any] = [
                "points": simplified.map { [$0.x, $0.y] },
                "colour": hex(inkColour),
                "width": tool == .highlighter ? 14.0 : inkWidth]
            if averagePressure < 0.98 { payload["pressure"] = Double(averagePressure) }
            let bounds = CGRect(points: simplified).insetBy(dx: -20, dy: -20)
            board.add(node: BoardNode(id: "", kind: "path", x: bounds.minX, y: bounds.minY,
                                      w: bounds.width, h: bounds.height, z: "",
                                      payload: (try? JSON.make(payload)) ?? .null))
        case .shape:
            guard var shape = liveShape, shape.width > 6, shape.height > 6 else { return }
            if shapeKind == "arrow" {
                // Arrow geometry: the drag from top-left to bottom-right of the frame.
                shape = CGRect(x: shape.minX, y: shape.minY, width: shape.width, height: shape.height)
            }
            board.add(node: BoardNode(id: "", kind: "shape", x: shape.minX, y: shape.minY,
                                      w: shape.width, h: shape.height, z: "",
                                      payload: (try? JSON.make(["shape": shapeKind, "colour": hex(inkColour)])) ?? .null))
        case .lasso:
            guard lassoPath.count > 5,
                  let rect = lassoBounds(lassoPath), rect.width > 12, rect.height > 12 else { return }
            pendingLasso = (points: lassoPath, rect: rect)
            questionDraft = ""
            askingQuestion = true
        default: break
        }
    }

    private func lassoBounds(_ points: [CGPoint]) -> CGRect? {
        guard let first = points.first else { return nil }
        var minX = first.x, maxX = first.x, minY = first.y, maxY = first.y
        for point in points {
            minX = min(minX, point.x); maxX = max(maxX, point.x)
            minY = min(minY, point.y); maxY = max(maxY, point.y)
        }
        return CGRect(x: minX, y: minY, width: maxX - minX, height: maxY - minY)
    }

    private func hex(_ colour: Color) -> String {
        let nsColour = NSColor(colour).usingColorSpace(.sRGB) ?? NSColor.black
        return String(format: "#%02x%02x%02x",
                      Int(round(nsColour.redComponent * 255)),
                      Int(round(nsColour.greenComponent * 255)),
                      Int(round(nsColour.blueComponent * 255)))
    }

    // ---------------------------------------------------------------- layers

    @ViewBuilder
    private var nodeLayer: some View {
        GeometryReader { proxy in
            ZStack(alignment: .topLeading) {
                ForEach(board.nodes) { node in
                    NodeView(node: node, zoom: zoom)
                        .scaleEffect(zoom, anchor: .topLeading)
                        .offset(x: toView(CGPoint(x: node.x, y: node.y), in: proxy.size).x,
                                y: toView(CGPoint(x: node.x, y: node.y), in: proxy.size).y)
                }
            }
        }
    }

    @ViewBuilder
    private var inkLayer: some View {
        GeometryReader { proxy in
            Canvas { context, _ in
                for node in board.nodes where node.kind == "path" {
                    drawStroke(node.payload, in: &context, proxy: proxy)
                }
                if livePoints.count > 1 {
                    var payload: JSON = .null
                    var points: [[JSON]] = []
                    for (index, point) in livePoints.enumerated() {
                        points.append([.number(point.x), .number(point.y),
                                       .number(Double(livePressure[min(index, livePressure.count - 1)]))])
                    }
                    payload = (try? JSON.make(["points": points, "colour": hex(inkColour),
                                               "width": tool == .highlighter ? 14.0 : inkWidth,
                                               "pressure": Double(livePressure.last ?? 0.5)])) ?? .null
                    drawStroke(payload, in: &context, proxy: proxy)
                }
                if let shape = liveShape {
                    let path = Path(shapeRect(shape))
                    context.stroke(path, with: .color(inkColour.opacity(0.8)), lineWidth: 2)
                }
                if lassoPath.count > 2 {
                    var path = Path()
                    path.addLines(lassoPath.map { toView($0, in: proxy.size) })
                    path.closeSubpath()
                    context.fill(path, with: .color(Palette.forest.opacity(0.12)))
                    context.stroke(path, with: .color(Palette.forest), style: StrokeStyle(lineWidth: 1.5, dash: [5, 4]))
                }
            }
        }
    }

    private func shapeRect(_ shape: CGRect) -> CGRect {
        CGRect(x: toView(shape.origin, in: .zero).x, y: toView(shape.origin, in: .zero).y,
               width: shape.width * zoom, height: shape.height * zoom)
    }

    private func drawStroke(_ payload: JSON, in context: inout GraphicsContext, proxy: GeometryProxy) {
        let raw = payload["points"].array.compactMap { pair -> PerfectFreehand.InputPoint? in
            let values = pair.array
            guard values.count >= 2 else { return nil }
            let pressure = values.count >= 3 && values[2].double.isFinite ? CGFloat(values[2].double) : 0.5
            return PerfectFreehand.InputPoint(point: CGPoint(x: values[0].double, y: values[1].double),
                                              pressure: pressure)
        }
        guard raw.count > 1 else { return }
        let width = payload["width"].double.isFinite ? CGFloat(payload["width"].double) : inkWidth
        let colour = Color(hexString: payload["colour"].string.isEmpty ? "#1d1d1f" : payload["colour"].string)
        let effective = tool == .highlighter || payload["width"].double == 14 ? colour.opacity(0.35) : colour
        var options = PerfectFreehand.Options()
        options.size = width * 4
        options.thinning = 0.6
        options.simulatePressure = false
        let outline = PerfectFreehand.stroke(raw, options: options)
        guard outline.count > 2 else { return }
        var path = Path()
        path.move(to: toView(outline[0], in: proxy.size))
        for point in outline.dropFirst() { path.addLine(to: toView(point, in: proxy.size)) }
        path.closeSubpath()
        context.fill(path, with: .color(effective))
    }

    @ViewBuilder
    private var overlayLayer: some View {
        if askingQuestion || pendingTextPoint != nil { Color.black.opacity(0.08) }
    }

    // ---------------------------------------------------------------- sheets

    private var textSheet: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Add text at the click point").font(.system(size: 14, weight: .semibold))
            TextField("Type the text", text: $textDraft)
                .textFieldStyle(.roundedBorder)
            HStack {
                Spacer()
                Button("Cancel") { pendingTextPoint = nil }.keyboardShortcut(.cancelAction)
                Button("Add") {
                    if let point = pendingTextPoint, !textDraft.trimmingCharacters(in: .whitespaces).isEmpty {
                        board.add(node: BoardNode(id: "", kind: "text", x: point.x, y: point.y,
                                                  w: 0, h: 0, z: "",
                                                  payload: (try? JSON.make(["text": textDraft, "size": 18.0])) ?? .null))
                    }
                    pendingTextPoint = nil
                }.keyboardShortcut(.defaultAction).buttonStyle(LuminfestButtonStyle())
            }
        }
        .padding(20).frame(width: 380)
    }

    private var askSheet: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("Ask the tutor about this selection", systemImage: "lasso.and.sparkles")
                .font(.system(size: 14, weight: .semibold))
            Text("The selected region is captured as an image and sent with your question. The answer is pinned back onto the board where you circled.")
                .font(.system(size: 11)).foregroundStyle(Palette.secondary)
            TextEditor(text: $questionDraft)
                .font(.system(size: 12)).scrollContentBackground(.hidden)
                .padding(7).frame(height: 84)
                .background(Palette.background, in: RoundedRectangle(cornerRadius: 10))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(Palette.line))
            HStack {
                Spacer()
                Button("Cancel") { askingQuestion = false }.keyboardShortcut(.cancelAction)
                Button {
                    ask()
                } label: {
                    HStack { Text(askingBusy ? "Thinking…" : "Ask"); if askingBusy { ProgressView().controlSize(.small) } }
                }
                .keyboardShortcut(.defaultAction)
                .buttonStyle(LuminfestButtonStyle())
                .disabled(askingBusy || questionDraft.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        .padding(20).frame(width: 430)
    }

    private func ask() {
        guard let lasso = pendingLasso else { askingQuestion = false; return }
        askingBusy = true
        let question = questionDraft
        let rect = lasso.rect.insetBy(dx: -12, dy: -12)
        let nodes = board.nodes.filter { $0.frame.intersects(rect) }
        Task { [board] in
            defer { askingBusy = false }
            // The snapshot is the ground truth the tutor reads: it is composited from
            // the same renderer the PDF export uses, so what the model sees is exactly
            // what the learner sees (minus embeds, which are chips for licence reasons).
            guard let image = BoardRenderer.image(of: nodes, in: rect),
                  let tiff = image.tiffRepresentation,
                  let rep = NSBitmapImageRep(data: tiff),
                  let png = rep.representation(using: .png, properties: [:]) else {
                board.error = "The selection could not be captured; nothing was asked."
                askingQuestion = false
                return
            }
            let dataURL = "data:image/png;base64," + png.base64EncodedString()
            do {
                guard let api = AppStore.current?.api else { return }
                var body: [String: Any] = [
                    "message": question,
                    "developer_mode": false,
                    "context": ["concept_id": conceptID, "board_id": board.boardID],
                    "images": [dataURL]]
                let result = try await api.json("/agent/chat", method: "POST", body: body)
                let answer = result["message"].string
                guard !answer.isEmpty else {
                    board.error = "The tutor turn finished without a reply; the selection was not answered."
                    askingQuestion = false
                    return
                }
                // The client-side hash is the anchor's provenance: the answer node
                // records which snapshot it answered.
                let sha = sha256Hex(png)
                board.pinAnswer(text: answer, question: question, imageSHA: sha,
                                at: CGPoint(x: rect.maxX + 24, y: rect.minY))
                askingQuestion = false
            } catch {
                board.error = error.localizedDescription
                askingQuestion = false
            }
        }
    }

    private func sha256Hex(_ data: Data) -> String {
        #if canImport(CryptoKit)
        let digest = CryptoSHA256.digest(data)
        return digest.map { String(format: "%02x", $0) }.joined()
        #else
        return ""
        #endif
    }
}

// The event bridge: an NSView that owns what SwiftUI on macOS still does not —
// scroll-wheel panning, pinch magnification at the cursor, and NSEvent tablet pressure.
private struct EventBridge: NSViewRepresentable {
    var onScroll: (CGVector, CGPoint, CGSize, Bool) -> Void
    var onMagnify: (CGFloat, CGPoint, CGSize) -> Void
    var onPress: (CGPoint, CGSize, CGFloat) -> Void
    var onDrag: (CGPoint, CGSize, CGFloat) -> Void
    var onRelease: (CGPoint, CGSize) -> Void

    func makeNSView(context: Context) -> BridgeView {
        let view = BridgeView()
        view.onScroll = onScroll
        view.onMagnify = onMagnify
        view.onPress = onPress
        view.onDrag = onDrag
        view.onRelease = onRelease
        return view
    }

    func updateNSView(_ view: BridgeView, context: Context) {
        view.onScroll = onScroll
        view.onMagnify = onMagnify
        view.onPress = onPress
        view.onDrag = onDrag
        view.onRelease = onRelease
    }

    final class BridgeView: NSView {
        var onScroll: ((CGVector, CGPoint, CGSize, Bool) -> Void)?
        var onMagnify: ((CGFloat, CGPoint, CGSize) -> Void)?
        var onPress: ((CGPoint, CGSize, CGFloat) -> Void)?
        var onDrag: ((CGPoint, CGSize, CGFloat) -> Void)?
        var onRelease: ((CGPoint, CGSize) -> Void)?
        private var pressure: CGFloat = 0.5

        override func scrollWheel(with event: NSEvent) {
            guard let onScroll else { super.scrollWheel(with: event); return }
            onScroll(CGVector(dx: event.scrollingDeltaX, dy: event.scrollingDeltaY),
                     convert(event.locationInWindow, from: nil), bounds.size,
                     event.modifierFlags.contains(.command))
        }

        override func magnify(with event: NSEvent) {
            guard let onMagnify else { super.magnify(with: event); return }
            onMagnify(1 + event.magnification,
                      convert(event.locationInWindow, from: nil), bounds.size)
        }

        override func mouseDown(with event: NSEvent) {
            // A mouse reports pressure 1.0 on click; treat that as the neutral 0.5.
            let reported = CGFloat(event.pressure)
            pressure = reported <= 0.01 || reported >= 0.99 ? 0.5 : reported
            onPress?(convert(event.locationInWindow, from: nil), bounds.size, pressure)
        }

        override func mouseDragged(with event: NSEvent) {
            // Tablet pressure arrives on drag events; a mouse reports 1.0 clamped to 0.5 here.
            let reported = CGFloat(event.pressure)
            if reported > 0.01 && reported < 0.99 { pressure = reported }
            onDrag?(convert(event.locationInWindow, from: nil), bounds.size, pressure)
        }

        override func mouseUp(with event: NSEvent) {
            onRelease?(convert(event.locationInWindow, from: nil), bounds.size)
        }

        override var acceptsFirstResponder: Bool { true }
    }
}

extension BoardNode {
    /// Hit-testing in board coordinates, generous on small nodes so a click lands.
    func hitTest(_ point: CGPoint) -> Bool {
        switch kind {
        case "path":
            let points = payload["points"].array.compactMap { pair -> CGPoint? in
                let values = pair.array
                guard values.count == 2 else { return nil }
                return CGPoint(x: values[0].double, y: values[1].double)
            }
            return points.contains { hypot($0.x - point.x, $0.y - point.y) < 14 }
        case "connector":
            let a = CGPoint(x: payload["x"].double, y: payload["y"].double)
            let b = CGPoint(x: payload["x2"].double, y: payload["y2"].double)
            let length = hypot(b.x - a.x, b.y - a.y)
            guard length > 0 else { return hypot(point.x - a.x, point.y - a.y) < 14 }
            let t = max(0, min(1, ((point.x - a.x) * (b.x - a.x) + (point.y - a.y) * (b.y - a.y)) / (length * length)))
            let projection = CGPoint(x: a.x + t * (b.x - a.x), y: a.y + t * (b.y - a.y))
            return hypot(point.x - projection.x, point.y - projection.y) < 12
        case "text":
            return CGRect(x: x - 8, y: y - 8, width: max(w, 120) + 16, height: max(h, 24) + 16).contains(point)
        default:
            return frame.insetBy(dx: -6, dy: -6).contains(point)
        }
    }
}

/// One rendered node. Paths render in the ink layer; everything else is a view.
struct NodeView: View {
    let node: BoardNode
    let zoom: CGFloat

    var body: some View {
        switch node.kind {
        case "path": Color.clear.frame(width: max(node.w, 1), height: max(node.h, 1))
        case "text": textView
        case "shape": shapeView
        case "connector": Color.clear.frame(width: 1, height: 1)
        case "image": imageView
        case "video": videoView
        case "simulation": simulationView
        case "answer": answerView
        default: Color.clear.frame(width: max(node.w, 1), height: max(node.h, 1))
        }
    }

    private var textView: some View {
        Text(node.payload["text"].string)
            .font(.system(size: min(96, max(9, node.payload["size"].double.isFinite ? node.payload["size"].double : 16))))
            .fixedSize(horizontal: false, vertical: true)
            .frame(width: node.w > 0 ? node.w : nil, alignment: .leading)
            .textSelection(.enabled)
    }

    private var shapeView: some View {
        let colour = Color(hexString: node.payload["colour"].string.isEmpty ? "#1d1d1f" : node.payload["colour"].string)
        return Group {
            switch node.payload["shape"].string {
            case "ellipse": Ellipse().stroke(colour, lineWidth: 2)
            case "arrow":
                ArrowShape().stroke(colour, style: StrokeStyle(lineWidth: 2, lineCap: .round))
            default: RoundedRectangle(cornerRadius: 3).stroke(colour, lineWidth: 2)
            }
        }
        .frame(width: max(node.w, 4), height: max(node.h, 4))
    }

    private var imageView: some View {
        let sha = node.payload["sha256"].string
        return Group {
            if let data = ImageCache.shared.data(sha: sha), let image = NSImage(data: data) {
                Image(nsImage: image).resizable().scaledToFill()
            } else {
                ZStack {
                    Rectangle().fill(Palette.muted)
                    Text("image unavailable").font(.system(size: 11)).foregroundStyle(Palette.secondary)
                }
            }
        }
        .frame(width: max(node.w, 40), height: max(node.h, 40))
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .overlay(alignment: .bottom) {
            if !node.payload["credit"].string.isEmpty {
                Text(node.payload["credit"].string)
                    .font(.system(size: 8)).foregroundStyle(Palette.tertiary)
                    .padding(.horizontal, 5).padding(.vertical, 2)
                    .background(.thinMaterial)
            }
        }
    }

    private var videoView: some View {
        VStack(alignment: .leading, spacing: 6) {
            if node.payload["status"].string == "verified_embed",
               let url = MediaEmbed.url(node.payload["embed_url"].string) {
                EmbeddedLessonWebView(url: url)
            } else if node.payload["status"].string == "withheld" {
                let reason = node.payload["withheld_reason"].string
                Text(reason.isEmpty ? "Withheld under the current rights position." : reason)
                    .font(.system(size: 11)).foregroundStyle(Palette.secondary)
            } else {
                Text("Embedding could not be verified; this video opens in the browser.")
                    .font(.system(size: 11)).foregroundStyle(Palette.secondary)
            }
            SafeLessonLink(title: "Open video", rawURL: node.payload["watch_url"].string)
        }
        .padding(8)
        .frame(width: max(node.w, 220), height: max(node.h, 160), alignment: .topLeading)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Palette.line))
    }

    private var simulationView: some View {
        VStack(alignment: .leading, spacing: 6) {
            if node.payload["status"].string == "verified_embed",
               node.payload["provider"].string == "phet",
               let url = MediaEmbed.url(node.payload["url"].string) {
                EmbeddedLessonWebView(url: url)
            } else {
                Text(node.payload["provider"].string == "gizmos"
                     ? "Gizmos is deep-link only: it opens in your own signed-in session."
                     : "This simulation opens in the browser.")
                    .font(.system(size: 11)).foregroundStyle(Palette.secondary)
            }
            SafeLessonLink(title: "Open simulation", rawURL: node.payload["url"].string)
        }
        .padding(8)
        .frame(width: max(node.w, 260), height: max(node.h, 200), alignment: .topLeading)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Palette.line))
    }

    private var answerView: some View {
        VStack(alignment: .leading, spacing: 8) {
            if !node.payload["question"].string.isEmpty {
                Text("Q: " + node.payload["question"].string)
                    .font(.system(size: 11, weight: .semibold)).foregroundStyle(Palette.accentLavender.deep)
            }
            Text(node.payload["text"].string)
                .font(.system(size: 12)).lineSpacing(4)
                .fixedSize(horizontal: false, vertical: true)
                .textSelection(.enabled)
            if !node.payload["image_sha256"].string.isEmpty {
                Label("Answered from a board snapshot", systemImage: "photo.on.rectangle.angled")
                    .font(.system(size: 9)).foregroundStyle(Palette.tertiary)
            }
        }
        .padding(12)
        .frame(width: max(node.w, 320), alignment: .topLeading)
        .background(Palette.lavender.opacity(0.5), in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Palette.accentLavender.deep.opacity(0.5)))
    }
}

struct ArrowShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.minX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX - 9, y: rect.maxY - 2))
        path.move(to: CGPoint(x: rect.maxX - 9, y: rect.maxY - 2))
        path.addLine(to: CGPoint(x: rect.maxX - 14, y: rect.maxY - 9))
        path.move(to: CGPoint(x: rect.maxX - 9, y: rect.maxY - 2))
        path.addLine(to: CGPoint(x: rect.maxX - 17, y: rect.maxY + 1))
        return path
    }
}

#if canImport(CryptoKit)
import CryptoKit
enum CryptoSHA256 {
    static func digest(_ data: Data) -> [UInt8] {
        Array(SHA256.hash(data: data))
    }
}
#endif
