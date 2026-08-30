//! Remaining ordinary canonical value projections.

use crate::{
    ApprovalPreset, AuthenticationStatus, AuthorizationPurpose, Capability, CodexError,
    CodexFailure, CollaborationMode, Connector, ConversationId, ConversationStatus,
    ConversationSummary, ElicitationAction, ElicitationValidation, FormFieldType, FormOption,
    FormStringFormat, HookTrustStatus, IntegrationAuthorizationStatus, McpServer, MessageRole,
    ResourceOrigin, SkillScope, Status, TurnProgress, Workspace, WorkspaceSelectionReason,
};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt::{Debug, Formatter};
use std::sync::Arc;

fn invalid(message: impl Into<String>) -> CodexError {
    CodexError::new(Status::InvalidArgument, message)
}

impl ApprovalPreset {
    /// Canonical user-facing display name.
    pub const fn display_name(self) -> &'static str {
        match self {
            Self::Never => "Never",
            Self::AutoReview => "Auto review",
            Self::AskMe => "Ask me",
            Self::Strict => "Strict",
        }
    }
}

impl Capability {
    /// Stable capability identifier.
    pub const fn id(self) -> &'static str {
        match self {
            Self::WebSearch => "web_search",
        }
    }

    /// User-facing capability label.
    pub const fn display_label(self) -> &'static str {
        match self {
            Self::WebSearch => "Web search",
        }
    }

    /// Optional capability icon.
    pub const fn icon(self) -> Option<&'static str> {
        match self {
            Self::WebSearch => Some("🌐"),
        }
    }

    /// User-facing prompt label.
    pub const fn prompt_label(self) -> &'static str {
        match self {
            Self::WebSearch => "Use 🌐 Web search",
        }
    }
}

impl SkillScope {
    /// Canonical user-facing display name.
    pub const fn display_name(self) -> &'static str {
        match self {
            Self::System => "Built in",
            Self::User => "User",
            Self::Repo => "Workspace",
            Self::Plugin => "Plugin",
            Self::Admin => "Managed",
        }
    }
}

/// A validated authorization URL.
#[derive(Clone, Eq, PartialEq)]
pub struct AuthorizationUrl {
    /// Validated URL string.
    pub value: String,
    /// Authorization purpose.
    pub purpose: AuthorizationPurpose,
}

impl AuthorizationUrl {
    /// Creates a trusted ChatGPT authorization URL.
    pub fn chat_gpt(value: impl Into<String>) -> Result<Self, CodexError> {
        crate::native_values::sync_authorization_url_chat_gpt(&value.into())
    }

    /// Creates a safe external-service authorization URL.
    pub fn external(value: impl Into<String>) -> Result<Self, CodexError> {
        crate::native_values::sync_authorization_url_external(&value.into())
    }
}

impl Debug for AuthorizationUrl {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("AuthorizationUrl")
            .field("purpose", &self.purpose)
            .finish_non_exhaustive()
    }
}

/// API-key authentication.
#[derive(Clone, Eq, PartialEq)]
pub struct ApiKeyAuthentication {
    /// Secret API-key value.
    pub value: String,
}

impl ApiKeyAuthentication {
    /// Creates nonblank API-key authentication.
    pub fn new(value: impl Into<String>) -> Result<Self, CodexError> {
        let value = value.into();
        if value.trim().is_empty() {
            return Err(invalid("API key must not be blank"));
        }
        Ok(Self { value })
    }
}

impl Debug for ApiKeyAuthentication {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("ApiKeyAuthentication(**redacted**)")
    }
}

/// Browser authentication singleton.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ChatGptBrowserAuthentication;

impl ChatGptBrowserAuthentication {
    /// The canonical browser-authentication value.
    pub const INSTANCE: Self = Self;
}

/// Device-code authentication singleton.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ChatGptDeviceCodeAuthentication;

impl ChatGptDeviceCodeAuthentication {
    /// The canonical device-code-authentication value.
    pub const INSTANCE: Self = Self;
}

/// Authentication method.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum AuthenticationMethod {
    /// Browser authentication.
    ChatGptBrowser(ChatGptBrowserAuthentication),
    /// Device-code authentication.
    ChatGptDeviceCode(ChatGptDeviceCodeAuthentication),
    /// API-key authentication.
    ApiKey(ApiKeyAuthentication),
}

