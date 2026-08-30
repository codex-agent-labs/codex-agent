use codex_agent::*;
use std::collections::{BTreeMap, BTreeSet};
#[cfg(all(target_os = "macos", target_arch = "aarch64"))]
use std::fmt::Write as _;
use std::path::{Path, PathBuf};
use std::process::Command;

pub struct Evidence {
    pub compiler: BTreeMap<String, String>,
    pub tests: BTreeSet<String>,
}

struct Fixtures {
    client: ClientInfo,
    connector: Connector,
    connector_sparse: Connector,
    conversation_id: ConversationId,
    conversation_settings: ConversationSettings,
    conversation_settings_sparse: ConversationSettings,
    conversation_summary: ConversationSummary,
    failure: CodexFailure,
    form_option: FormOption,
    form_option_sparse: FormOption,
    hook: HookActivity,
    hook_sparse: HookActivity,
    mcp_environment: McpEnvironmentVariable,
    mcp_environment_sparse: McpEnvironmentVariable,
    mcp_oauth: McpOauthConfiguration,
    mcp_oauth_sparse: McpOauthConfiguration,
    mcp_tool: McpToolConfiguration,
    mcp_tool_sparse: McpToolConfiguration,
    mcp_http: McpHttpTransport,
    mcp_http_sparse: McpHttpTransport,
    mcp_http_empty: McpHttpTransport,
    mcp_stdio: McpStdioTransport,
    mcp_stdio_sparse: McpStdioTransport,
    mcp_configuration: McpServerConfiguration,
    mcp_configuration_sparse: McpServerConfiguration,
    mcp_configuration_empty: McpServerConfiguration,
    mcp_server: McpServer,
    mcp_server_sparse: McpServer,
    model: Model,
    model_sparse: Model,
    plan_progress: PlanProgress,
    plan_progress_sparse: PlanProgress,
    plan_step: PlanStep,
    plugin_catalog: PluginCatalog,
    plugin_catalog_sparse: PluginCatalog,
    plugin_detail: PluginDetail,
    plugin_install: PluginInstallResult,
    plugin_install_sparse: PluginInstallResult,
    plugin_reference: PluginReference,
    plugin_reference_sparse: PluginReference,
    plugin_skill: PluginSkill,
    plugin_skill_sparse: PluginSkill,
    plugin_summary: PluginSummary,
    plugin_summary_sparse: PluginSummary,
    service_tier: ServiceTier,
    skill: Skill,
    skill_sparse: Skill,
    skill_catalog: SkillCatalog,
    skill_catalog_sparse: SkillCatalog,
    skill_chunk: SkillChunk,
    skill_chunk_sparse: SkillChunk,
    turn: TurnProgress,
    turn_sparse: TurnProgress,
    validation: ElicitationValidation,
    validation_sparse: ElicitationValidation,
    validation_issue: ElicitationValidationIssue,
    workspace: Workspace,
    workspace_default: Workspace,
}

fn fixtures() -> Fixtures {
    let client = ClientInfo::new("rust", "Rust consumer", "1.95").expect("valid client");
    let connector = Connector::new(
        "connector-id",
        "Connector",
        "connector description",
        Some("https://example.test/install".into()),
        true,
        false,
        vec!["first".into(), "first".into(), "last".into()],
    );
    let connector_sparse = Connector::new("sparse", "Sparse", "", None, false, true, vec![]);
    let conversation_id = ConversationId::new("conversation-1").expect("valid conversation ID");
    let conversation_settings =
        ConversationSettings::new(ApprovalPreset::AskMe, Some("priority".into()));
    let conversation_settings_sparse = ConversationSettings::default();
    let conversation_summary = ConversationSummary::new(conversation_id.clone(), "Summary", 1_234);
    let failure = CodexFailure::new("failed", "operation failed", true).expect("valid failure");
    let form_option = FormOption::new("value", "Title", Some("description".into()));
    let form_option_sparse = FormOption::new("sparse", "Sparse", None);
    let hook = HookActivity::new(
        "hook-id",
        "afterTurn",
        "command",
        HookRunStatus::Completed,
        Some("complete".into()),
        vec!["first".into(), "first".into(), "last".into()],
    );
    let hook_sparse = HookActivity::new(
        "sparse",
        "beforeTurn",
        "prompt",
        HookRunStatus::Running,
        None,
        vec![],
    );
    let mcp_environment = McpEnvironmentVariable::new("TOKEN", Some(McpEnvironmentSource::Remote))
        .expect("valid environment variable");
    let mcp_environment_sparse =
        McpEnvironmentVariable::new("LOCAL", None).expect("valid environment variable");
    let mcp_oauth = McpOauthConfiguration::new(Some("client".into()), Some(65_535))
        .expect("valid OAuth settings");
    let mcp_oauth_sparse = McpOauthConfiguration::new(None, None).expect("valid OAuth settings");
    let mcp_tool = McpToolConfiguration::new(Some(McpToolApproval::Writes));
    let mcp_tool_sparse = McpToolConfiguration::new(None);
    let map = |pairs: &[(&str, &str)]| {
        pairs
            .iter()
            .map(|(key, value)| ((*key).into(), (*value).into()))
            .collect::<BTreeMap<String, String>>()
    };
    let mcp_http = McpHttpTransport::new(
        "https://example.test/mcp",
        Some("TOKEN".into()),
        Some(map(&[("alpha", "one"), ("omega", "two")])),
        Some(map(&[("ENV_A", "A"), ("ENV_Z", "Z")])),
        Some("helper".into()),
    )
    .expect("valid HTTP MCP transport");
    let mcp_http_sparse = McpHttpTransport::new("http://127.0.0.1:8080", None, None, None, None)
        .expect("valid loopback HTTP MCP transport");
    let mcp_http_empty = McpHttpTransport::new(
        "https://empty.test",
        None,
        Some(BTreeMap::new()),
        Some(BTreeMap::new()),
        None,
    )
    .expect("valid empty HTTP maps");
    let mcp_stdio = McpStdioTransport::new(
        "node",
        vec!["first".into(), "first".into(), "last".into()],
        Some("/workspace".into()),
        Some(map(&[("A", "one"), ("Z", "two")])),
        vec![mcp_environment.clone(), mcp_environment.clone()],
    )
    .expect("valid stdio MCP transport");
    let mcp_stdio_sparse =
        McpStdioTransport::new("node", vec![], None, None, vec![]).expect("valid stdio");
    let tools = [
        ("read".into(), mcp_tool.clone()),
        ("write".into(), McpToolConfiguration::new(None)),
    ]
    .into_iter()
    .collect();
    let mcp_configuration = McpServerConfiguration::new(
        "server_name",
        McpTransport::Http(mcp_http.clone()),
        Some(McpAuthentication::Oauth),
        "local",
        true,
        true,
        true,
        Some(vec![
            McpToolExposureSurface::CodeMode,
            McpToolExposureSurface::CodeMode,
            McpToolExposureSurface::Direct,
        ]),
        Some(1.5),
        Some(2.5),
        Some(McpToolApproval::Prompt),
        Some(vec!["first".into(), "first".into(), "last".into()]),
        Some(vec!["deny".into(), "deny".into()]),
        Some(vec!["scope".into(), "scope".into()]),
        Some(mcp_oauth.clone()),
        Some("resource".into()),
        tools,
    )
    .expect("valid MCP server configuration");
    let mcp_configuration_sparse = McpServerConfiguration::new(
        "sparse",
        McpTransport::Stdio(mcp_stdio_sparse.clone()),
        None,
        "local",
        true,
        false,
        false,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        BTreeMap::new(),
    )
    .expect("valid sparse MCP server configuration");
    let mcp_configuration_empty = McpServerConfiguration::new(
        "empty",
        McpTransport::Http(mcp_http_empty.clone()),
        None,
        "local",
        false,
        false,
        false,
        Some(vec![]),
        None,
        None,
        None,
        Some(vec![]),
        Some(vec![]),
        Some(vec![]),
        None,
        None,
        BTreeMap::new(),
    )
    .expect("valid present-empty MCP server configuration");
    let mcp_server = McpServer::new(
        "server_name",
        "Server",
        McpAuthStatus::Oauth,
        Some(mcp_configuration.clone()),
        ResourceOrigin::Workspace,
        true,
    );
    let mcp_server_sparse = McpServer::new(
        "sparse",
        "Sparse",
        McpAuthStatus::NotLoggedIn,
        None,
        ResourceOrigin::Unknown,
        false,
    );
    let service_tier = ServiceTier::new("priority", "Priority", "Fast lane");
    let model = Model::new(
        "model-id",
        "Model",
        "model description",
        vec!["high".into(), "high".into(), "low".into()],
        "high",
        true,
        vec![service_tier.clone(), service_tier.clone()],
        Some("priority".into()),
    );
    let model_sparse = Model::new("sparse", "Sparse", "", vec![], "", false, vec![], None);
    let plan_step = PlanStep::new("Ship it", PlanStepStatus::InProgress);
    let plan_progress = PlanProgress::new(
        Some("explanation".into()),
        vec![plan_step.clone(), plan_step.clone()],
    );
    let plan_progress_sparse = PlanProgress::new(None, vec![]);
    let plugin_reference = PluginReference::new(
        "plugin-id",
        "plugin-name",
        "marketplace",
        Some("path".into()),
        Some("remote".into()),
    );
    let plugin_reference_sparse = PluginReference::new("sparse", "sparse", "market", None, None);
    let plugin_skill = PluginSkill::new("skill", "plugin skill", true, Some("/skill".into()));
    let plugin_skill_sparse = PluginSkill::new("sparse", "", false, None);
    let plugin_summary = PluginSummary::new(
        plugin_reference.clone(),
        "Plugin",
        "summary description",
        true,
        false,
        PluginInstallPolicy::InstalledByDefault,
        PluginAuthPolicy::OnUse,
        true,
        vec!["first".into(), "first".into(), "last".into()],
        Some("#fff".into()),
        Some("https://example.test/privacy".into()),
        Some("https://example.test/terms".into()),
        Some("https://example.test".into()),
    );
    let plugin_summary_sparse = PluginSummary::new(
        plugin_reference_sparse.clone(),
        "Sparse",
        "",
        false,
        true,
        PluginInstallPolicy::Available,
        PluginAuthPolicy::OnInstall,
        false,
        vec![],
        None,
        None,
        None,
        None,
    );
    let plugin_catalog = PluginCatalog::new(
        vec![plugin_summary.clone(), plugin_summary.clone()],
        vec!["first".into(), "first".into(), "last".into()],
        CatalogFreshness::StaleCache,
    );
    let plugin_catalog_sparse = PluginCatalog::new(vec![], vec![], CatalogFreshness::Live);
    let plugin_detail = PluginDetail::new(
        plugin_summary.clone(),
        "detail description",
        vec![plugin_skill.clone(), plugin_skill.clone()],
        vec![connector.clone(), connector.clone()],
        vec!["server".into(), "server".into()],
        7,
    );
    let plugin_install = PluginInstallResult::new(
        PluginAuthPolicy::OnUse,
        vec![connector.clone(), connector.clone()],
        Some("installed".into()),
    );
    let plugin_install_sparse = PluginInstallResult::new(PluginAuthPolicy::OnInstall, vec![], None);
    let skill = Skill::new(
        "skill",
        "Skill",
        "skill description",
        "/skill",
        SkillScope::Repo,
        true,
        Some("#000".into()),
        vec!["first".into(), "first".into(), "last".into()],
        true,
        None,
    );
    let skill_sparse = Skill::new(
        "sparse",
        "Sparse",
        "",
        "/sparse",
        SkillScope::System,
        false,
        None,
        vec![],
        false,
        Some(ResourceOrigin::Unknown),
    );
    let skill_catalog = SkillCatalog::new(
        vec![skill.clone(), skill.clone()],
        vec!["first".into(), "first".into(), "last".into()],
    );
    let skill_catalog_sparse = SkillCatalog::new(vec![], vec![]);
    let skill_chunk = SkillChunk::new("content", Some(42), 84);
    let skill_chunk_sparse = SkillChunk::new("", None, 0);
    let turn = TurnProgress::new(
        "text",
        "commentary",
        "reasoning",
        "plan",
        Some(plan_progress.clone()),
        "shell output",
        Some(17),
        Some(WorkActivity::WritingFiles),
        vec![hook.clone(), hook.clone()],
        true,
    );
    let turn_sparse = TurnProgress::new("", "", "", "", None, "", None, None, vec![], false);
    let validation_issue =
        ElicitationValidationIssue::new("field", ElicitationValidationReason::InvalidFormat);
    let validation =
        ElicitationValidation::new(vec![validation_issue.clone(), validation_issue.clone()]);
    let validation_sparse = ElicitationValidation::new(vec![]);
    let workspace = Workspace::new("/workspace", Some("Workspace".into())).expect("workspace");
    let workspace_default = Workspace::new("/default", None).expect("workspace default");

    Fixtures {
        client,
        connector,
        connector_sparse,
        conversation_id,
        conversation_settings,
        conversation_settings_sparse,
        conversation_summary,
        failure,
        form_option,
        form_option_sparse,
        hook,
        hook_sparse,
        mcp_environment,
        mcp_environment_sparse,
        mcp_oauth,
        mcp_oauth_sparse,
        mcp_tool,
        mcp_tool_sparse,
        mcp_http,
        mcp_http_sparse,
        mcp_http_empty,
        mcp_stdio,
        mcp_stdio_sparse,
        mcp_configuration,
        mcp_configuration_sparse,
        mcp_configuration_empty,
        mcp_server,
        mcp_server_sparse,
        model,
        model_sparse,
        plan_progress,
        plan_progress_sparse,
        plan_step,
        plugin_catalog,
        plugin_catalog_sparse,
        plugin_detail,
        plugin_install,
        plugin_install_sparse,
        plugin_reference,
        plugin_reference_sparse,
        plugin_skill,
        plugin_skill_sparse,
        plugin_summary,
        plugin_summary_sparse,
        service_tier,
        skill,
        skill_sparse,
        skill_catalog,
        skill_catalog_sparse,
        skill_chunk,
        skill_chunk_sparse,
        turn,
        turn_sparse,
        validation,
        validation_sparse,
        validation_issue,
        workspace,
        workspace_default,
    }
}

