import 'package:get/get.dart';
import 'package:shared_preferences/shared_preferences.dart';

class StorageService extends GetxService {
  late final SharedPreferences _prefs;

  Future<StorageService> init() async {
    _prefs = await SharedPreferences.getInstance();
    return this;
  }

  String read(String key, {String fallback = ''}) =>
      _prefs.getString(key) ?? fallback;

  Future<void> write(String key, String value) => _prefs.setString(key, value);

  Future<void> writeAll(Map<String, String> values) async {
    for (final entry in values.entries) {
      await _prefs.setString(entry.key, entry.value);
    }
  }

  bool get darkMode => _prefs.getBool('dark_mode') ?? false;

  Future<void> setDarkMode(bool value) => _prefs.setBool('dark_mode', value);
}
