import com.vanniktech.maven.publish.JavadocJar
import com.vanniktech.maven.publish.KotlinMultiplatform
import com.vanniktech.maven.publish.SourcesJar
import java.io.File
import java.util.zip.ZipFile
import org.apache.tools.ant.filters.ReplaceTokens
import org.gradle.api.file.DuplicatesStrategy
import org.gradle.api.tasks.Sync
import org.gradle.api.tasks.bundling.Compression
import org.gradle.api.tasks.bundling.Tar
import org.gradle.api.tasks.bundling.Zip
import org.jetbrains.kotlin.gradle.targets.js.nodejs.NodeJsEnvSpec
import org.jetbrains.kotlin.gradle.targets.wasm.nodejs.WasmNodeJsEnvSpec

plugins {
    alias(libs.plugins.kotlin.multiplatform)
    alias(libs.plugins.maven.publish)
    id("codexagent.desktop-runtime")
}

val codexAgentRepositoryUrl = rootProject.extra["codexAgent.repositoryUrl"].toString()

kotlin {
    explicitApi()
    sourceSets {
        commonMain.dependencies {
            api(project(":codex-agent-core"))
            implementation(libs.kotlinx.coroutines.core)
            implementation(libs.okio)
        }
        commonTest.dependencies {
            implementation(kotlin("test"))
            implementation(libs.kotlinx.coroutines.test)
        }
        nativeTest.dependencies { implementation(kotlin("test")) }
        jvmTest.dependencies { implementation(kotlin("test")) }
        jsTest.dependencies { implementation(kotlin("test")) }
        wasmJsTest.dependencies { implementation(kotlin("test")) }
    }
}

rootProject.extensions.configure<NodeJsEnvSpec> { download.set(false) }
extensions.configure<NodeJsEnvSpec> { download.set(false) }
rootProject.extensions.configure<WasmNodeJsEnvSpec> { download.set(false) }
extensions.configure<WasmNodeJsEnvSpec> { download.set(false) }

val packageNodeRuntimeEvidenceRunner = tasks.register<Zip>(
    "packageNodeRuntimeEvidenceRunner",
) {
    group = "distribution"
    description = "Packages the compiled standalone Node runtime evidence runner."
    dependsOn("jsProductionExecutableCompileSync")
    from(layout.buildDirectory.dir("compileSync/js/main/productionExecutable/kotlin")) {
        include("*.js")
    }
    archiveFileName.set("codex-agent-node-runtime-evidence-runner.zip")
    destinationDirectory.set(layout.buildDirectory.dir("distributions"))
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
    entryCompression = ZipEntryCompression.STORED
    doLast {
        ZipFile(archiveFile.get().asFile).use { zip ->
            val members = zip.entries().asSequence().toList()
            check(members.isNotEmpty() && members.none { it.isDirectory } &&
                members.map { it.name }.toSet().size == members.size &&
                members.all { it.name == File(it.name).name && it.name.endsWith(".js") && it.size > 0 } &&
                members.any { it.name == "codex-agent-codex-agent-runtime-desktop.js" }) {
                "Node evidence runner package has an incomplete or unsafe CommonJS module set"
            }
        }
    }
}

val npmEntryModule = "codex-agent-codex-agent-runtime-desktop"
val npmVersion = version.toString()
val npmSourceDirectory = layout.projectDirectory.dir("npm/package")
val npmConsumerSourceDirectory = layout.projectDirectory.dir("npm/consumer")
val npmCompiledDirectory = layout.buildDirectory.dir("compileSync/js/main/productionExecutable/kotlin")
val npmGeneratedDeclaration = npmCompiledDirectory.map { it.file("$npmEntryModule.d.ts") }
val npmReviewedDeclaration = npmSourceDirectory.file("index.d.ts")
val crossLanguageApiReport = rootProject.layout.projectDirectory.file(
    "codex-agent-core/build/reports/cross-language-api/canonical-api.json",
)
val npmGeneratedEnumDeclarations =
    layout.buildDirectory.file("generated/cross-language-js/canonical-enums.d.ts")
val npmDeclarationReport = layout.buildDirectory.file("reports/npm/generated-index.d.ts")
val npmStageDirectory = layout.buildDirectory.dir("npm/package")
val npmConsumerDirectory = layout.buildDirectory.dir("npm/consumer")
val npmConsumerCacheDirectory = layout.buildDirectory.dir("npm/cache")
val npmPublicApiReport = layout.buildDirectory.file("npm/consumer/public-api.json")
val npmPackedTestReport = layout.buildDirectory.file("npm/consumer/packed-tests.xml")
val javaScriptBindingParityReceipt =
    layout.buildDirectory.file("reports/cross-language-api/bindings/javascript-typescript-parity.json")
