import XCTest
@testable import LearningHarness

/// The sound layer is maths, so it can be asserted like maths: length, loudness, and the
/// fact that the same voice renders the same samples twice.
///
/// What these tests deliberately do not do is judge whether a fanfare *sounds* like a
/// fanfare. That is a listening decision. What they pin is the envelope: a sound that runs
/// too long or too loud stops being a reward and becomes an interruption, and that is the
/// failure mode a code review would miss.
final class SoundSynthTests: XCTestCase {
    func testEveryVoiceRendersShortAndQuiet() {
        for voice in SoundVoice.allCases {
            let samples = SoundSynth.samples(for: voice)
            let seconds = Double(samples.count) / SoundSynth.sampleRate
            XCTAssertGreaterThan(seconds, 0.2, "\(voice) is too short to register")
            XCTAssertLessThanOrEqual(seconds, 1.3, "\(voice) is long enough to interrupt")
            let peak = samples.reduce(Float(0)) { max($0, abs($1)) }
            XCTAssertGreaterThan(peak, 0.05, "\(voice) is inaudible")
            XCTAssertLessThanOrEqual(peak, 0.27, "\(voice) is louder than a UI sound should be")
        }
    }

    func testTheSameVoiceRendersTheSameSamples() {
        // The noise in `sparkle` comes from a seeded generator on purpose: a UI sound that
        // differs on every launch cannot be compared in a screenshot or debugged.
        XCTAssertEqual(SoundSynth.samples(for: .sparkle), SoundSynth.samples(for: .sparkle))
    }

    func testTheWavContainerIsSixteenBitMonoPcm() {
        let data = SoundSynth.wav([0, 0.5, -0.5])
        XCTAssertEqual(String(decoding: data.prefix(4), as: UTF8.self), "RIFF")
        XCTAssertEqual(String(decoding: data[8..<12], as: UTF8.self), "WAVE")
        XCTAssertEqual(String(decoding: data[12..<16], as: UTF8.self), "fmt ")
        XCTAssertEqual(uint16(data, at: 20), 1, "format must be PCM")
        XCTAssertEqual(uint16(data, at: 22), 1, "channels must be mono")
        XCTAssertEqual(uint32(data, at: 24), 44_100, "sample rate")
        XCTAssertEqual(uint16(data, at: 34), 16, "bit depth")
        XCTAssertEqual(String(decoding: data[36..<40], as: UTF8.self), "data")
        XCTAssertEqual(uint32(data, at: 40), 6, "three 16-bit samples")
    }

    private func uint16(_ data: Data, at offset: Int) -> UInt16 {
        UInt16(data[offset]) | (UInt16(data[offset + 1]) << 8)
    }

    private func uint32(_ data: Data, at offset: Int) -> UInt32 {
        UInt32(data[offset]) | (UInt32(data[offset + 1]) << 8)
            | (UInt32(data[offset + 2]) << 16) | (UInt32(data[offset + 3]) << 24)
    }
}

/// The client half of the reward contract: show each id once, heaviest first, one at a time.
@MainActor
final class RewardCenterTests: XCTestCase {
    private var defaults: UserDefaults!
    private let suite = "rewards.tests"

    override func setUp() {
        super.setUp()
        defaults = UserDefaults(suiteName: suite)
        defaults.removePersistentDomain(forName: suite)
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suite)
        super.tearDown()
    }

    private func event(_ id: String, tier: String = "toast", kind: String = "badge") throws -> RewardEvent {
        let json = try JSON.make(["id": id, "kind": kind, "value": 5, "tier": tier,
                                  "mascot": "celebrating", "sound": "chime",
                                  "title": "Title", "announce": "Announce"])
        return try XCTUnwrap(RewardEvent(json))
    }

    func testTheHeaviestCeremonyIsPresentedFirstAndOneAtATime() throws {
        let center = RewardCenter(defaults: defaults)
        center.enqueue([try event("a", tier: "toast"),
                        try event("b", tier: "celebrate"),
                        try event("c", tier: "banner")])

        XCTAssertEqual(center.current?.id, "b", "a celebration must not queue behind a toast")
        center.dismiss()
        XCTAssertEqual(center.current?.id, "c")
        center.dismiss()
        XCTAssertEqual(center.current?.id, "a")
        center.dismiss()
        XCTAssertNil(center.current, "the queue must drain")
    }

    func testTheSameIdIsNeverShownTwice() throws {
        let center = RewardCenter(defaults: defaults)
        center.enqueue([try event("streak:2026-10-24:5")])
        center.dismiss()

        center.enqueue([try event("streak:2026-10-24:5")])
        XCTAssertNil(center.current, "a second poll must not re-celebrate the same achievement")
    }

    func testTheSeenSetSurvivesARelaunch() throws {
        let first = RewardCenter(defaults: defaults)
        first.enqueue([try event("node:fractions:0.8")])
        first.dismiss()

        let second = RewardCenter(defaults: defaults)
        second.enqueue([try event("node:fractions:0.8")])
        XCTAssertNil(second.current, "the seen-set is persisted, so a relaunch is not a reset")
    }

    func testAnEventWithoutAnIdIsRejected() throws {
        // The id is the idempotency key. An event without one could only ever be shown
        // repeatedly, so it is dropped rather than rendered.
        XCTAssertNil(RewardEvent(try JSON.make(["kind": "badge", "title": "No id"])))
    }

    func testAnUnknownTierStillPresents() throws {
        // A newer server may add a tier this build has never heard of. Falling back to the
        // lightest presentation is better than dropping the milestone entirely.
        let center = RewardCenter(defaults: defaults)
        center.enqueue([try event("future", tier: "parade")])
        XCTAssertEqual(center.current?.id, "future")
    }
}
