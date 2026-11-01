import XCTest
@testable import LearningHarness

/// Lumi is mostly timing, and timing is hard to test in a view. The parts that *can* be
/// pinned are the tables the animation is built from: a mood that silently falls back to
/// idle, or a gesture that holds a frame long enough to read as a pose, would both look
/// fine in a screenshot and wrong in use.
@MainActor
final class LumiCompanionTests: XCTestCase {
    func testEveryMoodMapsToItsOwnSprite() {
        for mood in LumiMood.allCases {
            XCTAssertEqual(LumiSprite(mood: mood).rawValue, mood.rawValue,
                           "\(mood) must not fall back to idle — a missing sprite is a silent expression change")
        }
    }

    func testBlinkIsASpriteButNotAMood() {
        XCTAssertTrue(LumiSprite.allCases.contains(.blink))
        XCTAssertNil(LumiMood(rawValue: "blink"), "a blink is a frame, not a state to sit in")
    }

    func testEveryActionHasStepsAndStaysTransient() {
        for action in LumiAction.allCases {
            let steps = action.steps
            XCTAssertFalse(steps.isEmpty, "\(action) has no choreography")

            for step in steps {
                XCTAssertTrue(step.hold.isFinite, "\(action) has a non-finite hold")
                XCTAssertGreaterThanOrEqual(step.hold, 0)
                XCTAssertLessThanOrEqual(step.hold, 1.2,
                                         "\(action) holds one frame too long to read as a gesture")
            }
            XCTAssertLessThan(steps.map(\.hold).reduce(0, +), 1.6,
                              "\(action) runs long enough to be mistaken for a mood")
        }
    }

    func testBlinkIsFastEnoughToBeABlink() {
        let total = LumiAction.blink.steps.map(\.hold).reduce(0, +)
        XCTAssertLessThan(total, 0.2, "a blink slower than 200ms reads as a squint")
    }

    func testGreetingEndsOnTheWaveSoTheControllerRestoresTheMood() {
        // The controller always returns to `LumiSprite(mood:)` after a script. If the
        // greeting script ended on idle, the wave would be replaced twice in one frame
        // and the restore would look like a flicker.
        XCTAssertEqual(LumiAction.greet.steps.last?.sprite, .greeting)
    }

    func testDeformationStaysSubtle() {
        // A squash/stretch outside roughly ±8% stops reading as breathing and starts
        // reading as a cartoon boing, which is the wrong register for this product.
        for action in LumiAction.allCases {
            for step in action.steps {
                XCTAssertGreaterThanOrEqual(step.squash, 0.9, "\(action) crouches too far")
                XCTAssertLessThanOrEqual(step.squash, 1.08, "\(action) stretches too far")
                XCTAssertLessThanOrEqual(abs(step.rise), 8, "\(action) lifts off the ground")
                XCTAssertLessThanOrEqual(abs(step.tilt), 4, "\(action) tilts past a lean")
            }
        }
    }

    func testGreetingFollowsTheClock() throws {
        var components = DateComponents()
        components.year = 2026; components.month = 10; components.day = 22
        let calendar = Calendar.current

        components.hour = 8
        let morning = try XCTUnwrap(calendar.date(from: components))
        XCTAssertTrue(LumiCompanion.greeting(at: morning).hasPrefix("Morning"))

        components.hour = 14
        let afternoon = try XCTUnwrap(calendar.date(from: components))
        XCTAssertTrue(LumiCompanion.greeting(at: afternoon).hasPrefix("Afternoon"))

        components.hour = 21
        let evening = try XCTUnwrap(calendar.date(from: components))
        XCTAssertTrue(LumiCompanion.greeting(at: evening).hasPrefix("Evening"))
    }

    func testAffirmationsAreOnBrand() {
        // The brand forbids streak language outright (01_BRAND_TRAITS.md §A4). This is a
        // cheap guard against someone adding "Keep your streak alive!" later.
        let banned = ["streak", "don't break", "perfect", "amazing", "crush"]
        for line in LumiCompanion.affirmations {
            for word in banned {
                XCTAssertFalse(line.lowercased().contains(word), "off-brand line: \(line)")
            }
        }
    }
}
