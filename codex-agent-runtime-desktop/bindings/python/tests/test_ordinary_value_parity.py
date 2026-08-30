from __future__ import annotations

import csv
import inspect
import json
import sys
import unittest
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import codex_agent  # noqa: E402
import test_enum_parity as enum_parity  # noqa: E402
import test_mcp_value_parity as mcp_parity  # noqa: E402


OWNER_TYPES = {
    "AgentConnector": "Connector",
    "AgentConversationSettings": "ConversationSettings",
    "AgentConversationSummary": "ConversationSummary",
    "AgentElicitationValidation": "ElicitationValidation",
    "AgentElicitationValidationIssue": "ElicitationValidationIssue",
    "AgentFormOption": "FormOption",
    "AgentHookActivity": "HookActivity",
    "AgentModel": "Model",
    "AgentPlanProgress": "PlanProgress",
    "AgentPlanStep": "PlanStep",
    "AgentPluginCatalog": "PluginCatalog",
    "AgentPluginDetail": "PluginDetail",
    "AgentPluginInstallResult": "PluginInstallResult",
    "AgentPluginReference": "PluginReference",
    "AgentPluginSkill": "PluginSkill",
    "AgentPluginSummary": "PluginSummary",
    "AgentServiceTier": "ServiceTier",
    "AgentSkill": "Skill",
    "AgentSkillCatalog": "SkillCatalog",
    "AgentSkillChunk": "SkillChunk",
    "AgentTurnProgress": "TurnProgress",
    "CodexClientInfo": "ClientInfo",
    "CodexFailure": "Failure",
    "CodexWorkspace": "Workspace",
    "ConversationId": "ConversationId",
}
OWNER_PREFIX = "common|owner=io.github.codex_agent_labs.codexagent.agent/"
OVERLAP_OWNERS = {
    "AgentMcpEnvironmentVariable",
    "AgentMcpOauthConfiguration",
    "AgentMcpToolConfiguration",
}


def _owner(capability: str) -> str | None:
    return next(
        (
            owner
            for owner in OWNER_TYPES
            if capability.startswith(f"{OWNER_PREFIX}{owner}|")
        ),
        None,
    )


def _claims() -> list[list[str]]:
    rows = mcp_parity._claims()
    if len(rows) != 556:
        raise AssertionError("the Python inventory must contain exactly 556 claims")
    return rows


def _selected_rows(rows: list[list[str]]) -> list[list[str]]:
    return [row for row in rows if _owner(row[0]) is not None]


def _new_rows(rows: list[list[str]]) -> list[list[str]]:
    return [row for row in _selected_rows(rows) if mcp_parity._owner(row[0]) is None]


def _expected_scenarios(capability: str) -> tuple[str, ...]:
    scenarios = {"value-conversion"}
    if "?" in capability:
        scenarios.add("nullability")
    if "kotlin.collections" in capability:
        scenarios.add("collection-immutability-ordering")
    if f"{OWNER_PREFIX}CodexFailure|" in capability:
        scenarios.add("structured-failure")
    return tuple(sorted(scenarios))


