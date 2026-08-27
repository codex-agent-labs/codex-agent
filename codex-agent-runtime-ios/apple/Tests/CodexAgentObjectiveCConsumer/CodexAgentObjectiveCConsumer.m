#import "CodexAgentObjectiveCConsumer.h"

#import <CodexAgent/CodexAgent.h>
#include <math.h>

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

static NSString *CDXVerifyD076AuthorizationUrls(void) {
    CodexAgentCodexAuthorizationUrlCompanion *companion =
        [CodexAgentCodexAuthorizationUrl companion];
    NSString *chatGptValue = @"https://auth.openai.com/oauth/authorize";
    NSString *externalValue = @"https://example.com/oauth";
    CodexAgentCodexAuthorizationUrl *chatGpt = [companion chatGptValue:chatGptValue];
    CodexAgentCodexAuthorizationUrl *external = [companion externalValue:externalValue];

    if (![chatGpt.value isEqualToString:chatGptValue] ||
        chatGpt.purpose != [CodexAgentCodexAuthorizationPurpose chatGpt] ||
        ![external.value isEqualToString:externalValue] ||
        external.purpose != [CodexAgentCodexAuthorizationPurpose external]) {
        return @"Objective-C authorization URLs changed";
    }
    return nil;
}

static NSString *CDXVerifyD077McpServerValues(void) {
    CodexAgentAgentMcpAuthStatus *oauth = [CodexAgentAgentMcpAuthStatus oauth];
    CodexAgentAgentMcpAuthStatus *notLoggedIn = [CodexAgentAgentMcpAuthStatus notLoggedIn];
    CodexAgentAgentResourceOrigin *workspace = [CodexAgentAgentResourceOrigin workspace];
    CodexAgentAgentMcpServer *authorized = [[CodexAgentAgentMcpServer alloc]
        initWithName:@"oauth-server"
        displayName:@"OAuth Server"
        authStatus:oauth
        configuration:nil
        origin:workspace
        canRemove:YES];
    if (![authorized.name isEqualToString:@"oauth-server"] ||
        ![authorized.displayName isEqualToString:@"OAuth Server"] ||
        authorized.authStatus != oauth || authorized.configuration != nil ||
        authorized.origin != workspace || !authorized.canRemove || !authorized.isAuthorized) {
        return @"Objective-C MCP server values changed";
    }

    CodexAgentAgentMcpServer *unauthorized = [[CodexAgentAgentMcpServer alloc]
        initWithName:@"signed-out-server"
        displayName:@"Signed-out Server"
        authStatus:notLoggedIn
        configuration:nil
        origin:workspace
        canRemove:NO];
    if (unauthorized.authStatus != notLoggedIn || unauthorized.isAuthorized) {
        return @"Objective-C MCP server authorization changed";
    }

    CodexAgentAgentIntegrationMcpServer *integration =
        [[CodexAgentAgentIntegrationMcpServer alloc] initWithServer:authorized];
    id<CodexAgentAgentIntegration> integrationView = integration;
    if (integrationView != integration || integration.server != authorized ||
        ![integration.id isEqualToString:@"oauth-server"] ||
        ![integration.displayName isEqualToString:@"OAuth Server"] ||
        ![integrationView.id isEqualToString:@"oauth-server"] ||
        ![integrationView.displayName isEqualToString:@"OAuth Server"]) {
        return @"Objective-C MCP server integration changed";
    }
    return nil;
}

static NSString *CDXVerifyD078McpConfigurationValues(void) {
    NSDictionary<NSString *, NSString *> *headers = @{
        @"X-Static": @"value",
        @"X-Trace": @"trace-value",
    };
    NSDictionary<NSString *, NSString *> *environmentHeaders = @{
        @"Authorization": @"MCP_AUTH",
        @"X-Environment": @"MCP_ENVIRONMENT",
    };
    CodexAgentAgentMcpTransportHttp *http = [[CodexAgentAgentMcpTransportHttp alloc]
        initWithUrl:@"https://mcp.example.com"
        bearerTokenEnvironmentVariable:@"MCP_TOKEN"
        headers:headers
        environmentHeaders:environmentHeaders
        headersHelper:@"mcp-headers"];
    if (![http.url isEqualToString:@"https://mcp.example.com"] ||
        ![http.bearerTokenEnvironmentVariable isEqualToString:@"MCP_TOKEN"] ||
        ![http.headers isEqualToDictionary:headers] ||
        ![http.environmentHeaders isEqualToDictionary:environmentHeaders] ||
        ![http.headersHelper isEqualToString:@"mcp-headers"]) {
        return @"Objective-C D078 HTTP transport changed";
    }
    CodexAgentAgentMcpTransportHttp *defaultHttp = [[CodexAgentAgentMcpTransportHttp alloc]
        initWithUrl:@"https://default.example.com"
        bearerTokenEnvironmentVariable:nil
        headers:nil
        environmentHeaders:nil
        headersHelper:nil];
    if (defaultHttp.bearerTokenEnvironmentVariable != nil || defaultHttp.headers != nil ||
        defaultHttp.environmentHeaders != nil || defaultHttp.headersHelper != nil) {
        return @"Objective-C D078 HTTP transport defaults changed";
    }

    CodexAgentAgentMcpEnvironmentVariable *home =
        [[CodexAgentAgentMcpEnvironmentVariable alloc] initWithName:@"HOME" source:nil];
    CodexAgentAgentMcpEnvironmentVariable *remoteToken =
        [[CodexAgentAgentMcpEnvironmentVariable alloc]
            initWithName:@"REMOTE_TOKEN"
            source:[CodexAgentAgentMcpEnvironmentSource remote]];
    NSArray<NSString *> *arguments = @[@"server.js", @"--stdio"];
    NSDictionary<NSString *, NSString *> *environment = @{
        @"STATIC": @"value",
        @"MODE": @"test",
    };
    NSArray<CodexAgentAgentMcpEnvironmentVariable *> *forwardedEnvironment = @[home, remoteToken];
    CodexAgentAgentMcpTransportStdio *stdio = [[CodexAgentAgentMcpTransportStdio alloc]
        initWithCommand:@"node"
        arguments:arguments
        workingDirectory:@"/workspace"
        environment:environment
        forwardedEnvironment:forwardedEnvironment];
    if (![stdio.command isEqualToString:@"node"] ||
        ![stdio.arguments isEqualToArray:arguments] ||
        ![stdio.workingDirectory isEqualToString:@"/workspace"] ||
        ![stdio.environment isEqualToDictionary:environment] ||
        ![stdio.forwardedEnvironment isEqualToArray:forwardedEnvironment] ||
        stdio.forwardedEnvironment[0] != home || stdio.forwardedEnvironment[1] != remoteToken) {
        return @"Objective-C D078 stdio transport changed";
    }
    CodexAgentAgentMcpTransportStdio *defaultStdio = [[CodexAgentAgentMcpTransportStdio alloc]
        initWithCommand:@"mcp"
        arguments:@[]
        workingDirectory:nil
        environment:nil
        forwardedEnvironment:@[]];
    if (defaultStdio.arguments.count != 0 || defaultStdio.workingDirectory != nil ||
        defaultStdio.environment != nil || defaultStdio.forwardedEnvironment.count != 0) {
        return @"Objective-C D078 stdio transport defaults changed";
    }

    CodexAgentAgentMcpAuthentication *authentication = [CodexAgentAgentMcpAuthentication chatGpt];
    CodexAgentAgentMcpToolExposureSurface *codeMode =
        [CodexAgentAgentMcpToolExposureSurface codeMode];
    CodexAgentAgentMcpToolExposureSurface *deferred =
        [CodexAgentAgentMcpToolExposureSurface deferred];
    NSArray<CodexAgentAgentMcpToolExposureSurface *> *omitToolsFrom = @[codeMode, deferred];
    CodexAgentDouble *startupTimeout = [CodexAgentDouble numberWithDouble:3.5];
    CodexAgentDouble *toolTimeout = [CodexAgentDouble numberWithDouble:9.0];
    CodexAgentAgentMcpToolApproval *writes = [CodexAgentAgentMcpToolApproval writes];
    NSArray<NSString *> *enabledTools = @[@"read", @"search"];
    NSArray<NSString *> *disabledTools = @[@"write"];
    NSArray<NSString *> *scopes = @[@"files.read", @"files.write"];
    CodexAgentInt *callbackPort = [CodexAgentInt numberWithInt:9876];
    CodexAgentAgentMcpOauthConfiguration *oauth =
        [[CodexAgentAgentMcpOauthConfiguration alloc]
            initWithClientId:@"client"
            callbackPort:callbackPort];
    CodexAgentAgentMcpToolConfiguration *readTool =
        [[CodexAgentAgentMcpToolConfiguration alloc]
            initWithApproval:[CodexAgentAgentMcpToolApproval prompt]];
    CodexAgentAgentMcpToolConfiguration *writeTool =
        [[CodexAgentAgentMcpToolConfiguration alloc]
            initWithApproval:[CodexAgentAgentMcpToolApproval approve]];
    NSDictionary<NSString *, CodexAgentAgentMcpToolConfiguration *> *tools = @{
        @"read": readTool,
        @"write": writeTool,
    };
    CodexAgentAgentMcpServerConfiguration *configuration =
        [[CodexAgentAgentMcpServerConfiguration alloc]
            initWithName:@"remote-mcp"
            transport:http
            authentication:authentication
            environmentId:@"local"
            isEnabled:NO
            isRequired:YES
            supportsParallelToolCalls:YES
            omitToolsFrom:omitToolsFrom
            startupTimeoutSeconds:startupTimeout
            toolTimeoutSeconds:toolTimeout
            defaultToolApproval:writes
            enabledTools:enabledTools
            disabledTools:disabledTools
            scopes:scopes
            oauth:oauth
            oauthResource:@"https://mcp.example.com/resource"
            tools:tools];
    id<CodexAgentAgentMcpTransport> returnedTransport = configuration.transport;
    NSDictionary<NSString *, CodexAgentAgentMcpToolConfiguration *> *returnedTools =
        configuration.tools;
    if (![configuration.name isEqualToString:@"remote-mcp"] || returnedTransport != http ||
        ![(id)returnedTransport isKindOfClass:[CodexAgentAgentMcpTransportHttp class]] ||
        configuration.authentication != authentication ||
        ![configuration.environmentId isEqualToString:@"local"] || configuration.isEnabled ||
        !configuration.isRequired || !configuration.supportsParallelToolCalls ||
        ![configuration.omitToolsFrom isEqualToArray:omitToolsFrom] ||
        configuration.omitToolsFrom[0] != codeMode || configuration.omitToolsFrom[1] != deferred ||
        configuration.startupTimeoutSeconds.doubleValue != 3.5 ||
        configuration.toolTimeoutSeconds.doubleValue != 9.0 ||
        configuration.defaultToolApproval != writes ||
        ![configuration.enabledTools isEqualToArray:enabledTools] ||
        ![configuration.disabledTools isEqualToArray:disabledTools] ||
        ![configuration.scopes isEqualToArray:scopes] || configuration.oauth != oauth ||
        configuration.oauth.callbackPort.intValue != 9876 ||
        ![configuration.oauthResource isEqualToString:@"https://mcp.example.com/resource"] ||
        ![returnedTools isEqualToDictionary:tools] || returnedTools[@"read"] != readTool ||
        returnedTools[@"write"] != writeTool ||
        readTool.approval != [CodexAgentAgentMcpToolApproval prompt] ||
        writeTool.approval != [CodexAgentAgentMcpToolApproval approve]) {
        return @"Objective-C D078 MCP server configuration changed";
    }

    CodexAgentAgentMcpServerConfiguration *defaults =
        [[CodexAgentAgentMcpServerConfiguration alloc]
            initWithName:@"defaults"
            transport:defaultHttp
            authentication:nil
            environmentId:@"local"
            isEnabled:YES
            isRequired:NO
            supportsParallelToolCalls:NO
            omitToolsFrom:nil
            startupTimeoutSeconds:nil
            toolTimeoutSeconds:nil
            defaultToolApproval:nil
            enabledTools:nil
            disabledTools:nil
            scopes:nil
            oauth:nil
            oauthResource:nil
            tools:@{}];
    if (defaults.authentication != nil || ![defaults.environmentId isEqualToString:@"local"] ||
        !defaults.isEnabled || defaults.isRequired || defaults.supportsParallelToolCalls ||
        defaults.omitToolsFrom != nil || defaults.startupTimeoutSeconds != nil ||
        defaults.toolTimeoutSeconds != nil || defaults.defaultToolApproval != nil ||
        defaults.enabledTools != nil || defaults.disabledTools != nil || defaults.scopes != nil ||
        defaults.oauth != nil || defaults.oauthResource != nil || defaults.tools.count != 0) {
        return @"Objective-C D078 MCP server configuration defaults changed";
    }

    CodexAgentAgentFormValueText *text =
        [[CodexAgentAgentFormValueText alloc] initWithValue:@"Ada"];
    CodexAgentAgentFormValueNumber *number =
        [[CodexAgentAgentFormValueNumber alloc] initWithValue:7.5];
    CodexAgentAgentFormValueBooleanValue *boolean =
        [[CodexAgentAgentFormValueBooleanValue alloc] initWithValue:YES];
    CodexAgentAgentFormValueTextList *list =
        [[CodexAgentAgentFormValueTextList alloc] initWithValue:@[@"first", @"second"]];
    NSDictionary<NSString *, id<CodexAgentAgentFormValue>> *content = @{
        @"name": text,
        @"score": number,
        @"enabled": boolean,
        @"choices": list,
    };
    CodexAgentAgentElicitationAction *accept = [CodexAgentAgentElicitationAction accept];
    CodexAgentAgentElicitationResponse *response = [[CodexAgentAgentElicitationResponse alloc]
        initWithAction:accept
        content:content];
    NSDictionary<NSString *, id<CodexAgentAgentFormValue>> *returnedContent = response.content;
    if (response.action != accept || ![returnedContent isEqualToDictionary:content] ||
        returnedContent[@"name"] != text || returnedContent[@"score"] != number ||
        returnedContent[@"enabled"] != boolean || returnedContent[@"choices"] != list ||
        ![(id)returnedContent[@"name"] isKindOfClass:[CodexAgentAgentFormValueText class]] ||
        ![(id)returnedContent[@"score"] isKindOfClass:[CodexAgentAgentFormValueNumber class]] ||
        ![(id)returnedContent[@"enabled"] isKindOfClass:[CodexAgentAgentFormValueBooleanValue class]] ||
        ![(id)returnedContent[@"choices"] isKindOfClass:[CodexAgentAgentFormValueTextList class]] ||
        ![text.value isEqualToString:@"Ada"] || number.value != 7.5 || !boolean.value ||
        ![list.value isEqualToArray:@[@"first", @"second"]]) {
        return @"Objective-C D078 elicitation response changed";
    }
    CodexAgentAgentElicitationResponse *emptyResponse = [[CodexAgentAgentElicitationResponse alloc]
        initWithAction:accept
        content:@{}];
    if (emptyResponse.content.count != 0) {
        return @"Objective-C D078 elicitation response default content changed";
    }

    return nil;
}

static NSString *CDXVerifyD079ConversationValues(void) {
    CodexAgentConversationId *conversationId = [[CodexAgentConversationId alloc]
        initWithValue:@"d079-conversation"];
    CodexAgentAgentConversationSummary *summary = [[CodexAgentAgentConversationSummary alloc]
        initWithConversationId:conversationId
        title:@"D079 conversation"
        updatedAtEpochSeconds:79];
    CodexAgentAgentInvocationPlugin *pluginInvocation =
        [[CodexAgentAgentInvocationPlugin alloc]
            initWithName:@"review-plugin"
            uri:@"plugin://review-plugin@marketplace"];
    CodexAgentAgentInvocationSkill *skillInvocation =
        [[CodexAgentAgentInvocationSkill alloc]
            initWithName:@"review-skill"
            path:@"/skills/review/SKILL.md"];
    NSArray<id<CodexAgentAgentInvocation>> *invocations = @[pluginInvocation, skillInvocation];
    CodexAgentAgentCapability *webSearch = [CodexAgentAgentCapability webSearch];
    NSSet<CodexAgentAgentCapability *> *capabilities = [NSSet setWithObject:webSearch];
    CodexAgentInt *exitCode = [CodexAgentInt numberWithInt:7];
    CodexAgentAgentMessage *message = [[CodexAgentAgentMessage alloc]
        initWithId:@"d079-message"
        clientMessageId:@"d079-client-message"
        role:[CodexAgentAgentMessageRole assistant]
        text:@"D079 complete"
        collaborationMode:[CodexAgentAgentCollaborationMode plan]
        reasoning:@"Checked every value"
        plan:@"Ship D079"
        shellCommand:@"echo d079"
        exitCode:exitCode
        capabilities:capabilities
        invocations:invocations];
    if (![message.id isEqualToString:@"d079-message"] ||
        ![message.clientMessageId isEqualToString:@"d079-client-message"] ||
        message.role != [CodexAgentAgentMessageRole assistant] ||
        ![message.text isEqualToString:@"D079 complete"] ||
        message.collaborationMode != [CodexAgentAgentCollaborationMode plan] ||
        ![message.reasoning isEqualToString:@"Checked every value"] ||
        ![message.plan isEqualToString:@"Ship D079"] ||
        ![message.shellCommand isEqualToString:@"echo d079"] ||
        message.exitCode == nil || message.exitCode.intValue != 7 ||
        message.capabilities.count != 1 || ![message.capabilities containsObject:webSearch] ||
        message.invocations.count != 2 || message.invocations[0] != pluginInvocation ||
        message.invocations[1] != skillInvocation) {
        return @"Objective-C D079 rich message changed";
    }
    CodexAgentAgentInvocationPlugin *returnedPlugin =
        (CodexAgentAgentInvocationPlugin *)message.invocations[0];
    CodexAgentAgentInvocationSkill *returnedSkill =
        (CodexAgentAgentInvocationSkill *)message.invocations[1];
    if (![(id)returnedPlugin isKindOfClass:[CodexAgentAgentInvocationPlugin class]] ||
        ![(id)returnedSkill isKindOfClass:[CodexAgentAgentInvocationSkill class]] ||
        returnedPlugin != pluginInvocation || returnedSkill != skillInvocation) {
        return @"Objective-C D079 invocation projection changed";
    }

    NSSet<CodexAgentAgentCapability *> *emptyCapabilities = [NSSet set];
    NSArray<id<CodexAgentAgentInvocation>> *emptyInvocations = @[];
    CodexAgentAgentMessage *defaultMessage = [[CodexAgentAgentMessage alloc]
        initWithId:@"d079-default-message"
        clientMessageId:nil
        role:[CodexAgentAgentMessageRole user]
        text:@"Default message"
        collaborationMode:[CodexAgentAgentCollaborationMode default_]
        reasoning:nil
        plan:nil
        shellCommand:nil
        exitCode:nil
        capabilities:emptyCapabilities
        invocations:emptyInvocations];
    if (defaultMessage.clientMessageId != nil ||
        defaultMessage.collaborationMode != [CodexAgentAgentCollaborationMode default_] ||
        defaultMessage.reasoning != nil || defaultMessage.plan != nil ||
        defaultMessage.shellCommand != nil || defaultMessage.exitCode != nil ||
        defaultMessage.capabilities.count != 0 || defaultMessage.invocations.count != 0) {
        return @"Objective-C D079 message defaults changed";
    }

    CodexAgentAgentTurnRequest *request = [[CodexAgentAgentTurnRequest alloc]
        initWithPrompt:@"Review D079"
        clientMessageId:@"d079-request"
        model:@"codex-model"
        effort:@"high"
        serviceTier:@"fast"
        approvalPreset:[CodexAgentAgentApprovalPreset strict]
        capabilities:capabilities
        invocations:invocations
        collaborationMode:[CodexAgentAgentCollaborationMode plan]];
    if (![request.prompt isEqualToString:@"Review D079"] ||
        ![request.clientMessageId isEqualToString:@"d079-request"] ||
        ![request.model isEqualToString:@"codex-model"] ||
        ![request.effort isEqualToString:@"high"] ||
        ![request.serviceTier isEqualToString:@"fast"] ||
        request.approvalPreset != [CodexAgentAgentApprovalPreset strict] ||
        request.capabilities.count != 1 || ![request.capabilities containsObject:webSearch] ||
        request.invocations.count != 2 || request.invocations[0] != pluginInvocation ||
        request.invocations[1] != skillInvocation ||
        request.collaborationMode != [CodexAgentAgentCollaborationMode plan]) {
        return @"Objective-C D079 rich turn request changed";
    }

    CodexAgentAgentTurnRequest *defaultRequest = [[CodexAgentAgentTurnRequest alloc]
        initWithPrompt:@"Default request"
        clientMessageId:nil
        model:nil
        effort:nil
        serviceTier:nil
        approvalPreset:[CodexAgentAgentApprovalPreset autoReview]
        capabilities:emptyCapabilities
        invocations:emptyInvocations
        collaborationMode:[CodexAgentAgentCollaborationMode default_]];
    if (![defaultRequest.prompt isEqualToString:@"Default request"] ||
        defaultRequest.clientMessageId != nil || defaultRequest.model != nil ||
        defaultRequest.effort != nil || defaultRequest.serviceTier != nil ||
        defaultRequest.approvalPreset != [CodexAgentAgentApprovalPreset autoReview] ||
        defaultRequest.capabilities.count != 0 || defaultRequest.invocations.count != 0 ||
        defaultRequest.collaborationMode != [CodexAgentAgentCollaborationMode default_]) {
        return @"Objective-C D079 turn-request defaults changed";
    }

    NSArray<CodexAgentAgentMessage *> *messages = @[message, defaultMessage];
    CodexAgentAgentConversation *conversation = [[CodexAgentAgentConversation alloc]
        initWithSummary:summary
        messages:messages];
    if (conversation.summary != summary || conversation.messages.count != 2 ||
        ![conversation.messages isEqualToArray:messages] ||
        conversation.messages[0] != message || conversation.messages[1] != defaultMessage) {
        return @"Objective-C D079 conversation projection changed";
    }

    return nil;
}

