import AVFoundation
import SwiftUI

// A 45-minute auto-lecture.
//
// The lesson procedure makes the learner choose the next activity. This surface does the
// opposite: it plays a compiled storyboard — speech, a page turn, one image or video, and a
// fresh whiteboard page — without asking the learner to drive. The server owns the
// storyboard and the board mutations; this file is the theatre.

struct LectureSegment: Identifiable {
    let index: Int
    let title: String
    let narration: String
    let bullets: [String]
    let duration: Int
    let speech: Int
    let pause: Int

    var id: Int { index }

    init(_ json: JSON) {
        index = json["index"].int
        title = json["title"].string
        narration = json["narration"].string
        bullets = json["bullets"].array.map(\.string).filter { !$0.isEmpty }
        duration = max(1, json["duration_seconds"].int)
        speech = max(0, json["speech_seconds"].int)
        pause = max(0, json["pause_seconds"].int)
    }
}

struct LecturePlan {
    let title: String
    let segments: [LectureSegment]

    init(_ json: JSON) {
        title = json["title"].string
        segments = json["segments"].array.map(LectureSegment.init)
    }

    var totalSeconds: Int { segments.reduce(0) { $0 + $1.duration } }
}

@MainActor
final class LectureStore: ObservableObject {
    @Published var plan: LecturePlan?
    @Published var segment: LectureSegment?
    @Published var media: JSON = .null
    @Published var index = 0
    @Published var boardID = ""
    @Published var boardVersion = 0
    @Published var error = ""
    @Published var busy = false
    private let api: APIClient

    init(api: APIClient) { self.api = api }

    private func path(_ conceptID: String, _ suffix: String) -> String {
        let encoded = conceptID.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? conceptID
        return "/lecture/\(encoded)\(suffix)"
    }

    func start(conceptID: String) async {
        busy = true
        defer { busy = false }
        do {
            let value = try await api.json(path(conceptID, "/start?minutes=45"),
                                           method: "POST", body: [String: Any]())
            plan = LecturePlan(value["lecture"])
            boardID = value["board_id"].string
            boardVersion = value["board_version"].int
            index = 0
            error = ""
        } catch {
            self.error = (error as? AppFailure)?.message ?? error.localizedDescription
        }
    }

    func load(index wanted: Int, conceptID: String) async {
        busy = true
        defer { busy = false }
        do {
            let value = try await api.json(path(conceptID, "/segment/\(wanted)?minutes=45"),
                                           method: "POST", body: [String: Any]())
            segment = LectureSegment(value["segment"])
            media = value["media"]
            boardID = value["board_id"].string.isEmpty ? boardID : value["board_id"].string
            boardVersion = value["board_version"].int
            index = value["index"].int
            error = ""
        } catch {
            self.error = (error as? AppFailure)?.message ?? error.localizedDescription
        }
    }
}

/// Local speech for the lecture, chunked so a 300-word segment is not truncated.
///
/// The tutor's `VoiceIO` caps one utterance at 1,200 characters, which is right for a chat
/// reply and wrong for a lecture. Chunks queue on one synthesizer; the completion callback
/// fires only when the queue is empty.
@MainActor
final class LectureNarrator: NSObject, ObservableObject, AVSpeechSynthesizerDelegate {
    private let synthesizer = AVSpeechSynthesizer()
    @Published var speaking = false
    var onFinish: (() -> Void)?

    override init() {
        super.init()
        synthesizer.delegate = self
    }

    func speak(_ text: String) {
        stop()
        let clean = text.replacingOccurrences(of: "[#*`_]", with: "", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return }
        let speaksChinese = clean.unicodeScalars.contains { $0.value >= 0x4E00 && $0.value <= 0x9FFF }
        var buffer = ""
        for sentence in clean.split(whereSeparator: { ".!?。！？\n".contains($0) }) {
            let piece = String(sentence) + " "
            if buffer.count + piece.count > 900 {
                enqueue(buffer, chinese: speaksChinese)
                buffer = ""
            }
            buffer += piece
        }
        if !buffer.isEmpty { enqueue(buffer, chinese: speaksChinese) }
        speaking = true
    }

    private func enqueue(_ text: String, chinese: Bool) {
        let utterance = AVSpeechUtterance(string: String(text.prefix(1000)))
        utterance.rate = 0.48
        utterance.pitchMultiplier = 1.0
        if chinese { utterance.voice = AVSpeechSynthesisVoice(language: "zh-CN") }
        synthesizer.speak(utterance)
    }

