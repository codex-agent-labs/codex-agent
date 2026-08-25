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
  codexApprovalPresetDisplayName,
} from "@codex-agent-labs/codex-agent";
import type { CodexAgent, CodexTurnProgress } from "@codex-agent-labs/codex-agent";

// @ts-expect-error Raw Kotlin enum names are outside the public TypeScript domain.
codexApprovalPresetDisplayName("AUTO_REVIEW");

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

declare const turnProgress: CodexTurnProgress;
// @ts-expect-error Immutable turn progress cannot replace plan progress.
turnProgress.planProgress = null;
// @ts-expect-error Immutable turn progress cannot replace hook activities.
turnProgress.hookActivities = [];
// @ts-expect-error Turn-progress hook activities are readonly.
turnProgress.hookActivities.push(hookActivity);

async function rejectInvalidAuthentication(agent: CodexAgent): Promise<void> {
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
  // @ts-expect-error API-key authentication requires a key.
  await agent.authentication.authenticate("api_key");
  // @ts-expect-error Browser authentication does not accept an API key.
  await agent.authentication.authenticate("chatgpt_browser", "sk-test");
  // @ts-expect-error Device-code authentication does not accept an API key.
  await agent.authentication.authenticate("chatgpt_device_code", "sk-test");
  // @ts-expect-error This expected-error-only getter must not count as positive evidence.
  void agent.workspace.doesNotExist;
}

void rejectInvalidAuthentication;
