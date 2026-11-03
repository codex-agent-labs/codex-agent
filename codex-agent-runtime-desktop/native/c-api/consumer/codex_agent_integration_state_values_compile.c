#include "codex_agent.h"

#include <stdint.h>
#include <string.h>

#define CHECK(condition)     \
    do {                     \
        if (!(condition)) {  \
            return __LINE__; \
        }                    \
    } while (0)

#define VIEW(value) \
    (&(const codex_agent_string_view_t){(const uint8_t *)(value), sizeof(value) - 1u})

#define CHECK_COPY(function, context, handle, expected)                        \
    do {                                                                        \
        uint8_t copy_buffer[128] = {0};                                         \
        size_t copy_required = SIZE_MAX;                                        \
        CHECK((function)((context), (handle), NULL, 0u, &copy_required) ==      \
              CODEX_AGENT_STATUS_BUFFER_TOO_SMALL);                            \
        CHECK(copy_required == sizeof(expected) - 1u);                          \
        CHECK((function)((context), (handle), copy_buffer, sizeof(copy_buffer), \
                         &copy_required) == CODEX_AGENT_STATUS_OK);             \
        CHECK(copy_required == sizeof(expected) - 1u);                          \
        CHECK(memcmp(copy_buffer, (expected), sizeof(expected) - 1u) == 0);     \
    } while (0)

