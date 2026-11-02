from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("hierarchy", "0001_initial")]

    operations = [
        enable_rls("hierarchy_plant"),
        enable_rls("hierarchy_mcc"),
        enable_rls("hierarchy_mpp"),
        enable_rls("hierarchy_mpp_assignment"),
    ]
