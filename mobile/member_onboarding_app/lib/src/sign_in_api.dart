import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'session.dart';

class SignInFailed implements Exception {
  const SignInFailed(this.message);
  final String message;

  @override
  String toString() => message;
}

class OrganizationChoice {
  const OrganizationChoice(this.slug, this.name);
  final String slug;
  final String name;
}

/// What the code check answered: signed in, or which organization to choose first.
class VerifyResult {
  const VerifyResult.signedIn() : choices = const [];
  const VerifyResult.choose(this.choices);
  final List<OrganizationChoice> choices;
  bool get needsChoice => choices.isNotEmpty;
}

class SignInApi {
  SignInApi(this.session, {http.Client? client}) : _client = client ?? http.Client();

  final Session session;
  final http.Client _client;

  Future<Map<String, dynamic>> _post(String path, Map<String, Object> body) async {
    final http.Response response;
    try {
      response = await _client
          .post(
            session.uri(path),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(body),
          )
          .timeout(const Duration(seconds: 30));
    } on SocketException {
      throw const SignInFailed('No internet. Connect and try again.');
    } on TimeoutException {
      throw const SignInFailed('The server took too long. Try again.');
    } on http.ClientException {
      throw const SignInFailed('No internet. Connect and try again.');
    }
    final data = response.body.isEmpty
        ? <String, dynamic>{}
        : jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    if (response.statusCode == 200) return data;
    final error = data['error'];
    final message = error is Map ? '${error['message']}' : '';
    if (response.statusCode == 429) {
      throw const SignInFailed('Too many tries. Wait a minute and try again.');
    }
    throw SignInFailed(message.isEmpty ? 'Something went wrong. Try again.' : message);
  }

  /// Returns the challenge to send back with the code.
  Future<String> sendCode(String mobile) async {
    final data = await _post('auth/mobile/start/', {'mobile': mobile});
    return data['challenge'] as String;
  }

  Future<VerifyResult> verify(String challenge, String code, {String organization = ''}) async {
    final data = await _post('auth/mobile/verify/', {
      'challenge': challenge,
      'code': code,
      'organization': organization,
    });
    final choose = data['choose'];
    if (choose is List) {
      return VerifyResult.choose([
        for (final item in choose.cast<Map<String, dynamic>>())
          OrganizationChoice(item['slug'] as String, item['name'] as String),
      ]);
    }
    final organizationData = data['organization'] as Map<String, dynamic>;
    await session.start(
      access: data['access'] as String,
      refresh: data['refresh'] as String,
      slug: organizationData['slug'] as String,
      name: organizationData['name'] as String,
    );
    return const VerifyResult.signedIn();
  }

  /// The organization's colour, so the app looks like theirs. Null when unknown.
  Future<String?> primaryColor(String slug) async {
    try {
      final uri = session.uri('public/branding/').replace(queryParameters: {'organization': slug});
      final response = await _client.get(uri).timeout(const Duration(seconds: 15));
      if (response.statusCode != 200) return null;
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      return data['primary_color'] as String?;
    } catch (_) {
      return null;
    }
  }
}
