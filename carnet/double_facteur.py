"""Rangs de fonction et politique du déployeur pour l'authentification à
deux facteurs (2FA).

Les populations forment une échelle ordonnée, de la plus haute à la plus
large. Un niveau de la hiérarchie (le déployeur, puis l'école) pose deux
curseurs :

- « obligatoire jusqu'au rang n » : le 2FA est exigé pour les rangs <= n
  (0 : personne) ;
- « désactivé à partir du rang m » : le 2FA est retiré pour les rangs >= m
  (6 : jamais).

Entre les deux, il est optionnel. Ce module ne dépend d'aucun modèle : il est
lu par settings.py.
"""

from django.core.exceptions import ImproperlyConfigured

AUCUN = 0
DIRECTION = 1
RESPONSABLE = 2
ASSOCIE = 3
CONTRIBUTEUR = 4
SANS_FONCTION = 5
JAMAIS = 6

RANG_MAXIMAL = SANS_FONCTION

# Noms acceptés dans l'environnement, puis libellés affichés.
NOMS_RANGS = {
    "direction": DIRECTION,
    "responsable": RESPONSABLE,
    "associe": ASSOCIE,
    "contributeur": CONTRIBUTEUR,
    "sans_fonction": SANS_FONCTION,
}
LIBELLES_RANGS = {
    DIRECTION: "la direction",
    RESPONSABLE: "les responsables de classe",
    ASSOCIE: "les enseignants associés",
    CONTRIBUTEUR: "les contributeurs",
    SANS_FONCTION: "les personnes sans fonction",
}

VARIABLE_OBLIGATOIRE = "CARNET_2FA_OBLIGATOIRE"
VARIABLE_DESACTIVE = "CARNET_2FA_DESACTIVE_POUR"


def verifier_curseurs(obligatoire, desactive):
    """Lève ValueError si le couple de curseurs est invalide."""
    for valeur in (obligatoire, desactive):
        if type(valeur) is not int:
            raise ValueError("Les rangs doivent être des nombres entiers.")
    if not AUCUN <= obligatoire <= RANG_MAXIMAL:
        raise ValueError("Le rang d'obligation doit être compris entre 0 et 5.")
    if not DIRECTION <= desactive <= JAMAIS:
        raise ValueError("Le rang de désactivation doit être compris entre 1 et 6.")
    if obligatoire >= desactive:
        raise ValueError(
            "Le 2FA ne peut pas être à la fois obligatoire et désactivé pour "
            "une même fonction."
        )


def _lire_rang(environnement, variable, neutre, synonymes):
    brut = (environnement.get(variable) or "").strip().lower()
    if not brut or brut in synonymes:
        return neutre
    if brut == "tous":
        return SANS_FONCTION
    if brut in NOMS_RANGS:
        return NOMS_RANGS[brut]
    valides = ", ".join(sorted(NOMS_RANGS) + sorted(synonymes))
    raise ImproperlyConfigured(
        f"{variable}={brut!r} n'est pas une valeur reconnue. Valeurs "
        f"possibles : {valides}, tous."
    )


def politique_deployeur_depuis_environnement(environnement, *, mode_local=False):
    """Retourne (obligatoire_jusqu_au_rang, desactive_a_partir_du_rang).

    Absentes, les variables laissent le 2FA optionnel pour tout le monde. Une
    valeur mal orthographiée est refusée au démarrage plutôt qu'ignorée : une
    faute de frappe ne doit pas supprimer une obligation sans bruit. En mode
    local (installation autonome mono-poste), la fonction est indisponible.
    """
    if mode_local:
        return AUCUN, DIRECTION
    obligatoire = _lire_rang(environnement, VARIABLE_OBLIGATOIRE, AUCUN, {"aucun"})
    desactive = _lire_rang(environnement, VARIABLE_DESACTIVE, JAMAIS, {"jamais"})
    try:
        verifier_curseurs(obligatoire, desactive)
    except ValueError as erreur:
        raise ImproperlyConfigured(
            f"{VARIABLE_OBLIGATOIRE} et {VARIABLE_DESACTIVE} sont incohérentes : {erreur}"
        ) from erreur
    return obligatoire, desactive
