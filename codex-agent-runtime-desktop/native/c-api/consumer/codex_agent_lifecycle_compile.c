#include "codex_agent.h"

#define CHECK(condition)       \
    do {                       \
        if (!(condition)) {    \
            return __LINE__;   \
        }                      \
    } while (0)

#define DECLARE_FUNCTION_REFERENCE(return_type, variable, function, parameters) \
    return_type (CODEX_AGENT_CALL *volatile variable) parameters = function

#define OBSERVE(variable) ((void)(variable))

_Static_assert(CODEX_AGENT_ABI_VERSION_MAJOR == UINT32_C(1), "ABI major");
_Static_assert(CODEX_AGENT_ABI_VERSION_MINOR == UINT32_C(2), "ABI minor");
_Static_assert(CODEX_AGENT_ABI_VERSION_PATCH == UINT32_C(0), "ABI patch");
_Static_assert(
    CODEX_AGENT_ABI_VERSION_CURRENT == UINT32_C(0x01020000),
    "ABI current");
_Static_assert(
    CODEX_AGENT_ABI_VERSION_MINIMUM_COMPATIBLE == UINT32_C(0x01000000),
    "ABI minimum compatible");

_Static_assert(sizeof(codex_agent_status_t) == sizeof(int32_t), "status width");
_Static_assert(CODEX_AGENT_STATUS_OK == INT32_C(0), "status OK");
_Static_assert(CODEX_AGENT_STATUS_INVALID_ARGUMENT == INT32_C(1), "status invalid argument");
_Static_assert(CODEX_AGENT_STATUS_OUT_OF_MEMORY == INT32_C(2), "status out of memory");
_Static_assert(CODEX_AGENT_STATUS_STALE_HANDLE == INT32_C(3), "status stale handle");
_Static_assert(CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE == INT32_C(4), "status wrong handle type");
_Static_assert(CODEX_AGENT_STATUS_WRONG_CONTEXT == INT32_C(5), "status wrong context");
_Static_assert(CODEX_AGENT_STATUS_BUSY == INT32_C(6), "status busy");
_Static_assert(CODEX_AGENT_STATUS_CANCELLED == INT32_C(7), "status cancelled");
_Static_assert(CODEX_AGENT_STATUS_INTERNAL_ERROR == INT32_C(8), "status internal error");
_Static_assert(CODEX_AGENT_STATUS_BUFFER_TOO_SMALL == INT32_C(9), "status buffer too small");
_Static_assert(CODEX_AGENT_STATUS_UNSUPPORTED_ABI == INT32_C(10), "status unsupported ABI");
_Static_assert(CODEX_AGENT_STATUS_CLOSED == INT32_C(11), "status closed");
_Static_assert(CODEX_AGENT_STATUS_WOULD_DEADLOCK == INT32_C(12), "status would deadlock");
_Static_assert(CODEX_AGENT_STATUS_NOT_READY == INT32_C(13), "status not ready");
_Static_assert(CODEX_AGENT_STATUS_OPERATION_FAILED == INT32_C(14), "status operation failed");

_Static_assert(sizeof(codex_agent_host_state_kind_t) == sizeof(int32_t), "host state width");
_Static_assert(CODEX_AGENT_HOST_STATE_NEW == INT32_C(0), "host state new");
_Static_assert(CODEX_AGENT_HOST_STATE_RESTORING == INT32_C(1), "host state restoring");
_Static_assert(
    CODEX_AGENT_HOST_STATE_WORKSPACE_REQUIRED == INT32_C(2),
    "host state workspace required");
_Static_assert(CODEX_AGENT_HOST_STATE_PREPARING == INT32_C(3), "host state preparing");
_Static_assert(CODEX_AGENT_HOST_STATE_READY == INT32_C(4), "host state ready");
_Static_assert(CODEX_AGENT_HOST_STATE_FAILED == INT32_C(5), "host state failed");
_Static_assert(CODEX_AGENT_HOST_STATE_CLOSED == INT32_C(6), "host state closed");

_Static_assert(
    sizeof(codex_agent_conversation_status_t) == sizeof(int32_t),
    "conversation status width");
