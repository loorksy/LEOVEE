import 'dart:convert';

import 'package:crypto/crypto.dart';

/// SHA-256 of the lock-screen PIN. The plaintext PIN is not stored in source.
const String kPinSha256 =
    '158a323a7ba44870f23d96f1516dd70aa48e9a72db4ebb026b0a89e212a208ab';

String sha256Hex(String value) {
  return sha256.convert(utf8.encode(value)).toString();
}

bool verifyPin(String pin) {
  return sha256Hex(pin.trim()) == kPinSha256;
}
