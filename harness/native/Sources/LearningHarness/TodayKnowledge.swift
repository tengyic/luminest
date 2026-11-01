import SwiftUI

struct TodayView: View {
    @EnvironmentObject var store: AppStore
    /// When on, the Today hero is driven by the 9-MOVES harness decision rather than the
    /// simpler planner recommendation. The fallback stays visible when the harness is
    /// unreachable - the degradation is labelled, never silent.
    @AppStorage("harness.plan.primary") private var harnessPrimary = false
    var stats: JSON { store.dashboard["stats"] }
    var recommendation: JSON { store.dashboard["recommendation"] }
    var decision: HarnessDecision? { store.harnessPlanState.decision }
    var body: some View {
        VStack(spacing: 24) {
            HStack(spacing: 18) {
                Card(color: Palette.sage) {
                    HStack(spacing: 12) {
                        VStack(alignment: .leading, spacing: 15) {
                            HStack(spacing: 8) {
                                Eyebrow(text: "YOUR NEXT SMALL STEP")
                                Tag(text: decision != nil && harnessPrimary ? "9-MOVES DECISION" : "ADAPTIVE",
                                    color: Palette.accentMoss.soft)
                                if harnessPrimary && decision == nil {
                                    Tag(text: "PLANNER FALLBACK", color: Palette.accentRose.soft)
                                }
                            }
                            if harnessPrimary, let decision {
                                Text(decision.move.capitalized)
                                    .font(.system(size: 26, weight: .semibold, design: .rounded))
                                    .tracking(-0.7)
                                    .fixedSize(horizontal: false, vertical: true)
                                Text(decision.reason)
                                    .font(.system(size: 12))
                                    .foregroundStyle(Palette.secondary)
                                    .lineSpacing(4)
                                    .fixedSize(horizontal: false, vertical: true)
                            } else {
                                Text(recommendation.text("title", fallback: "Find your starting point."))
                                    .font(.system(size: 26, weight: .semibold, design: .rounded))
                                    .tracking(-0.7)
                                    .fixedSize(horizontal: false, vertical: true)
                                Text(recommendation.text("reason", fallback: "A short diagnostic helps us understand what you know and what deserves a closer look."))
                                    .font(.system(size: 12))
                                    .foregroundStyle(Palette.secondary)
                                    .lineSpacing(4)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            ViewThatFits(in: .horizontal) {
                                HStack(spacing: 10) { heroActions }
                                VStack(alignment: .leading, spacing: 10) { heroActions }
                            }.padding(.top, 3)
                            if harnessPrimary {
                                HarnessPlanCard()
                            }
                            Toggle("Plan my next step with the full harness (9 moves, visible reasoning)",
                                   isOn: $harnessPrimary)
                                .toggleStyle(.switch).tint(Palette.accentTeal.deep)
                                .font(.system(size: 11))
                                .accessibilityIdentifier("today.harnessToggle")
                        }
                        OrbitArtwork().frame(width: 130, height: 165)
                    }
                }
                .spotlight(cornerRadius: 22, tint: Palette.forest, intensity: 0.13)
                .task(id: harnessPrimary) {
                    guard harnessPrimary else { return }
                    let concept = decision?.conceptID.isEmpty == false ? decision!.conceptID
                        : recommendation["concept_id"].string
                    await store.loadHarnessPlan(conceptID: concept)
                }
                Card(color: Palette.accentSky.soft) {
                    VStack(alignment: .leading, spacing: 14) {
                        HStack {
                            Eyebrow(text: "DAILY INTENTION", tint: Palette.accentSky.deep.opacity(0.9))
                            Spacer()
                            Image(systemName: "sun.horizon")
                                .foregroundStyle(Palette.accentSky.deep)
                        }
                        HStack(alignment: .firstTextBaseline, spacing: 5) {
                            Text(stats["active_minutes"].isNull ? "—" : stats["active_minutes"].double.formatted(.number.precision(.fractionLength(0...1))))
                                .font(.system(size: 40, weight: .medium, design: .rounded))
                                .tracking(-1.5)
                            Text("/ \(max(1, store.user["daily_minutes"].int)) min")
                                .font(.system(size: 12))
                                .foregroundStyle(Palette.secondary)
                        }
                        ProgressView(value: min(1, max(0, stats["active_minutes"].double / Double(max(1, store.user["daily_minutes"].int)))))
                            .tint(Palette.accentSky.deep)
                        Text(store.user["telemetry_consent"].bool ? "Foreground activity is a focus proxy, not a measure of attention." : "Activity tracking is off. Turn it on only if you want to, in Settings.")
                            .font(.system(size: 11))
                            .foregroundStyle(Palette.secondary)
                            .lineSpacing(3)
                    }
                }.frame(width: 245)
                .spotlight(cornerRadius: 22, tint: Palette.accentSky.deep, intensity: 0.15)
            }
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 15), count: 4), spacing: 15) {
                MetricCard(title: "Practice accuracy", value: stats["attempts"].int == 0 ? "—" : percent(stats["accuracy"]), detail: "From submitted answers", icon: "scope", accent: Palette.accentTeal)
                MetricCard(title: "Ideas mastered", value: stats["mastered"].isNull ? "—" : "\(stats["mastered"].int)", detail: "Based on learning evidence", icon: "checkmark.seal", accent: Palette.accentIndigo)
                MetricCard(title: "Ready to revisit", value: stats["due"].isNull ? "—" : "\(stats["due"].int)", detail: "Your scheduled reviews", icon: "arrow.trianglehead.clockwise", accent: Palette.accentClay)
                MetricCard(title: "Learning streak", value: stats["streak"].isNull ? "—" : "\(stats["streak"].int)", detail: "Days with real practice", icon: "flame", accent: Palette.accentOchre)
            }
            // The run of show for today's concept: which activity comes now, through which
            // artifact, for how long, and what the harness refused to schedule and why.
            // Independent of the 9-moves toggle above - the sequence is compiled either way.
            LessonProcedureCard()
                .task(id: store.lessonConceptID) {
                    guard !store.lessonConceptID.isEmpty else { return }
                    await store.loadLessonProcedure(conceptID: store.lessonConceptID)
                }
            HStack(alignment: .top, spacing: 20) {
                Card {
                    VStack(alignment: .leading, spacing: 20) {
                        SectionHeading(title: "Your learning rhythm", detail: "RECENT ACTIVITY")
                        if store.dashboard["recent"].array.isEmpty {
                            EmptyState(icon: "book.pages", title: "Your story starts here", message: "Complete a diagnostic or a practice question. Real activity will appear here—never invented progress.")
                        } else {
                            ForEach(Array(store.dashboard["recent"].array.prefix(5).enumerated()), id: \.offset) { _, item in
                                HStack(spacing: 12) {
                                    Image(systemName: "checkmark.circle")
                                        .foregroundStyle(Palette.forest)
                                        .frame(width: 34, height: 34)
                                        .background(
                                            LinearGradient(colors: [Palette.sage, Palette.sage.opacity(0.5)], startPoint: .topLeading, endPoint: .bottomTrailing),
                                            in: RoundedRectangle(cornerRadius: 10, style: .continuous)
                                        )
                                        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(Color.white.opacity(0.8), lineWidth: 1))
                                    VStack(alignment: .leading, spacing: 5) {
                                        Text(item.text("concept_title", fallback: item.text("title", fallback: "Practice attempt")))
                                            .font(.system(size: 12, weight: .medium))
                                        Text(item.text("mode", fallback: "Practice").capitalized)
                                            .font(.system(size: 10))
                                            .foregroundStyle(Palette.secondary)
                                    }
                                    Spacer()
                                    Text(item["correct"].isNull ? friendlyDate(item["created_at"].string) : (item["correct"].bool ? "Correct" : "Keep exploring"))
                                        .font(.system(size: 10, weight: .medium))
                                        .foregroundStyle(Palette.secondary)
                                }
                            }
                        }
                    }
                }
                VStack(spacing: 16) {
                    Card(color: Palette.peach) {
                        VStack(alignment: .leading, spacing: 13) {
                            HStack {
                                Image(systemName: "arrow.trianglehead.clockwise").font(.system(size: 22, weight: .light))
                                Spacer()
                                Tag(text: "SPACED PRACTICE", color: Palette.accentRose.soft)
                            }
                            Text("Keep the ideas close.")
                                .font(.system(size: 19, weight: .semibold, design: .rounded))
                                .tracking(-0.4)
                            Text("A few thoughtful reviews make yesterday’s learning part of tomorrow.")
                                .font(.system(size: 12))
                                .foregroundStyle(Palette.secondary)
                                .lineSpacing(3)
                            Button { store.navigate(.review) } label: {
                                Label("See daily review", systemImage: "arrow.right")
                            }
                            .buttonStyle(LuminfestButtonStyle(primary: false))
                            .accessibilityIdentifier("review.open")
                        }
                    }
                    Card(padding: 18) {
                        HStack(alignment: .top, spacing: 10) {
                            Image(systemName: "checkmark.shield").foregroundStyle(Palette.forest)
                            VStack(alignment: .leading, spacing: 6) {
                                Text("Honest by design").font(.system(size: 12, weight: .semibold))
                                Text(modelNote).font(.system(size: 10)).foregroundStyle(Palette.secondary).lineSpacing(3)
                            }
                        }
                    }
                }.frame(width: 278)
            }
            PlanCard()
        }
    }
    @ViewBuilder var heroActions: some View {
        if !recommendation["concept_id"].string.isEmpty {
            Button { store.page = .studio; store.run { await store.selectConcept(recommendation["concept_id"].string) } } label: { Label("Open lesson", systemImage: "arrow.right") }.buttonStyle(LuminfestButtonStyle())
        }
        Button { store.run { await store.startQuestion(mode: "diagnostic") } } label: { Label("Start diagnostic", systemImage: "sparkle.magnifyingglass") }.buttonStyle(LuminfestButtonStyle(primary: recommendation["concept_id"].string.isEmpty)).accessibilityIdentifier("diagnostic.start")
    }
    var modelNote: String {
        let model = store.dashboard["model_status"]
        guard !model.isNull else { return "Model status is unavailable until the backend connects. Your progress is never simulated." }
        return "\(model.text("name", fallback: "Learning model")) · \(model.text("domain", fallback: "Domain not specified"))\n\(model["trained"].bool ? "Trained" : "Not trained") · \(model["commercial_ready"].bool ? "Commercial readiness reported by backend" : "Research harness, not a commercial claim")"
    }
}
struct MetricCard: View {
    let title: String
    let value: String
    let detail: String
    let icon: String
    let accent: Accent
    @State private var isHovered = false

