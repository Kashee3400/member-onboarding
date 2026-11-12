import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../api/onboarding_api.dart';
import '../models/form_schema.dart';
import 'record_card.dart';
import 'strings.dart';

/// Banner shown when the device is offline or network errors occur.
class OfflineBanner extends StatelessWidget {
  const OfflineBanner({
    required this.text,
    required this.onRetry,
    super.key,
  });

  final String text;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Material(
      color: scheme.tertiaryContainer,
      borderRadius: BorderRadius.circular(14),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 8, 6, 8),
        child: Row(
          children: [
            Icon(Icons.wifi_off_rounded, color: scheme.onTertiaryContainer),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                text,
                style: TextStyle(color: scheme.onTertiaryContainer),
              ),
            ),
            TextButton(onPressed: onRetry, child: const Text(Strings.retry)),
          ],
        ),
      ),
    );
  }
}

/// The top card allowing facilitators to pick an MPP and start a new onboarding form.
class StartCard extends StatelessWidget {
  const StartCard({
    required this.mpps,
    required this.chosen,
    required this.onChoose,
    required this.onStart,
    super.key,
  });

  final List<MppSummary> mpps;
  final MppSummary? chosen;
  final ValueChanged<MppSummary?> onChoose;
  final VoidCallback? onStart;

  int get mppCount => mpps.length;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            scheme.primary,
            Color.lerp(scheme.primary, scheme.tertiary, 0.55)!,
          ],
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: scheme.onPrimary.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(
                  Icons.person_add_alt_1_rounded,
                  color: scheme.onPrimary,
                ),
              ),
              const Spacer(),
              if (mppCount > 0)
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    color: scheme.onPrimary.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    '$mppCount ${Strings.mppsAssigned}',
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: scheme.onPrimary,
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 14),
          Text(
            Strings.startTitle,
            style: theme.textTheme.titleLarge?.copyWith(
              color: scheme.onPrimary,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            Strings.startHint,
            style: theme.textTheme.bodyMedium?.copyWith(
              color: scheme.onPrimary.withValues(alpha: 0.85),
            ),
          ),
          const SizedBox(height: 16),
          MppField(mpps: mpps, chosen: chosen, onChoose: onChoose),
          const SizedBox(height: 10),
          FilledButton.icon(
            style: FilledButton.styleFrom(
              backgroundColor: scheme.onPrimary,
              foregroundColor: scheme.primary,
              minimumSize: const Size.fromHeight(48),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
            onPressed: onStart,
            icon: const Icon(Icons.add_rounded),
            label: const Text(
              Strings.newForm,
              style: TextStyle(fontWeight: FontWeight.w700),
            ),
          ),
        ],
      ),
    );
  }
}

/// Searchable dropdown field for choosing an assigned MPP.
class MppField extends StatelessWidget {
  const MppField({
    required this.mpps,
    required this.chosen,
    required this.onChoose,
    super.key,
  });

  final List<MppSummary> mpps;
  final MppSummary? chosen;
  final ValueChanged<MppSummary?> onChoose;

  static String label(MppSummary mpp) => '${mpp.code} ${mpp.name}';

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return LayoutBuilder(
      builder: (context, box) => DropdownMenu<MppSummary>(
        key: ValueKey('mpp-field-${chosen?.id}'),
        width: box.maxWidth,
        menuHeight: 320,
        initialSelection: chosen,
        enabled: mpps.isNotEmpty,
        enableFilter: true,
        enableSearch: true,
        requestFocusOnTap: true,
        hintText: Strings.searchMpp,
        leadingIcon: const Icon(
          Icons.meeting_room_outlined,
          color: Color(0xFF10B981),
        ),
        textStyle: TextStyle(
          color: scheme.onSurface,
          fontWeight: FontWeight.w600,
        ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: scheme.surface,
          contentPadding: const EdgeInsets.symmetric(horizontal: 12),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide.none,
          ),
        ),
        dropdownMenuEntries: [
          for (final mpp in mpps)
            DropdownMenuEntry<MppSummary>(value: mpp, label: label(mpp)),
        ],
        onSelected: onChoose,
      ),
    );
  }
}

