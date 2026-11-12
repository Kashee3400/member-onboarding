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
import 'onboarding_home_widgets.dart';
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
    this.onSignOut,
    super.key,
  });

  /// A form to open at once, such as the one a push notification was about.
  final String? openApplicationId;

  /// Shows a sign-out button, for an app whose only screen this is. A host app
  /// with its own menu leaves it null.
  final VoidCallback? onSignOut;

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
        builder: (dialog) => SentBackDialog(
          rejected: _rejected,
          photoLoader: _serverPhoto,
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

  Future<bool> _confirmDelete(String name) async =>
      await showDialog<bool>(
        context: context,
        builder: (dialog) => AlertDialog(
          key: const ValueKey('draft.delete_confirm'),
          icon: Icon(Icons.delete_outline_rounded, color: Theme.of(dialog).colorScheme.error),
          title: const Text(Strings.deleteDraftTitle),
          content: Text(
            name.isEmpty ? Strings.deleteDraftBody : '$name\n\n${Strings.deleteDraftBody}',
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dialog, false), child: const Text(Strings.cancel)),
            FilledButton(
              style: FilledButton.styleFrom(backgroundColor: Theme.of(dialog).colorScheme.error),
              onPressed: () => Navigator.pop(dialog, true),
              child: const Text(Strings.delete),
            ),
          ],
        ),
      ) ??
      false;

  /// Throws the draft away on the server first, then on the phone, so it cannot come back.
  Future<void> _deleteDraft({Draft? draft, ApplicationSummary? item}) async {
    final name = draft?.applicantName ?? item?.applicantName ?? '';
    if (!await _confirmDelete(name) || !mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    final serverId = draft?.serverId ?? item?.id;
    try {
      if (serverId != null) await _api.discardApplication(serverId);
    } on OfflineException {
      messenger.showSnackBar(const SnackBar(content: Text(Strings.deleteNeedsInternet)));
      return;
    } on ApiException catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.message)));
      return;
    }
    final local = [
      for (final saved in await _store.all())
        if (saved.clientId == draft?.clientId || (serverId != null && saved.serverId == serverId)) saved,
    ];
    for (final saved in local) {
      await _store.delete(saved.clientId);
      await _vault.removeAll(saved.clientId);
    }
    if (!mounted) return;
    setState(() {
      _drafts = [for (final d in _drafts) if (!local.any((s) => s.clientId == d.clientId)) d];
      _serverDrafts = [for (final s in _serverDrafts) if (s.id != serverId) s];
    });
    messenger.showSnackBar(const SnackBar(content: Text(Strings.draftDeleted)));
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

  /// The MPP picked on the start card. With only one, it is picked already.
  String? _chosenMppId;

  MppSummary? get _chosenMpp {
    if (_mpps.length == 1) return _mpps.single;
    for (final mpp in _mpps) {
      if (mpp.id == _chosenMppId) return mpp;
    }
    return null;
  }

  Future<void> _startNew() async {
    final mpp = _chosenMpp;
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
      if (draft.serverId == item.id) return _open(await _withServerDocuments(draft));
    }
    await _open(await _withServerDocuments(Draft.fromServer(await _api.fetchApplication(item.id))));
  }

  /// A form already on the server keeps its photos there: the phone deleted its own
  /// copies once they were sent. They count as taken and show from the server, so a
  /// form sent back for one photo does not ask for all of them again. A photo the
  /// reviewer marked is left out on purpose: that one is to be taken again.
  Future<Draft> _withServerDocuments(Draft draft) async {
    final id = draft.serverId;
    if (id == null) return draft;
    try {
      final onServer = await _api.fetchDocumentIds(id);
      draft.uploadedDocuments
        ..clear()
        ..addAll(
          onServer.keys.where(
            (type) =>
                !draft.pendingDocuments.containsKey(type) &&
                !draft.rejectedFields.contains('documents.$type'),
          ),
        );
      await _store.save(draft);
    } on Object {
      // Offline: the form opens as the phone last knew it.
    }
    return draft;
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
                if (widget.onSignOut case final signOut?)
                  IconButton(
                    tooltip: Strings.signOut,
                    icon: const Icon(Icons.logout_rounded),
                    onPressed: signOut,
                  ),
              ],
            ),
            body: RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 32),
                children: [
                  if (_offline) ...[
                    OfflineBanner(
                      text: _schema == null ? Strings.firstRunNeedsNetwork : Strings.offlineReady,
                      onRetry: _load,
                    ),
                    const SizedBox(height: 12),
                  ],
                  StartCard(
                    mpps: _mpps,
                    chosen: _chosenMpp,
                    onChoose: (mpp) => setState(() => _chosenMppId = mpp?.id),
                    onStart: _schema == null || _chosenMpp == null ? null : _startNew,
                  ),
                  if (month != null) ...[
                    const SizedBox(height: 20),
                    HomeSectionTitle(Strings.thisMonth, onTap: _openRecords),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        CountTile(label: Strings.totalForms, value: month.total, onTap: _openRecords),
                        const SizedBox(width: 8),
                        CountTile(label: Strings.waiting, value: month.underReview, onTap: _openRecords),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        CountTile(
                          label: Strings.approved,
                          value: month.becameMembers,
                          color: Colors.green.shade700,
                          onTap: _openRecords,
                        ),
                        const SizedBox(width: 8),
                        CountTile(
                          label: Strings.returned,
                          value: month.sentBack,
                          color: scheme.error,
                          onTap: _openRecords,
                        ),
                      ],
                    ),
                  ],
                  if (_rejected.isNotEmpty) ...[
                    const SizedBox(height: 20),
                    HomeSectionTitle(Strings.sentBack, count: _rejected.length),
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
                  HomeSectionTitle(Strings.myDrafts, count: _drafts.length + _onlyOnServer.length),
                  const SizedBox(height: 8),
                  if (_drafts.isEmpty && _onlyOnServer.isEmpty)
                    const EmptyDraftsTile()
                  else
                    for (final draft in _drafts)
                      RecordCard(
                        name: draft.applicantName,
                        lines: _draftLines(draft),
                        status: 'draft',
                        statusLabel: draft.needsSync ? Strings.waitingUpload : Strings.draftStatus,
                        statusIcon: draft.needsSync ? Icons.cloud_upload_outlined : Icons.edit_note,
                        photo: _draftPhoto(draft),
                        onTap: () async => _open(await _withServerDocuments(draft)),
                        onDelete: draft.status == 'draft' ? () => _deleteDraft(draft: draft) : null,
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
                      onDelete: () => _deleteDraft(item: item),
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
