#include <codex_agent.h>

#include "host_native_probe.hpp"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstring>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

struct host_model {
    codex_agent_host_state_kind_t state = CODEX_AGENT_HOST_STATE_READY;
    std::string workspace_path = "/workspace";
    std::string workspace_name = "Workspace";
    std::size_t live_hosts = 0;
    std::size_t live_agents = 0;
    std::shared_ptr<int> agent_identity = std::make_shared<int>(0);
};

struct agent_model {
    std::shared_ptr<host_model> host;
    std::shared_ptr<int> identity;
};

struct codex_agent_context {};
struct codex_agent_host {
    codex_agent_context_t* context;
    std::shared_ptr<host_model> model;
};
struct codex_agent_agent {
    codex_agent_context_t* context;
    std::shared_ptr<agent_model> model;
};
struct codex_agent_workspace {
    std::string path;
    std::string name;
};
struct codex_agent_snapshot {
    codex_agent_host_state_kind_t state;
    std::string path;
    std::string name;
};
struct codex_agent_failure {
    std::string code;
    std::string message;
    std::int32_t recoverable;
};
struct codex_agent_operation {
    codex_agent_context_t* context = nullptr;
    codex_agent_operation_callback_t callback = nullptr;
    void* user_data = nullptr;
    codex_agent_status_t result = CODEX_AGENT_STATUS_OK;
    bool completed = false;
};
struct codex_agent_subscription {
    codex_agent_context_t* context;
    codex_agent_state_callback_t callback;
    void* user_data;
    std::shared_ptr<host_model> model;
    std::atomic<bool> terminal_started{false};
    std::atomic<bool> terminal_finished{false};
};

