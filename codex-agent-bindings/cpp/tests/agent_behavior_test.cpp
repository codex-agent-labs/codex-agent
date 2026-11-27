#include <codex_agent/codex_agent.hpp>

#include "agent_native_probe.hpp"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <map>
#include <string>
#include <type_traits>
#include <utility>

using AgentAuthentication = codex_agent::Authentication
    (codex_agent::Agent::*)() const;
using AgentConnectors = codex_agent::Connectors (codex_agent::Agent::*)() const;
using AgentConversations = codex_agent::Conversations
    (codex_agent::Agent::*)() const;
using AgentHooks = codex_agent::Hooks (codex_agent::Agent::*)() const;
using AgentIntegrationAuthorization = codex_agent::IntegrationAuthorization
    (codex_agent::Agent::*)() const;
using AgentInteractions = codex_agent::Interactions
    (codex_agent::Agent::*)() const;
using AgentMcpServers = codex_agent::McpServers
    (codex_agent::Agent::*)() const;
using AgentModels = codex_agent::Models (codex_agent::Agent::*)() const;
using AgentPlugins = codex_agent::Plugins (codex_agent::Agent::*)() const;
using AgentSkills = codex_agent::Skills (codex_agent::Agent::*)() const;
using AgentWorkspace = codex_agent::Workspace (codex_agent::Agent::*)() const;

static_assert(std::is_same_v<decltype(&codex_agent::Agent::authentication),
                             AgentAuthentication>);
static_assert(std::is_same_v<decltype(&codex_agent::Agent::connectors),
                             AgentConnectors>);
static_assert(std::is_same_v<decltype(&codex_agent::Agent::conversations),
                             AgentConversations>);
static_assert(std::is_same_v<decltype(&codex_agent::Agent::hooks), AgentHooks>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Agent::integration_authorization),
              AgentIntegrationAuthorization>);
static_assert(std::is_same_v<decltype(&codex_agent::Agent::interactions),
                             AgentInteractions>);
static_assert(std::is_same_v<decltype(&codex_agent::Agent::mcp_servers),
                             AgentMcpServers>);
static_assert(std::is_same_v<decltype(&codex_agent::Agent::models), AgentModels>);
static_assert(std::is_same_v<decltype(&codex_agent::Agent::plugins), AgentPlugins>);
static_assert(std::is_same_v<decltype(&codex_agent::Agent::skills), AgentSkills>);
static_assert(std::is_same_v<decltype(&codex_agent::Agent::workspace),
                             AgentWorkspace>);

#define AGENT_NATIVE_BOUNDARY(capability, function)                        \
    static_assert(std::is_pointer_v<decltype(&function)>);
#include "agent_native_boundaries.inc"
#undef AGENT_NATIVE_BOUNDARY

extern "C" void codex_agent_cpp_mock_agent_change_workspace();
extern "C" int codex_agent_cpp_mock_agent_identity_stable();
extern "C" int codex_agent_cpp_mock_agent_exact_release_order();
extern "C" std::size_t codex_agent_cpp_mock_agent_child_release_count();
extern "C" std::size_t codex_agent_cpp_mock_agent_agent_release_count();
extern "C" std::size_t codex_agent_cpp_mock_agent_host_release_count();
extern "C" std::size_t codex_agent_cpp_mock_agent_context_destroy_count();
extern "C" std::size_t codex_agent_cpp_mock_agent_premature_release_count();

