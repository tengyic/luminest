import SwiftUI
import AppKit

// MARK: - AppKit event bridge

/// The interaction surface: an `NSView` that owns what SwiftUI on macOS still cannot.
///
/// Two things live here and only here. **Pressure** — a SwiftUI `DragGesture` on macOS
/// reports a location and nothing else; `NSEvent.pressure` is the only way to read the
/// tablet or Force Touch value, and `pressureChange(with:)` is the only way to notice it
/// *change* mid-stroke, which is the whole point of pressure-sensitive ink. **Keyboard
/// and menu actions** — the editor's shortcuts (V/H/P/E/T…. for tools, ⌘Z, ⌘⌫, ⌘[ / ⌘]
/// for stacking) need an actual first responder.
///
/// Touching is intentionally *not* wired: overriding both `touchesBegan` and
/// `mouseDown` on a trackpad would fire both and lay down two strokes for one gesture.
/// macOS delivers tablet and Force Touch pressure on the mouse-drag events already
/// handled below, so there is nothing to gain and a duplicate-stroke bug to lose.
struct BoardEventBridge: NSViewRepresentable {
    var onScroll: (CGVector, CGPoint, CGSize, Bool) -> Void
    var onMagnify: (CGFloat, CGPoint, CGSize) -> Void
    var onPress: (CGPoint, CGSize, CGFloat) -> Void
    var onDrag: (CGPoint, CGSize, CGFloat) -> Void
    var onRelease: (CGPoint, CGSize) -> Void
    var onRightClick: (CGPoint, CGSize) -> Void
    var onKey: (String, NSEvent.ModifierFlags) -> Void

    func makeNSView(context: Context) -> BridgeView {
        let view = BridgeView()
        view.handlers = Handlers(onScroll: onScroll, onMagnify: onMagnify, onPress: onPress,
                                onDrag: onDrag, onRelease: onRelease,
                                onRightClick: onRightClick, onKey: onKey)
        return view
    }

    func updateNSView(_ view: BridgeView, context: Context) {
        view.handlers = Handlers(onScroll: onScroll, onMagnify: onMagnify, onPress: onPress,
                                onDrag: onDrag, onRelease: onRelease,
                                onRightClick: onRightClick, onKey: onKey)
    }

    struct Handlers {
        var onScroll: (CGVector, CGPoint, CGSize, Bool) -> Void
        var onMagnify: (CGFloat, CGPoint, CGSize) -> Void
        var onPress: (CGPoint, CGSize, CGFloat) -> Void
        var onDrag: (CGPoint, CGSize, CGFloat) -> Void
        var onRelease: (CGPoint, CGSize) -> Void
        var onRightClick: (CGPoint, CGSize) -> Void
        var onKey: (String, NSEvent.ModifierFlags) -> Void
    }

    final class BridgeView: NSView {
        var handlers: Handlers? {
            didSet { window?.makeFirstResponder(self) }
        }

        /// The live pressure of the current stroke. Held across events so a
        /// `pressureChange` without a movement event still updates the stroke.
        private var pressure: CGFloat = 0.5

        override var acceptsFirstResponder: Bool { true }

        // A board is drawn on, so it must not scroll when the pointer reaches an edge.
        override var enclosingScrollView: NSScrollView? { nil }

        override func resetCursorRects() {
            discardCursorRects()
        }

        override func scrollWheel(with event: NSEvent) {
            guard let handlers else { super.scrollWheel(with: event); return }
            handlers.onScroll(CGVector(dx: event.scrollingDeltaX, dy: event.scrollingDeltaY),
                              convert(event.locationInWindow, from: nil), bounds.size,
                              event.modifierFlags.contains(.command))
        }

        override func magnify(with event: NSEvent) {
            guard let handlers else { super.magnify(with: event); return }
            handlers.onMagnify(max(0.01, 1 + event.magnification),
                               convert(event.locationInWindow, from: nil), bounds.size)
        }

        /// Pressure the hardware actually reports, or nil when it is reporting the
        /// saturation value a trackpad always gives.
        ///
        /// A Force Touch trackpad and an Apple Pencil both report a meaningful range;
        /// an ordinary click reports 1.0 and every touch reports 1.0. Treating 1.0 as
        /// data is what produced the old flat strokes, so it is read as "no data" and
        /// the sampler falls back to velocity.
        private func readablePressure(_ event: NSEvent) -> CGFloat? {
            let reported = event.pressure
            guard reported > 0.02, reported < 0.985 else { return nil }
            return CGFloat(min(1, max(0.05, reported)))
        }

        override func mouseDown(with event: NSEvent) {
            window?.makeFirstResponder(self)
            pressure = readablePressure(event) ?? 0.5
            handlers?.onPress(convert(event.locationInWindow, from: nil), bounds.size, pressure)
        }

        override func mouseDragged(with event: NSEvent) {
            if let reported = readablePressure(event) { pressure = reported }
            handlers?.onDrag(convert(event.locationInWindow, from: nil), bounds.size, pressure)
        }

        override func mouseUp(with event: NSEvent) {
            handlers?.onRelease(convert(event.locationInWindow, from: nil), bounds.size)
        }

        /// The pressure changed while the pointer stood still — a finger pressing
        /// harder without moving. Only meaningful mid-stroke, which the editor tracks.
        override func pressureChange(with event: NSEvent) {
            guard event.type == .pressure else { return }
            if let reported = readablePressure(event) {
                pressure = reported
                handlers?.onDrag(convert(event.locationInWindow, from: nil), bounds.size, pressure)
            }
        }

        override func rightMouseDown(with event: NSEvent) {
            window?.makeFirstResponder(self)
            handlers?.onRightClick(convert(event.locationInWindow, from: nil), bounds.size)
        }

        override func keyDown(with event: NSEvent) {
            let characters = event.charactersIgnoringModifiers ?? ""
            guard !characters.isEmpty else { super.keyDown(with: event); return }
            let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
            // An unhandled key must not vanish: an editor that swallows ⌘A or a plain
            // letter is indistinguishable from a frozen one.
            handlers?.onKey(characters, flags)
            if flags.contains(.command) { return }
            super.keyDown(with: event)
        }
    }
}
