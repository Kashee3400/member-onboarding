import 'package:flutter/material.dart';

/// What a host app supplies. Everything else is handled inside the package.
///
/// A host signs its users in one of two ways: its backend vouches for them with
/// an [assertionProvider] (as the ERP does for facilitator2), or the app signs in
/// to this service itself and hands over the [accessTokenProvider] (as the
/// standalone app does, with a code by SMS). Exactly one of the two is given.
class MemberOnboardingConfig {
  const MemberOnboardingConfig({
    required this.baseUrl,
    this.assertionProvider,
    this.accessTokenProvider,
    this.primaryColor = const Color(0xFF0F6CBD),
    this.pushTokenProvider,
  }) : assert(
         (assertionProvider == null) != (accessTokenProvider == null),
         'Give an assertionProvider or an accessTokenProvider, not both.',
       );

  /// The onboarding service, for example `https://onboarding.example.com`.
  final String baseUrl;

  /// Returns a fresh signed assertion from the host's own backend.
  ///
  /// This is the only link to the host's login. The package calls it whenever
  /// it needs access, so signing out of the host ends access here too.
  final Future<String> Function()? assertionProvider;

  /// Returns an access token for this service. [renew] is true when the last one
  /// was refused, so the host should refresh it rather than hand it back again.
  final Future<String> Function({required bool renew})? accessTokenProvider;

  final Color primaryColor;

  /// The phone's push token (FCM), so a form sent back reaches it as a notification.
  /// Null when the host app has no push.
  final Future<String?> Function()? pushTokenProvider;
}
