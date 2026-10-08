"""Accueil réel après import : mêmes templates et jetons que l'ouverture d'école."""
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError
from django.core.validators import validate_email
from django.db import connections
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .autorisations import est_direction
from .courriels_comptes import composer_accueil
from .imports_ecole import verifier_serveur
from .models import EvenementAudit


def verifier_courriel(email, url):
    email = (email or '').strip().casefold()
    if not email:
        raise CommandError("Adresse électronique obligatoire avec --email.")
    if not isinstance(url, str) or any(c.isspace() for c in url):
        raise CommandError("--url doit être une origine HTTPS sans espace.")
    try:
        validate_email(email)
        origine = urlsplit(url or '')
        valide = (origine.scheme == 'https' and origine.hostname and not origine.username
                  and not origine.password and origine.path in ('', '/')
                  and not origine.query and not origine.fragment)
        origine.port  # Refuser aussi les ports mal formés.
    except (ValidationError, ValueError):
        raise CommandError("Adresse électronique ou origine HTTPS invalide.") from None
    if not valide:
        raise CommandError("--url doit être une origine HTTPS sans chemin ni identifiants.")
    if not settings.EMAIL_DISPONIBLE or settings.EMAIL_BACKEND in (
            'django.core.mail.backends.console.EmailBackend',
            'django.core.mail.backends.filebased.EmailBackend',
            'django.core.mail.backends.dummy.EmailBackend'):
        raise CommandError("Courrier désactivé : aucun envoi ni création de compte par courriel.")
    return email


def envoyer_accueil_import(*, ecole, direction, operateur, url):
    verifier_serveur()
    # Aucun courriel ne doit annoncer une école encore susceptible de rollback.
    if connections['default'].in_atomic_block:
        raise CommandError("Le courriel doit être envoyé après validation de la transaction d'import.")
    operateur.refresh_from_db()
    direction.refresh_from_db()
    ecole.refresh_from_db()
    if not operateur.is_active or not operateur.is_staff:
        raise CommandError("L'opérateur doit être un compte technique actif.")
    if not est_direction(direction, ecole):
        raise CommandError("Le compte ne dispose plus de la direction active de cette école.")
    if not EvenementAudit.objects.filter(ecole=ecole, action='ecole.import_zip',
            nouvelles_valeurs__direction_id=direction.pk,
            nouvelles_valeurs__direction_creee=True).exists():
        raise CommandError("Ce compte n'a pas été créé comme direction par cet import.")
    if not direction.has_usable_password():
        raise CommandError("Compte sans mot de passe utilisable : aucun lien de récupération envoyé.")
    destinataire = verifier_courriel(direction.email, url)
    lien = url.rstrip('/') + reverse('mot_de_passe_reinitialiser', kwargs={
        'uidb64': urlsafe_base64_encode(force_bytes(direction.pk)),
        'token': default_token_generator.make_token(direction),
    })
    try:
        resultat = composer_accueil(ecole=ecole, compte=direction, lien=lien,
            destinataire=destinataire, apres_import=True).send(fail_silently=False)
        if resultat != 1:
            raise RuntimeError('envoi non confirmé')
    except Exception as erreur:
        EvenementAudit.objects.create(ecole=ecole, acteur=operateur,
            action='ecole.import_accueil_echec', modele=ecole._meta.label_lower, objet_id=str(ecole.pk),
            nouvelles_valeurs={'direction_id': direction.pk, 'erreur': type(erreur).__name__})
        raise CommandError(
            "École importée et compte créés, mais envoi non confirmé. Ne pas réimporter : "
            "utiliser renvoyer_accueil_import, ou Mot de passe oublié sur le site."
        ) from None
    EvenementAudit.objects.create(ecole=ecole, acteur=operateur,
        action='ecole.import_accueil_envoye', modele=ecole._meta.label_lower, objet_id=str(ecole.pk),
        nouvelles_valeurs={'direction_id': direction.pk})
