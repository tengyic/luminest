import Combine
import Foundation

/// One reward event, exactly as the backend sent it.
///
/// Nothing here is computed. The tier, the mascot sprite and the sound name all arrive from
/// the server (`app/harness/rewards.py`), because the thresholds that decide *what* is worth
/// celebrating live in `motivation.py` and a client that re-scored them would be the second
/// place they are written down. The client's only opinions are *when* to show one and *how
/// long* it stays.
struct RewardEvent: Identifiable, Equatable {
    let id: String
    let kind: String
    let value: Double
    let tier: String
    let mascot: String
    let sound: String
    let title: String
    let announce: String

    init?(_ json: JSON) {
        let id = json.text("id")
        guard !id.isEmpty else { return nil }
        self.id = id
        kind = json.text("kind")
        value = json["value"].double
        tier = json.text("tier", fallback: "toast")
        mascot = json.text("mascot", fallback: "greeting")
        sound = json.text("sound")
        title = json.text("title", fallback: "Milestone")
        announce = json.text("announce", fallback: json.text("title", fallback: "Milestone"))
    }
}

/// Fetches reward events, remembers which ones have been shown, and presents one at a time.
///
/// Three decisions worth stating:
///
/// * **The seen-set is the client's.** The route is read-only and never marks an event as
///   delivered, so idempotency has to live somewhere; it lives here, keyed by the event's
///   own id. A second window, a retry or a reconnect therefore cannot double-celebrate, and
///   the server needs no state to prevent it.
/// * **One at a time, heaviest first.** Four events can land on the same poll (a streak, a
///   practice run and two badges). Showing them together would be a wall; showing them in
///   the order the backend sorted them means the 5-day run is not buried under a badge.
/// * **A failure is silent.** If the poll fails - offline, 401 before sign-in - there is
///   simply nothing to celebrate. A reward system that reports its own errors has stopped
///   being a reward.
@MainActor
final class RewardCenter: ObservableObject {
    /// The event on screen, if any.
    @Published private(set) var current: RewardEvent?

    private var queue: [RewardEvent] = []
    private var seen: Set<String>
    private let seenKey = "rewards.seen.ids"
    /// Bounded so the defaults file cannot grow without limit over a year of use. Ids are
    /// stable and old ones stop recurring, so dropping the tail is safe.
    private let seenLimit = 240

    init(defaults: UserDefaults = .standard) {
        seen = Set(defaults.stringArray(forKey: seenKey) ?? [])
        self.defaults = defaults
    }

    private let defaults: UserDefaults

    var isPresenting: Bool { current != nil }

    /// Ask the backend what this learner has earned. Safe to call on any interval.
    func refresh(_ api: APIClient?) async {
        guard let api else { return }
        guard let payload = try? await api.json("/rewards/events") else { return }
        enqueue(payload["events"].array.compactMap { RewardEvent($0) })
    }

    /// Add events that have not been shown before, heaviest first, and present the first.
    func enqueue(_ events: [RewardEvent]) {
        let fresh = events.filter { !seen.contains($0.id) }
        guard !fresh.isEmpty else { return }
        seen.formUnion(fresh.map(\.id))
        persist()
        queue.append(contentsOf: fresh.sorted { weight($0.tier) < weight($1.tier) })
        if current == nil { presentNext() }
    }

    /// Dismiss what is on screen and move to the next queued event.
    func dismiss() {
        current = nil
        presentNext()
    }

    /// Forget the seen-set. Used by the capture harness so a screenshot can show a moment
    /// that this machine has already seen.
    func reset() {
        seen.removeAll()
        persist()
        queue.removeAll()
        current = nil
    }

    private func presentNext() {
        guard current == nil, !queue.isEmpty else { return }
        current = queue.removeFirst()
    }

    private func weight(_ tier: String) -> Int {
        switch tier {
        case "celebrate": return 0
        case "banner": return 1
        default: return 2
        }
    }

    private func persist() {
        defaults.set(Array(seen).suffix(seenLimit).map { $0 }, forKey: seenKey)
    }
}
