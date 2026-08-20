import 'package:dio/dio.dart';

class ApiException implements Exception {
  ApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

class ApiService {
  ApiService({Dio? dio}) : _dio = dio ?? Dio();

  final Dio _dio;

  String _normalizeBase(String serverUrl) {
    var url = serverUrl.trim();
    if (url.endsWith('/')) url = url.substring(0, url.length - 1);
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      url = 'http://$url';
    }
    return url;
  }

  BaseOptions _options(String serverUrl, String apiToken) {
    return BaseOptions(
      baseUrl: _normalizeBase(serverUrl),
      connectTimeout: const Duration(seconds: 12),
      receiveTimeout: const Duration(seconds: 20),
      headers: {
        'Authorization': 'Bearer ${apiToken.trim()}',
        'Content-Type': 'application/json',
      },
    );
  }

  String _humanize(DioException error) {
    if (error.type == DioExceptionType.connectionTimeout ||
        error.type == DioExceptionType.receiveTimeout ||
        error.type == DioExceptionType.sendTimeout ||
        error.type == DioExceptionType.connectionError) {
      return 'فشل الاتصال بالخادم';
    }
    final data = error.response?.data;
    if (data is Map && data['error'] is String) {
      return data['error'] as String;
    }
    return 'فشل الاتصال بالخادم';
  }

  Future<Map<String, dynamic>> _send(
    String serverUrl,
    String apiToken,
    String method,
    String path, {
    Map<String, dynamic>? body,
  }) async {
    _dio.options = _options(serverUrl, apiToken);
    try {
      final Response<dynamic> response;
      if (method == 'GET') {
        response = await _dio.get<dynamic>(path);
      } else {
        response = await _dio.post<dynamic>(path, data: body);
      }
      final data = response.data;
      if (data is Map<String, dynamic>) return data;
      if (data is Map) return Map<String, dynamic>.from(data);
      return {'ok': true};
    } on DioException catch (error) {
      throw ApiException(
        _humanize(error),
        statusCode: error.response?.statusCode,
      );
    }
  }

  Future<Map<String, dynamic>> testConnection({
    required String serverUrl,
    required String apiToken,
  }) {
    return _send(serverUrl, apiToken, 'GET', '/api/health');
  }

  Future<Map<String, dynamic>> deploy({
    required String serverUrl,
    required String apiToken,
    required Map<String, String> values,
  }) {
    return _send(serverUrl, apiToken, 'POST', '/api/env', body: values);
  }

  Future<Map<String, dynamic>> restart({
    required String serverUrl,
    required String apiToken,
  }) {
    return _send(serverUrl, apiToken, 'POST', '/api/restart');
  }
}
