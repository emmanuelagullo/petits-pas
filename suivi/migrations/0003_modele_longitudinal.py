import django.db.models.deletion
from django.db import migrations, models


def creer_scolarites(apps, schema_editor):
    Eleve = apps.get_model("suivi", "Eleve")
    Scolarite = apps.get_model("suivi", "Scolarite")
    for eleve in Eleve.objects.select_related("classe").all().iterator():
        eleve.ecole_id = eleve.classe.ecole_id
        eleve.save(update_fields=["ecole"])
        Scolarite.objects.create(
            eleve_id=eleve.pk,
            classe_id=eleve.classe_id,
            annee_scolaire=eleve.classe.annee_scolaire,
            niveau=eleve.niveau,
        )


class Migration(migrations.Migration):
    dependencies = [("suivi", "0002_alter_observation_statut")]

    operations = [
        migrations.AddField(
            model_name="eleve",
            name="annee_naissance",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="eleve",
            name="archive_le",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="eleve",
            name="ecole",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="eleves",
                to="suivi.ecole",
            ),
        ),
        migrations.CreateModel(
            name="Scolarite",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("annee_scolaire", models.CharField(max_length=9)),
                ("niveau", models.CharField(choices=[("PS", "Petite section"), ("MS", "Moyenne section"), ("GS", "Grande section")], max_length=2)),
                ("cree_le", models.DateTimeField(auto_now_add=True)),
                ("modifie_le", models.DateTimeField(auto_now=True)),
                ("classe", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="scolarites", to="suivi.classe")),
                ("eleve", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scolarites", to="suivi.eleve")),
            ],
            options={"ordering": ["-annee_scolaire", "eleve__prenom", "eleve__nom"]},
        ),
        migrations.RunPython(creer_scolarites, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="eleve",
            name="ecole",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="eleves", to="suivi.ecole"),
        ),
        migrations.RemoveField(model_name="eleve", name="classe"),
        migrations.RemoveField(model_name="eleve", name="niveau"),
        migrations.AddConstraint(
            model_name="classe",
            constraint=models.UniqueConstraint(fields=("ecole", "annee_scolaire", "nom"), name="classe_unique_par_ecole_annee_nom"),
        ),
        migrations.AddConstraint(
            model_name="scolarite",
            constraint=models.UniqueConstraint(fields=("eleve", "annee_scolaire"), name="scolarite_unique_par_eleve_annee"),
        ),
        migrations.AddIndex(
            model_name="scolarite",
            index=models.Index(fields=["classe", "niveau"], name="suivi_scola_classe__b283c1_idx"),
        ),
    ]
