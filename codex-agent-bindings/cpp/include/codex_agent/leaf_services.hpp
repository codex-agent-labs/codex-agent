#pragma once

// Included by codex_agent.hpp after the canonical value and lifecycle types.

namespace codex_agent {

class Authentication;
class Interactions;
class IntegrationAuthorization;
class Models;
class Skills;
class Hooks;
class Plugins;
class Connectors;
class McpServers;

namespace detail {

using AuthenticationHandle = OwnedHandle<
    codex_agent_authentication_t, codex_agent_authentication_release>;
using InteractionsHandle = OwnedHandle<
    codex_agent_interactions_t, codex_agent_interactions_release>;
using IntegrationAuthorizationHandle = OwnedHandle<
    codex_agent_integration_authorization_t,
    codex_agent_integration_authorization_release>;
using ModelsHandle = OwnedHandle<codex_agent_models_t, codex_agent_models_release>;
using SkillsHandle = OwnedHandle<codex_agent_skills_t, codex_agent_skills_release>;
using HooksHandle = OwnedHandle<codex_agent_hooks_t, codex_agent_hooks_release>;
using PluginsHandle = OwnedHandle<codex_agent_plugins_t, codex_agent_plugins_release>;
using ConnectorsHandle = OwnedHandle<
    codex_agent_connectors_t, codex_agent_connectors_release>;
using McpServersHandle = OwnedHandle<
    codex_agent_mcp_servers_t, codex_agent_mcp_servers_release>;

using ModelHandle = SyncHandle<codex_agent_model_t, codex_agent_model_destroy>;
using ServiceTierHandle = SyncHandle<
    codex_agent_service_tier_t, codex_agent_service_tier_destroy>;
using SkillHandle = SyncHandle<codex_agent_skill_t, codex_agent_skill_destroy>;
using SkillCatalogHandle = SyncHandle<
    codex_agent_skill_catalog_t, codex_agent_skill_catalog_destroy>;
using SkillChunkHandle = SyncHandle<
    codex_agent_skill_chunk_t, codex_agent_skill_chunk_destroy>;
using HookHandle = SyncHandle<codex_agent_hook_t, codex_agent_hook_destroy>;
using HookCatalogHandle = SyncHandle<
    codex_agent_hook_catalog_t, codex_agent_hook_catalog_destroy>;
using PluginReferenceHandle = SyncHandle<
    codex_agent_plugin_reference_t, codex_agent_plugin_reference_destroy>;
using PluginCatalogHandle = SyncHandle<
    codex_agent_plugin_catalog_t, codex_agent_plugin_catalog_destroy>;
using PluginDetailHandle = SyncHandle<
    codex_agent_plugin_detail_t, codex_agent_plugin_detail_destroy>;
using PluginInstallResultHandle = SyncHandle<
    codex_agent_plugin_install_result_t,
    codex_agent_plugin_install_result_destroy>;
using ConnectorHandle = SyncHandle<
    codex_agent_connector_t, codex_agent_connector_destroy>;
using McpServerHandle = SyncHandle<
    codex_agent_mcp_server_t, codex_agent_mcp_server_destroy>;
using McpServerConfigurationHandle = SyncHandle<
    codex_agent_mcp_server_configuration_t,
    codex_agent_mcp_server_configuration_destroy>;
using AuthenticationStateHandle = SyncHandle<
    codex_agent_authentication_state_t,
    codex_agent_authentication_state_destroy>;
using IntegrationAuthorizationStateHandle = SyncHandle<
    codex_agent_integration_authorization_state_t,
    codex_agent_integration_authorization_state_destroy>;
using IntegrationHandle = SyncHandle<
    codex_agent_integration_t, codex_agent_integration_destroy>;
using IntegrationConnectorHandle = SyncHandle<
    codex_agent_integration_connector_t,
    codex_agent_integration_connector_destroy>;
using IntegrationMcpServerHandle = SyncHandle<
    codex_agent_integration_mcp_server_t,
    codex_agent_integration_mcp_server_destroy>;
using PluginSummaryHandle = SyncHandle<
    codex_agent_plugin_summary_t, codex_agent_plugin_summary_destroy>;
using PluginSkillHandle = SyncHandle<
    codex_agent_plugin_skill_t, codex_agent_plugin_skill_destroy>;
using HookHandlerHandle = SyncHandle<
    codex_agent_hook_handler_t, codex_agent_hook_handler_destroy>;
using InteractionStateHandle = SyncHandle<
    codex_agent_interaction_state_t, codex_agent_interaction_state_destroy>;
using ApiKeyAuthenticationHandle = SyncHandle<
    codex_agent_authentication_method_api_key_t,
    codex_agent_authentication_method_api_key_destroy>;
using BrowserAuthenticationHandle = SyncHandle<
    codex_agent_authentication_method_chat_gpt_browser_t,
    codex_agent_authentication_method_chat_gpt_browser_destroy>;
using DeviceAuthenticationHandle = SyncHandle<
    codex_agent_authentication_method_chat_gpt_device_code_t,
    codex_agent_authentication_method_chat_gpt_device_code_destroy>;

struct LivePending final {
    std::variant<
        std::shared_ptr<PendingApprovalHandle>,
        std::shared_ptr<PendingElicitationHandle>> value;
    std::shared_ptr<InteractionsHandle> owner;
};

template <typename Handle, auto Retain, auto Release>
std::shared_ptr<OwnedHandle<Handle, Release>> retain_leaf(
    const OwnedHandle<Handle, Release>& source) {
    if (source.get() == nullptr) {
        return std::make_shared<OwnedHandle<Handle, Release>>(
            source.context(), nullptr);
    }
    return retain_handle<Handle, Retain, Release>(source);
}

template <typename Handle>
void ensure_leaf_valid(const Handle& handle) {
    if (!handle || !handle.context() || handle.context_raw() == nullptr) {
        throw Error(Status::closed);
    }
}

template <typename Handle, auto Destroy, typename Read>
auto read_owned(Context context, Handle* raw, Read&& read) {
    SyncHandle<Handle, Destroy> owner(context, raw);
    return read(context, owner.get());
}

template <typename Handle, typename Get, typename Parse>
auto current_leaf(const Handle& handle, Get&& get, Parse&& parse) {
    ensure_leaf_valid(handle);
    codex_agent_snapshot_t* raw = nullptr;
    check(get(handle.context_raw(), handle.get(), &raw));
    Snapshot snapshot(handle.context(), raw);
    return parse(handle.context(), snapshot.get());
}

template <typename Value, typename Handle, auto Retain, auto Release,
          typename Subscribe, typename Parse>
StateSubscription<Value> subscribe_leaf(
    const Handle& handle,
    Subscribe&& subscribe,
    Parse&& parse,
    std::function<void(StateEvent<Value>)> callback) {
    ensure_leaf_valid(handle);
    auto owner = retain_leaf<typename std::remove_pointer_t<
        decltype(handle.get())>, Retain, Release>(handle);
    using Parser = std::function<Value(
        codex_agent_context_t*, codex_agent_snapshot_t*)>;
    Parser parser = [context = handle.context(), parse = std::forward<Parse>(parse)](
                        codex_agent_context_t*, codex_agent_snapshot_t* snapshot) {
        return parse(context, snapshot);
    };
    using State = SubscriptionState<Value, Parser>;
    auto state = std::make_shared<State>(
        handle.context(), owner, std::move(parser), std::move(callback));
    return detail_subscribe<Value>(
        state,
        [owner, subscribe = std::forward<Subscribe>(subscribe)](
            auto callback_fn, void* user_data, auto** out_subscription) {
            return subscribe(owner->context_raw(), owner->get(), callback_fn,
                             user_data, out_subscription);
        });
}

inline bool snapshot_boolean(
    const Context& context, codex_agent_snapshot_t* snapshot) {
    std::int32_t value = 0;
    check(codex_agent_state_boolean_value(context->raw, snapshot, &value));
    return value != 0;
}

inline std::vector<std::string> read_strings(
    std::size_t count,
    const std::function<codex_agent_status_t(
        std::size_t, std::uint8_t*, std::size_t, std::size_t*)>& copy) {
    std::vector<std::string> result;
    result.reserve(count);
    for (std::size_t index = 0; index < count; ++index) {
        result.push_back(copy_string(
            [&](std::uint8_t* buffer, std::size_t capacity,
                std::size_t* required) {
                return copy(index, buffer, capacity, required);
            }));
    }
    return result;
}

Model read_model(const Context&, codex_agent_model_t*);
ServiceTier read_service_tier(const Context&, codex_agent_service_tier_t*);
Skill read_skill(const Context&, codex_agent_skill_t*);
SkillCatalog read_skill_catalog(const Context&, codex_agent_skill_catalog_t*);
SkillChunk read_skill_chunk(const Context&, codex_agent_skill_chunk_t*);
Hook read_hook(const Context&, codex_agent_hook_t*);
HookCatalog read_hook_catalog(const Context&, codex_agent_hook_catalog_t*);
PluginReference read_plugin_reference(const Context&, codex_agent_plugin_reference_t*);
PluginSummary read_plugin_summary(const Context&, codex_agent_plugin_summary_t*);
PluginCatalog read_plugin_catalog(const Context&, codex_agent_plugin_catalog_t*);
PluginDetail read_plugin_detail(const Context&, codex_agent_plugin_detail_t*);
PluginInstallResult read_plugin_install_result(
    const Context&, codex_agent_plugin_install_result_t*);
Connector read_connector(const Context&, codex_agent_connector_t*);
McpServer read_mcp_server(const Context&, codex_agent_mcp_server_t*);
McpServerConfiguration read_mcp_configuration(
    const Context&, codex_agent_mcp_server_configuration_t*);
AuthenticationState read_authentication_state(
    const Context&, codex_agent_snapshot_t*);
IntegrationValue read_integration(const Context&, codex_agent_integration_t*);
IntegrationAuthorizationState read_integration_authorization_state(
    const Context&, codex_agent_snapshot_t*);
std::optional<IntegrationValue> read_active_integration(
    const Context&, codex_agent_snapshot_t*);
std::vector<PendingApproval> read_approvals(
    const Context&, codex_agent_snapshot_t*,
    const std::shared_ptr<InteractionsHandle>&);
std::vector<PendingElicitation> read_elicitations(
    const Context&, codex_agent_snapshot_t*,
    const std::shared_ptr<InteractionsHandle>&);
InteractionState read_interaction_state(
    const Context&, codex_agent_snapshot_t*,
    const std::shared_ptr<InteractionsHandle>&);

ModelHandle make_model(const Context&, const Model&);
SkillHandle make_skill(const Context&, const Skill&);
HookHandle make_hook(const Context&, const Hook&);
PluginReferenceHandle make_plugin_reference(const Context&, const PluginReference&);
McpServerHandle make_mcp_server(const Context&, const McpServer&);
McpServerConfigurationHandle make_mcp_configuration(
    const Context&, const McpServerConfiguration&);
IntegrationHandle make_integration(const Context&, const IntegrationValue&);

template <typename Service, auto Retain, auto Release, typename Handle,
          typename Initiate>
AsyncOperation<void> leaf_void_operation(
    const Handle& handle, Initiate&& initiate) {
    ensure_leaf_valid(handle);
    auto owner = retain_leaf<Service, Retain, Release>(handle);
    auto context = owner->context();
    return start_operation<void>(
        context,
        [context, owner, initiate = std::forward<Initiate>(initiate)](
            auto callback, void* user_data, auto** out_operation) mutable {
            return initiate(context, owner, callback, user_data, out_operation);
        },
        [owner](const Context&, codex_agent_operation_t*) {});
}

template <typename Value, typename Service, auto Retain, auto Release,
          typename Handle, typename Initiate, typename Extract>
AsyncOperation<Value> leaf_operation(
    const Handle& handle, Initiate&& initiate, Extract&& extract) {
    ensure_leaf_valid(handle);
    auto owner = retain_leaf<Service, Retain, Release>(handle);
    auto context = owner->context();
    return start_operation<Value>(
        context,
        [context, owner, initiate = std::forward<Initiate>(initiate)](
            auto callback, void* user_data, auto** out_operation) mutable {
            return initiate(context, owner, callback, user_data, out_operation);
        },
        [owner, extract = std::forward<Extract>(extract)](
            const Context& context, codex_agent_operation_t* operation) mutable {
            return extract(context, operation);
        });
}

template <typename Handle, typename Call>
bool leaf_available(const Handle& handle, Call call) {
    ensure_leaf_valid(handle);
    std::int32_t available = 0;
    check(call(handle.context_raw(), handle.get(), &available));
    return available != 0;
}

}  // namespace detail

class Authentication final {
public:
    Authentication() = default;
    Authentication(const Authentication&) = delete;
    Authentication& operator=(const Authentication&) = delete;
    Authentication(Authentication&&) noexcept = default;
    Authentication& operator=(Authentication&&) noexcept = default;

