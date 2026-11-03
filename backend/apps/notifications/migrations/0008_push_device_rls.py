from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("notifications", "0007_push_device")]

    operations = [enable_rls("notification_push_device")]