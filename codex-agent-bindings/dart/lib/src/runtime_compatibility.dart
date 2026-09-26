import 'dart:convert';
import 'dart:io';
import 'dart:isolate';
import 'dart:typed_data';

import 'package:crypto/crypto.dart' as crypto;

import 'errors.dart';

final class RuntimeCompatibility {
  RuntimeCompatibility._({
    required this.contractDigest,
    required _VersionRange compatibleRuntimeRange,
    required _VersionRange compatibleReleaseRange,
    required this.requiredIdentitySchema,
    required this.requiredAbiMajor,
    required this.minimumAbiMinor,
    required this.embeddedVariants,
  })  : _compatibleRuntimeRange = compatibleRuntimeRange,
        _compatibleReleaseRange = compatibleReleaseRange;

  final String contractDigest;
  final _VersionRange _compatibleRuntimeRange;
  final _VersionRange _compatibleReleaseRange;
  final int requiredIdentitySchema;
  final int requiredAbiMajor;
  final int minimumAbiMinor;
  final Map<String, EmbeddedRuntimeVariant> embeddedVariants;

  bool supportsRuntimeVersion(String version) =>
      _compatibleRuntimeRange.contains(version);

  bool supportsReleaseVersion(String version) =>
      _compatibleReleaseRange.contains(version);

  static RuntimeCompatibility load() {
    final uri = Isolate.resolvePackageUriSync(
      Uri.parse('package:codex_agent/src/native/sdk-compatibility.json'),
    );
    if (uri == null || uri.scheme != 'file') {
      throw const CodexException(
        'Codex Agent SDK compatibility declaration is absent',
      );
    }
    return read(File.fromUri(uri));
  }

