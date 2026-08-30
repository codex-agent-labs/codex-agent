#include "codex_agent.h"

#define VIEW(literal) { (const uint8_t *)(literal), sizeof(literal) - 1U }

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
