"""Plafond de longueur des mots de passe.

Très au-dessus de tout mot de passe ou toute phrase de passe réels ; une saisie
plus longue est refusée à la connexion comme à la création.
"""
from django.core.exceptions import ValidationError

LONGUEUR_MAX_MOT_DE_PASSE = 1024


class MaximumLengthValidator:
    def __init__(self, max_length=LONGUEUR_MAX_MOT_DE_PASSE):
        self.max_length = max_length

    def validate(self, password, user=None):
        if len(password) > self.max_length:
            raise ValidationError(
                "Ce mot de passe est trop long (%(max)d caractères au plus).",
                code="password_too_long",
                params={"max": self.max_length},
            )

    def get_help_text(self):
        return f"Votre mot de passe ne peut pas dépasser {self.max_length} caractères."
