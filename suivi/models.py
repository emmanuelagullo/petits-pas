import re
import datetime

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property

NIVEAUX = [
    ("PS", "Petite section"),
    ("MS", "Moyenne section"),
    ("GS", "Grande section"),
]


def annee_scolaire_pour(date):
    """Année scolaire (ex. « 2026-2027 ») à laquelle appartient une date,
    le cycle scolaire allant du 1er septembre au 31 août."""
    debut = date.year if date.month >= 9 else date.year - 1
    return f"{debut}-{debut + 1}"


def bornes_annee_scolaire(annee_scolaire):
    """Dates de début (1er septembre) et de fin (31 août) d'une année
    scolaire au format « 2026-2027 »."""
    debut = int(re.match(r"(\d{4})", annee_scolaire).group(1))
    return datetime.date(debut, 9, 1), datetime.date(debut + 1, 8, 31)


def statut_annee_scolaire(annee_scolaire, annee_reference=None):
    """Situe une année scolaire (« 2026-2027 ») par rapport à l'année
    scolaire de référence (aujourd'hui, par défaut) : ``"courante"``,
    ``"future"``, ``"passee"`` (l'année scolaire précédente) ou
    ``"ancienne"`` (plus ancienne encore)."""
    annee_reference = annee_reference or annee_scolaire_pour(timezone.localdate())
    if annee_scolaire == annee_reference:
        return "courante"
    if annee_scolaire > annee_reference:
        return "future"
    debut = re.match(r"(\d{4})", annee_scolaire)
    debut_reference = re.match(r"(\d{4})", annee_reference)
    if debut and debut_reference and int(debut.group(1)) == int(debut_reference.group(1)) - 1:
        return "passee"
    return "ancienne"


class Ecole(models.Model):
    """Une école. La V0 n'en héberge qu'une, mais tout est déjà rattaché à
    l'école pour que l'ouverture à plusieurs établissements ne demande pas
    de migration douloureuse."""

    PREPARATION = "preparation"
    ACTIVE = "active"
    DESACTIVEE = "desactivee"
    ETATS = [
        (PREPARATION, "En préparation"),
        (ACTIVE, "Active"),
        (DESACTIVEE, "Désactivée"),
    ]

    nom = models.CharField(max_length=200)
    commune = models.CharField(max_length=200, blank=True)
    etat = models.CharField(max_length=12, choices=ETATS, default=ACTIVE)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "école"
        verbose_name_plural = "écoles"

    def __str__(self):
        return self.nom

class ParametresCarnet(models.Model):
    ecole = models.OneToOneField(
        Ecole, on_delete=models.CASCADE, related_name="parametres_carnet"
    )
    titre_couverture = models.CharField(
        max_length=200, default="Carnet de suivi des apprentissages"
    )
    texte_couverture = models.TextField(blank=True, max_length=400)
    contenu_par_defaut = models.CharField(
        max_length=10,
        choices=[
            ("reussites", "Réussites"),
            ("observes", "Réussites et apprentissages en cours"),
            ("tout", "Référentiel complet"),
        ],
        default="observes",
    )
    regroupement_par_defaut = models.CharField(
        max_length=10,
        choices=[
            ("aucun", "Aucun"),
            ("annuel", "Annuel"),
            ("mensuel", "Mensuel"),
            ("bilan", "Par bilan"),
        ],
        default="aucun",
    )
    colonnes_par_defaut = models.PositiveSmallIntegerField(
        choices=[(1, "Une colonne"), (2, "Deux colonnes")], default=2
    )
    afficher_attendus = models.BooleanField(default=False)
    afficher_sous_domaines = models.BooleanField(default=True)
    inclure_bilans = models.BooleanField(default=True)

    def __str__(self):
        return f"Paramètres du carnet — {self.ecole}"


