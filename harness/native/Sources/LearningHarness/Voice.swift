import AVFoundation
import Speech
import SwiftUI

/// Device voice I/O for the Stage: on-device ASR (SFSpeechRecognizer) and TTS
/// (AVSpeechSynthesizer). No API key, no audio leaves the machine.
///
/// Two modes share one capture pipeline:
///
/// * **Push-to-talk.** Tap, speak, tap again. The recogniser finalises and the transcript
///   goes to the tutor. This is the mode that has always existed.
/// * **Conversation.** The microphone stays open, an energy detector finds the end of an
///   utterance, and the next one starts by itself. The tutor's speech is cut off the moment
///   the learner starts talking (barge-in), which is what makes a spoken exchange feel like a
///   conversation rather than a walkie-talkie.
///
/// What is deliberately *not* here: streaming the audio to a hosted realtime model. That is
/// ``VoiceRealtime``, it needs an API key, and it sends audio off the machine. This path keeps
/// the product's offline promise and works with the network unplugged.
///
/// macOS notes: there is no AVAudioSession here (that is an iOS surface). Mic permission goes
/// through AVCaptureDevice, and capture is a plain AVAudioEngine input tap. The app must be
/// launched from a bundle whose Info.plist declares ``NSMicrophoneUsageDescription`` and
/// ``NSSpeechRecognitionUsageDescription``. A hardened-runtime (Developer ID) build *also*
/// needs ``com.apple.security.device.audio-input`` in its entitlements: the sandbox file had
/// it and the direct-download file did not, so a notarised build asked for a microphone it had
/// no entitlement to open and TCC refused it.
@MainActor final class VoiceIO: NSObject, ObservableObject {
    @Published var transcript = ""
    @Published var listening = false
    @Published var speaking = false
    @Published var status = ""
    /// True while the microphone is held open for a back-and-forth exchange.
    @Published var conversation = false
    /// Input loudness, 0...1, for a level meter. Display only; the detector keeps its own
    /// calibrated value, because a meter and a threshold want different normalisations.
    @Published var level: Double = 0

    private let engine = AVAudioEngine()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private let synthesizer = AVSpeechSynthesizer()
    private lazy var recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private var detector = VoiceActivityDetector()
    /// When the current utterance's audio began, and when speech was last heard in it.
    private var utteranceStartedAt = Date()
    private var lastSpeechAt: Date?
    private var lastSpeechEndedAt = Date.distantPast
    private var lastLevelUpdate = Date.distantPast
    /// Consecutive frames loud enough to count as an interruption of the tutor's speech.
    private var bargeFrames = 0
    private var endpointer: Timer?
    /// Fired once when the recogniser reports a final transcript.
    var onFinal: ((String) -> Void)?

