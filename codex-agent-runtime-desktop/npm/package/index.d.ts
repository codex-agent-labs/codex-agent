type Nullable<T> = T | null | undefined;
export type CodexHostStatus = "new" | "restoring" | "workspace_required" | "preparing" | "ready" | "failed" | "closed";
export type CodexWorkspaceSelectionReason = "not_selected" | "not_found" | "access_revoked" | "invalid_selection";
export type CodexMessageRole = "user" | "assistant";
export type CodexWorkActivity = "running_command" | "writing_files";
export type CodexConversationStatus = "new" | "opening" | "ready" | "starting_turn" | "running_turn" | "cancelling_turn" | "reloading" | "failed" | "closed";
export type CodexApprovalPreset = "auto_review" | "never" | "ask_me" | "strict";
export declare class CodexFailure {
    private constructor();
    get code(): string;
    get message(): string;
    get recoverable(): boolean;
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
    get shellOutput(): string;
    get shellExitCode(): Nullable<number>;
    get workActivity(): Nullable<CodexWorkActivity>;
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
    get activeConversation(): Nullable<CodexConversation>;
    openConversation(conversationId?: Nullable<string>, approvalPreset?: Nullable<CodexApprovalPreset>, serviceTier?: Nullable<string>, signal?: Nullable<AbortSignal>): Promise<CodexConversation>;
    observeActiveConversation(listener: (conversation: Nullable<CodexConversation>) => void): CodexObservation;
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
