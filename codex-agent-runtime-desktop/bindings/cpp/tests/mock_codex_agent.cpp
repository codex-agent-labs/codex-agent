#include <codex_agent.h>

#include <atomic>
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <memory>
#include <optional>
#include <string>
#include <thread>
#include <vector>

#include "conversation_native_probe.hpp"

struct codex_agent_context {};
struct host_model {
    codex_agent_host_state_kind_t state = CODEX_AGENT_HOST_STATE_READY;
};
struct codex_agent_host {
    codex_agent_context_t* context;
    std::shared_ptr<host_model> model;
};
struct codex_agent_agent {
    codex_agent_context_t* context;
};
struct conversation_model;
struct codex_agent_conversations {
    codex_agent_context_t* context;
    std::shared_ptr<conversation_model> active;
};
struct conversation_model {
    int id = 1;
    codex_agent_conversation_status_t status = CODEX_AGENT_CONVERSATION_STATUS_READY;
};
struct codex_agent_conversation {
    codex_agent_context_t* context;
    std::shared_ptr<conversation_model> model;
};
struct codex_agent_failure {
    std::string code;
    std::string message;
    int32_t recoverable;
};
struct codex_agent_conversation_id {
    std::string value;
};
struct codex_agent_conversation_summary {
    std::string id;
    std::string title;
    int64_t updated_at_epoch_seconds;
};
struct codex_agent_invocation_plugin {
    std::string name;
    std::string uri;
};
struct codex_agent_invocation_skill {
    std::string name;
    std::string path;
};
struct codex_agent_invocation {
    codex_agent_invocation_kind_t kind;
    std::string key;
    std::string name;
    std::string location;
};
struct codex_agent_turn_request {
    std::string prompt;
    std::optional<std::string> client_message_id;
    std::optional<std::string> model;
    std::optional<std::string> effort;
    std::optional<std::string> service_tier;
    codex_agent_approval_preset_t approval_preset;
    std::vector<codex_agent_capability_t> capabilities;
    std::vector<codex_agent_invocation> invocations;
    codex_agent_collaboration_mode_t collaboration_mode;
};
struct codex_agent_message {
    std::string id;
    codex_agent_message_role_t role = CODEX_AGENT_MESSAGE_ROLE_ASSISTANT;
    std::string text;
    std::optional<std::string> client_message_id;
    std::optional<std::string> reasoning;
    std::optional<std::string> plan;
    std::optional<std::string> shell_command;
    std::optional<std::int32_t> exit_code;
    std::vector<codex_agent_capability_t> capabilities;
    std::vector<codex_agent_invocation> invocations;
    codex_agent_collaboration_mode_t collaboration_mode =
        CODEX_AGENT_COLLABORATION_MODE_DEFAULT;
};
struct codex_agent_conversation_value {
    codex_agent_conversation_summary summary;
    std::vector<codex_agent_message> messages;
};
struct codex_agent_plan_step {};
struct codex_agent_plan_progress {};
struct codex_agent_hook_activity {};
struct codex_agent_turn_progress { int phase = 0; };
struct codex_agent_operation {
    std::atomic<codex_agent_status_t> result{CODEX_AGENT_STATUS_OK};
    std::atomic<bool> callback_fired{false};
    bool returns_conversation = false;
    bool returns_summaries = false;
    bool returns_conversation_value = false;
    std::shared_ptr<conversation_model> conversation;
    codex_agent_context_t* context = nullptr;
    codex_agent_operation_callback_t callback = nullptr;
    void* user_data = nullptr;
    std::string failure_code;
    std::string failure_message;
};
enum class snapshot_kind {
    host,
    conversation,
    active,
    active_progress,
    can_cancel,
    can_reload,
    can_shell,
    can_start,
    messages,
    is_active,
};
struct codex_agent_snapshot {
    snapshot_kind kind;
    codex_agent_host_state_kind_t host_state = CODEX_AGENT_HOST_STATE_READY;
    codex_agent_conversation_status_t conversation_state =
        CODEX_AGENT_CONVERSATION_STATUS_READY;
    int phase = 0;
    std::shared_ptr<conversation_model> conversation;
};
struct codex_agent_subscription {
    codex_agent_context_t* context;
    codex_agent_state_callback_t callback;
    void* user_data;
    snapshot_kind kind;
    codex_agent_host_state_kind_t host_state;
    codex_agent_conversation_status_t conversation_state;
    int phase = 0;
    std::shared_ptr<conversation_model> conversation;
    std::atomic<bool> cancelled{false};
    std::atomic<bool> terminal_started{false};
    std::atomic<bool> terminal_finished{false};
    std::atomic<int> workers{0};
};

