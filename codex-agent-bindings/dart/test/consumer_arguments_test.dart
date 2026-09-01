import 'dart:io';

import 'package:test/test.dart';

import '../consumer/bin/host_smoke.dart' show runtimeOverrideFromArguments;

void main() {
  test('installed Host smoke selects default or one absolute override', () {
    expect(runtimeOverrideFromArguments(const []), isNull);
    final absolute = '${Directory.systemTemp.absolute.path}'
        '${Platform.pathSeparator}libcodex_agent';
    expect(runtimeOverrideFromArguments([absolute]), absolute);

    for (final arguments in const [
      [''],
      ['relative-runtime'],
      ['first', 'second'],
    ]) {
      expect(
        () => runtimeOverrideFromArguments(arguments),
        throwsA(isA<FormatException>()),
      );
    }
  });
}
