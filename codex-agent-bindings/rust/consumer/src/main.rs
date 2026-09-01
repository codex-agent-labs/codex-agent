use codex_agent::{
    ApprovalDecision, ApprovalPreset, AuthenticationMethod, AuthenticationState,
    AuthenticationStatus, AuthorizationUrl, ClientInfo, CodexAuthentication, CodexConnectors,
    CodexConversation, CodexConversations, CodexError, CodexHooks, CodexHost,
    CodexIntegrationAuthorization, CodexInteractions, CodexMcpServers, CodexModels, CodexPlugins,
    CodexSkills, Connector, ConnectorIntegration, ConversationId, ConversationOpenOptions,
    ConversationSettings, ConversationSummary, Elicitation, ElicitationAction, ElicitationResponse,
    FormField, FormFieldType, FormText, FormValue, Hook, HostOptions, HostStateReady,
    InstallationScope, Integration, InteractionState, McpAuthStatus, McpAuthentication,
    McpHttpTransport, McpServer, McpServerConfiguration, McpToolApproval, McpToolConfiguration,
    McpToolExposureSurface, McpTransport, Model, PendingApproval, PendingElicitation,
    PendingInteraction, PluginReference, Resolution, ResourceOrigin, RuntimeTarget, Skill,
    TurnRequest,
};
use std::collections::{BTreeMap, BTreeSet};

#[allow(dead_code, clippy::too_many_arguments)]
fn compile_exact_leaf_service_surface(
    authentication: &CodexAuthentication,
    connectors: &CodexConnectors,
    hooks: &CodexHooks,
    authorization: &CodexIntegrationAuthorization,
    interactions: &CodexInteractions,
    mcp: &CodexMcpServers,
    models: &CodexModels,
    plugins: &CodexPlugins,
    skills: &CodexSkills,
    method: &AuthenticationMethod,
    integration: &Integration,
    approval: &PendingApproval,
    elicitation: &PendingElicitation,
    response: &ElicitationResponse,
    hook: &Hook,
    configuration: &McpServerConfiguration,
    server: &McpServer,
    model: &Model,
    plugin: &PluginReference,
    skill: &Skill,
) {
    let _ = authentication.authenticate(method);
    let _ = authentication.cancel();
    let _ = authentication.sign_out();
    let _ = authentication.is_authenticated();
    let _ = authentication.is_authenticating();
    let _ = authentication.state();
    let _ = connectors.list(true);
    let _ = connectors.is_available();
    let _ = hooks.install("hooks", InstallationScope::User);
    let _ = hooks.list();
    let _ = hooks.trust(hook);
    let _ = hooks.uninstall(hook);
    let _ = hooks.is_available();
    let _ = authorization.authorize(integration);
    let _ = authorization.cancel();
    let _ = authorization.active();
    let _ = authorization.is_authorizing();
    let _ = authorization.state();
    let _ = interactions.open_url(elicitation);
    let _ = interactions.resolve_approval(approval, ApprovalDecision::Accept);
    let _ = interactions.resolve_elicitation(elicitation, response);
    let _ = interactions.approvals();
    let _ = interactions.elicitations();
    let _ = interactions.state();
    let _ = mcp.add(configuration);
    let _ = mcp.list();
    let _ = mcp.remove(server);
    let _ = mcp.is_available();
    let _ = models.list();
    let _ = models.resolve_effort(model, Resolution::Preferred);
    let _ = models.resolve_service_tier(model, Resolution::Preferred);
    let _ = models.resolve(Resolution::Preferred);
    let _ = plugins.install(plugin);
    let _ = plugins.list(true);
    let _ = plugins.read(plugin);
    let _ = plugins.uninstall(plugin);
    let _ = plugins.is_available();
    let _ = skills.install("skills", InstallationScope::Workspace);
    let _ = skills.list(true);
    let _ = skills.read("skill.md", 0);
    let _ = skills.uninstall(skill);
    let _ = skills.is_available();
}

#[allow(dead_code)]
fn compile_exact_conversation_surface(
    conversations: &CodexConversations,
    conversation: &CodexConversation,
    conversation_id: &ConversationId,
    request: &TurnRequest,
) {
    let _ = conversations.active();
    let _ = conversations.list();
    let _ = conversations.open(ConversationOpenOptions::default());
    let _ = conversations.read(conversation_id);
    let _ = conversations.rename(conversation_id, "renamed");
    let _ = conversations.delete(conversation_id);

    let _ = conversation.send("hello");
    let _ = conversation.send_request(request);
    let _ = conversation.run_shell_command("pwd");
    let _ = conversation.reload();
    let _ = conversation.cancel_turn();
    let _ = conversation.close();
    let _ = conversation.state();
    let _ = conversation.active_turn_progress();
    let _ = conversation.can_cancel_turn();
    let _ = conversation.can_reload();
    let _ = conversation.can_run_shell_command();
    let _ = conversation.can_start_turn();
    let _ = conversation.current_messages();
    let _ = conversation.is_turn_active();
}

