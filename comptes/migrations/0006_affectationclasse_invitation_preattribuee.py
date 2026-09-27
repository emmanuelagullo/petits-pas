# Rendre appartenance optionnelle : une affectation peut être pré-attribuée
# à une invitation en attente d'acceptation.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('comptes', '0005_affectationclasse_acces_historique'),
        ('suivi', '0012_demanderapprochementeleve_accesparcourseleve'),
    ]

    operations = [
        migrations.AddField(
            model_name='affectationclasse',
            name='invitation',
            field=models.ForeignKey(blank=True, help_text="Pré-attribution le temps que la personne invitée crée son compte ; appartenance est renseignée dès l'acceptation.", null=True, on_delete=django.db.models.deletion.PROTECT, related_name='affectations_classes', to='comptes.invitation'),
        ),
        migrations.AlterField(
            model_name='affectationclasse',
            name='appartenance',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='affectations_classes', to='comptes.appartenanceecole'),
        ),
        migrations.AddConstraint(
            model_name='affectationclasse',
            constraint=models.CheckConstraint(condition=models.Q(('appartenance__isnull', False), ('invitation__isnull', False), _connector='OR'), name='affectationclasse_appartenance_ou_invitation'),
        ),
    ]
