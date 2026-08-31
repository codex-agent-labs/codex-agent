from __future__ import annotations

from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TypeAlias

from ._enums import (
    ApprovalPreset,
    AuthenticationStatus,
    AuthorizationPurpose,
    Capability,
    CollaborationMode,
    ElicitationAction,
    FormFieldType,
    FormStringFormat,
    HookTrustStatus,
    IntegrationAuthorizationStatus,
    MessageRole,
    ResourceOrigin,
    WorkspaceSelectionReason,
)
from ._errors import Failure
from ._mcp_values import McpServer
from ._models import ConversationId, ConversationSummary, Workspace
from ._values import (
    Connector,
    ElicitationValidation,
    FormOption,
)


@dataclass(frozen=True, slots=True)
class AuthorizationUrl:
    value: str
    purpose: AuthorizationPurpose

    def __post_init__(self) -> None:
        symbol = (
            "codex_agent_authorization_url_chat_gpt"
            if self.purpose is AuthorizationPurpose.CHAT_GPT
            else "codex_agent_authorization_url_external"
        )
        from ._value_native import authorization_url_parts

        value, purpose = authorization_url_parts(symbol, self.value)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "purpose", purpose)

    @classmethod
    def _native(cls, symbol: str, value: str) -> AuthorizationUrl:
        from ._value_native import authorization_url_parts

        instance = object.__new__(cls)
        native_value, purpose = authorization_url_parts(symbol, value)
        object.__setattr__(instance, "value", native_value)
        object.__setattr__(instance, "purpose", purpose)
        return instance

    @classmethod
    def chat_gpt(cls, value: str) -> AuthorizationUrl:
        return cls._native("codex_agent_authorization_url_chat_gpt", value)

    @classmethod
    def external(cls, value: str) -> AuthorizationUrl:
        return cls._native("codex_agent_authorization_url_external", value)

    def __repr__(self) -> str:
        return f"AuthorizationUrl(purpose={self.purpose.name})"


@dataclass(frozen=True, slots=True)
class ApiKeyAuthentication:
    value: str

    def __post_init__(self) -> None:
        if not self.value or self.value.isspace():
            raise ValueError("API key must not be blank")


@dataclass(frozen=True, slots=True)
class ChatGptBrowserAuthentication:
    pass


@dataclass(frozen=True, slots=True)
class ChatGptDeviceCodeAuthentication:
    pass


CHAT_GPT_BROWSER_AUTHENTICATION = ChatGptBrowserAuthentication()
CHAT_GPT_DEVICE_CODE_AUTHENTICATION = ChatGptDeviceCodeAuthentication()


@dataclass(frozen=True, slots=True)
class AuthenticationState:
    status: AuthenticationStatus = AuthenticationStatus.SIGNED_OUT
    pending_sign_in_url: AuthorizationUrl | None = None
    device_verification_url: AuthorizationUrl | None = None
    device_user_code: str | None = None
    failure: Failure | None = None


@dataclass(frozen=True, slots=True)
class FormBooleanValue:
    value: bool


@dataclass(frozen=True, slots=True)
class FormNumberValue:
    value: float


@dataclass(frozen=True, slots=True)
class FormTextValue:
    value: str


