import 'package:flutter_test/flutter_test.dart';
import 'package:member_onboarding/src/models/form_schema.dart';
import 'package:member_onboarding/src/ui/strings.dart';
import 'package:member_onboarding/src/validation/form_checks.dart';

FormSchema schemaWith(List<FormSectionSpec> sections) => FormSchema(
  version: 1,
  sections: sections,
  maxFamilyMembers: 6,
  familyGenders: const [],
  familyRelations: const [],
);

final plain = FormChecks(schemaWith(const []), now: () => DateTime(2026, 11, 3));

String? check(String section, String key, Map<String, dynamic> values) =>
    plain.field(section, key, {section: values});

void main() {
  test('Aadhaar numbers pass the same checksum the server uses', () {
    expect(isValidAadhaar('234123412346'), isTrue);
    expect(isValidAadhaar('496858245229'), isTrue);
    expect(checkAadhaar('234123412345'), Strings.aadhaarChecksum);
    expect(checkAadhaar('123412341234'), Strings.aadhaarInvalid);
    expect(checkAadhaar('2341'), Strings.aadhaarInvalid);
    expect(checkAadhaar(''), isNull);
  });

  test('an account number has 9 to 18 digits', () {
    expect(checkAccount('656302010000644'), isNull);
    expect(checkAccount('12345'), Strings.accountInvalid);
  });

  test('mobile, PIN code, IFSC and email follow the server', () {
    expect(check('address', 'mobile', {'mobile': '9876543210'}), isNull);
    expect(check('address', 'mobile', {'mobile': '5876543210'}), Strings.mobileInvalid);
    expect(check('address', 'mobile', {'mobile': '98765'}), Strings.mobileInvalid);
    expect(check('address', 'pincode', {'pincode': '221406'}), isNull);
    expect(check('address', 'pincode', {'pincode': '021406'}), Strings.pincodeInvalid);
    expect(check('bank', 'ifsc', {'ifsc': 'ubin0572161'}), isNull);
    expect(check('bank', 'ifsc', {'ifsc': 'UBIN1572161'}), Strings.ifscInvalid);
    expect(check('address', 'email', {'email': 'a@b.in'}), isNull);
    expect(check('address', 'email', {'email': 'a@b'}), Strings.emailInvalid);
    expect(check('address', 'email', {'email': ''}), isNull);
  });

  test('a pattern sent with the form wins over the built-in one', () {
    final checks = FormChecks(
      schemaWith([
        const FormSectionSpec(
          key: 'address',
          title: 'पता',
          fields: [
            FormFieldSpec(
              key: 'mobile',
              label: 'मोबाइल',
              type: 'text',
              required: true,
              pattern: r'^9\d{9}$',
            ),
          ],
        ),
      ]),
    );
    expect(
      checks.field('address', 'mobile', {
        'address': {'mobile': '8123456789'},
      }),
      Strings.mobileInvalid,
    );
  });

  test('the applicant is at least 18 and not over 100', () {
    String? born(String date) => check('applicant', 'date_of_birth', {'date_of_birth': date});
    expect(born('1984-01-15'), isNull);
    expect(born('2008-11-03'), isNull);
    expect(born('2008-11-04'), Strings.applicantTooYoung);
    expect(born('1920-01-01'), Strings.applicantTooOld);
  });

  test('milk figures are numbers and consumption stays within production', () {
    expect(check('animals', 'production_lpd', {'production_lpd': 'बारह'}), Strings.notANumber);
    expect(check('animals', 'production_lpd', {'production_lpd': '0'}), Strings.productionNeeded);
    expect(
      check('animals', 'consumption_lpd', {'production_lpd': '4', 'consumption_lpd': '6'}),
      Strings.consumptionTooHigh,
    );
    expect(
      check('animals', 'consumption_lpd', {'production_lpd': 12, 'consumption_lpd': '4.5'}),
      isNull,
    );
  });

  test('a minor nominee needs a guardian, an adult has none', () {
    expect(
      check('nominee', 'guardian_name', {'date_of_birth': '2020-01-01'}),
      Strings.guardianNeeded,
    );
    expect(
      check('nominee', 'guardian_name', {'date_of_birth': '2020-01-01', 'guardian_name': 'X'}),
      isNull,
    );
    expect(
      check('nominee', 'guardian_name', {'date_of_birth': '1980-01-01', 'guardian_name': 'X'}),
      Strings.guardianNotNeeded,
    );
  });

  test('the review list gathers every problem, family ages and animals too', () {
    final problems = plain.all({
      'address': {'mobile': '12345'},
      'animals': {'production_lpd': '5'},
      'family': [
        {'name': 'राम', 'age': '200'},
        {'name': 'सीता', 'age': '40'},
      ],
    });
    expect(problems, {
      'address.mobile': Strings.mobileInvalid,
      'animals.indigenous_heifer': Strings.noAnimals,
      'family.0.age': Strings.familyAgeInvalid,
    });
  });

  test('the form brings its rules from the server', () {
    final field = FormFieldSpec.fromJson({
      'key': 'date_of_birth',
      'label': 'Date of birth',
      'type': 'date',
      'required': true,
      'min_age': 18,
      'max_age': 100,
      'pattern': r'^\d$',
    });
    expect(field.minAge, 18);
    expect(field.maxAge, 100);
    expect(field.pattern, r'^\d$');
  });
}
