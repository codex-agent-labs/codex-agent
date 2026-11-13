#include "codex_agent.h"

#include <string.h>

#define CHECK(condition)       \
    do {                       \
        if (!(condition)) {    \
            return __LINE__;   \
        }                      \
    } while (0)

#define CHECK_HANDLE_COPY(function, context, handle, expected)                     \
    do {                                                                            \
        uint8_t copied[256];                                                        \
        const char *expected_value = (expected);                                    \
        const size_t expected_size = strlen(expected_value);                        \
        size_t copy_required = 0U;                                                  \
        CHECK((function)((context), (handle), NULL, 0U, &copy_required) ==          \
              CODEX_AGENT_STATUS_BUFFER_TOO_SMALL);                                \
        CHECK(copy_required == expected_size);                                      \
        CHECK((function)((context), (handle), copied, sizeof(copied), &copy_required) == \
              CODEX_AGENT_STATUS_OK);                                               \
        CHECK(copy_required == expected_size);                                      \
        CHECK(memcmp(copied, expected_value, expected_size) == 0);                  \
    } while (0)

#define CHECK_ENUM_COPY(function, entry, expected)                                  \
    do {                                                                            \
        uint8_t copied[256];                                                        \
        const char *expected_value = (expected);                                    \
        const size_t expected_size = strlen(expected_value);                        \
        size_t required = 0U;                                                       \
        CHECK((function)((entry), NULL, 0U, &required) ==                           \
              CODEX_AGENT_STATUS_BUFFER_TOO_SMALL);                                \
        CHECK(required == expected_size);                                           \
        CHECK((function)((entry), copied, sizeof(copied), &required) ==              \
              CODEX_AGENT_STATUS_OK);                                               \
        CHECK(required == expected_size);                                           \
        CHECK(memcmp(copied, expected_value, expected_size) == 0);                  \
    } while (0)

#define STRING_VIEW(value) \
    (&(codex_agent_string_view_t){(const uint8_t *)(value), sizeof(value) - 1U})

_Static_assert(sizeof(codex_agent_capability_t) == sizeof(int32_t), "capability width");
_Static_assert(CODEX_AGENT_CAPABILITY_WEB_SEARCH == INT32_C(0), "web-search entry");
_Static_assert(sizeof(codex_agent_skill_scope_t) == sizeof(int32_t), "skill-scope width");
_Static_assert(CODEX_AGENT_SKILL_SCOPE_SYSTEM == INT32_C(0), "system scope");
_Static_assert(CODEX_AGENT_SKILL_SCOPE_USER == INT32_C(1), "user scope");
_Static_assert(CODEX_AGENT_SKILL_SCOPE_REPO == INT32_C(2), "repo scope");
_Static_assert(CODEX_AGENT_SKILL_SCOPE_PLUGIN == INT32_C(3), "plugin scope");
_Static_assert(CODEX_AGENT_SKILL_SCOPE_ADMIN == INT32_C(4), "admin scope");

