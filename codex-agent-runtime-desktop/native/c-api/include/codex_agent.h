#ifndef CODEX_AGENT_H
#define CODEX_AGENT_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#if defined(_WIN32)
#if defined(CODEX_AGENT_BUILD)
#define CODEX_AGENT_API __declspec(dllexport)
#else
#define CODEX_AGENT_API __declspec(dllimport)
#endif
#define CODEX_AGENT_CALL __cdecl
#else
#define CODEX_AGENT_API __attribute__((visibility("default")))
#define CODEX_AGENT_CALL
#endif

#define CODEX_AGENT_ABI_VERSION_MAJOR UINT32_C(1)
#define CODEX_AGENT_ABI_VERSION_MINOR UINT32_C(10)
#define CODEX_AGENT_ABI_VERSION_PATCH UINT32_C(0)
#define CODEX_AGENT_ABI_VERSION_ENCODE(major, minor, patch) \
    ((((uint32_t)(major) & UINT32_C(0xff)) << 24) | \
     (((uint32_t)(minor) & UINT32_C(0xff)) << 16) | \
     ((uint32_t)(patch) & UINT32_C(0xffff)))
#define CODEX_AGENT_ABI_VERSION_CURRENT \
    CODEX_AGENT_ABI_VERSION_ENCODE( \
        CODEX_AGENT_ABI_VERSION_MAJOR, \
        CODEX_AGENT_ABI_VERSION_MINOR, \
        CODEX_AGENT_ABI_VERSION_PATCH)
#define CODEX_AGENT_ABI_VERSION_MINIMUM_COMPATIBLE \
    CODEX_AGENT_ABI_VERSION_ENCODE(1, 0, 0)

typedef int32_t codex_agent_status_t;

#define CODEX_AGENT_STATUS_OK INT32_C(0)
#define CODEX_AGENT_STATUS_INVALID_ARGUMENT INT32_C(1)
#define CODEX_AGENT_STATUS_OUT_OF_MEMORY INT32_C(2)
#define CODEX_AGENT_STATUS_STALE_HANDLE INT32_C(3)
#define CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE INT32_C(4)
#define CODEX_AGENT_STATUS_WRONG_CONTEXT INT32_C(5)
#define CODEX_AGENT_STATUS_BUSY INT32_C(6)
#define CODEX_AGENT_STATUS_CANCELLED INT32_C(7)
#define CODEX_AGENT_STATUS_INTERNAL_ERROR INT32_C(8)
#define CODEX_AGENT_STATUS_BUFFER_TOO_SMALL INT32_C(9)
#define CODEX_AGENT_STATUS_UNSUPPORTED_ABI INT32_C(10)
#define CODEX_AGENT_STATUS_CLOSED INT32_C(11)
#define CODEX_AGENT_STATUS_WOULD_DEADLOCK INT32_C(12)
#define CODEX_AGENT_STATUS_NOT_READY INT32_C(13)
#define CODEX_AGENT_STATUS_OPERATION_FAILED INT32_C(14)

typedef struct codex_agent_context codex_agent_context_t;
typedef struct codex_agent_host codex_agent_host_t;
typedef struct codex_agent_agent codex_agent_agent_t;
typedef struct codex_agent_conversations codex_agent_conversations_t;
typedef struct codex_agent_authentication codex_agent_authentication_t;
typedef struct codex_agent_interactions codex_agent_interactions_t;
typedef struct codex_agent_integration_authorization codex_agent_integration_authorization_t;
typedef struct codex_agent_models codex_agent_models_t;
typedef struct codex_agent_skills codex_agent_skills_t;
typedef struct codex_agent_hooks codex_agent_hooks_t;
typedef struct codex_agent_plugins codex_agent_plugins_t;
typedef struct codex_agent_connectors codex_agent_connectors_t;
typedef struct codex_agent_mcp_servers codex_agent_mcp_servers_t;
typedef struct codex_agent_conversation codex_agent_conversation_t;
typedef struct codex_agent_operation codex_agent_operation_t;
typedef struct codex_agent_subscription codex_agent_subscription_t;
typedef struct codex_agent_snapshot codex_agent_snapshot_t;
typedef struct codex_agent_failure codex_agent_failure_t;
typedef struct codex_agent_conversation_id codex_agent_conversation_id_t;
typedef struct codex_agent_conversation_summary codex_agent_conversation_summary_t;
typedef struct codex_agent_workspace codex_agent_workspace_t;
typedef struct codex_agent_workspace_resolution_available codex_agent_workspace_resolution_available_t;
typedef struct codex_agent_workspace_selection_required codex_agent_workspace_selection_required_t;
typedef struct codex_agent_form_option codex_agent_form_option_t;
typedef struct codex_agent_mcp_environment_variable codex_agent_mcp_environment_variable_t;
typedef struct codex_agent_mcp_oauth_configuration codex_agent_mcp_oauth_configuration_t;
typedef struct codex_agent_mcp_tool_configuration codex_agent_mcp_tool_configuration_t;
typedef struct codex_agent_mcp_transport codex_agent_mcp_transport_t;
typedef struct codex_agent_mcp_transport_http codex_agent_mcp_transport_http_t;
typedef struct codex_agent_mcp_transport_stdio codex_agent_mcp_transport_stdio_t;
typedef struct codex_agent_mcp_server_configuration codex_agent_mcp_server_configuration_t;
typedef struct codex_agent_mcp_server codex_agent_mcp_server_t;
typedef struct codex_agent_elicitation_validation_issue codex_agent_elicitation_validation_issue_t;
typedef struct codex_agent_plan_step codex_agent_plan_step_t;
typedef struct codex_agent_plugin_reference codex_agent_plugin_reference_t;
typedef struct codex_agent_plugin_skill codex_agent_plugin_skill_t;
typedef struct codex_agent_service_tier codex_agent_service_tier_t;
typedef struct codex_agent_skill_chunk codex_agent_skill_chunk_t;
typedef struct codex_agent_form_boolean_value codex_agent_form_boolean_value_t;
typedef struct codex_agent_form_number_value codex_agent_form_number_value_t;
typedef struct codex_agent_form_text_value codex_agent_form_text_value_t;
typedef struct codex_agent_form_text_list_value codex_agent_form_text_list_value_t;
typedef struct codex_agent_elicitation_validation codex_agent_elicitation_validation_t;
typedef struct codex_agent_connector codex_agent_connector_t;
typedef struct codex_agent_integration_connector codex_agent_integration_connector_t;
typedef struct codex_agent_integration_mcp_server codex_agent_integration_mcp_server_t;
typedef struct codex_agent_skill codex_agent_skill_t;
typedef struct codex_agent_skill_catalog codex_agent_skill_catalog_t;
typedef struct codex_agent_plugin_summary codex_agent_plugin_summary_t;
typedef struct codex_agent_plugin_catalog codex_agent_plugin_catalog_t;
typedef struct codex_agent_plugin_detail codex_agent_plugin_detail_t;
typedef struct codex_agent_plugin_install_result codex_agent_plugin_install_result_t;
typedef struct codex_agent_model codex_agent_model_t;
typedef struct codex_agent_plan_progress codex_agent_plan_progress_t;
typedef struct codex_agent_hook_activity codex_agent_hook_activity_t;
typedef struct codex_agent_turn_progress codex_agent_turn_progress_t;
typedef struct codex_agent_hook_handler_agent codex_agent_hook_handler_agent_t;
typedef struct codex_agent_hook_handler_command codex_agent_hook_handler_command_t;
typedef struct codex_agent_hook_handler_mcp_tool codex_agent_hook_handler_mcp_tool_t;
typedef struct codex_agent_hook_handler_prompt codex_agent_hook_handler_prompt_t;
typedef struct codex_agent_invocation_plugin codex_agent_invocation_plugin_t;
typedef struct codex_agent_invocation_skill codex_agent_invocation_skill_t;
typedef struct codex_agent_pending_approval codex_agent_pending_approval_t;
typedef struct codex_agent_invocation codex_agent_invocation_t;
typedef struct codex_agent_message codex_agent_message_t;
typedef struct codex_agent_conversation_value codex_agent_conversation_value_t;
typedef struct codex_agent_turn_request codex_agent_turn_request_t;
typedef struct codex_agent_form_value codex_agent_form_value_t;
typedef struct codex_agent_form_field codex_agent_form_field_t;
typedef struct codex_agent_elicitation codex_agent_elicitation_t;
typedef struct codex_agent_elicitation_response codex_agent_elicitation_response_t;
typedef struct codex_agent_pending_elicitation codex_agent_pending_elicitation_t;
typedef struct codex_agent_pending_interaction codex_agent_pending_interaction_t;
typedef struct codex_agent_interaction_state codex_agent_interaction_state_t;
typedef struct codex_agent_hook_handler codex_agent_hook_handler_t;
typedef struct codex_agent_hook codex_agent_hook_t;
typedef struct codex_agent_hook_catalog codex_agent_hook_catalog_t;
typedef struct codex_agent_integration codex_agent_integration_t;
typedef struct codex_agent_integration_authorization_state codex_agent_integration_authorization_state_t;
typedef struct codex_agent_authentication_state codex_agent_authentication_state_t;
typedef struct codex_agent_conversation_settings codex_agent_conversation_settings_t;
typedef struct codex_agent_authorization_url codex_agent_authorization_url_t;
typedef struct codex_agent_client_info_value codex_agent_client_info_value_t;
typedef struct codex_agent_form_content codex_agent_form_content_t;
typedef struct codex_agent_pending_interaction_list codex_agent_pending_interaction_list_t;
typedef struct codex_agent_authentication_method_api_key codex_agent_authentication_method_api_key_t;
typedef struct codex_agent_authentication_method_chat_gpt_browser
    codex_agent_authentication_method_chat_gpt_browser_t;
typedef struct codex_agent_authentication_method_chat_gpt_device_code
    codex_agent_authentication_method_chat_gpt_device_code_t;

typedef int32_t codex_agent_host_state_kind_t;
#define CODEX_AGENT_HOST_STATE_NEW INT32_C(0)
#define CODEX_AGENT_HOST_STATE_RESTORING INT32_C(1)
#define CODEX_AGENT_HOST_STATE_WORKSPACE_REQUIRED INT32_C(2)
#define CODEX_AGENT_HOST_STATE_PREPARING INT32_C(3)
#define CODEX_AGENT_HOST_STATE_READY INT32_C(4)
#define CODEX_AGENT_HOST_STATE_FAILED INT32_C(5)
#define CODEX_AGENT_HOST_STATE_CLOSED INT32_C(6)

typedef int32_t codex_agent_workspace_selection_reason_t;
#define CODEX_AGENT_WORKSPACE_REASON_NOT_SELECTED INT32_C(0)
#define CODEX_AGENT_WORKSPACE_REASON_NOT_FOUND INT32_C(1)
#define CODEX_AGENT_WORKSPACE_REASON_ACCESS_REVOKED INT32_C(2)
#define CODEX_AGENT_WORKSPACE_REASON_INVALID_SELECTION INT32_C(3)

typedef int32_t codex_agent_conversation_status_t;
#define CODEX_AGENT_CONVERSATION_STATUS_NEW INT32_C(0)
#define CODEX_AGENT_CONVERSATION_STATUS_OPENING INT32_C(1)
#define CODEX_AGENT_CONVERSATION_STATUS_READY INT32_C(2)
#define CODEX_AGENT_CONVERSATION_STATUS_STARTING_TURN INT32_C(3)
#define CODEX_AGENT_CONVERSATION_STATUS_RUNNING_TURN INT32_C(4)
#define CODEX_AGENT_CONVERSATION_STATUS_CANCELLING_TURN INT32_C(5)
#define CODEX_AGENT_CONVERSATION_STATUS_RELOADING INT32_C(6)
#define CODEX_AGENT_CONVERSATION_STATUS_FAILED INT32_C(7)
#define CODEX_AGENT_CONVERSATION_STATUS_CLOSED INT32_C(8)

typedef int32_t codex_agent_approval_preset_t;
#define CODEX_AGENT_APPROVAL_PRESET_NEVER INT32_C(0)
#define CODEX_AGENT_APPROVAL_PRESET_AUTO_REVIEW INT32_C(1)
#define CODEX_AGENT_APPROVAL_PRESET_ASK_ME INT32_C(2)
#define CODEX_AGENT_APPROVAL_PRESET_STRICT INT32_C(3)

typedef int32_t codex_agent_capability_t;
#define CODEX_AGENT_CAPABILITY_WEB_SEARCH INT32_C(0)

typedef int32_t codex_agent_elicitation_validation_reason_t;
#define CODEX_AGENT_ELICITATION_VALIDATION_MISSING_REQUIRED INT32_C(0)
#define CODEX_AGENT_ELICITATION_VALIDATION_UNKNOWN_FIELD INT32_C(1)
#define CODEX_AGENT_ELICITATION_VALIDATION_INVALID_TYPE INT32_C(2)
#define CODEX_AGENT_ELICITATION_VALIDATION_NON_FINITE_NUMBER INT32_C(3)
#define CODEX_AGENT_ELICITATION_VALIDATION_BELOW_MINIMUM INT32_C(4)
#define CODEX_AGENT_ELICITATION_VALIDATION_ABOVE_MAXIMUM INT32_C(5)
#define CODEX_AGENT_ELICITATION_VALIDATION_NON_INTEGER INT32_C(6)
#define CODEX_AGENT_ELICITATION_VALIDATION_INVALID_FORMAT INT32_C(7)
#define CODEX_AGENT_ELICITATION_VALIDATION_INVALID_SELECTION INT32_C(8)
#define CODEX_AGENT_ELICITATION_VALIDATION_DUPLICATE_SELECTION INT32_C(9)

typedef int32_t codex_agent_mcp_environment_source_t;
#define CODEX_AGENT_MCP_ENVIRONMENT_SOURCE_LOCAL INT32_C(0)
#define CODEX_AGENT_MCP_ENVIRONMENT_SOURCE_REMOTE INT32_C(1)

typedef int32_t codex_agent_mcp_tool_approval_t;
#define CODEX_AGENT_MCP_TOOL_APPROVAL_AUTO INT32_C(0)
#define CODEX_AGENT_MCP_TOOL_APPROVAL_PROMPT INT32_C(1)
#define CODEX_AGENT_MCP_TOOL_APPROVAL_WRITES INT32_C(2)
#define CODEX_AGENT_MCP_TOOL_APPROVAL_APPROVE INT32_C(3)

typedef int32_t codex_agent_plan_step_status_t;
#define CODEX_AGENT_PLAN_STEP_PENDING INT32_C(0)
#define CODEX_AGENT_PLAN_STEP_IN_PROGRESS INT32_C(1)
#define CODEX_AGENT_PLAN_STEP_COMPLETED INT32_C(2)

typedef int32_t codex_agent_skill_scope_t;
#define CODEX_AGENT_SKILL_SCOPE_SYSTEM INT32_C(0)
#define CODEX_AGENT_SKILL_SCOPE_USER INT32_C(1)
#define CODEX_AGENT_SKILL_SCOPE_REPO INT32_C(2)
#define CODEX_AGENT_SKILL_SCOPE_PLUGIN INT32_C(3)
#define CODEX_AGENT_SKILL_SCOPE_ADMIN INT32_C(4)

typedef int32_t codex_agent_approval_decision_t;
#define CODEX_AGENT_APPROVAL_DECISION_ACCEPT INT32_C(0)
#define CODEX_AGENT_APPROVAL_DECISION_DECLINE INT32_C(1)

typedef int32_t codex_agent_authentication_status_t;
#define CODEX_AGENT_AUTHENTICATION_STATUS_SIGNED_OUT INT32_C(0)
#define CODEX_AGENT_AUTHENTICATION_STATUS_AUTHENTICATING INT32_C(1)
#define CODEX_AGENT_AUTHENTICATION_STATUS_AUTHENTICATED INT32_C(2)

