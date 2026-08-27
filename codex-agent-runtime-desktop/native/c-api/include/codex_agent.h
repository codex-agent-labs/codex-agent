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
#define CODEX_AGENT_ABI_VERSION_MINOR UINT32_C(2)
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
typedef struct codex_agent_elicitation_validation_issue codex_agent_elicitation_validation_issue_t;
typedef struct codex_agent_plan_step codex_agent_plan_step_t;
typedef struct codex_agent_plugin_reference codex_agent_plugin_reference_t;
typedef struct codex_agent_plugin_skill codex_agent_plugin_skill_t;
typedef struct codex_agent_service_tier codex_agent_service_tier_t;
typedef struct codex_agent_skill_chunk codex_agent_skill_chunk_t;

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
 * when its property is absent.
 */

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