    func stop() {
        synthesizer.stopSpeaking(at: .immediate)
        speaking = false
    }

    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer,
                                       didFinish utterance: AVSpeechUtterance) {
        Task { @MainActor in
            if !self.synthesizer.isSpeaking {
                self.speaking = false
                self.onFinish?()
            }
        }
    }

    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer,
                                       didCancel utterance: AVSpeechUtterance) {
        Task { @MainActor in self.speaking = false }
    }
}

struct LectureTheater: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss
    let conceptID: String

    @StateObject private var lecture: LectureStore
    @StateObject private var narrator = LectureNarrator()
    @StateObject private var board: BoardStore

    @State private var playing = true
    @State private var elapsed = 0
    @State private var started = false
    @State private var showTranscript = true
    private let tick = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    init(conceptID: String) {
        self.conceptID = conceptID
        let api = AppStore.current?.api
            ?? APIClient(endpoint: UserDefaults.standard.string(forKey: "luminfest.endpoint")
                         ?? "http://127.0.0.1:8765")
        _lecture = StateObject(wrappedValue: LectureStore(api: api))
        _board = StateObject(wrappedValue: BoardStore(api: api))
    }

    var body: some View {
        ZStack {
            Palette.background.ignoresSafeArea()
            VStack(spacing: 0) {
                header
                Divider().overlay(Palette.line)
                HStack(spacing: 0) {
                    slidePane.frame(maxWidth: .infinity)
                    Divider().overlay(Palette.line)
                    boardPane.frame(width: 470)
                }
                Divider().overlay(Palette.line)
                footer
            }
        }
        .frame(minWidth: 1_150, minHeight: 740)
        .task {
            guard !started else { return }
            started = true
            await begin()
        }
        .onReceive(tick) { _ in advanceClock() }
        .onDisappear { narrator.stop() }
    }

    // MARK: - chrome

    private var header: some View {
        HStack(spacing: 14) {
            VStack(alignment: .leading, spacing: 3) {
                Eyebrow(text: "AUTO LECTURE · 45 MIN")
                Text(lecture.plan?.title ?? "Compiling the lecture…")
                    .font(.system(size: 20, weight: .semibold))
                    .lineLimit(1)
            }
            Spacer()
            if let segment = lecture.segment {
                Tag(text: "PAGE \(segment.index) / \(lecture.plan?.segments.count ?? 0)",
                    color: Palette.accentTeal.soft)
            }
            Text(timeText(currentSeconds) + " / " + timeText(lecture.plan?.totalSeconds ?? 2700))
                .font(.system(size: 12, design: .monospaced))
                .foregroundStyle(Palette.secondary)
            Button { narrator.stop(); dismiss() } label: {
                Image(systemName: "xmark").font(.system(size: 12, weight: .semibold))
                    .padding(8).background(Palette.muted, in: Circle())
            }
            .buttonStyle(.plain)
            .help("End the lecture")
            .accessibilityIdentifier("lecture.close")
        }
        .padding(.horizontal, 26)
        .padding(.vertical, 16)
    }

    private var footer: some View {
        VStack(spacing: 10) {
            ProgressView(value: Double(currentSeconds),
                         total: Double(max(1, lecture.plan?.totalSeconds ?? 2700)))
                .tint(Palette.forest)
            HStack(spacing: 12) {
                Button { previous() } label: { Image(systemName: "backward.end.fill") }
                    .buttonStyle(.borderless).disabled(lecture.index == 0)
                    .help("Previous segment")
                Button { togglePlay() } label: {
                    Image(systemName: playing ? "pause.fill" : "play.fill")
                        .font(.system(size: 16))
                        .frame(width: 34, height: 34)
                        .background(Palette.forest, in: Circle())
                        .foregroundStyle(.white)
                }
                .buttonStyle(.plain)
                .help(playing ? "Pause" : "Resume")
                Button { next() } label: { Image(systemName: "forward.end.fill") }
                    .buttonStyle(.borderless)
                    .disabled(lecture.index + 1 >= (lecture.plan?.segments.count ?? 0))
                    .help("Next segment")
                Button("Restart") { restart() }
                    .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
                Spacer()
                if isPause {
                    Text("Pause — say it back in your own words")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(Palette.forest)
                } else if let segment = lecture.segment {
                    Text("\(segment.title) · \(remainingText)")
                        .font(.system(size: 12))
                        .foregroundStyle(Palette.secondary)
                        .lineLimit(1)
                }
                if !lecture.error.isEmpty {
                    Text(lecture.error).font(.system(size: 11))
                        .foregroundStyle(Palette.peachDeep).lineLimit(2)
                }
            }
            .padding(.horizontal, 26)
        }
        .padding(.vertical, 14)
    }

    // MARK: - slide

    private var slidePane: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                if let segment = lecture.segment {
                    Text(segment.title)
                        .font(.system(size: 34, weight: .semibold, design: .rounded))
                        .tracking(-0.9)
                    if !segment.bullets.isEmpty {
                        VStack(alignment: .leading, spacing: 9) {
                            ForEach(Array(segment.bullets.enumerated()), id: \.offset) { _, bullet in
                                HStack(alignment: .top, spacing: 9) {
                                    Circle().fill(Palette.forest).frame(width: 6, height: 6)
                                        .padding(.top, 7)
                                    Text(bullet).font(.system(size: 16))
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                            }
                        }
                    }
                    LectureMediaView(media: lecture.media)
                    if isPause {
                        Card(color: Palette.sage) {
                            VStack(alignment: .leading, spacing: 8) {
                                Eyebrow(text: "YOUR TURN")
                                Text("Say the last idea back in one sentence, out loud. Then let the lecture continue.")
                                    .font(.system(size: 13)).lineSpacing(4)
                                HStack(spacing: 10) {
                                    Text("\(max(0, segment.duration - elapsed))s")
                                        .font(.system(size: 12, design: .monospaced))
                                        .foregroundStyle(Palette.secondary)
                                    Button("Continue now") { next() }
                                        .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
                                }
                            }
                        }
                    }
                    if showTranscript {
                        Card {
                            VStack(alignment: .leading, spacing: 8) {
                                HStack {
                                    Eyebrow(text: "WHAT THE LECTURER IS SAYING")
                                    Spacer()
                                    Button(showTranscript ? "Hide" : "Show") { showTranscript.toggle() }
                                        .buttonStyle(.plain).font(.system(size: 11))
                                }
                                Text(segment.narration)
                                    .font(.system(size: 13)).lineSpacing(5)
                                    .foregroundStyle(Palette.secondary)
                                    .textSelection(.enabled)
                            }
                        }
                    }
                } else {
                    VStack(spacing: 16) {
                        ProgressView()
                        Text(lecture.error.isEmpty ? "Compiling a 45-minute lecture…" : lecture.error)
                            .font(.system(size: 13)).foregroundStyle(Palette.secondary)
                    }
                    .frame(maxWidth: .infinity, minHeight: 360)
                }
            }
            .padding(28)
        }
    }

    private var boardPane: some View {
        VStack(spacing: 0) {
            HStack {
                Eyebrow(text: "WHITEBOARD · PAGE \(lecture.index + 1)")
                Spacer()
                if lecture.boardVersion > 0 {
                    Text("v\(lecture.boardVersion)").font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(Palette.tertiary)
                }
            }
            .padding(.horizontal, 14).padding(.vertical, 10)
            BoardEditor(board: board, conceptID: conceptID)
                .id(lecture.boardID)
        }
        .background(Palette.surfaceSubtle)
    }

    // MARK: - playback

    private var currentSeconds: Int {
        guard let plan = lecture.plan, lecture.index < plan.segments.count else { return 0 }
        let before = plan.segments.prefix(lecture.index).reduce(0) { $0 + $1.duration }
        return before + min(elapsed, plan.segments[lecture.index].duration)
    }

    private var isPause: Bool {
        guard let segment = lecture.segment else { return false }
        return elapsed >= segment.speech && elapsed < segment.duration
    }

    private var remainingText: String {
        guard let segment = lecture.segment else { return "" }
        return "\(max(0, segment.duration - elapsed))s left"
    }

    private func begin() async {
        await lecture.start(conceptID: conceptID)
        guard lecture.plan != nil else { return }
        if !lecture.boardID.isEmpty { await board.loadExisting(lecture.boardID) }
        play(0)
    }

    private func play(_ wanted: Int) {
        guard let plan = lecture.plan, wanted >= 0, wanted < plan.segments.count else { return }
        elapsed = 0
        playing = true
        Task {
            await lecture.load(index: wanted, conceptID: conceptID)
            if !lecture.boardID.isEmpty { await board.loadExisting(lecture.boardID) }
            if let segment = lecture.segment {
                narrator.speak(segment.narration)
            }
        }
    }

    private func advanceClock() {
        guard playing, let segment = lecture.segment else { return }
        elapsed += 1
        if elapsed >= segment.duration {
            next()
        }
    }

    private func next() {
        guard let plan = lecture.plan else { return }
        if lecture.index + 1 < plan.segments.count {
            play(lecture.index + 1)
        } else {
            playing = false
            narrator.stop()
        }
    }

    private func previous() {
        guard lecture.index > 0 else { return }
        play(lecture.index - 1)
    }

    private func togglePlay() {
        if playing {
            playing = false
            narrator.stop()
        } else {
            playing = true
            if let segment = lecture.segment { narrator.speak(segment.narration) }
        }
    }

    private func restart() {
        narrator.stop()
        play(0)
    }

    private func timeText(_ seconds: Int) -> String {
        let value = max(0, seconds)
        return String(format: "%d:%02d", value / 60, value % 60)
    }
}

