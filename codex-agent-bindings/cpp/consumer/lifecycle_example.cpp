#include <codex_agent/codex_agent.hpp>

int main() {
    auto host = codex_agent::Host::create({
        .bundle_directory = "/bundle",
        .data_directory = "/data",
        .client_info = {"cpp-example", "C++ example", "1.0.0"},
    });
    host.start().get();
    if (host.state().kind != codex_agent::HostStateKind::ready) return 1;

    {
        codex_agent::HostStateReady ready(host.agent());
        auto conversations = ready.agent.conversations();
        auto conversation = conversations.open().get();
        conversation.send("hello").get();
        conversation.close().get();
        host.close().get();
    }
    return 0;
}
