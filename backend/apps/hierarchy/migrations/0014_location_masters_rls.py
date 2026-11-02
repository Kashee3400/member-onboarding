from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("hierarchy", "0013_location_masters")]

    operations = [
        enable_rls("hierarchy_state"),
        enable_rls("hierarchy_district"),
        enable_rls("hierarchy_tehsil"),
        enable_rls("hierarchy_village"),
        enable_rls("hierarchy_hamlet"),
    ]
