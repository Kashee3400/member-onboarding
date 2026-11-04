import 'dart:async';

import 'package:flutter/foundation.dart';

import '../api/api_client.dart';
import '../api/onboarding_api.dart';
import '../models/draft.dart';
import '../storage/document_vault.dart';
import '../storage/draft_store.dart';
import '../ui/strings.dart' show OtpWords, Taken;

enum SyncState { saved, saving, offline, conflict, failed }

/// Owns one form: saves locally at once, then syncs quietly when it can.
class DraftController extends ChangeNotifier {
  DraftController({
    required this.draft,
    required OnboardingApi api,
    required DraftStore store,
    DocumentVault? vault,
    this.debounce = const Duration(seconds: 2),
    this.offlineRetry = const Duration(minutes: 1),
  }) : _api = api,
       _store = store,
       _vault = vault ?? SecureDocumentVault();

  final Draft draft;
  final OnboardingApi _api;
  final DraftStore _store;
  final DocumentVault _vault;
  final Duration debounce;

  /// How often a form on screen tries again while there is no network.
  final Duration offlineRetry;

  SyncState state = SyncState.saved;
  String? aadhaarError;
  Map<String, String> serverErrors = const {};

  Timer? _timer;
  Future<void>? _running;
  bool _changedWhileSyncing = false;

  void _changed() {
    draft.needsSync = true;
    unawaited(_store.save(draft));
    _timer?.cancel();
    _timer = Timer(debounce, () => unawaited(sync()));
    notifyListeners();
  }

  void setValue(String section, String key, Object? value) {
    final before = draft.section(section)[key];
    draft.data[section] = {...draft.section(section), key: value};
    // The server forgets a proof once the number changes; so does the phone.
    if (section == 'address' && key == 'mobile' && before != value) draft.mobileVerified = false;
    if (section == 'address' && key == 'email' && before != value) draft.emailVerified = false;
    serverErrors = Map.of(serverErrors)..remove('$section.$key');
    _changed();
  }

  void setFamily(List<Map<String, dynamic>> family) {
    draft.data['family'] = family;
    _changed();
  }

  void setAadhaar(String number) {
    draft.pendingAadhaar = number;
    aadhaarError = null;
    _changed();
  }

  /// Only called after the member agreed: the consent travels with the QR.
  void setAadhaarQr(String raw) {
    draft.pendingAadhaarQr = raw;
    _changed();
  }

  void setAccount(String number) {
    draft.pendingAccount = number;
    serverErrors = Map.of(serverErrors)..remove('bank.account_number');
    _changed();
  }

  /// Takes a new photo into the vault, in place of any earlier one of the same kind.
  Future<void> attachDocument(String type, String path) async {
    final kept = await _vault.keep(draft.clientId, type, path);
    final earlier = draft.pendingDocuments[type];
    draft.pendingDocuments[type] = kept;
    draft.uploadedDocuments.remove(type);
    _shown.remove(type);
    if (earlier != null) await _vault.remove(earlier);
    _changed();
  }

  /// A photo to show: from the vault until it is sent, then from the server.
  Future<Uint8List?> imageOf(String type) async {
    final kept = draft.pendingDocuments[type];
    if (kept != null) return _vault.read(kept);
    return uploadedImage(type);
  }

  /// Photos already uploaded, fetched to show again. Kept in memory only: the phone
  /// deletes its copy after upload, and Aadhaar images must not be stored again.
  final Map<String, Uint8List> _shown = {};

  /// The uploaded photo of [type], or null when it is still on the phone or cannot load.
  Future<Uint8List?> uploadedImage(String type) async {
    final cached = _shown[type];
    if (cached != null) return cached;
    final id = draft.serverId;
    if (id == null || !draft.uploadedDocuments.contains(type)) return null;
    try {
      final ids = await _api.fetchDocumentIds(id);
      final documentId = ids[type];
      if (documentId == null) return null;
      final bytes = Uint8List.fromList(await _api.fetchDocumentFile(documentId));
      return _shown[type] = bytes;
    } on Exception {
      return null;
    }
  }

  /// One sync at a time. Changes made meanwhile are picked up straight after.
  Future<void> sync() {
    final running = _running;
    if (running != null) {
      _changedWhileSyncing = true;
      return running;
    }
    final future = _sync().whenComplete(() {
      _running = null;
      if (_changedWhileSyncing) {
        _changedWhileSyncing = false;
        unawaited(sync());
      }
    });
    return _running = future;
  }

  void _apply(Map<String, dynamic> server) {
    draft
      ..version = server['version'] as int
      ..status = server['status'] as String
      ..aadhaarLast4 = server['aadhaar_last4'] as String
      ..accountLast4 = server['account_last4'] as String;
    final verified = server['contact_verified'];
    if (verified is Map) {
      draft
        ..mobileVerified = verified['mobile'] != null
        ..emailVerified = verified['email'] != null;
    }
    final check = server['aadhaar_check'];
    draft.aadhaarCheck = check is Map ? check['status'] as String? : null;
    // The server knows the MPP's latest place, even for a form started before it was set.
    if (server['mpp_place'] != null) draft.place = placeFromJson(server['mpp_place']);
  }

