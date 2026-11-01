import SwiftUI
import WebKit

// MARK: - Stage store

/// State for the big central Stage. One stage per concept.
///
/// The Stage used to own a second, narrower board: the learner drew strokes through
/// the ``/whiteboards/{id}/ink`` op-log while the tutor's whiteboard_* tools wrote
/// *nodes* through ``/boards/{id}``. Two documents, two schemas, and never a shared
/// surface — which is why the tutor could draw on a board the learner could not see,
/// and why "the whiteboard does not work" was the single loudest complaint. The
/// backend now resolves both ids to one node board, and the Stage therefore owns
/// **one** store: the node board. The op-log route still exists for the student-ink
/// hand-off (a raised hand strips its strokes back to the teacher), because that is
/// a separate concern with a separate permission model, but nothing on the Stage
/// draws through it any more.
@MainActor final class StageStore: ObservableObject {
    enum Mode: String, CaseIterable, Identifiable {
        case whiteboard = "Whiteboard", deck = "Deck", cards = "Cards", web = "Web", assets = "Assets"
        var id: String { rawValue }
    }

    @Published var mode: Mode = .whiteboard
    @Published var board: JSON = .null
    @Published var boardError = ""
    /// The node board this concept's editor and the tutor's tools share. Held here
    /// rather than in the view so switching Stage tabs does not discard the canvas,
    /// its selection or its undo history.
    var board2: BoardStore?
    @Published var liveStrokes: [String] = []          // remote strokes being previewed
    @Published var handRaised = false
    @Published var note = ""

    @Published var taJobs: [JSON] = []
    @Published var taResults: [JSON] = []
    @Published var taDraft = ""
    @Published var taBusy = false

    @Published var assets: [JSON] = []
    @Published var webURLString = ""

    private var pollTask: Task<Void, Never>?
    private var resultsCursor: Double = 0

    var boardID: String {
        let concept = store?.selectedConcept ?? ""
        return concept.isEmpty ? "wb-general" : "wb-\(concept)"
    }
    var isTeacher: Bool {
        guard let store else { return false }
        return ["teacher", "staff", "admin"].contains(store.user["role"].string)
    }
    var boardVersion: Int { board["version"].int }
    weak var store: AppStore?

    func bind(_ store: AppStore) { self.store = store }

    // MARK: - the node board the tutor and the learner share

    /// The concept's node board, created on first use and kept for the session.
    ///
    /// The id is `board-<concept_id>`, which is the *same* document the tutor's
    /// whiteboard_* tools write (`whiteboard.concept_node_id` maps the legacy
    /// `wb-<concept_id>` spelling onto it). Deliberately not `@Published`: it is a
    /// reference type the editor observes itself, and publishing it would re-render
    /// the whole Stage on every node mutation.
    ///
    /// The store is replaced only when the *concept* changes — never because
    /// ``boardID`` is momentarily empty. ``ensureNodeBoard`` runs inside ``body``,
    /// so an identity check on ``boardID`` fired on every re-render (the 2.5s poll
    /// publishes ``board``, which re-renders the Stage): each pass threw away the
    /// store the learner was drawing in and built a fresh empty one, which is why
    /// blocks, lines and text vanished a few seconds after being drawn.
    private var boardConcept = ""

    func ensureNodeBoard() -> BoardStore? {
        guard let store else { return nil }
        let concept = store.selectedConcept
        guard !concept.isEmpty else { return nil }
        let wanted = BoardStore.id(forConcept: concept)
        if board2 == nil || boardConcept != concept {
            // The previous concept's board is a different document, so its poll goes
            // with it. Leaving it running would read another concept's board forever.
            board2?.stopPolling()
            board2 = BoardStore(api: store.api)
            boardConcept = concept
            ImageCache.shared.bind(api: store.api)
            let fresh = board2
            Task { await fresh?.loadExisting(wanted) }
            // Poll from the start, not from the first successful load: the board may
            // not exist yet, and a tutor who draws first is the one who creates it.
            fresh?.startPolling()
        }
        return board2
    }