/// Immutable authentication state.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AuthenticationState {
    /// Current status.
    pub status: AuthenticationStatus,
    /// Pending sign-in URL.
    pub pending_sign_in_url: Option<AuthorizationUrl>,
    /// Device verification URL.
    pub device_verification_url: Option<AuthorizationUrl>,
    /// Device user code.
    pub device_user_code: Option<String>,
    /// Structured failure.
    pub failure: Option<CodexFailure>,
}

impl AuthenticationState {
    /// Creates authentication state.
    pub fn new(
        status: AuthenticationStatus,
        pending_sign_in_url: Option<AuthorizationUrl>,
        device_verification_url: Option<AuthorizationUrl>,
        device_user_code: Option<String>,
        failure: Option<CodexFailure>,
    ) -> Self {
        Self {
            status,
            pending_sign_in_url,
            device_verification_url,
            device_user_code,
            failure,
        }
    }
}

/// Skill invocation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SkillInvocation {
    /// Display name.
    pub name: String,
    /// Skill path.
    pub path: String,
}

impl SkillInvocation {
    /// Creates a skill invocation.
    pub fn new(name: impl Into<String>, path: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            path: path.into(),
        }
    }

    /// Stable invocation key.
    pub fn key(&self) -> String {
        format!("skill:{}", self.path)
    }
}

/// Plugin invocation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PluginInvocation {
    /// Display name.
    pub name: String,
    /// Plugin URI.
    pub uri: String,
}

impl PluginInvocation {
    /// Creates a plugin invocation.
    pub fn new(name: impl Into<String>, uri: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            uri: uri.into(),
        }
    }

    /// Stable invocation key.
    pub fn key(&self) -> String {
        format!("plugin:{}", self.uri)
    }
}

/// Invocation attached to a message or turn.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Invocation {
    /// Skill invocation.
    Skill(SkillInvocation),
    /// Plugin invocation.
    Plugin(PluginInvocation),
}

impl Invocation {
    /// Display name.
    pub fn name(&self) -> &str {
        match self {
            Self::Skill(value) => &value.name,
            Self::Plugin(value) => &value.name,
        }
    }

    /// Stable invocation key.
    pub fn key(&self) -> String {
        match self {
            Self::Skill(value) => value.key(),
            Self::Plugin(value) => value.key(),
        }
    }
}

/// Immutable conversation message.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Message {
    /// Message identifier.
    pub id: String,
    /// Optional client identifier.
    pub client_message_id: Option<String>,
    /// Author role.
    pub role: MessageRole,
    /// Message text.
    pub text: String,
    /// Collaboration mode.
    pub collaboration_mode: CollaborationMode,
    /// Optional reasoning.
    pub reasoning: Option<String>,
    /// Optional plan.
    pub plan: Option<String>,
    /// Optional shell command.
    pub shell_command: Option<String>,
    /// Optional shell exit code.
    pub exit_code: Option<i32>,
    /// Enabled capabilities.
    pub capabilities: BTreeSet<Capability>,
    /// Ordered invocations.
    pub invocations: Vec<Invocation>,
}

impl Message {
    /// Creates a message.
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        id: impl Into<String>,
        client_message_id: Option<String>,
        role: MessageRole,
        text: impl Into<String>,
        collaboration_mode: CollaborationMode,
        reasoning: Option<String>,
        plan: Option<String>,
        shell_command: Option<String>,
        exit_code: Option<i32>,
        capabilities: BTreeSet<Capability>,
        invocations: Vec<Invocation>,
    ) -> Self {
        Self {
            id: id.into(),
            client_message_id,
            role,
            text: text.into(),
            collaboration_mode,
            reasoning,
            plan,
            shell_command,
            exit_code,
            capabilities,
            invocations,
        }
    }
}

/// Complete conversation value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ConversationSnapshot {
    /// Conversation summary.
    pub summary: ConversationSummary,
    /// Ordered messages.
    pub messages: Vec<Message>,
}

impl ConversationSnapshot {
    /// Creates a conversation value.
    pub fn new(summary: ConversationSummary, messages: Vec<Message>) -> Self {
        Self { summary, messages }
    }
}

