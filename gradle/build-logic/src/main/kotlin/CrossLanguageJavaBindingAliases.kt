private const val CANONICAL_API = "io.github.codex_agent_labs.codexagent.agent/"
private const val ABI_API = "io.github.codex_agent_labs.codexagent.agent."
private const val JVM_API = "io/github/codex_agent_labs/codexagent/agent/"
private const val JAVA_FACADE = JVM_API + "CodexJava"
private const val DESKTOP_FACADE = JVM_API + "runtime/DesktopCodex"
private const val ANDROID_FACADE = JVM_API + "runtime/AndroidCodex"

private val AGENT = jvmApiType("CodexAgent")
private val CONVERSATION = jvmApiType("CodexConversation")
private val HOST = jvmApiType("CodexHost")
private val STRING = "Ljava/lang/String;"

internal val javaBindingExceptionalAliases: List<JavaBindingExceptionalAlias> = listOf(
    // suspend -> CompletableFuture
    suspendAlias(
        "CodexAuthentication", "authenticate", abiApiType("CodexAuthenticationMethod"), "kotlin/Unit",
        parameters(parameter(canonicalApiType("CodexAuthenticationMethod"), default = true)),
        "authenticateAsync", AGENT, jvmApiType("CodexAuthenticationMethod"),
    ),
    suspendAlias("CodexAuthentication", "cancel", "", "kotlin/Unit", parameters(), "cancelAuthenticationAsync", AGENT),
    suspendAlias("CodexAuthentication", "signOut", "", "kotlin/Unit", parameters(), "signOutAsync", AGENT),
    suspendAlias(
        "CodexConnectors", "list", "kotlin.Boolean",
        "kotlin.collections/List<INVARIANT:" + canonicalApiType("AgentConnector") + ">!!",
        parameters(parameter("kotlin/Boolean!!", default = true)), "listConnectorsAsync", AGENT, "Z",
    ),
    suspendAlias(
        "CodexConversations", "delete", abiApiType("ConversationId"), "kotlin/Unit",
        parameters(parameter(canonicalApiType("ConversationId"))),
        "deleteConversationAsync", AGENT, jvmApiType("ConversationId"),
    ),
    suspendAlias(
        "CodexConversations", "list", "",
        "kotlin.collections/List<INVARIANT:" + canonicalApiType("AgentConversationSummary") + ">!!",
        parameters(), "listConversationsAsync", AGENT,
    ),
    suspendAlias(
        "CodexConversations", "open",
        abiParameters(abiApiType("ConversationId", nullable = true), abiApiType("AgentConversationSettings")),
        canonicalApiType("CodexConversation"),
        parameters(
            parameter(canonicalApiType("ConversationId", nullable = true), default = true),
            parameter(canonicalApiType("AgentConversationSettings"), default = true),
        ),
        "openConversationAsync", AGENT, jvmApiType("ConversationId"), jvmApiType("AgentConversationSettings"),
    ),
    suspendAlias(
        "CodexConversations", "read", abiApiType("ConversationId"), canonicalApiType("AgentConversation"),
        parameters(parameter(canonicalApiType("ConversationId"))),
        "readConversationAsync", AGENT, jvmApiType("ConversationId"),
    ),
    suspendAlias(
        "CodexConversations", "rename", abiParameters(abiApiType("ConversationId"), "kotlin.String"), "kotlin/Unit",
        parameters(parameter(canonicalApiType("ConversationId")), parameter("kotlin/String!!")),
        "renameConversationAsync", AGENT, jvmApiType("ConversationId"), STRING,
    ),
    suspendAlias("CodexConversation", "cancelTurn", "", "kotlin/Unit", parameters(), "cancelTurnAsync", CONVERSATION),
    suspendAlias("CodexConversation", "close", "", "kotlin/Unit", parameters(), "closeAsync", CONVERSATION),
    suspendAlias("CodexConversation", "reload", "", "kotlin/Unit", parameters(), "reloadAsync", CONVERSATION),
    suspendAlias(
        "CodexConversation", "runShellCommand", "kotlin.String", "kotlin/Unit",
        parameters(parameter("kotlin/String!!")), "runShellCommandAsync", CONVERSATION, STRING,
    ),
    suspendAlias(
        "CodexConversation", "send", abiApiType("AgentTurnRequest"), "kotlin/Unit",
        parameters(parameter(canonicalApiType("AgentTurnRequest"))),
        "sendAsync", CONVERSATION, jvmApiType("AgentTurnRequest"),
    ),
    suspendAlias(
        "CodexConversation", "send", "kotlin.String", "kotlin/Unit",
        parameters(parameter("kotlin/String!!")), "sendAsync", CONVERSATION, STRING,
    ),
    suspendAlias(
        "CodexHooks", "install", abiParameters("kotlin.String", abiApiType("AgentInstallationScope")),
        canonicalApiType("AgentHook"),
        parameters(parameter("kotlin/String!!"), parameter(canonicalApiType("AgentInstallationScope"))),
        "installHookAsync", AGENT, STRING, jvmApiType("AgentInstallationScope"),
    ),
    suspendAlias("CodexHooks", "list", "", canonicalApiType("AgentHookCatalog"), parameters(), "listHooksAsync", AGENT),
    suspendAlias(
        "CodexHooks", "trust", abiApiType("AgentHook"), "kotlin/Unit",
        parameters(parameter(canonicalApiType("AgentHook"))), "trustHookAsync", AGENT, jvmApiType("AgentHook"),
    ),
    suspendAlias(
        "CodexHooks", "uninstall", abiApiType("AgentHook"), "kotlin/Unit",
        parameters(parameter(canonicalApiType("AgentHook"))), "uninstallHookAsync", AGENT, jvmApiType("AgentHook"),
    ),
    suspendAlias("CodexHost", "close", "", "kotlin/Unit", parameters(), "closeAsync", HOST),
    suspendAlias(
        "CodexHost", "selectWorkspace", abiApiType("CodexWorkspaceSelection"), "kotlin/Unit",
        parameters(parameter(canonicalApiType("CodexWorkspaceSelection"))),
        "selectWorkspaceAsync", HOST, jvmApiType("CodexWorkspaceSelection"),
    ),
    suspendAlias("CodexHost", "start", "", "kotlin/Unit", parameters(), "startAsync", HOST),
    genericSuspendAlias(
        "CodexIntegrationAuthorization", "authorize",
        "authorize(0:0){0§<" + ABI_API + "AgentIntegration>}[0]", "kotlin/Unit",
        parameters(parameter("^A1")), "authorizeIntegrationAsync", AGENT, jvmApiType("AgentIntegration"),
    ),
    suspendAlias(
        "CodexIntegrationAuthorization", "cancel", "", "kotlin/Unit", parameters(),
        "cancelIntegrationAuthorizationAsync", AGENT,
    ),
    suspendAlias(
        "CodexInteractions", "openUrl", abiApiType("AgentPendingElicitation"), "kotlin/Unit",
        parameters(parameter(canonicalApiType("AgentPendingElicitation"))),
        "openElicitationUrlAsync", AGENT, jvmApiType("AgentPendingElicitation"),
    ),
    suspendAlias(
        "CodexInteractions", "resolve",
        abiParameters(abiApiType("AgentPendingApproval"), abiApiType("AgentApprovalDecision")), "kotlin/Unit",
        parameters(
            parameter(canonicalApiType("AgentPendingApproval")),
            parameter(canonicalApiType("AgentApprovalDecision")),
        ),
        "resolveApprovalAsync", AGENT, jvmApiType("AgentPendingApproval"), jvmApiType("AgentApprovalDecision"),
    ),
    suspendAlias(
        "CodexInteractions", "resolve",
        abiParameters(abiApiType("AgentPendingElicitation"), abiApiType("AgentElicitationResponse")), "kotlin/Unit",
        parameters(
            parameter(canonicalApiType("AgentPendingElicitation")),
            parameter(canonicalApiType("AgentElicitationResponse")),
        ),
        "resolveElicitationAsync", AGENT, jvmApiType("AgentPendingElicitation"), jvmApiType("AgentElicitationResponse"),
    ),
    suspendAlias(
        "CodexMcpServers", "add", abiApiType("AgentMcpServerConfiguration"), canonicalApiType("AgentMcpServer"),
        parameters(parameter(canonicalApiType("AgentMcpServerConfiguration"))),
        "addMcpServerAsync", AGENT, jvmApiType("AgentMcpServerConfiguration"),
    ),
    suspendAlias(
        "CodexMcpServers", "list", "",
        "kotlin.collections/List<INVARIANT:" + canonicalApiType("AgentMcpServer") + ">!!",
        parameters(), "listMcpServersAsync", AGENT,
    ),
    suspendAlias(
        "CodexMcpServers", "remove", abiApiType("AgentMcpServer"), "kotlin/Unit",
        parameters(parameter(canonicalApiType("AgentMcpServer"))),
        "removeMcpServerAsync", AGENT, jvmApiType("AgentMcpServer"),
    ),
    suspendAlias(
        "CodexModels", "list", "",
        "kotlin.collections/List<INVARIANT:" + canonicalApiType("AgentModel") + ">!!",
        parameters(), "listModelsAsync", AGENT,
    ),
    suspendAlias(
        "CodexModels", "resolveEffort", abiParameters(abiApiType("AgentModel"), abiApiType("AgentResolution")),
        "kotlin/String!!",
        parameters(
            parameter(canonicalApiType("AgentModel")),
            parameter(canonicalApiType("AgentResolution"), default = true),
        ),
        "resolveEffortAsync", AGENT, jvmApiType("AgentModel"), jvmApiType("AgentResolution"),
    ),
    suspendAlias(
        "CodexModels", "resolveServiceTier",
        abiParameters(abiApiType("AgentModel"), abiApiType("AgentResolution")),
        canonicalApiType("AgentServiceTier", nullable = true),
        parameters(
            parameter(canonicalApiType("AgentModel")),
            parameter(canonicalApiType("AgentResolution"), default = true),
        ),
        "resolveServiceTierAsync", AGENT, jvmApiType("AgentModel"), jvmApiType("AgentResolution"),
    ),
    suspendAlias(
        "CodexModels", "resolve", abiApiType("AgentResolution"), canonicalApiType("AgentModel"),
        parameters(parameter(canonicalApiType("AgentResolution"), default = true)),
        "resolveModelAsync", AGENT, jvmApiType("AgentResolution"),
    ),
    suspendAlias(
        "CodexPlugins", "install", abiApiType("AgentPluginReference"), canonicalApiType("AgentPluginInstallResult"),
        parameters(parameter(canonicalApiType("AgentPluginReference"))),
        "installPluginAsync", AGENT, jvmApiType("AgentPluginReference"),
    ),
    suspendAlias(
        "CodexPlugins", "list", "kotlin.Boolean", canonicalApiType("AgentPluginCatalog"),
        parameters(parameter("kotlin/Boolean!!", default = true)), "listPluginsAsync", AGENT, "Z",
    ),
    suspendAlias(
        "CodexPlugins", "read", abiApiType("AgentPluginReference"), canonicalApiType("AgentPluginDetail"),
        parameters(parameter(canonicalApiType("AgentPluginReference"))),
        "readPluginAsync", AGENT, jvmApiType("AgentPluginReference"),
    ),
    suspendAlias(
        "CodexPlugins", "uninstall", abiApiType("AgentPluginReference"), "kotlin/Unit",
        parameters(parameter(canonicalApiType("AgentPluginReference"))),
        "uninstallPluginAsync", AGENT, jvmApiType("AgentPluginReference"),
    ),
    suspendAlias(
        "CodexSkills", "install", abiParameters("kotlin.String", abiApiType("AgentInstallationScope")),
        canonicalApiType("AgentSkill"),
        parameters(parameter("kotlin/String!!"), parameter(canonicalApiType("AgentInstallationScope"))),
        "installSkillAsync", AGENT, STRING, jvmApiType("AgentInstallationScope"),
    ),
    suspendAlias(
        "CodexSkills", "list", "kotlin.Boolean", canonicalApiType("AgentSkillCatalog"),
        parameters(parameter("kotlin/Boolean!!", default = true)), "listSkillsAsync", AGENT, "Z",
    ),
    suspendAlias(
        "CodexSkills", "read", abiParameters("kotlin.String", "kotlin.Long"), canonicalApiType("AgentSkillChunk"),
        parameters(parameter("kotlin/String!!"), parameter("kotlin/Long!!", default = true)),
        "readSkillAsync", AGENT, STRING, "J",
    ),
    suspendAlias(
        "CodexSkills", "uninstall", abiApiType("AgentSkill"), "kotlin/Unit",
        parameters(parameter(canonicalApiType("AgentSkill"))), "uninstallSkillAsync", AGENT, jvmApiType("AgentSkill"),
    ),

    // Companion factories -> true outer static Java methods
    staticAlias(
        "AgentElicitationResponse.Companion", "cancel", "", canonicalApiType("AgentElicitationResponse"),
        parameters(), "AgentElicitationResponse",
    ),
    staticAlias(
        "AgentElicitationResponse.Companion", "decline", "", canonicalApiType("AgentElicitationResponse"),
        parameters(), "AgentElicitationResponse",
    ),
    staticAlias(
        "CodexAuthorizationUrl.Companion", "chatGpt", "kotlin.String", canonicalApiType("CodexAuthorizationUrl"),
        parameters(parameter("kotlin/String!!")), "CodexAuthorizationUrl", STRING,
    ),
    staticAlias(
        "CodexAuthorizationUrl.Companion", "external", "kotlin.String", canonicalApiType("CodexAuthorizationUrl"),
        parameters(parameter("kotlin/String!!")), "CodexAuthorizationUrl", STRING,
    ),

    // StateFlow -> current value plus AutoCloseable observation
    stateAlias(
        "CodexAuthentication", "isAuthenticated", "kotlin/Boolean!!",
        "isAuthenticated", "Z", "observeAuthenticated", AGENT,
    ),
    stateAlias(
        "CodexAuthentication", "isAuthenticating", "kotlin/Boolean!!",
        "isAuthenticating", "Z", "observeAuthenticating", AGENT,
    ),
    stateAlias(
        "CodexAuthentication", "state", canonicalApiType("AgentAuthenticationState"),
        "currentAuthenticationState", jvmApiType("AgentAuthenticationState"), "observeAuthenticationState", AGENT,
    ),
    stateAlias(
        "CodexConversations", "active", canonicalApiType("CodexConversation", nullable = true),
        "activeConversation", "Ljava/util/Optional;", "observeActiveConversation", AGENT,
    ),
    stateAlias(
        "CodexConversation", "activeTurnProgress", canonicalApiType("AgentTurnProgress", nullable = true),
        "currentTurnProgress", "Ljava/util/Optional;", "observeTurnProgress", CONVERSATION,
    ),
    stateAlias(
        "CodexConversation", "canCancelTurn", "kotlin/Boolean!!",
        "canCancelTurn", "Z", "observeCanCancelTurn", CONVERSATION,
    ),
    stateAlias(
        "CodexConversation", "canReload", "kotlin/Boolean!!",
        "canReload", "Z", "observeCanReload", CONVERSATION,
    ),
    stateAlias(
        "CodexConversation", "canRunShellCommand", "kotlin/Boolean!!",
        "canRunShellCommand", "Z", "observeCanRunShellCommand", CONVERSATION,
    ),
    stateAlias(
        "CodexConversation", "canStartTurn", "kotlin/Boolean!!",
        "canStartTurn", "Z", "observeCanStartTurn", CONVERSATION,
    ),
    stateAlias(
        "CodexConversation", "currentMessages",
        "kotlin.collections/List<INVARIANT:" + canonicalApiType("AgentMessage") + ">!!",
        "currentMessages", "Ljava/util/List;", "observeMessages", CONVERSATION,
    ),
    stateAlias(
        "CodexConversation", "isTurnActive", "kotlin/Boolean!!",
        "isTurnActive", "Z", "observeTurnActive", CONVERSATION,
    ),
    stateAlias(
        "CodexConversation", "state", canonicalApiType("AgentConversationState"),
        "currentConversationState", jvmApiType("AgentConversationState"), "observeConversation", CONVERSATION,
    ),
    stateAlias(
        "CodexHost", "lifecycleState", canonicalApiType("CodexHostState"),
        "currentLifecycleState", jvmApiType("CodexHostState"), "observeLifecycle", HOST,
    ),
    stateAlias(
        "CodexIntegrationAuthorization", "active", canonicalApiType("AgentIntegration", nullable = true),
        "activeIntegrationAuthorization", "Ljava/util/Optional;", "observeActiveIntegrationAuthorization", AGENT,
    ),
    stateAlias(
        "CodexIntegrationAuthorization", "isAuthorizing", "kotlin/Boolean!!",
        "isIntegrationAuthorizing", "Z", "observeIntegrationAuthorizing", AGENT,
    ),
    stateAlias(
        "CodexIntegrationAuthorization", "state", canonicalApiType("AgentIntegrationAuthorizationState"),
        "currentIntegrationAuthorizationState", jvmApiType("AgentIntegrationAuthorizationState"),
        "observeIntegrationAuthorizationState", AGENT,
    ),
    stateAlias(
        "CodexInteractions", "approvals",
        "kotlin.collections/List<INVARIANT:" + canonicalApiType("AgentPendingApproval") + ">!!",
        "currentApprovals", "Ljava/util/List;", "observeApprovals", AGENT,
    ),
    stateAlias(
        "CodexInteractions", "elicitations",
        "kotlin.collections/List<INVARIANT:" + canonicalApiType("AgentPendingElicitation") + ">!!",
        "currentElicitations", "Ljava/util/List;", "observeElicitations", AGENT,
    ),
    stateAlias(
        "CodexInteractions", "state", canonicalApiType("AgentInteractionState"),
        "currentInteractionState", jvmApiType("AgentInteractionState"), "observeInteractionState", AGENT,
    ),

    // The canonical SPI constructor projects to platform-native factories.
    hostFactoryAlias(),
)