  static RuntimeCompatibility read(File file) {
    requireAbsoluteRegularFile(file, 'SDK compatibility declaration');
    final bytes = file.readAsBytesSync();
    Object? decoded;
    try {
      decoded = jsonDecode(utf8.decode(bytes, allowMalformed: false));
    } on Object catch (error) {
      throw CodexException('invalid SDK compatibility declaration: $error');
    }
    if (!_hasRecursivelySortedKeys(decoded) ||
        '${jsonEncode(decoded)}\n' != utf8.decode(bytes)) {
      throw const CodexException(
        'SDK compatibility declaration is not canonical JSON',
      );
    }
    final root = _object(decoded, 'SDK compatibility', const {
      'schemaVersion',
      'sdkVersion',
      'contract',
      'runtime',
      'platformRuntime',
    });
    if (_integer(root['schemaVersion'], 'schemaVersion') != 1) {
      throw const CodexException('unsupported SDK compatibility schema');
    }
    _semver(root['sdkVersion'], 'sdkVersion');
    final contract = _object(root['contract'], 'contract', const {
      'version',
      'digest',
    });
    _semver(contract['version'], 'contract.version');
    final contractDigest = _sha256(contract['digest'], 'contract.digest');
    final runtime = _object(root['runtime'], 'runtime', const {
      'compatibleReleaseRange',
      'compatibleRuntimeCompatibilityRange',
      'requiredIdentitySchema',
      'requiredContractDigest',
      'requiredAbiMajor',
      'minimumAbiMinor',
      'defaultRuntimeVersion',
      'defaultManifestSha256',
      'embeddedVariants',
    });
    final releaseRange = _VersionRange.parse(
      runtime['compatibleReleaseRange'],
      'runtime.compatibleReleaseRange',
    );
    final compatibilityRange = _VersionRange.parse(
      runtime['compatibleRuntimeCompatibilityRange'],
      'runtime.compatibleRuntimeCompatibilityRange',
    );
    final identitySchema = _integer(
      runtime['requiredIdentitySchema'],
      'requiredIdentitySchema',
    );
    final abiMajor = _integer(runtime['requiredAbiMajor'], 'requiredAbiMajor');
    final abiMinor = _integer(runtime['minimumAbiMinor'], 'minimumAbiMinor');
    if (identitySchema != 1 || abiMajor != 1 || abiMinor < 13) {
      throw const CodexException(
        'unsupported SDK Runtime identity or ABI requirement',
      );
    }
    if (_sha256(runtime['requiredContractDigest'], 'requiredContractDigest') !=
        contractDigest) {
      throw const CodexException('SDK compatibility Contract digest mismatch');
    }
    final defaultRuntimeVersion = _semver(
      runtime['defaultRuntimeVersion'],
      'defaultRuntimeVersion',
    );
    if (!releaseRange.contains(defaultRuntimeVersion)) {
      throw const CodexException(
        'default Runtime version is outside the compatible release range',
      );
    }
    _sha256(runtime['defaultManifestSha256'], 'defaultManifestSha256');
    final variants = <String, EmbeddedRuntimeVariant>{};
    final componentIds = <String>{};
    final manifestDigests = <String>{};
    final array = runtime['embeddedVariants'];
    if (array is! List<Object?> || array.length != 5) {
      throw const CodexException(
        'SDK compatibility must contain five embedded Runtime variants',
      );
    }
    for (var index = 0; index < array.length; index++) {
      final value = _object(array[index], 'embeddedVariants[$index]', const {
        'target',
        'componentId',
        'bundleSha256',
        'manifestSha256',
        'runtimeLibrarySha256',
      });
      final target = _string(
        value['target'],
        'embeddedVariants[$index].target',
      );
      if (!_targets.contains(target) || variants.containsKey(target)) {
        throw const CodexException(
          'SDK compatibility embedded Runtime targets are inexact',
        );
      }
      final componentId = _sha256(value['componentId'], 'componentId');
      final manifestDigest = _sha256(
        value['manifestSha256'],
        'manifestSha256',
      );
      if (!componentIds.add(componentId) ||
          !manifestDigests.add(manifestDigest)) {
        throw const CodexException(
          'SDK compatibility embedded Runtime identities are not unique',
        );
      }
      variants[target] = EmbeddedRuntimeVariant(
        componentId: componentId,
        librarySha256: _sha256(
          value['runtimeLibrarySha256'],
          'runtimeLibrarySha256',
        ),
      );
      _sha256(value['bundleSha256'], 'bundleSha256');
    }
    if (variants.keys.join(',') != (_targets.toList()..sort()).join(',')) {
      throw const CodexException(
        'SDK compatibility embedded Runtime variants are not canonical',
      );
    }
    final platform = _object(root['platformRuntime'], 'platformRuntime', const {
      'android',
      'ios',
    });
    for (final name in const ['android', 'ios']) {
      final value = _object(platform[name], 'platformRuntime.$name', const {
        'owner',
        'desktopRuntimeApplicable',
      });
      if (value['owner'] != 'sdk' ||
          value['desktopRuntimeApplicable'] != false) {
        throw CodexException('invalid $name Runtime ownership declaration');
      }
    }
    return RuntimeCompatibility._(
      contractDigest: contractDigest,
      compatibleRuntimeRange: compatibilityRange,
      compatibleReleaseRange: releaseRange,
      requiredIdentitySchema: identitySchema,
      requiredAbiMajor: abiMajor,
      minimumAbiMinor: abiMinor,
      embeddedVariants: Map.unmodifiable(variants),
    );
  }