static int verify_plugin_references(codex_agent_context_t *context) {
    codex_agent_plugin_reference_t *reference = NULL;
    codex_agent_plugin_reference_t *absent = NULL;
    int32_t present = INT32_C(-1);
    size_t required = 0U;
    const codex_agent_string_view_t empty = {NULL, 0U};

    CHECK(codex_agent_plugin_reference_create(
              context,
              STRING_VIEW("plugin-id"),
              STRING_VIEW("tools"),
              STRING_VIEW("official"),
              INT32_C(1),
              STRING_VIEW("/market/tools"),
              INT32_C(1),
              STRING_VIEW("remote-id"),
              &reference) == CODEX_AGENT_STATUS_OK);
    CHECK(reference != NULL);
    CHECK_HANDLE_COPY(codex_agent_plugin_reference_id_copy, context, reference, "plugin-id");
    CHECK_HANDLE_COPY(codex_agent_plugin_reference_name_copy, context, reference, "tools");
    CHECK_HANDLE_COPY(
        codex_agent_plugin_reference_marketplace_name_copy,
        context,
        reference,
        "official");
    CHECK(codex_agent_plugin_reference_has_marketplace_path(
              context, reference, &present) == CODEX_AGENT_STATUS_OK);
    CHECK(present == INT32_C(1));
    CHECK_HANDLE_COPY(
        codex_agent_plugin_reference_marketplace_path_copy,
        context,
        reference,
        "/market/tools");
    CHECK(codex_agent_plugin_reference_has_remote_plugin_id(
              context, reference, &present) == CODEX_AGENT_STATUS_OK);
    CHECK(present == INT32_C(1));
    CHECK_HANDLE_COPY(
        codex_agent_plugin_reference_remote_plugin_id_copy,
        context,
        reference,
        "remote-id");
    CHECK_HANDLE_COPY(
        codex_agent_plugin_reference_uri_copy,
        context,
        reference,
        "plugin://tools@official");

    CHECK(codex_agent_plugin_reference_create(
              context,
              STRING_VIEW("minimal-id"),
              STRING_VIEW("minimal"),
              STRING_VIEW("local"),
              INT32_C(0),
              &empty,
              INT32_C(0),
              &empty,
              &absent) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_reference_has_marketplace_path(
              context, absent, &present) == CODEX_AGENT_STATUS_OK);
    CHECK(present == INT32_C(0));
    CHECK(codex_agent_plugin_reference_marketplace_path_copy(
              context, absent, NULL, 0U, &required) == CODEX_AGENT_STATUS_NOT_READY);
    CHECK(codex_agent_plugin_reference_has_remote_plugin_id(
              context, absent, &present) == CODEX_AGENT_STATUS_OK);
    CHECK(present == INT32_C(0));
    CHECK(codex_agent_plugin_reference_remote_plugin_id_copy(
              context, absent, NULL, 0U, &required) == CODEX_AGENT_STATUS_NOT_READY);

    CHECK(codex_agent_plugin_reference_destroy(context, &absent) == CODEX_AGENT_STATUS_OK);
    CHECK(absent == NULL);
    CHECK(codex_agent_plugin_reference_destroy(context, &reference) == CODEX_AGENT_STATUS_OK);
    CHECK(reference == NULL);
    CHECK(codex_agent_plugin_reference_destroy(context, &reference) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_plugin_skills(codex_agent_context_t *context) {
    codex_agent_plugin_skill_t *skill = NULL;
    codex_agent_plugin_skill_t *absent = NULL;
    int32_t value = INT32_C(-1);
    size_t required = 0U;
    const codex_agent_string_view_t empty = {NULL, 0U};

    CHECK(codex_agent_plugin_skill_create(
              context,
              STRING_VIEW("review"),
              STRING_VIEW("Review changes"),
              INT32_C(1),
              INT32_C(1),
              STRING_VIEW("/skills/review.md"),
              &skill) == CODEX_AGENT_STATUS_OK);
    CHECK_HANDLE_COPY(codex_agent_plugin_skill_name_copy, context, skill, "review");
    CHECK_HANDLE_COPY(
        codex_agent_plugin_skill_description_copy,
        context,
        skill,
        "Review changes");
    CHECK(codex_agent_plugin_skill_is_enabled(context, skill, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK(codex_agent_plugin_skill_has_path(context, skill, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(1));
    CHECK_HANDLE_COPY(
        codex_agent_plugin_skill_path_copy,
        context,
        skill,
        "/skills/review.md");

    CHECK(codex_agent_plugin_skill_create(
              context,
              STRING_VIEW("disabled"),
              STRING_VIEW("Disabled skill"),
              INT32_C(0),
              INT32_C(0),
              &empty,
              &absent) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_skill_is_enabled(context, absent, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(0));
    CHECK(codex_agent_plugin_skill_has_path(context, absent, &value) == CODEX_AGENT_STATUS_OK);
    CHECK(value == INT32_C(0));
    CHECK(codex_agent_plugin_skill_path_copy(
              context, absent, NULL, 0U, &required) == CODEX_AGENT_STATUS_NOT_READY);

    CHECK(codex_agent_plugin_skill_destroy(context, &absent) == CODEX_AGENT_STATUS_OK);
    CHECK(absent == NULL);
    CHECK(codex_agent_plugin_skill_destroy(context, &skill) == CODEX_AGENT_STATUS_OK);
    CHECK(skill == NULL);
    return 0;
}

static int verify_service_tier(codex_agent_context_t *context) {
    codex_agent_service_tier_t *tier = NULL;
    CHECK(codex_agent_service_tier_create(
              context,
              STRING_VIEW("fast"),
              STRING_VIEW("Fast"),
              STRING_VIEW("Lower latency"),
              &tier) == CODEX_AGENT_STATUS_OK);
    CHECK_HANDLE_COPY(codex_agent_service_tier_id_copy, context, tier, "fast");
    CHECK_HANDLE_COPY(codex_agent_service_tier_name_copy, context, tier, "Fast");
    CHECK_HANDLE_COPY(
        codex_agent_service_tier_description_copy,
        context,
        tier,
        "Lower latency");
    CHECK(codex_agent_service_tier_destroy(context, &tier) == CODEX_AGENT_STATUS_OK);
    CHECK(tier == NULL);
    return 0;
}

static int verify_skill_chunks(codex_agent_context_t *context) {
    codex_agent_skill_chunk_t *chunk = NULL;
    codex_agent_skill_chunk_t *last = NULL;
    int32_t has_next_offset = INT32_C(-1);
    int64_t next_offset = INT64_C(0);
    int64_t total_bytes = INT64_C(0);
    const int64_t expected_next = -INT64_C(9223372036854775791);
    const int64_t expected_total = INT64_MAX - INT64_C(19);

    CHECK(codex_agent_skill_chunk_create(
              context,
              STRING_VIEW("chunk-content"),
              INT32_C(1),
              expected_next,
              expected_total,
              &chunk) == CODEX_AGENT_STATUS_OK);
    CHECK_HANDLE_COPY(codex_agent_skill_chunk_content_copy, context, chunk, "chunk-content");
    CHECK(codex_agent_skill_chunk_next_offset(
              context, chunk, &has_next_offset, &next_offset) == CODEX_AGENT_STATUS_OK);
    CHECK(has_next_offset == INT32_C(1));
    CHECK(next_offset == expected_next);
    CHECK(codex_agent_skill_chunk_total_bytes(
              context, chunk, &total_bytes) == CODEX_AGENT_STATUS_OK);
    CHECK(total_bytes == expected_total);

    CHECK(codex_agent_skill_chunk_create(
              context,
              STRING_VIEW("last"),
              INT32_C(0),
              INT64_C(0),
              -INT64_C(1),
              &last) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_skill_chunk_next_offset(
              context, last, &has_next_offset, &next_offset) == CODEX_AGENT_STATUS_OK);
    CHECK(has_next_offset == INT32_C(0));
    CHECK(next_offset == INT64_C(0));
    CHECK(codex_agent_skill_chunk_total_bytes(
              context, last, &total_bytes) == CODEX_AGENT_STATUS_OK);
    CHECK(total_bytes == -INT64_C(1));

    CHECK(codex_agent_skill_chunk_destroy(context, &last) == CODEX_AGENT_STATUS_OK);
    CHECK(last == NULL);
    CHECK(codex_agent_skill_chunk_destroy(context, &chunk) == CODEX_AGENT_STATUS_OK);
    CHECK(chunk == NULL);
    return 0;
}

static int verify_enums(void) {
    int32_t has_icon = INT32_C(-1);
    CHECK(CODEX_AGENT_CAPABILITY_WEB_SEARCH == INT32_C(0));
    CHECK_ENUM_COPY(
        codex_agent_capability_id_copy,
        CODEX_AGENT_CAPABILITY_WEB_SEARCH,
        "web_search");
    CHECK_ENUM_COPY(
        codex_agent_capability_display_label_copy,
        CODEX_AGENT_CAPABILITY_WEB_SEARCH,
        "Web search");
    CHECK(codex_agent_capability_has_icon(
              CODEX_AGENT_CAPABILITY_WEB_SEARCH, &has_icon) == CODEX_AGENT_STATUS_OK);
    CHECK(has_icon == INT32_C(1));
    CHECK_ENUM_COPY(
        codex_agent_capability_icon_copy,
        CODEX_AGENT_CAPABILITY_WEB_SEARCH,
        "\xF0\x9F\x8C\x90");
    CHECK_ENUM_COPY(
        codex_agent_capability_prompt_label_copy,
        CODEX_AGENT_CAPABILITY_WEB_SEARCH,
        "Use \xF0\x9F\x8C\x90 Web search");

    CHECK(CODEX_AGENT_SKILL_SCOPE_SYSTEM == INT32_C(0));
    CHECK(CODEX_AGENT_SKILL_SCOPE_USER == INT32_C(1));
    CHECK(CODEX_AGENT_SKILL_SCOPE_REPO == INT32_C(2));
    CHECK(CODEX_AGENT_SKILL_SCOPE_PLUGIN == INT32_C(3));
    CHECK(CODEX_AGENT_SKILL_SCOPE_ADMIN == INT32_C(4));
    CHECK_ENUM_COPY(
        codex_agent_skill_scope_display_name_copy,
        CODEX_AGENT_SKILL_SCOPE_SYSTEM,
        "Built in");
    CHECK_ENUM_COPY(
        codex_agent_skill_scope_display_name_copy,
        CODEX_AGENT_SKILL_SCOPE_USER,
        "User");
    CHECK_ENUM_COPY(
        codex_agent_skill_scope_display_name_copy,
        CODEX_AGENT_SKILL_SCOPE_REPO,
        "Workspace");
    CHECK_ENUM_COPY(
        codex_agent_skill_scope_display_name_copy,
        CODEX_AGENT_SKILL_SCOPE_PLUGIN,
        "Plugin");
    CHECK_ENUM_COPY(
        codex_agent_skill_scope_display_name_copy,
        CODEX_AGENT_SKILL_SCOPE_ADMIN,
        "Managed");
    return 0;
}

int main(void) {
    codex_agent_context_t *context = NULL;
    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(context != NULL);
    CHECK(verify_plugin_references(context) == 0);
    CHECK(verify_plugin_skills(context) == 0);
    CHECK(verify_service_tier(context) == 0);
    CHECK(verify_skill_chunks(context) == 0);
    CHECK(verify_enums() == 0);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(context == NULL);
    return 0;
}
