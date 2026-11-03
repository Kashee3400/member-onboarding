import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/form_schema.dart';
import 'fields.dart';
import 'strings.dart';

/// A titled group of fields, so a long step reads as a few short parts.
class SectionCard extends StatelessWidget {
  const SectionCard({required this.children, this.title, this.icon, this.trailing, super.key});

  final String? title;
  final IconData? icon;
  final Widget? trailing;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    // Material, not a coloured box, so list rows inside still show their tap ripple.
    return Material(
      color: scheme.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: scheme.outlineVariant),
      ),
      child: Padding(
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (title != null) ...[
            Row(
              children: [
                if (icon != null) ...[
                  Icon(icon, size: 20, color: scheme.primary),
                  const SizedBox(width: 8),
                ],
                Expanded(
                  child: Text(
                    title!,
                    style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                  ),
                ),
                ?trailing,
              ],
            ),
            const SizedBox(height: 12),
          ],
          for (final child in children) ...[child, const SizedBox(height: 12)],
        ],
      ),
      ),
    );
  }
}

/// A short list of answers as chips: one tap, and every answer is in view.
class ChipChoice extends StatelessWidget {
  const ChipChoice({
    required this.label,
    required this.value,
    required this.options,
    required this.onChanged,
    this.retired = const [],
    this.optional = false,
    this.error,
    super.key,
  });

  final String label;
  final String? value;
  final List<ChoiceOption> options;

  /// Not offered, but shown when the form already holds one.
  final List<ChoiceOption> retired;
  final ValueChanged<String> onChanged;
  final bool optional;
  final String? error;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final offered = options.any((option) => option.value == value);
    final held = value == null || offered ? null : choiceLabel(value, options, retired);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        FieldLabel(label, optional: optional),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            // An old answer stays visible, but cannot be chosen again.
            if (held != null) ChoiceChip(label: Text(held), selected: true, onSelected: null),
            for (final option in options)
              ChoiceChip(
                label: Text(option.label),
                selected: option.value == value,
                showCheckmark: false,
                labelStyle: TextStyle(
                  fontWeight: option.value == value ? FontWeight.w700 : FontWeight.w500,
                ),
                side: BorderSide(color: error != null ? scheme.error : scheme.outlineVariant),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                onSelected: (_) => onChanged(option.value),
              ),
          ],
        ),
        if (error != null)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(error!, style: TextStyle(color: scheme.error, fontSize: 13)),
          ),
      ],
    );
  }
}

/// Where a document photo comes from: the phone until it is sent, then the server.
typedef UploadedImage = Future<Uint8List?> Function(String type);

/// A taken photo, from the phone's file or, once uploaded, fetched again.
class DocumentImage extends StatelessWidget {
  const DocumentImage({
    required this.type,
    required this.localPath,
    required this.uploaded,
    required this.load,
    this.fit = BoxFit.cover,
    super.key,
  });

  final String type;
  final String? localPath;
  final bool uploaded;
  final UploadedImage load;
  final BoxFit fit;

  @override
  Widget build(BuildContext context) {
    final path = localPath;
    if (path != null) {
      return Image.file(File(path), fit: fit, errorBuilder: (_, _, _) => const _NoImage());
    }
    if (!uploaded) return const _NoImage();
    return FutureBuilder<Uint8List?>(
      future: load(type),
      builder: (context, snapshot) {
        final bytes = snapshot.data;
        if (bytes != null) return Image.memory(bytes, fit: fit);
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2)));
        }
        // Offline, an uploaded photo cannot be shown, but it is safe on the server.
        return const _NoImage(icon: Icons.cloud_done_outlined);
      },
    );
  }
}

class _NoImage extends StatelessWidget {
  const _NoImage({this.icon = Icons.image_not_supported_outlined});

  final IconData icon;

  @override
  Widget build(BuildContext context) =>
      Center(child: Icon(icon, color: Theme.of(context).colorScheme.onSurfaceVariant));
}

/// One document: the photo itself once taken, with its state on top.
class DocumentTile extends StatelessWidget {
  const DocumentTile({
    required this.label,
    required this.hint,
    required this.icon,
    required this.taken,
    required this.image,
    required this.onTake,
    required this.onOpen,
    this.uploaded = false,
    this.doubtful = false,
    this.error,
    super.key,
  });

  final String label;
  final String hint;
  final IconData icon;
  final bool taken;
  final bool uploaded;
  final bool doubtful;
  final String? error;
  final Widget image;
  final VoidCallback onTake;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final (badge, badgeColor) = error != null
        ? (error!, scheme.error)
        : doubtful
        ? (Strings.checkPhoto, Colors.orange.shade800)
        : uploaded
        ? (Strings.uploaded, Colors.green.shade700)
        : (Strings.onPhone, scheme.tertiary);

