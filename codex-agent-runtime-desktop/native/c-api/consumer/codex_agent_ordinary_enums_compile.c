#include "codex_agent.h"

#define CHECK(condition)       \
    do {                       \
        if (!(condition)) {    \
            return __LINE__;   \
        }                      \
    } while (0)

#define CHECK_INVALID_VALUES(function, count)                                      \
    do {                                                                            \
        CHECK(function(INT32_MIN) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);          \
        CHECK(function(-INT32_C(1)) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);        \
        CHECK(function(INT32_C(count)) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);     \
        CHECK(function(INT32_MAX) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);          \
    } while (0)

_Static_assert(CODEX_AGENT_APPROVAL_DECISION_ACCEPT == INT32_C(0), "approval accept");
_Static_assert(CODEX_AGENT_APPROVAL_DECISION_DECLINE == INT32_C(1), "approval decline");

_Static_assert(CODEX_AGENT_AUTHENTICATION_STATUS_SIGNED_OUT == INT32_C(0), "signed out");
_Static_assert(CODEX_AGENT_AUTHENTICATION_STATUS_AUTHENTICATING == INT32_C(1), "authenticating");
_Static_assert(CODEX_AGENT_AUTHENTICATION_STATUS_AUTHENTICATED == INT32_C(2), "authenticated");

_Static_assert(CODEX_AGENT_CATALOG_FRESHNESS_LIVE == INT32_C(0), "catalog live");
_Static_assert(CODEX_AGENT_CATALOG_FRESHNESS_FRESH_CACHE == INT32_C(1), "catalog fresh cache");
_Static_assert(CODEX_AGENT_CATALOG_FRESHNESS_STALE_CACHE == INT32_C(2), "catalog stale cache");

_Static_assert(CODEX_AGENT_COLLABORATION_MODE_DEFAULT == INT32_C(0), "collaboration default");
_Static_assert(CODEX_AGENT_COLLABORATION_MODE_PLAN == INT32_C(1), "collaboration plan");

_Static_assert(CODEX_AGENT_ELICITATION_ACTION_ACCEPT == INT32_C(0), "elicitation accept");
_Static_assert(CODEX_AGENT_ELICITATION_ACTION_DECLINE == INT32_C(1), "elicitation decline");
_Static_assert(CODEX_AGENT_ELICITATION_ACTION_CANCEL == INT32_C(2), "elicitation cancel");

_Static_assert(CODEX_AGENT_FORM_FIELD_TYPE_STRING == INT32_C(0), "form string");
_Static_assert(CODEX_AGENT_FORM_FIELD_TYPE_NUMBER == INT32_C(1), "form number");
_Static_assert(CODEX_AGENT_FORM_FIELD_TYPE_INTEGER == INT32_C(2), "form integer");
_Static_assert(CODEX_AGENT_FORM_FIELD_TYPE_BOOLEAN == INT32_C(3), "form boolean");
_Static_assert(CODEX_AGENT_FORM_FIELD_TYPE_SINGLE_SELECT == INT32_C(4), "form single select");
_Static_assert(CODEX_AGENT_FORM_FIELD_TYPE_MULTI_SELECT == INT32_C(5), "form multi select");

_Static_assert(CODEX_AGENT_FORM_STRING_FORMAT_EMAIL == INT32_C(0), "format email");
_Static_assert(CODEX_AGENT_FORM_STRING_FORMAT_URI == INT32_C(1), "format uri");
_Static_assert(CODEX_AGENT_FORM_STRING_FORMAT_DATE == INT32_C(2), "format date");
_Static_assert(CODEX_AGENT_FORM_STRING_FORMAT_DATE_TIME == INT32_C(3), "format date time");

