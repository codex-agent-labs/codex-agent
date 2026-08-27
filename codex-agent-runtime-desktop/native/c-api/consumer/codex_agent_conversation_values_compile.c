#include "codex_agent.h"

#include <string.h>

#define CHECK(condition)       \
    do {                       \
        if (!(condition)) {    \
            return __LINE__;   \
        }                      \
    } while (0)

#define CHECK_HANDLE_COPY(function, context, handle, expected)                    \
    do {                                                                           \
        uint8_t copy_buffer[128];                                                   \
        size_t copy_required = SIZE_MAX;                                            \
        CHECK(                                                                      \
            function(                                                               \
                (context),                                                          \
                (handle),                                                           \
                copy_buffer,                                                        \
                sizeof(copy_buffer),                                                \
                &copy_required) == CODEX_AGENT_STATUS_OK);                          \
        CHECK(copy_required == strlen(expected));                                   \
        CHECK(memcmp(copy_buffer, (expected), copy_required) == 0);                 \
    } while (0)

_Static_assert(CODEX_AGENT_APPROVAL_PRESET_NEVER == INT32_C(0), "approval never");
_Static_assert(
    CODEX_AGENT_APPROVAL_PRESET_AUTO_REVIEW == INT32_C(1),
    "approval auto review");
_Static_assert(CODEX_AGENT_APPROVAL_PRESET_ASK_ME == INT32_C(2), "approval ask me");
_Static_assert(CODEX_AGENT_APPROVAL_PRESET_STRICT == INT32_C(3), "approval strict");
_Static_assert(
    CODEX_AGENT_WORKSPACE_REASON_NOT_SELECTED == INT32_C(0),
    "workspace not selected");
_Static_assert(
    CODEX_AGENT_WORKSPACE_REASON_NOT_FOUND == INT32_C(1),
    "workspace not found");
_Static_assert(
    CODEX_AGENT_WORKSPACE_REASON_ACCESS_REVOKED == INT32_C(2),
    "workspace access revoked");
_Static_assert(
    CODEX_AGENT_WORKSPACE_REASON_INVALID_SELECTION == INT32_C(3),
    "workspace invalid selection");

static codex_agent_string_view_t string_view(const char *value) {
    codex_agent_string_view_t view;
    view.data = (const uint8_t *)value;
    view.size = strlen(value);
    return view;
}

static int validate_approval_presets(void) {
    const codex_agent_approval_preset_t presets[] = {
        CODEX_AGENT_APPROVAL_PRESET_NEVER,
        CODEX_AGENT_APPROVAL_PRESET_AUTO_REVIEW,
        CODEX_AGENT_APPROVAL_PRESET_ASK_ME,
        CODEX_AGENT_APPROVAL_PRESET_STRICT};
    const char *display_names[] = {"Never", "Auto review", "Ask me", "Strict"};
    size_t index;

    for (index = 0U; index < sizeof(presets) / sizeof(presets[0]); ++index) {
        uint8_t buffer[32];
        size_t required = SIZE_MAX;
        CHECK(
            codex_agent_approval_preset_display_name_copy(
                presets[index],
                buffer,
                sizeof(buffer),
                &required) == CODEX_AGENT_STATUS_OK);
        CHECK(required == strlen(display_names[index]));
        CHECK(memcmp(buffer, display_names[index], required) == 0);
    }
    return 0;
}

static int validate_workspace_reasons(codex_agent_context_t *context) {
    const codex_agent_workspace_selection_reason_t reasons[] = {
        CODEX_AGENT_WORKSPACE_REASON_NOT_SELECTED,
        CODEX_AGENT_WORKSPACE_REASON_NOT_FOUND,
        CODEX_AGENT_WORKSPACE_REASON_ACCESS_REVOKED,
        CODEX_AGENT_WORKSPACE_REASON_INVALID_SELECTION};
    const char *messages[] = {
        "No workspace selected",
        "Workspace not found",
        "Workspace access revoked",
        "Workspace selection invalid"};
    size_t index;

    for (index = 0U; index < sizeof(reasons) / sizeof(reasons[0]); ++index) {
        const codex_agent_string_view_t message = string_view(messages[index]);
        codex_agent_workspace_selection_required_t *required = NULL;
        codex_agent_workspace_selection_reason_t projected = INT32_C(-1);
        CHECK(
            codex_agent_workspace_selection_required_create(
                context,
                reasons[index],
                &message,
                &required) == CODEX_AGENT_STATUS_OK);
        CHECK(required != NULL);
        CHECK(
            codex_agent_workspace_selection_required_reason(
                context,
                required,
                &projected) == CODEX_AGENT_STATUS_OK);
        CHECK(projected == reasons[index]);
        CHECK_HANDLE_COPY(
            codex_agent_workspace_selection_required_message_copy,
            context,
            required,
            messages[index]);
        CHECK(
            codex_agent_workspace_selection_required_destroy(context, &required) ==
            CODEX_AGENT_STATUS_OK);
        CHECK(required == NULL);
    }
    return 0;
}

