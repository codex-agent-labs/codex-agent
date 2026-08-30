from __future__ import annotations

import csv
import inspect
import json
import re
import sys
import unittest
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import codex_agent  # noqa: E402
import test_enum_parity as enum_parity  # noqa: E402
import test_mcp_value_parity as mcp_parity  # noqa: E402
import test_ordinary_value_parity as ordinary_parity  # noqa: E402


OWNER_TYPES = {
    "AgentApprovalPreset": "ApprovalPreset",
    "AgentAuthenticationState": "AuthenticationState",
    "AgentCapability": "Capability",
    "AgentConversation": "ConversationValue",
    "AgentConversationState": "ConversationState",
    "AgentElicitation": "Elicitation",
    "AgentElicitationResponse": "ElicitationResponse",
    "AgentFormField": "FormField",
    "AgentFormValue.BooleanValue": "FormBooleanValue",
    "AgentFormValue.Number": "FormNumberValue",
    "AgentFormValue.Text": "FormTextValue",
    "AgentFormValue.TextList": "FormTextListValue",
    "AgentHook": "Hook",
    "AgentHookCatalog": "HookCatalog",
    "AgentHookHandler.Agent": "HookHandlerAgent",
    "AgentHookHandler.Command": "HookHandlerCommand",
    "AgentHookHandler.McpTool": "HookHandlerMcpTool",
    "AgentHookHandler.Prompt": "HookHandlerPrompt",
    "AgentIntegration": "Integration",
    "AgentIntegration.Connector": "ConnectorIntegration",
    "AgentIntegration.McpServer": "McpServerIntegration",
    "AgentIntegrationAuthorizationState": "IntegrationAuthorizationState",
    "AgentInteractionState": "InteractionState",
    "AgentInvocation": "Invocation",
    "AgentInvocation.Plugin": "PluginInvocation",
    "AgentInvocation.Skill": "SkillInvocation",
    "AgentMessage": "Message",
    "AgentPendingApproval": "PendingApproval",
    "AgentPendingElicitation": "PendingElicitation",
    "AgentPendingInteraction": "PendingInteraction",
    "AgentSkillScope": "SkillScope",
    "AgentTurnRequest": "TurnRequest",
    "CodexAuthenticationMethod.ApiKey": "ApiKeyAuthentication",
    "CodexAuthenticationMethod.ChatGptBrowser": "ChatGptBrowserAuthentication",
    "CodexAuthenticationMethod.ChatGptDeviceCode": "ChatGptDeviceCodeAuthentication",
    "CodexAuthorizationUrl": "AuthorizationUrl",
    "CodexHostState.Closed": "HostStateClosed",
    "CodexHostState.Failed": "HostStateFailed",
    "CodexHostState.New": "HostStateNew",
    "CodexHostState.Preparing": "HostStatePreparing",
    "CodexHostState.Restoring": "HostStateRestoring",
    "CodexHostState.WorkspaceRequired": "HostStateWorkspaceRequired",
    "CodexPathWorkspaceSelection": "PathWorkspaceSelection",
    "CodexWorkspaceResolution.Available": "WorkspaceAvailable",
    "CodexWorkspaceResolution.SelectionRequired": "WorkspaceSelectionRequired",
}
OBJECT_SYMBOLS = {
    "AgentHookHandler.Agent": "codex_agent.HOOK_HANDLER_AGENT",
    "AgentHookHandler.Prompt": "codex_agent.HOOK_HANDLER_PROMPT",
    "CodexAuthenticationMethod.ChatGptBrowser": (
        "codex_agent.CHAT_GPT_BROWSER_AUTHENTICATION"
    ),
    "CodexAuthenticationMethod.ChatGptDeviceCode": (
        "codex_agent.CHAT_GPT_DEVICE_CODE_AUTHENTICATION"
    ),
    "CodexHostState.Closed": "codex_agent.HOST_STATE_CLOSED",
    "CodexHostState.New": "codex_agent.HOST_STATE_NEW",
    "CodexHostState.Restoring": "codex_agent.HOST_STATE_RESTORING",
}
OWNER_PREFIX = "common|owner=io.github.codex_agent_labs.codexagent.agent/"
LEAF_SERVICE_OWNERS = {
    "CodexAuthentication",
    "CodexConnectors",
    "CodexHooks",
    "CodexIntegrationAuthorization",
    "CodexInteractions",
    "CodexMcpServers",
    "CodexModels",
    "CodexPlugins",
    "CodexSkills",
}


