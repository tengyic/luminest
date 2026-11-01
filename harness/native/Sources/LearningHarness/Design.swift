import SwiftUI
import AppKit

extension Color {
    init(hex: UInt32) { self.init(.sRGB, red: Double((hex >> 16) & 255) / 255, green: Double((hex >> 8) & 255) / 255, blue: Double(hex & 255) / 255, opacity: 1) }
}

/// A Morandi accent pair: a soft surface tint used for fills and a deep ink tone used
/// for icons, borders and emphasis. Keeping the two paired is what stops the interface
/// sliding back to a single hue.
struct Accent: Equatable {
    let soft: Color
    let deep: Color

    /// A gentle two-stop fill for icon tiles and chips.
    var tile: LinearGradient {
        LinearGradient(colors: [soft, soft.opacity(0.62)], startPoint: .topLeading, endPoint: .bottomTrailing)
    }
}

enum Palette {
    // Morandi warm base tones (inspired by 2019.makemepulse.com & Apple/Google aesthetics)
    // 2026-10-11 brightness pass: base surfaces lifted, text anchors darkened, and every
    // soft fill raised one full step in chroma so cards read as colour, not fog.
    static let background = Color(hex: 0xFBFAF6)
    static let surface = Color(hex: 0xFFFFFF)
    static let surfaceSubtle = Color(hex: 0xF5F3EC)
    static let ink = Color(hex: 0x24312A)
    static let secondary = Color(hex: 0x5C6A60)
    static let tertiary = Color(hex: 0x8D9A90)

    // Morandi earthy botanical palette
    static let sage = Color(hex: 0xC4E6C9)
    static let forest = Color(hex: 0x3E7A55)
    static let deepForest = Color(hex: 0x2C5C3E)
    static let softForest = Color(hex: 0x58936B)
    static let eucalyptus = Color(hex: 0xA9D8B0)

    // Morandi ethereal accents
    static let lavender = Color(hex: 0xD8CFF2)
    static let lavenderDeep = Color(hex: 0x655CA8)
    static let peach = Color(hex: 0xFFDFC4)
    static let peachDeep = Color(hex: 0xC46A3E)
    static let terracotta = Color(hex: 0xD96F4F)
    static let sky = Color(hex: 0xBFDDF5)
    static let slate = Color(hex: 0x3E6172)
    static let oat = Color(hex: 0xF6EFDD)

    // Extended Morandi hues — dusty, low-chroma companions to the green core so the
    // interface is not monochrome. Each is a soft surface tint plus a deep ink tone.
    // Brightness pass: soft tints up ~1 chroma step, deeps kept dark enough for AA text.
    static let mossSoft = Color(hex: 0xD9E4B8)
    static let mossDeep = Color(hex: 0x5A702E)
    static let tealSoft = Color(hex: 0xBCE3DC)
    static let tealDeep = Color(hex: 0x2F6E68)
    static let indigoSoft = Color(hex: 0xCCD2F0)
    static let indigoDeep = Color(hex: 0x47519C)
    static let plumSoft = Color(hex: 0xE0C7EA)
    static let plumDeep = Color(hex: 0x7A3E8C)
    static let roseSoft = Color(hex: 0xF5C9D4)
    static let roseDeep = Color(hex: 0xA64E68)
    static let ochreSoft = Color(hex: 0xF7DFA8)
    static let ochreDeep = Color(hex: 0x8F6A1F)
    static let claySoft = Color(hex: 0xFBD0B4)
    static let clayDeep = Color(hex: 0xB35C2E)

    // Structure & Dividers
    static let line = Color(hex: 0xDFE2D6)
    static let muted = Color(hex: 0xECEDDF)
    static let borderHighlight = Color.white.opacity(0.85)

    // Semantic gradients
    static let heroGradient = LinearGradient(
        colors: [Palette.sage.opacity(0.95), Palette.sky.opacity(0.85), Palette.lavender.opacity(0.75)],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )
    static let forestGradient = LinearGradient(
        colors: [Palette.forest, Palette.softForest],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )
    static let auraGlow = RadialGradient(
        colors: [Palette.sage.opacity(0.45), Palette.lavender.opacity(0.3), Color.clear],
        center: .center,
        startRadius: 20,
        endRadius: 180
    )

