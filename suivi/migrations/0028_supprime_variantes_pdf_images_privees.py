from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("suivi", "0027_variantes_pdf_images_privees")]

    operations = [
        migrations.RemoveField(model_name="reglagepresentation", name="photo_pdf"),
        migrations.RemoveField(model_name="tracecommune", name="photo_pdf"),
        migrations.RemoveField(model_name="trace", name="photo_pdf"),
        migrations.RemoveField(model_name="ressourcereferentiel", name="fichier_pdf"),
    ]
