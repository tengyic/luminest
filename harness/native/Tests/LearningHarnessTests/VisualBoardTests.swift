import XCTest
@testable import LearningHarness

/// The native half of the structured-visual contract: the node kind, the tool entry,
/// the runnable starter specs, and the catalog the gallery renders from.
final class VisualBoardTests: XCTestCase {

    func testVisualIsARecognisedBoardKind() {
        XCTAssertTrue(BoardKind.all.contains("visual"))
        XCTAssertFalse(BoardKind.ink.contains("visual"),
                       "a visual node is not ink and must not go through the pen path")
    }

    func testVisualToolMetadata() {
        let tool = BoardTool.visual
        XCTAssertEqual(tool.rawValue, "visual")
        XCTAssertEqual(tool.label, "Interactive visual")
        XCTAssertEqual(tool.shortcut, "U")
        XCTAssertEqual(tool.group, .content)
        XCTAssertNil(tool.nodeKind, "the gallery creates the node; a canvas gesture must not")
        XCTAssertTrue(BoardTool.allCases.contains(tool))
        // The shortcut must be unique: two tools owning "U" makes one unreachable.
        let owners = BoardTool.allCases.filter { $0.shortcut == "U" }
        XCTAssertEqual(owners.count, 1)
    }

    func testVisualNodeParsesFromBoardJSON() throws {
        let json = try JSON.make([
            "id": "node-1", "kind": "visual", "x": 100, "y": 120,
            "w": 560, "h": 360, "z": "a",
            "payload": ["type": "mafs", "title": "Parabola", "spec": ["curves": [["expr": "x^2"]]]],
        ])
        let node = BoardNode.parse(json)
        XCTAssertNotNil(node)
        XCTAssertEqual(node?.kind, "visual")
        XCTAssertEqual(node?.w, 560)
        XCTAssertEqual(node?.h, 360)
        XCTAssertEqual(node?.payload["type"].string, "mafs")
    }

    /// A starter spec must be parseable JSON *and* a JSON object, otherwise the gallery
    /// would offer an example that the backend always refuses.
    func testEveryStarterSpecIsAValidJSONObject() {
        let types = ["mafs", "plotly", "jsxgraph", "mathbox", "molecule", "desmos", "tikz", "tex"]
        for type in types {
            let text = VisualStarterSpec.text(for: type)
            let data = Data(text.utf8)
            let object = try? JSONSerialization.jsonObject(with: data)
            XCTAssertNotNil(object, "\(type): starter spec is not valid JSON")
            XCTAssertTrue(object is [String: Any], "\(type): starter spec is not an object")
        }
    }

    func testTikzStarterSpecCarriesRealTeXAfterJSONDecoding() throws {
        let data = Data(VisualStarterSpec.text(for: "tikz").utf8)
        let object = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        let source = try XCTUnwrap(object["source"] as? String)
        XCTAssertTrue(source.contains("\\begin{tikzpicture}"))
        XCTAssertTrue(source.contains("\\draw"))
    }

    func testCatalogIsLoadedFromTheBundledResources() throws {
        let root = VisualResources.root
        XCTAssertNotNil(root, "Visuals/ must be present in the resource bundle")
        let catalog = VisualCatalog.load(from: root)
        XCTAssertEqual(catalog.version, 1)
        XCTAssertEqual(Set(catalog.types.keys), Set([
            "mafs", "plotly", "jsxgraph", "mathbox", "molecule", "desmos", "tikz", "tex",
        ]))
        XCTAssertEqual(Set(catalog.order), Set(catalog.types.keys))
        XCTAssertEqual(catalog.types["desmos"]?.provider, "external")
        XCTAssertEqual(catalog.types["desmos"]?.requires, "desmosApiKey")
        XCTAssertEqual(catalog.types["tikz"]?.requires, "tikzAssets")
        for type in catalog.order {
            XCTAssertTrue(catalog.types[type]?.isAvailable == true, "\(type) is not available")
            XCTAssertFalse(catalog.types[type]?.specKeys.isEmpty ?? true)
            XCTAssertGreaterThan(catalog.types[type]?.size.width ?? 0, 0)
        }
    }

    func testTikzAssetsAreReallyInsideTheBundle() {
        // The renderer fetches a WASM engine with fetch(); a bundle that omits it would
        // fail only when a learner tried to use TikZ. Fail here instead.
        XCTAssertTrue(VisualResources.hasTikzAssets)
    }

    func testSchemeHandlerServesOnlyBundledFiles() throws {
        let root = try XCTUnwrap(VisualResources.root)
        XCTAssertTrue(FileManager.default.fileExists(
            atPath: root.appendingPathComponent("index.html").path))
        XCTAssertTrue(FileManager.default.fileExists(
            atPath: root.appendingPathComponent("visuals.bundle.js").path))
        XCTAssertEqual(VisualResources.mime(for: "wasm"), "application/wasm")
        XCTAssertEqual(VisualResources.mime(for: "gz"), "application/gzip")
    }
}