static NSString *CDXVerifyD080StateValues(void) {
    CodexAgentCodexFailure *recoverableFailure = [[CodexAgentCodexFailure alloc]
        initWithCode:@"d080-recoverable"
        message:@"Retry D080"
        isRecoverable:YES];
    CodexAgentCodexFailure *terminalFailure = [[CodexAgentCodexFailure alloc]
        initWithCode:@"d080-terminal"
        message:@"Stop D080"
        isRecoverable:NO];
    CodexAgentCodexAuthorizationUrlCompanion *urlCompanion =
        [CodexAgentCodexAuthorizationUrl companion];
    CodexAgentCodexAuthorizationUrl *pendingSignInUrl =
        [urlCompanion externalValue:@"https://example.com/d080/sign-in"];
    CodexAgentCodexAuthorizationUrl *deviceVerificationUrl =
        [urlCompanion chatGptValue:@"https://auth.openai.com/d080/device"];

    CodexAgentAgentAuthenticationState *authentication =
        [[CodexAgentAgentAuthenticationState alloc]
            initWithStatus:[CodexAgentAgentAuthenticationStatus authenticating]
            pendingSignInUrl:pendingSignInUrl
            deviceVerificationUrl:deviceVerificationUrl
            deviceUserCode:@"D080-CODE"
            failure:recoverableFailure];
    if (authentication.status != [CodexAgentAgentAuthenticationStatus authenticating] ||
        authentication.pendingSignInUrl != pendingSignInUrl ||
        authentication.deviceVerificationUrl != deviceVerificationUrl ||
        ![authentication.deviceUserCode isEqualToString:@"D080-CODE"] ||
        authentication.failure != recoverableFailure) {
        return @"Objective-C D080 authentication state changed";
    }
    CodexAgentAgentAuthenticationState *defaultAuthentication =
        [[CodexAgentAgentAuthenticationState alloc]
            initWithStatus:[CodexAgentAgentAuthenticationStatus signedOut]
            pendingSignInUrl:nil
            deviceVerificationUrl:nil
            deviceUserCode:nil
            failure:nil];
    if (defaultAuthentication.status != [CodexAgentAgentAuthenticationStatus signedOut] ||
        defaultAuthentication.pendingSignInUrl != nil ||
        defaultAuthentication.deviceVerificationUrl != nil ||
        defaultAuthentication.deviceUserCode != nil || defaultAuthentication.failure != nil) {
        return @"Objective-C D080 authentication defaults changed";
    }

    CodexAgentConversationId *conversationId = [[CodexAgentConversationId alloc]
        initWithValue:@"d080-conversation"];
    CodexAgentAgentConversationSummary *summary = [[CodexAgentAgentConversationSummary alloc]
        initWithConversationId:conversationId
        title:@"D080 conversation"
        updatedAtEpochSeconds:80];
    CodexAgentAgentConversation *conversation = [[CodexAgentAgentConversation alloc]
        initWithSummary:summary
        messages:@[]];
    CodexAgentAgentTurnProgress *turnProgress = [[CodexAgentAgentTurnProgress alloc]
        initWithText:@"D080 text"
        commentary:@"D080 commentary"
        reasoning:nil
        plan:nil
        planProgress:nil
        shellOutput:nil
        shellExitCode:nil
        workActivity:nil
        hookActivities:@[]
        isTruncated:NO];
    CodexAgentAgentConversationState *readyState =
        [[CodexAgentAgentConversationState alloc]
            initWithStatus:[CodexAgentAgentConversationStatus ready]
            conversationId:conversationId
            conversation:conversation
            turnProgress:turnProgress
            model:@"d080-model"
            effort:@"high"
            serviceTier:@"fast"
            failure:recoverableFailure];
    if (readyState.status != [CodexAgentAgentConversationStatus ready] ||
        readyState.conversationId != conversationId || readyState.conversation != conversation ||
        readyState.turnProgress != turnProgress ||
        ![readyState.model isEqualToString:@"d080-model"] ||
        ![readyState.effort isEqualToString:@"high"] ||
        ![readyState.serviceTier isEqualToString:@"fast"] ||
        readyState.failure != recoverableFailure || !readyState.canStartTurn ||
        !readyState.canReload || readyState.canCancelTurn) {
        return @"Objective-C D080 rich conversation state changed";
    }

    CodexAgentAgentTurnProgress *defaultTurnProgress = [[CodexAgentAgentTurnProgress alloc]
        initWithText:nil
        commentary:nil
        reasoning:nil
        plan:nil
        planProgress:nil
        shellOutput:nil
        shellExitCode:nil
        workActivity:nil
        hookActivities:@[]
        isTruncated:NO];
    CodexAgentAgentConversationState *defaultConversationState =
        [[CodexAgentAgentConversationState alloc]
            initWithStatus:[CodexAgentAgentConversationStatus theNew]
            conversationId:nil
            conversation:nil
            turnProgress:defaultTurnProgress
            model:nil
            effort:nil
            serviceTier:nil
            failure:nil];
    if (defaultConversationState.status != [CodexAgentAgentConversationStatus theNew] ||
        defaultConversationState.conversationId != nil ||
        defaultConversationState.conversation != nil ||
        defaultConversationState.turnProgress != defaultTurnProgress ||
        defaultConversationState.model != nil || defaultConversationState.effort != nil ||
        defaultConversationState.serviceTier != nil || defaultConversationState.failure != nil ||
        defaultConversationState.canStartTurn || defaultConversationState.canReload ||
        defaultConversationState.canCancelTurn) {
        return @"Objective-C D080 conversation defaults changed";
    }

    CodexAgentAgentConversationState *readyWithoutId =
        [[CodexAgentAgentConversationState alloc]
            initWithStatus:[CodexAgentAgentConversationStatus ready]
            conversationId:nil
            conversation:nil
            turnProgress:defaultTurnProgress
            model:nil
            effort:nil
            serviceTier:nil
            failure:nil];
    CodexAgentAgentConversationState *recoverableFailed =
        [[CodexAgentAgentConversationState alloc]
            initWithStatus:[CodexAgentAgentConversationStatus failed]
            conversationId:conversationId
            conversation:nil
            turnProgress:defaultTurnProgress
            model:nil
            effort:nil
            serviceTier:nil
            failure:recoverableFailure];
    CodexAgentAgentConversationState *terminalFailed =
        [[CodexAgentAgentConversationState alloc]
            initWithStatus:[CodexAgentAgentConversationStatus failed]
            conversationId:conversationId
            conversation:nil
            turnProgress:defaultTurnProgress
            model:nil
            effort:nil
            serviceTier:nil
            failure:terminalFailure];
    CodexAgentAgentConversationState *failureMissing =
        [[CodexAgentAgentConversationState alloc]
            initWithStatus:[CodexAgentAgentConversationStatus failed]
            conversationId:conversationId
            conversation:nil
            turnProgress:defaultTurnProgress
            model:nil
            effort:nil
            serviceTier:nil
            failure:nil];
    CodexAgentAgentConversationState *starting =
        [[CodexAgentAgentConversationState alloc]
            initWithStatus:[CodexAgentAgentConversationStatus startingTurn]
            conversationId:conversationId
            conversation:nil
            turnProgress:defaultTurnProgress
            model:nil
            effort:nil
            serviceTier:nil
            failure:nil];
    CodexAgentAgentConversationState *running =
        [[CodexAgentAgentConversationState alloc]
            initWithStatus:[CodexAgentAgentConversationStatus runningTurn]
            conversationId:conversationId
            conversation:nil
            turnProgress:defaultTurnProgress
            model:nil
            effort:nil
            serviceTier:nil
            failure:nil];
    if (readyWithoutId.canStartTurn || readyWithoutId.canReload ||
        readyWithoutId.canCancelTurn || !recoverableFailed.canStartTurn ||
        !recoverableFailed.canReload || recoverableFailed.canCancelTurn ||
        terminalFailed.canStartTurn || !terminalFailed.canReload ||
        terminalFailed.canCancelTurn || failureMissing.canStartTurn ||
        !failureMissing.canReload || failureMissing.canCancelTurn ||
        starting.canStartTurn || starting.canReload || !starting.canCancelTurn ||
        running.canStartTurn || running.canReload || !running.canCancelTurn) {
        return @"Objective-C D080 conversation capability matrix changed";
    }

    CodexAgentAgentConnector *connector = [[CodexAgentAgentConnector alloc]
        initWithId:@"d080-connector"
        name:@"D080 Connector"
        description:nil
        installUrl:nil
        isAccessible:YES
        isEnabled:YES
        pluginNames:@[]];
    CodexAgentAgentIntegrationConnector *integration =
        [[CodexAgentAgentIntegrationConnector alloc] initWithConnector:connector];
    CodexAgentAgentIntegrationAuthorizationState *integrationState =
        [[CodexAgentAgentIntegrationAuthorizationState alloc]
            initWithStatus:[CodexAgentAgentIntegrationAuthorizationStatus starting]
            target:integration
            failure:recoverableFailure];
    id<CodexAgentAgentIntegration> returnedTarget = integrationState.target;
    CodexAgentAgentIntegrationConnector *returnedIntegration =
        (CodexAgentAgentIntegrationConnector *)returnedTarget;
    if (integrationState.status != [CodexAgentAgentIntegrationAuthorizationStatus starting] ||
        integrationState.failure != recoverableFailure || returnedTarget != integration ||
        ![(id)returnedTarget isKindOfClass:[CodexAgentAgentIntegrationConnector class]] ||
        returnedIntegration != integration || returnedIntegration.connector != connector) {
        return @"Objective-C D080 integration authorization state changed";
    }
    CodexAgentAgentIntegrationAuthorizationState *defaultIntegrationState =
        [[CodexAgentAgentIntegrationAuthorizationState alloc]
            initWithStatus:[CodexAgentAgentIntegrationAuthorizationStatus idle]
            target:nil
            failure:nil];
    if (defaultIntegrationState.status != [CodexAgentAgentIntegrationAuthorizationStatus idle] ||
        defaultIntegrationState.target != nil || defaultIntegrationState.failure != nil) {
        return @"Objective-C D080 integration authorization defaults changed";
    }

    CodexAgentConversationId *otherConversationId = [[CodexAgentConversationId alloc]
        initWithValue:@"d080-other-conversation"];
    CodexAgentAgentPendingApproval *approval = [[CodexAgentAgentPendingApproval alloc]
        initWithRequestId:@"d080-approval"
        conversationId:conversationId
        title:@"Approve D080"
        details:nil];
    CodexAgentAgentElicitation *elicitation = [[CodexAgentAgentElicitation alloc]
        initWithRequestId:@"d080-elicitation"
        serverName:@"d080-server"
        conversationId:conversationId
        message:@"Provide D080 input"
        form:nil
        url:nil];
    CodexAgentAgentPendingElicitation *pendingElicitation =
        [[CodexAgentAgentPendingElicitation alloc] initWithElicitation:elicitation];
    CodexAgentAgentPendingApproval *otherApproval = [[CodexAgentAgentPendingApproval alloc]
        initWithRequestId:@"d080-other-approval"
        conversationId:otherConversationId
        title:@"Approve other"
        details:nil];
    CodexAgentAgentPendingApproval *sameRequestDifferentInstance =
        [[CodexAgentAgentPendingApproval alloc]
            initWithRequestId:@"d080-approval"
            conversationId:conversationId
            title:@"Not owned"
            details:nil];
    CodexAgentAgentPendingApproval *unresolvedDetached =
        [[CodexAgentAgentPendingApproval alloc]
            initWithRequestId:@"d080-detached"
            conversationId:conversationId
            title:@"Detached"
            details:nil];
    NSArray<id<CodexAgentAgentPendingInteraction>> *pending =
        @[approval, pendingElicitation, otherApproval];
    NSSet<NSString *> *resolvingRequestIds = [NSSet setWithObjects:@"d080-approval", nil];
    CodexAgentAgentInteractionState *interactionState = [[CodexAgentAgentInteractionState alloc]
        initWithPending:pending
        resolvingRequestIds:resolvingRequestIds
        failure:recoverableFailure];
    if (interactionState.failure != recoverableFailure || interactionState.pending.count != 3 ||
        interactionState.pending[0] != approval ||
        interactionState.pending[1] != pendingElicitation ||
        interactionState.pending[2] != otherApproval ||
        interactionState.resolvingRequestIds.count != 1 ||
        ![interactionState.resolvingRequestIds containsObject:@"d080-approval"]) {
        return @"Objective-C D080 interaction state changed";
    }
    NSArray<id<CodexAgentAgentPendingInteraction>> *conversationPending =
        [interactionState pendingForConversationId:conversationId];
    NSArray<id<CodexAgentAgentPendingInteraction>> *otherPending =
        [interactionState pendingForConversationId:otherConversationId];
    CodexAgentConversationId *missingConversationId = [[CodexAgentConversationId alloc]
        initWithValue:@"d080-missing-conversation"];
    NSArray<id<CodexAgentAgentPendingInteraction>> *missingPending =
        [interactionState pendingForConversationId:missingConversationId];
    CodexAgentAgentPendingApproval *returnedApproval =
        (CodexAgentAgentPendingApproval *)conversationPending[0];
    CodexAgentAgentPendingElicitation *returnedElicitation =
        (CodexAgentAgentPendingElicitation *)conversationPending[1];
    CodexAgentAgentPendingApproval *returnedOtherApproval =
        (CodexAgentAgentPendingApproval *)otherPending[0];
    if (conversationPending.count != 2 || conversationPending[0] != approval ||
        conversationPending[1] != pendingElicitation || otherPending.count != 1 ||
        otherPending[0] != otherApproval || missingPending.count != 0 ||
        ![(id)returnedApproval isKindOfClass:[CodexAgentAgentPendingApproval class]] ||
        ![(id)returnedElicitation isKindOfClass:[CodexAgentAgentPendingElicitation class]] ||
        ![(id)returnedOtherApproval isKindOfClass:[CodexAgentAgentPendingApproval class]] ||
        returnedApproval != approval || returnedElicitation != pendingElicitation ||
        returnedOtherApproval != otherApproval) {
        return @"Objective-C D080 pending filtering changed";
    }
    if (![interactionState isResolvingInteraction:approval] ||
        [interactionState isResolvingInteraction:sameRequestDifferentInstance] ||
        [interactionState isResolvingInteraction:pendingElicitation] ||
        [interactionState isResolvingInteraction:unresolvedDetached]) {
        return @"Objective-C D080 resolving identity matrix changed";
    }
    CodexAgentAgentInteractionState *defaultInteractionState =
        [[CodexAgentAgentInteractionState alloc]
            initWithPending:@[]
            resolvingRequestIds:[NSSet set]
            failure:nil];
    if (defaultInteractionState.pending.count != 0 ||
        defaultInteractionState.resolvingRequestIds.count != 0 ||
        defaultInteractionState.failure != nil ||
        [defaultInteractionState isResolvingInteraction:approval] ||
        [defaultInteractionState pendingForConversationId:conversationId].count != 0) {
        return @"Objective-C D080 interaction defaults changed";
    }

    return nil;
}

static NSString *CDXVerifyD081SingletonObjects(void) {
    CodexAgentAgentHookHandlerAgent *agentHandlerFirst =
        [CodexAgentAgentHookHandlerAgent shared];
    CodexAgentAgentHookHandlerAgent *agentHandlerSecond =
        [CodexAgentAgentHookHandlerAgent shared];
    CodexAgentAgentHookHandlerPrompt *promptHandlerFirst =
        [CodexAgentAgentHookHandlerPrompt shared];
    CodexAgentAgentHookHandlerPrompt *promptHandlerSecond =
        [CodexAgentAgentHookHandlerPrompt shared];
    if (agentHandlerFirst == nil || agentHandlerSecond == nil || promptHandlerFirst == nil ||
        promptHandlerSecond == nil || ![agentHandlerFirst isEqual:agentHandlerSecond] ||
        ![promptHandlerFirst isEqual:promptHandlerSecond] ||
        [agentHandlerFirst isEqual:promptHandlerFirst]) {
        return @"Objective-C D081 hook-handler singleton identity changed";
    }

    CodexAgentCodexAuthenticationMethodChatGptBrowser *browserFirst =
        [CodexAgentCodexAuthenticationMethodChatGptBrowser shared];
    CodexAgentCodexAuthenticationMethodChatGptBrowser *browserSecond =
        [CodexAgentCodexAuthenticationMethodChatGptBrowser shared];
    CodexAgentCodexAuthenticationMethodChatGptDeviceCode *deviceCodeFirst =
        [CodexAgentCodexAuthenticationMethodChatGptDeviceCode shared];
    CodexAgentCodexAuthenticationMethodChatGptDeviceCode *deviceCodeSecond =
        [CodexAgentCodexAuthenticationMethodChatGptDeviceCode shared];
    if (browserFirst == nil || browserSecond == nil || deviceCodeFirst == nil ||
        deviceCodeSecond == nil || ![browserFirst isEqual:browserSecond] ||
        ![deviceCodeFirst isEqual:deviceCodeSecond] || [browserFirst isEqual:deviceCodeFirst]) {
        return @"Objective-C D081 authentication-method singleton identity changed";
    }

    CodexAgentCodexHostStateClosed *closedFirst = [CodexAgentCodexHostStateClosed shared];
    CodexAgentCodexHostStateClosed *closedSecond = [CodexAgentCodexHostStateClosed shared];
    CodexAgentCodexHostStateNew *newFirst = [CodexAgentCodexHostStateNew shared];
    CodexAgentCodexHostStateNew *newSecond = [CodexAgentCodexHostStateNew shared];
    CodexAgentCodexHostStateRestoring *restoringFirst =
        [CodexAgentCodexHostStateRestoring shared];
    CodexAgentCodexHostStateRestoring *restoringSecond =
        [CodexAgentCodexHostStateRestoring shared];
    if (closedFirst == nil || closedSecond == nil || newFirst == nil || newSecond == nil ||
        restoringFirst == nil || restoringSecond == nil ||
        ![closedFirst isEqual:closedSecond] || ![newFirst isEqual:newSecond] ||
        ![restoringFirst isEqual:restoringSecond] || [closedFirst isEqual:newFirst] ||
        [closedFirst isEqual:restoringFirst] || [newFirst isEqual:restoringFirst]) {
        return @"Objective-C D081 host-state singleton identity changed";
    }

    return nil;
}

