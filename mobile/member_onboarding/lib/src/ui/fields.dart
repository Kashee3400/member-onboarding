import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/form_schema.dart';
import 'strings.dart';

/// The sharp box of the staff portal: square corners, lifting while in use.
class LiftBox extends StatelessWidget {
  const LiftBox({required this.active, required this.child, this.hasError = false, super.key});

  final bool active;
  final bool hasError;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final primary = Theme.of(context).colorScheme.primary;
    final borderColor = hasError
        ? Theme.of(context).colorScheme.error
        : active
        ? primary
        : const Color(0xFFCBD5E1);

    return AnimatedContainer(
      duration: const Duration(milliseconds: 120),
      curve: Curves.easeOut,
      transform: Matrix4.translationValues(0, active ? -2 : 0, 0),
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: borderColor, width: active ? 1.5 : 1),
        boxShadow: active
            ? [
                BoxShadow(
                  color: primary.withValues(alpha: 0.22),
                  blurRadius: 14,
                  offset: const Offset(0, 6),
                ),
              ]
            : const [],
      ),
      child: Material(type: MaterialType.transparency, child: child),
    );
  }
}

class FieldLabel extends StatelessWidget {
  const FieldLabel(this.label, {this.optional = false, super.key});

  final String label;
  final bool optional;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Text.rich(
        TextSpan(
          text: label,
          style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15),
          children: [
            if (optional)
              const TextSpan(
                text: '  ${Strings.optional}',
                style: TextStyle(fontWeight: FontWeight.w400, fontSize: 12, color: Colors.black54),
              ),
          ],
        ),
      ),
    );
  }
}

class _ErrorLine extends StatelessWidget {
  const _ErrorLine(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Text(text, style: TextStyle(color: Theme.of(context).colorScheme.error, fontSize: 13)),
    );
  }
}

class TextBox extends StatefulWidget {
  const TextBox({
    required this.label,
    required this.value,
    required this.onChanged,
    this.optional = false,
    this.keyboard = TextInputType.text,
    this.error,
    this.obscure = false,
    this.formatters = const [],
    this.hint,
    this.check,
    this.completeLength,
    super.key,
  });

  final String label;
  final String value;
  final ValueChanged<String> onChanged;
  final bool optional;
  final TextInputType keyboard;
  final String? error;
  final bool obscure;
  final List<TextInputFormatter> formatters;
  final String? hint;

  /// The problem with the text, if any. Shown once the box is left, or as soon as the
  /// text reaches [completeLength], never while a value is still being typed.
  final String? Function(String text)? check;
  final int? completeLength;

  @override
  State<TextBox> createState() => _TextBoxState();
}

class _TextBoxState extends State<TextBox> {
  late final _controller = TextEditingController(text: widget.value);
  final _focus = FocusNode();

  @override
  void initState() {
    super.initState();
    _focus.addListener(() => setState(() {}));
  }

  @override
  void didUpdateWidget(TextBox old) {
    super.didUpdateWidget(old);
    // Scanned values arrive from outside, but typing must not move the cursor.
    if (!_focus.hasFocus && widget.value != _controller.text) {
      _controller.text = widget.value;
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    _focus.dispose();
    super.dispose();
  }

  String? get _problem {
    final check = widget.check;
    if (check == null) return null;
    final text = _controller.text;
    final complete = widget.completeLength != null && text.length >= widget.completeLength!;
    return !_focus.hasFocus || complete ? check(text) : null;
  }

  @override
  Widget build(BuildContext context) {
    final error = widget.error ?? _problem;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        FieldLabel(widget.label, optional: widget.optional),
        LiftBox(
          active: _focus.hasFocus,
          hasError: error != null,
          child: TextField(
            controller: _controller,
            focusNode: _focus,
            keyboardType: widget.keyboard,
            obscureText: widget.obscure,
            inputFormatters: widget.formatters,
            onChanged: (text) {
              widget.onChanged(text);
              // The parent may not rebuild for text it does not keep, such as a bad Aadhaar.
              if (widget.check != null) setState(() {});
            },
            style: const TextStyle(fontSize: 16),
            decoration: InputDecoration(
              isDense: true,
              hintText: widget.hint,
              border: InputBorder.none,
              contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
            ),
          ),
        ),
        if (error != null) _ErrorLine(error),
      ],
    );
  }
}

/// Tapped rather than typed, so the whole box behaves as one large target.
class _TapBox extends StatelessWidget {
  const _TapBox({
    required this.label,
    required this.text,
    required this.placeholder,
    required this.icon,
    required this.onTap,
    required this.optional,
    this.error,
  });

