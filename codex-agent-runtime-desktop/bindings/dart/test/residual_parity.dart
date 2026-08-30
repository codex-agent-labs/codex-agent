import 'dart:convert';
import 'dart:io';

import 'package:codex_agent/codex_agent.dart';
import 'package:test/test.dart';

final class DartResidualClaim {
  const DartResidualClaim({
    required this.capabilityKey,
    required this.publicSymbols,
    required this.executedTests,
    required this.compilerEvidenceIds,
    required this.sharedScenarios,
  });

  final String capabilityKey;
  final List<String> publicSymbols;
  final List<String> executedTests;
  final List<String> compilerEvidenceIds;
  final List<String> sharedScenarios;
}

final _failure = CodexFailure(
  code: 'failed',
  message: 'Failure',
  isRecoverable: true,
);
final _workspace = CodexWorkspace(path: '/workspace', displayName: 'Workspace');
final _conversationId = CodexConversationId('conversation-1');
final _summary = CodexConversationSummary(
  conversationId: _conversationId,
  title: 'Title',
  updatedAtEpochSeconds: 42,
);
final _skillInvocation = CodexSkillInvocation(name: 'Skill', path: 'skill.md');
final _pluginInvocation =
    CodexPluginInvocation(name: 'Plugin', uri: 'plugin://plugin@market');
final CodexInvocation _invocation = _skillInvocation;
final _message = CodexMessage(
  id: 'message',
  clientMessageId: 'client-message',
  role: CodexMessageRole.assistant,
  text: 'Text',
  collaborationMode: CodexCollaborationMode.plan,
  reasoning: 'Reasoning',
  plan: 'Plan',
  shellCommand: 'echo hi',
  exitCode: 0,
  capabilities: const <CodexCapability>{CodexCapability.webSearch},
  invocations: <CodexInvocation>[_skillInvocation, _pluginInvocation],
);
final _conversation = CodexConversationSnapshot(
    summary: _summary, messages: [_message, _message]);
final _turnProgress = CodexTurnProgress(text: 'progress');
final _conversationState = CodexConversationState(
  status: CodexConversationStatus.failed,
  conversationId: _conversationId,
  conversation: _conversation,
  turnProgress: _turnProgress,
  model: 'model',
  effort: 'high',
  serviceTier: 'fast',
  failure: _failure,
);
final _textValue = const CodexTextFormValue('text');
final _numberValue = const CodexNumberFormValue(1.5);
final _booleanValue = const CodexBooleanFormValue(true);
final _textListValue = CodexTextListFormValue(['one', 'one', 'two']);
final _formOption = CodexFormOption(
  value: 'one',
  title: 'One',
  description: 'Description',
);
final _formField = CodexFormField(
  name: 'field',
  title: 'Field',
  type: CodexFormFieldType.multiSelect,
  description: 'Description',
  isRequired: true,
  options: [_formOption, _formOption],
  defaultValue: _textListValue,
  minimum: 1,
  maximum: 10,
  format: CodexFormStringFormat.uri,
  minimumLength: 1,
  maximumLength: 20,
  minimumSelections: 1,
  maximumSelections: 3,
  allowsOther: true,
  isSecret: true,
);
final _elicitation = CodexElicitation(
  requestId: 'request',
  serverName: 'server',
  conversationId: _conversationId,
  message: 'Complete the form',
  form: [_formField, _formField],
  url: 'https://example.test/form',
);
final _response = CodexElicitationResponse(
  action: CodexElicitationAction.accept,
  content: <String, CodexFormValue>{'field': _textListValue},
);
final _commandHandler =
    const CodexCommandHookHandler(command: 'echo hi', isAsync: true);
final _mcpHandler =
    const CodexMcpToolHookHandler(server: 'server', tool: 'tool');