    var body: some View {
        Card(padding: 18) {
            VStack(alignment: .leading, spacing: 13) {
                HStack {
                    Image(systemName: icon)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(accent.deep)
                        .frame(width: 32, height: 32)
                        .background(accent.tile, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(Color.white.opacity(0.8), lineWidth: 1))
                        .shadow(color: accent.deep.opacity(isHovered ? 0.32 : 0.08), radius: isHovered ? 6 : 2, x: 0, y: 1)
                    Spacer()
                }
                Text(value)
                    .font(.system(size: 30, weight: .medium, design: .rounded))
                    .tracking(-1)
                VStack(alignment: .leading, spacing: 4) {
                    Text(title)
                        .font(.system(size: 11, weight: .semibold))
                    Text(detail)
                        .font(.system(size: 9))
                        .foregroundStyle(Palette.secondary)
                }
            }
        }
        .spotlight(cornerRadius: 22, tint: accent.deep, intensity: 0.16)
    }
}

// MARK: - Course knowledge graph
//
// The map is the whole course, not a sample. Every layout here is derived from the
// graph itself (strand -> unit -> topic, and prerequisite depth), so the same code
// renders 15 concepts or 1,500 without change.

struct KnowledgeView: View {
    @EnvironmentObject var store: AppStore
    @State private var selected: String?
    @State private var query = ""
    @State private var strandFilter: String?

