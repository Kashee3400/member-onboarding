import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../api/api_client.dart';
import '../api/onboarding_api.dart';
import '../config.dart';
import '../models/draft.dart';
import '../models/form_schema.dart';
import '../storage/document_vault.dart';
import '../storage/draft_store.dart';
import '../sync/bank_lookup.dart';
import '../sync/draft_controller.dart';
import 'device_services.dart';
import 'my_records.dart';
import 'record_card.dart';
import 'strings.dart';
import 'wizard.dart';

/// The package's one entry point. A host app pushes this as an ordinary screen.
class MemberOnboardingScreen extends StatefulWidget {
  const MemberOnboardingScreen({
    required this.config,
    this.store,
    this.api,
    this.device = const DeviceServices(),
    this.vault,
    this.openApplicationId,
    super.key,
  });

  /// A form to open at once, such as the one a push notification was about.
  final String? openApplicationId;

  final MemberOnboardingConfig config;
  final DraftStore? store;
  final OnboardingApi? api;
  final DeviceServices device;

  /// Where photos wait on the phone; the encrypted vault unless a test gives another.
  final DocumentVault? vault;

  @override
  State<MemberOnboardingScreen> createState() => _MemberOnboardingScreenState();
}

class _MemberOnboardingScreenState extends State<MemberOnboardingScreen> {
  late final DraftStore _store = widget.store ?? SecureDraftStore();
  late final OnboardingApi _api = widget.api ?? OnboardingApi(ApiClient(widget.config));
  late final DocumentVault _vault = widget.vault ?? SecureDocumentVault();
  late final BankLookup _banks = BankLookup(api: _api, store: _store, device: widget.device);

  static const _formCacheKey = 'form';
  static const _mppCacheKey = 'mpps';

  FormSchema? _schema;
  List<MppSummary> _mpps = const [];
  List<Draft> _drafts = const [];
  List<ApplicationSummary> _rejected = const [];

  /// Drafts on the server that are not on this phone: started on another, or before a reinstall.
  List<ApplicationSummary> _serverDrafts = const [];
  RecordSummary? _month;
  bool _offline = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _useForm(Map<String, dynamic> json) => _schema = FormSchema.fromJson(json);

  /// The phone's store keeps no order, so the list would shuffle on every visit.
  static List<Draft> _newestFirst(List<Draft> drafts) {
    final never = DateTime.fromMillisecondsSinceEpoch(0);
    return drafts..sort((a, b) => (b.updatedAt ?? never).compareTo(a.updatedAt ?? never));
  }

  void _useMpps(List<dynamic> json) =>
      _mpps = json.cast<Map<String, dynamic>>().map(MppSummary.fromJson).toList();

  /// The last known copy first, so the screen works at once and without a network.
  Future<void> _loadCached() async {
    final form = await _store.readCache(_formCacheKey);
    final mpps = await _store.readCache(_mppCacheKey);
    final drafts = _newestFirst(await _store.all());
    if (!mounted) return;
    setState(() {
      _drafts = drafts;
      if (form != null) _useForm(jsonDecode(form) as Map<String, dynamic>);
      if (mpps != null) _useMpps(jsonDecode(mpps) as List<dynamic>);
    });
  }

  Future<void> _load() async {
    await _loadCached();

    try {
      final form = await _api.fetchFormJson();
      final mpps = await _api.fetchMppsJson();
      final rejected = await _api.fetchApplications(status: 'rejected');
      final serverDrafts = await _api.fetchApplications(status: 'draft');
      await _store.writeCache(_formCacheKey, jsonEncode(form));
      await _store.writeCache(_mppCacheKey, jsonEncode(mpps));
      if (!mounted) return;
      setState(() {
        _useForm(form);
        _useMpps(mpps);
        _rejected = rejected;
        _serverDrafts = serverDrafts;
        _offline = false;
      });
      unawaited(_registerPush());
      if (!await _openRequested()) _announceSentBack();
      await _sendPending();
      await _loadMonth();
    } on OfflineException {
      if (mounted) setState(() => _offline = true);
    } on ApiException {
      if (mounted) setState(() => _offline = true);
    }
  }

  final Map<String, Future<Uint8List?>> _photos = {};

