import Foundation
import SwiftUI
import AppKit

// The board editor's model layer: what a tool is, what is selected, where a drag snaps,
// what a resize does to a frame, and how an undo is turned back into server mutations.
//
// Everything here is deliberately free of SwiftUI and of the network. The canvas view
// renders it and the store persists it, but the rules live in one place so they can be
// tested directly — a snapping rule that only exists inside a drag handler cannot be
// asserted, and an undo that only exists inside a button closure cannot be checked.

// MARK: - Tools

/// Every tool the board offers, grouped the way the toolbar presents them.
///
/// The set is the union of what the backend node schema can actually store (path, shape,
/// connector, text, image) and the gestures a person expects from a drawing surface. A
/// tool that had no node to write would be a lie in the toolbar, so the mapping from tool
/// to node kind is part of the tool's own definition rather than a switch somewhere else.
enum BoardTool: String, CaseIterable, Identifiable {
    case select, hand
    case pen, highlighter, eraser
    case text, sticky
    case rect, ellipse, line, arrow, connector, diagram
    case image
    case lasso

    var id: String { rawValue }

    /// Toolbar grouping. Ordering inside `allCases` already follows this, so the toolbar
    /// can just insert a divider wherever the group changes.
    enum Group: Int { case navigate, ink, draw, content, ask }
    var group: Group {
        switch self {
        case .select, .hand: return .navigate
        case .pen, .highlighter, .eraser: return .ink
        case .text, .sticky, .rect, .ellipse, .line, .arrow, .connector, .diagram: return .draw
        case .image: return .content
        case .lasso: return .ask
        }
    }

    var icon: String {
        switch self {
        case .select: return "cursorarrow"
        case .hand: return "hand.raised"
        case .pen: return "pencil.tip"
        case .highlighter: return "highlighter"
        case .eraser: return "eraser"
        case .text: return "textformat"
        case .sticky: return "note.text"
        case .rect: return "rectangle"
        case .ellipse: return "circle"
        case .line: return "line.diagonal"
        case .arrow: return "arrow.up.right"
        case .connector: return "arrow.triangle.branch"
        case .diagram: return "scribble.variable"
        case .image: return "photo"
        case .lasso: return "lasso.and.sparkles"
        }
    }

    var label: String {
        switch self {
        case .select: return "Select"
        case .hand: return "Pan"
        case .pen: return "Pen"
        case .highlighter: return "Highlighter"
        case .eraser: return "Eraser"
        case .text: return "Text"
        case .sticky: return "Sticky note"
        case .rect: return "Rectangle"
        case .ellipse: return "Ellipse"
        case .line: return "Line"
        case .arrow: return "Arrow"
        case .connector: return "Connector"
        case .diagram: return "AI diagram"
        case .image: return "Image"
        case .lasso: return "Circle & ask"
        }
    }

    /// Single-key shortcut, matching the convention every drawing tool uses so muscle
    /// memory transfers. Shown in the tool's tooltip, which is also the documentation.
    var shortcut: String {
        switch self {
        case .select: return "V"
        case .hand: return "H"
        case .pen: return "P"
        case .highlighter: return "M"
        case .eraser: return "E"
        case .text: return "T"
        case .sticky: return "N"
        case .rect: return "R"
        case .ellipse: return "O"
        case .line: return "L"
        case .arrow: return "A"
        case .connector: return "C"
        case .diagram: return "G"
        case .image: return "I"
        case .lasso: return "Q"
        }
    }

    /// True for the two tools that lay down ink, which share the pressure/velocity path.
    var isInk: Bool { self == .pen || self == .highlighter }

    /// The node kind this tool produces, or nil when the tool does not create one.
    var nodeKind: String? {
        switch self {
        case .pen, .highlighter: return "path"
        case .text, .sticky: return "text"
        case .rect, .ellipse, .line, .arrow: return "shape"
        case .connector: return "connector"
        case .image: return "image"
        case .select, .hand, .eraser, .lasso, .diagram: return nil
        }
    }

