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

  String _date(DateTime date) =>
      '${date.day.toString().padLeft(2, '0')}-${date.month.toString().padLeft(2, '0')}-${date.year}';

  Color _tone(String status) => switch (status) {
    'approved' => Colors.green.shade700,
    'rejected' => Colors.red.shade700,
    'draft' => Colors.grey.shade700,
    _ => Colors.orange.shade800,
  };

  @override
  Widget build(BuildContext context) {
    const labels = {
      _Range.today: Strings.today,
      _Range.yesterday: Strings.yesterday,
      _Range.week: Strings.thisWeek,
      _Range.month: Strings.thisMonth,
      _Range.custom: Strings.pickDates,
    };
    final counts = [
      (Strings.started, _summary.started),
      (Strings.sent, _summary.submitted),
      (Strings.waiting, _summary.pending),
      (Strings.approved, _summary.approved),
      (Strings.returned, _summary.rejected),
    ];

    return Scaffold(
      appBar: AppBar(title: const Text(Strings.myRecords)),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.only(bottom: 32),
          children: [
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.fromLTRB(12, 12, 12, 4),
              child: Row(
                children: [
                  for (final range in _Range.values)
                    Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: ChoiceChip(
                        label: Text(labels[range]!),
                        selected: _range == range,
                        shape: const RoundedRectangleBorder(),
                        onSelected: (_) => _choose(range),
                      ),
                    ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Text(
                _dates.start == _dates.end
                    ? _date(_dates.start)
                    : '${_date(_dates.start)} – ${_date(_dates.end)}',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(12),
              child: Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final (label, value) in counts)
                    Container(
                      width: 104,
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(border: Border.all(color: Colors.black12)),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(label, style: Theme.of(context).textTheme.bodySmall),
                          Text('$value', style: Theme.of(context).textTheme.titleLarge),
                        ],
                      ),
                    ),
                ],
              ),
            ),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Row(
                children: [
                  for (final entry in _statuses.entries)
                    Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: FilterChip(
                        label: Text(entry.value),
                        selected: _status == entry.key,
                        shape: const RoundedRectangleBorder(),
                        onSelected: (_) {
                          setState(() => _status = entry.key);
                          _load();
                        },
                      ),
                    ),
                ],
              ),
            ),
            const Divider(),
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
              ListTile(
                title: Text(item.applicantName.isEmpty ? Strings.untitled : item.applicantName),
                subtitle: Text(
                  [
                    if (item.formNumber.isNotEmpty) item.formNumber,
                    item.mppCode,
                    if (item.createdAt != null) '${Strings.startedOn} ${_date(item.createdAt!)}',
                    if (item.submittedAt != null) '${Strings.sentOn} ${_date(item.submittedAt!)}',
                  ].join(' · '),
                ),
                trailing: Text(
                  item.statusLabel,
                  style: TextStyle(color: _tone(item.status), fontWeight: FontWeight.w600),
                ),
                onTap:
                    widget.onOpen != null && (item.status == 'draft' || item.status == 'rejected')
                    ? () async {
                        await widget.onOpen!(item);
                        await _load();
                      }
                    : null,
              ),
            if (_items.length < _total)
              Padding(
                padding: const EdgeInsets.all(12),
                child: OutlinedButton(
                  onPressed: _loading ? null : () => _load(more: true),
                  style: OutlinedButton.styleFrom(shape: const RoundedRectangleBorder()),
                  child: const Text(Strings.showMore),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
