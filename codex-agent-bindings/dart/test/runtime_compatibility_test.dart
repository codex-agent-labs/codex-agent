import 'dart:collection';
import 'dart:convert';
import 'dart:ffi';
import 'dart:io';

import 'package:codex_agent/src/errors.dart';
import 'package:codex_agent/src/ffi.dart';
import 'package:codex_agent/src/runtime_compatibility.dart';
import 'package:test/test.dart';

const _digestA =
    'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _digestB =
    'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

void main() {
  late Directory temporary;
  late Map<String, Object?> declaration;

  setUp(() {
    temporary = Directory(
      Directory.systemTemp.resolveSymbolicLinksSync(),
    ).createTempSync('codex-agent-dart-runtime-');
    declaration = (jsonDecode(
      File('lib/src/native/sdk-compatibility.json').readAsStringSync(),
    ) as Map<String, Object?>);
  });

  tearDown(() => temporary.deleteSync(recursive: true));

  test('canonical SDK declaration and compatible identities are exact', () {
    final compatibility = _writeCompatibility(temporary, declaration);
    final target = currentClassifier();
    final embedded = compatibility.embeddedVariants[target]!;

    compatibility.verifyRuntimeIdentity(
      _identity(target, componentId: embedded.componentId),
      target,
      embedded: true,
    );
    compatibility.verifyRuntimeIdentity(
      _identity(target, componentId: _digestA),
      target,
      embedded: false,
    );
  });

  test('embedded bytes are authenticated and external bytes may differ', () {
    final library = File('${temporary.path}/runtime')
      ..writeAsStringSync('runtime');
    final digest = runtimeFileSha256(library);
    final target = currentClassifier();
    final variants =
        _runtime(declaration)['embeddedVariants']! as List<Object?>;
    final record = variants.cast<Map<String, Object?>>().firstWhere(
          (value) => value['target'] == target,
        );
    record['runtimeLibrarySha256'] = digest;
    final compatibility = _writeCompatibility(temporary, declaration);

    final snapshot = snapshotRuntimeLibrary(
      library,
      compatibility,
      target,
      embedded: true,
    );
    expect(snapshot.digest, digest);
    snapshot.removeAfterLoad();
    expect(
      () => snapshotRuntimeLibrary(
        library,
        compatibility,
        target,
        embedded: true,
        afterDescriptorRead: () => library.writeAsStringSync('tampered'),
      ),
      throwsA(isA<CodexException>()),
    );
    final external = snapshotRuntimeLibrary(
      library,
      compatibility,
      target,
      embedded: false,
    );
    external.removeAfterLoad();
  });

  test('identity rejects schema target Contract ABI range and component drift',
      () {
    final compatibility = _writeCompatibility(temporary, declaration);
    final target = currentClassifier();
    final embedded = compatibility.embeddedVariants[target]!;
    final valid = jsonDecode(
      _identity(target, componentId: embedded.componentId),
    ) as Map<String, Object?>;
    final cases = <Map<String, Object?>>[
      {...valid, 'schemaVersion': 2},
      {
        ...valid,
        'target': target == 'macos-arm64' ? 'linux-x64' : 'macos-arm64'
      },
      {...valid, 'contractDigest': _digestA},
      {...valid, 'cAbiVersion': '1.12.0'},
      {...valid, 'runtimeCompatibilityVersion': '0.3.0'},
      {...valid, 'componentId': _digestB},
    ];
    for (final identity in cases) {
      expect(
        () => compatibility.verifyRuntimeIdentity(
          jsonEncode(identity),
          target,
          embedded: true,
        ),
        throwsA(isA<CodexException>()),
      );
    }
    expect(
      () => compatibility.verifyRuntimeIdentity(
        _identity(target, componentId: embedded.componentId),
        target,
        embedded: true,
        actualAbiVersion: (1 << 24) | (14 << 16),
      ),
      throwsA(isA<CodexException>()),
    );
  });

  test('declaration rejects noncanonical unknown and incomplete inputs', () {
    final file = File('${temporary.path}/sdk-compatibility.json');
    file.writeAsStringSync(jsonEncode(declaration));
    expect(
      () => RuntimeCompatibility.read(file),
      throwsA(isA<CodexException>()),
    );

    final contract = declaration['contract']! as Map<String, Object?>;
    declaration['contract'] = {
      'version': contract['version'],
      'digest': contract['digest'],
    };
    file.writeAsStringSync('${jsonEncode(declaration)}\n');
    expect(
      () => RuntimeCompatibility.read(file),
      throwsA(isA<CodexException>()),
    );
    declaration['contract'] = contract;

    declaration['unknown'] = true;
    file.writeAsStringSync(_canonicalJson(declaration));
    expect(
      () => RuntimeCompatibility.read(file),
      throwsA(isA<CodexException>()),
    );

    declaration.remove('unknown');
    (_runtime(declaration)['embeddedVariants']! as List<Object?>).removeLast();
    file.writeAsStringSync(_canonicalJson(declaration));
    expect(
      () => RuntimeCompatibility.read(file),
      throwsA(isA<CodexException>()),
    );
  });

  test('default release and embedded identities are internally consistent', () {
    void expectRejected(void Function(Map<String, Object?>) mutate) {
      final changed =
          jsonDecode(jsonEncode(declaration)) as Map<String, Object?>;
      mutate(changed);
      expect(
        () => _writeCompatibility(temporary, changed),
        throwsA(isA<CodexException>()),
      );
    }

    expectRejected(
      (value) => _runtime(value)['defaultRuntimeVersion'] = '0.3.0',
    );
    expectRejected((value) {
      final variants = _runtime(value)['embeddedVariants']! as List<Object?>;
      (variants[1]! as Map<String, Object?>)['componentId'] =
          (variants[0]! as Map<String, Object?>)['componentId'];
    });
    expectRejected((value) {
      final variants = _runtime(value)['embeddedVariants']! as List<Object?>;
      (variants[1]! as Map<String, Object?>)['manifestSha256'] =
          (variants[0]! as Map<String, Object?>)['manifestSha256'];
    });
  });

  test('caller library paths are literal absolute regular files', () {
    for (final path in [
      '',
      'relative/runtime',
      libraryNameFor(currentClassifier())
    ]) {
      expect(
        () => resolveLibraryPathSync(path),
        throwsA(isA<CodexException>()),
      );
    }

    final real = File('${temporary.path}/runtime')
      ..writeAsStringSync('runtime');
    final separator = Platform.pathSeparator;
    final redundant =
        '${real.parent.path}$separator$separator${real.uri.pathSegments.last}';
    expect(
      () => resolveLibraryPathSync(redundant),
      throwsA(isA<CodexException>()),
    );
    final systemTemporary = Directory.systemTemp.absolute.path;
    final canonicalTemporary = Directory.systemTemp.resolveSymbolicLinksSync();
    if (systemTemporary != canonicalTemporary &&
        real.path.startsWith('$canonicalTemporary$separator')) {
      final alias =
          '$systemTemporary${real.path.substring(canonicalTemporary.length)}';
      expect(
        () => resolveLibraryPathSync(alias),
        throwsA(isA<CodexException>()),
      );
    }
    final finalLink = Link('${temporary.path}/runtime-link')
      ..createSync(real.path);
    expect(
      () => resolveLibraryPathSync(finalLink.path),
      throwsA(isA<CodexException>()),
    );
    final parent = Directory('${temporary.path}/parent')..createSync();
    final nested = File('${parent.path}/runtime')..writeAsStringSync('runtime');
    final parentLink = Link('${temporary.path}/parent-link')
      ..createSync(parent.path);
    expect(
      () => resolveLibraryPathSync(
          '${parentLink.path}/${nested.uri.pathSegments.last}'),
      throwsA(isA<CodexException>()),
    );
    expect(resolveLibraryPathSync(real.path), real.path);
  });

  test('reordered declaration and Runtime identity keys fail closed', () {
    final compatibility = _writeCompatibility(temporary, declaration);
    final target = currentClassifier();
    final identity = jsonDecode(
      _identity(target, componentId: _digestA),
    ) as Map<String, Object?>;
    final reordered = <String, Object?>{
      'target': identity['target'],
      ...identity..remove('target'),
    };
    expect(
      () => compatibility.verifyRuntimeIdentity(
        jsonEncode(reordered),
        target,
        embedded: false,
      ),
      throwsA(isA<CodexException>()),
    );
  });

  test('native identity function is required and uses the buffer contract',
      () async {
    final compatibility = _writeCompatibility(temporary, declaration);
    final target = currentClassifier();
    final valid = await _compileLibrary(
      temporary,
      'valid',
      identity: _identity(target, componentId: _digestA),
    );
    final missing = await _compileLibrary(temporary, 'missing');

    final json = readRuntimeIdentity(DynamicLibrary.open(valid.path));
    compatibility.verifyRuntimeIdentity(json, target, embedded: false);
    expect(
      () => readRuntimeIdentity(DynamicLibrary.open(missing.path)),
      throwsA(isA<CodexException>()),
    );
  });

  test('identity ABI must exactly equal the exported ABI before API lookup',
      () async {
    final target = currentClassifier();
    final mismatch = await _compileLibrary(
      temporary,
      'abi-mismatch',
      identity: _identity(target, componentId: _digestA),
      abiVersion: (1 << 24) | (14 << 16),
    );
    expect(
      () => NativeApi.load(mismatch.path),
      throwsA(isA<CodexException>()),
    );
  });

  test('identity ABI fields must fit the packed C ABI widths', () {
    final compatibility = _writeCompatibility(temporary, declaration);
    final target = currentClassifier();
    for (final claimed in const ['1.13.65536', '1.269.0']) {
      final identity = jsonDecode(
        _identity(target, componentId: _digestA),
      ) as Map<String, Object?>;
      identity['cAbiVersion'] = claimed;
      expect(
        () => compatibility.verifyRuntimeIdentity(
          jsonEncode(identity),
          target,
          embedded: false,
          actualAbiVersion: requiredAbiVersion,
        ),
        throwsA(isA<CodexException>()),
        reason: '$claimed must not collide with packed ABI 1.13.0',
      );
    }
  });

  test('identity is authenticated before the exported ABI is called', () async {
    final target = currentClassifier();
    final library = await _compileLibrary(
      temporary,
      'identity-first',
      identity: _identity(target, componentId: _digestA),
      abiVersion: requiredAbiVersion,
      requireIdentityBeforeAbi: true,
    );

    expect(
      authenticatedRuntimeLibraryForTesting(library.path)
          .lookupFunction<Int32 Function(), int Function()>(
        'codex_agent_test_marker',
      )(),
      1,
    );
  });

  test('dynamic open remains bound to the authenticated private file',
      () async {
    final target = currentClassifier();
    final verified = await _compileLibrary(
      temporary,
      'verified',
      identity: _identity(target, componentId: _digestA),
      abiVersion: requiredAbiVersion,
      marker: 1,
    );
    final malicious = await _compileLibrary(
      temporary,
      'malicious',
      identity: _identity(target, componentId: _digestA),
      abiVersion: requiredAbiVersion,
      marker: 2,
    );
    var replacementWasBlocked = false;
    final loaded = authenticatedRuntimeLibraryForTesting(
      verified.path,
      beforeDynamicOpen: (snapshot) {
        try {
          if (snapshot.existsSync()) {
            snapshot.renameSync('${snapshot.path}.verified');
          }
          malicious.copySync(snapshot.path);
        } on FileSystemException {
          replacementWasBlocked = true;
        }
      },
    );

    expect(
      loaded.lookupFunction<Int32 Function(), int Function()>(
        'codex_agent_test_marker',
      )(),
      1,
    );
    expect(replacementWasBlocked, isNot(Platform.isLinux));
  });

  test('child-process load leaves no owned Runtime snapshot behind', () async {
    final target = currentClassifier();
    final library = await _compileLibrary(
      temporary,
      'child-runtime',
      identity: _identity(target, componentId: _digestA),
      abiVersion: requiredAbiVersion,
    );
    final child = File('${temporary.path}/load_runtime.dart')
      ..writeAsStringSync('''
import 'package:codex_agent/src/ffi.dart';

void main(List<String> arguments) {
  authenticatedRuntimeLibraryForTesting(arguments.single);
}
''');
    final before = _runtimeSnapshots();
    final result = await Process.run(Platform.resolvedExecutable, [
      '--packages=${File('.dart_tool/package_config.json').absolute.path}',
      child.path,
      library.path,
    ]);
    expect(result.exitCode, 0, reason: '${result.stdout}\n${result.stderr}');
    expect(_runtimeSnapshots().difference(before), isEmpty);

    // In particular, Windows has released the source DLL handle at exit.
    final renamed = File('${library.path}.renamed');
    library.renameSync(renamed.path);
    renamed.renameSync(library.path);
  });
}

