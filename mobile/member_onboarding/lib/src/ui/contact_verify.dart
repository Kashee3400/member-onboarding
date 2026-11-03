import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../sync/draft_controller.dart';
import 'strings.dart';

/// Proves the member's mobile number or email: send a code, ask the member for it,
/// type it in. Shown under the address, beside what it proves.
class ContactVerify extends StatefulWidget {
  const ContactVerify({required this.controller, required this.channel, super.key});

  final DraftController controller;

  /// "mobile" or "email".
  final String channel;

  @override
  State<ContactVerify> createState() => _ContactVerifyState();
}

class _ContactVerifyState extends State<ContactVerify> {
  static const _wait = 30;

  final _code = TextEditingController();
  bool _sent = false;
  bool _busy = false;
  String? _problem;
  int _left = 0;
  Timer? _ticker;

  bool get _mobile => widget.channel == 'mobile';

  @override
  void dispose() {
    _ticker?.cancel();
    _code.dispose();
    super.dispose();
  }

  void _countDown() {
    _ticker?.cancel();
    setState(() => _left = _wait);
    _ticker = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted || _left <= 1) {
        timer.cancel();
        if (mounted) setState(() => _left = 0);
        return;
      }
      setState(() => _left--);
    });
  }

  Future<void> _send() async {
    setState(() {
      _busy = true;
      _problem = null;
    });
    final problem = await widget.controller.sendOtp(widget.channel);
    if (!mounted) return;
    setState(() {
      _busy = false;
      _problem = problem;
      if (problem == null) {
        _sent = true;
        _code.clear();
      }
    });
    if (problem == null) _countDown();
  }

  Future<void> _check() async {
    setState(() {
      _busy = true;
      _problem = null;
    });
    final problem = await widget.controller.verifyOtp(widget.channel, _code.text);
    if (!mounted) return;
    setState(() {
      _busy = false;
      _problem = problem;
      if (problem == null) _sent = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final draft = widget.controller.draft;
    final value = '${draft.section('address')[widget.channel] ?? ''}'.trim();
    final verified = _mobile ? draft.mobileVerified : draft.emailVerified;
    final error = Theme.of(context).colorScheme.error;

    return Container(
      key: ValueKey('verify.${widget.channel}'),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: verified ? Colors.green.shade300 : Colors.black12),
        color: verified ? Colors.green.shade50 : null,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  _mobile ? Strings.verifyMobile : Strings.verifyEmail,
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
              ),
              Icon(
                verified ? Icons.check_circle : Icons.cancel_outlined,
                size: 20,
                color: verified ? Colors.green.shade700 : error,
              ),
              const SizedBox(width: 4),
              Text(
                verified ? Strings.verified : Strings.notVerified,
                style: TextStyle(color: verified ? Colors.green.shade700 : error),
              ),
            ],
          ),
          if (!verified) ...[
            const SizedBox(height: 8),
            if (value.isEmpty)
              Text(_mobile ? Strings.enterMobileFirst : Strings.enterEmailFirst)
            else ...[
              if (_sent) ...[
                Text(_mobile ? Strings.otpSent : Strings.otpSentEmail),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        key: ValueKey('otp.${widget.channel}'),
                        controller: _code,
                        keyboardType: TextInputType.number,
                        autofillHints: const [AutofillHints.oneTimeCode],
                        inputFormatters: [
                          FilteringTextInputFormatter.digitsOnly,
                          LengthLimitingTextInputFormatter(6),
                        ],
                        decoration: const InputDecoration(
                          labelText: Strings.otpCode,
                          border: OutlineInputBorder(borderRadius: BorderRadius.zero),
                        ),
                        onChanged: (_) => setState(() {}),
                      ),
                    ),
                    const SizedBox(width: 8),
                    FilledButton(
                      style: FilledButton.styleFrom(
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                        minimumSize: const Size(96, 52),
                      ),
                      onPressed: _busy || _code.text.length != 6 ? null : _check,
                      child: const Text(Strings.checkOtp),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
              ],
              Align(
                alignment: Alignment.centerLeft,
                child: OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                  ),
                  onPressed: _busy || _left > 0 ? null : _send,
                  icon: _busy
                      ? const SizedBox.square(
                          dimension: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.sms_outlined),
                  label: Text(
                    _left > 0
                        ? '${Strings.resendIn} ($_left)'
                        : _sent
                        ? Strings.resendOtp
                        : Strings.sendOtp,
                  ),
                ),
              ),
            ],
          ],
          if (_problem != null) ...[
            const SizedBox(height: 6),
            Text(_problem!, style: TextStyle(color: error)),
          ],
        ],
      ),
    );
  }
}