    private var nodes: [JSON] { store.graphNodes }

    private var matched: [JSON] {
        let needle = query.trimmingCharacters(in: .whitespaces).lowercased()
        guard !needle.isEmpty else { return nodes }
        return nodes.filter { node in
            node["title"].string.lowercased().contains(needle)
                || node["topic"].string.lowercased().contains(needle)
                || node["unit"].string.lowercased().contains(needle)
                || node["strand"].string.lowercased().contains(needle)
                || node["id"].string.lowercased().contains(needle)
        }
    }

    private var visible: [JSON] {
        guard let strand = strandFilter else { return matched }
        return matched.filter { $0["strand"].string == strand }
    }

    private var strands: [String] {
        var seen: [String] = []
        for node in nodes {
            let value = node["strand"].string
            if !value.isEmpty && !seen.contains(value) { seen.append(value) }
        }
        return seen
    }

    private var lessonNodes: [JSON] { nodes.filter { $0["has_lesson"].bool } }

    var body: some View {
        VStack(spacing: 22) {
            header
            if nodes.isEmpty {
                Card { EmptyState(icon: "point.3.connected.trianglepath.dotted",
                                  title: "Waiting for your course graph",
                                  message: "Connect to the learning backend to see the concept network.") }
            } else {
                Card {
                    VStack(alignment: .leading, spacing: 14) {
                        SectionHeading(title: "Course map", detail: "\(visible.count) OF \(nodes.count) CONCEPTS")
                        GraphOverview(nodes: visible, edges: store.graphEdges, selected: $selected)
                            .frame(height: 300)
                        legend
                    }
                }
                HStack(alignment: .top, spacing: 18) {
                    UnitBrowser(nodes: visible, selected: $selected, nodeToLesson: store.nodeToLesson)
                    ConceptInspector(selected: selected, store: store)
                }
                if !lessonNodes.isEmpty { authoredLessons }
            }
            if !store.curriculum["sources"].array.isEmpty { sources }
        }
    }