Set<String> _runtimeSnapshots() => Directory(
      Directory.systemTemp.resolveSymbolicLinksSync(),
    )
        .listSync()
        .whereType<Directory>()
        .map((entry) => entry.path)
        .where((path) => path
            .split(Platform.pathSeparator)
            .last
            .startsWith('codex-agent-runtime-snapshot-'))
        .toSet();

RuntimeCompatibility _writeCompatibility(
  Directory root,
  Map<String, Object?> value,
) {
  final file = File('${root.path}/sdk-compatibility.json');
  file.writeAsStringSync(_canonicalJson(value));
  return RuntimeCompatibility.read(file);
}

Map<String, Object?> _runtime(Map<String, Object?> value) =>
    value['runtime']! as Map<String, Object?>;

String _identity(String target, {required String componentId}) => jsonEncode({
      'appServerVersion': '0.149.0',
      'buildInputDigest': _digestB,
      'cAbiVersion': '1.13.0',
      'componentId': componentId,
      'contractComponentDigest': _digestA,
      'contractDigest':
          'sha256:1111111111111111111111111111111111111111111111111111111111111111',
      'runtimeCompatibilityVersion': '0.2.0',
      'schemaVersion': 1,
      'target': target,
    });

String _canonicalJson(Object? value) => '${jsonEncode(_sorted(value))}\n';