static NSString *CDXVerifyD082ElicitationHelpers(
    CodexAgentAgentElicitationResponseCompanion *companion
) {
    CodexAgentConversationId *conversationId = [[CodexAgentConversationId alloc]
        initWithValue:@"d082-conversation"];
    CodexAgentAgentFormOption *optionA = [[CodexAgentAgentFormOption alloc]
        initWithValue:@"a" title:@"A" description:nil];
    CodexAgentAgentFormOption *optionB = [[CodexAgentAgentFormOption alloc]
        initWithValue:@"b" title:@"B" description:nil];
    CodexAgentAgentFormOption *optionC = [[CodexAgentAgentFormOption alloc]
        initWithValue:@"c" title:@"C" description:nil];
    NSArray<CodexAgentAgentFormOption *> *options = @[optionA, optionB, optionC];
    CodexAgentLong *minimumNameLength = [CodexAgentLong numberWithLongLong:2];
    CodexAgentLong *maximumNameLength = [CodexAgentLong numberWithLongLong:4];
    CodexAgentDouble *minimumNumber = [CodexAgentDouble numberWithDouble:0.0];
    CodexAgentDouble *maximumNumber = [CodexAgentDouble numberWithDouble:1.0];
    CodexAgentDouble *minimumInteger = [CodexAgentDouble numberWithDouble:1.0];
    CodexAgentDouble *maximumInteger = [CodexAgentDouble numberWithDouble:3.0];
    CodexAgentLong *minimumSelections = [CodexAgentLong numberWithLongLong:1];
    CodexAgentLong *maximumSelections = [CodexAgentLong numberWithLongLong:2];
    NSMutableArray<NSString *> *defaultSelections = [NSMutableArray arrayWithObject:@"a"];
    CodexAgentAgentFormValueNumber *defaultCount =
        [[CodexAgentAgentFormValueNumber alloc] initWithValue:2.0];
    CodexAgentAgentFormValueTextList *defaultManyValue =
        [[CodexAgentAgentFormValueTextList alloc] initWithValue:defaultSelections];

    CodexAgentAgentFormField *name = [[CodexAgentAgentFormField alloc]
        initWithName:@"name"
        title:@"Name"
        description:nil
        isRequired:YES
        type:[CodexAgentAgentFormFieldType string]
        options:@[]
        defaultValue:nil
        minimum:nil
        maximum:nil
        format:nil
        minimumLength:minimumNameLength
        maximumLength:maximumNameLength
        minimumSelections:nil
        maximumSelections:nil
        allowsOther:NO
        isSecret:NO];
    CodexAgentAgentFormField *email = [[CodexAgentAgentFormField alloc]
        initWithName:@"email"
        title:@"Email"
        description:nil
        isRequired:NO
        type:[CodexAgentAgentFormFieldType string]
        options:@[]
        defaultValue:nil
        minimum:nil
        maximum:nil
        format:[CodexAgentAgentFormStringFormat email]
        minimumLength:nil
        maximumLength:nil
        minimumSelections:nil
        maximumSelections:nil
        allowsOther:NO
        isSecret:NO];
    CodexAgentAgentFormField *uri = [[CodexAgentAgentFormField alloc]
        initWithName:@"uri"
        title:@"URI"
        description:nil
        isRequired:NO
        type:[CodexAgentAgentFormFieldType string]
        options:@[]
        defaultValue:nil
        minimum:nil
        maximum:nil
        format:[CodexAgentAgentFormStringFormat uri]
        minimumLength:nil
        maximumLength:nil
        minimumSelections:nil
        maximumSelections:nil
        allowsOther:NO
        isSecret:NO];
    CodexAgentAgentFormField *date = [[CodexAgentAgentFormField alloc]
        initWithName:@"date"
        title:@"Date"
        description:nil
        isRequired:NO
        type:[CodexAgentAgentFormFieldType string]
        options:@[]
        defaultValue:nil
        minimum:nil
        maximum:nil
        format:[CodexAgentAgentFormStringFormat date]
        minimumLength:nil
        maximumLength:nil
        minimumSelections:nil
        maximumSelections:nil
        allowsOther:NO
        isSecret:NO];
    CodexAgentAgentFormField *timestamp = [[CodexAgentAgentFormField alloc]
        initWithName:@"timestamp"
        title:@"Timestamp"
        description:nil
        isRequired:NO
        type:[CodexAgentAgentFormFieldType string]
        options:@[]
        defaultValue:nil
        minimum:nil
        maximum:nil
        format:[CodexAgentAgentFormStringFormat dateTime]
        minimumLength:nil
        maximumLength:nil
        minimumSelections:nil
        maximumSelections:nil
        allowsOther:NO
        isSecret:NO];
    CodexAgentAgentFormField *count = [[CodexAgentAgentFormField alloc]
        initWithName:@"count"
        title:@"Count"
        description:nil
        isRequired:NO
        type:[CodexAgentAgentFormFieldType integer]
        options:@[]
        defaultValue:defaultCount
        minimum:minimumInteger
        maximum:maximumInteger
        format:nil
        minimumLength:nil
        maximumLength:nil
        minimumSelections:nil
        maximumSelections:nil
        allowsOther:NO
        isSecret:NO];
    CodexAgentAgentFormField *ratio = [[CodexAgentAgentFormField alloc]
        initWithName:@"ratio"
        title:@"Ratio"
        description:nil
        isRequired:NO
        type:[CodexAgentAgentFormFieldType number]
        options:@[]
        defaultValue:nil
        minimum:minimumNumber
        maximum:maximumNumber
        format:nil
        minimumLength:nil
        maximumLength:nil
        minimumSelections:nil
        maximumSelections:nil
        allowsOther:NO
        isSecret:NO];
    CodexAgentAgentFormField *enabled = [[CodexAgentAgentFormField alloc]
        initWithName:@"enabled"
        title:@"Enabled"
        description:nil
        isRequired:NO
        type:[CodexAgentAgentFormFieldType boolean]
        options:@[]
        defaultValue:nil
        minimum:nil
        maximum:nil
        format:nil
        minimumLength:nil
        maximumLength:nil
        minimumSelections:nil
        maximumSelections:nil
        allowsOther:NO
        isSecret:NO];
    CodexAgentAgentFormField *choice = [[CodexAgentAgentFormField alloc]
        initWithName:@"choice"
        title:@"Choice"
        description:nil
        isRequired:NO
        type:[CodexAgentAgentFormFieldType singleSelect]
        options:options
        defaultValue:nil
        minimum:nil
        maximum:nil
        format:nil
        minimumLength:nil
        maximumLength:nil
        minimumSelections:nil
        maximumSelections:nil
        allowsOther:NO
        isSecret:NO];
    CodexAgentAgentFormField *otherChoice = [[CodexAgentAgentFormField alloc]
        initWithName:@"other"
        title:@"Other"
        description:nil
        isRequired:NO
        type:[CodexAgentAgentFormFieldType singleSelect]
        options:@[optionA]
        defaultValue:nil
        minimum:nil
        maximum:nil
        format:nil
        minimumLength:nil
        maximumLength:nil
        minimumSelections:nil
        maximumSelections:nil
        allowsOther:YES
        isSecret:NO];
    CodexAgentAgentFormField *many = [[CodexAgentAgentFormField alloc]
        initWithName:@"many"
        title:@"Many"
        description:nil
        isRequired:NO
        type:[CodexAgentAgentFormFieldType multiSelect]
        options:options
        defaultValue:nil
        minimum:nil
        maximum:nil
        format:nil
        minimumLength:nil
        maximumLength:nil
        minimumSelections:minimumSelections
        maximumSelections:maximumSelections
        allowsOther:NO
        isSecret:NO];
    CodexAgentAgentFormField *defaultMany = [[CodexAgentAgentFormField alloc]
        initWithName:@"default_many"
        title:@"Default many"
        description:nil
        isRequired:NO
        type:[CodexAgentAgentFormFieldType multiSelect]
        options:@[optionA, optionB]
        defaultValue:defaultManyValue
        minimum:nil
        maximum:nil
        format:nil
        minimumLength:nil
        maximumLength:nil
        minimumSelections:nil
        maximumSelections:nil
        allowsOther:NO
        isSecret:NO];
    CodexAgentAgentElicitation *elicitation = [[CodexAgentAgentElicitation alloc]
        initWithRequestId:@"d082-request"
        serverName:@"d082-server"
        conversationId:conversationId
        message:@"Configure"
        form:@[name, email, uri, date, timestamp, count, ratio, enabled, choice, many, defaultMany]
        url:nil];

    NSDictionary<NSString *, id<CodexAgentAgentFormValue>> *initialValues =
        [elicitation initialValues];
    CodexAgentAgentFormValueNumber *initialCount =
        (CodexAgentAgentFormValueNumber *)initialValues[@"count"];
    CodexAgentAgentFormValueTextList *initialMany =
        (CodexAgentAgentFormValueTextList *)initialValues[@"default_many"];
    [defaultSelections addObject:@"b"];
    if (initialValues.count != 2 || initialValues[@"name"] != nil ||
        ![(id)initialCount isKindOfClass:[CodexAgentAgentFormValueNumber class]] ||
        initialCount.value != 2.0 ||
        ![(id)initialMany isKindOfClass:[CodexAgentAgentFormValueTextList class]] ||
        ![initialMany.value isEqualToArray:@[@"a"]]) {
        return @"Objective-C D082 initial-value snapshot changed";
    }

    CodexAgentAgentFormValueText *validName =
        [[CodexAgentAgentFormValueText alloc] initWithValue:@"Ada"];
    CodexAgentAgentFormValueBooleanValue *trueValue =
        [[CodexAgentAgentFormValueBooleanValue alloc] initWithValue:YES];
    CodexAgentAgentFormValueNumber *validRatio =
        [[CodexAgentAgentFormValueNumber alloc] initWithValue:0.5];
    CodexAgentAgentFormValueNumber *validInteger =
        [[CodexAgentAgentFormValueNumber alloc] initWithValue:2.0];
    CodexAgentAgentFormValueText *validEmail =
        [[CodexAgentAgentFormValueText alloc] initWithValue:@"user@example.com"];
    CodexAgentAgentFormValueText *validUri =
        [[CodexAgentAgentFormValueText alloc] initWithValue:@"https://example.com"];
    CodexAgentAgentFormValueText *validDate =
        [[CodexAgentAgentFormValueText alloc] initWithValue:@"2024-02-29"];
    CodexAgentAgentFormValueText *validTimestamp =
        [[CodexAgentAgentFormValueText alloc] initWithValue:@"2026-01-01T12:00:00.123+01:00"];
    CodexAgentAgentFormValueText *selectedA =
        [[CodexAgentAgentFormValueText alloc] initWithValue:@"a"];
    NSMutableArray<NSString *> *selectedValues = [NSMutableArray arrayWithObject:@"a"];
    CodexAgentAgentFormValueTextList *selectedMany =
        [[CodexAgentAgentFormValueTextList alloc] initWithValue:selectedValues];

    if (![name acceptsValue:validName] || [name acceptsValue:nil] ||
        [name acceptsValue:[[CodexAgentAgentFormValueText alloc] initWithValue:@"x"]] ||
        [name acceptsValue:[[CodexAgentAgentFormValueText alloc] initWithValue:@"abcde"]] ||
        [name acceptsValue:trueValue] || ![ratio acceptsValue:nil] ||
        ![ratio acceptsValue:validRatio] ||
        [ratio acceptsValue:[[CodexAgentAgentFormValueNumber alloc] initWithValue:-0.1]] ||
        [ratio acceptsValue:[[CodexAgentAgentFormValueNumber alloc] initWithValue:1.1]] ||
        [ratio acceptsValue:[[CodexAgentAgentFormValueNumber alloc] initWithValue:NAN]] ||
        ![count acceptsValue:validInteger] ||
        [count acceptsValue:[[CodexAgentAgentFormValueNumber alloc] initWithValue:1.5]] ||
        ![enabled acceptsValue:trueValue] || [enabled acceptsValue:validName] ||
        ![email acceptsValue:validEmail] ||
        [email acceptsValue:[[CodexAgentAgentFormValueText alloc] initWithValue:@"invalid"]] ||
        ![uri acceptsValue:validUri] ||
        [uri acceptsValue:[[CodexAgentAgentFormValueText alloc] initWithValue:@"not a uri"]] ||
        ![date acceptsValue:validDate] ||
        [date acceptsValue:[[CodexAgentAgentFormValueText alloc] initWithValue:@"2026-02-31"]] ||
        ![timestamp acceptsValue:validTimestamp] ||
        [timestamp acceptsValue:[[CodexAgentAgentFormValueText alloc]
            initWithValue:@"2026-01-01T12:00:00+garbage"]] ||
        ![choice acceptsValue:selectedA] ||
        [choice acceptsValue:[[CodexAgentAgentFormValueText alloc] initWithValue:@"z"]] ||
        ![otherChoice acceptsValue:[[CodexAgentAgentFormValueText alloc] initWithValue:@"custom"]] ||
        [otherChoice acceptsValue:[[CodexAgentAgentFormValueText alloc] initWithValue:@" "]] ||
        ![many acceptsValue:selectedMany] ||
        [many acceptsValue:[[CodexAgentAgentFormValueTextList alloc] initWithValue:@[]]] ||
        [many acceptsValue:[[CodexAgentAgentFormValueTextList alloc]
            initWithValue:@[@"a", @"a"]]] ||
        [many acceptsValue:[[CodexAgentAgentFormValueTextList alloc]
            initWithValue:@[@"a", @"b", @"c"]]] ||
        [many acceptsValue:[[CodexAgentAgentFormValueTextList alloc] initWithValue:@[@"z"]]]) {
        return @"Objective-C D082 form-field acceptance changed";
    }

    NSArray<NSArray *> *validationCases = @[
        @[@{}, @"name", [CodexAgentAgentElicitationValidationReason missingRequired]],
        @[@{@"name": validName, @"unknown": validName}, @"unknown",
            [CodexAgentAgentElicitationValidationReason unknownField]],
        @[@{@"name": validInteger}, @"name",
            [CodexAgentAgentElicitationValidationReason invalidType]],
        @[@{@"name": validName, @"ratio":
            [[CodexAgentAgentFormValueNumber alloc] initWithValue:NAN]}, @"ratio",
            [CodexAgentAgentElicitationValidationReason nonFiniteNumber]],
        @[@{@"name": validName, @"ratio":
            [[CodexAgentAgentFormValueNumber alloc] initWithValue:-0.1]}, @"ratio",
            [CodexAgentAgentElicitationValidationReason belowMinimum]],
        @[@{@"name": validName, @"ratio":
            [[CodexAgentAgentFormValueNumber alloc] initWithValue:1.1]}, @"ratio",
            [CodexAgentAgentElicitationValidationReason aboveMaximum]],
        @[@{@"name": validName, @"count":
            [[CodexAgentAgentFormValueNumber alloc] initWithValue:1.5]}, @"count",
            [CodexAgentAgentElicitationValidationReason nonInteger]],
        @[@{@"name": validName, @"email":
            [[CodexAgentAgentFormValueText alloc] initWithValue:@"invalid"]}, @"email",
            [CodexAgentAgentElicitationValidationReason invalidFormat]],
        @[@{@"name": validName, @"choice":
            [[CodexAgentAgentFormValueText alloc] initWithValue:@"z"]}, @"choice",
            [CodexAgentAgentElicitationValidationReason invalidSelection]],
        @[@{@"name": validName, @"many":
            [[CodexAgentAgentFormValueTextList alloc] initWithValue:@[@"a", @"a"]]}, @"many",
            [CodexAgentAgentElicitationValidationReason duplicateSelection]],
    ];
    for (NSArray *validationCase in validationCases) {
        NSDictionary<NSString *, id<CodexAgentAgentFormValue>> *caseContent =
            (id)validationCase[0];
        NSString *expectedField = validationCase[1];
        CodexAgentAgentElicitationValidationReason *expectedReason = validationCase[2];
        CodexAgentAgentElicitationValidation *validation =
            [elicitation validateContent:caseContent];
        CodexAgentAgentElicitationValidationIssue *issue = validation.issues.firstObject;
        if (validation.isValid || validation.issues.count != 1 ||
            ![issue.fieldName isEqualToString:expectedField] || issue.reason != expectedReason) {
            return @"Objective-C D082 validation reasons changed";
        }
    }

    NSDictionary<NSString *, id<CodexAgentAgentFormValue>> *content = @{
        @"name": validName,
        @"email": validEmail,
        @"uri": validUri,
        @"date": validDate,
        @"timestamp": validTimestamp,
        @"count": validInteger,
        @"ratio": validRatio,
        @"enabled": trueValue,
        @"choice": selectedA,
        @"many": selectedMany,
    };
    CodexAgentAgentElicitationResponse *accepted = [elicitation acceptContent:content];
    CodexAgentAgentFormValueText *acceptedName =
        (CodexAgentAgentFormValueText *)accepted.content[@"name"];
    CodexAgentAgentFormValueTextList *acceptedMany =
        (CodexAgentAgentFormValueTextList *)accepted.content[@"many"];
    [selectedValues addObject:@"b"];
    if (accepted.action != [CodexAgentAgentElicitationAction accept] ||
        accepted.content.count != content.count ||
        ![(id)acceptedName isKindOfClass:[CodexAgentAgentFormValueText class]] ||
        ![acceptedName.value isEqualToString:@"Ada"] ||
        ![(id)acceptedMany isKindOfClass:[CodexAgentAgentFormValueTextList class]] ||
        ![acceptedMany.value isEqualToArray:@[@"a"]] ||
        ![elicitation acceptsResponse:accepted]) {
        return @"Objective-C D082 accepted response changed";
    }

    CodexAgentAgentElicitationResponse *invalidAccept = [[CodexAgentAgentElicitationResponse alloc]
        initWithAction:[CodexAgentAgentElicitationAction accept]
        content:@{}];
    CodexAgentAgentElicitationResponse *declined = [companion decline];
    CodexAgentAgentElicitationResponse *cancelled = [companion cancel];
    CodexAgentAgentElicitationResponse *contentfulDecline =
        [[CodexAgentAgentElicitationResponse alloc]
            initWithAction:[CodexAgentAgentElicitationAction decline]
            content:@{@"name": validName}];
    CodexAgentAgentElicitationResponse *contentfulCancel =
        [[CodexAgentAgentElicitationResponse alloc]
            initWithAction:[CodexAgentAgentElicitationAction cancel]
            content:@{@"name": validName}];
    if ([elicitation acceptsResponse:invalidAccept] ||
        declined.action != [CodexAgentAgentElicitationAction decline] ||
        declined.content.count != 0 ||
        cancelled.action != [CodexAgentAgentElicitationAction cancel] ||
        cancelled.content.count != 0 || ![elicitation acceptsResponse:declined] ||
        ![elicitation acceptsResponse:cancelled] ||
        [elicitation acceptsResponse:contentfulDecline] ||
        [elicitation acceptsResponse:contentfulCancel]) {
        return @"Objective-C D082 response-action acceptance changed";
    }

    CodexAgentAgentElicitation *urlOnly = [[CodexAgentAgentElicitation alloc]
        initWithRequestId:@"d082-url"
        serverName:@"d082-server"
        conversationId:conversationId
        message:@"Authorize"
        form:nil
        url:@"https://example.com"];
    CodexAgentAgentElicitationResponse *emptyAccept = [[CodexAgentAgentElicitationResponse alloc]
        initWithAction:[CodexAgentAgentElicitationAction accept]
        content:@{}];
    CodexAgentAgentElicitationResponse *unexpectedAccept =
        [[CodexAgentAgentElicitationResponse alloc]
            initWithAction:[CodexAgentAgentElicitationAction accept]
            content:@{@"unexpected": validName}];
    if (![urlOnly acceptsResponse:emptyAccept] ||
        [urlOnly acceptsResponse:unexpectedAccept] ||
        ![urlOnly validateContent:@{}].isValid) {
        return @"Objective-C D082 URL-only acceptance changed";
    }

    return nil;
}