    func startPolling() {
        guard pollTask == nil, let store else { return }
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                try? await Task.sleep(nanoseconds: 2_500_000_000)
            }
        }
    }

    func stopPolling() {
        pollTask?.cancel()
        pollTask = nil
    }

    func refresh() async {
        guard let store, store.authenticated, !store.selectedConcept.isEmpty else { return }
        do {
            let result = try await store.api.json("/whiteboards/\(boardID)")
            if !result["board"].isNull, result["board"]["version"].int != board["version"].int {
                board = result["board"]
            }
            if isTeacher { await refreshTA() }
            boardError = ""
        } catch {
            boardError = "Board unavailable: \((error as? AppFailure)?.message ?? "backend unreachable")"
        }
    }

    // ---- student ink / teacher hand strokes ----

    func pushStroke(_ points: [[Double]], raiseHand: Bool = false) async {
        guard let store, !points.isEmpty else { return }
        // Drawing is working. Without this the interval check would treat a learner who is
        // mid-diagram as idle and interrupt them.
        store.noteLearnerAction()
        do {
            _ = try await store.api.json("/whiteboards/\(boardID)/ink", method: "POST",
                                         body: ["op": ["type": "path", "points": points],
                                                "raise_hand": raiseHand])
            note = ""
            await refresh()
        } catch {
            note = "Stroke rejected: \((error as? AppFailure)?.message ?? "unavailable")"
        }
    }

    func ackHands() async {
        guard let store else { return }
        do {
            _ = try await store.api.json("/whiteboards/\(boardID)/ack", method: "POST", body: nil)
            await refresh()
        } catch {
            note = "Acknowledge failed: \((error as? AppFailure)?.message ?? "unavailable")"
        }
    }

    func raiseHand(_ message: String) async {
        guard let store else { return }
        do {
            _ = try await store.api.json("/whiteboards/\(boardID)/ink", method: "POST",
                                         body: ["op": ["type": "path", "points": []],
                                                "raise_hand": true, "message": message])
            handRaised = true
            note = "Hand raised — your tutor will address it next turn."
        } catch {
            note = "Interrupt rejected: \((error as? AppFailure)?.message ?? "unavailable")"
        }
    }

    // ---- TA ----

    func dispatchTA() async {
        guard let store else { return }
        let message = taDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !message.isEmpty, !taBusy else { return }
        taBusy = true
        defer { taBusy = false }
        do {
            _ = try await store.api.json("/ta/dispatch", method: "POST",
                                         body: ["message": message, "concept_id": store.selectedConcept])
            taDraft = ""
            note = "TA dispatched — results will appear here when ready."
            await refreshTA()
        } catch {
            note = "TA refused: \((error as? AppFailure)?.message ?? "unavailable")"
        }
    }

    func refreshTA() async {
        guard let store else { return }
        do {
            let status = try await store.api.json("/ta/status")
            taJobs = status["jobs"].array
            let results = try await store.api.json("/ta/results?since=\(resultsCursor)")
            let fresh = results["results"].array
            if let last = fresh.last, last["created_at"].double > resultsCursor {
                resultsCursor = last["created_at"].double
            }
            if !fresh.isEmpty { taResults = (fresh + taResults).prefix(12).map { $0 } }
        } catch { /* TA feed refresh failures are silent: it is a background convenience */ }
    }

    // ---- assets ----

    func loadAssets() async {
        guard let store else { return }
        do {
            let result = try await store.api.json("/sims")
            assets = (result["artifacts"].isNull ? result["sims"].array : result["artifacts"].array)
        } catch { assets = [] }
    }

    func openInStageWeb(_ urlString: String) {
        webURLString = urlString
        mode = .web
    }
}

// MARK: - TTS button

/// Small read-aloud toggle used on tutor transcript rows. On-device voice only.
struct SpeakerButton: View {
    let text: String
    @StateObject private var voice = VoiceIO()
    var body: some View {
        Button {
            if voice.speaking { voice.stopSpeaking() } else { voice.speak(text) }
        } label: {
            Image(systemName: voice.speaking ? "speaker.wave.3.fill" : "speaker.wave.2")
                .font(.system(size: 10))
        }
        .buttonStyle(.plain)
        .foregroundStyle(Palette.secondary)
        .help("Read this reply aloud (on-device voice)")
    }
}

