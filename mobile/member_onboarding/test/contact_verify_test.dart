import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:member_onboarding/src/api/api_client.dart';
import 'package:member_onboarding/src/api/onboarding_api.dart';
import 'package:member_onboarding/src/config.dart';
import 'package:member_onboarding/src/models/draft.dart';
import 'package:member_onboarding/src/storage/draft_store.dart';
import 'package:member_onboarding/src/sync/draft_controller.dart';
import 'package:member_onboarding/src/ui/contact_verify.dart';
import 'package:member_onboarding/src/ui/strings.dart';

/// The server, without a network: the right code is 123456.
class FakeApi extends OnboardingApi {
  FakeApi()
    : super(
        ApiClient(
          MemberOnboardingConfig(baseUrl: 'https://x.test', assertionProvider: () async => ''),
        ),
      );

  final sent = <String>[];

  Map<String, dynamic> _form(int version) => {
    'id': 's1',
    'version': version,
    'status': 'draft',
    'aadhaar_last4': '',
    'account_last4': '',
  };

  @override
  Future<Map<String, dynamic>> createApplication({
    required String clientId,
    required String mppId,
  }) async => _form(1);

  @override
  Future<Map<String, dynamic>> saveApplication(
    String id, {
    required int version,
    required Map<String, dynamic> data,
    String? aadhaarNumber,
    String? accountNumber,
    String? aadhaarQr,
  }) async => _form(version + 1);

  @override
  Future<void> sendContactOtp(String id, String channel) async => sent.add(channel);

  @override
  Future<Map<String, dynamic>> verifyContactOtp(String id, String channel, String code) async {
    if (code != '123456') {
      throw ApiException(400, 'wrong_code', 'That code is wrong. 4 tries left.', {
        'code': ['That code is wrong. 4 tries left.'],
      });
    }
    return {'mobile': channel == 'mobile' ? '2026-11-03T10:00:00Z' : null, 'email': null};
  }
}

DraftController controllerWith(FakeApi api, {String mobile = '9170800000'}) => DraftController(
  draft: Draft(
    clientId: 'c1',
    mppId: 'm1',
    mppLabel: '1305 Test',
    data: {
      'address': {'mobile': mobile},
    },
  ),
  api: api,
  store: MemoryDraftStore(),
  debounce: const Duration(hours: 1),
);

Future<void> pumpVerify(WidgetTester tester, DraftController controller) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: ListenableBuilder(
          listenable: controller,
          builder: (_, _) => ContactVerify(controller: controller, channel: 'mobile'),
        ),
      ),
    ),
  );
}

void main() {
  testWidgets('the right code marks the mobile verified', (tester) async {
    final api = FakeApi();
    final controller = controllerWith(api);
    await pumpVerify(tester, controller);
    expect(find.text(Strings.notVerified), findsOneWidget);

    await tester.tap(find.text(Strings.sendOtp));
    await tester.pumpAndSettle(const Duration(seconds: 1));
    expect(api.sent, ['mobile']);
    expect(find.text(Strings.otpSent), findsOneWidget);

    await tester.enterText(find.byKey(const ValueKey('otp.mobile')), '123456');
    await tester.pump();
    await tester.tap(find.text(Strings.checkOtp));
    await tester.pumpAndSettle(const Duration(seconds: 1));

    expect(controller.draft.mobileVerified, isTrue);
    expect(find.text(Strings.verified), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    controller.dispose();
  });

  testWidgets('a wrong code says so and stays unverified', (tester) async {
    final api = FakeApi();
    final controller = controllerWith(api);
    await pumpVerify(tester, controller);

    await tester.tap(find.text(Strings.sendOtp));
    await tester.pumpAndSettle(const Duration(seconds: 1));
    await tester.enterText(find.byKey(const ValueKey('otp.mobile')), '000000');
    await tester.pump();
    await tester.tap(find.text(Strings.checkOtp));
    await tester.pumpAndSettle(const Duration(seconds: 1));

    expect(find.textContaining('4 tries left'), findsOneWidget);
    expect(controller.draft.mobileVerified, isFalse);
    await tester.pumpWidget(const SizedBox());
    controller.dispose();
  });

  testWidgets('resending waits thirty seconds', (tester) async {
    final api = FakeApi();
    final controller = controllerWith(api);
    await pumpVerify(tester, controller);

    await tester.tap(find.text(Strings.sendOtp));
    await tester.pump(const Duration(seconds: 1));

    expect(find.textContaining(Strings.resendIn), findsOneWidget);
    await tester.pump(const Duration(seconds: 31));
    expect(find.text(Strings.resendOtp), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    controller.dispose();
  });

  test('a changed number is no longer verified', () {
    final controller = controllerWith(FakeApi());
    controller.draft.mobileVerified = true;

    controller.setValue('address', 'mobile', '9876543210');

    expect(controller.draft.mobileVerified, isFalse);
    controller.dispose();
  });

  test('a draft remembers what was verified', () {
    final draft = Draft(clientId: 'c1', mppId: 'm1', mppLabel: 'x', mobileVerified: true);

    expect(Draft.decode(draft.encode()).mobileVerified, isTrue);
    expect(
      Draft.decode(
        '{"client_id":"c","mpp_id":"m","mpp_label":"x","status":"draft","data":{},'
        '"aadhaar_last4":"","account_last4":"","pending_documents":{},"uploaded_documents":[],'
        '"rejection_reason":"","rejected_fields":[],"needs_sync":false}',
      ).mobileVerified,
      isFalse,
    );
  });
}
