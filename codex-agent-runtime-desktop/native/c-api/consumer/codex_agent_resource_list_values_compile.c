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

#define VIEW(value) \
    (&(const codex_agent_string_view_t){(const uint8_t *)(value), sizeof(value) - 1u})

#define CHECK_COPY(function, context, handle, expected) \
    do { \
        const char *copy_expected = (expected); \
        const size_t copy_size = strlen(copy_expected); \
        uint8_t copy_buffer[256] = {0}; \
        size_t copy_required = SIZE_MAX; \
        CHECK(copy_size <= sizeof(copy_buffer)); \
        CHECK((function)((context), (handle), NULL, 0u, &copy_required) == \
              (copy_size == 0u ? CODEX_AGENT_STATUS_OK : CODEX_AGENT_STATUS_BUFFER_TOO_SMALL)); \
        CHECK(copy_required == copy_size); \
        CHECK((function)((context), (handle), copy_buffer, sizeof(copy_buffer), &copy_required) == \
              CODEX_AGENT_STATUS_OK); \
        CHECK(copy_required == copy_size); \
        CHECK(memcmp(copy_buffer, copy_expected, copy_size) == 0); \
    } while (0)

#define CHECK_COPY_AT(function, context, handle, index, expected) \
    do { \
        const char *copy_at_expected = (expected); \
        const size_t copy_at_size = strlen(copy_at_expected); \
        uint8_t copy_at_buffer[256] = {0}; \
        size_t copy_at_required = SIZE_MAX; \
        CHECK(copy_at_size <= sizeof(copy_at_buffer)); \
        CHECK((function)((context), (handle), (index), NULL, 0u, &copy_at_required) == \
              (copy_at_size == 0u ? CODEX_AGENT_STATUS_OK : CODEX_AGENT_STATUS_BUFFER_TOO_SMALL)); \
        CHECK(copy_at_required == copy_at_size); \
        CHECK((function)((context), (handle), (index), copy_at_buffer, sizeof(copy_at_buffer), \
                         &copy_at_required) == CODEX_AGENT_STATUS_OK); \
        CHECK(copy_at_required == copy_at_size); \
        CHECK(memcmp(copy_at_buffer, copy_at_expected, copy_at_size) == 0); \
    } while (0)

static const codex_agent_string_view_t EMPTY_VIEW = {NULL, 0u};

static int create_connector(
    codex_agent_context_t *context,
    const char *id,
    codex_agent_connector_t **out_connector) {
    const codex_agent_string_view_t plugin_names[] = {
        {(const uint8_t *)"plugin-a", 8u},
        {(const uint8_t *)"plugin-a", 8u},
    };
    const codex_agent_string_view_t id_view = {(const uint8_t *)id, strlen(id)};
    return codex_agent_connector_create(
        context,
        &id_view,
        VIEW("Connector"),
        VIEW("Description"),
        INT32_C(0),
        &EMPTY_VIEW,
        INT32_C(1),
        INT32_C(1),
        plugin_names,
        2u,
        out_connector);
}

static int create_reference(
    codex_agent_context_t *context,
    const char *id,
    codex_agent_plugin_reference_t **out_reference) {
    const codex_agent_string_view_t id_view = {(const uint8_t *)id, strlen(id)};
    return codex_agent_plugin_reference_create(
        context,
        &id_view,
        VIEW("plugin"),
        VIEW("marketplace"),
        INT32_C(0),
        &EMPTY_VIEW,
        INT32_C(0),
        &EMPTY_VIEW,
        out_reference);
}

static int create_summary(
    codex_agent_context_t *context,
    codex_agent_plugin_reference_t *reference,
    const char *name,
    codex_agent_plugin_summary_t **out_summary) {
    const codex_agent_string_view_t name_view = {(const uint8_t *)name, strlen(name)};
    return codex_agent_plugin_summary_create(
        context,
        reference,
        &name_view,
        VIEW("Summary"),
        INT32_C(1),
        INT32_C(1),
        CODEX_AGENT_PLUGIN_INSTALL_POLICY_AVAILABLE,
        CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_INSTALL,
        INT32_C(1),
        NULL,
        0u,
        INT32_C(0),
        &EMPTY_VIEW,
        INT32_C(0),
        &EMPTY_VIEW,
        INT32_C(0),
        &EMPTY_VIEW,
        INT32_C(0),
        &EMPTY_VIEW,
        out_summary);
}