    /// The `shape` payload value, for the four tools that write a shape node.
    var shapeName: String? {
        switch self {
        case .rect: return "rect"
        case .ellipse: return "ellipse"
        case .line: return "line"
        case .arrow: return "arrow"
        case .sticky: return "sticky"
        default: return nil
        }
    }
}

// MARK: - Selection

/// A selection is a set of node ids. Multi-select is a first-class state rather than a
/// modifier on one node, because every bulk operation (move, align, distribute, delete,
/// copy, restyle) needs to see all of them at once.
struct BoardSelection: Equatable {
    private(set) var ids: Set<String> = []

    var isEmpty: Bool { ids.isEmpty }
    var count: Int { ids.count }
    var isSingle: Bool { ids.count == 1 }
    var single: String? { ids.count == 1 ? ids.first : nil }

    func contains(_ id: String) -> Bool { ids.contains(id) }

    mutating func clear() { ids.removeAll() }
    mutating func replace(with id: String) { ids = [id] }
    mutating func replace(with newIDs: Set<String>) { ids = newIDs }
    mutating func toggle(_ id: String) {
        if ids.contains(id) { ids.remove(id) } else { ids.insert(id) }
    }
    mutating func subtract(_ other: Set<String>) { ids.subtract(other) }
}

// MARK: - Resize handles

/// The eight resize grips on a selection's bounding box. `affects` says which edges a
/// handle moves, which is what keeps the resize arithmetic to one implementation instead
/// of eight near-identical ones.
enum ResizeHandle: String, CaseIterable, Identifiable {
    case topLeft, top, topRight, right, bottomRight, bottom, bottomLeft, left

    var id: String { rawValue }

    var movesLeft: Bool { self == .topLeft || self == .left || self == .bottomLeft }
    var movesRight: Bool { self == .topRight || self == .right || self == .bottomRight }
    var movesTop: Bool { self == .topLeft || self == .top || self == .topRight }
    var movesBottom: Bool { self == .bottomLeft || self == .bottom || self == .bottomRight }

    /// Where the grip sits on a box, in the box's own coordinate space.
    func point(in rect: CGRect) -> CGPoint {
        let midX = rect.midX, midY = rect.midY
        switch self {
        case .topLeft: return CGPoint(x: rect.minX, y: rect.minY)
        case .top: return CGPoint(x: midX, y: rect.minY)
        case .topRight: return CGPoint(x: rect.maxX, y: rect.minY)
        case .right: return CGPoint(x: rect.maxX, y: midY)
        case .bottomRight: return CGPoint(x: rect.maxX, y: rect.maxY)
        case .bottom: return CGPoint(x: midX, y: rect.maxY)
        case .bottomLeft: return CGPoint(x: rect.minX, y: rect.maxY)
        case .left: return CGPoint(x: rect.minX, y: midY)
        }
    }

    /// The box after dragging this grip to `point`. A minimum size keeps a box from
    /// inverting through itself, which is the usual way a naive resize loses the shape.
    func resized(_ rect: CGRect, to point: CGPoint, minimum: CGFloat = 8) -> CGRect {
        var minX = rect.minX, maxX = rect.maxX, minY = rect.minY, maxY = rect.maxY
        if movesLeft { minX = min(point.x, maxX - minimum) }
        if movesRight { maxX = max(point.x, minX + minimum) }
        if movesTop { minY = min(point.y, maxY - minimum) }
        if movesBottom { maxY = max(point.y, minY + minimum) }
        return CGRect(x: minX, y: minY, width: maxX - minX, height: maxY - minY)
    }
}

// MARK: - Alignment guides

/// A guide line drawn while dragging, in board coordinates.
struct SnapGuide: Equatable {
    enum Axis { case vertical, horizontal }
    var axis: Axis
    /// The line's coordinate on its own axis (an x for vertical, a y for horizontal).
    var position: Double
    /// The extent of the line along the other axis, so the guide is drawn only as far as
    /// the two things it relates actually span — a full-bleed line implies an alignment
    /// that is not there.
    var start: Double
    var end: Double
}

