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

static BOOL consumeD076AuthorizationUrls(
    CodexAgentCodexAuthorizationUrlCompanion *companion
) {
    CodexAgentCodexAuthorizationUrl *chatGpt =
        [companion chatGptValue:@"https://auth.openai.com/oauth/authorize"];
    CodexAgentCodexAuthorizationUrl *external =
        [companion externalValue:@"https://example.com/oauth"];
    return [chatGpt.value isEqualToString:@"https://auth.openai.com/oauth/authorize"] &&
        external.purpose != nil;
}

static BOOL consumeD077McpServerValues(
    CodexAgentAgentMcpAuthStatus *oauthStatus,
    CodexAgentAgentResourceOrigin *workspaceOrigin
) {
    CodexAgentAgentMcpServer *server = [[CodexAgentAgentMcpServer alloc]
        initWithName:@"compiler-mcp"
        displayName:@"Compiler MCP"
        authStatus:oauthStatus
        configuration:nil
        origin:workspaceOrigin
        canRemove:YES];
    CodexAgentAgentIntegrationMcpServer *integration =
        [[CodexAgentAgentIntegrationMcpServer alloc] initWithServer:server];
    return [server.name isEqualToString:@"compiler-mcp"] &&
        [server.displayName isEqualToString:@"Compiler MCP"] &&
        server.authStatus == oauthStatus &&
        server.configuration == nil &&
        server.origin == workspaceOrigin &&
        server.canRemove &&
        server.isAuthorized &&
        integration.server == server &&
        [integration.id isEqualToString:@"compiler-mcp"] &&
        [integration.displayName isEqualToString:@"Compiler MCP"];
}

