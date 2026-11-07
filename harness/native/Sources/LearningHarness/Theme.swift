import SwiftUI
import AppKit

// MARK: - Adaptive colour resolution
//
// The palette used to be thirty-odd fixed sRGB literals. That is why there was no dark
// mode: every surface, border and text anchor was written for a 0xFBFAF6 background, so
// inverting the window left white cards on white text.
//
// Rather than duplicate the palette into a second enum (which drifts the moment someone
// edits one branch), each token becomes a dynamic `NSColor` that resolves per appearance
// and per contrast preference at draw time. Call sites keep reading `Palette.sage`; only
// the resolution changes. That is the difference between "add a dark theme" and "make the
// theme a function of the environment".

/// A colour that resolves differently in light, dark, and increased-contrast appearances.
///
/// - Parameters:
///   - light/dark: base sRGB values for the two appearances.
///   - hcLight/hcDark: optional stronger variants used only when the user has turned on
///     Increase Contrast. When omitted the base value is reused, which is correct for
///     decorative fills that carry no text.
func adaptiveColor(_ light: UInt32, _ dark: UInt32,
                   hcLight: UInt32? = nil, hcDark: UInt32? = nil) -> Color {
    Color(nsColor: NSColor(name: nil) { appearance in
        let isDark = appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
        let increased = NSWorkspace.shared.accessibilityDisplayShouldIncreaseContrast
        let hex = isDark ? (increased ? (hcDark ?? dark) : dark)
                         : (increased ? (hcLight ?? light) : light)
        return NSColor(srgbRed: CGFloat((hex >> 16) & 0xFF) / 255.0,
                       green: CGFloat((hex >> 8) & 0xFF) / 255.0,
                       blue: CGFloat(hex & 0xFF) / 255.0,
                       alpha: 1.0)
    })
}

/// The hairline highlight used on cards and artwork. It is white at 85% in light mode —
/// which becomes a glowing outline on a dark surface — so dark mode gets a much fainter
/// value instead of the same colour at the same alpha.
func adaptiveBorderHighlight() -> Color {
    Color(nsColor: NSColor(name: nil) { appearance in
        let isDark = appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
        let increased = NSWorkspace.shared.accessibilityDisplayShouldIncreaseContrast
        let alpha: CGFloat = isDark ? (increased ? 0.34 : 0.14) : (increased ? 1.0 : 0.85)
        return NSColor(srgbRed: 1, green: 1, blue: 1, alpha: alpha)
    })
}

// MARK: - Typography
//
// Every fixed `.system(size: 13)` in the views ignores Dynamic Type: the window does not
// grow, so a learner who raises the text size gets clipped text instead of larger text.
// These tokens are built on semantic `Font.TextStyle` cases, which scale with the
// accessibility text size and reflow their containers.
enum Typography {
    static let body = Font.system(.body)
    static let bodyEmphasis = Font.system(.body, weight: .medium)
    static let callout = Font.system(.callout)
    static let footnote = Font.system(.footnote)
    static let caption = Font.system(.caption)
    static let captionEmphasis = Font.system(.caption, weight: .semibold)

    static let section = Font.system(.headline, design: .rounded, weight: .semibold)
    static let title = Font.system(.title3, design: .rounded, weight: .semibold)
    static let display = Font.system(.title2, design: .rounded, weight: .semibold)

    /// The small tracked-out label above a block ("TODAY'S FOCUS"). Caption-scale so it
    /// grows with the rest; tracking is applied at the call site because it is a design
    /// choice per heading, not a property of the token.
    static let eyebrow = Font.system(.caption2, design: .rounded, weight: .semibold)
}

// MARK: - Motion
//
// Reduce Motion is a system setting with a per-app override, and it must gate *decorative*
// motion only: a progress bar still needs to show progress, but a hovering card must not
// spring, drift or parallax. Returning `Animation?` makes the call site explicit —
// `withAnimation(LuminfestMotion.hover(reduceMotion: reduceMotion)) { ... }` compiles to
// "no animation" when the setting is on, rather than silently animating anyway.
enum LuminfestMotion {
    static func hover(reduceMotion: Bool) -> Animation? {
        reduceMotion ? nil : .spring(response: 0.26, dampingFraction: 0.74)
    }

    static func settle(reduceMotion: Bool) -> Animation? {
        reduceMotion ? nil : .spring(response: 0.32, dampingFraction: 0.78)
    }

    static func fade(reduceMotion: Bool, duration: Double = 0.18) -> Animation? {
        reduceMotion ? nil : .easeInOut(duration: duration)
    }

    /// Decorative ambience (breathing art, drifting mesh). Never animated under Reduce
    /// Motion — these carry no information, so freezing them loses nothing.
    static func ambient(reduceMotion: Bool, duration: Double = 2.8) -> Animation? {
        reduceMotion ? nil : .easeInOut(duration: duration).repeatForever(autoreverses: true)
    }
}

// MARK: - Text scale
//
// Backed by `.dynamicTypeSize`, not by a font multiplier: the former is the mechanism
// macOS accessibility expects, it clamps at the platform maximum, and it makes SwiftUI
// reflow containers instead of letting text overflow them.
enum TextScale: String, CaseIterable, Identifiable {
    case system
    case large
    case xLarge
    case xxLarge

    var id: String { rawValue }

    var dynamicTypeSize: DynamicTypeSize? {
        switch self {
        case .system: return nil
        case .large: return .large
        case .xLarge: return .xLarge
        case .xxLarge: return .xxLarge
        }
    }

    var labelKey: String { "settings.text.\(rawValue)" }
}

// MARK: - Appearance preference
//
// `system` must stay distinct from "light": a learner who sets the Mac to switch at sunset
// expects the app to follow, and collapsing that into a stored light/dark choice silently
// breaks the behaviour they configured.
enum AppearancePreference: String, CaseIterable, Identifiable {
    case system
    case light
    case dark

    var id: String { rawValue }

    var colorScheme: ColorScheme? {
        switch self {
        case .system: return nil
        case .light: return .light
        case .dark: return .dark
        }
    }

    var labelKey: String { "settings.appearance.\(rawValue)" }
}
