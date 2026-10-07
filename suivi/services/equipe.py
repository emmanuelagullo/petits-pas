import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import EmailMultiAlternatives
from django.db import models, transaction
from django.template.loader import render_to_string
from django.utils import timezone

from comptes.models import (
    AffectationClasse,
    AnomalieGouvernance,
    AppartenanceEcole,
    Invitation,
    ResponsabiliteEcole,
    Utilisateur,
)
from suivi.acces_double_facteur import fermer_sessions_compte, poser_echeance_si_besoin
from suivi.audit import journaliser
from suivi.autorisations import (
    ADMINISTRER_ECOLE,
    GERER_AFFECTATIONS,
    autorise,
    est_direction,
    peut_activer_classe,
    peut_auto_attribuer_temporairement,
    peut_suspendre_urgence,
    peut_terminer_affectation,
)
from suivi.models import Classe, Ecole


logger = logging.getLogger(__name__)


def _empreinte(jeton):
    return hashlib.sha256(jeton.encode()).hexdigest()


def invitation_est_utilisable(invitation, jeton):
    return bool(
        invitation.etat == Invitation.EN_ATTENTE
        and invitation.expire_le >= timezone.now()
        and secrets.compare_digest(invitation.empreinte_jeton, _empreinte(jeton))
    )


def _accepter_invitation_verrouillee(*, utilisateur, invitation):
    appartenance = AppartenanceEcole.objects.create(
        utilisateur=utilisateur,
        ecole=invitation.ecole,
        attribue_par=invitation.cree_par,
    )
    invitation.etat = Invitation.ACCEPTEE
    invitation.acceptee_par = utilisateur
    invitation.acceptee_le = timezone.now()
    invitation.save(update_fields=["etat", "acceptee_par", "acceptee_le"])
    journaliser(
        utilisateur,
        "invitation.acceptee",
        invitation,
        nouvelles={"appartenance_id": appartenance.pk},
    )
    preattributions = list(
        AffectationClasse.objects.select_for_update().filter(
            invitation=invitation, appartenance__isnull=True
        ).order_by("pk")
    )
    for affectation in preattributions:
        affectation.appartenance = appartenance
        affectation.save(update_fields=["appartenance"])
        journaliser(
            utilisateur,
            "affectation.promue",
            affectation,
            nouvelles={"appartenance_id": appartenance.pk},
        )
    return appartenance


def terminer_preattributions(invitation, *, acteur=None, motif=""):
    """Termine les pré-attributions encore actives d'une invitation qui ne sera
    jamais acceptée (révoquée ou expirée).

    Sans cela elles resteraient actives, et affichées « Invitation en cours »
    avec l'adresse de la personne, pour toujours. À appeler dans la transaction
    qui change l'état de l'invitation. Sans acteur (expiration automatique),
    rien n'est écrit au journal d'audit, qui exige un acteur : l'expiration
    de l'invitation elle-même n'y figure pas non plus.
    """
    aujourd_hui = timezone.localdate()
    maintenant = timezone.now()
    terminees = []
    for affectation in AffectationClasse.objects.select_for_update().filter(
        invitation=invitation,
        appartenance__isnull=True,
        etat__in=[AffectationClasse.ACTIVE, AffectationClasse.SUSPENDUE],
    ).order_by("pk"):
        ancien = {
            "etat": affectation.etat,
            "date_fin": affectation.date_fin.isoformat() if affectation.date_fin else None,
        }
        affectation.etat = AffectationClasse.TERMINEE
        affectation.date_fin = max(aujourd_hui, affectation.date_debut)
        affectation.termine_par = acteur
        affectation.termine_le = maintenant
        if motif:
            affectation.motif = f"{affectation.motif} | {motif}" if affectation.motif else motif
        affectation.save(
            update_fields=["etat", "date_fin", "termine_par", "termine_le", "motif"]
        )
        if acteur is not None:
            journaliser(
                acteur,
                "affectation.terminee",
                affectation,
                anciennes=ancien,
                nouvelles={
                    "etat": affectation.etat,
                    "date_fin": affectation.date_fin.isoformat(),
                    "cause": "invitation_revoquee",
                },
            )
        terminees.append(affectation)
    return terminees


def _exiger_direction(utilisateur, ecole):
    if not autorise(utilisateur, ADMINISTRER_ECOLE, ecole, ecole=ecole):
        raise PermissionDenied


