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

// MARK: - The editor

struct BoardEditor: View {
    @ObservedObject var board: BoardStore
    let conceptID: String
    /// Only for interaction telemetry: which node kinds the learner actually reaches for.
    /// Nothing on this screen is scored, so this is a reading of attention, not of learning.
    @EnvironmentObject var store: AppStore

    // ---------------------------------------------------------------- tool state
    @State var tool: BoardTool = .pen
    @State var colour = "#1d4ed8"
    @State var width: Double = 2.6
    @State var eraserMode: BoardEraserMode = .stroke
    @State var snapToGrid = false
    @State var gridStep: Double = 40
    @State var selection = BoardSelection()
    @State var showLayers = true
    @State var notice: String?

    // ---------------------------------------------------------------- viewport
    @State var viewport = BoardViewport()

    // ---------------------------------------------------------------- live gesture
    /// All live-gesture state is in **board** coordinates, never view coordinates, so the
    /// pointer never has to be re-derived after a zoom mid-drag.
    @State var livePoints: [CGPoint] = []
    @State var livePressure: [CGFloat] = []
    @State var liveBox: CGRect?
    @State var liveConnector: (from: CGPoint, to: CGPoint)?
    @State var liveLasso: [CGPoint] = []
    @State var marquee: CGRect?
    @State var guides: [SnapGuide] = []

    /// Nodes being dragged, with the box each one started at so a snap can be applied to
    /// all of them as one correction.
    @State var dragIDs: Set<String> = []
    @State var dragOrigin: CGPoint?
    @State var dragBase: [String: CGRect] = [:]
    @State var dragDidMove = false

    @State var resizeHandle: ResizeHandle?
    @State var resizeBase: [String: CGRect] = [:]
    @State var resizeGroup: CGRect?

    // ---------------------------------------------------------------- sheets
    @State var pendingTextAt: CGPoint?
    @State var textDraft = ""
    @State var pendingStickyAt: CGPoint?
    @State var askingAbout: CGRect?
    @State var questionDraft = ""
    @State var askBusy = false
    @State var showingImages = false
    @State var pendingDiagramAt: CGPoint?
    @State var showingCurves = false
    @State var showingDiagramCatalog = false
    @State var showingVectorizer = false
    @State var diagramPrompt = ""
    @State var catalogItems: [JSON] = []
    @State var catalogQuery = ""
    @State var catalogSubject = ""
    @State var catalogBusy = false
    @State var vectorizeBusy = false
    @State var vectorizeThreshold = 145.0
    @State var vectorizePreview: BoardPreview?
    @State var vectorizeProgress = 1.0
    @State var tracePlaying = false
    @State var stopTracePlayback = false
    @State var diagramUsesSnapshot = true
    @State var diagramBusy = false
    @State var diagramPreview: BoardPreview?
    @State var pendingCurvePreview: BoardPreview?
    @State var selectedDiagramTemplateID = "economics.supply-demand"
    @State var catalogPreview: BoardPreview?
    @State var curveType = "function"
    @State var curveExpression = "sin(x)"
    @State var curveXExpression = "cos(t)"
    @State var curveYExpression = "sin(t)"
    @State var curveFourierCosine = "0, 0, 0.6, 0"
    @State var curveFourierSine = "0, 1"
    @State var curveXRange = "-10, 10"
    @State var curveYRange = "-10, 10"
    @State var curveTRange = "0, 6.283185"
    @State var vectorizeSource = ""
    @State var vectorizeAt = CGPoint.zero
    @State var vectorizeSize = CGSize(width: 760, height: 480)
    @State var canvasPreviewNodes: [BoardNode] = []
    @State var showingVisualGallery = false
    @State var visualAnchor: CGPoint? = nil

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
        .sheet(isPresented: $showingVisualGallery) {
            VisualGalleryView(catalog: VisualResources.catalog,
                onCreate: { type, title, spec in
                    insertVisual(type: type, title: title, spec: spec)
                    showingVisualGallery = false
                    visualAnchor = nil
                    tool = .select
                },
                onCancel: {
                    showingVisualGallery = false
                    visualAnchor = nil
                })
        }
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

    var selectedNodes: [BoardNode] {
        board.nodes.filter { selection.contains($0.id) }
    }

    var selectionBounds: CGRect {
        BoardGeometry.bounds(of: selectedNodes)
    }

    /// Where a new image lands: the centre of what you are looking at, so inserting never
    /// puts a photograph off-screen at the current zoom.
    var insertionPoint: CGPoint { viewport.centre }

    // ---------------------------------------------------------------- toolbar

    var toolbar: some View {
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

    var toolGroup: some View {
        Group {
            ForEach(BoardTool.allCases) { candidate in
                if candidate != BoardTool.allCases.first, previousGroup(candidate) != candidate.group {
                    Divider().frame(width: 1, height: 20)
                }
                toolButton(for: candidate)
            }
        }
    }

    func previousGroup(_ tool: BoardTool) -> BoardTool.Group {
        let ordered = BoardTool.allCases
        guard let index = ordered.firstIndex(of: tool), index > 0 else { return tool.group }
        return ordered[ordered.index(before: index)].group
    }

    func toolButton(for candidate: BoardTool) -> some View {
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
    var inkGroup: some View {
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

    var caseShapeTools: Set<BoardTool> { [.rect, .ellipse, .line, .arrow, .sticky] }

    @State var shapeKind = "rect"
    var shapeBinding: Binding<String> {
        Binding(get: { tool.shapeName ?? shapeKind },
                set: { new in shapeKind = new })
    }

    @ViewBuilder
    var editGroup: some View {
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
    var zoomGroup: some View {
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

    var canvas: some View {
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
                // Interactive renderers live above the Canvas. They are positioned with
                // the same viewport transform, so panning and zooming track the ink.
                visualOverlay(in: size)
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
    func gridLayer(in size: CGSize) -> some View {
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

    var footer: some View {
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
