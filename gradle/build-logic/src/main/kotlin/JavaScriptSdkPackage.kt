import java.io.File
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.Files
import java.nio.file.LinkOption.NOFOLLOW_LINKS
import java.nio.file.StandardCopyOption.REPLACE_EXISTING
import java.nio.file.StandardOpenOption.CREATE_NEW
import java.util.Date
import java.util.zip.GZIPOutputStream
import org.apache.commons.compress.archivers.tar.TarArchiveEntry
import org.apache.commons.compress.archivers.tar.TarArchiveOutputStream
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

/** The same reviewed transformation is used by Gradle and the fixed standalone producer. */
internal fun verifyJavaScriptDeclarationGolden(
    rawCompilerDeclaration: File, reviewedGoldenDeclaration: File,
    generatedEnumDeclarations: File, output: File,
) {
        val raw = rawCompilerDeclaration.readText().replace("\r\n", "\n")
        val lines = raw.lines()
        val sanitized = mutableListOf<String>()
        var index = 0
        while (index < lines.size) {
            val line = lines[index]
            when {
                line.startsWith("declare function KtSingleton") ||
                    line.startsWith("export as namespace ") -> index += 1
                line.startsWith("export declare namespace ") -> {
                    val block = mutableListOf<String>()
                    var depth = 0
                    do {
                        val blockLine = lines[index++]
                        block += blockLine
                        depth += blockLine.count { it == '{' } - blockLine.count { it == '}' }
                    } while (depth > 0 && index < lines.size)
                    check(block.any { "\$metadata\$" in it }) {
                        "Unexpected non-metadata TypeScript namespace: ${block.first()}"
                    }
                }
                else -> {
                    sanitized += line.replace("extends /* kotlin.Exception */ Error", "extends Error")
                    index += 1
                }
            }
        }
        val canonicalEnumDeclarations =
            generatedEnumDeclarations.readText().replace("\r\n", "\n").trimEnd()
        var actual = sanitized.joinToString("\n").trimEnd() + "\n"
        val rawAgentSkillScopeDisplayNameDeclaration =
            "export declare function agentSkillScopeDisplayName(scope: string): string;"
        val reviewedAgentSkillScopeDisplayNameDeclaration =
            "export declare function agentSkillScopeDisplayName(scope: AgentSkillScope): string;"
        val rawAgentCapabilityIdDeclaration =
            "export declare function agentCapabilityId(capability: string): string;"
        val reviewedAgentCapabilityIdDeclaration =
            "export declare function agentCapabilityId(capability: AgentCapability): string;"
        val rawAgentCapabilityDisplayLabelDeclaration =
            "export declare function agentCapabilityDisplayLabel(capability: string): string;"
        val reviewedAgentCapabilityDisplayLabelDeclaration =
            "export declare function agentCapabilityDisplayLabel(capability: AgentCapability): string;"
        val rawAgentCapabilityIconDeclaration =
            "export declare function agentCapabilityIcon(capability: string): Nullable<string>;"
        val reviewedAgentCapabilityIconDeclaration =
            "export declare function agentCapabilityIcon(capability: AgentCapability): Nullable<string>;"
        val rawAgentCapabilityPromptLabelDeclaration =
            "export declare function agentCapabilityPromptLabel(capability: string): string;"
        val reviewedAgentCapabilityPromptLabelDeclaration =
            "export declare function agentCapabilityPromptLabel(capability: AgentCapability): string;"
        val rawApprovalPresetDisplayNameDeclaration =
            "export declare function codexApprovalPresetDisplayName(preset: string): string;"
        val reviewedApprovalPresetDisplayNameDeclaration =
            "export declare function codexApprovalPresetDisplayName(preset: CodexApprovalPreset): string;"
        val rawAgentTurnRequestDeclaration =
            """export declare interface AgentTurnRequest {
    readonly prompt: string;
    readonly clientMessageId?: Nullable<string>;
    readonly model?: Nullable<string>;
    readonly effort?: Nullable<string>;
    readonly serviceTier?: Nullable<string>;
    readonly approvalPreset?: Nullable<string>;
    readonly capabilities?: Nullable<Array<string>>;
    readonly invocations?: Nullable<Array<AgentInvocation>>;
    readonly collaborationMode?: Nullable<string>;
}"""
        val reviewedAgentTurnRequestDeclaration =
            """export type AgentTurnRequest = {
    readonly prompt: string;
    readonly clientMessageId?: Nullable<string>;
    readonly model?: Nullable<string>;
    readonly effort?: Nullable<string>;
    readonly serviceTier?: Nullable<string>;
    readonly approvalPreset?: CodexApprovalPreset;
    readonly capabilities?: ReadonlyArray<AgentCapability>;
    readonly invocations?: ReadonlyArray<AgentInvocation>;
    readonly collaborationMode?: AgentCollaborationMode;
};"""
        val expectedSendRequestDeclaration =
            "    sendRequest(request: AgentTurnRequest, signal?: Nullable<AbortSignal>): Promise<void>;"
        val rawAgentHookHandlerDeclaration =
            """export declare interface AgentHookHandler {
}"""
        val reviewedAgentHookHandlerDeclaration =
            """export type AgentHookHandler =
    | { readonly type: "agent" }
    | { readonly type: "command"; readonly command: string; readonly isAsync: boolean }
    | { readonly type: "mcp_tool"; readonly server: string; readonly tool: string }
    | { readonly type: "prompt" };"""
        val rawAgentMcpTransportDeclaration =
            """export declare interface AgentMcpTransport {
    readonly __doNotUseOrImplementIt: {
        readonly AgentMcpTransport: unique symbol;
    };
}"""
        val reviewedAgentMcpTransportDeclaration =
            "export type AgentMcpTransport = AgentMcpStdioTransport | AgentMcpHttpTransport;"
        val rawAgentPendingInteractionDeclaration =
            """export declare interface AgentPendingInteraction {
    readonly requestId: string;
    readonly conversationId: string;
    readonly __doNotUseOrImplementIt: {
        readonly AgentPendingInteraction: unique symbol;
    };
}"""
        val reviewedAgentPendingInteractionDeclaration =
            "export type AgentPendingInteraction = AgentPendingApproval | AgentPendingElicitation;"
        val rawAgentFormFieldDeclaration =
            """export declare class AgentFormField {
    constructor(name: string, title: string, type: string, description?: Nullable<string>, isRequired?: boolean, options?: Array<AgentFormOption>, defaultValue?: Nullable<any>, minimum?: Nullable<number>, maximum?: Nullable<number>, format?: Nullable<string>, minimumLength?: Nullable<bigint>, maximumLength?: Nullable<bigint>, minimumSelections?: Nullable<bigint>, maximumSelections?: Nullable<bigint>, allowsOther?: boolean, isSecret?: boolean);
    get name(): string;
    get title(): string;
    get type(): string;
    get description(): Nullable<string>;
    get isRequired(): boolean;
    get options(): Array<AgentFormOption>;
    get defaultValue(): Nullable<any>;
    get minimum(): Nullable<number>;
    get maximum(): Nullable<number>;
    get format(): Nullable<string>;
    get minimumLength(): Nullable<bigint>;
    get maximumLength(): Nullable<bigint>;
    get minimumSelections(): Nullable<bigint>;
    get maximumSelections(): Nullable<bigint>;
    get allowsOther(): boolean;
    get isSecret(): boolean;
    accepts(value: Nullable<any>): boolean;
}"""
        val reviewedAgentFormFieldDeclaration =
            """export type AgentFormValue =
    | AgentFormBooleanValue
    | AgentFormNumberValue
    | AgentFormTextListValue
    | AgentFormTextValue;
export declare class AgentFormField {
    constructor(name: string, title: string, type: AgentFormFieldType, description?: Nullable<string>, isRequired?: boolean, options?: ReadonlyArray<AgentFormOption>, defaultValue?: Nullable<AgentFormValue>, minimum?: Nullable<number>, maximum?: Nullable<number>, format?: Nullable<AgentFormStringFormat>, minimumLength?: Nullable<bigint>, maximumLength?: Nullable<bigint>, minimumSelections?: Nullable<bigint>, maximumSelections?: Nullable<bigint>, allowsOther?: boolean, isSecret?: boolean);
    get name(): string;
    get title(): string;
    get type(): AgentFormFieldType;
    get description(): Nullable<string>;
    get isRequired(): boolean;
    get options(): ReadonlyArray<AgentFormOption>;
    get defaultValue(): Nullable<AgentFormValue>;
    get minimum(): Nullable<number>;
    get maximum(): Nullable<number>;
    get format(): Nullable<AgentFormStringFormat>;
    get minimumLength(): Nullable<bigint>;
    get maximumLength(): Nullable<bigint>;
    get minimumSelections(): Nullable<bigint>;
    get maximumSelections(): Nullable<bigint>;
    get allowsOther(): boolean;
    get isSecret(): boolean;
    accepts(value: Nullable<AgentFormValue>): boolean;
}"""
        val rawInteractionValueDeclarations =
            """export declare class AgentElicitation {
    constructor(requestId: string, serverName: string, conversationId: string, message: string, form?: Nullable<Array<AgentFormField>>, url?: Nullable<string>);
    get requestId(): string;
    get serverName(): string;
    get conversationId(): string;
    get message(): string;
    get form(): Nullable<Array<AgentFormField>>;
    get url(): Nullable<string>;
    initialValues(): any;
    validate(content: any): AgentElicitationValidation;
    accept(content: any): AgentElicitationResponse;
    accepts(response: AgentElicitationResponse): boolean;
}
export declare class AgentElicitationResponse {
    constructor(action: string, content?: any);
    get action(): string;
    get content(): any;
    static decline(): AgentElicitationResponse;
    static cancel(): AgentElicitationResponse;
}
export declare class AgentPendingApproval implements AgentPendingInteraction {
    constructor(requestId: string, conversationId: string, title: string, details: string);
    get requestId(): string;
    get conversationId(): string;
    get title(): string;
    get details(): string;
    readonly __doNotUseOrImplementIt: AgentPendingInteraction["__doNotUseOrImplementIt"];
}
export declare class AgentPendingElicitation implements AgentPendingInteraction {
    constructor(elicitation: AgentElicitation);
    get elicitation(): AgentElicitation;
    get requestId(): string;
    get conversationId(): string;
    readonly __doNotUseOrImplementIt: AgentPendingInteraction["__doNotUseOrImplementIt"];
}
export declare class AgentInteractionState {
    constructor(pending?: Array<AgentPendingInteraction>, resolvingRequestIds?: Array<string>, failure?: Nullable<CodexFailure>);
    get pending(): Array<AgentPendingInteraction>;
    get resolvingRequestIds(): Array<string>;
    get failure(): Nullable<CodexFailure>;
    pendingFor(conversationId: string): Array<AgentPendingInteraction>;
    isResolving(interaction: AgentPendingInteraction): boolean;
}"""
        val reviewedInteractionValueDeclarations =
            """export declare class AgentElicitation {
    constructor(requestId: string, serverName: string, conversationId: string, message: string, form?: Nullable<ReadonlyArray<AgentFormField>>, url?: Nullable<string>);
    get requestId(): string;
    get serverName(): string;
    get conversationId(): string;
    get message(): string;
    get form(): Nullable<ReadonlyArray<AgentFormField>>;
    get url(): Nullable<string>;
    initialValues(): Readonly<Record<string, AgentFormValue>>;
    validate(content: Readonly<Record<string, AgentFormValue>>): AgentElicitationValidation;
    accept(content: Readonly<Record<string, AgentFormValue>>): AgentElicitationResponse;
    accepts(response: AgentElicitationResponse): boolean;
}
export declare class AgentElicitationResponse {
    constructor(action: AgentElicitationAction, content?: Readonly<Record<string, AgentFormValue>>);
    private readonly __agentElicitationResponseBrand: void;
    get action(): AgentElicitationAction;
    get content(): Readonly<Record<string, AgentFormValue>>;
    static decline(): AgentElicitationResponse;
    static cancel(): AgentElicitationResponse;
}
export declare class AgentPendingApproval {
    constructor(requestId: string, conversationId: string, title: string, details: string);
    get requestId(): string;
    get conversationId(): string;
    get title(): string;
    get details(): string;
}
export declare class AgentPendingElicitation {
    constructor(elicitation: AgentElicitation);
    get elicitation(): AgentElicitation;
    get requestId(): string;
    get conversationId(): string;
}
export declare class AgentInteractionState {
    constructor(pending?: ReadonlyArray<AgentPendingInteraction>, resolvingRequestIds?: ReadonlyArray<string>, failure?: Nullable<CodexFailure>);
    get pending(): ReadonlyArray<AgentPendingInteraction>;
    get resolvingRequestIds(): ReadonlyArray<string>;
    get failure(): Nullable<CodexFailure>;
    pendingFor(conversationId: string): ReadonlyArray<AgentPendingInteraction>;
    isResolving(interaction: AgentPendingInteraction): boolean;
}"""
        val rawAgentConnectorDeclaration =
            """export declare class AgentConnector {
    constructor(id: string, name: string, description?: string, installUrl?: Nullable<string>, isAccessible?: boolean, isEnabled?: boolean, pluginNames?: Array<string>);
    get id(): string;
    get name(): string;
    get description(): string;
    get installUrl(): Nullable<string>;
    get isAccessible(): boolean;
    get isEnabled(): boolean;
    get pluginNames(): Array<string>;
}"""
        val reviewedAgentConnectorDeclaration =
            """export declare class AgentConnector {
    constructor(id: string, name: string, description?: string, installUrl?: Nullable<string>, isAccessible?: boolean, isEnabled?: boolean, pluginNames?: ReadonlyArray<string>);
    get id(): string;
    get name(): string;
    get description(): string;
    get installUrl(): Nullable<string>;
    get isAccessible(): boolean;
    get isEnabled(): boolean;
    get pluginNames(): ReadonlyArray<string>;
}"""
        val rawAgentPluginDeclarations =
            """export declare class AgentPluginReference {
    constructor(id: string, name: string, marketplaceName: string, marketplacePath?: Nullable<string>, remotePluginId?: Nullable<string>);
    get id(): string;
    get name(): string;
    get marketplaceName(): string;
    get marketplacePath(): Nullable<string>;
    get remotePluginId(): Nullable<string>;
    get uri(): string;
}
export declare class AgentPluginSummary {
    constructor(reference: AgentPluginReference, displayName: string, description: string, isInstalled: boolean, isEnabled: boolean, installPolicy: string, authPolicy: string, isAvailable: boolean, capabilities?: Array<string>, brandColor?: Nullable<string>, privacyPolicyUrl?: Nullable<string>, termsOfServiceUrl?: Nullable<string>, websiteUrl?: Nullable<string>);
    get reference(): AgentPluginReference;
    get displayName(): string;
    get description(): string;
    get isInstalled(): boolean;
    get isEnabled(): boolean;
    get installPolicy(): string;
    get authPolicy(): string;
    get isAvailable(): boolean;
    get capabilities(): Array<string>;
    get brandColor(): Nullable<string>;
    get privacyPolicyUrl(): Nullable<string>;
    get termsOfServiceUrl(): Nullable<string>;
    get websiteUrl(): Nullable<string>;
}
export declare class AgentPluginCatalog {
    constructor(plugins: Array<AgentPluginSummary>, errors?: Array<string>, freshness?: string);
    get plugins(): Array<AgentPluginSummary>;
    get errors(): Array<string>;
    get freshness(): string;
}
export declare class AgentPluginSkill {
    constructor(name: string, description: string, isEnabled: boolean, path?: Nullable<string>);
    get name(): string;
    get description(): string;
    get isEnabled(): boolean;
    get path(): Nullable<string>;
}
export declare class AgentPluginDetail {
    constructor(summary: AgentPluginSummary, description: string, skills: Array<AgentPluginSkill>, connectors: Array<AgentConnector>, mcpServers: Array<string>, hookCount: number);
    get summary(): AgentPluginSummary;
    get description(): string;
    get skills(): Array<AgentPluginSkill>;
    get connectors(): Array<AgentConnector>;
    get mcpServers(): Array<string>;
    get hookCount(): number;
}
export declare class AgentPluginInstallResult {
    constructor(authPolicy: string, connectorsNeedingAuthentication: Array<AgentConnector>, message?: Nullable<string>);
    get authPolicy(): string;
    get connectorsNeedingAuthentication(): Array<AgentConnector>;
    get message(): Nullable<string>;
}"""
        val reviewedAgentPluginDeclarations =
            """export declare class AgentPluginReference {
    constructor(id: string, name: string, marketplaceName: string, marketplacePath?: Nullable<string>, remotePluginId?: Nullable<string>);
    get id(): string;
    get name(): string;
    get marketplaceName(): string;
    get marketplacePath(): Nullable<string>;
    get remotePluginId(): Nullable<string>;
    get uri(): string;
}
export declare class AgentPluginSummary {
    constructor(reference: AgentPluginReference, displayName: string, description: string, isInstalled: boolean, isEnabled: boolean, installPolicy: AgentPluginInstallPolicy, authPolicy: AgentPluginAuthPolicy, isAvailable: boolean, capabilities?: ReadonlyArray<string>, brandColor?: Nullable<string>, privacyPolicyUrl?: Nullable<string>, termsOfServiceUrl?: Nullable<string>, websiteUrl?: Nullable<string>);
    get reference(): AgentPluginReference;
    get displayName(): string;
    get description(): string;
    get isInstalled(): boolean;
    get isEnabled(): boolean;
    get installPolicy(): AgentPluginInstallPolicy;
    get authPolicy(): AgentPluginAuthPolicy;
    get isAvailable(): boolean;
    get capabilities(): ReadonlyArray<string>;
    get brandColor(): Nullable<string>;
    get privacyPolicyUrl(): Nullable<string>;
    get termsOfServiceUrl(): Nullable<string>;
    get websiteUrl(): Nullable<string>;
}
export declare class AgentPluginCatalog {
    constructor(plugins: ReadonlyArray<AgentPluginSummary>, errors?: ReadonlyArray<string>, freshness?: AgentCatalogFreshness);
    get plugins(): ReadonlyArray<AgentPluginSummary>;
    get errors(): ReadonlyArray<string>;
    get freshness(): AgentCatalogFreshness;
}
export declare class AgentPluginSkill {
    constructor(name: string, description: string, isEnabled: boolean, path?: Nullable<string>);
    get name(): string;
    get description(): string;
    get isEnabled(): boolean;
    get path(): Nullable<string>;
}
export declare class AgentPluginDetail {
    constructor(summary: AgentPluginSummary, description: string, skills: ReadonlyArray<AgentPluginSkill>, connectors: ReadonlyArray<AgentConnector>, mcpServers: ReadonlyArray<string>, hookCount: number);
    get summary(): AgentPluginSummary;
    get description(): string;
    get skills(): ReadonlyArray<AgentPluginSkill>;
    get connectors(): ReadonlyArray<AgentConnector>;
    get mcpServers(): ReadonlyArray<string>;
    get hookCount(): number;
}
export declare class AgentPluginInstallResult {
    constructor(authPolicy: AgentPluginAuthPolicy, connectorsNeedingAuthentication: ReadonlyArray<AgentConnector>, message?: Nullable<string>);
    get authPolicy(): AgentPluginAuthPolicy;
    get connectorsNeedingAuthentication(): ReadonlyArray<AgentConnector>;
    get message(): Nullable<string>;
}"""
        val rawAgentIntegrationDeclaration =
            """export declare interface AgentIntegration {
    readonly id: string;
    readonly displayName: string;
    readonly __doNotUseOrImplementIt: {
        readonly AgentIntegration: unique symbol;
    };
}"""
        val reviewedAgentIntegrationDeclaration =
            "export type AgentIntegration = AgentConnectorIntegration | AgentMcpServerIntegration;"
        val rawAgentConnectorIntegrationDeclaration =
            """export declare class AgentConnectorIntegration implements AgentIntegration {
    constructor(connector: AgentConnector);
    get connector(): AgentConnector;
    get id(): string;
    get displayName(): string;
    readonly __doNotUseOrImplementIt: AgentIntegration["__doNotUseOrImplementIt"];
}"""
        val reviewedAgentConnectorIntegrationDeclaration =
            """export declare class AgentConnectorIntegration {
    constructor(connector: AgentConnector);
    get connector(): AgentConnector;
    get id(): string;
    get displayName(): string;
}"""
        val rawAgentMcpServerIntegrationDeclaration =
            """export declare class AgentMcpServerIntegration implements AgentIntegration {
    constructor(server: AgentMcpServer);
    get server(): AgentMcpServer;
    get id(): string;
    get displayName(): string;
    readonly __doNotUseOrImplementIt: AgentIntegration["__doNotUseOrImplementIt"];
}"""
        val reviewedAgentMcpServerIntegrationDeclaration =
            """export declare class AgentMcpServerIntegration {
    constructor(server: AgentMcpServer);
    get server(): AgentMcpServer;
    get id(): string;
    get displayName(): string;
}"""
        val rawAgentInvocationDeclaration =
            """export declare interface AgentInvocation {
    readonly name: string;
    readonly key: string;
    readonly __doNotUseOrImplementIt: {
        readonly AgentInvocation: unique symbol;
    };
}"""
        val reviewedAgentInvocationDeclaration =
            "export type AgentInvocation = AgentPluginInvocation | AgentSkillInvocation;"
        val rawAgentSkillInvocationDeclaration =
            """export declare class AgentSkillInvocation implements AgentInvocation {
    constructor(name: string, path: string);
    get name(): string;
    get path(): string;
    get key(): string;
    readonly __doNotUseOrImplementIt: AgentInvocation["__doNotUseOrImplementIt"];
}"""
        val reviewedAgentSkillInvocationDeclaration =
            """export declare class AgentSkillInvocation {
    constructor(name: string, path: string);
    get name(): string;
    get path(): string;
    get key(): string;
}"""
        val rawAgentPluginInvocationDeclaration =
            """export declare class AgentPluginInvocation implements AgentInvocation {
    constructor(name: string, uri: string);
    get name(): string;
    get uri(): string;
    get key(): string;
    readonly __doNotUseOrImplementIt: AgentInvocation["__doNotUseOrImplementIt"];
}"""
        val reviewedAgentPluginInvocationDeclaration =
            """export declare class AgentPluginInvocation {
    constructor(name: string, uri: string);
    get name(): string;
    get uri(): string;
    get key(): string;
}"""
        val rawIntegrationAuthorizationStateDeclaration =
            """export declare class AgentIntegrationAuthorizationState {
    constructor(status?: string, target?: Nullable<AgentIntegration>, failure?: Nullable<CodexFailure>);
    get status(): string;
    get target(): Nullable<AgentIntegration>;
    get failure(): Nullable<CodexFailure>;
}"""
        val reviewedIntegrationAuthorizationStateDeclaration =
            """export declare class AgentIntegrationAuthorizationState {
    constructor(status?: AgentIntegrationAuthorizationStatus, target?: Nullable<AgentIntegration>, failure?: Nullable<CodexFailure>);
    get status(): AgentIntegrationAuthorizationStatus;
    get target(): Nullable<AgentIntegration>;
    get failure(): Nullable<CodexFailure>;
}"""
        val expectedAgentConversationSummaryDeclaration =
            """export declare class AgentConversationSummary {
    constructor(conversationId: string, title: string, updatedAtEpochSeconds: bigint);
    get conversationId(): string;
    get title(): string;
    get updatedAtEpochSeconds(): bigint;
}"""
        val rawAgentConversationDeclaration =
            """export declare class AgentConversation {
    constructor(summary: AgentConversationSummary, messages: Array<CodexMessage>);
    get summary(): AgentConversationSummary;
    get messages(): Array<CodexMessage>;
}"""
        val reviewedAgentConversationDeclaration =
            """export declare class AgentConversation {
    constructor(summary: AgentConversationSummary, messages: ReadonlyArray<CodexMessage>);
    get summary(): AgentConversationSummary;
    get messages(): ReadonlyArray<CodexMessage>;
}"""
        val rawCodexAuthorizationUrlDeclaration =
            """export declare class CodexAuthorizationUrl {
    private constructor();
    get value(): string;
    get purpose(): string;
    static chatGpt(value: string): CodexAuthorizationUrl;
    static external(value: string): CodexAuthorizationUrl;
}"""
        val reviewedCodexAuthorizationUrlDeclaration =
            """export declare class CodexAuthorizationUrl {
    private constructor();
    get value(): string;
    get purpose(): CodexAuthorizationPurpose;
    static chatGpt(value: string): CodexAuthorizationUrl;
    static external(value: string): CodexAuthorizationUrl;
}"""
        val expectedAgentServiceTierDeclaration =
            """export declare class AgentServiceTier {
    constructor(id: string, name: string, description: string);
    get id(): string;
    get name(): string;
    get description(): string;
}"""
        val rawAgentModelDeclaration =
            """export declare class AgentModel {
    constructor(id: string, displayName: string, description: string, supportedEfforts: Array<string>, defaultEffort: string, isDefault: boolean, serviceTiers?: Array<AgentServiceTier>, defaultServiceTier?: Nullable<string>);
    get id(): string;
    get displayName(): string;
    get description(): string;
    get supportedEfforts(): Array<string>;
    get defaultEffort(): string;
    get isDefault(): boolean;
    get serviceTiers(): Array<AgentServiceTier>;
    get defaultServiceTier(): Nullable<string>;
}"""
        val reviewedAgentModelDeclaration =
            """export declare class AgentModel {
    constructor(id: string, displayName: string, description: string, supportedEfforts: ReadonlyArray<string>, defaultEffort: string, isDefault: boolean, serviceTiers?: ReadonlyArray<AgentServiceTier>, defaultServiceTier?: Nullable<string>);
    get id(): string;
    get displayName(): string;
    get description(): string;
    get supportedEfforts(): ReadonlyArray<string>;
    get defaultEffort(): string;
    get isDefault(): boolean;
    get serviceTiers(): ReadonlyArray<AgentServiceTier>;
    get defaultServiceTier(): Nullable<string>;
}"""
        val rawAgentSkillDeclaration =
            """export declare class AgentSkill {
    constructor(name: string, displayName: string, description: string, path: string, scope: string, isEnabled: boolean, brandColor?: Nullable<string>, dependencies?: Array<string>, canUninstall?: boolean, origin?: string);
    get name(): string;
    get displayName(): string;
    get description(): string;
    get path(): string;
    get scope(): string;
    get isEnabled(): boolean;
    get brandColor(): Nullable<string>;
    get dependencies(): Array<string>;
    get canUninstall(): boolean;
    get origin(): string;
}"""
        val reviewedAgentSkillDeclaration =
            """export declare class AgentSkill {
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
}"""
        val rawAgentSkillCatalogDeclaration =
            """export declare class AgentSkillCatalog {
    constructor(skills: Array<AgentSkill>, errors?: Array<string>);
    get skills(): Array<AgentSkill>;
    get errors(): Array<string>;
}"""
        val reviewedAgentSkillCatalogDeclaration =
            """export declare class AgentSkillCatalog {
    constructor(skills: ReadonlyArray<AgentSkill>, errors?: ReadonlyArray<string>);
    get skills(): ReadonlyArray<AgentSkill>;
    get errors(): ReadonlyArray<string>;
}"""
        val rawAgentHookDeclaration =
            """export declare class AgentHook {
    constructor(key: string, currentHash: string, isEnabled: boolean, eventName: string, handler: AgentHookHandler, isManaged: boolean, source: string, sourcePath: string, timeoutSeconds: bigint, trustStatus: string, matcher?: Nullable<string>, pluginId?: Nullable<string>, statusMessage?: Nullable<string>, origin?: string, canUninstall?: boolean);
    get key(): string;
    get currentHash(): string;
    get isEnabled(): boolean;
    get eventName(): string;
    get handler(): AgentHookHandler;
    get isManaged(): boolean;
    get source(): string;
    get sourcePath(): string;
    get timeoutSeconds(): bigint;
    get trustStatus(): string;
    get matcher(): Nullable<string>;
    get pluginId(): Nullable<string>;
    get statusMessage(): Nullable<string>;
    get origin(): string;
    get canUninstall(): boolean;
    get canTrust(): boolean;
}"""
        val reviewedAgentHookDeclaration =
            """export declare class AgentHook {
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
}"""
        val rawAgentHookCatalogDeclaration =
            """export declare class AgentHookCatalog {
    constructor(hooks: Array<AgentHook>, warnings?: Array<string>, errors?: Array<string>);
    get hooks(): Array<AgentHook>;
    get warnings(): Array<string>;
    get errors(): Array<string>;
}"""
        val reviewedAgentHookCatalogDeclaration =
            """export declare class AgentHookCatalog {
    constructor(hooks: ReadonlyArray<AgentHook>, warnings?: ReadonlyArray<string>, errors?: ReadonlyArray<string>);
    get hooks(): ReadonlyArray<AgentHook>;
    get warnings(): ReadonlyArray<string>;
    get errors(): ReadonlyArray<string>;
}"""
        val expectedAgentSkillChunkDeclaration =
            """export declare class AgentSkillChunk {
    constructor(content: string, nextOffset: Nullable<bigint>, totalBytes: bigint);
    get content(): string;
    get nextOffset(): Nullable<bigint>;
    get totalBytes(): bigint;
}"""
        val rawCodexMessageDeclaration =
            """export declare class CodexMessage {
    private constructor();
    get id(): string;
    get clientMessageId(): Nullable<string>;
    get role(): string;
    get text(): string;
    get collaborationMode(): string;
    get reasoning(): Nullable<string>;
    get plan(): Nullable<string>;
    get shellCommand(): Nullable<string>;
    get exitCode(): Nullable<number>;
    get capabilities(): Array<string>;
    get invocations(): Array<AgentInvocation>;
}"""
        val reviewedCodexMessageDeclaration =
            """export declare class CodexMessage {
    private constructor();
    get id(): string;
    get clientMessageId(): Nullable<string>;
    get role(): string;
    get text(): string;
    get collaborationMode(): AgentCollaborationMode;
    get reasoning(): Nullable<string>;
    get plan(): Nullable<string>;
    get shellCommand(): Nullable<string>;
    get exitCode(): Nullable<number>;
    get capabilities(): ReadonlyArray<AgentCapability>;
    get invocations(): ReadonlyArray<AgentInvocation>;
}"""
        val rawListConversationsDeclaration =
            "    listConversations(signal?: Nullable<AbortSignal>): Promise<Array<AgentConversationSummary>>;"
        val reviewedListConversationsDeclaration =
            "    listConversations(signal?: Nullable<AbortSignal>): Promise<ReadonlyArray<AgentConversationSummary>>;"
        val expectedReadConversationDeclaration =
            "    readConversation(conversationId: string, signal?: Nullable<AbortSignal>): Promise<AgentConversation>;"
        val expectedConversationStateConversationDeclaration =
            "    get conversation(): Nullable<AgentConversation>;"
        val rawCodexConnectorsDeclaration =
            """export declare class CodexConnectors {
    private constructor();
    get isAvailable(): boolean;
    list(forceReload?: boolean, signal?: Nullable<AbortSignal>): Promise<Array<AgentConnector>>;
}"""
        val reviewedCodexConnectorsDeclaration =
            """export declare class CodexConnectors {
    private constructor();
    get isAvailable(): boolean;
    list(forceReload?: boolean, signal?: Nullable<AbortSignal>): Promise<ReadonlyArray<AgentConnector>>;
}"""
        val rawCodexModelsDeclaration =
            """export declare class CodexModels {
    private constructor();
    list(signal?: Nullable<AbortSignal>): Promise<Array<AgentModel>>;
    resolve(resolution?: string, signal?: Nullable<AbortSignal>): Promise<AgentModel>;
    resolveEffort(model: AgentModel, resolution?: string, signal?: Nullable<AbortSignal>): Promise<string>;
    resolveServiceTier(model: AgentModel, resolution?: string, signal?: Nullable<AbortSignal>): Promise<Nullable<AgentServiceTier>>;
}"""
        val reviewedCodexModelsDeclaration =
            """export declare class CodexModels {
    private constructor();
    list(signal?: Nullable<AbortSignal>): Promise<ReadonlyArray<AgentModel>>;
    resolve(resolution?: AgentResolution, signal?: Nullable<AbortSignal>): Promise<AgentModel>;
    resolveEffort(model: AgentModel, resolution?: AgentResolution, signal?: Nullable<AbortSignal>): Promise<string>;
    resolveServiceTier(model: AgentModel, resolution?: AgentResolution, signal?: Nullable<AbortSignal>): Promise<Nullable<AgentServiceTier>>;
}"""
        val rawCodexSkillsDeclaration =
            """export declare class CodexSkills {
    private constructor();
    get isAvailable(): boolean;
    list(forceReload?: boolean, signal?: Nullable<AbortSignal>): Promise<AgentSkillCatalog>;
    read(path: string, offset?: bigint, signal?: Nullable<AbortSignal>): Promise<AgentSkillChunk>;
    install(directory: string, scope: string, signal?: Nullable<AbortSignal>): Promise<AgentSkill>;
    uninstall(skill: AgentSkill, signal?: Nullable<AbortSignal>): Promise<void>;
}"""
        val reviewedCodexSkillsDeclaration =
            """export declare class CodexSkills {
    private constructor();
    get isAvailable(): boolean;
    list(forceReload?: boolean, signal?: Nullable<AbortSignal>): Promise<AgentSkillCatalog>;
    read(path: string, offset?: bigint, signal?: Nullable<AbortSignal>): Promise<AgentSkillChunk>;
    install(directory: string, scope: AgentInstallationScope, signal?: Nullable<AbortSignal>): Promise<AgentSkill>;
    uninstall(skill: AgentSkill, signal?: Nullable<AbortSignal>): Promise<void>;
}"""
        val rawCodexHooksDeclaration =
            """export declare class CodexHooks {
    private constructor();
    get isAvailable(): boolean;
    list(signal?: Nullable<AbortSignal>): Promise<AgentHookCatalog>;
    install(directory: string, scope: string, signal?: Nullable<AbortSignal>): Promise<AgentHook>;
    uninstall(hook: AgentHook, signal?: Nullable<AbortSignal>): Promise<void>;
    trust(hook: AgentHook, signal?: Nullable<AbortSignal>): Promise<void>;
}"""
        val reviewedCodexHooksDeclaration =
            """export declare class CodexHooks {
    private constructor();
    get isAvailable(): boolean;
    list(signal?: Nullable<AbortSignal>): Promise<AgentHookCatalog>;
    install(directory: string, scope: AgentInstallationScope, signal?: Nullable<AbortSignal>): Promise<AgentHook>;
    uninstall(hook: AgentHook, signal?: Nullable<AbortSignal>): Promise<void>;
    trust(hook: AgentHook, signal?: Nullable<AbortSignal>): Promise<void>;
}"""
        val expectedCodexPluginsDeclaration =
            """export declare class CodexPlugins {
    private constructor();
    get isAvailable(): boolean;
    list(forceReload?: boolean, signal?: Nullable<AbortSignal>): Promise<AgentPluginCatalog>;
    read(plugin: AgentPluginReference, signal?: Nullable<AbortSignal>): Promise<AgentPluginDetail>;
    install(plugin: AgentPluginReference, signal?: Nullable<AbortSignal>): Promise<AgentPluginInstallResult>;
    uninstall(plugin: AgentPluginReference, signal?: Nullable<AbortSignal>): Promise<void>;
}"""
        val rawAgentMcpStdioTransportDeclaration =
            """export declare class AgentMcpStdioTransport implements AgentMcpTransport {
    constructor(command: string, arguments?: Array<string>, workingDirectory?: Nullable<string>, environment?: Nullable<any>, forwardedEnvironment?: Array<AgentMcpEnvironmentVariable>);
    get command(): string;
    get arguments(): Array<string>;
    get workingDirectory(): Nullable<string>;
    get environment(): Nullable<any>;
    get forwardedEnvironment(): Array<AgentMcpEnvironmentVariable>;
    readonly __doNotUseOrImplementIt: AgentMcpTransport["__doNotUseOrImplementIt"];
}"""
        val reviewedAgentMcpStdioTransportDeclaration =
            """export declare class AgentMcpStdioTransport {
    constructor(command: string, arguments?: ReadonlyArray<string>, workingDirectory?: Nullable<string>, environment?: Nullable<Readonly<Record<string, string>>>, forwardedEnvironment?: ReadonlyArray<AgentMcpEnvironmentVariable>);
    get command(): string;
    get arguments(): ReadonlyArray<string>;
    get workingDirectory(): Nullable<string>;
    get environment(): Nullable<Readonly<Record<string, string>>>;
    get forwardedEnvironment(): ReadonlyArray<AgentMcpEnvironmentVariable>;
}"""
        val rawAgentMcpHttpTransportDeclaration =
            """export declare class AgentMcpHttpTransport implements AgentMcpTransport {
    constructor(url: string, bearerTokenEnvironmentVariable?: Nullable<string>, headers?: Nullable<any>, environmentHeaders?: Nullable<any>, headersHelper?: Nullable<string>);
    get url(): string;
    get bearerTokenEnvironmentVariable(): Nullable<string>;
    get headers(): Nullable<any>;
    get environmentHeaders(): Nullable<any>;
    get headersHelper(): Nullable<string>;
    readonly __doNotUseOrImplementIt: AgentMcpTransport["__doNotUseOrImplementIt"];
}"""
        val reviewedAgentMcpHttpTransportDeclaration =
            """export declare class AgentMcpHttpTransport {
    constructor(url: string, bearerTokenEnvironmentVariable?: Nullable<string>, headers?: Nullable<Readonly<Record<string, string>>>, environmentHeaders?: Nullable<Readonly<Record<string, string>>>, headersHelper?: Nullable<string>);
    get url(): string;
    get bearerTokenEnvironmentVariable(): Nullable<string>;
    get headers(): Nullable<Readonly<Record<string, string>>>;
    get environmentHeaders(): Nullable<Readonly<Record<string, string>>>;
    get headersHelper(): Nullable<string>;
}"""
        val rawAgentMcpServerConfigurationDeclaration =
            """export declare class AgentMcpServerConfiguration {
    constructor(name: string, transport: AgentMcpTransport, authentication?: Nullable<string>, environmentId?: string, isEnabled?: boolean, isRequired?: boolean, supportsParallelToolCalls?: boolean, omitToolsFrom?: Nullable<Array<string>>, startupTimeoutSeconds?: Nullable<number>, toolTimeoutSeconds?: Nullable<number>, defaultToolApproval?: Nullable<string>, enabledTools?: Nullable<Array<string>>, disabledTools?: Nullable<Array<string>>, scopes?: Nullable<Array<string>>, oauth?: Nullable<AgentMcpOauthConfiguration>, oauthResource?: Nullable<string>, tools?: any);
    get name(): string;
    get transport(): AgentMcpTransport;
    get authentication(): Nullable<string>;
    get environmentId(): string;
    get isEnabled(): boolean;
    get isRequired(): boolean;
    get supportsParallelToolCalls(): boolean;
    get omitToolsFrom(): Nullable<Array<string>>;
    get startupTimeoutSeconds(): Nullable<number>;
    get toolTimeoutSeconds(): Nullable<number>;
    get defaultToolApproval(): Nullable<string>;
    get enabledTools(): Nullable<Array<string>>;
    get disabledTools(): Nullable<Array<string>>;
    get scopes(): Nullable<Array<string>>;
    get oauth(): Nullable<AgentMcpOauthConfiguration>;
    get oauthResource(): Nullable<string>;
    get tools(): any;
}"""
        val reviewedAgentMcpServerConfigurationDeclaration =
            """export declare class AgentMcpServerConfiguration {
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
}"""
        val rawAgentMcpServerDeclaration =
            """export declare class AgentMcpServer {
    constructor(name: string, displayName: string, authStatus: string, configuration?: Nullable<AgentMcpServerConfiguration>, origin?: string, canRemove?: boolean);
    get name(): string;
    get displayName(): string;
    get authStatus(): string;
    get configuration(): Nullable<AgentMcpServerConfiguration>;
    get origin(): string;
    get canRemove(): boolean;
    get isAuthorized(): boolean;
}"""
        val reviewedAgentMcpServerDeclaration =
            """export declare class AgentMcpServer {
    constructor(name: string, displayName: string, authStatus: AgentMcpAuthStatus, configuration?: Nullable<AgentMcpServerConfiguration>, origin?: AgentResourceOrigin, canRemove?: boolean);
    get name(): string;
    get displayName(): string;
    get authStatus(): AgentMcpAuthStatus;
    get configuration(): Nullable<AgentMcpServerConfiguration>;
    get origin(): AgentResourceOrigin;
    get canRemove(): boolean;
    get isAuthorized(): boolean;
}"""
        val rawCodexMcpServersDeclaration =
            """export declare class CodexMcpServers {
    private constructor();
    get isAvailable(): boolean;
    list(signal?: Nullable<AbortSignal>): Promise<Array<AgentMcpServer>>;
    add(configuration: AgentMcpServerConfiguration, signal?: Nullable<AbortSignal>): Promise<AgentMcpServer>;
    remove(server: AgentMcpServer, signal?: Nullable<AbortSignal>): Promise<void>;
}"""
        val reviewedCodexMcpServersDeclaration =
            """export declare class CodexMcpServers {
    private constructor();
    get isAvailable(): boolean;
    list(signal?: Nullable<AbortSignal>): Promise<ReadonlyArray<AgentMcpServer>>;
    add(configuration: AgentMcpServerConfiguration, signal?: Nullable<AbortSignal>): Promise<AgentMcpServer>;
    remove(server: AgentMcpServer, signal?: Nullable<AbortSignal>): Promise<void>;
}"""
        val rawCodexIntegrationAuthorizationDeclaration =
            """export declare class CodexIntegrationAuthorization {
    private constructor();
    get state(): AgentIntegrationAuthorizationState;
    get active(): Nullable<AgentIntegration>;
    get isAuthorizing(): boolean;
    authorize(target: AgentIntegration, signal?: Nullable<AbortSignal>): Promise<void>;
    cancel(signal?: Nullable<AbortSignal>): Promise<void>;
    observeState(listener: (p0: AgentIntegrationAuthorizationState) => void): CodexObservation;
    observeActive(listener: (p0: Nullable<AgentIntegration>) => void): CodexObservation;
    observeAuthorizing(listener: (p0: boolean) => void): CodexObservation;
}"""
        val reviewedCodexIntegrationAuthorizationDeclaration =
            """export declare class CodexIntegrationAuthorization {
    private constructor();
    get state(): AgentIntegrationAuthorizationState;
    get active(): Nullable<AgentIntegration>;
    get isAuthorizing(): boolean;
    authorize(target: AgentIntegration, signal?: Nullable<AbortSignal>): Promise<void>;
    cancel(signal?: Nullable<AbortSignal>): Promise<void>;
    observeState(listener: (state: AgentIntegrationAuthorizationState) => void): CodexObservation;
    observeActive(listener: (target: Nullable<AgentIntegration>) => void): CodexObservation;
    observeAuthorizing(listener: (isAuthorizing: boolean) => void): CodexObservation;
}"""
        val rawCodexInteractionsDeclaration =
            """export declare class CodexInteractions {
    private constructor();
    get state(): AgentInteractionState;
    get approvals(): Array<AgentPendingApproval>;
    get elicitations(): Array<AgentPendingElicitation>;
    resolve(interaction: AgentPendingInteraction, resolution: any, signal?: Nullable<AbortSignal>): Promise<void>;
    openUrl(elicitation: AgentPendingElicitation, signal?: Nullable<AbortSignal>): Promise<void>;
    observeState(listener: (p0: AgentInteractionState) => void): CodexObservation;
    observeApprovals(listener: (p0: Array<AgentPendingApproval>) => void): CodexObservation;
    observeElicitations(listener: (p0: Array<AgentPendingElicitation>) => void): CodexObservation;
}"""
        val reviewedCodexInteractionsDeclaration =
            """export declare class CodexInteractions {
    private constructor();
    get state(): AgentInteractionState;
    get approvals(): ReadonlyArray<AgentPendingApproval>;
    get elicitations(): ReadonlyArray<AgentPendingElicitation>;
    resolve(approval: AgentPendingApproval, decision: AgentApprovalDecision, signal?: Nullable<AbortSignal>): Promise<void>;
    resolve(elicitation: AgentPendingElicitation, response: AgentElicitationResponse, signal?: Nullable<AbortSignal>): Promise<void>;
    openUrl(elicitation: AgentPendingElicitation, signal?: Nullable<AbortSignal>): Promise<void>;
    observeState(listener: (state: AgentInteractionState) => void): CodexObservation;
    observeApprovals(listener: (approvals: ReadonlyArray<AgentPendingApproval>) => void): CodexObservation;
    observeElicitations(listener: (elicitations: ReadonlyArray<AgentPendingElicitation>) => void): CodexObservation;
}"""
        check(actual.lineSequence().count { it == rawAgentSkillScopeDisplayNameDeclaration } == 1) {
            "Unexpected agentSkillScopeDisplayName TypeScript declaration"
        }
        check(actual.lineSequence().count { it == rawAgentCapabilityIdDeclaration } == 1) {
            "Unexpected agentCapabilityId TypeScript declaration"
        }
        check(actual.lineSequence().count { it == rawAgentCapabilityDisplayLabelDeclaration } == 1) {
            "Unexpected agentCapabilityDisplayLabel TypeScript declaration"
        }
        check(actual.lineSequence().count { it == rawAgentCapabilityIconDeclaration } == 1) {
            "Unexpected agentCapabilityIcon TypeScript declaration"
        }
        check(actual.lineSequence().count { it == rawAgentCapabilityPromptLabelDeclaration } == 1) {
            "Unexpected agentCapabilityPromptLabel TypeScript declaration"
        }
        check(actual.lineSequence().count { it == rawApprovalPresetDisplayNameDeclaration } == 1) {
            "Unexpected codexApprovalPresetDisplayName TypeScript declaration"
        }
        check(actual.split(rawAgentTurnRequestDeclaration).size == 2) {
            "Unexpected AgentTurnRequest TypeScript declaration"
        }
        check(actual.lineSequence().count { it == expectedSendRequestDeclaration } == 1) {
            "Unexpected CodexConversation.sendRequest TypeScript declaration"
        }
        check(actual.split(rawAgentHookHandlerDeclaration).size == 2) {
            "Unexpected AgentHookHandler TypeScript declaration"
        }
        check(actual.split(rawAgentMcpTransportDeclaration).size == 2) {
            "Unexpected AgentMcpTransport TypeScript declaration"
        }
        check(actual.split(rawAgentPendingInteractionDeclaration).size == 2) {
            "Unexpected AgentPendingInteraction TypeScript declaration"
        }
        check(actual.split(rawAgentFormFieldDeclaration).size == 2) {
            "Unexpected AgentFormField TypeScript declaration"
        }
        check(actual.split(rawInteractionValueDeclarations).size == 2) {
            "Unexpected interaction value TypeScript declarations"
        }
        check(actual.split(rawAgentConnectorDeclaration).size == 2) {
            "Unexpected AgentConnector TypeScript declaration"
        }
        check(actual.split(rawAgentPluginDeclarations).size == 2) {
            "Unexpected plugin value TypeScript declarations"
        }
        check(actual.split(rawAgentIntegrationDeclaration).size == 2) {
            "Unexpected AgentIntegration TypeScript declaration"
        }
        check(actual.split(rawAgentConnectorIntegrationDeclaration).size == 2) {
            "Unexpected AgentConnectorIntegration TypeScript declaration"
        }
        check(actual.split(rawAgentMcpServerIntegrationDeclaration).size == 2) {
            "Unexpected AgentMcpServerIntegration TypeScript declaration"
        }
        check(actual.split(rawAgentInvocationDeclaration).size == 2) {
            "Unexpected AgentInvocation TypeScript declaration"
        }
        check(actual.split(rawAgentSkillInvocationDeclaration).size == 2) {
            "Unexpected AgentSkillInvocation TypeScript declaration"
        }
        check(actual.split(rawAgentPluginInvocationDeclaration).size == 2) {
            "Unexpected AgentPluginInvocation TypeScript declaration"
        }
        check(actual.split(expectedAgentConversationSummaryDeclaration).size == 2) {
            "Unexpected AgentConversationSummary TypeScript declaration"
        }
        check(actual.split(rawAgentConversationDeclaration).size == 2) {
            "Unexpected AgentConversation TypeScript declaration"
        }
        check(actual.split(rawCodexAuthorizationUrlDeclaration).size == 2) {
            "Unexpected CodexAuthorizationUrl TypeScript declaration"
        }
        check(actual.split(rawIntegrationAuthorizationStateDeclaration).size == 2) {
            "Unexpected AgentIntegrationAuthorizationState TypeScript declaration"
        }
        check(actual.split(expectedAgentServiceTierDeclaration).size == 2) {
            "Unexpected AgentServiceTier TypeScript declaration"
        }
        check(actual.split(rawAgentModelDeclaration).size == 2) {
            "Unexpected AgentModel TypeScript declaration"
        }
        check(actual.split(rawAgentSkillDeclaration).size == 2) {
            "Unexpected AgentSkill TypeScript declaration"
        }
        check(actual.split(rawAgentSkillCatalogDeclaration).size == 2) {
            "Unexpected AgentSkillCatalog TypeScript declaration"
        }
        check(actual.split(rawAgentHookDeclaration).size == 2) {
            "Unexpected AgentHook TypeScript declaration"
        }
        check(actual.split(rawAgentHookCatalogDeclaration).size == 2) {
            "Unexpected AgentHookCatalog TypeScript declaration"
        }
        check(actual.split(expectedAgentSkillChunkDeclaration).size == 2) {
            "Unexpected AgentSkillChunk TypeScript declaration"
        }
        check(actual.split(rawCodexMessageDeclaration).size == 2) {
            "Unexpected CodexMessage TypeScript declaration"
        }
        check(actual.lineSequence().count { it == rawListConversationsDeclaration } == 1) {
            "Unexpected CodexAgent.listConversations TypeScript declaration"
        }
        check(actual.lineSequence().count { it == expectedReadConversationDeclaration } == 1) {
            "Unexpected CodexAgent.readConversation TypeScript declaration"
        }
        check(actual.lineSequence().count { it == expectedConversationStateConversationDeclaration } == 1) {
            "Unexpected CodexConversationState.conversation TypeScript declaration"
        }
        check(actual.split(rawCodexConnectorsDeclaration).size == 2) {
            "Unexpected CodexConnectors TypeScript declaration"
        }
        check(actual.lineSequence().count { it == "    get models(): CodexModels;" } == 1) {
            "Unexpected CodexAgent.models TypeScript declaration"
        }
        check(actual.split(rawCodexModelsDeclaration).size == 2) {
            "Unexpected CodexModels TypeScript declaration"
        }
        check(actual.lineSequence().count { it == "    get skills(): CodexSkills;" } == 1) {
            "Unexpected CodexAgent.skills TypeScript declaration"
        }
        check(actual.split(rawCodexSkillsDeclaration).size == 2) {
            "Unexpected CodexSkills TypeScript declaration"
        }
        check(actual.lineSequence().count { it == "    get hooks(): CodexHooks;" } == 1) {
            "Unexpected CodexAgent.hooks TypeScript declaration"
        }
        check(actual.split(rawCodexHooksDeclaration).size == 2) {
            "Unexpected CodexHooks TypeScript declaration"
        }
        check(actual.lineSequence().count { it == "    get plugins(): CodexPlugins;" } == 1) {
            "Unexpected CodexAgent.plugins TypeScript declaration"
        }
        check(actual.split(expectedCodexPluginsDeclaration).size == 2) {
            "Unexpected CodexPlugins TypeScript declaration"
        }
        check(actual.split(rawAgentMcpStdioTransportDeclaration).size == 2) {
            "Unexpected AgentMcpStdioTransport TypeScript declaration"
        }
        check(actual.split(rawAgentMcpHttpTransportDeclaration).size == 2) {
            "Unexpected AgentMcpHttpTransport TypeScript declaration"
        }
        check(actual.split(rawAgentMcpServerConfigurationDeclaration).size == 2) {
            "Unexpected AgentMcpServerConfiguration TypeScript declaration"
        }
        check(actual.split(rawAgentMcpServerDeclaration).size == 2) {
            "Unexpected AgentMcpServer TypeScript declaration"
        }
        check(actual.lineSequence().count { it == "    get mcpServers(): CodexMcpServers;" } == 1) {
            "Unexpected CodexAgent.mcpServers TypeScript declaration"
        }
        check(actual.split(rawCodexMcpServersDeclaration).size == 2) {
            "Unexpected CodexMcpServers TypeScript declaration"
        }
        check(actual.lineSequence().count {
            it == "    get integrationAuthorization(): CodexIntegrationAuthorization;"
        } == 1) {
            "Unexpected CodexAgent.integrationAuthorization TypeScript declaration"
        }
        check(actual.split(rawCodexIntegrationAuthorizationDeclaration).size == 2) {
            "Unexpected CodexIntegrationAuthorization TypeScript declaration"
        }
        check(actual.lineSequence().count { it == "    get interactions(): CodexInteractions;" } == 1) {
            "Unexpected CodexAgent.interactions TypeScript declaration"
        }
        check(actual.split(rawCodexInteractionsDeclaration).size == 2) {
            "Unexpected CodexInteractions TypeScript declaration"
        }
        actual = actual.replace(
            "type Nullable<T> = T | null | undefined\n",
            """type Nullable<T> = T | null | undefined;
export type CodexHostStatus = "new" | "restoring" | "workspace_required" | "preparing" | "ready" | "failed" | "closed";
$canonicalEnumDeclarations
export type CodexAuthenticationMethod = "chatgpt_browser" | "chatgpt_device_code" | "api_key";
""",
        ).replace(
            rawAgentSkillScopeDisplayNameDeclaration,
            reviewedAgentSkillScopeDisplayNameDeclaration,
        ).replace(
            rawAgentCapabilityIdDeclaration,
            reviewedAgentCapabilityIdDeclaration,
        ).replace(
            rawAgentCapabilityDisplayLabelDeclaration,
            reviewedAgentCapabilityDisplayLabelDeclaration,
        ).replace(
            rawAgentCapabilityIconDeclaration,
            reviewedAgentCapabilityIconDeclaration,
        ).replace(
            rawAgentCapabilityPromptLabelDeclaration,
            reviewedAgentCapabilityPromptLabelDeclaration,
        ).replace(
            rawApprovalPresetDisplayNameDeclaration,
            reviewedApprovalPresetDisplayNameDeclaration,
        ).replace(
            rawAgentTurnRequestDeclaration,
            reviewedAgentTurnRequestDeclaration,
        ).replace(
            rawAgentHookHandlerDeclaration,
            reviewedAgentHookHandlerDeclaration,
        ).replace(
            rawAgentMcpTransportDeclaration,
            reviewedAgentMcpTransportDeclaration,
        ).replace(
            rawAgentPendingInteractionDeclaration,
            reviewedAgentPendingInteractionDeclaration,
        ).replace(
            rawAgentFormFieldDeclaration,
            reviewedAgentFormFieldDeclaration,
        ).replace(
            rawInteractionValueDeclarations,
            reviewedInteractionValueDeclarations,
        ).replace(
            rawAgentConnectorDeclaration,
            reviewedAgentConnectorDeclaration,
        ).replace(
            rawAgentPluginDeclarations,
            reviewedAgentPluginDeclarations,
        ).replace(
            rawAgentIntegrationDeclaration,
            reviewedAgentIntegrationDeclaration,
        ).replace(
            rawAgentConnectorIntegrationDeclaration,
            reviewedAgentConnectorIntegrationDeclaration,
        ).replace(
            rawAgentMcpServerIntegrationDeclaration,
            reviewedAgentMcpServerIntegrationDeclaration,
        ).replace(
            rawAgentInvocationDeclaration,
            reviewedAgentInvocationDeclaration,
        ).replace(
            rawAgentSkillInvocationDeclaration,
            reviewedAgentSkillInvocationDeclaration,
        ).replace(
            rawAgentPluginInvocationDeclaration,
            reviewedAgentPluginInvocationDeclaration,
        ).replace(
            rawAgentConversationDeclaration,
            reviewedAgentConversationDeclaration,
        ).replace(
            rawCodexAuthorizationUrlDeclaration,
            reviewedCodexAuthorizationUrlDeclaration,
        ).replace(
            rawIntegrationAuthorizationStateDeclaration,
            reviewedIntegrationAuthorizationStateDeclaration,
        ).replace(
            rawAgentModelDeclaration,
            reviewedAgentModelDeclaration,
        ).replace(
            rawAgentSkillDeclaration,
            reviewedAgentSkillDeclaration,
        ).replace(
            rawAgentSkillCatalogDeclaration,
            reviewedAgentSkillCatalogDeclaration,
        ).replace(
            rawAgentHookDeclaration,
            reviewedAgentHookDeclaration,
        ).replace(
            rawAgentHookCatalogDeclaration,
            reviewedAgentHookCatalogDeclaration,
        ).replace(
            rawCodexMessageDeclaration,
            reviewedCodexMessageDeclaration,
        ).replace(
            rawListConversationsDeclaration,
            reviewedListConversationsDeclaration,
        ).replace(
            rawCodexConnectorsDeclaration,
            reviewedCodexConnectorsDeclaration,
        ).replace(
            rawCodexModelsDeclaration,
            reviewedCodexModelsDeclaration,
        ).replace(
            rawCodexSkillsDeclaration,
            reviewedCodexSkillsDeclaration,
        ).replace(
            rawCodexHooksDeclaration,
            reviewedCodexHooksDeclaration,
        ).replace(
            rawAgentMcpStdioTransportDeclaration,
            reviewedAgentMcpStdioTransportDeclaration,
        ).replace(
            rawAgentMcpHttpTransportDeclaration,
            reviewedAgentMcpHttpTransportDeclaration,
        ).replace(
            rawAgentMcpServerConfigurationDeclaration,
            reviewedAgentMcpServerConfigurationDeclaration,
        ).replace(
            rawAgentMcpServerDeclaration,
            reviewedAgentMcpServerDeclaration,
        ).replace(
            rawCodexMcpServersDeclaration,
            reviewedCodexMcpServersDeclaration,
        ).replace(
            rawCodexIntegrationAuthorizationDeclaration,
            reviewedCodexIntegrationAuthorizationDeclaration,
        ).replace(
            rawCodexInteractionsDeclaration,
            reviewedCodexInteractionsDeclaration,
        ).replace(
            """export declare class AgentFormTextListValue {
    constructor(value: Array<string>);
    get value(): Array<string>;
}""",
            """export declare class AgentFormTextListValue {
    constructor(value: ReadonlyArray<string>);
    get value(): ReadonlyArray<string>;
}""",
        ).replace(
            """export declare class AgentMcpEnvironmentVariable {
    constructor(name: string, source?: Nullable<string>);
    get name(): string;
    get source(): Nullable<string>;
}""",
            """export declare class AgentMcpEnvironmentVariable {
    constructor(name: string, source?: Nullable<AgentMcpEnvironmentSource>);
    get name(): string;
    get source(): Nullable<AgentMcpEnvironmentSource>;
}""",
        ).replace(
            """export declare class AgentMcpToolConfiguration {
    constructor(approval?: Nullable<string>);
    get approval(): Nullable<string>;
}""",
            """export declare class AgentMcpToolConfiguration {
    constructor(approval?: Nullable<AgentMcpToolApproval>);
    get approval(): Nullable<AgentMcpToolApproval>;
}""",
        ).replace(
            """export declare class AgentElicitationValidationIssue {
    constructor(fieldName: string, reason: string);
    get fieldName(): string;
    get reason(): string;
}""",
            """export declare class AgentElicitationValidationIssue {
    constructor(fieldName: string, reason: AgentElicitationValidationReason);
    get fieldName(): string;
    get reason(): AgentElicitationValidationReason;
}""",
        ).replace(
            """export declare class AgentElicitationValidation {
    constructor(issues: Array<AgentElicitationValidationIssue>);
    get issues(): Array<AgentElicitationValidationIssue>;
    get isValid(): boolean;
}""",
            """export declare class AgentElicitationValidation {
    constructor(issues: ReadonlyArray<AgentElicitationValidationIssue>);
    get issues(): ReadonlyArray<AgentElicitationValidationIssue>;
    get isValid(): boolean;
}""",
        ).replace(
            """export declare class AgentPlanStep {
    constructor(text: string, status: string);
    get text(): string;
    get status(): string;
}""",
            """export declare class AgentPlanStep {
    constructor(text: string, status: AgentPlanStepStatus);
    get text(): string;
    get status(): AgentPlanStepStatus;
}""",
        ).replace(
            """export declare class AgentPlanProgress {
    constructor(explanation?: Nullable<string>, steps?: Array<AgentPlanStep>);
    get explanation(): Nullable<string>;
    get steps(): Array<AgentPlanStep>;
}""",
            """export declare class AgentPlanProgress {
    constructor(explanation?: Nullable<string>, steps?: ReadonlyArray<AgentPlanStep>);
    get explanation(): Nullable<string>;
    get steps(): ReadonlyArray<AgentPlanStep>;
}""",
        ).replace(
            """export declare class AgentHookActivity {
    constructor(id: string, eventName: string, handlerType: string, status: string, statusMessage?: Nullable<string>, details?: Array<string>);
    get id(): string;
    get eventName(): string;
    get handlerType(): string;
    get status(): string;
    get statusMessage(): Nullable<string>;
    get details(): Array<string>;
}""",
            """export declare class AgentHookActivity {
    constructor(id: string, eventName: string, handlerType: string, status: AgentHookRunStatus, statusMessage?: Nullable<string>, details?: ReadonlyArray<string>);
    get id(): string;
    get eventName(): string;
    get handlerType(): string;
    get status(): AgentHookRunStatus;
    get statusMessage(): Nullable<string>;
    get details(): ReadonlyArray<string>;
}""",
        ).replace(
            """export declare class CodexTurnProgress {
    private constructor();
    get text(): string;
    get commentary(): string;
    get reasoning(): string;
    get plan(): string;
    get planProgress(): Nullable<AgentPlanProgress>;
    get shellOutput(): string;
    get shellExitCode(): Nullable<number>;
    get workActivity(): Nullable<string>;
    get hookActivities(): Array<AgentHookActivity>;
    get truncated(): boolean;
}""",
            """export declare class CodexTurnProgress {
    private constructor();
    get text(): string;
    get commentary(): string;
    get reasoning(): string;
    get plan(): string;
    get planProgress(): Nullable<AgentPlanProgress>;
    get shellOutput(): string;
    get shellExitCode(): Nullable<number>;
    get workActivity(): Nullable<string>;
    get hookActivities(): ReadonlyArray<AgentHookActivity>;
    get truncated(): boolean;
}""",
        ).replace(
            "    get recoverable(): boolean;\n}\nexport declare class CodexWorkspace",
            "    get recoverable(): boolean;\n    readonly cause?: unknown;\n}\nexport declare class CodexWorkspace",
        ).replace(
            "    get status(): string;\n    get pendingSignInUrl(): Nullable<CodexAuthorizationUrl>;",
            "    get status(): CodexAuthenticationStatus;\n    get pendingSignInUrl(): Nullable<CodexAuthorizationUrl>;",
        ).replace(
            "export declare class CodexHostState {\n    private constructor();\n    get status(): string;",
            "export declare class CodexHostState {\n    private constructor();\n    get status(): CodexHostStatus;",
        ).replace(
            "    get selectionReason(): Nullable<string>;",
            "    get selectionReason(): Nullable<CodexWorkspaceSelectionReason>;",
        ).replace(
            "    get role(): string;",
            "    get role(): CodexMessageRole;",
        ).replace(
            "    get workActivity(): Nullable<string>;",
            "    get workActivity(): Nullable<CodexWorkActivity>;",
        ).replace(
            "export declare class CodexConversationState {\n    private constructor();\n    get status(): string;",
            "export declare class CodexConversationState {\n    private constructor();\n    get status(): CodexConversationStatus;",
        ).replace(
            "    get messages(): Array<CodexMessage>;",
            "    get messages(): ReadonlyArray<CodexMessage>;",
        ).replace(
            "    dispose(): void;\n}\nexport declare class CodexHost",
            "    dispose(): void;\n    [Symbol.dispose](): void;\n}\nexport declare class CodexHost",
        ).replace(
            "    observeState(listener: (p0: CodexHostState) => void): CodexObservation;",
            "    observeState(listener: (state: CodexHostState) => void): CodexObservation;",
        ).replace(
            "    dispose(): Promise<void>;\n}\nexport declare function createCodexHost",
            "    dispose(): Promise<void>;\n    [Symbol.asyncDispose](): Promise<void>;\n}\nexport declare function createCodexHost",
        ).replace(
            "    observeActiveConversation(listener: (p0: Nullable<CodexConversation>) => void): CodexObservation;",
            "    observeActiveConversation(listener: (conversation: Nullable<CodexConversation>) => void): CodexObservation;",
        ).replace(
            "approvalPreset?: Nullable<string>",
            "approvalPreset?: Nullable<CodexApprovalPreset>",
        ).replace(
            "    authenticate(method?: Nullable<string>, apiKey?: Nullable<string>, " +
                "signal?: Nullable<AbortSignal>): Promise<void>;",
            """    authenticate(method?: Nullable<"chatgpt_browser">, apiKey?: null, signal?: Nullable<AbortSignal>): Promise<void>;
    authenticate(method: "chatgpt_device_code", apiKey?: null, signal?: Nullable<AbortSignal>): Promise<void>;
    authenticate(method: "api_key", apiKey: string, signal?: Nullable<AbortSignal>): Promise<void>;""",
        ).replace(
            "observeState(listener: (p0: CodexAuthenticationState) => void)",
            "observeState(listener: (state: CodexAuthenticationState) => void)",
        ).replace(
            "observeAuthenticated(listener: (p0: boolean) => void)",
            "observeAuthenticated(listener: (isAuthenticated: boolean) => void)",
        ).replace(
            "observeAuthenticating(listener: (p0: boolean) => void)",
            "observeAuthenticating(listener: (isAuthenticating: boolean) => void)",
        ).replace(
            "    observeState(listener: (p0: CodexConversationState) => void): CodexObservation;",
            "    observeState(listener: (state: CodexConversationState) => void): CodexObservation;",
        ).replace(
            "    dispose(): Promise<void>;\n}\n",
            "    dispose(): Promise<void>;\n    [Symbol.asyncDispose](): Promise<void>;\n}\n",
        )
        check("kotlin" !in actual.lowercase() && "\$metadata\$" !in actual && Regex("""\bany\b""") !in actual) {
            "Published TypeScript declarations expose Kotlin metadata or untyped any"
        }
        output.parentFile.mkdirs()
        output.writeText(actual)
        check(actual == reviewedGoldenDeclaration.readText().replace("\r\n", "\n")) {
            "Generated Node SDK declarations differ from codex-agent-bindings/javascript/package/index.d.ts"
        }
}