// MARK: - Stage view

struct StageView: View {
    @EnvironmentObject var store: AppStore
    @StateObject private var stage = StageStore()
    @StateObject private var voice = VoiceIO()
    /// Duplex voice to OpenAI Realtime. Used when a key is configured; the push-to-talk
    /// ``VoiceIO`` is suppressed while this is connected to avoid two mic captures.
    @StateObject private var realtime = VoiceRealtime()

    var body: some View {
        Card(padding: 18) {
            VStack(alignment: .leading, spacing: 12) {
                header
                if !stage.note.isEmpty {
                    Text(stage.note).font(.system(size: 11, weight: .medium))
                        .foregroundStyle(Palette.peachDeep)
                }
                switch stage.mode {
                case .whiteboard:
                    // The real editor, bound to the node board the tutor's tools write.
                    // The old `BoardPane` (pen + three colours + a click-drag) is gone:
                    // it wrote to the retired op-log, so the tutor and the learner were
                    // looking at two different boards.
                    if let board = stage.ensureNodeBoard() {
                        BoardEditor(board: board, conceptID: store.selectedConcept)
                    } else {
                        Text("Select a concept to open its board.")
                            .font(.system(size: 11)).foregroundStyle(Palette.tertiary)
                            .frame(maxWidth: .infinity, minHeight: 360)
                    }
                case .deck: DeckPane(store: store)
                case .cards: FlashcardsView(store: store)
                case .web: WebPane(stage: stage)
                case .assets: AssetsPane(stage: stage)
                }
                if stage.isTeacher { TAFeed(stage: stage).padding(.top, 2) }
            }
        }
        .onAppear {
            stage.bind(store)
            voice.onFinal = { text in
                let said = text
                store.run {
                    await store.sendMessage(said)
                    // In conversation mode the reply has to be spoken, or the exchange is
                    // one-directional and the learner has to reach for the speaker button
                    // after every turn. In push-to-talk mode nothing changes: the learner
                    // asked for one transcript, not a conversation.
                    guard voice.conversation else { return }
                    let last = store.messages.last(where: { $0["role"].string != "user" })
                    let reply = last?.text("content", fallback: last?.text("message", fallback: "") ?? "") ?? ""
                    if !reply.isEmpty { voice.speak(reply) }
                }
            }
            stage.startPolling()
            Task { await stage.loadAssets() }
        }
        .onChange(of: stage.mode) { _, mode in
            // A Stage tab change is the clearest "what did the learner reach for" signal the
            // app has: it distinguishes a learner who read the deck from one who went straight
            // to the cards. Recorded coarsely and never scored.
            store.recordInteraction("stage.tab." + ClickTelemetry.sanitise(mode.rawValue))
        }
        .onDisappear { stage.stopPolling() }
    }

    /// The Stage header.
    ///
    /// The actions sit in a ``ViewThatFits``, not a plain `HStack`. SwiftUI does not truncate
    /// a `Label` that is given less width than it needs — it wraps *mid-word*, so a narrow
    /// panel drew "Converse" as a column of single letters ("C / on / ve / rs / e") and
    /// "Raise hand" as "Rai / se / han / d". Five buttons beside a 360-pt picker do not fit a
    /// side panel, and the squeezed result reads as a broken app rather than a busy one. The
    /// compact variant keeps the icons and drops the words; every button keeps its `help`
    /// text either way, so nothing becomes undiscoverable.
    @ViewBuilder
    private var header: some View {
        ViewThatFits(in: .horizontal) {
            headerRow(compact: false)
            headerRow(compact: true)
        }
    }

    /// A `Label` when there is room for the words, the bare icon when there is not. The wide
    /// variant is `.fixedSize()`d as well: `ViewThatFits` measures ideal widths, and a label
    /// that is allowed to compress would report a smaller ideal width than it needs and be
    /// chosen anyway — which is the bug this pair exists to prevent.
    @ViewBuilder
    private func stageLabel(_ title: String, _ symbol: String, compact: Bool) -> some View {
        if compact {
            Image(systemName: symbol)
        } else {
            Label(title, systemImage: symbol)
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
        }
    }