  int verifyRuntimeIdentity(
    String json,
    String target, {
    required bool embedded,
    int? actualAbiVersion,
  }) {
    try {
      final decoded = jsonDecode(json);
      if (!_hasRecursivelySortedKeys(decoded) || jsonEncode(decoded) != json) {
        throw const CodexException('Runtime identity is not canonical JSON');
      }
      final identity = _object(decoded, 'Runtime identity', const {
        'schemaVersion',
        'componentId',
        'runtimeCompatibilityVersion',
        'contractDigest',
        'contractComponentDigest',
        'cAbiVersion',
        'target',
        'appServerVersion',
        'buildInputDigest',
      });
      final variant = embeddedVariants[target];
      if (variant == null) {
        throw CodexException('SDK does not support Runtime target $target');
      }
      final schema = _integer(
        identity['schemaVersion'],
        'identity.schemaVersion',
      );
      final component = _sha256(
        identity['componentId'],
        'identity.componentId',
      );
      final runtimeVersion = _semver(
        identity['runtimeCompatibilityVersion'],
        'identity.runtimeVersion',
      );
      final contract = _sha256(
        identity['contractDigest'],
        'identity.contractDigest',
      );
      _sha256(
        identity['contractComponentDigest'],
        'identity.contractComponentDigest',
      );
      final abi = _Semver.parse(
        identity['cAbiVersion'],
        'identity.cAbiVersion',
      );
      if (abi.major > 0xff || abi.minor > 0xff || abi.patch > 0xffff) {
        throw const CodexException(
          'Runtime identity ABI exceeds the packed ABI field widths',
        );
      }
      final packedAbi = (abi.major << 24) | (abi.minor << 16) | abi.patch;
      _semver(identity['appServerVersion'], 'identity.appServerVersion');
      _sha256(identity['buildInputDigest'], 'identity.buildInputDigest');
      if (schema != requiredIdentitySchema ||
          identity['target'] != target ||
          contract != contractDigest ||
          abi.major != requiredAbiMajor ||
          abi.minor < minimumAbiMinor ||
          (actualAbiVersion != null && actualAbiVersion != packedAbi) ||
          !supportsRuntimeVersion(runtimeVersion) ||
          (embedded && component != variant.componentId)) {
        throw const CodexException('incompatible Codex Agent Runtime identity');
      }
      return packedAbi;
    } on CodexException {
      rethrow;
    } on Object catch (error) {
      throw CodexException('invalid Codex Agent Runtime identity: $error');
    }
  }
}

final class EmbeddedRuntimeVariant {
  const EmbeddedRuntimeVariant({
    required this.componentId,
    required this.librarySha256,
  });

  final String componentId;
  final String librarySha256;
}

String runtimeFileSha256(File file) {
  requireAbsoluteRegularFile(file, 'Codex Agent Runtime');
  return _fileSha256(file);
}

