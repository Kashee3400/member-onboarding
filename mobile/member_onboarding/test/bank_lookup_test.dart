import 'package:flutter_test/flutter_test.dart';
import 'package:member_onboarding/src/api/api_client.dart';
import 'package:member_onboarding/src/api/onboarding_api.dart';
import 'package:member_onboarding/src/config.dart';
import 'package:member_onboarding/src/storage/draft_store.dart';
import 'package:member_onboarding/src/sync/bank_lookup.dart';
import 'package:member_onboarding/src/ui/device_services.dart';

class _MasterApi extends OnboardingApi {
  _MasterApi()
    : super(
        ApiClient(
          MemberOnboardingConfig(baseUrl: 'https://x.test', assertionProvider: () async => ''),
        ),
      );

  bool online = true;
  Object? failure;
  final Map<String, (String, String)> master = {
    'UBIN0572161': ('Union Bank of India', 'Siyarha'),
  };
  int calls = 0;

  @override
  Future<(String, String)?> findBranch(String ifsc) async {
    calls++;
    if (!online) throw const OfflineException();
    if (failure != null) throw failure!;
    return master[ifsc];
  }
}

class _OnlineLookup extends DeviceServices {
  _OnlineLookup();

  final asked = <String>[];

  @override
  Future<(String, String)?> lookupIfsc(String ifsc) async {
    asked.add(ifsc);
    return ifsc == 'SBIN0001234' ? ('STATE BANK OF INDIA', 'BHADOHI') : null;
  }
}

void main() {
  late _MasterApi api;
  late _OnlineLookup online;
  late MemoryDraftStore store;
  late BankLookup lookup;

  setUp(() {
    api = _MasterApi();
    online = _OnlineLookup();
    store = MemoryDraftStore();
    lookup = BankLookup(api: api, store: store, device: online);
  });

  test('the bank master answers first', () async {
    expect(await lookup.find('UBIN0572161'), ('Union Bank of India', 'Siyarha'));
    expect(online.asked, isEmpty);
  });

  test('an IFSC the master does not know is looked up online', () async {
    expect(await lookup.find('SBIN0001234'), ('STATE BANK OF INDIA', 'BHADOHI'));
    expect(online.asked, ['SBIN0001234']);
  });

  test('without a network, a branch found before still fills the form', () async {
    await lookup.find('UBIN0572161');
    api.online = false;

    expect(await lookup.find('UBIN0572161'), ('Union Bank of India', 'Siyarha'));
    expect(online.asked, isEmpty);
    expect(await lookup.find('HDFC0000001'), isNull);
  });

  test('a server without the master falls back to the online lookup', () async {
    api.failure = ApiException(500, 'error', 'Something went wrong.');

    expect(await lookup.find('SBIN0001234'), ('STATE BANK OF INDIA', 'BHADOHI'));
  });

  test('only the most recent branches are kept', () async {
    for (var number = 0; number < BankLookup.keep + 5; number++) {
      final ifsc = 'TEST0${number.toString().padLeft(6, '0')}';
      api.master[ifsc] = ('Bank', 'Branch $number');
      await lookup.find(ifsc);
    }
    api.online = false;

    expect(await lookup.find('TEST0000000'), isNull);
    expect(await lookup.find('TEST0000304'), ('Bank', 'Branch 304'));
  });
}
