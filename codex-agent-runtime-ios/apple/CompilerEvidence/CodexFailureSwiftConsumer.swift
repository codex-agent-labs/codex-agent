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
