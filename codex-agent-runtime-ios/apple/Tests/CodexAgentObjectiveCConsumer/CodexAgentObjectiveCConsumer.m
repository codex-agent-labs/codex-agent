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
    if (integration.server != authorized ||
        ![integration.id isEqualToString:@"oauth-server"] ||
        ![integration.displayName isEqualToString:@"OAuth Server"]) {
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
    if (integration.connector != connector ||
        ![integration.id isEqualToString:@"d074-connector"] ||
        ![integration.displayName isEqualToString:@"D074 Connector"]) {
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
