import 'dart:convert';
import 'dart:ffi';
import 'dart:io';

import 'package:codex_agent/codex_agent.dart';
import 'package:codex_agent/src/client.dart'
    show createLeafServicesForTesting, leafNativeCallObserver;
import 'package:codex_agent/src/ffi.dart'
    show authenticatedRuntimeLibraryForTesting, nativeMemory;
import 'package:test/test.dart';

import 'test_inputs.dart';
import 'native_fixture.dart';

final class DartLeafClaim {
  const DartLeafClaim({
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

const _owners = <String>{
  'CodexAuthentication',
  'CodexConnectors',
  'CodexHooks',
  'CodexIntegrationAuthorization',
  'CodexInteractions',
  'CodexMcpServers',
  'CodexModels',
  'CodexPlugins',
  'CodexSkills',
};

const _leafScenarios = <String, List<String>>{
  'CodexAuthentication.authenticate': <String>[
    'async-success',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexAuthentication.cancel': <String>[
    'async-success',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexAuthentication.signOut': <String>[
    'async-success',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexAuthentication.isAuthenticatedState': <String>[
    'parent-child-ownership',
    'state-current-value',
    'state-subsequent-value',
    'subscription-cancellation',
    'terminal-delivery',
    'value-conversion',
  ],
  'CodexAuthentication.isAuthenticatingState': <String>[
    'parent-child-ownership',
    'state-current-value',
    'state-subsequent-value',
    'subscription-cancellation',
    'terminal-delivery',
    'value-conversion',
  ],
  'CodexAuthentication.state': <String>[
    'parent-child-ownership',
    'state-current-value',
    'state-subsequent-value',
    'subscription-cancellation',
    'terminal-delivery',
    'value-conversion',
  ],
  'CodexConnectors.list': <String>[
    'async-success',
    'collection-immutability-ordering',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexConnectors.isAvailable': <String>[
    'parent-child-ownership',
    'repeated-close-dispose',
    'value-conversion',
  ],
  'CodexHooks.install': <String>[
    'async-success',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexHooks.list': <String>[
    'async-success',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexHooks.trust': <String>[
    'async-success',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexHooks.uninstall': <String>[
    'async-success',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexHooks.isAvailable': <String>[
    'parent-child-ownership',
    'repeated-close-dispose',
    'value-conversion',
  ],
  'CodexIntegrationAuthorization.authorize': <String>[
    'async-success',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexIntegrationAuthorization.cancel': <String>[
    'async-success',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexIntegrationAuthorization.activeState': <String>[
    'nullability',
    'parent-child-ownership',
    'state-current-value',
    'state-subsequent-value',
    'subscription-cancellation',
    'terminal-delivery',
    'value-conversion',
  ],
  'CodexIntegrationAuthorization.isAuthorizingState': <String>[
    'parent-child-ownership',
    'state-current-value',
    'state-subsequent-value',
    'subscription-cancellation',
    'terminal-delivery',
    'value-conversion',
  ],
  'CodexIntegrationAuthorization.state': <String>[
    'parent-child-ownership',
    'state-current-value',
    'state-subsequent-value',
    'subscription-cancellation',
    'terminal-delivery',
    'value-conversion',
  ],
  'CodexInteractions.openUrl': <String>[
    'async-failure',
    'async-success',
    'cancellation',
    'identity',
    'parent-child-ownership',
    'structured-failure',
    'value-conversion',
  ],
  'CodexInteractions.resolveApproval': <String>[
    'async-success',
    'cancellation',
    'identity',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexInteractions.resolveElicitation': <String>[
    'async-success',
    'cancellation',
    'identity',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexInteractions.approvalsState': <String>[
    'collection-immutability-ordering',
    'identity',
    'parent-child-ownership',
    'state-current-value',
    'state-subsequent-value',
    'subscription-cancellation',
    'terminal-delivery',
    'value-conversion',
  ],
  'CodexInteractions.elicitationsState': <String>[
    'collection-immutability-ordering',
    'identity',
    'parent-child-ownership',
    'state-current-value',
    'state-subsequent-value',
    'subscription-cancellation',
    'terminal-delivery',
    'value-conversion',
  ],
  'CodexInteractions.state': <String>[
    'identity',
    'parent-child-ownership',
    'state-current-value',
    'state-subsequent-value',
    'subscription-cancellation',
    'terminal-delivery',
    'value-conversion',
  ],
  'CodexMcpServers.add': <String>[
    'async-success',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexMcpServers.list': <String>[
    'async-success',
    'collection-immutability-ordering',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexMcpServers.remove': <String>[
    'async-success',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexMcpServers.isAvailable': <String>[
    'parent-child-ownership',
    'repeated-close-dispose',
    'value-conversion',
  ],
  'CodexModels.list': <String>[
    'async-success',
    'collection-immutability-ordering',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexModels.resolveEffort': <String>[
    'async-success',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexModels.resolveServiceTier': <String>[
    'async-success',
    'nullability',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexModels.resolve': <String>[
    'async-success',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexPlugins.install': <String>[
    'async-success',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexPlugins.list': <String>[
    'async-success',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexPlugins.read': <String>[
    'async-success',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexPlugins.uninstall': <String>[
    'async-success',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexPlugins.isAvailable': <String>[
    'parent-child-ownership',
    'repeated-close-dispose',
    'value-conversion',
  ],
  'CodexSkills.install': <String>[
    'async-success',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexSkills.list': <String>[
    'async-success',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexSkills.read': <String>[
    'async-success',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexSkills.uninstall': <String>[
    'async-success',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexSkills.isAvailable': <String>[
    'parent-child-ownership',
    'repeated-close-dispose',
    'value-conversion',
  ],
};

String _owner(String capability) =>
    capability.split('|owner=')[1].split('|').first.split('/').last;
String _member(String capability) => capability
    .split('|abi=io.github.codex_agent_labs.codexagent.agent/')[1]
    .split('|')
    .first
    .split('.')
    .last;

String _publicSymbol(String capability, List<String> headers) {
  final owner = _owner(capability);
  final member = _member(capability);
  if (owner == 'CodexInteractions' && member == 'resolve') {
    return headers.contains('codex_agent_interactions_resolve_approval')
        ? 'CodexInteractions.resolveApproval'
        : 'CodexInteractions.resolveElicitation';
  }
  final projection = switch ('$owner.$member') {
    'CodexAuthentication.isAuthenticated' =>
      'CodexAuthentication.isAuthenticatedState',
    'CodexAuthentication.isAuthenticating' =>
      'CodexAuthentication.isAuthenticatingState',
    'CodexIntegrationAuthorization.active' =>
      'CodexIntegrationAuthorization.activeState',
    'CodexIntegrationAuthorization.isAuthorizing' =>
      'CodexIntegrationAuthorization.isAuthorizingState',
    'CodexInteractions.approvals' => 'CodexInteractions.approvalsState',
    'CodexInteractions.elicitations' => 'CodexInteractions.elicitationsState',
    _ => '$owner.$member',
  };
  return projection;
}

String _primaryCall(DartLeafClaim claim) => claim.compilerEvidenceIds
    .where((item) => item.startsWith('c-header:'))
    .map((item) => item.substring('c-header:'.length))
    .firstWhere((item) =>
        item != 'codex_agent_operation_result' &&
        !item.startsWith('codex_agent_operation_') &&
        !item.endsWith('_subscribe') &&
        !item.endsWith('_value'));

String _servicePrefix(String owner) => switch (owner) {
      'CodexAuthentication' => 'codex_agent_authentication_',
      'CodexConnectors' => 'codex_agent_connectors_',
      'CodexHooks' => 'codex_agent_hooks_',
      'CodexIntegrationAuthorization' =>
        'codex_agent_integration_authorization_',
      'CodexInteractions' => 'codex_agent_interactions_',
      'CodexMcpServers' => 'codex_agent_mcp_servers_',
      'CodexModels' => 'codex_agent_models_',
      'CodexPlugins' => 'codex_agent_plugins_',
      'CodexSkills' => 'codex_agent_skills_',
      _ => throw StateError('unknown leaf owner: $owner'),
    };

List<String> _serviceCalls(DartLeafClaim claim) => claim.compilerEvidenceIds
    .where((item) => item.startsWith('c-header:'))
    .map((item) => item.substring('c-header:'.length))
    .where(
        (item) => item.startsWith(_servicePrefix(_owner(claim.capabilityKey))))
    .toList();

int _fixtureCallCount(
  int Function(Pointer<Uint8>) count,
  String symbol,
) {
  final bytes = utf8.encode('$symbol\x00');
  final pointer = nativeMemory.allocate<Uint8>(bytes.length);
  try {
    pointer.asTypedList(bytes.length).setAll(0, bytes);
    return count(pointer);
  } finally {
    nativeMemory.free(pointer);
  }
}

Set<String> verifyLeafClaims(
  List<DartLeafClaim> claims,
  Directory root, {
  String? sourceOverride,
}) {
  final report = jsonDecode(canonicalApiReport().readAsStringSync())
      as Map<String, dynamic>;
  final canonical = <String>{
    for (final owner in report['owners'] as List<dynamic>)
      if (_owners.contains(
          ((owner as Map<String, dynamic>)['name'] as String).split('/').last))
        for (final capability in owner['capabilities'] as List<dynamic>)
          if ((capability as String).contains('|kind=function|') ||
              capability.contains('|kind=property|'))
            capability,
  };
  if (claims.length != 42 ||
      _leafScenarios.length != 42 ||
      claims.map((claim) => claim.capabilityKey).toSet().length != 42 ||
      canonical.length != 42 ||
      !canonical.containsAll(claims.map((claim) => claim.capabilityKey)) ||
      !claims
          .map((claim) => claim.capabilityKey)
          .toSet()
          .containsAll(canonical) ||
      !_leafScenarios.keys
          .toSet()
          .containsAll(claims.expand((claim) => claim.publicSymbols))) {
    throw StateError('Dart leaf claims are incomplete, stale, or overclaimed');
  }
  final bootstrap = jsonDecode(cAbiBootstrapEvidence().readAsStringSync())
      as Map<String, dynamic>;
  final bootstrapClaims = <String, Map<String, dynamic>>{
    for (final claim in bootstrap['claims'] as List<dynamic>)
      (claim as Map<String, dynamic>)['capabilityKey'] as String: claim,
  };
  final passedNativeTests = <String>{
    for (final test in bootstrap['nativeTests'] as List<dynamic>)
      if ((test as Map<String, dynamic>)['status'] == 'passed')
        test['testId'] as String,
  };
  final header = cAbiHeader().readAsStringSync();
  final source = sourceOverride ??
      File('${root.path}/codex-agent-bindings/dart/lib/src/'
              'leaf_services.dart')
          .readAsStringSync();
  final compact = source.replaceAll(RegExp(r'\s+'), '');
  final references = <String>{};
  final sorted = claims.toList()
    ..sort((left, right) => left.capabilityKey.compareTo(right.capabilityKey));
  for (var index = 0; index < sorted.length; index++) {
    final claim = sorted[index];
    final bootstrapClaim = bootstrapClaims[claim.capabilityKey];
    if (bootstrapClaim == null) throw StateError('missing bootstrap claim');
    final headers =
        (bootstrapClaim['headerReferences'] as List<dynamic>).cast<String>();
    final fixtures =
        (bootstrapClaim['nativeTestIds'] as List<dynamic>).cast<String>();
    final expectedEvidence = <String>{
      ...headers.map((item) => 'c-header:$item'),
      ...fixtures.map((item) => 'cabi-fixture:$item'),
      'dart-analyzer-leaf:${index.toString().padLeft(3, '0')}',
    };
    if (claim.publicSymbols.single !=
            _publicSymbol(claim.capabilityKey, headers) ||
        claim.executedTests.single !=
            'dart.leaf:${index.toString().padLeft(3, '0')}' ||
        claim.compilerEvidenceIds.toSet().length != expectedEvidence.length ||
        !claim.compilerEvidenceIds.toSet().containsAll(expectedEvidence) ||
        claim.sharedScenarios.join(',') !=
            _leafScenarios[claim.publicSymbols.single]!.join(',')) {
      throw StateError('inexact Dart leaf evidence: ${claim.capabilityKey}');
    }
    for (final symbol in headers) {
      if (!RegExp('\\b${RegExp.escape(symbol)}\\s*\\(').hasMatch(header)) {
        throw StateError('stale C header reference: $symbol');
      }
      references.add(symbol);
    }
    for (final fixture in fixtures) {
      if (!passedNativeTests.contains(fixture)) {
        throw StateError('stale or failed C ABI fixture: $fixture');
      }
    }
    if (!compact.contains(claim.publicSymbols.single.split('.').last)) {
      throw StateError(
          'missing public Dart member: ${claim.publicSymbols.single}');
    }
    for (final serviceCall in _serviceCalls(claim)) {
      final lookup = RegExp(
        "lookupFunction<[^']*?>\\('${RegExp.escape(serviceCall)}'\\)",
      );
      if (!lookup.hasMatch(compact)) {
        throw StateError('missing exact production lookup: $serviceCall');
      }
    }
  }
  return references;
}

Set<String> _verifyRealBoundarySource(
  List<DartLeafClaim> claims,
  String source,
) {
  final expected = claims.expand(_serviceCalls).toSet();
  final declared = RegExp(r'REJECTED\((codex_agent_[a-z0-9_]+),')
      .allMatches(source)
      .map((match) => match.group(1)!)
      .toSet();
  if (expected.length != 62 ||
      declared.length != 62 ||
      !expected.containsAll(declared) ||
      !declared.containsAll(expected)) {
    throw StateError('real SDK leaf boundary source is incomplete or stale');
  }
  for (final symbol in expected) {
    final directCall = RegExp(
      'REJECTED\\(${RegExp.escape(symbol)},[^;]*'
      '${RegExp.escape(symbol)}\\(',
      dotAll: true,
    );
    if (!directCall.hasMatch(source)) {
      throw StateError('real SDK boundary does not directly call $symbol');
    }
  }
  return expected;
}

Future<void> verifyRealLeafBoundary(
  List<DartLeafClaim> claims,
  Directory root,
) async {
  if (!Platform.isMacOS) return;
  final source = File('${root.path}/codex-agent-bindings/'
      'dart/test/native/real_leaf_boundary.c');
  final expected = _verifyRealBoundarySource(claims, source.readAsStringSync());
  final library = requiredRealLibrary();
  final architecture = await Process.run('uname', ['-m']);
  if (architecture.exitCode != 0 ||
      (architecture.stdout as String).trim() != 'arm64') {
    throw StateError('real leaf receipt must execute on macOS Arm64');
  }
  final executable = '${Directory.systemTemp.path}/'
      'codex_agent_dart_real_leaf_$pid';
  final compile = await Process.run('cc', [
    '-std=c11',
    '-Wall',
    '-Wextra',
    '-Werror',
    '-pedantic',
    '-I',
    requiredCSdkInclude().path,
    source.absolute.path,
    library.absolute.path,
    '-Wl,-rpath,${library.absolute.parent.path}',
    '-o',
    executable,
  ]);
  if (compile.exitCode != 0) {
    throw StateError('real leaf boundary compile failed: ${compile.stderr}');
  }
  try {
    final run = await Process.run(executable, const []);
    if (run.exitCode != 0) {
      throw StateError('real leaf boundary failed: ${run.stderr}');
    }
    final executed = <String, int>{};
    for (final line in const LineSplitter().convert(run.stdout as String)) {
      final columns = line.split('\t');
      if (columns.length != 3 || columns[2] != 'null-handle-rejected') {
        throw StateError('malformed real leaf receipt: $line');
      }
      final status = int.parse(columns[1]);
      if (status == 0 ||
          executed.putIfAbsent(columns[0], () => status) != status) {
        throw StateError('invalid real leaf boundary row: $line');
      }
    }
    if (executed.length != 62 ||
        !executed.keys.toSet().containsAll(expected) ||
        !expected.containsAll(executed.keys)) {
      throw StateError('real leaf boundary execution is incomplete or stale');
    }
    final output = Directory('${root.path}/codex-agent-bindings/dart/'
        'build/parity')
      ..createSync(recursive: true);
    final sorted = claims.toList()
      ..sort(
          (left, right) => left.capabilityKey.compareTo(right.capabilityKey));
    File('${output.path}/leaf-real-sdk-receipt.tsv').writeAsStringSync(
      'capabilityKey\tpublicSymbol\texactNativeCalls\tboundary\tstatus\n'
      '${sorted.map((claim) => <String>[
            claim.capabilityKey,
            claim.publicSymbols.single,
            (_serviceCalls(claim)..sort()).join(','),
            'real-macos-arm64-null-handle',
            'passed',
          ].join('\t')).join('\n')}\n',
    );
  } finally {
    final file = File(executable);
    if (file.existsSync()) file.deleteSync();
  }
}

