#include "codex_agent.h"

#include <type_traits>

static_assert(CODEX_AGENT_ABI_VERSION_MAJOR == UINT32_C(1));
static_assert(CODEX_AGENT_ABI_VERSION_MINOR == UINT32_C(9));
static_assert(CODEX_AGENT_ABI_VERSION_PATCH == UINT32_C(0));
static_assert(CODEX_AGENT_ABI_VERSION_CURRENT == UINT32_C(0x01090000));
static_assert(CODEX_AGENT_ABI_VERSION_MINIMUM_COMPATIBLE == UINT32_C(0x01000000));
static_assert(CODEX_AGENT_ABI_VERSION_ENCODE(1, 9, 0) == CODEX_AGENT_ABI_VERSION_CURRENT);

static_assert(std::is_same_v<codex_agent_status_t, int32_t>);
static_assert(CODEX_AGENT_STATUS_OK == INT32_C(0));
static_assert(CODEX_AGENT_STATUS_INVALID_ARGUMENT == INT32_C(1));
static_assert(CODEX_AGENT_STATUS_OUT_OF_MEMORY == INT32_C(2));
static_assert(CODEX_AGENT_STATUS_STALE_HANDLE == INT32_C(3));
static_assert(CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE == INT32_C(4));
static_assert(CODEX_AGENT_STATUS_WRONG_CONTEXT == INT32_C(5));
static_assert(CODEX_AGENT_STATUS_BUSY == INT32_C(6));
static_assert(CODEX_AGENT_STATUS_CANCELLED == INT32_C(7));
static_assert(CODEX_AGENT_STATUS_INTERNAL_ERROR == INT32_C(8));
static_assert(CODEX_AGENT_STATUS_BUFFER_TOO_SMALL == INT32_C(9));
static_assert(CODEX_AGENT_STATUS_UNSUPPORTED_ABI == INT32_C(10));
static_assert(CODEX_AGENT_STATUS_CLOSED == INT32_C(11));
static_assert(CODEX_AGENT_STATUS_WOULD_DEADLOCK == INT32_C(12));
static_assert(CODEX_AGENT_STATUS_NOT_READY == INT32_C(13));
static_assert(CODEX_AGENT_STATUS_OPERATION_FAILED == INT32_C(14));

static_assert(std::is_class_v<codex_agent_context_t>);
static_assert(std::is_class_v<codex_agent_host_t>);
static_assert(std::is_class_v<codex_agent_agent_t>);
static_assert(std::is_class_v<codex_agent_conversations_t>);
static_assert(std::is_class_v<codex_agent_conversation_t>);
static_assert(std::is_class_v<codex_agent_operation_t>);
static_assert(std::is_class_v<codex_agent_subscription_t>);
static_assert(std::is_class_v<codex_agent_snapshot_t>);
static_assert(std::is_class_v<codex_agent_failure_t>);

static_assert(std::is_same_v<codex_agent_host_state_kind_t, int32_t>);
static_assert(CODEX_AGENT_HOST_STATE_NEW == INT32_C(0));
static_assert(CODEX_AGENT_HOST_STATE_RESTORING == INT32_C(1));
static_assert(CODEX_AGENT_HOST_STATE_WORKSPACE_REQUIRED == INT32_C(2));
static_assert(CODEX_AGENT_HOST_STATE_PREPARING == INT32_C(3));
static_assert(CODEX_AGENT_HOST_STATE_READY == INT32_C(4));
static_assert(CODEX_AGENT_HOST_STATE_FAILED == INT32_C(5));
static_assert(CODEX_AGENT_HOST_STATE_CLOSED == INT32_C(6));

static_assert(std::is_same_v<codex_agent_workspace_selection_reason_t, int32_t>);
static_assert(CODEX_AGENT_WORKSPACE_REASON_NOT_SELECTED == INT32_C(0));
static_assert(CODEX_AGENT_WORKSPACE_REASON_NOT_FOUND == INT32_C(1));
static_assert(CODEX_AGENT_WORKSPACE_REASON_ACCESS_REVOKED == INT32_C(2));
static_assert(CODEX_AGENT_WORKSPACE_REASON_INVALID_SELECTION == INT32_C(3));

