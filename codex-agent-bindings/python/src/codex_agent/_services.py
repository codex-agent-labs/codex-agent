from __future__ import annotations

import ctypes
from collections.abc import Callable, Sequence
from typing import TypeVar

from ._async import StateStream, run_operation
from ._client import _Context, _OwnedHandle, _failure, _stream
from ._enums import (
    ApprovalDecision,
    AuthenticationStatus,
    AuthorizationPurpose,
    CatalogFreshness,
    FormFieldType,
    FormStringFormat,
    HookTrustStatus,
    InstallationScope,
    IntegrationAuthorizationStatus,
    PluginAuthPolicy,
    PluginInstallPolicy,
    Resolution,
    ResourceOrigin,
    SkillScope,
)
from ._errors import Status
from ._ffi import Handle, NativeLibrary, StringView, null_view, utf8_view
from ._mcp_native import create_mcp_configuration, create_mcp_server, read_owned_mcp_server
from ._mcp_values import McpServer, McpServerConfiguration
from ._models import ConversationId
from ._residual_values import (
    CHAT_GPT_BROWSER_AUTHENTICATION,
    ApiKeyAuthentication,
    AuthenticationState,
    AuthorizationUrl,
    ChatGptBrowserAuthentication,
    ChatGptDeviceCodeAuthentication,
    ConnectorIntegration,
    Elicitation,
    ElicitationResponse,
    FormField,
    Hook,
    HookCatalog,
    HookHandlerAgent,
    HookHandlerCommand,
    HookHandlerMcpTool,
    HookHandlerPrompt,
    IntegrationAuthorizationState,
    IntegrationValue,
    InteractionState,
    McpServerIntegration,
    PendingApproval,
    PendingElicitation,
    PendingInteractionValue,
)
from ._value_native import _create_response, _read_form_value
from ._values import (
    Connector,
    FormOption,
    Model,
    PluginCatalog,
    PluginDetail,
    PluginInstallResult,
    PluginReference,
    PluginSkill,
    PluginSummary,
    ServiceTier,
    Skill,
    SkillCatalog,
    SkillChunk,
)


T = TypeVar("T")


def _handle(native: NativeLibrary, name: str, *arguments: object) -> Handle:
    value = Handle()
    native.call(name, *arguments, ctypes.byref(value))
    if not value.value:
        raise RuntimeError(f"{name} returned an absent owned value")
    return value


def _destroy(native: NativeLibrary, context: Handle, name: str, value: Handle) -> None:
    if value.value:
        native.call(name, context, ctypes.byref(value))


def _i32(native: NativeLibrary, name: str, *arguments: object) -> int:
    value = ctypes.c_int32()
    native.call(name, *arguments, ctypes.byref(value))
    return value.value


def _i64(native: NativeLibrary, name: str, *arguments: object) -> int:
    value = ctypes.c_int64()
    native.call(name, *arguments, ctypes.byref(value))
    return value.value


def _size(native: NativeLibrary, name: str, *arguments: object) -> int:
    value = ctypes.c_size_t()
    native.call(name, *arguments, ctypes.byref(value))
    return value.value


def _view(value: str | None) -> tuple[StringView, object | None]:
    return (null_view(), None) if value is None else utf8_view(value)


def _views(values: Sequence[str]) -> tuple[object, tuple[object | None, ...]]:
    converted = tuple(utf8_view(value) for value in values)
    return (
        (StringView * len(converted))(*(view for view, _ in converted))
        if converted
        else None,
        tuple(backing for _, backing in converted),
    )


def _handles(values: Sequence[Handle]) -> object:
    return (Handle * len(values))(*(value.value for value in values)) if values else None


def _optional_string(
    native: NativeLibrary,
    context: Handle,
    value: Handle,
    presence: str,
    copy: str,
) -> str | None:
    return native.copy_string(copy, context, value) if _i32(native, presence, context, value) else None


def _strings(
    native: NativeLibrary,
    context: Handle,
    value: Handle,
    count: str,
    copy: str,
) -> tuple[str, ...]:
    return tuple(
        native.copy_string(copy, context, value, index) or ""
        for index in range(_size(native, count, context, value))
    )


def _children(
    native: NativeLibrary,
    context: Handle,
    value: Handle,
    count: str,
    at: str,
    decoder: Callable[[NativeLibrary, Handle, Handle], T],
) -> tuple[T, ...]:
    return tuple(
        decoder(native, context, _handle(native, at, context, value, index))
        for index in range(_size(native, count, context, value))
    )


def _read_service_tier(native: NativeLibrary, context: Handle, value: Handle) -> ServiceTier:
    try:
        return ServiceTier(
            native.copy_string("codex_agent_service_tier_id_copy", context, value) or "",
            native.copy_string("codex_agent_service_tier_name_copy", context, value) or "",
            native.copy_string("codex_agent_service_tier_description_copy", context, value) or "",
        )
    finally:
        _destroy(native, context, "codex_agent_service_tier_destroy", value)


def _read_model(native: NativeLibrary, context: Handle, value: Handle) -> Model:
    try:
        return Model(
            native.copy_string("codex_agent_model_id_copy", context, value) or "",
            native.copy_string("codex_agent_model_display_name_copy", context, value) or "",
            native.copy_string("codex_agent_model_description_copy", context, value) or "",
            _strings(
                native,
                context,
                value,
                "codex_agent_model_supported_efforts_count",
                "codex_agent_model_supported_effort_copy_at",
            ),
            native.copy_string("codex_agent_model_default_effort_copy", context, value) or "",
            bool(_i32(native, "codex_agent_model_is_default", context, value)),
            _children(
                native,
                context,
                value,
                "codex_agent_model_service_tiers_count",
                "codex_agent_model_service_tier_at",
                _read_service_tier,
            ),
            _optional_string(
                native,
                context,
                value,
                "codex_agent_model_has_default_service_tier",
                "codex_agent_model_default_service_tier_copy",
            ),
        )
    finally:
        _destroy(native, context, "codex_agent_model_destroy", value)


def _read_connector(native: NativeLibrary, context: Handle, value: Handle) -> Connector:
    try:
        return Connector(
            native.copy_string("codex_agent_connector_id_copy", context, value) or "",
            native.copy_string("codex_agent_connector_name_copy", context, value) or "",
            native.copy_string("codex_agent_connector_description_copy", context, value) or "",
            _optional_string(
                native,
                context,
                value,
                "codex_agent_connector_has_install_url",
                "codex_agent_connector_install_url_copy",
            ),
            bool(_i32(native, "codex_agent_connector_is_accessible", context, value)),
            bool(_i32(native, "codex_agent_connector_is_enabled", context, value)),
            _strings(
                native,
                context,
                value,
                "codex_agent_connector_plugin_names_count",
                "codex_agent_connector_plugin_names_copy_at",
            ),
        )
    finally:
        _destroy(native, context, "codex_agent_connector_destroy", value)


def _read_plugin_reference(
    native: NativeLibrary, context: Handle, value: Handle
) -> PluginReference:
    try:
        result = PluginReference(
            native.copy_string("codex_agent_plugin_reference_id_copy", context, value) or "",
            native.copy_string("codex_agent_plugin_reference_name_copy", context, value) or "",
            native.copy_string(
                "codex_agent_plugin_reference_marketplace_name_copy", context, value
            )
            or "",
            _optional_string(
                native,
                context,
                value,
                "codex_agent_plugin_reference_has_marketplace_path",
                "codex_agent_plugin_reference_marketplace_path_copy",
            ),
            _optional_string(
                native,
                context,
                value,
                "codex_agent_plugin_reference_has_remote_plugin_id",
                "codex_agent_plugin_reference_remote_plugin_id_copy",
            ),
        )
        if result.uri != native.copy_string(
            "codex_agent_plugin_reference_uri_copy", context, value
        ):
            raise RuntimeError("native plugin URI disagrees with the canonical value")
        return result
    finally:
        _destroy(native, context, "codex_agent_plugin_reference_destroy", value)


