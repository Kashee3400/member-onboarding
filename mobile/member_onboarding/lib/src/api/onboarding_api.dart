
import 'api_client.dart';

class MppSummary {
  const MppSummary({
    required this.id,
    required this.code,
    required this.name,
    this.place = const {},
  });

  factory MppSummary.fromJson(Map<String, dynamic> json) => MppSummary(
    id: json['id'] as String,
    code: json['code'] as String,
    name: json['name'] as String,
    place: placeFromJson(json['place']),
  );

  final String id;
  final String code;
  final String name;

  /// Where the MPP is, keyed as the address fields. Only what the masters know.
  final Map<String, String> place;
}

/// Keeps only the values the masters actually hold.
Map<String, String> placeFromJson(Object? json) => {
  for (final entry in ((json as Map?) ?? const {}).entries)
    if (entry.value is String && (entry.value as String).isNotEmpty)
      entry.key as String: entry.value as String,
};

/// A reviewer's reason for each field sent back, keyed `section.field`. Empty for a
/// form returned before reasons were given per field.
Map<String, String> notesFromJson(Object? json) => {
  for (final entry in ((json as Map?) ?? const {}).entries)
    if (entry.value is String && (entry.value as String).trim().isNotEmpty)
      entry.key as String: (entry.value as String).trim(),
};

class ApplicationSummary {
  const ApplicationSummary({
    required this.id,
    required this.status,
    required this.statusLabel,
    required this.applicantName,
    required this.mppCode,
    this.formNumber = '',
    this.mppName = '',
    this.aadhaarLast4 = '',
    this.mobile = '',
    this.photoId,
    this.createdAt,
    this.submittedAt,
  });

  factory ApplicationSummary.fromJson(Map<String, dynamic> json) => ApplicationSummary(
    id: json['id'] as String,
    status: json['status'] as String,
    statusLabel: json['status_label'] as String,
    applicantName: (json['applicant_name'] as String?) ?? '',
    mppCode: json['mpp_code'] as String,
    formNumber: (json['form_number'] as String?) ?? '',
    mppName: (json['mpp_name'] as String?) ?? '',
    aadhaarLast4: (json['aadhaar_last4'] as String?) ?? '',
    mobile: (json['mobile'] as String?) ?? '',
    photoId: json['photo_id'] as String?,
    createdAt: DateTime.tryParse((json['created_at'] as String?) ?? '')?.toLocal(),
    submittedAt: DateTime.tryParse((json['submitted_at'] as String?) ?? '')?.toLocal(),
  );

  final String id;
  final String status;
  final String statusLabel;
  final String applicantName;
  final String mppCode;
  final String formNumber;
  final String mppName;
  final String aadhaarLast4;
  final String mobile;

  /// The member's photo document, when one has been uploaded.
  final String? photoId;
  final DateTime? createdAt;
  final DateTime? submittedAt;
}

/// A person's forms started between two dates, by where each stands now. Each form
/// is in one of them, so they add up to [total]: a form sent back and sent in again
/// is under review, no longer sent back.
class RecordSummary {
  const RecordSummary({
    this.total = 0,
    this.draft = 0,
    this.underReview = 0,
    this.sentBack = 0,
    this.becameMembers = 0,
  });

  factory RecordSummary.fromJson(Map<String, dynamic> json) {
    final now = json['now'];
    if (now is Map) {
      return RecordSummary(
        total: now['total'] as int? ?? 0,
        draft: now['draft'] as int? ?? 0,
        underReview: now['under_review'] as int? ?? 0,
        sentBack: now['sent_back'] as int? ?? 0,
        becameMembers: now['became_members'] as int? ?? 0,
      );
    }
    // An older server counts events instead: the nearest it has.
    final started = json['started'] as int? ?? 0;
    final submitted = json['submitted'] as int? ?? 0;
    return RecordSummary(
      total: started,
      draft: (started - submitted).clamp(0, started),
      underReview: json['pending'] as int? ?? 0,
      sentBack: json['rejected'] as int? ?? 0,
      becameMembers: json['approved'] as int? ?? 0,
    );
  }

  final int total;
  final int draft;
  final int underReview;
  final int sentBack;
  final int becameMembers;
}

/// One page of a person's forms, and how many there are in all.
class RecordPage {
  const RecordPage(this.items, this.total);

  final List<ApplicationSummary> items;
  final int total;
}

String _day(DateTime date) =>
    '${date.year}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';

/// The API as the package uses it. Tests replace this to run without a network.
class OnboardingApi {
  OnboardingApi(this._client);

  final ApiClient _client;

  List<Map<String, dynamic>> _results(Object? body) =>
      ((body as Map<String, dynamic>)['results'] as List).cast<Map<String, dynamic>>();

