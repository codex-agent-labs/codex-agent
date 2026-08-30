#include <codex_agent.h>

#include "leaf_native_probe.hpp"

#include <algorithm>
#include <array>
#include <cstring>
#include <map>
#include <memory>
#include <string>
#include <vector>

struct codex_agent_context {};
struct codex_agent_host { codex_agent_context_t* context; };
struct codex_agent_agent { codex_agent_context_t* context; };
#define LEAF_SERVICE(name) struct codex_agent_##name { codex_agent_context_t* context; };
LEAF_SERVICE(authentication)
LEAF_SERVICE(interactions)
LEAF_SERVICE(integration_authorization)
LEAF_SERVICE(models)
LEAF_SERVICE(skills)
LEAF_SERVICE(hooks)
LEAF_SERVICE(plugins)
LEAF_SERVICE(connectors)
LEAF_SERVICE(mcp_servers)
#undef LEAF_SERVICE

enum class operation_kind {
    void_, models, model, effort, tier, no_tier, skill_catalog, skill_chunk, skill,
    hook_catalog, hook, plugin_catalog, plugin_detail, plugin_install,
    connectors, mcp_servers, mcp_server,
};
struct codex_agent_operation {
    operation_kind kind = operation_kind::void_;
    bool cancelled = false;
};
enum class snapshot_kind {
    auth_state, authenticated, authenticating, authorization_state,
    authorization_active, authorizing, interaction_state, approvals,
    elicitations, host_state,
};
struct codex_agent_snapshot {
    snapshot_kind kind;
    int phase = 0;
    codex_agent_context_t* context = nullptr;
};
struct codex_agent_subscription {
    codex_agent_context_t* context;
    snapshot_kind kind;
    codex_agent_state_callback_t callback;
    void* user_data;
    bool active = true;
};
struct codex_agent_failure {
    std::string code = "fixture_failure";
    std::string message = "fixture failure";
    int32_t recoverable = 1;
};
struct codex_agent_authorization_url {
    std::string value;
    codex_agent_authorization_purpose_t purpose =
        CODEX_AGENT_AUTHORIZATION_PURPOSE_CHAT_GPT;
};
struct codex_agent_model {
    std::string id = "model";
    std::string default_effort = "medium";
    int32_t is_default = 1;
};
struct codex_agent_service_tier {};
struct codex_agent_skill {
    std::string name = "skill";
    std::string path = "/skill";
    codex_agent_skill_scope_t scope = CODEX_AGENT_SKILL_SCOPE_USER;
    int32_t is_enabled = 1;
};
struct codex_agent_skill_catalog {};
struct codex_agent_skill_chunk {};
struct codex_agent_hook {
    std::string key = "hook";
    std::string path = "/hook";
    int32_t is_enabled = 1;
    codex_agent_hook_trust_status_t trust = CODEX_AGENT_HOOK_TRUST_STATUS_TRUSTED;
};
struct codex_agent_hook_catalog {};
struct codex_agent_hook_handler {};
struct codex_agent_hook_handler_agent {};
struct codex_agent_hook_handler_prompt {};
struct codex_agent_hook_handler_command {};
struct codex_agent_hook_handler_mcp_tool {};
struct codex_agent_plugin_reference {
    std::string id = "plugin";
    std::string name = "plugin";
    std::string marketplace = "market";
};
struct codex_agent_plugin_catalog {};
struct codex_agent_plugin_summary {};
struct codex_agent_plugin_detail {};
struct codex_agent_plugin_install_result {};
struct codex_agent_plugin_skill {};
struct codex_agent_connector { std::string id = "connector"; };
struct codex_agent_mcp_server {
    std::string name = "server";
    std::string display_name = "Server";
    codex_agent_mcp_auth_status_t auth = CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN;
};
struct codex_agent_mcp_server_configuration {
    std::string name = "server";
    std::string url = "https://example.com";
};
struct codex_agent_mcp_transport { std::string url; };
struct codex_agent_mcp_transport_http { std::string url; };
struct codex_agent_mcp_transport_stdio {};
struct codex_agent_mcp_environment_variable {};
struct codex_agent_mcp_oauth_configuration {};
struct codex_agent_mcp_tool_configuration {};
struct codex_agent_integration { std::string id = "connector:connector"; };
struct codex_agent_integration_connector { std::string id = "connector:connector"; };
struct codex_agent_integration_mcp_server { std::string id = "mcp:server"; };
struct codex_agent_integration_authorization_state { int phase = 0; };
struct codex_agent_authentication_state { int phase = 0; };
struct codex_agent_authentication_method_api_key { std::string value; };
struct codex_agent_authentication_method_chat_gpt_browser {};
struct codex_agent_authentication_method_chat_gpt_device_code {};
struct codex_agent_conversation_id {};
struct codex_agent_pending_approval {
    std::string request_id = "approval";
    codex_agent_context_t* context = nullptr;
};
struct codex_agent_pending_elicitation {
    std::string request_id = "elicitation";
    codex_agent_context_t* context = nullptr;
};
struct codex_agent_pending_interaction { codex_agent_pending_interaction_kind_t kind = CODEX_AGENT_PENDING_INTERACTION_KIND_APPROVAL; };
struct codex_agent_interaction_state { int phase = 0; };
struct codex_agent_elicitation { std::string request_id = "elicitation"; };
struct codex_agent_elicitation_response {
    codex_agent_elicitation_action_t action = CODEX_AGENT_ELICITATION_ACTION_CANCEL;
    std::vector<std::string> keys;
};

