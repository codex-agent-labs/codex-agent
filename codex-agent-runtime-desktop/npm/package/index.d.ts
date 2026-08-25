type Nullable<T> = T | null | undefined;
export type CodexHostStatus = "new" | "restoring" | "workspace_required" | "preparing" | "ready" | "failed" | "closed";
export type AgentApprovalDecision = "accept" | "decline";
export type AgentCapability = "web_search";
export type AgentCatalogFreshness = "fresh_cache" | "live" | "stale_cache";
export type AgentCollaborationMode = "default" | "plan";
export type AgentElicitationAction = "accept" | "cancel" | "decline";
export type AgentElicitationValidationReason = "above_maximum" | "below_minimum" | "duplicate_selection" | "invalid_format" | "invalid_selection" | "invalid_type" | "missing_required" | "non_finite_number" | "non_integer" | "unknown_field";
export type AgentFormFieldType = "boolean" | "integer" | "multi_select" | "number" | "single_select" | "string";
export type AgentFormStringFormat = "date" | "date_time" | "email" | "uri";
export type AgentHookRunStatus = "blocked" | "completed" | "failed" | "running" | "stopped";
export type AgentHookTrustStatus = "managed" | "modified" | "trusted" | "untrusted";
export type AgentInstallationScope = "user" | "workspace";
export type AgentIntegrationAuthorizationStatus = "authorized" | "awaiting_completion" | "failed" | "idle" | "starting";
export type AgentMcpAuthStatus = "bearer_token" | "not_logged_in" | "oauth" | "unknown" | "unsupported";
export type AgentMcpAuthentication = "chat_gpt" | "oauth";
export type AgentMcpEnvironmentSource = "local" | "remote";
export type AgentMcpToolApproval = "approve" | "auto" | "prompt" | "writes";
export type AgentMcpToolExposureSurface = "code_mode" | "deferred" | "direct";
export type AgentPlanStepStatus = "completed" | "in_progress" | "pending";
export type AgentPluginAuthPolicy = "on_install" | "on_use";
export type AgentPluginInstallPolicy = "available" | "installed_by_default" | "not_available";
export type AgentResolution = "default" | "first" | "preferred";
export type AgentResourceOrigin = "managed" | "plugin" | "unknown" | "user" | "workspace";
export type AgentSkillScope = "admin" | "plugin" | "repo" | "system" | "user";
export type CodexApprovalPreset = "ask_me" | "auto_review" | "never" | "strict";
export type CodexAuthenticationStatus = "authenticated" | "authenticating" | "signed_out";
export type CodexAuthorizationPurpose = "chat_gpt" | "external";
export type CodexConversationStatus = "cancelling_turn" | "closed" | "failed" | "new" | "opening" | "ready" | "reloading" | "running_turn" | "starting_turn";
export type CodexMessageRole = "assistant" | "user";
export type CodexWorkActivity = "running_command" | "writing_files";
export type CodexWorkspaceSelectionReason = "access_revoked" | "invalid_selection" | "not_found" | "not_selected";
export type CodexAuthenticationMethod = "chatgpt_browser" | "chatgpt_device_code" | "api_key";
export declare class AgentFormOption {
    constructor(value: string, title?: string, description?: Nullable<string>);
    get value(): string;
    get title(): string;
    get description(): Nullable<string>;
}
export declare class AgentFormTextValue {
    constructor(value: string);
    get value(): string;
}
export declare class AgentFormNumberValue {
    constructor(value: number);
    get value(): number;
}
export declare class AgentFormBooleanValue {
    constructor(value: boolean);
    get value(): boolean;
}
export declare class AgentFormTextListValue {
    constructor(value: ReadonlyArray<string>);
    get value(): ReadonlyArray<string>;
}
export declare class AgentMcpEnvironmentVariable {
    constructor(name: string, source?: Nullable<AgentMcpEnvironmentSource>);
    get name(): string;
    get source(): Nullable<AgentMcpEnvironmentSource>;
}
export declare class AgentMcpOauthConfiguration {
    constructor(clientId?: Nullable<string>, callbackPort?: Nullable<number>);
    get clientId(): Nullable<string>;
    get callbackPort(): Nullable<number>;
}
export declare class AgentMcpToolConfiguration {
    constructor(approval?: Nullable<AgentMcpToolApproval>);
    get approval(): Nullable<AgentMcpToolApproval>;
}
export declare class AgentElicitationValidationIssue {
    constructor(fieldName: string, reason: AgentElicitationValidationReason);
    get fieldName(): string;
    get reason(): AgentElicitationValidationReason;
}
export declare class AgentElicitationValidation {
    constructor(issues: ReadonlyArray<AgentElicitationValidationIssue>);
    get issues(): ReadonlyArray<AgentElicitationValidationIssue>;
    get isValid(): boolean;
}
export declare class AgentPlanStep {
    constructor(text: string, status: AgentPlanStepStatus);
    get text(): string;
    get status(): AgentPlanStepStatus;
}
export declare class AgentPlanProgress {
    constructor(explanation?: Nullable<string>, steps?: ReadonlyArray<AgentPlanStep>);
    get explanation(): Nullable<string>;
    get steps(): ReadonlyArray<AgentPlanStep>;
}
export declare class AgentHookActivity {
    constructor(id: string, eventName: string, handlerType: string, status: AgentHookRunStatus, statusMessage?: Nullable<string>, details?: ReadonlyArray<string>);
    get id(): string;
    get eventName(): string;
    get handlerType(): string;
    get status(): AgentHookRunStatus;
    get statusMessage(): Nullable<string>;
    get details(): ReadonlyArray<string>;
}
export declare class CodexFailure {
    private constructor();
    get code(): string;
    get message(): string;
    get recoverable(): boolean;
}
export declare class CodexAuthenticationState {
    private constructor();
    get status(): CodexAuthenticationStatus;
    get pendingSignInUrl(): Nullable<string>;
    get deviceVerificationUrl(): Nullable<string>;
    get deviceUserCode(): Nullable<string>;
    get failure(): Nullable<CodexFailure>;
}
export declare class CodexError extends Error {
    private constructor();
    get code(): string;
    get recoverable(): boolean;
    readonly cause?: unknown;
}
export declare class CodexWorkspace {
    private constructor();
    get path(): string;
    get displayName(): string;
}
export declare class CodexHostState {
    private constructor();
    get status(): CodexHostStatus;
    get workspace(): Nullable<CodexWorkspace>;
    get agent(): Nullable<CodexAgent>;
    get selectionReason(): Nullable<CodexWorkspaceSelectionReason>;
    get selectionMessage(): Nullable<string>;
    get failure(): Nullable<CodexFailure>;
}
export declare class CodexMessage {
    private constructor();
    get id(): string;
    get clientMessageId(): Nullable<string>;
    get role(): CodexMessageRole;
    get text(): string;
    get reasoning(): Nullable<string>;
    get plan(): Nullable<string>;
    get shellCommand(): Nullable<string>;
    get exitCode(): Nullable<number>;
}
export declare class CodexTurnProgress {
    private constructor();
    get text(): string;
    get commentary(): string;
    get reasoning(): string;
    get plan(): string;
    get planProgress(): Nullable<AgentPlanProgress>;
    get shellOutput(): string;
    get shellExitCode(): Nullable<number>;
    get workActivity(): Nullable<CodexWorkActivity>;
    get hookActivities(): ReadonlyArray<AgentHookActivity>;
    get truncated(): boolean;
}
export declare class CodexConversationState {
    private constructor();
    get status(): CodexConversationStatus;
    get conversationId(): Nullable<string>;
    get title(): Nullable<string>;
    get messages(): ReadonlyArray<CodexMessage>;
    get turnProgress(): Nullable<CodexTurnProgress>;
    get model(): Nullable<string>;
    get effort(): Nullable<string>;
    get serviceTier(): Nullable<string>;
    get failure(): Nullable<CodexFailure>;
    get isTurnActive(): boolean;
    get canStartTurn(): boolean;
    get canReload(): boolean;
    get canCancelTurn(): boolean;
    get canRunShellCommand(): boolean;
}
export declare class CodexObservation {
    private constructor();
    get isClosed(): boolean;
    close(): void;
    dispose(): void;
    [Symbol.dispose](): void;
}
export declare class CodexHost {
    private constructor();
    get state(): CodexHostState;
    get agent(): Nullable<CodexAgent>;
    start(signal?: Nullable<AbortSignal>): Promise<void>;
    selectWorkspace(path: string, signal?: Nullable<AbortSignal>): Promise<void>;
    observeState(listener: (state: CodexHostState) => void): CodexObservation;
    close(): Promise<void>;
    dispose(): Promise<void>;
    [Symbol.asyncDispose](): Promise<void>;
}
export declare function createCodexHost(bundleDirectory: string, dataDirectory: string, clientName: string, clientTitle: string, clientVersion: string): CodexHost;
export declare class CodexAgent {
    private constructor();
    get workspace(): CodexWorkspace;
    get authentication(): CodexAuthentication;
    get activeConversation(): Nullable<CodexConversation>;
    openConversation(conversationId?: Nullable<string>, approvalPreset?: Nullable<CodexApprovalPreset>, serviceTier?: Nullable<string>, signal?: Nullable<AbortSignal>): Promise<CodexConversation>;
    rename(conversationId: string, name: string, signal?: Nullable<AbortSignal>): Promise<void>;
    delete(conversationId: string, signal?: Nullable<AbortSignal>): Promise<void>;
    observeActiveConversation(listener: (conversation: Nullable<CodexConversation>) => void): CodexObservation;
}
export declare class CodexAuthentication {
    private constructor();
    get state(): CodexAuthenticationState;
    get isAuthenticated(): boolean;
    get isAuthenticating(): boolean;
    authenticate(method?: Nullable<"chatgpt_browser">, apiKey?: null, signal?: Nullable<AbortSignal>): Promise<void>;
    authenticate(method: "chatgpt_device_code", apiKey?: null, signal?: Nullable<AbortSignal>): Promise<void>;
    authenticate(method: "api_key", apiKey: string, signal?: Nullable<AbortSignal>): Promise<void>;
    cancel(signal?: Nullable<AbortSignal>): Promise<void>;
    signOut(signal?: Nullable<AbortSignal>): Promise<void>;
    observeState(listener: (state: CodexAuthenticationState) => void): CodexObservation;
    observeAuthenticated(listener: (isAuthenticated: boolean) => void): CodexObservation;
    observeAuthenticating(listener: (isAuthenticating: boolean) => void): CodexObservation;
}
export declare class CodexConversation {
    private constructor();
    get state(): CodexConversationState;
    send(prompt: string, signal?: Nullable<AbortSignal>): Promise<void>;
    runShellCommand(command: string, signal?: Nullable<AbortSignal>): Promise<void>;
    cancelTurn(): Promise<void>;
    reload(signal?: Nullable<AbortSignal>): Promise<void>;
    observeState(listener: (state: CodexConversationState) => void): CodexObservation;
    close(): Promise<void>;
    dispose(): Promise<void>;
    [Symbol.asyncDispose](): Promise<void>;
}
