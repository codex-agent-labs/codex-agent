val pinnedProtocolSchema = layout.projectDirectory.file(
    "protocol/schema/codex_app_server_protocol.v2.schemas.json",
)
val pinnedCompleteProtocolSchema = layout.projectDirectory.file(
    "protocol/schema/codex_app_server_protocol.schemas.json",
)
val protocolProvenance = layout.projectDirectory.file("protocol/schema/provenance.json")

val verifyProtocolSource = tasks.register<VerifyProtocolSourceTask>("verifyProtocolSource") {
    protocolSchema.set(pinnedProtocolSchema)
    completeProtocolSchema.set(pinnedCompleteProtocolSchema)
    provenance.set(protocolProvenance)
    descriptor.set(layout.projectDirectory.file("protocol/schema/descriptors.json"))
    generatedSources.set(
        layout.projectDirectory.dir(
            "src/commonMain/kotlin/io/github/codex_agent_labs/codexagent/appserver/protocol/generated",
        ),
    )
    expectedSchemaSha256.set("9b3de71a5a2ffc980b792a18aa8f8dec3f85f48829560222a0264fe494b679a9")
    expectedCompleteSchemaSha256.set("02a4c63a638fdae4a5f6c3ad32a41a377b642c66f3abc84f6fc47c7f3d6074df")
}

tasks.register("updateProtocol") {
    group = "protocol"
    description = "Regenerates the pinned protocol from exact Codex sources."
    dependsOn(":tooling:protocol-generator:generateProtocol")
}

tasks.named("check").configure { dependsOn(verifyProtocolSource) }
