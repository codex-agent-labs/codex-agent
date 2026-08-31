import {
  AgentConnector,
  AgentConnectorIntegration,
  AgentConversation,
  AgentConversationSummary,
  AgentElicitation,
  AgentElicitationResponse,
  AgentElicitationValidation,
  AgentElicitationValidationIssue,
  AgentFormBooleanValue,
  AgentFormField,
  AgentFormNumberValue,
  AgentFormOption,
  AgentFormTextListValue,
  AgentFormTextValue,
  AgentHookActivity,
  AgentHook,
  AgentHookCatalog,
  AgentMcpEnvironmentVariable,
  AgentMcpHttpTransport,
  AgentMcpOauthConfiguration,
  AgentMcpServer,
  AgentMcpServerIntegration,
  AgentMcpServerConfiguration,
  AgentMcpStdioTransport,
  AgentMcpToolConfiguration,
  AgentModel,
  AgentInteractionState,
  AgentPlanProgress,
  AgentPlanStep,
  AgentPluginCatalog,
  AgentPluginDetail,
  AgentPluginInstallResult,
  AgentPluginInvocation,
  AgentPluginReference,
  AgentPluginSkill,
  AgentPluginSummary,
  AgentPendingApproval,
  AgentPendingElicitation,
  AgentServiceTier,
  AgentSkill,
  AgentSkillCatalog,
  AgentSkillChunk,
  AgentSkillInvocation,
  CodexAgent,
  CodexAuthentication,
  CodexAuthenticationState,
  CodexAuthorizationUrl,
  CodexConversation,
  CodexConversationState,
  CodexError,
  CodexFailure,
  CodexHost,
  CodexHostState,
  CodexIntegrationAuthorization,
  CodexInteractions,
  CodexHooks,
  CodexModels,
  CodexMcpServers,
  CodexPlugins,
  AgentIntegrationAuthorizationState,
  CodexObservation,
  CodexSkills,
  agentCapabilityDisplayLabel,
  agentCapabilityIcon,
  agentCapabilityId,
  agentCapabilityPromptLabel,
  agentSkillScopeDisplayName,
  codexApprovalPresetDisplayName,
  createCodexHost,
} from "@codex-agent-labs/codex-agent";
import type {
  AgentApprovalDecision,
  AgentCapability,
  AgentCatalogFreshness,
  AgentCollaborationMode,
  AgentElicitationAction,
  AgentElicitationValidationReason,
  AgentFormFieldType,
  AgentFormStringFormat,
  AgentFormValue,
  AgentHookRunStatus,
  AgentHookHandler,
  AgentHookTrustStatus,
  AgentInstallationScope,
  AgentIntegrationAuthorizationStatus,
  AgentIntegration,
  AgentInvocation,
  AgentMcpAuthStatus,
  AgentMcpAuthentication,
  AgentMcpEnvironmentSource,
  AgentMcpToolApproval,
  AgentMcpToolExposureSurface,
  AgentMcpTransport,
  AgentPendingInteraction,
  AgentPlanStepStatus,
  AgentPluginAuthPolicy,
  AgentPluginInstallPolicy,
  AgentResolution,
  AgentResourceOrigin,
  AgentSkillScope,
  AgentTurnRequest,
  CodexApprovalPreset,
  CodexAuthenticationMethod,
  CodexAuthenticationStatus,
  CodexAuthorizationPurpose,
  CodexConnectors,
  CodexConversationStatus,
  CodexHostStatus,
  CodexMessageRole,
  CodexWorkActivity,
  CodexWorkspaceSelectionReason,
} from "@codex-agent-labs/codex-agent";

const host: CodexHost = createCodexHost("/bundle", "/data", "typescript", "TypeScript", "test");
const state: CodexHostState = host.state;
const hostStatus: CodexHostStatus = state.status;
const hostWorkspace: typeof state.workspace = state.workspace;
const hostAgent: typeof state.agent = state.agent;
const hostSelectionReason: typeof state.selectionReason = state.selectionReason;
const hostSelectionMessage: typeof state.selectionMessage = state.selectionMessage;
const hostFailure: typeof state.failure = state.failure;
const approvalPreset: CodexApprovalPreset = "auto_review";
const approvalPresetDisplayName: string = codexApprovalPresetDisplayName(approvalPreset);
const skillScope: AgentSkillScope = "system";
const skillScopeDisplayName: string = agentSkillScopeDisplayName(skillScope);
const capability: AgentCapability = "web_search";
const capabilityId: string = agentCapabilityId(capability);
const capabilityDisplayLabel: string = agentCapabilityDisplayLabel(capability);
const capabilityIcon: string | null | undefined = agentCapabilityIcon(capability);
const capabilityPromptLabel: string = agentCapabilityPromptLabel(capability);
const chatGptAuthorizationUrl: CodexAuthorizationUrl =
  CodexAuthorizationUrl.chatGpt("https://auth.openai.com/authorize");
const externalAuthorizationUrl: CodexAuthorizationUrl =
  CodexAuthorizationUrl.external("http://localhost:8787/callback");
