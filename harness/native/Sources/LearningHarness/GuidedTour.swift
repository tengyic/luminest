import SwiftUI
import AppKit

/// A first-run walkthrough: it dims the window, cuts a hole around one control at a time,
/// points at it, and says what the control is for.
///
/// Why this is not part of `OnboardingView`: that view is registration and course setup —
/// it asks the learner for something. This asks nothing. It exists because the eight
/// destinations in the sidebar are named in the learner's language but their *purpose* is
/// not obvious from a label ("Studio" could be anything), and a learner who cannot tell
/// where to start uses one screen and leaves.
///
/// Anchors are collected as preferences rather than computed from a fixed layout. A
/// hardcoded rectangle is wrong the moment the sidebar collapses at 1,120 points, the text
/// size changes, or the window is resized — and being wrong about *where* to click is worse
/// than not pointing at all.

struct TourStep: Identifiable, Equatable {
    /// Also the anchor id: `nav.<Page case>`, matching the existing accessibility
    /// identifiers so the two cannot drift apart.
    let id: String
    let titleKey: String
    let bodyKey: String
}

enum GuidedTour {
    /// The coordinate space anchors are measured in. Named so the measurement and the
    /// overlay agree even though several views sit between them.
    static let space = "guidedTourSpace"

    static let steps: [TourStep] = [
        TourStep(id: "nav.today",
                 titleKey: "tour.today.title",
                 bodyKey: "tour.today.body"),
        TourStep(id: "nav.studio",
                 titleKey: "tour.studio.title",
                 bodyKey: "tour.studio.body"),
        TourStep(id: "nav.review",
                 titleKey: "tour.review.title",
                 bodyKey: "tour.review.body"),
        TourStep(id: "nav.settings",
                 titleKey: "tour.settings.title",
                 bodyKey: "tour.settings.body"),
    ]

    /// Posted by the menu item. A tour that cannot be replayed is a tour that helps exactly
    /// once, at the moment the learner is least able to take it in.
    static let replayNotification = Notification.Name("luminest.guidedTour.replay")

    static func postReplay() {
        NotificationCenter.default.post(name: replayNotification, object: nil)
    }
}

/// Frame of every anchored control, in ``GuidedTour/space``.
struct TourAnchorKey: PreferenceKey {
    static var defaultValue: [String: CGRect] = [:]

    static func reduce(value: inout [String: CGRect], nextValue: () -> [String: CGRect]) {
        value.merge(nextValue()) { _, new in new }
    }
}

extension View {
    /// Publishes this view's frame so the tour can point at it.
    ///
    /// `Color.clear` in a background does not affect layout and does not intercept clicks —
    /// the tour must never make a control harder to press than it was before the tour.
    func tourAnchor(_ id: String) -> some View {
        background(
            GeometryReader { proxy in
                Color.clear.preference(
                    key: TourAnchorKey.self,
                    value: [id: proxy.frame(in: .named(GuidedTour.space))]
                )
            }
        )
    }
}

/// Hosts the tour above whatever it wraps.
///
/// It reads `luminfest.tourSeen` rather than a store property so the answer survives a
/// crash mid-tour: a learner who quits during step 2 has still seen enough to be spared it
/// next launch, and `Skip` means skip.
struct TourHost<Content: View>: View {
    @ViewBuilder var content: Content

    @AppStorage("luminfest.tourSeen") private var seen = false
    @State private var active = false

    var body: some View {
        content
            .coordinateSpace(name: GuidedTour.space)
            .overlayPreferenceValue(TourAnchorKey.self) { anchors in
                if active {
                    GuidedTourOverlay(anchors: anchors) {
                        active = false
                        seen = true
                    }
                }
            }
            .onAppear(perform: beginIfFirstRun)
            .onReceive(NotificationCenter.default.publisher(for: GuidedTour.replayNotification)) { _ in
                active = true
            }
    }

    private func beginIfFirstRun() {
        guard !seen else { return }
        // The native QA driver addresses controls by identifier and measures frames; an
        // overlay that dims the window would make every one of its screenshots a picture of
        // the tour instead of the screen under test.
        guard !ProcessInfo.processInfo.arguments.contains("--ui-test") else { return }
        // Let the shell lay out and the anchors publish before measuring. One frame is not
        // enough on a cold first launch.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) {
            guard !seen else { return }
            active = true
        }
    }
}

struct GuidedTourOverlay: View {
    let anchors: [String: CGRect]
    var onFinish: () -> Void

    @State private var index = 0
    @State private var pulse = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var steps: [TourStep] { GuidedTour.steps }
    private var step: TourStep? { steps.indices.contains(index) ? steps[index] : nil }
    private var target: CGRect? { step.flatMap { anchors[$0.id] } }
    private var isLast: Bool { index >= steps.count - 1 }

