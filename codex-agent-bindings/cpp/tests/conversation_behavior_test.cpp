#include <codex_agent/codex_agent.hpp>

#include "conversation_native_probe.hpp"

#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <thread>
#include <type_traits>
#include <utility>
#include <vector>

using namespace std::chrono_literals;

using ConversationsVoid = codex_agent::AsyncOperation<void>
    (codex_agent::Conversations::*)(codex_agent::ConversationId) const;
using ConversationsList = codex_agent::AsyncOperation<
    std::vector<codex_agent::ConversationSummary>>
    (codex_agent::Conversations::*)() const;
using ConversationsOpen = codex_agent::AsyncOperation<codex_agent::Conversation>
    (codex_agent::Conversations::*)(
        std::optional<codex_agent::ConversationId>,
        codex_agent::ConversationSettings) const;
using ConversationsRead = codex_agent::AsyncOperation<
    codex_agent::ConversationValue>
    (codex_agent::Conversations::*)(codex_agent::ConversationId) const;
using ConversationsRename = codex_agent::AsyncOperation<void>
    (codex_agent::Conversations::*)(
        codex_agent::ConversationId, std::string) const;
using ConversationsActive = std::optional<codex_agent::Conversation>
    (codex_agent::Conversations::*)() const;
using ConversationsActiveSubscribe = codex_agent::StateSubscription<
    std::optional<codex_agent::Conversation>>
    (codex_agent::Conversations::*)(std::function<void(
        codex_agent::StateEvent<std::optional<codex_agent::Conversation>>)>)
        const;
using ConversationVoid = codex_agent::AsyncOperation<void>
    (codex_agent::Conversation::*)() const;
using ConversationString = codex_agent::AsyncOperation<void>
    (codex_agent::Conversation::*)(std::string) const;
using ConversationRequest = codex_agent::AsyncOperation<void>
    (codex_agent::Conversation::*)(codex_agent::TurnRequest) const;
using ConversationProgress = std::optional<codex_agent::TurnProgress>
    (codex_agent::Conversation::*)() const;
using ConversationProgressSubscribe = codex_agent::StateSubscription<
    std::optional<codex_agent::TurnProgress>>
    (codex_agent::Conversation::*)(std::function<void(
        codex_agent::StateEvent<std::optional<codex_agent::TurnProgress>>)>)
        const;
using ConversationBoolean = bool (codex_agent::Conversation::*)() const;
using ConversationBooleanSubscribe = codex_agent::StateSubscription<bool>
    (codex_agent::Conversation::*)(
        std::function<void(codex_agent::StateEvent<bool>)>) const;
using ConversationMessages = std::vector<codex_agent::Message>
    (codex_agent::Conversation::*)() const;
using ConversationMessagesSubscribe = codex_agent::StateSubscription<
    std::vector<codex_agent::Message>>
    (codex_agent::Conversation::*)(std::function<void(
        codex_agent::StateEvent<std::vector<codex_agent::Message>>)>) const;
using ConversationState = codex_agent::ConversationState
    (codex_agent::Conversation::*)() const;
using ConversationStateSubscribe = codex_agent::StateSubscription<
    codex_agent::ConversationState>
    (codex_agent::Conversation::*)(std::function<void(
        codex_agent::StateEvent<codex_agent::ConversationState>)>) const;

static_assert(std::is_same_v<
              decltype(static_cast<ConversationsVoid>(
                  &codex_agent::Conversations::remove)),
              ConversationsVoid>);
static_assert(std::is_same_v<decltype(&codex_agent::Conversations::list),
                             ConversationsList>);
static_assert(std::is_same_v<decltype(&codex_agent::Conversations::open),
                             ConversationsOpen>);
static_assert(std::is_same_v<decltype(&codex_agent::Conversations::read),
                             ConversationsRead>);
static_assert(std::is_same_v<decltype(&codex_agent::Conversations::rename),
                             ConversationsRename>);
static_assert(std::is_same_v<decltype(&codex_agent::Conversations::active),
                             ConversationsActive>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Conversations::subscribe_active),
              ConversationsActiveSubscribe>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Conversation::cancel_turn),
              ConversationVoid>);
static_assert(std::is_same_v<decltype(&codex_agent::Conversation::close),
                             ConversationVoid>);