/// Immutable turn request.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TurnRequest {
    /// Prompt.
    pub prompt: String,
    /// Optional client message ID.
    pub client_message_id: Option<String>,
    /// Optional model.
    pub model: Option<String>,
    /// Optional effort.
    pub effort: Option<String>,
    /// Optional service tier.
    pub service_tier: Option<String>,
    /// Approval preset.
    pub approval_preset: ApprovalPreset,
    /// Enabled capabilities.
    pub capabilities: BTreeSet<Capability>,
    /// Ordered invocations.
    pub invocations: Vec<Invocation>,
    /// Collaboration mode.
    pub collaboration_mode: CollaborationMode,
}

impl TurnRequest {
    /// Creates a turn request.
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        prompt: impl Into<String>,
        client_message_id: Option<String>,
        model: Option<String>,
        effort: Option<String>,
        service_tier: Option<String>,
        approval_preset: ApprovalPreset,
        capabilities: BTreeSet<Capability>,
        invocations: Vec<Invocation>,
        collaboration_mode: CollaborationMode,
    ) -> Self {
        Self {
            prompt: prompt.into(),
            client_message_id,
            model,
            effort,
            service_tier,
            approval_preset,
            capabilities,
            invocations,
            collaboration_mode,
        }
    }
}

/// Text form value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FormText {
    /// Text value.
    pub value: String,
}

impl FormText {
    /// Creates text form input.
    pub fn new(value: impl Into<String>) -> Self {
        Self {
            value: value.into(),
        }
    }
}

/// Numeric form value.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct FormNumber {
    /// Numeric value.
    pub value: f64,
}

impl FormNumber {
    /// Creates finite numeric form input.
    pub fn new(value: f64) -> Result<Self, CodexError> {
        if !value.is_finite() {
            return Err(invalid("form number must be finite"));
        }
        Ok(Self { value })
    }
}

/// Boolean form value.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FormBoolean {
    /// Boolean value.
    pub value: bool,
}

impl FormBoolean {
    /// Creates Boolean form input.
    pub const fn new(value: bool) -> Self {
        Self { value }
    }
}

/// Ordered text-list form value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FormTextList {
    /// Ordered strings.
    pub value: Vec<String>,
}

impl FormTextList {
    /// Creates text-list form input.
    pub fn new(value: Vec<String>) -> Self {
        Self { value }
    }
}

/// A form value.
#[derive(Clone, Debug, PartialEq)]
pub enum FormValue {
    /// Text value.
    Text(FormText),
    /// Number value.
    Number(FormNumber),
    /// Boolean value.
    Boolean(FormBoolean),
    /// Ordered text list.
    TextList(FormTextList),
}

/// Field in an elicitation form.
#[derive(Clone, Debug, PartialEq)]
pub struct FormField {
    /// Stable field name.
    pub name: String,
    /// User-facing title.
    pub title: String,
    /// Optional description.
    pub description: Option<String>,
    /// Whether required.
    pub is_required: bool,
    /// Field type.
    pub field_type: FormFieldType,
    /// Ordered options.
    pub options: Vec<FormOption>,
    /// Optional default.
    pub default_value: Option<FormValue>,
    /// Optional numeric minimum.
    pub minimum: Option<f64>,
    /// Optional numeric maximum.
    pub maximum: Option<f64>,
    /// Optional string format.
    pub format: Option<FormStringFormat>,
    /// Optional minimum length.
    pub minimum_length: Option<i64>,
    /// Optional maximum length.
    pub maximum_length: Option<i64>,
    /// Optional minimum selections.
    pub minimum_selections: Option<i64>,
    /// Optional maximum selections.
    pub maximum_selections: Option<i64>,
    /// Whether unlisted values are allowed.
    pub allows_other: bool,
    /// Whether the value is secret.
    pub is_secret: bool,
}

