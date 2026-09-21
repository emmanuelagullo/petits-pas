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
    return EvenementAudit.objects.create(
        ecole=objet.scolarite.classe.ecole
        if hasattr(objet, "scolarite")
        else objet.eleve.ecole,
        acteur=acteur,
        action=action,
        modele=objet._meta.label_lower,
        objet_id=str(objet.pk),
        anciennes_valeurs=anciennes or {},
        nouvelles_valeurs=nouvelles or {},
    )