@dataclass(frozen=True, slots=True)
class FormTextListValue:
    value: Sequence[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", tuple(self.value))


FormValue: TypeAlias = (
    FormBooleanValue | FormNumberValue | FormTextValue | FormTextListValue
)


@dataclass(frozen=True, slots=True)
class FormField:
    name: str
    title: str
    type: FormFieldType
    description: str | None = None
    is_required: bool = False
    is_secret: bool = False
    format: FormStringFormat | None = None
    default_value: FormValue | None = None
    minimum: float | None = None
    maximum: float | None = None
    minimum_length: int | None = None
    maximum_length: int | None = None
    options: Sequence[FormOption] = ()
    allows_other: bool = False
    minimum_selections: int | None = None
    maximum_selections: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", tuple(self.options))
        for value, label in (
            (self.minimum_length, "minimum length"),
            (self.maximum_length, "maximum length"),
            (self.minimum_selections, "minimum selections"),
            (self.maximum_selections, "maximum selections"),
        ):
            if value is not None and value < 0:
                raise ValueError(f"{label} must not be negative")
        if (
            self.minimum_length is not None
            and self.maximum_length is not None
            and self.minimum_length > self.maximum_length
        ):
            raise ValueError("minimum length must not exceed maximum length")
        if (
            self.minimum_selections is not None
            and self.maximum_selections is not None
            and self.minimum_selections > self.maximum_selections
        ):
            raise ValueError("minimum selections must not exceed maximum selections")

    def accepts(self, value: FormValue | None) -> bool:
        from ._value_native import form_field_accepts

        return form_field_accepts(self, value)


@dataclass(frozen=True, slots=True)
class Elicitation:
    request_id: str
    conversation_id: ConversationId
    server_name: str
    message: str
    url: str | None = None
    form: Sequence[FormField] | None = None

    def __post_init__(self) -> None:
        if self.form is not None:
            object.__setattr__(self, "form", tuple(self.form))

    def initial_values(self) -> Mapping[str, FormValue]:
        from ._value_native import elicitation_initial_values

        return elicitation_initial_values(self)

    def validate(self, content: Mapping[str, FormValue]) -> ElicitationValidation:
        from ._value_native import elicitation_validate

        return elicitation_validate(self, content)

    def accept(self, content: Mapping[str, FormValue]) -> ElicitationResponse:
        from ._value_native import elicitation_accept

        return elicitation_accept(self, content)

    def accepts(self, response: ElicitationResponse) -> bool:
        from ._value_native import elicitation_accepts

        return elicitation_accepts(self, response)


@dataclass(frozen=True, slots=True)
class ElicitationResponse:
    action: ElicitationAction
    content: Mapping[str, FormValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "content", MappingProxyType(dict(self.content)))

    @classmethod
    def decline(cls) -> ElicitationResponse:
        from ._value_native import response_factory

        return response_factory("codex_agent_elicitation_response_decline")

    @classmethod
    def cancel(cls) -> ElicitationResponse:
        from ._value_native import response_factory

        return response_factory("codex_agent_elicitation_response_cancel")


@dataclass(frozen=True, slots=True)
class HookHandlerAgent:
    pass


@dataclass(frozen=True, slots=True)
class HookHandlerPrompt:
    pass


HOOK_HANDLER_AGENT = HookHandlerAgent()
HOOK_HANDLER_PROMPT = HookHandlerPrompt()


@dataclass(frozen=True, slots=True)
class HookHandlerCommand:
    command: str
    is_async: bool = False


@dataclass(frozen=True, slots=True)
class HookHandlerMcpTool:
    server: str
    tool: str


HookHandler: TypeAlias = (
    HookHandlerAgent | HookHandlerCommand | HookHandlerMcpTool | HookHandlerPrompt
)


@dataclass(frozen=True, slots=True)
class Hook:
    key: str
    current_hash: str
    is_enabled: bool
    event_name: str
    handler: HookHandler
    is_managed: bool
    source: str
    source_path: str
    timeout_seconds: int
    trust_status: HookTrustStatus
    matcher: str | None = None
    plugin_id: str | None = None
    status_message: str | None = None
    origin: ResourceOrigin | None = None
    can_uninstall: bool = False

    def __post_init__(self) -> None:
        if self.origin is not None:
            return
        if self.plugin_id is not None or self.source == "PLUGIN":
            origin = ResourceOrigin.PLUGIN
        elif self.is_managed or self.source in {
            "SYSTEM",
            "MDM",
            "CLOUD_REQUIREMENTS",
            "CLOUD_MANAGED_CONFIG",
            "LEGACY_MANAGED_CONFIG_FILE",
            "LEGACY_MANAGED_CONFIG_MDM",
        }:
            origin = ResourceOrigin.MANAGED
        elif self.source == "USER":
            origin = ResourceOrigin.USER
        elif self.source == "PROJECT":
            origin = ResourceOrigin.WORKSPACE
        else:
            origin = ResourceOrigin.UNKNOWN
        object.__setattr__(self, "origin", origin)

    @property
    def can_trust(self) -> bool:
        return self.trust_status in {
            HookTrustStatus.UNTRUSTED,
            HookTrustStatus.MODIFIED,
        }


@dataclass(frozen=True, slots=True)
class HookCatalog:
    hooks: Sequence[Hook]
    warnings: Sequence[str] = ()
    errors: Sequence[str] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "hooks", tuple(self.hooks))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "errors", tuple(self.errors))


