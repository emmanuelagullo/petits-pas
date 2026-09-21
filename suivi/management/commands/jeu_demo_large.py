import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from comptes.models import AffectationClasse, AppartenanceEcole

from suivi.models import (
    Attendu,
    Bilan,
    Classe,
    Competence,
    Domaine,
    Ecole,
    Eleve,
    Observation,
    Scolarite,
    SousDomaine,
    Trace,
    bornes_annee_scolaire,
)

# Cinq années scolaires, la dernière étant la courante au moment de l'écriture.
ANNEES_DEMO = [
    "2022-2023",
    "2023-2024",
    "2024-2025",
    "2025-2026",
    "2026-2027",
]
ANNEE_COURANTE = ANNEES_DEMO[-1]

NOMS_CLASSES = ["Les Coccinelles", "Les Papillons"]

# Cohortes « standard » : un enfant né en N suit sa PS, MS puis GS trois
# années scolaires de suite, à partir de l'année où il a 3 ans au 31 décembre.
ANNEES_NAISSANCE_STANDARD = [2019, 2020, 2021, 2022, 2023]
ENFANTS_PAR_COHORTE = 5

ORDRE_NIVEAU = {"PS": 0, "MS": 1, "GS": 2}

PRENOMS_POOL = [
    "Aïcha", "Adam", "Alma", "Amir", "Anaïs", "Aymeric", "Chloé", "Clément",
    "Diego", "Elio", "Emma", "Enzo", "Faustine", "Gaspard", "Hana", "Hugo",
    "Inaya", "Jules", "Kenza", "Liam", "Lina", "Louis", "Maël", "Manon",
    "Nael", "Nour", "Oscar", "Paul", "Rania", "Sacha", "Sarah", "Théo",
    "Valentine", "Wassim", "Zoé",
]

MOTS_TRACE = [
    "Il l'a refait tout seul le lendemain, sans qu'on lui demande.",
    "Elle a expliqué à un camarade comment faire.",
    "Regarde, j'y arrive maintenant !",
    "Observé pendant l'atelier du matin.",
    "A recommencé plusieurs fois avant d'y arriver.",
]

TEXTES_BILAN = [
    "Une période posée, {prenom} progresse à son rythme.",
    "{prenom} gagne en autonomie, notamment sur les rituels du matin.",
    "Bon investissement dans les ateliers, {prenom} propose spontanément.",
    "{prenom} a besoin d'être encore un peu accompagné·e sur la fin d'activité.",
]


def parcours_normal(annee_naissance):
    """PS, MS puis GS pour un enfant né en ``annee_naissance``, en années
    scolaires successives (au format « 2026-2027 »)."""
    debut = annee_naissance + 3
    return [
        (f"{debut}-{debut + 1}", "PS"),
        (f"{debut + 1}-{debut + 2}", "MS"),
        (f"{debut + 2}-{debut + 3}", "GS"),
    ]


