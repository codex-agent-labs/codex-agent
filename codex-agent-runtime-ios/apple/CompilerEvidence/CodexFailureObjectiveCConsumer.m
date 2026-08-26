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
    CodexAgentAgentConversationSummary *summary = [[CodexAgentAgentConversationSummary alloc]
        initWithConversationId:conversationId
                         title:@"Compiler evidence"
         updatedAtEpochSeconds:42];
    return [conversationId.value isEqualToString:@"compiler_evidence"] &&
        summary.conversationId == conversationId &&
        [summary.title isEqualToString:@"Compiler evidence"] &&
        summary.updatedAtEpochSeconds == 42;
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
    CodexAgentAgentMcpEnvironmentVariable *variable =
        [[CodexAgentAgentMcpEnvironmentVariable alloc] initWithName:@"TOKEN" source:remote];
    return local != remote &&
        [variable.name isEqualToString:@"TOKEN"] &&
        variable.source == remote;
}

static BOOL consumeD065AppleValues(void) {
    CodexAgentAgentApprovalPreset *approvalAutoReview =
        [CodexAgentAgentApprovalPreset autoReview];
    CodexAgentAgentCapability *webSearch = [CodexAgentAgentCapability webSearch];
    CodexAgentAgentElicitationValidationReason *missingRequired =
        [CodexAgentAgentElicitationValidationReason missingRequired];
    CodexAgentAgentMcpToolApproval *promptApproval = [CodexAgentAgentMcpToolApproval prompt];
    CodexAgentAgentPlanStepStatus *pendingStep = [CodexAgentAgentPlanStepStatus pending];
    CodexAgentAgentSkillScope *systemScope = [CodexAgentAgentSkillScope system];

    NSArray *enumValues = @[
        [CodexAgentAgentApprovalPreset never], approvalAutoReview,
        [CodexAgentAgentApprovalPreset askMe], [CodexAgentAgentApprovalPreset strict],
        [CodexAgentAgentAuthenticationStatus signedOut],
        [CodexAgentAgentAuthenticationStatus authenticating],
        [CodexAgentAgentAuthenticationStatus authenticated], webSearch,
        [CodexAgentAgentCatalogFreshness live], [CodexAgentAgentCatalogFreshness freshCache],
        [CodexAgentAgentCatalogFreshness staleCache],
        [CodexAgentAgentConversationStatus theNew], [CodexAgentAgentConversationStatus opening],
        [CodexAgentAgentConversationStatus ready],
        [CodexAgentAgentConversationStatus startingTurn],
        [CodexAgentAgentConversationStatus runningTurn],
        [CodexAgentAgentConversationStatus cancellingTurn],
        [CodexAgentAgentConversationStatus reloading], [CodexAgentAgentConversationStatus failed],
        [CodexAgentAgentConversationStatus closed],
        [CodexAgentAgentElicitationAction accept], [CodexAgentAgentElicitationAction decline],
        [CodexAgentAgentElicitationAction cancel], missingRequired,
        [CodexAgentAgentElicitationValidationReason unknownField],
        [CodexAgentAgentElicitationValidationReason invalidType],
        [CodexAgentAgentElicitationValidationReason nonFiniteNumber],
        [CodexAgentAgentElicitationValidationReason belowMinimum],
        [CodexAgentAgentElicitationValidationReason aboveMaximum],
        [CodexAgentAgentElicitationValidationReason nonInteger],
        [CodexAgentAgentElicitationValidationReason invalidFormat],
        [CodexAgentAgentElicitationValidationReason invalidSelection],
        [CodexAgentAgentElicitationValidationReason duplicateSelection],
        [CodexAgentAgentFormFieldType string], [CodexAgentAgentFormFieldType number],
        [CodexAgentAgentFormFieldType integer], [CodexAgentAgentFormFieldType boolean],
        [CodexAgentAgentFormFieldType singleSelect], [CodexAgentAgentFormFieldType multiSelect],
        [CodexAgentAgentFormStringFormat email], [CodexAgentAgentFormStringFormat uri],
        [CodexAgentAgentFormStringFormat date], [CodexAgentAgentFormStringFormat dateTime],
        [CodexAgentAgentHookRunStatus running], [CodexAgentAgentHookRunStatus completed],
        [CodexAgentAgentHookRunStatus failed], [CodexAgentAgentHookRunStatus blocked],
        [CodexAgentAgentHookRunStatus stopped], [CodexAgentAgentHookTrustStatus managed],
        [CodexAgentAgentHookTrustStatus untrusted], [CodexAgentAgentHookTrustStatus trusted],
        [CodexAgentAgentHookTrustStatus modified],
        [CodexAgentAgentIntegrationAuthorizationStatus idle],
        [CodexAgentAgentIntegrationAuthorizationStatus starting],
        [CodexAgentAgentIntegrationAuthorizationStatus awaitingCompletion],
        [CodexAgentAgentIntegrationAuthorizationStatus authorized],
        [CodexAgentAgentIntegrationAuthorizationStatus failed],
        [CodexAgentAgentMcpAuthStatus unknown], [CodexAgentAgentMcpAuthStatus unsupported],
        [CodexAgentAgentMcpAuthStatus notLoggedIn], [CodexAgentAgentMcpAuthStatus bearerToken],
        [CodexAgentAgentMcpAuthStatus oauth], [CodexAgentAgentMcpAuthentication oauth],
        [CodexAgentAgentMcpAuthentication chatGpt], [CodexAgentAgentMcpToolApproval auto_],
        promptApproval, [CodexAgentAgentMcpToolApproval writes],
        [CodexAgentAgentMcpToolApproval approve],
        [CodexAgentAgentMcpToolExposureSurface codeMode],
        [CodexAgentAgentMcpToolExposureSurface deferred],
        [CodexAgentAgentMcpToolExposureSurface direct], pendingStep,
        [CodexAgentAgentPlanStepStatus inProgress], [CodexAgentAgentPlanStepStatus completed],
        [CodexAgentAgentPluginAuthPolicy onInstall], [CodexAgentAgentPluginAuthPolicy onUse],
        [CodexAgentAgentPluginInstallPolicy notAvailable],
        [CodexAgentAgentPluginInstallPolicy available],
        [CodexAgentAgentPluginInstallPolicy installedByDefault],
        [CodexAgentAgentResolution preferred], [CodexAgentAgentResolution default_],
        [CodexAgentAgentResolution first], [CodexAgentAgentResourceOrigin user],
        [CodexAgentAgentResourceOrigin workspace], [CodexAgentAgentResourceOrigin plugin],
        [CodexAgentAgentResourceOrigin managed], [CodexAgentAgentResourceOrigin unknown],
        systemScope, [CodexAgentAgentSkillScope user], [CodexAgentAgentSkillScope repo],
        [CodexAgentAgentSkillScope plugin], [CodexAgentAgentSkillScope admin],
        [CodexAgentAgentWorkActivity runningCommand], [CodexAgentAgentWorkActivity writingFiles],
        [CodexAgentCodexAuthorizationPurpose chatGpt],
        [CodexAgentCodexAuthorizationPurpose external],
        [CodexAgentCodexWorkspaceSelectionReason notSelected],
        [CodexAgentCodexWorkspaceSelectionReason notFound],
        [CodexAgentCodexWorkspaceSelectionReason accessRevoked],
        [CodexAgentCodexWorkspaceSelectionReason invalidSelection],
    ];

    CodexAgentAgentFormOption *formOption = [[CodexAgentAgentFormOption alloc]
        initWithValue:@"choice" title:@"Choice" description:nil];
    CodexAgentInt *callbackPort = [CodexAgentInt numberWithInt:3210];
    CodexAgentAgentMcpOauthConfiguration *oauth =
        [[CodexAgentAgentMcpOauthConfiguration alloc] initWithClientId:@"client" callbackPort:callbackPort];
    CodexAgentAgentPluginReference *plugin = [[CodexAgentAgentPluginReference alloc]
        initWithId:@"plugin-id"
        name:@"plugin-name"
        marketplaceName:@"marketplace"
        marketplacePath:@"/marketplace/plugin"
        remotePluginId:@"remote-plugin"];
    CodexAgentAgentPluginSkill *pluginSkill = [[CodexAgentAgentPluginSkill alloc]
        initWithName:@"plugin-skill"
        description:@"Plugin skill"
        isEnabled:YES
        path:@"/plugins/skill"];
    CodexAgentAgentServiceTier *serviceTier = [[CodexAgentAgentServiceTier alloc]
        initWithId:@"fast" name:@"Fast" description:@"Fast tier"];
    CodexAgentLong *nextOffset = [CodexAgentLong numberWithLongLong:12];
    CodexAgentAgentSkillChunk *skillChunk = [[CodexAgentAgentSkillChunk alloc]
        initWithContent:@"chunk" nextOffset:nextOffset totalBytes:34];
    CodexAgentCodexClientInfo *clientInfo = [[CodexAgentCodexClientInfo alloc]
        initWithName:@"compiler"
        title:@"Compiler Evidence"
        version:@"1.0"];
    CodexAgentCodexWorkspace *workspace = [[CodexAgentCodexWorkspace alloc]
        initWithPath:@"/tmp/compiler-workspace" displayName:@"Compiler Workspace"];
    CodexAgentAgentConversationSettings *settings = [[CodexAgentAgentConversationSettings alloc]
        initWithApprovalPreset:approvalAutoReview serviceTier:@"fast"];
    CodexAgentAgentElicitationValidationIssue *issue =
        [[CodexAgentAgentElicitationValidationIssue alloc]
            initWithFieldName:@"email"
                      reason:missingRequired];
    CodexAgentAgentPlanStep *planStep = [[CodexAgentAgentPlanStep alloc]
        initWithText:@"Inspect" status:pendingStep];
    CodexAgentAgentMcpToolConfiguration *tool = [[CodexAgentAgentMcpToolConfiguration alloc]
        initWithApproval:promptApproval];

    return enumValues.count == 100 &&
        [approvalAutoReview.displayName isEqualToString:@"Auto review"] &&
        [webSearch.displayLabel isEqualToString:@"Web search"] &&
        [webSearch.icon isEqualToString:@"🌐"] &&
        [webSearch.id isEqualToString:@"web_search"] &&
        [webSearch.promptLabel isEqualToString:@"Use 🌐 Web search"] &&
        [systemScope.displayName isEqualToString:@"Built in"] &&
        [formOption.value isEqualToString:@"choice"] &&
        [formOption.title isEqualToString:@"Choice"] && formOption.description_ == nil &&
        [oauth.clientId isEqualToString:@"client"] && oauth.callbackPort.intValue == 3210 &&
        [plugin.id isEqualToString:@"plugin-id"] &&
        [plugin.name isEqualToString:@"plugin-name"] &&
        [plugin.marketplaceName isEqualToString:@"marketplace"] &&
        [plugin.marketplacePath isEqualToString:@"/marketplace/plugin"] &&
        [plugin.remotePluginId isEqualToString:@"remote-plugin"] &&
        [plugin.uri isEqualToString:@"plugin://plugin-name@marketplace"] &&
        [pluginSkill.name isEqualToString:@"plugin-skill"] &&
        [pluginSkill.description_ isEqualToString:@"Plugin skill"] && pluginSkill.isEnabled &&
        [pluginSkill.path isEqualToString:@"/plugins/skill"] &&
        [serviceTier.id isEqualToString:@"fast"] && [serviceTier.name isEqualToString:@"Fast"] &&
        [serviceTier.description_ isEqualToString:@"Fast tier"] &&
        [skillChunk.content isEqualToString:@"chunk"] && skillChunk.nextOffset.longLongValue == 12 &&
        skillChunk.totalBytes == 34 && [clientInfo.name isEqualToString:@"compiler"] &&
        [clientInfo.title isEqualToString:@"Compiler Evidence"] &&
        [clientInfo.version isEqualToString:@"1.0"] &&
        [workspace.path isEqualToString:@"/tmp/compiler-workspace"] &&
        [workspace.displayName isEqualToString:@"Compiler Workspace"] &&
        settings.approvalPreset == approvalAutoReview &&
        [settings.serviceTier isEqualToString:@"fast"] &&
        [issue.fieldName isEqualToString:@"email"] && issue.reason == missingRequired &&
        [planStep.text isEqualToString:@"Inspect"] && planStep.status == pendingStep &&
        tool.approval == promptApproval;
}
