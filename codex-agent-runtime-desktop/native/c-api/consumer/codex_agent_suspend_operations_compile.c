#include "codex_agent.h"

#include <stdint.h>

#define CHECK_INVALID(call)                                                    \
    do {                                                                       \
        if ((call) != CODEX_AGENT_STATUS_INVALID_ARGUMENT) {                  \
            return __LINE__;                                                   \
        }                                                                      \
    } while (0)

static void CODEX_AGENT_CALL operation_callback(
    codex_agent_context_t *context,
    codex_agent_operation_t *operation,
    void *user_data) {
    (void)context;
    (void)operation;
    (void)user_data;
}

int main(void) {
    static const uint8_t bytes[] = {'x'};
    const codex_agent_string_view_t string = {bytes, sizeof(bytes)};
    codex_agent_context_t *context = NULL;
    codex_agent_host_t *host = NULL;
    codex_agent_authentication_t *authentication = NULL;
    codex_agent_authentication_method_api_key_t *api_key = NULL;
    codex_agent_authentication_method_chat_gpt_browser_t *browser = NULL;
    codex_agent_authentication_method_chat_gpt_device_code_t *device_code = NULL;
    codex_agent_integration_authorization_t *authorization = NULL;
    codex_agent_integration_t *integration = NULL;
    codex_agent_models_t *models = NULL;
    codex_agent_model_t *model = NULL;
    codex_agent_skills_t *skills = NULL;
    codex_agent_skill_t *skill = NULL;
    codex_agent_hooks_t *hooks = NULL;
    codex_agent_hook_t *hook = NULL;
    codex_agent_plugins_t *plugins = NULL;
    codex_agent_plugin_reference_t *plugin = NULL;
    codex_agent_connectors_t *connectors = NULL;
    codex_agent_mcp_servers_t *mcp_servers = NULL;
    codex_agent_mcp_server_configuration_t *configuration = NULL;
    codex_agent_mcp_server_t *mcp_server = NULL;
    codex_agent_conversations_t *conversations = NULL;
    codex_agent_conversation_id_t *conversation_id = NULL;
    codex_agent_conversation_t *conversation = NULL;
    codex_agent_turn_request_t *request = NULL;
    codex_agent_operation_t *operation = NULL;
    int32_t user_data = INT32_C(0);

    CHECK_INVALID(codex_agent_host_start(
        context, host, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_authentication_authenticate_api_key(
        context, authentication, api_key, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_authentication_authenticate_chat_gpt_browser(
        context, authentication, browser, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_authentication_authenticate_chat_gpt_device_code(
        context, authentication, device_code, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_authentication_cancel(
        context, authentication, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_authentication_sign_out(
        context, authentication, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_integration_authorization_authorize(
        context, authorization, integration, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_integration_authorization_cancel(
        context, authorization, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_models_list(
        context, models, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_models_resolve(
        context, models, CODEX_AGENT_RESOLUTION_DEFAULT,
        operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_models_resolve_effort(
        context, models, model, CODEX_AGENT_RESOLUTION_DEFAULT,
        operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_models_resolve_service_tier(
        context, models, model, CODEX_AGENT_RESOLUTION_DEFAULT,
        operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_skills_list(
        context, skills, INT32_C(0), operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_skills_read(
        context, skills, &string, INT64_C(0), operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_skills_install(
        context, skills, &string, CODEX_AGENT_INSTALLATION_SCOPE_USER,
        operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_skills_uninstall(
        context, skills, skill, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_hooks_list(
        context, hooks, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_hooks_install(
        context, hooks, &string, CODEX_AGENT_INSTALLATION_SCOPE_USER,
        operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_hooks_uninstall(
        context, hooks, hook, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_hooks_trust(
        context, hooks, hook, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_plugins_list(
        context, plugins, INT32_C(0), operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_plugins_read(
        context, plugins, plugin, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_plugins_install(
        context, plugins, plugin, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_plugins_uninstall(
        context, plugins, plugin, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_connectors_list(
        context, connectors, INT32_C(0), operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_mcp_servers_list(
        context, mcp_servers, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_mcp_servers_add(
        context, mcp_servers, configuration, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_mcp_servers_remove(
        context, mcp_servers, mcp_server, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_conversations_list(
        context, conversations, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_conversations_read(
        context, conversations, conversation_id, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_conversations_rename(
        context, conversations, conversation_id, &string,
        operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_conversations_delete(
        context, conversations, conversation_id, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_conversation_send_request(
        context, conversation, request, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_conversation_run_shell_command(
        context, conversation, &string, operation_callback, &user_data, &operation));
    CHECK_INVALID(codex_agent_conversation_reload(
        context, conversation, operation_callback, &user_data, &operation));

    {
        size_t count = SIZE_MAX;
        size_t required = SIZE_MAX;
        int32_t has_value = -1;
        uint8_t buffer[1] = {0};
        codex_agent_conversation_summary_t *summary = NULL;
        codex_agent_conversation_value_t *conversation_value = NULL;
        codex_agent_model_t *model_value = NULL;
        codex_agent_service_tier_t *service_tier = NULL;
        codex_agent_skill_catalog_t *skill_catalog = NULL;
        codex_agent_skill_chunk_t *skill_chunk = NULL;
        codex_agent_skill_t *skill_value = NULL;
        codex_agent_hook_catalog_t *hook_catalog = NULL;
        codex_agent_hook_t *hook_value = NULL;
        codex_agent_plugin_catalog_t *plugin_catalog = NULL;
        codex_agent_plugin_detail_t *plugin_detail = NULL;
        codex_agent_plugin_install_result_t *plugin_install_result = NULL;
        codex_agent_connector_t *connector = NULL;
        codex_agent_mcp_server_t *mcp_server_value = NULL;

        CHECK_INVALID(codex_agent_operation_conversation_summaries_count(
            context, operation, &count));
        CHECK_INVALID(codex_agent_operation_conversation_summary_at(
            context, operation, 0u, &summary));
        CHECK_INVALID(codex_agent_operation_conversation_value(
            context, operation, &conversation_value));
        CHECK_INVALID(codex_agent_operation_models_count(context, operation, &count));
        CHECK_INVALID(codex_agent_operation_model_at(context, operation, 0u, &model_value));
        CHECK_INVALID(codex_agent_operation_model(context, operation, &model_value));
        CHECK_INVALID(codex_agent_operation_string_copy(
            context, operation, buffer, sizeof(buffer), &required));
        CHECK_INVALID(codex_agent_operation_has_service_tier(
            context, operation, &has_value));
        CHECK_INVALID(codex_agent_operation_service_tier(
            context, operation, &service_tier));
        CHECK_INVALID(codex_agent_operation_skill_catalog(
            context, operation, &skill_catalog));
        CHECK_INVALID(codex_agent_operation_skill_chunk(
            context, operation, &skill_chunk));
        CHECK_INVALID(codex_agent_operation_skill(context, operation, &skill_value));
        CHECK_INVALID(codex_agent_operation_hook_catalog(
            context, operation, &hook_catalog));
        CHECK_INVALID(codex_agent_operation_hook(context, operation, &hook_value));
        CHECK_INVALID(codex_agent_operation_plugin_catalog(
            context, operation, &plugin_catalog));
        CHECK_INVALID(codex_agent_operation_plugin_detail(
            context, operation, &plugin_detail));
        CHECK_INVALID(codex_agent_operation_plugin_install_result(
            context, operation, &plugin_install_result));
        CHECK_INVALID(codex_agent_operation_connectors_count(context, operation, &count));
        CHECK_INVALID(codex_agent_operation_connector_at(
            context, operation, 0u, &connector));
        CHECK_INVALID(codex_agent_operation_mcp_servers_count(context, operation, &count));
        CHECK_INVALID(codex_agent_operation_mcp_server_at(
            context, operation, 0u, &mcp_server_value));
        CHECK_INVALID(codex_agent_operation_mcp_server(
            context, operation, &mcp_server_value));
    }

    return 0;
}