    @ViewBuilder
    private func headerRow(compact: Bool) -> some View {
        HStack(spacing: 10) {
            Text("STAGE")
                .font(.system(size: 9, weight: .semibold))
                .tracking(1.4)
                .foregroundStyle(Palette.secondary)
                .fixedSize()
            Picker("", selection: $stage.mode) {
                ForEach(StageStore.Mode.allCases) { mode in Text(mode.rawValue).tag(mode) }
            }.pickerStyle(.segmented).frame(width: compact ? 190 : 360)
            Spacer(minLength: 6)
            // TTS: read the tutor's latest reply aloud on-device.
            Button {
                store.recordInteraction("voice.speak")
                let last = store.messages.last(where: { $0["role"].string != "user" })
                let text = last?.text("content", fallback: last?.text("message", fallback: "") ?? "")
                if voice.speaking { voice.stopSpeaking() } else { voice.speak(text ?? "") }
            } label: {
                Image(systemName: voice.speaking ? "speaker.wave.3" : "speaker.wave.2")
            }.buttonStyle(LuminfestButtonStyle(primary: false))
                .disabled(store.messages.isEmpty)
                .help("Read the tutor's latest reply aloud (on-device voice)")
            // ASR: push-to-talk → transcript goes straight into the tutor chat.
            Button {
                store.recordInteraction("voice.dictate")
                voice.toggle()
            } label: {
                stageLabel(voice.listening && !voice.conversation ? "Stop" : "Speak",
                           voice.listening && !voice.conversation ? "mic.fill" : "mic",
                           compact: compact)
            }.buttonStyle(LuminfestButtonStyle(primary: voice.listening && !voice.conversation))
                .disabled(realtime.connected || voice.conversation)
                .help(realtime.connected ? "Voice chat is active" : "Dictate a message to the tutor (on-device speech recognition)")
            // Continuous local conversation: the microphone stays open, an energy detector
            // finds the end of each utterance, and the tutor's reply is spoken - with the
            // reply cut off the moment the learner talks over it. On-device, no API key, and
            // no audio leaves this machine (unlike the cloud voice chat beside it).
            Button {
                store.recordInteraction("voice.conversation")
                voice.toggleConversation()
            } label: {
                stageLabel(voice.conversation ? "End" : "Converse",
                           voice.conversation ? "bubble.left.and.bubble.right.fill" : "bubble.left.and.bubble.right",
                           compact: compact)
            }.buttonStyle(LuminfestButtonStyle(primary: voice.conversation))
                .disabled(realtime.connected)
                .help(realtime.connected ? "Cloud voice chat is active"
                      : "Talk back and forth with the tutor on this Mac — no API key, no audio uploaded")
            // Duplex voice chat: a live, two-way conversation with the tutor through
            // OpenAI Realtime. Requires an API key entered in Settings.
            Button {
                realtime.toggle()
            } label: {
                stageLabel(realtime.connected ? "End voice chat" : "Voice chat",
                           realtime.connected ? "waveform.circle.fill" : "waveform.circle",
                           compact: compact)
            }.buttonStyle(LuminfestButtonStyle(primary: realtime.connected))
                .help(realtime.connected ? "End the live voice conversation" : "Start a live voice conversation with the tutor (OpenAI Realtime)")
            if stage.isTeacher {
                Button {
                    Task { await stage.ackHands() }
                } label: { stageLabel("Clear hands", "hand.raised.slash", compact: compact) }
                    .buttonStyle(LuminfestButtonStyle(primary: false))
                    .help("Acknowledge raised hands without a tutor turn")
            } else {
                Button {
                    Task { await stage.raiseHand("") }
                } label: { stageLabel("Raise hand", "hand.raised", compact: compact) }
                    .buttonStyle(LuminfestButtonStyle(primary: stage.handRaised))
                    .disabled(stage.handRaised)
            }
        }
        if voice.listening || !voice.status.isEmpty {
            HStack(spacing: 8) {
                Circle().fill(voice.conversation ? Palette.forest : Palette.peachDeep).frame(width: 6, height: 6)
                // A live input meter, because the one question a learner has in continuous
                // mode is "is it hearing me?" - and a status word cannot answer it.
                if voice.conversation {
                    GeometryReader { proxy in
                        ZStack(alignment: .leading) {
                            Capsule().fill(Palette.muted)
                            Capsule().fill(voice.speaking ? Palette.peachDeep : Palette.forest)
                                .frame(width: max(2, proxy.size.width * voice.level))
                        }
                    }
                    .frame(width: 54, height: 4)
                }
                Text(voice.transcript.isEmpty ? (voice.status.isEmpty ? "listening…" : voice.status) : voice.transcript)
                    .font(.system(size: 11)).foregroundStyle(Palette.secondary).lineLimit(1)
            }
        }
        if realtime.connected || realtime.error != nil {
            HStack(spacing: 8) {
                Circle().fill(realtime.connected ? Palette.forest : Color.orange).frame(width: 6, height: 6)
                let caption = realtime.error
                    ?? (realtime.localTranscript.isEmpty
                        ? realtime.status
                        : realtime.localTranscript + (realtime.remoteTranscript.isEmpty ? "" : "  ·  " + realtime.remoteTranscript))
                Text(caption).font(.system(size: 11)).foregroundStyle(Palette.secondary).lineLimit(1)
            }
        }
    }
}

