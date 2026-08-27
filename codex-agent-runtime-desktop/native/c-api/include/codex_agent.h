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
#define CODEX_AGENT_ABI_VERSION_MINOR UINT32_C(1)
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
