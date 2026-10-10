#include <codex_agent/codex_agent.hpp>

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <optional>
#include <string>

namespace {

void require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << message << '\n';
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
    } catch (const std::exception&) {
        ++calls;
        return;
    }
    require(false, "typed production wrapper accepted an invalid real service");
}

}  // namespace

int main(int argc, char** argv) {
    require(argc == 2,
            "usage: leaf_real_boundary_test REAL_BOUNDARY_RECEIPT");

    struct LeafServices {
        codex_agent::Authentication authentication;
        codex_agent::Interactions interactions;
        codex_agent::IntegrationAuthorization integration_authorization;
        codex_agent::Models models;
        codex_agent::Skills skills;
        codex_agent::Hooks hooks;
        codex_agent::Plugins plugins;
        codex_agent::Connectors connectors;
        codex_agent::McpServers mcp_servers;
    } leaf;
    const codex_agent::PendingApproval pending_approval{
        {"approval", codex_agent::ConversationId("conversation")},
        "Approve", "details"};
    const codex_agent::Elicitation elicitation{
        "elicitation", codex_agent::ConversationId("conversation"),
        "server", "message", std::nullopt, std::nullopt};
    const codex_agent::PendingElicitation pending_elicitation{
        {"elicitation", codex_agent::ConversationId("conversation")},
        elicitation};

    const codex_agent::Connector connector{
        "connector", "Connector", "description", std::nullopt, true, true,
        {}};
    const codex_agent::Hook hook{
        "hook", "after-turn", std::nullopt, codex_agent::hook_handler_agent,
        1, codex_agent::HookTrustStatus::trusted, "hash", true, "user",
        "/hook", codex_agent::ResourceOrigin::user, std::nullopt, false, true,
        true, std::nullopt};
    const codex_agent::ConnectorIntegration connector_integration{
        {"connector:connector", "Connector"}, connector};
    const codex_agent::McpServer server{
        "server", "Server", codex_agent::McpAuthStatus::unknown};
    const codex_agent::McpServerIntegration mcp_integration{
        {"mcp:server", "Server"}, server};
    const codex_agent::McpServerConfiguration configuration(
        "server", codex_agent::McpHttpTransport("https://example.com"));
    const codex_agent::Model model{
        "model", "Model", "description", {}, "medium", true, {},
        std::nullopt};
    const codex_agent::PluginReference plugin{
        "plugin", "plugin", "market", std::nullopt, std::nullopt};
    const codex_agent::Skill skill(
        "skill", "Skill", "description", "/skill",
        codex_agent::SkillScope::user, true);

    std::map<std::string, std::size_t> typed;
    const auto prove = [&](const char* capability, auto&& action) {
        typed_real_rejection(action, typed[capability]);
    };
    prove("cpp.leaf:000", [&] {
        (void)leaf.authentication.authenticate(
            codex_agent::ApiKeyAuthentication("key"));
    });
    prove("cpp.leaf:000", [&] {
        (void)leaf.authentication.authenticate(
            codex_agent::chat_gpt_browser_authentication);
    });
    prove("cpp.leaf:000", [&] {
        (void)leaf.authentication.authenticate(
            codex_agent::chat_gpt_device_code_authentication);
    });
    prove("cpp.leaf:001", [&] { (void)leaf.authentication.cancel(); });
    prove("cpp.leaf:002", [&] { (void)leaf.authentication.sign_out(); });
    prove("cpp.leaf:003", [&] {
        (void)leaf.authentication.is_authenticated();
    });
    prove("cpp.leaf:003", [&] {
        (void)leaf.authentication.subscribe_is_authenticated(
            [](codex_agent::StateEvent<bool>) {});
    });
    prove("cpp.leaf:004", [&] {
        (void)leaf.authentication.is_authenticating();
    });
    prove("cpp.leaf:004", [&] {
        (void)leaf.authentication.subscribe_is_authenticating(
            [](codex_agent::StateEvent<bool>) {});
    });
    prove("cpp.leaf:005", [&] { (void)leaf.authentication.state(); });
    prove("cpp.leaf:005", [&] {
        (void)leaf.authentication.subscribe_state(
            [](codex_agent::StateEvent<codex_agent::AuthenticationState>) {});
    });
    prove("cpp.leaf:006", [&] { (void)leaf.connectors.list(true); });
    prove("cpp.leaf:007", [&] { (void)leaf.connectors.is_available(); });
    prove("cpp.leaf:008", [&] {
        (void)leaf.hooks.install("/hook", codex_agent::InstallationScope::user);
    });
    prove("cpp.leaf:009", [&] { (void)leaf.hooks.list(); });
    prove("cpp.leaf:010", [&] { (void)leaf.hooks.trust(hook); });
    prove("cpp.leaf:011", [&] { (void)leaf.hooks.uninstall(hook); });
    prove("cpp.leaf:012", [&] { (void)leaf.hooks.is_available(); });
    prove("cpp.leaf:013", [&] {
        (void)leaf.integration_authorization.authorize(connector_integration);
    });
    prove("cpp.leaf:013", [&] {
        (void)leaf.integration_authorization.authorize(mcp_integration);
    });
    prove("cpp.leaf:014", [&] {
        (void)leaf.integration_authorization.cancel();
    });
    prove("cpp.leaf:015", [&] {
        (void)leaf.integration_authorization.active();
    });
    prove("cpp.leaf:015", [&] {
        (void)leaf.integration_authorization.subscribe_active(
            [](codex_agent::StateEvent<
                std::optional<codex_agent::IntegrationValue>>) {});
    });
    prove("cpp.leaf:016", [&] {
        (void)leaf.integration_authorization.is_authorizing();
    });
    prove("cpp.leaf:016", [&] {
        (void)leaf.integration_authorization.subscribe_is_authorizing(
            [](codex_agent::StateEvent<bool>) {});
    });
    prove("cpp.leaf:017", [&] {
        (void)leaf.integration_authorization.state();
    });
    prove("cpp.leaf:017", [&] {
        (void)leaf.integration_authorization.subscribe_state(
            [](codex_agent::StateEvent<
                codex_agent::IntegrationAuthorizationState>) {});
    });
    prove("cpp.leaf:018", [&] {
        (void)leaf.interactions.open_url(pending_elicitation);
    });
    prove("cpp.leaf:019", [&] {
        (void)leaf.interactions.resolve(
            pending_approval, codex_agent::ApprovalDecision::accept);
    });
    prove("cpp.leaf:020", [&] {
        (void)leaf.interactions.resolve(
            pending_elicitation,
            codex_agent::ElicitationResponse{
                codex_agent::ElicitationAction::decline, {}});
    });
    prove("cpp.leaf:021", [&] { (void)leaf.interactions.approvals(); });
    prove("cpp.leaf:021", [&] {
        (void)leaf.interactions.subscribe_approvals(
            [](codex_agent::StateEvent<
                std::vector<codex_agent::PendingApproval>>) {});
    });
    prove("cpp.leaf:022", [&] { (void)leaf.interactions.elicitations(); });
    prove("cpp.leaf:022", [&] {
        (void)leaf.interactions.subscribe_elicitations(
            [](codex_agent::StateEvent<
                std::vector<codex_agent::PendingElicitation>>) {});
    });
    prove("cpp.leaf:023", [&] { (void)leaf.interactions.state(); });
    prove("cpp.leaf:023", [&] {
        (void)leaf.interactions.subscribe_state(
            [](codex_agent::StateEvent<codex_agent::InteractionState>) {});
    });
    prove("cpp.leaf:024", [&] { (void)leaf.mcp_servers.add(configuration); });
    prove("cpp.leaf:025", [&] { (void)leaf.mcp_servers.list(); });
    prove("cpp.leaf:026", [&] { (void)leaf.mcp_servers.remove(server); });
    prove("cpp.leaf:027", [&] { (void)leaf.mcp_servers.is_available(); });
    prove("cpp.leaf:028", [&] { (void)leaf.models.list(); });
    prove("cpp.leaf:029", [&] { (void)leaf.models.resolve_effort(model); });
    prove("cpp.leaf:030", [&] {
        (void)leaf.models.resolve_service_tier(model);
    });
    prove("cpp.leaf:031", [&] { (void)leaf.models.resolve(); });
    prove("cpp.leaf:032", [&] { (void)leaf.plugins.install(plugin); });
    prove("cpp.leaf:033", [&] { (void)leaf.plugins.list(true); });
    prove("cpp.leaf:034", [&] { (void)leaf.plugins.read(plugin); });
    prove("cpp.leaf:035", [&] { (void)leaf.plugins.uninstall(plugin); });
    prove("cpp.leaf:036", [&] { (void)leaf.plugins.is_available(); });
    prove("cpp.leaf:037", [&] {
        (void)leaf.skills.install(
            "/skill", codex_agent::InstallationScope::user);
    });
    prove("cpp.leaf:038", [&] { (void)leaf.skills.list(true); });
    prove("cpp.leaf:039", [&] { (void)leaf.skills.read("/skill", 7); });
    prove("cpp.leaf:040", [&] { (void)leaf.skills.uninstall(skill); });
    prove("cpp.leaf:041", [&] { (void)leaf.skills.is_available(); });

    require(typed.size() == 42,
            "typed real SDK leaf capability coverage is incomplete");
    std::size_t typed_calls = 0;
    for (const auto& [capability, calls] : typed) {
        (void)capability;
        require(calls != 0, "typed real SDK capability was not invoked");
        typed_calls += calls;
    }
    require(typed_calls == 54,
            "typed real SDK public member coverage is incomplete");

    std::map<std::string, std::size_t> raw;
#define LEAF_NATIVE_BOUNDARY(capability, function)                         \
    do {                                                                   \
        const auto status = invoke_null_boundary(&function);               \
        require(status != CODEX_AGENT_STATUS_OK,                           \
                "real SDK accepted a null leaf-service boundary");       \
        ++raw[capability];                                                  \
    } while (false);
#include "leaf_native_boundaries.inc"
#undef LEAF_NATIVE_BOUNDARY

    require(raw.size() == 42,
            "real SDK exact leaf reference coverage is incomplete");
    std::size_t raw_calls = 0;
    for (const auto& [capability, calls] : raw) {
        require(typed.contains(capability) && calls != 0,
                "raw exact reference lacks its typed production owner");
        raw_calls += calls;
    }
    require(raw_calls == 112,
            "real SDK exact leaf reference count is incomplete");

    const auto receipt = std::filesystem::path(argv[1]);
    std::filesystem::create_directories(receipt.parent_path());
    std::ofstream output(receipt, std::ios::binary | std::ios::trunc);
    require(output.good(), "cannot create real SDK leaf boundary receipt");
    output << "executedTestId\tboundary\tstatus\n";
    for (const auto& [id, calls] : raw) {
        (void)calls;
        output << id
               << "\ttyped-public-default-invalid+raw-exact-real-sdk-null-boundary\tpassed\n";
    }
    require(output.good(), "cannot write real SDK leaf boundary receipt");
}
