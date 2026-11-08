import SwiftUI
import AppKit

// MARK: - Commands, keyboard, context menu

extension BoardEditor {
    func fitToBoard() {
        viewport.fit(BoardGeometry.bounds(of: board.nodes), in: CGSize(width: 1200, height: 800))
    }

    func align(_ command: AlignCommand) {
        guard selectedNodes.count > 1 else { return }
        board.beginEdit()
        let moved = BoardGeometry.aligned(selectedNodes, by: command)
        board.moveMany(moved.map { (id: $0.id, x: $0.x, y: $0.y, w: $0.w, h: $0.h) })
    }

    func distribute(_ command: DistributeCommand) {
        guard selectedNodes.count > 2 else { return }
        board.beginEdit()
        let moved = BoardGeometry.distributed(selectedNodes, by: command)
        board.moveMany(moved.map { (id: $0.id, x: $0.x, y: $0.y, w: $0.w, h: $0.h) })
    }

    enum Layer { case front, forward, backward, back }

    func stack(_ direction: Layer) {
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

    func deleteSelection() {
        guard !selection.isEmpty else { return }
        board.beginEdit()
        for id in selection.ids { board.delete(id: id) }
        selection.clear()
    }

    func duplicateSelection() {
        guard !selectedNodes.isEmpty else { return }
        board.beginEdit()
        for node in BoardClipboard.paste(at: CGPoint(x: selectionBounds.maxX + 24, y: selectionBounds.minY)) {
            board.add(node: node)
        }
    }

    func copySelection() {
        guard !selectedNodes.isEmpty else { return }
        BoardClipboard.copy(selectedNodes)
        notice = "Copied \(BoardClipboard.count) object(s)"
    }

    func paste() {
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
    func keyPress(_ characters: String, flags: NSEvent.ModifierFlags, in size: CGSize) {
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