/// The outcome of a snap: the adjusted point plus the guides that justify it.
struct SnapOutcome: Equatable {
    var point: CGPoint
    var guides: [SnapGuide]
    static func unsnapped(_ point: CGPoint) -> SnapOutcome { SnapOutcome(point: point, guides: []) }
}

/// Edge- and grid-snapping.
///
/// Two rules, in priority order. Alignment with another node beats the grid, because
/// aligning two things to each other is what a person is almost always trying to do and
/// the grid is only a fallback for when there is nothing to align to. Within each rule the
/// nearest candidate wins, so a drag never jumps to a distant guide.
enum SnapEngine {
    /// Candidate distances closer than this (in board units, pre-zoom) are snapped.
    static let threshold: Double = 7

    /// The six alignment positions of a box: both edges and the centre on each axis.
    /// Including centres is what makes "centre these two" work without a separate command.
    static func anchors(of rect: CGRect) -> [(axis: SnapGuide.Axis, value: Double)] {
        [ (.vertical, rect.minX), (.vertical, rect.midX), (.vertical, rect.maxX),
          (.horizontal, rect.minY), (.horizontal, rect.midY), (.horizontal, rect.maxY) ]
    }

    /// Snap `moving` against `others`. `delta` is the raw drag translation being tested.
    ///
    /// The return value is the *corrected translation*, not an absolute point, so the
    /// caller can apply the same correction to every node in a multi-node selection
    /// without each node re-deriving it (which is how a group drag shears apart).
    static func snap(moving: CGRect, others: [CGRect], delta: CGVector,
                     grid: Double?, threshold: Double = threshold) -> (CGVector, [SnapGuide]) {
        let moved = moving.offsetBy(dx: delta.dx, dy: delta.dy)
        var bestX: (adjust: Double, distance: Double)?
        var bestY: (adjust: Double, distance: Double)?
        var guides: [SnapGuide] = []

        // Rule 1 — align to another node.
        for other in others {
            for (axis, value) in anchors(of: moved) {
                for (otherAxis, otherValue) in anchors(of: other) where otherAxis == axis {
                    let distance = abs(otherValue - value)
                    guard distance <= threshold else { continue }
                    let adjust = otherValue - value
                    if axis == .vertical {
                        if bestX == nil || distance < bestX!.distance { bestX = (adjust, distance) }
                    } else {
                        if bestY == nil || distance < bestY!.distance { bestY = (adjust, distance) }
                    }
                }
            }
        }

        var adjusted = CGVector(dx: delta.dx + (bestX?.adjust ?? 0),
                                dy: delta.dy + (bestY?.adjust ?? 0))

        // Rule 2 — the grid, only where rule 1 found nothing.
        if let grid, grid > 0 {
            if bestX == nil {
                let target = (moved.minX / grid).rounded() * grid
                let distance = abs(target - moved.minX)
                if distance <= threshold { adjusted.dx += target - moved.minX }
            }
            if bestY == nil {
                let target = (moved.minY / grid).rounded() * grid
                let distance = abs(target - moved.minY)
                if distance <= threshold { adjusted.dy += target - moved.minY }
            }
        }

        // Build the guides from the *final* geometry, so a guide can never be drawn at a
        // position the shape did not actually reach.
        let settled = moving.offsetBy(dx: adjusted.dx, dy: adjusted.dy)
        for other in others {
            for (axis, value) in anchors(of: settled) {
                for (otherAxis, otherValue) in anchors(of: other)
                where otherAxis == axis && abs(otherValue - value) <= 0.5 {
                    if axis == .vertical {
                        guides.append(SnapGuide(axis: .vertical, position: otherValue,
                                                start: min(settled.minY, other.minY),
                                                end: max(settled.maxY, other.maxY)))
                    } else {
                        guides.append(SnapGuide(axis: .horizontal, position: otherValue,
                                                start: min(settled.minX, other.minX),
                                                end: max(settled.maxX, other.maxX)))
                    }
                }
            }
        }
        return (adjusted, dedupe(guides))
    }

