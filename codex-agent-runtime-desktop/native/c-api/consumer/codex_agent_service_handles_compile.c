#include "codex_agent.h"

#include <stdint.h>
#include <stdio.h>

#define CHECK(condition)                                                       \
    do {                                                                       \
        if (!(condition)) {                                                    \
            (void)fprintf(stderr, "check failed at line %d: %s\n",            \
                          __LINE__, #condition);                               \
            return __LINE__;                                                   \
        }                                                                      \
    } while (0)

int main(void) {
    codex_agent_authentication_t *authentication = NULL;
    codex_agent_authentication_t *authentication_alias = NULL;
    codex_agent_interactions_t *interactions = NULL;
    codex_agent_interactions_t *interactions_alias = NULL;
    codex_agent_integration_authorization_t *integration_authorization = NULL;
    codex_agent_integration_authorization_t *integration_authorization_alias = NULL;
    codex_agent_models_t *models = NULL;
    codex_agent_models_t *models_alias = NULL;
    codex_agent_skills_t *skills = NULL;
    codex_agent_skills_t *skills_alias = NULL;
    codex_agent_hooks_t *hooks = NULL;
    codex_agent_hooks_t *hooks_alias = NULL;
    codex_agent_plugins_t *plugins = NULL;
    codex_agent_plugins_t *plugins_alias = NULL;
    codex_agent_connectors_t *connectors = NULL;
    codex_agent_connectors_t *connectors_alias = NULL;
    codex_agent_mcp_servers_t *mcp_servers = NULL;
    codex_agent_mcp_servers_t *mcp_servers_alias = NULL;
    codex_agent_workspace_t *workspace = NULL;
    int32_t available = INT32_C(73);

    CHECK(codex_agent_agent_authentication(NULL, NULL, &authentication) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_agent_interactions(NULL, NULL, &interactions) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_agent_integration_authorization(
              NULL, NULL, &integration_authorization) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_agent_models(NULL, NULL, &models) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_agent_skills(NULL, NULL, &skills) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_agent_hooks(NULL, NULL, &hooks) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_agent_plugins(NULL, NULL, &plugins) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_agent_connectors(NULL, NULL, &connectors) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_agent_mcp_servers(NULL, NULL, &mcp_servers) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_agent_workspace(NULL, NULL, &workspace) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);

    CHECK(codex_agent_authentication_retain(
              NULL, authentication, &authentication_alias) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_interactions_retain(NULL, interactions, &interactions_alias) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_integration_authorization_retain(
              NULL, integration_authorization, &integration_authorization_alias) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_models_retain(NULL, models, &models_alias) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_skills_retain(NULL, skills, &skills_alias) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_hooks_retain(NULL, hooks, &hooks_alias) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_plugins_retain(NULL, plugins, &plugins_alias) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_connectors_retain(NULL, connectors, &connectors_alias) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_mcp_servers_retain(NULL, mcp_servers, &mcp_servers_alias) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);

    CHECK(codex_agent_skills_is_available(NULL, skills, &available) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(available == INT32_C(73));
    CHECK(codex_agent_hooks_is_available(NULL, hooks, &available) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(available == INT32_C(73));
    CHECK(codex_agent_plugins_is_available(NULL, plugins, &available) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(available == INT32_C(73));
    CHECK(codex_agent_connectors_is_available(NULL, connectors, &available) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(available == INT32_C(73));
    CHECK(codex_agent_mcp_servers_is_available(NULL, mcp_servers, &available) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(available == INT32_C(73));

    CHECK(codex_agent_authentication_release(NULL, &authentication) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_interactions_release(NULL, &interactions) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_authorization_release(
              NULL, &integration_authorization) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_models_release(NULL, &models) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_skills_release(NULL, &skills) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hooks_release(NULL, &hooks) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugins_release(NULL, &plugins) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_connectors_release(NULL, &connectors) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_servers_release(NULL, &mcp_servers) ==
          CODEX_AGENT_STATUS_OK);

    return 0;
}
