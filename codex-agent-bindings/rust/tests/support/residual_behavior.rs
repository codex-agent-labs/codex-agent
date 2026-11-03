use codex_agent::*;
use std::collections::{BTreeMap, BTreeSet};

pub struct Fixtures {
    authentication: AuthenticationState,
    conversation_state: AgentConversationState,
    conversation: ConversationSnapshot,
    response: ElicitationResponse,
    elicitation: Elicitation,
    form_field: FormField,
    form_boolean: FormBoolean,
    form_number: FormNumber,
    form_text_list: FormTextList,
    form_text: FormText,
    hook_catalog: HookCatalog,
    command_handler: CommandHookHandler,
    mcp_handler: McpToolHookHandler,
    hook: Hook,
    connector_integration: ConnectorIntegration,
    mcp_integration: McpServerIntegration,
    authorization_state: IntegrationAuthorizationState,
    integration: Integration,
    interaction_state: InteractionState,
    plugin_invocation: PluginInvocation,
    skill_invocation: SkillInvocation,
    invocation: Invocation,
    message: Message,
    approval: PendingApproval,
    pending_elicitation: PendingElicitation,
    pending: PendingInteraction,
    request: TurnRequest,
    api_key: ApiKeyAuthentication,
    authorization_url: AuthorizationUrl,
    failed: HostStateFailed,
    preparing: HostStatePreparing,
    workspace_required: HostStateWorkspaceRequired,
    path_selection: PathWorkspaceSelection,
    workspace_available: WorkspaceAvailable,
    selection_required: WorkspaceSelectionRequired,
}

pub fn fixtures() -> Fixtures {
    let failure = CodexFailure::new("failed", "Failure", true).expect("failure");
    let workspace = Workspace::new("/workspace", Some("Workspace".into())).expect("workspace");
    let conversation_id = ConversationId::new("conversation-1").expect("conversation ID");
    let summary = ConversationSummary::new(conversation_id.clone(), "Title", 42);
    let skill_invocation = SkillInvocation::new("Skill", "skill.md");
    let plugin_invocation = PluginInvocation::new("Plugin", "plugin://plugin@market");
    let invocation = Invocation::Skill(skill_invocation.clone());
    let invocations = vec![
        invocation.clone(),
        Invocation::Plugin(plugin_invocation.clone()),
    ];
    let capabilities = BTreeSet::from([Capability::WebSearch]);
    let message = Message::new(
        "message",
        Some("client-message".into()),
        MessageRole::Assistant,
        "Text",
        CollaborationMode::Plan,
        Some("Reasoning".into()),
        Some("Plan".into()),
        Some("echo hi".into()),
        Some(0),
        capabilities.clone(),
        invocations.clone(),
    );
    let conversation = ConversationSnapshot::new(summary, vec![message.clone(), message.clone()]);
    let progress = TurnProgress::new(
        "progress",
        "commentary",
        "reasoning",
        "plan",
        None,
        "shell",
        None,
        None,
        vec![],
        false,
    );
    let conversation_state = AgentConversationState::new(
        ConversationStatus::Failed,
        Some(conversation_id.clone()),
        Some(conversation.clone()),
        progress,
        Some("model".into()),
        Some("high".into()),
        Some("fast".into()),
        Some(failure.clone()),
    );
    let form_text_list = FormTextList::new(vec!["one".into(), "one".into(), "two".into()]);
    let option = FormOption::new("one", "One", Some("Description".into()));
    let form_field = FormField::new(
        "field",
        "Field",
        Some("Description".into()),
        true,
        FormFieldType::MultiSelect,
        vec![option.clone(), option],
        Some(FormValue::TextList(form_text_list.clone())),
        Some(1.0),
        Some(10.0),
        Some(FormStringFormat::Uri),
        Some(1),
        Some(20),
        Some(1),
        Some(3),
        true,
        true,
    )
    .expect("form field");
    let elicitation = Elicitation::new(
        "request",
        "server",
        conversation_id.clone(),
        "Complete the form",
        Some(vec![form_field.clone(), form_field.clone()]),
        Some("https://example.test/form".into()),
    );
    let response = ElicitationResponse::new(
        ElicitationAction::Accept,
        BTreeMap::from([("field".into(), FormValue::TextList(form_text_list.clone()))]),
    );
    let command_handler = CommandHookHandler::new("echo hi", true);
    let mcp_handler = McpToolHookHandler::new("server", "tool");
    let hook = Hook::new(
        "hook",
        "hash",
        true,
        "after-turn",
        HookHandler::Command(command_handler.clone()),
        false,
        "PLUGIN",
        "/hook",
        30,
        HookTrustStatus::Modified,
        Some("matcher".into()),
        Some("plugin".into()),
        Some("changed".into()),
        None,
        true,
    );
    let hook_catalog = HookCatalog::new(
        vec![hook.clone(), hook.clone()],
        vec!["warning".into(), "warning".into()],
        vec!["error".into(), "error".into()],
    );
    let connector = Connector::new(
        "connector",
        "Connector",
        "Description",
        None,
        true,
        true,
        vec![],
    );
    let server = McpServer::new(
        "server",
        "Server",
        McpAuthStatus::Unknown,
        None,
        ResourceOrigin::User,
        false,
    );
    let connector_integration = ConnectorIntegration::new(connector);
    let mcp_integration = McpServerIntegration::new(server);
    let integration = Integration::Connector(connector_integration.clone());
    let authorization_url =
        AuthorizationUrl::chat_gpt("https://auth.openai.com/authorize").expect("authorization URL");
    let authentication = AuthenticationState::new(
        AuthenticationStatus::Authenticating,
        Some(authorization_url.clone()),
        Some(AuthorizationUrl::external("http://127.0.0.1:8080/device").expect("device URL")),
        Some("CODE".into()),
        Some(failure.clone()),
    );
    let approval = PendingApproval::new("approval", conversation_id.clone(), "Approve", "Details");
    let pending_elicitation = PendingElicitation::new(elicitation.clone());
    let pending = PendingInteraction::Approval(approval.clone());
    let interaction_state = InteractionState::new(
        vec![
            pending.clone(),
            PendingInteraction::Elicitation(pending_elicitation.clone()),
        ],
        BTreeSet::from(["approval".into()]),
        Some(failure.clone()),
    );
    let selection_required = WorkspaceSelectionRequired::new(
        WorkspaceSelectionReason::NotSelected,
        "Select a workspace",
    );
    Fixtures {
        authentication,
        conversation_state,
        conversation,
        response,
        elicitation,
        form_field,
        form_boolean: FormBoolean::new(true),
        form_number: FormNumber::new(1.5).expect("form number"),
        form_text_list,
        form_text: FormText::new("text"),
        hook_catalog,
        command_handler,
        mcp_handler,
        hook,
        connector_integration: connector_integration.clone(),
        mcp_integration,
        authorization_state: IntegrationAuthorizationState::new(
            IntegrationAuthorizationStatus::Authorized,
            Some(integration.clone()),
            Some(failure.clone()),
        ),
        integration,
        interaction_state,
        plugin_invocation,
        skill_invocation,
        invocation,
        message,
        approval,
        pending_elicitation,
        pending,
        request: TurnRequest::new(
            "Prompt",
            Some("client".into()),
            Some("model".into()),
            Some("high".into()),
            Some("fast".into()),
            ApprovalPreset::Strict,
            capabilities,
            invocations,
            CollaborationMode::Plan,
        ),
        api_key: ApiKeyAuthentication::new("secret").expect("API key"),
        authorization_url,
        failed: HostStateFailed::new(Some(workspace.clone()), failure),
        preparing: HostStatePreparing::new(workspace.clone()),
        workspace_required: HostStateWorkspaceRequired::new(selection_required.clone()),
        path_selection: PathWorkspaceSelection::new("/workspace").expect("path selection"),
        workspace_available: WorkspaceAvailable::new(workspace),
        selection_required,
    }
}

