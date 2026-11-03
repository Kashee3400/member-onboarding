import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'strings.dart';

/// A day as the forms show it: 03-11-2026.
String formatDate(DateTime date) =>
    '${date.day.toString().padLeft(2, '0')}-${date.month.toString().padLeft(2, '0')}-${date.year}';

Color statusTone(String status) => switch (status) {
  'approved' => Colors.green.shade700,
  'rejected' => Colors.red.shade700,
  'draft' => Colors.blueGrey.shade600,
  _ => Colors.orange.shade800,
};

/// The member's photo when there is one, her initials until it loads or when there is none.
class MemberPhoto extends StatelessWidget {
  const MemberPhoto({required this.name, required this.photo, this.size = 52, super.key});

  final String name;
  final Future<Uint8List?>? photo;
  final double size;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final parts = name.trim().split(RegExp(r'\s+')).where((part) => part.isNotEmpty);
    final initials = parts.take(2).map((part) => part[0].toUpperCase()).join();
    final fallback = Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      color: scheme.primaryContainer,
      child: initials.isEmpty
          ? Icon(Icons.person_outline, color: scheme.onPrimaryContainer)
          : Text(initials, style: TextStyle(color: scheme.onPrimaryContainer, fontWeight: FontWeight.w700)),
    );
    return ClipRRect(
      borderRadius: BorderRadius.circular(size / 4),
      child: SizedBox.square(
        dimension: size,
        child: photo == null
            ? fallback
            : FutureBuilder<Uint8List?>(
                future: photo,
                builder: (context, snapshot) {
                  final bytes = snapshot.data;
                  if (bytes == null || bytes.isEmpty) return fallback;
                  return Image.memory(bytes, fit: BoxFit.cover, errorBuilder: (_, _, _) => fallback);
                },
              ),
      ),
    );
  }
}

class StatusChip extends StatelessWidget {
  const StatusChip({required this.status, required this.label, this.icon, super.key});

  final String status;
  final String label;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final tone = statusTone(status);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(color: tone.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(20)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[Icon(icon, size: 14, color: tone), const SizedBox(width: 4)],
          Text(label, style: TextStyle(color: tone, fontWeight: FontWeight.w700, fontSize: 12.5)),
        ],
      ),
    );
  }
}

/// One form in a list: who it is for, its numbers, when, and where it stands.
class RecordCard extends StatelessWidget {
  const RecordCard({
    required this.name,
    required this.lines,
    required this.status,
    required this.statusLabel,
    required this.photo,
    required this.onTap,
    this.statusIcon,
    super.key,
  });

  final String name;

  /// Short facts under the name, each on its own line; empty ones are left out.
  final List<String> lines;
  final String status;
  final String statusLabel;
  final IconData? statusIcon;
  final Future<Uint8List?>? photo;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final muted = theme.textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant);

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Material(
        color: scheme.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: scheme.outlineVariant),
        ),
        child: InkWell(
          borderRadius: BorderRadius.circular(16),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                MemberPhoto(name: name, photo: photo),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        name.isEmpty ? Strings.untitled : name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                      ),
                      const SizedBox(height: 2),
                      for (final line in lines.where((line) => line.isNotEmpty)) Text(line, style: muted),
                      const SizedBox(height: 8),
                      StatusChip(status: status, label: statusLabel, icon: statusIcon),
                    ],
                  ),
                ),
                Icon(Icons.chevron_right_rounded, color: scheme.onSurfaceVariant),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