static BOOL consumeD078McpConfigurationValues(
    CodexAgentAgentMcpAuthentication *authentication,
    CodexAgentAgentMcpToolExposureSurface *exposureSurface,
    CodexAgentAgentMcpToolApproval *approval,
    CodexAgentAgentMcpOauthConfiguration *oauth,
    CodexAgentAgentMcpToolConfiguration *toolConfiguration,
    CodexAgentAgentMcpEnvironmentVariable *forwardedEnvironment,
    CodexAgentAgentElicitationAction *elicitationAction,
    id<CodexAgentAgentFormValue> formValue
) {
    NSDictionary<NSString *, NSString *> *headers = @{@"X-Static": @"value"};
    NSDictionary<NSString *, NSString *> *environmentHeaders = @{@"Authorization": @"MCP_AUTH"};
    CodexAgentAgentMcpTransportHttp *http = [[CodexAgentAgentMcpTransportHttp alloc]
        initWithUrl:@"https://mcp.example.com"
        bearerTokenEnvironmentVariable:@"MCP_TOKEN"
        headers:headers
        environmentHeaders:environmentHeaders
        headersHelper:@"mcp-headers"];
    NSString *httpUrl = http.url;
    NSString *bearerTokenEnvironmentVariable = http.bearerTokenEnvironmentVariable;
    NSDictionary<NSString *, NSString *> *returnedHeaders = http.headers;
    NSDictionary<NSString *, NSString *> *returnedEnvironmentHeaders = http.environmentHeaders;
    NSString *headersHelper = http.headersHelper;

    NSArray<NSString *> *arguments = @[@"server.js", @"--stdio"];
    NSDictionary<NSString *, NSString *> *environment = @{@"STATIC": @"value"};
    NSArray<CodexAgentAgentMcpEnvironmentVariable *> *forwarded = @[forwardedEnvironment];
    CodexAgentAgentMcpTransportStdio *stdio = [[CodexAgentAgentMcpTransportStdio alloc]
        initWithCommand:@"node"
        arguments:arguments
        workingDirectory:@"/workspace"
        environment:environment
        forwardedEnvironment:forwarded];
    NSString *command = stdio.command;
    NSArray<NSString *> *returnedArguments = stdio.arguments;
    NSString *workingDirectory = stdio.workingDirectory;
    NSDictionary<NSString *, NSString *> *returnedEnvironment = stdio.environment;
    NSArray<CodexAgentAgentMcpEnvironmentVariable *> *returnedForwarded = stdio.forwardedEnvironment;

    CodexAgentDouble *startupTimeout = [CodexAgentDouble numberWithDouble:3.5];
    CodexAgentDouble *toolTimeout = [CodexAgentDouble numberWithDouble:9.0];
    NSArray<CodexAgentAgentMcpToolExposureSurface *> *omitToolsFrom = @[exposureSurface];
    NSArray<NSString *> *enabledTools = @[@"read", @"search"];
    NSArray<NSString *> *disabledTools = @[@"write"];
    NSArray<NSString *> *scopes = @[@"files.read", @"files.write"];
    NSDictionary<NSString *, CodexAgentAgentMcpToolConfiguration *> *tools = @{
        @"write": toolConfiguration,
    };
    CodexAgentAgentMcpServerConfiguration *configuration =
        [[CodexAgentAgentMcpServerConfiguration alloc]
            initWithName:@"compiler-mcp"
            transport:http
            authentication:authentication
            environmentId:@"local"
            isEnabled:NO
            isRequired:YES
            supportsParallelToolCalls:YES
            omitToolsFrom:omitToolsFrom
            startupTimeoutSeconds:startupTimeout
            toolTimeoutSeconds:toolTimeout
            defaultToolApproval:approval
            enabledTools:enabledTools
            disabledTools:disabledTools
            scopes:scopes
            oauth:oauth
            oauthResource:@"https://mcp.example.com/resource"
            tools:tools];
    NSString *name = configuration.name;
    id<CodexAgentAgentMcpTransport> transport = configuration.transport;
    CodexAgentAgentMcpAuthentication *returnedAuthentication = configuration.authentication;
    NSString *environmentId = configuration.environmentId;
    BOOL isEnabled = configuration.isEnabled;
    BOOL isRequired = configuration.isRequired;
    BOOL supportsParallelToolCalls = configuration.supportsParallelToolCalls;
    NSArray<CodexAgentAgentMcpToolExposureSurface *> *returnedOmitToolsFrom =
        configuration.omitToolsFrom;
    CodexAgentDouble *returnedStartupTimeout = configuration.startupTimeoutSeconds;
    CodexAgentDouble *returnedToolTimeout = configuration.toolTimeoutSeconds;
    CodexAgentAgentMcpToolApproval *returnedApproval = configuration.defaultToolApproval;
    NSArray<NSString *> *returnedEnabledTools = configuration.enabledTools;
    NSArray<NSString *> *returnedDisabledTools = configuration.disabledTools;
    NSArray<NSString *> *returnedScopes = configuration.scopes;
    CodexAgentAgentMcpOauthConfiguration *returnedOauth = configuration.oauth;
    NSString *oauthResource = configuration.oauthResource;
    NSDictionary<NSString *, CodexAgentAgentMcpToolConfiguration *> *returnedTools = configuration.tools;

    NSDictionary<NSString *, id<CodexAgentAgentFormValue>> *content = @{@"field": formValue};
    CodexAgentAgentElicitationResponse *response = [[CodexAgentAgentElicitationResponse alloc]
        initWithAction:elicitationAction
        content:content];
    CodexAgentAgentElicitationAction *returnedAction = response.action;
    NSDictionary<NSString *, id<CodexAgentAgentFormValue>> *returnedContent = response.content;

    return [httpUrl isEqualToString:@"https://mcp.example.com"] &&
        [bearerTokenEnvironmentVariable isEqualToString:@"MCP_TOKEN"] &&
        [returnedHeaders isEqualToDictionary:headers] &&
        [returnedEnvironmentHeaders isEqualToDictionary:environmentHeaders] &&
        [headersHelper isEqualToString:@"mcp-headers"] &&
        [command isEqualToString:@"node"] && [returnedArguments isEqualToArray:arguments] &&
        [workingDirectory isEqualToString:@"/workspace"] &&
        [returnedEnvironment isEqualToDictionary:environment] &&
        [returnedForwarded isEqualToArray:forwarded] &&
        [name isEqualToString:@"compiler-mcp"] && transport == http &&
        returnedAuthentication == authentication && [environmentId isEqualToString:@"local"] &&
        !isEnabled && isRequired && supportsParallelToolCalls &&
        [returnedOmitToolsFrom isEqualToArray:omitToolsFrom] &&
        returnedStartupTimeout == startupTimeout && returnedToolTimeout == toolTimeout &&
        returnedApproval == approval && [returnedEnabledTools isEqualToArray:enabledTools] &&
        [returnedDisabledTools isEqualToArray:disabledTools] &&
        [returnedScopes isEqualToArray:scopes] && returnedOauth == oauth &&
        [oauthResource isEqualToString:@"https://mcp.example.com/resource"] &&
        [returnedTools isEqualToDictionary:tools] && returnedAction == elicitationAction &&
        [returnedContent isEqualToDictionary:content];
}