private fun requireJavaScriptRegularFile(file: File): File {
    check(Files.isRegularFile(file.toPath(), NOFOLLOW_LINKS) && !Files.isSymbolicLink(file.toPath())) {
        "JavaScript package input is missing or unsafe: $file"
    }
    return file
}

private fun requireJavaScriptOutput(output: File, inputs: Collection<File>) {
    val path = output.absoluteFile.toPath().normalize()
    var ancestor = path
    while (true) {
        check(!Files.isSymbolicLink(ancestor)) { "JavaScript package output has a symbolic ancestor: $output" }
        ancestor = ancestor.parent ?: break
    }
    inputs.forEach { input ->
        val original = input.canonicalFile.toPath()
        check(!path.startsWith(original) && !original.startsWith(path)) {
            "JavaScript package output overlaps an original input"
        }
    }
}

internal fun stageJavaScriptSdkPackage(
    compiled: File, sources: File, license: File, notices: File,
    compatibility: File, sdkVersion: String, destination: File,
) {
    check(Regex("[0-9]+\\.[0-9]+\\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\\+[0-9A-Za-z.-]+)?").matches(sdkVersion)) {
        "Invalid JavaScript SDK version"
    }
    val compiledFiles = verifiedRegularFiles(compiled)
    val sourceFiles = verifiedRegularFiles(sources)
    val selected = linkedMapOf<String, File>()
    compiledFiles.filterKeys { '/' !in it && (it.endsWith(".js") || it.endsWith(".js.map")) }
        .forEach { (name, file) -> selected["dist/$name"] = file }
    listOf("index.cjs", "index.mjs", "index.d.ts", "README.md").forEach { name ->
        selected[name] = checkNotNull(sourceFiles[name]) { "JavaScript package source is missing: $name" }
    }
    selected["LICENSE"] = requireJavaScriptRegularFile(license)
    selected["THIRD_PARTY_NOTICES.md"] = requireJavaScriptRegularFile(notices)
    selected["META-INF/codex-agent/sdk-compatibility.json"] = requireJavaScriptRegularFile(compatibility)
    val template = checkNotNull(sourceFiles["package.json.template"]) { "JavaScript package template is missing" }
    val packageJson = template.readText(UTF_8).replace("@VERSION@", sdkVersion)
    check(packageJson.contains("\"version\": \"$sdkVersion\"")) {
        "Staged npm package version does not match the selected SDK version"
    }
    check(selected["dist/codex-agent-codex-agent-runtime-desktop.js"]?.let { it.length() > 0 } == true &&
        selected.keys.any { it.startsWith("dist/") && it.endsWith(".map") }) {
        "Staged npm package is missing its linked entry or source maps"
    }
    requireJavaScriptOutput(destination, listOf(compiled, sources, license, notices, compatibility))
    if (destination.exists()) {
        // This is the declared task output, matching the previous Sync's stale-file removal.
        verifiedRegularFiles(destination).filterKeys { it !in selected && it != "package.json" }
            .values.forEach { Files.delete(it.toPath()) }
    } else {
        check(destination.mkdirs()) { "Cannot create JavaScript package staging directory" }
    }
    selected.forEach { (name, input) ->
        val output = destination.resolve(name)
        output.parentFile.mkdirs()
        Files.copy(input.toPath(), output.toPath(), REPLACE_EXISTING)
    }
    destination.resolve("package.json").atomicReplaceTextIfChanged(packageJson)
    check(verifiedRegularFiles(destination).keys == selected.keys + "package.json") {
        "JavaScript package staging contains unexpected files"
    }
}