int main(void) {
    const codex_agent_string_view_t empty = {NULL, 0U};
    const codex_agent_string_view_t failure_code = string_view("consumer_failure");
    const codex_agent_string_view_t failure_message = string_view("Consumer failure message");
    const codex_agent_string_view_t conversation_id_value = string_view("consumer-thread");
    const codex_agent_string_view_t summary_title = string_view("Consumer summary");
    const codex_agent_string_view_t workspace_path = string_view("/consumer/workspace");
    codex_agent_context_t *context = NULL;
    codex_agent_failure_t *failure = NULL;
    codex_agent_conversation_id_t *conversation_id = NULL;
    codex_agent_conversation_summary_t *summary = NULL;
    codex_agent_conversation_id_t *nested_conversation_id = NULL;
    codex_agent_workspace_t *workspace = NULL;
    codex_agent_workspace_resolution_available_t *available = NULL;
    codex_agent_workspace_t *nested_workspace = NULL;
    int32_t recoverable = INT32_C(-1);
    int64_t updated_at = INT64_C(-1);

    CHECK(validate_approval_presets() == 0);
    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(context != NULL);

    CHECK(
        codex_agent_failure_create(
            context,
            &failure_code,
            &failure_message,
            INT32_C(1),
            &failure) == CODEX_AGENT_STATUS_OK);
    CHECK(failure != NULL);
    CHECK_HANDLE_COPY(
        codex_agent_failure_code_copy,
        context,
        failure,
        "consumer_failure");
    CHECK_HANDLE_COPY(
        codex_agent_failure_message_copy,
        context,
        failure,
        "Consumer failure message");
    CHECK(
        codex_agent_failure_is_recoverable(context, failure, &recoverable) ==
        CODEX_AGENT_STATUS_OK);
    CHECK(recoverable == INT32_C(1));

    CHECK(
        codex_agent_conversation_id_create(
            context,
            &conversation_id_value,
            &conversation_id) == CODEX_AGENT_STATUS_OK);
    CHECK(conversation_id != NULL);
    CHECK_HANDLE_COPY(
        codex_agent_conversation_id_value_copy,
        context,
        conversation_id,
        "consumer-thread");
    CHECK(
        codex_agent_conversation_summary_create(
            context,
            conversation_id,
            &summary_title,
            INT64_C(1725000123),
            &summary) == CODEX_AGENT_STATUS_OK);
    CHECK(summary != NULL);
    CHECK_HANDLE_COPY(
        codex_agent_conversation_summary_title_copy,
        context,
        summary,
        "Consumer summary");
    CHECK(
        codex_agent_conversation_summary_updated_at_epoch_seconds(
            context,
            summary,
            &updated_at) == CODEX_AGENT_STATUS_OK);
    CHECK(updated_at == INT64_C(1725000123));
    CHECK(
        codex_agent_conversation_summary_conversation_id(
            context,
            summary,
            &nested_conversation_id) == CODEX_AGENT_STATUS_OK);
    CHECK(nested_conversation_id != NULL);
    CHECK(nested_conversation_id != conversation_id);
    CHECK(
        codex_agent_conversation_id_destroy(context, &conversation_id) ==
        CODEX_AGENT_STATUS_OK);
    CHECK(conversation_id == NULL);
    CHECK(
        codex_agent_conversation_summary_destroy(context, &summary) ==
        CODEX_AGENT_STATUS_OK);
    CHECK(summary == NULL);
    CHECK_HANDLE_COPY(
        codex_agent_conversation_id_value_copy,
        context,
        nested_conversation_id,
        "consumer-thread");
    CHECK(
        codex_agent_conversation_id_destroy(context, &nested_conversation_id) ==
        CODEX_AGENT_STATUS_OK);
    CHECK(nested_conversation_id == NULL);

    CHECK(
        codex_agent_workspace_create(
            context,
            &workspace_path,
            INT32_C(0),
            &empty,
            &workspace) == CODEX_AGENT_STATUS_OK);
    CHECK(workspace != NULL);
    CHECK_HANDLE_COPY(
        codex_agent_workspace_path_copy,
        context,
        workspace,
        "/consumer/workspace");
    CHECK_HANDLE_COPY(
        codex_agent_workspace_display_name_copy,
        context,
        workspace,
        "/consumer/workspace");
    CHECK(
        codex_agent_workspace_resolution_available_create(
            context,
            workspace,
            &available) == CODEX_AGENT_STATUS_OK);
    CHECK(available != NULL);
    CHECK(
        codex_agent_workspace_resolution_available_workspace(
            context,
            available,
            &nested_workspace) == CODEX_AGENT_STATUS_OK);
    CHECK(nested_workspace != NULL);
    CHECK(nested_workspace != workspace);
    CHECK(
        codex_agent_workspace_destroy(context, &workspace) ==
        CODEX_AGENT_STATUS_OK);
    CHECK(workspace == NULL);
    CHECK(
        codex_agent_workspace_resolution_available_destroy(context, &available) ==
        CODEX_AGENT_STATUS_OK);
    CHECK(available == NULL);
    CHECK_HANDLE_COPY(
        codex_agent_workspace_display_name_copy,
        context,
        nested_workspace,
        "/consumer/workspace");
    CHECK(
        codex_agent_workspace_destroy(context, &nested_workspace) ==
        CODEX_AGENT_STATUS_OK);
    CHECK(nested_workspace == NULL);

    CHECK(validate_workspace_reasons(context) == 0);
    CHECK(codex_agent_failure_release(context, &failure) == CODEX_AGENT_STATUS_OK);
    CHECK(failure == NULL);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(context == NULL);
    return 0;
}