  Future<Uint8List?> _serverPhoto(String id) => _photos.putIfAbsent(id, () async {
    try {
      return Uint8List.fromList(await _api.fetchDocumentFile(id));
    } on Exception {
      return null;
    }
  });

  /// A draft's photo: still in the vault, or already on the server.
  Future<Uint8List?>? _draftPhoto(Draft draft) {
    final kept = draft.pendingDocuments['photo'];
    if (kept != null) {
      return _photos.putIfAbsent('vault:$kept', () async {
        try {
          return await _vault.read(kept);
        } on Exception {
          return null;
        }
      });
    }
    final id = draft.serverId;
    if (id == null || !draft.uploadedDocuments.contains('photo')) return null;
    return _photos.putIfAbsent('form:$id', () async {
      try {
        final photo = (await _api.fetchDocumentIds(id))['photo'];
        return photo == null ? null : Uint8List.fromList(await _api.fetchDocumentFile(photo));
      } on Exception {
        return null;
      }
    });
  }

  List<String> _draftLines(Draft draft) {
    final aadhaar = draft.pendingAadhaar != null && draft.pendingAadhaar!.length >= 4
        ? draft.pendingAadhaar!.substring(draft.pendingAadhaar!.length - 4)
        : draft.aadhaarLast4;
    final mobile = '${draft.section('address')['mobile'] ?? ''}';
    return [
      draft.mppLabel,
      [if (aadhaar.isNotEmpty) 'Aadhaar XXXX $aadhaar', if (mobile.isNotEmpty) mobile].join(' · '),
      if (draft.updatedAt != null) '${Strings.savedOn} ${formatDate(draft.updatedAt!)}',
    ];
  }

  bool _announced = false;

  /// Server drafts this phone does not hold, so none shows twice.
  List<ApplicationSummary> get _onlyOnServer {
    final here = {for (final draft in _drafts) ?draft.serverId};
    return [for (final item in _serverDrafts) if (!here.contains(item.id)) item];
  }
  bool _pushRegistered = false;
  bool _requestOpened = false;

  /// Once per visit, so the server knows this phone; a failure only means no push.
  Future<void> _registerPush() async {
    final provider = widget.config.pushTokenProvider;
    if (_pushRegistered || provider == null) return;
    _pushRegistered = true;
    try {
      final token = await provider();
      if (token != null && token.isNotEmpty) {
        await _api.registerPushDevice(token, Platform.isIOS ? 'ios' : 'android');
      }
    } on Exception {
      _pushRegistered = false;
    }
  }

