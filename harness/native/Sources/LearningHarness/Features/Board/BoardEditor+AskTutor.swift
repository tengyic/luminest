import SwiftUI
import AppKit

// MARK: - Ask the tutor

extension BoardEditor {
    /// The snapshot the tutor reads is composited by the *same* renderer the PDF export
    /// uses, so what the model sees is exactly what the learner sees — minus embeds,
    /// which are chips rather than frames for licence reasons.
    var askSheet: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("Ask the tutor about this selection", systemImage: "lasso.and.sparkles")
                .font(.system(size: 14, weight: .semibold))
            Text("The selected objects are captured as an image and sent with your question. The answer is pinned back onto the board next to what you selected.")
                .font(.system(size: 11)).foregroundStyle(Palette.secondary)
            TextEditor(text: $questionDraft)
                .font(.system(size: 12)).scrollContentBackground(.hidden)
                .padding(7).frame(height: 84)
                .background(Palette.background, in: RoundedRectangle(cornerRadius: 10))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(Palette.line))
            HStack {
                Spacer()
                Button("Cancel") { askingAbout = nil }.keyboardShortcut(.cancelAction)
                Button {
                    Task { await ask() }
                } label: {
                    HStack {
                        Text(askBusy ? "Thinking…" : "Ask")
                        if askBusy { ProgressView().controlSize(.small) }
                    }
                }
                .keyboardShortcut(.defaultAction)
                .buttonStyle(LuminfestButtonStyle())
                .disabled(askBusy || questionDraft.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        .padding(20)
        .frame(width: 430)
    }

    func ask() async {
        guard let rect = askingAbout else { askingAbout = nil; return }
        askBusy = true
        defer { askBusy = false; askingAbout = nil }
        let padded = rect.insetBy(dx: -12, dy: -12)
        let nodes = board.nodes.filter { $0.frame.intersects(padded) }
        // The client-side hash is the anchor's provenance: the answer node records which
        // snapshot it answered, so a later reader can tell what was asked about.
        guard let image = BoardRenderer.image(of: nodes, in: padded),
              let tiff = image.tiffRepresentation,
              let rep = NSBitmapImageRep(data: tiff),
              let png = rep.representation(using: .png, properties: [:]) else {
            board.error = "The selection could not be captured; nothing was asked."
            return
        }
        let dataURL = "data:image/png;base64," + png.base64EncodedString()
        do {
            guard let api = AppStore.current?.api else { return }
            let result = try await api.json("/agent/chat", method: "POST", body: [
                "message": questionDraft,
                "developer_mode": false,
                "context": ["concept_id": conceptID, "board_id": board.boardID],
                "images": [dataURL],
            ])
            let answer = result["message"].string
            guard !answer.isEmpty else {
                board.error = "The tutor turn finished without a reply; the selection was not answered."
                return
            }
            #if canImport(CryptoKit)
            let digest = CryptoSHA256.digest(png)
            let sha = digest.map { String(format: "%02x", $0) }.joined()
            #else
            let sha = ""
            #endif
            board.pinAnswer(text: answer, question: questionDraft, imageSHA: sha,
                            at: CGPoint(x: padded.maxX + 24, y: padded.minY))
        } catch {
            board.error = error.localizedDescription
        }
    }
}