    // MARK: - Accent registry
    //
    // Ordered so neighbouring UI elements read as deliberately different hues. The
    // green core stays the brand anchor; everything else gives the app range.
    static let accentSage = Accent(soft: sage, deep: forest)
    static let accentTeal = Accent(soft: tealSoft, deep: tealDeep)
    static let accentIndigo = Accent(soft: indigoSoft, deep: indigoDeep)
    static let accentClay = Accent(soft: claySoft, deep: clayDeep)
    static let accentPlum = Accent(soft: plumSoft, deep: plumDeep)
    static let accentOchre = Accent(soft: ochreSoft, deep: ochreDeep)
    static let accentSky = Accent(soft: sky, deep: slate)
    static let accentRose = Accent(soft: roseSoft, deep: roseDeep)
    static let accentMoss = Accent(soft: mossSoft, deep: mossDeep)
    static let accentLavender = Accent(soft: lavender, deep: lavenderDeep)

    static let accents: [Accent] = [
        accentSage, accentTeal, accentIndigo, accentClay,
        accentPlum, accentOchre, accentSky, accentRose, accentMoss
    ]

    /// Rotation accessor — stable, never out of range.
    static func accent(at index: Int) -> Accent {
        guard !accents.isEmpty else { return accentSage }
        let count = accents.count
        return accents[((index % count) + count) % count]
    }

    /// Stable per-identifier accent, so a given page, strand or concept keeps its colour.
    static func accent(for key: String) -> Accent {
        guard !accents.isEmpty else { return accentSage }
        var hash = 5381
        for byte in key.utf8 { hash = ((hash << 5) &+ hash) &+ Int(byte) }
        let count = accents.count
        return accents[((hash % count) + count) % count]
    }
}

struct LuminfestButtonStyle: ButtonStyle {
    var primary = true
    var compact = false
    func makeBody(configuration: Configuration) -> some View {
        LuminfestButtonBody(configuration: configuration, primary: primary, compact: compact)
    }
}

private struct LuminfestButtonBody: View {
    let configuration: ButtonStyle.Configuration
    let primary: Bool
    let compact: Bool
    @State private var isHovered = false

    var body: some View {
        configuration.label
            .font(.system(size: compact ? 11 : 13, weight: .semibold))
            .padding(.horizontal, compact ? 14 : 19)
            .padding(.vertical, compact ? 8 : 12)
            .foregroundStyle(primary ? Color.white : Palette.ink)
            .background {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(primary
                        ? AnyShapeStyle(LinearGradient(
                            colors: isHovered
                                ? [Palette.forest, Palette.softForest]
                                : [Palette.deepForest, Palette.forest],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ))
                        : AnyShapeStyle(Color.white.opacity(isHovered ? 0.95 : 0.82))
                    )
            }
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .strokeBorder(
                        primary
                            ? (isHovered ? Color.white.opacity(0.32) : Color.clear)
                            : (isHovered ? Palette.forest.opacity(0.35) : Palette.line),
                        lineWidth: 1
                    )
            )
            .shadow(
                color: primary
                    ? Palette.forest.opacity(isHovered ? 0.32 : 0.12)
                    : Palette.ink.opacity(isHovered ? 0.08 : 0.02),
                radius: isHovered ? 8 : 3,
                x: 0,
                y: isHovered ? 3 : 1
            )
            .scaleEffect(configuration.isPressed ? 0.96 : (isHovered ? 1.015 : 1.0))
            .opacity(configuration.isPressed ? 0.85 : 1)
            .contentShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .onHover { hovering in
                withAnimation(.spring(response: 0.26, dampingFraction: 0.74)) {
                    isHovered = hovering
                }
            }
    }
}

struct Card<Content: View>: View {
    var color: Color = .white
    var padding: CGFloat = 24
    var interactive: Bool = true
    @ViewBuilder var content: Content
    @State private var isHovered = false

