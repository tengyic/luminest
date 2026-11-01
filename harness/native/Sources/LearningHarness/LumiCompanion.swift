import SwiftUI
import AppKit

// MARK: - Sprites
//
// Seven matted PNGs ship in `Resources/Lumi`. Six of them are *moods*; `blink` is a
// transient frame layered over a mood, which is why it is a sprite and not a mood — a
// blink is not a state the companion is in, it is something that happens to it.

enum LumiMood: String, CaseIterable, Equatable {
    case idle, greeting, listening, thinking, celebrating, resting
}

enum LumiSprite: String, CaseIterable, Equatable {
    case idle, blink, greeting, listening, thinking, celebrating, resting

    init(mood: LumiMood) { self = LumiSprite(rawValue: mood.rawValue) ?? .idle }
}

@MainActor
enum LumiArt {
    /// The matte leaves the figure at 60% of the square canvas, so a view that wants a
    /// 44pt character has to render a 73pt image. Keeping the constant here stops every
    /// call site from re-deriving that arithmetic (and getting it wrong by eye).
    static let fill: CGFloat = 0.60

    private static var cache: [LumiSprite: NSImage] = [:]

    static func image(_ sprite: LumiSprite) -> NSImage? {
        if let hit = cache[sprite] { return hit }
        guard let url = AppResources.url(for: "lumi-\(sprite.rawValue)", withExtension: "png"),
              let image = NSImage(contentsOf: url) else { return nil }
        cache[sprite] = image
        return image
    }

    /// True when every sprite resolves. Used by the test suite so a renamed PNG fails a
    /// test instead of silently rendering a sage dot in the sidebar.
    static var isComplete: Bool { LumiSprite.allCases.allSatisfy { image($0) != nil } }
}

// MARK: - Choreography
//
// A script is data, not code, so the timing can be asserted in a unit test and tuned
// without touching the view. Every script describes only the *distinctive* part of a
// move; the controller always returns to the current mood afterwards, which is what
// keeps a one-shot action from becoming a permanent expression.

struct LumiStep: Equatable {
    var sprite: LumiSprite
    /// Seconds to hold. Zero means "set this and move on".
    var hold: Double
    /// Points upward. Negative dips.
    var rise: CGFloat = 0
    /// Vertical scale. Below 1 crouches, above 1 stretches; x is inverted to preserve volume.
    var squash: CGFloat = 1
    /// Degrees, anchored at the feet so a tilt reads as a lean rather than a spin.
    var tilt: Double = 0
}

enum LumiAction: Equatable, CaseIterable {
    case blink, hop, nod, greet, celebrate, cheer, sparkle

    var steps: [LumiStep] {
        switch self {
        case .blink:
            return [LumiStep(sprite: .blink, hold: 0.11)]
        case .hop:
            return [
                LumiStep(sprite: .idle, hold: 0.06, squash: 0.93),
                LumiStep(sprite: .idle, hold: 0.10, rise: 5, squash: 1.05),
                LumiStep(sprite: .idle, hold: 0.07, squash: 0.98)
            ]
        case .nod:
            return [
                LumiStep(sprite: .idle, hold: 0.09, rise: -1.5, tilt: 1.6),
                LumiStep(sprite: .idle, hold: 0.07, tilt: 0)
            ]
        case .greet:
            // Two beats of the same frame, with the body settling, reads as a wave
            // rather than a pose held for a second.
            return [
                LumiStep(sprite: .greeting, hold: 0.50, rise: 3, squash: 1.02, tilt: -2),
                LumiStep(sprite: .greeting, hold: 0.30, tilt: 1)
            ]
        case .celebrate:
            return [
                LumiStep(sprite: .celebrating, hold: 0.26, rise: 6, squash: 1.05),
                LumiStep(sprite: .celebrating, hold: 0.20, squash: 0.98)
            ]
        case .cheer:
            // The heavier celebration: a crouch that loads the hop, the hop, then a
            // settle. Three beats rather than two, so it reads as a jump rather than a
            // bounce - and it still lands inside `testDeformationStaysSubtle`.
            return [
                LumiStep(sprite: .celebrating, hold: 0.14, rise: -1, squash: 0.92),
                LumiStep(sprite: .celebrating, hold: 0.22, rise: 7, squash: 1.06),
                LumiStep(sprite: .celebrating, hold: 0.18, rise: 1, squash: 0.99)
            ]
        case .sparkle:
            // A quick nod with a lean: the gesture for praise that is not a milestone.
            // Cheap on purpose - a toast every day must not cost the ceremony of a streak.
            return [
                LumiStep(sprite: .greeting, hold: 0.12, rise: -1, tilt: -2),
                LumiStep(sprite: .greeting, hold: 0.10, tilt: 2),
                LumiStep(sprite: .greeting, hold: 0.10)
            ]
        }
    }
}

