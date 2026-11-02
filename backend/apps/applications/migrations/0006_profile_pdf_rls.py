from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("applications", "0005_generatedpdf_organizationprofile")]

    operations = [enable_rls("organization_profile"), enable_rls("application_pdf")]
