package io.github.codex_agent_labs.codexagent.agent

import java.nio.file.Files
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertSame
import kotlin.test.assertTrue
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import okio.FileSystem
import okio.Path
import okio.Path.Companion.toPath

class OwnedCodexResourcesTest {
    @Test
    fun publicOperationBoundaryPreservesPartialChangeFailures(): Unit = runBlocking {
        val failure = AgentResourcePartialChangeException("partial")
        assertSame(
            failure,
            assertFailsWith<AgentResourcePartialChangeException> {
                codexOperation { throw failure }
            },
        )
    }

    @CoversApi(
        "api-v1:AgentHook#constructor:<init>#sha256:bc7133b8e642e459f23fb12e3431eb937fe22013f759dec3ea906eb8bf73723b",
        "api-v1:AgentHook#property:canUninstall#sha256:82caa3582937d01e5a40828c3b810ae5343bf80b85ced63586db7c7a72e99f09",
        "api-v1:AgentHook#property:key#sha256:f689f8d4661a7c41fa51087caf5326542dca60d026c1f6bdc6e2454e3f16ef56",
        "api-v1:AgentHook#property:origin#sha256:1d6b2ccee4b43fc189b9c7cf77bfae891465e8667853757f297b79283eefcb6b",
        "api-v1:AgentHook#property:sourcePath#sha256:1712bed85f459f702eceffc98de764db4d6117de706a3973cbc584b68746d247",
        "api-v1:AgentHookCatalog#constructor:<init>#sha256:1616af69893f519e19ec426baab646b027556277d0d3ea8b1ba26ea51db8ed84",
        "api-v1:AgentHookCatalog#property:hooks#sha256:d1db6832eb133670200512ee8f8c477ff82ebbb4a986d29e6b9a97b3a524e120",
        "api-v1:AgentInstallationScope#enum-entry:User#sha256:cd5b6f8bd50641eae4ee39e06fe302b2fb1a13d923bfc782dd3edea4c69bf4a6",
        "api-v1:AgentResourceOrigin#enum-entry:USER#sha256:12f676828b1a99b2314fa0da2043dd23f3ff80380323a3837f611dea98be0a1c",
        "api-v1:AgentSkill#constructor:<init>#sha256:401f7be29c24a9cb394931ea7cbf08ae0fce2cbce42be3aa29ca2f2daca2eab5",
        "api-v1:AgentSkill#property:canUninstall#sha256:5384626f9ea6fa8c5bfac0a19b849b510e24a8de6c39a1efdf8e69bddc1397a3",
        "api-v1:AgentSkill#property:origin#sha256:4e38bd43e55b8cbd3201b14232e9ffa7d2467d20417bd2de491bcee93ac47f9c",
        "api-v1:AgentSkill#property:path#sha256:46050951700e7e9f0d2790556cef18fc906e51ffa4e06d3ea36dca678ba95d69",
        "api-v1:AgentSkillCatalog#constructor:<init>#sha256:325713af43220c68c66a907c43cffa10f4bdea5e4351138f60ec7babaa6c6031",
        "api-v1:AgentSkillScope#enum-entry:USER#sha256:17ba5b299a98ffa7081f9d9e23d1e4978c0d0bac57311c33f71a670baaa8e65c",
        "api-v1:CodexHooks#function:install#sha256:f9af369f654d65799c2f9596224a564b9829998ba5b91488824e1aaba83ee1c1",
        "api-v1:CodexHooks#function:list#sha256:db3421bf5971be1781cbfadc619ccc6002698ed50c67980cac0ee536badf42b6",
        "api-v1:CodexHooks#function:trust#sha256:eee20ff92e97634e3a8efe49358c0c34235ead581658414b74a6362f32eaf5cb",
        "api-v1:CodexHooks#function:uninstall#sha256:4cde717fac76ff698bdf15ffad45b61dd8023fce56552ae8ba01191cd6b6d7fb",
        "api-v1:CodexHooks#property:isAvailable#sha256:4c9cad534c3bfe273d6cfff7289ae2a3d36ba56ead497bbcb3b19eeb07e0141f",
        "api-v1:CodexSkills#function:install#sha256:50a8f5dcefb659f569deb1afead95898a90ade7b1b19b9acf653ae053f6ca5b0",
        "api-v1:CodexSkills#function:uninstall#sha256:648830f48e3cbe1399adccb7ac3a8e88757b4bef927a496e2ba05cf497858b16",
        "api-v1:CodexSkills#property:isAvailable#sha256:3691b0d3ad9ee63aa4d0cc4213ccb5ebc53e97bddbabc5f183a7af11426458f2",
    )
    @Test
    fun installsAndUninstallsUserScopedSkillAndHook(): Unit = withTemporaryRoot { root, store ->
        val skillSource = root / "sources" / "user-skill"
        val hookSource = root / "sources" / "user-hook"
        val userSkills = root / "codex" / "skills"
        val userHooks = root / "codex" / "hooks.json"
        store.createDirectories(skillSource)
        store.writeUtf8Atomically(
            skillSource / "SKILL.md",
            "---\nname: user-skill\ndescription: User skill\n---\n",
        )
        store.createDirectories(hookSource)
        store.writeUtf8Atomically(
            hookSource / "hooks.json",
            """{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"true"}]}]}}""",
        )
        val skillManifest = userSkills / "user-skill" / "SKILL.md"
        var trustedHook: Pair<String, String>? = null
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "skills/list" -> server.respond(message.id, buildJsonObject {
                    putJsonArray("data") {
                        add(buildJsonObject {
                            put("cwd", "/workspace")
                            putJsonArray("errors") {}
                            putJsonArray("skills") {
                                if (store.metadata(skillManifest)?.isRegularFile == true) {
                                    add(buildJsonObject {
                                        put("name", "user-skill")
                                        put("description", "User skill")
                                        put("enabled", true)
                                        put("path", skillManifest.toString())
                                        put("scope", "user")
                                    })
                                }
                            }
                        })
                    }
                })
                "hooks/list" -> server.respond(message.id, buildJsonObject {
                    putJsonArray("data") {
                        add(buildJsonObject {
                            put("cwd", "/workspace")
                            putJsonArray("warnings") {}
                            putJsonArray("errors") {}
                            putJsonArray("hooks") {
                                val hookIsInstalled = store.metadata(userHooks)?.isRegularFile == true &&
                                    store.readUtf8(userHooks).contains("\"Stop\"")
                                if (hookIsInstalled) {
                                    add(buildJsonObject {
                                        put("currentHash", "hash")
                                        put("displayOrder", 0)
                                        put("enabled", true)
                                        put("eventName", "stop")
                                        put("handlerType", "command")
                                        put("isManaged", false)
                                        put("key", "user-hook")
                                        put("source", "user")
                                        put("sourcePath", userHooks.toString())
                                        put("timeoutSec", 10)
                                        put("trustStatus", "untrusted")
                                        put("command", "true")
                                    })
                                }
                            }
                        })
                    }
                })
                "config/batchWrite" -> {
                    val value = message.params.requiredArray("edits").single().jsonObject.requiredObject("value")
                    val (key, state) = value.entries.single()
                    trustedHook = key to state.jsonObject.requiredString("trusted_hash")
                    server.respond(message.id, buildJsonObject {
                        put("filePath", "/codex/config.toml")
                        put("status", "ok")
                        put("version", "1")
                    })
                }
            }
        }
        val client = CodexAgentClient(
            runtimeFactory = { runtime },
            clientInfo = CodexClientInfo("owned_resource_test", "Owned Resource Test", "test"),
            requestTimeoutMillis = 1_000,
            installationRoots = CodexInstallationRoots(
                userSkillsRoot = userSkills,
                userHooksFile = userHooks,
            ),
            fileSystem = store,
        )

        runBlocking {
            val agent = CodexAgent(
                workspace = CodexWorkspace("/workspace"),
                workingDirectory = "/workspace",
                features = setOf(CodexRuntimeFeature.SKILLS, CodexRuntimeFeature.HOOKS),
                client = client,
                parentScope = this,
                authorizationBrowser = CodexAuthorizationBrowser { CodexAuthorizationPresentation.None },
            )
            try {
                agent.start()
                assertTrue(agent.skills.isAvailable)
                assertTrue(agent.hooks.isAvailable)
                assertTrue(agent.hooks.list().hooks.isEmpty())

                val skill = agent.skills.install(skillSource.toString(), AgentInstallationScope.User)
                val hook = agent.hooks.install(hookSource.toString(), AgentInstallationScope.User)

                assertTrue(skill.canUninstall)
                assertTrue(hook.canUninstall)
                assertEquals(AgentResourceOrigin.USER, skill.origin)
                assertEquals(AgentResourceOrigin.USER, hook.origin)
                assertEquals(hook.key, agent.hooks.list().hooks.single().key)
                assertTrue(hook.canTrust)
                agent.hooks.trust(hook)
                assertEquals("user-hook" to "hash", trustedHook)

                agent.skills.uninstall(skill)
                agent.hooks.uninstall(hook)
            } finally {
                agent.close()
            }
        }
        assertEquals(null, store.metadata(userSkills / "user-skill"))
        assertEquals(null, store.metadata(userHooks.parent!! / ".codex-agent-hooks" / "user-hook"))
    }

    @CoversApi(
        "api-v1:AgentInstallationScope#enum-entry:Workspace#sha256:b0afc23065bb7d19f402e985207b0a67fda85f69dd6dcc9469085769d06341da",
        "api-v1:AgentSkillScope#enum-entry:REPO#sha256:3bf8d21dd6f8a99b8453e69e3c864a99e8be60999906c31caea872add92feb30",
    )
    @Test
    fun installsDiscoversAndUninstallsOwnedSkill(): Unit = withTemporaryRoot { root, store ->
        val source = root / "source" / "review"
        val skills = root / "workspace" / ".agents" / "skills"
        store.createDirectories(source / "scripts")
        store.writeUtf8Atomically(
            source / "SKILL.md",
            """---
                |name: review
                |description: Review changes
                |---
                |Review the requested changes.
                |
            """.trimMargin(),
        )
        store.writeUtf8Atomically(source / "scripts" / "review.sh", "echo review\n")
        val resources = resources(store, workspaceSkillsRoot = skills)

        val installed = runBlocking {
            resources.installSkill(source.toString(), AgentInstallationScope.Workspace) {
                val manifest = skills / "review" / "SKILL.md"
                AgentSkillCatalog(
                    listOf(AgentSkill("review", "Review", "Review changes", manifest.toString(), AgentSkillScope.REPO, true)),
                )
            }
        }

        assertTrue(installed.canUninstall)
        assertTrue(store.isRegularFile(skills / "review" / "scripts" / "review.sh"))
        assertTrue(resources.ownsSkill(installed))
        store.writeUtf8Atomically(skills / "review" / "user-added.txt", "keep\n")
        assertFailsWith<IllegalArgumentException> {
            runBlocking { resources.uninstallSkill(installed) { AgentSkillCatalog(emptyList()) } }
        }
        store.delete(skills / "review" / "user-added.txt")
        runBlocking {
            resources.uninstallSkill(installed) { AgentSkillCatalog(emptyList()) }
        }
        assertEquals(null, store.metadata(skills / "review"))
    }

    @Test
    fun rejectsMalformedSymlinkedAndCollidingSkillBundles(): Unit = withTemporaryRoot { root, store ->
        val skills = root / "skills"
        val malformed = root / "malformed"
        store.createDirectories(malformed)
        store.writeUtf8Atomically(malformed / "SKILL.md", "# Missing frontmatter\n")
        val resources = resources(store, workspaceSkillsRoot = skills)

        assertFailsWith<IllegalArgumentException> {
            runBlocking {
                resources.installSkill(malformed.toString(), AgentInstallationScope.Workspace) {
                    AgentSkillCatalog(emptyList())
                }
            }
        }

        val source = root / "valid"
        store.createDirectories(source)
        store.writeUtf8Atomically(source / "SKILL.md", "---\nname: valid\ndescription: Valid\n---\n")
        Files.createSymbolicLink(
            java.nio.file.Path.of((source / "linked").toString()),
            java.nio.file.Path.of((source / "SKILL.md").toString()),
        )
        assertFailsWith<IllegalArgumentException> {
            runBlocking {
                resources.installSkill(source.toString(), AgentInstallationScope.Workspace) {
                    AgentSkillCatalog(emptyList())
                }
            }
        }
        store.delete(source / "linked")
        store.createDirectories(skills / "valid")
        assertFailsWith<IllegalArgumentException> {
            runBlocking {
                resources.installSkill(source.toString(), AgentInstallationScope.Workspace) {
                    AgentSkillCatalog(emptyList())
                }
            }
        }

        val unowned = AgentSkill(
            "valid",
            "Valid",
            "Valid",
            (skills / "valid" / "SKILL.md").toString(),
            AgentSkillScope.REPO,
            true,
        )
        assertFailsWith<IllegalArgumentException> {
            runBlocking { resources.uninstallSkill(unowned) { AgentSkillCatalog(emptyList()) } }
        }
    }

    @Test
    fun rejectsTraversalEntriesFromTheSourceFileSystem(): Unit = withTemporaryRoot { root, delegate ->
        val source = root / "traversal"
        val skills = root / "skills"
        delegate.createDirectories(source)
        delegate.writeUtf8Atomically(source / "SKILL.md", "---\nname: traversal\ndescription: Traversal\n---\n")
        val malicious = object : AgentFileStore by delegate {
            override fun list(path: Path): List<Path> = if (path == source) {
                listOf("${source}/..".toPath(normalize = false))
            } else {
                delegate.list(path)
            }
        }

        assertFailsWith<IllegalArgumentException> {
            runBlocking {
                resources(malicious, workspaceSkillsRoot = skills)
                    .installSkill(source.toString(), AgentInstallationScope.Workspace) {
                        AgentSkillCatalog(emptyList())
                    }
            }
        }
        assertEquals(null, delegate.metadata(skills / "traversal"))
    }

    @Test
    fun rejectsMissingInstallationRootBelowSymlinkWithoutMutation(): Unit = withTemporaryRoot { root, store ->
        val source = root / "source" / "safe"
        val outside = root / "outside"
        val link = root / "linked"
        store.createDirectories(source)
        store.writeUtf8Atomically(source / "SKILL.md", "---\nname: safe\ndescription: Safe\n---\n")
        store.createDirectories(outside)
        Files.createSymbolicLink(
            java.nio.file.Path.of(link.toString()),
            java.nio.file.Path.of(outside.toString()),
        )
        val resources = resources(store, workspaceSkillsRoot = link / "missing" / "skills")

        assertFailsWith<IllegalArgumentException> {
            runBlocking {
                resources.installSkill(source.toString(), AgentInstallationScope.Workspace) {
                    AgentSkillCatalog(emptyList())
                }
            }
        }
        assertEquals(null, store.metadata(outside / "missing"))
    }

    @Test
    fun rollsBackInstalledSkillWhenCatalogDiscoveryFails(): Unit = withTemporaryRoot { root, store ->
        val source = root / "rollback"
        val skills = root / "skills"
        store.createDirectories(source)
        store.writeUtf8Atomically(source / "SKILL.md", "---\nname: rollback\ndescription: Rollback\n---\n")
        val resources = resources(store, workspaceSkillsRoot = skills)

        assertFailsWith<AgentResourceInstallationException> {
            runBlocking {
                resources.installSkill(source.toString(), AgentInstallationScope.Workspace) {
                    error("injected discovery failure")
                }
            }
        }
        assertEquals(null, store.metadata(skills / "rollback"))
    }

    @Test
    fun successfulSkillAndHookRollbacksPreserveCancellation(): Unit = withTemporaryRoot { root, store ->
        val skillSource = root / "sources" / "cancel-skill"
        val hookSource = root / "sources" / "cancel-hook"
        val skills = root / "skills"
        val hooks = root / "hooks.json"
        val originalHooks = "{\"hooks\":{}}\n"
        store.createDirectories(skillSource)
        store.writeUtf8Atomically(
            skillSource / "SKILL.md",
            "---\nname: cancel-skill\ndescription: Cancellation\n---\n",
        )
        store.createDirectories(hookSource)
        store.writeUtf8Atomically(
            hookSource / "hooks.json",
            """{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"true"}]}]}}""",
        )
        store.writeUtf8Atomically(hooks, originalHooks)
        val resources = resources(store, workspaceSkillsRoot = skills, workspaceHooksFile = hooks)

        val skillCancellation = CancellationException("cancel skill discovery")
        assertSame(skillCancellation, assertFailsWith<CancellationException> {
            runBlocking {
                resources.installSkill(skillSource.toString(), AgentInstallationScope.Workspace) {
                    throw skillCancellation
                }
            }
        })
        assertEquals(null, store.metadata(skills / "cancel-skill"))

        val hookCancellation = CancellationException("cancel hook discovery")
        var reloads = 0
        assertSame(hookCancellation, assertFailsWith<CancellationException> {
            runBlocking {
                resources.installHook(hookSource.toString(), AgentInstallationScope.Workspace) {
                    if (reloads++ == 0) AgentHookCatalog(emptyList()) else throw hookCancellation
                }
            }
        })
        assertEquals(originalHooks, store.readUtf8(hooks))
        assertEquals(null, store.metadata(hooks.parent!! / ".codex-agent-hooks" / "cancel-hook"))
    }

    @Test
    fun mergesOneHookCopiesAssetsAndRemovesOnlyOwnedEntry(): Unit = withTemporaryRoot { root, store ->
        val source = root / "source" / "lint"
        val target = root / "workspace" / ".codex" / "hooks.json"
        store.createDirectories(source / "scripts")
        store.writeUtf8Atomically(source / "scripts" / "lint.sh", "echo lint\n")
        store.writeUtf8Atomically(
            source / "hooks.json",
            """{
                |  "hooks": {
                |    "PreToolUse": [{
                |      "matcher": "Shell",
                |      "hooks": [{"type":"command","command":"sh scripts/lint.sh"}]
                |    }]
                |  }
                |}
            """.trimMargin(),
        )
        store.writeUtf8Atomically(
            target,
            """{"description":"keep","hooks":{"Stop":[{"hooks":[{"type":"agent"}]}]}}
            """,
        )
        val resources = resources(store, workspaceHooksFile = target)
        var reload = 0

        val installed = runBlocking {
            resources.installHook(source.toString(), AgentInstallationScope.Workspace) {
                if (reload++ == 0) AgentHookCatalog(emptyList())
                else AgentHookCatalog(listOf(hook("installed", target)))
            }
        }

        val installedConfig = store.readUtf8(target)
        assertTrue(installedConfig.contains("\"description\": \"keep\""))
        assertTrue(installedConfig.contains((target.parent!! / ".codex-agent-hooks" / "lint" / "scripts" / "lint.sh").toString()))
        assertTrue(resources.ownsHook(installed))

        runBlocking {
            resources.uninstallHook(installed) { AgentHookCatalog(emptyList()) }
        }
        val remaining = store.readUtf8(target)
        assertTrue(remaining.contains("\"Stop\""))
        assertFalse(remaining.contains("\"PreToolUse\""))
        assertEquals(null, store.metadata(target.parent!! / ".codex-agent-hooks" / "lint"))
    }

    @Test
    fun rejectsUnsafeHooksAndRollsBackAValidUndiscoveredHook(): Unit = withTemporaryRoot { root, store ->
        val malformed = root / "malformed-hook"
        val source = root / "rollback-hook"
        val target = root / "workspace" / ".codex" / "hooks.json"
        val original = "{\"description\":\"keep\",\"hooks\":{}}\n"
        store.createDirectories(malformed)
        store.writeUtf8Atomically(malformed / "hooks.json", """{"hooks":{"Unknown":[]}}""")
        store.createDirectories(source)
        store.writeUtf8Atomically(
            source / "hooks.json",
            """{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"true"}]}]}}""",
        )
        store.writeUtf8Atomically(target, original)
        val resources = resources(store, workspaceHooksFile = target)

        assertFailsWith<IllegalArgumentException> {
            runBlocking {
                resources.installHook(malformed.toString(), AgentInstallationScope.Workspace) {
                    AgentHookCatalog(emptyList())
                }
            }
        }
        assertFailsWith<IllegalArgumentException> {
            runBlocking { resources.uninstallHook(hook("unowned", target)) { AgentHookCatalog(emptyList()) } }
        }

        val collision = target.parent!! / ".codex-agent-hooks" / "rollback-hook"
        store.createDirectories(collision)
        assertFailsWith<IllegalArgumentException> {
            runBlocking {
                resources.installHook(source.toString(), AgentInstallationScope.Workspace) {
                    AgentHookCatalog(emptyList())
                }
            }
        }
        store.deleteRecursively(collision)

        var reload = 0
        assertFailsWith<AgentResourceInstallationException> {
            runBlocking {
                resources.installHook(source.toString(), AgentInstallationScope.Workspace) {
                    if (reload++ == 0) AgentHookCatalog(emptyList()) else error("injected discovery failure")
                }
            }
        }
        assertEquals(original, store.readUtf8(target))
        assertEquals(null, store.metadata(collision))
    }

    @Test
    fun rejectsUnsupportedCodex0149HooksBeforeMutatingTarget(): Unit = withTemporaryRoot { root, store ->
        val target = root / "workspace" / ".codex" / "hooks.json"
        val bundles = mapOf(
            "prompt" to """{"hooks":{"Stop":[{"hooks":[{"type":"prompt"}]}]}}""",
            "agent" to """{"hooks":{"Stop":[{"hooks":[{"type":"agent"}]}]}}""",
            "session-end-mcp" to
                """{"hooks":{"SessionEnd":[{"hooks":[{"type":"mcp_tool","server":"server","tool":"tool"}]}]}}""",
        )
        bundles.forEach { (name, config) ->
            val source = root / "sources" / name
            store.createDirectories(source)
            store.writeUtf8Atomically(source / "hooks.json", config)
        }
        val resources = resources(store, workspaceHooksFile = target)

        bundles.keys.forEach { name ->
            assertFailsWith<IllegalArgumentException> {
                runBlocking {
                    resources.installHook((root / "sources" / name).toString(), AgentInstallationScope.Workspace) {
                        AgentHookCatalog(emptyList())
                    }
                }
            }
        }
        assertEquals(null, store.metadata(root / "workspace"))
    }

    @Test
    fun reportsPartialChangeWhenRollbackCannotRemoveInstalledDirectory(): Unit = withTemporaryRoot { root, delegate ->
        val source = root / "partial"
        val skills = root / "skills"
        delegate.createDirectories(source)
        delegate.writeUtf8Atomically(source / "SKILL.md", "---\nname: partial\ndescription: Partial\n---\n")
        val failing = object : AgentFileStore by delegate {
            override fun deleteRecursively(path: Path) {
                if (path.name == "partial" && path.parent == skills) error("injected cleanup failure")
                delegate.deleteRecursively(path)
            }
        }
        val resources = resources(failing, workspaceSkillsRoot = skills)

        val cancellation = CancellationException("cancel discovery")
        val failure = assertFailsWith<AgentResourcePartialChangeException> {
            runBlocking {
                resources.installSkill(source.toString(), AgentInstallationScope.Workspace) {
                    throw cancellation
                }
            }
        }
        assertSame(cancellation, failure.cause)
        assertTrue(delegate.metadata(skills / "partial")?.isDirectory == true)
    }

    private fun resources(
        store: AgentFileStore,
        userSkillsRoot: Path? = null,
        workspaceSkillsRoot: Path? = null,
        userHooksFile: Path? = null,
        workspaceHooksFile: Path? = null,
    ): OwnedCodexResources = OwnedCodexResources(
        CodexInstallationRoots(
            userSkillsRoot = userSkillsRoot,
            workspaceSkillsRoot = workspaceSkillsRoot,
            userHooksFile = userHooksFile,
            workspaceHooksFile = workspaceHooksFile,
        ),
        store,
    )

    private fun hook(key: String, sourcePath: Path, source: String = "PROJECT"): AgentHook = AgentHook(
        key = key,
        currentHash = "hash",
        isEnabled = true,
        eventName = "PreToolUse",
        handler = AgentHookHandler.Command("sh lint.sh", false),
        isManaged = false,
        source = source,
        sourcePath = sourcePath.toString(),
        timeoutSeconds = 10,
        trustStatus = AgentHookTrustStatus.TRUSTED,
    )

    private fun withTemporaryRoot(block: (Path, AgentFileStore) -> Unit) {
        val root = Files.createTempDirectory("owned-codex-resources-").toRealPath().toString().toPath()
        val store = FileSystem.SYSTEM.asAgentFileStore()
        try {
            block(root, store)
        } finally {
            store.deleteRecursively(root)
        }
    }
}
