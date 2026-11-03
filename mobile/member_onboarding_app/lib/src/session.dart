import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

/// Who is signed in, kept in the phone's secure storage so the app opens straight
/// to the forms next time. Refresh tokens are replaced on every use, so only one
/// refresh may run at a time: a second one with the same token would be refused.
class Session extends ChangeNotifier {
  Session({required this.baseUrl, FlutterSecureStorage? storage, http.Client? client})
    : _storage = storage ?? const FlutterSecureStorage(),
      _client = client ?? http.Client();

  static const _key = 'member_onboarding_app.session';

  final String baseUrl;
  final FlutterSecureStorage _storage;
  final http.Client _client;

  String? _access;
  String? _refresh;
  String? organizationSlug;
  String? organizationName;
  Future<String>? _refreshing;

  bool get signedIn => _refresh != null;

  Uri uri(String path) {
    final base = baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl;
    return Uri.parse('$base/api/v1/$path');
  }

  Future<void> restore() async {
    final saved = await _storage.read(key: _key);
    if (saved != null) {
      final data = jsonDecode(saved) as Map<String, dynamic>;
      _access = data['access'] as String?;
      _refresh = data['refresh'] as String?;
      organizationSlug = data['organization_slug'] as String?;
      organizationName = data['organization_name'] as String?;
    }
    notifyListeners();
  }

  Future<void> start({
    required String access,
    required String refresh,
    required String slug,
    required String name,
  }) async {
    _access = access;
    _refresh = refresh;
    organizationSlug = slug;
    organizationName = name;
    await _save();
    notifyListeners();
  }

  Future<void> _save() => _storage.write(
    key: _key,
    value: jsonEncode({
      'access': _access,
      'refresh': _refresh,
      'organization_slug': organizationSlug,
      'organization_name': organizationName,
    }),
  );

  /// For the forms package: a token that is good now, refreshed when [renew] or
  /// when it is about to end.
  Future<String> accessToken({required bool renew}) async {
    final access = _access;
    if (!renew && access != null && !_endingSoon(access)) return access;
    return _refreshing ??= _refreshNow().whenComplete(() => _refreshing = null);
  }

  Future<String> _refreshNow() async {
    final refresh = _refresh;
    if (refresh == null) throw StateError('Not signed in.');
    final response = await _client
        .post(
          uri('auth/refresh/'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'refresh': refresh}),
        )
        .timeout(const Duration(seconds: 30));
    if (response.statusCode == 401) {
      // Ended, or taken away by the administrator: back to the sign-in screen.
      await signOut();
      throw StateError('Signed out.');
    }
    if (response.statusCode != 200) throw StateError('Could not refresh: ${response.statusCode}');
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    _access = body['access'] as String;
    _refresh = (body['refresh'] as String?) ?? refresh;
    await _save();
    return _access!;
  }

  Future<void> signOut() async {
    final refresh = _refresh;
    final access = _access;
    _access = _refresh = organizationSlug = organizationName = null;
    await _storage.delete(key: _key);
    notifyListeners();
    if (refresh != null && access != null) {
      // Best effort: the server forgets the refresh token too.
      unawaited(
        _client
            .post(
              uri('auth/logout/'),
              headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer $access'},
              body: jsonEncode({'refresh': refresh}),
            )
            .then((_) {}, onError: (_) {}),
      );
    }
  }

  static bool _endingSoon(String token) {
    try {
      final payload = token.split('.')[1];
      final claims =
          jsonDecode(utf8.decode(base64Url.decode(base64Url.normalize(payload))))
              as Map<String, dynamic>;
      final expires = DateTime.fromMillisecondsSinceEpoch((claims['exp'] as int) * 1000);
      return DateTime.now().isAfter(expires.subtract(const Duration(seconds: 60)));
    } catch (_) {
      return true;
    }
  }
}