    /// macOS *terminates the process* the moment an app requests speech recognition
    /// or microphone access without a matching ``NS*UsageDescription`` string in
    /// its Info.plist — a TCC abort (``EXC_CRASH``/``SIGABRT``), not a catchable
    /// error, so no ``do/catch`` survives it. The packaged ``Luminest.app`` carries
    /// both keys (``scripts/package.py`` writes them), but a bare ``swift run``
    /// binary or a stray copy of the executable has no Info.plist at all and dies
    /// on the first Speak tap. This guard turns that into an explanation.
    static func hasUsageDescription(_ key: String) -> Bool {
        guard let value = Bundle.main.object(forInfoDictionaryKey: key) as? String else {
            return false
        }
        return !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private static var speechPermitted: Bool {
        hasUsageDescription("NSSpeechRecognitionUsageDescription")
    }

    private static var microphonePermitted: Bool {
        hasUsageDescription("NSMicrophoneUsageDescription")
    }

    // MARK: - Public controls

    /// Push-to-talk: one utterance, then stop.
    func toggle() {
        if listening { stopListening(finish: true) } else { beginListening(conversation: false) }
    }

    /// Start a continuous exchange. The microphone stays open across turns; each finished
    /// utterance goes to ``onFinal`` and the next one is captured automatically.
    func startConversation() {
        guard !conversation else { return }
        conversation = true
        beginListening(conversation: true)
    }

    /// End the continuous exchange and release the microphone.
    func stopConversation() {
        conversation = false
        stopListening(finish: false)
    }

    func toggleConversation() {
        if conversation { stopConversation() } else { startConversation() }
    }

    func startListening() {
        beginListening(conversation: false)
    }

    // MARK: - Permission + capture

    private func beginListening(conversation wantsConversation: Bool) {
        guard !listening else { return }
        transcript = ""
        guard Self.speechPermitted else {
            status = "Dictation needs the packaged Luminest.app — its Info.plist declares "
                   + "speech recognition. This build has no usage description, and macOS "
                   + "terminates an app that asks without one. Use the tutor text box here."
            conversation = false
            return
        }
        status = "requesting permission…"
        SFSpeechRecognizer.requestAuthorization { [weak self] auth in
            Task { @MainActor in
                guard let self else { return }
                guard auth == .authorized else {
                    self.status = "Speech recognition not authorized (System Settings → Privacy)."
                    self.conversation = false
                    return
                }
                guard Self.microphonePermitted else {
                    self.status = "Dictation needs the packaged Luminest.app — its "
                                + "Info.plist declares microphone use, and macOS terminates "
                                + "an app that asks without one. Use the tutor text box here."
                    self.conversation = false
                    return
                }
                AVCaptureDevice.requestAccess(for: .audio) { [weak self] granted in
                    Task { @MainActor in
                        guard let self else { return }
                        guard granted else {
                            self.status = "Microphone access denied (System Settings → Privacy)."
                            self.conversation = false
                            return
                        }
                        self.conversation = wantsConversation
                        self.beginCapture()
                    }
                }
            }
        }
    }

    private func beginCapture() {
        do {
            if !engine.isRunning {
                let input = engine.inputNode
                input.removeTap(onBus: 0)
                let format = input.outputFormat(forBus: 0)
                input.installTap(onBus: 0, bufferSize: 2048, format: format) { [weak self] buffer, _ in
                    guard let self else { return }
                    // The buffer is appended on the audio thread, exactly as before; only the
                    // loudness reading is handed to the main actor, so the detector's state
                    // stays single-threaded.
                    self.request?.append(buffer)
                    if let rms = Self.loudness(of: buffer) {
                        Task { @MainActor in self.hear(rms: rms) }
                    }
                }
                engine.prepare()
                try engine.start()
            }
            listening = true
            startUtterance()
            status = conversation ? "listening — just talk" : "listening…"
            if conversation { startEndpointer() }
        } catch {
            status = "Could not start capture: \(error.localizedDescription)"
            listening = false
            conversation = false
        }
    }

    /// A fresh recognition request for one utterance. In conversation mode this is called
    /// again after every endpoint, which is what makes the exchange continuous without
    /// stopping and restarting the audio engine - and its permission handshake - each turn.
    private func startUtterance() {
        task?.cancel()
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        // On-device where the recogniser supports it: the transcript is the only thing that
        // leaves this class, and it should not leave the machine either.
        if recognizer?.supportsOnDeviceRecognition == true {
            request.requiresOnDeviceRecognition = true
        }
        self.request = request
        utteranceStartedAt = Date()
        lastSpeechAt = nil
        transcript = ""
        task = recognizer?.recognitionTask(with: request) { [weak self] result, error in
            Task { @MainActor in
                guard let self else { return }
                if let result {
                    self.transcript = result.bestTranscription.formattedString
                    if result.isFinal { self.finishUtterance() }
                }
                if error != nil { self.finishUtterance() }
            }
        }
    }

    /// One utterance is over: hand it over, and either close the mic or open the next turn.
    private func finishUtterance() {
        let said = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
        request = nil
        task = nil
        if !said.isEmpty { onFinal?(said) }
        guard conversation, listening else {
            if !conversation { stopListening(finish: false) }
            return
        }
        // A short pause before reopening: reopening inside the recogniser's own finalisation
        // callback races the task teardown and the first syllable of the next turn is lost.
        Task { [weak self] in
            try? await Task.sleep(nanoseconds: 220_000_000)
            guard let self, self.conversation, self.listening else { return }
            self.startUtterance()
        }
    }

    // MARK: - Voice activity

    /// Loudness of a capture buffer, or nil when the format carries no float data.
    private nonisolated static func loudness(of buffer: AVAudioPCMBuffer) -> Double? {
        guard let channels = buffer.floatChannelData, buffer.frameLength > 0 else { return nil }
        let frames = Int(buffer.frameLength)
        var sum = 0.0
        for index in 0..<frames {
            let sample = Double(channels[0][index])
            sum += sample * sample
        }
        return (sum / Double(frames)).squareRoot()
    }

    /// Feed one loudness reading to the detector and act on it.
    private func hear(rms: Double) {
        guard listening else { return }
        let now = Date()
        // The meter is decoration and is throttled: a @Published write on every audio buffer
        // re-renders the Stage forty times a second for no visible benefit.
        if now.timeIntervalSince(lastLevelUpdate) > 0.08 {
            lastLevelUpdate = now
            level = min(1, rms * 10)
        }
        detector.observe(rms)
        let voiced = detector.isVoiced(rms)

        if voiced {
            lastSpeechAt = now
            // Barge-in. A learner talking over the tutor is the strongest possible signal
            // that the tutor should stop - but the microphone also hears the tutor, through
            // the speakers. Cutting the reply off on the first loud frame is how a duplex
            // session ends up interrupting itself every time it starts talking, so the
            // interruption needs a louder signal and it needs to persist: roughly a third of
            // a second of speech above a raised threshold, which a speaker echo does not
            // sustain at the microphone.
            if speaking {
                if detector.isVoiced(rms, marginMultiplier: 2.4) {
                    bargeFrames += 1
                } else {
                    bargeFrames = 0
                }
                if bargeFrames >= 6, now.timeIntervalSince(lastSpeechEndedAt) > 0.25 {
                    stopSpeaking()
                    status = "listening — just talk"
                    bargeFrames = 0
                }
            }
        } else if speaking {
            bargeFrames = 0
        }
    }

    /// Poll for the end of an utterance. A timer rather than a check inside ``hear``: silence
    /// produces no buffer callbacks worth speaking of, so an event-driven endpoint would only
    /// fire when the learner made another sound.
    private func startEndpointer() {
        endpointer?.invalidate()
        endpointer = Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.endpointIfQuiet() }
        }
    }

    private func endpointIfQuiet() {
        guard conversation, listening, !speaking else { return }
        let now = Date()
        guard let heard = lastSpeechAt else {
            // Nothing said yet. Do not cut an utterance off before it starts, but do give up
            // on one that has produced no speech at all for a while, so a stray tap does not
            // leave the recogniser running for a minute.
            if now.timeIntervalSince(utteranceStartedAt) > 20 { request?.endAudio() }
            return
        }
        let quiet = now.timeIntervalSince(heard)
        if quiet >= detector.endpointSeconds && now.timeIntervalSince(utteranceStartedAt) > 0.4 {
            lastSpeechEndedAt = now
            lastSpeechAt = nil
            request?.endAudio()   // the recogniser finalises; finishUtterance reopens
        }
    }

    // MARK: - Teardown

    func stopListening(finish: Bool) {
        if finish { request?.endAudio() }
        endpointer?.invalidate()
        endpointer = nil
        task?.cancel()
        task = nil
        request = nil
        if engine.isRunning {
            engine.inputNode.removeTap(onBus: 0)
            engine.stop()
        }
        listening = false
        conversation = false
        level = 0
        detector.reset()
        if !status.hasPrefix("Speech") && !status.hasPrefix("Microphone") { status = "" }
    }

    // ---- TTS ----

    func speak(_ text: String) {
        let clean = text.replacingOccurrences(of: "[#*`_]", with: "", options: .regularExpression)
        guard !clean.isEmpty else { return }
        synthesizer.stopSpeaking(at: .immediate)
        let utterance = AVSpeechUtterance(string: String(clean.prefix(1200)))
        utterance.rate = 0.5
        utterance.pitchMultiplier = 1.0
        synthesizer.delegate = self
        synthesizer.speak(utterance)
        speaking = true
        if conversation { status = "speaking — talk over me to interrupt" }
    }

    func stopSpeaking() {
        synthesizer.stopSpeaking(at: .immediate)
        speaking = false
        lastSpeechEndedAt = Date()
        if conversation { status = "listening — just talk" }
    }
}

