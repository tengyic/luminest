import SwiftUI
import AppKit
import AVKit
import AVFoundation
import PDFKit
import UniformTypeIdentifiers
import Combine
import WebKit

struct SafeLessonLink: View {
    let title: String
    let rawURL: String
    static func url(_ text: String) -> URL? {
        guard let u = URL(string: text), u.scheme?.lowercased() == "https", let host = u.host, !host.isEmpty, u.user == nil, u.password == nil else { return nil }
        return u
    }
    var body: some View {
        if let url = Self.url(rawURL) { Link(destination: url) { Label(title, systemImage: "arrow.up.right").font(.system(size: 11)) } }
    }
}

@MainActor final class LessonSpeech: NSObject, ObservableObject, AVSpeechSynthesizerDelegate {
    @Published var isSpeaking = false
    /// True while the VoiceStudio backend is the voice. The caption under the
    /// button says which engine is talking, because "no third-party AI" is no
    /// longer true once the instance runs a voice backend.
    @Published var usingBackendVoice = false
    private let synthesizer = AVSpeechSynthesizer()
    private var player: AVAudioPlayer?
    private weak var api: APIClient?
    /// One-shot completion for narrated-deck autoplay. ``stop`` deliberately clears it:
    /// manually pausing or changing slide must never let an old utterance advance the deck.
    private var completion: (() -> Void)?

    override init() { super.init(); synthesizer.delegate = self }

    /// The backend is what makes VoiceStudio reachable; without a bound client
    /// read-aloud simply uses the device voice.
    func bind(api: APIClient) { self.api = api }

    func read(lesson: JSON) {
        stop()
        let blocks = lesson["blocks"].array.filter { LessonBlock.kinds.contains($0["kind"].string) || $0["kind"].string.isEmpty }
        let text = ([lesson["title"].string] + blocks.flatMap { [$0["title"].string, $0["body"].string, $0["formula"].string] }).filter { !$0.isEmpty }.joined(separator: ". ")
        guard !text.isEmpty else { return }
        readAloud(text)
    }

    /// Speak `text` through the local VoiceStudio backend first — the same engine
    /// (and the same voice profile) the tutor's `text_to_speech` tool uses — and
    /// fall back to the device voice when the backend is not running, refuses, or
    /// is slow. A read-aloud button that dies because a local service is down is
    /// a worse button than one that changes voice.
    func readAloud(_ text: String) {
        guard let api else { speakOnDevice(text); return }
        // The provider caps one request at 4096 characters; the device voice has
        // no such limit, so a long lesson reads in full either way.
        let payload = String(text.prefix(4096))
        Task {
            do {
                let data = try await api.data("/voice/speak", method: "POST",
                                             body: ["text": payload])
                try self.play(data)
                self.usingBackendVoice = true
            } catch {
                self.speakOnDevice(text)
            }
        }
    }

    private func play(_ data: Data) throws {
        player = try AVAudioPlayer(data: data)
        player?.delegate = self
        player?.prepareToPlay()
        player?.play()
        isSpeaking = true
    }

    private func speakOnDevice(_ text: String) {
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = AVSpeechSynthesisVoice(language: "en-US")
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate * 0.9
        isSpeaking = true
        synthesizer.speak(utterance)
    }

    func stop() {
        player?.stop()
        player = nil
        synthesizer.stopSpeaking(at: .immediate)
        isSpeaking = false
        usingBackendVoice = false
    }
    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) { Task { @MainActor in self.isSpeaking = false } }
    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) { Task { @MainActor in self.isSpeaking = self.synthesizer.isSpeaking } }
}

extension LessonSpeech: AVAudioPlayerDelegate {
    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in self.isSpeaking = false }
    }
}

struct LocalPDFView: NSViewRepresentable {
    let document: PDFDocument
    func makeNSView(context: Context) -> PDFView { let view = PDFView(); view.autoScales = true; view.document = document; return view }
    func updateNSView(_ view: PDFView, context: Context) { view.document = document }
}

