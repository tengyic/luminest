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
            resources: [.process("Resources")]
        ),
        .testTarget(name: "LearningHarnessTests", dependencies: ["LearningHarness"])
    ],
    swiftLanguageModes: [.v5]
)
