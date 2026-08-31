import 'dart:io';

import 'package:codex_agent/codex_agent.dart';

Future<void> main(List<String> arguments) async {
  if (arguments.length != 1) {
    stderr.writeln(
      'usage: dart run bin/host_smoke.dart <absolute-c-sdk-library>',
    );
    exitCode = 64;
    return;
  }

  final placeholderDirectory = Directory.systemTemp.absolute.path;
  final host = await CodexHost.create(
    bundleDirectory: placeholderDirectory,
    dataDirectory: placeholderDirectory,
    clientInfo: CodexClientInfo(
      name: 'installed-host-smoke',
      title: 'Installed Host smoke',
      version: '1.0.0',
    ),
    libraryPath: arguments.single,
  );

  final initial = await host.currentState;
  if (initial.kind != CodexHostStateKind.newHost) {
    throw StateError('expected new Host state, got ${initial.kind.name}');
  }

  final Future<void> firstClose = host.close();
  final Future<void> repeatedClose = host.close();
  await Future.wait(<Future<void>>[firstClose, repeatedClose]);
  await host.close();

  try {
    await host.currentState;
  } on CodexClosedException {
    stdout.writeln('Dart installed Host smoke passed.');
    return;
  }
  throw StateError('closed Host remained usable');
}
