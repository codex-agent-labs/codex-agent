import 'dart:async';
import 'dart:convert';
import 'dart:ffi';
import 'dart:io';

import 'package:codex_agent/codex_agent.dart';
import 'package:codex_agent/src/conversation_native.dart'
    show CodexNativeTurnRequest, ConversationNativeApi;
import 'package:codex_agent/src/ffi.dart'
    show
        CodexConversationOpenOptionsStruct,
        CodexNativeContext,
        CodexNativeConversation,
        CodexNativeConversationSummary,
        CodexNativeConversations,
        CodexNativeOperation,
        CodexNativeSnapshot,
        CodexNativeSubscription,
        CodexStringView,
        NativeApi,
        OperationCallbackNative,
        StateCallbackNative,
        nativeMemory,
        newHandleSlot;
import 'package:test/test.dart';

final class DartConversationClaim {
  const DartConversationClaim({
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

const _owners = <String>{'CodexConversations', 'CodexConversation'};

String _owner(String capability) =>
    capability.split('|owner=')[1].split('|').first.split('/').last;

String _member(String capability) => capability
    .split('|abi=io.github.codex_agent_labs.codexagent.agent/')[1]
    .split('|')
    .first
    .split('.')
    .last;

String _publicSymbol(String capability) {
  final owner = _owner(capability);
  final member = _member(capability);
  return switch ('$owner.$member') {
    'CodexConversations.active' => 'CodexConversations.activeState',
    'CodexConversation.close' => 'CodexConversation.closeConversation',
    'CodexConversation.send' when capability.contains('AgentTurnRequest') =>
      'CodexConversation.sendRequest',
    'CodexConversation.activeTurnProgress' =>
      'CodexConversation.activeTurnProgressState',
    'CodexConversation.canCancelTurn' => 'CodexConversation.canCancelTurnState',
    'CodexConversation.canReload' => 'CodexConversation.canReloadState',
    'CodexConversation.canRunShellCommand' =>
      'CodexConversation.canRunShellCommandState',
    'CodexConversation.canStartTurn' => 'CodexConversation.canStartTurnState',
    'CodexConversation.currentMessages' => 'CodexConversation.messagesState',
    'CodexConversation.isTurnActive' => 'CodexConversation.isTurnActiveState',
    _ => '$owner.$member',
  };
}

List<String> _headerCalls(DartConversationClaim claim) =>
    claim.compilerEvidenceIds
        .where((value) => value.startsWith('c-header:'))
        .map((value) => value.substring('c-header:'.length))
        .toList();

Set<String> verifyConversationClaims(
  List<DartConversationClaim> claims,
  Directory root, {
  String? sourceOverride,
}) {
  final report = jsonDecode(File('${root.path}/codex-agent-core/build/reports/'
          'cross-language-api/canonical-api.json')
      .readAsStringSync()) as Map<String, dynamic>;
  final canonical = <String>{
    for (final owner in report['owners'] as List<dynamic>)
      if (_owners.contains(
          ((owner as Map<String, dynamic>)['name'] as String).split('/').last))
        for (final capability in owner['capabilities'] as List<dynamic>)
          if ((capability as String).contains('|kind=function|') ||
              capability.contains('|kind=property|'))
            capability,
  };
  if (claims.length != 20 ||
      canonical.length != 20 ||
      claims.map((claim) => claim.capabilityKey).toSet().length != 20 ||
      !canonical.containsAll(claims.map((claim) => claim.capabilityKey)) ||
      !claims
          .map((claim) => claim.capabilityKey)
          .toSet()
          .containsAll(canonical)) {
    throw StateError('Dart conversation claims are incomplete or stale');
  }

  final bootstrap = jsonDecode(File('${root.path}/codex-agent-runtime-desktop/'
          'build/reports/cross-language-api/c-abi/bootstrap-evidence.json')
      .readAsStringSync()) as Map<String, dynamic>;
  final bootstrapClaims = <String, Map<String, dynamic>>{
    for (final claim in bootstrap['claims'] as List<dynamic>)
      (claim as Map<String, dynamic>)['capabilityKey'] as String: claim,
  };
  final passedFixtures = <String>{
    for (final item in bootstrap['nativeTests'] as List<dynamic>)
      if ((item as Map<String, dynamic>)['status'] == 'passed')
        item['testId'] as String,
  };
  final header = File('${root.path}/codex-agent-runtime-desktop/native/c-api/'
          'include/codex_agent.h')
      .readAsStringSync();
  final source = sourceOverride ??
      <String>[
        File('${root.path}/codex-agent-runtime-desktop/bindings/dart/lib/'
                'src/client.dart')
            .readAsStringSync(),
        File('${root.path}/codex-agent-runtime-desktop/bindings/dart/lib/'
                'src/ffi.dart')
            .readAsStringSync(),
        File('${root.path}/codex-agent-runtime-desktop/bindings/dart/lib/'
                'src/conversation_native.dart')
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
    final expectedEvidence = <String>{
      ...headers.map((value) => 'c-header:$value'),
      ...fixtures.map((value) => 'cabi-fixture:$value'),
      'dart-analyzer-conversation:${index.toString().padLeft(3, '0')}',
    };
    if (claim.publicSymbols.single != _publicSymbol(claim.capabilityKey) ||
        claim.executedTests.single !=
            'dart.conversation:${index.toString().padLeft(3, '0')}' ||
        claim.compilerEvidenceIds.toSet().length != expectedEvidence.length ||
        !claim.compilerEvidenceIds.toSet().containsAll(expectedEvidence)) {
      throw StateError(
          'inexact Dart conversation evidence: ${claim.capabilityKey}');
    }
    final publicMember = claim.publicSymbols.single.split('.').last;
    if (!RegExp('\\b${RegExp.escape(publicMember)}\\b').hasMatch(source)) {
      throw StateError(
          'missing public Dart member: ${claim.publicSymbols.single}');
    }
    for (final symbol in headers) {
      if (!RegExp('\\b${RegExp.escape(symbol)}\\s*\\(').hasMatch(header)) {
        throw StateError('stale C header reference: $symbol');
      }
      if (!compact.contains("('$symbol')")) {
        throw StateError('missing exact production lookup: $symbol');
      }
      references.add(symbol);
    }
    for (final fixture in fixtures) {
      if (!passedFixtures.contains(fixture)) {
        throw StateError('stale or failed C ABI fixture: $fixture');
      }
    }
  }
  return references;
}

Future<void> verifyRealConversationBoundary(
  List<DartConversationClaim> claims,
  Directory root,
) async {
  if (!Platform.isMacOS) return;
  final configured = Platform.environment['CODEX_AGENT_REAL_LIBRARY'];
  final repositorySdk = File('${root.path}/codex-agent-runtime-desktop/build/'
      'bin/macosArm64/releaseShared/libcodex_agent.dylib');
  final library = configured == null ? repositorySdk : File(configured);
  if (!library.existsSync()) {
    throw StateError(
        'real macOS Arm64 SDK is required; set CODEX_AGENT_REAL_LIBRARY');
  }
  final architecture = await Process.run('uname', const <String>['-m']);
  if (architecture.exitCode != 0 ||
      (architecture.stdout as String).trim() != 'arm64') {
    throw StateError('real Dart conversation receipt requires macOS Arm64');
  }

  final core = NativeApi.load(library.absolute.path);
  final api = ConversationNativeApi(core);
  final context = Pointer<CodexNativeContext>.fromAddress(0);
  final conversations = Pointer<CodexNativeConversations>.fromAddress(0);
  final conversation = Pointer<CodexNativeConversation>.fromAddress(0);
  final operation = Pointer<CodexNativeOperation>.fromAddress(0);
  final snapshot = Pointer<CodexNativeSnapshot>.fromAddress(0);
  final operationCallback =
      Pointer<NativeFunction<OperationCallbackNative>>.fromAddress(0);
  final stateCallback =
      Pointer<NativeFunction<StateCallbackNative>>.fromAddress(0);
  final operationOut = newHandleSlot<CodexNativeOperation>();
  final snapshotOut = newHandleSlot<CodexNativeSnapshot>();
  final subscriptionOut = newHandleSlot<CodexNativeSubscription>();
  final conversationOut = newHandleSlot<CodexNativeConversation>();
  final summaryOut = newHandleSlot<CodexNativeConversationSummary>();
  final voidOut = newHandleSlot<Void>();
  final intOut = nativeMemory.allocate<Int32>(sizeOf<Int32>());
  final sizeOut = nativeMemory.allocate<Size>(sizeOf<Size>());
  try {
    void reset() {
      operationOut.value = nullptr;
      snapshotOut.value = nullptr;
      subscriptionOut.value = nullptr;
      conversationOut.value = nullptr;
      summaryOut.value = nullptr;
      voidOut.value = nullptr;
      intOut.value = 0;
      sizeOut.value = 0;
    }

    final calls = <String, int Function()>{
      'codex_agent_active_conversation': () => core.activeConversation(
          context, conversations, snapshot, conversationOut),
      'codex_agent_conversation_active_turn_progress_get': () =>
          api.activeProgressGet(context, conversation, snapshotOut),
      'codex_agent_conversation_active_turn_progress_has_value': () =>
          api.activeProgressHasValue(context, nullptr, intOut),
      'codex_agent_conversation_active_turn_progress_subscribe': () =>
          api.activeProgressSubscribe(
              context, conversation, stateCallback, nullptr, subscriptionOut),
      'codex_agent_conversation_active_turn_progress_value': () =>
          api.activeProgressValue(context, nullptr, voidOut),
      'codex_agent_conversation_can_cancel_turn_get': () =>
          core.conversationCanCancelTurnGet(context, conversation, snapshotOut),
      'codex_agent_conversation_can_cancel_turn_subscribe': () =>
          core.conversationCanCancelTurnSubscribe(
              context, conversation, stateCallback, nullptr, subscriptionOut),
      'codex_agent_conversation_can_reload_get': () =>
          core.conversationCanReloadGet(context, conversation, snapshotOut),
      'codex_agent_conversation_can_reload_subscribe': () =>
          core.conversationCanReloadSubscribe(
              context, conversation, stateCallback, nullptr, subscriptionOut),
      'codex_agent_conversation_can_run_shell_command_get': () =>
          core.conversationCanRunShellGet(context, conversation, snapshotOut),
      'codex_agent_conversation_can_run_shell_command_subscribe': () =>
          core.conversationCanRunShellSubscribe(
              context, conversation, stateCallback, nullptr, subscriptionOut),
      'codex_agent_conversation_can_start_turn_get': () =>
          core.conversationCanStartTurnGet(context, conversation, snapshotOut),
      'codex_agent_conversation_can_start_turn_subscribe': () =>
          core.conversationCanStartTurnSubscribe(
              context, conversation, stateCallback, nullptr, subscriptionOut),
      'codex_agent_conversation_cancel_turn': () => core.conversationCancelTurn(
          context, conversation, operationCallback, nullptr, operationOut),
      'codex_agent_conversation_close': () => core.conversationClose(
          context, conversation, operationCallback, nullptr, operationOut),
      'codex_agent_conversation_current_messages_at': () =>
          api.currentMessagesAt(context, nullptr, 0, voidOut),
      'codex_agent_conversation_current_messages_count': () =>
          api.currentMessagesCount(context, nullptr, sizeOut),
      'codex_agent_conversation_current_messages_get': () =>
          api.currentMessagesGet(context, conversation, snapshotOut),
      'codex_agent_conversation_current_messages_subscribe': () =>
          api.currentMessagesSubscribe(
              context, conversation, stateCallback, nullptr, subscriptionOut),
      'codex_agent_conversation_is_turn_active_get': () =>
          core.conversationIsTurnActiveGet(context, conversation, snapshotOut),
      'codex_agent_conversation_is_turn_active_subscribe': () =>
          core.conversationIsTurnActiveSubscribe(
              context, conversation, stateCallback, nullptr, subscriptionOut),
      'codex_agent_conversation_reload': () => core.conversationReload(
          context, conversation, operationCallback, nullptr, operationOut),
      'codex_agent_conversation_run_shell_command': () =>
          core.conversationShell(
              context,
              conversation,
              Pointer<CodexStringView>.fromAddress(0),
              operationCallback,
              nullptr,
              operationOut),
      'codex_agent_conversation_send': () => core.conversationSend(
          context,
          conversation,
          Pointer<CodexStringView>.fromAddress(0),
          operationCallback,
          nullptr,
          operationOut),
      'codex_agent_conversation_send_request': () =>
          api.conversationSendRequest(
              context,
              conversation,
              Pointer<CodexNativeTurnRequest>.fromAddress(0),
              operationCallback,
              nullptr,
              operationOut),
      'codex_agent_conversation_state_get': () =>
          core.conversationStateGet(context, conversation, snapshotOut),
      'codex_agent_conversation_state_subscribe': () =>
          core.conversationStateSubscribe(
              context, conversation, stateCallback, nullptr, subscriptionOut),
      'codex_agent_conversations_active_get': () =>
          core.conversationsActiveGet(context, conversations, snapshotOut),
      'codex_agent_conversations_active_subscribe': () =>
          core.conversationsActiveSubscribe(
              context, conversations, stateCallback, nullptr, subscriptionOut),
      'codex_agent_conversations_delete': () => api.conversationsDelete(context,
          conversations, nullptr, operationCallback, nullptr, operationOut),
      'codex_agent_conversations_list': () => core.conversationsList(
          context, conversations, operationCallback, nullptr, operationOut),
      'codex_agent_conversations_open': () => core.conversationsOpen(
          context,
          conversations,
          Pointer<CodexConversationOpenOptionsStruct>.fromAddress(0),
          operationCallback,
          nullptr,
          operationOut),
      'codex_agent_conversations_read': () => api.conversationsRead(context,
          conversations, nullptr, operationCallback, nullptr, operationOut),
      'codex_agent_conversations_rename': () => api.conversationsRename(
          context,
          conversations,
          nullptr,
          Pointer<CodexStringView>.fromAddress(0),
          operationCallback,
          nullptr,
          operationOut),
      'codex_agent_operation_conversation_summaries_count': () =>
          core.operationSummariesCount(context, operation, sizeOut),
      'codex_agent_operation_conversation_summary_at': () =>
          core.operationSummaryAt(context, operation, 0, summaryOut),
      'codex_agent_operation_conversation_value': () =>
          api.operationConversationValue(context, nullptr, voidOut),
      'codex_agent_operation_result': () =>
          core.operationResult(context, operation, intOut),
      'codex_agent_state_boolean_value': () =>
          core.stateBooleanValue(context, snapshot, intOut),
    };
    final expected = claims.expand(_headerCalls).toSet();
    if (calls.length != 39 ||
        expected.length != 39 ||
        !calls.keys.toSet().containsAll(expected) ||
        !expected.containsAll(calls.keys)) {
      throw StateError('real Dart conversation boundary is incomplete');
    }
    final statuses = <String, int>{};
    for (final entry in calls.entries) {
      reset();
      final status = entry.value();
      if (status == 0) {
        throw StateError('${entry.key} accepted the typed null boundary');
      }
      statuses[entry.key] = status;
    }
    final output = Directory('${root.path}/codex-agent-runtime-desktop/'
        'bindings/dart/build/parity')
      ..createSync(recursive: true);
    final sorted = claims.toList()
      ..sort(
          (left, right) => left.capabilityKey.compareTo(right.capabilityKey));
    File('${output.path}/conversation-real-sdk-receipt.tsv').writeAsStringSync(
      'capabilityKey\tpublicSymbol\texactNativeCalls\tboundary\tstatus\n'
      '${sorted.map((claim) => <String>[
            claim.capabilityKey,
            claim.publicSymbols.single,
            (_headerCalls(claim)..sort())
                .map((symbol) => '$symbol:${statuses[symbol]}')
                .join(','),
            'real-macos-arm64-typed-null-handle',
            'passed',
          ].join('\t')).join('\n')}\n',
    );
  } finally {
    nativeMemory.free(sizeOut);
    nativeMemory.free(intOut);
    nativeMemory.free(voidOut);
    nativeMemory.free(summaryOut);
    nativeMemory.free(conversationOut);
    nativeMemory.free(subscriptionOut);
    nativeMemory.free(snapshotOut);
    nativeMemory.free(operationOut);
  }
}

