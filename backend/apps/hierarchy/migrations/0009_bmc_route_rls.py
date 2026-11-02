from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("hierarchy", "0008_bmc_route_mpp_route_and_more")]

    operations = [enable_rls("hierarchy_bmc"), enable_rls("hierarchy_route")]
