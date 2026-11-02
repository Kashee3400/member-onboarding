from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("applications", "0008_legacy_member_rls")]

    operations = [
        migrations.RenameField(
            model_name="membercodesettings", old_name="series", new_name="state_code"
        ),
        migrations.RenameField(
            model_name="membercodesettings", old_name="segment", new_name="hamlet_code"
        ),
    ]
