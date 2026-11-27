from __future__ import annotations

import csv
import inspect
import json
import re
import sys
import unittest
from collections import defaultdict
from pathlib import Path
from typing import get_type_hints
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import codex_agent  # noqa: E402
from artifact_inputs import (  # noqa: E402
    canonical_api_report,
    c_abi_bootstrap_evidence,
    c_header,
)
from codex_agent._ffi import NativeLibrary  # noqa: E402
import test_enum_parity as enum_parity  # noqa: E402
import test_ordinary_value_parity as ordinary_parity  # noqa: E402
import test_residual_value_parity as residual_parity  # noqa: E402


OWNER_PREFIX = "common|owner=io.github.codex_agent_labs.codexagent.agent/"
OWNERS = {
    "AgentElicitationResponse.Companion",
    "AgentElicitation",
    "AgentFormField",
    "AgentInteractionState",
    "CodexAuthorizationUrl.Companion",
}
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
SYMBOLS = {
    "AgentElicitationResponse.Companion.cancel": "codex_agent.ElicitationResponse.cancel",
    "AgentElicitationResponse.Companion.decline": "codex_agent.ElicitationResponse.decline",
    "AgentElicitation.accepts": "codex_agent.Elicitation.accepts",
    "AgentElicitation.accept": "codex_agent.Elicitation.accept",
    "AgentElicitation.initialValues": "codex_agent.Elicitation.initial_values",
    "AgentElicitation.validate": "codex_agent.Elicitation.validate",
    "AgentFormField.accepts": "codex_agent.FormField.accepts",
    "AgentInteractionState.isResolving": "codex_agent.InteractionState.is_resolving",
    "AgentInteractionState.pendingFor": "codex_agent.InteractionState.pending_for",
    "CodexAuthorizationUrl.Companion.chatGpt": "codex_agent.AuthorizationUrl.chat_gpt",
    "CodexAuthorizationUrl.Companion.external": "codex_agent.AuthorizationUrl.external",
}
CALL_SYMBOLS = {
    "AgentElicitationResponse.Companion.cancel": "codex_agent_elicitation_response_cancel",
    "AgentElicitationResponse.Companion.decline": "codex_agent_elicitation_response_decline",
    "AgentElicitation.accepts": "codex_agent_elicitation_accepts",
    "AgentElicitation.accept": "codex_agent_elicitation_accept",
    "AgentElicitation.initialValues": "codex_agent_elicitation_initial_values",
    "AgentElicitation.validate": "codex_agent_elicitation_validate",
    "AgentFormField.accepts": "codex_agent_form_field_accepts",
    "AgentInteractionState.isResolving": "codex_agent_interaction_state_is_resolving",
    "AgentInteractionState.pendingFor": "codex_agent_interaction_state_pending_for",
    "CodexAuthorizationUrl.Companion.chatGpt": "codex_agent_authorization_url_chat_gpt",
    "CodexAuthorizationUrl.Companion.external": "codex_agent_authorization_url_external",
}
PARAMETERS = {
    "AgentElicitationResponse.Companion.cancel": (),
    "AgentElicitationResponse.Companion.decline": (),
    "AgentElicitation.accepts": ("self", "response"),
    "AgentElicitation.accept": ("self", "content"),
    "AgentElicitation.initialValues": ("self",),
    "AgentElicitation.validate": ("self", "content"),
    "AgentFormField.accepts": ("self", "value"),
    "AgentInteractionState.isResolving": ("self", "interaction"),
    "AgentInteractionState.pendingFor": ("self", "conversation_id"),
    "CodexAuthorizationUrl.Companion.chatGpt": ("value",),
    "CodexAuthorizationUrl.Companion.external": ("value",),
}


def _owner(capability: str) -> str | None:
    return next(
        (owner for owner in OWNERS if capability.startswith(f"{OWNER_PREFIX}{owner}|")),
        None,
    )


def _function_name(capability: str) -> str:
    marker = "|abi=io.github.codex_agent_labs.codexagent.agent/"
    return capability.split(marker, 1)[1].split("|", 1)[0]


