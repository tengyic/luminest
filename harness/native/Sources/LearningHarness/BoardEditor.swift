import SwiftUI
import AppKit

// The Stage whiteboard, rebuilt as a real editor.
//
// What replaced it: a `BoardPane` with a pen, three fixed colours, and a DragGesture
// that required a deliberate click-drag to lay down a stroke. That is the "hard touch"
// complaint verbatim — a trackpad click is a commitment, so people drew slowly or not
// at all. This editor is built on four changes that address it directly:
//
//   1. **Pressure comes from the hardware where the hardware reports it**, and is
//      otherwise *derived from velocity*. A trackpad reports pressure exactly 1.0 on
//      every click; clamping that to a constant (what the old bridge did) makes every
//      stroke identical. Deriving width from speed instead means a slow light line is
//      bold and a quick flick tapers, which is how a felt tip actually behaves — so a
//      soft touch produces a soft line rather than nothing.
//   2. **No gesture requires a click to begin.** The pen starts on press-down and
//      follows the pointer; there is no minimum travel and no activation threshold.
//   3. **The board is a document, not a list of ops.** Moves, resizes and erases are
//      transmitted as *mutations against node ids*, so the tutor's drawings and the
//      learner's are the same objects rather than two parallel stores.
//   4. **Every edit is undoable.** Undo is a snapshot diff that emits the minimum
//      mutation batch (see ``BoardStore/reconcile(to:)``), so one undo never rewrites
//      the whole board.
//
// Rendering is deliberately *not* shared with the export path. `BoardRenderer` draws
// via AppKit into a flipped context for PNG/PDF; this canvas draws via SwiftUI, where
// the coordinate mapping is the other way up. One renderer serving both would need a
// y-flip at every call site, which is exactly how upside-down text happens. The two
// paths are kept apart on purpose and the PDF export remains the one true compositor.

// MARK: - Eraser modes

/// What the eraser takes off. Defaults to the whole stroke because that is what a person
/// reaching for an eraser expects; the finer modes exist because scrubbing a whole
/// drawing to fix one mark is the other reason people stop drawing on shared boards.
enum BoardEraserMode: String, CaseIterable, Identifiable {
    case stroke, segment

    var id: String { rawValue }

    var label: String {
        switch self {
        case .stroke: return "Whole stroke"
        case .segment: return "Scrub"
        }
    }

    var help: String {
        switch self {
        case .stroke: return "Remove the stroke you touch."
        case .segment: return "Remove only the samples under the pointer, keeping the rest of the stroke."
        }
    }

    var icon: String {
        switch self {
        case .stroke: return "eraser.fill"
        case .segment: return "scissors"
        }
    }
}

// MARK: - Viewport

/// Where the camera is: the board coordinate fixed at the centre of the view, and the
/// scale. One struct so a fit or a zoom-at-cursor is one allocation of the rules rather
/// than four copies of them.
struct BoardViewport {
    var centre = CGPoint(x: 3000, y: 2000)
    var zoom: CGFloat = 0.55

    static let minimumZoom: CGFloat = 0.12
    static let maximumZoom: CGFloat = 7

    /// Board point → view point. The view is centred, not origin-anchored, so panning is
    /// changing `centre` rather than tracking a translation offset.
    func toView(_ point: CGPoint, in size: CGSize) -> CGPoint {
        CGPoint(x: (point.x - centre.x) * zoom + size.width / 2,
                y: (point.y - centre.y) * zoom + size.height / 2)
    }

    func toBoard(_ point: CGPoint, in size: CGSize) -> CGPoint {
        CGPoint(x: (point.x - size.width / 2) / zoom + centre.x,
                y: (point.y - size.height / 2) / zoom + centre.y)
    }

    /// Zoom by a factor while keeping the board point under `location` exactly still.
    ///
    /// Zooming about the view centre is the default in most apps and is why a zoomed-in
    /// canvas always drifts away from whatever you were looking at. Anchoring to the
    /// pointer means the cursor keeps pointing at the same ink.
    mutating func zoom(by factor: CGFloat, at location: CGPoint, in size: CGSize) {
        let anchor = toBoard(location, in: size)
        let target = (zoom * factor).clamped(to: Self.minimumZoom...Self.maximumZoom)
        guard target != zoom else { return }
        zoom = target
        let moved = toBoard(location, in: size)
        centre.x += anchor.x - moved.x
        centre.y += anchor.y - moved.y
    }

    /// Frame the whole board with breathing room. Padding is in board units so the same
    /// margin applies at every zoom level.
    mutating func fit(_ bounds: CGRect, in size: CGSize, padding: CGFloat = 120) {
        guard bounds.width > 0.5, bounds.height > 0.5, size.width > 10, size.height > 10 else { return }
        let inset = bounds.insetBy(dx: -padding, dy: -padding)
        let target = min(size.width / inset.width, size.height / inset.height)
        zoom = target.clamped(to: Self.minimumZoom...Self.maximumZoom)
        centre = CGPoint(x: inset.midX, y: inset.midY)
    }
}

extension Comparable {
    fileprivate func clamped(to range: ClosedRange<Self>) -> Self {
        min(max(self, range.lowerBound), range.upperBound)
    }
}

// MARK: - AppKit event bridge

/// The interaction surface: an `NSView` that owns what SwiftUI on macOS still cannot.
///
/// Two things live here and only here. **Pressure** — a SwiftUI `DragGesture` on macOS
/// reports a location and nothing else; `NSEvent.pressure` is the only way to read the
/// tablet or Force Touch value, and `pressureChange(with:)` is the only way to notice it
/// *change* mid-stroke, which is the whole point of pressure-sensitive ink. **Keyboard
/// and menu actions** — the editor's shortcuts (V/H/P/E/T…. for tools, ⌘Z, ⌘⌫, ⌘[ / ⌘]
/// for stacking) need an actual first responder.
///
/// Touching is intentionally *not* wired: overriding both `touchesBegan` and
/// `mouseDown` on a trackpad would fire both and lay down two strokes for one gesture.
/// macOS delivers tablet and Force Touch pressure on the mouse-drag events already
/// handled below, so there is nothing to gain and a duplicate-stroke bug to lose.
private struct BoardEventBridge: NSViewRepresentable {
    var onScroll: (CGVector, CGPoint, CGSize, Bool) -> Void
    var onMagnify: (CGFloat, CGPoint, CGSize) -> Void
    var onPress: (CGPoint, CGSize, CGFloat) -> Void
    var onDrag: (CGPoint, CGSize, CGFloat) -> Void
    var onRelease: (CGPoint, CGSize) -> Void
    var onRightClick: (CGPoint, CGSize) -> Void
    var onKey: (String, NSEvent.ModifierFlags) -> Void

    func makeNSView(context: Context) -> BridgeView {
        let view = BridgeView()
        view.handlers = Handlers(onScroll: onScroll, onMagnify: onMagnify, onPress: onPress,
                                onDrag: onDrag, onRelease: onRelease,
                                onRightClick: onRightClick, onKey: onKey)
        return view
    }

    func updateNSView(_ view: BridgeView, context: Context) {
        view.handlers = Handlers(onScroll: onScroll, onMagnify: onMagnify, onPress: onPress,
                                onDrag: onDrag, onRelease: onRelease,
                                onRightClick: onRightClick, onKey: onKey)
    }

    struct Handlers {
        var onScroll: (CGVector, CGPoint, CGSize, Bool) -> Void
        var onMagnify: (CGFloat, CGPoint, CGSize) -> Void
        var onPress: (CGPoint, CGSize, CGFloat) -> Void
        var onDrag: (CGPoint, CGSize, CGFloat) -> Void
        var onRelease: (CGPoint, CGSize) -> Void
        var onRightClick: (CGPoint, CGSize) -> Void
        var onKey: (String, NSEvent.ModifierFlags) -> Void
    }

    final class BridgeView: NSView {
        var handlers: Handlers? {
            didSet { window?.makeFirstResponder(self) }
        }

        /// The live pressure of the current stroke. Held across events so a
        /// `pressureChange` without a movement event still updates the stroke.
        private var pressure: CGFloat = 0.5

        override var acceptsFirstResponder: Bool { true }

        // A board is drawn on, so it must not scroll when the pointer reaches an edge.
        override var enclosingScrollView: NSScrollView? { nil }

        override func resetCursorRects() {
            discardCursorRects()
        }

        override func scrollWheel(with event: NSEvent) {
            guard let handlers else { super.scrollWheel(with: event); return }
            handlers.onScroll(CGVector(dx: event.scrollingDeltaX, dy: event.scrollingDeltaY),
                              convert(event.locationInWindow, from: nil), bounds.size,
                              event.modifierFlags.contains(.command))
        }

        override func magnify(with event: NSEvent) {
            guard let handlers else { super.magnify(with: event); return }
            handlers.onMagnify(max(0.01, 1 + event.magnification),
                               convert(event.locationInWindow, from: nil), bounds.size)
        }

        /// Pressure the hardware actually reports, or nil when it is reporting the
        /// saturation value a trackpad always gives.
        ///
        /// A Force Touch trackpad and an Apple Pencil both report a meaningful range;
        /// an ordinary click reports 1.0 and every touch reports 1.0. Treating 1.0 as
        /// data is what produced the old flat strokes, so it is read as "no data" and
        /// the sampler falls back to velocity.
        private func readablePressure(_ event: NSEvent) -> CGFloat? {
            let reported = event.pressure
            guard reported > 0.02, reported < 0.985 else { return nil }
            return CGFloat(min(1, max(0.05, reported)))
        }

        override func mouseDown(with event: NSEvent) {
            window?.makeFirstResponder(self)
            pressure = readablePressure(event) ?? 0.5
            handlers?.onPress(convert(event.locationInWindow, from: nil), bounds.size, pressure)
        }

        override func mouseDragged(with event: NSEvent) {
            if let reported = readablePressure(event) { pressure = reported }
            handlers?.onDrag(convert(event.locationInWindow, from: nil), bounds.size, pressure)
        }

        override func mouseUp(with event: NSEvent) {
            handlers?.onRelease(convert(event.locationInWindow, from: nil), bounds.size)
        }

        /// The pressure changed while the pointer stood still — a finger pressing
        /// harder without moving. Only meaningful mid-stroke, which the editor tracks.
        override func pressureChange(with event: NSEvent) {
            guard event.type == .pressure else { return }
            if let reported = readablePressure(event) {
                pressure = reported
                handlers?.onDrag(convert(event.locationInWindow, from: nil), bounds.size, pressure)
            }
        }

        override func rightMouseDown(with event: NSEvent) {
            window?.makeFirstResponder(self)
            handlers?.onRightClick(convert(event.locationInWindow, from: nil), bounds.size)
        }

        override func keyDown(with event: NSEvent) {
            let characters = event.charactersIgnoringModifiers ?? ""
            guard !characters.isEmpty else { super.keyDown(with: event); return }
            let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
            // An unhandled key must not vanish: an editor that swallows ⌘A or a plain
            // letter is indistinguishable from a frozen one.
            handlers?.onKey(characters, flags)
            if flags.contains(.command) { return }
            super.keyDown(with: event)
        }
    }
}

// MARK: - The editor

struct BoardEditor: View {
    @ObservedObject var board: BoardStore
    let conceptID: String
    /// Only for interaction telemetry: which node kinds the learner actually reaches for.
    /// Nothing on this screen is scored, so this is a reading of attention, not of learning.
    @EnvironmentObject var store: AppStore

    // ---------------------------------------------------------------- tool state
    @State private var tool: BoardTool = .pen
    @State private var colour = "#1d4ed8"
    @State private var width: Double = 2.6
    @State private var eraserMode: BoardEraserMode = .stroke
    @State private var snapToGrid = false
    @State private var gridStep: Double = 40
    @State private var selection = BoardSelection()
    @State private var showLayers = true
    @State private var notice: String?

    // ---------------------------------------------------------------- viewport
    @State private var viewport = BoardViewport()

    // ---------------------------------------------------------------- live gesture
    /// All live-gesture state is in **board** coordinates, never view coordinates, so the
    /// pointer never has to be re-derived after a zoom mid-drag.
    @State private var livePoints: [CGPoint] = []
    @State private var livePressure: [CGFloat] = []
    @State private var liveBox: CGRect?
    @State private var liveConnector: (from: CGPoint, to: CGPoint)?
    @State private var liveLasso: [CGPoint] = []
    @State private var marquee: CGRect?
    @State private var guides: [SnapGuide] = []

    /// Nodes being dragged, with the box each one started at so a snap can be applied to
    /// all of them as one correction.
    @State private var dragIDs: Set<String> = []
    @State private var dragOrigin: CGPoint?
    @State private var dragBase: [String: CGRect] = [:]
    @State private var dragDidMove = false

