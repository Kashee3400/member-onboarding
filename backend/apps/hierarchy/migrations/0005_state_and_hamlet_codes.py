from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("hierarchy", "0004_remove_mpp_unique_mpp_per_village_mpp_segment_and_more")]

    operations = [
        migrations.RemoveConstraint(model_name="mpp", name="unique_mpp_per_village_number"),
        migrations.RenameField(model_name="mpp", old_name="series", new_name="state_code"),
        migrations.RenameField(model_name="mpp", old_name="segment", new_name="hamlet_code"),
        migrations.AddConstraint(
            model_name="mpp",
            constraint=models.UniqueConstraint(
                fields=("organization", "village_code", "hamlet_code"),
                name="unique_mpp_per_village_hamlet",
            ),
        ),
    ]