typedef int32_t codex_agent_catalog_freshness_t;
#define CODEX_AGENT_CATALOG_FRESHNESS_LIVE INT32_C(0)
#define CODEX_AGENT_CATALOG_FRESHNESS_FRESH_CACHE INT32_C(1)
#define CODEX_AGENT_CATALOG_FRESHNESS_STALE_CACHE INT32_C(2)

typedef int32_t codex_agent_collaboration_mode_t;
#define CODEX_AGENT_COLLABORATION_MODE_DEFAULT INT32_C(0)
#define CODEX_AGENT_COLLABORATION_MODE_PLAN INT32_C(1)

typedef int32_t codex_agent_invocation_kind_t;
#define CODEX_AGENT_INVOCATION_KIND_PLUGIN INT32_C(0)
#define CODEX_AGENT_INVOCATION_KIND_SKILL INT32_C(1)

typedef int32_t codex_agent_form_value_kind_t;
#define CODEX_AGENT_FORM_VALUE_KIND_BOOLEAN INT32_C(0)
#define CODEX_AGENT_FORM_VALUE_KIND_NUMBER INT32_C(1)
#define CODEX_AGENT_FORM_VALUE_KIND_TEXT INT32_C(2)
#define CODEX_AGENT_FORM_VALUE_KIND_TEXT_LIST INT32_C(3)

typedef int32_t codex_agent_pending_interaction_kind_t;
#define CODEX_AGENT_PENDING_INTERACTION_KIND_APPROVAL INT32_C(0)
#define CODEX_AGENT_PENDING_INTERACTION_KIND_ELICITATION INT32_C(1)

typedef int32_t codex_agent_hook_handler_kind_t;
#define CODEX_AGENT_HOOK_HANDLER_KIND_AGENT INT32_C(0)
#define CODEX_AGENT_HOOK_HANDLER_KIND_COMMAND INT32_C(1)
#define CODEX_AGENT_HOOK_HANDLER_KIND_MCP_TOOL INT32_C(2)
#define CODEX_AGENT_HOOK_HANDLER_KIND_PROMPT INT32_C(3)

typedef int32_t codex_agent_integration_kind_t;
#define CODEX_AGENT_INTEGRATION_KIND_CONNECTOR INT32_C(0)
#define CODEX_AGENT_INTEGRATION_KIND_MCP_SERVER INT32_C(1)

typedef int32_t codex_agent_elicitation_action_t;
#define CODEX_AGENT_ELICITATION_ACTION_ACCEPT INT32_C(0)
#define CODEX_AGENT_ELICITATION_ACTION_DECLINE INT32_C(1)
#define CODEX_AGENT_ELICITATION_ACTION_CANCEL INT32_C(2)

typedef int32_t codex_agent_form_field_type_t;
#define CODEX_AGENT_FORM_FIELD_TYPE_STRING INT32_C(0)
#define CODEX_AGENT_FORM_FIELD_TYPE_NUMBER INT32_C(1)
#define CODEX_AGENT_FORM_FIELD_TYPE_INTEGER INT32_C(2)
#define CODEX_AGENT_FORM_FIELD_TYPE_BOOLEAN INT32_C(3)
#define CODEX_AGENT_FORM_FIELD_TYPE_SINGLE_SELECT INT32_C(4)
#define CODEX_AGENT_FORM_FIELD_TYPE_MULTI_SELECT INT32_C(5)

typedef int32_t codex_agent_form_string_format_t;
#define CODEX_AGENT_FORM_STRING_FORMAT_EMAIL INT32_C(0)
#define CODEX_AGENT_FORM_STRING_FORMAT_URI INT32_C(1)
#define CODEX_AGENT_FORM_STRING_FORMAT_DATE INT32_C(2)
#define CODEX_AGENT_FORM_STRING_FORMAT_DATE_TIME INT32_C(3)

typedef int32_t codex_agent_hook_run_status_t;
#define CODEX_AGENT_HOOK_RUN_STATUS_RUNNING INT32_C(0)
#define CODEX_AGENT_HOOK_RUN_STATUS_COMPLETED INT32_C(1)
#define CODEX_AGENT_HOOK_RUN_STATUS_FAILED INT32_C(2)
#define CODEX_AGENT_HOOK_RUN_STATUS_BLOCKED INT32_C(3)
#define CODEX_AGENT_HOOK_RUN_STATUS_STOPPED INT32_C(4)

typedef int32_t codex_agent_hook_trust_status_t;
#define CODEX_AGENT_HOOK_TRUST_STATUS_MANAGED INT32_C(0)
#define CODEX_AGENT_HOOK_TRUST_STATUS_UNTRUSTED INT32_C(1)
#define CODEX_AGENT_HOOK_TRUST_STATUS_TRUSTED INT32_C(2)
#define CODEX_AGENT_HOOK_TRUST_STATUS_MODIFIED INT32_C(3)

typedef int32_t codex_agent_installation_scope_t;
#define CODEX_AGENT_INSTALLATION_SCOPE_USER INT32_C(0)
#define CODEX_AGENT_INSTALLATION_SCOPE_WORKSPACE INT32_C(1)

typedef int32_t codex_agent_integration_authorization_status_t;
#define CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_IDLE INT32_C(0)
#define CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_STARTING INT32_C(1)
#define CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_AWAITING_COMPLETION INT32_C(2)
#define CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_AUTHORIZED INT32_C(3)
#define CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_FAILED INT32_C(4)

typedef int32_t codex_agent_mcp_auth_status_t;
#define CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN INT32_C(0)
#define CODEX_AGENT_MCP_AUTH_STATUS_UNSUPPORTED INT32_C(1)
#define CODEX_AGENT_MCP_AUTH_STATUS_NOT_LOGGED_IN INT32_C(2)
#define CODEX_AGENT_MCP_AUTH_STATUS_BEARER_TOKEN INT32_C(3)
#define CODEX_AGENT_MCP_AUTH_STATUS_OAUTH INT32_C(4)

typedef int32_t codex_agent_mcp_authentication_t;
#define CODEX_AGENT_MCP_AUTHENTICATION_OAUTH INT32_C(0)
#define CODEX_AGENT_MCP_AUTHENTICATION_CHAT_GPT INT32_C(1)

typedef int32_t codex_agent_mcp_tool_exposure_surface_t;
#define CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_CODE_MODE INT32_C(0)
#define CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_DEFERRED INT32_C(1)
#define CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_DIRECT INT32_C(2)

typedef int32_t codex_agent_mcp_transport_kind_t;
#define CODEX_AGENT_MCP_TRANSPORT_KIND_HTTP INT32_C(0)
#define CODEX_AGENT_MCP_TRANSPORT_KIND_STDIO INT32_C(1)

typedef int32_t codex_agent_message_role_t;
#define CODEX_AGENT_MESSAGE_ROLE_USER INT32_C(0)
#define CODEX_AGENT_MESSAGE_ROLE_ASSISTANT INT32_C(1)

typedef int32_t codex_agent_plugin_auth_policy_t;
#define CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_INSTALL INT32_C(0)
#define CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_USE INT32_C(1)

typedef int32_t codex_agent_plugin_install_policy_t;
#define CODEX_AGENT_PLUGIN_INSTALL_POLICY_NOT_AVAILABLE INT32_C(0)
#define CODEX_AGENT_PLUGIN_INSTALL_POLICY_AVAILABLE INT32_C(1)
#define CODEX_AGENT_PLUGIN_INSTALL_POLICY_INSTALLED_BY_DEFAULT INT32_C(2)

typedef int32_t codex_agent_resolution_t;
#define CODEX_AGENT_RESOLUTION_PREFERRED INT32_C(0)
#define CODEX_AGENT_RESOLUTION_DEFAULT INT32_C(1)
#define CODEX_AGENT_RESOLUTION_FIRST INT32_C(2)

typedef int32_t codex_agent_resource_origin_t;
#define CODEX_AGENT_RESOURCE_ORIGIN_USER INT32_C(0)
#define CODEX_AGENT_RESOURCE_ORIGIN_WORKSPACE INT32_C(1)
#define CODEX_AGENT_RESOURCE_ORIGIN_PLUGIN INT32_C(2)
#define CODEX_AGENT_RESOURCE_ORIGIN_MANAGED INT32_C(3)
#define CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN INT32_C(4)

typedef int32_t codex_agent_work_activity_t;
#define CODEX_AGENT_WORK_ACTIVITY_RUNNING_COMMAND INT32_C(0)
#define CODEX_AGENT_WORK_ACTIVITY_WRITING_FILES INT32_C(1)

typedef int32_t codex_agent_authorization_purpose_t;
#define CODEX_AGENT_AUTHORIZATION_PURPOSE_CHAT_GPT INT32_C(0)
#define CODEX_AGENT_AUTHORIZATION_PURPOSE_EXTERNAL INT32_C(1)

typedef struct codex_agent_string_view {
    const uint8_t *data;
    size_t size;
} codex_agent_string_view_t;

typedef struct codex_agent_client_info {
    uint32_t struct_size;
    codex_agent_string_view_t name;
    codex_agent_string_view_t title;
    codex_agent_string_view_t version;
} codex_agent_client_info_t;

typedef struct codex_agent_host_options {
    uint32_t struct_size;
    codex_agent_string_view_t bundle_directory;
    codex_agent_string_view_t data_directory;
    codex_agent_client_info_t client_info;
} codex_agent_host_options_t;

typedef struct codex_agent_path_workspace_selection {
    uint32_t struct_size;
    codex_agent_string_view_t path;
} codex_agent_path_workspace_selection_t;

typedef struct codex_agent_conversation_open_options {
    uint32_t struct_size;
    int32_t has_conversation_id;
    codex_agent_string_view_t conversation_id;
    int32_t has_approval_preset;
    codex_agent_approval_preset_t approval_preset;
    int32_t has_service_tier;
    codex_agent_string_view_t service_tier;
} codex_agent_conversation_open_options_t;

/*
 * Input views are copied before an API call returns and must contain strict
 * UTF-8. Versioned input structs accept struct_size values at least as large
 * as the ABI 1.1 definition. String-copy functions report the exact number of
 * UTF-8 bytes in out_required, do not append NUL, and do not partially modify
 * the destination when returning BUFFER_TOO_SMALL.
 *
 * Every out_* handle slot must be non-null and initially contain NULL. Every
 * non-OK return preserves its exact value. Every non-NULL handle returned on
 * OK is a distinct owned token scoped to its creating context. Copying a raw
 * pointer does not create another token or owner; use the matching retain
 * function, when provided, to obtain a distinct owned alias.
 *
 * A non-null release or destroy slot whose value is NULL is idempotently
 * successful. Release and destroy functions write NULL only on OK; every
 * non-OK result, including BUSY, preserves the exact slot value. Apart from
 * the callback-publication guarantee below, caller-owned slots must not be
 * accessed concurrently.
 */

/*
 * Asynchronous callbacks run on library worker threads, are serialized per
 * context, and may begin before the initiating API call returns. The operation
 * or subscription output token is published before its first callback begins,
 * and an operation result is published before its operation callback begins.
 *
 * Callbacks must not unwind across the C boundary. A non-NULL operation
 * callback and its user_data must remain valid until that callback returns or
 * operation destruction returns OK. A state callback and its user_data must
 * remain valid until its terminal callback returns or subscription destruction
 * returns OK. BUSY destruction preserves the handle and does not end these
 * lifetimes; a callback may still begin or be running.
 */
typedef void (CODEX_AGENT_CALL *codex_agent_operation_callback_t)(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    void *user_data);

/*
 * Ownership of each non-NULL snapshot transfers when the state callback is
 * entered. The snapshot is immutable and must be passed once to
 * codex_agent_snapshot_destroy unless its context is successfully destroyed
 * first.
 */
typedef void (CODEX_AGENT_CALL *codex_agent_state_callback_t)(
    codex_agent_context_t *context,
    codex_agent_subscription_t *subscription,
    codex_agent_status_t event_status,
    codex_agent_snapshot_t *snapshot,
    int32_t is_terminal,
    void *user_data);

/*
 * ABI 1.x is backward compatible within major version 1. Additive minor and
 * patch releases accept every encoded version in the closed interval from
 * MINIMUM_COMPATIBLE through CURRENT.
 */