def _read_plugin_skill(native: NativeLibrary, context: Handle, value: Handle) -> PluginSkill:
    try:
        return PluginSkill(
            native.copy_string("codex_agent_plugin_skill_name_copy", context, value) or "",
            native.copy_string("codex_agent_plugin_skill_description_copy", context, value) or "",
            bool(_i32(native, "codex_agent_plugin_skill_is_enabled", context, value)),
            _optional_string(
                native,
                context,
                value,
                "codex_agent_plugin_skill_has_path",
                "codex_agent_plugin_skill_path_copy",
            ),
        )
    finally:
        _destroy(native, context, "codex_agent_plugin_skill_destroy", value)


def _read_plugin_summary(
    native: NativeLibrary, context: Handle, value: Handle
) -> PluginSummary:
    try:
        return PluginSummary(
            _read_plugin_reference(
                native,
                context,
                _handle(native, "codex_agent_plugin_summary_reference", context, value),
            ),
            native.copy_string("codex_agent_plugin_summary_display_name_copy", context, value)
            or "",
            native.copy_string("codex_agent_plugin_summary_description_copy", context, value)
            or "",
            bool(_i32(native, "codex_agent_plugin_summary_is_installed", context, value)),
            bool(_i32(native, "codex_agent_plugin_summary_is_enabled", context, value)),
            PluginInstallPolicy(
                _i32(native, "codex_agent_plugin_summary_install_policy", context, value)
            ),
            PluginAuthPolicy(
                _i32(native, "codex_agent_plugin_summary_auth_policy", context, value)
            ),
            bool(_i32(native, "codex_agent_plugin_summary_is_available", context, value)),
            _strings(
                native,
                context,
                value,
                "codex_agent_plugin_summary_capabilities_count",
                "codex_agent_plugin_summary_capabilities_copy_at",
            ),
            _optional_string(
                native,
                context,
                value,
                "codex_agent_plugin_summary_has_brand_color",
                "codex_agent_plugin_summary_brand_color_copy",
            ),
            _optional_string(
                native,
                context,
                value,
                "codex_agent_plugin_summary_has_privacy_policy_url",
                "codex_agent_plugin_summary_privacy_policy_url_copy",
            ),
            _optional_string(
                native,
                context,
                value,
                "codex_agent_plugin_summary_has_terms_of_service_url",
                "codex_agent_plugin_summary_terms_of_service_url_copy",
            ),
            _optional_string(
                native,
                context,
                value,
                "codex_agent_plugin_summary_has_website_url",
                "codex_agent_plugin_summary_website_url_copy",
            ),
        )
    finally:
        _destroy(native, context, "codex_agent_plugin_summary_destroy", value)


def _read_plugin_catalog(
    native: NativeLibrary, context: Handle, value: Handle
) -> PluginCatalog:
    try:
        return PluginCatalog(
            _children(
                native,
                context,
                value,
                "codex_agent_plugin_catalog_plugins_count",
                "codex_agent_plugin_catalog_plugins_at",
                _read_plugin_summary,
            ),
            _strings(
                native,
                context,
                value,
                "codex_agent_plugin_catalog_errors_count",
                "codex_agent_plugin_catalog_errors_copy_at",
            ),
            CatalogFreshness(
                _i32(native, "codex_agent_plugin_catalog_freshness", context, value)
            ),
        )
    finally:
        _destroy(native, context, "codex_agent_plugin_catalog_destroy", value)


def _read_plugin_detail(native: NativeLibrary, context: Handle, value: Handle) -> PluginDetail:
    try:
        return PluginDetail(
            _read_plugin_summary(
                native,
                context,
                _handle(native, "codex_agent_plugin_detail_summary", context, value),
            ),
            native.copy_string("codex_agent_plugin_detail_description_copy", context, value) or "",
            _children(
                native,
                context,
                value,
                "codex_agent_plugin_detail_skills_count",
                "codex_agent_plugin_detail_skills_at",
                _read_plugin_skill,
            ),
            _children(
                native,
                context,
                value,
                "codex_agent_plugin_detail_connectors_count",
                "codex_agent_plugin_detail_connectors_at",
                _read_connector,
            ),
            _strings(
                native,
                context,
                value,
                "codex_agent_plugin_detail_mcp_servers_count",
                "codex_agent_plugin_detail_mcp_servers_copy_at",
            ),
            _i32(native, "codex_agent_plugin_detail_hook_count", context, value),
        )
    finally:
        _destroy(native, context, "codex_agent_plugin_detail_destroy", value)


def _read_plugin_install_result(
    native: NativeLibrary, context: Handle, value: Handle
) -> PluginInstallResult:
    try:
        return PluginInstallResult(
            PluginAuthPolicy(
                _i32(native, "codex_agent_plugin_install_result_auth_policy", context, value)
            ),
            _children(
                native,
                context,
                value,
                "codex_agent_plugin_install_result_connectors_count",
                "codex_agent_plugin_install_result_connectors_at",
                _read_connector,
            ),
            _optional_string(
                native,
                context,
                value,
                "codex_agent_plugin_install_result_has_message",
                "codex_agent_plugin_install_result_message_copy",
            ),
        )
    finally:
        _destroy(native, context, "codex_agent_plugin_install_result_destroy", value)


def _read_skill(native: NativeLibrary, context: Handle, value: Handle) -> Skill:
    try:
        return Skill(
            native.copy_string("codex_agent_skill_name_copy", context, value) or "",
            native.copy_string("codex_agent_skill_display_name_copy", context, value) or "",
            native.copy_string("codex_agent_skill_description_copy", context, value) or "",
            native.copy_string("codex_agent_skill_path_copy", context, value) or "",
            SkillScope(_i32(native, "codex_agent_skill_scope", context, value)),
            bool(_i32(native, "codex_agent_skill_is_enabled", context, value)),
            _optional_string(
                native,
                context,
                value,
                "codex_agent_skill_has_brand_color",
                "codex_agent_skill_brand_color_copy",
            ),
            _strings(
                native,
                context,
                value,
                "codex_agent_skill_dependencies_count",
                "codex_agent_skill_dependencies_copy_at",
            ),
            bool(_i32(native, "codex_agent_skill_can_uninstall", context, value)),
            ResourceOrigin(_i32(native, "codex_agent_skill_origin", context, value)),
        )
    finally:
        _destroy(native, context, "codex_agent_skill_destroy", value)


def _read_skill_catalog(
    native: NativeLibrary, context: Handle, value: Handle
) -> SkillCatalog:
    try:
        return SkillCatalog(
            _children(
                native,
                context,
                value,
                "codex_agent_skill_catalog_skills_count",
                "codex_agent_skill_catalog_skills_at",
                _read_skill,
            ),
            _strings(
                native,
                context,
                value,
                "codex_agent_skill_catalog_errors_count",
                "codex_agent_skill_catalog_errors_copy_at",
            ),
        )
    finally:
        _destroy(native, context, "codex_agent_skill_catalog_destroy", value)


