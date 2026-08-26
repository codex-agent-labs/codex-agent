#import "CodexAgentObjectiveCConsumer.h"

#import <CodexAgent/CodexAgent.h>

typedef CDXOperation *(^CDXOperationFactory)(dispatch_block_t completed);

static const NSTimeInterval CDXConsumerTimeoutSeconds = 110.0;
static const NSTimeInterval CDXCleanupTimeoutSeconds = 5.0;
static const NSTimeInterval CDXUnsubscribeProofDelaySeconds = 0.1;

@interface CDXObjectiveCConsumerRun : NSObject

@property(nonatomic, copy) CDXObjectiveCConsumerCompletion completion;
@property(nonatomic, copy) NSString *sandboxRoot;
@property(nonatomic, strong) NSURL *workspaceURL;
@property(nonatomic, strong) CDXHost *host;
@property(nonatomic, strong) CDXAgent *agent;
@property(nonatomic, strong) CDXConversation *conversation;
@property(nonatomic, strong) CDXOperation *operation;
@property(nonatomic, strong) CDXObservation *hostObservation;
@property(nonatomic, strong) CDXObservation *activeConversationObservation;
@property(nonatomic, strong) CDXObservation *conversationObservation;
@property(nonatomic, strong) CDXObjectiveCConsumerRun *keepAlive;
@property(nonatomic) BOOL hostObserved;
@property(nonatomic) BOOL activeConversationObserved;
@property(nonatomic) BOOL conversationObserved;
@property(nonatomic) BOOL conversationClosedObserved;
@property(nonatomic) BOOL conversationCloseCompleted;
@property(nonatomic) BOOL postCloseStarted;
@property(nonatomic) BOOL finishing;
@property(nonatomic) BOOL completed;
@property(nonatomic) NSUInteger hostCallbackCount;
@property(nonatomic) NSUInteger hostCallbackCountAtInvalidation;

- (instancetype)initWithCompletion:(CDXObjectiveCConsumerCompletion)completion;
- (void)run;

@end

@implementation CDXObjectiveCConsumerRun

- (instancetype)initWithCompletion:(CDXObjectiveCConsumerCompletion)completion {
    self = [super init];
    if (self != nil) {
        _completion = [completion copy];
    }
    return self;
}

