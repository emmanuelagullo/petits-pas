import uuid

from django.db import migrations, models
from django.db.models import OuterRef, Subquery


def reprendre_identifiants(apps, schema_editor):
    classe = apps.get_model("suivi", "Classe")
    partage = apps.get_model("suivi", "PartageGristClasse")
    alias = schema_editor.connection.alias
    identifiants = partage.objects.using(alias).filter(classe_id=OuterRef("pk")).values("identifiant")
    classe.objects.using(alias).update(identifiant_publication=Subquery(identifiants[:1]))


class Migration(migrations.Migration):
    dependencies = [("suivi", "0061_partage_grist_index_catalogue")]

    operations = [
        migrations.AddField(model_name="classe", name="identifiant_publication",
                            field=models.UUIDField(null=True, editable=False)),
        migrations.RunPython(reprendre_identifiants, migrations.RunPython.noop),
        migrations.AlterField(model_name="classe", name="identifiant_publication",
                             field=models.UUIDField(default=uuid.uuid4, null=True, editable=False)),
    ]
