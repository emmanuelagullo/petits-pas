import hashlib
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from comptes.models import (
    AffectationClasse,
    AnomalieGouvernance,
    AppartenanceEcole,
    Invitation,
    ResponsabiliteEcole,
)
from suivi.models import Bilan, Classe, Ecole, Observation, Trace


PROFILS = (
    ("nadia-demo", "Nadia", "Co-titulaire"),
    ("amina-demo", "Amina", "Associée"),
    ("cora-demo", "Cora", "ATSEM"),
    ("samir-demo", "Samir", "Intervenant"),
    ("lea-demo", "Léa", "Remplaçante"),
    ("marc-demo", "Marc", "Sans affectation"),
    ("alice-demo", "Alice", "Ancienne intervenante"),
)


class Command(BaseCommand):
    help = "Crée une équipe fictive riche pour exercer rôles et autorisations."

    def add_arguments(self, parser):
        parser.add_argument("--ecole", type=int)
        parser.add_argument("--mot-de-passe", required=True)
        parser.add_argument(
            "--confirmer-donnees-fictives",
            action="store_true",
            help="Confirme que l'école ne contient aucune donnée réelle.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not options["confirmer_donnees_fictives"]:
            raise CommandError(
                "Refus : ajoutez --confirmer-donnees-fictives uniquement "
                "pour une démonstration sans donnée réelle."
            )
        ecoles = Ecole.objects.all()
        if options["ecole"]:
            ecole = ecoles.filter(pk=options["ecole"]).first()
        elif ecoles.count() == 1:
            ecole = ecoles.first()
        else:
            ecole = None
        if ecole is None:
            raise CommandError("École introuvable ou ambiguë : précisez --ecole.")
        if get_user_model().objects.filter(username="nadia-demo").exists():
            raise CommandError(
                "L'équipe de démonstration existe déjà. Repartez d'une base vide."
            )

        classes = list(
            ecole.classes.filter(annee_scolaire="2026-2027").order_by("ordre", "pk")
        )
        if len(classes) < 2:
            raise CommandError(
                "Le scénario riche exige deux classes en 2026-2027 ; "
                "lancez d'abord jeu_demo_large."
            )
        coccinelles, papillons = classes[:2]
        direction = self._compte_existant(
            ecole, ResponsabiliteEcole.DIRECTION, "Diane", "Direction"
        )
        remi = self._enseignant_existant(ecole)
        remi.first_name, remi.last_name = "Rémi", "Responsable"
        remi.save(update_fields=["first_name", "last_name"])

        utilisateurs = {"remi": remi, "direction": direction}
        for username, prenom, nom in PROFILS:
            utilisateurs[username.split("-")[0]] = self._creer_membre(
                ecole, username, prenom, nom, options["mot_de_passe"], direction
            )

        # Le jeu large historique donnait parfois toutes les classes au compte
        # enseignant. La démonstration riche repart d'affectations explicites.
        AffectationClasse.objects.filter(
            appartenance__ecole=ecole,
            classe__annee_scolaire="2026-2027",
        ).delete()

        self._affecter(utilisateurs["remi"], coccinelles, "responsable", direction)
        self._affecter(utilisateurs["nadia"], coccinelles, "responsable", direction)
        self._affecter(utilisateurs["nadia"], papillons, "responsable", direction)
        self._affecter(utilisateurs["amina"], coccinelles, "enseignant_associe", direction)
        self._affecter(utilisateurs["cora"], coccinelles, "contributeur", direction)
        self._affecter(utilisateurs["samir"], coccinelles, "contributeur", direction)
        self._affecter(utilisateurs["samir"], papillons, "enseignant_associe", direction)
        self._affecter(
            utilisateurs["lea"],
            papillons,
            "responsable",
            direction,
            date_fin=timezone.localdate() + timedelta(days=30),
            motif="Remplacement temporaire de démonstration",
        )
        ancienne = self._affecter(
            utilisateurs["alice"],
            coccinelles,
            "contributeur",
            direction,
            date_debut=timezone.localdate() - timedelta(days=90),
            date_fin=timezone.localdate() - timedelta(days=30),
            motif="Intervention ponctuelle terminée",
            etat=AffectationClasse.TERMINEE,
        )
        ancienne.termine_par = direction
        ancienne.termine_le = timezone.now() - timedelta(days=30)
        ancienne.save(update_fields=["termine_par", "termine_le"])

        for classe in (coccinelles, papillons):
            if classe.etat != Classe.ACTIVE:
                classe.activer()

        lucioles, _ = Classe.objects.get_or_create(
            ecole=ecole,
            nom="Les Lucioles — rentrée suivante",
            annee_scolaire="2027-2028",
            defaults={"ordre": 3, "etat": Classe.PREPARATION},
        )
        AnomalieGouvernance.objects.create(
            ecole=ecole,
            classe=lucioles,
            type=AnomalieGouvernance.CLASSE_SANS_RESPONSABLE,
            motif="Classe de démonstration à préparer",
            ouverte_par=direction,
        )
        self._invitations(ecole, direction)
        self._attribuer_auteurs(coccinelles, papillons, utilisateurs)

        self.stdout.write(
            self.style.SUCCESS(
                "Équipe fictive créée : direction, co-titulaires, associée, "
                "contributeurs, profil mixte, remplacement temporaire, "
                "membre sans affectation et ancienne intervenante."
            )
        )

    def _compte_existant(self, ecole, type_responsabilite, prenom, nom):
        responsabilite = ResponsabiliteEcole.objects.filter(
            appartenance__ecole=ecole,
            type=type_responsabilite,
            etat=ResponsabiliteEcole.ACTIVE,
        ).select_related("appartenance__utilisateur").first()
        if responsabilite is None:
            raise CommandError("Aucun compte de direction initial n'existe.")
        utilisateur = responsabilite.appartenance.utilisateur
        utilisateur.first_name, utilisateur.last_name = prenom, nom
        utilisateur.save(update_fields=["first_name", "last_name"])
        return utilisateur

    def _enseignant_existant(self, ecole):
        appartenance = ecole.appartenances.exclude(
            responsabilites__type=ResponsabiliteEcole.DIRECTION,
            responsabilites__etat=ResponsabiliteEcole.ACTIVE,
        ).select_related("utilisateur").first()
        if appartenance is None:
            raise CommandError("Aucun compte enseignant initial n'existe.")
        return appartenance.utilisateur

    def _creer_membre(self, ecole, username, prenom, nom, mot_de_passe, direction):
        utilisateur = get_user_model().objects.create_user(
            username=username,
            email=f"{username}@example.test",
            password=mot_de_passe,
            first_name=prenom,
            last_name=nom,
        )
        AppartenanceEcole.objects.create(
            utilisateur=utilisateur, ecole=ecole, attribue_par=direction
        )
        return utilisateur

    def _affecter(
        self,
        utilisateur,
        classe,
        type_affectation,
        direction,
        date_debut=None,
        date_fin=None,
        motif="",
        etat=AffectationClasse.ACTIVE,
    ):
        return AffectationClasse.objects.create(
            appartenance=utilisateur.appartenances_ecoles.get(ecole=classe.ecole),
            classe=classe,
            type=type_affectation,
            date_debut=date_debut or timezone.localdate(),
            date_fin=date_fin,
            motif=motif,
            etat=etat,
            attribue_par=direction,
        )

    def _invitations(self, ecole, direction):
        empreinte = hashlib.sha256(b"jeton-fictif-inutilisable").hexdigest()
        Invitation.objects.create(
            ecole=ecole,
            email="future-intervenante@example.test",
            empreinte_jeton=empreinte,
            expire_le=timezone.now() + timedelta(days=7),
            cree_par=direction,
        )
        Invitation.objects.create(
            ecole=ecole,
            email="invitation-revoquee@example.test",
            empreinte_jeton=empreinte,
            expire_le=timezone.now() + timedelta(days=7),
            etat=Invitation.REVOQUEE,
            cree_par=direction,
            revoquee_par=direction,
            revoquee_le=timezone.now(),
        )

    def _attribuer_auteurs(self, coccinelles, papillons, utilisateurs):
        auteurs = {
            coccinelles.pk: [
                utilisateurs["remi"],
                utilisateurs["amina"],
                utilisateurs["cora"],
            ],
            papillons.pk: [
                utilisateurs["nadia"],
                utilisateurs["samir"],
                utilisateurs["lea"],
            ],
        }
        compteurs = {coccinelles.pk: 0, papillons.pk: 0}
        for trace in Trace.objects.filter(
            scolarite__classe__in=(coccinelles, papillons)
        ).select_related("scolarite__classe"):
            classe_id = trace.scolarite.classe_id
            candidats = auteurs[classe_id]
            auteur = candidats[compteurs[classe_id] % len(candidats)]
            compteurs[classe_id] += 1
            trace.auteur = auteur
            trace.dernier_editeur = auteur
            trace.save(update_fields=["auteur", "dernier_editeur"])
        for bilan in Bilan.objects.filter(
            scolarite__classe__in=(coccinelles, papillons)
        ).select_related("scolarite__classe"):
            auteur = (
                utilisateurs["remi"]
                if bilan.scolarite.classe_id == coccinelles.pk
                else utilisateurs["nadia"]
            )
            bilan.auteur = auteur
            bilan.dernier_editeur = auteur
            bilan.save(update_fields=["auteur", "dernier_editeur"])
        contributions = (
            (
                coccinelles,
                utilisateurs["amina"],
                "Contribution de l'enseignante associée.",
            ),
            (
                coccinelles,
                utilisateurs["cora"],
                "Photo et commentaire proposés par l'ATSEM.",
            ),
            (
                papillons,
                utilisateurs["samir"],
                "Observation de l'intervenant associé.",
            ),
        )
        for classe, auteur, commentaire in contributions:
            observation = Observation.objects.filter(
                eleve__scolarites__classe=classe
            ).first()
            if observation:
                scolarite = classe.scolarites.get(eleve=observation.eleve)
                Trace.objects.create(
                    observation=observation,
                    scolarite=scolarite,
                    commentaire=commentaire,
                    auteur=auteur,
                    dernier_editeur=auteur,
                )
