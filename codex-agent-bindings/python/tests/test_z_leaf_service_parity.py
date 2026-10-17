from __future__ import annotations

import asyncio
import csv
import ctypes
import inspect
import json
import os
import re
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from typing import get_type_hints


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import codex_agent  # noqa: E402
from artifact_inputs import (  # noqa: E402
    c_abi_bootstrap_evidence,
    c_header,
    real_library,
)
from codex_agent._client import _Context  # noqa: E402
from codex_agent._ffi import (  # noqa: E402
    ConversationOpenOptionsStruct,
    Handle,
    HandlePointer,
    NativeLibrary,
    OperationCallback,
    StateCallback,
    StringView,
)
from codex_agent._errors import Status  # noqa: E402
import test_enum_parity as enum_parity  # noqa: E402
import test_ordinary_value_parity as ordinary_parity  # noqa: E402
from test_binding import (  # noqa: E402
    FakeLibrary,
    _set_handle,
    _set_i32,
    _set_i64,
    _set_size,
)


OWNER_PREFIX = "common|owner=io.github.codex_agent_labs.codexagent.agent/"
OWNERS = {
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
SNAKE = {
    "isAuthenticated": "is_authenticated",
    "isAuthenticating": "is_authenticating",
    "isAuthorizing": "is_authorizing",
    "isAvailable": "is_available",
    "openUrl": "open_url",
    "resolveEffort": "resolve_effort",
    "resolveServiceTier": "resolve_service_tier",
    "signOut": "sign_out",
}
SERVICE_STARTS = {
    "codex_agent_authentication_authenticate_api_key",
    "codex_agent_authentication_authenticate_chat_gpt_browser",
    "codex_agent_authentication_authenticate_chat_gpt_device_code",
    "codex_agent_authentication_cancel",
    "codex_agent_authentication_sign_out",
    "codex_agent_connectors_list",
    "codex_agent_hooks_install",
    "codex_agent_hooks_list",
    "codex_agent_hooks_trust",
    "codex_agent_hooks_uninstall",
    "codex_agent_integration_authorization_authorize",
    "codex_agent_integration_authorization_cancel",
    "codex_agent_interactions_open_url",
    "codex_agent_interactions_resolve_approval",
    "codex_agent_interactions_resolve_elicitation",
    "codex_agent_mcp_servers_add",
    "codex_agent_mcp_servers_list",
    "codex_agent_mcp_servers_remove",
    "codex_agent_models_list",
    "codex_agent_models_resolve",
    "codex_agent_models_resolve_effort",
    "codex_agent_models_resolve_service_tier",
    "codex_agent_plugins_install",
    "codex_agent_plugins_list",
    "codex_agent_plugins_read",
    "codex_agent_plugins_uninstall",
    "codex_agent_skills_install",
    "codex_agent_skills_list",
    "codex_agent_skills_read",
    "codex_agent_skills_uninstall",
}


def _owner(capability: str) -> str | None:
    return next(
        (owner for owner in OWNERS if capability.startswith(f"{OWNER_PREFIX}{owner}|")),
        None,
    )


def _member(capability: str) -> str:
    owner = _owner(capability)
    if owner is None:
        raise AssertionError(f"not a leaf-service capability: {capability}")
    marker = f"|abi=io.github.codex_agent_labs.codexagent.agent/{owner}."
    return capability.split(marker, 1)[1].split("|", 1)[0]


def _public_symbol(capability: str) -> str:
    owner = _owner(capability)
    member = _member(capability)
    if owner == "CodexInteractions" and member == "resolve":
        projected = (
            "resolve_approval"
            if "AgentPendingApproval" in capability
            else "resolve_elicitation"
        )
    else:
        projected = SNAKE.get(member, member)
    return f"codex_agent.{owner}.{projected}"


def _expected_scenarios(capability: str) -> tuple[str, ...]:
    member = _member(capability)
    scenarios = {"parent-child-ownership", "value-conversion"}
    if "|kind=function|" in capability:
        scenarios.add("async-success")
    if "StateFlow" in capability:
        scenarios.update(
            {
                "state-current-value",
                "state-subsequent-value",
                "subscription-cancellation",
                "terminal-delivery",
            }
        )
    if "kotlin.collections" in capability:
        scenarios.add("collection-immutability-ordering")
    if "?" in capability:
        scenarios.add("nullability")
    if member == "isAvailable":
        scenarios.add("repeated-close-dispose")
    if _owner(capability) == "CodexInteractions":
        scenarios.add("identity")
    if _owner(capability) == "CodexInteractions" and member in {"openUrl", "resolve"}:
        scenarios.add("cancellation")
    if member == "openUrl":
        scenarios.update({"async-failure", "structured-failure"})
    return tuple(sorted(scenarios))


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


def _selected_rows(rows: list[list[str]]) -> list[list[str]]:
    return [row for row in rows if _owner(row[0]) is not None]


def _validate_rows(rows: list[list[str]]) -> None:
    bootstrap, passed, header = _bootstrap()
    canonical = {key for key in bootstrap if _owner(key) is not None}
    if len(rows) != 42 or not all(len(row) == 5 and all(row) for row in rows):
        raise AssertionError("exactly 42 complete leaf-service claims are required")
    keys = [row[0] for row in rows]
    if keys != sorted(set(keys)) or set(keys) != canonical:
        raise AssertionError(
            "leaf-service claims contain a stale, missing, or duplicate key"
        )
    for index, row in enumerate(rows):
        capability, symbols, tests, evidence, scenarios = row
        claim = bootstrap[capability]
        if enum_parity._exact_list(symbols, "publicSymbols") != (
            _public_symbol(capability),
        ):
            raise AssertionError(f"stale Python projection: {capability}")
        if enum_parity._exact_list(tests, "executedTests") != (
            f"python.service:{index:03d}",
        ):
            raise AssertionError(f"stale executed-test ID: {capability}")
        expected_evidence = tuple(
            sorted(
                [f"c-header:{name}" for name in claim["headerReferences"]]
                + [f"cabi-fixture:{test}" for test in claim["nativeTestIds"]]
                + [f"python-analyzer-service:{index:03d}"]
            )
        )
        if (
            enum_parity._exact_list(evidence, "compilerEvidenceIds")
            != expected_evidence
        ):
            raise AssertionError(
                f"stale exact compiler/reference evidence: {capability}"
            )
        if enum_parity._exact_list(scenarios, "sharedScenarios") != _expected_scenarios(
            capability
        ):
            raise AssertionError(f"stale semantic scenarios: {capability}")
        for reference in claim["headerReferences"]:
            if not re.search(rf"\b{re.escape(reference)}\b", header):
                raise AssertionError(f"missing exact C header reference: {reference}")
        if not set(claim["nativeTestIds"]).issubset(passed):
            raise AssertionError(f"canonical C behavior did not pass: {capability}")


class LeafFakeLibrary(FakeLibrary):
    def __init__(self) -> None:
        super().__init__()
        self.state_terminal = True
        self.active_present = True
        self.service_tier_present = True
        self.handle_seed = 900

    def _fresh(self, pointer: object) -> None:
        self.handle_seed += 1
        _set_handle(pointer, self.handle_seed)

    def invoke(self, name: str, *args: object) -> int:
        if name in {
            "codex_agent_abi_version",
            "codex_agent_abi_is_compatible",
            "codex_agent_context_create",
            "codex_agent_context_destroy",
            "codex_agent_failure_is_recoverable",
            "codex_agent_operation_cancel",
            "codex_agent_operation_destroy",
            "codex_agent_operation_failure",
            "codex_agent_operation_result",
            "codex_agent_snapshot_destroy",
            "codex_agent_subscription_destroy",
        }:
            return super().invoke(name, *args)
        if name in SERVICE_STARTS:
            self.calls.append(name)
            callback, user_data, out = args[-3:]
            self._fresh(out)
            operation = Handle(self.handle_seed)
            if self.delay_operation:
                self.delayed_callback = (callback, user_data)
            else:
                callback(Handle(1), operation, user_data)
            return Status.OK
        if re.fullmatch(
            r"codex_agent_(authentication|integration_authorization|interactions)_"
            r"(state|is_authenticated|is_authenticating|active|is_authorizing|approvals|elicitations)_get",
            name,
        ):
            self.calls.append(name)
            self._fresh(args[-1])
            return Status.OK
        if re.fullmatch(
            r"codex_agent_(authentication|integration_authorization|interactions)_"
            r"(state|is_authenticated|is_authenticating|active|is_authorizing|approvals|elicitations)_subscribe",
            name,
        ):
            self.calls.append(name)
            callback, user_data, out = args[-3:]
            self._fresh(out)
            callback(
                Handle(1),
                Handle(self.handle_seed),
                Status.OK,
                Handle(self.handle_seed + 100),
                int(self.state_terminal),
                user_data,
            )
            return Status.OK
        if name.endswith("_is_available") and name.startswith("codex_agent_"):
            self.calls.append(name)
            _set_i32(args[-1], 1)
            return Status.OK
        if name in {
            "codex_agent_integration_authorization_state_target",
            "codex_agent_integration_authorization_state_failure",
        }:
            self.calls.append(name)
            return Status.NOT_READY
        if name.endswith("_copy"):
            self.calls.append(name)
            return self._copy(name, *args)
        if name in {
            "codex_agent_operation_connectors_count",
            "codex_agent_operation_models_count",
            "codex_agent_operation_mcp_servers_count",
        }:
            self.calls.append(name)
            _set_size(args[-1], 2)
            return Status.OK
        if name in {
            "codex_agent_interactions_approvals_count",
            "codex_agent_interactions_elicitations_count",
            "codex_agent_interaction_state_pending_count",
        }:
            self.calls.append(name)
            _set_size(args[-1], 1)
            return Status.OK
        if name.endswith("_count") or name.endswith("_count_at"):
            self.calls.append(name)
            _set_size(args[-1], 0)
            return Status.OK
        if name in {
            "codex_agent_skill_chunk_total_bytes",
            "codex_agent_hook_timeout_seconds",
        }:
            self.calls.append(name)
            _set_i64(args[-1], 0)
            return Status.OK
        if name in {
            "codex_agent_skill_chunk_next_offset",
            "codex_agent_form_field_minimum",
            "codex_agent_form_field_maximum",
            "codex_agent_form_field_minimum_length",
            "codex_agent_form_field_maximum_length",
            "codex_agent_form_field_minimum_selections",
            "codex_agent_form_field_maximum_selections",
            "codex_agent_form_field_format",
        }:
            self.calls.append(name)
            _set_i32(args[-2], 0)
            return Status.OK
        if name == "codex_agent_integration_authorization_active_has_value":
            self.calls.append(name)
            _set_i32(args[-1], int(self.active_present))
            return Status.OK
        if name == "codex_agent_operation_has_service_tier":
            self.calls.append(name)
            _set_i32(args[-1], int(self.service_tier_present))
            return Status.OK
        if name == "codex_agent_state_boolean_value":
            self.calls.append(name)
            _set_i32(args[-1], 1)
            return Status.OK
        if name.endswith("_contains"):
            self.calls.append(name)
            _set_i32(args[-1], 0)
            return Status.OK
        if any(
            marker in name
            for marker in (
                "_has_",
                "_is_",
                "_can_",
                "_status",
                "_kind",
                "_scope",
                "_origin",
                "_policy",
                "_freshness",
            )
        ):
            self.calls.append(name)
            _set_i32(args[-1], 0)
            return Status.OK
        if (
            name.endswith(("_create", "_acquire", "_at", "_value"))
            or "_from_" in name
            or name.startswith("codex_agent_operation_")
            or name.endswith(
                (
                    "_approval",
                    "_agent",
                    "_catalog",
                    "_command",
                    "_configuration",
                    "_connector",
                    "_conversation_id",
                    "_detail",
                    "_elicitation",
                    "_handler",
                    "_hook",
                    "_mcp_server",
                    "_model",
                    "_prompt",
                    "_reference",
                    "_server",
                    "_service_tier",
                    "_skill",
                    "_summary",
                    "_transport",
                )
            )
        ):
            self.calls.append(name)
            self._fresh(args[-1])
            return Status.OK
        return super().invoke(name, *args)

    def _copy(self, name: str, *args: object) -> int:
        values = {
            "codex_agent_connector_id_copy": b"connector",
            "codex_agent_connector_name_copy": b"Connector",
            "codex_agent_elicitation_request_id_copy": b"elicitation-1",
            "codex_agent_elicitation_server_name_copy": b"server",
            "codex_agent_mcp_server_name_copy": b"server",
            "codex_agent_mcp_server_display_name_copy": b"Server",
            "codex_agent_model_id_copy": b"model",
            "codex_agent_model_display_name_copy": b"Model",
            "codex_agent_pending_approval_request_id_copy": b"approval-1",
            "codex_agent_plugin_reference_id_copy": b"plugin-id",
            "codex_agent_plugin_reference_name_copy": b"plugin",
            "codex_agent_plugin_reference_marketplace_name_copy": b"market",
            "codex_agent_plugin_reference_uri_copy": b"plugin://plugin@market",
            "codex_agent_skill_name_copy": b"skill",
            "codex_agent_skill_display_name_copy": b"Skill",
            "codex_agent_skill_path_copy": b"skill.md",
        }
        value = values.get(name, b"fixture")
        buffer, capacity, required = args[-3:]
        _set_size(required, len(value))
        if len(value) > int(capacity):
            return Status.BUFFER_TOO_SMALL
        if value:
            ctypes.memmove(buffer, value, len(value))
        return Status.OK


class MissingSymbolLibrary:
    def __init__(self, missing: str) -> None:
        self.missing = missing
        self.delegate = LeafFakeLibrary()

    def __getattr__(self, name: str) -> object:
        if name == self.missing:
            raise AttributeError(name)
        return getattr(self.delegate, name)


def _make_service(owner: str) -> tuple[object, LeafFakeLibrary, _Context]:
    fake = LeafFakeLibrary()
    context = _Context(NativeLibrary(fake))
    service = getattr(codex_agent, owner)(context, Handle(50))
    return service, fake, context


def _fixture_model() -> codex_agent.Model:
    return codex_agent.Model("model", "Model", "", ("medium",), "medium", True)


def _fixture_plugin() -> codex_agent.PluginReference:
    return codex_agent.PluginReference("plugin-id", "plugin", "market")


def _fixture_connector() -> codex_agent.Connector:
    return codex_agent.Connector("connector", "Connector")


async def _exercise_state(stream: object, fake: LeafFakeLibrary) -> None:
    current = stream.current
    subscription = stream.subscribe()
    subsequent = await anext(subscription)
    with unittest.TestCase().assertRaises(StopAsyncIteration):
        await anext(subscription)
    self_check = unittest.TestCase()
    self_check.assertIsNotNone(current)
    self_check.assertIsNotNone(subsequent)
    fake.state_terminal = False
    cancellable = stream.subscribe()
    await anext(cancellable)
    await cancellable.aclose()
    await cancellable.aclose()


async def _exercise(capability: str) -> tuple[set[str], object]:
    owner = _owner(capability)
    assert owner is not None
    member = _member(capability)
    service, fake, context = _make_service(owner)
    result: object = None
    try:
        if owner == "CodexAuthentication":
            if member == "authenticate":
                await service.authenticate(codex_agent.ApiKeyAuthentication("secret"))
                await service.authenticate(codex_agent.CHAT_GPT_BROWSER_AUTHENTICATION)
                await service.authenticate(
                    codex_agent.CHAT_GPT_DEVICE_CODE_AUTHENTICATION
                )
            elif member in {"cancel", "signOut"}:
                await getattr(service, SNAKE.get(member, member))()
            else:
                result = getattr(service, SNAKE.get(member, member))
                await _exercise_state(result, fake)
        elif owner == "CodexConnectors":
            result = (
                service.is_available
                if member == "isAvailable"
                else await service.list(True)
            )
        elif owner == "CodexHooks":
            if member == "isAvailable":
                result = service.is_available
            elif member == "list":
                result = await service.list()
            elif member == "install":
                result = await service.install(
                    "hooks", codex_agent.InstallationScope.USER
                )
            else:
                hook = await service.install(
                    "hooks", codex_agent.InstallationScope.USER
                )
                await getattr(service, member)(hook)
        elif owner == "CodexIntegrationAuthorization":
            if member == "authorize":
                await service.authorize(
                    codex_agent.ConnectorIntegration(_fixture_connector())
                )
                await service.authorize(
                    codex_agent.McpServerIntegration(
                        codex_agent.McpServer(
                            "server", "Server", codex_agent.McpAuthStatus.UNKNOWN
                        )
                    )
                )
            elif member == "cancel":
                await service.cancel()
            else:
                result = getattr(service, SNAKE.get(member, member))
                await _exercise_state(result, fake)
                if member == "active":
                    fake.active_present = False
                    unittest.TestCase().assertIsNone(result.current)
        elif owner == "CodexInteractions":
            if "|kind=property|" in capability:
                result = getattr(service, member)
                await _exercise_state(result, fake)
            else:
                approval = service.approvals.current[0]
                elicitation = service.elicitations.current[0]
                if member == "openUrl":
                    await service.open_url(elicitation)
                    fake.next_operation_result = Status.OPERATION_FAILED
                    with unittest.TestCase().assertRaises(
                        codex_agent.OperationError
                    ) as failure:
                        await service.open_url(elicitation)
                    unittest.TestCase().assertEqual(
                        failure.exception.failure.code, "fixture"
                    )
                    fake.next_operation_result = Status.OK
                    fake.delay_operation = True
                    pending = asyncio.create_task(service.open_url(elicitation))
                elif "AgentPendingApproval" in capability:
                    await service.resolve_approval(
                        approval, codex_agent.ApprovalDecision.ACCEPT
                    )
                    with unittest.TestCase().assertRaises(ValueError):
                        await service.resolve_approval(
                            replace(approval), codex_agent.ApprovalDecision.ACCEPT
                        )
                    fake.delay_operation = True
                    pending = asyncio.create_task(
                        service.resolve_approval(
                            approval, codex_agent.ApprovalDecision.ACCEPT
                        )
                    )
                else:
                    response = codex_agent.ElicitationResponse(
                        codex_agent.ElicitationAction.DECLINE
                    )
                    await service.resolve_elicitation(elicitation, response)
                    with unittest.TestCase().assertRaises(ValueError):
                        await service.resolve_elicitation(
                            replace(elicitation), response
                        )
                    fake.delay_operation = True
                    pending = asyncio.create_task(
                        service.resolve_elicitation(elicitation, response)
                    )
                await asyncio.sleep(0)
                pending.cancel()
                with unittest.TestCase().assertRaises(asyncio.CancelledError):
                    await pending
                unittest.TestCase().assertTrue(fake.operation_cancelled)
                fake.complete_delayed()
                await asyncio.sleep(0)
        elif owner == "CodexMcpServers":
            if member == "isAvailable":
                result = service.is_available
            elif member == "list":
                result = await service.list()
            elif member == "add":
                result = await service.add(
                    codex_agent.McpServerConfiguration(
                        "server", codex_agent.McpStdioTransport("tool")
                    )
                )
            else:
                await service.remove((await service.list())[0])
        elif owner == "CodexModels":
            if member == "list":
                result = await service.list()
            elif member == "resolve":
                result = await service.resolve(codex_agent.Resolution.FIRST)
            elif member == "resolveEffort":
                result = await service.resolve_effort(_fixture_model())
            else:
                result = await service.resolve_service_tier(_fixture_model())
                fake.service_tier_present = False
                unittest.TestCase().assertIsNone(
                    await service.resolve_service_tier(_fixture_model())
                )
        elif owner == "CodexPlugins":
            if member == "isAvailable":
                result = service.is_available
            elif member == "list":
                result = await service.list(True)
            else:
                result = await getattr(service, member)(_fixture_plugin())
        elif owner == "CodexSkills":
            if member == "isAvailable":
                result = service.is_available
            elif member == "list":
                result = await service.list(True)
            elif member == "read":
                result = await service.read("skill.md", 7)
            elif member == "install":
                result = await service.install(
                    "skills", codex_agent.InstallationScope.WORKSPACE
                )
            else:
                await service.uninstall(
                    await service.install("skills", codex_agent.InstallationScope.USER)
                )
        await service.aclose()
        await service.aclose()
        return set(fake.calls), result
    finally:
        await service.aclose()
        await context.destroy()


def _real_library_path() -> Path:
    return real_library()


def _null_argument(argument_type: object) -> object:
    if argument_type is Handle:
        return Handle()
    if argument_type is ctypes.c_void_p:
        return None
    if isinstance(argument_type, type) and issubclass(argument_type, ctypes._Pointer):
        return None
    if isinstance(argument_type, type) and issubclass(argument_type, ctypes._CFuncPtr):
        return argument_type(lambda *unused: None)
    return 0


def _expected_argtypes(header: str, symbol: str) -> tuple[object, ...]:
    match = re.search(rf"\b{re.escape(symbol)}\s*\((.*?)\);", header, re.DOTALL)
    if match is None:
        raise AssertionError(f"missing declaration for {symbol}")
    parameters = tuple(
        " ".join(parameter.split())
        for parameter in match.group(1).split(",")
        if parameter.strip() and parameter.strip() != "void"
    )
    result: list[object] = []
    for parameter in parameters:
        declaration, name = parameter.rsplit(" ", 1)
        normalized = declaration.replace("const ", "").strip() + "*" * name.count("*")
        if normalized == "codex_agent_operation_callback_t":
            result.append(OperationCallback)
        elif normalized == "codex_agent_state_callback_t":
            result.append(StateCallback)
        elif normalized == "void*":
            result.append(ctypes.c_void_p)
        elif normalized == "codex_agent_string_view_t*":
            result.append(ctypes.POINTER(StringView))
        elif normalized == "codex_agent_conversation_open_options_t*":
            result.append(ctypes.POINTER(ConversationOpenOptionsStruct))
        elif normalized == "int32_t*":
            result.append(ctypes.POINTER(ctypes.c_int32))
        elif normalized == "int64_t*":
            result.append(ctypes.POINTER(ctypes.c_int64))
        elif normalized == "size_t*":
            result.append(ctypes.POINTER(ctypes.c_size_t))
        elif normalized == "uint8_t*":
            result.append(ctypes.POINTER(ctypes.c_uint8))
        elif normalized == "double*":
            result.append(ctypes.POINTER(ctypes.c_double))
        elif normalized == "codex_agent_status_t*":
            result.append(ctypes.POINTER(ctypes.c_int32))
        elif normalized.endswith("**"):
            result.append(HandlePointer)
        elif normalized.endswith("*"):
            result.append(Handle)
        elif normalized == "int32_t":
            result.append(ctypes.c_int32)
        elif normalized == "int64_t":
            result.append(ctypes.c_int64)
        elif normalized == "size_t":
            result.append(ctypes.c_size_t)
        elif normalized.startswith("codex_agent_") and normalized.endswith("_t"):
            result.append(ctypes.c_int32)
        else:
            raise AssertionError(f"unmapped parameter {parameter!r} for {symbol}")
    return tuple(result)


class LeafServiceParityTests(unittest.IsolatedAsyncioTestCase):
    def test_exact_inventory_public_surface_and_reference_evidence(self) -> None:
        rows = _selected_rows(ordinary_parity._claims())
        _validate_rows(rows)
        for capability, symbols, *_ in rows:
            owner = _owner(capability)
            assert owner is not None
            projected = _public_symbol(capability).rsplit(".", 1)[1]
            public = inspect.getattr_static(getattr(codex_agent, owner), projected)
            target = public.fget if isinstance(public, property) else public
            self.assertIsNotNone(target)
            self.assertIn("return", get_type_hints(target))

    async def test_each_capability_executes_exact_production_ctypes_calls(self) -> None:
        bootstrap, _, _ = _bootstrap()
        for row in _selected_rows(ordinary_parity._claims()):
            with self.subTest(capability=row[0]):
                calls, result = await _exercise(row[0])
                self.assertTrue(
                    set(bootstrap[row[0]]["headerReferences"]).issubset(calls),
                    set(bootstrap[row[0]]["headerReferences"]) - calls,
                )

    def test_real_sdk_executes_every_exact_symbol_at_fail_closed_null_boundary(
        self,
    ) -> None:
        path = _real_library_path()
        self.assertTrue(path.is_file(), f"real release SDK is required: {path}")
        native = NativeLibrary(ctypes.CDLL(path))
        bootstrap, _, header = _bootstrap()
        executed: set[str] = set()
        for row in _selected_rows(ordinary_parity._claims()):
            for symbol in bootstrap[row[0]]["headerReferences"]:
                function = native.function(symbol)
                self.assertEqual(
                    tuple(function.argtypes), _expected_argtypes(header, symbol)
                )
                status = int(
                    function(*(_null_argument(arg) for arg in function.argtypes))
                )
                self.assertNotEqual(status, int(Status.OK), symbol)
                executed.add(symbol)
        self.assertEqual(
            executed,
            {
                symbol
                for row in _selected_rows(ordinary_parity._claims())
                for symbol in bootstrap[row[0]]["headerReferences"]
            },
        )

    def test_stale_missing_fallback_and_claimed_call_evidence_fail_closed(self) -> None:
        rows = _selected_rows(ordinary_parity._claims())
        _validate_rows(rows)
        for candidate in (
            rows[:-1],
            [*rows[:-1], rows[-2]],
            [["removed", *rows[0][1:]], *rows[1:]],
        ):
            with self.assertRaises(AssertionError):
                _validate_rows(candidate)
        for column, stale in (
            (1, "codex_agent.Fallback.local"),
            (2, "python.service:999"),
            (3, "python-analyzer-service:999"),
            (4, "value-conversion"),
        ):
            candidate = [row[:] for row in rows]
            candidate[0][column] = stale
            with self.assertRaises(AssertionError):
                _validate_rows(candidate)
        bootstrap, _, _ = _bootstrap()
        calls, _ = asyncio.run(_exercise(rows[0][0]))
        calls.remove(bootstrap[rows[0][0]]["headerReferences"][0])
        self.assertFalse(set(bootstrap[rows[0][0]]["headerReferences"]).issubset(calls))
        with self.assertRaises(AttributeError):
            NativeLibrary(
                MissingSymbolLibrary(bootstrap[rows[0][0]]["headerReferences"][0])
            )

    async def test_z_complete_518_row_evidence_is_exact(self) -> None:
        rows = _selected_rows(ordinary_parity._claims())
        _validate_rows(rows)
        bootstrap, _, _ = _bootstrap()
        compiler_additions: dict[str, set[str]] = {}
        executed_additions: set[str] = set()
        for row in rows:
            calls, _ = await _exercise(row[0])
            self.assertTrue(set(bootstrap[row[0]]["headerReferences"]).issubset(calls))
            symbol = enum_parity._exact_list(row[1], "publicSymbols")[0]
            executed_additions.update(enum_parity._exact_list(row[2], "executedTests"))
            for evidence_id in enum_parity._exact_list(row[3], "compilerEvidenceIds"):
                compiler_additions.setdefault(evidence_id, set()).add(symbol)

        compiler_path = enum_parity.EVIDENCE_DIRECTORY / "compiler-evidence.tsv"
        with compiler_path.open(newline="", encoding="utf-8") as evidence_file:
            reader = csv.reader(evidence_file, delimiter="\t", strict=True)
            self.assertEqual(next(reader), ["compilerEvidenceId", "publicSymbols"])
            compiler_rows = {
                evidence_id: set(symbols.split(",")) for evidence_id, symbols in reader
            }
        for evidence_id, symbols in compiler_additions.items():
            compiler_rows.setdefault(evidence_id, set()).update(symbols)

        tests_path = enum_parity.EVIDENCE_DIRECTORY / "executed-tests.tsv"
        with tests_path.open(newline="", encoding="utf-8") as evidence_file:
            reader = csv.reader(evidence_file, delimiter="\t", strict=True)
            self.assertEqual(next(reader), ["executedTestId", "status"])
            all_tests = {test for test, status in reader if status == "passed"}
        all_tests.update(executed_additions)

        all_rows = [
            row
            for row in ordinary_parity._claims()
            if not row[0].startswith(f"{OWNER_PREFIX}CodexConversation")
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
        self.assertEqual((len(all_rows), len(claimed_tests)), (518, 518))
        self.assertEqual(set(compiler_rows), claimed_evidence)
        self.assertEqual(all_tests, claimed_tests)
        enum_parity._write_lf_tsv(
            compiler_path,
            ("compilerEvidenceId", "publicSymbols"),
            [
                (evidence_id, ",".join(sorted(symbols)))
                for evidence_id, symbols in compiler_rows.items()
            ],
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
