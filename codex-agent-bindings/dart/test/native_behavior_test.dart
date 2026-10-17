import 'dart:async';
import 'dart:collection';
import 'dart:convert';
import 'dart:ffi';
import 'dart:io';
import 'dart:isolate';

import 'package:crypto/crypto.dart' as crypto;
import 'package:codex_agent/codex_agent.dart';
import 'package:codex_agent/src/ffi.dart'
    show
        NativeApi,
        authenticatedRuntimeLibraryForTesting,
        currentClassifier,
        libraryNameFor,
        readRuntimeIdentity;
import 'package:codex_agent/src/runtime_compatibility.dart'
    show runtimeFileSha256;
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
  if (Platform.environment['CODEX_AGENT_TEST_ISOLATED'] != '1') {
    test('native behavior with signed fixture evidence', () async {
      final temporary = Directory(
        Directory.systemTemp.resolveSymbolicLinksSync(),
      ).createTempSync('codex-agent-native-behavior-');
      try {
        final rootKey = _testKey(temporary, 'root');
        final config = _isolatedPackage(temporary, rootKey.public);
        final result = await Process.run(
            Platform.resolvedExecutable,
            [
              '--packages=${config.path}',
              'run',
              'test:test',
              'test/native_behavior_test.dart',
              '-r',
              'expanded',
            ],
            environment: {
              ...Platform.environment,
              'CODEX_AGENT_TEST_ISOLATED': '1',
              'CODEX_AGENT_TEST_ROOT_PRIVATE': rootKey.privateKey,
              'CODEX_AGENT_TEST_ROOT_PUBLIC': '${rootKey.privateKey}.pub',
              'CODEX_AGENT_TEST_PACKAGE_CONFIG': config.path,
            }..remove('CODEX_AGENT_LIBRARY'));
        expect(result.exitCode, 0,
            reason: '${result.stdout}\n${result.stderr}');
      } finally {
        temporary.deleteSync(recursive: true);
      }
    },
        skip: Platform.isWindows
            ? 'Windows external SSHSIG verification is unavailable'
            : false);
    return;
  }
  late String libraryPath;

  setUpAll(() async {
    libraryPath = await _buildFixture();
    _signFixture(libraryPath);
  });

  tearDownAll(() {
    final fixture = File(libraryPath);
    if (fixture.existsSync()) fixture.deleteSync();
    final evidence = Directory('$libraryPath.evidence');
    if (evidence.existsSync()) evidence.deleteSync(recursive: true);
  });

  test('cached runtime still requires intact signed evidence', () {
    final loaded = authenticatedRuntimeLibraryForTesting(libraryPath);
    final signature =
        File('$libraryPath.evidence/runtime-library-authorization.sig');
    final original = signature.readAsBytesSync();
    try {
      signature.writeAsBytesSync([...original, 120]);
      expect(
        () => authenticatedRuntimeLibraryForTesting(libraryPath),
        throwsA(isA<CodexException>()),
      );
    } finally {
      signature.writeAsBytesSync(original);
    }
    expect(authenticatedRuntimeLibraryForTesting(libraryPath), same(loaded));
  });

  test(
      'cached embedded runtime rechecks the installed compatibility declaration',
      () {
    final uri = Isolate.resolvePackageUriSync(
      Uri.parse('package:codex_agent/src/native/sdk-compatibility.json'),
    )!;
    final declaration = File.fromUri(uri);
    final original = declaration.readAsBytesSync();
    final target = currentClassifier();
    final packaged = File(
      '${declaration.parent.path}/$target/${libraryNameFor(target)}',
    );
    packaged.parent.createSync(recursive: true);
    File(libraryPath).copySync(packaged.path);
    try {
      final value = jsonDecode(utf8.decode(original)) as Map<String, Object?>;
      final runtime = value['runtime']! as Map<String, Object?>;
      final variant = (runtime['embeddedVariants']! as List<Object?>)
          .cast<Map<String, Object?>>()
          .singleWhere((item) => item['target'] == target);
      final identity =
          jsonDecode(readRuntimeIdentity(DynamicLibrary.open(libraryPath)))
              as Map<String, Object?>;
      variant['runtimeLibrarySha256'] = runtimeFileSha256(packaged);
      variant['componentId'] = identity['componentId'];
      declaration.writeAsStringSync(_canonical(value));
      NativeApi.loadResolved();

      const differentContract =
          'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
      (value['contract']! as Map<String, Object?>)['digest'] =
          differentContract;
      runtime['requiredContractDigest'] = differentContract;
      declaration.writeAsStringSync(_canonical(value));
      expect(() => NativeApi.loadResolved(), throwsA(isA<CodexException>()));
    } finally {
      declaration.writeAsBytesSync(original);
      packaged.deleteSync();
    }
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
        '--packages=${Platform.environment['CODEX_AGENT_TEST_PACKAGE_CONFIG']}',
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
        '--packages=${Platform.environment['CODEX_AGENT_TEST_PACKAGE_CONFIG']}',
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

({String privateKey, List<int> public}) _testKey(
    Directory directory, String name) {
  final path = '${directory.path}/$name';
  final result = Process.runSync('ssh-keygen', [
    '-q',
    '-t',
    'ed25519',
    '-N',
    '',
    '-f',
    path,
  ]);
  if (result.exitCode != 0) {
    throw StateError('test key generation failed: ${result.stderr}');
  }
  final parts = File('$path.pub').readAsStringSync().split(' ');
  return (privateKey: path, public: ascii.encode('${parts[0]} ${parts[1]}\n'));
}

String _digest(List<int> bytes) => 'sha256:${crypto.sha256.convert(bytes)}';

String _fingerprint(List<int> key) =>
    _digest(base64.decode(ascii.decode(key).split(' ')[1].trim()));

Object? _sorted(Object? value) => switch (value) {
      Map<String, Object?> fields => SplayTreeMap<String, Object?>.of(
          Map.fromEntries(fields.entries
              .map((entry) => MapEntry(entry.key, _sorted(entry.value))))),
      List<Object?> items => items.map(_sorted).toList(),
      _ => value,
    };

String _canonical(Object? value) => '${jsonEncode(_sorted(value))}\n';

void _sign(File manifest, String privateKey, String namespace) {
  final result = Process.runSync('ssh-keygen', [
    '-Y',
    'sign',
    '-f',
    privateKey,
    '-n',
    namespace,
    manifest.path,
  ]);
  if (result.exitCode != 0) {
    throw StateError('test signing failed: ${result.stderr}');
  }
  File('${manifest.path}.sig').renameSync(
      '${manifest.parent.path}/${manifest.uri.pathSegments.last.replaceAll('.json', '.sig')}');
}

File _isolatedPackage(Directory temporary, List<int> rootKey) {
  final package = Directory('${temporary.path}/isolated-package')..createSync();
  Directory('${package.path}/lib').createSync();
  final original = Directory('lib');
  for (final entity in original.listSync(recursive: true)) {
    final relative = entity.path.substring(original.path.length + 1);
    final destination = '${package.path}/lib/$relative';
    if (entity is Directory) {
      Directory(destination).createSync(recursive: true);
    } else if (entity is File) {
      File(entity.path).copySync(destination);
    }
  }
  File('${package.path}/lib/src/native/sdk-runtime-root.pub')
      .writeAsBytesSync(rootKey);
  final configuration =
      jsonDecode(File('.dart_tool/package_config.json').readAsStringSync())
          as Map<String, Object?>;
  final packages = configuration['packages']! as List<Object?>;
  final codexAgent = packages
      .cast<Map<String, Object?>>()
      .singleWhere((entry) => entry['name'] == 'codex_agent');
  codexAgent['rootUri'] = package.uri.toString();
  return File('${temporary.path}/package_config.json')
    ..writeAsStringSync(jsonEncode(configuration));
}

void _signFixture(String libraryPath) {
  final rootPrivate = Platform.environment['CODEX_AGENT_TEST_ROOT_PRIVATE']!;
  final rootPublicPath = Platform.environment['CODEX_AGENT_TEST_ROOT_PUBLIC']!;
  final rootParts = File(rootPublicPath).readAsStringSync().split(' ');
  final rootPublic = ascii.encode('${rootParts[0]} ${rootParts[1]}\n');
  final signer = _testKey(File(rootPrivate).parent, 'release');
  final library = File(libraryPath);
  final identity =
      jsonDecode(readRuntimeIdentity(DynamicLibrary.open(libraryPath)))
          as Map<String, Object?>;
  final evidence = Directory('$libraryPath.evidence')..createSync();
  final keys = Directory('${evidence.path}/keys')..createSync();
  File('${keys.path}/release.pub').writeAsBytesSync(signer.public);
  final keyring = File('${evidence.path}/release-keyring.json')
    ..writeAsStringSync(_canonical({
      'schemaVersion': 1,
      'namespace': 'codex-agent-product-v1',
      'algorithm': 'ssh-ed25519',
      'trustDomain': 'release',
      'activeKey': {
        'keyId': 'release',
        'fingerprint': _fingerprint(signer.public),
      },
      'retiredKeys': <Object>[],
    }));
  final delegation = File('${evidence.path}/root-delegation.json')
    ..writeAsStringSync(_canonical({
      'schemaVersion': 1,
      'kind': 'sdk-runtime-release-keyring-delegation',
      'scope': 'desktop-runtime-library',
      'rootFingerprint': _fingerprint(rootPublic),
      'keyringSha256': _digest(keyring.readAsBytesSync()),
    }));
  _sign(delegation, rootPrivate, 'codex-agent-sdk-runtime-root-v1');
  final claim = File('${evidence.path}/runtime-library-authorization.json')
    ..writeAsStringSync(_canonical({
      'schemaVersion': 1,
      'kind': 'desktop-runtime-library-authorization',
      'runtimeVersion': '0.8.0',
      'runtimeIdentity': identity,
      'runtimeLibrarySha256': runtimeFileSha256(library),
      'variantBundleSha256': _digest(List<int>.filled(1, 1)),
      'variantManifestSha256': _digest(List<int>.filled(1, 2)),
      'aggregateManifestSha256': _digest(List<int>.filled(1, 3)),
      'variantAttestationSha256': _digest(List<int>.filled(1, 4)),
      'aggregateAttestationSha256': _digest(List<int>.filled(1, 5)),
      'signing': {
        'algorithm': 'ssh-ed25519',
        'namespace': 'codex-agent-product-v1',
        'trustDomain': 'release',
        'keyId': 'release',
        'fingerprint': _fingerprint(signer.public),
      },
    }));
  _sign(claim, signer.privateKey, 'codex-agent-product-v1');
}
