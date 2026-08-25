import {
  AgentConnector,
  AgentConversationSummary,
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
  AgentModel,
  AgentPlanProgress,
  AgentPlanStep,
  AgentServiceTier,
  AgentSkill,
  AgentSkillCatalog,
  AgentSkillChunk,
  CodexConnectors,
  CodexModels,
  CodexSkills,
  agentSkillScopeDisplayName,
  codexApprovalPresetDisplayName,
} from "@codex-agent-labs/codex-agent";
import type { CodexAgent, CodexTurnProgress } from "@codex-agent-labs/codex-agent";

// @ts-expect-error Raw Kotlin enum names are outside the public TypeScript domain.
codexApprovalPresetDisplayName("AUTO_REVIEW");
// @ts-expect-error Raw Kotlin enum names are outside the public TypeScript domain.
agentSkillScopeDisplayName("SYSTEM");

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

declare const models: CodexModels;
// @ts-expect-error Model controllers are created by an Agent.
new CodexModels();

declare const connectors: CodexConnectors;
// @ts-expect-error Connector controllers are created by an Agent.
new CodexConnectors();
// @ts-expect-error Connector feature availability is readonly.
connectors.isAvailable = false;

declare const turnProgress: CodexTurnProgress;
// @ts-expect-error Immutable turn progress cannot replace plan progress.
turnProgress.planProgress = null;
// @ts-expect-error Immutable turn progress cannot replace hook activities.
turnProgress.hookActivities = [];
// @ts-expect-error Turn-progress hook activities are readonly.
turnProgress.hookActivities.push(hookActivity);

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
