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

#define CHECK_COPY(function, context, handle, expected)                           \
    do {                                                                           \
        const char *copy_expected = (expected);                                   \
        const size_t copy_size = strlen(copy_expected);                           \
        uint8_t copy_buffer[256] = {0};                                            \
        size_t copy_required = SIZE_MAX;                                           \
        CHECK(copy_size <= sizeof(copy_buffer));                                  \
        CHECK((function)((context), (handle), NULL, 0u, &copy_required) ==         \
              CODEX_AGENT_STATUS_BUFFER_TOO_SMALL);                               \
        CHECK(copy_required == copy_size);                                         \
        CHECK((function)((context), (handle), copy_buffer, sizeof(copy_buffer),    \
                         &copy_required) == CODEX_AGENT_STATUS_OK);                \
        CHECK(copy_required == copy_size);                                         \
        CHECK(memcmp(copy_buffer, copy_expected, copy_size) == 0);                 \
    } while (0)

#define CHECK_COPY_AT(function, context, handle, index, expected)                         \
    do {                                                                                  \
        const char *copy_expected = (expected);                                          \
        const size_t copy_size = strlen(copy_expected);                                  \
        uint8_t copy_buffer[256] = {0};                                                   \
        size_t copy_required = SIZE_MAX;                                                  \
        CHECK(copy_size <= sizeof(copy_buffer));                                         \
        CHECK((function)((context), (handle), (index), NULL, 0u, &copy_required) ==       \
              CODEX_AGENT_STATUS_BUFFER_TOO_SMALL);                                      \
        CHECK(copy_required == copy_size);                                                \
        CHECK((function)((context), (handle), (index), copy_buffer, sizeof(copy_buffer),  \
                         &copy_required) == CODEX_AGENT_STATUS_OK);                       \
        CHECK(copy_required == copy_size);                                                \
        CHECK(memcmp(copy_buffer, copy_expected, copy_size) == 0);                        \
    } while (0)

static int create_connector(
    codex_agent_context_t *context,
    const char *id,
    const char *name,
    codex_agent_connector_t **out_connector) {
    const codex_agent_string_view_t id_view = {(const uint8_t *)id, strlen(id)};
    const codex_agent_string_view_t name_view = {(const uint8_t *)name, strlen(name)};
    const codex_agent_string_view_t plugins[] = {
        {(const uint8_t *)"plugin-a", 8u},
        {(const uint8_t *)"plugin-a", 8u},
        {(const uint8_t *)"plugin-b", 8u},
    };
    return codex_agent_connector_create(
        context,
        &id_view,
        &name_view,
        VIEW("Description"),
        INT32_C(1),
        VIEW("https://example.invalid/install"),
        INT32_C(1),
        INT32_C(0),
        plugins,
        3u,
        out_connector);
}

