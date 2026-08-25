import {
  AgentElicitationValidation,
  AgentElicitationValidationIssue,
  AgentFormBooleanValue,
  AgentFormNumberValue,
  AgentFormOption,
  AgentFormTextListValue,
  AgentFormTextValue,
  AgentPlanProgress,
  AgentPlanStep,
} from "@codex-agent-labs/codex-agent";
import type { CodexAgent } from "@codex-agent-labs/codex-agent";

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

async function rejectInvalidAuthentication(agent: CodexAgent): Promise<void> {
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
