from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from suivi.audit import instantane, journaliser
from suivi.autorisations import (
    ADMINISTRER_ECOLE,
    GERER_ELEVES_CLASSE,
    autorise,
)
from suivi.models import (
    AccesParcoursEleve,
    DemandeRapprochementEleve,
    Eleve,
    Scolarite,
)


CHAMPS_IDENTITE = ("prenom", "nom", "annee_naissance", "archive_le")


def correspondances(ecole, prenom, nom, annee_naissance):
    return Eleve.objects.filter(
        ecole=ecole,
        prenom__iexact=prenom.strip(),
        nom__iexact=nom.strip(),
        annee_naissance=annee_naissance,
    )


@transaction.atomic
def importer_nouveaux_eleves(*, utilisateur, classe, lignes, niveau_defaut):
    if not autorise(utilisateur, GERER_ELEVES_CLASSE, classe):
        raise PermissionDenied
    resultat = {"crees": 0, "demandes": 0}
    for ligne in lignes:
        prenom = ligne["prenom"].strip()
        if not prenom:
            continue
        nom = ligne.get("nom", "").strip()
        annee_naissance = ligne.get("annee_naissance")
        niveau = ligne.get("niveau") or niveau_defaut
        candidats = correspondances(
            classe.ecole, prenom, nom, annee_naissance
        )
        if candidats.exists():
            demande = DemandeRapprochementEleve.objects.create(
                ecole=classe.ecole,
                classe=classe,
                prenom_propose=prenom,
                nom_propose=nom,
                annee_naissance_proposee=annee_naissance,
                niveau_propose=niveau,
                demande_par=utilisateur,
            )
            journaliser(
                utilisateur,
                "rapprochement.demande",
                demande,
                nouvelles={
                    "classe_id": classe.pk,
                    "nombre_correspondances": candidats.count(),
                },
            )
            resultat["demandes"] += 1
            continue
        eleve = Eleve.objects.create(
            ecole=classe.ecole,
            prenom=prenom,
            nom=nom,
            annee_naissance=annee_naissance,
        )
        Scolarite.objects.create(
            eleve=eleve,
            classe=classe,
            annee_scolaire=classe.annee_scolaire,
            niveau=niveau,
        )
        journaliser(
            utilisateur,
            "eleve.cree",
            eleve,
            nouvelles={
                **instantane(eleve, CHAMPS_IDENTITE),
                "classe_id": classe.pk,
                "niveau": niveau,
            },
        )
        resultat["crees"] += 1
    return resultat


@transaction.atomic
def valider_rapprochement(*, utilisateur, demande, eleve):
    demande = DemandeRapprochementEleve.objects.select_for_update().get(
        pk=demande.pk
    )
    if not autorise(
        utilisateur, ADMINISTRER_ECOLE, demande.ecole, ecole=demande.ecole
    ):
        raise PermissionDenied
    if demande.etat != DemandeRapprochementEleve.EN_ATTENTE:
        raise ValidationError("Cette demande a déjà été traitée.")
    if eleve.ecole_id != demande.ecole_id or not correspondances(
        demande.ecole,
        demande.prenom_propose,
        demande.nom_propose,
        demande.annee_naissance_proposee,
    ).filter(pk=eleve.pk).exists():
        raise PermissionDenied
    scolarite = eleve.scolarites.filter(
        annee_scolaire=demande.classe.annee_scolaire
    ).first()
    if scolarite and scolarite.classe_id != demande.classe_id:
        raise ValidationError(
            "Cet élève appartient déjà à une autre classe pour cette année."
        )
    if scolarite is None:
        Scolarite.objects.create(
            eleve=eleve,
            classe=demande.classe,
            annee_scolaire=demande.classe.annee_scolaire,
            niveau=demande.niveau_propose,
        )
    eleve.archive_le = None
    eleve.save(update_fields=["archive_le"])
    demande.etat = DemandeRapprochementEleve.VALIDEE
    demande.eleve_retenu = eleve
    demande.decide_par = utilisateur
    demande.decide_le = timezone.now()
    demande.save(
        update_fields=["etat", "eleve_retenu", "decide_par", "decide_le"]
    )
    acces, _ = AccesParcoursEleve.objects.get_or_create(
        demande=demande,
        defaults={
            "eleve": eleve,
            "classe": demande.classe,
            "valide_par": utilisateur,
        },
    )
    journaliser(
        utilisateur,
        "rapprochement.valide",
        demande,
        anciennes={"etat": DemandeRapprochementEleve.EN_ATTENTE},
        nouvelles={
            "etat": demande.etat,
            "eleve_id": eleve.pk,
            "acces_parcours_id": acces.pk,
        },
    )
    return acces


