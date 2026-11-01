import Foundation
import Security

/// Keychain-backed storage for *both* halves of a session (audit finding E-1).
///
/// `SecureSession` in `Core.swift` already stores the access token in the Keychain
/// (`kSecAttrAccessibleWhenUnlockedThisDeviceOnly`), but the client dropped the
/// refresh token the server issues with every session, so the long half of the
/// credential never survived a relaunch and the rotation endpoint
/// (`POST /api/v1/auth/refresh`) was unreachable from the app.
///
/// `SessionVault` is the storage layer for the complete session: access and
/// refresh tokens each under their own Keychain account key, generic-password
/// class, never UserDefaults, never files. The tokens are stored as issued and
/// sent only over the origin they belong to (the endpoint is part of the lookup
/// key), so switching servers cannot replay a credential across origins.
///
/// **Integration note (blocked by file ownership, deliberately minimal):**
/// `Core.swift` is owned by another work stream in this cycle, so the one-line
/// wiring change is documented here instead of landed:
///
///     // AppStore.authenticate, after login/register succeed:
///     try? SessionVault.store(access: result["token"].string ?? "",
///                             refresh: result["refresh_token"].string, endpoint: origin)
///     // AppStore.restoreSession: prefer SessionVault.readAccess(endpoint:) and
///     // on 401 redeem SessionVault.readRefresh(endpoint:) via /auth/refresh,
///     // re-storing the rotated pair.
///     // AppStore.signOut / endpoint switch: SessionVault.clear(endpoint:)
///
/// Until that lands, `SecureSession` continues to store the access token and this
/// vault compiles and is tested independently of `AppStore`.
enum SessionVault {
    private static let service = "com.luminfest.learning-harness.session.vault"

    private enum Kind: String {
        case access
        case refresh
    }

    private static func account(_ kind: Kind, endpoint: String) -> String {
        kind.rawValue + ":" + endpoint
    }

    private static func baseQuery(_ kind: Kind, endpoint: String) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: service,
         kSecAttrAccount as String: account(kind, endpoint: endpoint)]
    }

    /// Store both halves of a session. The refresh token may be nil for servers
    /// that issue only an access token; an existing refresh credential is removed
    /// in that case so a stale one cannot outlive its session.
    static func store(access: String, refresh: String?, endpoint: String) throws {
        guard !access.isEmpty else {
            throw AppFailure(message: "Refusing to store an empty session token.", status: nil)
        }
        try write(access, kind: .access, endpoint: endpoint)
        if let refresh, !refresh.isEmpty {
            try write(refresh, kind: .refresh, endpoint: endpoint)
        } else {
            remove(.refresh, endpoint: endpoint)
        }
    }

    static func readAccess(endpoint: String) -> String? {
        read(.access, endpoint: endpoint)
    }

    static func readRefresh(endpoint: String) -> String? {
        read(.refresh, endpoint: endpoint)
    }

    /// Remove both halves for one endpoint. Idempotent.
    static func clear(endpoint: String) {
        remove(.access, endpoint: endpoint)
        remove(.refresh, endpoint: endpoint)
    }

    /// Mark the whole session compromised: called after a refresh rotation reports
    /// reuse, mirroring the server's revoke-the-session behaviour.
    static func clearAfterCompromise(endpoint: String) {
        clear(endpoint: endpoint)
    }

    // MARK: - SecItem plumbing

    private static func write(_ token: String, kind: Kind, endpoint: String) throws {
        SecItemDelete(baseQuery(kind, endpoint: endpoint) as CFDictionary)
        var attributes = baseQuery(kind, endpoint: endpoint)
        attributes[kSecValueData as String] = Data(token.utf8)
        attributes[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        let status = SecItemAdd(attributes as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw AppFailure(message: "Keychain could not store the \(kind.rawValue) token (OSStatus \(status)).", status: nil)
        }
    }

    private static func read(_ kind: Kind, endpoint: String) -> String? {
        var query = baseQuery(kind, endpoint: endpoint)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private static func remove(_ kind: Kind, endpoint: String) {
        SecItemDelete(baseQuery(kind, endpoint: endpoint) as CFDictionary)
    }
}