static BOOL consumeD079ConversationValues(
    CodexAgentAgentConversationSummary *summary,
    CodexAgentAgentInvocationPlugin *pluginInvocation,
    CodexAgentAgentInvocationSkill *skillInvocation
) {
    CodexAgentAgentCapability *webSearch = [CodexAgentAgentCapability webSearch];
    NSSet<CodexAgentAgentCapability *> *capabilities = [NSSet setWithObject:webSearch];
    NSArray<id<CodexAgentAgentInvocation>> *invocations = @[pluginInvocation, skillInvocation];
    CodexAgentInt *exitCode = [CodexAgentInt numberWithInt:7];
    CodexAgentAgentMessage *message = [[CodexAgentAgentMessage alloc]
        initWithId:@"compiler-message"
        clientMessageId:@"compiler-client-message"
        role:[CodexAgentAgentMessageRole assistant]
        text:@"Compiler message"
        collaborationMode:[CodexAgentAgentCollaborationMode plan]
        reasoning:@"Compiler reasoning"
        plan:@"Compiler plan"
        shellCommand:@"echo compiler"
        exitCode:exitCode
        capabilities:capabilities
        invocations:invocations];
    NSSet<CodexAgentAgentCapability *> *returnedMessageCapabilities = message.capabilities;
    NSString *returnedClientMessageId = message.clientMessageId;
    CodexAgentAgentCollaborationMode *returnedMessageCollaboration = message.collaborationMode;
    CodexAgentInt *returnedExitCode = message.exitCode;
    NSString *returnedMessageId = message.id;
    NSArray<id<CodexAgentAgentInvocation>> *returnedMessageInvocations = message.invocations;
    NSString *returnedPlan = message.plan;
    NSString *returnedReasoning = message.reasoning;
    CodexAgentAgentMessageRole *returnedRole = message.role;
    NSString *returnedShellCommand = message.shellCommand;
    NSString *returnedText = message.text;

    CodexAgentAgentTurnRequest *request = [[CodexAgentAgentTurnRequest alloc]
        initWithPrompt:@"Compiler prompt"
        clientMessageId:@"compiler-request"
        model:@"compiler-model"
        effort:@"high"
        serviceTier:@"fast"
        approvalPreset:[CodexAgentAgentApprovalPreset strict]
        capabilities:capabilities
        invocations:invocations
        collaborationMode:[CodexAgentAgentCollaborationMode plan]];
    CodexAgentAgentApprovalPreset *returnedApprovalPreset = request.approvalPreset;
    NSSet<CodexAgentAgentCapability *> *returnedRequestCapabilities = request.capabilities;
    NSString *returnedRequestClientMessageId = request.clientMessageId;
    CodexAgentAgentCollaborationMode *returnedRequestCollaboration = request.collaborationMode;
    NSString *returnedEffort = request.effort;
    NSArray<id<CodexAgentAgentInvocation>> *returnedRequestInvocations = request.invocations;
    NSString *returnedModel = request.model;
    NSString *returnedPrompt = request.prompt;
    NSString *returnedServiceTier = request.serviceTier;

    NSArray<CodexAgentAgentMessage *> *messages = @[message];
    CodexAgentAgentConversation *conversation = [[CodexAgentAgentConversation alloc]
        initWithSummary:summary
        messages:messages];
    NSArray<CodexAgentAgentMessage *> *returnedMessages = conversation.messages;
    CodexAgentAgentConversationSummary *returnedSummary = conversation.summary;

    return [returnedMessageCapabilities isEqualToSet:capabilities] &&
        [returnedClientMessageId isEqualToString:@"compiler-client-message"] &&
        returnedMessageCollaboration == [CodexAgentAgentCollaborationMode plan] &&
        returnedExitCode == exitCode && [returnedMessageId isEqualToString:@"compiler-message"] &&
        [returnedMessageInvocations isEqualToArray:invocations] &&
        [returnedPlan isEqualToString:@"Compiler plan"] &&
        [returnedReasoning isEqualToString:@"Compiler reasoning"] &&
        returnedRole == [CodexAgentAgentMessageRole assistant] &&
        [returnedShellCommand isEqualToString:@"echo compiler"] &&
        [returnedText isEqualToString:@"Compiler message"] &&
        returnedApprovalPreset == [CodexAgentAgentApprovalPreset strict] &&
        [returnedRequestCapabilities isEqualToSet:capabilities] &&
        [returnedRequestClientMessageId isEqualToString:@"compiler-request"] &&
        returnedRequestCollaboration == [CodexAgentAgentCollaborationMode plan] &&
        [returnedEffort isEqualToString:@"high"] &&
        [returnedRequestInvocations isEqualToArray:invocations] &&
        [returnedModel isEqualToString:@"compiler-model"] &&
        [returnedPrompt isEqualToString:@"Compiler prompt"] &&
        [returnedServiceTier isEqualToString:@"fast"] &&
        [returnedMessages isEqualToArray:messages] && returnedSummary == summary;
}

