import {
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
  CodexApprovalPreset,
  CodexAuthenticationMethod,
  CodexAuthenticationStatus,
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
  // @ts-expect-error API-key authentication requires a key.
  await authentication.authenticate("api_key");
  // @ts-expect-error Browser authentication does not accept an API key.
  await authentication.authenticate("chatgpt_browser", "sk-test", signal);
  // @ts-expect-error Device-code authentication does not accept an API key.
  await authentication.authenticate("chatgpt_device_code", "sk-test", signal);
  await authentication.cancel(signal);
  await authentication.signOut(signal);
  const conversation: CodexConversation = await agent.openConversation(
    null,
    approvalPreset,
    null,
    signal,
  );
  const conversationState: CodexConversationState = conversation.state;
  const isTurnActive: boolean = conversationState.isTurnActive;
  conversation.observeState((next: CodexConversationState): void => void next.status).dispose();
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
    conversationState,
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
void useAgent;
void handleFailure;
void host.start(new AbortController().signal);
void host.selectWorkspace("/workspace");
void host.close();
void host.dispose();
void host[Symbol.asyncDispose]();
