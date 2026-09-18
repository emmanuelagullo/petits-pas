from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("suivi", "0006_parametres_attendus_sous_domaines")]

    operations = [
        migrations.CreateModel(
            name="FormulationProposee",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=30)),
                ("texte", models.TextField(help_text="Utiliser {prenom} à l'endroit où insérer le prénom de l'enfant.")),
                ("ordre", models.PositiveSmallIntegerField(default=0)),
                ("active", models.BooleanField(default=True)),
                ("competence", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="formulations", to="suivi.competence")),
            ],
            options={"ordering": ["ordre", "pk"]},
        ),
        migrations.AddConstraint(
            model_name="formulationproposee",
            constraint=models.UniqueConstraint(fields=("competence", "code"), name="formulation_unique_par_competence"),
        ),
    ]