    AsyncOperation<void> authenticate(ApiKeyAuthentication method) const;
    AsyncOperation<void> authenticate(ChatGptBrowserAuthentication) const;
    AsyncOperation<void> authenticate(ChatGptDeviceCodeAuthentication) const;
    AsyncOperation<void> cancel() const;
    AsyncOperation<void> sign_out() const;
    [[nodiscard]] AuthenticationState state() const;
    StateSubscription<AuthenticationState> subscribe_state(
        std::function<void(StateEvent<AuthenticationState>)>) const;
    [[nodiscard]] bool is_authenticated() const;
    StateSubscription<bool> subscribe_is_authenticated(
        std::function<void(StateEvent<bool>)>) const;
    [[nodiscard]] bool is_authenticating() const;
    StateSubscription<bool> subscribe_is_authenticating(
        std::function<void(StateEvent<bool>)>) const;

private:
    friend class Agent;
    Authentication(
        std::shared_ptr<detail::AgentOwnership> owner,
        detail::AuthenticationHandle handle)
        : owner_(std::move(owner)), handle_(std::move(handle)) {}
    std::shared_ptr<detail::AgentOwnership> owner_;
    detail::AuthenticationHandle handle_;
};

class Models final {
public:
    Models() = default;
    Models(const Models&) = delete;
    Models& operator=(const Models&) = delete;
    Models(Models&&) noexcept = default;
    Models& operator=(Models&&) noexcept = default;

