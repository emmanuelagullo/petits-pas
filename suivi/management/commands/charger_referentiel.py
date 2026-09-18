import yaml
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from suivi.models import Attendu, Competence, Domaine, Ecole, SousDomaine


class Command(BaseCommand):
    help = (
        "Charge ou met à jour le référentiel de compétences depuis un fichier YAML. "
        "Les observations déjà saisies sont conservées tant que les codes ne changent pas."
    )

    def add_arguments(self, parser):
        parser.add_argument("fichier", help="Chemin du fichier YAML")
        parser.add_argument(
            "--ecole",
            type=int,
            help="Identifiant de l'école (inutile s'il n'y en a qu'une)",
        )
        parser.add_argument(
            "--desactiver-absents",
            action="store_true",
            help="Rend inactives les compétences absentes du fichier, au lieu de les laisser telles quelles.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        ecoles = Ecole.objects.all()
        if options["ecole"]:
            ecole = ecoles.filter(pk=options["ecole"]).first()
        elif ecoles.count() == 1:
            ecole = ecoles.first()
        else:
            raise CommandError(
                "Plusieurs écoles en base : précisez --ecole <id>."
                if ecoles.exists()
                else "Aucune école en base. Lancez d'abord : python manage.py creer_ecole"
            )
        if ecole is None:
            raise CommandError("École introuvable.")

        with open(options["fichier"], encoding="utf-8") as f:
            data = yaml.safe_load(f)

        vus = set()
        crees = maj = 0
        for i, d in enumerate(data.get("domaines", [])):
            domaine, _ = Domaine.objects.update_or_create(
                ecole=ecole,
                code=d["code"],
                defaults={"nom": d["nom"], "ordre": i},
            )

            for j, attendu_data in enumerate(d.get("attendus", [])):
                if isinstance(attendu_data, str):
                    attendu_data = {
                        "code": f"{d['code']}-ATT-{j + 1:02d}",
                        "texte": attendu_data,
                    }
                Attendu.objects.update_or_create(
                    domaine=domaine,
                    code=attendu_data["code"],
                    defaults={"texte": attendu_data["texte"], "ordre": j},
                )

            ordre_competence = 0

            def charger_competence(c, sous_domaine=None):
                nonlocal crees, maj, ordre_competence
                _, cree = Competence.objects.update_or_create(
                    domaine=domaine,
                    code=c["code"],
                    defaults={
                        "libelle": c["libelle"],
                        "niveau": c.get("niveau", "PS"),
                        "ordre": ordre_competence,
                        "sous_domaine": sous_domaine,
                        "active": True,
                    },
                )
                ordre_competence += 1
                vus.add(c["code"])
                crees += cree
                maj += not cree

            for c in d.get("competences", []):
                charger_competence(c)

            for j, sous_domaine_data in enumerate(d.get("sous_domaines", [])):
                sous_domaine, _ = SousDomaine.objects.update_or_create(
                    domaine=domaine,
                    code=sous_domaine_data["code"],
                    defaults={"nom": sous_domaine_data["nom"], "ordre": j},
                )
                for c in sous_domaine_data.get("competences", []):
                    charger_competence(c, sous_domaine)

        if options["desactiver_absents"]:
            hors = Competence.objects.filter(domaine__ecole=ecole).exclude(code__in=vus)
            n = hors.update(active=False)
            self.stdout.write(f"{n} compétence(s) rendue(s) inactive(s).")

        self.stdout.write(
            self.style.SUCCESS(
                f"{ecole} : {crees} compétence(s) créée(s), {maj} mise(s) à jour."
            )
        )
