use libloading::Library;
use std::ffi::c_void;
use std::mem::ManuallyDrop;
use std::path::Path;

#[cfg(test)]
use std::collections::BTreeSet;
#[cfg(test)]
use std::sync::{LazyLock, Mutex};

pub(crate) enum LoadError {
    Open(String),
    MissingSymbol(String),
    UnsupportedAbi(u32),
}

pub(crate) const STATUS_OK: i32 = 0;
pub(crate) const STATUS_BUSY: i32 = 6;
pub(crate) const STATUS_INTERNAL_ERROR: i32 = 8;
pub(crate) const STATUS_BUFFER_TOO_SMALL: i32 = 9;
#[cfg(test)]
pub(crate) const STATUS_NOT_READY: i32 = 13;
pub(crate) const STATUS_OPERATION_FAILED: i32 = 14;

pub(crate) const ABI_VERSION: u32 = (1 << 24) | (12 << 16);

macro_rules! opaque {
    ($($name:ident),+ $(,)?) => {$(
        #[repr(C)]
        pub(crate) struct $name {
            _private: [u8; 0],
        }
    )+};
}

opaque!(
    Context,
    Host,
    Agent,
    Authentication,
    Connectors,
    Hooks,
    IntegrationAuthorization,
    Interactions,
    McpServers,
    Models,
    Plugins,
    Skills,
    Conversations,
    Conversation,
    Operation,
    Subscription,
    Snapshot,
    Failure,
    AuthenticationState,
    AuthenticationMethodApiKey,
    AuthenticationMethodChatGptBrowser,
    AuthenticationMethodChatGptDeviceCode,
    Integration,
    IntegrationAuthorizationState,
    Hook,
    HookCatalog,
    HookHandler,
    HookHandlerAgent,
    HookHandlerCommand,
    HookHandlerMcpTool,
    HookHandlerPrompt,
    IntegrationConnector,
    IntegrationMcpServer,
    ClientInfoValue,
    Connector,
    ConversationId,
    ConversationSettings,
    ConversationSummary,
    ConversationValue,
    Invocation,
    InvocationPlugin,
    InvocationSkill,
    Message,
    ElicitationValidation,
    ElicitationValidationIssue,
    AuthorizationUrl,
    Elicitation,
    ElicitationResponse,
    FormBooleanValue,
    FormContent,
    FormField,
    FormNumberValue,
    FormOption,
    FormTextListValue,
    FormTextValue,
    FormValue,
    HookActivity,
    McpEnvironmentVariable,
    McpOauthConfiguration,
    McpToolConfiguration,
    McpTransport,
    McpTransportHttp,
    McpTransportStdio,
    McpServerConfiguration,
    McpServer,
    Model,
    PlanProgress,
    PlanStep,
    PendingApproval,
    PendingElicitation,
    PendingInteraction,
    PendingInteractionList,
    PluginCatalog,
    PluginDetail,
    PluginInstallResult,
    PluginReference,
    PluginSkill,
    PluginSummary,
    ServiceTier,
    Skill,
    SkillCatalog,
    SkillChunk,
    TurnProgress,
    TurnRequest,
    Workspace,
    InteractionState,
);

#[repr(C)]
#[derive(Clone, Copy)]
pub(crate) struct StringView {
    pub(crate) data: *const u8,
    pub(crate) size: usize,
}

impl StringView {
    pub(crate) fn new(value: &str) -> Self {
        Self {
            data: value.as_ptr(),
            size: value.len(),
        }
    }

    pub(crate) const fn absent() -> Self {
        Self {
            data: std::ptr::null(),
            size: 0,
        }
    }
}

#[repr(C)]
pub(crate) struct ClientInfo {
    pub(crate) struct_size: u32,
    pub(crate) name: StringView,
    pub(crate) title: StringView,
    pub(crate) version: StringView,
}

#[repr(C)]
pub(crate) struct HostOptions {
    pub(crate) struct_size: u32,
    pub(crate) bundle_directory: StringView,
    pub(crate) data_directory: StringView,
    pub(crate) client_info: ClientInfo,
}

#[repr(C)]
pub(crate) struct PathWorkspaceSelection {
    pub(crate) struct_size: u32,
    pub(crate) path: StringView,
}

#[repr(C)]
pub(crate) struct ConversationOpenOptions {
    pub(crate) struct_size: u32,
    pub(crate) has_conversation_id: i32,
    pub(crate) conversation_id: StringView,
    pub(crate) has_approval_preset: i32,
    pub(crate) approval_preset: i32,
    pub(crate) has_service_tier: i32,
    pub(crate) service_tier: StringView,
}

