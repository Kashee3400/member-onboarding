from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("rbac", "0004_staffinvitation")]

    operations = [enable_rls("rbac_staff_invitation")]
