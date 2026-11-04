import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:member_onboarding/member_onboarding.dart';
import 'package:member_onboarding/src/api/api_client.dart';
import 'package:member_onboarding/src/api/onboarding_api.dart';
import 'package:member_onboarding/src/models/draft.dart';
import 'package:member_onboarding/src/ui/device_services.dart';
import 'package:member_onboarding/src/ui/strings.dart';

Map<String, dynamic> formJson() => {
  'version': 1,
  'family': {
    'max_members': 6,
    'genders': [
      {'value': 'male', 'label': 'Male', 'label_hi': 'पुरुष'},
    ],
    'relations': [
      {'value': 'husband', 'label': 'Husband', 'label_hi': 'पति'},
    ],
  },
  'sections': [
    for (final key in const [
      'applicant',
      'address',
      'location',
      'animals',
      'bank',
      'nominee',
      'declaration',
    ])
      {
        'key': key,
        'title': key,
        'title_hi': key,
        'fields': [
          if (key == 'address')
            {
              'key': 'tehsil',
              'label': 'Tehsil',
              'label_hi': 'तहसील',
              'type': 'text',
              'required': true,
              'locked': true,
              'source': 'mpp',
            },
          if (key == 'bank')
            {'key': 'ifsc', 'label': 'IFSC', 'label_hi': 'IFSC', 'type': 'text', 'required': true},
          if (key == 'bank')
            {
              'key': 'bank_name',
              'label': 'Bank',
              'label_hi': 'बैंक',
              'type': 'text',
              'required': true,
            },
        ],
      },
  ],
};

class FakeApi extends OnboardingApi {
  FakeApi()
    : super(
        ApiClient(
          MemberOnboardingConfig(baseUrl: 'https://x.test', assertionProvider: () async => ''),
        ),
      );

  bool online = true;
  int saves = 0;
  List<ApplicationSummary> sentBack = const [];
  List<ApplicationSummary> serverDrafts = const [];
  List<Map<String, dynamic>> moreMpps = const [];
  final pushTokens = <String>[];

  @override
  Future<void> registerPushDevice(String token, String platform) async {
    _check();
    pushTokens.add(token);
  }

  void _check() {
    if (!online) throw const OfflineException();
  }

  @override
  Future<Map<String, dynamic>> fetchFormJson() async {
    _check();
    return formJson();
  }

  @override
  Future<List<Map<String, dynamic>>> fetchMppsJson() async {
    _check();
    return [
      {
        'id': 'm1',
        'code': '1305',
        'name': 'Dudwa',
        'place': {'tehsil': 'Gyanpur', 'tehsil_code': '00951', 'post_office': ''},
      },
      ...moreMpps,
    ];
  }

  @override
  Future<List<ApplicationSummary>> fetchApplications({String? status}) async {
    _check();
    return switch (status) {
      'rejected' => sentBack,
      'draft' => serverDrafts,
      _ => const [],
    };
  }

  @override
  Future<Map<String, dynamic>> createApplication({
    required String clientId,
    required String mppId,
  }) async => {
    'id': 's1',
    'version': 1,
    'status': 'draft',
    'aadhaar_last4': '',
    'account_last4': '',
  };

  @override
  Future<Map<String, dynamic>> saveApplication(
    String id, {
    required int version,
    required Map<String, dynamic> data,
    String? aadhaarNumber,
    String? accountNumber,
    String? aadhaarQr,
  }) async {
    saves++;
    return {
      'id': 's1',
      'version': version + 1,
      'status': 'draft',
      'aadhaar_last4': '',
      'account_last4': '',
    };
  }
}

class FakeDevice extends DeviceServices {
  const FakeDevice();

  @override
  Future<(String, String)?> lookupIfsc(String ifsc) async =>
      ifsc == 'UBIN0572161' ? ('Union Bank of India', 'Siyarha') : null;
}

Widget app(FakeApi api, DraftStore store) => MaterialApp(
  home: MemberOnboardingScreen(
    config: MemberOnboardingConfig(baseUrl: 'https://x.test', assertionProvider: () async => ''),
    api: api,
    store: store,
    device: const FakeDevice(),
  ),
);

