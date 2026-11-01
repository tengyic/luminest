import XCTest
@testable import LearningHarness

/// The launcher has to tell "the operator pointed the app at their own server" apart from
/// "the app remembered the fallback port it took last time". Both arrive as the same stored
/// string, and getting it wrong is not a cosmetic bug: the app starts no server and shows a
/// window that cannot sign in, with no message saying why.
@MainActor
final class BackendLauncherTests: XCTestCase {

    func testItsOwnFallbackPortsCountAsItsOwn() {
        for port in 8765...8785 {
            XCTAssertTrue(BackendLauncher.isOwnLocalEndpoint("http://127.0.0.1:\(port)"),
                          "\(port) is a port the launcher scans, so it is the app's own")
        }
    }

    func testLocalhostSpellingIsTheSameMachine() {
        XCTAssertTrue(BackendLauncher.isOwnLocalEndpoint("http://localhost:8766"))
    }

    /// Outside the scan range the operator meant something: a different local service, a
    /// server on the LAN, or one on the internet. None of those may be replaced by a
    /// locally spawned backend.
    func testAnythingElseIsAnOperatorsChoice() {
        XCTAssertFalse(BackendLauncher.isOwnLocalEndpoint("http://127.0.0.1:9000"))
        XCTAssertFalse(BackendLauncher.isOwnLocalEndpoint("https://luminfest.example.com"))
        XCTAssertFalse(BackendLauncher.isOwnLocalEndpoint("http://192.168.1.20:8766"))
        XCTAssertFalse(BackendLauncher.isOwnLocalEndpoint("not a url"))
        XCTAssertFalse(BackendLauncher.isOwnLocalEndpoint("http://127.0.0.1"))
    }
}