    AsyncOperation<std::vector<Model>> list() const;
    AsyncOperation<Model> resolve(Resolution = Resolution::preferred) const;
    AsyncOperation<std::string> resolve_effort(
        Model, Resolution = Resolution::preferred) const;
    AsyncOperation<std::optional<ServiceTier>> resolve_service_tier(
        Model, Resolution = Resolution::preferred) const;

private:
    friend class Agent;
    Models(
        std::shared_ptr<detail::AgentOwnership> owner,
        detail::ModelsHandle handle)
        : owner_(std::move(owner)), handle_(std::move(handle)) {}
    std::shared_ptr<detail::AgentOwnership> owner_;
    detail::ModelsHandle handle_;
};

class Skills final {
public:
    Skills() = default;
    Skills(const Skills&) = delete;
    Skills& operator=(const Skills&) = delete;
    Skills(Skills&&) noexcept = default;
    Skills& operator=(Skills&&) noexcept = default;

    AsyncOperation<SkillCatalog> list(bool force_reload = false) const;
    AsyncOperation<SkillChunk> read(std::string path, std::int64_t offset = 0) const;
    AsyncOperation<Skill> install(std::string directory, InstallationScope) const;
    AsyncOperation<void> uninstall(Skill) const;
    [[nodiscard]] bool is_available() const;

private:
    friend class Agent;
    Skills(
        std::shared_ptr<detail::AgentOwnership> owner,
        detail::SkillsHandle handle)
        : owner_(std::move(owner)), handle_(std::move(handle)) {}
    std::shared_ptr<detail::AgentOwnership> owner_;
    detail::SkillsHandle handle_;
};

class Hooks final {
public:
    Hooks() = default;
    Hooks(const Hooks&) = delete;
    Hooks& operator=(const Hooks&) = delete;
    Hooks(Hooks&&) noexcept = default;
    Hooks& operator=(Hooks&&) noexcept = default;