static NSString *CDXVerifyD073OrdinaryValues(void) {
    CodexAgentAgentConnector *connector = [[CodexAgentAgentConnector alloc]
        initWithId:@"connector-id"
        name:@"Connector"
        description:@"Connector description"
        installUrl:@"https://example.com/install"
        isAccessible:YES
        isEnabled:NO
        pluginNames:@[@"plugin"]];
    if (![connector.id isEqualToString:@"connector-id"] ||
        ![connector.name isEqualToString:@"Connector"] ||
        ![connector.description_ isEqualToString:@"Connector description"] ||
        ![connector.installUrl isEqualToString:@"https://example.com/install"] ||
        !connector.isAccessible || connector.isEnabled ||
        ![connector.pluginNames isEqualToArray:@[@"plugin"]]) {
        return @"Objective-C D073 connector changed";
    }

    CodexAgentAgentElicitationValidationIssue *validationIssue =
        [[CodexAgentAgentElicitationValidationIssue alloc]
            initWithFieldName:@"field"
            reason:[CodexAgentAgentElicitationValidationReason invalidType]];
    CodexAgentAgentElicitationValidation *validation =
        [[CodexAgentAgentElicitationValidation alloc] initWithIssues:@[validationIssue]];
    if (![validation.issues isEqualToArray:@[validationIssue]] || validation.isValid) {
        return @"Objective-C D073 elicitation validation changed";
    }

    CodexAgentAgentFormValueBooleanValue *booleanValue =
        [[CodexAgentAgentFormValueBooleanValue alloc] initWithValue:YES];
    if (!booleanValue.value) {
        return @"Objective-C D073 boolean form value changed";
    }
    CodexAgentAgentFormValueNumber *numberValue =
        [[CodexAgentAgentFormValueNumber alloc] initWithValue:7.5];
    if (numberValue.value != 7.5) {
        return @"Objective-C D073 number form value changed";
    }
    CodexAgentAgentFormValueText *textValue =
        [[CodexAgentAgentFormValueText alloc] initWithValue:@"text"];
    if (![textValue.value isEqualToString:@"text"]) {
        return @"Objective-C D073 text form value changed";
    }
    CodexAgentAgentFormValueTextList *textListValue =
        [[CodexAgentAgentFormValueTextList alloc] initWithValue:@[@"first", @"second"]];
    if (![textListValue.value isEqualToArray:@[@"first", @"second"]]) {
        return @"Objective-C D073 text-list form value changed";
    }

    CodexAgentAgentServiceTier *serviceTier = [[CodexAgentAgentServiceTier alloc]
        initWithId:@"fast" name:@"Fast" description:@"Fast tier"];
    CodexAgentAgentModel *model = [[CodexAgentAgentModel alloc]
        initWithId:@"model-id"
        displayName:@"Model"
        description:@"Model description"
        supportedEfforts:@[@"low", @"high"]
        defaultEffort:@"high"
        isDefault:YES
        serviceTiers:@[serviceTier]
        defaultServiceTier:@"fast"];
    if (![model.id isEqualToString:@"model-id"] ||
        ![model.displayName isEqualToString:@"Model"] ||
        ![model.description_ isEqualToString:@"Model description"] ||
        ![model.supportedEfforts isEqualToArray:@[@"low", @"high"]] ||
        ![model.defaultEffort isEqualToString:@"high"] || !model.isDefault ||
        ![model.serviceTiers isEqualToArray:@[serviceTier]] ||
        ![model.defaultServiceTier isEqualToString:@"fast"]) {
        return @"Objective-C D073 model changed";
    }

    CodexAgentAgentPlanStep *planStep = [[CodexAgentAgentPlanStep alloc]
        initWithText:@"Inspect" status:[CodexAgentAgentPlanStepStatus inProgress]];
    CodexAgentAgentPlanProgress *planProgress = [[CodexAgentAgentPlanProgress alloc]
        initWithExplanation:@"Plan explanation" steps:@[planStep]];
    if (![planProgress.explanation isEqualToString:@"Plan explanation"] ||
        ![planProgress.steps isEqualToArray:@[planStep]]) {
        return @"Objective-C D073 plan progress changed";
    }

    CodexAgentAgentPluginReference *pluginReference = [[CodexAgentAgentPluginReference alloc]
        initWithId:@"plugin-id"
        name:@"plugin"
        marketplaceName:@"marketplace"
        marketplacePath:@"/marketplace/plugin"
        remotePluginId:@"remote-plugin"];
    CodexAgentAgentPluginSummary *pluginSummary = [[CodexAgentAgentPluginSummary alloc]
        initWithReference:pluginReference
        displayName:@"Plugin"
        description:@"Plugin description"
        isInstalled:YES
        isEnabled:NO
        installPolicy:[CodexAgentAgentPluginInstallPolicy available]
        authPolicy:[CodexAgentAgentPluginAuthPolicy onUse]
        isAvailable:YES
        capabilities:@[@"tools", @"hooks"]
        brandColor:@"#123456"
        privacyPolicyUrl:@"https://example.com/privacy"
        termsOfServiceUrl:@"https://example.com/terms"
        websiteUrl:@"https://example.com"];
    if (pluginSummary.reference != pluginReference ||
        ![pluginSummary.displayName isEqualToString:@"Plugin"] ||
        ![pluginSummary.description_ isEqualToString:@"Plugin description"] ||
        !pluginSummary.isInstalled || pluginSummary.isEnabled ||
        pluginSummary.installPolicy != [CodexAgentAgentPluginInstallPolicy available] ||
        pluginSummary.authPolicy != [CodexAgentAgentPluginAuthPolicy onUse] ||
        !pluginSummary.isAvailable ||
        ![pluginSummary.capabilities isEqualToArray:@[@"tools", @"hooks"]] ||
        ![pluginSummary.brandColor isEqualToString:@"#123456"] ||
        ![pluginSummary.privacyPolicyUrl isEqualToString:@"https://example.com/privacy"] ||
        ![pluginSummary.termsOfServiceUrl isEqualToString:@"https://example.com/terms"] ||
        ![pluginSummary.websiteUrl isEqualToString:@"https://example.com"]) {
        return @"Objective-C D073 plugin summary changed";
    }

    CodexAgentAgentPluginSkill *pluginSkill = [[CodexAgentAgentPluginSkill alloc]
        initWithName:@"plugin-skill"
        description:@"Plugin skill"
        isEnabled:YES
        path:@"/plugins/skill"];
    CodexAgentAgentPluginCatalog *pluginCatalog = [[CodexAgentAgentPluginCatalog alloc]
        initWithPlugins:@[pluginSummary]
        errors:@[@"catalog warning"]
        freshness:[CodexAgentAgentCatalogFreshness freshCache]];
    if (![pluginCatalog.plugins isEqualToArray:@[pluginSummary]] ||
        ![pluginCatalog.errors isEqualToArray:@[@"catalog warning"]] ||
        pluginCatalog.freshness != [CodexAgentAgentCatalogFreshness freshCache]) {
        return @"Objective-C D073 plugin catalog changed";
    }

    CodexAgentAgentPluginDetail *pluginDetail = [[CodexAgentAgentPluginDetail alloc]
        initWithSummary:pluginSummary
        description:@"Detailed plugin"
        skills:@[pluginSkill]
        connectors:@[connector]
        mcpServers:@[@"filesystem"]
        hookCount:3];
    if (pluginDetail.summary != pluginSummary ||
        ![pluginDetail.description_ isEqualToString:@"Detailed plugin"] ||
        ![pluginDetail.skills isEqualToArray:@[pluginSkill]] ||
        ![pluginDetail.connectors isEqualToArray:@[connector]] ||
        ![pluginDetail.mcpServers isEqualToArray:@[@"filesystem"]] ||
        pluginDetail.hookCount != 3) {
        return @"Objective-C D073 plugin detail changed";
    }

    CodexAgentAgentPluginInstallResult *installResult =
        [[CodexAgentAgentPluginInstallResult alloc]
            initWithAuthPolicy:[CodexAgentAgentPluginAuthPolicy onInstall]
            connectorsNeedingAuthentication:@[connector]
            message:@"Authenticate connector"];
    if (installResult.authPolicy != [CodexAgentAgentPluginAuthPolicy onInstall] ||
        ![installResult.connectorsNeedingAuthentication isEqualToArray:@[connector]] ||
        ![installResult.message isEqualToString:@"Authenticate connector"]) {
        return @"Objective-C D073 plugin install result changed";
    }

    CodexAgentAgentSkill *skill = [[CodexAgentAgentSkill alloc]
        initWithName:@"skill"
        displayName:@"Skill"
        description:@"Skill description"
        path:@"/skills/skill"
        scope:[CodexAgentAgentSkillScope repo]
        isEnabled:YES
        brandColor:@"#abcdef"
        dependencies:@[@"git"]
        canUninstall:YES
        origin:[CodexAgentAgentResourceOrigin workspace]];
    if (![skill.name isEqualToString:@"skill"] ||
        ![skill.displayName isEqualToString:@"Skill"] ||
        ![skill.description_ isEqualToString:@"Skill description"] ||
        ![skill.path isEqualToString:@"/skills/skill"] ||
        skill.scope != [CodexAgentAgentSkillScope repo] || !skill.isEnabled ||
        ![skill.brandColor isEqualToString:@"#abcdef"] ||
        ![skill.dependencies isEqualToArray:@[@"git"]] || !skill.canUninstall ||
        skill.origin != [CodexAgentAgentResourceOrigin workspace]) {
        return @"Objective-C D073 skill changed";
    }

    CodexAgentAgentSkillCatalog *skillCatalog = [[CodexAgentAgentSkillCatalog alloc]
        initWithSkills:@[skill] errors:@[@"skill warning"]];
    if (![skillCatalog.skills isEqualToArray:@[skill]] ||
        ![skillCatalog.errors isEqualToArray:@[@"skill warning"]]) {
        return @"Objective-C D073 skill catalog changed";
    }

    CodexAgentCodexPathWorkspaceSelection *pathSelection =
        [[CodexAgentCodexPathWorkspaceSelection alloc] initWithPath:@"/workspace"];
    if (![pathSelection.path isEqualToString:@"/workspace"]) {
        return @"Objective-C D073 path workspace selection changed";
    }
    CodexAgentCodexWorkspace *workspace = [[CodexAgentCodexWorkspace alloc]
        initWithPath:@"/workspace" displayName:@"Workspace"];
    CodexAgentCodexWorkspaceResolutionAvailable *available =
        [[CodexAgentCodexWorkspaceResolutionAvailable alloc] initWithWorkspace:workspace];
    if (available.workspace != workspace) {
        return @"Objective-C D073 available workspace resolution changed";
    }
    CodexAgentCodexWorkspaceResolutionSelectionRequired *selectionRequired =
        [[CodexAgentCodexWorkspaceResolutionSelectionRequired alloc]
            initWithReason:[CodexAgentCodexWorkspaceSelectionReason notFound]
            message:@"Choose a workspace"];
    if (selectionRequired.reason != [CodexAgentCodexWorkspaceSelectionReason notFound] ||
        ![selectionRequired.message isEqualToString:@"Choose a workspace"]) {
        return @"Objective-C D073 selection-required workspace resolution changed";
    }

    return nil;
}

static NSString *CDXVerifyD074OrdinaryValues(void) {
    CodexAgentConversationId *conversationId = [[CodexAgentConversationId alloc]
        initWithValue:@"d074-conversation"];
    CodexAgentAgentFormOption *option = [[CodexAgentAgentFormOption alloc]
        initWithValue:@"choice" title:@"Choice" description:@"Choice description"];
    CodexAgentAgentFormValueText *defaultValue = [[CodexAgentAgentFormValueText alloc]
        initWithValue:@"https://example.com"];
    CodexAgentDouble *minimum = [CodexAgentDouble numberWithDouble:1.5];
    CodexAgentDouble *maximum = [CodexAgentDouble numberWithDouble:7.5];
    CodexAgentLong *minimumLength = [CodexAgentLong numberWithLongLong:2];
    CodexAgentLong *maximumLength = [CodexAgentLong numberWithLongLong:20];
    CodexAgentLong *minimumSelections = [CodexAgentLong numberWithLongLong:1];
    CodexAgentLong *maximumSelections = [CodexAgentLong numberWithLongLong:2];
    CodexAgentAgentFormField *field = [[CodexAgentAgentFormField alloc]
        initWithName:@"website"
        title:@"Website"
        description:@"Public website"
        isRequired:YES
        type:[CodexAgentAgentFormFieldType string]
        options:@[option]
        defaultValue:defaultValue
        minimum:minimum
        maximum:maximum
        format:[CodexAgentAgentFormStringFormat uri]
        minimumLength:minimumLength
        maximumLength:maximumLength
        minimumSelections:minimumSelections
        maximumSelections:maximumSelections
        allowsOther:YES
        isSecret:YES];
    if (![field.name isEqualToString:@"website"] ||
        ![field.title isEqualToString:@"Website"] ||
        ![field.description_ isEqualToString:@"Public website"] || !field.isRequired ||
        field.type != [CodexAgentAgentFormFieldType string] ||
        ![field.options isEqualToArray:@[option]] || field.defaultValue != defaultValue ||
        field.minimum.doubleValue != 1.5 || field.maximum.doubleValue != 7.5 ||
        field.format != [CodexAgentAgentFormStringFormat uri] ||
        field.minimumLength.longLongValue != 2 || field.maximumLength.longLongValue != 20 ||
        field.minimumSelections.longLongValue != 1 || field.maximumSelections.longLongValue != 2 ||
        !field.allowsOther || !field.isSecret) {
        return @"Objective-C D074 form field changed";
    }

    CodexAgentAgentElicitation *elicitation = [[CodexAgentAgentElicitation alloc]
        initWithRequestId:@"d074-request"
        serverName:@"d074-server"
        conversationId:conversationId
        message:@"Provide input"
        form:@[field]
        url:@"https://example.com/input"];
    if (![elicitation.requestId isEqualToString:@"d074-request"] ||
        ![elicitation.serverName isEqualToString:@"d074-server"] ||
        elicitation.conversationId != conversationId ||
        ![elicitation.message isEqualToString:@"Provide input"] ||
        ![elicitation.form isEqualToArray:@[field]] ||
        ![elicitation.url isEqualToString:@"https://example.com/input"]) {
        return @"Objective-C D074 elicitation changed";
    }

    CodexAgentAgentHookHandlerCommand *commandHandler =
        [[CodexAgentAgentHookHandlerCommand alloc] initWithCommand:@"echo ready" isAsync:YES];
    if (![commandHandler.command isEqualToString:@"echo ready"] || !commandHandler.isAsync) {
        return @"Objective-C D074 command hook handler changed";
    }
    CodexAgentAgentHookHandlerMcpTool *mcpHandler =
        [[CodexAgentAgentHookHandlerMcpTool alloc] initWithServer:@"server" tool:@"review"];
    if (![mcpHandler.server isEqualToString:@"server"] ||
        ![mcpHandler.tool isEqualToString:@"review"]) {
        return @"Objective-C D074 MCP hook handler changed";
    }

    CodexAgentAgentHookTrustStatus *modified = [CodexAgentAgentHookTrustStatus modified];
    CodexAgentAgentResourceOrigin *pluginOrigin = [CodexAgentAgentResourceOrigin plugin];
    CodexAgentAgentHook *hook = [[CodexAgentAgentHook alloc]
        initWithKey:@"d074-hook"
        currentHash:@"d074-hash"
        isEnabled:YES
        eventName:@"afterTurn"
        handler:commandHandler
        isManaged:NO
        source:@"PLUGIN"
        sourcePath:@"/hooks.json"
        timeoutSeconds:30
        trustStatus:modified
        matcher:@"*.kt"
        pluginId:@"d074-plugin"
        statusMessage:@"Ready"
        origin:pluginOrigin
        canUninstall:YES];
    if (![hook.key isEqualToString:@"d074-hook"] ||
        ![hook.currentHash isEqualToString:@"d074-hash"] || !hook.isEnabled ||
        ![hook.eventName isEqualToString:@"afterTurn"] || hook.handler != commandHandler ||
        hook.isManaged || ![hook.source isEqualToString:@"PLUGIN"] ||
        ![hook.sourcePath isEqualToString:@"/hooks.json"] || hook.timeoutSeconds != 30 ||
        hook.trustStatus != modified || ![hook.matcher isEqualToString:@"*.kt"] ||
        ![hook.pluginId isEqualToString:@"d074-plugin"] ||
        ![hook.statusMessage isEqualToString:@"Ready"] || hook.origin != pluginOrigin ||
        !hook.canUninstall || !hook.canTrust) {
        return @"Objective-C D074 hook changed";
    }

    CodexAgentAgentHookRunStatus *completed = [CodexAgentAgentHookRunStatus completed];
    CodexAgentAgentHookActivity *activity = [[CodexAgentAgentHookActivity alloc]
        initWithId:@"d074-activity"
        eventName:@"afterTurn"
        handlerType:@"command"
        status:completed
        statusMessage:@"Complete"
        details:@[@"first", @"second"]];
    if (![activity.id isEqualToString:@"d074-activity"] ||
        ![activity.eventName isEqualToString:@"afterTurn"] ||
        ![activity.handlerType isEqualToString:@"command"] || activity.status != completed ||
        ![activity.statusMessage isEqualToString:@"Complete"] ||
        ![activity.details isEqualToArray:@[@"first", @"second"]]) {
        return @"Objective-C D074 hook activity changed";
    }
    CodexAgentAgentHookCatalog *catalog = [[CodexAgentAgentHookCatalog alloc]
        initWithHooks:@[hook]
        warnings:@[@"warning"]
        errors:@[@"error"]];
    if (![catalog.hooks isEqualToArray:@[hook]] ||
        ![catalog.warnings isEqualToArray:@[@"warning"]] ||
        ![catalog.errors isEqualToArray:@[@"error"]]) {
        return @"Objective-C D074 hook catalog changed";
    }

    CodexAgentAgentConnector *connector = [[CodexAgentAgentConnector alloc]
        initWithId:@"d074-connector"
        name:@"D074 Connector"
        description:@"Connector"
        installUrl:nil
        isAccessible:YES
        isEnabled:YES
        pluginNames:@[]];
    CodexAgentAgentIntegrationConnector *integration =
        [[CodexAgentAgentIntegrationConnector alloc] initWithConnector:connector];
    id<CodexAgentAgentIntegration> integrationView = integration;
    if (integrationView != integration || integration.connector != connector ||
        ![integration.id isEqualToString:@"d074-connector"] ||
        ![integration.displayName isEqualToString:@"D074 Connector"] ||
        ![integrationView.id isEqualToString:@"d074-connector"] ||
        ![integrationView.displayName isEqualToString:@"D074 Connector"]) {
        return @"Objective-C D074 connector integration changed";
    }

    CodexAgentAgentInvocationPlugin *pluginInvocation =
        [[CodexAgentAgentInvocationPlugin alloc]
            initWithName:@"plugin"
            uri:@"plugin://plugin@marketplace"];
    if (![pluginInvocation.name isEqualToString:@"plugin"] ||
        ![pluginInvocation.uri isEqualToString:@"plugin://plugin@marketplace"] ||
        ![pluginInvocation.key isEqualToString:@"plugin:plugin://plugin@marketplace"]) {
        return @"Objective-C D074 plugin invocation changed";
    }
    CodexAgentAgentInvocationSkill *skillInvocation =
        [[CodexAgentAgentInvocationSkill alloc]
            initWithName:@"review"
            path:@"/skills/review/SKILL.md"];
    if (![skillInvocation.name isEqualToString:@"review"] ||
        ![skillInvocation.path isEqualToString:@"/skills/review/SKILL.md"] ||
        ![skillInvocation.key isEqualToString:@"skill:/skills/review/SKILL.md"]) {
        return @"Objective-C D074 skill invocation changed";
    }
    NSArray<id<CodexAgentAgentInvocation>> *invocations = @[pluginInvocation, skillInvocation];
    id<CodexAgentAgentInvocation> pluginView = invocations[0];
    id<CodexAgentAgentInvocation> skillView = invocations[1];
    if (invocations.count != 2 || pluginView != pluginInvocation || skillView != skillInvocation ||
        ![pluginView.name isEqualToString:@"plugin"] ||
        ![pluginView.key isEqualToString:@"plugin:plugin://plugin@marketplace"] ||
        ![pluginInvocation.uri isEqualToString:@"plugin://plugin@marketplace"] ||
        ![skillView.name isEqualToString:@"review"] ||
        ![skillInvocation.path isEqualToString:@"/skills/review/SKILL.md"] ||
        ![skillView.key isEqualToString:@"skill:/skills/review/SKILL.md"]) {
        return @"Objective-C D074 skill invocation changed";
    }

    CodexAgentAgentPlanStep *step = [[CodexAgentAgentPlanStep alloc]
        initWithText:@"Inspect" status:[CodexAgentAgentPlanStepStatus inProgress]];
    CodexAgentAgentPlanProgress *planProgress = [[CodexAgentAgentPlanProgress alloc]
        initWithExplanation:@"D074 plan" steps:@[step]];
    CodexAgentInt *exitCode = [CodexAgentInt numberWithInt:0];
    CodexAgentAgentWorkActivity *writingFiles = [CodexAgentAgentWorkActivity writingFiles];
    CodexAgentAgentTurnProgress *progress = [[CodexAgentAgentTurnProgress alloc]
        initWithText:@"text"
        commentary:@"commentary"
        reasoning:@"reasoning"
        plan:@"plan"
        planProgress:planProgress
        shellOutput:@"output"
        shellExitCode:exitCode
        workActivity:writingFiles
        hookActivities:@[activity]
        isTruncated:YES];
    if (![progress.text isEqualToString:@"text"] ||
        ![progress.commentary isEqualToString:@"commentary"] ||
        ![progress.reasoning isEqualToString:@"reasoning"] ||
        ![progress.plan isEqualToString:@"plan"] || progress.planProgress != planProgress ||
        ![progress.shellOutput isEqualToString:@"output"] || progress.shellExitCode.intValue != 0 ||
        progress.workActivity != writingFiles ||
        ![progress.hookActivities isEqualToArray:@[activity]] || !progress.isTruncated) {
        return @"Objective-C D074 turn progress changed";
    }

    CodexAgentCodexAuthenticationMethodApiKey *apiKey =
        [[CodexAgentCodexAuthenticationMethodApiKey alloc] initWithValue:@"sk-d074"];
    if (![apiKey.value isEqualToString:@"sk-d074"]) {
        return @"Objective-C D074 API key changed";
    }

    return nil;
}

static NSString *CDXVerifyD075PendingValues(void) {
    CodexAgentConversationId *conversationId = [[CodexAgentConversationId alloc]
        initWithValue:@"d075-conversation"];
    CodexAgentAgentPendingApproval *approval = [[CodexAgentAgentPendingApproval alloc]
        initWithRequestId:@"d075-approval"
        conversationId:conversationId
        title:@"Approve"
        details:@"Review the request"];
    if (![approval.requestId isEqualToString:@"d075-approval"] ||
        approval.conversationId != conversationId ||
        ![approval.title isEqualToString:@"Approve"] ||
        ![approval.details isEqualToString:@"Review the request"]) {
        return @"Objective-C D075 pending approval changed";
    }

    CodexAgentAgentElicitation *elicitation = [[CodexAgentAgentElicitation alloc]
        initWithRequestId:@"d075-elicitation"
        serverName:@"server"
        conversationId:conversationId
        message:@"Provide input"
        form:nil
        url:nil];
    CodexAgentAgentPendingElicitation *pendingElicitation =
        [[CodexAgentAgentPendingElicitation alloc] initWithElicitation:elicitation];
    if (pendingElicitation.elicitation != elicitation ||
        ![pendingElicitation.requestId isEqualToString:@"d075-elicitation"] ||
        pendingElicitation.conversationId != conversationId) {
        return @"Objective-C D075 pending elicitation changed";
    }
    NSArray<id<CodexAgentAgentPendingInteraction>> *pending = @[approval, pendingElicitation];
    id<CodexAgentAgentPendingInteraction> approvalView = pending[0];
    id<CodexAgentAgentPendingInteraction> elicitationView = pending[1];
    if (pending.count != 2 || approvalView != approval || elicitationView != pendingElicitation ||
        ![approvalView.requestId isEqualToString:@"d075-approval"] ||
        approvalView.conversationId != conversationId ||
        ![elicitationView.requestId isEqualToString:@"d075-elicitation"] ||
        [approvalView.requestId isEqualToString:elicitationView.requestId] ||
        elicitationView.conversationId != conversationId ||
        pendingElicitation.elicitation != elicitation) {
        return @"Objective-C D075 pending elicitation changed";
    }

    return nil;
}

