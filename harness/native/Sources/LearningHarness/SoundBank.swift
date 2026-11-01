import AVFoundation
import Foundation

/// The five sounds a celebration can make.
///
/// The names are the wire vocabulary the backend sends in a reward event (`chime_soft`,
/// `chime`, `fanfare`, `sparkle`, `badge`), so a client never maps an event to a sound by
/// guessing. An unknown name is silence, not a failure.
enum SoundVoice: String, CaseIterable {
    case chimeSoft = "chime_soft"
    case chime
    case fanfare
    case sparkle
    case badge
}

/// Synthesized sound effects: no audio files, no licensing, no download.
///
/// The bundle ships no audio today, and adding produced sound would mean a licence check
/// per file - the same rule the image pipeline already enforces. These five are therefore
/// *rendered* at first use from a handful of oscillators: a few hundred lines of maths
/// instead of a few hundred kilobytes of asset, deterministic enough to test, and honest
/// about being UI sound rather than music.
///
/// Every recipe is deliberately short (0.35-1.2 s) and quiet (peak <= 0.26). A reward
/// chime that is loud or long stops being a reward and becomes an interruption.
enum SoundSynth {
    static let sampleRate: Double = 44_100

    // MARK: Recipes

    static func samples(for voice: SoundVoice) -> [Float] {
        switch voice {
        case .chimeSoft:
            return chime([1046.5, 1318.5], duration: 0.45, stagger: 0, amplitude: 0.20)
        case .chime:
            return chime([1046.5, 1318.5, 1568.0], duration: 0.70, stagger: 0.06, amplitude: 0.18)
        case .fanfare:
            return fanfare()
        case .sparkle:
            return sparkle()
        case .badge:
            return bell()
        }
    }

    /// Two or three struck sines, optionally staggered. The stagger is what turns a chord
    /// into an arpeggio and makes it read as "something happened" rather than "a tone".
    private static func chime(_ frequencies: [Double], duration: Double, stagger: Double,
                              amplitude: Float) -> [Float] {
        var buffer: [Float] = []
        for (index, frequency) in frequencies.enumerated() {
            addTone(&buffer, frequency: frequency, start: Double(index) * stagger,
                    duration: duration, amplitude: 0.6, decay: duration / 3.0)
        }
        return normalised(buffer, peak: amplitude)
    }

    /// A triangle arpeggio: C5-E5-G5-C6. Triangle rather than sine because the slight edge
    /// reads as brass at low volume, where a sine just reads as a test tone.
    private static func fanfare() -> [Float] {
        var buffer: [Float] = []
        let notes = [523.25, 659.25, 783.99, 1046.5]
        for (index, frequency) in notes.enumerated() {
            addTone(&buffer, frequency: frequency, start: Double(index) * 0.09,
                    duration: 0.9, amplitude: 0.5, decay: 0.30,
                    shape: { 2 / .pi * asin(sin($0)) })
        }
        return normalised(buffer, peak: 0.24)
    }

    /// Filtered noise with a rising cutoff plus three short high partials: a shimmer rather
    /// than a pitched note, which is what "sparkle" has to be.
    private static func sparkle() -> [Float] {
        let duration = 0.35
        var buffer = [Float](repeating: 0, count: Int(duration * sampleRate))
        var noise = Noise()
        var lowpass = 0.0
        for index in 0..<buffer.count {
            let t = Double(index) / sampleRate
            let progress = t / duration
            // One-pole lowpass whose coefficient opens across the burst: a cheap sweep.
            let coefficient = 0.10 + 0.80 * progress
            lowpass += coefficient * (noise.next() - lowpass)
            let envelope = exp(-t / (duration / 3))
            buffer[index] = Float(0.55 * lowpass * envelope)
        }
        for (index, frequency) in [2637.0, 3136.0, 3951.0].enumerated() {
            addTone(&buffer, frequency: frequency, start: Double(index) * 0.02,
                    duration: duration * 0.8, amplitude: 0.18, decay: 0.06)
        }
        return normalised(buffer, peak: 0.22)
    }

    /// An FM bell: a modulated carrier whose index decays faster than its amplitude, so the
    /// attack is bright and the tail is pure. The classic badge sound.
    private static func bell() -> [Float] {
        let duration = 1.0
        let carrier = 880.0
        let modulator = carrier * 1.4
        var buffer: [Float] = []
        buffer.reserveCapacity(Int(duration * sampleRate))
        for index in 0..<Int(duration * sampleRate) {
            let t = Double(index) / sampleRate
            let brightness = 2.0 * exp(-t / 0.35)
            let envelope = min(1.0, t / 0.006) * exp(-t / 0.50)
            let value = sin(2 * .pi * carrier * t + brightness * sin(2 * .pi * modulator * t))
            buffer.append(Float(0.5 * envelope * value))
        }
        addTone(&buffer, frequency: 2637, start: 0, duration: 0.5, amplitude: 0.12, decay: 0.18)
        addTone(&buffer, frequency: 3520, start: 0.02, duration: 0.4, amplitude: 0.08, decay: 0.14)
        return normalised(buffer, peak: 0.26)
    }

