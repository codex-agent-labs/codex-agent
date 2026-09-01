//! Ordinary owned projections of canonical immutable values.

use crate::{
    ApprovalPreset, CatalogFreshness, ClientInfo, CodexError, CodexFailure,
    ElicitationValidationReason, HookRunStatus, McpAuthStatus, McpAuthentication,
    McpEnvironmentSource, McpToolApproval, McpToolExposureSurface, PlanStepStatus,
    PluginAuthPolicy, PluginInstallPolicy, ResourceOrigin, SkillScope, Status, WorkActivity,
    Workspace,
};
use std::collections::BTreeMap;

fn invalid(action: &'static str) -> CodexError {
    CodexError::new(Status::InvalidArgument, action)
}

fn valid_client_value(value: &str) -> bool {
    !value.trim().is_empty() && !value.chars().any(char::is_control)
}

impl ClientInfo {
    /// Creates validated client identity.
    pub fn new(
        name: impl Into<String>,
        title: impl Into<String>,
        version: impl Into<String>,
    ) -> Result<Self, CodexError> {
        let value = Self {
            name: name.into(),
            title: title.into(),
            version: version.into(),
        };
        if !valid_client_value(&value.name)
            || !valid_client_value(&value.title)
            || !valid_client_value(&value.version)
        {
            return Err(invalid("client information is invalid"));
        }
        Ok(value)
    }
}

impl CodexFailure {
    /// Creates a validated structured failure.
    pub fn new(
        code: impl Into<String>,
        message: impl Into<String>,
        recoverable: bool,
    ) -> Result<Self, CodexError> {
        let value = Self {
            code: code.into(),
            message: message.into(),
            recoverable,
        };
        if value.code.trim().is_empty()
            || value.message.trim().is_empty()
            || value.message.chars().count() > 500
        {
            return Err(invalid("failure code or message is invalid"));
        }
        Ok(value)
    }
}

impl Workspace {
    /// Creates a validated workspace; an absent display name defaults to the path.
    pub fn new(path: impl Into<String>, display_name: Option<String>) -> Result<Self, CodexError> {
        let path = path.into();
        let display_name = display_name.unwrap_or_else(|| path.clone());
        if path.trim().is_empty() || path.contains('\0') || display_name.trim().is_empty() {
            return Err(invalid("workspace is invalid"));
        }
        Ok(Self { path, display_name })
    }
}

/// Stable conversation identifier.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ConversationId {
    /// Identifier text.
    pub value: String,
}

impl ConversationId {
    /// Creates a nonblank identifier.
    pub fn new(value: impl Into<String>) -> Result<Self, CodexError> {
        let value = value.into();
        if value.trim().is_empty() {
            return Err(invalid("conversation ID must not be blank"));
        }
        Ok(Self { value })
    }
}

/// Settings applied when opening a conversation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ConversationSettings {
    /// Approval policy.
    pub approval_preset: ApprovalPreset,
    /// Optional service tier identifier.
    pub service_tier: Option<String>,
}

impl ConversationSettings {
    /// Creates conversation settings.
    pub fn new(approval_preset: ApprovalPreset, service_tier: Option<String>) -> Self {
        Self {
            approval_preset,
            service_tier,
        }
    }
}

impl Default for ConversationSettings {
    fn default() -> Self {
        Self::new(ApprovalPreset::AutoReview, None)
    }
}

/// A conversation list entry.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ConversationSummary {
    /// Conversation identifier.
    pub conversation_id: ConversationId,
    /// Display title.
    pub title: String,
    /// Last-update Unix timestamp.
    pub updated_at_epoch_seconds: i64,
}

impl ConversationSummary {
    /// Creates a conversation summary.
    pub fn new(
        conversation_id: ConversationId,
        title: impl Into<String>,
        updated_at_epoch_seconds: i64,
    ) -> Self {
        Self {
            conversation_id,
            title: title.into(),
            updated_at_epoch_seconds,
        }
    }
}

/// One invalid elicitation field.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ElicitationValidationIssue {
    /// Field name.
    pub field_name: String,
    /// Validation reason.
    pub reason: ElicitationValidationReason,
}

impl ElicitationValidationIssue {
    /// Creates an issue.
    pub fn new(field_name: impl Into<String>, reason: ElicitationValidationReason) -> Self {
        Self {
            field_name: field_name.into(),
            reason,
        }
    }
}

