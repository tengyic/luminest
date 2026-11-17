import Foundation

/// The four disclosure levels the backend accepts. The raw values are the API contract;
/// the labels are what a learner can actually distinguish without reading policy text.
enum AssistanceLevel: String, CaseIterable, Identifiable {
    case none
    case researchOnly = "research_only"
    case hintsOnly = "hints_only"
    case feedbackOnly = "feedback_only"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .none: return "No AI assistance"
        case .researchOnly: return "Research only"
        case .hintsOnly: return "Hints only"
        case .feedbackOnly: return "Feedback only"
        }
    }

    var detail: String {
        switch self {
        case .none: return "I wrote the work without AI help."
        case .researchOnly: return "AI helped me find or explain background material."
        case .hintsOnly: return "AI gave me hints, but not the answer or the wording."
        case .feedbackOnly: return "AI commented on my own draft after I wrote it."
        }
    }

    var disclosureSentence: String {
        switch self {
        case .none: return "No AI assistance was used in this project."
        case .researchOnly: return "AI was used for background research; the submitted explanation is mine."
        case .hintsOnly: return "AI was used for hints only; the submitted explanation is mine."
        case .feedbackOnly: return "AI reviewed my own draft; the submitted explanation is mine."
        }
    }
}

/// Unsubmitted project writing, kept on this Mac between visits.
///
/// `ProjectEditor` used to hold its text in a single `@State` and rebuild it from
/// `project["submission"]` on appear. That is the same thing as deleting the draft:
/// the editor is destroyed when the learner switches pages, so navigating away and
/// back silently discarded everything that had not been submitted. J5 measured it.
///
/// The store is deliberately local and deliberately scoped to the signed-in account.
/// Two learners sharing one Mac must not see each other's drafts, and a draft is not
/// learning evidence, so it does not belong in the backend's projects table. The key
/// uses a stable digest of (account id, project id) rather than the raw values: an
/// email address should not end up in a `UserDefaults` key. Writes are immediate, not
/// debounced — a learner can quit the app a fraction of a second after typing.
enum ProjectDrafts {
    struct Draft: Codable {
        var text: String
        var reflection: String
        var assistanceLevel: AssistanceLevel
        var confirmed: Bool
        var updatedAt: TimeInterval

        private enum CodingKeys: String, CodingKey {
            case text, reflection, assistanceLevel, usedAI, confirmed, updatedAt
        }

        init(text: String, reflection: String, assistanceLevel: AssistanceLevel,
             confirmed: Bool, updatedAt: TimeInterval) {
            self.text = text
            self.reflection = reflection
            self.assistanceLevel = assistanceLevel
            self.confirmed = confirmed
            self.updatedAt = updatedAt
        }

        /// A boolean-only draft predates the four disclosure levels. Its exact level is
        /// unknowable, so map "used AI" to the narrowest honest category rather than
        /// dropping the learner's writing or silently claiming no assistance.
        init(from decoder: Decoder) throws {
            let values = try decoder.container(keyedBy: CodingKeys.self)
            text = try values.decode(String.self, forKey: .text)
            reflection = try values.decode(String.self, forKey: .reflection)
            if let stored = try values.decodeIfPresent(String.self, forKey: .assistanceLevel),
               let level = AssistanceLevel(rawValue: stored) {
                assistanceLevel = level
            } else {
                let legacy = try values.decodeIfPresent(Bool.self, forKey: .usedAI) ?? false
                assistanceLevel = legacy ? .researchOnly : .none
            }
            confirmed = try values.decode(Bool.self, forKey: .confirmed)
            updatedAt = try values.decode(TimeInterval.self, forKey: .updatedAt)
        }

        func encode(to encoder: Encoder) throws {
            var values = encoder.container(keyedBy: CodingKeys.self)
            try values.encode(text, forKey: .text)
            try values.encode(reflection, forKey: .reflection)
            try values.encode(assistanceLevel.rawValue, forKey: .assistanceLevel)
            try values.encode(confirmed, forKey: .confirmed)
            try values.encode(updatedAt, forKey: .updatedAt)
        }
    }

    private static let prefix = "luminfest.project.draft."
    private static let defaults = UserDefaults.standard

    /// FNV-1a, 64-bit. Stable across launches, unlike Swift's seeded `hashValue`, and
    /// dependency-free so the packaged app does not need another framework to restore
    /// a paragraph the learner wrote.
    private static func digest(_ raw: String) -> String {
        var value: UInt64 = 14_695_981_039_346_656_037
        for byte in raw.utf8 {
            value ^= UInt64(byte)
            value &*= 1_099_511_628_211
        }
        return String(value, radix: 16)
    }

    private static func key(account: String, project: String) -> String {
        prefix + digest(account + "\u{1f}" + project)
    }

    private static func indexKey(account: String) -> String {
        prefix + "index." + digest(account)
    }

    static func load(account: String, project: String) -> Draft? {
        guard !project.isEmpty,
              let data = defaults.data(forKey: key(account: account, project: project)),
              let draft = try? JSONDecoder().decode(Draft.self, from: data) else { return nil }
        return draft
    }

    static func save(account: String, project: String, draft: Draft) {
        guard !account.isEmpty, !project.isEmpty,
              let data = try? JSONEncoder().encode(draft) else { return }
        defaults.set(data, forKey: key(account: account, project: project))
        let index = indexKey(account: account)
        var projects = Set(defaults.stringArray(forKey: index) ?? [])
        projects.insert(project)
        defaults.set(projects.sorted(), forKey: index)
    }

    static func clear(account: String, project: String) {
        defaults.removeObject(forKey: key(account: account, project: project))
        let index = indexKey(account: account)
        var projects = Set(defaults.stringArray(forKey: index) ?? [])
        projects.remove(project)
        defaults.set(projects.sorted(), forKey: index)
    }

    /// Called only after the server confirms account erasure, never on ordinary logout.
    /// The index covers all drafts saved by this build; known project ids also clear
    /// legacy drafts written before an index existed.
    static func clearAccount(_ account: String, knownProjects: [String] = []) {
        guard !account.isEmpty else { return }
        let index = indexKey(account: account)
        let projects = Set(defaults.stringArray(forKey: index) ?? []).union(knownProjects)
        for project in projects {
            defaults.removeObject(forKey: key(account: account, project: project))
        }
        defaults.removeObject(forKey: index)
    }
}
