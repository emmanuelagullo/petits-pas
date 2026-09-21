from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("suivi", "0008_bilan_visible_carnet")]

    operations = [
        migrations.RemoveField(model_name="ecole", name="mdp_enseignant"),
        migrations.RemoveField(model_name="ecole", name="mdp_direction"),
    ]
