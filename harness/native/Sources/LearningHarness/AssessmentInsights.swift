import SwiftUI

/// The two surfaces the November 8 audit said were missing: a unit-level grade book
/// and written multi-perspective observations.
///
/// Both render what the server computed. Nothing here turns a missing value into a
/// zero, and nothing turns foreground activity into a judgement about a learner.
/// "No grade yet" and "No observation yet" are real product states, so they have
/// text, not an empty progress bar.

struct GradebookCard: View {
    @EnvironmentObject var store: AppStore
    private var units: [JSON] { store.gradebook["units"].array }

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: 17) {
                SectionHeading(title: "Unit grade book", detail: "DECLARED STANDARDS")
                Text(store.gradebook.text("standards_note",
                                          fallback: "A unit is graded only when every declared standard has evidence."))
                    .font(.system(size: 11)).foregroundStyle(Palette.secondary)
                Text(store.gradebook.text("scope_note",
                                          fallback: "Formative, course-local mastery score."))
                    .font(.system(size: 10)).foregroundStyle(Palette.secondary)
                if units.isEmpty {
                    EmptyState(icon: "rosette", title: "No units to grade yet",
                               message: "Open a course and answer some questions. No sample grades are shown.")
                } else {
                    ForEach(Array(units.enumerated()), id: \.offset) { _, unit in
                        VStack(alignment: .leading, spacing: 9) {
                            HStack {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(unit["unit"].string).font(.system(size: 13, weight: .semibold))
                                    Text(unit["strand"].string).font(.system(size: 10)).foregroundStyle(Palette.secondary)
                                }
                                Spacer()
                                if unit["grade"]["percent"].isNull {
                                    Tag(text: "NO GRADE YET", color: Palette.accentOchre.soft)
                                } else {
                                    Text(percent(unit["grade"]["percent"]))
                                        .font(.system(size: 15, weight: .semibold))
                                        .foregroundStyle(Palette.accentTeal.deep)
                                }
                            }
                            ForEach(Array(unit["standards"].array.enumerated()), id: \.offset) { _, standard in
                                HStack(alignment: .firstTextBaseline, spacing: 8) {
                                    Text(standard["title"].string).font(.system(size: 11))
                                    Spacer()
                                    Text(standard.text("status", fallback: "insufficient_evidence")
                                            .replacingOccurrences(of: "_", with: " "))
                                        .font(.system(size: 10))
                                        .foregroundStyle(Palette.secondary)
                                    Text(percent(standard["score"]))
                                        .font(.system(size: 11, weight: .medium))
                                        .frame(width: 42, alignment: .trailing)
                                }
                            }
                            .accessibilityElement(children: .combine)
                            if unit["gradeable"].bool {
                                Button("Freeze this grade") {
                                    store.run { await store.finaliseUnitGrade(key: unit["key"].string) }
                                }
                                .buttonStyle(LuminfestButtonStyle(compact: true))
                                .disabled(store.busy)
                                .accessibilityIdentifier("gradebook.finalise")
                            } else {
                                let missing = unit["missing"].array.map { $0.string }.joined(separator: ", ")
                                Text("Needs evidence on: \(missing)")
                                    .font(.system(size: 10)).foregroundStyle(Palette.secondary)
                            }
                        }
                        .padding(.vertical, 9)
                        Divider()
                    }
                }
            }
        }
    }
}

struct PerspectiveCard: View {
    @EnvironmentObject var store: AppStore
    @State private var dimension = "communication"
    @State private var score = 3
    @State private var note = ""
    private var projects: [JSON] { store.projects["items"].array }
    private var reviews: [JSON] { store.perspectives["reviews"].array }
    private var dimensions: [JSON] { store.perspectives["dimensions"].array }
    private var canSave: Bool {
        !projects.isEmpty && note.trimmingCharacters(in: .whitespacesAndNewlines).count >= 12 && !store.busy
    }

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: 17) {
                SectionHeading(title: "Perspective observations", detail: "WRITTEN EVIDENCE ONLY")
                Text(store.perspectives.text("privacy",
                                             fallback: "No telemetry or pointer activity is used to infer a perspective."))
                    .font(.system(size: 11)).foregroundStyle(Palette.secondary)
                ForEach(Array(dimensions.enumerated()), id: \.offset) { index, item in
                    VStack(alignment: .leading, spacing: 5) {
                        HStack {
                            Text(item["name"].string).font(.system(size: 12, weight: .medium))
                            Spacer()
                            Text(percent(item["value"]))
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundStyle(Palette.accent(at: index).deep)
                        }
                        if !item["value"].isNull {
                            ProgressView(value: max(0, min(1, item["value"].double)))
                                .tint(Palette.accent(at: index).deep)
                        }
                        Text(item.text("evidence", fallback: item.text("status", fallback: "Insufficient evidence")))
                            .font(.system(size: 10)).foregroundStyle(Palette.secondary)
                    }
                    .padding(.vertical, 5)
                }
                Divider()
                Text("Record an observation about your own work")
                    .font(.system(size: 12, weight: .semibold))
                if dimensions.isEmpty {
                    Text("Measurement definitions are still loading.").font(.system(size: 11))
                        .foregroundStyle(Palette.secondary)
                } else {
                    Picker("Dimension", selection: $dimension) {
                        ForEach(Array(dimensions.enumerated()), id: \.offset) { _, item in
                            Text(item["name"].string).tag(item["code"].string)
                        }
                    }.font(.system(size: 11))
                    Stepper(value: $score, in: 0...4) {
                        Text("Rubric score: \(score) / 4").font(.system(size: 11))
                    }.font(.system(size: 11))
                    TextField("Describe what you actually observed", text: $note, axis: .vertical)
                        .lineLimit(2...4).textFieldStyle(.roundedBorder)
                        .font(.system(size: 11))
                        .accessibilityIdentifier("perspective.note")
                    if projects.isEmpty {
                        Text("Open Projects once to create an artifact, then an observation can be attached to it.")
                            .font(.system(size: 10)).foregroundStyle(Palette.secondary)
                    }
                    Button("Save observation") {
                        let trimmed = note.trimmingCharacters(in: .whitespacesAndNewlines)
                        store.run {
                            await store.recordSelfObservation(projectID: projects[0]["id"].string,
                                                              dimension: dimension, score: score,
                                                              note: trimmed)
                        }
                        note = ""
                    }
                    .buttonStyle(LuminfestButtonStyle(compact: true))
                    .disabled(!canSave)
                    .accessibilityIdentifier("perspective.save")
                    Text("A bare score is refused. Written evidence is required, and you can withdraw it.")
                        .font(.system(size: 10)).foregroundStyle(Palette.secondary)
                }
                if !reviews.isEmpty {
                    ForEach(Array(reviews.enumerated()), id: \.offset) { _, review in
                        HStack(alignment: .top) {
                            VStack(alignment: .leading, spacing: 3) {
                                Text("\(review["dimension"].string.capitalized) · \(review["score"].int)/4")
                                    .font(.system(size: 11, weight: .medium))
                                Text(review["evidence_note"].string).font(.system(size: 10))
                                    .foregroundStyle(Palette.secondary)
                            }
                            Spacer()
                            Button("Withdraw") {
                                store.run { await store.withdrawObservation(id: review["id"].string) }
                            }.buttonStyle(.borderless).font(.system(size: 10))
                        }
                        .padding(.vertical, 4)
                    }
                }
                Text(store.perspectives.text("accreditation",
                                            fallback: "Formative feedback, not an accredited grade or trait diagnosis."))
                    .font(.system(size: 10)).foregroundStyle(Palette.secondary)
            }
        }
    }
}
