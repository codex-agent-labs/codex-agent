import 'dart:async';
import 'dart:convert';
import 'dart:ffi';
import 'dart:io';

import 'package:codex_agent/codex_agent.dart';
import 'package:codex_agent/src/ffi.dart'
    show
        CodexNativeAgent,
        CodexNativeContext,
        NativeApi,
        authenticatedRuntimeLibraryForTesting,
        nativeMemory,
        newHandleSlot;
import 'package:test/test.dart';

import 'test_inputs.dart';
import 'native_fixture.dart';

final class DartAgentClaim {
  const DartAgentClaim({
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

typedef _AgentGetterNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeAgent>,
  Pointer<Pointer<Void>>,
);
typedef _AgentGetterDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeAgent>,
  Pointer<Pointer<Void>>,
);
typedef _CallCountNative = Int32 Function(Pointer<Uint8>);
typedef _CallCountDart = int Function(Pointer<Uint8>);

String _member(String capability) => capability
    .split('|abi=io.github.codex_agent_labs.codexagent.agent/')[1]
    .split('|')
    .first
    .split('.')
    .last;

List<String> _headers(DartAgentClaim claim) => claim.compilerEvidenceIds
    .where((value) => value.startsWith('c-header:'))
    .map((value) => value.substring('c-header:'.length))
    .toList();

const _serviceFields = <String, String>{
  'authentication': 'agentAuthentication',
  'connectors': 'agentConnectors',
  'hooks': 'agentHooks',
  'integrationAuthorization': 'agentIntegrationAuthorization',
  'interactions': 'agentInteractions',
  'mcpServers': 'agentMcpServers',
  'models': 'agentModels',
  'plugins': 'agentPlugins',
  'skills': 'agentSkills',
};

Set<String> verifyAgentClaims(
  List<DartAgentClaim> claims,
  Directory root, {
  String? sourceOverride,
}) {
  final report = jsonDecode(canonicalApiReport().readAsStringSync())
      as Map<String, dynamic>;
  final canonical = <String>{
    for (final owner in report['owners'] as List<dynamic>)
      if (((owner as Map<String, dynamic>)['name'] as String).split('/').last ==
          'CodexAgent')
        for (final capability in owner['capabilities'] as List<dynamic>)
          if ((capability as String).contains('|kind=property|')) capability,
  };
  if (claims.length != 11 ||
      canonical.length != 11 ||
      claims.map((claim) => claim.capabilityKey).toSet().length != 11 ||
      !canonical.containsAll(claims.map((claim) => claim.capabilityKey)) ||
      !claims
          .map((claim) => claim.capabilityKey)
          .toSet()
          .containsAll(canonical)) {
    throw StateError('Dart Agent claims are incomplete, stale, or overclaimed');
  }

  final bootstrap = jsonDecode(cAbiBootstrapEvidence().readAsStringSync())
      as Map<String, dynamic>;
  final bootstrapClaims = <String, Map<String, dynamic>>{
    for (final claim in bootstrap['claims'] as List<dynamic>)
      (claim as Map<String, dynamic>)['capabilityKey'] as String: claim,
  };
  final passedFixtures = <String>{
    for (final item in bootstrap['nativeTests'] as List<dynamic>)
      if ((item as Map<String, dynamic>)['status'] == 'passed')
        item['testId'] as String,
  };
  final header = cAbiHeader().readAsStringSync();
  final source = sourceOverride ??
      <String>[
        File('${root.path}/codex-agent-bindings/dart/lib/src/'
                'client.dart')
            .readAsStringSync(),
        File('${root.path}/codex-agent-bindings/dart/lib/src/'
                'leaf_services.dart')
            .readAsStringSync(),
        File('${root.path}/codex-agent-bindings/dart/lib/src/'
                'ffi.dart')
            .readAsStringSync(),
      ].join('\n');
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
    final member = _member(claim.capabilityKey);
    final expectedEvidence = <String>{
      ...headers.map((value) => 'c-header:$value'),
      ...fixtures.map((value) => 'cabi-fixture:$value'),
      'dart-analyzer-agent:${index.toString().padLeft(3, '0')}',
    };
    if (claim.publicSymbols.single != 'CodexAgent.$member' ||
        claim.executedTests.single !=
            'dart.agent:${index.toString().padLeft(3, '0')}' ||
        claim.compilerEvidenceIds.toSet().length != expectedEvidence.length ||
        !claim.compilerEvidenceIds.toSet().containsAll(expectedEvidence)) {
      throw StateError('inexact Dart Agent evidence: ${claim.capabilityKey}');
    }
    final symbol = headers.single;
    if (!RegExp('\\b${RegExp.escape(symbol)}\\s*\\(').hasMatch(header) ||
        !compact.contains("'$symbol'")) {
      throw StateError('missing exact Agent C edge: $symbol');
    }
    final field = _serviceFields[member];
    if (field != null) {
      if (!compact.contains('get$member=>') ||
          !compact.contains("'$symbol',$field"
              .replaceFirst(field, '_leafApi(_native.owner).$field')) ||
          !RegExp('${RegExp.escape(field)}=library\\.lookupFunction<[^;]+>'
                  "\\('$symbol'\\)")
              .hasMatch(compact)) {
        throw StateError('disconnected Agent service edge: $member');
      }
    } else if (member == 'conversations') {
      if (!compact.contains('getconversations=>_requireOpenProjection('
              '_conversations??=_acquireConversations())') ||
          !RegExp(
            'CodexConversations_acquireConversations\\(\\)\\{[^}]*'
            'api\\.agentConversations\\([^}]*'
            "'$symbol'",
          ).hasMatch(compact)) {
        throw StateError('disconnected Agent conversations edge');
      }
    } else if (member == 'workspace') {
      if (!compact.contains('getworkspace=>_requireOpenProjection('
              '_workspace??=_readWorkspace())') ||
          !RegExp(
            'CodexWorkspace_readWorkspace\\(\\)\\{[^}]*'
            'api\\.agentWorkspace\\([^}]*'
            "'$symbol'",
          ).hasMatch(compact) ||
          !compact.contains('api.workspaceDestroy(') ||
          !compact.contains('api.workspacePath') ||
          !compact.contains('api.workspaceDisplayName')) {
        throw StateError('disconnected Agent workspace edge');
      }
    } else {
      throw StateError('unknown Agent member: $member');
    }
    for (final fixture in fixtures) {
      if (!passedFixtures.contains(fixture)) {
        throw StateError('stale or failed C ABI fixture: $fixture');
      }
    }
    references.add(symbol);
  }
  return references;
}