/// One segment's visual. A local cleared image is rendered from the authenticated byte
/// endpoint; a reference is shown as a remote thumbnail with its licence and source link,
/// never as if it had been copied into the lesson.
struct LectureMediaView: View {
    @EnvironmentObject var store: AppStore
    let media: JSON

    var body: some View {
        let kind = media["kind"].string
        if kind == "image" {
            DeckPhotograph(visual: media, height: 280)
        } else if kind == "video" {
            videoCard
        } else if kind == "image_reference" {
            referenceCard
        } else if kind == "video_reference" {
            note(media["note"].string.isEmpty
                 ? "No verified video is curated for this segment."
                 : media["note"].string)
        }
    }

    private var videoCard: some View {
        let raw = media["embed_url"].string.isEmpty ? media["watch_url"].string : media["embed_url"].string
        let autoplay = raw.contains("?") ? raw + "&autoplay=1&mute=1&rel=0"
                                         : raw + "?autoplay=1&mute=1&rel=0"
        return VStack(alignment: .leading, spacing: 6) {
            if let url = URL(string: autoplay), !raw.isEmpty {
                StageWebView(url: url)
                    .frame(height: 300)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            } else {
                note("No embeddable video was returned for this segment.")
            }
            if !media["title"].string.isEmpty {
                Text(media["title"].string + (media["channel"].string.isEmpty
                     ? "" : " · " + media["channel"].string))
                    .font(.system(size: 11)).foregroundStyle(Palette.secondary).lineLimit(2)
            }
        }
    }

