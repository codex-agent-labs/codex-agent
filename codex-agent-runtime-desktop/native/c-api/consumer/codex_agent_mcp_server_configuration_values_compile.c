#include "codex_agent.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHECK(condition)                                                                            \
    do {                                                                                            \
        if (!(condition)) {                                                                         \
            fprintf(stderr, "check failed at line %d\n", __LINE__);                                \
            return 1;                                                                               \
        }                                                                                           \
    } while (0)

#define LITERAL_VIEW(value)                                                                         \
    { (const uint8_t *)(value), sizeof(value) - 1u }

#define CHECK_COPY(function, context, handle, expected)                                              \
    do {                                                                                            \
        size_t required_ = SIZE_MAX;                                                                \
        uint8_t buffer_[128];                                                                       \
        CHECK(function((context), (handle), NULL, 0u, &required_) ==                                \
              CODEX_AGENT_STATUS_BUFFER_TOO_SMALL);                                                 \
        CHECK(required_ == sizeof(expected) - 1u);                                                   \
        CHECK(function((context), (handle), buffer_, sizeof(buffer_), &required_) ==                 \
              CODEX_AGENT_STATUS_OK);                                                               \
        CHECK(memcmp(buffer_, (expected), sizeof(expected) - 1u) == 0);                             \
    } while (0)

#define CHECK_COPY_AT(function, context, handle, index, expected)                                    \
    do {                                                                                            \
        size_t required_ = SIZE_MAX;                                                                \
        uint8_t buffer_[128];                                                                       \
        CHECK(function((context), (handle), (index), NULL, 0u, &required_) ==                       \
              CODEX_AGENT_STATUS_BUFFER_TOO_SMALL);                                                 \
        CHECK(required_ == sizeof(expected) - 1u);                                                   \
        CHECK(function((context), (handle), (index), buffer_, sizeof(buffer_), &required_) ==        \
              CODEX_AGENT_STATUS_OK);                                                               \
        CHECK(memcmp(buffer_, (expected), sizeof(expected) - 1u) == 0);                             \
    } while (0)

static codex_agent_status_t create_configuration_with_default_approval(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_t *transport,
    codex_agent_mcp_tool_approval_t approval,
    codex_agent_mcp_server_configuration_t **out_configuration) {
    codex_agent_string_view_t name = LITERAL_VIEW("approval_server");
    codex_agent_string_view_t environment_id = LITERAL_VIEW("local");
    codex_agent_string_view_t absent = {NULL, 0u};
    return codex_agent_mcp_server_configuration_create(
        context,
        &name,
        transport,
        0,
        0,
        &environment_id,
        1,
        0,
        0,
        0,
        NULL,
        0u,
        0,
        0.0,
        0,
        0.0,
        1,
        approval,
        0,
        NULL,
        0u,
        0,
        NULL,
        0u,
        0,
        NULL,
        0u,
        0,
        NULL,
        0,
        &absent,
        NULL,
        NULL,
        0u,
        out_configuration);
}