    private var header: some View {
        Card(color: Palette.accentTeal.soft) {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Understanding is connected.").font(.system(size: 21, weight: .semibold))
                        Text("Every concept is placed by strand, unit and prerequisite depth. Select one to see what it rests on and what it unlocks.")
                            .foregroundStyle(Palette.secondary).font(.system(size: 12))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer()
                    Tag(text: "\(store.graphStats["concepts"].int) CONCEPTS", color: Palette.accentTeal.soft)
                }
                HStack(spacing: 10) {
                    Image(systemName: "magnifyingglass").font(.system(size: 12)).foregroundStyle(Palette.secondary)
                    TextField("Search concepts, units or strands", text: $query)
                        .textFieldStyle(.plain).font(.system(size: 13))
                        .accessibilityIdentifier("graph.search")
                    if !query.isEmpty {
                        Button { query = "" } label: { Image(systemName: "xmark.circle.fill") }
                            .buttonStyle(.plain).foregroundStyle(Palette.secondary)
                    }
                }
                .padding(.horizontal, 12).padding(.vertical, 9)
                .background(Color.white.opacity(0.75), in: RoundedRectangle(cornerRadius: 11))

                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        strandChip(nil, label: "All strands")
                        ForEach(strands, id: \.self) { strand in strandChip(strand, label: strand) }
                    }
                }

                HStack(spacing: 20) {
                    statPill("\(store.graphStats["units"].int)", "units")
                    statPill("\(store.graphStats["edges"].int)", "prerequisites")
                    statPill("\(store.graphStats["max_depth"].int)", "longest chain")
                    statPill("\(store.graphStats["with_lesson"].int)", "authored lessons")
                    Spacer()
                }
            }
        }
    }

    private func strandChip(_ value: String?, label: String) -> some View {
        // Every strand keeps a stable hue, so the filter row reads as a spectrum.
        let tint = value == nil ? Palette.accentSage.deep : Palette.accent(for: label).deep
        return ModeChip(title: label, isSelected: strandFilter == value, tint: tint) {
            strandFilter = value
        }
    }

    private func statPill(_ value: String, _ label: String) -> some View {
        HStack(spacing: 6) {
            Text(value).font(.system(size: 15, weight: .semibold))
            Text(label).font(.system(size: 10)).foregroundStyle(Palette.secondary)
        }
    }

    private var legend: some View {
        HStack(spacing: 16) {
            Label("Prerequisite", systemImage: "arrow.right")
            Label("Teaching order", systemImage: "arrow.turn.down.right")
            Label("Mastery from evidence", systemImage: "circle.hexagongrid")
            Spacer()
            Text("Depth is the longest prerequisite chain reaching a concept.")
        }
        .font(.system(size: 10)).foregroundStyle(Palette.secondary)
    }

    private var authoredLessons: some View {
        VStack(alignment: .leading, spacing: 14) {
            SectionHeading(title: "Authored lessons", detail: "\(lessonNodes.count) READY TO STUDY")
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 255), spacing: 18)], spacing: 18) {
                ForEach(lessonNodes, id: \.self) { node in
                    Card(color: selected == node["id"].string ? Palette.sage : .white, padding: 20) {
                        VStack(alignment: .leading, spacing: 13) {
                            HStack {
                                Eyebrow(text: node["unit"].string.uppercased())
                                Spacer()
                                Tag(text: percent(node["mastery"]), color: Palette.lavender)
                            }
                            Text(node["title"].string).font(.system(size: 17, weight: .semibold))
                            Text(node["summary"].string).font(.system(size: 12))
                                .foregroundStyle(Palette.secondary).lineLimit(3)
                                .frame(minHeight: 46, alignment: .top)
                            HStack {
                                Text("Recall: " + percent(node["recall"]))
                                Spacer()
                                Text(node["due_at"].isNull ? "No review scheduled" : friendlyDate(node["due_at"].string))
                            }.font(.system(size: 10)).foregroundStyle(Palette.secondary)
                            Button {
                                store.page = .studio
                                store.run { await store.selectConcept(node["lesson_id"].string) }
                            } label: { Label("Explore lesson", systemImage: "arrow.right") }
                                .buttonStyle(LuminfestButtonStyle(primary: false))
                        }
                    }
                    .onTapGesture { selected = node["id"].string }
                }
            }
        }
    }

    private var sources: some View {
        Card(padding: 18) {
            VStack(alignment: .leading, spacing: 10) {
                Eyebrow(text: "CURRICULUM SOURCES")
                ForEach(Array(store.curriculum["sources"].array.enumerated()), id: \.offset) { _, source in
                    HStack {
                        SourceLink(title: source["title"].string, url: source["url"].string)
                        Spacer()
                        Text(source["license"].string).font(.system(size: 10)).foregroundStyle(Palette.secondary)
                    }
                }
            }
        }
    }
}