class Integration:
    @property
    def id(self) -> str:
        raise NotImplementedError

    @property
    def display_name(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class ConnectorIntegration(Integration):
    connector: Connector

    @property
    def id(self) -> str:
        return self.connector.id

    @property
    def display_name(self) -> str:
        return self.connector.name


@dataclass(frozen=True, slots=True)
class McpServerIntegration(Integration):
    server: McpServer

    @property
    def id(self) -> str:
        return self.server.name

    @property
    def display_name(self) -> str:
        return self.server.display_name


IntegrationValue: TypeAlias = ConnectorIntegration | McpServerIntegration


@dataclass(frozen=True, slots=True)
class IntegrationAuthorizationState:
    status: IntegrationAuthorizationStatus = IntegrationAuthorizationStatus.IDLE
    target: IntegrationValue | None = None
    failure: Failure | None = None


class Invocation:
    @property
    def key(self) -> str:
        raise NotImplementedError

    @property
    def name(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class PluginInvocation(Invocation):
    name: str = field()
    uri: str = field()

    @property
    def key(self) -> str:
        return f"plugin:{self.uri}"


@dataclass(frozen=True, slots=True)
class SkillInvocation(Invocation):
    name: str = field()
    path: str = field()

    @property
    def key(self) -> str:
        return f"skill:{self.path}"


InvocationValue: TypeAlias = PluginInvocation | SkillInvocation


@dataclass(frozen=True, slots=True)
class Message:
    id: str
    role: MessageRole
    text: str
    reasoning: str | None = None
    plan: str | None = None
    shell_command: str | None = None
    exit_code: int | None = None
    invocations: Sequence[InvocationValue] = ()
    capabilities: Set[Capability] = frozenset()
    collaboration_mode: CollaborationMode = CollaborationMode.DEFAULT
    client_message_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "invocations", tuple(self.invocations))
        object.__setattr__(self, "capabilities", frozenset(self.capabilities))


@dataclass(frozen=True, slots=True)
class TurnRequest:
    prompt: str
    model: str | None = None
    effort: str | None = None
    approval_preset: ApprovalPreset = ApprovalPreset.AUTO_REVIEW
    service_tier: str | None = None
    capabilities: Set[Capability] = frozenset()
    collaboration_mode: CollaborationMode = CollaborationMode.DEFAULT
    invocations: Sequence[InvocationValue] = ()
    client_message_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "capabilities", frozenset(self.capabilities))
        object.__setattr__(self, "invocations", tuple(self.invocations))


class PendingInteraction:
    @property
    def request_id(self) -> str:
        raise NotImplementedError

    @property
    def conversation_id(self) -> ConversationId:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class PendingApproval(PendingInteraction):
    request_id: str = field()
    conversation_id: ConversationId = field()
    title: str = field()
    details: str = field()


@dataclass(frozen=True, slots=True)
class PendingElicitation(PendingInteraction):
    elicitation: Elicitation

    @property
    def request_id(self) -> str:
        return self.elicitation.request_id

    @property
    def conversation_id(self) -> ConversationId:
        return self.elicitation.conversation_id


PendingInteractionValue: TypeAlias = PendingApproval | PendingElicitation


@dataclass(frozen=True, slots=True)
class InteractionState:
    pending: Sequence[PendingInteractionValue] = ()
    resolving_request_ids: Set[str] = frozenset()
    failure: Failure | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "pending", tuple(self.pending))
        object.__setattr__(
            self, "resolving_request_ids", frozenset(self.resolving_request_ids)
        )

    def pending_for(
        self, conversation_id: ConversationId
    ) -> tuple[PendingInteractionValue, ...]:
        from ._value_native import interaction_pending_for

        return interaction_pending_for(self, conversation_id)

    def is_resolving(self, interaction: PendingInteractionValue) -> bool:
        from ._value_native import interaction_is_resolving

        return interaction_is_resolving(self, interaction)


@dataclass(frozen=True, slots=True)
class ConversationValue:
    summary: ConversationSummary
    messages: Sequence[Message] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "messages", tuple(self.messages))


@dataclass(frozen=True, slots=True)
class PathWorkspaceSelection:
    path: str

    def __post_init__(self) -> None:
        if not self.path or self.path.isspace() or "\0" in self.path:
            raise ValueError("workspace path must not be blank")


@dataclass(frozen=True, slots=True)
class WorkspaceAvailable:
    workspace: Workspace


@dataclass(frozen=True, slots=True)
class WorkspaceSelectionRequired:
    reason: WorkspaceSelectionReason
    message: str


@dataclass(frozen=True, slots=True)
class HostStateNew:
    pass


@dataclass(frozen=True, slots=True)
class HostStateRestoring:
    pass


@dataclass(frozen=True, slots=True)
class HostStateClosed:
    pass


HOST_STATE_NEW = HostStateNew()
HOST_STATE_RESTORING = HostStateRestoring()
HOST_STATE_CLOSED = HostStateClosed()


@dataclass(frozen=True, slots=True)
class HostStatePreparing:
    workspace: Workspace


@dataclass(frozen=True, slots=True)
class HostStateWorkspaceRequired:
    requirement: WorkspaceSelectionRequired


@dataclass(frozen=True, slots=True)
class HostStateFailed:
    failure: Failure
    workspace: Workspace | None = None