class Classe(models.Model):
    PREPARATION = "preparation"
    ACTIVE = "active"
    ARCHIVEE = "archivee"
    ETATS = [
        (PREPARATION, "En préparation"),
        (ACTIVE, "Active"),
        (ARCHIVEE, "Archivée"),
    ]

    ecole = models.ForeignKey(Ecole, on_delete=models.CASCADE, related_name="classes")
    nom = models.CharField(max_length=100, help_text="Par exemple : PS-MS de Nadia")
    annee_scolaire = models.CharField(max_length=9, default="2026-2027")
    ordre = models.PositiveSmallIntegerField(default=0)
    etat = models.CharField(max_length=11, choices=ETATS, default=PREPARATION)

    class Meta:
        ordering = ["ordre", "nom"]
        constraints = [
            models.UniqueConstraint(
                fields=["ecole", "annee_scolaire", "nom"],
                name="classe_unique_par_ecole_annee_nom",
            )
        ]

    def __str__(self):
        return self.nom

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()
        if self.etat == self.ACTIVE and (
            not self.pk or not self.responsables_actifs().exists()
        ):
            raise ValidationError(
                {"etat": "Une classe ne peut être activée sans responsable actif."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def statut_annee(self):
        return statut_annee_scolaire(self.annee_scolaire)

    @property
    def eleves(self):
        return Eleve.objects.filter(
            scolarites__classe=self,
            archive_le__isnull=True,
        ).distinct()

    def responsables_actifs(self, date=None):
        from comptes.models import AffectationClasse

        date = date or timezone.localdate()
        return self.affectations.filter(
            type=AffectationClasse.RESPONSABLE,
            appartenance__utilisateur__is_active=True,
            appartenance__ecole__etat=Ecole.ACTIVE,
            appartenance__etat=AffectationClasse.ACTIVE,
            appartenance__date_debut__lte=date,
            etat=AffectationClasse.ACTIVE,
            date_debut__lte=date,
        ).filter(
            models.Q(date_fin__isnull=True) | models.Q(date_fin__gte=date),
            models.Q(appartenance__date_fin__isnull=True)
            | models.Q(appartenance__date_fin__gte=date),
        )

    def activer(self, date=None):
        from django.core.exceptions import ValidationError

        if not self.pk or not self.responsables_actifs(date).exists():
            raise ValidationError(
                "Une classe ne peut être activée sans responsable actif."
            )
        self.etat = self.ACTIVE
        self.save(update_fields=["etat"])


class Eleve(models.Model):
    ecole = models.ForeignKey(Ecole, on_delete=models.CASCADE, related_name="eleves")
    prenom = models.CharField(max_length=100)
    nom = models.CharField(max_length=100, blank=True)
    annee_naissance = models.PositiveSmallIntegerField(blank=True, null=True)
    archive_le = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["prenom", "nom"]
        verbose_name = "élève"
        verbose_name_plural = "élèves"

    def __str__(self):
        return f"{self.prenom} {self.nom}".strip()

    @property
    def nom_court(self):
        if self.nom:
            return f"{self.prenom} {self.nom[0].upper()}."
        return self.prenom

    def scolarite_courante(self):
        return self.scolarites.select_related("classe").order_by("-annee_scolaire").first()

    @property
    def classe(self):
        scolarite = self.scolarite_courante()
        return scolarite.classe if scolarite else None

    @property
    def niveau(self):
        scolarite = self.scolarite_courante()
        return scolarite.niveau if scolarite else ""

    def get_niveau_display(self):
        return dict(NIVEAUX).get(self.niveau, self.niveau)


class Scolarite(models.Model):
    eleve = models.ForeignKey(
        Eleve, on_delete=models.CASCADE, related_name="scolarites"
    )
    classe = models.ForeignKey(
        Classe, on_delete=models.PROTECT, related_name="scolarites"
    )
    annee_scolaire = models.CharField(max_length=9)
    niveau = models.CharField(max_length=2, choices=NIVEAUX)
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-annee_scolaire", "eleve__prenom", "eleve__nom"]
        constraints = [
            models.UniqueConstraint(
                fields=["eleve", "annee_scolaire"],
                name="scolarite_unique_par_eleve_annee",
            )
        ]
        indexes = [
            models.Index(
                fields=["classe", "niveau"],
                name="suivi_scola_classe__b283c1_idx",
            )
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        erreurs = {}
        if self.classe_id and self.annee_scolaire != self.classe.annee_scolaire:
            erreurs["annee_scolaire"] = "L'année doit être celle de la classe."
        if self.eleve_id and self.classe_id and self.eleve.ecole_id != self.classe.ecole_id:
            erreurs["classe"] = "L'élève et la classe doivent appartenir à la même école."
        if erreurs:
            raise ValidationError(erreurs)

    def __str__(self):
        return f"{self.eleve} — {self.niveau} {self.annee_scolaire}"


class DemandeRapprochementEleve(models.Model):
    EN_ATTENTE = "en_attente"
    VALIDEE = "validee"
    REFUSEE = "refusee"
    ETATS = [
        (EN_ATTENTE, "En attente"),
        (VALIDEE, "Validée"),
        (REFUSEE, "Refusée"),
    ]

    ecole = models.ForeignKey(
        Ecole, on_delete=models.PROTECT, related_name="demandes_rapprochement"
    )
    classe = models.ForeignKey(
        Classe, on_delete=models.PROTECT, related_name="demandes_rapprochement"
    )
    prenom_propose = models.CharField(max_length=100)
    nom_propose = models.CharField(max_length=100, blank=True)
    annee_naissance_proposee = models.PositiveSmallIntegerField(blank=True, null=True)
    niveau_propose = models.CharField(max_length=2, choices=NIVEAUX)
    demande_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="demandes_rapprochement_creees",
    )
    demande_le = models.DateTimeField(auto_now_add=True)
    etat = models.CharField(max_length=10, choices=ETATS, default=EN_ATTENTE)
    eleve_retenu = models.ForeignKey(
        Eleve,
        on_delete=models.PROTECT,
        related_name="demandes_rapprochement",
        blank=True,
        null=True,
    )
    decide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="demandes_rapprochement_decidees",
        blank=True,
        null=True,
    )
    decide_le = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["demande_le", "pk"]


class AccesParcoursEleve(models.Model):
    demande = models.OneToOneField(
        DemandeRapprochementEleve,
        on_delete=models.PROTECT,
        related_name="acces_parcours",
    )
    eleve = models.ForeignKey(
        Eleve, on_delete=models.PROTECT, related_name="acces_parcours"
    )
    classe = models.ForeignKey(
        Classe, on_delete=models.PROTECT, related_name="acces_parcours_eleves"
    )
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="acces_parcours_valides",
    )
    valide_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["eleve", "classe"],
                name="acces_parcours_unique_par_eleve_classe",
            )
        ]