impl FormField {
    /// Creates a validated form field.
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        name: impl Into<String>,
        title: impl Into<String>,
        description: Option<String>,
        is_required: bool,
        field_type: FormFieldType,
        options: Vec<FormOption>,
        default_value: Option<FormValue>,
        minimum: Option<f64>,
        maximum: Option<f64>,
        format: Option<FormStringFormat>,
        minimum_length: Option<i64>,
        maximum_length: Option<i64>,
        minimum_selections: Option<i64>,
        maximum_selections: Option<i64>,
        allows_other: bool,
        is_secret: bool,
    ) -> Result<Self, CodexError> {
        let nonnegative = |value: Option<i64>| value.is_none_or(|value| value >= 0);
        if !nonnegative(minimum_length)
            || !nonnegative(maximum_length)
            || !nonnegative(minimum_selections)
            || !nonnegative(maximum_selections)
            || minimum_length
                .zip(maximum_length)
                .is_some_and(|(min, max)| min > max)
            || minimum_selections
                .zip(maximum_selections)
                .is_some_and(|(min, max)| min > max)
            || minimum.is_some_and(|value| !value.is_finite())
            || maximum.is_some_and(|value| !value.is_finite())
            || minimum.zip(maximum).is_some_and(|(min, max)| min > max)
        {
            return Err(invalid("form field bounds are invalid"));
        }
        Ok(Self {
            name: name.into(),
            title: title.into(),
            description,
            is_required,
            field_type,
            options,
            default_value,
            minimum,
            maximum,
            format,
            minimum_length,
            maximum_length,
            minimum_selections,
            maximum_selections,
            allows_other,
            is_secret,
        })
    }

    /// Whether the nullable value satisfies this field's exact validation rules.
    pub fn accepts(&self, value: Option<&FormValue>) -> Result<bool, CodexError> {
        crate::native_values::sync_form_field_accepts(self, value)
    }
}

/// Elicitation request.
#[derive(Clone, Debug, PartialEq)]
pub struct Elicitation {
    /// Request identifier.
    pub request_id: String,
    /// Requesting server name.
    pub server_name: String,
    /// Conversation identifier.
    pub conversation_id: ConversationId,
    /// Request message.
    pub message: String,
    /// Optional ordered form.
    pub form: Option<Vec<FormField>>,
    /// Optional request URL.
    pub url: Option<String>,
}

impl Elicitation {
    /// Creates an elicitation request.
    pub fn new(
        request_id: impl Into<String>,
        server_name: impl Into<String>,
        conversation_id: ConversationId,
        message: impl Into<String>,
        form: Option<Vec<FormField>>,
        url: Option<String>,
    ) -> Self {
        Self {
            request_id: request_id.into(),
            server_name: server_name.into(),
            conversation_id,
            message: message.into(),
            form,
            url,
        }
    }

    /// Copies all configured field defaults into an owned map.
    pub fn initial_values(&self) -> Result<BTreeMap<String, FormValue>, CodexError> {
        crate::native_values::sync_elicitation_initial_values(self)
    }

    /// Validates submitted content against the complete form shape.
    pub fn validate(
        &self,
        content: &BTreeMap<String, FormValue>,
    ) -> Result<ElicitationValidation, CodexError> {
        crate::native_values::sync_elicitation_validate(self, content)
    }

    /// Creates an accepted, deeply owned response when content is valid.
    pub fn accept(
        &self,
        content: &BTreeMap<String, FormValue>,
    ) -> Result<ElicitationResponse, CodexError> {
        crate::native_values::sync_elicitation_accept(self, content)
    }

    /// Whether a response has the exact action/content shape accepted by this request.
    pub fn accepts(&self, response: &ElicitationResponse) -> Result<bool, CodexError> {
        crate::native_values::sync_elicitation_accepts(self, response)
    }
}

/// Elicitation response.
#[derive(Clone, Debug, PartialEq)]
pub struct ElicitationResponse {
    /// Response action.
    pub action: ElicitationAction,
    /// Response content.
    pub content: BTreeMap<String, FormValue>,
}

impl ElicitationResponse {
    /// Creates an elicitation response.
    pub fn new(action: ElicitationAction, content: BTreeMap<String, FormValue>) -> Self {
        Self { action, content }
    }

    /// Creates an empty decline response.
    pub fn decline() -> Result<Self, CodexError> {
        crate::native_values::sync_elicitation_response_decline()
    }

    /// Creates an empty cancellation response.
    pub fn cancel() -> Result<Self, CodexError> {
        crate::native_values::sync_elicitation_response_cancel()
    }
}