static BOOL consumeD080StateValues(
    CodexAgentAgentAuthenticationStatus *authenticationStatusInput,
    CodexAgentAgentConversationStatus *conversationStatusInput,
    CodexAgentAgentIntegrationAuthorizationStatus *integrationStatusInput,
    CodexAgentCodexAuthorizationUrl *pendingSignInUrl,
    CodexAgentCodexAuthorizationUrl *deviceVerificationUrl,
    CodexAgentCodexFailure *failure,
    CodexAgentConversationId *conversationId,
    CodexAgentAgentConversation *conversation,
    CodexAgentAgentTurnProgress *turnProgress,
    CodexAgentAgentIntegrationConnector *integration,
    CodexAgentAgentPendingApproval *approval,
    CodexAgentAgentPendingElicitation *elicitation
) {
    CodexAgentAgentAuthenticationState *authentication =
        [[CodexAgentAgentAuthenticationState alloc]
            initWithStatus:authenticationStatusInput
            pendingSignInUrl:pendingSignInUrl
            deviceVerificationUrl:deviceVerificationUrl
            deviceUserCode:@"compiler-code"
            failure:failure];
    NSString *deviceUserCode = authentication.deviceUserCode;
    CodexAgentCodexAuthorizationUrl *returnedDeviceVerificationUrl =
        authentication.deviceVerificationUrl;
    CodexAgentCodexFailure *authenticationFailure = authentication.failure;
    CodexAgentCodexAuthorizationUrl *returnedPendingSignInUrl = authentication.pendingSignInUrl;
    CodexAgentAgentAuthenticationStatus *authenticationStatus = authentication.status;

    CodexAgentAgentConversationState *conversationState =
        [[CodexAgentAgentConversationState alloc]
            initWithStatus:conversationStatusInput
            conversationId:conversationId
            conversation:conversation
            turnProgress:turnProgress
            model:@"compiler-model"
            effort:@"high"
            serviceTier:@"fast"
            failure:failure];
    BOOL canCancelTurn = conversationState.canCancelTurn;
    BOOL canReload = conversationState.canReload;
    BOOL canStartTurn = conversationState.canStartTurn;
    CodexAgentAgentConversation *returnedConversation = conversationState.conversation;
    CodexAgentConversationId *returnedConversationId = conversationState.conversationId;
    NSString *effort = conversationState.effort;
    CodexAgentCodexFailure *conversationFailure = conversationState.failure;
    NSString *model = conversationState.model;
    NSString *serviceTier = conversationState.serviceTier;
    CodexAgentAgentConversationStatus *conversationStatus = conversationState.status;
    CodexAgentAgentTurnProgress *returnedTurnProgress = conversationState.turnProgress;

    CodexAgentAgentIntegrationAuthorizationState *integrationState =
        [[CodexAgentAgentIntegrationAuthorizationState alloc]
            initWithStatus:integrationStatusInput
            target:integration
            failure:failure];
    CodexAgentCodexFailure *integrationFailure = integrationState.failure;
    CodexAgentAgentIntegrationAuthorizationStatus *integrationStatus = integrationState.status;
    id<CodexAgentAgentIntegration> returnedTarget = integrationState.target;

    NSArray<id<CodexAgentAgentPendingInteraction>> *pending = @[approval, elicitation];
    NSSet<NSString *> *resolvingRequestIds = [NSSet setWithObject:@"approval"];
    CodexAgentAgentInteractionState *interactionState = [[CodexAgentAgentInteractionState alloc]
        initWithPending:pending
        resolvingRequestIds:resolvingRequestIds
        failure:failure];
    CodexAgentCodexFailure *interactionFailure = interactionState.failure;
    NSArray<id<CodexAgentAgentPendingInteraction>> *returnedPending = interactionState.pending;
    NSSet<NSString *> *returnedResolvingRequestIds = interactionState.resolvingRequestIds;
    NSArray<id<CodexAgentAgentPendingInteraction>> *conversationPending =
        [interactionState pendingForConversationId:conversationId];
    BOOL isResolving = [interactionState isResolvingInteraction:approval];

    return [deviceUserCode isEqualToString:@"compiler-code"] &&
        returnedDeviceVerificationUrl == deviceVerificationUrl &&
        authenticationFailure == failure && returnedPendingSignInUrl == pendingSignInUrl &&
        authenticationStatus == authenticationStatusInput &&
        !canCancelTurn && canReload && canStartTurn && returnedConversation == conversation &&
        returnedConversationId == conversationId && [effort isEqualToString:@"high"] &&
        conversationFailure == failure && [model isEqualToString:@"compiler-model"] &&
        [serviceTier isEqualToString:@"fast"] &&
        conversationStatus == conversationStatusInput &&
        returnedTurnProgress == turnProgress && integrationFailure == failure &&
        integrationStatus == integrationStatusInput &&
        returnedTarget == integration && interactionFailure == failure &&
        [returnedPending isEqualToArray:pending] &&
        [returnedResolvingRequestIds isEqualToSet:resolvingRequestIds] &&
        conversationPending.count == pending.count && isResolving;
}

static BOOL consumeD081SingletonObjects(void) {
    CodexAgentAgentHookHandlerAgent *agentHandler =
        [CodexAgentAgentHookHandlerAgent shared];
    CodexAgentAgentHookHandlerPrompt *promptHandler =
        [CodexAgentAgentHookHandlerPrompt shared];
    CodexAgentCodexAuthenticationMethodChatGptBrowser *browserAuthentication =
        [CodexAgentCodexAuthenticationMethodChatGptBrowser shared];
    CodexAgentCodexAuthenticationMethodChatGptDeviceCode *deviceCodeAuthentication =
        [CodexAgentCodexAuthenticationMethodChatGptDeviceCode shared];
    CodexAgentCodexHostStateClosed *closed = [CodexAgentCodexHostStateClosed shared];
    CodexAgentCodexHostStateNew *newState = [CodexAgentCodexHostStateNew shared];
    CodexAgentCodexHostStateRestoring *restoring = [CodexAgentCodexHostStateRestoring shared];

    return agentHandler != nil && promptHandler != nil && browserAuthentication != nil &&
        deviceCodeAuthentication != nil && closed != nil && newState != nil && restoring != nil;
}