    @State private var resizeHandle: ResizeHandle?
    @State private var resizeBase: [String: CGRect] = [:]
    @State private var resizeGroup: CGRect?

    // ---------------------------------------------------------------- sheets
    @State private var pendingTextAt: CGPoint?
    @State private var textDraft = ""
    @State private var pendingStickyAt: CGPoint?
    @State private var askingAbout: CGRect?
    @State private var questionDraft = ""
    @State private var askBusy = false
    @State private var showingImages = false
    @State private var pendingDiagramAt: CGPoint?
    @State private var showingCurves = false
    @State private var showingDiagramCatalog = false
    @State private var showingVectorizer = false
    @State private var diagramPrompt = ""
    @State private var catalogItems: [JSON] = []
    @State private var catalogQuery = ""
    @State private var catalogSubject = ""
    @State private var catalogBusy = false
    @State private var vectorizeBusy = false
    @State private var vectorizeThreshold = 145.0
    @State private var vectorizePreview: BoardPreview?
    @State private var vectorizeProgress = 1.0
    @State private var tracePlaying = false
    @State private var stopTracePlayback = false
    @State private var diagramUsesSnapshot = true
    @State private var diagramBusy = false
    @State private var diagramPreview: BoardPreview?
    @State private var pendingCurvePreview: BoardPreview?
    @State private var selectedDiagramTemplateID = "economics.supply-demand"
    @State private var catalogPreview: BoardPreview?
    @State private var curveType = "function"
    @State private var curveExpression = "sin(x)"
    @State private var curveXExpression = "cos(t)"
    @State private var curveYExpression = "sin(t)"
    @State private var curveFourierCosine = "0, 0, 0.6, 0"
    @State private var curveFourierSine = "0, 1"
    @State private var curveXRange = "-10, 10"
    @State private var curveYRange = "-10, 10"
    @State private var curveTRange = "0, 6.283185"
    @State private var vectorizeSource = ""
    @State private var vectorizeAt = CGPoint.zero
    @State private var vectorizeSize = CGSize(width: 760, height: 480)
    @State private var canvasPreviewNodes: [BoardNode] = []

    var body: some View {
        VStack(spacing: 0) {
            toolbar
            Divider()
            canvas
            Divider()
            footer
        }
        .background(Palette.background)
        .sheet(isPresented: $showingImages) { ImagePickerSheet(board: board, conceptID: conceptID, at: insertionPoint) }
        .sheet(isPresented: Binding(get: { pendingTextAt != nil }, set: { if !$0 { pendingTextAt = nil } })) {
            TextSheet(title: "Write on the board", draft: $textDraft) {
                guard !textDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                      let at = pendingTextAt else { return }
                board.beginEdit()
                board.add(node: BoardNode(id: "", kind: "text", x: at.x, y: at.y, w: 320, h: 0, z: "",
                                          payload: (try? JSON.make(["text": textDraft, "size": 16.0])) ?? .null))
                textDraft = ""
            }
        }
        .sheet(isPresented: Binding(get: { askingAbout != nil }, set: { if !$0 { askingAbout = nil } })) { askSheet }
        .sheet(isPresented: Binding(get: { pendingDiagramAt != nil }, set: { if !$0 { pendingDiagramAt = nil } })) {
            diagramSheet
        }
        .sheet(isPresented: $showingCurves) { curveSheet }
        .sheet(isPresented: $showingDiagramCatalog) { diagramCatalogSheet }
        .sheet(isPresented: $showingVectorizer) { vectorizerSheet }
        .onChange(of: showingDiagramCatalog) { _, shown in
            if shown {
                catalogPreview = nil
                Task { await loadDiagramCatalog() }
            } else {
                catalogPreview = nil
                refreshCanvasPreview()
            }
        }
        .onChange(of: showingCurves) { _, shown in
            if !shown { pendingCurvePreview = nil; refreshCanvasPreview() }
        }
        .onChange(of: showingVectorizer) { _, shown in
            if !shown {
                stopTracePlayback = true
                vectorizePreview = nil
                vectorizeProgress = 1
                refreshCanvasPreview()
            }
        }
        .onChange(of: pendingDiagramAt) { _, anchor in
            if anchor == nil { diagramPreview = nil; refreshCanvasPreview() }
        }
        .onChange(of: diagramPreview?.id) { _, _ in refreshCanvasPreview() }
        .onChange(of: pendingCurvePreview?.id) { _, _ in refreshCanvasPreview() }
        .onChange(of: catalogPreview?.id) { _, _ in refreshCanvasPreview() }
        .onChange(of: vectorizePreview?.id) { _, _ in refreshCanvasPreview() }
        .onChange(of: vectorizeProgress) { _, _ in refreshCanvasPreview() }
    }

    // ---------------------------------------------------------------- geometry

    private var selectedNodes: [BoardNode] {
        board.nodes.filter { selection.contains($0.id) }
    }

    private var selectionBounds: CGRect {
        BoardGeometry.bounds(of: selectedNodes)
    }

    /// Where a new image lands: the centre of what you are looking at, so inserting never
    /// puts a photograph off-screen at the current zoom.
    private var insertionPoint: CGPoint { viewport.centre }

    // ---------------------------------------------------------------- toolbar

