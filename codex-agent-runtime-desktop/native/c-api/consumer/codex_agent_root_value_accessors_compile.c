#include "codex_agent.h"

#define OBSERVE(symbol)                                             \
    do {                                                            \
        void (*volatile observed)(void) = (void (*)(void))(symbol); \
        (void)observed;                                             \
    } while (0)

int main(void) {
    OBSERVE(codex_agent_host_state_failed_workspace);
    OBSERVE(codex_agent_host_state_preparing_workspace);
    OBSERVE(codex_agent_host_state_workspace_required_requirement);
    OBSERVE(codex_agent_interaction_state_pending_for);
    OBSERVE(codex_agent_pending_interaction_list_destroy);
    OBSERVE(codex_agent_pending_interaction_list_count);
    OBSERVE(codex_agent_pending_interaction_list_at);
    return 0;
}
