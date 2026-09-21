from django.contrib.auth.models import AbstractUser
from django.db import models


class Utilisateur(AbstractUser):
    """Identité individuelle Petits Pas.

    ``ecole`` et ``profil_transition`` maintiennent le périmètre fonctionnel
    actuel jusqu'à l'introduction des appartenances et affectations en #A2.
    Ils ne constituent pas le modèle d'autorisation définitif.
    """

    ENSEIGNANT = "enseignant"
    DIRECTION = "direction"
    PROFILS_TRANSITION = [
        (ENSEIGNANT, "Enseignant"),
        (DIRECTION, "Direction"),
    ]

    ecole = models.ForeignKey(
        "suivi.Ecole",
        on_delete=models.PROTECT,
        related_name="utilisateurs_transition",
        blank=True,
        null=True,
    )
    profil_transition = models.CharField(
        max_length=12,
        choices=PROFILS_TRANSITION,
        blank=True,
        help_text="Remplacé par les responsabilités et affectations en #A2.",
    )

    @property
    def est_direction(self):
        return self.profil_transition == self.DIRECTION