int main(void) {
    codex_agent_context_t *context = NULL;
    codex_agent_context_t *other_context = NULL;
    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_create(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(context != NULL && other_context != NULL);

    codex_agent_string_view_t absent = {NULL, 0u};
    codex_agent_string_view_t http_url = LITERAL_VIEW("https://mcp.example.com/config");
    codex_agent_mcp_transport_http_t *http = NULL;
    CHECK(codex_agent_mcp_transport_http_create(
              context,
              &http_url,
              0,
              &absent,
              0,
              NULL,
              NULL,
              0u,
              0,
              NULL,
              NULL,
              0u,
              0,
              &absent,
              &http) == CODEX_AGENT_STATUS_OK);
    CHECK(http != NULL);

    codex_agent_mcp_transport_t *transport = NULL;
    CHECK(codex_agent_mcp_transport_from_http(context, http, &transport) == CODEX_AGENT_STATUS_OK);
    CHECK(transport != NULL);
    int32_t kind = -1;
    CHECK(codex_agent_mcp_transport_kind(context, transport, &kind) == CODEX_AGENT_STATUS_OK);
    CHECK(kind == 0);
    codex_agent_mcp_transport_http_t *http_child = NULL;
    CHECK(codex_agent_mcp_transport_http(context, transport, &http_child) == CODEX_AGENT_STATUS_OK);
    CHECK(http_child != NULL);
    CHECK_COPY(codex_agent_mcp_transport_http_url_copy, context, http_child, "https://mcp.example.com/config");
    codex_agent_mcp_transport_stdio_t *wrong_stdio_child = NULL;
    CHECK(codex_agent_mcp_transport_stdio(context, transport, &wrong_stdio_child) ==
          CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(wrong_stdio_child == NULL);
    kind = 73;
    CHECK(codex_agent_mcp_transport_kind(other_context, transport, &kind) == CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(kind == 73);

    codex_agent_string_view_t command = LITERAL_VIEW("mcp-command");
    codex_agent_mcp_transport_stdio_t *stdio = NULL;
    CHECK(codex_agent_mcp_transport_stdio_create(
              context,
              &command,
              NULL,
              0u,
              0,
              &absent,
              0,
              NULL,
              NULL,
              0u,
              NULL,
              0u,
              &stdio) == CODEX_AGENT_STATUS_OK);
    codex_agent_mcp_transport_t *stdio_transport = NULL;
    CHECK(codex_agent_mcp_transport_from_stdio(context, stdio, &stdio_transport) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_transport_kind(context, stdio_transport, &kind) == CODEX_AGENT_STATUS_OK);
    CHECK(kind == 1);
    codex_agent_mcp_transport_stdio_t *stdio_child = NULL;
    CHECK(codex_agent_mcp_transport_stdio(context, stdio_transport, &stdio_child) == CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_mcp_transport_stdio_command_copy, context, stdio_child, "mcp-command");

    codex_agent_string_view_t client_id = LITERAL_VIEW("client-c");
    codex_agent_mcp_oauth_configuration_t *oauth = NULL;
    CHECK(codex_agent_mcp_oauth_configuration_create(context, 1, &client_id, 1, 49152, &oauth) ==
          CODEX_AGENT_STATUS_OK);
    codex_agent_mcp_tool_configuration_t *tool_auto = NULL;
    codex_agent_mcp_tool_configuration_t *tool_prompt = NULL;
    CHECK(codex_agent_mcp_tool_configuration_create(
              context, 1, CODEX_AGENT_MCP_TOOL_APPROVAL_AUTO, &tool_auto) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_tool_configuration_create(
              context, 1, CODEX_AGENT_MCP_TOOL_APPROVAL_PROMPT, &tool_prompt) == CODEX_AGENT_STATUS_OK);

    codex_agent_string_view_t name = LITERAL_VIEW("server_c");
    codex_agent_string_view_t environment_id = LITERAL_VIEW("local");
    codex_agent_mcp_tool_exposure_surface_t omit_tools_from[] = {
        CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_CODE_MODE,
        CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_DEFERRED,
        CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_DIRECT,
    };
    codex_agent_string_view_t enabled_tools[] = {
        LITERAL_VIEW("tool-a"),
        LITERAL_VIEW("tool-b"),
        LITERAL_VIEW("tool-a"),
    };
    codex_agent_string_view_t scopes[] = {LITERAL_VIEW("scope-a"), LITERAL_VIEW("scope-b")};
    codex_agent_string_view_t oauth_resource = LITERAL_VIEW("resource://c");
    codex_agent_string_view_t tool_keys[] = {LITERAL_VIEW("auto"), LITERAL_VIEW("prompt")};
    codex_agent_mcp_tool_configuration_t *tool_values[] = {tool_auto, tool_prompt};
    codex_agent_mcp_server_configuration_t *configuration = NULL;
    CHECK(codex_agent_mcp_server_configuration_create(
              context,
              &name,
              transport,
              1,
              CODEX_AGENT_MCP_AUTHENTICATION_OAUTH,
              &environment_id,
              0,
              1,
              1,
              1,
              omit_tools_from,
              3u,
              1,
              0.5,
              1,
              7.5,
              1,
              CODEX_AGENT_MCP_TOOL_APPROVAL_APPROVE,
              1,
              enabled_tools,
              3u,
              1,
              NULL,
              0u,
              1,
              scopes,
              2u,
              1,
              oauth,
              1,
              &oauth_resource,
              tool_keys,
              tool_values,
              2u,
              &configuration) == CODEX_AGENT_STATUS_OK);
    CHECK(configuration != NULL);

    const codex_agent_mcp_tool_approval_t approval_values[] = {
        CODEX_AGENT_MCP_TOOL_APPROVAL_AUTO,
        CODEX_AGENT_MCP_TOOL_APPROVAL_PROMPT,
        CODEX_AGENT_MCP_TOOL_APPROVAL_WRITES,
        CODEX_AGENT_MCP_TOOL_APPROVAL_APPROVE,
    };
    for (size_t index = 0u; index < 4u; ++index) {
        codex_agent_mcp_server_configuration_t *approval_configuration = NULL;
        CHECK(create_configuration_with_default_approval(
                  context,
                  transport,
                  approval_values[index],
                  &approval_configuration) == CODEX_AGENT_STATUS_OK);
        CHECK(approval_configuration != NULL);
        int32_t approval_present = -1;
        codex_agent_mcp_tool_approval_t projected_approval = -1;
        CHECK(codex_agent_mcp_server_configuration_default_tool_approval(
                  context,
                  approval_configuration,
                  &approval_present,
                  &projected_approval) == CODEX_AGENT_STATUS_OK);
        CHECK(approval_present == 1 && projected_approval == approval_values[index]);
        CHECK(codex_agent_mcp_server_configuration_destroy(context, &approval_configuration) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(approval_configuration == NULL);
        CHECK(codex_agent_mcp_server_configuration_destroy(context, &approval_configuration) ==
              CODEX_AGENT_STATUS_OK);
    }

    codex_agent_mcp_server_configuration_t *invalid = NULL;
    CHECK(codex_agent_mcp_server_configuration_create(
              context, &name, transport, 2, 0, &environment_id, 1, 0, 0, 0, NULL, 0u,
              0, 0.0, 0, 0.0, 0, 0, 0, NULL, 0u, 0, NULL, 0u, 0, NULL, 0u,
              0, NULL, 0, &absent, NULL, NULL, 0u, &invalid) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid == NULL);
    CHECK(codex_agent_mcp_server_configuration_create(
              context, &name, stdio_transport, 1, CODEX_AGENT_MCP_AUTHENTICATION_OAUTH,
              &environment_id, 1, 0, 0, 0, NULL, 0u, 0, 0.0, 0, 0.0, 0, 0,
              0, NULL, 0u, 0, NULL, 0u, 0, NULL, 0u, 0, NULL, 0, &absent,
              NULL, NULL, 0u, &invalid) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    codex_agent_string_view_t duplicate_keys[] = {LITERAL_VIEW("same"), LITERAL_VIEW("same")};
    CHECK(codex_agent_mcp_server_configuration_create(
              context, &name, transport, 0, 0, &environment_id, 1, 0, 0, 0, NULL, 0u,
              0, 0.0, 0, 0.0, 0, 0, 0, NULL, 0u, 0, NULL, 0u, 0, NULL, 0u,
              0, NULL, 0, &absent, duplicate_keys, tool_values, 2u, &invalid) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid == NULL);

    CHECK(codex_agent_mcp_transport_destroy(context, &transport) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_transport_destroy(context, &transport) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_transport_http_destroy(context, &http) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_oauth_configuration_destroy(context, &oauth) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_tool_configuration_destroy(context, &tool_auto) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_tool_configuration_destroy(context, &tool_prompt) == CODEX_AGENT_STATUS_OK);

    CHECK_COPY(codex_agent_mcp_server_configuration_name_copy, context, configuration, "server_c");
    int32_t present = -1;
    int32_t enum_value = -1;
    CHECK(codex_agent_mcp_server_configuration_authentication(
              context, configuration, &present, &enum_value) == CODEX_AGENT_STATUS_OK);
    CHECK(present == 1 && enum_value == CODEX_AGENT_MCP_AUTHENTICATION_OAUTH);
    CHECK_COPY(codex_agent_mcp_server_configuration_environment_id_copy, context, configuration, "local");
    int32_t int_value = -1;
    CHECK(codex_agent_mcp_server_configuration_is_enabled(context, configuration, &int_value) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(int_value == 0);
    CHECK(codex_agent_mcp_server_configuration_is_required(context, configuration, &int_value) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(int_value == 1);
    CHECK(codex_agent_mcp_server_configuration_supports_parallel_tool_calls(
              context, configuration, &int_value) == CODEX_AGENT_STATUS_OK);
    CHECK(int_value == 1);

    CHECK(codex_agent_mcp_server_configuration_has_omit_tools_from(
              context, configuration, &present) == CODEX_AGENT_STATUS_OK);
    CHECK(present == 1);
    size_t count = SIZE_MAX;
    CHECK(codex_agent_mcp_server_configuration_omit_tools_from_count(
              context, configuration, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 3u);
    for (size_t index = 0u; index < 3u; ++index) {
        enum_value = -1;
        CHECK(codex_agent_mcp_server_configuration_omit_tools_from_at(
                  context, configuration, index, &enum_value) == CODEX_AGENT_STATUS_OK);
        CHECK(enum_value == (int32_t)index);
    }

    double double_value = -1.0;
    CHECK(codex_agent_mcp_server_configuration_startup_timeout_seconds(
              context, configuration, &present, &double_value) == CODEX_AGENT_STATUS_OK);
    CHECK(present == 1 && double_value == 0.5);
    CHECK(codex_agent_mcp_server_configuration_tool_timeout_seconds(
              context, configuration, &present, &double_value) == CODEX_AGENT_STATUS_OK);
    CHECK(present == 1 && double_value == 7.5);
    CHECK(codex_agent_mcp_server_configuration_default_tool_approval(
              context, configuration, &present, &enum_value) == CODEX_AGENT_STATUS_OK);
    CHECK(present == 1 && enum_value == CODEX_AGENT_MCP_TOOL_APPROVAL_APPROVE);

    CHECK(codex_agent_mcp_server_configuration_has_enabled_tools(
              context, configuration, &present) == CODEX_AGENT_STATUS_OK);
    CHECK(present == 1);
    CHECK(codex_agent_mcp_server_configuration_enabled_tools_count(
              context, configuration, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 3u);
    CHECK_COPY_AT(codex_agent_mcp_server_configuration_enabled_tool_copy_at,
                  context, configuration, 0u, "tool-a");
    CHECK_COPY_AT(codex_agent_mcp_server_configuration_enabled_tool_copy_at,
                  context, configuration, 1u, "tool-b");
    CHECK_COPY_AT(codex_agent_mcp_server_configuration_enabled_tool_copy_at,
                  context, configuration, 2u, "tool-a");
    CHECK(codex_agent_mcp_server_configuration_has_disabled_tools(
              context, configuration, &present) == CODEX_AGENT_STATUS_OK);
    CHECK(present == 1);
    CHECK(codex_agent_mcp_server_configuration_disabled_tools_count(
              context, configuration, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 0u);
    size_t required = 81u;
    CHECK(codex_agent_mcp_server_configuration_disabled_tool_copy_at(
              context, configuration, 0u, NULL, 0u, &required) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(required == 81u);
    CHECK(codex_agent_mcp_server_configuration_has_scopes(
              context, configuration, &present) == CODEX_AGENT_STATUS_OK);
    CHECK(present == 1);
    CHECK(codex_agent_mcp_server_configuration_scopes_count(
              context, configuration, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 2u);
    CHECK_COPY_AT(codex_agent_mcp_server_configuration_scope_copy_at,
                  context, configuration, 0u, "scope-a");
    CHECK_COPY_AT(codex_agent_mcp_server_configuration_scope_copy_at,
                  context, configuration, 1u, "scope-b");

    CHECK(codex_agent_mcp_server_configuration_has_oauth(context, configuration, &present) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(present == 1);
    codex_agent_mcp_oauth_configuration_t *oauth_child = NULL;
    CHECK(codex_agent_mcp_server_configuration_oauth(context, configuration, &oauth_child) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(oauth_child != NULL);
    CHECK_COPY(codex_agent_mcp_oauth_configuration_client_id_copy, context, oauth_child, "client-c");
    CHECK(codex_agent_mcp_server_configuration_has_oauth_resource(
              context, configuration, &present) == CODEX_AGENT_STATUS_OK);
    CHECK(present == 1);
    CHECK_COPY(codex_agent_mcp_server_configuration_oauth_resource_copy,
               context, configuration, "resource://c");

    CHECK(codex_agent_mcp_server_configuration_tools_count(context, configuration, &count) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(count == 2u);
    CHECK_COPY_AT(codex_agent_mcp_server_configuration_tools_key_copy_at,
                  context, configuration, 0u, "auto");
    CHECK_COPY_AT(codex_agent_mcp_server_configuration_tools_key_copy_at,
                  context, configuration, 1u, "prompt");
    codex_agent_mcp_tool_configuration_t *tool_child = NULL;
    CHECK(codex_agent_mcp_server_configuration_tools_value_at(
              context, configuration, 1u, &tool_child) == CODEX_AGENT_STATUS_OK);
    CHECK(tool_child != NULL);
    CHECK(codex_agent_mcp_tool_configuration_approval(
              context, tool_child, &present, &enum_value) == CODEX_AGENT_STATUS_OK);
    CHECK(present == 1 && enum_value == CODEX_AGENT_MCP_TOOL_APPROVAL_PROMPT);

    codex_agent_mcp_transport_t *owned_transport = NULL;
    CHECK(codex_agent_mcp_server_configuration_transport(
              context, configuration, &owned_transport) == CODEX_AGENT_STATUS_OK);
    CHECK(owned_transport != NULL);
    CHECK(codex_agent_mcp_transport_kind(context, owned_transport, &kind) == CODEX_AGENT_STATUS_OK);
    CHECK(kind == 0);
    codex_agent_mcp_transport_http_t *owned_http = NULL;
    CHECK(codex_agent_mcp_transport_http(context, owned_transport, &owned_http) == CODEX_AGENT_STATUS_OK);

    codex_agent_mcp_transport_t *occupied_transport = owned_transport;
    CHECK(codex_agent_mcp_server_configuration_transport(
              context, configuration, &occupied_transport) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(occupied_transport == owned_transport);
    count = 93u;
    CHECK(codex_agent_mcp_server_configuration_tools_count(other_context, configuration, &count) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(count == 93u);
    required = 94u;
    CHECK(codex_agent_mcp_server_configuration_tools_key_copy_at(
              context, configuration, SIZE_MAX, NULL, 0u, &required) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(required == 94u);

    codex_agent_mcp_server_configuration_t *stale_configuration = configuration;
    CHECK(codex_agent_mcp_server_configuration_destroy(context, &configuration) == CODEX_AGENT_STATUS_OK);
    CHECK(configuration == NULL);
    CHECK(codex_agent_mcp_server_configuration_destroy(context, &configuration) == CODEX_AGENT_STATUS_OK);
    int_value = 95;
    CHECK(codex_agent_mcp_server_configuration_is_enabled(
              context, stale_configuration, &int_value) == CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(int_value == 95);
    CHECK_COPY(codex_agent_mcp_transport_http_url_copy,
               context, owned_http, "https://mcp.example.com/config");
    CHECK_COPY(codex_agent_mcp_oauth_configuration_client_id_copy,
               context, oauth_child, "client-c");

    CHECK(codex_agent_mcp_transport_http_destroy(context, &owned_http) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_transport_destroy(context, &owned_transport) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_transport_destroy(context, &owned_transport) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_oauth_configuration_destroy(context, &oauth_child) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_tool_configuration_destroy(context, &tool_child) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_transport_stdio_destroy(context, &stdio_child) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_transport_destroy(context, &stdio_transport) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_transport_destroy(context, &stdio_transport) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_transport_stdio_destroy(context, &stdio) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_transport_http_destroy(context, &http_child) == CODEX_AGENT_STATUS_OK);

    {
        codex_agent_context_t *lifecycle_context = NULL;
        CHECK(codex_agent_context_create(&lifecycle_context) == CODEX_AGENT_STATUS_OK);
        codex_agent_string_view_t lifecycle_command = LITERAL_VIEW("lifecycle-command");
        codex_agent_string_view_t lifecycle_absent = {NULL, 0u};
        codex_agent_mcp_transport_stdio_t *lifecycle_stdio = NULL;
        CHECK(codex_agent_mcp_transport_stdio_create(
                  lifecycle_context,
                  &lifecycle_command,
                  NULL,
                  0u,
                  0,
                  &lifecycle_absent,
                  0,
                  NULL,
                  NULL,
                  0u,
                  NULL,
                  0u,
                  &lifecycle_stdio) == CODEX_AGENT_STATUS_OK);
        codex_agent_mcp_transport_t *lifecycle_carrier = NULL;
        CHECK(codex_agent_mcp_transport_from_stdio(
                  lifecycle_context, lifecycle_stdio, &lifecycle_carrier) == CODEX_AGENT_STATUS_OK);
        codex_agent_mcp_server_configuration_t *lifecycle_configuration = NULL;
        CHECK(create_configuration_with_default_approval(
                  lifecycle_context,
                  lifecycle_carrier,
                  CODEX_AGENT_MCP_TOOL_APPROVAL_AUTO,
                  &lifecycle_configuration) == CODEX_AGENT_STATUS_OK);
        codex_agent_mcp_transport_t *lifecycle_child = NULL;
        CHECK(codex_agent_mcp_server_configuration_transport(
                  lifecycle_context, lifecycle_configuration, &lifecycle_child) == CODEX_AGENT_STATUS_OK);

        codex_agent_context_t *stale_context = lifecycle_context;
        codex_agent_mcp_server_configuration_t *reclaimed_configuration = lifecycle_configuration;
        codex_agent_mcp_transport_t *reclaimed_carrier = lifecycle_carrier;
        codex_agent_mcp_transport_t *reclaimed_child = lifecycle_child;
        CHECK(codex_agent_context_destroy(&lifecycle_context) == CODEX_AGENT_STATUS_OK);
        CHECK(lifecycle_context == NULL);

        int32_t stale_value = 71;
        CHECK(codex_agent_mcp_server_configuration_is_enabled(
                  stale_context, reclaimed_configuration, &stale_value) == CODEX_AGENT_STATUS_STALE_HANDLE);
        CHECK(stale_value == 71);
        stale_value = 72;
        CHECK(codex_agent_mcp_transport_kind(stale_context, reclaimed_carrier, &stale_value) ==
              CODEX_AGENT_STATUS_STALE_HANDLE);
        CHECK(stale_value == 72);
        stale_value = 73;
        CHECK(codex_agent_mcp_transport_kind(stale_context, reclaimed_child, &stale_value) ==
              CODEX_AGENT_STATUS_STALE_HANDLE);
        CHECK(stale_value == 73);
        codex_agent_mcp_transport_t *empty_output = NULL;
        CHECK(codex_agent_mcp_server_configuration_transport(
                  stale_context, reclaimed_configuration, &empty_output) == CODEX_AGENT_STATUS_STALE_HANDLE);
        CHECK(empty_output == NULL);
    }

    CHECK(codex_agent_context_destroy(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(other_context == NULL && context == NULL);
    return 0;
}