def _canonical_functions() -> set[str]:
    report = json.loads(
        canonical_api_report().read_text(encoding="utf-8")
    )
    return {
        capability
        for owner in report["owners"]
        if owner["name"].rsplit("/", 1)[-1] in OWNERS
        for capability in owner["capabilities"]
        if "|kind=function|" in capability
    }


def _selected_rows(rows: list[list[str]]) -> list[list[str]]:
    return [
        row
        for row in rows
        if "|kind=function|" in row[0] and _owner(row[0]) is not None
    ]


def _bootstrap() -> tuple[dict[str, dict[str, object]], set[str], str]:
    report = json.loads(
        c_abi_bootstrap_evidence().read_text(encoding="utf-8")
    )
    return (
        {claim["capabilityKey"]: claim for claim in report["claims"]},
        {
            test["testId"]
            for test in report["nativeTests"]
            if test["status"] == "passed"
        },
        c_header().read_text(encoding="utf-8"),
    )


def _validate_rows(rows: list[list[str]], canonical: set[str]) -> None:
    if len(rows) != 11 or not all(len(row) == 5 and all(row) for row in rows):
        raise AssertionError(
            "exactly 11 complete synchronous-function claims are required"
        )
    keys = [row[0] for row in rows]
    if keys != sorted(set(keys)) or set(keys) != canonical:
        raise AssertionError(
            "function claims contain a stale, missing, or duplicate key"
        )
    if {_function_name(row[0]) for row in rows} != set(SYMBOLS):
        raise AssertionError("function symbol map is stale")


def _verify_reference_row(
    row: list[str],
    bootstrap_claims: dict[str, dict[str, object]],
    passed_native_tests: set[str],
    header: str,
) -> tuple[str, ...]:
    capability, symbol_cell, test_cell, evidence_cell, scenario_cell = row
    symbol = SYMBOLS[_function_name(capability)]
    if enum_parity._exact_list(symbol_cell, "publicSymbols") != (symbol,):
        raise AssertionError(f"inexact Python function symbol for {capability}")
    tests = enum_parity._exact_list(test_cell, "executedTests")
    if len(tests) != 1 or not re.fullmatch(r"python\.function:\d{3}", tests[0]):
        raise AssertionError(f"inexact Python function test for {capability}")
    suffix = tests[0].rsplit(":", 1)[1]
    analyzer = f"python-analyzer-function:{suffix}"
    bootstrap = bootstrap_claims.get(capability)
    if bootstrap is None:
        raise AssertionError(f"missing C ABI bootstrap claim: {capability}")
    call_symbol = CALL_SYMBOLS[_function_name(capability)]
    if call_symbol not in bootstrap["headerReferences"]:
        raise AssertionError(f"stale native-call connection: {call_symbol}")
    expected = {
        *(f"c-header:{name}" for name in bootstrap["headerReferences"]),
        *(f"cabi-fixture:{test}" for test in bootstrap["nativeTestIds"]),
        analyzer,
    }
    evidence = enum_parity._exact_list(evidence_cell, "compilerEvidenceIds")
    if set(evidence) != expected:
        raise AssertionError(f"inexact compiler/bootstrap evidence for {capability}")
    for evidence_id in evidence:
        if evidence_id.startswith("c-header:"):
            name = evidence_id.removeprefix("c-header:")
            if re.search(rf"\b{re.escape(name)}\s*\(", header) is None:
                raise AssertionError(f"stale C-header evidence: {evidence_id}")
        elif evidence_id.startswith("cabi-fixture:"):
            if evidence_id.removeprefix("cabi-fixture:") not in passed_native_tests:
                raise AssertionError(f"stale C ABI fixture evidence: {evidence_id}")
        elif evidence_id != analyzer:
            raise AssertionError(f"stale Python analyzer evidence: {evidence_id}")
    expected_scenarios = {"value-conversion"}
    if _function_name(capability) in {
        "AgentElicitation.accept",
        "AgentElicitation.initialValues",
        "AgentElicitation.validate",
        "AgentInteractionState.pendingFor",
    }:
        expected_scenarios.add("collection-immutability-ordering")
    if _function_name(capability) == "AgentFormField.accepts":
        expected_scenarios.add("nullability")
    if (
        set(enum_parity._exact_list(scenario_cell, "sharedScenarios"))
        != expected_scenarios
    ):
        raise AssertionError(f"inexact shared scenarios for {capability}")
    resolved = eval(
        compile(symbol, f"<{tests[0]}>", "eval"), {"codex_agent": codex_agent}
    )
    if not callable(resolved):
        raise AssertionError(f"Python function symbol is not callable: {symbol}")
    signature = inspect.signature(resolved)
    if tuple(signature.parameters) != PARAMETERS[_function_name(capability)]:
        raise AssertionError(f"inexact Python function signature for {capability}")
    if signature.return_annotation is inspect.Signature.empty or any(
        parameter.annotation is inspect.Parameter.empty
        for name, parameter in signature.parameters.items()
        if name != "self"
    ):
        raise AssertionError(f"missing Python function type evidence for {capability}")
    hints = get_type_hints(resolved)
    if "return" not in hints or any(
        name not in hints for name in signature.parameters if name != "self"
    ):
        raise AssertionError(
            f"unresolvable Python function type evidence for {capability}"
        )
    return evidence


