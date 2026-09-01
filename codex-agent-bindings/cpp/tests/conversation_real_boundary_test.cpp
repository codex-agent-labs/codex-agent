#include <codex_agent/codex_agent.hpp>

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <map>
#include <optional>
#include <string>

namespace {

void require(bool condition, const char* message) {
    if (!condition) {
        (void)message;
        std::abort();
    }
}

template <typename Value>
Value null_argument() {
    return Value{};
}

template <typename... Arguments>
codex_agent_status_t invoke_null_boundary(
    codex_agent_status_t (*function)(Arguments...)) {
    return function(null_argument<Arguments>()...);
}

template <typename Action>
void typed_real_rejection(Action&& action, std::size_t& calls) {
    try {
        action();
    } catch (const codex_agent::Error& error) {
        require(error.status() != codex_agent::Status::ok,
                "typed real SDK boundary reported success");
        ++calls;
        return;
    }
    require(false, "typed wrapper accepted an invalid real owner");
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
    require(argc == 2,
            "usage: conversation_real_boundary_test RECEIPT");
    codex_agent::Conversations conversations;
    codex_agent::Conversation conversation;

    std::map<std::string, std::size_t> typed;
    const auto prove = [&](const char* capability, auto&& action) {
        typed_real_rejection(action, typed[capability]);
    };
    prove("cpp.conversation:000", [&] {
        (void)conversations.remove(codex_agent::ConversationId("conversation-a"));
    });
    prove("cpp.conversation:001", [&] { (void)conversations.list(); });
    prove("cpp.conversation:002", [&] { (void)conversations.open(); });
    prove("cpp.conversation:003", [&] {
        (void)conversations.read(codex_agent::ConversationId("conversation-a"));
    });
    prove("cpp.conversation:004", [&] {
        (void)conversations.rename(
            codex_agent::ConversationId("conversation-a"), "Renamed");
    });
    prove("cpp.conversation:005", [&] { (void)conversations.active(); });
    prove("cpp.conversation:005", [&] {
        (void)conversations.subscribe_active([](auto) {});
    });
    prove("cpp.conversation:006", [&] { (void)conversation.cancel_turn(); });
    prove("cpp.conversation:007", [&] { (void)conversation.close(); });
    prove("cpp.conversation:008", [&] { (void)conversation.reload(); });
    prove("cpp.conversation:009", [&] {
        (void)conversation.run_shell_command("pwd");
    });
    prove("cpp.conversation:010", [&] { (void)conversation.send(request()); });
    prove("cpp.conversation:011", [&] { (void)conversation.send("hello"); });
    prove("cpp.conversation:012", [&] {
        (void)conversation.active_turn_progress();
    });
    prove("cpp.conversation:012", [&] {
        (void)conversation.subscribe_active_turn_progress([](auto) {});
    });
    prove("cpp.conversation:013", [&] {
        (void)conversation.can_cancel_turn();
    });
    prove("cpp.conversation:013", [&] {
        (void)conversation.subscribe_can_cancel_turn([](auto) {});
    });
    prove("cpp.conversation:014", [&] { (void)conversation.can_reload(); });
    prove("cpp.conversation:014", [&] {
        (void)conversation.subscribe_can_reload([](auto) {});
    });
    prove("cpp.conversation:015", [&] {
        (void)conversation.can_run_shell_command();
    });
    prove("cpp.conversation:015", [&] {
        (void)conversation.subscribe_can_run_shell_command([](auto) {});
    });
    prove("cpp.conversation:016", [&] { (void)conversation.can_start_turn(); });
    prove("cpp.conversation:016", [&] {
        (void)conversation.subscribe_can_start_turn([](auto) {});
    });
    prove("cpp.conversation:017", [&] {
        (void)conversation.current_messages();
    });
    prove("cpp.conversation:017", [&] {
        (void)conversation.subscribe_current_messages([](auto) {});
    });
    prove("cpp.conversation:018", [&] { (void)conversation.is_turn_active(); });
    prove("cpp.conversation:018", [&] {
        (void)conversation.subscribe_is_turn_active([](auto) {});
    });
    prove("cpp.conversation:019", [&] { (void)conversation.state(); });
    prove("cpp.conversation:019", [&] {
        (void)conversation.subscribe_state([](auto) {});
    });
    require(typed.size() == 20,
            "typed real SDK conversation capability coverage is incomplete");
    std::size_t typed_calls = 0;
    for (const auto& [capability, calls] : typed) {
        (void)capability;
        require(calls != 0, "typed real SDK capability was not invoked");
        typed_calls += calls;
    }
    require(typed_calls == 29,
            "typed real SDK conversation member coverage is incomplete");

    std::map<std::string, std::size_t> raw;
#define CONVERSATION_NATIVE_BOUNDARY(capability, function)                  \
    do {                                                                    \
        const auto status = invoke_null_boundary(&function);                \
        require(status != CODEX_AGENT_STATUS_OK,                            \
                "real SDK accepted a null conversation boundary");         \
        ++raw[capability];                                                   \
    } while (false);
#include "conversation_native_boundaries.inc"
#undef CONVERSATION_NATIVE_BOUNDARY

    require(raw.size() == 20,
            "real SDK exact conversation reference coverage is incomplete");
    std::size_t raw_calls = 0;
    for (const auto& [capability, calls] : raw) {
        require(typed.contains(capability) && calls != 0,
                "raw exact reference lacks a typed production owner");
        raw_calls += calls;
    }
    require(raw_calls == 49,
            "real SDK exact conversation reference count is incomplete");

    const auto receipt = std::filesystem::path(argv[1]);
    std::filesystem::create_directories(receipt.parent_path());
    std::ofstream output(receipt, std::ios::binary | std::ios::trunc);
    require(output.good(), "cannot create real SDK conversation receipt");
    output << "executedTestId\tboundary\tstatus\n";
    for (const auto& [id, calls] : raw) {
        (void)calls;
        output << id
               << "\ttyped-production-real-sdk-invalid-owner+raw-exact-null-boundary\tpassed\n";
    }
    require(output.good(), "cannot write real SDK conversation receipt");
}
