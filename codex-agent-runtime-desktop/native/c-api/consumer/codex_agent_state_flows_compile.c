#include "codex_agent.h"

#include <stdint.h>

_Static_assert(CODEX_AGENT_ABI_VERSION_MAJOR == UINT32_C(1), "ABI major");
_Static_assert(CODEX_AGENT_ABI_VERSION_MINOR == UINT32_C(13), "ABI minor");
_Static_assert(CODEX_AGENT_ABI_VERSION_PATCH == UINT32_C(0), "ABI patch");
_Static_assert(
    CODEX_AGENT_ABI_VERSION_CURRENT == UINT32_C(0x010D0000),
    "ABI current");

#define CHECK_INVALID(call)                                                    \
    do {                                                                       \
        if ((call) != CODEX_AGENT_STATUS_INVALID_ARGUMENT) {                  \
            return __LINE__;                                                   \
        }                                                                      \
    } while (0)

static void CODEX_AGENT_CALL state_callback(
    codex_agent_context_t *context,
    codex_agent_subscription_t *subscription,
    codex_agent_status_t status,
    codex_agent_snapshot_t *snapshot,
    int32_t terminal,
    void *user_data) {
    (void)context;
    (void)subscription;
    (void)status;
    (void)snapshot;
    (void)terminal;
    (void)user_data;
}

