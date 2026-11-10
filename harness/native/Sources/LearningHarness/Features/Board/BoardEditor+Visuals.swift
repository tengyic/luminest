import SwiftUI
import AppKit

// MARK: - Structured visual nodes on the board
//
// The Canvas layer draws ink, shapes, text and media. Interactive renderers cannot live
// inside a SwiftUI Canvas, so `visual` nodes are overlaid as WKWebViews positioned with
// the exact same `BoardViewport.toView` transform the Canvas uses. Static exports
// (PNG/PDF) draw an explicit placeholder instead - see BoardRenderer.

extension BoardEditor {

    func visualOverlay(in size: CGSize) -> some View {
        let nodes = board.nodes.filter { $0.kind == "visual" }
        return ZStack(alignment: .topLeading) {
            ForEach(nodes) { node in
                let origin = viewport.toView(CGPoint(x: node.x, y: node.y), in: size)
                let width = max(CGFloat(140), CGFloat(node.w) * viewport.zoom)
                let height = max(CGFloat(100), CGFloat(node.h) * viewport.zoom)
                VisualNodeFrame(node: node, isSelected: selection.contains(node.id)) {
                    selection.replace(with: node.id)
                }
                .frame(width: width, height: height)
                .position(x: origin.x + width / 2, y: origin.y + height / 2)
            }
        }
        .frame(width: size.width, height: size.height)
    }

    /// Insert a validated structured object as a board node. Only the three keys the
    /// backend accepts are sent; status/provider/schema are derived server-side.
    func insertVisual(type: String, title: String, spec: [String: Any]) {
        guard let anchor = visualAnchor,
              let entry = VisualResources.catalog.types[type],
              let payload = try? JSON.make(["type": type, "title": title, "spec": spec]) else { return }
        board.beginEdit()
        board.add(node: BoardNode(id: "", kind: "visual",
                                  x: anchor.x, y: anchor.y,
                                  w: Double(entry.size.width), h: Double(entry.size.height),
                                  z: "", payload: payload))
    }
}

/// One visual node: a small native chrome (title + selection target) around the live
/// WebView. The chrome stays hittable so a node can still be selected and moved even
/// though the renderer underneath owns its own pointer events.
private struct VisualNodeFrame: View {
    let node: BoardNode
    let isSelected: Bool
    let onSelect: () -> Void

    private var title: String {
        let type = node.payload["type"].string
        let label = node.payload["title"].string
        return label.isEmpty ? type.uppercased() : label
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 5) {
                Image(systemName: "chart.xyaxis.line").font(.system(size: 9))
                Text(title).font(.system(size: 9, weight: .semibold)).lineLimit(1)
                Spacer(minLength: 2)
            }
            .padding(.horizontal, 6)
            .frame(height: 18)
            .background(Palette.surface)
            .contentShape(Rectangle())
            .onTapGesture(perform: onSelect)
            VisualWebView(node: node)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(Color.white)
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(isSelected ? Palette.indigoDeep : Palette.line,
                        lineWidth: isSelected ? 2 : 0.8)
        )
    }
}

// MARK: - Gallery

/// Starter specs are deliberately real, runnable examples - the same eight cases the
/// headless smoke test drives. A learner can place one without writing any JSON.
enum VisualStarterSpec {
    static func text(for type: String) -> String {
        switch type {
        case "mafs":
            return #"{"viewport":{"x":[-5,5],"y":[-2,8]},"curves":[{"expr":"x^2"}],"points":[{"x":1,"y":1,"label":"P"}]}"#
        case "plotly":
            return #"{"traces":[{"type":"scatter","x":[1,2,3,4],"y":[1,4,9,16],"mode":"lines+markers"}]}"#
        case "jsxgraph":
            return #"{"viewport":{"boundingbox":[-5,5,5,-5]},"functions":[{"expr":"sin(x)"}]}"#
        case "mathbox":
            return #"{"range":[[-3,3],[-3,3],[-3,3]],"surfaces":[{"expr":"sin(x)*cos(y)","grid":16}]}"#
        case "molecule":
            return #"{"format":"pdb","data":"ATOM      1  C   MOL A   1       0.000   0.000   0.000  1.00  0.00           C\nATOM      2  O   MOL A   1       1.200   0.000   0.000  1.00  0.00           O\n","style":"stick"}"#
        case "desmos":
            return #"{"expressions":[{"latex":"x^2"}]}"#
        case "tikz":
            return #"{"source":"\\begin{tikzpicture}\\draw (0,0) circle (1in);\\end{tikzpicture}"}"#
        case "tex":
            // Doubly escaped on purpose: this is a JSON string literal that decodes to the
            // TeX `\frac{...}{...}`, not a Swift escape.
            return #"{"latex":"x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}","display":true}"#
        default:
            return "{}"
        }
    }
}

