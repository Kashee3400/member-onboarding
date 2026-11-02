from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("hierarchy", "0011_mcc_cover")]

    operations = [enable_rls("hierarchy_mcc_cover")]