def _expected_values() -> dict[str, object]:
    connector = codex_agent.Connector(
        "connector",
        "Connector",
        "Description",
        "https://example.test/install",
        True,
        False,
        ("plugin-a", "plugin-a", "plugin-b"),
    )
    conversation_id = codex_agent.ConversationId("conversation-1")
    issue = codex_agent.ElicitationValidationIssue(
        "email", codex_agent.ElicitationValidationReason.INVALID_FORMAT
    )
    step = codex_agent.PlanStep("compile", codex_agent.PlanStepStatus.COMPLETED)
    plan = codex_agent.PlanProgress("done", (step, step))
    hook = codex_agent.HookActivity(
        "hook-1",
        "after-turn",
        "command",
        codex_agent.HookRunStatus.COMPLETED,
        "ok",
        ("one", "one", "two"),
    )
    reference = codex_agent.PluginReference(
        "plugin-id", "plugin-name", "marketplace", "path", "remote"
    )
    plugin_skill = codex_agent.PluginSkill("skill", "Skill", True, "skill.md")
    summary = codex_agent.PluginSummary(
        reference,
        "Display",
        "Summary",
        True,
        False,
        codex_agent.PluginInstallPolicy.AVAILABLE,
        codex_agent.PluginAuthPolicy.ON_USE,
        True,
        ("one", "one", "two"),
        "#fff",
        "privacy",
        "terms",
        "website",
    )
    tier = codex_agent.ServiceTier("fast", "Fast", "Low latency")
    skill = codex_agent.Skill(
        "skill",
        "Skill",
        "Description",
        "skill.md",
        codex_agent.SkillScope.REPO,
        True,
        "#000",
        ("dep", "dep"),
        True,
    )
    return {
        "AgentConnector": connector,
        "AgentConversationSettings": codex_agent.ConversationSettings(
            codex_agent.ApprovalPreset.STRICT, "fast"
        ),
        "AgentConversationSummary": codex_agent.ConversationSummary(
            conversation_id, "Title", 42
        ),
        "AgentElicitationValidation": codex_agent.ElicitationValidation((issue,)),
        "AgentElicitationValidationIssue": issue,
        "AgentFormOption": codex_agent.FormOption("value", "Title", "Description"),
        "AgentHookActivity": hook,
        "AgentModel": codex_agent.Model(
            "model",
            "Model",
            "Description",
            ("low", "low", "high"),
            "low",
            True,
            (tier, tier),
            "fast",
        ),
        "AgentPlanProgress": plan,
        "AgentPlanStep": step,
        "AgentPluginCatalog": codex_agent.PluginCatalog(
            (summary, summary),
            ("error", "error"),
            codex_agent.CatalogFreshness.STALE_CACHE,
        ),
        "AgentPluginDetail": codex_agent.PluginDetail(
            summary,
            "Detail",
            (plugin_skill,),
            (connector,),
            ("mcp", "mcp"),
            2,
        ),
        "AgentPluginInstallResult": codex_agent.PluginInstallResult(
            codex_agent.PluginAuthPolicy.ON_INSTALL,
            (connector, connector),
            "ok",
        ),
        "AgentPluginReference": reference,
        "AgentPluginSkill": plugin_skill,
        "AgentPluginSummary": summary,
        "AgentServiceTier": tier,
        "AgentSkill": skill,
        "AgentSkillCatalog": codex_agent.SkillCatalog(
            (skill, skill), ("error", "error")
        ),
        "AgentSkillChunk": codex_agent.SkillChunk("content", 7, 12),
        "AgentTurnProgress": codex_agent.TurnProgress(
            "text",
            "commentary",
            "reasoning",
            "plan",
            plan,
            "output",
            7,
            codex_agent.WorkActivity.WRITING_FILES,
            (hook, hook),
            True,
        ),
        "CodexClientInfo": codex_agent.ClientInfo("client", "Client", "1.0"),
        "CodexFailure": codex_agent.Failure("failed", "Failure", True),
        "CodexWorkspace": codex_agent.Workspace("/workspace", "Workspace"),
        "ConversationId": conversation_id,
    }