/// Elicitation validation result.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ElicitationValidation {
    /// Ordered validation issues.
    pub issues: Vec<ElicitationValidationIssue>,
}

impl ElicitationValidation {
    /// Creates a validation result.
    pub fn new(issues: Vec<ElicitationValidationIssue>) -> Self {
        Self { issues }
    }

    /// Whether no issue was reported.
    pub fn is_valid(&self) -> bool {
        self.issues.is_empty()
    }
}

/// Selectable form option.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FormOption {
    /// Submitted value.
    pub value: String,
    /// Display title.
    pub title: String,
    /// Optional detail.
    pub description: Option<String>,
}

impl FormOption {
    /// Creates a form option.
    pub fn new(
        value: impl Into<String>,
        title: impl Into<String>,
        description: Option<String>,
    ) -> Self {
        Self {
            value: value.into(),
            title: title.into(),
            description,
        }
    }
}

/// Environment variable forwarded to an MCP server.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct McpEnvironmentVariable {
    /// Variable name.
    pub name: String,
    /// Optional source environment.
    pub source: Option<McpEnvironmentSource>,
}

impl McpEnvironmentVariable {
    /// Creates a nonblank environment-variable projection.
    pub fn new(
        name: impl Into<String>,
        source: Option<McpEnvironmentSource>,
    ) -> Result<Self, CodexError> {
        let name = name.into();
        if name.trim().is_empty() {
            return Err(invalid("MCP environment variable name must not be blank"));
        }
        Ok(Self { name, source })
    }
}

/// OAuth settings for an MCP server.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct McpOauthConfiguration {
    /// Optional client identifier.
    pub client_id: Option<String>,
    /// Optional local callback port.
    pub callback_port: Option<i32>,
}

impl McpOauthConfiguration {
    /// Creates validated OAuth settings.
    pub fn new(client_id: Option<String>, callback_port: Option<i32>) -> Result<Self, CodexError> {
        if callback_port.is_some_and(|port| !(1..=65_535).contains(&port)) {
            return Err(invalid("MCP OAuth callback port is invalid"));
        }
        Ok(Self {
            client_id,
            callback_port,
        })
    }
}

/// Per-tool MCP settings.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct McpToolConfiguration {
    /// Optional approval override.
    pub approval: Option<McpToolApproval>,
}

impl McpToolConfiguration {
    /// Creates tool settings.
    pub fn new(approval: Option<McpToolApproval>) -> Self {
        Self { approval }
    }
}

/// Transport used by an MCP server.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum McpTransport {
    /// HTTP transport.
    Http(McpHttpTransport),
    /// Local subprocess transport.
    Stdio(McpStdioTransport),
}

/// HTTP MCP transport.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct McpHttpTransport {
    /// Endpoint URL.
    pub url: String,
    /// Optional bearer-token environment variable.
    pub bearer_token_environment_variable: Option<String>,
    /// Optional literal headers, preserving absent versus empty.
    pub headers: Option<BTreeMap<String, String>>,
    /// Optional environment-backed headers, preserving absent versus empty.
    pub environment_headers: Option<BTreeMap<String, String>>,
    /// Optional local headers helper.
    pub headers_helper: Option<String>,
}

impl McpHttpTransport {
    /// Creates a validated HTTP transport.
    pub fn new(
        url: impl Into<String>,
        bearer_token_environment_variable: Option<String>,
        headers: Option<BTreeMap<String, String>>,
        environment_headers: Option<BTreeMap<String, String>>,
        headers_helper: Option<String>,
    ) -> Result<Self, CodexError> {
        let url = url.into();
        if !safe_mcp_http_url(&url)
            || bearer_token_environment_variable
                .as_deref()
                .is_some_and(|value| value.trim().is_empty())
            || headers_helper
                .as_deref()
                .is_some_and(|value| value.trim().is_empty())
        {
            return Err(invalid("MCP HTTP transport is invalid"));
        }
        Ok(Self {
            url,
            bearer_token_environment_variable,
            headers,
            environment_headers,
            headers_helper,
        })
    }
}

/// Subprocess MCP transport.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct McpStdioTransport {
    /// Executable or command.
    pub command: String,
    /// Ordered arguments.
    pub arguments: Vec<String>,
    /// Optional working directory.
    pub working_directory: Option<String>,
    /// Optional explicit environment, preserving absent versus empty.
    pub environment: Option<BTreeMap<String, String>>,
    /// Ordered forwarded environment variables.
    pub forwarded_environment: Vec<McpEnvironmentVariable>,
}

