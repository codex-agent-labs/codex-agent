#include <codex_agent/codex_agent.hpp>

#include "leaf_native_probe.hpp"

#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#include <vector>

#define LEAF_NATIVE_BOUNDARY(capability, function)                          \
    static_assert(std::is_pointer_v<decltype(&function)>);
#include "leaf_native_boundaries.inc"
#undef LEAF_NATIVE_BOUNDARY

namespace leaf_signatures {
using Authentication = codex_agent::Authentication;
using Connectors = codex_agent::Connectors;
using Hooks = codex_agent::Hooks;
using IntegrationAuthorization = codex_agent::IntegrationAuthorization;
using Interactions = codex_agent::Interactions;
using McpServers = codex_agent::McpServers;
using Models = codex_agent::Models;
using Plugins = codex_agent::Plugins;
using Skills = codex_agent::Skills;
using Boolean = bool;
using Integer64 = std::int64_t;
using String = std::string;
using ApiKeyAuthentication = codex_agent::ApiKeyAuthentication;
using BrowserAuthentication = codex_agent::ChatGptBrowserAuthentication;
using DeviceAuthentication = codex_agent::ChatGptDeviceCodeAuthentication;
using ApprovalDecision = codex_agent::ApprovalDecision;
using ElicitationResponse = codex_agent::ElicitationResponse;
using Hook = codex_agent::Hook;
using InstallationScope = codex_agent::InstallationScope;
using Integration = codex_agent::IntegrationValue;
using McpServer = codex_agent::McpServer;
using McpServerConfiguration = codex_agent::McpServerConfiguration;
using Model = codex_agent::Model;
using PendingApproval = codex_agent::PendingApproval;
using PendingElicitation = codex_agent::PendingElicitation;
using PluginReference = codex_agent::PluginReference;
using Resolution = codex_agent::Resolution;
using Skill = codex_agent::Skill;
using VoidOperation = codex_agent::AsyncOperation<void>;
using ConnectorListOperation =
    codex_agent::AsyncOperation<std::vector<codex_agent::Connector>>;
using HookOperation = codex_agent::AsyncOperation<codex_agent::Hook>;
using HookCatalogOperation =
    codex_agent::AsyncOperation<codex_agent::HookCatalog>;
using McpServerOperation = codex_agent::AsyncOperation<codex_agent::McpServer>;
using McpServerListOperation =
    codex_agent::AsyncOperation<std::vector<codex_agent::McpServer>>;
using ModelListOperation =
    codex_agent::AsyncOperation<std::vector<codex_agent::Model>>;
using ModelOperation = codex_agent::AsyncOperation<codex_agent::Model>;
using StringOperation = codex_agent::AsyncOperation<std::string>;
using ServiceTierOperation =
    codex_agent::AsyncOperation<std::optional<codex_agent::ServiceTier>>;
using PluginInstallOperation =
    codex_agent::AsyncOperation<codex_agent::PluginInstallResult>;
using PluginCatalogOperation =
    codex_agent::AsyncOperation<codex_agent::PluginCatalog>;
using PluginDetailOperation =
    codex_agent::AsyncOperation<codex_agent::PluginDetail>;
using SkillOperation = codex_agent::AsyncOperation<codex_agent::Skill>;
using SkillCatalogOperation =
    codex_agent::AsyncOperation<codex_agent::SkillCatalog>;
using SkillChunkOperation =
    codex_agent::AsyncOperation<codex_agent::SkillChunk>;
using AuthenticationValue = codex_agent::AuthenticationState;
using AuthenticationCallback = std::function<void(
    codex_agent::StateEvent<codex_agent::AuthenticationState>)>;
using AuthenticationSubscription =
    codex_agent::StateSubscription<codex_agent::AuthenticationState>;
using BooleanCallback =
    std::function<void(codex_agent::StateEvent<bool>)>;
using BooleanSubscription = codex_agent::StateSubscription<bool>;
using OptionalIntegration = std::optional<codex_agent::IntegrationValue>;
using OptionalIntegrationCallback = std::function<void(
    codex_agent::StateEvent<std::optional<codex_agent::IntegrationValue>>)>;
using OptionalIntegrationSubscription = codex_agent::StateSubscription<
    std::optional<codex_agent::IntegrationValue>>;
using IntegrationAuthorizationState =
    codex_agent::IntegrationAuthorizationState;
using IntegrationAuthorizationCallback = std::function<void(
    codex_agent::StateEvent<codex_agent::IntegrationAuthorizationState>)>;
using IntegrationAuthorizationSubscription = codex_agent::StateSubscription<
    codex_agent::IntegrationAuthorizationState>;
using ApprovalList = std::vector<codex_agent::PendingApproval>;
using ApprovalCallback =
    std::function<void(codex_agent::StateEvent<ApprovalList>)>;
using ApprovalSubscription = codex_agent::StateSubscription<ApprovalList>;
using ElicitationList = std::vector<codex_agent::PendingElicitation>;
using ElicitationCallback =
    std::function<void(codex_agent::StateEvent<ElicitationList>)>;
using ElicitationSubscription =
    codex_agent::StateSubscription<ElicitationList>;
using InteractionState = codex_agent::InteractionState;
using InteractionCallback =
    std::function<void(codex_agent::StateEvent<InteractionState>)>;
using InteractionSubscription =
    codex_agent::StateSubscription<InteractionState>;

template <typename Owner, typename Return, typename... Arguments>
using ConstMember = Return (Owner::*)(Arguments...) const;
template <typename Signature, Signature Member>
inline constexpr bool exact_member = true;
#define LEAF_PUBLIC_SIGNATURE(id, owner, result, member, ...)               \
    static_assert(exact_member<                                             \
                  ConstMember<owner, result __VA_OPT__(,) __VA_ARGS__>,     \
                  static_cast<ConstMember<                                  \
                      owner, result __VA_OPT__(,) __VA_ARGS__>>(            \
                      &owner::member)>);
#include "leaf_public_signatures.inc"
#undef LEAF_PUBLIC_SIGNATURE
}  // namespace leaf_signatures