/** This source-owned policy is keyed in JS phaseInputDigest, not the generic toolchain profile field. */
internal fun withJavaScriptArchivePolicy(policyFile: File, action: () -> Unit) {
    fun canonical(value: kotlinx.serialization.json.JsonElement): kotlinx.serialization.json.JsonElement = when (value) {
        is kotlinx.serialization.json.JsonObject -> kotlinx.serialization.json.JsonObject(
            value.toSortedMap().mapValues { canonical(it.value) })
        is kotlinx.serialization.json.JsonArray -> kotlinx.serialization.json.JsonArray(value.map(::canonical))
        else -> value
    }
    fun identity(file: File): Map<String, Any> {
        requireJavaScriptRegularFile(file)
        check(file.absoluteFile.normalize() == file.canonicalFile) { "Symbolic JavaScript codec input: $file" }
        return Files.readAttributes(file.toPath(), "unix:dev,ino,size,lastModifiedTime,ctime", NOFOLLOW_LINKS)
    }
    fun digest(value: String): String {
        check(Regex("sha256:[0-9a-f]{64}").matches(value)) { "Invalid JavaScript codec digest" }
        return value
    }
    val policyIdentity = identity(policyFile)
    check(policyFile.length() in 1..65536) { "JavaScript codec policy is oversized or empty" }
    val raw = policyFile.readText(UTF_8)
    val policy = policyFile.readReleaseObject()
    check(raw == kotlinx.serialization.json.Json.encodeToString(
        kotlinx.serialization.json.JsonElement.serializer(), canonical(policy)) + "\n") {
        "JavaScript codec policy must use exact canonical JSON"
    }
    check(policy.keys == setOf("schemaVersion", "runner", "javaArchiveSha256", "javaRuntime", "javaFiles", "commonsCompress") &&
        policy.releaseInt("schemaVersion") == 1) { "Unsupported JavaScript codec policy" }
    digest(policy.releaseString("javaArchiveSha256")) // Independently verified image provenance; the selected files are checked below.
    val system = when (System.getProperty("os.name")) { "Linux" -> "Linux"; "Mac OS X" -> "macOS"; else -> error("Unsupported JS codec host") }
    val arch = when (System.getProperty("os.arch")) { "amd64", "x86_64" -> "X64"; "aarch64", "arm64" -> "ARM64"; else -> error("Unsupported JS codec architecture") }
    val runner = policy.releaseObject("runner")
    check(runner.keys == setOf("os", "arch") && runner.releaseString("os") == system && runner.releaseString("arch") == arch) {
        "JavaScript codec host differs from source policy"
    }
    val javaHome = File(System.getProperty("java.home")).canonicalFile
    val javaLauncher = javaHome.resolve("bin/java")
    check(File(ProcessHandle.current().info().command().orElseThrow()).canonicalFile == javaLauncher.canonicalFile) {
        "JavaScript codec Java home differs from the actual process launcher"
    }
    val javaFiles = policy.releaseArray("javaFiles").map { it as kotlinx.serialization.json.JsonObject }
    val paths = javaFiles.map { it.releaseString("relativePath") }
    val suffix = if (system == "Linux") ".so" else ".dylib"
    check(paths == paths.sorted().distinct() && paths.size == 7 &&
        paths.containsAll(listOf("bin/java", "lib/modules", "release")) &&
        paths.map { it.substringAfterLast('/') }.containsAll(listOf("libjava", "libjli", "libzip", "libjvm").map { it + suffix })) {
        "JavaScript codec policy must bind the exact Java and bundled compression files"
    }
    val held = linkedMapOf<File, Map<String, Any>>(policyFile to policyIdentity)
    val observedHashes = linkedMapOf<String, String>()
    javaFiles.forEach { record ->
        check(record.keys == setOf("relativePath", "bytes", "sha256")) { "Unexpected JavaScript runtime file fields" }
        val relative = record.releaseString("relativePath")
        check(relative.split('/').all { it.isNotEmpty() && it != "." && it != ".." } && '\\' !in relative) {
            "Unsafe JavaScript runtime file path"
        }
        val file = javaHome.resolve(relative)
        held[file] = identity(file)
        check(record.releaseLong("bytes") > 0 && file.length() == record.releaseLong("bytes")) { "JavaScript runtime file length differs" }
        val observed = "sha256:" + file.releaseDigest()
        check(observed == digest(record.releaseString("sha256"))) { "JavaScript runtime file differs: $relative" }
        observedHashes[relative] = observed
    }
    val actualRuntime = mapOf(
        "arch" to System.getProperty("os.arch"), "binarySha256" to observedHashes.getValue("bin/java"),
        "runtimeVersion" to System.getProperty("java.runtime.version"), "vendor" to System.getProperty("java.vendor"),
        "vendorVersion" to System.getProperty("java.vendor.version", ""), "vmName" to System.getProperty("java.vm.name"),
        "vmVersion" to System.getProperty("java.vm.version"),
    )
    val expectedRuntime = policy.releaseObject("javaRuntime")
    check(expectedRuntime.keys == actualRuntime.keys && actualRuntime.all { (key, value) -> expectedRuntime.releaseString(key) == value }) {
        "JavaScript Java identity differs from source policy"
    }
    val codec = policy.releaseObject("commonsCompress")
    check(codec.keys == setOf("version", "resources")) { "Unexpected JavaScript TAR codec fields" }
    val codecClass = TarArchiveOutputStream::class.java
    val origin = codecClass.protectionDomain.codeSource.location
    val codecFile = File(origin.toURI())
    held[codecFile] = identity(codecFile)
    val names = listOf("TarArchiveEntry", "TarArchiveOutputStream", "TarUtils")
    names.forEach { name ->
        val type = Class.forName("org.apache.commons.compress.archivers.tar.$name", false, codecClass.classLoader)
        check(type.protectionDomain.codeSource.location == origin) { "JavaScript TAR codec classes have mixed origins" }
    }
    val pom = "META-INF/maven/org.apache.commons/commons-compress/pom.properties"
    val required = (listOf(pom) + names.map { "org/apache/commons/compress/archivers/tar/$it.class" }).sorted()
    val resources = codec.releaseArray("resources").map { it as kotlinx.serialization.json.JsonObject }
    check(resources.map { it.releaseString("relativePath") } == required) { "JavaScript TAR codec resource set differs" }
    resources.forEach { record ->
        check(record.keys == setOf("relativePath", "bytes", "sha256")) { "Unexpected JavaScript codec resource fields" }
        val name = record.releaseString("relativePath")
        val size = record.releaseLong("bytes")
        check(size in 1..1_048_576) { "JavaScript codec resource size is invalid" }
        val bytes = checkNotNull(codecClass.classLoader.getResourceAsStream(name)).use { it.readNBytes(size.toInt() + 1) }
        check(bytes.size.toLong() == size && "sha256:" + bytes.inputStream().releaseDigest() == digest(record.releaseString("sha256"))) {
            "JavaScript TAR codec differs: $name"
        }
        if (name == pom) {
            val properties = java.util.Properties().apply { bytes.inputStream().use { load(it) } }
            check(properties.getProperty("groupId") == "org.apache.commons" && properties.getProperty("artifactId") == "commons-compress" &&
                properties.getProperty("version") == codec.releaseString("version")) { "JavaScript TAR codec version differs" }
        }
    }
    fun unchanged() {
        check(held.all { (file, before) -> identity(file) == before } && policyFile.readText(UTF_8) == raw) {
            "JavaScript codec inputs changed during package production"
        }
    }
    unchanged()
    try { action() } finally { unchanged() }
}

