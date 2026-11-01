import SwiftUI
import AppKit
import UniformTypeIdentifiers

// The slide editor: a real 1:1 PPTX surface inside the app.
//
// The complaint this answers is that the deck was a *picture* of a slide you could not touch.
// Here the slide is a document: every heading, bullet, picture and shape is an element with a
// position, a size and a style, and the document round-trips to a real .pptx and back. The
// server owns validity, identity and persistence; this file owns the editing gestures.
//
// Two rules keep it honest:
//   * The canvas is a *view of the document*. Nothing is drawn that is not in the model, so
//     what you see is what the .pptx will contain.
//   * Writes are optimistic but never silent: a local edit is applied immediately, sent, and
//     rolled back with a visible message if the server refuses it.
//
// Coordinates are points on a 960 x 540 canvas, exactly as `backend/app/deck.py` defines them,
// so a value here is the same number the export writes into the .pptx.

private let deckCanvasW: CGFloat = 960
private let deckCanvasH: CGFloat = 540

// MARK: - Document model

/// The run-level style. Every field is optional so a patch can carry only what changed, and
/// so the server's own defaults fill the gaps.
struct DeckStyle: Codable, Equatable {
    var font: String?
    var size: Double?
    var bold: Bool?
    var italic: Bool?
    var underline: Bool?
    var color: String?
    var align: String?
    var anchor: String?
    var lineSpacing: Double?
    var level: Int?
    var fill: String?
    var stroke: String?
    var strokeWidth: Double?
    var radius: Double?
}

struct DeckRun: Codable, Equatable {
    var text: String
    var style: DeckStyle?
}

struct DeckParagraph: Codable, Equatable {
    var runs: [DeckRun]
    var level: Int?
    var align: String?
    var lineSpacing: Double?
    var spaceAfter: Double?

    /// The paragraph's plain text, for a single-run edit or a quick read-back.
    var plain: String { runs.map(\.text).joined() }
}

struct DeckTextBody: Codable, Equatable {
    var paragraphs: [DeckParagraph]
}

struct DeckCrop: Codable, Equatable {
    var l: Double?
    var t: Double?
    var r: Double?
    var b: Double?
}

struct DeckImageRef: Codable, Equatable {
    var sha256: String
    var fit: String?
    var crop: DeckCrop?
    var alt: String?
    var attribution: String?
}

struct DeckTableBody: Codable, Equatable {
    var rows: [[String]]
    var colWidths: [Double]?
}

struct DeckElement: Codable, Equatable, Identifiable {
    var id: String
    var kind: String
    var x: Double
    var y: Double
    var w: Double
    var h: Double
    var rotation: Double?
    var z: Int?
    var style: DeckStyle?
    var text: DeckTextBody?
    var image: DeckImageRef?
    var shape: String?
    var points: [[Double]]?
    var table: DeckTableBody?

    var frame: CGRect { CGRect(x: x, y: y, width: max(w, 1), height: max(h, 1)) }
    var isText: Bool { kind == "text" || kind == "formula" }

    /// A one-line label for the element list and the inspector header.
    var summary: String {
        switch kind {
        case "text", "formula": return text?.paragraphs.first?.plain ?? "Text"
        case "image": return image?.alt?.isEmpty == false ? (image?.alt ?? "Image") : "Image"
        case "shape": return shape ?? "Shape"
        case "table": return "Table (\(table?.rows.count ?? 0) rows)"
        default: return kind
        }
    }
}

struct DeckSlide: Codable, Equatable, Identifiable {
    var id: String
    var layout: String
    var notes: String?
    var background: String?
    var elements: [DeckElement]

    static let layouts = ["title", "section", "idea", "two_column", "figure",
                          "caption", "check", "summary", "blank"]
}

struct DeckTheme: Codable, Equatable {
    var name: String?
    var fonts: [String: String]?
    var colors: [String: String]?
}

struct DeckDoc: Codable, Equatable {
    var id: String
    var title: String
    var theme: DeckTheme?
    var slides: [DeckSlide]
    var version: Int?

    static func decode(_ data: Data) throws -> DeckDoc {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(DeckDoc.self, from: data)
    }

    func jsonObject() -> [String: Any] {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        guard let data = try? encoder.encode(self),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return [:] }
        return object
    }
}

// MARK: - Store

/// The editor's state. It owns the document, the selection, the undo history and the
/// clipboard, and it is the only thing that talks to the deck routes.
@MainActor
final class DeckEditorStore: ObservableObject {
    /// Mutable, because a drag must move an element without waiting for the network. Every
    /// local mutation is followed by a server write, and a refused write rolls the value back.
    @Published var doc: DeckDoc
    @Published var selectedSlideID: String = ""
    /// Selected element ids on the current slide. A Set because multi-select is a Set.
    @Published var selection: Set<String> = []
    @Published var zoom: CGFloat = 0.62
    @Published var busy = false
    @Published var error: String?
    @Published var notice: String?
    /// sha -> decoded bitmap, so a picture is fetched once and drawn from memory after that.
    @Published private(set) var images: [String: NSImage] = [:]

    private let api: APIClient
    private var deckID: String
    private var undoStack: [DeckDoc] = []
    private var redoStack: [DeckDoc] = []
    private var clipboardSlides: [DeckSlide] = []
    private var clipboardElements: [DeckElement] = []

    init(api: APIClient, deckID: String) {
        self.api = api
        self.deckID = deckID
        self.doc = DeckDoc(id: deckID, title: "Loading…", theme: nil, slides: [], version: nil)
    }

    // MARK: derived

    var slides: [DeckSlide] { doc.slides }
    var currentSlide: DeckSlide? { doc.slides.first { $0.id == selectedSlideID } ?? doc.slides.first }
    var currentIndex: Int { doc.slides.firstIndex { $0.id == (currentSlide?.id ?? "") } ?? 0 }
    /// `currentIndex` when it actually addresses a slide. Every mutation goes through this so
    /// an empty deck is a no-op rather than an out-of-range crash.
    var safeIndex: Int? { doc.slides.indices.contains(currentIndex) ? currentIndex : nil }
    var selectedElements: [DeckElement] { (currentSlide?.elements ?? []).filter { selection.contains($0.id) } }
    var singleSelection: DeckElement? { selectedElements.count == 1 ? selectedElements.first : nil }
    var canUndo: Bool { !undoStack.isEmpty }
    var canRedo: Bool { !redoStack.isEmpty }

    // MARK: load / save

