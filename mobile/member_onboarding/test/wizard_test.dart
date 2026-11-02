import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:member_onboarding/src/api/api_client.dart';
import 'package:member_onboarding/src/api/onboarding_api.dart';
import 'package:member_onboarding/src/config.dart';
import 'package:member_onboarding/src/models/draft.dart';
import 'package:member_onboarding/src/models/form_schema.dart';
import 'package:member_onboarding/src/storage/draft_store.dart';
import 'package:member_onboarding/src/sync/draft_controller.dart';
import 'package:member_onboarding/src/ui/device_services.dart';
import 'package:member_onboarding/src/ui/fields.dart';
import 'package:member_onboarding/src/ui/strings.dart';
import 'package:member_onboarding/src/ui/wizard.dart';

FormSectionSpec section(String key, String title, List<FormFieldSpec> fields) =>
    FormSectionSpec(key: key, title: title, fields: fields);

FormFieldSpec text(String key, String label, {bool required = true}) =>
    FormFieldSpec(key: key, label: label, type: 'text', required: required);

final schema = FormSchema(
  version: 1,
  maxFamilyMembers: 2,
  familyGenders: const [ChoiceOption(value: 'male', label: 'पुरुष')],
  familyRelations: const [ChoiceOption(value: 'husband', label: 'पति')],
  sections: [
    section('applicant', 'आवेदक', [
      text('full_name', 'पूरा नाम'),
      const FormFieldSpec(
        key: 'gender',
        label: 'लिंग',
        type: 'choice',
        required: true,
        options: [ChoiceOption(value: 'female', label: 'महिला')],
      ),
      text('full_name_hi', 'हिन्दी नाम', required: false),
    ]),
    section('address', 'पता', [text('tehsil', 'तहसील')]),
    section('location', 'स्थान', const [
      FormFieldSpec(key: 'latitude', label: 'अक्षांश', type: 'decimal', required: true),
    ]),
    section('animals', 'पशु', const [
      FormFieldSpec(key: 'buffalo_heifer', label: 'भैंस', type: 'number', required: false),
      FormFieldSpec(key: 'production_lpd', label: 'उत्पादन', type: 'decimal', required: true),
      FormFieldSpec(key: 'consumption_lpd', label: 'खपत', type: 'decimal', required: true),
    ]),
    section('bank', 'बैंक', [text('ifsc', 'IFSC')]),
    section('nominee', 'नामित', [text('name', 'नामित का नाम')]),
    section('declaration', 'घोषणा', const [
      FormFieldSpec(key: 'accepted_terms', label: 'सहमत', type: 'boolean', required: true),
    ]),
  ],
);

final _live = <DraftController>[];

DraftController newController({Draft? draft}) {
  final controller = DraftController(
    draft: draft ?? Draft(clientId: 'c1', mppId: 'm1', mppLabel: '1305 Test'),
    api: OnboardingApi(
      ApiClient(
        MemberOnboardingConfig(baseUrl: 'https://x.test', assertionProvider: () async => ''),
      ),
    ),
    store: MemoryDraftStore(),
    debounce: const Duration(hours: 1),
  );
  _live.add(controller);
  return controller;
}

/// Ends each test with the controllers' save timers cancelled.
void wizardTest(String name, Future<void> Function(WidgetTester) body) {
  testWidgets(name, (tester) async {
    tester.view
      ..physicalSize = const Size(1000, 5000)
      ..devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await body(tester);
    await tester.pumpWidget(const SizedBox());
    for (final controller in _live) {
      controller.dispose();
    }
    _live.clear();
  });
}

Future<void> pump(
  WidgetTester tester,
  DraftController controller, {
  FormSchema? withSchema,
  DeviceServices device = const DeviceServices(),
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: FormWizard(schema: withSchema ?? schema, controller: controller, device: device),
    ),
  );
  await tester.pump();
}

