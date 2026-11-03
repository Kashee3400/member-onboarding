import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../api/onboarding_api.dart';
import 'strings.dart';

enum _Range { today, yesterday, week, month, custom }

/// Every form this facilitator started, with counts, for any day or range of days.
class MyRecordsScreen extends StatefulWidget {
  const MyRecordsScreen({required this.api, this.onOpen, super.key});

  final OnboardingApi api;

  /// Opens a form that can still be changed: a draft, or one sent back.
  final Future<void> Function(ApplicationSummary item)? onOpen;

  @override
  State<MyRecordsScreen> createState() => _MyRecordsScreenState();
}

String _date(DateTime date) =>
    '${date.day.toString().padLeft(2, '0')}-${date.month.toString().padLeft(2, '0')}-${date.year}';

Color _tone(String status) => switch (status) {
  'approved' => Colors.green.shade700,
  'rejected' => Colors.red.shade700,
  'draft' => Colors.blueGrey.shade600,
  _ => Colors.orange.shade800,
};

bool _editable(String status) => status == 'draft' || status == 'rejected';

class _MyRecordsScreenState extends State<MyRecordsScreen> {
  static const _statuses = <String?, String>{
    null: Strings.all,
    'draft': Strings.drafts,
    'pending_am,pending_cs,pending_finance': Strings.waiting,
    'approved': Strings.approved,
    'rejected': Strings.returned,
  };

  _Range _range = _Range.today;
  late DateTimeRange _dates = _datesFor(_Range.today);
  String? _status;
  RecordSummary _summary = const RecordSummary();
  final List<ApplicationSummary> _items = [];
  int _total = 0;
  int _page = 1;
  bool _loading = true;
  bool _failed = false;

  /// Member photos, fetched once per visit and kept in memory only.
  final Map<String, Future<Uint8List?>> _photos = {};

  Future<Uint8List?> _photo(String id) => _photos.putIfAbsent(id, () async {
    try {
      return Uint8List.fromList(await widget.api.fetchDocumentFile(id));
    } on Exception {
      return null;
    }
  });

  @override
  void initState() {
    super.initState();
    _load();
  }

