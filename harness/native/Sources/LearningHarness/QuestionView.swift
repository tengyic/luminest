import SwiftUI

struct QuestionView: View {
    @EnvironmentObject var store: AppStore
    @State private var confirmFinish = false
    var exam: Bool { store.question["mode"].string == "exam" }
    var canSubmit: Bool { !store.answerOption.isEmpty || !store.answerText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                HStack(spacing: 10) { Image(systemName: "sun.max.fill").foregroundStyle(Palette.forest); Text("A moment of practice").font(.system(size: 15, weight: .semibold)) }
                Spacer()
                Tag(text: store.question.text("mode", fallback: "Learning").uppercased(), color: Palette.lavender)
                Button { if store.attempt.isNull && !store.question.isNull { confirmFinish = true } else { store.requestFinishQuestion() } } label: { Image(systemName: "xmark").font(.system(size: 12)).padding(8).background(Palette.muted, in: Circle()) }.buttonStyle(.plain).help("Finish session")
            }.padding(24).background(Color.white.opacity(0.6))
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    if store.question.isNull {
                        if store.questionBusy { ProgressView("Preparing your next question…").frame(maxWidth: .infinity).padding(60) }
                        else {
                            EmptyState(icon: "checkmark.circle", title: "No question available", message: store.questionError ?? "The backend has no question for this session. You can finish and return to your learning space.")
                            if store.questionError != nil {
                                Button("Retry loading question") { store.run { await store.startQuestion(mode: store.pendingQuestionMode, concept: store.pendingQuestionConcept) } }.buttonStyle(LuminfestButtonStyle(primary: false)).accessibilityIdentifier("question.retry")
                            }
                        }
                    } else {
                        HStack {
                            Eyebrow(text: store.question["concept_title"].string.uppercased())
                            Spacer()
                            Text("\(store.question["progress"]["answered"].int) / \(store.question["progress"]["total"].int) answered").font(.system(size: 11)).foregroundStyle(Palette.secondary)
                            Image(systemName: "timer").foregroundStyle(Palette.forest)
                            Text(String(format: "%02d:%02d", Int(store.questionElapsed) / 60, Int(store.questionElapsed) % 60)).font(.system(size: 12, design: .monospaced)).foregroundStyle(Palette.forest)
                        }
                        if exam { Label("Exam session · tutor help is unavailable", systemImage: "lock").font(.system(size: 11)).foregroundStyle(Palette.secondary) }
                        else if !store.question["selection_reason"].string.isEmpty { Text(store.question["selection_reason"].string).font(.system(size: 11)).foregroundStyle(Palette.secondary) }
                        Text(store.question["prompt"].string).font(.system(size: 22, weight: .medium)).tracking(-0.4).lineSpacing(6).fixedSize(horizontal: false, vertical: true)
                        if !store.question["options"].array.isEmpty {
                            VStack(spacing: 10) {
                                ForEach(store.question["options"].array, id: \.["id"].string) { option in
                                    Button {
                                        store.answerOption = option["id"].string
                                        // The control id the accessibility tree already uses, so
                                        // the interaction summary and a UI test name the same thing.
                                        store.recordInteraction("question.option." + ClickTelemetry.sanitise(option["id"].string))
                                    } label: {
                                        HStack(spacing: 14) {
                                            ZStack { Circle().stroke(store.answerOption == option["id"].string ? Palette.forest : Palette.secondary.opacity(0.4), lineWidth: 1.5).frame(width: 18, height: 18); if store.answerOption == option["id"].string { Circle().fill(Palette.forest).frame(width: 10, height: 10) } }
                                            Text(option["text"].string).font(.system(size: 14)).multilineTextAlignment(.leading)
                                            Spacer()
                                        }.padding(17).background(store.answerOption == option["id"].string ? Palette.sage : Color.white, in: RoundedRectangle(cornerRadius: 13)).overlay(RoundedRectangle(cornerRadius: 13).strokeBorder(store.answerOption == option["id"].string ? Palette.forest.opacity(0.5) : Palette.line, lineWidth: 1))
                                    }.buttonStyle(.plain).disabled(store.answerFrozen || !store.attempt.isNull).accessibilityIdentifier("question.option." + option["id"].string)
                                }
                            }
                        } else {
                            VStack(alignment: .leading, spacing: 9) { Text("Your answer").font(.system(size: 12, weight: .semibold)); TextField("Enter a numeric or written answer", text: $store.answerText, axis: .vertical).lineLimit(2...5).textFieldStyle(.plain).padding(15).background(Color.white, in: RoundedRectangle(cornerRadius: 12)).overlay(RoundedRectangle(cornerRadius: 12).stroke(Palette.line)).disabled(store.answerFrozen || !store.attempt.isNull).accessibilityIdentifier("question.answer") }
                        }
                        VStack(alignment: .leading, spacing: 9) {
                            HStack { Text("Show your thinking").font(.system(size: 12, weight: .semibold)); Text("Optional").font(.system(size: 10)).foregroundStyle(Palette.secondary) }
                            TextEditor(text: $store.reasoning).font(.system(size: 13)).scrollContentBackground(.hidden).padding(10).frame(height: 88).background(Color.white, in: RoundedRectangle(cornerRadius: 12)).overlay(RoundedRectangle(cornerRadius: 12).stroke(Palette.line)).disabled(store.answerFrozen || !store.attempt.isNull).accessibilityIdentifier("question.reasoning")
                        }
                        if store.attempt.isNull {
                            HStack { Text("How confident do you feel?").font(.system(size: 11)).foregroundStyle(Palette.secondary); Slider(value: $store.confidence, in: 0...1).tint(Palette.forest).frame(maxWidth: 180).disabled(store.answerFrozen); Text("\(Int(store.confidence * 100))%").font(.system(size: 11, design: .monospaced)) }
                        }
                        if !store.attempt.isNull { feedback }
                        if let error = store.questionError { Text(error + (store.answerFrozen ? "\nRetry sends the exact same answer and event ID; it will not create a new attempt." : "")).font(.system(size: 12)).foregroundStyle(.red).textSelection(.enabled) }
                        Text("The timer uses a monotonic clock and counts only while the app is foregrounded and this question is active. No clipboard monitoring or punitive focus conclusions.").font(.system(size: 10)).foregroundStyle(Palette.secondary).lineSpacing(3)
                    }
                }.padding(30)
            }
            HStack {
                Button("Finish") { if store.attempt.isNull && !store.question.isNull { confirmFinish = true } else { store.requestFinishQuestion() } }.buttonStyle(LuminfestButtonStyle(primary: false)).accessibilityIdentifier("question.finish")
                if store.attempt.isNull && !store.question.isNull {
                    Button(store.questionPaused ? "Resume timer" : "Pause") { store.questionPaused.toggle() }.buttonStyle(.borderless).font(.system(size: 12)).disabled(store.answerFrozen)
                }
                Spacer()
                if store.questionBusy { ProgressView().controlSize(.small) }
                if !store.attempt.isNull {
                    if store.attempt["assessment_complete"].bool || store.attempt["exam_complete"].bool { Button("Finish session") { store.requestFinishQuestion() }.buttonStyle(LuminfestButtonStyle()).accessibilityIdentifier("question.next") }
                    else { Button { let mode = store.question.text("mode", fallback: "practice"); let concept = mode == "diagnostic" || mode == "exam" ? nil : store.question["concept_id"].string; store.run { await store.startQuestion(mode: mode, concept: concept) } } label: { Label("Next question", systemImage: "arrow.right") }.buttonStyle(LuminfestButtonStyle()).accessibilityIdentifier("question.next") }
                } else if !store.question.isNull {
                    Button(store.answerFrozen ? "Retry submission" : "Submit answer") { store.recordInteraction("question.submit"); store.run { await store.submitAnswer() } }.buttonStyle(LuminfestButtonStyle()).disabled(!canSubmit || store.questionBusy || store.questionPaused).accessibilityIdentifier("question.submit")
                }
            }.padding(24).background(Color.white.opacity(0.6))
        }
        // Sized for the overlay card it is hosted in, not for a sheet. The height is capped rather
        // than fixed so a short window still fits the card, and the inner ScrollView absorbs the
        // remainder. `interactiveDismissDisabled` is gone with the sheet: there is no presentation
        // left to swipe away, and the scrim in `RootView` is deliberately inert.
        .frame(width: 760)
        .frame(maxHeight: 720)
        .background(Palette.background).foregroundStyle(Palette.ink)
            .confirmationDialog("Finish this session? Your unsubmitted answer will not be saved.", isPresented: $confirmFinish, titleVisibility: .visible) { Button("Finish session", role: .destructive) { store.requestFinishQuestion() }; Button("Keep learning", role: .cancel) {} }
    }
    var feedback: some View {
        Card(color: store.attempt["correct"].bool ? Palette.sage : Palette.peach, padding: 20) {
            VStack(alignment: .leading, spacing: 12) {
                Label(store.attempt["correct"].isNull ? "Answer recorded. Feedback is withheld until the exam ends." : (store.attempt["correct"].bool ? "You’ve got it." : "A useful place to look closer."), systemImage: store.attempt["correct"].isNull ? "lock" : (store.attempt["correct"].bool ? "checkmark.circle" : "lightbulb")).font(.system(size: 17, weight: .semibold))
                if !store.attempt["correct_answer"].isNull { Text("Correct answer: " + store.attempt["correct_answer"].string).font(.system(size: 13, weight: .medium)) }
                Text(store.attempt["explanation"].string).font(.system(size: 13)).lineSpacing(5).textSelection(.enabled)
                let diagnosis = store.attempt["diagnosis"]
                if !diagnosis.isNull {
                    Divider()
                    Text(diagnosis["category"].string.replacingOccurrences(of: "_", with: " ").capitalized).font(.system(size: 12, weight: .semibold))
                    Text(diagnosis["reason"].string).font(.system(size: 12)).foregroundStyle(Palette.secondary)
                    Text(diagnosis["next_action"].string).font(.system(size: 12))
                    Text("Diagnosis confidence: " + percent(diagnosis["confidence"])).font(.system(size: 10)).foregroundStyle(Palette.secondary)
                }
                if !store.attempt["mastery"].isNull { HStack { Tag(text: "Estimated mastery " + percent(store.attempt["mastery"]), color: .white.opacity(0.65)); if !store.attempt["review_at"].isNull { Text("Review " + friendlyDate(store.attempt["review_at"].string)).font(.system(size: 10)).foregroundStyle(Palette.secondary) } } }
                if !store.attempt["grade"].isNull {
                    Text("Practice-exam score: " + store.attempt["grade"].string + "%").font(.system(size: 14, weight: .semibold))
                    Text(store.attempt["assessment_label"].string + " · " + store.attempt["scope"].string).font(.system(size: 10)).foregroundStyle(Palette.secondary)
                    ForEach(Array(store.attempt["item_breakdown"].array.enumerated()), id: \.offset) { _, item in
                        Text(item.text("concept_id") + " · " + (item["correct"].bool ? "Correct" : "Review") + " · " + item.text("explanation")).font(.system(size: 11)).lineSpacing(3)
                    }
                }
            }
        }
    }
}
