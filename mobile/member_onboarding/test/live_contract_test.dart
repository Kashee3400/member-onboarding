import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:member_onboarding/src/api/api_client.dart';
import 'package:member_onboarding/src/api/onboarding_api.dart';
import 'package:member_onboarding/src/config.dart';
import 'package:member_onboarding/src/models/draft.dart';
import 'package:member_onboarding/src/models/form_schema.dart';
import 'package:member_onboarding/src/storage/draft_store.dart';
import 'package:member_onboarding/src/sync/draft_controller.dart';

/// Runs the real package against a real server, proving both sides agree.
/// Skipped unless MEMBER_ONBOARDING_LIVE points at a folder with `url`,
/// `assertion` and `photo.jpg`.
void main() {
  final folder = Platform.environment['MEMBER_ONBOARDING_LIVE'];

  Map<String, dynamic> completeForm() => {
    'applicant': {
      'full_name': 'Test Applicant',
      'relation_type': 'husband',
      'relation_name': 'Test Husband',
      'gender': 'female',
      'date_of_birth': '1984-01-15',
      'education': '12th',
      'category': 'obc',
    },
    'address': {
      'post_office': 'Mondh',
      'tehsil': 'Bhadohi',
      'district': 'Sant Ravidas Nagar',
      'state': 'Uttar Pradesh',
      'pincode': '221406',
      'mobile': '9170800000',
    },
    'location': {'latitude': 25.41507, 'longitude': 82.51469},
    'animals': {
      'buffalo_heifer': 1,
      'buffalo_in_milk': 2,
      'production_lpd': 12,
      'consumption_lpd': 4,
    },
    'bank': {
      'holder_name': 'Test Applicant',
      'ifsc': 'UBIN0572161',
      'bank_name': 'Union Bank of India',
      'branch_name': 'Siyarha',
    },
    'nominee': {
      'name': 'Test Husband',
      'relation': 'husband',
      'date_of_birth': '1982-01-01',
      'address': 'Same village',
    },
    'family': [
      {'name': 'Test Husband', 'gender': 'male', 'age': 44, 'relation': 'husband'},
    ],
    'declaration': {
      'accepted_terms': true,
      'no_household_member': true,
      'not_sahayak_or_employee': true,
    },
  };

  test('a form travels from the app to the first approval stage', () async {
    final url = File('$folder/url').readAsStringSync().trim();
    final assertion = File('$folder/assertion').readAsStringSync().trim();
    final api = OnboardingApi(
      ApiClient(MemberOnboardingConfig(baseUrl: url, assertionProvider: () async => assertion)),
    );

    final schema = FormSchema.fromJson(await api.fetchFormJson());
    expect(schema.section('applicant').title, 'आवेदक');
    expect(schema.section('applicant').fields.first.label, 'पूरा नाम');
    expect(schema.familyRelations, isNotEmpty);

    final mpp = MppSummary.fromJson((await api.fetchMppsJson()).single);
    expect(mpp.code, '1305');

    final controller = DraftController(
      draft: Draft(clientId: 'live-1', mppId: mpp.id, mppLabel: mpp.code),
      api: api,
      store: MemoryDraftStore(),
      debounce: const Duration(hours: 1),
    );
    addTearDown(controller.dispose);

    // Partial answers are accepted while it is a draft.
    controller.setValue('applicant', 'full_name', 'Half Done');
    await controller.sync();
    expect(controller.state, SyncState.saved);
    expect(controller.draft.serverId, isNotNull);

    // An empty form is refused, with reasons the app can show on each field.
    expect(await controller.submit(), isFalse);
    expect(controller.serverErrors, contains('documents.photo'));

    for (final entry in completeForm().entries) {
      if (entry.value is Map) {
        for (final field in (entry.value as Map<String, dynamic>).entries) {
          controller.setValue(entry.key, field.key, field.value);
        }
      }
    }
    controller
      ..setFamily((completeForm()['family'] as List).cast<Map<String, dynamic>>())
      ..setAadhaar('234123412346')
      ..setAccount('656302010000644');

    final temporary = await Directory.systemTemp.createTemp();
    for (final type in ['photo', 'member_signature', 'aadhaar_front', 'aadhaar_back', 'passbook']) {
      final copy = File('$folder/photo.jpg').copySync('${temporary.path}/$type.jpg');
      controller.attachDocument(type, copy.path);
    }

    expect(await controller.submit(), isTrue, reason: '${controller.serverErrors}');
    expect(controller.draft.status, 'pending_am');
    expect(controller.draft.aadhaarLast4, '2346');
    expect(controller.draft.pendingAadhaar, isNull);
    expect(controller.draft.uploadedDocuments, hasLength(5));

    final server = await api.fetchApplication(controller.draft.serverId!);
    expect(server['form_number'], isNotEmpty);
    expect(server.toString(), isNot(contains('234123412346')));
    expect(server['computed']['surplus_lpd'], 8.0);
  }, skip: folder == null ? 'Needs a live server' : false);
}
