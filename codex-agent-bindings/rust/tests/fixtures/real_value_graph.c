#include "codex_agent.h"

#define VIEW(literal) { (const uint8_t *)(literal), sizeof(literal) - 1U }

#define CHECK_STATUS(expression) \
    do { \
        const codex_agent_status_t checked_status = (expression); \
        if (checked_status != CODEX_AGENT_STATUS_OK) return checked_status; \
    } while (0)

static codex_agent_status_t create_plugin_reference(
    codex_agent_context_t *context,
    codex_agent_plugin_reference_t **out_reference) {
    static const codex_agent_string_view_t id = VIEW("plugin-id");
    static const codex_agent_string_view_t name = VIEW("tools");
    static const codex_agent_string_view_t marketplace = VIEW("official");
    static const codex_agent_string_view_t path = VIEW("plugins/tools");
    static const codex_agent_string_view_t remote = VIEW("remote-id");
    return codex_agent_plugin_reference_create(
        context, &id, &name, &marketplace, 1, &path, 1, &remote, out_reference);
}

static codex_agent_status_t create_plugin_summary(
    codex_agent_context_t *context,
    codex_agent_plugin_summary_t **out_summary) {
    static const codex_agent_string_view_t display_name = VIEW("Tools");
    static const codex_agent_string_view_t description = VIEW("Tooling plugin");
    static const codex_agent_string_view_t capabilities[] = { VIEW("hooks"), VIEW("hooks"), VIEW("skills") };
    static const codex_agent_string_view_t brand = VIEW("#abcdef");
    static const codex_agent_string_view_t privacy = VIEW("https://example.invalid/privacy");
    static const codex_agent_string_view_t terms = VIEW("https://example.invalid/terms");
    static const codex_agent_string_view_t website = VIEW("https://example.invalid");
    codex_agent_plugin_reference_t *reference = NULL;
    codex_agent_status_t status = create_plugin_reference(context, &reference);
    if (status == CODEX_AGENT_STATUS_OK) {
        status = codex_agent_plugin_summary_create(
            context,
            reference,
            &display_name,
            &description,
            1,
            0,
            CODEX_AGENT_PLUGIN_INSTALL_POLICY_INSTALLED_BY_DEFAULT,
            CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_USE,
            1,
            capabilities,
            3U,
            1,
            &brand,
            1,
            &privacy,
            1,
            &terms,
            1,
            &website,
            out_summary);
    }
    if (reference != NULL) (void)codex_agent_plugin_reference_destroy(context, &reference);
    return status;
}

static codex_agent_status_t create_connector(
    codex_agent_context_t *context,
    codex_agent_connector_t **out_connector) {
    static const codex_agent_string_view_t id = VIEW("connector-id");
    static const codex_agent_string_view_t name = VIEW("Connector");
    static const codex_agent_string_view_t description = VIEW("Connector description");
    static const codex_agent_string_view_t install_url = VIEW("https://example.invalid/install");
    static const codex_agent_string_view_t plugins[] = { VIEW("tools"), VIEW("tools") };
    return codex_agent_connector_create(
        context, &id, &name, &description, 1, &install_url, 1, 0, plugins, 2U, out_connector);
}

static codex_agent_status_t create_plugin_skill(
    codex_agent_context_t *context,
    codex_agent_plugin_skill_t **out_skill) {
    static const codex_agent_string_view_t name = VIEW("review");
    static const codex_agent_string_view_t description = VIEW("Review changes");
    static const codex_agent_string_view_t path = VIEW("/skills/review.md");
    return codex_agent_plugin_skill_create(context, &name, &description, 1, 1, &path, out_skill);
}

static codex_agent_status_t create_plugin_catalog(
    codex_agent_context_t *context,
    codex_agent_plugin_catalog_t **out_catalog) {
    static const codex_agent_string_view_t errors[] = { VIEW("warning"), VIEW("warning") };
    codex_agent_plugin_summary_t *summary = NULL;
    codex_agent_plugin_summary_t *summaries[2];
    codex_agent_status_t status = create_plugin_summary(context, &summary);
    if (status == CODEX_AGENT_STATUS_OK) {
        summaries[0] = summary;
        summaries[1] = summary;
        status = codex_agent_plugin_catalog_create(
            context, summaries, 2U, errors, 2U, CODEX_AGENT_CATALOG_FRESHNESS_STALE_CACHE, out_catalog);
    }
    if (summary != NULL) (void)codex_agent_plugin_summary_destroy(context, &summary);
    return status;
}

