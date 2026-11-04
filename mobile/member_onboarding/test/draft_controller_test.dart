import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:member_onboarding/src/api/api_client.dart';
import 'package:member_onboarding/src/api/onboarding_api.dart';
import 'package:member_onboarding/src/config.dart';
import 'package:member_onboarding/src/models/draft.dart';
import 'package:member_onboarding/src/storage/document_vault.dart';
import 'package:member_onboarding/src/storage/draft_store.dart';
import 'package:member_onboarding/src/sync/draft_controller.dart';
import 'package:member_onboarding/src/ui/strings.dart';

class FakeApi extends OnboardingApi {
  FakeApi()
    : super(
        ApiClient(
          MemberOnboardingConfig(baseUrl: 'https://x.test', assertionProvider: () async => ''),
        ),
      );

  Exception? failWith;
  int version = 1;
  int creates = 0;
  Map<String, String>? mppPlace;
  final saves = <Map<String, dynamic>>[];
  final uploads = <String>[];

  Map<String, dynamic> _server(String status) => {
    'id': 'server-1',
    'version': version,
    'status': status,
    'aadhaar_last4': saves.isNotEmpty && saves.last['aadhaar'] != null ? '2346' : '',
    'account_last4': '',
    'data': <String, dynamic>{
      'applicant': {'full_name': 'From server'},
    },
    'mpp_place': ?mppPlace,
  };

  void _maybeFail() {
    final failure = failWith;
    if (failure != null) throw failure;
  }

  @override
  Future<Map<String, dynamic>> createApplication({
    required String clientId,
    required String mppId,
  }) async {
    _maybeFail();
    creates++;
    return _server('draft');
  }

  @override
  Future<Map<String, dynamic>> saveApplication(
    String id, {
    required int version,
    required Map<String, dynamic> data,
    String? aadhaarNumber,
    String? accountNumber,
    String? aadhaarQr,
  }) async {
    _maybeFail();
    saves.add({'version': version, 'data': data, 'aadhaar': aadhaarNumber, 'qr': aadhaarQr});
    this.version++;
    return _server('draft');
  }

  @override
  Future<void> uploadDocument(
    String id,
    String documentType,
    List<int> bytes,
    String filename,
  ) async {
    _maybeFail();
    uploads.add(documentType);
    uploadedBytes[documentType] = bytes;
  }

  final Map<String, List<int>> uploadedBytes = {};

  @override
  Future<Map<String, dynamic>> submitApplication(String id, int version) async {
    _maybeFail();
    return _server('pending_am');
  }

  @override
  Future<Map<String, dynamic>> fetchApplication(String id) async => _server('draft');
}