Map<String, Object?> verifyExternalRuntimeReleaseEvidence(
  File snapshot,
  File selectedLibrary,
  RuntimeCompatibility compatibility,
  String target, {
  List<int>? trustedRootForTesting,
}) {
  final rootKey = trustedRootForTesting ?? _sdkRuntimeRoot();
  final rootFingerprint = _publicKeyFingerprint(rootKey);
  final evidence = Directory('${selectedLibrary.path}.evidence');
  final keyringBytes = _evidenceFile(evidence, 'release-keyring.json');
  final delegationBytes = _evidenceFile(evidence, 'root-delegation.json');
  final delegation = _canonicalEvidence(delegationBytes, 'root delegation');
  _object(delegation, 'root delegation', const {
    'schemaVersion',
    'kind',
    'scope',
    'rootFingerprint',
    'keyringSha256',
  });
  if (delegation['schemaVersion'] != 1 ||
      delegation['kind'] != 'sdk-runtime-release-keyring-delegation' ||
      delegation['scope'] != 'desktop-runtime-library' ||
      _sha256(delegation['rootFingerprint'], 'root fingerprint') !=
          rootFingerprint ||
      _sha256(delegation['keyringSha256'], 'keyring digest') !=
          _digestBytes(keyringBytes)) {
    throw const CodexException('external Runtime root delegation is invalid');
  }
  _verifySshsig(
    delegationBytes,
    _evidenceFile(evidence, 'root-delegation.sig'),
    rootKey,
    'codex-agent-sdk-runtime-root-v1',
    'codex-agent-sdk-runtime-root',
  );

  final keyring = _canonicalEvidence(keyringBytes, 'release keyring');
  _object(keyring, 'release keyring', const {
    'schemaVersion',
    'namespace',
    'algorithm',
    'trustDomain',
    'activeKey',
    'retiredKeys',
  });
  if (keyring['schemaVersion'] != 1 ||
      keyring['namespace'] != 'codex-agent-product-v1' ||
      keyring['algorithm'] != 'ssh-ed25519' ||
      keyring['trustDomain'] != 'release') {
    throw const CodexException('external Runtime release keyring is invalid');
  }
  final records = <Map<String, Object?>>[];
  if (keyring['activeKey'] != null) {
    records.add(_keyRecord(keyring['activeKey']));
  }
  final retired = keyring['retiredKeys'];
  if (retired is! List<Object?>) {
    throw const CodexException('external Runtime retired keys are invalid');
  }
  records.addAll(retired.map(_keyRecord));
  final ids = records.map((record) => record['keyId'] as String).toList();
  final retiredIds = ids.skip(keyring['activeKey'] == null ? 0 : 1).toList();
  if (retiredIds.join(',') != (retiredIds.toList()..sort()).join(',') ||
      ids.toSet().length != ids.length ||
      records.map((record) => record['fingerprint']).toSet().length !=
          records.length) {
    throw const CodexException('external Runtime release keys are not unique');
  }
  final keys = <String, List<int>>{};
  for (final record in records) {
    final id = record['keyId'] as String;
    final bytes = _evidenceFile(evidence, 'keys/$id.pub', maxBytes: 4096);
    if (_publicKeyFingerprint(bytes) != record['fingerprint']) {
      throw const CodexException(
          'external Runtime release key differs from keyring');
    }
    keys[id] = bytes;
  }

  final claimBytes =
      _evidenceFile(evidence, 'runtime-library-authorization.json');
  final claim = _canonicalEvidence(claimBytes, 'Runtime authorization');
  _object(claim, 'Runtime authorization', const {
    'schemaVersion',
    'kind',
    'runtimeVersion',
    'runtimeIdentity',
    'runtimeLibrarySha256',
    'variantBundleSha256',
    'variantManifestSha256',
    'aggregateManifestSha256',
    'variantAttestationSha256',
    'aggregateAttestationSha256',
    'signing',
  });
  if (claim['schemaVersion'] != 1 ||
      claim['kind'] != 'desktop-runtime-library-authorization' ||
      !compatibility.supportsReleaseVersion(
          _semver(claim['runtimeVersion'], 'authorized Runtime version'))) {
    throw const CodexException('external Runtime release is incompatible');
  }
  final identity =
      _object(claim['runtimeIdentity'], 'authorized identity', const {
    'schemaVersion',
    'componentId',
    'runtimeCompatibilityVersion',
    'contractDigest',
    'contractComponentDigest',
    'cAbiVersion',
    'target',
    'appServerVersion',
    'buildInputDigest',
  });
  compatibility.verifyRuntimeIdentity(jsonEncode(identity), target,
      embedded: false);
  for (final field in const [
    'runtimeLibrarySha256',
    'variantBundleSha256',
    'variantManifestSha256',
    'aggregateManifestSha256',
    'variantAttestationSha256',
    'aggregateAttestationSha256',
  ]) {
    _sha256(claim[field], field);
  }
  final signing = _object(claim['signing'], 'authorization signing', const {
    'algorithm',
    'namespace',
    'trustDomain',
    'keyId',
    'fingerprint',
  });
  if (signing['algorithm'] != 'ssh-ed25519' ||
      signing['namespace'] != 'codex-agent-product-v1' ||
      signing['trustDomain'] != 'release' ||
      !keys.containsKey(signing['keyId']) ||
      records.singleWhere(
              (record) => record['keyId'] == signing['keyId'])['fingerprint'] !=
          _sha256(signing['fingerprint'], 'signer fingerprint')) {
    throw const CodexException(
        'external Runtime release signer is not delegated');
  }
  _verifySshsig(
    claimBytes,
    _evidenceFile(evidence, 'runtime-library-authorization.sig'),
    keys[signing['keyId']]!,
    'codex-agent-product-v1',
    'codex-agent-product',
  );
  final expected = <String>{
    'release-keyring.json',
    'root-delegation.json',
    'root-delegation.sig',
    'runtime-library-authorization.json',
    'runtime-library-authorization.sig',
    for (final id in ids) 'keys/$id.pub',
  };
  _requireExactEvidenceFiles(evidence, expected);
  if (runtimeFileSha256(snapshot) != claim['runtimeLibrarySha256']) {
    throw const CodexException(
      'external Runtime snapshot differs from signed authorization',
    );
  }
  return claim;
}

