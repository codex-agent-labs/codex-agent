#include "codex_agent.h"

#include <stdint.h>
#include <string.h>

#define CHECK(condition)       \
    do {                       \
        if (!(condition)) {    \
            return __LINE__;   \
        }                      \
    } while (0)

#define CHECK_COPY(function, context, handle, expected)                         \
    do {                                                                        \
        uint8_t copied[256] = {0};                                              \
        const char *expected_value = (expected);                                \
        const size_t expected_size = strlen(expected_value);                    \
        size_t required = SIZE_MAX;                                             \
        CHECK((function)((context), (handle), NULL, 0U, &required) ==           \
              (expected_size == 0U ? CODEX_AGENT_STATUS_OK :                    \
                                     CODEX_AGENT_STATUS_BUFFER_TOO_SMALL));     \
        CHECK(required == expected_size);                                       \
        CHECK((function)((context), (handle), copied, sizeof(copied),           \
                         &required) == CODEX_AGENT_STATUS_OK);                   \
        CHECK(required == expected_size);                                       \
        CHECK(memcmp(copied, expected_value, expected_size) == 0);              \
    } while (0)

#define CHECK_INDEX_COPY(function, context, handle, index, expected)            \
    do {                                                                        \
        uint8_t copied[256] = {0};                                              \
        const char *expected_value = (expected);                                \
        const size_t expected_size = strlen(expected_value);                    \
        size_t copy_required = SIZE_MAX;                                        \
        CHECK((function)((context), (handle), (index), NULL, 0U, &copy_required) == \
              (expected_size == 0U ? CODEX_AGENT_STATUS_OK :                    \
                                     CODEX_AGENT_STATUS_BUFFER_TOO_SMALL));     \
        CHECK(copy_required == expected_size);                                  \
        CHECK((function)((context), (handle), (index), copied, sizeof(copied),     \
                         &copy_required) == CODEX_AGENT_STATUS_OK);                \
        CHECK(copy_required == expected_size);                                  \
        CHECK(memcmp(copied, expected_value, expected_size) == 0);              \
    } while (0)

static codex_agent_string_view_t string_view(const char *value) {
    const codex_agent_string_view_t view = {
        (const uint8_t *)value,
        strlen(value)};
    return view;
}