/// Command hook handler.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CommandHookHandler {
    /// Command text.
    pub command: String,
    /// Whether asynchronous.
    pub is_async: bool,
}

impl CommandHookHandler {
    /// Creates a command handler.
    pub fn new(command: impl Into<String>, is_async: bool) -> Self {
        Self {
            command: command.into(),
            is_async,
        }
    }
}

/// MCP-tool hook handler.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct McpToolHookHandler {
    /// Server name.
    pub server: String,
    /// Tool name.
    pub tool: String,
}

impl McpToolHookHandler {
    /// Creates an MCP-tool handler.
    pub fn new(server: impl Into<String>, tool: impl Into<String>) -> Self {
        Self {
            server: server.into(),
            tool: tool.into(),
        }
    }
}

/// Prompt hook singleton.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct PromptHookHandler;

impl PromptHookHandler {
    /// Canonical prompt handler.
    pub const INSTANCE: Self = Self;
}

/// Agent hook singleton.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct AgentHookHandler;

impl AgentHookHandler {
    /// Canonical agent handler.
    pub const INSTANCE: Self = Self;
}

/// Configured hook handler.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum HookHandler {
    /// Command handler.
    Command(CommandHookHandler),
    /// MCP-tool handler.
    McpTool(McpToolHookHandler),
    /// Prompt handler.
    Prompt(PromptHookHandler),
    /// Agent handler.
    Agent(AgentHookHandler),
}

/// Immutable hook definition.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Hook {
    /// Stable key.
    pub key: String,
    /// Current content hash.
    pub current_hash: String,
    /// Whether enabled.
    pub is_enabled: bool,
    /// Event name.
    pub event_name: String,
    /// Handler.
    pub handler: HookHandler,
    /// Whether managed.
    pub is_managed: bool,
    /// Source identifier.
    pub source: String,
    /// Source path.
    pub source_path: String,
    /// Timeout in seconds.
    pub timeout_seconds: i64,
    /// Trust status.
    pub trust_status: HookTrustStatus,
    /// Optional matcher.
    pub matcher: Option<String>,
    /// Optional plugin ID.
    pub plugin_id: Option<String>,
    /// Optional status message.
    pub status_message: Option<String>,
    /// Resolved origin.
    pub origin: ResourceOrigin,
    /// Whether removable.
    pub can_uninstall: bool,
}

impl Hook {
    /// Creates a hook snapshot and resolves its origin when omitted.
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        key: impl Into<String>,
        current_hash: impl Into<String>,
        is_enabled: bool,
        event_name: impl Into<String>,
        handler: HookHandler,
        is_managed: bool,
        source: impl Into<String>,
        source_path: impl Into<String>,
        timeout_seconds: i64,
        trust_status: HookTrustStatus,
        matcher: Option<String>,
        plugin_id: Option<String>,
        status_message: Option<String>,
        origin: Option<ResourceOrigin>,
        can_uninstall: bool,
    ) -> Self {
        let source = source.into();
        let origin = origin.unwrap_or_else(|| resolve_hook_origin(&source, is_managed, &plugin_id));
        Self {
            key: key.into(),
            current_hash: current_hash.into(),
            is_enabled,
            event_name: event_name.into(),
            handler,
            is_managed,
            source,
            source_path: source_path.into(),
            timeout_seconds,
            trust_status,
            matcher,
            plugin_id,
            status_message,
            origin,
            can_uninstall,
        }
    }

    /// Whether the hook may be trusted.
    pub fn can_trust(&self) -> bool {
        matches!(
            self.trust_status,
            HookTrustStatus::Untrusted | HookTrustStatus::Modified
        )
    }
}

fn resolve_hook_origin(
    source: &str,
    is_managed: bool,
    plugin_id: &Option<String>,
) -> ResourceOrigin {
    if plugin_id.is_some() || source == "PLUGIN" {
        ResourceOrigin::Plugin
    } else if is_managed
        || matches!(
            source,
            "SYSTEM"
                | "MDM"
                | "CLOUD_REQUIREMENTS"
                | "CLOUD_MANAGED_CONFIG"
                | "LEGACY_MANAGED_CONFIG_FILE"
                | "LEGACY_MANAGED_CONFIG_MDM"
        )
    {
        ResourceOrigin::Managed
    } else {
        match source {
            "USER" => ResourceOrigin::User,
            "PROJECT" => ResourceOrigin::Workspace,
            _ => ResourceOrigin::Unknown,
        }
    }
}