def _read_skill_chunk(native: NativeLibrary, context: Handle, value: Handle) -> SkillChunk:
    try:
        present = ctypes.c_int32()
        offset = ctypes.c_int64()
        native.call(
            "codex_agent_skill_chunk_next_offset",
            context,
            value,
            ctypes.byref(present),
            ctypes.byref(offset),
        )
        return SkillChunk(
            native.copy_string("codex_agent_skill_chunk_content_copy", context, value) or "",
            offset.value if present.value else None,
            _i64(native, "codex_agent_skill_chunk_total_bytes", context, value),
        )
    finally:
        _destroy(native, context, "codex_agent_skill_chunk_destroy", value)


def _read_hook_handler(native: NativeLibrary, context: Handle, value: Handle) -> object:
    try:
        kind = _i32(native, "codex_agent_hook_handler_kind", context, value)
        names = ("agent", "command", "mcp_tool", "prompt")
        if not 0 <= kind < len(names):
            raise RuntimeError(f"unknown native hook-handler kind {kind}")
        name = names[kind]
        concrete = _handle(native, f"codex_agent_hook_handler_{name}", context, value)
        destroy = f"codex_agent_hook_handler_{name}_destroy"
        try:
            if name == "agent":
                return HookHandlerAgent()
            if name == "prompt":
                return HookHandlerPrompt()
            if name == "command":
                return HookHandlerCommand(
                    native.copy_string(
                        "codex_agent_hook_handler_command_command_copy", context, concrete
                    )
                    or "",
                    bool(
                        _i32(
                            native,
                            "codex_agent_hook_handler_command_is_async",
                            context,
                            concrete,
                        )
                    ),
                )
            return HookHandlerMcpTool(
                native.copy_string(
                    "codex_agent_hook_handler_mcp_tool_server_copy", context, concrete
                )
                or "",
                native.copy_string(
                    "codex_agent_hook_handler_mcp_tool_tool_copy", context, concrete
                )
                or "",
            )
        finally:
            _destroy(native, context, destroy, concrete)
    finally:
        _destroy(native, context, "codex_agent_hook_handler_destroy", value)


def _read_hook(native: NativeLibrary, context: Handle, value: Handle) -> Hook:
    try:
        result = Hook(
            native.copy_string("codex_agent_hook_key_copy", context, value) or "",
            native.copy_string("codex_agent_hook_current_hash_copy", context, value) or "",
            bool(_i32(native, "codex_agent_hook_is_enabled", context, value)),
            native.copy_string("codex_agent_hook_event_name_copy", context, value) or "",
            _read_hook_handler(
                native, context, _handle(native, "codex_agent_hook_handler", context, value)
            ),
            bool(_i32(native, "codex_agent_hook_is_managed", context, value)),
            native.copy_string("codex_agent_hook_source_copy", context, value) or "",
            native.copy_string("codex_agent_hook_source_path_copy", context, value) or "",
            _i64(native, "codex_agent_hook_timeout_seconds", context, value),
            HookTrustStatus(_i32(native, "codex_agent_hook_trust_status", context, value)),
            _optional_string(
                native, context, value, "codex_agent_hook_has_matcher", "codex_agent_hook_matcher_copy"
            ),
            _optional_string(
                native,
                context,
                value,
                "codex_agent_hook_has_plugin_id",
                "codex_agent_hook_plugin_id_copy",
            ),
            _optional_string(
                native,
                context,
                value,
                "codex_agent_hook_has_status_message",
                "codex_agent_hook_status_message_copy",
            ),
            ResourceOrigin(_i32(native, "codex_agent_hook_origin", context, value)),
            bool(_i32(native, "codex_agent_hook_can_uninstall", context, value)),
        )
        if result.can_trust != bool(
            _i32(native, "codex_agent_hook_can_trust", context, value)
        ):
            raise RuntimeError("native hook trust projection is inconsistent")
        return result
    finally:
        _destroy(native, context, "codex_agent_hook_destroy", value)


def _read_hook_catalog(native: NativeLibrary, context: Handle, value: Handle) -> HookCatalog:
    try:
        return HookCatalog(
            _children(
                native,
                context,
                value,
                "codex_agent_hook_catalog_hooks_count",
                "codex_agent_hook_catalog_hooks_at",
                _read_hook,
            ),
            _strings(
                native,
                context,
                value,
                "codex_agent_hook_catalog_warnings_count",
                "codex_agent_hook_catalog_warnings_copy_at",
            ),
            _strings(
                native,
                context,
                value,
                "codex_agent_hook_catalog_errors_count",
                "codex_agent_hook_catalog_errors_copy_at",
            ),
        )
    finally:
        _destroy(native, context, "codex_agent_hook_catalog_destroy", value)


def _read_authorization_url(
    native: NativeLibrary, context: Handle, value: Handle
) -> AuthorizationUrl:
    try:
        result = object.__new__(AuthorizationUrl)
        object.__setattr__(
            result,
            "value",
            native.copy_string("codex_agent_authorization_url_value_copy", context, value)
            or "",
        )
        object.__setattr__(
            result,
            "purpose",
            AuthorizationPurpose(
                _i32(native, "codex_agent_authorization_url_purpose", context, value)
            ),
        )
        return result
    finally:
        _destroy(native, context, "codex_agent_authorization_url_destroy", value)


def _read_authentication_state(
    native: NativeLibrary, context: Handle, value: Handle
) -> AuthenticationState:
    try:
        return AuthenticationState(
            AuthenticationStatus(
                _i32(native, "codex_agent_authentication_state_status", context, value)
            ),
            _read_authorization_url(
                native,
                context,
                _handle(
                    native,
                    "codex_agent_authentication_state_pending_sign_in_url",
                    context,
                    value,
                ),
            )
            if _i32(
                native,
                "codex_agent_authentication_state_has_pending_sign_in_url",
                context,
                value,
            )
            else None,
            _read_authorization_url(
                native,
                context,
                _handle(
                    native,
                    "codex_agent_authentication_state_device_verification_url",
                    context,
                    value,
                ),
            )
            if _i32(
                native,
                "codex_agent_authentication_state_has_device_verification_url",
                context,
                value,
            )
            else None,
            _optional_string(
                native,
                context,
                value,
                "codex_agent_authentication_state_has_device_user_code",
                "codex_agent_authentication_state_device_user_code_copy",
            ),
            _failure(
                _ContextView(native, context),
                _handle(native, "codex_agent_authentication_state_failure", context, value),
            )
            if _i32(native, "codex_agent_authentication_state_has_failure", context, value)
            else None,
        )
    finally:
        _destroy(native, context, "codex_agent_authentication_state_destroy", value)


class _ContextView:
    def __init__(self, native: NativeLibrary, handle: Handle) -> None:
        self.native = native
        self.handle = handle

    def require(self) -> Handle:
        return self.handle


def _read_conversation_id(native: NativeLibrary, context: Handle, value: Handle) -> ConversationId:
    try:
        return ConversationId(
            native.copy_string("codex_agent_conversation_id_value_copy", context, value) or ""
        )
    finally:
        _destroy(native, context, "codex_agent_conversation_id_destroy", value)


def _read_form_option(native: NativeLibrary, context: Handle, value: Handle) -> FormOption:
    try:
        return FormOption(
            native.copy_string("codex_agent_form_option_value_copy", context, value) or "",
            native.copy_string("codex_agent_form_option_title_copy", context, value) or "",
            _optional_string(
                native,
                context,
                value,
                "codex_agent_form_option_has_description",
                "codex_agent_form_option_description_copy",
            ),
        )
    finally:
        _destroy(native, context, "codex_agent_form_option_destroy", value)


