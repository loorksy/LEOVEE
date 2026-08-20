import 'package:flutter_test/flutter_test.dart';

import 'package:babyclaw_manager/utils/pin_hasher.dart';

void main() {
  test('accepts the configured PIN hash and rejects others', () {
    expect(verifyPin('2026'), isTrue);
    expect(verifyPin('0000'), isFalse);
    expect(verifyPin('0096399'), isFalse);
    expect(sha256Hex('2026'), kPinSha256);
  });
}
