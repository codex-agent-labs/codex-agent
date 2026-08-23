import CodexAgent

public extension CodexHost {
    var lifecycleStates: AsyncStream<any CodexHostState> {
        codexStateStream(lifecycleState) { $0 as? any CodexHostState }
    }
}

public extension CodexAuthentication {
    var states: AsyncStream<AgentAuthenticationState> {
        codexStateStream(state) { $0 as? AgentAuthenticationState }
    }
}

public extension CodexInteractions {
    var states: AsyncStream<AgentInteractionState> {
        codexStateStream(state) { $0 as? AgentInteractionState }
    }
}

public extension CodexIntegrationAuthorization {
    var states: AsyncStream<AgentIntegrationAuthorizationState> {
        codexStateStream(state) { $0 as? AgentIntegrationAuthorizationState }
    }

    var activeIntegrations: AsyncStream<(any AgentIntegration)?> {
        codexOptionalStateStream(active) { $0 as? any AgentIntegration }
    }
}

public extension CodexConversations {
    var activeConversations: AsyncStream<CodexConversation?> {
        codexOptionalStateStream(active) { $0 as? CodexConversation }
    }
}

public extension CodexConversation {
    var states: AsyncStream<AgentConversationState> {
        codexStateStream(state) { $0 as? AgentConversationState }
    }
}

func codexAsyncStream<Element>(
    observe: (@escaping (Element) -> Void) -> () -> Void
) -> AsyncStream<Element> {
    AsyncStream(bufferingPolicy: .bufferingNewest(1)) { continuation in
        let close = observe { continuation.yield($0) }
        continuation.onTermination = { _ in close() }
    }
}

private func codexStateStream<Element>(
    _ state: any Kotlinx_coroutines_coreStateFlow,
    cast: @escaping (Any?) -> Element?
) -> AsyncStream<Element> {
    codexAsyncStream { yield in
        let observation = CodexStateObservation(state: state) { value in
            if let value = cast(value) { yield(value) }
        }
        return observation.close
    }
}

private func codexOptionalStateStream<Element>(
    _ state: any Kotlinx_coroutines_coreStateFlow,
    cast: @escaping (Any) -> Element?
) -> AsyncStream<Element?> {
    codexAsyncStream { yield in
        let observation = CodexStateObservation(state: state) { value in
            guard let value else {
                yield(nil)
                return
            }
            if let element = cast(value) { yield(element) }
        }
        return observation.close
    }
}
