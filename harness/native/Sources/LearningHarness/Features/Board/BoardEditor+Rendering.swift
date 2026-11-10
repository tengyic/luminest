import SwiftUI
import AppKit

// MARK: - Rendering

extension BoardEditor {
    /// The smallest line width a stroke is drawn at, in board units.
    ///
    /// Strokes are stored in absolute board units, so at 12% zoom a 2 pt stroke is
    /// 0.24 pt on screen and simply vanishes. Floors like this are why a board full of
    /// fine ink stays legible when you zoom out to find things.
    var hairline: CGFloat { 0.9 / max(0.01, viewport.zoom) }

    func tint(_ hex: String, fallback: Color = .primary) -> Color {
        hex.isEmpty ? fallback : Color(hexString: hex)
    }

    func drawNodes(in ctx: inout GraphicsContext, size: CGSize) {
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
    func drawNode(_ node: BoardNode, in ctx: inout GraphicsContext) {
        switch node.kind {
        case "path": drawStroke(node, in: &ctx)
        case "shape": drawShape(node, in: &ctx)
        case "connector": drawConnector(node, in: &ctx)
        case "text": drawText(node, in: &ctx)
        case "answer": drawAnswer(node, in: &ctx)
        case "image": drawImage(node, in: &ctx)
        case "video", "simulation": drawChip(node, in: &ctx)
        case "visual": drawVisualCard(node, in: &ctx)
        default: break
        }
    }

    // MARK: kinds

    func drawStroke(_ node: BoardNode, in ctx: inout GraphicsContext) {
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

    func drawShape(_ node: BoardNode, in ctx: inout GraphicsContext) {
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

    func drawArrowHead(from: CGPoint, to: CGPoint, colour: Color, in ctx: inout GraphicsContext) {
        let angle = atan2(to.y - from.y, to.x - from.x)
        let length: CGFloat = 12
        var head = Path()
        head.move(to: to)
        head.addLine(to: CGPoint(x: to.x - length * cos(angle - 0.42), y: to.y - length * sin(angle - 0.42)))
        head.addLine(to: CGPoint(x: to.x - length * cos(angle + 0.42), y: to.y - length * sin(angle + 0.42)))
        head.closeSubpath()
        ctx.fill(head, with: .color(colour))
    }

    func drawConnector(_ node: BoardNode, in ctx: inout GraphicsContext) {
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

    func drawText(_ node: BoardNode, in ctx: inout GraphicsContext) {
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

    func drawAnswer(_ node: BoardNode, in ctx: inout GraphicsContext) {
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

    func drawImage(_ node: BoardNode, in ctx: inout GraphicsContext) {
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

    /// The Canvas layer draws a labelled frame where the live WebView will be overlaid.
    /// It never claims the interactive content is present here.
    func drawVisualCard(_ node: BoardNode, in ctx: inout GraphicsContext) {
        let box = node.frame
        var card = Path()
        card.addRoundedRect(in: box, cornerSize: CGSize(width: 8, height: 8))
        ctx.fill(card, with: .color(Palette.surface))
        ctx.stroke(card, with: .color(Palette.indigoDeep), lineWidth: max(hairline, 1.1))
        let kind = node.payload["type"].string.uppercased()
        let heading = node.payload.text("title", fallback: kind)
        drawWrapped(heading, in: &ctx,
                    at: CGPoint(x: box.minX + 11, y: box.minY + 10),
                    size: 12, width: box.width - 22, tint: Palette.ink)
        drawWrapped("Interactive visual (\(kind)) — live render is above this layer",
                    in: &ctx, at: CGPoint(x: box.minX + 11, y: box.minY + 30),
                    size: 9, width: box.width - 22, tint: Palette.tertiary)
    }

    func drawChip(_ node: BoardNode, in ctx: inout GraphicsContext) {
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
    func drawWrapped(_ text: String, in ctx: inout GraphicsContext, at: CGPoint, size: CGFloat,
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

    func wrap(_ text: String, width: CGFloat, font: NSFont) -> [String] {
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

    static func weight(_ name: String) -> NSFont.Weight {
        switch name {
        case "medium": return .medium
        case "semibold": return .semibold
        case "bold": return .bold
        default: return .regular
        }
    }
}