def _optional_number(native: NativeLibrary, context: Handle, value: Handle, name: str):
    present = ctypes.c_int32()
    result = ctypes.c_double()
    native.call(name, context, value, ctypes.byref(present), ctypes.byref(result))
    return result.value if present.value else None


def _optional_integer(native: NativeLibrary, context: Handle, value: Handle, name: str):
    present = ctypes.c_int32()
    result = ctypes.c_int64()
    native.call(name, context, value, ctypes.byref(present), ctypes.byref(result))
    return result.value if present.value else None


def _read_form_field(native: NativeLibrary, context: Handle, value: Handle) -> FormField:
    try:
        has_format = ctypes.c_int32()
        format_value = ctypes.c_int32()
        native.call(
            "codex_agent_form_field_format",
            context,
            value,
            ctypes.byref(has_format),
            ctypes.byref(format_value),
        )
        default = None
        if _i32(native, "codex_agent_form_field_has_default_value", context, value):
            default = _read_form_value(
                native,
                context,
                _handle(native, "codex_agent_form_field_default_value", context, value),
            )
        return FormField(
            native.copy_string("codex_agent_form_field_name_copy", context, value) or "",
            native.copy_string("codex_agent_form_field_title_copy", context, value) or "",
            FormFieldType(_i32(native, "codex_agent_form_field_type", context, value)),
            _optional_string(
                native,
                context,
                value,
                "codex_agent_form_field_has_description",
                "codex_agent_form_field_description_copy",
            ),
            bool(_i32(native, "codex_agent_form_field_is_required", context, value)),
            bool(_i32(native, "codex_agent_form_field_is_secret", context, value)),
            FormStringFormat(format_value.value) if has_format.value else None,
            default,
            _optional_number(native, context, value, "codex_agent_form_field_minimum"),
            _optional_number(native, context, value, "codex_agent_form_field_maximum"),
            _optional_integer(native, context, value, "codex_agent_form_field_minimum_length"),
            _optional_integer(native, context, value, "codex_agent_form_field_maximum_length"),
            _children(
                native,
                context,
                value,
                "codex_agent_form_field_options_count",
                "codex_agent_form_field_option_at",
                _read_form_option,
            ),
            bool(_i32(native, "codex_agent_form_field_allows_other", context, value)),
            _optional_integer(
                native, context, value, "codex_agent_form_field_minimum_selections"
            ),
            _optional_integer(
                native, context, value, "codex_agent_form_field_maximum_selections"
            ),
        )
    finally:
        _destroy(native, context, "codex_agent_form_field_destroy", value)


def _read_elicitation(native: NativeLibrary, context: Handle, value: Handle) -> Elicitation:
    try:
        return Elicitation(
            native.copy_string("codex_agent_elicitation_request_id_copy", context, value) or "",
            _read_conversation_id(
                native,
                context,
                _handle(native, "codex_agent_elicitation_conversation_id", context, value),
            ),
            native.copy_string("codex_agent_elicitation_server_name_copy", context, value) or "",
            native.copy_string("codex_agent_elicitation_message_copy", context, value) or "",
            _optional_string(
                native,
                context,
                value,
                "codex_agent_elicitation_has_url",
                "codex_agent_elicitation_url_copy",
            ),
            _children(
                native,
                context,
                value,
                "codex_agent_elicitation_form_count",
                "codex_agent_elicitation_form_at",
                _read_form_field,
            )
            if _i32(native, "codex_agent_elicitation_has_form", context, value)
            else None,
        )
    finally:
        _destroy(native, context, "codex_agent_elicitation_destroy", value)


def _read_pending_approval(
    native: NativeLibrary, context: Handle, value: Handle
) -> PendingApproval:
    return PendingApproval(
        native.copy_string("codex_agent_pending_approval_request_id_copy", context, value) or "",
        _read_conversation_id(
            native,
            context,
            _handle(native, "codex_agent_pending_approval_conversation_id", context, value),
        ),
        native.copy_string("codex_agent_pending_approval_title_copy", context, value) or "",
        native.copy_string("codex_agent_pending_approval_details_copy", context, value) or "",
    )


def _read_pending_elicitation(
    native: NativeLibrary, context: Handle, value: Handle
) -> PendingElicitation:
    return PendingElicitation(
        _read_elicitation(
            native,
            context,
            _handle(native, "codex_agent_pending_elicitation_elicitation", context, value),
        )
    )


def _read_integration(native: NativeLibrary, context: Handle, value: Handle) -> IntegrationValue:
    try:
        kind = _i32(native, "codex_agent_integration_kind", context, value)
        if kind == 0:
            concrete = _handle(native, "codex_agent_integration_connector", context, value)
            try:
                connector = _read_connector(
                    native,
                    context,
                    _handle(
                        native,
                        "codex_agent_integration_connector_connector",
                        context,
                        concrete,
                    ),
                )
            finally:
                _destroy(native, context, "codex_agent_integration_connector_destroy", concrete)
            return ConnectorIntegration(connector)
        if kind == 1:
            concrete = _handle(native, "codex_agent_integration_mcp_server", context, value)
            try:
                server = read_owned_mcp_server(
                    native,
                    context,
                    _handle(
                        native,
                        "codex_agent_integration_mcp_server_server",
                        context,
                        concrete,
                    ),
                )
            finally:
                _destroy(native, context, "codex_agent_integration_mcp_server_destroy", concrete)
            return McpServerIntegration(server)
        raise RuntimeError(f"unknown native integration kind {kind}")
    finally:
        _destroy(native, context, "codex_agent_integration_destroy", value)


def _read_authorization_state(
    native: NativeLibrary, context: Handle, value: Handle
) -> IntegrationAuthorizationState:
    try:
        target = None
        target_handle = Handle()
        target_status = native.call(
            "codex_agent_integration_authorization_state_target",
            context,
            value,
            ctypes.byref(target_handle),
            allow=(Status.NOT_READY,),
        )
        if target_status is Status.OK and target_handle.value:
            target = _read_integration(native, context, target_handle)
        failure_handle = Handle()
        failure_status = native.call(
            "codex_agent_integration_authorization_state_failure",
            context,
            value,
            ctypes.byref(failure_handle),
            allow=(Status.NOT_READY,),
        )
        failure = (
            _failure(_ContextView(native, context), failure_handle)
            if failure_status is Status.OK and failure_handle.value
            else None
        )
        return IntegrationAuthorizationState(
            IntegrationAuthorizationStatus(
                _i32(
                    native,
                    "codex_agent_integration_authorization_state_status",
                    context,
                    value,
                )
            ),
            target,
            failure,
        )
    finally:
        _destroy(
            native,
            context,
            "codex_agent_integration_authorization_state_destroy",
            value,
        )


def _create_service_tier(native: NativeLibrary, context: Handle, value: ServiceTier) -> Handle:
    id_view, id_backing = utf8_view(value.id)
    name, name_backing = utf8_view(value.name)
    description, description_backing = utf8_view(value.description)
    return _handle(
        native,
        "codex_agent_service_tier_create",
        context,
        ctypes.byref(id_view),
        ctypes.byref(name),
        ctypes.byref(description),
    )


