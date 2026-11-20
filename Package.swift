// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "CodexAgent",
    platforms: [.iOS(.v15)],
    products: [
        .library(name: "CodexAgent", targets: ["CodexAgent"]),
        .library(
            name: "CodexAgentAuthentication",
            targets: ["CodexAgentAuthentication"]
        ),
        .library(
            name: "CodexAgentObservation",
            targets: ["CodexAgentObservation"]
        ),
        .library(
            name: "CodexAgentSwiftSupport",
            targets: ["CodexAgentSwiftSupport"]
        ),
    ],
    targets: [
        .binaryTarget(
            name: "CodexAgent",
            url: "https://github.com/codex-agent-labs/codex-agent/releases/download/sdk%2Fv0.8.0/CodexAgent-0.8.0.xcframework.zip",
            checksum: "3e57888e58ef978ac02656484d68c4ba8456e590c4eef85b7f1ea6c706614525"
        ),
        .target(
            name: "CodexAgentAuthentication",
            dependencies: ["CodexAgent"],
            path: "codex-agent-runtime-ios/apple/Sources/CodexAgentAuthentication",
            resources: [.copy("PrivacyInfo.xcprivacy")]
        ),
        .target(
            name: "CodexAgentObservation",
            dependencies: ["CodexAgent"],
            path: "codex-agent-runtime-ios/apple/Sources/CodexAgentObservation"
        ),
        .target(
            name: "CodexAgentSwiftSupport",
            dependencies: ["CodexAgent"],
            path: "codex-agent-runtime-ios/apple/Sources/CodexAgentSwiftSupport"
        ),
    ]
)