namespace {

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
};

LeafServices leaf_services(const codex_agent::Agent& agent) {
    return {
        agent.authentication(), agent.interactions(),
        agent.integration_authorization(), agent.models(), agent.skills(),
        agent.hooks(), agent.plugins(), agent.connectors(), agent.mcp_servers(),
    };
}
void require(bool condition, const std::string& message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::abort();
    }
}

extern "C" void codex_agent_cpp_mock_leaf_delay_next_operation();
extern "C" void codex_agent_cpp_mock_leaf_complete_pending_operation();
extern "C" void codex_agent_cpp_mock_leaf_publish_state(int, int);
extern "C" void codex_agent_cpp_mock_leaf_set_current_state(int, int);

bool edge_seen_since(LeafNativeEdge edge, std::size_t start) {
    for (auto index = start; index < codex_agent_cpp_mock_leaf_event_count();
         ++index) {
        if (codex_agent_cpp_mock_leaf_event_at(index) == edge) return true;
    }
    return false;
}

bool exact_edges_advanced(
    std::string_view capability, std::size_t before,
    std::string* missing = nullptr) {
    bool matched = false;
    bool complete = true;
#define LEAF_NATIVE_BOUNDARY(expected_capability, function)                 \
    if (capability == expected_capability) {                                \
        matched = true;                                                     \
        if (!edge_seen_since(LeafNativeEdge::function, before)) {           \
            complete = false;                                               \
            if (missing != nullptr) *missing = "typed native edge";        \
        }                                                                   \
    }
#include "leaf_native_boundaries.inc"
#undef LEAF_NATIVE_BOUNDARY
    return matched && complete;
}

const std::map<std::string, std::string>& exact_scenarios() {
    static const std::map<std::string, std::string> result{
#define LEAF_SCENARIO(capability, scenario) {capability, scenario},
#include "leaf_scenarios.inc"
#undef LEAF_SCENARIO
    };
    return result;
}

class CapabilityProof final {
public:
    CapabilityProof(std::string id, std::map<std::string, std::string>& passed)
        : id_(std::move(id)), passed_(passed),
          before_(codex_agent_cpp_mock_leaf_event_count()) {}

    void pass() {
        std::string missing;
        require(exact_edges_advanced(id_, before_, &missing),
                id_ + " did not execute exact production C call " + missing);
        require(passed_.emplace(id_, exact_scenarios().at(id_)).second,
                "duplicate leaf capability execution " + id_);
    }

    std::size_t before() const noexcept { return before_; }

private:
    std::string id_;
    std::map<std::string, std::string>& passed_;
    std::size_t before_;
};

