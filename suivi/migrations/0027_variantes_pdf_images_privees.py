from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("suivi", "0026_politique_double_facteur_ecole")]

    operations = [
        migrations.AddField(
            model_name="reglagepresentation",
            name="photo_pdf",
            field=models.ImageField(
                blank=True, null=True, upload_to="presentation/pdf/%Y/%m/"
            ),
        ),
        migrations.AddField(
            model_name="tracecommune",
            name="photo_pdf",
            field=models.ImageField(
                blank=True, null=True, upload_to="traces/pdf/%Y/%m/"
            ),
        ),
        migrations.AddField(
            model_name="trace",
            name="photo_pdf",
            field=models.ImageField(
                blank=True, null=True, upload_to="traces/pdf/%Y/%m/"
            ),
        ),
        migrations.AddField(
            model_name="ressourcereferentiel",
            name="fichier_pdf",
            field=models.FileField(
                blank=True, null=True, upload_to="referentiels/pdf/%Y/%m/"
            ),
        ),
    ]