static int verify_text_list(
    codex_agent_context_t *context,
    codex_agent_context_t *other_context) {
    char first_bytes[] = "alpha";
    char second_bytes[] = "beta";
    const uint8_t malformed_bytes[] = {UINT8_C(0xc3), UINT8_C(0x28)};
    codex_agent_string_view_t values[] = {
        string_view(first_bytes),
        string_view(second_bytes),
        string_view(first_bytes),
        {NULL, 0U},
    };
    const codex_agent_string_view_t malformed[] = {
        {malformed_bytes, sizeof(malformed_bytes)},
    };
    codex_agent_form_text_list_value_t *value = NULL;
    codex_agent_form_text_list_value_t *empty = NULL;
    codex_agent_form_text_list_value_t *invalid = NULL;
    codex_agent_elicitation_validation_t *validation = NULL;
    size_t count = SIZE_MAX;
    size_t required = SIZE_MAX;

    CHECK(codex_agent_form_text_list_value_create(context, NULL, 0U, &empty) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(empty != NULL);
    CHECK(codex_agent_form_text_list_value_count(context, empty, &count) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(count == 0U);
    required = SIZE_MAX;
    CHECK(codex_agent_form_text_list_value_copy_at(
              context, empty, 0U, NULL, 0U, &required) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(required == SIZE_MAX);
    CHECK(codex_agent_form_text_list_value_destroy(context, &empty) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(empty == NULL);

    CHECK(codex_agent_form_text_list_value_create(
              context, values, sizeof(values) / sizeof(values[0]), &value) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(value != NULL);
    first_bytes[0] = 'X';
    second_bytes[0] = 'X';
    values[1] = string_view("changed");
    CHECK(codex_agent_form_text_list_value_count(context, value, &count) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(count == 4U);
    CHECK_INDEX_COPY(codex_agent_form_text_list_value_copy_at, context, value, 0U, "alpha");
    CHECK_INDEX_COPY(codex_agent_form_text_list_value_copy_at, context, value, 1U, "beta");
    CHECK_INDEX_COPY(codex_agent_form_text_list_value_copy_at, context, value, 2U, "alpha");
    CHECK_INDEX_COPY(codex_agent_form_text_list_value_copy_at, context, value, 3U, "");

    CHECK(codex_agent_form_text_list_value_create(
              context, values, sizeof(values) / sizeof(values[0]), &value) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(value != NULL);
    CHECK(codex_agent_form_text_list_value_create(context, NULL, 1U, &invalid) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid == NULL);
    CHECK(codex_agent_form_text_list_value_create(context, values, 0U, &invalid) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid == NULL);
    CHECK(codex_agent_form_text_list_value_create(context, malformed, 1U, &invalid) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid == NULL);
    CHECK(codex_agent_form_text_list_value_create(context, NULL, 0U, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_form_text_list_value_create(NULL, NULL, 0U, &invalid) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid == NULL);

    count = SIZE_MAX;
    CHECK(codex_agent_form_text_list_value_count(other_context, value, &count) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(count == SIZE_MAX);
    CHECK(codex_agent_form_text_list_value_count(context, value, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    required = SIZE_MAX;
    CHECK(codex_agent_form_text_list_value_copy_at(
              context, value, 4U, NULL, 0U, &required) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(required == SIZE_MAX);
    CHECK(codex_agent_form_text_list_value_copy_at(
              context, value, 0U, NULL, 0U, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);

    CHECK(codex_agent_elicitation_validation_create(context, NULL, 0U, &validation) ==
          CODEX_AGENT_STATUS_OK);
    count = SIZE_MAX;
    CHECK(codex_agent_form_text_list_value_count(
              context, (codex_agent_form_text_list_value_t *)validation, &count) ==
          CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(count == SIZE_MAX);
    {
        codex_agent_form_text_list_value_t *wrong =
            (codex_agent_form_text_list_value_t *)validation;
        CHECK(codex_agent_form_text_list_value_destroy(context, &wrong) ==
              CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
        CHECK((void *)wrong == (void *)validation);
    }

    {
        codex_agent_form_text_list_value_t *stale = value;
        CHECK(codex_agent_form_text_list_value_destroy(context, &value) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(value == NULL);
        CHECK(codex_agent_form_text_list_value_destroy(context, &value) ==
              CODEX_AGENT_STATUS_OK);
        count = SIZE_MAX;
        CHECK(codex_agent_form_text_list_value_count(context, stale, &count) ==
              CODEX_AGENT_STATUS_STALE_HANDLE);
        CHECK(count == SIZE_MAX);
    }
    CHECK(codex_agent_form_text_list_value_destroy(context, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_elicitation_validation_destroy(context, &validation) ==
          CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_validation(
    codex_agent_context_t *context,
    codex_agent_context_t *other_context) {
    codex_agent_string_view_t first_name = string_view("first");
    codex_agent_string_view_t second_name = string_view("second");
    codex_agent_string_view_t other_name = string_view("other");
    codex_agent_elicitation_validation_issue_t *first = NULL;
    codex_agent_elicitation_validation_issue_t *second = NULL;
    codex_agent_elicitation_validation_issue_t *other = NULL;
    codex_agent_elicitation_validation_issue_t *children[3] = {NULL, NULL, NULL};
    codex_agent_elicitation_validation_issue_t *inputs[3];
    codex_agent_elicitation_validation_t *validation = NULL;
    codex_agent_elicitation_validation_t *empty = NULL;
    codex_agent_elicitation_validation_t *invalid = NULL;
    codex_agent_form_text_list_value_t *text = NULL;
    size_t count = SIZE_MAX;
    int32_t is_valid = -1;
    int32_t reason = -1;
    size_t index;

    CHECK(codex_agent_elicitation_validation_issue_create(
              context,
              &first_name,
              CODEX_AGENT_ELICITATION_VALIDATION_MISSING_REQUIRED,
              &first) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_elicitation_validation_issue_create(
              context,
              &second_name,
              CODEX_AGENT_ELICITATION_VALIDATION_DUPLICATE_SELECTION,
              &second) == CODEX_AGENT_STATUS_OK);
    inputs[0] = first;
    inputs[1] = second;
    inputs[2] = first;
    CHECK(codex_agent_elicitation_validation_create(context, inputs, 3U, &validation) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(validation != NULL);
    inputs[0] = NULL;
    inputs[1] = NULL;
    inputs[2] = NULL;
    CHECK(codex_agent_elicitation_validation_issue_destroy(context, &first) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_elicitation_validation_issue_destroy(context, &second) ==
          CODEX_AGENT_STATUS_OK);

    CHECK(codex_agent_elicitation_validation_issue_count(context, validation, &count) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(count == 3U);
    CHECK(codex_agent_elicitation_validation_is_valid(context, validation, &is_valid) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(is_valid == 0);
    for (index = 0U; index < 3U; ++index) {
        CHECK(codex_agent_elicitation_validation_issue_at(
                  context, validation, index, &children[index]) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(children[index] != NULL);
    }
    CHECK(children[0] != children[2]);
    CHECK_COPY(
        codex_agent_elicitation_validation_issue_field_name_copy,
        context,
        children[0],
        "first");
    CHECK_COPY(
        codex_agent_elicitation_validation_issue_field_name_copy,
        context,
        children[1],
        "second");
    CHECK_COPY(
        codex_agent_elicitation_validation_issue_field_name_copy,
        context,
        children[2],
        "first");
    CHECK(codex_agent_elicitation_validation_issue_reason(context, children[0], &reason) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(reason == CODEX_AGENT_ELICITATION_VALIDATION_MISSING_REQUIRED);
    CHECK(codex_agent_elicitation_validation_issue_reason(context, children[1], &reason) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(reason == CODEX_AGENT_ELICITATION_VALIDATION_DUPLICATE_SELECTION);

    CHECK(codex_agent_elicitation_validation_destroy(context, &validation) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(validation == NULL);
    CHECK_COPY(
        codex_agent_elicitation_validation_issue_field_name_copy,
        context,
        children[0],
        "first");
    for (index = 0U; index < 3U; ++index) {
        CHECK(codex_agent_elicitation_validation_issue_destroy(context, &children[index]) ==
              CODEX_AGENT_STATUS_OK);
    }

    CHECK(codex_agent_elicitation_validation_create(context, NULL, 0U, &empty) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_elicitation_validation_issue_count(context, empty, &count) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(count == 0U);
    CHECK(codex_agent_elicitation_validation_is_valid(context, empty, &is_valid) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(is_valid == 1);
    CHECK(codex_agent_elicitation_validation_issue_at(context, empty, 0U, &first) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(first == NULL);
    CHECK(codex_agent_elicitation_validation_destroy(context, &empty) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_elicitation_validation_destroy(context, &empty) ==
          CODEX_AGENT_STATUS_OK);

    inputs[0] = NULL;
    CHECK(codex_agent_elicitation_validation_create(context, inputs, 1U, &invalid) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid == NULL);
    CHECK(codex_agent_elicitation_validation_create(context, NULL, 1U, &invalid) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_elicitation_validation_create(context, inputs, 0U, &invalid) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_elicitation_validation_create(context, inputs, SIZE_MAX, &invalid) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_elicitation_validation_create(context, NULL, 0U, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);

    CHECK(codex_agent_elicitation_validation_issue_create(
              other_context,
              &other_name,
              CODEX_AGENT_ELICITATION_VALIDATION_INVALID_TYPE,
              &other) == CODEX_AGENT_STATUS_OK);
    inputs[0] = other;
    CHECK(codex_agent_elicitation_validation_create(context, inputs, 1U, &invalid) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(invalid == NULL);

    CHECK(codex_agent_form_text_list_value_create(context, NULL, 0U, &text) ==
          CODEX_AGENT_STATUS_OK);
    inputs[0] = (codex_agent_elicitation_validation_issue_t *)text;
    CHECK(codex_agent_elicitation_validation_create(context, inputs, 1U, &invalid) ==
          CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(invalid == NULL);

    {
        codex_agent_elicitation_validation_issue_t *stale = NULL;
        codex_agent_string_view_t stale_name = string_view("stale");
        CHECK(codex_agent_elicitation_validation_issue_create(
                  context,
                  &stale_name,
                  CODEX_AGENT_ELICITATION_VALIDATION_NON_FINITE_NUMBER,
                  &stale) == CODEX_AGENT_STATUS_OK);
        inputs[0] = stale;
        CHECK(codex_agent_elicitation_validation_issue_destroy(context, &stale) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_elicitation_validation_create(context, inputs, 1U, &invalid) ==
              CODEX_AGENT_STATUS_STALE_HANDLE);
        CHECK(invalid == NULL);
    }

    CHECK(codex_agent_elicitation_validation_create(context, NULL, 0U, &validation) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_elicitation_validation_create(context, NULL, 0U, &validation) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    count = SIZE_MAX;
    is_valid = -1;
    CHECK(codex_agent_elicitation_validation_issue_count(other_context, validation, &count) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(count == SIZE_MAX);
    CHECK(codex_agent_elicitation_validation_is_valid(other_context, validation, &is_valid) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(is_valid == -1);
    CHECK(codex_agent_elicitation_validation_issue_count(
              context, (codex_agent_elicitation_validation_t *)text, &count) ==
          CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(count == SIZE_MAX);
    CHECK(codex_agent_elicitation_validation_issue_count(context, validation, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_elicitation_validation_is_valid(context, validation, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_elicitation_validation_issue_at(context, validation, 0U, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    first = other;
    CHECK(codex_agent_elicitation_validation_issue_at(context, validation, 0U, &first) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(first == other);
    first = NULL;
    CHECK(codex_agent_elicitation_validation_issue_at(other_context, validation, 0U, &first) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(first == NULL);
    {
        codex_agent_elicitation_validation_t *wrong =
            (codex_agent_elicitation_validation_t *)text;
        CHECK(codex_agent_elicitation_validation_destroy(context, &wrong) ==
              CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
        CHECK((void *)wrong == (void *)text);
    }
    {
        codex_agent_elicitation_validation_t *wrong_context = validation;
        CHECK(codex_agent_elicitation_validation_destroy(other_context, &wrong_context) ==
              CODEX_AGENT_STATUS_WRONG_CONTEXT);
        CHECK(wrong_context == validation);
    }
    {
        codex_agent_elicitation_validation_t *stale = validation;
        CHECK(codex_agent_elicitation_validation_destroy(context, &validation) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_elicitation_validation_destroy(context, &validation) ==
              CODEX_AGENT_STATUS_OK);
        count = SIZE_MAX;
        CHECK(codex_agent_elicitation_validation_issue_count(context, stale, &count) ==
              CODEX_AGENT_STATUS_STALE_HANDLE);
        CHECK(count == SIZE_MAX);
    }
    CHECK(codex_agent_elicitation_validation_destroy(context, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_form_text_list_value_destroy(context, &text) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_elicitation_validation_issue_destroy(other_context, &other) ==
          CODEX_AGENT_STATUS_OK);
    return 0;
}

int main(void) {
    codex_agent_context_t *context = NULL;
    codex_agent_context_t *other_context = NULL;

    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_create(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(context != NULL);
    CHECK(other_context != NULL);
    CHECK(verify_text_list(context, other_context) == 0);
    CHECK(verify_validation(context, other_context) == 0);
    CHECK(codex_agent_context_destroy(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(other_context == NULL);
    CHECK(context == NULL);
    return 0;
}