#[allow(dead_code)]
fn compile_exact_agent_surface(agent: &codex_agent::CodexAgent) {
    let _ = agent.authentication();
    let _ = agent.connectors();
    let _ = agent.conversations();
    let _ = agent.hooks();
    let _ = agent.integration_authorization();
    let _ = agent.interactions();
    let _ = agent.mcp_servers();
    let _ = agent.models();
    let _ = agent.plugins();
    let _ = agent.skills();
    let _ = agent.workspace();
}

#[allow(dead_code)]
fn compile_exact_host_ready_surface(host: &CodexHost, agent: &codex_agent::CodexAgent) {
    let ready = HostStateReady::new(agent.clone());
    let _ = ready.agent();
    let _factory: fn(HostOptions) -> Result<CodexHost, CodexError> = CodexHost::create;
    let _ = host.start();
    let _ = host.select_workspace("workspace");
    let _ = host.close();
    let _ = host.state();
    let _ = host.states();
}

fn main() -> Result<(), CodexError> {
    let _target = RuntimeTarget::current();
    let _factory: fn(HostOptions) -> Result<CodexHost, CodexError> = CodexHost::create;
    let _options = HostOptions {
        bundle_directory: "bundle".into(),
        data_directory: "data".into(),
        client_info: ClientInfo {
            name: "consumer".into(),
            title: "Consumer".into(),
            version: "1".into(),
        },
    };
    let _open = ConversationOpenOptions::default();
    let _summary = ConversationSummary::new(
        ConversationId::new("conversation")?,
        "Consumer conversation",
        42,
    );
    let _settings = ConversationSettings::new(ApprovalPreset::Strict, Some("fast".into()));

    let http = McpHttpTransport::new(
        "https://example.com/mcp",
        Some("TOKEN_ENV".into()),
        Some(BTreeMap::from([("X-Consumer".into(), "true".into())])),
        Some(BTreeMap::new()),
        None,
    )?;
    let configuration = McpServerConfiguration::new(
        "consumer_server",
        McpTransport::Http(http),
        Some(McpAuthentication::Oauth),
        "local",
        true,
        false,
        true,
        Some(vec![McpToolExposureSurface::CodeMode]),
        Some(1.5),
        Some(2.5),
        Some(McpToolApproval::Prompt),
        Some(vec!["search".into()]),
        Some(Vec::new()),
        Some(vec!["read".into()]),
        None,
        Some(String::new()),
        BTreeMap::from([("search".into(), McpToolConfiguration::new(None))]),
    )?;
    let server = McpServer::new(
        "consumer_server",
        "Consumer server",
        McpAuthStatus::Oauth,
        Some(configuration),
        ResourceOrigin::User,
        true,
    );
    assert!(server.is_authorized());
    let authentication = AuthenticationState::new(
        AuthenticationStatus::Authenticating,
        Some(AuthorizationUrl::chat_gpt(
            "https://auth.openai.com/authorize",
        )?),
        None,
        None,
        None,
    );
    assert!(authentication.pending_sign_in_url.is_some());
    let integration = Integration::Connector(ConnectorIntegration::new(Connector::new(
        "connector",
        "Consumer connector",
        "Consumer coverage",
        None,
        true,
        true,
        vec![],
    )));
    assert_eq!(integration.id(), "connector");
    let required = FormField::new(
        "answer",
        "Answer",
        None,
        true,
        FormFieldType::String,
        vec![],
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        false,
        false,
    )?;
    assert!(
        required
            .accepts(Some(&FormValue::Text(FormText::new("yes"))))
            .expect("native field acceptance")
    );
    assert!(!required.accepts(None).expect("native required field"));
    let conversation_id = ConversationId::new("function-consumer")?;
    let elicitation = Elicitation::new(
        "request",
        "server",
        conversation_id.clone(),
        "Answer",
        Some(vec![required.clone()]),
        None,
    );
    let content = BTreeMap::from([("answer".into(), FormValue::Text(FormText::new("yes")))]);
    let accepted = elicitation.accept(&content)?;
    assert_eq!(accepted.action, ElicitationAction::Accept);
    assert!(elicitation.accepts(&accepted)?);
    assert!(elicitation.validate(&content)?.is_valid());
    assert!(elicitation.initial_values()?.is_empty());
    assert!(elicitation.accepts(&ElicitationResponse::decline()?)?);
    assert!(elicitation.accepts(&ElicitationResponse::cancel()?)?);

    let pending = PendingInteraction::Approval(PendingApproval::new(
        "approval",
        conversation_id.clone(),
        "Approve",
        "Details",
    ));
    let state = InteractionState::new(vec![pending], BTreeSet::from(["approval".into()]), None);
    assert!(state.is_resolving(&state.pending[0])?);
    assert_eq!(state.pending_for(&conversation_id)?.len(), 1);
    assert_eq!(
        AuthorizationUrl::external("http://127.0.0.1:8080/callback")?.purpose,
        codex_agent::AuthorizationPurpose::External
    );
    Ok(())
}