    var body: some View {
        content
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .fill(color.opacity(0.95))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .strokeBorder(
                        LinearGradient(
                            colors: [
                                Color.white.opacity(isHovered ? 0.95 : 0.8),
                                isHovered ? Palette.forest.opacity(0.22) : Color.white.opacity(0.3)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ),
                        lineWidth: isHovered ? 1.2 : 1
                    )
            )
            .shadow(
                color: Palette.ink.opacity(isHovered ? 0.08 : 0.03),
                radius: isHovered ? 14 : 7,
                x: 0,
                y: isHovered ? 5 : 2
            )
            .scaleEffect(interactive && isHovered ? 1.006 : 1.0)
            .offset(y: interactive && isHovered ? -1.5 : 0)
            .onHover { hovering in
                guard interactive else { return }
                withAnimation(.spring(response: 0.32, dampingFraction: 0.78)) {
                    isHovered = hovering
                }
            }
    }
}

struct Eyebrow: View {
    let text: String
    var tint: Color = Palette.secondary
    var body: some View {
        Text(text)
            .font(.system(size: 10, weight: .semibold, design: .rounded))
            .tracking(2.2)
            .foregroundStyle(tint)
    }
}

struct SectionHeading: View {
    let title: String
    var detail = ""
    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title)
                .font(.system(size: 19, weight: .semibold, design: .rounded))
                .tracking(-0.3)
            Spacer()
            if !detail.isEmpty {
                Text(detail)
                    .font(.system(size: 11, weight: .medium))
                    .tracking(1.2)
                    .foregroundStyle(Palette.secondary)
            }
        }
    }
}

struct Tag: View {
    let text: String
    var color: Color = Palette.sage
    @State private var isHovered = false

    var body: some View {
        Text(text)
            .font(.system(size: 10, weight: .semibold))
            .padding(.horizontal, 11)
            .padding(.vertical, 5)
            .background(color.opacity(isHovered ? 0.95 : 0.85), in: Capsule())
            .overlay(Capsule().strokeBorder(Color.white.opacity(0.6), lineWidth: 0.8))
            .shadow(color: color.opacity(isHovered ? 0.3 : 0.08), radius: isHovered ? 4 : 1, x: 0, y: 1)
            .scaleEffect(isHovered ? 1.03 : 1.0)
            .onHover { hovering in
                withAnimation(.spring(response: 0.25, dampingFraction: 0.7)) {
                    isHovered = hovering
                }
            }
    }
}

struct EmptyState: View {
    let icon: String
    let title: String
    let message: String
    @State private var floating = false

    var body: some View {
        VStack(spacing: 14) {
            Group {
                if let art = LuminfestArt.image(deterministicFrom: title) {
                    ArtImage(image: art)
                        .frame(height: 132)
                        .padding(.horizontal, 6)
                } else {
                    ZStack {
                        Circle()
                            .fill(Palette.sage.opacity(0.35))
                            .frame(width: 80, height: 80)
                            .scaleEffect(floating ? 1.06 : 0.96)
                        Image(systemName: icon)
                            .font(.system(size: 30, weight: .light))
                            .foregroundStyle(Palette.forest)
                            .frame(width: 65, height: 65)
                            .background(Color.white.opacity(0.9), in: RoundedRectangle(cornerRadius: 21, style: .continuous))
                            .shadow(color: Palette.ink.opacity(0.05), radius: 8, x: 0, y: 3)
                    }
                }
            }
            .offset(y: floating ? -3 : 2)
            .onAppear {
                withAnimation(.easeInOut(duration: 2.8).repeatForever(autoreverses: true)) {
                    floating = true
                }
            }

            Text(title)
                .font(.system(size: 17, weight: .semibold, design: .rounded))
            Text(message)
                .font(.system(size: 13))
                .foregroundStyle(Palette.secondary)
                .multilineTextAlignment(.center)
                .lineSpacing(3)
                .frame(maxWidth: 390)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 34)
    }
}

struct SourceLink: View {
    let title: String
    let url: String
    @State private var isHovered = false