static codex_agent_status_t create_plugin_detail(
    codex_agent_context_t *context,
    codex_agent_plugin_detail_t **out_detail) {
    static const codex_agent_string_view_t description = VIEW("Detailed description");
    static const codex_agent_string_view_t servers[] = { VIEW("server-a"), VIEW("server-a") };
    codex_agent_plugin_summary_t *summary = NULL;
    codex_agent_plugin_skill_t *skill = NULL;
    codex_agent_connector_t *connector = NULL;
    codex_agent_plugin_skill_t *skills[2];
    codex_agent_connector_t *connectors[2];
    codex_agent_status_t status = create_plugin_summary(context, &summary);
    if (status == CODEX_AGENT_STATUS_OK) status = create_plugin_skill(context, &skill);
    if (status == CODEX_AGENT_STATUS_OK) status = create_connector(context, &connector);
    if (status == CODEX_AGENT_STATUS_OK) {
        skills[0] = skill;
        skills[1] = skill;
        connectors[0] = connector;
        connectors[1] = connector;
        status = codex_agent_plugin_detail_create(
            context, summary, &description, skills, 2U, connectors, 2U, servers, 2U, 17, out_detail);
    }
    if (connector != NULL) (void)codex_agent_connector_destroy(context, &connector);
    if (skill != NULL) (void)codex_agent_plugin_skill_destroy(context, &skill);
    if (summary != NULL) (void)codex_agent_plugin_summary_destroy(context, &summary);
    return status;
}

static codex_agent_status_t create_plugin_install_result(
    codex_agent_context_t *context,
    codex_agent_plugin_install_result_t **out_result) {
    static const codex_agent_string_view_t message = VIEW("Authentication required");
    codex_agent_connector_t *connector = NULL;
    codex_agent_connector_t *connectors[2];
    codex_agent_status_t status = create_connector(context, &connector);
    if (status == CODEX_AGENT_STATUS_OK) {
        connectors[0] = connector;
        connectors[1] = connector;
        status = codex_agent_plugin_install_result_create(
            context, CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_USE, connectors, 2U, 1, &message, out_result);
    }
    if (connector != NULL) (void)codex_agent_connector_destroy(context, &connector);
    return status;
}

static codex_agent_status_t create_skill_catalog(
    codex_agent_context_t *context,
    codex_agent_skill_catalog_t **out_catalog) {
    static const codex_agent_string_view_t name = VIEW("review");
    static const codex_agent_string_view_t display_name = VIEW("Review");
    static const codex_agent_string_view_t description = VIEW("Review changes");
    static const codex_agent_string_view_t path = VIEW("/skills/review.md");
    static const codex_agent_string_view_t brand = VIEW("#123456");
    static const codex_agent_string_view_t dependencies[] = { VIEW("git"), VIEW("git"), VIEW("docker") };
    static const codex_agent_string_view_t errors[] = { VIEW("warning"), VIEW("warning") };
    codex_agent_skill_t *skill = NULL;
    codex_agent_skill_t *skills[2];
    codex_agent_status_t status = codex_agent_skill_create(
        context,
        &name,
        &display_name,
        &description,
        &path,
        CODEX_AGENT_SKILL_SCOPE_USER,
        1,
        1,
        &brand,
        dependencies,
        3U,
        1,
        1,
        CODEX_AGENT_RESOURCE_ORIGIN_USER,
        &skill);
    if (status == CODEX_AGENT_STATUS_OK) {
        skills[0] = skill;
        skills[1] = skill;
        status = codex_agent_skill_catalog_create(context, skills, 2U, errors, 2U, out_catalog);
    }
    if (skill != NULL) (void)codex_agent_skill_destroy(context, &skill);
    return status;
}