/// Header for home screen sections with an optional count badge and action button.
class HomeSectionTitle extends StatelessWidget {
  const HomeSectionTitle(this.text, {this.count, this.onTap, super.key});

  final String text;
  final int? count;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    return Row(
      children: [
        Text(
          text,
          style: theme.textTheme.titleSmall?.copyWith(
            fontWeight: FontWeight.w700,
          ),
        ),
        if (count != null && count! > 0) ...[
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 1),
            decoration: BoxDecoration(
              color: scheme.secondaryContainer,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Text(
              '$count',
              style: theme.textTheme.labelSmall?.copyWith(
                color: scheme.onSecondaryContainer,
              ),
            ),
          ),
        ],
        const Spacer(),
        if (onTap != null)
          InkWell(
            onTap: onTap,
            child: Icon(
              Icons.chevron_right_rounded,
              color: scheme.onSurfaceVariant,
            ),
          ),
      ],
    );
  }
}

/// A metric tile showing counts (e.g. Total, Waiting, Approved, Returned).
class CountTile extends StatelessWidget {
  const CountTile({
    required this.label,
    required this.value,
    required this.onTap,
    this.color,
    super.key,
  });

  final String label;
  final int value;
  final VoidCallback onTap;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    return Expanded(
      child: Material(
        color: scheme.surface,
        borderRadius: BorderRadius.circular(14),
        child: InkWell(
          borderRadius: BorderRadius.circular(14),
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 12),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: scheme.outlineVariant),
            ),
            child: Row(
              children: [
                Text(
                  '$value',
                  style: theme.textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                    color: color ?? scheme.onSurface,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    label,
                    maxLines: 2,
                    style: theme.textTheme.labelMedium?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Empty state tile when there are no unfinished drafts.
class EmptyDraftsTile extends StatelessWidget {
  const EmptyDraftsTile({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 28, horizontal: 16),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Column(
        children: [
          Icon(Icons.inbox_outlined, size: 36, color: scheme.onSurfaceVariant),
          const SizedBox(height: 8),
          Text(Strings.noDrafts, style: theme.textTheme.titleSmall),
          const SizedBox(height: 4),
          Text(
            Strings.noDraftsHint,
            textAlign: TextAlign.center,
            style: theme.textTheme.bodySmall?.copyWith(
              color: scheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }
}

/// Dialog announcing returned (rejected) applications on visit.
class SentBackDialog extends StatelessWidget {
  const SentBackDialog({
    required this.rejected,
    required this.photoLoader,
    super.key,
  });

  final List<ApplicationSummary> rejected;
  final Future<Uint8List?> Function(String photoId) photoLoader;

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      key: const ValueKey('sent_back.alert'),
      icon: Icon(
        Icons.assignment_return_rounded,
        color: Colors.red.shade600,
        size: 36,
      ),
      title: Text('${rejected.length} ${Strings.sentBackAlertTitle}'),
      content: SizedBox(
        width: double.maxFinite,
        child: ListView(
          shrinkWrap: true,
          children: [
            const Padding(
              padding: EdgeInsets.only(bottom: 8),
              child: Text(Strings.sentBackAlertBody),
            ),
            for (final item in rejected)
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: MemberPhoto(
                  name: item.applicantName,
                  photo: item.photoId == null ? null : photoLoader(item.photoId!),
                  size: 40,
                ),
                title: Text(
                  item.applicantName.isEmpty
                      ? Strings.untitled
                      : item.applicantName,
                ),
                subtitle: Text(
                  [
                    if (item.formNumber.isNotEmpty) item.formNumber,
                    item.mppCode,
                  ].join(' · '),
                ),
                trailing: const Icon(Icons.chevron_right_rounded),
                onTap: () => Navigator.pop(context, item),
              ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text(Strings.later),
        ),
      ],
    );
  }
}
