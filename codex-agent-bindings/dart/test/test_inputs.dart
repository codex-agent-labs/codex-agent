import 'dart:io';

File requiredInputFile(String name) {
  final path = Platform.environment[name];
  if (path == null || path.isEmpty) {
    throw StateError('$name is required');
  }
  final file = File(path).absolute;
  if (!file.existsSync()) {
    throw StateError('$name does not exist: ${file.path}');
  }
  return file;
}

Directory requiredCSdkInclude() {
  final root = Platform.environment['CODEX_AGENT_C_SDK_ROOT'];
  if (root == null || root.isEmpty) {
    throw StateError('CODEX_AGENT_C_SDK_ROOT is required');
  }
  final include = Directory('$root/include').absolute;
  final header = File('${include.path}/codex_agent.h');
  if (!header.existsSync()) {
    throw StateError(
      'CODEX_AGENT_C_SDK_ROOT must contain include/codex_agent.h: $root',
    );
  }
  return include;
}

File canonicalApiReport() =>
    requiredInputFile('CODEX_AGENT_CANONICAL_API_REPORT');

File cAbiBootstrapEvidence() =>
    requiredInputFile('CODEX_AGENT_C_ABI_BOOTSTRAP_EVIDENCE');

File cAbiHeader() => File('${requiredCSdkInclude().path}/codex_agent.h');

File requiredRealLibrary() => requiredInputFile('CODEX_AGENT_REAL_LIBRARY');