    AsyncOperation<HookCatalog> list() const;
    AsyncOperation<Hook> install(std::string directory, InstallationScope) const;
    AsyncOperation<void> uninstall(Hook) const;
    AsyncOperation<void> trust(Hook) const;
    [[nodiscard]] bool is_available() const;

private:
    friend class Agent;
    Hooks(
        std::shared_ptr<detail::AgentOwnership> owner,
        detail::HooksHandle handle)
        : owner_(std::move(owner)), handle_(std::move(handle)) {}
    std::shared_ptr<detail::AgentOwnership> owner_;
    detail::HooksHandle handle_;
};

class Plugins final {
public:
    Plugins() = default;
    Plugins(const Plugins&) = delete;
    Plugins& operator=(const Plugins&) = delete;
    Plugins(Plugins&&) noexcept = default;
    Plugins& operator=(Plugins&&) noexcept = default;

    AsyncOperation<PluginCatalog> list(bool force_reload = false) const;
    AsyncOperation<PluginDetail> read(PluginReference) const;
    AsyncOperation<PluginInstallResult> install(PluginReference) const;
    AsyncOperation<void> uninstall(PluginReference) const;
    [[nodiscard]] bool is_available() const;

private:
    friend class Agent;
    Plugins(
        std::shared_ptr<detail::AgentOwnership> owner,
        detail::PluginsHandle handle)
        : owner_(std::move(owner)), handle_(std::move(handle)) {}
    std::shared_ptr<detail::AgentOwnership> owner_;
    detail::PluginsHandle handle_;
};

class Connectors final {
public:
    Connectors() = default;
    Connectors(const Connectors&) = delete;
    Connectors& operator=(const Connectors&) = delete;
    Connectors(Connectors&&) noexcept = default;
    Connectors& operator=(Connectors&&) noexcept = default;