impl McpStdioTransport {
    /// Creates a validated subprocess transport.
    pub fn new(
        command: impl Into<String>,
        arguments: Vec<String>,
        working_directory: Option<String>,
        environment: Option<BTreeMap<String, String>>,
        forwarded_environment: Vec<McpEnvironmentVariable>,
    ) -> Result<Self, CodexError> {
        let command = command.into();
        if command.trim().is_empty() {
            return Err(invalid("MCP command must not be blank"));
        }
        Ok(Self {
            command,
            arguments,
            working_directory,
            environment,
            forwarded_environment,
        })
    }
}

/// Complete MCP server configuration.
#[derive(Clone, Debug, PartialEq)]
pub struct McpServerConfiguration {
    /// Stable server name.
    pub name: String,
    /// Transport configuration.
    pub transport: McpTransport,
    /// Optional authentication mechanism.
    pub authentication: Option<McpAuthentication>,
    /// Execution environment identifier.
    pub environment_id: String,
    /// Whether enabled.
    pub is_enabled: bool,
    /// Whether required.
    pub is_required: bool,
    /// Whether parallel tool calls are supported.
    pub supports_parallel_tool_calls: bool,
    /// Optional surfaces from which tools are omitted.
    pub omit_tools_from: Option<Vec<McpToolExposureSurface>>,
    /// Optional startup timeout in seconds.
    pub startup_timeout_seconds: Option<f64>,
    /// Optional tool timeout in seconds.
    pub tool_timeout_seconds: Option<f64>,
    /// Optional default tool approval.
    pub default_tool_approval: Option<McpToolApproval>,
    /// Optional allow-list of tools.
    pub enabled_tools: Option<Vec<String>>,
    /// Optional deny-list of tools.
    pub disabled_tools: Option<Vec<String>>,
    /// Optional OAuth scopes.
    pub scopes: Option<Vec<String>>,
    /// Optional OAuth settings.
    pub oauth: Option<McpOauthConfiguration>,
    /// Optional OAuth resource.
    pub oauth_resource: Option<String>,
    /// Per-tool settings.
    pub tools: BTreeMap<String, McpToolConfiguration>,
}

impl McpServerConfiguration {
    /// Creates validated server configuration.
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        name: impl Into<String>,
        transport: McpTransport,
        authentication: Option<McpAuthentication>,
        environment_id: impl Into<String>,
        is_enabled: bool,
        is_required: bool,
        supports_parallel_tool_calls: bool,
        omit_tools_from: Option<Vec<McpToolExposureSurface>>,
        startup_timeout_seconds: Option<f64>,
        tool_timeout_seconds: Option<f64>,
        default_tool_approval: Option<McpToolApproval>,
        enabled_tools: Option<Vec<String>>,
        disabled_tools: Option<Vec<String>>,
        scopes: Option<Vec<String>>,
        oauth: Option<McpOauthConfiguration>,
        oauth_resource: Option<String>,
        tools: BTreeMap<String, McpToolConfiguration>,
    ) -> Result<Self, CodexError> {
        let name = name.into();
        let environment_id = environment_id.into();
        let valid_name = !name.is_empty()
            && name
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'));
        let valid_timeout = |value: Option<f64>| {
            value.is_none_or(|seconds| {
                seconds.is_finite() && seconds > 0.0 && seconds < 1.844_674_407_370_955_2E19
            })
        };
        if !valid_name
            || environment_id.trim().is_empty()
            || !valid_timeout(startup_timeout_seconds)
            || !valid_timeout(tool_timeout_seconds)
        {
            return Err(invalid("MCP server configuration is invalid"));
        }
        if matches!(transport, McpTransport::Stdio(_))
            && (authentication.is_some() || oauth.is_some() || oauth_resource.is_some())
        {
            return Err(invalid("MCP stdio servers do not support authentication"));
        }
        if matches!(
            transport,
            McpTransport::Http(McpHttpTransport {
                headers_helper: Some(_),
                ..
            })
        ) && environment_id != "local"
        {
            return Err(invalid("MCP headers helpers require the local environment"));
        }
        Ok(Self {
            name,
            transport,
            authentication,
            environment_id,
            is_enabled,
            is_required,
            supports_parallel_tool_calls,
            omit_tools_from,
            startup_timeout_seconds,
            tool_timeout_seconds,
            default_tool_approval,
            enabled_tools,
            disabled_tools,
            scopes,
            oauth,
            oauth_resource,
            tools,
        })
    }
}

