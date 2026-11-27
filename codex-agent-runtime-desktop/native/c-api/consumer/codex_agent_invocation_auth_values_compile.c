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
        uint8_t copied[256];                                                       \
        const char *expected_value = (expected);                                   \
        const size_t expected_size = strlen(expected_value);                       \
        size_t copy_required = SIZE_MAX;                                           \
        CHECK((function)((context), (handle), NULL, 0U, &copy_required) ==         \
              CODEX_AGENT_STATUS_BUFFER_TOO_SMALL);                               \
        CHECK(copy_required == expected_size);                                     \
        CHECK((function)((context), (handle), copied, sizeof(copied), &copy_required) == \
              CODEX_AGENT_STATUS_OK);                                              \
        CHECK(copy_required == expected_size);                                     \
        CHECK(memcmp(copied, expected_value, expected_size) == 0);                 \
    } while (0)

static codex_agent_string_view_t string_view(const char *value) {
    const codex_agent_string_view_t view = {
        (const uint8_t *)value,
        strlen(value)};
    return view;
}

static int verify_invocations(
    codex_agent_context_t *context,
    codex_agent_context_t *other_context) {
    char plugin_name_bytes[] = "review-tools";
    char plugin_uri_bytes[] = "plugin://review@official";
    char skill_name_bytes[] = "review";
    char skill_path_bytes[] = "/skills/review.md";
    codex_agent_string_view_t plugin_name = string_view(plugin_name_bytes);
    codex_agent_string_view_t plugin_uri = string_view(plugin_uri_bytes);
    codex_agent_string_view_t skill_name = string_view(skill_name_bytes);
    codex_agent_string_view_t skill_path = string_view(skill_path_bytes);
    const uint8_t malformed_bytes[] = {UINT8_C(0xc3), UINT8_C(0x28)};
    const codex_agent_string_view_t malformed = {malformed_bytes, sizeof(malformed_bytes)};
    codex_agent_invocation_plugin_t *plugin = NULL;
    codex_agent_invocation_skill_t *skill = NULL;
    codex_agent_invocation_plugin_t *invalid_plugin = NULL;
    codex_agent_invocation_skill_t *invalid_skill = NULL;
    size_t required = SIZE_MAX;

    CHECK(codex_agent_invocation_plugin_create(
              context, &plugin_name, &plugin_uri, &plugin) == CODEX_AGENT_STATUS_OK);
    CHECK(plugin != NULL);
    CHECK(codex_agent_invocation_skill_create(
              context, &skill_name, &skill_path, &skill) == CODEX_AGENT_STATUS_OK);
    CHECK(skill != NULL);
    plugin_name_bytes[0] = 'X';
    plugin_uri_bytes[0] = 'X';
    skill_name_bytes[0] = 'X';
    skill_path_bytes[0] = 'X';

    CHECK_HANDLE_COPY(
        codex_agent_invocation_plugin_name_copy,
        context,
        plugin,
        "review-tools");
    CHECK_HANDLE_COPY(
        codex_agent_invocation_plugin_uri_copy,
        context,
        plugin,
        "plugin://review@official");
    CHECK_HANDLE_COPY(
        codex_agent_invocation_plugin_key_copy,
        context,
        plugin,
        "plugin:plugin://review@official");
    CHECK_HANDLE_COPY(
        codex_agent_invocation_skill_name_copy,
        context,
        skill,
        "review");
    CHECK_HANDLE_COPY(
        codex_agent_invocation_skill_path_copy,
        context,
        skill,
        "/skills/review.md");
    CHECK_HANDLE_COPY(
        codex_agent_invocation_skill_key_copy,
        context,
        skill,
        "skill:/skills/review.md");

    required = SIZE_MAX;
    CHECK(codex_agent_invocation_plugin_name_copy(
              context,
              (codex_agent_invocation_plugin_t *)skill,
              NULL,
              0U,
              &required) == CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(required == SIZE_MAX);
    CHECK(codex_agent_invocation_plugin_name_copy(
              other_context,
              plugin,
              NULL,
              0U,
              &required) == CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(required == SIZE_MAX);

    CHECK(codex_agent_invocation_plugin_create(
              context, &plugin_name, &plugin_uri, &plugin) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_invocation_skill_create(
              context, &skill_name, &skill_path, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_invocation_plugin_create(
              context, NULL, &plugin_uri, &invalid_plugin) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid_plugin == NULL);
    CHECK(codex_agent_invocation_plugin_create(
              context, &plugin_name, &malformed, &invalid_plugin) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid_plugin == NULL);
    CHECK(codex_agent_invocation_skill_create(
              context, NULL, &skill_path, &invalid_skill) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid_skill == NULL);
    CHECK(codex_agent_invocation_skill_create(
              context, &skill_name, &malformed, &invalid_skill) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid_skill == NULL);

    {
        codex_agent_invocation_plugin_t *wrong =
            (codex_agent_invocation_plugin_t *)skill;
        CHECK(codex_agent_invocation_plugin_destroy(context, &wrong) ==
              CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
        CHECK(wrong == (codex_agent_invocation_plugin_t *)skill);
    }
    {
        codex_agent_invocation_plugin_t *stale = plugin;
        CHECK(codex_agent_invocation_plugin_destroy(context, &plugin) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(plugin == NULL);
        CHECK(codex_agent_invocation_plugin_destroy(context, &plugin) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_invocation_plugin_key_copy(
                  context, stale, NULL, 0U, &required) ==
              CODEX_AGENT_STATUS_STALE_HANDLE);
    }
    CHECK(codex_agent_invocation_skill_destroy(context, &skill) == CODEX_AGENT_STATUS_OK);
    CHECK(skill == NULL);
    CHECK(codex_agent_invocation_skill_destroy(context, &skill) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_pending_approval(
    codex_agent_context_t *context,
    codex_agent_context_t *other_context) {
    char conversation_bytes[] = "conversation-17";
    char request_bytes[] = "approval-9";
    char title_bytes[] = "Run command?";
    char details_bytes[] = "git status";
    codex_agent_string_view_t conversation_value = string_view(conversation_bytes);
    codex_agent_string_view_t request_id = string_view(request_bytes);
    codex_agent_string_view_t title = string_view(title_bytes);
    codex_agent_string_view_t details = string_view(details_bytes);
    const codex_agent_string_view_t other_value = string_view("other-conversation");
    const uint8_t malformed_bytes[] = {UINT8_C(0xc3), UINT8_C(0x28)};
    const codex_agent_string_view_t malformed = {malformed_bytes, sizeof(malformed_bytes)};
    codex_agent_conversation_id_t *conversation_id = NULL;
    codex_agent_conversation_id_t *other_conversation_id = NULL;
    codex_agent_conversation_id_t *first_nested = NULL;
    codex_agent_conversation_id_t *second_nested = NULL;
    codex_agent_pending_approval_t *approval = NULL;
    codex_agent_pending_approval_t *invalid = NULL;
    size_t required = SIZE_MAX;

    CHECK(codex_agent_conversation_id_create(
              context, &conversation_value, &conversation_id) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_pending_approval_create(
              context,
              &request_id,
              conversation_id,
              &title,
              &details,
              &approval) == CODEX_AGENT_STATUS_OK);
    CHECK(approval != NULL);
    conversation_bytes[0] = 'X';
    request_bytes[0] = 'X';
    title_bytes[0] = 'X';
    details_bytes[0] = 'X';

    CHECK_HANDLE_COPY(
        codex_agent_pending_approval_request_id_copy,
        context,
        approval,
        "approval-9");
    CHECK_HANDLE_COPY(
        codex_agent_pending_approval_title_copy,
        context,
        approval,
        "Run command?");
    CHECK_HANDLE_COPY(
        codex_agent_pending_approval_details_copy,
        context,
        approval,
        "git status");

    CHECK(codex_agent_pending_approval_create(
              context, NULL, conversation_id, &title, &details, &invalid) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid == NULL);
    CHECK(codex_agent_pending_approval_create(
              context, &request_id, conversation_id, &title, &malformed, &invalid) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid == NULL);
    CHECK(codex_agent_pending_approval_create(
              context, &request_id, NULL, &title, &details, &invalid) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid == NULL);
    CHECK(codex_agent_pending_approval_create(
              context, &request_id, conversation_id, &title, &details, &approval) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);

    CHECK(codex_agent_conversation_id_create(
              other_context,
              &other_value,
              &other_conversation_id) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_pending_approval_create(
              context,
              &request_id,
              other_conversation_id,
              &title,
              &details,
              &invalid) == CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(invalid == NULL);

    CHECK(codex_agent_conversation_id_destroy(context, &conversation_id) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(conversation_id == NULL);
    CHECK(codex_agent_pending_approval_conversation_id(
              context, approval, &first_nested) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_pending_approval_conversation_id(
              context, approval, &second_nested) == CODEX_AGENT_STATUS_OK);
    CHECK(first_nested != NULL);
    CHECK(second_nested != NULL);
    CHECK(first_nested != second_nested);

    {
        codex_agent_conversation_id_t *occupied = first_nested;
        CHECK(codex_agent_pending_approval_conversation_id(
                  context, approval, &occupied) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK(occupied == first_nested);
    }
    CHECK(codex_agent_pending_approval_conversation_id(
              context,
              (codex_agent_pending_approval_t *)first_nested,
              &conversation_id) == CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(conversation_id == NULL);
    CHECK(codex_agent_pending_approval_request_id_copy(
              other_context,
              approval,
              NULL,
              0U,
              &required) == CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(required == SIZE_MAX);

    {
        codex_agent_pending_approval_t *wrong =
            (codex_agent_pending_approval_t *)first_nested;
        CHECK(codex_agent_pending_approval_destroy(context, &wrong) ==
              CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
        CHECK(wrong == (codex_agent_pending_approval_t *)first_nested);
    }
    {
        codex_agent_pending_approval_t *stale = approval;
        CHECK(codex_agent_pending_approval_destroy(context, &approval) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(approval == NULL);
        CHECK(codex_agent_pending_approval_destroy(context, &approval) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_pending_approval_request_id_copy(
                  context, stale, NULL, 0U, &required) == CODEX_AGENT_STATUS_STALE_HANDLE);
    }

    CHECK_HANDLE_COPY(
        codex_agent_conversation_id_value_copy,
        context,
        first_nested,
        "conversation-17");
    CHECK_HANDLE_COPY(
        codex_agent_conversation_id_value_copy,
        context,
        second_nested,
        "conversation-17");
    CHECK(codex_agent_conversation_id_destroy(context, &first_nested) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(first_nested == NULL);
    CHECK(codex_agent_conversation_id_destroy(context, &first_nested) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_conversation_id_destroy(context, &second_nested) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_conversation_id_destroy(other_context, &other_conversation_id) ==
          CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_authentication_methods(
    codex_agent_context_t *context,
    codex_agent_context_t *other_context) {
    char api_key_bytes[] = "sk-live-secret";
    codex_agent_string_view_t api_key_value = string_view(api_key_bytes);
    const codex_agent_string_view_t blank = string_view(" \t\n");
    const uint8_t malformed_bytes[] = {UINT8_C(0xc3), UINT8_C(0x28)};
    const codex_agent_string_view_t malformed = {malformed_bytes, sizeof(malformed_bytes)};
    codex_agent_authentication_method_api_key_t *api_key = NULL;
    codex_agent_authentication_method_api_key_t *invalid = NULL;
    codex_agent_authentication_method_chat_gpt_browser_t *first_browser = NULL;
    codex_agent_authentication_method_chat_gpt_browser_t *second_browser = NULL;
    codex_agent_authentication_method_chat_gpt_device_code_t *device_code = NULL;
    codex_agent_authentication_method_chat_gpt_device_code_t *invalid_device_code = NULL;
    size_t required = SIZE_MAX;

    CHECK(codex_agent_authentication_method_api_key_create(
              context, &api_key_value, &api_key) == CODEX_AGENT_STATUS_OK);
    CHECK(api_key != NULL);
    api_key_bytes[0] = 'X';
    CHECK_HANDLE_COPY(
        codex_agent_authentication_method_api_key_value_copy,
        context,
        api_key,
        "sk-live-secret");

    CHECK(codex_agent_authentication_method_api_key_create(
              context, NULL, &invalid) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid == NULL);
    CHECK(codex_agent_authentication_method_api_key_create(
              context, &malformed, &invalid) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid == NULL);
    CHECK(codex_agent_authentication_method_api_key_create(
              context, &blank, &invalid) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid == NULL);
    CHECK(codex_agent_authentication_method_api_key_create(
              context, &api_key_value, &api_key) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);

    CHECK(codex_agent_authentication_method_chat_gpt_browser_create(
              context, &first_browser) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_authentication_method_chat_gpt_browser_create(
              context, &second_browser) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_authentication_method_chat_gpt_device_code_create(
              context, &device_code) == CODEX_AGENT_STATUS_OK);
    CHECK(first_browser != NULL);
    CHECK(second_browser != NULL);
    CHECK(device_code != NULL);
    CHECK(first_browser != second_browser);
    CHECK((void *)first_browser != (void *)device_code);
    CHECK((void *)second_browser != (void *)device_code);

    CHECK(codex_agent_authentication_method_chat_gpt_browser_create(
              context, &first_browser) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_authentication_method_chat_gpt_device_code_create(
              NULL, &invalid_device_code) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid_device_code == NULL);
    CHECK(codex_agent_authentication_method_chat_gpt_device_code_create(
              context, NULL) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_authentication_method_api_key_value_copy(
              context,
              (codex_agent_authentication_method_api_key_t *)first_browser,
              NULL,
              0U,
              &required) == CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(required == SIZE_MAX);
    CHECK(codex_agent_authentication_method_api_key_value_copy(
              other_context,
              api_key,
              NULL,
              0U,
              &required) == CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(required == SIZE_MAX);

    {
        codex_agent_authentication_method_chat_gpt_browser_t *wrong =
            (codex_agent_authentication_method_chat_gpt_browser_t *)device_code;
        CHECK(codex_agent_authentication_method_chat_gpt_browser_destroy(
                  context, &wrong) == CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
        CHECK(wrong ==
              (codex_agent_authentication_method_chat_gpt_browser_t *)device_code);
    }
    {
        codex_agent_authentication_method_api_key_t *stale = api_key;
        CHECK(codex_agent_authentication_method_api_key_destroy(context, &api_key) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(api_key == NULL);
        CHECK(codex_agent_authentication_method_api_key_destroy(context, &api_key) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_authentication_method_api_key_value_copy(
                  context, stale, NULL, 0U, &required) == CODEX_AGENT_STATUS_STALE_HANDLE);
    }

    CHECK(codex_agent_authentication_method_chat_gpt_browser_destroy(
              context, &first_browser) == CODEX_AGENT_STATUS_OK);
    CHECK(first_browser == NULL);
    CHECK(codex_agent_authentication_method_chat_gpt_browser_destroy(
              context, &first_browser) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_authentication_method_chat_gpt_browser_destroy(
              context, &second_browser) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_authentication_method_chat_gpt_device_code_destroy(
              context, &device_code) == CODEX_AGENT_STATUS_OK);
    CHECK(device_code == NULL);
    CHECK(codex_agent_authentication_method_chat_gpt_device_code_destroy(
              context, &device_code) == CODEX_AGENT_STATUS_OK);
    return 0;
}

int main(void) {
    codex_agent_context_t *context = NULL;
    codex_agent_context_t *other_context = NULL;

    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_create(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(context != NULL);
    CHECK(other_context != NULL);
    CHECK(verify_invocations(context, other_context) == 0);
    CHECK(verify_pending_approval(context, other_context) == 0);
    CHECK(verify_authentication_methods(context, other_context) == 0);
    CHECK(codex_agent_context_destroy(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(other_context == NULL);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(context == NULL);
    return 0;
}
