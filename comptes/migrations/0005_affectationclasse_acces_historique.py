from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("comptes", "0004_alter_utilisateur_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="affectationclasse",
            name="acces_historique",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Autorise explicitement l’accès pédagogique à une classe "
                    "d’une année scolaire passée."
                ),
            ),
        ),
    ]