struct LocalMediaChooser: View {
    @State private var url: URL?
    @State private var scoped = false
    @State private var player: AVPlayer?
    @State private var image: NSImage?
    @State private var pdf: PDFDocument?
    @State private var error: String?
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack { SectionHeading(title: "Your local learning assets"); Spacer(); Button("Choose local media") { choose() }.buttonStyle(LuminfestButtonStyle(primary: false)).accessibilityIdentifier("media.import") }
            Text("User-selected, read-only movie, audio, image or PDF. Local assets are not uploaded or used for training. No automatic network downloads.").font(.system(size: 11)).foregroundStyle(Palette.secondary)
            if let url { Text(url.lastPathComponent).font(.system(size: 12, weight: .medium)) }
            if let player { VideoPlayer(player: player).frame(height: 250) }
            if let image { Image(nsImage: image).resizable().scaledToFit().frame(maxHeight: 320) }
            if let pdf { LocalPDFView(document: pdf).frame(height: 350) }
            if let error { Text(error).font(.system(size: 11)).foregroundStyle(Palette.secondary) }
        }.onDisappear { release() }
    }
    func release() {
        player?.pause(); player = nil; image = nil; pdf = nil
        if scoped { url?.stopAccessingSecurityScopedResource() }
        url = nil; scoped = false
    }
    func choose() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.movie, .audio, .image, .pdf]
        panel.allowsMultipleSelection = false; panel.canChooseDirectories = false
        panel.title = "Choose a local learning asset (read-only)"
        guard panel.runModal() == .OK, let selected = panel.url, selected.isFileURL else { return }
        release(); error = nil
        url = selected; scoped = selected.startAccessingSecurityScopedResource()
        guard let type = try? selected.resourceValues(forKeys: [.contentTypeKey]).contentType else { error = "The selected file type could not be verified."; return }
        if type.conforms(to: .pdf) { pdf = PDFDocument(url: selected); if pdf == nil { error = "This PDF could not be read." } }
        else if type.conforms(to: .image) { image = NSImage(contentsOf: selected); if image == nil { error = "This image could not be read." } }
        else if type.conforms(to: .movie) || type.conforms(to: .audio) { player = AVPlayer(url: selected) }
        else { error = "Only local movie, audio, image and PDF files are allowed."; release() }
    }
}

struct LessonPresentation: View {
    let lesson: JSON
    @Environment(\.dismiss) private var dismiss
    @State private var index = 0
    var blocks: [JSON] { lesson["blocks"].array.filter { LessonBlock.kinds.contains($0["kind"].string) || $0["kind"].string.isEmpty } }
    var count: Int { max(1, blocks.count + (lesson["simulation"].isNull ? 0 : 1)) }
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack { Eyebrow(text: "EXPLAIN MODE · NATIVE LESSON SLIDES"); Spacer(); Button("Done") { dismiss() }.keyboardShortcut(.cancelAction) }
            Text(lesson["title"].string).font(.system(size: 25, weight: .semibold))
            ScrollView {
                if index < blocks.count { LessonBlock(block: blocks[index]) }
                else if !lesson["simulation"].isNull { SimulationView(schema: lesson["simulation"]) }
                else { Text("No lesson slides available.") }
            }.frame(maxWidth: .infinity, maxHeight: .infinity)
            HStack {
                Button("Back") { index = max(0,index-1) }.keyboardShortcut(.leftArrow, modifiers: []).disabled(index == 0)
                Spacer(); Text("Slide \(index+1) of \(count)").font(.system(size: 12)); Spacer()
                Button("Next") { index = min(count-1,index+1) }.keyboardShortcut(.rightArrow, modifiers: []).disabled(index >= count-1)
            }
            Text("Use ← and → to navigate. Original lesson text and native diagrams only; no Office export, camera access or recording.").font(.system(size: 10)).foregroundStyle(Palette.secondary)
        }.padding(28).frame(minWidth: 760, minHeight: 620).background(Palette.background)
    }
}

// ---------------------------------------------------------------- external embeds
//
// Two providers may render *inside* the lesson: YouTube (youtube-nocookie) for curated
// video, and PhET for verified simulations. Everything else — Gizmos included — is a
// deep link into the learner's own signed-in browser session. The allowlist is the whole
// gate: a card that arrives with an embeddable-looking URL for any other host is
// downgraded to a link rather than rendered, so a compromised backend cannot turn the
// lesson surface into a general web view.

enum MediaEmbed {
    static let hosts: Set<String> = [
        "www.youtube-nocookie.com", "youtube-nocookie.com",
        "www.youtube.com", "youtube.com",
        "phet.colorado.edu",
    ]
    static func url(_ raw: String) -> URL? {
        guard let u = URL(string: raw), u.scheme?.lowercased() == "https",
              let host = u.host?.lowercased(), hosts.contains(host),
              u.user == nil, u.password == nil, !u.path.isEmpty else { return nil }
        return u
    }
}

