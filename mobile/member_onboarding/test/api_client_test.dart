import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:member_onboarding/src/api/api_client.dart';
import 'package:member_onboarding/src/config.dart';

void main() {
  late int assertions;
  late int exchanges;

  MemberOnboardingConfig config() => MemberOnboardingConfig(
    baseUrl: 'https://service.test/',
    primaryColor: Colors.blue,
    assertionProvider: () async {
      assertions++;
      return 'assertion-$assertions';
    },
  );

  http.Response token(String value, {int expiresIn = 900}) =>
      http.Response(jsonEncode({'access': value, 'expires_in': expiresIn}), 200);

  setUp(() {
    assertions = 0;
    exchanges = 0;
  });

  test('signs in through the host, then calls with the token', () async {
    final client = ApiClient(
      config(),
      client: MockClient((request) async {
        if (request.url.path.endsWith('auth/exchange/')) {
          exchanges++;
          expect(jsonDecode(request.body), {'assertion': 'assertion-1'});
          return token('t1');
        }
        expect(request.headers['Authorization'], 'Bearer t1');
        expect(request.url.toString(), 'https://service.test/api/v1/applications/form/');
        return http.Response('{}', 200);
      }),
    );

    await client.get('applications/form/');
    await client.get('applications/form/');

    expect(exchanges, 1);
  });

  test('parallel calls share one sign-in, as an assertion works only once', () async {
    final client = ApiClient(
      config(),
      client: MockClient((request) async {
        if (request.url.path.endsWith('auth/exchange/')) {
          exchanges++;
          return token('t1');
        }
        return http.Response('{}', 200);
      }),
    );

    await Future.wait([client.get('a/'), client.get('b/'), client.get('c/')]);

    expect(exchanges, 1);
  });

  test('a rejected token asks the host again and retries once', () async {
    var calls = 0;
    final client = ApiClient(
      config(),
      client: MockClient((request) async {
        if (request.url.path.endsWith('auth/exchange/')) return token('t${++exchanges}');
        calls++;
        return request.headers['Authorization'] == 'Bearer t1'
            ? http.Response('{}', 401)
            : http.Response('{"ok": true}', 200);
      }),
    );

    expect(await client.get('a/'), {'ok': true});
    expect(calls, 2);
    expect(exchanges, 2);
  });

  test('an expired token is renewed before it is used', () async {
    final client = ApiClient(
      config(),
      client: MockClient((request) async {
        if (request.url.path.endsWith('auth/exchange/')) {
          exchanges++;
          return token('t$exchanges', expiresIn: 10);
        }
        return http.Response('{}', 200);
      }),
    );

    await client.get('a/');
    await client.get('a/');

    expect(exchanges, 2);
  });

  test('server errors keep their code and field details', () async {
    final client = ApiClient(
      config(),
      client: MockClient((request) async {
        if (request.url.path.endsWith('auth/exchange/')) return token('t1');
        return http.Response(
          jsonEncode({
            'error': {
              'code': 'validation_error',
              'message': 'Invalid input.',
              'details': {
                'bank.ifsc': ['Enter a valid IFSC.'],
              },
            },
          }),
          400,
        );
      }),
    );

    await expectLater(
      client.post('applications/1/submit/'),
      throwsA(
        isA<ApiException>()
            .having((error) => error.code, 'code', 'validation_error')
            .having((error) => error.fieldErrors['bank.ifsc'], 'field', 'Enter a valid IFSC.'),
      ),
    );
  });

  test('Hindi in a response is decoded correctly', () async {
    final client = ApiClient(
      config(),
      client: MockClient((request) async {
        if (request.url.path.endsWith('auth/exchange/')) return token('t1');
        return http.Response.bytes(utf8.encode('{"title": "आवेदक"}'), 200);
      }),
    );

    expect(await client.get('a/'), {'title': 'आवेदक'});
  });

  test('no network becomes offline, so the work can wait', () async {
    final client = ApiClient(
      config(),
      client: MockClient((request) async => throw const SocketException('down')),
    );

    await expectLater(client.get('a/'), throwsA(isA<OfflineException>()));
  });
}
