import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../config.dart';

/// A refusal from the server, with its machine-readable code.
class ApiException implements Exception {
  ApiException(this.status, this.code, this.message, [this.details]);

  final int status;
  final String code;
  final String message;
  final Object? details;

  /// `{"section.field": "message"}`, when the server rejected specific fields.
  Map<String, String> get fieldErrors {
    final raw = details;
    if (raw is! Map) return const {};
    return raw.map((key, value) {
      final text = value is List ? value.join(' ') : '$value';
      return MapEntry('$key', text);
    });
  }

  @override
  String toString() => 'ApiException($status, $code): $message';
}

/// No connection, so the work stays on the device and is retried later.
class OfflineException implements Exception {
  const OfflineException();
}

class ApiClient {
  ApiClient(this.config, {http.Client? client}) : _client = client ?? http.Client();

  static const _timeout = Duration(seconds: 30);

  final MemberOnboardingConfig config;
  final http.Client _client;

  String? _accessToken;
  DateTime? _expiresAt;
  Future<void>? _signingIn;

  Uri _uri(String path, [Map<String, String>? query]) {
    final base = config.baseUrl.endsWith('/')
        ? config.baseUrl.substring(0, config.baseUrl.length - 1)
        : config.baseUrl;
    return Uri.parse('$base/api/v1/$path').replace(queryParameters: query);
  }

  Future<void> _signIn() async {
    final String assertion;
    try {
      assertion = await config.assertionProvider();
    } catch (_) {
      // Whatever the host app threw, the form work simply waits for a later try.
      throw const OfflineException();
    }

    final response = await _guard(
      () => _client.post(
        _uri('auth/exchange/'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'assertion': assertion}),
      ),
    );
    final body = _decode(response) as Map<String, dynamic>;
    _accessToken = body['access'] as String;
    // Renewed a little early, so a request never leaves with a dying token.
    final seconds = (body['expires_in'] as num).toInt();
    _expiresAt = DateTime.now().add(Duration(seconds: seconds - 30));
  }

  /// Parallel requests share one sign-in, because an assertion works only once.
  Future<void> _ensureSignedIn() async {
    final expiresAt = _expiresAt;
    if (_accessToken != null && expiresAt != null && DateTime.now().isBefore(expiresAt)) {
      return;
    }
    final pending = _signingIn ??= _signIn().whenComplete(() => _signingIn = null);
    await pending;
  }

  Future<http.Response> _guard(Future<http.Response> Function() call) async {
    try {
      return await call().timeout(_timeout);
    } on SocketException {
      throw const OfflineException();
    } on TimeoutException {
      throw const OfflineException();
    } on http.ClientException {
      throw const OfflineException();
    }
  }

  Future<http.Response> _authorized(
    Future<http.Response> Function(Map<String, String> headers) call,
  ) async {
    await _ensureSignedIn();
    var response = await _guard(() => call({'Authorization': 'Bearer $_accessToken'}));
    if (response.statusCode == 401) {
      // The token ended early, for instance after a role change: ask the host again.
      _accessToken = null;
      await _ensureSignedIn();
      response = await _guard(() => call({'Authorization': 'Bearer $_accessToken'}));
    }
    return response;
  }

  Object? _decode(http.Response response) {
    final Object? body = response.bodyBytes.isEmpty
        ? null
        : jsonDecode(utf8.decode(response.bodyBytes));
    if (response.statusCode >= 200 && response.statusCode < 300) return body;

    final error = body is Map ? body['error'] : null;
    throw ApiException(
      response.statusCode,
      error is Map ? '${error['code']}' : 'error',
      error is Map ? '${error['message']}' : 'Something went wrong.',
      error is Map ? error['details'] : null,
    );
  }

  Future<Object?> get(String path, {Map<String, String>? query}) async {
    final response = await _authorized(
      (headers) => _client.get(_uri(path, query), headers: headers),
    );
    return _decode(response);
  }

  /// A file's raw bytes, such as a document photo already on the server.
  Future<List<int>> getBytes(String path) async {
    final response = await _authorized((headers) => _client.get(_uri(path), headers: headers));
    if (response.statusCode >= 200 && response.statusCode < 300) return response.bodyBytes;
    _decode(response);
    return const [];
  }

  Future<Object?> post(String path, [Map<String, dynamic>? body]) async {
    final response = await _authorized(
      (headers) => _client.post(
        _uri(path),
        headers: {...headers, 'Content-Type': 'application/json'},
        body: jsonEncode(body ?? const {}),
      ),
    );
    return _decode(response);
  }

  Future<Object?> patch(String path, Map<String, dynamic> body) async {
    final response = await _authorized(
      (headers) => _client.patch(
        _uri(path),
        headers: {...headers, 'Content-Type': 'application/json'},
        body: jsonEncode(body),
      ),
    );
    return _decode(response);
  }

  /// Sends a file from memory, so a decrypted photo never touches the disk.
  Future<Object?> upload(
    String path,
    Map<String, String> fields,
    List<int> bytes,
    String filename,
  ) async {
    final response = await _authorized((headers) async {
      final request = http.MultipartRequest('POST', _uri(path))
        ..headers.addAll(headers)
        ..fields.addAll(fields)
        ..files.add(http.MultipartFile.fromBytes('file', bytes, filename: filename));
      return http.Response.fromStream(await _client.send(request));
    });
    return _decode(response);
  }
}