/// One provider-hosted player. The page is served by the provider itself; nothing is
/// downloaded, re-hosted or proxied, and the web view navigates nowhere else.
struct EmbeddedLessonWebView: NSViewRepresentable {
    let url: URL
    func makeNSView(context: Context) -> WKWebView {
        // Inline media playback is macOS WebView's default; the iOS toggle does not exist here.
        let configuration = WKWebViewConfiguration()
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.navigationDelegate = context.coordinator
        // The lesson background shows through before the player paints.
        view.underPageBackgroundColor = .clear
        view.setValue(false, forKey: "drawsBackground")
        view.load(URLRequest(url: url))
        return view
    }
    func updateNSView(_ view: WKWebView, context: Context) {
        if view.url != url { view.load(URLRequest(url: url)) }
    }
    func makeCoordinator() -> Coordinator { Coordinator() }
    final class Coordinator: NSObject, WKNavigationDelegate {
        // Only the initial provider URL loads; any navigation away from the same host is
        // refused and opened in the browser instead, so the embed cannot become a browser.
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let host = navigationAction.request.url?.host?.lowercased(),
                  MediaEmbed.hosts.contains(host), navigationAction.request.url?.scheme?.lowercased() == "https" else {
                if let url = navigationAction.request.url { NSWorkspace.shared.open(url) }
                decisionHandler(.cancel); return
            }
            decisionHandler(.allow)
        }
    }
}

// ---------------------------------------------------------------- narrated deck

