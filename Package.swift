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
            url: "https://github.com/codex-agent-labs/codex-agent/releases/download/v0.2.0/CodexAgent-0.2.0.xcframework.zip",
            checksum: "849bbaf8df8384e5c71d7dc56d2e617fe9cd35b3b354f7d41267cfa81647f167"
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
