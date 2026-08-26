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

static BOOL consumeD073OrdinaryValues(
    CodexAgentAgentElicitationValidationIssue *validationIssue,
    CodexAgentAgentServiceTier *serviceTier,
    CodexAgentAgentPlanStep *planStep,
    CodexAgentAgentPluginReference *pluginReference,
    CodexAgentAgentPluginSkill *pluginSkill,
    CodexAgentCodexWorkspace *workspace,
    CodexAgentAgentPluginInstallPolicy *availableInstallPolicy,
    CodexAgentAgentPluginAuthPolicy *authPolicy,
    CodexAgentAgentCatalogFreshness *freshCache,
    CodexAgentAgentSkillScope *repoScope,
    CodexAgentAgentResourceOrigin *workspaceOrigin,
    CodexAgentCodexWorkspaceSelectionReason *notFoundReason
) {
    CodexAgentAgentConnector *connector = [[CodexAgentAgentConnector alloc]
        initWithId:@"connector-id"
        name:@"Connector"
        description:@"Connector description"
        installUrl:@"https://example.com/install"
        isAccessible:YES
        isEnabled:NO
        pluginNames:@[@"plugin"]];
    CodexAgentAgentElicitationValidation *validation =
        [[CodexAgentAgentElicitationValidation alloc] initWithIssues:@[validationIssue]];
    CodexAgentAgentFormValueBooleanValue *booleanValue =
        [[CodexAgentAgentFormValueBooleanValue alloc] initWithValue:YES];
    CodexAgentAgentFormValueNumber *numberValue =
        [[CodexAgentAgentFormValueNumber alloc] initWithValue:7.5];
    CodexAgentAgentFormValueText *textValue =
        [[CodexAgentAgentFormValueText alloc] initWithValue:@"text"];
    CodexAgentAgentFormValueTextList *textListValue =
        [[CodexAgentAgentFormValueTextList alloc] initWithValue:@[@"first", @"second"]];
    CodexAgentAgentModel *model = [[CodexAgentAgentModel alloc]
        initWithId:@"model-id"
        displayName:@"Model"
        description:@"Model description"
        supportedEfforts:@[@"low", @"high"]
        defaultEffort:@"high"
        isDefault:YES
        serviceTiers:@[serviceTier]
        defaultServiceTier:@"fast"];
    CodexAgentAgentPlanProgress *planProgress = [[CodexAgentAgentPlanProgress alloc]
        initWithExplanation:@"Plan explanation" steps:@[planStep]];
    CodexAgentAgentPluginSummary *pluginSummary = [[CodexAgentAgentPluginSummary alloc]
        initWithReference:pluginReference
        displayName:@"Plugin"
        description:@"Plugin description"
        isInstalled:YES
        isEnabled:NO
        installPolicy:availableInstallPolicy
        authPolicy:authPolicy
        isAvailable:YES
        capabilities:@[@"tools", @"hooks"]
        brandColor:@"#123456"
        privacyPolicyUrl:@"https://example.com/privacy"
        termsOfServiceUrl:@"https://example.com/terms"
        websiteUrl:@"https://example.com"];
    CodexAgentAgentPluginCatalog *pluginCatalog = [[CodexAgentAgentPluginCatalog alloc]
        initWithPlugins:@[pluginSummary]
        errors:@[@"catalog warning"]
        freshness:freshCache];
    CodexAgentAgentPluginDetail *pluginDetail = [[CodexAgentAgentPluginDetail alloc]
        initWithSummary:pluginSummary
        description:@"Detailed plugin"
        skills:@[pluginSkill]
        connectors:@[connector]
        mcpServers:@[@"filesystem"]
        hookCount:3];
    CodexAgentAgentPluginInstallResult *installResult =
        [[CodexAgentAgentPluginInstallResult alloc]
            initWithAuthPolicy:authPolicy
            connectorsNeedingAuthentication:@[connector]
            message:@"Authenticate connector"];
    CodexAgentAgentSkill *skill = [[CodexAgentAgentSkill alloc]
        initWithName:@"skill"
        displayName:@"Skill"
        description:@"Skill description"
        path:@"/skills/skill"
        scope:repoScope
        isEnabled:YES
        brandColor:@"#abcdef"
        dependencies:@[@"git"]
        canUninstall:YES
        origin:workspaceOrigin];
    CodexAgentAgentSkillCatalog *skillCatalog = [[CodexAgentAgentSkillCatalog alloc]
        initWithSkills:@[skill] errors:@[@"skill warning"]];
    CodexAgentCodexPathWorkspaceSelection *pathSelection =
        [[CodexAgentCodexPathWorkspaceSelection alloc] initWithPath:@"/workspace"];
    CodexAgentCodexWorkspaceResolutionAvailable *available =
        [[CodexAgentCodexWorkspaceResolutionAvailable alloc] initWithWorkspace:workspace];
    CodexAgentCodexWorkspaceResolutionSelectionRequired *selectionRequired =
        [[CodexAgentCodexWorkspaceResolutionSelectionRequired alloc]
            initWithReason:notFoundReason
            message:@"Choose a workspace"];

    return [connector.id isEqualToString:@"connector-id"] &&
        [connector.name isEqualToString:@"Connector"] &&
        [connector.description_ isEqualToString:@"Connector description"] &&
        [connector.installUrl isEqualToString:@"https://example.com/install"] &&
        connector.isAccessible && !connector.isEnabled &&
        [connector.pluginNames isEqualToArray:@[@"plugin"]] &&
        [validation.issues isEqualToArray:@[validationIssue]] && !validation.isValid &&
        booleanValue.value && numberValue.value == 7.5 &&
        [textValue.value isEqualToString:@"text"] &&
        [textListValue.value isEqualToArray:@[@"first", @"second"]] &&
        [model.id isEqualToString:@"model-id"] &&
        [model.displayName isEqualToString:@"Model"] &&
        [model.description_ isEqualToString:@"Model description"] &&
        [model.supportedEfforts isEqualToArray:@[@"low", @"high"]] &&
        [model.defaultEffort isEqualToString:@"high"] && model.isDefault &&
        [model.serviceTiers isEqualToArray:@[serviceTier]] &&
        [model.defaultServiceTier isEqualToString:@"fast"] &&
        [planProgress.explanation isEqualToString:@"Plan explanation"] &&
        [planProgress.steps isEqualToArray:@[planStep]] &&
        [pluginCatalog.plugins isEqualToArray:@[pluginSummary]] &&
        [pluginCatalog.errors isEqualToArray:@[@"catalog warning"]] &&
        pluginCatalog.freshness == freshCache &&
        pluginDetail.summary == pluginSummary &&
        [pluginDetail.description_ isEqualToString:@"Detailed plugin"] &&
        [pluginDetail.skills isEqualToArray:@[pluginSkill]] &&
        [pluginDetail.connectors isEqualToArray:@[connector]] &&
        [pluginDetail.mcpServers isEqualToArray:@[@"filesystem"]] &&
        pluginDetail.hookCount == 3 &&
        installResult.authPolicy == authPolicy &&
        [installResult.connectorsNeedingAuthentication isEqualToArray:@[connector]] &&
        [installResult.message isEqualToString:@"Authenticate connector"] &&
        pluginSummary.reference == pluginReference &&
        [pluginSummary.displayName isEqualToString:@"Plugin"] &&
        [pluginSummary.description_ isEqualToString:@"Plugin description"] &&
        pluginSummary.isInstalled && !pluginSummary.isEnabled &&
        pluginSummary.installPolicy == availableInstallPolicy &&
        pluginSummary.authPolicy == authPolicy &&
        pluginSummary.isAvailable &&
        [pluginSummary.capabilities isEqualToArray:@[@"tools", @"hooks"]] &&
        [pluginSummary.brandColor isEqualToString:@"#123456"] &&
        [pluginSummary.privacyPolicyUrl isEqualToString:@"https://example.com/privacy"] &&
        [pluginSummary.termsOfServiceUrl isEqualToString:@"https://example.com/terms"] &&
        [pluginSummary.websiteUrl isEqualToString:@"https://example.com"] &&
        [skill.name isEqualToString:@"skill"] &&
        [skill.displayName isEqualToString:@"Skill"] &&
        [skill.description_ isEqualToString:@"Skill description"] &&
        [skill.path isEqualToString:@"/skills/skill"] &&
        skill.scope == repoScope && skill.isEnabled &&
        [skill.brandColor isEqualToString:@"#abcdef"] &&
        [skill.dependencies isEqualToArray:@[@"git"]] && skill.canUninstall &&
        skill.origin == workspaceOrigin &&
        [skillCatalog.skills isEqualToArray:@[skill]] &&
        [skillCatalog.errors isEqualToArray:@[@"skill warning"]] &&
        [pathSelection.path isEqualToString:@"/workspace"] &&
        available.workspace == workspace &&
        selectionRequired.reason == notFoundReason &&
        [selectionRequired.message isEqualToString:@"Choose a workspace"];
}
