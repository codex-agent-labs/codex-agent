import CodexAgent
@testable import CodexAgentObservation
import CodexAgentObjectiveCConsumer
import CodexAgentSwiftSupport
import XCTest

final class CodexAgentObservationTests: XCTestCase {
    func testBufferingCancellationAndDroppedStreamReleaseTheObservation() async {
        let buffered: AsyncStream<Int> = codexAsyncStream { yield in
            yield(1)
            yield(2)
            return {}
        }
        var iterator = buffered.makeAsyncIterator()
        let latest = await iterator.next()
        XCTAssertEqual(latest, 2)

        let closed = expectation(description: "observation closed")
        let cancellable: AsyncStream<Int> = codexAsyncStream { _ in
            return { closed.fulfill() }
        }
        let task = Task {
            for await _ in cancellable { /* wait for cancellation */ }
        }
        task.cancel()
        await fulfillment(of: [closed], timeout: 1)

        let droppedClosed = expectation(description: "dropped observation closed")
        let droppedDeinitialized = expectation(description: "dropped observation released")
        weak var weakToken: TestObservationToken?
        var dropped: AsyncStream<Int>? = codexAsyncStream { yield in
            let token = TestObservationToken(
                onClose: { droppedClosed.fulfill() },
                onDeinit: { droppedDeinitialized.fulfill() }
            )
            token.yield = yield
            weakToken = token
            return token.close
        }
        XCTAssertNotNil(dropped)
        XCTAssertNotNil(weakToken)

        dropped = nil

        await fulfillment(of: [droppedClosed, droppedDeinitialized], timeout: 1)
        XCTAssertNil(weakToken)
    }

    func testCodexOperationErrorsExposeStructuredFailure() {
        let accept = AgentApprovalDecision.accept
        let decline = AgentApprovalDecision.decline
        XCTAssertEqual(accept.name, "ACCEPT")
        XCTAssertEqual(accept.ordinal, 0)
        XCTAssertEqual(decline.name, "DECLINE")
        XCTAssertEqual(decline.ordinal, 1)
        XCTAssertFalse(accept === decline)
        XCTAssertTrue(accept === AgentApprovalDecision.accept)
        XCTAssertTrue(decline === AgentApprovalDecision.decline)

        let failure = CodexFailure(
            code: "workspace_unavailable",
            message: "Workspace is unavailable",
            isRecoverable: true
        )
        let error = CodexOperationException(failure: failure, cause: nil).asError()

        XCTAssertEqual(error.codexFailure?.code, failure.code)
        XCTAssertEqual(error.codexFailure?.message, failure.message)
        XCTAssertEqual(error.codexFailure?.isRecoverable, failure.isRecoverable)
    }

    func testObjectiveCConsumerExposesStructuredFailure() async {
        let objectiveCConsumer = expectation(description: "Objective-C lifecycle consumer")
        CDXRunObjectiveCConsumer { failureMessage in
            XCTAssertNil(failureMessage, failureMessage ?? "Objective-C consumer failed")
            objectiveCConsumer.fulfill()
        }
        await fulfillment(of: [objectiveCConsumer], timeout: 120)
    }
}

private final class TestObservationToken {
    var yield: ((Int) -> Void)?
    private let onClose: () -> Void
    private let onDeinit: () -> Void
    private var isClosed = false

    init(onClose: @escaping () -> Void, onDeinit: @escaping () -> Void) {
        self.onClose = onClose
        self.onDeinit = onDeinit
    }

    func close() {
        guard !isClosed else { return }
        isClosed = true
        yield = nil
        onClose()
    }

    deinit { onDeinit() }
}

private func compileTypedObservationSurface(
    host: CodexHost,
    agent: CodexAgent,
    conversation: CodexConversation
) {
    let _: AsyncStream<any CodexHostState> = host.lifecycleStates
    let _: AsyncStream<AgentAuthenticationState> = agent.authentication.states
    let _: AsyncStream<AgentInteractionState> = agent.interactions.states
    let _: AsyncStream<AgentIntegrationAuthorizationState> = agent.integrationAuthorization.states
    let _: AsyncStream<(any AgentIntegration)?> = agent.integrationAuthorization.activeIntegrations
    let _: AsyncStream<CodexConversation?> = agent.conversations.activeConversations
    let _: AsyncStream<AgentConversationState> = conversation.states
}

private func compileSimpleAndAdvancedOperations(
    agent: CodexAgent,
    conversation: CodexConversation
) async throws {
    try await agent.authentication.authenticate()
    try await agent.authentication.authenticate(method: CodexAuthenticationMethodChatGptDeviceCode())
    _ = try await agent.conversations.open()
    _ = try await agent.conversations.open(
        conversationId: nil,
        settings: AgentConversationSettings(
            approvalPreset: .strict,
            serviceTier: nil
        )
    )
    try await conversation.send("Hello")
    try await conversation.send(prompt: "Hello")
}

private func compileConvenienceSurface(
    agent: CodexAgent,
    conversation: CodexConversation,
    mcpServer: AgentMcpServer,
    hook: AgentHook,
    interactionState: AgentInteractionState,
    interaction: any AgentPendingInteraction
) {
    _ = agent.authentication.isAuthenticated
    _ = agent.authentication.isAuthenticating
    _ = conversation.isTurnActive
    _ = agent.integrationAuthorization.isAuthorizing
    _ = mcpServer.isAuthorized
    _ = hook.canTrust
    _ = interactionState.isResolving(interaction: interaction)
}

private func compileCapabilitiesMutationsAndElicitation(
    agent: CodexAgent,
    conversationState: AgentConversationState,
    skill: AgentSkill,
    hook: AgentHook,
    pluginReference: AgentPluginReference,
    approval: AgentPendingApproval,
    pendingElicitation: AgentPendingElicitation,
    integration: any AgentIntegration,
    elicitation: AgentElicitation
) async throws {
    _ = agent.skills.isAvailable
    _ = agent.hooks.isAvailable
    _ = agent.plugins.isAvailable
    _ = agent.connectors.isAvailable
    _ = agent.mcpServers.isAvailable
    let _: AgentConversationStatus = .closed
    _ = conversationState.canStartTurn
    _ = conversationState.canReload
    _ = conversationState.canCancelTurn

    _ = try await agent.skills.install(directory: "/tmp/skill", scope: .user)
    try await agent.skills.uninstall(skill: skill)
    let installedHook = try await agent.hooks.install(directory: "/tmp/hook", scope: .workspace)
    try await agent.hooks.trust(hook: installedHook)
    try await agent.hooks.uninstall(hook: hook)
    _ = try await agent.plugins.install(plugin: pluginReference)
    try await agent.plugins.uninstall(plugin: pluginReference)
    try await agent.interactions.resolve(approval: approval, decision: .accept)
    try await agent.interactions.resolve(
        elicitation: pendingElicitation,
        response: AgentElicitationResponse.decline()
    )
    try await agent.integrationAuthorization.authorize(target: integration)

    let initial = elicitation.initialValues()
    let validation = elicitation.validate(content: initial)
    _ = validation.isValid
    let accepted = elicitation.accept(content: initial)
    _ = elicitation.accepts(response: accepted)
    _ = AgentElicitationResponse.decline()
    _ = AgentElicitationResponse.cancel()
}