val invalidateJavaScriptTypeScriptBindingParityOutput = tasks.register<Delete>(
    "invalidateJavaScriptTypeScriptBindingParityOutput",
) {
    group = "verification"
    description = "Deletes stale JavaScript/TypeScript parity output before its prerequisites execute."
    delete(javaScriptBindingParityReceipt)
}

val generateJavaScriptEnumDeclarations = tasks.register<GenerateJavaScriptEnumDeclarationsTask>(
    "generateJavaScriptEnumDeclarations",
) {
    dependsOn(":codex-agent-core:discoverCrossLanguageApi")
    apiReport.set(crossLanguageApiReport)
    declarationsFile.set(npmGeneratedEnumDeclarations)
}

val verifyNpmDeclarationGolden = tasks.register("verifyNpmDeclarationGolden") {
    group = "verification"
    description = "Verifies the reviewed Node SDK declaration against the Kotlin compiler output."
    dependsOn("jsProductionExecutableCompileSync", generateJavaScriptEnumDeclarations)
    inputs.file(npmGeneratedDeclaration)
    inputs.file(npmReviewedDeclaration)
    inputs.file(npmGeneratedEnumDeclarations)
    outputs.file(npmDeclarationReport)
    doLast {
        val rawCompilerDeclaration = npmGeneratedDeclaration.get().asFile
        val reviewedGoldenDeclaration = npmReviewedDeclaration.asFile
        val generatedEnumDeclarations = npmGeneratedEnumDeclarations.get().asFile
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
        val output = outputs.files.singleFile
        output.parentFile.mkdirs()
        output.writeText(actual)
        check(actual == reviewedGoldenDeclaration.readText().replace("\r\n", "\n")) {
            "Generated Node SDK declarations differ from npm/package/index.d.ts"
        }
    }
}

val stageNpmPackage = tasks.register<Sync>("stageNpmPackage") {
    group = "distribution"
    description = "Stages the deterministic Node-only JavaScript and TypeScript SDK."
    dependsOn(verifyNpmDeclarationGolden)
    inputs.property("npmVersion", npmVersion)
    duplicatesStrategy = DuplicatesStrategy.FAIL
    into(npmStageDirectory)
    from(npmCompiledDirectory) {
        include("*.js", "*.js.map")
        into("dist")
    }
    from(npmSourceDirectory) {
        include("index.cjs", "index.mjs", "index.d.ts", "README.md")
    }
    from(npmSourceDirectory.file("package.json.template")) {
        rename { "package.json" }
        filter<ReplaceTokens>("tokens" to mapOf("VERSION" to npmVersion))
    }
    from(rootProject.layout.projectDirectory.file("LICENSE"))
    from(rootProject.layout.projectDirectory.file("THIRD_PARTY_NOTICES.md"))
    doLast {
        val expectedVersion = inputs.properties.getValue("npmVersion").toString()
        val stage = destinationDir
        val entry = stage.resolve("dist/codex-agent-codex-agent-runtime-desktop.js")
        val modules = stage.resolve("dist").listFiles().orEmpty().filter(File::isFile)
        check(entry.isFile && entry.length() > 0 && modules.any { it.extension == "map" }) {
            "Staged npm package is missing its linked entry or source maps"
        }
        check(stage.resolve("package.json").readText().contains("\"version\": \"$expectedVersion\"")) {
            "Staged npm package version does not match the Gradle project"
        }
    }
}

val packageNpm = tasks.register<Tar>("packageNpm") {
    group = "distribution"
    description = "Packages the deterministic Node-only JavaScript and TypeScript SDK."
    dependsOn(stageNpmPackage)
    duplicatesStrategy = DuplicatesStrategy.FAIL
    compression = Compression.GZIP
    archiveFileName.set("codex-agent-$npmVersion.tgz")
    destinationDirectory.set(layout.buildDirectory.dir("distributions"))
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
    from(npmStageDirectory) { into("package") }
}

val npmArchiveFile = layout.buildDirectory.file("distributions/codex-agent-$npmVersion.tgz")

val verifyNpmPackDryRun = tasks.register<Exec>("verifyNpmPackDryRun") {
    group = "verification"
    description = "Validates npm's exact public file inventory without creating another archive."
    dependsOn(stageNpmPackage)
    workingDir(npmStageDirectory)
    environment("npm_config_cache", npmConsumerCacheDirectory.get().asFile.absolutePath)
    commandLine("npm", "pack", "--dry-run", "--json", "--ignore-scripts")
}

