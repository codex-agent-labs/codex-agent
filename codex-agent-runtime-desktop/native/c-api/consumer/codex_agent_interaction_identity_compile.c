#include "codex_agent.h"

#include <stdint.h>

_Static_assert(CODEX_AGENT_ABI_VERSION_MAJOR == UINT32_C(1), "ABI major");
_Static_assert(CODEX_AGENT_ABI_VERSION_MINOR == UINT32_C(12), "ABI minor");
_Static_assert(CODEX_AGENT_ABI_VERSION_PATCH == UINT32_C(0), "ABI patch");
_Static_assert(
    CODEX_AGENT_ABI_VERSION_CURRENT == UINT32_C(0x010C0000),
    "ABI current");
_Static_assert(
    CODEX_AGENT_ABI_VERSION_ENCODE(1, 12, 0) ==
        CODEX_AGENT_ABI_VERSION_CURRENT,
    "ABI encoding");

#define CHECK(condition)                                                       \
    do {                                                                       \
        if (!(condition)) {                                                    \
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
    codex_agent_context_t *context = NULL;
    codex_agent_interactions_t *interactions = NULL;
    codex_agent_interaction_state_t *state = NULL;
    codex_agent_pending_interaction_t *interaction = NULL;
    codex_agent_pending_approval_t *approval = NULL;
    codex_agent_pending_elicitation_t *elicitation = NULL;
    codex_agent_elicitation_response_t *response = NULL;
    codex_agent_operation_t *operation = NULL;
    codex_agent_operation_t *const occupied_operation =
        (codex_agent_operation_t *)(uintptr_t)UINTPTR_MAX;
    const codex_agent_approval_decision_t decision =
        CODEX_AGENT_APPROVAL_DECISION_ACCEPT;
    codex_agent_status_t result = (codex_agent_status_t)INT32_C(-1);
    int32_t is_resolving = INT32_C(-1);
    int32_t user_data = INT32_C(0);

    CHECK(codex_agent_interaction_state_is_resolving(
              context, state, interaction, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_interaction_state_is_resolving(
              context, state, interaction, &is_resolving) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(is_resolving == INT32_C(-1));

    CHECK(codex_agent_interactions_open_url(
              context, interactions, elicitation, operation_callback,
              &user_data, NULL) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_interactions_open_url(
              context, interactions, elicitation, operation_callback,
              &user_data, &operation) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(operation == NULL);
    operation = occupied_operation;
    CHECK(codex_agent_interactions_open_url(
              context, interactions, elicitation, operation_callback,
              &user_data, &operation) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(operation == occupied_operation);

    operation = NULL;
    CHECK(codex_agent_interactions_resolve_approval(
              context, interactions, approval, decision, operation_callback,
              &user_data, NULL) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_interactions_resolve_approval(
              context, interactions, approval, decision, operation_callback,
              &user_data, &operation) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(operation == NULL);
    operation = occupied_operation;
    CHECK(codex_agent_interactions_resolve_approval(
              context, interactions, approval, decision, operation_callback,
              &user_data, &operation) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(operation == occupied_operation);

    operation = NULL;
    CHECK(codex_agent_interactions_resolve_elicitation(
              context, interactions, elicitation, response,
              operation_callback, &user_data, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_interactions_resolve_elicitation(
              context, interactions, elicitation, response,
              operation_callback, &user_data, &operation) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(operation == NULL);
    operation = occupied_operation;
    CHECK(codex_agent_interactions_resolve_elicitation(
              context, interactions, elicitation, response,
              operation_callback, &user_data, &operation) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(operation == occupied_operation);

    CHECK(codex_agent_operation_result(context, NULL, NULL) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_operation_result(context, NULL, &result) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(result == (codex_agent_status_t)INT32_C(-1));

    return 0;
}