    private var toolbar: some View {
        HStack(spacing: 6) {
            toolGroup
            Divider().frame(height: 20)
            inkGroup
            Spacer(minLength: 8)
            editGroup
            Divider().frame(height: 20)
            zoomGroup
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(.regularMaterial)
    }

    private var toolGroup: some View {
        Group {
            ForEach(BoardTool.allCases) { candidate in
                if candidate != BoardTool.allCases.first, previousGroup(candidate) != candidate.group {
                    Divider().frame(width: 1, height: 20)
                }
                toolButton(for: candidate)
            }
        }
    }

    private func previousGroup(_ tool: BoardTool) -> BoardTool.Group {
        let ordered = BoardTool.allCases
        guard let index = ordered.firstIndex(of: tool), index > 0 else { return tool.group }
        return ordered[ordered.index(before: index)].group
    }

    private func toolButton(for candidate: BoardTool) -> some View {
        Button {
            tool = candidate
        } label: {
            Image(systemName: candidate.icon)
                .font(.system(size: 12, weight: .medium))
                .frame(width: 26, height: 24)
                .background(tool == candidate ? Palette.sage : Color.clear,
                            in: RoundedRectangle(cornerRadius: 7))
        }
        .buttonStyle(.plain)
        .foregroundStyle(tool == candidate ? Palette.ink : Palette.secondary)
        .help("\(candidate.label) — \(candidate.shortcut)")
    }

    @ViewBuilder
    private var inkGroup: some View {
        if tool.isInk {
            Circle().fill(Color(hexString: colour)).frame(width: 16, height: 16)
            ColorPicker("", selection: Binding(get: { Color(hexString: colour) },
                                              set: { colour = Self.hex($0); BoardInkMemory.remember(colour) }),
                       supportsOpacity: false)
                .labelsHidden().frame(width: 28)
            Slider(value: $width, in: 0.6...14, step: 0.2).frame(width: 70)
                .help("Ink weight — \(String(format: "%.1f", width)) pt")
            // Recent colours, because the third time you need the same ochre is the third
            // time hunting through a colour wheel.
            ForEach(BoardInkMemory.recent.prefix(5), id: \.self) { recent in
                Circle().fill(Color(hexString: recent)).frame(width: 12, height: 12)
                    .overlay(Circle().strokeBorder(Palette.line, lineWidth: 0.5))
                    .onTapGesture { colour = recent }
            }
        }
        if tool == .eraser {
            Picker("", selection: $eraserMode) {
                ForEach(BoardEraserMode.allCases) { mode in
                    Label(mode.label, systemImage: mode.icon).tag(mode)
                }
            }
            .labelsHidden().frame(width: 150)
            .help(eraserMode.help)
        }
        if tool == .image {
            Button { showingImages = true } label: {
                Label("Search images", systemImage: "photo.on.rectangle.angled")
            }.buttonStyle(.plain).font(.system(size: 11)).help("Fetch a licence-cleared photograph and place it")
        }
        if tool == .diagram {
            Menu {
                Button("AI diagram from prompt…", systemImage: "scribble.variable") {
                    pendingDiagramAt = insertionPoint
                    diagramPrompt = ""
                    diagramPreview = nil
                }
                Button("Common diagram library…", systemImage: "books.vertical") {
                    showingDiagramCatalog = true
                }
                Button("Plot a function / curve…", systemImage: "function") {
                    showingCurves = true
                }
                Button("Image → line strokes…", systemImage: "point.topleft.down.to.point.bottomright.curvepath") {
                    let selectedImage = selectedNodes.first(where: { $0.kind == "image" })
                    vectorizeSource = selectedImage?.payload["sha256"].string ?? ""
                    vectorizeAt = selectedImage.map { CGPoint(x: $0.x, y: $0.y) } ?? insertionPoint
                    vectorizeSize = selectedImage.map { CGSize(width: $0.w, height: $0.h) }
                        ?? CGSize(width: 760, height: 480)
                    vectorizePreview = nil
                    vectorizeProgress = 0
                    showingVectorizer = true
                }
            } label: {
                Label("Diagram…", systemImage: "scribble.variable")
                    .font(.system(size: 11, weight: .medium))
            }
            .menuStyle(.borderlessButton)
            .help("AI diagram, common templates, mathematical curves, or vectorize an image")
        }
        if caseShapeTools.contains(tool) {
            Picker("", selection: shapeBinding) {
                Text("Rectangle").tag("rect")
                Text("Ellipse").tag("ellipse")
                Text("Line").tag("line")
                Text("Arrow").tag("arrow")
                Text("Sticky").tag("sticky")
            }
            .labelsHidden().frame(width: 130)
        }
    }

    private var caseShapeTools: Set<BoardTool> { [.rect, .ellipse, .line, .arrow, .sticky] }

    @State private var shapeKind = "rect"
    private var shapeBinding: Binding<String> {
        Binding(get: { tool.shapeName ?? shapeKind },
                set: { new in shapeKind = new })
    }

    @ViewBuilder
    private var editGroup: some View {
        Button { board.undo() } label: { Image(systemName: "arrow.uturn.backward") }
            .buttonStyle(.plain).disabled(!board.canUndo)
            .help("Undo — ⌘Z")
        Button { board.redo() } label: { Image(systemName: "arrow.uturn.forward") }
            .buttonStyle(.plain).disabled(!board.canRedo)
            .help("Redo — ⇧⌘Z")
        Menu {
            ForEach(AlignCommand.allCases) { command in
                Button(command.label) { align(command) }
            }
            Divider()
            ForEach(DistributeCommand.allCases) { command in
                Button(command.label) { distribute(command) }
            }
        } label: {
            Image(systemName: "align.horizontal.left")
        }
        .buttonStyle(.plain)
        .disabled(selectedNodes.count < 2)
        .help("Align and distribute the selection")
        Menu {
            Button("Bring to front") { stack(.front) }
            Button("Bring forward") { stack(.forward) }
            Button("Send backward") { stack(.backward) }
            Button("Send to back") { stack(.back) }
            Divider()
            Button("Duplicate") { duplicateSelection() }.keyboardShortcut("d", modifiers: .command)
            Button("Copy") { copySelection() }.keyboardShortcut("c", modifiers: .command)
            Button("Paste") { paste() }.keyboardShortcut("v", modifiers: .command)
        } label: {
            Image(systemName: "square.stack.3d.up")
        }
        .buttonStyle(.plain)
        .help("Stacking order and clipboard")
        if !selection.isEmpty {
            Button { deleteSelection() } label: { Image(systemName: "trash") }
                .buttonStyle(.plain).help("Delete the selection — ⌫")
        }
    }

    @ViewBuilder
    private var zoomGroup: some View {
        Button { fitToBoard() } label: { Image(systemName: "rectangle.arrowtriangle.2.inward") }
            .buttonStyle(.plain).help("Fit the whole board in view")
        Button { viewport.zoom(by: 1.2, at: .zero, in: CGSize.zero) } label: { Image(systemName: "plus.magnifyingglass") }
            .buttonStyle(.plain)
        Button { viewport.zoom(by: 1 / 1.2, at: .zero, in: CGSize.zero) } label: { Image(systemName: "minus.magnifyingglass") }
            .buttonStyle(.plain)
        Text(String(format: "%.0f%%", viewport.zoom * 100))
            .font(.system(size: 10, design: .monospaced))
            .foregroundStyle(Palette.tertiary)
            .frame(width: 42, alignment: .trailing)
    }

    // ---------------------------------------------------------------- canvas

    private var canvas: some View {
        GeometryReader { proxy in
            let size = proxy.size
            ZStack {
                // A faint grid gives the eye a scale reference at high zoom; it is a
                // drawing aid, not a constraint, and snapping to it is off by default.
                gridLayer(in: size)
                BoardEventBridge(
                    onScroll: { delta, location, _, command in
                        if command { viewport.zoom(by: delta.dy > 0 ? 1 / 1.12 : 1.12, at: location, in: size) }
                        else {
                            viewport.centre.x -= delta.dx / viewport.zoom
                            viewport.centre.y -= delta.dy / viewport.zoom
                        }
                    },
                    onMagnify: { scale, location, _ in viewport.zoom(by: scale, at: location, in: size) },
                    onPress: { location, _, pressure in press(location, in: size, pressure: pressure) },
                    onDrag: { location, _, pressure in drag(to: location, in: size, pressure: pressure) },
                    onRelease: { location, _ in release(at: location, in: size) },
                    onRightClick: { location, _ in
                        // A right-click selects what you are pointing at, which is what
                        // makes the menu that follows act on the thing you expected.
                        let point = viewport.toBoard(location, in: size)
                        if let hit = board.nodes.last(where: { $0.hitTest(point) }) {
                            if !selection.contains(hit.id) { selection.replace(with: hit.id) }
                        } else {
                            selection.clear()
                        }
                    },
                    onKey: { characters, flags in keyPress(characters, flags: flags, in: size) }
                )
                Canvas { context, canvasSize in
                    drawNodes(in: &context, size: canvasSize)
                    drawLive(in: &context, size: canvasSize)
                    drawOverlays(in: &context, size: canvasSize)
                }
                .allowsHitTesting(false)
                if board.busy {
                    VStack {
                        ProgressView().controlSize(.small)
                        Text("syncing…").font(.system(size: 9)).foregroundStyle(Palette.tertiary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
                    .padding(10)
                }
            }
            .background(Color.white)
            .clipped()
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Palette.line))
        }
        .frame(minHeight: 420)
    }

    @ViewBuilder
    private func gridLayer(in size: CGSize) -> some View {
        let step = gridStep * Double(viewport.zoom)
        if snapToGrid, step > 9 {
            Canvas { context, _ in
                var path = Path()
                var x = (viewport.toView(CGPoint(x: 0, y: 0), in: size).x).truncatingRemainder(dividingBy: step)
                while x < size.width {
                    path.move(to: CGPoint(x: x, y: 0)); path.addLine(to: CGPoint(x: x, y: size.height)); x += step
                }
                var y = (viewport.toView(CGPoint(x: 0, y: 0), in: size).y).truncatingRemainder(dividingBy: step)
                while y < size.height {
                    path.move(to: CGPoint(x: 0, y: y)); path.addLine(to: CGPoint(x: size.width, y: y)); y += step
                }
                context.stroke(path, with: .color(Palette.line.opacity(0.35)), lineWidth: 0.5)
            }
            .allowsHitTesting(false)
        }
    }

    // ---------------------------------------------------------------- footer

    private var footer: some View {
        HStack(spacing: 12) {
            Text("\(board.nodes.count) objects · v\(board.version)")
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(Palette.tertiary)
            if !selection.isEmpty {
                Text("\(selection.count) selected")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(Palette.forest)
            }
            Spacer()
            Text(snapToGrid ? "grid snap on · \(Int(gridStep))" : "free placement")
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(Palette.tertiary)
            Button("Ask the tutor") { if selectionBounds.width > 4 { askingAbout = selectionBounds } }
                .buttonStyle(.plain)
                .font(.system(size: 9, weight: .semibold))
                .foregroundStyle(Palette.indigoDeep)
                .disabled(selectedNodes.isEmpty)
            if let notice {
                Text(notice).font(.system(size: 9)).foregroundStyle(Palette.peachDeep).lineLimit(1)
            }
            if let error = board.error, !error.isEmpty {
                Text(error).font(.system(size: 9)).foregroundStyle(Palette.peachDeep).lineLimit(1)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
    }
}

// MARK: - Interaction

extension BoardEditor {
    fileprivate func press(_ location: CGPoint, in size: CGSize, pressure: CGFloat) {
        let point = viewport.toBoard(location, in: size)
        switch tool {
        case .select:
            // A grips wins over the nodes inside it: you grab a grip to resize, and only
            // an empty press starts a marquee or a move.
            if let grip = grip(at: location, in: size) {
                resizeHandle = grip
                resizeBase = Dictionary(uniqueKeysWithValues: selectedNodes.map { ($0.id, BoardGeometry.bounds(of: $0)) })
                resizeGroup = selectionBounds
                board.beginEdit()
                return
            }
            if let hit = board.nodes.last(where: { $0.hitTest(point) }) {
                // Nodes render in ascending z, so the *last* match is the topmost one.
                // A press on a node is the only evidence the product can get that a learner
                // opened it - an embedded simulation reports nothing back, so "they reached
                // for this" is the whole honest claim. Recorded by *kind* rather than by node
                // id: an id is unique per placement, so a hundred taps on a hundred simulation
                // nodes would look like a hundred unrelated targets and aggregate to nothing.
                store.recordInteraction("board.node." + ClickTelemetry.sanitise(hit.kind))
                let shift = NSEvent.modifierFlags.contains(.shift)
                if selection.contains(hit.id) {
                    dragIDs = Set(selection.ids)
                } else {
                    var updated = selection
                    if shift { updated.toggle(hit.id) } else { updated.replace(with: hit.id) }
                    selection = updated
                    dragIDs = Set(updated.ids)
                }
            } else {
                if !NSEvent.modifierFlags.contains(.shift) { selection.clear() }
                marquee = CGRect(origin: point, size: .zero)
                dragIDs = []
            }
            dragOrigin = point
            dragBase = Dictionary(uniqueKeysWithValues: board.nodes.map { ($0.id, BoardGeometry.bounds(of: $0)) })
            dragDidMove = false

        case .pen, .highlighter:
            // No minimum travel and no activation distance: the stroke begins the moment
            // the pointer goes down. That is the "soft touch" fix in one line — the old
            // path needed a deliberate click-drag before a single point was recorded.
            livePoints = [point]
            livePressure = [pressure]
            board.beginEdit()

        case .eraser:
            erase(at: point)

        case .text:
            pendingTextAt = point
            textDraft = ""

        case .sticky:
            board.beginEdit()
            board.add(node: BoardNode(id: "", kind: "text", x: point.x, y: point.y, w: 190, h: 150, z: "",
                                      payload: (try? JSON.make(["text": "", "shape": "sticky", "size": 15.0,
                                                                "fill": "#FCEBA4"])) ?? .null))

        case .rect, .ellipse, .line, .arrow:
            liveBox = CGRect(origin: point, size: .zero)

        case .connector:
            liveConnector = (from: point, to: point)

        case .image:
            showingImages = true

        case .diagram:
            // Prefer explicit menu choices; for the tool's canvas gesture open prompt AI.
            pendingDiagramAt = point
            diagramPrompt = ""
            diagramPreview = nil

        case .lasso:
            liveLasso = [point]

        case .hand:
            break
        }
    }

    fileprivate func drag(to location: CGPoint, in size: CGSize, pressure: CGFloat) {
        let point = viewport.toBoard(location, in: size)
        switch tool {
        case .select:
            if let grip = resizeHandle { resize(to: point, grip: grip); return }
            if dragIDs.isEmpty { marquee = rect(from: marquee?.origin ?? point, to: point); return }
            guard let origin = dragOrigin, !dragBase.isEmpty else { return }
            var delta = CGVector(dx: point.x - origin.x, dy: point.y - origin.y)
            // Snap the *group*, then apply one correction to every member. Deriving the
            // snap per node is how a group drag shears apart into smears.
            let moving = union(dragBase.filter { dragIDs.contains($0.key) }.map(\.value))
            let others = dragBase.filter { !dragIDs.contains($0.key) }.map(\.value)
            let (adjusted, found) = SnapEngine.snap(moving: moving, others: others, delta: delta,
                                                   grid: snapToGrid ? gridStep : nil)
            delta = adjusted
            guides = found
            if abs(delta.dx) > 0.4 || abs(delta.dy) > 0.4 { dragDidMove = true }
            let live = dragBase.filter { dragIDs.contains($0.key) }
            board.moveMany(live.map {
                (id: $0.key, x: $0.value.minX + delta.dx, y: $0.value.minY + delta.dy,
                 w: $0.value.width, h: $0.value.height)
            })

        case .pen, .highlighter:
            guard let last = livePoints.last else { return }
            guard InkSampler.shouldAccept(last, point) else { return }
            livePoints.append(point)
            livePressure.append(pressure)

        case .connector:
            liveConnector = (from: liveConnector?.from ?? point, to: point)

        case .rect, .ellipse, .line, .arrow:
            liveBox = rect(from: liveBox?.origin ?? point, to: point)

        case .lasso:
            guard let last = liveLasso.last, hypot(last.x - point.x, last.y - point.y) > 2 else { return }
            liveLasso.append(point)

        default:
            break
        }
    }

    fileprivate func release(at location: CGPoint, in size: CGSize) {
        defer {
            livePoints = []; livePressure = []; liveBox = nil
            liveConnector = nil; liveLasso = []
            dragIDs = []; dragOrigin = nil; dragBase = [:]
            resizeHandle = nil; resizeBase = [:]; resizeGroup = nil
            marquee = nil; guides = []
        }
        switch tool {
        case .pen, .highlighter:
            guard livePoints.count > 2 else { return }
            commitStroke(reported: livePressure)

        case .rect, .ellipse, .line, .arrow:
            guard let box = liveBox, box.width > 5, box.height > 5 else { return }
            let shape = tool.shapeName ?? "rect"
            board.add(node: BoardNode(id: "", kind: "shape", x: box.minX, y: box.minY,
                                      w: box.width, h: box.height, z: "",
                                      payload: (try? JSON.make(["shape": shape, "colour": colour,
                                                                "width": width])) ?? .null))

        case .connector:
            guard let wire = liveConnector,
                  hypot(wire.to.x - wire.from.x, wire.to.y - wire.from.y) > 8 else { return }
            let bounds = CGRect(points: [wire.from, wire.to]).insetBy(dx: -6, dy: -6)
            board.add(node: BoardNode(id: "", kind: "connector",
                                      x: bounds.minX, y: bounds.minY, w: bounds.width, h: bounds.height, z: "",
                                      payload: (try? JSON.make([
                                          "x": Double(wire.from.x), "y": Double(wire.from.y),
                                          "x2": Double(wire.to.x), "y2": Double(wire.to.y),
                                          "colour": colour, "arrow": true, "width": width])) ?? .null))

        case .lasso:
            guard liveLasso.count > 5, let box = bounds(of: liveLasso),
                  box.width > 14, box.height > 14 else { return }
            selection.replace(with: Set(board.nodes.filter { $0.frame.intersects(box) }.map(\.id)))

        case .select:
            if let marquee {
                let inside = Set(board.nodes.filter {
                    BoardGeometry.bounds(of: $0).intersects(marquee)
                }.map(\.id))
                if NSEvent.modifierFlags.contains(.shift) {
                    selection.replace(with: selection.ids.union(inside))
                } else {
                    selection.replace(with: inside)
                }
            }

        default:
            break
        }
    }

    // ---------------------------------------------------------------- small helpers

    private func rect(from a: CGPoint, to b: CGPoint) -> CGRect {
        CGRect(x: min(a.x, b.x), y: min(a.y, b.y), width: abs(b.x - a.x), height: abs(b.y - a.y))
    }

    private func bounds(of points: [CGPoint]) -> CGRect? {
        guard let first = points.first else { return nil }
        var rect = CGRect(x: first.x, y: first.y, width: 0, height: 0)
        for point in points.dropFirst() { rect = rect.union(CGRect(x: point.x, y: point.y, width: 0, height: 0)) }
        return rect
    }

    /// The grip under the pointer, or nil. Measured in board units with a screen-constant
    /// radius, so a grip stays clickable at every zoom instead of shrinking away.
    private func grip(at location: CGPoint, in size: CGSize) -> ResizeHandle? {
        guard selectedNodes.count >= 1, !selectionBounds.isNull else { return nil }
        let box = selectionBounds
        let here = viewport.toBoard(location, in: size)
        let radius: CGFloat = 8 / max(0.01, viewport.zoom)
        for candidate in ResizeHandle.allCases
        where hypot(candidate.point(in: box).x - here.x, candidate.point(in: box).y - here.y) <= radius {
            return candidate
        }
        return nil
    }

    private func resize(to point: CGPoint, grip: ResizeHandle) {
        guard var group = resizeGroup, let before = resizeGroup, dragBase.isEmpty == false else { return }
        group = grip.resized(group, to: point)
        guard before.width > 0.01, before.height > 0.01 else { return }
        let sx = group.width / before.width
        let sy = group.height / before.height
        guard sx > 0, sy > 0 else { return }
        resizeGroup = group
        board.moveMany(resizeBase.map { entry in
            let base = entry.value
            return (id: entry.key,
                    x: group.minX + (base.minX - before.minX) * sx,
                    y: group.minY + (base.minY - before.minY) * sy,
                    w: base.width * sx, h: base.height * sy)
        })
    }

    /// Layer down a stroke from the live pointer stream: decimate to the server's cap,
    /// derive pressure where the hardware reported none, and store one width.
    ///
    /// `useHardware` is false on purpose. The values that arrive here have already been
    /// through the bridge, which reports nil for a trackpad's saturated 1.0 — so at this
    /// point the array is either a real tablet curve or a row of 0.5s, and sending 0.5s
    /// as "hardware" would produce the identical flat stroke the bridge exists to avoid.
    /// The velocity curve is the honest signal in both cases.
    private func commitStroke(reported: [CGFloat]) {
        let points = InkSampler.decimate(livePoints)
        let pressure = InkSampler.pressures(points: points, reported: reported, useHardware: false)
        let trimmed = InkSampler.decimate(pressure, to: points.count)
        let bounds = CGRect(points: points).insetBy(dx: -20, dy: -20)
        let stored = InkSampler.storedWidth(trimmed, base: tool == .highlighter ? 13 : width)
        board.add(node: BoardNode(
            id: "", kind: "path", x: bounds.minX, y: bounds.minY, w: bounds.width, h: bounds.height, z: "",
            payload: (try? JSON.make([
                "points": points.map { [Double($0.x), Double($0.y)] },
                "pressure": trimmed.map(Double.init),
                "colour": colour,
                "width": stored,
                "highlight": tool == .highlighter,
            ])) ?? .null))
        BoardInkMemory.remember(colour)
    }

    private func erase(at point: CGPoint) {
        // Strokes first, then solid nodes: a stroke drawn on top of a shape should be
        // erasable without erasing the shape underneath.
        for node in board.nodes.reversed() where node.kind == "path" {
            guard BoardGeometry.points(of: node).contains(where: { hypot($0.x - point.x, $0.y - point.y) < 16 })
            else { continue }
            board.beginEdit()
            if eraserMode == .segment { board.eraseStroke(id: node.id, near: point) }
            else { board.delete(id: node.id) }
            return
        }
        for node in board.nodes.reversed() where node.kind != "path" {
            guard node.hitTest(point) else { continue }
            board.beginEdit()
            board.delete(id: node.id)
            return
        }
    }
}

// MARK: - Commands, keyboard, context menu

extension BoardEditor {
    fileprivate func fitToBoard() {
        viewport.fit(BoardGeometry.bounds(of: board.nodes), in: CGSize(width: 1200, height: 800))
    }

    fileprivate func align(_ command: AlignCommand) {
        guard selectedNodes.count > 1 else { return }
        board.beginEdit()
        let moved = BoardGeometry.aligned(selectedNodes, by: command)
        board.moveMany(moved.map { (id: $0.id, x: $0.x, y: $0.y, w: $0.w, h: $0.h) })
    }

    fileprivate func distribute(_ command: DistributeCommand) {
        guard selectedNodes.count > 2 else { return }
        board.beginEdit()
        let moved = BoardGeometry.distributed(selectedNodes, by: command)
        board.moveMany(moved.map { (id: $0.id, x: $0.x, y: $0.y, w: $0.w, h: $0.h) })
    }

    fileprivate enum Layer { case front, forward, backward, back }

    fileprivate func stack(_ direction: Layer) {
        guard let id = selection.single else { return }
        let sorted = board.nodes.sorted { $0.z < $1.z }
        guard let index = sorted.firstIndex(where: { $0.id == id }) else { return }
        switch direction {
        case .front:
            board.reorder(id: id, afterID: sorted.last?.id, beforeID: nil)
        case .back:
            board.reorder(id: id, afterID: nil, beforeID: sorted.first?.id)
        case .forward:
            board.reorder(id: id, afterID: index + 1 < sorted.count ? sorted[index + 1].id : nil, beforeID: nil)
        case .backward:
            board.reorder(id: id, afterID: nil, beforeID: index > 0 ? sorted[index - 1].id : nil)
        }
    }

    fileprivate func deleteSelection() {
        guard !selection.isEmpty else { return }
        board.beginEdit()
        for id in selection.ids { board.delete(id: id) }
        selection.clear()
    }

    fileprivate func duplicateSelection() {
        guard !selectedNodes.isEmpty else { return }
        board.beginEdit()
        for node in BoardClipboard.paste(at: CGPoint(x: selectionBounds.maxX + 24, y: selectionBounds.minY)) {
            board.add(node: node)
        }
    }

    fileprivate func copySelection() {
        guard !selectedNodes.isEmpty else { return }
        BoardClipboard.copy(selectedNodes)
        notice = "Copied \(BoardClipboard.count) object(s)"
    }

    fileprivate func paste() {
        if BoardClipboard.matchesSystemPasteboard, !BoardClipboard.isEmpty {
            board.addMany(nodes: BoardClipboard.paste())
            notice = "Pasted \(BoardClipboard.count) board object(s)"
            return
        }
        guard let image = Self.imageOnSystemPasteboard() else {
            guard !BoardClipboard.isEmpty else {
                notice = "Copy an image or board selection, then paste"
                return
            }
            board.addMany(nodes: BoardClipboard.paste())
            notice = "Pasted \(BoardClipboard.count) board object(s)"
            return
        }
        Task { await pasteSystemImage(image) }
    }

    private static func imageOnSystemPasteboard() -> NSImage? {
        let pasteboard = NSPasteboard.general
        if let image = NSImage(pasteboard: pasteboard) { return image }
        if let data = pasteboard.data(forType: .png) { return NSImage(data: data) }
        for type in [NSPasteboard.PasteboardType("public.jpeg"),
                     NSPasteboard.PasteboardType("public.tiff"),
                     NSPasteboard.PasteboardType("public.webp"),
                     NSPasteboard.PasteboardType("com.compuserve.gif")] {
            if let data = pasteboard.data(forType: type), let image = NSImage(data: data) { return image }
        }
        return nil
    }

    @MainActor
    private func pasteSystemImage(_ image: NSImage) async {
        guard let tiff = image.tiffRepresentation,
              let rep = NSBitmapImageRep(data: tiff),
              let data = rep.representation(using: .png, properties: [:]),
              !data.isEmpty else {
            board.error = "The clipboard image could not be encoded."
            return
        }
        guard let api = AppStore.current?.api else {
            board.error = "Image paste is unavailable until the account is connected."
            return
        }
        do {
            let result = try await api.json("/images/paste", method: "POST", body: [
                "data_base64": data.base64EncodedString(),
                "filename": "Pasted clipboard image",
            ])
            let asset = result["asset"]
            var size = image.size
            if size.width <= 1 || size.height <= 1 { size = CGSize(width: 320, height: 200) }
            let scale = min(420 / size.width, 420 / size.height, 1)
            size = CGSize(width: size.width * scale, height: size.height * scale)
            let at = insertionPoint
            let sha = asset["sha256"].string
            board.add(node: BoardNode(
                id: "", kind: "image", x: at.x - size.width / 2, y: at.y - size.height / 2,
                w: size.width, h: size.height, z: "",
                payload: (try? JSON.make([
                    "sha256": sha,
                    "src": asset["src"].string,
                    "title": asset["title"].string,
                    "credit": asset["credit"].string,
                    "licence": asset["licence"].string,
                ])) ?? .null))
            notice = "Pasted image · source/licence unverified"
        } catch {
            board.error = "Image paste failed: \(error.localizedDescription)"
        }
    }

    /// Single-key shortcuts and the command combinations every editor on the platform
    /// already owns. Muscle memory transfers; not having it is what makes a custom
    /// canvas feel like a toy.
    fileprivate func keyPress(_ characters: String, flags: NSEvent.ModifierFlags, in size: CGSize) {
        let command = flags.contains(.command)
        let shift = flags.contains(.shift)
        let key = characters.lowercased()

        if command, key == "z" {
            if shift { board.redo() } else { board.undo() }
            return
        }
        if command {
            if key == "a", !selectedNodes.isEmpty {
                selection.replace(with: Set(board.nodes.map(\.id)))
            } else if key == "c" { copySelection() }
            else if key == "v" { paste() }
            else if key == "d" { duplicateSelection() }
            else if key == "f" { fitToBoard() }
            return
        }

        if key == "\u{7F}" || key == "\u{8}" || key == String(Unicode.Scalar(127)!) {
            deleteSelection()
            return
        }
        // Nudge with the arrow keys: one board unit per press, ten with shift. AppKit
        // reports the arrow cluster in the Unicode private-use area (0xF700–0xF703),
        // which is why these are written as scalars rather than as names.
        let arrows: [(UInt32, Double, Double)] = [
            (0xF700, -1, 0), (0xF701, 1, 0), (0xF702, 0, 1), (0xF703, 0, -1),
        ]
        for (scalar, dx, dy) in arrows {
            guard let target = Unicode.Scalar(scalar),
                  characters == String(target), !dragBase.isEmpty else { continue }
            let step = shift ? 10.0 : 1.0
            board.moveMany(dragBase.map { (id: $0.key, x: $0.value.minX + dx * step, y: $0.value.minY + dy * step,
                                           w: $0.value.width, h: $0.value.height) })
            return
        }
        // "[" / "]" reorder without reaching for a menu.
        if characters == "[" { stack(shift ? .back : .backward) }
        if characters == "]" { stack(shift ? .front : .forward) }

        if let match = BoardTool.allCases.first(where: { $0.shortcut.lowercased() == key }) {
            tool = match
        }
    }

    /// The hex string for a colour, nearest sRGB. Used for every payload that stores a
    /// colour, so a stored stroke round-trips to exactly the colour that was shown.
    static func hex(_ colour: Color) -> String {
        let ns = NSColor(colour).usingColorSpace(.sRGB) ?? NSColor.black
        return String(format: "#%02x%02x%02x",
                      Int(round(ns.redComponent * 255)),
                      Int(round(ns.greenComponent * 255)),
                      Int(round(ns.blueComponent * 255)))
    }
}

// MARK: - Rendering

extension BoardEditor {
    /// The smallest line width a stroke is drawn at, in board units.
    ///
    /// Strokes are stored in absolute board units, so at 12% zoom a 2 pt stroke is
    /// 0.24 pt on screen and simply vanishes. Floors like this are why a board full of
    /// fine ink stays legible when you zoom out to find things.
    private var hairline: CGFloat { 0.9 / max(0.01, viewport.zoom) }

    private func tint(_ hex: String, fallback: Color = .primary) -> Color {
        hex.isEmpty ? fallback : Color(hexString: hex)
    }

    private func drawNodes(in ctx: inout GraphicsContext, size: CGSize) {
        // One transform for the whole document rather than one per node. `GraphicsContext`
        // has no save/restore stack, so a per-node translate-and-scale could not be undone
        // and every node after the first would be scaled twice. Board space for the entire
        // canvas is the simplest correct answer, and it makes every draw below work in the
        // units the document actually stores.
        enterBoardSpace(&ctx, size: size)
        for node in board.nodes { drawNode(node, in: &ctx) }
        if !canvasPreviewNodes.isEmpty {
            ctx.opacity = 0.58
            for node in canvasPreviewNodes { drawNode(node, in: &ctx) }
            ctx.opacity = 1
        }
    }

    /// Draw one node in absolute board coordinates.
    private func drawNode(_ node: BoardNode, in ctx: inout GraphicsContext) {
        switch node.kind {
        case "path": drawStroke(node, in: &ctx)
        case "shape": drawShape(node, in: &ctx)
        case "connector": drawConnector(node, in: &ctx)
        case "text": drawText(node, in: &ctx)
        case "answer": drawAnswer(node, in: &ctx)
        case "image": drawImage(node, in: &ctx)
        case "video", "simulation": drawChip(node, in: &ctx)
        default: break
        }
    }

    // MARK: kinds

    private func drawStroke(_ node: BoardNode, in ctx: inout GraphicsContext) {
        let points = BoardGeometry.points(of: node)
        guard points.count > 1 else { return }
        let pressures = BoardGeometry.pressure(of: node)
        let base = CGFloat(min(48, max(0.3, node.payload["width"].double.isFinite
                                        ? node.payload["width"].double : 2.6)))
        let colour = tint(node.payload["colour"].string)
        // A highlighter is a wash, not a line: the same geometry at low alpha.
        if node.payload["highlight"].bool {
            var path = Path()
            path.move(to: points[0])
            for point in points.dropFirst() { path.addLine(to: point) }
            ctx.stroke(path, with: .color(colour.opacity(0.32)),
                       style: StrokeStyle(lineWidth: max(base, hairline), lineCap: .round, lineJoin: .round))
            return
        }
        // Per-segment widths reproduce the taper the stored pressure curve describes. A
        // curve that does not actually vary takes the single-stroke fast path, because
        // drawing 780 separate segments to render a flat line is pure waste.
        let varying = pressures.contains { abs($0 - pressures[0]) > 0.06 }
        if varying, points.count <= 900 {
            for index in 0..<(points.count - 1) {
                let weight = pressures[min(index, pressures.count - 1)]
                var segment = Path()
                segment.move(to: points[index])
                segment.addLine(to: points[index + 1])
                ctx.stroke(segment, with: .color(colour),
                           style: StrokeStyle(lineWidth: max(hairline, base * (0.55 + 0.9 * weight)),
                                              lineCap: .round))
            }
            return
        }
        var path = Path()
        path.move(to: points[0])
        for point in points.dropFirst() { path.addLine(to: point) }
        ctx.stroke(path, with: .color(colour),
                   style: StrokeStyle(lineWidth: max(base, hairline), lineCap: .round, lineJoin: .round))
    }

    private func drawShape(_ node: BoardNode, in ctx: inout GraphicsContext) {
        let box = node.frame
        let colour = tint(node.payload["colour"].string)
        let fill = node.payload["fill"].string.isEmpty ? nil : tint(node.payload["fill"].string)
        let shape = node.payload["shape"].string
        let outline = Path { path in
            switch shape {
            case "ellipse": path.addEllipse(in: box)
            case "sticky": path.addRoundedRect(in: box, cornerSize: CGSize(width: 7, height: 7))
            case "line", "arrow":
                path.move(to: CGPoint(x: box.minX, y: box.minY))
                path.addLine(to: CGPoint(x: box.maxX, y: box.maxY))
            case "triangle":
                path.move(to: CGPoint(x: box.midX, y: box.minY))
                path.addLine(to: CGPoint(x: box.maxX, y: box.maxY))
                path.addLine(to: CGPoint(x: box.minX, y: box.maxY))
                path.closeSubpath()
            case "diamond":
                path.move(to: CGPoint(x: box.midX, y: box.minY))
                path.addLine(to: CGPoint(x: box.maxX, y: box.midY))
                path.addLine(to: CGPoint(x: box.midX, y: box.maxY))
                path.addLine(to: CGPoint(x: box.minX, y: box.midY))
                path.closeSubpath()
            default: path.addRect(box)
            }
        }
        // A sticky is a filled note with a border that only hints at the edge; drawing it
        // as a stroked box would make a note read as something someone drew.
        if shape == "sticky" || fill != nil {
            ctx.fill(outline, with: .color(fill ?? Color(hexString: "#FCEBA4")))
            if shape == "sticky" {
                ctx.stroke(outline, with: .color(.black.opacity(0.14)), lineWidth: max(hairline, 1))
            } else {
                ctx.stroke(outline, with: .color(colour), lineWidth: max(hairline, 2))
            }
            return
        }
        let width = CGFloat(min(48, max(0.3, node.payload["width"].double.isFinite
                                        ? node.payload["width"].double : 2)))
        ctx.stroke(outline, with: .color(colour),
                   style: StrokeStyle(lineWidth: max(width, hairline), lineCap: .round))
        if shape == "arrow" {
            drawArrowHead(from: CGPoint(x: box.minX, y: box.minY),
                          to: CGPoint(x: box.maxX, y: box.maxY), colour: colour, in: &ctx)
        }
    }

    private func drawArrowHead(from: CGPoint, to: CGPoint, colour: Color, in ctx: inout GraphicsContext) {
        let angle = atan2(to.y - from.y, to.x - from.x)
        let length: CGFloat = 12
        var head = Path()
        head.move(to: to)
        head.addLine(to: CGPoint(x: to.x - length * cos(angle - 0.42), y: to.y - length * sin(angle - 0.42)))
        head.addLine(to: CGPoint(x: to.x - length * cos(angle + 0.42), y: to.y - length * sin(angle + 0.42)))
        head.closeSubpath()
        ctx.fill(head, with: .color(colour))
    }

    private func drawConnector(_ node: BoardNode, in ctx: inout GraphicsContext) {
        // A connector stores its own endpoints in absolute board coordinates, so it is the
        // one kind that never needs a bounds-relative offset.
        let a = CGPoint(x: node.payload["x"].double, y: node.payload["y"].double)
        let b = CGPoint(x: node.payload["x2"].double, y: node.payload["y2"].double)
        let colour = tint(node.payload["colour"].string, fallback: .gray)
        var wire = Path()
        wire.move(to: a)
        wire.addLine(to: b)
        let width = CGFloat(min(48, max(0.3, node.payload["width"].double.isFinite
                                        ? node.payload["width"].double : 1.6)))
        var style = StrokeStyle(lineWidth: max(width, hairline), lineCap: .round)
        if node.payload["dashed"].bool { style.dash = [7, 5] }
        ctx.stroke(wire, with: .color(colour), style: style)
        // An arrowhead is opt-in: a plain connector is a relationship, and putting a head
        // on it would assert a direction the author did not draw.
        if node.payload["arrow"].bool { drawArrowHead(from: a, to: b, colour: colour, in: &ctx) }
        let label = node.payload["label"].string
        if !label.isEmpty {
            drawWrapped(label, in: &ctx, at: CGPoint(x: a.x + 6, y: a.y - 16), size: 12, tint: colour)
        }
    }

    private func drawText(_ node: BoardNode, in ctx: inout GraphicsContext) {
        let body = node.payload["text"].string
        let size = CGFloat(min(96, max(9, node.payload["size"].double.isFinite
                                       ? node.payload["size"].double : 16)))
        let box = node.frame
        if node.payload["sticky"].bool || node.payload["shape"].string == "sticky" {
            var note = Path()
            note.addRoundedRect(in: box, cornerSize: CGSize(width: 7, height: 7))
            let fill = node.payload["fill"].string.isEmpty
                ? Color(hexString: "#FCEBA4")
                : tint(node.payload["fill"].string)
            ctx.fill(note, with: .color(fill))
            ctx.stroke(note, with: .color(.black.opacity(0.14)), lineWidth: max(hairline, 1))
            drawWrapped(body, in: &ctx, at: CGPoint(x: 11, y: 11), size: size, width: box.width - 22)
            return
        }
        drawWrapped(body, in: &ctx, at: CGPoint(x: node.x, y: node.y), size: size,
                    width: node.w > 24 ? CGFloat(node.w) : 0,
                    weight: node.payload["weight"].string,
                    tint: tint(node.payload["colour"].string, fallback: .primary))
    }

    private func drawAnswer(_ node: BoardNode, in ctx: inout GraphicsContext) {
        let box = node.frame
        var card = Path()
        card.addRoundedRect(in: box, cornerSize: CGSize(width: 9, height: 9))
        ctx.fill(card, with: .color(Color.accentColor.opacity(0.12)))
        ctx.stroke(card, with: .color(Color.accentColor), lineWidth: max(hairline, 1.4))
        var y: CGFloat = 9
        let question = node.payload["question"].string
        if !question.isEmpty {
            drawWrapped("Q: " + question, in: &ctx, at: CGPoint(x: 11, y: y), size: 11.5,
                        width: box.width - 22, tint: .accentColor)
            y += 15
        }
        drawWrapped(node.payload["text"].string, in: &ctx, at: CGPoint(x: 11, y: y), size: 14,
                    width: box.width - 22)
    }

    private func drawImage(_ node: BoardNode, in ctx: inout GraphicsContext) {
        let box = node.frame
        let sha = node.payload["sha256"].string
        if let data = ImageCache.shared.data(sha: sha), let ns = NSImage(data: data) {
            ctx.draw(Image(nsImage: ns).resizable(), in: box)
        } else {
            var placeholder = Path()
            placeholder.addRect(box)
            ctx.fill(placeholder, with: .color(.gray.opacity(0.18)))
        }
        // A credit line is not optional decoration: it is what keeps an uncredited CC
        // image from being reused.
        let credit = node.payload["credit"].string
        if !credit.isEmpty {
            drawWrapped(credit, in: &ctx, at: CGPoint(x: 0, y: box.maxY + 3), size: 9, tint: .secondary)
        }
    }

    private func drawChip(_ node: BoardNode, in ctx: inout GraphicsContext) {
        let box = node.frame
        var card = Path()
        card.addRoundedRect(in: box, cornerSize: CGSize(width: 9, height: 9))
        ctx.fill(card, with: .color(.orange.opacity(0.13)))
        ctx.stroke(card, with: .color(.orange), lineWidth: max(hairline, 1.2))
        let icon = node.kind == "video" ? "▶ " : "⚙ "
        drawWrapped(icon + node.payload.text("title", fallback: ""), in: &ctx,
                    at: CGPoint(x: 11, y: 11), size: 13, width: box.width - 22, tint: .orange)
        drawWrapped("embed — licensed to its source, not redistributable", in: &ctx,
                    at: CGPoint(x: 11, y: 33), size: 9.5, width: box.width - 22, tint: .orange)
    }

    // MARK: text

    /// Text laid out with wrapping measured in board units.
    ///
    /// `GraphicsContext.draw(_:at:anchor:)` does not wrap, so a text node would run off
    /// the board the moment someone typed a sentence. Measuring against the node's own
    /// width keeps a sticky note a note.
    private func drawWrapped(_ text: String, in ctx: inout GraphicsContext, at: CGPoint, size: CGFloat,
                              width: CGFloat = 0, weight: String = "", tint: Color = .primary) {
        guard !text.isEmpty else { return }
        let font = NSFont.systemFont(ofSize: size, weight: BoardEditor.weight(weight))
        let lines: [String] = width > 20 ? wrap(text, width: width, font: font)
                                         : text.components(separatedBy: "\n")
        var y = at.y
        for line in lines {
            ctx.draw(Text(line).font(Font(font)).foregroundColor(tint),
                     at: CGPoint(x: at.x, y: y), anchor: .topLeading)
            y += size * 1.34
        }
    }

    private func wrap(_ text: String, width: CGFloat, font: NSFont) -> [String] {
        var out: [String] = []
        for raw in text.components(separatedBy: "\n") {
            var current = ""
            for word in raw.split(separator: " ", omittingEmptySubsequences: false).map(String.init) {
                let candidate = current.isEmpty ? word : current + " " + word
                if (candidate as NSString).size(withAttributes: [.font: font]).width > width, !current.isEmpty {
                    out.append(current)
                    current = word
                } else {
                    current = candidate
                }
            }
            out.append(current)
        }
        return out
    }

    private static func weight(_ name: String) -> NSFont.Weight {
        switch name {
        case "medium": return .medium
        case "semibold": return .semibold
        case "bold": return .bold
        default: return .regular
        }
    }
}

// MARK: - Live gesture and overlays

extension BoardEditor {
    /// What the pointer is doing right now, drawn on top of the committed document.
    ///
    /// Kept separate from ``drawNodes`` because live geometry is board-space already and
    /// should never be routed through the node transform — a stroke being drawn has no
    /// stored bounds yet, which is precisely what the live path exists for.
    private func drawLive(in ctx: inout GraphicsContext, size: CGSize) {
        // The same board-space transform the document layer uses, so live geometry and
        // committed geometry are drawn by the same rules and cannot drift apart.
        enterBoardSpace(&ctx, size: size)

        if livePoints.count > 1 {
            let pressures = InkSampler.pressures(points: livePoints, reported: livePressure,
                                                 useHardware: false)
            let base: CGFloat = tool == .highlighter ? 13 : width
            let ink = Color(hexString: colour)
            if tool == .highlighter {
                var path = Path()
                path.move(to: livePoints[0])
                for point in livePoints.dropFirst() { path.addLine(to: point) }
                ctx.stroke(path, with: .color(ink.opacity(0.32)),
                           style: StrokeStyle(lineWidth: base, lineCap: .round))
            } else {
                // Per-segment, because a live stroke is where the taper is actually felt —
                // a flat preview makes the committed stroke look like a different object.
                for index in 0..<(livePoints.count - 1) {
                    let weight = pressures[min(index, pressures.count - 1)]
                    var segment = Path()
                    segment.move(to: livePoints[index])
                    segment.addLine(to: livePoints[index + 1])
                    ctx.stroke(segment, with: .color(ink),
                               style: StrokeStyle(lineWidth: max(hairline, base * (0.55 + 0.9 * weight)),
                                                  lineCap: .round))
                }
            }
        }

        if let box = liveBox, box.width > 0.5 {
            let shape = tool.shapeName ?? "rect"
            let drawn: Path
            switch shape {
            case "ellipse": drawn = Path(ellipseIn: box)
            case "line", "arrow":
                drawn = Path { p in
                    p.move(to: CGPoint(x: box.minX, y: box.minY))
                    p.addLine(to: CGPoint(x: box.maxX, y: box.maxY))
                }
            default: drawn = Path(roundedRect: box, cornerSize: CGSize(width: 3, height: 3))
            }
            ctx.stroke(drawn, with: .color(Color(hexString: colour).opacity(0.85)),
                       style: StrokeStyle(lineWidth: max(hairline, 1.5)))
            if shape == "arrow" {
                drawArrowHead(from: CGPoint(x: box.minX, y: box.minY),
                              to: CGPoint(x: box.maxX, y: box.maxY),
                              colour: Color(hexString: colour), in: &ctx)
            }
        }

        if let wire = liveConnector {
            var path = Path()
            path.move(to: wire.from)
            path.addLine(to: wire.to)
            ctx.stroke(path, with: .color(Color(hexString: colour)),
                       style: StrokeStyle(lineWidth: max(hairline, width), lineCap: .round))
            drawArrowHead(from: wire.from, to: wire.to, colour: Color(hexString: colour), in: &ctx)
        }

        if liveLasso.count > 1 {
            var path = Path()
            path.move(to: liveLasso[0])
            for point in liveLasso.dropFirst() { path.addLine(to: point) }
            path.closeSubpath()
            ctx.stroke(path, with: .color(.accentColor),
                       style: StrokeStyle(lineWidth: max(hairline, 1.5), dash: [5, 4]))
            ctx.fill(path, with: .color(.accentColor.opacity(0.08)))
        }

        if let marquee {
            var rect = Path()
            rect.addRect(marquee)
            ctx.stroke(rect, with: .color(.accentColor.opacity(0.9)),
                       style: StrokeStyle(lineWidth: max(hairline, 1), dash: [4, 3]))
            ctx.fill(rect, with: .color(.accentColor.opacity(0.07)))
        }
    }

    /// Put the context into board space: centre-anchored, then scaled, then recentred on
    /// the camera's `centre`. Every subsequent draw is in document units.
    private func enterBoardSpace(_ ctx: inout GraphicsContext, size: CGSize) {
        ctx.translateBy(x: size.width / 2, y: size.height / 2)
        ctx.scaleBy(x: viewport.zoom, y: viewport.zoom)
        ctx.translateBy(x: -viewport.centre.x, y: -viewport.centre.y)
    }

    /// The smallest enclosing box of several boxes. `CGRect.union` takes exactly two, and
    /// a selection is a variable number, so this is the loop that keeps the call sites
    /// honest instead of a chain of nested unions.
    private func union(_ rects: [CGRect]) -> CGRect {
        var result = CGRect.null
        for rect in rects { result = result.isNull ? rect : result.union(rect) }
        return result
    }

    private func drawOverlays(in ctx: inout GraphicsContext, size: CGSize) {
        func view(_ point: CGPoint) -> CGPoint { viewport.toView(point, in: size) }

        // Snap guides, drawn only as far as the two things they relate actually span: a
        // full-bleed line implies an alignment that is not there.
        for guide in guides {
            var line = Path()
            if guide.axis == .vertical {
                let x = view(CGPoint(x: guide.position, y: 0)).x
                line.move(to: CGPoint(x: x, y: view(CGPoint(x: 0, y: guide.start)).y))
                line.addLine(to: CGPoint(x: x, y: view(CGPoint(x: 0, y: guide.end)).y))
            } else {
                let y = view(CGPoint(x: 0, y: guide.position)).y
                line.move(to: CGPoint(x: view(CGPoint(x: guide.start, y: 0)).x, y: y))
                line.addLine(to: CGPoint(x: view(CGPoint(x: guide.end, y: 0)).x, y: y))
            }
            ctx.stroke(line, with: .color(.pink), style: StrokeStyle(lineWidth: 1))
        }

        guard !selection.isEmpty, !selectionBounds.isNull else { return }
        let box = selectionBounds
        let corners = [CGPoint(x: box.minX, y: box.minY), CGPoint(x: box.maxX, y: box.minY),
                       CGPoint(x: box.maxX, y: box.maxY), CGPoint(x: box.minX, y: box.maxY)]
        var outline = Path()
        outline.move(to: view(corners[0]))
        for corner in corners.dropFirst() { outline.addLine(to: view(corner)) }
        outline.closeSubpath()
        ctx.stroke(outline, with: .color(.accentColor),
                   style: StrokeStyle(lineWidth: max(1, 1.2 * viewport.zoom)))
        // The eight grips, at a constant screen size so they stay grabbable when the
        // selection is small or the zoom is deep.
        let grip: CGFloat = 4.5
        for candidate in ResizeHandle.allCases {
            let centre = view(candidate.point(in: box))
            var rect = Path()
            rect.addRect(CGRect(x: centre.x - grip, y: centre.y - grip, width: grip * 2, height: grip * 2))
            ctx.fill(rect, with: .color(.white))
            ctx.stroke(rect, with: .color(.accentColor), lineWidth: 1.2)
        }
    }
}

// MARK: - Sheets

/// The write-on-board sheet. The typed text goes back to the editor so placement is
/// decided where the click happened rather than at a hard-coded centre.
private struct TextSheet: View {
    let title: String
    @Binding var draft: String
    let onPlace: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(title).font(.system(size: 14, weight: .semibold))
            TextEditor(text: $draft)
                .font(.system(size: 13))
                .scrollContentBackground(.hidden)
                .padding(7)
                .frame(height: 90)
                .background(Palette.background, in: RoundedRectangle(cornerRadius: 9))
                .overlay(RoundedRectangle(cornerRadius: 9).stroke(Palette.line))
            HStack {
                Spacer()
                Button("Cancel") { draft = "" }.keyboardShortcut(.cancelAction)
                Button("Place") { onPlace() }
                    .keyboardShortcut(.defaultAction)
                    .buttonStyle(LuminfestButtonStyle())
                    .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(20)
        .frame(width: 400)
    }
}

// MARK: - AI line diagrams

extension BoardEditor {
    /// Counts for the preview summary, kept out of the string literal: a Swift
    /// interpolation cannot contain an escaped quote, and the two filters in one
    /// Label are unreadable besides.
    fileprivate var diagramStrokeCount: Int {
        diagramPreview?.nodes.filter { $0.kind == "path" }.count ?? 0
    }

    fileprivate var diagramLabelCount: Int {
        diagramPreview?.nodes.filter { $0.kind == "text" }.count ?? 0
    }

    fileprivate var diagramSheet: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Draw a diagram with DeepSeek", systemImage: "scribble.variable")
                .font(.system(size: 14, weight: .semibold))
            Text("The model reads the current board snapshot and returns editable line strokes and labels. It never creates geometric shape objects; nothing is added until you review and accept the preview.")
                .font(.system(size: 10)).foregroundStyle(Palette.secondary)
            TextEditor(text: $diagramPrompt)
                .font(.system(size: 12)).scrollContentBackground(.hidden)
                .padding(7).frame(height: 80)
                .background(Palette.background, in: RoundedRectangle(cornerRadius: 9))
                .overlay(RoundedRectangle(cornerRadius: 9).stroke(Palette.line))
                .disabled(diagramBusy)
            Toggle("Use a snapshot of this board as VLM context", isOn: $diagramUsesSnapshot)
                .font(.system(size: 10))
                .disabled(diagramBusy)
            if let diagramPreview {
                Label("\(diagramStrokeCount) line strokes · \(diagramLabelCount) labels",
                      systemImage: "checkmark.circle.fill")
                    .font(.system(size: 11, weight: .medium)).foregroundStyle(Palette.forest)
                Text(diagramPreview.title).font(.system(size: 11, weight: .semibold))
                Text(diagramPreview.provider).font(.system(size: 9)).foregroundStyle(Palette.tertiary)
                if !diagramPreview.note.isEmpty {
                    Text(diagramPreview.note).font(.system(size: 9)).foregroundStyle(Palette.secondary)
                }
                if !diagramPreview.sourceURL.isEmpty {
                    Text(diagramPreview.sourceURL).font(.system(size: 8)).foregroundStyle(Palette.tertiary)
                        .lineLimit(1).truncationMode(.middle)
                }
            }
            if let pendingCurvePreview {
                Label("\(pendingCurvePreview.nodes.filter { $0.kind == "path" }.count) editable stroke(s)",
                      systemImage: "checkmark.circle.fill")
                    .font(.system(size: 10, weight: .medium)).foregroundStyle(Palette.forest)
                Text(pendingCurvePreview.title).font(.system(size: 11, weight: .semibold))
                Text(pendingCurvePreview.provider).font(.system(size: 9)).foregroundStyle(Palette.tertiary)
            }
            HStack {
                Spacer()
                Button("Cancel") { pendingDiagramAt = nil }.keyboardShortcut(.cancelAction)
                    .disabled(diagramBusy)
                if diagramPreview == nil {
                    Button {
                        Task { await requestDiagram() }
                    } label: {
                        HStack(spacing: 6) {
                            Text(diagramBusy ? "Reading board…" : "Generate preview")
                            if diagramBusy { ProgressView().controlSize(.small) }
                        }
                    }
                    .buttonStyle(LuminfestButtonStyle())
                    .disabled(diagramBusy || diagramPrompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                } else {
                    Button("Try again") { diagramPreview = nil }
                        .disabled(diagramBusy)
                    Button("Add to board") { acceptDiagram() }
                        .buttonStyle(LuminfestButtonStyle())
                        .keyboardShortcut(.defaultAction)
                        .disabled(diagramBusy)
                }
            }
        }
        .padding(18)
        .frame(width: 440)
    }

    fileprivate var curveSheet: some View {
        VStack(alignment: .leading, spacing: 11) {
            Label("Plot an editable curve", systemImage: "function")
                .font(.system(size: 14, weight: .semibold))
            Text("Enter math, not executable code. The sampler turns the curve into ordinary editable line strokes.")
                .font(.system(size: 10)).foregroundStyle(Palette.secondary)
            Picker("Curve type", selection: $curveType) {
                Text("Function y=f(x)").tag("function")
                Text("Parametric x(t), y(t)").tag("parametric")
                Text("Fourier series").tag("fourier")
            }
            .pickerStyle(.segmented)
            if curveType == "function" {
                TextField("Example: sin(x) or x^2 / 3", text: $curveExpression)
                    .textFieldStyle(.roundedBorder)
                Text("Allowed: + − × ÷ power, sin/cos/tan, sqrt, log, exp, abs; constants π and e.")
                    .font(.system(size: 9)).foregroundStyle(Palette.tertiary)
            } else if curveType == "parametric" {
                TextField("x(t), e.g. 4*cos(t)", text: $curveXExpression).textFieldStyle(.roundedBorder)
                TextField("y(t), e.g. 2*sin(t)", text: $curveYExpression).textFieldStyle(.roundedBorder)
                TextField("t min, max", text: $curveTRange).textFieldStyle(.roundedBorder)
            } else {
                TextField("Cosine coefficients a₀, a₁…", text: $curveFourierCosine).textFieldStyle(.roundedBorder)
                TextField("Sine coefficients b₁, b₂…", text: $curveFourierSine).textFieldStyle(.roundedBorder)
                Text("Builds y = a₀/2 + Σ(aₙ cos nx + bₙ sin nx). Each component remains a polyline stroke.")
                    .font(.system(size: 9)).foregroundStyle(Palette.tertiary)
            }
            TextField("x min, max", text: $curveXRange).textFieldStyle(.roundedBorder)
            TextField("y min, max", text: $curveYRange).textFieldStyle(.roundedBorder)
            if let pendingCurvePreview {
                Label("\(pendingCurvePreview.nodes.filter { $0.kind == "path" }.count) editable stroke(s)",
                      systemImage: "checkmark.circle.fill")
                    .font(.system(size: 10, weight: .medium)).foregroundStyle(Palette.forest)
                Text(pendingCurvePreview.title).font(.system(size: 11, weight: .semibold))
                Text(pendingCurvePreview.provider).font(.system(size: 9)).foregroundStyle(Palette.tertiary)
            }
            HStack {
                Spacer()
                Button("Cancel") { showingCurves = false; pendingCurvePreview = nil }
                    .keyboardShortcut(.cancelAction)
                if pendingCurvePreview == nil {
                    Button(diagramBusy ? "Sampling…" : "Preview curve") {
                        Task { await requestCurve() }
                    }
                    .buttonStyle(LuminfestButtonStyle())
                    .disabled(diagramBusy)
                } else {
                    Button("Try again") { pendingCurvePreview = nil }
                    Button("Add to board") { acceptCurve() }
                        .buttonStyle(LuminfestButtonStyle())
                        .keyboardShortcut(.defaultAction)
                }
            }
        }
        .padding(18)
        .frame(width: 440)
    }

    fileprivate var diagramCatalogSheet: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Common classroom diagrams", systemImage: "books.vertical")
                .font(.system(size: 14, weight: .semibold))
            Text("Original editable stroke schematics aligned to familiar lesson topics. Khan Academy links are references, not copied frames.")
                .font(.system(size: 10)).foregroundStyle(Palette.secondary)
            HStack {
                TextField("Search supply, cell cycle, PPF…", text: $catalogQuery)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { Task { await loadDiagramCatalog() } }
                Picker("Subject", selection: $catalogSubject) {
                    Text("All").tag("")
                    Text("Economics").tag("economics")
                    Text("Biology").tag("biology")
                }.frame(width: 125)
                Button("Search") { Task { await loadDiagramCatalog() } }
                    .buttonStyle(LuminfestButtonStyle()).disabled(catalogBusy)
            }
            if catalogBusy { ProgressView().controlSize(.small) }
            if let catalogPreview {
                Text("Preview: \(catalogPreview.title) · \(catalogPreview.nodes.filter { $0.kind == "path" }.count) strokes")
                    .font(.system(size: 10, weight: .medium)).foregroundStyle(Palette.forest)
                Text(catalogPreview.note).font(.system(size: 9)).foregroundStyle(Palette.secondary)
            }
            ScrollView {
                LazyVStack(spacing: 7) {
                    ForEach(catalogItems, id: \.self) { item in
                        HStack(alignment: .top, spacing: 10) {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(item["title"].string).font(.system(size: 11, weight: .semibold))
                                Text(item["description"].string).font(.system(size: 9)).foregroundStyle(Palette.secondary)
                                Text(item["source_title"].string).font(.system(size: 8)).foregroundStyle(Palette.tertiary)
                            }
                            Spacer(minLength: 4)
                            Button("Preview") { Task { await previewTemplate(item["id"].string) } }
                                .buttonStyle(.bordered)
                        }
                        .padding(8)
                        .background(Palette.background, in: RoundedRectangle(cornerRadius: 8))
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Palette.line))
                    }
                }
            }.frame(minHeight: 180)
            HStack {
                Spacer()
                Button("Done") { showingDiagramCatalog = false }.keyboardShortcut(.cancelAction)
                Button("Add selected preview") { acceptCatalogPreview() }
                    .buttonStyle(LuminfestButtonStyle())
                    .disabled(catalogPreview == nil)
            }
        }
        .padding(18)
        .frame(width: 600, height: 500)
    }

    fileprivate var vectorizerSheet: some View {
        VStack(alignment: .leading, spacing: 11) {
            Label("Image → editable line strokes", systemImage: "point.topleft.down.to.point.bottomright.curvepath")
                .font(.system(size: 14, weight: .semibold))
            Text("Select a board image first, or paste one onto the board. Local image processing thresholds dark ink, thins it to a 1px skeleton, traces endpoints and junctions, then Fourier-smooths those paths. The preview aligns over the source image; the image is retained. This does not use OCR.")
                .font(.system(size: 10)).foregroundStyle(Palette.secondary)
            if let sourceImageNode {
                HStack(spacing: 8) {
                    if let data = ImageCache.shared.data(sha: sourceImageNode.payload["sha256"].string),
                       let image = NSImage(data: data) {
                        Image(nsImage: image).resizable().scaledToFit().frame(width: 90, height: 62)
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        Text(sourceImageNode.payload.text("title", fallback: "Selected image"))
                            .font(.system(size: 10, weight: .medium))
                        Text("Original image stays on the board; extracted paths are added separately.")
                            .font(.system(size: 9)).foregroundStyle(Palette.secondary)
                    }
                }
            } else {
                Text("No selected image. Close this dialog, select an image node, then choose this tool again.")
                    .font(.system(size: 10, weight: .medium)).foregroundStyle(Palette.indigoDeep)
            }
            HStack {
                Text("Ink threshold")
                Slider(value: $vectorizeThreshold, in: 40...220, step: 1)
                Text("\(Int(vectorizeThreshold))").font(.system(size: 9, design: .monospaced))
                    .frame(width: 28, alignment: .trailing)
            }
            if let vectorizePreview {
                Label("\(vectorizePreview.nodes.filter { $0.kind == "path" }.count) traced line(s)",
                      systemImage: "checkmark.circle.fill")
                    .font(.system(size: 10, weight: .medium)).foregroundStyle(Palette.forest)
                Text(vectorizePreview.note).font(.system(size: 9)).foregroundStyle(Palette.secondary)
                Button(tracePlaying ? "Stop trace" : (vectorizeProgress >= 1 ? "Replay from start" : "Trace from start")) {
                    if tracePlaying { stopTracePlayback = true }
                    else { Task { await playVectorization() } }
                }
                .buttonStyle(.bordered)
            }
            HStack {
                Spacer()
                Button("Cancel") { showingVectorizer = false; vectorizePreview = nil }
                    .keyboardShortcut(.cancelAction)
                if vectorizePreview == nil {
                    Button(vectorizeBusy ? "Tracing image…" : "Extract lines") {
                        Task { await requestVectorization() }
                    }
                    .buttonStyle(LuminfestButtonStyle())
                    .disabled(vectorizeBusy || sourceImageNode == nil)
                } else {
                    Button("Try again") { vectorizePreview = nil }
                    Button("Add strokes") { acceptVectorization() }
                        .buttonStyle(LuminfestButtonStyle())
                        .keyboardShortcut(.defaultAction)
                }
            }
        }
        .padding(18)
        .frame(width: 470)
    }

    private var sourceImageNode: BoardNode? {
        board.nodes.first(where: { $0.kind == "image" && $0.payload["sha256"].string == vectorizeSource })
    }

    private func parsePair(_ text: String, fallback: (Double, Double)) -> (Double, Double)? {
        let pieces = text.split(whereSeparator: { $0 == "," || $0 == " " || $0 == ";" })
        guard pieces.count == 2, let first = Double(pieces[0]), let second = Double(pieces[1]),
              first.isFinite, second.isFinite, second > first else { return nil }
        return (first, second)
    }

    private func parseCoefficients(_ text: String) -> [Double]? {
        let pieces = text.split(whereSeparator: { $0 == "," || $0 == " " || $0 == ";" })
        guard !pieces.isEmpty, pieces.count <= 16 else { return nil }
        let values = pieces.compactMap { Double($0) }
        guard values.count == pieces.count, values.allSatisfy({ $0.isFinite && abs($0) <= 1000 }) else { return nil }
        return values
    }

    private func loadDiagramCatalog() async {
        catalogBusy = true
        defer { catalogBusy = false }
        do {
            guard let api = AppStore.current?.api else { return }
            catalogItems = try await api.json("/diagram-templates", query: [
                URLQueryItem(name: "q", value: catalogQuery),
                URLQueryItem(name: "subject", value: catalogSubject),
            ])["templates"].array
        } catch {
            board.error = error.localizedDescription
        }
    }

    private func previewTemplate(_ id: String) async {
        do {
            guard let api = AppStore.current?.api else { return }
            let result = try await api.json("/boards/\(board.boardID)/diagram/template", method: "POST", body: [
                "template_id": id, "x": Double(insertionPoint.x), "y": Double(insertionPoint.y),
            ])
            let nodes = previewNodes(result["nodes"].array)
            guard !nodes.isEmpty else { throw AppFailure(message: "Template has no valid strokes.", status: nil) }
            catalogPreview = BoardPreview(title: result["title"].string,
                                          provider: result["provider"].string, nodes: nodes,
                                          sourceURL: result["source_url"].string,
                                          note: result["provenance"].string)
            selectedDiagramTemplateID = id
        } catch { board.error = error.localizedDescription }
    }

    private func requestCurve() async {
        guard let api = AppStore.current?.api,
              let xRange = parsePair(curveXRange, fallback: (-10, 10)),
              let yRange = parsePair(curveYRange, fallback: (-10, 10)) else {
            board.error = "Enter valid increasing x and y ranges, such as -10, 10."
            return
        }
        let at = pendingDiagramAt ?? insertionPoint
        var body: [String: Any] = ["curve_type": curveType, "x": Double(at.x), "y": Double(at.y),
                                   "x_min": xRange.0, "x_max": xRange.1,
                                   "y_min": yRange.0, "y_max": yRange.1, "samples": 240]
        if curveType == "function" { body["expression"] = curveExpression }
        if curveType == "parametric" {
            guard let tRange = parsePair(curveTRange, fallback: (0, 2 * .pi)) else {
                board.error = "Enter a valid increasing parameter range."
                return
            }
            body["x_expression"] = curveXExpression
            body["y_expression"] = curveYExpression
            body["t_min"] = tRange.0
            body["t_max"] = tRange.1
        }
        if curveType == "fourier" {
            guard let cosine = parseCoefficients(curveFourierCosine),
                  let sine = parseCoefficients(curveFourierSine) else {
                board.error = "Fourier coefficients must be finite numbers separated by commas."
                return
            }
            body["cosine"] = cosine
            body["sine"] = sine
        }
        diagramBusy = true
        board.error = nil
        defer { diagramBusy = false }
        do {
            let result = try await api.json("/boards/\(board.boardID)/diagram/curve", method: "POST", body: body)
            let nodes = previewNodes(result["nodes"].array)
            guard !nodes.isEmpty else { throw AppFailure(message: "The curve did not intersect the selected plot window.", status: nil) }
            pendingCurvePreview = BoardPreview(title: result["title"].string,
                                               provider: result["provider"].string, nodes: nodes)
        } catch { board.error = error.localizedDescription }
    }

    private func imageDataURL(_ data: Data) -> String? {
        let prefix = Data(data.prefix(12))
        let mime: String
        if prefix.starts(with: Data([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) {
            mime = "image/png"
        } else if prefix.starts(with: Data([0xff, 0xd8, 0xff])) {
            mime = "image/jpeg"
        } else if prefix.starts(with: Data("GIF8".utf8)) {
            mime = "image/gif"
        } else if data.count >= 12,
                  prefix.prefix(4) == Data("RIFF".utf8),
                  prefix.suffix(4) == Data("WEBP".utf8) {
            mime = "image/webp"
        } else {
            return nil
        }
        return "data:\(mime);base64," + data.base64EncodedString()
    }

    private func requestVectorization() async {
        guard let sourceImageNode,
              let source = ImageCache.shared.data(sha: sourceImageNode.payload["sha256"].string),
              let api = AppStore.current?.api else {
            board.error = "Select an available image first."
            return
        }
        guard let dataURL = imageDataURL(source) else {
            board.error = "This image format cannot be traced. Use PNG, JPEG, WebP, or GIF."
            return
        }
        vectorizeBusy = true
        board.error = nil
        defer { vectorizeBusy = false }
        do {
            let result = try await api.json("/boards/\(board.boardID)/diagram/trace", method: "POST", body: [
                "image_data_url": dataURL,
                "x": Double(vectorizeAt.x), "y": Double(vectorizeAt.y),
                "w": Double(vectorizeSize.width), "h": Double(vectorizeSize.height),
                "threshold": Int(vectorizeThreshold),
            ])
            let nodes = previewNodes(result["nodes"].array)
            guard !nodes.isEmpty else { throw AppFailure(message: "No line traces were extracted.", status: nil) }
            vectorizeProgress = 0
            vectorizePreview = BoardPreview(title: result["title"].string,
                                            provider: result["provider"].string, nodes: nodes,
                                            note: "\(result["trace_count"].int) ordered path(s) · each begins at its detected endpoint · source image unchanged")
        } catch { board.error = error.localizedDescription }
    }

    private func previewNodes(_ values: [JSON]) -> [BoardNode] {
        values.compactMap { value -> BoardNode? in
            let kind = value["kind"].string
            guard kind == "path" || kind == "text" else { return nil }
            return BoardNode(id: "preview-" + UUID().uuidString, kind: kind,
                             x: value["x"].double, y: value["y"].double,
                             w: value["w"].double, h: value["h"].double,
                             z: "", payload: value["payload"])
        }
    }

    private func refreshCanvasPreview() {
        if let vectorizePreview {
            canvasPreviewNodes = vectorizePreview.nodes.compactMap { node in
                guard node.kind == "path", vectorizeProgress < 1 else { return node }
                let points = BoardGeometry.points(of: node)
                let visibleCount = Int(ceil(Double(points.count) * vectorizeProgress))
                guard visibleCount >= 2 else { return nil }
                var preview = node
                let shown = Array(points.prefix(visibleCount))
                preview.payload = (try? JSON.make(["points": shown.map { [Double($0.x), Double($0.y)] },
                                                   "colour": node.payload.text("colour", fallback: "#1d4ed8"),
                                                   "width": node.payload["width"].double])) ?? node.payload
                return preview
            }
            return
        }
        let active = diagramPreview ?? pendingCurvePreview ?? catalogPreview
        canvasPreviewNodes = active?.nodes ?? []
    }

    private func playVectorization() async {
        guard vectorizePreview != nil else { return }
        stopTracePlayback = false
        tracePlaying = true
        vectorizeProgress = 0
        defer {
            tracePlaying = false
            if stopTracePlayback { vectorizeProgress = 1 }
        }
        for step in 1...40 {
            if stopTracePlayback || Task.isCancelled { break }
            vectorizeProgress = Double(step) / 40
            try? await Task.sleep(for: .milliseconds(35))
        }
        if !stopTracePlayback { vectorizeProgress = 1 }
    }

    private func acceptCurve() {
        guard let pendingCurvePreview else { return }
        board.addMany(nodes: pendingCurvePreview.nodes)
        notice = "Curve added · \(pendingCurvePreview.title)"
        self.pendingCurvePreview = nil
        showingCurves = false
    }

    private func acceptCatalogPreview() {
        guard let catalogPreview else { return }
        board.addMany(nodes: catalogPreview.nodes)
        notice = "Diagram added · \(catalogPreview.title)"
        self.catalogPreview = nil
        showingDiagramCatalog = false
    }

    private func acceptVectorization() {
        guard let vectorizePreview else { return }
        stopTracePlayback = true
        board.addMany(nodes: vectorizePreview.nodes)
        notice = "Image traced · \(vectorizePreview.nodes.filter { $0.kind == "path" }.count) line strokes"
        self.vectorizePreview = nil
        showingVectorizer = false
    }

    private func requestDiagram() async {
        guard let anchor = pendingDiagramAt,
              !diagramPrompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              let api = AppStore.current?.api else { return }
        diagramBusy = true
        board.error = nil
        defer { diagramBusy = false }

        var snapshotURL: String?
        if diagramUsesSnapshot {
            let region = CGRect(x: anchor.x, y: anchor.y,
                                width: 760, height: 480)
            let nearby = board.nodes.filter { $0.frame.intersects(region) }
            if !nearby.isEmpty {
                guard let image = BoardRenderer.image(of: nearby, in: region),
                      let tiff = image.tiffRepresentation,
                      let rep = NSBitmapImageRep(data: tiff),
                      let png = rep.representation(using: .png, properties: [:]) else {
                    board.error = "This board snapshot could not be captured. Turn snapshot context off or retry."
                    return
                }
                snapshotURL = "data:image/png;base64," + png.base64EncodedString()
            }
        }

        do {
            var body: [String: Any] = ["prompt": diagramPrompt, "x": anchor.x, "y": anchor.y]
            if let snapshotURL { body["snapshot_data_url"] = snapshotURL }
            let result = try await api.json("/boards/\(board.boardID)/diagram", method: "POST", body: body)
            let candidates = result["nodes"].array.compactMap { value -> BoardNode? in
                let kind = value["kind"].string
                guard kind == "path" || kind == "text" else { return nil }
                return BoardNode(id: "preview-" + UUID().uuidString, kind: kind,
                                 x: value["x"].double, y: value["y"].double,
                                 w: value["w"].double, h: value["h"].double,
                                 z: "", payload: value["payload"])
            }
            guard !candidates.isEmpty,
                  candidates.allSatisfy({ $0.kind == "path" || $0.kind == "text" }) else {
                board.error = "The model returned no line diagram. The board was not changed."
                return
            }
            diagramPreview = BoardPreview(title: result["title"].string,
                                           provider: result["provider"].string,
                                           nodes: candidates)
        } catch {
            board.error = error.localizedDescription
        }
    }

    private func acceptDiagram() {
        guard let diagramPreview else { return }
        board.addMany(nodes: diagramPreview.nodes)
        pendingDiagramAt = nil
        notice = "Diagram added · \(diagramPreview.title)"
        self.diagramPreview = nil
    }
}

// MARK: - Ask the tutor

extension BoardEditor {
    /// The snapshot the tutor reads is composited by the *same* renderer the PDF export
    /// uses, so what the model sees is exactly what the learner sees — minus embeds,
    /// which are chips rather than frames for licence reasons.
    fileprivate var askSheet: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("Ask the tutor about this selection", systemImage: "lasso.and.sparkles")
                .font(.system(size: 14, weight: .semibold))
            Text("The selected objects are captured as an image and sent with your question. The answer is pinned back onto the board next to what you selected.")
                .font(.system(size: 11)).foregroundStyle(Palette.secondary)
            TextEditor(text: $questionDraft)
                .font(.system(size: 12)).scrollContentBackground(.hidden)
                .padding(7).frame(height: 84)
                .background(Palette.background, in: RoundedRectangle(cornerRadius: 10))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(Palette.line))
            HStack {
                Spacer()
                Button("Cancel") { askingAbout = nil }.keyboardShortcut(.cancelAction)
                Button {
                    Task { await ask() }
                } label: {
                    HStack {
                        Text(askBusy ? "Thinking…" : "Ask")
                        if askBusy { ProgressView().controlSize(.small) }
                    }
                }
                .keyboardShortcut(.defaultAction)
                .buttonStyle(LuminfestButtonStyle())
                .disabled(askBusy || questionDraft.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        .padding(20)
        .frame(width: 430)
    }

    private func ask() async {
        guard let rect = askingAbout else { askingAbout = nil; return }
        askBusy = true
        defer { askBusy = false; askingAbout = nil }
        let padded = rect.insetBy(dx: -12, dy: -12)
        let nodes = board.nodes.filter { $0.frame.intersects(padded) }
        // The client-side hash is the anchor's provenance: the answer node records which
        // snapshot it answered, so a later reader can tell what was asked about.
        guard let image = BoardRenderer.image(of: nodes, in: padded),
              let tiff = image.tiffRepresentation,
              let rep = NSBitmapImageRep(data: tiff),
              let png = rep.representation(using: .png, properties: [:]) else {
            board.error = "The selection could not be captured; nothing was asked."
            return
        }
        let dataURL = "data:image/png;base64," + png.base64EncodedString()
        do {
            guard let api = AppStore.current?.api else { return }
            let result = try await api.json("/agent/chat", method: "POST", body: [
                "message": questionDraft,
                "developer_mode": false,
                "context": ["concept_id": conceptID, "board_id": board.boardID],
                "images": [dataURL],
            ])
            let answer = result["message"].string
            guard !answer.isEmpty else {
                board.error = "The tutor turn finished without a reply; the selection was not answered."
                return
            }
            #if canImport(CryptoKit)
            let digest = CryptoSHA256.digest(png)
            let sha = digest.map { String(format: "%02x", $0) }.joined()
            #else
            let sha = ""
            #endif
            board.pinAnswer(text: answer, question: questionDraft, imageSHA: sha,
                            at: CGPoint(x: padded.maxX + 24, y: padded.minY))
        } catch {
            board.error = error.localizedDescription
        }
    }
}

// MARK: - Image insert

/// Fetch a licence-cleared photograph and drop it on the board.
///
/// The whole point of this sheet is that a board image is never invented: every candidate
/// arrives through the backend's acquire pipeline, which clears the licence before the
/// bytes are cached, and only a cached asset can be placed. The node records the content
/// hash the board resolves bitmaps by, so the client renders the real file rather than a
/// decorative rectangle, and the credit travels with the node so attribution survives a
/// reload and an export.
private struct ImagePickerSheet: View {
    @ObservedObject var board: BoardStore
    let conceptID: String
    let at: CGPoint

    @State private var query = ""
    @State private var results: [JSON] = []
    @State private var busy = false
    @State private var message = ""
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Find an image").font(.system(size: 14, weight: .semibold))
            HStack(spacing: 8) {
                TextField("Search term, e.g. “mitosis cell diagram”", text: $query)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { search() }
                Button(busy ? "Searching…" : "Search") { search() }
                    .buttonStyle(LuminfestButtonStyle())
                    .disabled(busy || query.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            if !message.isEmpty {
                Text(message).font(.system(size: 10)).foregroundStyle(Palette.secondary).lineLimit(2)
            }
            if busy && results.isEmpty { ProgressView().frame(maxWidth: .infinity) }
            ScrollView {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 10)], spacing: 10) {
                    ForEach(results, id: \.self) { asset in row(asset)
                    }
                }
            }
            .frame(minHeight: 200)
            if results.isEmpty, !busy {
                Text("Nothing fetched yet. Searches return licence-cleared images only; a search with no result says why.")
                    .font(.system(size: 11)).foregroundStyle(Palette.tertiary)
            }
            HStack { Spacer(); Button("Done") { dismiss() }.keyboardShortcut(.cancelAction) }
        }
        .padding(20)
        .frame(width: 520, height: 460)
    }

    @ViewBuilder
    private func row(_ asset: JSON) -> some View {
        let sha = asset["sha256"].string
        Button {
            place(asset)
            dismiss()
        } label: {
            VStack(alignment: .leading, spacing: 6) {
                ZStack {
                    Rectangle().fill(Palette.background)
                    if let data = ImageCache.shared.data(sha: sha), let ns = NSImage(data: data) {
                        Image(nsImage: ns).resizable().scaledToFill()
                    } else {
                        Image(systemName: "photo")
                            .foregroundStyle(Palette.tertiary)
                    }
                }
                .frame(height: 110)
                .clipped()
                .clipShape(RoundedRectangle(cornerRadius: 7))
                Text(asset.text("title", fallback: "Untitled"))
                    .font(.system(size: 10, weight: .medium))
                    .lineLimit(1)
                Text(asset.text("attribution", fallback: "credit unknown"))
                    .font(.system(size: 8.5))
                    .foregroundStyle(Palette.tertiary)
                    .lineLimit(2)
            }
            .padding(6)
            .background(Palette.background, in: RoundedRectangle(cornerRadius: 9))
            .overlay(RoundedRectangle(cornerRadius: 9).stroke(Palette.line))
        }
        .buttonStyle(.plain)
        .help("Place this image with its credit")
    }

    private func search() {
        let term = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !term.isEmpty else { return }
        busy = true
        message = ""
        Task {
            defer { busy = false }
            do {
                guard let api = AppStore.current?.api else { return }
                let result = try await api.json("/images/fetch", method: "POST", body: [
                    "query": term, "concept_id": conceptID, "count": 12,
                ])
                results = result["assets"].array
                let rejected = result["rejected"].array.count
                message = "\(results.count) image(s) cleared"
                    + (rejected > 0 ? " · \(rejected) rejected by the licence gate" : "")
                if results.isEmpty { message += " — nothing was available for that term." }
            } catch {
                message = error.localizedDescription
            }
        }
    }

    /// Place the asset. Width and height are estimated from the image so a photo does not
    /// arrive squashed, which is what happens when a node is created with a default box.
    private func place(_ asset: JSON) {
        let sha = asset["sha256"].string
        var size = CGSize(width: 320, height: 200)
        if let data = ImageCache.shared.data(sha: sha), let ns = NSImage(data: data) {
            let natural = ns.size
            guard natural.width > 1, natural.height > 1 else {
                board.error = "That image could not be measured; it was not placed."
                return
            }
            let scale = min(420 / natural.width, 420 / natural.height, 1)
            size = CGSize(width: natural.width * scale, height: natural.height * scale)
        }
        board.beginEdit()
        board.add(node: BoardNode(
            id: "", kind: "image", x: at.x, y: at.y, w: size.width, h: size.height, z: "",
            payload: (try? JSON.make([
                "sha256": sha,
                "src": "/api/v1/media/images/\(sha)/bytes",
                "title": asset.text("title", fallback: ""),
                "credit": asset.text("attribution", fallback: ""),
                "provider": asset.text("provider", fallback: ""),
                "licence": asset.text("licence", fallback: ""),
                "licence_url": asset.text("licence_url", fallback: ""),
            ])) ?? .null))
    }
}