Future<String> _buildFixture() async {
  final output = nativeFixturePath(
    'codex_agent_dart_leaf_$pid'
    '${Platform.isMacOS ? '.dylib' : Platform.isWindows ? '.dll' : '.so'}',
  );
  final source = File('test/native/fake_codex_agent.c').absolute.path;
  final result = Platform.isWindows
      ? await Process.run('cl', <String>[
          '/nologo',
          '/LD',
          ...runtimeIdentityCompilerDefinitions(),
          source,
          '/link',
          '/OUT:$output'
        ])
      : await Process.run('cc', <String>[
          '-std=c11',
          '-Wall',
          '-Wextra',
          '-Werror',
          '-pedantic',
          ...runtimeIdentityCompilerDefinitions(),
          ...(Platform.isMacOS
              ? const <String>['-dynamiclib']
              : const <String>['-shared', '-fPIC', '-pthread']),
          source,
          '-o',
          output,
        ]);
  if (result.exitCode != 0) {
    throw StateError('leaf fixture compilation failed: ${result.stderr}');
  }
  return output;
}

Future<({CodexHost host, CodexAgent agent, dynamic services})> _openServices(
    String path) async {
  final host = await CodexHost.create(
    bundleDirectory: '.',
    dataDirectory: '.',
    clientInfo: CodexClientInfo(name: 'leaf', title: 'Leaf', version: '1'),
    libraryPath: path,
  );
  final agent = (await host.currentState).agent!;
  return (
    host: host,
    agent: agent,
    services: createLeafServicesForTesting(agent)
  );
}