private fun suspendAlias(
    owner: String,
    name: String,
    abiParameters: String,
    returnType: String,
    parameters: String,
    javaName: String,
    vararg javaParameters: String,
): JavaSuspendBindingAlias = JavaSuspendBindingAlias(
    capabilityKey = canonicalFunctionKey(owner, name, "$name($abiParameters){}[0]", returnType, parameters),
    futureMethod = javaMethod(JAVA_FACADE, javaName, futureDescriptor(*javaParameters)),
)

private fun genericSuspendAlias(
    owner: String,
    name: String,
    abiSignature: String,
    returnType: String,
    parameters: String,
    javaName: String,
    vararg javaParameters: String,
): JavaSuspendBindingAlias = JavaSuspendBindingAlias(
    capabilityKey = canonicalFunctionKey(owner, name, abiSignature, returnType, parameters),
    futureMethod = javaMethod(JAVA_FACADE, javaName, futureDescriptor(*javaParameters)),
)

private fun staticAlias(
    owner: String,
    name: String,
    abiParameters: String,
    returnType: String,
    parameters: String,
    outerOwner: String,
    vararg javaParameters: String,
): JavaStaticBindingAlias = JavaStaticBindingAlias(
    capabilityKey = canonicalFunctionKey(
        owner,
        name,
        "$name($abiParameters){}[0]",
        returnType,
        parameters,
        suspend = false,
    ),
    staticMethod = javaMethod(
        JVM_API + outerOwner,
        name,
        javaParameters.joinToString(separator = "", prefix = "(", postfix = ")" + jvmApiType(outerOwner)),
    ),
)

