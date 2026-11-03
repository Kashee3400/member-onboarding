import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:path_provider/path_provider.dart';
import 'package:uuid/uuid.dart';

/// Where a form's photos wait on the phone until they are uploaded.
///
/// Aadhaar cards and passbooks must not sit in the gallery, nor in a cache the phone
/// may clear while the form waits for a network. Each one is kept encrypted in the
/// app's own folder, and removed once the server has it.
abstract class DocumentVault {
  /// Takes the photo at [sourcePath] into the vault and deletes the original.
  /// Returns where it is now kept.
  Future<String> keep(String clientId, String type, String sourcePath);

  /// The photo's bytes, or null when it is gone.
  Future<Uint8List?> read(String path);

  Future<void> remove(String path);

  /// Everything kept for one form, once it is submitted.
  Future<void> removeAll(String clientId);
}

/// AES-256-GCM, with the key in the phone's keystore: a copied file or a backup of
/// the app's folder cannot be read without this phone.
class SecureDocumentVault implements DocumentVault {
  SecureDocumentVault({FlutterSecureStorage? storage, Future<Directory> Function()? root})
    : _storage = storage ?? const FlutterSecureStorage(),
      _root = root ?? getApplicationSupportDirectory;

  static const _keyName = 'member_onboarding.document_key';
  static const _suffix = '.enc';

  final FlutterSecureStorage _storage;
  final Future<Directory> Function() _root;
  final _cipher = AesGcm.with256bits();
  SecretKey? _key;

  Future<SecretKey> _secret() async {
    final known = _key;
    if (known != null) return known;
    var encoded = await _storage.read(key: _keyName);
    if (encoded == null) {
      final random = Random.secure();
      encoded = base64Encode(List<int>.generate(32, (_) => random.nextInt(256)));
      await _storage.write(key: _keyName, value: encoded);
    }
    return _key = SecretKey(base64Decode(encoded));
  }

  Future<Directory> _folder(String clientId) async {
    final root = await _root();
    return Directory('${root.path}/member_onboarding_documents/$clientId').create(recursive: true);
  }

  @override
  Future<String> keep(String clientId, String type, String sourcePath) async {
    final source = File(sourcePath);
    final box = await _cipher.encrypt(await source.readAsBytes(), secretKey: await _secret());
    final extension = sourcePath.toLowerCase().endsWith('.png') ? 'png' : 'jpg';
    final folder = await _folder(clientId);
    final kept = File('${folder.path}/$type-${const Uuid().v4()}.$extension$_suffix');
    await kept.writeAsBytes(box.concatenation(), flush: true);
    if (await source.exists()) await source.delete();
    return kept.path;
  }

  @override
  Future<Uint8List?> read(String path) async {
    final file = File(path);
    if (!await file.exists()) return null;
    final bytes = await file.readAsBytes();
    // A photo taken before the vault existed is still a plain file.
    if (!path.endsWith(_suffix)) return bytes;
    final box = SecretBox.fromConcatenation(
      bytes,
      nonceLength: _cipher.nonceLength,
      macLength: _cipher.macAlgorithm.macLength,
    );
    return Uint8List.fromList(await _cipher.decrypt(box, secretKey: await _secret()));
  }

  @override
  Future<void> remove(String path) async {
    final file = File(path);
    if (await file.exists()) await file.delete();
  }

  @override
  Future<void> removeAll(String clientId) async {
    final folder = await _folder(clientId);
    if (await folder.exists()) await folder.delete(recursive: true);
  }
}

/// For tests: kept in memory, never on disk.
class MemoryDocumentVault implements DocumentVault {
  final Map<String, Uint8List> files = {};

  int _next = 0;

  // Synchronous file calls: widget tests run on fake time, where real file IO never ends.
  @override
  Future<String> keep(String clientId, String type, String sourcePath) async {
    final source = File(sourcePath);
    final path = 'vault://$clientId/$type-${_next++}';
    if (source.existsSync()) {
      files[path] = source.readAsBytesSync();
      source.deleteSync();
    } else {
      files[path] = Uint8List(0);
    }
    return path;
  }

  @override
  Future<Uint8List?> read(String path) async => files[path];

  @override
  Future<void> remove(String path) async => files.remove(path);

  @override
  Future<void> removeAll(String clientId) async =>
      files.removeWhere((path, _) => path.startsWith('vault://$clientId/'));
}