fn exact_strings(values: &[String], expected: &[&str]) -> bool {
    values
        .iter()
        .map(String::as_str)
        .eq(expected.iter().copied())
}

fn exercise(symbol: &str, f: &Fixtures) -> bool {
    match symbol {
        "codex_agent::ClientInfo::new" => ClientInfo::new("n", "t", "v").is_ok(),
        "codex_agent::ClientInfo::name" => f.client.name == "rust",
        "codex_agent::ClientInfo::title" => f.client.title == "Rust consumer",
        "codex_agent::ClientInfo::version" => f.client.version == "1.95",
        "codex_agent::CodexFailure::new" => CodexFailure::new("c", "m", false).is_ok(),
        "codex_agent::CodexFailure::code" => f.failure.code == "failed",
        "codex_agent::CodexFailure::message" => f.failure.message == "operation failed",
        "codex_agent::CodexFailure::recoverable" => f.failure.recoverable,
        "codex_agent::Workspace::new" => f.workspace_default.display_name == "/default",
        "codex_agent::Workspace::path" => f.workspace.path == "/workspace",
        "codex_agent::Workspace::display_name" => f.workspace.display_name == "Workspace",
        "codex_agent::ConversationId::new" => ConversationId::new("id").is_ok(),
        "codex_agent::ConversationId::value" => f.conversation_id.value == "conversation-1",
        "codex_agent::ConversationSettings::new" => {
            f.conversation_settings_sparse == ConversationSettings::default()
        }
        "codex_agent::ConversationSettings::approval_preset" => {
            f.conversation_settings.approval_preset == ApprovalPreset::AskMe
        }
        "codex_agent::ConversationSettings::service_tier" => {
            f.conversation_settings.service_tier.as_deref() == Some("priority")
                && f.conversation_settings_sparse.service_tier.is_none()
        }
        "codex_agent::ConversationSummary::new" => {
            f.conversation_summary.conversation_id == f.conversation_id
        }
        "codex_agent::ConversationSummary::conversation_id" => {
            f.conversation_summary.conversation_id.value == "conversation-1"
        }
        "codex_agent::ConversationSummary::title" => f.conversation_summary.title == "Summary",
        "codex_agent::ConversationSummary::updated_at_epoch_seconds" => {
            f.conversation_summary.updated_at_epoch_seconds == 1_234
        }
        "codex_agent::ElicitationValidationIssue::new" => f.validation_issue.field_name == "field",
        "codex_agent::ElicitationValidationIssue::field_name" => {
            f.validation_issue.field_name == "field"
        }
        "codex_agent::ElicitationValidationIssue::reason" => {
            f.validation_issue.reason == ElicitationValidationReason::InvalidFormat
        }
        "codex_agent::ElicitationValidation::new" => {
            f.validation.issues.len() == 2 && f.validation.issues[0] == f.validation.issues[1]
        }
        "codex_agent::ElicitationValidation::issues" => {
            f.validation.issues.len() == 2 && f.validation_sparse.issues.is_empty()
        }
        "codex_agent::ElicitationValidation::is_valid" => {
            !f.validation.is_valid() && f.validation_sparse.is_valid()
        }
        "codex_agent::FormOption::new" => {
            f.form_option.description.is_some() && f.form_option_sparse.description.is_none()
        }
        "codex_agent::FormOption::value" => f.form_option.value == "value",
        "codex_agent::FormOption::title" => f.form_option.title == "Title",
        "codex_agent::FormOption::description" => {
            f.form_option.description.as_deref() == Some("description")
                && f.form_option_sparse.description.is_none()
        }
        "codex_agent::McpEnvironmentVariable::new" => {
            McpEnvironmentVariable::new("NAME", None).is_ok()
        }
        "codex_agent::McpEnvironmentVariable::name" => f.mcp_environment.name == "TOKEN",
        "codex_agent::McpEnvironmentVariable::source" => {
            f.mcp_environment.source == Some(McpEnvironmentSource::Remote)
                && f.mcp_environment_sparse.source.is_none()
        }
        "codex_agent::McpOauthConfiguration::new" => {
            McpOauthConfiguration::new(None, Some(1)).is_ok()
                && McpOauthConfiguration::new(None, Some(65_535)).is_ok()
        }
        "codex_agent::McpOauthConfiguration::client_id" => {
            f.mcp_oauth.client_id.as_deref() == Some("client")
                && f.mcp_oauth_sparse.client_id.is_none()
        }
        "codex_agent::McpOauthConfiguration::callback_port" => {
            f.mcp_oauth.callback_port == Some(65_535) && f.mcp_oauth_sparse.callback_port.is_none()
        }
        "codex_agent::McpToolConfiguration::new" => {
            f.mcp_tool.approval == Some(McpToolApproval::Writes)
        }
        "codex_agent::McpToolConfiguration::approval" => {
            f.mcp_tool.approval == Some(McpToolApproval::Writes)
                && f.mcp_tool_sparse.approval.is_none()
        }
        "codex_agent::McpHttpTransport::new" => {
            McpHttpTransport::new("https://example.test", None, None, None, None).is_ok()
                && McpHttpTransport::new("http://localhost:8080", None, None, None, None).is_ok()
        }
        "codex_agent::McpHttpTransport::url" => f.mcp_http.url == "https://example.test/mcp",
        "codex_agent::McpHttpTransport::bearer_token_environment_variable" => {
            f.mcp_http.bearer_token_environment_variable.as_deref() == Some("TOKEN")
                && f.mcp_http_sparse
                    .bearer_token_environment_variable
                    .is_none()
        }
        "codex_agent::McpHttpTransport::headers" => {
            f.mcp_http
                .headers
                .as_ref()
                .is_some_and(|headers| headers.keys().map(String::as_str).eq(["alpha", "omega"]))
                && f.mcp_http_sparse.headers.is_none()
                && f.mcp_http_empty
                    .headers
                    .as_ref()
                    .is_some_and(BTreeMap::is_empty)
        }
        "codex_agent::McpHttpTransport::environment_headers" => {
            f.mcp_http
                .environment_headers
                .as_ref()
                .is_some_and(|headers| headers.keys().map(String::as_str).eq(["ENV_A", "ENV_Z"]))
                && f.mcp_http_sparse.environment_headers.is_none()
                && f.mcp_http_empty
                    .environment_headers
                    .as_ref()
                    .is_some_and(BTreeMap::is_empty)
        }
        "codex_agent::McpHttpTransport::headers_helper" => {
            f.mcp_http.headers_helper.as_deref() == Some("helper")
                && f.mcp_http_sparse.headers_helper.is_none()
        }
        "codex_agent::McpStdioTransport::new" => {
            McpStdioTransport::new("node", vec![], None, None, vec![]).is_ok()
        }
        "codex_agent::McpStdioTransport::command" => f.mcp_stdio.command == "node",
        "codex_agent::McpStdioTransport::arguments" => {
            exact_strings(&f.mcp_stdio.arguments, &["first", "first", "last"])
                && f.mcp_stdio_sparse.arguments.is_empty()
        }
        "codex_agent::McpStdioTransport::working_directory" => {
            f.mcp_stdio.working_directory.as_deref() == Some("/workspace")
                && f.mcp_stdio_sparse.working_directory.is_none()
        }
        "codex_agent::McpStdioTransport::environment" => {
            f.mcp_stdio
                .environment
                .as_ref()
                .is_some_and(|environment| environment.keys().map(String::as_str).eq(["A", "Z"]))
                && f.mcp_stdio_sparse.environment.is_none()
        }
        "codex_agent::McpStdioTransport::forwarded_environment" => {
            f.mcp_stdio.forwarded_environment.len() == 2
                && f.mcp_stdio.forwarded_environment[0] == f.mcp_stdio.forwarded_environment[1]
                && f.mcp_stdio_sparse.forwarded_environment.is_empty()
        }
        "codex_agent::McpServerConfiguration::new" => {
            f.mcp_configuration.name == "server_name"
                && f.mcp_configuration_sparse.name == "sparse"
                && f.mcp_configuration_empty.name == "empty"
        }
        "codex_agent::McpServerConfiguration::name" => f.mcp_configuration.name == "server_name",
        "codex_agent::McpServerConfiguration::transport" => {
            matches!(f.mcp_configuration.transport, McpTransport::Http(_))
                && matches!(f.mcp_configuration_sparse.transport, McpTransport::Stdio(_))
        }
        "codex_agent::McpServerConfiguration::authentication" => {
            f.mcp_configuration.authentication == Some(McpAuthentication::Oauth)
                && f.mcp_configuration_sparse.authentication.is_none()
        }
        "codex_agent::McpServerConfiguration::environment_id" => {
            f.mcp_configuration.environment_id == "local"
        }
        "codex_agent::McpServerConfiguration::is_enabled" => {
            f.mcp_configuration.is_enabled && !f.mcp_configuration_empty.is_enabled
        }
        "codex_agent::McpServerConfiguration::is_required" => {
            f.mcp_configuration.is_required && !f.mcp_configuration_sparse.is_required
        }
        "codex_agent::McpServerConfiguration::supports_parallel_tool_calls" => {
            f.mcp_configuration.supports_parallel_tool_calls
                && !f.mcp_configuration_sparse.supports_parallel_tool_calls
        }
        "codex_agent::McpServerConfiguration::omit_tools_from" => {
            f.mcp_configuration
                .omit_tools_from
                .as_ref()
                .is_some_and(|items| {
                    items
                        == &[
                            McpToolExposureSurface::CodeMode,
                            McpToolExposureSurface::CodeMode,
                            McpToolExposureSurface::Direct,
                        ]
                })
                && f.mcp_configuration_sparse.omit_tools_from.is_none()
                && f.mcp_configuration_empty
                    .omit_tools_from
                    .as_ref()
                    .is_some_and(Vec::is_empty)
        }
        "codex_agent::McpServerConfiguration::startup_timeout_seconds" => {
            f.mcp_configuration.startup_timeout_seconds == Some(1.5)
                && f.mcp_configuration_sparse.startup_timeout_seconds.is_none()
        }
        "codex_agent::McpServerConfiguration::tool_timeout_seconds" => {
            f.mcp_configuration.tool_timeout_seconds == Some(2.5)
                && f.mcp_configuration_sparse.tool_timeout_seconds.is_none()
        }
        "codex_agent::McpServerConfiguration::default_tool_approval" => {
            f.mcp_configuration.default_tool_approval == Some(McpToolApproval::Prompt)
                && f.mcp_configuration_sparse.default_tool_approval.is_none()
        }
        "codex_agent::McpServerConfiguration::enabled_tools" => {
            f.mcp_configuration
                .enabled_tools
                .as_ref()
                .is_some_and(|items| exact_strings(items, &["first", "first", "last"]))
                && f.mcp_configuration_sparse.enabled_tools.is_none()
                && f.mcp_configuration_empty
                    .enabled_tools
                    .as_ref()
                    .is_some_and(Vec::is_empty)
        }
        "codex_agent::McpServerConfiguration::disabled_tools" => {
            f.mcp_configuration
                .disabled_tools
                .as_ref()
                .is_some_and(|items| exact_strings(items, &["deny", "deny"]))
                && f.mcp_configuration_sparse.disabled_tools.is_none()
                && f.mcp_configuration_empty
                    .disabled_tools
                    .as_ref()
                    .is_some_and(Vec::is_empty)
        }
        "codex_agent::McpServerConfiguration::scopes" => {
            f.mcp_configuration
                .scopes
                .as_ref()
                .is_some_and(|items| exact_strings(items, &["scope", "scope"]))
                && f.mcp_configuration_sparse.scopes.is_none()
                && f.mcp_configuration_empty
                    .scopes
                    .as_ref()
                    .is_some_and(Vec::is_empty)
        }
        "codex_agent::McpServerConfiguration::oauth" => {
            f.mcp_configuration.oauth.as_ref() == Some(&f.mcp_oauth)
                && f.mcp_configuration_sparse.oauth.is_none()
        }
        "codex_agent::McpServerConfiguration::oauth_resource" => {
            f.mcp_configuration.oauth_resource.as_deref() == Some("resource")
                && f.mcp_configuration_sparse.oauth_resource.is_none()
        }
        "codex_agent::McpServerConfiguration::tools" => {
            f.mcp_configuration
                .tools
                .keys()
                .map(String::as_str)
                .eq(["read", "write"])
                && f.mcp_configuration_sparse.tools.is_empty()
        }
        "codex_agent::McpServer::new" => f.mcp_server.configuration.is_some(),
        "codex_agent::McpServer::name" => f.mcp_server.name == "server_name",
        "codex_agent::McpServer::display_name" => f.mcp_server.display_name == "Server",
        "codex_agent::McpServer::auth_status" => f.mcp_server.auth_status == McpAuthStatus::Oauth,
        "codex_agent::McpServer::configuration" => {
            f.mcp_server.configuration.as_ref() == Some(&f.mcp_configuration)
                && f.mcp_server_sparse.configuration.is_none()
        }
        "codex_agent::McpServer::origin" => f.mcp_server.origin == ResourceOrigin::Workspace,
        "codex_agent::McpServer::can_remove" => {
            f.mcp_server.can_remove && !f.mcp_server_sparse.can_remove
        }
        "codex_agent::McpServer::is_authorized" => [
            (McpAuthStatus::Unknown, false),
            (McpAuthStatus::Unsupported, false),
            (McpAuthStatus::NotLoggedIn, false),
            (McpAuthStatus::BearerToken, true),
            (McpAuthStatus::Oauth, true),
        ]
        .into_iter()
        .all(|(status, expected)| {
            McpServer::new("name", "Name", status, None, ResourceOrigin::Unknown, false)
                .is_authorized()
                == expected
        }),
        "codex_agent::PlanStep::new" => f.plan_step.text == "Ship it",
        "codex_agent::PlanStep::text" => f.plan_step.text == "Ship it",
        "codex_agent::PlanStep::status" => f.plan_step.status == PlanStepStatus::InProgress,
        "codex_agent::PlanProgress::new" => {
            f.plan_progress.steps.len() == 2 && f.plan_progress_sparse.steps.is_empty()
        }
        "codex_agent::PlanProgress::explanation" => {
            f.plan_progress.explanation.as_deref() == Some("explanation")
                && f.plan_progress_sparse.explanation.is_none()
        }
        "codex_agent::PlanProgress::steps" => {
            f.plan_progress.steps.len() == 2
                && f.plan_progress.steps[0] == f.plan_progress.steps[1]
                && f.plan_progress_sparse.steps.is_empty()
        }
        "codex_agent::ServiceTier::new" => f.service_tier.id == "priority",
        "codex_agent::ServiceTier::id" => f.service_tier.id == "priority",
        "codex_agent::ServiceTier::name" => f.service_tier.name == "Priority",
        "codex_agent::ServiceTier::description" => f.service_tier.description == "Fast lane",
        "codex_agent::Model::new" => {
            f.model.supported_efforts.len() == 3 && f.model_sparse.supported_efforts.is_empty()
        }
        "codex_agent::Model::id" => f.model.id == "model-id",
        "codex_agent::Model::display_name" => f.model.display_name == "Model",
        "codex_agent::Model::description" => f.model.description == "model description",
        "codex_agent::Model::supported_efforts" => {
            exact_strings(&f.model.supported_efforts, &["high", "high", "low"])
                && f.model_sparse.supported_efforts.is_empty()
        }
        "codex_agent::Model::default_effort" => f.model.default_effort == "high",
        "codex_agent::Model::is_default" => f.model.is_default && !f.model_sparse.is_default,
        "codex_agent::Model::service_tiers" => {
            f.model.service_tiers.len() == 2
                && f.model.service_tiers[0] == f.model.service_tiers[1]
                && f.model_sparse.service_tiers.is_empty()
        }
        "codex_agent::Model::default_service_tier" => {
            f.model.default_service_tier.as_deref() == Some("priority")
                && f.model_sparse.default_service_tier.is_none()
        }
        "codex_agent::Connector::new" => {
            f.connector.plugin_names.len() == 3 && f.connector_sparse.plugin_names.is_empty()
        }
        "codex_agent::Connector::id" => f.connector.id == "connector-id",
        "codex_agent::Connector::name" => f.connector.name == "Connector",
        "codex_agent::Connector::description" => f.connector.description == "connector description",
        "codex_agent::Connector::install_url" => {
            f.connector.install_url.as_deref() == Some("https://example.test/install")
                && f.connector_sparse.install_url.is_none()
        }
        "codex_agent::Connector::is_accessible" => {
            f.connector.is_accessible && !f.connector_sparse.is_accessible
        }
        "codex_agent::Connector::is_enabled" => {
            !f.connector.is_enabled && f.connector_sparse.is_enabled
        }
        "codex_agent::Connector::plugin_names" => {
            exact_strings(&f.connector.plugin_names, &["first", "first", "last"])
                && f.connector_sparse.plugin_names.is_empty()
        }
        "codex_agent::PluginReference::new" => {
            f.plugin_reference.uri() == "plugin://plugin-name@marketplace"
        }
        "codex_agent::PluginReference::id" => f.plugin_reference.id == "plugin-id",
        "codex_agent::PluginReference::name" => f.plugin_reference.name == "plugin-name",
        "codex_agent::PluginReference::marketplace_name" => {
            f.plugin_reference.marketplace_name == "marketplace"
        }
        "codex_agent::PluginReference::marketplace_path" => {
            f.plugin_reference.marketplace_path.as_deref() == Some("path")
                && f.plugin_reference_sparse.marketplace_path.is_none()
        }
        "codex_agent::PluginReference::remote_plugin_id" => {
            f.plugin_reference.remote_plugin_id.as_deref() == Some("remote")
                && f.plugin_reference_sparse.remote_plugin_id.is_none()
        }
        "codex_agent::PluginReference::uri" => {
            f.plugin_reference.uri() == "plugin://plugin-name@marketplace"
        }
        "codex_agent::PluginSkill::new" => f.plugin_skill.is_enabled,
        "codex_agent::PluginSkill::name" => f.plugin_skill.name == "skill",
        "codex_agent::PluginSkill::description" => f.plugin_skill.description == "plugin skill",
        "codex_agent::PluginSkill::is_enabled" => {
            f.plugin_skill.is_enabled && !f.plugin_skill_sparse.is_enabled
        }
        "codex_agent::PluginSkill::path" => {
            f.plugin_skill.path.as_deref() == Some("/skill") && f.plugin_skill_sparse.path.is_none()
        }
        "codex_agent::PluginSummary::new" => {
            f.plugin_summary.capabilities.len() == 3
                && f.plugin_summary_sparse.capabilities.is_empty()
        }
        "codex_agent::PluginSummary::reference" => f.plugin_summary.reference == f.plugin_reference,
        "codex_agent::PluginSummary::display_name" => f.plugin_summary.display_name == "Plugin",
        "codex_agent::PluginSummary::description" => {
            f.plugin_summary.description == "summary description"
        }
        "codex_agent::PluginSummary::is_installed" => {
            f.plugin_summary.is_installed && !f.plugin_summary_sparse.is_installed
        }
        "codex_agent::PluginSummary::is_enabled" => {
            !f.plugin_summary.is_enabled && f.plugin_summary_sparse.is_enabled
        }
        "codex_agent::PluginSummary::install_policy" => {
            f.plugin_summary.install_policy == PluginInstallPolicy::InstalledByDefault
        }
        "codex_agent::PluginSummary::auth_policy" => {
            f.plugin_summary.auth_policy == PluginAuthPolicy::OnUse
        }
        "codex_agent::PluginSummary::is_available" => {
            f.plugin_summary.is_available && !f.plugin_summary_sparse.is_available
        }
        "codex_agent::PluginSummary::capabilities" => {
            exact_strings(&f.plugin_summary.capabilities, &["first", "first", "last"])
                && f.plugin_summary_sparse.capabilities.is_empty()
        }
        "codex_agent::PluginSummary::brand_color" => {
            f.plugin_summary.brand_color.as_deref() == Some("#fff")
                && f.plugin_summary_sparse.brand_color.is_none()
        }
        "codex_agent::PluginSummary::privacy_policy_url" => {
            f.plugin_summary.privacy_policy_url.as_deref() == Some("https://example.test/privacy")
                && f.plugin_summary_sparse.privacy_policy_url.is_none()
        }
        "codex_agent::PluginSummary::terms_of_service_url" => {
            f.plugin_summary.terms_of_service_url.as_deref() == Some("https://example.test/terms")
                && f.plugin_summary_sparse.terms_of_service_url.is_none()
        }
        "codex_agent::PluginSummary::website_url" => {
            f.plugin_summary.website_url.as_deref() == Some("https://example.test")
                && f.plugin_summary_sparse.website_url.is_none()
        }
        "codex_agent::PluginCatalog::new" => {
            f.plugin_catalog.plugins.len() == 2 && f.plugin_catalog_sparse.plugins.is_empty()
        }
        "codex_agent::PluginCatalog::plugins" => {
            f.plugin_catalog.plugins.len() == 2
                && f.plugin_catalog.plugins[0] == f.plugin_catalog.plugins[1]
                && f.plugin_catalog_sparse.plugins.is_empty()
        }
        "codex_agent::PluginCatalog::errors" => {
            exact_strings(&f.plugin_catalog.errors, &["first", "first", "last"])
                && f.plugin_catalog_sparse.errors.is_empty()
        }
        "codex_agent::PluginCatalog::freshness" => {
            f.plugin_catalog.freshness == CatalogFreshness::StaleCache
                && f.plugin_catalog_sparse.freshness == CatalogFreshness::Live
        }
        "codex_agent::PluginDetail::new" => f.plugin_detail.hook_count == 7,
        "codex_agent::PluginDetail::summary" => f.plugin_detail.summary == f.plugin_summary,
        "codex_agent::PluginDetail::description" => {
            f.plugin_detail.description == "detail description"
        }
        "codex_agent::PluginDetail::skills" => {
            f.plugin_detail.skills.len() == 2
                && f.plugin_detail.skills[0] == f.plugin_detail.skills[1]
        }
        "codex_agent::PluginDetail::connectors" => {
            f.plugin_detail.connectors.len() == 2
                && f.plugin_detail.connectors[0] == f.plugin_detail.connectors[1]
        }
        "codex_agent::PluginDetail::mcp_servers" => {
            exact_strings(&f.plugin_detail.mcp_servers, &["server", "server"])
        }
        "codex_agent::PluginDetail::hook_count" => f.plugin_detail.hook_count == 7,
        "codex_agent::PluginInstallResult::new" => {
            f.plugin_install.connectors_needing_authentication.len() == 2
                && f.plugin_install_sparse
                    .connectors_needing_authentication
                    .is_empty()
        }
        "codex_agent::PluginInstallResult::auth_policy" => {
            f.plugin_install.auth_policy == PluginAuthPolicy::OnUse
        }
        "codex_agent::PluginInstallResult::connectors_needing_authentication" => {
            f.plugin_install.connectors_needing_authentication.len() == 2
                && f.plugin_install.connectors_needing_authentication[0]
                    == f.plugin_install.connectors_needing_authentication[1]
                && f.plugin_install_sparse
                    .connectors_needing_authentication
                    .is_empty()
        }
        "codex_agent::PluginInstallResult::message" => {
            f.plugin_install.message.as_deref() == Some("installed")
                && f.plugin_install_sparse.message.is_none()
        }
        "codex_agent::Skill::new" => {
            f.skill.origin == ResourceOrigin::Workspace
                && f.skill_sparse.origin == ResourceOrigin::Unknown
        }
        "codex_agent::Skill::name" => f.skill.name == "skill",
        "codex_agent::Skill::display_name" => f.skill.display_name == "Skill",
        "codex_agent::Skill::description" => f.skill.description == "skill description",
        "codex_agent::Skill::path" => f.skill.path == "/skill",
        "codex_agent::Skill::scope" => f.skill.scope == SkillScope::Repo,
        "codex_agent::Skill::is_enabled" => f.skill.is_enabled && !f.skill_sparse.is_enabled,
        "codex_agent::Skill::brand_color" => {
            f.skill.brand_color.as_deref() == Some("#000") && f.skill_sparse.brand_color.is_none()
        }
        "codex_agent::Skill::dependencies" => {
            exact_strings(&f.skill.dependencies, &["first", "first", "last"])
                && f.skill_sparse.dependencies.is_empty()
        }
        "codex_agent::Skill::can_uninstall" => {
            f.skill.can_uninstall && !f.skill_sparse.can_uninstall
        }
        "codex_agent::Skill::origin" => {
            f.skill.origin == ResourceOrigin::Workspace
                && f.skill_sparse.origin == ResourceOrigin::Unknown
        }
        "codex_agent::SkillCatalog::new" => {
            f.skill_catalog.skills.len() == 2 && f.skill_catalog_sparse.skills.is_empty()
        }
        "codex_agent::SkillCatalog::skills" => {
            f.skill_catalog.skills.len() == 2
                && f.skill_catalog.skills[0] == f.skill_catalog.skills[1]
                && f.skill_catalog_sparse.skills.is_empty()
        }
        "codex_agent::SkillCatalog::errors" => {
            exact_strings(&f.skill_catalog.errors, &["first", "first", "last"])
                && f.skill_catalog_sparse.errors.is_empty()
        }
        "codex_agent::SkillChunk::new" => f.skill_chunk.total_bytes == 84,
        "codex_agent::SkillChunk::content" => f.skill_chunk.content == "content",
        "codex_agent::SkillChunk::next_offset" => {
            f.skill_chunk.next_offset == Some(42) && f.skill_chunk_sparse.next_offset.is_none()
        }
        "codex_agent::SkillChunk::total_bytes" => f.skill_chunk.total_bytes == 84,
        "codex_agent::HookActivity::new" => {
            f.hook.details.len() == 3 && f.hook_sparse.details.is_empty()
        }
        "codex_agent::HookActivity::id" => f.hook.id == "hook-id",
        "codex_agent::HookActivity::event_name" => f.hook.event_name == "afterTurn",
        "codex_agent::HookActivity::handler_type" => f.hook.handler_type == "command",
        "codex_agent::HookActivity::status" => f.hook.status == HookRunStatus::Completed,
        "codex_agent::HookActivity::status_message" => {
            f.hook.status_message.as_deref() == Some("complete")
                && f.hook_sparse.status_message.is_none()
        }
        "codex_agent::HookActivity::details" => {
            exact_strings(&f.hook.details, &["first", "first", "last"])
                && f.hook_sparse.details.is_empty()
        }
        "codex_agent::TurnProgress::new" => {
            f.turn.plan_progress.is_some() && f.turn_sparse.plan_progress.is_none()
        }
        "codex_agent::TurnProgress::text" => f.turn.text == "text" && f.turn_sparse.text.is_empty(),
        "codex_agent::TurnProgress::commentary" => {
            f.turn.commentary == "commentary" && f.turn_sparse.commentary.is_empty()
        }
        "codex_agent::TurnProgress::reasoning" => {
            f.turn.reasoning == "reasoning" && f.turn_sparse.reasoning.is_empty()
        }
        "codex_agent::TurnProgress::plan" => f.turn.plan == "plan" && f.turn_sparse.plan.is_empty(),
        "codex_agent::TurnProgress::plan_progress" => {
            f.turn.plan_progress.as_ref() == Some(&f.plan_progress)
                && f.turn_sparse.plan_progress.is_none()
        }
        "codex_agent::TurnProgress::shell_output" => {
            f.turn.shell_output == "shell output" && f.turn_sparse.shell_output.is_empty()
        }
        "codex_agent::TurnProgress::shell_exit_code" => {
            f.turn.shell_exit_code == Some(17) && f.turn_sparse.shell_exit_code.is_none()
        }
        "codex_agent::TurnProgress::work_activity" => {
            f.turn.work_activity == Some(WorkActivity::WritingFiles)
                && f.turn_sparse.work_activity.is_none()
        }
        "codex_agent::TurnProgress::hook_activities" => {
            f.turn.hook_activities.len() == 2
                && f.turn.hook_activities[0] == f.turn.hook_activities[1]
                && f.turn_sparse.hook_activities.is_empty()
        }
        "codex_agent::TurnProgress::is_truncated" => {
            f.turn.is_truncated && !f.turn_sparse.is_truncated
        }
        _ => false,
    }
}