final _hook = CodexHook(
  key: 'hook',
  currentHash: 'hash',
  isEnabled: true,
  eventName: 'after-turn',
  handler: _commandHandler,
  isManaged: false,
  source: 'PLUGIN',
  sourcePath: '/hook',
  timeoutSeconds: 30,
  trustStatus: CodexHookTrustStatus.modified,
  matcher: 'matcher',
  pluginId: 'plugin',
  statusMessage: 'changed',
  canUninstall: true,
);
final _hookCatalog = CodexHookCatalog(
  hooks: [_hook, _hook],
  warnings: ['warning', 'warning'],
  errors: ['error', 'error'],
);
final _connector = CodexConnector(id: 'connector', name: 'Connector');
final _server = const CodexMcpServer(
  name: 'server',
  displayName: 'Server',
  authStatus: CodexMcpAuthStatus.unknown,
  origin: CodexResourceOrigin.user,
);
final _connectorIntegration = CodexConnectorIntegration(_connector);
final _serverIntegration = CodexMcpServerIntegration(_server);
final CodexIntegration _integration = _connectorIntegration;
final _authorizationUrl =
    CodexAuthorizationUrl.chatGpt('https://auth.openai.com/authorize');
final _authentication = CodexAuthenticationState(
  status: CodexAuthenticationStatus.authenticating,
  pendingSignInUrl: _authorizationUrl,
  deviceVerificationUrl:
      CodexAuthorizationUrl.external('http://127.0.0.1:8080/device'),
  deviceUserCode: 'CODE',
  failure: _failure,
);
final _approval = CodexPendingApproval(
  requestId: 'approval',
  conversationId: _conversationId,
  title: 'Approve',
  details: 'Details',
);
final _pendingElicitation = CodexPendingElicitation(_elicitation);
final CodexPendingInteraction _pendingInteraction = _approval;
final _interactionState = CodexInteractionState(
  pending: [_approval, _pendingElicitation],
  resolvingRequestIds: ['approval'],
  failure: _failure,
);
final _selectionRequired = const CodexWorkspaceSelectionRequired(
  reason: CodexWorkspaceSelectionReason.notSelected,
  message: 'Select a workspace',
);
final _turnRequest = CodexTurnRequest(
  prompt: 'Prompt',
  clientMessageId: 'client',
  model: 'model',
  effort: 'high',
  serviceTier: 'fast',
  approvalPreset: CodexApprovalPreset.strict,
  capabilities: const <CodexCapability>{CodexCapability.webSearch},
  invocations: <CodexInvocation>[_skillInvocation, _pluginInvocation],
  collaborationMode: CodexCollaborationMode.plan,
);
final _apiKey = CodexApiKeyAuthentication('secret');
final _failedHost =
    CodexFailedHostState(failure: _failure, workspace: _workspace);
final _preparingHost = CodexPreparingHostState(_workspace);
final _workspaceRequiredHost =
    CodexWorkspaceRequiredHostState(_selectionRequired);
final _pathSelection = CodexPathWorkspaceSelection('/workspace');
final _availableWorkspace = CodexAvailableWorkspace(_workspace);

