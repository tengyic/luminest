import SwiftUI

// MARK: - Sheets

/// The write-on-board sheet. The typed text goes back to the editor so placement is
/// decided where the click happened rather than at a hard-coded centre.
struct TextSheet: View {
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


// MARK: - Image insert

/// Fetch a licence-cleared photograph and drop it on the board.
///
/// The whole point of this sheet is that a board image is never invented: every candidate
/// arrives through the backend's acquire pipeline, which clears the licence before the
/// bytes are cached, and only a cached asset can be placed. The node records the content
/// hash the board resolves bitmaps by, so the client renders the real file rather than a
/// decorative rectangle, and the credit travels with the node so attribution survives a
/// reload and an export.
struct ImagePickerSheet: View {
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
