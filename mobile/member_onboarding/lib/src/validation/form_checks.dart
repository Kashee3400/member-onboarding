import '../models/form_schema.dart';
import '../ui/strings.dart';

// The server's rules (backend/apps/applications/form.py, validate_for_submit), so a
// mistake shows while the member is still there. The patterns and ages come with the
// form; these are only for a form cached before the server sent them.
const _mobile = r'^[6-9]\d{9}$';
const _pincode = r'^[1-9]\d{5}$';
const _ifsc = r'^[A-Z]{4}0[A-Z0-9]{6}$';
const _email = r'^[^@\s]+@[^@\s]+\.[^@\s]+$';
const _minimumAge = 18;
const _maximumAge = 100;
const _oldestRelative = 120;

final _aadhaar = RegExp(r'^[2-9]\d{11}$');
final _account = RegExp(r'^\d{9,18}$');

const _d = [
  [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
  [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
  [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
  [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
  [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
  [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
  [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
  [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
  [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
  [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
];
const _p = [
  [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
  [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
  [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
  [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
  [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
  [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
  [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
  [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
];

/// The Verhoeff checksum printed into every Aadhaar number: one wrong digit fails it.
bool isValidAadhaar(String number) {
  if (!_aadhaar.hasMatch(number)) return false;
  var checksum = 0;
  final digits = number.split('').reversed.map(int.parse).toList();
  for (var position = 0; position < digits.length; position++) {
    checksum = _d[checksum][_p[position % 8][digits[position]]];
  }
  return checksum == 0;
}

String? checkAadhaar(String number) {
  if (number.isEmpty) return null;
  if (!_aadhaar.hasMatch(number)) return Strings.aadhaarInvalid;
  return isValidAadhaar(number) ? null : Strings.aadhaarChecksum;
}

String? checkAccount(String number) =>
    number.isEmpty || _account.hasMatch(number) ? null : Strings.accountInvalid;

/// Whole years, counted the way the server counts them.
int ageOn(DateTime born, DateTime today) {
  final beforeBirthday =
      today.month < born.month || (today.month == born.month && today.day < born.day);
  return today.year - born.year - (beforeBirthday ? 1 : 0);
}

double? _number(Object? value) => value is num ? value.toDouble() : double.tryParse('$value');

bool _blank(Object? value) => value == null || '$value'.trim().isEmpty;

/// What the server would refuse on submit, worked out on the phone. Empty answers are
/// left to the list of what is still needed.
class FormChecks {
  FormChecks(FormSchema schema, {DateTime Function()? now}) : _now = now ?? DateTime.now {
    for (final section in schema.sections) {
      for (final field in section.fields) {
        _specs['${section.key}.${field.key}'] = field;
      }
    }
  }

  final DateTime Function() _now;
  final _specs = <String, FormFieldSpec>{};

  RegExp _pattern(String path, String fallback) => RegExp(_specs[path]?.pattern ?? fallback);

  DateTime get _today {
    final now = _now();
    return DateTime(now.year, now.month, now.day);
  }

  /// The problem with one answer, judged with the rest of [data] as it stands.
  String? field(String section, String key, Map<String, dynamic> data) {
    final values = (data[section] as Map?)?.cast<String, dynamic>() ?? const {};
    final value = values[key];
    final path = '$section.$key';

    switch (path) {
      case 'applicant.date_of_birth':
        if (_blank(value)) return null;
        final born = DateTime.tryParse('$value');
        if (born == null) return Strings.dateInvalid;
        final age = ageOn(born, _today);
        if (age < (_specs[path]?.minAge ?? _minimumAge)) return Strings.applicantTooYoung;
        if (age > (_specs[path]?.maxAge ?? _maximumAge)) return Strings.applicantTooOld;
        return null;
      case 'address.mobile':
        return _blank(value) || _pattern(path, _mobile).hasMatch('$value')
            ? null
            : Strings.mobileInvalid;
      case 'address.pincode':
        return _blank(value) || _pattern(path, _pincode).hasMatch('$value')
            ? null
            : Strings.pincodeInvalid;
      case 'address.email':
        return _blank(value) || _pattern(path, _email).hasMatch('$value'.trim())
            ? null
            : Strings.emailInvalid;
      case 'bank.ifsc':
        return _blank(value) || _pattern(path, _ifsc).hasMatch('$value'.trim().toUpperCase())
            ? null
            : Strings.ifscInvalid;
      case 'animals.production_lpd':
        if (_blank(value)) return null;
        final production = _number(value);
        if (production == null) return Strings.notANumber;
        return production <= 0 ? Strings.productionNeeded : null;
      case 'animals.consumption_lpd':
        if (_blank(value)) return null;
        final consumption = _number(value);
        if (consumption == null) return Strings.notANumber;
        if (consumption < 0) return Strings.notANumber;
        final production = _number(values['production_lpd']);
        return production != null && consumption > production ? Strings.consumptionTooHigh : null;
      case 'nominee.guardian_name':
        final born = DateTime.tryParse('${values['date_of_birth'] ?? ''}');
        if (born == null) return null;
        final adult =
            ageOn(born, _today) >= (_specs['nominee.date_of_birth']?.adultAge ?? _minimumAge);
        if (!adult && _blank(value)) return Strings.guardianNeeded;
        if (adult && !_blank(value)) return Strings.guardianNotNeeded;
        return null;
      case 'nominee.date_of_birth':
        return _blank(value) || DateTime.tryParse('$value') != null ? null : Strings.dateInvalid;
    }
    return null;
  }

  /// A family member's age, which the server takes from 0 to 120.
  String? familyAge(Object? value) {
    if (_blank(value)) return null;
    final age = _number(value);
    return age == null || age < 0 || age > _oldestRelative ? Strings.familyAgeInvalid : null;
  }

  /// Every problem in the form, as {"section.field": message}, for the review step.
  Map<String, String> all(Map<String, dynamic> data) {
    final problems = <String, String>{};
    for (final path in const [
      'applicant.date_of_birth',
      'address.mobile',
      'address.pincode',
      'address.email',
      'animals.production_lpd',
      'animals.consumption_lpd',
      'bank.ifsc',
      'nominee.date_of_birth',
      'nominee.guardian_name',
    ]) {
      final dot = path.indexOf('.');
      final problem = field(path.substring(0, dot), path.substring(dot + 1), data);
      if (problem != null) problems[path] = problem;
    }

    final animals = (data['animals'] as Map?)?.cast<String, dynamic>() ?? const {};
    final counted = animals.entries
        .where((entry) => !entry.key.endsWith('_lpd'))
        .fold<int>(0, (total, entry) => total + (_number(entry.value) ?? 0).truncate());
    if (counted == 0) problems['animals.indigenous_heifer'] = Strings.noAnimals;

    final family = data['family'];
    if (family is List) {
      for (final (index, person) in family.indexed) {
        if (person is! Map) continue;
        final problem = familyAge(person['age']);
        if (problem != null) problems['family.$index.age'] = problem;
      }
    }
    return problems;
  }
}
