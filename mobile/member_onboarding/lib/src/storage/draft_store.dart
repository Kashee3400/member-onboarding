import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../models/draft.dart';

abstract class DraftStore {
  Future<List<Draft>> all();
  Future<void> save(Draft draft);
  Future<void> delete(String clientId);

  /// Last known form and MPP list, so the app opens without a network.
  Future<String?> readCache(String key);
  Future<void> writeCache(String key, String value);
}

/// Encrypted by the phone's keystore: a draft can hold an Aadhaar or account number.
class SecureDraftStore implements DraftStore {
  SecureDraftStore({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();

  static const _prefix = 'member_onboarding.draft.';
  static const _cachePrefix = 'member_onboarding.cache.';

  final FlutterSecureStorage _storage;

  @override
  Future<List<Draft>> all() async {
    final entries = await _storage.readAll();
    return entries.entries
        .where((entry) => entry.key.startsWith(_prefix))
        .map((entry) => Draft.decode(entry.value))
        .toList();
  }

  @override
  Future<void> save(Draft draft) =>
      _storage.write(key: '$_prefix${draft.clientId}', value: draft.encode());

  @override
  Future<void> delete(String clientId) => _storage.delete(key: '$_prefix$clientId');

  @override
  Future<String?> readCache(String key) => _storage.read(key: '$_cachePrefix$key');

  @override
  Future<void> writeCache(String key, String value) =>
      _storage.write(key: '$_cachePrefix$key', value: value);
}

class MemoryDraftStore implements DraftStore {
  final Map<String, String> _drafts = {};
  final Map<String, String> _cache = {};

  @override
  Future<List<Draft>> all() async => _drafts.values.map(Draft.decode).toList();

  @override
  Future<void> save(Draft draft) async => _drafts[draft.clientId] = draft.encode();

  @override
  Future<void> delete(String clientId) async => _drafts.remove(clientId);

  @override
  Future<String?> readCache(String key) async => _cache[key];

  @override
  Future<void> writeCache(String key, String value) async => _cache[key] = value;
}
