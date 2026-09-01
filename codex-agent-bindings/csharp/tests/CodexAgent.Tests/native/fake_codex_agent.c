#include "codex_agent.h"

#include <stdlib.h>
#include <string.h>

struct codex_agent_context {
    int live;
    int release_attempts;
    codex_agent_status_t destroy_status;
};
struct codex_agent_host {
    codex_agent_host_state_kind_t state;
    int release_attempts;
    int released;
    int test_mode;
    uint8_t *copied_inputs;
    size_t copied_input_offsets[5];
    size_t copied_input_sizes[5];
    int copied_inputs_detached;
};
struct codex_agent_agent { struct codex_agent_host *host; int release_attempts; };
struct codex_agent_authentication { int release_attempts; int released; };
struct codex_agent_interactions { int release_attempts; int released; };
struct codex_agent_integration_authorization { int release_attempts; int released; };
struct codex_agent_models { int release_attempts; int released; };
struct codex_agent_skills { int release_attempts; int released; };
struct codex_agent_hooks { int release_attempts; int released; };
struct codex_agent_plugins { int release_attempts; int released; };
struct codex_agent_connectors { int release_attempts; int released; };
struct codex_agent_mcp_servers { int release_attempts; int released; };
struct codex_agent_workspace { int live; };
struct codex_agent_authentication_method_api_key { int valid; };
struct codex_agent_authentication_method_chat_gpt_browser { int live; };
struct codex_agent_authentication_method_chat_gpt_device_code { int live; };
struct codex_agent_authentication_state { int kind; };
struct codex_agent_integration_authorization_state { int kind; };
struct codex_agent_integration { int kind; int valid; };
struct codex_agent_plugin_reference { int valid; };
struct codex_agent_model { int index; int valid; };
struct codex_agent_skill { int index; int valid; };
struct codex_agent_hook { int index; int valid; };
struct codex_agent_mcp_server_configuration { int valid; };
struct codex_agent_mcp_server { int index; int valid; };
struct codex_agent_elicitation_response { int valid; };
struct codex_agent_pending_approval { int index; };
struct codex_agent_pending_elicitation { int index; };
struct codex_agent_interaction_state { int kind; };
struct codex_agent_elicitation { int index; };
struct codex_agent_conversation_id { int live; int input_kind; };
struct codex_agent_conversation_summary { int index; };
struct codex_agent_conversation_value { int live; };
struct codex_agent_message { int index; };
struct codex_agent_invocation { int kind; int valid; };
struct codex_agent_invocation_plugin { int valid; };
struct codex_agent_invocation_skill { int valid; };
struct codex_agent_turn_request { int valid; };
struct codex_agent_turn_progress { int index; };
struct codex_agent_connector { int index; int valid; };
struct codex_agent_integration_connector { int valid; };
struct codex_agent_hook_handler_agent { int valid; };
struct codex_agent_hook_handler { int valid; };
struct codex_agent_service_tier { int index; };
struct codex_agent_skill_catalog { int live; };
struct codex_agent_skill_chunk { int live; };
struct codex_agent_hook_catalog { int live; };
struct codex_agent_plugin_summary { int index; };
struct codex_agent_plugin_catalog { int live; };
struct codex_agent_plugin_detail { int live; };
struct codex_agent_plugin_install_result { int live; };
struct codex_agent_plugin_skill { int live; };
struct codex_agent_pending_interaction { int index; int kind; };
struct codex_agent_mcp_transport_http { int valid; };
struct codex_agent_mcp_transport { int valid; };
struct codex_agent_form_text_value { int valid; };
struct codex_agent_form_value { int valid; };
struct conversation_entity {
    codex_agent_conversation_status_t state;
    int handle_count;
    struct codex_agent_conversations *owner;
    codex_agent_status_t release_status;
};
struct codex_agent_conversations {
    int release_attempts;
    int released;
    struct codex_agent_agent *agent;
    struct conversation_entity *active;
};
struct codex_agent_conversation { int release_attempts; int released; struct conversation_entity *entity; };
struct codex_agent_operation {
    codex_agent_status_t result;
    struct conversation_entity *conversation;
    codex_agent_operation_callback_t callback;
    void *user_data;
    codex_agent_status_t cancel_status;
    int require_conversation_owner;
    int destroy_attempts;
    int leaf_kind;
    void *leaf_service;
    struct codex_agent_host *host;
    codex_agent_host_state_kind_t host_target_state;
};
struct codex_agent_failure {
    const char *code;
    const char *message;
    int32_t recoverable;
};
struct codex_agent_subscription {
    int live;
    int destroy_attempts;
    struct codex_agent_host *host;
    struct codex_agent_conversations *conversations;
    struct conversation_entity *conversation;
    void *leaf_service;
    codex_agent_state_callback_t callback;
    void *user_data;
    codex_agent_context_t *context;
};
struct codex_agent_snapshot {
    int kind;
    void *value;
};

static int live_operations = 0;
static codex_agent_operation_t *pending_leaf_operation = NULL;
static codex_agent_subscription_t *pending_active_subscription = NULL;
static codex_agent_operation_t *pending_host_operation = NULL;
static codex_agent_subscription_t *pending_host_subscription = NULL;
static int agent_release_calls = 0;
static codex_agent_host_t *copied_input_host = NULL;

/* Test-only compiler evidence: every value comes from the exact public C SDK header. */
static const int32_t canonical_enum_values[] = {
    CODEX_AGENT_APPROVAL_DECISION_ACCEPT,
    CODEX_AGENT_APPROVAL_DECISION_DECLINE,
    CODEX_AGENT_APPROVAL_PRESET_ASK_ME,
    CODEX_AGENT_APPROVAL_PRESET_AUTO_REVIEW,
    CODEX_AGENT_APPROVAL_PRESET_NEVER,
    CODEX_AGENT_APPROVAL_PRESET_STRICT,
    CODEX_AGENT_AUTHENTICATION_STATUS_AUTHENTICATED,
    CODEX_AGENT_AUTHENTICATION_STATUS_AUTHENTICATING,
    CODEX_AGENT_AUTHENTICATION_STATUS_SIGNED_OUT,
    CODEX_AGENT_CAPABILITY_WEB_SEARCH,
    CODEX_AGENT_CATALOG_FRESHNESS_FRESH_CACHE,
    CODEX_AGENT_CATALOG_FRESHNESS_LIVE,
    CODEX_AGENT_CATALOG_FRESHNESS_STALE_CACHE,
    CODEX_AGENT_COLLABORATION_MODE_DEFAULT,
    CODEX_AGENT_COLLABORATION_MODE_PLAN,
    CODEX_AGENT_CONVERSATION_STATUS_CANCELLING_TURN,
    CODEX_AGENT_CONVERSATION_STATUS_CLOSED,
    CODEX_AGENT_CONVERSATION_STATUS_FAILED,
    CODEX_AGENT_CONVERSATION_STATUS_NEW,
    CODEX_AGENT_CONVERSATION_STATUS_OPENING,
    CODEX_AGENT_CONVERSATION_STATUS_READY,
    CODEX_AGENT_CONVERSATION_STATUS_RELOADING,
    CODEX_AGENT_CONVERSATION_STATUS_RUNNING_TURN,
    CODEX_AGENT_CONVERSATION_STATUS_STARTING_TURN,
    CODEX_AGENT_ELICITATION_ACTION_ACCEPT,
    CODEX_AGENT_ELICITATION_ACTION_CANCEL,
    CODEX_AGENT_ELICITATION_ACTION_DECLINE,
    CODEX_AGENT_ELICITATION_VALIDATION_ABOVE_MAXIMUM,
    CODEX_AGENT_ELICITATION_VALIDATION_BELOW_MINIMUM,
    CODEX_AGENT_ELICITATION_VALIDATION_DUPLICATE_SELECTION,
    CODEX_AGENT_ELICITATION_VALIDATION_INVALID_FORMAT,
    CODEX_AGENT_ELICITATION_VALIDATION_INVALID_SELECTION,
    CODEX_AGENT_ELICITATION_VALIDATION_INVALID_TYPE,
    CODEX_AGENT_ELICITATION_VALIDATION_MISSING_REQUIRED,
    CODEX_AGENT_ELICITATION_VALIDATION_NON_FINITE_NUMBER,
    CODEX_AGENT_ELICITATION_VALIDATION_NON_INTEGER,
    CODEX_AGENT_ELICITATION_VALIDATION_UNKNOWN_FIELD,
    CODEX_AGENT_FORM_FIELD_TYPE_BOOLEAN,
    CODEX_AGENT_FORM_FIELD_TYPE_INTEGER,
    CODEX_AGENT_FORM_FIELD_TYPE_MULTI_SELECT,
    CODEX_AGENT_FORM_FIELD_TYPE_NUMBER,
    CODEX_AGENT_FORM_FIELD_TYPE_SINGLE_SELECT,
    CODEX_AGENT_FORM_FIELD_TYPE_STRING,
    CODEX_AGENT_FORM_STRING_FORMAT_DATE_TIME,
    CODEX_AGENT_FORM_STRING_FORMAT_DATE,
    CODEX_AGENT_FORM_STRING_FORMAT_EMAIL,
    CODEX_AGENT_FORM_STRING_FORMAT_URI,
    CODEX_AGENT_HOOK_RUN_STATUS_BLOCKED,
    CODEX_AGENT_HOOK_RUN_STATUS_COMPLETED,
    CODEX_AGENT_HOOK_RUN_STATUS_FAILED,
    CODEX_AGENT_HOOK_RUN_STATUS_RUNNING,
    CODEX_AGENT_HOOK_RUN_STATUS_STOPPED,
    CODEX_AGENT_HOOK_TRUST_STATUS_MANAGED,
    CODEX_AGENT_HOOK_TRUST_STATUS_MODIFIED,
    CODEX_AGENT_HOOK_TRUST_STATUS_TRUSTED,
    CODEX_AGENT_HOOK_TRUST_STATUS_UNTRUSTED,
    CODEX_AGENT_INSTALLATION_SCOPE_USER,
    CODEX_AGENT_INSTALLATION_SCOPE_WORKSPACE,
    CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_AUTHORIZED,
    CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_AWAITING_COMPLETION,
    CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_FAILED,
    CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_IDLE,
    CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_STARTING,
    CODEX_AGENT_MCP_AUTH_STATUS_BEARER_TOKEN,
    CODEX_AGENT_MCP_AUTH_STATUS_NOT_LOGGED_IN,
    CODEX_AGENT_MCP_AUTH_STATUS_OAUTH,
    CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN,
    CODEX_AGENT_MCP_AUTH_STATUS_UNSUPPORTED,
    CODEX_AGENT_MCP_AUTHENTICATION_CHAT_GPT,
    CODEX_AGENT_MCP_AUTHENTICATION_OAUTH,
    CODEX_AGENT_MCP_ENVIRONMENT_SOURCE_LOCAL,
    CODEX_AGENT_MCP_ENVIRONMENT_SOURCE_REMOTE,
    CODEX_AGENT_MCP_TOOL_APPROVAL_APPROVE,
    CODEX_AGENT_MCP_TOOL_APPROVAL_AUTO,
    CODEX_AGENT_MCP_TOOL_APPROVAL_PROMPT,
    CODEX_AGENT_MCP_TOOL_APPROVAL_WRITES,
    CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_CODE_MODE,
    CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_DEFERRED,
    CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_DIRECT,
    CODEX_AGENT_MESSAGE_ROLE_ASSISTANT,
    CODEX_AGENT_MESSAGE_ROLE_USER,
    CODEX_AGENT_PLAN_STEP_COMPLETED,
    CODEX_AGENT_PLAN_STEP_IN_PROGRESS,
    CODEX_AGENT_PLAN_STEP_PENDING,
    CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_INSTALL,
    CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_USE,
    CODEX_AGENT_PLUGIN_INSTALL_POLICY_AVAILABLE,
    CODEX_AGENT_PLUGIN_INSTALL_POLICY_INSTALLED_BY_DEFAULT,
    CODEX_AGENT_PLUGIN_INSTALL_POLICY_NOT_AVAILABLE,
    CODEX_AGENT_RESOLUTION_DEFAULT,
    CODEX_AGENT_RESOLUTION_FIRST,
    CODEX_AGENT_RESOLUTION_PREFERRED,
    CODEX_AGENT_RESOURCE_ORIGIN_MANAGED,
    CODEX_AGENT_RESOURCE_ORIGIN_PLUGIN,
    CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN,
    CODEX_AGENT_RESOURCE_ORIGIN_USER,
    CODEX_AGENT_RESOURCE_ORIGIN_WORKSPACE,
    CODEX_AGENT_SKILL_SCOPE_ADMIN,
    CODEX_AGENT_SKILL_SCOPE_PLUGIN,
    CODEX_AGENT_SKILL_SCOPE_REPO,
    CODEX_AGENT_SKILL_SCOPE_SYSTEM,
    CODEX_AGENT_SKILL_SCOPE_USER,
    CODEX_AGENT_WORK_ACTIVITY_RUNNING_COMMAND,
    CODEX_AGENT_WORK_ACTIVITY_WRITING_FILES,
    CODEX_AGENT_AUTHORIZATION_PURPOSE_CHAT_GPT,
    CODEX_AGENT_AUTHORIZATION_PURPOSE_EXTERNAL,
    CODEX_AGENT_WORKSPACE_REASON_ACCESS_REVOKED,
    CODEX_AGENT_WORKSPACE_REASON_INVALID_SELECTION,
    CODEX_AGENT_WORKSPACE_REASON_NOT_FOUND,
    CODEX_AGENT_WORKSPACE_REASON_NOT_SELECTED,
};

size_t codex_agent_test_enum_count(void) {
    return sizeof(canonical_enum_values) / sizeof(canonical_enum_values[0]);
}

codex_agent_status_t codex_agent_test_enum_value(size_t index, int32_t *out_value) {
    if (out_value == NULL || index >= codex_agent_test_enum_count())
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_value = canonical_enum_values[index];
    return CODEX_AGENT_STATUS_OK;
}

