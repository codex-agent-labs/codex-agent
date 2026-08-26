import CodexAgent

func consumeCodexFailure() -> (String, String, Bool) {
    let failure = CodexFailure(
        code: "compiler_evidence",
        message: "Compiler evidence",
        isRecoverable: true
    )
    return (failure.code, failure.message, failure.isRecoverable)
}

func consumeConversationId() -> String {
    ConversationId(value: "compiler_evidence").value
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

func consumeAgentMcpEnvironmentSources() -> (AgentMcpEnvironmentSource, AgentMcpEnvironmentSource) {
    (AgentMcpEnvironmentSource.local, AgentMcpEnvironmentSource.remote)
}

func consumeD065AgentApprovalPresets() -> [AgentApprovalPreset] {
    [.never, .autoReview, .askMe, .strict]
}

func consumeD065AgentAuthenticationStatuses() -> [AgentAuthenticationStatus] {
    [.signedOut, .authenticating, .authenticated]
}

func consumeD065AgentCapabilities() -> [AgentCapability] {
    [.webSearch]
}

func consumeD065AgentCatalogFreshnessValues() -> [AgentCatalogFreshness] {
    [.live, .freshCache, .staleCache]
}

func consumeD065AgentConversationStatuses() -> [AgentConversationStatus] {
    [.theNew, .opening, .ready, .startingTurn, .runningTurn, .cancellingTurn, .reloading, .failed, .closed]
}

func consumeD065AgentElicitationActions() -> [AgentElicitationAction] {
    [.accept, .decline, .cancel]
}

func consumeD065AgentElicitationValidationReasons() -> [AgentElicitationValidationReason] {
    [
        .missingRequired, .unknownField, .invalidType, .nonFiniteNumber, .belowMinimum,
        .aboveMaximum, .nonInteger, .invalidFormat, .invalidSelection, .duplicateSelection,
    ]
}

func consumeD065AgentFormFieldTypes() -> [AgentFormFieldType] {
    [.string, .number, .integer, .boolean, .singleSelect, .multiSelect]
}

func consumeD065AgentFormStringFormats() -> [AgentFormStringFormat] {
    [.email, .uri, .date, .dateTime]
}

func consumeD065AgentHookRunStatuses() -> [AgentHookRunStatus] {
    [.running, .completed, .failed, .blocked, .stopped]
}

func consumeD065AgentHookTrustStatuses() -> [AgentHookTrustStatus] {
    [.managed, .untrusted, .trusted, .modified]
}

func consumeD065AgentIntegrationAuthorizationStatuses() -> [AgentIntegrationAuthorizationStatus] {
    [.idle, .starting, .awaitingCompletion, .authorized, .failed]
}

func consumeD065AgentMcpAuthStatuses() -> [AgentMcpAuthStatus] {
    [.unknown, .unsupported, .notLoggedIn, .bearerToken, .oauth]
}

func consumeD065AgentMcpAuthentications() -> [AgentMcpAuthentication] {
    [.oauth, .chatGpt]
}

func consumeD065AgentMcpToolApprovals() -> [AgentMcpToolApproval] {
    [.auto_, .prompt, .writes, .approve]
}

func consumeD065AgentMcpToolExposureSurfaces() -> [AgentMcpToolExposureSurface] {
    [.codeMode, .deferred, .direct]
}

func consumeD065AgentPlanStepStatuses() -> [AgentPlanStepStatus] {
    [.pending, .inProgress, .completed]
}

func consumeD065AgentPluginAuthPolicies() -> [AgentPluginAuthPolicy] {
    [.onInstall, .onUse]
}

func consumeD065AgentPluginInstallPolicies() -> [AgentPluginInstallPolicy] {
    [.notAvailable, .available, .installedByDefault]
}

func consumeD065AgentResolutions() -> [AgentResolution] {
    [.preferred, .default_, .first]
}

func consumeD065AgentResourceOrigins() -> [AgentResourceOrigin] {
    [.user, .workspace, .plugin, .managed, .unknown]
}

func consumeD065AgentSkillScopes() -> [AgentSkillScope] {
    [.system, .user, .repo, .plugin, .admin]
}

func consumeD065AgentWorkActivities() -> [AgentWorkActivity] {
    [.runningCommand, .writingFiles]
}

func consumeD065CodexAuthorizationPurposes() -> [CodexAuthorizationPurpose] {
    [.chatGpt, .external]
}

func consumeD076CodexAuthorizationUrls(
    companion: CodexAuthorizationUrl.Companion
) -> (CodexAuthorizationUrl, String, CodexAuthorizationUrl, CodexAuthorizationPurpose) {
    let chatGpt = companion.chatGpt(value: "https://auth.openai.com/authorize?client=compiler")
    let external = companion.external(value: "https://example.com/oauth")
    return (chatGpt, chatGpt.value, external, external.purpose)
}

func consumeD065CodexWorkspaceSelectionReasons() -> [CodexWorkspaceSelectionReason] {
    [.notSelected, .notFound, .accessRevoked, .invalidSelection]
}

func consumeD065AgentConversationSummary(
    conversationId: ConversationId
) -> (AgentConversationSummary, ConversationId, String, Int64) {
    let summary = AgentConversationSummary(
        conversationId: conversationId,
        title: "Compiler evidence",
        updatedAtEpochSeconds: 1_700_000_000
    )
    return (summary, summary.conversationId, summary.title, summary.updatedAtEpochSeconds)
}

func consumeD065AgentFormOption() -> (AgentFormOption, String?, String, String) {
    let option = AgentFormOption(value: "value", title: "Title", description: "Description")
    return (option, option.description_, option.title, option.value)
}

func consumeD065AgentMcpEnvironmentVariable(
    source: AgentMcpEnvironmentSource?
) -> (AgentMcpEnvironmentVariable, String, AgentMcpEnvironmentSource?) {
    let variable = AgentMcpEnvironmentVariable(name: "TOKEN", source: source)
    return (variable, variable.name, variable.source)
}

func consumeD065AgentMcpOauthConfiguration() -> (AgentMcpOauthConfiguration, KotlinInt?, String?) {
    let configuration = AgentMcpOauthConfiguration(
        clientId: "compiler-client",
        callbackPort: KotlinInt(value: 8_080)
    )
    return (configuration, configuration.callbackPort, configuration.clientId)
}

func consumeD065AgentPluginReference() -> (AgentPluginReference, String, String, String?, String, String?, String) {
    let reference = AgentPluginReference(
        id: "plugin-id",
        name: "plugin",
        marketplaceName: "marketplace",
        marketplacePath: "/marketplace",
        remotePluginId: "remote-id"
    )
    return (
        reference,
        reference.id,
        reference.marketplaceName,
        reference.marketplacePath,
        reference.name,
        reference.remotePluginId,
        reference.uri
    )
}

func consumeD065AgentPluginSkill() -> (AgentPluginSkill, String, Bool, String, String?) {
    let skill = AgentPluginSkill(
        name: "skill",
        description: "Description",
        isEnabled: true,
        path: "/skill"
    )
    return (skill, skill.description_, skill.isEnabled, skill.name, skill.path)
}

func consumeD065AgentServiceTier() -> (AgentServiceTier, String, String, String) {
    let tier = AgentServiceTier(id: "fast", name: "Fast", description: "Fast service")
    return (tier, tier.description_, tier.id, tier.name)
}

func consumeD065AgentSkillChunk() -> (AgentSkillChunk, String, KotlinLong?, Int64) {
    let chunk = AgentSkillChunk(
        content: "content",
        nextOffset: KotlinLong(value: 7),
        totalBytes: 9
    )
    return (chunk, chunk.content, chunk.nextOffset, chunk.totalBytes)
}

func consumeD065CodexClientInfo() -> (CodexClientInfo, String, String, String) {
    let info = CodexClientInfo(name: "compiler", title: "Compiler", version: "1.0")
    return (info, info.name, info.title, info.version)
}

func consumeD065CodexWorkspace() -> (CodexWorkspace, String, String) {
    let workspace = CodexWorkspace(path: "/workspace", displayName: "Workspace")
    return (workspace, workspace.displayName, workspace.path)
}

func consumeD065AgentApprovalPresetDisplayName(
    preset: AgentApprovalPreset
) -> String {
    preset.displayName
}

func consumeD065AgentCapabilityProperties(
    capability: AgentCapability
) -> (String, String?, String, String) {
    (capability.displayLabel, capability.icon, capability.id, capability.promptLabel)
}

func consumeD065AgentSkillScopeDisplayName(scope: AgentSkillScope) -> String {
    scope.displayName
}

func consumeD065AgentConversationSettings(
    approvalPreset: AgentApprovalPreset
) -> (AgentConversationSettings, AgentApprovalPreset, String?) {
    let settings = AgentConversationSettings(approvalPreset: approvalPreset, serviceTier: "fast")
    return (settings, settings.approvalPreset, settings.serviceTier)
}

func consumeD065AgentElicitationValidationIssue(
    reason: AgentElicitationValidationReason
) -> (AgentElicitationValidationIssue, String, AgentElicitationValidationReason) {
    let issue = AgentElicitationValidationIssue(fieldName: "field", reason: reason)
    return (issue, issue.fieldName, issue.reason)
}

func consumeD065AgentPlanStep(
    status: AgentPlanStepStatus
) -> (AgentPlanStep, AgentPlanStepStatus, String) {
    let step = AgentPlanStep(text: "Step", status: status)
    return (step, step.status, step.text)
}

func consumeD065AgentMcpToolConfiguration(
    approval: AgentMcpToolApproval?
) -> (AgentMcpToolConfiguration, AgentMcpToolApproval?) {
    let configuration = AgentMcpToolConfiguration(approval: approval)
    return (configuration, configuration.approval)
}

func consumeD073AgentConnector() -> (
    AgentConnector, String, String, String, String?, Bool, Bool, [String]
) {
    let connector = AgentConnector(
        id: "connector-id",
        name: "Connector",
        description: "Compiler evidence connector",
        installUrl: "https://example.com/install",
        isAccessible: true,
        isEnabled: false,
        pluginNames: ["compiler-plugin"]
    )
    return (
        connector,
        connector.id,
        connector.name,
        connector.description_,
        connector.installUrl,
        connector.isAccessible,
        connector.isEnabled,
        connector.pluginNames
    )
}

func consumeD073AgentElicitationValidation(
    issues: [AgentElicitationValidationIssue]
) -> (AgentElicitationValidation, Bool, [AgentElicitationValidationIssue]) {
    let validation = AgentElicitationValidation(issues: issues)
    return (validation, validation.isValid, validation.issues)
}

func consumeD073AgentFormValueBooleanValue() -> (AgentFormValueBooleanValue, Bool) {
    let value = AgentFormValueBooleanValue(value: true)
    return (value, value.value)
}

func consumeD073AgentFormValueNumber() -> (AgentFormValueNumber, Double) {
    let value = AgentFormValueNumber(value: 73.0)
    return (value, value.value)
}

func consumeD073AgentFormValueText() -> (AgentFormValueText, String) {
    let value = AgentFormValueText(value: "compiler evidence")
    return (value, value.value)
}

func consumeD073AgentFormValueTextList() -> (AgentFormValueTextList, [String]) {
    let value = AgentFormValueTextList(value: ["compiler", "evidence"])
    return (value, value.value)
}

func consumeD073AgentModel(
    serviceTiers: [AgentServiceTier]
) -> (
    AgentModel, String, String, String, [String], String, Bool, [AgentServiceTier], String?
) {
    let model = AgentModel(
        id: "model-id",
        displayName: "Model",
        description: "Compiler evidence model",
        supportedEfforts: ["low", "high"],
        defaultEffort: "high",
        isDefault: true,
        serviceTiers: serviceTiers,
        defaultServiceTier: "fast"
    )
    return (
        model,
        model.id,
        model.displayName,
        model.description_,
        model.supportedEfforts,
        model.defaultEffort,
        model.isDefault,
        model.serviceTiers,
        model.defaultServiceTier
    )
}

func consumeD073AgentPlanProgress(
    steps: [AgentPlanStep]
) -> (AgentPlanProgress, String?, [AgentPlanStep]) {
    let progress = AgentPlanProgress(explanation: "Compiler evidence plan", steps: steps)
    return (progress, progress.explanation, progress.steps)
}

func consumeD073AgentPluginCatalog(
    plugins: [AgentPluginSummary],
    freshness: AgentCatalogFreshness
) -> (AgentPluginCatalog, [AgentPluginSummary], [String], AgentCatalogFreshness) {
    let catalog = AgentPluginCatalog(
        plugins: plugins,
        errors: ["compiler evidence warning"],
        freshness: freshness
    )
    return (catalog, catalog.plugins, catalog.errors, catalog.freshness)
}

func consumeD073AgentPluginDetail(
    summary: AgentPluginSummary,
    skills: [AgentPluginSkill],
    connectors: [AgentConnector]
) -> (
    AgentPluginDetail, AgentPluginSummary, String, [AgentPluginSkill], [AgentConnector], [String], Int32
) {
    let detail = AgentPluginDetail(
        summary: summary,
        description: "Compiler evidence detail",
        skills: skills,
        connectors: connectors,
        mcpServers: ["compiler-server"],
        hookCount: 1
    )
    return (
        detail,
        detail.summary,
        detail.description_,
        detail.skills,
        detail.connectors,
        detail.mcpServers,
        detail.hookCount
    )
}

func consumeD073AgentPluginInstallResult(
    authPolicy: AgentPluginAuthPolicy,
    connectors: [AgentConnector]
) -> (AgentPluginInstallResult, AgentPluginAuthPolicy, [AgentConnector], String?) {
    let result = AgentPluginInstallResult(
        authPolicy: authPolicy,
        connectorsNeedingAuthentication: connectors,
        message: "Compiler evidence install"
    )
    return (result, result.authPolicy, result.connectorsNeedingAuthentication, result.message)
}

func consumeD073AgentPluginSummary(
    reference: AgentPluginReference,
    installPolicy: AgentPluginInstallPolicy,
    authPolicy: AgentPluginAuthPolicy
) -> (
    AgentPluginSummary, AgentPluginReference, String, String, Bool, Bool,
    AgentPluginInstallPolicy, AgentPluginAuthPolicy, Bool, [String], String?, String?, String?, String?
) {
    let summary = AgentPluginSummary(
        reference: reference,
        displayName: "Compiler Plugin",
        description: "Compiler evidence plugin",
        isInstalled: true,
        isEnabled: false,
        installPolicy: installPolicy,
        authPolicy: authPolicy,
        isAvailable: true,
        capabilities: ["skill", "connector"],
        brandColor: "#123456",
        privacyPolicyUrl: "https://example.com/privacy",
        termsOfServiceUrl: "https://example.com/terms",
        websiteUrl: "https://example.com"
    )
    return (
        summary,
        summary.reference,
        summary.displayName,
        summary.description_,
        summary.isInstalled,
        summary.isEnabled,
        summary.installPolicy,
        summary.authPolicy,
        summary.isAvailable,
        summary.capabilities,
        summary.brandColor,
        summary.privacyPolicyUrl,
        summary.termsOfServiceUrl,
        summary.websiteUrl
    )
}

func consumeD073AgentSkill(
    scope: AgentSkillScope,
    origin: AgentResourceOrigin
) -> (
    AgentSkill, String, String, String, String, AgentSkillScope, Bool, String?, [String], Bool,
    AgentResourceOrigin
) {
    let skill = AgentSkill(
        name: "compiler-skill",
        displayName: "Compiler Skill",
        description: "Compiler evidence skill",
        path: "/compiler/skill",
        scope: scope,
        isEnabled: true,
        brandColor: "#654321",
        dependencies: ["git"],
        canUninstall: true,
        origin: origin
    )
    return (
        skill,
        skill.name,
        skill.displayName,
        skill.description_,
        skill.path,
        skill.scope,
        skill.isEnabled,
        skill.brandColor,
        skill.dependencies,
        skill.canUninstall,
        skill.origin
    )
}

func consumeD073AgentSkillCatalog(
    skills: [AgentSkill]
) -> (AgentSkillCatalog, [AgentSkill], [String]) {
    let catalog = AgentSkillCatalog(skills: skills, errors: ["compiler evidence warning"])
    return (catalog, catalog.skills, catalog.errors)
}

func consumeD073CodexPathWorkspaceSelection() -> (CodexPathWorkspaceSelection, String) {
    let selection = CodexPathWorkspaceSelection(path: "/compiler/workspace")
    return (selection, selection.path)
}

func consumeD073CodexWorkspaceResolutionAvailable(
    workspace: CodexWorkspace
) -> (CodexWorkspaceResolutionAvailable, CodexWorkspace) {
    let resolution = CodexWorkspaceResolutionAvailable(workspace: workspace)
    return (resolution, resolution.workspace)
}

func consumeD073CodexWorkspaceResolutionSelectionRequired(
    reason: CodexWorkspaceSelectionReason
) -> (CodexWorkspaceResolutionSelectionRequired, CodexWorkspaceSelectionReason, String) {
    let resolution = CodexWorkspaceResolutionSelectionRequired(
        reason: reason,
        message: "Compiler evidence selection required"
    )
    return (resolution, resolution.reason, resolution.message)
}

func consumeD074AgentElicitation(
    conversationId: ConversationId,
    form: [AgentFormField]?
) -> (AgentElicitation, ConversationId, [AgentFormField]?, String, String, String, String?) {
    let elicitation = AgentElicitation(
        requestId: "compiler-request",
        serverName: "compiler-server",
        conversationId: conversationId,
        message: "Compiler evidence elicitation",
        form: form,
        url: "https://example.com/elicit"
    )
    return (
        elicitation,
        elicitation.conversationId,
        elicitation.form,
        elicitation.message,
        elicitation.requestId,
        elicitation.serverName,
        elicitation.url
    )
}

func consumeD074AgentFormField(
    type: AgentFormFieldType,
    options: [AgentFormOption],
    defaultValue: (any AgentFormValue)?,
    minimum: KotlinDouble?,
    maximum: KotlinDouble?,
    format: AgentFormStringFormat?,
    minimumLength: KotlinLong?,
    maximumLength: KotlinLong?,
    minimumSelections: KotlinLong?,
    maximumSelections: KotlinLong?
) -> (
    AgentFormField, Bool, (any AgentFormValue)?, String?, AgentFormStringFormat?, Bool, Bool,
    KotlinDouble?, KotlinLong?, KotlinLong?, KotlinDouble?, KotlinLong?, KotlinLong?, String,
    [AgentFormOption], String, AgentFormFieldType
) {
    let field = AgentFormField(
        name: "compiler-field",
        title: "Compiler Field",
        description: "Compiler evidence field",
        isRequired: true,
        type: type,
        options: options,
        defaultValue: defaultValue,
        minimum: minimum,
        maximum: maximum,
        format: format,
        minimumLength: minimumLength,
        maximumLength: maximumLength,
        minimumSelections: minimumSelections,
        maximumSelections: maximumSelections,
        allowsOther: true,
        isSecret: false
    )
    return (
        field,
        field.allowsOther,
        field.defaultValue,
        field.description_,
        field.format,
        field.isRequired,
        field.isSecret,
        field.maximum,
        field.maximumLength,
        field.maximumSelections,
        field.minimum,
        field.minimumLength,
        field.minimumSelections,
        field.name,
        field.options,
        field.title,
        field.type
    )
}

func consumeD074AgentHookHandlerCommand() -> (AgentHookHandlerCommand, String, Bool) {
    let handler = AgentHookHandlerCommand(command: "echo compiler", isAsync: true)
    return (handler, handler.command, handler.isAsync)
}

func consumeD074AgentHookHandlerMcpTool() -> (AgentHookHandlerMcpTool, String, String) {
    let handler = AgentHookHandlerMcpTool(server: "compiler-server", tool: "compiler-tool")
    return (handler, handler.server, handler.tool)
}

func consumeD074AgentHook(
    handler: any AgentHookHandler,
    trustStatus: AgentHookTrustStatus,
    origin: AgentResourceOrigin
) -> (
    AgentHook, Bool, Bool, String, String, any AgentHookHandler, Bool, Bool, String, String?,
    AgentResourceOrigin, String?, String, String, String?, Int64, AgentHookTrustStatus
) {
    let hook = AgentHook(
        key: "compiler-hook",
        currentHash: "compiler-hash",
        isEnabled: true,
        eventName: "afterTurn",
        handler: handler,
        isManaged: false,
        source: "PLUGIN",
        sourcePath: "/compiler/hook",
        timeoutSeconds: 74,
        trustStatus: trustStatus,
        matcher: "*.swift",
        pluginId: "compiler-plugin",
        statusMessage: "Compiler evidence hook",
        origin: origin,
        canUninstall: true
    )
    return (
        hook,
        hook.canTrust,
        hook.canUninstall,
        hook.currentHash,
        hook.eventName,
        hook.handler,
        hook.isEnabled,
        hook.isManaged,
        hook.key,
        hook.matcher,
        hook.origin,
        hook.pluginId,
        hook.source,
        hook.sourcePath,
        hook.statusMessage,
        hook.timeoutSeconds,
        hook.trustStatus
    )
}

func consumeD074AgentHookActivity(
    status: AgentHookRunStatus
) -> (AgentHookActivity, [String], String, String, String, AgentHookRunStatus, String?) {
    let activity = AgentHookActivity(
        id: "compiler-activity",
        eventName: "afterTurn",
        handlerType: "command",
        status: status,
        statusMessage: "Compiler evidence activity",
        details: ["compiler detail"]
    )
    return (
        activity,
        activity.details,
        activity.eventName,
        activity.handlerType,
        activity.id,
        activity.status,
        activity.statusMessage
    )
}

func consumeD074AgentHookCatalog(
    hooks: [AgentHook]
) -> (AgentHookCatalog, [String], [AgentHook], [String]) {
    let catalog = AgentHookCatalog(
        hooks: hooks,
        warnings: ["compiler warning"],
        errors: ["compiler error"]
    )
    return (catalog, catalog.errors, catalog.hooks, catalog.warnings)
}

func consumeD074AgentIntegrationConnector(
    connector: AgentConnector
) -> (AgentIntegrationConnector, AgentConnector, String, String) {
    let integration = AgentIntegrationConnector(connector: connector)
    return (integration, integration.connector, integration.displayName, integration.id)
}

func consumeD074AgentInvocationPlugin() -> (AgentInvocationPlugin, String, String, String) {
    let invocation = AgentInvocationPlugin(name: "Compiler Plugin", uri: "plugin://compiler")
    return (invocation, invocation.key, invocation.name, invocation.uri)
}

func consumeD074AgentInvocationSkill() -> (AgentInvocationSkill, String, String, String) {
    let invocation = AgentInvocationSkill(name: "Compiler Skill", path: "/compiler/skill")
    return (invocation, invocation.key, invocation.name, invocation.path)
}

func consumeD074AgentTurnProgress(
    planProgress: AgentPlanProgress?,
    shellExitCode: KotlinInt?,
    workActivity: AgentWorkActivity?,
    hookActivities: [AgentHookActivity]
) -> (
    AgentTurnProgress, String, [AgentHookActivity], Bool, String, AgentPlanProgress?, String,
    KotlinInt?, String, String, AgentWorkActivity?
) {
    let progress = AgentTurnProgress(
        text: "Compiler text",
        commentary: "Compiler commentary",
        reasoning: "Compiler reasoning",
        plan: "Compiler plan",
        planProgress: planProgress,
        shellOutput: "Compiler output",
        shellExitCode: shellExitCode,
        workActivity: workActivity,
        hookActivities: hookActivities,
        isTruncated: true
    )
    return (
        progress,
        progress.commentary,
        progress.hookActivities,
        progress.isTruncated,
        progress.plan,
        progress.planProgress,
        progress.reasoning,
        progress.shellExitCode,
        progress.shellOutput,
        progress.text,
        progress.workActivity
    )
}

func consumeD074CodexAuthenticationMethodApiKey() -> (CodexAuthenticationMethodApiKey, String) {
    let method = CodexAuthenticationMethodApiKey(value: "compiler-api-key")
    return (method, method.value)
}

func consumeD075AgentPendingApproval(
    conversationId: ConversationId
) -> (AgentPendingApproval, ConversationId, String, String, String) {
    let approval = AgentPendingApproval(
        requestId: "compiler-approval",
        conversationId: conversationId,
        title: "Compiler approval",
        details: "Compiler approval details"
    )
    return (
        approval,
        approval.conversationId,
        approval.details,
        approval.requestId,
        approval.title
    )
}

func consumeD075AgentPendingElicitation(
    elicitation: AgentElicitation
) -> (AgentPendingElicitation, ConversationId, AgentElicitation, String) {
    let pending = AgentPendingElicitation(elicitation: elicitation)
    return (pending, pending.conversationId, pending.elicitation, pending.requestId)
}

func consumeD077AgentMcpServer(
    authStatus: AgentMcpAuthStatus,
    configuration: AgentMcpServerConfiguration?,
    origin: AgentResourceOrigin
) -> (
    AgentMcpServer, String, String, AgentMcpAuthStatus, AgentMcpServerConfiguration?,
    AgentResourceOrigin, Bool, Bool, AgentIntegrationMcpServer, AgentMcpServer, String, String
) {
    let server = AgentMcpServer(
        name: "compiler-server",
        displayName: "Compiler Server",
        authStatus: authStatus,
        configuration: configuration,
        origin: origin,
        canRemove: true
    )
    let integration = AgentIntegrationMcpServer(server: server)
    return (
        server,
        server.name,
        server.displayName,
        server.authStatus,
        server.configuration,
        server.origin,
        server.canRemove,
        server.isAuthorized,
        integration,
        integration.server,
        integration.id,
        integration.displayName
    )
}

func consumeD078AgentMcpTransportHttp() -> (
    AgentMcpTransportHttp, String?, [String: String]?, [String: String]?, String?, String
) {
    let transport = AgentMcpTransportHttp(
        url: "https://example.com/compiler-mcp",
        bearerTokenEnvironmentVariable: "COMPILER_TOKEN",
        headers: ["Authorization": "Bearer compiler", "X-Trace": "compiler"],
        environmentHeaders: ["X-Region": "COMPILER_REGION", "X-Workspace": "COMPILER_WORKSPACE"],
        headersHelper: "compiler-headers-helper"
    )
    return (
        transport,
        transport.bearerTokenEnvironmentVariable,
        transport.environmentHeaders,
        transport.headers,
        transport.headersHelper,
        transport.url
    )
}

func consumeD078AgentMcpTransportStdio(
    firstEnvironmentVariable: AgentMcpEnvironmentVariable,
    secondEnvironmentVariable: AgentMcpEnvironmentVariable
) -> (
    AgentMcpTransportStdio, [String], String, [String: String]?, [AgentMcpEnvironmentVariable], String?
) {
    let transport = AgentMcpTransportStdio(
        command: "compiler-mcp",
        arguments: ["--stdio", "--verbose"],
        workingDirectory: "/compiler/workspace",
        environment: ["MODE": "compiler", "TRACE": "enabled"],
        forwardedEnvironment: [firstEnvironmentVariable, secondEnvironmentVariable]
    )
    return (
        transport,
        transport.arguments,
        transport.command,
        transport.environment,
        transport.forwardedEnvironment,
        transport.workingDirectory
    )
}

func consumeD078AgentMcpServerConfiguration(
    transport: any AgentMcpTransport,
    authentication: AgentMcpAuthentication,
    omitToolsFrom: [AgentMcpToolExposureSurface],
    startupTimeoutSeconds: KotlinDouble,
    toolTimeoutSeconds: KotlinDouble,
    defaultToolApproval: AgentMcpToolApproval,
    oauth: AgentMcpOauthConfiguration,
    readTool: AgentMcpToolConfiguration,
    writeTool: AgentMcpToolConfiguration
) -> (
    AgentMcpServerConfiguration, AgentMcpAuthentication?, AgentMcpToolApproval?, [String]?, [String]?,
    String, Bool, Bool, String, AgentMcpOauthConfiguration?, String?, [AgentMcpToolExposureSurface]?,
    [String]?, KotlinDouble?, Bool, KotlinDouble?, [String: AgentMcpToolConfiguration], any AgentMcpTransport
) {
    let configuration = AgentMcpServerConfiguration(
        name: "compiler-server",
        transport: transport,
        authentication: authentication,
        environmentId: "local",
        isEnabled: true,
        isRequired: true,
        supportsParallelToolCalls: true,
        omitToolsFrom: omitToolsFrom,
        startupTimeoutSeconds: startupTimeoutSeconds,
        toolTimeoutSeconds: toolTimeoutSeconds,
        defaultToolApproval: defaultToolApproval,
        enabledTools: ["read", "write"],
        disabledTools: ["delete", "admin"],
        scopes: ["files.read", "files.write"],
        oauth: oauth,
        oauthResource: "https://example.com/compiler-resource",
        tools: ["read": readTool, "write": writeTool]
    )
    return (
        configuration,
        configuration.authentication,
        configuration.defaultToolApproval,
        configuration.disabledTools,
        configuration.enabledTools,
        configuration.environmentId,
        configuration.isEnabled,
        configuration.isRequired,
        configuration.name,
        configuration.oauth,
        configuration.oauthResource,
        configuration.omitToolsFrom,
        configuration.scopes,
        configuration.startupTimeoutSeconds,
        configuration.supportsParallelToolCalls,
        configuration.toolTimeoutSeconds,
        configuration.tools,
        configuration.transport
    )
}

func consumeD078AgentElicitationResponse(
    text: any AgentFormValue,
    number: any AgentFormValue,
    boolean: any AgentFormValue,
    list: any AgentFormValue
) -> (AgentElicitationResponse, AgentElicitationAction, [String: any AgentFormValue]) {
    let response = AgentElicitationResponse(
        action: .accept,
        content: ["text": text, "number": number, "boolean": boolean, "list": list]
    )
    return (response, response.action, response.content)
}

func consumeD079AgentMessage(
    plugin: AgentInvocationPlugin,
    skill: AgentInvocationSkill
) -> (
    AgentMessage, Set<AgentCapability>, String?, AgentCollaborationMode, KotlinInt?, String,
    [any AgentInvocation], String?, String?, AgentMessageRole, String?, String
) {
    let message = AgentMessage(
        id: "compiler-message",
        clientMessageId: "compiler-client-message",
        role: .assistant,
        text: "Compiler message",
        collaborationMode: .plan,
        reasoning: "Compiler reasoning",
        plan: "Compiler plan",
        shellCommand: "compiler command",
        exitCode: KotlinInt(value: 79),
        capabilities: [.webSearch],
        invocations: [plugin, skill]
    )
    return (
        message,
        message.capabilities,
        message.clientMessageId,
        message.collaborationMode,
        message.exitCode,
        message.id,
        message.invocations,
        message.plan,
        message.reasoning,
        message.role,
        message.shellCommand,
        message.text
    )
}

func consumeD079AgentTurnRequest(
    plugin: AgentInvocationPlugin,
    skill: AgentInvocationSkill
) -> (
    AgentTurnRequest, AgentApprovalPreset, Set<AgentCapability>, String?, AgentCollaborationMode,
    String?, [any AgentInvocation], String?, String, String?
) {
    let request = AgentTurnRequest(
        prompt: "Compiler request",
        clientMessageId: "compiler-request-client-message",
        model: "compiler-model",
        effort: "compiler-effort",
        serviceTier: "compiler-tier",
        approvalPreset: .strict,
        capabilities: [.webSearch],
        invocations: [skill, plugin],
        collaborationMode: .plan
    )
    return (
        request,
        request.approvalPreset,
        request.capabilities,
        request.clientMessageId,
        request.collaborationMode,
        request.effort,
        request.invocations,
        request.model,
        request.prompt,
        request.serviceTier
    )
}

func consumeD079AgentConversation(
    summary: AgentConversationSummary,
    firstMessage: AgentMessage,
    secondMessage: AgentMessage
) -> (AgentConversation, [AgentMessage], AgentConversationSummary) {
    let conversation = AgentConversation(summary: summary, messages: [firstMessage, secondMessage])
    return (conversation, conversation.messages, conversation.summary)
}

func consumeD080AgentAuthenticationState(
    status: AgentAuthenticationStatus,
    pendingSignInUrl: CodexAuthorizationUrl,
    deviceVerificationUrl: CodexAuthorizationUrl,
    failure: CodexFailure
) -> (
    AgentAuthenticationState, String?, CodexAuthorizationUrl?, CodexFailure?,
    CodexAuthorizationUrl?, AgentAuthenticationStatus
) {
    let state = AgentAuthenticationState(
        status: status,
        pendingSignInUrl: pendingSignInUrl,
        deviceVerificationUrl: deviceVerificationUrl,
        deviceUserCode: "compiler-device-code",
        failure: failure
    )
    return (
        state,
        state.deviceUserCode,
        state.deviceVerificationUrl,
        state.failure,
        state.pendingSignInUrl,
        state.status
    )
}

func consumeD080AgentConversationState(
    status: AgentConversationStatus,
    conversationId: ConversationId,
    conversation: AgentConversation,
    turnProgress: AgentTurnProgress,
    failure: CodexFailure
) -> (
    AgentConversationState, Bool, Bool, Bool, AgentConversation?, ConversationId?, String?,
    CodexFailure?, String?, String?, AgentConversationStatus, AgentTurnProgress
) {
    let state = AgentConversationState(
        status: status,
        conversationId: conversationId,
        conversation: conversation,
        turnProgress: turnProgress,
        model: "compiler-model",
        effort: "compiler-effort",
        serviceTier: "compiler-tier",
        failure: failure
    )
    return (
        state,
        state.canCancelTurn,
        state.canReload,
        state.canStartTurn,
        state.conversation,
        state.conversationId,
        state.effort,
        state.failure,
        state.model,
        state.serviceTier,
        state.status,
        state.turnProgress
    )
}

func consumeD080AgentIntegrationAuthorizationState(
    status: AgentIntegrationAuthorizationStatus,
    target: any AgentIntegration,
    failure: CodexFailure
) -> (
    AgentIntegrationAuthorizationState, CodexFailure?, AgentIntegrationAuthorizationStatus,
    (any AgentIntegration)?
) {
    let state = AgentIntegrationAuthorizationState(status: status, target: target, failure: failure)
    return (state, state.failure, state.status, state.target)
}

func consumeD080AgentInteractionState(
    pending: [any AgentPendingInteraction],
    resolvingRequestIds: Set<String>,
    failure: CodexFailure,
    conversationId: ConversationId,
    interaction: any AgentPendingInteraction
) -> (
    AgentInteractionState, CodexFailure?, [any AgentPendingInteraction], Set<String>,
    [any AgentPendingInteraction], Bool
) {
    let state = AgentInteractionState(
        pending: pending,
        resolvingRequestIds: resolvingRequestIds,
        failure: failure
    )
    return (
        state,
        state.failure,
        state.pending,
        state.resolvingRequestIds,
        state.pendingFor(conversationId: conversationId),
        state.isResolving(interaction: interaction)
    )
}
