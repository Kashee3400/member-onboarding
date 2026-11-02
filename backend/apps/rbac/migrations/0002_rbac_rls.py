from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("rbac", "0001_initial")]

    operations = [enable_rls("rbac_role"), enable_rls("rbac_membership_role")]
