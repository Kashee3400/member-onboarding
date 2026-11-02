import 'package:flutter/material.dart';
import 'package:member_onboarding/member_onboarding.dart';

void main() => runApp(const ExampleHostApp());

/// Stands in for a host such as the facilitator app.
class ExampleHostApp extends StatelessWidget {
  const ExampleHostApp({super.key});

  // A real host calls its own backend here, for the signed-in user.
  Future<String> _assertion() async => const String.fromEnvironment('ASSERTION');

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      home: MemberOnboardingScreen(
        config: MemberOnboardingConfig(
          baseUrl: const String.fromEnvironment('BASE_URL', defaultValue: 'http://10.0.2.2:8000'),
          assertionProvider: _assertion,
        ),
      ),
    );
  }
}
