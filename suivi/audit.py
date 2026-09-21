import datetime

from .models import EvenementAudit


def _json(valeur):
    if isinstance(valeur, (datetime.date, datetime.datetime)):
        return valeur.isoformat()
    if hasattr(valeur, "name"):
        return valeur.name or ""
    return valeur


def instantane(objet, champs):
    return {champ: _json(getattr(objet, champ)) for champ in champs}


def journaliser(acteur, action, objet, anciennes=None, nouvelles=None):
    if hasattr(objet, "ecole"):
        ecole = objet.ecole
    elif hasattr(objet, "classe"):
        ecole = objet.classe.ecole
    elif hasattr(objet, "scolarite"):
        ecole = objet.scolarite.classe.ecole
    elif hasattr(objet, "eleve"):
        ecole = objet.eleve.ecole
    else:
        raise ValueError("La ressource auditée n'est rattachée à aucune école.")
    return EvenementAudit.objects.create(
        ecole=ecole,
        acteur=acteur,
        action=action,
        modele=objet._meta.label_lower,
        objet_id=str(objet.pk),
        anciennes_valeurs=anciennes or {},
        nouvelles_valeurs=nouvelles or {},
    )
