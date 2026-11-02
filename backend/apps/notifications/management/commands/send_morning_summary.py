from django.core.management.base import BaseCommand

from apps.notifications.summary import send_morning_summaries


class Command(BaseCommand):
    help = (
        "Tell each approver how many forms wait for them. Safe to run twice in a day: "
        "nobody gets a second summary. Celery beat runs it at 9:00; cron can too."
    )

    def handle(self, *args, **options):
        sent = send_morning_summaries()
        self.stdout.write(f"Sent {sent} morning summaries")