// Direct compiler-checked references: one exact symbol per capability.
final Map<String, Object? Function()> residualPublicAccessors =
    <String, Object? Function()>{
  'CodexApprovalPresetMetadata.displayName': () =>
      CodexApprovalPreset.autoReview.displayName,
  'CodexAuthenticationState.new': () => _authentication,
  'CodexAuthenticationState.deviceUserCode': () =>
      _authentication.deviceUserCode,
  'CodexAuthenticationState.deviceVerificationUrl': () =>
      _authentication.deviceVerificationUrl,
  'CodexAuthenticationState.failure': () => _authentication.failure,
  'CodexAuthenticationState.pendingSignInUrl': () =>
      _authentication.pendingSignInUrl,
  'CodexAuthenticationState.status': () => _authentication.status,
  'CodexCapabilityMetadata.displayLabel': () =>
      CodexCapability.webSearch.displayLabel,
  'CodexCapabilityMetadata.icon': () => CodexCapability.webSearch.icon,
  'CodexCapabilityMetadata.id': () => CodexCapability.webSearch.id,
  'CodexCapabilityMetadata.promptLabel': () =>
      CodexCapability.webSearch.promptLabel,
  'CodexConversationState.new': () => _conversationState,
  'CodexConversationState.canCancelTurn': () =>
      _conversationState.canCancelTurn,
  'CodexConversationState.canReload': () => _conversationState.canReload,
  'CodexConversationState.canStartTurn': () => _conversationState.canStartTurn,
  'CodexConversationState.conversationId': () =>
      _conversationState.conversationId,
  'CodexConversationState.conversation': () => _conversationState.conversation,
  'CodexConversationState.effort': () => _conversationState.effort,
  'CodexConversationState.failure': () => _conversationState.failure,
  'CodexConversationState.model': () => _conversationState.model,
  'CodexConversationState.serviceTier': () => _conversationState.serviceTier,
  'CodexConversationState.status': () => _conversationState.status,
  'CodexConversationState.turnProgress': () => _conversationState.turnProgress,
  'CodexConversationSnapshot.new': () => _conversation,
  'CodexConversationSnapshot.messages': () => _conversation.messages,
  'CodexConversationSnapshot.summary': () => _conversation.summary,
  'CodexElicitationResponse.new': () => _response,
  'CodexElicitationResponse.action': () => _response.action,
  'CodexElicitationResponse.content': () => _response.content,
  'CodexElicitation.new': () => _elicitation,
  'CodexElicitation.conversationId': () => _elicitation.conversationId,
  'CodexElicitation.form': () => _elicitation.form,
  'CodexElicitation.message': () => _elicitation.message,
  'CodexElicitation.requestId': () => _elicitation.requestId,
  'CodexElicitation.serverName': () => _elicitation.serverName,
  'CodexElicitation.url': () => _elicitation.url,
  'CodexFormField.new': () => _formField,
  'CodexFormField.allowsOther': () => _formField.allowsOther,
  'CodexFormField.defaultValue': () => _formField.defaultValue,
  'CodexFormField.description': () => _formField.description,
  'CodexFormField.format': () => _formField.format,
  'CodexFormField.isRequired': () => _formField.isRequired,
  'CodexFormField.isSecret': () => _formField.isSecret,
  'CodexFormField.maximumLength': () => _formField.maximumLength,
  'CodexFormField.maximumSelections': () => _formField.maximumSelections,
  'CodexFormField.maximum': () => _formField.maximum,
  'CodexFormField.minimumLength': () => _formField.minimumLength,
  'CodexFormField.minimumSelections': () => _formField.minimumSelections,
  'CodexFormField.minimum': () => _formField.minimum,
  'CodexFormField.name': () => _formField.name,
  'CodexFormField.options': () => _formField.options,
  'CodexFormField.title': () => _formField.title,
  'CodexFormField.type': () => _formField.type,
  'CodexBooleanFormValue.new': () => _booleanValue,
  'CodexBooleanFormValue.value': () => _booleanValue.value,
  'CodexNumberFormValue.new': () => _numberValue,
  'CodexNumberFormValue.value': () => _numberValue.value,
  'CodexTextListFormValue.new': () => _textListValue,
  'CodexTextListFormValue.value': () => _textListValue.value,
  'CodexTextFormValue.new': () => _textValue,
  'CodexTextFormValue.value': () => _textValue.value,
  'CodexHookCatalog.new': () => _hookCatalog,
  'CodexHookCatalog.errors': () => _hookCatalog.errors,
  'CodexHookCatalog.hooks': () => _hookCatalog.hooks,
  'CodexHookCatalog.warnings': () => _hookCatalog.warnings,
  'CodexAgentHookHandler.instance': () => CodexAgentHookHandler.instance,
  'CodexCommandHookHandler.new': () => _commandHandler,
  'CodexCommandHookHandler.command': () => _commandHandler.command,
  'CodexCommandHookHandler.isAsync': () => _commandHandler.isAsync,
  'CodexMcpToolHookHandler.new': () => _mcpHandler,
  'CodexMcpToolHookHandler.server': () => _mcpHandler.server,
  'CodexMcpToolHookHandler.tool': () => _mcpHandler.tool,
  'CodexPromptHookHandler.instance': () => CodexPromptHookHandler.instance,
  'CodexHook.new': () => _hook,
  'CodexHook.canTrust': () => _hook.canTrust,
  'CodexHook.canUninstall': () => _hook.canUninstall,
  'CodexHook.currentHash': () => _hook.currentHash,
  'CodexHook.eventName': () => _hook.eventName,
  'CodexHook.handler': () => _hook.handler,
  'CodexHook.isEnabled': () => _hook.isEnabled,
  'CodexHook.isManaged': () => _hook.isManaged,
  'CodexHook.key': () => _hook.key,
  'CodexHook.matcher': () => _hook.matcher,
  'CodexHook.origin': () => _hook.origin,
  'CodexHook.pluginId': () => _hook.pluginId,
  'CodexHook.sourcePath': () => _hook.sourcePath,
  'CodexHook.source': () => _hook.source,
  'CodexHook.statusMessage': () => _hook.statusMessage,
  'CodexHook.timeoutSeconds': () => _hook.timeoutSeconds,
  'CodexHook.trustStatus': () => _hook.trustStatus,
  'CodexConnectorIntegration.new': () => _connectorIntegration,
  'CodexConnectorIntegration.connector': () => _connectorIntegration.connector,
  'CodexConnectorIntegration.displayName': () =>
      _connectorIntegration.displayName,
  'CodexConnectorIntegration.id': () => _connectorIntegration.id,
  'CodexMcpServerIntegration.new': () => _serverIntegration,
  'CodexMcpServerIntegration.displayName': () => _serverIntegration.displayName,
  'CodexMcpServerIntegration.id': () => _serverIntegration.id,
  'CodexMcpServerIntegration.server': () => _serverIntegration.server,
  'CodexIntegrationAuthorizationState.new': () =>
      CodexIntegrationAuthorizationState(
          status: CodexIntegrationAuthorizationStatus.authorized,
          target: _connectorIntegration,
          failure: _failure),
  'CodexIntegrationAuthorizationState.failure': () =>
      CodexIntegrationAuthorizationState(
              status: CodexIntegrationAuthorizationStatus.authorized,
              target: _connectorIntegration,
              failure: _failure)
          .failure,
  'CodexIntegrationAuthorizationState.status': () =>
      CodexIntegrationAuthorizationState(
              status: CodexIntegrationAuthorizationStatus.authorized,
              target: _connectorIntegration,
              failure: _failure)
          .status,
  'CodexIntegrationAuthorizationState.target': () =>
      CodexIntegrationAuthorizationState(
              status: CodexIntegrationAuthorizationStatus.authorized,
              target: _connectorIntegration,
              failure: _failure)
          .target,
  'CodexIntegration.displayName': () => _integration.displayName,
  'CodexIntegration.id': () => _integration.id,
  'CodexInteractionState.new': () => _interactionState,
  'CodexInteractionState.failure': () => _interactionState.failure,
  'CodexInteractionState.pending': () => _interactionState.pending,
  'CodexInteractionState.resolvingRequestIds': () =>
      _interactionState.resolvingRequestIds,
  'CodexPluginInvocation.new': () => _pluginInvocation,
  'CodexPluginInvocation.key': () => _pluginInvocation.key,
  'CodexPluginInvocation.name': () => _pluginInvocation.name,
  'CodexPluginInvocation.uri': () => _pluginInvocation.uri,
  'CodexSkillInvocation.new': () => _skillInvocation,
  'CodexSkillInvocation.key': () => _skillInvocation.key,
  'CodexSkillInvocation.name': () => _skillInvocation.name,
  'CodexSkillInvocation.path': () => _skillInvocation.path,
  'CodexInvocation.key': () => _invocation.key,
  'CodexInvocation.name': () => _invocation.name,
  'CodexMessage.new': () => _message,
  'CodexMessage.capabilities': () => _message.capabilities,
  'CodexMessage.clientMessageId': () => _message.clientMessageId,
  'CodexMessage.collaborationMode': () => _message.collaborationMode,
  'CodexMessage.exitCode': () => _message.exitCode,
  'CodexMessage.id': () => _message.id,
  'CodexMessage.invocations': () => _message.invocations,
  'CodexMessage.plan': () => _message.plan,
  'CodexMessage.reasoning': () => _message.reasoning,
  'CodexMessage.role': () => _message.role,
  'CodexMessage.shellCommand': () => _message.shellCommand,
  'CodexMessage.text': () => _message.text,
  'CodexPendingApproval.new': () => _approval,
  'CodexPendingApproval.conversationId': () => _approval.conversationId,
  'CodexPendingApproval.details': () => _approval.details,
  'CodexPendingApproval.requestId': () => _approval.requestId,
  'CodexPendingApproval.title': () => _approval.title,
  'CodexPendingElicitation.new': () => _pendingElicitation,
  'CodexPendingElicitation.conversationId': () =>
      _pendingElicitation.conversationId,
  'CodexPendingElicitation.elicitation': () => _pendingElicitation.elicitation,
  'CodexPendingElicitation.requestId': () => _pendingElicitation.requestId,
  'CodexPendingInteraction.conversationId': () =>
      _pendingInteraction.conversationId,
  'CodexPendingInteraction.requestId': () => _pendingInteraction.requestId,
  'CodexSkillScopeMetadata.displayName': () => CodexSkillScope.repo.displayName,
  'CodexTurnRequest.new': () => _turnRequest,
  'CodexTurnRequest.approvalPreset': () => _turnRequest.approvalPreset,
  'CodexTurnRequest.capabilities': () => _turnRequest.capabilities,
  'CodexTurnRequest.clientMessageId': () => _turnRequest.clientMessageId,
  'CodexTurnRequest.collaborationMode': () => _turnRequest.collaborationMode,
  'CodexTurnRequest.effort': () => _turnRequest.effort,
  'CodexTurnRequest.invocations': () => _turnRequest.invocations,
  'CodexTurnRequest.model': () => _turnRequest.model,
  'CodexTurnRequest.prompt': () => _turnRequest.prompt,
  'CodexTurnRequest.serviceTier': () => _turnRequest.serviceTier,
  'CodexApiKeyAuthentication.new': () => _apiKey,
  'CodexApiKeyAuthentication.value': () => _apiKey.value,
  'CodexChatGptBrowserAuthentication.instance': () =>
      CodexChatGptBrowserAuthentication.instance,
  'CodexChatGptDeviceCodeAuthentication.instance': () =>
      CodexChatGptDeviceCodeAuthentication.instance,
  'CodexAuthorizationUrl.purpose': () => _authorizationUrl.purpose,
  'CodexAuthorizationUrl.value': () => _authorizationUrl.value,
  'CodexClosedHostState.instance': () => CodexClosedHostState.instance,
  'CodexFailedHostState.new': () => _failedHost,
  'CodexFailedHostState.failure': () => _failedHost.failure,
  'CodexFailedHostState.workspace': () => _failedHost.workspace,
  'CodexNewHostState.instance': () => CodexNewHostState.instance,
  'CodexPreparingHostState.new': () => _preparingHost,
  'CodexPreparingHostState.workspace': () => _preparingHost.workspace,
  'CodexRestoringHostState.instance': () => CodexRestoringHostState.instance,
  'CodexWorkspaceRequiredHostState.new': () => _workspaceRequiredHost,
  'CodexWorkspaceRequiredHostState.requirement': () =>
      _workspaceRequiredHost.requirement,
  'CodexPathWorkspaceSelection.new': () => _pathSelection,
  'CodexPathWorkspaceSelection.path': () => _pathSelection.path,
  'CodexAvailableWorkspace.new': () => _availableWorkspace,
  'CodexAvailableWorkspace.workspace': () => _availableWorkspace.workspace,
  'CodexWorkspaceSelectionRequired.new': () => _selectionRequired,
  'CodexWorkspaceSelectionRequired.message': () => _selectionRequired.message,
  'CodexWorkspaceSelectionRequired.reason': () => _selectionRequired.reason,
};