const authorizationUrlValue: string = chatGptAuthorizationUrl.value;
const authorizationUrlPurpose: CodexAuthorizationPurpose = externalAuthorizationUrl.purpose;
const formOption = new AgentFormOption("value");
const formOptionValue: string = formOption.value;
const formOptionTitle: string = formOption.title;
const formOptionDescription: string | null | undefined = formOption.description;
const formTextValue = new AgentFormTextValue("text");
const formText: string = formTextValue.value;
const formNumberValue = new AgentFormNumberValue(1.5);
const formNumber: number = formNumberValue.value;
const formBooleanValue = new AgentFormBooleanValue(true);
const formBoolean: boolean = formBooleanValue.value;
const formTextListValue = new AgentFormTextListValue(["first", "second"]);
const formTextList: ReadonlyArray<string> = formTextListValue.value;
const formFieldClass: typeof AgentFormField = AgentFormField;
const formDefaultValue: AgentFormValue = formTextValue;
const formField = new AgentFormField(
  "email",
  "Email",
  "string",
  "Account email",
  true,
  [formOption],
  formDefaultValue,
  null,
  null,
  "email",
  3n,
  80n,
  null,
  null,
  false,
  true,
);
const formFieldName: string = formField.name;
const formFieldTitle: string = formField.title;
const formFieldType: AgentFormFieldType = formField.type;
const formFieldDescription: string | null | undefined = formField.description;
const formFieldRequired: boolean = formField.isRequired;
const formFieldOptions: ReadonlyArray<AgentFormOption> = formField.options;
const formFieldDefaultValue: AgentFormValue | null | undefined = formField.defaultValue;
const formFieldMinimum: number | null | undefined = formField.minimum;
const formFieldMaximum: number | null | undefined = formField.maximum;
const formFieldFormat: AgentFormStringFormat | null | undefined = formField.format;
const formFieldMinimumLength: bigint | null | undefined = formField.minimumLength;
const formFieldMaximumLength: bigint | null | undefined = formField.maximumLength;
const formFieldMinimumSelections: bigint | null | undefined = formField.minimumSelections;
const formFieldMaximumSelections: bigint | null | undefined = formField.maximumSelections;
const formFieldAllowsOther: boolean = formField.allowsOther;
const formFieldSecret: boolean = formField.isSecret;
const formFieldAccepts: boolean = formField.accepts(new AgentFormTextValue("person@example.com"));
const mcpEnvironmentVariables = [
  new AgentMcpEnvironmentVariable("TOKEN"),
  new AgentMcpEnvironmentVariable("OPTIONAL_TOKEN", null),
  new AgentMcpEnvironmentVariable("LOCAL_TOKEN", "local"),
  new AgentMcpEnvironmentVariable("REMOTE_TOKEN", "remote"),
];
const mcpEnvironmentNames: ReadonlyArray<string> = mcpEnvironmentVariables.map((variable) => variable.name);
const mcpEnvironmentSources: ReadonlyArray<AgentMcpEnvironmentSource | null | undefined> =
  mcpEnvironmentVariables.map((variable) => variable.source);
const mcpOauthConfigurations = [
  new AgentMcpOauthConfiguration(),
  new AgentMcpOauthConfiguration(null, null),
  new AgentMcpOauthConfiguration("minimum-port", 1),
  new AgentMcpOauthConfiguration("maximum-port", 65535),
];
const mcpOauthClientIds: ReadonlyArray<string | null | undefined> =
  mcpOauthConfigurations.map((configuration) => configuration.clientId);
const mcpOauthCallbackPorts: ReadonlyArray<number | null | undefined> =
  mcpOauthConfigurations.map((configuration) => configuration.callbackPort);
const mcpToolApprovals: ReadonlyArray<AgentMcpToolApproval | null | undefined> = [
  new AgentMcpToolConfiguration().approval,
  new AgentMcpToolConfiguration(null).approval,
  new AgentMcpToolConfiguration("approve").approval,
  new AgentMcpToolConfiguration("auto").approval,
  new AgentMcpToolConfiguration("prompt").approval,
  new AgentMcpToolConfiguration("writes").approval,
];
const mcpStdioTransportClass: typeof AgentMcpStdioTransport = AgentMcpStdioTransport;
const mcpHttpTransportClass: typeof AgentMcpHttpTransport = AgentMcpHttpTransport;
const mcpServerConfigurationClass: typeof AgentMcpServerConfiguration = AgentMcpServerConfiguration;
const mcpServerClass: typeof AgentMcpServer = AgentMcpServer;
const mcpStdioTransport = new AgentMcpStdioTransport(
  "node",
  ["server.js"],
  "/workspace",
  { STATIC_TOKEN: "value" },
  mcpEnvironmentVariables,
);
const mcpTransport: AgentMcpTransport = mcpStdioTransport;
const mcpStdioCommand: string = mcpStdioTransport.command;
const mcpStdioArguments: ReadonlyArray<string> = mcpStdioTransport.arguments;
const mcpStdioWorkingDirectory: string | null | undefined = mcpStdioTransport.workingDirectory;
const mcpStdioEnvironment: Readonly<Record<string, string>> | null | undefined =
  mcpStdioTransport.environment;
const mcpStdioForwardedEnvironment: ReadonlyArray<AgentMcpEnvironmentVariable> =
  mcpStdioTransport.forwardedEnvironment;
const mcpHttpTransport = new AgentMcpHttpTransport(
  "https://mcp.example.com",
  "MCP_TOKEN",
  { "X-Static": "value" },
  { Authorization: "MCP_AUTH" },
  "mcp-headers",
);
const mcpHttpUrl: string = mcpHttpTransport.url;
const mcpHttpBearerTokenEnvironmentVariable: string | null | undefined =
  mcpHttpTransport.bearerTokenEnvironmentVariable;
const mcpHttpHeaders: Readonly<Record<string, string>> | null | undefined = mcpHttpTransport.headers;
const mcpHttpEnvironmentHeaders: Readonly<Record<string, string>> | null | undefined =
  mcpHttpTransport.environmentHeaders;
const mcpHttpHeadersHelper: string | null | undefined = mcpHttpTransport.headersHelper;
const mcpServerConfiguration = new AgentMcpServerConfiguration(
  "remote",
  mcpHttpTransport,
  "chat_gpt",
  "local",
  false,
  true,
  true,
  ["code_mode", "deferred"],
  3.5,
  9,
  "writes",
  ["read"],
  [],
  ["files.read"],
  new AgentMcpOauthConfiguration("client", 9876),
  "https://mcp.example.com/resource",
  { write: new AgentMcpToolConfiguration("prompt") },
);
const mcpConfigurationName: string = mcpServerConfiguration.name;
const mcpConfigurationTransport: AgentMcpTransport = mcpServerConfiguration.transport;
const mcpConfigurationAuthentication: AgentMcpAuthentication | null | undefined =
  mcpServerConfiguration.authentication;
const mcpConfigurationEnvironmentId: string = mcpServerConfiguration.environmentId;
const mcpConfigurationIsEnabled: boolean = mcpServerConfiguration.isEnabled;
const mcpConfigurationIsRequired: boolean = mcpServerConfiguration.isRequired;
const mcpConfigurationSupportsParallelToolCalls: boolean =
  mcpServerConfiguration.supportsParallelToolCalls;
const mcpConfigurationOmitToolsFrom: ReadonlyArray<AgentMcpToolExposureSurface> | null | undefined =
  mcpServerConfiguration.omitToolsFrom;
const mcpConfigurationStartupTimeoutSeconds: number | null | undefined =
  mcpServerConfiguration.startupTimeoutSeconds;
