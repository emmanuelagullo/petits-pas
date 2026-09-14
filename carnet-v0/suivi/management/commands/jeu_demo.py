import random

from django.core.management.base import BaseCommand

from suivi.models import Classe, Competence, Ecole, Eleve, Observation

PRENOMS = [
    ("Camille", "PS"), ("Sofiane", "PS"), ("Lou", "PS"), ("Ismaël", "PS"),
    ("Anouk", "PS"), ("Gabriel", "MS"), ("Yasmine", "MS"), ("Timéo", "MS"),
    ("Jade", "MS"), ("Malo", "MS"), ("Noor", "MS"), ("Léonie", "GS"),
    ("Arthur", "GS"), ("Fatou", "GS"), ("Marius", "GS"), ("Élise", "GS"),
]

MOTS = [
    "Il l'a refait tout seul le lendemain, sans qu'on lui demande.",
    "Elle a expliqué à Malo comment faire.",
    "Regarde, j'y arrive maintenant !",
    "Observé pendant l'atelier du matin.",
    "A recommencé trois fois avant d'y arriver.",
]


class Command(BaseCommand):
    help = "Remplit une classe de démonstration avec des enfants et des réussites."

    def handle(self, *args, **options):
        random.seed(3)
        ecole = Ecole.objects.first()
        classe, _ = Classe.objects.get_or_create(
            ecole=ecole, nom="PS-MS-GS de Nadia", defaults={"ordre": 1}
        )
        if not classe.eleves.exists():
            for prenom, niveau in PRENOMS:
                Eleve.objects.create(classe=classe, prenom=prenom, niveau=niveau)

        competences = list(Competence.objects.filter(domaine__ecole=ecole))
        for eleve in classe.eleves.all():
            pertinentes = [
                c
                for c in competences
                if c.niveau == "PS"
                or (eleve.niveau in ("MS", "GS") and c.niveau == "MS")
                or (eleve.niveau == "GS" and c.niveau == "GS")
            ]
            for c in random.sample(pertinentes, k=max(3, len(pertinentes) // 2)):
                Observation.objects.update_or_create(
                    eleve=eleve,
                    competence=c,
                    defaults={
                        "statut": random.choices(
                            ["reussi", "en_cours"], weights=[4, 1]
                        )[0],
                        "commentaire": random.choice(MOTS) if random.random() < 0.2 else "",
                    },
                )
        self.stdout.write(
            self.style.SUCCESS(
                f"Démo prête : {classe} — {classe.eleves.count()} enfants, "
                f"{Observation.objects.filter(eleve__classe=classe).count()} observations."
            )
        )