    /// The same anchor pair can be found from several candidate nodes; one line is enough.
    private static func dedupe(_ guides: [SnapGuide]) -> [SnapGuide] {
        var seen = Set<String>()
        return guides.filter { guide in
            let key = "\(guide.axis)\(Int(guide.position.rounded()))"
            return seen.insert(key).inserted
        }
    }
}

// MARK: - Alignment commands

enum AlignCommand: String, CaseIterable, Identifiable {
    case left, centreX, right, top, middleY, bottom
    var id: String { rawValue }
    var icon: String {
        switch self {
        case .left: return "align.horizontal.left"
        case .centreX: return "align.horizontal.center"
        case .right: return "align.horizontal.right"
        case .top: return "align.vertical.top"
        case .middleY: return "align.vertical.center"
        case .bottom: return "align.vertical.bottom"
        }
    }
    var label: String {
        switch self {
        case .left: return "Align left"
        case .centreX: return "Align horizontal centres"
        case .right: return "Align right"
        case .top: return "Align top"
        case .middleY: return "Align vertical centres"
        case .bottom: return "Align bottom"
        }
    }
}

enum DistributeCommand: String, CaseIterable, Identifiable {
    case horizontal, vertical
    var id: String { rawValue }
    var icon: String { self == .horizontal ? "distribute.horizontal.center" : "distribute.vertical.center" }
    var label: String { self == .horizontal ? "Distribute horizontally" : "Distribute vertically" }
}

// MARK: - Undo

/// A board snapshot, enough to restore the canvas exactly.
struct BoardState: Equatable {
    var nodes: [BoardNode]
    var version: Int
}

/// A bounded undo/redo history.
///
/// Snapshots rather than inverse-commands: a board is at most 800 nodes of small payloads,
/// so the memory cost is trivial, while the correctness win is large — an inverse-command
/// scheme has to get every one of move/resize/restyle/reorder/delete-in-a-multi-select
/// right, and a single wrong inverse corrupts the document silently. The cap is what keeps
/// "trivial" true for a long session.
struct BoardHistory {
    private var past: [BoardState] = []
    private var future: [BoardState] = []
    private let limit: Int

    init(limit: Int = 80) { self.limit = limit }

    var canUndo: Bool { !past.isEmpty }
    var canRedo: Bool { !future.isEmpty }
    var depth: Int { past.count }

    /// Record the state *before* an edit. Any new edit invalidates the redo branch —
    /// keeping it would let a redo restore a state that no longer follows from anything.
    mutating func record(_ state: BoardState) {
        past.append(state)
        if past.count > limit { past.removeFirst(past.count - limit) }
        future.removeAll()
    }

    /// Step back, handing the current state over so it can be redone.
    mutating func undo(current: BoardState) -> BoardState? {
        guard let previous = past.popLast() else { return nil }
        future.append(current)
        return previous
    }

    mutating func redo(current: BoardState) -> BoardState? {
        guard let next = future.popLast() else { return nil }
        past.append(current)
        return next
    }

    mutating func reset() { past.removeAll(); future.removeAll() }
}

// MARK: - Clipboard

/// An in-app clipboard for board content.
///
/// Deliberately not the system pasteboard: pasting a node is pasting a *structure* (a path
/// with its pressure, an image with its licence and credit, a text box with its styling),
/// and the system pasteboard would carry only one of those faithfully. Slides and elements
/// in the deck editor use the same idea for the same reason.
/// A temporary collection of generated/imported nodes, never a server-persisted type.
struct BoardPreview: Identifiable {
    let id: String
    let title: String
    let provider: String
    let nodes: [BoardNode]
    let sourceURL: String
    let note: String