const mcpConfigurationToolTimeoutSeconds: number | null | undefined =
  mcpServerConfiguration.toolTimeoutSeconds;
const mcpConfigurationDefaultToolApproval: AgentMcpToolApproval | null | undefined =
  mcpServerConfiguration.defaultToolApproval;
const mcpConfigurationEnabledTools: ReadonlyArray<string> | null | undefined =
  mcpServerConfiguration.enabledTools;
const mcpConfigurationDisabledTools: ReadonlyArray<string> | null | undefined =
  mcpServerConfiguration.disabledTools;
const mcpConfigurationScopes: ReadonlyArray<string> | null | undefined = mcpServerConfiguration.scopes;
const mcpConfigurationOauth: AgentMcpOauthConfiguration | null | undefined = mcpServerConfiguration.oauth;
const mcpConfigurationOauthResource: string | null | undefined = mcpServerConfiguration.oauthResource;
const mcpConfigurationTools: Readonly<Record<string, AgentMcpToolConfiguration>> =
  mcpServerConfiguration.tools;
const mcpServer = new AgentMcpServer(
  "remote",
  "Remote",
  "oauth",
  mcpServerConfiguration,
  "user",
  true,
);
const mcpServerName: string = mcpServer.name;
const mcpServerDisplayName: string = mcpServer.displayName;
const mcpServerAuthStatus: AgentMcpAuthStatus = mcpServer.authStatus;
const mcpServerEffectiveConfiguration: AgentMcpServerConfiguration | null | undefined =
  mcpServer.configuration;
const mcpServerOrigin: AgentResourceOrigin = mcpServer.origin;
const mcpServerCanRemove: boolean = mcpServer.canRemove;
const mcpServerIsAuthorized: boolean = mcpServer.isAuthorized;
const validationIssue = new AgentElicitationValidationIssue("field", "missing_required");
const validationFieldName: string = validationIssue.fieldName;
const validationReason: AgentElicitationValidationReason = validationIssue.reason;
const validation = new AgentElicitationValidation([validationIssue]);
const validationIssues: ReadonlyArray<AgentElicitationValidationIssue> = validation.issues;
const validationIsValid: boolean = validation.isValid;
const elicitationClass: typeof AgentElicitation = AgentElicitation;
const elicitationResponseClass: typeof AgentElicitationResponse = AgentElicitationResponse;
const pendingApprovalClass: typeof AgentPendingApproval = AgentPendingApproval;
const pendingElicitationClass: typeof AgentPendingElicitation = AgentPendingElicitation;
const interactionStateClass: typeof AgentInteractionState = AgentInteractionState;
const elicitation = new AgentElicitation(
  "request",
  "server",
  "conversation",
  "Choose",
  [formField],
  null,
);
const elicitationRequestId: string = elicitation.requestId;
const elicitationServerName: string = elicitation.serverName;
const elicitationConversationId: string = elicitation.conversationId;
const elicitationMessage: string = elicitation.message;
const elicitationForm: ReadonlyArray<AgentFormField> | null | undefined = elicitation.form;
const elicitationUrl: string | null | undefined = elicitation.url;
const initialElicitationValues: Readonly<Record<string, AgentFormValue>> = elicitation.initialValues();
const elicitationValidation: AgentElicitationValidation = elicitation.validate(initialElicitationValues);
const elicitationResponse = elicitation.accept(initialElicitationValues);
const constructedResponse = new AgentElicitationResponse("accept", initialElicitationValues);
const elicitationAccepts: boolean = elicitation.accepts(elicitationResponse);
const responseAction: AgentElicitationAction = elicitationResponse.action;
const responseContent: Readonly<Record<string, AgentFormValue>> = elicitationResponse.content;
const declinedResponse: AgentElicitationResponse = AgentElicitationResponse.decline();
const cancelledResponse: AgentElicitationResponse = AgentElicitationResponse.cancel();
const pendingApproval = new AgentPendingApproval("approval", "conversation", "Approve?", "Details");
const pendingElicitation = new AgentPendingElicitation(elicitation);
const pendingInteraction: AgentPendingInteraction = pendingApproval;
const pendingApprovalRequestId: string = pendingApproval.requestId;
const pendingApprovalConversationId: string = pendingApproval.conversationId;
const pendingApprovalTitle: string = pendingApproval.title;
const pendingApprovalDetails: string = pendingApproval.details;
const pendingElicitationValue: AgentElicitation = pendingElicitation.elicitation;
const pendingElicitationRequestId: string = pendingElicitation.requestId;
const pendingElicitationConversationId: string = pendingElicitation.conversationId;
const pendingRequestId: string = pendingInteraction.requestId;
const pendingConversationId: string = pendingInteraction.conversationId;
const interactionState = new AgentInteractionState(
  [pendingApproval, pendingElicitation],
  [pendingApproval.requestId],
);
const statePending: ReadonlyArray<AgentPendingInteraction> = interactionState.pending;
const stateResolvingRequestIds: ReadonlyArray<string> = interactionState.resolvingRequestIds;
const interactionFailure: CodexFailure | null | undefined = interactionState.failure;
const conversationPending: ReadonlyArray<AgentPendingInteraction> =
  interactionState.pendingFor("conversation");
