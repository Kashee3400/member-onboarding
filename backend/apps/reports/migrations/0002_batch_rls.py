from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("reports", "0001_initial")]

    operations = [enable_rls("report_pdf_batch")]
