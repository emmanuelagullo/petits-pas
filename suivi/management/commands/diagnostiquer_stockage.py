import json
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import connection

from suivi.models import ReglagePresentation, RessourceReferentiel, Trace, TraceCommune


def _noms_medias():
    groupes = {
        "traces": set(Trace.objects.exclude(photo="").values_list("photo", flat=True)),
        "traces_communes": set(
            TraceCommune.objects.exclude(photo="").values_list("photo", flat=True)
        ),
        "presentation": set(
            ReglagePresentation.objects.exclude(photo="").values_list("photo", flat=True)
        ),
        "referentiels": set(
            RessourceReferentiel.objects.exclude(fichier="").values_list("fichier", flat=True)
        ),
    }
    return {cle: {nom for nom in noms if nom} for cle, noms in groupes.items()}


def _taille_base():
    moteur = connection.vendor
    try:
        if moteur == "sqlite":
            chemin = Path(settings.DATABASES["default"]["NAME"])
            return chemin.stat().st_size if chemin.is_file() else None
        if moteur == "postgresql":
            with connection.cursor() as curseur:
                curseur.execute("SELECT pg_database_size(current_database())")
                return curseur.fetchone()[0]
    except Exception:
        return None
    return None


def diagnostic():
    groupes = _noms_medias()
    tous = set().union(*groupes.values()) if groupes else set()
    tailles = {}
    erreurs = []
    for nom in sorted(tous):
        try:
            tailles[nom] = default_storage.size(nom)
        except Exception as exc:
            erreurs.append({"media": nom, "erreur": str(exc)})
    details = {
        cle: {
            "references": len(noms),
            "octets": sum(tailles.get(nom, 0) for nom in noms),
        }
        for cle, noms in groupes.items()
    }
    return {
        "medias": {
            "objets_uniques": len(tous),
            "octets_uniques": sum(tailles.values()),
            "par_usage": details,
            "erreurs": erreurs,
        },
        "base": {"moteur": connection.vendor, "octets": _taille_base()},
        "portee": (
            "Données gérées par Django. L'hébergeur ajoute le code, "
            "l'environnement Python, les journaux et ses fichiers temporaires."
        ),
    }


class Command(BaseCommand):
    help = "Mesure les médias privés référencés et, si possible, la base."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="json_sortie")

    def handle(self, *args, **options):
        resultat = diagnostic()
        if options["json_sortie"]:
            self.stdout.write(json.dumps(resultat, ensure_ascii=False, sort_keys=True))
            return
        medias = resultat["medias"]
        self.stdout.write(
            f"Médias privés référencés : {medias['objets_uniques']} objet(s), "
            f"{medias['octets_uniques']} octets"
        )
        for usage, valeurs in medias["par_usage"].items():
            self.stdout.write(
                f"- {usage} : {valeurs['references']} référence(s), {valeurs['octets']} octets"
            )
        base = resultat["base"]
        taille = f"{base['octets']} octets" if base["octets"] is not None else "non mesurée"
        self.stdout.write(f"Base {base['moteur']} : {taille}")
        self.stdout.write(resultat["portee"])
        if medias["erreurs"]:
            self.stderr.write(
                f"{len(medias['erreurs'])} objet(s) n'ont pas pu être mesurés."
            )