static NSString *CDXVerifyD084HostStatePayloads(CodexAgentCodexWorkspace *workspace) {
    CodexAgentCodexFailure *failure = [[CodexAgentCodexFailure alloc]
        initWithCode:@"d084_failure"
              message:@"D084 failure"
        isRecoverable:YES];
    CodexAgentCodexHostStateFailed *failed = [[CodexAgentCodexHostStateFailed alloc]
        initWithWorkspace:workspace
                 failure:failure];
    CodexAgentCodexHostStateFailed *workspaceLessFailed = [[CodexAgentCodexHostStateFailed alloc]
        initWithWorkspace:nil
                 failure:failure];
    if (failed.workspace != workspace || failed.failure != failure ||
        workspaceLessFailed.workspace != nil || workspaceLessFailed.failure != failure) {
        return @"Objective-C D084 Failed payload changed";
    }

    CodexAgentCodexHostStatePreparing *preparing = [[CodexAgentCodexHostStatePreparing alloc]
        initWithWorkspace:workspace];
    if (preparing.workspace != workspace) {
        return @"Objective-C D084 Preparing payload changed";
    }

    CodexAgentCodexWorkspaceResolutionSelectionRequired *requirement =
        [[CodexAgentCodexWorkspaceResolutionSelectionRequired alloc]
            initWithReason:[CodexAgentCodexWorkspaceSelectionReason notFound]
                    message:@"Choose a D084 workspace"];
    CodexAgentCodexHostStateWorkspaceRequired *workspaceRequired =
        [[CodexAgentCodexHostStateWorkspaceRequired alloc] initWithRequirement:requirement];
    if (workspaceRequired.requirement != requirement) {
        return @"Objective-C D084 WorkspaceRequired payload changed";
    }
    return nil;
}

static NSString *CDXVerifyD084ReadyPayload(CodexAgentCodexAgent *agent) {
    CodexAgentCodexHostStateReady *ready = [[CodexAgentCodexHostStateReady alloc]
        initWithAgent:agent];
    return ready.agent == agent ? nil : @"Objective-C D084 Ready payload changed";
}

#undef CDX_VERIFY_ENUM

typedef CDXOperation *(^CDXOperationFactory)(dispatch_block_t completed);

static const NSTimeInterval CDXConsumerTimeoutSeconds = 110.0;
static const NSTimeInterval CDXCleanupTimeoutSeconds = 5.0;
static const NSTimeInterval CDXUnsubscribeProofDelaySeconds = 0.1;

@interface CDXD084AuthorizationBrowser : NSObject <CodexAgentCodexAuthorizationBrowser>
@property(atomic, strong) CodexAgentCodexAuthorizationUrl *lastUrl;
@property(atomic) NSUInteger openCount;
@end

@implementation CDXD084AuthorizationBrowser

- (id<CodexAgentCodexAuthorizationPresentation> _Nullable)openUrl:
    (CodexAgentCodexAuthorizationUrl *)url
    error:(NSError * _Nullable * _Nullable)error {
    (void)error;
    self.lastUrl = url;
    self.openCount += 1;
    return [CodexAgentCodexAuthorizationPresentationCompanion companion].None;
}

@end

@interface CDXObjectiveCConsumerRun : NSObject

@property(nonatomic, copy) CDXObjectiveCConsumerCompletion completion;
@property(nonatomic, copy) NSString *sandboxRoot;
@property(nonatomic, strong) NSURL *workspaceURL;
@property(nonatomic, strong) NSURL *canonicalWorkspaceURL;
@property(nonatomic, strong) CodexAgentCodexHost *canonicalHost;
@property(nonatomic, strong) CodexAgentCodexStateObservation *canonicalHostObservation;
@property(nonatomic, strong) CDXD084AuthorizationBrowser *canonicalD084AuthorizationBrowser;
@property(nonatomic, strong) CodexAgentCodexAgent *canonicalD086Agent;
@property(nonatomic, strong) CodexAgentAgentHook *canonicalD086Hook;
@property(nonatomic, strong) CodexAgentAgentMcpServerConfiguration *canonicalD086McpConfiguration;
@property(nonatomic, strong) CodexAgentAgentMcpServer *canonicalD086McpServer;
@property(nonatomic, strong) CodexAgentAgentPluginReference *canonicalD086Plugin;
@property(nonatomic, strong) CodexAgentAgentServiceTier *canonicalD086FirstTier;
@property(nonatomic, strong) CodexAgentAgentModel *canonicalD086Model;
@property(nonatomic, strong) CodexAgentAgentModel *canonicalD086ModelWithoutTiers;
@property(nonatomic, strong) CodexAgentAgentSkill *canonicalD086UnownedSkill;
@property(nonatomic, copy) NSString *canonicalD086FirstModelId;
@property(nonatomic, strong) CodexAgentCodexStateObservation *canonicalD087AuthenticationStateObservation;
@property(nonatomic, strong) CodexAgentCodexStateObservation *canonicalD087IsAuthenticatedObservation;
@property(nonatomic, strong) CodexAgentCodexStateObservation *canonicalD087IsAuthenticatingObservation;
@property(nonatomic, strong) CodexAgentAgentIntegrationMcpServer *canonicalD087Integration;
@property(nonatomic, strong) CodexAgentAgentPendingApproval *canonicalD087Approval;
@property(nonatomic, strong) CodexAgentAgentPendingElicitation *canonicalD087Elicitation;
@property(nonatomic, strong) CodexAgentConversationId *canonicalD087ConversationId;
@property(nonatomic) BOOL canonicalD087ObservedSignedOut;
@property(nonatomic) BOOL canonicalD087ObservedAuthenticating;
@property(nonatomic) BOOL canonicalD087ObservedAuthenticated;
@property(nonatomic) BOOL canonicalD087ObservedAuthenticatedFalse;
@property(nonatomic) BOOL canonicalD087ObservedAuthenticatedTrue;
@property(nonatomic) BOOL canonicalD087ObservedAuthenticatingFalse;
@property(nonatomic) BOOL canonicalD087ObservedAuthenticatingTrue;
@property(nonatomic) BOOL canonicalD087ObservedBrowserUrl;
@property(nonatomic) BOOL canonicalD087BrowserAuthenticationCompleted;
@property(nonatomic) BOOL canonicalD087BrowserAuthenticationAdvanced;
@property(nonatomic) BOOL canonicalD087ObservedBrowserCancelledSignedOut;
@property(nonatomic) BOOL canonicalD087ObservedBrowserCancelledAuthenticatingFalse;
@property(nonatomic) BOOL canonicalD087BrowserCancelCompleted;
@property(nonatomic) BOOL canonicalD087BrowserCancelAdvanced;
@property(nonatomic) BOOL canonicalD087AuthenticationCompleted;
@property(nonatomic) BOOL canonicalD087AuthenticationAdvanced;
@property(nonatomic) BOOL canonicalD087ObservedCancelledSignedOut;
@property(nonatomic) BOOL canonicalD087ObservedCancelledAuthenticationFalse;
@property(nonatomic) BOOL canonicalD087CancelCompleted;
@property(nonatomic) BOOL canonicalD087CancelAdvanced;
@property(nonatomic, strong) CodexAgentCodexConversation *canonicalD088Conversation;
@property(nonatomic, strong) CodexAgentConversationId *canonicalD088ConversationId;
@property(nonatomic, strong) CodexAgentAgentConversationSettings *canonicalD088Settings;
@property(nonatomic, strong) CodexAgentAgentTurnRequest *canonicalD088Request;
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
@property(nonatomic) NSUInteger canonicalHostChangeCount;
@property(nonatomic) BOOL canonicalObservedNew;
@property(nonatomic) BOOL canonicalObservedWorkspaceRequired;
@property(nonatomic) BOOL canonicalObservedReady;
@property(nonatomic) BOOL canonicalObservedClosed;
@property(nonatomic) BOOL canonicalStartCompleted;
@property(nonatomic) BOOL canonicalStartAdvanced;
@property(nonatomic) BOOL canonicalSelectionCompleted;
@property(nonatomic) BOOL canonicalSelectionAdvanced;
@property(nonatomic) BOOL canonicalCloseCompleted;
@property(nonatomic) BOOL canonicalCloseAdvanced;

- (instancetype)initWithCompletion:(CDXObjectiveCConsumerCompletion)completion;
- (void)run;
- (void)beginD086ControllerFunctions:(CodexAgentCodexAgent *)agent;
- (void)advanceD086ControllerFunctionsAtStep:(NSUInteger)step;
- (void)beginD087GatewayFunctions;
- (void)advanceD087GatewayFunctionsAtStep:(NSUInteger)step;
- (void)continueD087BrowserAuthenticationIfReady;
- (void)continueD087BrowserCancelIfReady;
- (void)continueD087AuthenticationIfReady;
- (void)continueD087CancelIfReady;
- (void)beginD088ConversationFunctions;
- (void)advanceD088ConversationFunctionsAtStep:(NSUInteger)step;

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
    NSString *d073Failure = CDXVerifyD073OrdinaryValues();
    if (d073Failure != nil) {
        [self finishWithFailure:d073Failure];
        return;
    }
    NSString *d074Failure = CDXVerifyD074OrdinaryValues();
    if (d074Failure != nil) {
        [self finishWithFailure:d074Failure];
        return;
    }
    NSString *d075Failure = CDXVerifyD075PendingValues();
    if (d075Failure != nil) {
        [self finishWithFailure:d075Failure];
        return;
    }
    NSString *d076Failure = CDXVerifyD076AuthorizationUrls();
    if (d076Failure != nil) {
        [self finishWithFailure:d076Failure];
        return;
    }
    NSString *d077Failure = CDXVerifyD077McpServerValues();
    if (d077Failure != nil) {
        [self finishWithFailure:d077Failure];
        return;
    }
    NSString *d078Failure = CDXVerifyD078McpConfigurationValues();
    if (d078Failure != nil) {
        [self finishWithFailure:d078Failure];
        return;
    }
    NSString *d079Failure = CDXVerifyD079ConversationValues();
    if (d079Failure != nil) {
        [self finishWithFailure:d079Failure];
        return;
    }
    NSString *d080Failure = CDXVerifyD080StateValues();
    if (d080Failure != nil) {
        [self finishWithFailure:d080Failure];
        return;
    }
    NSString *d081Failure = CDXVerifyD081SingletonObjects();
    if (d081Failure != nil) {
        [self finishWithFailure:d081Failure];
        return;
    }
    CodexAgentAgentElicitationResponseCompanion *elicitationResponseCompanion =
        [CodexAgentAgentElicitationResponse companion];
    NSString *d082Failure =
        CDXVerifyD082ElicitationHelpers(elicitationResponseCompanion);
    if (d082Failure != nil) {
        [self finishWithFailure:d082Failure];
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
    NSString *canonicalRoot = [self.sandboxRoot stringByAppendingPathComponent:@"canonical"];
    NSString *canonicalWorkspacePath = [canonicalRoot stringByAppendingPathComponent:@"workspace"];
    if (![[NSFileManager defaultManager] createDirectoryAtPath:canonicalWorkspacePath
                                  withIntermediateDirectories:YES
                                                   attributes:nil
                                                        error:&directoryError]) {
        [self finishWithFailure:directoryError.localizedDescription];
        return;
    }
    self.canonicalWorkspaceURL = [NSURL fileURLWithPath:canonicalWorkspacePath isDirectory:YES];
    CodexAgentCodexWorkspace *canonicalWorkspace = [[CodexAgentCodexWorkspace alloc]
        initWithPath:canonicalWorkspacePath
         displayName:@"D084 Workspace"];
    NSString *d084Failure = CDXVerifyD084HostStatePayloads(canonicalWorkspace);
    if (d084Failure != nil) {
        [self finishWithFailure:d084Failure];
        return;
    }
    [self startCanonicalLifecycle];
}

- (void)startCanonicalLifecycle {
    NSString *canonicalRoot = self.canonicalWorkspaceURL.URLByDeletingLastPathComponent.path;
    NSString *codexHome = [canonicalRoot
        stringByAppendingPathComponent:@"Library/Application Support/CodexAgent"];
    self.canonicalD084AuthorizationBrowser = [[CDXD084AuthorizationBrowser alloc] init];
    CodexAgentIosCodexPlatform *platform = [[CodexAgentIosCodexPlatform alloc]
        initWithSandboxRootPath:canonicalRoot
          credentialProtection:[CodexAgentIosCodexCredentialProtection whileOpen]
          authorizationBrowser:self.canonicalD084AuthorizationBrowser
                 codexHomePath:codexHome
                  storageRoots:nil];
    CodexAgentCodexClientInfo *clientInfo = [[CodexAgentCodexClientInfo alloc]
        initWithName:@"objective-c-canonical"
               title:@"Objective-C Canonical Consumer"
             version:@"0.2.0"];
    self.canonicalHost = [[CodexAgentCodexHost alloc]
        initWithPlatform:platform
              clientInfo:clientInfo];
    id<CodexAgentKotlinx_coroutines_coreStateFlow> lifecycleState =
        self.canonicalHost.lifecycleState;
    if (![lifecycleState.value isKindOfClass:[CodexAgentCodexHostStateNew class]]) {
        [self finishWithFailure:@"Objective-C canonical host did not expose current New state"];
        return;
    }

    __weak CDXObjectiveCConsumerRun *weakSelf = self;
    self.canonicalHostObservation = [[CodexAgentCodexStateObservation alloc]
        initWithState:lifecycleState
              onValue:^(id _Nullable value) {
        CDXObjectiveCConsumerRun *run = weakSelf;
        if (run == nil || run.finishing) return;
        if (![NSThread isMainThread]) {
            [run finishWithFailure:@"Objective-C canonical state changed off the main queue"];
            return;
        }
        run.canonicalHostChangeCount += 1;
        run.canonicalObservedNew |= [value isKindOfClass:[CodexAgentCodexHostStateNew class]];
        run.canonicalObservedWorkspaceRequired |=
            [value isKindOfClass:[CodexAgentCodexHostStateWorkspaceRequired class]];
        run.canonicalObservedReady |= [value isKindOfClass:[CodexAgentCodexHostStateReady class]];
        run.canonicalObservedClosed |= [value isKindOfClass:[CodexAgentCodexHostStateClosed class]];
        [run continueCanonicalStartIfReady];
        [run continueCanonicalSelectionIfReady];
        [run continueCanonicalCloseIfReady];
    }];
    if (!self.canonicalObservedNew || self.canonicalHostChangeCount != 1) {
        [self finishWithFailure:@"Objective-C canonical observation omitted its current value"];
        return;
    }

    [self.canonicalHost startWithCompletionHandler:^(NSError *error) {
        dispatch_async(dispatch_get_main_queue(), ^{
            CDXObjectiveCConsumerRun *run = weakSelf;
            if (run == nil || run.finishing) return;
            if (error != nil) {
                [run finishWithFailure:[@"Objective-C canonical start failed: "
                    stringByAppendingString:error.localizedDescription]];
                return;
            }
            run.canonicalStartCompleted = YES;
            [run continueCanonicalStartIfReady];
        });
    }];
}

- (void)continueCanonicalStartIfReady {
    if (!self.canonicalStartCompleted || !self.canonicalObservedWorkspaceRequired ||
        self.canonicalStartAdvanced || self.finishing) return;
    self.canonicalStartAdvanced = YES;
    id current = self.canonicalHost.lifecycleState.value;
    if (![current isKindOfClass:[CodexAgentCodexHostStateWorkspaceRequired class]] ||
        self.canonicalHostChangeCount < 2) {
        [self finishWithFailure:@"Objective-C canonical start omitted its state change"];
        return;
    }
    CodexAgentCodexHostStateWorkspaceRequired *workspaceRequired = current;
    if (workspaceRequired.requirement.message.length == 0 ||
        workspaceRequired.requirement.reason == nil) {
        [self finishWithFailure:@"Objective-C canonical workspace requirement lost its payload"];
        return;
    }
    [self selectCanonicalWorkspace];
}

- (void)selectCanonicalWorkspace {
    CodexAgentIosCodexWorkspaceSelection *selection =
        [[CodexAgentIosCodexWorkspaceSelection alloc] initWithUrl:self.canonicalWorkspaceURL];
    __weak CDXObjectiveCConsumerRun *weakSelf = self;
    [self.canonicalHost selectWorkspaceSelection:selection completionHandler:^(NSError *error) {
        dispatch_async(dispatch_get_main_queue(), ^{
            CDXObjectiveCConsumerRun *run = weakSelf;
            if (run == nil || run.finishing) return;
            id current = run.canonicalHost.lifecycleState.value;
            if (error != nil || [current isKindOfClass:[CodexAgentCodexHostStateFailed class]]) {
                CodexAgentCodexHostStateFailed *failed =
                    [current isKindOfClass:[CodexAgentCodexHostStateFailed class]] ? current : nil;
                NSString *detail = failed.failure.message ?: error.localizedDescription ?: @"unknown";
                [run finishWithFailure:[@"Objective-C canonical selection failed: "
                    stringByAppendingString:detail]];
                return;
            }
            run.canonicalSelectionCompleted = YES;
            [run continueCanonicalSelectionIfReady];
        });
    }];
}

- (void)continueCanonicalSelectionIfReady {
    if (!self.canonicalSelectionCompleted || !self.canonicalObservedReady ||
        self.canonicalSelectionAdvanced || self.finishing) return;
    self.canonicalSelectionAdvanced = YES;
    id current = self.canonicalHost.lifecycleState.value;
    if (![current isKindOfClass:[CodexAgentCodexHostStateReady class]] ||
        self.canonicalHostChangeCount < 3) {
        [self finishWithFailure:@"Objective-C canonical selection omitted Ready state"];
        return;
    }
    CodexAgentCodexHostStateReady *ready = current;
    NSString *readyFailure = CDXVerifyD084ReadyPayload(ready.agent);
    if (ready.agent == nil || readyFailure != nil) {
        [self finishWithFailure:readyFailure ?: @"Objective-C canonical Ready lost its agent"];
        return;
    }
    CodexAgentCodexAuthentication *authentication = ready.agent.authentication;
    if (authentication == nil || authentication != ready.agent.authentication) {
        [self finishWithFailure:@"Objective-C canonical authentication controller was not stable"];
        return;
    }
    CodexAgentCodexConnectors *connectors = ready.agent.connectors;
    if (connectors == nil || connectors != ready.agent.connectors) {
        [self finishWithFailure:@"Objective-C canonical connectors controller was not stable"];
        return;
    }
    CodexAgentCodexConversations *conversations = ready.agent.conversations;
    if (conversations == nil || conversations != ready.agent.conversations) {
        [self finishWithFailure:@"Objective-C canonical conversations controller was not stable"];
        return;
    }
    CodexAgentCodexHooks *hooks = ready.agent.hooks;
    if (hooks == nil || hooks != ready.agent.hooks) {
        [self finishWithFailure:@"Objective-C canonical hooks controller was not stable"];
        return;
    }
    CodexAgentCodexIntegrationAuthorization *integrationAuthorization =
        ready.agent.integrationAuthorization;
    if (integrationAuthorization == nil ||
        integrationAuthorization != ready.agent.integrationAuthorization) {
        [self finishWithFailure:
            @"Objective-C canonical integration-authorization controller was not stable"];
        return;
    }
    CodexAgentCodexInteractions *interactions = ready.agent.interactions;
    if (interactions == nil || interactions != ready.agent.interactions) {
        [self finishWithFailure:@"Objective-C canonical interactions controller was not stable"];
        return;
    }
    CodexAgentCodexMcpServers *mcpServers = ready.agent.mcpServers;
    if (mcpServers == nil || mcpServers != ready.agent.mcpServers) {
        [self finishWithFailure:@"Objective-C canonical MCP-servers controller was not stable"];
        return;
    }
    CodexAgentCodexModels *models = ready.agent.models;
    if (models == nil || models != ready.agent.models) {
        [self finishWithFailure:@"Objective-C canonical models controller was not stable"];
        return;
    }
    CodexAgentCodexPlugins *plugins = ready.agent.plugins;
    if (plugins == nil || plugins != ready.agent.plugins) {
        [self finishWithFailure:@"Objective-C canonical plugins controller was not stable"];
        return;
    }
    CodexAgentCodexSkills *skills = ready.agent.skills;
    if (skills == nil || skills != ready.agent.skills) {
        [self finishWithFailure:@"Objective-C canonical skills controller was not stable"];
        return;
    }
    CodexAgentCodexWorkspace *workspace = ready.agent.workspace;
    if (workspace == nil || workspace != ready.agent.workspace) {
        [self finishWithFailure:@"Objective-C canonical workspace controller was not stable"];
        return;
    }
    if (![workspace.path isEqualToString:self.canonicalWorkspaceURL.path]) {
        [self finishWithFailure:@"Objective-C canonical workspace controller changed its path"];
        return;
    }
    if (!skills.isAvailable) {
        [self finishWithFailure:@"Objective-C canonical skills availability changed"];
        return;
    }
    if (connectors.isAvailable) {
        [self finishWithFailure:@"Objective-C canonical connectors availability changed"];
        return;
    }
    if (hooks.isAvailable) {
        [self finishWithFailure:@"Objective-C canonical hooks availability changed"];
        return;
    }
    if (mcpServers.isAvailable) {
        [self finishWithFailure:@"Objective-C canonical MCP-servers availability changed"];
        return;
    }
    if (plugins.isAvailable) {
        [self finishWithFailure:@"Objective-C canonical plugins availability changed"];
        return;
    }
    [self beginD086ControllerFunctions:ready.agent];
}

