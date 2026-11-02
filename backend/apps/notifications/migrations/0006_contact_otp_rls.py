from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("notifications", "0005_contact_otp")]

    operations = [enable_rls("notification_contact_otp")]