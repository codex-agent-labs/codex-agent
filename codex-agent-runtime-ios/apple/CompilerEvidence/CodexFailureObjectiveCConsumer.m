#import <CodexAgent/CodexAgent.h>

static BOOL consumeCodexFailure(void) {
    CodexAgentCodexFailure *failure = [[CodexAgentCodexFailure alloc]
        initWithCode:@"compiler_evidence"
              message:@"Compiler evidence"
        isRecoverable:YES];
    return failure.code.length > 0 &&
        failure.message.length > 0 &&
        failure.isRecoverable;
}

static BOOL consumeConversationId(void) {
    CodexAgentConversationId *conversationId = [[CodexAgentConversationId alloc]
        initWithValue:@"compiler_evidence"];
    return [conversationId.value isEqualToString:@"compiler_evidence"];
}

static BOOL consumeAgentApprovalDecisions(void) {
    CodexAgentAgentApprovalDecision *accept = [CodexAgentAgentApprovalDecision accept];
    CodexAgentAgentApprovalDecision *decline = [CodexAgentAgentApprovalDecision decline];
    return accept != decline;
}

static BOOL consumeAgentCollaborationModes(void) {
    CodexAgentAgentCollaborationMode *defaultMode = [CodexAgentAgentCollaborationMode default_];
    CodexAgentAgentCollaborationMode *plan = [CodexAgentAgentCollaborationMode plan];
    return defaultMode != plan;
}

static BOOL consumeAgentMessageRoles(void) {
    CodexAgentAgentMessageRole *user = [CodexAgentAgentMessageRole user];
    CodexAgentAgentMessageRole *assistant = [CodexAgentAgentMessageRole assistant];
    return user != assistant;
}

static BOOL consumeAgentInstallationScopes(void) {
    CodexAgentAgentInstallationScope *user = [CodexAgentAgentInstallationScope user];
    CodexAgentAgentInstallationScope *workspace = [CodexAgentAgentInstallationScope workspace];
    return user != workspace;
}

static BOOL consumeAgentMcpEnvironmentSources(void) {
    CodexAgentAgentMcpEnvironmentSource *local = [CodexAgentAgentMcpEnvironmentSource local];
    CodexAgentAgentMcpEnvironmentSource *remote = [CodexAgentAgentMcpEnvironmentSource remote];
    return local != remote;
}