// MARK: - Companion

/// The behaviour layer for Lumi: what she is doing, what she says, and what she does
/// when nothing is happening.
///
/// Everything runs on the main actor and every mutation is wrapped in `withAnimation`,
/// so the view stays a pure renderer and there is one place to reason about timing.
@MainActor
final class LumiCompanion: ObservableObject {
    @Published private(set) var sprite: LumiSprite = .idle
    @Published private(set) var rise: CGFloat = 0
    @Published private(set) var squash: CGFloat = 1
    @Published private(set) var tilt: Double = 0
    @Published private(set) var speech: String?
    @Published private(set) var mood: LumiMood = .idle

    /// A script is running. Mood changes are deferred until it finishes so a status
    /// update cannot cut a wave in half.
    private var isScripted = false
    private var script: Task<Void, Never>?
    private var breath: Task<Void, Never>?
    private var blink: Task<Void, Never>?
    private var speechTimer: Task<Void, Never>?
    /// Guards the cleanup of a cancelled script: without it, cancelling script A to start
    /// B lets A's tail clear `isScripted` while B is still running.
    private var generation = 0

    init(animated: Bool = true) {
        guard animated else { return }
        startBreathing()
        startBlinking()
    }

    // MARK: Mood

    func setMood(_ next: LumiMood) {
        guard mood != next else { return }
        mood = next
        guard !isScripted else { return }
        withAnimation(.easeInOut(duration: 0.18)) { apply(LumiSprite(mood: next)) }
    }

    // MARK: One-shot moves

    func play(_ action: LumiAction) {
        generation += 1
        let token = generation
        script?.cancel()
        isScripted = true

        script = Task { @MainActor [weak self] in
            for step in action.steps {
                guard let self, !Task.isCancelled else { break }
                withAnimation(.easeInOut(duration: 0.11)) {
                    self.apply(step.sprite, rise: step.rise, squash: step.squash, tilt: step.tilt)
                }
                if step.hold > 0 {
                    try? await Task.sleep(nanoseconds: UInt64(step.hold * 1_000_000_000))
                }
            }
            guard let self, self.generation == token else { return }
            self.isScripted = false
            guard !Task.isCancelled else { return }
            withAnimation(.easeInOut(duration: 0.20)) { self.apply(LumiSprite(mood: self.mood)) }
        }
    }

    // MARK: Speech

