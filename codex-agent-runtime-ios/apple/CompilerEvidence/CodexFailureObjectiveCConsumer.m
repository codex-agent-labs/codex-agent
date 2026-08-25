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