const interactionIsResolving: boolean = interactionState.isResolving(pendingApproval);
void [
  elicitationClass,
  elicitationResponseClass,
  constructedResponse,
  pendingApprovalClass,
  pendingElicitationClass,
  interactionStateClass,
  elicitationRequestId,
  elicitationServerName,
  elicitationConversationId,
  elicitationMessage,
  elicitationForm,
  elicitationUrl,
  elicitationValidation,
  elicitationAccepts,
  responseAction,
  responseContent,
  declinedResponse,
  cancelledResponse,
  pendingApprovalRequestId,
  pendingApprovalConversationId,
  pendingApprovalTitle,
  pendingApprovalDetails,
  pendingElicitationValue,
  pendingElicitationRequestId,
  pendingElicitationConversationId,
  pendingRequestId,
  pendingConversationId,
  statePending,
  stateResolvingRequestIds,
  interactionFailure,
  conversationPending,
  interactionIsResolving,
];
const planStep = new AgentPlanStep("Ship", "in_progress");
const planStepText: string = planStep.text;
const planStepStatus: AgentPlanStepStatus = planStep.status;
const emptyPlanProgress = new AgentPlanProgress();
const planProgress = new AgentPlanProgress(null, [planStep]);
const planExplanation: string | null | undefined = planProgress.explanation;
const planSteps: ReadonlyArray<AgentPlanStep> = planProgress.steps;
const hookActivity = new AgentHookActivity("hook", "SessionStart", "command", "running");
const hookActivities = [
  hookActivity,
  new AgentHookActivity("completed", "SessionStart", "command", "completed", null, ["done"]),
  new AgentHookActivity("failed", "SessionStart", "command", "failed"),
  new AgentHookActivity("blocked", "SessionStart", "command", "blocked"),
  new AgentHookActivity("stopped", "SessionStart", "command", "stopped"),
];
const hookActivityId: string = hookActivity.id;
const hookActivityEventName: string = hookActivity.eventName;
const hookActivityHandlerType: string = hookActivity.handlerType;
const hookActivityStatus: AgentHookRunStatus = hookActivity.status;
const hookActivityStatusMessage: string | null | undefined = hookActivity.statusMessage;
const hookActivityDetails: ReadonlyArray<string> = hookActivity.details;
const defaultConnector = new AgentConnector("drive", "Google Drive");
const customConnector = new AgentConnector(
  "slack",
  "Slack",
  "Team messaging",
  "https://example.com/install",
  true,
  false,
  ["Collaboration"],
);
const connectorValues: ReadonlyArray<AgentConnector> = [defaultConnector, customConnector];
const connectorId: string = customConnector.id;
const connectorName: string = customConnector.name;
const connectorDescription: string = customConnector.description;
const connectorInstallUrl: string | null | undefined = customConnector.installUrl;
const connectorIsAccessible: boolean = customConnector.isAccessible;
const connectorIsEnabled: boolean = customConnector.isEnabled;
const connectorPluginNames: ReadonlyArray<string> = customConnector.pluginNames;
const pluginReferenceClass: typeof AgentPluginReference = AgentPluginReference;
const pluginReference = new AgentPluginReference(
  "drive@openai-curated",
  "drive",
  "openai-curated",
  null,
  "plugin_remote_drive",
);
const pluginReferenceId: string = pluginReference.id;
const pluginReferenceName: string = pluginReference.name;
const pluginReferenceMarketplaceName: string = pluginReference.marketplaceName;
const pluginReferenceMarketplacePath: string | null | undefined = pluginReference.marketplacePath;
const pluginReferenceRemoteId: string | null | undefined = pluginReference.remotePluginId;
const pluginReferenceUri: string = pluginReference.uri;
const pluginSummaryClass: typeof AgentPluginSummary = AgentPluginSummary;
const pluginSummary = new AgentPluginSummary(
  pluginReference,
  "Drive",
  "Files in Drive",
  true,
  true,
  "available",
  "on_install",
  true,
  ["Search files"],
  "#4285f4",
  "https://example.com/privacy",
  "https://example.com/terms",
  "https://example.com",
);
const pluginSummaryReference: AgentPluginReference = pluginSummary.reference;
const pluginSummaryDisplayName: string = pluginSummary.displayName;
const pluginSummaryDescription: string = pluginSummary.description;
const pluginSummaryInstalled: boolean = pluginSummary.isInstalled;
const pluginSummaryEnabled: boolean = pluginSummary.isEnabled;
const pluginSummaryInstallPolicy: AgentPluginInstallPolicy = pluginSummary.installPolicy;
const pluginSummaryAuthPolicy: AgentPluginAuthPolicy = pluginSummary.authPolicy;
const pluginSummaryAvailable: boolean = pluginSummary.isAvailable;
const pluginSummaryCapabilities: ReadonlyArray<string> = pluginSummary.capabilities;
const pluginSummaryBrandColor: string | null | undefined = pluginSummary.brandColor;
const pluginSummaryPrivacyPolicy: string | null | undefined = pluginSummary.privacyPolicyUrl;
const pluginSummaryTerms: string | null | undefined = pluginSummary.termsOfServiceUrl;
const pluginSummaryWebsite: string | null | undefined = pluginSummary.websiteUrl;
const pluginCatalogClass: typeof AgentPluginCatalog = AgentPluginCatalog;
const pluginCatalog = new AgentPluginCatalog([pluginSummary], [], "live");
const pluginCatalogPlugins: ReadonlyArray<AgentPluginSummary> = pluginCatalog.plugins;
const pluginCatalogErrors: ReadonlyArray<string> = pluginCatalog.errors;
const pluginCatalogFreshness: AgentCatalogFreshness = pluginCatalog.freshness;
const pluginSkillClass: typeof AgentPluginSkill = AgentPluginSkill;
const pluginSkill = new AgentPluginSkill("search-drive", "Search Drive", true, "/plugin/SKILL.md");
const pluginSkillName: string = pluginSkill.name;
const pluginSkillDescription: string = pluginSkill.description;
const pluginSkillEnabled: boolean = pluginSkill.isEnabled;
const pluginSkillPath: string | null | undefined = pluginSkill.path;
const pluginDetailClass: typeof AgentPluginDetail = AgentPluginDetail;
const pluginDetail = new AgentPluginDetail(
  pluginSummary,
  "Complete Drive plugin",
  [pluginSkill],
  [customConnector],
  ["drive-mcp"],
  1,
);
const pluginDetailSummary: AgentPluginSummary = pluginDetail.summary;
const pluginDetailDescription: string = pluginDetail.description;
const pluginDetailSkills: ReadonlyArray<AgentPluginSkill> = pluginDetail.skills;
const pluginDetailConnectors: ReadonlyArray<AgentConnector> = pluginDetail.connectors;
const pluginDetailMcpServers: ReadonlyArray<string> = pluginDetail.mcpServers;
const pluginDetailHookCount: number = pluginDetail.hookCount;
const pluginInstallResultClass: typeof AgentPluginInstallResult = AgentPluginInstallResult;
const pluginInstallResult = new AgentPluginInstallResult("on_install", [customConnector], null);
const pluginInstallAuthPolicy: AgentPluginAuthPolicy = pluginInstallResult.authPolicy;
const pluginInstallConnectors: ReadonlyArray<AgentConnector> =
  pluginInstallResult.connectorsNeedingAuthentication;
