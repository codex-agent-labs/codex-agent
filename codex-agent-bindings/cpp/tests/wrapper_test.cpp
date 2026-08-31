#include <codex_agent/codex_agent.hpp>

#include <cassert>
#include <atomic>
#include <chrono>
#include <stdexcept>
#include <thread>
#include <type_traits>

using namespace std::chrono_literals;

int main() {
    static_assert(std::is_move_constructible_v<codex_agent::Host>);
    static_assert(!std::is_copy_constructible_v<codex_agent::Host>);
    static_assert(std::is_move_constructible_v<codex_agent::Conversation>);
    static_assert(!std::is_copy_constructible_v<codex_agent::Conversation>);

    auto host = codex_agent::Host::create({
        .bundle_directory = "/bundle",
        .data_directory = "/data",
        .client_info = {"cpp-test", "C++ test", "1"},
    });

    const auto host_state = host.state();
    assert(host_state.kind == codex_agent::HostStateKind::ready);
    assert(host_state.workspace.has_value());
    assert(host_state.workspace->path == "/workspace");
    assert(host_state.workspace->display_name.empty());

    std::atomic<int> host_events = 0;
    std::atomic<bool> host_terminal = false;
    auto host_subscription = host.subscribe(
        [&](codex_agent::StateEvent<codex_agent::HostState> event) {
            if (event.terminal) {
                assert(event.status == codex_agent::Status::cancelled);
                assert(!event.value.has_value());
                host_terminal = true;
            } else {
                assert(event.status == codex_agent::Status::ok);
                assert(event.value->kind == codex_agent::HostStateKind::ready);
            }
            ++host_events;
        });
    while (host_events < 2) {
        std::this_thread::sleep_for(1ms);
    }
    host_subscription.close();
    host_subscription.close();
    assert(host_terminal);
    assert(host_events == 3);

    std::atomic<int> throwing_events = 0;
    auto throwing_subscription = host.subscribe(
        [&](codex_agent::StateEvent<codex_agent::HostState>) {
            ++throwing_events;
            throw std::runtime_error("must not cross the C callback boundary");
        });
    assert(throwing_events >= 1);
    assert(throwing_subscription.callback_error() != nullptr);
    throwing_subscription.close();

    host.start().get();
    host.select_workspace("/workspace").get();

    auto agent = host.agent();
    auto conversations = agent.conversations();
    const auto summaries = conversations.list().get();
    assert(summaries.size() == 2);
    assert(summaries[0].conversation_id.value == "conversation-a");
    assert(summaries[0].title == "First");
    assert(summaries[0].updated_at_epoch_seconds == 100);
    assert(summaries[1].conversation_id.value == "conversation-a");
    assert(summaries[1].title == "Second");
    assert(summaries[1].updated_at_epoch_seconds == 101);
    auto conversation = conversations.open(
        codex_agent::ConversationId("conversation-a"),
        {.approval_preset = codex_agent::ApprovalPreset::ask_me,
         .service_tier = "priority"}).get();
    auto another = conversations.open().get();
    assert(conversation.same_as(another));

    const auto conversation_state = conversation.state();
    assert(conversation_state.status == codex_agent::ConversationStatus::ready);
    assert(!conversation_state.failure.has_value());

    std::atomic<int> conversation_events = 0;
    std::atomic<bool> conversation_terminal = false;
    auto conversation_subscription = conversation.subscribe(
        [&](codex_agent::StateEvent<codex_agent::ConversationState> event) {
            if (event.terminal) {
                assert(event.status == codex_agent::Status::cancelled);
                conversation_terminal = true;
            } else {
                assert(event.value->status == codex_agent::ConversationStatus::ready);
            }
            ++conversation_events;
        });
    while (conversation_events < 2) {
        std::this_thread::sleep_for(1ms);
    }
    conversation_subscription.close();
    conversation_subscription.close();
    assert(conversation_terminal);
    assert(conversation_events == 3);

    conversation.send("hello").get();
    conversation.reload().get();
    conversation.cancel_turn().get();

    auto operation_after_owner_destruction =
        conversations.open().get().send("slow");
    operation_after_owner_destruction.get();

    auto slow = conversation.send("cancel-inline");
    slow.cancel();
    try {
        slow.get();
        assert(false);
    } catch (const codex_agent::OperationError& error) {
        assert(error.status() == codex_agent::Status::cancelled);
        assert(!error.failure().has_value());
    }

    try {
        conversation.send("fail").get();
        assert(false);
    } catch (const codex_agent::OperationError& error) {
        assert(error.status() == codex_agent::Status::operation_failed);
        assert(error.failure().has_value());
        assert(error.failure()->code == "turn_failed");
        assert(error.failure()->message == "mock turn failed");
        assert(error.failure()->recoverable);
    }

    conversation.close().get();
    conversation.close().get();
    assert(conversation.state().status == codex_agent::ConversationStatus::closed);
    host.close().get();
    host.close().get();
    assert(host.state().kind == codex_agent::HostStateKind::closed);
}
