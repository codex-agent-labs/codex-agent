import 'dart:io';

import 'package:codex_agent/src/ffi.dart' show currentClassifier;
import 'package:codex_agent/src/runtime_compatibility.dart';

List<String> runtimeIdentityCompilerDefinitions() {
  final compatibility = RuntimeCompatibility.load();
  final prefix = Platform.isWindows ? '/D' : '-D';
  return [
    '${prefix}CODEX_AGENT_TEST_CONTRACT_DIGEST="${compatibility.contractDigest}"',
    '${prefix}CODEX_AGENT_TEST_TARGET="${currentClassifier()}"',
  ];
}

String nativeFixturePath(String name) =>
    '${Directory.systemTemp.resolveSymbolicLinksSync()}${Platform.pathSeparator}$name';