static BOOL consumeD082ElicitationHelpers(
    CodexAgentAgentElicitation *elicitation,
    CodexAgentAgentFormField *field,
    id<CodexAgentAgentFormValue> value,
    NSDictionary<NSString *, id<CodexAgentAgentFormValue>> *content,
    CodexAgentAgentElicitationResponse *response,
    CodexAgentAgentElicitationResponseCompanion *companion
) {
    CodexAgentAgentElicitationResponse *accepted = [elicitation acceptContent:content];
    BOOL accepts = [elicitation acceptsResponse:response];
    NSDictionary<NSString *, id<CodexAgentAgentFormValue>> *initialValues =
        [elicitation initialValues];
    CodexAgentAgentElicitationValidation *validation = [elicitation validateContent:content];
    BOOL fieldAccepts = [field acceptsValue:value];
    CodexAgentAgentElicitationResponse *cancelled = [companion cancel];
    CodexAgentAgentElicitationResponse *declined = [companion decline];
    return accepted != nil && initialValues != nil && validation != nil &&
        cancelled != nil && declined != nil && (accepts || !accepts) &&
        (fieldAccepts || !fieldAccepts);
}

static BOOL consumeD083ProtocolOwnerProperties(
    id<CodexAgentAgentIntegration> integration,
    id<CodexAgentAgentInvocation> invocation,
    id<CodexAgentAgentPendingInteraction> interaction
) {
    NSString *integrationDisplayName = integration.displayName;
    NSString *integrationId = integration.id;
    NSString *invocationKey = invocation.key;
    NSString *invocationName = invocation.name;
    CodexAgentConversationId *conversationId = interaction.conversationId;
    NSString *requestId = interaction.requestId;
    return integrationDisplayName.length > 0 && integrationId.length > 0 &&
        invocationKey.length > 0 && invocationName.length > 0 &&
        conversationId != nil && requestId.length > 0;
}

static BOOL consumeD084HostGateway(
    id<CodexAgentCodexPlatform> platform,
    CodexAgentCodexClientInfo *clientInfo,
    id<CodexAgentCodexWorkspaceSelection> selection,
    CodexAgentCodexWorkspace *workspace,
    CodexAgentCodexFailure *failure,
    CodexAgentCodexAgent *agent,
    CodexAgentCodexWorkspaceResolutionSelectionRequired *requirement
) {
    CodexAgentCodexHost *host = [[CodexAgentCodexHost alloc]
        initWithPlatform:platform
              clientInfo:clientInfo];
    id<CodexAgentKotlinx_coroutines_coreStateFlow> lifecycleState = host.lifecycleState;
    [host startWithCompletionHandler:^(NSError *error) {
        (void)error;
    }];
    [host selectWorkspaceSelection:selection completionHandler:^(NSError *error) {
        (void)error;
    }];
    [host closeWithCompletionHandler:^(NSError *error) {
        (void)error;
    }];

    CodexAgentCodexHostStateFailed *failed = [[CodexAgentCodexHostStateFailed alloc]
        initWithWorkspace:workspace
                 failure:failure];
    CodexAgentCodexFailure *returnedFailure = failed.failure;
    CodexAgentCodexWorkspace *failedWorkspace = failed.workspace;
    CodexAgentCodexHostStatePreparing *preparing = [[CodexAgentCodexHostStatePreparing alloc]
        initWithWorkspace:workspace];
    CodexAgentCodexWorkspace *preparingWorkspace = preparing.workspace;
    CodexAgentCodexHostStateReady *ready = [[CodexAgentCodexHostStateReady alloc]
        initWithAgent:agent];
    CodexAgentCodexAgent *returnedAgent = ready.agent;
    CodexAgentCodexHostStateWorkspaceRequired *workspaceRequired =
        [[CodexAgentCodexHostStateWorkspaceRequired alloc] initWithRequirement:requirement];
    CodexAgentCodexWorkspaceResolutionSelectionRequired *returnedRequirement =
        workspaceRequired.requirement;

    return lifecycleState != nil && returnedFailure == failure &&
        failedWorkspace == workspace && preparingWorkspace == workspace &&
        returnedAgent == agent && returnedRequirement == requirement;
}