String _owner(String capability) =>
    capability.split('|owner=')[1].split('|')[0].split('/').last;

String _kind(String capability) => capability.split('|kind=')[1].split('|')[0];

Set<String> _canonicalResidual(
  Directory root,
  Set<String> priorCapabilities,
) {
  final document = jsonDecode(
    File(
      '${root.path}/codex-agent-core/build/reports/'
      'cross-language-api/canonical-api.json',
    ).readAsStringSync(),
  ) as Map<String, dynamic>;
  const serviceOwners = <String>{
    'CodexAgent',
    'CodexAuthentication',
    'CodexConnectors',
    'CodexConversation',
    'CodexConversations',
    'CodexHooks',
    'CodexHost',
    'CodexIntegrationAuthorization',
    'CodexInteractions',
    'CodexMcpServers',
    'CodexModels',
    'CodexPlugins',
    'CodexSkills',
  };
  return {
    for (final owner in document['owners'] as List<dynamic>)
      for (final capability
          in (owner as Map<String, dynamic>)['capabilities'] as List<dynamic>)
        if (!priorCapabilities.contains(capability as String) &&
            const <String>{'constructor', 'property', 'object'}
                .contains(_kind(capability)) &&
            !serviceOwners.contains(_owner(capability)) &&
            _owner(capability) != 'CodexHostState.Ready')
          capability,
  };
}

