// swift-tools-version: 6.0
import PackageDescription

// `defaultLocalization` is not optional once the target ships `.lproj` folders: SwiftPM
// refuses the manifest without it, because "which language is the source of truth" has to
// be declared rather than inferred from whatever folder sorted first. English is the
// development language — every key in `Resources/en.lproj` is written by hand, and
// `zh-Hans` is checked against it by LocalizationTests.
let package = Package(
    name: "LuminfestLearningHarness",
    defaultLocalization: "en",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "LearningHarness", targets: ["LearningHarness"])],
    targets: [
        .executableTarget(
            name: "LearningHarness",
            // Features/README.md documents the split for humans only. SwiftPM treats an
            // undeclared file as an unhandled resource and warns on every build; naming
            // it here keeps the manifest honest without bundling prose into the app.
            exclude: ["Features/README.md"],
            // `Visuals/` is a WKWebView document root with a real directory hierarchy
            // (vendor/, tikzjax/fonts/). `.process` FLATTENS every file into the bundle
            // root, which makes `vendor/plotly.min.js` and the TeX WASM paths 404. It is
            // therefore declared as `.copy`, outside Resources/, so the shipped bundle
            // keeps the exact paths index.html and the CSP refer to.
            resources: [.process("Resources"), .copy("Visuals")]
        ),
        .testTarget(name: "LearningHarnessTests", dependencies: ["LearningHarness"])
    ],
    swiftLanguageModes: [.v5]
)
