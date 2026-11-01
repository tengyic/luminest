import SwiftUI

/// First-run setup: choose a subject, say what you are aiming for, choose a daily pace.
///
/// Three steps rather than one long form, because each answer changes what the next step
/// can honestly offer. The pace step shows the arithmetic the server will actually use, so
/// the learner can see what "20 minutes a day" buys before committing to it.
struct CourseSetupView: View {
    @EnvironmentObject var store: AppStore
    @StateObject private var lumi = LumiCompanion()
    @State private var step = 0
    @State private var courseID = ""
    @State private var goal = ""
    @State private var minutes = 20

    private var selected: JSON { store.courseList.first { $0["id"].string == courseID } ?? .null }
    private var canContinue: Bool {
        switch step {
        case 0: return !courseID.isEmpty
        default: return true
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().overlay(Palette.line)
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    switch step {
                    case 0: subjectStep
                    case 1: goalStep
                    default: paceStep
                    }
                }
                .padding(28)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            Divider().overlay(Palette.line)
            footer
        }
        // Fills the window: first-run setup is a shell branch rather than a sheet, so it owns the
        // whole surface and the three steps read as a page instead of a dialog.
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Palette.background)
        .foregroundStyle(Palette.ink)
        .onAppear {
            if courseID.isEmpty { courseID = store.enrolledCourseID.isEmpty ? (store.courseList.first?["id"].string ?? "") : store.enrolledCourseID }
            let existing = store.user["goal"].string
            if goal.isEmpty, !existing.isEmpty { goal = existing }
            minutes = max(5, store.user["daily_minutes"].int == 0 ? 20 : store.user["daily_minutes"].int)
            // Mood first, then the wave: the wave is a script, so a mood set during it
            // would be deferred until the wave finishes and the greeting would overrun.
            lumi.setMood(.listening)
            lumi.greet("Three quick questions, then we start.")
        }
    }

    private var header: some View {
        HStack(alignment: .top, spacing: 16) {
            LumiSetupGuide(lumi: lumi, step: step)
            VStack(alignment: .leading, spacing: 6) {
                Eyebrow(text: "SETTING UP YOUR LEARNING SPACE")
                Text(titles[step])
                    .font(.system(size: 24, weight: .semibold, design: .rounded))
                    .tracking(-0.6)
                Text(subtitles[step])
                    .font(.system(size: 12))
                    .foregroundStyle(Palette.secondary)
                    .lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true)
                // Lumi speaks here only while she has something to say; the step's own
                // subtitle stays put so the instruction never disappears under her.
                if let line = lumi.speech {
                    Text(line)
                        .font(.system(size: 11, design: .serif))
                        .italic()
                        .foregroundStyle(Palette.forest.opacity(0.9))
                        .padding(.top, 2)
                        .transition(.opacity)
                        .accessibilityLabel("Lumi says: \(line)")
                }
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 8) {
                Text("STEP \(step + 1) OF 3")
                    .font(.system(size: 9, weight: .semibold))
                    .tracking(1.6)
                    .foregroundStyle(Palette.secondary)
                    .accessibilityIdentifier("setup.step")
                HStack(spacing: 5) {
                    ForEach(0..<3, id: \.self) { index in
                        Capsule()
                            .fill(index <= step ? Palette.forest : Palette.line)
                            .frame(width: index == step ? 22 : 12, height: 4)
                    }
                }
            }
        }
        .padding(28)
        .background(Color.white.opacity(0.6))
    }

    private let titles = ["What would you like to learn?", "What are you aiming for?", "How much time a day?"]
    private let subtitles = [
        "Every course is its own knowledge map with its own practice items. You can switch later without losing what you have recorded.",
        "Say it in your own words. This is the framing the tutor is given - the harness also tracks a measurable target, and will never claim your goal has been reached.",
        "This is your budget, not a target set for you. It decides how much fits in one session, and the plan is re-derived every time you open Luminfest.",
    ]

    // MARK: Step 1 - subject

    private var subjectStep: some View {
        VStack(alignment: .leading, spacing: 14) {
            ForEach(store.courseList, id: \.self) { course in
                CourseOptionRow(course: course, isSelected: course["id"].string == courseID) {
                    courseID = course["id"].string
                }
            }
            if store.courseList.isEmpty {
                EmptyState(icon: "books.vertical", title: "No courses available",
                           message: "The server did not return a course catalogue. Check the connection and try again.")
            }
        }
    }

    // MARK: Step 2 - goal

    private var goalStep: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Your goal")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Palette.secondary)
                TextField("For example: get ready for university physics", text: $goal, axis: .vertical)
                    .textFieldStyle(.plain)
                    .lineLimit(2...4)
                    .padding(13)
                    .background(Color.white, in: RoundedRectangle(cornerRadius: 11, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 11, style: .continuous).stroke(Palette.line, lineWidth: 1))
                    .accessibilityIdentifier("setup.goal")
            }
            Text("Not sure? Pick one of these, or write your own.")
                .font(.system(size: 11))
                .foregroundStyle(Palette.secondary)
            FlowRow(spacing: 8) {
                ForEach(goalSuggestions, id: \.self) { suggestion in
                    Button { goal = suggestion } label: {
                        Tag(text: suggestion, color: goal == suggestion ? Palette.eucalyptus : Palette.muted)
                    }
                    .buttonStyle(.plain)
                }
            }
            Card(color: Palette.lavender) {
                VStack(alignment: .leading, spacing: 8) {
                    Eyebrow(text: "WHAT THE HARNESS WILL MEASURE")
                    Text("Mastery at or above 0.85 with at least three scored attempts on every concept the course offers, met in prerequisite order.")
                        .font(.system(size: 12))
                        .lineSpacing(4)
                    Text("Your words are the framing. This is the measurement. Reaching it is evidence toward your goal, not proof of it.")
                        .font(.system(size: 11))
                        .foregroundStyle(Palette.secondary)
                        .lineSpacing(3)
                }
            }
            if goal.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Text("You can leave this blank and add it later in Settings.")
                    .font(.system(size: 11))
                    .foregroundStyle(Palette.secondary)
            }
        }
    }

    private let goalSuggestions = [
        "Understand the ideas, not just pass",
        "Build real confidence from the ground up",
        "Get ready for the next course",
        "Fill in gaps I know I have",
    ]

    // MARK: Step 3 - pace

    private var paceStep: some View {
        VStack(alignment: .leading, spacing: 20) {
            Card(color: Palette.sage) {
                VStack(alignment: .leading, spacing: 12) {
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text("\(minutes)")
                            .font(.system(size: 44, weight: .medium, design: .rounded))
                            .tracking(-1.6)
                        Text("minutes a day")
                            .font(.system(size: 13))
                            .foregroundStyle(Palette.secondary)
                    }
                    Slider(value: Binding(get: { Double(minutes) }, set: { minutes = Int($0) }), in: 5...90, step: 5)
                        .tint(Palette.forest)
                        .accessibilityIdentifier("setup.pace")
                    HStack(spacing: 8) {
                        ForEach([10, 20, 30, 45, 60], id: \.self) { preset in
                            Button { minutes = preset } label: {
                                Tag(text: "\(preset) min", color: minutes == preset ? Palette.eucalyptus : Palette.muted)
                            }
                            .buttonStyle(.plain)
                            .accessibilityIdentifier("setup.pace.\(preset)")
                        }
                        Spacer()
                    }
                }
            }
            Card(color: Palette.sky) {
                VStack(alignment: .leading, spacing: 12) {
                    Eyebrow(text: "WHAT THAT BUYS, ON THIS COURSE")
                    paceLine("Items a day", "\(pace.itemsPerDay)")
                    paceLine("Concepts a day", "\(pace.conceptsPerDay)")
                    paceLine("Concepts a week", "\(pace.conceptsPerWeek) over \(pace.sessionsPerWeek) sessions")
                    paceLine("Course size", courseSize)
                    paceLine("At this pace", weeksLine)
                    Divider().overlay(Palette.line)
                    Text(pace.basis)
                        .font(.system(size: 10))
                        .foregroundStyle(Palette.secondary)
                        .lineSpacing(3)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Card(color: Palette.oat) {
                VStack(alignment: .leading, spacing: 8) {
                    Eyebrow(text: "WHAT HAPPENS NEXT")
                    Text("You will land on Today with a short first session. A few quick checks tell the harness what you already know, and the plan adjusts to that from then on. Nothing is set in stone: change your course, goal or pace in Settings at any time.")
                        .font(.system(size: 12))
                        .foregroundStyle(Palette.secondary)
                        .lineSpacing(4)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private func paceLine(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label).font(.system(size: 12)).foregroundStyle(Palette.secondary)
            Spacer()
            Text(value).font(.system(size: 12, weight: .semibold))
        }
    }

    /// The same arithmetic the server applies, computed locally so the slider is honest
    /// before the learner commits. Mirrors `app/planner.py`.
    private var pace: (itemsPerDay: Int, conceptsPerDay: Int, conceptsPerWeek: Int, sessionsPerWeek: Int, basis: String) {
        let practiceShare = 0.75, secondsPerItem = 75.0, feedback = 1.35, itemsPerConcept = 4, sessions = 5
        let practiceSeconds = Double(max(5, minutes)) * 60 * practiceShare
        let items = max(3, Int(practiceSeconds / (secondsPerItem * feedback)))
        let concepts = max(1, Int((Double(items) / Double(itemsPerConcept)).rounded()))
        return (items, concepts, concepts * sessions, sessions,
                "Item seconds are the expected time each item carries; the feedback overhead and practice share are project constants, not measurements of you.")
    }

    private var courseSize: String {
        let nodes = selected["stats"]["concepts"].int
        let withContent = selected["concepts_with_content"].int
        guard nodes > 0 else { return "—" }
        return withContent > 0 && withContent < nodes
            ? "\(nodes) concepts, \(withContent) with practice items"
            : "\(nodes) concepts"
    }

    private var weeksLine: String {
        let nodes = max(1, selected["concepts_with_content"].int > 0 ? selected["concepts_with_content"].int : selected["stats"]["concepts"].int)
        let weeks = Double(nodes) / Double(max(1, pace.conceptsPerWeek))
        return "about \(String(format: "%.1f", weeks)) weeks of practice"
    }

    // MARK: Footer

    private var footer: some View {
        HStack(spacing: 12) {
            if let message = store.setupError {
                HStack(spacing: 6) {
                    Image(systemName: "exclamationmark.circle")
                    Text(message).lineLimit(2)
                }
                .font(.system(size: 11))
                .foregroundStyle(Palette.peachDeep)
            }
            Spacer()
            if step > 0 {
                Button("Back") { withAnimation(.easeInOut(duration: 0.18)) { step -= 1 } }
                    .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
            }
            Button("Skip for now") {
                store.setupDismissed = true
                store.showCourseSetup = false
            }
            .buttonStyle(.plain)
            .font(.system(size: 11))
            .foregroundStyle(Palette.secondary)
            .accessibilityIdentifier("setup.skip")
            if step < 2 {
                Button("Continue") { withAnimation(.easeInOut(duration: 0.18)) { step += 1 } }
                    .buttonStyle(LuminfestButtonStyle(compact: true))
                    .disabled(!canContinue)
                    .accessibilityIdentifier("setup.continue")
            } else {
                Button {
                    store.run { await store.saveSetup(courseID: courseID, goal: goal, minutes: minutes) }
                } label: {
                    HStack(spacing: 6) {
                        if store.setupBusy { ProgressView().controlSize(.small) }
                        Text("Start learning")
                        Image(systemName: "arrow.right")
                    }
                }
                .buttonStyle(LuminfestButtonStyle(compact: true))
                .disabled(store.setupBusy || courseID.isEmpty)
                .accessibilityIdentifier("setup.finish")
            }
        }
        .padding(.horizontal, 28)
        .padding(.vertical, 18)
        .background(Color.white.opacity(0.6))
    }
}

/// One course in the picker, with the size facts a learner needs to choose.
private struct CourseOptionRow: View {
    let course: JSON
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(alignment: .top, spacing: 14) {
                ZStack {
                    Circle().fill(isSelected ? Palette.forest : Palette.muted)
                        .frame(width: 22, height: 22)
                    if isSelected {
                        Image(systemName: "checkmark").font(.system(size: 11, weight: .bold)).foregroundStyle(.white)
                    }
                }
                .padding(.top, 2)
                VStack(alignment: .leading, spacing: 7) {
                    HStack(spacing: 8) {
                        Text(course.text("title", fallback: "Course"))
                            .font(.system(size: 15, weight: .semibold, design: .rounded))
                        if course["authored"].bool {
                            Tag(text: "HAND-WRITTEN", color: Palette.eucalyptus)
                        } else {
                            Tag(text: "GRAPH-GENERATED", color: Palette.lavender)
                        }
                    }
                    Text(course.text("description", fallback: ""))
                        .font(.system(size: 11.5))
                        .foregroundStyle(Palette.secondary)
                        .lineSpacing(3.5)
                        .fixedSize(horizontal: false, vertical: true)
                    HStack(spacing: 14) {
                        fact("point.3.connected.trianglepath.dotted", "\(course["stats"]["concepts"].int) concepts")
                        fact("arrow.triangle.branch", "\(course["stats"]["strands"].int) strands")
                        fact("calendar", "\(course["expected_weeks"].int) weeks")
                    }
                }
                Spacer()
            }
            .padding(16)
            .background(isSelected ? Palette.sage.opacity(0.55) : Color.white.opacity(0.75),
                        in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .stroke(isSelected ? Palette.forest.opacity(0.45) : Palette.line, lineWidth: isSelected ? 1.4 : 1)
            )
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("setup.course." + course["id"].string)
    }

    private func fact(_ icon: String, _ text: String) -> some View {
        HStack(spacing: 4) {
            Image(systemName: icon).font(.system(size: 9.5))
            Text(text).font(.system(size: 10.5, weight: .medium))
        }
        .foregroundStyle(Palette.secondary)
    }
}

/// A small wrapping row, used for the goal suggestion chips.
struct FlowRow: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxWidth = proposal.width ?? .infinity
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > 0, x + size.width > maxWidth { x = 0; y += rowHeight + spacing; rowHeight = 0 }
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return CGSize(width: maxWidth == .infinity ? x : maxWidth, height: y + rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX, y = bounds.minY, rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > bounds.minX, x + size.width > bounds.maxX { x = bounds.minX; y += rowHeight + spacing; rowHeight = 0 }
            subview.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}

/// The plan, on Today. This is where the stated goal becomes a session.
struct PlanCard: View {
    @EnvironmentObject var store: AppStore

    var body: some View {
        Card(color: Palette.oat) {
            VStack(alignment: .leading, spacing: 16) {
                HStack(alignment: .firstTextBaseline) {
                    Eyebrow(text: "YOUR PLAN")
                    Spacer()
                    if !store.courseTitle.isEmpty {
                        Tag(text: store.courseSubject.uppercased(), color: Palette.muted)
                    }
                }
                if store.plan.isNull {
                    Text("Your plan is being derived from this course and your recorded answers.")
                        .font(.system(size: 12))
                        .foregroundStyle(Palette.secondary)
                } else {
                    goalLine
                    paceStrip
                    todayList
                    progressLine
                    if !blockedNote.isEmpty { blockedNoteView }
                    disclosure
                }
            }
        }
    }

    private var goalLine: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(store.courseTitle)
                .font(.system(size: 17, weight: .semibold, design: .rounded))
                .tracking(-0.3)
            let stated = store.plan["goal"]["stated"].string
            Text(stated.isEmpty
                 ? "No goal set yet. Add one in Settings and the plan will frame itself around it."
                 : "\u{201C}\(stated)\u{201D}")
                .font(.system(size: 12))
                .foregroundStyle(Palette.secondary)
                .lineSpacing(3.5)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var paceStrip: some View {
        VStack(spacing: 8) {
            HStack(spacing: 0) {
                stripCell("\(store.planPace["items_per_day"].int)", "items today")
                stripDivider
                stripCell("\(store.planPace["concepts_per_day"].int)", "concepts")
                stripDivider
                stripCell("\(store.planPace["daily_minutes"].int)", "minutes")
                stripDivider
                stripCell(weeksText, "weeks at this pace")
            }
            Text(store.planPace.text("adjustment_reason", fallback: "Pace follows your chosen daily time budget."))
                .font(.system(size: 10))
                .foregroundStyle(Palette.secondary)
                .lineSpacing(3)
                .frame(maxWidth: .infinity, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 12)
        }
        .padding(.vertical, 12)
        .background(Color.white.opacity(0.7), in: RoundedRectangle(cornerRadius: 13, style: .continuous))
    }

    private var stripDivider: some View { Rectangle().fill(Palette.line).frame(width: 1, height: 26) }

    private func stripCell(_ value: String, _ label: String) -> some View {
        VStack(spacing: 3) {
            Text(value).font(.system(size: 19, weight: .semibold, design: .rounded))
            Text(label).font(.system(size: 9.5)).foregroundStyle(Palette.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    private var weeksText: String {
        let weeks = store.planProgress["weeks_remaining_at_current_pace"]
        return weeks.isNull ? "—" : weeks.double.formatted(.number.precision(.fractionLength(0...1)))
    }

    private var todayList: some View {
        VStack(alignment: .leading, spacing: 9) {
            Eyebrow(text: "TODAY, IN THIS ORDER")
            if store.planToday.isEmpty {
                Text("Nothing is queued: either everything the course offers is secure, or the next concepts are waiting on a measured gap. Check the Knowledge map.")
                    .font(.system(size: 11.5))
                    .foregroundStyle(Palette.secondary)
                    .lineSpacing(3.5)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                ForEach(Array(store.planToday.enumerated()), id: \.offset) { index, row in
                    Button {
                        store.selectedConcept = row["concept_id"].string
                        store.navigate(.studio)
                    } label: {
                        HStack(alignment: .top, spacing: 11) {
                            Text("\(index + 1)")
                                .font(.system(size: 10, weight: .bold))
                                .frame(width: 18, height: 18)
                                .background(Palette.forest, in: Circle())
                                .foregroundStyle(.white)
                                .padding(.top, 1)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(row.text("title", fallback: row["concept_id"].string))
                                    .font(.system(size: 12.5, weight: .medium))
                                Text(row.text("why", fallback: ""))
                                    .font(.system(size: 10.5))
                                    .foregroundStyle(Palette.secondary)
                                    .lineSpacing(3)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            Spacer()
                            Image(systemName: "chevron.right").font(.system(size: 9)).foregroundStyle(Palette.tertiary)
                        }
                        .padding(11)
                        .background(Color.white.opacity(0.75), in: RoundedRectangle(cornerRadius: 11, style: .continuous))
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("plan.concept." + row["concept_id"].string)
                }
                Button {
                    store.run { await store.startQuestion(mode: "practice", concept: store.planToday.first?["concept_id"].string) }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "play.fill").font(.system(size: 10))
                        Text("Start today's practice")
                    }
                }
                .buttonStyle(LuminfestButtonStyle(compact: true))
                .accessibilityIdentifier("plan.start")
            }
        }
    }

    private var progressLine: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("Secure: \(store.planProgress["secure"].int) of \(store.planProgress["concepts_offered"].int) offered")
                    .font(.system(size: 11, weight: .medium))
                Spacer()
                Text("\(store.planProgress["percent_secure"].double.formatted(.number.precision(.fractionLength(0...1))))%")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Palette.forest)
            }
            ProgressView(value: min(1, max(0, store.planProgress["percent_secure"].double / 100)))
                .tint(Palette.forest)
        }
    }

    private var blockedNote: String {
        let count = store.plan["blocked_total"].int
        guard count > 0 else { return "" }
        return "\(count) concept(s) are listed but not scheduled: something they rest on is measured as not yet ready. Those come first."
    }

    private var blockedNoteView: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "info.circle").foregroundStyle(Palette.slate)
            Text(blockedNote).font(.system(size: 10.5)).foregroundStyle(Palette.secondary).lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(10)
        .background(Palette.sky.opacity(0.5), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private var disclosure: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 7) {
                ForEach(Array(store.plan["honesty"].array.enumerated()), id: \.offset) { _, line in
                    HStack(alignment: .top, spacing: 6) {
                        Text("•").foregroundStyle(Palette.tertiary)
                        Text(line.string).font(.system(size: 10.5)).foregroundStyle(Palette.secondary).lineSpacing(3)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                Text(store.plan["progress"]["projection_basis"].string)
                    .font(.system(size: 10.5)).foregroundStyle(Palette.secondary).lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.top, 8)
        } label: {
            Text("What this plan is not").font(.system(size: 11, weight: .medium)).foregroundStyle(Palette.forest)
        }
        .font(.system(size: 11))
    }
}