void main() {
  late FakeApi api;
  late MemoryDraftStore store;
  late MemoryDocumentVault vault;
  late DraftController controller;

  setUp(() {
    api = FakeApi();
    store = MemoryDraftStore();
    vault = MemoryDocumentVault();
    controller = DraftController(
      draft: Draft(clientId: 'c1', mppId: 'm1', mppLabel: '1305 Test'),
      api: api,
      store: store,
      vault: vault,
      debounce: const Duration(hours: 1),
    );
  });

  tearDown(() => controller.dispose());

  test('every change is on the device at once', () async {
    controller.setValue('applicant', 'full_name', 'Test');
    await Future<void>.delayed(Duration.zero);

    final saved = (await store.all()).single;
    expect(saved.section('applicant')['full_name'], 'Test');
    expect(saved.needsSync, isTrue);
  });

  test('a draft reaches the server and creates one application', () async {
    controller.setValue('applicant', 'full_name', 'Test');
    await controller.sync();
    controller.setValue('applicant', 'full_name', 'Test 2');
    await controller.sync();

    expect(api.creates, 1);
    expect(api.saves, hasLength(2));
    expect(api.saves[1]['version'], 2);
    expect(controller.state, SyncState.saved);
  });

  test('a draft started before its MPP had a place takes it from the server', () async {
    api.mppPlace = {'tehsil': 'Gyanpur'};
    controller.setValue('address', 'tehsil', 'Typed');
    await controller.sync();

    expect(controller.draft.place, {'tehsil': 'Gyanpur'});
    expect((await store.all()).single.place, {'tehsil': 'Gyanpur'});
  });

  test('offline work stays on the phone and goes when back online', () async {
    api.failWith = const OfflineException();
    controller.setValue('address', 'tehsil', 'Bhadohi');
    await controller.sync();

    expect(controller.state, SyncState.offline);
    expect((await store.all()).single.needsSync, isTrue);

    api.failWith = null;
    await controller.sync();

    expect(controller.state, SyncState.saved);
    expect(controller.draft.needsSync, isFalse);
  });

  test('a form on screen retries by itself after losing the network', () async {
    final retrying = DraftController(
      draft: Draft(clientId: 'c2', mppId: 'm1', mppLabel: 'x'),
      api: api,
      store: store,
      debounce: const Duration(hours: 1),
      offlineRetry: const Duration(milliseconds: 10),
    );
    addTearDown(retrying.dispose);
    api.failWith = const OfflineException();
    retrying.setValue('address', 'tehsil', 'Bhadohi');
    await retrying.sync();
    api.failWith = null;

    await Future<void>.delayed(const Duration(milliseconds: 60));

    expect(retrying.state, SyncState.saved);
  });

  test('a sensitive number leaves the device once the server has it', () async {
    controller.setAadhaar('234123412346');
    await controller.sync();

    expect(api.saves.single['aadhaar'], '234123412346');
    expect(controller.draft.pendingAadhaar, isNull);
    expect((await store.all()).single.encode(), isNot(contains('234123412346')));
    expect(controller.draft.hasAadhaar, isTrue);
  });

  test('a scanned Aadhaar QR goes to the server once and leaves the phone', () async {
    controller.setAadhaarQr('123456789');
    await controller.sync();

    expect(api.saves.single['qr'], '123456789');
    expect(controller.draft.pendingAadhaarQr, isNull);
    expect((await store.all()).single.encode(), isNot(contains('123456789')));
  });

  test('a sensitive number survives while offline', () async {
    api.failWith = const OfflineException();
    controller.setAadhaar('234123412346');
    await controller.sync();

    expect(controller.draft.pendingAadhaar, '234123412346');
  });

  test('a photo goes into the vault, not left where the camera put it', () async {
    final folder = await Directory.systemTemp.createTemp();
    final file = File('${folder.path}/card.jpg')..writeAsBytesSync([1, 2, 3]);

    await controller.attachDocument('aadhaar_front', file.path);

    expect(file.existsSync(), isFalse);
    expect(await controller.imageOf('aadhaar_front'), [1, 2, 3]);
  });

  test('uploaded pictures are removed from the phone', () async {
    final folder = await Directory.systemTemp.createTemp();
    final file = File('${folder.path}/card.jpg')..writeAsBytesSync([1, 2, 3]);

    await controller.attachDocument('aadhaar_front', file.path);
    await controller.sync();

    expect(api.uploads, ['aadhaar_front']);
    expect(api.uploadedBytes['aadhaar_front'], [1, 2, 3]);
    expect(controller.draft.uploadedDocuments, contains('aadhaar_front'));
    expect(vault.files, isEmpty);
  });

  test('a retaken photo replaces the earlier one in the vault', () async {
    final folder = await Directory.systemTemp.createTemp();
    for (final bytes in [
      [1],
      [2],
    ]) {
      final file = File('${folder.path}/p${bytes.first}.jpg')..writeAsBytesSync(bytes);
      await controller.attachDocument('photo', file.path);
    }

    expect(vault.files, hasLength(1));
    expect(await controller.imageOf('photo'), [2]);
  });

  test('a photo lost from the phone is not sent, and shows as still to take', () async {
    controller.draft
      ..pendingDocuments['passbook'] = 'vault://c1/gone'
      ..needsSync = true;

    await controller.sync();

    expect(api.uploads, isEmpty);
    expect(controller.draft.hasDocument('passbook'), isFalse);
  });

  test('a submitted form leaves nothing in the vault', () async {
    final folder = await Directory.systemTemp.createTemp();
    final file = File('${folder.path}/sign.png')..writeAsBytesSync([9]);
    await controller.attachDocument('member_signature', file.path);
    vault.files['vault://c1/left-over'] = Uint8List(1);

    expect(await controller.submit(), isTrue);

    expect(vault.files, isEmpty);
  });

  test('a stale edit becomes a conflict, not an overwrite', () async {
    api.failWith = ApiException(409, 'stale_version', 'Changed');
    controller.draft.serverId = 'server-1';
    controller.draft.version = 1;
    controller.setValue('address', 'tehsil', 'Old');
    await controller.sync();
    expect(controller.state, SyncState.conflict);

    api.failWith = null;
    await controller.reloadFromServer();

    expect(controller.draft.section('applicant')['full_name'], 'From server');
    expect(controller.state, SyncState.saved);
  });

  test('a duplicate Aadhaar is shown at once and dropped', () async {
    controller.draft.serverId = 'server-1';
    controller.draft.version = 1;
    api.failWith = ApiException(409, 'duplicate_record', 'Already exists');
    controller.setAadhaar('234123412346');
    await controller.sync();

    expect(controller.aadhaarError, Taken.aadhaar);
    expect(controller.draft.pendingAadhaar, isNull);
  });

  test('a submitted form is cleared from the phone', () async {
    controller.setValue('applicant', 'full_name', 'Test');

    expect(await controller.submit(), isTrue);

    expect(controller.draft.status, 'pending_am');
    expect(await store.all(), isEmpty);
  });

  test('field problems from the server come back to the form', () async {
    controller.draft
      ..serverId = 'server-1'
      ..version = 1;
    controller.setValue('bank', 'ifsc', 'BAD');
    await controller.sync();
    api.failWith = ApiException(400, 'validation_error', 'Invalid', {
      'bank.ifsc': ['Enter a valid IFSC.'],
    });

    final saved = await controller.submit();

    expect(saved, isFalse);
    expect(controller.serverErrors['bank.ifsc'], 'Enter a valid IFSC.');
    expect(await store.all(), isNotEmpty);
  });

  test('fixing a field clears its problem', () {
    controller.serverErrors = {'bank.ifsc': 'Bad'};
    controller.setValue('bank', 'ifsc', 'UBIN0572161');
    expect(controller.serverErrors, isEmpty);
  });

  test('a draft survives being written and read back', () {
    final draft = Draft(clientId: 'c', mppId: 'm', mppLabel: 'l')
      ..pendingDocuments['photo'] = '/x.jpg'
      ..uploadedDocuments.add('passbook')
      ..rejectedFields.add('bank.ifsc');

    final back = Draft.decode(draft.encode());

    expect(back.pendingDocuments['photo'], '/x.jpg');
    expect(back.hasDocument('passbook'), isTrue);
    expect(back.rejectedFields, ['bank.ifsc']);
  });
}