class SynchronousValueFunctionParityTests(unittest.TestCase):
    def _fixture(self) -> tuple[codex_agent.Elicitation, dict[str, object]]:
        defaults = ["alpha"]
        fields = (
            codex_agent.FormField(
                "name",
                "Name",
                codex_agent.FormFieldType.STRING,
                is_required=True,
                default_value=codex_agent.FormTextValue("Codex"),
            ),
            codex_agent.FormField(
                "choices",
                "Choices",
                codex_agent.FormFieldType.MULTI_SELECT,
                is_required=True,
                default_value=codex_agent.FormTextListValue(defaults),
                options=(
                    codex_agent.FormOption("alpha"),
                    codex_agent.FormOption("beta"),
                ),
            ),
        )
        elicitation = codex_agent.Elicitation(
            "request",
            codex_agent.ConversationId("conversation"),
            "server",
            "Choose",
            form=fields,
        )
        return elicitation, {
            "name": codex_agent.FormTextValue("Codex"),
            "choices": codex_agent.FormTextListValue(("alpha",)),
        }

    def _assert_behavior(self, test_id: str) -> None:
        elicitation, content = self._fixture()
        if test_id == "python.function:000":
            response = codex_agent.ElicitationResponse.cancel()
            self.assertEqual(response.action, codex_agent.ElicitationAction.CANCEL)
            self.assertEqual(dict(response.content), {})
        elif test_id == "python.function:001":
            response = codex_agent.ElicitationResponse.decline()
            self.assertEqual(response.action, codex_agent.ElicitationAction.DECLINE)
            self.assertEqual(dict(response.content), {})
        elif test_id == "python.function:002":
            self.assertTrue(elicitation.accepts(elicitation.accept(content)))
            self.assertFalse(
                elicitation.accepts(
                    codex_agent.ElicitationResponse(
                        codex_agent.ElicitationAction.ACCEPT
                    )
                )
            )
            for action in (
                codex_agent.ElicitationAction.DECLINE,
                codex_agent.ElicitationAction.CANCEL,
            ):
                self.assertTrue(
                    elicitation.accepts(codex_agent.ElicitationResponse(action))
                )
                self.assertFalse(
                    elicitation.accepts(
                        codex_agent.ElicitationResponse(action, content)
                    )
                )
        elif test_id == "python.function:003":
            mutable_content = dict(content)
            response = elicitation.accept(mutable_content)
            self.assertEqual(response.action, codex_agent.ElicitationAction.ACCEPT)
            self.assertIsNot(response.content, content)
            self.assertEqual(tuple(response.content), ("name", "choices"))
            mutable_content.clear()
            self.assertEqual(tuple(response.content), ("name", "choices"))
            with self.assertRaises(TypeError):
                response.content["other"] = codex_agent.FormTextValue("changed")  # type: ignore[index]
            with self.assertRaises(ValueError):
                elicitation.accept({})
        elif test_id == "python.function:004":
            values = elicitation.initial_values()
            self.assertEqual(values, content)
            self.assertIsNot(values["choices"], elicitation.form[1].default_value)
            with self.assertRaises(TypeError):
                values["name"] = codex_agent.FormTextValue("changed")  # type: ignore[index]
            duplicate = codex_agent.Elicitation(
                "duplicates",
                codex_agent.ConversationId("conversation"),
                "server",
                "Choose",
                form=(
                    codex_agent.FormField(
                        "same",
                        "First",
                        codex_agent.FormFieldType.STRING,
                        default_value=codex_agent.FormTextValue("first"),
                    ),
                    codex_agent.FormField(
                        "other",
                        "Other",
                        codex_agent.FormFieldType.STRING,
                        default_value=codex_agent.FormTextValue("other"),
                    ),
                    codex_agent.FormField(
                        "same",
                        "Last",
                        codex_agent.FormFieldType.STRING,
                        default_value=codex_agent.FormTextValue("last"),
                    ),
                ),
            ).initial_values()
            self.assertEqual(tuple(duplicate), ("same", "other"))
            self.assertEqual(duplicate["same"], codex_agent.FormTextValue("last"))
        elif test_id == "python.function:005":
            validation = elicitation.validate(
                {"unknown": codex_agent.FormTextValue("value")}
            )
            self.assertEqual(
                [(issue.field_name, issue.reason) for issue in validation.issues],
                [
                    ("unknown", codex_agent.ElicitationValidationReason.UNKNOWN_FIELD),
                    ("name", codex_agent.ElicitationValidationReason.MISSING_REQUIRED),
                    (
                        "choices",
                        codex_agent.ElicitationValidationReason.MISSING_REQUIRED,
                    ),
                ],
            )
        elif test_id == "python.function:006":
            self._assert_form_rules()
        elif test_id == "python.function:007":
            approval = codex_agent.PendingApproval(
                "request",
                codex_agent.ConversationId("conversation"),
                "Title",
                "Details",
            )
            state = codex_agent.InteractionState((approval,), {"request"})
            equal_copy = codex_agent.PendingApproval(
                "request",
                codex_agent.ConversationId("conversation"),
                "Title",
                "Details",
            )
            self.assertTrue(state.is_resolving(approval))
            self.assertFalse(state.is_resolving(equal_copy))
            self.assertFalse(
                codex_agent.InteractionState((approval,), ()).is_resolving(approval)
            )
        elif test_id == "python.function:008":
            conversation = codex_agent.ConversationId("conversation")
            first = codex_agent.PendingApproval("one", conversation, "One", "1")
            other = codex_agent.PendingApproval(
                "two", codex_agent.ConversationId("other"), "Two", "2"
            )
            state = codex_agent.InteractionState((first, other, first))
            selected = state.pending_for(codex_agent.ConversationId("conversation"))
            self.assertEqual(selected, (first, first))
            self.assertIs(selected[0], selected[1])
        elif test_id == "python.function:009":
            url = codex_agent.AuthorizationUrl.chat_gpt(
                "https://auth.openai.com/authorize?secret=do-not-print"
            )
            self.assertEqual(url.purpose, codex_agent.AuthorizationPurpose.CHAT_GPT)
            self.assertEqual(repr(url), "AuthorizationUrl(purpose=CHAT_GPT)")
            self.assertNotIn("do-not-print", repr(url))
            self.assertNotIn("do-not-print", str(url))
            for invalid in (
                "http://openai.com/",
                "https://openai.com.evil.example/",
                "https://user@openai.com/",
                "https://openai.com:444/",
                "https://.openai.com/",
                "https://openai.com./",
            ):
                with self.assertRaises(ValueError):
                    codex_agent.AuthorizationUrl.chat_gpt(invalid)
        elif test_id == "python.function:010":
            for valid in (
                "https://accounts.example.com/oauth",
                "http://localhost:8787/callback",
                "http://127.0.0.1/callback",
                "http://[::1]:8787/callback",
            ):
                self.assertEqual(
                    codex_agent.AuthorizationUrl.external(valid).value, valid
                )
            for invalid in (
                "http://192.168.1.2/login",
                "ftp://accounts.example.com/login",
                "https://user@accounts.example.com/login",
                "https://accounts.example.com:0/login",
                "https://accounts.example.com:65536/login",
                "https://accounts.example.com\\@evil.example/login",
                "https://accounts.example.com/space here",
                "https://accounts.example.com:\t/login",
            ):
                with self.assertRaises(ValueError):
                    codex_agent.AuthorizationUrl.external(invalid)
        else:
            self.fail(f"unknown function behavior ID: {test_id}")

    def _assert_form_rules(self) -> None:
        option = codex_agent.FormOption("alpha")
        optional = codex_agent.FormField(
            "optional", "Optional", codex_agent.FormFieldType.STRING
        )
        required = codex_agent.FormField(
            "required",
            "Required",
            codex_agent.FormFieldType.STRING,
            is_required=True,
        )
        self.assertTrue(optional.accepts(None))
        self.assertFalse(required.accepts(None))
        cases = (
            (
                codex_agent.FormField(
                    "text",
                    "Text",
                    codex_agent.FormFieldType.STRING,
                    is_required=True,
                    minimum_length=2,
                    maximum_length=3,
                ),
                codex_agent.FormTextValue("ab"),
                codex_agent.FormTextValue(" "),
            ),
            (
                codex_agent.FormField(
                    "number",
                    "Number",
                    codex_agent.FormFieldType.NUMBER,
                    minimum=1,
                    maximum=2,
                ),
                codex_agent.FormNumberValue(1.5),
                codex_agent.FormNumberValue(float("nan")),
            ),
            (
                codex_agent.FormField(
                    "integer", "Integer", codex_agent.FormFieldType.INTEGER
                ),
                codex_agent.FormNumberValue(2),
                codex_agent.FormNumberValue(1.5),
            ),
            (
                codex_agent.FormField(
                    "boolean", "Boolean", codex_agent.FormFieldType.BOOLEAN
                ),
                codex_agent.FormBooleanValue(False),
                codex_agent.FormTextValue("false"),
            ),
            (
                codex_agent.FormField(
                    "single",
                    "Single",
                    codex_agent.FormFieldType.SINGLE_SELECT,
                    options=(option,),
                ),
                codex_agent.FormTextValue("alpha"),
                codex_agent.FormTextValue("other"),
            ),
            (
                codex_agent.FormField(
                    "multi",
                    "Multi",
                    codex_agent.FormFieldType.MULTI_SELECT,
                    options=(option,),
                    minimum_selections=1,
                    maximum_selections=1,
                ),
                codex_agent.FormTextListValue(("alpha",)),
                codex_agent.FormTextListValue(("alpha", "alpha")),
            ),
        )
        for field, accepted, rejected in cases:
            self.assertTrue(field.accepts(accepted), field.name)
            self.assertFalse(field.accepts(rejected), field.name)
        bounded_text = codex_agent.FormField(
            "text",
            "Text",
            codex_agent.FormFieldType.STRING,
            minimum_length=2,
            maximum_length=3,
        )
        self.assertFalse(bounded_text.accepts(codex_agent.FormBooleanValue(True)))
        self.assertFalse(bounded_text.accepts(codex_agent.FormTextValue("a")))
        self.assertFalse(bounded_text.accepts(codex_agent.FormTextValue("abcd")))
        self.assertTrue(bounded_text.accepts(codex_agent.FormTextValue("😀")))
        bounded_number = codex_agent.FormField(
            "number",
            "Number",
            codex_agent.FormFieldType.NUMBER,
            minimum=1,
            maximum=2,
        )
        for rejected in (
            codex_agent.FormTextValue("1"),
            codex_agent.FormNumberValue(float("inf")),
            codex_agent.FormNumberValue(float("-inf")),
            codex_agent.FormNumberValue(0),
            codex_agent.FormNumberValue(3),
        ):
            self.assertFalse(bounded_number.accepts(rejected))
        single_other = codex_agent.FormField(
            "single",
            "Single",
            codex_agent.FormFieldType.SINGLE_SELECT,
            options=(option,),
            allows_other=True,
        )
        self.assertTrue(single_other.accepts(codex_agent.FormTextValue("other")))
        self.assertFalse(single_other.accepts(codex_agent.FormTextValue(" ")))
        multi = codex_agent.FormField(
            "multi",
            "Multi",
            codex_agent.FormFieldType.MULTI_SELECT,
            options=(option,),
            is_required=True,
            minimum_selections=1,
            maximum_selections=2,
        )
        for rejected in (
            codex_agent.FormTextValue("alpha"),
            codex_agent.FormTextListValue(()),
            codex_agent.FormTextListValue(("alpha", "alpha")),
            codex_agent.FormTextListValue(("alpha", "other")),
            codex_agent.FormTextListValue(("alpha", "beta", "gamma")),
        ):
            self.assertFalse(multi.accepts(rejected))
        multi_other = codex_agent.FormField(
            "multi",
            "Multi",
            codex_agent.FormFieldType.MULTI_SELECT,
            options=(option,),
            allows_other=True,
        )
        self.assertTrue(
            multi_other.accepts(codex_agent.FormTextListValue(("alpha", "other")))
        )
        self.assertFalse(
            multi_other.accepts(codex_agent.FormTextListValue(("alpha", " ")))
        )
        for format, accepted, rejected in (
            (codex_agent.FormStringFormat.EMAIL, "a@b", "a@@b"),
            (codex_agent.FormStringFormat.URI, "https:value", "1https:value"),
            (codex_agent.FormStringFormat.DATE, "2024-02-29", "2023-02-29"),
            (
                codex_agent.FormStringFormat.DATE_TIME,
                "2024-02-29T23:59:60Z",
                "2024-02-29T24:00:00Z",
            ),
        ):
            field = codex_agent.FormField(
                "formatted",
                "Formatted",
                codex_agent.FormFieldType.STRING,
                format=format,
            )
            self.assertTrue(field.accepts(codex_agent.FormTextValue(accepted)))
            self.assertFalse(field.accepts(codex_agent.FormTextValue(rejected)))
        for invalid_date_time in (
            "2024- 1-01",
            "2024-01-01T 1:00:00Z",
            "2024-01-01T01:00:00+ 1:00",
            "2024-01-01T01:00:00.Z",
        ):
            format = (
                codex_agent.FormStringFormat.DATE
                if "T" not in invalid_date_time
                else codex_agent.FormStringFormat.DATE_TIME
            )
            self.assertFalse(
                codex_agent.FormField(
                    "formatted",
                    "Formatted",
                    codex_agent.FormFieldType.STRING,
                    format=format,
                ).accepts(codex_agent.FormTextValue(invalid_date_time))
            )

    def test_exact_projection_behavior_and_complete_evidence(self) -> None:
        residual_parity.ResidualValueParityTests(
            "test_exact_public_projection_behavior_and_complete_evidence"
        ).test_exact_public_projection_behavior_and_complete_evidence()

        rows = _selected_rows(ordinary_parity._claims())
        canonical = _canonical_functions()
        _validate_rows(rows, canonical)
        bootstrap, passed, header = _bootstrap()
        executed_tests: set[str] = set()
        compiler_evidence: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            evidence = _verify_reference_row(row, bootstrap, passed, header)
            test_id = enum_parity._exact_list(row[2], "executedTests")[0]
            self.assertNotIn(test_id, executed_tests)
            called: list[str] = []
            original_call = NativeLibrary.call

            def recording_call(
                native: NativeLibrary, name: str, *arguments: object, **keywords: object
            ) -> object:
                called.append(name)
                return original_call(native, name, *arguments, **keywords)

            with self.subTest(capability=row[0]):
                with mock.patch.object(NativeLibrary, "call", recording_call):
                    self._assert_behavior(test_id)
                self.assertIn(CALL_SYMBOLS[_function_name(row[0])], called)
            executed_tests.add(test_id)
            symbol = enum_parity._exact_list(row[1], "publicSymbols")[0]
            for evidence_id in evidence:
                compiler_evidence[evidence_id].add(symbol)

        compiler_path = enum_parity.EVIDENCE_DIRECTORY / "compiler-evidence.tsv"
        with compiler_path.open(newline="", encoding="utf-8") as evidence_file:
            reader = csv.reader(evidence_file, delimiter="\t", strict=True)
            self.assertEqual(next(reader), ["compilerEvidenceId", "publicSymbols"])
            compiler_rows = dict(reader)
        for evidence_id, symbols in compiler_evidence.items():
            if evidence_id in compiler_rows:
                prior = set(compiler_rows[evidence_id].split(","))
                self.assertTrue(prior.isdisjoint(symbols), evidence_id)
                symbols.update(prior)
            compiler_rows[evidence_id] = ",".join(sorted(symbols))

        tests_path = enum_parity.EVIDENCE_DIRECTORY / "executed-tests.tsv"
        with tests_path.open(newline="", encoding="utf-8") as evidence_file:
            reader = csv.reader(evidence_file, delimiter="\t", strict=True)
            self.assertEqual(next(reader), ["executedTestId", "status"])
            all_tests = {test for test, status in reader if status == "passed"}
        self.assertTrue(all_tests.isdisjoint(executed_tests))
        all_tests.update(executed_tests)

        inventory = ordinary_parity._claims()
        self.assertEqual(len(inventory), 556)
        all_rows = [
            row
            for row in inventory
            if not any(
                row[0].startswith(f"{OWNER_PREFIX}{owner}|")
                for owner in LEAF_SERVICE_OWNERS
                | {
                    "CodexAgent",
                    "CodexConversation",
                    "CodexConversations",
                    "CodexHost",
                    "CodexHostState.Ready",
                }
            )
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
        self.assertEqual((len(all_rows), len(claimed_tests)), (476, 476))
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

    def test_stale_missing_duplicate_and_reference_evidence_fail_closed(self) -> None:
        rows = _selected_rows(ordinary_parity._claims())
        canonical = _canonical_functions()
        _validate_rows(rows, canonical)
        for candidate in (
            rows[:-1],
            [*rows[:-1], rows[-2]],
            [*rows[:-1], ["removed", *rows[-1][1:]]],
        ):
            with self.assertRaises(AssertionError):
                _validate_rows(candidate, canonical)
        bootstrap, passed, header = _bootstrap()
        for prefix, replacement in (
            ("c-header:", "c-header:codex_agent_removed_function"),
            ("cabi-fixture:", "cabi-fixture:removed.native.test#stale[macosArm64]"),
            ("python-analyzer-function:", "python-analyzer-function:999"),
        ):
            candidate = next(row for row in rows if prefix in row[3])
            candidate = [*candidate]
            old = next(
                item for item in candidate[3].split(",") if item.startswith(prefix)
            )
            candidate[3] = candidate[3].replace(old, replacement)
            with self.assertRaises(AssertionError):
                _verify_reference_row(candidate, bootstrap, passed, header)
        for index, replacement in (
            (1, "codex_agent.Removed.function"),
            (2, "python.function:999"),
            (4, "remote-execution"),
        ):
            candidate = [*rows[0]]
            candidate[index] = replacement
            with self.assertRaises(AssertionError):
                _verify_reference_row(candidate, bootstrap, passed, header)
        function = _function_name(rows[0][0])
        exact_call = CALL_SYMBOLS[function]
        try:
            CALL_SYMBOLS[function] = "codex_agent_removed_function"
            with self.assertRaises(AssertionError):
                _verify_reference_row(rows[0], bootstrap, passed, header)
        finally:
            CALL_SYMBOLS[function] = exact_call
        with mock.patch(
            "codex_agent._ffi.resolve_library_path",
            side_effect=FileNotFoundError("missing verified C SDK"),
        ):
            with self.assertRaisesRegex(FileNotFoundError, "missing verified C SDK"):
                codex_agent.ElicitationResponse.cancel()


if __name__ == "__main__":
    unittest.main()