Future<void> verifyRealAgentBoundary(
  List<DartAgentClaim> claims,
  Directory root,
) async {
  if (!Platform.isMacOS) return;
  final library = requiredRealLibrary();
  final architecture = await Process.run('uname', const <String>['-m']);
  if (architecture.exitCode != 0 ||
      (architecture.stdout as String).trim() != 'arm64') {
    throw StateError('real Dart Agent receipt requires macOS Arm64');
  }

  NativeApi.load(library.absolute.path);
  final dylib = authenticatedRuntimeLibraryForTesting(library.absolute.path);
  final output = newHandleSlot<Void>();
  final rows = <String>['capabilityKey\tcSymbol\tstatus'];
  try {
    final sorted = claims.toList()
      ..sort(
          (left, right) => left.capabilityKey.compareTo(right.capabilityKey));
    for (final claim in sorted) {
      final symbol = _headers(claim).single;
      final call =
          dylib.lookupFunction<_AgentGetterNative, _AgentGetterDart>(symbol);
      output.value = nullptr;
      final status = call(
        Pointer<CodexNativeContext>.fromAddress(0),
        Pointer<CodexNativeAgent>.fromAddress(0),
        output,
      );
      if (status == 0 || output.value != nullptr) {
        throw StateError('Agent boundary did not fail closed: $symbol');
      }
      rows.add('${claim.capabilityKey}\t$symbol\tpassed');
    }
  } finally {
    nativeMemory.free(output);
  }
  final receipt = File('build/parity/agent-native-tests.tsv');
  receipt.parent.createSync(recursive: true);
  receipt.writeAsStringSync('${rows.join('\n')}\n');
}

