import Foundation
import CoreGraphics

// MARK: - Visual resource bundle + catalog
//
// The WebView host is a *local* resource directory. It is loaded through a custom
// WKURLSchemeHandler rather than file:// because the vendored TikZ engine fetches its
// TeX WASM/core-dump with fetch(); file:// URLs make that a cross-origin request and the
// whole renderer dies with an opaque CORS error. A same-origin custom scheme keeps the
// CSP at `default-src 'self'` and keeps every byte of the renderers on this Mac.

struct VisualCatalog: Codable, Equatable {
    struct Entry: Codable, Equatable {
        let status: String
        let provider: String
        let requires: String?
        let label: String
        let purpose: String
        let renderer: String
        let defaultSize: [Double]
        let specKeys: [String]
        let requirement: String?

        var isAvailable: Bool { status == "available" }
        var isExternal: Bool { provider == "external" }
        var size: CGSize {
            CGSize(width: defaultSize.first ?? 560, height: defaultSize.dropFirst().first ?? 380)
        }
    }

    let version: Int
    let types: [String: Entry]
    let order: [String]

    static let empty = VisualCatalog(version: 0, types: [:], order: [])

    /// The catalog is generated from the backend's single source of truth at build time
    /// (`scripts/export_visual_catalog.py`). A missing or malformed file is an explicit
    /// empty catalog, never a hand-written fallback list that could drift out of sync.
    static func load(from root: URL?) -> VisualCatalog {
        guard let root,
              let data = try? Data(contentsOf: root.appendingPathComponent("catalog.json")),
              let decoded = try? JSONDecoder().decode(VisualCatalog.self, from: data) else {
            return .empty
        }
        return decoded
    }
}

enum VisualResources {
    static let scheme = "luminest-visuals"
    private static let tikzWasm = "3f69afb974a1e83f66a36f7618f88a38c254034b.wasm"

    /// `Package.swift` declares `.copy("Visuals")`, which preserves the directory tree
    /// inside the generated resource bundle. `.process("Resources")` flattens it and
    /// breaks every relative `vendor/...` fetch, so the packaged `.app` would boot with
    /// no usable renderers. Check the layouts both the packaged `.app` and a `swift test`
    /// tree actually use before declaring the assets absent.
    static var root: URL? {
        var candidates: [URL] = []
        if let resources = AppResources.bundle.resourceURL {
            candidates.append(resources.appendingPathComponent("Visuals", isDirectory: true))
            candidates.append(resources)
        }
        if let direct = AppResources.bundle.url(forResource: "Visuals", withExtension: nil) {
            candidates.append(direct)
        }
        let exists = FileManager.default
        for candidate in candidates where exists.fileExists(
            atPath: candidate.appendingPathComponent("index.html").path) {
            return candidate
        }
        return nil
    }

    static var indexURL: URL? { URL(string: "\(scheme)://bundle/index.html") }

    static var catalog: VisualCatalog { VisualCatalog.load(from: root) }

    /// Fail-closed: the TikZ renderer is only enabled when the WASM it must fetch is
    /// really inside the bundle. A missing asset yields RENDERER_ASSETS_NOT_INSTALLED.
    static var hasTikzAssets: Bool {
        guard let root else { return false }
        return FileManager.default.fileExists(
            atPath: root.appendingPathComponent("vendor/tikzjax/\(tikzWasm)").path)
    }

    /// Desmos is an external provider and needs a key. Never bake one into the binary:
    /// read the operator's own configuration at runtime.
    static var desmosAPIKey: String {
        if let key = UserDefaults.standard.string(forKey: "luminest.desmosApiKey"),
           !key.isEmpty { return key }
        return ProcessInfo.processInfo.environment["LUMINEST_DESMOS_API_KEY"] ?? ""
    }

    static var runtimeConfig: [String: Any] {
        ["tikzAssets": hasTikzAssets, "desmosApiKey": desmosAPIKey]
    }

    static func mime(for pathExtension: String) -> String {
        switch pathExtension.lowercased() {
        case "html": return "text/html"
        case "js": return "text/javascript"
        case "css": return "text/css"
        case "json": return "application/json"
        case "wasm": return "application/wasm"
        case "gz": return "application/gzip"
        case "ttf": return "font/ttf"
        case "svg": return "image/svg+xml"
        case "png": return "image/png"
        default: return "application/octet-stream"
        }
    }
}