@transaction.atomic
def inviter(*, utilisateur, ecole, email, duree_jours=7):
    _exiger_direction(utilisateur, ecole)
    email = email.strip().casefold()
    if not email:
        raise ValidationError("L'adresse électronique est obligatoire.")
    compte = Utilisateur.objects.filter(email__iexact=email).first()
    if compte and AppartenanceEcole.objects.a_la_date().filter(
        utilisateur=compte, ecole=ecole
    ).exists():
        raise ValidationError("Cette personne est déjà membre de l'école.")
    if Invitation.objects.filter(
        ecole=ecole,
        email__iexact=email,
        etat=Invitation.EN_ATTENTE,
        expire_le__gte=timezone.now(),
    ).exists():
        raise ValidationError("Une invitation encore valable existe déjà pour cette adresse.")
    jeton = secrets.token_urlsafe(32)
    invitation = Invitation.objects.create(
        ecole=ecole,
        email=email,
        empreinte_jeton=_empreinte(jeton),
        expire_le=timezone.now() + timedelta(days=duree_jours),
        cree_par=utilisateur,
    )
    journaliser(
        utilisateur,
        "invitation.creee",
        invitation,
        nouvelles={"email": email, "expire_le": invitation.expire_le.isoformat()},
    )
    return invitation, jeton


def envoyer_email_invitation(*, utilisateur, invitation, lien):
    """Envoie l'e-mail d'invitation.

    Un échec d'envoi est consigné mais ne remet jamais en cause
    l'invitation déjà créée : le lien affiché à l'écran de la direction
    reste utilisable en secours (voir
    AUDIT-AUTHENTIFICATION-INVITATIONS.org, §3.4). Renvoie True si
    l'envoi a réussi, False sinon.
    """
    if not settings.EMAIL_DISPONIBLE:
        return False

    contexte = {
        "ecole": invitation.ecole,
        "lien": lien,
        "expire_le": invitation.expire_le,
    }
    corps_texte = render_to_string("suivi/emails/invitation.txt", contexte)
    corps_html = render_to_string("suivi/emails/invitation.html", contexte)
    message = EmailMultiAlternatives(
        subject=f"Invitation à rejoindre {invitation.ecole.nom} sur Petits Pas",
        body=corps_texte,
        to=[invitation.email],
    )
    message.attach_alternative(corps_html, "text/html")
    try:
        message.send(fail_silently=False)
    except Exception as erreur:
        logger.warning(
            "Échec de l'envoi de l'e-mail d'invitation %s : %s",
            invitation.pk,
            erreur,
        )
        journaliser(
            utilisateur,
            "invitation.email_echec",
            invitation,
            nouvelles={"erreur": str(erreur)},
        )
        return False
    return True


@transaction.atomic
def accepter_invitation(*, utilisateur, invitation, jeton):
    invitation = Invitation.objects.select_for_update().get(pk=invitation.pk)
    if (
        not invitation_est_utilisable(invitation, jeton)
        or utilisateur.email.strip().casefold() != invitation.email.casefold()
    ):
        raise PermissionDenied
    return _accepter_invitation_verrouillee(
        utilisateur=utilisateur, invitation=invitation
    )


@transaction.atomic
def creer_compte_et_accepter_invitation(
    *, invitation, jeton, username, first_name, last_name, password
):
    invitation = Invitation.objects.select_for_update().get(pk=invitation.pk)
    if not invitation_est_utilisable(invitation, jeton):
        raise PermissionDenied
    if Utilisateur.objects.filter(email__iexact=invitation.email).exists():
        raise ValidationError(
            "Un compte existe déjà pour cette adresse : connectez-vous avec celui-ci."
        )
    utilisateur = Utilisateur.objects.create_user(
        username=username,
        email=invitation.email.strip().casefold(),
        password=password,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
    )
    _accepter_invitation_verrouillee(
        utilisateur=utilisateur, invitation=invitation
    )
    # Compte neuf déjà soumis à l'obligation : inscription dès la première
    # connexion, sans délai de grâce.
    poser_echeance_si_besoin(utilisateur, delai_de_grace=False)
    return utilisateur


@transaction.atomic
def revoquer_invitation(*, utilisateur, invitation):
    invitation = Invitation.objects.select_for_update().get(pk=invitation.pk)
    _exiger_direction(utilisateur, invitation.ecole)
    if invitation.etat != Invitation.EN_ATTENTE:
        raise ValidationError("Seule une invitation en attente peut être révoquée.")
    invitation.etat = Invitation.REVOQUEE
    invitation.revoquee_par = utilisateur
    invitation.revoquee_le = timezone.now()
    invitation.save(update_fields=["etat", "revoquee_par", "revoquee_le"])
    journaliser(utilisateur, "invitation.revoquee", invitation)
    # Une invitation révoquée ne sera jamais acceptée : ses pré-attributions
    # n'ont plus lieu d'être.
    terminer_preattributions(
        invitation, acteur=utilisateur, motif="Invitation révoquée"
    )