_Static_assert(CODEX_AGENT_HOOK_RUN_STATUS_RUNNING == INT32_C(0), "hook running");
_Static_assert(CODEX_AGENT_HOOK_RUN_STATUS_COMPLETED == INT32_C(1), "hook completed");
_Static_assert(CODEX_AGENT_HOOK_RUN_STATUS_FAILED == INT32_C(2), "hook failed");
_Static_assert(CODEX_AGENT_HOOK_RUN_STATUS_BLOCKED == INT32_C(3), "hook blocked");
_Static_assert(CODEX_AGENT_HOOK_RUN_STATUS_STOPPED == INT32_C(4), "hook stopped");

_Static_assert(CODEX_AGENT_HOOK_TRUST_STATUS_MANAGED == INT32_C(0), "hook managed");
_Static_assert(CODEX_AGENT_HOOK_TRUST_STATUS_UNTRUSTED == INT32_C(1), "hook untrusted");
_Static_assert(CODEX_AGENT_HOOK_TRUST_STATUS_TRUSTED == INT32_C(2), "hook trusted");
_Static_assert(CODEX_AGENT_HOOK_TRUST_STATUS_MODIFIED == INT32_C(3), "hook modified");

_Static_assert(CODEX_AGENT_INSTALLATION_SCOPE_USER == INT32_C(0), "installation user");
_Static_assert(CODEX_AGENT_INSTALLATION_SCOPE_WORKSPACE == INT32_C(1), "installation workspace");

_Static_assert(CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_IDLE == INT32_C(0), "authorization idle");
_Static_assert(CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_STARTING == INT32_C(1), "authorization starting");
_Static_assert(
    CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_AWAITING_COMPLETION == INT32_C(2),
    "authorization awaiting completion");
_Static_assert(CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_AUTHORIZED == INT32_C(3), "authorized");
_Static_assert(CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_FAILED == INT32_C(4), "authorization failed");

_Static_assert(CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN == INT32_C(0), "mcp auth unknown");
_Static_assert(CODEX_AGENT_MCP_AUTH_STATUS_UNSUPPORTED == INT32_C(1), "mcp auth unsupported");
_Static_assert(CODEX_AGENT_MCP_AUTH_STATUS_NOT_LOGGED_IN == INT32_C(2), "mcp auth not logged in");
_Static_assert(CODEX_AGENT_MCP_AUTH_STATUS_BEARER_TOKEN == INT32_C(3), "mcp bearer token");
_Static_assert(CODEX_AGENT_MCP_AUTH_STATUS_OAUTH == INT32_C(4), "mcp oauth");

_Static_assert(CODEX_AGENT_MCP_AUTHENTICATION_OAUTH == INT32_C(0), "authentication oauth");
_Static_assert(CODEX_AGENT_MCP_AUTHENTICATION_CHAT_GPT == INT32_C(1), "authentication chat gpt");

_Static_assert(CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_CODE_MODE == INT32_C(0), "exposure code mode");
_Static_assert(CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_DEFERRED == INT32_C(1), "exposure deferred");
_Static_assert(CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_DIRECT == INT32_C(2), "exposure direct");

_Static_assert(CODEX_AGENT_MESSAGE_ROLE_USER == INT32_C(0), "message user");
_Static_assert(CODEX_AGENT_MESSAGE_ROLE_ASSISTANT == INT32_C(1), "message assistant");

_Static_assert(CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_INSTALL == INT32_C(0), "auth on install");
_Static_assert(CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_USE == INT32_C(1), "auth on use");

_Static_assert(CODEX_AGENT_PLUGIN_INSTALL_POLICY_NOT_AVAILABLE == INT32_C(0), "plugin unavailable");
_Static_assert(CODEX_AGENT_PLUGIN_INSTALL_POLICY_AVAILABLE == INT32_C(1), "plugin available");
_Static_assert(
    CODEX_AGENT_PLUGIN_INSTALL_POLICY_INSTALLED_BY_DEFAULT == INT32_C(2),
    "plugin installed by default");

