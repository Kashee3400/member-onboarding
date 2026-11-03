import 'package:flutter/material.dart';
import 'package:member_onboarding/member_onboarding.dart';

import 'src/session.dart';
import 'src/sign_in_api.dart';
import 'src/sign_in_screen.dart';

/// The service this build talks to: `--dart-define=MEMBER_ONBOARDING_URL=...`.
const serviceUrl = String.fromEnvironment(
  'MEMBER_ONBOARDING_URL',
  defaultValue: 'https://support.kasheemilk.com',
);

const _fallbackColor = Color(0xFF0F6CBD);

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final session = Session(baseUrl: serviceUrl);
  await session.restore();
  runApp(MemberFormsApp(session: session));
}

/// For organizations with no app of their own: field staff sign in with their
/// mobile number and a code by SMS, then fill member forms exactly as in an app
/// that embeds the package.
class MemberFormsApp extends StatefulWidget {
  const MemberFormsApp({required this.session, this.api, super.key});

  final Session session;
  final SignInApi? api;

  @override
  State<MemberFormsApp> createState() => _MemberFormsAppState();
}

class _MemberFormsAppState extends State<MemberFormsApp> {
  late final SignInApi _api = widget.api ?? SignInApi(widget.session);
  Color _color = _fallbackColor;
  String? _colorFor;

  @override
  void initState() {
    super.initState();
    widget.session.addListener(_changed);
    _loadColor();
  }

  @override
  void dispose() {
    widget.session.removeListener(_changed);
    super.dispose();
  }

  void _changed() {
    setState(() {});
    _loadColor();
  }

  Future<void> _loadColor() async {
    final slug = widget.session.organizationSlug;
    if (slug == null || slug == _colorFor) return;
    _colorFor = slug;
    final hex = await _api.primaryColor(slug);
    final parsed = hex == null ? null : int.tryParse(hex.replaceFirst('#', ''), radix: 16);
    if (mounted && parsed != null) setState(() => _color = Color(0xFF000000 | parsed));
  }

  @override
  Widget build(BuildContext context) {
    final session = widget.session;
    return MaterialApp(
      title: 'Member Forms',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(colorSchemeSeed: _color, useMaterial3: true),
      home: session.signedIn
          ? MemberOnboardingScreen(
              // A new screen per organization, so nothing carries over between them.
              key: ValueKey(session.organizationSlug),
              config: MemberOnboardingConfig(
                baseUrl: serviceUrl,
                accessTokenProvider: session.accessToken,
                primaryColor: _color,
              ),
              onSignOut: () => _confirmSignOut(context),
            )
          : SignInScreen(api: _api),
    );
  }

  Future<void> _confirmSignOut(BuildContext context) async {
    final navigator = Navigator.of(context, rootNavigator: true);
    final yes = await showDialog<bool>(
      context: navigator.context,
      builder: (dialog) => AlertDialog(
        title: const Text('Sign out?'),
        content: const Text(
          'Forms not sent yet stay on this phone and are there when you sign in again.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialog, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(dialog, true), child: const Text('Sign out')),
        ],
      ),
    );
    if (yes ?? false) await widget.session.signOut();
  }
}