Future<String> _buildFixture() async {
  final output =
      '${Directory.systemTemp.path}/codex_agent_dart_conversation_$pid'
      '${Platform.isMacOS ? '.dylib' : Platform.isWindows ? '.dll' : '.so'}';
  final source = File('test/native/fake_codex_agent.c').absolute.path;
  final result = Platform.isWindows
      ? await Process.run(
          'cl', <String>['/nologo', '/LD', source, '/link', '/OUT:$output'])
      : await Process.run('cc', <String>[
          '-std=c11',
          '-Wall',
          '-Wextra',
          '-Werror',
          '-pedantic',
          ...(Platform.isMacOS
              ? const <String>['-dynamiclib']
              : const <String>['-shared', '-fPIC', '-pthread']),
          source,
          '-o',
          output,
        ]);
  if (result.exitCode != 0) {
    throw StateError('conversation fixture compile failed: ${result.stderr}');
  }
  return output;
}

int _callCount(
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

Future<
    ({
      CodexHost host,
      CodexAgent agent,
      CodexConversations conversations,
      CodexConversation conversation,
    })> _open(String path) async {
  final host = await CodexHost.create(
    bundleDirectory: '.',
    dataDirectory: '.',
    clientInfo: CodexClientInfo(
        name: 'conversation', title: 'Conversation', version: '1'),
    libraryPath: path,
  );
  final agent = (await host.currentState).agent!;
  final conversations = agent.conversations;
  final conversation = await conversations.open();
  return (
    host: host,
    agent: agent,
    conversations: conversations,
    conversation: conversation,
  );
}

Future<void> _close(
    ({
      CodexHost host,
      CodexAgent agent,
      CodexConversations conversations,
      CodexConversation conversation,
    }) opened) async {
  await opened.conversation.dispose();
  await opened.conversations.close();
  await opened.agent.close();
  await opened.host.close();
}

Future<void> _expectRejected(Future<void> Function() body) => expectLater(
      body(),
      throwsA(isA<CodexNativeException>()),
    );

Future<void> _expectAsyncSemantics<T>(
  void Function() failNext,
  Future<T> Function(CodexCancellation cancellation) start,
) async {
  final cancellation = CodexCancellation();
  final cancelled = start(cancellation);
  cancellation.cancel();
  await expectLater(
    cancelled,
    throwsA(
      isA<CodexOperationException>().having(
        (error) => error.operationStatus,
        'operationStatus',
        CodexStatus.cancelled,
      ),
    ),
  );

  failNext();
  await expectLater(
    start(CodexCancellation()),
    throwsA(
      isA<CodexOperationException>()
          .having(
            (error) => error.operationStatus,
            'operationStatus',
            CodexStatus.operationFailed,
          )
          .having((error) => error.failure?.code, 'failure.code', 'fake')
          .having((error) => error.failure?.message, 'failure.message',
              'fake failure')
          .having((error) => error.failure?.isRecoverable,
              'failure.isRecoverable', isTrue),
    ),
  );
}

Future<List<T>> _stateValues<T>(
  CodexObservableState<T> state,
  Future<void> Function() closeParent, {
  int expectedCount = 2,
}) async {
  final cancelledValues = <T>[];
  final first = Completer<void>();
  late StreamSubscription<T> cancelled;
  cancelled = state.changes.listen((value) {
    cancelledValues.add(value);
    if (!first.isCompleted) first.complete();
  });
  await first.future;
  await cancelled.cancel();
  expect(cancelledValues, isNotEmpty);
  final cancelledCount = cancelledValues.length;

  final valuesFuture = state.changes.toList();
  final closeFuture = closeParent();
  final values = await valuesFuture;
  await closeFuture;
  await Future<void>.delayed(const Duration(milliseconds: 10));
  expect(cancelledValues, hasLength(cancelledCount),
      reason: 'cancelled state subscription delivered a later native event');
  expect(values, hasLength(expectedCount));
  return values;
}

Future<void> _exercise(
  DartConversationClaim claim,
  void Function() failNext,
  ({
    CodexHost host,
    CodexAgent agent,
    CodexConversations conversations,
    CodexConversation conversation,
  }) opened,
) async {
  final member = _member(claim.capabilityKey);
  if (_owner(claim.capabilityKey) == 'CodexConversations') {
    switch (member) {
      case 'delete':
        await _expectAsyncSemantics(
          failNext,
          (cancellation) => opened.conversations.delete(
            CodexConversationId('conversation-1'),
            cancellation: cancellation,
          ),
        );
        await _expectRejected(
            () => opened.conversations.delete(CodexConversationId('wrong')));
        final operation =
            opened.conversations.delete(CodexConversationId('conversation-1'));
        await Future.wait(<Future<void>>[operation, opened.agent.close()]);
      case 'list':
        await _expectAsyncSemantics(
          failNext,
          (cancellation) =>
              opened.conversations.list(cancellation: cancellation),
        );
        final operation = opened.conversations.list();
        final close = opened.agent.close();
        final values = await operation;
        await close;
        expect(values.map((value) => value.conversationId.value),
            <String>['conversation-1', 'conversation-2']);
        expect(
            values.map((value) => value.title), <String>['Fixture', 'Fixture']);
        expect(values.map((value) => value.updatedAtEpochSeconds),
            <int>[1700000000, 1700000001]);
        expect(values.clear, throwsUnsupportedError);
      case 'open':
        const options = CodexConversationOpenOptions(
          conversationId: 'conversation-2',
          approvalPreset: CodexApprovalPreset.askMe,
          serviceTier: 'priority',
        );
        await _expectAsyncSemantics(
          failNext,
          (cancellation) => opened.conversations.open(
            options: options,
            cancellation: cancellation,
          ),
        );
        await expectLater(
          opened.conversations.open(
            options: const CodexConversationOpenOptions(
              conversationId: 'wrong',
              approvalPreset: CodexApprovalPreset.askMe,
              serviceTier: 'priority',
            ),
          ),
          throwsA(isA<CodexNativeException>()),
        );
        final defaultValue = await opened.conversations.open();
        await defaultValue.dispose();
        final value = await opened.conversations.open(options: options);
        await opened.conversations.close();
        expect(await value.isSame(value), isTrue);
        await value.dispose();
        await value.dispose();
      case 'read':
        await _expectAsyncSemantics(
          failNext,
          (cancellation) => opened.conversations.read(
            CodexConversationId('conversation-1'),
            cancellation: cancellation,
          ),
        );
        await expectLater(
          opened.conversations.read(CodexConversationId('wrong')),
          throwsA(isA<CodexNativeException>()),
        );
        final operation =
            opened.conversations.read(CodexConversationId('conversation-1'));
        final close = opened.agent.close();
        final value = await operation;
        await close;
        expect(value.summary.conversationId.value, 'conversation-1');
        expect(value.summary.title, 'Fixture');
        expect(value.messages.map((message) => message.id),
            <String>['message-1', 'message-2']);
        expect(value.messages.map((message) => message.text),
            <String>['duplicate', 'duplicate']);
        expect(value.messages.first.clientMessageId, 'client-message');
        expect(value.messages.last.clientMessageId, isNull);
        expect(value.messages.first.reasoning, 'reasoning');
        expect(value.messages.last.reasoning, isNull);
        expect(value.messages.first.plan, isNull);
        expect(value.messages.last.plan, 'plan');
        expect(value.messages.first.shellCommand, 'pwd');
        expect(value.messages.last.shellCommand, isNull);
        expect(value.messages.first.exitCode, 7);
        expect(value.messages.last.exitCode, isNull);
        expect(value.messages.first.invocations.first,
            isA<CodexPluginInvocation>());
        expect(
            value.messages.first.invocations.last, isA<CodexSkillInvocation>());
        expect(value.messages.clear, throwsUnsupportedError);
      case 'rename':
        await _expectAsyncSemantics(
          failNext,
          (cancellation) => opened.conversations.rename(
            CodexConversationId('conversation-1'),
            'renamed',
            cancellation: cancellation,
          ),
        );
        await _expectRejected(() => opened.conversations
            .rename(CodexConversationId('conversation-1'), 'wrong'));
        final operation = opened.conversations
            .rename(CodexConversationId('conversation-1'), 'renamed');
        await Future.wait(<Future<void>>[operation, opened.agent.close()]);
      case 'active':
        final current = await opened.conversations.activeState.current;
        expect(current, isNotNull);
        final values = await _stateValues(
            opened.conversations.activeState, opened.agent.close);
        expect(values.first, isNull);
        expect(values.last, isNotNull);
        expect(await current!.isSame(values.last!), isTrue);
      default:
        throw StateError('unhandled conversations capability: $member');
    }
    return;
  }

  switch (member) {
    case 'cancelTurn':
      await _expectAsyncSemantics(
        failNext,
        (cancellation) =>
            opened.conversation.cancelTurn(cancellation: cancellation),
      );
      final operation = opened.conversation.cancelTurn();
      await Future.wait(<Future<void>>[operation, opened.agent.close()]);
    case 'close':
      await _expectAsyncSemantics(
        failNext,
        (cancellation) =>
            opened.conversation.closeConversation(cancellation: cancellation),
      );
      await opened.conversation.closeConversation();
      await opened.conversation.closeConversation();
      await opened.conversation.dispose();
      await opened.conversation.dispose();
    case 'reload':
      await _expectAsyncSemantics(
        failNext,
        (cancellation) =>
            opened.conversation.reload(cancellation: cancellation),
      );
      final operation = opened.conversation.reload();
      await Future.wait(<Future<void>>[operation, opened.agent.close()]);
    case 'runShellCommand':
      await _expectAsyncSemantics(
        failNext,
        (cancellation) => opened.conversation
            .runShellCommand('pwd', cancellation: cancellation),
      );
      await _expectRejected(() => opened.conversation.runShellCommand('wrong'));
      final operation = opened.conversation.runShellCommand('pwd');
      await Future.wait(<Future<void>>[operation, opened.agent.close()]);
    case 'send' when claim.capabilityKey.contains('AgentTurnRequest'):
      final request = CodexTurnRequest(
        prompt: 'structured',
        clientMessageId: 'client-1',
        model: 'gpt-test',
        effort: 'high',
        serviceTier: 'priority',
        approvalPreset: CodexApprovalPreset.askMe,
        capabilities: const <CodexCapability>{CodexCapability.webSearch},
        invocations: const <CodexInvocation>[
          CodexPluginInvocation(name: 'plugin', uri: 'plugin://fixture'),
          CodexSkillInvocation(name: 'skill', path: '/fixture/SKILL.md'),
        ],
        collaborationMode: CodexCollaborationMode.plan,
      );
      await _expectAsyncSemantics(
        failNext,
        (cancellation) => opened.conversation
            .sendRequest(request, cancellation: cancellation),
      );
      await _expectRejected(() => opened.conversation.sendRequest(
            CodexTurnRequest(prompt: 'wrong'),
          ));
      final operation = opened.conversation.sendRequest(request);
      await Future.wait(<Future<void>>[operation, opened.agent.close()]);
    case 'send':
      await _expectAsyncSemantics(
        failNext,
        (cancellation) =>
            opened.conversation.send('hello', cancellation: cancellation),
      );
      await _expectRejected(() => opened.conversation.send('wrong'));
      final operation = opened.conversation.send('hello');
      await Future.wait(<Future<void>>[operation, opened.agent.close()]);
    case 'activeTurnProgress':
      expect(await opened.conversation.activeTurnProgressState.current, isNull);
      final values = await _stateValues(
        opened.conversation.activeTurnProgressState,
        opened.agent.close,
        expectedCount: 4,
      );
      expect(values.first, isNotNull);
      final progress = values.first!;
      expect(progress.text, 'text');
      expect(progress.planProgress?.steps.map((step) => step.text),
          <String>['duplicate step', 'duplicate step']);
      expect(progress.planProgress?.steps.clear, throwsUnsupportedError);
      expect(progress.hookActivities.map((hook) => hook.id),
          <String>['hook-1', 'hook-2']);
      expect(progress.hookActivities.first.details,
          <String>['duplicate detail', 'duplicate detail']);
      expect(
          progress.hookActivities.first.details.clear, throwsUnsupportedError);
      expect(progress.shellExitCode, 9);
      expect(progress.workActivity, CodexWorkActivity.writingFiles);
      expect(progress.isTruncated, isTrue);
      final absentExplanation = values[1]!;
      expect(absentExplanation.planProgress, isNotNull);
      expect(absentExplanation.planProgress?.explanation, isNull);
      expect(absentExplanation.shellExitCode, isNull);
      expect(absentExplanation.workActivity, isNull);
      expect(absentExplanation.hookActivities.first.statusMessage, isNull);
      expect(values[2]?.planProgress, isNull);
      expect(values.last, isNull);
    case 'currentMessages':
      final current = await opened.conversation.messagesState.current;
      expect(current.map((message) => message.id),
          <String>['message-1', 'message-2']);
      expect(current.map((message) => message.text),
          <String>['duplicate', 'duplicate']);
      expect(current.clear, throwsUnsupportedError);
      final values = await _stateValues(
          opened.conversation.messagesState, opened.agent.close);
      expect(values.first.single.id, 'message-updated');
      expect(values.first.single.text, 'updated');
      expect(values.last, isEmpty);
    case 'state':
      expect((await opened.conversation.state.current).status,
          CodexConversationStatus.ready);
      final values =
          await _stateValues(opened.conversation.state, opened.agent.close);
      expect(values.map((state) => state.status), <CodexConversationStatus>[
        CodexConversationStatus.runningTurn,
        CodexConversationStatus.closed,
      ]);
    case 'canCancelTurn':
      await _exerciseBooleanState(
          opened.conversation.canCancelTurnState, opened.agent.close);
    case 'canReload':
      await _exerciseBooleanState(
          opened.conversation.canReloadState, opened.agent.close);
    case 'canRunShellCommand':
      await _exerciseBooleanState(
          opened.conversation.canRunShellCommandState, opened.agent.close);
    case 'canStartTurn':
      await _exerciseBooleanState(
          opened.conversation.canStartTurnState, opened.agent.close);
    case 'isTurnActive':
      await _exerciseBooleanState(
          opened.conversation.isTurnActiveState, opened.agent.close);
    default:
      throw StateError('unhandled conversation capability: $member');
  }
}

Future<void> _exerciseBooleanState(
  CodexObservableState<bool> state,
  Future<void> Function() closeParent,
) async {
  expect(await state.current, isFalse);
  expect(await _stateValues(state, closeParent), <bool>[true, false]);
}

void registerConversationParity(
  List<DartConversationClaim> claims,
  Directory root,
  Map<String, Set<String>> passedCompilerEvidence,
  Set<String> passedTestIds,
) {
  late final Future<String> fixture = _buildFixture();
  test('dart.conversation.inventory', () {
    expect(() => verifyConversationClaims(claims, root), returnsNormally);
  });
  test('dart.conversation inventory and production lookups fail closed', () {
    expect(() => verifyConversationClaims(claims.sublist(1), root),
        throwsStateError);
    final source = <String>[
      File('${root.path}/codex-agent-runtime-desktop/bindings/dart/lib/src/'
              'client.dart')
          .readAsStringSync(),
      File('${root.path}/codex-agent-runtime-desktop/bindings/dart/lib/src/'
              'ffi.dart')
          .readAsStringSync(),
      File('${root.path}/codex-agent-runtime-desktop/bindings/dart/lib/src/'
              'conversation_native.dart')
          .readAsStringSync(),
    ].join('\n');
    for (final symbol in claims.expand(_headerCalls).toSet()) {
      expect(
        () => verifyConversationClaims(
          claims,
          root,
          sourceOverride: source.replaceAll("'$symbol'", "'codex_agent_stale'"),
        ),
        throwsStateError,
        reason: 'missing production lookup was accepted: $symbol',
      );
    }
  });

  final sorted = claims.toList()
    ..sort((left, right) => left.capabilityKey.compareTo(right.capabilityKey));
  for (final claim in sorted) {
    test(claim.executedTests.single, () async {
      final path = await fixture;
      final count = DynamicLibrary.open(path).lookupFunction<
          Int32 Function(Pointer<Uint8>),
          int Function(Pointer<Uint8>)>('codex_agent_dart_leaf_call_count');
      final failNext = DynamicLibrary.open(path)
          .lookupFunction<Void Function(), void Function()>(
              'codex_agent_dart_test_fail_next_operation');
      final headers = _headerCalls(claim);
      final opened = await _open(path);
      final before = <String, int>{
        for (final symbol in headers) symbol: _callCount(count, symbol),
      };
      try {
        await _exercise(claim, failNext, opened);
        for (final symbol in headers) {
          expect(_callCount(count, symbol), greaterThan(before[symbol]!),
              reason: 'public behavior did not execute $symbol');
        }
      } finally {
        await _close(opened);
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
