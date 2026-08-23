# Protocol provenance

The client is generated from OpenAI Codex App Server `0.149.0` at upstream tag
`rust-v0.149.0`, tag object `a4e15bf371341b067c8278d3b70b1a8c7b3d793e`,
and revision `758ef40f50c1a458425c7cfbf1eb12cbc07af0b0`.

The authoritative provenance, input Git blobs, SHA-256 digests, generator
version, and generated-output digests are recorded in
`codex-agent-client/protocol/schema/provenance.json`. The checked-in stable-v2
schema digest is
`9b3de71a5a2ffc980b792a18aa8f8dec3f85f48829560222a0264fe494b679a9`;
the complete schema digest is
`02a4c63a638fdae4a5f6c3ad32a41a377b642c66f3abc84f6fc47c7f3d6074df`.

`./gradlew :codex-agent-client:verifyProtocolSource` verifies those inputs and
all generated outputs. To regenerate, check out the recorded Codex revision and
run `:codex-agent-client:updateProtocol` with the four `codexProtocol*` file
properties listed in the provenance command. Review the complete generated diff
and update identity/runtime pins atomically.