// MARK: - Whiteboard pane

struct BoardPane: View {
    @ObservedObject var stage: StageStore
    @State private var draft: [CGPoint] = []
    @State private var colour = "forest"
    @State private var writing = false
    @State private var textDraft = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            toolbar
            ZStack {
                RoundedRectangle(cornerRadius: 12).fill(Color.white)
                GeometryReader { geo in
                    Canvas { context, _ in
                        draw(doc: stage.board, in: geo.size, context: &context)
                        if draft.count > 1 {
                            var path = Path()
                            path.move(to: draft[0])
                            for point in draft.dropFirst() { path.addLine(to: point) }
                            context.stroke(path, with: .color(Palette.forest), style: StrokeStyle(lineWidth: 2.5, lineCap: .round, lineJoin: .round))
                        }
                    }
                    .gesture(drag(in: geo.size))
                    .onTapGesture { } // reserved for anchor selection (P1)
                }
                if stage.board["version"].int == 0 && stage.boardError.isEmpty {
                    Text("Loading board…").font(.system(size: 11)).foregroundStyle(Palette.tertiary)
                }
                if !stage.boardError.isEmpty {
                    Text(stage.boardError).font(.system(size: 11)).foregroundStyle(Palette.tertiary).padding()
                }
            }
            .frame(minHeight: 360)
            .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Palette.line))
            legend
        }
    }

    private var toolbar: some View {
        HStack(spacing: 10) {
            Text("PEN").font(.system(size: 8, weight: .semibold)).tracking(1).foregroundStyle(Palette.secondary)
            ForEach([("forest", Palette.forest), ("peach", Palette.peachDeep), ("indigo", Palette.indigoDeep)], id: \.0) { name, tint in
                Circle().fill(tint).frame(width: 14, height: 14)
                    .overlay(Circle().strokeBorder(colour == name ? Palette.ink : .clear, lineWidth: 2))
                    .onTapGesture { colour = name }
            }
            Spacer()
            Button { writing = true } label: { Label("Text", systemImage: "textformat") }
                .buttonStyle(LuminfestButtonStyle(primary: false))
                .help("Write a text block at the centre of the board")
        }
        .alert("Write on the board", isPresented: $writing) {
            TextField("Text…", text: $textDraft)
            Button("Place") {
                let text = textDraft
                textDraft = ""
                guard !text.isEmpty else { return }
                Task { await stage.pushText(text, x: 2000, y: 1250) }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Placed at the centre. The tutor can move or extend it with its own tools.")
        }
    }

    private var legend: some View {
        HStack(spacing: 14) {
            Text("Board \(stage.board["version"].int > 0 ? "v\(stage.board["version"].int)" : "—")")
                .font(.system(size: 9, design: .monospaced)).foregroundStyle(Palette.tertiary)
            let hands = stage.board["interrupts"].array.count
            if hands > 0 {
                Label("\(hands) hand(s) raised", systemImage: "hand.raised.fill")
                    .font(.system(size: 10, weight: .semibold)).foregroundStyle(Palette.peachDeep)
            }
            Spacer()
            Text("Vector ops only — strokes, text, licence-cleared images. The tutor draws here with its whiteboard tools.")
                .font(.system(size: 9)).foregroundStyle(Palette.tertiary)
        }
    }

    private func drag(in size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 1)
            .onChanged { value in
                guard let point = map(value.location, size) else { return }
                draft.append(point)
            }
            .onEnded { _ in
                let points = draft
                draft = []
                guard points.count > 1 else { return }
                let encoded = points.map { [Double($0.x), Double($0.y)] }
                Task { await stage.pushStroke(encoded) }
            }
    }

    /// Canvas pixels → board space coordinates (fit mapping, P0: whole board visible).
    private func map(_ location: CGPoint, _ size: CGSize) -> CGPoint? {
        guard size.width > 1, size.height > 1 else { return nil }
        return CGPoint(x: Double(location.x / size.width) * 4000,
                       y: Double(location.y / size.height) * 2500)
    }

    private func draw(doc: JSON, in size: CGSize, context: inout GraphicsContext) {
        func px(_ v: Double, _ space: Double, _ view: CGFloat) -> CGFloat { CGFloat(v / space) * view }
        for op in doc["layers"]["student_ink"]["ops"].array {
            if let path = strokePath(op, size) {
                context.stroke(path, with: .color(Palette.indigoDeep.opacity(0.75)),
                               style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
            }
        }
        for op in doc["layers"]["board"]["ops"].array {
            switch op["type"].string {
            case "path":
                let path = strokePath(op, size)
                if let path {
                    let colour = op["colour"].string
                    context.stroke(path, with: .color(colour == "peach" ? Palette.peachDeep : colour == "indigo" ? Palette.indigoDeep : Palette.forest),
                                   style: StrokeStyle(lineWidth: 2.5, lineCap: .round, lineJoin: .round))
                }
            case "text":
                let text = op["text"].string
                guard !text.isEmpty else { break }
                let x = px(op["x"].double, 4000, size.width)
                let y = px(op["y"].double, 2500, size.height)
                let fontSize = CGFloat(min(26, max(11, op["size"].double == 0 ? 16 : op["size"].double)))
                let label = Text(text).font(.system(size: fontSize, weight: .medium)).foregroundColor(Palette.ink)
                context.draw(label, at: CGPoint(x: x, y: y), anchor: .leading)
            case "shape":
                let rect = CGRect(x: px(op["x"].double, 4000, size.width),
                                  y: px(op["y"].double, 2500, size.height),
                                  width: px(op["w"].double, 4000, size.width),
                                  height: px(op["h"].double, 2500, size.height))
                let shape = op["shape"].string == "ellipse"
                    ? AnyShape(Ellipse())
                    : AnyShape(Rectangle())
                context.stroke(shape.path(in: rect), with: .color(Palette.peachDeep), lineWidth: 2)
            case "image":
                // P0 renders a labelled chip; bitmap rendering of cached images is P1.
                let x = px(op["x"].double, 4000, size.width)
                let y = px(op["y"].double, 2500, size.height)
                let chip = Text("[img] \(op["title"].string) · \(op["licence"].string)").font(.system(size: 10))
                context.draw(chip, at: CGPoint(x: x, y: y), anchor: .leading)
            default: break
            }
        }
    }

    private func strokePath(_ op: JSON, _ size: CGSize) -> Path? {
        let points = op["points"].array
        guard points.count > 1 else { return nil }
        var path = Path()
        for (index, pair) in points.enumerated() {
            let coords = pair.array
            guard coords.count == 2 else { return nil }
            let x = CGFloat((coords[0].double / 4000) * Double(size.width))
            let y = CGFloat((coords[1].double / 2500) * Double(size.height))
            if index == 0 { path.move(to: CGPoint(x: x, y: y)) } else { path.addLine(to: CGPoint(x: x, y: y)) }
        }
        return path
    }
}