_Static_assert(CODEX_AGENT_RESOLUTION_PREFERRED == INT32_C(0), "resolution preferred");
_Static_assert(CODEX_AGENT_RESOLUTION_DEFAULT == INT32_C(1), "resolution default");
_Static_assert(CODEX_AGENT_RESOLUTION_FIRST == INT32_C(2), "resolution first");

_Static_assert(CODEX_AGENT_RESOURCE_ORIGIN_USER == INT32_C(0), "origin user");
_Static_assert(CODEX_AGENT_RESOURCE_ORIGIN_WORKSPACE == INT32_C(1), "origin workspace");
_Static_assert(CODEX_AGENT_RESOURCE_ORIGIN_PLUGIN == INT32_C(2), "origin plugin");
_Static_assert(CODEX_AGENT_RESOURCE_ORIGIN_MANAGED == INT32_C(3), "origin managed");
_Static_assert(CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN == INT32_C(4), "origin unknown");

_Static_assert(CODEX_AGENT_WORK_ACTIVITY_RUNNING_COMMAND == INT32_C(0), "work running command");
_Static_assert(CODEX_AGENT_WORK_ACTIVITY_WRITING_FILES == INT32_C(1), "work writing files");

_Static_assert(CODEX_AGENT_AUTHORIZATION_PURPOSE_CHAT_GPT == INT32_C(0), "purpose chat gpt");
_Static_assert(CODEX_AGENT_AUTHORIZATION_PURPOSE_EXTERNAL == INT32_C(1), "purpose external");