fn manifest_path(relative: impl AsRef<Path>) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join(relative)
}

fn exact_list(value: &str) -> Vec<&str> {
    assert!(!value.is_empty(), "empty evidence cell");
    let entries: Vec<_> = value.split(',').collect();
    assert!(
        entries.windows(2).all(|pair| pair[0] < pair[1]),
        "evidence list must be sorted and unique"
    );
    entries
}

#[derive(Default)]
struct BootstrapClaim {
    headers: BTreeSet<String>,
    native_tests: BTreeSet<String>,
}

fn json_string(line: &str) -> Option<&str> {
    let value = line.trim();
    let value = value.strip_prefix('"')?;
    value
        .strip_suffix("\",")
        .or_else(|| value.strip_suffix('"'))
}

fn json_field<'a>(line: &'a str, field: &str) -> Option<&'a str> {
    let value = line.trim().strip_prefix(field)?.trim();
    json_string(value)
}

fn canonical_keys(report: &str) -> BTreeSet<&str> {
    let owners = report
        .split_once("\n    \"owners\": [")
        .expect("canonical report contains owners")
        .1
        .split_once("\n    ],\n    \"targets\": [")
        .expect("canonical report contains targets")
        .0;
    owners
        .lines()
        .filter_map(json_string)
        .filter(|value| value.starts_with("common|owner="))
        .collect()
}

