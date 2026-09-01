import 'dart:convert';
import 'dart:io';
import 'dart:isolate';

import 'package:crypto/crypto.dart' as crypto;

import 'errors.dart';

final class RuntimeCompatibility {
  RuntimeCompatibility._({
    required this.contractDigest,
    required _VersionRange compatibleRuntimeRange,
    required this.requiredIdentitySchema,
    required this.requiredAbiMajor,
    required this.minimumAbiMinor,
    required this.embeddedVariants,
  }) : _compatibleRuntimeRange = compatibleRuntimeRange;

  final String contractDigest;
  final _VersionRange _compatibleRuntimeRange;
  final int requiredIdentitySchema;
  final int requiredAbiMajor;
  final int minimumAbiMinor;
  final Map<String, EmbeddedRuntimeVariant> embeddedVariants;

  bool supportsRuntimeVersion(String version) =>
      _compatibleRuntimeRange.contains(version);

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
      final fileMode = Process.runSync('chmod', ['400', snapshot.path]);
      final directoryMode = Process.runSync(
        'chmod',
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
  if (!Platform.isWindows) Process.runSync('chmod', ['700', directory.path]);
  directory.deleteSync(recursive: true);
}

String _fileSha256(File file) =>
    'sha256:${crypto.sha256.convert(file.readAsBytesSync())}';

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