def _is_leaf_service(capability: str) -> bool:
    return any(
        capability.startswith(f"{OWNER_PREFIX}{owner}|")
        for owner in LEAF_SERVICE_OWNERS
    )


def _owner(capability: str) -> str | None:
    return next(
        (
            owner
            for owner in OWNER_TYPES
            if capability.startswith(f"{OWNER_PREFIX}{owner}|")
        ),
        None,
    )


def _selected_rows(rows: list[list[str]]) -> list[list[str]]:
    return [
        row
        for row in rows
        if _owner(row[0]) is not None
        and any(
            marker in row[0]
            for marker in ("|kind=constructor|", "|kind=property|", "|kind=object|")
        )
    ]


def _expected_scenarios(capability: str) -> tuple[str, ...]:
    scenarios = {"value-conversion"}
    if "?" in capability:
        scenarios.add("nullability")
    if "kotlin.collections" in capability:
        scenarios.add("collection-immutability-ordering")
    return tuple(sorted(scenarios))


def _canonical_residual() -> set[str]:
    report = json.loads(
        (
            ROOT.parents[2]
            / "codex-agent-core"
            / "build"
            / "reports"
            / "cross-language-api"
            / "canonical-api.json"
        ).read_text(encoding="utf-8")
    )
    return {
        capability
        for owner in report["owners"]
        if owner["name"].rsplit("/", 1)[-1] in OWNER_TYPES
        for capability in owner["capabilities"]
        if any(
            marker in capability
            for marker in ("|kind=constructor|", "|kind=property|", "|kind=object|")
        )
    }


def _validate_rows(rows: list[list[str]], canonical: set[str]) -> None:
    if len(rows) != 175:
        raise AssertionError("exactly 175 residual immutable-value claims are required")
    if not all(len(row) == 5 and all(row) for row in rows):
        raise AssertionError("each residual claim must have five nonempty columns")
    keys = [row[0] for row in rows]
    if keys != sorted(set(keys)) or set(keys) != canonical:
        raise AssertionError(
            "residual claims contain a stale, missing, or duplicate key"
        )


def _verify_reference_row(
    row: list[str],
    bootstrap_claims: dict[str, dict[str, object]],
    passed_native_tests: set[str],
    header: str,
) -> tuple[str, ...]:
    capability = row[0]
    bootstrap = bootstrap_claims.get(capability)
    if bootstrap is None:
        raise AssertionError(f"missing C ABI bootstrap claim: {capability}")
    tests = enum_parity._exact_list(row[2], "executedTests")
    evidence = enum_parity._exact_list(row[3], "compilerEvidenceIds")
    if len(tests) != 1:
        raise AssertionError(f"{capability} must have one distinct executed test")
    suffix = tests[0].removeprefix("python.residual:")
    analyzer = f"python-analyzer-residual:{suffix}"
    expected = {
        *(f"c-header:{name}" for name in bootstrap["headerReferences"]),
        *(f"cabi-fixture:{test}" for test in bootstrap["nativeTestIds"]),
        analyzer,
    }
    if set(evidence) != expected:
        raise AssertionError(f"inexact compiler/bootstrap evidence for {capability}")
    for evidence_id in evidence:
        if evidence_id.startswith("c-header:"):
            name = evidence_id.removeprefix("c-header:")
            if re.fullmatch(r"CODEX_AGENT_[A-Z0-9_]+", name):
                present = (
                    re.search(
                        rf"^\s*#define\s+{re.escape(name)}\b", header, re.MULTILINE
                    )
                    is not None
                )
            elif name.endswith("_t"):
                present = re.search(rf"}}\s+{re.escape(name)}\s*;", header) is not None
            elif re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                present = re.search(rf"\b{re.escape(name)}\s*\(", header) is not None
            else:
                present = any(line.strip() == name for line in header.splitlines())
            if not present:
                raise AssertionError(f"stale C-header evidence: {evidence_id}")
        elif evidence_id.startswith("cabi-fixture:"):
            test = evidence_id.removeprefix("cabi-fixture:")
            if test not in passed_native_tests:
                raise AssertionError(f"stale C ABI fixture evidence: {evidence_id}")
        elif evidence_id != analyzer:
            raise AssertionError(f"stale Python analyzer evidence: {evidence_id}")
    return evidence


