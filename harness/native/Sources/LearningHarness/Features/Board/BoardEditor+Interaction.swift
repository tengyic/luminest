import SwiftUI
import AppKit

// MARK: - Interaction

extension BoardEditor {
    func press(_ location: CGPoint, in size: CGSize, pressure: CGFloat) {
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

        case .visual:
            visualAnchor = point
            showingVisualGallery = true

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

    func drag(to location: CGPoint, in size: CGSize, pressure: CGFloat) {
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

    func release(at location: CGPoint, in size: CGSize) {
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

    func rect(from a: CGPoint, to b: CGPoint) -> CGRect {
        CGRect(x: min(a.x, b.x), y: min(a.y, b.y), width: abs(b.x - a.x), height: abs(b.y - a.y))
    }

    func bounds(of points: [CGPoint]) -> CGRect? {
        guard let first = points.first else { return nil }
        var rect = CGRect(x: first.x, y: first.y, width: 0, height: 0)
        for point in points.dropFirst() { rect = rect.union(CGRect(x: point.x, y: point.y, width: 0, height: 0)) }
        return rect
    }

    /// The grip under the pointer, or nil. Measured in board units with a screen-constant
    /// radius, so a grip stays clickable at every zoom instead of shrinking away.
    func grip(at location: CGPoint, in size: CGSize) -> ResizeHandle? {
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

    func resize(to point: CGPoint, grip: ResizeHandle) {
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
    func commitStroke(reported: [CGFloat]) {
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

    func erase(at point: CGPoint) {
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