template <typename Get>
void require_cancelled(Get&& get) {
    try {
        get();
    } catch (const codex_agent::OperationError& error) {
        require(error.status() == codex_agent::Status::cancelled,
                "cancelled operation reported the wrong status");
        require(!error.failure(),
                "cancelled operation reported a fabricated failure");
        return;
    }
    require(false, "cancelled operation completed successfully");
}

template <typename Start, typename Verify>
void async_value(Start&& start, Verify&& verify) {
    auto operation = start();
    verify(operation.get());
    const auto cancellation_start = codex_agent_cpp_mock_leaf_event_count();
    codex_agent_cpp_mock_leaf_delay_next_operation();
    auto cancellable = start();
    cancellable.cancel();
    require(edge_seen_since(
                LeafNativeEdge::codex_agent_operation_cancel,
                cancellation_start),
            "async projection did not execute native cancellation");
    codex_agent_cpp_mock_leaf_complete_pending_operation();
    require_cancelled([&] { (void)cancellable.get(); });
}

template <typename Start>
void async_void(Start&& start) {
    auto operation = start();
    operation.get();
    const auto cancellation_start = codex_agent_cpp_mock_leaf_event_count();
    codex_agent_cpp_mock_leaf_delay_next_operation();
    auto cancellable = start();
    cancellable.cancel();
    require(edge_seen_since(
                LeafNativeEdge::codex_agent_operation_cancel,
                cancellation_start),
            "async projection did not execute native cancellation");
    codex_agent_cpp_mock_leaf_complete_pending_operation();
    require_cancelled([&] { cancellable.get(); });
}

template <typename Value, typename Current, typename Subscribe,
          typename Initial, typename Changed>
void state_flow(
    int kind, Current&& current, Subscribe&& subscribe,
    Initial&& initial, Changed&& changed) {
    initial(current());
    std::size_t events = 0;
    auto subscription = subscribe([&](codex_agent::StateEvent<Value> event) {
        if (events == 0) {
            require(event.status == codex_agent::Status::ok && event.value &&
                        !event.terminal,
                    "state projection did not emit its current value");
            initial(*event.value);
        } else if (events == 1) {
            require(event.status == codex_agent::Status::ok && event.value &&
                        !event.terminal,
                    "state projection did not emit its subsequent value");
            changed(*event.value);
        } else if (events == 2) {
            require(event.status == codex_agent::Status::ok && !event.value &&
                        event.terminal,
                    "state projection did not emit its terminal event");
        } else {
            require(false, "state projection emitted after terminal/close");
        }
        ++events;
    });
    require(events == 1, "state subscription missed current value");
    codex_agent_cpp_mock_leaf_publish_state(kind, 0);
    require(events == 2, "state subscription missed subsequent value");
    codex_agent_cpp_mock_leaf_publish_state(kind, 1);
    require(events == 3, "state subscription missed terminal event");
    subscription.close();
    subscription.close();
    codex_agent_cpp_mock_leaf_publish_state(kind, 0);
    require(events == 3, "closed state subscription was not quiescent");
}

template <typename Action>
void require_invalid(Action&& action, const char* label) {
    try {
        action();
    } catch (const std::invalid_argument&) {
        return;
    }
    require(false, std::string(label) + " accepted an unowned value");
}

template <typename Action>
void require_native_invalid(Action&& action, const char* label) {
    try {
        action();
    } catch (const codex_agent::Error& error) {
        require(error.status() == codex_agent::Status::invalid_argument,
                std::string(label) + " reported the wrong input error");
        return;
    }
    require(false, std::string(label) + " bypassed native input validation");
}
}  // namespace

