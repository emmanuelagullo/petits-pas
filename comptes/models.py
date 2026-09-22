from datetime import date
import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
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
        return super().save(*args, **kwargs)


class Utilisateur(AbstractUser):
    """Identité individuelle Petits Pas, indépendante de toute école."""


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
    )
    classe = models.ForeignKey(
        "suivi.Classe",
        on_delete=models.PROTECT,
        related_name="affectations",
    )
    type = models.CharField(max_length=20, choices=TYPES)

    class Meta:
        ordering = ["classe", "appartenance", "-date_debut"]

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
        if not self.appartenance_id or not self.classe_id or self.etat != self.ACTIVE:
            return
        chevauchements = AffectationClasse.objects.filter(
            appartenance__utilisateur=self.appartenance.utilisateur,
            classe=self.classe,
            etat=self.ACTIVE,
            date_debut__lte=self.date_fin or date.max,
        ).filter(Q(date_fin__isnull=True) | Q(date_fin__gte=self.date_debut))
        if self.pk:
            chevauchements = chevauchements.exclude(pk=self.pk)
        if chevauchements.exists():
            raise ValidationError(
                "Une personne ne peut avoir qu'un niveau d'affectation actif "
                "dans une classe pour une même période."
            )

    def est_active(self, date=None):
        return (
            super().est_active(date)
            and self.appartenance.est_active(date)
            and self.classe.etat == self.classe.ACTIVE
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