FormFieldSpec fromMpp(String key, String label) =>
    FormFieldSpec(key: key, label: label, type: 'text', required: true, locked: true);

/// The same form, with an address the MPP fills as the server's schema marks it.
final placeSchema = FormSchema(
  version: 1,
  maxFamilyMembers: 2,
  familyGenders: schema.familyGenders,
  familyRelations: schema.familyRelations,
  sections: [
    for (final item in schema.sections)
      if (item.key == 'address')
        section('address', 'पता', [
          text('house_number', 'घर संख्या', required: false),
          fromMpp('tehsil', 'तहसील'),
          fromMpp('post_office', 'पोस्ट ऑफिस'),
          fromMpp('pincode', 'पिन कोड'),
        ])
      else
        item,
  ],
);

Draft placedDraft() => Draft(
  clientId: 'c1',
  mppId: 'm1',
  mppLabel: '1305 Test',
  place: const {'tehsil': 'Gyanpur', 'pincode': '221406'},
  data: {
    'address': {'tehsil': 'Gyanpur', 'pincode': '221406'},
  },
);

/// An Aadhaar secure QR, built the way UIDAI packs one.
String secureQr(List<String> fields) {
  final bytes = <int>[];
  for (final field in fields) {
    bytes
      ..addAll(latin1.encode(field))
      ..add(255);
  }
  final hex = gzip.encode(bytes).map((byte) => byte.toRadixString(16).padLeft(2, '0')).join();
  return BigInt.parse(hex, radix: 16).toString();
}

Finder boxFor(String key) => find.byKey(ValueKey(key));