/// Installed or discoverable MCP server.
#[derive(Clone, Debug, PartialEq)]
pub struct McpServer {
    /// Stable server name.
    pub name: String,
    /// Display name.
    pub display_name: String,
    /// Current authentication status.
    pub auth_status: McpAuthStatus,
    /// Optional complete configuration.
    pub configuration: Option<McpServerConfiguration>,
    /// Configuration origin.
    pub origin: ResourceOrigin,
    /// Whether the current user may remove the server.
    pub can_remove: bool,
}

impl McpServer {
    /// Creates an MCP server value.
    pub fn new(
        name: impl Into<String>,
        display_name: impl Into<String>,
        auth_status: McpAuthStatus,
        configuration: Option<McpServerConfiguration>,
        origin: ResourceOrigin,
        can_remove: bool,
    ) -> Self {
        Self {
            name: name.into(),
            display_name: display_name.into(),
            auth_status,
            configuration,
            origin,
            can_remove,
        }
    }

    /// Whether bearer-token or OAuth authorization is configured.
    pub fn is_authorized(&self) -> bool {
        matches!(
            self.auth_status,
            McpAuthStatus::BearerToken | McpAuthStatus::Oauth
        )
    }
}

fn safe_mcp_http_url(value: &str) -> bool {
    if value.is_empty()
        || value
            .chars()
            .any(|character| character.is_whitespace() || character.is_control())
    {
        return false;
    }
    let (scheme, remainder) = if let Some(value) = value.strip_prefix("https://") {
        ("https", value)
    } else if let Some(value) = value.strip_prefix("http://") {
        ("http", value)
    } else {
        return false;
    };
    let authority = remainder
        .split(['/', '?', '#'])
        .next()
        .expect("split always yields one item");
    if authority.is_empty() || authority.contains('@') {
        return false;
    }
    let host = if let Some(bracketed) = authority.strip_prefix('[') {
        let Some(closing) = bracketed.find(']') else {
            return false;
        };
        let host = &bracketed[..closing];
        if !valid_port_suffix(&bracketed[closing + 1..])
            || !host.contains(':')
            || !host.bytes().any(|byte| byte.is_ascii_hexdigit())
            || !host
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit() || matches!(byte, b':' | b'.'))
        {
            return false;
        }
        host
    } else {
        if authority.matches(':').count() > 1 {
            return false;
        }
        let (host, port) = authority.split_once(':').unwrap_or((authority, ""));
        if !valid_port(port) || !valid_registered_host(host) {
            return false;
        }
        host
    };
    scheme == "https"
        || host.eq_ignore_ascii_case("localhost")
        || matches!(host, "127.0.0.1" | "::1")
}

fn valid_port(value: &str) -> bool {
    value.is_empty()
        || value.bytes().all(|byte| byte.is_ascii_digit())
            && value.parse::<u16>().is_ok_and(|port| port != 0)
}

fn valid_port_suffix(value: &str) -> bool {
    value.is_empty() || value.strip_prefix(':').is_some_and(valid_port)
}

fn valid_registered_host(value: &str) -> bool {
    let bytes = value.as_bytes();
    let mut index = 0;
    let mut has_name = false;
    while index < bytes.len() {
        match bytes[index] {
            byte if byte.is_ascii_alphanumeric() => {
                has_name = true;
                index += 1;
            }
            b'%' if bytes.get(index + 1).is_some_and(u8::is_ascii_hexdigit)
                && bytes.get(index + 2).is_some_and(u8::is_ascii_hexdigit) =>
            {
                has_name = true;
                index += 3;
            }
            b'-' | b'.' | b'_' | b'~' | b'!' | b'$' | b'&' | b'\'' | b'(' | b')' | b'*' | b'+'
            | b',' | b';' | b'=' => index += 1,
            _ => return false,
        }
    }
    has_name
}

/// One step in an agent plan.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PlanStep {
    /// Step text.
    pub text: String,
    /// Current status.
    pub status: PlanStepStatus,
}

impl PlanStep {
    /// Creates a plan step.
    pub fn new(text: impl Into<String>, status: PlanStepStatus) -> Self {
        Self {
            text: text.into(),
            status,
        }
    }
}

