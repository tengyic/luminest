import Foundation
import AppKit
import CryptoKit

/// Remote update check for the closed-beta bundle.
///
/// Deliberately conservative. The app is ad-hoc signed and NOT notarized, so a
/// silent self-replacement would be both dangerous and dishonest. This type only
/// does three things:
///   1. reads a small JSON manifest from the beta control server,
///   2. compares the published version with `CFBundleShortVersionString`,
///   3. verifies the SHA-256 of an archive the user downloaded themselves.
/// It never downloads an update in the background and never replaces the app.
///
/// Manifest URL resolution, in order:
///   * `LuminestUpdateManifestURL` in Info.plist (stamped by `package_beta.py`),
///   * `luminest.updateManifestURL` in UserDefaults (an operator can point an
///     already-shipped build at a server without re-signing),
///   * otherwise `.unconfigured` -- no network call is made. Fail-closed.
/// Only HTTPS is accepted, plus loopback HTTP for local device testing.
enum BetaUpdate {

    struct Artifact: Decodable {
        let name: String?
        let url: String
        let sha256: String
        let bytes: Int?
    }

    struct Manifest: Decodable {
        let product: String?
        let channel: String?
        let version: String
        let publishedAt: TimeInterval?
        let minMacOS: String?
        let artifacts: [Artifact]

        enum CodingKeys: String, CodingKey {
            case product, channel, version, artifacts
            case publishedAt = "published_at"
            case minMacOS = "min_macos"
        }

        init(from decoder: Decoder) throws {
            let box = try decoder.container(keyedBy: CodingKeys.self)
            product = try box.decodeIfPresent(String.self, forKey: .product)
            channel = try box.decodeIfPresent(String.self, forKey: .channel)
            version = try box.decode(String.self, forKey: .version)
            publishedAt = try box.decodeIfPresent(TimeInterval.self, forKey: .publishedAt)
            minMacOS = try box.decodeIfPresent(String.self, forKey: .minMacOS)
            artifacts = try box.decodeIfPresent([Artifact].self, forKey: .artifacts) ?? []
        }
    }

    enum Status {
        case current(version: String)
        case available(local: String, published: String, manifest: Manifest)
        case unconfigured
        case unreachable(reason: String)

        var summary: String {
            switch self {
            case .current(let v): return "up-to-date (\(v))"
            case .available(let local, let published, _): return "update available: \(local) → \(published)"
            case .unconfigured: return "update server not configured"
            case .unreachable(let reason): return "unreachable: \(reason)"
            }
        }
    }

    private static let infoKey = "LuminestUpdateManifestURL"
    private static let defaultsKey = "luminest.updateManifestURL"
    private static let statusKey = "luminest.updateStatus"

    static func manifestURL() -> URL? {
        let candidates = [
            Bundle.main.object(forInfoDictionaryKey: infoKey) as? String,
            UserDefaults.standard.string(forKey: defaultsKey),
        ]
        for raw in candidates.compactMap({ $0 }) {
            guard let url = URL(string: raw), let scheme = url.scheme?.lowercased() else { continue }
            let host = url.host?.lowercased() ?? ""
            let loopback = host == "127.0.0.1" || host == "localhost" || host == "::1"
            if scheme == "https" || (scheme == "http" && loopback) { return url }
        }
        return nil
    }

    /// The human-facing page for this server, derived from the manifest URL.
    static func landingURL() -> URL? {
        guard let url = manifestURL() else { return nil }
        var parts = URLComponents(url: url, resolvingAgainstBaseURL: false)
        parts?.path = "/"
        parts?.query = nil
        parts?.fragment = nil
        return parts?.url
    }

    static func localVersion() -> String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0"
    }

    /// Numeric-ish comparison, so `1.10` sorts after `1.9`. Non-numeric parts
    /// fall back to a lexicographic compare rather than pretending to know.
    static func isNewer(_ candidate: String, than local: String) -> Bool {
        let a = candidate.split(separator: ".").map(String.init)
        let b = local.split(separator: ".").map(String.init)
        for i in 0..<max(a.count, b.count) {
            let x = i < a.count ? a[i] : "0"
            let y = i < b.count ? b[i] : "0"
            if let xi = Int(x), let yi = Int(y) {
                if xi != yi { return xi > yi }
            } else if x != y {
                return x > y
            }
        }
        return false
    }

    static func check() async -> Status {
        guard let url = manifestURL() else { return .unconfigured }
        var request = URLRequest(url: url)
        request.timeoutInterval = 8
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                return .unreachable(reason: "not an HTTP response")
            }
            guard (200...299).contains(http.statusCode) else {
                return .unreachable(reason: "HTTP \(http.statusCode)")
            }
            let manifest = try JSONDecoder().decode(Manifest.self, from: data)
            let local = localVersion()
            return isNewer(manifest.version, than: local)
                ? .available(local: local, published: manifest.version, manifest: manifest)
                : .current(version: local)
        } catch {
            return .unreachable(reason: error.localizedDescription)
        }
    }

    /// Launch-time check: record the verdict, never interrupt the learner.
    static func checkOnLaunch() async {
        let status = await check()
        UserDefaults.standard.set(status.summary, forKey: statusKey)
    }

    /// Menu action: check and show a plain alert. Opening the download page is
    /// an explicit second action by the user, never an automatic install.
    @MainActor static func checkAndPresent() async {
        let status = await check()
        UserDefaults.standard.set(status.summary, forKey: statusKey)
        let alert = NSAlert()
        alert.messageText = "Luminest updates"
        switch status {
        case .current(let v):
            alert.informativeText = "You are on \(v), the current closed-beta build."
            alert.addButton(withTitle: "OK")
        case .available(let local, let published, let manifest):
            alert.informativeText = "Version \(published) is published; this app is \(local).\n\n" +
                "The update is not installed automatically. Verify the SHA-256 in SHA256SUMS.txt " +
                "before replacing the app. \(manifest.artifacts.count) artifact(s) listed."
            alert.addButton(withTitle: "Open download page")
            alert.addButton(withTitle: "Later")
        case .unconfigured:
            alert.informativeText = "No update server is configured for this build. " +
                "Set luminest.updateManifestURL or use the beta landing page."
            alert.addButton(withTitle: "OK")
        case .unreachable(let reason):
            alert.informativeText = "Could not check the update manifest: \(reason)"
            alert.addButton(withTitle: "OK")
        }
        let choice = alert.runModal()
        if choice == .alertFirstButtonReturn, case .available = status, let page = landingURL() {
            NSWorkspace.shared.open(page)
        }
    }

    /// Verify an archive the user downloaded themselves. Returns false on any
    /// mismatch; never throws the hash away silently.
    static func verifyDownloadedArchive(at fileURL: URL, expectedSHA256: String) throws -> Bool {
        let data = try Data(contentsOf: fileURL, options: .mappedIfSafe)
        let digest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        return digest.lowercased() == expectedSHA256.trimmingCharacters(in: .whitespaces).lowercased()
    }
}