static codex_agent_status_t copy_string(
    const char *value,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required) {
    const size_t size = strlen(value);
    if (out_required == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_required = size;
    if (capacity < size) return CODEX_AGENT_STATUS_BUFFER_TOO_SMALL;
    if (size != 0U) memcpy(buffer, value, size);
    return CODEX_AGENT_STATUS_OK;
}

static int view_equals(const codex_agent_string_view_t *view, const char *expected) {
    const size_t size = strlen(expected);
    return view != NULL && view->size == size && (size == 0U || memcmp(view->data, expected, size) == 0);
}

static int views_equal(
    const codex_agent_string_view_t *views, size_t count,
    const char *first, const char *second, const char *third) {
    return views != NULL && count == 3U && view_equals(&views[0], first) &&
        view_equals(&views[1], second) && view_equals(&views[2], third);
}

static codex_agent_status_t complete_operation(
    codex_agent_context_t *context,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_status_t result,
    codex_agent_operation_t **out_operation) {
    codex_agent_operation_t *operation = calloc(1U, sizeof(*operation));
    if (operation == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    live_operations += 1;
    operation->result = result;
    operation->callback = callback;
    operation->user_data = user_data;
    operation->cancel_status = CODEX_AGENT_STATUS_OK;
    *out_operation = operation;
    if (callback != NULL) callback(context, operation, user_data);
    return CODEX_AGENT_STATUS_OK;
}

uint32_t codex_agent_abi_version(void) {
#ifdef CODEX_AGENT_TEST_ABI_VERSION
    return CODEX_AGENT_TEST_ABI_VERSION;
#else
    return CODEX_AGENT_ABI_VERSION_CURRENT;
#endif
}

int32_t codex_agent_abi_is_compatible(uint32_t requested_version) {
    return requested_version >= CODEX_AGENT_ABI_VERSION_MINIMUM_COMPATIBLE &&
        requested_version <= CODEX_AGENT_ABI_VERSION_CURRENT;
}

#ifndef CODEX_AGENT_TEST_OMIT_RUNTIME_IDENTITY
codex_agent_status_t codex_agent_runtime_identity(char *buffer, size_t *inout_size) {
#if defined(__APPLE__) && defined(__aarch64__)
    static const char identity[] = "{\"appServerVersion\":\"0.149.0\",\"buildInputDigest\":\"sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee\",\"cAbiVersion\":\"1.13.0\",\"componentId\":\"sha256:2222222222222222222222222222222222222222222222222222222222222222\",\"contractComponentDigest\":\"sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff\",\"contractDigest\":\"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"runtimeCompatibilityVersion\":\"0.2.0\",\"schemaVersion\":1,\"target\":\"macos-arm64\"}";
#elif defined(__APPLE__) && defined(__x86_64__)
    static const char identity[] = "{\"appServerVersion\":\"0.149.0\",\"buildInputDigest\":\"sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee\",\"cAbiVersion\":\"1.13.0\",\"componentId\":\"sha256:3333333333333333333333333333333333333333333333333333333333333333\",\"contractComponentDigest\":\"sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff\",\"contractDigest\":\"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"runtimeCompatibilityVersion\":\"0.2.0\",\"schemaVersion\":1,\"target\":\"macos-x64\"}";
#elif defined(__linux__) && defined(__aarch64__)
    static const char identity[] = "{\"appServerVersion\":\"0.149.0\",\"buildInputDigest\":\"sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee\",\"cAbiVersion\":\"1.13.0\",\"componentId\":\"sha256:0000000000000000000000000000000000000000000000000000000000000000\",\"contractComponentDigest\":\"sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff\",\"contractDigest\":\"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"runtimeCompatibilityVersion\":\"0.2.0\",\"schemaVersion\":1,\"target\":\"linux-arm64\"}";
#elif defined(__linux__) && defined(__x86_64__)
    static const char identity[] = "{\"appServerVersion\":\"0.149.0\",\"buildInputDigest\":\"sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee\",\"cAbiVersion\":\"1.13.0\",\"componentId\":\"sha256:1111111111111111111111111111111111111111111111111111111111111111\",\"contractComponentDigest\":\"sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff\",\"contractDigest\":\"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"runtimeCompatibilityVersion\":\"0.2.0\",\"schemaVersion\":1,\"target\":\"linux-x64\"}";
#elif defined(_WIN64)
    static const char identity[] = "{\"appServerVersion\":\"0.149.0\",\"buildInputDigest\":\"sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee\",\"cAbiVersion\":\"1.13.0\",\"componentId\":\"sha256:4444444444444444444444444444444444444444444444444444444444444444\",\"contractComponentDigest\":\"sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff\",\"contractDigest\":\"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"runtimeCompatibilityVersion\":\"0.2.0\",\"schemaVersion\":1,\"target\":\"windows-x64\"}";
#else
#error unsupported Codex Agent test target
#endif
    const size_t required = sizeof(identity);
    if (inout_size == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (buffer == NULL || *inout_size < required) {
        *inout_size = required;
        return CODEX_AGENT_STATUS_BUFFER_TOO_SMALL;
    }
    memcpy(buffer, identity, required);
    *inout_size = required;
    return CODEX_AGENT_STATUS_OK;
}
#endif

codex_agent_status_t codex_agent_context_create(codex_agent_context_t **out_context) {
    *out_context = calloc(1U, sizeof(**out_context));
    if (*out_context == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_context)->live = 1;
    (*out_context)->destroy_status = CODEX_AGENT_STATUS_OK;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_context_destroy(codex_agent_context_t **context) {
    if ((*context)->destroy_status != CODEX_AGENT_STATUS_OK)
        return (*context)->destroy_status;
    if ((*context)->release_attempts++ == 0) return CODEX_AGENT_STATUS_BUSY;
    free(*context);
    *context = NULL;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_host_create(
    codex_agent_context_t *context,
    const codex_agent_host_options_t *options,
    codex_agent_host_t **out_host) {
    if (context == NULL || options == NULL || options->struct_size != sizeof(*options))
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (options->client_info.name.size == 12U &&
        memcmp(options->client_info.name.data, "context-busy", 12U) == 0)
        context->destroy_status = CODEX_AGENT_STATUS_BUSY;
    if (options->client_info.name.size == 13U &&
        memcmp(options->client_info.name.data, "context-error", 13U) == 0)
        context->destroy_status = CODEX_AGENT_STATUS_INTERNAL_ERROR;
    const int host_test = view_equals(&options->client_info.name, "host-parity");
    if (host_test &&
        (!view_equals(&options->bundle_directory, "/host-parity-bundle") ||
         !view_equals(&options->data_directory, "/host-parity-data") ||
         !view_equals(&options->client_info.title, "Host parity") ||
         !view_equals(&options->client_info.version, "1.0")))
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_host = calloc(1U, sizeof(**out_host));
    if (*out_host == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_host)->state = CODEX_AGENT_HOST_STATE_NEW;
    (*out_host)->test_mode = host_test;
    if (host_test) {
        const codex_agent_string_view_t *inputs[] = {
            &options->bundle_directory,
            &options->data_directory,
            &options->client_info.name,
            &options->client_info.title,
            &options->client_info.version,
        };
        size_t total_size = 0U;
        for (size_t index = 0U; index < 5U; index += 1U) total_size += inputs[index]->size;
        (*out_host)->copied_inputs = malloc(total_size);
        if ((*out_host)->copied_inputs == NULL) {
            free(*out_host);
            *out_host = NULL;
            return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
        }
        (*out_host)->copied_inputs_detached = 1;
        for (size_t index = 0U; index < 5U; index += 1U) {
            (*out_host)->copied_input_offsets[index] = index == 0U
                ? 0U
                : (*out_host)->copied_input_offsets[index - 1U] + (*out_host)->copied_input_sizes[index - 1U];
            (*out_host)->copied_input_sizes[index] = inputs[index]->size;
            uint8_t *destination = (*out_host)->copied_inputs + (*out_host)->copied_input_offsets[index];
            (*out_host)->copied_inputs_detached &= destination != inputs[index]->data;
            memcpy(destination, inputs[index]->data, inputs[index]->size);
        }
        copied_input_host = *out_host;
    }
    return CODEX_AGENT_STATUS_OK;
}

int32_t codex_agent_test_host_copied_input_count(void) {
    static const char *expected[] = {
        "/host-parity-bundle",
        "/host-parity-data",
        "host-parity",
        "Host parity",
        "1.0",
    };
    if (copied_input_host == NULL || !copied_input_host->copied_inputs_detached) return 0;
    int32_t matches = 0;
    for (size_t index = 0U; index < 5U; index += 1U) {
        const size_t size = strlen(expected[index]);
        const uint8_t *value = copied_input_host->copied_inputs + copied_input_host->copied_input_offsets[index];
        if (copied_input_host->copied_input_sizes[index] == size && memcmp(value, expected[index], size) == 0)
            matches += 1;
    }
    return matches;
}

codex_agent_status_t codex_agent_host_release(
    codex_agent_context_t *context,
    codex_agent_host_t **host) {
    (void)context;
    if ((*host)->state != CODEX_AGENT_HOST_STATE_CLOSED) return CODEX_AGENT_STATUS_BUSY;
    (*host)->released = 1;
    free((*host)->copied_inputs);
    (*host)->copied_inputs = NULL;
    if (copied_input_host == *host) copied_input_host = NULL;
    *host = NULL;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_host_start(
    codex_agent_context_t *context,
    codex_agent_host_t *host,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation) {
    if (!host->test_mode) {
        host->state = CODEX_AGENT_HOST_STATE_READY;
        return complete_operation(context, callback, user_data, CODEX_AGENT_STATUS_OK, out_operation);
    }
    codex_agent_status_t status = complete_operation(context, NULL, user_data, CODEX_AGENT_STATUS_OK, out_operation);
    if (status != CODEX_AGENT_STATUS_OK) return status;
    (*out_operation)->callback = callback;
    (*out_operation)->host = host;
    (*out_operation)->host_target_state = CODEX_AGENT_HOST_STATE_READY;
    pending_host_operation = *out_operation;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_host_select_workspace(
    codex_agent_context_t *context,
    codex_agent_host_t *host,
    const codex_agent_path_workspace_selection_t *selection,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation) {
    if (host->test_mode) {
        if (selection == NULL || !view_equals(&selection->path, "/selected-workspace"))
            return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
        codex_agent_status_t status = complete_operation(context, NULL, user_data, CODEX_AGENT_STATUS_OK, out_operation);
        if (status != CODEX_AGENT_STATUS_OK) return status;
        (*out_operation)->callback = callback;
        (*out_operation)->host = host;
        (*out_operation)->host_target_state = CODEX_AGENT_HOST_STATE_READY;
        pending_host_operation = *out_operation;
        return CODEX_AGENT_STATUS_OK;
    }
    host->state = CODEX_AGENT_HOST_STATE_READY;
    return complete_operation(context, callback, user_data, CODEX_AGENT_STATUS_OK, out_operation);
}

codex_agent_status_t codex_agent_host_close(
    codex_agent_context_t *context,
    codex_agent_host_t *host,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation) {
    if (host->test_mode) {
        codex_agent_status_t status = complete_operation(context, NULL, user_data, CODEX_AGENT_STATUS_OK, out_operation);
        if (status != CODEX_AGENT_STATUS_OK) return status;
        (*out_operation)->callback = callback;
        (*out_operation)->host = host;
        (*out_operation)->host_target_state = CODEX_AGENT_HOST_STATE_CLOSED;
        pending_host_operation = *out_operation;
        return CODEX_AGENT_STATUS_OK;
    }
    host->state = CODEX_AGENT_HOST_STATE_CLOSED;
    return complete_operation(context, callback, user_data, CODEX_AGENT_STATUS_OK, out_operation);
}

codex_agent_status_t codex_agent_test_complete_host_operation(codex_agent_status_t result) {
    codex_agent_operation_t *operation = pending_host_operation;
    if (operation == NULL) return CODEX_AGENT_STATUS_NOT_READY;
    pending_host_operation = NULL;
    operation->result = result;
    if (result == CODEX_AGENT_STATUS_OK && operation->host != NULL)
        operation->host->state = operation->host_target_state;
    operation->callback(NULL, operation, operation->user_data);
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_host_state_get(
    codex_agent_context_t *context,
    codex_agent_host_t *host,
    codex_agent_snapshot_t **out_snapshot) {
    (void)context;
    *out_snapshot = calloc(1U, sizeof(**out_snapshot));
    if (*out_snapshot == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_snapshot)->kind = host->state;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_host_state_subscribe(
    codex_agent_context_t *context,
    codex_agent_host_t *host,
    codex_agent_state_callback_t callback,
    void *user_data,
    codex_agent_subscription_t **out_subscription) {
    codex_agent_snapshot_t *snapshot = NULL;
    *out_subscription = calloc(1U, sizeof(**out_subscription));
    if (*out_subscription == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_subscription)->live = 1;
    (*out_subscription)->host = host;
    (*out_subscription)->callback = callback;
    (*out_subscription)->user_data = user_data;
    (*out_subscription)->context = context;
    codex_agent_host_state_get(context, host, &snapshot);
    callback(context, *out_subscription, CODEX_AGENT_STATUS_OK, snapshot, 0, user_data);
    if (host->test_mode) pending_host_subscription = *out_subscription;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_test_advance_host_subscription(codex_agent_context_t *context) {
    codex_agent_subscription_t *subscription = pending_host_subscription;
    codex_agent_snapshot_t *snapshot = NULL;
    if (subscription == NULL) return CODEX_AGENT_STATUS_NOT_READY;
    if (codex_agent_host_state_get(context, subscription->host, &snapshot) != CODEX_AGENT_STATUS_OK)
        return CODEX_AGENT_STATUS_INTERNAL_ERROR;
    pending_host_subscription = NULL;
    subscription->callback(context, subscription, CODEX_AGENT_STATUS_OK, snapshot, 0, subscription->user_data);
    subscription->callback(context, subscription, CODEX_AGENT_STATUS_OK, NULL, 1, subscription->user_data);
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_host_state_kind(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *snapshot,
    codex_agent_host_state_kind_t *out_kind) {
    (void)context;
    *out_kind = snapshot->kind;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_host_state_has_workspace(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *snapshot,
    int32_t *out_has_workspace) {
    (void)context;
    *out_has_workspace = snapshot->kind == CODEX_AGENT_HOST_STATE_READY ? 1 : 0;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_host_state_workspace_path_copy(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *snapshot,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required) {
    (void)context;
    (void)snapshot;
    return copy_string("/workspace", buffer, capacity, out_required);
}

codex_agent_status_t codex_agent_host_state_workspace_display_name_copy(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *snapshot,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required) {
    (void)context;
    (void)snapshot;
    (void)buffer;
    (void)capacity;
    if (out_required != NULL) *out_required = 0U;
    return CODEX_AGENT_STATUS_NOT_READY;
}

codex_agent_status_t codex_agent_host_state_agent(
    codex_agent_context_t *context,
    codex_agent_host_t *host,
    codex_agent_snapshot_t *snapshot,
    codex_agent_agent_t **out_agent) {
    (void)context;
    (void)snapshot;
    *out_agent = calloc(1U, sizeof(**out_agent));
    if (*out_agent == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_agent)->host = host;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_agent_release(
    codex_agent_context_t *context,
    codex_agent_agent_t **agent) {
    (void)context;
    agent_release_calls += 1;
    if ((*agent)->host->released != 0) return CODEX_AGENT_STATUS_INTERNAL_ERROR;
    if ((*agent)->release_attempts++ == 0) return CODEX_AGENT_STATUS_BUSY;
    free(*agent);
    *agent = NULL;
    return CODEX_AGENT_STATUS_OK;
}

int32_t codex_agent_test_agent_release_calls(void) { return agent_release_calls; }

codex_agent_status_t codex_agent_agent_conversations(
    codex_agent_context_t *context,
    codex_agent_agent_t *agent,
    codex_agent_conversations_t **out_conversations) {
    (void)context;
    *out_conversations = calloc(1U, sizeof(**out_conversations));
    if (*out_conversations == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_conversations)->agent = agent;
    return CODEX_AGENT_STATUS_OK;
}

#define DEFINE_AGENT_SERVICE(name, type) \
codex_agent_status_t codex_agent_agent_##name( \
    codex_agent_context_t *context, codex_agent_agent_t *agent, type **out_service) { \
    (void)context; \
    if (agent == NULL || out_service == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; \
    *out_service = calloc(1U, sizeof(**out_service)); \
    return *out_service == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK; \
}

#define DEFINE_SERVICE_RELEASE(name, type) \
codex_agent_status_t codex_agent_##name##_release( \
    codex_agent_context_t *context, type **service) { \
    (void)context; \
    if (service == NULL || *service == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; \
    if ((*service)->release_attempts++ == 0) return CODEX_AGENT_STATUS_BUSY; \
    (*service)->released = 1; \
    *service = NULL; \
    return CODEX_AGENT_STATUS_OK; \
}

DEFINE_AGENT_SERVICE(authentication, codex_agent_authentication_t)
DEFINE_AGENT_SERVICE(interactions, codex_agent_interactions_t)
DEFINE_AGENT_SERVICE(integration_authorization, codex_agent_integration_authorization_t)
DEFINE_AGENT_SERVICE(models, codex_agent_models_t)
DEFINE_AGENT_SERVICE(skills, codex_agent_skills_t)
DEFINE_AGENT_SERVICE(hooks, codex_agent_hooks_t)
DEFINE_AGENT_SERVICE(plugins, codex_agent_plugins_t)
DEFINE_AGENT_SERVICE(connectors, codex_agent_connectors_t)
DEFINE_AGENT_SERVICE(mcp_servers, codex_agent_mcp_servers_t)

codex_agent_status_t codex_agent_agent_workspace(
    codex_agent_context_t *context,
    codex_agent_agent_t *agent,
    codex_agent_workspace_t **out_workspace) {
    (void)context;
    if (agent == NULL || out_workspace == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_workspace = calloc(1U, sizeof(**out_workspace));
    if (*out_workspace == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_workspace)->live = 1;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_workspace_destroy(
    codex_agent_context_t *context,
    codex_agent_workspace_t **workspace) {
    (void)context;
    if (workspace == NULL || *workspace == NULL || (*workspace)->live == 0) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    (*workspace)->live = 0;
    free(*workspace);
    *workspace = NULL;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_workspace_path_copy(
    codex_agent_context_t *context,
    codex_agent_workspace_t *workspace,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required) {
    (void)context;
    if (workspace == NULL || workspace->live == 0) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return copy_string("/agent-workspace", buffer, capacity, out_required);
}

codex_agent_status_t codex_agent_workspace_display_name_copy(
    codex_agent_context_t *context,
    codex_agent_workspace_t *workspace,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required) {
    (void)context;
    if (workspace == NULL || workspace->live == 0) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return copy_string("Agent Workspace", buffer, capacity, out_required);
}

DEFINE_SERVICE_RELEASE(authentication, codex_agent_authentication_t)
DEFINE_SERVICE_RELEASE(interactions, codex_agent_interactions_t)
DEFINE_SERVICE_RELEASE(integration_authorization, codex_agent_integration_authorization_t)
DEFINE_SERVICE_RELEASE(models, codex_agent_models_t)
DEFINE_SERVICE_RELEASE(skills, codex_agent_skills_t)
DEFINE_SERVICE_RELEASE(hooks, codex_agent_hooks_t)
DEFINE_SERVICE_RELEASE(plugins, codex_agent_plugins_t)
DEFINE_SERVICE_RELEASE(connectors, codex_agent_connectors_t)
DEFINE_SERVICE_RELEASE(mcp_servers, codex_agent_mcp_servers_t)

#undef DEFINE_AGENT_SERVICE
#undef DEFINE_SERVICE_RELEASE

static codex_agent_status_t complete_leaf_operation(
    codex_agent_context_t *context,
    void *service,
    int leaf_kind,
    codex_agent_status_t result,
    int complete_immediately,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation) {
    codex_agent_operation_t *operation;
    if (context == NULL || service == NULL || out_operation == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    operation = calloc(1U, sizeof(*operation));
    if (operation == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    live_operations += 1;
    operation->result = result;
    operation->callback = callback;
    operation->user_data = user_data;
    operation->cancel_status = CODEX_AGENT_STATUS_OK;
    operation->leaf_kind = leaf_kind;
    operation->leaf_service = service;
    *out_operation = operation;
    if (complete_immediately != 0 && callback != NULL) callback(context, operation, user_data);
    else pending_leaf_operation = operation;
    return CODEX_AGENT_STATUS_OK;
}

#define COMPLETE_LEAF(service, kind) \
    complete_leaf_operation(context, (service), (kind), CODEX_AGENT_STATUS_OK, 0, callback, user_data, out_operation)

codex_agent_status_t codex_agent_test_complete_leaf_operation(codex_agent_context_t *context) {
    codex_agent_operation_t *operation = pending_leaf_operation;
    if (operation == NULL || operation->callback == NULL) return CODEX_AGENT_STATUS_NOT_READY;
    pending_leaf_operation = NULL;
    operation->callback(context, operation, operation->user_data);
    return CODEX_AGENT_STATUS_OK;
}

enum {
    LEAF_UNIT = 0, LEAF_MODELS = 1, LEAF_MODEL = 2, LEAF_STRING = 3,
    LEAF_TIER = 4, LEAF_NO_TIER = 5, LEAF_CONNECTORS = 6, LEAF_SKILL = 7,
    LEAF_SKILL_CATALOG = 8, LEAF_SKILL_CHUNK = 9, LEAF_HOOK = 10,
    LEAF_HOOK_CATALOG = 11, LEAF_PLUGIN_CATALOG = 12, LEAF_PLUGIN_DETAIL = 13,
    LEAF_PLUGIN_INSTALL = 14, LEAF_MCP_SERVER = 15, LEAF_MCP_SERVERS = 16,
    LEAF_CONVERSATION_SUMMARIES = 17, LEAF_CONVERSATION_VALUE = 18
};

#define DEFINE_LEAF_OPERATION_0(symbol, type) \
codex_agent_status_t symbol( \
    codex_agent_context_t *context, type *service, codex_agent_operation_callback_t callback, \
    void *user_data, codex_agent_operation_t **out_operation) { \
    if (service == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; \
    return COMPLETE_LEAF(service, 0); \
}

DEFINE_LEAF_OPERATION_0(codex_agent_authentication_cancel, codex_agent_authentication_t)
DEFINE_LEAF_OPERATION_0(codex_agent_authentication_sign_out, codex_agent_authentication_t)
DEFINE_LEAF_OPERATION_0(codex_agent_integration_authorization_cancel, codex_agent_integration_authorization_t)

codex_agent_status_t codex_agent_models_list(
    codex_agent_context_t *context, codex_agent_models_t *service, codex_agent_operation_callback_t callback,
    void *user_data, codex_agent_operation_t **out_operation) { return COMPLETE_LEAF(service, LEAF_MODELS); }
codex_agent_status_t codex_agent_hooks_list(
    codex_agent_context_t *context, codex_agent_hooks_t *service, codex_agent_operation_callback_t callback,
    void *user_data, codex_agent_operation_t **out_operation) { return COMPLETE_LEAF(service, LEAF_HOOK_CATALOG); }
codex_agent_status_t codex_agent_mcp_servers_list(
    codex_agent_context_t *context, codex_agent_mcp_servers_t *service, codex_agent_operation_callback_t callback,
    void *user_data, codex_agent_operation_t **out_operation) { return COMPLETE_LEAF(service, LEAF_MCP_SERVERS); }

codex_agent_status_t codex_agent_authentication_authenticate_api_key(
    codex_agent_context_t *context, codex_agent_authentication_t *service,
    codex_agent_authentication_method_api_key_t *method, codex_agent_operation_callback_t callback,
    void *user_data, codex_agent_operation_t **out_operation) {
    if (service == NULL || method == NULL || !method->valid) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return COMPLETE_LEAF(service, 0);
}

codex_agent_status_t codex_agent_authentication_authenticate_chat_gpt_browser(
    codex_agent_context_t *context, codex_agent_authentication_t *service,
    codex_agent_authentication_method_chat_gpt_browser_t *method, codex_agent_operation_callback_t callback,
    void *user_data, codex_agent_operation_t **out_operation) {
    if (service == NULL || method == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return COMPLETE_LEAF(service, 0);
}

codex_agent_status_t codex_agent_authentication_authenticate_chat_gpt_device_code(
    codex_agent_context_t *context, codex_agent_authentication_t *service,
    codex_agent_authentication_method_chat_gpt_device_code_t *method, codex_agent_operation_callback_t callback,
    void *user_data, codex_agent_operation_t **out_operation) {
    if (service == NULL || method == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return COMPLETE_LEAF(service, 0);
}

codex_agent_status_t codex_agent_integration_authorization_authorize(
    codex_agent_context_t *context, codex_agent_integration_authorization_t *service,
    codex_agent_integration_t *target, codex_agent_operation_callback_t callback,
    void *user_data, codex_agent_operation_t **out_operation) {
    if (service == NULL || target == NULL || !target->valid) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return COMPLETE_LEAF(service, 0);
}

codex_agent_status_t codex_agent_models_resolve(
    codex_agent_context_t *context, codex_agent_models_t *service, codex_agent_resolution_t resolution,
    codex_agent_operation_callback_t callback, void *user_data, codex_agent_operation_t **out_operation) {
    if (service == NULL || resolution != CODEX_AGENT_RESOLUTION_PREFERRED) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return COMPLETE_LEAF(service, LEAF_MODEL);
}

codex_agent_status_t codex_agent_models_resolve_effort(
    codex_agent_context_t *context, codex_agent_models_t *service, codex_agent_model_t *model,
    codex_agent_resolution_t resolution, codex_agent_operation_callback_t callback,
    void *user_data, codex_agent_operation_t **out_operation) {
    if (service == NULL || model == NULL || !model->valid || resolution != CODEX_AGENT_RESOLUTION_PREFERRED)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return COMPLETE_LEAF(service, LEAF_STRING);
}

codex_agent_status_t codex_agent_models_resolve_service_tier(
    codex_agent_context_t *context, codex_agent_models_t *service, codex_agent_model_t *model,
    codex_agent_resolution_t resolution, codex_agent_operation_callback_t callback,
    void *user_data, codex_agent_operation_t **out_operation) {
    if (service == NULL || model == NULL || !model->valid ||
        (resolution != CODEX_AGENT_RESOLUTION_PREFERRED && resolution != CODEX_AGENT_RESOLUTION_FIRST))
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return COMPLETE_LEAF(service, resolution == CODEX_AGENT_RESOLUTION_FIRST ? LEAF_NO_TIER : LEAF_TIER);
}

codex_agent_status_t codex_agent_skills_list(
    codex_agent_context_t *context, codex_agent_skills_t *service, int32_t force_reload,
    codex_agent_operation_callback_t callback, void *user_data, codex_agent_operation_t **out_operation) {
    if (service == NULL || force_reload != 1) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return COMPLETE_LEAF(service, LEAF_SKILL_CATALOG);
}

codex_agent_status_t codex_agent_skills_read(
    codex_agent_context_t *context, codex_agent_skills_t *service, const codex_agent_string_view_t *path,
    int64_t offset, codex_agent_operation_callback_t callback, void *user_data,
    codex_agent_operation_t **out_operation) {
    if (service == NULL || !view_equals(path, "/skill") || offset != 7) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return COMPLETE_LEAF(service, LEAF_SKILL_CHUNK);
}

codex_agent_status_t codex_agent_skills_install(
    codex_agent_context_t *context, codex_agent_skills_t *service, const codex_agent_string_view_t *directory,
    codex_agent_installation_scope_t scope, codex_agent_operation_callback_t callback, void *user_data,
    codex_agent_operation_t **out_operation) {
    if (service == NULL || !view_equals(directory, "/skill") || scope != CODEX_AGENT_INSTALLATION_SCOPE_USER)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return COMPLETE_LEAF(service, LEAF_SKILL);
}

codex_agent_status_t codex_agent_skills_uninstall(
    codex_agent_context_t *context, codex_agent_skills_t *service, codex_agent_skill_t *skill,
    codex_agent_operation_callback_t callback, void *user_data, codex_agent_operation_t **out_operation) {
    if (service == NULL || skill == NULL || !skill->valid) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return COMPLETE_LEAF(service, LEAF_UNIT);
}

codex_agent_status_t codex_agent_hooks_install(
    codex_agent_context_t *context, codex_agent_hooks_t *service, const codex_agent_string_view_t *directory,
    codex_agent_installation_scope_t scope, codex_agent_operation_callback_t callback, void *user_data,
    codex_agent_operation_t **out_operation) {
    if (service == NULL || !view_equals(directory, "/hook") || scope != CODEX_AGENT_INSTALLATION_SCOPE_USER)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return COMPLETE_LEAF(service, LEAF_HOOK);
}

#define DEFINE_LEAF_OPERATION_VALUE(symbol, service_type, value_type) \
codex_agent_status_t symbol( \
    codex_agent_context_t *context, service_type *service, value_type *value, \
    codex_agent_operation_callback_t callback, void *user_data, codex_agent_operation_t **out_operation) { \
    if (service == NULL || value == NULL || !value->valid) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; \
    return COMPLETE_LEAF(service, LEAF_UNIT); \
}

DEFINE_LEAF_OPERATION_VALUE(codex_agent_hooks_uninstall, codex_agent_hooks_t, codex_agent_hook_t)
DEFINE_LEAF_OPERATION_VALUE(codex_agent_hooks_trust, codex_agent_hooks_t, codex_agent_hook_t)

codex_agent_status_t codex_agent_plugins_list(
    codex_agent_context_t *context, codex_agent_plugins_t *service, int32_t force_reload,
    codex_agent_operation_callback_t callback, void *user_data, codex_agent_operation_t **out_operation) {
    if (service == NULL || force_reload != 1) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return COMPLETE_LEAF(service, LEAF_PLUGIN_CATALOG);
}

DEFINE_LEAF_OPERATION_VALUE(codex_agent_plugins_uninstall, codex_agent_plugins_t, codex_agent_plugin_reference_t)

#define DEFINE_TYPED_LEAF_OPERATION_VALUE(symbol, service_type, value_type, kind) \
codex_agent_status_t symbol( \
    codex_agent_context_t *context, service_type *service, value_type *value, \
    codex_agent_operation_callback_t callback, void *user_data, codex_agent_operation_t **out_operation) { \
    if (service == NULL || value == NULL || !value->valid) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; \
    return COMPLETE_LEAF(service, kind); \
}
DEFINE_TYPED_LEAF_OPERATION_VALUE(codex_agent_plugins_read, codex_agent_plugins_t, codex_agent_plugin_reference_t, LEAF_PLUGIN_DETAIL)
DEFINE_TYPED_LEAF_OPERATION_VALUE(codex_agent_plugins_install, codex_agent_plugins_t, codex_agent_plugin_reference_t, LEAF_PLUGIN_INSTALL)

codex_agent_status_t codex_agent_connectors_list(
    codex_agent_context_t *context, codex_agent_connectors_t *service, int32_t force_reload,
    codex_agent_operation_callback_t callback, void *user_data, codex_agent_operation_t **out_operation) {
    if (service == NULL || force_reload != 1) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return COMPLETE_LEAF(service, LEAF_CONNECTORS);
}

DEFINE_LEAF_OPERATION_VALUE(codex_agent_mcp_servers_remove, codex_agent_mcp_servers_t, codex_agent_mcp_server_t)
DEFINE_TYPED_LEAF_OPERATION_VALUE(codex_agent_mcp_servers_add, codex_agent_mcp_servers_t, codex_agent_mcp_server_configuration_t, LEAF_MCP_SERVER)

codex_agent_status_t codex_agent_interactions_resolve_approval(
    codex_agent_context_t *context, codex_agent_interactions_t *service,
    codex_agent_pending_approval_t *approval, codex_agent_approval_decision_t decision,
    codex_agent_operation_callback_t callback, void *user_data, codex_agent_operation_t **out_operation) {
    if (service == NULL || approval == NULL || decision != CODEX_AGENT_APPROVAL_DECISION_ACCEPT)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return complete_leaf_operation(context, service, LEAF_UNIT, CODEX_AGENT_STATUS_OK,
        0, callback, user_data, out_operation);
}

codex_agent_status_t codex_agent_interactions_resolve_elicitation(
    codex_agent_context_t *context, codex_agent_interactions_t *service,
    codex_agent_pending_elicitation_t *elicitation, codex_agent_elicitation_response_t *response,
    codex_agent_operation_callback_t callback, void *user_data, codex_agent_operation_t **out_operation) {
    if (service == NULL || elicitation == NULL || response == NULL || !response->valid)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return complete_leaf_operation(context, service, LEAF_UNIT, CODEX_AGENT_STATUS_OK,
        0, callback, user_data, out_operation);
}

codex_agent_status_t codex_agent_interactions_open_url(
    codex_agent_context_t *context, codex_agent_interactions_t *service,
    codex_agent_pending_elicitation_t *elicitation, codex_agent_operation_callback_t callback,
    void *user_data, codex_agent_operation_t **out_operation) {
    codex_agent_status_t result;
    if (service == NULL || elicitation == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    result = elicitation->index == 2 ? CODEX_AGENT_STATUS_OPERATION_FAILED : CODEX_AGENT_STATUS_OK;
    return complete_leaf_operation(context, service, LEAF_UNIT, result,
        elicitation->index >= 2 ? 1 : 0, callback, user_data, out_operation);
}

#undef DEFINE_LEAF_OPERATION_0
#undef DEFINE_LEAF_OPERATION_VALUE
#undef DEFINE_TYPED_LEAF_OPERATION_VALUE

#define LEAF_COUNT(symbol, kind, count_value) \
codex_agent_status_t symbol(codex_agent_context_t *context, codex_agent_operation_t *operation, size_t *out_count) { \
    (void)context; if (operation == NULL || operation->leaf_kind != (kind) || out_count == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; \
    *out_count = (count_value); return CODEX_AGENT_STATUS_OK; \
}
#define LEAF_OUTPUT(symbol, kind, type) \
codex_agent_status_t symbol(codex_agent_context_t *context, codex_agent_operation_t *operation, type **out_value) { \
    (void)context; if (operation == NULL || operation->leaf_kind != (kind) || out_value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; \
    *out_value = calloc(1U, sizeof(**out_value)); return *out_value == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK; \
}
#define LEAF_AT(symbol, kind, type) \
codex_agent_status_t symbol(codex_agent_context_t *context, codex_agent_operation_t *operation, size_t index, type **out_value) { \
    (void)context; if (operation == NULL || operation->leaf_kind != (kind) || index >= 3U || out_value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; \
    *out_value = calloc(1U, sizeof(**out_value)); if (*out_value == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY; \
    (*out_value)->index = (int)index; return CODEX_AGENT_STATUS_OK; \
}

LEAF_COUNT(codex_agent_operation_models_count, LEAF_MODELS, 3U)
LEAF_AT(codex_agent_operation_model_at, LEAF_MODELS, codex_agent_model_t)
LEAF_OUTPUT(codex_agent_operation_model, LEAF_MODEL, codex_agent_model_t)
LEAF_COUNT(codex_agent_operation_connectors_count, LEAF_CONNECTORS, 3U)
LEAF_AT(codex_agent_operation_connector_at, LEAF_CONNECTORS, codex_agent_connector_t)
LEAF_COUNT(codex_agent_operation_mcp_servers_count, LEAF_MCP_SERVERS, 3U)
LEAF_AT(codex_agent_operation_mcp_server_at, LEAF_MCP_SERVERS, codex_agent_mcp_server_t)
LEAF_OUTPUT(codex_agent_operation_mcp_server, LEAF_MCP_SERVER, codex_agent_mcp_server_t)
LEAF_OUTPUT(codex_agent_operation_skill, LEAF_SKILL, codex_agent_skill_t)
LEAF_OUTPUT(codex_agent_operation_skill_catalog, LEAF_SKILL_CATALOG, codex_agent_skill_catalog_t)
LEAF_OUTPUT(codex_agent_operation_skill_chunk, LEAF_SKILL_CHUNK, codex_agent_skill_chunk_t)
LEAF_OUTPUT(codex_agent_operation_hook, LEAF_HOOK, codex_agent_hook_t)
LEAF_OUTPUT(codex_agent_operation_hook_catalog, LEAF_HOOK_CATALOG, codex_agent_hook_catalog_t)
LEAF_OUTPUT(codex_agent_operation_plugin_catalog, LEAF_PLUGIN_CATALOG, codex_agent_plugin_catalog_t)
LEAF_OUTPUT(codex_agent_operation_plugin_detail, LEAF_PLUGIN_DETAIL, codex_agent_plugin_detail_t)
LEAF_OUTPUT(codex_agent_operation_plugin_install_result, LEAF_PLUGIN_INSTALL, codex_agent_plugin_install_result_t)

codex_agent_status_t codex_agent_operation_string_copy(
    codex_agent_context_t *context, codex_agent_operation_t *operation,
    uint8_t *buffer, size_t capacity, size_t *out_required) {
    (void)context;
    return operation == NULL || operation->leaf_kind != LEAF_STRING ? CODEX_AGENT_STATUS_INVALID_ARGUMENT :
        copy_string("medium", buffer, capacity, out_required);
}
codex_agent_status_t codex_agent_operation_has_service_tier(
    codex_agent_context_t *context, codex_agent_operation_t *operation, int32_t *out_present) {
    (void)context; if (operation == NULL || out_present == NULL ||
        (operation->leaf_kind != LEAF_TIER && operation->leaf_kind != LEAF_NO_TIER)) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_present = operation->leaf_kind == LEAF_TIER; return CODEX_AGENT_STATUS_OK;
}
LEAF_OUTPUT(codex_agent_operation_service_tier, LEAF_TIER, codex_agent_service_tier_t)

#undef LEAF_COUNT
#undef LEAF_OUTPUT
#undef LEAF_AT

#define DEFINE_AVAILABLE(name, type) \
codex_agent_status_t codex_agent_##name##_is_available( \
    codex_agent_context_t *context, type *service, int32_t *out_available) { \
    (void)context; \
    if (service == NULL || out_available == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; \
    *out_available = 1; \
    return CODEX_AGENT_STATUS_OK; \
}

DEFINE_AVAILABLE(skills, codex_agent_skills_t)
DEFINE_AVAILABLE(hooks, codex_agent_hooks_t)
DEFINE_AVAILABLE(plugins, codex_agent_plugins_t)
DEFINE_AVAILABLE(connectors, codex_agent_connectors_t)
DEFINE_AVAILABLE(mcp_servers, codex_agent_mcp_servers_t)
#undef DEFINE_AVAILABLE

static codex_agent_status_t leaf_snapshot(int kind, codex_agent_snapshot_t **out_snapshot) {
    if (out_snapshot == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_snapshot = calloc(1U, sizeof(**out_snapshot));
    if (*out_snapshot == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_snapshot)->kind = kind;
    return CODEX_AGENT_STATUS_OK;
}

static codex_agent_status_t leaf_subscribe(
    codex_agent_context_t *context, void *service, int kind, codex_agent_state_callback_t callback,
    void *user_data, codex_agent_subscription_t **out_subscription) {
    codex_agent_snapshot_t *snapshot = NULL;
    if (context == NULL || callback == NULL || out_subscription == NULL)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_subscription = calloc(1U, sizeof(**out_subscription));
    if (*out_subscription == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_subscription)->live = 1;
    (*out_subscription)->leaf_service = service;
    if (leaf_snapshot(kind, &snapshot) != CODEX_AGENT_STATUS_OK) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    callback(context, *out_subscription, CODEX_AGENT_STATUS_OK, snapshot, 0, user_data);
    snapshot = NULL;
    if (leaf_snapshot(kind == 0 ? 1 : kind == 1 ? 0 : kind + 100, &snapshot) != CODEX_AGENT_STATUS_OK)
        return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    callback(context, *out_subscription, CODEX_AGENT_STATUS_OK, snapshot, 0, user_data);
    callback(context, *out_subscription, CODEX_AGENT_STATUS_OK, NULL, 1, user_data);
    return CODEX_AGENT_STATUS_OK;
}

#define DEFINE_STATE_GET(symbol, type, kind) \
codex_agent_status_t symbol( \
    codex_agent_context_t *context, type *service, codex_agent_snapshot_t **out_snapshot) { \
    (void)context; \
    if (service == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; \
    return leaf_snapshot((kind), out_snapshot); \
}

#define DEFINE_STATE_SUBSCRIBE(symbol, type, kind) \
codex_agent_status_t symbol( \
    codex_agent_context_t *context, type *service, codex_agent_state_callback_t callback, \
    void *user_data, codex_agent_subscription_t **out_subscription) { \
    if (service == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; \
    return leaf_subscribe(context, service, (kind), callback, user_data, out_subscription); \
}

DEFINE_STATE_GET(codex_agent_authentication_state_get, codex_agent_authentication_t, 10)
DEFINE_STATE_SUBSCRIBE(codex_agent_authentication_state_subscribe, codex_agent_authentication_t, 10)
DEFINE_STATE_GET(codex_agent_authentication_is_authenticated_get, codex_agent_authentication_t, 1)
DEFINE_STATE_SUBSCRIBE(codex_agent_authentication_is_authenticated_subscribe, codex_agent_authentication_t, 1)
DEFINE_STATE_GET(codex_agent_authentication_is_authenticating_get, codex_agent_authentication_t, 0)
DEFINE_STATE_SUBSCRIBE(codex_agent_authentication_is_authenticating_subscribe, codex_agent_authentication_t, 0)
DEFINE_STATE_GET(codex_agent_integration_authorization_state_get, codex_agent_integration_authorization_t, 20)
DEFINE_STATE_SUBSCRIBE(codex_agent_integration_authorization_state_subscribe, codex_agent_integration_authorization_t, 20)
DEFINE_STATE_GET(codex_agent_integration_authorization_active_get, codex_agent_integration_authorization_t, 21)
DEFINE_STATE_SUBSCRIBE(codex_agent_integration_authorization_active_subscribe, codex_agent_integration_authorization_t, 21)
DEFINE_STATE_GET(codex_agent_integration_authorization_is_authorizing_get, codex_agent_integration_authorization_t, 0)
DEFINE_STATE_SUBSCRIBE(codex_agent_integration_authorization_is_authorizing_subscribe, codex_agent_integration_authorization_t, 0)
DEFINE_STATE_GET(codex_agent_interactions_state_get, codex_agent_interactions_t, 30)
DEFINE_STATE_SUBSCRIBE(codex_agent_interactions_state_subscribe, codex_agent_interactions_t, 30)
DEFINE_STATE_GET(codex_agent_interactions_approvals_get, codex_agent_interactions_t, 31)
DEFINE_STATE_SUBSCRIBE(codex_agent_interactions_approvals_subscribe, codex_agent_interactions_t, 31)
DEFINE_STATE_GET(codex_agent_interactions_elicitations_get, codex_agent_interactions_t, 32)
DEFINE_STATE_SUBSCRIBE(codex_agent_interactions_elicitations_subscribe, codex_agent_interactions_t, 32)

#undef DEFINE_STATE_GET
#undef DEFINE_STATE_SUBSCRIBE

codex_agent_status_t codex_agent_state_boolean_value(
    codex_agent_context_t *context, codex_agent_snapshot_t *snapshot, int32_t *out_value) {
    (void)context;
    if (snapshot == NULL || out_value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_value = snapshot->kind != 0 ? 1 : 0;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_authentication_state_value(
    codex_agent_context_t *context, codex_agent_snapshot_t *snapshot,
    codex_agent_authentication_state_t **out_state) {
    (void)context;
    if (snapshot == NULL || out_state == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_state = calloc(1U, sizeof(**out_state));
    if (*out_state != NULL) (*out_state)->kind = snapshot->kind;
    return *out_state == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_authentication_state_destroy(
    codex_agent_context_t *context, codex_agent_authentication_state_t **state) {
    (void)context;
    if (state == NULL || *state == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    free(*state);
    *state = NULL;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_authentication_state_status(
    codex_agent_context_t *context, codex_agent_authentication_state_t *state,
    codex_agent_authentication_status_t *out_status) {
    (void)context;
    if (state == NULL || out_status == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_status = state->kind == 10 ? CODEX_AGENT_AUTHENTICATION_STATUS_SIGNED_OUT : CODEX_AGENT_AUTHENTICATION_STATUS_AUTHENTICATED;
    return CODEX_AGENT_STATUS_OK;
}

#define DEFINE_AUTH_ABSENT(symbol) \
codex_agent_status_t symbol( \
    codex_agent_context_t *context, codex_agent_authentication_state_t *state, int32_t *out_present) { \
    (void)context; \
    if (state == NULL || out_present == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; \
    *out_present = 0; \
    return CODEX_AGENT_STATUS_OK; \
}

DEFINE_AUTH_ABSENT(codex_agent_authentication_state_has_pending_sign_in_url)
DEFINE_AUTH_ABSENT(codex_agent_authentication_state_has_device_verification_url)
DEFINE_AUTH_ABSENT(codex_agent_authentication_state_has_device_user_code)
DEFINE_AUTH_ABSENT(codex_agent_authentication_state_has_failure)
#undef DEFINE_AUTH_ABSENT

codex_agent_status_t codex_agent_integration_authorization_state_value(
    codex_agent_context_t *context, codex_agent_snapshot_t *snapshot,
    codex_agent_integration_authorization_state_t **out_state) {
    (void)context;
    if (snapshot == NULL || out_state == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_state = calloc(1U, sizeof(**out_state));
    if (*out_state != NULL) (*out_state)->kind = snapshot->kind;
    return *out_state == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_integration_authorization_state_destroy(
    codex_agent_context_t *context, codex_agent_integration_authorization_state_t **state) {
    (void)context;
    if (state == NULL || *state == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    free(*state);
    *state = NULL;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_integration_authorization_state_status(
    codex_agent_context_t *context, codex_agent_integration_authorization_state_t *state,
    codex_agent_integration_authorization_status_t *out_status) {
    (void)context;
    if (state == NULL || out_status == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_status = state->kind == 20 ? CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_IDLE : CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_AUTHORIZED;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_integration_authorization_state_target(
    codex_agent_context_t *context, codex_agent_integration_authorization_state_t *state,
    codex_agent_integration_t **out_target) {
    (void)context; (void)out_target;
    return state == NULL ? CODEX_AGENT_STATUS_INVALID_ARGUMENT : CODEX_AGENT_STATUS_NOT_READY;
}

codex_agent_status_t codex_agent_integration_authorization_state_failure(
    codex_agent_context_t *context, codex_agent_integration_authorization_state_t *state,
    codex_agent_failure_t **out_failure) {
    (void)context; (void)out_failure;
    return state == NULL ? CODEX_AGENT_STATUS_INVALID_ARGUMENT : CODEX_AGENT_STATUS_NOT_READY;
}

codex_agent_status_t codex_agent_integration_authorization_active_has_value(
    codex_agent_context_t *context, codex_agent_snapshot_t *snapshot, int32_t *out_present) {
    (void)context;
    if (snapshot == NULL || out_present == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_present = snapshot->kind == 21 ? 0 : 1;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_integration_authorization_active_value(
    codex_agent_context_t *context, codex_agent_snapshot_t *snapshot, codex_agent_integration_t **out_value) {
    (void)context;
    if (snapshot == NULL || snapshot->kind == 21 || out_value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_value = calloc(1U, sizeof(**out_value));
    return *out_value == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_integration_kind(
    codex_agent_context_t *context, codex_agent_integration_t *value, codex_agent_integration_kind_t *out_kind) {
    (void)context; if (value == NULL || out_kind == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_kind = CODEX_AGENT_INTEGRATION_KIND_CONNECTOR; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_integration_connector(
    codex_agent_context_t *context, codex_agent_integration_t *value, codex_agent_integration_connector_t **out_connector) {
    (void)context; if (value == NULL || out_connector == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_connector = calloc(1U, sizeof(**out_connector));
    return *out_connector == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_integration_connector_connector(
    codex_agent_context_t *context, codex_agent_integration_connector_t *value, codex_agent_connector_t **out_connector) {
    (void)context; if (value == NULL || out_connector == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_connector = calloc(1U, sizeof(**out_connector));
    return *out_connector == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_interactions_state_value(
    codex_agent_context_t *context, codex_agent_snapshot_t *snapshot,
    codex_agent_interaction_state_t **out_state) {
    (void)context;
    if (snapshot == NULL || out_state == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_state = calloc(1U, sizeof(**out_state));
    if (*out_state != NULL) (*out_state)->kind = snapshot->kind;
    return *out_state == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_interaction_state_destroy(
    codex_agent_context_t *context, codex_agent_interaction_state_t **state) {
    (void)context;
    if (state == NULL || *state == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    free(*state);
    *state = NULL;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_interaction_state_pending_count(
    codex_agent_context_t *context, codex_agent_interaction_state_t *state, size_t *out_count) {
    (void)context;
    if (state == NULL || out_count == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_count = state->kind == 30 ? 1U : 2U;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_interaction_state_has_failure(
    codex_agent_context_t *context, codex_agent_interaction_state_t *state, int32_t *out_present) {
    (void)context;
    if (state == NULL || out_present == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_present = 0;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_interaction_state_pending_at(
    codex_agent_context_t *context, codex_agent_interaction_state_t *state, size_t index,
    codex_agent_pending_interaction_t **out_interaction) {
    const size_t count = state != NULL && state->kind == 30 ? 1U : 2U;
    (void)context;
    if (state == NULL || index >= count || out_interaction == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_interaction = calloc(1U, sizeof(**out_interaction));
    if (*out_interaction == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_interaction)->index = (int)index;
    (*out_interaction)->kind = (int)(index % 2U);
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_pending_interaction_destroy(
    codex_agent_context_t *context, codex_agent_pending_interaction_t **interaction) {
    (void)context; if (interaction == NULL || *interaction == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    free(*interaction); *interaction = NULL; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_pending_interaction_kind(
    codex_agent_context_t *context, codex_agent_pending_interaction_t *interaction,
    codex_agent_pending_interaction_kind_t *out_kind) {
    (void)context; if (interaction == NULL || out_kind == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_kind = interaction->kind; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_pending_interaction_approval(
    codex_agent_context_t *context, codex_agent_pending_interaction_t *interaction,
    codex_agent_pending_approval_t **out_approval) {
    (void)context; if (interaction == NULL || interaction->kind != 0 || out_approval == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_approval = calloc(1U, sizeof(**out_approval));
    if (*out_approval != NULL) (*out_approval)->index = interaction->index;
    return *out_approval == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_pending_interaction_elicitation(
    codex_agent_context_t *context, codex_agent_pending_interaction_t *interaction,
    codex_agent_pending_elicitation_t **out_elicitation) {
    (void)context; if (interaction == NULL || interaction->kind != 1 || out_elicitation == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_elicitation = calloc(1U, sizeof(**out_elicitation));
    if (*out_elicitation != NULL) (*out_elicitation)->index = interaction->index;
    return *out_elicitation == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_interaction_state_is_resolving(
    codex_agent_context_t *context, codex_agent_interaction_state_t *state,
    codex_agent_pending_interaction_t *interaction, int32_t *out_value) {
    (void)context; if (state == NULL || interaction == NULL || out_value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_value = interaction->index == 1; return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_interactions_approvals_count(
    codex_agent_context_t *context, codex_agent_snapshot_t *snapshot, size_t *out_count) {
    (void)context;
    if (snapshot == NULL || out_count == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_count = snapshot->kind == 31 ? 3U : snapshot->kind == 131 ? 2U : 0U;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_interactions_elicitations_count(
    codex_agent_context_t *context, codex_agent_snapshot_t *snapshot, size_t *out_count) {
    (void)context;
    if (snapshot == NULL || out_count == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_count = snapshot->kind == 32 ? 3U : snapshot->kind == 132 ? 2U : 0U;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_interactions_approvals_at(
    codex_agent_context_t *context, codex_agent_snapshot_t *snapshot, size_t index,
    codex_agent_pending_approval_t **out_approval) {
    (void)context;
    if (snapshot == NULL || (snapshot->kind != 31 && snapshot->kind != 131) ||
        index >= (snapshot->kind == 31 ? 3U : 2U) || out_approval == NULL)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_approval = calloc(1U, sizeof(**out_approval));
    if (*out_approval != NULL) (*out_approval)->index = (int)index;
    return *out_approval == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_pending_approval_destroy(
    codex_agent_context_t *context, codex_agent_pending_approval_t **approval) {
    (void)context;
    if (approval == NULL || *approval == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    free(*approval);
    *approval = NULL;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_pending_approval_request_id_copy(
    codex_agent_context_t *context, codex_agent_pending_approval_t *approval,
    uint8_t *buffer, size_t capacity, size_t *out_required) {
    (void)context;
    return approval == NULL ? CODEX_AGENT_STATUS_INVALID_ARGUMENT :
        copy_string(approval->index == 1 ? "approval-second" : "approval-first", buffer, capacity, out_required);
}

codex_agent_status_t codex_agent_pending_approval_title_copy(
    codex_agent_context_t *context, codex_agent_pending_approval_t *approval,
    uint8_t *buffer, size_t capacity, size_t *out_required) {
    (void)context;
    return approval == NULL ? CODEX_AGENT_STATUS_INVALID_ARGUMENT : copy_string("Approve", buffer, capacity, out_required);
}

codex_agent_status_t codex_agent_pending_approval_details_copy(
    codex_agent_context_t *context, codex_agent_pending_approval_t *approval,
    uint8_t *buffer, size_t capacity, size_t *out_required) {
    (void)context;
    return approval == NULL ? CODEX_AGENT_STATUS_INVALID_ARGUMENT : copy_string("details", buffer, capacity, out_required);
}

codex_agent_status_t codex_agent_pending_approval_conversation_id(
    codex_agent_context_t *context, codex_agent_pending_approval_t *approval,
    codex_agent_conversation_id_t **out_id) {
    (void)context;
    if (approval == NULL || out_id == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_id = calloc(1U, sizeof(**out_id));
    return *out_id == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_conversation_id_destroy(
    codex_agent_context_t *context, codex_agent_conversation_id_t **id) {
    (void)context;
    if (id == NULL || *id == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    free(*id);
    *id = NULL;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_conversation_id_value_copy(
    codex_agent_context_t *context, codex_agent_conversation_id_t *id,
    uint8_t *buffer, size_t capacity, size_t *out_required) {
    (void)context;
    if (id == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return copy_string(id->live == 1 ? "conversation-alpha" : id->live == 2 ? "conversation-beta" : "conversation",
        buffer, capacity, out_required);
}

codex_agent_status_t codex_agent_interactions_elicitations_at(
    codex_agent_context_t *context, codex_agent_snapshot_t *snapshot, size_t index,
    codex_agent_pending_elicitation_t **out_elicitation) {
    (void)context;
    if (snapshot == NULL || (snapshot->kind != 32 && snapshot->kind != 132) ||
        index >= (snapshot->kind == 32 ? 3U : 2U) || out_elicitation == NULL)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_elicitation = calloc(1U, sizeof(**out_elicitation));
    if (*out_elicitation != NULL) (*out_elicitation)->index = (int)index;
    return *out_elicitation == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_pending_elicitation_destroy(
    codex_agent_context_t *context, codex_agent_pending_elicitation_t **pending) {
    (void)context;
    if (pending == NULL || *pending == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    free(*pending);
    *pending = NULL;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_pending_elicitation_elicitation(
    codex_agent_context_t *context, codex_agent_pending_elicitation_t *pending,
    codex_agent_elicitation_t **out_elicitation) {
    (void)context;
    if (pending == NULL || out_elicitation == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_elicitation = calloc(1U, sizeof(**out_elicitation));
    if (*out_elicitation != NULL) (*out_elicitation)->index = pending->index;
    return *out_elicitation == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_elicitation_destroy(
    codex_agent_context_t *context, codex_agent_elicitation_t **elicitation) {
    (void)context;
    if (elicitation == NULL || *elicitation == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    free(*elicitation);
    *elicitation = NULL;
    return CODEX_AGENT_STATUS_OK;
}

#define DEFINE_ELICITATION_COPY(symbol, text) \
codex_agent_status_t symbol( \
    codex_agent_context_t *context, codex_agent_elicitation_t *elicitation, \
    uint8_t *buffer, size_t capacity, size_t *out_required) { \
    (void)context; \
    return elicitation == NULL ? CODEX_AGENT_STATUS_INVALID_ARGUMENT : copy_string((text), buffer, capacity, out_required); \
}

DEFINE_ELICITATION_COPY(codex_agent_elicitation_server_name_copy, "server")
DEFINE_ELICITATION_COPY(codex_agent_elicitation_message_copy, "Choose")
DEFINE_ELICITATION_COPY(codex_agent_elicitation_url_copy, "https://example.com/authorize")
#undef DEFINE_ELICITATION_COPY

codex_agent_status_t codex_agent_elicitation_request_id_copy(
    codex_agent_context_t *context, codex_agent_elicitation_t *elicitation,
    uint8_t *buffer, size_t capacity, size_t *out_required) {
    (void)context;
    return elicitation == NULL ? CODEX_AGENT_STATUS_INVALID_ARGUMENT :
        copy_string(elicitation->index == 1 ? "elicitation-second" : "elicitation-first",
            buffer, capacity, out_required);
}

codex_agent_status_t codex_agent_elicitation_conversation_id(
    codex_agent_context_t *context, codex_agent_elicitation_t *elicitation,
    codex_agent_conversation_id_t **out_id) {
    (void)context;
    if (elicitation == NULL || out_id == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_id = calloc(1U, sizeof(**out_id));
    return *out_id == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_elicitation_has_form(
    codex_agent_context_t *context, codex_agent_elicitation_t *elicitation, int32_t *out_present) {
    (void)context;
    if (elicitation == NULL || out_present == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_present = 0;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_elicitation_has_url(
    codex_agent_context_t *context, codex_agent_elicitation_t *elicitation, int32_t *out_present) {
    (void)context;
    if (elicitation == NULL || out_present == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_present = 1;
    return CODEX_AGENT_STATUS_OK;
}

static codex_agent_status_t allocate_leaf_value(void **out_value, size_t size) {
    if (out_value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_value = calloc(1U, size);
    return *out_value == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}

#define DEFINE_VALUE_DESTROY(symbol, type) \
codex_agent_status_t symbol(codex_agent_context_t *context, type **value) { \
    (void)context; \
    if (value == NULL || *value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; \
    free(*value); \
    *value = NULL; \
    return CODEX_AGENT_STATUS_OK; \
}

codex_agent_status_t codex_agent_authentication_method_chat_gpt_browser_create(
    codex_agent_context_t *context, codex_agent_authentication_method_chat_gpt_browser_t **out_method) {
    (void)context;
    return allocate_leaf_value((void **)out_method, sizeof(**out_method));
}
DEFINE_VALUE_DESTROY(codex_agent_authentication_method_chat_gpt_browser_destroy, codex_agent_authentication_method_chat_gpt_browser_t)

codex_agent_status_t codex_agent_authentication_method_chat_gpt_device_code_create(
    codex_agent_context_t *context, codex_agent_authentication_method_chat_gpt_device_code_t **out_method) {
    (void)context;
    return allocate_leaf_value((void **)out_method, sizeof(**out_method));
}
DEFINE_VALUE_DESTROY(codex_agent_authentication_method_chat_gpt_device_code_destroy, codex_agent_authentication_method_chat_gpt_device_code_t)

codex_agent_status_t codex_agent_authentication_method_api_key_create(
    codex_agent_context_t *context, const codex_agent_string_view_t *value,
    codex_agent_authentication_method_api_key_t **out_method) {
    (void)context;
    if (value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (allocate_leaf_value((void **)out_method, sizeof(**out_method)) != CODEX_AGENT_STATUS_OK)
        return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_method)->valid = view_equals(value, "secret");
    return CODEX_AGENT_STATUS_OK;
}
DEFINE_VALUE_DESTROY(codex_agent_authentication_method_api_key_destroy, codex_agent_authentication_method_api_key_t)

codex_agent_status_t codex_agent_model_create(
    codex_agent_context_t *context, const codex_agent_string_view_t *id,
    const codex_agent_string_view_t *display_name, const codex_agent_string_view_t *description,
    const codex_agent_string_view_t *supported_efforts, size_t supported_effort_count,
    const codex_agent_string_view_t *default_effort, int32_t is_default,
    codex_agent_service_tier_t *const *service_tiers, size_t service_tier_count,
    int32_t has_default_service_tier, const codex_agent_string_view_t *default_service_tier,
    codex_agent_model_t **out_model) {
    (void)context; (void)service_tiers;
    if (id == NULL || display_name == NULL || description == NULL || default_effort == NULL)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (allocate_leaf_value((void **)out_model, sizeof(**out_model)) != CODEX_AGENT_STATUS_OK)
        return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_model)->valid = view_equals(id, "input-model") && view_equals(display_name, "Input Model") &&
        view_equals(description, "input description") &&
        views_equal(supported_efforts, supported_effort_count, "low", "medium", "low") &&
        view_equals(default_effort, "medium") && is_default == 1 && service_tier_count == 0U &&
        has_default_service_tier == 0 && view_equals(default_service_tier, "");
    return CODEX_AGENT_STATUS_OK;
}
DEFINE_VALUE_DESTROY(codex_agent_model_destroy, codex_agent_model_t)

codex_agent_status_t codex_agent_skill_create(
    codex_agent_context_t *context, const codex_agent_string_view_t *name,
    const codex_agent_string_view_t *display_name, const codex_agent_string_view_t *description,
    const codex_agent_string_view_t *path, codex_agent_skill_scope_t scope, int32_t is_enabled,
    int32_t has_brand_color, const codex_agent_string_view_t *brand_color,
    const codex_agent_string_view_t *dependencies, size_t dependency_count, int32_t can_uninstall,
    int32_t has_origin, codex_agent_resource_origin_t origin, codex_agent_skill_t **out_skill) {
    (void)context;
    if (name == NULL || display_name == NULL || description == NULL || path == NULL)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (allocate_leaf_value((void **)out_skill, sizeof(**out_skill)) != CODEX_AGENT_STATUS_OK)
        return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_skill)->valid = view_equals(name, "input-skill") && view_equals(display_name, "Input Skill") &&
        view_equals(description, "input skill description") && view_equals(path, "/input/skill") &&
        scope == CODEX_AGENT_SKILL_SCOPE_USER && is_enabled == 1 && has_brand_color == 1 &&
        view_equals(brand_color, "#123456") &&
        views_equal(dependencies, dependency_count, "dep-one", "dep-two", "dep-one") &&
        can_uninstall == 1 && has_origin == 1 && origin == CODEX_AGENT_RESOURCE_ORIGIN_USER;
    return CODEX_AGENT_STATUS_OK;
}
DEFINE_VALUE_DESTROY(codex_agent_skill_destroy, codex_agent_skill_t)

codex_agent_status_t codex_agent_plugin_reference_create(
    codex_agent_context_t *context, const codex_agent_string_view_t *id,
    const codex_agent_string_view_t *name, const codex_agent_string_view_t *marketplace_name,
    int32_t has_marketplace_path, const codex_agent_string_view_t *marketplace_path,
    int32_t has_remote_plugin_id, const codex_agent_string_view_t *remote_plugin_id,
    codex_agent_plugin_reference_t **out_reference) {
    (void)context;
    if (id == NULL || name == NULL || marketplace_name == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (allocate_leaf_value((void **)out_reference, sizeof(**out_reference)) != CODEX_AGENT_STATUS_OK)
        return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_reference)->valid = view_equals(id, "input-plugin") && view_equals(name, "input-name") &&
        view_equals(marketplace_name, "input-marketplace") && has_marketplace_path == 1 &&
        view_equals(marketplace_path, "/input/marketplace") && has_remote_plugin_id == 1 &&
        view_equals(remote_plugin_id, "input-remote");
    return CODEX_AGENT_STATUS_OK;
}
DEFINE_VALUE_DESTROY(codex_agent_plugin_reference_destroy, codex_agent_plugin_reference_t)

codex_agent_status_t codex_agent_connector_create(
    codex_agent_context_t *context, const codex_agent_string_view_t *id,
    const codex_agent_string_view_t *name, const codex_agent_string_view_t *description,
    int32_t has_install_url, const codex_agent_string_view_t *install_url,
    int32_t is_accessible, int32_t is_enabled, const codex_agent_string_view_t *plugin_names,
    size_t plugin_name_count, codex_agent_connector_t **out_connector) {
    (void)context;
    if (id == NULL || name == NULL || description == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (allocate_leaf_value((void **)out_connector, sizeof(**out_connector)) != CODEX_AGENT_STATUS_OK)
        return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_connector)->valid = view_equals(id, "input-connector") && view_equals(name, "Input Connector") &&
        view_equals(description, "input connector description") && has_install_url == 1 &&
        view_equals(install_url, "https://example.invalid/install") && is_accessible == 1 && is_enabled == 0 &&
        views_equal(plugin_names, plugin_name_count, "plugin-one", "plugin-two", "plugin-one");
    return CODEX_AGENT_STATUS_OK;
}
DEFINE_VALUE_DESTROY(codex_agent_connector_destroy, codex_agent_connector_t)

codex_agent_status_t codex_agent_integration_connector_create(
    codex_agent_context_t *context, codex_agent_connector_t *connector,
    codex_agent_integration_connector_t **out_integration) {
    (void)context;
    if (connector == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (allocate_leaf_value((void **)out_integration, sizeof(**out_integration)) != CODEX_AGENT_STATUS_OK)
        return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_integration)->valid = connector->valid;
    return CODEX_AGENT_STATUS_OK;
}
DEFINE_VALUE_DESTROY(codex_agent_integration_connector_destroy, codex_agent_integration_connector_t)

codex_agent_status_t codex_agent_integration_from_connector(
    codex_agent_context_t *context, codex_agent_integration_connector_t *connector,
    codex_agent_integration_t **out_integration) {
    (void)context;
    if (connector == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (allocate_leaf_value((void **)out_integration, sizeof(**out_integration)) != CODEX_AGENT_STATUS_OK)
        return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_integration)->kind = CODEX_AGENT_INTEGRATION_KIND_CONNECTOR;
    (*out_integration)->valid = connector->valid;
    return CODEX_AGENT_STATUS_OK;
}
DEFINE_VALUE_DESTROY(codex_agent_integration_destroy, codex_agent_integration_t)

codex_agent_status_t codex_agent_hook_handler_agent_acquire(
    codex_agent_context_t *context, codex_agent_hook_handler_agent_t **out_handler) {
    (void)context;
    if (allocate_leaf_value((void **)out_handler, sizeof(**out_handler)) != CODEX_AGENT_STATUS_OK)
        return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_handler)->valid = 1;
    return CODEX_AGENT_STATUS_OK;
}
DEFINE_VALUE_DESTROY(codex_agent_hook_handler_agent_destroy, codex_agent_hook_handler_agent_t)

codex_agent_status_t codex_agent_hook_handler_from_agent(
    codex_agent_context_t *context, codex_agent_hook_handler_agent_t *agent,
    codex_agent_hook_handler_t **out_handler) {
    (void)context;
    if (agent == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (allocate_leaf_value((void **)out_handler, sizeof(**out_handler)) != CODEX_AGENT_STATUS_OK)
        return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_handler)->valid = agent->valid;
    return CODEX_AGENT_STATUS_OK;
}
DEFINE_VALUE_DESTROY(codex_agent_hook_handler_destroy, codex_agent_hook_handler_t)

codex_agent_status_t codex_agent_hook_create(
    codex_agent_context_t *context, const codex_agent_string_view_t *key,
    const codex_agent_string_view_t *current_hash, int32_t is_enabled,
    const codex_agent_string_view_t *event_name, codex_agent_hook_handler_t *handler,
    int32_t is_managed, const codex_agent_string_view_t *source,
    const codex_agent_string_view_t *source_path, int64_t timeout_seconds,
    codex_agent_hook_trust_status_t trust_status, int32_t has_matcher,
    const codex_agent_string_view_t *matcher, int32_t has_plugin_id,
    const codex_agent_string_view_t *plugin_id, int32_t has_status_message,
    const codex_agent_string_view_t *status_message, int32_t has_origin,
    codex_agent_resource_origin_t origin, int32_t can_uninstall, codex_agent_hook_t **out_hook) {
    (void)context;
    if (key == NULL || current_hash == NULL || event_name == NULL || handler == NULL ||
        source == NULL || source_path == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (allocate_leaf_value((void **)out_hook, sizeof(**out_hook)) != CODEX_AGENT_STATUS_OK)
        return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_hook)->valid = view_equals(key, "input-hook") && view_equals(current_hash, "input-hash") &&
        is_enabled == 1 && view_equals(event_name, "input-event") && handler->valid && is_managed == 0 &&
        view_equals(source, "USER") && view_equals(source_path, "/input/hook") && timeout_seconds == 9 &&
        trust_status == CODEX_AGENT_HOOK_TRUST_STATUS_UNTRUSTED && has_matcher == 1 && view_equals(matcher, "*.kt") &&
        has_plugin_id == 1 && view_equals(plugin_id, "plugin-id") && has_status_message == 1 &&
        view_equals(status_message, "status") && has_origin == 1 && origin == CODEX_AGENT_RESOURCE_ORIGIN_USER &&
        can_uninstall == 1;
    return CODEX_AGENT_STATUS_OK;
}
DEFINE_VALUE_DESTROY(codex_agent_hook_destroy, codex_agent_hook_t)

codex_agent_status_t codex_agent_form_text_value_create(
    codex_agent_context_t *context, const codex_agent_string_view_t *value, codex_agent_form_text_value_t **out_text) {
    (void)context; if (value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (allocate_leaf_value((void **)out_text, sizeof(**out_text)) != CODEX_AGENT_STATUS_OK)
        return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_text)->valid = view_equals(value, "accepted");
    return CODEX_AGENT_STATUS_OK;
}
DEFINE_VALUE_DESTROY(codex_agent_form_text_value_destroy, codex_agent_form_text_value_t)
codex_agent_status_t codex_agent_form_value_from_text(
    codex_agent_context_t *context, codex_agent_form_text_value_t *text, codex_agent_form_value_t **out_value) {
    (void)context; if (text == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (allocate_leaf_value((void **)out_value, sizeof(**out_value)) != CODEX_AGENT_STATUS_OK)
        return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_value)->valid = text->valid;
    return CODEX_AGENT_STATUS_OK;
}
DEFINE_VALUE_DESTROY(codex_agent_form_value_destroy, codex_agent_form_value_t)

codex_agent_status_t codex_agent_elicitation_response_create(
    codex_agent_context_t *context, codex_agent_elicitation_action_t action,
    const codex_agent_string_view_t *content_keys,
    codex_agent_form_value_t *const *content_values, size_t content_count,
    codex_agent_elicitation_response_t **out_response) {
    (void)context;
    if (allocate_leaf_value((void **)out_response, sizeof(**out_response)) != CODEX_AGENT_STATUS_OK)
        return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_response)->valid = action == CODEX_AGENT_ELICITATION_ACTION_ACCEPT && content_count == 1U &&
        content_keys != NULL && view_equals(&content_keys[0], "answer") && content_values != NULL &&
        content_values[0] != NULL && content_values[0]->valid;
    return CODEX_AGENT_STATUS_OK;
}
DEFINE_VALUE_DESTROY(codex_agent_elicitation_response_destroy, codex_agent_elicitation_response_t)

codex_agent_status_t codex_agent_mcp_transport_http_create(
    codex_agent_context_t *context, const codex_agent_string_view_t *url,
    int32_t has_bearer_token_environment_variable,
    const codex_agent_string_view_t *bearer_token_environment_variable,
    int32_t has_headers, const codex_agent_string_view_t *header_keys,
    const codex_agent_string_view_t *header_values, size_t header_count,
    int32_t has_environment_headers, const codex_agent_string_view_t *environment_header_keys,
    const codex_agent_string_view_t *environment_header_values, size_t environment_header_count,
    int32_t has_headers_helper, const codex_agent_string_view_t *headers_helper,
    codex_agent_mcp_transport_http_t **out_transport) {
    (void)context;
    if (url == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (allocate_leaf_value((void **)out_transport, sizeof(**out_transport)) != CODEX_AGENT_STATUS_OK)
        return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_transport)->valid = view_equals(url, "https://example.invalid/mcp") &&
        has_bearer_token_environment_variable == 1 && view_equals(bearer_token_environment_variable, "TOKEN") &&
        has_headers == 1 && header_count == 2U && view_equals(&header_keys[0], "X-One") &&
        view_equals(&header_values[0], "one") && view_equals(&header_keys[1], "X-Two") &&
        view_equals(&header_values[1], "two") && has_environment_headers == 1 &&
        environment_header_count == 1U && view_equals(&environment_header_keys[0], "Authorization") &&
        view_equals(&environment_header_values[0], "AUTH") && has_headers_helper == 1 &&
        view_equals(headers_helper, "helper");
    return CODEX_AGENT_STATUS_OK;
}
DEFINE_VALUE_DESTROY(codex_agent_mcp_transport_http_destroy, codex_agent_mcp_transport_http_t)

codex_agent_status_t codex_agent_mcp_transport_from_http(
    codex_agent_context_t *context, codex_agent_mcp_transport_http_t *http,
    codex_agent_mcp_transport_t **out_transport) {
    (void)context;
    if (http == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (allocate_leaf_value((void **)out_transport, sizeof(**out_transport)) != CODEX_AGENT_STATUS_OK)
        return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_transport)->valid = http->valid;
    return CODEX_AGENT_STATUS_OK;
}
DEFINE_VALUE_DESTROY(codex_agent_mcp_transport_destroy, codex_agent_mcp_transport_t)

codex_agent_status_t codex_agent_mcp_server_configuration_create(
    codex_agent_context_t *context, const codex_agent_string_view_t *name,
    codex_agent_mcp_transport_t *transport, int32_t has_authentication,
    codex_agent_mcp_authentication_t authentication, const codex_agent_string_view_t *environment_id,
    int32_t is_enabled, int32_t is_required, int32_t supports_parallel_tool_calls,
    int32_t has_omit_tools_from, const codex_agent_mcp_tool_exposure_surface_t *omit_tools_from,
    size_t omit_tools_from_count, int32_t has_startup_timeout_seconds, double startup_timeout_seconds,
    int32_t has_tool_timeout_seconds, double tool_timeout_seconds, int32_t has_default_tool_approval,
    codex_agent_mcp_tool_approval_t default_tool_approval, int32_t has_enabled_tools,
    const codex_agent_string_view_t *enabled_tools, size_t enabled_tools_count,
    int32_t has_disabled_tools, const codex_agent_string_view_t *disabled_tools,
    size_t disabled_tools_count, int32_t has_scopes, const codex_agent_string_view_t *scopes,
    size_t scopes_count, int32_t has_oauth, codex_agent_mcp_oauth_configuration_t *oauth,
    int32_t has_oauth_resource, const codex_agent_string_view_t *oauth_resource,
    const codex_agent_string_view_t *tool_keys,
    codex_agent_mcp_tool_configuration_t *const *tool_configurations, size_t tool_count,
    codex_agent_mcp_server_configuration_t **out_configuration) {
    (void)context; (void)oauth; (void)tool_keys; (void)tool_configurations;
    if (name == NULL || transport == NULL || environment_id == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (allocate_leaf_value((void **)out_configuration, sizeof(**out_configuration)) != CODEX_AGENT_STATUS_OK)
        return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_configuration)->valid = view_equals(name, "input-server") && transport->valid &&
        has_authentication == 1 && authentication == CODEX_AGENT_MCP_AUTHENTICATION_OAUTH &&
        view_equals(environment_id, "local") && is_enabled == 0 && is_required == 1 &&
        supports_parallel_tool_calls == 1 && has_omit_tools_from == 1 && omit_tools_from_count == 3U &&
        omit_tools_from != NULL && omit_tools_from[0] == CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_CODE_MODE &&
        omit_tools_from[1] == CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_DEFERRED &&
        omit_tools_from[2] == CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_CODE_MODE &&
        has_startup_timeout_seconds == 1 && startup_timeout_seconds == 1.5 &&
        has_tool_timeout_seconds == 1 && tool_timeout_seconds == 2.5 && has_default_tool_approval == 1 &&
        default_tool_approval == CODEX_AGENT_MCP_TOOL_APPROVAL_WRITES && has_enabled_tools == 1 &&
        views_equal(enabled_tools, enabled_tools_count, "search", "fetch", "search") &&
        has_disabled_tools == 1 && disabled_tools_count == 1U && view_equals(&disabled_tools[0], "delete") &&
        has_scopes == 1 && views_equal(scopes, scopes_count, "files.read", "files.write", "files.read") &&
        has_oauth == 0 && has_oauth_resource == 1 && view_equals(oauth_resource, "resource") && tool_count == 0U;
    return CODEX_AGENT_STATUS_OK;
}
DEFINE_VALUE_DESTROY(codex_agent_mcp_server_configuration_destroy, codex_agent_mcp_server_configuration_t)

codex_agent_status_t codex_agent_mcp_server_create(
    codex_agent_context_t *context, const codex_agent_string_view_t *name,
    const codex_agent_string_view_t *display_name, codex_agent_mcp_auth_status_t auth_status,
    codex_agent_mcp_server_configuration_t *configuration, codex_agent_resource_origin_t origin,
    int32_t can_remove, codex_agent_mcp_server_t **out_server) {
    (void)context;
    if (name == NULL || display_name == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (allocate_leaf_value((void **)out_server, sizeof(**out_server)) != CODEX_AGENT_STATUS_OK)
        return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_server)->valid = view_equals(name, "remove-server") && view_equals(display_name, "Remove Server") &&
        auth_status == CODEX_AGENT_MCP_AUTH_STATUS_OAUTH && configuration == NULL &&
        origin == CODEX_AGENT_RESOURCE_ORIGIN_USER && can_remove == 1;
    return CODEX_AGENT_STATUS_OK;
}
DEFINE_VALUE_DESTROY(codex_agent_mcp_server_destroy, codex_agent_mcp_server_t)

DEFINE_VALUE_DESTROY(codex_agent_service_tier_destroy, codex_agent_service_tier_t)
DEFINE_VALUE_DESTROY(codex_agent_skill_catalog_destroy, codex_agent_skill_catalog_t)
DEFINE_VALUE_DESTROY(codex_agent_skill_chunk_destroy, codex_agent_skill_chunk_t)
DEFINE_VALUE_DESTROY(codex_agent_hook_catalog_destroy, codex_agent_hook_catalog_t)
DEFINE_VALUE_DESTROY(codex_agent_plugin_catalog_destroy, codex_agent_plugin_catalog_t)
DEFINE_VALUE_DESTROY(codex_agent_plugin_detail_destroy, codex_agent_plugin_detail_t)
DEFINE_VALUE_DESTROY(codex_agent_plugin_install_result_destroy, codex_agent_plugin_install_result_t)
DEFINE_VALUE_DESTROY(codex_agent_plugin_summary_destroy, codex_agent_plugin_summary_t)
DEFINE_VALUE_DESTROY(codex_agent_plugin_skill_destroy, codex_agent_plugin_skill_t)

#define INDEXED_COPY(symbol, type, first, second) \
codex_agent_status_t symbol(codex_agent_context_t *context, type *value, uint8_t *buffer, size_t capacity, size_t *out_required) { \
    (void)context; return value == NULL ? CODEX_AGENT_STATUS_INVALID_ARGUMENT : \
        copy_string(value->index == 1 ? (second) : (first), buffer, capacity, out_required); \
}
#define CONSTANT_COPY(symbol, type, text) \
codex_agent_status_t symbol(codex_agent_context_t *context, type *value, uint8_t *buffer, size_t capacity, size_t *out_required) { \
    (void)context; return value == NULL ? CODEX_AGENT_STATUS_INVALID_ARGUMENT : copy_string((text), buffer, capacity, out_required); \
}
#define INT_GET(symbol, type, field_type, result) \
codex_agent_status_t symbol(codex_agent_context_t *context, type *value, field_type *out_value) { \
    (void)context; if (value == NULL || out_value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; \
    *out_value = (result); return CODEX_AGENT_STATUS_OK; \
}

INDEXED_COPY(codex_agent_model_id_copy, codex_agent_model_t, "model-alpha", "model-beta")
INDEXED_COPY(codex_agent_model_display_name_copy, codex_agent_model_t, "Model Alpha", "Model Beta")
CONSTANT_COPY(codex_agent_model_description_copy, codex_agent_model_t, "native model")
CONSTANT_COPY(codex_agent_model_default_effort_copy, codex_agent_model_t, "medium")
INT_GET(codex_agent_model_supported_efforts_count, codex_agent_model_t, size_t, 2U)
codex_agent_status_t codex_agent_model_supported_effort_copy_at(
    codex_agent_context_t *context, codex_agent_model_t *value, size_t index,
    uint8_t *buffer, size_t capacity, size_t *out_required) {
    (void)context; if (value == NULL || index >= 2U) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return copy_string(index == 0U ? "low" : "medium", buffer, capacity, out_required);
}
INT_GET(codex_agent_model_is_default, codex_agent_model_t, int32_t, 1)
INT_GET(codex_agent_model_service_tiers_count, codex_agent_model_t, size_t, 0U)
INT_GET(codex_agent_model_has_default_service_tier, codex_agent_model_t, int32_t, 0)
CONSTANT_COPY(codex_agent_model_default_service_tier_copy, codex_agent_model_t, "fast")
codex_agent_status_t codex_agent_model_service_tier_at(
    codex_agent_context_t *context, codex_agent_model_t *value, size_t index, codex_agent_service_tier_t **out_tier) {
    (void)context; (void)index; (void)out_tier;
    return value == NULL ? CODEX_AGENT_STATUS_INVALID_ARGUMENT : CODEX_AGENT_STATUS_NOT_READY;
}

CONSTANT_COPY(codex_agent_service_tier_id_copy, codex_agent_service_tier_t, "fast")
CONSTANT_COPY(codex_agent_service_tier_name_copy, codex_agent_service_tier_t, "Fast")
CONSTANT_COPY(codex_agent_service_tier_description_copy, codex_agent_service_tier_t, "Native tier")

INDEXED_COPY(codex_agent_connector_id_copy, codex_agent_connector_t, "connector-alpha", "connector-beta")
INDEXED_COPY(codex_agent_connector_name_copy, codex_agent_connector_t, "Connector Alpha", "Connector Beta")
CONSTANT_COPY(codex_agent_connector_description_copy, codex_agent_connector_t, "native connector")
INT_GET(codex_agent_connector_has_install_url, codex_agent_connector_t, int32_t, 0)
CONSTANT_COPY(codex_agent_connector_install_url_copy, codex_agent_connector_t, "https://example.invalid/install")
INT_GET(codex_agent_connector_is_accessible, codex_agent_connector_t, int32_t, 1)
INT_GET(codex_agent_connector_is_enabled, codex_agent_connector_t, int32_t, 1)
INT_GET(codex_agent_connector_plugin_names_count, codex_agent_connector_t, size_t, 2U)
codex_agent_status_t codex_agent_connector_plugin_names_copy_at(
    codex_agent_context_t *context, codex_agent_connector_t *value, size_t index,
    uint8_t *buffer, size_t capacity, size_t *out_required) {
    (void)context; if (value == NULL || index >= 2U) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return copy_string(index == 0U ? "plugin-one" : "plugin-two", buffer, capacity, out_required);
}

INDEXED_COPY(codex_agent_mcp_server_name_copy, codex_agent_mcp_server_t, "server-alpha", "server-beta")
INDEXED_COPY(codex_agent_mcp_server_display_name_copy, codex_agent_mcp_server_t, "Server Alpha", "Server Beta")
INT_GET(codex_agent_mcp_server_auth_status, codex_agent_mcp_server_t, codex_agent_mcp_auth_status_t, CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN)
INT_GET(codex_agent_mcp_server_has_configuration, codex_agent_mcp_server_t, int32_t, 0)
INT_GET(codex_agent_mcp_server_origin, codex_agent_mcp_server_t, codex_agent_resource_origin_t, CODEX_AGENT_RESOURCE_ORIGIN_USER)
INT_GET(codex_agent_mcp_server_can_remove, codex_agent_mcp_server_t, int32_t, 1)
INT_GET(codex_agent_mcp_server_is_authorized, codex_agent_mcp_server_t, int32_t, 0)

CONSTANT_COPY(codex_agent_skill_name_copy, codex_agent_skill_t, "skill")
CONSTANT_COPY(codex_agent_skill_display_name_copy, codex_agent_skill_t, "Native Skill")
CONSTANT_COPY(codex_agent_skill_description_copy, codex_agent_skill_t, "native skill")
CONSTANT_COPY(codex_agent_skill_path_copy, codex_agent_skill_t, "/native/skill")
INT_GET(codex_agent_skill_scope, codex_agent_skill_t, codex_agent_skill_scope_t, CODEX_AGENT_SKILL_SCOPE_USER)
INT_GET(codex_agent_skill_is_enabled, codex_agent_skill_t, int32_t, 1)
INT_GET(codex_agent_skill_has_brand_color, codex_agent_skill_t, int32_t, 0)
CONSTANT_COPY(codex_agent_skill_brand_color_copy, codex_agent_skill_t, "#000000")
INT_GET(codex_agent_skill_dependencies_count, codex_agent_skill_t, size_t, 2U)
codex_agent_status_t codex_agent_skill_dependencies_copy_at(
    codex_agent_context_t *context, codex_agent_skill_t *value, size_t index,
    uint8_t *buffer, size_t capacity, size_t *out_required) {
    (void)context; if (value == NULL || index >= 2U) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return copy_string(index == 0U ? "dep-one" : "dep-two", buffer, capacity, out_required);
}
INT_GET(codex_agent_skill_can_uninstall, codex_agent_skill_t, int32_t, 1)
INT_GET(codex_agent_skill_origin, codex_agent_skill_t, codex_agent_resource_origin_t, CODEX_AGENT_RESOURCE_ORIGIN_USER)

#undef INDEXED_COPY
#undef CONSTANT_COPY
#undef INT_GET

#define SIMPLE_COUNT(symbol, type, result) \
codex_agent_status_t symbol(codex_agent_context_t *context, type *value, size_t *out_count) { \
    (void)context; if (value == NULL || out_count == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; \
    *out_count = (result); return CODEX_AGENT_STATUS_OK; \
}
#define SIMPLE_BOOL(symbol, type, result) \
codex_agent_status_t symbol(codex_agent_context_t *context, type *value, int32_t *out_value) { \
    (void)context; if (value == NULL || out_value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; \
    *out_value = (result); return CODEX_AGENT_STATUS_OK; \
}
#define SIMPLE_COPY(symbol, type, text) \
codex_agent_status_t symbol(codex_agent_context_t *context, type *value, uint8_t *buffer, size_t capacity, size_t *out_required) { \
    (void)context; return value == NULL ? CODEX_AGENT_STATUS_INVALID_ARGUMENT : copy_string((text), buffer, capacity, out_required); \
}

SIMPLE_COUNT(codex_agent_skill_catalog_skills_count, codex_agent_skill_catalog_t, 1U)
SIMPLE_COUNT(codex_agent_skill_catalog_errors_count, codex_agent_skill_catalog_t, 1U)
codex_agent_status_t codex_agent_skill_catalog_skills_at(
    codex_agent_context_t *context, codex_agent_skill_catalog_t *catalog, size_t index, codex_agent_skill_t **out_skill) {
    (void)context; if (catalog == NULL || index != 0U || out_skill == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_skill = calloc(1U, sizeof(**out_skill)); return *out_skill == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_skill_catalog_errors_copy_at(
    codex_agent_context_t *context, codex_agent_skill_catalog_t *catalog, size_t index,
    uint8_t *buffer, size_t capacity, size_t *out_required) {
    (void)context; return catalog == NULL || index != 0U ? CODEX_AGENT_STATUS_INVALID_ARGUMENT :
        copy_string("native skill warning", buffer, capacity, out_required);
}
SIMPLE_COPY(codex_agent_skill_chunk_content_copy, codex_agent_skill_chunk_t, "native skill content")
codex_agent_status_t codex_agent_skill_chunk_next_offset(
    codex_agent_context_t *context, codex_agent_skill_chunk_t *chunk, int32_t *out_present, int64_t *out_offset) {
    (void)context; if (chunk == NULL || out_present == NULL || out_offset == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_present = 1; *out_offset = 27; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_skill_chunk_total_bytes(
    codex_agent_context_t *context, codex_agent_skill_chunk_t *chunk, int64_t *out_total) {
    (void)context; if (chunk == NULL || out_total == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_total = 42; return CODEX_AGENT_STATUS_OK;
}

SIMPLE_COUNT(codex_agent_hook_catalog_hooks_count, codex_agent_hook_catalog_t, 0U)
SIMPLE_COUNT(codex_agent_hook_catalog_warnings_count, codex_agent_hook_catalog_t, 1U)
SIMPLE_COUNT(codex_agent_hook_catalog_errors_count, codex_agent_hook_catalog_t, 1U)
#define HOOK_CATALOG_COPY(symbol, text) \
codex_agent_status_t symbol(codex_agent_context_t *context, codex_agent_hook_catalog_t *catalog, size_t index, \
    uint8_t *buffer, size_t capacity, size_t *out_required) { \
    (void)context; return catalog == NULL || index != 0U ? CODEX_AGENT_STATUS_INVALID_ARGUMENT : copy_string((text), buffer, capacity, out_required); \
}
HOOK_CATALOG_COPY(codex_agent_hook_catalog_warnings_copy_at, "native hook warning")
HOOK_CATALOG_COPY(codex_agent_hook_catalog_errors_copy_at, "native hook error")
#undef HOOK_CATALOG_COPY
codex_agent_status_t codex_agent_hook_catalog_hooks_at(
    codex_agent_context_t *context, codex_agent_hook_catalog_t *catalog, size_t index, codex_agent_hook_t **out_hook) {
    (void)context; (void)index; (void)out_hook;
    return catalog == NULL ? CODEX_AGENT_STATUS_INVALID_ARGUMENT : CODEX_AGENT_STATUS_NOT_READY;
}

SIMPLE_COPY(codex_agent_hook_key_copy, codex_agent_hook_t, "native-hook")
SIMPLE_COPY(codex_agent_hook_current_hash_copy, codex_agent_hook_t, "native-hash")
SIMPLE_COPY(codex_agent_hook_event_name_copy, codex_agent_hook_t, "native-event")
SIMPLE_COPY(codex_agent_hook_source_copy, codex_agent_hook_t, "USER")
SIMPLE_COPY(codex_agent_hook_source_path_copy, codex_agent_hook_t, "/native/hook")
SIMPLE_COPY(codex_agent_hook_matcher_copy, codex_agent_hook_t, "matcher")
SIMPLE_COPY(codex_agent_hook_plugin_id_copy, codex_agent_hook_t, "plugin")
SIMPLE_COPY(codex_agent_hook_status_message_copy, codex_agent_hook_t, "ready")
SIMPLE_BOOL(codex_agent_hook_is_enabled, codex_agent_hook_t, 1)
SIMPLE_BOOL(codex_agent_hook_is_managed, codex_agent_hook_t, 0)
SIMPLE_BOOL(codex_agent_hook_has_matcher, codex_agent_hook_t, 0)
SIMPLE_BOOL(codex_agent_hook_has_plugin_id, codex_agent_hook_t, 0)
SIMPLE_BOOL(codex_agent_hook_has_status_message, codex_agent_hook_t, 0)
SIMPLE_BOOL(codex_agent_hook_can_uninstall, codex_agent_hook_t, 1)
codex_agent_status_t codex_agent_hook_timeout_seconds(codex_agent_context_t *context, codex_agent_hook_t *hook, int64_t *out_value) {
    (void)context; if (hook == NULL || out_value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; *out_value = 5; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_hook_trust_status(codex_agent_context_t *context, codex_agent_hook_t *hook, codex_agent_hook_trust_status_t *out_value) {
    (void)context; if (hook == NULL || out_value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; *out_value = CODEX_AGENT_HOOK_TRUST_STATUS_TRUSTED; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_hook_origin(codex_agent_context_t *context, codex_agent_hook_t *hook, codex_agent_resource_origin_t *out_value) {
    (void)context; if (hook == NULL || out_value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; *out_value = CODEX_AGENT_RESOURCE_ORIGIN_USER; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_hook_handler(codex_agent_context_t *context, codex_agent_hook_t *hook, codex_agent_hook_handler_t **out_handler) {
    (void)context; if (hook == NULL || out_handler == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_handler = calloc(1U, sizeof(**out_handler)); return *out_handler == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_hook_handler_kind(codex_agent_context_t *context, codex_agent_hook_handler_t *handler, int32_t *out_kind) {
    (void)context; if (handler == NULL || out_kind == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; *out_kind = 0; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_hook_handler_agent(codex_agent_context_t *context, codex_agent_hook_handler_t *handler, codex_agent_hook_handler_agent_t **out_agent) {
    (void)context; if (handler == NULL || out_agent == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_agent = calloc(1U, sizeof(**out_agent)); return *out_agent == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}

SIMPLE_COUNT(codex_agent_plugin_catalog_plugins_count, codex_agent_plugin_catalog_t, 1U)
SIMPLE_COUNT(codex_agent_plugin_catalog_errors_count, codex_agent_plugin_catalog_t, 1U)
codex_agent_status_t codex_agent_plugin_catalog_plugins_at(codex_agent_context_t *context, codex_agent_plugin_catalog_t *catalog, size_t index, codex_agent_plugin_summary_t **out_summary) {
    (void)context; if (catalog == NULL || index != 0U || out_summary == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_summary = calloc(1U, sizeof(**out_summary)); return *out_summary == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_plugin_catalog_errors_copy_at(codex_agent_context_t *context, codex_agent_plugin_catalog_t *catalog, size_t index, uint8_t *buffer, size_t capacity, size_t *out_required) {
    (void)context; return catalog == NULL || index != 0U ? CODEX_AGENT_STATUS_INVALID_ARGUMENT : copy_string("native plugin warning", buffer, capacity, out_required);
}
codex_agent_status_t codex_agent_plugin_catalog_freshness(codex_agent_context_t *context, codex_agent_plugin_catalog_t *catalog, codex_agent_catalog_freshness_t *out_value) {
    (void)context; if (catalog == NULL || out_value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; *out_value = CODEX_AGENT_CATALOG_FRESHNESS_LIVE; return CODEX_AGENT_STATUS_OK;
}

SIMPLE_COPY(codex_agent_plugin_summary_display_name_copy, codex_agent_plugin_summary_t, "Native Plugin")
SIMPLE_COPY(codex_agent_plugin_summary_description_copy, codex_agent_plugin_summary_t, "native plugin")
SIMPLE_BOOL(codex_agent_plugin_summary_is_installed, codex_agent_plugin_summary_t, 1)
SIMPLE_BOOL(codex_agent_plugin_summary_is_enabled, codex_agent_plugin_summary_t, 1)
SIMPLE_BOOL(codex_agent_plugin_summary_is_available, codex_agent_plugin_summary_t, 1)
SIMPLE_COUNT(codex_agent_plugin_summary_capabilities_count, codex_agent_plugin_summary_t, 1U)
SIMPLE_BOOL(codex_agent_plugin_summary_has_brand_color, codex_agent_plugin_summary_t, 0)
SIMPLE_BOOL(codex_agent_plugin_summary_has_privacy_policy_url, codex_agent_plugin_summary_t, 0)
SIMPLE_BOOL(codex_agent_plugin_summary_has_terms_of_service_url, codex_agent_plugin_summary_t, 0)
SIMPLE_BOOL(codex_agent_plugin_summary_has_website_url, codex_agent_plugin_summary_t, 0)
SIMPLE_COPY(codex_agent_plugin_summary_brand_color_copy, codex_agent_plugin_summary_t, "#000000")
SIMPLE_COPY(codex_agent_plugin_summary_privacy_policy_url_copy, codex_agent_plugin_summary_t, "https://example.invalid/privacy")
SIMPLE_COPY(codex_agent_plugin_summary_terms_of_service_url_copy, codex_agent_plugin_summary_t, "https://example.invalid/terms")
SIMPLE_COPY(codex_agent_plugin_summary_website_url_copy, codex_agent_plugin_summary_t, "https://example.invalid")
codex_agent_status_t codex_agent_plugin_summary_reference(codex_agent_context_t *context, codex_agent_plugin_summary_t *summary, codex_agent_plugin_reference_t **out_reference) {
    (void)context; if (summary == NULL || out_reference == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_reference = calloc(1U, sizeof(**out_reference)); return *out_reference == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_plugin_summary_install_policy(codex_agent_context_t *context, codex_agent_plugin_summary_t *summary, codex_agent_plugin_install_policy_t *out_value) {
    (void)context; if (summary == NULL || out_value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; *out_value = CODEX_AGENT_PLUGIN_INSTALL_POLICY_AVAILABLE; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_plugin_summary_auth_policy(codex_agent_context_t *context, codex_agent_plugin_summary_t *summary, codex_agent_plugin_auth_policy_t *out_value) {
    (void)context; if (summary == NULL || out_value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; *out_value = CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_USE; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_plugin_summary_capabilities_copy_at(codex_agent_context_t *context, codex_agent_plugin_summary_t *summary, size_t index, uint8_t *buffer, size_t capacity, size_t *out_required) {
    (void)context; return summary == NULL || index != 0U ? CODEX_AGENT_STATUS_INVALID_ARGUMENT : copy_string("native-capability", buffer, capacity, out_required);
}

SIMPLE_COPY(codex_agent_plugin_reference_id_copy, codex_agent_plugin_reference_t, "plugin")
SIMPLE_COPY(codex_agent_plugin_reference_name_copy, codex_agent_plugin_reference_t, "plugin")
SIMPLE_COPY(codex_agent_plugin_reference_marketplace_name_copy, codex_agent_plugin_reference_t, "marketplace")
SIMPLE_BOOL(codex_agent_plugin_reference_has_marketplace_path, codex_agent_plugin_reference_t, 0)
SIMPLE_BOOL(codex_agent_plugin_reference_has_remote_plugin_id, codex_agent_plugin_reference_t, 0)
SIMPLE_COPY(codex_agent_plugin_reference_marketplace_path_copy, codex_agent_plugin_reference_t, "/marketplace")
SIMPLE_COPY(codex_agent_plugin_reference_remote_plugin_id_copy, codex_agent_plugin_reference_t, "remote")

codex_agent_status_t codex_agent_plugin_detail_summary(codex_agent_context_t *context, codex_agent_plugin_detail_t *detail, codex_agent_plugin_summary_t **out_summary) {
    (void)context; if (detail == NULL || out_summary == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_summary = calloc(1U, sizeof(**out_summary)); return *out_summary == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}
SIMPLE_COPY(codex_agent_plugin_detail_description_copy, codex_agent_plugin_detail_t, "native plugin detail")
SIMPLE_COUNT(codex_agent_plugin_detail_skills_count, codex_agent_plugin_detail_t, 0U)
SIMPLE_COUNT(codex_agent_plugin_detail_connectors_count, codex_agent_plugin_detail_t, 0U)
SIMPLE_COUNT(codex_agent_plugin_detail_mcp_servers_count, codex_agent_plugin_detail_t, 0U)
codex_agent_status_t codex_agent_plugin_detail_hook_count(codex_agent_context_t *context, codex_agent_plugin_detail_t *detail, int32_t *out_count) {
    (void)context; if (detail == NULL || out_count == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; *out_count = 0; return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_plugin_install_result_auth_policy(codex_agent_context_t *context, codex_agent_plugin_install_result_t *result, codex_agent_plugin_auth_policy_t *out_value) {
    (void)context; if (result == NULL || out_value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; *out_value = CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_USE; return CODEX_AGENT_STATUS_OK;
}
SIMPLE_COUNT(codex_agent_plugin_install_result_connectors_count, codex_agent_plugin_install_result_t, 1U)
codex_agent_status_t codex_agent_plugin_install_result_connectors_at(codex_agent_context_t *context, codex_agent_plugin_install_result_t *result, size_t index, codex_agent_connector_t **out_connector) {
    (void)context; if (result == NULL || index != 0U || out_connector == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_connector = calloc(1U, sizeof(**out_connector)); return *out_connector == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}
SIMPLE_BOOL(codex_agent_plugin_install_result_has_message, codex_agent_plugin_install_result_t, 1)
SIMPLE_COPY(codex_agent_plugin_install_result_message_copy, codex_agent_plugin_install_result_t, "installed")

#undef SIMPLE_COUNT
#undef SIMPLE_BOOL
#undef SIMPLE_COPY

#undef DEFINE_VALUE_DESTROY

codex_agent_status_t codex_agent_conversation_id_create(
    codex_agent_context_t *context,
    const codex_agent_string_view_t *value,
    codex_agent_conversation_id_t **out_id) {
    (void)context;
    if (value == NULL || out_id == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_id = calloc(1U, sizeof(**out_id));
    if (*out_id == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_id)->live = 1;
    if (view_equals(value, "delete-input")) (*out_id)->input_kind = 1;
    else if (view_equals(value, "read-input")) (*out_id)->input_kind = 2;
    else if (view_equals(value, "rename-input")) (*out_id)->input_kind = 3;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_conversations_list(
    codex_agent_context_t *context, codex_agent_conversations_t *conversations,
    codex_agent_operation_callback_t callback, void *user_data,
    codex_agent_operation_t **out_operation) {
    return COMPLETE_LEAF(conversations, LEAF_CONVERSATION_SUMMARIES);
}

codex_agent_status_t codex_agent_conversations_read(
    codex_agent_context_t *context, codex_agent_conversations_t *conversations,
    codex_agent_conversation_id_t *conversation_id,
    codex_agent_operation_callback_t callback, void *user_data,
    codex_agent_operation_t **out_operation) {
    if (conversation_id == NULL || conversation_id->input_kind != 2)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return COMPLETE_LEAF(conversations, LEAF_CONVERSATION_VALUE);
}

codex_agent_status_t codex_agent_conversations_rename(
    codex_agent_context_t *context, codex_agent_conversations_t *conversations,
    codex_agent_conversation_id_t *conversation_id, const codex_agent_string_view_t *name,
    codex_agent_operation_callback_t callback, void *user_data,
    codex_agent_operation_t **out_operation) {
    if (conversation_id == NULL || conversation_id->input_kind != 3 || !view_equals(name, "Renamed"))
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return COMPLETE_LEAF(conversations, LEAF_UNIT);
}

codex_agent_status_t codex_agent_conversations_delete(
    codex_agent_context_t *context, codex_agent_conversations_t *conversations,
    codex_agent_conversation_id_t *conversation_id,
    codex_agent_operation_callback_t callback, void *user_data,
    codex_agent_operation_t **out_operation) {
    if (conversation_id == NULL || conversation_id->input_kind != 1)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return COMPLETE_LEAF(conversations, LEAF_UNIT);
}

codex_agent_status_t codex_agent_operation_conversation_summaries_count(
    codex_agent_context_t *context, codex_agent_operation_t *operation, size_t *out_count) {
    (void)context;
    if (operation == NULL || operation->leaf_kind != LEAF_CONVERSATION_SUMMARIES || out_count == NULL)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_count = 3U;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_operation_conversation_summary_at(
    codex_agent_context_t *context, codex_agent_operation_t *operation, size_t index,
    codex_agent_conversation_summary_t **out_summary) {
    (void)context;
    if (operation == NULL || operation->leaf_kind != LEAF_CONVERSATION_SUMMARIES ||
        index >= 3U || out_summary == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_summary = calloc(1U, sizeof(**out_summary));
    if (*out_summary == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_summary)->index = (int)index;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_operation_conversation_value(
    codex_agent_context_t *context, codex_agent_operation_t *operation,
    codex_agent_conversation_value_t **out_conversation) {
    (void)context;
    if (operation == NULL || operation->leaf_kind != LEAF_CONVERSATION_VALUE || out_conversation == NULL)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_conversation = calloc(1U, sizeof(**out_conversation));
    return *out_conversation == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_conversation_summary_destroy(
    codex_agent_context_t *context, codex_agent_conversation_summary_t **summary) {
    (void)context; if (summary == NULL || *summary == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    free(*summary); *summary = NULL; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_conversation_summary_conversation_id(
    codex_agent_context_t *context, codex_agent_conversation_summary_t *summary,
    codex_agent_conversation_id_t **out_id) {
    (void)context; if (summary == NULL || out_id == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_id = calloc(1U, sizeof(**out_id));
    if (*out_id == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_id)->live = summary->index == 1 ? 2 : 1;
    return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_conversation_summary_title_copy(
    codex_agent_context_t *context, codex_agent_conversation_summary_t *summary,
    uint8_t *buffer, size_t capacity, size_t *out_required) {
    (void)context;
    if (summary == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return copy_string(summary->index == 1 ? "Beta" : "Alpha", buffer, capacity, out_required);
}
codex_agent_status_t codex_agent_conversation_summary_updated_at_epoch_seconds(
    codex_agent_context_t *context, codex_agent_conversation_summary_t *summary,
    int64_t *out_value) {
    (void)context; if (summary == NULL || out_value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_value = summary->index == 1 ? 22 : 11; return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_conversation_value_destroy(
    codex_agent_context_t *context, codex_agent_conversation_value_t **conversation) {
    (void)context; if (conversation == NULL || *conversation == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    free(*conversation); *conversation = NULL; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_conversation_value_summary(
    codex_agent_context_t *context, codex_agent_conversation_value_t *conversation,
    codex_agent_conversation_summary_t **out_summary) {
    (void)context; if (conversation == NULL || out_summary == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_summary = calloc(1U, sizeof(**out_summary));
    return *out_summary == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_conversation_value_messages_count(
    codex_agent_context_t *context, codex_agent_conversation_value_t *conversation, size_t *out_count) {
    (void)context; if (conversation == NULL || out_count == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_count = 3U; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_conversation_value_message_at(
    codex_agent_context_t *context, codex_agent_conversation_value_t *conversation, size_t index,
    codex_agent_message_t **out_message) {
    (void)context; if (conversation == NULL || index >= 3U || out_message == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_message = calloc(1U, sizeof(**out_message));
    if (*out_message == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_message)->index = index == 1U ? 1 : 0;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_message_destroy(codex_agent_context_t *context, codex_agent_message_t **message) {
    (void)context; if (message == NULL || *message == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    free(*message); *message = NULL; return CODEX_AGENT_STATUS_OK;
}
static const char *message_text(codex_agent_message_t *message, const char *alpha, const char *beta, const char *gamma, const char *delta) {
    if (message->index == 1) return beta;
    if (message->index == 2) return gamma;
    if (message->index == 3) return delta;
    return alpha;
}
#define MESSAGE_COPY(symbol, alpha, beta, gamma, delta) \
codex_agent_status_t symbol(codex_agent_context_t *context, codex_agent_message_t *message, \
    uint8_t *buffer, size_t capacity, size_t *out_required) { \
    (void)context; if (message == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; \
    return copy_string(message_text(message, (alpha), (beta), (gamma), (delta)), buffer, capacity, out_required); \
}
MESSAGE_COPY(codex_agent_message_id_copy, "message-alpha", "message-beta", "message-gamma", "message-delta")
MESSAGE_COPY(codex_agent_message_client_message_id_copy, "client-alpha", "client-beta", "client-gamma", "client-delta")
MESSAGE_COPY(codex_agent_message_text_copy, "hello-alpha", "hello-beta", "hello-gamma", "hello-delta")
MESSAGE_COPY(codex_agent_message_reasoning_copy, "reason-alpha", "reason-beta", "reason-gamma", "reason-delta")
MESSAGE_COPY(codex_agent_message_plan_copy, "plan-alpha", "plan-beta", "plan-gamma", "plan-delta")
MESSAGE_COPY(codex_agent_message_shell_command_copy, "pwd-alpha", "pwd-beta", "pwd-gamma", "pwd-delta")
#undef MESSAGE_COPY
#define MESSAGE_BOOL(symbol) \
codex_agent_status_t symbol(codex_agent_context_t *context, codex_agent_message_t *message, int32_t *out_value) { \
    (void)context; if (message == NULL || out_value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; \
    *out_value = 1; return CODEX_AGENT_STATUS_OK; \
}
MESSAGE_BOOL(codex_agent_message_has_client_message_id)
MESSAGE_BOOL(codex_agent_message_has_reasoning)
MESSAGE_BOOL(codex_agent_message_has_plan)
MESSAGE_BOOL(codex_agent_message_has_shell_command)
#undef MESSAGE_BOOL
codex_agent_status_t codex_agent_message_role(codex_agent_context_t *context, codex_agent_message_t *message, codex_agent_message_role_t *out_role) {
    (void)context; if (message == NULL || out_role == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_role = CODEX_AGENT_MESSAGE_ROLE_ASSISTANT; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_message_collaboration_mode(codex_agent_context_t *context, codex_agent_message_t *message, codex_agent_collaboration_mode_t *out_mode) {
    (void)context; if (message == NULL || out_mode == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_mode = CODEX_AGENT_COLLABORATION_MODE_PLAN; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_message_exit_code(codex_agent_context_t *context, codex_agent_message_t *message, int32_t *out_has, int32_t *out_value) {
    (void)context; if (message == NULL || out_has == NULL || out_value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_has = 1; *out_value = message->index == 1 ? 8 : 7; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_message_capabilities_count(codex_agent_context_t *context, codex_agent_message_t *message, size_t *out_count) {
    (void)context; if (message == NULL || out_count == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_count = 1U; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_message_has_capability(codex_agent_context_t *context, codex_agent_message_t *message, codex_agent_capability_t capability, int32_t *out_has) {
    (void)context; if (message == NULL || out_has == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_has = capability == CODEX_AGENT_CAPABILITY_WEB_SEARCH ? 1 : 0; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_message_invocations_count(codex_agent_context_t *context, codex_agent_message_t *message, size_t *out_count) {
    (void)context; if (message == NULL || out_count == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_count = 2U; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_message_invocation_at(codex_agent_context_t *context, codex_agent_message_t *message, size_t index, codex_agent_invocation_t **out_invocation) {
    (void)context; if (message == NULL || index >= 2U || out_invocation == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_invocation = calloc(1U, sizeof(**out_invocation));
    if (*out_invocation == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_invocation)->kind = (int)index; (*out_invocation)->valid = 1; return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_invocation_destroy(codex_agent_context_t *context, codex_agent_invocation_t **invocation) {
    (void)context; if (invocation == NULL || *invocation == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    free(*invocation); *invocation = NULL; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_invocation_kind(codex_agent_context_t *context, codex_agent_invocation_t *invocation, codex_agent_invocation_kind_t *out_kind) {
    (void)context; if (invocation == NULL || out_kind == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_kind = invocation->kind; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_invocation_plugin(codex_agent_context_t *context, codex_agent_invocation_t *invocation, codex_agent_invocation_plugin_t **out_plugin) {
    (void)context; if (invocation == NULL || invocation->kind != CODEX_AGENT_INVOCATION_KIND_PLUGIN || out_plugin == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_plugin = calloc(1U, sizeof(**out_plugin));
    if (*out_plugin == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_plugin)->valid = invocation->valid; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_invocation_skill(codex_agent_context_t *context, codex_agent_invocation_t *invocation, codex_agent_invocation_skill_t **out_skill) {
    (void)context; if (invocation == NULL || invocation->kind != CODEX_AGENT_INVOCATION_KIND_SKILL || out_skill == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_skill = calloc(1U, sizeof(**out_skill));
    if (*out_skill == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_skill)->valid = invocation->valid; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_invocation_plugin_create(codex_agent_context_t *context, const codex_agent_string_view_t *name, const codex_agent_string_view_t *uri, codex_agent_invocation_plugin_t **out_plugin) {
    (void)context; if (name == NULL || uri == NULL || out_plugin == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_plugin = calloc(1U, sizeof(**out_plugin));
    if (*out_plugin == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_plugin)->valid = view_equals(name, "plugin") && view_equals(uri, "plugin://plugin@market");
    return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_invocation_plugin_destroy(codex_agent_context_t *context, codex_agent_invocation_plugin_t **plugin) {
    (void)context; if (plugin == NULL || *plugin == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    free(*plugin); *plugin = NULL; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_invocation_plugin_name_copy(codex_agent_context_t *context, codex_agent_invocation_plugin_t *plugin, uint8_t *buffer, size_t capacity, size_t *out_required) {
    (void)context; if (plugin == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return copy_string("plugin", buffer, capacity, out_required);
}
codex_agent_status_t codex_agent_invocation_plugin_uri_copy(codex_agent_context_t *context, codex_agent_invocation_plugin_t *plugin, uint8_t *buffer, size_t capacity, size_t *out_required) {
    (void)context; if (plugin == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return copy_string("plugin://plugin@market", buffer, capacity, out_required);
}
codex_agent_status_t codex_agent_invocation_skill_create(codex_agent_context_t *context, const codex_agent_string_view_t *name, const codex_agent_string_view_t *path, codex_agent_invocation_skill_t **out_skill) {
    (void)context; if (name == NULL || path == NULL || out_skill == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_skill = calloc(1U, sizeof(**out_skill));
    if (*out_skill == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_skill)->valid = view_equals(name, "skill") && view_equals(path, "skill.md");
    return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_invocation_skill_destroy(codex_agent_context_t *context, codex_agent_invocation_skill_t **skill) {
    (void)context; if (skill == NULL || *skill == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    free(*skill); *skill = NULL; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_invocation_skill_name_copy(codex_agent_context_t *context, codex_agent_invocation_skill_t *skill, uint8_t *buffer, size_t capacity, size_t *out_required) {
    (void)context; if (skill == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return copy_string("skill", buffer, capacity, out_required);
}
codex_agent_status_t codex_agent_invocation_skill_path_copy(codex_agent_context_t *context, codex_agent_invocation_skill_t *skill, uint8_t *buffer, size_t capacity, size_t *out_required) {
    (void)context; if (skill == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return copy_string("skill.md", buffer, capacity, out_required);
}
codex_agent_status_t codex_agent_invocation_from_plugin(codex_agent_context_t *context, codex_agent_invocation_plugin_t *plugin, codex_agent_invocation_t **out_invocation) {
    (void)context; if (plugin == NULL || out_invocation == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_invocation = calloc(1U, sizeof(**out_invocation));
    if (*out_invocation == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_invocation)->kind = CODEX_AGENT_INVOCATION_KIND_PLUGIN; (*out_invocation)->valid = plugin->valid;
    return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_invocation_from_skill(codex_agent_context_t *context, codex_agent_invocation_skill_t *skill, codex_agent_invocation_t **out_invocation) {
    (void)context; if (skill == NULL || out_invocation == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_invocation = calloc(1U, sizeof(**out_invocation));
    if (*out_invocation == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_invocation)->kind = CODEX_AGENT_INVOCATION_KIND_SKILL; (*out_invocation)->valid = skill->valid;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_turn_request_create(
    codex_agent_context_t *context, const codex_agent_string_view_t *prompt,
    int32_t has_client_message_id, const codex_agent_string_view_t *client_message_id,
    int32_t has_model, const codex_agent_string_view_t *model,
    int32_t has_effort, const codex_agent_string_view_t *effort,
    int32_t has_service_tier, const codex_agent_string_view_t *service_tier,
    codex_agent_approval_preset_t approval_preset,
    const codex_agent_capability_t *capabilities, size_t capability_count,
    codex_agent_invocation_t *const *invocations, size_t invocation_count,
    codex_agent_collaboration_mode_t collaboration_mode,
    codex_agent_turn_request_t **out_request) {
    (void)context; if (prompt == NULL || out_request == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_request = calloc(1U, sizeof(**out_request));
    if (*out_request == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_request)->valid = view_equals(prompt, "structured") && has_client_message_id == 1 &&
        view_equals(client_message_id, "client-1") && has_model == 1 && view_equals(model, "model") &&
        has_effort == 1 && view_equals(effort, "high") && has_service_tier == 1 &&
        view_equals(service_tier, "fast") && approval_preset == CODEX_AGENT_APPROVAL_PRESET_ASK_ME &&
        capability_count == 1U && capabilities != NULL && capabilities[0] == CODEX_AGENT_CAPABILITY_WEB_SEARCH &&
        invocation_count == 2U && invocations != NULL && invocations[0] != NULL && invocations[1] != NULL &&
        invocations[0]->kind == CODEX_AGENT_INVOCATION_KIND_PLUGIN && invocations[0]->valid &&
        invocations[1]->kind == CODEX_AGENT_INVOCATION_KIND_SKILL && invocations[1]->valid &&
        collaboration_mode == CODEX_AGENT_COLLABORATION_MODE_PLAN;
    return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_turn_request_destroy(codex_agent_context_t *context, codex_agent_turn_request_t **request) {
    (void)context; if (request == NULL || *request == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    free(*request); *request = NULL; return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_conversations_release(
    codex_agent_context_t *context,
    codex_agent_conversations_t **conversations) {
    (void)context;
    if ((*conversations)->release_attempts++ == 0) return CODEX_AGENT_STATUS_BUSY;
    (*conversations)->released = 1;
    *conversations = NULL;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_conversations_active_get(
    codex_agent_context_t *context,
    codex_agent_conversations_t *conversations,
    codex_agent_snapshot_t **out_snapshot) {
    (void)context;
    *out_snapshot = calloc(1U, sizeof(**out_snapshot));
    if (*out_snapshot == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_snapshot)->value = conversations->active;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_conversations_active_subscribe(
    codex_agent_context_t *context,
    codex_agent_conversations_t *conversations,
    codex_agent_state_callback_t callback,
    void *user_data,
    codex_agent_subscription_t **out_subscription) {
    codex_agent_snapshot_t *snapshot = NULL;
    *out_subscription = calloc(1U, sizeof(**out_subscription));
    if (*out_subscription == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_subscription)->conversations = conversations;
    (*out_subscription)->callback = callback;
    (*out_subscription)->user_data = user_data;
    (*out_subscription)->context = context;
    pending_active_subscription = *out_subscription;
    codex_agent_conversations_active_get(context, conversations, &snapshot);
    callback(context, *out_subscription, CODEX_AGENT_STATUS_OK, snapshot, 0, user_data);
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_test_advance_active_subscription(codex_agent_context_t *context) {
    codex_agent_subscription_t *subscription = pending_active_subscription;
    codex_agent_snapshot_t *snapshot = NULL;
    (void)context;
    if (subscription == NULL || subscription->callback == NULL)
        return CODEX_AGENT_STATUS_NOT_READY;
    context = subscription->context;
    pending_active_subscription = NULL;
    if (subscription->conversations->active != NULL) {
        subscription->conversations->active->state = CODEX_AGENT_CONVERSATION_STATUS_CLOSED;
        subscription->conversations->active = NULL;
    }
    snapshot = calloc(1U, sizeof(*snapshot));
    if (snapshot == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    subscription->callback(context, subscription, CODEX_AGENT_STATUS_OK, snapshot, 0, subscription->user_data);
    subscription->callback(context, subscription, CODEX_AGENT_STATUS_OK, NULL, 1, subscription->user_data);
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_active_conversation(
    codex_agent_context_t *context,
    codex_agent_conversations_t *conversations,
    codex_agent_snapshot_t *snapshot,
    codex_agent_conversation_t **out_conversation) {
    (void)context;
    (void)conversations;
    if (snapshot->value == NULL) {
        *out_conversation = NULL;
        return CODEX_AGENT_STATUS_OK;
    }
    *out_conversation = calloc(1U, sizeof(**out_conversation));
    if (*out_conversation == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_conversation)->entity = snapshot->value;
    (*out_conversation)->entity->handle_count += 1;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_conversations_open(
    codex_agent_context_t *context,
    codex_agent_conversations_t *conversations,
    const codex_agent_conversation_open_options_t *options,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation) {
    codex_agent_status_t status;
    if (options == NULL || options->struct_size != sizeof(*options))
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (options->has_conversation_id != 0 && view_equals(&options->conversation_id, "conversation-open") &&
        (options->has_approval_preset != 1 || options->approval_preset != CODEX_AGENT_APPROVAL_PRESET_ASK_ME ||
         options->has_service_tier != 1 || !view_equals(&options->service_tier, "fast")))
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (options->has_conversation_id != 0 && view_equals(&options->conversation_id, "wrong-open"))
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    status = complete_operation(context, NULL, user_data, CODEX_AGENT_STATUS_OK, out_operation);
    if (status != CODEX_AGENT_STATUS_OK) return status;
    if (conversations->active != NULL)
        conversations->active->state = CODEX_AGENT_CONVERSATION_STATUS_CLOSED;
    conversations->active = calloc(1U, sizeof(*conversations->active));
    if (conversations->active == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    conversations->active->state = CODEX_AGENT_CONVERSATION_STATUS_READY;
    conversations->active->owner = conversations;
    conversations->active->release_status = CODEX_AGENT_STATUS_OK;
    if (options->has_conversation_id != 0 && options->conversation_id.size == 12U &&
        memcmp(options->conversation_id.data, "release-busy", 12U) == 0)
        conversations->active->release_status = CODEX_AGENT_STATUS_BUSY;
    if (options->has_conversation_id != 0 && options->conversation_id.size == 13U &&
        memcmp(options->conversation_id.data, "release-error", 13U) == 0)
        conversations->active->release_status = CODEX_AGENT_STATUS_INTERNAL_ERROR;
    (*out_operation)->conversation = conversations->active;
    (*out_operation)->callback = callback;
    if (callback != NULL) callback(context, *out_operation, user_data);
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_operation_conversation(
    codex_agent_context_t *context,
    codex_agent_conversations_t *conversations,
    codex_agent_operation_t *operation,
    codex_agent_conversation_t **out_conversation) {
    (void)context;
    (void)conversations;
    *out_conversation = calloc(1U, sizeof(**out_conversation));
    if (*out_conversation == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_conversation)->entity = operation->conversation;
    (*out_conversation)->entity->handle_count += 1;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_conversation_release(
    codex_agent_context_t *context,
    codex_agent_conversation_t **conversation) {
    (void)context;
    if ((*conversation)->entity->release_status != CODEX_AGENT_STATUS_OK)
        return (*conversation)->entity->release_status;
    if ((*conversation)->entity->state != CODEX_AGENT_CONVERSATION_STATUS_CLOSED &&
        (*conversation)->entity->handle_count == 1)
        return CODEX_AGENT_STATUS_BUSY;
    (*conversation)->entity->handle_count -= 1;
    free(*conversation);
    *conversation = NULL;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_conversation_is_same(
    codex_agent_context_t *context,
    codex_agent_conversation_t *left,
    codex_agent_conversation_t *right,
    int32_t *out_same) {
    (void)context;
    *out_same = left->entity == right->entity ? 1 : 0;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_conversation_send(
    codex_agent_context_t *context,
    codex_agent_conversation_t *conversation,
    const codex_agent_string_view_t *prompt,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation) {
    (void)conversation;
    if (prompt == NULL || prompt->size == 0U) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (view_equals(prompt, "wrong-input")) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (prompt->size == 4U && memcmp(prompt->data, "fail", 4U) == 0)
        return complete_operation(context, callback, user_data, CODEX_AGENT_STATUS_OPERATION_FAILED, out_operation);
    return complete_operation(context, callback, user_data, CODEX_AGENT_STATUS_OK, out_operation);
}

codex_agent_status_t codex_agent_conversation_send_request(
    codex_agent_context_t *context, codex_agent_conversation_t *conversation,
    codex_agent_turn_request_t *request, codex_agent_operation_callback_t callback,
    void *user_data, codex_agent_operation_t **out_operation) {
    if (conversation == NULL || request == NULL || !request->valid) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return COMPLETE_LEAF(conversation, LEAF_UNIT);
}

codex_agent_status_t codex_agent_conversation_reload(
    codex_agent_context_t *context,
    codex_agent_conversation_t *conversation,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation) {
    (void)conversation;
    if (live_operations != 0) return CODEX_AGENT_STATUS_INTERNAL_ERROR;
    return complete_operation(context, callback, user_data, CODEX_AGENT_STATUS_OK, out_operation);
}

codex_agent_status_t codex_agent_conversation_run_shell_command(
    codex_agent_context_t *context,
    codex_agent_conversation_t *conversation,
    const codex_agent_string_view_t *command,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation) {
    if (conversation == NULL || command == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (view_equals(command, "pwd")) return COMPLETE_LEAF(conversation, LEAF_UNIT);
    if (view_equals(command, "wrong-shell")) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_operation = calloc(1U, sizeof(**out_operation));
    if (*out_operation == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    live_operations += 1;
    (*out_operation)->result = CODEX_AGENT_STATUS_OK;
    (*out_operation)->callback = callback;
    (*out_operation)->user_data = user_data;
    (*out_operation)->cancel_status =
        command->size == 12U && memcmp(command->data, "cancel-error", 12U) == 0
            ? CODEX_AGENT_STATUS_INTERNAL_ERROR
            : CODEX_AGENT_STATUS_OK;
    (*out_operation)->conversation = conversation->entity;
    (*out_operation)->require_conversation_owner = 1;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_conversation_cancel_turn(
    codex_agent_context_t *context,
    codex_agent_conversation_t *conversation,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation) {
    (void)conversation;
    return complete_operation(context, callback, user_data, CODEX_AGENT_STATUS_OK, out_operation);
}

codex_agent_status_t codex_agent_conversation_close(
    codex_agent_context_t *context,
    codex_agent_conversation_t *conversation,
    codex_agent_operation_callback_t callback,
    void *user_data,
    codex_agent_operation_t **out_operation) {
    conversation->entity->state = CODEX_AGENT_CONVERSATION_STATUS_CLOSED;
    if (conversation->entity->owner->active == conversation->entity)
        conversation->entity->owner->active = NULL;
    return complete_operation(context, callback, user_data, CODEX_AGENT_STATUS_OK, out_operation);
}

codex_agent_status_t codex_agent_conversation_state_get(
    codex_agent_context_t *context,
    codex_agent_conversation_t *conversation,
    codex_agent_snapshot_t **out_snapshot) {
    (void)context;
    *out_snapshot = calloc(1U, sizeof(**out_snapshot));
    if (*out_snapshot == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_snapshot)->kind = conversation->entity->state;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_conversation_state_subscribe(
    codex_agent_context_t *context,
    codex_agent_conversation_t *conversation,
    codex_agent_state_callback_t callback,
    void *user_data,
    codex_agent_subscription_t **out_subscription) {
    codex_agent_snapshot_t *snapshot = NULL;
    *out_subscription = calloc(1U, sizeof(**out_subscription));
    if (*out_subscription == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_subscription)->conversation = conversation->entity;
    codex_agent_conversation_state_get(context, conversation, &snapshot);
    callback(context, *out_subscription, CODEX_AGENT_STATUS_OK, snapshot, 0, user_data);
    snapshot = calloc(1U, sizeof(*snapshot));
    if (snapshot == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    snapshot->kind = CODEX_AGENT_CONVERSATION_STATUS_CANCELLING_TURN;
    callback(context, *out_subscription, CODEX_AGENT_STATUS_OK, snapshot, 0, user_data);
    callback(context, *out_subscription, CODEX_AGENT_STATUS_OK, NULL, 1, user_data);
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_conversation_state_status(
    codex_agent_context_t *context,
    codex_agent_snapshot_t *snapshot,
    codex_agent_conversation_status_t *out_status) {
    (void)context;
    *out_status = snapshot->kind;
    return CODEX_AGENT_STATUS_OK;
}

static codex_agent_status_t conversation_projection_get(
    codex_agent_conversation_t *conversation, int kind, codex_agent_snapshot_t **out_snapshot) {
    if (conversation == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return leaf_snapshot(kind, out_snapshot);
}

static codex_agent_status_t conversation_projection_subscribe(
    codex_agent_context_t *context, codex_agent_conversation_t *conversation, int current_kind, int subsequent_kind,
    codex_agent_state_callback_t callback, void *user_data, codex_agent_subscription_t **out_subscription) {
    codex_agent_snapshot_t *snapshot = NULL;
    if (context == NULL || conversation == NULL || callback == NULL || out_subscription == NULL)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_subscription = calloc(1U, sizeof(**out_subscription));
    if (*out_subscription == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_subscription)->conversation = conversation->entity;
    if (leaf_snapshot(current_kind, &snapshot) != CODEX_AGENT_STATUS_OK) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    callback(context, *out_subscription, CODEX_AGENT_STATUS_OK, snapshot, 0, user_data);
    if (leaf_snapshot(subsequent_kind, &snapshot) != CODEX_AGENT_STATUS_OK) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    callback(context, *out_subscription, CODEX_AGENT_STATUS_OK, snapshot, 0, user_data);
    callback(context, *out_subscription, CODEX_AGENT_STATUS_OK, NULL, 1, user_data);
    return CODEX_AGENT_STATUS_OK;
}

#define CONVERSATION_PROJECTION(name, current_kind, subsequent_kind) \
codex_agent_status_t codex_agent_conversation_##name##_get(codex_agent_context_t *context, codex_agent_conversation_t *conversation, codex_agent_snapshot_t **out_snapshot) { \
    (void)context; return conversation_projection_get(conversation, (current_kind), out_snapshot); \
} \
codex_agent_status_t codex_agent_conversation_##name##_subscribe(codex_agent_context_t *context, codex_agent_conversation_t *conversation, codex_agent_state_callback_t callback, void *user_data, codex_agent_subscription_t **out_subscription) { \
    return conversation_projection_subscribe(context, conversation, (current_kind), (subsequent_kind), callback, user_data, out_subscription); \
}

CONVERSATION_PROJECTION(current_messages, 50, 51)
CONVERSATION_PROJECTION(active_turn_progress, 60, 61)
CONVERSATION_PROJECTION(can_start_turn, 1, 0)
CONVERSATION_PROJECTION(can_reload, 1, 0)
CONVERSATION_PROJECTION(can_cancel_turn, 1, 0)
CONVERSATION_PROJECTION(can_run_shell_command, 1, 0)
CONVERSATION_PROJECTION(is_turn_active, 1, 0)
#undef CONVERSATION_PROJECTION

codex_agent_status_t codex_agent_conversation_current_messages_count(
    codex_agent_context_t *context, codex_agent_snapshot_t *snapshot, size_t *out_count) {
    (void)context; if (snapshot == NULL || out_count == NULL || (snapshot->kind != 50 && snapshot->kind != 51))
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_count = 3U; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_conversation_current_messages_at(
    codex_agent_context_t *context, codex_agent_snapshot_t *snapshot, size_t index,
    codex_agent_message_t **out_message) {
    (void)context; if (snapshot == NULL || index >= 3U || out_message == NULL ||
        (snapshot->kind != 50 && snapshot->kind != 51)) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_message = calloc(1U, sizeof(**out_message));
    if (*out_message == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    if (snapshot->kind == 50) (*out_message)->index = index == 1U ? 1 : 0;
    else (*out_message)->index = index == 1U ? 3 : 2;
    return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_conversation_active_turn_progress_has_value(
    codex_agent_context_t *context, codex_agent_snapshot_t *snapshot, int32_t *out_has) {
    (void)context; if (snapshot == NULL || out_has == NULL || (snapshot->kind != 60 && snapshot->kind != 61))
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_has = snapshot->kind == 60 ? 1 : 0; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_conversation_active_turn_progress_value(
    codex_agent_context_t *context, codex_agent_snapshot_t *snapshot, codex_agent_turn_progress_t **out_progress) {
    (void)context; if (snapshot == NULL || snapshot->kind != 60 || out_progress == NULL)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_progress = calloc(1U, sizeof(**out_progress));
    return *out_progress == NULL ? CODEX_AGENT_STATUS_OUT_OF_MEMORY : CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_turn_progress_destroy(codex_agent_context_t *context, codex_agent_turn_progress_t **progress) {
    (void)context; if (progress == NULL || *progress == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    free(*progress); *progress = NULL; return CODEX_AGENT_STATUS_OK;
}
#define PROGRESS_COPY(symbol, value) \
codex_agent_status_t symbol(codex_agent_context_t *context, codex_agent_turn_progress_t *progress, uint8_t *buffer, size_t capacity, size_t *out_required) { \
    (void)context; if (progress == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; \
    return copy_string((value), buffer, capacity, out_required); \
}
PROGRESS_COPY(codex_agent_turn_progress_text_copy, "working")
PROGRESS_COPY(codex_agent_turn_progress_commentary_copy, "commentary")
PROGRESS_COPY(codex_agent_turn_progress_reasoning_copy, "reasoning")
PROGRESS_COPY(codex_agent_turn_progress_plan_copy, "plan")
PROGRESS_COPY(codex_agent_turn_progress_shell_output_copy, "output")
#undef PROGRESS_COPY
codex_agent_status_t codex_agent_turn_progress_has_plan_progress(codex_agent_context_t *context, codex_agent_turn_progress_t *progress, int32_t *out_present) {
    (void)context; if (progress == NULL || out_present == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_present = 0; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_turn_progress_shell_exit_code(codex_agent_context_t *context, codex_agent_turn_progress_t *progress, int32_t *out_present, int32_t *out_value) {
    (void)context; if (progress == NULL || out_present == NULL || out_value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_present = 1; *out_value = 0; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_turn_progress_work_activity(codex_agent_context_t *context, codex_agent_turn_progress_t *progress, int32_t *out_present, codex_agent_work_activity_t *out_value) {
    (void)context; if (progress == NULL || out_present == NULL || out_value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_present = 1; *out_value = CODEX_AGENT_WORK_ACTIVITY_RUNNING_COMMAND; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_turn_progress_hook_activities_count(codex_agent_context_t *context, codex_agent_turn_progress_t *progress, size_t *out_count) {
    (void)context; if (progress == NULL || out_count == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_count = 0U; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_turn_progress_is_truncated(codex_agent_context_t *context, codex_agent_turn_progress_t *progress, int32_t *out_value) {
    (void)context; if (progress == NULL || out_value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_value = 1; return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_operation_cancel(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation) {
    operation->result = CODEX_AGENT_STATUS_CANCELLED;
    if (pending_leaf_operation == operation) pending_leaf_operation = NULL;
    if (pending_host_operation == operation) pending_host_operation = NULL;
    if (operation->callback != NULL)
        operation->callback(context, operation, operation->user_data);
    return operation->cancel_status;
}

codex_agent_status_t codex_agent_operation_result(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    codex_agent_status_t *out_result) {
    (void)context;
    *out_result = operation->result;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_operation_failure(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    codex_agent_failure_t **out_failure) {
    (void)context;
    if (operation->result != CODEX_AGENT_STATUS_OPERATION_FAILED)
        return CODEX_AGENT_STATUS_NOT_READY;
    *out_failure = calloc(1U, sizeof(**out_failure));
    if (*out_failure == NULL) return CODEX_AGENT_STATUS_OUT_OF_MEMORY;
    (*out_failure)->code = "test_failure";
    (*out_failure)->message = "expected failure";
    (*out_failure)->recoverable = 1;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_operation_destroy(
    codex_agent_context_t *context,
    codex_agent_operation_t **operation) {
    (void)context;
    if ((*operation)->destroy_attempts++ == 0) return CODEX_AGENT_STATUS_BUSY;
    if ((*operation)->require_conversation_owner != 0 &&
        (*operation)->conversation->handle_count == 0)
        return CODEX_AGENT_STATUS_INTERNAL_ERROR;
    if ((*operation)->leaf_service != NULL &&
        ((codex_agent_authentication_t *)(*operation)->leaf_service)->released != 0)
        return CODEX_AGENT_STATUS_INTERNAL_ERROR;
    free(*operation);
    *operation = NULL;
    live_operations -= 1;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_subscription_destroy(
    codex_agent_context_t *context,
    codex_agent_subscription_t **subscription) {
    (void)context;
    if ((*subscription)->destroy_attempts++ == 0) return CODEX_AGENT_STATUS_BUSY;
    if ((*subscription)->host != NULL && (*subscription)->host->released != 0)
        return CODEX_AGENT_STATUS_INTERNAL_ERROR;
    if ((*subscription)->conversations != NULL && (*subscription)->conversations->released != 0)
        return CODEX_AGENT_STATUS_INTERNAL_ERROR;
    if ((*subscription)->conversation != NULL && (*subscription)->conversation->handle_count == 0)
        return CODEX_AGENT_STATUS_INTERNAL_ERROR;
    if ((*subscription)->leaf_service != NULL &&
        ((codex_agent_authentication_t *)(*subscription)->leaf_service)->released != 0)
        return CODEX_AGENT_STATUS_INTERNAL_ERROR;
    if (pending_active_subscription == *subscription) pending_active_subscription = NULL;
    if (pending_host_subscription == *subscription) pending_host_subscription = NULL;
    free(*subscription);
    *subscription = NULL;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_snapshot_destroy(
    codex_agent_context_t *context,
    codex_agent_snapshot_t **snapshot) {
    (void)context;
    free(*snapshot);
    *snapshot = NULL;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_failure_release(
    codex_agent_context_t *context,
    codex_agent_failure_t **failure) {
    (void)context;
    free(*failure);
    *failure = NULL;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_failure_code_copy(
    codex_agent_context_t *context,
    codex_agent_failure_t *failure,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required) {
    (void)context;
    return copy_string(failure->code, buffer, capacity, out_required);
}

codex_agent_status_t codex_agent_failure_message_copy(
    codex_agent_context_t *context,
    codex_agent_failure_t *failure,
    uint8_t *buffer,
    size_t capacity,
    size_t *out_required) {
    (void)context;
    return copy_string(failure->message, buffer, capacity, out_required);
}

codex_agent_status_t codex_agent_failure_is_recoverable(
    codex_agent_context_t *context,
    codex_agent_failure_t *failure,
    int32_t *out_is_recoverable) {
    (void)context;
    *out_is_recoverable = failure->recoverable;
    return CODEX_AGENT_STATUS_OK;
}