static_assert(std::is_same_v<decltype(&codex_agent::Conversation::reload),
                             ConversationVoid>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Conversation::run_shell_command),
              ConversationString>);
static_assert(std::is_same_v<
              decltype(static_cast<ConversationRequest>(
                  &codex_agent::Conversation::send)),
              ConversationRequest>);
static_assert(std::is_same_v<
              decltype(static_cast<ConversationString>(
                  &codex_agent::Conversation::send)),
              ConversationString>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Conversation::active_turn_progress),
              ConversationProgress>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Conversation::subscribe_active_turn_progress),
              ConversationProgressSubscribe>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Conversation::can_cancel_turn),
              ConversationBoolean>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Conversation::subscribe_can_cancel_turn),
              ConversationBooleanSubscribe>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Conversation::can_reload),
              ConversationBoolean>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Conversation::subscribe_can_reload),
              ConversationBooleanSubscribe>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Conversation::can_run_shell_command),
              ConversationBoolean>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Conversation::subscribe_can_run_shell_command),
              ConversationBooleanSubscribe>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Conversation::can_start_turn),
              ConversationBoolean>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Conversation::subscribe_can_start_turn),
              ConversationBooleanSubscribe>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Conversation::current_messages),
              ConversationMessages>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Conversation::subscribe_current_messages),
              ConversationMessagesSubscribe>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Conversation::is_turn_active),
              ConversationBoolean>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Conversation::subscribe_is_turn_active),
              ConversationBooleanSubscribe>);
static_assert(std::is_same_v<decltype(&codex_agent::Conversation::state),
                             ConversationState>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Conversation::subscribe_state),
              ConversationStateSubscribe>);