fn field(name: &str, field_type: FormFieldType) -> FormField {
    FormField::new(
        name,
        name,
        None,
        false,
        field_type,
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
    )
    .expect("valid behavior field")
}

fn field_accepts(field: &FormField, value: Option<&FormValue>) -> bool {
    field
        .accepts(value)
        .expect("real C SDK form-field acceptance")
}

fn form_field_accepts_truth_table() -> bool {
    let mut string = field("string", FormFieldType::String);
    string.is_required = true;
    string.minimum_length = Some(2);
    string.maximum_length = Some(4);
    let text = |value| FormValue::Text(FormText::new(value));
    if !field_accepts(&string, Some(&text("ok")))
        || field_accepts(&string, None)
        || field_accepts(&string, Some(&text(" \t")))
        || field_accepts(&string, Some(&text("x")))
        || field_accepts(&string, Some(&text("abcde")))
        || field_accepts(&string, Some(&FormValue::Boolean(FormBoolean::new(true))))
    {
        return false;
    }

    let mut number = field("number", FormFieldType::Number);
    number.minimum = Some(1.0);
    number.maximum = Some(3.0);
    let numeric = |value| FormValue::Number(FormNumber { value });
    if !field_accepts(&number, Some(&numeric(1.0)))
        || !field_accepts(&number, Some(&numeric(3.0)))
        || field_accepts(&number, Some(&numeric(0.9)))
        || field_accepts(&number, Some(&numeric(3.1)))
        || field_accepts(&number, Some(&numeric(f64::NAN)))
        || field_accepts(&number, Some(&numeric(f64::INFINITY)))
    {
        return false;
    }
    let integer = field("integer", FormFieldType::Integer);
    if !field_accepts(&integer, Some(&numeric(2.0))) || field_accepts(&integer, Some(&numeric(1.5)))
    {
        return false;
    }
    let boolean = field("boolean", FormFieldType::Boolean);
    if !field_accepts(&boolean, Some(&FormValue::Boolean(FormBoolean::new(false))))
        || field_accepts(&boolean, Some(&text("false")))
    {
        return false;
    }

    let mut single = field("single", FormFieldType::SingleSelect);
    single.options = vec![FormOption::new("alpha", "Alpha", None)];
    if !field_accepts(&single, Some(&text("alpha"))) || field_accepts(&single, Some(&text("other")))
    {
        return false;
    }
    single.allows_other = true;
    if !field_accepts(&single, Some(&text("other"))) || field_accepts(&single, Some(&text(" "))) {
        return false;
    }

    let mut multi = field("multi", FormFieldType::MultiSelect);
    multi.is_required = true;
    multi.options = vec![
        FormOption::new("alpha", "Alpha", None),
        FormOption::new("beta", "Beta", None),
    ];
    multi.minimum_selections = Some(1);
    multi.maximum_selections = Some(2);
    let texts = |values: &[&str]| {
        FormValue::TextList(FormTextList::new(
            values.iter().map(|value| (*value).to_owned()).collect(),
        ))
    };
    if !field_accepts(&multi, Some(&texts(&["alpha", "beta"])))
        || field_accepts(&multi, Some(&texts(&[])))
        || field_accepts(&multi, Some(&texts(&["alpha", "alpha"])))
        || field_accepts(&multi, Some(&texts(&["alpha", "beta", "other"])))
        || field_accepts(&multi, Some(&texts(&["other"])))
    {
        return false;
    }
    multi.allows_other = true;
    if !field_accepts(&multi, Some(&texts(&["alpha", "other"])))
        || field_accepts(&multi, Some(&texts(&["alpha", " "])))
    {
        return false;
    }

    let formats_match = [
        (FormStringFormat::Email, "user@example.com", "invalid"),
        (FormStringFormat::Uri, "https:x", "1https:x"),
        (FormStringFormat::Date, "2024-02-29", "2026-02-29"),
        (
            FormStringFormat::DateTime,
            "2026-01-01T12:00:60.123+01:00",
            "2026-01-01T24:00:00Z",
        ),
    ]
    .into_iter()
    .all(|(format, accepted, rejected)| {
        let mut formatted = field("formatted", FormFieldType::String);
        formatted.format = Some(format);
        field_accepts(&formatted, Some(&text(accepted)))
            && !field_accepts(&formatted, Some(&text(rejected)))
    });
    let mut date = field("date", FormFieldType::String);
    date.format = Some(FormStringFormat::Date);
    let mut date_time = field("date-time", FormFieldType::String);
    date_time.format = Some(FormStringFormat::DateTime);
    formats_match
        && !field_accepts(&date, Some(&text("2024- 1-01")))
        && !field_accepts(&date_time, Some(&text("2026-01-01T1 :00:00Z")))
}