class Bilan(models.Model):
    scolarite = models.ForeignKey(
        Scolarite, on_delete=models.CASCADE, related_name="bilans"
    )
    date_bilan = models.DateField()
    texte = models.TextField()
    visible_carnet = models.BooleanField(default=True)
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bilans_crees",
        blank=True,
        null=True,
    )
    dernier_editeur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bilans_modifies",
        blank=True,
        null=True,
    )
    supprime_le = models.DateTimeField(blank=True, null=True)
    supprime_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bilans_supprimes",
        blank=True,
        null=True,
    )
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date_bilan", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["scolarite", "date_bilan"],
                name="bilan_unique_par_scolarite_date",
            )
        ]

    def __str__(self):
        return f"{self.scolarite.eleve} — {self.date_bilan:%d/%m/%Y}"


class Domaine(models.Model):
    ecole = models.ForeignKey(Ecole, on_delete=models.CASCADE, related_name="domaines")
    code = models.CharField(max_length=20)
    nom = models.CharField(max_length=200)
    ordre = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["ordre"]
        unique_together = [("ecole", "code")]

    def __str__(self):
        return self.nom


class SousDomaine(models.Model):
    domaine = models.ForeignKey(
        Domaine, on_delete=models.CASCADE, related_name="sous_domaines"
    )
    code = models.CharField(max_length=30)
    nom = models.CharField(max_length=200)
    ordre = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["ordre", "nom"]
        constraints = [
            models.UniqueConstraint(
                fields=["domaine", "code"], name="sous_domaine_unique_par_domaine"
            )
        ]

    def __str__(self):
        return self.nom


class Attendu(models.Model):
    domaine = models.ForeignKey(
        Domaine, on_delete=models.CASCADE, related_name="attendus"
    )
    code = models.CharField(max_length=30)
    texte = models.TextField()
    ordre = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["ordre", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["domaine", "code"], name="attendu_unique_par_domaine"
            )
        ]

    def __str__(self):
        return self.texte


class Competence(models.Model):
    domaine = models.ForeignKey(
        Domaine, on_delete=models.CASCADE, related_name="competences"
    )
    sous_domaine = models.ForeignKey(
        SousDomaine,
        on_delete=models.SET_NULL,
        related_name="competences",
        blank=True,
        null=True,
    )
    code = models.CharField(max_length=30)
    libelle = models.CharField(max_length=300)
    niveau = models.CharField(max_length=2, choices=NIVEAUX, default="PS")
    ordre = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(
        default=True,
        help_text="Décochée, la compétence disparaît de la saisie mais les "
        "observations déjà faites sont conservées.",
    )

    class Meta:
        ordering = ["ordre"]
        verbose_name = "compétence"
        verbose_name_plural = "compétences"

    def __str__(self):
        return self.libelle