    var body: some View {
        if let value = URL(string: url), ["https", "http"].contains(value.scheme ?? "") {
            Link(destination: value) {
                HStack(spacing: 5) {
                    Text(title)
                        .font(.system(size: 11, weight: .medium))
                    Image(systemName: "arrow.up.right")
                        .font(.system(size: 9, weight: .bold))
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(isHovered ? Palette.sage.opacity(0.5) : Color.clear, in: Capsule())
            }
            .foregroundStyle(Palette.forest)
            .onHover { hovering in
                withAnimation(.easeInOut(duration: 0.18)) {
                    isHovered = hovering
                }
            }
        }
    }
}

// MARK: - Bundled Illustration Assets
//
// Five bright botanical-geometric artworks ship inside the app bundle
// (Sources/LearningHarness/Resources/Images) and are surfaced in empty states and the
// narrated deck so screens never sit as bare text on pale surfaces.

enum LuminfestArt {
    static let names = ["hero-constellation", "growth-seedling", "math-shapes", "reading-desk", "ocean-shore"]

    static func image(_ name: String) -> NSImage? {
        guard let url = AppResources.url(for: name, withExtension: "png") else { return nil }
        return NSImage(contentsOf: url)
    }

    /// Stable pick: the same title always renders the same artwork.
    static func image(deterministicFrom seed: String) -> NSImage? {
        var hash = 5381
        for byte in seed.utf8 { hash = ((hash << 5) &+ hash) &+ Int(byte) }
        return image(names[((hash % names.count) + names.count) % names.count])
    }

    static func name(at index: Int) -> String {
        names[((index % names.count) + names.count) % names.count]
    }
}

/// Aspect-fill artwork with the app's rounded-corner + hairline treatment.
struct ArtImage: View {
    let image: NSImage
    var cornerRadius: CGFloat = 20

    var body: some View {
        GeometryReader { geo in
            Image(nsImage: image)
                .resizable()
                .scaledToFill()
                .frame(width: geo.size.width, height: geo.size.height)
                .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                        .strokeBorder(Color.white.opacity(0.75), lineWidth: 1)
                )
                .shadow(color: Palette.ink.opacity(0.06), radius: 7, x: 0, y: 2)
        }
    }
}

func percent(_ value: JSON) -> String {
    guard !value.isNull else { return "—" }
    let n = value.double
    guard n.isFinite, abs(n) <= 1_000_000 else { return "—" }
    return "\(Int((n <= 1 ? n * 100 : n).rounded()))%"
}

func friendlyDate(_ text: String) -> String {
    let formatter = ISO8601DateFormatter()
    if let date = formatter.date(from: text) { return date.formatted(date: .abbreviated, time: .omitted) }
    return text.isEmpty ? "Not scheduled" : String(text.prefix(10))
}

// MARK: - OpenAI-inspired Interactive Dot Matrix Canvas
/// An interactive dot grid inspired by OpenAI's web animations and 2018.makemepulse.com.
/// Dots breathe in an organic wave and react fluidly to continuous cursor hover,
/// dynamically scaling, glowing with Morandi hues, and connecting with faint constellation lines.
struct OpenAIDotsCanvas: View {
    var spacing: CGFloat = 24
    var baseRadius: CGFloat = 1.8
    var maxRadius: CGFloat = 5.0
    var influenceRadius: CGFloat = 125
    var primaryColor: Color = Palette.forest
    var glowColor: Color = Palette.peachDeep