/// Immutable hook catalog.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HookCatalog {
    /// Ordered hooks.
    pub hooks: Vec<Hook>,
    /// Ordered warnings.
    pub warnings: Vec<String>,
    /// Ordered errors.
    pub errors: Vec<String>,
}

impl HookCatalog {
    /// Creates a hook catalog.
    pub fn new(hooks: Vec<Hook>, warnings: Vec<String>, errors: Vec<String>) -> Self {
        Self {
            hooks,
            warnings,
            errors,
        }
    }
}

/// Connector integration.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ConnectorIntegration {
    /// Connector value.
    pub connector: Connector,
}

impl ConnectorIntegration {
    /// Creates a connector integration.
    pub fn new(connector: Connector) -> Self {
        Self { connector }
    }

    /// Stable integration ID.
    pub fn id(&self) -> &str {
        &self.connector.id
    }

    /// Integration display name.
    pub fn display_name(&self) -> &str {
        &self.connector.name
    }
}

/// MCP-server integration.
#[derive(Clone, Debug, PartialEq)]
pub struct McpServerIntegration {
    /// MCP server.
    pub server: McpServer,
}

impl McpServerIntegration {
    /// Creates an MCP-server integration.
    pub fn new(server: McpServer) -> Self {
        Self { server }
    }

    /// Stable integration ID.
    pub fn id(&self) -> &str {
        &self.server.name
    }

    /// Integration display name.
    pub fn display_name(&self) -> &str {
        &self.server.display_name
    }
}

/// Authorizable integration.
#[derive(Clone, Debug, PartialEq)]
pub enum Integration {
    /// Connector integration.
    Connector(ConnectorIntegration),
    /// MCP-server integration.
    McpServer(Box<McpServerIntegration>),
}

impl Integration {
    /// Stable integration ID.
    pub fn id(&self) -> &str {
        match self {
            Self::Connector(value) => value.id(),
            Self::McpServer(value) => value.id(),
        }
    }

    /// Integration display name.
    pub fn display_name(&self) -> &str {
        match self {
            Self::Connector(value) => value.display_name(),
            Self::McpServer(value) => value.display_name(),
        }
    }
}

/// Immutable integration-authorization state.
#[derive(Clone, Debug, PartialEq)]
pub struct IntegrationAuthorizationState {
    /// Current status.
    pub status: IntegrationAuthorizationStatus,
    /// Optional target.
    pub target: Option<Integration>,
    /// Optional failure.
    pub failure: Option<CodexFailure>,
}

impl IntegrationAuthorizationState {
    /// Creates authorization state.
    pub fn new(
        status: IntegrationAuthorizationStatus,
        target: Option<Integration>,
        failure: Option<CodexFailure>,
    ) -> Self {
        Self {
            status,
            target,
            failure,
        }
    }
}

/// Pending approval.
#[derive(Clone, Debug)]
pub struct PendingApproval {
    /// Request identifier.
    pub request_id: String,
    /// Conversation identifier.
    pub conversation_id: ConversationId,
    /// Approval title.
    pub title: String,
    /// Approval details.
    pub details: String,
    binding_identity: Option<Arc<BindingIdentity>>,
}

impl PendingApproval {
    /// Creates a pending approval.
    pub fn new(
        request_id: impl Into<String>,
        conversation_id: ConversationId,
        title: impl Into<String>,
        details: impl Into<String>,
    ) -> Self {
        Self {
            request_id: request_id.into(),
            conversation_id,
            title: title.into(),
            details: details.into(),
            binding_identity: None,
        }
    }

    pub(crate) fn with_binding_identity(mut self, identity: Arc<BindingIdentity>) -> Self {
        self.binding_identity = Some(identity);
        self
    }

    pub(crate) fn binding_identity(&self) -> Option<&Arc<BindingIdentity>> {
        self.binding_identity.as_ref()
    }
}