val preparePackedNpmConsumer = tasks.register<Sync>("preparePackedNpmConsumer") {
    group = "verification"
    description = "Prepares an isolated consumer for the packed Node SDK."
    duplicatesStrategy = DuplicatesStrategy.FAIL
    from(npmConsumerSourceDirectory)
    into(npmConsumerDirectory)
}

val npmCiPackedConsumer = tasks.register<Exec>("npmCiPackedConsumer") {
    group = "verification"
    description = "Installs the pinned TypeScript toolchain for the isolated npm consumer."
    dependsOn(preparePackedNpmConsumer)
    workingDir(npmConsumerDirectory)
    environment("npm_config_engine_strict", "true")
    environment("npm_config_cache", npmConsumerCacheDirectory.get().asFile.absolutePath)
    commandLine("npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund")
}

val installPackedNpmSdk = tasks.register<Exec>("installPackedNpmSdk") {
    group = "verification"
    description = "Installs the exact generated SDK tarball into the isolated npm consumer."
    dependsOn(npmCiPackedConsumer, packageNpm, verifyNpmPackDryRun)
    workingDir(npmConsumerDirectory)
    inputs.file(npmArchiveFile)
    environment("npm_config_engine_strict", "true")
    environment("npm_config_cache", npmConsumerCacheDirectory.get().asFile.absolutePath)
    commandLine(
        "npm",
        "install",
        "--no-save",
        "--package-lock=false",
        "--ignore-scripts",
        "--no-audit",
        "--no-fund",
        npmArchiveFile.get().asFile.absolutePath,
    )
}

val verifyPackedNpmConsumers = tasks.register<Exec>("verifyPackedNpmConsumers") {
    group = "verification"
    description = "Type-checks and executes CJS/ESM consumers against the exact SDK tarball."
    dependsOn(installPackedNpmSdk)
    workingDir(npmConsumerDirectory)
    inputs.file(npmArchiveFile)
    inputs.files(npmConsumerSourceDirectory.asFileTree)
    outputs.files(npmPublicApiReport, npmPackedTestReport)
    environment("CODEX_AGENT_NPM_TARBALL", npmArchiveFile.get().asFile.absolutePath)
    commandLine("npm", "run", "verify")
    doFirst {
        outputs.files.forEach(File::delete)
    }
    doLast {
        val publicApi = outputs.files.single { it.name == "public-api.json" }
        val junit = outputs.files.single { it.name == "packed-tests.xml" }
        val publicApiText = publicApi.takeIf(File::isFile)?.readText().orEmpty()
        check(publicApi.isFile && publicApi.length() > 0 &&
            publicApiText.startsWith("{\n    \"schema\": 2,") && publicApiText.endsWith("}\n") &&
            "\"referencedSymbols\": [" in publicApiText) {
            "Packed npm compiler API report is missing or malformed"
        }
        val testReport = junit.takeIf(File::isFile)?.readText().orEmpty()
        check(testReport.isNotBlank() &&
            !Regex("""<(failure|error|skipped)\b""").containsMatchIn(testReport)) {
            "Packed npm JUnit evidence is missing, failed, or skipped"
        }
        listOf(
            "cjs exposes the exact Node-only SDK surface",
            "cjs projects lifecycle state failure cleanup and terminal delivery",
            "cjs maps AbortSignal cancellation without starting",
            "esm exposes the same runtime values as CommonJS",
            "typescript compiler discovers the exact installed public API",
        ).forEach { testId ->
            check(testId in testReport) { "Packed npm JUnit evidence did not execute: $testId" }
        }
    }
}

val jsNodeTest = tasks.named("jsNodeTest")
verifyPackedNpmConsumers.configure { dependsOn(invalidateJavaScriptTypeScriptBindingParityOutput) }
jsNodeTest.configure { dependsOn(invalidateJavaScriptTypeScriptBindingParityOutput) }
tasks.configureEach {
    if (name != invalidateJavaScriptTypeScriptBindingParityOutput.name) {
        mustRunAfter(invalidateJavaScriptTypeScriptBindingParityOutput)
    }
}
project(":codex-agent-core").tasks.matching {
    it.name == "invalidateCrossLanguageBindingParityOutputs"
}.configureEach {
    dependsOn(invalidateJavaScriptTypeScriptBindingParityOutput)
}

