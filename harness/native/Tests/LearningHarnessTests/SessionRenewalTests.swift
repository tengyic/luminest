import XCTest
@testable import LearningHarness

/// B8: "registration succeeded, the database has the account, but the app stays on the
/// authentication screen."
///
/// The measured cause was not navigation. The server issued a 1-hour access token and a
/// 60-day refresh token; the client kept only the access half, so when a host sleep
/// crossed the TTL, `record(401)` called `logout()` and the learner was sent back to a
/// freshly built auth form. These tests drive that state machine deterministically —
/// no network, no one-hour wait — by substituting only the `/auth/refresh` exchange.
@MainActor
final class SessionRenewalTests: XCTestCase {
    private let endpoint = "http://127.0.0.1:18998"
    private var store: AppStore!
    private var savedEndpoint: String?

    /// Mutable state captured by the async exchange closure. A class box keeps the
    /// counters visible to the assertions without making the closure itself @Sendable.
    private final class ExchangeLog {
        var calls = 0
        var seenEndpoint: String?
        var seenRefresh: String?
    }

    override func setUp() {
        super.setUp()
        savedEndpoint = UserDefaults.standard.string(forKey: "luminfest.endpoint")
        SessionVault.clear(endpoint: endpoint)
        SecureSession.remove(endpoint: endpoint)
        // No bundled backend, no restore, no timer-driven network work from init().
        store = AppStore(startBundledBackend: false)
        store.endpoint = endpoint
        store.api.endpoint = endpoint
        store.user = .object(["id": .string("learner-b8")])
        store.api.token = "expired-access"
        // The replay is the last thing refreshSession() does. Pin it to a no-op so the
        // test never issues real requests to a port nothing listens on.
        store.retryAction = { }
    }

    override func tearDown() {
        store?.shutdown()
        store = nil
        SessionVault.clear(endpoint: endpoint)
        SecureSession.remove(endpoint: endpoint)
        SessionVault.clear(endpoint: "http://127.0.0.1:18997")
        if let savedEndpoint {
            UserDefaults.standard.set(savedEndpoint, forKey: "luminfest.endpoint")
        } else {
            UserDefaults.standard.removeObject(forKey: "luminfest.endpoint")
        }
        super.tearDown()
    }

    /// Real Keychain, matching SessionVaultTests. A headless CI keychain reports a skip
    /// rather than a fabricated green.
    private func seed(access: String = "expired-access", refresh: String = "refresh-1") throws {
        do {
            try SessionVault.store(access: access, refresh: refresh, endpoint: endpoint)
        } catch let failure as AppFailure where failure.message.contains("OSStatus") {
            throw XCTSkip("Keychain unavailable in this environment: \(failure.message)")
        }
    }

    private func exchange(returning token: String, rotated: String, log: ExchangeLog)
        -> (String, String) async throws -> JSON {
        { origin, refresh in
            log.calls += 1
            log.seenEndpoint = origin
            log.seenRefresh = refresh
            return .object(["token": .string(token), "refresh_token": .string(rotated)])
        }
    }

    func testExpiredAccessRenewsWithoutSigningOut() async throws {
        try seed()
        let log = ExchangeLog()
        store.sessionRefreshExchange = exchange(returning: "fresh-access", rotated: "refresh-2", log: log)
        let epochBefore = store.epoch

        store.record(AppFailure(message: "Invalid or expired token", status: 401))
        // Let the single-flight Task run on the main actor.
        try await Task.sleep(nanoseconds: 250_000_000)

        XCTAssertTrue(store.authenticated, "an expired access token must not sign the learner out")
        XCTAssertEqual(store.epoch, epochBefore, "changing epoch would silently discard in-flight replies")
        XCTAssertEqual(log.calls, 1)
        XCTAssertEqual(log.seenEndpoint, endpoint)
        XCTAssertEqual(log.seenRefresh, "refresh-1")
        XCTAssertEqual(store.api.token, "fresh-access")
        XCTAssertNil(store.errorStatus)
        XCTAssertNil(store.error)
        XCTAssertEqual(SessionVault.readAccess(endpoint: endpoint), "fresh-access")
        XCTAssertEqual(SessionVault.readRefresh(endpoint: endpoint), "refresh-2",
                       "the rotated refresh half must replace the consumed one")
    }

    func testFourConcurrent401sTriggerExactlyOneExchange() async throws {
        try seed()
        let log = ExchangeLog()
        store.sessionRefreshExchange = exchange(returning: "fresh-access", rotated: "refresh-2", log: log)

        // refresh() issues /dashboard, /curriculum, /courses and /plan with the same
        // expired bearer. Rotating four times would invalidate three of the exchanges.
        for _ in 0..<4 { store.record(AppFailure(message: "Invalid or expired token", status: 401)) }
        try await Task.sleep(nanoseconds: 250_000_000)

        XCTAssertEqual(log.calls, 1, "the server rotates the refresh token on first use")
        XCTAssertTrue(store.authenticated)
    }

    func test403NeitherRenewsNorSignsOut() async throws {
        try seed()
        let log = ExchangeLog()
        store.sessionRefreshExchange = exchange(returning: "fresh-access", rotated: "refresh-2", log: log)

        store.record(AppFailure(message: "A Beta invite code is required", status: 403))

        XCTAssertEqual(log.calls, 0, "403 is forbidden, not an expired credential")
        XCTAssertTrue(store.authenticated)
        XCTAssertEqual(store.errorStatus, 403)
        XCTAssertEqual(store.api.token, "expired-access", "no exchange means the token is untouched")
    }

    func testFailedExchangeSignsOutAndClearsBothHalves() async throws {
        try seed()
        store.sessionRefreshExchange = { _, _ in
            throw AppFailure(message: "Refresh token is invalid, expired or already used", status: 401)
        }

        await store.refreshSession()

        XCTAssertFalse(store.authenticated)
        XCTAssertNil(store.api.token)
        XCTAssertNil(SessionVault.readAccess(endpoint: endpoint))
        XCTAssertNil(SessionVault.readRefresh(endpoint: endpoint))
        XCTAssertEqual(store.errorStatus, 401)
        XCTAssertEqual(store.error, "Your session expired. Please sign in again.")
    }

    func testNoRefreshCredentialStillSignsOut() async {
        SessionVault.clear(endpoint: endpoint)
        let log = ExchangeLog()
        store.sessionRefreshExchange = exchange(returning: "fresh-access", rotated: "refresh-2", log: log)

        await store.refreshSession()

        XCTAssertEqual(log.calls, 0, "there is nothing to exchange")
        XCTAssertFalse(store.authenticated, "a legacy single-token session cannot be renewed")
        XCTAssertNil(store.api.token)
    }

    func testLogoutClearsBothHalves() throws {
        try seed()
        store.logout()
        XCTAssertNil(SessionVault.readAccess(endpoint: endpoint))
        XCTAssertNil(SessionVault.readRefresh(endpoint: endpoint))
        XCTAssertNil(SecureSession.read(endpoint: endpoint))
    }

    func testChangeEndpointDoesNotLeaveOldOriginCredentials() throws {
        try seed()
        let other = "http://127.0.0.1:18997"
        XCTAssertNoThrow(try store.changeEndpoint(other))
        XCTAssertNil(SessionVault.readAccess(endpoint: endpoint))
        XCTAssertNil(SessionVault.readRefresh(endpoint: endpoint),
                     "credentials are scoped by origin and must not survive a server switch")
        XCTAssertNil(SessionVault.readAccess(endpoint: other))
    }
}