pub(crate) type OperationCallback = unsafe extern "C" fn(*mut Context, *mut Operation, *mut c_void);
pub(crate) type StateCallback =
    unsafe extern "C" fn(*mut Context, *mut Subscription, i32, *mut Snapshot, i32, *mut c_void);

type AbiVersion = unsafe extern "C" fn() -> u32;
type AbiCompatible = unsafe extern "C" fn(u32) -> i32;
type ContextCreate = unsafe extern "C" fn(*mut *mut Context) -> i32;
type ContextDestroy = unsafe extern "C" fn(*mut *mut Context) -> i32;
type HostCreate = unsafe extern "C" fn(*mut Context, *const HostOptions, *mut *mut Host) -> i32;
type HostRelease = unsafe extern "C" fn(*mut Context, *mut *mut Host) -> i32;
type HostOperation = unsafe extern "C" fn(
    *mut Context,
    *mut Host,
    OperationCallback,
    *mut c_void,
    *mut *mut Operation,
) -> i32;
type HostSelectWorkspace = unsafe extern "C" fn(
    *mut Context,
    *mut Host,
    *const PathWorkspaceSelection,
    OperationCallback,
    *mut c_void,
    *mut *mut Operation,
) -> i32;
type HostStateGet = unsafe extern "C" fn(*mut Context, *mut Host, *mut *mut Snapshot) -> i32;
type HostStateSubscribe = unsafe extern "C" fn(
    *mut Context,
    *mut Host,
    StateCallback,
    *mut c_void,
    *mut *mut Subscription,
) -> i32;
type AgentRelease = unsafe extern "C" fn(*mut Context, *mut *mut Agent) -> i32;
type AgentConversations =
    unsafe extern "C" fn(*mut Context, *mut Agent, *mut *mut Conversations) -> i32;
type ConversationsRelease = unsafe extern "C" fn(*mut Context, *mut *mut Conversations) -> i32;
type ConversationsStateGet =
    unsafe extern "C" fn(*mut Context, *mut Conversations, *mut *mut Snapshot) -> i32;
type ConversationsStateSubscribe = unsafe extern "C" fn(
    *mut Context,
    *mut Conversations,
    StateCallback,
    *mut c_void,
    *mut *mut Subscription,
) -> i32;
type ConversationsOpen = unsafe extern "C" fn(
    *mut Context,
    *mut Conversations,
    *const ConversationOpenOptions,
    OperationCallback,
    *mut c_void,
    *mut *mut Operation,
) -> i32;
type ConversationRelease = unsafe extern "C" fn(*mut Context, *mut *mut Conversation) -> i32;
type ConversationIsSame =
    unsafe extern "C" fn(*mut Context, *mut Conversation, *mut Conversation, *mut i32) -> i32;
type ConversationStringOperation = unsafe extern "C" fn(
    *mut Context,
    *mut Conversation,
    *const StringView,
    OperationCallback,
    *mut c_void,
    *mut *mut Operation,
) -> i32;
type ConversationOperation = unsafe extern "C" fn(
    *mut Context,
    *mut Conversation,
    OperationCallback,
    *mut c_void,
    *mut *mut Operation,
) -> i32;
type ConversationStateGet =
    unsafe extern "C" fn(*mut Context, *mut Conversation, *mut *mut Snapshot) -> i32;
type ConversationStateSubscribe = unsafe extern "C" fn(
    *mut Context,
    *mut Conversation,
    StateCallback,
    *mut c_void,
    *mut *mut Subscription,
) -> i32;
type OperationCancel = unsafe extern "C" fn(*mut Context, *mut Operation) -> i32;
type OperationResult = unsafe extern "C" fn(*mut Context, *mut Operation, *mut i32) -> i32;
type OperationConversation = unsafe extern "C" fn(
    *mut Context,
    *mut Conversations,
    *mut Operation,
    *mut *mut Conversation,
) -> i32;
type OperationFailure =
    unsafe extern "C" fn(*mut Context, *mut Operation, *mut *mut Failure) -> i32;
type OperationDestroy = unsafe extern "C" fn(*mut Context, *mut *mut Operation) -> i32;
type SubscriptionDestroy = unsafe extern "C" fn(*mut Context, *mut *mut Subscription) -> i32;
type SnapshotDestroy = unsafe extern "C" fn(*mut Context, *mut *mut Snapshot) -> i32;
type HostStateKind = unsafe extern "C" fn(*mut Context, *mut Snapshot, *mut i32) -> i32;
type HostStateAgent =
    unsafe extern "C" fn(*mut Context, *mut Host, *mut Snapshot, *mut *mut Agent) -> i32;