fn bootstrap_claims(report: &str) -> BTreeMap<String, BootstrapClaim> {
    let claims = report
        .split_once("\"claims\": [")
        .expect("bootstrap contains claims")
        .1
        .rsplit_once("\n    ]")
        .expect("bootstrap claims terminate")
        .0;
    let mut result = BTreeMap::new();
    for object in claims.split("\n        {").skip(1) {
        let object = object
            .split_once("\n        }")
            .map_or(object, |pair| pair.0);
        let key = object
            .lines()
            .find_map(|line| json_field(line, "\"capabilityKey\":"))
            .expect("bootstrap capability key")
            .to_owned();
        let mut claim = BootstrapClaim::default();
        let mut array = "";
        for line in object.lines() {
            match line.trim() {
                "\"headerReferences\": [" => array = "header",
                "\"nativeTestIds\": [" => array = "native",
                "]," | "]" => array = "",
                _ => {
                    if let Some(value) = json_string(line) {
                        match array {
                            "header" => {
                                claim.headers.insert(format!("c-header:{value}"));
                            }
                            "native" => {
                                claim.native_tests.insert(format!("cabi-fixture:{value}"));
                            }
                            _ => {}
                        }
                    }
                }
            }
        }
        assert!(
            result.insert(key, claim).is_none(),
            "duplicate bootstrap claim"
        );
    }
    result
}

fn passed_native_tests(report: &str) -> BTreeSet<String> {
    let tests = report
        .split_once("\"nativeTests\": [")
        .expect("bootstrap contains native tests")
        .1
        .split_once("\n    ],\n    \"claims\":")
        .expect("bootstrap native tests terminate before claims")
        .0;
    tests
        .split("\n        {")
        .skip(1)
        .filter_map(|object| {
            let object = object
                .split_once("\n        }")
                .map_or(object, |pair| pair.0);
            let id = object
                .lines()
                .find_map(|line| json_field(line, "\"testId\":"))?;
            let status = object
                .lines()
                .find_map(|line| json_field(line, "\"status\":"))?;
            (status == "passed").then(|| id.to_owned())
        })
        .collect()
}

fn compile_header_references(headers: &BTreeSet<String>, stale: bool) -> bool {
    let output = manifest_path("target/cross-language-evidence");
    std::fs::create_dir_all(&output).expect("create Rust evidence directory");
    let source = output.join(if stale {
        "stale-value-header-evidence.c"
    } else {
        "value-header-evidence.c"
    });
    let object = source.with_extension("o");
    let mut contents = String::from("#include \"codex_agent.h\"\nint main(void) {\n");
    for header in headers {
        if header.starts_with("CODEX_AGENT_") {
            contents.push_str("  (void)(");
            contents.push_str(header);
            contents.push_str(");\n");
        } else if header.ends_with("_t") {
            contents.push_str("  (void)sizeof(");
            contents.push_str(header);
            contents.push_str(");\n");
        } else if header.ends_with(';') {
            contents.push_str("  ");
            contents.push_str(header);
            contents.push('\n');
            contents.push_str("  (void)");
            contents.push_str(
                header
                    .trim_end_matches(';')
                    .split_whitespace()
                    .next_back()
                    .expect("header declaration name"),
            );
            contents.push_str(";\n");
        } else {
            contents.push_str("  (void)&");
            contents.push_str(header);
            contents.push_str(";\n");
        }
    }
    if stale {
        contents.push_str("  (void)&codex_agent_stale_value_evidence;\n");
    }
    contents.push_str("  return 0;\n}\n");
    std::fs::write(&source, contents).expect("write C-header value evidence");
    let result = Command::new(std::env::var_os("CC").unwrap_or_else(|| "cc".into()))
        .arg("-std=c11")
        .arg("-Wall")
        .arg("-Wextra")
        .arg("-Werror")
        .arg("-I")
        .arg(manifest_path("../../native/c-api/include"))
        .arg("-c")
        .arg(source)
        .arg("-o")
        .arg(object)
        .output()
        .expect("compile C-header value evidence");
    result.status.success()
}