    @State private var hoverLocation: CGPoint? = nil
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        // Adaptive frame rate: the ambient wave only needs a gentle cadence while idle,
        // and ramps to full smoothness only while the pointer is actually interacting.
        // This keeps the CPU cost of the decorative canvas negligible when untouched.
        TimelineView(.animation(minimumInterval: (hoverLocation == nil || reduceMotion) ? 1.0 / 12.0 : 1.0 / 60.0)) { timeline in
            Canvas { context, size in
                let time = reduceMotion ? 0 : timeline.date.timeIntervalSinceReferenceDate
                let cols = Int(ceil(size.width / spacing)) + 1
                let rows = Int(ceil(size.height / spacing)) + 1

                var activePoints: [(point: CGPoint, weight: Double)] = []

                for r in 0..<rows {
                    for c in 0..<cols {
                        let originX = CGFloat(c) * spacing
                        let originY = CGFloat(r) * spacing

                        // Ambient organic breathing wave (2018/OpenAI wave style)
                        let wave = sin(time * 1.4 + Double(originX) * 0.035 + Double(originY) * 0.035) * 2.0
                        var posX = originX
                        var posY = originY + CGFloat(wave)

                        var radius = baseRadius
                        var dotColor = Palette.secondary.opacity(0.28)
                        var excitation: Double = 0

                        if let hover = hoverLocation {
                            let dx = posX - hover.x
                            let dy = posY - hover.y
                            let dist = sqrt(dx * dx + dy * dy)
                            if dist < influenceRadius {
                                let norm = 1.0 - Double(dist / influenceRadius)
                                excitation = norm * norm * (3.0 - 2.0 * norm) // smoothstep

                                // Gentle spring repulsion from cursor
                                let angle = atan2(dy, dx)
                                let push = CGFloat(excitation * 7.0)
                                posX += cos(angle) * push
                                posY += sin(angle) * push

                                radius = baseRadius + CGFloat(excitation) * (maxRadius - baseRadius)

                                // Gradient glow from sage forest to warm Morandi peach
                                let blendColor = excitation > 0.5 ? glowColor : primaryColor
                                dotColor = blendColor.opacity(0.45 + excitation * 0.5)

                                activePoints.append((CGPoint(x: posX, y: posY), excitation))
                            }
                        }

                        let rect = CGRect(x: posX - radius, y: posY - radius, width: radius * 2, height: radius * 2)
                        context.fill(Path(ellipseIn: rect), with: .color(dotColor))
                    }
                }

                // Draw constellation connection threads between neighboring excited dots
                if activePoints.count > 1 {
                    for i in 0..<activePoints.count {
                        for j in (i + 1)..<min(activePoints.count, i + 8) {
                            let p1 = activePoints[i].point
                            let p2 = activePoints[j].point
                            let dX = p1.x - p2.x
                            let dY = p1.y - p2.y
                            let dist = sqrt(dX * dX + dY * dY)
                            if dist < spacing * 1.8 {
                                let strength = (activePoints[i].weight + activePoints[j].weight) * 0.5
                                var linePath = Path()
                                linePath.move(to: p1)
                                linePath.addLine(to: p2)
                                context.stroke(
                                    linePath,
                                    with: .color(primaryColor.opacity(strength * 0.35)),
                                    lineWidth: CGFloat(strength * 1.2)
                                )
                            }
                        }
                    }
                }
            }
        }
        .onContinuousHover { phase in
            switch phase {
            case .active(let location):
                hoverLocation = location
            case .ended:
                hoverLocation = nil
            }
        }
        .accessibilityHidden(true)
    }
}

// MARK: - Google Labs Fluid Mesh Aura
/// Soft-blurred animated Morandi gradient orbs inspired by Google Labs and Google DeepMind visuals.
struct GoogleLabMeshAura: View {
    @State private var phase: Double = 0
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        // A slow-drifting mesh does not need a high frame rate; 24 fps keeps the
        // large-radius blur cheap while staying visually fluid. Reduce Motion freezes it.
        TimelineView(.animation(minimumInterval: reduceMotion ? 1.0 / 6.0 : 1.0 / 24.0)) { timeline in
            let t = reduceMotion ? 0 : timeline.date.timeIntervalSinceReferenceDate * 0.4
            GeometryReader { geo in
                let w = geo.size.width
                let h = geo.size.height
                ZStack {
                    // Orb 1: Sage
                    Circle()
                        .fill(Palette.sage.opacity(0.7))
                        .frame(width: w * 0.65, height: w * 0.65)
                        .position(
                            x: w * 0.35 + cos(t) * w * 0.12,
                            y: h * 0.35 + sin(t * 0.8) * h * 0.12
                        )

                    // Orb 2: Lavender
                    Circle()
                        .fill(Palette.lavender.opacity(0.65))
                        .frame(width: w * 0.55, height: w * 0.55)
                        .position(
                            x: w * 0.7 + sin(t * 1.1) * w * 0.14,
                            y: h * 0.65 + cos(t * 0.9) * h * 0.12
                        )

                    // Orb 3: Peach
                    Circle()
                        .fill(Palette.peach.opacity(0.6))
                        .frame(width: w * 0.5, height: w * 0.5)
                        .position(
                            x: w * 0.45 + cos(t * 0.7) * w * 0.15,
                            y: h * 0.75 + sin(t * 1.3) * h * 0.1
                        )

                    // Orb 4: Sky Blue
                    Circle()
                        .fill(Palette.sky.opacity(0.55))
                        .frame(width: w * 0.45, height: w * 0.45)
                        .position(
                            x: w * 0.8 + cos(t * 1.2) * w * 0.1,
                            y: h * 0.25 + sin(t * 0.6) * h * 0.12
                        )
                }
                .blur(radius: 34)
            }
        }
        .accessibilityHidden(true)
    }
}