void main() {
  wizardTest('labels come from the server, in Hindi', (tester) async {
    await pump(tester, newController());

    expect(find.text('आवेदक'), findsOneWidget);
    expect(find.textContaining('पूरा नाम'), findsOneWidget);
  });

  wizardTest('optional fields say so', (tester) async {
    await pump(tester, newController());
    expect(find.textContaining(Strings.optional), findsOneWidget);
  });

  wizardTest('typing saves into the draft', (tester) async {
    final controller = newController();
    await pump(tester, controller);

    await tester.enterText(
      find.descendant(of: boxFor('applicant.full_name'), matching: find.byType(TextField)),
      'सीता',
    );

    expect(controller.draft.section('applicant')['full_name'], 'सीता');
  });

  wizardTest('moving on needs no complete step, so nobody gets stuck', (tester) async {
    await pump(tester, newController());

    await tester.tap(find.text(Strings.next));
    await tester.pump();

    expect(find.text('पता'), findsOneWidget);
  });

  wizardTest('the form has nine short steps', (tester) async {
    await pump(tester, newController());
    expect(find.text('${Strings.step} 1 / 9'), findsOneWidget);
  });

  wizardTest('an active field lifts and an idle one stays flat', (tester) async {
    await pump(tester, newController());
    final field = find.descendant(
      of: boxFor('applicant.full_name'),
      matching: find.byType(LiftBox),
    );
    expect(tester.widget<LiftBox>(field).active, isFalse);

    await tester.tap(
      find.descendant(of: boxFor('applicant.full_name'), matching: find.byType(TextField)),
    );
    await tester.pumpAndSettle();

    expect(tester.widget<LiftBox>(field).active, isTrue);
  });

  wizardTest('a corner is square', (tester) async {
    await pump(tester, newController());
    final box = tester.widget<AnimatedContainer>(
      find.descendant(of: boxFor('applicant.full_name'), matching: find.byType(AnimatedContainer)),
    );
    expect((box.decoration! as BoxDecoration).borderRadius, isNull);
  });

  wizardTest('the Aadhaar box takes only digits, twelve at most', (tester) async {
    final controller = newController();
    await pump(tester, controller);

    await tester.enterText(
      find.descendant(of: boxFor('aadhaar_number'), matching: find.byType(TextField)),
      '2341abc234123469999',
    );

    expect(controller.draft.pendingAadhaar, '234123412346');
  });

  wizardTest('choices open in a sheet and save', (tester) async {
    final controller = newController();
    await pump(tester, controller);
    await tester.ensureVisible(boxFor('applicant.gender'));

    await tester.tap(boxFor('applicant.gender'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('महिला'));
    await tester.pumpAndSettle();

    expect(controller.draft.section('applicant')['gender'], 'female');
  });

  Future<void> goToStep(WidgetTester tester, int step) async {
    for (var at = 1; at < step; at++) {
      await tester.ensureVisible(find.text(Strings.next));
      await tester.tap(find.text(Strings.next));
      await tester.pump();
    }
  }

  wizardTest('the bank number must match when typed twice', (tester) async {
    final controller = newController();
    await pump(tester, controller);
    await goToStep(tester, 4);

    await tester.enterText(
      find.descendant(of: boxFor('account_number'), matching: find.byType(TextField)),
      '12345',
    );
    await tester.enterText(
      find.descendant(of: boxFor('account_number_again'), matching: find.byType(TextField)),
      '12346',
    );
    await tester.pump();

    expect(find.text(Strings.accountMismatch), findsOneWidget);
    expect(controller.draft.pendingAccount, isNull);

    await tester.enterText(
      find.descendant(of: boxFor('account_number_again'), matching: find.byType(TextField)),
      '12345',
    );
    await tester.pump();

    expect(controller.draft.pendingAccount, '12345');
  });

  wizardTest('family stops at the limit of the printed form', (tester) async {
    final controller = newController();
    await pump(tester, controller);
    await goToStep(tester, 5);

    await tester.tap(find.text(Strings.addPerson));
    await tester.pump();
    await tester.ensureVisible(find.text(Strings.addPerson));
    await tester.tap(find.text(Strings.addPerson));
    await tester.pump();

    expect(controller.draft.family, hasLength(2));
    expect(find.text(Strings.addPerson), findsNothing);
  });

  wizardTest('review lists what is missing and blocks submit', (tester) async {
    await pump(tester, newController());
    await goToStep(tester, 9);

    expect(find.text(Strings.stillNeeded), findsOneWidget);
    expect(find.text(Strings.aadhaarNumber), findsOneWidget);
    expect(find.text(Strings.photo), findsOneWidget);
    final submit = tester.widget<FilledButton>(find.widgetWithText(FilledButton, Strings.submit));
    expect(submit.onPressed, isNull);
  });

  wizardTest('tapping a missing item jumps to its step', (tester) async {
    await pump(tester, newController());
    await goToStep(tester, 9);

    await tester.ensureVisible(find.text(Strings.accountNumber));
    await tester.tap(find.text(Strings.accountNumber));
    await tester.pump();

    expect(find.text('${Strings.step} 4 / 9'), findsOneWidget);
  });

  wizardTest('a returned form shows why, and marks the field', (tester) async {
    final draft = Draft(
      clientId: 'c1',
      mppId: 'm1',
      mppLabel: 'x',
      rejectionReason: 'नाम गलत है',
      rejectedFields: ['applicant.full_name'],
    );
    await pump(tester, newController(draft: draft));

    expect(find.textContaining('नाम गलत है'), findsOneWidget);
    final box = find.descendant(of: boxFor('applicant.full_name'), matching: find.byType(LiftBox));
    expect(tester.widget<LiftBox>(box).hasError, isTrue);
  });

  wizardTest('the sync bar tells the facilitator where the work is', (tester) async {
    final controller = newController();
    await pump(tester, controller);
    expect(find.text(Strings.saved), findsOneWidget);

    controller
      ..state = SyncState.offline
      ..notifyListeners();
    await tester.pump();

    expect(find.text(Strings.offline), findsOneWidget);
  });

  Future<void> pumpWith(
    WidgetTester tester,
    DraftController controller,
    DeviceServices device,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: FormWizard(schema: schema, controller: controller, device: device),
      ),
    );
    await tester.pump();
  }

  wizardTest('a blurred photo is caught, and can be retaken or kept', (tester) async {
    final controller = newController();
    await pumpWith(tester, controller, const _FakeDevice(problem: PhotoProblem.blurry));
    await goToStep(tester, 7);

    await tester.tap(find.text(Strings.aadhaarFront));
    await tester.pumpAndSettle();
    expect(find.text(Strings.photoBlurry), findsOneWidget);
    expect(controller.draft.hasDocument('aadhaar_front'), isFalse);

    await tester.tap(find.text(Strings.keepAnyway));
    await tester.pumpAndSettle();

    expect(controller.draft.hasDocument('aadhaar_front'), isTrue);
    expect(find.text(Strings.photoDoubt), findsOneWidget);
  });

  wizardTest('a clear photo is kept without asking', (tester) async {
    final controller = newController();
    await pumpWith(tester, controller, const _FakeDevice());
    await goToStep(tester, 7);

    await tester.tap(find.text(Strings.passbook));
    await tester.pumpAndSettle();

    expect(find.text(Strings.photoBlurry), findsNothing);
    expect(controller.draft.hasDocument('passbook'), isTrue);
  });

  wizardTest('a returned form opens at the first correction', (tester) async {
    final draft = Draft(
      clientId: 'c1',
      mppId: 'm1',
      mppLabel: 'x',
      rejectionReason: 'IFSC गलत है',
      rejectedFields: ['bank.ifsc', 'nominee.name'],
    );
    await pump(tester, newController(draft: draft));

    expect(find.text('${Strings.step} 4 / 9'), findsOneWidget);
  });

  wizardTest('review shows each marked field, and whether it was changed', (tester) async {
    final draft = Draft(
      clientId: 'c1',
      mppId: 'm1',
      mppLabel: 'x',
      rejectionReason: 'नाम गलत है',
      rejectedFields: ['applicant.full_name', 'applicant.gender'],
    );
    await pump(tester, newController(draft: draft));
    await tester.enterText(
      find.descendant(of: boxFor('applicant.full_name'), matching: find.byType(TextField)),
      'सीता देवी',
    );
    await goToStep(tester, 9);

    expect(find.text(Strings.toCorrect), findsOneWidget);
    expect(find.text(Strings.corrected), findsOneWidget);
    expect(find.text(Strings.notCorrected), findsOneWidget);
  });

  wizardTest('review shows every step as done or with what is left', (tester) async {
    await pump(tester, newController());
    await goToStep(tester, 9);

    expect(find.text(Strings.checklist), findsOneWidget);
    expect(find.byKey(const ValueKey('checklist.0')), findsOneWidget);
    expect(find.byKey(const ValueKey('checklist.7')), findsOneWidget);
    expect(find.textContaining(Strings.stepLeft), findsWidgets);
  });

  wizardTest('a complete IFSC fills the bank and branch', (tester) async {
    final controller = newController();
    await tester.pumpWidget(
      MaterialApp(
        home: FormWizard(schema: schema, controller: controller, device: const _FakeDevice()),
      ),
    );
    await tester.pump();
    await goToStep(tester, 4);

    await tester.enterText(
      find.descendant(of: boxFor('bank.ifsc'), matching: find.byType(TextField)),
      'ubin0572161',
    );
    await tester.pumpAndSettle();

    expect(controller.draft.section('bank')['ifsc'], 'UBIN0572161');
    expect(controller.draft.section('bank')['bank_name'], 'Union Bank of India');
    expect(controller.draft.section('bank')['branch_name'], 'Siyarha');
  });

  wizardTest("the MPP's place shows filled, locked and marked as from the MPP", (tester) async {
    await pump(tester, newController(draft: placedDraft()), withSchema: placeSchema);
    await goToStep(tester, 2);

    final tehsil = boxFor('address.tehsil');
    expect(find.descendant(of: tehsil, matching: find.text('Gyanpur')), findsOneWidget);
    expect(find.descendant(of: tehsil, matching: find.byType(TextField)), findsNothing);
    expect(find.descendant(of: tehsil, matching: find.byIcon(Icons.lock_outline)), findsOneWidget);
    expect(find.descendant(of: tehsil, matching: find.text(Strings.fromMpp)), findsOneWidget);
    expect(find.byType(LockedBox), findsNWidgets(2));
  });

  wizardTest('what the MPP does not know is typed as usual', (tester) async {
    final controller = newController(draft: placedDraft());
    await pump(tester, controller, withSchema: placeSchema);
    await goToStep(tester, 2);

    await tester.enterText(
      find.descendant(of: boxFor('address.post_office'), matching: find.byType(TextField)),
      'Mondh',
    );

    expect(controller.draft.section('address')['post_office'], 'Mondh');
    expect(controller.draft.section('address')['tehsil'], 'Gyanpur');
  });

  wizardTest("an Aadhaar scan leaves the MPP's place alone", (tester) async {
    final controller = newController(draft: placedDraft());
    final qr = secureQr(const [
      'V2',
      '3',
      '123420190101',
      'Test Applicant',
      '15-01-1984',
      'F',
      'W/O: Test Husband',
      'Bhadohi',
      '',
      '12',
      'Sugapur',
      '110001',
      'Mondh',
      'Uttar Pradesh',
      '',
      'Bhadohi',
      'Sugapur',
    ]);
    await pump(
      tester,
      controller,
      withSchema: placeSchema,
      device: _FakeDevice(qr: qr),
    );

    await tester.tap(find.text(Strings.scanAadhaar));
    await tester.pumpAndSettle();

    final address = controller.draft.section('address');
    expect(controller.draft.section('applicant')['full_name'], 'Test Applicant');
    expect(address['pincode'], '221406');
    expect(address['tehsil'], 'Gyanpur');
    expect(address['house_number'], '12');
    expect(address['post_office'], 'Mondh');
  });

  wizardTest('a place from the MPP never shows as still needed', (tester) async {
    await pump(tester, newController(draft: placedDraft()), withSchema: placeSchema);
    await goToStep(tester, 9);

    expect(find.text(Strings.stillNeeded), findsOneWidget);
    expect(find.widgetWithText(ListTile, 'तहसील'), findsNothing);
    expect(find.widgetWithText(ListTile, 'पोस्ट ऑफिस'), findsOneWidget);
  });

  test('a returned form takes what the MPP fills from the server', () {
    final draft = Draft.fromServer({
      'id': 's1',
      'client_id': 'c1',
      'mpp': 'm1',
      'mpp_code': '1305',
      'mpp_name': 'Dudwa',
      'version': 3,
      'status': 'rejected',
      'data': <String, dynamic>{},
      'aadhaar_last4': '',
      'account_last4': '',
      'rejection_reason': '',
      'rejected_fields': <String>[],
      'mpp_place': {'tehsil': 'Gyanpur', 'post_office': ''},
    });

    expect(draft.place, {'tehsil': 'Gyanpur'});
    expect(Draft.decode(draft.encode()).place, {'tehsil': 'Gyanpur'});
  });
}

class _FakeDevice extends DeviceServices {
  const _FakeDevice({this.problem, this.qr});

  final PhotoProblem? problem;
  final String? qr;

  @override
  Future<String?> scanQr(BuildContext context) async => qr;

  @override
  Future<(String, String)?> lookupIfsc(String ifsc) async => ('Union Bank of India', 'Siyarha');

  @override
  Future<String?> takePhoto() async => '/tmp/photo.jpg';

  @override
  Future<PhotoProblem?> checkPhoto(String path) async => problem;
}
