#include "codex_agent.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHECK(condition) \
    do { \
        if (!(condition)) { \
            (void)fprintf(stderr, "check failed at line %d: %s\n", __LINE__, #condition); \
            return 1; \
        } \
    } while (0)

#define STRING_VIEW(data_value, size_value) \
    (&(const codex_agent_string_view_t){(const uint8_t *)(data_value), (size_value)})

#define LITERAL_VIEW(value) STRING_VIEW((value), strlen(value))
#define EMPTY_VIEW() STRING_VIEW(NULL, 0u)

#define CHECK_COPY(function, context, handle, expected) \
    do { \
        const char *check_copy_expected = (expected); \
        const size_t check_copy_size = strlen(check_copy_expected); \
        size_t check_copy_required = SIZE_MAX; \
        uint8_t check_copy_buffer[128] = {0}; \
        CHECK(check_copy_size <= sizeof(check_copy_buffer)); \
        CHECK((function)((context), (handle), NULL, 0u, &check_copy_required) == \
              (check_copy_size == 0u ? CODEX_AGENT_STATUS_OK : CODEX_AGENT_STATUS_BUFFER_TOO_SMALL)); \
        CHECK(check_copy_required == check_copy_size); \
        CHECK((function)((context), (handle), check_copy_buffer, sizeof(check_copy_buffer), \
                         &check_copy_required) == CODEX_AGENT_STATUS_OK); \
        CHECK(memcmp(check_copy_buffer, check_copy_expected, check_copy_size) == 0); \
    } while (0)

int main(void) {
    codex_agent_context_t *context = NULL;
    codex_agent_context_t *other_context = NULL;
    codex_agent_invocation_plugin_t *plugin = NULL;
    codex_agent_invocation_skill_t *skill = NULL;
    codex_agent_invocation_t *plugin_invocation = NULL;
    codex_agent_invocation_t *skill_invocation = NULL;
    codex_agent_message_t *message = NULL;
    codex_agent_message_t *second_message = NULL;
    codex_agent_conversation_id_t *conversation_id = NULL;
    codex_agent_conversation_summary_t *summary = NULL;
    codex_agent_conversation_value_t *conversation = NULL;
    codex_agent_turn_progress_t *progress = NULL;
    codex_agent_turn_request_t *request = NULL;
    codex_agent_snapshot_t *state = NULL;
    int32_t projected = -1;
    size_t count = SIZE_MAX;

    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_create(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(context != NULL);
    CHECK(other_context != NULL);

    CHECK(codex_agent_invocation_plugin_create(
              context, LITERAL_VIEW("plugin"), LITERAL_VIEW("file:///plugin"), &plugin) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_invocation_skill_create(
              context, LITERAL_VIEW("skill"), LITERAL_VIEW("/skill"), &skill) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_invocation_from_plugin(context, plugin, &plugin_invocation) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_invocation_from_skill(context, skill, &skill_invocation) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_invocation_kind(context, plugin_invocation, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == CODEX_AGENT_INVOCATION_KIND_PLUGIN);
    CHECK(codex_agent_invocation_kind(context, skill_invocation, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == CODEX_AGENT_INVOCATION_KIND_SKILL);
    {
        codex_agent_invocation_plugin_t *copied_plugin = NULL;
        codex_agent_invocation_skill_t *copied_skill = NULL;
        CHECK(codex_agent_invocation_plugin(context, plugin_invocation, &copied_plugin) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_invocation_skill(context, plugin_invocation, &copied_skill) ==
              CODEX_AGENT_STATUS_NOT_READY);
        CHECK(copied_skill == NULL);
        CHECK(codex_agent_invocation_skill(context, skill_invocation, &copied_skill) ==
              CODEX_AGENT_STATUS_OK);
        CHECK_COPY(codex_agent_invocation_plugin_name_copy, context, copied_plugin, "plugin");
        CHECK_COPY(codex_agent_invocation_skill_name_copy, context, copied_skill, "skill");
        CHECK(codex_agent_invocation_plugin_destroy(context, &copied_plugin) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_invocation_skill_destroy(context, &copied_skill) == CODEX_AGENT_STATUS_OK);
    }

    {
        uint8_t id_bytes[] = "message";
        uint8_t text_bytes[] = "message text";
        const int32_t capabilities[] = {
            CODEX_AGENT_CAPABILITY_WEB_SEARCH,
            CODEX_AGENT_CAPABILITY_WEB_SEARCH,
        };
        codex_agent_invocation_t *const invocations[] = {plugin_invocation, skill_invocation, plugin_invocation};
        CHECK(codex_agent_message_create(
                  context,
                  STRING_VIEW(id_bytes, sizeof(id_bytes) - 1u),
                  1,
                  LITERAL_VIEW("client"),
                  CODEX_AGENT_MESSAGE_ROLE_ASSISTANT,
                  STRING_VIEW(text_bytes, sizeof(text_bytes) - 1u),
                  CODEX_AGENT_COLLABORATION_MODE_PLAN,
                  1,
                  LITERAL_VIEW("reasoning"),
                  1,
                  LITERAL_VIEW(""),
                  1,
                  LITERAL_VIEW("pwd"),
                  1,
                  -7,
                  capabilities,
                  sizeof(capabilities) / sizeof(capabilities[0]),
                  invocations,
                  sizeof(invocations) / sizeof(invocations[0]),
                  &message) == CODEX_AGENT_STATUS_OK);
        id_bytes[0] = (uint8_t)'X';
        text_bytes[0] = (uint8_t)'X';
    }
    CHECK_COPY(codex_agent_message_id_copy, context, message, "message");
    CHECK(codex_agent_message_has_client_message_id(context, message, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == 1);
    CHECK_COPY(codex_agent_message_client_message_id_copy, context, message, "client");
    CHECK(codex_agent_message_role(context, message, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == CODEX_AGENT_MESSAGE_ROLE_ASSISTANT);
    CHECK_COPY(codex_agent_message_text_copy, context, message, "message text");
    CHECK(codex_agent_message_collaboration_mode(context, message, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == CODEX_AGENT_COLLABORATION_MODE_PLAN);
    CHECK(codex_agent_message_has_reasoning(context, message, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == 1);
    CHECK_COPY(codex_agent_message_reasoning_copy, context, message, "reasoning");
    CHECK(codex_agent_message_has_plan(context, message, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == 1);
    CHECK_COPY(codex_agent_message_plan_copy, context, message, "");
    CHECK(codex_agent_message_has_shell_command(context, message, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == 1);
    CHECK_COPY(codex_agent_message_shell_command_copy, context, message, "pwd");
    {
        int32_t has_exit = -1;
        int32_t exit_code = 99;
        CHECK(codex_agent_message_exit_code(context, message, &has_exit, &exit_code) == CODEX_AGENT_STATUS_OK);
        CHECK(has_exit == 1);
        CHECK(exit_code == -7);
    }
    CHECK(codex_agent_message_capabilities_count(context, message, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 1u);
    CHECK(codex_agent_message_has_capability(
              context, message, CODEX_AGENT_CAPABILITY_WEB_SEARCH, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == 1);
    CHECK(codex_agent_message_invocations_count(context, message, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 3u);
    {
        codex_agent_invocation_t *child = NULL;
        CHECK(codex_agent_message_invocation_at(context, message, 1u, &child) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_invocation_kind(context, child, &projected) == CODEX_AGENT_STATUS_OK);
        CHECK(projected == CODEX_AGENT_INVOCATION_KIND_SKILL);
        CHECK(codex_agent_invocation_destroy(context, &child) == CODEX_AGENT_STATUS_OK);
        CHECK(child == NULL);
    }

    {
        codex_agent_invocation_t *const no_invocations[] = {plugin_invocation};
        CHECK(codex_agent_message_create(
                  context, LITERAL_VIEW("second"), 0, EMPTY_VIEW(), CODEX_AGENT_MESSAGE_ROLE_USER,
                  LITERAL_VIEW("second text"), CODEX_AGENT_COLLABORATION_MODE_DEFAULT,
                  0, EMPTY_VIEW(), 0, EMPTY_VIEW(), 0, EMPTY_VIEW(), 0, 0,
                  NULL, 0u, no_invocations, 1u, &second_message) == CODEX_AGENT_STATUS_OK);
    }
    CHECK(codex_agent_conversation_id_create(context, LITERAL_VIEW("conversation"), &conversation_id) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_conversation_summary_create(
              context, conversation_id, LITERAL_VIEW("title"), INT64_C(42), &summary) ==
          CODEX_AGENT_STATUS_OK);
    {
        codex_agent_message_t *const messages[] = {message, second_message, message};
        CHECK(codex_agent_conversation_value_create(
                  context, summary, messages, sizeof(messages) / sizeof(messages[0]), &conversation) ==
              CODEX_AGENT_STATUS_OK);
    }
    CHECK(codex_agent_conversation_value_messages_count(context, conversation, &count) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(count == 3u);
    {
        codex_agent_conversation_summary_t *child_summary = NULL;
        codex_agent_message_t *first = NULL;
        codex_agent_message_t *middle = NULL;
        codex_agent_message_t *last = NULL;
        CHECK(codex_agent_conversation_value_summary(context, conversation, &child_summary) ==
              CODEX_AGENT_STATUS_OK);
        CHECK_COPY(codex_agent_conversation_summary_title_copy, context, child_summary, "title");
        CHECK(codex_agent_conversation_value_message_at(context, conversation, 0u, &first) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_conversation_value_message_at(context, conversation, 1u, &middle) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_conversation_value_message_at(context, conversation, 2u, &last) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(first != last);
        CHECK_COPY(codex_agent_message_id_copy, context, first, "message");
        CHECK_COPY(codex_agent_message_id_copy, context, middle, "second");
        CHECK_COPY(codex_agent_message_id_copy, context, last, "message");
        CHECK(codex_agent_conversation_value_destroy(context, &conversation) == CODEX_AGENT_STATUS_OK);
        CHECK_COPY(codex_agent_message_id_copy, context, first, "message");
        CHECK(codex_agent_message_destroy(context, &first) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_message_destroy(context, &middle) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_message_destroy(context, &last) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_conversation_summary_destroy(context, &child_summary) == CODEX_AGENT_STATUS_OK);
    }

    CHECK(codex_agent_turn_progress_create(
              context,
              LITERAL_VIEW("turn"),
              LITERAL_VIEW(""),
              LITERAL_VIEW(""),
              LITERAL_VIEW(""),
              0,
              NULL,
              LITERAL_VIEW(""),
              0,
              0,
              0,
              0,
              NULL,
              0u,
              0,
              &progress) == CODEX_AGENT_STATUS_OK);
    {
        const int32_t capabilities[] = {
            CODEX_AGENT_CAPABILITY_WEB_SEARCH,
            CODEX_AGENT_CAPABILITY_WEB_SEARCH,
        };
        codex_agent_invocation_t *const invocations[] = {plugin_invocation, skill_invocation, plugin_invocation};
        CHECK(codex_agent_turn_request_create(
                  context,
                  LITERAL_VIEW("prompt"),
                  1,
                  LITERAL_VIEW(""),
                  0,
                  EMPTY_VIEW(),
                  1,
                  LITERAL_VIEW("high"),
                  1,
                  LITERAL_VIEW("fast"),
                  CODEX_AGENT_APPROVAL_PRESET_STRICT,
                  capabilities,
                  sizeof(capabilities) / sizeof(capabilities[0]),
                  invocations,
                  sizeof(invocations) / sizeof(invocations[0]),
                  CODEX_AGENT_COLLABORATION_MODE_PLAN,
                  &request) == CODEX_AGENT_STATUS_OK);
    }
    CHECK_COPY(codex_agent_turn_request_prompt_copy, context, request, "prompt");
    CHECK(codex_agent_turn_request_has_client_message_id(context, request, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == 1);
    CHECK_COPY(codex_agent_turn_request_client_message_id_copy, context, request, "");
    CHECK(codex_agent_turn_request_has_model(context, request, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == 0);
    count = SIZE_MAX;
    CHECK(codex_agent_turn_request_model_copy(context, request, NULL, 0u, &count) ==
          CODEX_AGENT_STATUS_NOT_READY);
    CHECK(count == SIZE_MAX);
    CHECK(codex_agent_turn_request_has_effort(context, request, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == 1);
    CHECK_COPY(codex_agent_turn_request_effort_copy, context, request, "high");
    CHECK(codex_agent_turn_request_has_service_tier(context, request, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == 1);
    CHECK_COPY(codex_agent_turn_request_service_tier_copy, context, request, "fast");
    CHECK(codex_agent_turn_request_approval_preset(context, request, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == CODEX_AGENT_APPROVAL_PRESET_STRICT);
    CHECK(codex_agent_turn_request_capabilities_count(context, request, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 1u);
    CHECK(codex_agent_turn_request_has_capability(
              context, request, CODEX_AGENT_CAPABILITY_WEB_SEARCH, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == 1);
    CHECK(codex_agent_turn_request_invocations_count(context, request, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 3u);
    CHECK(codex_agent_turn_request_collaboration_mode(context, request, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == CODEX_AGENT_COLLABORATION_MODE_PLAN);
    {
        codex_agent_invocation_t *child = NULL;
        codex_agent_invocation_plugin_t *child_plugin = NULL;
        CHECK(codex_agent_turn_request_invocation_at(context, request, 2u, &child) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_turn_request_destroy(context, &request) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_invocation_plugin(context, child, &child_plugin) == CODEX_AGENT_STATUS_OK);
        CHECK_COPY(codex_agent_invocation_plugin_name_copy, context, child_plugin, "plugin");
        CHECK(codex_agent_invocation_plugin_destroy(context, &child_plugin) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_invocation_destroy(context, &child) == CODEX_AGENT_STATUS_OK);
    }

    CHECK(codex_agent_conversation_state_create(
              context,
              CODEX_AGENT_CONVERSATION_STATUS_READY,
              1,
              conversation_id,
              0,
              NULL,
              progress,
              1,
              LITERAL_VIEW("model"),
              1,
              LITERAL_VIEW(""),
              1,
              LITERAL_VIEW("tier"),
              0,
              NULL,
              &state) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_conversation_state_status(context, state, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == CODEX_AGENT_CONVERSATION_STATUS_READY);
    CHECK(codex_agent_conversation_state_has_conversation_id(context, state, &projected) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(projected == 1);
    CHECK(codex_agent_conversation_state_has_conversation(context, state, &projected) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(projected == 0);
    CHECK(codex_agent_conversation_state_has_model(context, state, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == 1);
    CHECK_COPY(codex_agent_conversation_state_model_copy, context, state, "model");
    CHECK(codex_agent_conversation_state_has_effort(context, state, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == 1);
    CHECK_COPY(codex_agent_conversation_state_effort_copy, context, state, "");
    CHECK(codex_agent_conversation_state_has_service_tier(context, state, &projected) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(projected == 1);
    CHECK_COPY(codex_agent_conversation_state_service_tier_copy, context, state, "tier");
    CHECK(codex_agent_conversation_state_can_start_turn(context, state, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == 1);
    CHECK(codex_agent_conversation_state_can_reload(context, state, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == 1);
    CHECK(codex_agent_conversation_state_can_cancel_turn(context, state, &projected) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(projected == 0);
    {
        codex_agent_conversation_id_t *child_id = NULL;
        codex_agent_conversation_value_t *absent_conversation = NULL;
        codex_agent_turn_progress_t *child_progress = NULL;
        codex_agent_failure_t *absent_failure = NULL;
        CHECK(codex_agent_conversation_state_conversation_id(context, state, &child_id) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_conversation_state_conversation(context, state, &absent_conversation) ==
              CODEX_AGENT_STATUS_NOT_READY);
        CHECK(absent_conversation == NULL);
        CHECK(codex_agent_conversation_state_turn_progress(context, state, &child_progress) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_conversation_state_failure(context, state, &absent_failure) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(absent_failure == NULL);
        CHECK(codex_agent_snapshot_destroy(context, &state) == CODEX_AGENT_STATUS_OK);
        CHECK_COPY(codex_agent_conversation_id_value_copy, context, child_id, "conversation");
        CHECK_COPY(codex_agent_turn_progress_text_copy, context, child_progress, "turn");
        CHECK(codex_agent_conversation_id_destroy(context, &child_id) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_turn_progress_destroy(context, &child_progress) == CODEX_AGENT_STATUS_OK);
    }

    {
        const uint8_t invalid_utf8[] = {UINT8_C(0xc3), UINT8_C(0x28)};
        codex_agent_message_t *invalid = NULL;
        CHECK(codex_agent_message_create(
                  context, STRING_VIEW(invalid_utf8, sizeof(invalid_utf8)), 0, EMPTY_VIEW(),
                  CODEX_AGENT_MESSAGE_ROLE_USER, LITERAL_VIEW("text"),
                  CODEX_AGENT_COLLABORATION_MODE_DEFAULT, 0, EMPTY_VIEW(), 0, EMPTY_VIEW(),
                  0, EMPTY_VIEW(), 0, 0, NULL, 0u, NULL, 0u, &invalid) ==
              CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK(invalid == NULL);
        CHECK(codex_agent_message_create(
                  context, LITERAL_VIEW("id"), 0, EMPTY_VIEW(), INT32_C(99), LITERAL_VIEW("text"),
                  CODEX_AGENT_COLLABORATION_MODE_DEFAULT, 0, EMPTY_VIEW(), 0, EMPTY_VIEW(),
                  0, EMPTY_VIEW(), 0, 0, NULL, 0u, NULL, 0u, &invalid) ==
              CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK(invalid == NULL);
    }
    {
        int32_t untouched = 71;
        size_t required = SIZE_MAX;
        codex_agent_message_t *occupied = (codex_agent_message_t *)context;
        codex_agent_invocation_t *bad_index = NULL;
        CHECK(codex_agent_message_role(other_context, message, &untouched) ==
              CODEX_AGENT_STATUS_WRONG_CONTEXT);
        CHECK(untouched == 71);
        CHECK(codex_agent_message_role(context, (codex_agent_message_t *)summary, &untouched) ==
              CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
        CHECK(untouched == 71);
        CHECK(codex_agent_message_invocation_at(context, message, SIZE_MAX, &bad_index) ==
              CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK(bad_index == NULL);
        CHECK(codex_agent_conversation_value_message_at(
                  context, (codex_agent_conversation_value_t *)message, 0u, &occupied) ==
              CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK((void *)occupied == (void *)context);
        CHECK(codex_agent_message_has_capability(context, message, INT32_C(99), &untouched) ==
              CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK(untouched == 71);
        CHECK(codex_agent_message_id_copy(other_context, message, NULL, 0u, &required) ==
              CODEX_AGENT_STATUS_WRONG_CONTEXT);
        CHECK(required == SIZE_MAX);
    }

    CHECK(codex_agent_invocation_destroy(context, &plugin_invocation) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_invocation_destroy(context, &plugin_invocation) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_invocation_destroy(context, &skill_invocation) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_invocation_plugin_destroy(context, &plugin) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_invocation_skill_destroy(context, &skill) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_message_destroy(context, &message) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_message_destroy(context, &message) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_message_destroy(context, &second_message) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_conversation_summary_destroy(context, &summary) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_conversation_id_destroy(context, &conversation_id) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_turn_progress_destroy(context, &progress) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_destroy(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(other_context == NULL);
    CHECK(context == NULL);
    return 0;
}