private fun stateAlias(
    owner: String,
    name: String,
    stateType: String,
    currentName: String,
    currentReturn: String,
    observeName: String,
    receiver: String,
): JavaStateFlowBindingAlias = JavaStateFlowBindingAlias(
    capabilityKey = "common|owner=$CANONICAL_API$owner|kind=property|abi=$CANONICAL_API$owner.$name|" +
        "{}$name[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:$stateType>!!",
    currentMethod = javaMethod(JAVA_FACADE, currentName, "($receiver)$currentReturn"),
    observeMethod = javaMethod(
        JAVA_FACADE,
        observeName,
        "($receiver" +
            "Ljava/util/concurrent/Executor;Ljava/util/function/Consumer;)" +
            jvmApiType("CodexJavaObservation"),
    ),
)

private fun hostFactoryAlias(): JavaHostFactoryBindingAlias = JavaHostFactoryBindingAlias(
    capabilityKey = "common|owner=" + CANONICAL_API + "CodexHost|kind=constructor|abi=" +
        CANONICAL_API + "CodexHost.<init>|<init>(" + ABI_API + "CodexPlatform;" + ABI_API +
        "CodexClientInfo){}[0]|return=" + CANONICAL_API + "CodexHost|suspend=false|parameters=" +
        parameters(parameter(canonicalApiType("CodexPlatform")), parameter(canonicalApiType("CodexClientInfo"))),
    desktopFactory = javaMethod(
        DESKTOP_FACADE,
        "createHost",
        "(Ljava/nio/file/Path;Ljava/nio/file/Path;" + jvmApiType("CodexClientInfo") + ")" + HOST,
    ),
    androidFactory = javaMethod(
        ANDROID_FACADE,
        "createHost",
        "(Landroid/content/Context;" + jvmApiType("CodexClientInfo") + ")" + HOST,
    ),
)