class OrdinaryValueParityTests(unittest.TestCase):
    def test_exact_inventory_and_stale_references_fail_closed(self) -> None:
        rows = _claims()
        selected = _selected_rows(rows)
        overlap = [row for row in rows if mcp_parity._owner(row[0]) in OVERLAP_OWNERS]
        new_rows = _new_rows(rows)
        self.assertEqual((len(selected), len(overlap), len(new_rows)), (134, 8, 134))
        closure = selected + overlap
        self.assertEqual(len({row[0] for row in closure}), 142)

        canonical_report = json.loads(
            (
                ROOT.parents[2]
                / "codex-agent-core"
                / "build"
                / "reports"
                / "cross-language-api"
                / "canonical-api.json"
            ).read_text(encoding="utf-8")
        )
        canonical = {
            capability
            for owner in canonical_report["owners"]
            if owner["name"].rsplit("/", 1)[-1] in OWNER_TYPES.keys() | OVERLAP_OWNERS
            for capability in owner["capabilities"]
        }
        self.assertEqual({row[0] for row in closure}, canonical)

        bootstrap = json.loads(
            (
                ROOT.parents[1]
                / "build"
                / "reports"
                / "cross-language-api"
                / "c-abi"
                / "bootstrap-evidence.json"
            ).read_text(encoding="utf-8")
        )
        claims = {claim["capabilityKey"]: claim for claim in bootstrap["claims"]}
        passed = {
            test["testId"]
            for test in bootstrap["nativeTests"]
            if test["status"] == "passed"
        }
        header = (
            ROOT.parents[1] / "native" / "c-api" / "include" / "codex_agent.h"
        ).read_text(encoding="utf-8")
        for row in new_rows:
            mcp_parity._verify_reference_row(row, claims, passed, header)

        stale = [*new_rows[0]]
        stale[3] = stale[3].replace(
            next(item for item in stale[3].split(",") if item.startswith("c-header:")),
            "c-header:codex_agent_removed_ordinary_value",
        )
        with self.assertRaises(AssertionError):
            mcp_parity._verify_reference_row(stale, claims, passed, header)

    def test_immutable_null_empty_order_and_defensive_copy_behavior(self) -> None:
        names = ["one", "one", "two"]
        connector = codex_agent.Connector("id", "name", plugin_names=names)
        names[0] = "changed"
        self.assertEqual(connector.plugin_names, ("one", "one", "two"))
        with self.assertRaises(AttributeError):
            connector.name = "changed"  # type: ignore[misc]

        steps = [
            codex_agent.PlanStep("one", codex_agent.PlanStepStatus.PENDING),
            codex_agent.PlanStep("one", codex_agent.PlanStepStatus.PENDING),
        ]
        progress = codex_agent.PlanProgress(None, steps)
        steps.clear()
        self.assertIsNone(progress.explanation)
        self.assertEqual(len(progress.steps), 2)
        self.assertEqual(codex_agent.PlanProgress().steps, ())

        self.assertTrue(codex_agent.ElicitationValidation(()).is_valid)
        self.assertFalse(
            codex_agent.ElicitationValidation(
                (
                    codex_agent.ElicitationValidationIssue(
                        "field", codex_agent.ElicitationValidationReason.INVALID_TYPE
                    ),
                )
            ).is_valid
        )
        self.assertEqual(
            codex_agent.PluginReference("id", "name", "market").uri,
            "plugin://name@market",
        )
        self.assertEqual(
            codex_agent.Skill(
                "s", "S", "d", "p", codex_agent.SkillScope.REPO, True
            ).origin,
            codex_agent.ResourceOrigin.WORKSPACE,
        )
        self.assertEqual(codex_agent.Workspace("/workspace").display_name, "/workspace")
        for action in (
            lambda: codex_agent.ClientInfo("", "Title", "1"),
            lambda: codex_agent.ConversationId(" "),
            lambda: codex_agent.Failure("", "message", False),
            lambda: codex_agent.Workspace(" "),
        ):
            with self.assertRaises(ValueError):
                action()

    def test_exact_public_projection_behavior_and_complete_evidence(self) -> None:
        mcp_parity.McpValueParityTests(
            "test_exact_mcp_value_parity_and_complete_evidence"
        ).test_exact_mcp_value_parity_and_complete_evidence()

        rows = _claims()
        new_rows = _new_rows(rows)
        expected = _expected_values()
        executed_tests: set[str] = set()
        compiler_evidence: dict[str, set[str]] = defaultdict(set)

        bootstrap = json.loads(
            (
                ROOT.parents[1]
                / "build"
                / "reports"
                / "cross-language-api"
                / "c-abi"
                / "bootstrap-evidence.json"
            ).read_text(encoding="utf-8")
        )
        bootstrap_claims = {
            claim["capabilityKey"]: claim for claim in bootstrap["claims"]
        }
        passed = {
            test["testId"]
            for test in bootstrap["nativeTests"]
            if test["status"] == "passed"
        }
        header = (
            ROOT.parents[1] / "native" / "c-api" / "include" / "codex_agent.h"
        ).read_text(encoding="utf-8")

        for row in new_rows:
            capability, symbol_cell, test_cell, _, scenario_cell = row
            owner = _owner(capability)
            self.assertIsNotNone(owner, capability)
            type_name = OWNER_TYPES[owner]
            public_type = getattr(codex_agent, type_name)
            self.assertIn(type_name, codex_agent.__all__)
            symbols = enum_parity._exact_list(symbol_cell, "publicSymbols")
            tests = enum_parity._exact_list(test_cell, "executedTests")
            evidence = mcp_parity._verify_reference_row(
                row, bootstrap_claims, passed, header
            )
            self.assertEqual(len(symbols), 1, capability)
            self.assertEqual(len(tests), 1, capability)
            self.assertEqual(
                enum_parity._exact_list(scenario_cell, "sharedScenarios"),
                _expected_scenarios(capability),
                capability,
            )
            value = expected[owner]
            if "|kind=constructor|" in capability:
                self.assertEqual(symbols[0], f"codex_agent.{type_name}", capability)
                self.assertTrue(callable(public_type), capability)
                self.assertGreater(len(inspect.signature(public_type).parameters), 0)
                self.assertIsInstance(value, public_type)
            else:
                member = symbols[0].rsplit(".", 1)[1]
                self.assertEqual(symbols[0], f"codex_agent.{type_name}.{member}")
                self.assertTrue(hasattr(public_type, member), capability)
                getattr(value, member)
            self.assertNotIn(tests[0], executed_tests, capability)
            executed_tests.add(tests[0])
            for evidence_id in evidence:
                compiler_evidence[evidence_id].add(symbols[0])

        self.assertEqual(len(executed_tests), 134)
        compiler_rows: dict[str, str] = {}
        with (enum_parity.EVIDENCE_DIRECTORY / "compiler-evidence.tsv").open(
            newline="", encoding="utf-8"
        ) as evidence_file:
            reader = csv.reader(evidence_file, delimiter="\t", strict=True)
            self.assertEqual(next(reader), ["compilerEvidenceId", "publicSymbols"])
            compiler_rows.update(reader)
        for evidence_id, symbols in compiler_evidence.items():
            if evidence_id in compiler_rows:
                self.assertEqual(
                    set(compiler_rows[evidence_id].split(",")) & symbols,
                    set(),
                    evidence_id,
                )
                symbols.update(compiler_rows[evidence_id].split(","))
            compiler_rows[evidence_id] = ",".join(sorted(symbols))

        all_tests: set[str] = set()
        with (enum_parity.EVIDENCE_DIRECTORY / "executed-tests.tsv").open(
            newline="", encoding="utf-8"
        ) as evidence_file:
            reader = csv.reader(evidence_file, delimiter="\t", strict=True)
            self.assertEqual(next(reader), ["executedTestId", "status"])
            for test_id, status in reader:
                self.assertEqual(status, "passed")
                all_tests.add(test_id)
        self.assertTrue(all_tests.isdisjoint(executed_tests))
        all_tests.update(executed_tests)

        proven_rows = (
            [row for row in rows if "|kind=enum-entry|" in row[0]]
            + [row for row in rows if mcp_parity._owner(row[0]) is not None]
            + new_rows
        )
        self.assertEqual(len(proven_rows), 290)
        claimed_evidence = {
            evidence_id
            for row in proven_rows
            for evidence_id in enum_parity._exact_list(row[3], "compilerEvidenceIds")
        }
        claimed_tests = {
            test_id
            for row in proven_rows
            for test_id in enum_parity._exact_list(row[2], "executedTests")
        }
        self.assertEqual(set(compiler_rows), claimed_evidence)
        self.assertEqual(all_tests, claimed_tests)
        enum_parity._write_lf_tsv(
            enum_parity.EVIDENCE_DIRECTORY / "compiler-evidence.tsv",
            ("compilerEvidenceId", "publicSymbols"),
            list(compiler_rows.items()),
        )
        enum_parity._write_lf_tsv(
            enum_parity.EVIDENCE_DIRECTORY / "executed-tests.tsv",
            ("executedTestId", "status"),
            [(test, "passed") for test in all_tests],
        )
        for path in (
            enum_parity.EVIDENCE_DIRECTORY / "compiler-evidence.tsv",
            enum_parity.EVIDENCE_DIRECTORY / "executed-tests.tsv",
        ):
            lines = path.read_text(encoding="utf-8").splitlines()[1:]
            self.assertEqual(lines, sorted(lines))
            self.assertNotIn(b"\r", path.read_bytes())


if __name__ == "__main__":
    unittest.main()