List<int> _sdkRuntimeRoot() {
  final uri = Isolate.resolvePackageUriSync(
    Uri.parse('package:codex_agent/src/native/sdk-runtime-root.pub'),
  );
  if (uri == null || uri.scheme != 'file') {
    throw const CodexException(
        'external Runtime release evidence is unavailable: SDK root is absent');
  }
  final file = File.fromUri(uri);
  if (!file.existsSync()) {
    throw const CodexException(
        'external Runtime release evidence is unavailable: SDK root is absent');
  }
  requireAbsoluteRegularFile(file, 'SDK Runtime root');
  return file.readAsBytesSync();
}

Map<String, Object?> _keyRecord(Object? value) {
  final record = _object(value, 'release key', const {'keyId', 'fingerprint'});
  final id = record['keyId'];
  if (id is! String || !RegExp(r'^[a-z0-9][a-z0-9-]{0,63}$').hasMatch(id)) {
    throw const CodexException('external Runtime release key ID is invalid');
  }
  _sha256(record['fingerprint'], 'release key fingerprint');
  return record;
}

List<int> _evidenceFile(Directory root, String name,
    {int maxBytes = 1024 * 1024}) {
  final file = File('${root.path}${Platform.pathSeparator}$name');
  requireAbsoluteRegularFile(file, 'external Runtime evidence $name');
  final opened = file.openSync(mode: FileMode.read);
  try {
    final length = opened.lengthSync();
    if (length <= 0 || length > maxBytes) {
      throw CodexException('external Runtime evidence $name has invalid size');
    }
    // Bound the read on the opened file, even if the pathname changes after inspection.
    final bytes = opened.readSync(length);
    if (bytes.length != length || opened.lengthSync() != length) {
      throw CodexException(
          'external Runtime evidence $name changed while reading');
    }
    requireAbsoluteRegularFile(file, 'external Runtime evidence $name');
    return bytes;
  } finally {
    opened.closeSync();
  }
}

Map<String, Object?> _canonicalEvidence(List<int> bytes, String label) {
  late final Object? decoded;
  try {
    decoded = jsonDecode(utf8.decode(bytes, allowMalformed: false));
  } on Object {
    throw CodexException('$label is not UTF-8 JSON');
  }
  if (decoded is! Map<String, Object?> ||
      _containsFloatingPoint(decoded) ||
      !_hasRecursivelySortedKeys(decoded) ||
      utf8.decode(bytes) != '${jsonEncode(decoded)}\n') {
    throw CodexException('$label is not canonical JSON');
  }
  return decoded;
}

bool _containsFloatingPoint(Object? value) => switch (value) {
      double _ => true,
      List<Object?> items => items.any(_containsFloatingPoint),
      Map<String, Object?> fields => fields.values.any(_containsFloatingPoint),
      _ => false,
    };

String _digestBytes(List<int> bytes) =>
    'sha256:${crypto.sha256.convert(bytes)}';

String _publicKeyFingerprint(List<int> bytes) {
  late final String line;
  try {
    line = ascii.decode(bytes);
  } on Object {
    throw const CodexException('external Runtime public key is not ASCII');
  }
  final match =
      RegExp(r'^ssh-ed25519 ([A-Za-z0-9+/]+={0,2})\n$').firstMatch(line);
  if (match == null) {
    throw const CodexException('external Runtime public key is not canonical');
  }
  late final List<int> blob;
  try {
    blob = base64.decode(match.group(1)!);
  } on Object {
    throw const CodexException('external Runtime public key is malformed');
  }
  if (base64.encode(blob) != match.group(1) || blob.length != 51) {
    throw const CodexException('external Runtime public key is malformed');
  }
  final data = ByteData.sublistView(Uint8List.fromList(blob));
  if (data.getUint32(0) != 11 ||
      ascii.decode(blob.sublist(4, 15)) != 'ssh-ed25519' ||
      data.getUint32(15) != 32) {
    throw const CodexException('external Runtime public key is malformed');
  }
  return _digestBytes(blob);
}