    private var referenceCard: some View {
        let rows = media["references"].array
        return VStack(alignment: .leading, spacing: 10) {
            if let first = rows.first, !first["thumb_url"].string.isEmpty,
               let url = URL(string: first["thumb_url"].string) {
                AsyncImage(url: url) { phase in
                    if case .success(let image) = phase {
                        image.resizable().scaledToFill().frame(height: 250)
                            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                    } else {
                        RoundedRectangle(cornerRadius: 14).fill(Palette.muted)
                            .frame(height: 250)
                            .overlay(ProgressView().controlSize(.small))
                    }
                }
            }
            ForEach(Array(rows.prefix(3).enumerated()), id: \.offset) { _, row in
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "photo").foregroundStyle(Palette.forest)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(row["title"].string).font(.system(size: 12, weight: .medium)).lineLimit(2)
                        Text([row["source"].string, row["licence"].string]
                             .filter { !$0.isEmpty }.joined(separator: " · "))
                            .font(.system(size: 10)).foregroundStyle(Palette.secondary)
                    }
                    Spacer()
                    if let url = URL(string: row["url"].string), !row["url"].string.isEmpty {
                        Link("Source", destination: url).font(.system(size: 11))
                    }
                }
            }
            if rows.isEmpty {
                note(media["note"].string.isEmpty
                     ? "No image passed the licence, size and relevance gates."
                     : media["note"].string)
            } else {
                Text("References only: these are linked to their source, not copied into the lesson.")
                    .font(.system(size: 10)).foregroundStyle(Palette.tertiary)
            }
        }
    }

    private func note(_ text: String) -> some View {
        Label(text, systemImage: "info.circle")
            .font(.system(size: 11)).foregroundStyle(Palette.secondary)
            .padding(12).frame(maxWidth: .infinity, alignment: .leading)
            .background(Palette.muted, in: RoundedRectangle(cornerRadius: 12))
    }
}