static_assert(std::is_same_v<codex_agent_conversation_status_t, int32_t>);
static_assert(CODEX_AGENT_CONVERSATION_STATUS_NEW == INT32_C(0));
static_assert(CODEX_AGENT_CONVERSATION_STATUS_OPENING == INT32_C(1));
static_assert(CODEX_AGENT_CONVERSATION_STATUS_READY == INT32_C(2));
static_assert(CODEX_AGENT_CONVERSATION_STATUS_STARTING_TURN == INT32_C(3));
static_assert(CODEX_AGENT_CONVERSATION_STATUS_RUNNING_TURN == INT32_C(4));
static_assert(CODEX_AGENT_CONVERSATION_STATUS_CANCELLING_TURN == INT32_C(5));
static_assert(CODEX_AGENT_CONVERSATION_STATUS_RELOADING == INT32_C(6));
static_assert(CODEX_AGENT_CONVERSATION_STATUS_FAILED == INT32_C(7));
static_assert(CODEX_AGENT_CONVERSATION_STATUS_CLOSED == INT32_C(8));

static_assert(std::is_same_v<codex_agent_approval_preset_t, int32_t>);
static_assert(CODEX_AGENT_APPROVAL_PRESET_NEVER == INT32_C(0));
static_assert(CODEX_AGENT_APPROVAL_PRESET_AUTO_REVIEW == INT32_C(1));
static_assert(CODEX_AGENT_APPROVAL_PRESET_ASK_ME == INT32_C(2));
static_assert(CODEX_AGENT_APPROVAL_PRESET_STRICT == INT32_C(3));

static_assert(std::is_same_v<
    decltype(codex_agent_string_view_t::data),
    const uint8_t *>);
static_assert(std::is_same_v<decltype(codex_agent_string_view_t::size), size_t>);

static_assert(std::is_same_v<decltype(codex_agent_client_info_t::struct_size), uint32_t>);
static_assert(std::is_same_v<
    decltype(codex_agent_client_info_t::name),
    codex_agent_string_view_t>);
static_assert(std::is_same_v<
    decltype(codex_agent_client_info_t::title),
    codex_agent_string_view_t>);
static_assert(std::is_same_v<
    decltype(codex_agent_client_info_t::version),
    codex_agent_string_view_t>);

static_assert(std::is_same_v<decltype(codex_agent_host_options_t::struct_size), uint32_t>);
static_assert(std::is_same_v<
    decltype(codex_agent_host_options_t::bundle_directory),
    codex_agent_string_view_t>);
static_assert(std::is_same_v<
    decltype(codex_agent_host_options_t::data_directory),
    codex_agent_string_view_t>);
static_assert(std::is_same_v<
    decltype(codex_agent_host_options_t::client_info),
    codex_agent_client_info_t>);

static_assert(std::is_same_v<
    decltype(codex_agent_path_workspace_selection_t::struct_size),
    uint32_t>);
static_assert(std::is_same_v<
    decltype(codex_agent_path_workspace_selection_t::path),
    codex_agent_string_view_t>);

static_assert(std::is_same_v<
    decltype(codex_agent_conversation_open_options_t::struct_size),
    uint32_t>);
static_assert(std::is_same_v<
    decltype(codex_agent_conversation_open_options_t::has_conversation_id),
    int32_t>);
static_assert(std::is_same_v<
    decltype(codex_agent_conversation_open_options_t::conversation_id),
    codex_agent_string_view_t>);
static_assert(std::is_same_v<
    decltype(codex_agent_conversation_open_options_t::has_approval_preset),
    int32_t>);
static_assert(std::is_same_v<
    decltype(codex_agent_conversation_open_options_t::approval_preset),
    codex_agent_approval_preset_t>);