/** New, explicitly JS-owned archive contract; it does not reproduce Gradle Tar's old headers. */
internal fun writeJavaScriptSdkArchive(stage: File, archive: File) {
    val files = verifiedRegularFiles(stage).toSortedMap()
    check(files.isNotEmpty()) { "JavaScript package stage is empty" }
    files.keys.forEach { relative ->
        check('\\' !in relative && relative.split('/').all { it.isNotEmpty() && it != "." && it != ".." } &&
            relative.none { it.code < 32 || it.code == 127 }) { "Unsafe JavaScript package path: $relative" }
    }
    requireJavaScriptOutput(archive, listOf(stage))
    archive.parentFile.mkdirs()
    val temporary = Files.createTempFile(archive.parentFile.toPath(), ".javascript-package-", ".tgz")
    try {
        Files.newOutputStream(temporary).use { raw ->
            object : GZIPOutputStream(raw) { init { def.setLevel(9) } }.use { gzip ->
                TarArchiveOutputStream(gzip, 10_240, UTF_8.name()).use { tar ->
                    tar.setLongFileMode(TarArchiveOutputStream.LONGFILE_POSIX)
                    tar.setBigNumberMode(TarArchiveOutputStream.BIGNUMBER_POSIX)
                    tar.setAddPaxHeadersForNonAsciiNames(true)
                    files.forEach { (relative, file) ->
                        val entry = TarArchiveEntry("package/$relative").apply {
                            size = file.length()
                            mode = 420 // 0644, independent of source umask and executable bits.
                            modTime = Date(315_532_800_000L)
                            setUserId(0L)
                            setGroupId(0L)
                            userName = ""
                            groupName = ""
                        }
                        tar.putArchiveEntry(entry)
                        file.inputStream().use { it.copyTo(tar) }
                        tar.closeArchiveEntry()
                    }
                }
            }
        }
        Files.move(temporary, archive.toPath(), REPLACE_EXISTING)
    } finally {
        Files.deleteIfExists(temporary)
    }
}