@transaction.atomic
def modifier_identite(*, utilisateur, eleve, classe, valeurs):
    if not autorise(utilisateur, GERER_ELEVES_CLASSE, classe):
        raise PermissionDenied
    if not autorise(utilisateur, ADMINISTRER_ECOLE, eleve.ecole) and not (
        classe and eleve.scolarites.filter(classe=classe).exists()
    ):
        raise PermissionDenied
    anciennes = instantane(eleve, CHAMPS_IDENTITE)
    for champ in ("prenom", "nom", "annee_naissance"):
        setattr(eleve, champ, valeurs[champ])
    eleve.save(update_fields=["prenom", "nom", "annee_naissance"])
    journaliser(
        utilisateur,
        "eleve.identite_modifiee",
        eleve,
        anciennes=anciennes,
        nouvelles=instantane(eleve, CHAMPS_IDENTITE),
    )
    return eleve


@transaction.atomic
def modifier_niveau_courant(*, utilisateur, scolarite, niveau):
    if not autorise(
        utilisateur, GERER_ELEVES_CLASSE, scolarite.classe
    ):
        raise PermissionDenied
    ancien = {"niveau": scolarite.niveau}
    scolarite.niveau = niveau
    scolarite.save(update_fields=["niveau", "modifie_le"])
    journaliser(
        utilisateur,
        "scolarite.niveau_modifie",
        scolarite,
        anciennes=ancien,
        nouvelles={"niveau": niveau},
    )
    return scolarite


@transaction.atomic
def archiver(*, utilisateur, eleve, classe):
    direction = autorise(utilisateur, ADMINISTRER_ECOLE, eleve.ecole)
    if not direction and not (
        classe and autorise(utilisateur, GERER_ELEVES_CLASSE, classe)
    ):
        raise PermissionDenied
    if not direction and not eleve.scolarites.filter(classe=classe).exists():
        raise PermissionDenied
    anciennes = instantane(eleve, CHAMPS_IDENTITE)
    eleve.archive_le = timezone.now()
    eleve.save(update_fields=["archive_le"])
    journaliser(
        utilisateur,
        "eleve.archive",
        eleve,
        anciennes=anciennes,
        nouvelles=instantane(eleve, CHAMPS_IDENTITE),
    )
    return eleve


@transaction.atomic
def desarchiver(*, utilisateur, eleve, classe):
    direction = autorise(utilisateur, ADMINISTRER_ECOLE, eleve.ecole)
    if not direction and not (
        classe and autorise(utilisateur, GERER_ELEVES_CLASSE, classe)
    ):
        raise PermissionDenied
    if not direction and not eleve.scolarites.filter(classe=classe).exists():
        raise PermissionDenied
    anciennes = instantane(eleve, CHAMPS_IDENTITE)
    eleve.archive_le = None
    eleve.save(update_fields=["archive_le"])
    journaliser(
        utilisateur,
        "eleve.desarchive",
        eleve,
        anciennes=anciennes,
        nouvelles=instantane(eleve, CHAMPS_IDENTITE),
    )
    return eleve
