import SwiftUI
import AppKit

// MARK: - AI line diagrams

extension BoardEditor {
    /// Counts for the preview summary, kept out of the string literal: a Swift
    /// interpolation cannot contain an escaped quote, and the two filters in one
    /// Label are unreadable besides.
    var diagramStrokeCount: Int {
        diagramPreview?.nodes.filter { $0.kind == "path" }.count ?? 0
    }

    var diagramLabelCount: Int {
        diagramPreview?.nodes.filter { $0.kind == "text" }.count ?? 0
    }

    var diagramSheet: some View {
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

    var curveSheet: some View {
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

    var diagramCatalogSheet: some View {
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

    var vectorizerSheet: some View {
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

    var sourceImageNode: BoardNode? {
        board.nodes.first(where: { $0.kind == "image" && $0.payload["sha256"].string == vectorizeSource })
    }

    func parsePair(_ text: String, fallback: (Double, Double)) -> (Double, Double)? {
        let pieces = text.split(whereSeparator: { $0 == "," || $0 == " " || $0 == ";" })
        guard pieces.count == 2, let first = Double(pieces[0]), let second = Double(pieces[1]),
              first.isFinite, second.isFinite, second > first else { return nil }
        return (first, second)
    }

    func parseCoefficients(_ text: String) -> [Double]? {
        let pieces = text.split(whereSeparator: { $0 == "," || $0 == " " || $0 == ";" })
        guard !pieces.isEmpty, pieces.count <= 16 else { return nil }
        let values = pieces.compactMap { Double($0) }
        guard values.count == pieces.count, values.allSatisfy({ $0.isFinite && abs($0) <= 1000 }) else { return nil }
        return values
    }

    func loadDiagramCatalog() async {
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

    func previewTemplate(_ id: String) async {
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

    func requestCurve() async {
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

    func imageDataURL(_ data: Data) -> String? {
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

    func requestVectorization() async {
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

    func previewNodes(_ values: [JSON]) -> [BoardNode] {
        values.compactMap { value -> BoardNode? in
            let kind = value["kind"].string
            guard kind == "path" || kind == "text" else { return nil }
            return BoardNode(id: "preview-" + UUID().uuidString, kind: kind,
                             x: value["x"].double, y: value["y"].double,
                             w: value["w"].double, h: value["h"].double,
                             z: "", payload: value["payload"])
        }
    }

    func refreshCanvasPreview() {
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

    func playVectorization() async {
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

    func acceptCurve() {
        guard let pendingCurvePreview else { return }
        board.addMany(nodes: pendingCurvePreview.nodes)
        notice = "Curve added · \(pendingCurvePreview.title)"
        self.pendingCurvePreview = nil
        showingCurves = false
    }

    func acceptCatalogPreview() {
        guard let catalogPreview else { return }
        board.addMany(nodes: catalogPreview.nodes)
        notice = "Diagram added · \(catalogPreview.title)"
        self.catalogPreview = nil
        showingDiagramCatalog = false
    }

    func acceptVectorization() {
        guard let vectorizePreview else { return }
        stopTracePlayback = true
        board.addMany(nodes: vectorizePreview.nodes)
        notice = "Image traced · \(vectorizePreview.nodes.filter { $0.kind == "path" }.count) line strokes"
        self.vectorizePreview = nil
        showingVectorizer = false
    }

    func requestDiagram() async {
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

    func acceptDiagram() {
        guard let diagramPreview else { return }
        board.addMany(nodes: diagramPreview.nodes)
        pendingDiagramAt = nil
        notice = "Diagram added · \(diagramPreview.title)"
        self.diagramPreview = nil
    }
}