Future<void> _closeServices(
    dynamic services, CodexAgent agent, CodexHost host) async {
  await services.authentication.close();
  await services.interactions.close();
  await services.integrationAuthorization.close();
  await services.models.close();
  await services.skills.close();
  await services.hooks.close();
  await services.plugins.close();
  await services.connectors.close();
  await services.mcpServers.close();
  await agent.close();
  await host.close();
}

final _model = CodexModel(
  id: 'model',
  displayName: 'Model',
  description: 'model',
  supportedEfforts: const ['high'],
  defaultEffort: 'high',
  isDefault: true,
);
final _skill = CodexSkill(
  name: 'skill',
  displayName: 'Skill',
  description: 'skill',
  path: '/skill',
  scope: CodexSkillScope.user,
  isEnabled: true,
);
final _hook = CodexHook(
  key: 'hook',
  currentHash: 'hash',
  isEnabled: true,
  eventName: 'sessionStart',
  handler: CodexAgentHookHandler.instance,
  isManaged: false,
  source: 'USER',
  sourcePath: '/hook',
  timeoutSeconds: 17,
  trustStatus: CodexHookTrustStatus.trusted,
);
const _plugin = CodexPluginReference(
  id: 'plugin-id',
  name: 'plugin',
  marketplaceName: 'marketplace',
);
final _mcpConfiguration = CodexMcpServerConfiguration(
  name: 'fixture_server',
  transport: CodexMcpHttpTransport(url: 'https://example.test/mcp'),
);
const _mcpServer = CodexMcpServer(
  name: 'fixture_server',
  displayName: 'Fixture server',
  authStatus: CodexMcpAuthStatus.oauth,
);

