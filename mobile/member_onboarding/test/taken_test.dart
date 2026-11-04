import 'package:flutter_test/flutter_test.dart';
import 'package:member_onboarding/src/api/api_client.dart';
import 'package:member_onboarding/src/api/onboarding_api.dart';
import 'package:member_onboarding/src/config.dart';
import 'package:member_onboarding/src/models/draft.dart';
import 'package:member_onboarding/src/storage/draft_store.dart';
import 'package:member_onboarding/src/sync/draft_controller.dart';
import 'package:member_onboarding/src/ui/strings.dart';

/// A server that already has this mobile number and bank account on another form.
class TakenApi extends OnboardingApi {
  TakenApi()
    : super(
        ApiClient(
          MemberOnboardingConfig(baseUrl: 'https://x.test', assertionProvider: () async => ''),
        ),
      );

  Map<String, dynamic> _form(int version, [Map<String, String> taken = const {}]) => {
    'id': 's1',
    'version': version,
    'status': 'draft',
    'aadhaar_last4': '',
    'account_last4': '',
    'duplicate_fields': taken,
  };

  @override
  Future<Map<String, dynamic>> createApplication({
    required String clientId,
    required String mppId,
  }) async => _form(1);

  @override
  Future<Map<String, dynamic>> saveApplication(
    String id, {
    required int version,
    required Map<String, dynamic> data,
    String? aadhaarNumber,
    String? accountNumber,
    String? aadhaarQr,
  }) async => _form(version + 1, {
    'address.mobile': 'Another form already uses this mobile number.',
    if (accountNumber != null)
      'bank.account_number': 'Another form already uses this bank account.',
  });
}

void main() {
  test('a taken mobile and account are not kept, and their fields say why', () async {
    final controller = DraftController(
      draft: Draft(
        clientId: 'c1',
        mppId: 'm1',
        mppLabel: 'x',
        data: {
          'address': {'mobile': '9170800000', 'tehsil': 'Gyanpur'},
        },
      ),
      api: TakenApi(),
      store: MemoryDraftStore(),
      debounce: const Duration(hours: 1),
    );
    controller.setAccount('656302010000644');

    await controller.sync();

    expect(controller.draft.section('address')['mobile'], '');
    expect(controller.draft.section('address')['tehsil'], 'Gyanpur');
    expect(controller.serverErrors['address.mobile'], Taken.mobile);
    expect(controller.serverErrors['bank.account_number'], Taken.account);

    controller.setAccount('123456789012');
    expect(controller.serverErrors.containsKey('bank.account_number'), isFalse);
    controller.dispose();
  });
}
