import XCTest
@testable import LearningHarness

/// The header that decides what language the server *generates* in.
///
/// It is a pure mapping, so it is tested as one: the store object is main-actor isolated
/// and cannot be consulted from the request paths, which is exactly why this reads the
/// stored preference instead.
final class ContentLanguageTests: XCTestCase {

    func testSimplifiedChineseOutranksEnglishButStillListsIt() {
        let header = APIClient.acceptLanguage(preference: "zh-Hans")
        XCTAssertTrue(header.hasPrefix("zh-Hans"))
        // Without q-values a server that honours preference order can pick the tail.
        XCTAssertTrue(header.contains("q="))
        XCTAssertTrue(header.contains("en"))
    }

    func testEnglishIsSentAlone() {
        XCTAssertEqual(APIClient.acceptLanguage(preference: "en"), "en")
    }

    /// `nil` is the stored value for "follow the system", and it must not turn into the
    /// development language when the Mac is set to Chinese.
    func testSystemPreferenceFollowsTheSystemFirstLanguage() {
        XCTAssertEqual(APIClient.acceptLanguage(preference: nil, system: ["zh-Hans-CN", "en-US"]),
                       "zh-Hans-CN")
        XCTAssertEqual(APIClient.acceptLanguage(preference: nil, system: []), "en")
    }

    /// A raw value from an older build must degrade to "follow the system" rather than
    /// silently asking for English.
    func testUnknownStoredValueFallsBackToTheSystem() {
        XCTAssertEqual(APIClient.acceptLanguage(preference: "fr", system: ["zh-Hans-CN"]),
                       "zh-Hans-CN")
    }
}
