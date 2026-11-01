import Foundation
import Security

/// The OpenAI Realtime API key, held in the macOS Keychain so it never lives in
/// UserDefaults, logs, or the process environment. The native client connects
/// *directly* to OpenAI; the backend key (``HARNESS_REALTIME_KEY``) is optional and
/// only used by a future server proxy. The key is read at connect time, so duplex
/// voice needs no backend configuration to work.
enum RealtimeKey {
    private static let service = "com.luminfest.learning-harness.realtime"
    private static let account = "openai-realtime"

    /// The stored key, or `nil` when none has been entered.
    static func load() -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data, let string = String(data: data, encoding: .utf8) else { return nil }
        let trimmed = string.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    /// Persist the key. Replaces any previous value. Fails loudly rather than silently
    /// dropping the key, because a missing key would make duplex voice look broken.
    static func save(_ key: String) throws {
        remove()
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecValueData as String: Data(key.utf8),
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        ]
        let status = SecItemAdd(query as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw AppFailure(message: "Keychain could not save the API key (\(status)).", status: nil)
        }
    }

    static func remove() {
        SecItemDelete([
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ] as CFDictionary)
    }

    /// Whether duplex voice can start: a non-empty key is stored.
    static var isConfigured: Bool { load() != nil }
}