CODEX_AGENT_API uint32_t CODEX_AGENT_CALL codex_agent_abi_version(void);
CODEX_AGENT_API int32_t CODEX_AGENT_CALL codex_agent_abi_is_compatible(
    uint32_t requested_version);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_approval_decision_validate(
    codex_agent_approval_decision_t value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_authentication_status_validate(
    codex_agent_authentication_status_t value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_catalog_freshness_validate(
    codex_agent_catalog_freshness_t value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_collaboration_mode_validate(
    codex_agent_collaboration_mode_t value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_action_validate(
    codex_agent_elicitation_action_t value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_field_type_validate(
    codex_agent_form_field_type_t value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_string_format_validate(
    codex_agent_form_string_format_t value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_run_status_validate(
    codex_agent_hook_run_status_t value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_trust_status_validate(
    codex_agent_hook_trust_status_t value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_installation_scope_validate(
    codex_agent_installation_scope_t value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_integration_authorization_status_validate(
    codex_agent_integration_authorization_status_t value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_auth_status_validate(
    codex_agent_mcp_auth_status_t value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_authentication_validate(
    codex_agent_mcp_authentication_t value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_tool_exposure_surface_validate(
    codex_agent_mcp_tool_exposure_surface_t value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_role_validate(
    codex_agent_message_role_t value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_auth_policy_validate(
    codex_agent_plugin_auth_policy_t value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_install_policy_validate(
    codex_agent_plugin_install_policy_t value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_resolution_validate(
    codex_agent_resolution_t value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_resource_origin_validate(
    codex_agent_resource_origin_t value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_work_activity_validate(
    codex_agent_work_activity_t value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_authorization_purpose_validate(
    codex_agent_authorization_purpose_t value);

/*
 * Creates an opaque context. The output slot must be non-null and initially
 * contain NULL. The context is uniquely owned and its pointer must not be
 * copied.
 */
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_context_create(
    codex_agent_context_t **out_context);

/*
 * On OK, destroys the context, writes NULL, and invalidates and reclaims every
 * remaining context-scoped handle; no such handle may be used afterward. A
 * non-null slot already containing NULL is successful. Every non-OK result,
 * including BUSY, preserves the exact slot value. The slot must not be
 * accessed concurrently. Only the original context output slot may be passed;
 * use or destruction through a copied pointer is invalid caller behavior.
 */
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_context_destroy(
    codex_agent_context_t **context);

/*
 * Immutable value handles are context-scoped, type checked, and uniquely
 * owned. Their create functions copy every input before returning. Each
 * matching destroy function follows the same slot, BUSY, and idempotent-NULL
 * rules as the other handle release functions above.
 *
 * Every string-view parameter must be a non-null pointer. A has_* input flag
 * must be 0 or 1. When it is 0, the paired string view must point to {NULL, 0}
 * and the paired scalar must be zero. A nullable string copy returns NOT_READY
 * when its property is absent. An input array may be NULL only when its count
 * is zero. Array elements and nested handles are copied before create returns.
 * An indexed getter returns INVALID_ARGUMENT without changing outputs when the
 * index is outside the immutable collection.
 */

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_boolean_value_create(
    codex_agent_context_t *context,
    int32_t value,
    codex_agent_form_boolean_value_t **out_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_boolean_value_destroy(
    codex_agent_context_t *context,
    codex_agent_form_boolean_value_t **value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_boolean_value_value(
    codex_agent_context_t *context,
    codex_agent_form_boolean_value_t *value,
    int32_t *out_value);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_number_value_create(
    codex_agent_context_t *context,
    double value,
    codex_agent_form_number_value_t **out_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_number_value_destroy(
    codex_agent_context_t *context,
    codex_agent_form_number_value_t **value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_number_value_value(
    codex_agent_context_t *context,
    codex_agent_form_number_value_t *value,
    double *out_value);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_text_value_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *value,
    codex_agent_form_text_value_t **out_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_text_value_destroy(
    codex_agent_context_t *context,
    codex_agent_form_text_value_t **value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_text_value_value_copy(
    codex_agent_context_t *context,
    codex_agent_form_text_value_t *value,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_text_list_value_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *values,
    size_t value_count,
    codex_agent_form_text_list_value_t **out_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_text_list_value_destroy(
    codex_agent_context_t *context,
    codex_agent_form_text_list_value_t **value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_text_list_value_count(
    codex_agent_context_t *context,
    codex_agent_form_text_list_value_t *value,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_text_list_value_copy_at(
    codex_agent_context_t *context,
    codex_agent_form_text_list_value_t *value,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_handler_agent_acquire(
    codex_agent_context_t *context,
    codex_agent_hook_handler_agent_t **out_handler);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_handler_agent_destroy(
    codex_agent_context_t *context,
    codex_agent_hook_handler_agent_t **handler);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_handler_command_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *command,
    int32_t is_async,
    codex_agent_hook_handler_command_t **out_handler);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_handler_command_destroy(
    codex_agent_context_t *context,
    codex_agent_hook_handler_command_t **handler);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_handler_command_command_copy(
    codex_agent_context_t *context,
    codex_agent_hook_handler_command_t *handler,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_handler_command_is_async(
    codex_agent_context_t *context,
    codex_agent_hook_handler_command_t *handler,
    int32_t *out_is_async);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_handler_mcp_tool_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *server,
    const codex_agent_string_view_t *tool,
    codex_agent_hook_handler_mcp_tool_t **out_handler);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_handler_mcp_tool_destroy(
    codex_agent_context_t *context,
    codex_agent_hook_handler_mcp_tool_t **handler);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_hook_handler_mcp_tool_server_copy(
    codex_agent_context_t *context,
    codex_agent_hook_handler_mcp_tool_t *handler,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_handler_mcp_tool_tool_copy(
    codex_agent_context_t *context,
    codex_agent_hook_handler_mcp_tool_t *handler,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_handler_prompt_acquire(
    codex_agent_context_t *context,
    codex_agent_hook_handler_prompt_t **out_handler);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_handler_prompt_destroy(
    codex_agent_context_t *context,
    codex_agent_hook_handler_prompt_t **handler);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_plugin_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *name,
    const codex_agent_string_view_t *uri,
    codex_agent_invocation_plugin_t **out_plugin);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_plugin_destroy(
    codex_agent_context_t *context,
    codex_agent_invocation_plugin_t **plugin);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_plugin_name_copy(
    codex_agent_context_t *context,
    codex_agent_invocation_plugin_t *plugin,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_plugin_uri_copy(
    codex_agent_context_t *context,
    codex_agent_invocation_plugin_t *plugin,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_plugin_key_copy(
    codex_agent_context_t *context,
    codex_agent_invocation_plugin_t *plugin,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_skill_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *name,
    const codex_agent_string_view_t *path,
    codex_agent_invocation_skill_t **out_skill);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_skill_destroy(
    codex_agent_context_t *context,
    codex_agent_invocation_skill_t **skill);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_skill_name_copy(
    codex_agent_context_t *context,
    codex_agent_invocation_skill_t *skill,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_skill_path_copy(
    codex_agent_context_t *context,
    codex_agent_invocation_skill_t *skill,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_skill_key_copy(
    codex_agent_context_t *context,
    codex_agent_invocation_skill_t *skill,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_pending_approval_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *request_id,
    codex_agent_conversation_id_t *conversation_id,
    const codex_agent_string_view_t *title,
    const codex_agent_string_view_t *details,
    codex_agent_pending_approval_t **out_approval);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_pending_approval_destroy(
    codex_agent_context_t *context,
    codex_agent_pending_approval_t **approval);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_pending_approval_request_id_copy(
    codex_agent_context_t *context,
    codex_agent_pending_approval_t *approval,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_pending_approval_conversation_id(
    codex_agent_context_t *context,
    codex_agent_pending_approval_t *approval,
    codex_agent_conversation_id_t **out_conversation_id);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_pending_approval_title_copy(
    codex_agent_context_t *context,
    codex_agent_pending_approval_t *approval,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_pending_approval_details_copy(
    codex_agent_context_t *context,
    codex_agent_pending_approval_t *approval,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_authentication_method_api_key_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *value,
    codex_agent_authentication_method_api_key_t **out_method);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_authentication_method_api_key_destroy(
    codex_agent_context_t *context,
    codex_agent_authentication_method_api_key_t **method);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_authentication_method_api_key_value_copy(
    codex_agent_context_t *context,
    codex_agent_authentication_method_api_key_t *method,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_authentication_method_chat_gpt_browser_create(
    codex_agent_context_t *context,
    codex_agent_authentication_method_chat_gpt_browser_t **out_method);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_authentication_method_chat_gpt_browser_destroy(
    codex_agent_context_t *context,
    codex_agent_authentication_method_chat_gpt_browser_t **method);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_authentication_method_chat_gpt_device_code_create(
    codex_agent_context_t *context,
    codex_agent_authentication_method_chat_gpt_device_code_t **out_method);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_authentication_method_chat_gpt_device_code_destroy(
    codex_agent_context_t *context,
    codex_agent_authentication_method_chat_gpt_device_code_t **method);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_failure_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *code,
    const codex_agent_string_view_t *message,
    int32_t is_recoverable,
    codex_agent_failure_t **out_failure);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_id_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *value,
    codex_agent_conversation_id_t **out_conversation_id);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_id_destroy(
    codex_agent_context_t *context,
    codex_agent_conversation_id_t **conversation_id);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_id_value_copy(
    codex_agent_context_t *context,
    codex_agent_conversation_id_t *conversation_id,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_summary_create(
    codex_agent_context_t *context,
    codex_agent_conversation_id_t *conversation_id,
    const codex_agent_string_view_t *title,
    int64_t updated_at_epoch_seconds,
    codex_agent_conversation_summary_t **out_summary);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_summary_destroy(
    codex_agent_context_t *context,
    codex_agent_conversation_summary_t **summary);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_summary_conversation_id(
    codex_agent_context_t *context,
    codex_agent_conversation_summary_t *summary,
    codex_agent_conversation_id_t **out_conversation_id);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_summary_title_copy(
    codex_agent_context_t *context,
    codex_agent_conversation_summary_t *summary,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_summary_updated_at_epoch_seconds(
    codex_agent_context_t *context,
    codex_agent_conversation_summary_t *summary,
    int64_t *out_updated_at_epoch_seconds);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_workspace_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *path,
    int32_t has_display_name,
    const codex_agent_string_view_t *display_name,
    codex_agent_workspace_t **out_workspace);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_workspace_destroy(
    codex_agent_context_t *context,
    codex_agent_workspace_t **workspace);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_workspace_path_copy(
    codex_agent_context_t *context,
    codex_agent_workspace_t *workspace,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_workspace_display_name_copy(
    codex_agent_context_t *context,
    codex_agent_workspace_t *workspace,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_workspace_resolution_available_create(
    codex_agent_context_t *context,
    codex_agent_workspace_t *workspace,
    codex_agent_workspace_resolution_available_t **out_available);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_workspace_resolution_available_destroy(
    codex_agent_context_t *context,
    codex_agent_workspace_resolution_available_t **available);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_workspace_resolution_available_workspace(
    codex_agent_context_t *context,
    codex_agent_workspace_resolution_available_t *available,
    codex_agent_workspace_t **out_workspace);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_workspace_selection_required_create(
    codex_agent_context_t *context,
    codex_agent_workspace_selection_reason_t reason,
    const codex_agent_string_view_t *message,
    codex_agent_workspace_selection_required_t **out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_workspace_selection_required_destroy(
    codex_agent_context_t *context,
    codex_agent_workspace_selection_required_t **required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_workspace_selection_required_reason(
    codex_agent_context_t *context,
    codex_agent_workspace_selection_required_t *required,
    codex_agent_workspace_selection_reason_t *out_reason);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_workspace_selection_required_message_copy(
    codex_agent_context_t *context,
    codex_agent_workspace_selection_required_t *required,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_approval_preset_display_name_copy(
    codex_agent_approval_preset_t preset,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_option_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *value,
    int32_t has_title,
    const codex_agent_string_view_t *title,
    int32_t has_description,
    const codex_agent_string_view_t *description,
    codex_agent_form_option_t **out_option);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_option_destroy(
    codex_agent_context_t *context,
    codex_agent_form_option_t **option);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_option_value_copy(
    codex_agent_context_t *context,
    codex_agent_form_option_t *option,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_option_title_copy(
    codex_agent_context_t *context,
    codex_agent_form_option_t *option,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_option_has_description(
    codex_agent_context_t *context,
    codex_agent_form_option_t *option,
    int32_t *out_has_description);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_option_description_copy(
    codex_agent_context_t *context,
    codex_agent_form_option_t *option,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_environment_variable_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *name,
    int32_t has_source,
    codex_agent_mcp_environment_source_t source,
    codex_agent_mcp_environment_variable_t **out_variable);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_environment_variable_destroy(
    codex_agent_context_t *context,
    codex_agent_mcp_environment_variable_t **variable);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_environment_variable_name_copy(
    codex_agent_context_t *context,
    codex_agent_mcp_environment_variable_t *variable,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_environment_variable_source(
    codex_agent_context_t *context,
    codex_agent_mcp_environment_variable_t *variable,
    int32_t *out_has_source,
    codex_agent_mcp_environment_source_t *out_source);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_oauth_configuration_create(
    codex_agent_context_t *context,
    int32_t has_client_id,
    const codex_agent_string_view_t *client_id,
    int32_t has_callback_port,
    int32_t callback_port,
    codex_agent_mcp_oauth_configuration_t **out_configuration);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_oauth_configuration_destroy(
    codex_agent_context_t *context,
    codex_agent_mcp_oauth_configuration_t **configuration);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_oauth_configuration_has_client_id(
    codex_agent_context_t *context,
    codex_agent_mcp_oauth_configuration_t *configuration,
    int32_t *out_has_client_id);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_oauth_configuration_client_id_copy(
    codex_agent_context_t *context,
    codex_agent_mcp_oauth_configuration_t *configuration,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_oauth_configuration_callback_port(
    codex_agent_context_t *context,
    codex_agent_mcp_oauth_configuration_t *configuration,
    int32_t *out_has_callback_port,
    int32_t *out_callback_port);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_tool_configuration_create(
    codex_agent_context_t *context,
    int32_t has_approval,
    codex_agent_mcp_tool_approval_t approval,
    codex_agent_mcp_tool_configuration_t **out_configuration);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_tool_configuration_destroy(
    codex_agent_context_t *context,
    codex_agent_mcp_tool_configuration_t **configuration);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_tool_configuration_approval(
    codex_agent_context_t *context,
    codex_agent_mcp_tool_configuration_t *configuration,
    int32_t *out_has_approval,
    codex_agent_mcp_tool_approval_t *out_approval);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_transport_http_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *url,
    int32_t has_bearer_token_environment_variable,
    const codex_agent_string_view_t *bearer_token_environment_variable,
    int32_t has_headers,
    const codex_agent_string_view_t *header_keys,
    const codex_agent_string_view_t *header_values,
    size_t header_count,
    int32_t has_environment_headers,
    const codex_agent_string_view_t *environment_header_keys,
    const codex_agent_string_view_t *environment_header_values,
    size_t environment_header_count,
    int32_t has_headers_helper,
    const codex_agent_string_view_t *headers_helper,
    codex_agent_mcp_transport_http_t **out_transport);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_transport_http_destroy(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_http_t **transport);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_transport_http_url_copy(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_http_t *transport,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_transport_http_has_bearer_token_environment_variable(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_http_t *transport,
    int32_t *out_has_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_transport_http_bearer_token_environment_variable_copy(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_http_t *transport,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_transport_http_has_headers(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_http_t *transport,
    int32_t *out_has_headers);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_transport_http_headers_count(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_http_t *transport,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_transport_http_headers_key_copy_at(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_http_t *transport,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_transport_http_headers_value_copy_at(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_http_t *transport,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_transport_http_has_environment_headers(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_http_t *transport,
    int32_t *out_has_environment_headers);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_transport_http_environment_headers_count(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_http_t *transport,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_transport_http_environment_headers_key_copy_at(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_http_t *transport,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_transport_http_environment_headers_value_copy_at(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_http_t *transport,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_transport_http_has_headers_helper(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_http_t *transport,
    int32_t *out_has_headers_helper);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_transport_http_headers_helper_copy(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_http_t *transport,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_transport_stdio_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *command,
    const codex_agent_string_view_t *arguments,
    size_t argument_count,
    int32_t has_working_directory,
    const codex_agent_string_view_t *working_directory,
    int32_t has_environment,
    const codex_agent_string_view_t *environment_keys,
    const codex_agent_string_view_t *environment_values,
    size_t environment_count,
    codex_agent_mcp_environment_variable_t *const *forwarded_environment,
    size_t forwarded_environment_count,
    codex_agent_mcp_transport_stdio_t **out_transport);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_transport_stdio_destroy(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_stdio_t **transport);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_transport_stdio_command_copy(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_stdio_t *transport,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_transport_stdio_arguments_count(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_stdio_t *transport,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_transport_stdio_argument_copy_at(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_stdio_t *transport,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_transport_stdio_has_working_directory(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_stdio_t *transport,
    int32_t *out_has_working_directory);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_transport_stdio_working_directory_copy(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_stdio_t *transport,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_transport_stdio_has_environment(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_stdio_t *transport,
    int32_t *out_has_environment);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_transport_stdio_environment_count(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_stdio_t *transport,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_transport_stdio_environment_key_copy_at(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_stdio_t *transport,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_transport_stdio_environment_value_copy_at(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_stdio_t *transport,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_transport_stdio_forwarded_environment_count(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_stdio_t *transport,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_transport_stdio_forwarded_environment_at(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_stdio_t *transport,
    size_t index,
    codex_agent_mcp_environment_variable_t **out_variable);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_validation_issue_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *field_name,
    codex_agent_elicitation_validation_reason_t reason,
    codex_agent_elicitation_validation_issue_t **out_issue);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_validation_issue_destroy(
    codex_agent_context_t *context,
    codex_agent_elicitation_validation_issue_t **issue);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_validation_issue_field_name_copy(
    codex_agent_context_t *context,
    codex_agent_elicitation_validation_issue_t *issue,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_validation_issue_reason(
    codex_agent_context_t *context,
    codex_agent_elicitation_validation_issue_t *issue,
    codex_agent_elicitation_validation_reason_t *out_reason);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_validation_create(
    codex_agent_context_t *context,
    codex_agent_elicitation_validation_issue_t *const *issues,
    size_t issue_count,
    codex_agent_elicitation_validation_t **out_validation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_validation_destroy(
    codex_agent_context_t *context,
    codex_agent_elicitation_validation_t **validation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_validation_issue_count(
    codex_agent_context_t *context,
    codex_agent_elicitation_validation_t *validation,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_validation_issue_at(
    codex_agent_context_t *context,
    codex_agent_elicitation_validation_t *validation,
    size_t index,
    codex_agent_elicitation_validation_issue_t **out_issue);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_validation_is_valid(
    codex_agent_context_t *context,
    codex_agent_elicitation_validation_t *validation,
    int32_t *out_is_valid);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plan_step_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *text,
    codex_agent_plan_step_status_t status,
    codex_agent_plan_step_t **out_step);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plan_step_destroy(
    codex_agent_context_t *context,
    codex_agent_plan_step_t **step);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plan_step_text_copy(
    codex_agent_context_t *context,
    codex_agent_plan_step_t *step,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plan_step_status(
    codex_agent_context_t *context,
    codex_agent_plan_step_t *step,
    codex_agent_plan_step_status_t *out_status);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_model_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *id,
    const codex_agent_string_view_t *display_name,
    const codex_agent_string_view_t *description,
    const codex_agent_string_view_t *supported_efforts,
    size_t supported_effort_count,
    const codex_agent_string_view_t *default_effort,
    int32_t is_default,
    codex_agent_service_tier_t *const *service_tiers,
    size_t service_tier_count,
    int32_t has_default_service_tier,
    const codex_agent_string_view_t *default_service_tier,
    codex_agent_model_t **out_model);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_model_destroy(
    codex_agent_context_t *context,
    codex_agent_model_t **model);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_model_id_copy(
    codex_agent_context_t *context,
    codex_agent_model_t *model,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_model_display_name_copy(
    codex_agent_context_t *context,
    codex_agent_model_t *model,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_model_description_copy(
    codex_agent_context_t *context,
    codex_agent_model_t *model,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_model_supported_efforts_count(
    codex_agent_context_t *context,
    codex_agent_model_t *model,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_model_supported_effort_copy_at(
    codex_agent_context_t *context,
    codex_agent_model_t *model,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_model_default_effort_copy(
    codex_agent_context_t *context,
    codex_agent_model_t *model,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_model_is_default(
    codex_agent_context_t *context,
    codex_agent_model_t *model,
    int32_t *out_is_default);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_model_service_tiers_count(
    codex_agent_context_t *context,
    codex_agent_model_t *model,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_model_service_tier_at(
    codex_agent_context_t *context,
    codex_agent_model_t *model,
    size_t index,
    codex_agent_service_tier_t **out_tier);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_model_has_default_service_tier(
    codex_agent_context_t *context,
    codex_agent_model_t *model,
    int32_t *out_has_default_service_tier);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_model_default_service_tier_copy(
    codex_agent_context_t *context,
    codex_agent_model_t *model,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plan_progress_create(
    codex_agent_context_t *context,
    int32_t has_explanation,
    const codex_agent_string_view_t *explanation,
    codex_agent_plan_step_t *const *steps,
    size_t step_count,
    codex_agent_plan_progress_t **out_progress);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plan_progress_destroy(
    codex_agent_context_t *context,
    codex_agent_plan_progress_t **progress);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plan_progress_has_explanation(
    codex_agent_context_t *context,
    codex_agent_plan_progress_t *progress,
    int32_t *out_has_explanation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plan_progress_explanation_copy(
    codex_agent_context_t *context,
    codex_agent_plan_progress_t *progress,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plan_progress_steps_count(
    codex_agent_context_t *context,
    codex_agent_plan_progress_t *progress,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plan_progress_step_at(
    codex_agent_context_t *context,
    codex_agent_plan_progress_t *progress,
    size_t index,
    codex_agent_plan_step_t **out_step);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_activity_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *id,
    const codex_agent_string_view_t *event_name,
    const codex_agent_string_view_t *handler_type,
    codex_agent_hook_run_status_t status,
    int32_t has_status_message,
    const codex_agent_string_view_t *status_message,
    const codex_agent_string_view_t *details,
    size_t detail_count,
    codex_agent_hook_activity_t **out_activity);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_activity_destroy(
    codex_agent_context_t *context,
    codex_agent_hook_activity_t **activity);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_activity_id_copy(
    codex_agent_context_t *context,
    codex_agent_hook_activity_t *activity,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_activity_event_name_copy(
    codex_agent_context_t *context,
    codex_agent_hook_activity_t *activity,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_activity_handler_type_copy(
    codex_agent_context_t *context,
    codex_agent_hook_activity_t *activity,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_activity_status(
    codex_agent_context_t *context,
    codex_agent_hook_activity_t *activity,
    codex_agent_hook_run_status_t *out_status);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_activity_has_status_message(
    codex_agent_context_t *context,
    codex_agent_hook_activity_t *activity,
    int32_t *out_has_status_message);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_activity_status_message_copy(
    codex_agent_context_t *context,
    codex_agent_hook_activity_t *activity,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_activity_details_count(
    codex_agent_context_t *context,
    codex_agent_hook_activity_t *activity,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_activity_detail_copy_at(
    codex_agent_context_t *context,
    codex_agent_hook_activity_t *activity,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_progress_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *text,
    const codex_agent_string_view_t *commentary,
    const codex_agent_string_view_t *reasoning,
    const codex_agent_string_view_t *plan,
    int32_t has_plan_progress,
    codex_agent_plan_progress_t *plan_progress,
    const codex_agent_string_view_t *shell_output,
    int32_t has_shell_exit_code,
    int32_t shell_exit_code,
    int32_t has_work_activity,
    codex_agent_work_activity_t work_activity,
    codex_agent_hook_activity_t *const *hook_activities,
    size_t hook_activity_count,
    int32_t is_truncated,
    codex_agent_turn_progress_t **out_progress);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_progress_destroy(
    codex_agent_context_t *context,
    codex_agent_turn_progress_t **progress);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_progress_text_copy(
    codex_agent_context_t *context,
    codex_agent_turn_progress_t *progress,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_progress_commentary_copy(
    codex_agent_context_t *context,
    codex_agent_turn_progress_t *progress,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_progress_reasoning_copy(
    codex_agent_context_t *context,
    codex_agent_turn_progress_t *progress,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_progress_plan_copy(
    codex_agent_context_t *context,
    codex_agent_turn_progress_t *progress,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_progress_has_plan_progress(
    codex_agent_context_t *context,
    codex_agent_turn_progress_t *progress,
    int32_t *out_has_plan_progress);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_progress_plan_progress(
    codex_agent_context_t *context,
    codex_agent_turn_progress_t *progress,
    codex_agent_plan_progress_t **out_plan_progress);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_progress_shell_output_copy(
    codex_agent_context_t *context,
    codex_agent_turn_progress_t *progress,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_progress_shell_exit_code(
    codex_agent_context_t *context,
    codex_agent_turn_progress_t *progress,
    int32_t *out_has_shell_exit_code,
    int32_t *out_shell_exit_code);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_progress_work_activity(
    codex_agent_context_t *context,
    codex_agent_turn_progress_t *progress,
    int32_t *out_has_work_activity,
    codex_agent_work_activity_t *out_work_activity);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_progress_hook_activities_count(
    codex_agent_context_t *context,
    codex_agent_turn_progress_t *progress,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_progress_hook_activity_at(
    codex_agent_context_t *context,
    codex_agent_turn_progress_t *progress,
    size_t index,
    codex_agent_hook_activity_t **out_activity);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_progress_is_truncated(
    codex_agent_context_t *context,
    codex_agent_turn_progress_t *progress,
    int32_t *out_is_truncated);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_reference_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *id,
    const codex_agent_string_view_t *name,
    const codex_agent_string_view_t *marketplace_name,
    int32_t has_marketplace_path,
    const codex_agent_string_view_t *marketplace_path,
    int32_t has_remote_plugin_id,
    const codex_agent_string_view_t *remote_plugin_id,
    codex_agent_plugin_reference_t **out_reference);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_reference_destroy(
    codex_agent_context_t *context,
    codex_agent_plugin_reference_t **reference);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_reference_id_copy(
    codex_agent_context_t *context,
    codex_agent_plugin_reference_t *reference,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_reference_name_copy(
    codex_agent_context_t *context,
    codex_agent_plugin_reference_t *reference,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_reference_marketplace_name_copy(
    codex_agent_context_t *context,
    codex_agent_plugin_reference_t *reference,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_reference_has_marketplace_path(
    codex_agent_context_t *context,
    codex_agent_plugin_reference_t *reference,
    int32_t *out_has_marketplace_path);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_reference_marketplace_path_copy(
    codex_agent_context_t *context,
    codex_agent_plugin_reference_t *reference,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_reference_has_remote_plugin_id(
    codex_agent_context_t *context,
    codex_agent_plugin_reference_t *reference,
    int32_t *out_has_remote_plugin_id);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_reference_remote_plugin_id_copy(
    codex_agent_context_t *context,
    codex_agent_plugin_reference_t *reference,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_reference_uri_copy(
    codex_agent_context_t *context,
    codex_agent_plugin_reference_t *reference,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_skill_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *name,
    const codex_agent_string_view_t *description,
    int32_t is_enabled,
    int32_t has_path,
    const codex_agent_string_view_t *path,
    codex_agent_plugin_skill_t **out_skill);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_skill_destroy(
    codex_agent_context_t *context,
    codex_agent_plugin_skill_t **skill);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_skill_name_copy(
    codex_agent_context_t *context,
    codex_agent_plugin_skill_t *skill,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_skill_description_copy(
    codex_agent_context_t *context,
    codex_agent_plugin_skill_t *skill,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_skill_is_enabled(
    codex_agent_context_t *context,
    codex_agent_plugin_skill_t *skill,
    int32_t *out_is_enabled);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_skill_has_path(
    codex_agent_context_t *context,
    codex_agent_plugin_skill_t *skill,
    int32_t *out_has_path);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_skill_path_copy(
    codex_agent_context_t *context,
    codex_agent_plugin_skill_t *skill,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_service_tier_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *id,
    const codex_agent_string_view_t *name,
    const codex_agent_string_view_t *description,
    codex_agent_service_tier_t **out_tier);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_service_tier_destroy(
    codex_agent_context_t *context,
    codex_agent_service_tier_t **tier);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_service_tier_id_copy(
    codex_agent_context_t *context,
    codex_agent_service_tier_t *tier,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_service_tier_name_copy(
    codex_agent_context_t *context,
    codex_agent_service_tier_t *tier,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_service_tier_description_copy(
    codex_agent_context_t *context,
    codex_agent_service_tier_t *tier,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_chunk_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *content,
    int32_t has_next_offset,
    int64_t next_offset,
    int64_t total_bytes,
    codex_agent_skill_chunk_t **out_chunk);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_chunk_destroy(
    codex_agent_context_t *context,
    codex_agent_skill_chunk_t **chunk);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_chunk_content_copy(
    codex_agent_context_t *context,
    codex_agent_skill_chunk_t *chunk,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_chunk_next_offset(
    codex_agent_context_t *context,
    codex_agent_skill_chunk_t *chunk,
    int32_t *out_has_next_offset,
    int64_t *out_next_offset);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_chunk_total_bytes(
    codex_agent_context_t *context,
    codex_agent_skill_chunk_t *chunk,
    int64_t *out_total_bytes);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_connector_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *id,
    const codex_agent_string_view_t *name,
    const codex_agent_string_view_t *description,
    int32_t has_install_url,
    const codex_agent_string_view_t *install_url,
    int32_t is_accessible,
    int32_t is_enabled,
    const codex_agent_string_view_t *plugin_names,
    size_t plugin_name_count,
    codex_agent_connector_t **out_connector);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_connector_destroy(
    codex_agent_context_t *context,
    codex_agent_connector_t **connector);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_connector_id_copy(
    codex_agent_context_t *context,
    codex_agent_connector_t *connector,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_connector_name_copy(
    codex_agent_context_t *context,
    codex_agent_connector_t *connector,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_connector_description_copy(
    codex_agent_context_t *context,
    codex_agent_connector_t *connector,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_connector_has_install_url(
    codex_agent_context_t *context,
    codex_agent_connector_t *connector,
    int32_t *out_has_install_url);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_connector_install_url_copy(
    codex_agent_context_t *context,
    codex_agent_connector_t *connector,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_connector_is_accessible(
    codex_agent_context_t *context,
    codex_agent_connector_t *connector,
    int32_t *out_is_accessible);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_connector_is_enabled(
    codex_agent_context_t *context,
    codex_agent_connector_t *connector,
    int32_t *out_is_enabled);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_connector_plugin_names_count(
    codex_agent_context_t *context,
    codex_agent_connector_t *connector,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_connector_plugin_names_copy_at(
    codex_agent_context_t *context,
    codex_agent_connector_t *connector,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_integration_connector_create(
    codex_agent_context_t *context,
    codex_agent_connector_t *connector,
    codex_agent_integration_connector_t **out_integration);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_integration_connector_destroy(
    codex_agent_context_t *context,
    codex_agent_integration_connector_t **integration);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_integration_connector_connector(
    codex_agent_context_t *context,
    codex_agent_integration_connector_t *integration,
    codex_agent_connector_t **out_connector);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_integration_connector_id_copy(
    codex_agent_context_t *context,
    codex_agent_integration_connector_t *integration,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_integration_connector_display_name_copy(
    codex_agent_context_t *context,
    codex_agent_integration_connector_t *integration,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_transport_from_http(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_http_t *http,
    codex_agent_mcp_transport_t **out_transport);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_transport_from_stdio(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_stdio_t *stdio,
    codex_agent_mcp_transport_t **out_transport);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_transport_destroy(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_t **transport);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_transport_kind(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_t *transport,
    codex_agent_mcp_transport_kind_t *out_kind);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_transport_http(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_t *transport,
    codex_agent_mcp_transport_http_t **out_http);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_transport_stdio(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_t *transport,
    codex_agent_mcp_transport_stdio_t **out_stdio);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *name,
    codex_agent_mcp_transport_t *transport,
    int32_t has_authentication,
    codex_agent_mcp_authentication_t authentication,
    const codex_agent_string_view_t *environment_id,
    int32_t is_enabled,
    int32_t is_required,
    int32_t supports_parallel_tool_calls,
    int32_t has_omit_tools_from,
    const codex_agent_mcp_tool_exposure_surface_t *omit_tools_from,
    size_t omit_tools_from_count,
    int32_t has_startup_timeout_seconds,
    double startup_timeout_seconds,
    int32_t has_tool_timeout_seconds,
    double tool_timeout_seconds,
    int32_t has_default_tool_approval,
    codex_agent_mcp_tool_approval_t default_tool_approval,
    int32_t has_enabled_tools,
    const codex_agent_string_view_t *enabled_tools,
    size_t enabled_tools_count,
    int32_t has_disabled_tools,
    const codex_agent_string_view_t *disabled_tools,
    size_t disabled_tools_count,
    int32_t has_scopes,
    const codex_agent_string_view_t *scopes,
    size_t scopes_count,
    int32_t has_oauth,
    codex_agent_mcp_oauth_configuration_t *oauth,
    int32_t has_oauth_resource,
    const codex_agent_string_view_t *oauth_resource,
    const codex_agent_string_view_t *tool_keys,
    codex_agent_mcp_tool_configuration_t *const *tool_configurations,
    size_t tool_count,
    codex_agent_mcp_server_configuration_t **out_configuration);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_destroy(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t **configuration);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_name_copy(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_transport(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    codex_agent_mcp_transport_t **out_transport);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_authentication(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    int32_t *out_has_authentication,
    codex_agent_mcp_authentication_t *out_authentication);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_environment_id_copy(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_is_enabled(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    int32_t *out_is_enabled);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_is_required(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    int32_t *out_is_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_supports_parallel_tool_calls(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    int32_t *out_supports_parallel_tool_calls);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_has_omit_tools_from(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    int32_t *out_has_omit_tools_from);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_omit_tools_from_count(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_omit_tools_from_at(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    size_t index,
    codex_agent_mcp_tool_exposure_surface_t *out_surface);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_startup_timeout_seconds(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    int32_t *out_has_value,
    double *out_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_tool_timeout_seconds(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    int32_t *out_has_value,
    double *out_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_default_tool_approval(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    int32_t *out_has_value,
    codex_agent_mcp_tool_approval_t *out_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_has_enabled_tools(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    int32_t *out_has_enabled_tools);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_enabled_tools_count(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_enabled_tool_copy_at(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_has_disabled_tools(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    int32_t *out_has_disabled_tools);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_disabled_tools_count(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_disabled_tool_copy_at(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_has_scopes(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    int32_t *out_has_scopes);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_scopes_count(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_scope_copy_at(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_has_oauth(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    int32_t *out_has_oauth);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_oauth(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    codex_agent_mcp_oauth_configuration_t **out_oauth);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_has_oauth_resource(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    int32_t *out_has_oauth_resource);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_oauth_resource_copy(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_tools_count(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_tools_key_copy_at(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_mcp_server_configuration_tools_value_at(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t *configuration,
    size_t index,
    codex_agent_mcp_tool_configuration_t **out_tool_configuration);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_server_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *name,
    const codex_agent_string_view_t *display_name,
    codex_agent_mcp_auth_status_t auth_status,
    codex_agent_mcp_server_configuration_t *configuration,
    codex_agent_resource_origin_t origin,
    int32_t can_remove,
    codex_agent_mcp_server_t **out_server);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_server_destroy(
    codex_agent_context_t *context,
    codex_agent_mcp_server_t **server);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_server_name_copy(
    codex_agent_context_t *context,
    codex_agent_mcp_server_t *server,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_server_display_name_copy(
    codex_agent_context_t *context,
    codex_agent_mcp_server_t *server,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_server_auth_status(
    codex_agent_context_t *context,
    codex_agent_mcp_server_t *server,
    codex_agent_mcp_auth_status_t *out_auth_status);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_server_has_configuration(
    codex_agent_context_t *context,
    codex_agent_mcp_server_t *server,
    int32_t *out_has_configuration);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_server_configuration(
    codex_agent_context_t *context,
    codex_agent_mcp_server_t *server,
    codex_agent_mcp_server_configuration_t **out_configuration);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_server_origin(
    codex_agent_context_t *context,
    codex_agent_mcp_server_t *server,
    codex_agent_resource_origin_t *out_origin);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_server_can_remove(
    codex_agent_context_t *context,
    codex_agent_mcp_server_t *server,
    int32_t *out_can_remove);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_server_is_authorized(
    codex_agent_context_t *context,
    codex_agent_mcp_server_t *server,
    int32_t *out_is_authorized);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_integration_mcp_server_create(
    codex_agent_context_t *context,
    codex_agent_mcp_server_t *server,
    codex_agent_integration_mcp_server_t **out_integration);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_integration_mcp_server_destroy(
    codex_agent_context_t *context,
    codex_agent_integration_mcp_server_t **integration);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_integration_mcp_server_server(
    codex_agent_context_t *context,
    codex_agent_integration_mcp_server_t *integration,
    codex_agent_mcp_server_t **out_server);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_integration_mcp_server_id_copy(
    codex_agent_context_t *context,
    codex_agent_integration_mcp_server_t *integration,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_integration_mcp_server_display_name_copy(
    codex_agent_context_t *context,
    codex_agent_integration_mcp_server_t *integration,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *name,
    const codex_agent_string_view_t *display_name,
    const codex_agent_string_view_t *description,
    const codex_agent_string_view_t *path,
    codex_agent_skill_scope_t scope,
    int32_t is_enabled,
    int32_t has_brand_color,
    const codex_agent_string_view_t *brand_color,
    const codex_agent_string_view_t *dependencies,
    size_t dependency_count,
    int32_t can_uninstall,
    int32_t has_origin,
    codex_agent_resource_origin_t origin,
    codex_agent_skill_t **out_skill);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_destroy(
    codex_agent_context_t *context,
    codex_agent_skill_t **skill);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_name_copy(
    codex_agent_context_t *context,
    codex_agent_skill_t *skill,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_display_name_copy(
    codex_agent_context_t *context,
    codex_agent_skill_t *skill,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_description_copy(
    codex_agent_context_t *context,
    codex_agent_skill_t *skill,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_path_copy(
    codex_agent_context_t *context,
    codex_agent_skill_t *skill,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_scope(
    codex_agent_context_t *context,
    codex_agent_skill_t *skill,
    codex_agent_skill_scope_t *out_scope);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_is_enabled(
    codex_agent_context_t *context,
    codex_agent_skill_t *skill,
    int32_t *out_is_enabled);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_has_brand_color(
    codex_agent_context_t *context,
    codex_agent_skill_t *skill,
    int32_t *out_has_brand_color);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_brand_color_copy(
    codex_agent_context_t *context,
    codex_agent_skill_t *skill,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_dependencies_count(
    codex_agent_context_t *context,
    codex_agent_skill_t *skill,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_dependencies_copy_at(
    codex_agent_context_t *context,
    codex_agent_skill_t *skill,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_can_uninstall(
    codex_agent_context_t *context,
    codex_agent_skill_t *skill,
    int32_t *out_can_uninstall);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_origin(
    codex_agent_context_t *context,
    codex_agent_skill_t *skill,
    codex_agent_resource_origin_t *out_origin);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_catalog_create(
    codex_agent_context_t *context,
    codex_agent_skill_t *const *skills,
    size_t skill_count,
    const codex_agent_string_view_t *errors,
    size_t error_count,
    codex_agent_skill_catalog_t **out_catalog);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_catalog_destroy(
    codex_agent_context_t *context,
    codex_agent_skill_catalog_t **catalog);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_catalog_skills_count(
    codex_agent_context_t *context,
    codex_agent_skill_catalog_t *catalog,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_catalog_skills_at(
    codex_agent_context_t *context,
    codex_agent_skill_catalog_t *catalog,
    size_t index,
    codex_agent_skill_t **out_skill);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_catalog_errors_count(
    codex_agent_context_t *context,
    codex_agent_skill_catalog_t *catalog,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_catalog_errors_copy_at(
    codex_agent_context_t *context,
    codex_agent_skill_catalog_t *catalog,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_summary_create(
    codex_agent_context_t *context,
    codex_agent_plugin_reference_t *reference,
    const codex_agent_string_view_t *display_name,
    const codex_agent_string_view_t *description,
    int32_t is_installed,
    int32_t is_enabled,
    codex_agent_plugin_install_policy_t install_policy,
    codex_agent_plugin_auth_policy_t auth_policy,
    int32_t is_available,
    const codex_agent_string_view_t *capabilities,
    size_t capability_count,
    int32_t has_brand_color,
    const codex_agent_string_view_t *brand_color,
    int32_t has_privacy_policy_url,
    const codex_agent_string_view_t *privacy_policy_url,
    int32_t has_terms_of_service_url,
    const codex_agent_string_view_t *terms_of_service_url,
    int32_t has_website_url,
    const codex_agent_string_view_t *website_url,
    codex_agent_plugin_summary_t **out_summary);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_summary_destroy(
    codex_agent_context_t *context,
    codex_agent_plugin_summary_t **summary);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_summary_reference(
    codex_agent_context_t *context,
    codex_agent_plugin_summary_t *summary,
    codex_agent_plugin_reference_t **out_reference);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_summary_display_name_copy(
    codex_agent_context_t *context,
    codex_agent_plugin_summary_t *summary,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_summary_description_copy(
    codex_agent_context_t *context,
    codex_agent_plugin_summary_t *summary,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_summary_is_installed(
    codex_agent_context_t *context,
    codex_agent_plugin_summary_t *summary,
    int32_t *out_is_installed);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_summary_is_enabled(
    codex_agent_context_t *context,
    codex_agent_plugin_summary_t *summary,
    int32_t *out_is_enabled);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_summary_install_policy(
    codex_agent_context_t *context,
    codex_agent_plugin_summary_t *summary,
    codex_agent_plugin_install_policy_t *out_install_policy);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_summary_auth_policy(
    codex_agent_context_t *context,
    codex_agent_plugin_summary_t *summary,
    codex_agent_plugin_auth_policy_t *out_auth_policy);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_summary_is_available(
    codex_agent_context_t *context,
    codex_agent_plugin_summary_t *summary,
    int32_t *out_is_available);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_summary_capabilities_count(
    codex_agent_context_t *context,
    codex_agent_plugin_summary_t *summary,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_summary_capabilities_copy_at(
    codex_agent_context_t *context,
    codex_agent_plugin_summary_t *summary,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_summary_has_brand_color(
    codex_agent_context_t *context,
    codex_agent_plugin_summary_t *summary,
    int32_t *out_has_brand_color);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_summary_brand_color_copy(
    codex_agent_context_t *context,
    codex_agent_plugin_summary_t *summary,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_summary_has_privacy_policy_url(
    codex_agent_context_t *context,
    codex_agent_plugin_summary_t *summary,
    int32_t *out_has_privacy_policy_url);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_summary_privacy_policy_url_copy(
    codex_agent_context_t *context,
    codex_agent_plugin_summary_t *summary,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_summary_has_terms_of_service_url(
    codex_agent_context_t *context,
    codex_agent_plugin_summary_t *summary,
    int32_t *out_has_terms_of_service_url);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_summary_terms_of_service_url_copy(
    codex_agent_context_t *context,
    codex_agent_plugin_summary_t *summary,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_summary_has_website_url(
    codex_agent_context_t *context,
    codex_agent_plugin_summary_t *summary,
    int32_t *out_has_website_url);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_summary_website_url_copy(
    codex_agent_context_t *context,
    codex_agent_plugin_summary_t *summary,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_catalog_create(
    codex_agent_context_t *context,
    codex_agent_plugin_summary_t *const *plugins,
    size_t plugin_count,
    const codex_agent_string_view_t *errors,
    size_t error_count,
    codex_agent_catalog_freshness_t freshness,
    codex_agent_plugin_catalog_t **out_catalog);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_catalog_destroy(
    codex_agent_context_t *context,
    codex_agent_plugin_catalog_t **catalog);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_catalog_plugins_count(
    codex_agent_context_t *context,
    codex_agent_plugin_catalog_t *catalog,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_catalog_plugins_at(
    codex_agent_context_t *context,
    codex_agent_plugin_catalog_t *catalog,
    size_t index,
    codex_agent_plugin_summary_t **out_summary);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_catalog_errors_count(
    codex_agent_context_t *context,
    codex_agent_plugin_catalog_t *catalog,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_catalog_errors_copy_at(
    codex_agent_context_t *context,
    codex_agent_plugin_catalog_t *catalog,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_catalog_freshness(
    codex_agent_context_t *context,
    codex_agent_plugin_catalog_t *catalog,
    codex_agent_catalog_freshness_t *out_freshness);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_detail_create(
    codex_agent_context_t *context,
    codex_agent_plugin_summary_t *summary,
    const codex_agent_string_view_t *description,
    codex_agent_plugin_skill_t *const *skills,
    size_t skill_count,
    codex_agent_connector_t *const *connectors,
    size_t connector_count,
    const codex_agent_string_view_t *mcp_servers,
    size_t mcp_server_count,
    int32_t hook_count,
    codex_agent_plugin_detail_t **out_detail);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_detail_destroy(
    codex_agent_context_t *context,
    codex_agent_plugin_detail_t **detail);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_detail_summary(
    codex_agent_context_t *context,
    codex_agent_plugin_detail_t *detail,
    codex_agent_plugin_summary_t **out_summary);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_detail_description_copy(
    codex_agent_context_t *context,
    codex_agent_plugin_detail_t *detail,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_detail_skills_count(
    codex_agent_context_t *context,
    codex_agent_plugin_detail_t *detail,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_detail_skills_at(
    codex_agent_context_t *context,
    codex_agent_plugin_detail_t *detail,
    size_t index,
    codex_agent_plugin_skill_t **out_skill);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_detail_connectors_count(
    codex_agent_context_t *context,
    codex_agent_plugin_detail_t *detail,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_detail_connectors_at(
    codex_agent_context_t *context,
    codex_agent_plugin_detail_t *detail,
    size_t index,
    codex_agent_connector_t **out_connector);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_detail_mcp_servers_count(
    codex_agent_context_t *context,
    codex_agent_plugin_detail_t *detail,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_detail_mcp_servers_copy_at(
    codex_agent_context_t *context,
    codex_agent_plugin_detail_t *detail,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_detail_hook_count(
    codex_agent_context_t *context,
    codex_agent_plugin_detail_t *detail,
    int32_t *out_hook_count);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_install_result_create(
    codex_agent_context_t *context,
    codex_agent_plugin_auth_policy_t auth_policy,
    codex_agent_connector_t *const *connectors,
    size_t connector_count,
    int32_t has_message,
    const codex_agent_string_view_t *message,
    codex_agent_plugin_install_result_t **out_result);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_install_result_destroy(
    codex_agent_context_t *context,
    codex_agent_plugin_install_result_t **result);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_install_result_auth_policy(
    codex_agent_context_t *context,
    codex_agent_plugin_install_result_t *result,
    codex_agent_plugin_auth_policy_t *out_auth_policy);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_install_result_connectors_count(
    codex_agent_context_t *context,
    codex_agent_plugin_install_result_t *result,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_install_result_connectors_at(
    codex_agent_context_t *context,
    codex_agent_plugin_install_result_t *result,
    size_t index,
    codex_agent_connector_t **out_connector);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_install_result_has_message(
    codex_agent_context_t *context,
    codex_agent_plugin_install_result_t *result,
    int32_t *out_has_message);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugin_install_result_message_copy(
    codex_agent_context_t *context,
    codex_agent_plugin_install_result_t *result,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_capability_id_copy(
    codex_agent_capability_t capability,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_capability_display_label_copy(
    codex_agent_capability_t capability,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_capability_has_icon(
    codex_agent_capability_t capability,
    int32_t *out_has_icon);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_capability_icon_copy(
    codex_agent_capability_t capability,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_capability_prompt_label_copy(
    codex_agent_capability_t capability,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skill_scope_display_name_copy(
    codex_agent_skill_scope_t scope,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_create(
    codex_agent_context_t *context,
    const codex_agent_host_options_t *options,
    codex_agent_host_t **out_host);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_retain(
    codex_agent_context_t *context,
    codex_agent_host_t *host,
    codex_agent_host_t **out_host);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_release(
    codex_agent_context_t *context,
    codex_agent_host_t **host);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_start(
    codex_agent_context_t *context,
    codex_agent_host_t *host,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_select_workspace(
    codex_agent_context_t *context,
    codex_agent_host_t *host,
    const codex_agent_path_workspace_selection_t *selection,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_close(
    codex_agent_context_t *context,
    codex_agent_host_t *host,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_state_get(
    codex_agent_context_t *context,
    codex_agent_host_t *host,
    codex_agent_snapshot_t **out_snapshot);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_state_subscribe(
    codex_agent_context_t *context,
    codex_agent_host_t *host,
    codex_agent_state_callback_t callback,
    void *user_data,
    codex_agent_subscription_t **out_subscription);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_agent_retain(
    codex_agent_context_t *context,
    codex_agent_agent_t *agent,
    codex_agent_agent_t **out_agent);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_agent_release(
    codex_agent_context_t *context,
    codex_agent_agent_t **agent);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_agent_conversations(
    codex_agent_context_t *context,
    codex_agent_agent_t *agent,
    codex_agent_conversations_t **out_conversations);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_agent_authentication(
    codex_agent_context_t *context,
    codex_agent_agent_t *agent,
    codex_agent_authentication_t **out_authentication);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_agent_interactions(
    codex_agent_context_t *context,
    codex_agent_agent_t *agent,
    codex_agent_interactions_t **out_interactions);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_agent_integration_authorization(
    codex_agent_context_t *context,
    codex_agent_agent_t *agent,
    codex_agent_integration_authorization_t **out_authorization);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_agent_models(
    codex_agent_context_t *context,
    codex_agent_agent_t *agent,
    codex_agent_models_t **out_models);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_agent_skills(
    codex_agent_context_t *context,
    codex_agent_agent_t *agent,
    codex_agent_skills_t **out_skills);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_agent_hooks(
    codex_agent_context_t *context,
    codex_agent_agent_t *agent,
    codex_agent_hooks_t **out_hooks);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_agent_plugins(
    codex_agent_context_t *context,
    codex_agent_agent_t *agent,
    codex_agent_plugins_t **out_plugins);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_agent_connectors(
    codex_agent_context_t *context,
    codex_agent_agent_t *agent,
    codex_agent_connectors_t **out_connectors);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_agent_mcp_servers(
    codex_agent_context_t *context,
    codex_agent_agent_t *agent,
    codex_agent_mcp_servers_t **out_mcp_servers);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_agent_workspace(
    codex_agent_context_t *context,
    codex_agent_agent_t *agent,
    codex_agent_workspace_t **out_workspace);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_authentication_retain(
    codex_agent_context_t *context,
    codex_agent_authentication_t *authentication,
    codex_agent_authentication_t **out_authentication);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_authentication_release(
    codex_agent_context_t *context,
    codex_agent_authentication_t **authentication);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_interactions_retain(
    codex_agent_context_t *context,
    codex_agent_interactions_t *interactions,
    codex_agent_interactions_t **out_interactions);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_interactions_release(
    codex_agent_context_t *context,
    codex_agent_interactions_t **interactions);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_integration_authorization_retain(
    codex_agent_context_t *context,
    codex_agent_integration_authorization_t *authorization,
    codex_agent_integration_authorization_t **out_authorization);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_integration_authorization_release(
    codex_agent_context_t *context,
    codex_agent_integration_authorization_t **authorization);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_models_retain(
    codex_agent_context_t *context,
    codex_agent_models_t *models,
    codex_agent_models_t **out_models);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_models_release(
    codex_agent_context_t *context,
    codex_agent_models_t **models);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skills_retain(
    codex_agent_context_t *context,
    codex_agent_skills_t *skills,
    codex_agent_skills_t **out_skills);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skills_release(
    codex_agent_context_t *context,
    codex_agent_skills_t **skills);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hooks_retain(
    codex_agent_context_t *context,
    codex_agent_hooks_t *hooks,
    codex_agent_hooks_t **out_hooks);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hooks_release(
    codex_agent_context_t *context,
    codex_agent_hooks_t **hooks);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugins_retain(
    codex_agent_context_t *context,
    codex_agent_plugins_t *plugins,
    codex_agent_plugins_t **out_plugins);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugins_release(
    codex_agent_context_t *context,
    codex_agent_plugins_t **plugins);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_connectors_retain(
    codex_agent_context_t *context,
    codex_agent_connectors_t *connectors,
    codex_agent_connectors_t **out_connectors);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_connectors_release(
    codex_agent_context_t *context,
    codex_agent_connectors_t **connectors);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_servers_retain(
    codex_agent_context_t *context,
    codex_agent_mcp_servers_t *mcp_servers,
    codex_agent_mcp_servers_t **out_mcp_servers);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_servers_release(
    codex_agent_context_t *context,
    codex_agent_mcp_servers_t **mcp_servers);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skills_is_available(
    codex_agent_context_t *context,
    codex_agent_skills_t *skills,
    int32_t *out_is_available);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hooks_is_available(
    codex_agent_context_t *context,
    codex_agent_hooks_t *hooks,
    int32_t *out_is_available);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugins_is_available(
    codex_agent_context_t *context,
    codex_agent_plugins_t *plugins,
    int32_t *out_is_available);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_connectors_is_available(
    codex_agent_context_t *context,
    codex_agent_connectors_t *connectors,
    int32_t *out_is_available);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_servers_is_available(
    codex_agent_context_t *context,
    codex_agent_mcp_servers_t *mcp_servers,
    int32_t *out_is_available);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_authentication_authenticate_api_key(
    codex_agent_context_t *context,
    codex_agent_authentication_t *authentication,
    codex_agent_authentication_method_api_key_t *method,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_authentication_authenticate_chat_gpt_browser(
    codex_agent_context_t *context,
    codex_agent_authentication_t *authentication,
    codex_agent_authentication_method_chat_gpt_browser_t *method,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_authentication_authenticate_chat_gpt_device_code(
    codex_agent_context_t *context,
    codex_agent_authentication_t *authentication,
    codex_agent_authentication_method_chat_gpt_device_code_t *method,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_authentication_cancel(
    codex_agent_context_t *context,
    codex_agent_authentication_t *authentication,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_authentication_sign_out(
    codex_agent_context_t *context,
    codex_agent_authentication_t *authentication,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_integration_authorization_authorize(
    codex_agent_context_t *context,
    codex_agent_integration_authorization_t *authorization,
    codex_agent_integration_t *target,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_integration_authorization_cancel(
    codex_agent_context_t *context,
    codex_agent_integration_authorization_t *authorization,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_models_list(
    codex_agent_context_t *context,
    codex_agent_models_t *models,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_models_resolve(
    codex_agent_context_t *context,
    codex_agent_models_t *models,
    codex_agent_resolution_t resolution,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_models_resolve_effort(
    codex_agent_context_t *context,
    codex_agent_models_t *models,
    codex_agent_model_t *model,
    codex_agent_resolution_t resolution,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_models_resolve_service_tier(
    codex_agent_context_t *context,
    codex_agent_models_t *models,
    codex_agent_model_t *model,
    codex_agent_resolution_t resolution,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skills_list(
    codex_agent_context_t *context,
    codex_agent_skills_t *skills,
    int32_t force_reload,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skills_read(
    codex_agent_context_t *context,
    codex_agent_skills_t *skills,
    const codex_agent_string_view_t *path,
    int64_t offset,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skills_install(
    codex_agent_context_t *context,
    codex_agent_skills_t *skills,
    const codex_agent_string_view_t *directory,
    codex_agent_installation_scope_t scope,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_skills_uninstall(
    codex_agent_context_t *context,
    codex_agent_skills_t *skills,
    codex_agent_skill_t *skill,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hooks_list(
    codex_agent_context_t *context,
    codex_agent_hooks_t *hooks,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hooks_install(
    codex_agent_context_t *context,
    codex_agent_hooks_t *hooks,
    const codex_agent_string_view_t *directory,
    codex_agent_installation_scope_t scope,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hooks_uninstall(
    codex_agent_context_t *context,
    codex_agent_hooks_t *hooks,
    codex_agent_hook_t *hook,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hooks_trust(
    codex_agent_context_t *context,
    codex_agent_hooks_t *hooks,
    codex_agent_hook_t *hook,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugins_list(
    codex_agent_context_t *context,
    codex_agent_plugins_t *plugins,
    int32_t force_reload,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugins_read(
    codex_agent_context_t *context,
    codex_agent_plugins_t *plugins,
    codex_agent_plugin_reference_t *plugin,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugins_install(
    codex_agent_context_t *context,
    codex_agent_plugins_t *plugins,
    codex_agent_plugin_reference_t *plugin,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_plugins_uninstall(
    codex_agent_context_t *context,
    codex_agent_plugins_t *plugins,
    codex_agent_plugin_reference_t *plugin,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_connectors_list(
    codex_agent_context_t *context,
    codex_agent_connectors_t *connectors,
    int32_t force_reload,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_servers_list(
    codex_agent_context_t *context,
    codex_agent_mcp_servers_t *mcp_servers,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_servers_add(
    codex_agent_context_t *context,
    codex_agent_mcp_servers_t *mcp_servers,
    codex_agent_mcp_server_configuration_t *configuration,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_mcp_servers_remove(
    codex_agent_context_t *context,
    codex_agent_mcp_servers_t *mcp_servers,
    codex_agent_mcp_server_t *server,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversations_retain(
    codex_agent_context_t *context,
    codex_agent_conversations_t *conversations,
    codex_agent_conversations_t **out_conversations);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversations_release(
    codex_agent_context_t *context,
    codex_agent_conversations_t **conversations);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversations_active_get(
    codex_agent_context_t *context,
    codex_agent_conversations_t *conversations,
    codex_agent_snapshot_t **out_snapshot);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversations_active_subscribe(
    codex_agent_context_t *context,
    codex_agent_conversations_t *conversations,
    codex_agent_state_callback_t callback,
    void *user_data,
    codex_agent_subscription_t **out_subscription);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversations_list(
    codex_agent_context_t *context,
    codex_agent_conversations_t *conversations,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversations_read(
    codex_agent_context_t *context,
    codex_agent_conversations_t *conversations,
    codex_agent_conversation_id_t *conversation_id,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversations_rename(
    codex_agent_context_t *context,
    codex_agent_conversations_t *conversations,
    codex_agent_conversation_id_t *conversation_id,
    const codex_agent_string_view_t *name,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversations_delete(
    codex_agent_context_t *context,
    codex_agent_conversations_t *conversations,
    codex_agent_conversation_id_t *conversation_id,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversations_open(
    codex_agent_context_t *context,
    codex_agent_conversations_t *conversations,
    const codex_agent_conversation_open_options_t *options,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_retain(
    codex_agent_context_t *context,
    codex_agent_conversation_t *conversation,
    codex_agent_conversation_t **out_conversation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_release(
    codex_agent_context_t *context,
    codex_agent_conversation_t **conversation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_is_same(
    codex_agent_context_t *context,
    codex_agent_conversation_t *left,
    codex_agent_conversation_t *right,
    int32_t *out_same);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_send(
    codex_agent_context_t *context,
    codex_agent_conversation_t *conversation,
    const codex_agent_string_view_t *prompt,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_send_request(
    codex_agent_context_t *context,
    codex_agent_conversation_t *conversation,
    codex_agent_turn_request_t *request,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_run_shell_command(
    codex_agent_context_t *context,
    codex_agent_conversation_t *conversation,
    const codex_agent_string_view_t *command,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_reload(
    codex_agent_context_t *context,
    codex_agent_conversation_t *conversation,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_cancel_turn(
    codex_agent_context_t *context,
    codex_agent_conversation_t *conversation,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_close(
    codex_agent_context_t *context,
    codex_agent_conversation_t *conversation,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_state_get(
    codex_agent_context_t *context,
    codex_agent_conversation_t *conversation,
    codex_agent_snapshot_t **out_snapshot);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_state_subscribe(
    codex_agent_context_t *context,
    codex_agent_conversation_t *conversation,
    codex_agent_state_callback_t callback,
    void *user_data,
    codex_agent_subscription_t **out_subscription);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_cancel(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_result(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    codex_agent_status_t *out_result);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_conversation(
    codex_agent_context_t *context,
    codex_agent_conversations_t *conversations,
    codex_agent_operation_t *operation,
    codex_agent_conversation_t **out_conversation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_failure(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    codex_agent_failure_t **out_failure);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_operation_conversation_summaries_count(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_operation_conversation_summary_at(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    size_t index,
    codex_agent_conversation_summary_t **out_summary);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_conversation_value(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    codex_agent_conversation_value_t **out_conversation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_models_count(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_model_at(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    size_t index,
    codex_agent_model_t **out_model);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_model(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    codex_agent_model_t **out_model);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_string_copy(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_has_service_tier(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    int32_t *out_has_service_tier);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_service_tier(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    codex_agent_service_tier_t **out_service_tier);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_skill_catalog(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    codex_agent_skill_catalog_t **out_catalog);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_skill_chunk(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    codex_agent_skill_chunk_t **out_chunk);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_skill(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    codex_agent_skill_t **out_skill);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_hook_catalog(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    codex_agent_hook_catalog_t **out_catalog);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_hook(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    codex_agent_hook_t **out_hook);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_plugin_catalog(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    codex_agent_plugin_catalog_t **out_catalog);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_plugin_detail(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    codex_agent_plugin_detail_t **out_detail);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_operation_plugin_install_result(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    codex_agent_plugin_install_result_t **out_result);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_connectors_count(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_connector_at(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    size_t index,
    codex_agent_connector_t **out_connector);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_mcp_servers_count(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_mcp_server_at(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    size_t index,
    codex_agent_mcp_server_t **out_server);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_mcp_server(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    codex_agent_mcp_server_t **out_server);
/*
 * Destroy requests cancellation and never waits. BUSY preserves the slot and
 * means callbacks and user_data remain live; retry after quiescence. OK writes
 * NULL and guarantees that no later callback for this operation can begin.
 */
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_destroy(
    codex_agent_context_t *context,
    codex_agent_operation_t **operation);

/*
 * Subscription destruction has the same BUSY/retry/slot/quiescence contract
 * as operation destruction. A terminal callback occurs at most once.
 */
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_subscription_destroy(
    codex_agent_context_t *context,
    codex_agent_subscription_t **subscription);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_snapshot_destroy(
    codex_agent_context_t *context,
    codex_agent_snapshot_t **snapshot);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_state_kind(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *snapshot,
    codex_agent_host_state_kind_t *out_kind);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_state_agent(
    codex_agent_context_t *context,
    codex_agent_host_t *host,
    codex_agent_snapshot_t *snapshot,
    codex_agent_agent_t **out_agent);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_state_failure(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *snapshot,
    codex_agent_failure_t **out_failure);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_state_has_workspace(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *snapshot,
    int32_t *out_has_workspace);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_state_workspace_path_copy(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *snapshot,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_host_state_workspace_display_name_copy(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *snapshot,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_state_requirement_reason(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *snapshot,
    codex_agent_workspace_selection_reason_t *out_reason);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_host_state_requirement_message_copy(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *snapshot,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_active_conversation(
    codex_agent_context_t *context,
    codex_agent_conversations_t *conversations,
    codex_agent_snapshot_t *snapshot,
    codex_agent_conversation_t **out_conversation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_state_status(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *snapshot,
    codex_agent_conversation_status_t *out_status);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_state_failure(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *snapshot,
    codex_agent_failure_t **out_failure);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_from_plugin(
    codex_agent_context_t *context,
    codex_agent_invocation_plugin_t *plugin,
    codex_agent_invocation_t **out_invocation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_from_skill(
    codex_agent_context_t *context,
    codex_agent_invocation_skill_t *skill,
    codex_agent_invocation_t **out_invocation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_destroy(
    codex_agent_context_t *context,
    codex_agent_invocation_t **invocation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_kind(
    codex_agent_context_t *context,
    codex_agent_invocation_t *invocation,
    codex_agent_invocation_kind_t *out_kind);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_plugin(
    codex_agent_context_t *context,
    codex_agent_invocation_t *invocation,
    codex_agent_invocation_plugin_t **out_plugin);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_skill(
    codex_agent_context_t *context,
    codex_agent_invocation_t *invocation,
    codex_agent_invocation_skill_t **out_skill);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *id,
    int32_t has_client_message_id,
    const codex_agent_string_view_t *client_message_id,
    codex_agent_message_role_t role,
    const codex_agent_string_view_t *text,
    codex_agent_collaboration_mode_t collaboration_mode,
    int32_t has_reasoning,
    const codex_agent_string_view_t *reasoning,
    int32_t has_plan,
    const codex_agent_string_view_t *plan,
    int32_t has_shell_command,
    const codex_agent_string_view_t *shell_command,
    int32_t has_exit_code,
    int32_t exit_code,
    const codex_agent_capability_t *capabilities,
    size_t capability_count,
    codex_agent_invocation_t *const *invocations,
    size_t invocation_count,
    codex_agent_message_t **out_message);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_destroy(
    codex_agent_context_t *context,
    codex_agent_message_t **message);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_id_copy(
    codex_agent_context_t *context,
    codex_agent_message_t *message,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_has_client_message_id(
    codex_agent_context_t *context,
    codex_agent_message_t *message,
    int32_t *out_has_client_message_id);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_client_message_id_copy(
    codex_agent_context_t *context,
    codex_agent_message_t *message,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_role(
    codex_agent_context_t *context,
    codex_agent_message_t *message,
    codex_agent_message_role_t *out_role);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_text_copy(
    codex_agent_context_t *context,
    codex_agent_message_t *message,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_collaboration_mode(
    codex_agent_context_t *context,
    codex_agent_message_t *message,
    codex_agent_collaboration_mode_t *out_mode);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_has_reasoning(
    codex_agent_context_t *context,
    codex_agent_message_t *message,
    int32_t *out_has_reasoning);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_reasoning_copy(
    codex_agent_context_t *context,
    codex_agent_message_t *message,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_has_plan(
    codex_agent_context_t *context,
    codex_agent_message_t *message,
    int32_t *out_has_plan);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_plan_copy(
    codex_agent_context_t *context,
    codex_agent_message_t *message,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_has_shell_command(
    codex_agent_context_t *context,
    codex_agent_message_t *message,
    int32_t *out_has_shell_command);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_shell_command_copy(
    codex_agent_context_t *context,
    codex_agent_message_t *message,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_exit_code(
    codex_agent_context_t *context,
    codex_agent_message_t *message,
    int32_t *out_has_exit_code,
    int32_t *out_exit_code);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_capabilities_count(
    codex_agent_context_t *context,
    codex_agent_message_t *message,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_has_capability(
    codex_agent_context_t *context,
    codex_agent_message_t *message,
    codex_agent_capability_t capability,
    int32_t *out_has_capability);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_invocations_count(
    codex_agent_context_t *context,
    codex_agent_message_t *message,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_invocation_at(
    codex_agent_context_t *context,
    codex_agent_message_t *message,
    size_t index,
    codex_agent_invocation_t **out_invocation);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_value_create(
    codex_agent_context_t *context,
    codex_agent_conversation_summary_t *summary,
    codex_agent_message_t *const *messages,
    size_t message_count,
    codex_agent_conversation_value_t **out_conversation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_value_destroy(
    codex_agent_context_t *context,
    codex_agent_conversation_value_t **conversation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_value_summary(
    codex_agent_context_t *context,
    codex_agent_conversation_value_t *conversation,
    codex_agent_conversation_summary_t **out_summary);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_value_messages_count(
    codex_agent_context_t *context,
    codex_agent_conversation_value_t *conversation,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_value_message_at(
    codex_agent_context_t *context,
    codex_agent_conversation_value_t *conversation,
    size_t index,
    codex_agent_message_t **out_message);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_request_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *prompt,
    int32_t has_client_message_id,
    const codex_agent_string_view_t *client_message_id,
    int32_t has_model,
    const codex_agent_string_view_t *model,
    int32_t has_effort,
    const codex_agent_string_view_t *effort,
    int32_t has_service_tier,
    const codex_agent_string_view_t *service_tier,
    codex_agent_approval_preset_t approval_preset,
    const codex_agent_capability_t *capabilities,
    size_t capability_count,
    codex_agent_invocation_t *const *invocations,
    size_t invocation_count,
    codex_agent_collaboration_mode_t collaboration_mode,
    codex_agent_turn_request_t **out_request);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_request_destroy(
    codex_agent_context_t *context,
    codex_agent_turn_request_t **request);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_request_prompt_copy(
    codex_agent_context_t *context,
    codex_agent_turn_request_t *request,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_turn_request_has_client_message_id(
    codex_agent_context_t *context,
    codex_agent_turn_request_t *request,
    int32_t *out_has_client_message_id);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_turn_request_client_message_id_copy(
    codex_agent_context_t *context,
    codex_agent_turn_request_t *request,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_request_has_model(
    codex_agent_context_t *context,
    codex_agent_turn_request_t *request,
    int32_t *out_has_model);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_request_model_copy(
    codex_agent_context_t *context,
    codex_agent_turn_request_t *request,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_request_has_effort(
    codex_agent_context_t *context,
    codex_agent_turn_request_t *request,
    int32_t *out_has_effort);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_request_effort_copy(
    codex_agent_context_t *context,
    codex_agent_turn_request_t *request,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_turn_request_has_service_tier(
    codex_agent_context_t *context,
    codex_agent_turn_request_t *request,
    int32_t *out_has_service_tier);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_turn_request_service_tier_copy(
    codex_agent_context_t *context,
    codex_agent_turn_request_t *request,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_turn_request_approval_preset(
    codex_agent_context_t *context,
    codex_agent_turn_request_t *request,
    codex_agent_approval_preset_t *out_preset);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_turn_request_capabilities_count(
    codex_agent_context_t *context,
    codex_agent_turn_request_t *request,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_turn_request_has_capability(
    codex_agent_context_t *context,
    codex_agent_turn_request_t *request,
    codex_agent_capability_t capability,
    int32_t *out_has_capability);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_turn_request_invocations_count(
    codex_agent_context_t *context,
    codex_agent_turn_request_t *request,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_turn_request_invocation_at(
    codex_agent_context_t *context,
    codex_agent_turn_request_t *request,
    size_t index,
    codex_agent_invocation_t **out_invocation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_turn_request_collaboration_mode(
    codex_agent_context_t *context,
    codex_agent_turn_request_t *request,
    codex_agent_collaboration_mode_t *out_mode);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_state_create(
    codex_agent_context_t *context,
    codex_agent_conversation_status_t status,
    int32_t has_conversation_id,
    codex_agent_conversation_id_t *conversation_id,
    int32_t has_conversation,
    codex_agent_conversation_value_t *conversation,
    codex_agent_turn_progress_t *turn_progress,
    int32_t has_model,
    const codex_agent_string_view_t *model,
    int32_t has_effort,
    const codex_agent_string_view_t *effort,
    int32_t has_service_tier,
    const codex_agent_string_view_t *service_tier,
    int32_t has_failure,
    codex_agent_failure_t *failure,
    codex_agent_snapshot_t **out_state);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_state_has_conversation_id(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *state,
    int32_t *out_has_conversation_id);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_state_conversation_id(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *state,
    codex_agent_conversation_id_t **out_conversation_id);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_state_has_conversation(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *state,
    int32_t *out_has_conversation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_state_conversation(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *state,
    codex_agent_conversation_value_t **out_conversation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_state_turn_progress(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *state,
    codex_agent_turn_progress_t **out_progress);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_state_has_model(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *state,
    int32_t *out_has_model);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_state_model_copy(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *state,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_state_has_effort(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *state,
    int32_t *out_has_effort);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_state_effort_copy(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *state,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_state_has_service_tier(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *state,
    int32_t *out_has_service_tier);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_state_service_tier_copy(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *state,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_state_can_start_turn(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *state,
    int32_t *out_can_start);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_state_can_reload(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *state,
    int32_t *out_can_reload);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_state_can_cancel_turn(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *state,
    int32_t *out_can_cancel);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_value_from_boolean(
    codex_agent_context_t *context,
    codex_agent_form_boolean_value_t *boolean_value,
    codex_agent_form_value_t **out_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_value_from_number(
    codex_agent_context_t *context,
    codex_agent_form_number_value_t *number_value,
    codex_agent_form_value_t **out_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_value_from_text(
    codex_agent_context_t *context,
    codex_agent_form_text_value_t *text_value,
    codex_agent_form_value_t **out_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_form_value_from_text_list(
    codex_agent_context_t *context,
    codex_agent_form_text_list_value_t *text_list_value,
    codex_agent_form_value_t **out_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_value_destroy(
    codex_agent_context_t *context,
    codex_agent_form_value_t **value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_value_kind(
    codex_agent_context_t *context,
    codex_agent_form_value_t *value,
    codex_agent_form_value_kind_t *out_kind);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_value_boolean(
    codex_agent_context_t *context,
    codex_agent_form_value_t *value,
    codex_agent_form_boolean_value_t **out_boolean_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_value_number(
    codex_agent_context_t *context,
    codex_agent_form_value_t *value,
    codex_agent_form_number_value_t **out_number_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_value_text(
    codex_agent_context_t *context,
    codex_agent_form_value_t *value,
    codex_agent_form_text_value_t **out_text_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_value_text_list(
    codex_agent_context_t *context,
    codex_agent_form_value_t *value,
    codex_agent_form_text_list_value_t **out_text_list_value);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_field_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *name,
    const codex_agent_string_view_t *title,
    int32_t has_description,
    const codex_agent_string_view_t *description,
    int32_t is_required,
    codex_agent_form_field_type_t type,
    codex_agent_form_option_t *const *options,
    size_t option_count,
    int32_t has_default_value,
    codex_agent_form_value_t *default_value,
    int32_t has_minimum,
    double minimum,
    int32_t has_maximum,
    double maximum,
    int32_t has_format,
    codex_agent_form_string_format_t format,
    int32_t has_minimum_length,
    int64_t minimum_length,
    int32_t has_maximum_length,
    int64_t maximum_length,
    int32_t has_minimum_selections,
    int64_t minimum_selections,
    int32_t has_maximum_selections,
    int64_t maximum_selections,
    int32_t allows_other,
    int32_t is_secret,
    codex_agent_form_field_t **out_field);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_field_destroy(
    codex_agent_context_t *context,
    codex_agent_form_field_t **field);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_field_name_copy(
    codex_agent_context_t *context,
    codex_agent_form_field_t *field,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_field_title_copy(
    codex_agent_context_t *context,
    codex_agent_form_field_t *field,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_form_field_has_description(
    codex_agent_context_t *context,
    codex_agent_form_field_t *field,
    int32_t *out_has_description);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_field_description_copy(
    codex_agent_context_t *context,
    codex_agent_form_field_t *field,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_field_is_required(
    codex_agent_context_t *context,
    codex_agent_form_field_t *field,
    int32_t *out_is_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_field_type(
    codex_agent_context_t *context,
    codex_agent_form_field_t *field,
    codex_agent_form_field_type_t *out_type);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_field_options_count(
    codex_agent_context_t *context,
    codex_agent_form_field_t *field,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_field_option_at(
    codex_agent_context_t *context,
    codex_agent_form_field_t *field,
    size_t index,
    codex_agent_form_option_t **out_option);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_form_field_has_default_value(
    codex_agent_context_t *context,
    codex_agent_form_field_t *field,
    int32_t *out_has_default_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_field_default_value(
    codex_agent_context_t *context,
    codex_agent_form_field_t *field,
    codex_agent_form_value_t **out_default_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_field_minimum(
    codex_agent_context_t *context,
    codex_agent_form_field_t *field,
    int32_t *out_has_minimum,
    double *out_minimum);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_field_maximum(
    codex_agent_context_t *context,
    codex_agent_form_field_t *field,
    int32_t *out_has_maximum,
    double *out_maximum);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_field_format(
    codex_agent_context_t *context,
    codex_agent_form_field_t *field,
    int32_t *out_has_format,
    codex_agent_form_string_format_t *out_format);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_field_minimum_length(
    codex_agent_context_t *context,
    codex_agent_form_field_t *field,
    int32_t *out_has_value,
    int64_t *out_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_field_maximum_length(
    codex_agent_context_t *context,
    codex_agent_form_field_t *field,
    int32_t *out_has_value,
    int64_t *out_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_form_field_minimum_selections(
    codex_agent_context_t *context,
    codex_agent_form_field_t *field,
    int32_t *out_has_value,
    int64_t *out_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_form_field_maximum_selections(
    codex_agent_context_t *context,
    codex_agent_form_field_t *field,
    int32_t *out_has_value,
    int64_t *out_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_field_allows_other(
    codex_agent_context_t *context,
    codex_agent_form_field_t *field,
    int32_t *out_allows_other);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_field_is_secret(
    codex_agent_context_t *context,
    codex_agent_form_field_t *field,
    int32_t *out_is_secret);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *request_id,
    const codex_agent_string_view_t *server_name,
    codex_agent_conversation_id_t *conversation_id,
    const codex_agent_string_view_t *message,
    int32_t has_form,
    codex_agent_form_field_t *const *form,
    size_t form_count,
    int32_t has_url,
    const codex_agent_string_view_t *url,
    codex_agent_elicitation_t **out_elicitation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_destroy(
    codex_agent_context_t *context,
    codex_agent_elicitation_t **elicitation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_request_id_copy(
    codex_agent_context_t *context,
    codex_agent_elicitation_t *elicitation,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_server_name_copy(
    codex_agent_context_t *context,
    codex_agent_elicitation_t *elicitation,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_elicitation_conversation_id(
    codex_agent_context_t *context,
    codex_agent_elicitation_t *elicitation,
    codex_agent_conversation_id_t **out_conversation_id);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_message_copy(
    codex_agent_context_t *context,
    codex_agent_elicitation_t *elicitation,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_has_form(
    codex_agent_context_t *context,
    codex_agent_elicitation_t *elicitation,
    int32_t *out_has_form);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_form_count(
    codex_agent_context_t *context,
    codex_agent_elicitation_t *elicitation,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_form_at(
    codex_agent_context_t *context,
    codex_agent_elicitation_t *elicitation,
    size_t index,
    codex_agent_form_field_t **out_field);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_has_url(
    codex_agent_context_t *context,
    codex_agent_elicitation_t *elicitation,
    int32_t *out_has_url);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_url_copy(
    codex_agent_context_t *context,
    codex_agent_elicitation_t *elicitation,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_response_create(
    codex_agent_context_t *context,
    codex_agent_elicitation_action_t action,
    const codex_agent_string_view_t *content_keys,
    codex_agent_form_value_t *const *content_values,
    size_t content_count,
    codex_agent_elicitation_response_t **out_response);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_elicitation_response_destroy(
    codex_agent_context_t *context,
    codex_agent_elicitation_response_t **response);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_elicitation_response_action(
    codex_agent_context_t *context,
    codex_agent_elicitation_response_t *response,
    codex_agent_elicitation_action_t *out_action);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_elicitation_response_content_count(
    codex_agent_context_t *context,
    codex_agent_elicitation_response_t *response,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_elicitation_response_content_value(
    codex_agent_context_t *context,
    codex_agent_elicitation_response_t *response,
    const codex_agent_string_view_t *key,
    codex_agent_form_value_t **out_value);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_pending_elicitation_create(
    codex_agent_context_t *context,
    codex_agent_elicitation_t *elicitation,
    codex_agent_pending_elicitation_t **out_pending_elicitation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_pending_elicitation_destroy(
    codex_agent_context_t *context,
    codex_agent_pending_elicitation_t **pending_elicitation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_pending_elicitation_elicitation(
    codex_agent_context_t *context,
    codex_agent_pending_elicitation_t *pending_elicitation,
    codex_agent_elicitation_t **out_elicitation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_pending_elicitation_request_id_copy(
    codex_agent_context_t *context,
    codex_agent_pending_elicitation_t *pending_elicitation,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_pending_elicitation_conversation_id(
    codex_agent_context_t *context,
    codex_agent_pending_elicitation_t *pending_elicitation,
    codex_agent_conversation_id_t **out_conversation_id);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_pending_interaction_from_approval(
    codex_agent_context_t *context,
    codex_agent_pending_approval_t *approval,
    codex_agent_pending_interaction_t **out_interaction);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_pending_interaction_from_elicitation(
    codex_agent_context_t *context,
    codex_agent_pending_elicitation_t *pending_elicitation,
    codex_agent_pending_interaction_t **out_interaction);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_pending_interaction_destroy(
    codex_agent_context_t *context,
    codex_agent_pending_interaction_t **interaction);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_pending_interaction_kind(
    codex_agent_context_t *context,
    codex_agent_pending_interaction_t *interaction,
    codex_agent_pending_interaction_kind_t *out_kind);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_pending_interaction_approval(
    codex_agent_context_t *context,
    codex_agent_pending_interaction_t *interaction,
    codex_agent_pending_approval_t **out_approval);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_pending_interaction_elicitation(
    codex_agent_context_t *context,
    codex_agent_pending_interaction_t *interaction,
    codex_agent_pending_elicitation_t **out_elicitation);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_interaction_state_create(
    codex_agent_context_t *context,
    codex_agent_pending_interaction_t *const *pending,
    size_t pending_count,
    const codex_agent_string_view_t *resolving_request_ids,
    size_t resolving_request_id_count,
    int32_t has_failure,
    codex_agent_failure_t *failure,
    codex_agent_interaction_state_t **out_state);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_interaction_state_destroy(
    codex_agent_context_t *context,
    codex_agent_interaction_state_t **state);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_interaction_state_pending_count(
    codex_agent_context_t *context,
    codex_agent_interaction_state_t *state,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_interaction_state_pending_at(
    codex_agent_context_t *context,
    codex_agent_interaction_state_t *state,
    size_t index,
    codex_agent_pending_interaction_t **out_interaction);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_interaction_state_resolving_request_ids_count(
    codex_agent_context_t *context,
    codex_agent_interaction_state_t *state,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_interaction_state_resolving_request_ids_contains(
    codex_agent_context_t *context,
    codex_agent_interaction_state_t *state,
    const codex_agent_string_view_t *request_id,
    int32_t *out_contains);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_interaction_state_has_failure(
    codex_agent_context_t *context,
    codex_agent_interaction_state_t *state,
    int32_t *out_has_failure);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_interaction_state_failure(
    codex_agent_context_t *context,
    codex_agent_interaction_state_t *state,
    codex_agent_failure_t **out_failure);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_hook_handler_from_agent(
    codex_agent_context_t *context,
    codex_agent_hook_handler_agent_t *agent,
    codex_agent_hook_handler_t **out_handler);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_hook_handler_from_command(
    codex_agent_context_t *context,
    codex_agent_hook_handler_command_t *command,
    codex_agent_hook_handler_t **out_handler);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_hook_handler_from_mcp_tool(
    codex_agent_context_t *context,
    codex_agent_hook_handler_mcp_tool_t *mcp_tool,
    codex_agent_hook_handler_t **out_handler);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_hook_handler_from_prompt(
    codex_agent_context_t *context,
    codex_agent_hook_handler_prompt_t *prompt,
    codex_agent_hook_handler_t **out_handler);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_handler_destroy(
    codex_agent_context_t *context,
    codex_agent_hook_handler_t **handler);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_handler_kind(
    codex_agent_context_t *context,
    codex_agent_hook_handler_t *handler,
    codex_agent_hook_handler_kind_t *out_kind);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_handler_agent(
    codex_agent_context_t *context,
    codex_agent_hook_handler_t *handler,
    codex_agent_hook_handler_agent_t **out_agent);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_handler_command(
    codex_agent_context_t *context,
    codex_agent_hook_handler_t *handler,
    codex_agent_hook_handler_command_t **out_command);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_handler_mcp_tool(
    codex_agent_context_t *context,
    codex_agent_hook_handler_t *handler,
    codex_agent_hook_handler_mcp_tool_t **out_mcp_tool);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_handler_prompt(
    codex_agent_context_t *context,
    codex_agent_hook_handler_t *handler,
    codex_agent_hook_handler_prompt_t **out_prompt);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *key,
    const codex_agent_string_view_t *current_hash,
    int32_t is_enabled,
    const codex_agent_string_view_t *event_name,
    codex_agent_hook_handler_t *handler,
    int32_t is_managed,
    const codex_agent_string_view_t *source,
    const codex_agent_string_view_t *source_path,
    int64_t timeout_seconds,
    codex_agent_hook_trust_status_t trust_status,
    int32_t has_matcher,
    const codex_agent_string_view_t *matcher,
    int32_t has_plugin_id,
    const codex_agent_string_view_t *plugin_id,
    int32_t has_status_message,
    const codex_agent_string_view_t *status_message,
    int32_t has_origin,
    codex_agent_resource_origin_t origin,
    int32_t can_uninstall,
    codex_agent_hook_t **out_hook);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_destroy(
    codex_agent_context_t *context,
    codex_agent_hook_t **hook);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_key_copy(
    codex_agent_context_t *context,
    codex_agent_hook_t *hook,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_current_hash_copy(
    codex_agent_context_t *context,
    codex_agent_hook_t *hook,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_is_enabled(
    codex_agent_context_t *context,
    codex_agent_hook_t *hook,
    int32_t *out_is_enabled);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_event_name_copy(
    codex_agent_context_t *context,
    codex_agent_hook_t *hook,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_handler(
    codex_agent_context_t *context,
    codex_agent_hook_t *hook,
    codex_agent_hook_handler_t **out_handler);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_is_managed(
    codex_agent_context_t *context,
    codex_agent_hook_t *hook,
    int32_t *out_is_managed);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_source_copy(
    codex_agent_context_t *context,
    codex_agent_hook_t *hook,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_source_path_copy(
    codex_agent_context_t *context,
    codex_agent_hook_t *hook,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_timeout_seconds(
    codex_agent_context_t *context,
    codex_agent_hook_t *hook,
    int64_t *out_timeout_seconds);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_trust_status(
    codex_agent_context_t *context,
    codex_agent_hook_t *hook,
    codex_agent_hook_trust_status_t *out_trust_status);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_has_matcher(
    codex_agent_context_t *context,
    codex_agent_hook_t *hook,
    int32_t *out_has_matcher);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_matcher_copy(
    codex_agent_context_t *context,
    codex_agent_hook_t *hook,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_has_plugin_id(
    codex_agent_context_t *context,
    codex_agent_hook_t *hook,
    int32_t *out_has_plugin_id);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_plugin_id_copy(
    codex_agent_context_t *context,
    codex_agent_hook_t *hook,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_has_status_message(
    codex_agent_context_t *context,
    codex_agent_hook_t *hook,
    int32_t *out_has_status_message);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_status_message_copy(
    codex_agent_context_t *context,
    codex_agent_hook_t *hook,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_origin(
    codex_agent_context_t *context,
    codex_agent_hook_t *hook,
    codex_agent_resource_origin_t *out_origin);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_can_uninstall(
    codex_agent_context_t *context,
    codex_agent_hook_t *hook,
    int32_t *out_can_uninstall);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_can_trust(
    codex_agent_context_t *context,
    codex_agent_hook_t *hook,
    int32_t *out_can_trust);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_catalog_create(
    codex_agent_context_t *context,
    codex_agent_hook_t *const *hooks,
    size_t hook_count,
    const codex_agent_string_view_t *warnings,
    size_t warning_count,
    const codex_agent_string_view_t *errors,
    size_t error_count,
    codex_agent_hook_catalog_t **out_catalog);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_catalog_destroy(
    codex_agent_context_t *context,
    codex_agent_hook_catalog_t **catalog);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_catalog_hooks_count(
    codex_agent_context_t *context,
    codex_agent_hook_catalog_t *catalog,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_catalog_hooks_at(
    codex_agent_context_t *context,
    codex_agent_hook_catalog_t *catalog,
    size_t index,
    codex_agent_hook_t **out_hook);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_hook_catalog_warnings_count(
    codex_agent_context_t *context,
    codex_agent_hook_catalog_t *catalog,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_hook_catalog_warnings_copy_at(
    codex_agent_context_t *context,
    codex_agent_hook_catalog_t *catalog,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_hook_catalog_errors_count(
    codex_agent_context_t *context,
    codex_agent_hook_catalog_t *catalog,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_hook_catalog_errors_copy_at(
    codex_agent_context_t *context,
    codex_agent_hook_catalog_t *catalog,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_integration_from_connector(
    codex_agent_context_t *context,
    codex_agent_integration_connector_t *connector,
    codex_agent_integration_t **out_integration);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_integration_from_mcp_server(
    codex_agent_context_t *context,
    codex_agent_integration_mcp_server_t *server,
    codex_agent_integration_t **out_integration);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_integration_destroy(
    codex_agent_context_t *context,
    codex_agent_integration_t **integration);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_integration_kind(
    codex_agent_context_t *context,
    codex_agent_integration_t *integration,
    codex_agent_integration_kind_t *out_kind);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_integration_connector(
    codex_agent_context_t *context,
    codex_agent_integration_t *integration,
    codex_agent_integration_connector_t **out_connector);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_integration_mcp_server(
    codex_agent_context_t *context,
    codex_agent_integration_t *integration,
    codex_agent_integration_mcp_server_t **out_server);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_integration_authorization_state_create(
    codex_agent_context_t *context,
    codex_agent_integration_authorization_status_t status,
    codex_agent_integration_t *target,
    codex_agent_failure_t *failure,
    codex_agent_integration_authorization_state_t **out_state);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_integration_authorization_state_destroy(
    codex_agent_context_t *context,
    codex_agent_integration_authorization_state_t **state);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_integration_authorization_state_status(
    codex_agent_context_t *context,
    codex_agent_integration_authorization_state_t *state,
    codex_agent_integration_authorization_status_t *out_status);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_integration_authorization_state_target(
    codex_agent_context_t *context,
    codex_agent_integration_authorization_state_t *state,
    codex_agent_integration_t **out_target);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_integration_authorization_state_failure(
    codex_agent_context_t *context,
    codex_agent_integration_authorization_state_t *state,
    codex_agent_failure_t **out_failure);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_authentication_state_create(
    codex_agent_context_t *context,
    codex_agent_authentication_status_t status,
    int32_t has_pending_sign_in_url,
    codex_agent_authorization_url_t *pending_sign_in_url,
    int32_t has_device_verification_url,
    codex_agent_authorization_url_t *device_verification_url,
    int32_t has_device_user_code,
    const codex_agent_string_view_t *device_user_code,
    int32_t has_failure,
    codex_agent_failure_t *failure,
    codex_agent_authentication_state_t **out_state);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_authentication_state_destroy(
    codex_agent_context_t *context,
    codex_agent_authentication_state_t **state);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_authentication_state_status(
    codex_agent_context_t *context,
    codex_agent_authentication_state_t *state,
    codex_agent_authentication_status_t *out_status);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_authentication_state_has_pending_sign_in_url(
    codex_agent_context_t *context,
    codex_agent_authentication_state_t *state,
    int32_t *out_has_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_authentication_state_pending_sign_in_url(
    codex_agent_context_t *context,
    codex_agent_authentication_state_t *state,
    codex_agent_authorization_url_t **out_url);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_authentication_state_has_device_verification_url(
    codex_agent_context_t *context,
    codex_agent_authentication_state_t *state,
    int32_t *out_has_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_authentication_state_device_verification_url(
    codex_agent_context_t *context,
    codex_agent_authentication_state_t *state,
    codex_agent_authorization_url_t **out_url);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_authentication_state_has_device_user_code(
    codex_agent_context_t *context,
    codex_agent_authentication_state_t *state,
    int32_t *out_has_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_authentication_state_device_user_code_copy(
    codex_agent_context_t *context,
    codex_agent_authentication_state_t *state,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_authentication_state_has_failure(
    codex_agent_context_t *context,
    codex_agent_authentication_state_t *state,
    int32_t *out_has_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_authentication_state_failure(
    codex_agent_context_t *context,
    codex_agent_authentication_state_t *state,
    codex_agent_failure_t **out_failure);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_settings_create(
    codex_agent_context_t *context,
    codex_agent_approval_preset_t approval_preset,
    int32_t has_service_tier,
    const codex_agent_string_view_t *service_tier,
    codex_agent_conversation_settings_t **out_settings);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_settings_destroy(
    codex_agent_context_t *context,
    codex_agent_conversation_settings_t **settings);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_settings_approval_preset(
    codex_agent_context_t *context,
    codex_agent_conversation_settings_t *settings,
    codex_agent_approval_preset_t *out_approval_preset);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_settings_has_service_tier(
    codex_agent_context_t *context,
    codex_agent_conversation_settings_t *settings,
    int32_t *out_has_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_settings_service_tier_copy(
    codex_agent_context_t *context,
    codex_agent_conversation_settings_t *settings,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_authorization_url_chat_gpt(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *value,
    codex_agent_authorization_url_t **out_url);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_authorization_url_external(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *value,
    codex_agent_authorization_url_t **out_url);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_authorization_url_destroy(
    codex_agent_context_t *context,
    codex_agent_authorization_url_t **url);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_authorization_url_value_copy(
    codex_agent_context_t *context,
    codex_agent_authorization_url_t *url,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_authorization_url_purpose(
    codex_agent_context_t *context,
    codex_agent_authorization_url_t *url,
    codex_agent_authorization_purpose_t *out_purpose);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_client_info_value_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *name,
    const codex_agent_string_view_t *title,
    const codex_agent_string_view_t *version,
    codex_agent_client_info_value_t **out_client_info);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_client_info_value_destroy(
    codex_agent_context_t *context,
    codex_agent_client_info_value_t **client_info);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_client_info_value_name_copy(
    codex_agent_context_t *context,
    codex_agent_client_info_value_t *client_info,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_client_info_value_title_copy(
    codex_agent_context_t *context,
    codex_agent_client_info_value_t *client_info,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_client_info_value_version_copy(
    codex_agent_context_t *context,
    codex_agent_client_info_value_t *client_info,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_content_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *keys,
    codex_agent_form_value_t *const *values,
    size_t count,
    codex_agent_form_content_t **out_content);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_content_destroy(
    codex_agent_context_t *context,
    codex_agent_form_content_t **content);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_content_count(
    codex_agent_context_t *context,
    codex_agent_form_content_t *content,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_content_key_copy(
    codex_agent_context_t *context,
    codex_agent_form_content_t *content,
    size_t index,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_content_value_at(
    codex_agent_context_t *context,
    codex_agent_form_content_t *content,
    const codex_agent_string_view_t *key,
    codex_agent_form_value_t **out_value);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_form_field_accepts(
    codex_agent_context_t *context,
    codex_agent_form_field_t *field,
    codex_agent_form_value_t *value,
    int32_t *out_accepts);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_initial_values(
    codex_agent_context_t *context,
    codex_agent_elicitation_t *elicitation,
    codex_agent_form_content_t **out_content);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_validate(
    codex_agent_context_t *context,
    codex_agent_elicitation_t *elicitation,
    codex_agent_form_content_t *content,
    codex_agent_elicitation_validation_t **out_validation);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_accept(
    codex_agent_context_t *context,
    codex_agent_elicitation_t *elicitation,
    codex_agent_form_content_t *content,
    codex_agent_elicitation_response_t **out_response);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_elicitation_accepts(
    codex_agent_context_t *context,
    codex_agent_elicitation_t *elicitation,
    codex_agent_elicitation_response_t *response,
    int32_t *out_accepts);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_elicitation_response_decline(
    codex_agent_context_t *context,
    codex_agent_elicitation_response_t **out_response);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_elicitation_response_cancel(
    codex_agent_context_t *context,
    codex_agent_elicitation_response_t **out_response);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_name_copy(
    codex_agent_context_t *context,
    codex_agent_invocation_t *invocation,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_key_copy(
    codex_agent_context_t *context,
    codex_agent_invocation_t *invocation,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_pending_interaction_request_id_copy(
    codex_agent_context_t *context,
    codex_agent_pending_interaction_t *interaction,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_pending_interaction_conversation_id(
    codex_agent_context_t *context,
    codex_agent_pending_interaction_t *interaction,
    codex_agent_conversation_id_t **out_conversation_id);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_integration_id_copy(
    codex_agent_context_t *context,
    codex_agent_integration_t *integration,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_integration_display_name_copy(
    codex_agent_context_t *context,
    codex_agent_integration_t *integration,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_host_state_failed_workspace(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *state,
    codex_agent_workspace_t **out_workspace);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_host_state_preparing_workspace(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *state,
    codex_agent_workspace_t **out_workspace);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_host_state_workspace_required_requirement(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *state,
    codex_agent_workspace_selection_required_t **out_requirement);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_interaction_state_pending_for(
    codex_agent_context_t *context,
    codex_agent_interaction_state_t *state,
    codex_agent_conversation_id_t *conversation_id,
    codex_agent_pending_interaction_list_t **out_pending);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_pending_interaction_list_destroy(
    codex_agent_context_t *context,
    codex_agent_pending_interaction_list_t **pending);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_pending_interaction_list_count(
    codex_agent_context_t *context,
    codex_agent_pending_interaction_list_t *pending,
    size_t *out_count);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_pending_interaction_list_at(
    codex_agent_context_t *context,
    codex_agent_pending_interaction_list_t *pending,
    size_t index,
    codex_agent_pending_interaction_t **out_interaction);

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_failure_retain(
    codex_agent_context_t *context,
    codex_agent_failure_t *failure,
    codex_agent_failure_t **out_failure);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_failure_release(
    codex_agent_context_t *context,
    codex_agent_failure_t **failure);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_failure_code_copy(
    codex_agent_context_t *context,
    codex_agent_failure_t *failure,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_failure_message_copy(
    codex_agent_context_t *context,
    codex_agent_failure_t *failure,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required);
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_failure_is_recoverable(
    codex_agent_context_t *context,
    codex_agent_failure_t *failure,
    int32_t *out_is_recoverable);

#ifdef __cplusplus
}
#endif

#endif
