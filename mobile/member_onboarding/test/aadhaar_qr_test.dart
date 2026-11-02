import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:member_onboarding/member_onboarding.dart';

String secureQr(List<String> fields) {
  final bytes = <int>[];
  for (final field in fields) {
    bytes
      ..addAll(latin1.encode(field))
      ..add(255);
  }
  final zipped = gzip.encode(bytes);
  final hex = zipped.map((byte) => byte.toRadixString(16).padLeft(2, '0')).join();
  return BigInt.parse(hex, radix: 16).toString();
}

void main() {
  const v2 = [
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
    '221406',
    'Mondh',
    'Uttar Pradesh',
    '',
    'Bhadohi',
    'Sugapur',
  ];

  test('reads a version 2 secure QR', () {
    final details = parseAadhaarQr(secureQr(v2))!;

    expect(details.name, 'Test Applicant');
    expect(details.dateOfBirth, '1984-01-15');
    expect(details.gender, 'female');
    expect(details.relationType, 'husband');
    expect(details.relationName, 'Test Husband');
    expect(details.houseNumber, '12');
    expect(details.pincode, '221406');
    expect(details.postOffice, 'Mondh');
    expect(details.state, 'Uttar Pradesh');
    expect(details.tehsil, 'Bhadohi');
  });

  test('a secure QR never gives the full Aadhaar number', () {
    expect(parseAadhaarQr(secureQr(v2))!.number, isNull);
  });

  test('reads a first version secure QR, which has no version marker', () {
    final details = parseAadhaarQr(secureQr(v2.sublist(1)))!;
    expect(details.name, 'Test Applicant');
    expect(details.gender, 'female');
  });

  test('reads the older XML code', () {
    const xml =
        '<?xml version="1.0"?><PrintLetterBarcodeData uid="234123412346" name="Test Applicant" '
        'gender="F" yob="1984" co="D/O: Test Father" house="12" po="Mondh" dist="Bhadohi" '
        'subdist="Bhadohi" state="Uttar Pradesh" pc="221406" dob="15/01/1984"/>';

    final details = parseAadhaarQr(xml)!;

    expect(details.number, '234123412346');
    expect(details.dateOfBirth, '1984-01-15');
    expect(details.relationType, 'father');
    expect(details.relationName, 'Test Father');
  });

  for (final bad in ['', 'hello', '12345', '<a/>', '99999999999999999999']) {
    test('anything else is simply not understood: "$bad"', () {
      expect(parseAadhaarQr(bad), isNull);
    });
  }
}
