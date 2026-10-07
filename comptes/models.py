from datetime import date
import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone


class RelationsActivesQuerySet(models.QuerySet):
    def a_la_date(self, date=None):
        date = date or timezone.localdate()
        return self.filter(
            etat="active",
            date_debut__lte=date,
        ).filter(Q(date_fin__isnull=True) | Q(date_fin__gte=date))


class RelationTemporelle(models.Model):
    ACTIVE = "active"
    SUSPENDUE = "suspendue"
    TERMINEE = "terminee"
    ETATS = [
        (ACTIVE, "Active"),
        (SUSPENDUE, "Suspendue"),
        (TERMINEE, "Terminée"),
    ]

    etat = models.CharField(max_length=10, choices=ETATS, default=ACTIVE)
    date_debut = models.DateField(default=timezone.localdate)
    date_fin = models.DateField(blank=True, null=True)
    attribue_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_attributions",
        blank=True,
        null=True,
    )
    attribue_le = models.DateTimeField(auto_now_add=True)
    termine_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_retraits",
        blank=True,
        null=True,
    )
    termine_le = models.DateTimeField(blank=True, null=True)
    motif = models.TextField(blank=True)

    objects = RelationsActivesQuerySet.as_manager()

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if self.date_fin and self.date_fin < self.date_debut:
            raise ValidationError(
                {"date_fin": "La date de fin doit suivre la date de début."}
            )

    def est_active(self, date=None):
        date = date or timezone.localdate()
        return (
            self.etat == self.ACTIVE
            and self.date_debut <= date
            and (self.date_fin is None or self.date_fin >= date)
        )

    def save(self, *args, **kwargs):
        self.full_clean()
        return _enregistrer_avec_continuite(self, super().save, args, kwargs)


class Utilisateur(AbstractUser):
    """Identité individuelle Petits Pas, indépendante de toute école."""

    def save(self, *args, **kwargs):
        return _enregistrer_avec_continuite(self, super().save, args, kwargs)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                condition=~Q(email=""),
                name="utilisateur_email_unique_sans_casse",
            )
        ]


class AppartenanceEcole(RelationTemporelle):
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="appartenances_ecoles",
    )
    ecole = models.ForeignKey(
        "suivi.Ecole",
        on_delete=models.PROTECT,
        related_name="appartenances",
    )

    class Meta:
        ordering = ["ecole", "utilisateur", "-date_debut"]

    def clean(self):
        super().clean()
        if not self.utilisateur_id or not self.ecole_id or self.etat != self.ACTIVE:
            return
        chevauchements = AppartenanceEcole.objects.filter(
            utilisateur=self.utilisateur,
            ecole=self.ecole,
            etat=self.ACTIVE,
            date_debut__lte=self.date_fin or date.max,
        ).filter(Q(date_fin__isnull=True) | Q(date_fin__gte=self.date_debut))
        if self.pk:
            chevauchements = chevauchements.exclude(pk=self.pk)
        if chevauchements.exists():
            raise ValidationError(
                "Deux appartenances actives à la même école ne peuvent se chevaucher."
            )

    def est_active(self, date=None):
        return (
            super().est_active(date)
            and self.utilisateur.is_active
            and self.ecole.etat == self.ecole.ACTIVE
        )

    def __str__(self):
        return f"{self.utilisateur} — {self.ecole}"


class ResponsabiliteEcole(RelationTemporelle):
    DIRECTION = "direction"
    TYPES = [(DIRECTION, "Direction")]

    appartenance = models.ForeignKey(
        AppartenanceEcole,
        on_delete=models.PROTECT,
        related_name="responsabilites",
    )
    type = models.CharField(max_length=20, choices=TYPES, default=DIRECTION)

    class Meta:
        ordering = ["appartenance", "type", "-date_debut"]

    def clean(self):
        super().clean()
        if not self.appartenance_id or self.etat != self.ACTIVE:
            return
        chevauchements = ResponsabiliteEcole.objects.filter(
            appartenance=self.appartenance,
            type=self.type,
            etat=self.ACTIVE,
            date_debut__lte=self.date_fin or date.max,
        ).filter(Q(date_fin__isnull=True) | Q(date_fin__gte=self.date_debut))
        if self.pk:
            chevauchements = chevauchements.exclude(pk=self.pk)
        if chevauchements.exists():
            raise ValidationError(
                "Deux responsabilités identiques actives ne peuvent se chevaucher."
            )

    def est_active(self, date=None):
        return super().est_active(date) and self.appartenance.est_active(date)


