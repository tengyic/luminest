import SwiftUI
import Foundation

// Flashcards: retrieval practice on the same memory curve as the rest of the harness.
//
// Two ideas shape this surface.
//
// First, a review is a *graded* event, not a right/wrong answer. The four buttons are
// again / hard / good / easy, and each one shows the interval it will produce ("Good · 3d").
// The consequence is on the button because grading honestly is only possible when the
// learner can see what the choice buys -- the same reason the backend returns a per-grade
// preview computed from the FSRS-6 model rather than a hard-coded label.
//
// Second, the session is interleaved across concepts by the server, so the queue here is
// exactly the order the memory curve wants. The client does not re-sort it.

// MARK: - Model

/// One card as the server describes it. Cards from the session endpoint carry a per-grade
/// ``preview``; cards from the browse list do not.
struct Flashcard: Identifiable, Equatable {
    let id: String
    let conceptID: String
    let kind: String
    let front: String
    let back: String
    let hint: String
    let tags: [String]
    let state: String
    let dueAt: Double
    let reps: Int
    let lapses: Int
    let stability: Double
    let difficulty: Double
    let preview: [String: JSON]
    let source: JSON

    var kindLabel: String { kind.replacingOccurrences(of: "_", with: " ").capitalized }

    /// The interval each grade would produce, e.g. "3d". Empty when the server did not
    /// send a preview (browse rows).
    func intervalLabel(_ grade: String) -> String { preview[grade]?["label"].string ?? "" }

    var isDueNow: Bool { dueAt <= Date().timeIntervalSince1970 }

    static func parse(_ json: JSON) -> Flashcard? {
        let front = json["front"].string
        guard !front.isEmpty else { return nil }
        let id = json["id"].string
        return Flashcard(
            id: id.isEmpty ? front : id,           // a dry-run preview card has no id yet
            conceptID: json["concept_id"].string,
            kind: json["kind"].string.isEmpty ? "basic" : json["kind"].string,
            front: front,
            back: json["back"].string,
            hint: json["hint"].string,
            tags: json["tags"].array.map { $0.string },
            state: json["state"].string,
            dueAt: json["due_at"].double,
            reps: json["reps"].int,
            lapses: json["lapses"].int,
            stability: json["stability"].double,
            difficulty: json["difficulty"].double,
            preview: json["preview"].object,
            source: json["source"])
    }
}

/// Which of the deck's two surfaces is showing.
enum FlashTab: String, CaseIterable, Identifiable {
    case study = "Study"
    case browse = "Browse"
    var id: String { rawValue }
}

// MARK: - Store

@MainActor
final class FlashcardStore: ObservableObject {
    /// The due-now queue, already interleaved across concepts by the server.
    @Published private(set) var session: [Flashcard] = []
    @Published private(set) var cursor = 0
    @Published var revealed = false
    @Published private(set) var dueTotal = 0
    /// The whole deck (or the current concept's deck) for the browse surface.
    @Published private(set) var deck: [Flashcard] = []
    @Published private(set) var stats: JSON = .null
    /// Cards a generate action *would* add, shown before it is committed.
    @Published private(set) var preview: [Flashcard] = []
    @Published var busy = false
    @Published var error: String?
    @Published var notice: String?

    private let api: APIClient

    init(api: APIClient) { self.api = api }

    var current: Flashcard? {
        cursor >= 0 && cursor < session.count ? session[cursor] : nil
    }
    var finished: Bool { !session.isEmpty && cursor >= session.count }
    var progressText: String {
        session.isEmpty ? "" : "\(min(cursor + 1, session.count)) of \(session.count)"
    }
    var previewCreated: Int { preview.count }

    private func conceptQuery(_ conceptID: String?) -> [URLQueryItem] {
        guard let conceptID, !conceptID.isEmpty else { return [] }
        return [URLQueryItem(name: "concept_id", value: conceptID)]
    }

    // ---------------------------------------------------------------- read