void _verifySshsig(List<int> message, List<int> signature, List<int> key,
    String namespace, String principal) {
  final armor = ascii.decode(signature, allowInvalid: true);
  const header = '-----BEGIN SSH SIGNATURE-----\n';
  const footer = '-----END SSH SIGNATURE-----\n';
  if (!armor.startsWith(header) || !armor.endsWith(footer)) {
    throw const CodexException('external Runtime signature armor is invalid');
  }
  final lines = armor
      .substring(header.length, armor.length - footer.length)
      .split('\n')
    ..removeLast();
  if (lines.isEmpty ||
      lines.any((line) => line.isEmpty || line.length > 70) ||
      lines.take(lines.length - 1).any((line) => line.length != 70)) {
    throw const CodexException('external Runtime signature armor is invalid');
  }
  final encoded = lines.join();
  late final List<int> blob;
  try {
    blob = base64.decode(encoded);
  } on Object {
    throw const CodexException('external Runtime signature armor is invalid');
  }
  if (base64.encode(blob) != encoded ||
      ascii.decode(blob.take(6).toList(), allowInvalid: true) != 'SSHSIG') {
    throw const CodexException('external Runtime signature armor is invalid');
  }
  if (!supportsExternalRuntimeSignatureVerifier(Platform.operatingSystem)) {
    throw const CodexException(
        'external Runtime SSHSIG verification is unavailable on Windows');
  }
  final directory = Directory.systemTemp.createTempSync('codex-agent-sshsig-');
  try {
    final allowed = File('${directory.path}/allowed-signers')
      ..writeAsBytesSync([...ascii.encode('$principal '), ...key]);
    final detached = File('${directory.path}/signature.sig')
      ..writeAsBytesSync(signature);
    final input = File('${directory.path}/message')..writeAsBytesSync(message);
    const script =
        'exec /usr/bin/ssh-keygen -Y verify -f "\$1" -I "\$2" -n "\$3" -s "\$4" < "\$5"';
    final result = Process.runSync('/bin/sh', [
      '-c',
      script,
      'sh',
      allowed.path,
      principal,
      namespace,
      detached.path,
      input.path,
    ]);
    if (result.exitCode != 0) {
      throw const CodexException('external Runtime SSHSIG verification failed');
    }
  } on ProcessException {
    throw const CodexException(
        'external Runtime SSHSIG verifier is unavailable');
  } finally {
    directory.deleteSync(recursive: true);
  }
}

bool supportsExternalRuntimeSignatureVerifier(String operatingSystem) =>
    operatingSystem == 'macos' || operatingSystem == 'linux';

void _requireExactEvidenceFiles(Directory root, Set<String> expected) {
  if (!root.existsSync()) {
    throw const CodexException('external Runtime evidence directory is absent');
  }
  final actual = <String>{};
  for (final entity in root.listSync(recursive: true, followLinks: false)) {
    final relative = entity.path
        .substring(root.path.length + 1)
        .replaceAll(Platform.pathSeparator, '/');
    if (entity is Directory) {
      if (relative != 'keys') {
        throw const CodexException(
            'external Runtime evidence contains extra directories');
      }
    } else if (entity is File) {
      actual.add(relative);
    } else {
      throw const CodexException(
          'external Runtime evidence contains unsafe files');
    }
  }
  if (actual.length != expected.length || !actual.containsAll(expected)) {
    throw const CodexException(
        'external Runtime evidence contains extra or missing files');
  }
}

final class RuntimeLibrarySnapshot {
  const RuntimeLibrarySnapshot._(this.file, this.digest, this.directory);

  final File file;
  final String digest;
  final Directory? directory;

  void verify() {
    requireAbsoluteRegularFile(file, 'Runtime snapshot');
    if (_fileSha256(file) != digest) {
      throw const CodexException('Codex Agent Runtime snapshot changed');
    }
  }

  void verifyDescriptor(File descriptor) {
    if (_fileSha256(descriptor) != digest) {
      throw const CodexException('Codex Agent Runtime snapshot changed');
    }
  }

