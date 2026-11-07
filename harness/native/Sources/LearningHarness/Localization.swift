import Foundation
import SwiftUI
import Combine

/// The languages this build ships.
///
/// `.system` follows macOS. The two explicit cases exist because "follow the system"
/// is not the same request as "show me this screen in Chinese on an English Mac":
/// a school laptop is frequently set to English for the operator and read in Chinese
/// by the learner. Choosing a language therefore has to be a decision the app can
/// carry, not something the OS decides once at launch.
enum AppLanguage: String, CaseIterable, Identifiable {
    case system
    case english = "en"
    case simplifiedChinese = "zh-Hans"

    var id: String { rawValue }

    /// The `.lproj` folder to load, or `nil` when the system decides.
    var lproj: String? {
        switch self {
        case .system: return nil
        case .english: return "en"
        case .simplifiedChinese: return "zh-Hans"
        }
    }

    /// Locale used for dates, numbers and measurements, not just words.
    var locale: Locale {
        switch self {
        case .system: return .autoupdatingCurrent
        case .english: return Locale(identifier: "en")
        case .simplifiedChinese: return Locale(identifier: "zh-Hans")
        }
    }

    /// The language's own name. A picker that renders every option in the *current*
    /// interface language is unreadable to exactly the person who needs it: someone who
    /// cannot read the current language. So each option is written in itself.
    var endonym: String {
        switch self {
        case .system: return ""          // supplied by the localization table
        case .english: return "English"
        case .simplifiedChinese: return "简体中文"
        }
    }
}

/// Runtime localization with an in-app switch.
///
/// Why not `.environment(\.locale)` alone: SwiftUI's locale environment changes how
/// `Text("literal")` is *looked up* in the main bundle, but a SwiftPM resource bundle
/// resolves against the process locale, so switching the environment re-renders the
/// chrome while leaving every `LocalizedStringKey` on the launch language. Resolving the
/// `.lproj` bundle ourselves and reading through it is the only arrangement where the
/// whole interface moves together, immediately, without a relaunch.
@MainActor
final class Localization: ObservableObject {
    static let shared = Localization()

    /// Kept under the same `luminfest.` prefix as the app's other preferences. The
    /// prefix is an internal storage key, not a brand: renaming it would silently reset
    /// every existing user's endpoint, streaming and window preferences.
    private static let defaultsKey = "luminfest.language"

    @Published private(set) var language: AppLanguage
    private(set) var bundle: Bundle

    private init() {
        let stored = UserDefaults.standard.string(forKey: Self.defaultsKey)
        let resolved = stored.flatMap(AppLanguage.init(rawValue:)) ?? .system
        language = resolved
        bundle = Self.bundle(for: resolved)
    }

    /// Switch language. Publishes immediately, so every view that reads `L10n.t`
    /// re-renders on the next run loop pass — no relaunch, no window rebuild.
    func set(_ value: AppLanguage) {
        guard value != language else { return }
        language = value
        bundle = Self.bundle(for: value)
        UserDefaults.standard.set(value.rawValue, forKey: Self.defaultsKey)
        objectWillChange.send()
    }

    /// Every `.lproj` present in this build, so a test can assert the two tables agree.
    nonisolated static func availableLocalizations() -> [String] {
        AppResources.bundle.localizations.sorted()
    }

    /// The raw table for one language, independent of the current selection.
    ///
    /// Exists so a test can compare the two tables without switching the live store —
    /// a parity check that ran through `set(_:)` would leave the process in whatever
    /// language the last test chose.
    nonisolated static func table(for language: AppLanguage) -> [String: String] {
        table(named: "Localizable", for: language)
    }

    /// One named table. Surfaces may ship their own (“Studio.strings”, “Flashcards.strings”)
    /// instead of appending to one growing catalogue, so two people localising two screens
    /// never edit the same file.
    nonisolated static func table(named name: String, for language: AppLanguage) -> [String: String] {
        let chosen = bundle(for: language)
        guard let path = chosen.path(forResource: name, ofType: "strings"),
              let table = NSDictionary(contentsOfFile: path) as? [String: String] else {
            return [:]
        }
        return table
    }

    /// Every `.strings` table present in one language folder.
    nonisolated static func tableNames(for language: AppLanguage) -> [String] {
        let chosen = bundle(for: language)
        let directory = chosen.resourceURL ?? chosen.bundleURL
        let files = (try? FileManager.default.contentsOfDirectory(atPath: directory.path)) ?? []
        return files
            .filter { $0.hasSuffix(".strings") }
            .map { String($0.dropLast(".strings".count)) }
            .sorted()
    }

    nonisolated private static func bundle(for language: AppLanguage) -> Bundle {
        // `.system` means "let the process locale decide", which is exactly what the
        // resource bundle already does. Resolved through ``AppResources`` even here: the
        // generated accessor is the one code path in this app that can call `fatalError`
        // at launch, and a language preference must not be able to kill the window.
        guard let requested = language.lproj else { return AppResources.bundle }
        // SwiftPM canonicalises `.lproj` names to lower-case BCP-47 (`zh-hans.lproj`)
        // while the tag we ask for is the conventional `zh-Hans`. A case-sensitive
        // `path(forResource:)` therefore misses and silently falls back to the
        // development language — the switch would appear to do nothing at all. Resolve
        // against the bundle's own list, case-insensitively, and only then look up.
        // The generated accessor is the other reason the bundle is resolved through
        // ``AppResources``: it looks beside `Bundle.main.bundleURL` (the `.app` directory,
        // not `Contents/Resources`) and then at an absolute path on the build machine,
        // while `package.py` stages the bundle at
        // `Contents/Resources/<Package>_<Target>.bundle`. Neither candidate exists on a
        // user's Mac, so it aborts — invisibly under `swift build`, which resolves from
        // `.build`. `AppResources` documents the same failure for artwork.
        let available = AppResources.bundle.localizations
        let match = available.first { $0.caseInsensitiveCompare(requested) == .orderedSame }
            ?? requested
        guard let path = AppResources.bundle.path(forResource: match, ofType: "lproj"),
              let chosen = Bundle(path: path) else {
            // A build that lost the folder: fall back to the resources bundle, which
            // resolves through the process locale. Never crash on a missing translation —
            // a readable English string beats a blank screen.
            return AppResources.bundle
        }
        return chosen
    }

    /// A missing key returns the key itself. That is deliberate: a half-translated
    /// screen shows `settings.appearance.dark` instead of an empty button, which is
    /// ugly but diagnosable, and it makes the gap greppable in QA.
    func t(_ key: String, table: String? = nil) -> String {
        bundle.localizedString(forKey: key, value: key, table: table)
    }

    /// Format variant for strings with positional arguments.
    func tf(_ key: String, _ args: [CVarArg]) -> String {
        String(format: t(key), arguments: args)
    }
}

/// Call-site shim so views read `L10n.t("key")` rather than touching the store.
enum L10n {
    static func t(_ key: String, table: String? = nil) -> String {
        if Thread.isMainThread {
            return MainActor.assumeIsolated { Localization.shared.t(key, table: table) }
        }
        return AppResources.bundle.localizedString(forKey: key, value: key, table: table)
    }

    static func tf(_ key: String, _ args: CVarArg...) -> String {
        let template = t(key)
        return String(format: template, arguments: args)
    }
}