- (void)run {
    self.keepAlive = self;
    CodexAgentConversationId *conversationId = [[CodexAgentConversationId alloc]
        initWithValue:@"conversation-1"];
    if (![conversationId.value isEqualToString:@"conversation-1"]) {
        [self finishWithFailure:@"Objective-C conversation ID changed"];
        return;
    }
    CodexAgentAgentApprovalDecision *accept = [CodexAgentAgentApprovalDecision accept];
    CodexAgentAgentApprovalDecision *decline = [CodexAgentAgentApprovalDecision decline];
    if (![accept.name isEqualToString:@"ACCEPT"] || accept.ordinal != 0 ||
        ![decline.name isEqualToString:@"DECLINE"] || decline.ordinal != 1 ||
        accept == decline || accept != [CodexAgentAgentApprovalDecision accept] ||
        decline != [CodexAgentAgentApprovalDecision decline]) {
        [self finishWithFailure:@"Objective-C approval decisions changed"];
        return;
    }
    CodexAgentAgentCollaborationMode *defaultMode = [CodexAgentAgentCollaborationMode default_];
    CodexAgentAgentCollaborationMode *plan = [CodexAgentAgentCollaborationMode plan];
    if (![defaultMode.name isEqualToString:@"DEFAULT"] || defaultMode.ordinal != 0 ||
        ![plan.name isEqualToString:@"PLAN"] || plan.ordinal != 1 ||
        defaultMode == plan || defaultMode != [CodexAgentAgentCollaborationMode default_] ||
        plan != [CodexAgentAgentCollaborationMode plan]) {
        [self finishWithFailure:@"Objective-C collaboration modes changed"];
        return;
    }
    CodexAgentAgentMessageRole *user = [CodexAgentAgentMessageRole user];
    CodexAgentAgentMessageRole *assistant = [CodexAgentAgentMessageRole assistant];
    if (![user.name isEqualToString:@"USER"] || user.ordinal != 0 ||
        ![assistant.name isEqualToString:@"ASSISTANT"] || assistant.ordinal != 1 ||
        user == assistant || user != [CodexAgentAgentMessageRole user] ||
        assistant != [CodexAgentAgentMessageRole assistant]) {
        [self finishWithFailure:@"Objective-C message roles changed"];
        return;
    }
    CodexAgentAgentInstallationScope *userScope = [CodexAgentAgentInstallationScope user];
    CodexAgentAgentInstallationScope *workspaceScope = [CodexAgentAgentInstallationScope workspace];
    if (![userScope.name isEqualToString:@"User"] || userScope.ordinal != 0 ||
        ![workspaceScope.name isEqualToString:@"Workspace"] || workspaceScope.ordinal != 1 ||
        userScope == workspaceScope || userScope != [CodexAgentAgentInstallationScope user] ||
        workspaceScope != [CodexAgentAgentInstallationScope workspace]) {
        [self finishWithFailure:@"Objective-C installation scopes changed"];
        return;
    }
    CodexAgentAgentMcpEnvironmentSource *localEnvironment =
        [CodexAgentAgentMcpEnvironmentSource local];
    CodexAgentAgentMcpEnvironmentSource *remoteEnvironment =
        [CodexAgentAgentMcpEnvironmentSource remote];
    if (![localEnvironment.name isEqualToString:@"LOCAL"] || localEnvironment.ordinal != 0 ||
        ![remoteEnvironment.name isEqualToString:@"REMOTE"] || remoteEnvironment.ordinal != 1 ||
        localEnvironment == remoteEnvironment ||
        localEnvironment != [CodexAgentAgentMcpEnvironmentSource local] ||
        remoteEnvironment != [CodexAgentAgentMcpEnvironmentSource remote]) {
        [self finishWithFailure:@"Objective-C MCP environment sources changed"];
        return;
    }
    __weak CDXObjectiveCConsumerRun *weakSelf = self;
    dispatch_after(
        dispatch_time(DISPATCH_TIME_NOW, (int64_t)(CDXConsumerTimeoutSeconds * NSEC_PER_SEC)),
        dispatch_get_main_queue(),
        ^{
            CDXObjectiveCConsumerRun *run = weakSelf;
            if (run != nil && !run.completed) {
                [run finishWithFailure:@"Objective-C lifecycle consumer timed out"];
            }
        }
    );
    self.sandboxRoot = [NSTemporaryDirectory()
        stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
    NSString *workspacePath = [self.sandboxRoot stringByAppendingPathComponent:@"workspace"];
    NSError *directoryError = nil;
    if (![[NSFileManager defaultManager] createDirectoryAtPath:workspacePath
                                  withIntermediateDirectories:YES
                                                   attributes:nil
                                                        error:&directoryError]) {
        [self finishWithFailure:directoryError.localizedDescription];
        return;
    }
    self.workspaceURL = [NSURL fileURLWithPath:workspacePath isDirectory:YES];
    self.host = [[CDXHost alloc]
        initWithSandboxRootPath:self.sandboxRoot
                    clientName:@"objective-c-consumer"
                   clientTitle:@"Objective-C Consumer"
                 clientVersion:@"0.2.0"];

    if (self.host.state.status != [CDXHostStatus initial]) {
        [self finishWithFailure:@"Objective-C host did not start in New state"];
        return;
    }

    self.hostObservation = [self.host observeStateWithHandler:^(CDXHostState *state) {
        CDXObjectiveCConsumerRun *run = weakSelf;
        if (run == nil || run.finishing) return;
        if (![NSThread isMainThread]) {
            [run finishWithFailure:@"Objective-C host state was not delivered on the main queue"];
            return;
        }
        run.hostCallbackCount += 1;
        run.hostObserved = YES;
    }];
    if (!self.hostObserved) {
        [self finishWithFailure:@"Objective-C host observation did not deliver its current value"];
        return;
    }

    [self beginOperation:^CDXOperation *(dispatch_block_t completed) {
        return [self.host startWithCompletion:^(CDXOperationResult *result) {
            completed();
            CDXObjectiveCConsumerRun *run = weakSelf;
            if (run == nil || run.finishing) return;
            if (![run requireSuccess:result operation:@"start"] ||
                ![run requireMainQueue:@"start completion"]) return;
            CDXHostState *state = run.host.state;
            if (state.status != [CDXHostStatus workspaceRequired] ||
                state.requirementMessage.length == 0 || state.agent != nil) {
                [run finishWithFailure:@"Objective-C start did not expose WorkspaceRequired state"];
                return;
            }
            [run selectWorkspace];
        }];
    }];
}

- (void)selectWorkspace {
    __weak CDXObjectiveCConsumerRun *weakSelf = self;
    [self beginOperation:^CDXOperation *(dispatch_block_t completed) {
        return [self.host selectWorkspaceURL:self.workspaceURL
                                   completion:^(CDXOperationResult *result) {
            completed();
            CDXObjectiveCConsumerRun *run = weakSelf;
            if (run == nil || run.finishing) return;
            if (![run requireSuccess:result operation:@"workspace selection"] ||
                ![run requireMainQueue:@"workspace completion"]) return;
            CDXHostState *state = run.host.state;
            if (state.status != [CDXHostStatus ready] || state.agent == nil ||
                ![state.workspacePath isEqualToString:run.workspaceURL.path]) {
                [run finishWithFailure:@"Objective-C workspace selection did not expose Ready agent state"];
                return;
            }
            run.agent = state.agent;
            [run openConversation];
        }];
    }];
}

- (void)openConversation {
    __weak CDXObjectiveCConsumerRun *weakSelf = self;
    self.activeConversationObservation =
        [self.agent observeActiveConversationWithHandler:^(CDXConversation *conversation) {
            CDXObjectiveCConsumerRun *run = weakSelf;
            if (run == nil || run.finishing) return;
            if (![NSThread isMainThread]) {
                [run finishWithFailure:@"Objective-C active conversation was not delivered on the main queue"];
                return;
            }
            run.activeConversationObserved = YES;
            if (conversation != nil && run.conversation != nil && conversation != run.conversation) {
                [run finishWithFailure:@"Objective-C active conversation lost wrapper identity"];
            }
        }];
    if (!self.activeConversationObserved) {
        [self finishWithFailure:@"Objective-C active-conversation observation omitted its current value"];
        return;
    }
    [self beginOperation:^CDXOperation *(dispatch_block_t completed) {
        return [self.agent openConversationWithCompletion:^(CDXConversationResult *result) {
            completed();
            CDXObjectiveCConsumerRun *run = weakSelf;
            if (run == nil || run.finishing) return;
            if (![run requireMainQueue:@"open conversation completion"]) return;
            if (result.conversation == nil || result.failure != nil) {
                [run finishWithFailure:[run describeFailure:result.failure
                                                     prefix:@"Objective-C conversation open failed"]];
                return;
            }
            run.conversation = result.conversation;
            if (run.agent.activeConversation != run.conversation) {
                [run finishWithFailure:@"Objective-C open result lost active-conversation identity"];
                return;
            }
            [run observeAndCloseConversation];
        }];
    }];
}

- (void)observeAndCloseConversation {
    __weak CDXObjectiveCConsumerRun *weakSelf = self;
    self.conversationObservation =
        [self.conversation observeStateWithHandler:^(CDXConversationState *state) {
            CDXObjectiveCConsumerRun *run = weakSelf;
            if (run == nil || run.finishing) return;
            if (![NSThread isMainThread]) {
                [run finishWithFailure:@"Objective-C conversation state was not delivered on the main queue"];
                return;
            }
            run.conversationObserved = YES;
            if (state.status == [CDXConversationStatus closed]) {
                run.conversationClosedObserved = YES;
                [run continueAfterConversationClosedIfReady];
            }
        }];
    if (!self.conversationObserved || self.conversation.state.status != [CDXConversationStatus ready] ||
        self.conversation.state.conversationId.length == 0 || !self.conversation.state.canStartTurn) {
        [self finishWithFailure:@"Objective-C conversation did not expose its current Ready state"];
        return;
    }
    [self beginOperation:^CDXOperation *(dispatch_block_t completed) {
        return [self.conversation disposeWithCompletion:^(CDXOperationResult *result) {
            completed();
            CDXObjectiveCConsumerRun *run = weakSelf;
            if (run == nil || run.finishing) return;
            if (![run requireSuccess:result operation:@"conversation dispose"] ||
                ![run requireMainQueue:@"conversation dispose completion"]) return;
            run.conversationCloseCompleted = YES;
            [run continueAfterConversationClosedIfReady];
        }];
    }];
}

- (void)continueAfterConversationClosedIfReady {
    if (!self.conversationCloseCompleted || !self.conversationClosedObserved || self.postCloseStarted) return;
    self.postCloseStarted = YES;
    if (self.conversation.state.status != [CDXConversationStatus closed] ||
        self.conversation.state.canStartTurn) {
        [self finishWithFailure:@"Objective-C conversation did not expose Closed state"];
        return;
    }
    [self verifyStructuredPostCloseFailure];
}

- (void)verifyStructuredPostCloseFailure {
    __weak CDXObjectiveCConsumerRun *weakSelf = self;
    [self beginOperation:^CDXOperation *(dispatch_block_t completed) {
        return [self.conversation sendPrompt:@"must fail after close"
                                   completion:^(CDXOperationResult *result) {
            completed();
            CDXObjectiveCConsumerRun *run = weakSelf;
            if (run == nil || run.finishing) return;
            if (![run requireMainQueue:@"post-close failure completion"]) return;
            CDXFailure *failure = result.failure;
            if (result.success || failure == nil ||
                ![failure.code isEqualToString:@"operation_failed"] ||
                ![failure.message isEqualToString:@"Codex operation failed"] ||
                failure.isRecoverable) {
                [run finishWithFailure:@"Objective-C post-close operation exposed the wrong structured failure"];
                return;
            }
            [run verifyCancelAfterClose];
        }];
    }];
}

- (void)verifyCancelAfterClose {
    __weak CDXObjectiveCConsumerRun *weakSelf = self;
    [self beginOperation:^CDXOperation *(dispatch_block_t completed) {
        return [self.conversation cancelTurnWithCompletion:^(CDXOperationResult *result) {
            completed();
            CDXObjectiveCConsumerRun *run = weakSelf;
            if (run == nil || run.finishing) return;
            CDXFailure *failure = result.failure;
            if (result.success || failure == nil ||
                ![failure.code isEqualToString:@"operation_failed"] ||
                ![failure.message isEqualToString:@"Codex operation failed"] ||
                failure.isRecoverable) {
                [run finishWithFailure:@"Objective-C post-close cancellation exposed the wrong structured failure"];
                return;
            }
            [run verifyRepeatedClose];
        }];
    }];
}

- (void)verifyRepeatedClose {
    __weak CDXObjectiveCConsumerRun *weakSelf = self;
    [self beginOperation:^CDXOperation *(dispatch_block_t completed) {
        return [self.conversation disposeWithCompletion:^(CDXOperationResult *result) {
            completed();
            CDXObjectiveCConsumerRun *run = weakSelf;
            if (run == nil || run.finishing) return;
            if (![run requireSuccess:result operation:@"repeated conversation dispose"]) return;
            [run disposeAgent];
        }];
    }];
}

- (void)disposeAgent {
    [self.hostObservation invalidate];
    [self.hostObservation dispose];
    self.hostObservation = nil;
    self.hostCallbackCountAtInvalidation = self.hostCallbackCount;

    __weak CDXObjectiveCConsumerRun *weakSelf = self;
    [self beginOperation:^CDXOperation *(dispatch_block_t completed) {
        return [self.agent disposeWithCompletion:^(CDXOperationResult *result) {
            completed();
            CDXObjectiveCConsumerRun *run = weakSelf;
            if (run == nil || run.finishing) return;
            if (![run requireSuccess:result operation:@"agent dispose"]) return;
            if (run.host.state.status != [CDXHostStatus closed]) {
                [run finishWithFailure:@"Objective-C agent dispose did not close its parent host"];
                return;
            }
            dispatch_after(
                dispatch_time(
                    DISPATCH_TIME_NOW,
                    (int64_t)(CDXUnsubscribeProofDelaySeconds * NSEC_PER_SEC)
                ),
                dispatch_get_main_queue(),
                ^{
                    CDXObjectiveCConsumerRun *delayedRun = weakSelf;
                    if (delayedRun == nil || delayedRun.finishing) return;
                    if (delayedRun.hostCallbackCount != delayedRun.hostCallbackCountAtInvalidation) {
                        [delayedRun finishWithFailure:
                            @"Objective-C host observation delivered after invalidation"];
                        return;
                    }
                    [delayedRun finishWithFailure:nil];
                }
            );
        }];
    }];
}

- (void)beginOperation:(CDXOperationFactory)factory {
    if (self.finishing) return;
    __weak CDXObjectiveCConsumerRun *weakSelf = self;
    __block BOOL completedInline = NO;
    __block CDXOperation *started = nil;
    started = factory(^{
        completedInline = YES;
        CDXObjectiveCConsumerRun *run = weakSelf;
        if (run != nil && run.operation == started) run.operation = nil;
    });
    if (!completedInline && !self.finishing) self.operation = started;
}

- (BOOL)requireSuccess:(CDXOperationResult *)result operation:(NSString *)operation {
    if (!result.success || result.failure != nil) {
        [self finishWithFailure:[self describeFailure:result.failure
                                            prefix:[operation stringByAppendingString:@" failed"]]];
        return NO;
    }
    return YES;
}

- (BOOL)requireMainQueue:(NSString *)event {
    if (![NSThread isMainThread]) {
        [self finishWithFailure:[event stringByAppendingString:@" was not delivered on the main queue"]];
        return NO;
    }
    return YES;
}

- (NSString *)describeFailure:(CDXFailure *)failure prefix:(NSString *)prefix {
    if (failure == nil) return prefix;
    return [NSString stringWithFormat:@"%@: %@: %@", prefix, failure.code, failure.message];
}

- (void)finishWithFailure:(NSString *)failure {
    if (self.finishing) return;
    self.finishing = YES;
    [self.operation cancel];
    [self.operation dispose];
    self.operation = nil;
    [self.hostObservation invalidate];
    [self.hostObservation dispose];
    [self.activeConversationObservation invalidate];
    [self.activeConversationObservation dispose];
    [self.conversationObservation invalidate];
    [self.conversationObservation dispose];

    __weak CDXObjectiveCConsumerRun *weakSelf = self;
    dispatch_after(
        dispatch_time(DISPATCH_TIME_NOW, (int64_t)(CDXCleanupTimeoutSeconds * NSEC_PER_SEC)),
        dispatch_get_main_queue(),
        ^{
            CDXObjectiveCConsumerRun *run = weakSelf;
            if (run != nil && !run.completed) {
                [run completeWithFailure:failure ?: @"Objective-C host cleanup timed out"];
            }
        }
    );
    void (^complete)(NSString *) = ^(NSString *cleanupFailure) {
        CDXObjectiveCConsumerRun *run = weakSelf;
        if (run == nil) return;
        [run completeWithFailure:failure ?: cleanupFailure];
    };
    if (self.host == nil) {
        complete(nil);
        return;
    }
    [self.host disposeWithCompletion:^(CDXOperationResult *result) {
        CDXObjectiveCConsumerRun *run = weakSelf;
        if (run == nil) return;
        complete(result.success ? nil : [run describeFailure:result.failure
                                                       prefix:@"Objective-C host cleanup failed"]);
    }];
}

- (void)completeWithFailure:(NSString *)failure {
    if (self.completed) return;
    self.completed = YES;
    NSString *sandboxRoot = self.sandboxRoot;
    CDXObjectiveCConsumerCompletion completion = self.completion;
    self.completion = nil;
    self.operation = nil;
    self.hostObservation = nil;
    self.activeConversationObservation = nil;
    self.conversationObservation = nil;
    self.workspaceURL = nil;
    self.host = nil;
    self.agent = nil;
    self.conversation = nil;
    self.sandboxRoot = nil;
    if (sandboxRoot != nil) [[NSFileManager defaultManager] removeItemAtPath:sandboxRoot error:nil];
    if (completion != nil) completion(failure);
    self.keepAlive = nil;
}

@end

void CDXRunObjectiveCConsumer(CDXObjectiveCConsumerCompletion completion) {
    NSCParameterAssert(completion != nil);
    dispatch_async(dispatch_get_main_queue(), ^{
        [[[CDXObjectiveCConsumerRun alloc] initWithCompletion:completion] run];
    });
}
