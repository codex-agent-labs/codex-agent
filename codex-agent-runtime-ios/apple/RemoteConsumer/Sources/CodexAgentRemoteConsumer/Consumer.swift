import CodexAgent
import CodexAgentAuthentication
import CodexAgentObservation
import CodexAgentSwiftSupport

public func makeCodexHost(
    sandboxRootPath: String,
    clientInfo: CodexClientInfo
) -> CodexHost {
    let platform = IosCodexPlatform(
        sandboxRootPath: sandboxRootPath,
        credentialProtection: .whenUnlocked,
        authorizationBrowser: CodexWebAuthenticationBrowser(),
        codexHomePath: sandboxRootPath + "/Library/Application Support/CodexAgent",
        storageRoots: nil
    )
    return CodexHost(platform: platform, clientInfo: clientInfo)
}

public func observeCodexHost(
    _ host: CodexHost
) -> AsyncStream<any CodexHostState> {
    host.lifecycleStates
}

public func openConversationAndSend(
    _ prompt: String,
    using ready: CodexHostStateReady
) async throws -> CodexConversation {
    let agent = ready.agent
    _ = agent.authentication.states
    _ = agent.conversations.activeConversations
    let conversation = try await agent.conversations.open()
    _ = conversation.states
    try await conversation.send(prompt)
    return conversation
}

public func authenticate(
    _ ready: CodexHostStateReady,
    method: (any CodexAuthenticationMethod)? = nil
) async throws {
    if let method {
        try await ready.agent.authentication.authenticate(method: method)
    } else {
        try await ready.agent.authentication.authenticate()
    }
}

private func compileAdvancedConversationOperations(
    _ agent: CodexAgent,
    prompt: String
) async throws {
    let conversation = try await agent.conversations.open(
        conversationId: nil,
        settings: AgentConversationSettings(
            approvalPreset: .strict,
            serviceTier: nil
        )
    )
    try await conversation.send(prompt: prompt)
}