type HostStateFailure = unsafe extern "C" fn(*mut Context, *mut Snapshot, *mut *mut Failure) -> i32;
type HostStateHasWorkspace = unsafe extern "C" fn(*mut Context, *mut Snapshot, *mut i32) -> i32;
type StringCopy =
    unsafe extern "C" fn(*mut Context, *mut Snapshot, *mut u8, usize, *mut usize) -> i32;
type HostStateReason = unsafe extern "C" fn(*mut Context, *mut Snapshot, *mut i32) -> i32;
type ActiveConversation = unsafe extern "C" fn(
    *mut Context,
    *mut Conversations,
    *mut Snapshot,
    *mut *mut Conversation,
) -> i32;
type ConversationStateStatus = unsafe extern "C" fn(*mut Context, *mut Snapshot, *mut i32) -> i32;
type ConversationStateFailure =
    unsafe extern "C" fn(*mut Context, *mut Snapshot, *mut *mut Failure) -> i32;
type FailureRelease = unsafe extern "C" fn(*mut Context, *mut *mut Failure) -> i32;
type FailureStringCopy =
    unsafe extern "C" fn(*mut Context, *mut Failure, *mut u8, usize, *mut usize) -> i32;
type FailureRecoverable = unsafe extern "C" fn(*mut Context, *mut Failure, *mut i32) -> i32;

macro_rules! api {
    (
        abi_version: $abi_version_ty:ty => $abi_version_symbol:literal,
        abi_is_compatible: $abi_compatible_ty:ty => $abi_compatible_symbol:literal,
        $($field:ident: $ty:ty => $symbol:literal),+ $(,)?
    ) => {
        #[allow(dead_code)]
        pub(crate) struct Api {
            _library: ManuallyDrop<Library>,
            pub(crate) abi_version: $abi_version_ty,
            $(pub(crate) $field: $ty,)+
        }

        impl Api {
            pub(crate) fn load(path: &Path) -> Result<Self, LoadError> {
                // SAFETY: the library remains owned by Api for at least as long as every copied
                // function pointer, and every symbol is loaded with its exact public C ABI type.
                let library = unsafe { Library::new(path) }
                    .map_err(|error| LoadError::Open(format!("could not load {}: {error}", path.display())))?;
                // Resolve only the stable compatibility prefix before touching the
                // version-dependent symbol set.
                // SAFETY: these two symbols form the stable ABI compatibility prefix.
                let abi_version = unsafe {
                    *library
                        .get::<$abi_version_ty>(concat!($abi_version_symbol, "\0").as_bytes())
                        .map_err(|error| LoadError::MissingSymbol(format!("missing C SDK symbol {}: {error}", $abi_version_symbol)))?
                };
                // SAFETY: this symbol is the other stable ABI compatibility-prefix function.
                let abi_is_compatible = unsafe {
                    *library
                        .get::<$abi_compatible_ty>(concat!($abi_compatible_symbol, "\0").as_bytes())
                        .map_err(|error| LoadError::MissingSymbol(format!("missing C SDK symbol {}: {error}", $abi_compatible_symbol)))?
                };
                // SAFETY: both version functions accept no borrowed memory.
                let actual = unsafe { abi_version() };
                // SAFETY: the compatibility query accepts an encoded integer only.
                let compatible = unsafe { abi_is_compatible(ABI_VERSION) };
                if actual >> 24 != 1 || compatible != 1 {
                    return Err(LoadError::UnsupportedAbi(actual));
                }
                $(
                    // SAFETY: the stable C SDK header defines this exact symbol and signature.
                    let $field = unsafe {
                        *library
                            .get::<$ty>(concat!($symbol, "\0").as_bytes())
                            .map_err(|error| LoadError::MissingSymbol(format!("missing C SDK symbol {}: {error}", $symbol)))?
                    };
                )+
                // Kotlin/Native owns process-wide runtime state and cannot be safely unloaded.
                Ok(Self { _library: ManuallyDrop::new(library), abi_version, $($field,)+ })
            }
        }
    };
}

