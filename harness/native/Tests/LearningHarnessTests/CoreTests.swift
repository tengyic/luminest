import XCTest
@testable import LearningHarness

final class CoreTests: XCTestCase {
    func testTolerantJSON() throws {
        let json = try JSONDecoder().decode(JSON.self, from: Data("{\"id\":\"x\",\"value\":null,\"unknown\":[1,true,\"a\"]}".utf8))
        XCTAssertEqual(json["id"].string, "x")
        XCTAssertTrue(json["value"].isNull)
        XCTAssertTrue(json["missing"].isNull)
        XCTAssertEqual(json["unknown"].array.count, 3)
        XCTAssertEqual(try JSONDecoder().decode(JSON.self, from: JSONEncoder().encode(json)), json)
    }
    func testParameterValidationAndClamping() throws {
        let valid = try JSON.make(["id": "m", "label": "Slope", "min": -5, "max": 5, "value": 9])
        XCTAssertEqual(SimulationParameter.parse(valid)?.value, 5)
        XCTAssertNil(SimulationParameter.parse(try JSON.make(["id": "m", "min": 5, "max": -5, "value": 0])))
        XCTAssertNil(SimulationParameter.parse(try JSON.make(["id": "m", "value": 1])))
    }
    func testPlotMathematics() {
        XCTAssertEqual(PlotMath.value(kind: "linear", x: 3, parameters: ["m": 2, "b": 1]), 7)
        XCTAssertEqual(PlotMath.value(kind: "quadratic", x: 2, parameters: ["a": 2, "b": 3, "c": 1]), 15)
        XCTAssertEqual(PlotMath.value(kind: "equations", x: 2, parameters: ["m2": 3, "b2": 4], secondary: true), 10)
        XCTAssertEqual(PlotMath.value(kind: "probability", x: 1, parameters: ["n": 2, "p": 0.5])!, 0.5, accuracy: 1e-9)
        XCTAssertNil(PlotMath.value(kind: "generated_script", x: 1, parameters: [:]))
        XCTAssertNil(PlotMath.value(kind: "linear", x: .infinity, parameters: [:]))
        XCTAssertNil(PlotMath.value(kind: "quadratic", x: 1, parameters: ["a": .nan]))
    }
    func testBinomialDistributionSumsToOne() {
        for p in [0.0, 0.2, 0.5, 1.0] {
            let sum = (0...10).reduce(0.0) { $0 + (PlotMath.value(kind: "probability", x: Double($1), parameters: ["n": 10, "p": p]) ?? 0) }
            XCTAssertEqual(sum, 1, accuracy: 1e-9)
        }
    }
    func testDiagramToolIsAPathDrawingActionNotAShapePrimitive() {
        XCTAssertEqual(BoardTool.diagram.group, .draw)
        XCTAssertNil(BoardTool.diagram.nodeKind)
        XCTAssertEqual(BoardTool.diagram.label, "AI diagram")
    }
    func testDiagramPreviewCarriesAttributionWithoutBecomingAPersistedNode() throws {
        let node = BoardNode(id: "preview-path", kind: "path", x: 0, y: 0,
                             w: 20, h: 10, z: "",
                             payload: try JSON.make(["points": [[0.0, 0.0], [20.0, 10.0]]]))
        let preview = BoardPreview(title: "Supply and demand",
                                   provider: "Built-in editable diagram catalog",
                                   nodes: [node], sourceURL: "https://example.test/lesson",
                                   note: "Original schematic")
        XCTAssertEqual(preview.nodes.map(\.kind), ["path"])
        XCTAssertEqual(preview.sourceURL, "https://example.test/lesson")
        XCTAssertEqual(preview.note, "Original schematic")
    }
    @MainActor func testEndpointSecurity() throws {
        XCTAssertEqual(try APIClient.validateEndpoint("http://127.0.0.1:8765/"), "http://127.0.0.1:8765")
        XCTAssertEqual(try APIClient.validateEndpoint("https://example.com"), "https://example.com")
        XCTAssertThrowsError(try APIClient.validateEndpoint("http://example.com"))
        XCTAssertThrowsError(try APIClient.validateEndpoint("https://user:password@example.com"))
        XCTAssertThrowsError(try APIClient.validateEndpoint("https://example.com/api/v1"))
    }
}
