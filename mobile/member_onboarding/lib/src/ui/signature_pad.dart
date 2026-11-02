import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:uuid/uuid.dart';

import 'strings.dart';

class _StrokePainter extends CustomPainter {
  _StrokePainter(this.strokes);

  final List<List<Offset>> strokes;

  static final _ink = Paint()
    ..color = const Color(0xFF10205E)
    ..strokeWidth = 3
    ..strokeCap = StrokeCap.round
    ..style = PaintingStyle.stroke;

  void paintStrokes(Canvas canvas) {
    for (final stroke in strokes) {
      if (stroke.length == 1) canvas.drawPoints(ui.PointMode.points, stroke, _ink);
      final path = Path();
      for (final (index, point) in stroke.indexed) {
        index == 0 ? path.moveTo(point.dx, point.dy) : path.lineTo(point.dx, point.dy);
      }
      canvas.drawPath(path, _ink);
    }
  }

  @override
  void paint(Canvas canvas, Size size) => paintStrokes(canvas);

  @override
  bool shouldRepaint(_StrokePainter old) => true;
}

/// Opens full screen, so the member has room to sign. Returns a file path.
class SignaturePadScreen extends StatefulWidget {
  const SignaturePadScreen({super.key});

  @override
  State<SignaturePadScreen> createState() => _SignaturePadScreenState();
}

class _SignaturePadScreenState extends State<SignaturePadScreen> {
  static const _scale = 2.0;
  static const _background = Colors.white;

  final _strokes = <List<Offset>>[];
  final _areaKey = GlobalKey();

  Future<void> _save() async {
    final size = _areaKey.currentContext!.size!;
    final recorder = ui.PictureRecorder();
    final canvas = Canvas(recorder)
      ..scale(_scale)
      ..drawRect(Offset.zero & size, Paint()..color = _background);
    _StrokePainter(_strokes).paintStrokes(canvas);

    final image = await recorder.endRecording().toImage(
      (size.width * _scale).ceil(),
      (size.height * _scale).ceil(),
    );
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    final folder = await getTemporaryDirectory();
    final file = File('${folder.path}/${const Uuid().v4()}.png');
    await file.writeAsBytes(bytes!.buffer.asUint8List());
    if (mounted) Navigator.pop(context, file.path);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(Strings.memberSignature),
        actions: [
          TextButton(
            onPressed: _strokes.isEmpty ? null : () => setState(_strokes.clear),
            child: const Text(Strings.clear),
          ),
        ],
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(Strings.signHere),
              const SizedBox(height: 8),
              Expanded(
                child: Container(
                  decoration: BoxDecoration(border: Border.all(color: Colors.black38)),
                  child: GestureDetector(
                    onPanStart: (start) => setState(() => _strokes.add([start.localPosition])),
                    onPanUpdate: (update) =>
                        setState(() => _strokes.last.add(update.localPosition)),
                    child: CustomPaint(
                      key: _areaKey,
                      painter: _StrokePainter(_strokes),
                      child: const SizedBox.expand(),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 12),
              FilledButton(
                style: FilledButton.styleFrom(
                  shape: const RoundedRectangleBorder(),
                  minimumSize: const Size.fromHeight(52),
                ),
                onPressed: _strokes.isEmpty ? null : _save,
                child: const Text(Strings.saveSignature),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