namespace {

[[noreturn]] void fail(const char* message) {
    (void)message;
    std::abort();
}

void require(bool condition, const char* message) {
    if (!condition) fail(message);
}

template <typename Action>
void require_closed(Action&& action) {
    try {
        action();
    } catch (const codex_agent::Error& error) {
        require(error.status() == codex_agent::Status::closed,
                "moved-from agent reported the wrong status");
        return;
    }
    fail("moved-from agent projected a child");
}

bool edge_seen_since(AgentNativeEdge edge, std::size_t start) {
    for (auto index = start; index < codex_agent_cpp_mock_agent_event_count();
         ++index) {
        if (codex_agent_cpp_mock_agent_event_at(index) == edge) return true;
    }
    return false;
}

const std::map<std::string, std::string>& scenarios() {
    static const std::map<std::string, std::string> values{
#define AGENT_SCENARIO(capability, scenario) {capability, scenario},
#include "agent_scenarios.inc"
#undef AGENT_SCENARIO
    };
    return values;
}

void require_exact_edge(std::string_view capability, std::size_t start) {
    bool matched = false;
    bool complete = true;
#define AGENT_NATIVE_BOUNDARY(expected, function)                          \
    if (capability == expected) {                                          \
        matched = true;                                                    \
        complete = complete &&                                             \
            edge_seen_since(AgentNativeEdge::function, start);             \
    }
#include "agent_native_boundaries.inc"
#undef AGENT_NATIVE_BOUNDARY
    require(matched && complete, "agent capability missed its native edge");
}

template <typename Child>
void prove_service(
    const char* capability, Child (codex_agent::Agent::*member)() const,
    std::map<std::string, std::string>& passed) {
    codex_agent_cpp_mock_agent_reset();
    const auto start = codex_agent_cpp_mock_agent_event_count();
    {
        auto child = [&] {
            auto host = codex_agent::Host::create({
                "/bundle", "/data", {"agent-test", "Agent Test", "1"}});
            auto agent = host.agent();
            auto first = (agent.*member)();
            auto second = (agent.*member)();
            auto parent = std::move(agent);
            const auto before_rejection =
                codex_agent_cpp_mock_agent_event_count();
            require_closed([&] { (void)(agent.*member)(); });
            require(codex_agent_cpp_mock_agent_event_count() ==
                        before_rejection,
                    "fail-closed projection crossed the native boundary");
            require(codex_agent_cpp_mock_agent_identity_stable() != 0,
                    "repeated projections lost native identity");
            (void)parent;
            (void)second;
            return first;
        }();
        require(codex_agent_cpp_mock_agent_child_release_count() == 1,
                "sibling child did not release after its parent");
        require(codex_agent_cpp_mock_agent_agent_release_count() == 2,
                "parent and sibling Agent handles did not release exactly");
        require(codex_agent_cpp_mock_agent_host_release_count() == 1,
                "source Host did not release while retained Host survived");
        require(codex_agent_cpp_mock_agent_context_destroy_count() == 0,
                "child did not retain its native context");
        (void)child;
    }
    require(codex_agent_cpp_mock_agent_child_release_count() == 2,
            "surviving child did not release");
    require(codex_agent_cpp_mock_agent_agent_release_count() == 3,
            "retained Agent handles did not release exactly");
    require(codex_agent_cpp_mock_agent_host_release_count() == 2,
            "retained Host did not release after every Agent");
    require(codex_agent_cpp_mock_agent_exact_release_order() != 0,
            "release order was not child then Agent then Host");
    require(codex_agent_cpp_mock_agent_context_destroy_count() == 1,
            "child/context ownership did not quiesce");
    require(codex_agent_cpp_mock_agent_premature_release_count() == 0,
            "native parent release was attempted with live children");
    require_exact_edge(capability, start);
    require(passed.emplace(capability, scenarios().at(capability)).second,
            "duplicate agent capability");
}

void prove_workspace(std::map<std::string, std::string>& passed) {
    codex_agent_cpp_mock_agent_reset();
    const auto start = codex_agent_cpp_mock_agent_event_count();
    codex_agent::Workspace copied;
    {
        auto host = codex_agent::Host::create({
            "/bundle", "/data", {"workspace-test", "Workspace Test", "1"}});
        auto agent = host.agent();
        copied = agent.workspace();
        const auto duplicate = agent.workspace();
        require(duplicate.path == copied.path &&
                    duplicate.display_name == copied.display_name &&
                    codex_agent_cpp_mock_agent_identity_stable() != 0,
                "workspace projection was not identity-stable");
        codex_agent_cpp_mock_agent_change_workspace();
        auto parent = std::move(agent);
        const auto before_rejection = codex_agent_cpp_mock_agent_event_count();
        require_closed([&] { (void)agent.workspace(); });
        require(codex_agent_cpp_mock_agent_event_count() == before_rejection,
                "fail-closed workspace crossed the native boundary");
        (void)parent;
    }
    require(copied.path == "/workspace" &&
                copied.display_name == "Workspace",
            "workspace did not retain an independent owned copy");
    require(codex_agent_cpp_mock_agent_child_release_count() == 2 &&
                codex_agent_cpp_mock_agent_agent_release_count() == 3 &&
                codex_agent_cpp_mock_agent_host_release_count() == 2,
            "workspace snapshot/Agent/Host teardown count was not exact");
    require(codex_agent_cpp_mock_agent_exact_release_order() != 0,
            "workspace teardown order was not snapshot then Agent then Host");
    require(codex_agent_cpp_mock_agent_context_destroy_count() == 1,
            "workspace projection retained native ownership");
    require(codex_agent_cpp_mock_agent_premature_release_count() == 0,
            "workspace teardown attempted a premature parent release");
    require_exact_edge("cpp.agent:010", start);
    require(passed.emplace("cpp.agent:010", scenarios().at("cpp.agent:010"))
                .second,
            "duplicate workspace capability");
}

}  // namespace

int main(int argc, char** argv) {
    require(argc == 2, "usage: agent_behavior_test RECEIPT");
    std::map<std::string, std::string> passed;
    prove_service("cpp.agent:000", &codex_agent::Agent::authentication, passed);
    prove_service("cpp.agent:001", &codex_agent::Agent::connectors, passed);
    prove_service("cpp.agent:002", &codex_agent::Agent::conversations, passed);
    prove_service("cpp.agent:003", &codex_agent::Agent::hooks, passed);
    prove_service(
        "cpp.agent:004", &codex_agent::Agent::integration_authorization,
        passed);
    prove_service("cpp.agent:005", &codex_agent::Agent::interactions, passed);
    prove_service("cpp.agent:006", &codex_agent::Agent::mcp_servers, passed);
    prove_service("cpp.agent:007", &codex_agent::Agent::models, passed);
    prove_service("cpp.agent:008", &codex_agent::Agent::plugins, passed);
    prove_service("cpp.agent:009", &codex_agent::Agent::skills, passed);
    prove_workspace(passed);
    require(passed.size() == 11, "agent capability execution is incomplete");

    std::ofstream output(
        std::filesystem::path(argv[1]), std::ios::binary | std::ios::trunc);
    require(output.good(), "cannot create agent receipt");
    output << "executedTestId\tscenarios\tstatus\n";
    for (const auto& [capability, scenario] : passed)
        output << capability << '\t' << scenario << "\tpassed\n";
    require(output.good(), "cannot write agent receipt");
}