  /// A mobile number, email or bank account another form or member already has: the
  /// server did not keep it, so neither does the phone, and the field says why.
  void _refuseTaken(Object? taken) {
    if (taken is! Map || taken.isEmpty) return;
    final errors = Map.of(serverErrors);
    final address = draft.section('address');
    for (final path in taken.keys.cast<String>()) {
      final message = Taken.forPath(path);
      if (message == null) continue;
      errors[path] = message;
      if (path.startsWith('address.')) address[path.substring(8)] = '';
    }
    draft.data['address'] = address;
    serverErrors = errors;
  }

  /// Sends an OTP for "mobile" or "email". Returns why it could not, or null.
  Future<String?> sendOtp(String channel) async {
    _timer?.cancel();
    draft.needsSync = draft.needsSync || draft.serverId == null;
    // The server sends to what it holds, so the latest number must reach it first.
    await sync();
    if (state == SyncState.offline) return OtpWords.offline;
    if (state != SyncState.saved || draft.serverId == null) return OtpWords.notSaved;
    try {
      await _api.sendContactOtp(draft.serverId!, channel);
      return null;
    } on OfflineException {
      return OtpWords.offline;
    } on ApiException catch (error) {
      return error.message;
    }
  }

  /// Checks the code the member read out. Returns why it failed, or null.
  Future<String?> verifyOtp(String channel, String code) async {
    if (draft.serverId == null) return OtpWords.notSaved;
    try {
      final verified = await _api.verifyContactOtp(draft.serverId!, channel, code);
      draft
        ..mobileVerified = verified['mobile'] != null
        ..emailVerified = verified['email'] != null;
      await _store.save(draft);
      notifyListeners();
      return null;
    } on OfflineException {
      return OtpWords.offline;
    } on ApiException catch (error) {
      return error.fieldErrors['code'] ?? error.message;
    }
  }

  Future<void> _sync() async {
    if (!draft.needsSync) return;
    state = SyncState.saving;
    notifyListeners();

    try {
      if (draft.serverId == null) {
        final created = await _api.createApplication(clientId: draft.clientId, mppId: draft.mppId);
        draft.serverId = created['id'] as String;
        _apply(created);
      }

      final aadhaar = draft.pendingAadhaar;
      final account = draft.pendingAccount;
      final qr = draft.pendingAadhaarQr;
      final saved = await _api.saveApplication(
        draft.serverId!,
        version: draft.version!,
        data: draft.data,
        aadhaarNumber: aadhaar,
        accountNumber: account,
        aadhaarQr: qr,
      );
      _apply(saved);
      // The server holds them now, so they must not stay on the phone.
      if (draft.pendingAadhaar == aadhaar) draft.pendingAadhaar = null;
      if (draft.pendingAccount == account) draft.pendingAccount = null;
      if (draft.pendingAadhaarQr == qr) draft.pendingAadhaarQr = null;
      _refuseTaken(saved['duplicate_fields']);

      for (final entry in Map.of(draft.pendingDocuments).entries) {
        final bytes = await _vault.read(entry.value);
        if (bytes == null) {
          // Gone from the phone: the form shows it as still to take, and cannot be sent.
          draft.pendingDocuments.remove(entry.key);
          continue;
        }
        final extension = entry.value.contains('.png') ? 'png' : 'jpg';
        await _api.uploadDocument(draft.serverId!, entry.key, bytes, '${entry.key}.$extension');
        draft.pendingDocuments.remove(entry.key);
        draft.uploadedDocuments.add(entry.key);
        // The picture is on the server, so this copy of an ID card should go.
        await _vault.remove(entry.value);
      }

      draft.needsSync = false;
      state = SyncState.saved;
    } on OfflineException {
      state = SyncState.offline;
      _timer?.cancel();
      _timer = Timer(offlineRetry, () => unawaited(sync()));
    } on ApiException catch (error) {
      if (error.code == 'stale_version') {
        state = SyncState.conflict;
      } else if (error.code == 'duplicate_record') {
        aadhaarError = Taken.aadhaar;
        draft.pendingAadhaar = null;
        state = SyncState.failed;
      } else {
        serverErrors = error.fieldErrors;
        state = SyncState.failed;
      }
    }

    await _store.save(draft);
    notifyListeners();
  }

  /// Throws nothing for an invalid form: the problems land in [serverErrors].
  Future<bool> submit() async {
    _timer?.cancel();
    draft.needsSync = draft.needsSync || draft.serverId == null;
    await sync();
    if (state != SyncState.saved) return false;

    try {
      final submitted = await _api.submitApplication(draft.serverId!, draft.version!);
      _apply(submitted);
      serverErrors = const {};
      await _store.delete(draft.clientId);
      // Nothing of a submitted form stays on the phone.
      await _vault.removeAll(draft.clientId);
      notifyListeners();
      return true;
    } on OfflineException {
      state = SyncState.offline;
    } on ApiException catch (error) {
      serverErrors = error.fieldErrors.isEmpty ? {'form': error.message} : error.fieldErrors;
      state = SyncState.failed;
    }
    notifyListeners();
    return false;
  }

  /// After a conflict: take the server's copy and drop this device's changes.
  Future<void> reloadFromServer() async {
    final server = await _api.fetchApplication(draft.serverId!);
    _apply(server);
    draft
      ..data = (server['data'] as Map).cast<String, dynamic>()
      ..needsSync = false;
    state = SyncState.saved;
    await _store.save(draft);
    notifyListeners();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}