    AsyncOperation<std::vector<Connector>> list(bool force_reload = false) const;
    [[nodiscard]] bool is_available() const;

private:
    friend class Agent;
    Connectors(
        std::shared_ptr<detail::AgentOwnership> owner,
        detail::ConnectorsHandle handle)
        : owner_(std::move(owner)), handle_(std::move(handle)) {}
    std::shared_ptr<detail::AgentOwnership> owner_;
    detail::ConnectorsHandle handle_;
};

class McpServers final {
public:
    McpServers() = default;
    McpServers(const McpServers&) = delete;
    McpServers& operator=(const McpServers&) = delete;
    McpServers(McpServers&&) noexcept = default;
    McpServers& operator=(McpServers&&) noexcept = default;

    AsyncOperation<std::vector<McpServer>> list() const;
    AsyncOperation<McpServer> add(McpServerConfiguration) const;
    AsyncOperation<void> remove(McpServer) const;
    [[nodiscard]] bool is_available() const;

private:
    friend class Agent;
    McpServers(
        std::shared_ptr<detail::AgentOwnership> owner,
        detail::McpServersHandle handle)
        : owner_(std::move(owner)), handle_(std::move(handle)) {}
    std::shared_ptr<detail::AgentOwnership> owner_;
    detail::McpServersHandle handle_;
};

class IntegrationAuthorization final {
public:
    IntegrationAuthorization() = default;
    IntegrationAuthorization(const IntegrationAuthorization&) = delete;
    IntegrationAuthorization& operator=(const IntegrationAuthorization&) = delete;
    IntegrationAuthorization(IntegrationAuthorization&&) noexcept = default;
    IntegrationAuthorization& operator=(IntegrationAuthorization&&) noexcept = default;

