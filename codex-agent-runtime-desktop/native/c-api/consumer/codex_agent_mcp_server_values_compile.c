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

#define VIEW(value)                                                                                 \
    (&(const codex_agent_string_view_t){(const uint8_t *)(value), sizeof(value) - 1u})

#define CHECK_COPY(function, context, handle, expected)                                              \
    do {                                                                                            \
        size_t required_ = SIZE_MAX;                                                                \
        uint8_t buffer_[128] = {0};                                                                 \
        CHECK((function)((context), (handle), NULL, 0u, &required_) ==                              \
              CODEX_AGENT_STATUS_BUFFER_TOO_SMALL);                                                 \
        CHECK(required_ == sizeof(expected) - 1u);                                                   \
        CHECK((function)((context), (handle), buffer_, sizeof(buffer_), &required_) ==               \
              CODEX_AGENT_STATUS_OK);                                                               \
        CHECK(required_ == sizeof(expected) - 1u);                                                   \
        CHECK(memcmp(buffer_, (expected), sizeof(expected) - 1u) == 0);                             \
    } while (0)

static int create_configuration(
    codex_agent_context_t *context,
    codex_agent_mcp_server_configuration_t **out_configuration) {
    const codex_agent_string_view_t absent = {NULL, 0u};
    codex_agent_mcp_transport_stdio_t *stdio = NULL;
    codex_agent_mcp_transport_t *transport = NULL;

    CHECK(codex_agent_mcp_transport_stdio_create(
              context,
              VIEW("node"),
              VIEW("server.js"),
              1u,
              INT32_C(0),
              &absent,
              INT32_C(0),
              NULL,
              NULL,
              0u,
              NULL,
              0u,
              &stdio) == CODEX_AGENT_STATUS_OK);
    CHECK(stdio != NULL);
    CHECK(codex_agent_mcp_transport_from_stdio(context, stdio, &transport) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(transport != NULL);
    CHECK(codex_agent_mcp_server_configuration_create(
              context,
              VIEW("config_server"),
              transport,
              INT32_C(0),
              INT32_C(0),
              VIEW("local"),
              INT32_C(1),
              INT32_C(0),
              INT32_C(0),
              INT32_C(0),
              NULL,
              0u,
              INT32_C(0),
              0.0,
              INT32_C(0),
              0.0,
              INT32_C(0),
              INT32_C(0),
              INT32_C(0),
              NULL,
              0u,
              INT32_C(0),
              NULL,
              0u,
              INT32_C(0),
              NULL,
              0u,
              INT32_C(0),
              NULL,
              INT32_C(0),
              &absent,
              NULL,
              NULL,
              0u,
              out_configuration) == CODEX_AGENT_STATUS_OK);
    CHECK(*out_configuration != NULL);
    CHECK(codex_agent_mcp_transport_destroy(context, &transport) == CODEX_AGENT_STATUS_OK);
    CHECK(transport == NULL);
    CHECK(codex_agent_mcp_transport_stdio_destroy(context, &stdio) == CODEX_AGENT_STATUS_OK);
    CHECK(stdio == NULL);
    return 0;
}

static int verify_constructor_names_origins_and_can_remove(codex_agent_context_t *context) {
    const codex_agent_resource_origin_t origins[] = {
        CODEX_AGENT_RESOURCE_ORIGIN_USER,
        CODEX_AGENT_RESOURCE_ORIGIN_WORKSPACE,
        CODEX_AGENT_RESOURCE_ORIGIN_PLUGIN,
        CODEX_AGENT_RESOURCE_ORIGIN_MANAGED,
        CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN,
    };
    uint8_t name_bytes[] = "server_user";
    uint8_t display_name_bytes[] = "Server user";
    codex_agent_string_view_t name = {name_bytes, sizeof(name_bytes) - 1u};
    codex_agent_string_view_t display_name = {display_name_bytes, sizeof(display_name_bytes) - 1u};
    size_t index;

    for (index = 0u; index < sizeof(origins) / sizeof(origins[0]); ++index) {
        codex_agent_mcp_server_t *server = NULL;
        codex_agent_resource_origin_t origin = INT32_MIN;
        int32_t can_remove = INT32_MIN;
        int32_t has_configuration = INT32_MIN;
        codex_agent_mcp_server_configuration_t *absent_configuration = NULL;
        const int32_t expected_can_remove = (int32_t)(index % 2u);
        const codex_agent_string_view_t *server_name = index == 0u ? &name : VIEW("server");
        const codex_agent_string_view_t *server_display = index == 0u ? &display_name : VIEW("Server");

        CHECK(codex_agent_mcp_server_create(
                  context,
                  server_name,
                  server_display,
                  CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN,
                  NULL,
                  origins[index],
                  expected_can_remove,
                  &server) == CODEX_AGENT_STATUS_OK);
        CHECK(server != NULL);
        if (index == 0u) {
            name_bytes[0] = 'X';
            display_name_bytes[0] = 'X';
            CHECK_COPY(codex_agent_mcp_server_name_copy, context, server, "server_user");
            CHECK_COPY(codex_agent_mcp_server_display_name_copy, context, server, "Server user");
        } else {
            CHECK_COPY(codex_agent_mcp_server_name_copy, context, server, "server");
            CHECK_COPY(codex_agent_mcp_server_display_name_copy, context, server, "Server");
        }
        CHECK(codex_agent_mcp_server_origin(context, server, &origin) == CODEX_AGENT_STATUS_OK);
        CHECK(origin == origins[index]);
        CHECK(codex_agent_mcp_server_can_remove(context, server, &can_remove) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(can_remove == expected_can_remove);
        CHECK(codex_agent_mcp_server_has_configuration(context, server, &has_configuration) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(has_configuration == INT32_C(0));
        CHECK(codex_agent_mcp_server_configuration(context, server, &absent_configuration) ==
              CODEX_AGENT_STATUS_NOT_READY);
        CHECK(absent_configuration == NULL);
        CHECK(codex_agent_mcp_server_destroy(context, &server) == CODEX_AGENT_STATUS_OK);
        CHECK(server == NULL);
    }
    return 0;
}

static int verify_auth_status_and_is_authorized(codex_agent_context_t *context) {
    const codex_agent_mcp_auth_status_t statuses[] = {
        CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN,
        CODEX_AGENT_MCP_AUTH_STATUS_UNSUPPORTED,
        CODEX_AGENT_MCP_AUTH_STATUS_NOT_LOGGED_IN,
        CODEX_AGENT_MCP_AUTH_STATUS_BEARER_TOKEN,
        CODEX_AGENT_MCP_AUTH_STATUS_OAUTH,
    };
    const int32_t authorized[] = {INT32_C(0), INT32_C(0), INT32_C(0), INT32_C(1), INT32_C(1)};
    size_t index;

    for (index = 0u; index < sizeof(statuses) / sizeof(statuses[0]); ++index) {
        codex_agent_mcp_server_t *server = NULL;
        codex_agent_mcp_auth_status_t auth_status = INT32_MIN;
        int32_t is_authorized = INT32_MIN;
        CHECK(codex_agent_mcp_server_create(
                  context,
                  VIEW("server"),
                  VIEW("Server"),
                  statuses[index],
                  NULL,
                  CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN,
                  INT32_C(0),
                  &server) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_mcp_server_auth_status(context, server, &auth_status) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(auth_status == statuses[index]);
        CHECK(codex_agent_mcp_server_is_authorized(context, server, &is_authorized) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(is_authorized == authorized[index]);
        CHECK(codex_agent_mcp_server_destroy(context, &server) == CODEX_AGENT_STATUS_OK);
    }
    return 0;
}

static int verify_configuration_ownership(codex_agent_context_t *context) {
    codex_agent_mcp_server_configuration_t *source = NULL;
    codex_agent_mcp_server_configuration_t *first_child = NULL;
    codex_agent_mcp_server_configuration_t *second_child = NULL;
    codex_agent_mcp_server_t *server = NULL;
    int32_t has_configuration = INT32_MIN;

    CHECK(create_configuration(context, &source) == 0);
    CHECK(codex_agent_mcp_server_create(
              context,
              VIEW("configured"),
              VIEW("Configured"),
              CODEX_AGENT_MCP_AUTH_STATUS_BEARER_TOKEN,
              source,
              CODEX_AGENT_RESOURCE_ORIGIN_MANAGED,
              INT32_C(1),
              &server) == CODEX_AGENT_STATUS_OK);
    CHECK(server != NULL);
    CHECK(codex_agent_mcp_server_configuration_destroy(context, &source) == CODEX_AGENT_STATUS_OK);
    CHECK(source == NULL);
    CHECK(codex_agent_mcp_server_has_configuration(context, server, &has_configuration) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(has_configuration == INT32_C(1));
    CHECK(codex_agent_mcp_server_configuration(context, server, &first_child) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_server_configuration(context, server, &second_child) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(first_child != NULL);
    CHECK(second_child != NULL);
    CHECK(first_child != second_child);
    CHECK(codex_agent_mcp_server_destroy(context, &server) == CODEX_AGENT_STATUS_OK);
    CHECK(server == NULL);
    CHECK_COPY(
        codex_agent_mcp_server_configuration_name_copy,
        context,
        first_child,
        "config_server");
    CHECK_COPY(
        codex_agent_mcp_server_configuration_name_copy,
        context,
        second_child,
        "config_server");
    CHECK(codex_agent_mcp_server_configuration_destroy(context, &first_child) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(first_child == NULL);
    CHECK_COPY(
        codex_agent_mcp_server_configuration_name_copy,
        context,
        second_child,
        "config_server");
    CHECK(codex_agent_mcp_server_configuration_destroy(context, &second_child) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(second_child == NULL);
    return 0;
}

static int verify_constructor_boundaries(
    codex_agent_context_t *context,
    codex_agent_context_t *other_context) {
    const uint8_t invalid_utf8_bytes[] = {UINT8_C(0xff)};
    const codex_agent_string_view_t invalid_utf8 = {invalid_utf8_bytes, 1u};
    const int32_t invalid_values[] = {INT32_C(-1), INT32_C(5), INT32_MIN, INT32_MAX};
    const int32_t invalid_flags[] = {INT32_C(-1), INT32_C(2), INT32_MIN, INT32_MAX};
    codex_agent_mcp_server_configuration_t *configuration = NULL;
    codex_agent_mcp_server_configuration_t *stale_configuration;
    codex_agent_mcp_server_t *wrong_type = NULL;
    codex_agent_mcp_server_t *output = NULL;
    size_t index;

    for (index = 0u; index < sizeof(invalid_values) / sizeof(invalid_values[0]); ++index) {
        CHECK(codex_agent_mcp_server_create(
                  context,
                  VIEW("server"),
                  VIEW("Server"),
                  invalid_values[index],
                  NULL,
                  CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN,
                  INT32_C(0),
                  &output) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK(output == NULL);
        CHECK(codex_agent_mcp_server_create(
                  context,
                  VIEW("server"),
                  VIEW("Server"),
                  CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN,
                  NULL,
                  invalid_values[index],
                  INT32_C(0),
                  &output) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK(output == NULL);
    }
    for (index = 0u; index < sizeof(invalid_flags) / sizeof(invalid_flags[0]); ++index) {
        CHECK(codex_agent_mcp_server_create(
                  context,
                  VIEW("server"),
                  VIEW("Server"),
                  CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN,
                  NULL,
                  CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN,
                  invalid_flags[index],
                  &output) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK(output == NULL);
    }

    CHECK(codex_agent_mcp_server_create(
              NULL,
              VIEW("server"),
              VIEW("Server"),
              CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN,
              NULL,
              CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN,
              INT32_C(0),
              &output) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_mcp_server_create(
              context,
              NULL,
              VIEW("Server"),
              CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN,
              NULL,
              CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN,
              INT32_C(0),
              &output) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_mcp_server_create(
              context,
              VIEW("server"),
              NULL,
              CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN,
              NULL,
              CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN,
              INT32_C(0),
              &output) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_mcp_server_create(
              context,
              &invalid_utf8,
              VIEW("Server"),
              CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN,
              NULL,
              CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN,
              INT32_C(0),
              &output) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_mcp_server_create(
              context,
              VIEW("server"),
              VIEW("Server"),
              CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN,
              NULL,
              CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN,
              INT32_C(0),
              NULL) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(output == NULL);

    CHECK(create_configuration(context, &configuration) == 0);
    CHECK(codex_agent_mcp_server_create(
              other_context,
              VIEW("server"),
              VIEW("Server"),
              CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN,
              configuration,
              CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN,
              INT32_C(0),
              &output) == CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(output == NULL);
    CHECK(codex_agent_mcp_server_create(
              context,
              VIEW("wrong_type"),
              VIEW("Wrong type"),
              CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN,
              NULL,
              CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN,
              INT32_C(0),
              &wrong_type) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_server_create(
              context,
              VIEW("server"),
              VIEW("Server"),
              CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN,
              (codex_agent_mcp_server_configuration_t *)wrong_type,
              CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN,
              INT32_C(0),
              &output) == CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(output == NULL);

    stale_configuration = configuration;
    CHECK(codex_agent_mcp_server_configuration_destroy(context, &configuration) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(configuration == NULL);
    CHECK(codex_agent_mcp_server_create(
              context,
              VIEW("server"),
              VIEW("Server"),
              CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN,
              stale_configuration,
              CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN,
              INT32_C(0),
              &output) == CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(output == NULL);

    output = wrong_type;
    CHECK(codex_agent_mcp_server_create(
              context,
              VIEW("server"),
              VIEW("Server"),
              CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN,
              NULL,
              CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN,
              INT32_C(0),
              &output) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(output == wrong_type);
    CHECK(codex_agent_mcp_server_destroy(context, &wrong_type) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_getter_and_destroy_boundaries(
    codex_agent_context_t *context,
    codex_agent_context_t *other_context) {
    codex_agent_mcp_server_configuration_t *configuration = NULL;
    codex_agent_mcp_server_t *server = NULL;
    codex_agent_mcp_server_t *stale_server;
    codex_agent_mcp_server_configuration_t *child = NULL;
    size_t required = SIZE_MAX;
    int32_t scalar = INT32_MIN;

    CHECK(create_configuration(context, &configuration) == 0);
    CHECK(codex_agent_mcp_server_create(
              context,
              VIEW("boundary"),
              VIEW("Boundary"),
              CODEX_AGENT_MCP_AUTH_STATUS_OAUTH,
              configuration,
              CODEX_AGENT_RESOURCE_ORIGIN_PLUGIN,
              INT32_C(1),
              &server) == CODEX_AGENT_STATUS_OK);

    CHECK(codex_agent_mcp_server_name_copy(context, server, NULL, 0u, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_mcp_server_display_name_copy(context, server, NULL, 0u, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_mcp_server_auth_status(context, server, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_mcp_server_has_configuration(context, server, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_mcp_server_configuration(context, server, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_mcp_server_origin(context, server, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_mcp_server_can_remove(context, server, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_mcp_server_is_authorized(context, server, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_mcp_server_destroy(context, NULL) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);

    child = configuration;
    CHECK(codex_agent_mcp_server_configuration(context, server, &child) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(child == configuration);
    child = NULL;

    CHECK(codex_agent_mcp_server_name_copy(other_context, server, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(codex_agent_mcp_server_display_name_copy(other_context, server, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(codex_agent_mcp_server_auth_status(other_context, server, &scalar) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(codex_agent_mcp_server_has_configuration(other_context, server, &scalar) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(codex_agent_mcp_server_configuration(other_context, server, &child) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(codex_agent_mcp_server_origin(other_context, server, &scalar) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(codex_agent_mcp_server_can_remove(other_context, server, &scalar) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(codex_agent_mcp_server_is_authorized(other_context, server, &scalar) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(required == SIZE_MAX);
    CHECK(scalar == INT32_MIN);
    CHECK(child == NULL);

    CHECK(codex_agent_mcp_server_name_copy(
              context, (codex_agent_mcp_server_t *)configuration, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(codex_agent_mcp_server_display_name_copy(
              context, (codex_agent_mcp_server_t *)configuration, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(codex_agent_mcp_server_auth_status(
              context, (codex_agent_mcp_server_t *)configuration, &scalar) ==
          CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(codex_agent_mcp_server_has_configuration(
              context, (codex_agent_mcp_server_t *)configuration, &scalar) ==
          CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(codex_agent_mcp_server_configuration(
              context, (codex_agent_mcp_server_t *)configuration, &child) ==
          CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(codex_agent_mcp_server_origin(
              context, (codex_agent_mcp_server_t *)configuration, &scalar) ==
          CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(codex_agent_mcp_server_can_remove(
              context, (codex_agent_mcp_server_t *)configuration, &scalar) ==
          CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(codex_agent_mcp_server_is_authorized(
              context, (codex_agent_mcp_server_t *)configuration, &scalar) ==
          CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(required == SIZE_MAX);
    CHECK(scalar == INT32_MIN);
    CHECK(child == NULL);

    {
        codex_agent_mcp_server_t *wrong_destroy = (codex_agent_mcp_server_t *)configuration;
        CHECK(codex_agent_mcp_server_destroy(context, &wrong_destroy) ==
              CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
        CHECK(wrong_destroy == (codex_agent_mcp_server_t *)configuration);
    }
    CHECK(codex_agent_mcp_server_destroy(other_context, &server) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(server != NULL);

    stale_server = server;
    CHECK(codex_agent_mcp_server_destroy(context, &server) == CODEX_AGENT_STATUS_OK);
    CHECK(server == NULL);
    CHECK(codex_agent_mcp_server_name_copy(context, stale_server, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(codex_agent_mcp_server_display_name_copy(context, stale_server, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(codex_agent_mcp_server_auth_status(context, stale_server, &scalar) ==
          CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(codex_agent_mcp_server_has_configuration(context, stale_server, &scalar) ==
          CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(codex_agent_mcp_server_configuration(context, stale_server, &child) ==
          CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(codex_agent_mcp_server_origin(context, stale_server, &scalar) ==
          CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(codex_agent_mcp_server_can_remove(context, stale_server, &scalar) ==
          CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(codex_agent_mcp_server_is_authorized(context, stale_server, &scalar) ==
          CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(required == SIZE_MAX);
    CHECK(scalar == INT32_MIN);
    CHECK(child == NULL);
    CHECK(codex_agent_mcp_server_destroy(context, &server) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_server_configuration_destroy(context, &configuration) ==
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
    CHECK(verify_constructor_names_origins_and_can_remove(context) == 0);
    CHECK(verify_auth_status_and_is_authorized(context) == 0);
    CHECK(verify_configuration_ownership(context) == 0);
    CHECK(verify_constructor_boundaries(context, other_context) == 0);
    CHECK(verify_getter_and_destroy_boundaries(context, other_context) == 0);
    CHECK(codex_agent_context_destroy(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(other_context == NULL);
    CHECK(context == NULL);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    return 0;
}