def _create_model(native: NativeLibrary, context: Handle, value: Model) -> Handle:
    id_view, id_backing = utf8_view(value.id)
    display, display_backing = utf8_view(value.display_name)
    description, description_backing = utf8_view(value.description)
    efforts, effort_backings = _views(value.supported_efforts)
    default_effort, default_effort_backing = utf8_view(value.default_effort)
    default_tier, default_tier_backing = _view(value.default_service_tier)
    tiers = tuple(_create_service_tier(native, context, tier) for tier in value.service_tiers)
    try:
        return _handle(
            native,
            "codex_agent_model_create",
            context,
            ctypes.byref(id_view),
            ctypes.byref(display),
            ctypes.byref(description),
            efforts,
            len(value.supported_efforts),
            ctypes.byref(default_effort),
            int(value.is_default),
            _handles(tiers),
            len(tiers),
            int(value.default_service_tier is not None),
            ctypes.byref(default_tier),
        )
    finally:
        for tier in tiers:
            _destroy(native, context, "codex_agent_service_tier_destroy", tier)


def _create_connector(native: NativeLibrary, context: Handle, value: Connector) -> Handle:
    id_view, id_backing = utf8_view(value.id)
    name, name_backing = utf8_view(value.name)
    description, description_backing = utf8_view(value.description)
    install, install_backing = _view(value.install_url)
    plugins, plugin_backings = _views(value.plugin_names)
    return _handle(
        native,
        "codex_agent_connector_create",
        context,
        ctypes.byref(id_view),
        ctypes.byref(name),
        ctypes.byref(description),
        int(value.install_url is not None),
        ctypes.byref(install),
        int(value.is_accessible),
        int(value.is_enabled),
        plugins,
        len(value.plugin_names),
    )


def _create_plugin_reference(
    native: NativeLibrary, context: Handle, value: PluginReference
) -> Handle:
    id_view, id_backing = utf8_view(value.id)
    name, name_backing = utf8_view(value.name)
    marketplace, marketplace_backing = utf8_view(value.marketplace_name)
    path, path_backing = _view(value.marketplace_path)
    remote, remote_backing = _view(value.remote_plugin_id)
    return _handle(
        native,
        "codex_agent_plugin_reference_create",
        context,
        ctypes.byref(id_view),
        ctypes.byref(name),
        ctypes.byref(marketplace),
        int(value.marketplace_path is not None),
        ctypes.byref(path),
        int(value.remote_plugin_id is not None),
        ctypes.byref(remote),
    )


def _create_skill(native: NativeLibrary, context: Handle, value: Skill) -> Handle:
    name, name_backing = utf8_view(value.name)
    display, display_backing = utf8_view(value.display_name)
    description, description_backing = utf8_view(value.description)
    path, path_backing = utf8_view(value.path)
    brand, brand_backing = _view(value.brand_color)
    dependencies, dependency_backings = _views(value.dependencies)
    return _handle(
        native,
        "codex_agent_skill_create",
        context,
        ctypes.byref(name),
        ctypes.byref(display),
        ctypes.byref(description),
        ctypes.byref(path),
        int(value.scope),
        int(value.is_enabled),
        int(value.brand_color is not None),
        ctypes.byref(brand),
        dependencies,
        len(value.dependencies),
        int(value.can_uninstall),
        int(value.origin is not None),
        0 if value.origin is None else int(value.origin),
    )


def _create_hook_handler(native: NativeLibrary, context: Handle, value: object) -> Handle:
    if isinstance(value, HookHandlerAgent):
        concrete = _handle(native, "codex_agent_hook_handler_agent_acquire", context)
        name = "agent"
    elif isinstance(value, HookHandlerPrompt):
        concrete = _handle(native, "codex_agent_hook_handler_prompt_acquire", context)
        name = "prompt"
    elif isinstance(value, HookHandlerCommand):
        command, command_backing = utf8_view(value.command)
        concrete = _handle(
            native,
            "codex_agent_hook_handler_command_create",
            context,
            ctypes.byref(command),
            int(value.is_async),
        )
        name = "command"
    elif isinstance(value, HookHandlerMcpTool):
        server, server_backing = utf8_view(value.server)
        tool, tool_backing = utf8_view(value.tool)
        concrete = _handle(
            native,
            "codex_agent_hook_handler_mcp_tool_create",
            context,
            ctypes.byref(server),
            ctypes.byref(tool),
        )
        name = "mcp_tool"
    else:
        raise TypeError(f"unsupported hook handler: {type(value).__name__}")
    try:
        return _handle(native, f"codex_agent_hook_handler_from_{name}", context, concrete)
    finally:
        _destroy(native, context, f"codex_agent_hook_handler_{name}_destroy", concrete)


def _create_hook(native: NativeLibrary, context: Handle, value: Hook) -> Handle:
    key, key_backing = utf8_view(value.key)
    current_hash, hash_backing = utf8_view(value.current_hash)
    event, event_backing = utf8_view(value.event_name)
    source, source_backing = utf8_view(value.source)
    source_path, source_path_backing = utf8_view(value.source_path)
    matcher, matcher_backing = _view(value.matcher)
    plugin_id, plugin_id_backing = _view(value.plugin_id)
    status, status_backing = _view(value.status_message)
    handler = _create_hook_handler(native, context, value.handler)
    try:
        return _handle(
            native,
            "codex_agent_hook_create",
            context,
            ctypes.byref(key),
            ctypes.byref(current_hash),
            int(value.is_enabled),
            ctypes.byref(event),
            handler,
            int(value.is_managed),
            ctypes.byref(source),
            ctypes.byref(source_path),
            value.timeout_seconds,
            int(value.trust_status),
            int(value.matcher is not None),
            ctypes.byref(matcher),
            int(value.plugin_id is not None),
            ctypes.byref(plugin_id),
            int(value.status_message is not None),
            ctypes.byref(status),
            int(value.origin is not None),
            0 if value.origin is None else int(value.origin),
            int(value.can_uninstall),
        )
    finally:
        _destroy(native, context, "codex_agent_hook_handler_destroy", handler)


def _create_integration(
    native: NativeLibrary, context: Handle, value: IntegrationValue
) -> Handle:
    if isinstance(value, ConnectorIntegration):
        item = _create_connector(native, context, value.connector)
        concrete_name = "connector"
        concrete_create = "codex_agent_integration_connector_create"
        item_destroy = "codex_agent_connector_destroy"
    elif isinstance(value, McpServerIntegration):
        item = create_mcp_server(native, context, value.server)
        concrete_name = "mcp_server"
        concrete_create = "codex_agent_integration_mcp_server_create"
        item_destroy = "codex_agent_mcp_server_destroy"
    else:
        raise TypeError(f"unsupported integration: {type(value).__name__}")
    try:
        concrete = _handle(native, concrete_create, context, item)
    finally:
        _destroy(native, context, item_destroy, item)
    try:
        return _handle(
            native, f"codex_agent_integration_from_{concrete_name}", context, concrete
        )
    finally:
        _destroy(native, context, f"codex_agent_integration_{concrete_name}_destroy", concrete)


class _Service(_OwnedHandle):
    async def _operation(
        self,
        name: str,
        *arguments: object,
        decoder: Callable[[Handle, Handle], T] | None = None,
    ) -> T | None:
        context, service = self._require()
        return await run_operation(
            self._context.native,
            context,
            lambda callback, user_data, out: self._context.native.function(name)(
                context, service, *arguments, callback, user_data, out
            ),
            (lambda operation: None)
            if decoder is None
            else (lambda operation: decoder(context, operation)),
            lambda failure: _failure(self._context, failure),
        )

    def _available(self, name: str) -> bool:
        context, service = self._require()
        return bool(_i32(self._context.native, name, context, service))

    def _state(
        self, getter: str, subscriber: str, decoder: Callable[[Handle], T]
    ) -> StateStream[T]:
        _, service = self._require()
        return _stream(self._context, getter, subscriber, service, decoder)


