import 'package:codex_agent/codex_agent.dart';

Future<void> main() async {
  final client = CodexClientInfo(
    name: 'consumer',
    title: 'Dart consumer',
    version: '1.0.0',
  );
  final cancellation = CodexCancellation();
  final request = CodexTurnRequest(
    prompt: 'hello',
    capabilities: const <CodexCapability>{CodexCapability.webSearch},
    invocations: const <CodexInvocation>[
      CodexSkillInvocation(name: 'review', path: 'skills/review.md'),
    ],
  );
  final mcp = CodexMcpServerConfiguration(
    name: 'local_tools',
    transport: CodexMcpStdioTransport(command: 'tool'),
  );
  if (client.name != 'consumer' ||
      cancellation.isCancelled ||
      request.invocations.single.key != 'skill:skills/review.md' ||
      mcp.name != 'local_tools') {
    throw StateError('public Dart package contract is unusable');
  }

  final field = CodexFormField(
    name: 'name',
    title: 'Name',
    type: CodexFormFieldType.string,
    isRequired: true,
    defaultValue: const CodexTextFormValue('Codex'),
  );
  final elicitation = CodexElicitation(
    requestId: 'request',
    serverName: 'server',
    conversationId: CodexConversationId('conversation'),
    message: 'Name',
    form: [field],
  );
  final content = <String, CodexFormValue>{
    'name': const CodexTextFormValue('Codex'),
  };
  final accepted = elicitation.accept(content);
  final validation = elicitation.validate(content);
  if (!field.accepts(content['name']) ||
      elicitation.initialValues().keys.single != 'name' ||
      validation.issues.isNotEmpty ||
      !elicitation.accepts(accepted) ||
      CodexElicitationResponse.cancel().action !=
          CodexElicitationAction.cancel ||
      CodexElicitationResponse.decline().action !=
          CodexElicitationAction.decline) {
    throw StateError('synchronous elicitation projection is unusable');
  }

  final approval = CodexPendingApproval(
    requestId: 'approval',
    conversationId: CodexConversationId('conversation'),
    title: 'Approve',
    details: 'Details',
  );
  final interactions = CodexInteractionState(
    pending: [approval, approval],
    resolvingRequestIds: ['approval'],
  );
  final selected = interactions.pendingFor(CodexConversationId('conversation'));
  if (!interactions.isResolving(approval) ||
      selected.length != 2 ||
      !identical(selected.first, approval) ||
      CodexAuthorizationUrl.chatGpt('https://auth.openai.com/authorize')
              .purpose !=
          CodexAuthorizationPurpose.chatGpt ||
      CodexAuthorizationUrl.external('http://localhost/callback').purpose !=
          CodexAuthorizationPurpose.external) {
    throw StateError('synchronous interaction projection is unusable');
  }
}

// Compiled from the installed package so every leaf projection remains a
// public, statically typed Dart API.
Future<void> compileLeafServiceSurface({
  required CodexAuthentication authentication,
  required CodexInteractions interactions,
  required CodexIntegrationAuthorization authorization,
  required CodexModels models,
  required CodexSkills skills,
  required CodexHooks hooks,
  required CodexPlugins plugins,
  required CodexConnectors connectors,
  required CodexMcpServers mcpServers,
  required CodexModel model,
  required CodexPluginReference plugin,
  required CodexHook hook,
  required CodexSkill skill,
  required CodexMcpServer server,
  required CodexMcpServerConfiguration configuration,
  required CodexPendingApproval approval,
  required CodexPendingElicitation elicitation,
  required CodexIntegration integration,
}) async {
  await authentication.authenticate(CodexApiKeyAuthentication('key'));
  await authentication.cancel();
  await authentication.signOut();
  await authentication.state.current;
  authentication.state.changes.listen((_) {});
  await authentication.isAuthenticatedState.current;
  authentication.isAuthenticatedState.changes.listen((_) {});
  await authentication.isAuthenticatingState.current;
  authentication.isAuthenticatingState.changes.listen((_) {});

  await interactions.openUrl(elicitation);
  await interactions.resolveApproval(approval, CodexApprovalDecision.accept);
  await interactions.resolveElicitation(
    elicitation,
    CodexElicitationResponse(action: CodexElicitationAction.cancel),
  );
  await interactions.state.current;
  interactions.state.changes.listen((_) {});
  await interactions.approvalsState.current;
  interactions.approvalsState.changes.listen((_) {});
  await interactions.elicitationsState.current;
  interactions.elicitationsState.changes.listen((_) {});

  await authorization.authorize(integration);
  await authorization.cancel();
  await authorization.state.current;
  authorization.state.changes.listen((_) {});
  await authorization.activeState.current;
  authorization.activeState.changes.listen((_) {});
  await authorization.isAuthorizingState.current;
  authorization.isAuthorizingState.changes.listen((_) {});

  await models.list();
  await models.resolve();
  await models.resolveEffort(model);
  await models.resolveServiceTier(model);
  await skills.list();
  await skills.read('/skill');
  await skills.install('/skill', CodexInstallationScope.user);
  await skills.uninstall(skill);
  await hooks.list();
  await hooks.install('/hook', CodexInstallationScope.user);
  await hooks.trust(hook);
  await hooks.uninstall(hook);
  await plugins.list();
  await plugins.read(plugin);
  await plugins.install(plugin);
  await plugins.uninstall(plugin);
  await connectors.list();
  await mcpServers.list();
  await mcpServers.add(configuration);
  await mcpServers.remove(server);
  final availability = <bool>[
    skills.isAvailable,
    hooks.isAvailable,
    plugins.isAvailable,
    connectors.isAvailable,
    mcpServers.isAvailable,
  ];
  if (availability.every((value) => value)) return;
}

void compileAgentSurface(CodexAgent agent) {
  final projections = <Object>[
    agent.authentication,
    agent.connectors,
    agent.conversations,
    agent.hooks,
    agent.integrationAuthorization,
    agent.interactions,
    agent.mcpServers,
    agent.models,
    agent.plugins,
    agent.skills,
  ];
  final workspace = agent.workspace;
  if (projections.length != 10 || workspace.path.isEmpty) {
    throw StateError('public Agent projection is unusable');
  }
}

void compileHostSurface(CodexHost host, CodexAgent agent) {
  final create = CodexHost.create;
  final ready = CodexReadyHostState(agent);
  final lifecycle = host.state;
  final start = host.start;
  final selectWorkspace = host.selectWorkspace;
  final close = host.close;
  if (!identical(ready.agent, agent) ||
      ready.kind != CodexHostStateKind.ready ||
      <Object>[create, lifecycle, start, selectWorkspace, close].length != 5) {
    throw StateError('public Host/READY projection is unusable');
  }
}