static codex_agent_status_t create_model(
    codex_agent_context_t *context,
    codex_agent_model_t **out_model) {
    static const codex_agent_string_view_t tier_id = VIEW("fast");
    static const codex_agent_string_view_t tier_name = VIEW("Fast");
    static const codex_agent_string_view_t tier_description = VIEW("Low latency");
    static const codex_agent_string_view_t id = VIEW("model");
    static const codex_agent_string_view_t display_name = VIEW("Model");
    static const codex_agent_string_view_t description = VIEW("Description");
    static const codex_agent_string_view_t efforts[] = { VIEW("low"), VIEW("high"), VIEW("low") };
    static const codex_agent_string_view_t default_effort = VIEW("medium");
    static const codex_agent_string_view_t default_tier = VIEW("fast");
    codex_agent_service_tier_t *tier = NULL;
    codex_agent_service_tier_t *tiers[2];
    codex_agent_status_t status = codex_agent_service_tier_create(
        context, &tier_id, &tier_name, &tier_description, &tier);
    if (status == CODEX_AGENT_STATUS_OK) {
        tiers[0] = tier;
        tiers[1] = tier;
        status = codex_agent_model_create(
            context,
            &id,
            &display_name,
            &description,
            efforts,
            3U,
            &default_effort,
            1,
            tiers,
            2U,
            1,
            &default_tier,
            out_model);
    }
    if (tier != NULL) (void)codex_agent_service_tier_destroy(context, &tier);
    return status;
}

static codex_agent_status_t create_validation(
    codex_agent_context_t *context,
    codex_agent_elicitation_validation_t **out_validation) {
    static const codex_agent_string_view_t field = VIEW("count");
    codex_agent_elicitation_validation_issue_t *issue = NULL;
    codex_agent_elicitation_validation_issue_t *issues[2];
    codex_agent_status_t status = codex_agent_elicitation_validation_issue_create(
        context, &field, CODEX_AGENT_ELICITATION_VALIDATION_NON_INTEGER, &issue);
    if (status == CODEX_AGENT_STATUS_OK) {
        issues[0] = issue;
        issues[1] = issue;
        status = codex_agent_elicitation_validation_create(context, issues, 2U, out_validation);
    }
    if (issue != NULL) (void)codex_agent_elicitation_validation_issue_destroy(context, &issue);
    return status;
}

