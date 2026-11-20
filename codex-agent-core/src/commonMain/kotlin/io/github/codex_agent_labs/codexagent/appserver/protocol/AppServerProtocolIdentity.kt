package io.github.codex_agent_labs.codexagent.appserver

/** Protocol identity required to verify a custom runtime against this client. */
public object AppServerProtocolIdentity {
    public const val APP_SERVER_VERSION: String = "0.149.0"
    public const val UPSTREAM_REVISION: String = "758ef40f50c1a458425c7cfbf1eb12cbc07af0b0"
    public const val SCHEMA_SHA256: String = "9b3de71a5a2ffc980b792a18aa8f8dec3f85f48829560222a0264fe494b679a9"
    internal const val UPSTREAM_TAG: String = "rust-v0.149.0"
    internal const val UPSTREAM_TAG_OBJECT: String = "a4e15bf371341b067c8278d3b70b1a8c7b3d793e"
    internal const val COMPLETE_SCHEMA_SHA256: String = "02a4c63a638fdae4a5f6c3ad32a41a377b642c66f3abc84f6fc47c7f3d6074df"
    internal const val RPC_SOURCE_SHA256: String = "78c516097c55b665e375807be6dcdceba232805c9ae9fa48420b0a537f0df705"
    internal const val METHOD_SOURCE_SHA256: String = "f301b8b3bdcee9275457348ea041f0187c7fd375b57a0fbac48e799fb4bc9235"
}
