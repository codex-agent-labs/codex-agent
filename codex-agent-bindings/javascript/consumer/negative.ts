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
  CodexAuthorizationUrl,
  CodexConnectors,
  CodexModels,
  CodexMcpServers,
  CodexPlugins,
  CodexIntegrationAuthorization,
  CodexInteractions,
  AgentIntegrationAuthorizationState,
  CodexSkills,
  CodexHooks,
  agentCapabilityDisplayLabel,
  agentCapabilityIcon,
  agentCapabilityId,
  agentCapabilityPromptLabel,
  agentSkillScopeDisplayName,
  codexApprovalPresetDisplayName,
} from "@codex-agent-labs/codex-agent";
import type {
  AgentCapability,
  AgentFormValue,
  AgentHookHandler,
  AgentHookTrustStatus,
  AgentInvocation,
  AgentIntegration,
  AgentMcpTransport,
  AgentPendingInteraction,
  AgentTurnRequest,
  CodexAgent,
  CodexAuthenticationState,
  CodexConversation,
  CodexConversationState,
  CodexHostState,
  CodexMessage,
  CodexTurnProgress,
} from "@codex-agent-labs/codex-agent";

// @ts-expect-error Raw Kotlin enum names are outside the public TypeScript domain.
codexApprovalPresetDisplayName("AUTO_REVIEW");
// @ts-expect-error Raw Kotlin enum names are outside the public TypeScript domain.
agentSkillScopeDisplayName("SYSTEM");
// @ts-expect-error Raw Kotlin enum names are outside the public TypeScript domain.
agentCapabilityId("WEB_SEARCH");
// @ts-expect-error Raw Kotlin enum names are outside the public TypeScript domain.
agentCapabilityDisplayLabel("WEB_SEARCH");
// @ts-expect-error Raw Kotlin enum names are outside the public TypeScript domain.
agentCapabilityIcon("WEB_SEARCH");
// @ts-expect-error Raw Kotlin enum names are outside the public TypeScript domain.
agentCapabilityPromptLabel("WEB_SEARCH");

// @ts-expect-error Authorization URLs are created by their validated static factories.
new CodexAuthorizationUrl();
const authorizationUrl = CodexAuthorizationUrl.chatGpt("https://auth.openai.com/authorize");
// @ts-expect-error Authorization URL values are readonly.
authorizationUrl.value = "https://chatgpt.com/authorize";
// @ts-expect-error Authorization URL purposes are readonly.
authorizationUrl.purpose = "external";
// @ts-expect-error ChatGPT authorization URL values are strings.
CodexAuthorizationUrl.chatGpt(1);
// @ts-expect-error External authorization URL values are strings.
CodexAuthorizationUrl.external(1);
declare const authenticationState: CodexAuthenticationState;
// @ts-expect-error Pending sign-in URLs retain their validated value object.
const legacyPendingSignInUrl: string | null | undefined = authenticationState.pendingSignInUrl;
// @ts-expect-error Device-verification URLs retain their validated value object.
const legacyDeviceVerificationUrl: string | null | undefined = authenticationState.deviceVerificationUrl;

declare const hostState: CodexHostState;
// @ts-expect-error Host-state workspaces are readonly.
hostState.workspace = null;
// @ts-expect-error Host-state agents are readonly.
hostState.agent = null;
// @ts-expect-error Host-state selection reasons are readonly.
hostState.selectionReason = null;
// @ts-expect-error Host-state selection messages are readonly.
hostState.selectionMessage = null;
// @ts-expect-error Host-state failures are readonly.
hostState.failure = null;

const skillInvocation = new AgentSkillInvocation("review", "/skills/review/SKILL.md");
// @ts-expect-error Skill invocation names are strings.
new AgentSkillInvocation(1, "/skills/review/SKILL.md");
// @ts-expect-error Skill invocation paths are strings.
new AgentSkillInvocation("review", 1);
// @ts-expect-error Skill invocation paths are required.
new AgentSkillInvocation("review");
// @ts-expect-error Immutable skill invocation names are readonly.
skillInvocation.name = "changed";
// @ts-expect-error Immutable skill invocation paths are readonly.
skillInvocation.path = "/changed";
// @ts-expect-error Derived skill invocation keys are readonly.
skillInvocation.key = "changed";

const pluginInvocation = new AgentPluginInvocation("tools", "plugin://tools@official");
// @ts-expect-error Plugin invocation names are strings.
new AgentPluginInvocation(1, "plugin://tools@official");
// @ts-expect-error Plugin invocation URIs are strings.
new AgentPluginInvocation("tools", 1);
// @ts-expect-error Plugin invocation URIs are required.
new AgentPluginInvocation("tools");
// @ts-expect-error Immutable plugin invocation names are readonly.
pluginInvocation.name = "changed";
// @ts-expect-error Immutable plugin invocation URIs are readonly.
pluginInvocation.uri = "plugin://changed@official";
// @ts-expect-error Derived plugin invocation keys are readonly.
pluginInvocation.key = "changed";

// @ts-expect-error Invocation values must use one of the reviewed concrete shapes.
const invalidInvocation: AgentInvocation = { name: "invalid", key: "invalid" };

const connectorIntegration = new AgentConnectorIntegration(new AgentConnector("drive", "Drive"));
// @ts-expect-error Connector integration targets require a connector.
new AgentConnectorIntegration();
// @ts-expect-error Connector integration targets require canonical connectors.
new AgentConnectorIntegration({});
// @ts-expect-error Connector integration connector values are readonly.
connectorIntegration.connector = new AgentConnector("other", "Other");
// @ts-expect-error Connector integration IDs are readonly.
connectorIntegration.id = "other";
// @ts-expect-error Connector integration display names are readonly.
connectorIntegration.displayName = "Other";

const integrationMcpServer = new AgentMcpServer("drive", "Drive", "not_logged_in");
const mcpIntegration = new AgentMcpServerIntegration(integrationMcpServer);
// @ts-expect-error MCP integration targets require a server.
new AgentMcpServerIntegration();
// @ts-expect-error MCP integration targets require canonical servers.
new AgentMcpServerIntegration({});
// @ts-expect-error MCP integration server values are readonly.
mcpIntegration.server = integrationMcpServer;
// @ts-expect-error MCP integration IDs are readonly.
mcpIntegration.id = "other";
// @ts-expect-error MCP integration display names are readonly.
mcpIntegration.displayName = "Other";
// @ts-expect-error Integration targets use one of the reviewed concrete values.
const invalidIntegration: AgentIntegration = { id: "drive", displayName: "Drive" };

