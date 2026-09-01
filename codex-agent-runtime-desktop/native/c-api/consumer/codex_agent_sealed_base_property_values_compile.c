#include "codex_agent.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHECK(condition) \
    do { \
        if (!(condition)) { \
            (void)fprintf(stderr, "check failed at line %d: %s\n", __LINE__, #condition); \
            return __LINE__; \
        } \
    } while (0)

#define VIEW(value) \
    (&(const codex_agent_string_view_t){(const uint8_t *)(value), sizeof(value) - 1u})

#define EMPTY_VIEW() (&(const codex_agent_string_view_t){NULL, 0u})

#define CHECK_COPY(function, context, handle, expected)                         \
    do {                                                                         \
        uint8_t copy_buffer[128] = {0};                                          \
        size_t copy_required = SIZE_MAX;                                         \
        CHECK((function)((context), (handle), NULL, 0u, &copy_required) ==       \
              CODEX_AGENT_STATUS_BUFFER_TOO_SMALL);                             \
        CHECK(copy_required == sizeof(expected) - 1u);                           \
        CHECK((function)((context), (handle), copy_buffer,                       \
                         sizeof(expected) - 2u, &copy_required) ==               \
              CODEX_AGENT_STATUS_BUFFER_TOO_SMALL);                             \
        CHECK(copy_required == sizeof(expected) - 1u);                           \
        CHECK((function)((context), (handle), copy_buffer, sizeof(copy_buffer),  \
                         &copy_required) == CODEX_AGENT_STATUS_OK);              \
        CHECK(memcmp(copy_buffer, (expected), sizeof(expected) - 1u) == 0);      \
    } while (0)

static int create_plugin_invocation(
    codex_agent_context_t *context,
    codex_agent_invocation_t **out_invocation) {
    codex_agent_invocation_plugin_t *plugin = NULL;
    CHECK(codex_agent_invocation_plugin_create(
              context, VIEW("review-plugin"), VIEW("plugin://review@official"), &plugin) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_invocation_from_plugin(context, plugin, out_invocation) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_invocation_plugin_destroy(context, &plugin) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int create_skill_invocation(
    codex_agent_context_t *context,
    codex_agent_invocation_t **out_invocation) {
    codex_agent_invocation_skill_t *skill = NULL;
    CHECK(codex_agent_invocation_skill_create(
              context, VIEW("review-skill"), VIEW("/skills/review.md"), &skill) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_invocation_from_skill(context, skill, out_invocation) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_invocation_skill_destroy(context, &skill) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int create_approval_interaction(
    codex_agent_context_t *context,
    codex_agent_pending_interaction_t **out_interaction) {
    codex_agent_conversation_id_t *conversation_id = NULL;
    codex_agent_pending_approval_t *approval = NULL;
    CHECK(codex_agent_conversation_id_create(
              context, VIEW("approval-conversation"), &conversation_id) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_pending_approval_create(
              context,
              VIEW("approval-request"),
              conversation_id,
              VIEW("Approve?"),
              VIEW("Review the request"),
              &approval) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_pending_interaction_from_approval(context, approval, out_interaction) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_pending_approval_destroy(context, &approval) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_conversation_id_destroy(context, &conversation_id) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int create_elicitation_interaction(
    codex_agent_context_t *context,
    codex_agent_pending_interaction_t **out_interaction) {
    codex_agent_conversation_id_t *conversation_id = NULL;
    codex_agent_elicitation_t *elicitation = NULL;
    codex_agent_pending_elicitation_t *pending = NULL;
    CHECK(codex_agent_conversation_id_create(
              context, VIEW("elicitation-conversation"), &conversation_id) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_elicitation_create(
              context,
              VIEW("elicitation-request"),
              VIEW("review-server"),
              conversation_id,
              VIEW("Provide review input"),
              INT32_C(0),
              NULL,
              0u,
              INT32_C(0),
              EMPTY_VIEW(),
              &elicitation) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_pending_elicitation_create(context, elicitation, &pending) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_pending_interaction_from_elicitation(context, pending, out_interaction) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_pending_elicitation_destroy(context, &pending) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_elicitation_destroy(context, &elicitation) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_conversation_id_destroy(context, &conversation_id) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int create_connector_integration(
    codex_agent_context_t *context,
    codex_agent_integration_t **out_integration) {
    codex_agent_connector_t *connector = NULL;
    codex_agent_integration_connector_t *concrete = NULL;
    CHECK(codex_agent_connector_create(
              context,
              VIEW("drive"),
              VIEW("Drive connector"),
              VIEW("Drive files"),
              INT32_C(0),
              EMPTY_VIEW(),
              INT32_C(1),
              INT32_C(1),
              NULL,
              0u,
              &connector) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_connector_create(context, connector, &concrete) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_from_connector(context, concrete, out_integration) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_connector_destroy(context, &concrete) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_connector_destroy(context, &connector) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int create_mcp_integration(
    codex_agent_context_t *context,
    codex_agent_integration_t **out_integration) {
    codex_agent_mcp_server_t *server = NULL;
    codex_agent_integration_mcp_server_t *concrete = NULL;
    CHECK(codex_agent_mcp_server_create(
              context,
              VIEW("review-mcp"),
              VIEW("Review MCP"),
              CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN,
              NULL,
              CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN,
              INT32_C(1),
              &server) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_mcp_server_create(context, server, &concrete) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_from_mcp_server(context, concrete, out_integration) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_mcp_server_destroy(context, &concrete) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_server_destroy(context, &server) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_invocations(codex_agent_context_t *context) {
    codex_agent_invocation_t *plugin = NULL;
    codex_agent_invocation_t *skill = NULL;
    codex_agent_invocation_plugin_t *plugin_child = NULL;
    codex_agent_invocation_skill_t *skill_child = NULL;
    CHECK(create_plugin_invocation(context, &plugin) == 0);
    CHECK(create_skill_invocation(context, &skill) == 0);
    CHECK_COPY(codex_agent_invocation_name_copy, context, plugin, "review-plugin");
    CHECK_COPY(
        codex_agent_invocation_key_copy,
        context,
        plugin,
        "plugin:plugin://review@official");
    CHECK_COPY(codex_agent_invocation_name_copy, context, skill, "review-skill");
    CHECK_COPY(codex_agent_invocation_key_copy, context, skill, "skill:/skills/review.md");
    CHECK(codex_agent_invocation_plugin(context, plugin, &plugin_child) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_invocation_skill(context, skill, &skill_child) == CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_invocation_plugin_name_copy, context, plugin_child, "review-plugin");
    CHECK_COPY(codex_agent_invocation_skill_name_copy, context, skill_child, "review-skill");
    CHECK(codex_agent_invocation_plugin_destroy(context, &plugin_child) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_invocation_skill_destroy(context, &skill_child) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_invocation_destroy(context, &plugin) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_invocation_destroy(context, &plugin) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_invocation_destroy(context, &skill) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_invocation_destroy(context, &skill) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_pending_interactions(codex_agent_context_t *context) {
    codex_agent_pending_interaction_t *approval = NULL;
    codex_agent_pending_interaction_t *elicitation = NULL;
    codex_agent_pending_approval_t *approval_child = NULL;
    codex_agent_pending_elicitation_t *elicitation_child = NULL;
    codex_agent_conversation_id_t *first_id = NULL;
    codex_agent_conversation_id_t *second_id = NULL;
    codex_agent_conversation_id_t *elicitation_id = NULL;
    CHECK(create_approval_interaction(context, &approval) == 0);
    CHECK(create_elicitation_interaction(context, &elicitation) == 0);
    CHECK_COPY(
        codex_agent_pending_interaction_request_id_copy,
        context,
        approval,
        "approval-request");
    CHECK_COPY(
        codex_agent_pending_interaction_request_id_copy,
        context,
        elicitation,
        "elicitation-request");
    CHECK(codex_agent_pending_interaction_conversation_id(context, approval, &first_id) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_pending_interaction_conversation_id(context, approval, &second_id) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(first_id != second_id);
    CHECK(codex_agent_pending_interaction_conversation_id(
              context, elicitation, &elicitation_id) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_pending_interaction_approval(context, approval, &approval_child) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_pending_interaction_elicitation(
              context, elicitation, &elicitation_child) == CODEX_AGENT_STATUS_OK);
    CHECK_COPY(
        codex_agent_pending_approval_request_id_copy,
        context,
        approval_child,
        "approval-request");
    CHECK_COPY(
        codex_agent_pending_elicitation_request_id_copy,
        context,
        elicitation_child,
        "elicitation-request");
    CHECK(codex_agent_pending_approval_destroy(context, &approval_child) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_pending_elicitation_destroy(context, &elicitation_child) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_pending_interaction_destroy(context, &approval) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_pending_interaction_destroy(context, &approval) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_pending_interaction_destroy(context, &elicitation) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_pending_interaction_destroy(context, &elicitation) == CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_conversation_id_value_copy, context, first_id, "approval-conversation");
    CHECK_COPY(codex_agent_conversation_id_value_copy, context, second_id, "approval-conversation");
    CHECK_COPY(
        codex_agent_conversation_id_value_copy,
        context,
        elicitation_id,
        "elicitation-conversation");
    CHECK(codex_agent_conversation_id_destroy(context, &first_id) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_conversation_id_destroy(context, &second_id) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_conversation_id_destroy(context, &elicitation_id) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_integrations(codex_agent_context_t *context) {
    codex_agent_integration_t *connector = NULL;
    codex_agent_integration_t *mcp = NULL;
    codex_agent_integration_connector_t *connector_child = NULL;
    codex_agent_integration_mcp_server_t *mcp_child = NULL;
    CHECK(create_connector_integration(context, &connector) == 0);
    CHECK(create_mcp_integration(context, &mcp) == 0);
    CHECK_COPY(codex_agent_integration_id_copy, context, connector, "drive");
    CHECK_COPY(
        codex_agent_integration_display_name_copy,
        context,
        connector,
        "Drive connector");
    CHECK_COPY(codex_agent_integration_id_copy, context, mcp, "review-mcp");
    CHECK_COPY(codex_agent_integration_display_name_copy, context, mcp, "Review MCP");
    CHECK(codex_agent_integration_connector(context, connector, &connector_child) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_mcp_server(context, mcp, &mcp_child) == CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_integration_connector_id_copy, context, connector_child, "drive");
    CHECK_COPY(codex_agent_integration_mcp_server_id_copy, context, mcp_child, "review-mcp");
    CHECK(codex_agent_integration_connector_destroy(context, &connector_child) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_mcp_server_destroy(context, &mcp_child) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_destroy(context, &connector) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_destroy(context, &connector) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_destroy(context, &mcp) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_destroy(context, &mcp) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_fail_closed(
    codex_agent_context_t *context,
    codex_agent_context_t *other_context) {
    codex_agent_invocation_t *invocation = NULL;
    codex_agent_pending_interaction_t *interaction = NULL;
    codex_agent_integration_t *integration = NULL;
    codex_agent_conversation_id_t *wrong_type = NULL;
    codex_agent_conversation_id_t *output = NULL;
    size_t required = SIZE_MAX;
    CHECK(create_plugin_invocation(context, &invocation) == 0);
    CHECK(create_approval_interaction(context, &interaction) == 0);
    CHECK(create_connector_integration(context, &integration) == 0);
    CHECK(codex_agent_conversation_id_create(context, VIEW("wrong-type"), &wrong_type) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_invocation_name_copy(context, invocation, NULL, 0u, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_invocation_name_copy(other_context, invocation, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(required == SIZE_MAX);
    CHECK(codex_agent_invocation_key_copy(
              context, (codex_agent_invocation_t *)wrong_type, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(required == SIZE_MAX);
    CHECK(codex_agent_pending_interaction_request_id_copy(
              context, (codex_agent_pending_interaction_t *)wrong_type, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(required == SIZE_MAX);
    CHECK(codex_agent_integration_id_copy(
              context, (codex_agent_integration_t *)wrong_type, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(required == SIZE_MAX);
    CHECK(codex_agent_pending_interaction_conversation_id(context, interaction, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    output = wrong_type;
    CHECK(codex_agent_pending_interaction_conversation_id(context, interaction, &output) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(output == wrong_type);
    output = NULL;
    CHECK(codex_agent_pending_interaction_conversation_id(other_context, interaction, &output) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(output == NULL);
    CHECK(codex_agent_pending_interaction_conversation_id(
              context, (codex_agent_pending_interaction_t *)wrong_type, &output) ==
          CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(output == NULL);
    {
        codex_agent_invocation_t *stale_invocation = invocation;
        codex_agent_pending_interaction_t *stale_interaction = interaction;
        codex_agent_integration_t *stale_integration = integration;
        CHECK(codex_agent_invocation_destroy(context, &invocation) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_pending_interaction_destroy(context, &interaction) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_integration_destroy(context, &integration) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_invocation_name_copy(
                  context, stale_invocation, NULL, 0u, &required) == CODEX_AGENT_STATUS_STALE_HANDLE);
        CHECK(codex_agent_pending_interaction_conversation_id(
                  context, stale_interaction, &output) == CODEX_AGENT_STATUS_STALE_HANDLE);
        CHECK(output == NULL);
        CHECK(codex_agent_integration_display_name_copy(
                  context, stale_integration, NULL, 0u, &required) ==
              CODEX_AGENT_STATUS_STALE_HANDLE);
    }
    CHECK(codex_agent_conversation_id_destroy(context, &wrong_type) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_context_reclamation(void) {
    codex_agent_context_t *context = NULL;
    codex_agent_invocation_t *plugin = NULL;
    codex_agent_invocation_t *skill = NULL;
    codex_agent_pending_interaction_t *approval = NULL;
    codex_agent_pending_interaction_t *elicitation = NULL;
    codex_agent_integration_t *connector = NULL;
    codex_agent_integration_t *mcp = NULL;
    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(create_plugin_invocation(context, &plugin) == 0);
    CHECK(create_skill_invocation(context, &skill) == 0);
    CHECK(create_approval_interaction(context, &approval) == 0);
    CHECK(create_elicitation_interaction(context, &elicitation) == 0);
    CHECK(create_connector_integration(context, &connector) == 0);
    CHECK(create_mcp_integration(context, &mcp) == 0);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(context == NULL);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    return 0;
}

int main(void) {
    codex_agent_context_t *context = NULL;
    codex_agent_context_t *other_context = NULL;
    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_create(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(verify_invocations(context) == 0);
    CHECK(verify_pending_interactions(context) == 0);
    CHECK(verify_integrations(context) == 0);
    CHECK(verify_fail_closed(context, other_context) == 0);
    CHECK(codex_agent_context_destroy(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(verify_context_reclamation() == 0);
    return 0;
}
