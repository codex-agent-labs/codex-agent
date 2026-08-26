import CodexAgent

func consumeCodexFailure() -> (String, String, Bool) {
    let failure = CodexFailure(
        code: "compiler_evidence",
        message: "Compiler evidence",
        isRecoverable: true
    )
    return (failure.code, failure.message, failure.isRecoverable)
}

func consumeAgentApprovalDecisions() -> (AgentApprovalDecision, AgentApprovalDecision) {
    (AgentApprovalDecision.accept, AgentApprovalDecision.decline)
}

func consumeAgentCollaborationModes() -> (AgentCollaborationMode, AgentCollaborationMode) {
    (AgentCollaborationMode.default_, AgentCollaborationMode.plan)
}

func consumeAgentMessageRoles() -> (AgentMessageRole, AgentMessageRole) {
    (AgentMessageRole.user, AgentMessageRole.assistant)
}

func consumeAgentInstallationScopes() -> (AgentInstallationScope, AgentInstallationScope) {
    (AgentInstallationScope.user, AgentInstallationScope.workspace)
}