fn verify_exact_sync_function_calls() {
    let native = include_str!("../../src/native_values.rs");
    let public = include_str!("../../src/residual_values.rs");
    let expected = [
        (
            "sync_elicitation_response_cancel",
            "codex_agent_elicitation_response_cancel",
        ),
        (
            "sync_elicitation_response_decline",
            "codex_agent_elicitation_response_decline",
        ),
        (
            "sync_elicitation_accepts",
            "codex_agent_elicitation_accepts",
        ),
        ("sync_elicitation_accept", "codex_agent_elicitation_accept"),
        (
            "sync_elicitation_initial_values",
            "codex_agent_elicitation_initial_values",
        ),
        (
            "sync_elicitation_validate",
            "codex_agent_elicitation_validate",
        ),
        ("sync_form_field_accepts", "codex_agent_form_field_accepts"),
        (
            "sync_interaction_state_is_resolving",
            "codex_agent_interaction_state_is_resolving",
        ),
        (
            "sync_interaction_state_pending_for",
            "codex_agent_interaction_state_pending_for",
        ),
        (
            "sync_authorization_url_chat_gpt",
            "codex_agent_authorization_url_chat_gpt",
        ),
        (
            "sync_authorization_url_external",
            "codex_agent_authorization_url_external",
        ),
    ];
    for (helper, symbol) in expected {
        assert!(
            public.contains(helper),
            "public Rust projection is disconnected from {helper}"
        );
        assert!(
            native.contains(&format!("let {symbol}:")),
            "Rust native seam does not resolve exact {symbol}"
        );
        assert!(
            native.contains(&format!("{symbol}(")),
            "Rust native seam does not call exact {symbol}"
        );
    }
    assert!(!native.contains("codex_agent_stale_sync_function"));
    assert!(!public.contains("safe_authorization_url"));
    assert!(!public.contains("validation_reason"));
    assert!(!public.contains("matches_string_format"));
}

const LEAF_SERVICE_OWNERS: [&str; 9] = [
    "CodexAuthentication",
    "CodexConnectors",
    "CodexHooks",
    "CodexIntegrationAuthorization",
    "CodexInteractions",
    "CodexMcpServers",
    "CodexModels",
    "CodexPlugins",
    "CodexSkills",
];

fn leaf_service_owner(capability: &str) -> Option<&str> {
    let owner = capability
        .split("|owner=")
        .nth(1)?
        .split('|')
        .next()?
        .rsplit('/')
        .next()?;
    LEAF_SERVICE_OWNERS.contains(&owner).then_some(owner)
}

fn leaf_service_member<'a>(capability: &'a str, owner: &str) -> Option<&'a str> {
    capability
        .split(&format!("/{owner}."))
        .nth(1)
        .and_then(|value| value.split('|').next())
}

fn rust_service_method(capability: &str, member: &str) -> &'static str {
    if member == "resolve" && capability.contains("AgentPendingApproval") {
        return "resolve_approval";
    }
    if member == "resolve" && capability.contains("AgentPendingElicitation") {
        return "resolve_elicitation";
    }
    match member {
        "isAuthenticated" => "is_authenticated",
        "isAuthenticating" => "is_authenticating",
        "isAuthorizing" => "is_authorizing",
        "isAvailable" => "is_available",
        "openUrl" => "open_url",
        "resolveEffort" => "resolve_effort",
        "resolveServiceTier" => "resolve_service_tier",
        "signOut" => "sign_out",
        "active" => "active",
        "add" => "add",
        "approvals" => "approvals",
        "authenticate" => "authenticate",
        "authorize" => "authorize",
        "cancel" => "cancel",
        "elicitations" => "elicitations",
        "install" => "install",
        "list" => "list",
        "read" => "read",
        "remove" => "remove",
        "resolve" => "resolve",
        "state" => "state",
        "trust" => "trust",
        "uninstall" => "uninstall",
        _ => panic!("unmapped leaf-service member: {member}"),
    }
}

fn expected_service_scenarios(capability: &str, member: &str) -> BTreeSet<&'static str> {
    let mut scenarios = BTreeSet::from(["parent-child-ownership", "value-conversion"]);
    if capability.contains("|kind=function|") {
        scenarios.insert("async-success");
    }
    if capability.contains("StateFlow") {
        scenarios.extend([
            "state-current-value",
            "state-subsequent-value",
            "subscription-cancellation",
            "terminal-delivery",
        ]);
    }
    if capability.contains("kotlin.collections") {
        scenarios.insert("collection-immutability-ordering");
    }
    if capability.contains('?') {
        scenarios.insert("nullability");
    }
    if member == "isAvailable" {
        scenarios.insert("repeated-close-dispose");
    }
    if leaf_service_owner(capability) == Some("CodexInteractions") {
        scenarios.insert("identity");
        if matches!(member, "openUrl" | "resolve") {
            scenarios.insert("cancellation");
        }
    }
    if member == "openUrl" {
        scenarios.extend(["async-failure", "structured-failure"]);
    }
    scenarios
}

fn service_method_is_public(source: &str, owner: &str, method: &str) -> bool {
    let marker = format!("impl {owner} {{");
    source.split(&marker).skip(1).any(|section| {
        let section = section.split_once("\nimpl ").map_or(section, |pair| pair.0);
        section.contains(&format!("pub fn {method}("))
            || section.contains(&format!("pub const fn {method}("))
    })
}

fn rust_item(source: &str, marker: &str, closing_indent: &str) -> Option<String> {
    let start = source.find(marker)?;
    let tail = &source[start..];
    let end = tail.find(&format!("\n{closing_indent}}}"))? + closing_indent.len() + 2;
    Some(tail[..end].to_owned())
}

fn reachable_service_source(source: &str, owner: &str, method: &str) -> Option<String> {
    let production = source
        .split("\n#[cfg(test)]\nmod tests")
        .next()
        .unwrap_or(source);
    let marker = format!("impl {owner} {{");
    let owner_source = production
        .split(&marker)
        .skip(1)
        .find(|section| section.contains(&format!("    pub fn {method}(")))?;
    let mut reachable = rust_item(owner_source, &format!("    pub fn {method}("), "    ")?;
    let private_functions = production
        .lines()
        .filter_map(|line| {
            let signature = line
                .strip_prefix("fn ")
                .or_else(|| line.strip_prefix("unsafe fn "))?;
            let name = signature.split(['(', '<']).next()?.trim();
            rust_item(production, &format!("\n{line}"), "").map(|item| (name.to_owned(), item))
        })
        .collect::<BTreeMap<_, _>>();
    let mut included = BTreeSet::new();
    loop {
        let next = private_functions.iter().find(|(name, _)| {
            !included.contains(*name) && contains_rust_identifier(&reachable, name)
        });
        let Some((name, item)) = next else {
            break;
        };
        included.insert(name.clone());
        reachable.push('\n');
        reachable.push_str(item);
    }
    Some(reachable)
}

fn contains_rust_identifier(source: &str, identifier: &str) -> bool {
    source.match_indices(identifier).any(|(offset, _)| {
        let before = source[..offset].chars().next_back();
        let after = source[offset + identifier.len()..].chars().next();
        let boundary = |character: Option<char>| {
            character.is_none_or(|value| !(value.is_ascii_alphanumeric() || value == '_'))
        };
        boundary(before) && boundary(after)
    })
}

fn service_reference_is_connected(
    reference: &str,
    owner: &str,
    method: &str,
    service_source: &str,
    async_source: &str,
    ffi_source: &str,
) -> bool {
    if reference == "codex_agent_operation_result" {
        return ffi_source
            .contains("operation_result: OperationResult => \"codex_agent_operation_result\"")
            && async_source.contains(".api.operation_result)(");
    }
    reachable_service_source(service_source, owner, method)
        .is_some_and(|source| source.contains(&format!("b\"{reference}\\0\"")))
}

fn validate_service_rows(
    rows: &[Vec<&str>],
    bootstrap_claims: &BTreeMap<String, BootstrapClaim>,
    passed_tests: &BTreeSet<String>,
    service_source: &str,
    async_source: &str,
    ffi_source: &str,
) -> Result<(), String> {
    if rows.len() != 42 || rows.iter().any(|row| row.len() != 5) {
        return Err("exactly 42 five-column leaf-service claims are required".into());
    }
    let keys = rows.iter().map(|row| row[0]).collect::<Vec<_>>();
    if !keys.windows(2).all(|pair| pair[0] < pair[1]) {
        return Err("leaf-service capability keys must be sorted and unique".into());
    }
    let canonical = bootstrap_claims
        .keys()
        .filter(|key| leaf_service_owner(key).is_some())
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    if keys.iter().copied().collect::<BTreeSet<_>>() != canonical {
        return Err("leaf-service claims contain a stale, missing, or duplicate key".into());
    }

    for (index, row) in rows.iter().enumerate() {
        let capability = row[0];
        let owner = leaf_service_owner(capability).ok_or("non-service capability")?;
        let member = leaf_service_member(capability, owner).ok_or("missing service member")?;
        let method = rust_service_method(capability, member);
        if exact_list(row[1]) != [format!("codex_agent::{owner}::{method}").as_str()] {
            return Err(format!("stale Rust public projection: {capability}"));
        }
        if exact_list(row[2]) != [format!("rust.service:{index:03}").as_str()] {
            return Err(format!("stale Rust service executed-test ID: {capability}"));
        }
        let claim = &bootstrap_claims[capability];
        let mut expected_evidence = claim.headers.clone();
        expected_evidence.extend(claim.native_tests.iter().cloned());
        expected_evidence.insert(format!("rust-analyzer-service:{index:03}"));
        if exact_list(row[3])
            .into_iter()
            .map(str::to_owned)
            .collect::<BTreeSet<_>>()
            != expected_evidence
        {
            return Err(format!(
                "stale exact compiler/reference evidence: {capability}"
            ));
        }
        if exact_list(row[4]).into_iter().collect::<BTreeSet<_>>()
            != expected_service_scenarios(capability, member)
        {
            return Err(format!("stale semantic scenarios: {capability}"));
        }
        if !service_method_is_public(service_source, owner, method) {
            return Err(format!(
                "missing compiled public Rust method: {owner}::{method}"
            ));
        }
        for reference in &claim.headers {
            let reference = reference.trim_start_matches("c-header:");
            if !service_reference_is_connected(
                reference,
                owner,
                method,
                service_source,
                async_source,
                ffi_source,
            ) {
                return Err(format!(
                    "public Rust projection is disconnected from exact {reference}: {capability}"
                ));
            }
        }
        if !claim
            .native_tests
            .iter()
            .all(|test| passed_tests.contains(test.trim_start_matches("cabi-fixture:")))
        {
            return Err(format!("canonical C behavior did not pass: {capability}"));
        }
    }
    Ok(())
}

fn conversation_owner(capability: &str) -> Option<&str> {
    let owner = capability
        .split("|owner=")
        .nth(1)?
        .split('|')
        .next()?
        .rsplit('/')
        .next()?;
    matches!(owner, "CodexConversation" | "CodexConversations").then_some(owner)
}

fn rust_conversation_method(capability: &str, owner: &str) -> &'static str {
    let member = leaf_service_member(capability, owner).expect("conversation member");
    if member == "send" && capability.contains("AgentTurnRequest") {
        return "send_request";
    }
    match member {
        "active" => "active",
        "activeTurnProgress" => "active_turn_progress",
        "cancelTurn" => "cancel_turn",
        "canCancelTurn" => "can_cancel_turn",
        "canReload" => "can_reload",
        "canRunShellCommand" => "can_run_shell_command",
        "canStartTurn" => "can_start_turn",
        "close" => "close",
        "currentMessages" => "current_messages",
        "delete" => "delete",
        "isTurnActive" => "is_turn_active",
        "list" => "list",
        "open" => "open",
        "read" => "read",
        "reload" => "reload",
        "rename" => "rename",
        "runShellCommand" => "run_shell_command",
        "send" => "send",
        "state" => "state",
        _ => panic!("unmapped conversation member: {member}"),
    }
}

fn expected_conversation_scenarios(capability: &str, method: &str) -> BTreeSet<&'static str> {
    let mut scenarios = BTreeSet::from(["parent-child-ownership", "value-conversion"]);
    if capability.contains("|kind=function|") {
        scenarios.insert("async-success");
    }
    if capability.contains("StateFlow") {
        scenarios.extend([
            "state-current-value",
            "state-subsequent-value",
            "subscription-cancellation",
            "terminal-delivery",
        ]);
    }
    if capability.contains("kotlin.collections") {
        scenarios.insert("collection-immutability-ordering");
    }
    if capability.contains('?') {
        scenarios.insert("nullability");
    }
    if matches!(method, "active" | "open") {
        scenarios.insert("identity");
    }
    if method == "close" {
        scenarios.insert("repeated-close-dispose");
    }
    scenarios
}