const integrationState = new AgentIntegrationAuthorizationState();
// @ts-expect-error Integration authorization statuses remain a closed typed domain.
new AgentIntegrationAuthorizationState("IDLE");
// @ts-expect-error Integration authorization targets use reviewed integration values.
new AgentIntegrationAuthorizationState("idle", {});
// @ts-expect-error Integration authorization failures use canonical failure values.
new AgentIntegrationAuthorizationState("failed", null, {});
// @ts-expect-error Integration authorization state statuses are readonly.
integrationState.status = "authorized";
// @ts-expect-error Integration authorization state targets are readonly.
integrationState.target = connectorIntegration;
// @ts-expect-error Integration authorization state failures are readonly.
integrationState.failure = null;
// @ts-expect-error Capabilities remain a closed typed domain.
const invalidCapabilities: ReadonlyArray<AgentCapability> = ["WEB_SEARCH"];
declare const message: CodexMessage;
// @ts-expect-error Message collaboration modes remain a closed typed domain.
const invalidCollaborationMode: typeof message.collaborationMode = "PLAN";
// @ts-expect-error Immutable message collaboration modes are readonly.
message.collaborationMode = "plan";
// @ts-expect-error Immutable message capability collections cannot be replaced.
message.capabilities = [];
// @ts-expect-error Message capability collections are readonly.
message.capabilities.push("web_search");
// @ts-expect-error Immutable message invocation collections cannot be replaced.
message.invocations = [];
// @ts-expect-error Message invocation collections are readonly.
message.invocations.push(skillInvocation);
// @ts-expect-error Message invocation collections contain reviewed invocation values.
const invalidInvocations: ReadonlyArray<AgentInvocation> = [{}];

const option = new AgentFormOption("value");
// @ts-expect-error Immutable form-option values are readonly.
option.value = "changed";
// @ts-expect-error A defaulted title remains non-null when provided.
new AgentFormOption("value", null);
// @ts-expect-error Descriptions are nullable strings, not numbers.
new AgentFormOption("value", "title", 1);

const textValue = new AgentFormTextValue("text");
// @ts-expect-error Text form values require strings.
new AgentFormTextValue(1);
// @ts-expect-error Text form values require one argument.
new AgentFormTextValue();
// @ts-expect-error Immutable text form values are readonly.
textValue.value = "changed";

const numberValue = new AgentFormNumberValue(1.5);
// @ts-expect-error Number form values require numbers.
new AgentFormNumberValue("1.5");
// @ts-expect-error Number form values require one argument.
new AgentFormNumberValue();
// @ts-expect-error Immutable number form values are readonly.
numberValue.value = 2;

const booleanValue = new AgentFormBooleanValue(true);
// @ts-expect-error Boolean form values require booleans.
new AgentFormBooleanValue(1);
// @ts-expect-error Boolean form values require one argument.
new AgentFormBooleanValue();
// @ts-expect-error Immutable boolean form values are readonly.
booleanValue.value = false;

const textListValue = new AgentFormTextListValue(["first", "second"]);
// @ts-expect-error Text-list form values require strings.
new AgentFormTextListValue(["first", 2]);
// @ts-expect-error Text-list form values require one argument.
new AgentFormTextListValue();
// @ts-expect-error Immutable text-list form values are readonly.
textListValue.value = [];
// @ts-expect-error Text-list form value elements are readonly.
textListValue.value.push("third");