Future<void> _exercise(DartLeafClaim claim, dynamic s) async {
  final owner = _owner(claim.capabilityKey);
  final member = _member(claim.capabilityKey);
  final primary = _primaryCall(claim);
  switch ('$owner.$member') {
    case 'CodexAuthentication.authenticate':
      await s.authentication
          .authenticate(CodexApiKeyAuthentication('fixture-secret'));
      await s.authentication
          .authenticate(CodexChatGptBrowserAuthentication.instance);
      await s.authentication
          .authenticate(CodexChatGptDeviceCodeAuthentication.instance);
    case 'CodexAuthentication.cancel':
      await s.authentication.cancel();
    case 'CodexAuthentication.signOut':
      await s.authentication.signOut();
    case 'CodexAuthentication.state':
      expect((await s.authentication.state.current).status,
          CodexAuthenticationStatus.authenticated);
      expect((await s.authentication.state.changes.first).status,
          CodexAuthenticationStatus.authenticated);
    case 'CodexAuthentication.isAuthenticated':
      expect(await s.authentication.isAuthenticatedState.current, isTrue);
      expect(await s.authentication.isAuthenticatedState.changes.first, isTrue);
    case 'CodexAuthentication.isAuthenticating':
      expect(await s.authentication.isAuthenticatingState.current, isTrue);
      expect(
          await s.authentication.isAuthenticatingState.changes.first, isTrue);
    case 'CodexConnectors.list':
      final result =
          await s.connectors.list(forceReload: true) as List<CodexConnector>;
      expect(result.map((value) => value.id), ['connector', 'connector']);
    case 'CodexConnectors.isAvailable':
      expect(s.connectors.isAvailable, isTrue);
    case 'CodexHooks.list':
      expect((await s.hooks.list()).hooks.single.key, 'fixture-hook');
    case 'CodexHooks.install':
      expect((await s.hooks.install('/hook', CodexInstallationScope.user)).key,
          'fixture-hook');
    case 'CodexHooks.trust':
      await s.hooks.trust(_hook);
    case 'CodexHooks.uninstall':
      await s.hooks.uninstall(_hook);
    case 'CodexHooks.isAvailable':
      expect(s.hooks.isAvailable, isTrue);
    case 'CodexIntegrationAuthorization.authorize':
      await s.integrationAuthorization.authorize(
          CodexConnectorIntegration(CodexConnector(id: 'id', name: 'name')));
    case 'CodexIntegrationAuthorization.cancel':
      await s.integrationAuthorization.cancel();
    case 'CodexIntegrationAuthorization.state':
      expect((await s.integrationAuthorization.state.current).status,
          CodexIntegrationAuthorizationStatus.idle);
      expect((await s.integrationAuthorization.state.changes.first).status,
          CodexIntegrationAuthorizationStatus.idle);
    case 'CodexIntegrationAuthorization.active':
      expect(await s.integrationAuthorization.activeState.current,
          isA<CodexConnectorIntegration>());
      expect(await s.integrationAuthorization.activeState.changes.first,
          isA<CodexConnectorIntegration>());
    case 'CodexIntegrationAuthorization.isAuthorizing':
      expect(
          await s.integrationAuthorization.isAuthorizingState.current, isTrue);
      expect(await s.integrationAuthorization.isAuthorizingState.changes.first,
          isTrue);
    case 'CodexInteractions.openUrl':
      await s.interactions
          .openUrl((await s.interactions.elicitationsState.current).single);
    case 'CodexInteractions.resolve':
      if (primary.endsWith('resolve_approval')) {
        await s.interactions.resolveApproval(
            (await s.interactions.approvalsState.current).single,
            CodexApprovalDecision.accept);
      } else {
        await s.interactions.resolveElicitation(
            (await s.interactions.elicitationsState.current).single,
            CodexElicitationResponse(
              action: CodexElicitationAction.cancel,
            ));
      }
    case 'CodexInteractions.approvals':
      expect((await s.interactions.approvalsState.current).single.requestId,
          'approval-1');
      expect(
          (await s.interactions.approvalsState.changes.first).single.requestId,
          'approval-1');
    case 'CodexInteractions.elicitations':
      expect((await s.interactions.elicitationsState.current).single.requestId,
          'elicitation-1');
      expect(
          (await s.interactions.elicitationsState.changes.first)
              .single
              .requestId,
          'elicitation-1');
    case 'CodexInteractions.state':
      expect((await s.interactions.state.current).pending, isEmpty);
      expect((await s.interactions.state.changes.first).pending, isEmpty);
    case 'CodexMcpServers.list':
      final result = await s.mcpServers.list() as List<CodexMcpServer>;
      expect(result.map((CodexMcpServer value) => value.name),
          ['fixture_server', 'fixture_server']);
    case 'CodexMcpServers.add':
      expect(
          (await s.mcpServers.add(_mcpConfiguration)).name, 'fixture_server');
    case 'CodexMcpServers.remove':
      await s.mcpServers.remove(_mcpServer);
    case 'CodexMcpServers.isAvailable':
      expect(s.mcpServers.isAvailable, isTrue);
    case 'CodexModels.list':
      final result = await s.models.list() as List<CodexModel>;
      expect(result.map((CodexModel value) => value.id), ['model', 'model']);
    case 'CodexModels.resolve':
      expect((await s.models.resolve()).id, 'model');
    case 'CodexModels.resolveEffort':
      expect(await s.models.resolveEffort(_model), 'high');
    case 'CodexModels.resolveServiceTier':
      expect((await s.models.resolveServiceTier(_model))?.id, 'tier');
    case 'CodexPlugins.list':
      expect((await s.plugins.list(forceReload: true)).plugins, hasLength(2));
    case 'CodexPlugins.read':
      expect((await s.plugins.read(_plugin)).description, 'fixture detail');
    case 'CodexPlugins.install':
      expect((await s.plugins.install(_plugin)).message, 'installed');
    case 'CodexPlugins.uninstall':
      await s.plugins.uninstall(_plugin);
    case 'CodexPlugins.isAvailable':
      expect(s.plugins.isAvailable, isTrue);
    case 'CodexSkills.list':
      expect((await s.skills.list(forceReload: true)).skills, hasLength(2));
    case 'CodexSkills.read':
      expect((await s.skills.read('/skill')).content, 'fixture skill content');
    case 'CodexSkills.install':
      expect(
          (await s.skills.install('/skill', CodexInstallationScope.user)).name,
          'skill');
    case 'CodexSkills.uninstall':
      await s.skills.uninstall(_skill);
    case 'CodexSkills.isAvailable':
      expect(s.skills.isAvailable, isTrue);
    default:
      throw StateError('unhandled leaf behavior: $owner.$member');
  }
}

