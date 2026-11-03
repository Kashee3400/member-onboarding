import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../aadhaar/aadhaar_qr.dart';
import '../models/form_schema.dart';
import '../sync/draft_controller.dart';
import '../validation/form_checks.dart';
import 'contact_verify.dart';
import 'device_services.dart';
import 'fields.dart';
import 'form_widgets.dart';
import 'signature_pad.dart';
import 'strings.dart';

/// One short screen at a time, because the long paper form was the real problem.
class FormWizard extends StatefulWidget {
  const FormWizard({
    required this.schema,
    required this.controller,
    this.device = const DeviceServices(),
    this.findBranch,
    super.key,
  });

  final FormSchema schema;
  final DraftController controller;
  final DeviceServices device;

  /// Bank and branch for an IFSC, from the bank master; the online lookup when absent.
  final Future<(String, String)?> Function(String ifsc)? findBranch;

  @override
  State<FormWizard> createState() => _FormWizardState();
}

class _Step {
  const _Step(this.key, this.title, this.icon);

  final String key;
  final String title;
  final IconData icon;
}

enum _Lookup { idle, looking, found, notFound }

class _FormWizardState extends State<FormWizard> {
  int _index = 0;

  DraftController get _form => widget.controller;
  FormSchema get _schema => widget.schema;
  late final FormChecks _checks = FormChecks(widget.schema);

  /// Typed numbers the phone would not pass on, kept so the review step can list them.
  String? _aadhaarProblem;
  String? _accountProblem;

  /// Text boxes that are checked as soon as the value has all its characters.
  static const _fullLength = {'address.mobile': 10, 'address.pincode': 6, 'bank.ifsc': 11};

  // Documents first: they are taken in one go, and the rest is typed from them.
  // The member signs last, on the review, once the whole form has been read to them.
  late final List<_Step> _steps = [
    const _Step('documents', Strings.documents, Icons.photo_library_outlined),
    _Step('applicant', _schema.section('applicant').title, Icons.person_outline),
    _Step('address', _schema.section('address').title, Icons.home_outlined),
    _Step('animals', _schema.section('animals').title, Icons.pets_outlined),
    _Step('bank', _schema.section('bank').title, Icons.account_balance_outlined),
    const _Step('family', Strings.family, Icons.groups_outlined),
    _Step('nominee', _schema.section('nominee').title, Icons.volunteer_activism_outlined),
    _Step('declaration', _schema.section('declaration').title, Icons.fact_check_outlined),
    const _Step('review', Strings.review, Icons.draw_outlined),
  ];

  /// Which step each part of the form is filled on.
  static const _sectionStep = {
    'documents': 0,
    'applicant': 1,
    'address': 2,
    'location': 2,
    'animals': 3,
    'bank': 4,
    'family': 5,
    'nominee': 6,
    'declaration': 7,
  };
  static const _reviewIndex = 8;
  static const _signatures = {'member_signature', 'member_thumbprint'};

  static const _photos = [
    ('photo', Strings.photo, Strings.photoHint, Icons.face_outlined),
    ('aadhaar_front', Strings.aadhaarFront, Strings.cardHint, Icons.badge_outlined),
    ('aadhaar_back', Strings.aadhaarBack, Strings.cardHint, Icons.badge_outlined),
    ('passbook', Strings.passbook, Strings.passbookHint, Icons.menu_book_outlined),
  ];

  static const _documentLabels = {
    'photo': Strings.photo,
    'aadhaar_front': Strings.aadhaarFront,
    'aadhaar_back': Strings.aadhaarBack,
    'passbook': Strings.passbook,
    'member_signature': Strings.memberSignature,
    'member_thumbprint': Strings.thumbprint,
  };

  /// What was edited on this screen, to show which returned fields were corrected.
  final Set<String> _changed = {};

  /// Fields the Aadhaar QR filled, marked until someone changes them.
  final Set<String> _fromQr = {};

  /// Photos kept although they looked too dark or blurred.
  final Map<String, PhotoProblem> _doubtful = {};

  _Lookup _lookup = _Lookup.idle;

  int _stepOf(String path) {
    final parts = path.split('.');
    if (parts.first == 'documents' && parts.length > 1 && _signatures.contains(parts[1])) {
      return _reviewIndex;
    }
    return _sectionStep[parts.first] ?? 1;
  }

  @override
  void initState() {
    super.initState();
    _form.addListener(_refresh);
    // A returned form opens where the first correction is.
    final rejected = _form.draft.rejectedFields;
    if (rejected.isNotEmpty) {
      _index = rejected.map(_stepOf).reduce((a, b) => a < b ? a : b);
    }
  }

  @override
  void dispose() {
    _form.removeListener(_refresh);
    super.dispose();
  }

  void _refresh() {
    if (mounted) setState(() {});
  }

  void _go(int step) => setState(() => _index = step);

  String? _errorFor(String path) {
    final server = _form.serverErrors[path];
    if (server != null) return server;
    return _returnedBecause(path);
  }

  /// For a field sent back: the reviewer's own reason, or the general words when none was given.
  String? _returnedBecause(String path) {
    final draft = _form.draft;
    if (!draft.rejectedFields.contains(path)) return null;
    final note = draft.noteFor(path);
    return note == null ? Strings.rejectedBecause : '${Strings.rejectedBecause}: $note';
  }

  /// The phone's own check of a typed answer, judged with the rest of the form.
  String? Function(String) _checkOf(String section, String key) => (text) {
    final values = {..._form.draft.section(section), key: text};
    return _checks.field(section, key, {..._form.draft.data, section: values});
  };

  /// What the MPP fills for this field, which nobody types or changes here.
  String? _fromMpp(String section, FormFieldSpec spec) =>
      section == 'address' && spec.locked ? _form.draft.place[spec.key] : null;

  static int? _ageOf(Object? dateOfBirth) {
    final born = DateTime.tryParse('${dateOfBirth ?? ''}');
    return born == null ? null : ageOn(born, DateTime.now());
  }

