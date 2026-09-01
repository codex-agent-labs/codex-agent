import 'dart:async';
import 'dart:ffi';
import 'dart:io';

import 'package:codex_agent/codex_agent.dart';
import 'package:codex_agent/src/ffi.dart'
    show authenticatedRuntimeLibraryForTesting;
import 'package:test/test.dart';

import 'native_fixture.dart';

typedef _SetTerminalNative = Void Function(Int32);
typedef _SetTerminalDart = void Function(int);
typedef _FailOnceNative = Void Function();
typedef _FailOnceDart = void Function();

Future<String> _buildFixture() async {
  final source = File('test/native/fake_codex_agent.c').absolute.path;
  final output = File(nativeFixturePath(
    'codex_agent_dart_test_$pid'
    '${Platform.isWindows ? '.dll' : Platform.isMacOS ? '.dylib' : '.so'}',
  )).path;
  final result = Platform.isWindows
      ? await Process.run('cl', <String>[
          '/nologo',
          '/LD',
          ...runtimeIdentityCompilerDefinitions(),
          source,
          '/link',
          '/OUT:$output',
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
    throw StateError(
        'fixture compilation failed: ${result.stdout}\n${result.stderr}');
  }
  return output;
}

void main() {
  late String libraryPath;

  setUpAll(() async {
    libraryPath = await _buildFixture();
  });

  tearDownAll(() {
    final fixture = File(libraryPath);
    if (fixture.existsSync()) fixture.deleteSync();
  });

  test('Host Agent Conversation lifecycle, values, state and ownership',
      () async {
    final host = await CodexHost.create(
      bundleDirectory: '/fixture/bundle',
      dataDirectory: '/fixture/data',
      clientInfo: CodexClientInfo(
        name: 'dart-tests',
        title: 'Dart tests',
        version: '1.0.0',
      ),
      libraryPath: libraryPath,
    );
    await host.start();

    final currentHost = await host.currentState;
    expect(currentHost.kind, CodexHostStateKind.ready);
    expect(currentHost.workspace?.path, '/workspace');
    expect(currentHost.workspace?.displayName, '/workspace');
    final streamedHost = await host.states.first;
    expect(streamedHost.kind, CodexHostStateKind.ready);

    final agent = currentHost.agent!;
    final conversations = agent.conversations;
    final summaries = await conversations.list();
    expect(summaries.map((value) => value.conversationId.value),
        <String>['conversation-1', 'conversation-2']);
    expect(
        summaries.map((value) => value.title), <String>['Fixture', 'Fixture']);
    expect(summaries.map((value) => value.updatedAtEpochSeconds),
        <int>[1700000000, 1700000001]);

    final conversation = await conversations.open(
      options: const CodexConversationOpenOptions(
        approvalPreset: CodexApprovalPreset.autoReview,
        serviceTier: 'default',
      ),
    );
    expect(await conversation.isSame(conversation), isTrue);
    expect((await conversation.currentState).status,
        CodexConversationStatus.ready);
    expect(await conversation.states.first.then((state) => state.status),
        CodexConversationStatus.ready);
    expect(await conversation.canStartTurn, isTrue);
    expect(await conversation.canStartTurnChanges.first, isTrue);
    final broadcastStates = conversation.states;
    final listeners = await Future.wait(<Future<List<CodexConversationState>>>[
      broadcastStates.toList(),
      broadcastStates.toList(),
    ]);
    expect(listeners[0].map((state) => state.status), <CodexConversationStatus>[
      CodexConversationStatus.runningTurn,
      CodexConversationStatus.closed,
    ]);
    expect(listeners[1].map((state) => state.status), <CodexConversationStatus>[
      CodexConversationStatus.runningTurn,
      CodexConversationStatus.closed,
    ]);
    await conversation.send('hello');
    await expectLater(
      conversation.send('fail'),
      throwsA(
        isA<CodexOperationException>()
            .having(
              (error) => error.operationStatus,
              'operationStatus',
              CodexStatus.operationFailed,
            )
            .having((error) => error.failure?.code, 'failure.code', 'fake')
            .having(
              (error) => error.failure?.isRecoverable,
              'failure.isRecoverable',
              isTrue,
            ),
      ),
    );
    await conversation.runShellCommand('pwd');
    await conversation.reload();
    await conversation.cancelTurn();
    await conversation.closeConversation();

    await conversation.dispose();
    await conversation.dispose();
    await conversations.close();
    await agent.close();
    await streamedHost.agent!.close();
    await host.close();
    await host.close();
    expect(() => agent.conversations, throwsA(isA<CodexClosedException>()));
  });

  test('pre-cancelled operation projects structured cancellation', () async {
    final host = await CodexHost.create(
      bundleDirectory: '.',
      dataDirectory: '.',
      clientInfo: CodexClientInfo(name: 'test', title: 'Test', version: '1'),
      libraryPath: libraryPath,
    );
    final cancellation = CodexCancellation()..cancel();
    await expectLater(
      host.start(cancellation: cancellation),
      throwsA(
        isA<CodexOperationException>().having(
          (error) => error.operationStatus,
          'operationStatus',
          CodexStatus.cancelled,
        ),
      ),
    );
    await host.close();
  });

  test('parent close waits for pinned in-flight operation and is idempotent',
      () async {
    final host = await CodexHost.create(
      bundleDirectory: '.',
      dataDirectory: '.',
      clientInfo: CodexClientInfo(name: 'test', title: 'Test', version: '1'),
      libraryPath: libraryPath,
    );
    final start = host.start();
    final firstClose = host.close();
    final secondClose = host.close();
    await Future.wait(<Future<void>>[start, firstClose, secondClose]);
    await expectLater(host.start(), throwsA(isA<CodexClosedException>()));
  });

  test('host close waits for an in-flight descendant operation', () async {
    final host = await CodexHost.create(
      bundleDirectory: '.',
      dataDirectory: '.',
      clientInfo: CodexClientInfo(name: 'test', title: 'Test', version: '1'),
      libraryPath: libraryPath,
    );
    final agent = (await host.currentState).agent!;
    final conversations = agent.conversations;
    final conversation = await conversations.open();
    final send = conversation.send('hello');
    await Future.wait(<Future<void>>[send, host.close()]);
    await expectLater(
      conversation.send('after close'),
      throwsA(isA<CodexClosedException>()),
    );
    await conversation.dispose();
    await conversations.close();
    await agent.close();
  });

  test('cancel and close race reaches callback quiescence once', () async {
    final host = await CodexHost.create(
      bundleDirectory: '.',
      dataDirectory: '.',
      clientInfo: CodexClientInfo(name: 'test', title: 'Test', version: '1'),
      libraryPath: libraryPath,
    );
    final cancellation = CodexCancellation();
    final start = host.start(cancellation: cancellation);
    cancellation.cancel();
    await expectLater(start, throwsA(isA<CodexOperationException>()));
    await Future.wait(<Future<void>>[host.close(), host.close()]);
  });

  test('parent close terminates an active nonterminal broadcast stream',
      () async {
    final library = authenticatedRuntimeLibraryForTesting(libraryPath);
    final setTerminal =
        library.lookupFunction<_SetTerminalNative, _SetTerminalDart>(
            'codex_agent_test_emit_terminal_state');
    setTerminal(0);
    final host = await CodexHost.create(
      bundleDirectory: '.',
      dataDirectory: '.',
      clientInfo: CodexClientInfo(name: 'test', title: 'Test', version: '1'),
      libraryPath: libraryPath,
    );
    final first = Completer<CodexHostState>();
    final done = Completer<void>();
    final subscription = host.states.listen(
      (state) {
        if (!first.isCompleted) first.complete(state);
      },
      onDone: done.complete,
    );
    expect((await first.future).kind, CodexHostStateKind.ready);
    await Future.wait(<Future<void>>[host.close(), host.close()]);
    await done.future;
    await subscription.cancel();
    setTerminal(1);
  });

  test('immediate stream cancellation quiesces before callback delivery',
      () async {
    final library = authenticatedRuntimeLibraryForTesting(libraryPath);
    final setTerminal =
        library.lookupFunction<_SetTerminalNative, _SetTerminalDart>(
            'codex_agent_test_emit_terminal_state');
    setTerminal(0);
    final host = await CodexHost.create(
      bundleDirectory: '.',
      dataDirectory: '.',
      clientInfo: CodexClientInfo(name: 'test', title: 'Test', version: '1'),
      libraryPath: libraryPath,
    );
    var events = 0;
    final subscription = host.states.listen((_) => events++);
    await subscription.cancel();
    await Future<void>.delayed(const Duration(milliseconds: 20));
    expect(events, 0);
    await host.close();
    setTerminal(1);
  });

  test('immediate parent close suppresses queued stream delivery', () async {
    final library = authenticatedRuntimeLibraryForTesting(libraryPath);
    final setTerminal =
        library.lookupFunction<_SetTerminalNative, _SetTerminalDart>(
            'codex_agent_test_emit_terminal_state');
    setTerminal(0);
    final host = await CodexHost.create(
      bundleDirectory: '.',
      dataDirectory: '.',
      clientInfo: CodexClientInfo(name: 'test', title: 'Test', version: '1'),
      libraryPath: libraryPath,
    );
    var events = 0;
    final done = Completer<void>();
    final subscription = host.states.listen(
      (_) => events++,
      onDone: done.complete,
    );
    await Future.wait(<Future<void>>[host.close(), host.close()]);
    await done.future;
    final afterClose = events;
    await Future<void>.delayed(const Duration(milliseconds: 20));
    expect(events, afterClose);
    await subscription.cancel();
    setTerminal(1);
  });

  test('unexpected operation destroy error is surfaced and retained for retry',
      () async {
    final library = authenticatedRuntimeLibraryForTesting(libraryPath);
    library.lookupFunction<_FailOnceNative, _FailOnceDart>(
      'codex_agent_test_fail_operation_destroy_once',
    )();
    final host = await CodexHost.create(
      bundleDirectory: '.',
      dataDirectory: '.',
      clientInfo: CodexClientInfo(name: 'test', title: 'Test', version: '1'),
      libraryPath: libraryPath,
    );
    await expectLater(
      host.start(),
      throwsA(
        isA<CodexNativeException>().having(
          (error) => error.status,
          'status',
          CodexStatus.internalError,
        ),
      ),
    );
    await host.close();
  });

  test('unexpected host release preserves ownership for explicit retry',
      () async {
    final library = authenticatedRuntimeLibraryForTesting(libraryPath);
    library.lookupFunction<_FailOnceNative, _FailOnceDart>(
      'codex_agent_test_fail_host_release_once',
    )();
    final host = await CodexHost.create(
      bundleDirectory: '.',
      dataDirectory: '.',
      clientInfo: CodexClientInfo(name: 'test', title: 'Test', version: '1'),
      libraryPath: libraryPath,
    );
    await expectLater(host.close(), throwsA(isA<CodexNativeException>()));
    await host.close();
  });

  test(
      'host finalizer performs semantic close before release and context destroy',
      () async {
    final result = await Process.run(
      Platform.resolvedExecutable,
      <String>[
        '--enable-vm-service=0',
        '--disable-service-auth-codes',
        'run',
        'tool/finalizer_probe.dart',
        libraryPath,
      ],
    ).timeout(const Duration(seconds: 30));
    expect(
      result.exitCode,
      0,
      reason: 'finalizer probe failed:\n${result.stdout}\n${result.stderr}',
    );
  });

  test('reachable descendant pins the host finalizer coordinator', () async {
    final result = await Process.run(
      Platform.resolvedExecutable,
      <String>[
        '--enable-vm-service=0',
        '--disable-service-auth-codes',
        'run',
        'tool/finalizer_probe.dart',
        libraryPath,
        'child',
      ],
    ).timeout(const Duration(seconds: 30));
    expect(
      result.exitCode,
      0,
      reason:
          'child retention probe failed:\n${result.stdout}\n${result.stderr}',
    );
  });
}