int main(int argc, char** argv) {
    require(argc == 2, "usage: leaf_behavior_test EXECUTED_RECEIPT");
    std::map<std::string, std::string> passed;
    auto leaf = [] {
        auto host = codex_agent::Host::create({
            "/bundle", "/data", {"cpp-test", "C++ Test", "1"}});
        auto agent = host.agent();
        return leaf_services(agent);
    }();

    {
        CapabilityProof proof("cpp.leaf:000", passed);
        const auto wrong_method = codex_agent_cpp_mock_leaf_event_count();
        require_native_invalid(
            [&] {
                (void)leaf.authentication.authenticate(
                    codex_agent::ApiKeyAuthentication("wrong"));
            },
            "authenticate API key");
        async_void([&] {
            return leaf.authentication.authenticate(
                codex_agent::ApiKeyAuthentication("key"));
        });
        leaf.authentication.authenticate(
            codex_agent::chat_gpt_browser_authentication).get();
        leaf.authentication.authenticate(
            codex_agent::chat_gpt_device_code_authentication).get();
        require(!edge_seen_since(
                    LeafNativeEdge::codex_agent_authentication_cancel,
                    wrong_method),
                "authenticate executed the wrong public native method");
        require(!exact_edges_advanced("cpp.leaf:001", proof.before()),
                "wrong capability/native-call pairing was accepted");
        require(!exact_scenarios().contains("cpp.leaf:999"),
                "stale self-reported behavior trace was accepted");
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:001", passed);
        async_void([&] { return leaf.authentication.cancel(); });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:002", passed);
        async_void([&] { return leaf.authentication.sign_out(); });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:003", passed);
        state_flow<bool>(
            1, [&] { return leaf.authentication.is_authenticated(); },
            [&](auto callback) {
                return leaf.authentication.subscribe_is_authenticated(
                    std::move(callback));
            },
            [](bool value) { require(value, "authenticated current mismatch"); },
            [](bool value) { require(!value, "authenticated change mismatch"); });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:004", passed);
        state_flow<bool>(
            2, [&] { return leaf.authentication.is_authenticating(); },
            [&](auto callback) {
                return leaf.authentication.subscribe_is_authenticating(
                    std::move(callback));
            },
            [](bool value) { require(!value, "authenticating current mismatch"); },
            [](bool value) { require(value, "authenticating change mismatch"); });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:005", passed);
        state_flow<codex_agent::AuthenticationState>(
            0, [&] { return leaf.authentication.state(); },
            [&](auto callback) {
                return leaf.authentication.subscribe_state(std::move(callback));
            },
            [](const auto& value) {
                require(value.status ==
                            codex_agent::AuthenticationStatus::authenticated,
                        "authentication current state mismatch");
                require(value.pending_sign_in_url &&
                            value.pending_sign_in_url->value ==
                                "https://sign-in.example" &&
                            value.device_verification_url &&
                            value.device_verification_url->value ==
                                "https://verify.example" &&
                            value.device_user_code == "ABCD-EFGH" &&
                            value.failure &&
                            value.failure->code == "fixture_failure",
                        "authentication present optionals mismatch");
            },
            [](const auto& value) {
                require(value.status ==
                            codex_agent::AuthenticationStatus::signed_out,
                        "authentication changed state mismatch");
                require(!value.pending_sign_in_url &&
                            !value.device_verification_url &&
                            !value.device_user_code && !value.failure,
                        "authentication absent optionals mismatch");
            });
        proof.pass();
    }

    const codex_agent::Connector connector{
        "connector", "Connector", "description", std::nullopt, true, true, {}};
    {
        CapabilityProof proof("cpp.leaf:006", passed);
        require_native_invalid(
            [&] { (void)leaf.connectors.list(false); },
            "connector force reload");
        async_value(
            [&] { return leaf.connectors.list(true); },
            [](const auto& values) {
                require(values.size() == 2 && values[0].id == "connector" &&
                            values[1].id == "connector",
                        "connector ordering/duplicates mismatch");
            });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:007", passed);
        require(leaf.connectors.is_available(), "connector unavailable");
        proof.pass();
    }

    const codex_agent::Hook hook{
        "hook", "after-turn", std::nullopt, codex_agent::hook_handler_agent,
        1, codex_agent::HookTrustStatus::trusted, "hash", true, "user",
        "/hook", codex_agent::ResourceOrigin::user, std::nullopt, false, true,
        true, std::nullopt};
    {
        CapabilityProof proof("cpp.leaf:008", passed);
        require_native_invalid(
            [&] {
                (void)leaf.hooks.install(
                    "/wrong", codex_agent::InstallationScope::user);
            },
            "hook install path");
        require_native_invalid(
            [&] {
                (void)leaf.hooks.install(
                    "/hook", codex_agent::InstallationScope::workspace);
            },
            "hook install scope");
        async_value(
            [&] {
                return leaf.hooks.install(
                    "/hook", codex_agent::InstallationScope::user);
            },
            [](const auto& value) {
                require(value.key == "hook", "hook install result mismatch");
            });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:009", passed);
        async_value([&] { return leaf.hooks.list(); }, [](const auto& value) {
            require(value.hooks.empty(), "hook catalog mismatch");
        });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:010", passed);
        auto wrong_hook = hook;
        wrong_hook.key = "wrong";
        require_native_invalid(
            [&] { (void)leaf.hooks.trust(wrong_hook); }, "hook trust");
        async_void([&] { return leaf.hooks.trust(hook); });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:011", passed);
        auto wrong_hook = hook;
        wrong_hook.source_path = "/wrong";
        require_native_invalid(
            [&] { (void)leaf.hooks.uninstall(wrong_hook); },
            "hook uninstall");
        async_void([&] { return leaf.hooks.uninstall(hook); });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:012", passed);
        require(leaf.hooks.is_available(), "hooks unavailable");
        proof.pass();
    }

    const codex_agent::ConnectorIntegration connector_integration{
        {"connector:connector", "Connector"}, connector};
    const codex_agent::McpServer mcp_server{
        "server", "Server", codex_agent::McpAuthStatus::unknown};
    const codex_agent::McpServerIntegration mcp_integration{
        {"mcp:server", "Server"}, mcp_server};
    {
        CapabilityProof proof("cpp.leaf:013", passed);
        auto wrong_connector = connector_integration;
        wrong_connector.connector.id = "wrong";
        require_native_invalid(
            [&] {
                (void)leaf.integration_authorization.authorize(
                    wrong_connector);
            },
            "connector authorization");
        auto wrong_mcp = mcp_integration;
        wrong_mcp.server.name = "wrong";
        require_native_invalid(
            [&] {
                (void)leaf.integration_authorization.authorize(wrong_mcp);
            },
            "MCP authorization");
        async_void([&] {
            return leaf.integration_authorization.authorize(
                connector_integration);
        });
        leaf.integration_authorization.authorize(mcp_integration).get();
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:014", passed);
        async_void([&] { return leaf.integration_authorization.cancel(); });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:015", passed);
        using OptionalIntegration =
            std::optional<codex_agent::IntegrationValue>;
        state_flow<OptionalIntegration>(
            4, [&] { return leaf.integration_authorization.active(); },
            [&](auto callback) {
                return leaf.integration_authorization.subscribe_active(
                    std::move(callback));
            },
            [](const auto& value) {
                require(value && std::get<codex_agent::ConnectorIntegration>(
                                     *value).connector.id == "connector",
                        "active integration current mismatch");
            },
            [](const auto& value) {
                require(value &&
                            std::get<codex_agent::McpServerIntegration>(*value)
                                    .server.name == "server",
                        "active MCP integration transition mismatch");
            });
        codex_agent_cpp_mock_leaf_set_current_state(4, 2);
        require(!leaf.integration_authorization.active(),
                "active integration absent variant mismatch");
        codex_agent_cpp_mock_leaf_set_current_state(4, 0);
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:016", passed);
        state_flow<bool>(
            5,
            [&] {
                return leaf.integration_authorization.is_authorizing();
            },
            [&](auto callback) {
                return leaf.integration_authorization.subscribe_is_authorizing(
                    std::move(callback));
            },
            [](bool value) { require(!value, "authorizing current mismatch"); },
            [](bool value) { require(value, "authorizing change mismatch"); });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:017", passed);
        state_flow<codex_agent::IntegrationAuthorizationState>(
            3, [&] { return leaf.integration_authorization.state(); },
            [&](auto callback) {
                return leaf.integration_authorization.subscribe_state(
                    std::move(callback));
            },
            [](const auto& value) {
                require(value.status ==
                            codex_agent::IntegrationAuthorizationStatus::idle,
                        "integration state current mismatch");
                require(!value.target && !value.failure,
                        "integration state absent optionals mismatch");
            },
            [](const auto& value) {
                require(value.status == codex_agent::
                            IntegrationAuthorizationStatus::failed,
                        "integration state change mismatch");
                require(value.target &&
                            std::get<codex_agent::McpServerIntegration>(
                                *value.target).server.name == "server" &&
                            value.failure &&
                            value.failure->code == "fixture_failure",
                        "integration target/failure present mismatch");
            });
        proof.pass();
    }

    auto approvals = leaf.interactions.approvals();
    auto elicitations = leaf.interactions.elicitations();
    auto other_leaf = [] {
        auto host = codex_agent::Host::create({
            "/bundle", "/data", {"cpp-other", "C++ Other", "1"}});
        auto agent = host.agent();
        return leaf_services(agent);
    }();
    auto other_approvals = other_leaf.interactions.approvals();
    auto other_elicitations = other_leaf.interactions.elicitations();
    require(approvals.size() == 1 && elicitations.size() == 1,
            "interaction input fixture mismatch");
    {
        CapabilityProof proof("cpp.leaf:018", passed);
        auto unowned = elicitations.front();
        unowned._native_identity.reset();
        require_invalid(
            [&] { (void)leaf.interactions.open_url(unowned); }, "open_url");
        auto forged = elicitations.front();
        forged._native_identity = approvals.front()._native_identity;
        require_invalid(
            [&] { (void)leaf.interactions.open_url(forged); },
            "forged open_url");
        require_invalid(
            [&] {
                (void)leaf.interactions.open_url(other_elicitations.front());
            },
            "cross-owner open_url");
        async_void(
            [&] { return leaf.interactions.open_url(elicitations.front()); });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:019", passed);
        auto unowned = approvals.front();
        unowned._native_identity.reset();
        require_invalid(
            [&] {
                (void)leaf.interactions.resolve(
                    unowned, codex_agent::ApprovalDecision::accept);
            },
            "resolve approval");
        require_invalid(
            [&] {
                (void)leaf.interactions.resolve(
                    other_approvals.front(),
                    codex_agent::ApprovalDecision::accept);
            },
            "cross-owner resolve approval");
        require_native_invalid(
            [&] {
                (void)leaf.interactions.resolve(
                    approvals.front(), codex_agent::ApprovalDecision::decline);
            },
            "approval decision");
        async_void([&] {
            return leaf.interactions.resolve(
                approvals.front(), codex_agent::ApprovalDecision::accept);
        });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:020", passed);
        auto unowned = elicitations.front();
        unowned._native_identity.reset();
        require_invalid(
            [&] {
                (void)leaf.interactions.resolve(
                    unowned, codex_agent::ElicitationResponse{
                                 codex_agent::ElicitationAction::decline, {}});
            },
            "resolve elicitation");
        require_invalid(
            [&] {
                (void)leaf.interactions.resolve(
                    other_elicitations.front(),
                    codex_agent::ElicitationResponse{
                        codex_agent::ElicitationAction::decline, {}});
            },
            "cross-owner resolve elicitation");
        require_native_invalid(
            [&] {
                (void)leaf.interactions.resolve(
                    elicitations.front(), codex_agent::ElicitationResponse{
                        codex_agent::ElicitationAction::cancel, {}});
            },
            "elicitation response");
        async_void([&] {
            return leaf.interactions.resolve(
                elicitations.front(), codex_agent::ElicitationResponse{
                                          codex_agent::ElicitationAction::decline,
                                          {}});
        });
        proof.pass();
    }
    {
        std::weak_ptr<codex_agent::detail::InteractionsHandle> owner =
            other_elicitations.front()._native_identity->owner;
        other_leaf.interactions = {};
        require(!owner.expired(),
                "pending interaction did not retain its parent service");
        other_approvals.clear();
        other_elicitations.clear();
        require(owner.expired(),
                "pending interaction leaked its parent service");
    }
    {
        CapabilityProof proof("cpp.leaf:021", passed);
        state_flow<std::vector<codex_agent::PendingApproval>>(
            7, [&] { return leaf.interactions.approvals(); },
            [&](auto callback) {
                return leaf.interactions.subscribe_approvals(
                    std::move(callback));
            },
            [](const auto& value) {
                require(value.size() == 1 &&
                            value.front().request_id == "approval" &&
                            value.front()._native_identity,
                        "approval current/identity mismatch");
            },
            [](const auto& value) {
                require(value.size() == 2 &&
                            value[0].request_id == "approval" &&
                            value[1].request_id == "approval-2" &&
                            value[0]._native_identity &&
                            value[1]._native_identity &&
                            value[0]._native_identity != value[1]._native_identity,
                        "approval change/order/identity mismatch");
            });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:022", passed);
        state_flow<std::vector<codex_agent::PendingElicitation>>(
            8, [&] { return leaf.interactions.elicitations(); },
            [&](auto callback) {
                return leaf.interactions.subscribe_elicitations(
                    std::move(callback));
            },
            [](const auto& value) {
                require(value.size() == 1 &&
                            value.front().request_id == "elicitation" &&
                            value.front()._native_identity,
                        "elicitation current/identity mismatch");
            },
            [](const auto& value) {
                require(value.size() == 2 &&
                            value[0].request_id == "elicitation" &&
                            value[1].request_id == "elicitation-2" &&
                            value[0]._native_identity &&
                            value[1]._native_identity &&
                            value[0]._native_identity != value[1]._native_identity,
                        "elicitation change/order/identity mismatch");
            });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:023", passed);
        state_flow<codex_agent::InteractionState>(
            6, [&] { return leaf.interactions.state(); },
            [&](auto callback) {
                return leaf.interactions.subscribe_state(std::move(callback));
            },
            [](const auto& value) {
                require(value.pending.empty(),
                        "interaction current state mismatch");
            },
            [](const auto& value) {
                require(value.pending.size() == 1 &&
                            std::get<codex_agent::PendingApproval>(
                                value.pending.front()).request_id == "approval",
                        "interaction changed state/order mismatch");
            });
        proof.pass();
    }

    const codex_agent::McpServerConfiguration configuration(
        "server", codex_agent::McpHttpTransport("https://example.com"));
    {
        CapabilityProof proof("cpp.leaf:024", passed);
        const codex_agent::McpServerConfiguration wrong_configuration(
            "wrong", codex_agent::McpHttpTransport("https://wrong.example"));
        require_native_invalid(
            [&] { (void)leaf.mcp_servers.add(wrong_configuration); },
            "MCP add");
        async_value(
            [&] { return leaf.mcp_servers.add(configuration); },
            [](const auto& value) {
                require(value.name == "server", "MCP add result mismatch");
            });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:025", passed);
        async_value([&] { return leaf.mcp_servers.list(); }, [](const auto& value) {
            require(value.size() == 2 && value[0].name == "server" &&
                        value[1].name == "server",
                    "MCP list order/duplicates mismatch");
        });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:026", passed);
        auto wrong_server = mcp_server;
        wrong_server.name = "wrong";
        require_native_invalid(
            [&] { (void)leaf.mcp_servers.remove(wrong_server); },
            "MCP remove");
        async_void([&] { return leaf.mcp_servers.remove(mcp_server); });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:027", passed);
        require(leaf.mcp_servers.is_available(), "MCP unavailable");
        proof.pass();
    }

    const codex_agent::Model model{
        "model", "Model", "description", {}, "medium", true, {}, std::nullopt};
    {
        CapabilityProof proof("cpp.leaf:028", passed);
        async_value([&] { return leaf.models.list(); }, [](const auto& value) {
            require(value.size() == 2 && value[0].id == "model" &&
                        value[1].id == "model",
                    "model list order/duplicates mismatch");
        });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:029", passed);
        auto wrong_model = model;
        wrong_model.id = "wrong";
        require_native_invalid(
            [&] { (void)leaf.models.resolve_effort(wrong_model); },
            "model effort");
        require_native_invalid(
            [&] {
                (void)leaf.models.resolve_effort(
                    model, codex_agent::Resolution::first);
            },
            "model effort resolution");
        async_value(
            [&] { return leaf.models.resolve_effort(model); },
            [](const auto& value) {
                require(value == "medium", "model effort mismatch");
            });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:030", passed);
        auto wrong_model = model;
        wrong_model.default_effort = "wrong";
        require_native_invalid(
            [&] { (void)leaf.models.resolve_service_tier(wrong_model); },
            "service tier model");
        require_native_invalid(
            [&] {
                (void)leaf.models.resolve_service_tier(
                    model, codex_agent::Resolution::default_);
            },
            "service tier resolution");
        async_value(
            [&] { return leaf.models.resolve_service_tier(model); },
            [](const auto& value) {
                require(value && value->id == "fast",
                        "present service tier mismatch");
            });
        require(!leaf.models.resolve_service_tier(
                    model, codex_agent::Resolution::first).get(),
                "absent service tier mismatch");
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:031", passed);
        require_native_invalid(
            [&] {
                (void)leaf.models.resolve(codex_agent::Resolution::first);
            },
            "model resolution");
        async_value([&] { return leaf.models.resolve(); }, [](const auto& value) {
            require(value.id == "model", "model resolve mismatch");
        });
        proof.pass();
    }

    const codex_agent::PluginReference plugin{
        "plugin", "plugin", "market", std::nullopt, std::nullopt};
    {
        CapabilityProof proof("cpp.leaf:032", passed);
        auto wrong_plugin = plugin;
        wrong_plugin.id = "wrong";
        require_native_invalid(
            [&] { (void)leaf.plugins.install(wrong_plugin); },
            "plugin install");
        async_value([&] { return leaf.plugins.install(plugin); }, [](const auto& value) {
            require(value.connectors_needing_authentication.empty(),
                    "plugin install result mismatch");
        });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:033", passed);
        require_native_invalid(
            [&] { (void)leaf.plugins.list(false); },
            "plugin force reload");
        async_value([&] { return leaf.plugins.list(true); }, [](const auto& value) {
            require(value.plugins.empty(), "plugin catalog mismatch");
        });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:034", passed);
        auto wrong_plugin = plugin;
        wrong_plugin.marketplace_name = "wrong";
        require_native_invalid(
            [&] { (void)leaf.plugins.read(wrong_plugin); }, "plugin read");
        async_value([&] { return leaf.plugins.read(plugin); }, [](const auto& value) {
            require(value.summary.reference.id == "plugin",
                    "plugin detail mismatch");
        });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:035", passed);
        auto wrong_plugin = plugin;
        wrong_plugin.name = "wrong";
        require_native_invalid(
            [&] { (void)leaf.plugins.uninstall(wrong_plugin); },
            "plugin uninstall");
        async_void([&] { return leaf.plugins.uninstall(plugin); });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:036", passed);
        require(leaf.plugins.is_available(), "plugins unavailable");
        proof.pass();
    }

    const codex_agent::Skill skill(
        "skill", "Skill", "description", "/skill",
        codex_agent::SkillScope::user, true);
    {
        CapabilityProof proof("cpp.leaf:037", passed);
        require_native_invalid(
            [&] {
                (void)leaf.skills.install(
                    "/wrong", codex_agent::InstallationScope::user);
            },
            "skill install path");
        require_native_invalid(
            [&] {
                (void)leaf.skills.install(
                    "/skill", codex_agent::InstallationScope::workspace);
            },
            "skill install scope");
        async_value(
            [&] {
                return leaf.skills.install(
                    "/skill", codex_agent::InstallationScope::user);
            },
            [](const auto& value) {
                require(value.name == "skill", "skill install result mismatch");
            });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:038", passed);
        require_native_invalid(
            [&] { (void)leaf.skills.list(false); },
            "skill force reload");
        async_value([&] { return leaf.skills.list(true); }, [](const auto& value) {
            require(value.skills.empty(), "skill catalog mismatch");
        });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:039", passed);
        require_native_invalid(
            [&] { (void)leaf.skills.read("/wrong", 7); },
            "skill read path");
        require_native_invalid(
            [&] { (void)leaf.skills.read("/skill", 8); },
            "skill read offset");
        async_value(
            [&] { return leaf.skills.read("/skill", 7); },
            [](const auto& value) {
                require(value.content == "chunk", "skill chunk mismatch");
            });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:040", passed);
        auto wrong_skill = skill;
        wrong_skill.name = "wrong";
        require_native_invalid(
            [&] { (void)leaf.skills.uninstall(wrong_skill); },
            "skill uninstall");
        async_void([&] { return leaf.skills.uninstall(skill); });
        proof.pass();
    }
    {
        CapabilityProof proof("cpp.leaf:041", passed);
        require(leaf.skills.is_available(), "skills unavailable");
        proof.pass();
    }

    require(passed == exact_scenarios(),
            "leaf capability behavior/scenario execution is incomplete");
    const auto receipt = std::filesystem::path(argv[1]);
    std::filesystem::create_directories(receipt.parent_path());
    std::ofstream output(receipt, std::ios::binary | std::ios::trunc);
    require(output.good(), "cannot create leaf behavior receipt");
    output << "executedTestId\tscenarios\tstatus\n";
    for (const auto& [id, scenarios] : passed) {
        output << id << '\t' << scenarios << "\tpassed\n";
    }
    require(output.good(), "cannot write leaf behavior receipt");
}