    init(title: String, provider: String, nodes: [BoardNode],
         sourceURL: String = "", note: String = "") {
        self.id = UUID().uuidString
        self.title = title
        self.provider = provider
        self.nodes = nodes
        self.sourceURL = sourceURL
        self.note = note
    }
}

enum BoardClipboard {
    private(set) static var nodes: [BoardNode] = []
    private(set) static var sourcePasteboardChangeCount: Int?
    /// How far a paste is offset from the original, so the copy is visibly a copy instead
    /// of landing exactly on top of its source.
    static let pasteOffset: Double = 24

    static var isEmpty: Bool { nodes.isEmpty }
    static var count: Int { nodes.count }

    static func copy(_ items: [BoardNode]) {
        // Sorted so a paste preserves the relative stacking order it was copied with.
        nodes = items.sorted { $0.z < $1.z }
        sourcePasteboardChangeCount = NSPasteboard.general.changeCount
    }

    /// An external copy supersedes this in-app copy; without the generation check a
    /// stale board object would mask a newly copied image from another app.
    static var matchesSystemPasteboard: Bool {
        !nodes.isEmpty && sourcePasteboardChangeCount == NSPasteboard.general.changeCount
    }

    static func clear() {
        nodes = []
        sourcePasteboardChangeCount = nil
    }

    /// The nodes to paste, translated so the group's top-left lands at `at` when given.
    /// Returns an empty array when the clipboard is empty, which the caller treats as
    /// "nothing to do" rather than an error.
    static func paste(at origin: CGPoint? = nil) -> [BoardNode] {
        guard !nodes.isEmpty else { return [] }
        let bounds = BoardGeometry.bounds(of: nodes)
        let dx: Double, dy: Double
        if let origin, !bounds.isNull {
            dx = origin.x - bounds.minX
            dy = origin.y - bounds.minY
        } else {
            dx = pasteOffset
            dy = pasteOffset
        }
        return nodes.map { node in
            var copy = node
            copy.x = node.x + dx
            copy.y = node.y + dy
            if node.kind == "connector" { copy.translatePayload(dx: dx, dy: dy) }
            return copy
        }
    }
}

// MARK: - Geometry

enum BoardGeometry {
    /// The bounding box of a node, whichever kind it is.
    ///
    /// A path stores its extent as x/y/w/h on the node, but a path whose points are the
    /// only truth would drift if those went stale, so paths and connectors are measured
    /// from their own geometry. Everything else uses the node frame.
    static func bounds(of node: BoardNode) -> CGRect {
        switch node.kind {
        case "path":
            let points = points(of: node)
            guard !points.isEmpty else { return node.frame }
            return CGRect(points: points)
        case "connector":
            let a = CGPoint(x: node.payload["x"].double, y: node.payload["y"].double)
            let b = CGPoint(x: node.payload["x2"].double, y: node.payload["y2"].double)
            return CGRect(points: [a, b])
        default:
            return node.frame
        }
    }

    static func bounds(of nodes: [BoardNode]) -> CGRect {
        var rect = CGRect.null
        for node in nodes { rect = rect.union(bounds(of: node)) }
        return rect
    }

    static func points(of node: BoardNode) -> [CGPoint] {
        node.payload["points"].array.compactMap { pair -> CGPoint? in
            let values = pair.array
            guard values.count >= 2 else { return nil }
            return CGPoint(x: values[0].double, y: values[1].double)
        }
    }

    /// Per-point pressure for a stroke, padded or truncated to the point count so the
    /// renderer never has to guard its own indexing.
    static func pressure(of node: BoardNode) -> [CGFloat] {
        let raw = node.payload["pressure"].array.map { CGFloat($0.double) }
        let count = points(of: node).count
        guard count > 0 else { return [] }
        if raw.count == count { return raw.map { min(1, max(0.05, $0)) } }
        let fallback = raw.isEmpty ? 0.5 : raw.reduce(0, +) / CGFloat(raw.count)
        return Array(repeating: min(1, max(0.05, fallback)), count: count)
    }

