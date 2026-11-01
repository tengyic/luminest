import AppKit
import SwiftUI

/// The reward surface: one event at a time, at the weight of ceremony the backend asked for.
///
/// Three tiers, and the difference between them is the point:
///
/// * ``toast`` - a card in the bottom corner. A day counted, a focus stretch. It must not
///   stop the lesson, so it takes no clicks and leaves on its own.
/// * ``banner`` - centred, a soft scale-in, a sparkle. Praise that is worth looking at once.
/// * ``celebrate`` - a scrim, Lumi centre stage, confetti, and a Continue button. Reserved
///   for the moments the rules call milestones; using it for anything smaller is how a
///   celebration becomes wallpaper.
///
/// Nothing here decides whether something deserves celebrating. That is `rewards.py` and
/// `motivation.py`; this file only knows how to show what it was handed.
struct RewardOverlay: View {
    @ObservedObject var center: RewardCenter
    @StateObject private var lumi = LumiCompanion()
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        Group {
            if let event = center.current {
                layer(event)
                    .transition(.opacity)
                    .task(id: event.id) { await run(event) }
            }
        }
        .animation(.easeInOut(duration: 0.22), value: center.current?.id)
    }

    // MARK: Tiers

    @ViewBuilder
    private func layer(_ event: RewardEvent) -> some View {
        switch event.tier {
        case "celebrate": celebrate(event)
        case "banner": banner(event)
        default: toast(event)
        }
    }

    private func toast(_ event: RewardEvent) -> some View {
        ZStack(alignment: .bottomTrailing) {
            Color.clear
            HStack(spacing: 12) {
                sprite(event, height: 34)
                VStack(alignment: .leading, spacing: 2) {
                    Text(event.title)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(Palette.ink)
                    if !event.announce.isEmpty, event.announce != event.title {
                        Text(event.announce)
                            .font(.system(size: 11))
                            .foregroundStyle(Palette.secondary)
                    }
                }
                Button("OK") { close() }
                    .buttonStyle(.plain)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Palette.forest)
            }
            .padding(14)
            .background(Palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(Palette.line, lineWidth: 1))
            .shadow(color: Palette.ink.opacity(0.10), radius: 18, x: 0, y: 8)
            .padding(24)
            .transition(.move(edge: .trailing).combined(with: .opacity))
            .accessibilityElement(children: .combine)
            .accessibilityLabel("\(event.title). \(event.announce)")
        }
    }

    private func banner(_ event: RewardEvent) -> some View {
        ZStack {
            Color.black.opacity(0.10).ignoresSafeArea().allowsHitTesting(false)
            VStack(spacing: 10) {
                sprite(event, height: 62)
                Text(event.title)
                    .font(.system(size: 18, weight: .semibold, design: .rounded))
                    .foregroundStyle(Palette.ink)
                Text(event.announce)
                    .font(.system(size: 12))
                    .foregroundStyle(Palette.secondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 30)
            .padding(.vertical, 24)
            .frame(maxWidth: 360)
            .background(Palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous)
                .strokeBorder(Palette.borderHighlight, lineWidth: 1))
            .shadow(color: Palette.ink.opacity(0.18), radius: 30, x: 0, y: 14)
            .transition(.scale(scale: 0.94).combined(with: .opacity))
            .accessibilityElement(children: .combine)
            .accessibilityLabel("\(event.title). \(event.announce)")
            .onTapGesture { close() }
        }
    }

    private func celebrate(_ event: RewardEvent) -> some View {
        ZStack {
            Color.black.opacity(0.28).ignoresSafeArea()
            if !reduceMotion {
                CelebrationParticles(seed: 7).ignoresSafeArea()
            }
            VStack(spacing: 14) {
                sprite(event, height: 120)
                Text(event.title)
                    .font(.system(size: 26, weight: .semibold, design: .rounded))
                    .tracking(-0.6)
                    .foregroundStyle(Palette.ink)
                Text(event.announce)
                    .font(.system(size: 13))
                    .foregroundStyle(Palette.secondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                Button("Continue") { close() }
                    .buttonStyle(.plain)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Color.white)
                    .padding(.horizontal, 24)
                    .padding(.vertical, 10)
                    .background(Palette.forest, in: Capsule())
                    .padding(.top, 6)
            }
            .padding(36)
            .frame(maxWidth: 420)
            .background(Palette.surface, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous)
                .strokeBorder(Palette.borderHighlight, lineWidth: 1))
            .shadow(color: Palette.ink.opacity(0.24), radius: 44, x: 0, y: 20)
            .transition(.scale(scale: 0.92).combined(with: .opacity))
            .accessibilityElement(children: .contain)
            .accessibilityLabel("\(event.title). \(event.announce)")
        }
    }

    private func sprite(_ event: RewardEvent, height: CGFloat) -> some View {
        LumiSpriteView(sprite: LumiSprite(rawValue: event.mascot) ?? .greeting, height: height,
                       rise: lumi.rise, squash: lumi.squash, tilt: lumi.tilt)
    }

    // MARK: Behaviour

    /// Sound, gesture, announcement, then dismissal.
    ///
    /// The timer is per tier and generous on purpose: a toast that vanishes in 1.5 s has not
    /// been read, and a celebration that vanishes before it is understood has not been a
    /// reward. ``celebrate`` also has a Continue button, so the timer is a backstop against
    /// a card that sticks rather than the primary way out.
    private func run(_ event: RewardEvent) async {
        SoundBank.shared.play(event.sound)
        lumi.celebrate(tier: event.tier, line: event.announce)
        announce(event.announce)
        let seconds: Double
        switch event.tier {
        case "celebrate": seconds = 9.0
        case "banner": seconds = 3.5
        default: seconds = 2.5
        }
        try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
        guard !Task.isCancelled else { return }
        close()
    }

    private func close() {
        lumi.settle()
        center.dismiss()
    }

    /// Speak the line to VoiceOver. The card itself is one combined element, but a
    /// celebration appears without the learner having moved focus, so the announcement is
    /// what actually tells a screen-reader user that something happened.
    private func announce(_ line: String) {
        guard !line.isEmpty else { return }
        NSAccessibility.post(element: NSApp as Any, notification: .announcementRequested,
                             userInfo: [.announcement: line,
                                        .priority: NSAccessibilityPriorityLevel.high.rawValue])
    }
}

