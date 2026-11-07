import Foundation

/// Where the bundled artwork actually lives.
///
/// SwiftPM's generated `Bundle.module` accessor is not usable inside a packaged `.app`.
/// For an executable target with resources this toolchain emits:
///
///     let mainPath  = Bundle.main.bundleURL.appendingPathComponent("<Package>_<Target>.bundle")
///     let buildPath = "/Users/<builder>/…/.build/arm64-apple-macosx/release/<…>.bundle"
///     guard let bundle = Bundle(path: mainPath) ?? Bundle(path: buildPath) else { fatalError(…) }
///
/// Two consequences, both fatal. `Bundle.main.bundleURL` is the `.app` directory itself,
/// not `Contents/Resources`, so a correctly packaged bundle is never found there; and the
/// only other candidate is an absolute path on the machine that built it. The app
/// therefore resolved its artwork on the build machine and aborted on every other Mac —
/// signed, portable, arm64, and dead on the first frame that drew a sprite.
///
/// This resolver asks the locations a packaged app and a `swift test` tree actually use,
/// in that order, and never aborts: artwork is decoration, so a bundle that cannot be
/// found degrades to "no sprite" and the caller draws its placeholder. A missing PNG must
/// not be able to kill a session mid-lesson.
enum AppResources {
    static let bundleName = "LuminfestLearningHarness_LearningHarness"

    private final class BundleFinder {}

    static let bundle: Bundle = {
        var candidates: [URL] = []
        // A packaged app: Contents/Resources/<Package>_<Target>.bundle
        if let resources = Bundle.main.resourceURL {
            candidates.append(resources.appendingPathComponent(bundleName + ".bundle"))
        }
        // A bundle parked beside Contents, and the test bundle's own Resources.
        candidates.append(Bundle.main.bundleURL.appendingPathComponent(bundleName + ".bundle"))
        // A `swift test` tree. Two things are true here and both used to break the probe:
        // `Bundle.main` is the `xctest` *tool* directory (`…/Developer/usr/bin`), not the
        // `.xctest` bundle, so every candidate derived from it points outside the build
        // tree; and SwiftPM copies the resource bundle *next to* the `.xctest`, not into
        // its `Contents/Resources`. The code under test is linked into the .xctest, so
        // `Bundle(for:)` is the only handle on the directory that actually holds it.
        // Without this the resolver fell through to `Bundle.main`, whose `localizations`
        // reports `["en"]` for a plain directory - so the suite saw an English-only tree
        // and reported missing tables rather than a missing bundle.
        let testBundle = Bundle(for: BundleFinder.self).bundleURL
        candidates.append(testBundle.appendingPathComponent(bundleName + ".bundle"))
        candidates.append(testBundle.deletingLastPathComponent()
            .appendingPathComponent(bundleName + ".bundle"))
        if let sibling = Bundle(for: BundleFinder.self).resourceURL {
            candidates.append(sibling.appendingPathComponent(bundleName + ".bundle"))
        }
        for candidate in candidates {
            if let bundle = Bundle(url: candidate) { return bundle }
        }
        // Nothing found. Callers treat a nil image as "draw the placeholder", so this is a
        // quieter outcome than the crash the generated accessor produced.
        return Bundle.main
    }()

    static func url(for name: String, withExtension ext: String) -> URL? {
        bundle.url(forResource: name, withExtension: ext)
            ?? Bundle.main.url(forResource: name, withExtension: ext)
    }
}
