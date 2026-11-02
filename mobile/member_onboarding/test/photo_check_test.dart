import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:member_onboarding/src/ui/device_services.dart';

const size = 64;

Uint8List picture(int Function(int x, int y) shade) {
  final pixels = Uint8List(size * size * 4);
  for (var y = 0; y < size; y++) {
    for (var x = 0; x < size; x++) {
      final at = (y * size + x) * 4;
      final value = shade(x, y);
      pixels
        ..[at] = value
        ..[at + 1] = value
        ..[at + 2] = value
        ..[at + 3] = 255;
    }
  }
  return pixels;
}

void main() {
  test('a photo with sharp print is fine', () {
    final text = picture((x, y) => (x ~/ 3 + y ~/ 3).isEven ? 30 : 230);
    expect(photoProblem(text, size, size), isNull);
  });

  test('a photo taken in the dark is too dark', () {
    expect(
      photoProblem(picture((x, y) => (x + y).isEven ? 10 : 40), size, size),
      PhotoProblem.dark,
    );
  });

  test('a smooth photo with no edges is blurred', () {
    final smear = picture((x, y) => 120 + (x + y) ~/ 4);
    expect(photoProblem(smear, size, size), PhotoProblem.blurry);
  });
}