// MARK: - Upgraded OrbitArtwork with Interactive Constellation & Morandi Rings
struct OrbitArtwork: View {
    @State private var hovered = false

    var body: some View {
        ZStack {
            GoogleLabMeshAura()
                .opacity(0.4)

            OpenAIDotsCanvas(
                spacing: 20,
                baseRadius: 1.6,
                maxRadius: 4.8,
                influenceRadius: 100,
                primaryColor: Palette.forest,
                glowColor: Palette.peachDeep
            )
            .opacity(0.7)

            Canvas { context, size in
                let center = CGPoint(x: size.width * 0.51, y: size.height * 0.52)
                for i in 0..<4 {
                    let r = CGFloat(35 + i * 23)
                    let rect = CGRect(x: center.x - r, y: center.y - r * 0.58, width: r * 2, height: r * 1.16)
                    context.stroke(
                        Path(ellipseIn: rect),
                        with: .color(Palette.forest.opacity(0.18)),
                        style: StrokeStyle(lineWidth: 1, dash: [4, 6])
                    )
                }

                let dots: [(CGFloat, CGFloat, CGFloat, Color)] = [
                    (0.49, 0.49, 30, Palette.forest),
                    (0.78, 0.29, 16, Palette.peachDeep),
                    (0.19, 0.65, 22, Palette.lavenderDeep),
                    (0.7, 0.76, 12, Palette.sky)
                ]
                for (x, y, r, c) in dots {
                    let rect = CGRect(x: size.width * x - r, y: size.height * y - r, width: 2 * r, height: 2 * r)
                    context.fill(Path(ellipseIn: rect), with: .color(c.opacity(0.85)))
                    context.stroke(Path(ellipseIn: rect), with: .color(Color.white.opacity(0.9)), lineWidth: 1.5)
                }
                context.draw(
                    Text("✦").font(.system(size: 28, weight: .light)).foregroundColor(.white),
                    at: center
                )
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous).strokeBorder(Color.white.opacity(0.7), lineWidth: 1))
        .accessibilityHidden(true)
    }
}

// MARK: - Cursor-tracking Spotlight (Apple / Vercel / OpenAI-inspired)
/// A soft Morandi radial glow that follows the pointer across a surface, clipped to a
/// rounded rectangle. This recreates the "living surface" highlight seen on Apple and
/// OpenAI marketing pages — pure SwiftUI gradients, no WebGL. When the pointer leaves,
/// the glow settles into a gentle resting position instead of snapping off.
struct SpotlightModifier: ViewModifier {
    var cornerRadius: CGFloat = 22
    var tint: Color = Palette.forest
    var intensity: Double = 0.16
    var radiusFactor: CGFloat = 0.62
    @State private var location: CGPoint? = nil

    func body(content: Content) -> some View {
        content
            .overlay {
                GeometryReader { geo in
                    let w = max(1, geo.size.width)
                    let h = max(1, geo.size.height)
                    let point = location ?? CGPoint(x: w * 0.5, y: h * 0.14)
                    let unit = UnitPoint(
                        x: min(max(point.x / w, 0), 1),
                        y: min(max(point.y / h, 0), 1)
                    )
                    RadialGradient(
                        colors: [
                            tint.opacity(location == nil ? intensity * 0.32 : intensity),
                            tint.opacity(0.0)
                        ],
                        center: unit,
                        startRadius: 0,
                        endRadius: max(w, h) * radiusFactor
                    )
                    .animation(.easeOut(duration: 0.22), value: location)
                }
                .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
                .allowsHitTesting(false)
            }
            .onContinuousHover { phase in
                switch phase {
                case .active(let point): location = point
                case .ended: location = nil
                }
            }
    }
}

