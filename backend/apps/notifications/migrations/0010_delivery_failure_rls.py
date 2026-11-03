from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("notifications", "0009_delivery_failure")]

    operations = [enable_rls("notification_delivery_failure")]