/// A whole-course overview. Horizontal axis is prerequisite depth, vertical axis is
/// unit, so prerequisites always flow left to right and units stay legible in rows.
struct GraphOverview: View {
    let nodes: [JSON]
    let edges: [JSON]
    @Binding var selected: String?
    @State private var hoveredNode: String? = nil

    private var units: [String] {
        var seen: [String] = []
        for node in nodes {
            let unit = node["unit"].string
            if !unit.isEmpty && !seen.contains(unit) { seen.append(unit) }
        }
        return seen
    }

    var body: some View {
        GeometryReader { geo in
            let maxDepth = max(1, nodes.map { $0["depth"].int }.max() ?? 1)
            let rows = max(1, units.count)
            let columnWidth = geo.size.width / CGFloat(maxDepth + 1)
            let rowHeight = geo.size.height / CGFloat(rows)
            let index = Dictionary(uniqueKeysWithValues: units.enumerated().map { ($1, $0) })
            let place: (JSON) -> CGPoint = { node in
                let column = CGFloat(min(max(node["depth"].int, 0), maxDepth))
                let row = CGFloat(index[node["unit"].string] ?? 0)
                return CGPoint(x: columnWidth * (column + 0.5), y: rowHeight * (row + 0.5))
            }
            let byID = Dictionary(uniqueKeysWithValues: nodes.map { ($0["id"].string, $0) })
            let activeID = hoveredNode ?? selected

            ZStack {
                // Background OpenAI interactive constellation dots
                OpenAIDotsCanvas(
                    spacing: 28,
                    baseRadius: 1.2,
                    maxRadius: 3.8,
                    influenceRadius: 100,
                    primaryColor: Palette.forest,
                    glowColor: Palette.peachDeep
                )
                .opacity(0.3)

                Canvas { context, _ in
                    for edge in edges {
                        guard let from = byID[edge["from"].string], let to = byID[edge["to"].string] else { continue }
                        let isSequence = edge["kind"].string == "sequence"
                        let isHighlighted = activeID != nil && (edge["from"].string == activeID || edge["to"].string == activeID)

                        var path = Path()
                        path.move(to: place(from))
                        path.addCurve(to: place(to),
                                      control1: CGPoint(x: place(from).x + 30, y: place(from).y),
                                      control2: CGPoint(x: place(to).x - 30, y: place(to).y))

                        if isHighlighted {
                            context.stroke(
                                path,
                                with: .color(isSequence ? Palette.peachDeep : Palette.forest),
                                style: StrokeStyle(lineWidth: 2.2, dash: isSequence ? [4, 4] : [])
                            )
                        } else {
                            context.stroke(
                                path,
                                with: .color(Palette.forest.opacity(isSequence ? 0.08 : 0.18)),
                                style: StrokeStyle(lineWidth: isSequence ? 1 : 1.3, dash: isSequence ? [3, 4] : [])
                            )
                        }
                    }
                }

                ForEach(nodes, id: \.self) { node in
                    let isHovered = hoveredNode == node["id"].string
                    let isSelected = selected == node["id"].string
                    Button {
                        selected = node["id"].string
                    } label: {
                        ZStack {
                            if isHovered || isSelected {
                                Circle()
                                    .fill(masteryColor(node["mastery"]).opacity(0.25))
                                    .frame(width: isSelected ? 26 : 20, height: isSelected ? 26 : 20)
                            }
                            Circle()
                                .fill(masteryColor(node["mastery"]))
                                .frame(width: isSelected ? 16 : (isHovered ? 13 : 10),
                                       height: isSelected ? 16 : (isHovered ? 13 : 10))
                                .overlay(Circle().strokeBorder(Color.white, lineWidth: isSelected ? 2 : 1.5))
                                .shadow(color: masteryColor(node["mastery"]).opacity(isHovered ? 0.6 : 0.2), radius: isHovered ? 5 : 2)
                        }
                    }
                    .buttonStyle(.plain)
                    .position(place(node))
                    .accessibilityLabel(node["title"].string + ", mastery " + percent(node["mastery"]))
                    .onHover { hovering in
                        withAnimation(.spring(response: 0.25, dampingFraction: 0.75)) {
                            hoveredNode = hovering ? node["id"].string : nil
                        }
                    }
                }

                if let id = activeID, let node = byID[id] {
                    VStack {
                        HStack {
                            Spacer()
                            HStack(spacing: 8) {
                                Circle().fill(masteryColor(node["mastery"])).frame(width: 8, height: 8)
                                Text(node["title"].string).font(.system(size: 11, weight: .semibold))
                                Text("·").foregroundStyle(Palette.secondary)
                                Text(node["unit"].string).font(.system(size: 10)).foregroundStyle(Palette.secondary)
                                Tag(text: percent(node["mastery"]), color: Palette.lavender)
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .background(Color.white.opacity(0.92), in: Capsule())
                            .overlay(Capsule().stroke(Palette.line, lineWidth: 1))
                            .shadow(color: Palette.ink.opacity(0.06), radius: 8, x: 0, y: 2)
                            .padding(10)
                        }
                        Spacer()
                    }
                }
            }
        }
    }
}

/// Unit-by-unit browser. Lazy so it stays smooth at any graph size.
struct UnitBrowser: View {
    let nodes: [JSON]
    @Binding var selected: String?
    let nodeToLesson: [String: String]

