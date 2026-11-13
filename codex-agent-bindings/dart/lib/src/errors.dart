enum CodexStatus {
  ok(0),
  invalidArgument(1),
  outOfMemory(2),
  staleHandle(3),
  wrongHandleType(4),
  wrongContext(5),
  busy(6),
  cancelled(7),
  internalError(8),
  bufferTooSmall(9),
  unsupportedAbi(10),
  closed(11),
  wouldDeadlock(12),
  notReady(13),
  operationFailed(14);

  const CodexStatus(this.value);
  final int value;

  static CodexStatus fromValue(int value) => values.firstWhere(
        (candidate) => candidate.value == value,
        orElse: () => throw CodexNativeException(
          value,
          'native C SDK returned an unknown status',
        ),
      );
}

final class CodexFailure {
  const CodexFailure({
    required this.code,
    required this.message,
    required this.isRecoverable,
  });

  final String code;
  final String message;
  final bool isRecoverable;

  @override
  String toString() => '$code: $message';
}

class CodexException implements Exception {
  const CodexException(this.message);
  final String message;

  @override
  String toString() => 'CodexException: $message';
}

final class CodexNativeException extends CodexException {
  const CodexNativeException(this.statusValue, super.message);
  final int statusValue;

  CodexStatus? get status {
    for (final candidate in CodexStatus.values) {
      if (candidate.value == statusValue) return candidate;
    }
    return null;
  }

  @override
  String toString() => 'CodexNativeException($statusValue): $message';
}

final class CodexOperationException extends CodexException {
  CodexOperationException(this.operationStatus, this.failure)
      : super('operation failed with ${operationStatus.name}');

  final CodexStatus operationStatus;
  final CodexFailure? failure;

  @override
  String toString() => failure == null
      ? 'CodexOperationException: ${operationStatus.name}'
      : 'CodexOperationException: ${operationStatus.name}: $failure';
}

final class CodexClosedException extends CodexException {
  const CodexClosedException(super.message);
}

final class CodexUnsupportedPlatformException extends CodexException {
  const CodexUnsupportedPlatformException(super.message);
}