static codex_agent_status_t create_turn_progress(
    codex_agent_context_t *context,
    codex_agent_turn_progress_t **out_progress) {
    static const codex_agent_string_view_t step_text = VIEW("first");
    static const codex_agent_string_view_t explanation = VIEW("because");
    static const codex_agent_string_view_t hook_id = VIEW("hook");
    static const codex_agent_string_view_t event_name = VIEW("event");
    static const codex_agent_string_view_t handler_type = VIEW("command");
    static const codex_agent_string_view_t status_message = VIEW("blocked");
    static const codex_agent_string_view_t details[] = { VIEW("detail"), VIEW("detail") };
    static const codex_agent_string_view_t text = VIEW("text");
    static const codex_agent_string_view_t commentary = VIEW("commentary");
    static const codex_agent_string_view_t reasoning = VIEW("reasoning");
    static const codex_agent_string_view_t plan = VIEW("plan");
    static const codex_agent_string_view_t shell = VIEW("shell");
    codex_agent_plan_step_t *step = NULL;
    codex_agent_plan_step_t *steps[2];
    codex_agent_plan_progress_t *plan_progress = NULL;
    codex_agent_hook_activity_t *hook = NULL;
    codex_agent_hook_activity_t *hooks[2];
    codex_agent_status_t status = codex_agent_plan_step_create(
        context, &step_text, CODEX_AGENT_PLAN_STEP_COMPLETED, &step);
    if (status == CODEX_AGENT_STATUS_OK) {
        steps[0] = step;
        steps[1] = step;
        status = codex_agent_plan_progress_create(context, 1, &explanation, steps, 2U, &plan_progress);
    }
    if (status == CODEX_AGENT_STATUS_OK) {
        status = codex_agent_hook_activity_create(
            context,
            &hook_id,
            &event_name,
            &handler_type,
            CODEX_AGENT_HOOK_RUN_STATUS_BLOCKED,
            1,
            &status_message,
            details,
            2U,
            &hook);
    }
    if (status == CODEX_AGENT_STATUS_OK) {
        hooks[0] = hook;
        hooks[1] = hook;
        status = codex_agent_turn_progress_create(
            context,
            &text,
            &commentary,
            &reasoning,
            &plan,
            1,
            plan_progress,
            &shell,
            1,
            -7,
            1,
            CODEX_AGENT_WORK_ACTIVITY_WRITING_FILES,
            hooks,
            2U,
            1,
            out_progress);
    }
    if (hook != NULL) (void)codex_agent_hook_activity_destroy(context, &hook);
    if (plan_progress != NULL) (void)codex_agent_plan_progress_destroy(context, &plan_progress);
    if (step != NULL) (void)codex_agent_plan_step_destroy(context, &step);
    return status;
}

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_test_ordinary_value_fixture(
    codex_agent_context_t *context,
    int32_t kind,
    void **out_value) {
    static const codex_agent_string_view_t one = VIEW("one");
    static const codex_agent_string_view_t two = VIEW("two");
    static const codex_agent_string_view_t three = VIEW("three");
    static const codex_agent_string_view_t service = VIEW("fast");
    if (context == NULL || out_value == NULL) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_value = NULL;
    switch (kind) {
        case 0: {
            codex_agent_client_info_value_t *value = NULL;
            CHECK_STATUS(codex_agent_client_info_value_create(context, &one, &two, &three, &value));
            *out_value = value;
            return CODEX_AGENT_STATUS_OK;
        }
        case 1: {
            codex_agent_failure_t *value = NULL;
            CHECK_STATUS(codex_agent_failure_create(context, &one, &two, 1, &value));
            *out_value = value;
            return CODEX_AGENT_STATUS_OK;
        }
        case 2: {
            codex_agent_workspace_t *value = NULL;
            CHECK_STATUS(codex_agent_workspace_create(context, &one, 1, &two, &value));
            *out_value = value;
            return CODEX_AGENT_STATUS_OK;
        }
        case 3: {
            codex_agent_conversation_settings_t *value = NULL;
            CHECK_STATUS(codex_agent_conversation_settings_create(
                context, CODEX_AGENT_APPROVAL_PRESET_STRICT, 1, &service, &value));
            *out_value = value;
            return CODEX_AGENT_STATUS_OK;
        }
        case 4: {
            codex_agent_conversation_id_t *id = NULL;
            codex_agent_conversation_summary_t *value = NULL;
            codex_agent_status_t status = codex_agent_conversation_id_create(context, &one, &id);
            if (status == CODEX_AGENT_STATUS_OK)
                status = codex_agent_conversation_summary_create(context, id, &two, INT64_C(42), &value);
            if (id != NULL) (void)codex_agent_conversation_id_destroy(context, &id);
            if (status != CODEX_AGENT_STATUS_OK) return status;
            *out_value = value;
            return CODEX_AGENT_STATUS_OK;
        }
        case 5: {
            codex_agent_elicitation_validation_t *value = NULL;
            CHECK_STATUS(create_validation(context, &value));
            *out_value = value;
            return CODEX_AGENT_STATUS_OK;
        }
        case 6: {
            codex_agent_form_option_t *value = NULL;
            CHECK_STATUS(codex_agent_form_option_create(context, &one, 1, &two, 1, &three, &value));
            *out_value = value;
            return CODEX_AGENT_STATUS_OK;
        }
        case 7: {
            codex_agent_model_t *value = NULL;
            CHECK_STATUS(create_model(context, &value));
            *out_value = value;
            return CODEX_AGENT_STATUS_OK;
        }
        case 8: {
            codex_agent_plugin_catalog_t *value = NULL;
            CHECK_STATUS(create_plugin_catalog(context, &value));
            *out_value = value;
            return CODEX_AGENT_STATUS_OK;
        }
        case 9: {
            codex_agent_plugin_detail_t *value = NULL;
            CHECK_STATUS(create_plugin_detail(context, &value));
            *out_value = value;
            return CODEX_AGENT_STATUS_OK;
        }
        case 10: {
            codex_agent_plugin_install_result_t *value = NULL;
            CHECK_STATUS(create_plugin_install_result(context, &value));
            *out_value = value;
            return CODEX_AGENT_STATUS_OK;
        }
        case 11: {
            codex_agent_skill_catalog_t *value = NULL;
            CHECK_STATUS(create_skill_catalog(context, &value));
            *out_value = value;
            return CODEX_AGENT_STATUS_OK;
        }
        case 12: {
            codex_agent_skill_chunk_t *value = NULL;
            CHECK_STATUS(codex_agent_skill_chunk_create(context, &one, 1, INT64_C(9), INT64_C(12), &value));
            *out_value = value;
            return CODEX_AGENT_STATUS_OK;
        }
        case 13: {
            codex_agent_turn_progress_t *value = NULL;
            CHECK_STATUS(create_turn_progress(context, &value));
            *out_value = value;
            return CODEX_AGENT_STATUS_OK;
        }
        default:
            return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
}

CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_test_mcp_server_fixture(
    codex_agent_context_t *context,
    int32_t variant,
    int32_t *out_stage,
    codex_agent_mcp_server_t **out_server) {
    static const codex_agent_string_view_t empty = VIEW("");
    static const codex_agent_string_view_t absent = { NULL, 0U };
    static const codex_agent_string_view_t http_url = VIEW("https://example.com/mcp");
    static const codex_agent_string_view_t loopback_url = VIEW("http://127.0.0.1:7777/mcp");
    static const codex_agent_string_view_t bearer = VIEW("TOKEN_ENV");
    static const codex_agent_string_view_t helper = VIEW("/usr/bin/headers-helper");
    static const codex_agent_string_view_t header_keys[] = { VIEW("X-A"), VIEW("X-B") };
    static const codex_agent_string_view_t header_values[] = { VIEW("one"), VIEW("two") };
    static const codex_agent_string_view_t environment_header_keys[] = { VIEW("Authorization") };
    static const codex_agent_string_view_t environment_header_values[] = { VIEW("AUTH_HEADER") };
    static const codex_agent_string_view_t command = VIEW("node");
    static const codex_agent_string_view_t arguments[] = { VIEW("server.js"), VIEW("--flag"), VIEW("--flag") };
    static const codex_agent_string_view_t working_directory = VIEW("/workspace");
    static const codex_agent_string_view_t environment_keys[] = { VIEW("A"), VIEW("B") };
    static const codex_agent_string_view_t environment_values[] = { VIEW("1"), VIEW("2") };
    static const codex_agent_string_view_t forwarded_name = VIEW("REMOTE_TOKEN");
    static const codex_agent_string_view_t oauth_client = VIEW("");
    static const codex_agent_string_view_t server_name = VIEW("server_1");
    static const codex_agent_string_view_t display_name = VIEW("Server One");
    static const codex_agent_string_view_t environment_id = VIEW("local");
    static const codex_agent_mcp_tool_exposure_surface_t omitted[] = {
        CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_CODE_MODE,
        CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_DIRECT,
    };
    static const codex_agent_string_view_t enabled_tools[] = { VIEW("one"), VIEW("one") };
    static const codex_agent_string_view_t scopes[] = { VIEW("scope-a"), VIEW("scope-a") };
    static const codex_agent_string_view_t tool_keys[] = { VIEW("tool") };

    codex_agent_status_t status = CODEX_AGENT_STATUS_OK;
    codex_agent_mcp_environment_variable_t *forwarded = NULL;
    codex_agent_mcp_transport_http_t *http = NULL;
    codex_agent_mcp_transport_stdio_t *stdio = NULL;
    codex_agent_mcp_transport_t *transport = NULL;
    codex_agent_mcp_oauth_configuration_t *oauth = NULL;
    codex_agent_mcp_tool_configuration_t *tool = NULL;
    codex_agent_mcp_server_configuration_t *configuration = NULL;
    codex_agent_mcp_environment_variable_t *forwarded_values[1];
    codex_agent_mcp_tool_configuration_t *tool_values[1];

    if (context == NULL || out_stage == NULL || out_server == NULL || variant < 0 || variant > 2)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_stage = 0;
    *out_server = NULL;

    if (variant == 1) {
        *out_stage = 1;
        status = codex_agent_mcp_environment_variable_create(
            context, &forwarded_name, 1, CODEX_AGENT_MCP_ENVIRONMENT_SOURCE_REMOTE, &forwarded);
        if (status != CODEX_AGENT_STATUS_OK) goto cleanup;
        forwarded_values[0] = forwarded;
        *out_stage = 2;
        status = codex_agent_mcp_transport_stdio_create(
            context,
            &command,
            arguments,
            3U,
            1,
            &working_directory,
            1,
            environment_keys,
            environment_values,
            2U,
            forwarded_values,
            1U,
            &stdio);
        if (status != CODEX_AGENT_STATUS_OK) goto cleanup;
        *out_stage = 3;
        status = codex_agent_mcp_transport_from_stdio(context, stdio, &transport);
    } else {
        const int32_t rich = variant == 0;
        *out_stage = 4;
        status = codex_agent_mcp_transport_http_create(
            context,
            rich ? &http_url : &loopback_url,
            rich,
            rich ? &bearer : &absent,
            rich,
            rich ? header_keys : NULL,
            rich ? header_values : NULL,
            rich ? 2U : 0U,
            rich,
            rich ? environment_header_keys : NULL,
            rich ? environment_header_values : NULL,
            rich ? 1U : 0U,
            rich,
            rich ? &helper : &absent,
            &http);
        if (status != CODEX_AGENT_STATUS_OK) goto cleanup;
        *out_stage = 5;
        status = codex_agent_mcp_transport_from_http(context, http, &transport);
    }
    if (status != CODEX_AGENT_STATUS_OK) goto cleanup;

    if (variant == 0) {
        *out_stage = 6;
        status = codex_agent_mcp_oauth_configuration_create(context, 1, &oauth_client, 1, 65535, &oauth);
        if (status != CODEX_AGENT_STATUS_OK) goto cleanup;
        *out_stage = 7;
        status = codex_agent_mcp_tool_configuration_create(
            context, 1, CODEX_AGENT_MCP_TOOL_APPROVAL_PROMPT, &tool);
        if (status != CODEX_AGENT_STATUS_OK) goto cleanup;
        tool_values[0] = tool;
    }

    *out_stage = 8;
    status = codex_agent_mcp_server_configuration_create(
        context,
        &server_name,
        transport,
        variant == 0,
        CODEX_AGENT_MCP_AUTHENTICATION_OAUTH,
        &environment_id,
        variant != 1,
        variant == 1,
        variant == 0,
        variant != 1,
        variant == 0 ? omitted : NULL,
        variant == 0 ? 2U : 0U,
        variant == 0,
        variant == 0 ? 1.5 : 0.0,
        variant == 0,
        variant == 0 ? 2.5 : 0.0,
        variant == 0,
        variant == 0 ? CODEX_AGENT_MCP_TOOL_APPROVAL_WRITES : 0,
        variant != 1,
        variant == 0 ? enabled_tools : NULL,
        variant == 0 ? 2U : 0U,
        variant != 1,
        NULL,
        0U,
        variant != 1,
        variant == 0 ? scopes : NULL,
        variant == 0 ? 2U : 0U,
        variant == 0,
        oauth,
        variant == 0,
        variant == 0 ? &empty : &absent,
        variant == 0 ? tool_keys : NULL,
        variant == 0 ? tool_values : NULL,
        variant == 0 ? 1U : 0U,
        &configuration);
    if (status != CODEX_AGENT_STATUS_OK) goto cleanup;

    *out_stage = 9;
    status = codex_agent_mcp_server_create(
        context,
        &server_name,
        &display_name,
        variant == 0 ? CODEX_AGENT_MCP_AUTH_STATUS_OAUTH : CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN,
        configuration,
        variant == 0 ? CODEX_AGENT_RESOURCE_ORIGIN_PLUGIN : CODEX_AGENT_RESOURCE_ORIGIN_USER,
        variant == 0,
        out_server);

cleanup:
    if (configuration != NULL) (void)codex_agent_mcp_server_configuration_destroy(context, &configuration);
    if (tool != NULL) (void)codex_agent_mcp_tool_configuration_destroy(context, &tool);
    if (oauth != NULL) (void)codex_agent_mcp_oauth_configuration_destroy(context, &oauth);
    if (transport != NULL) (void)codex_agent_mcp_transport_destroy(context, &transport);
    if (stdio != NULL) (void)codex_agent_mcp_transport_stdio_destroy(context, &stdio);
    if (http != NULL) (void)codex_agent_mcp_transport_http_destroy(context, &http);
    if (forwarded != NULL) (void)codex_agent_mcp_environment_variable_destroy(context, &forwarded);
    if (status == CODEX_AGENT_STATUS_OK) *out_stage = 10;
    return status;
}