namespace {

std::vector<HostNativeEdge> events;
std::vector<codex_agent_subscription_t*> subscriptions;
std::mutex subscriptions_mutex;
codex_agent_operation_t* pending_operation = nullptr;
bool delay_next = false;
bool fail_next = false;
std::string copied_bundle;
std::string copied_data;
std::string copied_name;
std::string copied_title;
std::string copied_version;
std::string copied_selection;
std::shared_ptr<agent_model> projected_agent;
bool identity_stable = true;
std::vector<std::string> releases;
std::size_t premature_releases = 0;
std::size_t context_destroys = 0;
std::size_t ready_projections = 0;
std::size_t agent_retains = 0;
std::size_t agent_releases = 0;

void record(HostNativeEdge edge) { events.push_back(edge); }

std::string from_view(codex_agent_string_view_t value) {
    return std::string(
        reinterpret_cast<const char*>(value.data), value.size);
}

codex_agent_status_t copy_string(
    const std::string& value, std::uint8_t* buffer, std::size_t capacity,
    std::size_t* out_required) {
    if (out_required == nullptr) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_required = value.size();
    if (capacity < value.size()) return CODEX_AGENT_STATUS_BUFFER_TOO_SMALL;
    if (!value.empty()) {
        if (buffer == nullptr) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
        std::memcpy(buffer, value.data(), value.size());
    }
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_snapshot_t* snapshot(const std::shared_ptr<host_model>& model) {
    return new codex_agent_snapshot{model->state, model->workspace_path,
                                    model->workspace_name};
}

codex_agent_status_t launch(
    codex_agent_context_t* context, codex_agent_operation_callback_t callback,
    void* user_data, codex_agent_operation_t** out_operation) {
    if (context == nullptr || callback == nullptr || out_operation == nullptr ||
        *out_operation != nullptr) {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    auto* operation = new codex_agent_operation{
        context, callback, user_data,
        fail_next ? CODEX_AGENT_STATUS_OPERATION_FAILED
                  : CODEX_AGENT_STATUS_OK,
        false};
    fail_next = false;
    *out_operation = operation;
    if (delay_next) {
        delay_next = false;
        pending_operation = operation;
    } else {
        operation->completed = true;
        callback(context, operation, user_data);
    }
    return CODEX_AGENT_STATUS_OK;
}

std::size_t release_position(const char* value) {
    const auto found = std::find(releases.begin(), releases.end(), value);
    return found == releases.end()
        ? static_cast<std::size_t>(-1)
        : static_cast<std::size_t>(found - releases.begin());
}

}  // namespace

void codex_agent_cpp_mock_host_reset() {
    events.clear();
    releases.clear();
    copied_bundle.clear();
    copied_data.clear();
    copied_name.clear();
    copied_title.clear();
    copied_version.clear();
    copied_selection.clear();
    projected_agent.reset();
    identity_stable = true;
    premature_releases = 0;
    context_destroys = 0;
    ready_projections = 0;
    agent_retains = 0;
    agent_releases = 0;
    delay_next = false;
    fail_next = false;
    pending_operation = nullptr;
}

std::size_t codex_agent_cpp_mock_host_event_count() {
    return events.size();
}

HostNativeEdge codex_agent_cpp_mock_host_event_at(
    std::size_t index) {
    return events.at(index);
}

extern "C" void codex_agent_cpp_mock_host_delay_next() { delay_next = true; }
extern "C" void codex_agent_cpp_mock_host_fail_next() { fail_next = true; }

extern "C" void codex_agent_cpp_mock_host_complete_pending() {
    if (pending_operation == nullptr) return;
    auto* operation = pending_operation;
    pending_operation = nullptr;
    operation->completed = true;
    operation->callback(operation->context, operation, operation->user_data);
}

extern "C" void codex_agent_cpp_mock_host_publish() {
    std::lock_guard lock(subscriptions_mutex);
    for (auto* subscription : subscriptions) {
        subscription->callback(
            subscription->context, subscription, CODEX_AGENT_STATUS_OK,
            snapshot(subscription->model), 0, subscription->user_data);
    }
}

extern "C" void codex_agent_cpp_mock_host_change_workspace() {
    std::lock_guard lock(subscriptions_mutex);
    for (auto* subscription : subscriptions) {
        subscription->model->workspace_path = "/workspace-next";
        subscription->model->workspace_name = "Workspace Next";
    }
}

extern "C" const char* codex_agent_cpp_mock_host_bundle() {
    return copied_bundle.c_str();
}
extern "C" const char* codex_agent_cpp_mock_host_data() {
    return copied_data.c_str();
}
extern "C" const char* codex_agent_cpp_mock_host_name() {
    return copied_name.c_str();
}
extern "C" const char* codex_agent_cpp_mock_host_title() {
    return copied_title.c_str();
}
extern "C" const char* codex_agent_cpp_mock_host_version() {
    return copied_version.c_str();
}
extern "C" const char* codex_agent_cpp_mock_host_selection() {
    return copied_selection.c_str();
}
extern "C" int codex_agent_cpp_mock_host_identity_stable() {
    return identity_stable ? 1 : 0;
}
extern "C" std::size_t codex_agent_cpp_mock_host_premature_releases() {
    return premature_releases;
}
extern "C" std::size_t codex_agent_cpp_mock_host_context_destroys() {
    return context_destroys;
}
extern "C" std::size_t codex_agent_cpp_mock_host_ready_projections() {
    return ready_projections;
}
extern "C" std::size_t codex_agent_cpp_mock_host_agent_retains() {
    return agent_retains;
}
extern "C" std::size_t codex_agent_cpp_mock_host_agent_releases() {
    return agent_releases;
}
extern "C" int codex_agent_cpp_mock_host_release_order() {
    const auto workspace = release_position("workspace");
    const auto agent = release_position("agent-last");
    const auto host = release_position("host-last");
    const auto context = release_position("context");
    return workspace < agent && agent < host && host < context ? 1 : 0;
}

extern "C" std::int32_t CODEX_AGENT_CALL codex_agent_abi_is_compatible(
    std::uint32_t requested_version) {
    return requested_version >= CODEX_AGENT_ABI_VERSION_MINIMUM_COMPATIBLE &&
           requested_version <= CODEX_AGENT_ABI_VERSION_CURRENT;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL codex_agent_context_create(
    codex_agent_context_t** out_context) {
    if (out_context == nullptr || *out_context != nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_context = new codex_agent_context{};
    return CODEX_AGENT_STATUS_OK;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL codex_agent_context_destroy(
    codex_agent_context_t** context) {
    if (context == nullptr || *context == nullptr)
        return context == nullptr ? CODEX_AGENT_STATUS_INVALID_ARGUMENT
                                  : CODEX_AGENT_STATUS_OK;
    releases.emplace_back("context");
    ++context_destroys;
    delete *context;
    *context = nullptr;
    return CODEX_AGENT_STATUS_OK;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_create(
    codex_agent_context_t* context, const codex_agent_host_options_t* options,
    codex_agent_host_t** out_host) {
    record(HostNativeEdge::codex_agent_host_create);
    if (context == nullptr || options == nullptr || out_host == nullptr ||
        *out_host != nullptr || options->struct_size != sizeof(*options) ||
        options->client_info.struct_size != sizeof(options->client_info)) {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    copied_bundle = from_view(options->bundle_directory);
    copied_data = from_view(options->data_directory);
    copied_name = from_view(options->client_info.name);
    copied_title = from_view(options->client_info.title);
    copied_version = from_view(options->client_info.version);
    if (copied_bundle.empty() || copied_data.empty() || copied_name.empty() ||
        copied_title.empty() || copied_version.empty()) {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    auto model = std::make_shared<host_model>();
    model->live_hosts = 1;
    *out_host = new codex_agent_host{context, std::move(model)};
    return CODEX_AGENT_STATUS_OK;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_retain(
    codex_agent_context_t* context, codex_agent_host_t* host,
    codex_agent_host_t** out_host) {
    if (context == nullptr || host == nullptr || out_host == nullptr ||
        *out_host != nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    ++host->model->live_hosts;
    *out_host = new codex_agent_host{context, host->model};
    return CODEX_AGENT_STATUS_OK;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_release(
    codex_agent_context_t*, codex_agent_host_t** host) {
    if (host == nullptr || *host == nullptr)
        return host == nullptr ? CODEX_AGENT_STATUS_INVALID_ARGUMENT
                               : CODEX_AGENT_STATUS_OK;
    auto model = (*host)->model;
    if (model->live_hosts == 1 && model->live_agents != 0) {
        ++premature_releases;
        return CODEX_AGENT_STATUS_INTERNAL_ERROR;
    }
    if (--model->live_hosts == 0) releases.emplace_back("host-last");
    delete *host;
    *host = nullptr;
    return CODEX_AGENT_STATUS_OK;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_start(
    codex_agent_context_t* context, codex_agent_host_t* host,
    codex_agent_operation_callback_t callback, void* user_data,
    codex_agent_operation_t** out_operation) {
    record(HostNativeEdge::codex_agent_host_start);
    if (host == nullptr) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return launch(context, callback, user_data, out_operation);
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL
codex_agent_host_select_workspace(
    codex_agent_context_t* context, codex_agent_host_t* host,
    const codex_agent_path_workspace_selection_t* selection,
    codex_agent_operation_callback_t callback, void* user_data,
    codex_agent_operation_t** out_operation) {
    record(HostNativeEdge::codex_agent_host_select_workspace);
    if (host == nullptr || selection == nullptr ||
        selection->struct_size != sizeof(*selection))
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    copied_selection = from_view(selection->path);
    if (copied_selection.empty()) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return launch(context, callback, user_data, out_operation);
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_close(
    codex_agent_context_t* context, codex_agent_host_t* host,
    codex_agent_operation_callback_t callback, void* user_data,
    codex_agent_operation_t** out_operation) {
    record(HostNativeEdge::codex_agent_host_close);
    if (host == nullptr) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    const bool changes_state = !delay_next && !fail_next;
    const auto status = launch(context, callback, user_data, out_operation);
    if (status == CODEX_AGENT_STATUS_OK && changes_state)
        host->model->state = CODEX_AGENT_HOST_STATE_CLOSED;
    return status;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_state_get(
    codex_agent_context_t*, codex_agent_host_t* host,
    codex_agent_snapshot_t** out_snapshot) {
    record(HostNativeEdge::codex_agent_host_state_get);
    if (host == nullptr || out_snapshot == nullptr || *out_snapshot != nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_snapshot = snapshot(host->model);
    return CODEX_AGENT_STATUS_OK;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL
codex_agent_host_state_subscribe(
    codex_agent_context_t* context, codex_agent_host_t* host,
    codex_agent_state_callback_t callback, void* user_data,
    codex_agent_subscription_t** out_subscription) {
    record(HostNativeEdge::codex_agent_host_state_subscribe);
    if (context == nullptr || host == nullptr || callback == nullptr ||
        out_subscription == nullptr || *out_subscription != nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    auto* subscription = new codex_agent_subscription{
        context, callback, user_data, host->model};
    {
        std::lock_guard lock(subscriptions_mutex);
        subscriptions.push_back(subscription);
    }
    *out_subscription = subscription;
    callback(context, subscription, CODEX_AGENT_STATUS_OK,
             snapshot(host->model), 0, user_data);
    return CODEX_AGENT_STATUS_OK;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_state_kind(
    codex_agent_context_t*, codex_agent_snapshot_t* value,
    codex_agent_host_state_kind_t* out_kind) {
    record(HostNativeEdge::codex_agent_host_state_kind);
    if (value == nullptr || out_kind == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_kind = value->state;
    return CODEX_AGENT_STATUS_OK;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL
codex_agent_host_state_has_workspace(
    codex_agent_context_t*, codex_agent_snapshot_t* value,
    std::int32_t* out_has_workspace) {
    if (value == nullptr || out_has_workspace == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_has_workspace = value->state == CODEX_AGENT_HOST_STATE_READY ? 1 : 0;
    return CODEX_AGENT_STATUS_OK;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL
codex_agent_host_state_workspace_path_copy(
    codex_agent_context_t*, codex_agent_snapshot_t* value,
    std::uint8_t* buffer, std::size_t capacity, std::size_t* out_required) {
    if (value == nullptr) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return copy_string(value->path, buffer, capacity, out_required);
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL
codex_agent_host_state_workspace_display_name_copy(
    codex_agent_context_t*, codex_agent_snapshot_t* value,
    std::uint8_t* buffer, std::size_t capacity, std::size_t* out_required) {
    if (value == nullptr) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return copy_string(value->name, buffer, capacity, out_required);
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_state_agent(
    codex_agent_context_t* context, codex_agent_host_t* host,
    codex_agent_snapshot_t* value, codex_agent_agent_t** out_agent) {
    record(HostNativeEdge::codex_agent_host_state_agent);
    if (context == nullptr || host == nullptr || value == nullptr ||
        out_agent == nullptr || *out_agent != nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (host->model->state != CODEX_AGENT_HOST_STATE_READY ||
        value->state != CODEX_AGENT_HOST_STATE_READY)
        return CODEX_AGENT_STATUS_NOT_READY;
    auto model = std::make_shared<agent_model>();
    model->host = host->model;
    model->identity = host->model->agent_identity;
    if (projected_agent)
        identity_stable = projected_agent->identity == model->identity;
    projected_agent = model;
    ++ready_projections;
    ++host->model->live_agents;
    *out_agent = new codex_agent_agent{context, std::move(model)};
    return CODEX_AGENT_STATUS_OK;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL codex_agent_agent_retain(
    codex_agent_context_t* context, codex_agent_agent_t* agent,
    codex_agent_agent_t** out_agent) {
    if (context == nullptr || agent == nullptr || out_agent == nullptr ||
        *out_agent != nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    ++agent_retains;
    ++agent->model->host->live_agents;
    *out_agent = new codex_agent_agent{context, agent->model};
    return CODEX_AGENT_STATUS_OK;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL codex_agent_agent_release(
    codex_agent_context_t*, codex_agent_agent_t** agent) {
    if (agent == nullptr || *agent == nullptr)
        return agent == nullptr ? CODEX_AGENT_STATUS_INVALID_ARGUMENT
                                : CODEX_AGENT_STATUS_OK;
    auto model = (*agent)->model->host;
    ++agent_releases;
    if (--model->live_agents == 0) releases.emplace_back("agent-last");
    delete *agent;
    *agent = nullptr;
    return CODEX_AGENT_STATUS_OK;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL codex_agent_agent_workspace(
    codex_agent_context_t*, codex_agent_agent_t* agent,
    codex_agent_workspace_t** out_workspace) {
    if (agent == nullptr || out_workspace == nullptr || *out_workspace != nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_workspace = new codex_agent_workspace{
        agent->model->host->workspace_path, agent->model->host->workspace_name};
    return CODEX_AGENT_STATUS_OK;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL codex_agent_workspace_destroy(
    codex_agent_context_t*, codex_agent_workspace_t** workspace) {
    if (workspace == nullptr || *workspace == nullptr)
        return workspace == nullptr ? CODEX_AGENT_STATUS_INVALID_ARGUMENT
                                    : CODEX_AGENT_STATUS_OK;
    releases.emplace_back("workspace");
    delete *workspace;
    *workspace = nullptr;
    return CODEX_AGENT_STATUS_OK;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL
codex_agent_workspace_path_copy(
    codex_agent_context_t*, codex_agent_workspace_t* workspace,
    std::uint8_t* buffer, std::size_t capacity, std::size_t* out_required) {
    if (workspace == nullptr) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return copy_string(workspace->path, buffer, capacity, out_required);
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL
codex_agent_workspace_display_name_copy(
    codex_agent_context_t*, codex_agent_workspace_t* workspace,
    std::uint8_t* buffer, std::size_t capacity, std::size_t* out_required) {
    if (workspace == nullptr) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return copy_string(workspace->name, buffer, capacity, out_required);
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_result(
    codex_agent_context_t*, codex_agent_operation_t* operation,
    codex_agent_status_t* out_result) {
    record(HostNativeEdge::codex_agent_operation_result);
    if (operation == nullptr || out_result == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_result = operation->result;
    return CODEX_AGENT_STATUS_OK;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_cancel(
    codex_agent_context_t*, codex_agent_operation_t* operation) {
    if (operation == nullptr) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (!operation->completed) {
        if (pending_operation == operation) pending_operation = nullptr;
        operation->result = CODEX_AGENT_STATUS_CANCELLED;
        operation->completed = true;
        operation->callback(
            operation->context, operation, operation->user_data);
    }
    return CODEX_AGENT_STATUS_OK;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_failure(
    codex_agent_context_t*, codex_agent_operation_t* operation,
    codex_agent_failure_t** out_failure) {
    if (operation == nullptr || out_failure == nullptr || *out_failure != nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    if (operation->result != CODEX_AGENT_STATUS_OPERATION_FAILED)
        return CODEX_AGENT_STATUS_NOT_READY;
    *out_failure = new codex_agent_failure{
        "host_failed", "mock host operation failed", 1};
    return CODEX_AGENT_STATUS_OK;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_destroy(
    codex_agent_context_t*, codex_agent_operation_t** operation) {
    if (operation == nullptr || *operation == nullptr)
        return operation == nullptr ? CODEX_AGENT_STATUS_INVALID_ARGUMENT
                                    : CODEX_AGENT_STATUS_OK;
    delete *operation;
    *operation = nullptr;
    return CODEX_AGENT_STATUS_OK;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL
codex_agent_subscription_destroy(
    codex_agent_context_t*, codex_agent_subscription_t** subscription) {
    if (subscription == nullptr || *subscription == nullptr)
        return subscription == nullptr ? CODEX_AGENT_STATUS_INVALID_ARGUMENT
                                       : CODEX_AGENT_STATUS_OK;
    auto* value = *subscription;
    if (!value->terminal_started.exchange(true)) {
        std::thread([value] {
            value->callback(value->context, value, CODEX_AGENT_STATUS_CANCELLED,
                            nullptr, 1, value->user_data);
            value->terminal_finished = true;
        }).detach();
        return CODEX_AGENT_STATUS_BUSY;
    }
    if (!value->terminal_finished.load()) return CODEX_AGENT_STATUS_BUSY;
    {
        std::lock_guard lock(subscriptions_mutex);
        subscriptions.erase(
            std::remove(subscriptions.begin(), subscriptions.end(), value),
            subscriptions.end());
    }
    delete value;
    *subscription = nullptr;
    return CODEX_AGENT_STATUS_OK;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL codex_agent_snapshot_destroy(
    codex_agent_context_t*, codex_agent_snapshot_t** value) {
    if (value == nullptr || *value == nullptr)
        return value == nullptr ? CODEX_AGENT_STATUS_INVALID_ARGUMENT
                                : CODEX_AGENT_STATUS_OK;
    delete *value;
    *value = nullptr;
    return CODEX_AGENT_STATUS_OK;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL codex_agent_failure_release(
    codex_agent_context_t*, codex_agent_failure_t** failure) {
    if (failure == nullptr || *failure == nullptr)
        return failure == nullptr ? CODEX_AGENT_STATUS_INVALID_ARGUMENT
                                  : CODEX_AGENT_STATUS_OK;
    delete *failure;
    *failure = nullptr;
    return CODEX_AGENT_STATUS_OK;
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL codex_agent_failure_code_copy(
    codex_agent_context_t*, codex_agent_failure_t* failure,
    std::uint8_t* buffer, std::size_t capacity, std::size_t* out_required) {
    if (failure == nullptr) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return copy_string(failure->code, buffer, capacity, out_required);
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL
codex_agent_failure_message_copy(
    codex_agent_context_t*, codex_agent_failure_t* failure,
    std::uint8_t* buffer, std::size_t capacity, std::size_t* out_required) {
    if (failure == nullptr) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return copy_string(failure->message, buffer, capacity, out_required);
}

extern "C" codex_agent_status_t CODEX_AGENT_CALL
codex_agent_failure_is_recoverable(
    codex_agent_context_t*, codex_agent_failure_t* failure,
    std::int32_t* out_recoverable) {
    if (failure == nullptr || out_recoverable == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_recoverable = failure->recoverable;
    return CODEX_AGENT_STATUS_OK;
}