/// The NotebookLM-style deck, assembled by the backend and rendered as native slides:
/// single narrator, audio-led timing, one visual per slide, and the script/timeline kept
/// editable alongside the render.
struct NarratedDeckView: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss
    @State private var index = 0
    private var deck: JSON { store.deckData }
    private var slides: [JSON] { deck["slides"].array }
    private var method: JSON { deck["method"] }
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 5) {
                    Eyebrow(text: "NARRATED DECK · SINGLE NARRATOR · AUDIO-LED")
                    Text(deck.text("title", fallback: "Narrated deck")).font(.system(size: 24, weight: .semibold))
                }
                Spacer()
                if !slides.isEmpty {
                    Button { saveHTML() } label: { Label("Export HTML", systemImage: "square.and.arrow.up") }
                        .buttonStyle(LuminfestButtonStyle(primary: false)).accessibilityIdentifier("deck.export")
                }
                Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
            }
            if store.deckBusy {
                HStack { ProgressView().controlSize(.small); Text("Assembling the deck from this lesson…").font(.system(size: 12)).foregroundStyle(Palette.secondary) }.padding(.vertical, 60).frame(maxWidth: .infinity)
            } else if slides.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("No deck is loaded.").font(.system(size: 14, weight: .medium))
                    Text(store.deck["error"].string.isEmpty ? "Build one from the lesson toolbar." : store.deck["error"].string)
                        .font(.system(size: 12)).foregroundStyle(Palette.secondary)
                }.padding(.vertical, 60).frame(maxWidth: .infinity)
            } else {
                if let slide = slides.indices.contains(index) ? slides[index] : nil { slideView(slide) }
                HStack {
                    Button("Back") { index = max(0, index - 1) }.keyboardShortcut(.leftArrow, modifiers: []).disabled(index == 0)
                    Spacer()
                    Text("Slide \(index + 1) of \(slides.count) · \(deck.text("total_seconds", fallback: "—"))s estimated narration")
                        .font(.system(size: 12)).foregroundStyle(Palette.secondary)
                    Spacer()
                    Button("Next") { index = min(slides.count - 1, index + 1) }.keyboardShortcut(.rightArrow, modifiers: []).disabled(index >= slides.count - 1)
                }
                Text("Timing is the narration estimate plus a 0.6s pad, accumulated audio-first. The script and timeline are data you can edit; the HTML export is self-contained and opens offline.")
                    .font(.system(size: 10)).foregroundStyle(Palette.secondary)
                if !method["assembly"].string.isEmpty {
                    Text(method["assembly"].string).font(.system(size: 9)).foregroundStyle(Palette.tertiary)
                }
            }
        }
        .padding(28).frame(minWidth: 780, minHeight: 640).background(Palette.background)
    }

    private func slideView(_ slide: JSON) -> some View {
        ScrollView(.vertical) {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Tag(text: slide.text("layout", fallback: "slide").uppercased(), color: Palette.lavender)
                    Spacer()
                    Text("\(slide.text("start")) – \(slide.text("end")) · \(slide.text("duration"))s")
                        .font(.system(size: 10, design: .monospaced)).foregroundStyle(Palette.tertiary)
                }
                Text(slide.text("title", fallback: "Untitled slide")).font(.system(size: 22, weight: .semibold))
                if !slide["formula"].string.isEmpty {
                    Text(slide["formula"].string).font(.system(size: 18, weight: .medium, design: .serif))
                        .textSelection(.enabled).padding(14).frame(maxWidth: .infinity, alignment: .leading)
                        .background(Palette.sage, in: RoundedRectangle(cornerRadius: 12))
                        .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Palette.forest.opacity(0.3), lineWidth: 1))
                }
                if !slide["bullets"].array.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(Array(slide["bullets"].array.enumerated()), id: \.offset) { _, bullet in
                            Label(bullet.string, systemImage: "circle.fill")
                                .labelStyle(TinyDotLabelStyle())
                                .font(.system(size: 13)).foregroundStyle(Palette.ink)
                        }
                    }
                }
                if slide["visual"]["type"].string == "generated_figure", !slide["visual"]["svg"].string.isEmpty {
                    InlineSVGView(svg: slide["visual"]["svg"].string)
                        .padding(10).frame(maxWidth: .infinity)
                        .background(Palette.surfaceSubtle, in: RoundedRectangle(cornerRadius: 12))
                } else if slide["visual"]["type"].string == "photograph",
                          !slide["visual"]["url"].string.isEmpty {
                    // A real, licence-cleared photograph. This branch is why the deck stopped
                    // drawing a decorative pattern where a picture belongs: the backend was
                    // attaching a photograph to the slide and the client ignored the field,
                    // so a curated image existed on the wire and never reached the slide.
                    DeckPhotograph(visual: slide["visual"], height: 190)
                } else if let art = LuminfestArt.image(LuminfestArt.name(at: index)) {
                    // Slides without a generated figure get a bundled illustration instead of
                    // bare text — cycled deterministically so the deck feels art-directed.
                    ArtImage(image: art, cornerRadius: 14)
                        .frame(height: 190)
                }
                if !slide.text("narration").isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Eyebrow(text: "NARRATION")
                        Text(slide["narration"].string).font(.system(size: 12)).lineSpacing(4).foregroundStyle(Palette.ink).textSelection(.enabled)
                    }.padding(12).frame(maxWidth: .infinity, alignment: .leading)
                        .background(Palette.peach.opacity(0.85), in: RoundedRectangle(cornerRadius: 12))
                }
                if !slide.text("speaker_notes").isEmpty {
                    Text("Speaker note. " + slide["speaker_notes"].string).font(.system(size: 11)).foregroundStyle(Palette.secondary)
                }
                if !slide.text("citation").isEmpty {
                    Text("Source: " + slide["citation"].string).font(.system(size: 10)).foregroundStyle(Palette.secondary)
                }
            }.padding(.vertical, 6).frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func saveHTML() {
        let html = deck["html"].string
        guard !html.isEmpty else { return }
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.html]
        panel.nameFieldStringValue = (deck.text("title", fallback: "deck")
            .replacingOccurrences(of: "/", with: "-")) + ".html"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do { try html.write(to: url, atomically: true, encoding: .utf8); store.notice = "Deck exported to " + url.lastPathComponent }
        catch { store.error = "The deck could not be saved: " + error.localizedDescription }
    }
}

struct TinyDotLabelStyle: LabelStyle {
    func makeBody(configuration: Configuration) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 7) {
            configuration.icon.font(.system(size: 4)).foregroundStyle(Palette.peachDeep)
            configuration.title
        }
    }
}

