import SwiftUI
import AppKit

// The board shell: owns the store lifecycle, the export menu and the share flow.
// Exports never fake a format — PDF is vector-drawn here by the same compositor the
// lasso snapshot uses; SVG and the .lesson bundle come byte-for-byte from the backend
// so what is re-imported is exactly what was exported.

struct BoardSheet: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss
    @StateObject private var board: BoardStore
    @State private var notice: String?
    @State private var shareURL: URL?
    let conceptID: String

    init(conceptID: String) {
        self.conceptID = conceptID
        // The store needs the live API client; the environment is not available in init,
        // so the shared store reference (the same one the QA driver uses) supplies it.
        _board = StateObject(wrappedValue: BoardStore(api: AppStore.current?.api
            ?? APIClient(endpoint: UserDefaults.standard.string(forKey: "luminfest.endpoint") ?? "http://127.0.0.1:8765")))
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            if board.boardID.isEmpty {
                VStack(spacing: 14) {
                    ProgressView()
                    Text("Opening the board for this concept…").font(.system(size: 12)).foregroundStyle(Palette.secondary)
                    if let error = board.error {
                        Text(error).font(.system(size: 11)).foregroundStyle(Palette.peachDeep)
                    }
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                CanvasView(board: board, conceptID: conceptID)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            if let notice { footer(notice) }
        }
        .frame(minWidth: 1080, minHeight: 700)
        .task { await open() }
        .onAppear { ImageCache.shared.bind(api: store.api) }
    }

    private var header: some View {
        HStack(spacing: 12) {
            Image(systemName: "square.and.pencil").foregroundStyle(Palette.forest)
            VStack(alignment: .leading, spacing: 1) {
                Text(board.title.isEmpty ? "Board" : board.title)
                    .font(.system(size: 14, weight: .semibold))
                Text("Board \(board.boardID) · v\(board.version)")
                    .font(.system(size: 9)).foregroundStyle(Palette.tertiary)
            }
            Spacer()
            Menu {
                Button("Export PDF (vector)") { exportPDF() }
                Button("Export SVG") { exportRemote(format: "svg", name: "svg") }
                Button("Export .lesson bundle") { exportRemote(format: "lesson", name: "lesson") }
                Divider()
                Button("Create share link (7 days, read-only)") {
                    store.run { await createShare() }
                }
                if shareURL != nil {
                    Button("Revoke all share links for this board") {
                        store.run { await board.revokeShares(); shareURL = nil; notice = "All share links for this board were revoked." }
                    }
                }
            } label: {
                Label("Export & share", systemImage: "square.and.arrow.up")
            }
            Button("Close") { dismiss() }.keyboardShortcut(.cancelAction)
        }
        .padding(.horizontal, 14).padding(.vertical, 10)
        .background(.regularMaterial)
    }

    private func footer(_ text: String) -> some View {
        HStack {
            Text(text).font(.system(size: 10)).foregroundStyle(Palette.secondary).lineLimit(2)
            Spacer()
        }.padding(.horizontal, 14).padding(.vertical, 7).background(Palette.surfaceSubtle)
    }

    private func open() async {
        ImageCache.shared.bind(api: store.api)
        let id = BoardStore.id(forConcept: conceptID)
        await board.loadExisting(id)
        if board.boardID.isEmpty {
            await board.create(title: store.currentConcept.text("title", fallback: conceptID))
            // The created board gets a random id; rename the surface to the deterministic
            // concept id only if the server accepted it as-is (it does for create).
        }
    }

    // ---------------------------------------------------------------- export

    private func savePanel(name: String, ext: String) -> URL? {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = name
        panel.allowedContentTypes = ext == "pdf" ? [.pdf] : (ext == "svg" ? [.svg] : [.data])
        return panel.runModal() == .OK ? panel.url : nil
    }

    private func exportPDF() {
        guard let url = savePanel(name: board.title, ext: "pdf") else { return }
        // PDF is rendered client-side from the same compositor as the lasso snapshot:
        // vector strokes and text, embedded images by content hash, and media nodes as
        // chips because an embed licence does not travel with a rasterised page.
        let nodes = board.nodes
        let data = BoardRenderer.pdfData(of: nodes, pageSize: CGSize(width: 842, height: 595))
        guard let data, !data.isEmpty else {
            notice = "The PDF could not be rendered; nothing was written."
            return
        }
        do { try data.write(to: url, options: .atomic); notice = "PDF exported: \(url.lastPathComponent)" }
        catch { notice = "The PDF could not be written: \(error.localizedDescription)" }
    }

    private func exportRemote(format: String, name: String) {
        let api = store.api
        store.run {
            do {
                let data = try await api.data("/boards/\(board.boardID)/export",
                                             query: [URLQueryItem(name: "format", value: format)])
                guard let url = savePanel(name: board.title, ext: name) else { return }
                try data.write(to: url, options: .atomic)
                notice = "\(name.uppercased()) exported: \(url.lastPathComponent)"
            } catch {
                notice = "The export failed: \(error.localizedDescription)"
            }
        }
    }

    private func createShare() async {
        guard let url = await board.createShare() else { return }
        shareURL = url
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(url.absoluteString, forType: .string)
        notice = "Read-only link copied to the clipboard. It expires in 7 days and can be revoked from this menu."
    }
}