Future<String> _buildFixture() async {
  final output = nativeFixturePath(
    'codex_agent_dart_agent_$pid'
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
    throw StateError('Agent fixture compilation failed: ${result.stderr}');
  }
  return output;
}

int _callCount(_CallCountDart count, String symbol) {
  final bytes = utf8.encode('$symbol\x00');
  final pointer = nativeMemory.allocate<Uint8>(bytes.length);
  try {
    pointer.asTypedList(bytes.length).setAll(0, bytes);
    return count(pointer);
  } finally {
    nativeMemory.free(pointer);
  }
}

Future<({CodexHost host, CodexAgent agent})> _open(String path) async {
  final host = await CodexHost.create(
    bundleDirectory: '.',
    dataDirectory: '.',
    clientInfo: CodexClientInfo(name: 'agent', title: 'Agent', version: '1'),
    libraryPath: path,
  );
  return (host: host, agent: (await host.currentState).agent!);
}

Object _projection(CodexAgent agent, String member) => switch (member) {
      'authentication' => agent.authentication,
      'connectors' => agent.connectors,
      'conversations' => agent.conversations,
      'hooks' => agent.hooks,
      'integrationAuthorization' => agent.integrationAuthorization,
      'interactions' => agent.interactions,
      'mcpServers' => agent.mcpServers,
      'models' => agent.models,
      'plugins' => agent.plugins,
      'skills' => agent.skills,
      'workspace' => agent.workspace,
      _ => throw StateError('unknown Agent projection: $member'),
    };

Future<void> _expectClosed(Object projection, String member) async {
  FutureOr<Object?> action() => switch (member) {
        'authentication' => (projection as CodexAuthentication).state.current,
        'connectors' => (projection as CodexConnectors).isAvailable,
        'conversations' => (projection as CodexConversations).currentActive,
        'hooks' => (projection as CodexHooks).isAvailable,
        'integrationAuthorization' =>
          (projection as CodexIntegrationAuthorization).state.current,
        'interactions' => (projection as CodexInteractions).state.current,
        'mcpServers' => (projection as CodexMcpServers).isAvailable,
        'models' => (projection as CodexModels).list(),
        'plugins' => (projection as CodexPlugins).isAvailable,
        'skills' => (projection as CodexSkills).isAvailable,
        _ => throw StateError('unknown close projection: $member'),
      };
  await expectLater(
    Future<Object?>.sync(action),
    throwsA(isA<CodexException>()),
  );
}

Future<void> _closeProjection(Object projection, String member) =>
    switch (member) {
      'authentication' => (projection as CodexAuthentication).close(),
      'connectors' => (projection as CodexConnectors).close(),
      'conversations' => (projection as CodexConversations).close(),
      'hooks' => (projection as CodexHooks).close(),
      'integrationAuthorization' =>
        (projection as CodexIntegrationAuthorization).close(),
      'interactions' => (projection as CodexInteractions).close(),
      'mcpServers' => (projection as CodexMcpServers).close(),
      'models' => (projection as CodexModels).close(),
      'plugins' => (projection as CodexPlugins).close(),
      'skills' => (projection as CodexSkills).close(),
      _ => throw StateError('unknown close projection: $member'),
    };

String _releaseSymbol(String member) => switch (member) {
      'authentication' => 'codex_agent_authentication_release',
      'connectors' => 'codex_agent_connectors_release',
      'conversations' => 'codex_agent_conversations_release',
      'hooks' => 'codex_agent_hooks_release',
      'integrationAuthorization' =>
        'codex_agent_integration_authorization_release',
      'interactions' => 'codex_agent_interactions_release',
      'mcpServers' => 'codex_agent_mcp_servers_release',
      'models' => 'codex_agent_models_release',
      'plugins' => 'codex_agent_plugins_release',
      'skills' => 'codex_agent_skills_release',
      _ => throw StateError('unknown release projection: $member'),
    };

