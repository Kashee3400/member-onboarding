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
    ];
  }

  @override
  Future<List<ApplicationSummary>> fetchApplications({String? status}) async {
    _check();
    return const [];
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

    await tester.tap(find.text(Strings.newForm));
    await tester.pumpAndSettle();
    await tester.tap(find.text('1305 Dudwa'));
    await tester.pumpAndSettle();

    expect(find.textContaining('${Strings.step} 1 / 9'), findsOneWidget);
    expect((await store.all()).single.mppLabel, '1305 Dudwa');

    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('a new form starts with the place its MPP knows', (tester) async {
    final store = MemoryDraftStore();
    await tester.pumpWidget(app(FakeApi(), store));
    await tester.pumpAndSettle();

    await tester.tap(find.text(Strings.newForm));
    await tester.pumpAndSettle();
    await tester.tap(find.text('1305 Dudwa'));
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
}
