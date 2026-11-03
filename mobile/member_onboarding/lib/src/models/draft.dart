import 'dart:convert';

import '../api/onboarding_api.dart';

/// A form on this device. Every keystroke lands here first, so nothing is lost
/// when the network or the phone drops out in the village.
class Draft {
  Draft({
    required this.clientId,
    required this.mppId,
    required this.mppLabel,
    this.serverId,
    this.version,
    this.status = 'draft',
    Map<String, dynamic>? data,
    this.pendingAadhaar,
    this.pendingAccount,
    this.aadhaarLast4 = '',
    this.accountLast4 = '',
    Map<String, String>? pendingDocuments,
    Set<String>? uploadedDocuments,
    this.rejectionReason = '',
    List<String>? rejectedFields,
    Map<String, String>? rejectedFieldNotes,
    this.needsSync = false,
    this.mobileVerified = false,
    this.emailVerified = false,
    this.updatedAt,
    Map<String, String>? place,
  }) : place = place ?? {},
       data = data ?? {},
       pendingDocuments = pendingDocuments ?? {},
       uploadedDocuments = uploadedDocuments ?? {},
       rejectedFields = rejectedFields ?? [],
       rejectedFieldNotes = rejectedFieldNotes ?? {};

  factory Draft.fromJson(Map<String, dynamic> json) => Draft(
    clientId: json['client_id'] as String,
    mppId: json['mpp_id'] as String,
    mppLabel: json['mpp_label'] as String,
    serverId: json['server_id'] as String?,
    version: json['version'] as int?,
    status: json['status'] as String,
    data: (json['data'] as Map).cast<String, dynamic>(),
    pendingAadhaar: json['pending_aadhaar'] as String?,
    pendingAccount: json['pending_account'] as String?,
    aadhaarLast4: json['aadhaar_last4'] as String,
    accountLast4: json['account_last4'] as String,
    pendingDocuments: (json['pending_documents'] as Map).cast<String, String>(),
    uploadedDocuments: (json['uploaded_documents'] as List).cast<String>().toSet(),
    rejectionReason: json['rejection_reason'] as String,
    rejectedFields: (json['rejected_fields'] as List).cast<String>(),
    // Drafts saved by an older app have no notes.
    rejectedFieldNotes: notesFromJson(json['rejected_field_notes']),
    needsSync: json['needs_sync'] as bool,
    // Drafts saved by an older app have neither; they start unverified.
    mobileVerified: json['mobile_verified'] as bool? ?? false,
    emailVerified: json['email_verified'] as bool? ?? false,
    place: placeFromJson(json['place']),
    updatedAt: DateTime.tryParse('${json['updated_at'] ?? ''}'),
  );

  /// Opens a form from the server, such as one sent back for correction.
  factory Draft.fromServer(Map<String, dynamic> json) => Draft(
    clientId: json['client_id'] as String,
    mppId: json['mpp'] as String,
    mppLabel: '${json['mpp_code']} ${json['mpp_name']}',
    serverId: json['id'] as String,
    version: json['version'] as int,
    status: json['status'] as String,
    data: (json['data'] as Map).cast<String, dynamic>(),
    aadhaarLast4: json['aadhaar_last4'] as String,
    accountLast4: json['account_last4'] as String,
    rejectionReason: json['rejection_reason'] as String,
    rejectedFields: (json['rejected_fields'] as List).cast<String>(),
    // An older server, or a form sent back before reasons per field, has none.
    rejectedFieldNotes: notesFromJson(json['rejected_field_notes']),
    mobileVerified: (json['contact_verified'] as Map?)?['mobile'] != null,
    emailVerified: (json['contact_verified'] as Map?)?['email'] != null,
    place: placeFromJson(json['mpp_place']),
  );

  factory Draft.decode(String source) =>
      Draft.fromJson((jsonDecode(source) as Map).cast<String, dynamic>());

  final String clientId;
  final String mppId;
  final String mppLabel;

  /// The address fields the MPP fills. They show read-only and the server enforces them.
  Map<String, String> place;

  String? serverId;
  int? version;
  String status;
  Map<String, dynamic> data;

  /// Sensitive numbers stay here only until the server has them.
  String? pendingAadhaar;
  String? pendingAccount;
  String aadhaarLast4;
  String accountLast4;

  /// Document type to file path, waiting for upload.
  Map<String, String> pendingDocuments;
  Set<String> uploadedDocuments;

  String rejectionReason;
  List<String> rejectedFields;

  /// The reviewer's own reason for a returned field, where they gave one.
  Map<String, String> rejectedFieldNotes;
  bool needsSync;

  /// When it was last saved on the phone, to list the latest first.
  DateTime? updatedAt;

  /// Why this field was sent back: the reviewer's words, or null when none were given.
  String? noteFor(String path) {
    final note = rejectedFieldNotes[path]?.trim();
    return note == null || note.isEmpty ? null : note;
  }

  /// Proven by an OTP on the server. A changed number or email loses it.
  bool mobileVerified;
  bool emailVerified;

  bool get hasAadhaar => pendingAadhaar != null || aadhaarLast4.isNotEmpty;
  bool get hasAccount => pendingAccount != null || accountLast4.isNotEmpty;

  bool hasDocument(String type) =>
      pendingDocuments.containsKey(type) || uploadedDocuments.contains(type);

  String get applicantName => (section('applicant')['full_name'] as String?) ?? '';

  Map<String, dynamic> section(String key) {
    final value = data[key];
    if (value is Map) return value.cast<String, dynamic>();
    return {};
  }

  List<Map<String, dynamic>> get family =>
      ((data['family'] as List?) ?? const []).cast<Map>().map((person) {
        return person.cast<String, dynamic>();
      }).toList();

  Map<String, dynamic> toJson() => {
    'client_id': clientId,
    'mpp_id': mppId,
    'mpp_label': mppLabel,
    'server_id': serverId,
    'version': version,
    'status': status,
    'data': data,
    'pending_aadhaar': pendingAadhaar,
    'pending_account': pendingAccount,
    'aadhaar_last4': aadhaarLast4,
    'account_last4': accountLast4,
    'pending_documents': pendingDocuments,
    'uploaded_documents': uploadedDocuments.toList(),
    'rejection_reason': rejectionReason,
    'rejected_fields': rejectedFields,
    'rejected_field_notes': rejectedFieldNotes,
    'needs_sync': needsSync,
    'updated_at': updatedAt?.toIso8601String(),
    'mobile_verified': mobileVerified,
    'email_verified': emailVerified,
    'place': place,
  };

  String encode() => jsonEncode(toJson());
}
