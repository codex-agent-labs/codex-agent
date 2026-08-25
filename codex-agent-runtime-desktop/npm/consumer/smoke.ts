import {
  AgentElicitationValidation,
  AgentElicitationValidationIssue,
  AgentFormBooleanValue,
  AgentFormNumberValue,
  AgentFormOption,
  AgentFormTextListValue,
  AgentFormTextValue,
  AgentHookActivity,
  AgentMcpEnvironmentVariable,
  AgentMcpOauthConfiguration,
  AgentMcpToolConfiguration,
  AgentPlanProgress,
  AgentPlanStep,
  CodexAgent,
  CodexAuthentication,
  CodexAuthenticationState,
  CodexConversation,
  CodexConversationState,
  CodexError,
  CodexFailure,
  CodexHost,
  CodexHostState,
  CodexObservation,
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
  AgentHookRunStatus,
  AgentHookTrustStatus,
  AgentInstallationScope,
  AgentIntegrationAuthorizationStatus,
  AgentMcpAuthStatus,
  AgentMcpAuthentication,
  AgentMcpEnvironmentSource,
  AgentMcpToolApproval,
  AgentMcpToolExposureSurface,
  AgentPlanStepStatus,
  AgentPluginAuthPolicy,
  AgentPluginInstallPolicy,
  AgentResolution,
  AgentResourceOrigin,
  AgentSkillScope,
  CodexApprovalPreset,
  CodexAuthenticationMethod,
  CodexAuthenticationStatus,
  CodexAuthorizationPurpose,
  CodexConversationStatus,
  CodexHostStatus,
  CodexMessageRole,
  CodexWorkActivity,
  CodexWorkspaceSelectionReason,
} from "@codex-agent-labs/codex-agent";

const host: CodexHost = createCodexHost("/bundle", "/data", "typescript", "TypeScript", "test");
const state: CodexHostState = host.state;
const hostStatus: CodexHostStatus = state.status;
const approvalPreset: CodexApprovalPreset = "auto_review";
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
const validationIssue = new AgentElicitationValidationIssue("field", "missing_required");
const validationFieldName: string = validationIssue.fieldName;
const validationReason: AgentElicitationValidationReason = validationIssue.reason;
const validation = new AgentElicitationValidation([validationIssue]);
const validationIssues: ReadonlyArray<AgentElicitationValidationIssue> = validation.issues;
const validationIsValid: boolean = validation.isValid;
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
  const pendingSignInUrl: string | null | undefined = authenticationState.pendingSignInUrl;
  const deviceVerificationUrl: string | null | undefined = authenticationState.deviceVerificationUrl;
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
  const conversation: CodexConversation = await agent.openConversation(
    null,
    approvalPreset,
    null,
    signal,
  );
  await agent.rename("conversation", "Renamed conversation", signal);
  await agent.delete("conversation", signal);
  const conversationState: CodexConversationState = conversation.state;
  const messages = conversationState.messages;
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
  await conversation.runShellCommand("pwd", signal);
  await conversation.cancelTurn();
  await conversation.reload(signal);
  await conversation.close();
  await conversation.dispose();
  await conversation[Symbol.asyncDispose]();
  void [
    authenticationStatus,
    isAuthenticated,
    isAuthenticating,
    pendingSignInUrl,
    deviceVerificationUrl,
    deviceUserCode,
    authenticationFailure,
    activeConversation,
    conversationState,
    messages,
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
];
void enumEvidence;
void useAgent;
void handleFailure;
void host.start(new AbortController().signal);
void host.selectWorkspace("/workspace");
void host.close();
void host.dispose();
void host[Symbol.asyncDispose]();
