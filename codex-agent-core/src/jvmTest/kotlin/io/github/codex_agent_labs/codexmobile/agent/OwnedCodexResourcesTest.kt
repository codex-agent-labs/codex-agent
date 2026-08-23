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
        val resources = resources(store, userSkillsRoot = userSkills, userHooksFile = userHooks)

        val skill = runBlocking {
            resources.installSkill(skillSource.toString(), AgentInstallationScope.User) {
                AgentSkillCatalog(
                    listOf(
                        AgentSkill(
                            "user-skill",
                            "User skill",
                            "User skill",
                            (userSkills / "user-skill" / "SKILL.md").toString(),
                            AgentSkillScope.USER,
                            true,
                        ),
                    ),
                )
            }
        }
        var hookReload = 0
        val hook = runBlocking {
            resources.installHook(hookSource.toString(), AgentInstallationScope.User) {
                if (hookReload++ == 0) AgentHookCatalog(emptyList())
                else AgentHookCatalog(listOf(hook("user-hook", userHooks, source = "USER")))
            }
        }

        assertTrue(skill.canUninstall)
        assertTrue(hook.canUninstall)
        assertEquals(AgentResourceOrigin.USER, skill.origin)
        assertEquals(AgentResourceOrigin.USER, hook.origin)
        runBlocking {
            resources.uninstallSkill(skill) { AgentSkillCatalog(emptyList()) }
            resources.uninstallHook(hook) { AgentHookCatalog(emptyList()) }
        }
        assertEquals(null, store.metadata(userSkills / "user-skill"))
        assertEquals(null, store.metadata(userHooks.parent!! / ".codex-agent-hooks" / "user-hook"))
    }

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
