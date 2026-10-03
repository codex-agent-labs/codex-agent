#include "codex_agent.h"

#include <stdio.h>

#define REJECTED(symbol, expression) do { \
  codex_agent_status_t status = (expression); \
  if (status == CODEX_AGENT_STATUS_OK) { \
    fprintf(stderr, "%s unexpectedly accepted null handles\n", #symbol); \
    return 1; \
  } \
  printf("%s\t%d\tnull-handle-rejected\n", #symbol, (int)status); \
} while (0)

int main(void) {
  REJECTED(codex_agent_authentication_authenticate_api_key,
      codex_agent_authentication_authenticate_api_key(NULL, NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_authentication_authenticate_chat_gpt_browser,
      codex_agent_authentication_authenticate_chat_gpt_browser(NULL, NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_authentication_authenticate_chat_gpt_device_code,
      codex_agent_authentication_authenticate_chat_gpt_device_code(NULL, NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_authentication_cancel,
      codex_agent_authentication_cancel(NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_authentication_is_authenticated_get,
      codex_agent_authentication_is_authenticated_get(NULL, NULL, NULL));
  REJECTED(codex_agent_authentication_is_authenticated_subscribe,
      codex_agent_authentication_is_authenticated_subscribe(NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_authentication_is_authenticating_get,
      codex_agent_authentication_is_authenticating_get(NULL, NULL, NULL));
  REJECTED(codex_agent_authentication_is_authenticating_subscribe,
      codex_agent_authentication_is_authenticating_subscribe(NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_authentication_sign_out,
      codex_agent_authentication_sign_out(NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_authentication_state_get,
      codex_agent_authentication_state_get(NULL, NULL, NULL));
  REJECTED(codex_agent_authentication_state_subscribe,
      codex_agent_authentication_state_subscribe(NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_authentication_state_value,
      codex_agent_authentication_state_value(NULL, NULL, NULL));

  REJECTED(codex_agent_connectors_is_available,
      codex_agent_connectors_is_available(NULL, NULL, NULL));
  REJECTED(codex_agent_connectors_list,
      codex_agent_connectors_list(NULL, NULL, 0, NULL, NULL, NULL));

  REJECTED(codex_agent_hooks_install,
      codex_agent_hooks_install(NULL, NULL, NULL, (codex_agent_installation_scope_t)0, NULL, NULL, NULL));
  REJECTED(codex_agent_hooks_is_available,
      codex_agent_hooks_is_available(NULL, NULL, NULL));
  REJECTED(codex_agent_hooks_list,
      codex_agent_hooks_list(NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_hooks_trust,
      codex_agent_hooks_trust(NULL, NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_hooks_uninstall,
      codex_agent_hooks_uninstall(NULL, NULL, NULL, NULL, NULL, NULL));

  REJECTED(codex_agent_integration_authorization_active_get,
      codex_agent_integration_authorization_active_get(NULL, NULL, NULL));
  REJECTED(codex_agent_integration_authorization_active_has_value,
      codex_agent_integration_authorization_active_has_value(NULL, NULL, NULL));
  REJECTED(codex_agent_integration_authorization_active_subscribe,
      codex_agent_integration_authorization_active_subscribe(NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_integration_authorization_active_value,
      codex_agent_integration_authorization_active_value(NULL, NULL, NULL));
  REJECTED(codex_agent_integration_authorization_authorize,
      codex_agent_integration_authorization_authorize(NULL, NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_integration_authorization_cancel,
      codex_agent_integration_authorization_cancel(NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_integration_authorization_is_authorizing_get,
      codex_agent_integration_authorization_is_authorizing_get(NULL, NULL, NULL));
  REJECTED(codex_agent_integration_authorization_is_authorizing_subscribe,
      codex_agent_integration_authorization_is_authorizing_subscribe(NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_integration_authorization_state_get,
      codex_agent_integration_authorization_state_get(NULL, NULL, NULL));
  REJECTED(codex_agent_integration_authorization_state_subscribe,
      codex_agent_integration_authorization_state_subscribe(NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_integration_authorization_state_value,
      codex_agent_integration_authorization_state_value(NULL, NULL, NULL));

  REJECTED(codex_agent_interactions_approvals_at,
      codex_agent_interactions_approvals_at(NULL, NULL, 0, NULL));
  REJECTED(codex_agent_interactions_approvals_count,
      codex_agent_interactions_approvals_count(NULL, NULL, NULL));
  REJECTED(codex_agent_interactions_approvals_get,
      codex_agent_interactions_approvals_get(NULL, NULL, NULL));
  REJECTED(codex_agent_interactions_approvals_subscribe,
      codex_agent_interactions_approvals_subscribe(NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_interactions_elicitations_at,
      codex_agent_interactions_elicitations_at(NULL, NULL, 0, NULL));
  REJECTED(codex_agent_interactions_elicitations_count,
      codex_agent_interactions_elicitations_count(NULL, NULL, NULL));
  REJECTED(codex_agent_interactions_elicitations_get,
      codex_agent_interactions_elicitations_get(NULL, NULL, NULL));
  REJECTED(codex_agent_interactions_elicitations_subscribe,
      codex_agent_interactions_elicitations_subscribe(NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_interactions_open_url,
      codex_agent_interactions_open_url(NULL, NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_interactions_resolve_approval,
      codex_agent_interactions_resolve_approval(NULL, NULL, NULL, (codex_agent_approval_decision_t)0, NULL, NULL, NULL));
  REJECTED(codex_agent_interactions_resolve_elicitation,
      codex_agent_interactions_resolve_elicitation(NULL, NULL, NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_interactions_state_get,
      codex_agent_interactions_state_get(NULL, NULL, NULL));
  REJECTED(codex_agent_interactions_state_subscribe,
      codex_agent_interactions_state_subscribe(NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_interactions_state_value,
      codex_agent_interactions_state_value(NULL, NULL, NULL));

  REJECTED(codex_agent_mcp_servers_add,
      codex_agent_mcp_servers_add(NULL, NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_mcp_servers_is_available,
      codex_agent_mcp_servers_is_available(NULL, NULL, NULL));
  REJECTED(codex_agent_mcp_servers_list,
      codex_agent_mcp_servers_list(NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_mcp_servers_remove,
      codex_agent_mcp_servers_remove(NULL, NULL, NULL, NULL, NULL, NULL));

  REJECTED(codex_agent_models_list,
      codex_agent_models_list(NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_models_resolve,
      codex_agent_models_resolve(NULL, NULL, (codex_agent_resolution_t)0, NULL, NULL, NULL));
  REJECTED(codex_agent_models_resolve_effort,
      codex_agent_models_resolve_effort(NULL, NULL, NULL, (codex_agent_resolution_t)0, NULL, NULL, NULL));
  REJECTED(codex_agent_models_resolve_service_tier,
      codex_agent_models_resolve_service_tier(NULL, NULL, NULL, (codex_agent_resolution_t)0, NULL, NULL, NULL));

  REJECTED(codex_agent_plugins_install,
      codex_agent_plugins_install(NULL, NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_plugins_is_available,
      codex_agent_plugins_is_available(NULL, NULL, NULL));
  REJECTED(codex_agent_plugins_list,
      codex_agent_plugins_list(NULL, NULL, 0, NULL, NULL, NULL));
  REJECTED(codex_agent_plugins_read,
      codex_agent_plugins_read(NULL, NULL, NULL, NULL, NULL, NULL));
  REJECTED(codex_agent_plugins_uninstall,
      codex_agent_plugins_uninstall(NULL, NULL, NULL, NULL, NULL, NULL));

  REJECTED(codex_agent_skills_install,
      codex_agent_skills_install(NULL, NULL, NULL, (codex_agent_installation_scope_t)0, NULL, NULL, NULL));
  REJECTED(codex_agent_skills_is_available,
      codex_agent_skills_is_available(NULL, NULL, NULL));
  REJECTED(codex_agent_skills_list,
      codex_agent_skills_list(NULL, NULL, 0, NULL, NULL, NULL));
  REJECTED(codex_agent_skills_read,
      codex_agent_skills_read(NULL, NULL, NULL, 0, NULL, NULL, NULL));
  REJECTED(codex_agent_skills_uninstall,
      codex_agent_skills_uninstall(NULL, NULL, NULL, NULL, NULL, NULL));

  return 0;
}