static int verify_connector_integration(codex_agent_context_t *context) {
    codex_agent_connector_t *source = NULL;
    codex_agent_connector_t *first_child = NULL;
    codex_agent_connector_t *second_child = NULL;
    codex_agent_integration_connector_t *integration = NULL;
    size_t count = SIZE_MAX;
    int32_t flag = INT32_MIN;

    CHECK(create_connector(context, "connector-id", "Connector name", &source) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_connector_create(context, source, &integration) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(integration != NULL);
    CHECK(codex_agent_connector_destroy(context, &source) == CODEX_AGENT_STATUS_OK);
    CHECK(source == NULL);

    CHECK_COPY(
        codex_agent_integration_connector_id_copy,
        context,
        integration,
        "connector-id");
    CHECK_COPY(
        codex_agent_integration_connector_display_name_copy,
        context,
        integration,
        "Connector name");
    CHECK(codex_agent_integration_connector_connector(
              context, integration, &first_child) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_connector_connector(
              context, integration, &second_child) == CODEX_AGENT_STATUS_OK);
    CHECK(first_child != NULL);
    CHECK(second_child != NULL);
    CHECK(first_child != second_child);

    CHECK(codex_agent_integration_connector_destroy(context, &integration) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(integration == NULL);
    CHECK_COPY(codex_agent_connector_id_copy, context, first_child, "connector-id");
    CHECK_COPY(codex_agent_connector_name_copy, context, first_child, "Connector name");
    CHECK_COPY(codex_agent_connector_description_copy, context, first_child, "Description");
    CHECK(codex_agent_connector_has_install_url(context, first_child, &flag) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(flag == INT32_C(1));
    CHECK_COPY(
        codex_agent_connector_install_url_copy,
        context,
        first_child,
        "https://example.invalid/install");
    CHECK(codex_agent_connector_is_accessible(context, first_child, &flag) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(flag == INT32_C(1));
    CHECK(codex_agent_connector_is_enabled(context, first_child, &flag) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(flag == INT32_C(0));
    CHECK(codex_agent_connector_plugin_names_count(context, first_child, &count) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(count == 3u);
    CHECK_COPY_AT(
        codex_agent_connector_plugin_names_copy_at,
        context,
        first_child,
        0u,
        "plugin-a");
    CHECK_COPY_AT(
        codex_agent_connector_plugin_names_copy_at,
        context,
        first_child,
        1u,
        "plugin-a");
    CHECK_COPY_AT(
        codex_agent_connector_plugin_names_copy_at,
        context,
        first_child,
        2u,
        "plugin-b");
    CHECK(codex_agent_connector_destroy(context, &first_child) == CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_connector_id_copy, context, second_child, "connector-id");
    CHECK(codex_agent_connector_destroy(context, &second_child) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_connector_destroy(context, &integration) ==
          CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_invalid_boundaries(
    codex_agent_context_t *context,
    codex_agent_context_t *other_context) {
    codex_agent_connector_t *connector = NULL;
    codex_agent_connector_t *child = NULL;
    codex_agent_connector_t *occupied_child = NULL;
    codex_agent_connector_t *stale_connector;
    codex_agent_integration_connector_t *integration = NULL;
    codex_agent_integration_connector_t *invalid = NULL;
    codex_agent_integration_connector_t *stale_integration;
    size_t required = SIZE_MAX;

    CHECK(create_connector(context, "boundary-id", "Boundary connector", &connector) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_connector_create(context, connector, &integration) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(integration != NULL);

    CHECK(codex_agent_integration_connector_create(context, connector, &integration) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(integration != NULL);
    CHECK(codex_agent_integration_connector_create(context, connector, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_integration_connector_create(NULL, connector, &invalid) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid == NULL);
    CHECK(codex_agent_integration_connector_create(context, NULL, &invalid) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid == NULL);
    CHECK(codex_agent_integration_connector_create(other_context, connector, &invalid) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(invalid == NULL);
    CHECK(codex_agent_integration_connector_create(
              context, (codex_agent_connector_t *)integration, &invalid) ==
          CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(invalid == NULL);

    CHECK(codex_agent_integration_connector_connector(context, integration, &child) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(child != NULL);
    occupied_child = child;
    CHECK(codex_agent_integration_connector_connector(
              context, integration, &occupied_child) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(occupied_child == child);
    CHECK(codex_agent_integration_connector_connector(context, integration, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    occupied_child = NULL;
    CHECK(codex_agent_integration_connector_connector(NULL, integration, &occupied_child) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(occupied_child == NULL);
    CHECK(codex_agent_integration_connector_connector(
              other_context, integration, &occupied_child) == CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(occupied_child == NULL);
    CHECK(codex_agent_integration_connector_connector(
              context,
              (codex_agent_integration_connector_t *)connector,
              &occupied_child) == CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(occupied_child == NULL);

    CHECK(codex_agent_integration_connector_id_copy(
              context, integration, NULL, 0u, NULL) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_integration_connector_display_name_copy(
              context, integration, NULL, 0u, NULL) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_integration_connector_id_copy(
              other_context, integration, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(required == SIZE_MAX);
    CHECK(codex_agent_integration_connector_id_copy(
              context,
              (codex_agent_integration_connector_t *)connector,
              NULL,
              0u,
              &required) == CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(required == SIZE_MAX);
    CHECK(codex_agent_integration_connector_display_name_copy(
              other_context, integration, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(required == SIZE_MAX);
    CHECK(codex_agent_integration_connector_display_name_copy(
              context,
              (codex_agent_integration_connector_t *)connector,
              NULL,
              0u,
              &required) == CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(required == SIZE_MAX);

    {
        codex_agent_integration_connector_t *wrong =
            (codex_agent_integration_connector_t *)child;
        CHECK(codex_agent_integration_connector_destroy(context, NULL) ==
              CODEX_AGENT_STATUS_INVALID_ARGUMENT);
        CHECK(codex_agent_integration_connector_destroy(context, &wrong) ==
              CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
        CHECK(wrong == (codex_agent_integration_connector_t *)child);
    }
    CHECK(codex_agent_integration_connector_destroy(other_context, &integration) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(integration != NULL);

    stale_connector = connector;
    CHECK(codex_agent_connector_destroy(context, &connector) == CODEX_AGENT_STATUS_OK);
    CHECK(connector == NULL);
    CHECK(codex_agent_integration_connector_create(context, stale_connector, &invalid) ==
          CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(invalid == NULL);

    stale_integration = integration;
    CHECK(codex_agent_integration_connector_destroy(context, &integration) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(integration == NULL);
    CHECK(codex_agent_integration_connector_connector(
              context, stale_integration, &occupied_child) == CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(occupied_child == NULL);
    CHECK(codex_agent_integration_connector_id_copy(
              context, stale_integration, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(required == SIZE_MAX);
    CHECK(codex_agent_integration_connector_display_name_copy(
              context, stale_integration, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(required == SIZE_MAX);
    CHECK(codex_agent_integration_connector_destroy(context, &integration) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_connector_destroy(context, &child) == CODEX_AGENT_STATUS_OK);
    return 0;
}

int main(void) {
    codex_agent_context_t *context = NULL;
    codex_agent_context_t *other_context = NULL;

    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_create(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(context != NULL);
    CHECK(other_context != NULL);
    CHECK(verify_connector_integration(context) == 0);
    CHECK(verify_invalid_boundaries(context, other_context) == 0);
    CHECK(codex_agent_context_destroy(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(other_context == NULL);
    CHECK(context == NULL);
    return 0;
}
