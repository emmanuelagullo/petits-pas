import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models
from django.db.models import Q


def migrer_traces(apps, schema_editor):
    Observation = apps.get_model("suivi", "Observation")
    Scolarite = apps.get_model("suivi", "Scolarite")
    Trace = apps.get_model("suivi", "Trace")
    observations = Observation.objects.filter(
        Q(commentaire__isnull=False) & ~Q(commentaire="")
        | Q(photo__isnull=False) & ~Q(photo="")
    )
    for observation in observations.iterator():
        scolarite = (
            Scolarite.objects.filter(eleve_id=observation.eleve_id)
            .order_by("-annee_scolaire")
            .first()
        )
        if scolarite is None:
            raise RuntimeError(
                "Impossible de migrer une trace sans scolarité pour "
                f"l'observation {observation.pk}."
            )
        Trace.objects.create(
            observation_id=observation.pk,
            scolarite_id=scolarite.pk,
            date_observation=observation.date_observation,
            commentaire=observation.commentaire,
            photo=observation.photo,
            visible_carnet=True,
        )


class Migration(migrations.Migration):
    dependencies = [("suivi", "0004_bilan")]

    operations = [
        migrations.CreateModel(
            name="Trace",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date_observation", models.DateField(default=django.utils.timezone.localdate)),
                ("commentaire", models.TextField(blank=True)),
                ("photo", models.ImageField(blank=True, null=True, upload_to="traces/%Y/%m/")),
                ("visible_carnet", models.BooleanField(default=True)),
                ("cree_le", models.DateTimeField(auto_now_add=True)),
                ("modifie_le", models.DateTimeField(auto_now=True)),
                ("observation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="traces", to="suivi.observation")),
                ("scolarite", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="traces", to="suivi.scolarite")),
            ],
            options={"ordering": ["date_observation", "pk"]},
        ),
        migrations.RunPython(migrer_traces, migrations.RunPython.noop),
        migrations.RemoveField(model_name="observation", name="commentaire"),
        migrations.RemoveField(model_name="observation", name="photo"),
    ]