    func load() async {
        busy = true
        defer { busy = false }
        do {
            let data = try await resolveDeckData()
            let loaded = try DeckDoc.decode(data)
            doc = loaded
            // Adopt the persisted id so subsequent PUT/PATCH/export hit the right resource.
            // `from-concept` mints a fresh id, and a deck created through it must be saved
            // back to that id, not to the concept id it was composed from.
            if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let id = obj["id"] as? String, !id.isEmpty {
                deckID = id
            }
            if selectedSlideID.isEmpty || !doc.slides.contains(where: { $0.id == selectedSlideID }) {
                selectedSlideID = doc.slides.first?.id ?? ""
            }
            selection = []
            await loadImages()
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// Load an existing editable deck. When nothing is persisted under `deckID` (for example
    /// when it is a concept id with no editable deck yet), compose one from the grounded
    /// curriculum via `from-concept`, which also persists it and returns a real deck id.
    private func resolveDeckData() async throws -> Data {
        do {
            return try await api.data("/deck/\(deckID)")
        } catch {
            return try await api.data("/deck/from-concept/\(deckID)")
        }
    }

    /// Fetch every picture the deck references, once. The bytes come from the same
    /// content-addressed media route the rest of the app uses.
    func loadImages() async {
        // Collected with explicit loops rather than one long chain: the chained form made the
        // type-checker give up, and a picture list is not worth an expression that clever.
        var shas: [String] = []
        for slide in doc.slides {
            for element in slide.elements where element.kind == "image" {
                guard let sha = element.image?.sha256, sha.count == 64 else { continue }
                if !shas.contains(sha) { shas.append(sha) }
            }
        }
        for sha in shas where images[sha] == nil {
            if let data = try? await api.data("/media/images/\(sha)/bytes"),
               let image = NSImage(data: data) {
                images[sha] = image
            }
        }
    }

    private func snapshot() {
        undoStack.append(doc)
        if undoStack.count > 60 { undoStack.removeFirst() }
        redoStack.removeAll()
    }

    private func persist(_ previous: DeckDoc) {
        let payload = doc.jsonObject()
        Task {
            do {
                _ = try await api.data("/deck/\(deckID)", method: "PUT", body: payload)
            } catch {
                self.doc = previous            // a refused write must not leave a phantom edit
                self.error = error.localizedDescription
            }
        }
    }

    func undo() {
        guard let previous = undoStack.popLast() else { return }
        redoStack.append(doc)
        doc = previous
        persist(doc)
    }

    func redo() {
        guard let next = redoStack.popLast() else { return }
        undoStack.append(doc)
        doc = next
        persist(doc)
    }

    // MARK: slides

    func select(slideID: String) {
        selectedSlideID = slideID
        selection = []
    }

    func addSlide(layout: String = "idea") {
        let previous = doc
        snapshot()
        var slide = DeckSlide(id: "tmp-\(UUID().uuidString)", layout: layout, notes: "",
                              background: nil, elements: [])
        slide.elements = []
        doc.slides.append(slide)
        selectedSlideID = slide.id
        persist(previous)
        Task { await reload(keeping: slide.id) }
    }

    func deleteSlide(_ slideID: String) {
        guard doc.slides.count > 1 else { notice = "A deck keeps at least one slide."; return }
        let previous = doc
        snapshot()
        doc.slides.removeAll { $0.id == slideID }
        if selectedSlideID == slideID { selectedSlideID = doc.slides.first?.id ?? "" }
        selection = []
        persist(previous)
        Task { await reload(keeping: selectedSlideID) }
    }

    func duplicateSlide(_ slideID: String) {
        let previous = doc
        snapshot()
        guard let index = doc.slides.firstIndex(where: { $0.id == slideID }) else { return }
        var clone = doc.slides[index]
        clone.id = "tmp-\(UUID().uuidString)"
        clone.elements = clone.elements.map { var e = $0; e.id = "tmp-\(UUID().uuidString)"; return e }
        doc.slides.insert(clone, at: index + 1)
        selectedSlideID = clone.id
        persist(previous)
        Task { await reload(keeping: clone.id) }
    }

    func moveSlide(from: Int, to: Int) {
        guard doc.slides.indices.contains(from), to >= 0, to < doc.slides.count, from != to else { return }
        let previous = doc
        snapshot()
        let slide = doc.slides.remove(at: from)
        doc.slides.insert(slide, at: to)
        persist(previous)
        Task { await reload(keeping: slide.id) }
    }

    func patchSlide(_ patch: [String: Any]) {
        guard let slide = currentSlide else { return }
        let previous = doc
        snapshot()
        applySlidePatch(patch, to: slide.id)
        persist(previous)
        Task {
            do { _ = try await api.data("/deck/\(deckID)/slides/\(slide.id)", method: "PATCH", body: patch) }
            catch { self.doc = previous; self.error = error.localizedDescription }
        }
    }

    private func applySlidePatch(_ patch: [String: Any], to slideID: String) {
        guard let index = doc.slides.firstIndex(where: { $0.id == slideID }) else { return }
        if let layout = patch["layout"] as? String { doc.slides[index].layout = layout }
        if let notes = patch["notes"] as? String { doc.slides[index].notes = notes }
        if let background = patch["background"] as? String { doc.slides[index].background = background }
    }

    // MARK: elements

    func addElement(_ element: DeckElement) {
        guard let slide = currentSlide else { return }
        let previous = doc
        snapshot()
        var placed = element
        placed.z = (slide.elements.map { $0.z ?? 0 }.max() ?? -1) + 1
        guard let index = safeIndex else { return }
        doc.slides[index].elements.append(placed)
        selection = [placed.id]
        persist(previous)
        Task { await reload(keeping: slide.id, selecting: placed.summary) }
    }

    /// Move or resize: applied locally every frame, sent once when the gesture ends. Sending
    /// per frame would be a request per pixel of drag.
    func commitGeometry(_ elementID: String, x: Double, y: Double, w: Double, h: Double) {
        guard let index = safeIndex,
              let elementIndex = doc.slides[index].elements.firstIndex(where: { $0.id == elementID })
        else { return }
        let previous = doc
        snapshot()
        doc.slides[index].elements[elementIndex].x = x
        doc.slides[index].elements[elementIndex].y = y
        doc.slides[index].elements[elementIndex].w = max(w, 8)
        doc.slides[index].elements[elementIndex].h = max(h, 8)
        persist(previous)
        let body: [String: Any] = ["x": x, "y": y, "w": max(w, 8), "h": max(h, 8)]
        Task {
            do { _ = try await api.data("/deck/\(deckID)/elements/\(elementID)", method: "PATCH", body: body) }
            catch { self.doc = previous; self.error = error.localizedDescription }
        }
    }

    func patchElement(_ elementID: String, _ patch: [String: Any], snapshotForUndo: Bool = true) {
        let previous = doc
        if snapshotForUndo { snapshot() }
        guard let index = safeIndex,
              let elementIndex = doc.slides[index].elements.firstIndex(where: { $0.id == elementID })
        else { return }
        if let text = patch["text"] as? [String: Any],
           let paragraphs = text["paragraphs"] as? [[String: Any]] {
            doc.slides[index].elements[elementIndex].text = DeckEditorStore.textBody(paragraphs)
        }
        if let style = patch["style"] as? [String: Any] {
            doc.slides[index].elements[elementIndex].style = DeckEditorStore.merge(
                doc.slides[index].elements[elementIndex].style, style)
        }
        if let image = patch["image"] as? [String: Any] {
            if let fit = image["fit"] as? String { doc.slides[index].elements[elementIndex].image?.fit = fit }
            if let alt = image["alt"] as? String { doc.slides[index].elements[elementIndex].image?.alt = alt }
        }
        persist(previous)
        Task {
            do { _ = try await api.data("/deck/\(deckID)/elements/\(elementID)", method: "PATCH", body: patch) }
            catch { self.doc = previous; self.error = error.localizedDescription }
        }
    }

    func deleteSelection() {
        guard !selection.isEmpty, let slide = currentSlide, let index = safeIndex else { return }
        let previous = doc
        snapshot()
        doc.slides[index].elements.removeAll { selection.contains($0.id) }
        let removed = selection
        selection = []
        persist(previous)
        Task {
            for id in removed where !id.hasPrefix("tmp-") {
                _ = try? await api.data("/deck/\(deckID)/elements/\(id)", method: "DELETE")
            }
            await reload(keeping: slide.id)
        }
    }

    func nudge(dx: Double, dy: Double) {
        for element in selectedElements {
            commitGeometry(element.id, x: element.x + dx, y: element.y + dy, w: element.w, h: element.h)
        }
    }

    // MARK: z-order

    func bringForward(_ elementID: String) { reorder(elementID, delta: 1) }
    func sendBackward(_ elementID: String) { reorder(elementID, delta: -1) }

    private func reorder(_ elementID: String, delta: Int) {
        guard let index = safeIndex,
              let elementIndex = doc.slides[index].elements.firstIndex(where: { $0.id == elementID })
        else { return }
        let previous = doc
        snapshot()
        let sorted = doc.slides[index].elements.enumerated()
            .sorted { ($0.element.z ?? 0) < ($1.element.z ?? 0) }.map(\.offset)
        guard let position = sorted.firstIndex(of: elementIndex) else { return }
        let target = min(max(position + delta, 0), sorted.count - 1)
        var order = sorted
        order.swapAt(position, target)
        for (z, originalIndex) in order.enumerated() {
            doc.slides[index].elements[originalIndex].z = z
        }
        persist(previous)
    }

    // MARK: alignment

    /// Align every selected element inside the slide (or inside the selection's own bounds
    /// when there are several). This is what the align buttons call.
    func align(_ mode: String) {
        let targets = selectedElements
        guard targets.count > 0 else { return }
        let previous = doc
        snapshot()
        let bounds = targets.dropFirst().reduce(targets[0].frame) { $0.union($1.frame) }
        guard let index = safeIndex else { return }
        for element in targets {
            guard let elementIndex = doc.slides[index].elements.firstIndex(where: { $0.id == element.id }) else { continue }
            var frame = element.frame
            switch mode {
            case "left": frame.origin.x = bounds.minX
            case "right": frame.origin.x = bounds.maxX - frame.width
            case "centerX": frame.origin.x = bounds.midX - frame.width / 2
            case "top": frame.origin.y = bounds.minY
            case "bottom": frame.origin.y = bounds.maxY - frame.height
            case "middle": frame.origin.y = bounds.midY - frame.height / 2
            default: break
            }
            doc.slides[index].elements[elementIndex].x = Double(frame.origin.x)
            doc.slides[index].elements[elementIndex].y = Double(frame.origin.y)
        }
        persist(previous)
    }

    /// Space the selected elements evenly between the two outermost, along one axis.
    func distribute(_ axis: String) {
        let targets = selectedElements.sorted {
            axis == "h" ? $0.x < $1.x : $0.y < $1.y
        }
        guard targets.count >= 3, let index = safeIndex else { return }
        let previous = doc
        snapshot()
        let first = axis == "h" ? targets.first!.x : targets.first!.y
        let last = axis == "h" ? targets.last!.x : targets.last!.y
        let step = (last - first) / Double(targets.count - 1)
        for (position, element) in targets.enumerated() {
            guard let elementIndex = doc.slides[index].elements.firstIndex(where: { $0.id == element.id }) else { continue }
            let value = first + step * Double(position)
            if axis == "h" { doc.slides[index].elements[elementIndex].x = value }
            else { doc.slides[index].elements[elementIndex].y = value }
        }
        persist(previous)
    }

    // MARK: clipboard

    func copyElements() {
        guard !selection.isEmpty else { return }
        clipboardElements = selectedElements
        clipboardSlides = []
        notice = "\(clipboardElements.count) element(s) copied."
    }

    func copySlide() {
        guard let slide = currentSlide else { return }
        clipboardSlides = [slide]
        clipboardElements = []
        notice = "Slide copied."
    }

    func paste() {
        if !clipboardElements.isEmpty {
            guard let slide = currentSlide, let index = safeIndex else { return }
            let previous = doc
            snapshot()
            let offset = 24.0
            var pasted: [DeckElement] = []
            var nextZ = (slide.elements.map { $0.z ?? 0 }.max() ?? -1) + 1
            for var element in clipboardElements {
                element.id = "tmp-\(UUID().uuidString)"
                element.x += offset
                element.y += offset
                element.z = nextZ
                nextZ += 1
                pasted.append(element)
            }
            doc.slides[index].elements.append(contentsOf: pasted)
            selection = Set(pasted.map(\.id))
            persist(previous)
            Task { await reload(keeping: slide.id) }
        } else if let slide = clipboardSlides.first {
            let previous = doc
            snapshot()
            var clone = slide
            clone.id = "tmp-\(UUID().uuidString)"
            clone.elements = clone.elements.map { var e = $0; e.id = "tmp-\(UUID().uuidString)"; return e }
            let insertAt = min(currentIndex + 1, doc.slides.count)
            doc.slides.insert(clone, at: insertAt)
            selectedSlideID = clone.id
            persist(previous)
            Task { await reload(keeping: clone.id) }
        }
    }

    func duplicateSelection() {
        guard !selection.isEmpty else { duplicateSlide(currentSlide?.id ?? ""); return }
        copyElements()
        paste()
    }

    // MARK: reconcile

    /// Re-read the document and re-point the selection at a slide. The server assigns ids, so
    /// a locally-created slide or element is only addressable after this.
    private func reload(keeping slideID: String, selecting summary: String? = nil) async {
        do {
            let data = try await api.data("/deck/\(deckID)")
            let loaded = try DeckDoc.decode(data)
            doc = loaded
            if doc.slides.contains(where: { $0.id == slideID }) {
                selectedSlideID = slideID
            } else if let index = doc.slides.indices.first, doc.slides.indices.contains(min(currentIndex, doc.slides.count - 1)) {
                selectedSlideID = doc.slides[min(index, doc.slides.count - 1)].id
            }
            if let summary,
               let match = doc.slides.first(where: { $0.id == selectedSlideID })?.elements.first(where: { $0.summary == summary }) {
                selection = [match.id]
            }
            await loadImages()
        } catch {
            self.error = error.localizedDescription
        }
    }

    // MARK: export / import

    func exportPptx() {
        Task {
            do {
                let data = try await api.data("/deck/\(deckID)/export.pptx")
                let panel = NSSavePanel()
                panel.nameFieldStringValue = "\(doc.title.isEmpty ? "deck" : doc.title).pptx"
                panel.allowedContentTypes = [UTType(filenameExtension: "pptx") ?? .data]
                guard panel.runModal() == .OK, let url = panel.url else { return }
                try data.write(to: url, options: .atomic)
                notice = "Exported \(url.lastPathComponent) (\(data.count) bytes)."
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    func importPptx() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [UTType(filenameExtension: "pptx") ?? .data]
        panel.allowsMultipleSelection = false
        panel.title = "Import a PowerPoint deck"
        guard panel.runModal() == .OK, let url = panel.url,
              let data = try? Data(contentsOf: url) else { return }
        Task {
            do {
                let body: [String: Any] = ["title": url.deletingPathExtension().lastPathComponent,
                                           "data_base64": data.base64EncodedString()]
                let result = try await api.json("/deck/import", method: "POST", body: body)
                let newID = result["id"].string
                if newID.isEmpty {
                    // The refusal is structured ({ok:false, reason:...}); surface the reason.
                    notice = result.text("reason", fallback: "The deck could not be imported.")
                    return
                }
                let loaded = try DeckDoc.decode(try JSONEncoder().encode(result))
                doc = loaded
                selectedSlideID = loaded.slides.first?.id ?? ""
                selection = []
                await loadImages()
                notice = "Imported \(loaded.slides.count) slide(s)."
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    /// Insert a local image: the bytes are uploaded to the content-addressed store, and the
    /// returned sha becomes a normal image element, so it embeds in the .pptx like any other.
    func insertImage(from url: URL, on slideID: String) {
        guard let data = try? Data(contentsOf: url) else { return }
        Task {
            do {
                let body: [String: Any] = ["data_base64": data.base64EncodedString(),
                                           "title": url.lastPathComponent]
                let result = try await api.json("/deck/\(deckID)/images", method: "POST", body: body)
                let sha = result["sha256"].string
                guard sha.count == 64 else { notice = "That file is not an image the server accepts."; return }
                var element = DeckElement(id: "tmp-\(UUID().uuidString)", kind: "image",
                                          x: 300, y: 150, w: 360, h: 240, rotation: 0, z: 0,
                                          style: nil, text: nil,
                                          image: DeckImageRef(sha256: sha, fit: "contain", crop: nil,
                                                              alt: url.deletingPathExtension().lastPathComponent,
                                                              attribution: nil),
                                          shape: nil, points: nil, table: nil)
                element.x = 300
                addElement(element)
                await loadImages()
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    // MARK: static helpers

    static func textBody(_ paragraphs: [[String: Any]]) -> DeckTextBody {
        let parsed: [DeckParagraph] = paragraphs.map { para in
            let runs = (para["runs"] as? [[String: Any]] ?? []).map { run in
                DeckRun(text: run["text"] as? String ?? "",
                        style: style(from: run["style"] as? [String: Any]))
            }
            return DeckParagraph(runs: runs.isEmpty ? [DeckRun(text: "", style: nil)] : runs,
                                 level: para["level"] as? Int,
                                 align: para["align"] as? String,
                                 lineSpacing: para["line_spacing"] as? Double,
                                 spaceAfter: nil)
        }
        return DeckTextBody(paragraphs: parsed.isEmpty ? [DeckParagraph(runs: [DeckRun(text: "", style: nil)], level: 0, align: nil, lineSpacing: nil, spaceAfter: nil)] : parsed)
    }

    static func style(from dict: [String: Any]?) -> DeckStyle? {
        guard let dict else { return nil }
        var style = DeckStyle()
        style.font = dict["font"] as? String
        style.size = dict["size"] as? Double
        style.bold = dict["bold"] as? Bool
        style.italic = dict["italic"] as? Bool
        style.underline = dict["underline"] as? Bool
        style.color = dict["color"] as? String
        style.align = dict["align"] as? String
        style.anchor = dict["anchor"] as? String
        style.lineSpacing = dict["line_spacing"] as? Double
        style.level = dict["level"] as? Int
        return style
    }

    static func merge(_ base: DeckStyle?, _ patch: [String: Any]) -> DeckStyle {
        var merged = base ?? DeckStyle()
        if let value = patch["font"] as? String { merged.font = value }
        if let value = patch["size"] as? Double { merged.size = value }
        if let value = patch["bold"] as? Bool { merged.bold = value }
        if let value = patch["italic"] as? Bool { merged.italic = value }
        if let value = patch["underline"] as? Bool { merged.underline = value }
        if let value = patch["color"] as? String { merged.color = value }
        if let value = patch["align"] as? String { merged.align = value }
        if let value = patch["anchor"] as? String { merged.anchor = value }
        if let value = patch["line_spacing"] as? Double { merged.lineSpacing = value }
        if let value = patch["level"] as? Int { merged.level = value }
        if let value = patch["fill"] as? String { merged.fill = value }
        if let value = patch["stroke"] as? String { merged.stroke = value }
        if let value = patch["stroke_width"] as? Double { merged.strokeWidth = value }
        if let value = patch["radius"] as? Double { merged.radius = value }
        return merged
    }
}

// MARK: - View

struct DeckEditorView: View {
    let deckID: String
    let store: AppStore
    @StateObject private var editor: DeckEditorStore
    @FocusState private var focus: Field?

    /// Which field currently holds the keyboard. Shortcut actions consult this so ⌘C never
    /// fires while a text field is being typed into.
    private enum Field: Hashable { case notes, inspector, runText }

    init(deckID: String, store: AppStore) {
        self.deckID = deckID
        self.store = store
        _editor = StateObject(wrappedValue: DeckEditorStore(api: store.api, deckID: deckID))
    }

    var body: some View {
        VStack(spacing: 0) {
            toolbar
            Divider()
            HStack(spacing: 0) {
                slideRail.frame(width: 208)
                Divider()
                canvas
                Divider()
                inspector.frame(width: 288)
            }
            Divider()
            notesPane
        }
        .background(Palette.background)
        .task { await editor.load() }
        .overlay(alignment: .top) { banner }
        .background(shortcuts)
    }

    // MARK: toolbar

    private var toolbar: some View {
        HStack(spacing: 10) {
            Eyebrow(text: "SLIDE EDITOR")
            Text(editor.doc.title.isEmpty ? "Deck" : editor.doc.title)
                .font(.system(size: 13, weight: .semibold))
                .lineLimit(1)
            if let version = editor.doc.version {
                Tag(text: "v\(version)", color: Palette.sage)
            }
            Spacer()
            Button("Undo") { editor.undo() }.buttonStyle(LuminfestButtonStyle(primary: false, compact: true)).disabled(!editor.canUndo)
            Button("Redo") { editor.redo() }.buttonStyle(LuminfestButtonStyle(primary: false, compact: true)).disabled(!editor.canRedo)
            Divider().frame(height: 18)
            Button { editor.importPptx() } label: { Label("Import .pptx", systemImage: "square.and.arrow.down") }
                .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
            Button { editor.exportPptx() } label: { Label("Export .pptx", systemImage: "square.and.arrow.up") }
                .buttonStyle(LuminfestButtonStyle(compact: true))
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .background(Palette.surface)
    }

    private var banner: some View {
        Group {
            if let error = editor.error {
                bannerRow(error, tint: Palette.terracotta) { editor.error = nil }
            } else if let notice = editor.notice {
                bannerRow(notice, tint: Palette.forest) { editor.notice = nil }
            } else if editor.busy {
                bannerRow("Working…", tint: Palette.slate, dismiss: nil)
            }
        }
    }

    private func bannerRow(_ text: String, tint: Color, dismiss: (() -> Void)?) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "info.circle").foregroundStyle(tint)
            Text(text).font(.system(size: 12))
            Spacer()
            if let dismiss { Button("Dismiss") { dismiss() }.buttonStyle(LuminfestButtonStyle(primary: false, compact: true)) }
        }
        .padding(.horizontal, 16).padding(.vertical, 8)
        .background(tint.opacity(0.12))
        .overlay(Rectangle().frame(height: 1).foregroundStyle(tint.opacity(0.3)), alignment: .bottom)
    }

    // MARK: slide rail

    private var slideRail: some View {
        VStack(spacing: 0) {
            HStack {
                Eyebrow(text: "SLIDES")
                Spacer()
                Menu {
                    ForEach(DeckSlide.layouts, id: \.self) { layout in
                        Button(layout.capitalized) { editor.addSlide(layout: layout) }
                    }
                } label: { Image(systemName: "plus") }
                    .menuStyle(.borderlessButton).frame(width: 24)
            }
            .padding(.horizontal, 12).padding(.vertical, 8)

            ScrollView {
                LazyVStack(spacing: 8) {
                    ForEach(Array(editor.slides.enumerated()), id: \.element.id) { index, slide in
                        railRow(index: index, slide: slide)
                    }
                }
                .padding(10)
            }
        }
        .background(Palette.surfaceSubtle)
    }

    private func railRow(index: Int, slide: DeckSlide) -> some View {
        let selected = slide.id == (editor.currentSlide?.id ?? "")
        return VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                Text("\(index + 1)").font(.system(size: 10, weight: .bold)).foregroundStyle(Palette.secondary)
                Text(slide.layout).font(.system(size: 10)).foregroundStyle(Palette.tertiary)
                Spacer()
                if !(slide.notes ?? "").isEmpty { Image(systemName: "text.bubble").font(.system(size: 9)).foregroundStyle(Palette.tertiary) }
            }
            ZStack(alignment: .topLeading) {
                RoundedRectangle(cornerRadius: 6).fill(Color.white)
                ForEach(slide.elements) { element in
                    miniElement(element)
                }
            }
            .frame(width: 168, height: 94)
            .overlay(RoundedRectangle(cornerRadius: 6)
                .strokeBorder(selected ? Palette.forest : Palette.line, lineWidth: selected ? 2 : 1))
        }
        .contentShape(Rectangle())
        .onTapGesture { editor.select(slideID: slide.id) }
        .contextMenu {
            Button("Duplicate") { editor.duplicateSlide(slide.id) }
            Button("Move up") { editor.moveSlide(from: index, to: max(0, index - 1)) }
            Button("Move down") { editor.moveSlide(from: index, to: min(editor.slides.count - 1, index + 1)) }
            Divider()
            Button("Delete", role: .destructive) { editor.deleteSlide(slide.id) }
        }
    }

    /// A slide thumbnail, drawn from the document model at rail scale. Same elements, same
    /// geometry — a smaller view of the real slide, not a second representation of it.
    private func miniElement(_ element: DeckElement) -> some View {
        let scale = 168.0 / deckCanvasW
        return Group {
            if element.kind == "image", let sha = element.image?.sha256, let image = editor.images[sha] {
                Image(nsImage: image).resizable().scaledToFill()
            } else if element.isText {
                Text(element.text?.paragraphs.first?.plain.prefix(24) ?? "")
                    .font(.system(size: max(3, CGFloat(element.style?.size ?? 18) * scale * 0.9)))
                    .foregroundStyle(Color(hexString: element.style?.color ?? "#24312A"))
                    .lineLimit(2)
            } else if element.kind == "shape" {
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color(hexString: element.style?.fill ?? "#ECEDDF"))
            } else {
                RoundedRectangle(cornerRadius: 2).fill(Palette.muted)
            }
        }
        .frame(width: max(2, CGFloat(element.w) * scale), height: max(2, CGFloat(element.h) * scale))
        .offset(x: CGFloat(element.x) * scale, y: CGFloat(element.y) * scale)
    }

    // MARK: canvas

    private var canvas: some View {
        ScrollView([.horizontal, .vertical]) {
            ZStack(alignment: .topLeading) {
                Color(hexString: editor.currentSlide?.background ?? "#FFFFFF")
                elementLayer
                if let marquee {
                    Rectangle().fill(Palette.forest.opacity(0.10))
                        .overlay(Rectangle().strokeBorder(Palette.forest, lineWidth: 1))
                        .frame(width: marquee.width, height: marquee.height)
                        .position(x: marquee.midX, y: marquee.midY)
                }
                selectionChrome
            }
            .frame(width: deckCanvasW, height: deckCanvasH)
            // The marquee gesture is attached to the *unscaled* canvas so its coordinates are
            // the document's own points, the same numbers an element's frame uses.
            .contentShape(Rectangle())
            .gesture(marqueeGesture())
            .scaleEffect(editor.zoom, anchor: .topLeading)
            .frame(width: deckCanvasW * editor.zoom, height: deckCanvasH * editor.zoom)
            .shadow(color: Palette.ink.opacity(0.12), radius: 10, y: 4)
            .padding(24)
        }
        .background(Palette.background)
        .overlay(alignment: .bottomLeading) { zoomControls }
    }

    private var elementLayer: some View {
        ForEach((editor.currentSlide?.elements ?? []).sorted { ($0.z ?? 0) < ($1.z ?? 0) }) { element in
            elementView(element)
        }
    }

    @ViewBuilder
    private func elementView(_ element: DeckElement) -> some View {
        let selected = editor.selection.contains(element.id)
        ZStack {
            switch element.kind {
            case "image": imageView(element)
            case "shape": shapeView(element)
            case "table": tableView(element)
            default: textView(element)
            }
        }
        .frame(width: element.frame.width, height: element.frame.height)
        .rotationEffect(.degrees(element.rotation ?? 0))
        .overlay(RoundedRectangle(cornerRadius: 3)
            .strokeBorder(selected ? Palette.forest : Color.clear, lineWidth: selected ? 1.5 : 0))
        .position(x: element.frame.midX, y: element.frame.midY)
        .gesture(dragGesture(element))
        .onTapGesture { handleTap(element) }
    }

    private func textView(_ element: DeckElement) -> some View {
        let base = element.style
        return VStack(alignment: alignment(base?.align), spacing: 2) {
            ForEach(Array((element.text?.paragraphs ?? []).enumerated()), id: \.offset) { _, para in
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    if (para.level ?? 0) > 0 {
                        Text("•").font(.system(size: CGFloat(base?.size ?? 18))).foregroundStyle(Palette.secondary)
                    }
                    paragraphText(para, base: base)
                    Spacer(minLength: 0)
                }
                .padding(.leading, CGFloat(para.level ?? 0) * 18)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: alignmentFor(base?.anchor))
        .clipped()
    }

    /// Runs are concatenated as `Text` values so each run keeps its own font, size, colour and
    /// emphasis — this is the on-screen half of "font and text management is real".
    private func paragraphText(_ para: DeckParagraph, base: DeckStyle?) -> Text {
        var combined = Text("")
        for run in para.runs {
            let style = run.style ?? base
            var piece = Text(run.text)
                .font(.custom(style?.font ?? "Helvetica Neue", size: CGFloat(style?.size ?? 18)))
                .foregroundColor(Color(hexString: style?.color ?? base?.color ?? "#24312A"))
            if style?.bold == true { piece = piece.bold() }
            if style?.italic == true { piece = piece.italic() }
            if style?.underline == true { piece = piece.underline() }
            combined = combined + piece
        }
        return combined
    }

    private func alignment(_ value: String?) -> HorizontalAlignment {
        switch value { case "center": return .center; case "right": return .trailing; default: return .leading }
    }

    private func alignmentFor(_ anchor: String?) -> Alignment {
        switch anchor {
        case "middle": return .leading
        case "bottom": return .bottomLeading
        default: return .topLeading
        }
    }

    private func imageView(_ element: DeckElement) -> some View {
        Group {
            if let sha = element.image?.sha256, let image = editor.images[sha] {
                Image(nsImage: image).resizable()
                    .aspectRatio(contentMode: (element.image?.fit == "stretch") ? .fill : .fit)
            } else {
                ZStack {
                    Rectangle().fill(Palette.muted)
                    VStack(spacing: 4) {
                        Image(systemName: "photo").foregroundStyle(Palette.tertiary)
                        Text(element.image?.alt ?? "Image unavailable")
                            .font(.system(size: 10)).foregroundStyle(Palette.secondary)
                    }
                }
            }
        }
    }

    private func shapeView(_ element: DeckElement) -> some View {
        let fill = Color(hexString: element.style?.fill ?? "#ECEDDF")
        let stroke = Color(hexString: element.style?.stroke ?? "#DFE2D6")
        let width = CGFloat(element.style?.strokeWidth ?? 1)
        return Group {
            switch element.shape {
            case "ellipse": Ellipse().fill(fill).overlay(Ellipse().stroke(stroke, lineWidth: width))
            case "roundRect": RoundedRectangle(cornerRadius: CGFloat(element.style?.radius ?? 12)).fill(fill).overlay(RoundedRectangle(cornerRadius: CGFloat(element.style?.radius ?? 12)).stroke(stroke, lineWidth: width))
            case "triangle": Triangle().fill(fill).overlay(Triangle().stroke(stroke, lineWidth: width))
            case "line", "arrow": Path { path in
                path.move(to: .zero)
                path.addLine(to: CGPoint(x: element.w, y: element.h))
            }.stroke(stroke, lineWidth: max(width, 1))
            case "polyline": Path { path in
                guard let first = element.points?.first else { return }
                path.move(to: CGPoint(x: first[0] - element.x, y: first[1] - element.y))
                for point in (element.points ?? []).dropFirst() {
                    path.addLine(to: CGPoint(x: point[0] - element.x, y: point[1] - element.y))
                }
            }.stroke(stroke, lineWidth: max(width, 1))
            default: Rectangle().fill(fill).overlay(Rectangle().stroke(stroke, lineWidth: width))
            }
        }
    }

    private func tableView(_ element: DeckElement) -> some View {
        let rows = element.table?.rows ?? []
        return VStack(spacing: 0) {
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                HStack(spacing: 0) {
                    ForEach(Array(row.enumerated()), id: \.offset) { _, cell in
                        Text(cell).font(.system(size: 12)).frame(maxWidth: .infinity, alignment: .leading)
                            .padding(4)
                    }
                }
                .frame(maxHeight: .infinity)
                .overlay(Rectangle().stroke(Palette.line, lineWidth: 0.5))
            }
        }
        .frame(width: element.w, height: element.h)
        .overlay(Rectangle().stroke(Palette.line))
        .background(Color.white.opacity(0.6))
    }

    // MARK: gestures

    private func dragGesture(_ element: DeckElement) -> some Gesture {
        DragGesture(minimumDistance: 1)
            .onChanged { value in
                // Move locally for a live feel; the network write happens on release.
                guard let index = editor.safeIndex,
                      let elementIndex = editor.doc.slides[index].elements.firstIndex(where: { $0.id == element.id })
                else { return }
                if !editor.selection.contains(element.id) { editor.selection = [element.id] }
                editor.doc.slides[index].elements[elementIndex].x = element.x + Double(value.translation.width)
                editor.doc.slides[index].elements[elementIndex].y = element.y + Double(value.translation.height)
            }
            .onEnded { value in
                editor.commitGeometry(element.id, x: element.x + Double(value.translation.width),
                                      y: element.y + Double(value.translation.height),
                                      w: element.w, h: element.h)
            }
    }

    private func handleDrag(_ element: DeckElement, corner: HandleCorner) -> some Gesture {
        DragGesture(minimumDistance: 1)
            .onEnded { value in
                var frame = element.frame
                let dx = value.translation.width, dy = value.translation.height
                if corner.touchesLeft { frame.origin.x += dx; frame.size.width -= dx }
                if corner.touchesRight { frame.size.width += dx }
                if corner.touchesTop { frame.origin.y += dy; frame.size.height -= dy }
                if corner.touchesBottom { frame.size.height += dy }
                editor.commitGeometry(element.id, x: Double(frame.origin.x), y: Double(frame.origin.y),
                                      w: Double(max(frame.width, 8)), h: Double(max(frame.height, 8)))
            }
    }

    private func handleTap(_ element: DeckElement) {
        if NSEvent.modifierFlags.contains(.shift) {
            if editor.selection.contains(element.id) { editor.selection.remove(element.id) }
            else { editor.selection.insert(element.id) }
        } else {
            editor.selection = [element.id]
        }
    }

    private var selectionChrome: some View {
        Group {
            if let element = editor.singleSelection {
                ForEach(HandleCorner.allCases, id: \.self) { corner in
                    let point = corner.point(in: element.frame)
                    Circle().fill(Palette.surface)
                        .frame(width: 9, height: 9)
                        .overlay(Circle().stroke(Palette.forest, lineWidth: 1.5))
                        .position(x: point.x, y: point.y)
                        .gesture(handleDrag(element, corner: corner))
                }
            }
        }
    }

    private func marqueeGesture() -> some Gesture {
        DragGesture(minimumDistance: 6)
            .onChanged { value in
                let rect = CGRect(x: min(value.startLocation.x, value.location.x),
                                  y: min(value.startLocation.y, value.location.y),
                                  width: abs(value.location.x - value.startLocation.x),
                                  height: abs(value.location.y - value.startLocation.y))
                marquee = rect
            }
            .onEnded { value in
                let rect = CGRect(x: min(value.startLocation.x, value.location.x),
                                  y: min(value.startLocation.y, value.location.y),
                                  width: abs(value.location.x - value.startLocation.x),
                                  height: abs(value.location.y - value.startLocation.y))
                marquee = nil
                guard rect.width > 4, rect.height > 4, let slide = editor.currentSlide else { return }
                let hits = slide.elements.filter { $0.frame.intersects(rect) }.map(\.id)
                if NSEvent.modifierFlags.contains(.shift) { editor.selection.formUnion(hits) }
                else { editor.selection = Set(hits) }
            }
    }

    @State private var marquee: CGRect?

    private var zoomControls: some View {
        HStack(spacing: 8) {
            Button { editor.zoom = max(0.25, editor.zoom - 0.1) } label: { Image(systemName: "minus.magnifyingglass") }
            Text("\(Int(editor.zoom * 100))%").font(.system(size: 11, weight: .medium)).frame(width: 40)
            Button { editor.zoom = min(2.0, editor.zoom + 0.1) } label: { Image(systemName: "plus.magnifyingglass") }
        }
        .buttonStyle(.plain)
        .padding(8)
        .background(.regularMaterial, in: Capsule())
        .padding(14)
    }

    // MARK: inspector

    private var inspector: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                SectionHeading(title: "Inspector", detail: editor.selection.isEmpty ? "slide" : "\(editor.selection.count) selected")
                slideSection
                if !editor.selection.isEmpty { elementSection }
                if editor.selection.count > 1 { arrangeSection }
            }
            .padding(14)
        }
        .background(Palette.surface)
    }

    private var slideSection: some View {
        Card(padding: 14, interactive: false) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Slide").font(.system(size: 12, weight: .semibold))
                Picker("Layout", selection: Binding(
                    get: { editor.currentSlide?.layout ?? "blank" },
                    set: { editor.patchSlide(["layout": $0]) })) {
                    ForEach(DeckSlide.layouts, id: \.self) { Text($0.capitalized).tag($0) }
                }
                .labelsHidden()
                HStack {
                    Text("Background").font(.system(size: 11)).foregroundStyle(Palette.secondary)
                    Spacer()
                    ColorPicker("", selection: Binding(
                        get: { Color(hexString: editor.currentSlide?.background ?? "#FFFFFF") },
                        set: { editor.patchSlide(["background": $0.deckHex]) }),
                        supportsOpacity: false).labelsHidden().frame(width: 36)
                }
            }
        }
    }

    private var elementSection: some View {
        Card(padding: 14, interactive: false) {
            VStack(alignment: .leading, spacing: 10) {
                Text("Element").font(.system(size: 12, weight: .semibold))
                Text(editor.singleSelection?.summary ?? "\(editor.selection.count) elements")
                    .font(.system(size: 11)).foregroundStyle(Palette.secondary).lineLimit(2)

                if let element = editor.singleSelection {
                    if element.isText { textInspector(element) }
                    if element.kind == "image" { imageInspector(element) }
                    if element.kind == "shape" { shapeInspector(element) }
                    HStack(spacing: 6) {
                        Button("Forward") { editor.bringForward(element.id) }.buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
                        Button("Back") { editor.sendBackward(element.id) }.buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
                    }
                }
                Button("Delete", role: .destructive) { editor.deleteSelection() }
                    .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
            }
        }
    }

    private func textInspector(_ element: DeckElement) -> some View {
        let base = element.style ?? DeckStyle()
        return VStack(alignment: .leading, spacing: 8) {
            // Font family: the real macOS font list, so what you pick is what is installed.
            Picker("Font", selection: Binding(
                get: { base.font ?? "Helvetica Neue" },
                set: { value in editor.patchElement(element.id, ["style": ["font": value]]) })) {
                ForEach(NSFontManager.shared.availableFontFamilies, id: \.self) { Text($0).tag($0) }
            }
            .labelsHidden()

            HStack(spacing: 6) {
                Text("Size").font(.system(size: 11)).foregroundStyle(Palette.secondary)
                Stepper(value: Binding(
                    get: { Int(base.size ?? 18) },
                    set: { value in editor.patchElement(element.id, ["style": ["size": Double(value)]]) }),
                    in: 8...200) { Text("\(Int(base.size ?? 18)) pt").font(.system(size: 11)) }
            }

            HStack(spacing: 6) {
                styleToggle("B", active: base.bold == true) { editor.patchElement(element.id, ["style": ["bold": !(base.bold ?? false)]]) }
                styleToggle("I", active: base.italic == true) { editor.patchElement(element.id, ["style": ["italic": !(base.italic ?? false)]]) }
                styleToggle("U", active: base.underline == true) { editor.patchElement(element.id, ["style": ["underline": !(base.underline ?? false)]]) }
                Spacer()
                ColorPicker("", selection: Binding(
                    get: { Color(hexString: base.color ?? "#24312A") },
                    set: { editor.patchElement(element.id, ["style": ["color": $0.deckHex]]) }),
                    supportsOpacity: false).labelsHidden().frame(width: 36)
            }

            Picker("Align", selection: Binding(
                get: { base.align ?? "left" },
                set: { editor.patchElement(element.id, ["style": ["align": $0]]) })) {
                Text("Left").tag("left"); Text("Centre").tag("center")
                Text("Right").tag("right"); Text("Justify").tag("justify")
            }
            .pickerStyle(.segmented)

            HStack {
                Text("Line spacing").font(.system(size: 11)).foregroundStyle(Palette.secondary)
                Slider(value: Binding(
                    get: { base.lineSpacing ?? 1.0 },
                    set: { editor.patchElement(element.id, ["style": ["line_spacing": $0]]) }), in: 0.8...2.5)
            }

            ForEach(Array((element.text?.paragraphs ?? []).enumerated()), id: \.offset) { pIndex, para in
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text("Paragraph \(pIndex + 1)").font(.system(size: 10, weight: .semibold)).foregroundStyle(Palette.secondary)
                        Spacer()
                        Picker("Level", selection: Binding(
                            get: { para.level ?? 0 },
                            set: { setParagraphLevel(element, pIndex, $0) })) {
                            ForEach(0...4, id: \.self) { Text("L\($0)").tag($0) }
                        }.labelsHidden().frame(width: 70)
                    }
                    ForEach(Array(para.runs.enumerated()), id: \.offset) { rIndex, run in
                        HStack(spacing: 4) {
                            TextField("run", text: Binding(
                                get: { run.text },
                                set: { setRunText(element, pIndex, rIndex, $0) }))
                                .textFieldStyle(.roundedBorder)
                                .font(.system(size: 11))
                                .focused($focus, equals: .runText)
                        }
                    }
                }
            }
        }
    }

    private func setRunText(_ element: DeckElement, _ pIndex: Int, _ rIndex: Int, _ value: String) {
        guard var body = element.text, body.paragraphs.indices.contains(pIndex),
              body.paragraphs[pIndex].runs.indices.contains(rIndex) else { return }
        body.paragraphs[pIndex].runs[rIndex].text = value
        editor.patchElement(element.id, ["text": encode(body)], snapshotForUndo: false)
    }

    private func setParagraphLevel(_ element: DeckElement, _ pIndex: Int, _ level: Int) {
        guard var body = element.text, body.paragraphs.indices.contains(pIndex) else { return }
        body.paragraphs[pIndex].level = level
        editor.patchElement(element.id, ["text": encode(body)], snapshotForUndo: false)
    }

    /// The backend's text shape, as plain JSON, so a run edit is a real server write.
    private func encode(_ body: DeckTextBody) -> [String: Any] {
        ["paragraphs": body.paragraphs.map { para in
            var dict: [String: Any] = ["runs": para.runs.map { run in
                ["text": run.text, "style": run.style.map(styleDict) ?? [:]]
            }]
            if let level = para.level { dict["level"] = level }
            if let align = para.align { dict["align"] = align }
            if let spacing = para.lineSpacing { dict["line_spacing"] = spacing }
            return dict
        }]
    }

    private func styleDict(_ style: DeckStyle) -> [String: Any] {
        var dict: [String: Any] = [:]
        if let value = style.font { dict["font"] = value }
        if let value = style.size { dict["size"] = value }
        if let value = style.bold { dict["bold"] = value }
        if let value = style.italic { dict["italic"] = value }
        if let value = style.underline { dict["underline"] = value }
        if let value = style.color { dict["color"] = value }
        return dict
    }

    private func imageInspector(_ element: DeckElement) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Picker("Fit", selection: Binding(
                get: { element.image?.fit ?? "contain" },
                set: { editor.patchElement(element.id, ["image": ["fit": $0]]) })) {
                Text("Contain").tag("contain"); Text("Cover").tag("cover"); Text("Stretch").tag("stretch")
            }.pickerStyle(.segmented)
            TextField("Alt text", text: Binding(
                get: { element.image?.alt ?? "" },
                set: { editor.patchElement(element.id, ["image": ["alt": $0]]) }))
                .textFieldStyle(.roundedBorder).font(.system(size: 11))
                .focused($focus, equals: .inspector)
        }
    }

    private func shapeInspector(_ element: DeckElement) -> some View {
        HStack {
            Text("Fill").font(.system(size: 11)).foregroundStyle(Palette.secondary)
            ColorPicker("", selection: Binding(
                get: { Color(hexString: element.style?.fill ?? "#ECEDDF") },
                set: { editor.patchElement(element.id, ["style": ["fill": $0.deckHex]]) }),
                supportsOpacity: false).labelsHidden().frame(width: 36)
            Text("Stroke").font(.system(size: 11)).foregroundStyle(Palette.secondary)
            ColorPicker("", selection: Binding(
                get: { Color(hexString: element.style?.stroke ?? "#DFE2D6") },
                set: { editor.patchElement(element.id, ["style": ["stroke": $0.deckHex]]) }),
                supportsOpacity: false).labelsHidden().frame(width: 36)
        }
    }

    private var arrangeSection: some View {
        Card(padding: 14, interactive: false) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Arrange").font(.system(size: 12, weight: .semibold))
                HStack(spacing: 4) {
                    ForEach([("left", "arrow.left.to.line"), ("centerX", "arrow.left.and.right"),
                             ("right", "arrow.right.to.line")], id: \.0) { mode, icon in
                        Button { editor.align(mode) } label: { Image(systemName: icon) }.buttonStyle(.plain)
                    }
                }
                HStack(spacing: 4) {
                    ForEach([("top", "arrow.up.to.line"), ("middle", "arrow.up.and.down"),
                             ("bottom", "arrow.down.to.line")], id: \.0) { mode, icon in
                        Button { editor.align(mode) } label: { Image(systemName: icon) }.buttonStyle(.plain)
                    }
                }
                HStack(spacing: 6) {
                    Button("Distribute H") { editor.distribute("h") }.buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
                    Button("Distribute V") { editor.distribute("v") }.buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
                }
            }
        }
    }

    private func styleToggle(_ label: String, active: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label).font(.system(size: 12, weight: .semibold))
                .frame(width: 26, height: 22)
                .background(active ? Palette.sage : Palette.surfaceSubtle, in: RoundedRectangle(cornerRadius: 5))
        }.buttonStyle(.plain)
    }

    // MARK: notes

    private var notesPane: some View {
        VStack(alignment: .leading, spacing: 6) {
            Eyebrow(text: "SPEAKER NOTES")
            TextEditor(text: Binding(
                get: { editor.currentSlide?.notes ?? "" },
                set: { editor.patchSlide(["notes": $0]) }))
                .font(.system(size: 12))
                .frame(height: 72)
                .focused($focus, equals: .notes)
                .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(Palette.line))
        }
        .padding(12)
        .background(Palette.surfaceSubtle)
    }

    // MARK: keyboard

    /// Shortcuts live on zero-size buttons so they are real menu-level key equivalents, and
    /// each action returns early while a text field has focus — ⌘C must not steal a copy from
    /// the notes editor.
    private var shortcuts: some View {
        ZStack {
            Button("Copy") { if focus == nil { editor.copyElements() } }
                .keyboardShortcut("c", modifiers: .command)
            Button("Paste") { if focus == nil { editor.paste() } }
                .keyboardShortcut("v", modifiers: .command)
            Button("Duplicate") { if focus == nil { editor.duplicateSelection() } }
                .keyboardShortcut("d", modifiers: .command)
            Button("Undo") { if focus == nil { editor.undo() } }
                .keyboardShortcut("z", modifiers: .command)
            Button("Redo") { if focus == nil { editor.redo() } }
                .keyboardShortcut("z", modifiers: [.command, .shift])
            Button("Delete") { if focus == nil { editor.deleteSelection() } }
                .keyboardShortcut(.delete, modifiers: [])
            Button("Left") { if focus == nil { editor.nudge(dx: -1, dy: 0) } }
                .keyboardShortcut(.leftArrow, modifiers: [])
            Button("Right") { if focus == nil { editor.nudge(dx: 1, dy: 0) } }
                .keyboardShortcut(.rightArrow, modifiers: [])
            Button("Up") { if focus == nil { editor.nudge(dx: 0, dy: -1) } }
                .keyboardShortcut(.upArrow, modifiers: [])
            Button("Down") { if focus == nil { editor.nudge(dx: 0, dy: 1) } }
                .keyboardShortcut(.downArrow, modifiers: [])
        }
        .frame(width: 0, height: 0)
        .opacity(0)
        .allowsHitTesting(false)
    }
}

