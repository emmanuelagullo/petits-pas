import yaml
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from suivi.models import Competence, Domaine, Ecole


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
            for j, c in enumerate(d.get("competences", [])):
                _, cree = Competence.objects.update_or_create(
                    domaine=domaine,
                    code=c["code"],
                    defaults={
                        "libelle": c["libelle"],
                        "niveau": c.get("niveau", "PS"),
                        "ordre": j,
                        "active": True,
                    },
                )
                vus.add(c["code"])
                crees += cree
                maj += not cree

        if options["desactiver_absents"]:
            hors = Competence.objects.filter(domaine__ecole=ecole).exclude(code__in=vus)
            n = hors.update(active=False)
            self.stdout.write(f"{n} compétence(s) rendue(s) inactive(s).")

        self.stdout.write(
            self.style.SUCCESS(
                f"{ecole} : {crees} compétence(s) créée(s), {maj} mise(s) à jour."
            )
        )
