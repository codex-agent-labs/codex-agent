#include "codex_agent.h"

#include <stdint.h>
#include <string.h>

#define CHECK(condition)     \
    do {                     \
        if (!(condition)) {  \
            return __LINE__; \
        }                    \
    } while (0)

#define VIEW(value) \
    (&(const codex_agent_string_view_t){(const uint8_t *)(value), sizeof(value) - 1u})

#define CHECK_COPY(function, context, handle, expected)                        \
    do {                                                                        \
        const char *copy_expected = (expected);                                \
        const size_t copy_size = strlen(copy_expected);                        \
        uint8_t copy_buffer[256] = {0};                                         \
        size_t copy_required = SIZE_MAX;                                        \
        CHECK(copy_size <= sizeof(copy_buffer));                               \
        CHECK((function)((context), (handle), NULL, 0u, &copy_required) ==      \
              CODEX_AGENT_STATUS_BUFFER_TOO_SMALL);                            \
        CHECK(copy_required == copy_size);                                      \
        CHECK((function)((context), (handle), copy_buffer, sizeof(copy_buffer), \
                         &copy_required) == CODEX_AGENT_STATUS_OK);             \
        CHECK(copy_required == copy_size);                                      \
        CHECK(memcmp(copy_buffer, copy_expected, copy_size) == 0);              \
    } while (0)

#define CHECK_COPY_AT(function, context, handle, index, expected)                      \
    do {                                                                                \
        const char *copy_expected = (expected);                                        \
        const size_t copy_size = strlen(copy_expected);                                \
        uint8_t copy_buffer[256] = {0};                                                 \
        size_t copy_required = SIZE_MAX;                                                \
        CHECK(copy_size <= sizeof(copy_buffer));                                       \
        CHECK((function)((context), (handle), (index), NULL, 0u, &copy_required) ==     \
              CODEX_AGENT_STATUS_BUFFER_TOO_SMALL);                                    \
        CHECK(copy_required == copy_size);                                              \
        CHECK((function)((context), (handle), (index), copy_buffer,                     \
                         sizeof(copy_buffer), &copy_required) == CODEX_AGENT_STATUS_OK); \
        CHECK(copy_required == copy_size);                                              \
        CHECK(memcmp(copy_buffer, copy_expected, copy_size) == 0);                      \
    } while (0)

