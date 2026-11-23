from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("suivi", "0044_propositions_referentiels")]

    operations = [
        migrations.AddField(
            model_name="ecole",
            name="catalogues_referentiels",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
