import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../api/api_client.dart';
import '../api/onboarding_api.dart';
import '../config.dart';
import '../models/draft.dart';
import '../models/form_schema.dart';
import '../storage/draft_store.dart';
import '../sync/bank_lookup.dart';
import '../sync/draft_controller.dart';
import 'device_services.dart';
import 'my_records.dart';
import 'strings.dart';
import 'wizard.dart';

/// The package's one entry point. A host app pushes this as an ordinary screen.
class MemberOnboardingScreen extends StatefulWidget {
  const MemberOnboardingScreen({
    required this.config,
    this.store,
    this.api,
    this.device = const DeviceServices(),
    super.key,
  });

  final MemberOnboardingConfig config;
  final DraftStore? store;
  final OnboardingApi? api;
  final DeviceServices device;

  @override
  State<MemberOnboardingScreen> createState() => _MemberOnboardingScreenState();
}

class _MemberOnboardingScreenState extends State<MemberOnboardingScreen> {
  late final DraftStore _store = widget.store ?? SecureDraftStore();
  late final OnboardingApi _api = widget.api ?? OnboardingApi(ApiClient(widget.config));
  late final BankLookup _banks = BankLookup(api: _api, store: _store, device: widget.device);

  static const _formCacheKey = 'form';
  static const _mppCacheKey = 'mpps';

  FormSchema? _schema;
  List<MppSummary> _mpps = const [];
  List<Draft> _drafts = const [];
  List<ApplicationSummary> _rejected = const [];
  bool _offline = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _useForm(Map<String, dynamic> json) => _schema = FormSchema.fromJson(json);

  void _useMpps(List<dynamic> json) =>
      _mpps = json.cast<Map<String, dynamic>>().map(MppSummary.fromJson).toList();

  /// The last known copy first, so the screen works at once and without a network.
  Future<void> _loadCached() async {
    final form = await _store.readCache(_formCacheKey);
    final mpps = await _store.readCache(_mppCacheKey);
    final drafts = await _store.all();
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
      await _store.writeCache(_formCacheKey, jsonEncode(form));
      await _store.writeCache(_mppCacheKey, jsonEncode(mpps));
      if (!mounted) return;
      setState(() {
        _useForm(form);
        _useMpps(mpps);
        _rejected = rejected;
        _offline = false;
      });
      await _sendPending();
    } on OfflineException {
      if (mounted) setState(() => _offline = true);
    } on ApiException {
      if (mounted) setState(() => _offline = true);
    }
  }

  /// Forms finished in the field go up here, without being reopened.
  Future<void> _sendPending() async {
    final pending = (await _store.all()).where((draft) => draft.needsSync);
    for (final draft in pending) {
      final controller = DraftController(draft: draft, api: _api, store: _store);
      await controller.sync();
      controller.dispose();
    }
    final drafts = await _store.all();
    if (mounted) setState(() => _drafts = drafts);
  }

  Future<void> _open(Draft draft) async {
    final schema = _schema;
    if (schema == null) return;
    final controller = DraftController(draft: draft, api: _api, store: _store);
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
    if (mpp == null) return;

    final draft = Draft(
      clientId: const Uuid().v4(),
      mppId: mpp.id,
      mppLabel: '${mpp.code} ${mpp.name}',
    );
    await _store.save(draft);
    await _open(draft);
  }

  Future<void> _openRejected(ApplicationSummary item) async {
    await _open(Draft.fromServer(await _api.fetchApplication(item.id)));
  }

  @override
  Widget build(BuildContext context) {
    final primary = widget.config.primaryColor;
    return Theme(
      data: ThemeData(colorSchemeSeed: primary, useMaterial3: true),
      child: Scaffold(
        appBar: AppBar(
          title: const Text(Strings.title),
          actions: [
            IconButton(
              tooltip: Strings.myRecords,
              icon: const Icon(Icons.bar_chart),
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => MyRecordsScreen(api: _api, onOpen: _openRejected),
                ),
              ),
            ),
          ],
        ),
        floatingActionButton: FloatingActionButton.extended(
          shape: const RoundedRectangleBorder(),
          onPressed: _schema == null ? null : _startNew,
          icon: const Icon(Icons.add),
          label: const Text(Strings.newForm),
        ),
        body: RefreshIndicator(
          onRefresh: _load,
          child: ListView(
            padding: const EdgeInsets.only(bottom: 96),
            children: [
              if (_offline)
                ListTile(
                  title: Text(
                    _schema == null ? Strings.firstRunNeedsNetwork : Strings.offlineReady,
                  ),
                  trailing: TextButton(onPressed: _load, child: const Text(Strings.retry)),
                ),
              if (_rejected.isNotEmpty) ...[
                const ListTile(dense: true, title: Text(Strings.sentBack)),
                for (final item in _rejected)
                  ListTile(
                    leading: const Icon(Icons.error_outline, color: Colors.red),
                    title: Text(item.applicantName.isEmpty ? Strings.untitled : item.applicantName),
                    subtitle: Text(item.mppCode),
                    onTap: () => _openRejected(item),
                  ),
              ],
              const ListTile(dense: true, title: Text(Strings.myDrafts)),
              if (_drafts.isEmpty) const ListTile(title: Text(Strings.nothingHere)),
              for (final draft in _drafts)
                ListTile(
                  title: Text(draft.applicantName.isEmpty ? Strings.untitled : draft.applicantName),
                  subtitle: Text(draft.mppLabel),
                  trailing: draft.needsSync ? const Icon(Icons.cloud_upload_outlined) : null,
                  onTap: () => _open(draft),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
