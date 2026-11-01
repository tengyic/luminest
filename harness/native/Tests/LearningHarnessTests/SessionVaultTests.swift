import XCTest
@testable import LearningHarness

/// Keychain round-trip tests for the session vault (audit finding E-1).
///
/// These use the *real* macOS Keychain of the test host with the
/// `WhenUnlockedThisDeviceOnly` accessibility class, matching production. In a
/// headless CI keychain without a proper search list, SecItemAdd can fail with
/// `errSecMissingEntitlement`; the guard tests then report a skip rather than a
/// false failure -- a skipped keychain test is visible in the summary, a faked
/// pass is not.
final class SessionVaultTests: XCTestCase {
    private let endpoint = "http://127.0.0.1:18999"

    override func tearDown() {
        SessionVault.clear(endpoint: endpoint)
        super.tearDown()
    }

    private func withRealKeychain(_ body: () throws -> Void) throws {
        do {
            try body()
        } catch let failure as AppFailure where failure.message.contains("OSStatus") {
            throw XCTSkip("Keychain unavailable in this environment: \(failure.message)")
        }
    }

    func testStoresAndReadsBothHalves() throws {
        try withRealKeychain {
            try SessionVault.store(access: "access-token-1", refresh: "refresh-token-1", endpoint: endpoint)
            XCTAssertEqual(SessionVault.readAccess(endpoint: endpoint), "access-token-1")
            XCTAssertEqual(SessionVault.readRefresh(endpoint: endpoint), "refresh-token-1")
        }
    }

    func testRotationReplacesBothHalves() throws {
        try withRealKeychain {
            try SessionVault.store(access: "a1", refresh: "r1", endpoint: endpoint)
            try SessionVault.store(access: "a2", refresh: "r2", endpoint: endpoint)
            XCTAssertEqual(SessionVault.readAccess(endpoint: endpoint), "a2")
            XCTAssertEqual(SessionVault.readRefresh(endpoint: endpoint), "r2")
        }
    }

    func testClearRemovesBothHalves() throws {
        try withRealKeychain {
            try SessionVault.store(access: "a1", refresh: "r1", endpoint: endpoint)
            SessionVault.clear(endpoint: endpoint)
            XCTAssertNil(SessionVault.readAccess(endpoint: endpoint))
            XCTAssertNil(SessionVault.readRefresh(endpoint: endpoint))
            SessionVault.clear(endpoint: endpoint)  // idempotent
        }
    }

    func testEndpointIsPartOfTheCredentialScope() throws {
        try withRealKeychain {
            try SessionVault.store(access: "a1", refresh: "r1", endpoint: endpoint)
            XCTAssertNil(SessionVault.readAccess(endpoint: "http://127.0.0.1:19000"),
                         "a credential stored for one origin must not be served to another")
        }
    }

    func testNilRefreshDropsAnyStaleRefreshCredential() throws {
        try withRealKeychain {
            try SessionVault.store(access: "a1", refresh: "r1", endpoint: endpoint)
            try SessionVault.store(access: "a2", refresh: nil, endpoint: endpoint)
            XCTAssertEqual(SessionVault.readAccess(endpoint: endpoint), "a2")
            XCTAssertNil(SessionVault.readRefresh(endpoint: endpoint))
        }
    }

    func testRefusesToStoreAnEmptyAccessToken() {
        XCTAssertThrowsError(try SessionVault.store(access: "", refresh: nil, endpoint: endpoint))
        XCTAssertNil(SessionVault.readAccess(endpoint: endpoint))
    }
}
