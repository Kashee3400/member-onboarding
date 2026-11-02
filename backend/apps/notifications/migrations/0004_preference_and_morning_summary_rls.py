from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("notifications", "0003_preference_and_morning_summary")]

    operations = [
        enable_rls("notification_preference"),
        enable_rls("notification_morning_summary"),
    ]
