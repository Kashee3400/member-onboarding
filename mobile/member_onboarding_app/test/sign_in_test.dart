import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:member_onboarding_app/src/session.dart';
import 'package:member_onboarding_app/src/sign_in_api.dart';
import 'package:member_onboarding_app/src/sign_in_screen.dart';

String jwt(Duration validFor) {
  final exp = DateTime.now().add(validFor).millisecondsSinceEpoch ~/ 1000;
  final payload = base64Url.encode(utf8.encode(jsonEncode({'exp': exp}))).replaceAll('=', '');
  return 'h.$payload.s';
}

http.Response json(Object body, [int status = 200]) => http.Response(jsonEncode(body), status);

void main() {
  setUp(() => FlutterSecureStorage.setMockInitialValues({}));

  Future<(Session, List<http.Request>)> pump(
    WidgetTester tester,
    http.Response Function(http.Request) server,
  ) async {
    final seen = <http.Request>[];
    final client = MockClient((request) async {
      seen.add(request);
      return server(request);
    });
    final session = Session(baseUrl: 'https://svc.test', client: client);
    await tester.pumpWidget(
      MaterialApp(home: SignInScreen(api: SignInApi(session, client: client))),
    );
    return (session, seen);
  }

  testWidgets('a mobile number and the code sign a facilitator in', (tester) async {
    final (session, seen) = await pump(tester, (request) {
      if (request.url.path.endsWith('mobile/start/')) return json({'challenge': 'c1', 'expires_in': 600});
      return json({
        'access': jwt(const Duration(minutes: 15)),
        'refresh': 'r1',
        'organization': {'slug': 'kashee', 'name': 'Kashee'},
      });
    });

    await tester.enterText(find.byKey(const ValueKey('sign-in.mobile')), '9876543210');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('sign-in.send')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('sign-in.code')), '123456');
    await tester.pumpAndSettle();

    expect(session.signedIn, isTrue);
    expect(session.organizationSlug, 'kashee');
    expect(jsonDecode(seen.last.body), {'challenge': 'c1', 'code': '123456', 'organization': ''});
    // The resend timer would keep the test waiting otherwise.
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a number in two companies chooses one after the code', (tester) async {
    final (session, seen) = await pump(tester, (request) {
      if (request.url.path.endsWith('mobile/start/')) return json({'challenge': 'c1', 'expires_in': 600});
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      if (body['organization'] == '') {
        return json({
          'choose': [
            {'slug': 'kashee', 'name': 'Kashee'},
            {'slug': 'paayas', 'name': 'Paayas Milk'},
          ],
        });
      }
      return json({
        'access': jwt(const Duration(minutes: 15)),
        'refresh': 'r1',
        'organization': {'slug': body['organization'], 'name': 'Paayas Milk'},
      });
    });

    await tester.enterText(find.byKey(const ValueKey('sign-in.mobile')), '9876543210');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('sign-in.send')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('sign-in.code')), '123456');
    await tester.pumpAndSettle();
    await tester.tap(find.text('Paayas Milk'));
    await tester.pumpAndSettle();

    expect(session.organizationSlug, 'paayas');
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a wrong code says so and keeps the facilitator on the code', (tester) async {
    final (session, _) = await pump(tester, (request) {
      if (request.url.path.endsWith('mobile/start/')) return json({'challenge': 'c1', 'expires_in': 600});
      return json({
        'error': {'code': 'code_rejected', 'message': 'That code is not right.'},
      }, 401);
    });

    await tester.enterText(find.byKey(const ValueKey('sign-in.mobile')), '9876543210');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('sign-in.send')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('sign-in.code')), '000000');
    await tester.pumpAndSettle();

    expect(find.text('That code is not right.'), findsOneWidget);
    expect(find.byKey(const ValueKey('sign-in.code')), findsOneWidget);
    expect(session.signedIn, isFalse);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a short or wrong number cannot ask for a code', (tester) async {
    await pump(tester, (_) => json({}));

    await tester.enterText(find.byKey(const ValueKey('sign-in.mobile')), '12345');
    await tester.pump();

    final send = tester.widget<FilledButton>(find.byKey(const ValueKey('sign-in.send')));
    expect(send.onPressed, isNull);
  });

  group('session', () {
    test('an ending token is refreshed once, even when asked twice at once', () async {
      var refreshes = 0;
      final session = Session(
        baseUrl: 'https://svc.test',
        client: MockClient((request) async {
          refreshes++;
          expect(jsonDecode(request.body), {'refresh': 'r1'});
          return json({'access': jwt(const Duration(minutes: 15)), 'refresh': 'r2'});
        }),
      );
      await session.start(access: jwt(Duration.zero), refresh: 'r1', slug: 'k', name: 'K');

      final tokens = await Future.wait([
        session.accessToken(renew: false),
        session.accessToken(renew: false),
      ]);

      expect(refreshes, 1);
      expect(tokens[0], tokens[1]);
    });

    test('a refused refresh signs the person out', () async {
      final session = Session(
        baseUrl: 'https://svc.test',
        client: MockClient((request) async {
          if (request.url.path.endsWith('refresh/')) return json({}, 401);
          return json({});
        }),
      );
      await session.start(access: jwt(Duration.zero), refresh: 'r1', slug: 'k', name: 'K');

      await expectLater(session.accessToken(renew: true), throwsStateError);
      expect(session.signedIn, isFalse);
    });

    test('a signed-in person is remembered on the phone', () async {
      final first = Session(baseUrl: 'https://svc.test', client: MockClient((_) async => json({})));
      await first.start(access: 'a', refresh: 'r', slug: 'paayas', name: 'Paayas Milk');

      final next = Session(baseUrl: 'https://svc.test', client: MockClient((_) async => json({})));
      await next.restore();

      expect(next.signedIn, isTrue);
      expect(next.organizationName, 'Paayas Milk');
    });
  });
}