static_assert(std::is_same_v<
    decltype(codex_agent_conversation_open_options_t::has_service_tier),
    int32_t>);
static_assert(std::is_same_v<
    decltype(codex_agent_conversation_open_options_t::service_tier),
    codex_agent_string_view_t>);

using ExpectedOperationCallback = void (CODEX_AGENT_CALL *)(
    codex_agent_context_t *,
    codex_agent_operation_t *,
    void *);
using ExpectedStateCallback = void (CODEX_AGENT_CALL *)(
    codex_agent_context_t *,
    codex_agent_subscription_t *,
    codex_agent_status_t,
    codex_agent_snapshot_t *,
    int32_t,
    void *);
static_assert(std::is_same_v<codex_agent_operation_callback_t, ExpectedOperationCallback>);
static_assert(std::is_same_v<codex_agent_state_callback_t, ExpectedStateCallback>);

using AbiVersionFunction = uint32_t (CODEX_AGENT_CALL *)(void);
using AbiCompatibilityFunction = int32_t (CODEX_AGENT_CALL *)(uint32_t);
using ContextSlotFunction = codex_agent_status_t (CODEX_AGENT_CALL *)(
    codex_agent_context_t **);

template <typename Handle>
using RetainFunction = codex_agent_status_t (CODEX_AGENT_CALL *)(
    codex_agent_context_t *,
    Handle *,
    Handle **);

template <typename Handle>
using ReleaseFunction = codex_agent_status_t (CODEX_AGENT_CALL *)(
    codex_agent_context_t *,
    Handle **);

template <typename Handle>
using OperationFunction = codex_agent_status_t (CODEX_AGENT_CALL *)(
    codex_agent_context_t *,
    Handle *,
    codex_agent_operation_callback_t,
    void *,
    codex_agent_operation_t **);

template <typename Handle>
using SnapshotGetFunction = codex_agent_status_t (CODEX_AGENT_CALL *)(
    codex_agent_context_t *,
    Handle *,
    codex_agent_snapshot_t **);

template <typename Handle>
using StateSubscribeFunction = codex_agent_status_t (CODEX_AGENT_CALL *)(
    codex_agent_context_t *,
    Handle *,
    codex_agent_state_callback_t,
    void *,
    codex_agent_subscription_t **);

using SnapshotFailureFunction = codex_agent_status_t (CODEX_AGENT_CALL *)(
    codex_agent_context_t *,
    codex_agent_snapshot_t *,
    codex_agent_failure_t **);
using SnapshotCopyFunction = codex_agent_status_t (CODEX_AGENT_CALL *)(
    codex_agent_context_t *,
    codex_agent_snapshot_t *,
    uint8_t *,
    size_t,
    size_t *);
using FailureCopyFunction = codex_agent_status_t (CODEX_AGENT_CALL *)(
    codex_agent_context_t *,
    codex_agent_failure_t *,
    uint8_t *,
    size_t,
    size_t *);

#define ASSERT_DECLARATION(name, expected) \
    static_assert(std::is_same_v<decltype(&name), expected>)

ASSERT_DECLARATION(codex_agent_abi_version, AbiVersionFunction);
ASSERT_DECLARATION(codex_agent_abi_is_compatible, AbiCompatibilityFunction);
ASSERT_DECLARATION(codex_agent_context_create, ContextSlotFunction);
ASSERT_DECLARATION(codex_agent_context_destroy, ContextSlotFunction);

ASSERT_DECLARATION(
    codex_agent_host_create,
    codex_agent_status_t (CODEX_AGENT_CALL *)(
        codex_agent_context_t *,
        const codex_agent_host_options_t *,
        codex_agent_host_t **));
