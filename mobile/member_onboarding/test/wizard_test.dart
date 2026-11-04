import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:member_onboarding/src/api/api_client.dart';
import 'package:member_onboarding/src/api/onboarding_api.dart';
import 'package:member_onboarding/src/config.dart';
import 'package:member_onboarding/src/models/draft.dart';
import 'package:member_onboarding/src/models/form_schema.dart';
import 'package:member_onboarding/src/storage/document_vault.dart';
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
    vault: MemoryDocumentVault(),
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
  bool inOrder = false,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: FormWizard(
        schema: withSchema ?? schema,
        controller: controller,
        device: device,
        stepsInOrder: inOrder,
      ),
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

/// Jumps by the step chips; steps count from 1, as the screen shows them.
Future<void> goToStep(WidgetTester tester, int step) async {
  await tester.tap(find.byKey(ValueKey('stepchip.${step - 1}')));
  await tester.pump();
}

/// The member's own details are the second step, after the documents.
Future<void> pumpOnMember(WidgetTester tester, DraftController controller) async {
  await pump(tester, controller);
  await goToStep(tester, 2);
}

void main() {
  wizardTest('labels come from the server, in Hindi', (tester) async {
    await pumpOnMember(tester, newController());

    expect(find.text('आवेदक'), findsOneWidget);
    expect(find.textContaining('पूरा नाम'), findsOneWidget);
  });

  wizardTest('optional fields say so', (tester) async {
    await pumpOnMember(tester, newController());
    expect(find.textContaining(Strings.optional), findsOneWidget);
  });

  wizardTest('typing saves into the draft', (tester) async {
    final controller = newController();
    await pumpOnMember(tester, controller);

    await tester.enterText(
      find.descendant(of: boxFor('applicant.full_name'), matching: find.byType(TextField)),
      'सीता',
    );

    expect(controller.draft.section('applicant')['full_name'], 'सीता');
  });

  wizardTest('Next stays on an unfinished step and says what is missing', (tester) async {
    await pump(tester, newController(), inOrder: true);

    await tester.tap(find.text(Strings.next));
    await tester.pump();

    expect(find.text('${Strings.step} 1 / 9'), findsOneWidget);
    expect(find.byKey(const ValueKey('step.still_to_fill')), findsOneWidget);
    expect(find.text('• ${Strings.photo}'), findsOneWidget);
  });

  wizardTest('a step chip cannot skip past an unfinished step', (tester) async {
    await pump(tester, newController(), inOrder: true);

    await goToStep(tester, 5);

    expect(find.text('${Strings.step} 1 / 9'), findsOneWidget);
  });

  wizardTest('a finished step lets Next go on, and empty fields say they are needed', (tester) async {
    final controller = newController();
    for (final type in ['photo', 'aadhaar_front', 'aadhaar_back', 'passbook']) {
      controller.draft.uploadedDocuments.add(type);
    }
    await pump(tester, controller, inOrder: true);

    await tester.tap(find.text(Strings.next));
    await tester.pump();
    expect(find.text('आवेदक'), findsOneWidget);

    await tester.tap(find.text(Strings.next));
    await tester.pump();
    expect(find.text('${Strings.step} 2 / 9'), findsOneWidget);
    expect(
      find.descendant(of: boxFor('applicant.full_name'), matching: find.text(Strings.required)),
      findsOneWidget,
    );

    // Back is always open.
    await tester.tap(find.text(Strings.back));
    await tester.pump();
    expect(find.text('${Strings.step} 1 / 9'), findsOneWidget);
  });

  wizardTest('the form has nine short steps', (tester) async {
    await pump(tester, newController());
    expect(find.text('${Strings.step} 1 / 9'), findsOneWidget);
  });

  wizardTest('an active field lifts and an idle one stays flat', (tester) async {
    await pumpOnMember(tester, newController());
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
    await pumpOnMember(tester, newController());
    final box = tester.widget<AnimatedContainer>(
      find.descendant(of: boxFor('applicant.full_name'), matching: find.byType(AnimatedContainer)),
    );
    expect((box.decoration! as BoxDecoration).borderRadius, isNull);
  });

  wizardTest('the Aadhaar box takes only digits, twelve at most', (tester) async {
    final controller = newController();
    await pumpOnMember(tester, controller);

    await tester.enterText(
      find.descendant(of: boxFor('aadhaar_number'), matching: find.byType(TextField)),
      '2341abc234123469999',
    );

    expect(controller.draft.pendingAadhaar, '234123412346');
  });

  wizardTest('a short list of choices is one tap on a chip', (tester) async {
    final controller = newController();
    await pumpOnMember(tester, controller);

    await tester.tap(find.widgetWithText(ChoiceChip, 'महिला'));
    await tester.pumpAndSettle();

    expect(controller.draft.section('applicant')['gender'], 'female');
  });

  wizardTest('the bank number must match when typed twice', (tester) async {
    final controller = newController();
    await pump(tester, controller);
    await goToStep(tester, 5);

    await tester.enterText(
      find.descendant(of: boxFor('account_number'), matching: find.byType(TextField)),
      '656302010000644',
    );
    await tester.enterText(
      find.descendant(of: boxFor('account_number_again'), matching: find.byType(TextField)),
      '656302010000645',
    );
    await tester.pump();

    expect(find.text(Strings.accountMismatch), findsOneWidget);
    expect(controller.draft.pendingAccount, isNull);

    await tester.enterText(
      find.descendant(of: boxFor('account_number_again'), matching: find.byType(TextField)),
      '656302010000644',
    );
    await tester.pump();

    expect(controller.draft.pendingAccount, '656302010000644');
  });

  wizardTest('animals are a grid with a total per column', (tester) async {
    final controller = newController();
    controller.draft.data['animals'] = {'buffalo_dry': 2};
    await pump(tester, controller);
    await goToStep(tester, 4);

    for (final label in [Strings.heifer, Strings.dry, Strings.inMilk, Strings.buffalo, Strings.total]) {
      expect(find.text(label), findsOneWidget);
    }
    await tester.enterText(
      find.descendant(of: find.byKey(const ValueKey('animals.crossbred_dry')), matching: find.byType(TextField)),
      '3',
    );
    await tester.pump();

    expect(controller.draft.section('animals')['crossbred_dry'], '3');
    expect(tester.widget<Text>(find.byKey(const ValueKey('animals.total.dry'))).data, '5');
  });

  wizardTest('family stops at the limit of the printed form', (tester) async {
    final controller = newController();
    await pump(tester, controller);
    await goToStep(tester, 6);

    for (final name in ['राम', 'श्याम']) {
      await tester.ensureVisible(find.widgetWithText(OutlinedButton, Strings.addPerson));
      await tester.tap(find.widgetWithText(OutlinedButton, Strings.addPerson));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.descendant(of: boxFor('person.name'), matching: find.byType(TextField)),
        name,
      );
      await tester.tap(find.widgetWithText(ChoiceChip, 'पति'));
      await tester.tap(find.widgetWithText(ChoiceChip, 'पुरुष'));
      await tester.enterText(
        find.descendant(of: boxFor('person.age'), matching: find.byType(TextField)),
        '40',
      );
      await tester.pump();
      await tester.tap(find.text(Strings.savePerson));
      await tester.pumpAndSettle();
    }

    expect(controller.draft.family, hasLength(2));
    expect(controller.draft.family.first['name'], 'राम');
    expect(find.widgetWithText(OutlinedButton, Strings.addPerson), findsNothing);
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

  wizardTest('an unconfirmed mobile and email are still needed', (tester) async {
    final controller = newController();
    controller.draft.data['address'] = {'mobile': '9876543210', 'email': 'a@b.in'};
    await pump(tester, controller);
    await goToStep(tester, 9);

    expect(find.text(Strings.mobileNotVerified), findsOneWidget);
    expect(find.text(Strings.emailNotVerified), findsOneWidget);

    final confirmed = newController();
    confirmed.draft
      ..data['address'] = {'mobile': '9876543210', 'email': 'a@b.in'}
      ..mobileVerified = true
      ..emailVerified = true;
    await tester.pumpWidget(const SizedBox());
    await pump(tester, confirmed);
    await goToStep(tester, 9);

    expect(find.text(Strings.mobileNotVerified), findsNothing);
    expect(find.text(Strings.emailNotVerified), findsNothing);
  });

  wizardTest('tapping a missing item jumps to its step', (tester) async {
    await pump(tester, newController());
    await goToStep(tester, 9);

    await tester.ensureVisible(find.text(Strings.accountNumber));
    await tester.tap(find.text(Strings.accountNumber));
    await tester.pump();

    expect(find.text('${Strings.step} 5 / 9'), findsOneWidget);
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
        home: FormWizard(
          schema: schema,
          controller: controller,
          device: device,
          stepsInOrder: false,
        ),
      ),
    );
    await tester.pump();
  }

  wizardTest('a blurred photo is caught, and can be retaken or kept', (tester) async {
    final controller = newController();
    await pumpWith(tester, controller, const _FakeDevice(problem: PhotoProblem.blurry));

    await tester.tap(find.text(Strings.aadhaarFront));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('source.camera')));
    await tester.pumpAndSettle();
    expect(find.text(Strings.photoBlurry), findsOneWidget);
    expect(controller.draft.hasDocument('aadhaar_front'), isFalse);

    await tester.tap(find.text(Strings.keepAnyway));
    await tester.pumpAndSettle();

    expect(controller.draft.hasDocument('aadhaar_front'), isTrue);
    expect(find.text(Strings.checkPhoto), findsOneWidget);
  });

  wizardTest('a clear photo is kept without asking', (tester) async {
    final controller = newController();
    await pumpWith(tester, controller, const _FakeDevice());

    await tester.tap(find.text(Strings.passbook));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('source.camera')));
    await tester.pumpAndSettle();

    expect(find.text(Strings.photoBlurry), findsNothing);
    expect(controller.draft.hasDocument('passbook'), isTrue);
  });

  wizardTest('every photo is cut to its document before it is checked', (tester) async {
    crops.clear();
    checked.clear();
    final controller = newController();
    await pumpWith(tester, controller, const _FakeDevice());

    await tester.tap(find.text(Strings.passbook));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('source.gallery')));
    await tester.pumpAndSettle();

    expect(crops, [('passbook', '/tmp/gallery.jpg')]);
    expect(checked, ['/tmp/gallery.jpg']);
    expect(controller.draft.hasDocument('passbook'), isTrue);
  });

  test('each document has the shape it is printed in', () {
    final aadhaar = DeviceServices.cropRatios['aadhaar_front']!;
    expect(aadhaar.ratioX / aadhaar.ratioY, closeTo(1.585, 0.001));
    expect(DeviceServices.cropRatios['aadhaar_back'], DeviceServices.cropRatios['aadhaar_front']);
    final photo = DeviceServices.cropRatios['photo']!;
    expect(photo.ratioX / photo.ratioY, 0.75);
    expect(DeviceServices.cropRatios['passbook'], isNull);
  });

  wizardTest('a document can come from the gallery too', (tester) async {
    final controller = newController();
    await pumpWith(tester, controller, const _FakeDevice());

    await tester.tap(find.text(Strings.passbook));
    await tester.pumpAndSettle();
    expect(find.text(Strings.fromGallery), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('source.gallery')));
    await tester.pumpAndSettle();

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

    expect(find.text('${Strings.step} 5 / 9'), findsOneWidget);
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

  Draft returnedWithNotes() => Draft(
    clientId: 'c1',
    mppId: 'm1',
    mppLabel: 'x',
    rejectionReason: 'कुछ फ़ील्ड गलत हैं',
    rejectedFields: ['applicant.full_name', 'applicant.gender'],
    rejectedFieldNotes: {'applicant.full_name': 'आधार कार्ड से मेल नहीं खाता'},
  );

  wizardTest('a returned field shows the reviewer\'s own reason', (tester) async {
    await pump(tester, newController(draft: returnedWithNotes()));

    expect(
      find.descendant(
        of: boxFor('applicant.full_name'),
        matching: find.text('${Strings.rejectedBecause}: आधार कार्ड से मेल नहीं खाता'),
      ),
      findsOneWidget,
    );
    // A field sent back without its own reason keeps the general words.
    expect(
      find.descendant(of: boxFor('applicant.gender'), matching: find.text(Strings.rejectedBecause)),
      findsOneWidget,
    );
  });

  wizardTest('review lists each field with the reason it was sent back', (tester) async {
    await pump(tester, newController(draft: returnedWithNotes()));
    await goToStep(tester, 9);

    expect(
      find.descendant(
        of: find.byKey(const ValueKey('correction.applicant.full_name')),
        matching: find.text('आधार कार्ड से मेल नहीं खाता · ${Strings.notCorrected}'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('correction.applicant.gender')),
        matching: find.text(Strings.notCorrected),
      ),
      findsOneWidget,
    );
  });

  test('field reasons come from the server and survive the device store', () {
    Map<String, dynamic> server({Object? notes}) => {
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
      'rejection_reason': 'x',
      'rejected_fields': <String>['bank.ifsc', 'family'],
      'rejected_field_notes': ?notes,
    };

    final draft = Draft.fromServer(
      server(notes: {'bank.ifsc': ' Passbook says SBIN ', 'family': ''}),
    );
    expect(draft.noteFor('bank.ifsc'), 'Passbook says SBIN');
    expect(draft.noteFor('family'), isNull);
    expect(Draft.decode(draft.encode()).noteFor('bank.ifsc'), 'Passbook says SBIN');

    // A form sent back before reasons per field, and a draft an older app stored.
    final old = Draft.fromServer(server());
    expect(old.rejectedFieldNotes, isEmpty);
    final stored = old.toJson()..remove('rejected_field_notes');
    expect(Draft.fromJson(stored).rejectedFieldNotes, isEmpty);
  });

  wizardTest('the review says what the member pays, before the signature', (tester) async {
    final withFee = FormSchema(
      version: 1,
      maxFamilyMembers: 2,
      familyGenders: schema.familyGenders,
      familyRelations: schema.familyRelations,
      sections: schema.sections,
      fee: const MemberFee(admissionFee: 50, shareCount: 5, sharePrice: 100, total: 550),
    );
    await pump(tester, newController(), withSchema: withFee);
    await goToStep(tester, 9);

    expect(find.byKey(const ValueKey('checklist.0')), findsNothing);
    // Only the admission fee is paid now; the shares come out of the milk money.
    expect(find.text('₹550'), findsNothing);
    expect(find.text('₹50'), findsNWidgets(2));
    expect(find.textContaining(Strings.sharesFromMilk), findsOneWidget);
    expect(
      tester.getTopLeft(find.byKey(const ValueKey('review.fee'))).dy,
      lessThan(tester.getTopLeft(find.byKey(const ValueKey('review.signature'))).dy),
    );
  });

  wizardTest('a complete IFSC fills the bank and branch', (tester) async {
    final controller = newController();
    await tester.pumpWidget(
      MaterialApp(
        home: FormWizard(
          schema: schema,
          controller: controller,
          device: const _FakeDevice(),
          stepsInOrder: false,
        ),
      ),
    );
    await tester.pump();
    await goToStep(tester, 5);

    await tester.enterText(
      find.descendant(of: boxFor('bank.ifsc'), matching: find.byType(TextField)),
      'ubin0572161',
    );
    await tester.pumpAndSettle();

    expect(controller.draft.section('bank')['ifsc'], 'UBIN0572161');
    expect(controller.draft.section('bank')['bank_name'], 'Union Bank of India');
    expect(controller.draft.section('bank')['branch_name'], 'Siyarha');
  });

  wizardTest("the MPP's place shows filled and locked, in one card", (tester) async {
    await pump(tester, newController(draft: placedDraft()), withSchema: placeSchema);
    await goToStep(tester, 3);

    expect(find.text(Strings.fromMppTitle), findsOneWidget);
    expect(find.text('Gyanpur'), findsOneWidget);
    expect(find.text('221406'), findsOneWidget);
    expect(find.descendant(of: boxFor('address.tehsil'), matching: find.byType(TextField)), findsNothing);
  });

  wizardTest('what the MPP does not know is typed as usual', (tester) async {
    final controller = newController(draft: placedDraft());
    await pump(tester, controller, withSchema: placeSchema);
    await goToStep(tester, 3);

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
    await goToStep(tester, 2);

    await tester.tap(find.text(Strings.scanAadhaar));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('scan.consent')));
    await tester.pumpAndSettle();

    final address = controller.draft.section('address');
    expect(controller.draft.section('applicant')['full_name'], 'Test Applicant');
    expect(address['pincode'], '221406');
    expect(address['tehsil'], 'Gyanpur');
    expect(address['house_number'], '12');
    expect(address['post_office'], 'Mondh');
    // Kept for the server to check UIDAI's signature, and shown as waiting for it.
    expect(controller.draft.pendingAadhaarQr, qr);
    expect(find.text(Strings.aadhaarWaiting), findsOneWidget);
  });

  wizardTest('no scan without the member agreeing', (tester) async {
    final controller = newController(draft: placedDraft());
    await pump(
      tester,
      controller,
      withSchema: placeSchema,
      device: _FakeDevice(qr: '<PrintLetterBarcodeData name="Test Applicant"/>'),
    );
    await goToStep(tester, 2);

    await tester.tap(find.text(Strings.scanAadhaar));
    await tester.pumpAndSettle();
    expect(find.text(Strings.scanConsent), findsOneWidget);
    await tester.tap(find.text(Strings.scanConsentNo));
    await tester.pumpAndSettle();

    expect(controller.draft.section('applicant')['full_name'], isNull);
    expect(controller.draft.pendingAadhaarQr, isNull);
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

  wizardTest('the bank master is asked before the online lookup', (tester) async {
    final controller = newController();
    final asked = <String>[];
    await tester.pumpWidget(
      MaterialApp(
        home: FormWizard(
          schema: schema,
          controller: controller,
          device: const _FakeDevice(),
          stepsInOrder: false,
          findBranch: (ifsc) async {
            asked.add(ifsc);
            return ('State Bank of India', 'Bhadohi');
          },
        ),
      ),
    );
    await tester.pump();
    await goToStep(tester, 5);

    await tester.enterText(
      find.descendant(of: boxFor('bank.ifsc'), matching: find.byType(TextField)),
      'SBIN0001234',
    );
    await tester.pumpAndSettle();

    expect(asked, ['SBIN0001234']);
    expect(controller.draft.section('bank')['bank_name'], 'State Bank of India');
    expect(controller.draft.section('bank')['branch_name'], 'Bhadohi');
  });

  wizardTest('a retired choice still reads on an older form, but is not offered', (tester) async {
    final withRetired = FormSchema(
      version: 1,
      maxFamilyMembers: 2,
      familyGenders: schema.familyGenders,
      familyRelations: schema.familyRelations,
      sections: [
        section('applicant', 'आवेदक', const [
          FormFieldSpec(
            key: 'gender',
            label: 'लिंग',
            type: 'choice',
            required: true,
            options: [ChoiceOption(value: 'female', label: 'महिला')],
            retired: [ChoiceOption(value: 'other', label: 'अन्य')],
          ),
        ]),
        ...schema.sections.skip(1),
      ],
    );
    final controller = newController()..setValue('applicant', 'gender', 'other');
    await tester.pumpWidget(
      MaterialApp(
        home: FormWizard(schema: withRetired, controller: controller, stepsInOrder: false),
      ),
    );
    await tester.pump();
    await goToStep(tester, 2);

    // Today's choice is offered; the old one shows, chosen, and cannot be picked again.
    expect(find.widgetWithText(ChoiceChip, 'महिला'), findsOneWidget);
    final old = tester.widget<ChoiceChip>(find.widgetWithText(ChoiceChip, 'अन्य'));
    expect(old.selected, isTrue);
    expect(old.onSelected, isNull);
  });

  nomineeTests();

  wizardTest('a relation typed before it was a list shows as typed', (tester) async {
    final controller = newController();
    controller.draft.data['family'] = [
      {'name': 'राम', 'gender': 'male', 'age': 40, 'relation': 'Grandson'},
    ];
    await pump(tester, controller);
    await goToStep(tester, 6);

    expect(find.textContaining('Grandson'), findsOneWidget);
  });
}


/// The test form with a nominee who has a relation and a date of birth.
final nomineeSchema = FormSchema(
  version: 1,
  maxFamilyMembers: 6,
  familyGenders: schema.familyGenders,
  familyRelations: schema.familyRelations,
  sections: [
    for (final item in schema.sections)
      if (item.key == 'nominee')
        section('nominee', 'नामित', const [
          FormFieldSpec(key: 'name', label: 'नामित का नाम', type: 'text', required: true),
          FormFieldSpec(
            key: 'relation',
            label: 'संबंध',
            type: 'choice',
            required: true,
            options: [ChoiceOption(value: 'husband', label: 'पति')],
          ),
          FormFieldSpec(key: 'date_of_birth', label: 'जन्म तिथि', type: 'date', required: true),
        ])
      else
        item,
  ],
);

DraftController familyController() => newController()
  ..draft.data['family'] = [
    {'name': 'Ram', 'gender': 'male', 'age': '40', 'relation': 'husband'},
  ];

void nomineeTests() {
  wizardTest('a nominee chosen from the household fills in, born 1 January', (tester) async {
    final controller = familyController();
    await pump(tester, controller, withSchema: nomineeSchema);
    await goToStep(tester, 7);

    await tester.tap(find.byKey(const ValueKey('nominee.from.0')));
    await tester.pump();

    final nominee = controller.draft.section('nominee');
    expect(nominee['name'], 'Ram');
    expect(nominee['relation'], 'husband');
    expect(nominee['date_of_birth'], '${DateTime.now().year - 40}-01-01');
  });

  wizardTest("a household member's new age moves the nominee's year of birth", (tester) async {
    final controller = familyController()
      ..draft.data['nominee'] = {'name': 'Ram', 'date_of_birth': '${DateTime.now().year - 40}-01-01'};
    await pump(tester, controller, withSchema: nomineeSchema);
    await goToStep(tester, 6);

    await tester.tap(find.byKey(const ValueKey('family.0')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.descendant(of: boxFor('person.age'), matching: find.byType(TextField)),
      '45',
    );
    await tester.pump();
    await tester.tap(find.text(Strings.savePerson));
    await tester.pumpAndSettle();

    expect(controller.draft.family.single['age'], '45');
    expect(controller.draft.section('nominee')['date_of_birth'], '${DateTime.now().year - 45}-01-01');
  });

  wizardTest('the member signs on the review, not with the photos', (tester) async {
    await pump(tester, newController());
    expect(find.byKey(const ValueKey('review.signature')), findsNothing);

    await goToStep(tester, 9);

    expect(find.byKey(const ValueKey('review.signature')), findsOneWidget);
    expect(find.text(Strings.signHere), findsOneWidget);
  });

  wizardTest('the documents come first, as photo tiles', (tester) async {
    await pump(tester, newController());

    expect(find.text('${Strings.step} 1 / 9'), findsOneWidget);
    for (final type in ['photo', 'aadhaar_front', 'aadhaar_back', 'passbook']) {
      expect(find.byKey(ValueKey('document.$type')), findsOneWidget);
    }
    expect(find.text('0 / 4'), findsOneWidget);
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
  Future<String?> choosePhoto() async => '/tmp/gallery.jpg';

  @override
  Future<String> cropPhoto(
    String path, {
    required String type,
    required String title,
    required Color color,
  }) async {
    crops.add((type, path));
    return path;
  }

  @override
  Future<PhotoProblem?> checkPhoto(String path) async {
    checked.add(path);
    return problem;
  }
}

/// What the fake device was asked to crop and check, in order.
final crops = <(String, String)>[];
final checked = <String>[];