  Widget _field(String section, FormFieldSpec spec, {ValueChanged<Object?>? onSaved}) {
    final path = '$section.${spec.key}';
    final fixed = _fromMpp(section, spec);
    if (fixed != null) {
      return LockedBox(key: ValueKey(path), label: spec.label, value: fixed);
    }
    final value = _form.draft.section(section)[spec.key];
    final error = _errorFor(path);
    void save(Object? next) {
      _changed.add(path);
      _fromQr.remove(path);
      _form.setValue(section, spec.key, next);
      onSaved?.call(next);
    }

    final box = switch (spec.type) {
      // A short list is quicker as chips than as a list to open.
      'choice' when spec.options.length <= 8 => ChipChoice(
        key: ValueKey(path),
        label: spec.label,
        value: value as String?,
        options: spec.options,
        retired: spec.retired,
        optional: !spec.required,
        error: error,
        onChanged: save,
      ),
      'choice' => ChoiceBox(
        key: ValueKey(path),
        label: spec.label,
        value: value as String?,
        options: spec.options,
        retired: spec.retired,
        optional: !spec.required,
        error: error,
        onChanged: save,
      ),
      'date' => DateBox(
        key: ValueKey(path),
        label: spec.label,
        value: value as String?,
        optional: !spec.required,
        // A picked date is complete at once, so it is checked at once.
        error: error ?? _checks.field(section, spec.key, _form.draft.data),
        onChanged: save,
      ),
      'boolean' => YesBox(
        key: ValueKey(path),
        label: spec.label,
        value: value == true,
        error: error,
        onChanged: save,
      ),
      'number' || 'decimal' => TextBox(
        key: ValueKey(path),
        label: spec.label,
        value: value?.toString() ?? '',
        optional: !spec.required,
        error: error,
        check: _checkOf(section, spec.key),
        keyboard: TextInputType.numberWithOptions(decimal: spec.type == 'decimal'),
        onChanged: save,
      ),
      _ => TextBox(
        key: ValueKey(path),
        label: spec.label,
        value: value?.toString() ?? '',
        optional: !spec.required,
        error: error,
        check: _checkOf(section, spec.key),
        completeLength: _fullLength[path],
        keyboard: switch (path) {
          'address.mobile' => TextInputType.phone,
          'address.email' => TextInputType.emailAddress,
          _ => TextInputType.text,
        },
        onChanged: save,
      ),
    };

    final age = spec.type == 'date' ? _ageOf(value) : null;
    if (age == null && !_fromQr.contains(path)) return box;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        box,
        if (age != null) _note(Icons.cake_outlined, '$age ${Strings.years}'),
        if (_fromQr.contains(path)) _note(Icons.verified_outlined, Strings.fromQr, Colors.green.shade700),
      ],
    );
  }

  Widget _note(IconData icon, String text, [Color? color]) {
    final shade = color ?? Theme.of(context).colorScheme.onSurfaceVariant;
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Row(
        children: [
          Icon(icon, size: 14, color: shade),
          const SizedBox(width: 4),
          Text(text, style: TextStyle(fontSize: 12.5, color: shade)),
        ],
      ),
    );
  }

  Widget _spaced(List<Widget> children) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      for (final child in children) ...[child, const SizedBox(height: 14)],
    ],
  );

  FormFieldSpec? _spec(String section, String key) {
    for (final spec in _schema.section(section).fields) {
      if (spec.key == key) return spec;
    }
    return null;
  }

  ButtonStyle get _outlined => OutlinedButton.styleFrom(
    minimumSize: const Size.fromHeight(50),
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
  );

  // Documents ---------------------------------------------------------------------------

  void _attach(String type, String path) {
    _changed.add('documents.$type');
    _form.attachDocument(type, path);
  }

  /// A dark or blurred photo is caught now, not days later by the reviewer.
  Future<void> _capture(String type) async {
    while (true) {
      final path = await widget.device.takePhoto();
      if (path == null) return;
      final problem = await widget.device.checkPhoto(path);
      if (!mounted) return;
      if (problem == null) {
        _doubtful.remove(type);
        _attach(type, path);
        return;
      }
      final again = await showDialog<bool>(
        context: context,
        builder: (dialog) => AlertDialog(
          icon: const Icon(Icons.warning_amber_rounded, color: Colors.orange),
          title: Text(problem == PhotoProblem.dark ? Strings.photoDark : Strings.photoBlurry),
          content: const Text(Strings.photoHelp),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialog, false),
              child: const Text(Strings.keepAnyway),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialog, true),
              child: const Text(Strings.retake),
            ),
          ],
        ),
      );
      if (again != true) {
        _doubtful[type] = problem;
        _attach(type, path);
        return;
      }
    }
  }

  Widget _image(String type, {BoxFit fit = BoxFit.cover}) => DocumentImage(
    key: ValueKey('image.$type.${_form.draft.pendingDocuments[type]}'),
    type: type,
    localPath: _form.draft.pendingDocuments[type],
    uploaded: _form.draft.uploadedDocuments.contains(type),
    load: _form.uploadedImage,
    fit: fit,
  );

  void _view(String type, {VoidCallback? retake}) => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => DocumentViewer(
        label: _documentLabels[type] ?? type,
        image: _image(type, fit: BoxFit.contain),
        onRetake: retake ?? () => _capture(type),
      ),
    ),
  );

  Widget _documentsStep() {
    final draft = _form.draft;
    final taken = _photos.where((item) => draft.hasDocument(item.$1)).length;
    return _spaced([
      _StepIntro(
        text: Strings.documentsIntro,
        trailing: '$taken / ${_photos.length}',
        done: taken == _photos.length,
      ),
      GridView.count(
        crossAxisCount: 2,
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        mainAxisSpacing: 12,
        crossAxisSpacing: 12,
        childAspectRatio: 0.98,
        children: [
          for (final (type, label, hint, icon) in _photos)
            DocumentTile(
              key: ValueKey('document.$type'),
              label: label,
              hint: hint,
              icon: icon,
              taken: draft.hasDocument(type),
              uploaded: draft.uploadedDocuments.contains(type),
              doubtful: _doubtful.containsKey(type),
              error: _errorFor('documents.$type'),
              image: _image(type),
              onTake: () => _capture(type),
              onOpen: () => _view(type),
            ),
        ],
      ),
    ]);
  }

  // Member ------------------------------------------------------------------------------

  void _applyScan(AadhaarDetails details) {
    void fill(String section, String key, String? value) {
      // The card may name the place differently, but the MPP's own record wins.
      if (value != null && !(section == 'address' && _form.draft.place.containsKey(key))) {
        _form.setValue(section, key, value);
        _fromQr.add('$section.$key');
      }
    }

    fill('applicant', 'full_name', details.name);
    fill('applicant', 'date_of_birth', details.dateOfBirth);
    fill('applicant', 'gender', details.gender);
    fill('applicant', 'relation_type', details.relationType);
    fill('applicant', 'relation_name', details.relationName);
    fill('address', 'house_number', details.houseNumber);
    fill('address', 'post_office', details.postOffice);
    fill('address', 'tehsil', details.tehsil);
    fill('address', 'district', details.district);
    fill('address', 'state', details.state);
    fill('address', 'pincode', details.pincode);
    if (details.number != null) _form.setAadhaar(details.number!);
  }

  Future<void> _scanAadhaar() async {
    final messenger = ScaffoldMessenger.of(context);
    final raw = await widget.device.scanQr(context);
    if (raw == null) return;
    final details = parseAadhaarQr(raw);
    if (details != null) _applyScan(details);
    messenger.showSnackBar(
      SnackBar(content: Text(details == null ? Strings.scanFailed : Strings.scanCheck)),
    );
  }

  Widget _applicantStep() {
    final draft = _form.draft;
    return _spaced([
      SectionCard(
        title: Strings.aadhaarNumber,
        icon: Icons.badge_outlined,
        children: [
          FilledButton.tonalIcon(
            style: FilledButton.styleFrom(
              minimumSize: const Size.fromHeight(48),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
            onPressed: _scanAadhaar,
            icon: const Icon(Icons.qr_code_scanner),
            label: const Text(Strings.scanAadhaar),
          ),
          TextBox(
            key: const ValueKey('aadhaar_number'),
            label: Strings.aadhaarNumber,
            value: draft.pendingAadhaar ?? '',
            hint: draft.aadhaarLast4.isEmpty ? null : 'XXXX XXXX ${draft.aadhaarLast4}',
            keyboard: TextInputType.number,
            formatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(12)],
            error:
                _form.aadhaarError ??
                _form.serverErrors['applicant.aadhaar_number'] ??
                _returnedBecause('applicant.aadhaar_number'),
            check: checkAadhaar,
            completeLength: 12,
            onChanged: (value) {
              _changed.add('applicant.aadhaar_number');
              _aadhaarProblem = value.length == 12 ? checkAadhaar(value) : null;
              // The server refuses a number that fails the check, so it is not sent.
              if (value.length == 12 && _aadhaarProblem == null) _form.setAadhaar(value);
            },
          ),
          if (draft.hasDocument('aadhaar_front'))
            _Thumb(
              label: Strings.aadhaarFront,
              image: _image('aadhaar_front'),
              onTap: () => _view('aadhaar_front'),
            ),
        ],
      ),
      SectionCard(
        title: Strings.memberDetails,
        icon: Icons.person_outline,
        children: [for (final spec in _schema.section('applicant').fields) _field('applicant', spec)],
      ),
    ]);
  }

  // Address -----------------------------------------------------------------------------

  Future<void> _captureLocation() async {
    final messenger = ScaffoldMessenger.of(context);
    final position = await widget.device.currentPosition();
    if (position == null) {
      messenger.showSnackBar(const SnackBar(content: Text(Strings.locationFailed)));
      return;
    }
    _form
      ..setValue('location', 'latitude', position.$1)
      ..setValue('location', 'longitude', position.$2);
  }

  Widget _addressStep() {
    final fields = _schema.section('address').fields;
    final locked = [for (final spec in fields) if (_fromMpp('address', spec) != null) spec];
    final contact = {'mobile', 'landline', 'email'};
    final location = _form.draft.section('location');
    final captured = location['latitude'] != null;
    final theme = Theme.of(context);

    return _spaced([
      if (locked.isNotEmpty)
        SectionCard(
          title: Strings.fromMppTitle,
          icon: Icons.lock_outline,
          children: [
            for (final spec in locked)
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: 130,
                    child: Text(
                      spec.label,
                      style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                    ),
                  ),
                  Expanded(
                    child: Text(
                      _fromMpp('address', spec)!,
                      key: ValueKey('address.${spec.key}'),
                      style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
                    ),
                  ),
                ],
              ),
          ],
        ),
      SectionCard(
        title: Strings.addressTitle,
        icon: Icons.home_outlined,
        children: [
          for (final spec in fields)
            if (!locked.contains(spec) && !contact.contains(spec.key)) _field('address', spec),
        ],
      ),
      SectionCard(
        title: Strings.contactTitle,
        icon: Icons.phone_outlined,
        children: [
          // The member's own number and email, each proven by an OTP right under its field.
          for (final spec in fields)
            if (contact.contains(spec.key)) ...[
              _field('address', spec),
              if (spec.key == 'mobile' || spec.key == 'email')
                ContactVerify(controller: _form, channel: spec.key),
            ],
        ],
      ),
      SectionCard(
        title: Strings.locationTitle,
        icon: Icons.location_on_outlined,
        children: [
          if (captured)
            _note(
              Icons.check_circle,
              '${(location['latitude'] as num).toStringAsFixed(5)}, '
              '${(location['longitude'] as num).toStringAsFixed(5)}',
              Colors.green.shade700,
            ),
          OutlinedButton.icon(
            style: _outlined,
            onPressed: _captureLocation,
            icon: Icon(captured ? Icons.refresh : Icons.my_location),
            label: Text(captured ? Strings.locationAgain : Strings.useLocation),
          ),
          if (_form.serverErrors['location.latitude'] != null)
            Text(
              _form.serverErrors['location.latitude']!,
              style: TextStyle(color: theme.colorScheme.error),
            ),
        ],
      ),
    ]);
  }

  // Animals -----------------------------------------------------------------------------

  static const _animalRows = [
    ('indigenous', Strings.indigenous),
    ('crossbred', Strings.crossbred),
    ('buffalo', Strings.buffalo),
  ];
  static const _countColumns = [
    ('heifer', Strings.heifer),
    ('dry', Strings.dry),
    ('in_milk', Strings.inMilk),
  ];

  /// Animals down the side and heifer / dry / in milk across, as on the printed form.
  Widget _animalGrid(Map<String, dynamic> animals) {
    final theme = Theme.of(context);
    final muted = theme.textTheme.labelMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final error = _errorFor('animals.indigenous_heifer');
    int count(String key) => int.tryParse('${animals[key] ?? ''}') ?? 0;

    Widget row(String label, List<Widget> cells, {TextStyle? style}) => Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          SizedBox(width: 86, child: Text(label, style: style ?? theme.textTheme.bodyMedium)),
          for (final cell in cells) ...[
            const SizedBox(width: 8),
            Expanded(child: cell),
          ],
        ],
      ),
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        row('', [
          for (final (_, label) in _countColumns) Text(label, textAlign: TextAlign.center, style: muted),
        ]),
        for (final (animal, label) in _animalRows)
          row(label, [
            for (final (column, _) in _countColumns)
              CountCell(
                key: ValueKey('animals.${animal}_$column'),
                value: animals['${animal}_$column']?.toString() ?? '',
                hasError: error != null,
                onChanged: (text) {
                  _changed.add('animals.${animal}_$column');
                  _form.setValue('animals', '${animal}_$column', text);
                },
              ),
          ]),
        row(Strings.total, [
          for (final (column, _) in _countColumns)
            Text(
              '${_animalRows.fold(0, (sum, item) => sum + count('${item.$1}_$column'))}',
              key: ValueKey('animals.total.$column'),
              textAlign: TextAlign.center,
              style: theme.textTheme.titleSmall,
            ),
        ], style: theme.textTheme.titleSmall),
        if (error != null) Text(error, style: TextStyle(color: theme.colorScheme.error, fontSize: 13)),
      ],
    );
  }

  Widget _animalsStep() {
    final fields = _schema.section('animals').fields;
    final amounts = fields.where((spec) => spec.type == 'decimal').toList();
    final animals = _form.draft.section('animals');
    final production = double.tryParse('${animals['production_lpd']}') ?? 0;
    final consumption = double.tryParse('${animals['consumption_lpd']}') ?? 0;
    final scheme = Theme.of(context).colorScheme;

    return _spaced([
      SectionCard(
        title: Strings.animalsTitle,
        icon: Icons.pets_outlined,
        children: [if (fields.any((spec) => spec.type == 'number')) _animalGrid(animals)],
      ),
      SectionCard(
        title: Strings.milkTitle,
        icon: Icons.water_drop_outlined,
        children: [
          for (final spec in amounts) _field('animals', spec),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(
              color: scheme.primaryContainer,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              children: [
                Icon(Icons.storefront_outlined, color: scheme.onPrimaryContainer),
                const SizedBox(width: 8),
                Text(
                  '${Strings.milkToSell}: ${(production - consumption).toStringAsFixed(1)} ${Strings.litresPerDay}',
                  style: TextStyle(color: scheme.onPrimaryContainer, fontWeight: FontWeight.w600),
                ),
              ],
            ),
          ),
        ],
      ),
    ]);
  }

  // Bank --------------------------------------------------------------------------------

  String _accountAgain = '';
  String _accountFirst = '';

  /// A complete IFSC fills the bank and branch: the bank master first, then the internet.
  Future<void> _ifscChanged(String value) async {
    final ifsc = value.trim().toUpperCase();
    _changed.add('bank.ifsc');
    _form.setValue('bank', 'ifsc', ifsc);
    if (!RegExp(r'^[A-Z]{4}0[A-Z0-9]{6}$').hasMatch(ifsc)) {
      if (_lookup != _Lookup.idle) setState(() => _lookup = _Lookup.idle);
      return;
    }
    setState(() => _lookup = _Lookup.looking);
    final found = await (widget.findBranch ?? widget.device.lookupIfsc)(ifsc);
    if (!mounted) return;
    if (found == null) {
      setState(() => _lookup = _Lookup.notFound);
      return;
    }
    _form
      ..setValue('bank', 'bank_name', found.$1)
      ..setValue('bank', 'branch_name', found.$2);
    setState(() => _lookup = _Lookup.found);
  }

  Widget _lookupCard() {
    final scheme = Theme.of(context).colorScheme;
    final bank = _form.draft.section('bank');
    final (icon, text, color) = switch (_lookup) {
      _Lookup.looking => (Icons.search, Strings.findingBranch, scheme.onSurfaceVariant),
      _Lookup.found => (
        Icons.check_circle,
        '${bank['bank_name'] ?? ''} · ${bank['branch_name'] ?? ''}',
        Colors.green.shade700,
      ),
      _Lookup.notFound => (Icons.info_outline, Strings.branchNotFound, Colors.orange.shade800),
      _Lookup.idle => (Icons.info_outline, '', scheme.onSurfaceVariant),
    };
    return Container(
      key: const ValueKey('bank.lookup'),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Row(
        children: [
          if (_lookup == _Lookup.looking)
            const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2))
          else
            Icon(icon, color: color, size: 20),
          const SizedBox(width: 10),
          Expanded(child: Text(text, style: TextStyle(color: color, fontWeight: FontWeight.w600))),
        ],
      ),
    );
  }

  Widget _bankStep() {
    final draft = _form.draft;
    final matches = _accountFirst == _accountAgain;
    final fields = _schema.section('bank').fields;
    final memberName = '${draft.section('applicant')['full_name'] ?? ''}'.trim();
    final holder = '${draft.section('bank')['holder_name'] ?? ''}'.trim();

    return _spaced([
      if (draft.hasDocument('passbook'))
        _Thumb(label: Strings.passbook, image: _image('passbook'), onTap: () => _view('passbook')),
      SectionCard(
        title: Strings.accountNumber,
        icon: Icons.numbers,
        children: [
          TextBox(
            key: const ValueKey('account_number'),
            label: Strings.accountNumber,
            value: '',
            hint: draft.accountLast4.isEmpty ? null : 'XXXX ${draft.accountLast4}',
            keyboard: TextInputType.number,
            obscure: true,
            formatters: [FilteringTextInputFormatter.digitsOnly],
            error: _form.serverErrors['bank.account_number'] ?? _returnedBecause('bank.account_number'),
            check: checkAccount,
            onChanged: (value) {
              _changed.add('bank.account_number');
              setState(() {
                _accountFirst = value;
                _accountProblem = checkAccount(value);
              });
              if (_accountProblem == null && value.isNotEmpty && value == _accountAgain) {
                _form.setAccount(value);
              }
            },
          ),
          // Typed twice: one wrong digit sends milk money to the wrong person.
          TextBox(
            key: const ValueKey('account_number_again'),
            label: Strings.accountAgain,
            value: _accountAgain,
            keyboard: TextInputType.number,
            formatters: [FilteringTextInputFormatter.digitsOnly],
            error: _accountAgain.isNotEmpty && !matches ? Strings.accountMismatch : null,
            onChanged: (value) {
              setState(() => _accountAgain = value);
              if (_accountProblem == null && value.isNotEmpty && value == _accountFirst) {
                _form.setAccount(value);
              }
            },
          ),
          if (_accountAgain.isNotEmpty && matches && _accountProblem == null)
            _note(Icons.check_circle, Strings.accountsMatch, Colors.green.shade700),
        ],
      ),
      SectionCard(
        title: Strings.bankTitle,
        icon: Icons.account_balance_outlined,
        children: [
          for (final spec in fields)
            if (spec.key == 'holder_name') ...[
              _field('bank', spec),
              if (memberName.isNotEmpty && holder != memberName)
                Align(
                  alignment: Alignment.centerLeft,
                  child: ActionChip(
                    avatar: const Icon(Icons.content_copy, size: 16),
                    label: Text('${Strings.sameAsMember}: $memberName'),
                    onPressed: () => _form.setValue('bank', 'holder_name', memberName),
                  ),
                ),
            ] else if (spec.key == 'ifsc') ...[
              TextBox(
                key: const ValueKey('bank.ifsc'),
                label: spec.label,
                value: '${draft.section('bank')['ifsc'] ?? ''}',
                error: _errorFor('bank.ifsc'),
                check: _checkOf('bank', 'ifsc'),
                completeLength: _fullLength['bank.ifsc'],
                formatters: [UpperCaseTextFormatter(), LengthLimitingTextInputFormatter(11)],
                onChanged: _ifscChanged,
              ),
              if (_lookup != _Lookup.idle) _lookupCard(),
            ] else
              _field('bank', spec),
        ],
      ),
    ]);
  }

  // Household ---------------------------------------------------------------------------

  String _choice(String? value, List<ChoiceOption> options, List<ChoiceOption> retired) =>
      choiceLabel(value, options, retired) ?? '';

  void _setFamily(List<Map<String, dynamic>> family) {
    _changed.add('family');
    _form.setFamily(family);
  }

  Future<void> _editPerson(int? index, [Map<String, dynamic>? start]) async {
    final family = _form.draft.family;
    final person = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => PersonSheet(
        person: start ?? (index == null ? const {} : family[index]),
        genders: _schema.familyGenders,
        relations: _schema.familyRelations,
        checkAge: _checks.familyAge,
      ),
    );
    if (person == null || !mounted) return;
    final next = [...family];
    final before = index == null ? null : family[index];
    if (index == null) {
      next.add(person);
    } else {
      next[index] = person;
    }
    _setFamily(next);
    _syncNomineeFromPerson(before, person);
  }

  Future<void> _removePerson(int index) async {
    final family = _form.draft.family;
    final sure = await showDialog<bool>(
      context: context,
      builder: (dialog) => AlertDialog(
        title: Text('${Strings.removePerson} ${family[index]['name'] ?? ''}?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialog, false), child: const Text(Strings.cancel)),
          FilledButton(onPressed: () => Navigator.pop(dialog, true), child: const Text(Strings.removePerson)),
        ],
      ),
    );
    if (sure == true) _setFamily([...family]..removeAt(index));
  }

  Widget _familyStep() {
    final family = _form.draft.family;
    final applicant = _form.draft.section('applicant');
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final relationName = '${applicant['relation_name'] ?? ''}'.trim();
    final relationType = '${applicant['relation_type'] ?? ''}';
    final known = family.any(
      (person) => '${person['name'] ?? ''}'.trim().toLowerCase() == relationName.toLowerCase(),
    );
    final relationIsListed = _schema.familyRelations.any((option) => option.value == relationType);
    final full = family.length >= _schema.maxFamilyMembers;

    return _spaced([
      _StepIntro(
        text: Strings.familyIntro,
        trailing: '${family.length} / ${_schema.maxFamilyMembers}',
        done: family.isNotEmpty,
      ),
      if (relationName.isNotEmpty && !known && !full)
        ActionChip(
          key: const ValueKey('family.quick_add'),
          avatar: const Icon(Icons.person_add_alt_1, size: 18),
          label: Text('${Strings.addPerson}: $relationName'),
          onPressed: () => _editPerson(null, {
            'name': relationName,
            if (relationIsListed) 'relation': relationType,
            if (relationType == 'husband' || relationType == 'father') 'gender': 'male',
          }),
        ),
      for (final (index, person) in family.indexed)
        Material(
          key: ValueKey('family.$index'),
          color: scheme.surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
            side: BorderSide(
              color: _form.serverErrors.keys.any((key) => key.startsWith('family.$index.'))
                  ? scheme.error
                  : scheme.outlineVariant,
            ),
          ),
          child: ListTile(
            contentPadding: const EdgeInsets.fromLTRB(12, 4, 4, 4),
            leading: CircleAvatar(
              backgroundColor: scheme.primaryContainer,
              child: Text(
                '${person['name'] ?? '?'}'.trim().isEmpty ? '?' : '${person['name']}'.trim()[0].toUpperCase(),
                style: TextStyle(color: scheme.onPrimaryContainer, fontWeight: FontWeight.w700),
              ),
            ),
            title: Text('${person['name'] ?? ''}', style: const TextStyle(fontWeight: FontWeight.w600)),
            subtitle: Text(
              [
                _choice(person['relation'] as String?, _schema.familyRelations, _schema.retiredRelations),
                _choice(person['gender'] as String?, _schema.familyGenders, _schema.retiredGenders),
                if ('${person['age'] ?? ''}'.isNotEmpty) '${person['age']} ${Strings.years}',
              ].where((part) => part.isNotEmpty).join(' · '),
            ),
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton(
                  tooltip: Strings.editPerson,
                  icon: const Icon(Icons.edit_outlined),
                  onPressed: () => _editPerson(index),
                ),
                IconButton(
                  tooltip: Strings.removePerson,
                  icon: Icon(Icons.delete_outline, color: scheme.error),
                  onPressed: () => _removePerson(index),
                ),
              ],
            ),
            onTap: () => _editPerson(index),
          ),
        ),
      if (family.isEmpty)
        Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: scheme.outlineVariant),
          ),
          child: Column(
            children: [
              Icon(Icons.groups_outlined, size: 36, color: scheme.onSurfaceVariant),
              const SizedBox(height: 8),
              Text(Strings.noFamily, style: theme.textTheme.bodyMedium),
            ],
          ),
        ),
      if (!full)
        OutlinedButton.icon(
          style: _outlined,
          onPressed: () => _editPerson(null),
          icon: const Icon(Icons.person_add_alt),
          label: const Text(Strings.addPerson),
        ),
    ]);
  }

  // Nominee -----------------------------------------------------------------------------

  static String _birthYearDate(int age) => '${DateTime.now().year - age}-01-01';

  /// Only the year is known from an age, so it stands for 1 January of that year.
  void _chooseNominee(Map<String, dynamic> person) {
    _changed.add('nominee.name');
    _form.setValue('nominee', 'name', '${person['name'] ?? ''}');
    final relation = person['relation'] as String?;
    final relationSpec = _spec('nominee', 'relation');
    if (relation != null && (relationSpec?.options.any((option) => option.value == relation) ?? false)) {
      _form.setValue('nominee', 'relation', relation);
    }
    final age = int.tryParse('${person['age'] ?? ''}');
    if (age != null) _form.setValue('nominee', 'date_of_birth', _birthYearDate(age));
  }

  int? _nomineeInFamily() {
    final name = '${_form.draft.section('nominee')['name'] ?? ''}'.trim().toLowerCase();
    if (name.isEmpty) return null;
    for (final (index, person) in _form.draft.family.indexed) {
      if ('${person['name'] ?? ''}'.trim().toLowerCase() == name) return index;
    }
    return null;
  }

  /// A nominee's new date of birth changes the age of the same person in the household.
  void _syncFamilyFromNominee(Object? dateOfBirth) {
    final index = _nomineeInFamily();
    final age = _ageOf(dateOfBirth);
    if (index == null || age == null) return;
    final family = _form.draft.family;
    if ('${family[index]['age'] ?? ''}' == '$age') return;
    _setFamily([...family]..[index] = {...family[index], 'age': '$age'});
  }

  /// And a household member's new age moves the nominee's year of birth, when it is them.
  void _syncNomineeFromPerson(Map<String, dynamic>? before, Map<String, dynamic> after) {
    final nominee = _form.draft.section('nominee');
    final name = '${nominee['name'] ?? ''}'.trim().toLowerCase();
    if (name.isEmpty) return;
    final names = {'${before?['name'] ?? ''}', '${after['name'] ?? ''}'}.map((item) => item.trim().toLowerCase());
    if (!names.contains(name)) return;
    final age = int.tryParse('${after['age'] ?? ''}');
    if (age == null || _ageOf(nominee['date_of_birth']) == age) return;
    _form.setValue('nominee', 'date_of_birth', _birthYearDate(age));
  }

  String _memberAddress() {
    final draft = _form.draft;
    final address = draft.section('address');
    String part(String key) => '${draft.place[key] ?? address[key] ?? ''}'.trim();
    return [
      part('house_number'),
      part('village_name'),
      if (part('post_office').isNotEmpty) 'PO ${part('post_office')}',
      part('tehsil'),
      part('district'),
      part('state'),
      part('pincode'),
    ].where((item) => item.isNotEmpty).join(', ');
  }

  Widget _nomineeStep() {
    final family = _form.draft.family;
    final nominee = _form.draft.section('nominee');
    final chosen = _nomineeInFamily();
    final age = _ageOf(nominee['date_of_birth']);
    final memberAddress = _memberAddress();
    final sameAddress = memberAddress.isNotEmpty && '${nominee['address'] ?? ''}' == memberAddress;

    return _spaced([
      if (family.isNotEmpty)
        SectionCard(
          title: Strings.chooseFromFamily,
          icon: Icons.groups_outlined,
          children: [
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final (index, person) in family.indexed)
                  ChoiceChip(
                    key: ValueKey('nominee.from.$index'),
                    label: Text('${person['name'] ?? ''}'),
                    selected: chosen == index,
                    onSelected: (_) => _chooseNominee(person),
                  ),
              ],
            ),
          ],
        ),
      SectionCard(
        title: Strings.nomineeTitle,
        icon: Icons.volunteer_activism_outlined,
        children: [
          for (final spec in _schema.section('nominee').fields)
            if (spec.key == 'date_of_birth') ...[
              _field('nominee', spec, onSaved: _syncFamilyFromNominee),
              _note(Icons.info_outline, Strings.yearOnlyHint),
            ] else if (spec.key == 'address') ...[
              _field('nominee', spec),
              if (memberAddress.isNotEmpty)
                CheckboxListTile(
                  key: const ValueKey('nominee.same_address'),
                  value: sameAddress,
                  contentPadding: EdgeInsets.zero,
                  controlAffinity: ListTileControlAffinity.leading,
                  title: const Text(Strings.sameAddress),
                  onChanged: (checked) {
                    _changed.add('nominee.address');
                    _form.setValue('nominee', 'address', checked == true ? memberAddress : '');
                  },
                ),
            ] else if (spec.key == 'guardian_name') ...[
              // Only a minor nominee needs a guardian.
              if (age != null && age < 18) _field('nominee', spec),
            ] else
              _field('nominee', spec),
        ],
      ),
    ]);
  }

  Widget _declarationStep() => SectionCard(
    title: _schema.section('declaration').title,
    icon: Icons.fact_check_outlined,
    children: [for (final spec in _schema.section('declaration').fields) _field('declaration', spec)],
  );

  // Review and signature ----------------------------------------------------------------

  Future<void> _sign() async {
    final path = await Navigator.of(
      context,
    ).push<String>(MaterialPageRoute(builder: (_) => const SignaturePadScreen()));
    if (path != null) _attach('member_signature', path);
  }

  Widget _signatureCard() {
    final draft = _form.draft;
    final signed = draft.hasDocument('member_signature');
    final thumb = draft.hasDocument('member_thumbprint');
    final type = signed ? 'member_signature' : 'member_thumbprint';
    final error = _errorFor('documents.member_signature');
    return SectionCard(
      key: const ValueKey('review.signature'),
      title: Strings.memberSignature,
      icon: Icons.draw_outlined,
      children: [
        Text(Strings.signLast, style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
        if (signed || thumb)
          ClipRRect(
            borderRadius: BorderRadius.circular(12),
            child: Container(
              height: 140,
              color: Colors.white,
              child: InkWell(
                onTap: () => _view(type, retake: signed ? _sign : () => _capture(type)),
                child: _image(type, fit: BoxFit.contain),
              ),
            ),
          ),
        FilledButton.icon(
          style: FilledButton.styleFrom(
            minimumSize: const Size.fromHeight(50),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          ),
          onPressed: _sign,
          icon: const Icon(Icons.draw_outlined),
          label: Text(signed ? Strings.signAgain : Strings.signHere),
        ),
        TextButton(
          onPressed: () => _capture('member_thumbprint'),
          child: Text(thumb ? Strings.thumbprintAgain : Strings.cannotWrite),
        ),
        if (error != null) Text(error, style: TextStyle(color: Theme.of(context).colorScheme.error)),
      ],
    );
  }

  /// What is still empty, so the facilitator can jump straight to it.
  List<(String, int)> _missing() {
    final draft = _form.draft;
    final missing = <(String, int)>[];

    for (final section in _schema.sections) {
      for (final spec in section.fields.where((field) => field.required)) {
        final value = _fromMpp(section.key, spec) ?? draft.section(section.key)[spec.key];
        if (value == null || value == '' || value == false) {
          missing.add((spec.label, _stepOf(section.key)));
        }
      }
    }
    if (!draft.hasAadhaar) missing.add((Strings.aadhaarNumber, 1));
    if (!draft.hasAccount) missing.add((Strings.accountNumber, 4));
    // The mobile number and the email go in only once confirmed by OTP.
    final address = draft.section('address');
    if ('${address['mobile'] ?? ''}'.trim().isNotEmpty && !draft.mobileVerified) {
      missing.add((Strings.mobileNotVerified, 2));
    }
    if ('${address['email'] ?? ''}'.trim().isNotEmpty && !draft.emailVerified) {
      missing.add((Strings.emailNotVerified, 2));
    }
    for (final (type, label, _, _) in _photos) {
      if (!draft.hasDocument(type)) missing.add((label, 0));
    }
    if (!draft.hasDocument('member_signature') && !draft.hasDocument('member_thumbprint')) {
      missing.add((Strings.memberSignature, _reviewIndex));
    }
    return missing;
  }

  Future<void> _submit() async {
    final navigator = Navigator.of(context);
    if (!await _form.submit()) return;
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (dialog) => AlertDialog(
        icon: Icon(Icons.check_circle, color: Colors.green.shade600, size: 48),
        title: const Text(Strings.submitted),
        content: const Text(Strings.submittedHint, textAlign: TextAlign.center),
        actions: [
          FilledButton(onPressed: () => Navigator.pop(dialog), child: const Text(Strings.done)),
        ],
      ),
    );
    navigator.pop(true);
  }

  String _labelOf(String path) {
    final dot = path.indexOf('.');
    final section = dot < 0 ? path : path.substring(0, dot);
    final key = dot < 0 ? '' : path.substring(dot + 1);
    if (path == 'applicant.aadhaar_number') return Strings.aadhaarNumber;
    if (path == 'bank.account_number') return Strings.accountNumber;
    if (section == 'family') return Strings.family;
    if (section == 'documents') return _documentLabels[key] ?? key;
    return _spec(section, key)?.label ?? path;
  }

  /// What the server would refuse, found on the phone, with the step it is on.
  List<(String, String, int)> _problems() {
    final problems = [
      if (_aadhaarProblem != null) ('applicant.aadhaar_number', _aadhaarProblem!, 1),
      for (final MapEntry(key: path, value: message) in _checks.all(_form.draft.data).entries)
        if (!_form.serverErrors.containsKey(path)) (path, message, _stepOf(path)),
      if (_accountProblem != null) ('bank.account_number', _accountProblem!, 4),
    ];
    problems.sort((a, b) => a.$3.compareTo(b.$3));
    return problems;
  }

  String _problemLabel(String path) {
    final parts = path.split('.');
    if (parts.length == 3 && parts.first == 'family') {
      return '${Strings.family} ${int.parse(parts[1]) + 1}: ${Strings.age}';
    }
    // The animal count rule is about the whole table, not its first box.
    if (path == 'animals.indigenous_heifer') return _schema.section('animals').title;
    return _labelOf(path);
  }

  /// How much is left on each step, for the checklist and the step chips.
  Map<int, int> _leftByStep() {
    final left = <int, int>{};
    for (final (_, step) in [..._missing(), for (final (_, _, step) in _problems()) ('', step)]) {
      left[step] = (left[step] ?? 0) + 1;
    }
    return left;
  }

  /// Every step at a glance: done, or how much is left, one tap from fixing it.
  Widget _checklist(Map<int, int> left) {
    return SectionCard(
      title: Strings.checklist,
      icon: Icons.checklist,
      children: [
        for (var step = 0; step < _steps.length; step++)
          ListTile(
            key: ValueKey('checklist.$step'),
            dense: true,
            contentPadding: EdgeInsets.zero,
            leading: Icon(
              left.containsKey(step) ? Icons.error_outline : Icons.check_circle,
              color: left.containsKey(step) ? Colors.orange.shade800 : Colors.green,
            ),
            title: Text('${step + 1}. ${_steps[step].title}'),
            trailing: Text(left.containsKey(step) ? '${left[step]} ${Strings.stepLeft}' : Strings.stepDone),
            onTap: () => _go(step),
          ),
      ],
    );
  }

  /// For a returned form: each field the reviewer marked, and whether it was changed.
  Widget _corrections() {
    final rejected = _form.draft.rejectedFields;
    // Material, not a coloured box, so the rows still show their tap ripple.
    return Material(
      color: Colors.red.shade50,
      borderRadius: BorderRadius.circular(14),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(Strings.toCorrect, style: TextStyle(fontWeight: FontWeight.w600)),
            for (final path in rejected)
              ListTile(
                key: ValueKey('correction.$path'),
                dense: true,
                contentPadding: EdgeInsets.zero,
                leading: Icon(
                  _changed.contains(path) ? Icons.check_circle : Icons.edit_outlined,
                  color: _changed.contains(path) ? Colors.green : Colors.red.shade700,
                ),
                title: Text(_labelOf(path)),
                // The reviewer's reason first, so the facilitator knows what to fix.
                subtitle: Text(
                  [
                    ?_form.draft.noteFor(path),
                    _changed.contains(path) ? Strings.corrected : Strings.notCorrected,
                  ].join(' · '),
                ),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => _go(_stepOf(path)),
              ),
          ],
        ),
      ),
    );
  }

  Widget _reviewStep() {
    final missing = _missing();
    final problems = _problems();
    final errors = _form.serverErrors;
    final doubtful = _doubtful.keys.where(_form.draft.hasDocument).toList();
    final scheme = Theme.of(context).colorScheme;
    return _spaced([
      if (errors.isNotEmpty) ...[
        const Text(Strings.fixFirst, style: TextStyle(fontWeight: FontWeight.w600)),
        for (final message in errors.values) Text('• $message'),
      ],
      if (_form.draft.rejectedFields.isNotEmpty) _corrections(),
      if (problems.isNotEmpty)
        Material(
          key: const ValueKey('review.problems'),
          color: Colors.orange.shade50,
          borderRadius: BorderRadius.circular(14),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text(Strings.pleaseCheck, style: TextStyle(fontWeight: FontWeight.w600)),
                for (final (path, message, step) in problems)
                  ListTile(
                    key: ValueKey('problem.$path'),
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    leading: Icon(Icons.error_outline, color: Colors.orange.shade800),
                    title: Text(_problemLabel(path)),
                    subtitle: Text(message),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => _go(step),
                  ),
              ],
            ),
          ),
        ),
      if (missing.isNotEmpty)
        Material(
          key: const ValueKey('review.missing'),
          color: scheme.inverseSurface,
          borderRadius: BorderRadius.circular(14),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  Strings.stillNeeded,
                  style: TextStyle(fontWeight: FontWeight.w700, color: scheme.onInverseSurface),
                ),
                for (final (label, step) in missing)
                  ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    title: Text(label, style: TextStyle(color: scheme.onInverseSurface)),
                    trailing: Icon(Icons.chevron_right, color: scheme.onInverseSurface),
                    onTap: () => _go(step),
                  ),
              ],
            ),
          ),
        ),
      for (final type in doubtful)
        ListTile(
          dense: true,
          contentPadding: EdgeInsets.zero,
          leading: const Icon(Icons.warning_amber_rounded, color: Colors.orange),
          title: Text(_documentLabels[type] ?? type),
          subtitle: const Text(Strings.photoDoubt),
          trailing: const Icon(Icons.chevron_right),
          onTap: () => _go(0),
        ),
      _checklist(_leftByStep()),
      _signatureCard(),
      if (missing.isEmpty)
        Text(Strings.allFilled, style: TextStyle(color: Colors.green.shade700, fontWeight: FontWeight.w600)),
      FilledButton(
        style: FilledButton.styleFrom(
          minimumSize: const Size.fromHeight(54),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
        onPressed: missing.isEmpty ? _submit : null,
        child: const Text(Strings.submit, style: TextStyle(fontWeight: FontWeight.w700)),
      ),
    ]);
  }

  Widget _currentStep() => switch (_steps[_index].key) {
    'documents' => _documentsStep(),
    'applicant' => _applicantStep(),
    'address' => _addressStep(),
    'animals' => _animalsStep(),
    'bank' => _bankStep(),
    'family' => _familyStep(),
    'nominee' => _nomineeStep(),
    'declaration' => _declarationStep(),
    _ => _reviewStep(),
  };

  Widget _syncChip() {
    final (text, color, icon) = switch (_form.state) {
      SyncState.saved => (Strings.saved, Colors.green.shade700, Icons.cloud_done_outlined),
      SyncState.saving => (Strings.saving, Colors.black54, Icons.cloud_sync_outlined),
      SyncState.offline => (Strings.offline, Colors.orange.shade800, Icons.phone_android),
      SyncState.conflict => (Strings.conflict, Colors.red.shade700, Icons.sync_problem),
      SyncState.failed => (Strings.syncFailed, Colors.red.shade700, Icons.cloud_off_outlined),
    };
    return Row(
      children: [
        Icon(icon, size: 16, color: color),
        const SizedBox(width: 6),
        Expanded(
          child: Text(text, style: TextStyle(color: color, fontSize: 12.5), overflow: TextOverflow.ellipsis),
        ),
        if (_form.state == SyncState.conflict)
          TextButton(onPressed: _form.reloadFromServer, child: const Text(Strings.useServerCopy)),
      ],
    );
  }

  /// The steps as chips: where you are, what is done, and a tap to jump anywhere.
  Widget _stepChips(Map<int, int> left) {
    final scheme = Theme.of(context).colorScheme;
    return SizedBox(
      height: 44,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        itemCount: _steps.length,
        separatorBuilder: (_, _) => const SizedBox(width: 6),
        itemBuilder: (context, step) {
          final current = step == _index;
          final done = !left.containsKey(step);
          return InkWell(
            key: ValueKey('stepchip.$step'),
            borderRadius: BorderRadius.circular(16),
            onTap: () => _go(step),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10),
              decoration: BoxDecoration(
                color: current ? scheme.primary : scheme.surfaceContainerHigh,
                borderRadius: BorderRadius.circular(16),
              ),
              child: Row(
                children: [
                  Icon(
                    done ? Icons.check_circle : _steps[step].icon,
                    size: 16,
                    color: current ? scheme.onPrimary : (done ? Colors.green.shade600 : scheme.onSurfaceVariant),
                  ),
                  const SizedBox(width: 4),
                  Text(
                    '${step + 1}',
                    style: TextStyle(
                      fontWeight: FontWeight.w700,
                      color: current ? scheme.onPrimary : scheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final draft = _form.draft;
    final scheme = Theme.of(context).colorScheme;
    final left = _leftByStep();
    final last = _index == _steps.length - 1;
    return Scaffold(
      backgroundColor: scheme.surfaceContainerLowest,
      appBar: AppBar(
        backgroundColor: scheme.surfaceContainerLowest,
        surfaceTintColor: Colors.transparent,
        titleSpacing: 0,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '${Strings.step} ${_index + 1} / ${_steps.length}',
              style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
            ),
            Text(_steps[_index].title, style: const TextStyle(fontWeight: FontWeight.w700)),
          ],
        ),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(48),
          child: Column(
            children: [
              _stepChips(left),
              LinearProgressIndicator(value: (_index + 1) / _steps.length, minHeight: 3),
            ],
          ),
        ),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Padding(padding: const EdgeInsets.fromLTRB(16, 8, 16, 0), child: _syncChip()),
            if (draft.rejectionReason.isNotEmpty)
              Container(
                width: double.infinity,
                margin: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(color: Colors.red.shade50, borderRadius: BorderRadius.circular(12)),
                child: Text('${Strings.rejectedBecause}: ${draft.rejectionReason}'),
              ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
                children: [_currentStep()],
              ),
            ),
            Container(
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 12),
              decoration: BoxDecoration(
                color: scheme.surface,
                border: Border(top: BorderSide(color: scheme.outlineVariant)),
              ),
              child: Row(
                children: [
                  if (_index > 0)
                    Expanded(
                      child: OutlinedButton(
                        style: _outlined,
                        onPressed: () => _go(_index - 1),
                        child: const Text(Strings.back),
                      ),
                    ),
                  if (_index > 0 && !last) const SizedBox(width: 12),
                  if (!last)
                    Expanded(
                      child: FilledButton(
                        style: FilledButton.styleFrom(
                          minimumSize: const Size.fromHeight(50),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                        ),
                        onPressed: () => _go(_index + 1),
                        child: const Text(Strings.next),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// A line above a step: what it asks for, and how far along it is.
class _StepIntro extends StatelessWidget {
  const _StepIntro({required this.text, required this.trailing, required this.done});

  final String text;
  final String trailing;
  final bool done;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Row(
      children: [
        Expanded(child: Text(text, style: TextStyle(color: scheme.onSurfaceVariant))),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
          decoration: BoxDecoration(
            color: done ? Colors.green.shade50 : scheme.secondaryContainer,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Text(
            trailing,
            style: TextStyle(
              fontWeight: FontWeight.w700,
              color: done ? Colors.green.shade800 : scheme.onSecondaryContainer,
            ),
          ),
        ),
      ],
    );
  }
}

/// A small photo already taken, to type from without leaving the step.
class _Thumb extends StatelessWidget {
  const _Thumb({required this.label, required this.image, required this.onTap});

  final String label;
  final Widget image;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Material(
      color: scheme.surface,
      borderRadius: BorderRadius.circular(14),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: scheme.outlineVariant),
          ),
          child: Row(
            children: [
              SizedBox(width: 120, height: 80, child: image),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(label, style: const TextStyle(fontWeight: FontWeight.w600)),
                    const SizedBox(height: 2),
                    Text(Strings.tapToZoom, style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
                  ],
                ),
              ),
              Icon(Icons.zoom_in, color: scheme.onSurfaceVariant),
              const SizedBox(width: 12),
            ],
          ),
        ),
      ),
    );
  }
}