class CodexAuthentication(_Service):
    _release_name = "codex_agent_authentication_release"

    @property
    def state(self) -> StateStream[AuthenticationState]:
        def decode(snapshot: Handle) -> AuthenticationState:
            context, _ = self._require()
            return _read_authentication_state(
                self._context.native,
                context,
                _handle(
                    self._context.native,
                    "codex_agent_authentication_state_value",
                    context,
                    snapshot,
                ),
            )

        return self._state(
            "codex_agent_authentication_state_get",
            "codex_agent_authentication_state_subscribe",
            decode,
        )

    def _boolean_state(self, name: str) -> StateStream[bool]:
        def decode(snapshot: Handle) -> bool:
            context, _ = self._require()
            return bool(
                _i32(
                    self._context.native,
                    "codex_agent_state_boolean_value",
                    context,
                    snapshot,
                )
            )

        return self._state(
            f"codex_agent_authentication_{name}_get",
            f"codex_agent_authentication_{name}_subscribe",
            decode,
        )

    @property
    def is_authenticated(self) -> StateStream[bool]:
        return self._boolean_state("is_authenticated")

    @property
    def is_authenticating(self) -> StateStream[bool]:
        return self._boolean_state("is_authenticating")

    async def authenticate(
        self,
        method: ApiKeyAuthentication
        | ChatGptBrowserAuthentication
        | ChatGptDeviceCodeAuthentication = CHAT_GPT_BROWSER_AUTHENTICATION,
    ) -> None:
        context, _ = self._require()
        if isinstance(method, ApiKeyAuthentication):
            value, backing = utf8_view(method.value)
            native_method = _handle(
                self._context.native,
                "codex_agent_authentication_method_api_key_create",
                context,
                ctypes.byref(value),
            )
            suffix = "api_key"
        elif isinstance(method, ChatGptBrowserAuthentication):
            native_method = _handle(
                self._context.native,
                "codex_agent_authentication_method_chat_gpt_browser_create",
                context,
            )
            suffix = "chat_gpt_browser"
        elif isinstance(method, ChatGptDeviceCodeAuthentication):
            native_method = _handle(
                self._context.native,
                "codex_agent_authentication_method_chat_gpt_device_code_create",
                context,
            )
            suffix = "chat_gpt_device_code"
        else:
            raise TypeError(f"unsupported authentication method: {type(method).__name__}")
        try:
            await self._operation(
                f"codex_agent_authentication_authenticate_{suffix}", native_method
            )
        finally:
            _destroy(
                self._context.native,
                context,
                f"codex_agent_authentication_method_{suffix}_destroy",
                native_method,
            )

    async def cancel(self) -> None:
        await self._operation("codex_agent_authentication_cancel")

    async def sign_out(self) -> None:
        await self._operation("codex_agent_authentication_sign_out")


class CodexConnectors(_Service):
    _release_name = "codex_agent_connectors_release"

    @property
    def is_available(self) -> bool:
        return self._available("codex_agent_connectors_is_available")

    async def list(self, force_reload: bool = False) -> tuple[Connector, ...]:
        def decode(context: Handle, operation: Handle) -> tuple[Connector, ...]:
            return tuple(
                _read_connector(
                    self._context.native,
                    context,
                    _handle(
                        self._context.native,
                        "codex_agent_operation_connector_at",
                        context,
                        operation,
                        index,
                    ),
                )
                for index in range(
                    _size(
                        self._context.native,
                        "codex_agent_operation_connectors_count",
                        context,
                        operation,
                    )
                )
            )

        result = await self._operation(
            "codex_agent_connectors_list", int(force_reload), decoder=decode
        )
        return result  # type: ignore[return-value]


class CodexHooks(_Service):
    _release_name = "codex_agent_hooks_release"

    @property
    def is_available(self) -> bool:
        return self._available("codex_agent_hooks_is_available")

    async def list(self) -> HookCatalog:
        result = await self._operation(
            "codex_agent_hooks_list",
            decoder=lambda context, operation: _read_hook_catalog(
                self._context.native,
                context,
                _handle(
                    self._context.native,
                    "codex_agent_operation_hook_catalog",
                    context,
                    operation,
                ),
            ),
        )
        return result  # type: ignore[return-value]

    async def install(self, directory: str, scope: InstallationScope) -> Hook:
        view, backing = utf8_view(directory)
        result = await self._operation(
            "codex_agent_hooks_install",
            ctypes.byref(view),
            int(scope),
            decoder=lambda context, operation: _read_hook(
                self._context.native,
                context,
                _handle(
                    self._context.native,
                    "codex_agent_operation_hook",
                    context,
                    operation,
                ),
            ),
        )
        return result  # type: ignore[return-value]

    async def _with_hook(self, name: str, hook: Hook) -> None:
        context, _ = self._require()
        native_hook = _create_hook(self._context.native, context, hook)
        try:
            await self._operation(name, native_hook)
        finally:
            _destroy(self._context.native, context, "codex_agent_hook_destroy", native_hook)

    async def uninstall(self, hook: Hook) -> None:
        await self._with_hook("codex_agent_hooks_uninstall", hook)

    async def trust(self, hook: Hook) -> None:
        await self._with_hook("codex_agent_hooks_trust", hook)


class CodexIntegrationAuthorization(_Service):
    _release_name = "codex_agent_integration_authorization_release"

    @property
    def state(self) -> StateStream[IntegrationAuthorizationState]:
        def decode(snapshot: Handle) -> IntegrationAuthorizationState:
            context, _ = self._require()
            return _read_authorization_state(
                self._context.native,
                context,
                _handle(
                    self._context.native,
                    "codex_agent_integration_authorization_state_value",
                    context,
                    snapshot,
                ),
            )

        return self._state(
            "codex_agent_integration_authorization_state_get",
            "codex_agent_integration_authorization_state_subscribe",
            decode,
        )

    @property
    def active(self) -> StateStream[IntegrationValue | None]:
        def decode(snapshot: Handle) -> IntegrationValue | None:
            context, _ = self._require()
            if not _i32(
                self._context.native,
                "codex_agent_integration_authorization_active_has_value",
                context,
                snapshot,
            ):
                return None
            return _read_integration(
                self._context.native,
                context,
                _handle(
                    self._context.native,
                    "codex_agent_integration_authorization_active_value",
                    context,
                    snapshot,
                ),
            )

        return self._state(
            "codex_agent_integration_authorization_active_get",
            "codex_agent_integration_authorization_active_subscribe",
            decode,
        )

    @property
    def is_authorizing(self) -> StateStream[bool]:
        def decode(snapshot: Handle) -> bool:
            context, _ = self._require()
            return bool(
                _i32(
                    self._context.native,
                    "codex_agent_state_boolean_value",
                    context,
                    snapshot,
                )
            )

        return self._state(
            "codex_agent_integration_authorization_is_authorizing_get",
            "codex_agent_integration_authorization_is_authorizing_subscribe",
            decode,
        )

    async def authorize(self, target: IntegrationValue) -> None:
        context, _ = self._require()
        native_target = _create_integration(self._context.native, context, target)
        try:
            await self._operation(
                "codex_agent_integration_authorization_authorize", native_target
            )
        finally:
            _destroy(
                self._context.native,
                context,
                "codex_agent_integration_destroy",
                native_target,
            )

    async def cancel(self) -> None:
        await self._operation("codex_agent_integration_authorization_cancel")