    func say(_ line: String, seconds: Double = 4.2) {
        speech = line
        speechTimer?.cancel()
        speechTimer = Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
            guard let self, !Task.isCancelled else { return }
            withAnimation(.easeOut(duration: 0.18)) { self.speech = nil }
        }
    }

    func greet(_ line: String) {
        say(line, seconds: 5.0)
        play(.greet)
    }

    // MARK: Rewards

    /// React to a reward event: the heavier tier gets `.cheer`, everything lighter `.sparkle`.
    ///
    /// ``tier`` is the server's own word (``toast`` / ``banner`` / ``celebrate``) and is not
    /// re-derived from the number here. The backend decides what an achievement is worth;
    /// a client that re-scored it would be the second place the thresholds live, and the
    /// first place they would drift apart.
    func celebrate(tier: String, line: String) {
        let big = tier == "celebrate"
        setMood(.celebrating)
        play(big ? .cheer : .sparkle)
        guard !line.isEmpty else { return }
        say(line, seconds: big ? 5.5 : 3.6)
    }

    /// Return to the resting face once a celebration is dismissed.
    ///
    /// A mood is persistent by design, so something has to end it - and the overlay is the
    /// only thing that knows when the moment is over. Without this the companion keeps the
    /// `celebrating` sprite for the rest of the session.
    func settle() { setMood(.idle) }

    // MARK: Idle life
    //
    // Breathing and blinking are what make a still image read as a creature. They are
    // driven from here rather than from a repeating SwiftUI animation so that a script
    // can interrupt them cleanly — a `repeatForever` modifier cannot be paused.

    private func startBreathing() {
        breath?.cancel()
        breath = Task { @MainActor [weak self] in
            var lifted = false
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 2_300_000_000)
                guard let self, !Task.isCancelled else { return }
                guard !self.isScripted, self.mood != .resting else { continue }
                lifted.toggle()
                withAnimation(.easeInOut(duration: 1.15)) { self.rise = lifted ? 1.4 : 0 }
            }
        }
    }

    private func startBlinking() {
        blink?.cancel()
        blink = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: UInt64(Double.random(in: 2.4...6.4) * 1_000_000_000))
                guard let self, !Task.isCancelled else { return }
                // Closed eyes are already the resting face; blinking it would look like a twitch.
                guard !self.isScripted, self.mood != .resting, self.sprite != .blink else { continue }
                self.blinkOnce()
            }
        }
    }

    private func blinkOnce() {
        let previous = sprite
        withAnimation(.easeOut(duration: 0.05)) { sprite = .blink }
        Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: 105_000_000)
            guard let self, self.sprite == .blink, !self.isScripted else { return }
            withAnimation(.easeIn(duration: 0.09)) { self.sprite = previous }
        }
    }

    private func apply(_ next: LumiSprite, rise: CGFloat = 0, squash: CGFloat = 1, tilt: Double = 0) {
        sprite = next
        self.rise = rise
        self.squash = squash
        self.tilt = tilt
    }

    // MARK: Lines
    //
    // Calm, second person, no streak language — the brand voice in 01_BRAND_TRAITS.md §A4.

    static let affirmations = [
        "Take the time you need.",
        "One idea at a time.",
        "We can stop whenever you like.",
        "Nothing is due right now."
    ]

    static func greeting(at date: Date = Date()) -> String {
        switch Calendar.current.component(.hour, from: date) {
        case 5..<12: return "Morning. Shall we start with one idea?"
        case 12..<18: return "Afternoon. Ready when you are."
        default: return "Evening. Twenty minutes, that's all."
        }
    }
}

// MARK: - Views

/// Pure renderer: it draws whatever the companion says to draw, and animates nothing
/// itself. `rise`, `squash` and `tilt` are already animated by the controller.
struct LumiSpriteView: View {
    var sprite: LumiSprite
    /// Height of the *character*, not of the image canvas.
    var height: CGFloat
    var rise: CGFloat = 0
    var squash: CGFloat = 1
    var tilt: Double = 0
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var canvas: CGFloat { height / LumiArt.fill }
    private var motion: Bool { !reduceMotion }

    var body: some View {
        Group {
            if let image = LumiArt.image(sprite) {
                Image(nsImage: image)
                    .resizable()
                    .interpolation(.high)
                    .scaledToFit()
            } else {
                // A missing resource must not collapse the layout it sits in.
                Circle().fill(Palette.sage)
            }
        }
        .frame(width: canvas, height: canvas)
        .scaleEffect(x: motion ? 1 / max(squash, 0.6) : 1, y: motion ? squash : 1, anchor: .bottom)
        .rotationEffect(.degrees(motion ? tilt : 0), anchor: .bottom)
        .offset(y: motion ? -rise : 0)
        .accessibilityHidden(true)
    }
}