extension StageStore {
    func pushText(_ text: String, x: Double, y: Double) async {
        guard let store else { return }
        do {
            _ = try await store.api.json("/whiteboards/\(boardID)/ink", method: "POST",
                                         body: ["op": ["type": "text", "text": text, "x": x, "y": y],
                                                "raise_hand": false])
            note = ""
            await refresh()
        } catch {
            // Students may not write text blocks: surface the server's verdict verbatim.
            note = "Text rejected: \((error as? AppFailure)?.message ?? "unavailable")"
        }
    }
}

// MARK: - Deck / Web / Assets panes

struct DeckPane: View {
    let store: AppStore
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "film.stack").foregroundStyle(Palette.forest)
                Text("Narrated deck for \(store.currentConcept["title"].string)").font(.system(size: 14, weight: .semibold))
                Spacer()
                Button { store.run { await store.buildDeck() } } label: {
                    Label(store.deckBusy ? "Assembling…" : "Rebuild deck", systemImage: "arrow.clockwise")
                }.buttonStyle(LuminfestButtonStyle(primary: false)).disabled(store.deckBusy)
                Button { store.showDeck = true } label: { Label("Open deck", systemImage: "play.rectangle") }
                    .buttonStyle(LuminfestButtonStyle(primary: true)).disabled(store.deck.isNull)
                Button { store.showDeckEditor = true } label: { Label("Edit deck", systemImage: "slider.horizontal.3") }
                    .buttonStyle(LuminfestButtonStyle(primary: false)).disabled(store.deck.isNull)
                    .accessibilityIdentifier("deck.edit")
            }
            Text(store.deck.isNull
                 ? "No deck assembled for this concept yet. The tutor builds one with generate_slides; it appears here and can be projected full-window."
                 : "Deck ready. Open it to present; the Stage keeps it one click away while you teach.")
                .font(.system(size: 11)).foregroundStyle(Palette.secondary)
            Spacer()
        }.padding(.vertical, 40).padding(.horizontal, 8)
    }
}