class AffectationClasse(RelationTemporelle):
    RESPONSABLE = "responsable"
    ENSEIGNANT_ASSOCIE = "enseignant_associe"
    CONTRIBUTEUR = "contributeur"
    TYPES = [
        (RESPONSABLE, "Responsable de classe"),
        (ENSEIGNANT_ASSOCIE, "Enseignant associé"),
        (CONTRIBUTEUR, "Contributeur"),
    ]

    appartenance = models.ForeignKey(
        AppartenanceEcole,
        on_delete=models.PROTECT,
        related_name="affectations_classes",
        blank=True,
        null=True,
    )
    invitation = models.ForeignKey(
        "Invitation",
        on_delete=models.PROTECT,
        related_name="affectations_classes",
        blank=True,
        null=True,
        help_text=(
            "Pré-attribution le temps que la personne invitée crée son "
            "compte ; appartenance est renseignée dès l'acceptation."
        ),
    )
    classe = models.ForeignKey(
        "suivi.Classe",
        on_delete=models.PROTECT,
        related_name="affectations",
    )
    type = models.CharField(max_length=20, choices=TYPES)
    acces_historique = models.BooleanField(
        default=False,
        help_text=(
            "Autorise explicitement l’accès pédagogique à une classe d’une "
            "année scolaire passée."
        ),
    )

    class Meta:
        ordering = ["classe", "appartenance", "-date_debut"]
        constraints = [
            models.CheckConstraint(
                condition=Q(appartenance__isnull=False) | Q(invitation__isnull=False),
                name="affectationclasse_appartenance_ou_invitation",
            )
        ]

    @property
    def en_attente(self):
        """True tant que la personne n'a pas créé son compte : la ligne
        est rattachée à une invitation, pas encore à une appartenance."""
        return self.appartenance_id is None

    @property
    def preattribution_en_cours(self):
        """Pré-attribution encore susceptible de devenir une affectation réelle :
        rattachée à une invitation toujours valable (ni acceptée, ni révoquée,
        ni expirée, même si la commande de marquage n'est pas encore passée) et
        non annulée. Une pré-attribution qui ne l'est plus n'a plus rien à
        afficher comme « en cours »."""
        invitation = self.invitation
        return bool(
            self.appartenance_id is None
            and self.etat == self.ACTIVE
            and invitation is not None
            and invitation.etat == Invitation.EN_ATTENTE
            and invitation.expire_le >= timezone.now()
        )

    def clean(self):
        super().clean()
        if (
            self.appartenance_id
            and self.classe_id
            and self.appartenance.ecole_id != self.classe.ecole_id
        ):
            raise ValidationError(
                {"classe": "L'appartenance et la classe doivent relever de la même école."}
            )
        if (
            self.invitation_id
            and self.classe_id
            and self.invitation.ecole_id != self.classe.ecole_id
        ):
            raise ValidationError(
                {"classe": "L'invitation et la classe doivent relever de la même école."}
            )
        if not self.classe_id or self.etat != self.ACTIVE:
            return
        if self.appartenance_id:
            chevauchements = AffectationClasse.objects.filter(
                appartenance__utilisateur=self.appartenance.utilisateur,
                classe=self.classe,
                etat=self.ACTIVE,
                date_debut__lte=self.date_fin or date.max,
            ).filter(Q(date_fin__isnull=True) | Q(date_fin__gte=self.date_debut))
        elif self.invitation_id:
            chevauchements = AffectationClasse.objects.filter(
                invitation=self.invitation,
                classe=self.classe,
                etat=self.ACTIVE,
                date_debut__lte=self.date_fin or date.max,
            ).filter(Q(date_fin__isnull=True) | Q(date_fin__gte=self.date_debut))
        else:
            return
        if self.pk:
            chevauchements = chevauchements.exclude(pk=self.pk)
        if chevauchements.exists():
            raise ValidationError(
                "Une personne ne peut avoir qu'un niveau d'affectation actif "
                "dans une classe pour une même période."
            )

    def est_active(self, date=None):
        if self.appartenance_id is None:
            return False
        return (
            super().est_active(date)
            and self.appartenance.est_active(date)
            and (
                self.classe.etat == self.classe.ACTIVE
                or self.acces_historique
            )
        )


class Invitation(models.Model):
    EN_ATTENTE = "en_attente"
    ACCEPTEE = "acceptee"
    REVOQUEE = "revoquee"
    EXPIREE = "expiree"
    ETATS = [
        (EN_ATTENTE, "En attente"),
        (ACCEPTEE, "Acceptée"),
        (REVOQUEE, "Révoquée"),
        (EXPIREE, "Expirée"),
    ]

    ecole = models.ForeignKey(
        "suivi.Ecole", on_delete=models.PROTECT, related_name="invitations"
    )
    email = models.EmailField()
    selecteur = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    empreinte_jeton = models.CharField(max_length=64, editable=False)
    expire_le = models.DateTimeField()
    etat = models.CharField(max_length=10, choices=ETATS, default=EN_ATTENTE)
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="invitations_creees",
    )
    cree_le = models.DateTimeField(auto_now_add=True)
    acceptee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="invitations_acceptees",
        blank=True,
        null=True,
    )
    acceptee_le = models.DateTimeField(blank=True, null=True)
    revoquee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="invitations_revoquees",
        blank=True,
        null=True,
    )
    revoquee_le = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-cree_le"]


