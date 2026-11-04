import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'package:image_cropper/image_cropper.dart';
import 'package:image_picker/image_picker.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import 'strings.dart';

/// Phone hardware, kept behind one class so screens can be tested without it.
class DeviceServices {
  const DeviceServices();

  /// Small enough to upload on a weak village network, sharp enough to read a card.
  static const _maxImageWidth = 1600.0;
  static const _imageQuality = 75;

  /// A photo already on the phone, such as one the member sent on WhatsApp. The picker
  /// hands over a copy, so the gallery's own picture is never touched.
  Future<String?> choosePhoto() async {
    final photo = await ImagePicker().pickImage(
      source: ImageSource.gallery,
      maxWidth: _maxImageWidth,
      imageQuality: _imageQuality,
    );
    return photo?.path;
  }

  Future<String?> takePhoto() async {
    final photo = await ImagePicker().pickImage(
      source: ImageSource.camera,
      maxWidth: _maxImageWidth,
      imageQuality: _imageQuality,
    );
    return photo?.path;
  }

  /// The shape each document is cut to. Null lets the facilitator choose.
  static const cropRatios = <String, CropAspectRatio?>{
    // An Aadhaar card is ID-1 size, 85.6 x 54 mm.
    'aadhaar_front': CropAspectRatio(ratioX: 85.6, ratioY: 54),
    'aadhaar_back': CropAspectRatio(ratioX: 85.6, ratioY: 54),
    // Passport style, the shape of the photo box on the printed form.
    'photo': CropAspectRatio(ratioX: 3, ratioY: 4),
    'member_signature': CropAspectRatio(ratioX: 3, ratioY: 1),
    'member_thumbprint': CropAspectRatio(ratioX: 1, ratioY: 1),
    // First pages differ from bank to bank.
    'passbook': null,
  };

  /// Opens the photo to cut it to the document's shape, with rotate and zoom. Gives
  /// back the cropped picture, or the photo as it was when the crop is cancelled
  /// or the phone cannot crop: a photo is never lost here.
  Future<String> cropPhoto(
    String path, {
    required String type,
    required String title,
    required Color color,
  }) async {
    final ratio = cropRatios[type];
    final locked = ratio != null;
    try {
      final cropped = await ImageCropper().cropImage(
        sourcePath: path,
        aspectRatio: ratio,
        maxWidth: _maxImageWidth.toInt(),
        compressQuality: 85,
        uiSettings: [
          AndroidUiSettings(
            toolbarTitle: title,
            toolbarColor: color,
            toolbarWidgetColor: Colors.white,
            activeControlsWidgetColor: color,
            lockAspectRatio: locked,
            showCropGrid: true,
          ),
          IOSUiSettings(
            title: title,
            aspectRatioLockEnabled: locked,
            resetAspectRatioEnabled: !locked,
            aspectRatioPickerButtonHidden: locked,
          ),
        ],
      );
      return cropped?.path ?? path;
    } catch (_) {
      return path;
    }
  }

  /// Looked at on the phone, so a bad photo is retaken while the member is still there.
  /// Null when the photo looks fine, or could not be read.
  Future<PhotoProblem?> checkPhoto(String path) async {
    try {
      final codec = await ui.instantiateImageCodec(
        await File(path).readAsBytes(),
        targetWidth: photoCheckWidth,
      );
      final image = (await codec.getNextFrame()).image;
      final pixels = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
      final (width, height) = (image.width, image.height);
      image.dispose();
      if (pixels == null) return null;
      return photoProblem(pixels.buffer.asUint8List(), width, height);
    } catch (_) {
      return null;
    }
  }

  /// Returns (latitude, longitude), or null when no position could be had.
  Future<(double, double)?> currentPosition() async {
    if (!await Geolocator.isLocationServiceEnabled()) return null;
    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.denied || permission == LocationPermission.deniedForever) {
      return null;
    }
    final position = await Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.high,
        timeLimit: Duration(seconds: 20),
      ),
    );
    return (position.latitude, position.longitude);
  }

  /// Bank and branch for an IFSC, or null. Only the public IFSC leaves the phone.
  Future<(String, String)?> lookupIfsc(String ifsc) async {
    try {
      final response = await http
          .get(Uri.parse('https://ifsc.razorpay.com/$ifsc'))
          .timeout(const Duration(seconds: 8));
      if (response.statusCode != 200) return null;
      final body = jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
      return ('${body['BANK']}', '${body['BRANCH']}');
    } catch (_) {
      return null;
    }
  }

  Future<String?> scanQr(BuildContext context) {
    return Navigator.of(
      context,
    ).push<String>(MaterialPageRoute(builder: (_) => const _QrScannerScreen()));
  }
}

enum PhotoProblem { dark, blurry }

/// Photos are judged at this width, the same for every phone camera.
const photoCheckWidth = 320;

/// Below this average brightness (0 to 255) a card cannot be read.
const _darkBelow = 55.0;

/// Below this spread of edge strength there are no sharp edges: the photo moved or
/// was out of focus. Measured at [photoCheckWidth]; tune it with real village photos.
const _blurryBelow = 45.0;

/// Judges a photo from its raw RGBA pixels: too dark, too blurry, or fine (null).
PhotoProblem? photoProblem(Uint8List rgba, int width, int height) {
  if (width < 3 || height < 3) return null;
  final gray = Float64List(width * height);
  var total = 0.0;
  for (var at = 0; at < gray.length; at++) {
    final pixel = at * 4;
    final value = 0.299 * rgba[pixel] + 0.587 * rgba[pixel + 1] + 0.114 * rgba[pixel + 2];
    gray[at] = value;
    total += value;
  }
  if (total / gray.length < _darkBelow) return PhotoProblem.dark;

  // Variance of the Laplacian: a sharp photo has strong edges, a blurred one has none.
  var sum = 0.0;
  var squares = 0.0;
  var count = 0;
  for (var y = 1; y < height - 1; y++) {
    for (var x = 1; x < width - 1; x++) {
      final at = y * width + x;
      final edge = gray[at - 1] + gray[at + 1] + gray[at - width] + gray[at + width] - 4 * gray[at];
      sum += edge;
      squares += edge * edge;
      count++;
    }
  }
  final mean = sum / count;
  return squares / count - mean * mean < _blurryBelow ? PhotoProblem.blurry : null;
}

class _QrScannerScreen extends StatefulWidget {
  const _QrScannerScreen();

  @override
  State<_QrScannerScreen> createState() => _QrScannerScreenState();
}

class _QrScannerScreenState extends State<_QrScannerScreen> {
  bool _finished = false;

  void _onDetect(BarcodeCapture capture) {
    final value = capture.barcodes.firstOrNull?.rawValue;
    if (value == null || _finished) return;
    _finished = true;
    Navigator.pop(context, value);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text(Strings.scanAadhaar)),
      body: Stack(
        children: [
          MobileScanner(onDetect: _onDetect),
          const Align(
            alignment: Alignment.bottomCenter,
            child: Padding(
              padding: EdgeInsets.all(24),
              child: Text(Strings.scanHint, style: TextStyle(color: Colors.white, fontSize: 16)),
            ),
          ),
        ],
      ),
    );
  }
}