impl PartialEq for PendingApproval {
    fn eq(&self, other: &Self) -> bool {
        self.request_id == other.request_id
            && self.conversation_id == other.conversation_id
            && self.title == other.title
            && self.details == other.details
    }
}

impl Eq for PendingApproval {}

/// Pending elicitation.
#[derive(Clone, Debug)]
pub struct PendingElicitation {
    /// Elicitation request.
    pub elicitation: Elicitation,
    binding_identity: Option<Arc<BindingIdentity>>,
}

impl PendingElicitation {
    /// Creates a pending elicitation.
    pub fn new(elicitation: Elicitation) -> Self {
        Self {
            elicitation,
            binding_identity: None,
        }
    }

    /// Request identifier.
    pub fn request_id(&self) -> &str {
        &self.elicitation.request_id
    }

    /// Conversation identifier.
    pub fn conversation_id(&self) -> &ConversationId {
        &self.elicitation.conversation_id
    }

    pub(crate) fn with_binding_identity(mut self, identity: Arc<BindingIdentity>) -> Self {
        self.binding_identity = Some(identity);
        self
    }

    pub(crate) fn binding_identity(&self) -> Option<&Arc<BindingIdentity>> {
        self.binding_identity.as_ref()
    }
}

impl PartialEq for PendingElicitation {
    fn eq(&self, other: &Self) -> bool {
        self.elicitation == other.elicitation
    }
}

pub(crate) struct BindingIdentity;

impl Debug for BindingIdentity {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("BindingIdentity")
    }
}

/// Pending user interaction.
#[derive(Clone, Debug, PartialEq)]
pub enum PendingInteraction {
    /// Approval request.
    Approval(PendingApproval),
    /// Elicitation request.
    Elicitation(PendingElicitation),
}

impl PendingInteraction {
    /// Request identifier.
    pub fn request_id(&self) -> &str {
        match self {
            Self::Approval(value) => &value.request_id,
            Self::Elicitation(value) => value.request_id(),
        }
    }

    /// Conversation identifier.
    pub fn conversation_id(&self) -> &ConversationId {
        match self {
            Self::Approval(value) => &value.conversation_id,
            Self::Elicitation(value) => value.conversation_id(),
        }
    }
}

/// Immutable interaction state.
#[derive(Clone, Debug, PartialEq)]
pub struct InteractionState {
    /// Ordered pending interactions.
    pub pending: Vec<PendingInteraction>,
    /// Request IDs being resolved.
    pub resolving_request_ids: BTreeSet<String>,
    /// Optional failure.
    pub failure: Option<CodexFailure>,
}

impl InteractionState {
    /// Creates interaction state.
    pub fn new(
        pending: Vec<PendingInteraction>,
        resolving_request_ids: BTreeSet<String>,
        failure: Option<CodexFailure>,
    ) -> Self {
        Self {
            pending,
            resolving_request_ids,
            failure,
        }
    }

    /// Returns pending interactions for a conversation without losing order or identity.
    pub fn pending_for(
        &self,
        conversation_id: &ConversationId,
    ) -> Result<Vec<&PendingInteraction>, CodexError> {
        crate::native_values::sync_interaction_state_pending_for(self, conversation_id).map(
            |indices| {
                indices
                    .into_iter()
                    .map(|index| &self.pending[index])
                    .collect()
            },
        )
    }

    /// Whether this exact live pending value is currently being resolved.
    pub fn is_resolving(&self, interaction: &PendingInteraction) -> Result<bool, CodexError> {
        crate::native_values::sync_interaction_state_is_resolving(self, interaction)
    }
}

/// Complete immutable conversation state.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AgentConversationState {
    /// Lifecycle status.
    pub status: ConversationStatus,
    /// Optional conversation identifier.
    pub conversation_id: Option<ConversationId>,
    /// Optional conversation value.
    pub conversation: Option<ConversationSnapshot>,
    /// Current turn progress.
    pub turn_progress: TurnProgress,
    /// Optional model.
    pub model: Option<String>,
    /// Optional effort.
    pub effort: Option<String>,
    /// Optional service tier.
    pub service_tier: Option<String>,
    /// Optional failure.
    pub failure: Option<CodexFailure>,
}