bool _sameSet(Set<String> left, Set<String> right) =>
    left.length == right.length && left.containsAll(right);

Set<String> verifyResidualClaims(
  List<DartResidualClaim> claims,
  Directory root,
  Set<String> priorCapabilities,
) {
  if (claims.length != 175 ||
      claims.map((claim) => _owner(claim.capabilityKey)).toSet().length != 45 ||
      !_sameSet(
        claims.map((claim) => claim.capabilityKey).toSet(),
        _canonicalResidual(root, priorCapabilities),
      ) ||
      !_sameSet(
        claims.expand((claim) => claim.publicSymbols).toSet(),
        residualPublicAccessors.keys.toSet(),
      )) {
    throw StateError(
        'Dart residual claims are incomplete, stale, or overclaimed');
  }
  final bootstrap = jsonDecode(
    File(
      '${root.path}/codex-agent-runtime-desktop/build/reports/'
      'cross-language-api/c-abi/bootstrap-evidence.json',
    ).readAsStringSync(),
  ) as Map<String, dynamic>;
  final bootstrapClaims = <String, Map<String, dynamic>>{
    for (final claim in bootstrap['claims'] as List<dynamic>)
      (claim as Map<String, dynamic>)['capabilityKey'] as String: claim,
  };
  final passedTests = <String>{
    for (final test in bootstrap['nativeTests'] as List<dynamic>)
      if ((test as Map<String, dynamic>)['status'] == 'passed')
        test['testId'] as String,
  };
  final header = File(
    '${root.path}/codex-agent-runtime-desktop/native/c-api/include/'
    'codex_agent.h',
  ).readAsStringSync();
  final references = <String>{};
  for (var index = 0; index < claims.length; index++) {
    final claim = claims[index];
    final bootstrapClaim = bootstrapClaims[claim.capabilityKey];
    if (bootstrapClaim == null) throw StateError('missing bootstrap claim');
    final expectedHeaders =
        (bootstrapClaim['headerReferences'] as List<dynamic>)
            .cast<String>()
            .map((value) => 'c-header:$value')
            .toSet();
    final expectedTests = (bootstrapClaim['nativeTestIds'] as List<dynamic>)
        .cast<String>()
        .map((value) => 'cabi-fixture:$value')
        .toSet();
    final expectedAnalyzer =
        'dart-analyzer-residual:${index.toString().padLeft(3, '0')}';
    if (!_sameSet(claim.compilerEvidenceIds.toSet(), {
      ...expectedHeaders,
      ...expectedTests,
      expectedAnalyzer,
    })) {
      throw StateError('inexact residual evidence: ${claim.capabilityKey}');
    }
    for (final evidence in expectedTests) {
      if (!passedTests.contains(evidence.substring('cabi-fixture:'.length))) {
        throw StateError('stale C ABI fixture: $evidence');
      }
    }
    for (final evidence in expectedHeaders) {
      final reference = evidence.substring('c-header:'.length);
      if (!header.contains(reference)) {
        throw StateError('stale C header reference: $reference');
      }
      references.add(reference);
    }
  }
  return references;
}

