import 'dart:developer';
import 'dart:ffi';

import 'package:codex_agent/codex_agent.dart';
import 'package:vm_service/vm_service.dart';
import 'package:vm_service/vm_service_io.dart';

typedef _CounterNative = Int32 Function();
typedef _CounterDart = int Function();

Future<WeakReference<CodexHost>> _abandonHost(String libraryPath) async {
  final host = await CodexHost.create(
    bundleDirectory: '.',
    dataDirectory: '.',
    clientInfo: CodexClientInfo(
      name: 'finalizer-test',
      title: 'Finalizer test',
      version: '1',
    ),
    libraryPath: libraryPath,
  );
  return WeakReference<CodexHost>(host);
}

final class _RetainedChild {
  _RetainedChild(this.host, this.agent);

  final WeakReference<CodexHost> host;
  CodexAgent? agent;
}

Future<_RetainedChild> _abandonHostButRetainChild(String libraryPath) async {
  final host = await CodexHost.create(
    bundleDirectory: '.',
    dataDirectory: '.',
    clientInfo: CodexClientInfo(
      name: 'finalizer-child-test',
      title: 'Finalizer child test',
      version: '1',
    ),
    libraryPath: libraryPath,
  );
  final agent = (await host.currentState).agent!;
  return _RetainedChild(WeakReference<CodexHost>(host), agent);
}

Future<void> _collect(VmService service, String isolateId) async {
  await service.getAllocationProfile(isolateId, gc: true);
  await Future<void>.delayed(const Duration(milliseconds: 10));
}

Future<void> _releaseRetainedChild(_RetainedChild retained) async {
  final agent = retained.agent!;
  final conversations = agent.conversations;
  await conversations.close();
  await agent.close();
  retained.agent = null;
}

Future<void> main(List<String> arguments) async {
  if (arguments.isEmpty || arguments.length > 2) {
    throw ArgumentError('native library path and optional mode required');
  }
  final libraryPath = arguments.first;
  final mode = arguments.length == 2 ? arguments[1] : 'abandon';
  final library = DynamicLibrary.open(libraryPath);
  final hostClose = library.lookupFunction<_CounterNative, _CounterDart>(
    'codex_agent_test_host_close_calls',
  );
  final hostRelease = library.lookupFunction<_CounterNative, _CounterDart>(
    'codex_agent_test_host_release_calls',
  );
  final contextDestroy = library.lookupFunction<_CounterNative, _CounterDart>(
    'codex_agent_test_context_destroy_calls',
  );

  final serviceInfo = await Service.getInfo();
  final webSocket = serviceInfo.serverWebSocketUri;
  if (webSocket == null) throw StateError('VM service is required');
  final service = await vmServiceConnectUri(webSocket.toString());
  final vm = await service.getVM();
  final isolateId = vm.isolates!.single.id!;
  if (mode == 'child') {
    final retained = await _abandonHostButRetainChild(libraryPath);
    for (var attempt = 0; attempt < 50; attempt++) {
      await _collect(service, isolateId);
      if (retained.host.target == null) break;
    }
    if (retained.host.target != null ||
        hostClose() != 0 ||
        hostRelease() != 0 ||
        contextDestroy() != 0) {
      await service.dispose();
      throw StateError(
        'a reachable child must retain native host lifetime: '
        'hostReachable=${retained.host.target != null}, close=${hostClose()}, '
        'release=${hostRelease()}, context=${contextDestroy()}',
      );
    }
    await _releaseRetainedChild(retained);
    for (var attempt = 0; attempt < 100; attempt++) {
      await _collect(service, isolateId);
      if (hostClose() == 1 && hostRelease() == 1 && contextDestroy() == 1) {
        await service.dispose();
        return;
      }
    }
    await service.dispose();
    throw StateError(
      'host lifetime did not finalize after its last child: '
      'close=${hostClose()}, release=${hostRelease()}, '
      'context=${contextDestroy()}',
    );
  }
  if (mode != 'abandon') throw ArgumentError.value(mode, 'mode');
  final weak = await _abandonHost(libraryPath);
  for (var attempt = 0; attempt < 100; attempt++) {
    await _collect(service, isolateId);
    if (weak.target == null &&
        hostClose() == 1 &&
        hostRelease() == 1 &&
        contextDestroy() == 1) {
      await service.dispose();
      return;
    }
  }
  await service.dispose();
  throw StateError(
    'finalizer did not complete semantic close/release/context destruction: '
    'reachable=${weak.target != null}, close=${hostClose()}, '
    'release=${hostRelease()}, context=${contextDestroy()}',
  );
}