struct WebPane: View {
    @ObservedObject var stage: StageStore
    @State private var draftURL = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                TextField("https://…", text: $draftURL)
                    .textFieldStyle(.roundedBorder).font(.system(size: 12))
                    .onSubmit { stage.webURLString = draftURL }
                Button("Go") { stage.webURLString = draftURL }.buttonStyle(LuminfestButtonStyle(primary: false))
                Button { stage.webURLString = "" } label: { Image(systemName: "xmark.circle") }
                    .buttonStyle(LuminfestButtonStyle(primary: false))
                    .help("Close the page and return to an empty preview")
            }
            if stage.webURLString.isEmpty {
                VStack(spacing: 10) {
                    Image(systemName: "safari").font(.system(size: 30)).foregroundStyle(Palette.tertiary)
                    Text("Browser preview — a page opens inside the workspace, so teaching never leaves the room.")
                        .font(.system(size: 11)).foregroundStyle(Palette.secondary)
                }.frame(maxWidth: .infinity, minHeight: 340)
            } else if let url = URL(string: stage.webURLString) {
                StageWebView(url: url).frame(minHeight: 380)
                    .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Palette.line))
                    .clipShape(RoundedRectangle(cornerRadius: 12))
            }
        }
    }
}

struct StageWebView: NSViewRepresentable {
    let url: URL

    func makeNSView(context: Context) -> WKWebView {
        let view = WKWebView()
        view.allowsBackForwardNavigationGestures = true
        view.load(URLRequest(url: url))
        return view
    }

    func updateNSView(_ view: WKWebView, context: Context) {
        if view.url != url { view.load(URLRequest(url: url)) }
    }
}