    func load(conceptID: String?) async {
        busy = true; error = nil
        defer { busy = false }
        do {
            var query = conceptQuery(conceptID)
            query.append(URLQueryItem(name: "limit", value: "40"))
            let value = try await api.json("/flashcards/session", query: query)
            session = value["cards"].array.compactMap(Flashcard.parse)
            dueTotal = value["due_total"].int
            cursor = 0
            revealed = false
            await loadStats(conceptID: conceptID)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func loadStats(conceptID: String?) async {
        do {
            stats = try await api.json("/flashcards/stats", query: conceptQuery(conceptID))
        } catch {
            // Stats are a summary, not a precondition: a failure here must not blank the
            // study surface, so it is reported and the deck still loads.
            self.error = error.localizedDescription
        }
    }

    func loadDeck(conceptID: String?) async {
        var query = conceptQuery(conceptID)
        query.append(URLQueryItem(name: "limit", value: "200"))
        do {
            deck = try await api.json("/flashcards", query: query)["cards"].array.compactMap(Flashcard.parse)
        } catch {
            self.error = error.localizedDescription
        }
    }

    // ---------------------------------------------------------------- study

    func reveal() { if current != nil { revealed = true } }

    func grade(_ value: Int) async {
        guard let card = current else { return }
        busy = true; error = nil
        defer { busy = false }
        do {
            _ = try await api.json("/flashcards/\(card.id)/review", method: "POST",
                                   body: ["grade": value])
            cursor += 1
            revealed = false
            await loadStats(conceptID: nil)
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// Pull another page of due cards (the queue is capped per request).
    func extendSession(conceptID: String?) async {
        await load(conceptID: conceptID)
    }

    // ---------------------------------------------------------------- generate

    func previewGeneration(conceptID: String, count: Int) async {
        guard !conceptID.isEmpty else { error = "Choose a concept first."; return }
        busy = true; error = nil
        defer { busy = false }
        do {
            let value = try await api.json("/flashcards/generate", method: "POST",
                                           body: ["concept_id": conceptID, "count": count,
                                                  "dry_run": true])
            preview = value["cards"].array.compactMap(Flashcard.parse)
            if preview.isEmpty {
                notice = "Nothing new to generate here — every card already exists."
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func commitGeneration(conceptID: String, count: Int) async {
        busy = true; error = nil
        defer { busy = false }
        do {
            let value = try await api.json("/flashcards/generate", method: "POST",
                                           body: ["concept_id": conceptID, "count": count])
            notice = "Added \(value["created"].int) card\(value["created"].int == 1 ? "" : "s")."
            preview = []
            await load(conceptID: nil)
            await loadDeck(conceptID: nil)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func clearPreview() { preview = [] }

    // ---------------------------------------------------------------- manage

    func update(_ card: Flashcard, front: String, back: String, hint: String, tags: [String]) async {
        busy = true; error = nil
        defer { busy = false }
        do {
            _ = try await api.json("/flashcards/\(card.id)", method: "PATCH",
                                   body: ["front": front, "back": back, "hint": hint, "tags": tags])
            await loadDeck(conceptID: nil)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func delete(_ card: Flashcard) async {
        busy = true; error = nil
        defer { busy = false }
        do {
            _ = try await api.json("/flashcards/\(card.id)", method: "DELETE")
            session.removeAll { $0.id == card.id }
            await loadDeck(conceptID: nil)
            await loadStats(conceptID: nil)
        } catch {
            self.error = error.localizedDescription
        }
    }
}

// MARK: - View

struct FlashcardsView: View {
    @ObservedObject var store: AppStore
    @StateObject private var flash: FlashcardStore
    @State private var tab: FlashTab = .study
    @State private var editing: Flashcard?
    @State private var showGenerate = false
    @State private var generateCount = 12
    @FocusState private var studyFocused: Bool

    init(store: AppStore) {
        self.store = store
        _flash = StateObject(wrappedValue: FlashcardStore(api: store.api))
    }

    private var conceptID: String { store.selectedConcept }
    private var conceptTitle: String {
        let title = store.currentConcept.text("title", fallback: "")
        return title.isEmpty ? (conceptID.isEmpty ? "Your whole deck" : conceptID) : title
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            header
            statsStrip
            Picker("", selection: $tab) {
                ForEach(FlashTab.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .frame(maxWidth: 260)
            if tab == .study { studyPane } else { browsePane }
            if let error = flash.error { banner(error, tone: Palette.peachDeep) }
            if let notice = flash.notice { banner(notice, tone: Palette.forest) }
            Spacer(minLength: 0)
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Palette.background)
        .task(id: conceptID) { await reload() }
        .sheet(item: $editing) { card in FlashcardEditor(flash: flash, card: card) }
        .sheet(isPresented: $showGenerate) {
            GenerateSheet(flash: flash, conceptID: conceptID, title: conceptTitle,
                          count: $generateCount)
        }
    }

    // ---------------------------------------------------------------- chrome

    private var header: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Eyebrow(text: "RETRIEVAL PRACTICE")
                SectionHeading(title: "Flashcards",
                               detail: "\(flash.dueTotal) due now · \(conceptTitle)")
            }
            Spacer()
            Button {
                flash.notice = nil
                showGenerate = true
            } label: {
                Label("Auto-generate", systemImage: "wand.and.stars")
            }
            .buttonStyle(LuminfestButtonStyle(primary: true, compact: true))
            .disabled(conceptID.isEmpty)
            .accessibilityIdentifier("flashcards.generate")
        }
    }

    private var statsStrip: some View {
        HStack(spacing: 12) {
            statTile("Due today", "\(flash.stats["due_today"].int)", "calendar")
            statTile("Retention", retentionText, "target")
            statTile("Next due", nextDueText, "clock")
        }
    }

    private func statTile(_ label: String, _ value: String, _ icon: String) -> some View {
        Card(color: Palette.surface, padding: 14, interactive: false) {
            HStack(spacing: 10) {
                Image(systemName: icon)
                    .font(.system(size: 15, weight: .light))
                    .foregroundStyle(Palette.forest)
                    .frame(width: 34, height: 34)
                    .background(Palette.sage.opacity(0.4), in: RoundedRectangle(cornerRadius: 11, style: .continuous))
                VStack(alignment: .leading, spacing: 1) {
                    Text(label).font(.system(size: 10, weight: .semibold)).tracking(0.6)
                        .foregroundStyle(Palette.secondary)
                    Text(value).font(.system(size: 17, weight: .semibold, design: .rounded))
                        .foregroundStyle(Palette.ink)
                }
                Spacer(minLength: 0)
            }
        }
    }

    private var retentionText: String {
        let rate = flash.stats["retention_rate"]
        if rate.isNull || flash.stats["reviews"].int == 0 { return "—" }
        return "\(Int((rate.double * 100).rounded()))%"
    }

    private var nextDueText: String {
        let label = flash.stats["next_due_label"].string
        return label.isEmpty ? "—" : label
    }

    private func banner(_ text: String, tone: Color) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "info.circle").foregroundStyle(tone)
            Text(text).font(.system(size: 12)).foregroundStyle(Palette.secondary)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 14).padding(.vertical, 9)
        .background(Palette.surfaceSubtle, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    // ---------------------------------------------------------------- study

    @ViewBuilder
    private var studyPane: some View {
        if flash.busy && flash.session.isEmpty {
            HStack(spacing: 10) { ProgressView().controlSize(.small)
                Text("Building your session…").font(.system(size: 12)).foregroundStyle(Palette.secondary) }
                .frame(maxWidth: .infinity, alignment: .leading)
        } else if flash.session.isEmpty {
            EmptyState(icon: "rectangle.stack",
                       title: "Nothing due right now",
                       message: "Your cards come back when the memory curve says they should. "
                              + "Auto-generate a deck for this concept to start, or come back later.")
        } else if flash.finished {
            sessionComplete
        } else if let card = flash.current {
            studyCard(card)
        }
    }

    private var sessionComplete: some View {
        Card(color: Palette.surface, padding: 22, interactive: false) {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 10) {
                    Image(systemName: "checkmark.seal.fill").foregroundStyle(Palette.forest)
                    Text("Session complete").font(.system(size: 16, weight: .semibold, design: .rounded))
                }
                Text("You reviewed \(flash.session.count) card\(flash.session.count == 1 ? "" : "s"). "
                     + "Each one is scheduled for the moment recall is predicted to start fading.")
                    .font(.system(size: 12)).foregroundStyle(Palette.secondary).lineSpacing(3)
                Button("Load more due cards") {
                    Task { await flash.extendSession(conceptID: conceptID) }
                }
                .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
            }
        }
    }

    private func studyCard(_ card: Flashcard) -> some View {
        Card(color: Palette.surface, padding: 26, interactive: false) {
            VStack(alignment: .leading, spacing: 16) {
                HStack(spacing: 8) {
                    Tag(text: card.kindLabel, color: Palette.accent(for: card.kind).soft)
                    Tag(text: conceptTitle, color: Palette.sage)
                    if card.reps > 0 {
                        Tag(text: card.state.capitalized, color: Palette.eucalyptus)
                    }
                    Spacer()
                    Text(flash.progressText).font(.system(size: 11, weight: .medium))
                        .foregroundStyle(Palette.secondary)
                }
                Text(card.front)
                    .font(.system(size: 21, weight: .semibold, design: .rounded))
                    .foregroundStyle(Palette.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)

                if flash.revealed {
                    Divider().overlay(Palette.line)
                    Text(card.back)
                        .font(.system(size: 15)).foregroundStyle(Palette.ink.opacity(0.92))
                        .lineSpacing(4)
                        .fixedSize(horizontal: false, vertical: true)
                        .textSelection(.enabled)
                    if !card.hint.isEmpty {
                        Text("Hint: \(card.hint)").font(.system(size: 11))
                            .foregroundStyle(Palette.tertiary)
                    }
                    gradeButtons(card)
                } else {
                    Button("Show answer  (space)") { flash.reveal() }
                        .buttonStyle(LuminfestButtonStyle(primary: true))
                        .accessibilityIdentifier("flashcards.reveal")
                }
            }
        }
        .focusable()
        .focused($studyFocused)
        .onAppear { studyFocused = true }
        .onKeyPress(.space) {
            if !flash.revealed { flash.reveal(); return .handled }
            return .ignored
        }
        .onKeyPress(characters: CharacterSet(charactersIn: "1234")) { press in
            guard flash.revealed,
                  let character = press.characters.first,
                  let grade = character.wholeNumberValue else { return .ignored }
            Task { await flash.grade(grade) }
            return .handled
        }
    }

    private func gradeButtons(_ card: Flashcard) -> some View {
        HStack(spacing: 10) {
            gradeButton(1, "again", "Again", Palette.roseDeep, card)
            gradeButton(2, "hard", "Hard", Palette.ochreDeep, card)
            gradeButton(3, "good", "Good", Palette.forest, card)
            gradeButton(4, "easy", "Easy", Palette.tealDeep, card)
        }
    }

    private func gradeButton(_ grade: Int, _ name: String, _ title: String,
                             _ tone: Color, _ card: Flashcard) -> some View {
        Button {
            Task { await flash.grade(grade) }
        } label: {
            VStack(spacing: 1) {
                Text("\(grade) · \(title)").font(.system(size: 12, weight: .semibold))
                Text(card.intervalLabel(name)).font(.system(size: 10)).opacity(0.85)
            }
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(tone.opacity(0.35), lineWidth: 1)
        )
        .accessibilityIdentifier("flashcards.grade.\(name)")
    }

    // ---------------------------------------------------------------- browse

    @ViewBuilder
    private var browsePane: some View {
        if flash.deck.isEmpty {
            EmptyState(icon: "rectangle.on.rectangle",
                       title: "No cards yet",
                       message: "Use Auto-generate to build a deck from this concept's lesson "
                              + "blocks and questions. Every card names the block it came from.")
        } else {
            ScrollView {
                LazyVStack(spacing: 10) {
                    ForEach(flash.deck) { card in
                        browseRow(card)
                    }
                }
                .padding(.vertical, 2)
            }
            .frame(maxHeight: .infinity)
        }
    }

    private func browseRow(_ card: Flashcard) -> some View {
        Card(color: Palette.surface, padding: 14, interactive: false) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 5) {
                    HStack(spacing: 7) {
                        Tag(text: card.kindLabel, color: Palette.accent(for: card.kind).soft)
                        if card.reps > 0 {
                            Text("\(card.reps) review\(card.reps == 1 ? "" : "s") · "
                                 + "\(card.lapses) lapse\(card.lapses == 1 ? "" : "s")")
                                .font(.system(size: 10)).foregroundStyle(Palette.tertiary)
                        } else {
                            Text("new").font(.system(size: 10)).foregroundStyle(Palette.tertiary)
                        }
                    }
                    Text(card.front).font(.system(size: 13, weight: .medium))
                        .foregroundStyle(Palette.ink).lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(card.back).font(.system(size: 11)).foregroundStyle(Palette.secondary)
                        .lineLimit(2).fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
                VStack(spacing: 6) {
                    Button { editing = card } label: { Image(systemName: "pencil") }
                        .buttonStyle(.borderless).help("Edit this card")
                    Button { Task { await flash.delete(card) } } label: {
                        Image(systemName: "trash")
                    }
                    .buttonStyle(.borderless).foregroundStyle(Palette.roseDeep)
                    .help("Delete this card")
                }
            }
        }
    }

    // ---------------------------------------------------------------- lifecycle

    private func reload() async {
        await flash.load(conceptID: conceptID)
        await flash.loadDeck(conceptID: conceptID)
    }
}

// MARK: - Editor

/// Edit a card's text in place. Provenance and schedule are not editable here: the source
/// is what makes the card checkable, and the schedule belongs to the memory model.
private struct FlashcardEditor: View {
    @ObservedObject var flash: FlashcardStore
    let card: Flashcard
    @Environment(\.dismiss) private var dismiss
    @State private var front: String
    @State private var back: String
    @State private var hint: String
    @State private var tags: String

    init(flash: FlashcardStore, card: Flashcard) {
        self.flash = flash
        self.card = card
        _front = State(initialValue: card.front)
        _back = State(initialValue: card.back)
        _hint = State(initialValue: card.hint)
        _tags = State(initialValue: card.tags.joined(separator: ", "))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Eyebrow(text: "EDIT CARD")
            SectionHeading(title: "\(card.kindLabel) card", detail: card.conceptID)
            labelled("Front", $front, height: 70)
            labelled("Back", $back, height: 110)
            labelled("Hint", $hint, height: 44)
            labelled("Tags (comma separated)", $tags, height: 44)
            HStack {
                Spacer()
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Button("Save") {
                    let parsed = tags.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }
                        .filter { !$0.isEmpty }
                    Task {
                        await flash.update(card, front: front, back: back, hint: hint, tags: parsed)
                        dismiss()
                    }
                }
                .buttonStyle(LuminfestButtonStyle(primary: true, compact: true))
                .keyboardShortcut(.defaultAction)
                .disabled(front.trimmingCharacters(in: .whitespaces).isEmpty
                          || back.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        .padding(22)
        .frame(width: 520)
        .background(Palette.background)
    }

    private func labelled(_ title: String, _ binding: Binding<String>, height: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.system(size: 11, weight: .semibold)).foregroundStyle(Palette.secondary)
            TextEditor(text: binding)
                .font(.system(size: 13))
                .frame(height: height)
                .padding(6)
                .background(Palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .strokeBorder(Palette.line, lineWidth: 1))
        }
    }
}

// MARK: - Generate

/// The auto-generate flow: preview first, commit second.
///
/// The preview comes from the server's dry-run, so what the learner sees is exactly the set
/// that would be inserted -- grounded in this concept's lesson blocks and questions, minus
/// the fronts already in the deck.
private struct GenerateSheet: View {
    @ObservedObject var flash: FlashcardStore
    let conceptID: String
    let title: String
    @Binding var count: Int
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Eyebrow(text: "AUTO-GENERATE")
            SectionHeading(title: "New cards for \(title)",
                           detail: "\(flash.previewCreated) to add")
            HStack(spacing: 12) {
                Stepper("Count: \(count)", value: $count, in: 1...40)
                    .frame(maxWidth: 200)
                Spacer()
                Button("Preview") { Task { await flash.previewGeneration(conceptID: conceptID, count: count) } }
                    .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
            }
            Text("Cards are built from this concept's lesson blocks and its questions' "
                 + "diagnosed distractors. Nothing is invented, and every card names the block "
                 + "or question it came from.")
                .font(.system(size: 11)).foregroundStyle(Palette.secondary).lineSpacing(3)

            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(flash.preview) { card in
                        Card(color: Palette.surfaceSubtle, padding: 12, interactive: false) {
                            VStack(alignment: .leading, spacing: 4) {
                                Tag(text: card.kindLabel, color: Palette.accent(for: card.kind).soft)
                                Text(card.front).font(.system(size: 12, weight: .medium))
                                    .foregroundStyle(Palette.ink).fixedSize(horizontal: false, vertical: true)
                                Text(card.back).font(.system(size: 11)).foregroundStyle(Palette.secondary)
                                    .lineLimit(3).fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                }
            }
            .frame(minHeight: 220, maxHeight: 360)

            HStack {
                Spacer()
                Button("Cancel") { flash.clearPreview(); dismiss() }.keyboardShortcut(.cancelAction)
                Button("Add \(flash.previewCreated) card\(flash.previewCreated == 1 ? "" : "s")") {
                    Task {
                        await flash.commitGeneration(conceptID: conceptID, count: count)
                        dismiss()
                    }
                }
                .buttonStyle(LuminfestButtonStyle(primary: true, compact: true))
                .keyboardShortcut(.defaultAction)
                .disabled(flash.previewCreated == 0)
            }
        }
        .padding(22)
        .frame(width: 560)
        .background(Palette.background)
        .task { await flash.previewGeneration(conceptID: conceptID, count: count) }
    }
}
