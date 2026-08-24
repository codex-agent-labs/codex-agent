package io.github.codex_agent_labs.codexmobile.agent

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
        "api-v1:AgentHook#constructor:<init>#sha256:ebdb4f13688d0eef21e5e9dd404e625d9634a177bec1e6b23450a6457ce0dfd7",
        "api-v1:AgentHook#property:canUninstall#sha256:c0cabde70c97b0cb6cbe98cb368924b9fb31f0ecb52b19e306bfa41b45ed467b",
        "api-v1:AgentHook#property:key#sha256:e6e371c05604d106c691b9fccac0ad3fb2c2faf68c2d17c064eeaeda3ad77892",
        "api-v1:AgentHook#property:origin#sha256:93f5059040243a0292ba5eb8b4160eb421c26fed08e8b722fbf0b002cf61fb37",
        "api-v1:AgentHook#property:sourcePath#sha256:7822add4e08d3e6ba357910e798d93277ed85d7c9b7af4e1a66535d5c06cd7a1",
        "api-v1:AgentHookCatalog#constructor:<init>#sha256:cb186f245a492587af8e3632e43c804b30c8f2bef6329b974e1bd4b19a0d651f",
        "api-v1:AgentHookCatalog#property:hooks#sha256:e5128a111bed4f3e8614061ba56fd5876647baf88eec427ad7779cf1c7a63431",
        "api-v1:AgentInstallationScope#enum-entry:User#sha256:2f69afc19c6f7a1b033fe00173acf97939c51d49f4e8f10c4cf7ee75d42477a3",
        "api-v1:AgentResourceOrigin#enum-entry:USER#sha256:96c27264eccb57770d89a1c27769f63635dea4b8ce46fc8bd3eb56e7efa32a89",
        "api-v1:AgentSkill#constructor:<init>#sha256:57163ba8c084a8dfbe8a4437b21ba7211d8fe9c4ea817f84ff88d573ebe1dda6",
        "api-v1:AgentSkill#property:canUninstall#sha256:ecb5eeacd2575f0be9ab49880993033f4d7322432b0bd76e0e869a815d4a9611",
        "api-v1:AgentSkill#property:origin#sha256:71e6ecec54260d04ced6fc377685b799301b1de673700d4c4a946de64c8fd069",
        "api-v1:AgentSkill#property:path#sha256:c34ed294794da6bfb74b904f385ed88076bd5c3f549ab36053290dd75df274aa",
        "api-v1:AgentSkillCatalog#constructor:<init>#sha256:2aef112408596db7a6d985f364b362ba668c7525ffc2bfae65065fe44b9ff85d",
        "api-v1:AgentSkillScope#enum-entry:USER#sha256:0f8455a736db5cb0f4d6c2bc14325f8cf96237db3f5ccf75d5f3a1180e089b36",
        "api-v1:CodexHooks#function:install#sha256:7c8f0f9395a7b5005b2c6f6057f141b4a41bda96fbedce1e5183df6d84bbd16e",
        "api-v1:CodexHooks#function:list#sha256:a4410c972b42f5d2957090b4ab03ceb0166d2fcc5fca6f3b4b62c1e07d54e2fb",
        "api-v1:CodexHooks#function:trust#sha256:58582fef5697704ab8b4eb95af6427e5806af1469c278ffa0dd5efe3ab0fce3d",
        "api-v1:CodexHooks#function:uninstall#sha256:e907f11c00275e2d8cc1d0d72763c3083c550031a21cddc04ca467cf1d1da894",
        "api-v1:CodexHooks#property:isAvailable#sha256:1f4b637fa9e452f986569fec56bb35ac8872523870a0201dfc389382a041650d",
        "api-v1:CodexSkills#function:install#sha256:0020690700c00861eb5d53a45ee1a1bc404166b5bd24c207e8a5ec754800a44f",
        "api-v1:CodexSkills#function:uninstall#sha256:d129aba8ddf27859be49a76fc7316043a8b869a4130cd29e40461a1f4c9d73d5",
        "api-v1:CodexSkills#property:isAvailable#sha256:d55dd76a0304cf8e9b7c48d1df39b941ae387a6da8d25bb0abefd204607213fa",
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
        "api-v1:AgentInstallationScope#enum-entry:Workspace#sha256:fff8b4780086308bd27166be208daf44e8bb8595bcd4ce0de0fc4cd7d261b267",
        "api-v1:AgentSkillScope#enum-entry:REPO#sha256:91cba025ec4eca465de07f5c2ee23a5f5fe3598cce4f4aea622345a53f6fcd92",
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