    /// A frame that always has drawable size, so a freshly created node is visible.
    static func visibleFrame(_ node: BoardNode) -> CGRect {
        let rect = bounds(of: node)
        return rect.width >= 4 && rect.height >= 4
            ? rect
            : CGRect(x: rect.minX, y: rect.minY, width: max(rect.width, 24), height: max(rect.height, 24))
    }

    /// Alignment: move every node so the chosen edge or centre matches the group's own.
    /// The group's extreme is the reference, which is what "align left" means when the
    /// thing being aligned to is the selection itself.
    static func aligned(_ nodes: [BoardNode], by command: AlignCommand) -> [BoardNode] {
        guard nodes.count > 1 else { return nodes }
        let group = bounds(of: nodes)
        return nodes.map { node in
            var moved = node
            let frame = bounds(of: node)
            switch command {
            case .left: moved.shift(dx: group.minX - frame.minX, dy: 0)
            case .right: moved.shift(dx: group.maxX - frame.maxX, dy: 0)
            case .centreX: moved.shift(dx: group.midX - frame.midX, dy: 0)
            case .top: moved.shift(dx: 0, dy: group.minY - frame.minY)
            case .bottom: moved.shift(dx: 0, dy: group.maxY - frame.maxY)
            case .middleY: moved.shift(dx: 0, dy: group.midY - frame.midY)
            }
            return moved
        }
    }

    /// Distribute: keep the two extremes still and equalise the gaps between the rest.
    /// Nodes are ordered by their own position, not by array order, so the result is what
    /// a person sees rather than what the document happens to hold.
    static func distributed(_ nodes: [BoardNode], by command: DistributeCommand) -> [BoardNode] {
        guard nodes.count > 2 else { return nodes }
        let horizontal = command == .horizontal
        let ordered = nodes.sorted {
            horizontal ? bounds(of: $0).minX < bounds(of: $1).minX
                       : bounds(of: $0).minY < bounds(of: $1).minY
        }
        let group = bounds(of: ordered)
        let total = ordered.reduce(CGFloat(0)) { $0 + (horizontal ? bounds(of: $1).width : bounds(of: $1).height) }
        let span = horizontal ? group.width : group.height
        let gap = max(0, (span - total) / CGFloat(ordered.count - 1))

        var cursor = horizontal ? group.minX : group.minY
        var output: [BoardNode] = []
        for node in ordered {
            var moved = node
            let frame = bounds(of: node)
            let target = cursor
            moved.shift(dx: horizontal ? target - frame.minX : 0,
                        dy: horizontal ? 0 : target - frame.minY)
            cursor = target + (horizontal ? frame.width : frame.height) + gap
            output.append(moved)
        }
        return output
    }
}

// MARK: - Node helpers used by the editor

extension BoardNode {
    /// Translate the node itself, and its payload for the kinds that store their own
    /// geometry inside the payload (a connector's endpoints).
    mutating func shift(dx: CGFloat, dy: CGFloat) {
        x += Double(dx)
        y += Double(dy)
        translatePayload(dx: dx, dy: dy)
    }

    mutating func translatePayload(dx: CGFloat, dy: CGFloat) {
        guard kind == "connector" else { return }
        guard case .object(var object) = payload else { return }
        if case .number(let ax) = object["x"] ?? .null { object["x"] = .number(ax + Double(dx)) }
        if case .number(let ay) = object["y"] ?? .null { object["y"] = .number(ay + Double(dy)) }
        if case .number(let bx) = object["x2"] ?? .null { object["x2"] = .number(bx + Double(dx)) }
        if case .number(let by) = object["y2"] ?? .null { object["y2"] = .number(by + Double(dy)) }
        payload = .object(object)
    }