namespace {

constexpr int state_kind = 1;
constexpr int active_kind = 2;
constexpr int progress_kind = 3;
constexpr int can_cancel_kind = 4;
constexpr int can_reload_kind = 5;
constexpr int can_shell_kind = 6;
constexpr int can_start_kind = 7;
constexpr int messages_kind = 8;
constexpr int is_active_kind = 9;

[[noreturn]] void fail(const char* message) {
    (void)message;
    std::abort();
}

void require(bool condition, const char* message) {
    if (!condition) fail(message);
}

template <typename Action>
void require_invalid(Action&& action) {
    try {
        action();
    } catch (const codex_agent::Error& error) {
        require(error.status() == codex_agent::Status::invalid_argument,
                "wrong rejection status");
        return;
    }
    fail("invalid input was accepted");
}

template <typename Action, typename Verify>
void async_contract(Action&& action, Verify&& verify) {
    verify(action().get());

    codex_agent_cpp_mock_conversation_delay_next_operation();
    auto cancelled = action();
    cancelled.cancel();
    try {
        (void)cancelled.get();
        fail("cancelled operation completed");
    } catch (const codex_agent::OperationError& error) {
        require(error.status() == codex_agent::Status::cancelled &&
                    !error.failure(),
                "cancelled operation lost structured status");
    }

    codex_agent_cpp_mock_conversation_set_failure();
    try {
        (void)action().get();
        fail("failed operation completed");
    } catch (const codex_agent::OperationError& error) {
        require(error.status() == codex_agent::Status::operation_failed &&
                    error.failure() &&
                    error.failure()->code == "conversation_failed" &&
                    error.failure()->recoverable,
                "operation failure was not structured");
    }
}

template <typename Action>
void async_void_contract(Action&& action) {
    action().get();
    codex_agent_cpp_mock_conversation_delay_next_operation();
    auto cancelled = action();
    cancelled.cancel();
    try {
        cancelled.get();
        fail("cancelled operation completed");
    } catch (const codex_agent::OperationError& error) {
        require(error.status() == codex_agent::Status::cancelled &&
                    !error.failure(),
                "cancelled operation lost structured status");
    }
    codex_agent_cpp_mock_conversation_set_failure();
    try {
        action().get();
        fail("failed operation completed");
    } catch (const codex_agent::OperationError& error) {
        require(error.status() == codex_agent::Status::operation_failed &&
                    error.failure() &&
                    error.failure()->code == "conversation_failed" &&
                    error.failure()->recoverable,
                "operation failure was not structured");
    }
}

struct Fixture {
    codex_agent::Host host;
    codex_agent::Agent agent;
    codex_agent::Conversations conversations;
    codex_agent::Conversation conversation;
};

Fixture fixture() {
    auto host = codex_agent::Host::create({
        .bundle_directory = "/bundle",
        .data_directory = "/data",
        .client_info = {"conversation-test", "Conversation test", "1"},
    });
    host.start().get();
    auto agent = host.agent();
    auto conversations = agent.conversations();
    auto conversation = conversations.open(
        codex_agent::ConversationId("conversation-a"),
        {.approval_preset = codex_agent::ApprovalPreset::ask_me,
         .service_tier = "priority"}).get();
    codex_agent_cpp_mock_conversation_reset();
    return {std::move(host), std::move(agent), std::move(conversations),
            std::move(conversation)};
}

const std::map<std::string, std::set<ConversationNativeEdge>>& expected_edges() {
    static const auto value = [] {
        std::map<std::string, std::set<ConversationNativeEdge>> result;
#define CONVERSATION_NATIVE_BOUNDARY(capability, function)                  \
        result[capability].insert(ConversationNativeEdge::function);
#include "conversation_native_boundaries.inc"
#undef CONVERSATION_NATIVE_BOUNDARY
        return result;
    }();
    return value;
}

const std::map<std::string, std::string>& scenarios() {
    static const std::map<std::string, std::string> value{
#define CONVERSATION_SCENARIO(capability, scenario) {capability, scenario},
#include "conversation_scenarios.inc"
#undef CONVERSATION_SCENARIO
    };
    return value;
}

std::set<ConversationNativeEdge> observed_edges() {
    std::set<ConversationNativeEdge> result;
    for (std::size_t index = 0;
         index < codex_agent_cpp_mock_conversation_event_count(); ++index) {
        result.insert(codex_agent_cpp_mock_conversation_event_at(index));
    }
    return result;
}

void pass(std::string capability, std::vector<std::string>& passed) {
    const auto observed = observed_edges();
    for (const auto edge : expected_edges().at(capability)) {
        require(observed.contains(edge),
                "typed public method missed an exact native edge");
    }
    passed.push_back(std::move(capability));
}

template <typename Value, typename Current, typename Subscribe, typename Check>
void state_contract(
    int kind, Current&& current, Subscribe&& subscribe, Check&& check) {
    codex_agent_cpp_mock_conversation_set_phase(kind, 0);
    check(current(), 0);
    std::vector<codex_agent::StateEvent<Value>> events;
    auto subscription = subscribe(
        [&](codex_agent::StateEvent<Value> event) {
            events.push_back(std::move(event));
        });
    require(events.size() == 1 && !events.front().terminal &&
                events.front().status == codex_agent::Status::ok &&
                events.front().value,
            "state current event is incomplete");
    check(*events.front().value, 0);
    codex_agent_cpp_mock_conversation_set_phase(kind, 1);
    codex_agent_cpp_mock_conversation_publish(kind, 0);
    require(events.size() == 2 && events.back().value,
            "state change event is missing");
    check(*events.back().value, 1);
    subscription.close();
    require(events.size() == 3 && events.back().terminal &&
                events.back().status == codex_agent::Status::cancelled &&
                !events.back().value,
            "state terminal event is missing");
    const auto closed_count = events.size();
    codex_agent_cpp_mock_conversation_publish(kind, 0);
    require(events.size() == closed_count,
            "state callback continued after close");
    subscription.close();
}

codex_agent::TurnRequest request() {
    return {
        .prompt = "structured",
        .model = "model",
        .effort = "high",
        .approval_preset = codex_agent::ApprovalPreset::ask_me,
        .service_tier = "priority",
        .capabilities = {codex_agent::Capability::web_search},
        .collaboration_mode = codex_agent::CollaborationMode::plan,
        .invocations = {
            codex_agent::PluginInvocation{
                {"plugin:plugin://uri", "plugin"}, "plugin://uri"},
            codex_agent::SkillInvocation{
                {"skill:/skill", "skill"}, "/skill"}},
        .client_message_id = "client-1",
    };
}

}  // namespace