- (void)beginD086ControllerFunctions:(CodexAgentCodexAgent *)agent {
    self.canonicalD086Agent = agent;
    self.canonicalD086Hook = [[CodexAgentAgentHook alloc]
        initWithKey:@"d086-hook"
        currentHash:@"d086-hash"
        isEnabled:YES
        eventName:@"afterTurn"
        handler:[CodexAgentAgentHookHandlerAgent shared]
        isManaged:NO
        source:@"USER"
        sourcePath:[self.sandboxRoot stringByAppendingPathComponent:@"hooks.json"]
        timeoutSeconds:86
        trustStatus:[CodexAgentAgentHookTrustStatus untrusted]
        matcher:nil
        pluginId:nil
        statusMessage:nil
        origin:[CodexAgentAgentResourceOrigin user]
        canUninstall:NO];
    CodexAgentAgentMcpTransportHttp *transport = [[CodexAgentAgentMcpTransportHttp alloc]
        initWithUrl:@"https://example.com/d086-mcp"
        bearerTokenEnvironmentVariable:nil
        headers:nil
        environmentHeaders:nil
        headersHelper:nil];
    self.canonicalD086McpConfiguration = [[CodexAgentAgentMcpServerConfiguration alloc]
        initWithName:@"d086-server"
        transport:transport
        authentication:nil
        environmentId:@"local"
        isEnabled:YES
        isRequired:NO
        supportsParallelToolCalls:NO
        omitToolsFrom:nil
        startupTimeoutSeconds:nil
        toolTimeoutSeconds:nil
        defaultToolApproval:nil
        enabledTools:nil
        disabledTools:nil
        scopes:nil
        oauth:nil
        oauthResource:nil
        tools:@{}];
    self.canonicalD086McpServer = [[CodexAgentAgentMcpServer alloc]
        initWithName:@"d086-server"
        displayName:@"D086 Server"
        authStatus:[CodexAgentAgentMcpAuthStatus unknown]
        configuration:self.canonicalD086McpConfiguration
        origin:[CodexAgentAgentResourceOrigin workspace]
        canRemove:NO];
    self.canonicalD086Plugin = [[CodexAgentAgentPluginReference alloc]
        initWithId:@"d086-plugin"
        name:@"d086-plugin"
        marketplaceName:@"d086-marketplace"
        marketplacePath:nil
        remotePluginId:nil];
    self.canonicalD086FirstTier = [[CodexAgentAgentServiceTier alloc]
        initWithId:@"d086-first-tier"
        name:@"D086 First Tier"
        description:@"D086 first service tier"];
    self.canonicalD086Model = [[CodexAgentAgentModel alloc]
        initWithId:@"d086-model"
        displayName:@"D086 Model"
        description:@"D086 model"
        supportedEfforts:@[@"low", @"medium"]
        defaultEffort:@"medium"
        isDefault:YES
        serviceTiers:@[self.canonicalD086FirstTier]
        defaultServiceTier:@"d086-first-tier"];
    self.canonicalD086ModelWithoutTiers = [[CodexAgentAgentModel alloc]
        initWithId:@"d086-model-without-tiers"
        displayName:@"D086 Model Without Tiers"
        description:@"D086 model without service tiers"
        supportedEfforts:@[@"medium"]
        defaultEffort:@"medium"
        isDefault:NO
        serviceTiers:@[]
        defaultServiceTier:nil];
    NSString *unownedSkillPath = [[self.sandboxRoot
        stringByAppendingPathComponent:@"unowned-skill"]
        stringByAppendingPathComponent:@"SKILL.md"];
    self.canonicalD086UnownedSkill = [[CodexAgentAgentSkill alloc]
        initWithName:@"d086-unowned"
        displayName:@"D086 Unowned Skill"
        description:@"D086 unowned skill"
        path:unownedSkillPath
        scope:[CodexAgentAgentSkillScope user]
        isEnabled:YES
        brandColor:nil
        dependencies:@[]
        canUninstall:YES
        origin:[CodexAgentAgentResourceOrigin user]];
    [self advanceD086ControllerFunctionsAtStep:0];
}

- (void)advanceD086ControllerFunctionsAtStep:(NSUInteger)step {
    if (self.finishing) return;
    __weak CDXObjectiveCConsumerRun *weakSelf = self;
    switch (step) {
        case 0: {
            [self.canonicalD086Agent.connectors
                listForceReload:NO
                completionHandler:^(NSArray<CodexAgentAgentConnector *> *connectors,
                                    NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexOperationException *exception =
                        [error.kotlinException
                            isKindOfClass:[CodexAgentCodexOperationException class]]
                            ? error.kotlinException
                            : nil;
                    CodexAgentCodexFailure *failure = exception.failure;
                    if (connectors != nil || error == nil || failure == nil ||
                        ![failure.code isEqualToString:@"unsupported_feature"] ||
                        ![failure.message isEqualToString:
                            @"Runtime feature CONNECTORS is not supported"] ||
                        failure.isRecoverable) {
                        [run finishWithFailure:
                            @"Objective-C D086 connectors.list exposed the wrong failure"];
                        return;
                    }
                    [run advanceD086ControllerFunctionsAtStep:1];
                });
            }];
            break;
        }
        case 1: {
            [self.canonicalD086Agent.hooks
                installDirectory:[self.sandboxRoot stringByAppendingPathComponent:@"missing-hook"]
                scope:[CodexAgentAgentInstallationScope workspace]
                completionHandler:^(CodexAgentAgentHook *hook, NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexOperationException *exception =
                        [error.kotlinException
                            isKindOfClass:[CodexAgentCodexOperationException class]]
                            ? error.kotlinException
                            : nil;
                    CodexAgentCodexFailure *failure = exception.failure;
                    if (hook != nil || error == nil || failure == nil ||
                        ![failure.code isEqualToString:@"unsupported_feature"] ||
                        ![failure.message isEqualToString:
                            @"Runtime feature HOOKS is not supported"] ||
                        failure.isRecoverable) {
                        [run finishWithFailure:
                            @"Objective-C D086 hooks.install exposed the wrong failure"];
                        return;
                    }
                    [run advanceD086ControllerFunctionsAtStep:2];
                });
            }];
            break;
        }
        case 2: {
            [self.canonicalD086Agent.hooks
                listWithCompletionHandler:^(CodexAgentAgentHookCatalog *catalog,
                                            NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexOperationException *exception =
                        [error.kotlinException
                            isKindOfClass:[CodexAgentCodexOperationException class]]
                            ? error.kotlinException
                            : nil;
                    CodexAgentCodexFailure *failure = exception.failure;
                    if (catalog != nil || error == nil || failure == nil ||
                        ![failure.code isEqualToString:@"unsupported_feature"] ||
                        ![failure.message isEqualToString:
                            @"Runtime feature HOOKS is not supported"] ||
                        failure.isRecoverable) {
                        [run finishWithFailure:
                            @"Objective-C D086 hooks.list exposed the wrong failure"];
                        return;
                    }
                    [run advanceD086ControllerFunctionsAtStep:3];
                });
            }];
            break;
        }
        case 3: {
            [self.canonicalD086Agent.hooks
                trustHook:self.canonicalD086Hook
                completionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexOperationException *exception =
                        [error.kotlinException
                            isKindOfClass:[CodexAgentCodexOperationException class]]
                            ? error.kotlinException
                            : nil;
                    CodexAgentCodexFailure *failure = exception.failure;
                    if (error == nil || failure == nil ||
                        ![failure.code isEqualToString:@"unsupported_feature"] ||
                        ![failure.message isEqualToString:
                            @"Runtime feature HOOKS is not supported"] ||
                        failure.isRecoverable) {
                        [run finishWithFailure:
                            @"Objective-C D086 hooks.trust exposed the wrong failure"];
                        return;
                    }
                    [run advanceD086ControllerFunctionsAtStep:4];
                });
            }];
            break;
        }
        case 4: {
            [self.canonicalD086Agent.hooks
                uninstallHook:self.canonicalD086Hook
                completionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexOperationException *exception =
                        [error.kotlinException
                            isKindOfClass:[CodexAgentCodexOperationException class]]
                            ? error.kotlinException
                            : nil;
                    CodexAgentCodexFailure *failure = exception.failure;
                    if (error == nil || failure == nil ||
                        ![failure.code isEqualToString:@"unsupported_feature"] ||
                        ![failure.message isEqualToString:
                            @"Runtime feature HOOKS is not supported"] ||
                        failure.isRecoverable) {
                        [run finishWithFailure:
                            @"Objective-C D086 hooks.uninstall exposed the wrong failure"];
                        return;
                    }
                    [run advanceD086ControllerFunctionsAtStep:5];
                });
            }];
            break;
        }
        case 5: {
            [self.canonicalD086Agent.mcpServers
                addConfiguration:self.canonicalD086McpConfiguration
                completionHandler:^(CodexAgentAgentMcpServer *server, NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexOperationException *exception =
                        [error.kotlinException
                            isKindOfClass:[CodexAgentCodexOperationException class]]
                            ? error.kotlinException
                            : nil;
                    CodexAgentCodexFailure *failure = exception.failure;
                    if (server != nil || error == nil || failure == nil ||
                        ![failure.code isEqualToString:@"unsupported_feature"] ||
                        ![failure.message isEqualToString:
                            @"Runtime feature MCP_SERVERS is not supported"] ||
                        failure.isRecoverable) {
                        [run finishWithFailure:
                            @"Objective-C D086 mcpServers.add exposed the wrong failure"];
                        return;
                    }
                    [run advanceD086ControllerFunctionsAtStep:6];
                });
            }];
            break;
        }
        case 6: {
            [self.canonicalD086Agent.mcpServers
                listWithCompletionHandler:^(NSArray<CodexAgentAgentMcpServer *> *servers,
                                            NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexOperationException *exception =
                        [error.kotlinException
                            isKindOfClass:[CodexAgentCodexOperationException class]]
                            ? error.kotlinException
                            : nil;
                    CodexAgentCodexFailure *failure = exception.failure;
                    if (servers != nil || error == nil || failure == nil ||
                        ![failure.code isEqualToString:@"unsupported_feature"] ||
                        ![failure.message isEqualToString:
                            @"Runtime feature MCP_SERVERS is not supported"] ||
                        failure.isRecoverable) {
                        [run finishWithFailure:
                            @"Objective-C D086 mcpServers.list exposed the wrong failure"];
                        return;
                    }
                    [run advanceD086ControllerFunctionsAtStep:7];
                });
            }];
            break;
        }
        case 7: {
            [self.canonicalD086Agent.mcpServers
                removeServer:self.canonicalD086McpServer
                completionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexOperationException *exception =
                        [error.kotlinException
                            isKindOfClass:[CodexAgentCodexOperationException class]]
                            ? error.kotlinException
                            : nil;
                    CodexAgentCodexFailure *failure = exception.failure;
                    if (error == nil || failure == nil ||
                        ![failure.code isEqualToString:@"unsupported_feature"] ||
                        ![failure.message isEqualToString:
                            @"Runtime feature MCP_SERVERS is not supported"] ||
                        failure.isRecoverable) {
                        [run finishWithFailure:
                            @"Objective-C D086 mcpServers.remove exposed the wrong failure"];
                        return;
                    }
                    [run advanceD086ControllerFunctionsAtStep:8];
                });
            }];
            break;
        }
        case 8: {
            [self.canonicalD086Agent.models
                listWithCompletionHandler:^(NSArray<CodexAgentAgentModel *> *models,
                                            NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentAgentModel *first = models.firstObject;
                    if (error != nil || models.count == 0 ||
                        ![first isKindOfClass:[CodexAgentAgentModel class]] ||
                        first.id.length == 0) {
                        [run finishWithFailure:
                            @"Objective-C D086 models.list did not expose a nonempty typed list"];
                        return;
                    }
                    run.canonicalD086FirstModelId = first.id;
                    [run advanceD086ControllerFunctionsAtStep:9];
                });
            }];
            break;
        }
        case 9: {
            [self.canonicalD086Agent.models
                resolveResolution:[CodexAgentAgentResolution first]
                completionHandler:^(CodexAgentAgentModel *model, NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    if (error != nil || model == nil ||
                        ![model.id isEqualToString:run.canonicalD086FirstModelId]) {
                        [run finishWithFailure:
                            @"Objective-C D086 models.resolve First changed the first model"];
                        return;
                    }
                    [run advanceD086ControllerFunctionsAtStep:10];
                });
            }];
            break;
        }
        case 10: {
            [self.canonicalD086Agent.models
                resolveEffortModel:self.canonicalD086Model
                resolution:[CodexAgentAgentResolution default_]
                completionHandler:^(NSString *effort, NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    if (error != nil ||
                        ![effort isEqualToString:run.canonicalD086Model.defaultEffort]) {
                        [run finishWithFailure:
                            @"Objective-C D086 models.resolveEffort Default changed metadata"];
                        return;
                    }
                    [run advanceD086ControllerFunctionsAtStep:11];
                });
            }];
            break;
        }
        case 11: {
            [self.canonicalD086Agent.models
                resolveServiceTierModel:self.canonicalD086Model
                resolution:[CodexAgentAgentResolution first]
                completionHandler:^(CodexAgentAgentServiceTier *tier, NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    if (error != nil || tier != run.canonicalD086FirstTier) {
                        [run finishWithFailure:
                            @"Objective-C D086 models.resolveServiceTier First changed identity"];
                        return;
                    }
                    [run advanceD086ControllerFunctionsAtStep:12];
                });
            }];
            break;
        }
        case 12: {
            [self.canonicalD086Agent.models
                resolveServiceTierModel:self.canonicalD086ModelWithoutTiers
                resolution:[CodexAgentAgentResolution first]
                completionHandler:^(CodexAgentAgentServiceTier *tier, NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    if (error != nil || tier != nil) {
                        [run finishWithFailure:
                            @"Objective-C D086 models.resolveServiceTier lost nullable absence"];
                        return;
                    }
                    [run advanceD086ControllerFunctionsAtStep:13];
                });
            }];
            break;
        }
        case 13: {
            [self.canonicalD086Agent.plugins
                installPlugin:self.canonicalD086Plugin
                completionHandler:^(CodexAgentAgentPluginInstallResult *result,
                                    NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexOperationException *exception =
                        [error.kotlinException
                            isKindOfClass:[CodexAgentCodexOperationException class]]
                            ? error.kotlinException
                            : nil;
                    CodexAgentCodexFailure *failure = exception.failure;
                    if (result != nil || error == nil || failure == nil ||
                        ![failure.code isEqualToString:@"unsupported_feature"] ||
                        ![failure.message isEqualToString:
                            @"Runtime feature PLUGINS is not supported"] ||
                        failure.isRecoverable) {
                        [run finishWithFailure:
                            @"Objective-C D086 plugins.install exposed the wrong failure"];
                        return;
                    }
                    [run advanceD086ControllerFunctionsAtStep:14];
                });
            }];
            break;
        }
        case 14: {
            [self.canonicalD086Agent.plugins
                listForceReload:NO
                completionHandler:^(CodexAgentAgentPluginCatalog *catalog, NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexOperationException *exception =
                        [error.kotlinException
                            isKindOfClass:[CodexAgentCodexOperationException class]]
                            ? error.kotlinException
                            : nil;
                    CodexAgentCodexFailure *failure = exception.failure;
                    if (catalog != nil || error == nil || failure == nil ||
                        ![failure.code isEqualToString:@"unsupported_feature"] ||
                        ![failure.message isEqualToString:
                            @"Runtime feature PLUGINS is not supported"] ||
                        failure.isRecoverable) {
                        [run finishWithFailure:
                            @"Objective-C D086 plugins.list exposed the wrong failure"];
                        return;
                    }
                    [run advanceD086ControllerFunctionsAtStep:15];
                });
            }];
            break;
        }
        case 15: {
            [self.canonicalD086Agent.plugins
                readPlugin:self.canonicalD086Plugin
                completionHandler:^(CodexAgentAgentPluginDetail *detail, NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexOperationException *exception =
                        [error.kotlinException
                            isKindOfClass:[CodexAgentCodexOperationException class]]
                            ? error.kotlinException
                            : nil;
                    CodexAgentCodexFailure *failure = exception.failure;
                    if (detail != nil || error == nil || failure == nil ||
                        ![failure.code isEqualToString:@"unsupported_feature"] ||
                        ![failure.message isEqualToString:
                            @"Runtime feature PLUGINS is not supported"] ||
                        failure.isRecoverable) {
                        [run finishWithFailure:
                            @"Objective-C D086 plugins.read exposed the wrong failure"];
                        return;
                    }
                    [run advanceD086ControllerFunctionsAtStep:16];
                });
            }];
            break;
        }
        case 16: {
            [self.canonicalD086Agent.plugins
                uninstallPlugin:self.canonicalD086Plugin
                completionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexOperationException *exception =
                        [error.kotlinException
                            isKindOfClass:[CodexAgentCodexOperationException class]]
                            ? error.kotlinException
                            : nil;
                    CodexAgentCodexFailure *failure = exception.failure;
                    if (error == nil || failure == nil ||
                        ![failure.code isEqualToString:@"unsupported_feature"] ||
                        ![failure.message isEqualToString:
                            @"Runtime feature PLUGINS is not supported"] ||
                        failure.isRecoverable) {
                        [run finishWithFailure:
                            @"Objective-C D086 plugins.uninstall exposed the wrong failure"];
                        return;
                    }
                    [run advanceD086ControllerFunctionsAtStep:17];
                });
            }];
            break;
        }
        case 17: {
            [self.canonicalD086Agent.skills
                listForceReload:YES
                completionHandler:^(CodexAgentAgentSkillCatalog *catalog, NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    if (error != nil || catalog == nil ||
                        ![catalog isKindOfClass:[CodexAgentAgentSkillCatalog class]] ||
                        catalog.errors.count != 0) {
                        [run finishWithFailure:
                            @"Objective-C D086 skills.list did not expose a typed clean catalog"];
                        return;
                    }
                    [run advanceD086ControllerFunctionsAtStep:18];
                });
            }];
            break;
        }
        case 18: {
            NSString *unknownPath = [[self.sandboxRoot
                stringByAppendingPathComponent:@"never-listed"]
                stringByAppendingPathComponent:@"SKILL.md"];
            [self.canonicalD086Agent.skills
                readPath:unknownPath
                offset:0
                completionHandler:^(CodexAgentAgentSkillChunk *chunk, NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexOperationException *exception =
                        [error.kotlinException
                            isKindOfClass:[CodexAgentCodexOperationException class]]
                            ? error.kotlinException
                            : nil;
                    CodexAgentCodexFailure *failure = exception.failure;
                    if (chunk != nil || error == nil || failure == nil ||
                        ![failure.code isEqualToString:@"skill_read_failed"] ||
                        ![failure.message isEqualToString:@"Could not read skill"] ||
                        !failure.isRecoverable) {
                        [run finishWithFailure:
                            @"Objective-C D086 skills.read exposed the wrong local failure"];
                        return;
                    }
                    [run advanceD086ControllerFunctionsAtStep:19];
                });
            }];
            break;
        }
        case 19: {
            [self.canonicalD086Agent.skills
                installDirectory:[self.sandboxRoot
                    stringByAppendingPathComponent:@"missing-skill"]
                scope:[CodexAgentAgentInstallationScope user]
                completionHandler:^(CodexAgentAgentSkill *skill, NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexOperationException *exception =
                        [error.kotlinException
                            isKindOfClass:[CodexAgentCodexOperationException class]]
                            ? error.kotlinException
                            : nil;
                    CodexAgentCodexFailure *failure = exception.failure;
                    if (skill != nil || error == nil || failure == nil ||
                        ![failure.code isEqualToString:@"skill_install_failed"] ||
                        ![failure.message isEqualToString:@"Could not install skill"] ||
                        !failure.isRecoverable) {
                        [run finishWithFailure:
                            @"Objective-C D086 skills.install exposed the wrong local failure"];
                        return;
                    }
                    [run advanceD086ControllerFunctionsAtStep:20];
                });
            }];
            break;
        }
        case 20: {
            [self.canonicalD086Agent.skills
                uninstallSkill:self.canonicalD086UnownedSkill
                completionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexOperationException *exception =
                        [error.kotlinException
                            isKindOfClass:[CodexAgentCodexOperationException class]]
                            ? error.kotlinException
                            : nil;
                    CodexAgentCodexFailure *failure = exception.failure;
                    if (error == nil || failure == nil ||
                        ![failure.code isEqualToString:@"skill_uninstall_failed"] ||
                        ![failure.message isEqualToString:@"Could not uninstall skill"] ||
                        !failure.isRecoverable) {
                        [run finishWithFailure:
                            @"Objective-C D086 skills.uninstall exposed the wrong local failure"];
                        return;
                    }
                    [run advanceD086ControllerFunctionsAtStep:21];
                });
            }];
            break;
        }
        case 21:
            [self beginD087GatewayFunctions];
            break;
        default:
            [self finishWithFailure:@"Objective-C D086 controller sequence advanced past its end"];
            break;
    }
}