Future<void> compileResidualHeaderReferences(
  Directory root,
  Set<String> references,
) async {
  final directory = Directory.systemTemp.createTempSync('dart_residual_');
  try {
    final expressions = <String>[];
    for (final reference in references.toList()..sort()) {
      if (reference.startsWith('CODEX_AGENT_')) {
        expressions.add('  (void)$reference;');
      } else if (reference == 'codex_agent_path_workspace_selection_t' ||
          reference == 'codex_agent_host_options_t') {
        expressions.add('  (void)sizeof($reference);');
      } else if (reference == 'codex_agent_string_view_t path;') {
        expressions.add(
          '  codex_agent_path_workspace_selection_t selection = {0}; '
          '(void)selection.path;',
        );
      } else {
        expressions.add('  (void)sizeof(&$reference);');
      }
    }
    final source = File('${directory.path}/references.c')
      ..writeAsStringSync(
        '#include "codex_agent.h"\n'
        'void dart_residual_references(void) {\n'
        '${expressions.join('\n')}\n}\n',
      );
    final include =
        '${root.path}/codex-agent-runtime-desktop/native/c-api/include';
    final output = '${directory.path}/references.o';
    final result = Platform.isWindows
        ? await Process.run('cl', [
            '/nologo',
            '/W4',
            '/WX',
            '/c',
            '/I$include',
            source.path,
            '/Fo$output',
          ])
        : await Process.run('cc', [
            '-std=c11',
            '-Wall',
            '-Wextra',
            '-Werror',
            '-pedantic',
            '-I',
            include,
            '-c',
            source.path,
            '-o',
            output,
          ]);
    if (result.exitCode != 0) {
      throw StateError('${result.stdout}\n${result.stderr}');
    }
  } finally {
    directory.deleteSync(recursive: true);
  }
}

