from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("applications", "0018_review_settings_reject_reason")]

    operations = [
        enable_rls("application_review_settings"),
        enable_rls("application_reject_reason"),
    ]