_Static_assert(CODEX_AGENT_CONVERSATION_STATUS_NEW == INT32_C(0), "conversation new");
_Static_assert(CODEX_AGENT_CONVERSATION_STATUS_OPENING == INT32_C(1), "conversation opening");
_Static_assert(CODEX_AGENT_CONVERSATION_STATUS_READY == INT32_C(2), "conversation ready");
_Static_assert(
    CODEX_AGENT_CONVERSATION_STATUS_STARTING_TURN == INT32_C(3),
    "conversation starting turn");
_Static_assert(
    CODEX_AGENT_CONVERSATION_STATUS_RUNNING_TURN == INT32_C(4),
    "conversation running turn");
_Static_assert(
    CODEX_AGENT_CONVERSATION_STATUS_CANCELLING_TURN == INT32_C(5),
    "conversation cancelling turn");
_Static_assert(CODEX_AGENT_CONVERSATION_STATUS_RELOADING == INT32_C(6), "conversation reloading");
_Static_assert(CODEX_AGENT_CONVERSATION_STATUS_FAILED == INT32_C(7), "conversation failed");
_Static_assert(CODEX_AGENT_CONVERSATION_STATUS_CLOSED == INT32_C(8), "conversation closed");

_Static_assert(
    sizeof(codex_agent_approval_preset_t) == sizeof(int32_t),
    "approval preset width");
_Static_assert(CODEX_AGENT_APPROVAL_PRESET_NEVER == INT32_C(0), "approval never");
_Static_assert(CODEX_AGENT_APPROVAL_PRESET_AUTO_REVIEW == INT32_C(1), "approval auto review");
_Static_assert(CODEX_AGENT_APPROVAL_PRESET_ASK_ME == INT32_C(2), "approval ask me");
_Static_assert(CODEX_AGENT_APPROVAL_PRESET_STRICT == INT32_C(3), "approval strict");

_Static_assert(sizeof(codex_agent_client_info_t) <= UINT32_MAX, "client info size");
_Static_assert(sizeof(codex_agent_host_options_t) <= UINT32_MAX, "host options size");
_Static_assert(
    sizeof(codex_agent_path_workspace_selection_t) <= UINT32_MAX,
    "workspace selection size");
_Static_assert(
    sizeof(codex_agent_conversation_open_options_t) <= UINT32_MAX,
    "conversation options size");

static void CODEX_AGENT_CALL operation_callback(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    void *user_data) {
    (void)context;
    (void)operation;
    (void)user_data;
}

static void CODEX_AGENT_CALL state_callback(
    codex_agent_context_t *context,
    codex_agent_subscription_t *subscription,
    codex_agent_status_t event_status,
    codex_agent_snapshot_t *snapshot,
    int32_t is_terminal,
    void *user_data) {
    (void)context;
    (void)subscription;
    (void)event_status;
    (void)snapshot;
    (void)is_terminal;
    (void)user_data;
}