const pluginInstallMessage: string | null | undefined = pluginInstallResult.message;
const connectorIntegrationClass: typeof AgentConnectorIntegration = AgentConnectorIntegration;
const connectorIntegration = new AgentConnectorIntegration(customConnector);
const connectorIntegrationConnector: AgentConnector = connectorIntegration.connector;
const connectorIntegrationId: string = connectorIntegration.id;
const connectorIntegrationDisplayName: string = connectorIntegration.displayName;
const mcpIntegrationClass: typeof AgentMcpServerIntegration = AgentMcpServerIntegration;
const mcpIntegration = new AgentMcpServerIntegration(mcpServer);
const mcpIntegrationServer: AgentMcpServer = mcpIntegration.server;
const mcpIntegrationId: string = mcpIntegration.id;
const mcpIntegrationDisplayName: string = mcpIntegration.displayName;
const integrationTargets: ReadonlyArray<AgentIntegration> = [connectorIntegration, mcpIntegration];
const integrationAuthorizationStateClass: typeof AgentIntegrationAuthorizationState =
  AgentIntegrationAuthorizationState;
const integrationAuthorizationState = new AgentIntegrationAuthorizationState(
  "awaiting_completion",
  connectorIntegration,
  null,
);
const integrationAuthorizationStateStatus: AgentIntegrationAuthorizationStatus =
  integrationAuthorizationState.status;
const integrationAuthorizationStateTarget: AgentIntegration | null | undefined =
  integrationAuthorizationState.target;
const integrationAuthorizationStateFailure: CodexFailure | null | undefined =
  integrationAuthorizationState.failure;
const skillInvocation = new AgentSkillInvocation("review", "/skills/review/SKILL.md");
const pluginInvocation = new AgentPluginInvocation("tools", "plugin://tools@official");
const skillInvocationClass: typeof AgentSkillInvocation = AgentSkillInvocation;
const pluginInvocationClass: typeof AgentPluginInvocation = AgentPluginInvocation;
const invocations: ReadonlyArray<AgentInvocation> = [skillInvocation, pluginInvocation];
const skillInvocationName: string = skillInvocation.name;
const skillInvocationPath: string = skillInvocation.path;
const skillInvocationKey: string = skillInvocation.key;
const pluginInvocationName: string = pluginInvocation.name;
const pluginInvocationUri: string = pluginInvocation.uri;
const pluginInvocationKey: string = pluginInvocation.key;
const conversationSummary = new AgentConversationSummary("conversation", "Conversation title", 1n);
const summaryConversationId: string = conversationSummary.conversationId;
const summaryTitle: string = conversationSummary.title;
const summaryUpdatedAtEpochSeconds: bigint = conversationSummary.updatedAtEpochSeconds;
const serviceTier: AgentServiceTier = new AgentServiceTier("fast", "Fast", "Lowest latency");
const serviceTierId: string = serviceTier.id;
const serviceTierName: string = serviceTier.name;
const serviceTierDescription: string = serviceTier.description;
const defaultModel: AgentModel = new AgentModel(
  "model-default",
  "Default model",
  "Default description",
  ["medium"],
  "medium",
  true,
);
const model: AgentModel = new AgentModel(
  "model",
  "Model",
  "Description",
  ["low", "medium", "high"],
  "medium",
  false,
  [serviceTier],
  "fast",
);
const modelId: string = model.id;
const modelDisplayName: string = model.displayName;
const modelDescription: string = model.description;
const modelSupportedEfforts: ReadonlyArray<string> = model.supportedEfforts;
const modelDefaultEffort: string = model.defaultEffort;
const modelIsDefault: boolean = model.isDefault;
const modelServiceTiers: ReadonlyArray<AgentServiceTier> = model.serviceTiers;
const modelDefaultServiceTier: string | null | undefined = model.defaultServiceTier;
const skill: AgentSkill = new AgentSkill(
  "review",
  "Review",
  "Review the current changes",
  "/skills/review/SKILL.md",
  "user",
  true,
  "#123456",
  ["git"],
  true,
  "user",
);
const skillName: string = skill.name;
const skillDisplayName: string = skill.displayName;
const skillDescription: string = skill.description;
const skillPath: string = skill.path;
const skillValueScope: AgentSkillScope = skill.scope;
const skillIsEnabled: boolean = skill.isEnabled;
const skillBrandColor: string | null | undefined = skill.brandColor;
const skillDependencies: ReadonlyArray<string> = skill.dependencies;
const skillCanUninstall: boolean = skill.canUninstall;
const skillOrigin: AgentResourceOrigin = skill.origin;
const skillCatalog: AgentSkillCatalog = new AgentSkillCatalog([skill], ["warning"]);
const catalogSkills: ReadonlyArray<AgentSkill> = skillCatalog.skills;
const catalogErrors: ReadonlyArray<string> = skillCatalog.errors;
const skillChunk: AgentSkillChunk = new AgentSkillChunk("content", 7n, 20n);
const skillChunkContent: string = skillChunk.content;
const skillChunkNextOffset: bigint | null | undefined = skillChunk.nextOffset;
const skillChunkTotalBytes: bigint = skillChunk.totalBytes;
const hookHandler: AgentHookHandler = { type: "command", command: "./check", isAsync: false };
const hook: AgentHook = new AgentHook(
  "review-hook",
  "sha256:review",
  true,
  "preToolUse",
  hookHandler,
  false,
  "PROJECT",
  "/workspace/.codex/hooks.json",
  10n,
  "untrusted",
  "Shell",
  null,
  "Review shell commands",
  "workspace",
  true,
);
const hookClass: typeof AgentHook = AgentHook;
const hookKey: string = hook.key;
const hookCurrentHash: string = hook.currentHash;
const hookIsEnabled: boolean = hook.isEnabled;
const hookEventName: string = hook.eventName;
const projectedHookHandler: AgentHookHandler = hook.handler;
const hookIsManaged: boolean = hook.isManaged;
const hookSource: string = hook.source;
const hookSourcePath: string = hook.sourcePath;
const hookTimeoutSeconds: bigint = hook.timeoutSeconds;
const hookTrustStatus: AgentHookTrustStatus = hook.trustStatus;
const hookMatcher: string | null | undefined = hook.matcher;
const hookPluginId: string | null | undefined = hook.pluginId;
const hookStatusMessage: string | null | undefined = hook.statusMessage;
const hookOrigin: AgentResourceOrigin = hook.origin;
const hookCanUninstall: boolean = hook.canUninstall;
const hookCanTrust: boolean = hook.canTrust;
const hookCatalog: AgentHookCatalog = new AgentHookCatalog([hook], ["warning"], ["error"]);
const hookCatalogClass: typeof AgentHookCatalog = AgentHookCatalog;
const catalogHooks: ReadonlyArray<AgentHook> = hookCatalog.hooks;
const hookCatalogWarnings: ReadonlyArray<string> = hookCatalog.warnings;
const hookCatalogErrors: ReadonlyArray<string> = hookCatalog.errors;
const enumEvidence: {
  approvalDecision: AgentApprovalDecision;
  capability: AgentCapability;
  catalogFreshness: AgentCatalogFreshness;
  collaborationMode: AgentCollaborationMode;
  elicitationAction: AgentElicitationAction;
  elicitationValidationReason: AgentElicitationValidationReason;
  formFieldType: AgentFormFieldType;
  formStringFormat: AgentFormStringFormat;
  hookRunStatus: AgentHookRunStatus;
  hookTrustStatus: AgentHookTrustStatus;
  installationScope: AgentInstallationScope;
  integrationAuthorizationStatus: AgentIntegrationAuthorizationStatus;
  mcpAuthStatus: AgentMcpAuthStatus;
  mcpAuthentication: AgentMcpAuthentication;
  mcpEnvironmentSource: AgentMcpEnvironmentSource;
  mcpToolApproval: AgentMcpToolApproval;
  mcpToolExposureSurface: AgentMcpToolExposureSurface;
  planStepStatus: AgentPlanStepStatus;
  pluginAuthPolicy: AgentPluginAuthPolicy;
  pluginInstallPolicy: AgentPluginInstallPolicy;
  resolution: AgentResolution;
  resourceOrigin: AgentResourceOrigin;
  skillScope: AgentSkillScope;
  approvalPreset: CodexApprovalPreset;
  authenticationStatus: CodexAuthenticationStatus;
  authorizationPurpose: CodexAuthorizationPurpose;
  conversationStatus: CodexConversationStatus;
  messageRole: CodexMessageRole;
  workActivity: CodexWorkActivity;
  workspaceSelectionReason: CodexWorkspaceSelectionReason;
} = {
  approvalDecision: "accept",
  capability: "web_search",
  catalogFreshness: "fresh_cache",
  collaborationMode: "default",
  elicitationAction: "accept",
  elicitationValidationReason: "above_maximum",
  formFieldType: "boolean",
  formStringFormat: "date",
  hookRunStatus: "blocked",
  hookTrustStatus: "managed",
  installationScope: "user",
  integrationAuthorizationStatus: "authorized",
  mcpAuthStatus: "bearer_token",
  mcpAuthentication: "chat_gpt",
  mcpEnvironmentSource: "local",
  mcpToolApproval: "approve",
  mcpToolExposureSurface: "code_mode",
  planStepStatus: "completed",
  pluginAuthPolicy: "on_install",
  pluginInstallPolicy: "available",
  resolution: "default",
  resourceOrigin: "managed",
  skillScope: "admin",
  approvalPreset: "ask_me",
  authenticationStatus: "authenticated",
  authorizationPurpose: "chat_gpt",
  conversationStatus: "cancelling_turn",
  messageRole: "assistant",
  workActivity: "running_command",
  workspaceSelectionReason: "access_revoked",
};
const observation: CodexObservation = host.observeState((next: CodexHostState): void => {
  const status: string = next.status;
  void status;
});
observation.close();
observation.dispose();
observation[Symbol.dispose]();