ASSERT_DECLARATION(codex_agent_host_retain, RetainFunction<codex_agent_host_t>);
ASSERT_DECLARATION(codex_agent_host_release, ReleaseFunction<codex_agent_host_t>);
ASSERT_DECLARATION(
    codex_agent_host_select_workspace,
    codex_agent_status_t (CODEX_AGENT_CALL *)(
        codex_agent_context_t *,
        codex_agent_host_t *,
        const codex_agent_path_workspace_selection_t *,
        codex_agent_operation_callback_t,
        void *,
        codex_agent_operation_t **));
ASSERT_DECLARATION(codex_agent_host_close, OperationFunction<codex_agent_host_t>);
ASSERT_DECLARATION(codex_agent_host_state_get, SnapshotGetFunction<codex_agent_host_t>);
ASSERT_DECLARATION(
    codex_agent_host_state_subscribe,
    StateSubscribeFunction<codex_agent_host_t>);

ASSERT_DECLARATION(codex_agent_agent_retain, RetainFunction<codex_agent_agent_t>);
ASSERT_DECLARATION(codex_agent_agent_release, ReleaseFunction<codex_agent_agent_t>);
ASSERT_DECLARATION(
    codex_agent_agent_conversations,
    codex_agent_status_t (CODEX_AGENT_CALL *)(
        codex_agent_context_t *,
        codex_agent_agent_t *,
        codex_agent_conversations_t **));

ASSERT_DECLARATION(
    codex_agent_conversations_retain,
    RetainFunction<codex_agent_conversations_t>);
ASSERT_DECLARATION(
    codex_agent_conversations_release,
    ReleaseFunction<codex_agent_conversations_t>);
ASSERT_DECLARATION(
    codex_agent_conversations_active_get,
    SnapshotGetFunction<codex_agent_conversations_t>);
ASSERT_DECLARATION(
    codex_agent_conversations_active_subscribe,
    StateSubscribeFunction<codex_agent_conversations_t>);
ASSERT_DECLARATION(
    codex_agent_conversations_open,
    codex_agent_status_t (CODEX_AGENT_CALL *)(
        codex_agent_context_t *,
        codex_agent_conversations_t *,
        const codex_agent_conversation_open_options_t *,
        codex_agent_operation_callback_t,
        void *,
        codex_agent_operation_t **));

ASSERT_DECLARATION(
    codex_agent_conversation_retain,
    RetainFunction<codex_agent_conversation_t>);
ASSERT_DECLARATION(
    codex_agent_conversation_release,
    ReleaseFunction<codex_agent_conversation_t>);
ASSERT_DECLARATION(
    codex_agent_conversation_is_same,
    codex_agent_status_t (CODEX_AGENT_CALL *)(
        codex_agent_context_t *,
        codex_agent_conversation_t *,
        codex_agent_conversation_t *,
        int32_t *));
ASSERT_DECLARATION(
    codex_agent_conversation_send,
    codex_agent_status_t (CODEX_AGENT_CALL *)(
        codex_agent_context_t *,
        codex_agent_conversation_t *,
        const codex_agent_string_view_t *,
        codex_agent_operation_callback_t,
        void *,
        codex_agent_operation_t **));
ASSERT_DECLARATION(
    codex_agent_conversation_cancel_turn,
    OperationFunction<codex_agent_conversation_t>);
ASSERT_DECLARATION(
    codex_agent_conversation_close,
    OperationFunction<codex_agent_conversation_t>);
ASSERT_DECLARATION(
    codex_agent_conversation_state_get,
    SnapshotGetFunction<codex_agent_conversation_t>);
ASSERT_DECLARATION(
    codex_agent_conversation_state_subscribe,
    StateSubscribeFunction<codex_agent_conversation_t>);

ASSERT_DECLARATION(
    codex_agent_operation_cancel,
    codex_agent_status_t (CODEX_AGENT_CALL *)(
        codex_agent_context_t *,
        codex_agent_operation_t *));
ASSERT_DECLARATION(
    codex_agent_operation_result,
    codex_agent_status_t (CODEX_AGENT_CALL *)(
        codex_agent_context_t *,
        codex_agent_operation_t *,
        codex_agent_status_t *));