    return Material(
      color: scheme.surface,
      borderRadius: BorderRadius.circular(16),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: taken ? onOpen : onTake,
        child: Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: error != null ? scheme.error : scheme.outlineVariant,
              width: error != null ? 1.5 : 1,
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              AspectRatio(
                aspectRatio: 4 / 3,
                child: taken
                    ? Stack(
                        fit: StackFit.expand,
                        children: [
                          image,
                          Positioned(
                            left: 8,
                            top: 8,
                            child: Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                              decoration: BoxDecoration(
                                color: badgeColor,
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Text(
                                badge,
                                style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w600),
                              ),
                            ),
                          ),
                        ],
                      )
                    : Container(
                        color: scheme.surfaceContainerHigh,
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(icon, size: 34, color: scheme.primary),
                            const SizedBox(height: 6),
                            Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 8),
                              child: Text(
                                hint,
                                textAlign: TextAlign.center,
                                maxLines: 2,
                                style: theme.textTheme.labelSmall?.copyWith(color: scheme.onSurfaceVariant),
                              ),
                            ),
                          ],
                        ),
                      ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(10, 8, 6, 8),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        label,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w600),
                      ),
                    ),
                    Icon(
                      taken ? Icons.check_circle : Icons.photo_camera_outlined,
                      size: 20,
                      color: taken ? Colors.green.shade600 : scheme.primary,
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// A taken photo, full screen and zoomable, with what can be done to it.
class DocumentViewer extends StatelessWidget {
  const DocumentViewer({required this.label, required this.image, required this.onRetake, super.key});

  final String label;
  final Widget image;
  final VoidCallback onRetake;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: Text(label),
        systemOverlayStyle: SystemUiOverlayStyle.light,
      ),
      body: InteractiveViewer(maxScale: 5, child: Center(child: image)),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: FilledButton.icon(
            style: FilledButton.styleFrom(
              minimumSize: const Size.fromHeight(50),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
            onPressed: () {
              Navigator.pop(context);
              onRetake();
            },
            icon: const Icon(Icons.photo_camera_outlined),
            label: const Text(Strings.retake),
          ),
        ),
      ),
    );
  }
}

/// One household member, added or corrected in a sheet over the list.
class PersonSheet extends StatefulWidget {
  const PersonSheet({
    required this.person,
    required this.genders,
    required this.relations,
    required this.checkAge,
    super.key,
  });

  final Map<String, dynamic> person;
  final List<ChoiceOption> genders;
  final List<ChoiceOption> relations;
  final String? Function(String) checkAge;

  @override
  State<PersonSheet> createState() => _PersonSheetState();
}

class _PersonSheetState extends State<PersonSheet> {
  late final Map<String, dynamic> _person = {...widget.person};
  bool _tried = false;

  String? get _ageProblem => widget.checkAge('${_person['age'] ?? ''}');

  bool get _complete =>
      '${_person['name'] ?? ''}'.trim().isNotEmpty &&
      _person['gender'] != null &&
      _person['relation'] != null &&
      '${_person['age'] ?? ''}'.isNotEmpty &&
      _ageProblem == null;

  void _set(String key, Object? value) => setState(() => _person[key] = value);

  void _step(int by) {
    // The box takes the new number only once it is not being typed in.
    FocusScope.of(context).unfocus();
    final age = (int.tryParse('${_person['age'] ?? ''}') ?? 0) + by;
    if (age >= 0 && age <= 120) _set('age', '$age');
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final missing = _tried && !_complete;
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                widget.person.isEmpty ? Strings.addPerson : Strings.editPerson,
                style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 16),
              TextBox(
                key: const ValueKey('person.name'),
                label: Strings.name,
                value: '${_person['name'] ?? ''}',
                error: missing && '${_person['name'] ?? ''}'.trim().isEmpty ? Strings.required : null,
                onChanged: (value) => _person['name'] = value,
              ),
              const SizedBox(height: 14),
              ChipChoice(
                label: Strings.relation,
                value: _person['relation'] as String?,
                options: widget.relations,
                error: missing && _person['relation'] == null ? Strings.required : null,
                onChanged: (value) => _set('relation', value),
              ),
              const SizedBox(height: 14),
              ChipChoice(
                label: Strings.gender,
                value: _person['gender'] as String?,
                options: widget.genders,
                error: missing && _person['gender'] == null ? Strings.required : null,
                onChanged: (value) => _set('gender', value),
              ),
              const SizedBox(height: 14),
              const FieldLabel(Strings.age),
              Row(
                children: [
                  IconButton.filledTonal(
                    onPressed: () => _step(-1),
                    icon: const Icon(Icons.remove),
                  ),
                  const SizedBox(width: 8),
                  SizedBox(
                    width: 90,
                    child: CountCell(
                      key: const ValueKey('person.age'),
                      value: '${_person['age'] ?? ''}',
                      hasError: missing && _ageProblem != null,
                      onChanged: (value) => _set('age', value),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filledTonal(
                    onPressed: () => _step(1),
                    icon: const Icon(Icons.add),
                  ),
                  const SizedBox(width: 12),
                  Text(Strings.years, style: TextStyle(color: scheme.onSurfaceVariant)),
                ],
              ),
              if (missing && _ageProblem != null)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(_ageProblem!, style: TextStyle(color: scheme.error, fontSize: 13)),
                ),
              const SizedBox(height: 20),
              FilledButton(
                style: FilledButton.styleFrom(
                  minimumSize: const Size.fromHeight(50),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
                onPressed: () {
                  if (_complete) {
                    Navigator.pop(context, {..._person, 'name': '${_person['name']}'.trim()});
                  } else {
                    setState(() => _tried = true);
                  }
                },
                child: const Text(Strings.savePerson),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