@transaction.atomic
def attribuer_affectation(
    *,
    utilisateur,
    classe,
    type,
    appartenance=None,
    invitation=None,
    date_debut=None,
    date_fin=None,
    motif="",
):
    if bool(appartenance) == bool(invitation):
        raise ValueError(
            "attribuer_affectation attend soit appartenance, soit invitation."
        )
    classe = Classe.objects.select_for_update().get(pk=classe.pk)
    if not autorise(utilisateur, GERER_AFFECTATIONS, classe, ecole=classe.ecole):
        raise PermissionDenied
    if appartenance is not None:
        appartenance = AppartenanceEcole.objects.select_for_update().get(
            pk=appartenance.pk
        )
        if not appartenance.est_active() or appartenance.ecole_id != classe.ecole_id:
            raise PermissionDenied
    else:
        invitation = Invitation.objects.select_for_update().get(pk=invitation.pk)
        if (
            invitation.etat != Invitation.EN_ATTENTE
            or invitation.ecole_id != classe.ecole_id
        ):
            raise PermissionDenied
    affectation = AffectationClasse.objects.create(
        appartenance=appartenance,
        invitation=invitation,
        classe=classe,
        type=type,
        acces_historique=classe.statut_annee in {"passee", "ancienne"},
        date_debut=date_debut or timezone.localdate(),
        date_fin=date_fin,
        motif=motif.strip(),
        attribue_par=utilisateur,
    )
    journaliser(
        utilisateur,
        "affectation.preattribuee" if invitation else "affectation.attribuee",
        affectation,
        nouvelles={
            "type": type,
            "acces_historique": affectation.acces_historique,
            "date_debut": affectation.date_debut.isoformat(),
            "date_fin": affectation.date_fin.isoformat() if affectation.date_fin else None,
            "utilisateur_id": appartenance.utilisateur_id if appartenance else None,
            "invitation_id": invitation.pk if invitation else None,
        },
    )
    if type == AffectationClasse.RESPONSABLE and affectation.est_active():
        AnomalieGouvernance.objects.filter(
            classe=classe,
            type=AnomalieGouvernance.CLASSE_SANS_RESPONSABLE,
            resolue_le__isnull=True,
        ).update(resolue_le=timezone.now())
    return affectation


@transaction.atomic
def auto_attribuer_temporairement(
    *, utilisateur, classe, appartenance, motif, date_fin
):
    autorisee = peut_auto_attribuer_temporairement(
        utilisateur, classe, motif, date_fin
    )
    if appartenance.utilisateur_id != utilisateur.pk or not autorisee:
        raise PermissionDenied
    affectation = attribuer_affectation(
        utilisateur=utilisateur,
        appartenance=appartenance,
        classe=classe,
        type=AffectationClasse.RESPONSABLE,
        date_fin=date_fin,
        motif=motif,
    )
    journaliser(
        utilisateur,
        "affectation.auto_attribution_temporaire",
        affectation,
        nouvelles={"motif": motif, "date_fin": date_fin.isoformat()},
    )
    return affectation


@transaction.atomic
def terminer_affectation(*, utilisateur, affectation, remplacement=None):
    Classe.objects.select_for_update().get(pk=affectation.classe_id)
    affectation = AffectationClasse.objects.select_for_update().get(pk=affectation.pk)
    list(
        AffectationClasse.objects.select_for_update().filter(
            classe=affectation.classe,
            type=AffectationClasse.RESPONSABLE,
            etat=AffectationClasse.ACTIVE,
        ).order_by("pk")
    )
    if not peut_terminer_affectation(utilisateur, affectation, remplacement):
        raise ValidationError("Le dernier responsable doit d'abord être remplacé.")
    ancien = {
        "etat": affectation.etat,
        "date_fin": affectation.date_fin.isoformat() if affectation.date_fin else None,
    }
    affectation.etat = AffectationClasse.TERMINEE
    affectation.date_fin = timezone.localdate()
    affectation.termine_par = utilisateur
    affectation.termine_le = timezone.now()
    affectation.save(
        update_fields=["etat", "date_fin", "termine_par", "termine_le"]
    )
    journaliser(
        utilisateur,
        "affectation.terminee",
        affectation,
        anciennes=ancien,
        nouvelles={"etat": affectation.etat, "date_fin": affectation.date_fin.isoformat()},
    )
    return affectation


@transaction.atomic
def remplacer_responsable(
    *, utilisateur, affectation, appartenance_remplacante, motif=""
):
    if affectation.type != AffectationClasse.RESPONSABLE:
        raise ValidationError("Seul un responsable peut être remplacé.")
    remplacement = attribuer_affectation(
        utilisateur=utilisateur,
        appartenance=appartenance_remplacante,
        classe=affectation.classe,
        type=AffectationClasse.RESPONSABLE,
        motif=motif,
    )
    terminer_affectation(
        utilisateur=utilisateur,
        affectation=affectation,
        remplacement=remplacement,
    )
    journaliser(
        utilisateur,
        "affectation.responsable_remplace",
        remplacement,
        anciennes={"affectation_id": affectation.pk},
    )
    return remplacement