tasks.register<VerifyJavaScriptTypeScriptBindingParityTask>("verifyJavaScriptTypeScriptBindingParity") {
    group = "verification"
    description = "Verifies the exact packed JavaScript/TypeScript API and shared projection behavior parity."
    dependsOn(
        invalidateJavaScriptTypeScriptBindingParityOutput,
        ":codex-agent-core:verifyCrossLanguageApiCoverage",
        verifyPackedNpmConsumers,
        jsNodeTest,
    )
    apiReport.set(rootProject.layout.projectDirectory.file(
        "codex-agent-core/build/reports/cross-language-api/canonical-api.json",
    ))
    coverage.set(rootProject.layout.projectDirectory.file(
        "codex-agent-core/build/reports/cross-language-api/canonical-coverage.json",
    ))
    packedApiReport.set(npmPublicApiReport)
    npmTarball.set(npmArchiveFile)
    installedPackage.set(npmConsumerDirectory.map {
        it.dir("node_modules/@codex-agent-labs/codex-agent")
    })
    packedConsumerProgram.set(npmConsumerSourceDirectory)
    compiledJsNodeTestProgram.set(
        layout.buildDirectory.dir("compileSync/js/test/testDevelopmentExecutable/kotlin"),
    )
    packedJUnit.set(npmPackedTestReport)
    jsNodeJUnit.set(layout.buildDirectory.file(
        "test-results/jsNodeTest/TEST-jsNodeTest.CodexNodeApiTest.xml",
    ))
    receiptFile.set(javaScriptBindingParityReceipt)
}

val nodeWasmRunnerBaseName = "codex-agent-codex-agent-runtime-desktop"
val nodeWasmRunnerMembers = setOf(
    "$nodeWasmRunnerBaseName.mjs",
    "$nodeWasmRunnerBaseName.uninstantiated.mjs",
    "$nodeWasmRunnerBaseName.wasm",
    "custom-formatters.js",
)
val packageNodeWasmRuntimeEvidenceRunner = tasks.register<Zip>(
    "packageNodeWasmRuntimeEvidenceRunner",
) {
    group = "distribution"
    description = "Packages the unoptimized standalone Kotlin/Wasm Node evidence runner."
    dependsOn("wasmJsDevelopmentExecutableCompileSync")
    from(layout.buildDirectory.dir("compileSync/wasmJs/main/developmentExecutable/kotlin")) {
        include(nodeWasmRunnerMembers)
    }
    archiveFileName.set("codex-agent-node-wasm-runtime-evidence-runner.zip")
    destinationDirectory.set(layout.buildDirectory.dir("distributions"))
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
    entryCompression = ZipEntryCompression.STORED
    doLast {
        ZipFile(archiveFile.get().asFile).use { zip ->
            val members = zip.entries().asSequence().toList()
            val expectedMembers = setOf(
                "codex-agent-codex-agent-runtime-desktop.mjs",
                "codex-agent-codex-agent-runtime-desktop.uninstantiated.mjs",
                "codex-agent-codex-agent-runtime-desktop.wasm",
                "custom-formatters.js",
            )
            check(
                members.none { it.isDirectory } &&
                    members.map { it.name }.toSet() == expectedMembers &&
                    members.all { it.name == File(it.name).name && it.size > 0 }
            ) { "Node Wasm evidence runner package has an incomplete or unsafe module set" }
        }
    }
}

mavenPublishing {
    configure(
        KotlinMultiplatform(
            javadocJar = JavadocJar.Empty(),
            sourcesJar = SourcesJar.Sources(),
        ),
    )
    coordinates(project.group.toString(), "codex-agent-runtime-desktop", project.version.toString())
    if (
        providers.gradleProperty("signingInMemoryKey").isPresent ||
        providers.gradleProperty("signing.secretKeyRingFile").isPresent
    ) {
        signAllPublications()
    }
    pom {
        name.set("Codex Agent Runtime for Desktop")
        description.set("JVM, Native, and Node desktop process runtime for the Codex App Server.")
        inceptionYear.set("2026")
        url.set(codexAgentRepositoryUrl)
        licenses {
            license {
                name.set("GNU General Public License v3.0 or later")
                url.set("https://www.gnu.org/licenses/gpl-3.0.txt")
                distribution.set("repo")
            }
        }
        developers {
            developer {
                id.set("ciurlaro")
                name.set("Cesare Iurlaro")
                url.set("https://github.com/ciurlaro")
            }
        }
        scm {
            url.set(codexAgentRepositoryUrl)
            connection.set("scm:git:$codexAgentRepositoryUrl.git")
            developerConnection.set("scm:git:ssh://git@github.com/${codexAgentRepositoryUrl.substringAfter("github.com/")}.git")
        }
    }
}

dependencyLocking {
    lockAllConfigurations()
}
