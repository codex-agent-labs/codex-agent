#include <codex_agent.h>

#include "agent_native_probe.hpp"

#include <cstring>
#include <string>
#include <vector>

struct AgentCore {
    std::string workspace_path = "/workspace";
    std::string workspace_name = "Workspace";
};

struct codex_agent_context {
    AgentCore core;
    std::size_t live_hosts = 0;
};
struct codex_agent_host {
    codex_agent_context_t* context;
    AgentCore* core;
    std::size_t live_agents = 0;
};
struct codex_agent_agent {
    codex_agent_context_t* context;
    AgentCore* core;
    codex_agent_host_t* parent;
    std::size_t live_children = 0;
    bool had_child = false;
};
#define AGENT_SERVICE(name)                                                \
    struct codex_agent_##name {                                           \
        codex_agent_context_t* context;                                   \
        AgentCore* core;                                                   \
        codex_agent_agent_t* parent;                                      \
    };
AGENT_SERVICE(authentication)
AGENT_SERVICE(connectors)
AGENT_SERVICE(conversations)
AGENT_SERVICE(hooks)
AGENT_SERVICE(integration_authorization)
AGENT_SERVICE(interactions)
AGENT_SERVICE(mcp_servers)
AGENT_SERVICE(models)
AGENT_SERVICE(plugins)
AGENT_SERVICE(skills)
#undef AGENT_SERVICE
struct codex_agent_workspace {
    codex_agent_context_t* context;
    codex_agent_agent_t* parent;
    std::string path;
    std::string display_name;
};
struct codex_agent_snapshot { codex_agent_host_t* host; };

