from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("applications", "0012_legacymember_full_name_legacymember_mpp_and_more")]

    operations = [enable_rls("application_step_approval")]