api!(
    abi_version: AbiVersion => "codex_agent_abi_version",
    abi_is_compatible: AbiCompatible => "codex_agent_abi_is_compatible",
    context_create: ContextCreate => "codex_agent_context_create",
    context_destroy: ContextDestroy => "codex_agent_context_destroy",
    host_create: HostCreate => "codex_agent_host_create",
    host_release: HostRelease => "codex_agent_host_release",
    host_start: HostOperation => "codex_agent_host_start",
    host_select_workspace: HostSelectWorkspace => "codex_agent_host_select_workspace",
    host_close: HostOperation => "codex_agent_host_close",
    host_state_get: HostStateGet => "codex_agent_host_state_get",
    host_state_subscribe: HostStateSubscribe => "codex_agent_host_state_subscribe",
    agent_release: AgentRelease => "codex_agent_agent_release",
    agent_conversations: AgentConversations => "codex_agent_agent_conversations",
    conversations_release: ConversationsRelease => "codex_agent_conversations_release",
    conversations_active_get: ConversationsStateGet => "codex_agent_conversations_active_get",
    conversations_active_subscribe: ConversationsStateSubscribe => "codex_agent_conversations_active_subscribe",
    conversations_open: ConversationsOpen => "codex_agent_conversations_open",
    conversation_release: ConversationRelease => "codex_agent_conversation_release",
    conversation_is_same: ConversationIsSame => "codex_agent_conversation_is_same",
    conversation_send: ConversationStringOperation => "codex_agent_conversation_send",
    conversation_run_shell_command: ConversationStringOperation => "codex_agent_conversation_run_shell_command",
    conversation_reload: ConversationOperation => "codex_agent_conversation_reload",
    conversation_cancel_turn: ConversationOperation => "codex_agent_conversation_cancel_turn",
    conversation_close: ConversationOperation => "codex_agent_conversation_close",
    conversation_state_get: ConversationStateGet => "codex_agent_conversation_state_get",
    conversation_state_subscribe: ConversationStateSubscribe => "codex_agent_conversation_state_subscribe",
    operation_cancel: OperationCancel => "codex_agent_operation_cancel",
    operation_result: OperationResult => "codex_agent_operation_result",
    operation_conversation: OperationConversation => "codex_agent_operation_conversation",
    operation_failure: OperationFailure => "codex_agent_operation_failure",
    operation_destroy: OperationDestroy => "codex_agent_operation_destroy",
    subscription_destroy: SubscriptionDestroy => "codex_agent_subscription_destroy",
    snapshot_destroy: SnapshotDestroy => "codex_agent_snapshot_destroy",
    host_state_kind: HostStateKind => "codex_agent_host_state_kind",
    host_state_agent: HostStateAgent => "codex_agent_host_state_agent",
    host_state_failure: HostStateFailure => "codex_agent_host_state_failure",
    host_state_has_workspace: HostStateHasWorkspace => "codex_agent_host_state_has_workspace",
    host_state_workspace_path_copy: StringCopy => "codex_agent_host_state_workspace_path_copy",
    host_state_workspace_display_name_copy: StringCopy => "codex_agent_host_state_workspace_display_name_copy",
    host_state_requirement_reason: HostStateReason => "codex_agent_host_state_requirement_reason",
    host_state_requirement_message_copy: StringCopy => "codex_agent_host_state_requirement_message_copy",
    active_conversation: ActiveConversation => "codex_agent_active_conversation",
    conversation_state_status: ConversationStateStatus => "codex_agent_conversation_state_status",
    conversation_state_failure: ConversationStateFailure => "codex_agent_conversation_state_failure",
    failure_release: FailureRelease => "codex_agent_failure_release",
    failure_code_copy: FailureStringCopy => "codex_agent_failure_code_copy",
    failure_message_copy: FailureStringCopy => "codex_agent_failure_message_copy",
    failure_is_recoverable: FailureRecoverable => "codex_agent_failure_is_recoverable",
);

pub(crate) unsafe fn load_value_symbol<T: Copy>(
    api: &Api,
    name: &'static [u8],
) -> Result<T, String> {
    // SAFETY: callers bind each stable public name to its reviewed codex_agent.h signature.
    match unsafe { api._library.get::<T>(name) } {
        Ok(symbol) => Ok(*symbol),
        Err(error) => Err(format!(
            "missing C SDK value symbol {}: {error}",
            String::from_utf8_lossy(name).trim_end_matches('\0')
        )),
    }
}

#[cfg(test)]
static TEST_CALLS: LazyLock<Mutex<BTreeSet<String>>> =
    LazyLock::new(|| Mutex::new(BTreeSet::new()));

#[cfg(test)]
static TEST_CALL_SESSION: LazyLock<Mutex<()>> = LazyLock::new(|| Mutex::new(()));

#[cfg(test)]
pub(crate) fn test_call_session() -> std::sync::MutexGuard<'static, ()> {
    TEST_CALL_SESSION
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

#[cfg(test)]
pub(crate) fn test_trace_invocation(name: &str) {
    TEST_CALLS
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .insert(name.to_owned());
}

#[cfg(test)]
pub(crate) fn test_clear_calls() {
    TEST_CALLS
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .clear();
}

#[cfg(test)]
pub(crate) fn test_calls() -> BTreeSet<String> {
    TEST_CALLS
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .clone()
}