class Command(BaseCommand):
    help = (
        "Remplit la base avec une démonstration bien plus large que jeu_demo : "
        "cinq années scolaires, plusieurs classes par année, des enfants qui "
        "suivent des années successives (dont certains déjà archivés), "
        "quelques parcours non standards, et une ébauche de sous-domaines et "
        "d'attendus pour tester ces affichages du carnet."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--sans-hierarchie",
            action="store_true",
            help="Ne pas ajouter la démonstration de sous-domaines et d'attendus.",
        )
        parser.add_argument(
            "--ecole",
            type=int,
            help="Identifiant de l'école (inutile s'il n'y en a qu'une)",
        )


    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(17)
        ecoles = Ecole.objects.all()
        if options["ecole"]:
            ecole = ecoles.filter(pk=options["ecole"]).first()
        elif ecoles.count() == 1:
            ecole = ecoles.first()
        else:
            raise CommandError(
                "Plusieurs écoles en base : précisez --ecole <id>."
                if ecoles.exists()
                else "Aucune école en base. Lancez d'abord :\n"
                     '  python manage.py creer_ecole "Nom de l\'école"\n'
                     "  python manage.py charger_referentiel referentiel/trame-cycle1.yaml"
            )
        competences = list(Competence.objects.filter(domaine__ecole=ecole))
        if not competences:
            raise CommandError(
                "Aucune compétence en base. Lancez d'abord :\n"
                "  python manage.py charger_referentiel referentiel/trame-cycle1.yaml"
            )
        if Eleve.objects.filter(ecole=ecole, prenom="Redouble").exists():
            raise CommandError(
                "La grande démo semble déjà avoir été générée pour cette école "
                "(un élève « Redouble » existe déjà). Repartez d'une base vide "
                "pour la regénérer."
            )

        classes = self._creer_classes(ecole)
        self._affecter_comptes_demo(ecole, classes[ANNEE_COURANTE])
        self._creer_cohortes_standard(ecole, classes)
        self._creer_parcours_non_standards(ecole, classes)

        eleves = list(Eleve.objects.filter(ecole=ecole))
        self._archiver_les_sortis(eleves)
        self._peupler_observations(eleves, competences)
        self._peupler_bilans(eleves)

        if not options["sans_hierarchie"]:
            self._demo_hierarchie_pedagogique(ecole)

        self.stdout.write(
            self.style.SUCCESS(
                f"Grande démo prête : {len(eleves)} enfants, "
                f"{Classe.objects.filter(ecole=ecole).count()} classes sur "
                f"{len(ANNEES_DEMO)} années, "
                f"{Eleve.objects.filter(ecole=ecole, archive_le__isnull=False).count()} "
                "archivés."
            )
        )

    def _creer_classes(self, ecole):
        """Deux classes par année scolaire. Renvoie {annee: [classe, classe]}."""
        classes = {}
        for annee in ANNEES_DEMO:
            classes[annee] = [
                Classe.objects.get_or_create(
                    ecole=ecole,
                    nom=nom,
                    annee_scolaire=annee,
                    defaults={
                        "ordre": i + 1,
                        "etat": (
                            Classe.PREPARATION
                            if annee == ANNEE_COURANTE
                            else Classe.ARCHIVEE
                        ),
                    },
                )[0]
                for i, nom in enumerate(NOMS_CLASSES)
            ]
        return classes

    def _affecter_comptes_demo(self, ecole, classes_courantes):
        appartenances = AppartenanceEcole.objects.filter(ecole=ecole).exclude(
            responsabilites__type="direction",
            responsabilites__etat="active",
        )
        for appartenance in appartenances:
            for classe in classes_courantes:
                AffectationClasse.objects.get_or_create(
                    appartenance=appartenance,
                    classe=classe,
                    type=AffectationClasse.RESPONSABLE,
                )
                if classe.etat != Classe.ACTIVE:
                    classe.activer()

    def _inscrire(self, eleve, classes, annee, niveau, indice_classe):
        Scolarite.objects.create(
            eleve=eleve,
            classe=classes[annee][indice_classe % len(classes[annee])],
            annee_scolaire=annee,
            niveau=niveau,
        )

    def _creer_cohortes_standard(self, ecole, classes):
        prenoms = random.sample(
            PRENOMS_POOL, k=len(ANNEES_NAISSANCE_STANDARD) * ENFANTS_PAR_COHORTE
        )
        i = 0
        for annee_naissance in ANNEES_NAISSANCE_STANDARD:
            for indice in range(ENFANTS_PAR_COHORTE):
                eleve = Eleve.objects.create(
                    ecole=ecole, prenom=prenoms[i], annee_naissance=annee_naissance
                )
                i += 1
                for annee, niveau in parcours_normal(annee_naissance):
                    if annee in classes:
                        self._inscrire(eleve, classes, annee, niveau, indice)

    def _creer_parcours_non_standards(self, ecole, classes):
        """Trois enfants au parcours volontairement atypique, reconnaissables
        à leur (faux) prénom."""
        # Né en 2020, a redoublé sa PS : niveau par niveau, il rejoint le
        # parcours d'un enfant né en 2021 dès la MS.
        redouble = Eleve.objects.create(
            ecole=ecole, prenom="Redouble", annee_naissance=2020
        )
        self._inscrire(redouble, classes, "2023-2024", "PS", 0)
        self._inscrire(redouble, classes, "2024-2025", "PS", 1)
        self._inscrire(redouble, classes, "2025-2026", "MS", 0)
        self._inscrire(redouble, classes, "2026-2027", "GS", 1)

        # Né en 2021, arrivé directement en MS (pas de scolarité PS connue
        # dans cette école).
        direct = Eleve.objects.create(
            ecole=ecole, prenom="Direct", annee_naissance=2021
        )
        self._inscrire(direct, classes, "2025-2026", "MS", 1)
        self._inscrire(direct, classes, "2026-2027", "GS", 0)

        # Né en 2021, une année d'interruption (archivé) entre sa PS et son
        # retour directement en GS.
        retour = Eleve.objects.create(
            ecole=ecole, prenom="Retour", annee_naissance=2021
        )
        self._inscrire(retour, classes, "2024-2025", "PS", 0)
        retour.archive_le = timezone.make_aware(
            timezone.datetime(2025, 9, 15)
        )
        retour.save(update_fields=["archive_le"])
        self._inscrire(retour, classes, "2026-2027", "GS", 1)
        retour.archive_le = None
        retour.save(update_fields=["archive_le"])

    def _archiver_les_sortis(self, eleves):
        """Un enfant sans scolarité pour l'année courante est considéré
        sorti de l'école et archivé."""
        for eleve in eleves:
            scolarite = eleve.scolarite_courante()
            if not scolarite or scolarite.annee_scolaire != ANNEE_COURANTE:
                if not eleve.archive_le:
                    eleve.archive_le = timezone.now()
                    eleve.save(update_fields=["archive_le"])

    def _peupler_observations(self, eleves, competences):
        for eleve in eleves:
            niveaux_atteints = {s.niveau for s in eleve.scolarites.all()}
            if not niveaux_atteints:
                continue
            seuil = max(ORDRE_NIVEAU[n] for n in niveaux_atteints)
            pertinentes = [c for c in competences if ORDRE_NIVEAU[c.niveau] <= seuil]
            if not pertinentes:
                continue
            for c in random.sample(
                pertinentes, k=min(len(pertinentes), max(3, len(pertinentes) // 2))
            ):
                observation, _ = Observation.objects.update_or_create(
                    eleve=eleve,
                    competence=c,
                    defaults={
                        "statut": random.choices(
                            ["reussi", "en_cours"], weights=[4, 1]
                        )[0],
                    },
                )
                if random.random() < 0.15 and not observation.traces.exists():
                    scolarite = eleve.scolarite_courante()
                    if scolarite:
                        Trace.objects.create(
                            observation=observation,
                            scolarite=scolarite,
                            commentaire=random.choice(MOTS_TRACE),
                        )

    def _peupler_bilans(self, eleves):
        for eleve in eleves:
            for scolarite in eleve.scolarites.all():
                if random.random() < 0.7:
                    debut, fin = bornes_annee_scolaire(scolarite.annee_scolaire)
                    jours = (fin - debut).days
                    date_bilan = debut + timezone.timedelta(
                        days=random.randint(60, max(60, jours - 30))
                    )
                    texte = random.choice(TEXTES_BILAN).format(prenom=eleve.prenom)
                    Bilan.objects.get_or_create(
                        scolarite=scolarite,
                        date_bilan=date_bilan,
                        defaults={"texte": texte},
                    )

    def _demo_hierarchie_pedagogique(self, ecole):
        """Ajoute, sans toucher au référentiel chargé, un exemple de
        sous-domaines et d'attendus pour vérifier que ces affichages du
        carnet fonctionnent bien une fois la hiérarchie renseignée."""
        domaine_lang = Domaine.objects.filter(ecole=ecole, code="LANG").first()
        if not domaine_lang:
            return

        Attendu.objects.get_or_create(
            domaine=domaine_lang,
            code="LANG-ATT-DEMO-01",
            defaults={
                "texte": "Communique avec les adultes et les autres enfants "
                "par le langage, en se faisant comprendre.",
                "ordre": 0,
            },
        )
        Attendu.objects.get_or_create(
            domaine=domaine_lang,
            code="LANG-ATT-DEMO-02",
            defaults={
                "texte": "Pratique divers usages du langage oral : raconter, "
                "décrire, évoquer, expliquer, questionner, proposer des "
                "solutions, discuter un point de vue.",
                "ordre": 1,
            },
        )

        sous_domaine_oral, _ = SousDomaine.objects.get_or_create(
            domaine=domaine_lang,
            code="LANG-ORAL",
            defaults={"nom": "L'oral", "ordre": 0},
        )
        sous_domaine_ecrit, _ = SousDomaine.objects.get_or_create(
            domaine=domaine_lang,
            code="LANG-ECRIT",
            defaults={"nom": "L'écrit", "ordre": 1},
        )
        competences_lang = list(
            Competence.objects.filter(domaine=domaine_lang, sous_domaine__isnull=True)
        )
        for i, c in enumerate(competences_lang):
            c.sous_domaine = sous_domaine_oral if i % 2 == 0 else sous_domaine_ecrit
            c.save(update_fields=["sous_domaine"])