/// Current plan progress.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PlanProgress {
    /// Optional explanation.
    pub explanation: Option<String>,
    /// Ordered steps.
    pub steps: Vec<PlanStep>,
}

impl PlanProgress {
    /// Creates plan progress.
    pub fn new(explanation: Option<String>, steps: Vec<PlanStep>) -> Self {
        Self { explanation, steps }
    }
}

/// Service tier offered by a model.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ServiceTier {
    /// Stable identifier.
    pub id: String,
    /// Display name.
    pub name: String,
    /// Description.
    pub description: String,
}

impl ServiceTier {
    /// Creates a service tier.
    pub fn new(
        id: impl Into<String>,
        name: impl Into<String>,
        description: impl Into<String>,
    ) -> Self {
        Self {
            id: id.into(),
            name: name.into(),
            description: description.into(),
        }
    }
}

/// Model catalog entry.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Model {
    /// Stable identifier.
    pub id: String,
    /// Display name.
    pub display_name: String,
    /// Description.
    pub description: String,
    /// Ordered supported effort names.
    pub supported_efforts: Vec<String>,
    /// Default effort name.
    pub default_effort: String,
    /// Whether this is the default model.
    pub is_default: bool,
    /// Ordered service tiers.
    pub service_tiers: Vec<ServiceTier>,
    /// Optional default service-tier identifier.
    pub default_service_tier: Option<String>,
}

impl Model {
    /// Creates a model entry.
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        id: impl Into<String>,
        display_name: impl Into<String>,
        description: impl Into<String>,
        supported_efforts: Vec<String>,
        default_effort: impl Into<String>,
        is_default: bool,
        service_tiers: Vec<ServiceTier>,
        default_service_tier: Option<String>,
    ) -> Self {
        Self {
            id: id.into(),
            display_name: display_name.into(),
            description: description.into(),
            supported_efforts,
            default_effort: default_effort.into(),
            is_default,
            service_tiers,
            default_service_tier,
        }
    }
}

/// Connector catalog entry.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Connector {
    /// Stable identifier.
    pub id: String,
    /// Display name.
    pub name: String,
    /// Description.
    pub description: String,
    /// Optional installation URL.
    pub install_url: Option<String>,
    /// Whether the connector is accessible.
    pub is_accessible: bool,
    /// Whether the connector is enabled.
    pub is_enabled: bool,
    /// Ordered owning plugin names.
    pub plugin_names: Vec<String>,
}

impl Connector {
    /// Creates a connector.
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        id: impl Into<String>,
        name: impl Into<String>,
        description: impl Into<String>,
        install_url: Option<String>,
        is_accessible: bool,
        is_enabled: bool,
        plugin_names: Vec<String>,
    ) -> Self {
        Self {
            id: id.into(),
            name: name.into(),
            description: description.into(),
            install_url,
            is_accessible,
            is_enabled,
            plugin_names,
        }
    }
}

/// Plugin identity in a marketplace.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PluginReference {
    /// Stable identifier.
    pub id: String,
    /// Plugin name.
    pub name: String,
    /// Marketplace name.
    pub marketplace_name: String,
    /// Optional marketplace path.
    pub marketplace_path: Option<String>,
    /// Optional remote identifier.
    pub remote_plugin_id: Option<String>,
}

impl PluginReference {
    /// Creates a plugin reference.
    pub fn new(
        id: impl Into<String>,
        name: impl Into<String>,
        marketplace_name: impl Into<String>,
        marketplace_path: Option<String>,
        remote_plugin_id: Option<String>,
    ) -> Self {
        Self {
            id: id.into(),
            name: name.into(),
            marketplace_name: marketplace_name.into(),
            marketplace_path,
            remote_plugin_id,
        }
    }

    /// Stable plugin URI.
    pub fn uri(&self) -> String {
        format!("plugin://{}@{}", self.name, self.marketplace_name)
    }
}

/// Skill contributed by a plugin.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PluginSkill {
    /// Skill name.
    pub name: String,
    /// Description.
    pub description: String,
    /// Whether the skill is enabled.
    pub is_enabled: bool,
    /// Optional local path.
    pub path: Option<String>,
}

impl PluginSkill {
    /// Creates a plugin skill.
    pub fn new(
        name: impl Into<String>,
        description: impl Into<String>,
        is_enabled: bool,
        path: Option<String>,
    ) -> Self {
        Self {
            name: name.into(),
            description: description.into(),
            is_enabled,
            path,
        }
    }
}