@transaction.atomic
def suspendre_affectation_urgence(*, utilisateur, affectation, motif):
    if not motif.strip() or not peut_suspendre_urgence(utilisateur, affectation):
        raise PermissionDenied
    affectation.etat = AffectationClasse.SUSPENDUE
    affectation.termine_par = utilisateur
    affectation.termine_le = timezone.now()
    affectation.motif = motif.strip()
    affectation.save(
        update_fields=["etat", "termine_par", "termine_le", "motif"]
    )
    journaliser(utilisateur, "affectation.suspendue_urgence", affectation)
    if (
        affectation.type == AffectationClasse.RESPONSABLE
        and not affectation.classe.responsables_actifs().exists()
    ):
        anomalie = AnomalieGouvernance.objects.create(
            ecole=affectation.classe.ecole,
            classe=affectation.classe,
            type=AnomalieGouvernance.CLASSE_SANS_RESPONSABLE,
            motif=motif.strip(),
            ouverte_par=utilisateur,
        )
        journaliser(utilisateur, "anomalie.ouverte", anomalie)
    return affectation


@transaction.atomic
def attribuer_direction(*, utilisateur, appartenance, date_fin=None, motif=""):
    # Même verrou pour attribution, retrait et changements de compte/membre.
    Ecole.objects.select_for_update().get(pk=appartenance.ecole_id)
    appartenance = AppartenanceEcole.objects.select_for_update().get(pk=appartenance.pk)
    utilisateur = Utilisateur.objects.get(pk=utilisateur.pk)
    _exiger_direction(utilisateur, appartenance.ecole)
    if not appartenance.est_active():
        raise ValidationError("L'appartenance à l'école n'est pas active.")
    if date_fin is not None and date_fin < timezone.localdate():
        raise ValidationError("La date de fin ne peut pas être passée.")
    if appartenance.date_fin and (date_fin is None or date_fin > appartenance.date_fin):
        raise ValidationError("La fin des droits doit respecter la fin de l'appartenance à l'école.")
    responsabilite = ResponsabiliteEcole.objects.create(
        appartenance=appartenance, attribue_par=utilisateur,
        date_fin=date_fin, motif=motif.strip(),
    )
    poser_echeance_si_besoin(appartenance.utilisateur, delai_de_grace=False)
    if settings.DOUBLE_FACTEUR_DISPONIBLE:
        fermer_sessions_compte(appartenance.utilisateur)
    journaliser(utilisateur, "direction.attribuee", responsabilite, nouvelles={
        "utilisateur_id": appartenance.utilisateur_id,
        "date_fin": date_fin.isoformat() if date_fin else None,
        "motif": motif.strip(),
    })
    return responsabilite


@transaction.atomic
def terminer_direction(*, utilisateur, responsabilite, motif=""):
    from suivi.continuite_direction import verifier_continuite_direction

    ecole_id = responsabilite.appartenance.ecole_id
    Ecole.objects.select_for_update().get(pk=ecole_id)
    responsabilite = ResponsabiliteEcole.objects.select_for_update().select_related(
        "appartenance__ecole"
    ).get(pk=responsabilite.pk)
    utilisateur = Utilisateur.objects.get(pk=utilisateur.pk)
    _exiger_direction(utilisateur, responsabilite.appartenance.ecole)
    if not responsabilite.est_active():
        raise ValidationError("Ces droits de gestion ne sont plus actifs.")
    verifier_continuite_direction(ecole_id, exclure=responsabilite.pk)
    responsabilite.etat = ResponsabiliteEcole.TERMINEE
    responsabilite.date_fin = timezone.localdate()
    responsabilite.termine_par = utilisateur
    responsabilite.termine_le = timezone.now()
    responsabilite.motif = motif.strip()
    responsabilite.save(update_fields=["etat", "date_fin", "termine_par", "termine_le", "motif"])
    journaliser(utilisateur, "direction.terminee", responsabilite, nouvelles={
        "utilisateur_id": responsabilite.appartenance.utilisateur_id,
        "motif": motif.strip(),
    })
    return responsabilite


@transaction.atomic
def activer_classe(*, utilisateur, classe):
    if not peut_activer_classe(utilisateur, classe):
        raise ValidationError("La classe doit avoir un responsable actif.")
    classe.activer()
    journaliser(utilisateur, "classe.activee", classe)
    return classe