extension View {
    /// Adds a cursor-following Morandi spotlight glow to any surface.
    func spotlight(cornerRadius: CGFloat = 22, tint: Color = Palette.forest, intensity: Double = 0.16) -> some View {
        modifier(SpotlightModifier(cornerRadius: cornerRadius, tint: tint, intensity: intensity))
    }
}

// MARK: - Ambient Aura Background
/// A soft, static Morandi aura used behind hero content. Reuses `Palette.auraGlow`
/// so the radial treatment stays consistent across the app.
struct AmbientAura: View {
    var tint: Color? = nil
    var opacity: Double = 0.9

    var body: some View {
        Group {
            if let tint {
                RadialGradient(
                    colors: [tint.opacity(0.4), tint.opacity(0.12), Color.clear],
                    center: .topLeading,
                    startRadius: 12,
                    endRadius: 240
                )
            } else {
                Palette.auraGlow
            }
        }
        .opacity(opacity)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

// MARK: - Gradient Wordmark
/// A subtle top-to-bottom gradient treatment for large titles, echoing the
/// softly-lit typography on Google Lab and Apple product pages.
struct GradientText: View {
    let text: String
    var size: CGFloat = 32
    var weight: Font.Weight = .semibold
    var design: Font.Design = .default
    var from: Color = Palette.deepForest
    var to: Color = Palette.softForest

    var body: some View {
        Text(text)
            .font(.system(size: size, weight: weight, design: design))
            .foregroundStyle(
                LinearGradient(colors: [from, to], startPoint: .top, endPoint: .bottom)
            )
    }
}

// MARK: - Learn Your Way reading components
//
// These are adapted from the "Learn Your Way" immersive-text experience
// (learnyourway.withgoogle.com/scopes/:id/immersive-text/:chunk) — its reading rail,
// segmented progress bar, mode chips and annotation treatments — re-expressed in
// Luminfest's Morandi palette rather than the original coral/indigo.
//
// Reference selectors this mirrors, for traceability:
//   .header-progress-bar / -current / -remaining   -> SegmentedProgressBar
//   .scope-topbar-item (+ per-mode colour coding)  -> ModeChip
//   .card / .margin-note                           -> MarginNote
//   .immersive-text-simple-paginator-button        -> RailIconButton
//   .highlight.active / .selected-with-tooltip     -> KeyHighlight
//   .underline (+ ::before tooltip)                -> PersonalizedExample

/// A hairline rule used for the dotted "personalised example" underline.
private struct DashedUnderline: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.minX, y: rect.midY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.midY))
        return path
    }
}

/// Segmented reading-progress bar (`.header-progress-bar`).
struct SegmentedProgressBar: View {
    var progress: Double
    var tint: Color = Palette.forest
    var track: Color = Palette.muted
    var height: CGFloat = 8

    var body: some View {
        GeometryReader { geo in
            let clamped = max(0, min(1, progress))
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: height / 2, style: .continuous)
                    .fill(track)
                RoundedRectangle(cornerRadius: height / 2, style: .continuous)
                    .fill(tint)
                    .frame(width: geo.size.width * clamped)
            }
        }
        .frame(height: height)
        .animation(.spring(response: 0.4, dampingFraction: 0.85), value: progress)
        .accessibilityElement()
        .accessibilityLabel("Reading progress")
        .accessibilityValue("\(Int(max(0, min(1, progress)) * 100)) percent")
    }
}