/// Plugin catalog summary.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PluginSummary {
    /// Plugin reference.
    pub reference: PluginReference,
    /// Display name.
    pub display_name: String,
    /// Description.
    pub description: String,
    /// Whether installed.
    pub is_installed: bool,
    /// Whether enabled.
    pub is_enabled: bool,
    /// Installation policy.
    pub install_policy: PluginInstallPolicy,
    /// Authentication policy.
    pub auth_policy: PluginAuthPolicy,
    /// Whether currently available.
    pub is_available: bool,
    /// Ordered capability names.
    pub capabilities: Vec<String>,
    /// Optional brand color.
    pub brand_color: Option<String>,
    /// Optional privacy-policy URL.
    pub privacy_policy_url: Option<String>,
    /// Optional terms URL.
    pub terms_of_service_url: Option<String>,
    /// Optional website URL.
    pub website_url: Option<String>,
}

impl PluginSummary {
    /// Creates a plugin summary.
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        reference: PluginReference,
        display_name: impl Into<String>,
        description: impl Into<String>,
        is_installed: bool,
        is_enabled: bool,
        install_policy: PluginInstallPolicy,
        auth_policy: PluginAuthPolicy,
        is_available: bool,
        capabilities: Vec<String>,
        brand_color: Option<String>,
        privacy_policy_url: Option<String>,
        terms_of_service_url: Option<String>,
        website_url: Option<String>,
    ) -> Self {
        Self {
            reference,
            display_name: display_name.into(),
            description: description.into(),
            is_installed,
            is_enabled,
            install_policy,
            auth_policy,
            is_available,
            capabilities,
            brand_color,
            privacy_policy_url,
            terms_of_service_url,
            website_url,
        }
    }
}

/// Plugin catalog snapshot.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PluginCatalog {
    /// Ordered plugins.
    pub plugins: Vec<PluginSummary>,
    /// Ordered catalog errors.
    pub errors: Vec<String>,
    /// Catalog freshness.
    pub freshness: CatalogFreshness,
}

impl PluginCatalog {
    /// Creates a plugin catalog.
    pub fn new(
        plugins: Vec<PluginSummary>,
        errors: Vec<String>,
        freshness: CatalogFreshness,
    ) -> Self {
        Self {
            plugins,
            errors,
            freshness,
        }
    }
}

/// Detailed plugin information.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PluginDetail {
    /// Summary.
    pub summary: PluginSummary,
    /// Detailed description.
    pub description: String,
    /// Ordered skills.
    pub skills: Vec<PluginSkill>,
    /// Ordered connectors.
    pub connectors: Vec<Connector>,
    /// Ordered MCP server names.
    pub mcp_servers: Vec<String>,
    /// Hook count.
    pub hook_count: i32,
}

impl PluginDetail {
    /// Creates plugin detail.
    pub fn new(
        summary: PluginSummary,
        description: impl Into<String>,
        skills: Vec<PluginSkill>,
        connectors: Vec<Connector>,
        mcp_servers: Vec<String>,
        hook_count: i32,
    ) -> Self {
        Self {
            summary,
            description: description.into(),
            skills,
            connectors,
            mcp_servers,
            hook_count,
        }
    }
}

/// Result of installing a plugin.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PluginInstallResult {
    /// Authentication policy.
    pub auth_policy: PluginAuthPolicy,
    /// Ordered connectors requiring authentication.
    pub connectors_needing_authentication: Vec<Connector>,
    /// Optional user-facing message.
    pub message: Option<String>,
}

impl PluginInstallResult {
    /// Creates an installation result.
    pub fn new(
        auth_policy: PluginAuthPolicy,
        connectors_needing_authentication: Vec<Connector>,
        message: Option<String>,
    ) -> Self {
        Self {
            auth_policy,
            connectors_needing_authentication,
            message,
        }
    }
}

/// Installed skill metadata.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Skill {
    /// Skill name.
    pub name: String,
    /// Display name.
    pub display_name: String,
    /// Description.
    pub description: String,
    /// Local path.
    pub path: String,
    /// Installation scope.
    pub scope: SkillScope,
    /// Whether enabled.
    pub is_enabled: bool,
    /// Optional brand color.
    pub brand_color: Option<String>,
    /// Ordered dependency names.
    pub dependencies: Vec<String>,
    /// Whether uninstall is supported.
    pub can_uninstall: bool,
    /// Resource origin.
    pub origin: ResourceOrigin,
}