// MARK: - Confetti

/// A seeded particle field. Seeded, not random: the same event always produces the same
/// arrangement, so a screenshot regression is comparable and the effect is reproducible.
struct CelebrationParticles: View {
    var seed: UInt64 = 7
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var start = Date()

    private struct Particle {
        var x: Double
        var delay: Double
        var speed: Double
        var sway: Double
        var size: Double
        var phase: Double
        var tint: Int
    }

    private let particles: [Particle]
    private static let tints: [Color] = [Palette.sage, Palette.peach, Palette.lavender, Palette.ochreSoft]

    init(seed: UInt64 = 7) {
        self.seed = seed
        var generator = SeededGenerator(seed: seed)
        particles = (0..<54).map { _ in
            Particle(x: generator.unit(),
                     delay: generator.unit() * 0.9,
                     speed: 0.55 + generator.unit() * 0.8,
                     sway: (generator.unit() - 0.5) * 0.06,
                     size: 4 + generator.unit() * 6,
                     phase: generator.unit() * 6.28,
                     tint: Int(generator.unit() * Double(Self.tints.count)) % Self.tints.count)
        }
    }

    var body: some View {
        if reduceMotion {
            EmptyView()
        } else {
            TimelineView(.animation) { timeline in
                Canvas { context, size in
                    let elapsed = timeline.date.timeIntervalSince(start)
                    for particle in particles {
                        let age = elapsed - particle.delay
                        guard age > 0 else { continue }
                        let fall = (age * particle.speed).truncatingRemainder(dividingBy: 2.4) / 2.4
                        let x = particle.x * size.width + sin(age * 2 + particle.phase) * particle.sway * size.width
                        let y = -20 + fall * (size.height + 40)
                        let rect = CGRect(x: x, y: y, width: particle.size, height: particle.size * 0.62)
                        let tint = Self.tints[particle.tint]
                        context.fill(Path(ellipseIn: rect), with: .color(tint.opacity(0.9 * (1 - fall))))
                    }
                }
            }
            .allowsHitTesting(false)
            .accessibilityHidden(true)
        }
    }
}

/// A tiny reproducible generator. `Double.random` would make every celebration different,
/// which sounds harmless until a screenshot test can never be compared to the last one.
struct SeededGenerator: RandomNumberGenerator {
    private var state: UInt64

    init(seed: UInt64) {
        state = seed &* 6_364_136_223_846_793_005 &+ 1
    }

    mutating func next() -> UInt64 {
        state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
        return state
    }

    /// Uniform in [0, 1).
    mutating func unit() -> Double {
        Double(next() >> 11) / Double(1 << 53)
    }
}
