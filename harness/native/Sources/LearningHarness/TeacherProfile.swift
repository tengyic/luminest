import SwiftUI

/// Transcript-based teacher style analysis. The transcript stays in this view's local
/// state; only the user-reviewed style preference is sent with tutoring turns.
struct TeacherProfileSheet: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.dismiss) private var dismiss

    @State private var transcript = ""
    @State private var authorizationBasis = "self"
    @State private var studentIdentifiersRemoved = false
    @State private var aiProcessingConfirmed = false
    @State private var analyzing = false
    @State private var error: String?
    @State private var analysisMode = ""
    @State private var evidence: JSON = .null
    @State private var editable: [String: String] = [:]

    private let dimensions: [(String, String)] = [
        ("methodology", "Teaching methodology"),
        ("teaching_style", "Teaching style"),
        ("content_procedure", "Content procedure"),
        ("interaction_prompts", "Interaction prompts"),
        ("tone", "Written tone"),
    ]

    private var hasAnalysis: Bool { !editable.isEmpty }
    private var canAnalyze: Bool {
        transcript.trimmingCharacters(in: .whitespacesAndNewlines).count >= 100
            && studentIdentifiersRemoved && aiProcessingConfirmed && !analyzing
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Personalize your tutor").font(.system(size: 20, weight: .semibold))
                    Text("Extract observable teaching habits, not a real person's identity or voice.")
                        .font(.system(size: 11)).foregroundStyle(Palette.secondary)
                }
                Spacer()
                Button("Close") { dismiss() }.buttonStyle(LuminfestButtonStyle(primary: false))
            }

            if hasAnalysis {
                reviewedProfile
            } else {
                transcriptForm
            }
        }
        .padding(22)
        .frame(minWidth: 620, minHeight: 620)
        .background(Palette.background)
    }

    private var transcriptForm: some View {
        VStack(alignment: .leading, spacing: 13) {
            Text("Paste a transcript you own or are authorized to use. Remove student names and identifying details first.")
                .font(.system(size: 12)).foregroundStyle(Palette.secondary).lineSpacing(3)
            TextEditor(text: $transcript)
                .font(.system(size: 12)).scrollContentBackground(.hidden).padding(9)
                .frame(minHeight: 190).background(Palette.surfaceSubtle, in: RoundedRectangle(cornerRadius: 12))
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(Palette.line))
                .accessibilityIdentifier("teacher-profile.transcript")
            HStack {
                Text("\(transcript.count) / 40,000 characters")
                Spacer()
                Text("Minimum 100 characters")
            }.font(.system(size: 10)).foregroundStyle(Palette.tertiary)

            Picker("Authorization", selection: $authorizationBasis) {
                Text("I am the teacher in this transcript").tag("self")
                Text("I have the teacher's explicit permission").tag("explicit_permission")
            }.pickerStyle(.menu)

            Toggle("I removed student names and identifying details", isOn: $studentIdentifiersRemoved)
                .toggleStyle(.checkbox).font(.system(size: 11))
            Toggle("I authorize the configured tutor provider to process this transcript", isOn: $aiProcessingConfirmed)
                .toggleStyle(.checkbox).font(.system(size: 11))

            Text("The raw transcript is sent to the configured provider only for analysis and is not saved by Luminfest. With the offline tutor, analysis uses local heuristics. Student accounts, recordings, or third-party transcripts require appropriate permission. The output cannot reproduce acoustic voice, accent, prosody, or identity.")
                .font(.system(size: 10)).foregroundStyle(Palette.secondary).lineSpacing(3)

            if let error { Text(error).font(.system(size: 11)).foregroundStyle(Palette.peachDeep) }
            HStack {
                Spacer()
                Button {
                    Task { await analyze() }
                } label: {
                    HStack(spacing: 7) {
                        if analyzing { ProgressView().controlSize(.small) }
                        Text(analyzing ? "Analyzing transcript…" : "Analyze teaching style")
                    }
                }
                .buttonStyle(LuminfestButtonStyle())
                .disabled(!canAnalyze)
                .accessibilityIdentifier("teacher-profile.analyze")
            }
        }
    }

    private var reviewedProfile: some View {
        VStack(alignment: .leading, spacing: 13) {
            HStack {
                Tag(text: analysisMode == "offline_heuristic_review_required" ? "LOCAL HEURISTIC DRAFT" : "AI DRAFT · REVIEW REQUIRED", color: Palette.lavender)
                Spacer()
                Button("Analyze another transcript") { editable = [:]; evidence = .null; error = nil }
                    .buttonStyle(LuminfestButtonStyle(primary: false))
            }
            Text("Review the evidence and edit each field. Only the edited style notes below—not the transcript or evidence quotes—will be used in this session's tutor calls.")
                .font(.system(size: 11)).foregroundStyle(Palette.secondary).lineSpacing(3)

            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    ForEach(dimensions, id: \.0) { key, title in
                        VStack(alignment: .leading, spacing: 7) {
                            Text(title.uppercased()).font(.system(size: 9, weight: .semibold)).tracking(1)
                                .foregroundStyle(Palette.secondary)
                            TextEditor(text: field(key)).font(.system(size: 11))
                                .scrollContentBackground(.hidden).padding(6).frame(height: 58)
                                .background(Palette.surfaceSubtle, in: RoundedRectangle(cornerRadius: 9))
                                .overlay(RoundedRectangle(cornerRadius: 9).stroke(Palette.line))
                            let examples = evidence[key].array
                            if !examples.isEmpty {
                                ForEach(Array(examples.enumerated()), id: \.offset) { _, item in
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(item["claim"].string).font(.system(size: 10, weight: .medium))
                                        Text("Evidence: “\(item["evidence_quote"].string)”")
                                            .font(.system(size: 9)).foregroundStyle(Palette.secondary).lineSpacing(2)
                                    }
                                    .padding(8).frame(maxWidth: .infinity, alignment: .leading)
                                    .background(Palette.background, in: RoundedRectangle(cornerRadius: 8))
                                }
                            }
                        }
                    }
                }
            }
            .frame(maxHeight: 390)

            HStack {
                Button("Clear profile") { store.teacherStyleProfile = [:]; dismiss() }
                    .buttonStyle(LuminfestButtonStyle(primary: false))
                Spacer()
                Button("Use reviewed profile") {
                    store.teacherStyleProfile = Dictionary(uniqueKeysWithValues: dimensions.compactMap { key, _ in
                        let lines = (editable[key] ?? "").components(separatedBy: .newlines)
                            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                            .filter { !$0.isEmpty }.prefix(4)
                        return lines.isEmpty ? nil : (key, Array(lines))
                    })
                    dismiss()
                }
                .buttonStyle(LuminfestButtonStyle())
                .accessibilityIdentifier("teacher-profile.apply")
            }
        }
    }

    private func field(_ key: String) -> Binding<String> {
        Binding(get: { editable[key] ?? "" }, set: { editable[key] = String($0.prefix(1000)) })
    }

    @MainActor
    private func analyze() async {
        guard canAnalyze else { return }
        analyzing = true
        error = nil
        defer { analyzing = false }
        do {
            let result = try await store.api.json("/teacher-profiles/analyze", method: "POST", body: [
                "transcript": transcript,
                "authorization": authorizationBasis,
                "student_identifiers_removed": studentIdentifiersRemoved,
                "ai_processing_confirmed": aiProcessingConfirmed,
            ])
            evidence = result["profile"]
            analysisMode = result["analysis_mode"].string
            transcript = ""
            editable = Dictionary(uniqueKeysWithValues: dimensions.map { key, _ in
                (key, result["tutor_profile"][key].array.map(\.string).joined(separator: "\n"))
            })
            if editable.values.allSatisfy({ $0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) {
                error = "The transcript did not contain enough observable teaching evidence. Add a longer sample or use a different transcript."
                editable = [:]
            }
        } catch {
            self.error = error.localizedDescription
        }
    }
}
