from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("applications", "0007_legacymember")]

    operations = [enable_rls("member_legacy")]