  void removeAfterLoad() {
    final ownedDirectory = directory;
    if (ownedDirectory != null && ownedDirectory.existsSync()) {
      _removeOwnedSnapshot(ownedDirectory);
    }
  }
}

RuntimeLibrarySnapshot snapshotRuntimeLibrary(
  File source,
  RuntimeCompatibility compatibility,
  String target, {
  required bool embedded,
  void Function()? afterDescriptorRead,
}) {
  requireAbsoluteRegularFile(source, 'Codex Agent Runtime');
  final opened = source.openSync(mode: FileMode.read);
  late final List<int> bytes;
  try {
    final length = opened.lengthSync();
    if (length <= 0 || length > 512 * 1024 * 1024) {
      throw const CodexException('Codex Agent Runtime size is invalid');
    }
    bytes = opened.readSync(length);
    if (bytes.length != length) {
      throw const CodexException('Codex Agent Runtime read was incomplete');
    }
  } finally {
    opened.closeSync();
  }
  final digest = 'sha256:${crypto.sha256.convert(bytes)}';
  afterDescriptorRead?.call();
  requireAbsoluteRegularFile(source, 'Codex Agent Runtime');
  if (_fileSha256(source) != digest) {
    throw const CodexException(
        'Codex Agent Runtime changed while snapshotting');
  }
  final variant = compatibility.embeddedVariants[target];
  if (variant == null || (embedded && digest != variant.librarySha256)) {
    throw const CodexException('embedded Codex Agent Runtime digest mismatch');
  }

  // Windows holds loaded DLLs open until process exit. Loading the already
  // authenticated source under a non-write/non-delete sharing handle avoids
  // creating an undeletable snapshot directory in the first place.
  if (Platform.isWindows) {
    return RuntimeLibrarySnapshot._(source, digest, null);
  }

  final temporaryRoot = Directory(
    Directory.systemTemp.resolveSymbolicLinksSync(),
  );
  final directory = temporaryRoot.createTempSync(
    'codex-agent-runtime-snapshot-',
  );
  final snapshot = File(
      '${directory.path}${Platform.pathSeparator}${source.uri.pathSegments.last}');
  try {
    snapshot.writeAsBytesSync(bytes, flush: true);
    if (!Platform.isWindows) {
      final fileMode = Process.runSync('/bin/chmod', ['400', snapshot.path]);
      final directoryMode = Process.runSync(
        '/bin/chmod',
        [Platform.isMacOS ? '500' : '700', directory.path],
      );
      if (fileMode.exitCode != 0 || directoryMode.exitCode != 0) {
        throw const CodexException('Runtime snapshot permissions failed');
      }
    }
    final result = RuntimeLibrarySnapshot._(snapshot, digest, directory);
    result.verify();
    return result;
  } catch (_) {
    if (directory.existsSync()) {
      _removeOwnedSnapshot(directory);
    }
    rethrow;
  }
}

void _removeOwnedSnapshot(Directory directory) {
  if (!Platform.isWindows) {
    Process.runSync('/bin/chmod', ['700', directory.path]);
  }
  directory.deleteSync(recursive: true);
}

String _fileSha256(File file) {
  final opened = file.openSync(mode: FileMode.read);
  try {
    final length = opened.lengthSync();
    if (length <= 0 || length > 512 * 1024 * 1024) {
      throw const CodexException('Codex Agent Runtime size is invalid');
    }
    final digests = <crypto.Digest>[];
    final sink = crypto.sha256.startChunkedConversion(
      ChunkedConversionSink<crypto.Digest>.withCallback(digests.addAll),
    );
    var remaining = length;
    while (remaining > 0) {
      final bytes = opened.readSync(remaining < 65536 ? remaining : 65536);
      if (bytes.isEmpty) {
        throw const CodexException('Codex Agent Runtime read was incomplete');
      }
      sink.add(bytes);
      remaining -= bytes.length;
    }
    sink.close();
    if (opened.lengthSync() != length || digests.length != 1) {
      throw const CodexException('Codex Agent Runtime changed while hashing');
    }
    return 'sha256:${digests.single}';
  } finally {
    opened.closeSync();
  }
}

