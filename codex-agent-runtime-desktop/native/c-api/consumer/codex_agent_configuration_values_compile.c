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
    const codex_agent_string_view_t absent = {NULL, 0u};
    int32_t present = -1;
    int32_t projected = -1;
    size_t required = SIZE_MAX;

    CHECK(CODEX_AGENT_MCP_ENVIRONMENT_SOURCE_LOCAL == 0);
    CHECK(CODEX_AGENT_MCP_ENVIRONMENT_SOURCE_REMOTE == 1);
    CHECK(CODEX_AGENT_MCP_TOOL_APPROVAL_AUTO == 0);
    CHECK(CODEX_AGENT_MCP_TOOL_APPROVAL_PROMPT == 1);
    CHECK(CODEX_AGENT_MCP_TOOL_APPROVAL_WRITES == 2);
    CHECK(CODEX_AGENT_MCP_TOOL_APPROVAL_APPROVE == 3);
    CHECK(CODEX_AGENT_ELICITATION_VALIDATION_MISSING_REQUIRED == 0);
    CHECK(CODEX_AGENT_ELICITATION_VALIDATION_UNKNOWN_FIELD == 1);
    CHECK(CODEX_AGENT_ELICITATION_VALIDATION_INVALID_TYPE == 2);
    CHECK(CODEX_AGENT_ELICITATION_VALIDATION_NON_FINITE_NUMBER == 3);
    CHECK(CODEX_AGENT_ELICITATION_VALIDATION_BELOW_MINIMUM == 4);
    CHECK(CODEX_AGENT_ELICITATION_VALIDATION_ABOVE_MAXIMUM == 5);
    CHECK(CODEX_AGENT_ELICITATION_VALIDATION_NON_INTEGER == 6);
    CHECK(CODEX_AGENT_ELICITATION_VALIDATION_INVALID_FORMAT == 7);
    CHECK(CODEX_AGENT_ELICITATION_VALIDATION_INVALID_SELECTION == 8);
    CHECK(CODEX_AGENT_ELICITATION_VALIDATION_DUPLICATE_SELECTION == 9);
    CHECK(CODEX_AGENT_PLAN_STEP_PENDING == 0);
    CHECK(CODEX_AGENT_PLAN_STEP_IN_PROGRESS == 1);
    CHECK(CODEX_AGENT_PLAN_STEP_COMPLETED == 2);

    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_create(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(context != NULL);
    CHECK(other_context != NULL);

    {
        uint8_t value_bytes[] = "value";
        codex_agent_form_option_t *option = NULL;
        CHECK(codex_agent_form_option_create(
                  context,
                  STRING_VIEW(value_bytes, sizeof(value_bytes) - 1u),
                  0,
                  &absent,
                  0,
                  &absent,
                  &option) == CODEX_AGENT_STATUS_OK);
        CHECK(option != NULL);
        value_bytes[0] = (uint8_t)'X';
        CHECK_COPY(codex_agent_form_option_value_copy, context, option, "value");
        CHECK_COPY(codex_agent_form_option_title_copy, context, option, "value");
        CHECK(codex_agent_form_option_has_description(context, option, &present) == CODEX_AGENT_STATUS_OK);
        CHECK(present == 0);
        required = SIZE_MAX;
        CHECK(codex_agent_form_option_description_copy(context, option, NULL, 0u, &required) ==
              CODEX_AGENT_STATUS_NOT_READY);
        CHECK(required == SIZE_MAX);
        CHECK(codex_agent_form_option_value_copy(other_context, option, NULL, 0u, &required) ==
              CODEX_AGENT_STATUS_WRONG_CONTEXT);
        CHECK(codex_agent_plan_step_status(context, (codex_agent_plan_step_t *)option, &projected) ==
              CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
        CHECK(codex_agent_form_option_destroy(context, &option) == CODEX_AGENT_STATUS_OK);
        CHECK(option == NULL);
    }

    {
        codex_agent_form_option_t *option = NULL;
        CHECK(codex_agent_form_option_create(
                  context,
                  LITERAL_VIEW("id"),
                  1,
                  LITERAL_VIEW("Title"),
                  1,
                  LITERAL_VIEW("Description"),
                  &option) == CODEX_AGENT_STATUS_OK);
        CHECK_COPY(codex_agent_form_option_title_copy, context, option, "Title");
        CHECK(codex_agent_form_option_has_description(context, option, &present) == CODEX_AGENT_STATUS_OK);
        CHECK(present == 1);
        CHECK_COPY(codex_agent_form_option_description_copy, context, option, "Description");
        CHECK(codex_agent_form_option_destroy(context, &option) == CODEX_AGENT_STATUS_OK);
    }

    {
        const codex_agent_mcp_environment_source_t sources[] = {
            CODEX_AGENT_MCP_ENVIRONMENT_SOURCE_LOCAL,
            CODEX_AGENT_MCP_ENVIRONMENT_SOURCE_REMOTE,
        };
        size_t index;
        for (index = 0u; index < sizeof(sources) / sizeof(sources[0]); ++index) {
            codex_agent_mcp_environment_variable_t *variable = NULL;
            CHECK(codex_agent_mcp_environment_variable_create(
                      context, LITERAL_VIEW("NAME"), 1, sources[index], &variable) == CODEX_AGENT_STATUS_OK);
            CHECK_COPY(codex_agent_mcp_environment_variable_name_copy, context, variable, "NAME");
            CHECK(codex_agent_mcp_environment_variable_source(context, variable, &present, &projected) ==
                  CODEX_AGENT_STATUS_OK);
            CHECK(present == 1);
            CHECK(projected == sources[index]);
            CHECK(codex_agent_mcp_environment_variable_destroy(context, &variable) == CODEX_AGENT_STATUS_OK);
        }
        {
            codex_agent_mcp_environment_variable_t *variable = NULL;
            CHECK(codex_agent_mcp_environment_variable_create(
                      context, LITERAL_VIEW("OPTIONAL"), 0, 0, &variable) == CODEX_AGENT_STATUS_OK);
            CHECK(codex_agent_mcp_environment_variable_source(context, variable, &present, &projected) ==
                  CODEX_AGENT_STATUS_OK);
            CHECK(present == 0);
            CHECK(projected == 0);
            CHECK(codex_agent_mcp_environment_variable_destroy(context, &variable) == CODEX_AGENT_STATUS_OK);
        }
    }

    {
        codex_agent_mcp_oauth_configuration_t *configuration = NULL;
        CHECK(codex_agent_mcp_oauth_configuration_create(
                  context, 0, &absent, 0, 0, &configuration) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_mcp_oauth_configuration_has_client_id(context, configuration, &present) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(present == 0);
        CHECK(codex_agent_mcp_oauth_configuration_client_id_copy(
                  context, configuration, NULL, 0u, &required) == CODEX_AGENT_STATUS_NOT_READY);
        CHECK(codex_agent_mcp_oauth_configuration_callback_port(
                  context, configuration, &present, &projected) == CODEX_AGENT_STATUS_OK);
        CHECK(present == 0);
        CHECK(projected == 0);
        CHECK(codex_agent_mcp_oauth_configuration_destroy(context, &configuration) == CODEX_AGENT_STATUS_OK);

        CHECK(codex_agent_mcp_oauth_configuration_create(
                  context, 1, LITERAL_VIEW("client"), 1, 65535, &configuration) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_mcp_oauth_configuration_has_client_id(context, configuration, &present) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(present == 1);
        CHECK_COPY(codex_agent_mcp_oauth_configuration_client_id_copy, context, configuration, "client");
        CHECK(codex_agent_mcp_oauth_configuration_callback_port(
                  context, configuration, &present, &projected) == CODEX_AGENT_STATUS_OK);
        CHECK(present == 1);
        CHECK(projected == 65535);
        CHECK(codex_agent_mcp_oauth_configuration_destroy(context, &configuration) == CODEX_AGENT_STATUS_OK);
    }

    {
        const codex_agent_mcp_tool_approval_t approvals[] = {
            CODEX_AGENT_MCP_TOOL_APPROVAL_AUTO,
            CODEX_AGENT_MCP_TOOL_APPROVAL_PROMPT,
            CODEX_AGENT_MCP_TOOL_APPROVAL_WRITES,
            CODEX_AGENT_MCP_TOOL_APPROVAL_APPROVE,
        };
        size_t index;
        for (index = 0u; index < sizeof(approvals) / sizeof(approvals[0]); ++index) {
            codex_agent_mcp_tool_configuration_t *configuration = NULL;
            CHECK(codex_agent_mcp_tool_configuration_create(
                      context, 1, approvals[index], &configuration) == CODEX_AGENT_STATUS_OK);
            CHECK(codex_agent_mcp_tool_configuration_approval(context, configuration, &present, &projected) ==
                  CODEX_AGENT_STATUS_OK);
            CHECK(present == 1);
            CHECK(projected == approvals[index]);
            CHECK(codex_agent_mcp_tool_configuration_destroy(context, &configuration) == CODEX_AGENT_STATUS_OK);
        }
        {
            codex_agent_mcp_tool_configuration_t *configuration = NULL;
            CHECK(codex_agent_mcp_tool_configuration_create(context, 0, 0, &configuration) ==
                  CODEX_AGENT_STATUS_OK);
            CHECK(codex_agent_mcp_tool_configuration_approval(context, configuration, &present, &projected) ==
                  CODEX_AGENT_STATUS_OK);
            CHECK(present == 0);
            CHECK(projected == 0);
            CHECK(codex_agent_mcp_tool_configuration_destroy(context, &configuration) == CODEX_AGENT_STATUS_OK);
        }
    }

    {
        const codex_agent_elicitation_validation_reason_t reasons[] = {
            CODEX_AGENT_ELICITATION_VALIDATION_MISSING_REQUIRED,
            CODEX_AGENT_ELICITATION_VALIDATION_UNKNOWN_FIELD,
            CODEX_AGENT_ELICITATION_VALIDATION_INVALID_TYPE,
            CODEX_AGENT_ELICITATION_VALIDATION_NON_FINITE_NUMBER,
            CODEX_AGENT_ELICITATION_VALIDATION_BELOW_MINIMUM,
            CODEX_AGENT_ELICITATION_VALIDATION_ABOVE_MAXIMUM,
            CODEX_AGENT_ELICITATION_VALIDATION_NON_INTEGER,
            CODEX_AGENT_ELICITATION_VALIDATION_INVALID_FORMAT,
            CODEX_AGENT_ELICITATION_VALIDATION_INVALID_SELECTION,
            CODEX_AGENT_ELICITATION_VALIDATION_DUPLICATE_SELECTION,
        };
        size_t index;
        for (index = 0u; index < sizeof(reasons) / sizeof(reasons[0]); ++index) {
            codex_agent_elicitation_validation_issue_t *issue = NULL;
            CHECK(codex_agent_elicitation_validation_issue_create(
                      context, LITERAL_VIEW("field"), reasons[index], &issue) == CODEX_AGENT_STATUS_OK);
            CHECK_COPY(codex_agent_elicitation_validation_issue_field_name_copy, context, issue, "field");
            CHECK(codex_agent_elicitation_validation_issue_reason(context, issue, &projected) ==
                  CODEX_AGENT_STATUS_OK);
            CHECK(projected == reasons[index]);
            CHECK(codex_agent_elicitation_validation_issue_destroy(context, &issue) == CODEX_AGENT_STATUS_OK);
        }
    }

    {
        const codex_agent_plan_step_status_t statuses[] = {
            CODEX_AGENT_PLAN_STEP_PENDING,
            CODEX_AGENT_PLAN_STEP_IN_PROGRESS,
            CODEX_AGENT_PLAN_STEP_COMPLETED,
        };
        size_t index;
        for (index = 0u; index < sizeof(statuses) / sizeof(statuses[0]); ++index) {
            codex_agent_plan_step_t *step = NULL;
            CHECK(codex_agent_plan_step_create(
                      context, LITERAL_VIEW("step"), statuses[index], &step) == CODEX_AGENT_STATUS_OK);
            CHECK_COPY(codex_agent_plan_step_text_copy, context, step, "step");
            CHECK(codex_agent_plan_step_status(context, step, &projected) == CODEX_AGENT_STATUS_OK);
            CHECK(projected == statuses[index]);
            CHECK(codex_agent_plan_step_destroy(context, &step) == CODEX_AGENT_STATUS_OK);
            CHECK(step == NULL);
        }
    }

    {
        codex_agent_plan_step_t *step = NULL;
        CHECK(codex_agent_plan_step_create(context, LITERAL_VIEW("step"), 3, &step) ==
              CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK(step == NULL);
    }

    CHECK(codex_agent_context_destroy(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(other_context == NULL);
    CHECK(context == NULL);
    return 0;
}
