#include "codex_agent.h"

#include <string.h>

#define CHECK(condition)       \
    do {                       \
        if (!(condition)) {    \
            return __LINE__;   \
        }                      \
    } while (0)

#define VIEW(literal)                                                      \
    ((codex_agent_string_view_t){                                          \
        (const uint8_t *)(literal), sizeof(literal) - sizeof((literal)[0]) \
    })

_Static_assert(CODEX_AGENT_ABI_VERSION_MAJOR == UINT32_C(1), "ABI major");
_Static_assert(CODEX_AGENT_ABI_VERSION_MINOR == UINT32_C(8), "ABI minor");
_Static_assert(CODEX_AGENT_ABI_VERSION_PATCH == UINT32_C(0), "ABI patch");
_Static_assert(
    CODEX_AGENT_ABI_VERSION_CURRENT == UINT32_C(0x01080000),
    "ABI current");
_Static_assert(
    CODEX_AGENT_ABI_VERSION_MINIMUM_COMPATIBLE == UINT32_C(0x01000000),
    "ABI minimum compatible");

int main(void) {
    codex_agent_context_t *context = NULL;
    codex_agent_form_text_value_t *text = NULL;
    codex_agent_form_value_t *value = NULL;
    codex_agent_form_value_t *projected_value = NULL;
    codex_agent_form_field_t *field = NULL;
    codex_agent_conversation_id_t *conversation_id = NULL;
    codex_agent_elicitation_t *elicitation = NULL;
    codex_agent_form_content_t *initial = NULL;
    codex_agent_form_content_t *content = NULL;
    codex_agent_elicitation_validation_t *validation = NULL;
    codex_agent_elicitation_response_t *accepted = NULL;
    codex_agent_elicitation_response_t *declined = NULL;
    codex_agent_elicitation_response_t *cancelled = NULL;
    const codex_agent_string_view_t absent = {NULL, 0};
    const codex_agent_string_view_t name = VIEW("name");
    const codex_agent_string_view_t title = VIEW("Name");
    const codex_agent_string_view_t answer = VIEW("answer");
    const codex_agent_string_view_t request_id = VIEW("request-1");
    const codex_agent_string_view_t server_name = VIEW("server");
    const codex_agent_string_view_t conversation = VIEW("conversation-1");
    const codex_agent_string_view_t message = VIEW("Provide input");
    codex_agent_form_field_t *fields[1];
    codex_agent_form_value_t *values[1];
    codex_agent_string_view_t keys[1];
    int32_t accepted_flag = -1;
    int32_t action = -1;
    int32_t is_valid = -1;
    size_t count = SIZE_MAX;
    size_t required = SIZE_MAX;
    uint8_t key_buffer[4] = {0};

    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(context != NULL);
    CHECK(codex_agent_form_text_value_create(context, &answer, &text) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_form_value_from_text(context, text, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_form_text_value_destroy(context, &text) == CODEX_AGENT_STATUS_OK);

    CHECK(
        codex_agent_form_field_create(
            context,
            &name,
            &title,
            0,
            &absent,
            1,
            CODEX_AGENT_FORM_FIELD_TYPE_STRING,
            NULL,
            0,
            0,
            NULL,
            0,
            0.0,
            0,
            0.0,
            0,
            CODEX_AGENT_FORM_STRING_FORMAT_EMAIL,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            &field) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_form_field_accepts(context, field, value, &accepted_flag) == CODEX_AGENT_STATUS_OK);
    CHECK(accepted_flag == 1);
    CHECK(codex_agent_form_field_accepts(context, field, NULL, &accepted_flag) == CODEX_AGENT_STATUS_OK);
    CHECK(accepted_flag == 0);

    CHECK(codex_agent_conversation_id_create(context, &conversation, &conversation_id) == CODEX_AGENT_STATUS_OK);
    fields[0] = field;
    CHECK(
        codex_agent_elicitation_create(
            context,
            &request_id,
            &server_name,
            conversation_id,
            &message,
            1,
            fields,
            1,
            0,
            &absent,
            &elicitation) == CODEX_AGENT_STATUS_OK);

    CHECK(codex_agent_elicitation_initial_values(context, elicitation, &initial) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_form_content_count(context, initial, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 0);
    CHECK(codex_agent_form_content_destroy(context, &initial) == CODEX_AGENT_STATUS_OK);

    keys[0] = name;
    values[0] = value;
    CHECK(codex_agent_form_content_create(context, keys, values, 1, &content) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_form_content_count(context, content, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 1);
    CHECK(
        codex_agent_form_content_key_copy(context, content, 0, NULL, 0, &required) ==
        CODEX_AGENT_STATUS_BUFFER_TOO_SMALL);
    CHECK(required == sizeof(key_buffer));
    CHECK(
        codex_agent_form_content_key_copy(
            context,
            content,
            0,
            key_buffer,
            sizeof(key_buffer),
            &required) == CODEX_AGENT_STATUS_OK);
    CHECK(memcmp(key_buffer, "name", sizeof(key_buffer)) == 0);
    CHECK(
        codex_agent_form_content_value_at(context, content, &name, &projected_value) ==
        CODEX_AGENT_STATUS_OK);
    CHECK(projected_value != NULL);
    CHECK(codex_agent_form_value_destroy(context, &projected_value) == CODEX_AGENT_STATUS_OK);

    CHECK(
        codex_agent_elicitation_validate(context, elicitation, content, &validation) ==
        CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_elicitation_validation_is_valid(context, validation, &is_valid) == CODEX_AGENT_STATUS_OK);
    CHECK(is_valid == 1);
    CHECK(
        codex_agent_elicitation_accept(context, elicitation, content, &accepted) ==
        CODEX_AGENT_STATUS_OK);
    CHECK(
        codex_agent_elicitation_accepts(context, elicitation, accepted, &accepted_flag) ==
        CODEX_AGENT_STATUS_OK);
    CHECK(accepted_flag == 1);
    CHECK(codex_agent_elicitation_response_action(context, accepted, &action) == CODEX_AGENT_STATUS_OK);
    CHECK(action == CODEX_AGENT_ELICITATION_ACTION_ACCEPT);

    CHECK(codex_agent_elicitation_response_decline(context, &declined) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_elicitation_response_cancel(context, &cancelled) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_elicitation_accepts(context, elicitation, declined, &accepted_flag) == CODEX_AGENT_STATUS_OK);
    CHECK(accepted_flag == 1);
    CHECK(codex_agent_elicitation_accepts(context, elicitation, cancelled, &accepted_flag) == CODEX_AGENT_STATUS_OK);
    CHECK(accepted_flag == 1);

    CHECK(codex_agent_elicitation_response_destroy(context, &cancelled) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_elicitation_response_destroy(context, &declined) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_elicitation_response_destroy(context, &accepted) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_elicitation_validation_destroy(context, &validation) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_form_content_destroy(context, &content) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_elicitation_destroy(context, &elicitation) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_conversation_id_destroy(context, &conversation_id) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_form_field_destroy(context, &field) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_form_value_destroy(context, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(context == NULL);
    return 0;
}
