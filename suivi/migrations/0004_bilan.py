import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("suivi", "0003_modele_longitudinal")]

    operations = [
        migrations.CreateModel(
            name="Bilan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date_bilan", models.DateField()),
                ("texte", models.TextField()),
                ("cree_le", models.DateTimeField(auto_now_add=True)),
                ("modifie_le", models.DateTimeField(auto_now=True)),
                ("scolarite", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bilans", to="suivi.scolarite")),
            ],
            options={"ordering": ["date_bilan", "pk"]},
        ),
        migrations.AddConstraint(
            model_name="bilan",
            constraint=models.UniqueConstraint(fields=("scolarite", "date_bilan"), name="bilan_unique_par_scolarite_date"),
        ),
    ]
