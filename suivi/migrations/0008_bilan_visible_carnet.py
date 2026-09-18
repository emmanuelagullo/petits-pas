from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("suivi", "0007_formulation_proposee")]

    operations = [
        migrations.AddField(
            model_name="bilan",
            name="visible_carnet",
            field=models.BooleanField(default=True),
        ),
    ]