/// Sprite plus optional speech bubble. Tapping Lumi gets a hop and a quiet line — the
/// smallest possible acknowledgement that she is a character and not a status light.
struct LumiCompanionView: View {
    @ObservedObject var lumi: LumiCompanion
    var height: CGFloat = 46
    var showsSpeech: Bool = true
    var onTap: (() -> Void)?

    var body: some View {
        VStack(spacing: 9) {
            if showsSpeech, let line = lumi.speech {
                Text(line)
                    .font(.system(size: 11))
                    .foregroundStyle(Palette.secondary)
                    .lineSpacing(3)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 11)
                    .padding(.vertical, 8)
                    .background(Palette.surface, in: RoundedRectangle(cornerRadius: 11, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 11, style: .continuous)
                            .strokeBorder(Palette.line, lineWidth: 1)
                    )
                    .shadow(color: Palette.ink.opacity(0.05), radius: 5, x: 0, y: 2)
                    .transition(.opacity.combined(with: .scale(scale: 0.96, anchor: .bottom)))
                    .accessibilityLabel("Lumi says: \(line)")
            }

            LumiSpriteView(sprite: lumi.sprite, height: height, rise: lumi.rise, squash: lumi.squash, tilt: lumi.tilt)
                .contentShape(Rectangle())
                .onTapGesture {
                    if let onTap { onTap() } else { lumi.play(.hop); lumi.say(LumiCompanion.affirmations.randomElement() ?? "", seconds: 2.6) }
                }
                .accessibilityLabel("Lumi, your study companion")
                .accessibilityAddTraits(.isButton)
        }
    }
}

// MARK: - Placements

/// The sidebar companion. She greets once when the shell appears, thinks while the app
/// is waiting on the server, and marks a completed action — never a streak, because
/// there is no streak to mark.
struct LumiSidebarSlot: View {
    @EnvironmentObject var store: AppStore
    @StateObject private var lumi = LumiCompanion()
    @State private var greeted = false

    var body: some View {
        LumiCompanionView(lumi: lumi, height: 54)
            .frame(maxWidth: .infinity)
            .padding(.horizontal, 14)
            .onAppear {
                guard !greeted else { return }
                greeted = true
                lumi.greet(LumiCompanion.greeting())
            }
            .onChange(of: store.busy) { _, busy in
                lumi.setMood(busy ? .thinking : .idle)
            }
            .onChange(of: store.notice) { _, notice in
                guard notice != nil else { return }
                lumi.play(.celebrate)
                lumi.say("That's saved.", seconds: 2.8)
            }
            // The silent half of the teacher: nobody asked a question, and the harness
            // decided there was something worth saying. Shown in her bubble rather than the
            // chat, because a supervision line is not part of the lesson transcript and must
            // not look like an answer.
            .onChange(of: store.supervisionNotice) { _, line in
                guard let line, !line.isEmpty else { return }
                lumi.say(line, seconds: 9)
            }
    }
}

/// First-run guide. She is attentive while the learner answers, and visibly thinking on
/// the last step, where the app is about to do arithmetic on their behalf.
struct LumiSetupGuide: View {
    @ObservedObject var lumi: LumiCompanion
    var step: Int

    var body: some View {
        LumiSpriteView(sprite: lumi.sprite, height: 30, rise: lumi.rise, squash: lumi.squash, tilt: lumi.tilt)
            .frame(width: 56, height: 56)
            .background(Palette.sage.opacity(0.55), in: RoundedRectangle(cornerRadius: 13, style: .continuous))
            .accessibilityHidden(true)
            .onChange(of: step) { _, next in
                lumi.setMood(next == 2 ? .thinking : .listening)
            }
    }
}
