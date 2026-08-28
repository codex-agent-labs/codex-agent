#include "codex_agent.h"

#include <limits.h>
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

int main(void) {
    codex_agent_context_t *context = NULL;
    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(context != NULL);

    uint8_t http_url_bytes[] = "https://mcp.example.com/path";
    uint8_t bearer_bytes[] = "MCP_TOKEN";
    uint8_t helper_bytes[] = "mcp-headers";
    uint8_t header_key_bytes[] = "X-First";
    uint8_t header_value_bytes[] = "one";
    codex_agent_string_view_t http_url = {http_url_bytes, sizeof(http_url_bytes) - 1u};
    codex_agent_string_view_t bearer = {bearer_bytes, sizeof(bearer_bytes) - 1u};
    codex_agent_string_view_t helper = {helper_bytes, sizeof(helper_bytes) - 1u};
    codex_agent_string_view_t header_keys[] = {
        {header_key_bytes, sizeof(header_key_bytes) - 1u},
        LITERAL_VIEW("X-Second"),
    };
    codex_agent_string_view_t header_values[] = {
        {header_value_bytes, sizeof(header_value_bytes) - 1u},
        LITERAL_VIEW("two"),
    };
    codex_agent_string_view_t environment_header_keys[] = {
        LITERAL_VIEW("Authorization"),
        LITERAL_VIEW("X-Remote"),
    };
    codex_agent_string_view_t environment_header_values[] = {
        LITERAL_VIEW("MCP_AUTH"),
        LITERAL_VIEW("MCP_REMOTE"),
    };
    codex_agent_mcp_transport_http_t *http = NULL;
    CHECK(codex_agent_mcp_transport_http_create(
              context,
              &http_url,
              1,
              &bearer,
              1,
              header_keys,
              header_values,
              2u,
              1,
              environment_header_keys,
              environment_header_values,
              2u,
              1,
              &helper,
              &http) == CODEX_AGENT_STATUS_OK);
    CHECK(http != NULL);
    http_url_bytes[0] = 'X';
    bearer_bytes[0] = 'X';
    helper_bytes[0] = 'X';
    header_key_bytes[0] = 'X';
    header_value_bytes[0] = 'X';
    header_keys[1] = helper;
    header_values[1] = helper;
    environment_header_keys[0] = helper;
    environment_header_values[0] = helper;

    CHECK_COPY(codex_agent_mcp_transport_http_url_copy, context, http, "https://mcp.example.com/path");
    int32_t present = INT32_MIN;
    CHECK(codex_agent_mcp_transport_http_has_bearer_token_environment_variable(
              context, http, &present) == CODEX_AGENT_STATUS_OK);
    CHECK(present == 1);
    CHECK_COPY(
        codex_agent_mcp_transport_http_bearer_token_environment_variable_copy,
        context,
        http,
        "MCP_TOKEN");
    CHECK(codex_agent_mcp_transport_http_has_headers(context, http, &present) == CODEX_AGENT_STATUS_OK);
    CHECK(present == 1);
    size_t count = SIZE_MAX;
    CHECK(codex_agent_mcp_transport_http_headers_count(context, http, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 2u);
    CHECK_COPY_AT(codex_agent_mcp_transport_http_headers_key_copy_at, context, http, 0u, "X-First");
    CHECK_COPY_AT(codex_agent_mcp_transport_http_headers_value_copy_at, context, http, 0u, "one");
    CHECK_COPY_AT(codex_agent_mcp_transport_http_headers_key_copy_at, context, http, 1u, "X-Second");
    CHECK_COPY_AT(codex_agent_mcp_transport_http_headers_value_copy_at, context, http, 1u, "two");
    CHECK(codex_agent_mcp_transport_http_has_environment_headers(context, http, &present) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(present == 1);
    CHECK(codex_agent_mcp_transport_http_environment_headers_count(context, http, &count) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(count == 2u);
    CHECK_COPY_AT(
        codex_agent_mcp_transport_http_environment_headers_key_copy_at,
        context,
        http,
        0u,
        "Authorization");
    CHECK_COPY_AT(
        codex_agent_mcp_transport_http_environment_headers_value_copy_at,
        context,
        http,
        0u,
        "MCP_AUTH");
    CHECK_COPY_AT(
        codex_agent_mcp_transport_http_environment_headers_key_copy_at,
        context,
        http,
        1u,
        "X-Remote");
    CHECK_COPY_AT(
        codex_agent_mcp_transport_http_environment_headers_value_copy_at,
        context,
        http,
        1u,
        "MCP_REMOTE");
    CHECK(codex_agent_mcp_transport_http_has_headers_helper(context, http, &present) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(present == 1);
    CHECK_COPY(codex_agent_mcp_transport_http_headers_helper_copy, context, http, "mcp-headers");

    codex_agent_string_view_t empty = {NULL, 0u};
    codex_agent_string_view_t empty_url = LITERAL_VIEW("http://127.0.0.1:8080/mcp");
    codex_agent_mcp_transport_http_t *empty_http = NULL;
    CHECK(codex_agent_mcp_transport_http_create(
              context,
              &empty_url,
              0,
              &empty,
              1,
              NULL,
              NULL,
              0u,
              1,
              NULL,
              NULL,
              0u,
              0,
              &empty,
              &empty_http) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_transport_http_has_bearer_token_environment_variable(
              context, empty_http, &present) == CODEX_AGENT_STATUS_OK);
    CHECK(present == 0);
    CHECK(codex_agent_mcp_transport_http_has_headers(context, empty_http, &present) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(present == 1);
    CHECK(codex_agent_mcp_transport_http_headers_count(context, empty_http, &count) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(count == 0u);
    CHECK(codex_agent_mcp_transport_http_has_environment_headers(context, empty_http, &present) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(present == 1);
    CHECK(codex_agent_mcp_transport_http_environment_headers_count(context, empty_http, &count) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(count == 0u);
    CHECK(codex_agent_mcp_transport_http_has_headers_helper(context, empty_http, &present) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(present == 0);

    codex_agent_string_view_t home_name = LITERAL_VIEW("HOME");
    codex_agent_string_view_t remote_name = LITERAL_VIEW("REMOTE_TOKEN");
    codex_agent_mcp_environment_variable_t *home = NULL;
    codex_agent_mcp_environment_variable_t *remote = NULL;
    CHECK(codex_agent_mcp_environment_variable_create(
              context, &home_name, 0, CODEX_AGENT_MCP_ENVIRONMENT_SOURCE_LOCAL, &home) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_environment_variable_create(
              context, &remote_name, 1, CODEX_AGENT_MCP_ENVIRONMENT_SOURCE_REMOTE, &remote) ==
          CODEX_AGENT_STATUS_OK);

    uint8_t command_bytes[] = "node";
    uint8_t argument_bytes[] = "server.js";
    uint8_t directory_bytes[] = "/workspace";
    uint8_t environment_key_bytes[] = "STATIC";
    uint8_t environment_value_bytes[] = "value";
    codex_agent_string_view_t command = {command_bytes, sizeof(command_bytes) - 1u};
    codex_agent_string_view_t arguments[] = {
        {argument_bytes, sizeof(argument_bytes) - 1u},
        LITERAL_VIEW("--safe"),
        {argument_bytes, sizeof(argument_bytes) - 1u},
    };
    codex_agent_string_view_t working_directory = {directory_bytes, sizeof(directory_bytes) - 1u};
    codex_agent_string_view_t environment_keys[] = {
        {environment_key_bytes, sizeof(environment_key_bytes) - 1u},
        LITERAL_VIEW("TOKEN"),
    };
    codex_agent_string_view_t environment_values[] = {
        {environment_value_bytes, sizeof(environment_value_bytes) - 1u},
        LITERAL_VIEW("secret-ref"),
    };
    codex_agent_mcp_environment_variable_t *forwarded[] = {home, remote, home};
    codex_agent_mcp_transport_stdio_t *stdio_transport = NULL;
    CHECK(codex_agent_mcp_transport_stdio_create(
              context,
              &command,
              arguments,
              3u,
              1,
              &working_directory,
              1,
              environment_keys,
              environment_values,
              2u,
              forwarded,
              3u,
              &stdio_transport) == CODEX_AGENT_STATUS_OK);
    CHECK(stdio_transport != NULL);
    command_bytes[0] = 'X';
    argument_bytes[0] = 'X';
    directory_bytes[0] = 'X';
    environment_key_bytes[0] = 'X';
    environment_value_bytes[0] = 'X';
    arguments[1] = empty;
    environment_keys[1] = empty;
    environment_values[1] = empty;
    forwarded[0] = remote;
    CHECK(codex_agent_mcp_environment_variable_destroy(context, &home) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_environment_variable_destroy(context, &remote) == CODEX_AGENT_STATUS_OK);

    CHECK_COPY(codex_agent_mcp_transport_stdio_command_copy, context, stdio_transport, "node");
    CHECK(codex_agent_mcp_transport_stdio_arguments_count(context, stdio_transport, &count) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(count == 3u);
    CHECK_COPY_AT(
        codex_agent_mcp_transport_stdio_argument_copy_at, context, stdio_transport, 0u, "server.js");
    CHECK_COPY_AT(
        codex_agent_mcp_transport_stdio_argument_copy_at, context, stdio_transport, 1u, "--safe");
    CHECK_COPY_AT(
        codex_agent_mcp_transport_stdio_argument_copy_at, context, stdio_transport, 2u, "server.js");
    CHECK(codex_agent_mcp_transport_stdio_has_working_directory(context, stdio_transport, &present) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(present == 1);
    CHECK_COPY(
        codex_agent_mcp_transport_stdio_working_directory_copy,
        context,
        stdio_transport,
        "/workspace");
    CHECK(codex_agent_mcp_transport_stdio_has_environment(context, stdio_transport, &present) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(present == 1);
    CHECK(codex_agent_mcp_transport_stdio_environment_count(context, stdio_transport, &count) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(count == 2u);
    CHECK_COPY_AT(
        codex_agent_mcp_transport_stdio_environment_key_copy_at,
        context,
        stdio_transport,
        0u,
        "STATIC");
    CHECK_COPY_AT(
        codex_agent_mcp_transport_stdio_environment_value_copy_at,
        context,
        stdio_transport,
        0u,
        "value");
    CHECK_COPY_AT(
        codex_agent_mcp_transport_stdio_environment_key_copy_at,
        context,
        stdio_transport,
        1u,
        "TOKEN");
    CHECK_COPY_AT(
        codex_agent_mcp_transport_stdio_environment_value_copy_at,
        context,
        stdio_transport,
        1u,
        "secret-ref");
    CHECK(codex_agent_mcp_transport_stdio_forwarded_environment_count(context, stdio_transport, &count) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(count == 3u);
    codex_agent_mcp_environment_variable_t *returned_home = NULL;
    codex_agent_mcp_environment_variable_t *returned_remote = NULL;
    codex_agent_mcp_environment_variable_t *returned_duplicate = NULL;
    CHECK(codex_agent_mcp_transport_stdio_forwarded_environment_at(
              context, stdio_transport, 0u, &returned_home) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_transport_stdio_forwarded_environment_at(
              context, stdio_transport, 1u, &returned_remote) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_transport_stdio_forwarded_environment_at(
              context, stdio_transport, 2u, &returned_duplicate) == CODEX_AGENT_STATUS_OK);
    CHECK(returned_home != returned_duplicate);
    CHECK_COPY(codex_agent_mcp_environment_variable_name_copy, context, returned_home, "HOME");
    CHECK_COPY(codex_agent_mcp_environment_variable_name_copy, context, returned_remote, "REMOTE_TOKEN");
    CHECK_COPY(codex_agent_mcp_environment_variable_name_copy, context, returned_duplicate, "HOME");

    codex_agent_mcp_environment_variable_t *missing_variable = NULL;
    CHECK(codex_agent_mcp_transport_stdio_forwarded_environment_at(
              context, stdio_transport, 3u, &missing_variable) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(missing_variable == NULL);
    size_t untouched = 71u;
    CHECK(codex_agent_mcp_transport_stdio_environment_key_copy_at(
              context, stdio_transport, 2u, NULL, 0u, &untouched) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(untouched == 71u);

    CHECK(codex_agent_mcp_environment_variable_destroy(context, &returned_home) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_transport_stdio_destroy(context, &stdio_transport) == CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_mcp_environment_variable_name_copy, context, returned_remote, "REMOTE_TOKEN");
    CHECK(codex_agent_mcp_environment_variable_destroy(context, &returned_remote) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_environment_variable_destroy(context, &returned_duplicate) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_transport_stdio_destroy(context, &stdio_transport) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_transport_http_destroy(context, &http) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_transport_http_destroy(context, &empty_http) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_transport_http_destroy(context, &http) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(context == NULL);
    return 0;
}