impl AgentConversationState {
    /// Creates complete conversation state.
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        status: ConversationStatus,
        conversation_id: Option<ConversationId>,
        conversation: Option<ConversationSnapshot>,
        turn_progress: TurnProgress,
        model: Option<String>,
        effort: Option<String>,
        service_tier: Option<String>,
        failure: Option<CodexFailure>,
    ) -> Self {
        Self {
            status,
            conversation_id,
            conversation,
            turn_progress,
            model,
            effort,
            service_tier,
            failure,
        }
    }

    /// Whether a turn may start.
    pub fn can_start_turn(&self) -> bool {
        self.conversation_id.is_some()
            && (self.status == ConversationStatus::Ready
                || self.status == ConversationStatus::Failed
                    && self
                        .failure
                        .as_ref()
                        .is_some_and(|failure| failure.recoverable))
    }

    /// Whether the conversation may reload.
    pub fn can_reload(&self) -> bool {
        self.conversation_id.is_some()
            && matches!(
                self.status,
                ConversationStatus::Ready | ConversationStatus::Failed
            )
    }

    /// Whether the current turn may be cancelled.
    pub fn can_cancel_turn(&self) -> bool {
        matches!(
            self.status,
            ConversationStatus::StartingTurn | ConversationStatus::RunningTurn
        )
    }
}

/// Validated path workspace selection.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PathWorkspaceSelection {
    /// Workspace path.
    pub path: String,
}

impl PathWorkspaceSelection {
    /// Creates a path selection.
    pub fn new(path: impl Into<String>) -> Result<Self, CodexError> {
        let path = path.into();
        if path.trim().is_empty() || path.contains('\0') {
            return Err(invalid("workspace path is invalid"));
        }
        Ok(Self { path })
    }
}

/// Available workspace resolution.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct WorkspaceAvailable {
    /// Available workspace.
    pub workspace: Workspace,
}

impl WorkspaceAvailable {
    /// Creates an available resolution.
    pub fn new(workspace: Workspace) -> Self {
        Self { workspace }
    }
}

/// Required workspace selection.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct WorkspaceSelectionRequired {
    /// Selection reason.
    pub reason: WorkspaceSelectionReason,
    /// User-facing guidance.
    pub message: String,
}

impl WorkspaceSelectionRequired {
    /// Creates a required resolution.
    pub fn new(reason: WorkspaceSelectionReason, message: impl Into<String>) -> Self {
        Self {
            reason,
            message: message.into(),
        }
    }
}

/// Workspace-resolution result.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum WorkspaceResolution {
    /// Workspace is available.
    Available(WorkspaceAvailable),
    /// Selection is required.
    SelectionRequired(WorkspaceSelectionRequired),
}

/// Canonical new host state.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct HostStateNew;

impl HostStateNew {
    /// Canonical new state.
    pub const INSTANCE: Self = Self;
}

/// Canonical restoring host state.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct HostStateRestoring;

impl HostStateRestoring {
    /// Canonical restoring state.
    pub const INSTANCE: Self = Self;
}

/// Workspace-required host state.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HostStateWorkspaceRequired {
    /// Selection requirement.
    pub requirement: WorkspaceSelectionRequired,
}

impl HostStateWorkspaceRequired {
    /// Creates workspace-required state.
    pub fn new(requirement: WorkspaceSelectionRequired) -> Self {
        Self { requirement }
    }
}

/// Runtime-preparing host state.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HostStatePreparing {
    /// Selected workspace.
    pub workspace: Workspace,
}

impl HostStatePreparing {
    /// Creates preparing state.
    pub fn new(workspace: Workspace) -> Self {
        Self { workspace }
    }
}

/// Failed host state.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HostStateFailed {
    /// Optional selected workspace.
    pub workspace: Option<Workspace>,
    /// Structured failure.
    pub failure: CodexFailure,
}

impl HostStateFailed {
    /// Creates failed state.
    pub fn new(workspace: Option<Workspace>, failure: CodexFailure) -> Self {
        Self { workspace, failure }
    }
}

/// Canonical closed host state.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct HostStateClosed;

impl HostStateClosed {
    /// Canonical closed state.
    pub const INSTANCE: Self = Self;
}
