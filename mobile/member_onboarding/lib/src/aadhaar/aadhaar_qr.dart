import 'dart:convert';
import 'dart:io';

/// What the card's QR code gives, to save typing. Always shown to the facilitator
/// to check: the QR's digital signature is not verified on the device.
class AadhaarDetails {
  const AadhaarDetails({
    required this.name,
    this.number,
    this.dateOfBirth,
    this.gender,
    this.relationType,
    this.relationName,
    this.houseNumber,
    this.postOffice,
    this.tehsil,
    this.district,
    this.state,
    this.pincode,
  });

  final String name;

  /// Only older QR codes hold the full number. Secure QR codes do not.
  final String? number;

  /// In `yyyy-mm-dd`, as the form stores it.
  final String? dateOfBirth;
  final String? gender;
  final String? relationType;
  final String? relationName;
  final String? houseNumber;
  final String? postOffice;
  final String? tehsil;
  final String? district;
  final String? state;
  final String? pincode;
}

const _separator = 255;
const _versionedFieldOffset = 3;

String? _orNull(String value) => value.trim().isEmpty ? null : value.trim();

String? _isoDate(String? value) {
  if (value == null) return null;
  final parts = value.split(RegExp(r'[-/]'));
  if (parts.length != 3 || parts[2].length != 4) return null;
  return '${parts[2]}-${parts[1].padLeft(2, '0')}-${parts[0].padLeft(2, '0')}';
}

String? _gender(String? value) => switch (value?.toUpperCase()) {
  'F' || 'FEMALE' => 'female',
  'M' || 'MALE' => 'male',
  'T' || 'OTHER' => 'other',
  _ => null,
};

/// Reads "W/O: Name" into the form's relation and name.
(String?, String?) _careOf(String? value) {
  if (value == null) return (null, null);
  final match = RegExp(
    r'^\s*([SDWC])\s*/?\s*O\s*:?\s*(.*)$',
    caseSensitive: false,
  ).firstMatch(value);
  if (match == null) return (null, _orNull(value));
  final relation = switch (match.group(1)!.toUpperCase()) {
    'W' => 'husband',
    'S' || 'D' => 'father',
    _ => 'guardian',
  };
  return (relation, _orNull(match.group(2)!));
}

AadhaarDetails? _parseSecure(String digits) {
  final List<int> bytes;
  try {
    final number = BigInt.parse(digits);
    var hex = number.toRadixString(16);
    if (hex.length.isOdd) hex = '0$hex';
    bytes = gzip.decode([
      for (var at = 0; at < hex.length; at += 2) int.parse(hex.substring(at, at + 2), radix: 16),
    ]);
  } on FormatException {
    return null;
  }

  final fields = <String>[];
  var start = 0;
  for (var at = 0; at < bytes.length && fields.length < 20; at++) {
    if (bytes[at] == _separator) {
      fields.add(latin1.decode(bytes.sublist(start, at)));
      start = at + 1;
    }
  }

  // Version 2 and later start with "V2"; the first version has no such marker.
  final offset = fields.isNotEmpty && fields.first.startsWith('V') ? 1 : 0;
  String? read(int index) {
    final at = index + offset;
    return at < fields.length ? _orNull(fields[at]) : null;
  }

  final name = read(_versionedFieldOffset - 1);
  if (name == null) return null;
  final (relationType, relationName) = _careOf(read(5));
  return AadhaarDetails(
    name: name,
    dateOfBirth: _isoDate(read(3)),
    gender: _gender(read(4)),
    relationType: relationType,
    relationName: relationName,
    district: read(6),
    houseNumber: read(8),
    pincode: read(10),
    postOffice: read(11),
    state: read(12),
    tehsil: read(14),
  );
}

AadhaarDetails? _parseXml(String xml) {
  String? attribute(String name) {
    final match = RegExp('\\b$name="([^"]*)"').firstMatch(xml);
    return match == null ? null : _orNull(match.group(1)!);
  }

  final name = attribute('name');
  if (name == null) return null;
  final (relationType, relationName) = _careOf(attribute('co') ?? attribute('gname'));
  return AadhaarDetails(
    name: name,
    number: attribute('uid'),
    dateOfBirth: _isoDate(attribute('dob')),
    gender: _gender(attribute('gender')),
    relationType: relationType,
    relationName: relationName,
    houseNumber: attribute('house'),
    postOffice: attribute('po'),
    tehsil: attribute('subdist'),
    district: attribute('dist'),
    state: attribute('state'),
    pincode: attribute('pc'),
  );
}

/// Understands both the older XML code and the newer Secure QR. Returns null for
/// anything else, so a failed scan simply means typing it in.
AadhaarDetails? parseAadhaarQr(String raw) {
  final value = raw.trim();
  if (value.isEmpty) return null;
  if (value.startsWith('<')) return _parseXml(value);
  if (RegExp(r'^\d+$').hasMatch(value)) return _parseSecure(value);
  return null;
}