  static DateTimeRange _datesFor(_Range range) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    return switch (range) {
      _Range.yesterday => DateTimeRange(
        start: today.subtract(const Duration(days: 1)),
        end: today.subtract(const Duration(days: 1)),
      ),
      _Range.week => DateTimeRange(
        start: today.subtract(Duration(days: today.weekday - 1)),
        end: today,
      ),
      _Range.month => DateTimeRange(start: DateTime(today.year, today.month), end: today),
      _ => DateTimeRange(start: today, end: today),
    };
  }

  Future<void> _load({bool more = false}) async {
    setState(() {
      _loading = true;
      _failed = false;
    });
    try {
      final page = more ? _page + 1 : 1;
      final records = await widget.api.fetchRecords(
        from: _dates.start,
        to: _dates.end,
        status: _status,
        page: page,
      );
      final summary = more
          ? _summary
          : await widget.api.fetchSummary(from: _dates.start, to: _dates.end);
      if (!mounted) return;
      setState(() {
        if (!more) _items.clear();
        _items.addAll(records.items);
        _total = records.total;
        _page = page;
        _summary = summary;
        _loading = false;
      });
    } on OfflineException {
      _fail();
    } on ApiException {
      _fail();
    }
  }

  void _fail() {
    if (!mounted) return;
    setState(() {
      _loading = false;
      _failed = true;
    });
  }

  Future<void> _choose(_Range range) async {
    var dates = _datesFor(range);
    if (range == _Range.custom) {
      final picked = await showDateRangePicker(
        context: context,
        firstDate: DateTime(2020),
        lastDate: DateTime.now(),
        initialDateRange: _dates,
      );
      if (picked == null) return;
      dates = picked;
    }
    setState(() {
      _range = range;
      _dates = dates;
    });
    await _load();
  }

  Future<void> _details(ApplicationSummary item) async {
    final edit = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => _RecordSheet(
        item: item,
        api: widget.api,
        photo: item.photoId == null ? null : _photo(item.photoId!),
        canEdit: widget.onOpen != null && _editable(item.status),
      ),
    );
    if (edit == true && widget.onOpen != null) {
      await widget.onOpen!(item);
      await _load();
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    const labels = {
      _Range.today: Strings.today,
      _Range.yesterday: Strings.yesterday,
      _Range.week: Strings.thisWeek,
      _Range.month: Strings.thisMonth,
      _Range.custom: Strings.pickDates,
    };
    final counts = [
      (Strings.started, _summary.started, scheme.onSurface),
      (Strings.sent, _summary.submitted, scheme.onSurface),
      (Strings.waiting, _summary.pending, Colors.orange.shade800),
      (Strings.approved, _summary.approved, Colors.green.shade700),
      (Strings.returned, _summary.rejected, Colors.red.shade700),
    ];

    Widget chips<T>(Iterable<(T, String)> options, T selected, ValueChanged<T> onTap) =>
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Row(
            children: [
              for (final (value, label) in options)
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: ChoiceChip(
                    label: Text(label),
                    selected: value == selected,
                    showCheckmark: false,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                    onSelected: (_) => onTap(value),
                  ),
                ),
            ],
          ),
        );

    return Scaffold(
      backgroundColor: scheme.surfaceContainerLowest,
      appBar: AppBar(
        title: const Text(Strings.myRecords, style: TextStyle(fontWeight: FontWeight.w700)),
        backgroundColor: scheme.surfaceContainerLowest,
        surfaceTintColor: Colors.transparent,
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.only(top: 4, bottom: 32),
          children: [
            chips([for (final range in _Range.values) (range, labels[range]!)], _range, _choose),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
              child: Text(
                _dates.start == _dates.end
                    ? _date(_dates.start)
                    : '${_date(_dates.start)} – ${_date(_dates.end)}',
                style: theme.textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 14),
              child: Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final (label, value, color) in counts)
                    Container(
                      width: (MediaQuery.of(context).size.width - 48) / 3,
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
                      decoration: BoxDecoration(
                        color: scheme.surface,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: scheme.outlineVariant),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '$value',
                            style: theme.textTheme.titleLarge?.copyWith(
                              fontWeight: FontWeight.w700,
                              color: color,
                            ),
                          ),
                          Text(
                            label,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: theme.textTheme.labelSmall?.copyWith(color: scheme.onSurfaceVariant),
                          ),
                        ],
                      ),
                    ),
                ],
              ),
            ),
            chips([for (final entry in _statuses.entries) (entry.key, entry.value)], _status, (value) {
              setState(() => _status = value);
              _load();
            }),
            const SizedBox(height: 12),
            if (_failed)
              ListTile(
                title: const Text(Strings.recordsNeedNetwork),
                trailing: TextButton(onPressed: _load, child: const Text(Strings.retry)),
              )
            else if (_loading && _items.isEmpty)
              const Padding(
                padding: EdgeInsets.all(32),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_items.isEmpty)
              const ListTile(title: Text(Strings.noRecords)),
            for (final item in _items)
              _RecordCard(
                item: item,
                photo: item.photoId == null ? null : _photo(item.photoId!),
                onTap: () => _details(item),
              ),
            if (_items.length < _total)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 0),
                child: OutlinedButton(
                  onPressed: _loading ? null : () => _load(more: true),
                  style: OutlinedButton.styleFrom(
                    minimumSize: const Size.fromHeight(46),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                  child: const Text(Strings.showMore),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// The member's photo when there is one, her initials until it loads or when there is none.
class _MemberPhoto extends StatelessWidget {
  const _MemberPhoto({required this.name, required this.photo, this.size = 52});

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

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.status, required this.label});

  final String status;
  final String label;

  @override
  Widget build(BuildContext context) {
    final tone = _tone(status);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: tone.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(label, style: TextStyle(color: tone, fontWeight: FontWeight.w700, fontSize: 12.5)),
    );
  }
}

class _RecordCard extends StatelessWidget {
  const _RecordCard({required this.item, required this.photo, required this.onTap});

  final ApplicationSummary item;
  final Future<Uint8List?>? photo;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final muted = theme.textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant);
    final when = item.submittedAt != null
        ? '${Strings.sentOn} ${_date(item.submittedAt!)}'
        : item.createdAt != null
        ? '${Strings.startedOn} ${_date(item.createdAt!)}'
        : '';

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
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
                _MemberPhoto(name: item.applicantName, photo: photo),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        item.applicantName.isEmpty ? Strings.untitled : item.applicantName,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        [
                          if (item.formNumber.isNotEmpty) item.formNumber,
                          '${Strings.mpp} ${item.mppCode}',
                        ].join(' · '),
                        style: muted,
                      ),
                      if (item.aadhaarLast4.isNotEmpty || item.mobile.isNotEmpty)
                        Text(
                          [
                            if (item.aadhaarLast4.isNotEmpty) 'Aadhaar XXXX ${item.aadhaarLast4}',
                            if (item.mobile.isNotEmpty) item.mobile,
                          ].join(' · '),
                          style: muted,
                        ),
                      if (when.isNotEmpty) Text(when, style: muted),
                      const SizedBox(height: 8),
                      _StatusChip(status: item.status, label: item.statusLabel),
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

/// One stage of the approval, as the facilitator needs to know it.
class _Stage {
  const _Stage(this.label, this.state, this.by, this.at, this.since, this.reason);

  factory _Stage.fromJson(Map<String, dynamic> json) => _Stage(
    '${json['label'] ?? ''}',
    '${json['state'] ?? 'waiting'}',
    '${json['by'] ?? ''}',
    DateTime.tryParse('${json['at'] ?? ''}')?.toLocal(),
    DateTime.tryParse('${json['since'] ?? ''}')?.toLocal(),
    '${json['reason'] ?? ''}',
  );

