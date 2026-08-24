import {
  CodexAgent,
  CodexConversation,
  CodexConversationState,
  CodexError,
  CodexHost,
  CodexHostState,
  CodexObservation,
  createCodexHost,
} from "@codex-agent-labs/codex-agent";
import type {
  CodexApprovalPreset,
  CodexHostStatus,
} from "@codex-agent-labs/codex-agent";

const host: CodexHost = createCodexHost("/bundle", "/data", "typescript", "TypeScript", "test");
const state: CodexHostState = host.state;
const hostStatus: CodexHostStatus = state.status;
const approvalPreset: CodexApprovalPreset = "auto_review";
const observation: CodexObservation = host.observeState((next: CodexHostState): void => {
  const status: string = next.status;
  void status;
});
observation.close();
observation.dispose();
observation[Symbol.dispose]();

async function useAgent(agent: CodexAgent, signal: AbortSignal): Promise<void> {
  const conversation: CodexConversation = await agent.openConversation(
    null,
    approvalPreset,
    null,
    signal,
  );
  const conversationState: CodexConversationState = conversation.state;
  conversation.observeState((next: CodexConversationState): void => void next.status).dispose();
  await conversation.send("hello", signal);
  await conversation.runShellCommand("pwd", signal);
  await conversation.cancelTurn();
  await conversation.reload(signal);
  await conversation.close();
  await conversation.dispose();
  await conversation[Symbol.asyncDispose]();
  void conversationState;
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
void useAgent;
void handleFailure;
void host.start(new AbortController().signal);
void host.selectWorkspace("/workspace");
void host.close();
void host.dispose();
void host[Symbol.asyncDispose]();