fn elicitation_with_required_field() -> Elicitation {
    let mut required = field("required", FormFieldType::String);
    required.is_required = true;
    Elicitation::new(
        "request",
        "server",
        ConversationId::new("conversation").expect("conversation"),
        "Provide input",
        Some(vec![required]),
        None,
    )
}

fn elicitation_accepts_truth_table() -> bool {
    let elicitation = elicitation_with_required_field();
    let content = BTreeMap::from([("required".into(), FormValue::Text(FormText::new("answer")))]);
    elicitation
        .accepts(&ElicitationResponse::new(
            ElicitationAction::Accept,
            content.clone(),
        ))
        .expect("real C SDK accepts valid response")
        && !elicitation
            .accepts(&ElicitationResponse::new(
                ElicitationAction::Accept,
                BTreeMap::new(),
            ))
            .expect("real C SDK rejects missing response")
        && elicitation
            .accepts(&ElicitationResponse::decline().expect("native decline response"))
            .expect("real C SDK accepts decline")
        && elicitation
            .accepts(&ElicitationResponse::cancel().expect("native cancel response"))
            .expect("real C SDK accepts cancel")
        && !elicitation
            .accepts(&ElicitationResponse::new(
                ElicitationAction::Decline,
                content,
            ))
            .expect("real C SDK rejects decline content")
}

fn elicitation_accept_snapshot() -> bool {
    let elicitation = elicitation_with_required_field();
    let mut content =
        BTreeMap::from([("required".into(), FormValue::Text(FormText::new("answer")))]);
    let response = elicitation.accept(&content).expect("valid response");
    content.clear();
    response.action == ElicitationAction::Accept
        && response.content.len() == 1
        && elicitation.accept(&content).is_err()
}

fn elicitation_initial_values_snapshot() -> bool {
    let mut first = field("same", FormFieldType::MultiSelect);
    first.default_value = Some(FormValue::TextList(FormTextList::new(vec!["first".into()])));
    let mut second = field("same", FormFieldType::String);
    second.default_value = Some(FormValue::Text(FormText::new("second")));
    let omitted = field("omitted", FormFieldType::String);
    let mut elicitation = Elicitation::new(
        "request",
        "server",
        ConversationId::new("conversation").expect("conversation"),
        "message",
        Some(vec![first, second, omitted]),
        None,
    );
    let initial = elicitation
        .initial_values()
        .expect("real C SDK initial values");
    if let Some(fields) = &mut elicitation.form {
        fields[1].default_value = Some(FormValue::Text(FormText::new("mutated")));
    }
    initial == BTreeMap::from([("same".into(), FormValue::Text(FormText::new("second")))])
}

fn elicitation_validation_truth_table() -> bool {
    let elicitation = elicitation_with_required_field();
    let issues = elicitation
        .validate(&BTreeMap::from([(
            "unknown".into(),
            FormValue::Text(FormText::new("value")),
        )]))
        .expect("real C SDK invalid validation")
        .issues;
    issues
        == [
            ElicitationValidationIssue::new("unknown", ElicitationValidationReason::UnknownField),
            ElicitationValidationIssue::new(
                "required",
                ElicitationValidationReason::MissingRequired,
            ),
        ]
        && elicitation
            .validate(&BTreeMap::from([(
                "required".into(),
                FormValue::Text(FormText::new("answer")),
            )]))
            .expect("real C SDK valid validation")
            .is_valid()
}

