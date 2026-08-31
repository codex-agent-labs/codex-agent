import 'dart:ffi';
import 'dart:io';

import 'package:codex_agent/codex_agent.dart';
import 'package:codex_agent/src/ffi.dart';
import 'package:test/test.dart';

void main() {
  test('public values preserve native status identity', () {
    expect(CodexStatus.busy.value, 6);
    expect(CodexStatus.operationFailed.value, 14);
    expect(CodexConversationStatus.runningTurn.value, 4);
    expect(CodexApprovalPreset.strict.value, 3);
  });

  test('C ABI size_t and versioned struct layouts are exact', () {
    expect(sizeOf<Size>(), sizeOf<Pointer<Void>>());
    expect(sizeOf<CodexStringView>(), 16);
    expect(sizeOf<CodexClientInfoStruct>(), 56);
    expect(sizeOf<CodexHostOptionsStruct>(), 96);
    expect(sizeOf<CodexPathWorkspaceSelectionStruct>(), 24);
    expect(sizeOf<CodexConversationOpenOptionsStruct>(), 56);
  });

  test('cancellation is idempotent and late listeners fire', () {
    final cancellation = CodexCancellation();
    var calls = 0;
    cancellation.attach(() => calls++);
    cancellation.cancel();
    cancellation.cancel();
    cancellation.attach(() => calls++);
    expect(calls, 2);
  });

  test('unsupported explicit native path fails closed', () async {
    await expectLater(
      CodexHost.create(
        bundleDirectory: '.',
        dataDirectory: '.',
        clientInfo: CodexClientInfo(
          name: 'test',
          title: 'Test',
          version: '1',
        ),
        libraryPath: '${Directory.systemTemp.path}/missing-codex-agent-library',
      ),
      throwsA(isA<CodexException>()),
    );
  });
}