void registerAgentParity(
  List<DartAgentClaim> claims,
  Directory root,
  Map<String, Set<String>> passedCompilerEvidence,
  Set<String> passedTestIds,
) {
  late final Future<String> fixture = _buildFixture();
  test('dart.agent.inventory', () {
    expect(() => verifyAgentClaims(claims, root), returnsNormally);
  });
  test('dart.agent inventory and production edges fail closed', () {
    expect(() => verifyAgentClaims(claims.sublist(1), root), throwsStateError);
    final source = <String>[
      File('${root.path}/codex-agent-bindings/dart/lib/src/'
              'client.dart')
          .readAsStringSync(),
      File('${root.path}/codex-agent-bindings/dart/lib/src/'
              'leaf_services.dart')
          .readAsStringSync(),
      File('${root.path}/codex-agent-bindings/dart/lib/src/'
              'ffi.dart')
          .readAsStringSync(),
    ].join('\n');
    for (final symbol in claims.expand(_headers)) {
      expect(
        () => verifyAgentClaims(
          claims,
          root,
          sourceOverride:
              source.replaceFirst("'$symbol'", "'codex_agent_removed'"),
        ),
        throwsStateError,
        reason: 'missing Agent production edge was accepted: $symbol',
      );
    }
  });

  final sorted = claims.toList()
    ..sort((left, right) => left.capabilityKey.compareTo(right.capabilityKey));
  for (final claim in sorted) {
    test(claim.executedTests.single, () async {
      final path = await fixture;
      final library = authenticatedRuntimeLibraryForTesting(path);
      final count = library.lookupFunction<_CallCountNative, _CallCountDart>(
          'codex_agent_dart_leaf_call_count');
      final symbol = _headers(claim).single;
      final member = _member(claim.capabilityKey);
      final before = _callCount(count, symbol);
      final opened = await _open(path);
      try {
        final first = _projection(opened.agent, member);
        expect(_projection(opened.agent, member), same(first));
        expect(_callCount(count, symbol), before + 1);
        if (member == 'workspace') {
          final workspace = first as CodexWorkspace;
          expect(workspace.path, '/agent-workspace');
          expect(workspace.displayName, 'Agent Workspace');
          expect(_callCount(count, 'codex_agent_workspace_destroy'),
              greaterThan(0));
          await opened.agent.close();
          expect(
            () => _projection(opened.agent, member),
            throwsA(isA<CodexClosedException>()),
          );
          expect(workspace.path, '/agent-workspace');
          expect(workspace.displayName, 'Agent Workspace');
        } else {
          final release = _releaseSymbol(member);
          final releaseBefore = _callCount(count, release);
          await opened.agent.close();
          expect(
            () => _projection(opened.agent, member),
            throwsA(isA<CodexClosedException>()),
          );
          await _expectClosed(first, member);
          await _closeProjection(first, member);
          expect(_callCount(count, release), greaterThan(releaseBefore));
        }
        expect(_callCount(count, 'codex_agent_agent_release'), greaterThan(0));
      } finally {
        await opened.agent.close();
        await opened.host.close();
      }
      final expectedScenarios = member == 'workspace'
          ? <String>['parent-child-ownership', 'value-conversion']
          : <String>[
              'identity',
              'parent-child-ownership',
              'value-conversion',
            ];
      expect(claim.sharedScenarios, expectedScenarios);
      for (final evidence in claim.compilerEvidenceIds) {
        passedCompilerEvidence
            .putIfAbsent(evidence, () => <String>{})
            .add(claim.publicSymbols.single);
      }
      expect(passedTestIds.add(claim.executedTests.single), isTrue);
    });
  }
}