fn interaction_identity_truth_table(f: &Fixtures) -> bool {
    let live = &f.interaction_state.pending[0];
    let equal_copy = live.clone();
    f.interaction_state
        .is_resolving(live)
        .expect("real C SDK live identity")
        && !f
            .interaction_state
            .is_resolving(&equal_copy)
            .expect("real C SDK detached identity")
        && !f
            .interaction_state
            .is_resolving(&f.interaction_state.pending[1])
            .expect("real C SDK unresolved identity")
}

fn interaction_pending_filter_truth_table(f: &Fixtures) -> bool {
    let target = f.approval.conversation_id.clone();
    let other = ConversationId::new("other").expect("other conversation");
    let approval = f.pending.clone();
    let elicitation = PendingInteraction::Elicitation(f.pending_elicitation.clone());
    let state = InteractionState::new(
        vec![
            approval.clone(),
            PendingInteraction::Approval(PendingApproval::new("other", other, "Other", "Other")),
            elicitation,
            approval,
        ],
        BTreeSet::new(),
        None,
    );
    let pending = state
        .pending_for(&target)
        .expect("real C SDK pending filter");
    pending.len() == 3
        && pending[0].request_id() == "approval"
        && pending[1].request_id() == "request"
        && pending[0] == pending[2]
        && !std::ptr::eq(pending[0], pending[2])
        && state
            .pending_for(&ConversationId::new("missing").expect("missing"))
            .expect("real C SDK missing pending filter")
            .is_empty()
}

