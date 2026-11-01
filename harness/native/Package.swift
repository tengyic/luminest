// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "LuminfestLearningHarness",
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