class FormulationProposee(models.Model):
    competence = models.ForeignKey(
        Competence, on_delete=models.CASCADE, related_name="formulations"
    )
    code = models.CharField(max_length=30)
    texte = models.TextField(
        help_text="Utiliser {prenom} à l'endroit où insérer le prénom de l'enfant."
    )
    ordre = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["ordre", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["competence", "code"],
                name="formulation_unique_par_competence",
            )
        ]

    def __str__(self):
        return self.texte


class Observation(models.Model):
    """Où en est un enfant sur une compétence. Une ligne par couple
    (élève, compétence).."""

    NON_DEBUTE = "non_debute"
    EN_COURS = "en_cours"
    REUSSI = "reussi"

    STATUTS = [
        (NON_DEBUTE, "Pas commencé"),
        (EN_COURS, "En cours"),
        (REUSSI, "Réussi"),
    ]

    eleve = models.ForeignKey(
        Eleve, on_delete=models.CASCADE, related_name="observations"
    )
    competence = models.ForeignKey(
        Competence, on_delete=models.CASCADE, related_name="observations"
    )
    statut = models.CharField(
        max_length=10, choices=STATUTS, default=REUSSI, blank=True, null=True
    )
    date_observation = models.DateField(default=timezone.localdate)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("eleve", "competence")]
        ordering = ["-date_observation"]

    def __str__(self):
        return f"{self.eleve} — {self.competence} ({self.get_statut_display()})"

    @property
    def trace_courante(self):
        traces_prefaites = getattr(self, "_prefetched_objects_cache", {}).get(
            "traces"
        )
        if traces_prefaites is not None:
            return max(
                (trace for trace in traces_prefaites if trace.supprime_le is None),
                key=lambda trace: (trace.date_observation, trace.pk),
                default=None,
            )
        return self.traces.filter(supprime_le__isnull=True).order_by(
            "-date_observation", "-pk"
        ).first()

    @property
    def commentaire(self):
        trace = self.trace_courante
        return trace.commentaire if trace else ""

    @property
    def photo(self):
        trace = self.trace_courante
        return trace.photo if trace else None

    def _traces_prefaites(self):
        return getattr(self, "_prefetched_objects_cache", {}).get("traces")

    @cached_property
    def a_un_commentaire(self):
        traces_prefaites = self._traces_prefaites()
        if traces_prefaites is not None:
            return any(
                trace.commentaire
                for trace in traces_prefaites
                if trace.supprime_le is None
            )
        return self.traces.filter(supprime_le__isnull=True).exclude(
            commentaire=""
        ).exists()

    @cached_property
    def a_une_photo(self):
        traces_prefaites = self._traces_prefaites()
        if traces_prefaites is not None:
            return any(
                trace.photo for trace in traces_prefaites if trace.supprime_le is None
            )
        return self.traces.filter(supprime_le__isnull=True).exclude(
            photo=""
        ).exclude(photo__isnull=True).exists()


class Trace(models.Model):
    observation = models.ForeignKey(
        Observation, on_delete=models.CASCADE, related_name="traces"
    )
    scolarite = models.ForeignKey(
        Scolarite, on_delete=models.PROTECT, related_name="traces"
    )
    date_observation = models.DateField(default=timezone.localdate)
    commentaire = models.TextField(blank=True)
    photo = models.ImageField(upload_to="traces/%Y/%m/", blank=True, null=True)
    visible_carnet = models.BooleanField(default=True)
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="traces_creees",
        blank=True,
        null=True,
    )
    dernier_editeur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="traces_modifiees",
        blank=True,
        null=True,
    )
    supprime_le = models.DateTimeField(blank=True, null=True)
    supprime_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="traces_supprimees",
        blank=True,
        null=True,
    )
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date_observation", "pk"]

    def __str__(self):
        return f"{self.observation.eleve} — {self.date_observation:%d/%m/%Y}"


class EvenementAudit(models.Model):
    ecole = models.ForeignKey(Ecole, on_delete=models.PROTECT, related_name="audit")
    acteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="evenements_audit",
    )
    action = models.CharField(max_length=80)
    modele = models.CharField(max_length=80)
    objet_id = models.CharField(max_length=80)
    anciennes_valeurs = models.JSONField(default=dict, blank=True)
    nouvelles_valeurs = models.JSONField(default=dict, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-cree_le", "-pk"]
        indexes = [models.Index(fields=["ecole", "cree_le"])]

    def __str__(self):
        return f"{self.action} {self.modele}#{self.objet_id}"