fn validate_conversation_rows(
    rows: &[Vec<&str>],
    bootstrap_claims: &BTreeMap<String, BootstrapClaim>,
    passed_tests: &BTreeSet<String>,
    source: &str,
    async_source: &str,
    ffi_source: &str,
) -> Result<(), String> {
    if rows.len() != 20 || rows.iter().any(|row| row.len() != 5) {
        return Err("exactly 20 five-column conversation claims are required".into());
    }
    let canonical = bootstrap_claims
        .keys()
        .filter(|key| conversation_owner(key).is_some())
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    if rows.iter().map(|row| row[0]).collect::<BTreeSet<_>>() != canonical {
        return Err("conversation claims contain a stale, missing, or duplicate key".into());
    }
    let mut indexed = rows.iter().collect::<Vec<_>>();
    indexed.sort_by_key(|row| row[2]);
    for (index, row) in indexed.into_iter().enumerate() {
        let capability = row[0];
        let owner = conversation_owner(capability).ok_or("non-conversation capability")?;
        let method = rust_conversation_method(capability, owner);
        if exact_list(row[1]) != [format!("codex_agent::{owner}::{method}").as_str()] {
            return Err(format!("stale Rust conversation projection: {capability}"));
        }
        if exact_list(row[2]) != [format!("rust.conversation:{index:03}").as_str()] {
            return Err(format!("stale Rust conversation test ID: {capability}"));
        }
        let claim = &bootstrap_claims[capability];
        let mut expected_evidence = claim.headers.clone();
        expected_evidence.extend(claim.native_tests.iter().cloned());
        expected_evidence.insert(format!("rust-analyzer-conversation:{index:03}"));
        if exact_list(row[3])
            .into_iter()
            .map(str::to_owned)
            .collect::<BTreeSet<_>>()
            != expected_evidence
        {
            return Err(format!("stale conversation evidence: {capability}"));
        }
        if exact_list(row[4]).into_iter().collect::<BTreeSet<_>>()
            != expected_conversation_scenarios(capability, method)
        {
            return Err(format!("stale conversation scenarios: {capability}"));
        }
        if !service_method_is_public(source, owner, method) {
            return Err(format!(
                "missing compiled public Rust method: {owner}::{method}"
            ));
        }
        for reference in &claim.headers {
            let reference = reference.trim_start_matches("c-header:");
            if !service_reference_is_connected(
                reference,
                owner,
                method,
                source,
                async_source,
                ffi_source,
            ) {
                return Err(format!(
                    "conversation projection disconnected from {reference}: {capability}"
                ));
            }
        }
        if !claim
            .native_tests
            .iter()
            .all(|test| passed_tests.contains(test.trim_start_matches("cabi-fixture:")))
        {
            return Err(format!(
                "canonical C conversation behavior did not pass: {capability}"
            ));
        }
    }
    Ok(())
}

fn agent_owner(capability: &str) -> Option<&str> {
    capability
        .contains("|owner=io.github.codex_agent_labs.codexagent.agent/CodexAgent|")
        .then_some("CodexAgent")
}

fn rust_agent_method(capability: &str) -> &'static str {
    match leaf_service_member(capability, "CodexAgent").expect("agent member") {
        "authentication" => "authentication",
        "connectors" => "connectors",
        "conversations" => "conversations",
        "hooks" => "hooks",
        "integrationAuthorization" => "integration_authorization",
        "interactions" => "interactions",
        "mcpServers" => "mcp_servers",
        "models" => "models",
        "plugins" => "plugins",
        "skills" => "skills",
        "workspace" => "workspace",
        member => panic!("unmapped Agent member: {member}"),
    }
}

fn expected_agent_scenarios(method: &str) -> BTreeSet<&'static str> {
    let mut scenarios = BTreeSet::from(["parent-child-ownership", "value-conversion"]);
    if method != "workspace" {
        scenarios.insert("identity");
    }
    scenarios
}

fn validate_agent_rows(
    rows: &[Vec<&str>],
    bootstrap_claims: &BTreeMap<String, BootstrapClaim>,
    passed_tests: &BTreeSet<String>,
    source: &str,
    async_source: &str,
    ffi_source: &str,
) -> Result<(), String> {
    if rows.len() != 11 || rows.iter().any(|row| row.len() != 5) {
        return Err("exactly 11 five-column Agent claims are required".into());
    }
    let canonical = bootstrap_claims
        .keys()
        .filter(|key| agent_owner(key).is_some())
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    if rows.iter().map(|row| row[0]).collect::<BTreeSet<_>>() != canonical {
        return Err("Agent claims contain a stale, missing, or duplicate key".into());
    }
    let mut indexed = rows.iter().collect::<Vec<_>>();
    indexed.sort_by_key(|row| row[2]);
    for (index, row) in indexed.into_iter().enumerate() {
        let capability = row[0];
        let owner = agent_owner(capability).ok_or("non-Agent capability")?;
        let method = rust_agent_method(capability);
        if exact_list(row[1]) != [format!("codex_agent::{owner}::{method}").as_str()] {
            return Err(format!("stale Rust Agent projection: {capability}"));
        }
        if exact_list(row[2]) != [format!("rust.agent:{index:03}").as_str()] {
            return Err(format!("stale Rust Agent test ID: {capability}"));
        }
        let claim = &bootstrap_claims[capability];
        let mut expected_evidence = claim.headers.clone();
        expected_evidence.extend(claim.native_tests.iter().cloned());
        expected_evidence.insert(format!("rust-analyzer-agent:{index:03}"));
        if exact_list(row[3])
            .into_iter()
            .map(str::to_owned)
            .collect::<BTreeSet<_>>()
            != expected_evidence
        {
            return Err(format!("stale Agent evidence: {capability}"));
        }
        if exact_list(row[4]).into_iter().collect::<BTreeSet<_>>()
            != expected_agent_scenarios(method)
        {
            return Err(format!("stale Agent scenarios: {capability}"));
        }
        if !service_method_is_public(source, owner, method) {
            return Err(format!(
                "missing compiled public Rust method: {owner}::{method}"
            ));
        }
        for reference in &claim.headers {
            let reference = reference.trim_start_matches("c-header:");
            if !service_reference_is_connected(
                reference,
                owner,
                method,
                source,
                async_source,
                ffi_source,
            ) {
                return Err(format!(
                    "Agent projection disconnected from {reference}: {capability}"
                ));
            }
        }
        if !claim
            .native_tests
            .iter()
            .all(|test| passed_tests.contains(test.trim_start_matches("cabi-fixture:")))
        {
            return Err(format!(
                "canonical C Agent behavior did not pass: {capability}"
            ));
        }
    }
    Ok(())
}

fn host_owner(capability: &str) -> Option<&'static str> {
    if capability
        .contains("|owner=io.github.codex_agent_labs.codexagent.agent/CodexHostState.Ready|")
    {
        Some("HostStateReady")
    } else if capability.contains("|owner=io.github.codex_agent_labs.codexagent.agent/CodexHost|") {
        Some("CodexHost")
    } else {
        None
    }
}

fn expected_host_symbols(index: usize) -> Vec<&'static str> {
    match index {
        0 => vec!["codex_agent::HostStateReady::new"],
        1 => vec!["codex_agent::HostStateReady::agent"],
        2 => vec!["codex_agent::CodexHost::create"],
        3 => vec!["codex_agent::CodexHost::close"],
        4 => vec!["codex_agent::CodexHost::select_workspace"],
        5 => vec!["codex_agent::CodexHost::start"],
        6 => vec![
            "codex_agent::CodexHost::state",
            "codex_agent::CodexHost::states",
        ],
        _ => panic!("unknown Host/Ready index: {index}"),
    }
}

fn expected_host_scenarios(index: usize) -> BTreeSet<&'static str> {
    match index {
        0 | 1 => BTreeSet::from(["identity", "parent-child-ownership", "value-conversion"]),
        2 => BTreeSet::from(["parent-child-ownership", "value-conversion"]),
        3 => BTreeSet::from([
            "async-failure",
            "async-success",
            "cancellation",
            "parent-child-ownership",
            "repeated-close-dispose",
            "structured-failure",
            "value-conversion",
        ]),
        4 | 5 => BTreeSet::from([
            "async-failure",
            "async-success",
            "cancellation",
            "parent-child-ownership",
            "structured-failure",
            "value-conversion",
        ]),
        6 => BTreeSet::from([
            "identity",
            "parent-child-ownership",
            "state-current-value",
            "state-subsequent-value",
            "subscription-cancellation",
            "terminal-delivery",
            "value-conversion",
        ]),
        _ => panic!("unknown Host/Ready index: {index}"),
    }
}

fn host_production_roots(index: usize) -> &'static [(&'static str, &'static str)] {
    match index {
        0 | 1 => &[("CodexHost", "state")],
        2 => &[("CodexHost", "create_with_library")],
        3 => &[("CodexHost", "close")],
        4 => &[("CodexHost", "select_workspace")],
        5 => &[("CodexHost", "start")],
        6 => &[("CodexHost", "state"), ("CodexHost", "states")],
        _ => panic!("unknown Host/Ready index: {index}"),
    }
}

fn host_reference_is_connected(
    reference: &str,
    index: usize,
    source: &str,
    async_source: &str,
    ffi_source: &str,
) -> bool {
    if reference == "CODEX_AGENT_HOST_STATE_READY" {
        return index == 0 && source.contains("Ready = 4");
    }
    if reference == "codex_agent_host_options_t" {
        return index == 2
            && reachable_service_source(source, "CodexHost", "create_with_library")
                .is_some_and(|root| root.contains("ffi::HostOptions"));
    }
    host_production_roots(index).iter().any(|(owner, method)| {
        service_reference_is_connected(reference, owner, method, source, async_source, ffi_source)
    })
}

fn validate_host_rows(
    rows: &[Vec<&str>],
    bootstrap_claims: &BTreeMap<String, BootstrapClaim>,
    passed_tests: &BTreeSet<String>,
    source: &str,
    async_source: &str,
    ffi_source: &str,
) -> Result<(), String> {
    if rows.len() != 7 || rows.iter().any(|row| row.len() != 5) {
        return Err("exactly seven five-column Host/Ready claims are required".into());
    }
    let canonical = bootstrap_claims
        .keys()
        .filter(|key| host_owner(key).is_some())
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    if rows.iter().map(|row| row[0]).collect::<BTreeSet<_>>() != canonical {
        return Err("Host/Ready claims contain a stale, missing, or duplicate key".into());
    }
    let mut indexed = rows.iter().collect::<Vec<_>>();
    indexed.sort_by_key(|row| row[2]);
    for (index, row) in indexed.into_iter().enumerate() {
        let capability = row[0];
        let symbols = exact_list(row[1]);
        if symbols != expected_host_symbols(index) {
            return Err(format!("stale Rust Host/Ready projection: {capability}"));
        }
        for symbol in &symbols {
            let (owner, method) = symbol
                .trim_start_matches("codex_agent::")
                .split_once("::")
                .ok_or("malformed Host/Ready public symbol")?;
            if !service_method_is_public(source, owner, method) {
                return Err(format!("missing compiled public Rust method: {symbol}"));
            }
        }
        if exact_list(row[2]) != [format!("rust.host:{index:03}").as_str()] {
            return Err(format!("stale Rust Host/Ready test ID: {capability}"));
        }
        let claim = &bootstrap_claims[capability];
        let mut expected_evidence = claim.headers.clone();
        expected_evidence.extend(claim.native_tests.iter().cloned());
        expected_evidence.insert(format!("rust-analyzer-host:{index:03}"));
        if exact_list(row[3])
            .into_iter()
            .map(str::to_owned)
            .collect::<BTreeSet<_>>()
            != expected_evidence
        {
            return Err(format!("stale Host/Ready evidence: {capability}"));
        }
        if exact_list(row[4]).into_iter().collect::<BTreeSet<_>>() != expected_host_scenarios(index)
        {
            return Err(format!("stale Host/Ready scenarios: {capability}"));
        }
        for reference in &claim.headers {
            let reference = reference.trim_start_matches("c-header:");
            if !host_reference_is_connected(reference, index, source, async_source, ffi_source) {
                return Err(format!(
                    "Host/Ready projection disconnected from {reference}: {capability}"
                ));
            }
        }
        if !claim
            .native_tests
            .iter()
            .all(|test| passed_tests.contains(test.trim_start_matches("cabi-fixture:")))
        {
            return Err(format!(
                "canonical C Host/Ready behavior did not pass: {capability}"
            ));
        }
    }
    Ok(())
}

