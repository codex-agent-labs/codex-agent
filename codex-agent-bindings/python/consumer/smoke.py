import inspect
import typing

from codex_agent import (
    ApprovalPreset,
    AuthenticationState,
    AuthenticationStatus,
    AuthorizationUrl,
    Capability,
    ClientInfo,
    CollaborationMode,
    CodexAgent,
    CodexAuthentication,
    CodexConversation,
    CodexConnectors,
    CodexHooks,
    CodexHost,
    CodexIntegrationAuthorization,
    CodexInteractions,
    CodexMcpServers,
    CodexModels,
    CodexPlugins,
    CodexSkills,
    ConversationId,
    Conversations,
    ConversationValue,
    Elicitation,
    ElicitationAction,
    ElicitationResponse,
    FormField,
    FormFieldType,
    FormTextListValue,
    FormTextValue,
    HOST_STATE_NEW,
    HostState,
    HostStateKind,
    HostStateReady,
    Message,
    MessageRole,
    PlanProgress,
    PlanStep,
    PlanStepStatus,
    PluginReference,
    TurnRequest,
    McpHttpTransport,
    McpServer,
    McpServerConfiguration,
    McpAuthStatus,
    McpToolApproval,
    InteractionState,
    PendingApproval,
    StateStream,
    TurnProgress,
    Workspace,
)


assert tuple(
    service.__name__
    for service in (
        CodexAuthentication,
        CodexConnectors,
        CodexHooks,
        CodexIntegrationAuthorization,
        CodexInteractions,
        CodexMcpServers,
        CodexModels,
        CodexPlugins,
        CodexSkills,
    )
) == (
    "CodexAuthentication",
    "CodexConnectors",
    "CodexHooks",
    "CodexIntegrationAuthorization",
    "CodexInteractions",
    "CodexMcpServers",
    "CodexModels",
    "CodexPlugins",
    "CodexSkills",
)


client = ClientInfo("consumer", "Python consumer", "1.0")
assert client.name == "consumer"
assert ConversationId("abc").value == "abc"
assert ApprovalPreset.ASK_ME.value == 2
assert AuthenticationStatus.AUTHENTICATED.value == 2
assert HostStateKind.READY.value == 4
assert McpToolApproval.WRITES.value == 2

headers = {"X-Client": "consumer"}
transport = McpHttpTransport("https://example.com/mcp", headers=headers)
configuration = McpServerConfiguration("consumer", transport, enabled_tools=[])
server = McpServer("consumer", "Consumer", McpAuthStatus.OAUTH, configuration)
headers["X-Client"] = "changed"
assert server.is_authorized
assert server.configuration.transport.headers["X-Client"] == "consumer"
assert server.configuration.enabled_tools == ()
assert server.configuration.disabled_tools is None

steps = [PlanStep("compile", PlanStepStatus.COMPLETED)]
progress = PlanProgress("done", steps)
steps.clear()
assert progress.steps == (PlanStep("compile", PlanStepStatus.COMPLETED),)
assert PluginReference("id", "plugin", "market").uri == "plugin://plugin@market"

values = ["one", "one", "two"]
field = FormField(
    "items",
    "Items",
    FormFieldType.MULTI_SELECT,
    default_value=FormTextListValue(values),
)
values.clear()
assert field.default_value == FormTextListValue(("one", "one", "two"))
assert AuthenticationState(AuthenticationStatus.SIGNED_OUT).failure is None
assert Message(
    "message",
    MessageRole.USER,
    "hello",
    capabilities={Capability.WEB_SEARCH},
).capabilities == frozenset({Capability.WEB_SEARCH})
assert (
    TurnRequest("hello", collaboration_mode=CollaborationMode.PLAN).collaboration_mode
    is CollaborationMode.PLAN
)
assert HOST_STATE_NEW is HOST_STATE_NEW
assert issubclass(HostStateReady, HostState)
assert inspect.signature(HostStateReady).parameters["agent"].annotation == "CodexAgent"
assert inspect.iscoroutinefunction(CodexHost.start)
assert inspect.iscoroutinefunction(CodexHost.select_workspace)
assert inspect.iscoroutinefunction(CodexHost.aclose)
host_state = inspect.getattr_static(CodexHost, "state")
assert isinstance(host_state, property)
assert typing.get_type_hints(host_state.fget)["return"] == StateStream[HostState]

assert inspect.iscoroutinefunction(Conversations.read)
assert typing.get_type_hints(Conversations.read)["return"] is ConversationValue
assert inspect.iscoroutinefunction(CodexConversation.send)
assert typing.get_type_hints(CodexConversation.send)["prompt"] == str | TurnRequest
assert isinstance(CodexConversation.current_messages, property)
assert (
    typing.get_type_hints(CodexConversation.current_messages.fget)["return"]
    == StateStream[tuple[Message, ...]]
)
assert isinstance(CodexConversation.active_turn_progress, property)
assert (
    typing.get_type_hints(CodexConversation.active_turn_progress.fget)["return"]
    == StateStream[TurnProgress | None]
)

for name, return_type in {
    "authentication": CodexAuthentication,
    "connectors": CodexConnectors,
    "conversations": Conversations,
    "hooks": CodexHooks,
    "integration_authorization": CodexIntegrationAuthorization,
    "interactions": CodexInteractions,
    "mcp_servers": CodexMcpServers,
    "models": CodexModels,
    "plugins": CodexPlugins,
    "skills": CodexSkills,
    "workspace": Workspace,
}.items():
    member = inspect.getattr_static(CodexAgent, name)
    assert isinstance(member, property)
    assert typing.get_type_hints(member.fget)["return"] is return_type

form_field = FormField(
    "name",
    "Name",
    FormFieldType.STRING,
    is_required=True,
    default_value=FormTextValue("Codex"),
)
elicitation = Elicitation(
    "request",
    ConversationId("conversation"),
    "server",
    "Choose",
    form=(form_field,),
)
content = elicitation.initial_values()
assert form_field.accepts(content["name"])
assert elicitation.validate(content).is_valid
response = elicitation.accept(content)
assert elicitation.accepts(response)
assert ElicitationResponse.decline().action is ElicitationAction.DECLINE
assert ElicitationResponse.cancel().action is ElicitationAction.CANCEL

approval = PendingApproval(
    "request", ConversationId("conversation"), "Title", "Details"
)
interactions = InteractionState((approval, approval), {"request"})
assert interactions.is_resolving(approval)
assert interactions.pending_for(ConversationId("conversation")) == (approval, approval)

chat_gpt_url = AuthorizationUrl.chat_gpt("https://auth.openai.com/authorize")
external_url = AuthorizationUrl.external("http://localhost:8787/callback")
assert "auth.openai.com" not in repr(chat_gpt_url)
assert external_url.value.startswith("http://localhost:")