Object? _sorted(Object? value) => switch (value) {
      Map<String, Object?> map => SplayTreeMap<String, Object?>.of(
          Map.fromEntries(map.entries.map(
            (entry) => MapEntry(entry.key, _sorted(entry.value)),
          )),
        ),
      List<Object?> list => list.map(_sorted).toList(),
      _ => value,
    };

Future<File> _compileLibrary(
  Directory root,
  String name, {
  String? identity,
  int? abiVersion,
  bool requireIdentityBeforeAbi = false,
  int marker = 1,
}) async {
  final source = File('${root.path}/$name.c');
  final output = File(
    '${root.path}/$name${Platform.isMacOS ? '.dylib' : Platform.isWindows ? '.dll' : '.so'}',
  );
  source.writeAsStringSync(identity == null
      ? 'int codex_agent_test_only(void) { return 0; }\n'
      : '''
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif
static const char runtime_identity[] = ${jsonEncode(identity)};
static int identity_queried = 0;
${abiVersion == null ? '' : '''
API uint32_t codex_agent_abi_version(void) {
  ${requireIdentityBeforeAbi ? 'if (!identity_queried) return 0u;' : ''}
  return ${abiVersion}u;
}
API int32_t codex_agent_abi_is_compatible(uint32_t requested) {
  return (requested >> 24) == 1u;
}
'''}
API int32_t codex_agent_test_marker(void) { return $marker; }
API int32_t codex_agent_runtime_identity(char *buffer, size_t *size) {
  identity_queried = 1;
  size_t required = sizeof(runtime_identity);
  if (size == NULL) return 1;
  if (buffer == NULL || *size < required) { *size = required; return 9; }
  memcpy(buffer, runtime_identity, required);
  *size = required;
  return 0;
}
''');
  final result = Platform.isWindows
      ? await Process.run('cl', [
          '/nologo',
          '/LD',
          source.path,
          '/link',
          '/OUT:${output.path}',
        ])
      : await Process.run('cc', [
          '-std=c11',
          '-Wall',
          '-Wextra',
          '-Werror',
          '-pedantic',
          if (Platform.isMacOS) '-dynamiclib' else ...['-shared', '-fPIC'],
          source.path,
          '-o',
          output.path,
        ]);
  if (result.exitCode != 0) {
    throw StateError('fixture compilation failed: ${result.stderr}');
  }
  return output;
}
