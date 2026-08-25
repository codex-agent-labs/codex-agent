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
        actual = actual.replace(
            "type Nullable<T> = T | null | undefined\n",
            """type Nullable<T> = T | null | undefined;
export type CodexHostStatus = "new" | "restoring" | "workspace_required" | "preparing" | "ready" | "failed" | "closed";
$canonicalEnumDeclarations
export type CodexAuthenticationMethod = "chatgpt_browser" | "chatgpt_device_code" | "api_key";
""",
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
            "    get recoverable(): boolean;\n}\nexport declare class CodexWorkspace",
            "    get recoverable(): boolean;\n    readonly cause?: unknown;\n}\nexport declare class CodexWorkspace",
        ).replace(
            "    get status(): string;\n    get pendingSignInUrl(): Nullable<string>;",
            "    get status(): CodexAuthenticationStatus;\n    get pendingSignInUrl(): Nullable<string>;",
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
