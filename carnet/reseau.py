"""Adresse IP du client, y compris derrière des reverse-proxys de confiance.

Par défaut (CARNET_PROXYS_NB=0), seule REMOTE_ADDR est lue : un client ne peut
pas usurper son adresse avec un en-tête X-Forwarded-For. Derrière N proxys
dont on sait qu'ils ajoutent chacun l'adresse de leur interlocuteur à la fin
de X-Forwarded-For, le client réel est la N-ième entrée en partant de la
droite. Les entrées à gauche (que le client peut forger) sont ignorées.

N doit être exactement le nombre de proxys de confiance. Trop petit : on lit
l'adresse d'un proxy (moins de finesse, sans danger). Trop grand : on lit une
entrée que le client a pu forger en préfixant l'en-tête, et l'adresse
retenue est falsifiable. Seuls les cas manifestement malformés (en-tête plus
court que N, valeur qui n'est pas une adresse IP) retombent sur REMOTE_ADDR.
"""

import ipaddress

from django.conf import settings


def _adresse_valide(valeur):
    try:
        return str(ipaddress.ip_address(valeur.strip()))
    except ValueError:
        return None


def adresse_client(request):
    directe = request.META.get("REMOTE_ADDR", "")
    nombre = settings.PROXYS_DE_CONFIANCE
    if nombre <= 0:
        return directe
    chaine = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
    if len(chaine) < nombre:
        return directe
    return _adresse_valide(chaine[-nombre]) or directe


def cle_ip(groupe, request):
    """Clé django-ratelimit : même adresse que celle vue par django-axes."""
    return adresse_client(request)