def _values() -> dict[str, object]:
    failure = codex_agent.Failure("failed", "Failed", True)
    workspace = codex_agent.Workspace("/workspace", "Workspace")
    conversation_id = codex_agent.ConversationId("conversation-1")
    authorization_url = codex_agent.AuthorizationUrl(
        "https://example.test/auth", codex_agent.AuthorizationPurpose.EXTERNAL
    )
    authentication = codex_agent.AuthenticationState(
        codex_agent.AuthenticationStatus.AUTHENTICATING,
        authorization_url,
        authorization_url,
        "ABCD-EFGH",
        failure,
    )
    form_text = codex_agent.FormTextValue("hello")
    form_field = codex_agent.FormField(
        name="email",
        title="Email",
        type=codex_agent.FormFieldType.STRING,
        description="Address",
        is_required=True,
        is_secret=False,
        format=codex_agent.FormStringFormat.EMAIL,
        default_value=form_text,
        minimum=1.0,
        maximum=10.0,
        minimum_length=1,
        maximum_length=20,
        options=(codex_agent.FormOption("work", "Work"),),
        allows_other=True,
        minimum_selections=1,
        maximum_selections=2,
    )
    elicitation = codex_agent.Elicitation(
        "elicitation-1",
        conversation_id,
        "server",
        "Choose",
        "https://example.test/form",
        (form_field,),
    )
    response = codex_agent.ElicitationResponse(
        codex_agent.ElicitationAction.ACCEPT, {"email": form_text}
    )
    command = codex_agent.HookHandlerCommand("echo ok", True)
    mcp_handler = codex_agent.HookHandlerMcpTool("server", "tool")
    hook = codex_agent.Hook(
        key="hook-1",
        current_hash="hash",
        is_enabled=True,
        event_name="after-turn",
        handler=command,
        is_managed=False,
        source="PROJECT",
        source_path="/workspace/hook",
        timeout_seconds=30,
        trust_status=codex_agent.HookTrustStatus.TRUSTED,
        matcher="matcher",
        plugin_id=None,
        status_message="ready",
        can_uninstall=True,
    )
    hook_catalog = codex_agent.HookCatalog((hook,), ("warning",), ("error",))
    connector = codex_agent.Connector("connector", "Connector")
    mcp_server = mcp_parity._expected_graph()[0]
    connector_integration = codex_agent.ConnectorIntegration(connector)
    mcp_integration = codex_agent.McpServerIntegration(mcp_server)
    authorization = codex_agent.IntegrationAuthorizationState(
        codex_agent.IntegrationAuthorizationStatus.AUTHORIZED,
        connector_integration,
        None,
    )
    plugin_invocation = codex_agent.PluginInvocation("Plugin", "plugin://example")
    skill_invocation = codex_agent.SkillInvocation("Skill", "/workspace/SKILL.md")
    message = codex_agent.Message(
        "message-1",
        codex_agent.MessageRole.ASSISTANT,
        "hello",
        "reasoning",
        "plan",
        "echo ok",
        0,
        (plugin_invocation, skill_invocation),
        {codex_agent.Capability.WEB_SEARCH},
        codex_agent.CollaborationMode.PLAN,
        "client-message-1",
    )
    turn_request = codex_agent.TurnRequest(
        "prompt",
        "model",
        "high",
        codex_agent.ApprovalPreset.STRICT,
        "priority",
        {codex_agent.Capability.WEB_SEARCH},
        codex_agent.CollaborationMode.PLAN,
        (plugin_invocation,),
        "client-message-2",
    )
    approval = codex_agent.PendingApproval(
        "approval", conversation_id, "Run command", "echo ok"
    )
    pending_elicitation = codex_agent.PendingElicitation(elicitation)
    interactions = codex_agent.InteractionState(
        (approval, pending_elicitation), {"approval", "elicitation"}, failure
    )
    summary = codex_agent.ConversationSummary(conversation_id, "Conversation", 42)
    conversation = codex_agent.ConversationValue(summary, (message,))
    conversation_state = codex_agent.ConversationState(
        codex_agent.ConversationStatus.RUNNING_TURN,
        None,
        conversation_id,
        conversation,
        "model",
        "high",
        "priority",
        codex_agent.TurnProgress(text="working"),
    )
    requirement = codex_agent.WorkspaceSelectionRequired(
        codex_agent.WorkspaceSelectionReason.NOT_FOUND, "Select a workspace"
    )
    return {
        "AgentApprovalPreset": codex_agent.ApprovalPreset.AUTO_REVIEW,
        "AgentAuthenticationState": authentication,
        "AgentCapability": codex_agent.Capability.WEB_SEARCH,
        "AgentConversation": conversation,
        "AgentConversationState": conversation_state,
        "AgentElicitation": elicitation,
        "AgentElicitationResponse": response,
        "AgentFormField": form_field,
        "AgentFormValue.BooleanValue": codex_agent.FormBooleanValue(True),
        "AgentFormValue.Number": codex_agent.FormNumberValue(1.5),
        "AgentFormValue.Text": form_text,
        "AgentFormValue.TextList": codex_agent.FormTextListValue(("a", "a", "b")),
        "AgentHook": hook,
        "AgentHookCatalog": hook_catalog,
        "AgentHookHandler.Agent": codex_agent.HOOK_HANDLER_AGENT,
        "AgentHookHandler.Command": command,
        "AgentHookHandler.McpTool": mcp_handler,
        "AgentHookHandler.Prompt": codex_agent.HOOK_HANDLER_PROMPT,
        "AgentIntegration": connector_integration,
        "AgentIntegration.Connector": connector_integration,
        "AgentIntegration.McpServer": mcp_integration,
        "AgentIntegrationAuthorizationState": authorization,
        "AgentInteractionState": interactions,
        "AgentInvocation": plugin_invocation,
        "AgentInvocation.Plugin": plugin_invocation,
        "AgentInvocation.Skill": skill_invocation,
        "AgentMessage": message,
        "AgentPendingApproval": approval,
        "AgentPendingElicitation": pending_elicitation,
        "AgentPendingInteraction": approval,
        "AgentSkillScope": codex_agent.SkillScope.REPO,
        "AgentTurnRequest": turn_request,
        "CodexAuthenticationMethod.ApiKey": codex_agent.ApiKeyAuthentication("key"),
        "CodexAuthenticationMethod.ChatGptBrowser": (
            codex_agent.CHAT_GPT_BROWSER_AUTHENTICATION
        ),
        "CodexAuthenticationMethod.ChatGptDeviceCode": (
            codex_agent.CHAT_GPT_DEVICE_CODE_AUTHENTICATION
        ),
        "CodexAuthorizationUrl": authorization_url,
        "CodexHostState.Closed": codex_agent.HOST_STATE_CLOSED,
        "CodexHostState.Failed": codex_agent.HostStateFailed(failure, workspace),
        "CodexHostState.New": codex_agent.HOST_STATE_NEW,
        "CodexHostState.Preparing": codex_agent.HostStatePreparing(workspace),
        "CodexHostState.Restoring": codex_agent.HOST_STATE_RESTORING,
        "CodexHostState.WorkspaceRequired": (
            codex_agent.HostStateWorkspaceRequired(requirement)
        ),
        "CodexPathWorkspaceSelection": codex_agent.PathWorkspaceSelection("/workspace"),
        "CodexWorkspaceResolution.Available": codex_agent.WorkspaceAvailable(workspace),
        "CodexWorkspaceResolution.SelectionRequired": requirement,
    }


