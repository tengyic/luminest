import XCTest
@testable import LearningHarness

/// The shell used to be four independent Bools. These tests pin the one ordering that
/// decides which full-screen state wins when more than one flag is true.
final class AppLifecycleTests: XCTestCase {
    func testRestoreOutranksEveryOtherFlag() {
        for authenticated in [false, true] {
            for inCourseSetup in [false, true] {
                XCTAssertEqual(
                    AppLifecycle.resolve(restoring: true, authenticated: authenticated,
                                         inCourseSetup: inCourseSetup),
                    .restoring)
            }
        }
    }

    func testSignedOutAlwaysMeansOnboarding() {
        XCTAssertEqual(
            AppLifecycle.resolve(restoring: false, authenticated: false,
                                 inCourseSetup: true),
            .onboarding)
    }

    func testFirstRunOutranksTheOrdinaryShell() {
        XCTAssertEqual(
            AppLifecycle.resolve(restoring: false, authenticated: true,
                                 inCourseSetup: true),
            .courseSetup)
        XCTAssertEqual(
            AppLifecycle.resolve(restoring: false, authenticated: true,
                                 inCourseSetup: false),
            .shell)
    }
}