int main(void) {
    CHECK(codex_agent_approval_decision_validate(CODEX_AGENT_APPROVAL_DECISION_ACCEPT) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_approval_decision_validate(CODEX_AGENT_APPROVAL_DECISION_DECLINE) == CODEX_AGENT_STATUS_OK);
    CHECK_INVALID_VALUES(codex_agent_approval_decision_validate, 2);

    CHECK(codex_agent_authentication_status_validate(CODEX_AGENT_AUTHENTICATION_STATUS_SIGNED_OUT) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_authentication_status_validate(CODEX_AGENT_AUTHENTICATION_STATUS_AUTHENTICATING) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_authentication_status_validate(CODEX_AGENT_AUTHENTICATION_STATUS_AUTHENTICATED) == CODEX_AGENT_STATUS_OK);
    CHECK_INVALID_VALUES(codex_agent_authentication_status_validate, 3);

    CHECK(codex_agent_catalog_freshness_validate(CODEX_AGENT_CATALOG_FRESHNESS_LIVE) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_catalog_freshness_validate(CODEX_AGENT_CATALOG_FRESHNESS_FRESH_CACHE) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_catalog_freshness_validate(CODEX_AGENT_CATALOG_FRESHNESS_STALE_CACHE) == CODEX_AGENT_STATUS_OK);
    CHECK_INVALID_VALUES(codex_agent_catalog_freshness_validate, 3);

    CHECK(codex_agent_collaboration_mode_validate(CODEX_AGENT_COLLABORATION_MODE_DEFAULT) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_collaboration_mode_validate(CODEX_AGENT_COLLABORATION_MODE_PLAN) == CODEX_AGENT_STATUS_OK);
    CHECK_INVALID_VALUES(codex_agent_collaboration_mode_validate, 2);

    CHECK(codex_agent_elicitation_action_validate(CODEX_AGENT_ELICITATION_ACTION_ACCEPT) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_elicitation_action_validate(CODEX_AGENT_ELICITATION_ACTION_DECLINE) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_elicitation_action_validate(CODEX_AGENT_ELICITATION_ACTION_CANCEL) == CODEX_AGENT_STATUS_OK);
    CHECK_INVALID_VALUES(codex_agent_elicitation_action_validate, 3);

    CHECK(codex_agent_form_field_type_validate(CODEX_AGENT_FORM_FIELD_TYPE_STRING) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_form_field_type_validate(CODEX_AGENT_FORM_FIELD_TYPE_NUMBER) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_form_field_type_validate(CODEX_AGENT_FORM_FIELD_TYPE_INTEGER) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_form_field_type_validate(CODEX_AGENT_FORM_FIELD_TYPE_BOOLEAN) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_form_field_type_validate(CODEX_AGENT_FORM_FIELD_TYPE_SINGLE_SELECT) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_form_field_type_validate(CODEX_AGENT_FORM_FIELD_TYPE_MULTI_SELECT) == CODEX_AGENT_STATUS_OK);
    CHECK_INVALID_VALUES(codex_agent_form_field_type_validate, 6);

    CHECK(codex_agent_form_string_format_validate(CODEX_AGENT_FORM_STRING_FORMAT_EMAIL) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_form_string_format_validate(CODEX_AGENT_FORM_STRING_FORMAT_URI) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_form_string_format_validate(CODEX_AGENT_FORM_STRING_FORMAT_DATE) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_form_string_format_validate(CODEX_AGENT_FORM_STRING_FORMAT_DATE_TIME) == CODEX_AGENT_STATUS_OK);
    CHECK_INVALID_VALUES(codex_agent_form_string_format_validate, 4);

    CHECK(codex_agent_hook_run_status_validate(CODEX_AGENT_HOOK_RUN_STATUS_RUNNING) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_run_status_validate(CODEX_AGENT_HOOK_RUN_STATUS_COMPLETED) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_run_status_validate(CODEX_AGENT_HOOK_RUN_STATUS_FAILED) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_run_status_validate(CODEX_AGENT_HOOK_RUN_STATUS_BLOCKED) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_run_status_validate(CODEX_AGENT_HOOK_RUN_STATUS_STOPPED) == CODEX_AGENT_STATUS_OK);
    CHECK_INVALID_VALUES(codex_agent_hook_run_status_validate, 5);

    CHECK(codex_agent_hook_trust_status_validate(CODEX_AGENT_HOOK_TRUST_STATUS_MANAGED) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_trust_status_validate(CODEX_AGENT_HOOK_TRUST_STATUS_UNTRUSTED) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_trust_status_validate(CODEX_AGENT_HOOK_TRUST_STATUS_TRUSTED) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_hook_trust_status_validate(CODEX_AGENT_HOOK_TRUST_STATUS_MODIFIED) == CODEX_AGENT_STATUS_OK);
    CHECK_INVALID_VALUES(codex_agent_hook_trust_status_validate, 4);

    CHECK(codex_agent_installation_scope_validate(CODEX_AGENT_INSTALLATION_SCOPE_USER) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_installation_scope_validate(CODEX_AGENT_INSTALLATION_SCOPE_WORKSPACE) == CODEX_AGENT_STATUS_OK);
    CHECK_INVALID_VALUES(codex_agent_installation_scope_validate, 2);

    CHECK(codex_agent_integration_authorization_status_validate(CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_IDLE) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_authorization_status_validate(CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_STARTING) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_authorization_status_validate(CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_AWAITING_COMPLETION) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_authorization_status_validate(CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_AUTHORIZED) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_authorization_status_validate(CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_FAILED) == CODEX_AGENT_STATUS_OK);
    CHECK_INVALID_VALUES(codex_agent_integration_authorization_status_validate, 5);

    CHECK(codex_agent_mcp_auth_status_validate(CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_auth_status_validate(CODEX_AGENT_MCP_AUTH_STATUS_UNSUPPORTED) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_auth_status_validate(CODEX_AGENT_MCP_AUTH_STATUS_NOT_LOGGED_IN) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_auth_status_validate(CODEX_AGENT_MCP_AUTH_STATUS_BEARER_TOKEN) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_auth_status_validate(CODEX_AGENT_MCP_AUTH_STATUS_OAUTH) == CODEX_AGENT_STATUS_OK);
    CHECK_INVALID_VALUES(codex_agent_mcp_auth_status_validate, 5);

    CHECK(codex_agent_mcp_authentication_validate(CODEX_AGENT_MCP_AUTHENTICATION_OAUTH) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_authentication_validate(CODEX_AGENT_MCP_AUTHENTICATION_CHAT_GPT) == CODEX_AGENT_STATUS_OK);
    CHECK_INVALID_VALUES(codex_agent_mcp_authentication_validate, 2);

    CHECK(codex_agent_mcp_tool_exposure_surface_validate(CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_CODE_MODE) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_tool_exposure_surface_validate(CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_DEFERRED) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_tool_exposure_surface_validate(CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_DIRECT) == CODEX_AGENT_STATUS_OK);
    CHECK_INVALID_VALUES(codex_agent_mcp_tool_exposure_surface_validate, 3);

    CHECK(codex_agent_message_role_validate(CODEX_AGENT_MESSAGE_ROLE_USER) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_message_role_validate(CODEX_AGENT_MESSAGE_ROLE_ASSISTANT) == CODEX_AGENT_STATUS_OK);
    CHECK_INVALID_VALUES(codex_agent_message_role_validate, 2);

    CHECK(codex_agent_plugin_auth_policy_validate(CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_INSTALL) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_auth_policy_validate(CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_USE) == CODEX_AGENT_STATUS_OK);
    CHECK_INVALID_VALUES(codex_agent_plugin_auth_policy_validate, 2);

    CHECK(codex_agent_plugin_install_policy_validate(CODEX_AGENT_PLUGIN_INSTALL_POLICY_NOT_AVAILABLE) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_install_policy_validate(CODEX_AGENT_PLUGIN_INSTALL_POLICY_AVAILABLE) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_plugin_install_policy_validate(CODEX_AGENT_PLUGIN_INSTALL_POLICY_INSTALLED_BY_DEFAULT) == CODEX_AGENT_STATUS_OK);
    CHECK_INVALID_VALUES(codex_agent_plugin_install_policy_validate, 3);

    CHECK(codex_agent_resolution_validate(CODEX_AGENT_RESOLUTION_PREFERRED) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_resolution_validate(CODEX_AGENT_RESOLUTION_DEFAULT) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_resolution_validate(CODEX_AGENT_RESOLUTION_FIRST) == CODEX_AGENT_STATUS_OK);
    CHECK_INVALID_VALUES(codex_agent_resolution_validate, 3);

    CHECK(codex_agent_resource_origin_validate(CODEX_AGENT_RESOURCE_ORIGIN_USER) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_resource_origin_validate(CODEX_AGENT_RESOURCE_ORIGIN_WORKSPACE) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_resource_origin_validate(CODEX_AGENT_RESOURCE_ORIGIN_PLUGIN) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_resource_origin_validate(CODEX_AGENT_RESOURCE_ORIGIN_MANAGED) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_resource_origin_validate(CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN) == CODEX_AGENT_STATUS_OK);
    CHECK_INVALID_VALUES(codex_agent_resource_origin_validate, 5);

    CHECK(codex_agent_work_activity_validate(CODEX_AGENT_WORK_ACTIVITY_RUNNING_COMMAND) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_work_activity_validate(CODEX_AGENT_WORK_ACTIVITY_WRITING_FILES) == CODEX_AGENT_STATUS_OK);
    CHECK_INVALID_VALUES(codex_agent_work_activity_validate, 2);

    CHECK(codex_agent_authorization_purpose_validate(CODEX_AGENT_AUTHORIZATION_PURPOSE_CHAT_GPT) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_authorization_purpose_validate(CODEX_AGENT_AUTHORIZATION_PURPOSE_EXTERNAL) == CODEX_AGENT_STATUS_OK);
    CHECK_INVALID_VALUES(codex_agent_authorization_purpose_validate, 2);
    return 0;
}