/** Diagnostics only: actual class-loader/codec equality must be checked by the control fixture. */
internal fun javaScriptArchiveEncoderIdentity(): String = listOf(
    TarArchiveOutputStream::class.java.name,
    TarArchiveOutputStream::class.java.`package`.implementationVersion ?: "unspecified",
    TarArchiveOutputStream::class.java.protectionDomain.codeSource?.location?.toExternalForm() ?: "unavailable",
    System.getProperty("java.runtime.version"),
).joinToString("|")

@CacheableTask
abstract class StageJavaScriptSdkPackageTask : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val compiledDirectory: DirectoryProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val sourceDirectory: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val licenseFile: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val noticesFile: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val compatibilityFile: RegularFileProperty
    @get:Input abstract val sdkVersion: Property<String>
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val archivePolicyFile: RegularFileProperty
    @get:OutputDirectory abstract val destinationDirectory: DirectoryProperty

    @TaskAction fun stage() = withJavaScriptArchivePolicy(archivePolicyFile.get().asFile) {
        stageJavaScriptSdkPackage(compiledDirectory.get().asFile, sourceDirectory.get().asFile,
            licenseFile.get().asFile, noticesFile.get().asFile, compatibilityFile.get().asFile,
            sdkVersion.get(), destinationDirectory.get().asFile)
    }
}

