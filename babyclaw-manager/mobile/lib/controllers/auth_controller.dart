import 'package:get/get.dart';

import '../utils/pin_hasher.dart';

class AuthController extends GetxController {
  final pin = ''.obs;
  final error = ''.obs;
  final unlocked = false.obs;

  void setPin(String value) {
    pin.value = value;
    if (error.isNotEmpty) error.value = '';
  }

  bool unlock() {
    if (verifyPin(pin.value)) {
      unlocked.value = true;
      error.value = '';
      Get.offNamed('/settings');
      return true;
    }
    error.value = 'رمز الدخول غير صحيح';
    return false;
  }
}
