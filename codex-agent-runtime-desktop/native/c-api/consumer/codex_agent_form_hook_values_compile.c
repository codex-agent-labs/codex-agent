#include "codex_agent.h"

#include <math.h>
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

#define STRING_VIEW(data_value, size_value) \
    (&(const codex_agent_string_view_t){(const uint8_t *)(data_value), (size_value)})

#define LITERAL_VIEW(value) STRING_VIEW((value), strlen(value))

int main(void) {
    codex_agent_context_t *context = NULL;
    codex_agent_context_t *other_context = NULL;
    int32_t projected_flag = -1;
    double projected_number = 0.0;
    size_t required = SIZE_MAX;

    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_create(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(context != NULL);
    CHECK(other_context != NULL);

    {
        int32_t expected;
        for (expected = 0; expected <= 1; ++expected) {
            codex_agent_form_boolean_value_t *value = NULL;
            CHECK(codex_agent_form_boolean_value_create(context, expected, &value) == CODEX_AGENT_STATUS_OK);
            CHECK(value != NULL);
            projected_flag = -1;
            CHECK(codex_agent_form_boolean_value_value(context, value, &projected_flag) ==
                  CODEX_AGENT_STATUS_OK);
            CHECK(projected_flag == expected);
            CHECK(codex_agent_form_boolean_value_value(context, value, NULL) ==
                  CODEX_AGENT_STATUS_INVALID_ARGUMENT);
            CHECK(codex_agent_form_boolean_value_destroy(context, &value) == CODEX_AGENT_STATUS_OK);
            CHECK(value == NULL);
        }
        {
            codex_agent_form_boolean_value_t *invalid_value = NULL;
            CHECK(codex_agent_form_boolean_value_create(context, -1, &invalid_value) ==
                  CODEX_AGENT_STATUS_INVALID_ARGUMENT);
            CHECK(invalid_value == NULL);
            CHECK(codex_agent_form_boolean_value_create(context, 2, &invalid_value) ==
                  CODEX_AGENT_STATUS_INVALID_ARGUMENT);
            CHECK(invalid_value == NULL);
        }
        CHECK(codex_agent_form_boolean_value_create(context, 0, NULL) ==
              CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    }

    {
        const double values[] = {12.5, INFINITY, -INFINITY, NAN};
        size_t index;
        for (index = 0u; index < sizeof(values) / sizeof(values[0]); ++index) {
            codex_agent_form_number_value_t *value = NULL;
            CHECK(codex_agent_form_number_value_create(context, values[index], &value) == CODEX_AGENT_STATUS_OK);
            projected_number = 0.0;
            CHECK(codex_agent_form_number_value_value(context, value, &projected_number) ==
                  CODEX_AGENT_STATUS_OK);
            CHECK(codex_agent_form_number_value_value(context, value, NULL) ==
                  CODEX_AGENT_STATUS_INVALID_ARGUMENT);
            if (isnan(values[index])) {
                CHECK(isnan(projected_number));
            } else if (isinf(values[index])) {
                CHECK(isinf(projected_number));
                CHECK(signbit(values[index]) == signbit(projected_number));
            } else {
                CHECK(projected_number == values[index]);
            }
            CHECK(codex_agent_form_number_value_destroy(context, &value) == CODEX_AGENT_STATUS_OK);
        }
        CHECK(codex_agent_form_number_value_create(context, 1.0, NULL) ==
              CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    }

    {
        uint8_t bytes[] = "copied text";
        codex_agent_form_text_value_t *value = NULL;
        codex_agent_form_text_value_t *stale;
        CHECK(codex_agent_form_text_value_create(
                  context, STRING_VIEW(bytes, sizeof(bytes) - 1u), &value) == CODEX_AGENT_STATUS_OK);
        stale = value;
        bytes[0] = (uint8_t)'X';
        CHECK_COPY(codex_agent_form_text_value_value_copy, context, value, "copied text");
        required = SIZE_MAX;
        CHECK(codex_agent_form_text_value_value_copy(other_context, value, NULL, 0u, &required) ==
              CODEX_AGENT_STATUS_WRONG_CONTEXT);
        CHECK(required == SIZE_MAX);
        CHECK(codex_agent_form_text_value_destroy(context, &value) == CODEX_AGENT_STATUS_OK);
        CHECK(value == NULL);
        CHECK(codex_agent_form_text_value_destroy(context, &value) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_form_text_value_value_copy(context, stale, NULL, 0u, &required) ==
              CODEX_AGENT_STATUS_STALE_HANDLE);
        CHECK(codex_agent_form_text_value_create(context, LITERAL_VIEW("text"), NULL) ==
              CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK(codex_agent_form_text_value_create(context, NULL, &value) ==
              CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK(value == NULL);
    }

    {
        codex_agent_hook_handler_agent_t *agent_one = NULL;
        codex_agent_hook_handler_agent_t *agent_two = NULL;
        codex_agent_hook_handler_prompt_t *prompt_one = NULL;
        codex_agent_hook_handler_prompt_t *prompt_two = NULL;
        codex_agent_hook_handler_agent_t *wrong_agent;
        CHECK(codex_agent_hook_handler_agent_acquire(context, &agent_one) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_hook_handler_agent_acquire(context, &agent_two) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_hook_handler_prompt_acquire(context, &prompt_one) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_hook_handler_prompt_acquire(context, &prompt_two) == CODEX_AGENT_STATUS_OK);
        CHECK(agent_one != agent_two);
        CHECK(prompt_one != prompt_two);
        CHECK((void *)agent_one != (void *)prompt_one);
        wrong_agent = (codex_agent_hook_handler_agent_t *)prompt_one;
        CHECK(codex_agent_hook_handler_agent_destroy(context, &wrong_agent) ==
              CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
        CHECK((void *)wrong_agent == (void *)prompt_one);
        CHECK(codex_agent_hook_handler_agent_destroy(context, &agent_one) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_hook_handler_agent_destroy(context, &agent_two) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_hook_handler_prompt_destroy(context, &prompt_one) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_hook_handler_prompt_destroy(context, &prompt_two) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_hook_handler_agent_acquire(context, NULL) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK(codex_agent_hook_handler_prompt_acquire(context, NULL) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    }

    {
        int32_t expected;
        for (expected = 0; expected <= 1; ++expected) {
            uint8_t bytes[] = "command";
            codex_agent_hook_handler_command_t *command = NULL;
            CHECK(codex_agent_hook_handler_command_create(
                      context, STRING_VIEW(bytes, sizeof(bytes) - 1u), expected, &command) ==
                  CODEX_AGENT_STATUS_OK);
            bytes[0] = (uint8_t)'X';
            CHECK_COPY(codex_agent_hook_handler_command_command_copy, context, command, "command");
            projected_flag = -1;
            CHECK(codex_agent_hook_handler_command_is_async(context, command, &projected_flag) ==
                  CODEX_AGENT_STATUS_OK);
            CHECK(projected_flag == expected);
            CHECK(codex_agent_hook_handler_command_is_async(context, command, NULL) ==
                  CODEX_AGENT_STATUS_INVALID_ARGUMENT);
            CHECK(codex_agent_hook_handler_command_destroy(context, &command) == CODEX_AGENT_STATUS_OK);
        }
        {
            codex_agent_hook_handler_command_t *command = NULL;
            CHECK(codex_agent_hook_handler_command_create(context, LITERAL_VIEW("command"), 0, NULL) ==
                  CODEX_AGENT_STATUS_INVALID_ARGUMENT);
            CHECK(codex_agent_hook_handler_command_create(context, LITERAL_VIEW("command"), -1, &command) ==
                  CODEX_AGENT_STATUS_INVALID_ARGUMENT);
            CHECK(command == NULL);
            CHECK(codex_agent_hook_handler_command_create(context, LITERAL_VIEW("command"), 2, &command) ==
                  CODEX_AGENT_STATUS_INVALID_ARGUMENT);
            CHECK(command == NULL);
            CHECK(codex_agent_hook_handler_command_create(context, NULL, 0, &command) ==
                  CODEX_AGENT_STATUS_INVALID_ARGUMENT);
            CHECK(command == NULL);
        }
    }

    {
        uint8_t server_bytes[] = "server";
        uint8_t tool_bytes[] = "tool";
        codex_agent_hook_handler_mcp_tool_t *handler = NULL;
        CHECK(codex_agent_hook_handler_mcp_tool_create(
                  context,
                  STRING_VIEW(server_bytes, sizeof(server_bytes) - 1u),
                  STRING_VIEW(tool_bytes, sizeof(tool_bytes) - 1u),
                  &handler) == CODEX_AGENT_STATUS_OK);
        server_bytes[0] = (uint8_t)'X';
        tool_bytes[0] = (uint8_t)'X';
        CHECK_COPY(codex_agent_hook_handler_mcp_tool_server_copy, context, handler, "server");
        CHECK_COPY(codex_agent_hook_handler_mcp_tool_tool_copy, context, handler, "tool");
        CHECK(codex_agent_hook_handler_command_is_async(
                  context, (codex_agent_hook_handler_command_t *)handler, &projected_flag) ==
              CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
        CHECK(codex_agent_hook_handler_mcp_tool_destroy(context, &handler) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_hook_handler_mcp_tool_create(
                  context, LITERAL_VIEW("server"), LITERAL_VIEW("tool"), NULL) ==
              CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK(codex_agent_hook_handler_mcp_tool_create(context, NULL, LITERAL_VIEW("tool"), &handler) ==
              CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK(handler == NULL);
        CHECK(codex_agent_hook_handler_mcp_tool_create(context, LITERAL_VIEW("server"), NULL, &handler) ==
              CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK(handler == NULL);
    }

    {
        const uint8_t invalid_utf8[] = {UINT8_C(0xc3), UINT8_C(0x28)};
        codex_agent_form_text_value_t *text = NULL;
        codex_agent_hook_handler_command_t *command = NULL;
        codex_agent_hook_handler_mcp_tool_t *mcp_tool = NULL;
        CHECK(codex_agent_form_text_value_create(
                  context, STRING_VIEW(invalid_utf8, sizeof(invalid_utf8)), &text) ==
              CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK(codex_agent_hook_handler_command_create(
                  context, STRING_VIEW(invalid_utf8, sizeof(invalid_utf8)), 0, &command) ==
              CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK(codex_agent_hook_handler_mcp_tool_create(
                  context, STRING_VIEW(invalid_utf8, sizeof(invalid_utf8)), LITERAL_VIEW("tool"), &mcp_tool) ==
              CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK(mcp_tool == NULL);
        CHECK(codex_agent_hook_handler_mcp_tool_create(
                  context, LITERAL_VIEW("server"), STRING_VIEW(invalid_utf8, sizeof(invalid_utf8)), &mcp_tool) ==
              CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK(text == NULL);
        CHECK(command == NULL);
        CHECK(mcp_tool == NULL);
    }

    {
        codex_agent_form_boolean_value_t *occupied = (codex_agent_form_boolean_value_t *)context;
        CHECK(codex_agent_form_boolean_value_create(context, 1, &occupied) ==
              CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK((void *)occupied == (void *)context);
    }

    CHECK(codex_agent_context_destroy(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(other_context == NULL);
    CHECK(context == NULL);
    return 0;
}
