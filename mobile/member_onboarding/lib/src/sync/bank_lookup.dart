import 'dart:convert';

import '../api/api_client.dart';
import '../api/onboarding_api.dart';
import '../storage/draft_store.dart';
import '../ui/device_services.dart';

/// Bank and branch for a typed IFSC. The organization's own bank master comes
/// first; without a network, a branch this phone was given before; and only when
/// the master does not know the IFSC, the public online lookup.
class BankLookup {
  BankLookup({required OnboardingApi api, required DraftStore store, required DeviceServices device})
    : _api = api,
      _store = store,
      _device = device;

  static const cacheKey = 'bank_branches';

  /// Enough for the branches of a facilitator's villages, small enough for the keystore.
  static const keep = 300;

  final OnboardingApi _api;
  final DraftStore _store;
  final DeviceServices _device;

  Future<(String, String)?> find(String ifsc) async {
    try {
      final found = await _api.findBranch(ifsc);
      if (found != null) {
        await _remember(ifsc, found);
        return found;
      }
    } on OfflineException {
      final known = (await _known())[ifsc];
      if (known != null) return known;
    } on ApiException {
      // A server without the master yet: the online lookup still helps.
    }
    return _device.lookupIfsc(ifsc);
  }

  Future<Map<String, (String, String)>> _known() async {
    final raw = await _store.readCache(cacheKey);
    if (raw == null) return {};
    try {
      final json = jsonDecode(raw) as Map<String, dynamic>;
      return json.map((ifsc, pair) {
        final names = (pair as List).cast<String>();
        return MapEntry(ifsc, (names[0], names[1]));
      });
    } catch (_) {
      return {};
    }
  }

  Future<void> _remember(String ifsc, (String, String) found) async {
    final known = await _known()
      ..remove(ifsc)
      ..[ifsc] = found;
    final kept = known.entries.skip(known.length > keep ? known.length - keep : 0);
    await _store.writeCache(
      cacheKey,
      jsonEncode({
        for (final entry in kept) entry.key: [entry.value.$1, entry.value.$2],
      }),
    );
  }
}
