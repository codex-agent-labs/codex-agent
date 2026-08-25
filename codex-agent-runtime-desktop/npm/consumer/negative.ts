import type { CodexAgent } from "@codex-agent-labs/codex-agent";

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
