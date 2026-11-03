import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../aadhaar/aadhaar_qr.dart';
import '../models/form_schema.dart';
import '../sync/draft_controller.dart';
import '../validation/form_checks.dart';
import 'device_services.dart';
import 'contact_verify.dart';
import 'fields.dart';
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
  const _Step(this.title, this.build);

  final String title;
  final Widget Function() build;
}

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

  late final List<_Step> _steps = [
    _Step(_schema.section('applicant').title, _applicantStep),
    _Step(_schema.section('address').title, _addressStep),
    _Step(_schema.section('animals').title, _animalsStep),
    _Step(_schema.section('bank').title, _bankStep),
    const _Step(Strings.family, _placeholder),
    _Step(_schema.section('nominee').title, () => _section('nominee')),
    const _Step(Strings.documents, _placeholder),
    _Step(_schema.section('declaration').title, () => _section('declaration')),
    const _Step(Strings.review, _placeholder),
  ];

  static Widget _placeholder() => const SizedBox.shrink();

  /// Which step each part of the form is filled on.
  static const _sectionStep = {
    'applicant': 0,
    'address': 1,
    'location': 1,
    'animals': 2,
    'bank': 3,
    'family': 4,
    'nominee': 5,
    'documents': 6,
    'declaration': 7,
  };

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

  /// Photos kept although they looked too dark or blurred.
  final Map<String, PhotoProblem> _doubtful = {};

  int _stepOf(String path) => _sectionStep[path.split('.').first] ?? 0;

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

  Widget _field(String section, FormFieldSpec spec) {
    final fixed = _fromMpp(section, spec);
    if (fixed != null) {
      return LockedBox(key: ValueKey('$section.${spec.key}'), label: spec.label, value: fixed);
    }
    final value = _form.draft.section(section)[spec.key];
    final error = _errorFor('$section.${spec.key}');
    void save(Object? next) {
      _changed.add('$section.${spec.key}');
      _form.setValue(section, spec.key, next);
    }

    return switch (spec.type) {
      'choice' => ChoiceBox(
        key: ValueKey('$section.${spec.key}'),
        label: spec.label,
        value: value as String?,
        options: spec.options,
        retired: spec.retired,
        optional: !spec.required,
        error: error,
        onChanged: save,
      ),
      'date' => DateBox(
        key: ValueKey('$section.${spec.key}'),
        label: spec.label,
        value: value as String?,
        optional: !spec.required,
        // A picked date is complete at once, so it is checked at once.
        error: error ?? _checks.field(section, spec.key, _form.draft.data),
        onChanged: save,
      ),
      'boolean' => YesBox(
        key: ValueKey('$section.${spec.key}'),
        label: spec.label,
        value: value == true,
        error: error,
        onChanged: save,
      ),
      'number' || 'decimal' => TextBox(
        key: ValueKey('$section.${spec.key}'),
        label: spec.label,
        value: value?.toString() ?? '',
        optional: !spec.required,
        error: error,
        check: _checkOf(section, spec.key),
        keyboard: TextInputType.numberWithOptions(decimal: spec.type == 'decimal'),
        onChanged: save,
      ),
      _ => TextBox(
        key: ValueKey('$section.${spec.key}'),
        label: spec.label,
        value: value?.toString() ?? '',
        optional: !spec.required,
        error: error,
        check: _checkOf(section, spec.key),
        completeLength: _fullLength['$section.${spec.key}'],
        keyboard: switch ('$section.${spec.key}') {
          'address.mobile' => TextInputType.phone,
          'address.email' => TextInputType.emailAddress,
          _ => TextInputType.text,
        },
        onChanged: save,
      ),
    };
  }

  Widget _spaced(List<Widget> children) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      for (final child in children) ...[child, const SizedBox(height: 18)],
    ],
  );

  Widget _section(String key) =>
      _spaced([for (final spec in _schema.section(key).fields) _field(key, spec)]);

  /// A complete IFSC fills the bank and branch. Offline, they are simply typed.
  Future<void> _ifscChanged(String value) async {
    final ifsc = value.trim().toUpperCase();
    _changed.add('bank.ifsc');
    _form.setValue('bank', 'ifsc', ifsc);
    if (!RegExp(r'^[A-Z]{4}0[A-Z0-9]{6}$').hasMatch(ifsc)) return;

    final found = await (widget.findBranch ?? widget.device.lookupIfsc)(ifsc);
    if (found == null || !mounted) return;
    _form
      ..setValue('bank', 'bank_name', found.$1)
      ..setValue('bank', 'branch_name', found.$2);
  }

  void _applyScan(AadhaarDetails details) {
    void fill(String section, String key, String? value) {
      // The card may name the place differently, but the MPP's own record wins.
      if (value != null && !(section == 'address' && _form.draft.place.containsKey(key))) {
        _form.setValue(section, key, value);
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
      OutlinedButton.icon(
        style: OutlinedButton.styleFrom(
          shape: const RoundedRectangleBorder(),
          minimumSize: const Size.fromHeight(52),
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
      _section('applicant'),
    ]);
  }

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
    final location = _form.draft.section('location');
    final captured = location['latitude'] != null;
    return _spaced([
      _section('address'),
      // The member's own number and email, proven by an OTP while she is here.
      ContactVerify(controller: _form, channel: 'mobile'),
      if ('${_form.draft.section('address')['email'] ?? ''}'.trim().isNotEmpty)
        ContactVerify(controller: _form, channel: 'email'),
      OutlinedButton.icon(
        style: OutlinedButton.styleFrom(
          shape: const RoundedRectangleBorder(),
          minimumSize: const Size.fromHeight(52),
        ),
        onPressed: _captureLocation,
        icon: Icon(captured ? Icons.check_circle : Icons.my_location),
        label: Text(captured ? Strings.locationSaved : Strings.useLocation),
      ),
      if (_form.serverErrors['location.latitude'] != null)
        Text(
          _form.serverErrors['location.latitude']!,
          style: TextStyle(color: Theme.of(context).colorScheme.error),
        ),
    ]);
  }

  Widget _animalsStep() {
    final fields = _schema.section('animals').fields;
    final counts = fields.where((spec) => spec.type == 'number').toList();
    final amounts = fields.where((spec) => spec.type == 'decimal').toList();
    final animals = _form.draft.section('animals');
    final production = double.tryParse('${animals['production_lpd']}') ?? 0;
    final consumption = double.tryParse('${animals['consumption_lpd']}') ?? 0;

    return _spaced([
      for (var at = 0; at < counts.length; at += 3)
        Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            for (final spec in counts.skip(at).take(3)) ...[
              Expanded(child: _field('animals', spec)),
              if (spec != counts.skip(at).take(3).last) const SizedBox(width: 8),
            ],
          ],
        ),
      for (final spec in amounts) _field('animals', spec),
      Text('बिक्री योग्य दूध: ${(production - consumption).toStringAsFixed(1)} लीटर प्रति दिन'),
    ]);
  }

  String _accountAgain = '';
  String _accountFirst = '';

  Widget _bankStep() {
    final draft = _form.draft;
    final matches = _accountFirst == _accountAgain;
    return _spaced([
      TextBox(
        key: const ValueKey('account_number'),
        label: Strings.accountNumber,
        value: _accountFirst,
        hint: draft.accountLast4.isEmpty ? null : 'XXXXXX${draft.accountLast4}',
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
      for (final spec in _schema.section('bank').fields)
        if (spec.key == 'ifsc')
          TextBox(
            key: const ValueKey('bank.ifsc'),
            label: spec.label,
            value: '${draft.section('bank')['ifsc'] ?? ''}',
            error: _errorFor('bank.ifsc'),
            check: _checkOf('bank', 'ifsc'),
            completeLength: _fullLength['bank.ifsc'],
            onChanged: _ifscChanged,
          )
        else
          _field('bank', spec),
    ]);
  }

  Widget _familyStep() {
    final family = _form.draft.family;

    void update(int index, String key, Object value) {
      _changed.add('family');
      final next = [...family];
      next[index] = {...next[index], key: value};
      _form.setFamily(next);
    }

    return _spaced([
      for (final (index, person) in family.indexed)
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(border: Border.all(color: Colors.black12)),
          child: _spaced([
            TextBox(
              key: ValueKey('family.$index.name'),
              label: Strings.name,
              value: '${person['name'] ?? ''}',
              error: _form.serverErrors['family.$index.name'],
              onChanged: (value) => update(index, 'name', value),
            ),
            ChoiceBox(
              label: Strings.gender,
              value: person['gender'] as String?,
              options: _schema.familyGenders,
              retired: _schema.retiredGenders,
              error: _form.serverErrors['family.$index.gender'],
              onChanged: (value) => update(index, 'gender', value),
            ),
            TextBox(
              key: ValueKey('family.$index.age'),
              label: Strings.age,
              value: '${person['age'] ?? ''}',
              keyboard: TextInputType.number,
              error: _form.serverErrors['family.$index.age'],
              check: _checks.familyAge,
              onChanged: (value) => update(index, 'age', value),
            ),
            ChoiceBox(
              label: Strings.relation,
              value: person['relation'] as String?,
              options: _schema.familyRelations,
              retired: _schema.retiredRelations,
              error: _form.serverErrors['family.$index.relation'],
              onChanged: (value) => update(index, 'relation', value),
            ),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: () => _form.setFamily([...family]..removeAt(index)),
                child: const Text(Strings.removePerson),
              ),
            ),
          ]),
        ),
      if (family.length < _schema.maxFamilyMembers)
        OutlinedButton.icon(
          style: OutlinedButton.styleFrom(
            shape: const RoundedRectangleBorder(),
            minimumSize: const Size.fromHeight(52),
          ),
          onPressed: () => _form.setFamily([...family, <String, dynamic>{}]),
          icon: const Icon(Icons.person_add_alt),
          label: const Text(Strings.addPerson),
        ),
    ]);
  }

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
          shape: const RoundedRectangleBorder(),
          icon: const Icon(Icons.warning_amber_rounded, color: Colors.orange),
          title: Text(problem == PhotoProblem.dark ? Strings.photoDark : Strings.photoBlurry),
          content: const Text(Strings.photoHelp),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialog, false),
              child: const Text(Strings.keepAnyway),
            ),
            FilledButton(
              style: FilledButton.styleFrom(shape: const RoundedRectangleBorder()),
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

  Future<void> _sign() async {
    final path = await Navigator.of(
      context,
    ).push<String>(MaterialPageRoute(builder: (_) => const SignaturePadScreen()));
    if (path != null) _attach('member_signature', path);
  }

  Widget _documentRow(String label, String type, {VoidCallback? onTap}) {
    final done = _form.draft.hasDocument(type);
    final error = _form.serverErrors['documents.$type'];
    final doubtful = done && _doubtful.containsKey(type);
    return LiftBox(
      active: false,
      hasError: error != null,
      child: ListTile(
        shape: const RoundedRectangleBorder(),
        leading: Icon(
          doubtful
              ? Icons.warning_amber_rounded
              : done
              ? Icons.check_circle
              : Icons.photo_camera_outlined,
          color: doubtful ? Colors.orange : (done ? Colors.green : null),
        ),
        title: Text(label),
        subtitle: error != null
            ? Text(error)
            : doubtful
            ? const Text(Strings.photoDoubt)
            : null,
        trailing: Text(done ? Strings.retake : Strings.takePhoto),
        onTap: onTap ?? () => _capture(type),
      ),
    );
  }

  Widget _documentsStep() {
    return _spaced([
      _documentRow(Strings.photo, 'photo'),
      _documentRow(Strings.aadhaarFront, 'aadhaar_front'),
      _documentRow(Strings.aadhaarBack, 'aadhaar_back'),
      _documentRow(Strings.passbook, 'passbook'),
      _documentRow(Strings.memberSignature, 'member_signature', onTap: _sign),
      TextButton(
        onPressed: () => _capture('member_thumbprint'),
        child: Text(
          _form.draft.hasDocument('member_thumbprint') ? Strings.thumbprint : Strings.cannotWrite,
        ),
      ),
    ]);
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
    if (!draft.hasAadhaar) missing.add((Strings.aadhaarNumber, 0));
    if (!draft.hasAccount) missing.add((Strings.accountNumber, 3));
    // A mobile number, and an email when given, go in only once confirmed by OTP.
    final address = draft.section('address');
    if ('${address['mobile'] ?? ''}'.trim().isNotEmpty && !draft.mobileVerified) {
      missing.add((Strings.mobileNotVerified, 1));
    }
    if ('${address['email'] ?? ''}'.trim().isNotEmpty && !draft.emailVerified) {
      missing.add((Strings.emailNotVerified, 1));
    }
    for (final (type, label) in const [
      ('photo', Strings.photo),
      ('aadhaar_front', Strings.aadhaarFront),
      ('aadhaar_back', Strings.aadhaarBack),
      ('passbook', Strings.passbook),
    ]) {
      if (!draft.hasDocument(type)) missing.add((label, 6));
    }
    if (!draft.hasDocument('member_signature') && !draft.hasDocument('member_thumbprint')) {
      missing.add((Strings.memberSignature, 6));
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
        shape: const RoundedRectangleBorder(),
        title: const Text(Strings.submitted),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialog), child: const Text(Strings.done)),
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
    for (final candidate in _schema.sections.where((item) => item.key == section)) {
      for (final spec in candidate.fields.where((field) => field.key == key)) {
        return spec.label;
      }
    }
    return path;
  }

  /// What the server would refuse, found on the phone, with the step it is on.
  List<(String, String, int)> _problems() {
    final problems = [
      if (_aadhaarProblem != null) ('applicant.aadhaar_number', _aadhaarProblem!, 0),
      for (final MapEntry(key: path, value: message) in _checks.all(_form.draft.data).entries)
        if (!_form.serverErrors.containsKey(path)) (path, message, _stepOf(path)),
      if (_accountProblem != null) ('bank.account_number', _accountProblem!, 3),
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

  /// Every step at a glance: done, or how much is left, one tap from fixing it.
  Widget _checklist(List<(String, int)> missing) {
    final left = <int, int>{};
    for (final (_, step) in missing) {
      left[step] = (left[step] ?? 0) + 1;
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(Strings.checklist, style: TextStyle(fontWeight: FontWeight.w600)),
        for (var step = 0; step < _steps.length - 1; step++)
          ListTile(
            key: ValueKey('checklist.$step'),
            dense: true,
            contentPadding: EdgeInsets.zero,
            leading: Icon(
              left.containsKey(step) ? Icons.error_outline : Icons.check_circle,
              color: left.containsKey(step) ? Colors.orange.shade800 : Colors.green,
            ),
            title: Text('${step + 1}. ${_steps[step].title}'),
            trailing: Text(
              left.containsKey(step) ? '${left[step]} ${Strings.stepLeft}' : Strings.stepDone,
            ),
            onTap: () => setState(() => _index = step),
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
                onTap: () => setState(() => _index = _stepOf(path)),
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
                    onTap: () => setState(() => _index = step),
                  ),
              ],
            ),
          ),
        ),
      _checklist([...missing, for (final (path, _, step) in problems) (path, step)]),
      for (final type in doubtful)
        ListTile(
          dense: true,
          contentPadding: EdgeInsets.zero,
          leading: const Icon(Icons.warning_amber_rounded, color: Colors.orange),
          title: Text(_documentLabels[type] ?? type),
          subtitle: const Text(Strings.photoDoubt),
          trailing: const Icon(Icons.chevron_right),
          onTap: () => setState(() => _index = 6),
        ),
      if (missing.isEmpty)
        const Text(Strings.allFilled)
      else ...[
        const Text(Strings.stillNeeded, style: TextStyle(fontWeight: FontWeight.w600)),
        for (final (label, step) in missing)
          ListTile(
            dense: true,
            contentPadding: EdgeInsets.zero,
            title: Text(label),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => setState(() => _index = step),
          ),
      ],
      FilledButton(
        style: FilledButton.styleFrom(
          shape: const RoundedRectangleBorder(),
          minimumSize: const Size.fromHeight(52),
        ),
        onPressed: missing.isEmpty ? _submit : null,
        child: const Text(Strings.submit),
      ),
    ]);
  }

  Widget _currentStep() => switch (_index) {
    4 => _familyStep(),
    6 => _documentsStep(),
    8 => _reviewStep(),
    _ => _steps[_index].build(),
  };

  Widget _syncBar() {
    final (text, color) = switch (_form.state) {
      SyncState.saved => (Strings.saved, Colors.green.shade700),
      SyncState.saving => (Strings.saving, Colors.black54),
      SyncState.offline => (Strings.offline, Colors.orange.shade800),
      SyncState.conflict => (Strings.conflict, Colors.red.shade700),
      SyncState.failed => (Strings.syncFailed, Colors.red.shade700),
    };
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: Row(
        children: [
          Expanded(
            child: Text(text, style: TextStyle(color: color, fontSize: 13)),
          ),
          if (_form.state == SyncState.conflict)
            TextButton(onPressed: _form.reloadFromServer, child: const Text(Strings.useServerCopy)),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final draft = _form.draft;
    return Scaffold(
      appBar: AppBar(
        title: Text(_steps[_index].title),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(4),
          child: LinearProgressIndicator(value: (_index + 1) / _steps.length),
        ),
      ),
      body: SafeArea(
        child: Column(
          children: [
            _syncBar(),
            if (draft.rejectionReason.isNotEmpty)
              Container(
                width: double.infinity,
                margin: const EdgeInsets.symmetric(horizontal: 16),
                padding: const EdgeInsets.all(12),
                color: Colors.red.shade50,
                child: Text('${Strings.rejectedBecause}: ${draft.rejectionReason}'),
              ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  Text(
                    '${Strings.step} ${_index + 1} / ${_steps.length}',
                    style: const TextStyle(color: Colors.black54),
                  ),
                  const SizedBox(height: 12),
                  _currentStep(),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  if (_index > 0)
                    Expanded(
                      child: OutlinedButton(
                        style: OutlinedButton.styleFrom(
                          shape: const RoundedRectangleBorder(),
                          minimumSize: const Size.fromHeight(52),
                        ),
                        onPressed: () => setState(() => _index--),
                        child: const Text(Strings.back),
                      ),
                    ),
                  if (_index > 0 && _index < _steps.length - 1) const SizedBox(width: 12),
                  if (_index < _steps.length - 1)
                    Expanded(
                      child: FilledButton(
                        style: FilledButton.styleFrom(
                          shape: const RoundedRectangleBorder(),
                          minimumSize: const Size.fromHeight(52),
                        ),
                        onPressed: () => setState(() => _index++),
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
