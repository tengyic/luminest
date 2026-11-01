import AppKit
import Foundation

/// App-wide interaction telemetry: what was touched, in batches, with no content.
///
/// Two sources feed one buffer.
///
/// 1. A local ``NSEvent`` monitor records that a click or a key press happened anywhere in
///    this app, plus window focus and blur. It cannot say *what* was touched, only which
///    page was on screen, so its target is coarse (``page:studio``).
/// 2. Call sites that know better call ``record(kind:target:)`` with a control identifier
///    (``stage.tab.deck``, ``board.node.cell-theory``). That is the useful half: a page-level
///    click count cannot answer "did the learner open the hint before or after trying".
///
/// Deliberate limits, each of which the backend enforces again:
///
/// * **No content.** The key monitor records *that* a key was pressed, never which one. There
///   is no field for text, and ``isValidTarget`` refuses anything that is not a short
///   identifier, so a call site cannot smuggle a sentence into a target.
/// * **No window titles.** An earlier version sent ``"window": "Luminfest"``. A window title
///   is a document name, a URL or a message subject; the backend now refuses the field, and
///   so does this file.
/// * **Local monitor only.** ``addLocalMonitorForEvents`` sees this app's events without
///   Accessibility permission and never watches another app's input. A global monitor would
///   be a keylogger with extra steps.
/// * **Bounded memory.** A failed upload re-queues, but the buffer is capped: telemetry that
///   cannot be delivered must not grow until the app is killed.
@MainActor final class ClickTelemetry {
    private struct Interaction {
        let kind: String      // click | tap | key | focus | blur
        let target: String    // an identifier, never prose
        let at: Date
    }

    /// Matches ``schemas.Events`` (max 100 per request) so one flush cannot be rejected for
    /// being too large after it has already been removed from the buffer.
    static let maxBatch = 100
    /// Oldest events are dropped beyond this. 400 is a few minutes of ordinary use.
    static let maxBuffer = 400

    weak var store: AppStore?
    private var localMonitor: Any?
    private var focusObserver: NSObjectProtocol?
    private var blurObserver: NSObjectProtocol?
    private var flushTask: Task<Void, Never>?
    private var buffer: [Interaction] = []

    // MARK: - Lifecycle

