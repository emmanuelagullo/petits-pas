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
    return appartenance


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


@transaction.atomic
def attribuer_affectation(
    *, utilisateur, appartenance, classe, type, date_debut=None, date_fin=None, motif=""
):
    appartenance = AppartenanceEcole.objects.select_for_update().get(
        pk=appartenance.pk
    )
    classe = Classe.objects.select_for_update().get(pk=classe.pk)
    if not autorise(utilisateur, GERER_AFFECTATIONS, classe, ecole=classe.ecole):
        raise PermissionDenied
    if not appartenance.est_active() or appartenance.ecole_id != classe.ecole_id:
        raise PermissionDenied
    affectation = AffectationClasse.objects.create(
        appartenance=appartenance,
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
        "affectation.attribuee",
        affectation,
        nouvelles={
            "type": type,
            "acces_historique": affectation.acces_historique,
            "date_debut": affectation.date_debut.isoformat(),
            "date_fin": affectation.date_fin.isoformat() if affectation.date_fin else None,
            "utilisateur_id": appartenance.utilisateur_id,
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
        )
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
def attribuer_direction(*, utilisateur, appartenance):
    appartenance = AppartenanceEcole.objects.select_for_update().get(
        pk=appartenance.pk
    )
    _exiger_direction(utilisateur, appartenance.ecole)
    if not appartenance.est_active():
        raise ValidationError("L'appartenance à l'école n'est pas active.")
    responsabilite = ResponsabiliteEcole.objects.create(
        appartenance=appartenance,
        attribue_par=utilisateur,
    )
    journaliser(utilisateur, "direction.attribuee", responsabilite)
    return responsabilite


@transaction.atomic
def terminer_direction(*, utilisateur, responsabilite):
    ecole_id = responsabilite.appartenance.ecole_id
    Ecole.objects.select_for_update().get(pk=ecole_id)
    responsabilite = ResponsabiliteEcole.objects.select_for_update().select_related(
        "appartenance__ecole"
    ).get(pk=responsabilite.pk)
    ecole = responsabilite.appartenance.ecole
    _exiger_direction(utilisateur, ecole)
    aujourd_hui = timezone.localdate()
    actives = list(
        ResponsabiliteEcole.objects.select_for_update()
        .a_la_date(aujourd_hui)
        .filter(
            appartenance__ecole=ecole,
            appartenance__etat=AppartenanceEcole.ACTIVE,
            appartenance__date_debut__lte=aujourd_hui,
            appartenance__utilisateur__is_active=True,
            appartenance__ecole__etat="active",
            type=ResponsabiliteEcole.DIRECTION,
        )
        .filter(
            models.Q(appartenance__date_fin__isnull=True)
            | models.Q(appartenance__date_fin__gte=aujourd_hui)
        )
    )
    if not any(active.pk != responsabilite.pk for active in actives):
        raise ValidationError("La dernière direction active ne peut pas être retirée.")
    responsabilite.etat = ResponsabiliteEcole.TERMINEE
    responsabilite.date_fin = aujourd_hui
    responsabilite.termine_par = utilisateur
    responsabilite.termine_le = timezone.now()
    responsabilite.save(
        update_fields=["etat", "date_fin", "termine_par", "termine_le"]
    )
    journaliser(utilisateur, "direction.terminee", responsabilite)
    return responsabilite


@transaction.atomic
def activer_classe(*, utilisateur, classe):
    if not peut_activer_classe(utilisateur, classe):
        raise ValidationError("La classe doit avoir un responsable actif.")
    classe.activer()
    journaliser(utilisateur, "classe.activee", classe)
    return classe
