import 'dart:async';
import 'dart:convert';
import 'dart:ffi';
import 'dart:io';

import 'package:codex_agent/codex_agent.dart';
import 'package:codex_agent/src/ffi.dart';
import 'package:test/test.dart';

import 'test_inputs.dart';
import 'native_fixture.dart';

final class DartHostClaim {
  const DartHostClaim({
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

const _hostPrefix =
    'common|owner=io.github.codex_agent_labs.codexagent.agent/CodexHost|';
const _readyPrefix =
    'common|owner=io.github.codex_agent_labs.codexagent.agent/CodexHostState.Ready|';

String _member(String capability) => capability
    .split('|abi=io.github.codex_agent_labs.codexagent.agent/')[1]
    .split('|')
    .first;

const _publicSymbols = <String, String>{
  'CodexHostState.Ready.<init>': 'CodexReadyHostState.new',
  'CodexHostState.Ready.agent': 'CodexReadyHostState.agent',
  'CodexHost.<init>': 'CodexHost.create',
  'CodexHost.close': 'CodexHost.close',
  'CodexHost.selectWorkspace': 'CodexHost.selectWorkspace',
  'CodexHost.start': 'CodexHost.start',
  'CodexHost.lifecycleState': 'CodexHost.state',
};

const _scenarios = <String, List<String>>{
  'CodexHostState.Ready.<init>': <String>[
    'identity',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexHostState.Ready.agent': <String>[
    'identity',
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexHost.<init>': <String>[
    'parent-child-ownership',
    'value-conversion',
  ],
  'CodexHost.close': <String>[
    'async-failure',
    'async-success',
    'cancellation',
    'parent-child-ownership',
    'repeated-close-dispose',
    'structured-failure',
    'value-conversion',
  ],
  'CodexHost.selectWorkspace': <String>[
    'async-failure',
    'async-success',
    'cancellation',
    'parent-child-ownership',
    'structured-failure',
    'value-conversion',
  ],
  'CodexHost.start': <String>[
    'async-failure',
    'async-success',
    'cancellation',
    'parent-child-ownership',
    'structured-failure',
    'value-conversion',
  ],
  'CodexHost.lifecycleState': <String>[
    'identity',
    'parent-child-ownership',
    'state-current-value',
    'state-subsequent-value',
    'subscription-cancellation',
    'terminal-delivery',
    'value-conversion',
  ],
};

final _publicReferences = <String, Object>{
  'CodexReadyHostState.new': (CodexAgent agent) => CodexReadyHostState(agent),
  'CodexReadyHostState.agent': (CodexReadyHostState state) => state.agent,
  'CodexHost.create': CodexHost.create,
  'CodexHost.close': (CodexHost host) => host.close(),
  'CodexHost.selectWorkspace': (CodexHost host, String path) =>
      host.selectWorkspace(path),
  'CodexHost.start': (CodexHost host) => host.start(),
  'CodexHost.state': (CodexHost host) => host.state,
};

List<String> _headers(DartHostClaim claim) => claim.compilerEvidenceIds
    .where((value) => value.startsWith('c-header:'))
    .map((value) => value.substring('c-header:'.length))
    .toList();

bool _sameSet(Set<String> left, Set<String> right) =>
    left.length == right.length && left.containsAll(right);

Set<String> verifyHostClaims(
  List<DartHostClaim> claims,
  Directory root, {
  String? clientSourceOverride,
  String? ffiSourceOverride,
}) {
  final report = jsonDecode(canonicalApiReport().readAsStringSync())
      as Map<String, dynamic>;
  final canonical = <String>{
    for (final owner in report['owners'] as List<dynamic>)
      for (final capability
          in (owner as Map<String, dynamic>)['capabilities'] as List<dynamic>)
        if ((capability as String).startsWith(_hostPrefix) ||
            capability.startsWith(_readyPrefix))
          capability,
  };
  if (claims.length != 7 ||
      canonical.length != 7 ||
      !_sameSet(
        claims.map((claim) => claim.capabilityKey).toSet(),
        canonical,
      ) ||
      !_sameSet(
        claims.expand((claim) => claim.publicSymbols).toSet(),
        _publicReferences.keys.toSet(),
      )) {
    throw StateError('Dart Host/Ready claims are incomplete or stale');
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
  final client = (clientSourceOverride ??
          File('${root.path}/codex-agent-bindings/dart/lib/src/'
                  'client.dart')
              .readAsStringSync())
      .replaceAll(RegExp(r'\s+'), '');
  final ffi = (ffiSourceOverride ??
          File('${root.path}/codex-agent-bindings/dart/lib/src/'
                  'ffi.dart')
              .readAsStringSync())
      .replaceAll(RegExp(r'\s+'), '');
  final references = <String>{};
  final sorted = claims.toList()
    ..sort((left, right) => left.capabilityKey.compareTo(right.capabilityKey));
  for (var index = 0; index < sorted.length; index++) {
    final claim = sorted[index];
    final member = _member(claim.capabilityKey);
    final bootstrapClaim = bootstrapClaims[claim.capabilityKey];
    if (bootstrapClaim == null) {
      throw StateError('missing Host bootstrap claim');
    }
    final headers =
        (bootstrapClaim['headerReferences'] as List<dynamic>).cast<String>();
    final fixtures =
        (bootstrapClaim['nativeTestIds'] as List<dynamic>).cast<String>();
    final expectedEvidence = <String>{
      ...headers.map((value) => 'c-header:$value'),
      ...fixtures.map((value) => 'cabi-fixture:$value'),
      'dart-analyzer-host:${index.toString().padLeft(3, '0')}',
    };
    if (claim.publicSymbols.single != _publicSymbols[member] ||
        claim.executedTests.single !=
            'dart.host:${index.toString().padLeft(3, '0')}' ||
        !_sameSet(claim.compilerEvidenceIds.toSet(), expectedEvidence) ||
        claim.sharedScenarios.join(',') != _scenarios[member]!.join(',')) {
      throw StateError('inexact Dart Host evidence: ${claim.capabilityKey}');
    }
    for (final reference in headers) {
      if (!RegExp(r'\b' + RegExp.escape(reference) + r'\b').hasMatch(header)) {
        throw StateError('stale Host header reference: $reference');
      }
      references.add(reference);
      if (reference.startsWith('codex_agent_') && !reference.endsWith('_t')) {
        if (!RegExp("lookupFunction<[^;]+?>\\('$reference',?\\)")
            .hasMatch(ffi)) {
          throw StateError('missing Host production lookup: $reference');
        }
      }
    }
    for (final fixture in fixtures) {
      if (!passedFixtures.contains(fixture)) {
        throw StateError('stale or failed Host fixture: $fixture');
      }
    }
    final edges = switch (member) {
      'CodexHostState.Ready.<init>' => <String>[
          'CodexHostStateKind.fromValue(',
          'api.hostStateKind(',
          'api.hostStateAgent(',
          'CodexReadyHostState(',
        ],
      'CodexHostState.Ready.agent' => <String>[
          'api.hostStateAgent(',
          'CodexReadyHostState(',
          'CodexAgentgetagent=>super.agent!;',
        ],
      'CodexHost.<init>' => <String>[
          'staticFuture<CodexHost>create(',
          'CodexHostOptionsStruct',
          'owner.api.hostCreate(',
        ],
      'CodexHost.close' => <String>[
          'Future<void>close(',
          'owner.api.hostClose(',
        ],
      'CodexHost.selectWorkspace' => <String>[
          'Future<void>selectWorkspace(',
          'CodexPathWorkspaceSelectionStruct',
          '_owner.api.hostSelectWorkspace(',
        ],
      'CodexHost.start' => <String>[
          'Future<void>start(',
          '_owner.api.hostStart(',
          'owner.api.operationResult(',
        ],
      'CodexHost.lifecycleState' => <String>[
          'CodexObservableState<CodexHostState>state;',
          '_owner.api.hostStateGet',
          '_owner.api.hostStateSubscribe(',
        ],
      _ => throw StateError('unknown Host capability: $member'),
    };
    for (final edge in edges) {
      if (!client.contains(edge)) {
        throw StateError('disconnected Host production edge: $member / $edge');
      }
    }
  }
  return references;
}

Future<void> verifyRealHostBoundary(
  List<DartHostClaim> claims,
  Directory root,
) async {
  if (!Platform.isMacOS) return;
  final library = requiredRealLibrary();
  NativeApi.load(library.absolute.path);
  final dylib = authenticatedRuntimeLibraryForTesting(library.absolute.path);
  final api = NativeApi.load(library.absolute.path);
  final handle = newHandleSlot<Void>();
  final scalar = nativeMemory.allocate<Int32>(sizeOf<Int32>());
  final rows = <String>['executedTestId\tnativeSymbol\tstatus'];
  try {
    for (final claim in claims.toList()
      ..sort(
          (left, right) => left.capabilityKey.compareTo(right.capabilityKey))) {
      for (final symbol in _headers(claim)
          .where((value) => value.startsWith('codex_agent_'))
          .where((value) => !value.endsWith('_t'))) {
        dylib.lookup<NativeFunction<Void Function()>>(symbol);
        handle.value = nullptr;
        scalar.value = 0;
        final status = switch (symbol) {
          'codex_agent_host_create' => api.hostCreate(
              nullptr,
              nullptr,
              handle.cast<Pointer<CodexNativeHost>>(),
            ),
          'codex_agent_host_close' => api.hostClose(
              nullptr,
              nullptr,
              nullptr.cast<NativeFunction<OperationCallbackNative>>(),
              nullptr,
              handle.cast<Pointer<CodexNativeOperation>>(),
            ),
          'codex_agent_host_select_workspace' => api.hostSelectWorkspace(
              nullptr,
              nullptr,
              nullptr,
              nullptr.cast<NativeFunction<OperationCallbackNative>>(),
              nullptr,
              handle.cast<Pointer<CodexNativeOperation>>(),
            ),
          'codex_agent_host_start' => api.hostStart(
              nullptr,
              nullptr,
              nullptr.cast<NativeFunction<OperationCallbackNative>>(),
              nullptr,
              handle.cast<Pointer<CodexNativeOperation>>(),
            ),
          'codex_agent_host_state_get' => api.hostStateGet(
              nullptr,
              nullptr,
              handle.cast<Pointer<CodexNativeSnapshot>>(),
            ),
          'codex_agent_host_state_subscribe' => api.hostStateSubscribe(
              nullptr,
              nullptr,
              nullptr.cast<NativeFunction<StateCallbackNative>>(),
              nullptr,
              handle.cast<Pointer<CodexNativeSubscription>>(),
            ),
          'codex_agent_host_state_kind' =>
            api.hostStateKind(nullptr, nullptr, scalar),
          'codex_agent_host_state_agent' => api.hostStateAgent(
              nullptr,
              nullptr,
              nullptr,
              handle.cast<Pointer<CodexNativeAgent>>(),
            ),
          'codex_agent_operation_result' =>
            api.operationResult(nullptr, nullptr, scalar),
          _ => throw StateError('unknown Host null-boundary symbol: $symbol'),
        };
        if (status == CodexStatus.ok.value || handle.value != nullptr) {
          throw StateError('Host boundary did not fail closed: $symbol');
        }
        rows.add('${claim.executedTests.single}\t$symbol\tpassed');
      }
    }
  } finally {
    nativeMemory.free(handle);
    nativeMemory.free(scalar);
  }
  final receipt = File('build/parity/host-native-tests.tsv');
  receipt.parent.createSync(recursive: true);
  receipt.writeAsStringSync('${rows.join('\n')}\n');
}

Future<String> _buildFixture() async {
  final source = File('test/native/fake_codex_agent.c').absolute.path;
  final output = nativeFixturePath(
    'codex_agent_dart_host_$pid'
    '${Platform.isMacOS ? '.dylib' : Platform.isWindows ? '.dll' : '.so'}',
  );
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
    throw StateError('Host fixture compilation failed: ${result.stderr}');
  }
  return output;
}

typedef _VoidNative = Void Function();
typedef _VoidDart = void Function();
typedef _ModeNative = Void Function(Int32);
typedef _ModeDart = void Function(int);
typedef _CounterNative = Int32 Function();
typedef _CounterDart = int Function();
typedef _CallCountNative = Int32 Function(Pointer<Uint8>);
typedef _CallCountDart = int Function(Pointer<Uint8>);

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

Future<CodexHost> _open(String path) => CodexHost.create(
      bundleDirectory: '/host-parity-bundle',
      dataDirectory: '/host-parity-data',
      clientInfo: CodexClientInfo(
        name: 'host-parity',
        title: 'Host parity',
        version: '1.0',
      ),
      libraryPath: path,
    );

Future<void> _expectOperationSemantics(
  CodexHost host,
  _VoidDart failNext,
  Future<void> Function(CodexCancellation? cancellation) action,
) async {
  failNext();
  await expectLater(
    action(null),
    throwsA(
      isA<CodexOperationException>()
          .having((error) => error.operationStatus, 'status',
              CodexStatus.operationFailed)
          .having((error) => error.failure?.code, 'failure.code', 'fake')
          .having((error) => error.failure?.message, 'failure.message',
              'fake failure')
          .having((error) => error.failure?.isRecoverable,
              'failure.isRecoverable', isTrue),
    ),
  );
  final cancellation = CodexCancellation();
  final cancelled = action(cancellation);
  cancellation.cancel();
  await expectLater(
    cancelled,
    throwsA(isA<CodexOperationException>().having(
      (error) => error.operationStatus,
      'status',
      CodexStatus.cancelled,
    )),
  );
  await action(null);
}

Future<void> _exercise(
  String member,
  String path,
  DynamicLibrary library,
) async {
  final mode = library.lookupFunction<_ModeNative, _ModeDart>(
      'codex_agent_dart_test_host_parity_mode');
  final failNext = library.lookupFunction<_VoidNative, _VoidDart>(
      'codex_agent_dart_test_fail_next_operation');
  if (member == 'CodexHost.<init>') {
    mode(1);
    try {
      final host = await _open(path);
      await host.close();
      for (final wrong in <List<String>>[
        <String>[
          'wrong',
          '/host-parity-data',
          'host-parity',
          'Host parity',
          '1.0'
        ],
        <String>[
          '/host-parity-bundle',
          'wrong',
          'host-parity',
          'Host parity',
          '1.0'
        ],
        <String>[
          '/host-parity-bundle',
          '/host-parity-data',
          'wrong',
          'Host parity',
          '1.0'
        ],
        <String>[
          '/host-parity-bundle',
          '/host-parity-data',
          'host-parity',
          'wrong',
          '1.0'
        ],
        <String>[
          '/host-parity-bundle',
          '/host-parity-data',
          'host-parity',
          'Host parity',
          'wrong'
        ],
      ]) {
        await expectLater(
          CodexHost.create(
            bundleDirectory: wrong[0],
            dataDirectory: wrong[1],
            clientInfo: CodexClientInfo(
              name: wrong[2],
              title: wrong[3],
              version: wrong[4],
            ),
            libraryPath: path,
          ),
          throwsA(isA<CodexNativeException>()),
        );
      }
    } finally {
      mode(0);
    }
    return;
  }

  final host = await _open(path);
  if (member == 'CodexHost.start') {
    await _expectOperationSemantics(
      host,
      failNext,
      (cancellation) => host.start(cancellation: cancellation),
    );
    await host.close();
    return;
  }
  if (member == 'CodexHost.selectWorkspace') {
    mode(1);
    try {
      await expectLater(
        host.selectWorkspace('/wrong'),
        throwsA(isA<CodexNativeException>()),
      );
      await _expectOperationSemantics(
        host,
        failNext,
        (cancellation) => host.selectWorkspace(
          '/selected-workspace',
          cancellation: cancellation,
        ),
      );
    } finally {
      mode(0);
    }
    await host.close();
    return;
  }
  if (member == 'CodexHost.close') {
    await _expectOperationSemantics(
      host,
      failNext,
      (cancellation) => host.close(cancellation: cancellation),
    );
    await host.close();
    await host.close();
    expect(() => host.state, returnsNormally);
    await expectLater(
      Future<CodexHostState>.sync(() => host.currentState),
      throwsA(isA<CodexClosedException>()),
    );
    return;
  }

  final first = await host.currentState;
  final second = await host.currentState;
  expect(first, isA<CodexReadyHostState>());
  expect(second, isA<CodexReadyHostState>());
  final firstReady = first as CodexReadyHostState;
  final secondReady = second as CodexReadyHostState;
  expect(secondReady.agent, same(firstReady.agent));
  expect(firstReady.agent, same(firstReady.agent));
  expect(first.workspace?.path, '/workspace');
  expect(first.workspace?.displayName, '/workspace');
  if (member == 'CodexHostState.Ready.<init>' ||
      member == 'CodexHostState.Ready.agent') {
    final projected = CodexReadyHostState(firstReady.agent);
    expect(projected.kind, CodexHostStateKind.ready);
    expect(projected.agent, same(firstReady.agent));
  } else if (member == 'CodexHost.lifecycleState') {
    final states = await host.states.toList();
    expect(states, hasLength(2));
    expect(states.first, isA<CodexReadyHostState>());
    expect(states.first.agent, same(firstReady.agent));
    expect(states.last.kind, CodexHostStateKind.closed);

    final setTerminal = library.lookupFunction<_ModeNative, _ModeDart>(
        'codex_agent_test_emit_terminal_state');
    setTerminal(0);
    var events = 0;
    final subscription = host.states.listen((_) => events++);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    await subscription.cancel();
    await subscription.cancel();
    final afterCancel = events;
    await Future<void>.delayed(const Duration(milliseconds: 10));
    expect(events, afterCancel);
    setTerminal(1);
  }
  final releases = library.lookupFunction<_CounterNative, _CounterDart>(
      'codex_agent_dart_test_agent_release_calls');
  final releaseBefore = releases();
  final copiedWorkspace = first.workspace!;
  final child = firstReady.agent.authentication;
  await host.close();
  expect(releases(), greaterThanOrEqualTo(releaseBefore + 1));
  await expectLater(
    Future<Object?>.sync(() => child.state.current),
    throwsA(isA<CodexClosedException>()),
  );
  expect(copiedWorkspace.path, '/workspace');
  expect(copiedWorkspace.displayName, '/workspace');
  await child.close();
  final readyAgent = firstReady.agent;
  await readyAgent.close();
  expect(firstReady.agent, same(readyAgent));
}

void registerHostParity(
  List<DartHostClaim> claims,
  Directory root,
  Map<String, Set<String>> passedCompilerEvidence,
  Set<String> passedTestIds,
) {
  late final Future<String> fixture = _buildFixture();
  test('dart.host.inventory', () {
    expect(() => verifyHostClaims(claims, root), returnsNormally);
  });
  test('dart.host inventory and production edges fail closed', () {
    expect(() => verifyHostClaims(claims.sublist(1), root), throwsStateError);
    final client = File('${root.path}/codex-agent-bindings/dart/'
            'lib/src/client.dart')
        .readAsStringSync();
    final ffi = File('${root.path}/codex-agent-bindings/dart/'
            'lib/src/ffi.dart')
        .readAsStringSync();
    for (final symbol in claims.expand(_headers).where(
          (value) => value.startsWith('codex_agent_') && !value.endsWith('_t'),
        )) {
      expect(
        () => verifyHostClaims(
          claims,
          root,
          ffiSourceOverride: ffi.replaceAll("'$symbol'", "'codex_agent_stale'"),
        ),
        throwsStateError,
        reason: 'missing Host production lookup was accepted: $symbol',
      );
    }
    expect(
      () => verifyHostClaims(
        claims,
        root,
        clientSourceOverride: client.replaceFirst(
            '_owner.api.hostStart(', '_owner.api.hostClose('),
      ),
      throwsStateError,
    );
  });

  final sorted = claims.toList()
    ..sort((left, right) => left.capabilityKey.compareTo(right.capabilityKey));
  for (final claim in sorted) {
    test(claim.executedTests.single, () async {
      final path = await fixture;
      final library = authenticatedRuntimeLibraryForTesting(path);
      final count = library.lookupFunction<_CallCountNative, _CallCountDart>(
          'codex_agent_dart_leaf_call_count');
      final functions = _headers(claim)
          .where((value) => value.startsWith('codex_agent_'))
          .where((value) => !value.endsWith('_t'))
          .toSet();
      final before = <String, int>{
        for (final function in functions) function: _callCount(count, function),
      };
      await _exercise(_member(claim.capabilityKey), path, library);
      for (final function in functions) {
        expect(
          _callCount(count, function),
          greaterThan(before[function]!),
          reason: '${claim.executedTests.single} did not call $function',
        );
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