namespace {

std::vector<ConversationNativeEdge> conversation_events;
std::vector<codex_agent_subscription_t*> conversation_subscriptions;
std::array<int, 10> conversation_phases{};
bool conversation_delay_next = false;
bool conversation_fail_next = false;
struct PendingConversationCompletion {
    codex_agent_context_t* context = nullptr;
    codex_agent_operation_t* operation = nullptr;
    codex_agent_operation_callback_t callback = nullptr;
    void* user_data = nullptr;
} pending_conversation_completion;

void record(ConversationNativeEdge edge) {
    conversation_events.push_back(edge);
}

codex_agent_message message_value(int phase, std::size_t index) {
    codex_agent_message result;
    result.id = index == 0 ? "message-a" : "message-b";
    result.role = index == 0 ? CODEX_AGENT_MESSAGE_ROLE_USER
                             : CODEX_AGENT_MESSAGE_ROLE_ASSISTANT;
    result.text = (phase == 0 ? "current-" : "changed-") +
                  std::to_string(index);
    if (index == 0) {
        result.client_message_id = "client-message";
        result.reasoning = "reasoning";
        result.plan = "plan";
        result.shell_command = "pwd";
        result.exit_code = 0;
        result.capabilities.push_back(CODEX_AGENT_CAPABILITY_WEB_SEARCH);
        result.collaboration_mode = CODEX_AGENT_COLLABORATION_MODE_PLAN;
    }
    return result;
}

codex_agent_conversation_value conversation_value(int phase = 0) {
    return {{"conversation-a", "Conversation", 123},
            {message_value(phase, 0), message_value(phase, 1)}};
}

codex_agent_conversation_status_t conversation_status(
    snapshot_kind kind, int phase,
    const std::shared_ptr<conversation_model>& conversation) {
    if (kind == snapshot_kind::conversation && phase == 2)
        return CODEX_AGENT_CONVERSATION_STATUS_FAILED;
    if (kind == snapshot_kind::conversation && phase == 1)
        return CODEX_AGENT_CONVERSATION_STATUS_RUNNING_TURN;
    return conversation ? conversation->status
                        : CODEX_AGENT_CONVERSATION_STATUS_READY;
}

std::string from_view(const codex_agent_string_view_t& value) {
    return std::string(reinterpret_cast<const char*>(value.data), value.size);
}

codex_agent_status_t copy_string(
    const std::string& value,
    uint8_t* buffer,
    size_t capacity,
    size_t* out_required) {
    if (out_required == nullptr) {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    *out_required = value.size();
    if (capacity < value.size()) {
        return CODEX_AGENT_STATUS_BUFFER_TOO_SMALL;
    }
    if (!value.empty()) {
        if (buffer == nullptr) {
            return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
        }
        std::memcpy(buffer, value.data(), value.size());
    }
    return CODEX_AGENT_STATUS_OK;
}

template <typename Handle>
codex_agent_status_t destroy(Handle** handle) {
    if (handle == nullptr) {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    delete *handle;
    *handle = nullptr;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t complete(
    codex_agent_context_t* context,
    codex_agent_operation_t* operation,
    codex_agent_operation_callback_t callback,
    void* user_data,
    codex_agent_operation_t** out_operation) {
    operation->context = context;
    *out_operation = operation;
    if (conversation_fail_next) {
        conversation_fail_next = false;
        operation->result = CODEX_AGENT_STATUS_OPERATION_FAILED;
        operation->failure_code = "conversation_failed";
        operation->failure_message = "mock conversation failure";
    }
    if (conversation_delay_next) {
        conversation_delay_next = false;
        pending_conversation_completion = {
            context, operation, callback, user_data};
        operation->callback = callback;
        operation->user_data = user_data;
        return CODEX_AGENT_STATUS_OK;
    }
    callback(context, operation, user_data);
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t complete_void(
    codex_agent_context_t* context,
    codex_agent_operation_callback_t callback,
    void* user_data,
    codex_agent_operation_t** out_operation) {
    return complete(
        context, new codex_agent_operation{}, callback, user_data, out_operation);
}

void publish_subsequent(codex_agent_subscription_t* subscription) {
    ++subscription->workers;
    std::thread([subscription] {
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
        if (!subscription->cancelled.load()) {
            auto* snapshot = new codex_agent_snapshot{
                subscription->kind,
                subscription->host_state,
                subscription->conversation_state,
                subscription->phase,
                subscription->conversation,
            };
            subscription->callback(
                subscription->context,
                subscription,
                CODEX_AGENT_STATUS_OK,
                snapshot,
                0,
                subscription->user_data);
        }
        --subscription->workers;
    }).detach();
}

codex_agent_status_t publish_conversation_state(
    codex_agent_context_t* context,
    std::shared_ptr<conversation_model> conversation,
    snapshot_kind kind,
    codex_agent_state_callback_t callback,
    void* user_data,
    codex_agent_subscription_t** out_subscription) {
    if (context == nullptr || callback == nullptr || out_subscription == nullptr ||
        *out_subscription != nullptr) {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    auto* subscription = new codex_agent_subscription{
        context, callback, user_data, kind, CODEX_AGENT_HOST_STATE_READY,
        conversation_status(
            kind, conversation_phases.at(static_cast<std::size_t>(kind)),
            conversation),
        conversation_phases.at(static_cast<std::size_t>(kind)), conversation};
    *out_subscription = subscription;
    conversation_subscriptions.push_back(subscription);
    callback(
        context, subscription, CODEX_AGENT_STATUS_OK,
        new codex_agent_snapshot{
            kind, CODEX_AGENT_HOST_STATE_READY,
            subscription->conversation_state, subscription->phase,
            std::move(conversation)},
        0, user_data);
    return CODEX_AGENT_STATUS_OK;
}

}  // namespace

void codex_agent_cpp_mock_conversation_reset() {
    conversation_events.clear();
}

std::size_t codex_agent_cpp_mock_conversation_event_count() {
    return conversation_events.size();
}

ConversationNativeEdge codex_agent_cpp_mock_conversation_event_at(
    std::size_t index) {
    return conversation_events.at(index);
}

void codex_agent_cpp_mock_conversation_delay_next_operation() {
    conversation_delay_next = true;
}

void codex_agent_cpp_mock_conversation_complete_pending_operation() {
    if (pending_conversation_completion.callback == nullptr) return;
    const auto pending = pending_conversation_completion;
    pending_conversation_completion = {};
    pending.callback(pending.context, pending.operation, pending.user_data);
}

void codex_agent_cpp_mock_conversation_set_failure() {
    conversation_fail_next = true;
}

void codex_agent_cpp_mock_conversation_set_phase(int kind, int phase) {
    conversation_phases.at(static_cast<std::size_t>(kind)) = phase;
}

void codex_agent_cpp_mock_conversation_publish(int kind, int terminal) {
    const auto wanted = static_cast<snapshot_kind>(kind);
    for (auto* subscription : conversation_subscriptions) {
        if (subscription == nullptr || subscription->cancelled.load() ||
            subscription->kind != wanted) {
            continue;
        }
        subscription->phase = conversation_phases.at(
            static_cast<std::size_t>(wanted));
        subscription->conversation_state = conversation_status(
            wanted, subscription->phase, subscription->conversation);
        subscription->callback(
            subscription->context, subscription,
            terminal != 0 ? CODEX_AGENT_STATUS_CANCELLED
                          : CODEX_AGENT_STATUS_OK,
            terminal != 0
                ? nullptr
                : new codex_agent_snapshot{
                      wanted, subscription->host_state,
                      subscription->conversation_state,
                      subscription->phase, subscription->conversation},
            terminal, subscription->user_data);
    }
}

extern "C" {

uint32_t CODEX_AGENT_CALL codex_agent_abi_version(void) {
    return CODEX_AGENT_ABI_VERSION_CURRENT;
}

int32_t CODEX_AGENT_CALL codex_agent_abi_is_compatible(uint32_t requested_version) {
    return requested_version >= CODEX_AGENT_ABI_VERSION_MINIMUM_COMPATIBLE &&
           requested_version <= CODEX_AGENT_ABI_VERSION_CURRENT;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_context_create(
    codex_agent_context_t** out_context) {
    if (out_context == nullptr || *out_context != nullptr) {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    *out_context = new codex_agent_context{};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_context_destroy(
    codex_agent_context_t** context) {
    return destroy(context);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_create(
    codex_agent_context_t* context,
    const codex_agent_host_options_t* options,
    codex_agent_host_t** out_host) {
    if (context == nullptr || options == nullptr || out_host == nullptr ||
        *out_host != nullptr || options->struct_size != sizeof(*options) ||
        from_view(options->bundle_directory).empty() ||
        from_view(options->data_directory).empty() ||
        from_view(options->client_info.name).empty()) {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    *out_host = new codex_agent_host{context, std::make_shared<host_model>()};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_retain(
    codex_agent_context_t*, codex_agent_host_t* host, codex_agent_host_t** out_host) {
    *out_host = new codex_agent_host{host->context, host->model};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_release(
    codex_agent_context_t*, codex_agent_host_t** host) {
    return destroy(host);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_start(
    codex_agent_context_t* context,
    codex_agent_host_t*,
    codex_agent_operation_callback_t callback,
    void* user_data,
    codex_agent_operation_t** out_operation) {
    return complete_void(context, callback, user_data, out_operation);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_select_workspace(
    codex_agent_context_t* context,
    codex_agent_host_t*,
    const codex_agent_path_workspace_selection_t* selection,
    codex_agent_operation_callback_t callback,
    void* user_data,
    codex_agent_operation_t** out_operation) {
    if (selection == nullptr || from_view(selection->path).empty()) {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    return complete_void(context, callback, user_data, out_operation);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_close(
    codex_agent_context_t* context,
    codex_agent_host_t* host,
    codex_agent_operation_callback_t callback,
    void* user_data,
    codex_agent_operation_t** out_operation) {
    host->model->state = CODEX_AGENT_HOST_STATE_CLOSED;
    return complete_void(context, callback, user_data, out_operation);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_state_get(
    codex_agent_context_t*,
    codex_agent_host_t* host,
    codex_agent_snapshot_t** out_snapshot) {
    *out_snapshot = new codex_agent_snapshot{
        snapshot_kind::host, host->model->state,
        CODEX_AGENT_CONVERSATION_STATUS_READY, 0, nullptr};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_state_subscribe(
    codex_agent_context_t* context,
    codex_agent_host_t* host,
    codex_agent_state_callback_t callback,
    void* user_data,
    codex_agent_subscription_t** out_subscription) {
    auto* subscription = new codex_agent_subscription{
        context,
        callback,
        user_data,
        snapshot_kind::host,
        host->model->state,
        CODEX_AGENT_CONVERSATION_STATUS_READY,
        0,
        nullptr,
    };
    *out_subscription = subscription;
    callback(
        context,
        subscription,
        CODEX_AGENT_STATUS_OK,
        new codex_agent_snapshot{
            snapshot_kind::host, host->model->state,
            CODEX_AGENT_CONVERSATION_STATUS_READY, 0, nullptr},
        0,
        user_data);
    publish_subsequent(subscription);
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_state_kind(
    codex_agent_context_t*,
    codex_agent_snapshot_t* snapshot,
    codex_agent_host_state_kind_t* out_kind) {
    *out_kind = snapshot->host_state;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_state_has_workspace(
    codex_agent_context_t*, codex_agent_snapshot_t*, int32_t* out_has_workspace) {
    *out_has_workspace = 1;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_state_workspace_path_copy(
    codex_agent_context_t*, codex_agent_snapshot_t*, uint8_t* buffer,
    size_t capacity, size_t* out_required) {
    return copy_string("/workspace", buffer, capacity, out_required);
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_host_state_workspace_display_name_copy(
    codex_agent_context_t*, codex_agent_snapshot_t*, uint8_t*,
    size_t, size_t*) {
    return CODEX_AGENT_STATUS_NOT_READY;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_state_requirement_reason(
    codex_agent_context_t*, codex_agent_snapshot_t*,
    codex_agent_workspace_selection_reason_t*) {
    return CODEX_AGENT_STATUS_NOT_READY;
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_host_state_requirement_message_copy(
    codex_agent_context_t*, codex_agent_snapshot_t*, uint8_t*, size_t, size_t*) {
    return CODEX_AGENT_STATUS_NOT_READY;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_state_failure(
    codex_agent_context_t*, codex_agent_snapshot_t*, codex_agent_failure_t**) {
    return CODEX_AGENT_STATUS_NOT_READY;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_host_state_agent(
    codex_agent_context_t* context,
    codex_agent_host_t* host,
    codex_agent_snapshot_t* snapshot,
    codex_agent_agent_t** out_agent) {
    if (host->model->state != CODEX_AGENT_HOST_STATE_READY ||
        snapshot->host_state != CODEX_AGENT_HOST_STATE_READY) {
        return CODEX_AGENT_STATUS_NOT_READY;
    }
    *out_agent = new codex_agent_agent{context};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_agent_release(
    codex_agent_context_t*, codex_agent_agent_t** agent) {
    return destroy(agent);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_agent_retain(
    codex_agent_context_t*, codex_agent_agent_t* agent,
    codex_agent_agent_t** out_agent) {
    *out_agent = new codex_agent_agent{agent->context};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_agent_conversations(
    codex_agent_context_t* context,
    codex_agent_agent_t*,
    codex_agent_conversations_t** out_conversations) {
    *out_conversations = new codex_agent_conversations{
        context, std::make_shared<conversation_model>()};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversations_release(
    codex_agent_context_t*, codex_agent_conversations_t** conversations) {
    return destroy(conversations);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversations_retain(
    codex_agent_context_t*, codex_agent_conversations_t* conversations,
    codex_agent_conversations_t** out_conversations) {
    *out_conversations = new codex_agent_conversations{
        conversations->context, conversations->active};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversations_open(
    codex_agent_context_t* context,
    codex_agent_conversations_t* conversations,
    const codex_agent_conversation_open_options_t* options,
    codex_agent_operation_callback_t callback,
    void* user_data,
    codex_agent_operation_t** out_operation) {
    record(ConversationNativeEdge::codex_agent_conversations_open);
    if (context == nullptr || conversations == nullptr || options == nullptr ||
        options->struct_size != sizeof(*options)) {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    const auto id = from_view(options->conversation_id);
    const auto tier = from_view(options->service_tier);
    const auto default_options =
        options->has_conversation_id == 0 &&
        options->has_approval_preset != 0 &&
        options->approval_preset == CODEX_AGENT_APPROVAL_PRESET_AUTO_REVIEW &&
        options->has_service_tier == 0;
    const auto full_options =
        options->has_conversation_id != 0 &&
        (id == "conversation-a" || id == "conversation-1") &&
        options->has_approval_preset != 0 &&
        options->approval_preset == CODEX_AGENT_APPROVAL_PRESET_ASK_ME &&
        options->has_service_tier != 0 && tier == "priority";
    if (!default_options && !full_options) {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    auto* operation = new codex_agent_operation{};
    operation->returns_conversation = true;
    operation->conversation = conversations->active;
    return complete(context, operation, callback, user_data, out_operation);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversations_list(
    codex_agent_context_t* context,
    codex_agent_conversations_t*,
    codex_agent_operation_callback_t callback,
    void* user_data,
    codex_agent_operation_t** out_operation) {
    record(ConversationNativeEdge::codex_agent_conversations_list);
    auto* operation = new codex_agent_operation{};
    operation->returns_summaries = true;
    return complete(context, operation, callback, user_data, out_operation);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversations_read(
    codex_agent_context_t* context,
    codex_agent_conversations_t* conversations,
    codex_agent_conversation_id_t* conversation_id,
    codex_agent_operation_callback_t callback,
    void* user_data,
    codex_agent_operation_t** out_operation) {
    record(ConversationNativeEdge::codex_agent_conversations_read);
    if (conversations == nullptr || conversation_id == nullptr ||
        conversation_id->value != "conversation-a") {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    auto* operation = new codex_agent_operation{};
    operation->returns_conversation_value = true;
    return complete(context, operation, callback, user_data, out_operation);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversations_rename(
    codex_agent_context_t* context,
    codex_agent_conversations_t* conversations,
    codex_agent_conversation_id_t* conversation_id,
    const codex_agent_string_view_t* title,
    codex_agent_operation_callback_t callback,
    void* user_data,
    codex_agent_operation_t** out_operation) {
    record(ConversationNativeEdge::codex_agent_conversations_rename);
    if (conversations == nullptr || conversation_id == nullptr ||
        title == nullptr || conversation_id->value != "conversation-a" ||
        from_view(*title) != "Renamed") {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    return complete_void(context, callback, user_data, out_operation);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversations_delete(
    codex_agent_context_t* context,
    codex_agent_conversations_t* conversations,
    codex_agent_conversation_id_t* conversation_id,
    codex_agent_operation_callback_t callback,
    void* user_data,
    codex_agent_operation_t** out_operation) {
    record(ConversationNativeEdge::codex_agent_conversations_delete);
    if (conversations == nullptr || conversation_id == nullptr ||
        conversation_id->value != "conversation-a") {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    return complete_void(context, callback, user_data, out_operation);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversations_active_get(
    codex_agent_context_t*, codex_agent_conversations_t* conversations,
    codex_agent_snapshot_t** out_snapshot) {
    record(ConversationNativeEdge::codex_agent_conversations_active_get);
    if (conversations == nullptr || out_snapshot == nullptr ||
        *out_snapshot != nullptr) {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    *out_snapshot = new codex_agent_snapshot{
        snapshot_kind::active, CODEX_AGENT_HOST_STATE_READY,
        conversations->active->status,
        conversation_phases[static_cast<std::size_t>(snapshot_kind::active)],
        conversations->active};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversations_active_subscribe(
    codex_agent_context_t* context, codex_agent_conversations_t* conversations,
    codex_agent_state_callback_t callback, void* user_data,
    codex_agent_subscription_t** out_subscription) {
    record(ConversationNativeEdge::codex_agent_conversations_active_subscribe);
    return publish_conversation_state(
        context, conversations ? conversations->active : nullptr,
        snapshot_kind::active, callback, user_data, out_subscription);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_active_conversation(
    codex_agent_context_t*, codex_agent_conversations_t* conversations,
    codex_agent_snapshot_t* snapshot,
    codex_agent_conversation_t** out_conversation) {
    record(ConversationNativeEdge::codex_agent_active_conversation);
    if (conversations == nullptr || snapshot == nullptr ||
        snapshot->kind != snapshot_kind::active || out_conversation == nullptr ||
        *out_conversation != nullptr) {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    if (snapshot->phase == 0) return CODEX_AGENT_STATUS_NOT_READY;
    *out_conversation = new codex_agent_conversation{
        conversations->context, snapshot->conversation};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_release(
    codex_agent_context_t*, codex_agent_conversation_t** conversation) {
    return destroy(conversation);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_conversation(
    codex_agent_context_t* context,
    codex_agent_conversations_t*,
    codex_agent_operation_t* operation,
    codex_agent_conversation_t** out_conversation) {
    if (!operation->returns_conversation) {
        return CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE;
    }
    *out_conversation = new codex_agent_conversation{
        context, operation->conversation};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_retain(
    codex_agent_context_t*, codex_agent_conversation_t* conversation,
    codex_agent_conversation_t** out_conversation) {
    *out_conversation = new codex_agent_conversation{
        conversation->context, conversation->model};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_is_same(
    codex_agent_context_t*,
    codex_agent_conversation_t* left,
    codex_agent_conversation_t* right,
    int32_t* out_same) {
    *out_same = left->model->id == right->model->id;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_send(
    codex_agent_context_t* context,
    codex_agent_conversation_t*,
    const codex_agent_string_view_t* prompt,
    codex_agent_operation_callback_t callback,
    void* user_data,
    codex_agent_operation_t** out_operation) {
    record(ConversationNativeEdge::codex_agent_conversation_send);
    if (prompt == nullptr) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    const auto value = from_view(*prompt);
    auto* operation = new codex_agent_operation{};
    operation->context = context;
    *out_operation = operation;
    if (value == "fail") {
        operation->result = CODEX_AGENT_STATUS_OPERATION_FAILED;
        operation->failure_code = "turn_failed";
        operation->failure_message = "mock turn failed";
        callback(context, operation, user_data);
        return CODEX_AGENT_STATUS_OK;
    }
    if (value == "slow") {
        std::thread([context, operation, callback, user_data] {
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
            callback(context, operation, user_data);
        }).detach();
        return CODEX_AGENT_STATUS_OK;
    }
    if (value == "cancel-inline") {
        operation->callback = callback;
        operation->user_data = user_data;
        return CODEX_AGENT_STATUS_OK;
    }
    if (value != "hello") return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return complete(context, operation, callback, user_data, out_operation);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_send_request(
    codex_agent_context_t* context, codex_agent_conversation_t* conversation,
    codex_agent_turn_request_t* request,
    codex_agent_operation_callback_t callback, void* user_data,
    codex_agent_operation_t** out_operation) {
    record(ConversationNativeEdge::codex_agent_conversation_send_request);
    const auto full = conversation != nullptr && request != nullptr &&
        request->prompt == "structured" && request->client_message_id &&
        *request->client_message_id == "client-1" && request->model &&
        *request->model == "model" && request->effort &&
        *request->effort == "high" && request->service_tier &&
        *request->service_tier == "priority" &&
        request->approval_preset == CODEX_AGENT_APPROVAL_PRESET_ASK_ME &&
        request->capabilities ==
            std::vector<codex_agent_capability_t>{
                CODEX_AGENT_CAPABILITY_WEB_SEARCH} &&
        request->invocations.size() == 2 &&
        request->invocations[0].kind == CODEX_AGENT_INVOCATION_KIND_PLUGIN &&
        request->invocations[0].name == "plugin" &&
        request->invocations[0].location == "plugin://uri" &&
        request->invocations[1].kind == CODEX_AGENT_INVOCATION_KIND_SKILL &&
        request->invocations[1].name == "skill" &&
        request->invocations[1].location == "/skill" &&
        request->collaboration_mode ==
            CODEX_AGENT_COLLABORATION_MODE_PLAN;
    const auto defaults = conversation != nullptr && request != nullptr &&
        request->prompt == "structured-default" &&
        !request->client_message_id && !request->model && !request->effort &&
        !request->service_tier &&
        request->approval_preset == CODEX_AGENT_APPROVAL_PRESET_AUTO_REVIEW &&
        request->capabilities.empty() && request->invocations.empty() &&
        request->collaboration_mode == CODEX_AGENT_COLLABORATION_MODE_DEFAULT;
    if (!full && !defaults) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    return complete_void(context, callback, user_data, out_operation);
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_run_shell_command(
    codex_agent_context_t* context, codex_agent_conversation_t* conversation,
    const codex_agent_string_view_t* command,
    codex_agent_operation_callback_t callback, void* user_data,
    codex_agent_operation_t** out_operation) {
    record(ConversationNativeEdge::codex_agent_conversation_run_shell_command);
    if (conversation == nullptr || command == nullptr ||
        from_view(*command) != "pwd") {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    return complete_void(context, callback, user_data, out_operation);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_reload(
    codex_agent_context_t* context, codex_agent_conversation_t*,
    codex_agent_operation_callback_t callback, void* user_data,
    codex_agent_operation_t** out_operation) {
    record(ConversationNativeEdge::codex_agent_conversation_reload);
    return complete_void(context, callback, user_data, out_operation);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_cancel_turn(
    codex_agent_context_t* context, codex_agent_conversation_t*,
    codex_agent_operation_callback_t callback, void* user_data,
    codex_agent_operation_t** out_operation) {
    record(ConversationNativeEdge::codex_agent_conversation_cancel_turn);
    return complete_void(context, callback, user_data, out_operation);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_close(
    codex_agent_context_t* context,
    codex_agent_conversation_t* conversation,
    codex_agent_operation_callback_t callback,
    void* user_data,
    codex_agent_operation_t** out_operation) {
    record(ConversationNativeEdge::codex_agent_conversation_close);
    conversation->model->status = CODEX_AGENT_CONVERSATION_STATUS_CLOSED;
    return complete_void(context, callback, user_data, out_operation);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_state_get(
    codex_agent_context_t*,
    codex_agent_conversation_t* conversation,
    codex_agent_snapshot_t** out_snapshot) {
    record(ConversationNativeEdge::codex_agent_conversation_state_get);
    const auto phase = conversation_phases[
        static_cast<std::size_t>(snapshot_kind::conversation)];
    auto* snapshot = new codex_agent_snapshot{
        snapshot_kind::conversation, CODEX_AGENT_HOST_STATE_READY,
        conversation_status(
            snapshot_kind::conversation, phase, conversation->model),
        phase, conversation->model};
    snapshot->conversation_state = conversation->model->status;
    snapshot->conversation = conversation->model;
    *out_snapshot = snapshot;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_state_subscribe(
    codex_agent_context_t* context,
    codex_agent_conversation_t* conversation,
    codex_agent_state_callback_t callback,
    void* user_data,
    codex_agent_subscription_t** out_subscription) {
    record(ConversationNativeEdge::codex_agent_conversation_state_subscribe);
    const auto status = publish_conversation_state(
        context, conversation ? conversation->model : nullptr,
        snapshot_kind::conversation, callback, user_data, out_subscription);
    if (status == CODEX_AGENT_STATUS_OK) publish_subsequent(*out_subscription);
    return status;
}

#define DEFINE_CONVERSATION_DERIVED_STATE(name, kind_value)                 \
    codex_agent_status_t CODEX_AGENT_CALL name##_get(                       \
        codex_agent_context_t*, codex_agent_conversation_t* conversation,   \
        codex_agent_snapshot_t** out_snapshot) {                            \
        record(ConversationNativeEdge::name##_get);                         \
        if (conversation == nullptr || out_snapshot == nullptr ||           \
            *out_snapshot != nullptr) {                                     \
            return CODEX_AGENT_STATUS_INVALID_ARGUMENT;                     \
        }                                                                   \
        *out_snapshot = new codex_agent_snapshot{                           \
            kind_value, CODEX_AGENT_HOST_STATE_READY,                       \
            conversation->model->status,                                    \
            conversation_phases[static_cast<std::size_t>(kind_value)],      \
            conversation->model};                                           \
        return CODEX_AGENT_STATUS_OK;                                       \
    }                                                                       \
    codex_agent_status_t CODEX_AGENT_CALL name##_subscribe(                 \
        codex_agent_context_t* context,                                     \
        codex_agent_conversation_t* conversation,                           \
        codex_agent_state_callback_t callback, void* user_data,             \
        codex_agent_subscription_t** out_subscription) {                    \
        record(ConversationNativeEdge::name##_subscribe);                   \
        return publish_conversation_state(                                  \
            context, conversation ? conversation->model : nullptr,          \
            kind_value, callback, user_data, out_subscription);             \
    }

DEFINE_CONVERSATION_DERIVED_STATE(
    codex_agent_conversation_active_turn_progress,
    snapshot_kind::active_progress)
DEFINE_CONVERSATION_DERIVED_STATE(
    codex_agent_conversation_can_cancel_turn, snapshot_kind::can_cancel)
DEFINE_CONVERSATION_DERIVED_STATE(
    codex_agent_conversation_can_reload, snapshot_kind::can_reload)
DEFINE_CONVERSATION_DERIVED_STATE(
    codex_agent_conversation_can_run_shell_command, snapshot_kind::can_shell)
DEFINE_CONVERSATION_DERIVED_STATE(
    codex_agent_conversation_can_start_turn, snapshot_kind::can_start)
DEFINE_CONVERSATION_DERIVED_STATE(
    codex_agent_conversation_current_messages, snapshot_kind::messages)
DEFINE_CONVERSATION_DERIVED_STATE(
    codex_agent_conversation_is_turn_active, snapshot_kind::is_active)

#undef DEFINE_CONVERSATION_DERIVED_STATE

codex_agent_status_t CODEX_AGENT_CALL codex_agent_state_boolean_value(
    codex_agent_context_t*, codex_agent_snapshot_t* snapshot,
    std::int32_t* out_value) {
    record(ConversationNativeEdge::codex_agent_state_boolean_value);
    if (snapshot == nullptr || out_value == nullptr) {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    *out_value = snapshot->phase == 1 ? 1 : 0;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_active_turn_progress_has_value(
    codex_agent_context_t*, codex_agent_snapshot_t* snapshot,
    std::int32_t* out_has_value) {
    record(ConversationNativeEdge::
               codex_agent_conversation_active_turn_progress_has_value);
    if (snapshot == nullptr || out_has_value == nullptr ||
        snapshot->kind != snapshot_kind::active_progress) {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    *out_has_value = snapshot->phase == 1 ? 1 : 0;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_active_turn_progress_value(
    codex_agent_context_t*, codex_agent_snapshot_t* snapshot,
    codex_agent_turn_progress_t** out_progress) {
    record(ConversationNativeEdge::
               codex_agent_conversation_active_turn_progress_value);
    if (snapshot == nullptr || out_progress == nullptr ||
        *out_progress != nullptr || snapshot->phase != 1) {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    *out_progress = new codex_agent_turn_progress{snapshot->phase};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_current_messages_count(
    codex_agent_context_t*, codex_agent_snapshot_t* snapshot,
    std::size_t* out_count) {
    record(ConversationNativeEdge::
               codex_agent_conversation_current_messages_count);
    if (snapshot == nullptr || out_count == nullptr ||
        snapshot->kind != snapshot_kind::messages) {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    *out_count = 2;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_current_messages_at(
    codex_agent_context_t*, codex_agent_snapshot_t* snapshot,
    std::size_t index, codex_agent_message_t** out_message) {
    record(ConversationNativeEdge::
               codex_agent_conversation_current_messages_at);
    if (snapshot == nullptr || index >= 2 || out_message == nullptr ||
        *out_message != nullptr || snapshot->kind != snapshot_kind::messages) {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    *out_message = new codex_agent_message(
        message_value(snapshot->phase, index));
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_state_status(
    codex_agent_context_t*,
    codex_agent_snapshot_t* snapshot,
    codex_agent_conversation_status_t* out_status) {
    *out_status = snapshot->conversation_state;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_state_failure(
    codex_agent_context_t*, codex_agent_snapshot_t* snapshot,
    codex_agent_failure_t** out_failure) {
    if (snapshot == nullptr || out_failure == nullptr ||
        *out_failure != nullptr ||
        snapshot->conversation_state != CODEX_AGENT_CONVERSATION_STATUS_FAILED) {
        return CODEX_AGENT_STATUS_NOT_READY;
    }
    *out_failure = new codex_agent_failure{
        "state_failed", "mock state failure", 1};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_state_has_conversation_id(
    codex_agent_context_t*, codex_agent_snapshot_t* snapshot,
    std::int32_t* out_present) {
    if (snapshot == nullptr || out_present == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_present = 1;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_state_conversation_id(
    codex_agent_context_t*, codex_agent_snapshot_t* snapshot,
    codex_agent_conversation_id_t** out_id) {
    if (snapshot == nullptr || out_id == nullptr || *out_id != nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_id = new codex_agent_conversation_id{"conversation-a"};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_state_has_conversation(
    codex_agent_context_t*, codex_agent_snapshot_t* snapshot,
    std::int32_t* out_present) {
    if (snapshot == nullptr || out_present == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_present = 1;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_state_conversation(
    codex_agent_context_t*, codex_agent_snapshot_t* snapshot,
    codex_agent_conversation_value_t** out_value) {
    if (snapshot == nullptr || out_value == nullptr || *out_value != nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_value = new codex_agent_conversation_value(
        conversation_value(snapshot->phase));
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_state_turn_progress(
    codex_agent_context_t*, codex_agent_snapshot_t* snapshot,
    codex_agent_turn_progress_t** out_progress) {
    if (snapshot == nullptr || out_progress == nullptr ||
        *out_progress != nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_progress = new codex_agent_turn_progress{snapshot->phase};
    return CODEX_AGENT_STATUS_OK;
}

#define DEFINE_STATE_OPTIONAL_STRING(has_name, copy_name, value)             \
    codex_agent_status_t CODEX_AGENT_CALL has_name(                          \
        codex_agent_context_t*, codex_agent_snapshot_t* snapshot,            \
        std::int32_t* out_present) {                                         \
        if (snapshot == nullptr || out_present == nullptr)                   \
            return CODEX_AGENT_STATUS_INVALID_ARGUMENT;                      \
        *out_present = 1;                                                    \
        return CODEX_AGENT_STATUS_OK;                                        \
    }                                                                        \
    codex_agent_status_t CODEX_AGENT_CALL copy_name(                         \
        codex_agent_context_t*, codex_agent_snapshot_t* snapshot,            \
        std::uint8_t* buffer, std::size_t capacity,                          \
        std::size_t* required) {                                             \
        if (snapshot == nullptr) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; \
        return copy_string(value, buffer, capacity, required);               \
    }

DEFINE_STATE_OPTIONAL_STRING(
    codex_agent_conversation_state_has_model,
    codex_agent_conversation_state_model_copy, "model")
DEFINE_STATE_OPTIONAL_STRING(
    codex_agent_conversation_state_has_effort,
    codex_agent_conversation_state_effort_copy, "high")
DEFINE_STATE_OPTIONAL_STRING(
    codex_agent_conversation_state_has_service_tier,
    codex_agent_conversation_state_service_tier_copy, "priority")

#undef DEFINE_STATE_OPTIONAL_STRING

#define DEFINE_STATE_BOOLEAN(name)                                         \
    codex_agent_status_t CODEX_AGENT_CALL name(                            \
        codex_agent_context_t*, codex_agent_snapshot_t* snapshot,          \
        std::int32_t* out_value) {                                         \
        if (snapshot == nullptr || out_value == nullptr)                   \
            return CODEX_AGENT_STATUS_INVALID_ARGUMENT;                    \
        *out_value = snapshot->conversation_state ==                       \
                             CODEX_AGENT_CONVERSATION_STATUS_READY         \
                         ? 1                                               \
                         : 0;                                              \
        return CODEX_AGENT_STATUS_OK;                                      \
    }

DEFINE_STATE_BOOLEAN(codex_agent_conversation_state_can_start_turn)
DEFINE_STATE_BOOLEAN(codex_agent_conversation_state_can_reload)
DEFINE_STATE_BOOLEAN(codex_agent_conversation_state_can_cancel_turn)

#undef DEFINE_STATE_BOOLEAN

codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_conversation_value(
    codex_agent_context_t*, codex_agent_operation_t* operation,
    codex_agent_conversation_value_t** out_value) {
    record(ConversationNativeEdge::codex_agent_operation_conversation_value);
    if (operation == nullptr || !operation->returns_conversation_value ||
        out_value == nullptr || *out_value != nullptr) {
        return CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE;
    }
    *out_value = new codex_agent_conversation_value(conversation_value());
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_cancel(
    codex_agent_context_t*, codex_agent_operation_t* operation) {
    operation->result = CODEX_AGENT_STATUS_CANCELLED;
    if (operation->callback != nullptr && !operation->callback_fired.exchange(true)) {
        operation->callback(operation->context, operation, operation->user_data);
    }
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_result(
    codex_agent_context_t*,
    codex_agent_operation_t* operation,
    codex_agent_status_t* out_result) {
    record(ConversationNativeEdge::codex_agent_operation_result);
    *out_result = operation->result.load();
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_failure(
    codex_agent_context_t*,
    codex_agent_operation_t* operation,
    codex_agent_failure_t** out_failure) {
    if (operation->failure_code.empty()) {
        return CODEX_AGENT_STATUS_NOT_READY;
    }
    *out_failure = new codex_agent_failure{
        operation->failure_code, operation->failure_message, 1};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_operation_conversation_summaries_count(
    codex_agent_context_t*, codex_agent_operation_t* operation, size_t* out_count) {
    record(ConversationNativeEdge::
               codex_agent_operation_conversation_summaries_count);
    if (!operation->returns_summaries) {
        return CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE;
    }
    *out_count = 2;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_conversation_summary_at(
    codex_agent_context_t*,
    codex_agent_operation_t* operation,
    size_t index,
    codex_agent_conversation_summary_t** out_summary) {
    record(ConversationNativeEdge::
               codex_agent_operation_conversation_summary_at);
    if (!operation->returns_summaries) {
        return CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE;
    }
    if (index >= 2) {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    *out_summary = new codex_agent_conversation_summary{
        "conversation-a", index == 0 ? "First" : "Second",
        static_cast<int64_t>(100 + index)};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_summary_destroy(
    codex_agent_context_t*, codex_agent_conversation_summary_t** summary) {
    return destroy(summary);
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_summary_conversation_id(
    codex_agent_context_t*,
    codex_agent_conversation_summary_t* summary,
    codex_agent_conversation_id_t** out_conversation_id) {
    *out_conversation_id = new codex_agent_conversation_id{summary->id};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_summary_title_copy(
    codex_agent_context_t*,
    codex_agent_conversation_summary_t* summary,
    uint8_t* buffer,
    size_t capacity,
    size_t* out_required) {
    return copy_string(summary->title, buffer, capacity, out_required);
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_summary_updated_at_epoch_seconds(
    codex_agent_context_t*,
    codex_agent_conversation_summary_t* summary,
    int64_t* out_updated_at_epoch_seconds) {
    *out_updated_at_epoch_seconds = summary->updated_at_epoch_seconds;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_id_destroy(
    codex_agent_context_t*, codex_agent_conversation_id_t** conversation_id) {
    return destroy(conversation_id);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_id_create(
    codex_agent_context_t*, const codex_agent_string_view_t* value,
    codex_agent_conversation_id_t** out_conversation_id) {
    if (value == nullptr || out_conversation_id == nullptr ||
        *out_conversation_id != nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_conversation_id = new codex_agent_conversation_id{from_view(*value)};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_id_value_copy(
    codex_agent_context_t*,
    codex_agent_conversation_id_t* conversation_id,
    uint8_t* buffer,
    size_t capacity,
    size_t* out_required) {
    return copy_string(conversation_id->value, buffer, capacity, out_required);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_plugin_create(
    codex_agent_context_t*, const codex_agent_string_view_t* name,
    const codex_agent_string_view_t* uri,
    codex_agent_invocation_plugin_t** out_plugin) {
    if (name == nullptr || uri == nullptr || out_plugin == nullptr ||
        *out_plugin != nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_plugin = new codex_agent_invocation_plugin_t{
        from_view(*name), from_view(*uri)};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_plugin_destroy(
    codex_agent_context_t*, codex_agent_invocation_plugin_t** plugin) {
    return destroy(plugin);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_skill_create(
    codex_agent_context_t*, const codex_agent_string_view_t* name,
    const codex_agent_string_view_t* path,
    codex_agent_invocation_skill_t** out_skill) {
    if (name == nullptr || path == nullptr || out_skill == nullptr ||
        *out_skill != nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_skill = new codex_agent_invocation_skill_t{
        from_view(*name), from_view(*path)};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_skill_destroy(
    codex_agent_context_t*, codex_agent_invocation_skill_t** skill) {
    return destroy(skill);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_from_plugin(
    codex_agent_context_t*, codex_agent_invocation_plugin_t* plugin,
    codex_agent_invocation_t** out_invocation) {
    if (plugin == nullptr || out_invocation == nullptr ||
        *out_invocation != nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_invocation = new codex_agent_invocation{
        CODEX_AGENT_INVOCATION_KIND_PLUGIN, "plugin:" + plugin->uri,
        plugin->name, plugin->uri};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_from_skill(
    codex_agent_context_t*, codex_agent_invocation_skill_t* skill,
    codex_agent_invocation_t** out_invocation) {
    if (skill == nullptr || out_invocation == nullptr ||
        *out_invocation != nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_invocation = new codex_agent_invocation{
        CODEX_AGENT_INVOCATION_KIND_SKILL, "skill:" + skill->path,
        skill->name, skill->path};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_destroy(
    codex_agent_context_t*, codex_agent_invocation_t** invocation) {
    return destroy(invocation);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_kind(
    codex_agent_context_t*, codex_agent_invocation_t* invocation,
    codex_agent_invocation_kind_t* out_kind) {
    if (invocation == nullptr || out_kind == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_kind = invocation->kind;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_key_copy(
    codex_agent_context_t*, codex_agent_invocation_t* invocation,
    std::uint8_t* buffer, std::size_t capacity, std::size_t* required) {
    return invocation == nullptr
               ? CODEX_AGENT_STATUS_INVALID_ARGUMENT
               : copy_string(invocation->key, buffer, capacity, required);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_name_copy(
    codex_agent_context_t*, codex_agent_invocation_t* invocation,
    std::uint8_t* buffer, std::size_t capacity, std::size_t* required) {
    return invocation == nullptr
               ? CODEX_AGENT_STATUS_INVALID_ARGUMENT
               : copy_string(invocation->name, buffer, capacity, required);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_plugin(
    codex_agent_context_t*, codex_agent_invocation_t* invocation,
    codex_agent_invocation_plugin_t** out_plugin) {
    if (invocation == nullptr || out_plugin == nullptr ||
        *out_plugin != nullptr ||
        invocation->kind != CODEX_AGENT_INVOCATION_KIND_PLUGIN)
        return CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE;
    *out_plugin = new codex_agent_invocation_plugin_t{
        invocation->name, invocation->location};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_skill(
    codex_agent_context_t*, codex_agent_invocation_t* invocation,
    codex_agent_invocation_skill_t** out_skill) {
    if (invocation == nullptr || out_skill == nullptr || *out_skill != nullptr ||
        invocation->kind != CODEX_AGENT_INVOCATION_KIND_SKILL)
        return CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE;
    *out_skill = new codex_agent_invocation_skill_t{
        invocation->name, invocation->location};
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_plugin_uri_copy(
    codex_agent_context_t*, codex_agent_invocation_plugin_t* plugin,
    std::uint8_t* buffer, std::size_t capacity, std::size_t* required) {
    return plugin == nullptr
               ? CODEX_AGENT_STATUS_INVALID_ARGUMENT
               : copy_string(plugin->uri, buffer, capacity, required);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_invocation_skill_path_copy(
    codex_agent_context_t*, codex_agent_invocation_skill_t* skill,
    std::uint8_t* buffer, std::size_t capacity, std::size_t* required) {
    return skill == nullptr
               ? CODEX_AGENT_STATUS_INVALID_ARGUMENT
               : copy_string(skill->path, buffer, capacity, required);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_request_create(
    codex_agent_context_t*, const codex_agent_string_view_t* prompt,
    std::int32_t has_client_message_id,
    const codex_agent_string_view_t* client_message_id,
    std::int32_t has_model, const codex_agent_string_view_t* model,
    std::int32_t has_effort, const codex_agent_string_view_t* effort,
    std::int32_t has_service_tier,
    const codex_agent_string_view_t* service_tier,
    codex_agent_approval_preset_t approval_preset,
    const codex_agent_capability_t* capabilities,
    std::size_t capability_count,
    codex_agent_invocation_t* const* invocations,
    std::size_t invocation_count,
    codex_agent_collaboration_mode_t collaboration_mode,
    codex_agent_turn_request_t** out_request) {
    if (prompt == nullptr || client_message_id == nullptr || model == nullptr ||
        effort == nullptr || service_tier == nullptr || out_request == nullptr ||
        *out_request != nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    auto* request = new codex_agent_turn_request{
        from_view(*prompt), std::nullopt, std::nullopt, std::nullopt,
        std::nullopt, approval_preset, {}, {}, collaboration_mode};
    if (has_client_message_id != 0)
        request->client_message_id = from_view(*client_message_id);
    if (has_model != 0) request->model = from_view(*model);
    if (has_effort != 0) request->effort = from_view(*effort);
    if (has_service_tier != 0)
        request->service_tier = from_view(*service_tier);
    if (capability_count != 0 && capabilities == nullptr) {
        delete request;
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    if (capability_count != 0) {
        request->capabilities.assign(
            capabilities, capabilities + capability_count);
    }
    if (invocation_count != 0 && invocations == nullptr) {
        delete request;
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    }
    for (std::size_t index = 0; index < invocation_count; ++index)
        request->invocations.push_back(*invocations[index]);
    *out_request = request;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_request_destroy(
    codex_agent_context_t*, codex_agent_turn_request_t** request) {
    return destroy(request);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_destroy(
    codex_agent_context_t*, codex_agent_message_t** message) {
    return destroy(message);
}

#define DEFINE_MESSAGE_COPY(name, member)                                  \
    codex_agent_status_t CODEX_AGENT_CALL name(                            \
        codex_agent_context_t*, codex_agent_message_t* message,            \
        std::uint8_t* buffer, std::size_t capacity,                        \
        std::size_t* required) {                                           \
        return message == nullptr                                          \
                   ? CODEX_AGENT_STATUS_INVALID_ARGUMENT                   \
                   : copy_string(                                          \
                         message->member, buffer, capacity, required);      \
    }

DEFINE_MESSAGE_COPY(codex_agent_message_id_copy, id)
DEFINE_MESSAGE_COPY(codex_agent_message_text_copy, text)

#undef DEFINE_MESSAGE_COPY

#define DEFINE_MESSAGE_OPTIONAL_STRING(has_name, copy_name, member)         \
    codex_agent_status_t CODEX_AGENT_CALL has_name(                         \
        codex_agent_context_t*, codex_agent_message_t* message,             \
        std::int32_t* out_present) {                                        \
        if (message == nullptr || out_present == nullptr)                   \
            return CODEX_AGENT_STATUS_INVALID_ARGUMENT;                     \
        *out_present = message->member ? 1 : 0;                             \
        return CODEX_AGENT_STATUS_OK;                                       \
    }                                                                       \
    codex_agent_status_t CODEX_AGENT_CALL copy_name(                        \
        codex_agent_context_t*, codex_agent_message_t* message,             \
        std::uint8_t* buffer, std::size_t capacity,                         \
        std::size_t* required) {                                            \
        if (message == nullptr || !message->member)                         \
            return CODEX_AGENT_STATUS_NOT_READY;                            \
        return copy_string(                                                 \
            *message->member, buffer, capacity, required);                  \
    }

DEFINE_MESSAGE_OPTIONAL_STRING(
    codex_agent_message_has_client_message_id,
    codex_agent_message_client_message_id_copy, client_message_id)
DEFINE_MESSAGE_OPTIONAL_STRING(
    codex_agent_message_has_reasoning,
    codex_agent_message_reasoning_copy, reasoning)
DEFINE_MESSAGE_OPTIONAL_STRING(
    codex_agent_message_has_plan, codex_agent_message_plan_copy, plan)
DEFINE_MESSAGE_OPTIONAL_STRING(
    codex_agent_message_has_shell_command,
    codex_agent_message_shell_command_copy, shell_command)

#undef DEFINE_MESSAGE_OPTIONAL_STRING

codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_role(
    codex_agent_context_t*, codex_agent_message_t* message,
    codex_agent_message_role_t* out_role) {
    if (message == nullptr || out_role == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_role = message->role;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_collaboration_mode(
    codex_agent_context_t*, codex_agent_message_t* message,
    codex_agent_collaboration_mode_t* out_mode) {
    if (message == nullptr || out_mode == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_mode = message->collaboration_mode;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_exit_code(
    codex_agent_context_t*, codex_agent_message_t* message,
    std::int32_t* out_present, std::int32_t* out_exit_code) {
    if (message == nullptr || out_present == nullptr || out_exit_code == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_present = message->exit_code ? 1 : 0;
    *out_exit_code = message->exit_code.value_or(0);
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_message_capabilities_count(
    codex_agent_context_t*, codex_agent_message_t* message,
    std::size_t* out_count) {
    if (message == nullptr || out_count == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_count = message->capabilities.size();
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_has_capability(
    codex_agent_context_t*, codex_agent_message_t* message,
    codex_agent_capability_t capability, std::int32_t* out_present) {
    if (message == nullptr || out_present == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_present = std::find(
        message->capabilities.begin(), message->capabilities.end(),
        capability) != message->capabilities.end();
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_message_invocations_count(
    codex_agent_context_t*, codex_agent_message_t* message,
    std::size_t* out_count) {
    if (message == nullptr || out_count == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_count = message->invocations.size();
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_message_invocation_at(
    codex_agent_context_t*, codex_agent_message_t* message, std::size_t index,
    codex_agent_invocation_t** out_invocation) {
    if (message == nullptr || index >= message->invocations.size() ||
        out_invocation == nullptr || *out_invocation != nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_invocation = new codex_agent_invocation(message->invocations[index]);
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_value_destroy(
    codex_agent_context_t*, codex_agent_conversation_value_t** value) {
    return destroy(value);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_conversation_value_summary(
    codex_agent_context_t*, codex_agent_conversation_value_t* value,
    codex_agent_conversation_summary_t** out_summary) {
    if (value == nullptr || out_summary == nullptr || *out_summary != nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_summary = new codex_agent_conversation_summary(value->summary);
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_value_messages_count(
    codex_agent_context_t*, codex_agent_conversation_value_t* value,
    std::size_t* out_count) {
    if (value == nullptr || out_count == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_count = value->messages.size();
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_conversation_value_message_at(
    codex_agent_context_t*, codex_agent_conversation_value_t* value,
    std::size_t index, codex_agent_message_t** out_message) {
    if (value == nullptr || index >= value->messages.size() ||
        out_message == nullptr || *out_message != nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_message = new codex_agent_message(value->messages[index]);
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_progress_destroy(
    codex_agent_context_t*, codex_agent_turn_progress_t** progress) {
    return destroy(progress);
}

#define DEFINE_PROGRESS_COPY(name, value)                                  \
    codex_agent_status_t CODEX_AGENT_CALL name(                            \
        codex_agent_context_t*, codex_agent_turn_progress_t* progress,     \
        std::uint8_t* buffer, std::size_t capacity,                        \
        std::size_t* required) {                                           \
        if (progress == nullptr) return CODEX_AGENT_STATUS_INVALID_ARGUMENT; \
        return copy_string(value, buffer, capacity, required);             \
    }

DEFINE_PROGRESS_COPY(codex_agent_turn_progress_text_copy, "progress")
DEFINE_PROGRESS_COPY(codex_agent_turn_progress_commentary_copy, "commentary")
DEFINE_PROGRESS_COPY(codex_agent_turn_progress_reasoning_copy, "reasoning")
DEFINE_PROGRESS_COPY(codex_agent_turn_progress_plan_copy, "plan")
DEFINE_PROGRESS_COPY(codex_agent_turn_progress_shell_output_copy, "output")

#undef DEFINE_PROGRESS_COPY

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_turn_progress_has_plan_progress(
    codex_agent_context_t*, codex_agent_turn_progress_t* progress,
    std::int32_t* out_present) {
    if (progress == nullptr || out_present == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_present = 0;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_progress_plan_progress(
    codex_agent_context_t*, codex_agent_turn_progress_t*,
    codex_agent_plan_progress_t**) {
    return CODEX_AGENT_STATUS_NOT_READY;
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_turn_progress_shell_exit_code(
    codex_agent_context_t*, codex_agent_turn_progress_t* progress,
    std::int32_t* out_present, std::int32_t* out_code) {
    if (progress == nullptr || out_present == nullptr || out_code == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_present = progress->phase == 1 ? 1 : 0;
    *out_code = 0;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_progress_work_activity(
    codex_agent_context_t*, codex_agent_turn_progress_t* progress,
    std::int32_t* out_present,
    codex_agent_work_activity_t* out_activity) {
    if (progress == nullptr || out_present == nullptr || out_activity == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_present = progress->phase == 1 ? 1 : 0;
    *out_activity = CODEX_AGENT_WORK_ACTIVITY_RUNNING_COMMAND;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_turn_progress_hook_activities_count(
    codex_agent_context_t*, codex_agent_turn_progress_t* progress,
    std::size_t* out_count) {
    if (progress == nullptr || out_count == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_count = 0;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL
codex_agent_turn_progress_hook_activity_at(
    codex_agent_context_t*, codex_agent_turn_progress_t*, std::size_t,
    codex_agent_hook_activity_t**) {
    return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_turn_progress_is_truncated(
    codex_agent_context_t*, codex_agent_turn_progress_t* progress,
    std::int32_t* out_truncated) {
    if (progress == nullptr || out_truncated == nullptr)
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    *out_truncated = progress->phase == 1 ? 1 : 0;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_plan_progress_destroy(
    codex_agent_context_t*, codex_agent_plan_progress_t** progress) {
    return destroy(progress);
}
codex_agent_status_t CODEX_AGENT_CALL
codex_agent_plan_progress_has_explanation(
    codex_agent_context_t*, codex_agent_plan_progress_t*, std::int32_t*) {
    return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
}
codex_agent_status_t CODEX_AGENT_CALL
codex_agent_plan_progress_explanation_copy(
    codex_agent_context_t*, codex_agent_plan_progress_t*, std::uint8_t*,
    std::size_t, std::size_t*) {
    return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
}
codex_agent_status_t CODEX_AGENT_CALL codex_agent_plan_progress_steps_count(
    codex_agent_context_t*, codex_agent_plan_progress_t*, std::size_t*) {
    return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
}
codex_agent_status_t CODEX_AGENT_CALL codex_agent_plan_progress_step_at(
    codex_agent_context_t*, codex_agent_plan_progress_t*, std::size_t,
    codex_agent_plan_step_t**) {
    return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
}
codex_agent_status_t CODEX_AGENT_CALL codex_agent_plan_step_destroy(
    codex_agent_context_t*, codex_agent_plan_step_t** step) {
    return destroy(step);
}
codex_agent_status_t CODEX_AGENT_CALL codex_agent_plan_step_text_copy(
    codex_agent_context_t*, codex_agent_plan_step_t*, std::uint8_t*,
    std::size_t, std::size_t*) {
    return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
}
codex_agent_status_t CODEX_AGENT_CALL codex_agent_plan_step_status(
    codex_agent_context_t*, codex_agent_plan_step_t*,
    codex_agent_plan_step_status_t*) {
    return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
}
codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_activity_destroy(
    codex_agent_context_t*, codex_agent_hook_activity_t** activity) {
    return destroy(activity);
}

#define DEFINE_UNUSED_HOOK_COPY(name)                                      \
    codex_agent_status_t CODEX_AGENT_CALL name(                            \
        codex_agent_context_t*, codex_agent_hook_activity_t*,              \
        std::uint8_t*, std::size_t, std::size_t*) {                        \
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT;                        \
    }

DEFINE_UNUSED_HOOK_COPY(codex_agent_hook_activity_id_copy)
DEFINE_UNUSED_HOOK_COPY(codex_agent_hook_activity_event_name_copy)
DEFINE_UNUSED_HOOK_COPY(codex_agent_hook_activity_handler_type_copy)
DEFINE_UNUSED_HOOK_COPY(codex_agent_hook_activity_status_message_copy)

#undef DEFINE_UNUSED_HOOK_COPY

codex_agent_status_t CODEX_AGENT_CALL codex_agent_hook_activity_status(
    codex_agent_context_t*, codex_agent_hook_activity_t*,
    codex_agent_hook_run_status_t*) {
    return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
}
codex_agent_status_t CODEX_AGENT_CALL
codex_agent_hook_activity_has_status_message(
    codex_agent_context_t*, codex_agent_hook_activity_t*, std::int32_t*) {
    return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
}
codex_agent_status_t CODEX_AGENT_CALL
codex_agent_hook_activity_details_count(
    codex_agent_context_t*, codex_agent_hook_activity_t*, std::size_t*) {
    return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
}
codex_agent_status_t CODEX_AGENT_CALL
codex_agent_hook_activity_detail_copy_at(
    codex_agent_context_t*, codex_agent_hook_activity_t*, std::size_t,
    std::uint8_t*, std::size_t, std::size_t*) {
    return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_operation_destroy(
    codex_agent_context_t*, codex_agent_operation_t** operation) {
    return destroy(operation);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_subscription_destroy(
    codex_agent_context_t*, codex_agent_subscription_t** subscription) {
    if (subscription == nullptr || *subscription == nullptr) {
        return subscription == nullptr ? CODEX_AGENT_STATUS_INVALID_ARGUMENT
                                       : CODEX_AGENT_STATUS_OK;
    }
    auto* value = *subscription;
    value->cancelled = true;
    if (value->workers.load() != 0) {
        return CODEX_AGENT_STATUS_BUSY;
    }
    if (!value->terminal_started.exchange(true)) {
        ++value->workers;
        std::thread([value] {
            value->callback(
                value->context,
                value,
                CODEX_AGENT_STATUS_CANCELLED,
                nullptr,
                1,
                value->user_data);
            value->terminal_finished = true;
            --value->workers;
        }).detach();
        return CODEX_AGENT_STATUS_BUSY;
    }
    if (!value->terminal_finished.load() || value->workers.load() != 0) {
        return CODEX_AGENT_STATUS_BUSY;
    }
    conversation_subscriptions.erase(
        std::remove(conversation_subscriptions.begin(),
                    conversation_subscriptions.end(), value),
        conversation_subscriptions.end());
    delete value;
    *subscription = nullptr;
    return CODEX_AGENT_STATUS_OK;
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_snapshot_destroy(
    codex_agent_context_t*, codex_agent_snapshot_t** snapshot) {
    return destroy(snapshot);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_failure_release(
    codex_agent_context_t*, codex_agent_failure_t** failure) {
    return destroy(failure);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_failure_code_copy(
    codex_agent_context_t*, codex_agent_failure_t* failure, uint8_t* buffer,
    size_t capacity, size_t* out_required) {
    return copy_string(failure->code, buffer, capacity, out_required);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_failure_message_copy(
    codex_agent_context_t*, codex_agent_failure_t* failure, uint8_t* buffer,
    size_t capacity, size_t* out_required) {
    return copy_string(failure->message, buffer, capacity, out_required);
}

codex_agent_status_t CODEX_AGENT_CALL codex_agent_failure_is_recoverable(
    codex_agent_context_t*, codex_agent_failure_t* failure,
    int32_t* out_is_recoverable) {
    *out_is_recoverable = failure->recoverable;
    return CODEX_AGENT_STATUS_OK;
}

}  // extern "C"