const formField = new AgentFormField(
  "email",
  "Email",
  "string",
  null,
  true,
  [option],
  textValue,
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
// @ts-expect-error Form fields require name, title, and type.
new AgentFormField("email", "Email");
// @ts-expect-error Form-field names are strings.
new AgentFormField(1, "Email", "string");
// @ts-expect-error Form-field titles are strings.
new AgentFormField("email", 1, "string");
// @ts-expect-error Form-field types remain a closed typed domain.
new AgentFormField("email", "Email", "text");
// @ts-expect-error Form-field descriptions are nullable strings.
new AgentFormField("email", "Email", "string", 1);
// @ts-expect-error Required markers are booleans.
new AgentFormField("email", "Email", "string", null, "true");
// @ts-expect-error Form-field options use canonical option values.
new AgentFormField("email", "Email", "string", null, false, [{}]);
// @ts-expect-error Default values use one of the reviewed form-value shapes.
new AgentFormField("email", "Email", "string", null, false, [], { invalid: true });
// @ts-expect-error Numeric minima are nullable numbers.
new AgentFormField("email", "Email", "string", null, false, [], null, "1");
// @ts-expect-error Numeric maxima are nullable numbers.
new AgentFormField("email", "Email", "string", null, false, [], null, null, "2");
// @ts-expect-error String formats remain a closed typed domain.
new AgentFormField("email", "Email", "string", null, false, [], null, null, null, "EMAIL");
// @ts-expect-error Length bounds use bigint values.
new AgentFormField("email", "Email", "string", null, false, [], null, null, null, null, 1);
// @ts-expect-error Maximum lengths use bigint values.
new AgentFormField("email", "Email", "string", null, false, [], null, null, null, null, 1n, 2);
// @ts-expect-error Selection minima use bigint values.
new AgentFormField("email", "Email", "string", null, false, [], null, null, null, null, 1n, 2n, 1);
// @ts-expect-error Selection maxima use bigint values.
new AgentFormField("email", "Email", "string", null, false, [], null, null, null, null, 1n, 2n, 1n, 2);
// @ts-expect-error Other-value flags are booleans.
new AgentFormField("email", "Email", "string", null, false, [], null, null, null, null, 1n, 2n, 1n, 2n, "true");
// @ts-expect-error Secret flags are booleans.
new AgentFormField("email", "Email", "string", null, false, [], null, null, null, null, 1n, 2n, 1n, 2n, false, "true");
// @ts-expect-error Immutable form-field names are readonly.
formField.name = "changed";
// @ts-expect-error Immutable form-field titles are readonly.
formField.title = "Changed";
// @ts-expect-error Immutable form-field types are readonly.
formField.type = "number";
// @ts-expect-error Immutable form-field descriptions are readonly.
formField.description = null;
// @ts-expect-error Immutable required markers are readonly.
formField.isRequired = false;
// @ts-expect-error Immutable form-field options cannot be replaced.
formField.options = [];
// @ts-expect-error Form-field option collections are readonly.
formField.options.push(option);
// @ts-expect-error Immutable default values are readonly.
formField.defaultValue = null;
// @ts-expect-error Immutable numeric minima are readonly.
formField.minimum = 0;
// @ts-expect-error Immutable numeric maxima are readonly.
formField.maximum = 1;
// @ts-expect-error Immutable string formats are readonly.
formField.format = "uri";
// @ts-expect-error Immutable minimum lengths are readonly.
formField.minimumLength = 1n;
// @ts-expect-error Immutable maximum lengths are readonly.
formField.maximumLength = 2n;
// @ts-expect-error Immutable minimum selections are readonly.
formField.minimumSelections = 1n;
// @ts-expect-error Immutable maximum selections are readonly.
formField.maximumSelections = 2n;
// @ts-expect-error Immutable other-value flags are readonly.
formField.allowsOther = true;
// @ts-expect-error Immutable secret flags are readonly.
formField.isSecret = false;
// @ts-expect-error Form-field validation accepts reviewed form values or null.
formField.accepts({ invalid: true });
// @ts-expect-error Form-value unions exclude unrelated objects.
const invalidFormValue: AgentFormValue = { invalid: true };

const elicitation = new AgentElicitation("request", "server", "conversation", "Choose", [formField]);
// @ts-expect-error Elicitation request IDs are strings.
new AgentElicitation(1, "server", "conversation", "Choose");
// @ts-expect-error Elicitation server names are strings.
new AgentElicitation("request", 1, "conversation", "Choose");
// @ts-expect-error Elicitation conversation IDs are strings.
new AgentElicitation("request", "server", 1, "Choose");
// @ts-expect-error Elicitation messages are strings.
new AgentElicitation("request", "server", "conversation", 1);
// @ts-expect-error Elicitation forms contain canonical fields.
new AgentElicitation("request", "server", "conversation", "Choose", [{}]);
// @ts-expect-error Elicitation URLs are nullable strings.
new AgentElicitation("request", "server", "conversation", "Choose", [], 1);
// @ts-expect-error Elicitation properties are readonly.
elicitation.requestId = "changed";
// @ts-expect-error Elicitation form collections are readonly.
elicitation.form?.push(formField);
// @ts-expect-error Elicitation content values use the reviewed union.
elicitation.validate({ field: { invalid: true } });
// @ts-expect-error Elicitation content values use the reviewed union.
elicitation.accept({ field: { invalid: true } });
// @ts-expect-error Elicitation acceptance requires a canonical response.
elicitation.accepts({ action: "accept", content: {} });

const elicitationResponse = new AgentElicitationResponse("accept", {});
// @ts-expect-error Elicitation actions remain a closed domain.
new AgentElicitationResponse("approve", {});
// @ts-expect-error Elicitation response content uses reviewed values.
new AgentElicitationResponse("accept", { field: { invalid: true } });
// @ts-expect-error Elicitation response actions are readonly.
elicitationResponse.action = "decline";
// @ts-expect-error Elicitation response content is readonly.
elicitationResponse.content.field = textValue;

const pendingApproval = new AgentPendingApproval("approval", "conversation", "Approve?", "Details");
const pendingElicitation = new AgentPendingElicitation(elicitation);
const pendingInteraction: AgentPendingInteraction = pendingApproval;
// @ts-expect-error Pending approval request IDs are strings.
new AgentPendingApproval(1, "conversation", "Approve?", "Details");
// @ts-expect-error Pending approval properties are readonly.
pendingApproval.title = "Changed";
// @ts-expect-error Pending elicitations require canonical elicitation values.
new AgentPendingElicitation({});
// @ts-expect-error Pending elicitation properties are readonly.
pendingElicitation.elicitation = elicitation;
// @ts-expect-error Pending-interaction unions exclude unrelated shapes.
const invalidPendingInteraction: AgentPendingInteraction = { requestId: "request", conversationId: "conversation" };

const interactionState = new AgentInteractionState([pendingInteraction], ["approval"]);
// @ts-expect-error Interaction-state pending values use the reviewed union.
new AgentInteractionState([{}]);
// @ts-expect-error Resolving request IDs are strings.
new AgentInteractionState([], [1]);
// @ts-expect-error Interaction pending collections are readonly.
interactionState.pending.push(pendingApproval);
// @ts-expect-error Resolving-ID collections are readonly.
interactionState.resolvingRequestIds.push("other");
// @ts-expect-error Interaction failures are readonly.
interactionState.failure = null;
// @ts-expect-error pendingFor requires a conversation ID string.
interactionState.pendingFor(1);
// @ts-expect-error isResolving requires a pending interaction.
interactionState.isResolving({});

void invalidPendingInteraction;

const mcpEnvironmentVariable = new AgentMcpEnvironmentVariable("TOKEN", "local");
// @ts-expect-error MCP environment-variable names are strings.
new AgentMcpEnvironmentVariable(1);
// @ts-expect-error MCP environment sources remain a closed typed domain.
new AgentMcpEnvironmentVariable("TOKEN", "workspace");
// @ts-expect-error Immutable MCP environment-variable names are readonly.
mcpEnvironmentVariable.name = "CHANGED";
// @ts-expect-error Immutable MCP environment-variable sources are readonly.
mcpEnvironmentVariable.source = "remote";

const mcpOauthConfiguration = new AgentMcpOauthConfiguration("client", 8080);
// @ts-expect-error MCP OAuth client IDs are nullable strings, not numbers.
new AgentMcpOauthConfiguration(1);
// @ts-expect-error MCP OAuth callback ports are nullable numbers, not strings.
new AgentMcpOauthConfiguration("client", "8080");
// @ts-expect-error Immutable MCP OAuth client IDs are readonly.
mcpOauthConfiguration.clientId = "changed";
// @ts-expect-error Immutable MCP OAuth callback ports are readonly.
mcpOauthConfiguration.callbackPort = 9090;

const mcpToolConfiguration = new AgentMcpToolConfiguration("auto");
// @ts-expect-error MCP tool approvals remain a closed typed domain.
new AgentMcpToolConfiguration("not_an_approval");
// @ts-expect-error MCP tool approvals are strings, not numbers.
new AgentMcpToolConfiguration(1);
// @ts-expect-error Immutable MCP tool configurations are readonly.
mcpToolConfiguration.approval = "prompt";

const stdioTransport = new AgentMcpStdioTransport("node", ["server.js"]);
// @ts-expect-error MCP stdio commands are required.
new AgentMcpStdioTransport();
// @ts-expect-error MCP stdio commands are strings.
new AgentMcpStdioTransport(1);
// @ts-expect-error MCP stdio arguments contain strings.
new AgentMcpStdioTransport("node", [1]);
// @ts-expect-error MCP stdio working directories are nullable strings.
new AgentMcpStdioTransport("node", [], 1);
// @ts-expect-error MCP stdio environment values are strings.
new AgentMcpStdioTransport("node", [], null, { TOKEN: 1 });
// @ts-expect-error Immutable MCP stdio commands are readonly.
stdioTransport.command = "changed";
// @ts-expect-error MCP stdio argument collections are readonly.
stdioTransport.arguments.push("changed");

const httpTransport = new AgentMcpHttpTransport("https://mcp.example.com");
// @ts-expect-error MCP HTTP URLs are required.
new AgentMcpHttpTransport();
// @ts-expect-error MCP HTTP URLs are strings.
new AgentMcpHttpTransport(1);
// @ts-expect-error MCP bearer-token environment variables are nullable strings.
new AgentMcpHttpTransport("https://mcp.example.com", 1);
// @ts-expect-error MCP HTTP header values are strings.
new AgentMcpHttpTransport("https://mcp.example.com", null, { Header: 1 });
// @ts-expect-error MCP HTTP environment-header values are strings.
new AgentMcpHttpTransport("https://mcp.example.com", null, null, { Header: 1 });
// @ts-expect-error MCP HTTP headers helpers are nullable strings.
new AgentMcpHttpTransport("https://mcp.example.com", null, null, null, 1);
// @ts-expect-error Immutable MCP HTTP URLs are readonly.
httpTransport.url = "https://changed.example.com";
// @ts-expect-error MCP HTTP header records are readonly.
if (httpTransport.headers) httpTransport.headers.Header = "changed";

const validMcpTransport: AgentMcpTransport = stdioTransport;
// @ts-expect-error MCP transports use one of the two reviewed concrete shapes.
const invalidMcpTransport: AgentMcpTransport = {};
const mcpServerConfiguration = new AgentMcpServerConfiguration("server", validMcpTransport);
// @ts-expect-error MCP server configurations require a transport.
new AgentMcpServerConfiguration("server");
// @ts-expect-error MCP server names are strings.
new AgentMcpServerConfiguration(1, validMcpTransport);
// @ts-expect-error MCP server transports use the reviewed union.
new AgentMcpServerConfiguration("server", {});
// @ts-expect-error MCP authentication remains a closed typed domain.
new AgentMcpServerConfiguration("server", httpTransport, "api_key");
// @ts-expect-error MCP environment IDs are strings.
new AgentMcpServerConfiguration("server", httpTransport, null, 1);
// @ts-expect-error MCP enablement is boolean.
new AgentMcpServerConfiguration("server", httpTransport, null, "local", "yes");
// @ts-expect-error MCP required status is boolean.
new AgentMcpServerConfiguration("server", httpTransport, null, "local", true, "yes");
// @ts-expect-error MCP parallel-call status is boolean.
new AgentMcpServerConfiguration("server", httpTransport, null, "local", true, false, "yes");
// @ts-expect-error MCP tool-exposure surfaces remain a closed typed domain.
new AgentMcpServerConfiguration("server", httpTransport, null, "local", true, false, false, ["shell"]);
// @ts-expect-error MCP startup timeouts are nullable numbers.
new AgentMcpServerConfiguration("server", httpTransport, null, "local", true, false, false, null, "3");
// @ts-expect-error MCP tool timeouts are nullable numbers.
new AgentMcpServerConfiguration("server", httpTransport, null, "local", true, false, false, null, null, "9");
// @ts-expect-error MCP default tool approvals remain a closed typed domain.
new AgentMcpServerConfiguration("server", httpTransport, null, "local", true, false, false, null, null, null, "always");
// @ts-expect-error MCP enabled-tool collections contain strings.
new AgentMcpServerConfiguration("server", httpTransport, null, "local", true, false, false, null, null, null, null, [1]);
// @ts-expect-error MCP OAuth values use the canonical class.
new AgentMcpServerConfiguration("server", httpTransport, null, "local", true, false, false, null, null, null, null, null, null, null, {});
// @ts-expect-error MCP tool records contain canonical tool configurations.
new AgentMcpServerConfiguration("server", httpTransport, null, "local", true, false, false, null, null, null, null, null, null, null, null, null, { read: "auto" });
// @ts-expect-error Immutable MCP configuration names are readonly.
mcpServerConfiguration.name = "changed";
// @ts-expect-error MCP configuration collections are readonly.
mcpServerConfiguration.enabledTools?.push("changed");
// @ts-expect-error MCP tool records are readonly.
mcpServerConfiguration.tools.read = mcpToolConfiguration;

const mcpServer = new AgentMcpServer("server", "Server", "oauth", mcpServerConfiguration, "user", true);
// @ts-expect-error MCP server auth statuses remain a closed typed domain.
new AgentMcpServer("server", "Server", "authorized");
// @ts-expect-error MCP server configurations use the canonical class.
new AgentMcpServer("server", "Server", "oauth", {});
// @ts-expect-error MCP server origins remain a closed typed domain.
new AgentMcpServer("server", "Server", "oauth", null, "repo");
// @ts-expect-error MCP server removability is boolean.
new AgentMcpServer("server", "Server", "oauth", null, "user", "yes");
// @ts-expect-error Immutable MCP server names are readonly.
mcpServer.name = "changed";
// @ts-expect-error Derived MCP authorization status is readonly.
mcpServer.isAuthorized = false;

const issue = new AgentElicitationValidationIssue("field", "missing_required");
// @ts-expect-error Validation reasons remain a closed typed domain.
new AgentElicitationValidationIssue("field", "not_a_reason");
// @ts-expect-error Immutable validation issues are readonly.
issue.reason = "invalid_type";

const validation = new AgentElicitationValidation([issue]);
// @ts-expect-error Immutable validation results cannot replace their issue collection.
validation.issues = [];
// @ts-expect-error Validation issue collections are readonly.
validation.issues.push(issue);
// @ts-expect-error Nested validation values must have the canonical issue shape.
new AgentElicitationValidation(["missing_required"]);
// @ts-expect-error Derived validity is readonly.
validation.isValid = true;

const planStep = new AgentPlanStep("Ship", "in_progress");
// @ts-expect-error Plan-step statuses remain a closed typed domain.
new AgentPlanStep("Ship", "running");
// @ts-expect-error Plan-step status is required.
new AgentPlanStep("Ship");
// @ts-expect-error Immutable plan-step text is readonly.
planStep.text = "Changed";
// @ts-expect-error Immutable plan-step status is readonly.
planStep.status = "completed";

const planProgress = new AgentPlanProgress(null, [planStep]);
// @ts-expect-error Immutable plan progress cannot replace its explanation.
planProgress.explanation = "Changed";
// @ts-expect-error Immutable plan progress cannot replace its steps.
planProgress.steps = [];
// @ts-expect-error Plan-progress steps are readonly.
planProgress.steps.push(planStep);
// @ts-expect-error Plan-progress explanations are nullable strings, not numbers.
new AgentPlanProgress(1);
// @ts-expect-error Nested plan-progress values must be canonical plan steps.
new AgentPlanProgress(null, ["Ship"]);

const hookActivity = new AgentHookActivity("hook", "SessionStart", "command", "running");
// @ts-expect-error Hook-activity statuses remain a closed typed domain.
new AgentHookActivity("hook", "SessionStart", "command", "waiting");
// @ts-expect-error Hook-activity identifiers are strings.
new AgentHookActivity(1, "SessionStart", "command", "running");
// @ts-expect-error Hook-activity status messages are nullable strings.
new AgentHookActivity("hook", "SessionStart", "command", "running", 1);
// @ts-expect-error Immutable hook-activity statuses are readonly.
hookActivity.status = "completed";
// @ts-expect-error Hook-activity details are readonly.
hookActivity.details.push("changed");

const commandHookHandler: AgentHookHandler = { type: "command", command: "./check", isAsync: false };
const validHookTrustStatus: AgentHookTrustStatus = "untrusted";
// @ts-expect-error Hook handler discriminants remain a closed typed domain.
const unknownHookHandler: AgentHookHandler = { type: "future" };
// @ts-expect-error Command hook handlers require a command.
const missingHookCommand: AgentHookHandler = { type: "command", isAsync: false };
// @ts-expect-error Command hook commands are strings.
const numericHookCommand: AgentHookHandler = { type: "command", command: 1, isAsync: false };
// @ts-expect-error Command hook async flags are booleans.
const stringHookAsync: AgentHookHandler = { type: "command", command: "./check", isAsync: "false" };
// @ts-expect-error MCP-tool hook handlers require a tool name.
const missingHookTool: AgentHookHandler = { type: "mcp_tool", server: "review" };
// @ts-expect-error Prompt handlers have no command payload.
const promptWithCommand: AgentHookHandler = { type: "prompt", command: "./check" };
// @ts-expect-error Immutable handler discriminants are readonly.
commandHookHandler.type = "prompt";

const hook = new AgentHook(
  "review-hook", "sha256:review", true, "preToolUse", commandHookHandler, false,
  "PROJECT", "/workspace/.codex/hooks.json", 10n, validHookTrustStatus,
);
// @ts-expect-error Hook trust statuses remain a closed typed domain.
new AgentHook("hook", "hash", true, "stop", commandHookHandler, false, "USER", "/hooks.json", 10n, "unknown");
// @ts-expect-error Hook timeout values are bigint values.
new AgentHook("hook", "hash", true, "stop", commandHookHandler, false, "USER", "/hooks.json", 10, "trusted");
// @ts-expect-error Hook handlers use the reviewed structural union.
new AgentHook("hook", "hash", true, "stop", {}, false, "USER", "/hooks.json", 10n, "trusted");
// @ts-expect-error Hook origins remain a closed typed domain.
new AgentHook("hook", "hash", true, "stop", commandHookHandler, false, "USER", "/hooks.json", 10n, "trusted", null, null, null, "repo");
// @ts-expect-error Hook uninstallability is boolean.
new AgentHook("hook", "hash", true, "stop", commandHookHandler, false, "USER", "/hooks.json", 10n, "trusted", null, null, null, "user", "yes");
// @ts-expect-error Hook event names are strings.
new AgentHook("hook", "hash", true, 1, commandHookHandler, false, "USER", "/hooks.json", 10n, "trusted");
// @ts-expect-error Immutable hook keys are readonly.
hook.key = "changed";
// @ts-expect-error Immutable hook handlers are readonly.
hook.handler = { type: "prompt" };
// @ts-expect-error Immutable nested handler fields are readonly.
if (hook.handler.type === "command") hook.handler.command = "changed";
// @ts-expect-error Derived hook trustability is readonly.
hook.canTrust = false;

const hookCatalog = new AgentHookCatalog([hook], ["warning"], ["error"]);
// @ts-expect-error Hook catalogs contain canonical hook values.
new AgentHookCatalog(["hook"]);
// @ts-expect-error Hook catalog warnings are strings.
new AgentHookCatalog([hook], [1]);
// @ts-expect-error Hook catalog errors are strings.
new AgentHookCatalog([hook], [], [1]);
// @ts-expect-error Hook catalog hook collections are readonly.
hookCatalog.hooks.push(hook);
// @ts-expect-error Immutable hook catalogs cannot replace warning collections.
hookCatalog.warnings = [];
// @ts-expect-error Hook catalog errors are readonly.
hookCatalog.errors.push("changed");

const connector = new AgentConnector("drive", "Google Drive", "Drive connector", null, true, true, ["Drive"]);
// @ts-expect-error Connector names are required.
new AgentConnector("drive");
// @ts-expect-error Connector IDs are strings.
new AgentConnector(1, "Google Drive");
// @ts-expect-error Defaulted connector descriptions remain non-null strings.
new AgentConnector("drive", "Google Drive", null);
// @ts-expect-error Connector install URLs are nullable strings.
new AgentConnector("drive", "Google Drive", "", 1);
// @ts-expect-error Connector accessibility is boolean.
new AgentConnector("drive", "Google Drive", "", null, "yes");
// @ts-expect-error Connector enablement is boolean.
new AgentConnector("drive", "Google Drive", "", null, true, "yes");
// @ts-expect-error Connector plugin names are strings.
new AgentConnector("drive", "Google Drive", "", null, true, true, [1]);
// @ts-expect-error Immutable connector IDs are readonly.
connector.id = "changed";
// @ts-expect-error Immutable connector plugin-name collections cannot be replaced.
connector.pluginNames = [];
// @ts-expect-error Connector plugin-name collections are readonly.
connector.pluginNames.push("Changed");

const pluginReference = new AgentPluginReference("drive@catalog", "drive", "catalog", null, "remote");
// @ts-expect-error Plugin references require an ID, name, and marketplace.
new AgentPluginReference("drive", "drive");
// @ts-expect-error Plugin reference IDs are strings.
new AgentPluginReference(1, "drive", "catalog");
// @ts-expect-error Plugin marketplace paths are nullable strings.
new AgentPluginReference("drive", "drive", "catalog", 1);
// @ts-expect-error Plugin reference IDs are readonly.
pluginReference.id = "changed";
// @ts-expect-error Derived plugin URIs are readonly.
pluginReference.uri = "plugin://changed@catalog";
const pluginSummary = new AgentPluginSummary(
  pluginReference, "Drive", "Files", true, true, "available", "on_install", true, ["Search"],
);
// @ts-expect-error Plugin summaries require all canonical policy fields.
new AgentPluginSummary(pluginReference, "Drive", "Files", true);
// @ts-expect-error Plugin summaries require canonical references.
new AgentPluginSummary({}, "Drive", "Files", true, true, "available", "on_install", true);
// @ts-expect-error Plugin install policies remain a closed domain.
new AgentPluginSummary(pluginReference, "Drive", "Files", true, true, "AVAILABLE", "on_install", true);
// @ts-expect-error Plugin auth policies remain a closed domain.
new AgentPluginSummary(pluginReference, "Drive", "Files", true, true, "available", "always", true);
// @ts-expect-error Plugin capabilities contain strings.
new AgentPluginSummary(pluginReference, "Drive", "Files", true, true, "available", "on_install", true, [1]);
// @ts-expect-error Plugin summary references are readonly.
pluginSummary.reference = pluginReference;
// @ts-expect-error Plugin capability collections are readonly.
pluginSummary.capabilities.push("Changed");
const pluginCatalog = new AgentPluginCatalog([pluginSummary]);
// @ts-expect-error Plugin catalogs contain canonical summaries.
new AgentPluginCatalog([{}]);
// @ts-expect-error Plugin catalog errors contain strings.
new AgentPluginCatalog([pluginSummary], [1]);
// @ts-expect-error Plugin freshness remains a closed domain.
new AgentPluginCatalog([pluginSummary], [], "cached");
// @ts-expect-error Plugin collections are readonly.
pluginCatalog.plugins.push(pluginSummary);
const pluginSkill = new AgentPluginSkill("search", "Search Drive", true);
// @ts-expect-error Plugin skills require enablement.
new AgentPluginSkill("search", "Search Drive");
// @ts-expect-error Plugin skill enablement is boolean.
new AgentPluginSkill("search", "Search Drive", "yes");
// @ts-expect-error Plugin skill paths are nullable strings.
new AgentPluginSkill("search", "Search Drive", true, 1);
// @ts-expect-error Plugin skill names are readonly.
pluginSkill.name = "changed";
const pluginDetail = new AgentPluginDetail(pluginSummary, "Detail", [pluginSkill], [connector], ["mcp"], 1);
// @ts-expect-error Plugin details require all nested collections and hook count.
new AgentPluginDetail(pluginSummary, "Detail", [], []);
// @ts-expect-error Plugin details contain canonical skills.
new AgentPluginDetail(pluginSummary, "Detail", [{}], [connector], [], 0);
// @ts-expect-error Plugin details contain canonical connectors.
new AgentPluginDetail(pluginSummary, "Detail", [], [{}], [], 0);
// @ts-expect-error Plugin detail MCP server names are strings.
new AgentPluginDetail(pluginSummary, "Detail", [], [], [1], 0);
// @ts-expect-error Plugin hook counts are numbers.
new AgentPluginDetail(pluginSummary, "Detail", [], [], [], "1");
// @ts-expect-error Plugin detail skill collections are readonly.
pluginDetail.skills.push(pluginSkill);
const pluginInstallResult = new AgentPluginInstallResult("on_install", [connector]);
// @ts-expect-error Plugin install results require connector collections.
new AgentPluginInstallResult("on_install");
// @ts-expect-error Plugin install-result policies remain closed.
new AgentPluginInstallResult("always", []);
// @ts-expect-error Plugin install results contain canonical connectors.
new AgentPluginInstallResult("on_install", [{}]);
// @ts-expect-error Plugin install messages are nullable strings.
new AgentPluginInstallResult("on_install", [], 1);
// @ts-expect-error Plugin install connector collections are readonly.
pluginInstallResult.connectorsNeedingAuthentication.push(connector);

const conversationSummary = new AgentConversationSummary("conversation", "Title", 1n);
// @ts-expect-error Conversation-summary timestamps are bigint values, not numbers.
new AgentConversationSummary("conversation", "Title", 1);
// @ts-expect-error Conversation summaries require an updated timestamp.
new AgentConversationSummary("conversation", "Title");
// @ts-expect-error Conversation-summary IDs are strings.
new AgentConversationSummary(1, "Title", 1n);
// @ts-expect-error Conversation-summary titles are strings.
new AgentConversationSummary("conversation", 1, 1n);
// @ts-expect-error Immutable conversation-summary IDs are readonly.
conversationSummary.conversationId = "changed";
// @ts-expect-error Immutable conversation-summary titles are readonly.
conversationSummary.title = "Changed";
// @ts-expect-error Immutable conversation-summary timestamps are readonly.
conversationSummary.updatedAtEpochSeconds = 2n;

const historicalConversation = new AgentConversation(conversationSummary, [message]);
// @ts-expect-error Historical conversations require a message collection.
new AgentConversation(conversationSummary);
// @ts-expect-error Historical conversation summaries use the canonical summary value.
new AgentConversation({}, [message]);
// @ts-expect-error Historical conversation messages use canonical message values.
new AgentConversation(conversationSummary, [{}]);
// @ts-expect-error Immutable historical conversation summaries are readonly.
historicalConversation.summary = conversationSummary;
// @ts-expect-error Immutable historical conversation collections cannot be replaced.
historicalConversation.messages = [];
// @ts-expect-error Historical conversation message collections are readonly.
historicalConversation.messages.push(message);

const serviceTier = new AgentServiceTier("fast", "Fast", "Lowest latency");
// @ts-expect-error Service-tier descriptions are required.
new AgentServiceTier("fast", "Fast");
// @ts-expect-error Service-tier IDs are strings.
new AgentServiceTier(1, "Fast", "Lowest latency");
// @ts-expect-error Immutable service-tier IDs are readonly.
serviceTier.id = "changed";

const model = new AgentModel(
  "model",
  "Model",
  "Description",
  ["medium"],
  "medium",
  true,
  [serviceTier],
  "fast",
);
// @ts-expect-error Model default status is required.
new AgentModel("model", "Model", "Description", ["medium"], "medium");
// @ts-expect-error Model IDs are strings.
new AgentModel(1, "Model", "Description", ["medium"], "medium", true);
// @ts-expect-error Supported model efforts are strings.
new AgentModel("model", "Model", "Description", [1], "medium", true);
// @ts-expect-error Model default status is boolean.
new AgentModel("model", "Model", "Description", ["medium"], "medium", "yes");
// @ts-expect-error Model service tiers must use the canonical value shape.
new AgentModel("model", "Model", "Description", ["medium"], "medium", true, ["fast"]);
// @ts-expect-error Default service-tier IDs are nullable strings.
new AgentModel("model", "Model", "Description", ["medium"], "medium", true, [], 1);
// @ts-expect-error Immutable model IDs are readonly.
model.id = "changed";
// @ts-expect-error Immutable model effort collections cannot be replaced.
model.supportedEfforts = [];
// @ts-expect-error Model effort collections are readonly.
model.supportedEfforts.push("high");
// @ts-expect-error Model service-tier collections are readonly.
model.serviceTiers.push(serviceTier);

const skill = new AgentSkill(
  "review", "Review", "Review changes", "/skills/review/SKILL.md", "user", true,
);
// @ts-expect-error Skill enablement is required.
new AgentSkill("review", "Review", "Review changes", "/skills/review/SKILL.md", "user");
// @ts-expect-error Skill names are strings.
new AgentSkill(1, "Review", "Review changes", "/skills/review/SKILL.md", "user", true);
// @ts-expect-error Skill scopes remain a closed typed domain.
new AgentSkill("review", "Review", "Review changes", "/skills/review/SKILL.md", "workspace", true);
// @ts-expect-error Skill enablement is boolean.
new AgentSkill("review", "Review", "Review changes", "/skills/review/SKILL.md", "user", "yes");
// @ts-expect-error Skill brand colors are nullable strings.
new AgentSkill("review", "Review", "Review changes", "/skills/review/SKILL.md", "user", true, 1);
// @ts-expect-error Skill dependencies are strings.
new AgentSkill("review", "Review", "Review changes", "/skills/review/SKILL.md", "user", true, null, [1]);
// @ts-expect-error Skill uninstallability is boolean.
new AgentSkill("review", "Review", "Review changes", "/skills/review/SKILL.md", "user", true, null, [], "yes");
// @ts-expect-error Skill origins remain a closed typed domain.
new AgentSkill("review", "Review", "Review changes", "/skills/review/SKILL.md", "user", true, null, [], false, "repo");
// @ts-expect-error Immutable skill names are readonly.
skill.name = "changed";
// @ts-expect-error Immutable skill dependency collections cannot be replaced.
skill.dependencies = [];
// @ts-expect-error Skill dependency collections are readonly.
skill.dependencies.push("changed");

const skillCatalog = new AgentSkillCatalog([skill], ["warning"]);
// @ts-expect-error Skill catalogs contain canonical skill values.
new AgentSkillCatalog(["review"]);
// @ts-expect-error Skill catalog errors are strings.
new AgentSkillCatalog([skill], [1]);
// @ts-expect-error Immutable skill catalogs cannot replace their skill collection.
skillCatalog.skills = [];
// @ts-expect-error Skill catalog collections are readonly.
skillCatalog.skills.push(skill);
// @ts-expect-error Skill catalog error collections are readonly.
skillCatalog.errors.push("changed");

const skillChunk = new AgentSkillChunk("content", 7n, 20n);
// @ts-expect-error Skill chunk offsets are bigint values, not numbers.
new AgentSkillChunk("content", 7, 20n);
// @ts-expect-error Skill chunk totals are bigint values, not numbers.
new AgentSkillChunk("content", null, 20);
// @ts-expect-error Skill chunks require a total byte count.
new AgentSkillChunk("content", null);
// @ts-expect-error Immutable skill chunk content is readonly.
skillChunk.content = "changed";
// @ts-expect-error Immutable skill chunk offsets are readonly.
skillChunk.nextOffset = 8n;

declare const skills: CodexSkills;
// @ts-expect-error Skill controllers are created by an Agent.
new CodexSkills();

declare const hooks: CodexHooks;
// @ts-expect-error Hook controllers are created by an Agent.
new CodexHooks();

declare const plugins: CodexPlugins;
// @ts-expect-error Plugin controllers are created by an Agent.
new CodexPlugins();
// @ts-expect-error Plugin feature availability is readonly.
plugins.isAvailable = false;

declare const models: CodexModels;
// @ts-expect-error Model controllers are created by an Agent.
new CodexModels();

declare const connectors: CodexConnectors;
// @ts-expect-error Connector controllers are created by an Agent.
new CodexConnectors();
// @ts-expect-error Connector feature availability is readonly.
connectors.isAvailable = false;

declare const mcpServers: CodexMcpServers;
// @ts-expect-error MCP server controllers are created by an Agent.
new CodexMcpServers();
// @ts-expect-error MCP server feature availability is readonly.
mcpServers.isAvailable = false;

declare const turnProgress: CodexTurnProgress;
// @ts-expect-error Immutable turn progress cannot replace plan progress.
turnProgress.planProgress = null;
// @ts-expect-error Immutable turn progress cannot replace hook activities.
turnProgress.hookActivities = [];
// @ts-expect-error Turn-progress hook activities are readonly.
turnProgress.hookActivities.push(hookActivity);

declare const conversationState: CodexConversationState;
// @ts-expect-error Reconciled conversation snapshots are readonly.
conversationState.conversation = null;
// @ts-expect-error Conversation-state progress is readonly.
conversationState.turnProgress = null;

const turnRequest: AgentTurnRequest = {
  prompt: "review",
  clientMessageId: null,
  model: null,
  effort: null,
  serviceTier: null,
  approvalPreset: "auto_review",
  capabilities: ["web_search"],
  invocations: [skillInvocation, pluginInvocation],
  collaborationMode: "plan",
};
// @ts-expect-error Turn requests require a prompt.
const missingTurnPrompt: AgentTurnRequest = {};
// @ts-expect-error Turn-request prompts are strings.
const numericTurnPrompt: AgentTurnRequest = { prompt: 1 };
// @ts-expect-error Client message IDs are strings when present.
const numericClientMessageId: AgentTurnRequest = { prompt: "review", clientMessageId: 1 };
// @ts-expect-error Model IDs are strings when present.
const numericTurnModel: AgentTurnRequest = { prompt: "review", model: 1 };
// @ts-expect-error Effort IDs are strings when present.
const numericTurnEffort: AgentTurnRequest = { prompt: "review", effort: 1 };
// @ts-expect-error Service-tier IDs are strings when present.
const numericTurnServiceTier: AgentTurnRequest = { prompt: "review", serviceTier: 1 };
// @ts-expect-error Approval presets remain a closed typed domain.
const rawTurnApproval: AgentTurnRequest = { prompt: "review", approvalPreset: "AUTO_REVIEW" };
// @ts-expect-error Capability inputs are readonly arrays, not sets.
const setTurnCapabilities: AgentTurnRequest = { prompt: "review", capabilities: new Set(["web_search"]) };
// @ts-expect-error Capabilities remain a closed typed domain.
const rawTurnCapability: AgentTurnRequest = { prompt: "review", capabilities: ["WEB_SEARCH"] };
// @ts-expect-error Invocation inputs are readonly arrays, not sets.
const setTurnInvocations: AgentTurnRequest = { prompt: "review", invocations: new Set([skillInvocation]) };
// @ts-expect-error Invocation inputs require a projected invocation shape.
const invalidTurnInvocation: AgentTurnRequest = { prompt: "review", invocations: [{}] };
// @ts-expect-error Collaboration modes remain a closed typed domain.
const rawCollaborationMode: AgentTurnRequest = { prompt: "review", collaborationMode: "PLAN" };
// @ts-expect-error Turn-request fields are readonly.
turnRequest.prompt = "changed";
// @ts-expect-error Turn-request capability collections are readonly.
turnRequest.capabilities?.push("web_search");
// @ts-expect-error Turn-request invocation collections are readonly.
turnRequest.invocations?.push(skillInvocation);
declare const typedConversation: CodexConversation;
// @ts-expect-error Structured sends require a turn-request object.
typedConversation.sendRequest("review");
// @ts-expect-error Structured-send signals must be AbortSignal values.
typedConversation.sendRequest(turnRequest, {});

void [
  missingTurnPrompt,
  numericTurnPrompt,
  numericClientMessageId,
  numericTurnModel,
  numericTurnEffort,
  numericTurnServiceTier,
  rawTurnApproval,
  setTurnCapabilities,
  rawTurnCapability,
  setTurnInvocations,
  invalidTurnInvocation,
  rawCollaborationMode,
];

async function rejectInvalidAuthentication(agent: CodexAgent): Promise<void> {
  // @ts-expect-error Connector controllers are owned by the Agent.
  agent.connectors = connectors;
  // @ts-expect-error Connector reload flags are boolean.
  await connectors.list("true");
  // @ts-expect-error Connector list signals must be AbortSignal values.
  await connectors.list(false, {});
  const listedConnectors = await connectors.list();
  // @ts-expect-error Connector list results are readonly.
  listedConnectors.push(connector);
  // @ts-expect-error Model controllers are owned by the Agent.
  agent.models = models;
  // @ts-expect-error Model-list signals must be AbortSignal values.
  await models.list({});
  const listedModels = await models.list();
  // @ts-expect-error Model-list results are readonly.
  listedModels.push(model);
  // @ts-expect-error Model resolution remains a closed typed domain.
  await models.resolve("latest");
  // @ts-expect-error Model-resolution signals must be AbortSignal values.
  await models.resolve("preferred", {});
  // @ts-expect-error Effort resolution requires a canonical model.
  await models.resolveEffort({});
  // @ts-expect-error Effort resolution remains a closed typed domain.
  await models.resolveEffort(model, "latest");
  // @ts-expect-error Effort-resolution signals must be AbortSignal values.
  await models.resolveEffort(model, "preferred", {});
  // @ts-expect-error Service-tier resolution requires a canonical model.
  await models.resolveServiceTier({});
  // @ts-expect-error Service-tier resolution remains a closed typed domain.
  await models.resolveServiceTier(model, "latest");
  // @ts-expect-error Service-tier-resolution signals must be AbortSignal values.
  await models.resolveServiceTier(model, "preferred", {});
  // @ts-expect-error Service-tier resolution may return no tier.
  const resolvedServiceTier: AgentServiceTier = await models.resolveServiceTier(model);
  void resolvedServiceTier;
  // @ts-expect-error Skill controllers are owned by the Agent.
  agent.skills = skills;
  // @ts-expect-error Skill feature availability is readonly.
  skills.isAvailable = false;
  // @ts-expect-error Skill reload flags are boolean.
  await skills.list("true");
  // @ts-expect-error Skill-list signals must be AbortSignal values.
  await skills.list(false, {});
  const listedSkills = await skills.list();
  // @ts-expect-error Listed skill collections are readonly.
  listedSkills.skills.push(skill);
  // @ts-expect-error Skill paths are strings.
  await skills.read(1);
  // @ts-expect-error Skill offsets are bigint values, not numbers.
  await skills.read("/skills/review/SKILL.md", 0);
  // @ts-expect-error Skill-read signals must be AbortSignal values.
  await skills.read("/skills/review/SKILL.md", 0n, {});
  // @ts-expect-error Skill installation directories are strings.
  await skills.install(1, "user");
  // @ts-expect-error Skill installation scopes remain a closed typed domain.
  await skills.install("/skills/review", "repo");
  // @ts-expect-error Skill-install signals must be AbortSignal values.
  await skills.install("/skills/review", "workspace", {});
  // @ts-expect-error Skill uninstallation requires a canonical skill value.
  await skills.uninstall({});
  // @ts-expect-error Skill-uninstall signals must be AbortSignal values.
  await skills.uninstall(skill, {});
  // @ts-expect-error Hook controllers are owned by the Agent.
  agent.hooks = hooks;
  // @ts-expect-error Hook feature availability is readonly.
  hooks.isAvailable = false;
  // @ts-expect-error Hook-list signals must be AbortSignal values.
  await hooks.list({});
  // @ts-expect-error Hook installation directories are strings.
  await hooks.install(1, "user");
  // @ts-expect-error Hook installation scopes remain a closed typed domain.
  await hooks.install("/hooks/review", "repo");
  // @ts-expect-error Hook-install signals must be AbortSignal values.
  await hooks.install("/hooks/review", "workspace", {});
  // @ts-expect-error Hook uninstallation requires a canonical hook value.
  await hooks.uninstall({});
  // @ts-expect-error Hook-uninstall signals must be AbortSignal values.
  await hooks.uninstall(hook, {});
  // @ts-expect-error Hook trust requires a canonical hook value.
  await hooks.trust({});
  // @ts-expect-error Hook-trust signals must be AbortSignal values.
  await hooks.trust(hook, {});
  // @ts-expect-error Plugin controllers are owned by the Agent.
  agent.plugins = plugins;
  // @ts-expect-error Plugin reload flags are boolean.
  await plugins.list("true");
  // @ts-expect-error Plugin-list signals must be AbortSignal values.
  await plugins.list(false, {});
  // @ts-expect-error Plugin reads require canonical references.
  await plugins.read({});
  // @ts-expect-error Plugin-read signals must be AbortSignal values.
  await plugins.read(pluginReference, {});
  // @ts-expect-error Plugin installs require canonical references.
  await plugins.install({});
  // @ts-expect-error Plugin-install signals must be AbortSignal values.
  await plugins.install(pluginReference, {});
  // @ts-expect-error Plugin uninstalls require canonical references.
  await plugins.uninstall({});
  // @ts-expect-error Plugin-uninstall signals must be AbortSignal values.
  await plugins.uninstall(pluginReference, {});
  // @ts-expect-error MCP server controllers are owned by the Agent.
  agent.mcpServers = mcpServers;
  // @ts-expect-error MCP server-list signals must be AbortSignal values.
  await mcpServers.list({});
  const listedMcpServers = await mcpServers.list();
  // @ts-expect-error MCP server-list results are readonly.
  listedMcpServers.push(mcpServer);
  // @ts-expect-error MCP server installation requires canonical configuration.
  await mcpServers.add({});
  // @ts-expect-error MCP server-install signals must be AbortSignal values.
  await mcpServers.add(mcpServerConfiguration, {});
  // @ts-expect-error MCP server removal requires a canonical server.
  await mcpServers.remove({});
  // @ts-expect-error MCP server-remove signals must be AbortSignal values.
  await mcpServers.remove(mcpServer, {});
  const integrationAuthorization = agent.integrationAuthorization;
  // @ts-expect-error Integration authorization controllers are created by an Agent.
  new CodexIntegrationAuthorization();
  // @ts-expect-error Integration authorization controllers are owned by the Agent.
  agent.integrationAuthorization = integrationAuthorization;
  // @ts-expect-error Integration authorization state is readonly.
  integrationAuthorization.state = integrationState;
  // @ts-expect-error Active integration authorization is readonly.
  integrationAuthorization.active = connectorIntegration;
  // @ts-expect-error Integration authorization activity is readonly.
  integrationAuthorization.isAuthorizing = false;
  // @ts-expect-error State observers require state values.
  integrationAuthorization.observeState((value: boolean) => void value);
  // @ts-expect-error Active-target observers require nullable integration values.
  integrationAuthorization.observeActive((value: boolean) => void value);
  // @ts-expect-error Activity observers require booleans.
  integrationAuthorization.observeAuthorizing((value: string) => void value);
  // @ts-expect-error Authorization requires a reviewed integration target.
  await integrationAuthorization.authorize({});
  // @ts-expect-error Authorization signals must be AbortSignal values.
  await integrationAuthorization.authorize(connectorIntegration, {});
  // @ts-expect-error Cancellation signals must be AbortSignal values.
  await integrationAuthorization.cancel({});
  const interactions = agent.interactions;
  // @ts-expect-error Interaction controllers are created by an Agent.
  new CodexInteractions();
  // @ts-expect-error Interaction controllers are owned by the Agent.
  agent.interactions = interactions;
  // @ts-expect-error Interaction state is readonly.
  interactions.state = interactionState;
  // @ts-expect-error Approval snapshots are readonly.
  interactions.approvals.push(pendingApproval);
  // @ts-expect-error Elicitation snapshots are readonly.
  interactions.elicitations.push(pendingElicitation);
  // @ts-expect-error State observers receive interaction states.
  interactions.observeState((value: boolean) => void value);
  // @ts-expect-error Approval observers receive readonly approval arrays.
  interactions.observeApprovals((value: boolean) => void value);
  // @ts-expect-error Elicitation observers receive readonly elicitation arrays.
  interactions.observeElicitations((value: boolean) => void value);
  // @ts-expect-error Approval resolution requires a decision.
  await interactions.resolve(pendingApproval, elicitationResponse);
  // @ts-expect-error Elicitation resolution requires a response.
  await interactions.resolve(pendingElicitation, "accept");
  // @ts-expect-error Resolution signals must be AbortSignal values.
  await interactions.resolve(pendingApproval, "accept", {});
  // @ts-expect-error URL opening requires a pending elicitation.
  await interactions.openUrl(pendingApproval);
  // @ts-expect-error URL-opening signals must be AbortSignal values.
  await interactions.openUrl(pendingElicitation, {});
  // @ts-expect-error Conversation IDs are strings.
  await agent.rename(1, "Renamed conversation");
  // @ts-expect-error Conversation names are strings.
  await agent.rename("conversation", 1);
  // @ts-expect-error Rename requires a conversation name.
  await agent.rename("conversation");
  // @ts-expect-error Rename signals must be AbortSignal values.
  await agent.rename("conversation", "Renamed conversation", {});
  // @ts-expect-error Delete requires a conversation ID.
  await agent.delete();
  // @ts-expect-error Conversation IDs are strings.
  await agent.delete(1);
  // @ts-expect-error Delete signals must be AbortSignal values.
  await agent.delete("conversation", "signal");
  // @ts-expect-error Conversation-list signals must be AbortSignal values.
  await agent.listConversations({});
  const summaries = await agent.listConversations();
  // @ts-expect-error Conversation-list results are readonly.
  summaries.push(conversationSummary);
  // @ts-expect-error Reading a conversation requires an ID.
  await agent.readConversation();
  // @ts-expect-error Conversation IDs are strings.
  await agent.readConversation(1);
  // @ts-expect-error Conversation-read signals must be AbortSignal values.
  await agent.readConversation("conversation", {});
  // @ts-expect-error API-key authentication requires a key.
  await agent.authentication.authenticate("api_key");
  // @ts-expect-error API-key authentication requires a string key.
  await agent.authentication.authenticate("api_key", 42);
  // @ts-expect-error Browser authentication does not accept an API key.
  await agent.authentication.authenticate("chatgpt_browser", "sk-test");
  // @ts-expect-error Device-code authentication does not accept an API key.
  await agent.authentication.authenticate("chatgpt_device_code", "sk-test");
  // @ts-expect-error This expected-error-only getter must not count as positive evidence.
  void agent.workspace.doesNotExist;
}

void rejectInvalidAuthentication;