extension VoiceIO: AVSpeechSynthesizerDelegate {
    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        Task { @MainActor in
            self.speaking = false
            self.lastSpeechEndedAt = Date()
        }
    }
    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        Task { @MainActor in
            self.speaking = false
            self.lastSpeechEndedAt = Date()
        }
    }
}

/// Energy-based voice activity detection with a floor that follows the room.
///
/// A fixed threshold is why speakerphone software fails in a new room: 0.02 is silence in a
/// quiet study and speech next to a fan. This detector keeps a decaying estimate of the noise
/// floor and places the threshold above it, so the same code works with a laptop mic in a
/// library and a headset in a café.
///
/// Deliberately not a model. A learned VAD would be more accurate and would also be another
/// dependency, another download and another thing that cannot run offline on the first
/// launch; energy plus a floor estimate is honest about being a heuristic, and it is enough
/// to decide "they have stopped talking".
struct VoiceActivityDetector {
    /// Absolute floor: below this nothing is speech, however quiet the room.
    ///
    /// Calibrated against the barge-in margin: ``minimumThreshold * 2.4`` must sit clearly
    /// above ordinary speech (~0.03 RMS in this scale), or speaker echo at conversational
    /// level interrupts the tutor while it is talking. 0.012 × 2.4 = 0.0288 was a 4% sliver;
    /// 0.015 × 2.4 = 0.036 leaves real headroom.
    static let minimumThreshold = 0.015
    /// How far above the noise floor speech must sit to count.
    static let floorMargin = 2.6
    /// Silence after speech that ends an utterance.
    var endpointSeconds: Double = 1.1