- (void)beginD087GatewayFunctions {
    CodexAgentCodexAuthentication *authentication = self.canonicalD086Agent.authentication;
    id stateValue = authentication.state.value;
    id authenticatedValue = authentication.isAuthenticated.value;
    id authenticatingValue = authentication.isAuthenticating.value;
    if (![stateValue isKindOfClass:[CodexAgentAgentAuthenticationState class]] ||
        ((CodexAgentAgentAuthenticationState *)stateValue).status !=
            [CodexAgentAgentAuthenticationStatus signedOut] ||
        ((CodexAgentAgentAuthenticationState *)stateValue).pendingSignInUrl != nil ||
        ((CodexAgentAgentAuthenticationState *)stateValue).deviceVerificationUrl != nil ||
        ((CodexAgentAgentAuthenticationState *)stateValue).deviceUserCode != nil ||
        ((CodexAgentAgentAuthenticationState *)stateValue).failure != nil ||
        ![authenticatedValue isKindOfClass:[CodexAgentBoolean class]] ||
        [(CodexAgentBoolean *)authenticatedValue boolValue] ||
        ![authenticatingValue isKindOfClass:[CodexAgentBoolean class]] ||
        [(CodexAgentBoolean *)authenticatingValue boolValue]) {
        [self finishWithFailure:@"Objective-C D087 authentication current values changed"];
        return;
    }

    __weak CDXObjectiveCConsumerRun *weakSelf = self;
    self.canonicalD087AuthenticationStateObservation = [[CodexAgentCodexStateObservation alloc]
        initWithState:authentication.state
              onValue:^(id _Nullable value) {
        CDXObjectiveCConsumerRun *run = weakSelf;
        if (run == nil || run.finishing) return;
        if (![NSThread isMainThread]) {
            [run finishWithFailure:@"Objective-C D087 authentication state changed off the main queue"];
            return;
        }
        if (![value isKindOfClass:[CodexAgentAgentAuthenticationState class]]) {
            [run finishWithFailure:@"Objective-C D087 authentication state lost its type"];
            return;
        }
        CodexAgentAgentAuthenticationState *state = value;
        if (state.status == [CodexAgentAgentAuthenticationStatus signedOut]) {
            run.canonicalD087ObservedSignedOut = YES;
            if (run.canonicalD087BrowserAuthenticationAdvanced &&
                !run.canonicalD087BrowserCancelAdvanced) {
                run.canonicalD087ObservedBrowserCancelledSignedOut = YES;
            }
            if (run.canonicalD087AuthenticationAdvanced) {
                run.canonicalD087ObservedCancelledSignedOut = YES;
            }
        } else if (state.status == [CodexAgentAgentAuthenticationStatus authenticating]) {
            if (state.deviceVerificationUrl != nil || state.deviceUserCode != nil ||
                state.failure != nil) {
                [run finishWithFailure:
                    @"Objective-C D087 Authenticating state payload changed"];
                return;
            }
            if (state.pendingSignInUrl != nil) {
                if (state.pendingSignInUrl.purpose != [CodexAgentCodexAuthorizationPurpose chatGpt] ||
                    state.pendingSignInUrl.value.length == 0) {
                    [run finishWithFailure:
                        @"Objective-C D087 browser URL payload changed"];
                    return;
                }
                run.canonicalD087ObservedBrowserUrl = YES;
            }
            run.canonicalD087ObservedAuthenticating = YES;
        } else if (state.status == [CodexAgentAgentAuthenticationStatus authenticated]) {
            run.canonicalD087ObservedAuthenticated = YES;
        } else {
            [run finishWithFailure:@"Objective-C D087 authentication exposed an unknown status"];
            return;
        }
        [run continueD087BrowserAuthenticationIfReady];
        [run continueD087BrowserCancelIfReady];
        [run continueD087AuthenticationIfReady];
        [run continueD087CancelIfReady];
    }];
    self.canonicalD087IsAuthenticatedObservation = [[CodexAgentCodexStateObservation alloc]
        initWithState:authentication.isAuthenticated
              onValue:^(id _Nullable value) {
        CDXObjectiveCConsumerRun *run = weakSelf;
        if (run == nil || run.finishing) return;
        if (![NSThread isMainThread] || ![value isKindOfClass:[CodexAgentBoolean class]]) {
            [run finishWithFailure:
                @"Objective-C D087 isAuthenticated callback changed queue or type"];
            return;
        }
        if ([(CodexAgentBoolean *)value boolValue]) {
            run.canonicalD087ObservedAuthenticatedTrue = YES;
        } else {
            run.canonicalD087ObservedAuthenticatedFalse = YES;
            if (run.canonicalD087AuthenticationAdvanced) {
                run.canonicalD087ObservedCancelledAuthenticationFalse = YES;
            }
        }
        [run continueD087BrowserAuthenticationIfReady];
        [run continueD087BrowserCancelIfReady];
        [run continueD087AuthenticationIfReady];
        [run continueD087CancelIfReady];
    }];
    self.canonicalD087IsAuthenticatingObservation = [[CodexAgentCodexStateObservation alloc]
        initWithState:authentication.isAuthenticating
              onValue:^(id _Nullable value) {
        CDXObjectiveCConsumerRun *run = weakSelf;
        if (run == nil || run.finishing) return;
        if (![NSThread isMainThread] || ![value isKindOfClass:[CodexAgentBoolean class]]) {
            [run finishWithFailure:
                @"Objective-C D087 isAuthenticating callback changed queue or type"];
            return;
        }
        if ([(CodexAgentBoolean *)value boolValue]) {
            run.canonicalD087ObservedAuthenticatingTrue = YES;
        } else {
            run.canonicalD087ObservedAuthenticatingFalse = YES;
            if (run.canonicalD087BrowserAuthenticationAdvanced &&
                !run.canonicalD087BrowserCancelAdvanced) {
                run.canonicalD087ObservedBrowserCancelledAuthenticatingFalse = YES;
            }
        }
        [run continueD087BrowserAuthenticationIfReady];
        [run continueD087BrowserCancelIfReady];
        [run continueD087AuthenticationIfReady];
    }];
    if (!self.canonicalD087ObservedSignedOut ||
        !self.canonicalD087ObservedAuthenticatedFalse ||
        !self.canonicalD087ObservedAuthenticatingFalse) {
        [self finishWithFailure:@"Objective-C D087 observations omitted current values"];
        return;
    }

    self.canonicalD087Integration = [[CodexAgentAgentIntegrationMcpServer alloc]
        initWithServer:self.canonicalD086McpServer];
    self.canonicalD087ConversationId = [[CodexAgentConversationId alloc]
        initWithValue:@"d087-conversation"];
    self.canonicalD087Approval = [[CodexAgentAgentPendingApproval alloc]
        initWithRequestId:@"d087-approval"
        conversationId:self.canonicalD087ConversationId
        title:@"D087 approval"
        details:@"Not pending"];
    CodexAgentAgentElicitation *elicitation = [[CodexAgentAgentElicitation alloc]
        initWithRequestId:@"d087-elicitation"
        serverName:@"d087-server"
        conversationId:self.canonicalD087ConversationId
        message:@"D087 URL"
        form:nil
        url:@"https://example.com/d087"];
    self.canonicalD087Elicitation = [[CodexAgentAgentPendingElicitation alloc]
        initWithElicitation:elicitation];
    [self advanceD087GatewayFunctionsAtStep:0];
}

- (void)continueD087BrowserAuthenticationIfReady {
    if (!self.canonicalD087BrowserAuthenticationCompleted ||
        !self.canonicalD087ObservedAuthenticating ||
        !self.canonicalD087ObservedAuthenticatingTrue ||
        !self.canonicalD087ObservedBrowserUrl ||
        self.canonicalD087BrowserAuthenticationAdvanced || self.finishing) return;
    CodexAgentCodexAuthentication *authentication = self.canonicalD086Agent.authentication;
    CodexAgentAgentAuthenticationState *state =
        (CodexAgentAgentAuthenticationState *)authentication.state.value;
    CodexAgentBoolean *authenticated =
        (CodexAgentBoolean *)authentication.isAuthenticated.value;
    CodexAgentBoolean *authenticating =
        (CodexAgentBoolean *)authentication.isAuthenticating.value;
    CodexAgentCodexAuthorizationUrl *browserUrl =
        self.canonicalD084AuthorizationBrowser.lastUrl;
    if (![state isKindOfClass:[CodexAgentAgentAuthenticationState class]] ||
        state.status != [CodexAgentAgentAuthenticationStatus authenticating] ||
        state.pendingSignInUrl == nil || state.pendingSignInUrl != browserUrl ||
        state.pendingSignInUrl.purpose != [CodexAgentCodexAuthorizationPurpose chatGpt] ||
        state.pendingSignInUrl.value.length == 0 ||
        state.deviceVerificationUrl != nil || state.deviceUserCode != nil || state.failure != nil ||
        self.canonicalD084AuthorizationBrowser.openCount != 1 ||
        ![authenticated isKindOfClass:[CodexAgentBoolean class]] || authenticated.boolValue ||
        ![authenticating isKindOfClass:[CodexAgentBoolean class]] || !authenticating.boolValue) {
        [self finishWithFailure:@"Objective-C D087 browser authentication state changed"];
        return;
    }
    self.canonicalD087BrowserAuthenticationAdvanced = YES;
    [self advanceD087GatewayFunctionsAtStep:2];
}

- (void)continueD087BrowserCancelIfReady {
    if (!self.canonicalD087BrowserCancelCompleted ||
        !self.canonicalD087ObservedBrowserCancelledSignedOut ||
        !self.canonicalD087ObservedBrowserCancelledAuthenticatingFalse ||
        self.canonicalD087BrowserCancelAdvanced || self.finishing) return;
    CodexAgentCodexAuthentication *authentication = self.canonicalD086Agent.authentication;
    CodexAgentAgentAuthenticationState *state =
        (CodexAgentAgentAuthenticationState *)authentication.state.value;
    CodexAgentBoolean *authenticated =
        (CodexAgentBoolean *)authentication.isAuthenticated.value;
    CodexAgentBoolean *authenticating =
        (CodexAgentBoolean *)authentication.isAuthenticating.value;
    if (![state isKindOfClass:[CodexAgentAgentAuthenticationState class]] ||
        state.status != [CodexAgentAgentAuthenticationStatus signedOut] ||
        state.pendingSignInUrl != nil || state.deviceVerificationUrl != nil ||
        state.deviceUserCode != nil ||
        ![state.failure.code isEqualToString:@"authentication_failed"] ||
        ![state.failure.message isEqualToString:@"Authentication was canceled."] ||
        !state.failure.isRecoverable ||
        ![authenticated isKindOfClass:[CodexAgentBoolean class]] || authenticated.boolValue ||
        ![authenticating isKindOfClass:[CodexAgentBoolean class]] || authenticating.boolValue) {
        [self finishWithFailure:@"Objective-C D087 browser cancel state changed"];
        return;
    }
    self.canonicalD087BrowserCancelAdvanced = YES;
    [self advanceD087GatewayFunctionsAtStep:3];
}

- (void)continueD087AuthenticationIfReady {
    if (!self.canonicalD087AuthenticationCompleted ||
        !self.canonicalD087ObservedAuthenticated ||
        !self.canonicalD087ObservedAuthenticatedTrue ||
        self.canonicalD087AuthenticationAdvanced || self.finishing) return;
    CodexAgentCodexAuthentication *authentication = self.canonicalD086Agent.authentication;
    CodexAgentAgentAuthenticationState *state =
        (CodexAgentAgentAuthenticationState *)authentication.state.value;
    CodexAgentBoolean *authenticated =
        (CodexAgentBoolean *)authentication.isAuthenticated.value;
    CodexAgentBoolean *authenticating =
        (CodexAgentBoolean *)authentication.isAuthenticating.value;
    if (![state isKindOfClass:[CodexAgentAgentAuthenticationState class]] ||
        ![authenticated isKindOfClass:[CodexAgentBoolean class]] ||
        ![authenticating isKindOfClass:[CodexAgentBoolean class]]) {
        [self finishWithFailure:@"Objective-C D087 API-key authentication values lost their types"];
        return;
    }
    if (state.status != [CodexAgentAgentAuthenticationStatus authenticated] ||
        !authenticated.boolValue || authenticating.boolValue) return;
    if (state.pendingSignInUrl != nil || state.deviceVerificationUrl != nil ||
        state.deviceUserCode != nil || state.failure != nil) {
        [self finishWithFailure:@"Objective-C D087 API-key authentication state changed"];
        return;
    }
    self.canonicalD087AuthenticationAdvanced = YES;
    [self advanceD087GatewayFunctionsAtStep:4];
}

- (void)continueD087CancelIfReady {
    if (!self.canonicalD087CancelCompleted ||
        !self.canonicalD087ObservedCancelledSignedOut ||
        !self.canonicalD087ObservedCancelledAuthenticationFalse ||
        self.canonicalD087CancelAdvanced || self.finishing) return;
    CodexAgentCodexAuthentication *authentication = self.canonicalD086Agent.authentication;
    CodexAgentAgentAuthenticationState *state =
        (CodexAgentAgentAuthenticationState *)authentication.state.value;
    CodexAgentBoolean *authenticated =
        (CodexAgentBoolean *)authentication.isAuthenticated.value;
    CodexAgentBoolean *authenticating =
        (CodexAgentBoolean *)authentication.isAuthenticating.value;
    if (![state isKindOfClass:[CodexAgentAgentAuthenticationState class]] ||
        state.status != [CodexAgentAgentAuthenticationStatus signedOut] ||
        state.pendingSignInUrl != nil || state.deviceVerificationUrl != nil ||
        state.deviceUserCode != nil ||
        ![state.failure.code isEqualToString:@"authentication_failed"] ||
        ![state.failure.message isEqualToString:@"Authentication was canceled."] ||
        !state.failure.isRecoverable ||
        ![authenticated isKindOfClass:[CodexAgentBoolean class]] || authenticated.boolValue ||
        ![authenticating isKindOfClass:[CodexAgentBoolean class]] || authenticating.boolValue) {
        [self finishWithFailure:@"Objective-C D087 authentication cancel state changed"];
        return;
    }
    self.canonicalD087CancelAdvanced = YES;
    [self advanceD087GatewayFunctionsAtStep:5];
}

- (void)advanceD087GatewayFunctionsAtStep:(NSUInteger)step {
    if (self.finishing) return;
    __weak CDXObjectiveCConsumerRun *weakSelf = self;
    switch (step) {
        case 0: {
            [self.canonicalD086Agent.authentication signOutWithCompletionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexAuthentication *authentication =
                        run.canonicalD086Agent.authentication;
                    CodexAgentAgentAuthenticationState *state =
                        (CodexAgentAgentAuthenticationState *)authentication.state.value;
                    CodexAgentBoolean *authenticated =
                        (CodexAgentBoolean *)authentication.isAuthenticated.value;
                    CodexAgentBoolean *authenticating =
                        (CodexAgentBoolean *)authentication.isAuthenticating.value;
                    if (error != nil ||
                        ![state isKindOfClass:[CodexAgentAgentAuthenticationState class]] ||
                        state.status != [CodexAgentAgentAuthenticationStatus signedOut] ||
                        state.failure != nil ||
                        ![authenticated isKindOfClass:[CodexAgentBoolean class]] ||
                        authenticated.boolValue ||
                        ![authenticating isKindOfClass:[CodexAgentBoolean class]] ||
                        authenticating.boolValue) {
                        [run finishWithFailure:@"Objective-C D087 authentication signOut changed state"];
                        return;
                    }
                    [run advanceD087GatewayFunctionsAtStep:1];
                });
            }];
            break;
        }
        case 1: {
            [self.canonicalD086Agent.authentication
                authenticateMethod:[CodexAgentCodexAuthenticationMethodChatGptBrowser shared]
                completionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    if (error != nil) {
                        [run finishWithFailure:
                            [@"Objective-C D087 browser authentication failed: "
                                stringByAppendingString:error.localizedDescription]];
                        return;
                    }
                    run.canonicalD087BrowserAuthenticationCompleted = YES;
                    [run continueD087BrowserAuthenticationIfReady];
                });
            }];
            break;
        }
        case 2: {
            [self.canonicalD086Agent.authentication cancelWithCompletionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    if (error != nil) {
                        [run finishWithFailure:
                            [@"Objective-C D087 browser authentication cancel failed: "
                                stringByAppendingString:error.localizedDescription]];
                        return;
                    }
                    run.canonicalD087BrowserCancelCompleted = YES;
                    [run continueD087BrowserCancelIfReady];
                });
            }];
            break;
        }
        case 3: {
            CodexAgentCodexAuthenticationMethodApiKey *method =
                [[CodexAgentCodexAuthenticationMethodApiKey alloc]
                    initWithValue:@"sk-d087-objective-c"];
            [self.canonicalD086Agent.authentication
                authenticateMethod:method
                completionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    if (error != nil) {
                        [run finishWithFailure:
                            [@"Objective-C D087 API-key authentication failed: "
                                stringByAppendingString:error.localizedDescription]];
                        return;
                    }
                    run.canonicalD087AuthenticationCompleted = YES;
                    [run continueD087AuthenticationIfReady];
                });
            }];
            break;
        }
        case 4: {
            [self.canonicalD086Agent.authentication cancelWithCompletionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    if (error != nil) {
                        [run finishWithFailure:
                            [@"Objective-C D087 API-key authentication cancel failed: "
                                stringByAppendingString:error.localizedDescription]];
                        return;
                    }
                    run.canonicalD087CancelCompleted = YES;
                    [run continueD087CancelIfReady];
                });
            }];
            break;
        }
        case 5: {
            [self.canonicalD086Agent.authentication signOutWithCompletionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexAuthentication *authentication =
                        run.canonicalD086Agent.authentication;
                    CodexAgentAgentAuthenticationState *state =
                        (CodexAgentAgentAuthenticationState *)authentication.state.value;
                    CodexAgentBoolean *authenticated =
                        (CodexAgentBoolean *)authentication.isAuthenticated.value;
                    CodexAgentBoolean *authenticating =
                        (CodexAgentBoolean *)authentication.isAuthenticating.value;
                    if (error != nil ||
                        ![state isKindOfClass:[CodexAgentAgentAuthenticationState class]] ||
                        state.status != [CodexAgentAgentAuthenticationStatus signedOut] ||
                        state.pendingSignInUrl != nil || state.deviceVerificationUrl != nil ||
                        state.deviceUserCode != nil || state.failure != nil ||
                        ![authenticated isKindOfClass:[CodexAgentBoolean class]] ||
                        authenticated.boolValue ||
                        ![authenticating isKindOfClass:[CodexAgentBoolean class]] ||
                        authenticating.boolValue) {
                        [run finishWithFailure:
                            @"Objective-C D087 final signOut did not reset authentication state"];
                        return;
                    }
                    [run advanceD087GatewayFunctionsAtStep:6];
                });
            }];
            break;
        }
        case 6: {
            [self.canonicalD086Agent.integrationAuthorization
                authorizeTarget:self.canonicalD087Integration
                completionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexOperationException *exception =
                        [error.kotlinException
                            isKindOfClass:[CodexAgentCodexOperationException class]]
                            ? error.kotlinException
                            : nil;
                    CodexAgentCodexFailure *failure = exception.failure;
                    if (error == nil || failure == nil ||
                        ![failure.code isEqualToString:@"unsupported_feature"] ||
                        ![failure.message isEqualToString:
                            @"Runtime feature MCP_SERVERS is not supported"] ||
                        failure.isRecoverable) {
                        [run finishWithFailure:
                            @"Objective-C D087 integration authorize exposed the wrong failure"];
                        return;
                    }
                    [run advanceD087GatewayFunctionsAtStep:7];
                });
            }];
            break;
        }
        case 7: {
            [self.canonicalD086Agent.integrationAuthorization
                cancelWithCompletionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    if (error != nil) {
                        [run finishWithFailure:
                            @"Objective-C D087 idle integration cancel did not succeed"];
                        return;
                    }
                    [run advanceD087GatewayFunctionsAtStep:8];
                });
            }];
            break;
        }
        case 8: {
            [self.canonicalD086Agent.interactions
                openUrlElicitation:self.canonicalD087Elicitation
                completionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentKotlinThrowable *exception =
                        (CodexAgentKotlinThrowable *)error.kotlinException;
                    if (error == nil ||
                        ![exception isKindOfClass:[CodexAgentKotlinIllegalStateException class]] ||
                        [exception isKindOfClass:[CodexAgentCodexOperationException class]] ||
                        ![exception.message isEqualToString:@"URL elicitation is no longer pending"]) {
                        [run finishWithFailure:
                            @"Objective-C D087 interactions.openUrl exposed the wrong local error"];
                        return;
                    }
                    [run advanceD087GatewayFunctionsAtStep:9];
                });
            }];
            break;
        }
        case 9: {
            [self.canonicalD086Agent.interactions
                resolveApproval:self.canonicalD087Approval
                decision:[CodexAgentAgentApprovalDecision accept]
                completionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentKotlinThrowable *exception =
                        (CodexAgentKotlinThrowable *)error.kotlinException;
                    if (error == nil ||
                        ![exception isKindOfClass:[CodexAgentKotlinIllegalStateException class]] ||
                        [exception isKindOfClass:[CodexAgentCodexOperationException class]] ||
                        ![exception.message isEqualToString:@"Interaction is no longer pending"]) {
                        [run finishWithFailure:
                            @"Objective-C D087 approval resolve exposed the wrong local error"];
                        return;
                    }
                    [run advanceD087GatewayFunctionsAtStep:10];
                });
            }];
            break;
        }
        case 10: {
            [self.canonicalD086Agent.interactions
                resolveElicitation:self.canonicalD087Elicitation
                response:[[CodexAgentAgentElicitationResponse companion] decline]
                completionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentKotlinThrowable *exception =
                        (CodexAgentKotlinThrowable *)error.kotlinException;
                    if (error == nil ||
                        ![exception isKindOfClass:[CodexAgentKotlinIllegalStateException class]] ||
                        [exception isKindOfClass:[CodexAgentCodexOperationException class]] ||
                        ![exception.message isEqualToString:@"Elicitation is no longer pending"]) {
                        [run finishWithFailure:
                            @"Objective-C D087 elicitation resolve exposed the wrong local error"];
                        return;
                    }
                    [run advanceD087GatewayFunctionsAtStep:11];
                });
            }];
            break;
        }
        case 11: {
            [self.canonicalD086Agent.conversations
                renameId:self.canonicalD087ConversationId
                name:@"   "
                completionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentKotlinThrowable *exception =
                        (CodexAgentKotlinThrowable *)error.kotlinException;
                    if (error == nil || exception == nil ||
                        [exception isKindOfClass:[CodexAgentCodexOperationException class]] ||
                        ![exception.message isEqualToString:@"Conversation name must not be blank"]) {
                        [run finishWithFailure:
                            @"Objective-C D087 conversations.rename exposed the wrong local error"];
                        return;
                    }
                    [run advanceD087GatewayFunctionsAtStep:12];
                });
            }];
            break;
        }
        case 12:
            [self.canonicalD087AuthenticationStateObservation close];
            [self.canonicalD087IsAuthenticatedObservation close];
            [self.canonicalD087IsAuthenticatingObservation close];
            self.canonicalD087AuthenticationStateObservation = nil;
            self.canonicalD087IsAuthenticatedObservation = nil;
            self.canonicalD087IsAuthenticatingObservation = nil;
            [self beginD088ConversationFunctions];
            break;
        default:
            [self finishWithFailure:@"Objective-C D087 gateway sequence advanced past its end"];
            break;
    }
}