class AnomalieGouvernance(models.Model):
    CLASSE_SANS_RESPONSABLE = "classe_sans_responsable"
    TYPES = [(CLASSE_SANS_RESPONSABLE, "Classe sans responsable")]

    ecole = models.ForeignKey(
        "suivi.Ecole", on_delete=models.PROTECT, related_name="anomalies_gouvernance"
    )
    classe = models.ForeignKey(
        "suivi.Classe",
        on_delete=models.PROTECT,
        related_name="anomalies_gouvernance",
        blank=True,
        null=True,
    )
    type = models.CharField(max_length=40, choices=TYPES)
    motif = models.TextField()
    ouverte_le = models.DateTimeField(auto_now_add=True)
    ouverte_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="anomalies_gouvernance_ouvertes",
    )
    resolue_le = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-ouverte_le"]


class DoubleFacteurCompte(models.Model):
    """État 2FA d'un compte : clé TOTP chiffrée et échéance d'inscription.

    La ligne existe dès qu'une inscription commence (clé générée, pas encore
    confirmée) ou qu'une échéance d'obligation est posée. Le compte n'est
    protégé qu'une fois la clé confirmée par un premier code valide.
    """

    utilisateur = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="double_facteur"
    )
    # Clé secrète chiffrée (Fernet) ; jamais en clair en base.
    cle_chiffree = models.TextField(blank=True)
    confirme_le = models.DateTimeField(null=True, blank=True)
    # Dernier pas de 30 s accepté : un code déjà utilisé ne peut pas être rejoué.
    dernier_pas = models.BigIntegerField(default=0)
    # Au-delà, un compte soumis à l'obligation et non inscrit est bloqué.
    echeance_le = models.DateTimeField(null=True, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    @property
    def inscrit(self):
        return bool(self.cle_chiffree) and self.confirme_le is not None


class CodeSecoursDoubleFacteur(models.Model):
    """Code de secours à usage unique, conservé sous forme d'empreinte seule."""

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="codes_secours"
    )
    empreinte = models.CharField(max_length=64)
    utilise_le = models.DateTimeField(null=True, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["utilisateur", "empreinte"],
                name="code_secours_unique_par_compte"),
        ]


def _enregistrer_avec_continuite(instance, enregistrer, args, kwargs):
    """Protéger les changements existants ; ne pas bloquer l'initialisation.

    Les migrations historiques et QuerySet.update n'appellent pas ce helper.
    Une intervention SQL doit vérifier explicitement la gouvernance.
    """
    nom = instance._meta.model_name
    champs = {
        "utilisateur": {"is_active"},
        "appartenanceecole": {"etat", "date_debut", "date_fin", "utilisateur_id", "ecole_id"},
        "responsabiliteecole": {"etat", "date_debut", "date_fin", "type", "appartenance_id"},
    }.get(nom)
    if instance._state.adding or champs is None:
        return enregistrer(*args, **kwargs)
    update_fields = kwargs.get("update_fields")
    if update_fields is not None:
        champs = {c for c in champs if c in update_fields or c.removesuffix("_id") in update_fields}
    if not champs:
        return enregistrer(*args, **kwargs)
    from suivi.models import Ecole
    from suivi.continuite_direction import verifier_continuite_direction

    with transaction.atomic():
        ancien = type(instance).objects.get(pk=instance.pk)
        if not any(getattr(ancien, c) != getattr(instance, c) for c in champs):
            return enregistrer(*args, **kwargs)
        relations = ResponsabiliteEcole.objects.filter(etat="active", type="direction")
        if nom == "utilisateur":
            relations = relations.filter(appartenance__utilisateur_id=instance.pk)
        elif nom == "appartenanceecole":
            relations = relations.filter(appartenance_id=instance.pk)
            if instance.ecole_id != ancien.ecole_id or instance.utilisateur_id != ancien.utilisateur_id:
                if relations.exists():
                    raise ValidationError("Terminez d'abord les responsabilités avant de changer l'appartenance.")
        else:
            relations = relations.filter(pk=instance.pk)
            if instance.appartenance_id != ancien.appartenance_id and relations.exists():
                raise ValidationError("Une responsabilité doit être terminée avant de changer de personne.")
        # Inclure les appartenances même sans responsabilité : une attribution
        # concurrente doit prendre le même verrou que la désactivation.
        if nom == "utilisateur":
            ecoles = list(AppartenanceEcole.objects.filter(utilisateur_id=instance.pk)
                .values_list("ecole_id", flat=True))
        elif nom == "appartenanceecole":
            ecoles = [ancien.ecole_id, instance.ecole_id]
        else:
            ecoles = list(relations.values_list("appartenance__ecole_id", flat=True))
        for ecole in Ecole.objects.select_for_update().filter(pk__in=set(ecoles)).order_by("pk"):
            if ecole.etat == Ecole.ACTIVE and relations.filter(appartenance__ecole=ecole).exists():
                verifier_continuite_direction(ecole.pk, modification=instance)
        return enregistrer(*args, **kwargs)