  /// The form a notification was about, opened straight away. True when one was.
  Future<bool> _openRequested() async {
    final id = widget.openApplicationId;
    if (_requestOpened || id == null) return false;
    _requestOpened = true;
    for (final item in _rejected) {
      if (item.id == id) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) _openRejected(item);
        });
        return true;
      }
    }
    return false;
  }

  /// Once per visit: a form sent back waits on the facilitator, so it is said out loud.
  void _announceSentBack() {
    if (_announced || _rejected.isEmpty || !mounted) return;
    _announced = true;
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      final open = await showDialog<ApplicationSummary>(
        context: context,
        builder: (dialog) => AlertDialog(
          key: const ValueKey('sent_back.alert'),
          icon: Icon(Icons.assignment_return_rounded, color: Colors.red.shade600, size: 36),
          title: Text('${_rejected.length} ${Strings.sentBackAlertTitle}'),
          content: SizedBox(
            width: double.maxFinite,
            child: ListView(
              shrinkWrap: true,
              children: [
                const Padding(
                  padding: EdgeInsets.only(bottom: 8),
                  child: Text(Strings.sentBackAlertBody),
                ),
                for (final item in _rejected)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: MemberPhoto(
                      name: item.applicantName,
                      photo: item.photoId == null ? null : _serverPhoto(item.photoId!),
                      size: 40,
                    ),
                    title: Text(item.applicantName.isEmpty ? Strings.untitled : item.applicantName),
                    subtitle: Text(
                      [if (item.formNumber.isNotEmpty) item.formNumber, item.mppCode].join(' · '),
                    ),
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: () => Navigator.pop(dialog, item),
                  ),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dialog), child: const Text(Strings.later)),
          ],
        ),
      );
      if (open != null && mounted) await _openRejected(open);
    });
  }

  /// This month's counts, loaded on their own so a failure never hides the forms.
  Future<void> _loadMonth() async {
    final today = DateTime.now();
    try {
      final month = await _api.fetchSummary(from: DateTime(today.year, today.month), to: today);
      if (mounted) setState(() => _month = month);
    } on Exception {
      // The counts are a convenience; the forms below matter more.
    }
  }

  void _openRecords() => Navigator.of(context).push(
    MaterialPageRoute<void>(builder: (_) => MyRecordsScreen(api: _api, onOpen: _openRejected)),
  );

  /// Forms finished in the field go up here, without being reopened.
  Future<void> _sendPending() async {
    final pending = (await _store.all()).where((draft) => draft.needsSync);
    for (final draft in pending) {
      final controller = DraftController(draft: draft, api: _api, store: _store, vault: _vault);
      await controller.sync();
      controller.dispose();
    }
    final drafts = _newestFirst(await _store.all());
    if (mounted) setState(() => _drafts = drafts);
  }

  Future<void> _open(Draft draft) async {
    final schema = _schema;
    if (schema == null) return;
    final controller = DraftController(draft: draft, api: _api, store: _store, vault: _vault);
    await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => FormWizard(
          schema: schema,
          controller: controller,
          device: widget.device,
          findBranch: _banks.find,
        ),
      ),
    );
    await controller.sync();
    controller.dispose();
    await _load();
  }

  Future<void> _startNew() async {
    final mpp = await showModalBottomSheet<MppSummary>(
      context: context,
      shape: const RoundedRectangleBorder(),
      builder: (sheet) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            const ListTile(title: Text(Strings.chooseMpp)),
            for (final item in _mpps)
              ListTile(
                title: Text('${item.code} ${item.name}'),
                onTap: () => Navigator.pop(sheet, item),
              ),
          ],
        ),
      ),
    );
    if (mpp == null || !mounted) return;

    // Filled now, not on the first sync, so a form started offline shows it too.
    final place = {
      for (final spec in _schema!.section('address').fields)
        if (spec.locked && mpp.place[spec.key] != null) spec.key: mpp.place[spec.key]!,
    };
    final draft = Draft(
      clientId: const Uuid().v4(),
      mppId: mpp.id,
      mppLabel: '${mpp.code} ${mpp.name}',
      place: place,
      data: {
        if (place.isNotEmpty) 'address': {...place},
      },
    );
    await _store.save(draft);
    await _open(draft);
  }

  Future<void> _openRejected(ApplicationSummary item) async {
    for (final draft in await _store.all()) {
      if (draft.serverId == item.id) return _open(draft);
    }
    await _open(Draft.fromServer(await _api.fetchApplication(item.id)));
  }

  @override
  Widget build(BuildContext context) {
    final primary = widget.config.primaryColor;
    return Theme(
      data: ThemeData(colorSchemeSeed: primary, useMaterial3: true),
      child: Builder(
        builder: (context) {
          final scheme = Theme.of(context).colorScheme;
          final month = _month;
          return Scaffold(
            backgroundColor: scheme.surfaceContainerLowest,
            appBar: AppBar(
              title: const Text(Strings.title, style: TextStyle(fontWeight: FontWeight.w700)),
              backgroundColor: scheme.surfaceContainerLowest,
              surfaceTintColor: Colors.transparent,
              actions: [
                IconButton(
                  tooltip: Strings.myRecords,
                  icon: const Icon(Icons.insights_rounded),
                  onPressed: _openRecords,
                ),
              ],
            ),
            body: RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 32),
                children: [
                  if (_offline) ...[
                    _Banner(
                      text: _schema == null ? Strings.firstRunNeedsNetwork : Strings.offlineReady,
                      onRetry: _load,
                    ),
                    const SizedBox(height: 12),
                  ],
                  _StartCard(
                    mppCount: _mpps.length,
                    onStart: _schema == null ? null : _startNew,
                  ),
                  if (month != null) ...[
                    const SizedBox(height: 20),
                    _SectionTitle(Strings.thisMonth, onTap: _openRecords),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        _CountTile(label: Strings.sent, value: month.submitted, onTap: _openRecords),
                        const SizedBox(width: 8),
                        _CountTile(label: Strings.waiting, value: month.pending, onTap: _openRecords),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        _CountTile(
                          label: Strings.approved,
                          value: month.approved,
                          color: Colors.green.shade700,
                          onTap: _openRecords,
                        ),
                        const SizedBox(width: 8),
                        _CountTile(
                          label: Strings.returned,
                          value: month.rejected,
                          color: scheme.error,
                          onTap: _openRecords,
                        ),
                      ],
                    ),
                  ],
                  if (_rejected.isNotEmpty) ...[
                    const SizedBox(height: 20),
                    _SectionTitle(Strings.sentBack, count: _rejected.length),
                    const SizedBox(height: 8),
                    for (final item in _rejected)
                      RecordCard(
                        name: item.applicantName,
                        lines: recordLines(item),
                        status: item.status,
                        statusLabel: Strings.stageReturned,
                        statusIcon: Icons.assignment_return_rounded,
                        photo: item.photoId == null ? null : _serverPhoto(item.photoId!),
                        onTap: () => _openRejected(item),
                      ),
                  ],
                  const SizedBox(height: 20),
                  _SectionTitle(Strings.myDrafts, count: _drafts.length + _onlyOnServer.length),
                  const SizedBox(height: 8),
                  if (_drafts.isEmpty && _onlyOnServer.isEmpty)
                    const _Empty()
                  else
                    for (final draft in _drafts)
                      RecordCard(
                        name: draft.applicantName,
                        lines: _draftLines(draft),
                        status: 'draft',
                        statusLabel: draft.needsSync ? Strings.waitingUpload : Strings.draftStatus,
                        statusIcon: draft.needsSync ? Icons.cloud_upload_outlined : Icons.edit_note,
                        photo: _draftPhoto(draft),
                        onTap: () => _open(draft),
                      ),
                  for (final item in _onlyOnServer)
                    RecordCard(
                      name: item.applicantName,
                      lines: recordLines(item),
                      status: 'draft',
                      statusLabel: Strings.draftStatus,
                      statusIcon: Icons.edit_note,
                      photo: item.photoId == null ? null : _serverPhoto(item.photoId!),
                      onTap: () => _openRejected(item),
                    ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

class _Banner extends StatelessWidget {
  const _Banner({required this.text, required this.onRetry});

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
            Expanded(child: Text(text, style: TextStyle(color: scheme.onTertiaryContainer))),
            TextButton(onPressed: onRetry, child: const Text(Strings.retry)),
          ],
        ),
      ),
    );
  }
}

