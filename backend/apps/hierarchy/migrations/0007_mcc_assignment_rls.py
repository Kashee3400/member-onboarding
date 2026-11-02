from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("hierarchy", "0006_alter_mpp_hamlet_code_alter_mpp_state_code_and_more")]

    operations = [enable_rls("hierarchy_mcc_assignment")]