    private var grouped: [(unit: String, strand: String, nodes: [JSON])] {
        var order: [String] = []
        var buckets: [String: [JSON]] = [:]
        var strands: [String: String] = [:]
        for node in nodes {
            let unit = node["unit"].string
            if buckets[unit] == nil { order.append(unit); strands[unit] = node["strand"].string }
            buckets[unit, default: []].append(node)
        }
        return order.map { (unit: $0, strand: strands[$0] ?? "", nodes: buckets[$0] ?? []) }
    }

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: 16) {
                SectionHeading(title: "Units", detail: "\(grouped.count) IN COURSE ORDER")
                if grouped.isEmpty {
                    EmptyState(icon: "magnifyingglass", title: "Nothing matches", message: "Try a different search term or strand.")
                } else {
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 16) {
                            ForEach(grouped, id: \.unit) { group in
                                VStack(alignment: .leading, spacing: 9) {
                                    HStack(spacing: 8) {
                                        Eyebrow(text: group.strand.uppercased())
                                        Spacer()
                                        Text("\(group.nodes.count)").font(.system(size: 10))
                                            .foregroundStyle(Palette.secondary)
                                    }
                                    Text(group.unit).font(.system(size: 15, weight: .semibold))
                                    ForEach(group.nodes, id: \.self) { node in
                                        conceptRow(node)
                                    }
                                }
                                Divider().overlay(Palette.line)
                            }
                        }
                        .padding(.trailing, 4)
                    }
                    .frame(maxHeight: 460)
                }
            }
        }
        .frame(maxWidth: .infinity)
    }

    private func conceptRow(_ node: JSON) -> some View {
        let isSelected = selected == node["id"].string
        return Button { selected = node["id"].string } label: {
            HStack(spacing: 10) {
                Circle().fill(masteryColor(node["mastery"])).frame(width: 8, height: 8)
                VStack(alignment: .leading, spacing: 2) {
                    Text(node["title"].string).font(.system(size: 12, weight: .medium))
                        .foregroundStyle(Palette.ink).multilineTextAlignment(.leading)
                    if !node["topic"].string.isEmpty {
                        Text(node["topic"].string).font(.system(size: 9)).foregroundStyle(Palette.secondary)
                    }
                }
                Spacer()
                if node["has_lesson"].bool {
                    Image(systemName: "book.closed.fill").font(.system(size: 9)).foregroundStyle(Palette.forest)
                }
                difficultyDots(node["difficulty"].int)
            }
            .padding(.horizontal, 10).padding(.vertical, 7)
            .background(isSelected ? Palette.sage : Color.white.opacity(0.6), in: RoundedRectangle(cornerRadius: 10))
            .contentShape(RoundedRectangle(cornerRadius: 10))
        }
        .buttonStyle(.plain)
    }

    private func difficultyDots(_ value: Int) -> some View {
        HStack(spacing: 2) {
            ForEach(1...5, id: \.self) { step in
                Circle()
                    .fill(step <= value ? Palette.forest.opacity(0.7) : Palette.line)
                    .frame(width: 4, height: 4)
            }
        }
    }
}