#[cfg(all(target_os = "macos", target_arch = "aarch64"))]
fn execute_real_sdk_null_boundaries(
    rows: &[Vec<&str>],
    bootstrap_claims: &BTreeMap<String, BootstrapClaim>,
) {
    let header_path = manifest_path("../../native/c-api/include/codex_agent.h");
    let header = std::fs::read_to_string(&header_path).expect("read exact public C header");
    let library = manifest_path("../../build/bin/macosArm64/releaseShared/libcodex_agent.dylib");
    assert!(
        library.is_file(),
        "real macOS Arm64 release SDK is required"
    );
    let symbols = rows
        .iter()
        .flat_map(|row| bootstrap_claims[row[0]].headers.iter())
        .map(|reference| reference.trim_start_matches("c-header:"))
        .filter(|reference| reference.starts_with("codex_agent_") && !reference.ends_with("_t"))
        .collect::<BTreeSet<_>>();

    let output = manifest_path("target/cross-language-evidence");
    std::fs::create_dir_all(&output).expect("create Rust service evidence directory");
    let source = output.join("real-sdk-leaf-service-null-boundary.c");
    let executable = output.join("real-sdk-leaf-service-null-boundary");
    let mut program = String::from(
        "#include <stdio.h>\n#include \"codex_agent.h\"\nint main(void) {\n  int failures = 0;\n",
    );
    for symbol in &symbols {
        let declaration = header
            .split_once(&format!("{symbol}("))
            .unwrap_or_else(|| panic!("missing exact C declaration: {symbol}"))
            .1
            .split_once(");")
            .expect("C declaration terminator")
            .0;
        let count = if declaration.trim() == "void" {
            0
        } else {
            declaration.split(',').count()
        };
        let arguments = std::iter::repeat_n("0", count)
            .collect::<Vec<_>>()
            .join(", ");
        writeln!(
            program,
            "  codex_agent_status_t status_{symbol} = {symbol}({arguments});\n  printf(\"{symbol}\\t%d\\n\", (int)status_{symbol});\n  failures += status_{symbol} == CODEX_AGENT_STATUS_OK;"
        )
        .expect("write real-SDK call");
    }
    program.push_str("  return failures == 0 ? 0 : 1;\n}\n");
    std::fs::write(&source, program).expect("write exact real-SDK boundary source");
    let library_directory = library.parent().expect("SDK library directory");
    let compile = Command::new(std::env::var_os("CC").unwrap_or_else(|| "cc".into()))
        .args(["-std=c11", "-Wall", "-Wextra", "-Werror"])
        .arg(&source)
        .arg("-I")
        .arg(header_path.parent().expect("header directory"))
        .arg("-L")
        .arg(library_directory)
        .arg("-lcodex_agent")
        .arg(format!("-Wl,-rpath,{}", library_directory.display()))
        .arg("-o")
        .arg(&executable)
        .output()
        .expect("compile exact real-SDK boundary executable");
    assert!(
        compile.status.success(),
        "real-SDK boundary compile failed:\n{}",
        String::from_utf8_lossy(&compile.stderr)
    );
    let run = Command::new(&executable)
        .output()
        .expect("execute exact real-SDK null boundary");
    assert!(
        run.status.success(),
        "real-SDK boundary must fail closed for every exact symbol:\n{}\n{}",
        String::from_utf8_lossy(&run.stdout),
        String::from_utf8_lossy(&run.stderr)
    );
    let statuses = String::from_utf8(run.stdout)
        .expect("real-SDK boundary output is UTF-8")
        .lines()
        .map(|line| {
            let (symbol, status) = line.split_once('\t').expect("symbol/status boundary row");
            let status = status.parse::<i32>().expect("numeric boundary status");
            assert_ne!(status, ffi_status_ok(), "{symbol} unexpectedly succeeded");
            (symbol.to_owned(), status)
        })
        .collect::<BTreeMap<_, _>>();
    assert_eq!(
        statuses.keys().map(String::as_str).collect::<BTreeSet<_>>(),
        symbols
    );
    let mut receipt = String::from("capabilityKey\theaderReference\tboundaryExecution\n");
    for row in rows {
        for reference in &bootstrap_claims[row[0]].headers {
            let symbol = reference.trim_start_matches("c-header:");
            if !symbol.starts_with("codex_agent_") || symbol.ends_with("_t") {
                continue;
            }
            writeln!(
                receipt,
                "{}\t{}\tfail-closed-null-boundary:{}",
                row[0], symbol, statuses[symbol]
            )
            .expect("write real-SDK boundary receipt");
        }
    }
    std::fs::write(
        output.join("real-sdk-leaf-service-null-boundary.tsv"),
        receipt,
    )
    .expect("write exact real-SDK boundary receipt");
}

#[cfg(all(target_os = "macos", target_arch = "aarch64"))]
const fn ffi_status_ok() -> i32 {
    0
}

#[cfg(not(all(target_os = "macos", target_arch = "aarch64")))]
fn execute_real_sdk_null_boundaries(_: &[Vec<&str>], _: &BTreeMap<String, BootstrapClaim>) {}

