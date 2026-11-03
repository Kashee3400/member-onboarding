import 'package:flutter/material.dart';

/// What a host app supplies. Everything else is handled inside the package.
class MemberOnboardingConfig {
  const MemberOnboardingConfig({
    required this.baseUrl,
    required this.assertionProvider,
    this.primaryColor = const Color(0xFF0F6CBD),
    this.pushTokenProvider,
  });

  /// The onboarding service, for example `https://onboarding.example.com`.
  final String baseUrl;

  /// Returns a fresh signed assertion from the host's own backend.
  ///
  /// This is the only link to the host's login. The package calls it whenever
  /// it needs access, so signing out of the host ends access here too.
  final Future<String> Function() assertionProvider;

  final Color primaryColor;

  /// The phone's push token (FCM), so a form sent back reaches it as a notification.
  /// Null when the host app has no push.
  final Future<String?> Function()? pushTokenProvider;
}