static int reference_function_declarations(void) {
    DECLARE_FUNCTION_REFERENCE(
        uint32_t,
        abi_version_fn,
        codex_agent_abi_version,
        (void));
    DECLARE_FUNCTION_REFERENCE(
        int32_t,
        abi_is_compatible_fn,
        codex_agent_abi_is_compatible,
        (uint32_t));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        context_create_fn,
        codex_agent_context_create,
        (codex_agent_context_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        context_destroy_fn,
        codex_agent_context_destroy,
        (codex_agent_context_t **));

    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        host_create_fn,
        codex_agent_host_create,
        (codex_agent_context_t *, const codex_agent_host_options_t *, codex_agent_host_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        host_retain_fn,
        codex_agent_host_retain,
        (codex_agent_context_t *, codex_agent_host_t *, codex_agent_host_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        host_release_fn,
        codex_agent_host_release,
        (codex_agent_context_t *, codex_agent_host_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        host_select_workspace_fn,
        codex_agent_host_select_workspace,
        (codex_agent_context_t *,
         codex_agent_host_t *,
         const codex_agent_path_workspace_selection_t *,
         codex_agent_operation_callback_t,
         void *,
         codex_agent_operation_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        host_close_fn,
        codex_agent_host_close,
        (codex_agent_context_t *,
         codex_agent_host_t *,
         codex_agent_operation_callback_t,
         void *,
         codex_agent_operation_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        host_state_get_fn,
        codex_agent_host_state_get,
        (codex_agent_context_t *, codex_agent_host_t *, codex_agent_snapshot_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        host_state_subscribe_fn,
        codex_agent_host_state_subscribe,
        (codex_agent_context_t *,
         codex_agent_host_t *,
         codex_agent_state_callback_t,
         void *,
         codex_agent_subscription_t **));

    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        agent_retain_fn,
        codex_agent_agent_retain,
        (codex_agent_context_t *, codex_agent_agent_t *, codex_agent_agent_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        agent_release_fn,
        codex_agent_agent_release,
        (codex_agent_context_t *, codex_agent_agent_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        agent_conversations_fn,
        codex_agent_agent_conversations,
        (codex_agent_context_t *, codex_agent_agent_t *, codex_agent_conversations_t **));

    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        conversations_retain_fn,
        codex_agent_conversations_retain,
        (codex_agent_context_t *, codex_agent_conversations_t *, codex_agent_conversations_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        conversations_release_fn,
        codex_agent_conversations_release,
        (codex_agent_context_t *, codex_agent_conversations_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        conversations_active_get_fn,
        codex_agent_conversations_active_get,
        (codex_agent_context_t *, codex_agent_conversations_t *, codex_agent_snapshot_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        conversations_active_subscribe_fn,
        codex_agent_conversations_active_subscribe,
        (codex_agent_context_t *,
         codex_agent_conversations_t *,
         codex_agent_state_callback_t,
         void *,
         codex_agent_subscription_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        conversations_open_fn,
        codex_agent_conversations_open,
        (codex_agent_context_t *,
         codex_agent_conversations_t *,
         const codex_agent_conversation_open_options_t *,
         codex_agent_operation_callback_t,
         void *,
         codex_agent_operation_t **));

    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        conversation_retain_fn,
        codex_agent_conversation_retain,
        (codex_agent_context_t *, codex_agent_conversation_t *, codex_agent_conversation_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        conversation_release_fn,
        codex_agent_conversation_release,
        (codex_agent_context_t *, codex_agent_conversation_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        conversation_is_same_fn,
        codex_agent_conversation_is_same,
        (codex_agent_context_t *,
         codex_agent_conversation_t *,
         codex_agent_conversation_t *,
         int32_t *));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        conversation_send_fn,
        codex_agent_conversation_send,
        (codex_agent_context_t *,
         codex_agent_conversation_t *,
         const codex_agent_string_view_t *,
         codex_agent_operation_callback_t,
         void *,
         codex_agent_operation_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        conversation_cancel_turn_fn,
        codex_agent_conversation_cancel_turn,
        (codex_agent_context_t *,
         codex_agent_conversation_t *,
         codex_agent_operation_callback_t,
         void *,
         codex_agent_operation_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        conversation_close_fn,
        codex_agent_conversation_close,
        (codex_agent_context_t *,
         codex_agent_conversation_t *,
         codex_agent_operation_callback_t,
         void *,
         codex_agent_operation_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        conversation_state_get_fn,
        codex_agent_conversation_state_get,
        (codex_agent_context_t *, codex_agent_conversation_t *, codex_agent_snapshot_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        conversation_state_subscribe_fn,
        codex_agent_conversation_state_subscribe,
        (codex_agent_context_t *,
         codex_agent_conversation_t *,
         codex_agent_state_callback_t,
         void *,
         codex_agent_subscription_t **));

    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        operation_cancel_fn,
        codex_agent_operation_cancel,
        (codex_agent_context_t *, codex_agent_operation_t *));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        operation_result_fn,
        codex_agent_operation_result,
        (codex_agent_context_t *, codex_agent_operation_t *, codex_agent_status_t *));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        operation_conversation_fn,
        codex_agent_operation_conversation,
        (codex_agent_context_t *,
         codex_agent_conversations_t *,
         codex_agent_operation_t *,
         codex_agent_conversation_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        operation_failure_fn,
        codex_agent_operation_failure,
        (codex_agent_context_t *, codex_agent_operation_t *, codex_agent_failure_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        operation_destroy_fn,
        codex_agent_operation_destroy,
        (codex_agent_context_t *, codex_agent_operation_t **));

    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        subscription_destroy_fn,
        codex_agent_subscription_destroy,
        (codex_agent_context_t *, codex_agent_subscription_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        snapshot_destroy_fn,
        codex_agent_snapshot_destroy,
        (codex_agent_context_t *, codex_agent_snapshot_t **));

    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        host_state_kind_fn,
        codex_agent_host_state_kind,
        (codex_agent_context_t *, codex_agent_snapshot_t *, codex_agent_host_state_kind_t *));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        host_state_agent_fn,
        codex_agent_host_state_agent,
        (codex_agent_context_t *, codex_agent_host_t *, codex_agent_snapshot_t *, codex_agent_agent_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        host_state_failure_fn,
        codex_agent_host_state_failure,
        (codex_agent_context_t *, codex_agent_snapshot_t *, codex_agent_failure_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        host_state_has_workspace_fn,
        codex_agent_host_state_has_workspace,
        (codex_agent_context_t *, codex_agent_snapshot_t *, int32_t *));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        host_state_workspace_path_copy_fn,
        codex_agent_host_state_workspace_path_copy,
        (codex_agent_context_t *, codex_agent_snapshot_t *, uint8_t *, size_t, size_t *));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        host_state_workspace_display_name_copy_fn,
        codex_agent_host_state_workspace_display_name_copy,
        (codex_agent_context_t *, codex_agent_snapshot_t *, uint8_t *, size_t, size_t *));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        host_state_requirement_reason_fn,
        codex_agent_host_state_requirement_reason,
        (codex_agent_context_t *,
         codex_agent_snapshot_t *,
         codex_agent_workspace_selection_reason_t *));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        host_state_requirement_message_copy_fn,
        codex_agent_host_state_requirement_message_copy,
        (codex_agent_context_t *, codex_agent_snapshot_t *, uint8_t *, size_t, size_t *));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        active_conversation_fn,
        codex_agent_active_conversation,
        (codex_agent_context_t *,
         codex_agent_conversations_t *,
         codex_agent_snapshot_t *,
         codex_agent_conversation_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        conversation_state_status_fn,
        codex_agent_conversation_state_status,
        (codex_agent_context_t *,
         codex_agent_snapshot_t *,
         codex_agent_conversation_status_t *));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        conversation_state_failure_fn,
        codex_agent_conversation_state_failure,
        (codex_agent_context_t *, codex_agent_snapshot_t *, codex_agent_failure_t **));

    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        failure_retain_fn,
        codex_agent_failure_retain,
        (codex_agent_context_t *, codex_agent_failure_t *, codex_agent_failure_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        failure_release_fn,
        codex_agent_failure_release,
        (codex_agent_context_t *, codex_agent_failure_t **));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        failure_code_copy_fn,
        codex_agent_failure_code_copy,
        (codex_agent_context_t *, codex_agent_failure_t *, uint8_t *, size_t, size_t *));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        failure_message_copy_fn,
        codex_agent_failure_message_copy,
        (codex_agent_context_t *, codex_agent_failure_t *, uint8_t *, size_t, size_t *));
    DECLARE_FUNCTION_REFERENCE(
        codex_agent_status_t,
        failure_is_recoverable_fn,
        codex_agent_failure_is_recoverable,
        (codex_agent_context_t *, codex_agent_failure_t *, int32_t *));

    codex_agent_operation_callback_t volatile operation_callback_fn = operation_callback;
    codex_agent_state_callback_t volatile state_callback_fn = state_callback;

    OBSERVE(abi_version_fn);
    OBSERVE(abi_is_compatible_fn);
    OBSERVE(context_create_fn);
    OBSERVE(context_destroy_fn);
    OBSERVE(host_create_fn);
    OBSERVE(host_retain_fn);
    OBSERVE(host_release_fn);
    OBSERVE(host_select_workspace_fn);
    OBSERVE(host_close_fn);
    OBSERVE(host_state_get_fn);
    OBSERVE(host_state_subscribe_fn);
    OBSERVE(agent_retain_fn);
    OBSERVE(agent_release_fn);
    OBSERVE(agent_conversations_fn);
    OBSERVE(conversations_retain_fn);
    OBSERVE(conversations_release_fn);
    OBSERVE(conversations_active_get_fn);
    OBSERVE(conversations_active_subscribe_fn);
    OBSERVE(conversations_open_fn);
    OBSERVE(conversation_retain_fn);
    OBSERVE(conversation_release_fn);
    OBSERVE(conversation_is_same_fn);
    OBSERVE(conversation_send_fn);
    OBSERVE(conversation_cancel_turn_fn);
    OBSERVE(conversation_close_fn);
    OBSERVE(conversation_state_get_fn);
    OBSERVE(conversation_state_subscribe_fn);
    OBSERVE(operation_cancel_fn);
    OBSERVE(operation_result_fn);
    OBSERVE(operation_conversation_fn);
    OBSERVE(operation_failure_fn);
    OBSERVE(operation_destroy_fn);
    OBSERVE(subscription_destroy_fn);
    OBSERVE(snapshot_destroy_fn);
    OBSERVE(host_state_kind_fn);
    OBSERVE(host_state_agent_fn);
    OBSERVE(host_state_failure_fn);
    OBSERVE(host_state_has_workspace_fn);
    OBSERVE(host_state_workspace_path_copy_fn);
    OBSERVE(host_state_workspace_display_name_copy_fn);
    OBSERVE(host_state_requirement_reason_fn);
    OBSERVE(host_state_requirement_message_copy_fn);
    OBSERVE(active_conversation_fn);
    OBSERVE(conversation_state_status_fn);
    OBSERVE(conversation_state_failure_fn);
    OBSERVE(failure_retain_fn);
    OBSERVE(failure_release_fn);
    OBSERVE(failure_code_copy_fn);
    OBSERVE(failure_message_copy_fn);
    OBSERVE(failure_is_recoverable_fn);
    OBSERVE(operation_callback_fn);
    OBSERVE(state_callback_fn);
    return 0;
}

static int view_matches(
    codex_agent_string_view_t view,
    const uint8_t *expected_data,
    size_t expected_size) {
    return view.data == expected_data && view.size == expected_size;
}

static int validate_struct_declarations(void) {
    static const uint8_t client_name_data[] = {'s', 'm', 'o', 'k', 'e'};
    static const uint8_t client_title_data[] = {'C', ' ', 's', 'm', 'o', 'k', 'e'};
    static const uint8_t client_version_data[] = {'1', '.', '1'};
    static const uint8_t bundle_data[] = {'b', 'u', 'n', 'd', 'l', 'e'};
    static const uint8_t data_directory_data[] = {'d', 'a', 't', 'a'};
    static const uint8_t workspace_data[] = {'w', 'o', 'r', 'k'};
    static const uint8_t conversation_id_data[] = {'c', 'o', 'n', 'v'};
    static const uint8_t service_tier_data[] = {'f', 'a', 's', 't'};

    const codex_agent_string_view_t client_name = {
        client_name_data,
        sizeof(client_name_data)};
    const codex_agent_string_view_t client_title = {
        client_title_data,
        sizeof(client_title_data)};
    const codex_agent_string_view_t client_version = {
        client_version_data,
        sizeof(client_version_data)};
    const codex_agent_string_view_t bundle_directory = {
        bundle_data,
        sizeof(bundle_data)};
    const codex_agent_string_view_t data_directory = {
        data_directory_data,
        sizeof(data_directory_data)};
    const codex_agent_string_view_t workspace = {
        workspace_data,
        sizeof(workspace_data)};
    const codex_agent_string_view_t conversation_id = {
        conversation_id_data,
        sizeof(conversation_id_data)};
    const codex_agent_string_view_t service_tier = {
        service_tier_data,
        sizeof(service_tier_data)};
    const codex_agent_string_view_t empty = {NULL, 0U};

    const codex_agent_client_info_t client_info = {
        (uint32_t)sizeof(codex_agent_client_info_t),
        client_name,
        client_title,
        client_version};
    const codex_agent_host_options_t host_options = {
        (uint32_t)sizeof(codex_agent_host_options_t),
        bundle_directory,
        data_directory,
        client_info};
    const codex_agent_path_workspace_selection_t workspace_selection = {
        (uint32_t)sizeof(codex_agent_path_workspace_selection_t),
        workspace};
    const codex_agent_conversation_open_options_t new_conversation_options = {
        (uint32_t)sizeof(codex_agent_conversation_open_options_t),
        INT32_C(0),
        empty,
        INT32_C(0),
        CODEX_AGENT_APPROVAL_PRESET_NEVER,
        INT32_C(0),
        empty};
    const codex_agent_conversation_open_options_t resume_conversation_options = {
        (uint32_t)sizeof(codex_agent_conversation_open_options_t),
        INT32_C(1),
        conversation_id,
        INT32_C(1),
        CODEX_AGENT_APPROVAL_PRESET_ASK_ME,
        INT32_C(1),
        service_tier};

    CHECK(view_matches(client_name, client_name_data, sizeof(client_name_data)));
    CHECK(view_matches(empty, NULL, 0U));
    CHECK(client_info.struct_size == (uint32_t)sizeof(client_info));
    CHECK(view_matches(client_info.name, client_name_data, sizeof(client_name_data)));
    CHECK(view_matches(client_info.title, client_title_data, sizeof(client_title_data)));
    CHECK(view_matches(client_info.version, client_version_data, sizeof(client_version_data)));
    CHECK(host_options.struct_size == (uint32_t)sizeof(host_options));
    CHECK(view_matches(host_options.bundle_directory, bundle_data, sizeof(bundle_data)));
    CHECK(view_matches(
        host_options.data_directory,
        data_directory_data,
        sizeof(data_directory_data)));
    CHECK(host_options.client_info.struct_size == (uint32_t)sizeof(client_info));
    CHECK(workspace_selection.struct_size == (uint32_t)sizeof(workspace_selection));
    CHECK(view_matches(workspace_selection.path, workspace_data, sizeof(workspace_data)));
    CHECK(
        new_conversation_options.struct_size ==
        (uint32_t)sizeof(new_conversation_options));
    CHECK(new_conversation_options.has_conversation_id == INT32_C(0));
    CHECK(view_matches(new_conversation_options.conversation_id, NULL, 0U));
    CHECK(new_conversation_options.has_approval_preset == INT32_C(0));
    CHECK(new_conversation_options.approval_preset == CODEX_AGENT_APPROVAL_PRESET_NEVER);
    CHECK(new_conversation_options.has_service_tier == INT32_C(0));
    CHECK(view_matches(new_conversation_options.service_tier, NULL, 0U));
    CHECK(
        resume_conversation_options.struct_size ==
        (uint32_t)sizeof(resume_conversation_options));
    CHECK(resume_conversation_options.has_conversation_id == INT32_C(1));
    CHECK(view_matches(
        resume_conversation_options.conversation_id,
        conversation_id_data,
        sizeof(conversation_id_data)));
    CHECK(resume_conversation_options.has_approval_preset == INT32_C(1));
    CHECK(
        resume_conversation_options.approval_preset ==
        CODEX_AGENT_APPROVAL_PRESET_ASK_ME);
    CHECK(resume_conversation_options.has_service_tier == INT32_C(1));
    CHECK(view_matches(
        resume_conversation_options.service_tier,
        service_tier_data,
        sizeof(service_tier_data)));
    return 0;
}

int main(void) {
    codex_agent_context_t *context = NULL;
    int result = reference_function_declarations();

    CHECK(result == 0);
    result = validate_struct_declarations();
    CHECK(result == 0);

    CHECK(codex_agent_abi_version() == CODEX_AGENT_ABI_VERSION_CURRENT);
    CHECK(
        codex_agent_abi_is_compatible(CODEX_AGENT_ABI_VERSION_MINIMUM_COMPATIBLE) ==
        INT32_C(1));
    CHECK(codex_agent_abi_is_compatible(CODEX_AGENT_ABI_VERSION_CURRENT) == INT32_C(1));
    CHECK(
        codex_agent_abi_is_compatible(CODEX_AGENT_ABI_VERSION_ENCODE(1, 3, 0)) ==
        INT32_C(0));
    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(context != NULL);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(context == NULL);
    return 0;
}
