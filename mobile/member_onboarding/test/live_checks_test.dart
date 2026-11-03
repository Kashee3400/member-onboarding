import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:member_onboarding/src/models/draft.dart';
import 'package:member_onboarding/src/models/form_schema.dart';
import 'package:member_onboarding/src/ui/fields.dart';
import 'package:member_onboarding/src/ui/strings.dart';

import 'wizard_test.dart'
    show boxFor, goToStep, newController, pump, schema, section, text, wizardTest;

/// The test form, with the fields the phone checks while typing.
final checkedSchema = FormSchema(
  version: 1,
  maxFamilyMembers: 2,
  familyGenders: schema.familyGenders,
  familyRelations: schema.familyRelations,
  sections: [
    for (final item in schema.sections)
      if (item.key == 'applicant')
        section('applicant', 'आवेदक', [
          text('full_name', 'पूरा नाम'),
          const FormFieldSpec(
            key: 'date_of_birth',
            label: 'जन्म तिथि',
            type: 'date',
            required: true,
            minAge: 18,
            maxAge: 100,
          ),
        ])
      else if (item.key == 'address')
        section('address', 'पता', [text('mobile', 'मोबाइल'), text('tehsil', 'तहसील')])
      else
        item,
  ],
);

Finder input(String key) => find.descendant(of: boxFor(key), matching: find.byType(TextField));

Future<void> leaveField(WidgetTester tester) async {
  FocusManager.instance.primaryFocus?.unfocus();
  await tester.pump();
}

void main() {
  wizardTest('a half-typed mobile number is not judged until the box is left', (tester) async {
    await pump(tester, newController(), withSchema: checkedSchema);
    await goToStep(tester, 3);

    await tester.enterText(input('address.mobile'), '98765');
    await tester.pump();
    expect(find.text(Strings.mobileInvalid), findsNothing);

    await leaveField(tester);
    expect(find.text(Strings.mobileInvalid), findsOneWidget);
    final box = find.descendant(of: boxFor('address.mobile'), matching: find.byType(LiftBox));
    expect(tester.widget<LiftBox>(box).hasError, isTrue);
  });

  wizardTest('a complete but wrong mobile number is pointed out at once', (tester) async {
    await pump(tester, newController(), withSchema: checkedSchema);
    await goToStep(tester, 3);

    await tester.enterText(input('address.mobile'), '5876543210');
    await tester.pump();

    expect(find.text(Strings.mobileInvalid), findsOneWidget);
  });

  wizardTest('a right number shows nothing', (tester) async {
    await pump(tester, newController(), withSchema: checkedSchema);
    await goToStep(tester, 3);

    await tester.enterText(input('address.mobile'), '9876543210');
    await leaveField(tester);

    expect(find.text(Strings.mobileInvalid), findsNothing);
  });

  wizardTest('an Aadhaar number that fails the checksum is caught and not sent', (tester) async {
    final controller = newController();
    await pump(tester, controller, withSchema: checkedSchema);
    await goToStep(tester, 2);

    await tester.enterText(input('aadhaar_number'), '234123412345');
    await tester.pump();

    expect(find.text(Strings.aadhaarChecksum), findsOneWidget);
    expect(controller.draft.pendingAadhaar, isNull);
  });

  wizardTest('an under-age date of birth is shown under the field', (tester) async {
    final today = DateTime.now();
    final draft = Draft(
      clientId: 'c1',
      mppId: 'm1',
      mppLabel: 'x',
      data: {
        'applicant': {'date_of_birth': '${today.year - 10}-01-01'},
      },
    );
    await pump(tester, newController(draft: draft), withSchema: checkedSchema);
    await goToStep(tester, 2);

    expect(find.text(Strings.applicantTooYoung), findsOneWidget);
  });

  wizardTest('consumption over production is shown as soon as both are in', (tester) async {
    final draft = Draft(
      clientId: 'c1',
      mppId: 'm1',
      mppLabel: 'x',
      data: {
        'animals': {'production_lpd': '4', 'consumption_lpd': '6'},
      },
    );
    await pump(tester, newController(draft: draft), withSchema: checkedSchema);
    await goToStep(tester, 4);

    expect(find.text(Strings.consumptionTooHigh), findsOneWidget);
  });

  wizardTest('review lists the problems, one tap from their step, and never blocks moving on', (
    tester,
  ) async {
    final draft = Draft(
      clientId: 'c1',
      mppId: 'm1',
      mppLabel: 'x',
      data: {
        'address': {'mobile': '12345'},
        'animals': {'buffalo_heifer': 1},
      },
    );
    await pump(tester, newController(draft: draft), withSchema: checkedSchema);
    await goToStep(tester, 9);

    expect(find.text(Strings.pleaseCheck), findsOneWidget);
    final problem = find.byKey(const ValueKey('problem.address.mobile'));
    expect(problem, findsOneWidget);
    expect(
      find.descendant(of: problem, matching: find.text(Strings.mobileInvalid)),
      findsOneWidget,
    );

    await tester.ensureVisible(problem);
    await tester.tap(problem);
    await tester.pump();

    expect(find.text('${Strings.step} 3 / 9'), findsOneWidget);
  });
}
