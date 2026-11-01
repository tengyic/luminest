import AVFoundation
import Foundation

/// Real-time, duplex voice with the OpenAI Realtime API (`/v1/realtime`).
///
/// This replaces the one-way push-to-talk path in ``VoiceIO`` for learners who have
/// entered an API key. The app opens aWebSocket straight to OpenAI, streams mic audio
/// in 24 kHz PCM16, and plays the model's audio deltas as they arrive — so the tutor
/// speaks and listens at the same time (barge-in: the learner can interrupt, and the
/// in-flight response is cancelled).
///
/// Honest scope notes:
/// - The key is read from the Keychain (``RealtimeKey``), never logged.
/// - Microphone permission is required; without it the connect fails and the UI says so.
/// - This is a voice-only channel to OpenAI. It is independent of the backend tutor;
///   the backend still owns curriculum, grading and the text chat.
@MainActor final class VoiceRealtime: NSObject, ObservableObject {
    @Published var connected = false
    @Published var status = ""
    @Published var localTranscript = ""   // what the learner said (server transcription)
    @Published var remoteTranscript = ""  // what the tutor said (model transcript)
    @Published var error: String?

    private static let model = "gpt-4o-realtime-preview-2024-12-17"
    private static let sampleRate: Double = 24_000

    // Network
    private var session: URLSession?
    private var socket: URLSessionWebSocketTask?
    private var receiveTask: Task<Void, Never>?
    private var sendTask: Task<Void, Never>?

    // Audio capture
    private let audioEngine = AVAudioEngine()
    private let targetFormat: AVAudioFormat
    private var captureConverter: AVAudioConverter?

    // Audio playback
    private let playerNode = AVAudioPlayerNode()
    private var playbackFormat: AVAudioFormat?
    private var playbackConverter: AVAudioConverter?

    // Thread-safe outbound audio queue (filled from the realtime audio thread, drained
    // by `sendTask` on the main actor).
    private let sendQueue = DispatchQueue(label: "luminfest.realtime.send")
    private var pending: [String] = []
    private var sendSignal: CheckedContinuation<Void, Never>?