List<String> _expectedScenarios(String capability) {
  final scenarios = <String>{'value-conversion'};
  if (capability.contains('?')) scenarios.add('nullability');
  if (capability.contains('kotlin.collections')) {
    scenarios.add('collection-immutability-ordering');
  }
  if (capability.contains('CodexFailure')) scenarios.add('structured-failure');
  return scenarios.toList()..sort();
}

void registerResidualParity(
  List<DartResidualClaim> claims,
  Directory root,
  Set<String> priorCapabilities,
  Map<String, Set<String>> passedCompilerEvidence,
  Set<String> passedTestIds,
) {
  test('dart.residual.inventory', () {
    expect(
      () => verifyResidualClaims(claims, root, priorCapabilities),
      returnsNormally,
    );
  });
  test('dart.residual inventory rejects stale header and fixture references',
      () {
    final first = claims.first;
    List<DartResidualClaim> withStale(String prefix, String stale) => [
          DartResidualClaim(
            capabilityKey: first.capabilityKey,
            publicSymbols: first.publicSymbols,
            executedTests: first.executedTests,
            compilerEvidenceIds: <String>[
              ...first.compilerEvidenceIds
                  .where((evidence) => !evidence.startsWith(prefix)),
              stale,
            ]..sort(),
            sharedScenarios: first.sharedScenarios,
          ),
          ...claims.skip(1),
        ];

    expect(
      () => verifyResidualClaims(
        withStale(
          'c-header:',
          'c-header:codex_agent_removed_residual_value',
        ),
        root,
        priorCapabilities,
      ),
      throwsStateError,
    );
    expect(
      () => verifyResidualClaims(
        withStale(
          'cabi-fixture:',
          'cabi-fixture:removed.native.test#stale[macosArm64]',
        ),
        root,
        priorCapabilities,
      ),
      throwsStateError,
    );
  });
  test('dart.residual exact value semantics', _verifyValueSemantics);
  for (final claim in claims) {
    final testId = claim.executedTests.single;
    test(testId, () {
      expect(claim.publicSymbols, hasLength(1));
      expect(claim.sharedScenarios, _expectedScenarios(claim.capabilityKey));
      final symbol = claim.publicSymbols.single;
      final accessor = residualPublicAccessors[symbol];
      expect(accessor, isNotNull, reason: claim.capabilityKey);
      expect(() => accessor!(), returnsNormally);
      for (final evidenceId in claim.compilerEvidenceIds) {
        passedCompilerEvidence
            .putIfAbsent(evidenceId, () => <String>{})
            .add(symbol);
      }
      expect(passedTestIds.add(testId), isTrue);
    });
  }
}