  final String label;
  final String? text;
  final String placeholder;
  final IconData icon;
  final VoidCallback onTap;
  final bool optional;
  final String? error;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        FieldLabel(label, optional: optional),
        LiftBox(
          active: false,
          hasError: error != null,
          child: InkWell(
            onTap: onTap,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      text ?? placeholder,
                      style: TextStyle(
                        fontSize: 16,
                        color: text == null ? Colors.black45 : Colors.black87,
                      ),
                    ),
                  ),
                  Icon(icon, color: Colors.black54),
                ],
              ),
            ),
          ),
        ),
        if (error != null) _ErrorLine(error!),
      ],
    );
  }
}

class ChoiceBox extends StatelessWidget {
  const ChoiceBox({
    required this.label,
    required this.value,
    required this.options,
    required this.onChanged,
    this.retired = const [],
    this.optional = false,
    this.error,
    super.key,
  });

  final String label;
  final String? value;
  final List<ChoiceOption> options;

  /// Not offered, but named when the form already holds one.
  final List<ChoiceOption> retired;
  final ValueChanged<String> onChanged;
  final bool optional;
  final String? error;

  Future<void> _pick(BuildContext context) async {
    final picked = await showModalBottomSheet<String>(
      context: context,
      shape: const RoundedRectangleBorder(),
      builder: (sheet) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            for (final option in options)
              ListTile(
                title: Text(option.label),
                trailing: option.value == value ? const Icon(Icons.check) : null,
                onTap: () => Navigator.pop(sheet, option.value),
              ),
          ],
        ),
      ),
    );
    if (picked != null) onChanged(picked);
  }

  @override
  Widget build(BuildContext context) {
    return _TapBox(
      label: label,
      text: choiceLabel(value, options, retired),
      placeholder: Strings.choose,
      icon: Icons.keyboard_arrow_down,
      optional: optional,
      error: error,
      onTap: () => _pick(context),
    );
  }
}

class DateBox extends StatelessWidget {
  const DateBox({
    required this.label,
    required this.value,
    required this.onChanged,
    this.optional = false,
    this.error,
    super.key,
  });

  final String label;

  /// `yyyy-mm-dd`, or null.
  final String? value;
  final ValueChanged<String> onChanged;
  final bool optional;
  final String? error;

  String? get _display {
    final parsed = DateTime.tryParse(value ?? '');
    if (parsed == null) return null;
    final day = parsed.day.toString().padLeft(2, '0');
    final month = parsed.month.toString().padLeft(2, '0');
    return '$day-$month-${parsed.year}';
  }

  Future<void> _pick(BuildContext context) async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      firstDate: DateTime(1920),
      lastDate: now,
      initialDate: DateTime.tryParse(value ?? '') ?? DateTime(now.year - 30),
      // Typing a birth year is far quicker than paging back decades.
      initialEntryMode: DatePickerEntryMode.input,
    );
    if (picked == null) return;
    final month = picked.month.toString().padLeft(2, '0');
    final day = picked.day.toString().padLeft(2, '0');
    onChanged('${picked.year}-$month-$day');
  }

  @override
  Widget build(BuildContext context) {
    return _TapBox(
      label: label,
      text: _display,
      placeholder: 'DD-MM-YYYY',
      icon: Icons.calendar_today_outlined,
      optional: optional,
      error: error,
      onTap: () => _pick(context),
    );
  }
}

class YesBox extends StatelessWidget {
  const YesBox({
    required this.label,
    required this.value,
    required this.onChanged,
    this.error,
    super.key,
  });

  final String label;
  final bool value;
  final ValueChanged<bool> onChanged;
  final String? error;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        CheckboxListTile(
          value: value,
          onChanged: (checked) => onChanged(checked ?? false),
          title: Text(label),
          controlAffinity: ListTileControlAffinity.leading,
          contentPadding: EdgeInsets.zero,
          shape: const RoundedRectangleBorder(),
        ),
        if (error != null) _ErrorLine(error!),
      ],
    );
  }
}

/// A value the MPP fills: shown greyed with a lock, and never editable.
class LockedBox extends StatelessWidget {
  const LockedBox({required this.label, required this.value, super.key});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      readOnly: true,
      label: '$label, ${Strings.fromMpp}',
      value: value,
      excludeSemantics: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          FieldLabel(label),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
            decoration: BoxDecoration(
              color: const Color(0xFFF1F5F9),
              border: Border.all(color: const Color(0xFFE2E8F0)),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Text(value, style: const TextStyle(fontSize: 16, color: Colors.black54)),
                ),
                const Icon(Icons.lock_outline, size: 16, color: Colors.black45),
                const SizedBox(width: 4),
                const Text(Strings.fromMpp, style: TextStyle(fontSize: 12, color: Colors.black45)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
