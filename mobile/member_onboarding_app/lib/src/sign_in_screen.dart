import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'sign_in_api.dart';

/// Mobile number, then the code sent to it, then (rarely) which organization.
class SignInScreen extends StatefulWidget {
  const SignInScreen({required this.api, super.key});

  final SignInApi api;

  @override
  State<SignInScreen> createState() => _SignInScreenState();
}

enum _Step { mobile, code, organization }

class _SignInScreenState extends State<SignInScreen> {
  static const _resendAfter = 30;

  final _mobile = TextEditingController();
  final _code = TextEditingController();
  var _step = _Step.mobile;
  String? _challenge;
  String? _error;
  var _busy = false;
  var _wait = 0;
  Timer? _timer;
  List<OrganizationChoice> _choices = const [];

  @override
  void dispose() {
    _timer?.cancel();
    _mobile.dispose();
    _code.dispose();
    super.dispose();
  }

  bool get _mobileValid => RegExp(r'^[6-9]\d{9}$').hasMatch(_mobile.text);

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
    } on SignInFailed catch (failure) {
      if (mounted) setState(() => _error = failure.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _countDown() {
    _timer?.cancel();
    setState(() => _wait = _resendAfter);
    _timer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted || _wait <= 1) {
        timer.cancel();
        if (mounted) setState(() => _wait = 0);
        return;
      }
      setState(() => _wait--);
    });
  }

  Future<void> _sendCode() => _run(() async {
    _challenge = await widget.api.sendCode(_mobile.text);
    _code.clear();
    _countDown();
    setState(() => _step = _Step.code);
  });

  Future<void> _verify({String organization = ''}) => _run(() async {
    final result = await widget.api.verify(
      _challenge!,
      _code.text,
      organization: organization,
    );
    if (result.needsChoice) {
      setState(() {
        _choices = result.choices;
        _step = _Step.organization;
      });
    }
    // Signed in: the session notifies the app, which opens the forms.
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Icon(Icons.assignment_ind_rounded, size: 56, color: theme.colorScheme.primary),
                  const SizedBox(height: 16),
                  Text(
                    'Member Forms',
                    textAlign: TextAlign.center,
                    style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    switch (_step) {
                      _Step.mobile => 'Sign in with the mobile number your office registered.',
                      _Step.code => 'Enter the 6 digit code sent to ${_mobile.text}.',
                      _Step.organization => 'This number works for more than one company. Choose one.',
                    },
                    textAlign: TextAlign.center,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 28),
                  ...switch (_step) {
                    _Step.mobile => _mobileStep(),
                    _Step.code => _codeStep(),
                    _Step.organization => _organizationStep(),
                  },
                  if (_error case final error?) ...[
                    const SizedBox(height: 16),
                    Text(
                      error,
                      key: const ValueKey('sign-in.error'),
                      textAlign: TextAlign.center,
                      style: TextStyle(color: theme.colorScheme.error),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  List<Widget> _mobileStep() => [
    TextField(
      key: const ValueKey('sign-in.mobile'),
      controller: _mobile,
      autofocus: true,
      keyboardType: TextInputType.phone,
      inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(10)],
      decoration: const InputDecoration(
        labelText: 'Mobile number',
        prefixText: '+91 ',
        border: OutlineInputBorder(borderRadius: BorderRadius.zero),
      ),
      onChanged: (_) => setState(() {}),
      onSubmitted: (_) => _mobileValid && !_busy ? _sendCode() : null,
    ),
    const SizedBox(height: 16),
    FilledButton(
      key: const ValueKey('sign-in.send'),
      onPressed: _mobileValid && !_busy ? _sendCode : null,
      child: Text(_busy ? 'Sending…' : 'Send code'),
    ),
  ];

  List<Widget> _codeStep() => [
    TextField(
      key: const ValueKey('sign-in.code'),
      controller: _code,
      autofocus: true,
      keyboardType: TextInputType.number,
      textAlign: TextAlign.center,
      style: const TextStyle(fontSize: 24, letterSpacing: 8),
      inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(6)],
      autofillHints: const [AutofillHints.oneTimeCode],
      decoration: const InputDecoration(border: OutlineInputBorder(borderRadius: BorderRadius.zero)),
      onChanged: (value) {
        setState(() {});
        if (value.length == 6 && !_busy) _verify();
      },
    ),
    const SizedBox(height: 16),
    FilledButton(
      key: const ValueKey('sign-in.verify'),
      onPressed: _code.text.length == 6 && !_busy ? _verify : null,
      child: Text(_busy ? 'Checking…' : 'Sign in'),
    ),
    const SizedBox(height: 8),
    // Wraps on narrow phones and with large text, rather than running off the edge.
    Wrap(
      alignment: WrapAlignment.spaceBetween,
      children: [
        TextButton(
          onPressed: _busy ? null : () => setState(() => _step = _Step.mobile),
          child: const Text('Change number'),
        ),
        TextButton(
          onPressed: _busy || _wait > 0 ? null : _sendCode,
          child: Text(_wait > 0 ? 'Send again in $_wait s' : 'Send again'),
        ),
      ],
    ),
  ];

  List<Widget> _organizationStep() => [
    for (final choice in _choices)
      Card(
        margin: const EdgeInsets.only(bottom: 8),
        child: ListTile(
          key: ValueKey('sign-in.organization.${choice.slug}'),
          title: Text(choice.name),
          trailing: const Icon(Icons.chevron_right),
          enabled: !_busy,
          onTap: () => _verify(organization: choice.slug),
        ),
      ),
  ];
}