/// Details for the selected concept: where it sits, what it needs, what it unlocks.
struct ConceptInspector: View {
    let selected: String?
    @ObservedObject var store: AppStore
    @State private var showFigure = false

    private var node: JSON { guard let id = selected else { return .null }; return store.graphNode(id) }

    var body: some View {
        Card {
            if node.isNull {
                EmptyState(icon: "cursorarrow.rays", title: "Select a concept",
                           message: "Pick any node in the map or the unit list to inspect its place in the course.")
            } else {
                VStack(alignment: .leading, spacing: 14) {
                    Eyebrow(text: node["strand"].string.uppercased())
                    Text(node["title"].string).font(.system(size: 18, weight: .semibold))
                        .fixedSize(horizontal: false, vertical: true)
                    if !node["summary"].string.isEmpty {
                        Text(node["summary"].string).font(.system(size: 12))
                            .foregroundStyle(Palette.secondary).lineSpacing(3)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    HStack(spacing: 8) {
                        Tag(text: node["tier"].string.uppercased(), color: Palette.lavender)
                        Tag(text: "DIFFICULTY \(node["difficulty"].int)/5", color: Palette.peach)
                    }
                    Divider().overlay(Palette.line)
                    detailRow("Unit", node["unit"].string)
                    detailRow("Topic", node["topic"].string)
                    detailRow("Depth", "\(node["depth"].int)")
                    detailRow("Mastery", percent(node["mastery"]))
                    detailRow("Attempts", "\(node["attempts"].int)")
                    if !node["prerequisites"].array.isEmpty { idList("Rests on", node["prerequisites"].array) }
                    if !node["dependants"].array.isEmpty { idList("Unlocks", node["dependants"].array) }
                    if !node["lesson_id"].string.isEmpty {
                        Button {
                            store.page = .studio
                            store.run { await store.selectConcept(node["lesson_id"].string) }
                        } label: { Label("Open the lesson", systemImage: "arrow.right") }
                            .buttonStyle(LuminfestButtonStyle())
                            .accessibilityIdentifier("graph.openLesson")
                    } else {
                        Text("No lesson has been authored for this concept yet. It still counts towards prerequisite reasoning and coverage.")
                            .font(.system(size: 10)).foregroundStyle(Palette.secondary).lineSpacing(3)
                    }
                    figureSection
                }
            }
        }
        .frame(width: 330)
        .onChange(of: selected) { _, _ in showFigure = false }
    }

    /// Every concept in the course graph has a figure, not only the authored lessons,
    /// because the figure is generated from the concept's own classification. It is
    /// fetched only when opened, so browsing the map does not issue 164 requests.
    @ViewBuilder private var figureSection: some View {
        Divider().overlay(Palette.line)
        Button {
            withAnimation(.easeInOut(duration: 0.18)) { showFigure.toggle() }
        } label: {
            HStack(spacing: 6) {
                Image(systemName: showFigure ? "chevron.down" : "chevron.right").font(.system(size: 9, weight: .bold))
                Text(showFigure ? "Hide the live figure" : "See the idea move").font(.system(size: 11, weight: .semibold))
                Spacer()
                if !node["simulation_kind"].string.isEmpty {
                    Tag(text: node["simulation_kind"].string.uppercased().replacingOccurrences(of: "_", with: " "),
                        color: Palette.sage)
                }
            }
        }
        .buttonStyle(.plain)
        .foregroundStyle(Palette.forest)
        .accessibilityIdentifier("graph.toggleFigure")

        if showFigure, let id = selected {
            SimulationLab(conceptID: id, store: store, compact: true)
                .transition(.opacity.combined(with: .move(edge: .top)))
        }
    }

    private func detailRow(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Text(label).font(.system(size: 10)).foregroundStyle(Palette.secondary).frame(width: 62, alignment: .leading)
            Text(value.isEmpty ? "—" : value).font(.system(size: 11, weight: .medium))
                .fixedSize(horizontal: false, vertical: true)
            Spacer()
        }
    }