private fun canonicalFunctionKey(
    owner: String,
    name: String,
    abiSignature: String,
    returnType: String,
    parameters: String,
    suspend: Boolean = true,
): String = "common|owner=$CANONICAL_API$owner|kind=function|abi=$CANONICAL_API$owner.$name|" +
    "$abiSignature|return=$returnType|suspend=$suspend|parameters=$parameters"

private fun canonicalApiType(name: String, nullable: Boolean = false): String =
    CANONICAL_API + name + if (nullable) "?" else "!!"

private fun abiApiType(name: String, nullable: Boolean = false): String =
    ABI_API + name + if (nullable) "?" else ""

private fun jvmApiType(name: String): String = "L$JVM_API$name;"

private fun abiParameters(vararg types: String): String = types.joinToString(separator = ";")

private fun parameter(type: String, default: Boolean = false): String =
    "REGULAR:$type:default=$default:vararg=false"

private fun parameters(vararg parameters: String): String = parameters.joinToString(
    separator = ",",
    prefix = "[",
    postfix = "]",
)

private fun futureDescriptor(vararg parameters: String): String =
    parameters.joinToString(separator = "", prefix = "(", postfix = ")Ljava/util/concurrent/CompletableFuture;")

private fun javaMethod(owner: String, name: String, descriptor: String): JavaJvmSymbol =
    JavaJvmSymbol(JavaJvmSymbolKind.METHOD, owner, name, descriptor)