static int create_connector_target(
    codex_agent_context_t *context,
    codex_agent_integration_t **out_target) {
    codex_agent_connector_t *connector = NULL;
    codex_agent_integration_connector_t *connector_integration = NULL;

    CHECK(codex_agent_connector_create(
              context,
              VIEW("state-connector"),
              VIEW("State connector"),
              VIEW("State connector description"),
              INT32_C(0),
              (&(const codex_agent_string_view_t){NULL, 0u}),
              INT32_C(1),
              INT32_C(1),
              NULL,
              0u,
              &connector) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_connector_create(
              context, connector, &connector_integration) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_from_connector(
              context, connector_integration, out_target) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_connector_destroy(context, &connector_integration) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_connector_destroy(context, &connector) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int create_mcp_target(
    codex_agent_context_t *context,
    codex_agent_integration_t **out_target) {
    codex_agent_mcp_server_t *server = NULL;
    codex_agent_integration_mcp_server_t *server_integration = NULL;

    CHECK(codex_agent_mcp_server_create(
              context,
              VIEW("state-server"),
              VIEW("State server"),
              CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN,
              NULL,
              CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN,
              INT32_C(1),
              &server) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_mcp_server_create(
              context, server, &server_integration) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_from_mcp_server(
              context, server_integration, out_target) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_mcp_server_destroy(context, &server_integration) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_mcp_server_destroy(context, &server) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_absent_values(codex_agent_context_t *context) {
    const codex_agent_integration_authorization_status_t statuses[] = {
        CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_IDLE,
        CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_STARTING,
        CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_AWAITING_COMPLETION,
        CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_AUTHORIZED,
        CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_FAILED,
    };
    size_t index;

    for (index = 0u; index < sizeof(statuses) / sizeof(statuses[0]); ++index) {
        codex_agent_integration_authorization_state_t *state = NULL;
        codex_agent_integration_authorization_status_t status = INT32_MIN;
        codex_agent_integration_t *target = NULL;
        codex_agent_failure_t *failure = NULL;

        CHECK(codex_agent_integration_authorization_state_create(
                  context, statuses[index], NULL, NULL, &state) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_integration_authorization_state_status(context, state, &status) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(status == statuses[index]);
        CHECK(codex_agent_integration_authorization_state_target(context, state, &target) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(target == NULL);
        CHECK(codex_agent_integration_authorization_state_failure(context, state, &failure) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(failure == NULL);
        CHECK(codex_agent_integration_authorization_state_destroy(context, &state) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_integration_authorization_state_destroy(context, &state) ==
              CODEX_AGENT_STATUS_OK);
    }
    return 0;
}

static int verify_connector_target_and_failure(codex_agent_context_t *context) {
    codex_agent_integration_t *source_target = NULL;
    codex_agent_failure_t *source_failure = NULL;
    codex_agent_integration_authorization_state_t *state = NULL;
    codex_agent_integration_t *first_target = NULL;
    codex_agent_integration_t *second_target = NULL;
    codex_agent_failure_t *first_failure = NULL;
    codex_agent_failure_t *second_failure = NULL;
    codex_agent_integration_connector_t *connector = NULL;
    codex_agent_integration_mcp_server_t *wrong_server = NULL;
    codex_agent_integration_kind_t kind = INT32_MIN;
    codex_agent_integration_authorization_status_t status = INT32_MIN;
    int32_t recoverable = INT32_MIN;

    CHECK(create_connector_target(context, &source_target) == 0);
    CHECK(codex_agent_failure_create(
              context,
              VIEW("integration_authorization_failed"),
              VIEW("Authorization failed"),
              INT32_C(1),
              &source_failure) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_authorization_state_create(
              context,
              CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_FAILED,
              source_target,
              source_failure,
              &state) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_destroy(context, &source_target) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_failure_release(context, &source_failure) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_authorization_state_status(context, state, &status) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(status == CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_FAILED);
    CHECK(codex_agent_integration_authorization_state_target(context, state, &first_target) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_authorization_state_target(context, state, &second_target) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(first_target != second_target);
    CHECK(codex_agent_integration_authorization_state_failure(context, state, &first_failure) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_authorization_state_failure(context, state, &second_failure) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(first_failure != second_failure);
    CHECK(codex_agent_integration_authorization_state_destroy(context, &state) ==
          CODEX_AGENT_STATUS_OK);

    CHECK(codex_agent_integration_kind(context, first_target, &kind) == CODEX_AGENT_STATUS_OK);
    CHECK(kind == CODEX_AGENT_INTEGRATION_KIND_CONNECTOR);
    CHECK(codex_agent_integration_connector(context, first_target, &connector) ==
          CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_integration_connector_id_copy,
               context, connector, "state-connector");
    CHECK(codex_agent_integration_mcp_server(context, first_target, &wrong_server) ==
          CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(wrong_server == NULL);
    CHECK(codex_agent_integration_connector_destroy(context, &connector) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_destroy(context, &first_target) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_kind(context, second_target, &kind) == CODEX_AGENT_STATUS_OK);
    CHECK(kind == CODEX_AGENT_INTEGRATION_KIND_CONNECTOR);
    CHECK(codex_agent_integration_destroy(context, &second_target) == CODEX_AGENT_STATUS_OK);

    CHECK_COPY(codex_agent_failure_code_copy,
               context, first_failure, "integration_authorization_failed");
    CHECK(codex_agent_failure_release(context, &first_failure) == CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_failure_message_copy,
               context, second_failure, "Authorization failed");
    CHECK(codex_agent_failure_is_recoverable(context, second_failure, &recoverable) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(recoverable == INT32_C(1));
    CHECK(codex_agent_failure_release(context, &second_failure) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_mcp_target(codex_agent_context_t *context) {
    codex_agent_integration_t *source_target = NULL;
    codex_agent_integration_authorization_state_t *state = NULL;
    codex_agent_integration_t *target = NULL;
    codex_agent_integration_mcp_server_t *server = NULL;
    codex_agent_integration_kind_t kind = INT32_MIN;

    CHECK(create_mcp_target(context, &source_target) == 0);
    CHECK(codex_agent_integration_authorization_state_create(
              context,
              CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_AUTHORIZED,
              source_target,
              NULL,
              &state) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_destroy(context, &source_target) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_authorization_state_target(context, state, &target) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_authorization_state_destroy(context, &state) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_kind(context, target, &kind) == CODEX_AGENT_STATUS_OK);
    CHECK(kind == CODEX_AGENT_INTEGRATION_KIND_MCP_SERVER);
    CHECK(codex_agent_integration_mcp_server(context, target, &server) == CODEX_AGENT_STATUS_OK);
    CHECK_COPY(codex_agent_integration_mcp_server_id_copy, context, server, "state-server");
    CHECK(codex_agent_integration_mcp_server_destroy(context, &server) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_destroy(context, &target) == CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_fail_closed_boundaries(
    codex_agent_context_t *context,
    codex_agent_context_t *other_context) {
    codex_agent_integration_t *target = NULL;
    codex_agent_failure_t *failure = NULL;
    codex_agent_integration_authorization_state_t *state = NULL;
    codex_agent_integration_authorization_state_t *occupied = NULL;
    codex_agent_integration_authorization_status_t status = INT32_C(73);

    CHECK(create_connector_target(context, &target) == 0);
    CHECK(codex_agent_failure_create(
              context, VIEW("code"), VIEW("message"), INT32_C(0), &failure) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_authorization_state_create(
              context, INT32_C(5), target, failure, &state) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(state == NULL);
    CHECK(codex_agent_integration_authorization_state_create(
              other_context,
              CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_FAILED,
              target,
              failure,
              &state) == CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(state == NULL);
    CHECK(codex_agent_integration_authorization_state_create(
              context,
              CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_FAILED,
              (codex_agent_integration_t *)failure,
              NULL,
              &state) == CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(state == NULL);
    CHECK(codex_agent_integration_authorization_state_create(
              context,
              CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_FAILED,
              target,
              failure,
              &state) == CODEX_AGENT_STATUS_OK);
    occupied = state;
    CHECK(codex_agent_integration_authorization_state_create(
              context,
              CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_IDLE,
              NULL,
              NULL,
              &occupied) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(occupied == state);
    CHECK(codex_agent_integration_authorization_state_status(other_context, state, &status) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(status == INT32_C(73));
    CHECK(codex_agent_integration_authorization_state_status(
              context,
              (codex_agent_integration_authorization_state_t *)target,
              &status) == CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(status == INT32_C(73));
    CHECK(codex_agent_integration_authorization_state_destroy(context, &state) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_integration_destroy(context, &target) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_failure_release(context, &failure) == CODEX_AGENT_STATUS_OK);
    return 0;
}

int main(void) {
    codex_agent_context_t *context = NULL;
    codex_agent_context_t *other_context = NULL;

    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_create(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(verify_absent_values(context) == 0);
    CHECK(verify_connector_target_and_failure(context) == 0);
    CHECK(verify_mcp_target(context) == 0);
    CHECK(verify_fail_closed_boundaries(context, other_context) == 0);
    CHECK(codex_agent_context_destroy(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    return 0;
}