static int create_full_configuration(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t **out_configuration) {
    const codex_agent_string_view_t header_keys[] = {
        {(const uint8_t *)"header-a", 8u},
        {(const uint8_t *)"header-b", 8u},
    };
    const codex_agent_string_view_t header_values[] = {
        {(const uint8_t *)"value-a", 7u},
        {(const uint8_t *)"value-b", 7u},
    };
    const codex_agent_string_view_t environment_header_keys[] = {
        {(const uint8_t *)"X-Token", 7u},
        {(const uint8_t *)"X-Trace", 7u},
    };
    const codex_agent_string_view_t environment_header_values[] = {
        {(const uint8_t *)"MCP_TOKEN", 9u},
        {(const uint8_t *)"TRACE_ID", 8u},
    };
    const int32_t omit_tools_from[] = {
        CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_DIRECT,
        CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_CODE_MODE,
    };
    const codex_agent_string_view_t enabled_tools[] = {
        {(const uint8_t *)"tool-a", 6u},
        {(const uint8_t *)"tool-a", 6u},
        {(const uint8_t *)"tool-b", 6u},
    };
    const codex_agent_string_view_t disabled_tools[] = {
        {(const uint8_t *)"tool-c", 6u},
    };
    const codex_agent_string_view_t scopes[] = {
        {(const uint8_t *)"scope-a", 7u},
        {(const uint8_t *)"scope-b", 7u},
    };
    const codex_agent_string_view_t tool_keys[] = {
        {(const uint8_t *)"tool-a", 6u},
        {(const uint8_t *)"tool-b", 6u},
    };
    codex_agent_mcp_transport_http_t *http = NULL;
    codex_agent_mcp_transport_t *transport = NULL;
    codex_agent_mcp_oauth_configuration_t *oauth = NULL;
    codex_agent_mcp_tool_configuration_t *tool_a = NULL;
    codex_agent_mcp_tool_configuration_t *tool_b = NULL;
    codex_agent_mcp_tool_configuration_t *tools[2];

    CHECK(codex_agent_mcp_transport_http_create(
              context,
              VIEW("https://mcp.example.invalid/api"),
              INT32_C(1),
              VIEW("MCP_TOKEN"),
              INT32_C(1),
              header_keys,
              header_values,
              2u,
              INT32_C(1),
              environment_header_keys,
              environment_header_values,
              2u,
              INT32_C(1),
              VIEW("headers-helper"),
              &http) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_transport_from_http(context, http, &transport) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_transport_http_destroy(context, &http) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_oauth_configuration_create(
              context,
              INT32_C(1),
              VIEW("client-id"),
              INT32_C(1),
              INT32_C(4321),
              &oauth) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_tool_configuration_create(
              context,
              INT32_C(1),
              CODEX_AGENT_MCP_TOOL_APPROVAL_APPROVE,
              &tool_a) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_tool_configuration_create(
              context,
              INT32_C(0),
              CODEX_AGENT_MCP_TOOL_APPROVAL_AUTO,
              &tool_b) == CODEX_AGENT_STATUS_OK);
    tools[0] = tool_a;
    tools[1] = tool_b;

    CHECK(codex_agent_mcp_server_configuration_create(
              context,
              VIEW("server_config"),
              transport,
              INT32_C(1),
              CODEX_AGENT_MCP_AUTHENTICATION_OAUTH,
              VIEW("local"),
              INT32_C(0),
              INT32_C(1),
              INT32_C(1),
              INT32_C(1),
              omit_tools_from,
              2u,
              INT32_C(1),
              3.5,
              INT32_C(1),
              7.25,
              INT32_C(1),
              CODEX_AGENT_MCP_TOOL_APPROVAL_WRITES,
              INT32_C(1),
              enabled_tools,
              3u,
              INT32_C(1),
              disabled_tools,
              1u,
              INT32_C(1),
              scopes,
              2u,
              INT32_C(1),
              oauth,
              INT32_C(1),
              VIEW("https://resource.example.invalid/"),
              tool_keys,
              tools,
              2u,
              out_configuration) == CODEX_AGENT_STATUS_OK);

    CHECK(codex_agent_mcp_transport_destroy(context, &transport) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_oauth_configuration_destroy(context, &oauth) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_tool_configuration_destroy(context, &tool_a) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_tool_configuration_destroy(context, &tool_b) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int create_full_server(
    codex_agent_context_t *context,
    codex_agent_mcp_server_t **out_server) {
    codex_agent_mcp_server_configuration_t *configuration = NULL;
    CHECK(create_full_configuration(context, &configuration) == 0);
    CHECK(codex_agent_mcp_server_create(
              context,
              VIEW("server_id"),
              VIEW("Server display"),
              CODEX_AGENT_MCP_AUTH_STATUS_OAUTH,
              configuration,
              CODEX_AGENT_RESOURCE_ORIGIN_WORKSPACE,
              INT32_C(1),
              out_server) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_server_configuration_destroy(context, &configuration) ==
          CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_http_transport(
    codex_agent_context_t *context,
    codex_agent_mcp_transport_t **transport_slot) {
    codex_agent_mcp_transport_http_t *http = NULL;
    size_t count = SIZE_MAX;
    int32_t kind = INT32_MIN;
    int32_t flag = INT32_MIN;

    CHECK(codex_agent_mcp_transport_kind(context, *transport_slot, &kind) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(kind == INT32_C(0));
    CHECK(codex_agent_mcp_transport_http(context, *transport_slot, &http) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_transport_destroy(context, transport_slot) == CODEX_AGENT_STATUS_OK);
    CHECK(*transport_slot == NULL);
    CHECK_COPY(codex_agent_mcp_transport_http_url_copy, context, http,
               "https://mcp.example.invalid/api");
    CHECK(codex_agent_mcp_transport_http_has_bearer_token_environment_variable(
              context, http, &flag) == CODEX_AGENT_STATUS_OK);
    CHECK(flag == INT32_C(1));
    CHECK_COPY(codex_agent_mcp_transport_http_bearer_token_environment_variable_copy,
               context, http, "MCP_TOKEN");
    CHECK(codex_agent_mcp_transport_http_has_headers(context, http, &flag) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(flag == INT32_C(1));
    CHECK(codex_agent_mcp_transport_http_headers_count(context, http, &count) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(count == 2u);
    CHECK_COPY_AT(codex_agent_mcp_transport_http_headers_key_copy_at,
                  context, http, 0u, "header-a");
    CHECK_COPY_AT(codex_agent_mcp_transport_http_headers_value_copy_at,
                  context, http, 0u, "value-a");
    CHECK_COPY_AT(codex_agent_mcp_transport_http_headers_key_copy_at,
                  context, http, 1u, "header-b");
    CHECK_COPY_AT(codex_agent_mcp_transport_http_headers_value_copy_at,
                  context, http, 1u, "value-b");
    CHECK(codex_agent_mcp_transport_http_has_environment_headers(context, http, &flag) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(flag == INT32_C(1));
    CHECK(codex_agent_mcp_transport_http_environment_headers_count(context, http, &count) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(count == 2u);
    CHECK_COPY_AT(codex_agent_mcp_transport_http_environment_headers_key_copy_at,
                  context, http, 0u, "X-Token");
    CHECK_COPY_AT(codex_agent_mcp_transport_http_environment_headers_value_copy_at,
                  context, http, 0u, "MCP_TOKEN");
    CHECK_COPY_AT(codex_agent_mcp_transport_http_environment_headers_key_copy_at,
                  context, http, 1u, "X-Trace");
    CHECK_COPY_AT(codex_agent_mcp_transport_http_environment_headers_value_copy_at,
                  context, http, 1u, "TRACE_ID");
    CHECK(codex_agent_mcp_transport_http_has_headers_helper(context, http, &flag) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(flag == INT32_C(1));
    CHECK_COPY(codex_agent_mcp_transport_http_headers_helper_copy,
               context, http, "headers-helper");
    CHECK(codex_agent_mcp_transport_http_destroy(context, &http) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_configuration(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t **configuration_slot) {
    codex_agent_mcp_transport_t *transport = NULL;
    codex_agent_mcp_oauth_configuration_t *oauth = NULL;
    codex_agent_mcp_tool_configuration_t *tool_a = NULL;
    codex_agent_mcp_tool_configuration_t *tool_b = NULL;
    size_t count = SIZE_MAX;
    int32_t has_value = INT32_MIN;
    int32_t value = INT32_MIN;
    int32_t callback_port = INT32_MIN;
    double number = -1.0;

    CHECK_COPY(codex_agent_mcp_server_configuration_name_copy,
               context, *configuration_slot, "server_config");
    CHECK(codex_agent_mcp_server_configuration_transport(
              context, *configuration_slot, &transport) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_server_configuration_authentication(
              context, *configuration_slot, &has_value, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(has_value == INT32_C(1));
    CHECK(value == CODEX_AGENT_MCP_AUTHENTICATION_OAUTH);
    CHECK_COPY(codex_agent_mcp_server_configuration_environment_id_copy,
               context, *configuration_slot, "local");
    CHECK(codex_agent_mcp_server_configuration_is_enabled(
              context, *configuration_slot, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(0));
    CHECK(codex_agent_mcp_server_configuration_is_required(
              context, *configuration_slot, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK(codex_agent_mcp_server_configuration_supports_parallel_tool_calls(
              context, *configuration_slot, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK(codex_agent_mcp_server_configuration_has_omit_tools_from(
              context, *configuration_slot, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK(codex_agent_mcp_server_configuration_omit_tools_from_count(
              context, *configuration_slot, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 2u);
    CHECK(codex_agent_mcp_server_configuration_omit_tools_from_at(
              context, *configuration_slot, 0u, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_DIRECT);
    CHECK(codex_agent_mcp_server_configuration_omit_tools_from_at(
              context, *configuration_slot, 1u, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_CODE_MODE);
    CHECK(codex_agent_mcp_server_configuration_startup_timeout_seconds(
              context, *configuration_slot, &has_value, &number) == CODEX_AGENT_STATUS_OK);
    CHECK(has_value == INT32_C(1));
    CHECK(number == 3.5);
    CHECK(codex_agent_mcp_server_configuration_tool_timeout_seconds(
              context, *configuration_slot, &has_value, &number) == CODEX_AGENT_STATUS_OK);
    CHECK(has_value == INT32_C(1));
    CHECK(number == 7.25);
    CHECK(codex_agent_mcp_server_configuration_default_tool_approval(
              context, *configuration_slot, &has_value, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(has_value == INT32_C(1));
    CHECK(value == CODEX_AGENT_MCP_TOOL_APPROVAL_WRITES);

    CHECK(codex_agent_mcp_server_configuration_has_enabled_tools(
              context, *configuration_slot, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK(codex_agent_mcp_server_configuration_enabled_tools_count(
              context, *configuration_slot, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 3u);
    CHECK_COPY_AT(codex_agent_mcp_server_configuration_enabled_tool_copy_at,
                  context, *configuration_slot, 0u, "tool-a");
    CHECK_COPY_AT(codex_agent_mcp_server_configuration_enabled_tool_copy_at,
                  context, *configuration_slot, 1u, "tool-a");
    CHECK_COPY_AT(codex_agent_mcp_server_configuration_enabled_tool_copy_at,
                  context, *configuration_slot, 2u, "tool-b");
    CHECK(codex_agent_mcp_server_configuration_has_disabled_tools(
              context, *configuration_slot, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK(codex_agent_mcp_server_configuration_disabled_tools_count(
              context, *configuration_slot, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 1u);
    CHECK_COPY_AT(codex_agent_mcp_server_configuration_disabled_tool_copy_at,
                  context, *configuration_slot, 0u, "tool-c");
    CHECK(codex_agent_mcp_server_configuration_has_scopes(
              context, *configuration_slot, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK(codex_agent_mcp_server_configuration_scopes_count(
              context, *configuration_slot, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 2u);
    CHECK_COPY_AT(codex_agent_mcp_server_configuration_scope_copy_at,
                  context, *configuration_slot, 0u, "scope-a");
    CHECK_COPY_AT(codex_agent_mcp_server_configuration_scope_copy_at,
                  context, *configuration_slot, 1u, "scope-b");

    CHECK(codex_agent_mcp_server_configuration_has_oauth(
              context, *configuration_slot, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK(codex_agent_mcp_server_configuration_oauth(
              context, *configuration_slot, &oauth) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_server_configuration_has_oauth_resource(
              context, *configuration_slot, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK_COPY(codex_agent_mcp_server_configuration_oauth_resource_copy,
               context, *configuration_slot, "https://resource.example.invalid/");
    CHECK(codex_agent_mcp_server_configuration_tools_count(
              context, *configuration_slot, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 2u);
    CHECK_COPY_AT(codex_agent_mcp_server_configuration_tools_key_copy_at,
                  context, *configuration_slot, 0u, "tool-a");
    CHECK_COPY_AT(codex_agent_mcp_server_configuration_tools_key_copy_at,
                  context, *configuration_slot, 1u, "tool-b");
    CHECK(codex_agent_mcp_server_configuration_tools_value_at(
              context, *configuration_slot, 0u, &tool_a) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_server_configuration_tools_value_at(
              context, *configuration_slot, 1u, &tool_b) == CODEX_AGENT_STATUS_OK);

    CHECK(codex_agent_mcp_server_configuration_destroy(context, configuration_slot) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(*configuration_slot == NULL);
    CHECK(verify_http_transport(context, &transport) == 0);
    CHECK(codex_agent_mcp_oauth_configuration_has_client_id(context, oauth, &has_value) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(has_value == INT32_C(1));
    CHECK_COPY(codex_agent_mcp_oauth_configuration_client_id_copy,
               context, oauth, "client-id");
    CHECK(codex_agent_mcp_oauth_configuration_callback_port(
              context, oauth, &has_value, &callback_port) == CODEX_AGENT_STATUS_OK);
    CHECK(has_value == INT32_C(1));
    CHECK(callback_port == INT32_C(4321));
    CHECK(codex_agent_mcp_oauth_configuration_destroy(context, &oauth) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_tool_configuration_approval(
              context, tool_a, &has_value, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(has_value == INT32_C(1));
    CHECK(value == CODEX_AGENT_MCP_TOOL_APPROVAL_APPROVE);
    CHECK(codex_agent_mcp_tool_configuration_destroy(context, &tool_a) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_tool_configuration_approval(
              context, tool_b, &has_value, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(has_value == INT32_C(0));
    CHECK(value == CODEX_AGENT_MCP_TOOL_APPROVAL_AUTO);
    CHECK(codex_agent_mcp_tool_configuration_destroy(context, &tool_b) ==
          CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_server_child(
    codex_agent_context_t *context,
    codex_agent_mcp_server_t **server_slot) {
    codex_agent_mcp_server_configuration_t *configuration = NULL;
    int32_t value = INT32_MIN;

    CHECK_COPY(codex_agent_mcp_server_name_copy, context, *server_slot, "server_id");
    CHECK_COPY(codex_agent_mcp_server_display_name_copy,
               context, *server_slot, "Server display");
    CHECK(codex_agent_mcp_server_auth_status(context, *server_slot, &value) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(value == CODEX_AGENT_MCP_AUTH_STATUS_OAUTH);
    CHECK(codex_agent_mcp_server_has_configuration(context, *server_slot, &value) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK(codex_agent_mcp_server_configuration(context, *server_slot, &configuration) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_server_origin(context, *server_slot, &value) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(value == CODEX_AGENT_RESOURCE_ORIGIN_WORKSPACE);
    CHECK(codex_agent_mcp_server_can_remove(context, *server_slot, &value) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK(codex_agent_mcp_server_is_authorized(context, *server_slot, &value) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK(codex_agent_mcp_server_destroy(context, server_slot) == CODEX_AGENT_STATUS_OK);
    CHECK(*server_slot == NULL);
    CHECK(verify_configuration(context, &configuration) == 0);
    return 0;
}

static int verify_absent_configuration(codex_agent_context_t *context) {
    codex_agent_mcp_server_t *source = NULL;
    codex_agent_mcp_server_t *child = NULL;
    codex_agent_mcp_server_configuration_t *configuration = NULL;
    codex_agent_integration_mcp_server_t *integration = NULL;
    int32_t has_configuration = INT32_MIN;

    CHECK(codex_agent_mcp_server_create(
              context,
              VIEW("absent"),
              VIEW("Absent configuration"),
              CODEX_AGENT_MCP_AUTH_STATUS_NOT_LOGGED_IN,
              NULL,
              CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN,
              INT32_C(0),
              &source) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_mcp_server_create(context, source, &integration) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_server_destroy(context, &source) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_mcp_server_server(context, integration, &child) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_mcp_server_destroy(context, &integration) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_server_has_configuration(context, child, &has_configuration) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(has_configuration == INT32_C(0));
    CHECK(codex_agent_mcp_server_configuration(context, child, &configuration) ==
          CODEX_AGENT_STATUS_NOT_READY);
    CHECK(configuration == NULL);
    CHECK(codex_agent_mcp_server_destroy(context, &child) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_integration_mcp_server(codex_agent_context_t *context) {
    codex_agent_mcp_server_t *source = NULL;
    codex_agent_mcp_server_t *first_child = NULL;
    codex_agent_mcp_server_t *second_child = NULL;
    codex_agent_integration_mcp_server_t *integration = NULL;

    CHECK(create_full_server(context, &source) == 0);
    CHECK(codex_agent_integration_mcp_server_create(context, source, &integration) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(integration != NULL);
    CHECK(codex_agent_mcp_server_destroy(context, &source) == CODEX_AGENT_STATUS_OK);
    CHECK(source == NULL);
    CHECK_COPY(codex_agent_integration_mcp_server_id_copy,
               context, integration, "server_id");
    CHECK_COPY(codex_agent_integration_mcp_server_display_name_copy,
               context, integration, "Server display");
    CHECK(codex_agent_integration_mcp_server_server(
              context, integration, &first_child) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_mcp_server_server(
              context, integration, &second_child) == CODEX_AGENT_STATUS_OK);
    CHECK(first_child != NULL);
    CHECK(second_child != NULL);
    CHECK(first_child != second_child);
    CHECK(codex_agent_integration_mcp_server_destroy(context, &integration) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(integration == NULL);
    CHECK(verify_server_child(context, &first_child) == 0);
    CHECK(verify_server_child(context, &second_child) == 0);
    CHECK(verify_absent_configuration(context) == 0);
    CHECK(codex_agent_integration_mcp_server_destroy(context, &integration) ==
          CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_invalid_boundaries(
    codex_agent_context_t *context,
    codex_agent_context_t *other_context) {
    codex_agent_mcp_server_t *server = NULL;
    codex_agent_mcp_server_t *child = NULL;
    codex_agent_mcp_server_t *occupied_child = NULL;
    codex_agent_mcp_server_t *stale_server;
    codex_agent_integration_mcp_server_t *integration = NULL;
    codex_agent_integration_mcp_server_t *invalid = NULL;
    codex_agent_integration_mcp_server_t *stale_integration;
    size_t required = SIZE_MAX;

    CHECK(create_full_server(context, &server) == 0);
    CHECK(codex_agent_integration_mcp_server_create(context, server, &integration) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(integration != NULL);
    CHECK(codex_agent_integration_mcp_server_create(context, server, &integration) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(integration != NULL);
    CHECK(codex_agent_integration_mcp_server_create(context, server, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_integration_mcp_server_create(NULL, server, &invalid) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid == NULL);
    CHECK(codex_agent_integration_mcp_server_create(context, NULL, &invalid) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid == NULL);
    CHECK(codex_agent_integration_mcp_server_create(other_context, server, &invalid) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(invalid == NULL);
    CHECK(codex_agent_integration_mcp_server_create(
              context, (codex_agent_mcp_server_t *)integration, &invalid) ==
          CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(invalid == NULL);

    CHECK(codex_agent_integration_mcp_server_server(context, integration, &child) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(child != NULL);
    occupied_child = child;
    CHECK(codex_agent_integration_mcp_server_server(
              context, integration, &occupied_child) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(occupied_child == child);
    CHECK(codex_agent_integration_mcp_server_server(context, integration, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    occupied_child = NULL;
    CHECK(codex_agent_integration_mcp_server_server(NULL, integration, &occupied_child) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(occupied_child == NULL);
    CHECK(codex_agent_integration_mcp_server_server(
              other_context, integration, &occupied_child) == CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(occupied_child == NULL);
    CHECK(codex_agent_integration_mcp_server_server(
              context,
              (codex_agent_integration_mcp_server_t *)server,
              &occupied_child) == CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(occupied_child == NULL);

    CHECK(codex_agent_integration_mcp_server_id_copy(
              context, integration, NULL, 0u, NULL) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_integration_mcp_server_display_name_copy(
              context, integration, NULL, 0u, NULL) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_integration_mcp_server_id_copy(
              other_context, integration, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(required == SIZE_MAX);
    CHECK(codex_agent_integration_mcp_server_id_copy(
              context,
              (codex_agent_integration_mcp_server_t *)server,
              NULL,
              0u,
              &required) == CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(required == SIZE_MAX);
    CHECK(codex_agent_integration_mcp_server_display_name_copy(
              other_context, integration, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(required == SIZE_MAX);
    CHECK(codex_agent_integration_mcp_server_display_name_copy(
              context,
              (codex_agent_integration_mcp_server_t *)server,
              NULL,
              0u,
              &required) == CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(required == SIZE_MAX);

    {
        codex_agent_integration_mcp_server_t *wrong =
            (codex_agent_integration_mcp_server_t *)child;
        CHECK(codex_agent_integration_mcp_server_destroy(context, NULL) ==
              CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK(codex_agent_integration_mcp_server_destroy(context, &wrong) ==
              CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
        CHECK(wrong == (codex_agent_integration_mcp_server_t *)child);
    }
    CHECK(codex_agent_integration_mcp_server_destroy(other_context, &integration) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(integration != NULL);

    stale_server = server;
    CHECK(codex_agent_mcp_server_destroy(context, &server) == CODEX_AGENT_STATUS_OK);
    CHECK(server == NULL);
    CHECK(codex_agent_integration_mcp_server_create(context, stale_server, &invalid) ==
          CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(invalid == NULL);
    stale_integration = integration;
    CHECK(codex_agent_integration_mcp_server_destroy(context, &integration) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(integration == NULL);
    CHECK(codex_agent_integration_mcp_server_server(
              context, stale_integration, &occupied_child) == CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(occupied_child == NULL);
    CHECK(codex_agent_integration_mcp_server_id_copy(
              context, stale_integration, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(required == SIZE_MAX);
    CHECK(codex_agent_integration_mcp_server_display_name_copy(
              context, stale_integration, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(required == SIZE_MAX);
    CHECK(codex_agent_integration_mcp_server_destroy(context, &integration) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_server_destroy(context, &child) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_server_destroy(context, &child) == CODEX_AGENT_STATUS_OK);
    return 0;
}

int main(void) {
    codex_agent_context_t *context = NULL;
    codex_agent_context_t *other_context = NULL;

    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_create(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(context != NULL);
    CHECK(other_context != NULL);
    CHECK(verify_integration_mcp_server(context) == 0);
    CHECK(verify_invalid_boundaries(context, other_context) == 0);
    CHECK(codex_agent_context_destroy(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(other_context == NULL);
    CHECK(context == NULL);
    return 0;
}
