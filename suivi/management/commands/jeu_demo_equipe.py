import hashlib
from datetime import timedelta

from django.conf import settings
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
from suivi.configuration_demo import charger_configuration_demo


class Command(BaseCommand):
    help = "Crée une équipe fictive riche pour exercer rôles et autorisations."

    def add_arguments(self, parser):
        parser.add_argument("--ecole", type=int)
        parser.add_argument("--mot-de-passe", required=True)
        parser.add_argument(
            "--configuration",
            default=settings.BASE_DIR / "site" / "data" / "demonstration.yaml",
        )
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
        try:
            configuration = charger_configuration_demo(options["configuration"])
        except (OSError, ValueError) as erreur:
            raise CommandError(str(erreur)) from erreur
        profils = {profil["id"]: profil for profil in configuration["profils"]}
        comptes_a_creer = [
            profil["utilisateur"]
            for profil in profils.values()
            if "compte_initial" not in profil
        ]
        if get_user_model().objects.filter(username__in=comptes_a_creer).exists():
            raise CommandError(
                "L'équipe de démonstration existe déjà. Repartez d'une base vide."
            )

        classes = self._classes_configuration(ecole, configuration)
        coccinelles = classes["coccinelles"]
        papillons = classes["papillons"]
        direction = self._compte_existant(ecole, ResponsabiliteEcole.DIRECTION)
        remi = self._enseignant_existant(ecole)
        utilisateurs = {"diane": direction, "remi": remi}
        for identifiant, utilisateur in utilisateurs.items():
            self._nommer(utilisateur, profils[identifiant])
        for identifiant, profil in profils.items():
            if identifiant in utilisateurs:
                continue
            utilisateurs[identifiant] = self._creer_membre(
                ecole, profil, options["mot_de_passe"], direction
            )

        # Le jeu large historique donnait parfois toutes les classes au compte
        # enseignant. La démonstration riche repart d'affectations explicites.
        AffectationClasse.objects.filter(
            appartenance__ecole=ecole,
            classe__in=(coccinelles, papillons),
        ).delete()

        for identifiant, profil in profils.items():
            for affectation in profil["affectations"]:
                self._affecter_depuis_configuration(
                    utilisateurs[identifiant],
                    classes[affectation["classe"]],
                    affectation,
                    direction,
                )

        for classe in (coccinelles, papillons):
            if classe.etat != Classe.ACTIVE:
                classe.activer()

        lucioles = classes["lucioles"]
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

    def _classes_configuration(self, ecole, configuration):
        classes = {}
        for identifiant, donnees in configuration["classes"].items():
            classe = ecole.classes.filter(
                nom=donnees["nom"], annee_scolaire=donnees["annee_scolaire"]
            ).first()
            if classe is None and identifiant == "lucioles":
                classe = Classe.objects.create(
                    ecole=ecole,
                    nom=donnees["nom"],
                    annee_scolaire=donnees["annee_scolaire"],
                    ordre=3,
                    etat=Classe.PREPARATION,
                )
            if classe is None:
                raise CommandError(
                    f"Classe de démonstration introuvable : {donnees['nom']} "
                    f"({donnees['annee_scolaire']}). Lancez d'abord jeu_demo_large."
                )
            classes[identifiant] = classe
        return classes

    def _compte_existant(self, ecole, type_responsabilite):
        responsabilite = ResponsabiliteEcole.objects.filter(
            appartenance__ecole=ecole,
            type=type_responsabilite,
            etat=ResponsabiliteEcole.ACTIVE,
        ).select_related("appartenance__utilisateur").first()
        if responsabilite is None:
            raise CommandError("Aucun compte de direction initial n'existe.")
        return responsabilite.appartenance.utilisateur

    def _enseignant_existant(self, ecole):
        appartenance = ecole.appartenances.exclude(
            responsabilites__type=ResponsabiliteEcole.DIRECTION,
            responsabilites__etat=ResponsabiliteEcole.ACTIVE,
        ).select_related("utilisateur").first()
        if appartenance is None:
            raise CommandError("Aucun compte enseignant initial n'existe.")
        return appartenance.utilisateur

    def _nommer(self, utilisateur, profil):
        utilisateur.first_name = profil["prenom"]
        utilisateur.last_name = profil["nom_famille"]
        utilisateur.save(update_fields=["first_name", "last_name"])

    def _creer_membre(self, ecole, profil, mot_de_passe, direction):
        utilisateur = get_user_model().objects.create_user(
            username=profil["utilisateur"],
            email=f"{profil['utilisateur']}@example.test",
            password=mot_de_passe,
            first_name=profil["prenom"],
            last_name=profil["nom_famille"],
        )
        AppartenanceEcole.objects.create(
            utilisateur=utilisateur, ecole=ecole, attribue_par=direction
        )
        return utilisateur

    def _affecter_depuis_configuration(
        self, utilisateur, classe, configuration, direction
    ):
        aujourd_hui = timezone.localdate()
        periode = configuration["periode"]
        parametres = {
            "motif": configuration.get("motif", ""),
        }
        if periode == "temporaire":
            parametres["date_fin"] = aujourd_hui + timedelta(
                days=configuration["duree_jours"]
            )
        elif periode == "terminee":
            parametres.update(
                date_debut=aujourd_hui
                - timedelta(days=configuration["debut_jours_avant"]),
                date_fin=aujourd_hui
                - timedelta(days=configuration["fin_jours_avant"]),
                etat=AffectationClasse.TERMINEE,
            )
        affectation = self._affecter(
            utilisateur,
            classe,
            configuration["type"],
            direction,
            **parametres,
        )
        if periode == "terminee":
            affectation.termine_par = direction
            affectation.termine_le = timezone.now() - timedelta(
                days=configuration["fin_jours_avant"]
            )
            affectation.save(update_fields=["termine_par", "termine_le"])
        return affectation

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
