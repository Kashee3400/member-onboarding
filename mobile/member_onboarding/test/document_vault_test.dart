import 'dart:io';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:member_onboarding/src/storage/document_vault.dart';

void main() {
  late Directory root;
  late SecureDocumentVault vault;

  setUp(() async {
    FlutterSecureStorage.setMockInitialValues({});
    root = await Directory.systemTemp.createTemp();
    vault = SecureDocumentVault(root: () async => root);
  });

  tearDown(() => root.delete(recursive: true));

  Future<File> photo(List<int> bytes, [String name = 'card.jpg']) async =>
      File('${root.path}/$name')..writeAsBytesSync(bytes);

  test('a kept photo is encrypted on disk and reads back the same', () async {
    final bytes = List<int>.generate(64, (index) => index);
    final source = await photo(bytes);

    final kept = await vault.keep('c1', 'aadhaar_front', source.path);

    expect(source.existsSync(), isFalse);
    final onDisk = File(kept).readAsBytesSync();
    expect(onDisk, isNot(containsAllInOrder(bytes.take(16))));
    expect(await vault.read(kept), bytes);
  });

  test('another key cannot read it', () async {
    final kept = await vault.keep('c1', 'passbook', (await photo([1, 2, 3])).path);
    FlutterSecureStorage.setMockInitialValues({});

    final stranger = SecureDocumentVault(root: () async => root);

    expect(() => stranger.read(kept), throwsA(anything));
  });

  test('a submitted form leaves no files behind', () async {
    await vault.keep('c1', 'photo', (await photo([1], 'a.jpg')).path);
    await vault.keep('c1', 'member_signature', (await photo([2], 'b.png')).path);

    await vault.removeAll('c1');

    expect(Directory('${root.path}/member_onboarding_documents/c1').existsSync(), isFalse);
  });
}