class ResidualValueParityTests(unittest.TestCase):
    def test_exact_inventory_and_stale_evidence_fail_closed(self) -> None:
        rows = _selected_rows(ordinary_parity._claims())
        canonical = _canonical_residual()
        self.assertEqual((len(OWNER_TYPES), len(canonical)), (45, 175))
        self.assertEqual(
            (
                sum("|kind=constructor|" in key for key in canonical),
                sum("|kind=property|" in key for key in canonical),
                sum("|kind=object|" in key for key in canonical),
            ),
            (31, 137, 7),
        )
        _validate_rows(rows, canonical)

        malformed = [*rows[:-1], rows[-1][:-1]]
        duplicate = [*rows[:-1], rows[-2]]
        stale = [*rows]
        stale[-1] = [*stale[-1]]
        stale[-1][0] = "common|owner=removed/Stale|kind=property|abi=removed"
        for candidate in (malformed, duplicate, stale):
            with self.assertRaises(AssertionError):
                _validate_rows(candidate, canonical)

        bootstrap, passed, header = self._bootstrap()
        for prefix, replacement in (
            ("c-header:", "c-header:codex_agent_removed_residual"),
            (
                "cabi-fixture:",
                "cabi-fixture:removed.native.test#stale[macosArm64]",
            ),
            ("python-analyzer-", "python-analyzer-residual:999"),
        ):
            candidate = next(row for row in rows if prefix in row[3])
            candidate = [*candidate]
            old = next(
                item for item in candidate[3].split(",") if item.startswith(prefix)
            )
            candidate[3] = candidate[3].replace(old, replacement)
            with self.assertRaises(AssertionError):
                _verify_reference_row(candidate, bootstrap, passed, header)

    def _bootstrap(self) -> tuple[dict[str, dict[str, object]], set[str], str]:
        report = json.loads(
            (
                ROOT.parents[1]
                / "build"
                / "reports"
                / "cross-language-api"
                / "c-abi"
                / "bootstrap-evidence.json"
            ).read_text(encoding="utf-8")
        )
        return (
            {claim["capabilityKey"]: claim for claim in report["claims"]},
            {
                test["testId"]
                for test in report["nativeTests"]
                if test["status"] == "passed"
            },
            (
                ROOT.parents[1] / "native" / "c-api" / "include" / "codex_agent.h"
            ).read_text(encoding="utf-8"),
        )

    def test_immutable_null_empty_order_and_defensive_copy_behavior(self) -> None:
        self.assertEqual(
            (
                codex_agent.Capability.WEB_SEARCH.id,
                codex_agent.Capability.WEB_SEARCH.display_label,
                codex_agent.Capability.WEB_SEARCH.icon,
                codex_agent.Capability.WEB_SEARCH.prompt_label,
            ),
            ("web_search", "Web search", "🌐", "Use 🌐 Web search"),
        )
        self.assertEqual(
            [scope.display_name for scope in codex_agent.SkillScope],
            ["Built in", "User", "Workspace", "Plugin", "Managed"],
        )
        self.assertEqual(
            codex_agent.AuthenticationState(),
            codex_agent.AuthenticationState(
                codex_agent.AuthenticationStatus.SIGNED_OUT
            ),
        )
        items = ["a", "a", "b"]
        text_list = codex_agent.FormTextListValue(items)
        items[0] = "changed"
        self.assertEqual(text_list.value, ("a", "a", "b"))

        options = [codex_agent.FormOption("a")]
        field = codex_agent.FormField(
            "field", "Field", codex_agent.FormFieldType.STRING, options=options
        )
        options.clear()
        self.assertEqual(len(field.options), 1)

        content = {"field": codex_agent.FormTextValue("value")}
        response = codex_agent.ElicitationResponse(
            codex_agent.ElicitationAction.ACCEPT, content
        )
        content.clear()
        self.assertEqual(response.content["field"].value, "value")
        with self.assertRaises(TypeError):
            response.content["other"] = codex_agent.FormTextValue("no")  # type: ignore[index]

        pending = [
            codex_agent.PendingApproval(
                "request",
                codex_agent.ConversationId("conversation"),
                "Title",
                "Details",
            )
        ]
        resolving = {"request"}
        state = codex_agent.InteractionState(pending, resolving)
        pending.clear()
        resolving.clear()
        self.assertEqual(len(state.pending), 1)
        self.assertEqual(state.resolving_request_ids, frozenset({"request"}))
        self.assertIsNone(state.failure)
        with self.assertRaises(AttributeError):
            state.failure = codex_agent.Failure("x", "x", False)  # type: ignore[misc]

        connector_integration = codex_agent.ConnectorIntegration(
            codex_agent.Connector("connector", "Connector")
        )
        self.assertEqual(
            (connector_integration.id, connector_integration.display_name),
            ("connector", "Connector"),
        )
        plugin = codex_agent.PluginInvocation("Plugin", "plugin://example")
        skill = codex_agent.SkillInvocation("Skill", "/workspace/SKILL.md")
        self.assertEqual(
            (plugin.key, skill.key),
            ("plugin:plugin://example", "skill:/workspace/SKILL.md"),
        )
        elicitation = codex_agent.Elicitation(
            "request", codex_agent.ConversationId("conversation"), "server", "Choose"
        )
        pending_elicitation = codex_agent.PendingElicitation(elicitation)
        self.assertEqual(pending_elicitation.request_id, elicitation.request_id)
        self.assertEqual(
            pending_elicitation.conversation_id, elicitation.conversation_id
        )
        untrusted = codex_agent.Hook(
            "hook",
            "hash",
            True,
            "event",
            codex_agent.HOOK_HANDLER_AGENT,
            False,
            "PROJECT",
            "/workspace/hook",
            30,
            codex_agent.HookTrustStatus.UNTRUSTED,
        )
        self.assertTrue(untrusted.can_trust)
        self.assertEqual(untrusted.origin, codex_agent.ResourceOrigin.WORKSPACE)
        running = codex_agent.ConversationState(
            codex_agent.ConversationStatus.RUNNING_TURN,
            conversation_id=codex_agent.ConversationId("conversation"),
        )
        self.assertEqual(
            (running.can_start_turn, running.can_cancel_turn, running.can_reload),
            (False, True, False),
        )

        self.assertIs(codex_agent.HOOK_HANDLER_AGENT, codex_agent.HOOK_HANDLER_AGENT)
        self.assertIs(codex_agent.HOST_STATE_NEW, codex_agent.HOST_STATE_NEW)
        for action in (
            lambda: codex_agent.ApiKeyAuthentication(" "),
            lambda: codex_agent.PathWorkspaceSelection(""),
            lambda: codex_agent.FormField(
                "field",
                "Field",
                codex_agent.FormFieldType.STRING,
                minimum_length=2,
                maximum_length=1,
            ),
        ):
            with self.assertRaises(ValueError):
                action()

    def test_exact_public_projection_behavior_and_complete_evidence(self) -> None:
        ordinary_parity.OrdinaryValueParityTests(
            "test_exact_public_projection_behavior_and_complete_evidence"
        ).test_exact_public_projection_behavior_and_complete_evidence()

        rows = _selected_rows(ordinary_parity._claims())
        expected = _values()
        bootstrap, passed, header = self._bootstrap()
        executed_tests: set[str] = set()
        compiler_evidence: dict[str, set[str]] = defaultdict(set)

        for row in rows:
            capability, symbol_cell, test_cell, _, scenario_cell = row
            owner = _owner(capability)
            self.assertIsNotNone(owner, capability)
            type_name = OWNER_TYPES[owner]
            public_type = getattr(codex_agent, type_name)
            self.assertIn(type_name, codex_agent.__all__)
            symbols = enum_parity._exact_list(symbol_cell, "publicSymbols")
            tests = enum_parity._exact_list(test_cell, "executedTests")
            evidence = _verify_reference_row(row, bootstrap, passed, header)
            self.assertEqual((len(symbols), len(tests)), (1, 1), capability)
            self.assertEqual(
                enum_parity._exact_list(scenario_cell, "sharedScenarios"),
                _expected_scenarios(capability),
                capability,
            )

            symbol = symbols[0]
            compiled = compile(symbol, f"<{tests[0]}>", "eval")
            resolved = eval(compiled, {"codex_agent": codex_agent})
            value = expected[owner]
            if "|kind=constructor|" in capability:
                self.assertEqual(symbol, f"codex_agent.{type_name}", capability)
                self.assertIs(resolved, public_type, capability)
                self.assertGreater(len(inspect.signature(public_type).parameters), 0)
                self.assertIsInstance(value, public_type, capability)
            elif "|kind=object|" in capability:
                self.assertEqual(symbol, OBJECT_SYMBOLS[owner], capability)
                self.assertIs(resolved, value, capability)
            else:
                member = symbol.rsplit(".", 1)[1]
                self.assertEqual(symbol, f"codex_agent.{type_name}.{member}")
                self.assertTrue(hasattr(public_type, member), capability)
                getattr(value, member)

            self.assertNotIn(tests[0], executed_tests, capability)
            executed_tests.add(tests[0])
            for evidence_id in evidence:
                compiler_evidence[evidence_id].add(symbol)

        self.assertEqual(len(executed_tests), 175)
        compiler_rows: dict[str, str] = {}
        compiler_path = enum_parity.EVIDENCE_DIRECTORY / "compiler-evidence.tsv"
        with compiler_path.open(newline="", encoding="utf-8") as evidence_file:
            reader = csv.reader(evidence_file, delimiter="\t", strict=True)
            self.assertEqual(next(reader), ["compilerEvidenceId", "publicSymbols"])
            compiler_rows.update(reader)
        for evidence_id, symbols in compiler_evidence.items():
            if evidence_id in compiler_rows:
                prior = set(compiler_rows[evidence_id].split(","))
                self.assertTrue(prior.isdisjoint(symbols), evidence_id)
                symbols.update(prior)
            compiler_rows[evidence_id] = ",".join(sorted(symbols))

        tests_path = enum_parity.EVIDENCE_DIRECTORY / "executed-tests.tsv"
        all_tests: set[str] = set()
        with tests_path.open(newline="", encoding="utf-8") as evidence_file:
            reader = csv.reader(evidence_file, delimiter="\t", strict=True)
            self.assertEqual(next(reader), ["executedTestId", "status"])
            for test_id, status in reader:
                self.assertEqual(status, "passed")
                all_tests.add(test_id)
        self.assertTrue(all_tests.isdisjoint(executed_tests))
        all_tests.update(executed_tests)

        all_rows = [
            row
            for row in ordinary_parity._claims()
            if "|kind=function|" not in row[0]
            and not _is_leaf_service(row[0])
            and not row[0].startswith(f"{OWNER_PREFIX}CodexConversation")
            and not row[0].startswith(f"{OWNER_PREFIX}CodexAgent|")
            and not row[0].startswith(f"{OWNER_PREFIX}CodexHost|")
            and not row[0].startswith(f"{OWNER_PREFIX}CodexHostState.Ready|")
        ]
        claimed_evidence = {
            evidence_id
            for row in all_rows
            for evidence_id in enum_parity._exact_list(row[3], "compilerEvidenceIds")
        }
        claimed_tests = {
            test_id
            for row in all_rows
            for test_id in enum_parity._exact_list(row[2], "executedTests")
        }
        self.assertEqual((len(all_rows), len(claimed_tests)), (465, 465))
        self.assertEqual(set(compiler_rows), claimed_evidence)
        self.assertEqual(all_tests, claimed_tests)
        enum_parity._write_lf_tsv(
            compiler_path,
            ("compilerEvidenceId", "publicSymbols"),
            list(compiler_rows.items()),
        )
        enum_parity._write_lf_tsv(
            tests_path,
            ("executedTestId", "status"),
            [(test, "passed") for test in all_tests],
        )
        for path in (compiler_path, tests_path):
            self.assertNotIn(b"\r", path.read_bytes())
            lines = path.read_text(encoding="utf-8").splitlines()[1:]
            self.assertEqual(lines, sorted(lines))


if __name__ == "__main__":
    unittest.main()