int main(void) {
    codex_agent_context_t *context = NULL;
    codex_agent_authentication_t *authentication = NULL;
    codex_agent_conversation_t *conversation = NULL;
    codex_agent_integration_authorization_t *authorization = NULL;
    codex_agent_interactions_t *interactions = NULL;
    codex_agent_snapshot_t *snapshot = NULL;
    codex_agent_subscription_t *subscription = NULL;
    codex_agent_authentication_state_t *authentication_state = NULL;
    codex_agent_integration_authorization_state_t *authorization_state = NULL;
    codex_agent_integration_t *integration = NULL;
    codex_agent_interaction_state_t *interaction_state = NULL;
    codex_agent_message_t *message = NULL;
    codex_agent_turn_progress_t *progress = NULL;
    codex_agent_pending_approval_t *approval = NULL;
    codex_agent_pending_elicitation_t *elicitation = NULL;
    int32_t flag = INT32_C(-1);
    size_t count = SIZE_MAX;
    int32_t user_data = INT32_C(0);

    CHECK_INVALID(codex_agent_authentication_state_get(
        context, authentication, &snapshot));
    CHECK_INVALID(codex_agent_authentication_state_subscribe(
        context, authentication, state_callback, &user_data, &subscription));
    CHECK_INVALID(codex_agent_authentication_is_authenticated_get(
        context, authentication, &snapshot));
    CHECK_INVALID(codex_agent_authentication_is_authenticated_subscribe(
        context, authentication, state_callback, &user_data, &subscription));
    CHECK_INVALID(codex_agent_authentication_is_authenticating_get(
        context, authentication, &snapshot));
    CHECK_INVALID(codex_agent_authentication_is_authenticating_subscribe(
        context, authentication, state_callback, &user_data, &subscription));
    CHECK_INVALID(codex_agent_authentication_state_value(
        context, snapshot, &authentication_state));
    CHECK_INVALID(codex_agent_state_boolean_value(context, snapshot, &flag));

    CHECK_INVALID(codex_agent_conversation_current_messages_get(
        context, conversation, &snapshot));
    CHECK_INVALID(codex_agent_conversation_current_messages_subscribe(
        context, conversation, state_callback, &user_data, &subscription));
    CHECK_INVALID(codex_agent_conversation_active_turn_progress_get(
        context, conversation, &snapshot));
    CHECK_INVALID(codex_agent_conversation_active_turn_progress_subscribe(
        context, conversation, state_callback, &user_data, &subscription));
    CHECK_INVALID(codex_agent_conversation_can_start_turn_get(
        context, conversation, &snapshot));
    CHECK_INVALID(codex_agent_conversation_can_start_turn_subscribe(
        context, conversation, state_callback, &user_data, &subscription));
    CHECK_INVALID(codex_agent_conversation_can_reload_get(
        context, conversation, &snapshot));
    CHECK_INVALID(codex_agent_conversation_can_reload_subscribe(
        context, conversation, state_callback, &user_data, &subscription));
    CHECK_INVALID(codex_agent_conversation_can_cancel_turn_get(
        context, conversation, &snapshot));
    CHECK_INVALID(codex_agent_conversation_can_cancel_turn_subscribe(
        context, conversation, state_callback, &user_data, &subscription));
    CHECK_INVALID(codex_agent_conversation_can_run_shell_command_get(
        context, conversation, &snapshot));
    CHECK_INVALID(codex_agent_conversation_can_run_shell_command_subscribe(
        context, conversation, state_callback, &user_data, &subscription));
    CHECK_INVALID(codex_agent_conversation_is_turn_active_get(
        context, conversation, &snapshot));
    CHECK_INVALID(codex_agent_conversation_is_turn_active_subscribe(
        context, conversation, state_callback, &user_data, &subscription));
    CHECK_INVALID(codex_agent_conversation_current_messages_count(
        context, snapshot, &count));
    CHECK_INVALID(codex_agent_conversation_current_messages_at(
        context, snapshot, 0u, &message));
    CHECK_INVALID(codex_agent_conversation_active_turn_progress_has_value(
        context, snapshot, &flag));
    CHECK_INVALID(codex_agent_conversation_active_turn_progress_value(
        context, snapshot, &progress));

    CHECK_INVALID(codex_agent_integration_authorization_state_get(
        context, authorization, &snapshot));
    CHECK_INVALID(codex_agent_integration_authorization_state_subscribe(
        context, authorization, state_callback, &user_data, &subscription));
    CHECK_INVALID(codex_agent_integration_authorization_active_get(
        context, authorization, &snapshot));
    CHECK_INVALID(codex_agent_integration_authorization_active_subscribe(
        context, authorization, state_callback, &user_data, &subscription));
    CHECK_INVALID(codex_agent_integration_authorization_is_authorizing_get(
        context, authorization, &snapshot));
    CHECK_INVALID(codex_agent_integration_authorization_is_authorizing_subscribe(
        context, authorization, state_callback, &user_data, &subscription));
    CHECK_INVALID(codex_agent_integration_authorization_state_value(
        context, snapshot, &authorization_state));
    CHECK_INVALID(codex_agent_integration_authorization_active_has_value(
        context, snapshot, &flag));
    CHECK_INVALID(codex_agent_integration_authorization_active_value(
        context, snapshot, &integration));

    CHECK_INVALID(codex_agent_interactions_state_get(
        context, interactions, &snapshot));
    CHECK_INVALID(codex_agent_interactions_state_subscribe(
        context, interactions, state_callback, &user_data, &subscription));
    CHECK_INVALID(codex_agent_interactions_approvals_get(
        context, interactions, &snapshot));
    CHECK_INVALID(codex_agent_interactions_approvals_subscribe(
        context, interactions, state_callback, &user_data, &subscription));
    CHECK_INVALID(codex_agent_interactions_elicitations_get(
        context, interactions, &snapshot));
    CHECK_INVALID(codex_agent_interactions_elicitations_subscribe(
        context, interactions, state_callback, &user_data, &subscription));
    CHECK_INVALID(codex_agent_interactions_state_value(
        context, snapshot, &interaction_state));
    CHECK_INVALID(codex_agent_interactions_approvals_count(
        context, snapshot, &count));
    CHECK_INVALID(codex_agent_interactions_approvals_at(
        context, snapshot, 0u, &approval));
    CHECK_INVALID(codex_agent_interactions_elicitations_count(
        context, snapshot, &count));
    CHECK_INVALID(codex_agent_interactions_elicitations_at(
        context, snapshot, 0u, &elicitation));

    return 0;
}