    /// Resize by rewriting the frame, keeping a path's points in step so the stored
    /// geometry and the stored frame cannot disagree.
    mutating func resize(to rect: CGRect) {
        let old = BoardGeometry.bounds(of: self)
        guard old.width > 0.01, old.height > 0.01 else {
            x = Double(rect.minX); y = Double(rect.minY)
            w = Double(rect.width); h = Double(rect.height)
            return
        }
        let sx = rect.width / old.width, sy = rect.height / old.height
        switch kind {
        case "path":
            guard case .object(var object) = payload, case .array(let raw) = object["points"] ?? .null else { break }
            let scaled: [JSON] = raw.map { pair in
                let values = pair.array
                guard values.count >= 2 else { return pair }
                return .array([.number(rect.minX + (values[0].double - Double(old.minX)) * Double(sx)),
                               .number(rect.minY + (values[1].double - Double(old.minY)) * Double(sy))])
            }
            object["points"] = .array(scaled)
            payload = .object(object)
            x = Double(rect.minX); y = Double(rect.minY)
            w = Double(rect.width); h = Double(rect.height)
        case "connector":
            guard case .object(var object) = payload else { break }
            func scale(_ key: String, _ origin: Double, _ factor: Double, _ base: Double) {
                if case .number(let v) = object[key] ?? .null {
                    object[key] = .number(origin + (v - base) * factor)
                }
            }
            scale("x", Double(rect.minX), Double(sx), Double(old.minX))
            scale("y", Double(rect.minY), Double(sy), Double(old.minY))
            scale("x2", Double(rect.minX), Double(sx), Double(old.minX))
            scale("y2", Double(rect.minY), Double(sy), Double(old.minY))
            payload = .object(object)
            x = Double(rect.minX); y = Double(rect.minY)
            w = Double(rect.width); h = Double(rect.height)
        default:
            x = Double(rect.minX); y = Double(rect.minY)
            w = Double(rect.width); h = Double(rect.height)
        }
    }

    /// A short human label for the layers list and the tutor digest.
    var summaryLabel: String {
        switch kind {
        case "path": return "Ink · \(BoardGeometry.points(of: self).count) pts"
        case "text":
            let value = payload["text"].string
            return value.isEmpty ? "Text" : "“" + String(value.prefix(28)) + "”"
        case "shape": return "Shape · \(payload["shape"].string)"
        case "connector": return "Connector"
        case "image": return payload.text("title", fallback: "Image")
        case "video": return payload.text("title", fallback: "Video")
        case "simulation": return payload.text("title", fallback: "Simulation")
        case "answer": return "Tutor answer"
        default: return kind
        }
    }

    var symbolName: String {
        switch kind {
        case "path": return "scribble"
        case "text": return "textformat"
        case "shape": return payload["shape"].string == "sticky" ? "note.text" : "square.on.circle"
        case "connector": return "arrow.triangle.branch"
        case "image": return "photo"
        case "video": return "play.rectangle"
        case "simulation": return "dial.min"
        case "answer": return "text.bubble"
        default: return "questionmark"
        }
    }
}

// MARK: - Ink sampling

/// Turns a raw pointer stream into the stroke that gets stored.
///
/// Two things happen here, and both exist because of the "the marker needs a hard press"
/// complaint. First, width is derived from *velocity* when the hardware reports no usable
/// pressure — a trackpad reports exactly 1.0 on every click, which the old code clamped to
/// a flat 0.5, so every stroke came out identical and lifeless. Second, the stroke is
/// decimated before it is sent, because a 60 Hz pointer over a long stroke is thousands of
/// points and the board caps a path at 800.
enum InkSampler {
    /// Pointer samples are dropped closer together than this (board units). Roughly one
    /// sample per 3 screen pixels at 100% zoom: dense enough that a curve reads as smooth,
    /// sparse enough that a full-width stroke stays well inside the server's point cap.
    static let minimumSpacing: CGFloat = 1.6