    AsyncOperation<void> authorize(IntegrationValue) const;
    AsyncOperation<void> cancel() const;
    [[nodiscard]] IntegrationAuthorizationState state() const;
    StateSubscription<IntegrationAuthorizationState> subscribe_state(
        std::function<void(StateEvent<IntegrationAuthorizationState>)>) const;
    [[nodiscard]] std::optional<IntegrationValue> active() const;
    StateSubscription<std::optional<IntegrationValue>> subscribe_active(
        std::function<void(StateEvent<std::optional<IntegrationValue>>)>) const;
    [[nodiscard]] bool is_authorizing() const;
    StateSubscription<bool> subscribe_is_authorizing(
        std::function<void(StateEvent<bool>)>) const;

private:
    friend class Agent;
    IntegrationAuthorization(
        std::shared_ptr<detail::AgentOwnership> owner,
        detail::IntegrationAuthorizationHandle handle)
        : owner_(std::move(owner)), handle_(std::move(handle)) {}
    std::shared_ptr<detail::AgentOwnership> owner_;
    detail::IntegrationAuthorizationHandle handle_;
};

class Interactions final {
public:
    Interactions() = default;
    Interactions(const Interactions&) = delete;
    Interactions& operator=(const Interactions&) = delete;
    Interactions(Interactions&&) noexcept = default;
    Interactions& operator=(Interactions&&) noexcept = default;

