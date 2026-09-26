import 'dart:collection';
import 'dart:convert';
import 'dart:ffi';
import 'dart:io';

import 'package:crypto/crypto.dart' as crypto;
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

  test('0.8.x accepts a compatible external Runtime only', () {
    final runtime = _runtime(declaration);
    runtime['compatibleReleaseRange'] = '>=0.8.0 <0.9.0';
    runtime['compatibleRuntimeCompatibilityRange'] = '>=0.8.0 <0.9.0';
    runtime['defaultRuntimeVersion'] = '0.8.0';
    final compatibility = _writeCompatibility(temporary, declaration);
    final target = currentClassifier();
    final embedded = compatibility.embeddedVariants[target]!;

    compatibility.verifyRuntimeIdentity(
      _identity(target, componentId: _digestA, version: '0.8.5'),
      target,
      embedded: false,
    );
    for (final version in const ['0.7.9', '0.9.0']) {
      expect(
        () => compatibility.verifyRuntimeIdentity(
          _identity(target, componentId: _digestA, version: version),
          target,
          embedded: false,
        ),
        throwsA(isA<CodexException>()),
      );
    }
    expect(
      () => compatibility.verifyRuntimeIdentity(
        _identity(target, componentId: _digestA, version: '0.8.5'),
        target,
        embedded: true,
      ),
      throwsA(isA<CodexException>()),
    );
    compatibility.verifyRuntimeIdentity(
      _identity(target, componentId: embedded.componentId, version: '0.8.0'),
      target,
      embedded: true,
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

  test('Runtime hash rejects an oversized sparse file before reading it', () {
    final library = File('${temporary.path}/oversized-runtime');
    final opened = library.openSync(mode: FileMode.write);
    try {
      opened.truncateSync(512 * 1024 * 1024 + 1);
    } finally {
      opened.closeSync();
    }
    expect(() => runtimeFileSha256(library), throwsA(isA<CodexException>()));
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
      {...valid, 'contractDigest': _wrongContractDigest},
      {...valid, 'cAbiVersion': '1.12.0'},
      {...valid, 'cAbiVersion': '2.0.0'},
      {...valid, 'runtimeCompatibilityVersion': '0.9.0'},
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

  test('missing SDK compatibility declaration fails closed', () {
    expect(
      () => RuntimeCompatibility.read(
        File('${temporary.path}/missing-sdk-compatibility.json'),
      ),
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
      (value) => _runtime(value)['defaultRuntimeVersion'] = '0.9.0',
    );
    expectRejected(
      (value) =>
          _runtime(value)['requiredContractDigest'] = _wrongContractDigest,
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
    expectRejected((value) {
      final platform = value['platformRuntime']! as Map<String, Object?>;
      final android = platform['android']! as Map<String, Object?>;
      android['desktopRuntimeApplicable'] = true;
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

  test('incompatible explicit override fails at the loader boundary', () async {
    final target = currentClassifier();
    final identity = jsonDecode(
      _identity(target, componentId: _digestA),
    ) as Map<String, Object?>;
    identity['contractDigest'] = _wrongContractDigest;
    final incompatible = await _compileLibrary(
      temporary,
      'incompatible-override',
      identity: jsonEncode(identity),
      abiVersion: requiredAbiVersion,
    );

    expect(
      () => authenticatedRuntimeLibraryForTesting(incompatible.path),
      throwsA(isA<CodexException>()),
    );
  });

  test('path-only override fails before dynamic loading', () {
    final library = File('${temporary.path}/path-only-runtime')
      ..writeAsStringSync('not a native library');
    var reachedDynamicOpen = false;

    expect(
      () => authenticatedRuntimeLibraryForTesting(
        library.path,
        beforeDynamicOpen: (_) => reachedDynamicOpen = true,
      ),
      throwsA(isA<CodexException>().having(
        (error) => error.message,
        'message',
        contains('release evidence is unavailable'),
      )),
    );
    expect(reachedDynamicOpen, isFalse);
    expect(
      () => NativeApi.load(library.path),
      throwsA(isA<CodexException>().having(
        (error) => error.message,
        'message',
        contains('release evidence is unavailable'),
      )),
    );
  });

  test('explicit packaged library uses embedded trust, not external evidence',
      () {
    expect(requiresExternalRuntimeEvidence(true, true), isFalse);
    expect(requiresExternalRuntimeEvidence(false, true), isFalse);
    expect(requiresExternalRuntimeEvidence(true, false), isTrue);
    expect(requiresExternalRuntimeEvidence(false, false), isFalse);
  });

  test('Windows external signature verification fails closed', () {
    expect(supportsExternalRuntimeSignatureVerifier('windows'), isFalse);
    expect(supportsExternalRuntimeSignatureVerifier('macos'), isTrue);
    expect(supportsExternalRuntimeSignatureVerifier('linux'), isTrue);
  });

  test('root-delegated release evidence binds exact external bytes', () {
    if (Platform.isWindows) return;
    final library = File('${temporary.path}/signed-runtime')
      ..writeAsStringSync('synthetic runtime bytes');
    final root = _testKey(temporary, 'root');
    final signer = _testKey(temporary, 'signer');
    final evidence = Directory('${library.path}.evidence')..createSync();
    final keys = Directory('${evidence.path}/keys')..createSync();
    final releaseKey = File('${keys.path}/release-a.pub')
      ..writeAsBytesSync(signer.public);
    final signerFingerprint = _fingerprint(signer.public);
    final keyring = File('${evidence.path}/release-keyring.json')
      ..writeAsStringSync(_canonicalJson({
        'schemaVersion': 1,
        'namespace': 'codex-agent-product-v1',
        'algorithm': 'ssh-ed25519',
        'trustDomain': 'release',
        'activeKey': {
          'keyId': 'release-a',
          'fingerprint': signerFingerprint,
        },
        'retiredKeys': <Object>[],
      }));
    final delegation = File('${evidence.path}/root-delegation.json')
      ..writeAsStringSync(_canonicalJson({
        'schemaVersion': 1,
        'kind': 'sdk-runtime-release-keyring-delegation',
        'scope': 'desktop-runtime-library',
        'rootFingerprint': _fingerprint(root.public),
        'keyringSha256': _digest(keyring.readAsBytesSync()),
      }));
    _sign(delegation, root.privateKey, 'codex-agent-sdk-runtime-root-v1');
    final claim = File('${evidence.path}/runtime-library-authorization.json')
      ..writeAsStringSync(_canonicalJson({
        'schemaVersion': 1,
        'kind': 'desktop-runtime-library-authorization',
        'runtimeVersion': '0.8.0',
        'runtimeIdentity':
            jsonDecode(_identity(currentClassifier(), componentId: _digestA)),
        'runtimeLibrarySha256': runtimeFileSha256(library),
        'variantBundleSha256': _digestA,
        'variantManifestSha256': _digestA,
        'aggregateManifestSha256': _digestA,
        'variantAttestationSha256': _digestA,
        'aggregateAttestationSha256': _digestA,
        'signing': {
          'algorithm': 'ssh-ed25519',
          'namespace': 'codex-agent-product-v1',
          'trustDomain': 'release',
          'keyId': 'release-a',
          'fingerprint': signerFingerprint,
        },
      }));
    _sign(claim, signer.privateKey, 'codex-agent-product-v1');
    final compatibility = RuntimeCompatibility.load();
    Map<String, Object?> verify([List<int>? trustedRoot]) =>
        verifyExternalRuntimeReleaseEvidence(
          library,
          library,
          compatibility,
          currentClassifier(),
          trustedRootForTesting: trustedRoot ?? root.public,
        );

    expect(verify()['runtimeLibrarySha256'], runtimeFileSha256(library));
    releaseKey.writeAsBytesSync(List<int>.filled(4097, 0x41));
    expect(
      () => verify(),
      throwsA(isA<CodexException>().having(
        (error) => error.message,
        'message',
        contains('has invalid size'),
      )),
    );
    releaseKey.writeAsBytesSync(signer.public);
    expect(verify()['runtimeLibrarySha256'], runtimeFileSha256(library));
    final originalClaim = claim.readAsStringSync();
    for (final nested in const [false, true]) {
      final altered = jsonDecode(originalClaim) as Map<String, Object?>;
      if (nested) {
        (altered['runtimeIdentity'] as Map<String, Object?>)['schemaVersion'] =
            1.0;
      } else {
        altered['schemaVersion'] = 1.0;
      }
      claim.writeAsStringSync(_canonicalJson(altered));
      expect(
        () => verify(),
        throwsA(isA<CodexException>().having(
          (error) => error.message,
          'message',
          contains('not canonical JSON'),
        )),
      );
    }
    claim.writeAsStringSync(originalClaim);
    expect(
      () => verify(signer.public),
      throwsA(isA<CodexException>()),
    );
    library.writeAsStringSync('changed runtime bytes');
    expect(() => verify(), throwsA(isA<CodexException>()));
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
    if (Platform.isWindows) return;
    final target = currentClassifier();
    final library = await _compileLibrary(
      temporary,
      'identity-first',
      identity: _identity(target, componentId: _digestA),
      abiVersion: requiredAbiVersion,
      requireIdentityBeforeAbi: true,
    );

    final root = _testKey(temporary, 'identity-root');
    final signer = _testKey(temporary, 'identity-signer');
    _writeSignedEvidence(
        library, root, signer, _identity(target, componentId: _digestA));
    final result = await _runIsolated(temporary, root.public, '''
import 'dart:ffi';
import 'package:codex_agent/src/ffi.dart';
void main(List<String> arguments) {
  final marker = authenticatedRuntimeLibraryForTesting(arguments.single)
      .lookupFunction<Int32 Function(), int Function()>('codex_agent_test_marker')();
  print(marker);
}
''', [library.path]);
    expect(result.exitCode, 0, reason: '${result.stdout}\n${result.stderr}');
    expect((result.stdout as String).trim(), '1');
  });

  test('dynamic open remains bound to the authenticated private file',
      () async {
    if (Platform.isWindows) return;
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
    final root = _testKey(temporary, 'swap-root');
    final signer = _testKey(temporary, 'swap-signer');
    _writeSignedEvidence(
        verified, root, signer, _identity(target, componentId: _digestA));
    final result = await _runIsolated(temporary, root.public, '''
import 'dart:ffi';
import 'dart:io';
import 'package:codex_agent/src/ffi.dart';
void main(List<String> arguments) {
  var blocked = false;
  final library = authenticatedRuntimeLibraryForTesting(
    arguments[0],
    beforeDynamicOpen: (snapshot) {
      try {
        if (snapshot.existsSync()) snapshot.renameSync('\${snapshot.path}.verified');
        File(arguments[1]).copySync(snapshot.path);
      } on FileSystemException {
        blocked = true;
      }
    },
  );
  final marker = library.lookupFunction<Int32 Function(), int Function()>(
      'codex_agent_test_marker')();
  print('\$marker,\$blocked');
}
''', [verified.path, malicious.path]);
    expect(result.exitCode, 0, reason: '${result.stdout}\n${result.stderr}');
    expect((result.stdout as String).trim(),
        Platform.isLinux ? '1,false' : '1,true');
  });

  test('child-process load leaves no owned Runtime snapshot behind', () async {
    if (Platform.isWindows) return;
    final target = currentClassifier();
    final library = await _compileLibrary(
      temporary,
      'child-runtime',
      identity: _identity(target, componentId: _digestA),
      abiVersion: requiredAbiVersion,
    );
    final root = _testKey(temporary, 'cleanup-root');
    final signer = _testKey(temporary, 'cleanup-signer');
    _writeSignedEvidence(
        library, root, signer, _identity(target, componentId: _digestA));
    final before = _runtimeSnapshots();
    final result = await _runIsolated(temporary, root.public, '''
import 'package:codex_agent/src/ffi.dart';
void main(List<String> arguments) {
  authenticatedRuntimeLibraryForTesting(arguments.single);
}
''', [library.path]);
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
  expect(result.exitCode, 0, reason: '${result.stderr}');
  final parts = File('$path.pub').readAsStringSync().split(' ');
  return (privateKey: path, public: ascii.encode('${parts[0]} ${parts[1]}\n'));
}

String _digest(List<int> bytes) => 'sha256:${crypto.sha256.convert(bytes)}';

String _fingerprint(List<int> public) =>
    _digest(base64.decode(ascii.decode(public).split(' ')[1].trim()));

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
  expect(result.exitCode, 0, reason: '${result.stderr}');
  File('${manifest.path}.sig').renameSync(
      '${manifest.parent.path}/${manifest.uri.pathSegments.last.replaceAll('.json', '.sig')}');
}

void _writeSignedEvidence(
  File library,
  ({String privateKey, List<int> public}) root,
  ({String privateKey, List<int> public}) signer,
  String identity,
) {
  final evidence = Directory('${library.path}.evidence')..createSync();
  final keys = Directory('${evidence.path}/keys')..createSync();
  File('${keys.path}/release-a.pub').writeAsBytesSync(signer.public);
  final fingerprint = _fingerprint(signer.public);
  final keyring = File('${evidence.path}/release-keyring.json')
    ..writeAsStringSync(_canonicalJson({
      'schemaVersion': 1,
      'namespace': 'codex-agent-product-v1',
      'algorithm': 'ssh-ed25519',
      'trustDomain': 'release',
      'activeKey': {'keyId': 'release-a', 'fingerprint': fingerprint},
      'retiredKeys': <Object>[],
    }));
  final delegation = File('${evidence.path}/root-delegation.json')
    ..writeAsStringSync(_canonicalJson({
      'schemaVersion': 1,
      'kind': 'sdk-runtime-release-keyring-delegation',
      'scope': 'desktop-runtime-library',
      'rootFingerprint': _fingerprint(root.public),
      'keyringSha256': _digest(keyring.readAsBytesSync()),
    }));
  _sign(delegation, root.privateKey, 'codex-agent-sdk-runtime-root-v1');
  final claim = File('${evidence.path}/runtime-library-authorization.json')
    ..writeAsStringSync(_canonicalJson({
      'schemaVersion': 1,
      'kind': 'desktop-runtime-library-authorization',
      'runtimeVersion': '0.8.0',
      'runtimeIdentity': jsonDecode(identity),
      'runtimeLibrarySha256': runtimeFileSha256(library),
      'variantBundleSha256': _digestA,
      'variantManifestSha256': _digestA,
      'aggregateManifestSha256': _digestA,
      'variantAttestationSha256': _digestA,
      'aggregateAttestationSha256': _digestA,
      'signing': {
        'algorithm': 'ssh-ed25519',
        'namespace': 'codex-agent-product-v1',
        'trustDomain': 'release',
        'keyId': 'release-a',
        'fingerprint': fingerprint,
      },
    }));
  _sign(claim, signer.privateKey, 'codex-agent-product-v1');
}

Future<ProcessResult> _runIsolated(
  Directory temporary,
  List<int> rootKey,
  String source,
  List<String> arguments,
) async {
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
  final configFile = File('${temporary.path}/package_config.json')
    ..writeAsStringSync(jsonEncode(configuration));
  final script = File('${temporary.path}/isolated_test.dart')
    ..writeAsStringSync(source);
  return Process.run(Platform.resolvedExecutable, [
    '--packages=${configFile.path}',
    script.path,
    ...arguments,
  ]);
}

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

String get _wrongContractDigest =>
    RuntimeCompatibility.load().contractDigest == _digestA
        ? _digestB
        : _digestA;

String _identity(String target,
        {required String componentId, String version = '0.8.0'}) =>
    jsonEncode({
      'appServerVersion': '0.149.0',
      'buildInputDigest': _digestB,
      'cAbiVersion': '1.13.0',
      'componentId': componentId,
      'contractComponentDigest': _digestA,
      'contractDigest': RuntimeCompatibility.load().contractDigest,
      'runtimeCompatibilityVersion': version,
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