impl Skill {
    /// Creates skill metadata.
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        name: impl Into<String>,
        display_name: impl Into<String>,
        description: impl Into<String>,
        path: impl Into<String>,
        scope: SkillScope,
        is_enabled: bool,
        brand_color: Option<String>,
        dependencies: Vec<String>,
        can_uninstall: bool,
        origin: Option<ResourceOrigin>,
    ) -> Self {
        let origin = origin.unwrap_or(match scope {
            SkillScope::User => ResourceOrigin::User,
            SkillScope::Repo => ResourceOrigin::Workspace,
            SkillScope::Plugin => ResourceOrigin::Plugin,
            SkillScope::System | SkillScope::Admin => ResourceOrigin::Managed,
        });
        Self {
            name: name.into(),
            display_name: display_name.into(),
            description: description.into(),
            path: path.into(),
            scope,
            is_enabled,
            brand_color,
            dependencies,
            can_uninstall,
            origin,
        }
    }
}

/// Skill catalog snapshot.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SkillCatalog {
    /// Ordered skills.
    pub skills: Vec<Skill>,
    /// Ordered catalog errors.
    pub errors: Vec<String>,
}

impl SkillCatalog {
    /// Creates a skill catalog.
    pub fn new(skills: Vec<Skill>, errors: Vec<String>) -> Self {
        Self { skills, errors }
    }
}

/// Chunk of skill content.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SkillChunk {
    /// UTF-8 content.
    pub content: String,
    /// Next byte offset, if more data remains.
    pub next_offset: Option<i64>,
    /// Total content size.
    pub total_bytes: i64,
}

impl SkillChunk {
    /// Creates a skill chunk.
    pub fn new(content: impl Into<String>, next_offset: Option<i64>, total_bytes: i64) -> Self {
        Self {
            content: content.into(),
            next_offset,
            total_bytes,
        }
    }
}

/// One hook execution in turn progress.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HookActivity {
    /// Stable identifier.
    pub id: String,
    /// Hook event name.
    pub event_name: String,
    /// Handler type.
    pub handler_type: String,
    /// Run status.
    pub status: HookRunStatus,
    /// Optional status detail.
    pub status_message: Option<String>,
    /// Ordered detail lines.
    pub details: Vec<String>,
}

impl HookActivity {
    /// Creates hook activity.
    pub fn new(
        id: impl Into<String>,
        event_name: impl Into<String>,
        handler_type: impl Into<String>,
        status: HookRunStatus,
        status_message: Option<String>,
        details: Vec<String>,
    ) -> Self {
        Self {
            id: id.into(),
            event_name: event_name.into(),
            handler_type: handler_type.into(),
            status,
            status_message,
            details,
        }
    }
}

/// Current turn progress.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TurnProgress {
    /// User-visible response text.
    pub text: String,
    /// Commentary text.
    pub commentary: String,
    /// Reasoning text.
    pub reasoning: String,
    /// Plan text.
    pub plan: String,
    /// Structured plan progress.
    pub plan_progress: Option<PlanProgress>,
    /// Shell output.
    pub shell_output: String,
    /// Shell exit code.
    pub shell_exit_code: Option<i32>,
    /// Current work activity.
    pub work_activity: Option<WorkActivity>,
    /// Ordered hook activities.
    pub hook_activities: Vec<HookActivity>,
    /// Whether output was truncated.
    pub is_truncated: bool,
}

impl TurnProgress {
    /// Creates turn progress.
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        text: impl Into<String>,
        commentary: impl Into<String>,
        reasoning: impl Into<String>,
        plan: impl Into<String>,
        plan_progress: Option<PlanProgress>,
        shell_output: impl Into<String>,
        shell_exit_code: Option<i32>,
        work_activity: Option<WorkActivity>,
        hook_activities: Vec<HookActivity>,
        is_truncated: bool,
    ) -> Self {
        Self {
            text: text.into(),
            commentary: commentary.into(),
            reasoning: reasoning.into(),
            plan: plan.into(),
            plan_progress,
            shell_output: shell_output.into(),
            shell_exit_code,
            work_activity,
            hook_activities,
            is_truncated,
        }
    }
}
