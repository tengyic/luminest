import XCTest
@testable import LearningHarness

/// The native disclosure control and the backend enum must not drift: the server rejects
/// an unknown level, and a client that sends "none" after the learner chose hints would be
/// worse than a client that sends nothing.
final class AssistanceLevelTests: XCTestCase {
    func testRawValuesMatchTheBackendLiteral() {
        XCTAssertEqual(AssistanceLevel.allCases.map(\.rawValue),
                       ["none", "research_only", "hints_only", "feedback_only"])
    }

    func testLegacyBooleanDraftKeepsItsWritingAndNamesAnHonestLevel() throws {
        let legacy = """
        {"text":"A long enough draft","reflection":"I changed my mind",
         "usedAI":true,"confirmed":true,"updatedAt":1}
        """.data(using: .utf8)!
        let draft = try JSONDecoder().decode(ProjectDrafts.Draft.self, from: legacy)
        XCTAssertEqual(draft.text, "A long enough draft")
        XCTAssertEqual(draft.assistanceLevel, .researchOnly)

        let encoded = try JSONEncoder().encode(draft)
        let roundTrip = try JSONDecoder().decode(ProjectDrafts.Draft.self, from: encoded)
        XCTAssertEqual(roundTrip.assistanceLevel, .researchOnly)
    }
}
