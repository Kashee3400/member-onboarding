import 'dart:io';

import 'api_client.dart';

class MppSummary {
  const MppSummary({required this.id, required this.code, required this.name});

  factory MppSummary.fromJson(Map<String, dynamic> json) => MppSummary(
    id: json['id'] as String,
    code: json['code'] as String,
    name: json['name'] as String,
  );

  final String id;
  final String code;
  final String name;
}

class ApplicationSummary {
  const ApplicationSummary({
    required this.id,
    required this.status,
    required this.statusLabel,
    required this.applicantName,
    required this.mppCode,
    this.formNumber = '',
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
    createdAt: DateTime.tryParse((json['created_at'] as String?) ?? '')?.toLocal(),
    submittedAt: DateTime.tryParse((json['submitted_at'] as String?) ?? '')?.toLocal(),
  );

  final String id;
  final String status;
  final String statusLabel;
  final String applicantName;
  final String mppCode;
  final String formNumber;
  final DateTime? createdAt;
  final DateTime? submittedAt;
}

/// A person's own counts between two dates, as the records screen shows them.
class RecordSummary {
  const RecordSummary({
    this.started = 0,
    this.submitted = 0,
    this.pending = 0,
    this.approved = 0,
    this.rejected = 0,
  });

  factory RecordSummary.fromJson(Map<String, dynamic> json) => RecordSummary(
    started: json['started'] as int? ?? 0,
    submitted: json['submitted'] as int? ?? 0,
    pending: json['pending'] as int? ?? 0,
    approved: json['approved'] as int? ?? 0,
    rejected: json['rejected'] as int? ?? 0,
  );

  final int started;
  final int submitted;
  final int pending;
  final int approved;
  final int rejected;
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
  }) async =>
      await _client.patch('applications/$id/', {
            'version': version,
            'data': data,
            'aadhaar_number': ?aadhaarNumber,
            'account_number': ?accountNumber,
          })
          as Map<String, dynamic>;

  Future<void> uploadDocument(String id, String documentType, File file) async {
    await _client.upload('applications/$id/documents/', {'document_type': documentType}, file);
  }

  Future<Map<String, dynamic>> submitApplication(String id, int version) async =>
      await _client.post('applications/$id/submit/', {'version': version}) as Map<String, dynamic>;
}