    private func idList(_ label: String, _ ids: [JSON]) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(label).font(.system(size: 10)).foregroundStyle(Palette.secondary)
            ForEach(ids, id: \.self) { id in
                Button { } label: {
                    Text("• " + store.graphTitle(id.string)).font(.system(size: 11))
                        .multilineTextAlignment(.leading)
                }.buttonStyle(.plain)
            }
        }
    }
}

func masteryColor(_ value: JSON) -> Color {
    guard !value.isNull else { return Palette.muted }
    let level = value.double
    if level >= 0.8 { return Palette.forest }
    if level >= 0.5 { return Palette.sage }
    if level > 0 { return Palette.peach }
    return Palette.muted
}

struct ReviewView: View {
    @EnvironmentObject var store: AppStore
    var body: some View {
        VStack(spacing: 20) {
            Card(color: Palette.accentPlum.soft) {
                HStack {
                    VStack(alignment: .leading, spacing: 10) { Eyebrow(text: "A MOMENT TO REMEMBER", tint: Palette.accentPlum.deep.opacity(0.9)); Text("\(store.reviews["total"].int) ideas ready for a revisit.").font(.system(size: 25, weight: .semibold)).tracking(-0.8); Text("Retrieval first. Explanation after. Let your memory do the work.").font(.system(size: 12)).foregroundStyle(Palette.secondary) }
                    Spacer()
                    Button { store.run { await store.startQuestion(mode: "review") } } label: { Label("Start review", systemImage: "arrow.right") }.buttonStyle(LuminfestButtonStyle()).disabled(store.reviews["items"].array.isEmpty).accessibilityIdentifier("review.start")
                }
            }
            Card {
                VStack(spacing: 18) {
                    SectionHeading(title: "Your review queue", detail: "SCHEDULED BY THE BACKEND")
                    if store.reviews["items"].array.isEmpty { EmptyState(icon: "checkmark.circle", title: "A little breathing room", message: "No ideas are due right now. Explore a lesson or practice something new.") }
                    ForEach(Array(store.reviews["items"].array.enumerated()), id: \.offset) { _, item in
                        HStack(spacing: 16) {
                            Image(systemName: "book.closed").font(.system(size: 18)).foregroundStyle(Palette.forest).frame(width: 44, height: 44).background(Palette.sage, in: RoundedRectangle(cornerRadius: 12))
                            VStack(alignment: .leading, spacing: 6) { Text(item["title"].string).font(.system(size: 14, weight: .medium)); Text("Due " + friendlyDate(item["due_at"].string)).font(.system(size: 11)).foregroundStyle(Palette.secondary) }
                            Spacer(); Tag(text: "Recall " + percent(item["recall"]), color: Palette.lavender)
                            Button("Review") { store.run { await store.startQuestion(mode: "review", concept: item["concept_id"].string) } }.buttonStyle(LuminfestButtonStyle(primary: false))
                        }.padding(.vertical, 8)
                        Divider().overlay(Palette.line)
                    }
                }
            }
        }
    }
}
