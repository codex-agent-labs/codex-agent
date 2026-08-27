@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentApprovalDecision
import io.github.codex_agent_labs.codexmobile.agent.AgentAuthenticationStatus
import io.github.codex_agent_labs.codexmobile.agent.AgentCatalogFreshness
import io.github.codex_agent_labs.codexmobile.agent.AgentCollaborationMode
import io.github.codex_agent_labs.codexmobile.agent.AgentElicitationAction
import io.github.codex_agent_labs.codexmobile.agent.AgentFormFieldType
import io.github.codex_agent_labs.codexmobile.agent.AgentFormStringFormat
import io.github.codex_agent_labs.codexmobile.agent.AgentHookRunStatus
import io.github.codex_agent_labs.codexmobile.agent.AgentHookTrustStatus
import io.github.codex_agent_labs.codexmobile.agent.AgentInstallationScope
import io.github.codex_agent_labs.codexmobile.agent.AgentIntegrationAuthorizationStatus
import io.github.codex_agent_labs.codexmobile.agent.AgentMcpAuthentication
import io.github.codex_agent_labs.codexmobile.agent.AgentMcpAuthStatus
import io.github.codex_agent_labs.codexmobile.agent.AgentMcpToolExposureSurface
import io.github.codex_agent_labs.codexmobile.agent.AgentMessageRole
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginAuthPolicy
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginInstallPolicy
import io.github.codex_agent_labs.codexmobile.agent.AgentResolution
import io.github.codex_agent_labs.codexmobile.agent.AgentResourceOrigin
import io.github.codex_agent_labs.codexmobile.agent.AgentWorkActivity
import io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationPurpose

@CName("codex_agent_approval_decision_validate")
public fun codexAgentApprovalDecisionValidate(value: Int): Int {
    when (value) {
        0 -> AgentApprovalDecision.ACCEPT
        1 -> AgentApprovalDecision.DECLINE
        else -> return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    return CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_authentication_status_validate")
public fun codexAgentAuthenticationStatusValidate(value: Int): Int {
    when (value) {
        0 -> AgentAuthenticationStatus.SIGNED_OUT
        1 -> AgentAuthenticationStatus.AUTHENTICATING
        2 -> AgentAuthenticationStatus.AUTHENTICATED
        else -> return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    return CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_catalog_freshness_validate")
public fun codexAgentCatalogFreshnessValidate(value: Int): Int {
    when (value) {
        0 -> AgentCatalogFreshness.LIVE
        1 -> AgentCatalogFreshness.FRESH_CACHE
        2 -> AgentCatalogFreshness.STALE_CACHE
        else -> return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    return CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_collaboration_mode_validate")
public fun codexAgentCollaborationModeValidate(value: Int): Int {
    when (value) {
        0 -> AgentCollaborationMode.DEFAULT
        1 -> AgentCollaborationMode.PLAN
        else -> return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    return CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_elicitation_action_validate")
public fun codexAgentElicitationActionValidate(value: Int): Int {
    when (value) {
        0 -> AgentElicitationAction.ACCEPT
        1 -> AgentElicitationAction.DECLINE
        2 -> AgentElicitationAction.CANCEL
        else -> return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    return CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_form_field_type_validate")
public fun codexAgentFormFieldTypeValidate(value: Int): Int {
    when (value) {
        0 -> AgentFormFieldType.STRING
        1 -> AgentFormFieldType.NUMBER
        2 -> AgentFormFieldType.INTEGER
        3 -> AgentFormFieldType.BOOLEAN
        4 -> AgentFormFieldType.SINGLE_SELECT
        5 -> AgentFormFieldType.MULTI_SELECT
        else -> return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    return CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_form_string_format_validate")
public fun codexAgentFormStringFormatValidate(value: Int): Int {
    when (value) {
        0 -> AgentFormStringFormat.EMAIL
        1 -> AgentFormStringFormat.URI
        2 -> AgentFormStringFormat.DATE
        3 -> AgentFormStringFormat.DATE_TIME
        else -> return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    return CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_hook_run_status_validate")
public fun codexAgentHookRunStatusValidate(value: Int): Int {
    when (value) {
        0 -> AgentHookRunStatus.RUNNING
        1 -> AgentHookRunStatus.COMPLETED
        2 -> AgentHookRunStatus.FAILED
        3 -> AgentHookRunStatus.BLOCKED
        4 -> AgentHookRunStatus.STOPPED
        else -> return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    return CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_hook_trust_status_validate")
public fun codexAgentHookTrustStatusValidate(value: Int): Int {
    when (value) {
        0 -> AgentHookTrustStatus.MANAGED
        1 -> AgentHookTrustStatus.UNTRUSTED
        2 -> AgentHookTrustStatus.TRUSTED
        3 -> AgentHookTrustStatus.MODIFIED
        else -> return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    return CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_installation_scope_validate")
public fun codexAgentInstallationScopeValidate(value: Int): Int {
    when (value) {
        0 -> AgentInstallationScope.User
        1 -> AgentInstallationScope.Workspace
        else -> return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    return CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_integration_authorization_status_validate")
public fun codexAgentIntegrationAuthorizationStatusValidate(value: Int): Int {
    when (value) {
        0 -> AgentIntegrationAuthorizationStatus.IDLE
        1 -> AgentIntegrationAuthorizationStatus.STARTING
        2 -> AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION
        3 -> AgentIntegrationAuthorizationStatus.AUTHORIZED
        4 -> AgentIntegrationAuthorizationStatus.FAILED
        else -> return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    return CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_mcp_auth_status_validate")
public fun codexAgentMcpAuthStatusValidate(value: Int): Int {
    when (value) {
        0 -> AgentMcpAuthStatus.UNKNOWN
        1 -> AgentMcpAuthStatus.UNSUPPORTED
        2 -> AgentMcpAuthStatus.NOT_LOGGED_IN
        3 -> AgentMcpAuthStatus.BEARER_TOKEN
        4 -> AgentMcpAuthStatus.OAUTH
        else -> return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    return CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_mcp_authentication_validate")
public fun codexAgentMcpAuthenticationValidate(value: Int): Int {
    when (value) {
        0 -> AgentMcpAuthentication.OAUTH
        1 -> AgentMcpAuthentication.CHAT_GPT
        else -> return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    return CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_mcp_tool_exposure_surface_validate")
public fun codexAgentMcpToolExposureSurfaceValidate(value: Int): Int {
    when (value) {
        0 -> AgentMcpToolExposureSurface.CODE_MODE
        1 -> AgentMcpToolExposureSurface.DEFERRED
        2 -> AgentMcpToolExposureSurface.DIRECT
        else -> return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    return CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_message_role_validate")
public fun codexAgentMessageRoleValidate(value: Int): Int {
    when (value) {
        0 -> AgentMessageRole.USER
        1 -> AgentMessageRole.ASSISTANT
        else -> return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    return CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_plugin_auth_policy_validate")
public fun codexAgentPluginAuthPolicyValidate(value: Int): Int {
    when (value) {
        0 -> AgentPluginAuthPolicy.ON_INSTALL
        1 -> AgentPluginAuthPolicy.ON_USE
        else -> return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    return CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_plugin_install_policy_validate")
public fun codexAgentPluginInstallPolicyValidate(value: Int): Int {
    when (value) {
        0 -> AgentPluginInstallPolicy.NOT_AVAILABLE
        1 -> AgentPluginInstallPolicy.AVAILABLE
        2 -> AgentPluginInstallPolicy.INSTALLED_BY_DEFAULT
        else -> return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    return CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_resolution_validate")
public fun codexAgentResolutionValidate(value: Int): Int {
    when (value) {
        0 -> AgentResolution.Preferred
        1 -> AgentResolution.Default
        2 -> AgentResolution.First
        else -> return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    return CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_resource_origin_validate")
public fun codexAgentResourceOriginValidate(value: Int): Int {
    when (value) {
        0 -> AgentResourceOrigin.USER
        1 -> AgentResourceOrigin.WORKSPACE
        2 -> AgentResourceOrigin.PLUGIN
        3 -> AgentResourceOrigin.MANAGED
        4 -> AgentResourceOrigin.UNKNOWN
        else -> return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    return CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_work_activity_validate")
public fun codexAgentWorkActivityValidate(value: Int): Int {
    when (value) {
        0 -> AgentWorkActivity.RUNNING_COMMAND
        1 -> AgentWorkActivity.WRITING_FILES
        else -> return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    return CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_authorization_purpose_validate")
public fun codexAgentAuthorizationPurposeValidate(value: Int): Int {
    when (value) {
        0 -> CodexAuthorizationPurpose.CHAT_GPT
        1 -> CodexAuthorizationPurpose.EXTERNAL
        else -> return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    return CODEX_AGENT_STATUS_OK
}