void _verifyValueSemantics() {
  final messages = <CodexMessage>[_message, _message];
  final snapshot =
      CodexConversationSnapshot(summary: _summary, messages: messages);
  messages.clear();
  expect(snapshot.messages, hasLength(2));
  expect(snapshot.messages.clear, throwsUnsupportedError);
  expect(_message.capabilities,
      const <CodexCapability>{CodexCapability.webSearch});
  expect(_message.capabilities.clear, throwsUnsupportedError);
  expect(_skillInvocation.key, 'skill:skill.md');
  expect(_pluginInvocation.key, 'plugin:plugin://plugin@market');
  expect(_conversationState.canStartTurn, isTrue);
  expect(_conversationState.canReload, isTrue);
  expect(_conversationState.canCancelTurn, isFalse);
  expect(
    CodexConversationState(status: CodexConversationStatus.runningTurn)
        .canCancelTurn,
    isTrue,
  );
  expect(_elicitation.form, hasLength(2));
  expect(_response.content.clear, throwsUnsupportedError);
  expect(_hook.origin, CodexResourceOrigin.plugin);
  expect(_hook.canTrust, isTrue);
  expect(_pendingElicitation.requestId, _elicitation.requestId);
  expect(_connectorIntegration.id, _connector.id);
  expect(_apiKey.toString(), contains('**redacted**'));
  expect(CodexNewHostState.instance, same(CodexNewHostState.instance));
  expect(
    () => CodexAuthorizationUrl.external('http://example.test/auth'),
    throwsArgumentError,
  );
  expect(
    () => CodexFormField(
      name: 'field',
      title: 'Field',
      type: CodexFormFieldType.string,
      minimumLength: 2,
      maximumLength: 1,
    ),
    throwsArgumentError,
  );
  expect(
      () => CodexPathWorkspaceSelection('bad\u0000path'), throwsArgumentError);
}
