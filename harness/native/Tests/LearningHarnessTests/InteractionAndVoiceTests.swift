import XCTest
@testable import LearningHarness

/// The interaction channel and the voice-activity detector are both pure enough to pin, and
/// both have a failure mode that a code review would miss: a target that quietly becomes
/// prose, and a threshold that silently stops working in a different room.
///
/// What these tests do not do is judge whether the conversation *feels* natural. That is a
/// listening decision made with a microphone in a real room. What is pinned here is the
/// grammar the backend will accept and the arithmetic that decides "they stopped talking".
final class InteractionTargetTests: XCTestCase {
    /// The backend's pattern, mirrored. If these two ever disagree the client records taps the
    /// server rejects, and the flush retries a batch that can never succeed.
    func testControlIdentifiersAreAccepted() {
        for target in ["stage.tab.deck", "board.node.cell-theory", "question.option.a",
                       "page:studio", "voice.dictate"] {
            XCTAssertTrue(ClickTelemetry.isValidTarget(target), target)
        }
    }

    func testProseAndEmptyTargetsAreRefused() {
        for target in ["", "the learner opened the deck", "-leading", "tab with space",
                       String(repeating: "x", count: 65), "emoji🙂"] {
            XCTAssertFalse(ClickTelemetry.isValidTarget(target), target)
        }
    }

    func testSanitiseNeverProducesAnInvalidTarget() {
        for raw in ["Studio", "Today's plan", "", "  ", "a/b/c", "Ünïcode"] {
            let clean = ClickTelemetry.sanitise(raw)
            XCTAssertTrue(ClickTelemetry.isValidTarget(clean), "\(raw) -> \(clean)")
        }
    }

    func testSanitiseIsLowercaseAndStable() {
        XCTAssertEqual(ClickTelemetry.sanitise("Stage Deck"), "stage-deck")
        XCTAssertEqual(ClickTelemetry.sanitise("stage.tab.deck"), "stage.tab.deck")
    }
}

final class VoiceActivityDetectorTests: XCTestCase {
    func testQuietRoomDoesNotCountAsSpeech() {
        var detector = VoiceActivityDetector()
        for _ in 0..<20 { detector.observe(0.003) }
        XCTAssertFalse(detector.isVoiced(0.004))
    }

    func testSpeechOverAFanStillCounts() {
        var detector = VoiceActivityDetector()
        // A loud steady room: the floor rises, but a voice above it must still register.
        for _ in 0..<400 { detector.observe(0.03) }
        XCTAssertTrue(detector.isVoiced(0.10))
        XCTAssertFalse(detector.isVoiced(0.032))
    }

    func testTheFloorFallsFastAndRisesSlowly() {
        var detector = VoiceActivityDetector()
        for _ in 0..<200 { detector.observe(0.05) }
        let afterLoud = detector.isVoiced(0.02)
        for _ in 0..<10 { detector.observe(0.001) }
        // One quiet moment should not leave the detector deaf, and one loud moment should not
        // leave it shouting: that asymmetry is the whole design.
        XCTAssertFalse(afterLoud)
        XCTAssertTrue(detector.isVoiced(0.02))
    }

    func testBargeInNeedsMoreThanOrdinarySpeech() {
        var detector = VoiceActivityDetector()
        for _ in 0..<200 { detector.observe(0.002) }
        let ordinary = 0.03
        XCTAssertTrue(detector.isVoiced(ordinary))
        XCTAssertFalse(detector.isVoiced(ordinary, marginMultiplier: 2.4),
                       "speaker echo at ordinary speech level must not interrupt the tutor")
        XCTAssertTrue(detector.isVoiced(0.12, marginMultiplier: 2.4))
    }

    func testResetReturnsToTheDefaultFloor() {
        var detector = VoiceActivityDetector()
        for _ in 0..<300 { detector.observe(0.08) }
        detector.reset()
        XCTAssertFalse(detector.isVoiced(0.002))
        XCTAssertTrue(detector.isVoiced(0.05))
    }
}

/// The voice picker resolves to two strings that ride on *every* speech request. These
/// tests pin the client's built-in fallback against the backend's ``VOICE_PRESETS`` ids
/// and the pure resolution rule, without booting an AppStore (which starts a timer and
/// binds the shared API client).
final class VoiceOptionTests: XCTestCase {
    func testBuiltInMirrorsTheServerPresets() {
        let ids = VoiceOption.builtIn.map(\.id)
        XCTAssertEqual(ids, ["default", "warm_teacher", "clear_narrator",
                             "friendly_tutor", "calm_explainer", "energetic_coach",
                             "mandarin_teacher", "custom"])
        XCTAssertEqual(Set(ids).count, ids.count, "a duplicate id makes the picker ambiguous")
        for option in VoiceOption.builtIn {
            XCTAssertFalse(option.label.isEmpty)
        }
    }

    func testDefaultAndCustomCarryNoProfileOrTone() {
        for id in ["default", "custom"] {
            let resolved = VoiceOption.resolve(id: id, custom: "", options: VoiceOption.builtIn)
            XCTAssertEqual(resolved.voice, "")
            XCTAssertEqual(resolved.tone, "")
        }
    }

    func testAPresetSendsItsToneAndNotAProfile() {
        let resolved = VoiceOption.resolve(id: "warm_teacher", custom: "ignored",
                                           options: VoiceOption.builtIn)
        XCTAssertEqual(resolved.voice, "")
        XCTAssertEqual(resolved.tone, "female, young adult, moderate pitch, british accent")
    }

    func testCustomSendsTheTrimmedProfileAndNoTone() {
        let resolved = VoiceOption.resolve(id: "custom", custom: "  my-mentor  ",
                                           options: VoiceOption.builtIn)
        XCTAssertEqual(resolved.voice, "my-mentor")
        XCTAssertEqual(resolved.tone, "")
    }

    func testAnUnknownSavedIdFallsBackToTheInstanceDefault() {
        let resolved = VoiceOption.resolve(id: "retired_preset", custom: "my-mentor",
                                           options: VoiceOption.builtIn)
        XCTAssertEqual(resolved.voice, "", "a renamed preset must not send a stale profile")
        XCTAssertEqual(resolved.tone, "", "nor a tone the operator did not choose")
    }
}