struct VisualGalleryView: View {
    let catalog: VisualCatalog
    let onCreate: (String, String, [String: Any]) -> Void
    let onCancel: () -> Void

    @State private var selectedType = "mafs"
    @State private var title = ""
    @State private var specText = VisualStarterSpec.text(for: "mafs")
    @State private var parseError = ""

    private var entry: VisualCatalog.Entry? { catalog.types[selectedType] }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Add an interactive visual").font(.headline)
            Text("Structured content objects are validated by the board before they are stored. "
                 + "Each renderer has its own fields.")
                .font(.system(size: 11)).foregroundStyle(Palette.secondary)

            HStack(alignment: .top, spacing: 14) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Renderer").font(.system(size: 10, weight: .semibold))
                    ForEach(catalog.order, id: \.self) { type in
                        if let item = catalog.types[type] {
                            Button {
                                selectedType = type
                                specText = VisualStarterSpec.text(for: type)
                                parseError = ""
                            } label: {
                                VStack(alignment: .leading, spacing: 1) {
                                    HStack(spacing: 5) {
                                        Text(item.label).font(.system(size: 11, weight: .semibold))
                                        if item.isExternal {
                                            Text("external").font(.system(size: 8))
                                                .foregroundStyle(.orange)
                                        }
                                    }
                                    Text(item.purpose).font(.system(size: 9))
                                        .foregroundStyle(Palette.tertiary)
                                }
                                .padding(.vertical, 3)
                                .padding(.horizontal, 6)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(selectedType == type
                                            ? Palette.indigoDeep.opacity(0.12) : Color.clear)
                                .clipShape(RoundedRectangle(cornerRadius: 4))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                .frame(width: 190)

                VStack(alignment: .leading, spacing: 8) {
                    if let entry {
                        Text("\(entry.label) — \(entry.renderer)")
                            .font(.system(size: 11, weight: .semibold))
                        if let requirement = entry.requirement, !requirement.isEmpty {
                            Text(requirement).font(.system(size: 10))
                                .foregroundStyle(.orange)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        Text("spec fields: \(entry.specKeys.joined(separator: ", "))")
                            .font(.system(size: 9)).foregroundStyle(Palette.tertiary)
                    }
                    TextField("Title (optional)", text: $title)
                        .textFieldStyle(.roundedBorder)
                    Text("Spec (JSON)").font(.system(size: 10, weight: .semibold))
                    TextEditor(text: $specText)
                        .font(.system(size: 10, design: .monospaced))
                        .frame(minHeight: 150)
                        .overlay(RoundedRectangle(cornerRadius: 4).stroke(Palette.line))
                    if !parseError.isEmpty {
                        Text(parseError).font(.system(size: 10)).foregroundStyle(.red)
                    }
                }
                .frame(minWidth: 320)
            }

            HStack {
                Spacer()
                Button("Cancel", action: onCancel).keyboardShortcut(.cancelAction)
                Button("Add to board") { commit() }
                    .keyboardShortcut(.defaultAction)
                    .disabled(catalog.types.isEmpty)
            }
        }
        .padding(16)
        .frame(minWidth: 620, minHeight: 380)
    }

    private func commit() {
        guard let data = specText.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data),
              let spec = object as? [String: Any] else {
            parseError = "Spec must be a JSON object."
            return
        }
        parseError = ""
        onCreate(selectedType, title, spec)
    }
}