struct AssetsPane: View {
    @ObservedObject var stage: StageStore
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                if stage.assets.isEmpty {
                    Text("No generated assets yet. When the tutor builds a simulation or slides, they appear here.")
                        .font(.system(size: 11)).foregroundStyle(Palette.secondary).padding(.vertical, 30)
                }
                ForEach(Array(stage.assets.enumerated()), id: \.offset) { _, artifact in
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: artifact["kind"].string == "deck" ? "rectangle.stack" : "dial.min")
                            .foregroundStyle(Palette.forest)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(artifact["title"].string).font(.system(size: 12, weight: .medium))
                            Text("\(artifact["kind"].string) · v\(artifact["versions"].array.last?["version"].int ?? 1)")
                                .font(.system(size: 9, design: .monospaced)).foregroundStyle(Palette.tertiary)
                        }
                        Spacer()
                        Button("Preview") {
                            stage.openInStageWeb("\(stage.store?.endpoint ?? "")/sims/\(artifact["id"].string)/raw")
                        }.buttonStyle(LuminfestButtonStyle(primary: false))
                    }
                    .padding(10)
                    .background(Color.white.opacity(0.9), in: RoundedRectangle(cornerRadius: 11))
                    .overlay(RoundedRectangle(cornerRadius: 11).strokeBorder(Palette.line))
                }
            }.padding(.horizontal, 4)
        }.frame(minHeight: 340)
    }
}

// MARK: - TA feed

struct TAFeed: View {
    @ObservedObject var stage: StageStore

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: "person.2.wave.2").foregroundStyle(Palette.indigoDeep)
                Text("TEACHER'S ASSISTANT").font(.system(size: 8, weight: .semibold)).tracking(1.3).foregroundStyle(Palette.secondary)
                Text("runs in the background; results land here, never on the Stage")
                    .font(.system(size: 9)).foregroundStyle(Palette.tertiary)
                Spacer()
            }
            HStack(spacing: 8) {
                TextField("e.g. find three fractions games and a 4-minute video on equivalent ratios", text: $stage.taDraft)
                    .textFieldStyle(.roundedBorder).font(.system(size: 11))
                    .onSubmit { Task { await stage.dispatchTA() } }
                Button(stage.taBusy ? "Dispatching…" : "Dispatch") {
                    Task { await stage.dispatchTA() }
                }.buttonStyle(LuminfestButtonStyle(primary: true)).disabled(stage.taBusy || stage.taDraft.isEmpty)
            }
            let running = stage.taJobs.filter { ["queued", "running"].contains($0["status"].string) }
            if !running.isEmpty {
                HStack(spacing: 6) {
                    ProgressView().controlSize(.small)
                    Text("\(running.count) TA job(s) in flight").font(.system(size: 10)).foregroundStyle(Palette.secondary)
                }
            }
            ForEach(Array(stage.taResults.enumerated()), id: \.offset) { _, entry in
                VStack(alignment: .leading, spacing: 6) {
                    Text("TA · \(entry["concept_id"].string.isEmpty ? "general" : entry["concept_id"].string)")
                        .font(.system(size: 8, weight: .semibold)).tracking(1).foregroundStyle(Palette.indigoDeep)
                    Text(entry["summary"].string).font(.system(size: 11)).lineSpacing(3)
                        .textSelection(.enabled)
                    ForEach(Array(entry["result"]["cards"].array.enumerated()), id: \.offset) { _, card in
                        HStack(spacing: 8) {
                            Tag(text: card["kind"].string.uppercased(), color: Palette.accentIndigo.soft)
                            Text(card["title"].string).font(.system(size: 10, weight: .medium)).lineLimit(1)
                            if let link = card["url"].string.isEmpty ? (card["watch_url"].string.isEmpty ? nil : URL(string: card["watch_url"].string)) : URL(string: card["url"].string) {
                                Link("Open", destination: link).font(.system(size: 9, weight: .semibold)).foregroundStyle(Palette.forest)
                            }
                            if card["kind"].string == "image" && !card["url"].string.isEmpty {
                                Button("Stage it") { stage.openInStageWeb(card["url"].string) }
                                    .buttonStyle(LuminfestButtonStyle(primary: false))
                            }
                        }
                    }
                }
                .padding(10).frame(maxWidth: .infinity, alignment: .leading)
                .background(Palette.surfaceSubtle, in: RoundedRectangle(cornerRadius: 11))
            }
        }
    }
}