pub fn verify_and_execute(rows: &[Vec<&str>]) -> Evidence {
    assert_eq!(rows.len(), 556, "exact combined Rust claim count");
    verify_exact_sync_function_calls();
    let canonical_report = std::fs::read_to_string(manifest_path(
        "../../../codex-agent-core/build/reports/cross-language-api/canonical-api.json",
    ))
    .expect("read canonical compiler report");
    let canonical_keys = canonical_keys(&canonical_report);
    let bootstrap_report = std::fs::read_to_string(manifest_path(
        "../../build/reports/cross-language-api/c-abi/bootstrap-evidence.json",
    ))
    .expect("read canonical C ABI evidence");
    let bootstrap_claims = bootstrap_claims(&bootstrap_report);
    let passed_tests = passed_native_tests(&bootstrap_report);
    let service_source = format!(
        "{}\n{}",
        std::fs::read_to_string(manifest_path("src/lib.rs"))
            .expect("read production Rust conversation projections"),
        std::fs::read_to_string(manifest_path("src/services.rs"))
            .expect("read production Rust service projections")
    );
    let async_source = std::fs::read_to_string(manifest_path("src/async_runtime.rs"))
        .expect("read production Rust async projection");
    let ffi_source = std::fs::read_to_string(manifest_path("src/ffi.rs"))
        .expect("read production Rust C loader");

    let f = fixtures();
    let residual_f = super::residual_behavior::fixtures();
    let mut owners = BTreeSet::new();
    let mut headers = BTreeSet::new();
    let mut compiler_symbols: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    let mut executed = BTreeSet::new();
    let mut value_count = 0;
    let mut residual_count = 0;
    let mut function_count = 0;
    let mut residual_keys = BTreeSet::new();
    let mut function_keys = BTreeSet::new();
    let mut prior_keys = BTreeSet::new();
    let mut service_rows = Vec::new();
    let mut conversation_rows = Vec::new();
    let mut agent_rows = Vec::new();
    let mut host_rows = Vec::new();
    for row in rows {
        assert_eq!(row.len(), 5, "exact five-column claim");
        assert!(
            canonical_keys.contains(row[0]),
            "noncanonical capability: {}",
            row[0]
        );
        let symbols = exact_list(row[1]);
        let tests = exact_list(row[2]);
        let evidence = exact_list(row[3]);
        let scenarios = exact_list(row[4]);
        if tests[0] == "rust.host:006" {
            assert_eq!(symbols.len(), 2, "current and stream Host state symbols");
        } else {
            assert_eq!(symbols.len(), 1, "one exact Rust public symbol");
        }
        assert_eq!(tests.len(), 1, "one distinct executed Rust test");
        assert!(executed.insert(tests[0].to_owned()), "duplicate test ID");
        for id in &evidence {
            compiler_symbols
                .entry((*id).to_owned())
                .or_default()
                .insert(symbols[0].to_owned());
        }
        if row[0].contains("|kind=enum-entry|") {
            assert!(tests[0].starts_with("rust.enum."));
            prior_keys.insert(row[0].to_owned());
            continue;
        }
        if tests[0].starts_with("rust.service:") {
            service_rows.push(row.clone());
            let canonical_claim = &bootstrap_claims[row[0]];
            headers.extend(
                canonical_claim
                    .headers
                    .iter()
                    .map(|reference| reference.trim_start_matches("c-header:").to_owned()),
            );
            continue;
        }
        if tests[0].starts_with("rust.conversation:") {
            conversation_rows.push(row.clone());
            let canonical_claim = &bootstrap_claims[row[0]];
            headers.extend(
                canonical_claim
                    .headers
                    .iter()
                    .map(|reference| reference.trim_start_matches("c-header:").to_owned()),
            );
            continue;
        }
        if tests[0].starts_with("rust.agent:") {
            agent_rows.push(row.clone());
            let canonical_claim = &bootstrap_claims[row[0]];
            headers.extend(
                canonical_claim
                    .headers
                    .iter()
                    .map(|reference| reference.trim_start_matches("c-header:").to_owned()),
            );
            continue;
        }
        if tests[0].starts_with("rust.host:") {
            host_rows.push(row.clone());
            let canonical_claim = &bootstrap_claims[row[0]];
            headers.extend(
                canonical_claim
                    .headers
                    .iter()
                    .map(|reference| reference.trim_start_matches("c-header:").to_owned()),
            );
            continue;
        }
        value_count += 1;
        if tests[0].starts_with("rust.function:") {
            function_count += 1;
            function_keys.insert(row[0].to_owned());
            let expected_scenarios: &[&str] = match tests[0] {
                "rust.function:003" | "rust.function:004" | "rust.function:005"
                | "rust.function:008" => &["collection-immutability-ordering", "value-conversion"],
                "rust.function:006" => &["nullability", "value-conversion"],
                _ => &["value-conversion"],
            };
            assert_eq!(scenarios, expected_scenarios);
            assert!(
                super::residual_behavior::exercise(symbols[0], tests[0], &residual_f),
                "{} failed",
                tests[0]
            );
        } else if tests[0].starts_with("rust.residual:") {
            residual_count += 1;
            residual_keys.insert(row[0].to_owned());
            assert!(
                super::residual_behavior::exercise(symbols[0], tests[0], &residual_f),
                "{} failed",
                tests[0]
            );
        } else {
            prior_keys.insert(row[0].to_owned());
            assert!(exercise(symbols[0], &f), "{} failed", tests[0]);
        }
        let owner = row[0]
            .split("|owner=")
            .nth(1)
            .and_then(|value| value.split('|').next())
            .expect("claim owner");
        owners.insert(owner);
        let canonical_claim = &bootstrap_claims[row[0]];
        let expected_headers = &canonical_claim.headers;
        let expected_native = &canonical_claim.native_tests;
        let actual_headers: BTreeSet<_> = evidence
            .iter()
            .filter(|id| id.starts_with("c-header:"))
            .map(|id| (*id).to_owned())
            .collect();
        let actual_native: BTreeSet<_> = evidence
            .iter()
            .filter(|id| id.starts_with("cabi-fixture:"))
            .map(|id| (*id).to_owned())
            .collect();
        assert_eq!(&actual_headers, expected_headers, "stale C-header evidence");
        assert_eq!(
            &actual_native, expected_native,
            "stale native-test evidence"
        );
        for id in actual_headers {
            headers.insert(id.trim_start_matches("c-header:").to_owned());
        }
        for id in actual_native {
            assert!(
                passed_tests.contains(id.trim_start_matches("cabi-fixture:")),
                "native evidence did not pass"
            );
        }
    }
    assert_eq!(value_count, 366, "exact non-enum capability count");
    assert_eq!(residual_count, 175, "exact residual capability count");
    assert_eq!(function_count, 11, "exact synchronous value-function count");
    assert_eq!(owners.len(), 79, "exact non-enum owner count");
    validate_service_rows(
        &service_rows,
        &bootstrap_claims,
        &passed_tests,
        &service_source,
        &async_source,
        &ffi_source,
    )
    .expect("exact Rust leaf-service parity");
    validate_conversation_rows(
        &conversation_rows,
        &bootstrap_claims,
        &passed_tests,
        &service_source,
        &async_source,
        &ffi_source,
    )
    .expect("exact Rust conversation parity");
    validate_agent_rows(
        &agent_rows,
        &bootstrap_claims,
        &passed_tests,
        &service_source,
        &async_source,
        &ffi_source,
    )
    .expect("exact Rust Agent parity");
    validate_host_rows(
        &host_rows,
        &bootstrap_claims,
        &passed_tests,
        &service_source,
        &async_source,
        &ffi_source,
    )
    .expect("exact Rust Host/Ready parity");
    let missing_host = host_rows[..host_rows.len() - 1].to_vec();
    assert!(
        validate_host_rows(
            &missing_host,
            &bootstrap_claims,
            &passed_tests,
            &service_source,
            &async_source,
            &ffi_source,
        )
        .is_err(),
        "missing Host/Ready claim must fail closed"
    );
    let mut duplicate_host = missing_host;
    duplicate_host.push(host_rows[host_rows.len() - 2].clone());
    assert!(
        validate_host_rows(
            &duplicate_host,
            &bootstrap_claims,
            &passed_tests,
            &service_source,
            &async_source,
            &ffi_source,
        )
        .is_err(),
        "duplicate Host/Ready claim must fail closed"
    );
    for (column, stale) in [
        (0, "removed"),
        (1, "codex_agent::Fallback::local"),
        (2, "rust.host:999"),
        (3, "rust-analyzer-host:999"),
        (4, "value-conversion"),
    ] {
        let mut candidate = host_rows.clone();
        candidate[0][column] = stale;
        assert!(
            validate_host_rows(
                &candidate,
                &bootstrap_claims,
                &passed_tests,
                &service_source,
                &async_source,
                &ffi_source,
            )
            .is_err(),
            "stale Host/Ready evidence column {column} must fail closed"
        );
    }
    let disconnected_host_source = service_source.replace(
        "b\"codex_agent_host_create\\0\"",
        "b\"codex_agent_fallback_local\\0\"",
    );
    assert!(
        validate_host_rows(
            &host_rows,
            &bootstrap_claims,
            &passed_tests,
            &disconnected_host_source,
            &async_source,
            &ffi_source,
        )
        .is_err(),
        "disconnected claimed Host C call must fail closed"
    );
    assert!(
        !host_reference_is_connected(
            "codex_agent_host_start",
            3,
            &service_source,
            &async_source,
            &ffi_source,
        ),
        "a Host symbol reachable only from another public method must fail closed"
    );
    let missing_agent = agent_rows[..agent_rows.len() - 1].to_vec();
    assert!(
        validate_agent_rows(
            &missing_agent,
            &bootstrap_claims,
            &passed_tests,
            &service_source,
            &async_source,
            &ffi_source,
        )
        .is_err(),
        "missing Agent claim must fail closed"
    );
    let mut duplicate_agent = missing_agent;
    duplicate_agent.push(agent_rows[agent_rows.len() - 2].clone());
    assert!(
        validate_agent_rows(
            &duplicate_agent,
            &bootstrap_claims,
            &passed_tests,
            &service_source,
            &async_source,
            &ffi_source,
        )
        .is_err(),
        "duplicate Agent claim must fail closed"
    );
    for (column, stale) in [
        (0, "removed"),
        (1, "codex_agent::Fallback::local"),
        (2, "rust.agent:999"),
        (3, "rust-analyzer-agent:999"),
        (4, "value-conversion"),
    ] {
        let mut candidate = agent_rows.clone();
        candidate[0][column] = stale;
        assert!(
            validate_agent_rows(
                &candidate,
                &bootstrap_claims,
                &passed_tests,
                &service_source,
                &async_source,
                &ffi_source,
            )
            .is_err(),
            "stale Agent evidence column {column} must fail closed"
        );
    }
    let first_agent_reference = bootstrap_claims[agent_rows[0][0]]
        .headers
        .iter()
        .next()
        .expect("first Agent C reference")
        .trim_start_matches("c-header:");
    let disconnected_agent_source = service_source.replace(
        &format!("b\"{first_agent_reference}\\0\""),
        "b\"codex_agent_fallback_local\\0\"",
    );
    assert!(
        validate_agent_rows(
            &agent_rows,
            &bootstrap_claims,
            &passed_tests,
            &disconnected_agent_source,
            &async_source,
            &ffi_source,
        )
        .is_err(),
        "disconnected claimed Agent C call must fail closed"
    );
    assert!(
        !service_reference_is_connected(
            first_agent_reference,
            "CodexAgent",
            "connectors",
            &service_source,
            &async_source,
            &ffi_source,
        ),
        "an Agent symbol reachable only from another public method must fail closed"
    );
    let missing_conversation = conversation_rows[..conversation_rows.len() - 1].to_vec();
    assert!(
        validate_conversation_rows(
            &missing_conversation,
            &bootstrap_claims,
            &passed_tests,
            &service_source,
            &async_source,
            &ffi_source,
        )
        .is_err(),
        "missing conversation claim must fail closed"
    );
    let mut stale_conversation = conversation_rows.clone();
    stale_conversation[0][1] = "codex_agent::Fallback::local";
    assert!(
        validate_conversation_rows(
            &stale_conversation,
            &bootstrap_claims,
            &passed_tests,
            &service_source,
            &async_source,
            &ffi_source,
        )
        .is_err(),
        "stale conversation projection must fail closed"
    );
    let missing = service_rows[..service_rows.len() - 1].to_vec();
    assert!(
        validate_service_rows(
            &missing,
            &bootstrap_claims,
            &passed_tests,
            &service_source,
            &async_source,
            &ffi_source,
        )
        .is_err(),
        "missing service claim must fail closed"
    );
    let mut duplicate = missing;
    duplicate.push(service_rows[service_rows.len() - 2].clone());
    assert!(
        validate_service_rows(
            &duplicate,
            &bootstrap_claims,
            &passed_tests,
            &service_source,
            &async_source,
            &ffi_source,
        )
        .is_err(),
        "duplicate service claim must fail closed"
    );
    for (column, stale) in [
        (0, "removed"),
        (1, "codex_agent::Fallback::local"),
        (2, "rust.service:999"),
        (3, "rust-analyzer-service:999"),
        (4, "value-conversion"),
    ] {
        let mut candidate = service_rows.clone();
        candidate[0][column] = stale;
        assert!(
            validate_service_rows(
                &candidate,
                &bootstrap_claims,
                &passed_tests,
                &service_source,
                &async_source,
                &ffi_source,
            )
            .is_err(),
            "stale service evidence column {column} must fail closed"
        );
    }
    let first_reference = bootstrap_claims[service_rows[0][0]]
        .headers
        .iter()
        .next()
        .expect("first service C reference")
        .trim_start_matches("c-header:");
    let disconnected_source = service_source.replace(
        &format!("b\"{first_reference}\\0\""),
        "b\"codex_agent_fallback_local\\0\"",
    );
    assert!(
        validate_service_rows(
            &service_rows,
            &bootstrap_claims,
            &passed_tests,
            &disconnected_source,
            &async_source,
            &ffi_source,
        )
        .is_err(),
        "disconnected claimed C call must fail closed"
    );
    assert!(
        !service_reference_is_connected(
            first_reference,
            "CodexAuthentication",
            "cancel",
            &service_source,
            &async_source,
            &ffi_source,
        ),
        "a symbol reachable only from another public method must fail closed"
    );
    let mut native_rows = service_rows.clone();
    native_rows.extend(conversation_rows.clone());
    native_rows.extend(agent_rows.clone());
    native_rows.extend(host_rows.clone());
    execute_real_sdk_null_boundaries(&native_rows, &bootstrap_claims);
    let service_owners = [
        "CodexAgent",
        "CodexAuthentication",
        "CodexConnectors",
        "CodexConversation",
        "CodexConversations",
        "CodexHooks",
        "CodexHost",
        "CodexIntegrationAuthorization",
        "CodexInteractions",
        "CodexMcpServers",
        "CodexModels",
        "CodexPlugins",
        "CodexSkills",
    ];
    let expected_residual = canonical_keys
        .iter()
        .filter(|capability| {
            let owner = capability
                .split("|owner=")
                .nth(1)
                .and_then(|value| value.split('|').next())
                .and_then(|value| value.rsplit('/').next())
                .expect("canonical owner");
            let kind = capability
                .split("|kind=")
                .nth(1)
                .and_then(|value| value.split('|').next())
                .expect("canonical kind");
            !prior_keys.contains(**capability)
                && matches!(kind, "constructor" | "property" | "object")
                && !service_owners.contains(&owner)
                && owner != "CodexHostState.Ready"
        })
        .map(|capability| (*capability).to_owned())
        .collect::<BTreeSet<_>>();
    assert_eq!(
        residual_keys, expected_residual,
        "residual claims exactly match the audited compiler-derived selection"
    );
    let expected_functions = canonical_keys
        .iter()
        .filter(|capability| {
            capability.contains("|kind=function|") && capability.contains("|suspend=false|")
        })
        .map(|capability| (*capability).to_owned())
        .collect::<BTreeSet<_>>();
    assert_eq!(
        function_keys, expected_functions,
        "function claims exactly match every compiler-derived synchronous value function"
    );
    assert!(compile_header_references(&headers, false));
    assert!(!compile_header_references(&headers, true));

    assert!(ClientInfo::new("", "title", "1").is_err());
    assert!(ClientInfo::new("name", "bad\n", "1").is_err());
    assert!(ConversationId::new(" \t").is_err());
    assert!(CodexFailure::new("", "message", false).is_err());
    assert!(CodexFailure::new("code", "x".repeat(501), false).is_err());
    assert!(Workspace::new("bad\0path", None).is_err());
    assert!(Workspace::new("/path", Some(" ".into())).is_err());
    assert!(McpEnvironmentVariable::new(" ", None).is_err());
    assert!(McpOauthConfiguration::new(None, Some(0)).is_err());
    assert!(McpOauthConfiguration::new(None, Some(65_536)).is_err());
    assert!(McpHttpTransport::new("http://example.test", None, None, None, None).is_err());
    assert!(McpHttpTransport::new("HTTPS://example.test", None, None, None, None).is_err());
    assert!(McpHttpTransport::new("http://[::1]:8080", None, None, None, None).is_ok());
    assert!(McpStdioTransport::new(" ", vec![], None, None, vec![]).is_err());
    assert!(
        McpServerConfiguration::new(
            "bad name",
            McpTransport::Stdio(f.mcp_stdio_sparse.clone()),
            None,
            "local",
            true,
            false,
            false,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            BTreeMap::new(),
        )
        .is_err()
    );
    assert!(!exercise("codex_agent::Stale::symbol", &f));
    assert!(!super::residual_behavior::exercise(
        "codex_agent::Stale::symbol",
        "rust.residual:stale",
        &residual_f,
    ));
    assert!(!super::residual_behavior::exercise(
        "codex_agent::ElicitationResponse::cancel",
        "rust.function:stale",
        &residual_f,
    ));
    assert!(!super::residual_behavior::exercise(
        "codex_agent::Stale::symbol",
        "rust.function:000",
        &residual_f,
    ));
    super::residual_behavior::verify_negatives();

    let compiler = compiler_symbols
        .into_iter()
        .map(|(id, symbols)| (id, symbols.into_iter().collect::<Vec<_>>().join(",")))
        .collect();
    Evidence {
        compiler,
        tests: executed,
    }
}