namespace {
std::vector<LeafNativeEdge> native_events;
bool delay_next_operation = false;
std::array<int, 10> state_phases{};
struct PendingCompletion {
    codex_agent_context_t* context = nullptr;
    codex_agent_operation_t* operation = nullptr;
    codex_agent_operation_callback_t callback = nullptr;
    void* user_data = nullptr;
} pending_completion;
std::vector<codex_agent_subscription_t*> subscriptions;

std::string string_value(const codex_agent_string_view_t* value) {
    if (value == nullptr || (value->data == nullptr && value->size != 0)) {
        return {};
    }
    return {reinterpret_cast<const char*>(value->data), value->size};
}

codex_agent_status_t require_input(bool condition) {
    return condition ? CODEX_AGENT_STATUS_OK : CODEX_AGENT_STATUS_INVALID_ARGUMENT;
}

codex_agent_status_t copy(
    const std::string& value, std::uint8_t* buffer, std::size_t capacity,
    std::size_t* required) {
    if (required == nullptr) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *required = value.size();
    if (capacity < value.size()) return CODEX_AGENT_STATUS_BUFFER_TOO_SMALL;
    if (!value.empty()) std::memcpy(buffer, value.data(), value.size());
    return CODEX_AGENT_STATUS_OK;
}
template <typename T> codex_agent_status_t drop(T** value) {
    if (value == nullptr) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    delete *value;
    *value = nullptr;
    return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t complete(
    codex_agent_context_t* context, operation_kind kind,
    codex_agent_operation_callback_t callback, void* user_data,
    codex_agent_operation_t** out) {
    *out = new codex_agent_operation{kind};
    if (delay_next_operation) {
        delay_next_operation = false;
        pending_completion = {context, *out, callback, user_data};
        return CODEX_AGENT_STATUS_OK;
    }
    callback(context, *out, user_data);
    return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t publish(
    codex_agent_context_t* context, snapshot_kind kind,
    codex_agent_state_callback_t callback, void* user_data,
    codex_agent_subscription_t** out) {
    *out = new codex_agent_subscription{context, kind, callback, user_data};
    subscriptions.push_back(*out);
    callback(context, *out, CODEX_AGENT_STATUS_OK,
             new codex_agent_snapshot{kind, 0, context}, 0, user_data);
    return CODEX_AGENT_STATUS_OK;
}
}

void codex_agent_cpp_mock_leaf_record(LeafNativeEdge edge) {
    native_events.push_back(edge);
}

std::size_t codex_agent_cpp_mock_leaf_event_count() {
    return native_events.size();
}

LeafNativeEdge codex_agent_cpp_mock_leaf_event_at(std::size_t index) {
    return native_events.at(index);
}

extern "C" {

void codex_agent_cpp_mock_leaf_delay_next_operation() {
    delay_next_operation = true;
}

void codex_agent_cpp_mock_leaf_complete_pending_operation() {
    if (pending_completion.callback == nullptr) return;
    const auto completion = pending_completion;
    pending_completion = {};
    completion.callback(
        completion.context, completion.operation, completion.user_data);
}

void codex_agent_cpp_mock_leaf_publish_state(int kind, int terminal) {
    const auto wanted = static_cast<snapshot_kind>(kind);
    for (auto* subscription : subscriptions) {
        if (subscription == nullptr || !subscription->active ||
            subscription->kind != wanted) {
            continue;
        }
        subscription->callback(
            subscription->context, subscription, CODEX_AGENT_STATUS_OK,
            terminal != 0 ? nullptr
                          : new codex_agent_snapshot{
                                subscription->kind, 1,
                                subscription->context},
            terminal, subscription->user_data);
    }
}

void codex_agent_cpp_mock_leaf_set_current_state(int kind, int phase) {
    state_phases.at(static_cast<std::size_t>(kind)) = phase;
}

codex_agent_status_t codex_agent_context_create(codex_agent_context_t** out) {
    *out = new codex_agent_context{}; return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_context_destroy(codex_agent_context_t** value) { return drop(value); }
codex_agent_status_t codex_agent_host_create(
    codex_agent_context_t* context, const codex_agent_host_options_t*,
    codex_agent_host_t** out) {
    *out = new codex_agent_host{context};
    return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_host_retain(
    codex_agent_context_t*, codex_agent_host_t* value,
    codex_agent_host_t** out) {
    *out = new codex_agent_host{value->context};
    return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_host_release(
    codex_agent_context_t*, codex_agent_host_t** value) {
    return drop(value);
}
codex_agent_status_t codex_agent_host_state_get(
    codex_agent_context_t*, codex_agent_host_t*, codex_agent_snapshot_t** out) {
    *out = new codex_agent_snapshot{snapshot_kind::host_state, 0, nullptr};
    return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_host_state_agent(
    codex_agent_context_t*, codex_agent_host_t* host,
    codex_agent_snapshot_t* snapshot, codex_agent_agent_t** out) {
    if (host == nullptr || snapshot == nullptr ||
        snapshot->kind != snapshot_kind::host_state) {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    *out = new codex_agent_agent{host->context};
    return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_agent_release(
    codex_agent_context_t*, codex_agent_agent_t** value) {
    return drop(value);
}
codex_agent_status_t codex_agent_agent_retain(
    codex_agent_context_t*, codex_agent_agent_t* value,
    codex_agent_agent_t** out) {
    *out = new codex_agent_agent{value->context};
    return CODEX_AGENT_STATUS_OK;
}
codex_agent_status_t codex_agent_snapshot_destroy(codex_agent_context_t*, codex_agent_snapshot_t** value) { return drop(value); }
codex_agent_status_t codex_agent_subscription_destroy(codex_agent_context_t*, codex_agent_subscription_t** value) {
    if (value == nullptr || *value == nullptr) {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    (*value)->active = false;
    const auto found = std::find(subscriptions.begin(), subscriptions.end(), *value);
    if (found != subscriptions.end()) *found = nullptr;
    return drop(value);
}
codex_agent_status_t codex_agent_operation_destroy(codex_agent_context_t*, codex_agent_operation_t** value) { return drop(value); }
codex_agent_status_t codex_agent_operation_cancel(codex_agent_context_t*, codex_agent_operation_t* operation) { codex_agent_cpp_mock_leaf_record(LeafNativeEdge::codex_agent_operation_cancel); operation->cancelled = true; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_operation_result(codex_agent_context_t*, codex_agent_operation_t* operation, codex_agent_status_t* out) { codex_agent_cpp_mock_leaf_record(LeafNativeEdge::codex_agent_operation_result); *out = operation->cancelled ? CODEX_AGENT_STATUS_CANCELLED : CODEX_AGENT_STATUS_OK; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_operation_failure(codex_agent_context_t*, codex_agent_operation_t*, codex_agent_failure_t**) { return CODEX_AGENT_STATUS_NOT_READY; }

void codex_agent_cpp_mock_leaf_handles(
    codex_agent_context_t* context,
    codex_agent_authentication_t** authentication,
    codex_agent_interactions_t** interactions,
    codex_agent_integration_authorization_t** authorization,
    codex_agent_models_t** models, codex_agent_skills_t** skills,
    codex_agent_hooks_t** hooks, codex_agent_plugins_t** plugins,
    codex_agent_connectors_t** connectors,
    codex_agent_mcp_servers_t** mcp_servers) {
    *authentication = new codex_agent_authentication{context};
    *interactions = new codex_agent_interactions{context};
    *authorization = new codex_agent_integration_authorization{context};
    *models = new codex_agent_models{context};
    *skills = new codex_agent_skills{context};
    *hooks = new codex_agent_hooks{context};
    *plugins = new codex_agent_plugins{context};
    *connectors = new codex_agent_connectors{context};
    *mcp_servers = new codex_agent_mcp_servers{context};
}

#define AGENT_SERVICE(name)                                                \
codex_agent_status_t codex_agent_agent_##name(                             \
    codex_agent_context_t*, codex_agent_agent_t* agent,                    \
    codex_agent_##name##_t** out) {                                        \
    if (agent == nullptr || out == nullptr)                                \
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;                        \
    *out = new codex_agent_##name{agent->context};                         \
    return CODEX_AGENT_STATUS_OK;                                          \
}
AGENT_SERVICE(authentication)
AGENT_SERVICE(interactions)
AGENT_SERVICE(integration_authorization)
AGENT_SERVICE(models)
AGENT_SERVICE(skills)
AGENT_SERVICE(hooks)
AGENT_SERVICE(plugins)
AGENT_SERVICE(connectors)
AGENT_SERVICE(mcp_servers)
#undef AGENT_SERVICE

#define RETAIN_RELEASE(name) \
codex_agent_status_t codex_agent_##name##_retain(codex_agent_context_t*, codex_agent_##name##_t* value, codex_agent_##name##_t** out) { *out = new codex_agent_##name{value->context}; return CODEX_AGENT_STATUS_OK; } \
codex_agent_status_t codex_agent_##name##_release(codex_agent_context_t*, codex_agent_##name##_t** value) { return drop(value); }
RETAIN_RELEASE(authentication)
RETAIN_RELEASE(interactions)
RETAIN_RELEASE(integration_authorization)
RETAIN_RELEASE(models)
RETAIN_RELEASE(skills)
RETAIN_RELEASE(hooks)
RETAIN_RELEASE(plugins)
RETAIN_RELEASE(connectors)
RETAIN_RELEASE(mcp_servers)
#undef RETAIN_RELEASE

#define AVAILABLE(name) codex_agent_status_t codex_agent_##name##_is_available(codex_agent_context_t*, codex_agent_##name##_t*, int32_t* out) { codex_agent_cpp_mock_leaf_record(LeafNativeEdge::codex_agent_##name##_is_available); *out = 1; return CODEX_AGENT_STATUS_OK; }
AVAILABLE(skills)
AVAILABLE(hooks)
AVAILABLE(plugins)
AVAILABLE(connectors)
AVAILABLE(mcp_servers)
#undef AVAILABLE

#define VOID_OPERATION(name, type) codex_agent_status_t name(codex_agent_context_t* context, type*, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { codex_agent_cpp_mock_leaf_record(LeafNativeEdge::name); return complete(context, operation_kind::void_, callback, user_data, out); }
VOID_OPERATION(codex_agent_authentication_cancel, codex_agent_authentication_t)
VOID_OPERATION(codex_agent_authentication_sign_out, codex_agent_authentication_t)
VOID_OPERATION(codex_agent_integration_authorization_cancel, codex_agent_integration_authorization_t)
#undef VOID_OPERATION

#define AUTH_METHOD_CREATE(name, type) \
codex_agent_status_t codex_agent_authentication_method_##name##_create(codex_agent_context_t*, type** out) { *out = new type{}; return CODEX_AGENT_STATUS_OK; } \
codex_agent_status_t codex_agent_authentication_method_##name##_destroy(codex_agent_context_t*, type** value) { return drop(value); }
codex_agent_status_t codex_agent_authentication_method_api_key_create(codex_agent_context_t*, const codex_agent_string_view_t* value, codex_agent_authentication_method_api_key_t** out) { *out = new codex_agent_authentication_method_api_key{string_value(value)}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_authentication_method_api_key_destroy(codex_agent_context_t*, codex_agent_authentication_method_api_key_t** value) { return drop(value); }
AUTH_METHOD_CREATE(chat_gpt_browser, codex_agent_authentication_method_chat_gpt_browser_t)
AUTH_METHOD_CREATE(chat_gpt_device_code, codex_agent_authentication_method_chat_gpt_device_code_t)
#undef AUTH_METHOD_CREATE
codex_agent_status_t codex_agent_authentication_authenticate_api_key(codex_agent_context_t* context, codex_agent_authentication_t*, codex_agent_authentication_method_api_key_t* method, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { codex_agent_cpp_mock_leaf_record(LeafNativeEdge::codex_agent_authentication_authenticate_api_key); if (require_input(method != nullptr && method->value == "key") != CODEX_AGENT_STATUS_OK) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; return complete(context, operation_kind::void_, callback, user_data, out); }
#define AUTH_OPERATION(name, type) codex_agent_status_t codex_agent_authentication_authenticate_##name(codex_agent_context_t* context, codex_agent_authentication_t*, type* method, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { codex_agent_cpp_mock_leaf_record(LeafNativeEdge::codex_agent_authentication_authenticate_##name); if (require_input(method != nullptr) != CODEX_AGENT_STATUS_OK) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; return complete(context, operation_kind::void_, callback, user_data, out); }
AUTH_OPERATION(chat_gpt_browser, codex_agent_authentication_method_chat_gpt_browser_t)
AUTH_OPERATION(chat_gpt_device_code, codex_agent_authentication_method_chat_gpt_device_code_t)
#undef AUTH_OPERATION

#define SNAPSHOT_GET(name, type, kind) codex_agent_status_t name(codex_agent_context_t* context, type*, codex_agent_snapshot_t** out) { codex_agent_cpp_mock_leaf_record(LeafNativeEdge::name); *out = new codex_agent_snapshot{snapshot_kind::kind, state_phases.at(static_cast<std::size_t>(snapshot_kind::kind)), context}; return CODEX_AGENT_STATUS_OK; }
#define SNAPSHOT_SUB(name, type, kind) codex_agent_status_t name(codex_agent_context_t* context, type*, codex_agent_state_callback_t callback, void* user_data, codex_agent_subscription_t** out) { codex_agent_cpp_mock_leaf_record(LeafNativeEdge::name); return publish(context, snapshot_kind::kind, callback, user_data, out); }
SNAPSHOT_GET(codex_agent_authentication_state_get, codex_agent_authentication_t, auth_state)
SNAPSHOT_SUB(codex_agent_authentication_state_subscribe, codex_agent_authentication_t, auth_state)
SNAPSHOT_GET(codex_agent_authentication_is_authenticated_get, codex_agent_authentication_t, authenticated)
SNAPSHOT_SUB(codex_agent_authentication_is_authenticated_subscribe, codex_agent_authentication_t, authenticated)
SNAPSHOT_GET(codex_agent_authentication_is_authenticating_get, codex_agent_authentication_t, authenticating)
SNAPSHOT_SUB(codex_agent_authentication_is_authenticating_subscribe, codex_agent_authentication_t, authenticating)
SNAPSHOT_GET(codex_agent_integration_authorization_state_get, codex_agent_integration_authorization_t, authorization_state)
SNAPSHOT_SUB(codex_agent_integration_authorization_state_subscribe, codex_agent_integration_authorization_t, authorization_state)
SNAPSHOT_GET(codex_agent_integration_authorization_active_get, codex_agent_integration_authorization_t, authorization_active)
SNAPSHOT_SUB(codex_agent_integration_authorization_active_subscribe, codex_agent_integration_authorization_t, authorization_active)
SNAPSHOT_GET(codex_agent_integration_authorization_is_authorizing_get, codex_agent_integration_authorization_t, authorizing)
SNAPSHOT_SUB(codex_agent_integration_authorization_is_authorizing_subscribe, codex_agent_integration_authorization_t, authorizing)
SNAPSHOT_GET(codex_agent_interactions_state_get, codex_agent_interactions_t, interaction_state)
SNAPSHOT_SUB(codex_agent_interactions_state_subscribe, codex_agent_interactions_t, interaction_state)
SNAPSHOT_GET(codex_agent_interactions_approvals_get, codex_agent_interactions_t, approvals)
SNAPSHOT_SUB(codex_agent_interactions_approvals_subscribe, codex_agent_interactions_t, approvals)
SNAPSHOT_GET(codex_agent_interactions_elicitations_get, codex_agent_interactions_t, elicitations)
SNAPSHOT_SUB(codex_agent_interactions_elicitations_subscribe, codex_agent_interactions_t, elicitations)
#undef SNAPSHOT_GET
#undef SNAPSHOT_SUB
codex_agent_status_t codex_agent_state_boolean_value(codex_agent_context_t*, codex_agent_snapshot_t* snapshot, int32_t* out) { codex_agent_cpp_mock_leaf_record(LeafNativeEdge::codex_agent_state_boolean_value); if (snapshot->kind == snapshot_kind::authenticated) *out = snapshot->phase == 0 ? 1 : 0; else *out = snapshot->phase == 0 ? 0 : 1; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_authentication_state_value(codex_agent_context_t*, codex_agent_snapshot_t* snapshot, codex_agent_authentication_state_t** out) { codex_agent_cpp_mock_leaf_record(LeafNativeEdge::codex_agent_authentication_state_value); *out = new codex_agent_authentication_state{snapshot->phase}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_authentication_state_destroy(codex_agent_context_t*, codex_agent_authentication_state_t** value) { return drop(value); }
codex_agent_status_t codex_agent_authentication_state_status(codex_agent_context_t*, codex_agent_authentication_state_t* state, codex_agent_authentication_status_t* out) { *out = state->phase == 0 ? CODEX_AGENT_AUTHENTICATION_STATUS_AUTHENTICATED : CODEX_AGENT_AUTHENTICATION_STATUS_SIGNED_OUT; return CODEX_AGENT_STATUS_OK; }
#define AUTH_PRESENT(name) codex_agent_status_t name(codex_agent_context_t*, codex_agent_authentication_state_t* state, int32_t* out) { *out = state->phase == 0 ? 1 : 0; return CODEX_AGENT_STATUS_OK; }
AUTH_PRESENT(codex_agent_authentication_state_has_pending_sign_in_url)
AUTH_PRESENT(codex_agent_authentication_state_has_device_verification_url)
AUTH_PRESENT(codex_agent_authentication_state_has_device_user_code)
AUTH_PRESENT(codex_agent_authentication_state_has_failure)
#undef AUTH_PRESENT
codex_agent_status_t codex_agent_authentication_state_pending_sign_in_url(codex_agent_context_t*, codex_agent_authentication_state_t*, codex_agent_authorization_url_t** out) { *out = new codex_agent_authorization_url{"https://sign-in.example", CODEX_AGENT_AUTHORIZATION_PURPOSE_CHAT_GPT}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_authentication_state_device_verification_url(codex_agent_context_t*, codex_agent_authentication_state_t*, codex_agent_authorization_url_t** out) { *out = new codex_agent_authorization_url{"https://verify.example", CODEX_AGENT_AUTHORIZATION_PURPOSE_CHAT_GPT}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_authentication_state_device_user_code_copy(codex_agent_context_t*, codex_agent_authentication_state_t*, uint8_t* b, size_t n, size_t* r) { return copy("ABCD-EFGH", b, n, r); }
codex_agent_status_t codex_agent_authentication_state_failure(codex_agent_context_t*, codex_agent_authentication_state_t*, codex_agent_failure_t** out) { *out = new codex_agent_failure{}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_authorization_url_destroy(codex_agent_context_t*, codex_agent_authorization_url_t** value) { return drop(value); }
codex_agent_status_t codex_agent_authorization_url_value_copy(codex_agent_context_t*, codex_agent_authorization_url_t* value, uint8_t* b, size_t n, size_t* r) { return copy(value->value, b, n, r); }
codex_agent_status_t codex_agent_authorization_url_purpose(codex_agent_context_t*, codex_agent_authorization_url_t* value, codex_agent_authorization_purpose_t* out) { *out = value->purpose; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_failure_release(codex_agent_context_t*, codex_agent_failure_t** value) { return drop(value); }
codex_agent_status_t codex_agent_failure_code_copy(codex_agent_context_t*, codex_agent_failure_t* value, uint8_t* b, size_t n, size_t* r) { return copy(value->code, b, n, r); }
codex_agent_status_t codex_agent_failure_message_copy(codex_agent_context_t*, codex_agent_failure_t* value, uint8_t* b, size_t n, size_t* r) { return copy(value->message, b, n, r); }
codex_agent_status_t codex_agent_failure_is_recoverable(codex_agent_context_t*, codex_agent_failure_t* value, int32_t* out) { *out = value->recoverable; return CODEX_AGENT_STATUS_OK; }

#define START0(name, service, kind) codex_agent_status_t name(codex_agent_context_t* context, service*, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { codex_agent_cpp_mock_leaf_record(LeafNativeEdge::name); return complete(context, operation_kind::kind, callback, user_data, out); }
START0(codex_agent_models_list, codex_agent_models_t, models)
START0(codex_agent_hooks_list, codex_agent_hooks_t, hook_catalog)
START0(codex_agent_mcp_servers_list, codex_agent_mcp_servers_t, mcp_servers)
#undef START0
#define RECORD_START(function) codex_agent_cpp_mock_leaf_record(LeafNativeEdge::function)
codex_agent_status_t codex_agent_models_resolve(codex_agent_context_t* context, codex_agent_models_t*, codex_agent_resolution_t resolution, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { RECORD_START(codex_agent_models_resolve); if (resolution != CODEX_AGENT_RESOLUTION_PREFERRED) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; return complete(context, operation_kind::model, callback, user_data, out); }
codex_agent_status_t codex_agent_models_resolve_effort(codex_agent_context_t* context, codex_agent_models_t*, codex_agent_model_t* model, codex_agent_resolution_t resolution, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { RECORD_START(codex_agent_models_resolve_effort); if (model == nullptr || model->id != "model" || model->default_effort != "medium" || model->is_default != 1 || resolution != CODEX_AGENT_RESOLUTION_PREFERRED) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; return complete(context, operation_kind::effort, callback, user_data, out); }
codex_agent_status_t codex_agent_models_resolve_service_tier(codex_agent_context_t* context, codex_agent_models_t*, codex_agent_model_t* model, codex_agent_resolution_t resolution, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { RECORD_START(codex_agent_models_resolve_service_tier); if (model == nullptr || model->id != "model" || model->default_effort != "medium" || model->is_default != 1 || (resolution != CODEX_AGENT_RESOLUTION_PREFERRED && resolution != CODEX_AGENT_RESOLUTION_FIRST)) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; return complete(context, resolution == CODEX_AGENT_RESOLUTION_PREFERRED ? operation_kind::tier : operation_kind::no_tier, callback, user_data, out); }
codex_agent_status_t codex_agent_skills_list(codex_agent_context_t* context, codex_agent_skills_t*, int32_t force_reload, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { RECORD_START(codex_agent_skills_list); if (force_reload != 1) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; return complete(context, operation_kind::skill_catalog, callback, user_data, out); }
codex_agent_status_t codex_agent_skills_read(codex_agent_context_t* context, codex_agent_skills_t*, const codex_agent_string_view_t* path, int64_t offset, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { RECORD_START(codex_agent_skills_read); if (string_value(path) != "/skill" || offset != 7) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; return complete(context, operation_kind::skill_chunk, callback, user_data, out); }
codex_agent_status_t codex_agent_skills_install(codex_agent_context_t* context, codex_agent_skills_t*, const codex_agent_string_view_t* path, codex_agent_installation_scope_t scope, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { RECORD_START(codex_agent_skills_install); if (string_value(path) != "/skill" || scope != CODEX_AGENT_INSTALLATION_SCOPE_USER) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; return complete(context, operation_kind::skill, callback, user_data, out); }
codex_agent_status_t codex_agent_skills_uninstall(codex_agent_context_t* context, codex_agent_skills_t*, codex_agent_skill_t* skill, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { RECORD_START(codex_agent_skills_uninstall); if (skill == nullptr || skill->name != "skill" || skill->path != "/skill" || skill->scope != CODEX_AGENT_SKILL_SCOPE_USER || skill->is_enabled != 1) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; return complete(context, operation_kind::void_, callback, user_data, out); }
codex_agent_status_t codex_agent_hooks_install(codex_agent_context_t* context, codex_agent_hooks_t*, const codex_agent_string_view_t* path, codex_agent_installation_scope_t scope, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { RECORD_START(codex_agent_hooks_install); if (string_value(path) != "/hook" || scope != CODEX_AGENT_INSTALLATION_SCOPE_USER) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; return complete(context, operation_kind::hook, callback, user_data, out); }
codex_agent_status_t codex_agent_hooks_uninstall(codex_agent_context_t* context, codex_agent_hooks_t*, codex_agent_hook_t* hook, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { RECORD_START(codex_agent_hooks_uninstall); if (hook == nullptr || hook->key != "hook" || hook->path != "/hook" || hook->is_enabled != 1 || hook->trust != CODEX_AGENT_HOOK_TRUST_STATUS_TRUSTED) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; return complete(context, operation_kind::void_, callback, user_data, out); }
codex_agent_status_t codex_agent_hooks_trust(codex_agent_context_t* context, codex_agent_hooks_t*, codex_agent_hook_t* hook, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { RECORD_START(codex_agent_hooks_trust); if (hook == nullptr || hook->key != "hook" || hook->path != "/hook" || hook->is_enabled != 1 || hook->trust != CODEX_AGENT_HOOK_TRUST_STATUS_TRUSTED) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; return complete(context, operation_kind::void_, callback, user_data, out); }
codex_agent_status_t codex_agent_plugins_list(codex_agent_context_t* context, codex_agent_plugins_t*, int32_t force_reload, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { RECORD_START(codex_agent_plugins_list); if (force_reload != 1) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; return complete(context, operation_kind::plugin_catalog, callback, user_data, out); }
#define PLUGIN_START(function, kind) codex_agent_status_t function(codex_agent_context_t* context, codex_agent_plugins_t*, codex_agent_plugin_reference_t* plugin, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { RECORD_START(function); if (plugin == nullptr || plugin->id != "plugin" || plugin->name != "plugin" || plugin->marketplace != "market") return CODEX_AGENT_STATUS_INVALID_ARGUMENT; return complete(context, operation_kind::kind, callback, user_data, out); }
PLUGIN_START(codex_agent_plugins_read, plugin_detail)
PLUGIN_START(codex_agent_plugins_install, plugin_install)
PLUGIN_START(codex_agent_plugins_uninstall, void_)
#undef PLUGIN_START
codex_agent_status_t codex_agent_connectors_list(codex_agent_context_t* context, codex_agent_connectors_t*, int32_t force_reload, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { RECORD_START(codex_agent_connectors_list); if (force_reload != 1) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; return complete(context, operation_kind::connectors, callback, user_data, out); }
codex_agent_status_t codex_agent_mcp_servers_add(codex_agent_context_t* context, codex_agent_mcp_servers_t*, codex_agent_mcp_server_configuration_t* configuration, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { RECORD_START(codex_agent_mcp_servers_add); if (configuration == nullptr || configuration->name != "server" || configuration->url != "https://example.com") return CODEX_AGENT_STATUS_INVALID_ARGUMENT; return complete(context, operation_kind::mcp_server, callback, user_data, out); }
codex_agent_status_t codex_agent_mcp_servers_remove(codex_agent_context_t* context, codex_agent_mcp_servers_t*, codex_agent_mcp_server_t* server, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { RECORD_START(codex_agent_mcp_servers_remove); if (server == nullptr || server->name != "server" || server->display_name != "Server" || server->auth != CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; return complete(context, operation_kind::void_, callback, user_data, out); }

#define COUNTED_OUTPUT(name, type) codex_agent_status_t name(codex_agent_context_t*, codex_agent_operation_t*, type** out) { RECORD_START(name); *out = new type{}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_operation_models_count(codex_agent_context_t*, codex_agent_operation_t*, size_t* out) { RECORD_START(codex_agent_operation_models_count); *out = 2; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_operation_model_at(codex_agent_context_t*, codex_agent_operation_t*, size_t, codex_agent_model_t** out) { RECORD_START(codex_agent_operation_model_at); *out = new codex_agent_model{}; return CODEX_AGENT_STATUS_OK; }
COUNTED_OUTPUT(codex_agent_operation_model, codex_agent_model_t)
codex_agent_status_t codex_agent_operation_string_copy(codex_agent_context_t*, codex_agent_operation_t*, uint8_t* b, size_t n, size_t* r) { RECORD_START(codex_agent_operation_string_copy); return copy("medium", b, n, r); }
codex_agent_status_t codex_agent_operation_has_service_tier(codex_agent_context_t*, codex_agent_operation_t* operation, int32_t* out) { RECORD_START(codex_agent_operation_has_service_tier); *out = operation->kind == operation_kind::tier ? 1 : 0; return CODEX_AGENT_STATUS_OK; }
COUNTED_OUTPUT(codex_agent_operation_service_tier, codex_agent_service_tier_t)
COUNTED_OUTPUT(codex_agent_operation_skill_catalog, codex_agent_skill_catalog_t)
COUNTED_OUTPUT(codex_agent_operation_skill_chunk, codex_agent_skill_chunk_t)
COUNTED_OUTPUT(codex_agent_operation_skill, codex_agent_skill_t)
COUNTED_OUTPUT(codex_agent_operation_hook_catalog, codex_agent_hook_catalog_t)
COUNTED_OUTPUT(codex_agent_operation_hook, codex_agent_hook_t)
COUNTED_OUTPUT(codex_agent_operation_plugin_catalog, codex_agent_plugin_catalog_t)
COUNTED_OUTPUT(codex_agent_operation_plugin_detail, codex_agent_plugin_detail_t)
COUNTED_OUTPUT(codex_agent_operation_plugin_install_result, codex_agent_plugin_install_result_t)
codex_agent_status_t codex_agent_operation_connectors_count(codex_agent_context_t*, codex_agent_operation_t*, size_t* out) { RECORD_START(codex_agent_operation_connectors_count); *out = 2; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_operation_connector_at(codex_agent_context_t*, codex_agent_operation_t*, size_t, codex_agent_connector_t** out) { RECORD_START(codex_agent_operation_connector_at); *out = new codex_agent_connector{}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_operation_mcp_servers_count(codex_agent_context_t*, codex_agent_operation_t*, size_t* out) { RECORD_START(codex_agent_operation_mcp_servers_count); *out = 2; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_operation_mcp_server_at(codex_agent_context_t*, codex_agent_operation_t*, size_t, codex_agent_mcp_server_t** out) { RECORD_START(codex_agent_operation_mcp_server_at); *out = new codex_agent_mcp_server{}; return CODEX_AGENT_STATUS_OK; }
COUNTED_OUTPUT(codex_agent_operation_mcp_server, codex_agent_mcp_server_t)
#undef COUNTED_OUTPUT

#define SIMPLE_DESTROY(name) codex_agent_status_t codex_agent_##name##_destroy(codex_agent_context_t*, codex_agent_##name##_t** value) { return drop(value); }
SIMPLE_DESTROY(model)
SIMPLE_DESTROY(service_tier)
SIMPLE_DESTROY(skill)
SIMPLE_DESTROY(skill_catalog)
SIMPLE_DESTROY(skill_chunk)
SIMPLE_DESTROY(hook)
SIMPLE_DESTROY(hook_catalog)
SIMPLE_DESTROY(hook_handler)
SIMPLE_DESTROY(plugin_reference)
SIMPLE_DESTROY(plugin_catalog)
SIMPLE_DESTROY(plugin_summary)
SIMPLE_DESTROY(plugin_detail)
SIMPLE_DESTROY(plugin_install_result)
SIMPLE_DESTROY(plugin_skill)
SIMPLE_DESTROY(connector)
SIMPLE_DESTROY(mcp_server)
SIMPLE_DESTROY(mcp_server_configuration)
SIMPLE_DESTROY(mcp_transport)
SIMPLE_DESTROY(mcp_transport_http)
SIMPLE_DESTROY(mcp_transport_stdio)
SIMPLE_DESTROY(mcp_environment_variable)
SIMPLE_DESTROY(mcp_oauth_configuration)
SIMPLE_DESTROY(mcp_tool_configuration)
SIMPLE_DESTROY(integration)
SIMPLE_DESTROY(integration_connector)
SIMPLE_DESTROY(integration_mcp_server)
SIMPLE_DESTROY(integration_authorization_state)
SIMPLE_DESTROY(conversation_id)
SIMPLE_DESTROY(pending_approval)
SIMPLE_DESTROY(pending_elicitation)
SIMPLE_DESTROY(pending_interaction)
SIMPLE_DESTROY(interaction_state)
SIMPLE_DESTROY(elicitation)
SIMPLE_DESTROY(elicitation_response)
#undef SIMPLE_DESTROY

#define TEXT_ACCESSOR(name, type, value) codex_agent_status_t name(codex_agent_context_t*, type*, uint8_t* b, size_t n, size_t* r) { return copy(value, b, n, r); }
TEXT_ACCESSOR(codex_agent_service_tier_id_copy, codex_agent_service_tier_t, "fast")
TEXT_ACCESSOR(codex_agent_service_tier_name_copy, codex_agent_service_tier_t, "Fast")
TEXT_ACCESSOR(codex_agent_service_tier_description_copy, codex_agent_service_tier_t, "Fast tier")
TEXT_ACCESSOR(codex_agent_model_id_copy, codex_agent_model_t, "model")
TEXT_ACCESSOR(codex_agent_model_display_name_copy, codex_agent_model_t, "Model")
TEXT_ACCESSOR(codex_agent_model_description_copy, codex_agent_model_t, "description")
TEXT_ACCESSOR(codex_agent_model_default_effort_copy, codex_agent_model_t, "medium")
codex_agent_status_t codex_agent_model_supported_efforts_count(codex_agent_context_t*, codex_agent_model_t*, size_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_model_is_default(codex_agent_context_t*, codex_agent_model_t*, int32_t* out) { *out = 1; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_model_service_tiers_count(codex_agent_context_t*, codex_agent_model_t*, size_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_model_has_default_service_tier(codex_agent_context_t*, codex_agent_model_t*, int32_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_model_create(codex_agent_context_t*, const codex_agent_string_view_t* id, const codex_agent_string_view_t*, const codex_agent_string_view_t*, const codex_agent_string_view_t*, size_t, const codex_agent_string_view_t* default_effort, int32_t is_default, codex_agent_service_tier_t* const*, size_t, int32_t, const codex_agent_string_view_t*, codex_agent_model_t** out) { *out = new codex_agent_model{string_value(id), string_value(default_effort), is_default}; return CODEX_AGENT_STATUS_OK; }

TEXT_ACCESSOR(codex_agent_skill_name_copy, codex_agent_skill_t, "skill")
TEXT_ACCESSOR(codex_agent_skill_display_name_copy, codex_agent_skill_t, "Skill")
TEXT_ACCESSOR(codex_agent_skill_description_copy, codex_agent_skill_t, "description")
TEXT_ACCESSOR(codex_agent_skill_path_copy, codex_agent_skill_t, "/skill")
codex_agent_status_t codex_agent_skill_scope(codex_agent_context_t*, codex_agent_skill_t*, codex_agent_skill_scope_t* out) { *out = CODEX_AGENT_SKILL_SCOPE_USER; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_skill_is_enabled(codex_agent_context_t*, codex_agent_skill_t*, int32_t* out) { *out = 1; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_skill_has_brand_color(codex_agent_context_t*, codex_agent_skill_t*, int32_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_skill_dependencies_count(codex_agent_context_t*, codex_agent_skill_t*, size_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_skill_can_uninstall(codex_agent_context_t*, codex_agent_skill_t*, int32_t* out) { *out = 1; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_skill_origin(codex_agent_context_t*, codex_agent_skill_t*, codex_agent_resource_origin_t* out) { *out = CODEX_AGENT_RESOURCE_ORIGIN_USER; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_skill_create(codex_agent_context_t*, const codex_agent_string_view_t* name, const codex_agent_string_view_t*, const codex_agent_string_view_t*, const codex_agent_string_view_t* path, codex_agent_skill_scope_t scope, int32_t is_enabled, int32_t, const codex_agent_string_view_t*, const codex_agent_string_view_t*, size_t, int32_t, int32_t, codex_agent_resource_origin_t, codex_agent_skill_t** out) { *out = new codex_agent_skill{string_value(name), string_value(path), scope, is_enabled}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_skill_catalog_skills_count(codex_agent_context_t*, codex_agent_skill_catalog_t*, size_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_skill_catalog_errors_count(codex_agent_context_t*, codex_agent_skill_catalog_t*, size_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
TEXT_ACCESSOR(codex_agent_skill_chunk_content_copy, codex_agent_skill_chunk_t, "chunk")
codex_agent_status_t codex_agent_skill_chunk_next_offset(codex_agent_context_t*, codex_agent_skill_chunk_t*, int32_t* present, int64_t* out) { *present = 0; *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_skill_chunk_total_bytes(codex_agent_context_t*, codex_agent_skill_chunk_t*, int64_t* out) { *out = 5; return CODEX_AGENT_STATUS_OK; }

codex_agent_status_t codex_agent_hook_catalog_hooks_count(codex_agent_context_t*, codex_agent_hook_catalog_t*, size_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_hook_catalog_warnings_count(codex_agent_context_t*, codex_agent_hook_catalog_t*, size_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_hook_catalog_errors_count(codex_agent_context_t*, codex_agent_hook_catalog_t*, size_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
TEXT_ACCESSOR(codex_agent_hook_key_copy, codex_agent_hook_t, "hook")
TEXT_ACCESSOR(codex_agent_hook_event_name_copy, codex_agent_hook_t, "after-turn")
TEXT_ACCESSOR(codex_agent_hook_current_hash_copy, codex_agent_hook_t, "hash")
TEXT_ACCESSOR(codex_agent_hook_source_copy, codex_agent_hook_t, "user")
TEXT_ACCESSOR(codex_agent_hook_source_path_copy, codex_agent_hook_t, "/hook")
codex_agent_status_t codex_agent_hook_is_enabled(codex_agent_context_t*, codex_agent_hook_t*, int32_t* out) { *out = 1; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_hook_is_managed(codex_agent_context_t*, codex_agent_hook_t*, int32_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_hook_can_trust(codex_agent_context_t*, codex_agent_hook_t*, int32_t* out) { *out = 1; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_hook_can_uninstall(codex_agent_context_t*, codex_agent_hook_t*, int32_t* out) { *out = 1; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_hook_timeout_seconds(codex_agent_context_t*, codex_agent_hook_t*, int64_t* out) { *out = 1; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_hook_trust_status(codex_agent_context_t*, codex_agent_hook_t*, codex_agent_hook_trust_status_t* out) { *out = CODEX_AGENT_HOOK_TRUST_STATUS_TRUSTED; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_hook_origin(codex_agent_context_t*, codex_agent_hook_t*, codex_agent_resource_origin_t* out) { *out = CODEX_AGENT_RESOURCE_ORIGIN_USER; return CODEX_AGENT_STATUS_OK; }
#define HOOK_ABSENT(name) codex_agent_status_t name(codex_agent_context_t*, codex_agent_hook_t*, int32_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
HOOK_ABSENT(codex_agent_hook_has_matcher)
HOOK_ABSENT(codex_agent_hook_has_plugin_id)
HOOK_ABSENT(codex_agent_hook_has_status_message)
#undef HOOK_ABSENT
codex_agent_status_t codex_agent_hook_handler(codex_agent_context_t*, codex_agent_hook_t*, codex_agent_hook_handler_t** out) { *out = new codex_agent_hook_handler_t{}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_hook_handler_kind(codex_agent_context_t*, codex_agent_hook_handler_t*, codex_agent_hook_handler_kind_t* out) { *out = CODEX_AGENT_HOOK_HANDLER_KIND_AGENT; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_hook_handler_agent_acquire(codex_agent_context_t*, codex_agent_hook_handler_agent_t** out) { *out = new codex_agent_hook_handler_agent_t{}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_hook_handler_agent_destroy(codex_agent_context_t*, codex_agent_hook_handler_agent_t** value) { return drop(value); }
codex_agent_status_t codex_agent_hook_handler_from_agent(codex_agent_context_t*, codex_agent_hook_handler_agent_t*, codex_agent_hook_handler_t** out) { *out = new codex_agent_hook_handler_t{}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_hook_create(codex_agent_context_t*, const codex_agent_string_view_t* key, const codex_agent_string_view_t*, int32_t is_enabled, const codex_agent_string_view_t*, codex_agent_hook_handler_t*, int32_t, const codex_agent_string_view_t*, const codex_agent_string_view_t* path, int64_t, codex_agent_hook_trust_status_t trust, int32_t, const codex_agent_string_view_t*, int32_t, const codex_agent_string_view_t*, int32_t, const codex_agent_string_view_t*, int32_t, codex_agent_resource_origin_t, int32_t, codex_agent_hook_t** out) { *out = new codex_agent_hook{string_value(key), string_value(path), is_enabled, trust}; return CODEX_AGENT_STATUS_OK; }

codex_agent_status_t codex_agent_plugin_catalog_plugins_count(codex_agent_context_t*, codex_agent_plugin_catalog_t*, size_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_plugin_catalog_errors_count(codex_agent_context_t*, codex_agent_plugin_catalog_t*, size_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_plugin_catalog_freshness(codex_agent_context_t*, codex_agent_plugin_catalog_t*, codex_agent_catalog_freshness_t* out) { *out = CODEX_AGENT_CATALOG_FRESHNESS_LIVE; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_plugin_reference_create(codex_agent_context_t*, const codex_agent_string_view_t* id, const codex_agent_string_view_t* name, const codex_agent_string_view_t* marketplace, int32_t, const codex_agent_string_view_t*, int32_t, const codex_agent_string_view_t*, codex_agent_plugin_reference_t** out) { *out = new codex_agent_plugin_reference{string_value(id), string_value(name), string_value(marketplace)}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_plugin_detail_summary(codex_agent_context_t*, codex_agent_plugin_detail_t*, codex_agent_plugin_summary_t** out) { *out = new codex_agent_plugin_summary{}; return CODEX_AGENT_STATUS_OK; }
TEXT_ACCESSOR(codex_agent_plugin_detail_description_copy, codex_agent_plugin_detail_t, "detail")
codex_agent_status_t codex_agent_plugin_detail_skills_count(codex_agent_context_t*, codex_agent_plugin_detail_t*, size_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_plugin_detail_connectors_count(codex_agent_context_t*, codex_agent_plugin_detail_t*, size_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_plugin_detail_mcp_servers_count(codex_agent_context_t*, codex_agent_plugin_detail_t*, size_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_plugin_detail_hook_count(codex_agent_context_t*, codex_agent_plugin_detail_t*, int32_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_plugin_summary_reference(codex_agent_context_t*, codex_agent_plugin_summary_t*, codex_agent_plugin_reference_t** out) { *out = new codex_agent_plugin_reference{}; return CODEX_AGENT_STATUS_OK; }
TEXT_ACCESSOR(codex_agent_plugin_reference_id_copy, codex_agent_plugin_reference_t, "plugin")
TEXT_ACCESSOR(codex_agent_plugin_reference_name_copy, codex_agent_plugin_reference_t, "plugin")
TEXT_ACCESSOR(codex_agent_plugin_reference_marketplace_name_copy, codex_agent_plugin_reference_t, "market")
#define REF_ABSENT(name) codex_agent_status_t name(codex_agent_context_t*, codex_agent_plugin_reference_t*, int32_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
REF_ABSENT(codex_agent_plugin_reference_has_marketplace_path)
REF_ABSENT(codex_agent_plugin_reference_has_remote_plugin_id)
#undef REF_ABSENT
TEXT_ACCESSOR(codex_agent_plugin_summary_display_name_copy, codex_agent_plugin_summary_t, "Plugin")
TEXT_ACCESSOR(codex_agent_plugin_summary_description_copy, codex_agent_plugin_summary_t, "description")
#define SUMMARY_BOOL(name, value) codex_agent_status_t name(codex_agent_context_t*, codex_agent_plugin_summary_t*, int32_t* out) { *out = value; return CODEX_AGENT_STATUS_OK; }
SUMMARY_BOOL(codex_agent_plugin_summary_is_installed, 1)
SUMMARY_BOOL(codex_agent_plugin_summary_is_enabled, 1)
SUMMARY_BOOL(codex_agent_plugin_summary_is_available, 1)
SUMMARY_BOOL(codex_agent_plugin_summary_has_brand_color, 0)
SUMMARY_BOOL(codex_agent_plugin_summary_has_privacy_policy_url, 0)
SUMMARY_BOOL(codex_agent_plugin_summary_has_terms_of_service_url, 0)
SUMMARY_BOOL(codex_agent_plugin_summary_has_website_url, 0)
#undef SUMMARY_BOOL
codex_agent_status_t codex_agent_plugin_summary_install_policy(codex_agent_context_t*, codex_agent_plugin_summary_t*, codex_agent_plugin_install_policy_t* out) { *out = CODEX_AGENT_PLUGIN_INSTALL_POLICY_AVAILABLE; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_plugin_summary_auth_policy(codex_agent_context_t*, codex_agent_plugin_summary_t*, codex_agent_plugin_auth_policy_t* out) { *out = CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_USE; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_plugin_summary_capabilities_count(codex_agent_context_t*, codex_agent_plugin_summary_t*, size_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_plugin_install_result_auth_policy(codex_agent_context_t*, codex_agent_plugin_install_result_t*, codex_agent_plugin_auth_policy_t* out) { *out = CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_USE; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_plugin_install_result_connectors_count(codex_agent_context_t*, codex_agent_plugin_install_result_t*, size_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_plugin_install_result_has_message(codex_agent_context_t*, codex_agent_plugin_install_result_t*, int32_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }

/* Minimal MCP input/output graph used by the service projection test. */
codex_agent_status_t codex_agent_mcp_transport_http_create(codex_agent_context_t*, const codex_agent_string_view_t* url, int32_t, const codex_agent_string_view_t*, int32_t, const codex_agent_string_view_t*, const codex_agent_string_view_t*, size_t, int32_t, const codex_agent_string_view_t*, const codex_agent_string_view_t*, size_t, int32_t, const codex_agent_string_view_t*, codex_agent_mcp_transport_http_t** out) { *out = new codex_agent_mcp_transport_http_t{string_value(url)}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_mcp_transport_from_http(codex_agent_context_t*, codex_agent_mcp_transport_http_t* http, codex_agent_mcp_transport_t** out) { *out = new codex_agent_mcp_transport{http->url}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_mcp_server_configuration_create(codex_agent_context_t*, const codex_agent_string_view_t* name, codex_agent_mcp_transport_t* transport, int32_t, codex_agent_mcp_authentication_t, const codex_agent_string_view_t*, int32_t, int32_t, int32_t, int32_t, const codex_agent_mcp_tool_exposure_surface_t*, size_t, int32_t, double, int32_t, double, int32_t, codex_agent_mcp_tool_approval_t, int32_t, const codex_agent_string_view_t*, size_t, int32_t, const codex_agent_string_view_t*, size_t, int32_t, const codex_agent_string_view_t*, size_t, int32_t, codex_agent_mcp_oauth_configuration_t*, int32_t, const codex_agent_string_view_t*, const codex_agent_string_view_t*, codex_agent_mcp_tool_configuration_t* const*, size_t, codex_agent_mcp_server_configuration_t** out) { *out = new codex_agent_mcp_server_configuration_t{string_value(name), transport->url}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_mcp_server_create(codex_agent_context_t*, const codex_agent_string_view_t* name, const codex_agent_string_view_t* display_name, codex_agent_mcp_auth_status_t auth, codex_agent_mcp_server_configuration_t*, codex_agent_resource_origin_t, int32_t, codex_agent_mcp_server_t** out) { *out = new codex_agent_mcp_server{string_value(name), string_value(display_name), auth}; return CODEX_AGENT_STATUS_OK; }
TEXT_ACCESSOR(codex_agent_mcp_server_name_copy, codex_agent_mcp_server_t, "server")
TEXT_ACCESSOR(codex_agent_mcp_server_display_name_copy, codex_agent_mcp_server_t, "Server")
codex_agent_status_t codex_agent_mcp_server_auth_status(codex_agent_context_t*, codex_agent_mcp_server_t*, codex_agent_mcp_auth_status_t* out) { *out = CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_mcp_server_origin(codex_agent_context_t*, codex_agent_mcp_server_t*, codex_agent_resource_origin_t* out) { *out = CODEX_AGENT_RESOURCE_ORIGIN_USER; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_mcp_server_can_remove(codex_agent_context_t*, codex_agent_mcp_server_t*, int32_t* out) { *out = 1; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_mcp_server_has_configuration(codex_agent_context_t*, codex_agent_mcp_server_t*, int32_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }

codex_agent_status_t codex_agent_integration_authorization_authorize(codex_agent_context_t* context, codex_agent_integration_authorization_t*, codex_agent_integration_t* integration, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { RECORD_START(codex_agent_integration_authorization_authorize); if (integration == nullptr || (integration->id != "connector:connector" && integration->id != "mcp:server")) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; return complete(context, operation_kind::void_, callback, user_data, out); }
codex_agent_status_t codex_agent_integration_authorization_state_value(codex_agent_context_t*, codex_agent_snapshot_t* snapshot, codex_agent_integration_authorization_state_t** out) { RECORD_START(codex_agent_integration_authorization_state_value); *out = new codex_agent_integration_authorization_state{snapshot->phase}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_integration_authorization_state_status(codex_agent_context_t*, codex_agent_integration_authorization_state_t* state, codex_agent_integration_authorization_status_t* out) { *out = state->phase == 0 ? CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_IDLE : CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_FAILED; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_integration_authorization_state_target(codex_agent_context_t*, codex_agent_integration_authorization_state_t* state, codex_agent_integration_t** out) { if (state->phase == 0) return CODEX_AGENT_STATUS_NOT_READY; *out = new codex_agent_integration{"mcp:server"}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_integration_authorization_state_failure(codex_agent_context_t*, codex_agent_integration_authorization_state_t* state, codex_agent_failure_t** out) { if (state->phase == 0) return CODEX_AGENT_STATUS_NOT_READY; *out = new codex_agent_failure{}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_integration_authorization_active_has_value(codex_agent_context_t*, codex_agent_snapshot_t* snapshot, int32_t* out) { RECORD_START(codex_agent_integration_authorization_active_has_value); *out = snapshot->phase < 2 ? 1 : 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_integration_authorization_active_value(codex_agent_context_t*, codex_agent_snapshot_t* snapshot, codex_agent_integration_t** out) { RECORD_START(codex_agent_integration_authorization_active_value); *out = new codex_agent_integration{snapshot->phase == 0 ? "connector:connector" : "mcp:server"}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_connector_create(codex_agent_context_t*, const codex_agent_string_view_t* id, const codex_agent_string_view_t*, const codex_agent_string_view_t*, int32_t, const codex_agent_string_view_t*, int32_t, int32_t, const codex_agent_string_view_t*, size_t, codex_agent_connector_t** out) { *out = new codex_agent_connector{string_value(id)}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_integration_connector_create(codex_agent_context_t*, codex_agent_connector_t* connector, codex_agent_integration_connector_t** out) { *out = new codex_agent_integration_connector_t{"connector:" + connector->id}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_integration_from_connector(codex_agent_context_t*, codex_agent_integration_connector_t* connector, codex_agent_integration_t** out) { *out = new codex_agent_integration{connector->id}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_integration_mcp_server_create(codex_agent_context_t*, codex_agent_mcp_server_t* server, codex_agent_integration_mcp_server_t** out) { *out = new codex_agent_integration_mcp_server_t{"mcp:" + server->name}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_integration_from_mcp_server(codex_agent_context_t*, codex_agent_integration_mcp_server_t* server, codex_agent_integration_t** out) { *out = new codex_agent_integration{server->id}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_integration_kind(codex_agent_context_t*, codex_agent_integration_t* integration, codex_agent_integration_kind_t* out) { *out = integration->id.starts_with("mcp:") ? CODEX_AGENT_INTEGRATION_KIND_MCP_SERVER : CODEX_AGENT_INTEGRATION_KIND_CONNECTOR; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_integration_connector(codex_agent_context_t*, codex_agent_integration_t* integration, codex_agent_integration_connector_t** out) { *out = new codex_agent_integration_connector_t{integration->id}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_integration_connector_connector(codex_agent_context_t*, codex_agent_integration_connector_t*, codex_agent_connector_t** out) { *out = new codex_agent_connector{}; return CODEX_AGENT_STATUS_OK; }
TEXT_ACCESSOR(codex_agent_integration_connector_id_copy, codex_agent_integration_connector_t, "connector:connector")
TEXT_ACCESSOR(codex_agent_integration_connector_display_name_copy, codex_agent_integration_connector_t, "Connector")
codex_agent_status_t codex_agent_integration_mcp_server(codex_agent_context_t*, codex_agent_integration_t* integration, codex_agent_integration_mcp_server_t** out) { *out = new codex_agent_integration_mcp_server_t{integration->id}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_integration_mcp_server_server(codex_agent_context_t*, codex_agent_integration_mcp_server_t*, codex_agent_mcp_server_t** out) { *out = new codex_agent_mcp_server{}; return CODEX_AGENT_STATUS_OK; }
TEXT_ACCESSOR(codex_agent_integration_mcp_server_id_copy, codex_agent_integration_mcp_server_t, "mcp:server")
TEXT_ACCESSOR(codex_agent_integration_mcp_server_display_name_copy, codex_agent_integration_mcp_server_t, "Server")
TEXT_ACCESSOR(codex_agent_connector_id_copy, codex_agent_connector_t, "connector")
TEXT_ACCESSOR(codex_agent_connector_name_copy, codex_agent_connector_t, "Connector")
TEXT_ACCESSOR(codex_agent_connector_description_copy, codex_agent_connector_t, "description")
codex_agent_status_t codex_agent_connector_has_install_url(codex_agent_context_t*, codex_agent_connector_t*, int32_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_connector_is_accessible(codex_agent_context_t*, codex_agent_connector_t*, int32_t* out) { *out = 1; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_connector_is_enabled(codex_agent_context_t*, codex_agent_connector_t*, int32_t* out) { *out = 1; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_connector_plugin_names_count(codex_agent_context_t*, codex_agent_connector_t*, size_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }

codex_agent_status_t codex_agent_interactions_state_value(codex_agent_context_t*, codex_agent_snapshot_t* snapshot, codex_agent_interaction_state_t** out) { RECORD_START(codex_agent_interactions_state_value); *out = new codex_agent_interaction_state{snapshot->phase}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_interaction_state_pending_count(codex_agent_context_t*, codex_agent_interaction_state_t* state, size_t* out) { *out = state->phase == 0 ? 0 : 1; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_interaction_state_pending_at(codex_agent_context_t*, codex_agent_interaction_state_t*, size_t index, codex_agent_pending_interaction_t** out) { if (index != 0) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; *out = new codex_agent_pending_interaction{}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_pending_interaction_kind(codex_agent_context_t*, codex_agent_pending_interaction_t* pending, codex_agent_pending_interaction_kind_t* out) { *out = pending->kind; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_pending_interaction_approval(codex_agent_context_t*, codex_agent_pending_interaction_t*, codex_agent_pending_approval_t** out) { *out = new codex_agent_pending_approval{}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_interaction_state_resolving_request_ids_contains(codex_agent_context_t*, codex_agent_interaction_state_t*, const codex_agent_string_view_t*, int32_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_interaction_state_has_failure(codex_agent_context_t*, codex_agent_interaction_state_t*, int32_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_interactions_approvals_count(codex_agent_context_t*, codex_agent_snapshot_t* snapshot, size_t* out) { RECORD_START(codex_agent_interactions_approvals_count); *out = snapshot->phase == 0 ? 1 : 2; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_interactions_approvals_at(codex_agent_context_t*, codex_agent_snapshot_t* snapshot, size_t index, codex_agent_pending_approval_t** out) { RECORD_START(codex_agent_interactions_approvals_at); *out = new codex_agent_pending_approval{index == 0 ? "approval" : "approval-2", snapshot->context}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_pending_approval_request_id_copy(codex_agent_context_t*, codex_agent_pending_approval_t* approval, uint8_t* b, size_t n, size_t* r) { return copy(approval->request_id, b, n, r); }
TEXT_ACCESSOR(codex_agent_pending_approval_title_copy, codex_agent_pending_approval_t, "Approve")
TEXT_ACCESSOR(codex_agent_pending_approval_details_copy, codex_agent_pending_approval_t, "details")
codex_agent_status_t codex_agent_pending_approval_conversation_id(codex_agent_context_t*, codex_agent_pending_approval_t*, codex_agent_conversation_id_t** out) { *out = new codex_agent_conversation_id{}; return CODEX_AGENT_STATUS_OK; }
TEXT_ACCESSOR(codex_agent_conversation_id_value_copy, codex_agent_conversation_id_t, "conversation")
codex_agent_status_t codex_agent_interactions_elicitations_count(codex_agent_context_t*, codex_agent_snapshot_t* snapshot, size_t* out) { RECORD_START(codex_agent_interactions_elicitations_count); *out = snapshot->phase == 0 ? 1 : 2; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_interactions_elicitations_at(codex_agent_context_t*, codex_agent_snapshot_t* snapshot, size_t index, codex_agent_pending_elicitation_t** out) { RECORD_START(codex_agent_interactions_elicitations_at); *out = new codex_agent_pending_elicitation{index == 0 ? "elicitation" : "elicitation-2", snapshot->context}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_pending_elicitation_elicitation(codex_agent_context_t*, codex_agent_pending_elicitation_t* pending, codex_agent_elicitation_t** out) { *out = new codex_agent_elicitation{pending->request_id}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_elicitation_request_id_copy(codex_agent_context_t*, codex_agent_elicitation_t* elicitation, uint8_t* b, size_t n, size_t* r) { return copy(elicitation->request_id, b, n, r); }
TEXT_ACCESSOR(codex_agent_elicitation_server_name_copy, codex_agent_elicitation_t, "server")
TEXT_ACCESSOR(codex_agent_elicitation_message_copy, codex_agent_elicitation_t, "message")
codex_agent_status_t codex_agent_elicitation_conversation_id(codex_agent_context_t*, codex_agent_elicitation_t*, codex_agent_conversation_id_t** out) { *out = new codex_agent_conversation_id{}; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_elicitation_has_url(codex_agent_context_t*, codex_agent_elicitation_t*, int32_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_elicitation_has_form(codex_agent_context_t*, codex_agent_elicitation_t*, int32_t* out) { *out = 0; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_elicitation_response_create(codex_agent_context_t*, codex_agent_elicitation_action_t action, const codex_agent_string_view_t* content_keys, codex_agent_form_value_t* const*, size_t content_count, codex_agent_elicitation_response_t** out) { auto* response = new codex_agent_elicitation_response{}; response->action = action; for (size_t index = 0; index < content_count; ++index) response->keys.push_back(string_value(&content_keys[index])); *out = response; return CODEX_AGENT_STATUS_OK; }
codex_agent_status_t codex_agent_interactions_open_url(codex_agent_context_t* context, codex_agent_interactions_t* interactions, codex_agent_pending_elicitation_t* pending, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { RECORD_START(codex_agent_interactions_open_url); if (pending == nullptr || interactions == nullptr || pending->request_id != "elicitation" || pending->context != interactions->context) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; return complete(context, operation_kind::void_, callback, user_data, out); }
codex_agent_status_t codex_agent_interactions_resolve_approval(codex_agent_context_t* context, codex_agent_interactions_t* interactions, codex_agent_pending_approval_t* pending, codex_agent_approval_decision_t decision, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { RECORD_START(codex_agent_interactions_resolve_approval); if (pending == nullptr || interactions == nullptr || pending->request_id != "approval" || pending->context != interactions->context || decision != CODEX_AGENT_APPROVAL_DECISION_ACCEPT) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; return complete(context, operation_kind::void_, callback, user_data, out); }
codex_agent_status_t codex_agent_interactions_resolve_elicitation(codex_agent_context_t* context, codex_agent_interactions_t* interactions, codex_agent_pending_elicitation_t* pending, codex_agent_elicitation_response_t* response, codex_agent_operation_callback_t callback, void* user_data, codex_agent_operation_t** out) { RECORD_START(codex_agent_interactions_resolve_elicitation); if (pending == nullptr || interactions == nullptr || pending->request_id != "elicitation" || pending->context != interactions->context || response == nullptr || response->action != CODEX_AGENT_ELICITATION_ACTION_DECLINE || !response->keys.empty()) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; return complete(context, operation_kind::void_, callback, user_data, out); }

#undef RECORD_START
#undef TEXT_ACCESSOR
}