    private var floor: Double = 0.006

    mutating func observe(_ rms: Double) {
        // The floor falls quickly and rises slowly: a cough must not raise the threshold for
        // the next ten seconds, but a fan switching on must be absorbed.
        if rms < floor {
            floor += (rms - floor) * 0.35
        } else {
            floor += (rms - floor) * 0.004
        }
        floor = max(0.0005, floor)
    }

    func isVoiced(_ rms: Double) -> Bool {
        rms > max(Self.minimumThreshold, floor * Self.floorMargin)
    }

    /// A stricter reading used while the tutor is speaking: the microphone is hearing the
    /// speakers as well as the learner, so the bar for "this is a person interrupting" is
    /// raised rather than the detector being told to ignore input entirely.
    func isVoiced(_ rms: Double, marginMultiplier: Double) -> Bool {
        rms > max(Self.minimumThreshold * marginMultiplier, floor * Self.floorMargin * marginMultiplier)
    }

    mutating func reset() {
        floor = 0.006
    }
}

/// Plays a speech clip the backend already rendered (mp3 bytes from the local
/// VoiceStudio service).
///
/// Deliberately a separate object from ``VoiceIO``: that one is this Mac's
/// ``AVSpeechSynthesizer`` reading the text aloud, which is a different voice with
/// different limits and is the one that sounds robotic. Keeping them apart means the
/// UI can say which is speaking, and a learner is never left guessing why the tutor's
/// voice changed character between two replies.
///
/// The bytes arrive over the authenticated artifact route, because every media route
/// on this backend is bearer-protected - a bare ``AVPlayer(url:)`` pointed at the URL
/// would get a 401 and play silence.
@MainActor final class ClipPlayer: NSObject, ObservableObject {
    @Published var playing = false
    private var player: AVAudioPlayer?

    func play(_ data: Data) {
        stop()
        guard let audio = try? AVAudioPlayer(data: data), audio.duration > 0 else { return }
        audio.delegate = self
        audio.prepareToPlay()
        audio.play()
        player = audio
        playing = true
    }

    func stop() {
        player?.stop()
        player = nil
        playing = false
    }
}

extension ClipPlayer: AVAudioPlayerDelegate {
    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in self.playing = false }
    }
}
