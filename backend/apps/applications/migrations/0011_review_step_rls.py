from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("applications", "0010_reviewstepaccess")]

    operations = [enable_rls("application_review_step")]
