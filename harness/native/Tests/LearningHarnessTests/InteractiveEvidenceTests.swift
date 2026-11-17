import XCTest
@testable import LearningHarness

final class InteractiveEvidenceTests: XCTestCase {
    func testEvidenceStateKeepsOnlyNumbersAndStrings() throws {
        let state: [String: JSON] = [
            "slope": .number(2.5),
            "mode": .string("linear"),
            "flag": .bool(true),
            "nested": .object(["x": .number(1)]),
            "list": .array([.number(1)]),
            "empty": .null
        ]
        let body = AppStore.evidenceState(state)
        XCTAssertEqual(body.count, 2)
        XCTAssertEqual(body["slope"] as? Double, 2.5)
        XCTAssertEqual(body["mode"] as? String, "linear")
        XCTAssertNil(body["flag"])
        XCTAssertNil(body["nested"])
        XCTAssertNil(body["list"])
        XCTAssertNil(body["empty"])

        // The narrowed body must be safely serializable for `api.json`.
        XCTAssertNoThrow(try JSONSerialization.data(withJSONObject: ["artifact_id": "a1", "state": body]))
    }

    func testAssistantMessageCarriesInteractiveAsArray() {
        let entry = JSON.object(["artifact_id": .string("a1"),
                                 "spec": .object(["schema_version": .number(1)]),
                                 "source": .string("model")])
        let assistant: JSON = .object(["role": .string("assistant"),
                                       "content": .string("Try this probe."),
                                       "interactive": .array([entry])])
        XCTAssertEqual(assistant["role"].string, "assistant")
        XCTAssertEqual(assistant["interactive"].array.count, 1)
        XCTAssertEqual(assistant["interactive"].array.first?["artifact_id"].string, "a1")
        XCTAssertEqual(assistant["interactive"].array.first?["spec"]["schema_version"].double, 1)

        // A message with no interactive renders nothing (Studio.swift reads .array).
        let plain: JSON = .object(["role": .string("user"), "content": .string("hi")])
        XCTAssertTrue(plain["interactive"].array.isEmpty)
    }
}
