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
#define EMPTY_VIEW STRING_VIEW(NULL, 0u)

#define CHECK_COPY(function, context, handle, expected) \
    do { \
        const char *copy_expected = (expected); \
        const size_t copy_size = strlen(copy_expected); \
        uint8_t copy_buffer[128] = {0}; \
        size_t copy_required = SIZE_MAX; \
        CHECK(copy_size <= sizeof(copy_buffer)); \
        CHECK((function)((context), (handle), NULL, 0u, &copy_required) == \
              (copy_size == 0u ? CODEX_AGENT_STATUS_OK : CODEX_AGENT_STATUS_BUFFER_TOO_SMALL)); \
        CHECK(copy_required == copy_size); \
        CHECK((function)((context), (handle), copy_buffer, sizeof(copy_buffer), &copy_required) == \
              CODEX_AGENT_STATUS_OK); \
        CHECK(memcmp(copy_buffer, copy_expected, copy_size) == 0); \
    } while (0)

static int check_handler_carriers(
    codex_agent_context_t *context,
    codex_agent_hook_handler_t **out_command_handler) {
    codex_agent_hook_handler_agent_t *agent = NULL;
    codex_agent_hook_handler_command_t *command = NULL;
    codex_agent_hook_handler_mcp_tool_t *mcp_tool = NULL;
    codex_agent_hook_handler_prompt_t *prompt = NULL;
    codex_agent_hook_handler_t *agent_handler = NULL;
    codex_agent_hook_handler_t *command_handler = NULL;
    codex_agent_hook_handler_t *mcp_handler = NULL;
    codex_agent_hook_handler_t *prompt_handler = NULL;
    codex_agent_hook_handler_kind_t kind = -1;
    int32_t is_async = -1;

    CHECK(codex_agent_hook_handler_agent_acquire(context, &agent) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_handler_from_agent(context, agent, &agent_handler) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_handler_agent_destroy(context, &agent) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_handler_kind(context, agent_handler, &kind) == CODEX_AGENT_STATUS_OK);
    CHECK(kind == CODEX_AGENT_HOOK_HANDLER_KIND_AGENT);
    CHECK(codex_agent_hook_handler_agent(context, agent_handler, &agent) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_handler_agent_destroy(context, &agent) == CODEX_AGENT_STATUS_OK);

    CHECK(codex_agent_hook_handler_command_create(
              context, LITERAL_VIEW("command"), INT32_C(1), &command) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_handler_from_command(context, command, &command_handler) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_handler_command_destroy(context, &command) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_handler_kind(context, command_handler, &kind) == CODEX_AGENT_STATUS_OK);
    CHECK(kind == CODEX_AGENT_HOOK_HANDLER_KIND_COMMAND);
    CHECK(codex_agent_hook_handler_command(context, command_handler, &command) == CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_hook_handler_command_command_copy, context, command, "command");
    CHECK(codex_agent_hook_handler_command_is_async(context, command, &is_async) == CODEX_AGENT_STATUS_OK);
    CHECK(is_async == INT32_C(1));
    CHECK(codex_agent_hook_handler_command_destroy(context, &command) == CODEX_AGENT_STATUS_OK);

    CHECK(codex_agent_hook_handler_mcp_tool_create(
              context, LITERAL_VIEW("server"), LITERAL_VIEW("tool"), &mcp_tool) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_handler_from_mcp_tool(context, mcp_tool, &mcp_handler) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_handler_mcp_tool_destroy(context, &mcp_tool) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_handler_kind(context, mcp_handler, &kind) == CODEX_AGENT_STATUS_OK);
    CHECK(kind == CODEX_AGENT_HOOK_HANDLER_KIND_MCP_TOOL);
    CHECK(codex_agent_hook_handler_mcp_tool(context, mcp_handler, &mcp_tool) == CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_hook_handler_mcp_tool_server_copy, context, mcp_tool, "server");
    CHECK_COPY(codex_agent_hook_handler_mcp_tool_tool_copy, context, mcp_tool, "tool");
    CHECK(codex_agent_hook_handler_mcp_tool_destroy(context, &mcp_tool) == CODEX_AGENT_STATUS_OK);

    CHECK(codex_agent_hook_handler_prompt_acquire(context, &prompt) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_handler_from_prompt(context, prompt, &prompt_handler) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_handler_prompt_destroy(context, &prompt) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_handler_kind(context, prompt_handler, &kind) == CODEX_AGENT_STATUS_OK);
    CHECK(kind == CODEX_AGENT_HOOK_HANDLER_KIND_PROMPT);
    CHECK(codex_agent_hook_handler_prompt(context, prompt_handler, &prompt) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_handler_prompt_destroy(context, &prompt) == CODEX_AGENT_STATUS_OK);

    CHECK(codex_agent_hook_handler_command(context, agent_handler, &command) ==
          CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(command == NULL);
    CHECK(codex_agent_hook_handler_destroy(context, &agent_handler) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_handler_destroy(context, &mcp_handler) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_handler_destroy(context, &prompt_handler) == CODEX_AGENT_STATUS_OK);
    *out_command_handler = command_handler;
    return 0;
}

int main(void) {
    codex_agent_context_t *context = NULL;
    codex_agent_context_t *other_context = NULL;
    codex_agent_hook_handler_t *command_handler = NULL;
    codex_agent_hook_handler_t *projected_handler = NULL;
    codex_agent_hook_handler_command_t *projected_command = NULL;
    codex_agent_hook_t *hook = NULL;
    codex_agent_hook_t *stale_hook = NULL;
    codex_agent_hook_t *child_one = NULL;
    codex_agent_hook_t *child_two = NULL;
    codex_agent_hook_catalog_t *catalog = NULL;
    codex_agent_hook_t *hooks[3];
    int32_t projected = -1;
    int64_t timeout_seconds = INT64_MIN;
    size_t count = SIZE_MAX;
    size_t required = SIZE_MAX;
    uint8_t key[] = "hook-key";
    uint8_t current_hash[] = "hook-hash";
    uint8_t warning[] = "warning";
    const codex_agent_string_view_t warnings[] = {
        {(const uint8_t *)warning, sizeof(warning) - 1u},
        {(const uint8_t *)warning, sizeof(warning) - 1u},
        {NULL, 0u},
    };
    const codex_agent_string_view_t errors[] = {
        {(const uint8_t *)"error", sizeof("error") - 1u},
        {(const uint8_t *)"error", sizeof("error") - 1u},
    };

    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_create(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(check_handler_carriers(context, &command_handler) == 0);
    CHECK(command_handler != NULL);

    CHECK(codex_agent_hook_create(
              context,
              STRING_VIEW(key, sizeof(key) - 1u),
              STRING_VIEW(current_hash, sizeof(current_hash) - 1u),
              INT32_C(1),
              LITERAL_VIEW("SessionStart"),
              command_handler,
              INT32_C(0),
              LITERAL_VIEW("PROJECT"),
              LITERAL_VIEW("/workspace/.codex/hooks.json"),
              INT64_C(42),
              CODEX_AGENT_HOOK_TRUST_STATUS_UNTRUSTED,
              INT32_C(1),
              EMPTY_VIEW,
              INT32_C(1),
              EMPTY_VIEW,
              INT32_C(1),
              EMPTY_VIEW,
              INT32_C(1),
              CODEX_AGENT_RESOURCE_ORIGIN_USER,
              INT32_C(1),
              &hook) == CODEX_AGENT_STATUS_OK);
    CHECK(hook != NULL);
    key[0] = (uint8_t)'X';
    current_hash[0] = (uint8_t)'X';
    CHECK_COPY(codex_agent_hook_key_copy, context, hook, "hook-key");
    CHECK_COPY(codex_agent_hook_current_hash_copy, context, hook, "hook-hash");
    CHECK_COPY(codex_agent_hook_event_name_copy, context, hook, "SessionStart");
    CHECK_COPY(codex_agent_hook_source_copy, context, hook, "PROJECT");
    CHECK_COPY(codex_agent_hook_source_path_copy, context, hook, "/workspace/.codex/hooks.json");
    CHECK(codex_agent_hook_is_enabled(context, hook, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == INT32_C(1));
    CHECK(codex_agent_hook_is_managed(context, hook, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == INT32_C(0));
    CHECK(codex_agent_hook_timeout_seconds(context, hook, &timeout_seconds) == CODEX_AGENT_STATUS_OK);
    CHECK(timeout_seconds == INT64_C(42));
    CHECK(codex_agent_hook_trust_status(context, hook, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == CODEX_AGENT_HOOK_TRUST_STATUS_UNTRUSTED);
    CHECK(codex_agent_hook_has_matcher(context, hook, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == INT32_C(1));
    CHECK_COPY(codex_agent_hook_matcher_copy, context, hook, "");
    CHECK(codex_agent_hook_has_plugin_id(context, hook, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == INT32_C(1));
    CHECK_COPY(codex_agent_hook_plugin_id_copy, context, hook, "");
    CHECK(codex_agent_hook_has_status_message(context, hook, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == INT32_C(1));
    CHECK_COPY(codex_agent_hook_status_message_copy, context, hook, "");
    CHECK(codex_agent_hook_origin(context, hook, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == CODEX_AGENT_RESOURCE_ORIGIN_USER);
    CHECK(codex_agent_hook_can_uninstall(context, hook, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == INT32_C(1));
    CHECK(codex_agent_hook_can_trust(context, hook, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == INT32_C(1));
    CHECK(codex_agent_hook_handler(context, hook, &projected_handler) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_handler_kind(context, projected_handler, &projected) == CODEX_AGENT_STATUS_OK);
    CHECK(projected == CODEX_AGENT_HOOK_HANDLER_KIND_COMMAND);
    CHECK(codex_agent_hook_handler_command(context, projected_handler, &projected_command) ==
          CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_hook_handler_command_command_copy, context, projected_command, "command");
    CHECK(codex_agent_hook_handler_command_destroy(context, &projected_command) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_handler_destroy(context, &projected_handler) == CODEX_AGENT_STATUS_OK);

    hooks[0] = hook;
    hooks[1] = hook;
    hooks[2] = hook;
    CHECK(codex_agent_hook_catalog_create(
              context, hooks, 3u, warnings, 3u, errors, 2u, &catalog) == CODEX_AGENT_STATUS_OK);
    warning[0] = (uint8_t)'X';
    stale_hook = hook;
    CHECK(codex_agent_hook_destroy(context, &hook) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_destroy(context, &hook) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_catalog_hooks_count(context, catalog, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 3u);
    CHECK(codex_agent_hook_catalog_warnings_count(context, catalog, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 3u);
    CHECK(codex_agent_hook_catalog_errors_count(context, catalog, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 2u);
    CHECK(codex_agent_hook_catalog_warnings_copy_at(
              context, catalog, 0u, NULL, 0u, &required) == CODEX_AGENT_STATUS_BUFFER_TOO_SMALL);
    CHECK(required == sizeof("warning") - 1u);
    CHECK(codex_agent_hook_catalog_warnings_copy_at(
              context, catalog, 3u, NULL, 0u, &required) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_hook_catalog_errors_copy_at(
              context, catalog, 0u, NULL, 0u, &required) == CODEX_AGENT_STATUS_BUFFER_TOO_SMALL);
    CHECK(required == sizeof("error") - 1u);
    CHECK(codex_agent_hook_catalog_hooks_at(context, catalog, 0u, &child_one) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_catalog_hooks_at(context, catalog, 2u, &child_two) == CODEX_AGENT_STATUS_OK);
    CHECK(child_one != child_two);
    CHECK(codex_agent_hook_catalog_hooks_at(context, catalog, 3u, &hook) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(hook == NULL);
    CHECK(codex_agent_hook_catalog_destroy(context, &catalog) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_catalog_destroy(context, &catalog) == CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_hook_key_copy, context, child_one, "hook-key");
    CHECK_COPY(codex_agent_hook_key_copy, context, child_two, "hook-key");
    CHECK(codex_agent_hook_key_copy(other_context, child_one, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(codex_agent_hook_destroy(context, &child_one) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_destroy(context, &child_two) == CODEX_AGENT_STATUS_OK);
    required = SIZE_MAX;
    CHECK(codex_agent_hook_key_copy(context, stale_hook, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(required == SIZE_MAX);

    CHECK(codex_agent_hook_handler_destroy(context, &command_handler) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_destroy(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(context == NULL);
    CHECK(other_context == NULL);
    return 0;
}
