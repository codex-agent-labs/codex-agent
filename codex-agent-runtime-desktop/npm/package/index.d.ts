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
export type AgentTurnRequest = {
    readonly prompt: string;
    readonly clientMessageId?: Nullable<string>;
    readonly model?: Nullable<string>;
    readonly effort?: Nullable<string>;
    readonly serviceTier?: Nullable<string>;
    readonly approvalPreset?: CodexApprovalPreset;
    readonly capabilities?: ReadonlyArray<AgentCapability>;
    readonly invocations?: ReadonlyArray<AgentInvocation>;
    readonly collaborationMode?: AgentCollaborationMode;
};
export type AgentHookHandler =
    | { readonly type: "agent" }
    | { readonly type: "command"; readonly command: string; readonly isAsync: boolean }
    | { readonly type: "mcp_tool"; readonly server: string; readonly tool: string }
    | { readonly type: "prompt" };
export type AgentMcpTransport = AgentMcpStdioTransport | AgentMcpHttpTransport;
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
export declare class AgentMcpStdioTransport {
    constructor(command: string, arguments?: ReadonlyArray<string>, workingDirectory?: Nullable<string>, environment?: Nullable<Readonly<Record<string, string>>>, forwardedEnvironment?: ReadonlyArray<AgentMcpEnvironmentVariable>);
    get command(): string;
    get arguments(): ReadonlyArray<string>;
    get workingDirectory(): Nullable<string>;
    get environment(): Nullable<Readonly<Record<string, string>>>;
    get forwardedEnvironment(): ReadonlyArray<AgentMcpEnvironmentVariable>;
}
export declare class AgentMcpHttpTransport {
    constructor(url: string, bearerTokenEnvironmentVariable?: Nullable<string>, headers?: Nullable<Readonly<Record<string, string>>>, environmentHeaders?: Nullable<Readonly<Record<string, string>>>, headersHelper?: Nullable<string>);
    get url(): string;
    get bearerTokenEnvironmentVariable(): Nullable<string>;
    get headers(): Nullable<Readonly<Record<string, string>>>;
    get environmentHeaders(): Nullable<Readonly<Record<string, string>>>;
    get headersHelper(): Nullable<string>;
}
export declare class AgentMcpServerConfiguration {
    constructor(name: string, transport: AgentMcpTransport, authentication?: Nullable<AgentMcpAuthentication>, environmentId?: string, isEnabled?: boolean, isRequired?: boolean, supportsParallelToolCalls?: boolean, omitToolsFrom?: Nullable<ReadonlyArray<AgentMcpToolExposureSurface>>, startupTimeoutSeconds?: Nullable<number>, toolTimeoutSeconds?: Nullable<number>, defaultToolApproval?: Nullable<AgentMcpToolApproval>, enabledTools?: Nullable<ReadonlyArray<string>>, disabledTools?: Nullable<ReadonlyArray<string>>, scopes?: Nullable<ReadonlyArray<string>>, oauth?: Nullable<AgentMcpOauthConfiguration>, oauthResource?: Nullable<string>, tools?: Readonly<Record<string, AgentMcpToolConfiguration>>);
    get name(): string;
    get transport(): AgentMcpTransport;
    get authentication(): Nullable<AgentMcpAuthentication>;
    get environmentId(): string;
    get isEnabled(): boolean;
    get isRequired(): boolean;
    get supportsParallelToolCalls(): boolean;
    get omitToolsFrom(): Nullable<ReadonlyArray<AgentMcpToolExposureSurface>>;
    get startupTimeoutSeconds(): Nullable<number>;
    get toolTimeoutSeconds(): Nullable<number>;
    get defaultToolApproval(): Nullable<AgentMcpToolApproval>;
    get enabledTools(): Nullable<ReadonlyArray<string>>;
    get disabledTools(): Nullable<ReadonlyArray<string>>;
    get scopes(): Nullable<ReadonlyArray<string>>;
    get oauth(): Nullable<AgentMcpOauthConfiguration>;
    get oauthResource(): Nullable<string>;
    get tools(): Readonly<Record<string, AgentMcpToolConfiguration>>;
}
export declare class AgentMcpServer {
    constructor(name: string, displayName: string, authStatus: AgentMcpAuthStatus, configuration?: Nullable<AgentMcpServerConfiguration>, origin?: AgentResourceOrigin, canRemove?: boolean);
    get name(): string;
    get displayName(): string;
    get authStatus(): AgentMcpAuthStatus;
    get configuration(): Nullable<AgentMcpServerConfiguration>;
    get origin(): AgentResourceOrigin;
    get canRemove(): boolean;
    get isAuthorized(): boolean;
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
export declare class AgentHook {
    constructor(key: string, currentHash: string, isEnabled: boolean, eventName: string, handler: AgentHookHandler, isManaged: boolean, source: string, sourcePath: string, timeoutSeconds: bigint, trustStatus: AgentHookTrustStatus, matcher?: Nullable<string>, pluginId?: Nullable<string>, statusMessage?: Nullable<string>, origin?: AgentResourceOrigin, canUninstall?: boolean);
    get key(): string;
    get currentHash(): string;
    get isEnabled(): boolean;
    get eventName(): string;
    get handler(): AgentHookHandler;
    get isManaged(): boolean;
    get source(): string;
    get sourcePath(): string;
    get timeoutSeconds(): bigint;
    get trustStatus(): AgentHookTrustStatus;
    get matcher(): Nullable<string>;
    get pluginId(): Nullable<string>;
    get statusMessage(): Nullable<string>;
    get origin(): AgentResourceOrigin;
    get canUninstall(): boolean;
    get canTrust(): boolean;
}
export declare class AgentHookCatalog {
    constructor(hooks: ReadonlyArray<AgentHook>, warnings?: ReadonlyArray<string>, errors?: ReadonlyArray<string>);
    get hooks(): ReadonlyArray<AgentHook>;
    get warnings(): ReadonlyArray<string>;
    get errors(): ReadonlyArray<string>;
}
export declare class AgentConnector {
    constructor(id: string, name: string, description?: string, installUrl?: Nullable<string>, isAccessible?: boolean, isEnabled?: boolean, pluginNames?: ReadonlyArray<string>);
    get id(): string;
    get name(): string;
    get description(): string;
    get installUrl(): Nullable<string>;
    get isAccessible(): boolean;
    get isEnabled(): boolean;
    get pluginNames(): ReadonlyArray<string>;
}
export type AgentIntegration = AgentConnectorIntegration | AgentMcpServerIntegration;
export declare class AgentConnectorIntegration {
    constructor(connector: AgentConnector);
    get connector(): AgentConnector;
    get id(): string;
    get displayName(): string;
}
export declare class AgentMcpServerIntegration {
    constructor(server: AgentMcpServer);
    get server(): AgentMcpServer;
    get id(): string;
    get displayName(): string;
}
export type AgentInvocation = AgentPluginInvocation | AgentSkillInvocation;
export declare class AgentSkillInvocation {
    constructor(name: string, path: string);
    get name(): string;
    get path(): string;
    get key(): string;
}
export declare class AgentPluginInvocation {
    constructor(name: string, uri: string);
    get name(): string;
    get uri(): string;
    get key(): string;
}
export declare class AgentServiceTier {
    constructor(id: string, name: string, description: string);
    get id(): string;
    get name(): string;
    get description(): string;
}
export declare class AgentModel {
    constructor(id: string, displayName: string, description: string, supportedEfforts: ReadonlyArray<string>, defaultEffort: string, isDefault: boolean, serviceTiers?: ReadonlyArray<AgentServiceTier>, defaultServiceTier?: Nullable<string>);
    get id(): string;
    get displayName(): string;
    get description(): string;
    get supportedEfforts(): ReadonlyArray<string>;
    get defaultEffort(): string;
    get isDefault(): boolean;
    get serviceTiers(): ReadonlyArray<AgentServiceTier>;
    get defaultServiceTier(): Nullable<string>;
}
export declare class AgentSkill {
    constructor(name: string, displayName: string, description: string, path: string, scope: AgentSkillScope, isEnabled: boolean, brandColor?: Nullable<string>, dependencies?: ReadonlyArray<string>, canUninstall?: boolean, origin?: AgentResourceOrigin);
    get name(): string;
    get displayName(): string;
    get description(): string;
    get path(): string;
    get scope(): AgentSkillScope;
    get isEnabled(): boolean;
    get brandColor(): Nullable<string>;
    get dependencies(): ReadonlyArray<string>;
    get canUninstall(): boolean;
    get origin(): AgentResourceOrigin;
}
export declare class AgentSkillCatalog {
    constructor(skills: ReadonlyArray<AgentSkill>, errors?: ReadonlyArray<string>);
    get skills(): ReadonlyArray<AgentSkill>;
    get errors(): ReadonlyArray<string>;
}
export declare class AgentSkillChunk {
    constructor(content: string, nextOffset: Nullable<bigint>, totalBytes: bigint);
    get content(): string;
    get nextOffset(): Nullable<bigint>;
    get totalBytes(): bigint;
}
export declare class AgentConversationSummary {
    constructor(conversationId: string, title: string, updatedAtEpochSeconds: bigint);
    get conversationId(): string;
    get title(): string;
    get updatedAtEpochSeconds(): bigint;
}
export declare class AgentConversation {
    constructor(summary: AgentConversationSummary, messages: ReadonlyArray<CodexMessage>);
    get summary(): AgentConversationSummary;
    get messages(): ReadonlyArray<CodexMessage>;
}
export declare class CodexAuthorizationUrl {
    private constructor();
    get value(): string;
    get purpose(): CodexAuthorizationPurpose;
    static chatGpt(value: string): CodexAuthorizationUrl;
    static external(value: string): CodexAuthorizationUrl;
}
export declare class CodexFailure {
    private constructor();
    get code(): string;
    get message(): string;
    get recoverable(): boolean;
}
export declare class AgentIntegrationAuthorizationState {
    constructor(status?: AgentIntegrationAuthorizationStatus, target?: Nullable<AgentIntegration>, failure?: Nullable<CodexFailure>);
    get status(): AgentIntegrationAuthorizationStatus;
    get target(): Nullable<AgentIntegration>;
    get failure(): Nullable<CodexFailure>;
}
export declare class CodexAuthenticationState {
    private constructor();
    get status(): CodexAuthenticationStatus;
    get pendingSignInUrl(): Nullable<CodexAuthorizationUrl>;
    get deviceVerificationUrl(): Nullable<CodexAuthorizationUrl>;
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
    get collaborationMode(): AgentCollaborationMode;
    get reasoning(): Nullable<string>;
    get plan(): Nullable<string>;
    get shellCommand(): Nullable<string>;
    get exitCode(): Nullable<number>;
    get capabilities(): ReadonlyArray<AgentCapability>;
    get invocations(): ReadonlyArray<AgentInvocation>;
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
    get conversation(): Nullable<AgentConversation>;
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
export declare function codexApprovalPresetDisplayName(preset: CodexApprovalPreset): string;
export declare function agentSkillScopeDisplayName(scope: AgentSkillScope): string;
export declare function agentCapabilityId(capability: AgentCapability): string;
export declare function agentCapabilityDisplayLabel(capability: AgentCapability): string;
export declare function agentCapabilityIcon(capability: AgentCapability): Nullable<string>;
export declare function agentCapabilityPromptLabel(capability: AgentCapability): string;
export declare class CodexAgent {
    private constructor();
    get workspace(): CodexWorkspace;
    get authentication(): CodexAuthentication;
    get connectors(): CodexConnectors;
    get models(): CodexModels;
    get skills(): CodexSkills;
    get hooks(): CodexHooks;
    get mcpServers(): CodexMcpServers;
    get integrationAuthorization(): CodexIntegrationAuthorization;
    get activeConversation(): Nullable<CodexConversation>;
    listConversations(signal?: Nullable<AbortSignal>): Promise<ReadonlyArray<AgentConversationSummary>>;
    readConversation(conversationId: string, signal?: Nullable<AbortSignal>): Promise<AgentConversation>;
    openConversation(conversationId?: Nullable<string>, approvalPreset?: Nullable<CodexApprovalPreset>, serviceTier?: Nullable<string>, signal?: Nullable<AbortSignal>): Promise<CodexConversation>;
    rename(conversationId: string, name: string, signal?: Nullable<AbortSignal>): Promise<void>;
    delete(conversationId: string, signal?: Nullable<AbortSignal>): Promise<void>;
    observeActiveConversation(listener: (conversation: Nullable<CodexConversation>) => void): CodexObservation;
}
export declare class CodexConnectors {
    private constructor();
    get isAvailable(): boolean;
    list(forceReload?: boolean, signal?: Nullable<AbortSignal>): Promise<ReadonlyArray<AgentConnector>>;
}
export declare class CodexModels {
    private constructor();
    list(signal?: Nullable<AbortSignal>): Promise<ReadonlyArray<AgentModel>>;
    resolve(resolution?: AgentResolution, signal?: Nullable<AbortSignal>): Promise<AgentModel>;
    resolveEffort(model: AgentModel, resolution?: AgentResolution, signal?: Nullable<AbortSignal>): Promise<string>;
    resolveServiceTier(model: AgentModel, resolution?: AgentResolution, signal?: Nullable<AbortSignal>): Promise<Nullable<AgentServiceTier>>;
}
export declare class CodexSkills {
    private constructor();
    get isAvailable(): boolean;
    list(forceReload?: boolean, signal?: Nullable<AbortSignal>): Promise<AgentSkillCatalog>;
    read(path: string, offset?: bigint, signal?: Nullable<AbortSignal>): Promise<AgentSkillChunk>;
    install(directory: string, scope: AgentInstallationScope, signal?: Nullable<AbortSignal>): Promise<AgentSkill>;
    uninstall(skill: AgentSkill, signal?: Nullable<AbortSignal>): Promise<void>;
}
export declare class CodexHooks {
    private constructor();
    get isAvailable(): boolean;
    list(signal?: Nullable<AbortSignal>): Promise<AgentHookCatalog>;
    install(directory: string, scope: AgentInstallationScope, signal?: Nullable<AbortSignal>): Promise<AgentHook>;
    uninstall(hook: AgentHook, signal?: Nullable<AbortSignal>): Promise<void>;
    trust(hook: AgentHook, signal?: Nullable<AbortSignal>): Promise<void>;
}
export declare class CodexMcpServers {
    private constructor();
    get isAvailable(): boolean;
    list(signal?: Nullable<AbortSignal>): Promise<ReadonlyArray<AgentMcpServer>>;
    add(configuration: AgentMcpServerConfiguration, signal?: Nullable<AbortSignal>): Promise<AgentMcpServer>;
    remove(server: AgentMcpServer, signal?: Nullable<AbortSignal>): Promise<void>;
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
export declare class CodexIntegrationAuthorization {
    private constructor();
    get state(): AgentIntegrationAuthorizationState;
    get active(): Nullable<AgentIntegration>;
    get isAuthorizing(): boolean;
    authorize(target: AgentIntegration, signal?: Nullable<AbortSignal>): Promise<void>;
    cancel(signal?: Nullable<AbortSignal>): Promise<void>;
    observeState(listener: (state: AgentIntegrationAuthorizationState) => void): CodexObservation;
    observeActive(listener: (target: Nullable<AgentIntegration>) => void): CodexObservation;
    observeAuthorizing(listener: (isAuthorizing: boolean) => void): CodexObservation;
}
export declare class CodexConversation {
    private constructor();
    get state(): CodexConversationState;
    send(prompt: string, signal?: Nullable<AbortSignal>): Promise<void>;
    sendRequest(request: AgentTurnRequest, signal?: Nullable<AbortSignal>): Promise<void>;
    runShellCommand(command: string, signal?: Nullable<AbortSignal>): Promise<void>;
    cancelTurn(): Promise<void>;
    reload(signal?: Nullable<AbortSignal>): Promise<void>;
    observeState(listener: (state: CodexConversationState) => void): CodexObservation;
    close(): Promise<void>;
    dispose(): Promise<void>;
    [Symbol.asyncDispose](): Promise<void>;
}