// MARK: - Small helpers

private struct Triangle: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.midX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
        path.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
        path.closeSubpath()
        return path
    }
}

private enum HandleCorner: CaseIterable {
    case topLeft, topRight, bottomLeft, bottomRight, midLeft, midRight, midTop, midBottom

    var touchesLeft: Bool { self == .topLeft || self == .bottomLeft || self == .midLeft }
    var touchesRight: Bool { self == .topRight || self == .bottomRight || self == .midRight }
    var touchesTop: Bool { self == .topLeft || self == .topRight || self == .midTop }
    var touchesBottom: Bool { self == .bottomLeft || self == .bottomRight || self == .midBottom }

    func point(in rect: CGRect) -> CGPoint {
        let x = touchesLeft ? rect.minX : (touchesRight ? rect.maxX : rect.midX)
        let y = touchesTop ? rect.minY : (touchesBottom ? rect.maxY : rect.midY)
        return CGPoint(x: x, y: y)
    }
}

private extension Color {
    /// The colour as `#RRGGBB`, which is the form the deck document stores. Converting
    /// through sRGB keeps a picked colour stable across displays.
    var deckHex: String {
        let colour = NSColor(self).usingColorSpace(.sRGB) ?? .black
        let red = Int((colour.redComponent * 255).rounded())
        let green = Int((colour.greenComponent * 255).rounded())
        let blue = Int((colour.blueComponent * 255).rounded())
        return String(format: "#%02X%02X%02X", red, green, blue)
    }
}