    /// Install the monitors. Idempotent: a second call while running does nothing.
    func start(store: AppStore) {
        self.store = store
        guard localMonitor == nil else { return }

        let mask: NSEvent.EventTypeMask = [.leftMouseDown, .rightMouseDown, .keyDown]
        localMonitor = NSEvent.addLocalMonitorForEvents(matching: mask) { [weak self] event in
            self?.record(event)
            return event
        }
        focusObserver = NotificationCenter.default.addObserver(
            forName: NSApplication.didBecomeActiveNotification, object: nil, queue: .main) { [weak self] _ in
            // The observer block is nonisolated even though it is delivered on the main
            // queue, so the hop is explicit rather than an implicitly-asynchronous call.
            Task { @MainActor in self?.recordFocus(focused: true) }
        }
        blurObserver = NotificationCenter.default.addObserver(
            forName: NSApplication.didResignActiveNotification, object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor in self?.recordFocus(focused: false) }
        }
        flushTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 5_000_000_000)
                await self?.flush()
            }
        }
    }

    /// Remove all monitors and cancel the flush timer. The buffer is dropped, not uploaded:
    /// the learner revoked consent, and their remaining taps are not ours to keep.
    func stop() {
        if let localMonitor { NSEvent.removeMonitor(localMonitor) }
        if let focusObserver { NotificationCenter.default.removeObserver(focusObserver) }
        if let blurObserver { NotificationCenter.default.removeObserver(blurObserver) }
        localMonitor = nil
        focusObserver = nil
        blurObserver = nil
        flushTask?.cancel()
        flushTask = nil
        buffer.removeAll()
    }

    // MARK: - Recording

    /// Record a control-level interaction. The useful entry point: a caller that knows the
    /// learner opened the deck says so, and the summary can then count it.
    func record(kind: String = "click", target: String) {
        guard permitted, Self.isValidTarget(target) else { return }
        append(Interaction(kind: kind, target: target, at: Date()))
    }

    private var permitted: Bool {
        guard let store else { return false }
        return store.authenticated && store.user["telemetry_consent"].bool
    }

    private func record(_ event: NSEvent) {
        guard permitted, let store else { return }
        let kind = (event.type == .keyDown) ? "key" : "click"
        // Page-level on purpose: the monitor cannot see which control was hit, and guessing
        // from coordinates would produce a target that looks precise and is not.
        let target = Self.sanitise("page:" + store.page.rawValue)
        append(Interaction(kind: kind, target: target, at: Date()))
    }

    private func recordFocus(focused: Bool) {
        guard permitted else { return }
        append(Interaction(kind: focused ? "focus" : "blur", target: "window", at: Date()))
    }

    private func append(_ item: Interaction) {
        buffer.append(item)
        if buffer.count > Self.maxBuffer {
            buffer.removeFirst(buffer.count - Self.maxBuffer)
        }
        if buffer.count >= 40 { Task { await flush() } }
    }

    // MARK: - Vocabulary

    /// The same grammar the backend enforces, checked here first so a bad call site fails at
    /// the call rather than in a 422 nobody reads.
    ///
    /// ASCII only, and deliberately so: the server's pattern is ``[A-Za-z0-9._:-]``, and a
    /// client that accepts a wider alphabet records taps that can never be delivered - the
    /// flush then retries a batch that is rejected every time.
    nonisolated static func isValidTarget(_ target: String) -> Bool {
        guard let first = target.first, let scalar = first.unicodeScalars.first,
              Self.asciiAlphanumerics.contains(scalar) else { return false }
        guard !target.isEmpty, target.count <= 64 else { return false }
        return target.unicodeScalars.allSatisfy { Self.asciiTargetCharacters.contains($0) }
    }

    /// Lower-case, and map anything outside the grammar to a dash. Used only for the
    /// page-derived target, where the input is ours but its formatting is not.
    ///
    /// `nonisolated`: a pure string function over its argument touches no UI state, so
    /// forcing callers onto the main actor (the test suite calls it synchronously) would
    /// be isolation theatre, not safety.
    nonisolated static func sanitise(_ raw: String) -> String {
        var out = ""
        for scalar in raw.lowercased().unicodeScalars {
            out.unicodeScalars.append(Self.asciiTargetCharacters.contains(scalar) ? scalar : "-")
        }
        let trimmed = String(out.prefix(64))
        return isValidTarget(trimmed) ? trimmed : "page:unknown"
    }

    private nonisolated static let asciiAlphanumerics = CharacterSet(
        charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
    private nonisolated static let asciiTargetCharacters = CharacterSet(
        charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-")

    // MARK: - Upload

    /// Upload the buffered interactions in batches the schema accepts.
    ///
    /// Best-effort by design: telemetry must never block, alarm or slow the learner. A failed
    /// batch goes back to the front of the buffer once and the loop stops, so a server that
    /// is refusing this channel costs one retry rather than an unbounded queue.
    func flush() async {
        guard let store, store.authenticated, !buffer.isEmpty else { return }
        var stalled = false
        while !buffer.isEmpty && !stalled {
            let batch = Array(buffer.prefix(Self.maxBatch))
            buffer.removeFirst(batch.count)
            let events: [[String: Any]] = batch.map { item in
                ["id": UUID().uuidString,
                 "type": "interaction",
                 "occurred_at": ISO8601DateFormatter().string(from: item.at),
                 "payload": ["kind": item.kind, "target": item.target]]
            }
            do {
                _ = try await store.api.json("/events", method: "POST", body: ["events": events])
            } catch {
                buffer.insert(contentsOf: batch, at: 0)
                stalled = true
            }
        }
        if buffer.count > Self.maxBuffer {
            buffer.removeFirst(buffer.count - Self.maxBuffer)
        }
    }
}