    var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .topLeading) {
                scrim(size: proxy.size)
                if let rect = target {
                    highlight(rect)
                    pointer(rect)
                }
                callout(in: proxy.size)
            }
        }
        .ignoresSafeArea()
        .onExitCommand(perform: onFinish)
        .accessibilityIdentifier("tour.overlay")
    }

    // MARK: - Dimming

    /// A dim layer with a real hole, not a border. Cutting the hole matters: a learner who
    /// is told "click here" needs to see the control at its normal brightness, otherwise the
    /// instruction points at something they cannot read.
    private func scrim(size: CGSize) -> some View {
        Color.black.opacity(target == nil ? 0.38 : 0.46)
            .mask {
                ZStack {
                    Rectangle().fill(Color.black)
                    if let rect = target {
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .frame(width: rect.width + 14, height: rect.height + 14)
                            .position(x: rect.midX, y: rect.midY)
                            .blendMode(.destinationOut)
                    }
                }
                .compositingGroup()
            }
            .frame(width: size.width, height: size.height)
            .contentShape(Rectangle())
            // Swallowing clicks is the point: the tour is a modal explanation, and a click
            // that silently navigates away mid-sentence reads as the app misbehaving.
            .onTapGesture {}
    }

    private func highlight(_ rect: CGRect) -> some View {
        RoundedRectangle(cornerRadius: 14, style: .continuous)
            .strokeBorder(Palette.forest.opacity(pulse ? 0.95 : 0.6), lineWidth: 2)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(Palette.sage.opacity(pulse ? 0.16 : 0.06))
            )
            .frame(width: rect.width + 14, height: rect.height + 14)
            .position(x: rect.midX, y: rect.midY)
            .allowsHitTesting(false)
            .onAppear {
                guard let animation = LuminfestMotion.ambient(reduceMotion: reduceMotion, duration: 1.6) else {
                    pulse = true
                    return
                }
                withAnimation(animation) { pulse = true }
            }
    }

    /// A drawn pointer, not the system cursor. Moving the real cursor is the one thing an
    /// app should never do: it takes the pointer away from whatever the person was doing and
    /// it cannot be undone when the tour is dismissed.
    private func pointer(_ rect: CGRect) -> some View {
        Image(systemName: "cursorarrow")
            .font(.system(size: 22, weight: .semibold))
            .foregroundStyle(Palette.ink)
            .shadow(color: .black.opacity(0.28), radius: 3, y: 1)
            .rotationEffect(.degrees(-8))
            .position(x: rect.minX + 10, y: rect.minY + 8)
            .allowsHitTesting(false)
            .accessibilityHidden(true)
    }

    // MARK: - Explanation

    private func callout(in size: CGSize) -> some View {
        let width: CGFloat = 340
        let placement = calloutOrigin(width: width, in: size)

        return VStack(alignment: .leading, spacing: 11) {
            HStack(spacing: 8) {
                Text(step.map { _ in
                    L10n.tf("tour.counter", table: nil, index + 1, steps.count)
                } ?? "")
                    .font(Typography.eyebrow)
                    .tracking(1.4)
                    .foregroundStyle(Palette.secondary)
                Spacer(minLength: 0)
                Button(L10n.t("tour.skip"), action: onFinish)
                    .buttonStyle(.plain)
                    .font(Typography.caption)
                    .foregroundStyle(Palette.secondary)
                    .accessibilityIdentifier("tour.skip")
            }

            if let step {
                Text(L10n.t(step.titleKey))
                    .font(Typography.title)
                    .foregroundStyle(Palette.ink)
                    .fixedSize(horizontal: false, vertical: true)
                Text(L10n.t(step.bodyKey))
                    .font(Typography.callout)
                    .foregroundStyle(Palette.secondary)
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)
            }

            HStack {
                Spacer()
                Button(isLast ? L10n.t("tour.done") : L10n.t("tour.next"), action: advance)
                    .buttonStyle(LuminfestButtonStyle())
                    .keyboardShortcut(.defaultAction)
                    .accessibilityIdentifier("tour.next")
            }
        }
        .padding(18)
        .frame(width: width, alignment: .leading)
        .background(Palette.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(Palette.line, lineWidth: 1)
        )
        .shadow(color: Palette.ink.opacity(0.18), radius: 22, y: 8)
        .position(x: placement.x + width / 2, y: placement.y)
        .accessibilityElement(children: .contain)
        .accessibilityAddTraits(.isModal)
        .accessibilityLabel(step.map { L10n.t($0.titleKey) } ?? "")
        .accessibilityIdentifier("tour.callout")
    }

    /// Places the card beside the control when there is room, and in the middle when the
    /// anchor is missing or the window is too narrow. A card pinned off-screen is the same
    /// as no tour at all.
    private func calloutOrigin(width: CGFloat, in size: CGSize) -> CGPoint {
        guard let rect = target else { return CGPoint(x: (size.width - width) / 2, y: size.height * 0.42) }
        let margin: CGFloat = 18
        let cardHeight: CGFloat = 190
        var x = rect.maxX + 26
        if x + width > size.width - margin { x = max(margin, rect.minX - width - 26) }
        let y = min(max(margin + cardHeight / 2, rect.midY), size.height - margin - cardHeight / 2)
        return CGPoint(x: x, y: y)
    }

    private func advance() {
        if isLast { onFinish() } else {
            index += 1
            pulse = false
        }
    }
}