void main() {
  testWidgets('with nothing cached, the first start says it needs the internet', (tester) async {
    final api = FakeApi()..online = false;

    await tester.pumpWidget(app(api, MemoryDraftStore()));
    await tester.pumpAndSettle();

    expect(find.text(Strings.firstRunNeedsNetwork), findsOneWidget);
  });

  testWidgets('after one online start, a new form can begin offline', (tester) async {
    final api = FakeApi();
    final store = MemoryDraftStore();
    await tester.pumpWidget(app(api, store));
    await tester.pumpAndSettle();

    api.online = false;
    await tester.pumpWidget(const SizedBox());
    await tester.pumpWidget(app(api, store));
    await tester.pumpAndSettle();

    expect(find.text(Strings.offlineReady), findsOneWidget);

    // The only MPP is chosen already.
    await tester.tap(find.text(Strings.newForm));
    await tester.pumpAndSettle();

    expect(find.textContaining('${Strings.step} 1 / 8'), findsOneWidget);
    expect((await store.all()).single.mppLabel, '1305 Dudwa');

    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('with several MPPs, one is searched for and chosen before a new form', (tester) async {
    final store = MemoryDraftStore();
    final api = FakeApi()
      ..moreMpps = const [
        {'id': 'm2', 'code': '1152', 'name': 'Tilthi', 'place': <String, String>{}},
      ];
    await tester.pumpWidget(app(api, store));
    await tester.pumpAndSettle();

    final start = find.widgetWithText(FilledButton, Strings.newForm);
    expect(tester.widget<FilledButton>(start).onPressed, isNull);

    await tester.tap(find.byType(DropdownMenu<MppSummary>));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).first, 'Til');
    await tester.pumpAndSettle();
    // Typing narrows the list to the MPPs that match.
    expect(find.widgetWithText(MenuItemButton, '1305 Dudwa'), findsNothing);
    await tester.tap(find.widgetWithText(MenuItemButton, '1152 Tilthi'));
    await tester.pumpAndSettle();
    await tester.tap(start);
    await tester.pumpAndSettle();

    expect((await store.all()).single.mppLabel, '1152 Tilthi');
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('a new form starts with the place its MPP knows', (tester) async {
    final store = MemoryDraftStore();
    await tester.pumpWidget(app(FakeApi(), store));
    await tester.pumpAndSettle();

    // The only MPP is chosen already.
    await tester.tap(find.text(Strings.newForm));
    await tester.pumpAndSettle();

    final draft = (await store.all()).single;
    // Only fields the form locks, and only what the MPP actually knows.
    expect(draft.place, {'tehsil': 'Gyanpur'});
    expect(draft.section('address')['tehsil'], 'Gyanpur');

    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('forms waiting on the phone go up when the network returns', (tester) async {
    final api = FakeApi();
    final store = MemoryDraftStore();
    await store.save(Draft(clientId: 'c1', mppId: 'm1', mppLabel: 'x', needsSync: true));

    await tester.pumpWidget(app(api, store));
    await tester.pumpAndSettle();

    expect(api.saves, 1);
    expect((await store.all()).single.needsSync, isFalse);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the cached copy survives as JSON', (tester) async {
    final store = MemoryDraftStore();
    await tester.pumpWidget(app(FakeApi(), store));
    await tester.pumpAndSettle();

    final cached = jsonDecode((await store.readCache('form'))!) as Map<String, dynamic>;
    expect(cached['version'], 1);
    await tester.pumpWidget(const SizedBox());
  });

  test('a host that fails to vouch counts as offline, and never crashes the form', () async {
    final client = ApiClient(
      MemberOnboardingConfig(
        baseUrl: 'https://x.test',
        assertionProvider: () async => throw 'token call failed',
      ),
    );

    await expectLater(client.get('a/'), throwsA(isA<OfflineException>()));
  });

  testWidgets('forms sent back are announced when the home opens', (tester) async {
    final api = FakeApi()
      ..sentBack = const [
        ApplicationSummary(
          id: 'r1',
          status: 'rejected',
          statusLabel: 'Rejected',
          applicantName: 'Sita Devi',
          mppCode: '1305',
          formNumber: 'A00012',
        ),
      ];

    await tester.pumpWidget(app(api, MemoryDraftStore()));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('sent_back.alert')), findsOneWidget);
    expect(find.descendant(of: find.byKey(const ValueKey('sent_back.alert')), matching: find.text('Sita Devi')), findsOneWidget);

    await tester.tap(find.text(Strings.later));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('sent_back.alert')), findsNothing);
  });

  testWidgets('no alert when nothing was sent back', (tester) async {
    await tester.pumpWidget(app(FakeApi(), MemoryDraftStore()));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('sent_back.alert')), findsNothing);
  });

  testWidgets('the phone tells the server where to send push notifications', (tester) async {
    final api = FakeApi();
    await tester.pumpWidget(
      MaterialApp(
        home: MemberOnboardingScreen(
          config: MemberOnboardingConfig(
            baseUrl: 'https://x.test',
            assertionProvider: () async => '',
            pushTokenProvider: () async => 'fcm-token-1',
          ),
          api: api,
          store: MemoryDraftStore(),
          device: const FakeDevice(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(api.pushTokens, ['fcm-token-1']);
  });

  testWidgets('a draft only on the server still shows among the unfinished forms', (tester) async {
    final api = FakeApi()
      ..serverDrafts = const [
        ApplicationSummary(
          id: 's1',
          status: 'draft',
          statusLabel: 'Draft',
          applicantName: 'Sita Devi',
          mppCode: '1305',
        ),
      ];

    await tester.pumpWidget(app(api, MemoryDraftStore()));
    await tester.pumpAndSettle();

    expect(find.text('Sita Devi'), findsOneWidget);
    expect(find.text(Strings.noDrafts), findsNothing);
  });
}