  final String label;
  final String state;
  final String by;
  final DateTime? at;
  final DateTime? since;
  final String reason;
}

/// A form's details and where it stands at each stage; drafts and returned forms can be edited.
class _RecordSheet extends StatefulWidget {
  const _RecordSheet({required this.item, required this.api, required this.photo, required this.canEdit});

  final ApplicationSummary item;
  final OnboardingApi api;
  final Future<Uint8List?>? photo;
  final bool canEdit;

  @override
  State<_RecordSheet> createState() => _RecordSheetState();
}

class _RecordSheetState extends State<_RecordSheet> {
  late final Future<List<_Stage>> _stages = _loadStages();

  Future<List<_Stage>> _loadStages() async {
    if (widget.item.status == 'draft') return const [];
    try {
      final detail = await widget.api.fetchApplication(widget.item.id);
      return [
        for (final stage in (detail['stages'] as List? ?? const []).cast<Map<String, dynamic>>())
          _Stage.fromJson(stage),
      ];
    } on Exception {
      return const [];
    }
  }

  Widget _row(String label, String value) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 110,
            child: Text(label, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
          ),
          Expanded(child: Text(value, style: const TextStyle(fontWeight: FontWeight.w600))),
        ],
      ),
    );
  }

  Widget _stageTile(_Stage stage, bool last) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final (icon, color, text) = switch (stage.state) {
      'approved' => (
        Icons.check_circle,
        Colors.green.shade600,
        [
          Strings.stageApproved,
          if (stage.by.isNotEmpty) stage.by,
          if (stage.at != null) _date(stage.at!),
        ].join(' · '),
      ),
      'rejected' => (
        Icons.cancel,
        Colors.red.shade600,
        [
          Strings.stageReturned,
          if (stage.at != null) _date(stage.at!),
          if (stage.reason.isNotEmpty) stage.reason,
        ].join(' · '),
      ),
      'pending' => (
        Icons.hourglass_top_rounded,
        Colors.orange.shade700,
        stage.since == null
            ? Strings.stagePending
            : '${Strings.stagePending} · ${DateTime.now().difference(stage.since!).inDays} ${Strings.days}',
      ),
      _ => (Icons.radio_button_unchecked, scheme.outline, Strings.stageNotYet),
    };
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Column(
            children: [
              Icon(icon, color: color, size: 22),
              if (!last) Expanded(child: Container(width: 2, color: scheme.outlineVariant)),
            ],
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(bottom: 14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(stage.label, style: const TextStyle(fontWeight: FontWeight.w700)),
                  const SizedBox(height: 2),
                  Text(text, style: theme.textTheme.bodySmall?.copyWith(color: color)),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final item = widget.item;
    final theme = Theme.of(context);
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                _MemberPhoto(name: item.applicantName, photo: widget.photo, size: 64),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        item.applicantName.isEmpty ? Strings.untitled : item.applicantName,
                        style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
                      ),
                      const SizedBox(height: 6),
                      _StatusChip(status: item.status, label: item.statusLabel),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            if (item.formNumber.isNotEmpty) _row(Strings.formNumber, item.formNumber),
            _row(Strings.mpp, '${item.mppCode} ${item.mppName}'.trim()),
            if (item.aadhaarLast4.isNotEmpty) _row(Strings.aadhaarNumber, 'XXXX XXXX ${item.aadhaarLast4}'),
            if (item.mobile.isNotEmpty) _row(Strings.mobileLabel, item.mobile),
            if (item.createdAt != null) _row(Strings.startedOn, _date(item.createdAt!)),
            if (item.submittedAt != null) _row(Strings.sentOn, _date(item.submittedAt!)),
            if (item.status != 'draft') ...[
              const SizedBox(height: 12),
              Text(Strings.approvals, style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
              const SizedBox(height: 10),
              FutureBuilder<List<_Stage>>(
                future: _stages,
                builder: (context, snapshot) {
                  if (snapshot.connectionState != ConnectionState.done) {
                    return const Padding(
                      padding: EdgeInsets.all(12),
                      child: Center(child: CircularProgressIndicator()),
                    );
                  }
                  final stages = snapshot.data ?? const [];
                  if (stages.isEmpty) return const Text(Strings.recordsNeedNetwork);
                  return Column(
                    children: [
                      for (final (index, stage) in stages.indexed) _stageTile(stage, index == stages.length - 1),
                    ],
                  );
                },
              ),
            ],
            if (widget.canEdit) ...[
              const SizedBox(height: 12),
              FilledButton.icon(
                style: FilledButton.styleFrom(
                  minimumSize: const Size.fromHeight(50),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
                onPressed: () => Navigator.pop(context, true),
                icon: const Icon(Icons.edit_outlined),
                label: Text(item.status == 'rejected' ? Strings.correctForm : Strings.editForm),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