  /// Returned as JSON so the caller can keep a copy for working offline.
  Future<Map<String, dynamic>> fetchFormJson() async =>
      await _client.get('applications/form/') as Map<String, dynamic>;

  /// Bank and branch from the organization's bank master, or null when it has no
  /// branch in use with this IFSC.
  Future<(String, String)?> findBranch(String ifsc) async {
    try {
      final body =
          await _client.get('banks/branches/by-ifsc/${Uri.encodeComponent(ifsc)}/')
              as Map<String, dynamic>;
      return ('${body['bank_name']}', '${body['branch_name']}');
    } on ApiException catch (error) {
      if (error.status == 404) return null;
      rethrow;
    }
  }

  Future<List<Map<String, dynamic>>> fetchMppsJson() async {
    final body = await _client.get('hierarchy/mpps/', query: {'page_size': '200'});
    return _results(body);
  }

  Future<List<ApplicationSummary>> fetchApplications({String? status}) async {
    final body = await _client.get('applications/', query: {'page_size': '200', 'status': ?status});
    return _results(body).map(ApplicationSummary.fromJson).toList();
  }

  /// Forms this person started between two dates, newest first.
  Future<RecordPage> fetchRecords({
    required DateTime from,
    required DateTime to,
    String? status,
    int page = 1,
  }) async {
    final body =
        await _client.get(
              'applications/',
              query: {
                'mine': 'true',
                'created_from': _day(from),
                'created_to': _day(to),
                'status': ?status,
                'ordering': '-updated_at',
                'page': '$page',
                'page_size': '30',
              },
            )
            as Map<String, dynamic>;
    return RecordPage(
      _results(body).map(ApplicationSummary.fromJson).toList(),
      body['count'] as int? ?? 0,
    );
  }

  Future<RecordSummary> fetchSummary({required DateTime from, required DateTime to}) async {
    final body = await _client.get(
      'applications/summary/',
      query: {'mine': 'true', 'from': _day(from), 'to': _day(to)},
    );
    return RecordSummary.fromJson(body as Map<String, dynamic>);
  }

  Future<Map<String, dynamic>> fetchApplication(String id) async =>
      await _client.get('applications/$id/') as Map<String, dynamic>;

  Future<Map<String, dynamic>> createApplication({
    required String clientId,
    required String mppId,
  }) async =>
      await _client.post('applications/', {'client_id': clientId, 'mpp': mppId})
          as Map<String, dynamic>;

  Future<Map<String, dynamic>> saveApplication(
    String id, {
    required int version,
    required Map<String, dynamic> data,
    String? aadhaarNumber,
    String? accountNumber,
    String? aadhaarQr,
  }) async =>
      await _client.patch('applications/$id/', {
            'version': version,
            'data': data,
            'aadhaar_number': ?aadhaarNumber,
            'account_number': ?accountNumber,
            if (aadhaarQr != null) ...{'aadhaar_qr': aadhaarQr, 'aadhaar_qr_consent': true},
          })
          as Map<String, dynamic>;

  Future<void> uploadDocument(
    String id,
    String documentType,
    List<int> bytes,
    String filename,
  ) async {
    await _client.upload(
      'applications/$id/documents/',
      {'document_type': documentType},
      bytes,
      filename,
    );
  }

  /// Document type to id, for the photos already uploaded to a form.
  Future<Map<String, String>> fetchDocumentIds(String id) async {
    final body = await _client.get('applications/$id/documents/') as List<dynamic>;
    return {
      for (final item in body.cast<Map<String, dynamic>>())
        '${item['document_type']}': '${item['id']}',
    };
  }

  Future<List<int>> fetchDocumentFile(String documentId) =>
      _client.getBytes('documents/$documentId/file/');

  /// Tells the server where to send this person's push notifications.
  Future<void> registerPushDevice(String token, String platform) async =>
      await _client.post('notifications/push-devices/', {'token': token, 'platform': platform});

  /// Sends a code to the form's mobile number or email (`channel` is "mobile" or "email").
  Future<void> sendContactOtp(String id, String channel) async =>
      await _client.post('applications/$id/contact-otp/', {'channel': channel});

  /// Returns `{"mobile": when, "email": when}`, each null until proven.
  Future<Map<String, dynamic>> verifyContactOtp(String id, String channel, String code) async =>
      await _client.post('applications/$id/contact-otp/verify/', {'channel': channel, 'code': code})
          as Map<String, dynamic>;

  Future<Map<String, dynamic>> submitApplication(String id, int version) async =>
      await _client.post('applications/$id/submit/', {'version': version}) as Map<String, dynamic>;
}
