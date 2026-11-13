#include <codex_agent/codex_agent.hpp>

#include <cassert>
#include <type_traits>

static_assert(std::is_same_v<
              decltype(&codex_agent::Host::create),
              codex_agent::Host (*)(const codex_agent::HostOptions&)>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Host::start),
              codex_agent::AsyncOperation<void>
                  (codex_agent::Host::*)() const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Host::select_workspace),
              codex_agent::AsyncOperation<void>
                  (codex_agent::Host::*)(std::string) const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Host::close),
              codex_agent::AsyncOperation<void>
                  (codex_agent::Host::*)() const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Host::state),
              codex_agent::HostState (codex_agent::Host::*)() const>);
static_assert(std::is_constructible_v<
              codex_agent::HostStateReady, codex_agent::Agent>);
static_assert(std::is_same_v<
              decltype(codex_agent::HostStateReady::agent),
              codex_agent::Agent>);

static_assert(std::is_same_v<
              decltype(&codex_agent::Agent::authentication),
              codex_agent::Authentication (codex_agent::Agent::*)() const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Agent::connectors),
              codex_agent::Connectors (codex_agent::Agent::*)() const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Agent::conversations),
              codex_agent::Conversations (codex_agent::Agent::*)() const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Agent::hooks),
              codex_agent::Hooks (codex_agent::Agent::*)() const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Agent::integration_authorization),
              codex_agent::IntegrationAuthorization
                  (codex_agent::Agent::*)() const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Agent::interactions),
              codex_agent::Interactions (codex_agent::Agent::*)() const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Agent::mcp_servers),
              codex_agent::McpServers (codex_agent::Agent::*)() const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Agent::models),
              codex_agent::Models (codex_agent::Agent::*)() const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Agent::plugins),
              codex_agent::Plugins (codex_agent::Agent::*)() const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Agent::skills),
              codex_agent::Skills (codex_agent::Agent::*)() const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Agent::workspace),
              codex_agent::Workspace (codex_agent::Agent::*)() const>);

static_assert(std::is_same_v<
              decltype(&codex_agent::Authentication::cancel),
              codex_agent::AsyncOperation<void>
                  (codex_agent::Authentication::*)() const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Interactions::state),
              codex_agent::InteractionState
                  (codex_agent::Interactions::*)() const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::IntegrationAuthorization::cancel),
              codex_agent::AsyncOperation<void>
                  (codex_agent::IntegrationAuthorization::*)() const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Models::list),
              codex_agent::AsyncOperation<std::vector<codex_agent::Model>>
                  (codex_agent::Models::*)() const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Skills::is_available),
              bool (codex_agent::Skills::*)() const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Hooks::list),
              codex_agent::AsyncOperation<codex_agent::HookCatalog>
                  (codex_agent::Hooks::*)() const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Plugins::is_available),
              bool (codex_agent::Plugins::*)() const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Connectors::is_available),
              bool (codex_agent::Connectors::*)() const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::McpServers::list),
              codex_agent::AsyncOperation<std::vector<codex_agent::McpServer>>
                  (codex_agent::McpServers::*)() const>);

int main() {
    const auto cancelled = codex_agent::ElicitationResponse::cancel();
    const auto declined = codex_agent::ElicitationResponse::decline();
    assert(cancelled.action == codex_agent::ElicitationAction::cancel);
    assert(declined.action == codex_agent::ElicitationAction::decline);

    codex_agent::FormField field{};
    field.name = "answer";
    field.title = "Answer";
    field.type = codex_agent::FormFieldType::string;
    field.is_required = true;
    assert(field.accepts(codex_agent::FormValue{
        codex_agent::FormTextValue{"yes"}}));
    assert(!field.accepts(std::nullopt));

    const codex_agent::Elicitation elicitation{
        "request", codex_agent::ConversationId("conversation"), "server",
        "Answer", std::nullopt,
        std::vector<codex_agent::FormField>{field}};
    const std::map<std::string, codex_agent::FormValue> content{
        {"answer", codex_agent::FormTextValue{"yes"}}};
    assert(elicitation.initial_values().empty());
    assert(elicitation.validate(content).is_valid());
    assert(elicitation.accept(content).action ==
           codex_agent::ElicitationAction::accept);
    assert((elicitation.accepts({
        codex_agent::ElicitationAction::accept, content})));

    const codex_agent::PendingApproval approval{
        {"approval", codex_agent::ConversationId("conversation")},
        "Approve", "Details"};
    codex_agent::InteractionState interactions{
        {approval}, {"approval"}, std::nullopt};
    const auto& live =
        std::get<codex_agent::PendingApproval>(interactions.pending.front());
    assert(interactions.is_resolving(live));
    assert(interactions.pending_for(
               codex_agent::ConversationId("conversation")).size() == 1);

    assert(codex_agent::AuthorizationUrl::chat_gpt(
               "https://chatgpt.com/").purpose ==
           codex_agent::AuthorizationPurpose::chat_gpt);
    assert(codex_agent::AuthorizationUrl::external(
               "https://example.com/").purpose ==
           codex_agent::AuthorizationPurpose::external);

    const codex_agent::McpServer mcp_server{
        "local", "Local MCP", codex_agent::McpAuthStatus::oauth,
        codex_agent::McpServerConfiguration{
            "local", codex_agent::McpHttpTransport{"https://example.com/mcp"}},
        codex_agent::ResourceOrigin::user};
    assert(mcp_server.is_authorized());
    assert(mcp_server.configuration.has_value());

    auto host = codex_agent::Host::create({
        .bundle_directory = "/bundle",
        .data_directory = "/data",
        .client_info = {"installed-consumer", "Installed consumer", "1"},
    });
    host.start().get();
    if (host.state().kind == codex_agent::HostStateKind::ready) {
        (void)host.agent();
    } else {
        try {
            (void)host.agent();
            assert(false);
        } catch (const codex_agent::Error& error) {
            assert(error.status() == codex_agent::Status::wrong_handle_type);
        }
    }
    host.close().get();
    assert(host.state().kind == codex_agent::HostStateKind::closed);
}