void requireAbsoluteRegularFile(File file, String label) {
  if (file.path.isEmpty || !file.isAbsolute || _hasDotSegment(file.path)) {
    throw CodexException('$label path must be a literal absolute path');
  }
  var path = file.path;
  if (FileSystemEntity.typeSync(path, followLinks: false) !=
      FileSystemEntityType.file) {
    throw CodexException('$label is absent or not a regular file: $path');
  }
  if (file.resolveSymbolicLinksSync() != path) {
    throw CodexException('$label path is not canonically spelled: $path');
  }
  while (true) {
    final parent = Directory(path).parent.path;
    if (parent == path) break;
    if (FileSystemEntity.typeSync(parent, followLinks: false) !=
        FileSystemEntityType.directory) {
      throw CodexException('$label has a symlinked or invalid parent: $parent');
    }
    path = parent;
  }
}

bool _hasDotSegment(String path) =>
    path.split(RegExp(r'[\\/]')).any((part) => part == '.' || part == '..');

bool _hasRecursivelySortedKeys(Object? value) {
  if (value is List<Object?>) return value.every(_hasRecursivelySortedKeys);
  if (value is! Map<String, Object?>) return true;
  final keys = value.keys.toList();
  final sorted = keys.toList()..sort();
  return keys.join('\u0000') == sorted.join('\u0000') &&
      value.values.every(_hasRecursivelySortedKeys);
}

Map<String, Object?> _object(Object? value, String label, Set<String> keys) {
  if (value is! Map<String, Object?> ||
      value.length != keys.length ||
      !value.keys.toSet().containsAll(keys)) {
    throw CodexException('$label has an inexact object schema');
  }
  return value;
}

String _string(Object? value, String label) {
  if (value is! String || value.isEmpty) {
    throw CodexException('$label must be a non-empty string');
  }
  return value;
}

String _sha256(Object? value, String label) {
  final text = _string(value, label);
  if (!RegExp(r'^sha256:[0-9a-f]{64}$').hasMatch(text)) {
    throw CodexException('$label must be a SHA-256 identity');
  }
  return text;
}

int _integer(Object? value, String label) {
  if (value is! int || value < 0) {
    throw CodexException('$label must be a non-negative integer');
  }
  return value;
}

String _semver(Object? value, String label) =>
    _Semver.parse(value, label).source;

final class _VersionRange {
  const _VersionRange(this.minimum, this.maximum);

  final _Semver minimum;
  final _Semver maximum;

  static _VersionRange parse(Object? value, String label) {
    final text = _string(value, label);
    final match =
        RegExp(r'^>=(\d+\.\d+\.\d+) <(\d+\.\d+\.\d+)$').firstMatch(text);
    if (match == null) throw CodexException('$label is not an exact range');
    final minimum = _Semver.parse(match.group(1), label);
    final maximum = _Semver.parse(match.group(2), label);
    if (minimum.compareTo(maximum) >= 0) {
      throw CodexException('$label is empty');
    }
    return _VersionRange(minimum, maximum);
  }

  bool contains(String value) {
    final version = _Semver.parse(value, 'Runtime compatibility version');
    return minimum.compareTo(version) <= 0 && version.compareTo(maximum) < 0;
  }
}

final class _Semver implements Comparable<_Semver> {
  const _Semver(this.source, this.major, this.minor, this.patch);

  final String source;
  final int major;
  final int minor;
  final int patch;

  static _Semver parse(Object? value, String label) {
    final text = _string(value, label);
    final match =
        RegExp(r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$').firstMatch(text);
    if (match == null) throw CodexException('$label must be stable SemVer');
    return _Semver(
      text,
      int.parse(match.group(1)!),
      int.parse(match.group(2)!),
      int.parse(match.group(3)!),
    );
  }

  @override
  int compareTo(_Semver other) {
    for (final difference in [
      major - other.major,
      minor - other.minor,
      patch - other.patch,
    ]) {
      if (difference != 0) return difference;
    }
    return 0;
  }
}

const _targets = {
  'linux-arm64',
  'linux-x64',
  'macos-arm64',
  'macos-x64',
  'windows-x64',
};
