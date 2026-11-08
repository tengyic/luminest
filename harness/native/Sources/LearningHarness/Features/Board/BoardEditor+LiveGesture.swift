import SwiftUI
import AppKit

// MARK: - Live gesture and overlays

extension BoardEditor {
    /// What the pointer is doing right now, drawn on top of the committed document.
    ///
    /// Kept separate from ``drawNodes`` because live geometry is board-space already and
    /// should never be routed through the node transform — a stroke being drawn has no
    /// stored bounds yet, which is precisely what the live path exists for.
    func drawLive(in ctx: inout GraphicsContext, size: CGSize) {
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
    func enterBoardSpace(_ ctx: inout GraphicsContext, size: CGSize) {
        ctx.translateBy(x: size.width / 2, y: size.height / 2)
        ctx.scaleBy(x: viewport.zoom, y: viewport.zoom)
        ctx.translateBy(x: -viewport.centre.x, y: -viewport.centre.y)
    }

    /// The smallest enclosing box of several boxes. `CGRect.union` takes exactly two, and
    /// a selection is a variable number, so this is the loop that keeps the call sites
    /// honest instead of a chain of nested unions.
    func union(_ rects: [CGRect]) -> CGRect {
        var result = CGRect.null
        for rect in rects { result = result.isNull ? rect : result.union(rect) }
        return result
    }

    func drawOverlays(in ctx: inout GraphicsContext, size: CGSize) {
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