int main(int argc, char** argv) {
    require(argc == 2, "usage: conversation_behavior_test RECEIPT");
    std::vector<std::string> passed;

    {
        auto value = fixture();
        async_void_contract([&] {
            return value.conversations.remove(
                codex_agent::ConversationId("conversation-a"));
        });
        require_invalid([&] {
            (void)value.conversations.remove(
                codex_agent::ConversationId("wrong"));
        });
        pass("cpp.conversation:000", passed);
    }
    {
        auto value = fixture();
        async_contract(
            [&] { return value.conversations.list(); },
            [](const auto& summaries) {
                require(summaries.size() == 2 &&
                            summaries[0].conversation_id.value ==
                                "conversation-a" &&
                            summaries[1].conversation_id.value ==
                                "conversation-a" &&
                            summaries[0].title == "First" &&
                            summaries[1].title == "Second" &&
                            summaries[0].updated_at_epoch_seconds == 100 &&
                            summaries[1].updated_at_epoch_seconds == 101,
                        "conversation summaries lost order or duplicates");
            });
        pass("cpp.conversation:001", passed);
    }
    {
        auto value = fixture();
        async_contract(
            [&] {
                return value.conversations.open(
                    codex_agent::ConversationId("conversation-a"),
                    {.approval_preset = codex_agent::ApprovalPreset::ask_me,
                     .service_tier = "priority"});
            },
            [&](auto opened) {
                require(opened.same_as(value.conversation),
                        "opened conversation identity changed");
            });
        value.conversations.open().get();
        require_invalid([&] {
            (void)value.conversations.open(
                codex_agent::ConversationId("wrong"),
                {.approval_preset = codex_agent::ApprovalPreset::ask_me,
                 .service_tier = "priority"});
        });
        require_invalid([&] {
            (void)value.conversations.open(
                codex_agent::ConversationId("conversation-a"),
                {.approval_preset = codex_agent::ApprovalPreset::never,
                 .service_tier = "priority"});
        });
        require_invalid([&] {
            (void)value.conversations.open(
                codex_agent::ConversationId("conversation-a"),
                {.approval_preset = codex_agent::ApprovalPreset::ask_me,
                 .service_tier = "wrong"});
        });
        auto retained_child = [] {
            auto parent = fixture();
            return parent.conversations.open(
                codex_agent::ConversationId("conversation-a"),
                {.approval_preset = codex_agent::ApprovalPreset::ask_me,
                 .service_tier = "priority"}).get();
        }();
        retained_child.send("hello").get();
        pass("cpp.conversation:002", passed);
    }
    {
        auto value = fixture();
        async_contract(
            [&] {
                return value.conversations.read(
                    codex_agent::ConversationId("conversation-a"));
            },
            [](const auto& conversation) {
                require(conversation.summary.conversation_id.value ==
                            "conversation-a" &&
                            conversation.messages.size() == 2 &&
                            conversation.messages[0].text == "current-0" &&
                            conversation.messages[0].reasoning &&
                            !conversation.messages[1].reasoning &&
                            conversation.messages[0].capabilities.contains(
                                codex_agent::Capability::web_search),
                        "read projection lost values or nullability");
            });
        require_invalid([&] {
            (void)value.conversations.read(codex_agent::ConversationId("wrong"));
        });
        pass("cpp.conversation:003", passed);
    }
    {
        auto value = fixture();
        async_void_contract([&] {
            return value.conversations.rename(
                codex_agent::ConversationId("conversation-a"), "Renamed");
        });
        require_invalid([&] {
            (void)value.conversations.rename(
                codex_agent::ConversationId("wrong"), "Renamed");
        });
        require_invalid([&] {
            (void)value.conversations.rename(
                codex_agent::ConversationId("conversation-a"), "Wrong");
        });
        pass("cpp.conversation:004", passed);
    }
    {
        auto value = fixture();
        codex_agent_cpp_mock_conversation_set_phase(active_kind, 0);
        require(!value.conversations.active(),
                "active conversation absent value changed");
        codex_agent_cpp_mock_conversation_set_phase(active_kind, 1);
        auto current = value.conversations.active();
        require(current && current->same_as(value.conversation),
                "active conversation identity changed");
        state_contract<std::optional<codex_agent::Conversation>>(
            active_kind,
            [&] { return value.conversations.active(); },
            [&](auto callback) {
                return value.conversations.subscribe_active(
                    std::move(callback));
            },
            [&](const auto& active, int phase) {
                require((phase == 0 && !active) ||
                            (phase == 1 && active &&
                             active->same_as(value.conversation)),
                        "active transition lost nullability or identity");
            });
        pass("cpp.conversation:005", passed);
    }
    {
        auto value = fixture();
        async_void_contract([&] { return value.conversation.cancel_turn(); });
        pass("cpp.conversation:006", passed);
    }
    {
        auto value = fixture();
        async_void_contract([&] { return value.conversation.close(); });
        value.conversation.close().get();
        require(value.conversation.state().status ==
                    codex_agent::ConversationStatus::closed,
                "repeated close did not close conversation");
        pass("cpp.conversation:007", passed);
    }
    {
        auto value = fixture();
        async_void_contract([&] { return value.conversation.reload(); });
        pass("cpp.conversation:008", passed);
    }
    {
        auto value = fixture();
        async_void_contract([&] {
            return value.conversation.run_shell_command("pwd");
        });
        require_invalid([&] {
            (void)value.conversation.run_shell_command("wrong");
        });
        pass("cpp.conversation:009", passed);
    }
    {
        auto value = fixture();
        async_void_contract([&] { return value.conversation.send(request()); });
        auto wrong_prompt = request();
        wrong_prompt.prompt = "wrong";
        require_invalid([&] { (void)value.conversation.send(wrong_prompt); });
        auto wrong_model = request();
        wrong_model.model = "wrong";
        require_invalid([&] { (void)value.conversation.send(wrong_model); });
        auto wrong_effort = request();
        wrong_effort.effort = "wrong";
        require_invalid([&] { (void)value.conversation.send(wrong_effort); });
        auto wrong_tier = request();
        wrong_tier.service_tier = "wrong";
        require_invalid([&] { (void)value.conversation.send(wrong_tier); });
        auto wrong_preset = request();
        wrong_preset.approval_preset = codex_agent::ApprovalPreset::never;
        require_invalid([&] { (void)value.conversation.send(wrong_preset); });
        auto wrong_capability = request();
        wrong_capability.capabilities.clear();
        require_invalid(
            [&] { (void)value.conversation.send(wrong_capability); });
        auto wrong_mode = request();
        wrong_mode.collaboration_mode =
            codex_agent::CollaborationMode::default_;
        require_invalid([&] { (void)value.conversation.send(wrong_mode); });
        auto wrong_client = request();
        wrong_client.client_message_id = "wrong";
        require_invalid([&] { (void)value.conversation.send(wrong_client); });
        auto wrong_plugin = request();
        std::get<codex_agent::PluginInvocation>(
            wrong_plugin.invocations[0]).uri = "wrong";
        require_invalid([&] { (void)value.conversation.send(wrong_plugin); });
        auto wrong_skill = request();
        std::get<codex_agent::SkillInvocation>(
            wrong_skill.invocations[1]).path = "wrong";
        require_invalid([&] { (void)value.conversation.send(wrong_skill); });
        codex_agent::TurnRequest defaults;
        defaults.prompt = "structured-default";
        value.conversation.send(std::move(defaults)).get();
        pass("cpp.conversation:010", passed);
    }
    {
        auto value = fixture();
        async_void_contract([&] { return value.conversation.send("hello"); });
        require_invalid([&] { (void)value.conversation.send("wrong"); });
        pass("cpp.conversation:011", passed);
    }
    {
        auto value = fixture();
        state_contract<std::optional<codex_agent::TurnProgress>>(
            progress_kind,
            [&] { return value.conversation.active_turn_progress(); },
            [&](auto callback) {
                return value.conversation.subscribe_active_turn_progress(
                    std::move(callback));
            },
            [](const auto& progress, int phase) {
                require((phase == 0 && !progress) ||
                            (phase == 1 && progress &&
                             progress->text == "progress" &&
                             progress->shell_exit_code == 0 &&
                             progress->work_activity ==
                                 codex_agent::WorkActivity::running_command &&
                             progress->is_truncated),
                        "active progress transition lost values");
            });
        pass("cpp.conversation:012", passed);
    }

    const auto boolean_capability = [&](
        const char* id, int kind, auto current, auto subscribe) {
        auto value = fixture();
        state_contract<bool>(
            kind,
            [&] { return current(value.conversation); },
            [&](auto callback) {
                return subscribe(value.conversation, std::move(callback));
            },
            [](bool observed, int phase) {
                require(observed == (phase == 1),
                        "boolean state transition changed");
            });
        pass(id, passed);
    };
    boolean_capability(
        "cpp.conversation:013", can_cancel_kind,
        [](const auto& value) { return value.can_cancel_turn(); },
        [](const auto& value, auto callback) {
            return value.subscribe_can_cancel_turn(std::move(callback));
        });
    boolean_capability(
        "cpp.conversation:014", can_reload_kind,
        [](const auto& value) { return value.can_reload(); },
        [](const auto& value, auto callback) {
            return value.subscribe_can_reload(std::move(callback));
        });
    boolean_capability(
        "cpp.conversation:015", can_shell_kind,
        [](const auto& value) { return value.can_run_shell_command(); },
        [](const auto& value, auto callback) {
            return value.subscribe_can_run_shell_command(std::move(callback));
        });
    boolean_capability(
        "cpp.conversation:016", can_start_kind,
        [](const auto& value) { return value.can_start_turn(); },
        [](const auto& value, auto callback) {
            return value.subscribe_can_start_turn(std::move(callback));
        });
    {
        auto value = fixture();
        state_contract<std::vector<codex_agent::Message>>(
            messages_kind,
            [&] { return value.conversation.current_messages(); },
            [&](auto callback) {
                return value.conversation.subscribe_current_messages(
                    std::move(callback));
            },
            [](const auto& messages, int phase) {
                require(messages.size() == 2 &&
                            messages[0].id == "message-a" &&
                            messages[1].id == "message-b" &&
                            messages[0].text ==
                                (phase == 0 ? "current-0" : "changed-0") &&
                            messages[0].reasoning &&
                            !messages[1].reasoning,
                        "message state lost ordering or nullability");
            });
        pass("cpp.conversation:017", passed);
    }
    boolean_capability(
        "cpp.conversation:018", is_active_kind,
        [](const auto& value) { return value.is_turn_active(); },
        [](const auto& value, auto callback) {
            return value.subscribe_is_turn_active(std::move(callback));
        });
    {
        auto value = fixture();
        codex_agent_cpp_mock_conversation_set_phase(state_kind, 0);
        auto current = value.conversation.state();
        require(current.status == codex_agent::ConversationStatus::ready &&
                    current.conversation_id && current.conversation &&
                    current.model == "model" && current.effort == "high" &&
                    current.service_tier == "priority" &&
                    current.conversation->messages.size() == 2,
                "conversation state current value is incomplete");
        std::vector<codex_agent::StateEvent<codex_agent::ConversationState>>
            events;
        auto subscription = value.conversation.subscribe_state(
            [&](auto event) { events.push_back(std::move(event)); });
        codex_agent_cpp_mock_conversation_set_phase(state_kind, 1);
        codex_agent_cpp_mock_conversation_publish(state_kind, 0);
        require(events.size() == 2 && events.back().value &&
                    events.back().value->status ==
                        codex_agent::ConversationStatus::running_turn,
                "conversation state change is missing");
        codex_agent_cpp_mock_conversation_set_phase(state_kind, 2);
        codex_agent_cpp_mock_conversation_publish(state_kind, 0);
        require(events.size() == 3 && events.back().value &&
                    events.back().value->status ==
                        codex_agent::ConversationStatus::failed &&
                    events.back().value->failure &&
                    events.back().value->failure->code == "state_failed",
                "conversation state structured failure is missing");
        subscription.close();
        require(events.size() == 4 && events.back().terminal,
                "conversation state terminal is missing");
        const auto count = events.size();
        codex_agent_cpp_mock_conversation_publish(state_kind, 0);
        require(events.size() == count,
                "conversation state continued after close");
        pass("cpp.conversation:019", passed);
    }

    require(passed.size() == 20 && scenarios().size() == 20,
            "conversation capability execution is incomplete");
    const auto receipt = std::filesystem::path(argv[1]);
    std::filesystem::create_directories(receipt.parent_path());
    std::ofstream output(receipt, std::ios::binary | std::ios::trunc);
    require(output.good(), "cannot create conversation receipt");
    output << "executedTestId\tscenarios\tstatus\n";
    for (const auto& id : passed)
        output << id << '\t' << scenarios().at(id) << "\tpassed\n";
    require(output.good(), "cannot write conversation receipt");
}