async function useAgent(agent: CodexAgent, signal: AbortSignal): Promise<void> {
  const connectors: CodexConnectors = agent.connectors;
  const connectorsAvailable: boolean = connectors.isAvailable;
  const listedConnectors: ReadonlyArray<AgentConnector> = await connectors.list();
  await connectors.list(true, signal);
  const models: CodexModels = agent.models;
  const listedModels: ReadonlyArray<AgentModel> = await models.list();
  await models.list(signal);
  const resolvedModel: AgentModel = await models.resolve();
  await models.resolve("default", signal);
  const resolvedEffort: string = await models.resolveEffort(model);
  await models.resolveEffort(model, "first", signal);
  const resolvedServiceTier: AgentServiceTier | null | undefined =
    await models.resolveServiceTier(model);
  await models.resolveServiceTier(model, "preferred", signal);
  const skills: CodexSkills = agent.skills;
  const skillsAvailable: boolean = skills.isAvailable;
  const listedSkills: AgentSkillCatalog = await skills.list();
  await skills.list(true, signal);
  const readSkill: AgentSkillChunk = await skills.read("/skills/review/SKILL.md");
  await skills.read("/skills/review/SKILL.md", 7n, signal);
  const installedSkill: AgentSkill = await skills.install("/skills/review", "workspace", signal);
  await skills.uninstall(installedSkill, signal);
  const hooks: CodexHooks = agent.hooks;
  const hooksClass: typeof CodexHooks = CodexHooks;
  const hooksAvailable: boolean = hooks.isAvailable;
  const listedHooks: AgentHookCatalog = await hooks.list(signal);
  const installedHook: AgentHook = await hooks.install("/hooks/review", "workspace", signal);
  await hooks.uninstall(installedHook, signal);
  await hooks.trust(hook, signal);
  const plugins: CodexPlugins = agent.plugins;
  const pluginsClass: typeof CodexPlugins = CodexPlugins;
  const pluginsAvailable: boolean = plugins.isAvailable;
  const listedPluginCatalog: AgentPluginCatalog = await plugins.list(true, signal);
  const readPluginDetail: AgentPluginDetail = await plugins.read(pluginReference, signal);
  const installedPlugin: AgentPluginInstallResult = await plugins.install(pluginReference, signal);
  await plugins.uninstall(pluginReference, signal);
  const mcpServers: CodexMcpServers = agent.mcpServers;
  const mcpServersClass: typeof CodexMcpServers = CodexMcpServers;
  const mcpServersAvailable: boolean = mcpServers.isAvailable;
  const listedMcpServers: ReadonlyArray<AgentMcpServer> = await mcpServers.list(signal);
  const addedMcpServer: AgentMcpServer = await mcpServers.add(mcpServerConfiguration, signal);
  await mcpServers.remove(addedMcpServer, signal);
  const activeConversation: CodexConversation | null | undefined = agent.activeConversation;
  agent.observeActiveConversation(
    (next: CodexConversation | null | undefined): void => void next,
  ).dispose();
  const authentication: CodexAuthentication = agent.authentication;
  const authenticationState: CodexAuthenticationState = authentication.state;
  const authenticationStatus: CodexAuthenticationStatus = authenticationState.status;
  const authenticationMethod: CodexAuthenticationMethod = "api_key";
  const isAuthenticated: boolean = authentication.isAuthenticated;
  const isAuthenticating: boolean = authentication.isAuthenticating;
  const pendingSignInUrl: CodexAuthorizationUrl | null | undefined =
    authenticationState.pendingSignInUrl;
  const deviceVerificationUrl: CodexAuthorizationUrl | null | undefined =
    authenticationState.deviceVerificationUrl;
  const deviceUserCode: string | null | undefined = authenticationState.deviceUserCode;
  const authenticationFailure: CodexFailure | null | undefined = authenticationState.failure;
  authentication.observeState((next: CodexAuthenticationState): void => void next.status).dispose();
  authentication.observeAuthenticated((next: boolean): void => void next).dispose();
  authentication.observeAuthenticating((next: boolean): void => void next).dispose();
  await authentication.authenticate("chatgpt_browser", null, signal);
  await authentication.authenticate("chatgpt_device_code", null, signal);
  await authentication.authenticate(authenticationMethod, "sk-test", signal);
  await authentication.cancel(signal);
  await authentication.signOut(signal);
  const integrationAuthorization: CodexIntegrationAuthorization = agent.integrationAuthorization;
  const integrationAuthorizationClass: typeof CodexIntegrationAuthorization =
    CodexIntegrationAuthorization;
  const currentIntegrationAuthorizationState: AgentIntegrationAuthorizationState =
    integrationAuthorization.state;
  const activeIntegration: AgentIntegration | null | undefined = integrationAuthorization.active;
  const isAuthorizingIntegration: boolean = integrationAuthorization.isAuthorizing;
  integrationAuthorization.observeState(
    (next: AgentIntegrationAuthorizationState): void => void next.status,
  ).dispose();
  integrationAuthorization.observeActive(
    (next: AgentIntegration | null | undefined): void => void next,
  ).dispose();
  integrationAuthorization.observeAuthorizing((next: boolean): void => void next).dispose();
  await integrationAuthorization.authorize(connectorIntegration, signal);
  await integrationAuthorization.cancel(signal);
  const interactions: CodexInteractions = agent.interactions;
  const interactionsClass: typeof CodexInteractions = CodexInteractions;
  const currentInteractionState: AgentInteractionState = interactions.state;
  const currentApprovals: ReadonlyArray<AgentPendingApproval> = interactions.approvals;
  const currentElicitations: ReadonlyArray<AgentPendingElicitation> = interactions.elicitations;
  interactions.observeState((next: AgentInteractionState): void => void next.pending).dispose();
  interactions.observeApprovals(
    (next: ReadonlyArray<AgentPendingApproval>): void => void next,
  ).dispose();
  interactions.observeElicitations(
    (next: ReadonlyArray<AgentPendingElicitation>): void => void next,
  ).dispose();
  await interactions.resolve(pendingApproval, "accept", signal);
  await interactions.resolve(pendingElicitation, elicitationResponse, signal);
  await interactions.openUrl(pendingElicitation, signal);
  const conversation: CodexConversation = await agent.openConversation(
    null,
    approvalPreset,
    null,
    signal,
  );
  await agent.rename("conversation", "Renamed conversation", signal);
  await agent.delete("conversation", signal);
  const conversationSummaries: ReadonlyArray<AgentConversationSummary> = await agent.listConversations();
  await agent.listConversations(signal);
  const historicalConversation: AgentConversation = await agent.readConversation("conversation", signal);
  const historicalSummary: AgentConversationSummary = historicalConversation.summary;
  const historicalMessages = historicalConversation.messages;
  const conversationState: CodexConversationState = conversation.state;
  const reconciledConversation: AgentConversation | null | undefined = conversationState.conversation;
  const messages = conversationState.messages;
  const constructedConversation = new AgentConversation(conversationSummary, messages);
  const messageCollaborationModes: ReadonlyArray<AgentCollaborationMode> =
    messages.map((message) => message.collaborationMode);
  const messageCapabilities: ReadonlyArray<ReadonlyArray<AgentCapability>> =
    messages.map((message) => message.capabilities);
  const messageInvocations: ReadonlyArray<ReadonlyArray<AgentInvocation>> =
    messages.map((message) => message.invocations);
  const turnProgress = conversationState.turnProgress;
  const turnPlanProgress: AgentPlanProgress | null | undefined = turnProgress?.planProgress;
  const turnHookActivities: ReadonlyArray<AgentHookActivity> | undefined = turnProgress?.hookActivities;
  const canStartTurn: boolean = conversationState.canStartTurn;
  const canReload: boolean = conversationState.canReload;
  const canCancelTurn: boolean = conversationState.canCancelTurn;
  const canRunShellCommand: boolean = conversationState.canRunShellCommand;
  const isTurnActive: boolean = conversationState.isTurnActive;
  conversation.observeState((next: CodexConversationState): void => {
    void [
      next.status,
      next.messages,
      next.turnProgress,
      next.canStartTurn,
      next.canReload,
      next.canCancelTurn,
      next.canRunShellCommand,
      next.isTurnActive,
    ];
  }).dispose();
  await conversation.send("hello", signal);
  const turnRequest: AgentTurnRequest = {
    prompt: "review",
    clientMessageId: "client-request",
    model: "model",
    effort: "medium",
    serviceTier: "fast",
    approvalPreset,
    capabilities: [capability],
    invocations: [skillInvocation, pluginInvocation],
    collaborationMode: "plan",
  };
  await conversation.sendRequest(turnRequest, signal);
  await conversation.runShellCommand("pwd", signal);
  await conversation.cancelTurn();
  await conversation.reload(signal);
  await conversation.close();
  await conversation.dispose();
  await conversation[Symbol.asyncDispose]();
  void [
    authenticationStatus,
    connectorsAvailable,
    listedConnectors,
    listedModels,
    resolvedModel,
    resolvedEffort,
    resolvedServiceTier,
    skillsAvailable,
    listedSkills,
    readSkill,
    installedSkill,
    hooksClass,
    hooksAvailable,
    listedHooks,
    installedHook,
    mcpServersClass,
    mcpServersAvailable,
    listedMcpServers,
    addedMcpServer,
    isAuthenticated,
    isAuthenticating,
    pendingSignInUrl,
    deviceVerificationUrl,
    deviceUserCode,
    authenticationFailure,
    integrationAuthorizationClass,
    interactionsClass,
    currentInteractionState,
    currentApprovals,
    currentElicitations,
    currentIntegrationAuthorizationState,
    activeIntegration,
    isAuthorizingIntegration,
    activeConversation,
    conversationSummaries,
    historicalConversation,
    historicalSummary,
    historicalMessages,
    constructedConversation,
    conversationState,
    reconciledConversation,
    messages,
    messageCollaborationModes,
    messageCapabilities,
    messageInvocations,
    turnProgress,
    turnPlanProgress,
    turnHookActivities,
    canStartTurn,
    canReload,
    canCancelTurn,
    canRunShellCommand,
    isTurnActive,
  ];
}