/// A pill chip (`.scope-topbar-item`): transparent by default, then a tinted fill plus a
/// tinted border on hover and when selected.
struct ModeChip: View {
    let title: String
    var icon: String? = nil
    var isSelected: Bool = false
    var tint: Color = Palette.forest
    var action: () -> Void = {}
    @State private var isHovered = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 7) {
                if let icon { Image(systemName: icon).font(.system(size: 11, weight: .semibold)) }
                Text(title).font(.system(size: 12, weight: .medium))
            }
            .foregroundStyle(isSelected ? tint : (isHovered ? tint : tint.opacity(0.78)))
            .padding(.horizontal, 14)
            .padding(.vertical, 7)
            .background(
                (isSelected || isHovered) ? tint.opacity(isSelected ? 0.18 : 0.1) : Color.clear,
                in: Capsule()
            )
            .overlay(
                Capsule().strokeBorder(
                    isSelected ? tint.opacity(0.55) : (isHovered ? tint.opacity(0.28) : Color.clear),
                    lineWidth: 1
                )
            )
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            withAnimation(.spring(response: 0.25, dampingFraction: 0.78)) { isHovered = hovering }
        }
    }
}

/// A hairline-bordered helper card for the reading rail (`.card` / `.margin-note`).
struct MarginNote<Content: View>: View {
    var title: String
    var icon: String? = nil
    var tint: Color = Palette.forest
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 7) {
                if let icon {
                    Image(systemName: icon)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(tint)
                }
                Text(title)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Palette.ink)
            }
            content
                .font(.system(size: 12))
                .foregroundStyle(Palette.secondary)
                .lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.92), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(Palette.line, lineWidth: 1)
        )
    }
}

/// A round rail button (`.immersive-text-simple-paginator-button`).
struct RailIconButton: View {
    let icon: String
    var enabled: Bool = true
    var help: String = ""
    let action: () -> Void
    @State private var isHovered = false

    var body: some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(enabled ? (isHovered ? Palette.forest : Palette.secondary) : Palette.tertiary.opacity(0.55))
                .frame(width: 32, height: 32)
                .background(isHovered && enabled ? Palette.sage.opacity(0.5) : Color.clear, in: Circle())
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .help(help)
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.16)) { isHovered = hovering }
        }
    }
}

/// A warm key-phrase highlight with an optional right-margin annotation
/// (`.highlight.active` / `.highlight.selected-with-tooltip`).
struct KeyHighlight: View {
    let text: String
    var annotated: Bool = false
    var tint: Color = Palette.peach
    var annotationTint: Color = Palette.peachDeep

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Text(text)
                .font(.system(size: 13))
                .foregroundStyle(Palette.ink)
                .padding(.horizontal, 5)
                .padding(.vertical, 2)
                .background(tint.opacity(annotated ? 0.95 : 0.6), in: RoundedRectangle(cornerRadius: 4, style: .continuous))
                .fixedSize(horizontal: false, vertical: true)
            if annotated {
                HStack(spacing: 4) {
                    Image(systemName: "bookmark.fill").font(.system(size: 9))
                    Text("Area to review").font(.system(size: 10, weight: .semibold))
                }
                .foregroundStyle(annotationTint)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(tint.opacity(0.9), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                .fixedSize()
            }
        }
    }
}

/// A dotted-underline phrase that reveals a tooltip on hover (`.underline` + tooltip).
struct PersonalizedExample: View {
    let text: String
    let tip: String
    var tint: Color = Palette.lavenderDeep
    @State private var isHovered = false

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(text)
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(tint)
                .padding(.bottom, 4)
                .overlay(alignment: .bottom) {
                    DashedUnderline()
                        .stroke(tint.opacity(0.8), style: StrokeStyle(lineWidth: 1.5, dash: [2, 4]))
                        .frame(height: 2)
                }
            if isHovered {
                Text(tip)
                    .font(.system(size: 11))
                    .foregroundStyle(Palette.ink)
                    .lineSpacing(3)
                    .padding(11)
                    .background(Palette.lavender.opacity(0.9), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .strokeBorder(Palette.lavenderDeep.opacity(0.25), lineWidth: 1)
                    )
                    .fixedSize(horizontal: false, vertical: true)
                    .transition(.opacity.combined(with: .offset(y: -4)))
            }
        }
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.18)) { isHovered = hovering }
        }
    }
}