    // MARK: Primitives

    private static func addTone(_ into: inout [Float], frequency: Double, start: Double,
                               duration: Double, amplitude: Float, decay: Double,
                               shape: (Double) -> Double = { sin($0) }) {
        let first = Int(start * sampleRate)
        let count = Int(duration * sampleRate)
        guard count > 0 else { return }
        if into.count < first + count {
            into.append(contentsOf: Array(repeating: 0, count: first + count - into.count))
        }
        for index in 0..<count {
            let t = Double(index) / sampleRate
            // 8 ms attack: long enough not to click, short enough to still sound struck.
            let attack = min(1.0, t / 0.008)
            let envelope = attack * exp(-t / decay)
            // Split across three statements: one Float/Double mixed expression this deep
            // times out the type checker rather than failing to compile.
            let phase = 2 * Double.pi * frequency * t
            let value = shape(phase)
            let sample = Double(amplitude) * envelope * value
            into[first + index] += Float(sample)
        }
    }

    /// Scale so the loudest sample sits at `peak`. Summing oscillators otherwise drifts with
    /// the number of partials, and a fanfare would be twice as loud as a chime for no reason.
    private static func normalised(_ samples: [Float], peak: Float) -> [Float] {
        let loudest = samples.reduce(Float(0)) { max($0, abs($1)) }
        guard loudest > 0 else { return samples }
        let gain = peak / loudest
        return samples.map { $0 * gain }
    }

    /// Deterministic white noise (fixed-seed LCG).
    ///
    /// `Double.random` would make the sparkle different on every launch and the rendered
    /// buffer untestable; a seeded generator makes the same sound every time, which is what
    /// a UI sound should be anyway.
    private struct Noise {
        private var state: UInt64 = 0x9E37_79B9_7F4A_7C15
        mutating func next() -> Double {
            state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
            return Double(state >> 11) / Double(1 << 53) * 2 - 1
        }
    }

    // MARK: Container

    /// Wrap float samples in a 16-bit mono WAV container so `AVAudioPlayer` can take them.
    static func wav(_ samples: [Float]) -> Data {
        var data = Data()
        let channels: UInt16 = 1
        let bits: UInt16 = 16
        let blockAlign = channels * bits / 8
        let byteRate = UInt32(sampleRate) * UInt32(blockAlign)
        let payload = UInt32(samples.count * 2)

        func append32(_ value: UInt32) {
            withUnsafeBytes(of: value.littleEndian) { data.append(contentsOf: $0) }
        }
        func append16(_ value: UInt16) {
            withUnsafeBytes(of: value.littleEndian) { data.append(contentsOf: $0) }
        }

        data.append(contentsOf: Array("RIFF".utf8))
        append32(36 + payload)
        data.append(contentsOf: Array("WAVEfmt ".utf8))
        append32(16)
        append16(1)                       // PCM
        append16(channels)
        append32(UInt32(sampleRate))
        append32(byteRate)
        append16(blockAlign)
        append16(bits)
        data.append(contentsOf: Array("data".utf8))
        append32(payload)
        for sample in samples {
            let clamped = max(-1, min(1, sample))
            append16(UInt16(bitPattern: Int16((clamped * 32_767).rounded())))
        }
        return data
    }
}

/// Plays the synthesized sounds, once each, and remembers whether the learner wants them.
///
/// Rendering happens on first play and is cached, so the cost is paid the first time a
/// milestone lands rather than at launch. A failure to build a player (no output device,
/// audio service unavailable) is silent on purpose: a reward that throws an alert is worse
/// than a reward with no sound.
@MainActor
final class SoundBank {
    static let shared = SoundBank()

    private var cache: [SoundVoice: Data] = [:]
    /// Players are held until they finish; an `AVAudioPlayer` deallocated mid-playback
    /// stops. Six is more than can overlap, so old ones are dropped from the front.
    private var players: [AVAudioPlayer] = []

    private let enabledKey = "sound.rewards.enabled"

    var isEnabled: Bool {
        get { UserDefaults.standard.object(forKey: enabledKey) as? Bool ?? true }
        set { UserDefaults.standard.set(newValue, forKey: enabledKey) }
    }

    /// Play by wire name. An unknown name is silence, so a newer server cannot break an
    /// older client with a sound it has never heard of.
    func play(_ name: String) {
        guard let voice = SoundVoice(rawValue: name) else { return }
        play(voice)
    }

    func play(_ voice: SoundVoice) {
        guard isEnabled else { return }
        guard let player = try? AVAudioPlayer(data: data(for: voice)) else { return }
        player.volume = 0.7
        player.play()
        players.append(player)
        if players.count > 6 { players.removeFirst(players.count - 6) }
    }

    private func data(for voice: SoundVoice) -> Data {
        if let cached = cache[voice] { return cached }
        let rendered = SoundSynth.wav(SoundSynth.samples(for: voice))
        cache[voice] = rendered
        return rendered
    }
}
