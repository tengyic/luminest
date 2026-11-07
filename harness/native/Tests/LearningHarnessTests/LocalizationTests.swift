import XCTest
@testable import LearningHarness

/// Guards the two things that silently break a bilingual app:
/// a `.lproj` that stops resolving (the switch then "works" but changes nothing), and a
/// translation table that drifts from the development language.
///
/// These are not smoke tests. Each one fails on a specific, plausible regression:
/// - renaming `Resources/zh-Hans.lproj` (SwiftPM canonicalises to `zh-hans.lproj`)
/// - adding an English key without its Chinese counterpart
/// - pasting English into the Chinese table to make the build pass
final class LocalizationTests: XCTestCase {

    // MARK: - Bundle layout

    func testBothLanguageFoldersShip() {
        let locales = Localization.availableLocalizations().map { $0.lowercased() }
        XCTAssertTrue(locales.contains("en"),
                      "en.lproj missing from the resource bundle; got \(locales)")
        XCTAssertTrue(locales.contains("zh-hans"),
                      "zh-hans.lproj missing from the resource bundle; got \(locales)")
    }

    /// The folder on disk is `zh-hans.lproj` even though the tag is `zh-Hans`. This
    /// asserts the case-insensitive resolution, which is the difference between a working
    /// language switch and one that silently falls back to English.
    func testSimplifiedChineseResolvesCaseInsensitively() {
        let table = Localization.table(for: .simplifiedChinese)
        XCTAssertFalse(table.isEmpty,
                       "zh-Hans table did not load. The .lproj lookup is case-sensitive somewhere it should not be.")
        XCTAssertEqual(table["nav.today"], "今日")
    }

    // MARK: - Table integrity

    func testTablesHaveIdenticalKeys() {
        let en = Localization.table(for: .english)
        let zh = Localization.table(for: .simplifiedChinese)
        XCTAssertFalse(en.isEmpty, "English table failed to load")
        XCTAssertFalse(zh.isEmpty, "zh-Hans table failed to load")

        let missingInChinese = Set(en.keys).subtracting(zh.keys).sorted()
        let missingInEnglish = Set(zh.keys).subtracting(en.keys).sorted()
        XCTAssertTrue(missingInChinese.isEmpty,
                      "keys present in en.lproj but missing in zh-Hans: \(missingInChinese)")
        XCTAssertTrue(missingInEnglish.isEmpty,
                      "keys present in zh-Hans but missing in en.lproj: \(missingInEnglish)")
    }

    func testNoBlankTranslations() {
        for language in [AppLanguage.english, .simplifiedChinese] {
            let table = Localization.table(for: language)
            let blank = table.filter {
                $0.value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            }
            XCTAssertTrue(blank.isEmpty,
                          "\(language.rawValue) has blank values: \(blank.keys.sorted())")
        }
    }

    /// A table that merely copies English would pass every structural check above and
    /// still ship an untranslated app. These keys are chosen because a real translation
    /// cannot coincide with the English string.
    func testChineseTableIsActuallyTranslated() {
        let en = Localization.table(for: .english)
        let zh = Localization.table(for: .simplifiedChinese)
        for key in ["nav.today", "state.offline.title", "action.retry",
                    "settings.appearance.dark", "language.title"] {
            guard let english = en[key], let chinese = zh[key] else {
                XCTFail("key \(key) missing from one table")
                continue
            }
            XCTAssertNotEqual(chinese, english,
                              "\(key) is identical in both tables — untranslated placeholder")
        }
    }

    /// Surfaces may ship their own table instead of appending to one catalogue, so that
    /// two screens can be localised concurrently without editing the same file. That
    /// freedom is only safe if the table *set* and the keys inside each table still match
    /// across languages — otherwise a screen silently falls back to its key name.
    func testEveryTableMatchesAcrossLanguages() {
        let english = Localization.tableNames(for: .english)
        let chinese = Localization.tableNames(for: .simplifiedChinese)
        XCTAssertFalse(english.isEmpty, "no .strings tables found in en.lproj")
        XCTAssertEqual(english, chinese,
                       "the two language folders ship different table sets")
        for name in english {
            let en = Localization.table(named: name, for: .english)
            let zh = Localization.table(named: name, for: .simplifiedChinese)
            XCTAssertEqual(Set(en.keys), Set(zh.keys),
                           "table \(name).strings has drifted between en and zh-Hans")
        }
    }

    // MARK: - Runtime behaviour

    /// The whole point of resolving the `.lproj` ourselves: changing the selection changes
    /// lookups immediately, with no relaunch and no view rebuild.
    @MainActor
    func testSwitchingLanguageChangesLookupImmediately() {
        let store = Localization.shared
        let original = store.language
        defer { store.set(original) }

        store.set(.simplifiedChinese)
        XCTAssertEqual(L10n.t("nav.today"), "今日")
        XCTAssertEqual(L10n.t("action.retry"), "重试")

        store.set(.english)
        XCTAssertEqual(L10n.t("nav.today"), "Today")
        XCTAssertEqual(L10n.t("action.retry"), "Try Again")
    }

    /// A missing key must surface as the key itself. An empty button is unreportable in a
    /// screenshot review; a literal `nav.whatever` is greppable and obviously wrong.
    func testMissingKeySurfacesTheKey() {
        XCTAssertEqual(L10n.t("luminest.key.that.does.not.exist"),
                       "luminest.key.that.does.not.exist")
    }

    @MainActor
    func testFormattingUsesTheSelectedLanguage() {
        let store = Localization.shared
        let original = store.language
        defer { store.set(original) }

        store.set(.simplifiedChinese)
        let chinese = store.language.locale.identifier
        XCTAssertEqual(chinese, "zh-Hans")

        store.set(.english)
        let english = store.language.locale.identifier
        XCTAssertEqual(english, "en")
    }
}