void registerLeafServiceParity(
  List<DartLeafClaim> claims,
  Directory root,
  Map<String, Set<String>> passedCompilerEvidence,
  Set<String> passedTestIds,
) {
  late final Future<String> fixture = _buildFixture();
  test('dart.leaf.inventory', () {
    expect(() => verifyLeafClaims(claims, root), returnsNormally);
  });
  test('dart.leaf inventory and source chain fail closed', () {
    expect(() => verifyLeafClaims(claims.sublist(1), root), throwsStateError);
    final firstClaim = claims.first;
    expect(
      () => verifyLeafClaims(
        <DartLeafClaim>[
          DartLeafClaim(
            capabilityKey: firstClaim.capabilityKey,
            publicSymbols: firstClaim.publicSymbols,
            executedTests: firstClaim.executedTests,
            compilerEvidenceIds: firstClaim.compilerEvidenceIds,
            sharedScenarios: const <String>['remote-execution'],
          ),
          ...claims.skip(1),
        ],
        root,
      ),
      throwsStateError,
    );
    final source = File('${root.path}/codex-agent-bindings/'
            'dart/lib/src/leaf_services.dart')
        .readAsStringSync();
    final first = _primaryCall(claims.first);
    expect(
      () => verifyLeafClaims(
        claims,
        root,
        sourceOverride:
            "${source.replaceFirst("'$first'", "'codex_agent_removed_leaf'")}\n"
            "void fake() => leafNativeCallObserver?.call('$first');",
      ),
      throwsStateError,
    );
    final boundary = File('${root.path}/codex-agent-bindings/'
            'dart/test/native/real_leaf_boundary.c')
        .readAsStringSync();
    final serviceCall = _serviceCalls(claims.first).first;
    expect(
      () => _verifyRealBoundarySource(
        claims,
        boundary.replaceFirst(serviceCall, 'codex_agent_removed_leaf'),
      ),
      throwsStateError,
    );
  });
  final sorted = claims.toList()
    ..sort((left, right) => left.capabilityKey.compareTo(right.capabilityKey));
  for (final claim in sorted) {
    test(claim.executedTests.single, () async {
      final path = await fixture;
      final count = authenticatedRuntimeLibraryForTesting(path).lookupFunction<
          Int32 Function(Pointer<Uint8>),
          int Function(Pointer<Uint8>)>('codex_agent_dart_leaf_call_count');
      final serviceCalls = _serviceCalls(claim);
      final before = <String, int>{
        for (final symbol in serviceCalls)
          symbol: _fixtureCallCount(count, symbol),
      };
      final opened = await _openServices(path);
      final calls = <String>[];
      leafNativeCallObserver = calls.add;
      try {
        await _exercise(claim, opened.services);
        for (final symbol in serviceCalls) {
          expect(calls, contains(symbol),
              reason: 'missing exact trace: $symbol');
          expect(
            _fixtureCallCount(count, symbol),
            greaterThan(before[symbol]!),
            reason:
                'public behavior did not call exact fixture symbol: $symbol',
          );
        }
      } finally {
        leafNativeCallObserver = null;
        await _closeServices(opened.services, opened.agent, opened.host);
      }
      for (final evidence in claim.compilerEvidenceIds) {
        passedCompilerEvidence
            .putIfAbsent(evidence, () => <String>{})
            .add(claim.publicSymbols.single);
      }
      expect(passedTestIds.add(claim.executedTests.single), isTrue);
    });
  }
}