namespace {

std::vector<AgentNativeEdge> events;
codex_agent_context_t* latest_context = nullptr;
bool stable_identity = true;
bool exact_release_order = true;
std::size_t child_releases = 0;
std::size_t agent_releases = 0;
std::size_t host_releases = 0;
std::size_t context_destroys = 0;
std::size_t premature_releases = 0;

codex_agent_status_t copy(
    const std::string& value, std::uint8_t* buffer, std::size_t capacity,
    std::size_t* required) {
    if (required == nullptr) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *required = value.size();
    if (capacity < value.size()) return CODEX_AGENT_STATUS_BUFFER_TOO_SMALL;
    if (!value.empty()) std::memcpy(buffer, value.data(), value.size());
    return CODEX_AGENT_STATUS_OK;
}

template <typename Value>
codex_agent_status_t release_child(Value** value) {
    if (value == nullptr || *value == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    auto* parent = (*value)->parent;
    exact_release_order = exact_release_order && parent != nullptr &&
                          parent->live_children == 1;
    --parent->live_children;
    ++child_releases;
    delete *value;
    *value = nullptr;
    return CODEX_AGENT_STATUS_OK;
}

}  // namespace

void codex_agent_cpp_mock_agent_reset() {
    events.clear();
    latest_context = nullptr;
    stable_identity = true;
    exact_release_order = true;
    child_releases = 0;
    agent_releases = 0;
    host_releases = 0;
    context_destroys = 0;
    premature_releases = 0;
}

std::size_t codex_agent_cpp_mock_agent_event_count() { return events.size(); }

AgentNativeEdge codex_agent_cpp_mock_agent_event_at(std::size_t index) {
    return events.at(index);
}

extern "C" {

void codex_agent_cpp_mock_agent_change_workspace() {
    latest_context->core.workspace_path = "/changed";
    latest_context->core.workspace_name = "Changed";
}

int codex_agent_cpp_mock_agent_identity_stable() {
    return stable_identity ? 1 : 0;
}

int codex_agent_cpp_mock_agent_exact_release_order() {
    return exact_release_order ? 1 : 0;
}

std::size_t codex_agent_cpp_mock_agent_child_release_count() {
    return child_releases;
}

std::size_t codex_agent_cpp_mock_agent_agent_release_count() {
    return agent_releases;
}

std::size_t codex_agent_cpp_mock_agent_host_release_count() {
    return host_releases;
}

std::size_t codex_agent_cpp_mock_agent_context_destroy_count() {
    return context_destroys;
}

std::size_t codex_agent_cpp_mock_agent_premature_release_count() {
    return premature_releases;
}

int32_t codex_agent_abi_is_compatible(uint32_t requested_version) {
    return requested_version == CODEX_AGENT_ABI_VERSION_CURRENT ? 1 : 0;
}

codex_agent_status_t codex_agent_context_create(codex_agent_context_t** out) {
    if (out == nullptr || *out != nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out = new codex_agent_context{};
    latest_context = *out;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_context_destroy(codex_agent_context_t** value) {
    if (value == nullptr || *value == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if ((*value)->live_hosts != 0) {
        ++premature_releases;
        return CODEX_AGENT_STATUS_OPERATION_FAILED;
    }
    ++context_destroys;
    latest_context = nullptr;
    delete *value;
    *value = nullptr;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_host_create(
    codex_agent_context_t* context, const codex_agent_host_options_t* options,
    codex_agent_host_t** out) {
    if (context == nullptr || options == nullptr || out == nullptr ||
        *out != nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    ++context->live_hosts;
    *out = new codex_agent_host{context, &context->core};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_host_retain(
    codex_agent_context_t* context, codex_agent_host_t* host,
    codex_agent_host_t** out) {
    if (context == nullptr || host == nullptr || out == nullptr ||
        *out != nullptr || host->context != context)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    ++context->live_hosts;
    *out = new codex_agent_host{context, host->core};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_host_release(
    codex_agent_context_t*, codex_agent_host_t** value) {
    if (value == nullptr || *value == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if ((*value)->live_agents != 0) {
        ++premature_releases;
        return CODEX_AGENT_STATUS_OPERATION_FAILED;
    }
    auto* context = (*value)->context;
    --context->live_hosts;
    ++host_releases;
    delete *value;
    *value = nullptr;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_host_state_get(
    codex_agent_context_t* context, codex_agent_host_t* host,
    codex_agent_snapshot_t** out) {
    if (context == nullptr || host == nullptr || out == nullptr ||
        *out != nullptr || host->context != context)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out = new codex_agent_snapshot{host};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_host_state_agent(
    codex_agent_context_t* context, codex_agent_host_t* host,
    codex_agent_snapshot_t* snapshot, codex_agent_agent_t** out) {
    if (context == nullptr || host == nullptr || snapshot == nullptr ||
        out == nullptr || *out != nullptr || host->context != context ||
        snapshot->host != host)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    ++host->live_agents;
    *out = new codex_agent_agent{context, host->core, host};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_snapshot_destroy(
    codex_agent_context_t*, codex_agent_snapshot_t** value) {
    if (value == nullptr) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    delete *value;
    *value = nullptr;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_agent_retain(
    codex_agent_context_t* context, codex_agent_agent_t* agent,
    codex_agent_agent_t** out) {
    if (context == nullptr || agent == nullptr || out == nullptr ||
        *out != nullptr || agent->context != context)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    ++agent->parent->live_agents;
    *out = new codex_agent_agent{context, agent->core, agent->parent};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t codex_agent_agent_release(
    codex_agent_context_t*, codex_agent_agent_t** value) {
    if (value == nullptr || *value == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if ((*value)->live_children != 0) {
        ++premature_releases;
        return CODEX_AGENT_STATUS_OPERATION_FAILED;
    }
    exact_release_order = exact_release_order &&
                          (!(*value)->had_child ||
                           (*value)->live_children == 0);
    --(*value)->parent->live_agents;
    ++agent_releases;
    delete *value;
    *value = nullptr;
    return CODEX_AGENT_STATUS_OK;
}

#define AGENT_ACCESSOR(name)                                               \
codex_agent_status_t codex_agent_agent_##name(                             \
    codex_agent_context_t* context, codex_agent_agent_t* agent,            \
    codex_agent_##name##_t** out) {                                        \
    events.push_back(AgentNativeEdge::codex_agent_agent_##name);           \
    if (context == nullptr || agent == nullptr || out == nullptr ||        \
        *out != nullptr || agent->context != context ||                    \
        agent->live_children != 0)                                         \
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;                        \
    stable_identity = stable_identity && agent->core == &context->core;    \
    ++agent->live_children;                                                \
    agent->had_child = true;                                               \
    *out = new codex_agent_##name{context, agent->core, agent};            \
    return CODEX_AGENT_STATUS_OK;                                          \
}
AGENT_ACCESSOR(authentication)
AGENT_ACCESSOR(connectors)
AGENT_ACCESSOR(conversations)
AGENT_ACCESSOR(hooks)
AGENT_ACCESSOR(integration_authorization)
AGENT_ACCESSOR(interactions)
AGENT_ACCESSOR(mcp_servers)
AGENT_ACCESSOR(models)
AGENT_ACCESSOR(plugins)
AGENT_ACCESSOR(skills)
#undef AGENT_ACCESSOR

codex_agent_status_t codex_agent_agent_workspace(
    codex_agent_context_t* context, codex_agent_agent_t* agent,
    codex_agent_workspace_t** out) {
    events.push_back(AgentNativeEdge::codex_agent_agent_workspace);
    if (context == nullptr || agent == nullptr || out == nullptr ||
        *out != nullptr || agent->context != context ||
        agent->live_children != 0)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    stable_identity = stable_identity && agent->core == &context->core;
    ++agent->live_children;
    agent->had_child = true;
    *out = new codex_agent_workspace{
        context, agent, agent->core->workspace_path,
        agent->core->workspace_name};
    return CODEX_AGENT_STATUS_OK;
}

#define AGENT_RELEASE(name)                                                \
codex_agent_status_t codex_agent_##name##_release(                         \
    codex_agent_context_t*, codex_agent_##name##_t** value) {              \
    return release_child(value);                                           \
}
AGENT_RELEASE(authentication)
AGENT_RELEASE(connectors)
AGENT_RELEASE(conversations)
AGENT_RELEASE(hooks)
AGENT_RELEASE(integration_authorization)
AGENT_RELEASE(interactions)
AGENT_RELEASE(mcp_servers)
AGENT_RELEASE(models)
AGENT_RELEASE(plugins)
AGENT_RELEASE(skills)
#undef AGENT_RELEASE

codex_agent_status_t codex_agent_workspace_destroy(
    codex_agent_context_t*, codex_agent_workspace_t** value) {
    return release_child(value);
}

codex_agent_status_t codex_agent_workspace_path_copy(
    codex_agent_context_t*, codex_agent_workspace_t* value,
    std::uint8_t* buffer, std::size_t capacity, std::size_t* required) {
    if (value == nullptr) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return copy(value->path, buffer, capacity, required);
}

codex_agent_status_t codex_agent_workspace_display_name_copy(
    codex_agent_context_t*, codex_agent_workspace_t* value,
    std::uint8_t* buffer, std::size_t capacity, std::size_t* required) {
    if (value == nullptr) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return copy(value->display_name, buffer, capacity, required);
}

}  // extern "C"