    /// Velocity→width response. A stroke drawn at `slowSpeed` or below is at full weight;
    /// by `fastSpeed` it has thinned to `floor` of it. Chosen so a deliberate line stays
    /// bold and a flick tapers, which is the physical intuition of a felt tip.
    static let slowSpeed: CGFloat = 220
    static let fastSpeed: CGFloat = 2600
    static let floor: CGFloat = 0.42

    /// Whether a new sample should be kept, given the previous one.
    static func shouldAccept(_ previous: CGPoint?, _ point: CGPoint) -> Bool {
        guard let previous else { return true }
        return hypot(point.x - previous.x, point.y - previous.y) >= minimumSpacing
    }

    /// Per-sample pressure. Real hardware pressure wins where it is informative; otherwise
    /// the value is derived from how fast the pointer was moving between neighbours.
    static func pressures(points: [CGPoint], reported: [CGFloat], useHardware: Bool) -> [CGFloat] {
        guard !points.isEmpty else { return [] }
        if useHardware, reported.count == points.count,
           reported.contains(where: { $0 > 0.06 && $0 < 0.97 }) {
            return reported.map { min(1, max(0.05, $0)) }
        }
        guard points.count > 2 else { return Array(repeating: 0.6, count: points.count) }
        var out: [CGFloat] = []
        out.reserveCapacity(points.count)
        for index in points.indices {
            let previous = points[max(0, index - 1)]
            let next = points[min(points.count - 1, index + 1)]
            let travel = hypot(next.x - previous.x, next.y - previous.y)
            // A two-sample window understates speed, so scale it by the window's width.
            let speed = travel * 2
            let t = min(1, max(0, (speed - slowSpeed) / (fastSpeed - slowSpeed)))
            out.append(1 - t * (1 - floor))
        }
        out[0] = out.first ?? 0.6
        out[out.count - 1] = out.last ?? 0.6
        return out
    }

    /// The single width a stored stroke carries. The server's path payload has one width,
    /// so the stroke's *weight* is the average of its per-sample pressure — the shape of
    /// the line is still drawn from the full pressure curve on the client.
    static func storedWidth(_ pressures: [CGFloat], base: CGFloat) -> Double {
        guard !pressures.isEmpty else { return Double(base) }
        let mean = pressures.reduce(0, +) / CGFloat(pressures.count)
        return Double(min(48, max(0.3, base * (0.55 + 0.9 * mean))))
    }

    /// Simplify a stroke for storage, keeping the first and last samples so a stroke never
    /// appears to start or end somewhere it did not.
    static func decimate(_ points: [CGPoint], limit: Int = 780) -> [CGPoint] {
        guard points.count > limit else { return points }
        let step = Double(points.count - 1) / Double(limit - 1)
        var out: [CGPoint] = []
        out.reserveCapacity(limit)
        for index in 0..<limit {
            out.append(points[min(points.count - 1, Int((Double(index) * step).rounded()))])
        }
        return out
    }

    /// The same selection, applied to a parallel pressure array.
    static func decimate(_ pressures: [CGFloat], to count: Int) -> [CGFloat] {
        guard pressures.count > count, count > 1 else { return pressures }
        let step = Double(pressures.count - 1) / Double(count - 1)
        return (0..<count).map { pressures[min(pressures.count - 1, Int((Double($0) * step).rounded()))] }
    }
}

// MARK: - Recent colours

/// The colours a learner actually reaches for, most recent first. A fixed swatch row is
/// fine until the third time you need the same ochre; remembering it is the difference
/// between a palette and a decoration.
enum BoardInkMemory {
    private static let key = "luminfest.board.recentColours"
    private static let limit = 8

    static var recent: [String] {
        get { UserDefaults.standard.stringArray(forKey: key) ?? [] }
        set {
            var seen = Set<String>()
            let cleaned = newValue.filter { seen.insert($0).inserted }.prefix(limit)
            UserDefaults.standard.set(Array(cleaned), forKey: key)
        }
    }

    static func remember(_ hex: String) {
        guard !hex.isEmpty else { return }
        recent = [hex] + recent.filter { $0 != hex }
    }
}
