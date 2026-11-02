import 'package:flutter/material.dart';

/// What a host app supplies. Everything else is handled inside the package.
class MemberOnboardingConfig {
  const MemberOnboardingConfig({
    required this.baseUrl,
    required this.assertionProvider,
    this.primaryColor = const Color(0xFF0F6CBD),
  });

  /// The onboarding service, for example `https://onboarding.example.com`.
  final String baseUrl;

  /// Returns a fresh signed assertion from the host's own backend.
  ///
  /// This is the only link to the host's login. The package calls it whenever
  /// it needs access, so signing out of the host ends access here too.
  final Future<String> Function() assertionProvider;

  final Color primaryColor;
}