    override init() {
        // 16-bit mono PCM at 24 kHz — the format OpenAI's realtime model ingests.
        let fmt = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: Self.sampleRate, channels: 1, interleaved: false)!
        targetFormat = fmt
        super.init()
    }

    deinit {
        sendSignal?.resume()
    }

    // MARK: Lifecycle

    func toggle() {
        if connected { disconnect() } else { connect() }
    }

    func connect() {
        guard !connected else { return }
        guard let key = RealtimeKey.load(), !key.isEmpty else {
            error = "No OpenAI Realtime API key. Add one in Settings → Learning environment."
            status = "API key missing"
            return
        }
        guard AVCaptureDevice.authorizationStatus(for: .audio) != .denied else {
            error = "Microphone access was denied in System Settings → Privacy."
            status = "Microphone denied"
            return
        }
        status = "connecting…"
        error = nil
        let url = URL(string: "https://api.openai.com/v1/realtime?model=\(Self.model)")!
        var request = URLRequest(url: url)
        request.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
        request.setValue("realtime=v1", forHTTPHeaderField: "OpenAI-Beta")

        let wsSession = URLSession(configuration: .ephemeral)
        session = wsSession
        let socket = wsSession.webSocketTask(with: request)
        self.socket = socket

        setupAudio()

        socket.resume()
        receiveTask = Task { await receiveLoop() }
        sendTask = Task { await sendLoop() }

        // Hand the model its behaviour, then start the mic. Server-VAD means we just
        // keep streaming audio and the model decides when the learner is done.
        Task {
            try? await sendJSON([
                "type": "session.update",
                "session": [
                    "modalities": ["audio", "text"],
                    "instructions": Self.instructions,
                    "voice": "alloy",
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "input_audio_transcription": ["model": "whisper-1"],
                    "turn_detection": [
                        "type": "server_vad",
                        "threshold": 0.5,
                        "silence_duration_ms": 350,
                        "prefix_padding_ms": 200,
                        "create_response": true,
                        "interrupt_response": true
                    ]
                ]
            ])
        }
    }

    func disconnect() {
        receiveTask?.cancel()
        sendTask?.cancel()
        receiveTask = nil
        sendTask = nil
        socket?.cancel(with: .normalClosure, reason: nil)
        socket = nil
        session = nil
        teardownAudio()
        connected = false
        status = "ended"
    }

    // MARK: Audio graph

    private func setupAudio() {
        let input = audioEngine.inputNode
        let inputFormat = input.outputFormat(forBus: 0)
        captureConverter = AVAudioConverter(from: inputFormat, to: targetFormat)

        playbackFormat = audioEngine.outputNode.inputFormat(forBus: 0)
        if let playbackFormat {
            playbackConverter = AVAudioConverter(from: targetFormat, to: playbackFormat)
            audioEngine.attach(playerNode)
            audioEngine.connect(playerNode, to: audioEngine.outputNode, format: playbackFormat)
        }

        input.installTap(onBus: 0, bufferSize: 2048, format: inputFormat) { [weak self] buffer, _ in
            self?.capture(buffer)
        }
        do {
            audioEngine.prepare()
            try audioEngine.start()
            playerNode.play()
        } catch {
            Task { @MainActor in self.status = "Audio engine failed: \(error.localizedDescription)" }
        }
    }

    private func teardownAudio() {
        audioEngine.inputNode.removeTap(onBus: 0)
        playerNode.stop()
        audioEngine.stop()
        audioEngine.disconnectNodeOutput(playerNode)
    }

    /// Convert a captured float buffer to 24 kHz PCM16 and enqueue it for sending.
    private func capture(_ buffer: AVAudioPCMBuffer) {
        guard let converter = captureConverter else { return }
        let ratio = targetFormat.sampleRate / buffer.format.sampleRate
        let outFrames = AVAudioFrameCount(max(1, Double(buffer.frameLength) * ratio))
        guard let out = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: outFrames) else { return }
        var consumed = false
        var err: NSError?
        converter.convert(to: out, error: &err) { _, statusPtr in
            if consumed { statusPtr.pointee = .noDataNow; return nil }
            consumed = true
            statusPtr.pointee = .haveData
            return buffer
        }
        guard err == nil, out.frameLength > 0, let channel = out.int16ChannelData else { return }
        let frameCount = Int(out.frameLength)
        let data = Data(bytes: channel[0], count: frameCount * MemoryLayout<Int16>.stride)
        let b64 = data.base64EncodedString()
        sendQueue.async { [weak self] in
            self?.pending.append(b64)
            self?.signalSend()
        }
    }

    /// Convert an incoming PCM16 chunk to the output format and schedule it on the player.
    private func play(_ int16Data: Data) {
        let frameCount = int16Data.count / MemoryLayout<Int16>.stride
        guard frameCount > 0, let inBuf = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: AVAudioFrameCount(frameCount)) else { return }
        int16Data.withUnsafeBytes { raw in
            guard let base = raw.bindMemory(to: Int16.self).baseAddress else { return }
            inBuf.int16ChannelData?[0].update(from: base, count: frameCount)
        }
        inBuf.frameLength = AVAudioFrameCount(frameCount)
        guard let playbackFormat, let converter = playbackConverter else { return }
        let ratio = playbackFormat.sampleRate / targetFormat.sampleRate
        let outFrames = AVAudioFrameCount(max(1, Double(frameCount) * ratio)) + 16
        guard let out = AVAudioPCMBuffer(pcmFormat: playbackFormat, frameCapacity: outFrames) else { return }
        var consumed = false
        var err: NSError?
        converter.convert(to: out, error: &err) { _, statusPtr in
            if consumed { statusPtr.pointee = .noDataNow; return nil }
            consumed = true
            statusPtr.pointee = .haveData
            return inBuf
        }
        guard err == nil else { return }
        playerNode.scheduleBuffer(out)
    }

    // MARK: Send loop

    private func signalSend() {
        sendSignal?.resume()
        sendSignal = nil
    }

    private func sendLoop() async {
        while !Task.isCancelled {
            await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
                sendSignal = cont
            }
            guard !Task.isCancelled else { return }
            let batch = sendQueue.sync { () -> [String] in
                let b = pending
                pending.removeAll()
                return b
            }
            for b64 in batch {
                do {
                    try await sendJSON(["type": "input_audio_buffer.append", "audio": b64])
                } catch {
                    // A transient send failure should not kill the session.
                    break
                }
            }
        }
    }

    private func sendJSON(_ dict: [String: Any]) async throws {
        guard let socket else { throw AppFailure(message: "Not connected.", status: nil) }
        let data = try JSONSerialization.data(withJSONObject: dict)
        try await socket.send(.data(data))
    }

    // MARK: Receive loop

    private func receiveLoop() async {
        guard let socket else { return }
        while !Task.isCancelled {
            do {
                let message = try await socket.receive()
                switch message {
                case let .string(text):
                    await handle(text)
                case let .data(data):
                    if let text = String(data: data, encoding: .utf8) { await handle(text) }
                @unknown default:
                    break
                }
            } catch is CancellationError {
                return
            } catch {
                Task { @MainActor in
                    self.error = "Connection lost: \(error.localizedDescription)"
                    self.connected = false
                    self.status = "disconnected"
                }
                return
            }
        }
    }

    private func handle(_ text: String) async {
        guard let json = try? JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any],
              let type = json["type"] as? String else { return }
        switch type {
        case "session.created", "session.updated":
            Task { @MainActor in
                if !self.connected { self.connected = true }
                self.status = "connected — speak naturally"
            }
        case "input_audio_buffer.speech_started":
            // Barge-in: the learner started talking, so stop the tutor mid-sentence.
            Task { @MainActor in
                self.remoteTranscript = ""
                self.localTranscript = ""
                self.status = "listening…"
            }
            try? await sendJSON(["type": "response.cancel"])
        case "conversation.item.input_audio_transcription.delta",
             "conversation.item.input_audio_transcription.completed":
            if let transcript = json["transcript"] as? String {
                Task { @MainActor in self.localTranscript += transcript }
            }
        case "response.audio_transcript.delta":
            if let delta = json["delta"] as? String {
                Task { @MainActor in self.remoteTranscript += delta }
            }
        case "response.audio.delta":
            if let b64 = json["delta"] as? String, let data = Data(base64Encoded: b64) {
                play(data)
            }
        case "error":
            if let message = (json["error"] as? [String: Any])?["message"] as? String {
                Task { @MainActor in
                    self.error = "OpenAI: \(message)"
                    self.status = "error"
                }
            }
        default:
            break
        }
    }

    /// What the model is told to be. Kept short and spoken-friendly: this is a voice-only
    /// channel, so no markdown, links or on-screen formatting survive.
    private static let instructions = """
    You are Lumi, a calm and encouraging tutor for K-12 mathematics and science, \
    speaking with a learner through voice. Use short spoken sentences. Ask one question \
    at a time and wait for the answer. If the learner is mistaken, give a small hint \
    rather than the answer. Keep each reply under about 30 seconds of speech. Do not read \
    long passages, and never use written formatting such as markdown, links or lists.
    """
}
