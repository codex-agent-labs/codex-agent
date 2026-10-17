import 'package:codex_agent/codex_agent.dart';

Future<void> main(List<String> arguments) async {
  if (arguments.length != 3) {
    throw ArgumentError(
      'usage: dart run example/main.dart <bundle-dir> <data-dir> <library>',
    );
  }
  final host = await CodexHost.create(
    bundleDirectory: arguments[0],
    dataDirectory: arguments[1],
    libraryPath: arguments[2],
    clientInfo: CodexClientInfo(
      name: 'dart-example',
      title: 'Dart example',
      version: '1.0.0',
    ),
  );
  try {
    await host.start();
    final ready = await host.states.firstWhere(
      (state) => state.kind == CodexHostStateKind.ready,
    );
    final conversation = await ready.agent!.conversations.open();
    try {
      await conversation.send('Hello from Dart');
    } finally {
      try {
        await conversation.closeConversation();
      } finally {
        await conversation.dispose();
      }
    }
  } finally {
    await host.close();
  }
}