static BOOL consumeD085AgentControllers(CodexAgentCodexAgent *agent) {
    CodexAgentCodexAuthentication *authentication = agent.authentication;
    CodexAgentCodexConnectors *connectors = agent.connectors;
    CodexAgentCodexConversations *conversations = agent.conversations;
    CodexAgentCodexHooks *hooks = agent.hooks;
    CodexAgentCodexIntegrationAuthorization *integrationAuthorization =
        agent.integrationAuthorization;
    CodexAgentCodexInteractions *interactions = agent.interactions;
    CodexAgentCodexMcpServers *mcpServers = agent.mcpServers;
    CodexAgentCodexModels *models = agent.models;
    CodexAgentCodexPlugins *plugins = agent.plugins;
    CodexAgentCodexSkills *skills = agent.skills;
    CodexAgentCodexWorkspace *workspace = agent.workspace;
    BOOL connectorsAvailable = connectors.isAvailable;
    BOOL hooksAvailable = hooks.isAvailable;
    BOOL mcpServersAvailable = mcpServers.isAvailable;
    BOOL pluginsAvailable = plugins.isAvailable;
    BOOL skillsAvailable = skills.isAvailable;
    return authentication != nil && connectors != nil && conversations != nil && hooks != nil &&
        integrationAuthorization != nil && interactions != nil && mcpServers != nil && models != nil &&
        plugins != nil && skills != nil && workspace != nil &&
        (connectorsAvailable || !connectorsAvailable) && (hooksAvailable || !hooksAvailable) &&
        (mcpServersAvailable || !mcpServersAvailable) && (pluginsAvailable || !pluginsAvailable) &&
        (skillsAvailable || !skillsAvailable);
}