    AsyncOperation<void> open_url(PendingElicitation) const;
    AsyncOperation<void> resolve(PendingApproval, ApprovalDecision) const;
    AsyncOperation<void> resolve(PendingElicitation, ElicitationResponse) const;
    [[nodiscard]] InteractionState state() const;
    StateSubscription<InteractionState> subscribe_state(
        std::function<void(StateEvent<InteractionState>)>) const;
    [[nodiscard]] std::vector<PendingApproval> approvals() const;
    StateSubscription<std::vector<PendingApproval>> subscribe_approvals(
        std::function<void(StateEvent<std::vector<PendingApproval>>)>) const;
    [[nodiscard]] std::vector<PendingElicitation> elicitations() const;
    StateSubscription<std::vector<PendingElicitation>> subscribe_elicitations(
        std::function<void(StateEvent<std::vector<PendingElicitation>>)>) const;

private:
    friend class Agent;
    Interactions(
        std::shared_ptr<detail::AgentOwnership> owner,
        detail::InteractionsHandle handle)
        : owner_(std::move(owner)),
          handle_(std::make_shared<detail::InteractionsHandle>(
              std::move(handle))) {}
    std::shared_ptr<detail::AgentOwnership> owner_;
    std::shared_ptr<detail::InteractionsHandle> handle_ =
        std::make_shared<detail::InteractionsHandle>();
};

inline Authentication Agent::authentication() const {
    ensure_valid();
    auto owner = detail::retain_agent_ownership(owner_);
    codex_agent_authentication_t* raw = nullptr;
    detail::check(codex_agent_agent_authentication(
        owner->agent->context_raw(), owner->agent->get(), &raw));
    return Authentication(
        owner, detail::AuthenticationHandle(owner->agent->context(), raw));
}

inline Connectors Agent::connectors() const {
    ensure_valid();
    auto owner = detail::retain_agent_ownership(owner_);
    codex_agent_connectors_t* raw = nullptr;
    detail::check(codex_agent_agent_connectors(
        owner->agent->context_raw(), owner->agent->get(), &raw));
    return Connectors(
        owner, detail::ConnectorsHandle(owner->agent->context(), raw));
}

inline Hooks Agent::hooks() const {
    ensure_valid();
    auto owner = detail::retain_agent_ownership(owner_);
    codex_agent_hooks_t* raw = nullptr;
    detail::check(codex_agent_agent_hooks(
        owner->agent->context_raw(), owner->agent->get(), &raw));
    return Hooks(owner, detail::HooksHandle(owner->agent->context(), raw));
}

inline IntegrationAuthorization Agent::integration_authorization() const {
    ensure_valid();
    auto owner = detail::retain_agent_ownership(owner_);
    codex_agent_integration_authorization_t* raw = nullptr;
    detail::check(codex_agent_agent_integration_authorization(
        owner->agent->context_raw(), owner->agent->get(), &raw));
    return IntegrationAuthorization(
        owner,
        detail::IntegrationAuthorizationHandle(owner->agent->context(), raw));
}

inline Interactions Agent::interactions() const {
    ensure_valid();
    auto owner = detail::retain_agent_ownership(owner_);
    codex_agent_interactions_t* raw = nullptr;
    detail::check(codex_agent_agent_interactions(
        owner->agent->context_raw(), owner->agent->get(), &raw));
    return Interactions(
        owner, detail::InteractionsHandle(owner->agent->context(), raw));
}

inline McpServers Agent::mcp_servers() const {
    ensure_valid();
    auto owner = detail::retain_agent_ownership(owner_);
    codex_agent_mcp_servers_t* raw = nullptr;
    detail::check(codex_agent_agent_mcp_servers(
        owner->agent->context_raw(), owner->agent->get(), &raw));
    return McpServers(
        owner, detail::McpServersHandle(owner->agent->context(), raw));
}

inline Models Agent::models() const {
    ensure_valid();
    auto owner = detail::retain_agent_ownership(owner_);
    codex_agent_models_t* raw = nullptr;
    detail::check(codex_agent_agent_models(
        owner->agent->context_raw(), owner->agent->get(), &raw));
    return Models(owner, detail::ModelsHandle(owner->agent->context(), raw));
}

inline Plugins Agent::plugins() const {
    ensure_valid();
    auto owner = detail::retain_agent_ownership(owner_);
    codex_agent_plugins_t* raw = nullptr;
    detail::check(codex_agent_agent_plugins(
        owner->agent->context_raw(), owner->agent->get(), &raw));
    return Plugins(
        owner, detail::PluginsHandle(owner->agent->context(), raw));
}

inline Skills Agent::skills() const {
    ensure_valid();
    auto owner = detail::retain_agent_ownership(owner_);
    codex_agent_skills_t* raw = nullptr;
    detail::check(codex_agent_agent_skills(
        owner->agent->context_raw(), owner->agent->get(), &raw));
    return Skills(owner, detail::SkillsHandle(owner->agent->context(), raw));
}

inline Workspace Agent::workspace() const {
    ensure_valid();
    auto owner = detail::retain_agent_ownership(owner_);
    codex_agent_workspace_t* raw = nullptr;
    detail::check(codex_agent_agent_workspace(
        owner->agent->context_raw(), owner->agent->get(), &raw));
    detail::SyncHandle<codex_agent_workspace_t, codex_agent_workspace_destroy>
        snapshot(owner->agent->context(), raw);
    auto path = detail::copy_string(
        [&](std::uint8_t* buffer, std::size_t capacity,
            std::size_t* required) {
            return codex_agent_workspace_path_copy(
                owner->agent->context_raw(), snapshot.get(), buffer, capacity,
                required);
        });
    auto display_name = detail::copy_string(
        [&](std::uint8_t* buffer, std::size_t capacity,
            std::size_t* required) {
            return codex_agent_workspace_display_name_copy(
                owner->agent->context_raw(), snapshot.get(), buffer, capacity,
                required);
        });
    return Workspace(std::move(path), std::move(display_name));
}

}  // namespace codex_agent

#include <codex_agent/leaf_services_impl.hpp>
