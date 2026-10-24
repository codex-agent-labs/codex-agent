#include "codex_agent.h"

#define OBSERVE(symbol)                                      \
    do {                                                     \
        void (*volatile observed)(void) = (void (*)(void))(symbol); \
        (void)observed;                                      \
    } while (0)

int main(void) {
    OBSERVE(codex_agent_form_value_from_boolean);
    OBSERVE(codex_agent_form_value_from_number);
    OBSERVE(codex_agent_form_value_from_text);
    OBSERVE(codex_agent_form_value_from_text_list);
    OBSERVE(codex_agent_form_value_destroy);
    OBSERVE(codex_agent_form_value_kind);
    OBSERVE(codex_agent_form_value_boolean);
    OBSERVE(codex_agent_form_value_number);
    OBSERVE(codex_agent_form_value_text);
    OBSERVE(codex_agent_form_value_text_list);

    OBSERVE(codex_agent_form_field_create);
    OBSERVE(codex_agent_form_field_destroy);
    OBSERVE(codex_agent_form_field_name_copy);
    OBSERVE(codex_agent_form_field_title_copy);
    OBSERVE(codex_agent_form_field_has_description);
    OBSERVE(codex_agent_form_field_description_copy);
    OBSERVE(codex_agent_form_field_is_required);
    OBSERVE(codex_agent_form_field_type);
    OBSERVE(codex_agent_form_field_options_count);
    OBSERVE(codex_agent_form_field_option_at);
    OBSERVE(codex_agent_form_field_has_default_value);
    OBSERVE(codex_agent_form_field_default_value);
    OBSERVE(codex_agent_form_field_minimum);
    OBSERVE(codex_agent_form_field_maximum);
    OBSERVE(codex_agent_form_field_format);
    OBSERVE(codex_agent_form_field_minimum_length);
    OBSERVE(codex_agent_form_field_maximum_length);
    OBSERVE(codex_agent_form_field_minimum_selections);
    OBSERVE(codex_agent_form_field_maximum_selections);
    OBSERVE(codex_agent_form_field_allows_other);
    OBSERVE(codex_agent_form_field_is_secret);

    OBSERVE(codex_agent_elicitation_create);
    OBSERVE(codex_agent_elicitation_destroy);
    OBSERVE(codex_agent_elicitation_request_id_copy);
    OBSERVE(codex_agent_elicitation_server_name_copy);
    OBSERVE(codex_agent_elicitation_conversation_id);
    OBSERVE(codex_agent_elicitation_message_copy);
    OBSERVE(codex_agent_elicitation_has_form);
    OBSERVE(codex_agent_elicitation_form_count);
    OBSERVE(codex_agent_elicitation_form_at);
    OBSERVE(codex_agent_elicitation_has_url);
    OBSERVE(codex_agent_elicitation_url_copy);

    OBSERVE(codex_agent_elicitation_response_create);
    OBSERVE(codex_agent_elicitation_response_destroy);
    OBSERVE(codex_agent_elicitation_response_action);
    OBSERVE(codex_agent_elicitation_response_content_count);
    OBSERVE(codex_agent_elicitation_response_content_value);

    OBSERVE(codex_agent_pending_elicitation_create);
    OBSERVE(codex_agent_pending_elicitation_destroy);
    OBSERVE(codex_agent_pending_elicitation_elicitation);
    OBSERVE(codex_agent_pending_elicitation_request_id_copy);
    OBSERVE(codex_agent_pending_elicitation_conversation_id);

    OBSERVE(codex_agent_pending_interaction_from_approval);
    OBSERVE(codex_agent_pending_interaction_from_elicitation);
    OBSERVE(codex_agent_pending_interaction_destroy);
    OBSERVE(codex_agent_pending_interaction_kind);
    OBSERVE(codex_agent_pending_interaction_approval);
    OBSERVE(codex_agent_pending_interaction_elicitation);

    OBSERVE(codex_agent_interaction_state_create);
    OBSERVE(codex_agent_interaction_state_destroy);
    OBSERVE(codex_agent_interaction_state_pending_count);
    OBSERVE(codex_agent_interaction_state_pending_at);
    OBSERVE(codex_agent_interaction_state_resolving_request_ids_count);
    OBSERVE(codex_agent_interaction_state_resolving_request_ids_contains);
    OBSERVE(codex_agent_interaction_state_has_failure);
    OBSERVE(codex_agent_interaction_state_failure);
    return 0;
}