ASSERT_DECLARATION(
    codex_agent_operation_conversation,
    codex_agent_status_t (CODEX_AGENT_CALL *)(
        codex_agent_context_t *,
        codex_agent_conversations_t *,
        codex_agent_operation_t *,
        codex_agent_conversation_t **));
ASSERT_DECLARATION(
    codex_agent_operation_failure,
    codex_agent_status_t (CODEX_AGENT_CALL *)(
        codex_agent_context_t *,
        codex_agent_operation_t *,
        codex_agent_failure_t **));
ASSERT_DECLARATION(
    codex_agent_operation_destroy,
    ReleaseFunction<codex_agent_operation_t>);

ASSERT_DECLARATION(
    codex_agent_subscription_destroy,
    ReleaseFunction<codex_agent_subscription_t>);
ASSERT_DECLARATION(codex_agent_snapshot_destroy, ReleaseFunction<codex_agent_snapshot_t>);

ASSERT_DECLARATION(
    codex_agent_host_state_kind,
    codex_agent_status_t (CODEX_AGENT_CALL *)(
        codex_agent_context_t *,
        codex_agent_snapshot_t *,
        codex_agent_host_state_kind_t *));
ASSERT_DECLARATION(
    codex_agent_host_state_agent,
    codex_agent_status_t (CODEX_AGENT_CALL *)(
        codex_agent_context_t *,
        codex_agent_host_t *,
        codex_agent_snapshot_t *,
        codex_agent_agent_t **));
ASSERT_DECLARATION(codex_agent_host_state_failure, SnapshotFailureFunction);
ASSERT_DECLARATION(
    codex_agent_host_state_has_workspace,
    codex_agent_status_t (CODEX_AGENT_CALL *)(
        codex_agent_context_t *,
        codex_agent_snapshot_t *,
        int32_t *));
ASSERT_DECLARATION(codex_agent_host_state_workspace_path_copy, SnapshotCopyFunction);
ASSERT_DECLARATION(
    codex_agent_host_state_workspace_display_name_copy,
    SnapshotCopyFunction);
ASSERT_DECLARATION(
    codex_agent_host_state_requirement_reason,
    codex_agent_status_t (CODEX_AGENT_CALL *)(
        codex_agent_context_t *,
        codex_agent_snapshot_t *,
        codex_agent_workspace_selection_reason_t *));
ASSERT_DECLARATION(
    codex_agent_host_state_requirement_message_copy,
    SnapshotCopyFunction);
ASSERT_DECLARATION(
    codex_agent_active_conversation,
    codex_agent_status_t (CODEX_AGENT_CALL *)(
        codex_agent_context_t *,
        codex_agent_conversations_t *,
        codex_agent_snapshot_t *,
        codex_agent_conversation_t **));
ASSERT_DECLARATION(
    codex_agent_conversation_state_status,
    codex_agent_status_t (CODEX_AGENT_CALL *)(
        codex_agent_context_t *,
        codex_agent_snapshot_t *,
        codex_agent_conversation_status_t *));
ASSERT_DECLARATION(codex_agent_conversation_state_failure, SnapshotFailureFunction);

ASSERT_DECLARATION(codex_agent_failure_retain, RetainFunction<codex_agent_failure_t>);
ASSERT_DECLARATION(codex_agent_failure_release, ReleaseFunction<codex_agent_failure_t>);
ASSERT_DECLARATION(codex_agent_failure_code_copy, FailureCopyFunction);
ASSERT_DECLARATION(codex_agent_failure_message_copy, FailureCopyFunction);
ASSERT_DECLARATION(
    codex_agent_failure_is_recoverable,
    codex_agent_status_t (CODEX_AGENT_CALL *)(
        codex_agent_context_t *,
        codex_agent_failure_t *,
        int32_t *));

#undef ASSERT_DECLARATION
