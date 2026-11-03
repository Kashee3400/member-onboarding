import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:member_onboarding/member_onboarding.dart';
import 'package:member_onboarding/src/api/api_client.dart';
import 'package:member_onboarding/src/api/onboarding_api.dart';
import 'package:member_onboarding/src/ui/my_records.dart';
import 'package:member_onboarding/src/ui/strings.dart';

class RecordsApi extends OnboardingApi {
  RecordsApi()
    : super(
        ApiClient(
          MemberOnboardingConfig(baseUrl: 'https://x.test', assertionProvider: () async => ''),
        ),
      );

  final asked = <String>[];
  bool online = true;

  @override
  Future<RecordPage> fetchRecords({
    required DateTime from,
    required DateTime to,
    String? status,
    int page = 1,
  }) async {
    if (!online) throw const OfflineException();
    asked.add('${from.day}-${to.day}-$status-$page');
    final all = [
      for (var i = 0; i < 35; i++)
        ApplicationSummary(
          id: 'a$i',
          status: i == 0 ? 'rejected' : 'pending_am',
          statusLabel: i == 0 ? 'Rejected' : 'Pending Area Manager',
          applicantName: 'Member $i',
          mppCode: '1305',
          formNumber: 'A0000$i',
          createdAt: DateTime(2026, 11, 2),
        ),
    ];
    final items = status == 'rejected'
        ? all.take(1).toList()
        : all.skip((page - 1) * 30).take(30).toList();
    return RecordPage(items, status == 'rejected' ? 1 : all.length);
  }

  @override
  Future<RecordSummary> fetchSummary({required DateTime from, required DateTime to}) async =>
      const RecordSummary(started: 35, submitted: 34, pending: 33, approved: 0, rejected: 1);
}

// The page itself, not the rows of chips that scroll sideways inside it.
final list = find.byType(Scrollable).first;

Widget screen(RecordsApi api, {Future<void> Function(ApplicationSummary)? onOpen}) => MaterialApp(
  home: MyRecordsScreen(api: api, onOpen: onOpen),
);

void main() {
  testWidgets('shows the counts and the first page of forms', (tester) async {
    final api = RecordsApi();

    await tester.pumpWidget(screen(api));
    await tester.pumpAndSettle();

    expect(find.text('35'), findsOneWidget);
    expect(find.text('Member 0'), findsOneWidget);
    await tester.scrollUntilVisible(find.text(Strings.showMore), 300, scrollable: list);
    expect(find.text(Strings.showMore), findsOneWidget);
  });

  testWidgets('show more fetches the next page', (tester) async {
    final api = RecordsApi();
    await tester.pumpWidget(screen(api));
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(find.text(Strings.showMore), 300, scrollable: list);
    await tester.tap(find.text(Strings.showMore));
    await tester.pumpAndSettle();

    expect(api.asked.last.endsWith('-2'), isTrue);
    expect(find.text(Strings.showMore), findsNothing);
  });

  testWidgets('a status filter asks again', (tester) async {
    final api = RecordsApi();
    await tester.pumpWidget(screen(api));
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.text(Strings.returned).last);
    await tester.tap(find.text(Strings.returned).last);
    await tester.pumpAndSettle();

    expect(api.asked.last.contains('-rejected-'), isTrue);
    expect(find.text('Member 1'), findsNothing);
  });

  testWidgets('a form sent back opens for correction', (tester) async {
    final api = RecordsApi();
    ApplicationSummary? opened;
    await tester.pumpWidget(screen(api, onOpen: (item) async => opened = item));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Member 0'));
    await tester.pumpAndSettle();

    expect(opened?.id, 'a0');
  });

  testWidgets('without a network it says so', (tester) async {
    final api = RecordsApi()..online = false;

    await tester.pumpWidget(screen(api));
    await tester.pumpAndSettle();

    expect(find.text(Strings.recordsNeedNetwork), findsOneWidget);
  });
}