#[allow(clippy::cognitive_complexity)]
pub fn exercise(symbol: &str, test_id: &str, f: &Fixtures) -> bool {
    let expected_id = match symbol {
        "codex_agent::ApprovalPreset::display_name" => {
            ApprovalPreset::AutoReview.display_name() == "Auto review"
        }
        "codex_agent::AuthenticationState::new" => {
            AuthenticationState::new(AuthenticationStatus::SignedOut, None, None, None, None).status
                == AuthenticationStatus::SignedOut
        }
        "codex_agent::AuthenticationState::device_user_code" => {
            f.authentication.device_user_code.as_deref() == Some("CODE")
        }
        "codex_agent::AuthenticationState::device_verification_url" => {
            f.authentication.device_verification_url.is_some()
        }
        "codex_agent::AuthenticationState::failure" => f.authentication.failure.is_some(),
        "codex_agent::AuthenticationState::pending_sign_in_url" => {
            f.authentication.pending_sign_in_url.is_some()
        }
        "codex_agent::AuthenticationState::status" => {
            f.authentication.status == AuthenticationStatus::Authenticating
        }
        "codex_agent::Capability::display_label" => {
            Capability::WebSearch.display_label() == "Web search"
        }
        "codex_agent::Capability::icon" => Capability::WebSearch.icon() == Some("🌐"),
        "codex_agent::Capability::id" => Capability::WebSearch.id() == "web_search",
        "codex_agent::Capability::prompt_label" => {
            Capability::WebSearch.prompt_label() == "Use 🌐 Web search"
        }
        "codex_agent::AgentConversationState::new" => {
            AgentConversationState::new(
                ConversationStatus::New,
                None,
                None,
                f.conversation_state.turn_progress.clone(),
                None,
                None,
                None,
                None,
            )
            .status
                == ConversationStatus::New
        }
        "codex_agent::AgentConversationState::can_cancel_turn" => {
            !f.conversation_state.can_cancel_turn()
        }
        "codex_agent::AgentConversationState::can_reload" => f.conversation_state.can_reload(),
        "codex_agent::AgentConversationState::can_start_turn" => {
            f.conversation_state.can_start_turn()
        }
        "codex_agent::AgentConversationState::conversation_id" => {
            f.conversation_state.conversation_id.is_some()
        }
        "codex_agent::AgentConversationState::conversation" => {
            f.conversation_state.conversation.is_some()
        }
        "codex_agent::AgentConversationState::effort" => {
            f.conversation_state.effort.as_deref() == Some("high")
        }
        "codex_agent::AgentConversationState::failure" => f.conversation_state.failure.is_some(),
        "codex_agent::AgentConversationState::model" => {
            f.conversation_state.model.as_deref() == Some("model")
        }
        "codex_agent::AgentConversationState::service_tier" => {
            f.conversation_state.service_tier.as_deref() == Some("fast")
        }
        "codex_agent::AgentConversationState::status" => {
            f.conversation_state.status == ConversationStatus::Failed
        }
        "codex_agent::AgentConversationState::turn_progress" => {
            f.conversation_state.turn_progress.text == "progress"
        }
        "codex_agent::ConversationSnapshot::new" => {
            ConversationSnapshot::new(f.conversation.summary.clone(), vec![])
                .messages
                .is_empty()
        }
        "codex_agent::ConversationSnapshot::messages" => f.conversation.messages.len() == 2,
        "codex_agent::ConversationSnapshot::summary" => f.conversation.summary.title == "Title",
        "codex_agent::ElicitationResponse::new" => {
            ElicitationResponse::new(ElicitationAction::Cancel, BTreeMap::new())
                .content
                .is_empty()
        }
        "codex_agent::ElicitationResponse::action" => {
            f.response.action == ElicitationAction::Accept
        }
        "codex_agent::ElicitationResponse::content" => f.response.content.len() == 1,
        "codex_agent::ElicitationResponse::cancel" => {
            let response = ElicitationResponse::cancel().expect("native cancel response");
            response.action == ElicitationAction::Cancel && response.content.is_empty()
        }
        "codex_agent::ElicitationResponse::decline" => {
            let response = ElicitationResponse::decline().expect("native decline response");
            response.action == ElicitationAction::Decline && response.content.is_empty()
        }
        "codex_agent::Elicitation::new" => Elicitation::new(
            "id",
            "server",
            f.elicitation.conversation_id.clone(),
            "message",
            None,
            None,
        )
        .form
        .is_none(),
        "codex_agent::Elicitation::conversation_id" => {
            f.elicitation.conversation_id.value == "conversation-1"
        }
        "codex_agent::Elicitation::form" => f
            .elicitation
            .form
            .as_ref()
            .is_some_and(|value| value.len() == 2),
        "codex_agent::Elicitation::message" => f.elicitation.message == "Complete the form",
        "codex_agent::Elicitation::request_id" => f.elicitation.request_id == "request",
        "codex_agent::Elicitation::server_name" => f.elicitation.server_name == "server",
        "codex_agent::Elicitation::url" => {
            f.elicitation.url.as_deref() == Some("https://example.test/form")
        }
        "codex_agent::Elicitation::accepts" => elicitation_accepts_truth_table(),
        "codex_agent::Elicitation::accept" => elicitation_accept_snapshot(),
        "codex_agent::Elicitation::initial_values" => elicitation_initial_values_snapshot(),
        "codex_agent::Elicitation::validate" => elicitation_validation_truth_table(),
        "codex_agent::FormField::new" => FormField::new(
            "field",
            "Field",
            None,
            false,
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
        )
        .is_ok(),
        "codex_agent::FormField::allows_other" => f.form_field.allows_other,
        "codex_agent::FormField::default_value" => f.form_field.default_value.is_some(),
        "codex_agent::FormField::description" => {
            f.form_field.description.as_deref() == Some("Description")
        }
        "codex_agent::FormField::format" => f.form_field.format == Some(FormStringFormat::Uri),
        "codex_agent::FormField::is_required" => f.form_field.is_required,
        "codex_agent::FormField::is_secret" => f.form_field.is_secret,
        "codex_agent::FormField::maximum_length" => f.form_field.maximum_length == Some(20),
        "codex_agent::FormField::maximum_selections" => f.form_field.maximum_selections == Some(3),
        "codex_agent::FormField::maximum" => f.form_field.maximum == Some(10.0),
        "codex_agent::FormField::minimum_length" => f.form_field.minimum_length == Some(1),
        "codex_agent::FormField::minimum_selections" => f.form_field.minimum_selections == Some(1),
        "codex_agent::FormField::minimum" => f.form_field.minimum == Some(1.0),
        "codex_agent::FormField::name" => f.form_field.name == "field",
        "codex_agent::FormField::options" => f.form_field.options.len() == 2,
        "codex_agent::FormField::title" => f.form_field.title == "Field",
        "codex_agent::FormField::field_type" => {
            f.form_field.field_type == FormFieldType::MultiSelect
        }
        "codex_agent::FormField::accepts" => form_field_accepts_truth_table(),
        "codex_agent::FormBoolean::new" => !FormBoolean::new(false).value,
        "codex_agent::FormBoolean::value" => f.form_boolean.value,
        "codex_agent::FormNumber::new" => FormNumber::new(2.5).is_ok(),
        "codex_agent::FormNumber::value" => f.form_number.value == 1.5,
        "codex_agent::FormTextList::new" => FormTextList::new(vec![]).value.is_empty(),
        "codex_agent::FormTextList::value" => f.form_text_list.value == ["one", "one", "two"],
        "codex_agent::FormText::new" => FormText::new("new").value == "new",
        "codex_agent::FormText::value" => f.form_text.value == "text",
        "codex_agent::HookCatalog::new" => {
            HookCatalog::new(vec![], vec![], vec![]).hooks.is_empty()
        }
        "codex_agent::HookCatalog::errors" => f.hook_catalog.errors.len() == 2,
        "codex_agent::HookCatalog::hooks" => f.hook_catalog.hooks.len() == 2,
        "codex_agent::HookCatalog::warnings" => f.hook_catalog.warnings.len() == 2,
        "codex_agent::AgentHookHandler::INSTANCE" => AgentHookHandler::INSTANCE == AgentHookHandler,
        "codex_agent::CommandHookHandler::new" => {
            CommandHookHandler::new("true", false).command == "true"
        }
        "codex_agent::CommandHookHandler::command" => f.command_handler.command == "echo hi",
        "codex_agent::CommandHookHandler::is_async" => f.command_handler.is_async,
        "codex_agent::McpToolHookHandler::new" => McpToolHookHandler::new("s", "t").tool == "t",
        "codex_agent::McpToolHookHandler::server" => f.mcp_handler.server == "server",
        "codex_agent::McpToolHookHandler::tool" => f.mcp_handler.tool == "tool",
        "codex_agent::PromptHookHandler::INSTANCE" => {
            PromptHookHandler::INSTANCE == PromptHookHandler
        }
        "codex_agent::Hook::new" => {
            Hook::new(
                "k",
                "h",
                false,
                "e",
                HookHandler::Agent(AgentHookHandler),
                false,
                "USER",
                "p",
                1,
                HookTrustStatus::Trusted,
                None,
                None,
                None,
                None,
                false,
            )
            .key == "k"
        }
        "codex_agent::Hook::can_trust" => f.hook.can_trust(),
        "codex_agent::Hook::can_uninstall" => f.hook.can_uninstall,
        "codex_agent::Hook::current_hash" => f.hook.current_hash == "hash",
        "codex_agent::Hook::event_name" => f.hook.event_name == "after-turn",
        "codex_agent::Hook::handler" => matches!(f.hook.handler, HookHandler::Command(_)),
        "codex_agent::Hook::is_enabled" => f.hook.is_enabled,
        "codex_agent::Hook::is_managed" => !f.hook.is_managed,
        "codex_agent::Hook::key" => f.hook.key == "hook",
        "codex_agent::Hook::matcher" => f.hook.matcher.as_deref() == Some("matcher"),
        "codex_agent::Hook::origin" => f.hook.origin == ResourceOrigin::Plugin,
        "codex_agent::Hook::plugin_id" => f.hook.plugin_id.as_deref() == Some("plugin"),
        "codex_agent::Hook::source_path" => f.hook.source_path == "/hook",
        "codex_agent::Hook::source" => f.hook.source == "PLUGIN",
        "codex_agent::Hook::status_message" => f.hook.status_message.as_deref() == Some("changed"),
        "codex_agent::Hook::timeout_seconds" => f.hook.timeout_seconds == 30,
        "codex_agent::Hook::trust_status" => f.hook.trust_status == HookTrustStatus::Modified,
        "codex_agent::ConnectorIntegration::new" => {
            ConnectorIntegration::new(f.connector_integration.connector.clone()).id() == "connector"
        }
        "codex_agent::ConnectorIntegration::connector" => {
            f.connector_integration.connector.id == "connector"
        }
        "codex_agent::ConnectorIntegration::display_name" => {
            f.connector_integration.display_name() == "Connector"
        }
        "codex_agent::ConnectorIntegration::id" => f.connector_integration.id() == "connector",
        "codex_agent::McpServerIntegration::new" => {
            McpServerIntegration::new(f.mcp_integration.server.clone()).id() == "server"
        }
        "codex_agent::McpServerIntegration::display_name" => {
            f.mcp_integration.display_name() == "Server"
        }
        "codex_agent::McpServerIntegration::id" => f.mcp_integration.id() == "server",
        "codex_agent::McpServerIntegration::server" => f.mcp_integration.server.name == "server",
        "codex_agent::IntegrationAuthorizationState::new" => {
            IntegrationAuthorizationState::new(IntegrationAuthorizationStatus::Idle, None, None)
                .target
                .is_none()
        }
        "codex_agent::IntegrationAuthorizationState::failure" => {
            f.authorization_state.failure.is_some()
        }
        "codex_agent::IntegrationAuthorizationState::status" => {
            f.authorization_state.status == IntegrationAuthorizationStatus::Authorized
        }
        "codex_agent::IntegrationAuthorizationState::target" => {
            f.authorization_state.target.is_some()
        }
        "codex_agent::Integration::display_name" => {
            f.integration.display_name() == "Connector"
                && Integration::McpServer(Box::new(f.mcp_integration.clone())).display_name()
                    == "Server"
        }
        "codex_agent::Integration::id" => {
            f.integration.id() == "connector"
                && Integration::McpServer(Box::new(f.mcp_integration.clone())).id() == "server"
        }
        "codex_agent::InteractionState::new" => {
            InteractionState::new(vec![], BTreeSet::new(), None)
                .pending
                .is_empty()
        }
        "codex_agent::InteractionState::failure" => f.interaction_state.failure.is_some(),
        "codex_agent::InteractionState::pending" => f.interaction_state.pending.len() == 2,
        "codex_agent::InteractionState::resolving_request_ids" => f
            .interaction_state
            .resolving_request_ids
            .contains("approval"),
        "codex_agent::InteractionState::is_resolving" => interaction_identity_truth_table(f),
        "codex_agent::InteractionState::pending_for" => interaction_pending_filter_truth_table(f),
        "codex_agent::PluginInvocation::new" => PluginInvocation::new("p", "u").uri == "u",
        "codex_agent::PluginInvocation::key" => {
            f.plugin_invocation.key() == "plugin:plugin://plugin@market"
        }
        "codex_agent::PluginInvocation::name" => f.plugin_invocation.name == "Plugin",
        "codex_agent::PluginInvocation::uri" => f.plugin_invocation.uri == "plugin://plugin@market",
        "codex_agent::SkillInvocation::new" => SkillInvocation::new("s", "p").path == "p",
        "codex_agent::SkillInvocation::key" => f.skill_invocation.key() == "skill:skill.md",
        "codex_agent::SkillInvocation::name" => f.skill_invocation.name == "Skill",
        "codex_agent::SkillInvocation::path" => f.skill_invocation.path == "skill.md",
        "codex_agent::Invocation::key" => f.invocation.key() == "skill:skill.md",
        "codex_agent::Invocation::name" => f.invocation.name() == "Skill",
        "codex_agent::Message::new" => {
            Message::new(
                "i",
                None,
                MessageRole::User,
                "t",
                CollaborationMode::Default,
                None,
                None,
                None,
                None,
                BTreeSet::new(),
                vec![],
            )
            .id == "i"
        }
        "codex_agent::Message::capabilities" => {
            f.message.capabilities.contains(&Capability::WebSearch)
        }
        "codex_agent::Message::client_message_id" => {
            f.message.client_message_id.as_deref() == Some("client-message")
        }
        "codex_agent::Message::collaboration_mode" => {
            f.message.collaboration_mode == CollaborationMode::Plan
        }
        "codex_agent::Message::exit_code" => f.message.exit_code == Some(0),
        "codex_agent::Message::id" => f.message.id == "message",
        "codex_agent::Message::invocations" => f.message.invocations.len() == 2,
        "codex_agent::Message::plan" => f.message.plan.as_deref() == Some("Plan"),
        "codex_agent::Message::reasoning" => f.message.reasoning.as_deref() == Some("Reasoning"),
        "codex_agent::Message::role" => f.message.role == MessageRole::Assistant,
        "codex_agent::Message::shell_command" => {
            f.message.shell_command.as_deref() == Some("echo hi")
        }
        "codex_agent::Message::text" => f.message.text == "Text",
        "codex_agent::PendingApproval::new" => {
            PendingApproval::new("r", f.approval.conversation_id.clone(), "t", "d").request_id
                == "r"
        }
        "codex_agent::PendingApproval::conversation_id" => {
            f.approval.conversation_id.value == "conversation-1"
        }
        "codex_agent::PendingApproval::details" => f.approval.details == "Details",
        "codex_agent::PendingApproval::request_id" => f.approval.request_id == "approval",
        "codex_agent::PendingApproval::title" => f.approval.title == "Approve",
        "codex_agent::PendingElicitation::new" => {
            PendingElicitation::new(f.elicitation.clone()).request_id() == "request"
        }
        "codex_agent::PendingElicitation::conversation_id" => {
            f.pending_elicitation.conversation_id().value == "conversation-1"
        }
        "codex_agent::PendingElicitation::elicitation" => {
            f.pending_elicitation.elicitation.request_id == "request"
        }
        "codex_agent::PendingElicitation::request_id" => {
            f.pending_elicitation.request_id() == "request"
        }
        "codex_agent::PendingInteraction::conversation_id" => {
            f.pending.conversation_id().value == "conversation-1"
        }
        "codex_agent::PendingInteraction::request_id" => f.pending.request_id() == "approval",
        "codex_agent::SkillScope::display_name" => SkillScope::Repo.display_name() == "Workspace",
        "codex_agent::TurnRequest::new" => {
            TurnRequest::new(
                "p",
                None,
                None,
                None,
                None,
                ApprovalPreset::AutoReview,
                BTreeSet::new(),
                vec![],
                CollaborationMode::Default,
            )
            .prompt
                == "p"
        }
        "codex_agent::TurnRequest::approval_preset" => {
            f.request.approval_preset == ApprovalPreset::Strict
        }
        "codex_agent::TurnRequest::capabilities" => {
            f.request.capabilities.contains(&Capability::WebSearch)
        }
        "codex_agent::TurnRequest::client_message_id" => {
            f.request.client_message_id.as_deref() == Some("client")
        }
        "codex_agent::TurnRequest::collaboration_mode" => {
            f.request.collaboration_mode == CollaborationMode::Plan
        }
        "codex_agent::TurnRequest::effort" => f.request.effort.as_deref() == Some("high"),
        "codex_agent::TurnRequest::invocations" => f.request.invocations.len() == 2,
        "codex_agent::TurnRequest::model" => f.request.model.as_deref() == Some("model"),
        "codex_agent::TurnRequest::prompt" => f.request.prompt == "Prompt",
        "codex_agent::TurnRequest::service_tier" => {
            f.request.service_tier.as_deref() == Some("fast")
        }
        "codex_agent::ApiKeyAuthentication::new" => ApiKeyAuthentication::new("key").is_ok(),
        "codex_agent::ApiKeyAuthentication::value" => f.api_key.value == "secret",
        "codex_agent::ChatGptBrowserAuthentication::INSTANCE" => {
            ChatGptBrowserAuthentication::INSTANCE == ChatGptBrowserAuthentication
        }
        "codex_agent::ChatGptDeviceCodeAuthentication::INSTANCE" => {
            ChatGptDeviceCodeAuthentication::INSTANCE == ChatGptDeviceCodeAuthentication
        }
        "codex_agent::AuthorizationUrl::purpose" => {
            f.authorization_url.purpose == AuthorizationPurpose::ChatGpt
        }
        "codex_agent::AuthorizationUrl::value" => {
            f.authorization_url.value == "https://auth.openai.com/authorize"
        }
        "codex_agent::AuthorizationUrl::chat_gpt" => {
            AuthorizationUrl::chat_gpt("https://auth.openai.com:443/login").is_ok()
                && AuthorizationUrl::chat_gpt("https://evil-openai.com").is_err()
                && AuthorizationUrl::chat_gpt("https://openai.com:444").is_err()
        }
        "codex_agent::AuthorizationUrl::external" => {
            AuthorizationUrl::external("https://example.com/login").is_ok()
                && AuthorizationUrl::external("http://[::1]:8080/callback").is_ok()
                && AuthorizationUrl::external("http://example.com").is_err()
        }
        "codex_agent::HostStateClosed::INSTANCE" => HostStateClosed::INSTANCE == HostStateClosed,
        "codex_agent::HostStateFailed::new" => HostStateFailed::new(None, f.failed.failure.clone())
            .workspace
            .is_none(),
        "codex_agent::HostStateFailed::failure" => f.failed.failure.code == "failed",
        "codex_agent::HostStateFailed::workspace" => f.failed.workspace.is_some(),
        "codex_agent::HostStateNew::INSTANCE" => HostStateNew::INSTANCE == HostStateNew,
        "codex_agent::HostStatePreparing::new" => {
            HostStatePreparing::new(f.preparing.workspace.clone())
                .workspace
                .path
                == "/workspace"
        }
        "codex_agent::HostStatePreparing::workspace" => f.preparing.workspace.path == "/workspace",
        "codex_agent::HostStateRestoring::INSTANCE" => {
            HostStateRestoring::INSTANCE == HostStateRestoring
        }
        "codex_agent::HostStateWorkspaceRequired::new" => {
            HostStateWorkspaceRequired::new(f.selection_required.clone())
                .requirement
                .message
                == "Select a workspace"
        }
        "codex_agent::HostStateWorkspaceRequired::requirement" => {
            f.workspace_required.requirement.reason == WorkspaceSelectionReason::NotSelected
        }
        "codex_agent::PathWorkspaceSelection::new" => PathWorkspaceSelection::new("/tmp").is_ok(),
        "codex_agent::PathWorkspaceSelection::path" => f.path_selection.path == "/workspace",
        "codex_agent::WorkspaceAvailable::new" => {
            WorkspaceAvailable::new(f.workspace_available.workspace.clone())
                .workspace
                .path
                == "/workspace"
        }
        "codex_agent::WorkspaceAvailable::workspace" => {
            f.workspace_available.workspace.path == "/workspace"
        }
        "codex_agent::WorkspaceSelectionRequired::new" => {
            WorkspaceSelectionRequired::new(WorkspaceSelectionReason::NotFound, "missing").message
                == "missing"
        }
        "codex_agent::WorkspaceSelectionRequired::message" => {
            f.selection_required.message == "Select a workspace"
        }
        "codex_agent::WorkspaceSelectionRequired::reason" => {
            f.selection_required.reason == WorkspaceSelectionReason::NotSelected
        }
        _ => return false,
    };
    let function_test = match symbol {
        "codex_agent::ElicitationResponse::cancel" => Some("rust.function:000"),
        "codex_agent::ElicitationResponse::decline" => Some("rust.function:001"),
        "codex_agent::Elicitation::accepts" => Some("rust.function:002"),
        "codex_agent::Elicitation::accept" => Some("rust.function:003"),
        "codex_agent::Elicitation::initial_values" => Some("rust.function:004"),
        "codex_agent::Elicitation::validate" => Some("rust.function:005"),
        "codex_agent::FormField::accepts" => Some("rust.function:006"),
        "codex_agent::InteractionState::is_resolving" => Some("rust.function:007"),
        "codex_agent::InteractionState::pending_for" => Some("rust.function:008"),
        "codex_agent::AuthorizationUrl::chat_gpt" => Some("rust.function:009"),
        "codex_agent::AuthorizationUrl::external" => Some("rust.function:010"),
        _ => None,
    };
    expected_id
        && function_test.map_or_else(|| test_id.starts_with("rust.residual:"), |id| test_id == id)
}

pub fn verify_negatives() {
    assert!(ApiKeyAuthentication::new(" \t").is_err());
    assert!(AuthorizationUrl::chat_gpt("https://evil-openai.com").is_err());
    assert!(AuthorizationUrl::chat_gpt("https://auth.openai.com:443/login").is_ok());
    assert!(AuthorizationUrl::chat_gpt("https://openai.com:444").is_err());
    assert!(AuthorizationUrl::external("http://example.com").is_err());
    assert!(AuthorizationUrl::external("http://[::1]:8080/callback").is_ok());
    assert!(AuthorizationUrl::external("https://bad_host.test/login").is_err());
    assert!(AuthorizationUrl::external("https://.example.test/login").is_err());
    assert!(AuthorizationUrl::external("https://example.test:/login").is_err());
    assert!(FormNumber::new(f64::NAN).is_err());
    assert!(
        FormField::new(
            "f",
            "F",
            None,
            false,
            FormFieldType::String,
            vec![],
            None,
            None,
            None,
            None,
            Some(2),
            Some(1),
            None,
            None,
            false,
            false
        )
        .is_err()
    );
    assert!(PathWorkspaceSelection::new("bad\0path").is_err());
}