static BOOL consumeD086ControllerFunctions(
    CodexAgentCodexAgent *agent,
    CodexAgentAgentHook *hook,
    CodexAgentAgentMcpServerConfiguration *mcpConfiguration,
    CodexAgentAgentMcpServer *mcpServer,
    CodexAgentAgentModel *model,
    CodexAgentAgentPluginReference *plugin,
    CodexAgentAgentSkill *skill
) {
    [agent.connectors listForceReload:NO
                   completionHandler:^(NSArray<CodexAgentAgentConnector *> *connectors,
                                       NSError *error) {
        (void)connectors;
        (void)error;
    }];

    [agent.hooks installDirectory:@"/compiler/hook"
                            scope:[CodexAgentAgentInstallationScope workspace]
                completionHandler:^(CodexAgentAgentHook *installedHook, NSError *error) {
        (void)installedHook;
        (void)error;
    }];
    [agent.hooks listWithCompletionHandler:^(CodexAgentAgentHookCatalog *catalog, NSError *error) {
        (void)catalog;
        (void)error;
    }];
    [agent.hooks trustHook:hook completionHandler:^(NSError *error) {
        (void)error;
    }];
    [agent.hooks uninstallHook:hook completionHandler:^(NSError *error) {
        (void)error;
    }];

    [agent.mcpServers addConfiguration:mcpConfiguration
                     completionHandler:^(CodexAgentAgentMcpServer *server, NSError *error) {
        (void)server;
        (void)error;
    }];
    [agent.mcpServers listWithCompletionHandler:^(NSArray<CodexAgentAgentMcpServer *> *servers,
                                                  NSError *error) {
        (void)servers;
        (void)error;
    }];
    [agent.mcpServers removeServer:mcpServer completionHandler:^(NSError *error) {
        (void)error;
    }];

    [agent.models listWithCompletionHandler:^(NSArray<CodexAgentAgentModel *> *models,
                                               NSError *error) {
        (void)models;
        (void)error;
    }];
    [agent.models resolveEffortModel:model
                          resolution:[CodexAgentAgentResolution default_]
                   completionHandler:^(NSString *effort, NSError *error) {
        (void)effort;
        (void)error;
    }];
    [agent.models resolveServiceTierModel:model
                               resolution:[CodexAgentAgentResolution first]
                        completionHandler:^(CodexAgentAgentServiceTier *tier, NSError *error) {
        (void)tier;
        (void)error;
    }];
    [agent.models resolveResolution:[CodexAgentAgentResolution first]
                  completionHandler:^(CodexAgentAgentModel *resolvedModel, NSError *error) {
        (void)resolvedModel;
        (void)error;
    }];

    [agent.plugins installPlugin:plugin
               completionHandler:^(CodexAgentAgentPluginInstallResult *result, NSError *error) {
        (void)result;
        (void)error;
    }];
    [agent.plugins listForceReload:NO
                completionHandler:^(CodexAgentAgentPluginCatalog *catalog, NSError *error) {
        (void)catalog;
        (void)error;
    }];
    [agent.plugins readPlugin:plugin
            completionHandler:^(CodexAgentAgentPluginDetail *detail, NSError *error) {
        (void)detail;
        (void)error;
    }];
    [agent.plugins uninstallPlugin:plugin completionHandler:^(NSError *error) {
        (void)error;
    }];

    [agent.skills installDirectory:@"/compiler/skill"
                             scope:[CodexAgentAgentInstallationScope user]
                 completionHandler:^(CodexAgentAgentSkill *installedSkill, NSError *error) {
        (void)installedSkill;
        (void)error;
    }];
    [agent.skills listForceReload:YES
               completionHandler:^(CodexAgentAgentSkillCatalog *catalog, NSError *error) {
        (void)catalog;
        (void)error;
    }];
    [agent.skills readPath:@"/compiler/skill/SKILL.md"
                    offset:0
         completionHandler:^(CodexAgentAgentSkillChunk *chunk, NSError *error) {
        (void)chunk;
        (void)error;
    }];
    [agent.skills uninstallSkill:skill completionHandler:^(NSError *error) {
        (void)error;
    }];
    return YES;
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

static BOOL consumeD074OrdinaryValues(
    CodexAgentConversationId *conversationId,
    CodexAgentAgentFormOption *formOption,
    id<CodexAgentAgentFormValue> defaultValue,
    CodexAgentAgentFormFieldType *formFieldType,
    CodexAgentAgentFormStringFormat *formStringFormat,
    CodexAgentDouble *minimum,
    CodexAgentDouble *maximum,
    CodexAgentLong *minimumLength,
    CodexAgentLong *maximumLength,
    CodexAgentLong *minimumSelections,
    CodexAgentLong *maximumSelections,
    CodexAgentAgentHookRunStatus *hookRunStatus,
    CodexAgentAgentHookTrustStatus *hookTrustStatus,
    CodexAgentAgentResourceOrigin *resourceOrigin,
    CodexAgentAgentConnector *connector,
    CodexAgentAgentPlanProgress *planProgress,
    CodexAgentInt *shellExitCode,
    CodexAgentAgentWorkActivity *workActivity
) {
    CodexAgentAgentFormField *field = [[CodexAgentAgentFormField alloc]
        initWithName:@"field"
        title:@"Field"
        description:@"Field description"
        isRequired:YES
        type:formFieldType
        options:@[formOption]
        defaultValue:defaultValue
        minimum:minimum
        maximum:maximum
        format:formStringFormat
        minimumLength:minimumLength
        maximumLength:maximumLength
        minimumSelections:minimumSelections
        maximumSelections:maximumSelections
        allowsOther:YES
        isSecret:YES];
    CodexAgentAgentElicitation *elicitation = [[CodexAgentAgentElicitation alloc]
        initWithRequestId:@"request"
        serverName:@"server"
        conversationId:conversationId
        message:@"Provide input"
        form:@[field]
        url:@"https://example.com/input"];
    CodexAgentAgentHookHandlerCommand *commandHandler =
        [[CodexAgentAgentHookHandlerCommand alloc] initWithCommand:@"echo ready" isAsync:YES];
    id<CodexAgentAgentHookHandler> handler = commandHandler;
    CodexAgentAgentHookHandlerMcpTool *mcpHandler =
        [[CodexAgentAgentHookHandlerMcpTool alloc] initWithServer:@"server" tool:@"review"];
    CodexAgentAgentHook *hook = [[CodexAgentAgentHook alloc]
        initWithKey:@"hook"
        currentHash:@"hash"
        isEnabled:YES
        eventName:@"afterTurn"
        handler:handler
        isManaged:NO
        source:@"PROJECT"
        sourcePath:@"/hooks.json"
        timeoutSeconds:30
        trustStatus:hookTrustStatus
        matcher:@"*.kt"
        pluginId:@"plugin"
        statusMessage:@"Ready"
        origin:resourceOrigin
        canUninstall:YES];
    CodexAgentAgentHookActivity *activity = [[CodexAgentAgentHookActivity alloc]
        initWithId:@"activity"
        eventName:@"afterTurn"
        handlerType:@"command"
        status:hookRunStatus
        statusMessage:@"Complete"
        details:@[@"first", @"second"]];
    CodexAgentAgentHookCatalog *catalog = [[CodexAgentAgentHookCatalog alloc]
        initWithHooks:@[hook]
        warnings:@[@"warning"]
        errors:@[@"error"]];
    CodexAgentAgentIntegrationConnector *integration =
        [[CodexAgentAgentIntegrationConnector alloc] initWithConnector:connector];
    CodexAgentAgentInvocationPlugin *pluginInvocation =
        [[CodexAgentAgentInvocationPlugin alloc] initWithName:@"plugin" uri:@"plugin://plugin@marketplace"];
    CodexAgentAgentInvocationSkill *skillInvocation =
        [[CodexAgentAgentInvocationSkill alloc] initWithName:@"skill" path:@"/skills/review/SKILL.md"];
    CodexAgentAgentTurnProgress *progress = [[CodexAgentAgentTurnProgress alloc]
        initWithText:@"text"
        commentary:@"commentary"
        reasoning:@"reasoning"
        plan:@"plan"
        planProgress:planProgress
        shellOutput:@"output"
        shellExitCode:shellExitCode
        workActivity:workActivity
        hookActivities:@[activity]
        isTruncated:YES];
    CodexAgentCodexAuthenticationMethodApiKey *apiKey =
        [[CodexAgentCodexAuthenticationMethodApiKey alloc] initWithValue:@"sk-compiler"];

    return [elicitation.requestId isEqualToString:@"request"] &&
        [elicitation.serverName isEqualToString:@"server"] &&
        elicitation.conversationId == conversationId &&
        [elicitation.message isEqualToString:@"Provide input"] &&
        [elicitation.form isEqualToArray:@[field]] &&
        [elicitation.url isEqualToString:@"https://example.com/input"] &&
        [field.name isEqualToString:@"field"] &&
        [field.title isEqualToString:@"Field"] &&
        [field.description_ isEqualToString:@"Field description"] &&
        field.isRequired && field.type == formFieldType &&
        [field.options isEqualToArray:@[formOption]] && field.defaultValue == defaultValue &&
        field.minimum == minimum && field.maximum == maximum && field.format == formStringFormat &&
        field.minimumLength == minimumLength && field.maximumLength == maximumLength &&
        field.minimumSelections == minimumSelections && field.maximumSelections == maximumSelections &&
        field.allowsOther && field.isSecret &&
        [hook.key isEqualToString:@"hook"] && [hook.currentHash isEqualToString:@"hash"] &&
        hook.isEnabled && [hook.eventName isEqualToString:@"afterTurn"] && hook.handler == commandHandler &&
        !hook.isManaged && [hook.source isEqualToString:@"PROJECT"] &&
        [hook.sourcePath isEqualToString:@"/hooks.json"] && hook.timeoutSeconds == 30 &&
        hook.trustStatus == hookTrustStatus && [hook.matcher isEqualToString:@"*.kt"] &&
        [hook.pluginId isEqualToString:@"plugin"] && [hook.statusMessage isEqualToString:@"Ready"] &&
        hook.origin == resourceOrigin && hook.canUninstall && hook.canTrust &&
        [activity.id isEqualToString:@"activity"] && [activity.eventName isEqualToString:@"afterTurn"] &&
        [activity.handlerType isEqualToString:@"command"] && activity.status == hookRunStatus &&
        [activity.statusMessage isEqualToString:@"Complete"] &&
        [activity.details isEqualToArray:@[@"first", @"second"]] &&
        [catalog.hooks isEqualToArray:@[hook]] && [catalog.warnings isEqualToArray:@[@"warning"]] &&
        [catalog.errors isEqualToArray:@[@"error"]] &&
        [commandHandler.command isEqualToString:@"echo ready"] && commandHandler.isAsync &&
        [mcpHandler.server isEqualToString:@"server"] && [mcpHandler.tool isEqualToString:@"review"] &&
        integration.connector == connector && [integration.id isEqualToString:@"connector-id"] &&
        [integration.displayName isEqualToString:@"Connector"] &&
        [pluginInvocation.name isEqualToString:@"plugin"] &&
        [pluginInvocation.uri isEqualToString:@"plugin://plugin@marketplace"] &&
        [pluginInvocation.key isEqualToString:@"plugin:plugin://plugin@marketplace"] &&
        [skillInvocation.name isEqualToString:@"skill"] &&
        [skillInvocation.path isEqualToString:@"/skills/review/SKILL.md"] &&
        [skillInvocation.key isEqualToString:@"skill:/skills/review/SKILL.md"] &&
        [progress.text isEqualToString:@"text"] && [progress.commentary isEqualToString:@"commentary"] &&
        [progress.reasoning isEqualToString:@"reasoning"] && [progress.plan isEqualToString:@"plan"] &&
        progress.planProgress == planProgress && [progress.shellOutput isEqualToString:@"output"] &&
        progress.shellExitCode == shellExitCode && progress.workActivity == workActivity &&
        [progress.hookActivities isEqualToArray:@[activity]] && progress.isTruncated &&
        [apiKey.value isEqualToString:@"sk-compiler"];
}

static BOOL consumeD075PendingValues(
    CodexAgentConversationId *conversationId,
    CodexAgentAgentElicitation *elicitation
) {
    CodexAgentAgentPendingApproval *approval = [[CodexAgentAgentPendingApproval alloc]
        initWithRequestId:@"approval"
        conversationId:conversationId
        title:@"Approve"
        details:@"Details"];
    CodexAgentAgentPendingElicitation *pendingElicitation =
        [[CodexAgentAgentPendingElicitation alloc] initWithElicitation:elicitation];

    return [approval.requestId isEqualToString:@"approval"] &&
        approval.conversationId == conversationId &&
        [approval.title isEqualToString:@"Approve"] &&
        [approval.details isEqualToString:@"Details"] &&
        pendingElicitation.elicitation == elicitation &&
        [pendingElicitation.requestId isEqualToString:@"request"] &&
        pendingElicitation.conversationId == conversationId;
}
