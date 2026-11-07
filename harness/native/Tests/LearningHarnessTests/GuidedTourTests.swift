import XCTest
@testable import LearningHarness

/// The walkthrough is only as good as its anchors and its copy.
///
/// Both failure modes are silent: an anchor id that no view publishes makes the tour
/// degrade to a centred card with nothing highlighted — it still "works", so nothing
/// reports it; and a missing string renders its key name, which looks like a bug in the
/// tour rather than a missing translation.
final class GuidedTourTests: XCTestCase {

    func testEveryAnchorMatchesARealDestination() {
        let pages = Set(Page.allCases.map { "nav.\($0.rawValue)" })
        for step in GuidedTour.steps {
            XCTAssertTrue(pages.contains(step.id),
                          "step \(step.id) does not correspond to any Page case, so no view publishes that anchor")
        }
    }

    func testAnchorIDsAreUnique() {
        let ids = GuidedTour.steps.map(\.id)
        XCTAssertEqual(ids.count, Set(ids).count, "two steps point at the same control: \(ids)")
    }

    func testTheTourHasSteps() {
        XCTAssertFalse(GuidedTour.steps.isEmpty, "an empty tour would dim the window and say nothing")
    }

    /// Copy is checked against both tables, not just the development language: a tour that
    /// shows `tour.review.body` to a Chinese learner is indistinguishable from a crash in
    /// that card.
    func testEveryStepHasCopyInBothLanguages() {
        for language in [AppLanguage.english, .simplifiedChinese] {
            let table = Localization.table(for: language)
            for step in GuidedTour.steps {
                for key in [step.titleKey, step.bodyKey, "tour.next", "tour.done", "tour.skip",
                            "tour.counter", "tour.replay"] {
                    let value = table[key]
                    XCTAssertNotNil(value, "\(language.rawValue) is missing \(key)")
                    XCTAssertFalse(value?.isEmpty ?? true, "\(language.rawValue) has a blank value for \(key)")
                    XCTAssertNotEqual(value, key, "\(language.rawValue) renders the key name for \(key)")
                }
            }
        }
    }

    @MainActor
    func testCounterUsesTheSelectedLanguage() {
        let store = Localization.shared
        let original = store.language
        defer { store.set(original) }

        store.set(.english)
        XCTAssertEqual(L10n.tf("tour.counter", table: nil, 2, 4), "2 of 4")

        store.set(.simplifiedChinese)
        XCTAssertEqual(L10n.tf("tour.counter", table: nil, 2, 4), "第 2 步，共 4 步")
    }

    /// Replay must be reachable without relaunching: it is the only recovery path for a
    /// learner who skipped by accident.
    func testReplayNotificationIsDistinct() {
        XCTAssertEqual(GuidedTour.replayNotification.rawValue, "luminest.guidedTour.replay")
    }
}