/// A licence-cleared photograph on a deck slide.
///
/// The bytes come through `store.api.artifact`, not `AsyncImage`: the media route is
/// bearer-protected, so a URL handed straight to a web view would render a 401 and the slide
/// would look empty for a reason nobody could see. The attribution is drawn with the picture
/// because it is a condition of the licence rather than decoration — a photograph shown
/// without its credit is a photograph this project may not show.
struct DeckPhotograph: View {
    let visual: JSON
    var height: CGFloat = 190
    @EnvironmentObject var store: AppStore
    @State private var image: NSImage?
    @State private var failed = false

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Group {
                if let image {
                    Image(nsImage: image).resizable().scaledToFill()
                        .frame(height: height)
                        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                } else if failed {
                    Label("This slide's photograph could not be loaded.", systemImage: "photo.badge.exclamationmark")
                        .font(.system(size: 10)).foregroundStyle(Palette.secondary)
                        .frame(height: height).frame(maxWidth: .infinity)
                        .background(Palette.muted, in: RoundedRectangle(cornerRadius: 14))
                } else {
                    RoundedRectangle(cornerRadius: 14).fill(Palette.muted)
                        .frame(height: height)
                        .overlay(ProgressView().controlSize(.small))
                }
            }
            .frame(maxWidth: .infinity)
            if !credit.isEmpty {
                Text(credit).font(.system(size: 9)).foregroundStyle(Palette.tertiary)
                    .lineLimit(2).fixedSize(horizontal: false, vertical: true)
            }
        }
        .task(id: visual["url"].string) { await load() }
    }

    private var credit: String {
        let text = visual["credit"].string
        if !text.isEmpty { return text }
        // A row that carries a licence but no attribution sentence still has to say something
        // true about where the picture came from.
        let licence = visual["licence"].string
        let title = visual["title"].string
        return [title, licence].filter { !$0.isEmpty }.joined(separator: " · ")
    }

    private func load() async {
        guard image == nil, !failed else { return }
        let path = visual["url"].string
        guard path.hasPrefix("/api/v1/") else { failed = true; return }
        do {
            let data = try await store.api.artifact(path)
            if let decoded = NSImage(data: data) { image = decoded } else { failed = true }
        } catch {
            failed = true
        }
    }
}

/// Deterministic SVG figures rendered inline. A figure is backend-computed geometry, not a
/// fetched image, so it is safe to render — anything that is not well-formed simply does
/// not draw.
struct InlineSVGView: NSViewRepresentable {
    let svg: String
    func makeNSView(context: Context) -> WKWebView {
        let view = WKWebView(frame: .zero)
        view.underPageBackgroundColor = .clear
        view.setValue(false, forKey: "drawsBackground")
        view.loadHTMLString("<html><head><meta charset='utf-8'><style>body{margin:0;background:transparent;}svg{max-width:100%;height:auto;}</style></head><body>\(svg)</body></html>", baseURL: nil)
        return view
    }
    func updateNSView(_ view: WKWebView, context: Context) {}
}

// ---------------------------------------------------------------- external simulations

/// The concept-to-simulation map for the current concept: PhET embeds where verified,
/// Gizmos as a deep link into the operator's own signed-in session, and the named gap
/// when nothing credible matches. A simulation is never evidence — the card says so.
struct ExternalSimulationsCard: View {
    @EnvironmentObject var store: AppStore
    var body: some View {
        let payload = store.conceptSimulations
        let sims = payload["simulations"].array
        return VStack(alignment: .leading, spacing: 14) {
            HStack {
                SectionHeading(title: "Experiment with a simulation")
                Spacer()
                if store.conceptSimulationsBusy { ProgressView().controlSize(.small) }
                else { Button("Find simulations") { store.run { await store.loadConceptSimulations() } }
                        .buttonStyle(LuminfestButtonStyle(primary: false)).accessibilityIdentifier("sims.find") }
            }
            if sims.isEmpty && !payload.isNull {
                Text(payload["gap"].string.isEmpty
                     ? "No simulation is offered for this concept; the gap is published rather than filled with the least-bad match."
                     : payload["gap"].string)
                    .font(.system(size: 11)).foregroundStyle(Palette.secondary)
            }
            ForEach(Array(sims.enumerated()), id: \.offset) { _, sim in
                NativeMediaView(media: sim)
                    .onAppear {
                        // An embed the learner actually sees counts as opened; a deep-link
                        // card does not fire until they tap it (handled by the card's link).
                        if sim["open_mode"].string == "embed_in_lesson"
                            || sim["status"].string == "verified_embed" {
                            let concept = store.selectedConcept
                            store.run { await store.recordExternalSimulationOpened(concept: concept) }
                        }
                    }
            }
            if !sims.isEmpty {
                // True of the third-party simulations this card shows, and of nothing else:
                // a playground game is first-party, checks the learner's answer and reports
                // it, so it *is* evidence. The two claims must not be made in one voice.
                Text("A third-party simulation (PhET, Gizmos) reports nothing back to this app, so time spent here is practice for you, not evidence for the record. Playground games are first-party and do count.")
                    .font(.system(size: 10)).foregroundStyle(Palette.secondary)
            }
        }
    }
}