@CacheableTask
abstract class PackageJavaScriptSdkTask : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val stageDirectory: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val archivePolicyFile: RegularFileProperty
    @get:OutputFile abstract val archiveFile: RegularFileProperty

    @TaskAction fun archive() = withJavaScriptArchivePolicy(archivePolicyFile.get().asFile) {
        println("JavaScript archive encoder: ${javaScriptArchiveEncoderIdentity()}")
        writeJavaScriptSdkArchive(stageDirectory.get().asFile, archiveFile.get().asFile)
    }
}

/** Fixed producer only. The caller owns original authentication, source/key binding and final admission. */
object JavaScriptSdkPackageMain {
    @JvmStatic fun main(arguments: Array<String>) {
        check(arguments.size == 10) {
            "Expected SDK version, Runtime adapter, package source, Contract API, compatibility, LICENSE, notices, private work, archive, codec policy"
        }
        val version = arguments[0]
        val compiled = File(arguments[1])
        val sources = File(arguments[2])
        val api = requireJavaScriptRegularFile(File(arguments[3]))
        val compatibility = requireJavaScriptRegularFile(File(arguments[4]))
        val license = requireJavaScriptRegularFile(File(arguments[5]))
        val notices = requireJavaScriptRegularFile(File(arguments[6]))
        val work = File(arguments[7])
        val archive = File(arguments[8])
        val policy = requireJavaScriptRegularFile(File(arguments[9]))
        val inputs = listOf(compiled, sources, api, compatibility, license, notices, policy)
        requireJavaScriptOutput(work, inputs)
        requireJavaScriptOutput(archive, inputs + work)
        check(!work.exists() && !archive.exists() && !Files.isSymbolicLink(work.toPath()) &&
            !Files.isSymbolicLink(archive.toPath())) { "JavaScript standalone producer requires fresh outputs" }
        withJavaScriptArchivePolicy(policy) {
            check(work.mkdirs()) { "Cannot create JavaScript private work directory" }
            val enums = work.resolve("canonical-enums.d.ts")
            Files.writeString(enums.toPath(), renderJavaScriptEnumDeclarations(api), UTF_8, CREATE_NEW)
            verifyJavaScriptDeclarationGolden(compiled.resolve("codex-agent-codex-agent-runtime-desktop.d.ts"),
                sources.resolve("index.d.ts"), enums, work.resolve("generated-index.d.ts"))
            val stage = work.resolve("package")
            stageJavaScriptSdkPackage(compiled, sources, license, notices, compatibility, version, stage)
            println("JavaScript archive encoder: ${javaScriptArchiveEncoderIdentity()}")
            writeJavaScriptSdkArchive(stage, archive)
        }
    }
}
