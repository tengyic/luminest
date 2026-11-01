import XCTest
@testable import LearningHarness

/// The playground entry point is mostly a hosted web view, and a web view cannot be
/// exercised in a unit test. What *can* be pinned is the small amount of logic the app
/// contributes to it, and that logic is the security-relevant part: the URL it loads and
/// the two scripts it injects. A regression in either would be silent in the UI and loud
/// in its consequences - a token that breaks out of its literal, or a slug read as selector
/// syntax - so both are asserted here.
final class PlaygroundTests: XCTestCase {

    // MARK: the URL

    func testGalleryURLJoinsTheOriginAndThePage() {
        XCTAssertEqual(PlaygroundWebView.galleryURL("http://127.0.0.1:8765")?.absoluteString,
                       "http://127.0.0.1:8765/playground")
        // A stored endpoint may carry a trailing slash; it must not produce a double slash.
        XCTAssertEqual(PlaygroundWebView.galleryURL("https://example.test/")?.absoluteString,
                       "https://example.test/playground")
    }

    func testGalleryURLRefusesAnEmptyOrigin() {
        XCTAssertNil(PlaygroundWebView.galleryURL(""))
        XCTAssertNil(PlaygroundWebView.galleryURL("/"))
    }

    // MARK: the token injection

    func testTokenScriptSeedsTheKeyThePageReads() {
        let script = PlaygroundWebView.tokenScript("abc")
        XCTAssertTrue(script.contains("sessionStorage.setItem('luminfest.token', \"abc\")"), script)
    }

    func testTokenScriptEscapesTheTokenSoItCannotBreakOut() {
        // Each of these would terminate the literal, inject code, or split the statement if
        // the token were interpolated raw. JSON-encoding is what stops that.
        XCTAssertEqual(PlaygroundWebView.jsonLiteral("abc"), "\"abc\"")
        XCTAssertEqual(PlaygroundWebView.jsonLiteral("a\"b"), "\"a\\\"b\"")
        XCTAssertEqual(PlaygroundWebView.jsonLiteral("a\\b"), "\"a\\\\b\"")
        XCTAssertEqual(PlaygroundWebView.jsonLiteral("a\nb"), "\"a\\nb\"")
        XCTAssertEqual(PlaygroundWebView.jsonLiteral("a'b"), "\"a'b\"")
        // The script for a newline-bearing token must be a single line: a raw newline inside
        // the statement would end it mid-expression.
        XCTAssertFalse(PlaygroundWebView.tokenScript("a\nb").contains("a\nb"))
    }

    // MARK: the deep link

    func testOpenScriptMatchesTheCardByAttributeNotBySelector() {
        let script = PlaygroundWebView.Coordinator.openScript("math-plot-points-slope-intercept")
        // The slug is data, compared against `data-slug`; it is never pasted into a CSS
        // selector, so a slug can never be read as selector syntax.
        XCTAssertTrue(script.contains("getAttribute('data-slug')"), script)
        XCTAssertFalse(script.contains(".card[data-slug="), script)
    }

    func testOpenScriptCarriesTheSlugAsAJSONLiteral() {
        XCTAssertTrue(PlaygroundWebView.Coordinator.openScript("a\"b").contains("\"a\\\"b\""))
    }
}