class CodexInteractions(_Service):
    _release_name = "codex_agent_interactions_release"

    def __init__(self, context: _Context, handle: Handle) -> None:
        super().__init__(context, handle)
        self._pending: dict[int, tuple[object, Handle, str]] = {}

    def _remember(self, value: PendingInteractionValue, handle: Handle, destroy: str) -> PendingInteractionValue:
        self._pending[id(value)] = (value, handle, destroy)
        return value

    def _approval(self, value: Handle) -> PendingApproval:
        context, _ = self._require()
        return self._remember(
            _read_pending_approval(self._context.native, context, value),
            value,
            "codex_agent_pending_approval_destroy",
        )  # type: ignore[return-value]

    def _elicitation(self, value: Handle) -> PendingElicitation:
        context, _ = self._require()
        return self._remember(
            _read_pending_elicitation(self._context.native, context, value),
            value,
            "codex_agent_pending_elicitation_destroy",
        )  # type: ignore[return-value]

    def _interaction(self, value: Handle) -> PendingInteractionValue:
        context, _ = self._require()
        try:
            kind = _i32(
                self._context.native,
                "codex_agent_pending_interaction_kind",
                context,
                value,
            )
            if kind == 0:
                return self._approval(
                    _handle(
                        self._context.native,
                        "codex_agent_pending_interaction_approval",
                        context,
                        value,
                    )
                )
            if kind == 1:
                return self._elicitation(
                    _handle(
                        self._context.native,
                        "codex_agent_pending_interaction_elicitation",
                        context,
                        value,
                    )
                )
            raise RuntimeError(f"unknown native pending-interaction kind {kind}")
        finally:
            _destroy(
                self._context.native,
                context,
                "codex_agent_pending_interaction_destroy",
                value,
            )

    def _interaction_state(self, value: Handle) -> InteractionState:
        context, _ = self._require()
        try:
            pending = tuple(
                self._interaction(
                    _handle(
                        self._context.native,
                        "codex_agent_interaction_state_pending_at",
                        context,
                        value,
                        index,
                    )
                )
                for index in range(
                    _size(
                        self._context.native,
                        "codex_agent_interaction_state_pending_count",
                        context,
                        value,
                    )
                )
            )
            failure = None
            if _i32(
                self._context.native,
                "codex_agent_interaction_state_has_failure",
                context,
                value,
            ):
                failure = _failure(
                    self._context,
                    _handle(
                        self._context.native,
                        "codex_agent_interaction_state_failure",
                        context,
                        value,
                    ),
                )
            resolving = frozenset(
                item.request_id
                for item in pending
                if _i32(
                    self._context.native,
                    "codex_agent_interaction_state_resolving_request_ids_contains",
                    context,
                    value,
                    ctypes.byref(utf8_view(item.request_id)[0]),
                )
            )
            if len(resolving) != _size(
                self._context.native,
                "codex_agent_interaction_state_resolving_request_ids_count",
                context,
                value,
            ):
                raise RuntimeError(
                    "native resolving IDs are not represented by pending interactions"
                )
            return InteractionState(pending, resolving, failure)
        finally:
            _destroy(
                self._context.native,
                context,
                "codex_agent_interaction_state_destroy",
                value,
            )

    @property
    def state(self) -> StateStream[InteractionState]:
        def decode(snapshot: Handle) -> InteractionState:
            context, _ = self._require()
            return self._interaction_state(
                _handle(
                    self._context.native,
                    "codex_agent_interactions_state_value",
                    context,
                    snapshot,
                )
            )

        return self._state(
            "codex_agent_interactions_state_get",
            "codex_agent_interactions_state_subscribe",
            decode,
        )

    @property
    def approvals(self) -> StateStream[tuple[PendingApproval, ...]]:
        def decode(snapshot: Handle) -> tuple[PendingApproval, ...]:
            context, _ = self._require()
            return tuple(
                self._approval(
                    _handle(
                        self._context.native,
                        "codex_agent_interactions_approvals_at",
                        context,
                        snapshot,
                        index,
                    )
                )
                for index in range(
                    _size(
                        self._context.native,
                        "codex_agent_interactions_approvals_count",
                        context,
                        snapshot,
                    )
                )
            )

        return self._state(
            "codex_agent_interactions_approvals_get",
            "codex_agent_interactions_approvals_subscribe",
            decode,
        )

    @property
    def elicitations(self) -> StateStream[tuple[PendingElicitation, ...]]:
        def decode(snapshot: Handle) -> tuple[PendingElicitation, ...]:
            context, _ = self._require()
            return tuple(
                self._elicitation(
                    _handle(
                        self._context.native,
                        "codex_agent_interactions_elicitations_at",
                        context,
                        snapshot,
                        index,
                    )
                )
                for index in range(
                    _size(
                        self._context.native,
                        "codex_agent_interactions_elicitations_count",
                        context,
                        snapshot,
                    )
                )
            )

        return self._state(
            "codex_agent_interactions_elicitations_get",
            "codex_agent_interactions_elicitations_subscribe",
            decode,
        )

    def _pending_handle(self, value: PendingInteractionValue, expected: str) -> Handle:
        retained = self._pending.get(id(value))
        if retained is None or retained[0] is not value or retained[2] != expected:
            raise ValueError("interaction must be the exact live value emitted by this service")
        return retained[1]

    async def resolve_approval(
        self, approval: PendingApproval, decision: ApprovalDecision
    ) -> None:
        await self._operation(
            "codex_agent_interactions_resolve_approval",
            self._pending_handle(approval, "codex_agent_pending_approval_destroy"),
            int(decision),
        )

    async def resolve_elicitation(
        self, elicitation: PendingElicitation, response: ElicitationResponse
    ) -> None:
        context, _ = self._require()
        native_response = _create_response(self._context.native, context, response)
        try:
            await self._operation(
                "codex_agent_interactions_resolve_elicitation",
                self._pending_handle(
                    elicitation, "codex_agent_pending_elicitation_destroy"
                ),
                native_response,
            )
        finally:
            _destroy(
                self._context.native,
                context,
                "codex_agent_elicitation_response_destroy",
                native_response,
            )

    async def open_url(self, elicitation: PendingElicitation) -> None:
        await self._operation(
            "codex_agent_interactions_open_url",
            self._pending_handle(
                elicitation, "codex_agent_pending_elicitation_destroy"
            ),
        )

    async def aclose(self) -> None:
        if self._context.open:
            context = self._context.require()
            for _, handle, destroy in self._pending.values():
                _destroy(self._context.native, context, destroy, handle)
        self._pending.clear()
        await super().aclose()


