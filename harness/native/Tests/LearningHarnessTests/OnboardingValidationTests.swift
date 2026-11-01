import XCTest
@testable import LearningHarness

/// The sign-up form's own copy of the server's address rule.
///
/// These cases exist because of a specific failure: an address typed without an `@` left the
/// submit button disabled with no message, so the learner saw a dead button and no request
/// ever reached the server - nothing in the log, nothing on screen. The rule is pinned here so
/// that tightening or loosening it cannot quietly reintroduce a form that refuses to say why.
final class OnboardingValidationTests: XCTestCase {
    private func valid(_ email: String) -> Bool {
        OnboardingView.emailLooksValid(email)
    }

    func testAddressWithoutAtIsRejected() {
        // The exact string that produced the dead button.
        XCTAssertFalse(valid("tengyi.chen.aian.org.cn"))
        XCTAssertFalse(valid("tengyichen"))
        XCTAssertFalse(valid(""))
    }

    func testOrdinaryAddressesAreAccepted() {
        XCTAssertTrue(valid("tengyi.chen@aian.org.cn"))
        XCTAssertTrue(valid("you@example.com"))
        XCTAssertTrue(valid("a.b+tag@sub.domain.co.uk"))
        XCTAssertTrue(valid("  you@example.com  "), "surrounding whitespace is trimmed")
    }

    func testMalformedAddressesAreRejected() {
        XCTAssertFalse(valid("@example.com"), "no local part")
        XCTAssertFalse(valid("you@"), "no domain")
        XCTAssertFalse(valid("you@example"), "no dotted domain")
        XCTAssertFalse(valid("you@.com"), "domain starts with a dot")
        XCTAssertFalse(valid("you@example."), "domain ends with a dot")
        XCTAssertFalse(valid("you@@example.com"), "two separators")
        XCTAssertFalse(valid("you @example.com"), "space inside the address")
    }
}