/// Course switching, for Settings. Enrolling is a real change of context, not a preference,
/// so it says plainly what it does to the recorded evidence.
struct CourseSwitcher: View {
    @EnvironmentObject var store: AppStore
    @State private var confirmID = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(store.courseList, id: \.self) { course in
                let id = course["id"].string
                let isCurrent = id == store.enrolledCourseID
                HStack(alignment: .top, spacing: 12) {
                    VStack(alignment: .leading, spacing: 5) {
                        HStack(spacing: 7) {
                            Text(course.text("title", fallback: "Course"))
                                .font(.system(size: 13, weight: .semibold))
                            if isCurrent { Tag(text: "ENROLLED", color: Palette.eucalyptus) }
                        }
                        Text("\(course["stats"]["concepts"].int) concepts - \(course.text("subject", fallback: ""))")
                            .font(.system(size: 10.5))
                            .foregroundStyle(Palette.secondary)
                    }
                    Spacer()
                    if !isCurrent {
                        if confirmID == id {
                            HStack(spacing: 8) {
                                Button("Switch") {
                                    confirmID = ""
                                    store.run { await store.switchCourse(id) }
                                }
                                .buttonStyle(LuminfestButtonStyle(compact: true))
                                Button("Cancel") { confirmID = "" }
                                    .buttonStyle(.plain)
                                    .font(.system(size: 11))
                                    .foregroundStyle(Palette.secondary)
                            }
                        } else {
                            Button("Enrol") { confirmID = id }
                                .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
                        }
                    }
                }
                .padding(13)
                .background(isCurrent ? Palette.sage.opacity(0.5) : Color.white.opacity(0.7),
                            in: RoundedRectangle(cornerRadius: 13, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 13, style: .continuous)
                    .stroke(isCurrent ? Palette.forest.opacity(0.35) : Palette.line, lineWidth: 1))
                .accessibilityIdentifier("settings.course." + id)
            }
            if confirmID == store.courseList.first(where: { $0["id"].string != store.enrolledCourseID })?["id"].string {
                Text("Switching changes the map, the practice items and the figures. What you have already recorded stays attached to the concepts it was recorded on and is not mixed between courses, so switching back restores your progress.")
                    .font(.system(size: 10.5))
                    .foregroundStyle(Palette.secondary)
                    .lineSpacing(3.5)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}