- (void)beginD088ConversationFunctions {
    CodexAgentCodexConversations *conversations = self.canonicalD086Agent.conversations;
    if (conversations.active.value != nil) {
        [self finishWithFailure:@"Objective-C D088 conversations.active did not start nil"];
        return;
    }
    self.canonicalD088Settings = [[CodexAgentAgentConversationSettings alloc]
        initWithApprovalPreset:[CodexAgentAgentApprovalPreset autoReview]
                   serviceTier:nil];
    [self advanceD088ConversationFunctionsAtStep:0];
}

- (void)advanceD088ConversationFunctionsAtStep:(NSUInteger)step {
    if (self.finishing) return;
    __weak CDXObjectiveCConsumerRun *weakSelf = self;
    CodexAgentCodexConversations *conversations = self.canonicalD086Agent.conversations;
    switch (step) {
        case 0: {
            [conversations openConversationId:nil
                                     settings:self.canonicalD088Settings
                           completionHandler:^(CodexAgentCodexConversation *conversation,
                                               NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    if (error != nil || conversation == nil) {
                        [run finishWithFailure:[@"Objective-C D088 conversations.open failed: "
                            stringByAppendingString:error.localizedDescription ?: @"missing value"]];
                        return;
                    }
                    run.canonicalD088Conversation = conversation;
                    [run advanceD088ConversationFunctionsAtStep:1];
                });
            }];
            break;
        }
        case 1: {
            CodexAgentCodexConversation *conversation = self.canonicalD088Conversation;
            CodexAgentAgentConversationState *state =
                (CodexAgentAgentConversationState *)conversation.state.value;
            NSArray<CodexAgentAgentMessage *> *messages =
                (NSArray<CodexAgentAgentMessage *> *)conversation.currentMessages.value;
            CodexAgentBoolean *canStart = (CodexAgentBoolean *)conversation.canStartTurn.value;
            CodexAgentBoolean *canReload = (CodexAgentBoolean *)conversation.canReload.value;
            CodexAgentBoolean *canCancel = (CodexAgentBoolean *)conversation.canCancelTurn.value;
            CodexAgentBoolean *canRunShell =
                (CodexAgentBoolean *)conversation.canRunShellCommand.value;
            CodexAgentBoolean *turnActive = (CodexAgentBoolean *)conversation.isTurnActive.value;
            if (conversations.active.value != conversation ||
                ![state isKindOfClass:[CodexAgentAgentConversationState class]] ||
                state.status != [CodexAgentAgentConversationStatus ready] ||
                state.conversationId.value.length == 0 || state.failure != nil ||
                ![messages isKindOfClass:[NSArray class]] || messages.count != 0 ||
                conversation.activeTurnProgress.value != nil ||
                ![canStart isKindOfClass:[CodexAgentBoolean class]] || !canStart.boolValue ||
                ![canReload isKindOfClass:[CodexAgentBoolean class]] || !canReload.boolValue ||
                ![canCancel isKindOfClass:[CodexAgentBoolean class]] || canCancel.boolValue ||
                ![canRunShell isKindOfClass:[CodexAgentBoolean class]] || canRunShell.boolValue ||
                ![turnActive isKindOfClass:[CodexAgentBoolean class]] || turnActive.boolValue) {
                [self finishWithFailure:@"Objective-C D088 initial conversation values changed"];
                return;
            }
            self.canonicalD088ConversationId = state.conversationId;
            [conversation cancelTurnWithCompletionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentKotlinThrowable *exception =
                        (CodexAgentKotlinThrowable *)error.kotlinException;
                    if (error == nil ||
                        ![exception isKindOfClass:[CodexAgentKotlinIllegalStateException class]] ||
                        [exception isKindOfClass:[CodexAgentCodexOperationException class]] ||
                        ![exception.message isEqualToString:
                            @"Conversation does not have an active turn"]) {
                        [run finishWithFailure:
                            @"Objective-C D088 idle cancelTurn exposed the wrong local error"];
                        return;
                    }
                    [run.canonicalD086Agent.conversations
                        renameId:run.canonicalD088ConversationId
                        name:@"D088 materialized"
                        completionHandler:^(NSError *renameError) {
                        dispatch_async(dispatch_get_main_queue(), ^{
                            CDXObjectiveCConsumerRun *renamedRun = weakSelf;
                            if (renamedRun == nil || renamedRun.finishing) return;
                            if (renameError != nil) {
                                [renamedRun finishWithFailure:
                                    @"Objective-C D088 conversation materialization failed"];
                                return;
                            }
                            [renamedRun advanceD088ConversationFunctionsAtStep:2];
                        });
                    }];
                });
            }];
            break;
        }
        case 2: {
            CodexAgentAgentConversationState *state =
                (CodexAgentAgentConversationState *)self.canonicalD088Conversation.state.value;
            if (state.status != [CodexAgentAgentConversationStatus ready] || state.failure != nil) {
                [self finishWithFailure:@"Objective-C D088 idle cancelTurn changed state"];
                return;
            }
            [self.canonicalD088Conversation
                runShellCommandCommand:@"echo d088"
                completionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexOperationException *exception =
                        [error.kotlinException
                            isKindOfClass:[CodexAgentCodexOperationException class]]
                            ? error.kotlinException
                            : nil;
                    CodexAgentCodexFailure *failure = exception.failure;
                    if (error == nil || failure == nil ||
                        ![failure.code isEqualToString:@"unsupported_feature"] ||
                        ![failure.message isEqualToString:
                            @"Runtime feature SHELL_COMMANDS is not supported"] ||
                        failure.isRecoverable) {
                        [run finishWithFailure:
                            @"Objective-C D088 runShellCommand exposed the wrong failure"];
                        return;
                    }
                    [run advanceD088ConversationFunctionsAtStep:3];
                });
            }];
            break;
        }
        case 3: {
            [self.canonicalD088Conversation sendPrompt:@"" completionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexOperationException *exception =
                        [error.kotlinException
                            isKindOfClass:[CodexAgentCodexOperationException class]]
                            ? error.kotlinException
                            : nil;
                    CodexAgentCodexFailure *failure = exception.failure;
                    CodexAgentCodexConversation *conversation = run.canonicalD088Conversation;
                    CodexAgentAgentConversationState *state =
                        (CodexAgentAgentConversationState *)conversation.state.value;
                    NSArray<CodexAgentAgentMessage *> *messages =
                        (NSArray<CodexAgentAgentMessage *> *)conversation.currentMessages.value;
                    CodexAgentAgentMessage *message = messages.firstObject;
                    CodexAgentBoolean *canStart =
                        (CodexAgentBoolean *)conversation.canStartTurn.value;
                    CodexAgentBoolean *canReload =
                        (CodexAgentBoolean *)conversation.canReload.value;
                    CodexAgentBoolean *canCancel =
                        (CodexAgentBoolean *)conversation.canCancelTurn.value;
                    CodexAgentBoolean *canRunShell =
                        (CodexAgentBoolean *)conversation.canRunShellCommand.value;
                    CodexAgentBoolean *turnActive =
                        (CodexAgentBoolean *)conversation.isTurnActive.value;
                    if (error == nil || failure == nil ||
                        ![failure.code isEqualToString:@"turn_start_failed"] ||
                        ![failure.message isEqualToString:@"Could not start turn"] ||
                        !failure.isRecoverable ||
                        state.status != [CodexAgentAgentConversationStatus failed] ||
                        ![state.failure.code isEqualToString:@"turn_start_failed"] ||
                        ![state.failure.message isEqualToString:@"Could not start turn"] ||
                        !state.failure.isRecoverable || messages.count != 1 ||
                        message.role != [CodexAgentAgentMessageRole user] ||
                        ![message.text isEqualToString:@""] ||
                        conversation.activeTurnProgress.value != nil ||
                        ![canStart isKindOfClass:[CodexAgentBoolean class]] ||
                        ![canReload isKindOfClass:[CodexAgentBoolean class]] ||
                        ![canCancel isKindOfClass:[CodexAgentBoolean class]] ||
                        ![canRunShell isKindOfClass:[CodexAgentBoolean class]] ||
                        ![turnActive isKindOfClass:[CodexAgentBoolean class]] ||
                        !canStart.boolValue || !canReload.boolValue || canCancel.boolValue ||
                        canRunShell.boolValue || turnActive.boolValue) {
                        [run finishWithFailure:
                            @"Objective-C D088 send(String) exposed the wrong final failure"];
                        return;
                    }
                    [run advanceD088ConversationFunctionsAtStep:4];
                });
            }];
            break;
        }
        case 4: {
            [self.canonicalD088Conversation reloadWithCompletionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexConversation *conversation = run.canonicalD088Conversation;
                    CodexAgentAgentConversationState *state =
                        (CodexAgentAgentConversationState *)conversation.state.value;
                    NSArray *messages = (NSArray *)conversation.currentMessages.value;
                    if (error != nil || state.status != [CodexAgentAgentConversationStatus ready] ||
                        state.failure != nil || state.conversation == nil || messages.count != 0 ||
                        conversation.activeTurnProgress.value != nil) {
                        [run finishWithFailure:
                            @"Objective-C D088 reload did not restore canonical Ready state"];
                        return;
                    }
                    run.canonicalD088Request = [[CodexAgentAgentTurnRequest alloc]
                        initWithPrompt:@""
                        clientMessageId:@"d088-objective-c-request"
                        model:@"d088-model"
                        effort:@"medium"
                        serviceTier:@"fast"
                        approvalPreset:[CodexAgentAgentApprovalPreset strict]
                        capabilities:[NSSet set]
                        invocations:@[]
                        collaborationMode:[CodexAgentAgentCollaborationMode default_]];
                    [run advanceD088ConversationFunctionsAtStep:5];
                });
            }];
            break;
        }
        case 5: {
            [self.canonicalD088Conversation
                sendRequest:self.canonicalD088Request
                completionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexOperationException *exception =
                        [error.kotlinException
                            isKindOfClass:[CodexAgentCodexOperationException class]]
                            ? error.kotlinException
                            : nil;
                    CodexAgentCodexFailure *failure = exception.failure;
                    CodexAgentCodexConversation *conversation = run.canonicalD088Conversation;
                    CodexAgentAgentConversationState *state =
                        (CodexAgentAgentConversationState *)conversation.state.value;
                    NSArray<CodexAgentAgentMessage *> *messages =
                        (NSArray<CodexAgentAgentMessage *> *)conversation.currentMessages.value;
                    CodexAgentAgentMessage *message = messages.firstObject;
                    CodexAgentBoolean *canStart =
                        (CodexAgentBoolean *)conversation.canStartTurn.value;
                    CodexAgentBoolean *canReload =
                        (CodexAgentBoolean *)conversation.canReload.value;
                    CodexAgentBoolean *canCancel =
                        (CodexAgentBoolean *)conversation.canCancelTurn.value;
                    CodexAgentBoolean *canRunShell =
                        (CodexAgentBoolean *)conversation.canRunShellCommand.value;
                    CodexAgentBoolean *turnActive =
                        (CodexAgentBoolean *)conversation.isTurnActive.value;
                    if (error == nil || failure == nil ||
                        ![failure.code isEqualToString:@"turn_start_failed"] ||
                        ![failure.message isEqualToString:@"Could not start turn"] ||
                        !failure.isRecoverable ||
                        state.status != [CodexAgentAgentConversationStatus failed] ||
                        ![state.failure.code isEqualToString:@"turn_start_failed"] ||
                        ![state.failure.message isEqualToString:@"Could not start turn"] ||
                        !state.failure.isRecoverable || messages.count != 1 ||
                        ![message.clientMessageId isEqualToString:@"d088-objective-c-request"] ||
                        message.role != [CodexAgentAgentMessageRole user] ||
                        ![message.text isEqualToString:@""] ||
                        conversation.activeTurnProgress.value != nil ||
                        ![canStart isKindOfClass:[CodexAgentBoolean class]] ||
                        ![canReload isKindOfClass:[CodexAgentBoolean class]] ||
                        ![canCancel isKindOfClass:[CodexAgentBoolean class]] ||
                        ![canRunShell isKindOfClass:[CodexAgentBoolean class]] ||
                        ![turnActive isKindOfClass:[CodexAgentBoolean class]] ||
                        !canStart.boolValue || !canReload.boolValue || canCancel.boolValue ||
                        canRunShell.boolValue || turnActive.boolValue) {
                        [run finishWithFailure:
                            @"Objective-C D088 send(AgentTurnRequest) exposed the wrong final failure"];
                        return;
                    }
                    [run advanceD088ConversationFunctionsAtStep:6];
                });
            }];
            break;
        }
        case 6: {
            [self.canonicalD088Conversation reloadWithCompletionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentCodexConversation *conversation = run.canonicalD088Conversation;
                    CodexAgentAgentConversationState *state =
                        (CodexAgentAgentConversationState *)conversation.state.value;
                    if (error != nil || state.status != [CodexAgentAgentConversationStatus ready] ||
                        state.failure != nil ||
                        [(NSArray *)conversation.currentMessages.value count] != 0) {
                        [run finishWithFailure:
                            @"Objective-C D088 second reload did not restore Ready state"];
                        return;
                    }
                    [run advanceD088ConversationFunctionsAtStep:7];
                });
            }];
            break;
        }
        case 7: {
            [self.canonicalD088Conversation closeWithCompletionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentAgentConversationState *state =
                        (CodexAgentAgentConversationState *)run.canonicalD088Conversation.state.value;
                    if (error != nil || state.status != [CodexAgentAgentConversationStatus closed] ||
                        run.canonicalD086Agent.conversations.active.value != nil) {
                        [run finishWithFailure:
                            @"Objective-C D088 explicit close did not release the active conversation"];
                        return;
                    }
                    [run advanceD088ConversationFunctionsAtStep:8];
                });
            }];
            break;
        }
        case 8: {
            [conversations openConversationId:self.canonicalD088ConversationId
                                     settings:self.canonicalD088Settings
                           completionHandler:^(CodexAgentCodexConversation *conversation,
                                               NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentAgentConversationState *state =
                        (CodexAgentAgentConversationState *)conversation.state.value;
                    if (error != nil || conversation == nil ||
                        state.status != [CodexAgentAgentConversationStatus ready] ||
                        ![state.conversationId.value
                            isEqualToString:run.canonicalD088ConversationId.value] ||
                        run.canonicalD086Agent.conversations.active.value != conversation) {
                        [run finishWithFailure:
                            @"Objective-C D088 reopen did not preserve exact conversation ID"];
                        return;
                    }
                    run.canonicalD088Conversation = conversation;
                    [run advanceD088ConversationFunctionsAtStep:9];
                });
            }];
            break;
        }
        case 9: {
            [conversations listWithCompletionHandler:^(
                NSArray<CodexAgentAgentConversationSummary *> *summaries,
                NSError *error
            ) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    NSUInteger matches = 0;
                    for (CodexAgentAgentConversationSummary *summary in summaries) {
                        if ([summary.conversationId.value
                            isEqualToString:run.canonicalD088ConversationId.value]) {
                            matches += 1;
                        }
                    }
                    if (error != nil || summaries == nil || matches != 0) {
                        [run finishWithFailure:
                            @"Objective-C D088 conversations.list retained the zero-user-turn conversation"];
                        return;
                    }
                    [run advanceD088ConversationFunctionsAtStep:10];
                });
            }];
            break;
        }
        case 10: {
            [conversations readId:self.canonicalD088ConversationId
                completionHandler:^(CodexAgentAgentConversation *value, NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    if (error != nil || value == nil ||
                        ![value.summary.conversationId.value
                            isEqualToString:run.canonicalD088ConversationId.value]) {
                        [run finishWithFailure:
                            @"Objective-C D088 conversations.read lost the exact reopened ID"];
                        return;
                    }
                    [run advanceD088ConversationFunctionsAtStep:11];
                });
            }];
            break;
        }
        case 11: {
            [conversations deleteId:self.canonicalD088ConversationId
                completionHandler:^(NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    CodexAgentAgentConversationState *state =
                        (CodexAgentAgentConversationState *)run.canonicalD088Conversation.state.value;
                    if (error != nil || state.status != [CodexAgentAgentConversationStatus closed] ||
                        run.canonicalD086Agent.conversations.active.value != nil) {
                        [run finishWithFailure:
                            @"Objective-C D088 active delete did not close and release ownership"];
                        return;
                    }
                    [run advanceD088ConversationFunctionsAtStep:12];
                });
            }];
            break;
        }
        case 12: {
            [conversations listWithCompletionHandler:^(
                NSArray<CodexAgentAgentConversationSummary *> *summaries,
                NSError *error
            ) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    CDXObjectiveCConsumerRun *run = weakSelf;
                    if (run == nil || run.finishing) return;
                    BOOL containsDeleted = NO;
                    for (CodexAgentAgentConversationSummary *summary in summaries) {
                        containsDeleted |= [summary.conversationId.value
                            isEqualToString:run.canonicalD088ConversationId.value];
                    }
                    if (error != nil || summaries == nil || containsDeleted) {
                        [run finishWithFailure:
                            @"Objective-C D088 final list retained the deleted conversation"];
                        return;
                    }
                    [run closeCanonicalHost];
                });
            }];
            break;
        }
        default:
            [self finishWithFailure:@"Objective-C D088 conversation sequence advanced past its end"];
            break;
    }
}

- (void)closeCanonicalHost {
    __weak CDXObjectiveCConsumerRun *weakSelf = self;
    [self.canonicalHost closeWithCompletionHandler:^(NSError *error) {
        dispatch_async(dispatch_get_main_queue(), ^{
            CDXObjectiveCConsumerRun *run = weakSelf;
            if (run == nil || run.finishing) return;
            if (error != nil) {
                [run finishWithFailure:error.localizedDescription];
                return;
            }
            run.canonicalCloseCompleted = YES;
            [run continueCanonicalCloseIfReady];
        });
    }];
}

- (void)continueCanonicalCloseIfReady {
    if (!self.canonicalCloseCompleted || !self.canonicalObservedClosed ||
        self.canonicalCloseAdvanced || self.finishing) return;
    self.canonicalCloseAdvanced = YES;
    id current = self.canonicalHost.lifecycleState.value;
    if (![current isKindOfClass:[CodexAgentCodexHostStateClosed class]] ||
        self.canonicalHostChangeCount < 4) {
        [self finishWithFailure:@"Objective-C canonical close omitted Closed state"];
        return;
    }
    [self.canonicalHostObservation close];
    self.canonicalHostObservation = nil;
    self.canonicalHost = nil;
    [self startLegacyLifecycle];
}

- (void)startLegacyLifecycle {
    __weak CDXObjectiveCConsumerRun *weakSelf = self;
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
    [self.canonicalHostObservation close];
    self.canonicalHostObservation = nil;
    [self.canonicalD087AuthenticationStateObservation close];
    [self.canonicalD087IsAuthenticatedObservation close];
    [self.canonicalD087IsAuthenticatingObservation close];
    self.canonicalD087AuthenticationStateObservation = nil;
    self.canonicalD087IsAuthenticatedObservation = nil;
    self.canonicalD087IsAuthenticatingObservation = nil;

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
    void (^closeLegacyHost)(void) = ^{
        CDXObjectiveCConsumerRun *run = weakSelf;
        if (run == nil) return;
        if (run.host == nil) {
            complete(nil);
            return;
        }
        [run.host disposeWithCompletion:^(CDXOperationResult *result) {
            CDXObjectiveCConsumerRun *completedRun = weakSelf;
            if (completedRun == nil) return;
            complete(result.success ? nil : [completedRun describeFailure:result.failure
                prefix:@"Objective-C host cleanup failed"]);
        }];
    };
    CodexAgentCodexHost *canonicalHost = self.canonicalHost;
    self.canonicalHost = nil;
    if (canonicalHost == nil) {
        closeLegacyHost();
        return;
    }
    [canonicalHost closeWithCompletionHandler:^(NSError *error) {
        dispatch_async(dispatch_get_main_queue(), ^{
            if (error != nil && failure == nil) {
                complete([@"Objective-C canonical host cleanup failed: "
                    stringByAppendingString:error.localizedDescription]);
                return;
            }
            closeLegacyHost();
        });
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
    self.canonicalHostObservation = nil;
    self.canonicalD087AuthenticationStateObservation = nil;
    self.canonicalD087IsAuthenticatedObservation = nil;
    self.canonicalD087IsAuthenticatingObservation = nil;
    self.workspaceURL = nil;
    self.canonicalWorkspaceURL = nil;
    self.canonicalHost = nil;
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
