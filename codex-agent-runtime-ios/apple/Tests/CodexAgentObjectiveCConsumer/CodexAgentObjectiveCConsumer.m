#import "CodexAgentObjectiveCConsumer.h"

#import <CodexAgent/CodexAgent.h>

#define CDX_VERIFY_ENUM(TYPE, SELECTOR, EXPECTED_NAME, EXPECTED_ORDINAL) do { \
    TYPE *value = [TYPE SELECTOR]; \
    if (![value.name isEqualToString:EXPECTED_NAME] || \
        value.ordinal != EXPECTED_ORDINAL || value != [TYPE SELECTOR]) { \
        return [NSString stringWithFormat:@"Objective-C enum changed: %s.%s", #TYPE, #SELECTOR]; \
    } \
} while (0)

static NSString *CDXVerifyD065Values(
    CodexAgentConversationId *conversationId,
    CodexAgentAgentMcpEnvironmentSource *remoteEnvironment
) {
    CDX_VERIFY_ENUM(CodexAgentAgentApprovalPreset, never, @"NEVER", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentApprovalPreset, autoReview, @"AUTO_REVIEW", 1);
    CDX_VERIFY_ENUM(CodexAgentAgentApprovalPreset, askMe, @"ASK_ME", 2);
    CDX_VERIFY_ENUM(CodexAgentAgentApprovalPreset, strict, @"STRICT", 3);
    CDX_VERIFY_ENUM(CodexAgentAgentAuthenticationStatus, signedOut, @"SIGNED_OUT", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentAuthenticationStatus, authenticating, @"AUTHENTICATING", 1);
    CDX_VERIFY_ENUM(CodexAgentAgentAuthenticationStatus, authenticated, @"AUTHENTICATED", 2);
    CDX_VERIFY_ENUM(CodexAgentAgentCapability, webSearch, @"WEB_SEARCH", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentCatalogFreshness, live, @"LIVE", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentCatalogFreshness, freshCache, @"FRESH_CACHE", 1);
    CDX_VERIFY_ENUM(CodexAgentAgentCatalogFreshness, staleCache, @"STALE_CACHE", 2);
    CDX_VERIFY_ENUM(CodexAgentAgentConversationStatus, theNew, @"NEW", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentConversationStatus, opening, @"OPENING", 1);
    CDX_VERIFY_ENUM(CodexAgentAgentConversationStatus, ready, @"READY", 2);
    CDX_VERIFY_ENUM(CodexAgentAgentConversationStatus, startingTurn, @"STARTING_TURN", 3);
    CDX_VERIFY_ENUM(CodexAgentAgentConversationStatus, runningTurn, @"RUNNING_TURN", 4);
    CDX_VERIFY_ENUM(CodexAgentAgentConversationStatus, cancellingTurn, @"CANCELLING_TURN", 5);
    CDX_VERIFY_ENUM(CodexAgentAgentConversationStatus, reloading, @"RELOADING", 6);
    CDX_VERIFY_ENUM(CodexAgentAgentConversationStatus, failed, @"FAILED", 7);
    CDX_VERIFY_ENUM(CodexAgentAgentConversationStatus, closed, @"CLOSED", 8);
    CDX_VERIFY_ENUM(CodexAgentAgentElicitationAction, accept, @"ACCEPT", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentElicitationAction, decline, @"DECLINE", 1);
    CDX_VERIFY_ENUM(CodexAgentAgentElicitationAction, cancel, @"CANCEL", 2);
    CDX_VERIFY_ENUM(CodexAgentAgentElicitationValidationReason, missingRequired, @"MISSING_REQUIRED", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentElicitationValidationReason, unknownField, @"UNKNOWN_FIELD", 1);
    CDX_VERIFY_ENUM(CodexAgentAgentElicitationValidationReason, invalidType, @"INVALID_TYPE", 2);
    CDX_VERIFY_ENUM(CodexAgentAgentElicitationValidationReason, nonFiniteNumber, @"NON_FINITE_NUMBER", 3);
    CDX_VERIFY_ENUM(CodexAgentAgentElicitationValidationReason, belowMinimum, @"BELOW_MINIMUM", 4);
    CDX_VERIFY_ENUM(CodexAgentAgentElicitationValidationReason, aboveMaximum, @"ABOVE_MAXIMUM", 5);
    CDX_VERIFY_ENUM(CodexAgentAgentElicitationValidationReason, nonInteger, @"NON_INTEGER", 6);
    CDX_VERIFY_ENUM(CodexAgentAgentElicitationValidationReason, invalidFormat, @"INVALID_FORMAT", 7);
    CDX_VERIFY_ENUM(CodexAgentAgentElicitationValidationReason, invalidSelection, @"INVALID_SELECTION", 8);
    CDX_VERIFY_ENUM(CodexAgentAgentElicitationValidationReason, duplicateSelection, @"DUPLICATE_SELECTION", 9);
    CDX_VERIFY_ENUM(CodexAgentAgentFormFieldType, string, @"STRING", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentFormFieldType, number, @"NUMBER", 1);
    CDX_VERIFY_ENUM(CodexAgentAgentFormFieldType, integer, @"INTEGER", 2);
    CDX_VERIFY_ENUM(CodexAgentAgentFormFieldType, boolean, @"BOOLEAN", 3);
    CDX_VERIFY_ENUM(CodexAgentAgentFormFieldType, singleSelect, @"SINGLE_SELECT", 4);
    CDX_VERIFY_ENUM(CodexAgentAgentFormFieldType, multiSelect, @"MULTI_SELECT", 5);
    CDX_VERIFY_ENUM(CodexAgentAgentFormStringFormat, email, @"EMAIL", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentFormStringFormat, uri, @"URI", 1);
    CDX_VERIFY_ENUM(CodexAgentAgentFormStringFormat, date, @"DATE", 2);
    CDX_VERIFY_ENUM(CodexAgentAgentFormStringFormat, dateTime, @"DATE_TIME", 3);
    CDX_VERIFY_ENUM(CodexAgentAgentHookRunStatus, running, @"RUNNING", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentHookRunStatus, completed, @"COMPLETED", 1);
    CDX_VERIFY_ENUM(CodexAgentAgentHookRunStatus, failed, @"FAILED", 2);
    CDX_VERIFY_ENUM(CodexAgentAgentHookRunStatus, blocked, @"BLOCKED", 3);
    CDX_VERIFY_ENUM(CodexAgentAgentHookRunStatus, stopped, @"STOPPED", 4);
    CDX_VERIFY_ENUM(CodexAgentAgentHookTrustStatus, managed, @"MANAGED", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentHookTrustStatus, untrusted, @"UNTRUSTED", 1);
    CDX_VERIFY_ENUM(CodexAgentAgentHookTrustStatus, trusted, @"TRUSTED", 2);
    CDX_VERIFY_ENUM(CodexAgentAgentHookTrustStatus, modified, @"MODIFIED", 3);
    CDX_VERIFY_ENUM(CodexAgentAgentIntegrationAuthorizationStatus, idle, @"IDLE", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentIntegrationAuthorizationStatus, starting, @"STARTING", 1);
    CDX_VERIFY_ENUM(CodexAgentAgentIntegrationAuthorizationStatus, awaitingCompletion, @"AWAITING_COMPLETION", 2);
    CDX_VERIFY_ENUM(CodexAgentAgentIntegrationAuthorizationStatus, authorized, @"AUTHORIZED", 3);
    CDX_VERIFY_ENUM(CodexAgentAgentIntegrationAuthorizationStatus, failed, @"FAILED", 4);
    CDX_VERIFY_ENUM(CodexAgentAgentMcpAuthStatus, unknown, @"UNKNOWN", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentMcpAuthStatus, unsupported, @"UNSUPPORTED", 1);
    CDX_VERIFY_ENUM(CodexAgentAgentMcpAuthStatus, notLoggedIn, @"NOT_LOGGED_IN", 2);
    CDX_VERIFY_ENUM(CodexAgentAgentMcpAuthStatus, bearerToken, @"BEARER_TOKEN", 3);
    CDX_VERIFY_ENUM(CodexAgentAgentMcpAuthStatus, oauth, @"OAUTH", 4);
    CDX_VERIFY_ENUM(CodexAgentAgentMcpAuthentication, oauth, @"OAUTH", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentMcpAuthentication, chatGpt, @"CHAT_GPT", 1);
    CDX_VERIFY_ENUM(CodexAgentAgentMcpToolApproval, auto_, @"AUTO", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentMcpToolApproval, prompt, @"PROMPT", 1);
    CDX_VERIFY_ENUM(CodexAgentAgentMcpToolApproval, writes, @"WRITES", 2);
    CDX_VERIFY_ENUM(CodexAgentAgentMcpToolApproval, approve, @"APPROVE", 3);
    CDX_VERIFY_ENUM(CodexAgentAgentMcpToolExposureSurface, codeMode, @"CODE_MODE", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentMcpToolExposureSurface, deferred, @"DEFERRED", 1);
    CDX_VERIFY_ENUM(CodexAgentAgentMcpToolExposureSurface, direct, @"DIRECT", 2);
    CDX_VERIFY_ENUM(CodexAgentAgentPlanStepStatus, pending, @"PENDING", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentPlanStepStatus, inProgress, @"IN_PROGRESS", 1);
    CDX_VERIFY_ENUM(CodexAgentAgentPlanStepStatus, completed, @"COMPLETED", 2);
    CDX_VERIFY_ENUM(CodexAgentAgentPluginAuthPolicy, onInstall, @"ON_INSTALL", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentPluginAuthPolicy, onUse, @"ON_USE", 1);
    CDX_VERIFY_ENUM(CodexAgentAgentPluginInstallPolicy, notAvailable, @"NOT_AVAILABLE", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentPluginInstallPolicy, available, @"AVAILABLE", 1);
    CDX_VERIFY_ENUM(CodexAgentAgentPluginInstallPolicy, installedByDefault, @"INSTALLED_BY_DEFAULT", 2);
    CDX_VERIFY_ENUM(CodexAgentAgentResolution, preferred, @"Preferred", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentResolution, default_, @"Default", 1);
    CDX_VERIFY_ENUM(CodexAgentAgentResolution, first, @"First", 2);
    CDX_VERIFY_ENUM(CodexAgentAgentResourceOrigin, user, @"USER", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentResourceOrigin, workspace, @"WORKSPACE", 1);
    CDX_VERIFY_ENUM(CodexAgentAgentResourceOrigin, plugin, @"PLUGIN", 2);
    CDX_VERIFY_ENUM(CodexAgentAgentResourceOrigin, managed, @"MANAGED", 3);
    CDX_VERIFY_ENUM(CodexAgentAgentResourceOrigin, unknown, @"UNKNOWN", 4);
    CDX_VERIFY_ENUM(CodexAgentAgentSkillScope, system, @"SYSTEM", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentSkillScope, user, @"USER", 1);
    CDX_VERIFY_ENUM(CodexAgentAgentSkillScope, repo, @"REPO", 2);
    CDX_VERIFY_ENUM(CodexAgentAgentSkillScope, plugin, @"PLUGIN", 3);
    CDX_VERIFY_ENUM(CodexAgentAgentSkillScope, admin, @"ADMIN", 4);
    CDX_VERIFY_ENUM(CodexAgentAgentWorkActivity, runningCommand, @"RUNNING_COMMAND", 0);
    CDX_VERIFY_ENUM(CodexAgentAgentWorkActivity, writingFiles, @"WRITING_FILES", 1);
    CDX_VERIFY_ENUM(CodexAgentCodexAuthorizationPurpose, chatGpt, @"CHAT_GPT", 0);
    CDX_VERIFY_ENUM(CodexAgentCodexAuthorizationPurpose, external, @"EXTERNAL", 1);
    CDX_VERIFY_ENUM(CodexAgentCodexWorkspaceSelectionReason, notSelected, @"NOT_SELECTED", 0);
    CDX_VERIFY_ENUM(CodexAgentCodexWorkspaceSelectionReason, notFound, @"NOT_FOUND", 1);
    CDX_VERIFY_ENUM(CodexAgentCodexWorkspaceSelectionReason, accessRevoked, @"ACCESS_REVOKED", 2);
    CDX_VERIFY_ENUM(CodexAgentCodexWorkspaceSelectionReason, invalidSelection, @"INVALID_SELECTION", 3);

    if (![[CodexAgentAgentApprovalPreset never].displayName isEqualToString:@"Never"] ||
        ![[CodexAgentAgentApprovalPreset autoReview].displayName isEqualToString:@"Auto review"] ||
        ![[CodexAgentAgentApprovalPreset askMe].displayName isEqualToString:@"Ask me"] ||
        ![[CodexAgentAgentApprovalPreset strict].displayName isEqualToString:@"Strict"]) {
        return @"Objective-C approval-preset display names changed";
    }
    CodexAgentAgentCapability *webSearch = [CodexAgentAgentCapability webSearch];
    if (![webSearch.id isEqualToString:@"web_search"] ||
        ![webSearch.displayLabel isEqualToString:@"Web search"] ||
        ![webSearch.icon isEqualToString:@"🌐"] ||
        ![webSearch.promptLabel isEqualToString:@"Use 🌐 Web search"]) {
        return @"Objective-C capability metadata changed";
    }
    if (![[CodexAgentAgentSkillScope system].displayName isEqualToString:@"Built in"] ||
        ![[CodexAgentAgentSkillScope user].displayName isEqualToString:@"User"] ||
        ![[CodexAgentAgentSkillScope repo].displayName isEqualToString:@"Workspace"] ||
        ![[CodexAgentAgentSkillScope plugin].displayName isEqualToString:@"Plugin"] ||
        ![[CodexAgentAgentSkillScope admin].displayName isEqualToString:@"Managed"]) {
        return @"Objective-C skill-scope display names changed";
    }

    CodexAgentAgentConversationSummary *summary = [[CodexAgentAgentConversationSummary alloc]
        initWithConversationId:conversationId title:@"Conversation" updatedAtEpochSeconds:42];
    if (summary.conversationId != conversationId ||
        ![summary.title isEqualToString:@"Conversation"] || summary.updatedAtEpochSeconds != 42) {
        return @"Objective-C conversation summary changed";
    }
    CodexAgentAgentFormOption *option = [[CodexAgentAgentFormOption alloc]
        initWithValue:@"choice" title:@"Choice" description:nil];
    CodexAgentAgentFormOption *describedOption = [[CodexAgentAgentFormOption alloc]
        initWithValue:@"described" title:@"Described" description:@"Description"];
    if (![option.value isEqualToString:@"choice"] ||
        ![option.title isEqualToString:@"Choice"] || option.description_ != nil ||
        ![describedOption.description_ isEqualToString:@"Description"]) {
        return @"Objective-C form option changed";
    }
    CodexAgentAgentMcpEnvironmentVariable *variable =
        [[CodexAgentAgentMcpEnvironmentVariable alloc]
            initWithName:@"TOKEN"
                  source:remoteEnvironment];
    CodexAgentAgentMcpEnvironmentVariable *unscopedVariable =
        [[CodexAgentAgentMcpEnvironmentVariable alloc] initWithName:@"HOME" source:nil];
    if (![variable.name isEqualToString:@"TOKEN"] || variable.source != remoteEnvironment ||
        unscopedVariable.source != nil) {
        return @"Objective-C MCP environment variable changed";
    }
    CodexAgentInt *callbackPort = [CodexAgentInt numberWithInt:3210];
    CodexAgentAgentMcpOauthConfiguration *oauth =
        [[CodexAgentAgentMcpOauthConfiguration alloc]
            initWithClientId:@"client"
                 callbackPort:callbackPort];
    CodexAgentAgentMcpOauthConfiguration *emptyOauth =
        [[CodexAgentAgentMcpOauthConfiguration alloc] initWithClientId:nil callbackPort:nil];
    if (![oauth.clientId isEqualToString:@"client"] || oauth.callbackPort.intValue != 3210 ||
        emptyOauth.clientId != nil || emptyOauth.callbackPort != nil) {
        return @"Objective-C MCP OAuth configuration changed";
    }
    CodexAgentAgentPluginReference *plugin = [[CodexAgentAgentPluginReference alloc]
        initWithId:@"plugin-id"
        name:@"plugin-name"
        marketplaceName:@"marketplace"
        marketplacePath:@"/marketplace/plugin"
        remotePluginId:@"remote-plugin"];
    CodexAgentAgentPluginReference *localPlugin = [[CodexAgentAgentPluginReference alloc]
        initWithId:@"local-id"
        name:@"local-name"
        marketplaceName:@"local-marketplace"
        marketplacePath:nil
        remotePluginId:nil];
    if (![plugin.id isEqualToString:@"plugin-id"] ||
        ![plugin.name isEqualToString:@"plugin-name"] ||
        ![plugin.marketplaceName isEqualToString:@"marketplace"] ||
        ![plugin.marketplacePath isEqualToString:@"/marketplace/plugin"] ||
        ![plugin.remotePluginId isEqualToString:@"remote-plugin"] ||
        ![plugin.uri isEqualToString:@"plugin://plugin-name@marketplace"] ||
        localPlugin.marketplacePath != nil || localPlugin.remotePluginId != nil ||
        ![localPlugin.uri isEqualToString:@"plugin://local-name@local-marketplace"]) {
        return @"Objective-C plugin reference changed";
    }
    CodexAgentAgentPluginSkill *pluginSkill = [[CodexAgentAgentPluginSkill alloc]
        initWithName:@"plugin-skill"
        description:@"Plugin skill"
        isEnabled:YES
        path:@"/plugins/skill"];
    CodexAgentAgentPluginSkill *pathlessSkill = [[CodexAgentAgentPluginSkill alloc]
        initWithName:@"pathless" description:@"Pathless" isEnabled:NO path:nil];
    if (![pluginSkill.name isEqualToString:@"plugin-skill"] ||
        ![pluginSkill.description_ isEqualToString:@"Plugin skill"] ||
        !pluginSkill.isEnabled || ![pluginSkill.path isEqualToString:@"/plugins/skill"] ||
        pathlessSkill.isEnabled || pathlessSkill.path != nil) {
        return @"Objective-C plugin skill changed";
    }
    CodexAgentAgentServiceTier *serviceTier = [[CodexAgentAgentServiceTier alloc]
        initWithId:@"fast" name:@"Fast" description:@"Fast tier"];
    if (![serviceTier.id isEqualToString:@"fast"] ||
        ![serviceTier.name isEqualToString:@"Fast"] ||
        ![serviceTier.description_ isEqualToString:@"Fast tier"]) {
        return @"Objective-C service tier changed";
    }
    CodexAgentLong *nextOffset = [CodexAgentLong numberWithLongLong:12];
    CodexAgentAgentSkillChunk *chunk = [[CodexAgentAgentSkillChunk alloc]
        initWithContent:@"chunk" nextOffset:nextOffset totalBytes:34];
    CodexAgentAgentSkillChunk *terminalChunk = [[CodexAgentAgentSkillChunk alloc]
        initWithContent:@"terminal" nextOffset:nil totalBytes:8];
    if (![chunk.content isEqualToString:@"chunk"] ||
        chunk.nextOffset.longLongValue != 12 || chunk.totalBytes != 34 ||
        terminalChunk.nextOffset != nil) {
        return @"Objective-C skill chunk changed";
    }
    CodexAgentCodexClientInfo *clientInfo = [[CodexAgentCodexClientInfo alloc]
        initWithName:@"objective-c"
        title:@"Objective-C Consumer"
        version:@"1.0"];
    if (![clientInfo.name isEqualToString:@"objective-c"] ||
        ![clientInfo.title isEqualToString:@"Objective-C Consumer"] ||
        ![clientInfo.version isEqualToString:@"1.0"]) {
        return @"Objective-C client info changed";
    }
    CodexAgentCodexWorkspace *workspace = [[CodexAgentCodexWorkspace alloc]
        initWithPath:@"/tmp/objective-c-workspace" displayName:@"Objective-C Workspace"];
    if (![workspace.path isEqualToString:@"/tmp/objective-c-workspace"] ||
        ![workspace.displayName isEqualToString:@"Objective-C Workspace"]) {
        return @"Objective-C workspace changed";
    }
    CodexAgentAgentApprovalPreset *autoReview = [CodexAgentAgentApprovalPreset autoReview];
    CodexAgentAgentConversationSettings *settings = [[CodexAgentAgentConversationSettings alloc]
        initWithApprovalPreset:autoReview serviceTier:@"fast"];
    CodexAgentAgentConversationSettings *settingsWithoutTier =
        [[CodexAgentAgentConversationSettings alloc]
            initWithApprovalPreset:autoReview
                       serviceTier:nil];
    if (settings.approvalPreset != autoReview ||
        ![settings.serviceTier isEqualToString:@"fast"] || settingsWithoutTier.serviceTier != nil) {
        return @"Objective-C conversation settings changed";
    }
    CodexAgentAgentElicitationValidationReason *missingRequired =
        [CodexAgentAgentElicitationValidationReason missingRequired];
    CodexAgentAgentElicitationValidationIssue *issue =
        [[CodexAgentAgentElicitationValidationIssue alloc]
            initWithFieldName:@"email"
                      reason:missingRequired];
    if (![issue.fieldName isEqualToString:@"email"] || issue.reason != missingRequired) {
        return @"Objective-C elicitation validation issue changed";
    }
    CodexAgentAgentPlanStepStatus *pending = [CodexAgentAgentPlanStepStatus pending];
    CodexAgentAgentPlanStep *step = [[CodexAgentAgentPlanStep alloc]
        initWithText:@"Inspect" status:pending];
    if (![step.text isEqualToString:@"Inspect"] || step.status != pending) {
        return @"Objective-C plan step changed";
    }
    CodexAgentAgentMcpToolApproval *prompt = [CodexAgentAgentMcpToolApproval prompt];
    CodexAgentAgentMcpToolConfiguration *tool = [[CodexAgentAgentMcpToolConfiguration alloc]
        initWithApproval:prompt];
    CodexAgentAgentMcpToolConfiguration *defaultTool =
        [[CodexAgentAgentMcpToolConfiguration alloc] initWithApproval:nil];
    if (tool.approval != prompt || defaultTool.approval != nil) {
        return @"Objective-C MCP tool configuration changed";
    }

    return nil;
}

#undef CDX_VERIFY_ENUM

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
    NSString *d065Failure = CDXVerifyD065Values(conversationId, remoteEnvironment);
    if (d065Failure != nil) {
        [self finishWithFailure:d065Failure];
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