async function handleFailure(operation: Promise<void>): Promise<void> {
  try {
    await operation;
  } catch (error: unknown) {
    if (error instanceof CodexError) {
      const code: string = error.code;
      const recoverable: boolean = error.recoverable;
      const cause: unknown = error.cause;
      void [code, recoverable, cause];
    }
  }
}

void state;
void hostStatus;
void [
  hostWorkspace,
  hostAgent,
  hostSelectionReason,
  hostSelectionMessage,
  hostFailure,
  approvalPresetDisplayName,
  skillScopeDisplayName,
  capabilityId,
  capabilityDisplayLabel,
  capabilityIcon,
  capabilityPromptLabel,
  chatGptAuthorizationUrl,
  externalAuthorizationUrl,
  authorizationUrlValue,
  authorizationUrlPurpose,
  formOptionValue,
  formOptionTitle,
  formOptionDescription,
  formText,
  formNumber,
  formBoolean,
  formTextList,
  mcpEnvironmentNames,
  mcpEnvironmentSources,
  mcpOauthClientIds,
  mcpOauthCallbackPorts,
  mcpToolApprovals,
  mcpStdioTransportClass,
  mcpHttpTransportClass,
  mcpServerConfigurationClass,
  mcpServerClass,
  mcpTransport,
  mcpStdioCommand,
  mcpStdioArguments,
  mcpStdioWorkingDirectory,
  mcpStdioEnvironment,
  mcpStdioForwardedEnvironment,
  mcpHttpUrl,
  mcpHttpBearerTokenEnvironmentVariable,
  mcpHttpHeaders,
  mcpHttpEnvironmentHeaders,
  mcpHttpHeadersHelper,
  mcpConfigurationName,
  mcpConfigurationTransport,
  mcpConfigurationAuthentication,
  mcpConfigurationEnvironmentId,
  mcpConfigurationIsEnabled,
  mcpConfigurationIsRequired,
  mcpConfigurationSupportsParallelToolCalls,
  mcpConfigurationOmitToolsFrom,
  mcpConfigurationStartupTimeoutSeconds,
  mcpConfigurationToolTimeoutSeconds,
  mcpConfigurationDefaultToolApproval,
  mcpConfigurationEnabledTools,
  mcpConfigurationDisabledTools,
  mcpConfigurationScopes,
  mcpConfigurationOauth,
  mcpConfigurationOauthResource,
  mcpConfigurationTools,
  mcpServerName,
  mcpServerDisplayName,
  mcpServerAuthStatus,
  mcpServerEffectiveConfiguration,
  mcpServerOrigin,
  mcpServerCanRemove,
  mcpServerIsAuthorized,
  validationFieldName,
  validationReason,
  validationIssues,
  validationIsValid,
  hookActivities,
  hookActivityId,
  hookActivityEventName,
  hookActivityHandlerType,
  hookActivityStatus,
  hookActivityStatusMessage,
  hookActivityDetails,
  connectorValues,
  connectorId,
  connectorName,
  connectorDescription,
  connectorInstallUrl,
  connectorIsAccessible,
  connectorIsEnabled,
  connectorPluginNames,
  connectorIntegrationClass,
  connectorIntegrationConnector,
  connectorIntegrationId,
  connectorIntegrationDisplayName,
  mcpIntegrationClass,
  mcpIntegrationServer,
  mcpIntegrationId,
  mcpIntegrationDisplayName,
  integrationTargets,
  integrationAuthorizationStateClass,
  integrationAuthorizationStateStatus,
  integrationAuthorizationStateTarget,
  integrationAuthorizationStateFailure,
  skillInvocationClass,
  pluginInvocationClass,
  invocations,
  skillInvocationName,
  skillInvocationPath,
  skillInvocationKey,
  pluginInvocationName,
  pluginInvocationUri,
  pluginInvocationKey,
  summaryConversationId,
  summaryTitle,
  summaryUpdatedAtEpochSeconds,
  serviceTierId,
  serviceTierName,
  serviceTierDescription,
  defaultModel,
  modelId,
  modelDisplayName,
  modelDescription,
  modelSupportedEfforts,
  modelDefaultEffort,
  modelIsDefault,
  modelServiceTiers,
  modelDefaultServiceTier,
  skillName,
  skillDisplayName,
  skillDescription,
  skillPath,
  skillValueScope,
  skillIsEnabled,
  skillBrandColor,
  skillDependencies,
  skillCanUninstall,
  skillOrigin,
  catalogSkills,
  catalogErrors,
  skillChunkContent,
  skillChunkNextOffset,
  skillChunkTotalBytes,
  hookClass,
  hookKey,
  hookCurrentHash,
  hookIsEnabled,
  hookEventName,
  projectedHookHandler,
  hookIsManaged,
  hookSource,
  hookSourcePath,
  hookTimeoutSeconds,
  hookTrustStatus,
  hookMatcher,
  hookPluginId,
  hookStatusMessage,
  hookOrigin,
  hookCanUninstall,
  hookCanTrust,
  hookCatalogClass,
  catalogHooks,
  hookCatalogWarnings,
  hookCatalogErrors,
];
void enumEvidence;
void useAgent;
void handleFailure;
void host.start(new AbortController().signal);
void host.selectWorkspace("/workspace");
void host.close();
void host.dispose();
void host[Symbol.asyncDispose]();