class CodexMcpServers(_Service):
    _release_name = "codex_agent_mcp_servers_release"

    @property
    def is_available(self) -> bool:
        return self._available("codex_agent_mcp_servers_is_available")

    async def list(self) -> tuple[McpServer, ...]:
        def decode(context: Handle, operation: Handle) -> tuple[McpServer, ...]:
            return tuple(
                read_owned_mcp_server(
                    self._context.native,
                    context,
                    _handle(
                        self._context.native,
                        "codex_agent_operation_mcp_server_at",
                        context,
                        operation,
                        index,
                    ),
                )
                for index in range(
                    _size(
                        self._context.native,
                        "codex_agent_operation_mcp_servers_count",
                        context,
                        operation,
                    )
                )
            )

        result = await self._operation("codex_agent_mcp_servers_list", decoder=decode)
        return result  # type: ignore[return-value]

    async def add(self, configuration: McpServerConfiguration) -> McpServer:
        context, _ = self._require()
        native_configuration = create_mcp_configuration(
            self._context.native, context, configuration
        )
        try:
            result = await self._operation(
                "codex_agent_mcp_servers_add",
                native_configuration,
                decoder=lambda current, operation: read_owned_mcp_server(
                    self._context.native,
                    current,
                    _handle(
                        self._context.native,
                        "codex_agent_operation_mcp_server",
                        current,
                        operation,
                    ),
                ),
            )
            return result  # type: ignore[return-value]
        finally:
            _destroy(
                self._context.native,
                context,
                "codex_agent_mcp_server_configuration_destroy",
                native_configuration,
            )

    async def remove(self, server: McpServer) -> None:
        context, _ = self._require()
        native_server = create_mcp_server(self._context.native, context, server)
        try:
            await self._operation("codex_agent_mcp_servers_remove", native_server)
        finally:
            _destroy(
                self._context.native,
                context,
                "codex_agent_mcp_server_destroy",
                native_server,
            )


class CodexModels(_Service):
    _release_name = "codex_agent_models_release"

    async def list(self) -> tuple[Model, ...]:
        def decode(context: Handle, operation: Handle) -> tuple[Model, ...]:
            return tuple(
                _read_model(
                    self._context.native,
                    context,
                    _handle(
                        self._context.native,
                        "codex_agent_operation_model_at",
                        context,
                        operation,
                        index,
                    ),
                )
                for index in range(
                    _size(
                        self._context.native,
                        "codex_agent_operation_models_count",
                        context,
                        operation,
                    )
                )
            )

        result = await self._operation("codex_agent_models_list", decoder=decode)
        return result  # type: ignore[return-value]

    async def resolve(self, resolution: Resolution = Resolution.PREFERRED) -> Model:
        result = await self._operation(
            "codex_agent_models_resolve",
            int(resolution),
            decoder=lambda context, operation: _read_model(
                self._context.native,
                context,
                _handle(
                    self._context.native,
                    "codex_agent_operation_model",
                    context,
                    operation,
                ),
            ),
        )
        return result  # type: ignore[return-value]

    async def resolve_effort(
        self, model: Model, resolution: Resolution = Resolution.PREFERRED
    ) -> str:
        context, _ = self._require()
        native_model = _create_model(self._context.native, context, model)
        try:
            result = await self._operation(
                "codex_agent_models_resolve_effort",
                native_model,
                int(resolution),
                decoder=lambda current, operation: self._context.native.copy_string(
                    "codex_agent_operation_string_copy", current, operation
                )
                or "",
            )
            return result  # type: ignore[return-value]
        finally:
            _destroy(self._context.native, context, "codex_agent_model_destroy", native_model)

    async def resolve_service_tier(
        self, model: Model, resolution: Resolution = Resolution.PREFERRED
    ) -> ServiceTier | None:
        context, _ = self._require()
        native_model = _create_model(self._context.native, context, model)

        def decode(current: Handle, operation: Handle) -> ServiceTier | None:
            if not _i32(
                self._context.native,
                "codex_agent_operation_has_service_tier",
                current,
                operation,
            ):
                return None
            return _read_service_tier(
                self._context.native,
                current,
                _handle(
                    self._context.native,
                    "codex_agent_operation_service_tier",
                    current,
                    operation,
                ),
            )

        try:
            return await self._operation(
                "codex_agent_models_resolve_service_tier",
                native_model,
                int(resolution),
                decoder=decode,
            )
        finally:
            _destroy(self._context.native, context, "codex_agent_model_destroy", native_model)


class CodexPlugins(_Service):
    _release_name = "codex_agent_plugins_release"

    @property
    def is_available(self) -> bool:
        return self._available("codex_agent_plugins_is_available")

    async def list(self, force_reload: bool = False) -> PluginCatalog:
        result = await self._operation(
            "codex_agent_plugins_list",
            int(force_reload),
            decoder=lambda context, operation: _read_plugin_catalog(
                self._context.native,
                context,
                _handle(
                    self._context.native,
                    "codex_agent_operation_plugin_catalog",
                    context,
                    operation,
                ),
            ),
        )
        return result  # type: ignore[return-value]

    async def _with_plugin(
        self,
        name: str,
        plugin: PluginReference,
        decoder: Callable[[Handle, Handle], T] | None = None,
    ) -> T | None:
        context, _ = self._require()
        native_plugin = _create_plugin_reference(self._context.native, context, plugin)
        try:
            return await self._operation(name, native_plugin, decoder=decoder)
        finally:
            _destroy(
                self._context.native,
                context,
                "codex_agent_plugin_reference_destroy",
                native_plugin,
            )

    async def read(self, plugin: PluginReference) -> PluginDetail:
        result = await self._with_plugin(
            "codex_agent_plugins_read",
            plugin,
            lambda context, operation: _read_plugin_detail(
                self._context.native,
                context,
                _handle(
                    self._context.native,
                    "codex_agent_operation_plugin_detail",
                    context,
                    operation,
                ),
            ),
        )
        return result  # type: ignore[return-value]

    async def install(self, plugin: PluginReference) -> PluginInstallResult:
        result = await self._with_plugin(
            "codex_agent_plugins_install",
            plugin,
            lambda context, operation: _read_plugin_install_result(
                self._context.native,
                context,
                _handle(
                    self._context.native,
                    "codex_agent_operation_plugin_install_result",
                    context,
                    operation,
                ),
            ),
        )
        return result  # type: ignore[return-value]

    async def uninstall(self, plugin: PluginReference) -> None:
        await self._with_plugin("codex_agent_plugins_uninstall", plugin)


class CodexSkills(_Service):
    _release_name = "codex_agent_skills_release"

    @property
    def is_available(self) -> bool:
        return self._available("codex_agent_skills_is_available")

    async def list(self, force_reload: bool = False) -> SkillCatalog:
        result = await self._operation(
            "codex_agent_skills_list",
            int(force_reload),
            decoder=lambda context, operation: _read_skill_catalog(
                self._context.native,
                context,
                _handle(
                    self._context.native,
                    "codex_agent_operation_skill_catalog",
                    context,
                    operation,
                ),
            ),
        )
        return result  # type: ignore[return-value]

    async def read(self, path: str, offset: int = 0) -> SkillChunk:
        view, backing = utf8_view(path)
        result = await self._operation(
            "codex_agent_skills_read",
            ctypes.byref(view),
            offset,
            decoder=lambda context, operation: _read_skill_chunk(
                self._context.native,
                context,
                _handle(
                    self._context.native,
                    "codex_agent_operation_skill_chunk",
                    context,
                    operation,
                ),
            ),
        )
        return result  # type: ignore[return-value]

    async def install(self, directory: str, scope: InstallationScope) -> Skill:
        view, backing = utf8_view(directory)
        result = await self._operation(
            "codex_agent_skills_install",
            ctypes.byref(view),
            int(scope),
            decoder=lambda context, operation: _read_skill(
                self._context.native,
                context,
                _handle(
                    self._context.native,
                    "codex_agent_operation_skill",
                    context,
                    operation,
                ),
            ),
        )
        return result  # type: ignore[return-value]

    async def uninstall(self, skill: Skill) -> None:
        context, _ = self._require()
        native_skill = _create_skill(self._context.native, context, skill)
        try:
            await self._operation("codex_agent_skills_uninstall", native_skill)
        finally:
            _destroy(self._context.native, context, "codex_agent_skill_destroy", native_skill)
