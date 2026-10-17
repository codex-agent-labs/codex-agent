#include "codex_agent.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHECK(condition)                                                       \
    do {                                                                       \
        if (!(condition)) {                                                    \
            (void)fprintf(stderr, "check failed at line %d: %s\n",            \
                          __LINE__, #condition);                               \
            return __LINE__;                                                   \
        }                                                                      \
    } while (0)

#define STRING_VIEW(data_value, size_value)                                    \
    (&(const codex_agent_string_view_t){                                       \
        (const uint8_t *)(data_value), (size_value)                            \
    })
#define VIEW(value) STRING_VIEW((value), sizeof(value) - 1u)
#define EMPTY_VIEW STRING_VIEW(NULL, 0u)

#define CHECK_COPY(function, context, handle, expected)                        \
    do {                                                                       \
        const char *copy_expected = (expected);                                \
        const size_t copy_size = strlen(copy_expected);                        \
        uint8_t copy_buffer[160] = {0};                                        \
        size_t copy_required = SIZE_MAX;                                       \
        CHECK(copy_size <= sizeof(copy_buffer));                               \
        CHECK((function)((context), (handle), NULL, 0u, &copy_required) ==     \
              (copy_size == 0u ? CODEX_AGENT_STATUS_OK :                       \
                                  CODEX_AGENT_STATUS_BUFFER_TOO_SMALL));       \
        CHECK(copy_required == copy_size);                                     \
        CHECK((function)((context), (handle), copy_buffer,                     \
                         sizeof(copy_buffer), &copy_required) ==               \
              CODEX_AGENT_STATUS_OK);                                          \
        CHECK(copy_required == copy_size);                                     \
        CHECK(memcmp(copy_buffer, copy_expected, copy_size) == 0);             \
    } while (0)

static int verify_absent_states_and_settings(codex_agent_context_t *context) {
    const codex_agent_authentication_status_t statuses[] = {
        CODEX_AGENT_AUTHENTICATION_STATUS_SIGNED_OUT,
        CODEX_AGENT_AUTHENTICATION_STATUS_AUTHENTICATING,
        CODEX_AGENT_AUTHENTICATION_STATUS_AUTHENTICATED,
    };
    const codex_agent_approval_preset_t presets[] = {
        CODEX_AGENT_APPROVAL_PRESET_NEVER,
        CODEX_AGENT_APPROVAL_PRESET_AUTO_REVIEW,
        CODEX_AGENT_APPROVAL_PRESET_ASK_ME,
        CODEX_AGENT_APPROVAL_PRESET_STRICT,
    };
    size_t index;

    for (index = 0u; index < sizeof(statuses) / sizeof(statuses[0]); ++index) {
        codex_agent_authentication_state_t *state = NULL;
        codex_agent_authorization_url_t *url = NULL;
        codex_agent_failure_t *failure = NULL;
        codex_agent_authentication_status_t status = INT32_MIN;
        int32_t present = INT32_MIN;
        size_t required = SIZE_MAX;

        CHECK(codex_agent_authentication_state_create(
                  context,
                  statuses[index],
                  INT32_C(0),
                  NULL,
                  INT32_C(0),
                  NULL,
                  INT32_C(0),
                  EMPTY_VIEW,
                  INT32_C(0),
                  NULL,
                  &state) == CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_authentication_state_status(context, state, &status) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(status == statuses[index]);
        CHECK(codex_agent_authentication_state_has_pending_sign_in_url(
                  context, state, &present) == CODEX_AGENT_STATUS_OK);
        CHECK(present == INT32_C(0));
        CHECK(codex_agent_authentication_state_pending_sign_in_url(
                  context, state, &url) == CODEX_AGENT_STATUS_NOT_READY);
        CHECK(url == NULL);
        CHECK(codex_agent_authentication_state_has_device_verification_url(
                  context, state, &present) == CODEX_AGENT_STATUS_OK);
        CHECK(present == INT32_C(0));
        CHECK(codex_agent_authentication_state_device_verification_url(
                  context, state, &url) == CODEX_AGENT_STATUS_NOT_READY);
        CHECK(url == NULL);
        CHECK(codex_agent_authentication_state_has_device_user_code(
                  context, state, &present) == CODEX_AGENT_STATUS_OK);
        CHECK(present == INT32_C(0));
        CHECK(codex_agent_authentication_state_device_user_code_copy(
                  context, state, NULL, 0u, &required) ==
              CODEX_AGENT_STATUS_NOT_READY);
        CHECK(required == SIZE_MAX);
        CHECK(codex_agent_authentication_state_has_failure(context, state, &present) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(present == INT32_C(0));
        CHECK(codex_agent_authentication_state_failure(context, state, &failure) ==
              CODEX_AGENT_STATUS_NOT_READY);
        CHECK(failure == NULL);
        CHECK(codex_agent_authentication_state_destroy(context, &state) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(state == NULL);
        CHECK(codex_agent_authentication_state_destroy(context, &state) ==
              CODEX_AGENT_STATUS_OK);
    }

    for (index = 0u; index < sizeof(presets) / sizeof(presets[0]); ++index) {
        codex_agent_conversation_settings_t *settings = NULL;
        codex_agent_approval_preset_t preset = INT32_MIN;
        int32_t present = INT32_MIN;
        size_t required = SIZE_MAX;
        const int32_t has_tier = index == 1u ? INT32_C(0) : INT32_C(1);
        const codex_agent_string_view_t *tier = index == 1u ? EMPTY_VIEW : VIEW("tier");

        CHECK(codex_agent_conversation_settings_create(
                  context, presets[index], has_tier, tier, &settings) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(codex_agent_conversation_settings_approval_preset(
                  context, settings, &preset) == CODEX_AGENT_STATUS_OK);
        CHECK(preset == presets[index]);
        CHECK(codex_agent_conversation_settings_has_service_tier(
                  context, settings, &present) == CODEX_AGENT_STATUS_OK);
        CHECK(present == has_tier);
        if (has_tier == INT32_C(0)) {
            CHECK(codex_agent_conversation_settings_service_tier_copy(
                      context, settings, NULL, 0u, &required) ==
                  CODEX_AGENT_STATUS_NOT_READY);
            CHECK(required == SIZE_MAX);
        } else {
            CHECK_COPY(codex_agent_conversation_settings_service_tier_copy,
                       context, settings, "tier");
        }
        CHECK(codex_agent_conversation_settings_destroy(context, &settings) ==
              CODEX_AGENT_STATUS_OK);
        CHECK(settings == NULL);
        CHECK(codex_agent_conversation_settings_destroy(context, &settings) ==
              CODEX_AGENT_STATUS_OK);
    }
    return 0;
}

static int verify_owned_nested_values(codex_agent_context_t *context) {
    uint8_t pending_bytes[] = "https://auth.openai.com/authorize?client=c";
    uint8_t device_bytes[] = "https://example.com/device";
    uint8_t code_bytes[] = "CODE-17";
    codex_agent_authorization_url_t *pending = NULL;
    codex_agent_authorization_url_t *device = NULL;
    codex_agent_failure_t *source_failure = NULL;
    codex_agent_authentication_state_t *state = NULL;
    codex_agent_authorization_url_t *first_pending = NULL;
    codex_agent_authorization_url_t *second_pending = NULL;
    codex_agent_authorization_url_t *projected_device = NULL;
    codex_agent_failure_t *first_failure = NULL;
    codex_agent_failure_t *second_failure = NULL;
    codex_agent_authorization_purpose_t purpose = INT32_MIN;
    int32_t present = INT32_MIN;
    int32_t recoverable = INT32_MIN;

    CHECK(codex_agent_authorization_url_chat_gpt(
              context,
              STRING_VIEW(pending_bytes, sizeof(pending_bytes) - 1u),
              &pending) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_authorization_url_external(
              context,
              STRING_VIEW(device_bytes, sizeof(device_bytes) - 1u),
              &device) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_failure_create(
              context, VIEW("auth_failed"), VIEW("Authentication failed"),
              INT32_C(1), &source_failure) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_authentication_state_create(
              context,
              CODEX_AGENT_AUTHENTICATION_STATUS_AUTHENTICATING,
              INT32_C(1),
              pending,
              INT32_C(1),
              device,
              INT32_C(1),
              STRING_VIEW(code_bytes, sizeof(code_bytes) - 1u),
              INT32_C(1),
              source_failure,
              &state) == CODEX_AGENT_STATUS_OK);
    pending_bytes[0] = (uint8_t)'X';
    device_bytes[0] = (uint8_t)'X';
    code_bytes[0] = (uint8_t)'X';
    CHECK(codex_agent_authorization_url_destroy(context, &pending) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_authorization_url_destroy(context, &device) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_failure_release(context, &source_failure) ==
          CODEX_AGENT_STATUS_OK);

    CHECK(codex_agent_authentication_state_has_pending_sign_in_url(
              context, state, &present) == CODEX_AGENT_STATUS_OK);
    CHECK(present == INT32_C(1));
    CHECK(codex_agent_authentication_state_has_device_verification_url(
              context, state, &present) == CODEX_AGENT_STATUS_OK);
    CHECK(present == INT32_C(1));
    CHECK(codex_agent_authentication_state_has_device_user_code(
              context, state, &present) == CODEX_AGENT_STATUS_OK);
    CHECK(present == INT32_C(1));
    CHECK(codex_agent_authentication_state_has_failure(context, state, &present) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(present == INT32_C(1));
    CHECK_COPY(codex_agent_authentication_state_device_user_code_copy,
               context, state, "CODE-17");
    CHECK(codex_agent_authentication_state_pending_sign_in_url(
              context, state, &first_pending) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_authentication_state_pending_sign_in_url(
              context, state, &second_pending) == CODEX_AGENT_STATUS_OK);
    CHECK(first_pending != second_pending);
    CHECK(codex_agent_authentication_state_device_verification_url(
              context, state, &projected_device) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_authentication_state_failure(context, state, &first_failure) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_authentication_state_failure(context, state, &second_failure) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(first_failure != second_failure);
    CHECK(codex_agent_authentication_state_destroy(context, &state) ==
          CODEX_AGENT_STATUS_OK);

    CHECK_COPY(codex_agent_authorization_url_value_copy, context, first_pending,
               "https://auth.openai.com/authorize?client=c");
    CHECK(codex_agent_authorization_url_purpose(context, first_pending, &purpose) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(purpose == CODEX_AGENT_AUTHORIZATION_PURPOSE_CHAT_GPT);
    CHECK_COPY(codex_agent_authorization_url_value_copy, context, second_pending,
               "https://auth.openai.com/authorize?client=c");
    CHECK_COPY(codex_agent_authorization_url_value_copy, context, projected_device,
               "https://example.com/device");
    CHECK(codex_agent_authorization_url_purpose(context, projected_device, &purpose) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(purpose == CODEX_AGENT_AUTHORIZATION_PURPOSE_EXTERNAL);
    CHECK_COPY(codex_agent_failure_code_copy, context, first_failure, "auth_failed");
    CHECK_COPY(codex_agent_failure_message_copy, context, second_failure,
               "Authentication failed");
    CHECK(codex_agent_failure_is_recoverable(context, second_failure, &recoverable) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(recoverable == INT32_C(1));
    CHECK(codex_agent_authorization_url_destroy(context, &first_pending) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_authorization_url_destroy(context, &second_pending) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_authorization_url_destroy(context, &projected_device) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_failure_release(context, &first_failure) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_failure_release(context, &second_failure) ==
          CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_client_info(codex_agent_context_t *context) {
    uint8_t name[] = "codex_c";
    uint8_t title[] = "Codex C";
    uint8_t version[] = "1.7";
    codex_agent_client_info_value_t *client = NULL;

    CHECK(codex_agent_client_info_value_create(
              context,
              STRING_VIEW(name, sizeof(name) - 1u),
              STRING_VIEW(title, sizeof(title) - 1u),
              STRING_VIEW(version, sizeof(version) - 1u),
              &client) == CODEX_AGENT_STATUS_OK);
    name[0] = (uint8_t)'X';
    title[0] = (uint8_t)'X';
    version[0] = (uint8_t)'X';
    CHECK_COPY(codex_agent_client_info_value_name_copy, context, client, "codex_c");
    CHECK_COPY(codex_agent_client_info_value_title_copy, context, client, "Codex C");
    CHECK_COPY(codex_agent_client_info_value_version_copy, context, client, "1.7");
    CHECK(codex_agent_client_info_value_destroy(context, &client) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(client == NULL);
    CHECK(codex_agent_client_info_value_destroy(context, &client) ==
          CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_fail_closed(
    codex_agent_context_t *context,
    codex_agent_context_t *other_context) {
    codex_agent_authorization_url_t *url = NULL;
    codex_agent_conversation_settings_t *settings = NULL;
    codex_agent_authentication_state_t *state = NULL;
    codex_agent_authentication_state_t *stale_state = NULL;
    codex_agent_authentication_state_t *invalid_state = NULL;
    codex_agent_client_info_value_t *client = NULL;
    codex_agent_authorization_url_t *occupied_url = NULL;
    int32_t projected = INT32_C(73);
    size_t required = SIZE_MAX;

    CHECK(codex_agent_authorization_url_external(
              context, VIEW("https://example.com/auth"), &url) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_conversation_settings_create(
              context, CODEX_AGENT_APPROVAL_PRESET_AUTO_REVIEW,
              INT32_C(0), EMPTY_VIEW, &settings) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_authentication_state_create(
              context,
              CODEX_AGENT_AUTHENTICATION_STATUS_SIGNED_OUT,
              INT32_C(1), url,
              INT32_C(0), NULL,
              INT32_C(0), EMPTY_VIEW,
              INT32_C(0), NULL,
              &state) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_client_info_value_create(
              context, VIEW("client"), VIEW("Client"), VIEW("1"), &client) ==
          CODEX_AGENT_STATUS_OK);

    CHECK(codex_agent_authentication_state_status(other_context, state, &projected) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(projected == INT32_C(73));
    CHECK(codex_agent_authentication_state_status(
              context, (codex_agent_authentication_state_t *)settings, &projected) ==
          CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(projected == INT32_C(73));
    CHECK(codex_agent_authorization_url_value_copy(
              context, (codex_agent_authorization_url_t *)client,
              NULL, 0u, &required) == CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE);
    CHECK(required == SIZE_MAX);
    occupied_url = (codex_agent_authorization_url_t *)client;
    CHECK(codex_agent_authentication_state_pending_sign_in_url(
              context, state, &occupied_url) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(occupied_url == (codex_agent_authorization_url_t *)client);

    CHECK(codex_agent_authentication_state_create(
              context, INT32_C(3), INT32_C(0), NULL, INT32_C(0), NULL,
              INT32_C(0), EMPTY_VIEW, INT32_C(0), NULL, &invalid_state) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid_state == NULL);
    CHECK(codex_agent_authentication_state_create(
              context, CODEX_AGENT_AUTHENTICATION_STATUS_SIGNED_OUT,
              INT32_C(2), NULL, INT32_C(0), NULL,
              INT32_C(0), EMPTY_VIEW, INT32_C(0), NULL, &invalid_state) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid_state == NULL);
    CHECK(codex_agent_authentication_state_create(
              context, CODEX_AGENT_AUTHENTICATION_STATUS_SIGNED_OUT,
              INT32_C(0), url, INT32_C(0), NULL,
              INT32_C(0), EMPTY_VIEW, INT32_C(0), NULL, &invalid_state) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(invalid_state == NULL);
    CHECK(codex_agent_authentication_state_create(
              other_context, CODEX_AGENT_AUTHENTICATION_STATUS_SIGNED_OUT,
              INT32_C(1), url, INT32_C(0), NULL,
              INT32_C(0), EMPTY_VIEW, INT32_C(0), NULL, &invalid_state) ==
          CODEX_AGENT_STATUS_WRONG_CONTEXT);
    CHECK(invalid_state == NULL);
    CHECK(codex_agent_conversation_settings_create(
              context, INT32_C(4), INT32_C(0), EMPTY_VIEW,
              &settings) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_authorization_url_chat_gpt(
              context, VIEW("http://openai.com/"), &occupied_url) ==
          CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(occupied_url == (codex_agent_authorization_url_t *)client);
    CHECK(codex_agent_client_info_value_create(
              context, VIEW(""), VIEW("Client"), VIEW("1"),
              &client) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);

    stale_state = state;
    CHECK(codex_agent_authentication_state_destroy(context, &state) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_authentication_state_destroy(context, &state) ==
          CODEX_AGENT_STATUS_OK);
    projected = INT32_C(83);
    CHECK(codex_agent_authentication_state_status(context, stale_state, &projected) ==
          CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(projected == INT32_C(83));
    CHECK(codex_agent_conversation_settings_destroy(context, &settings) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_authorization_url_destroy(context, &url) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_client_info_value_destroy(context, &client) ==
          CODEX_AGENT_STATUS_OK);
    return 0;
}

static int verify_context_teardown(void) {
    codex_agent_context_t *context = NULL;
    codex_agent_context_t *saved_context = NULL;
    codex_agent_authorization_url_t *url = NULL;
    codex_agent_authorization_url_t *saved_url = NULL;
    codex_agent_conversation_settings_t *settings = NULL;
    codex_agent_conversation_settings_t *saved_settings = NULL;
    codex_agent_authentication_state_t *state = NULL;
    codex_agent_authentication_state_t *saved_state = NULL;
    codex_agent_client_info_value_t *client = NULL;
    codex_agent_client_info_value_t *saved_client = NULL;
    int32_t projected = INT32_C(101);
    size_t required = SIZE_MAX;

    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_OK);
    saved_context = context;
    CHECK(codex_agent_authorization_url_external(
              context, VIEW("https://teardown.example"), &url) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_conversation_settings_create(
              context, CODEX_AGENT_APPROVAL_PRESET_STRICT,
              INT32_C(1), VIEW("fast"), &settings) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_authentication_state_create(
              context, CODEX_AGENT_AUTHENTICATION_STATUS_AUTHENTICATED,
              INT32_C(1), url, INT32_C(0), NULL,
              INT32_C(0), EMPTY_VIEW, INT32_C(0), NULL, &state) ==
          CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_client_info_value_create(
              context, VIEW("teardown"), VIEW("Teardown"), VIEW("1"), &client) ==
          CODEX_AGENT_STATUS_OK);
    saved_url = url;
    saved_settings = settings;
    saved_state = state;
    saved_client = client;
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(context == NULL);
    CHECK(codex_agent_authentication_state_status(
              saved_context, saved_state, &projected) == CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(projected == INT32_C(101));
    CHECK(codex_agent_conversation_settings_approval_preset(
              saved_context, saved_settings, &projected) ==
          CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(projected == INT32_C(101));
    CHECK(codex_agent_authorization_url_purpose(
              saved_context, saved_url, &projected) == CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(projected == INT32_C(101));
    CHECK(codex_agent_client_info_value_name_copy(
              saved_context, saved_client, NULL, 0u, &required) ==
          CODEX_AGENT_STATUS_STALE_HANDLE);
    CHECK(required == SIZE_MAX);
    return 0;
}

int main(void) {
    codex_agent_context_t *context = NULL;
    codex_agent_context_t *other_context = NULL;

    CHECK(CODEX_AGENT_AUTHENTICATION_STATUS_SIGNED_OUT == INT32_C(0));
    CHECK(CODEX_AGENT_AUTHENTICATION_STATUS_AUTHENTICATING == INT32_C(1));
    CHECK(CODEX_AGENT_AUTHENTICATION_STATUS_AUTHENTICATED == INT32_C(2));
    CHECK(CODEX_AGENT_APPROVAL_PRESET_NEVER == INT32_C(0));
    CHECK(CODEX_AGENT_APPROVAL_PRESET_AUTO_REVIEW == INT32_C(1));
    CHECK(CODEX_AGENT_APPROVAL_PRESET_ASK_ME == INT32_C(2));
    CHECK(CODEX_AGENT_APPROVAL_PRESET_STRICT == INT32_C(3));
    CHECK(CODEX_AGENT_AUTHORIZATION_PURPOSE_CHAT_GPT == INT32_C(0));
    CHECK(CODEX_AGENT_AUTHORIZATION_PURPOSE_EXTERNAL == INT32_C(1));

    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_create(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(verify_absent_states_and_settings(context) == 0);
    CHECK(verify_owned_nested_values(context) == 0);
    CHECK(verify_client_info(context) == 0);
    CHECK(verify_fail_closed(context, other_context) == 0);
    CHECK(codex_agent_context_destroy(&other_context) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(verify_context_teardown() == 0);
    return 0;
}