class _StartCard extends StatelessWidget {
  const _StartCard({required this.mppCount, required this.onStart});

  final int mppCount;
  final VoidCallback? onStart;

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
          colors: [scheme.primary, Color.lerp(scheme.primary, scheme.tertiary, 0.55)!],
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
                child: Icon(Icons.person_add_alt_1_rounded, color: scheme.onPrimary),
              ),
              const Spacer(),
              if (mppCount > 0)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: scheme.onPrimary.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    '$mppCount ${Strings.mppsAssigned}',
                    style: theme.textTheme.labelSmall?.copyWith(color: scheme.onPrimary),
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
          FilledButton.icon(
            style: FilledButton.styleFrom(
              backgroundColor: scheme.onPrimary,
              foregroundColor: scheme.primary,
              minimumSize: const Size.fromHeight(48),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
            onPressed: onStart,
            icon: const Icon(Icons.add_rounded),
            label: const Text(Strings.newForm, style: TextStyle(fontWeight: FontWeight.w700)),
          ),
        ],
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.text, {this.count, this.onTap});

  final String text;
  final int? count;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    return Row(
      children: [
        Text(text, style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
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
              style: theme.textTheme.labelSmall?.copyWith(color: scheme.onSecondaryContainer),
            ),
          ),
        ],
        const Spacer(),
        if (onTap != null)
          InkWell(
            onTap: onTap,
            child: Icon(Icons.chevron_right_rounded, color: scheme.onSurfaceVariant),
          ),
      ],
    );
  }
}

class _CountTile extends StatelessWidget {
  const _CountTile({required this.label, required this.value, required this.onTap, this.color});

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
                    style: theme.textTheme.labelMedium?.copyWith(color: scheme.onSurfaceVariant),
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

class _Empty extends StatelessWidget {
  const _Empty();

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
            style: theme.textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
          ),
        ],
      ),
    );
  }
}