static int verify_connector(codex_agent_context_t *context) {
    uint8_t mutable_id[] = "connector-id";
    uint8_t mutable_plugin[] = "plugin-a";
    const codex_agent_string_view_t id = {mutable_id, sizeof(mutable_id) - 1u};
    const codex_agent_string_view_t plugin_names[] = {
        {mutable_plugin, sizeof(mutable_plugin) - 1u},
        {(const uint8_t *)"plugin-a", 8u},
        {(const uint8_t *)"plugin-b", 8u},
    };
    codex_agent_connector_t *connector = NULL;
    codex_agent_connector_t *empty = NULL;
    int32_t value = INT32_C(-1);
    size_t count = SIZE_MAX;
    size_t required = SIZE_MAX;

    CHECK(codex_agent_connector_create(
              context,
              &id,
              VIEW("Connector"),
              VIEW("Description"),
              INT32_C(1),
              VIEW("https://example.invalid/install"),
              INT32_C(1),
              INT32_C(0),
              plugin_names,
              3u,
              &connector) == CODEX_AGENT_STATUS_OK);
    CHECK(connector != NULL);
    mutable_id[0] = (uint8_t)'X';
    mutable_plugin[0] = (uint8_t)'X';
    CHECK_COPY(codex_agent_connector_id_copy, context, connector, "connector-id");
    CHECK_COPY(codex_agent_connector_name_copy, context, connector, "Connector");
    CHECK_COPY(codex_agent_connector_description_copy, context, connector, "Description");
    CHECK(codex_agent_connector_has_install_url(context, connector, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK_COPY(
        codex_agent_connector_install_url_copy,
        context,
        connector,
        "https://example.invalid/install");
    CHECK(codex_agent_connector_is_accessible(context, connector, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK(codex_agent_connector_is_enabled(context, connector, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(0));
    CHECK(codex_agent_connector_plugin_names_count(context, connector, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 3u);
    CHECK_COPY_AT(codex_agent_connector_plugin_names_copy_at, context, connector, 0u, "plugin-a");
    CHECK_COPY_AT(codex_agent_connector_plugin_names_copy_at, context, connector, 1u, "plugin-a");
    CHECK_COPY_AT(codex_agent_connector_plugin_names_copy_at, context, connector, 2u, "plugin-b");

    CHECK(codex_agent_connector_create(
              context,
              VIEW("empty"),
              VIEW("Empty"),
              &EMPTY_VIEW,
              INT32_C(0),
              &EMPTY_VIEW,
              INT32_C(0),
              INT32_C(1),
              NULL,
              0u,
              &empty) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_connector_has_install_url(context, empty, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(0));
    required = SIZE_MAX;
    CHECK(codex_agent_connector_install_url_copy(context, empty, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_NOT_READY);
    CHECK(required == SIZE_MAX);
    CHECK(codex_agent_connector_plugin_names_count(context, empty, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 0u);
    required = SIZE_MAX;
    CHECK(codex_agent_connector_plugin_names_copy_at(context, empty, 0u, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(required == SIZE_MAX);

    CHECK(codex_agent_connector_destroy(context, &empty) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_connector_destroy(context, &connector) == CODEX_AGENT_STATUS_OK);
    CHECK(connector == NULL);
    CHECK(codex_agent_connector_destroy(context, &connector) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_skills(codex_agent_context_t *context) {
    uint8_t mutable_dependency[] = "git";
    const codex_agent_string_view_t dependencies[] = {
        {mutable_dependency, sizeof(mutable_dependency) - 1u},
        {(const uint8_t *)"git", 3u},
        {(const uint8_t *)"docker", 6u},
    };
    const codex_agent_string_view_t errors[] = {
        {(const uint8_t *)"warning", 7u},
        {(const uint8_t *)"warning", 7u},
    };
    codex_agent_skill_t *skill = NULL;
    codex_agent_skill_t *managed = NULL;
    codex_agent_skill_t *nested_one = NULL;
    codex_agent_skill_t *nested_two = NULL;
    codex_agent_skill_catalog_t *catalog = NULL;
    codex_agent_skill_catalog_t *empty = NULL;
    codex_agent_skill_t *skill_values[3];
    int32_t value = INT32_C(-1);
    size_t count = SIZE_MAX;
    size_t required = SIZE_MAX;

    CHECK(codex_agent_skill_create(
              context,
              VIEW("review"),
              VIEW("Review"),
              VIEW("Review changes"),
              VIEW("/skills/review.md"),
              CODEX_AGENT_SKILL_SCOPE_USER,
              INT32_C(1),
              INT32_C(1),
              VIEW("#123456"),
              dependencies,
              3u,
              INT32_C(1),
              INT32_C(0),
              CODEX_AGENT_RESOURCE_ORIGIN_USER,
              &skill) == CODEX_AGENT_STATUS_OK);
    mutable_dependency[0] = (uint8_t)'X';
    CHECK_COPY(codex_agent_skill_name_copy, context, skill, "review");
    CHECK_COPY(codex_agent_skill_display_name_copy, context, skill, "Review");
    CHECK_COPY(codex_agent_skill_description_copy, context, skill, "Review changes");
    CHECK_COPY(codex_agent_skill_path_copy, context, skill, "/skills/review.md");
    CHECK(codex_agent_skill_scope(context, skill, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == CODEX_AGENT_SKILL_SCOPE_USER);
    CHECK(codex_agent_skill_is_enabled(context, skill, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK(codex_agent_skill_has_brand_color(context, skill, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK_COPY(codex_agent_skill_brand_color_copy, context, skill, "#123456");
    CHECK(codex_agent_skill_dependencies_count(context, skill, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 3u);
    CHECK_COPY_AT(codex_agent_skill_dependencies_copy_at, context, skill, 0u, "git");
    CHECK_COPY_AT(codex_agent_skill_dependencies_copy_at, context, skill, 1u, "git");
    CHECK_COPY_AT(codex_agent_skill_dependencies_copy_at, context, skill, 2u, "docker");
    CHECK(codex_agent_skill_can_uninstall(context, skill, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK(codex_agent_skill_origin(context, skill, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == CODEX_AGENT_RESOURCE_ORIGIN_USER);

    CHECK(codex_agent_skill_create(
              context,
              VIEW("managed"),
              VIEW("Managed"),
              VIEW("Managed skill"),
              VIEW("/skills/managed.md"),
              CODEX_AGENT_SKILL_SCOPE_SYSTEM,
              INT32_C(0),
              INT32_C(0),
              &EMPTY_VIEW,
              NULL,
              0u,
              INT32_C(0),
              INT32_C(1),
              CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN,
              &managed) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_skill_has_brand_color(context, managed, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(0));
    CHECK(codex_agent_skill_brand_color_copy(context, managed, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_NOT_READY);
    CHECK(codex_agent_skill_origin(context, managed, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN);

    skill_values[0] = skill;
    skill_values[1] = skill;
    skill_values[2] = managed;
    CHECK(codex_agent_skill_catalog_create(
              context, skill_values, 3u, errors, 2u, &catalog) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_skill_destroy(context, &skill) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_skill_destroy(context, &managed) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_skill_catalog_skills_count(context, catalog, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 3u);
    CHECK(codex_agent_skill_catalog_errors_count(context, catalog, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 2u);
    CHECK_COPY_AT(codex_agent_skill_catalog_errors_copy_at, context, catalog, 0u, "warning");
    CHECK_COPY_AT(codex_agent_skill_catalog_errors_copy_at, context, catalog, 1u, "warning");
    CHECK(codex_agent_skill_catalog_skills_at(context, catalog, 0u, &nested_one) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_skill_catalog_skills_at(context, catalog, 0u, &nested_two) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(nested_one != nested_two);
    CHECK_COPY(codex_agent_skill_name_copy, context, nested_one, "review");

    CHECK(codex_agent_skill_catalog_create(
              context, NULL, 0u, NULL, 0u, &empty) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_skill_catalog_skills_count(context, empty, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 0u);
    CHECK(codex_agent_skill_catalog_errors_count(context, empty, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 0u);

    CHECK(codex_agent_skill_destroy(context, &nested_two) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_skill_destroy(context, &nested_one) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_skill_catalog_destroy(context, &empty) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_skill_catalog_destroy(context, &catalog) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_plugin_summaries(codex_agent_context_t *context) {
    uint8_t mutable_capability[] = "hooks";
    const codex_agent_string_view_t capabilities[] = {
        {mutable_capability, sizeof(mutable_capability) - 1u},
        {(const uint8_t *)"hooks", 5u},
        {(const uint8_t *)"skills", 6u},
    };
    const codex_agent_string_view_t errors[] = {
        {(const uint8_t *)"error", 5u},
        {(const uint8_t *)"error", 5u},
    };
    codex_agent_plugin_reference_t *reference = NULL;
    codex_agent_plugin_reference_t *nested_reference_one = NULL;
    codex_agent_plugin_reference_t *nested_reference_two = NULL;
    codex_agent_plugin_summary_t *summary = NULL;
    codex_agent_plugin_summary_t *absent = NULL;
    codex_agent_plugin_summary_t *nested_summary = NULL;
    codex_agent_plugin_catalog_t *catalog = NULL;
    codex_agent_plugin_catalog_t *empty = NULL;
    codex_agent_plugin_summary_t *summaries[3];
    int32_t value = INT32_C(-1);
    size_t count = SIZE_MAX;
    size_t required = SIZE_MAX;

    CHECK(create_reference(context, "plugin-id", &reference) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_summary_create(
              context,
              reference,
              VIEW("Tools"),
              VIEW("Tooling plugin"),
              INT32_C(1),
              INT32_C(0),
              CODEX_AGENT_PLUGIN_INSTALL_POLICY_INSTALLED_BY_DEFAULT,
              CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_USE,
              INT32_C(1),
              capabilities,
              3u,
              INT32_C(1),
              VIEW("#abcdef"),
              INT32_C(1),
              VIEW("https://example.invalid/privacy"),
              INT32_C(1),
              VIEW("https://example.invalid/terms"),
              INT32_C(1),
              VIEW("https://example.invalid"),
              &summary) == CODEX_AGENT_STATUS_OK);
    mutable_capability[0] = (uint8_t)'X';
    CHECK(codex_agent_plugin_reference_destroy(context, &reference) == CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_plugin_summary_display_name_copy, context, summary, "Tools");
    CHECK_COPY(codex_agent_plugin_summary_description_copy, context, summary, "Tooling plugin");
    CHECK(codex_agent_plugin_summary_is_installed(context, summary, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK(codex_agent_plugin_summary_is_enabled(context, summary, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(0));
    CHECK(codex_agent_plugin_summary_install_policy(context, summary, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == CODEX_AGENT_PLUGIN_INSTALL_POLICY_INSTALLED_BY_DEFAULT);
    CHECK(codex_agent_plugin_summary_auth_policy(context, summary, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_USE);
    CHECK(codex_agent_plugin_summary_is_available(context, summary, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK(codex_agent_plugin_summary_capabilities_count(context, summary, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 3u);
    CHECK_COPY_AT(codex_agent_plugin_summary_capabilities_copy_at, context, summary, 0u, "hooks");
    CHECK_COPY_AT(codex_agent_plugin_summary_capabilities_copy_at, context, summary, 1u, "hooks");
    CHECK_COPY_AT(codex_agent_plugin_summary_capabilities_copy_at, context, summary, 2u, "skills");
    CHECK(codex_agent_plugin_summary_has_brand_color(context, summary, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK_COPY(codex_agent_plugin_summary_brand_color_copy, context, summary, "#abcdef");
    CHECK(codex_agent_plugin_summary_has_privacy_policy_url(context, summary, &value) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK_COPY(
        codex_agent_plugin_summary_privacy_policy_url_copy,
        context,
        summary,
        "https://example.invalid/privacy");
    CHECK(codex_agent_plugin_summary_has_terms_of_service_url(context, summary, &value) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK_COPY(
        codex_agent_plugin_summary_terms_of_service_url_copy,
        context,
        summary,
        "https://example.invalid/terms");
    CHECK(codex_agent_plugin_summary_has_website_url(context, summary, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK_COPY(
        codex_agent_plugin_summary_website_url_copy,
        context,
        summary,
        "https://example.invalid");
    CHECK(codex_agent_plugin_summary_reference(context, summary, &nested_reference_one) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_summary_reference(context, summary, &nested_reference_two) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(nested_reference_one != nested_reference_two);
    CHECK_COPY(codex_agent_plugin_reference_id_copy, context, nested_reference_one, "plugin-id");

    CHECK(create_reference(context, "absent-id", &reference) == CODEX_AGENT_STATUS_OK);
    CHECK(create_summary(context, reference, "Absent", &absent) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_reference_destroy(context, &reference) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_summary_capabilities_count(context, absent, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 0u);
    CHECK(codex_agent_plugin_summary_has_brand_color(context, absent, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(0));
    CHECK(codex_agent_plugin_summary_brand_color_copy(context, absent, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_NOT_READY);
    CHECK(codex_agent_plugin_summary_has_privacy_policy_url(context, absent, &value) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(0));
    CHECK(codex_agent_plugin_summary_privacy_policy_url_copy(context, absent, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_NOT_READY);
    CHECK(codex_agent_plugin_summary_has_terms_of_service_url(context, absent, &value) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(0));
    CHECK(codex_agent_plugin_summary_terms_of_service_url_copy(context, absent, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_NOT_READY);
    CHECK(codex_agent_plugin_summary_has_website_url(context, absent, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(0));
    CHECK(codex_agent_plugin_summary_website_url_copy(context, absent, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_NOT_READY);

    summaries[0] = summary;
    summaries[1] = summary;
    summaries[2] = absent;
    CHECK(codex_agent_plugin_catalog_create(
              context,
              summaries,
              3u,
              errors,
              2u,
              CODEX_AGENT_CATALOG_FRESHNESS_STALE_CACHE,
              &catalog) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_summary_destroy(context, &summary) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_summary_destroy(context, &absent) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_catalog_plugins_count(context, catalog, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 3u);
    CHECK(codex_agent_plugin_catalog_errors_count(context, catalog, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 2u);
    CHECK_COPY_AT(codex_agent_plugin_catalog_errors_copy_at, context, catalog, 1u, "error");
    CHECK(codex_agent_plugin_catalog_freshness(context, catalog, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == CODEX_AGENT_CATALOG_FRESHNESS_STALE_CACHE);
    CHECK(codex_agent_plugin_catalog_plugins_at(context, catalog, 0u, &nested_summary) ==
          CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_plugin_summary_display_name_copy, context, nested_summary, "Tools");

    CHECK(codex_agent_plugin_catalog_create(
              context,
              NULL,
              0u,
              NULL,
              0u,
              CODEX_AGENT_CATALOG_FRESHNESS_LIVE,
              &empty) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_catalog_plugins_count(context, empty, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 0u);
    CHECK(codex_agent_plugin_catalog_errors_count(context, empty, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 0u);

    CHECK(codex_agent_plugin_summary_destroy(context, &nested_summary) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_catalog_destroy(context, &empty) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_catalog_destroy(context, &catalog) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_reference_destroy(context, &nested_reference_two) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_reference_destroy(context, &nested_reference_one) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_plugin_detail_and_install(codex_agent_context_t *context) {
    const codex_agent_string_view_t mcp_servers[] = {
        {(const uint8_t *)"server-a", 8u},
        {(const uint8_t *)"server-a", 8u},
        {(const uint8_t *)"server-b", 8u},
    };
    codex_agent_connector_t *connector = NULL;
    codex_agent_connector_t *nested_connector_one = NULL;
    codex_agent_connector_t *nested_connector_two = NULL;
    codex_agent_connector_t *install_connector = NULL;
    codex_agent_plugin_skill_t *skill = NULL;
    codex_agent_plugin_skill_t *nested_skill = NULL;
    codex_agent_plugin_reference_t *reference = NULL;
    codex_agent_plugin_summary_t *summary = NULL;
    codex_agent_plugin_summary_t *nested_summary = NULL;
    codex_agent_plugin_detail_t *detail = NULL;
    codex_agent_plugin_detail_t *empty_detail = NULL;
    codex_agent_plugin_install_result_t *install = NULL;
    codex_agent_plugin_install_result_t *absent = NULL;
    codex_agent_plugin_skill_t *skills[2];
    codex_agent_connector_t *connectors[2];
    int32_t value = INT32_C(-1);
    size_t count = SIZE_MAX;
    size_t required = SIZE_MAX;

    CHECK(create_connector(context, "connector", &connector) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_skill_create(
              context,
              VIEW("review"),
              VIEW("Review changes"),
              INT32_C(1),
              INT32_C(0),
              &EMPTY_VIEW,
              &skill) == CODEX_AGENT_STATUS_OK);
    CHECK(create_reference(context, "detail-id", &reference) == CODEX_AGENT_STATUS_OK);
    CHECK(create_summary(context, reference, "Detail", &summary) == CODEX_AGENT_STATUS_OK);
    skills[0] = skill;
    skills[1] = skill;
    connectors[0] = connector;
    connectors[1] = connector;

    CHECK(codex_agent_plugin_detail_create(
              context,
              summary,
              VIEW("Detailed description"),
              skills,
              2u,
              connectors,
              2u,
              mcp_servers,
              3u,
              INT32_C(17),
              &detail) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_detail_create(
              context,
              summary,
              VIEW("Empty detail"),
              NULL,
              0u,
              NULL,
              0u,
              NULL,
              0u,
              INT32_C(0),
              &empty_detail) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_install_result_create(
              context,
              CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_USE,
              connectors,
              2u,
              INT32_C(1),
              VIEW("Authentication required"),
              &install) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_install_result_create(
              context,
              CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_INSTALL,
              NULL,
              0u,
              INT32_C(0),
              &EMPTY_VIEW,
              &absent) == CODEX_AGENT_STATUS_OK);

    CHECK(codex_agent_plugin_summary_destroy(context, &summary) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_reference_destroy(context, &reference) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_skill_destroy(context, &skill) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_connector_destroy(context, &connector) == CODEX_AGENT_STATUS_OK);

    CHECK_COPY(codex_agent_plugin_detail_description_copy, context, detail, "Detailed description");
    CHECK(codex_agent_plugin_detail_skills_count(context, detail, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 2u);
    CHECK(codex_agent_plugin_detail_connectors_count(context, detail, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 2u);
    CHECK(codex_agent_plugin_detail_mcp_servers_count(context, detail, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 3u);
    CHECK_COPY_AT(codex_agent_plugin_detail_mcp_servers_copy_at, context, detail, 0u, "server-a");
    CHECK_COPY_AT(codex_agent_plugin_detail_mcp_servers_copy_at, context, detail, 1u, "server-a");
    CHECK_COPY_AT(codex_agent_plugin_detail_mcp_servers_copy_at, context, detail, 2u, "server-b");
    CHECK(codex_agent_plugin_detail_hook_count(context, detail, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(17));
    CHECK(codex_agent_plugin_detail_summary(context, detail, &nested_summary) == CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_plugin_summary_display_name_copy, context, nested_summary, "Detail");
    CHECK(codex_agent_plugin_detail_skills_at(context, detail, 1u, &nested_skill) ==
          CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_plugin_skill_name_copy, context, nested_skill, "review");
    CHECK(codex_agent_plugin_detail_connectors_at(context, detail, 0u, &nested_connector_one) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_detail_connectors_at(context, detail, 0u, &nested_connector_two) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(nested_connector_one != nested_connector_two);

    CHECK(codex_agent_plugin_detail_skills_count(context, empty_detail, &count) == CODEX_AGENT_STATUS_OK);
    CHECK(count == 0u);
    CHECK(codex_agent_plugin_detail_connectors_count(context, empty_detail, &count) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(count == 0u);
    CHECK(codex_agent_plugin_detail_mcp_servers_count(context, empty_detail, &count) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(count == 0u);

    CHECK(codex_agent_plugin_install_result_auth_policy(context, install, &value) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(value == CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_USE);
    CHECK(codex_agent_plugin_install_result_connectors_count(context, install, &count) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(count == 2u);
    CHECK(codex_agent_plugin_install_result_has_message(context, install, &value) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK_COPY(
        codex_agent_plugin_install_result_message_copy,
        context,
        install,
        "Authentication required");
    CHECK(codex_agent_plugin_install_result_connectors_at(context, install, 1u, &install_connector) ==
          CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_connector_id_copy, context, install_connector, "connector");
    CHECK(codex_agent_plugin_install_result_connectors_count(context, absent, &count) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(count == 0u);
    CHECK(codex_agent_plugin_install_result_has_message(context, absent, &value) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(0));
    CHECK(codex_agent_plugin_install_result_message_copy(context, absent, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_NOT_READY);

    CHECK(codex_agent_connector_destroy(context, &install_connector) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_connector_destroy(context, &nested_connector_two) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_connector_destroy(context, &nested_connector_one) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_skill_destroy(context, &nested_skill) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_summary_destroy(context, &nested_summary) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_install_result_destroy(context, &absent) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_install_result_destroy(context, &install) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_detail_destroy(context, &empty_detail) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_detail_destroy(context, &detail) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_invalid_boundaries(
    codex_agent_context_t *context,
    codex_agent_context_t *other_context) {
    const uint8_t malformed_bytes[] = {UINT8_C(0xc3), UINT8_C(0x28)};
    const codex_agent_string_view_t malformed = {malformed_bytes, 2u};
    codex_agent_connector_t *connector = NULL;
    codex_agent_connector_t *invalid = NULL;
    codex_agent_connector_t *occupied;
    codex_agent_connector_t *stale = NULL;
    codex_agent_skill_t *skill = NULL;
    codex_agent_skill_catalog_t *catalog = NULL;
    codex_agent_plugin_install_result_t *invalid_result = NULL;
    codex_agent_connector_t *connector_values[1];
    codex_agent_context_t *stale_context = NULL;
    codex_agent_context_t *stale_context_alias;
    size_t untouched = SIZE_MAX;

    CHECK(create_connector(context, "valid", &connector) == CODEX_AGENT_STATUS_OK);
    occupied = connector;
    CHECK(codex_agent_connector_create(
              context,
              VIEW("id"),
              VIEW("name"),
              VIEW("description"),
              -INT32_C(1),
              &EMPTY_VIEW,
              INT32_C(0),
              INT32_C(1),
              NULL,
              0u,
              &invalid) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid == NULL);
    CHECK(codex_agent_connector_create(
              context,
              VIEW("id"),
              VIEW("name"),
              VIEW("description"),
              INT32_C(0),
              &EMPTY_VIEW,
              INT32_C(0),
              INT32_C(1),
              &malformed,
              1u,
              &invalid) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid == NULL);
    CHECK(codex_agent_connector_create(
              context,
              VIEW("id"),
              &malformed,
              VIEW("description"),
              INT32_C(0),
              &EMPTY_VIEW,
              INT32_C(0),
              INT32_C(1),
              NULL,
              0u,
              &invalid) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid == NULL);
    CHECK(codex_agent_connector_create(
              context,
              VIEW("id"),
              VIEW("name"),
              VIEW("description"),
              INT32_C(0),
              &EMPTY_VIEW,
              INT32_C(0),
              INT32_C(1),
              NULL,
              1u,
              &invalid) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid == NULL);
    CHECK(codex_agent_connector_create(
              context,
              VIEW("id"),
              VIEW("name"),
              VIEW("description"),
              INT32_C(0),
              &EMPTY_VIEW,
              INT32_C(0),
              INT32_C(1),
              NULL,
              0u,
              &occupied) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(occupied == connector);

    CHECK(codex_agent_skill_create(
              context,
              VIEW("skill"),
              VIEW("Skill"),
              VIEW("Description"),
              VIEW("/skill"),
              (codex_agent_skill_scope_t)INT32_C(99),
              INT32_C(1),
              INT32_C(0),
              &EMPTY_VIEW,
              NULL,
              0u,
              INT32_C(0),
              INT32_C(0),
              CODEX_AGENT_RESOURCE_ORIGIN_USER,
              &skill) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(skill == NULL);
    CHECK(codex_agent_skill_create(
              context,
              VIEW("skill"),
              VIEW("Skill"),
              VIEW("Description"),
              VIEW("/skill"),
              CODEX_AGENT_SKILL_SCOPE_USER,
              INT32_C(1),
              INT32_C(0),
              &EMPTY_VIEW,
              NULL,
              0u,
              INT32_C(0),
              INT32_C(0),
              CODEX_AGENT_RESOURCE_ORIGIN_WORKSPACE,
              &skill) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(skill == NULL);

    connector_values[0] = connector;
    CHECK(codex_agent_skill_catalog_create(
              context,
              (codex_agent_skill_t *const *)connector_values,
              1u,
              NULL,
              0u,
              &catalog) == CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(catalog == NULL);
    CHECK(codex_agent_plugin_install_result_create(
              other_context,
              CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_INSTALL,
              connector_values,
              1u,
              INT32_C(0),
              &EMPTY_VIEW,
              &invalid_result) == CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(invalid_result == NULL);

    CHECK(codex_agent_skill_catalog_skills_count(
              context,
              (codex_agent_skill_catalog_t *)connector,
              &untouched) == CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(untouched == SIZE_MAX);
    CHECK(codex_agent_connector_plugin_names_count(context, connector, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_connector_is_enabled(context, connector, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_skill_catalog_skills_at(
              context,
              (codex_agent_skill_catalog_t *)connector,
              0u,
              NULL) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);

    CHECK(codex_agent_context_create(&stale_context) == CODEX_AGENT_STATUS_OK);
    stale_context_alias = stale_context;
    CHECK(create_connector(stale_context, "stale", &stale) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_destroy(&stale_context) == CODEX_AGENT_STATUS_OK);
    CHECK(stale_context == NULL);
    CHECK(codex_agent_connector_id_copy(stale_context_alias, stale, NULL, 0u, &untouched) ==
          CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(untouched == SIZE_MAX);
    CHECK(codex_agent_connector_destroy(context, &connector) == CODEX_AGENT_STATUS_OK);
    CHECK(connector == NULL);
    CHECK(codex_agent_connector_destroy(context, &connector) == CODEX_AGENT_STATUS_OK);
    return 0;
}

int main(void) {
    codex_agent_context_t *context = NULL;
    codex_agent_context_t *other_context = NULL;

    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_create(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(context != NULL);
    CHECK(other_context != NULL);
    CHECK(verify_connector(context) == 0);
    CHECK(verify_skills(context) == 0);
    CHECK(verify_plugin_summaries(context) == 0);
    CHECK(verify_plugin_detail_and_install(context) == 0);
    CHECK(verify_invalid_boundaries(context, other_context) == 0);
    CHECK(codex_agent_context_destroy(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(context == NULL);
    return 0;
}
