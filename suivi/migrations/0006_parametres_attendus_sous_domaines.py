import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("suivi", "0005_trace")]

    operations = [
        migrations.CreateModel(
            name="ParametresCarnet",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titre_couverture", models.CharField(default="Carnet de suivi des apprentissages", max_length=200)),
                ("texte_couverture", models.TextField(blank=True, max_length=400)),
                ("contenu_par_defaut", models.CharField(choices=[("reussites", "Réussites"), ("observes", "Réussites et apprentissages en cours"), ("tout", "Référentiel complet")], default="observes", max_length=10)),
                ("regroupement_par_defaut", models.CharField(choices=[("aucun", "Aucun"), ("annuel", "Annuel"), ("mensuel", "Mensuel"), ("bilan", "Par bilan")], default="aucun", max_length=10)),
                ("colonnes_par_defaut", models.PositiveSmallIntegerField(choices=[(1, "Une colonne"), (2, "Deux colonnes")], default=2)),
                ("afficher_attendus", models.BooleanField(default=False)),
                ("afficher_sous_domaines", models.BooleanField(default=True)),
                ("inclure_bilans", models.BooleanField(default=True)),
                ("ecole", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="parametres_carnet", to="suivi.ecole")),
            ],
        ),
        migrations.CreateModel(
            name="SousDomaine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=30)),
                ("nom", models.CharField(max_length=200)),
                ("ordre", models.PositiveSmallIntegerField(default=0)),
                ("domaine", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sous_domaines", to="suivi.domaine")),
            ],
            options={"ordering": ["ordre", "nom"]},
        ),
        migrations.CreateModel(
            name="Attendu",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=30)),
                ("texte", models.TextField()),
                ("ordre", models.PositiveSmallIntegerField(default=0)),
                ("domaine", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attendus", to="suivi.domaine")),
            ],
            options={"ordering": ["ordre", "pk"]},
        ),
        migrations.AddField(
            model_name="competence",
            name="sous_domaine",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="competences", to="suivi.sousdomaine"),
        ),
        migrations.AddConstraint(
            model_name="sousdomaine",
            constraint=models.UniqueConstraint(fields=("domaine", "code"), name="sous_domaine_unique_par_domaine"),
        ),
        migrations.AddConstraint(
            model_name="attendu",
            constraint=models.UniqueConstraint(fields=("domaine", "code"), name="attendu_unique_par_domaine"),
        ),
    ]
