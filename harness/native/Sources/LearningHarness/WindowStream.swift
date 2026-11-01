import AppKit
import Foundation

/// Tells the backend where this app's window is, so `/app` can present it in a browser tab.
///
/// The browser view is a capture of *this* window — the same app, the same lesson, the same
/// backend — so something has to say which rectangle of the screen to capture. The window
/// server knows, but it will not answer without Accessibility, which is the permission the
/// *input* path needs and the capture path deliberately does not. The app already knows its
/// own frame, so it reports it instead: no permission, no window-server query, and the
/// region is right even when the window is moved or resized.
///
/// Two details that are easy to get wrong and invisible when they are:
///
/// * **The origin is flipped.** AppKit measures from the bottom-left of the main display;
///   `screencapture` measures from the top-left. The conversion uses the main display's
///   height, which is the one `screencapture` also uses as its origin.
/// * **The whole frame, not the content rect.** The title bar is part of what a person sees,
///   and cropping it out would make the browser view look subtly unlike the app.
@MainActor final class WindowFrameReporter {
    static let shared = WindowFrameReporter()

    /// Two seconds: a window that is being dragged produces a new frame every few
    /// milliseconds, and reporting each one would be a request per pixel of travel.
    private let interval: TimeInterval = 2.0

    /// How long to stay quiet after the backend says streaming is switched off. Without it a
    /// switched-off instance would receive a refusal every two seconds for the whole session.
    private let backoff: TimeInterval = 60.0

    private var timer: Timer?
    private var lastSent: NSDictionary?
    private var suppressedUntil: Date?
    private weak var store: AppStore?

    private init() {}

    func start(store: AppStore) {
        self.store = store
        guard timer == nil else { return }
        let timer = Timer(timeInterval: interval, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.report() }
        }
        // Common mode, so a report still happens while a menu is open or a sheet is tracking.
        RunLoop.main.add(timer, forMode: .common)
        self.timer = timer
        Task { @MainActor in self.report() }
    }

    func stop() {
        timer?.invalidate()
        timer = nil
        store = nil
    }

    /// Report the window now, ignoring the backoff.
    ///
    /// The backoff exists so a *refusal* is not re-asked every two seconds. When the operator
    /// turns the switch on, the refusal has just been withdrawn — waiting out the rest of the
    /// minute would make the switch look like it did nothing, which is the exact complaint
    /// this whole path has to answer.
    func reportNow() {
        suppressedUntil = nil
        lastSent = nil
        report()
    }

    private func report() {
        guard let store, store.authenticated else { return }
        if let suppressedUntil, Date() < suppressedUntil { return }
        guard let window = NSApp.windows.first(where: { $0.isVisible && $0.contentView != nil }),
              let main = NSScreen.screens.first else { return }

        let frame = window.frame
        let body: [String: Any] = [
            "x": Int(frame.origin.x.rounded()),
            // AppKit: bottom-left origin. `screencapture`: top-left origin of the main display.
            "y": Int((main.frame.height - frame.maxY).rounded()),
            "width": Int(frame.width.rounded()),
            "height": Int(frame.height.rounded()),
            "scale": Double(window.backingScaleFactor),
        ]
        let comparable = NSDictionary(dictionary: body)
        if let lastSent, lastSent.isEqual(comparable) { return }

        Task { @MainActor in
            do {
                _ = try await store.api.data("/stream/window", method: "POST", body: body)
                lastSent = comparable
            } catch let failure as AppFailure where failure.status == 503 {
                // Streaming is off on this instance. Stay quiet rather than asking again
                // every two seconds; the operator turning it on is a restart.
                suppressedUntil = Date().addingTimeInterval(backoff)
            } catch {
                // Any other failure is transient — the backend may still be starting. The
                // next tick tries again, and `lastSent` is not updated, so a real change is
                // not lost.
            }
        }
    }
}
