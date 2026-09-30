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

    def libelle(self, avec_annee=False):
        """Nom court, ou libellé autonome qui reste non ambigu hors contexte."""
        if avec_annee:
            return f"{self.nom} — {self.annee_scolaire}"
        return self.nom

    @property
    def libelle_avec_annee(self):
        return self.libelle(avec_annee=True)

    @property
    def libelle_statut_annee(self):
        return {
            "courante": "année en cours",
            "future": "à venir",
            "passee": "année précédente",
            "ancienne": "année antérieure",
        }[self.statut_annee]

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
    icone = models.CharField(max_length=80, blank=True)
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


class ReglagePresentation(models.Model):
    HERITER = "heriter"
    REMPLACER = "remplacer"
    DESACTIVER = "desactiver"
    MODES = [(HERITER, "Hériter"), (REMPLACER, "Remplacer"), (DESACTIVER, "Désactiver")]
    ecole = models.ForeignKey(Ecole, on_delete=models.CASCADE)
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, blank=True, null=True)
    # Sans compétence, le réglage porte sur la photo de couverture.
    competence = models.ForeignKey(Competence, on_delete=models.PROTECT, blank=True, null=True)
    mode = models.CharField(max_length=12, choices=MODES, default=HERITER)
    icone = models.CharField(max_length=80, blank=True)
    photo = models.ImageField(upload_to="presentation/%Y/%m/", blank=True, null=True)
    dernier_editeur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["ecole", "competence"], condition=models.Q(classe__isnull=True, competence__isnull=False), name="presentation_ecole_competence_unique"),
            models.UniqueConstraint(fields=["classe", "competence"], condition=models.Q(classe__isnull=False, competence__isnull=False), name="presentation_classe_competence_unique"),
            models.UniqueConstraint(fields=["ecole"], condition=models.Q(classe__isnull=True, competence__isnull=True), name="couverture_ecole_unique"),
            models.UniqueConstraint(fields=["classe"], condition=models.Q(classe__isnull=False, competence__isnull=True), name="couverture_classe_unique"),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        from .presentation import catalogue_icones

        if self.classe_id and self.classe.ecole_id != self.ecole_id:
            raise ValidationError("La classe doit appartenir à l'école.")
        if self.competence_id and self.competence.domaine.ecole_id != self.ecole_id:
            raise ValidationError("La compétence doit appartenir à l'école.")
        if self.icone and (not self.competence_id or self.icone not in catalogue_icones()):
            raise ValidationError("Icône inconnue ou inapplicable à la couverture.")
        if self.mode == self.REMPLACER and bool(self.icone) == bool(self.photo):
            raise ValidationError("Choisissez une seule illustration : icône fournie ou image importée.")


class FormulationLocale(models.Model):
    ecole = models.ForeignKey(Ecole, on_delete=models.CASCADE)
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, blank=True, null=True)
    competence = models.ForeignKey(Competence, on_delete=models.PROTECT)
    origine = models.ForeignKey(FormulationProposee, on_delete=models.PROTECT, blank=True, null=True)
    origine_locale = models.ForeignKey("self", on_delete=models.PROTECT, related_name="adaptations", blank=True, null=True)
    mode = models.CharField(max_length=12, choices=ReglagePresentation.MODES, default=ReglagePresentation.REMPLACER)
    texte = models.TextField(blank=True)
    dernier_editeur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(fields=["ecole", "origine"], condition=models.Q(classe__isnull=True, origine__isnull=False), name="formulation_ecole_origine_unique"),
            models.UniqueConstraint(fields=["classe", "origine"], condition=models.Q(classe__isnull=False, origine__isnull=False), name="formulation_classe_origine_unique"),
            models.UniqueConstraint(fields=["classe", "origine_locale"], condition=models.Q(origine_locale__isnull=False), name="formulation_classe_locale_unique"),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.competence.domaine.ecole_id != self.ecole_id or (self.classe_id and self.classe.ecole_id != self.ecole_id):
            raise ValidationError("La formulation doit rester dans son école et sa compétence.")
        if self.origine_id and (self.origine.competence_id != self.competence_id or self.origine_locale_id):
            raise ValidationError("Origine de formulation incohérente.")
        if self.origine_locale_id:
            source = self.origine_locale
            if not self.classe_id or source.classe_id or source.ecole_id != self.ecole_id or source.competence_id != self.competence_id or source.origine_id or source.origine_locale_id:
                raise ValidationError("L'origine locale doit être une proposition ajoutée par cette école.")
        if self.mode == ReglagePresentation.REMPLACER and not self.texte.strip():
            raise ValidationError("Saisissez une formulation.")
        if self.mode == ReglagePresentation.HERITER and not (self.origine_id or self.origine_locale_id):
            raise ValidationError("Une proposition ajoutée localement ne peut pas hériter.")


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
        Competence, on_delete=models.PROTECT, related_name="observations"
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


class TraceCommune(models.Model):
    usage_referentiel = models.ForeignKey("UsageCompetence", on_delete=models.PROTECT, null=True, blank=True)
    classe = models.ForeignKey(Classe, on_delete=models.PROTECT, related_name="traces_communes")
    competence = models.ForeignKey(Competence, on_delete=models.PROTECT, related_name="traces_communes")
    date_observation = models.DateField(default=timezone.localdate)
    commentaire = models.TextField(blank=True)
    photo = models.ImageField(upload_to="traces/%Y/%m/", blank=True, null=True)
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    dernier_editeur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="traces_communes_modifiees", blank=True, null=True,
    )
    supprime_le = models.DateTimeField(blank=True, null=True)
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date_observation", "pk"]


class Trace(models.Model):
    usage_referentiel = models.ForeignKey("UsageCompetence", on_delete=models.PROTECT, null=True, blank=True)
    observation = models.ForeignKey(
        Observation, on_delete=models.CASCADE, related_name="traces"
    )
    scolarite = models.ForeignKey(
        Scolarite, on_delete=models.PROTECT, related_name="traces"
    )
    date_observation = models.DateField(default=timezone.localdate)
    commentaire = models.TextField(blank=True)
    photo = models.ImageField(upload_to="traces/%Y/%m/", blank=True, null=True)
    commune = models.ForeignKey(
        TraceCommune, on_delete=models.PROTECT, related_name="attributions",
        blank=True, null=True,
    )
    origine_commune = models.ForeignKey(
        TraceCommune, on_delete=models.PROTECT, related_name="versions_personnelles",
        blank=True, null=True,
    )
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


class SourceReferentiel(models.Model):
    """Une provenance déclarée, jamais déduite du texte d'une compétence."""
    identifiant = models.CharField(max_length=120, unique=True)
    titre = models.CharField(max_length=200)
    provenance = models.TextField(blank=True)
    licence = models.CharField(max_length=120, blank=True)
    provisoire = models.BooleanField(default=True)
    # Une source reprise appartient à son école ; les sources fournies sont publiques.
    ecole = models.ForeignKey(Ecole, on_delete=models.PROTECT, null=True, blank=True)


class VersionReferentiel(models.Model):
    source = models.ForeignKey(SourceReferentiel, on_delete=models.PROTECT, related_name="versions")
    numero = models.CharField(max_length=80)
    empreinte = models.CharField(max_length=64)
    contenu = models.JSONField()
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["source", "numero"], name="version_source_unique")]

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError

        if self.pk:
            ancienne = type(self).objects.get(pk=self.pk)
            if any(getattr(ancienne, champ) != getattr(self, champ)
                   for champ in ("source_id", "numero", "empreinte", "contenu")):
                raise ValidationError("Une version publiée ne peut pas être modifiée.")
        return super().save(*args, **kwargs)


class IdentiteSourceCompetence(models.Model):
    """Identité déclarée par une source, indépendante des textes et codes."""
    source = models.ForeignKey(SourceReferentiel, on_delete=models.PROTECT, related_name="identites")
    identifiant = models.CharField(max_length=120)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["source", "identifiant"], name="identite_source_unique")]


class DefinitionSourceCompetence(models.Model):
    identite = models.ForeignKey(IdentiteSourceCompetence, on_delete=models.PROTECT, related_name="definitions")
    version = models.ForeignKey(VersionReferentiel, on_delete=models.PROTECT, related_name="definitions")
    # Structure, libellé et ressources restent dans le contenu immuable de la version.
    class Meta:
        constraints = [models.UniqueConstraint(fields=["version", "identite"], name="definition_identite_version_unique")]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.identite_id and self.version_id and self.identite.source_id != self.version.source_id:
            raise ValidationError("La définition et l'identité doivent appartenir à la même source.")


class CompetenceSourceEcole(models.Model):
    ecole = models.ForeignKey(Ecole, on_delete=models.PROTECT)
    identite = models.ForeignKey(IdentiteSourceCompetence, on_delete=models.PROTECT)
    competence = models.OneToOneField(Competence, on_delete=models.PROTECT, related_name="origine_source")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["ecole", "identite"], name="identite_suivi_source_ecole_unique")]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.competence_id and self.ecole_id and self.competence.domaine.ecole_id != self.ecole_id:
            raise ValidationError("L'identité de suivi doit appartenir à l'école.")


class VersionSourceEcole(models.Model):
    ecole = models.ForeignKey(Ecole, on_delete=models.PROTECT)
    version = models.ForeignKey(VersionReferentiel, on_delete=models.PROTECT)
    contenu = models.JSONField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["ecole", "version"], name="version_source_ecole_unique")]

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        if self.pk:
            ancienne = type(self).objects.get(pk=self.pk)
            if any(getattr(ancienne, champ) != getattr(self, champ) for champ in ("ecole_id", "version_id", "contenu")):
                raise ValidationError("La définition d'une version dans une école ne peut pas être modifiée.")
        return super().save(*args, **kwargs)


class ChoixApplicationAnnuel(models.Model):
    annee_scolaire = models.CharField(max_length=9, unique=True)
    configure = models.BooleanField(default=False)
    versions_autorisees = models.ManyToManyField(VersionReferentiel, blank=True, related_name="choix_application")
    version_proposee = models.ForeignKey(VersionReferentiel, on_delete=models.PROTECT, null=True, blank=True, related_name="defauts_application")
    revision = models.PositiveIntegerField(default=0)


class ChoixEcoleAnnuel(models.Model):
    ecole = models.ForeignKey(Ecole, on_delete=models.PROTECT, related_name="choix_bases_annuels")
    annee_scolaire = models.CharField(max_length=9)
    # False suit les autorisations supérieures ; True conserve une liste explicite.
    restreindre = models.BooleanField(default=False)
    versions_autorisees = models.ManyToManyField(VersionReferentiel, blank=True, related_name="choix_ecoles")
    # Null suit le défaut supérieur, sans choisir la première base disponible.
    version_proposee = models.ForeignKey(VersionReferentiel, on_delete=models.PROTECT, null=True, blank=True, related_name="defauts_ecoles")
    revision = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["ecole", "annee_scolaire"], name="choix_bases_ecole_annee_unique")]


class ReferentielAnnuel(models.Model):
    """Choix d'une école pour une année ; état initial distinct d'une histoire reconstruite."""
    ecole = models.ForeignKey(Ecole, on_delete=models.PROTECT, related_name="referentiels_annuels")
    annee_scolaire = models.CharField(max_length=9)
    version_proposee = models.ForeignKey(VersionReferentiel, on_delete=models.PROTECT)
    etat_initial = models.JSONField(default=dict)
    origine_reprise = models.BooleanField(default=False)
    historique_reconstitue = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["ecole", "annee_scolaire"], name="referentiel_ecole_annee_unique")]


class AdoptionReferentiel(models.Model):
    contenu = models.JSONField(default=dict, blank=True)
    clos = models.BooleanField(default=False)
    etat_final = models.JSONField(default=dict, blank=True)
    classe = models.ForeignKey(Classe, on_delete=models.PROTECT, related_name="adoptions_referentiel")
    annuel = models.ForeignKey(ReferentielAnnuel, on_delete=models.PROTECT)
    version = models.ForeignKey(VersionReferentiel, on_delete=models.PROTECT)
    courante = models.BooleanField(default=True)
    # Pas de date d'adoption inventée lors de la reprise.
    adopte_le = models.DateTimeField(null=True, blank=True)
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    reprise = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["classe"], condition=models.Q(courante=True), name="adoption_courante_classe_unique")]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.classe_id and self.annuel_id and (
            self.classe.ecole_id != self.annuel.ecole_id
            or self.classe.annee_scolaire != self.annuel.annee_scolaire
        ):
            raise ValidationError("La classe et les choix annuels doivent appartenir à la même école et année.")
        if self.version_id and self.classe_id and self.version.source.ecole_id not in (None, self.classe.ecole_id):
            raise ValidationError("Cette version appartient à une autre école.")


class UsageCompetence(models.Model):
    adoption = models.ForeignKey(AdoptionReferentiel, on_delete=models.PROTECT, related_name="usages")
    competence = models.ForeignKey(Competence, on_delete=models.PROTECT, related_name="usages_referentiel")
    # Identifiant repris de la clé locale ; ne prétend pas être un code source officiel.
    cle_definition = models.CharField(max_length=120)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["adoption", "competence"], name="usage_adoption_competence_unique")]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.adoption_id and self.competence_id and self.adoption.classe.ecole_id != self.competence.domaine.ecole_id:
            raise ValidationError("La compétence doit appartenir à l'école de la classe.")


class EtatAnnuelObservation(models.Model):
    observation = models.ForeignKey(Observation, on_delete=models.PROTECT, related_name="etats_annuels")
    annee_scolaire = models.CharField(max_length=9)
    usage = models.ForeignKey(UsageCompetence, on_delete=models.PROTECT, null=True, blank=True)
    statut = models.CharField(max_length=10, choices=Observation.STATUTS, null=True, blank=True)
    date_observation = models.DateField(null=True, blank=True)
    # Inconnu permet de conserver un contexte annuel sans fabriquer un état passé.
    connu = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["observation", "annee_scolaire"], name="etat_observation_annee_unique")]

    def clean(self):
        from django.core.exceptions import ValidationError

        if not self.connu and (self.statut is not None or self.date_observation is not None):
            raise ValidationError("Un état historique inconnu ne peut pas porter une réussite ou une date.")
        if self.usage_id and self.observation_id and (
            self.usage.competence_id != self.observation.competence_id
            or self.usage.adoption.classe.ecole_id != self.observation.eleve.ecole_id
            or self.usage.adoption.classe.annee_scolaire != self.annee_scolaire
        ):
            raise ValidationError("Le contexte doit correspondre à la compétence, à l'école et à l'année.")


class RessourceReferentiel(models.Model):
    """Référence privée à un fichier encore nécessaire à une présentation annuelle."""
    annuel = models.ForeignKey(ReferentielAnnuel, on_delete=models.PROTECT, related_name="ressources")
    fichier = models.FileField(upload_to="referentiels/%Y/%m/")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["annuel", "fichier"], name="ressource_annuelle_fichier_unique")]


class AdaptationCompetence(models.Model):
    """Libellé et visibilité annuels, indépendants de l'identité de suivi."""
    ecole = models.ForeignKey(Ecole, on_delete=models.PROTECT, related_name="adaptations_referentiel")
    annee_scolaire = models.CharField(max_length=9)
    classe = models.ForeignKey(Classe, on_delete=models.PROTECT, null=True, blank=True,
                              related_name="adaptations_referentiel")
    competence = models.ForeignKey(Competence, on_delete=models.PROTECT, related_name="adaptations_annuelles")
    # Chaque propriété laissée à None suit séparément le niveau supérieur.
    libelle = models.CharField(max_length=300, null=True, blank=True)
    visible = models.BooleanField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["ecole", "annee_scolaire", "competence"],
                condition=models.Q(classe__isnull=True), name="adaptation_competence_ecole_annee_unique"),
            models.UniqueConstraint(fields=["classe", "competence"],
                condition=models.Q(classe__isnull=False), name="adaptation_competence_classe_unique"),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        from .services.choix_bases_referentiels import verifier_annee
        verifier_annee(self.annee_scolaire)
        if self.competence_id and self.competence.domaine.ecole_id != self.ecole_id:
            raise ValidationError("La compétence doit appartenir à l'école.")
        if self.classe_id and (self.classe.ecole_id != self.ecole_id or self.classe.annee_scolaire != self.annee_scolaire):
            raise ValidationError("L'adaptation doit appartenir à l'école et à l'année de la classe.")
        if self.libelle is not None and not self.libelle.strip():
            raise ValidationError("Le libellé adapté ne peut pas être vide.")


class CompetenceLocale(models.Model):
    """Identité locale et définition d'origine, indépendantes des bases fournies."""
    ecole = models.ForeignKey(Ecole, on_delete=models.PROTECT)
    competence = models.OneToOneField(Competence, on_delete=models.PROTECT, related_name="origine_locale")
    classe_origine = models.ForeignKey(Classe, on_delete=models.PROTECT, null=True, blank=True)
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    cree_le = models.DateTimeField(default=timezone.now)
    definition = models.JSONField()

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.competence_id and self.competence.domaine.ecole_id != self.ecole_id:
            raise ValidationError("L'ajout doit appartenir à l'école.")
        if self.classe_origine_id and self.classe_origine.ecole_id != self.ecole_id:
            raise ValidationError("La classe d'origine doit appartenir à l'école.")

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        if self.pk:
            ancienne = type(self).objects.get(pk=self.pk)
            champs = ("ecole_id", "competence_id", "classe_origine_id", "auteur_id", "cree_le", "definition")
            if any(getattr(self, c) != getattr(ancienne, c) for c in champs):
                raise ValidationError("L'origine d'un ajout est conservée. Utilisez les adaptations annuelles.")
        return super().save(*args, **kwargs)


class DisponibiliteCompetenceLocale(models.Model):
    """Proposition annuelle à l'école ou reprise explicite par une classe."""
    locale = models.ForeignKey(CompetenceLocale, on_delete=models.PROTECT, related_name="disponibilites")
    annee_scolaire = models.CharField(max_length=9)
    classe = models.ForeignKey(Classe, on_delete=models.PROTECT, null=True, blank=True)
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    cree_le = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["locale", "annee_scolaire"], condition=models.Q(classe__isnull=True),
                                    name="ajout_propose_ecole_annee_unique"),
            models.UniqueConstraint(fields=["locale", "classe"], condition=models.Q(classe__isnull=False),
                                    name="ajout_repris_classe_unique"),
        ]

    @property
    def ecole(self):
        return self.locale.ecole

    def clean(self):
        from django.core.exceptions import ValidationError
        from .services.choix_bases_referentiels import verifier_annee
        verifier_annee(self.annee_scolaire)
        if self.classe_id and (self.classe.ecole_id != self.locale.ecole_id or
                              self.classe.annee_scolaire != self.annee_scolaire):
            raise ValidationError("La reprise doit appartenir à l'école et à l'année de la classe.")


class CorrespondanceCompetence(models.Model):
    """Lien pédagogique orienté ; ne fusionne ni compétences ni observations."""
    TYPES = [("lien", "En lien avec"), ("precise", "Précise cette compétence"),
             ("remplace", "Remplace cette compétence")]
    ecole = models.ForeignKey(Ecole, on_delete=models.PROTECT)
    annee_scolaire = models.CharField(max_length=9)
    classe = models.ForeignKey(Classe, on_delete=models.PROTECT, null=True, blank=True)
    depart = models.ForeignKey(Competence, on_delete=models.PROTECT, related_name="correspondances_sortantes")
    arrivee = models.ForeignKey(Competence, on_delete=models.PROTECT, related_name="correspondances_entrantes")
    version_depart = models.ForeignKey(VersionReferentiel, on_delete=models.PROTECT, null=True, blank=True,
                                      related_name="correspondances_sortantes")
    version_arrivee = models.ForeignKey(VersionReferentiel, on_delete=models.PROTECT, null=True, blank=True,
                                       related_name="correspondances_entrantes")
    # Références et textes d'origine au moment de la validation, jamais réinterprétés.
    reference_depart = models.CharField(max_length=100)
    reference_arrivee = models.CharField(max_length=100)
    origine_depart = models.JSONField()
    origine_arrivee = models.JSONField()
    type_lien = models.CharField(max_length=10, choices=TYPES)
    justification = models.TextField(max_length=1000)
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="correspondances_validees")
    cree_le = models.DateTimeField(default=timezone.now)
    active = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=0)
    retire_le = models.DateTimeField(null=True, blank=True)
    retire_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                  related_name="correspondances_retirees")

    class Meta:
        constraints = [
            models.CheckConstraint(condition=~models.Q(depart=models.F("arrivee")), name="correspondance_pas_vers_soi"),
            models.UniqueConstraint(fields=["ecole", "annee_scolaire", "reference_depart", "reference_arrivee", "type_lien"],
                condition=models.Q(classe__isnull=True, active=True), name="correspondance_ecole_active_unique"),
            models.UniqueConstraint(fields=["classe", "reference_depart", "reference_arrivee", "type_lien"],
                condition=models.Q(classe__isnull=False, active=True), name="correspondance_classe_active_unique"),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        from .services.choix_bases_referentiels import verifier_annee
        verifier_annee(self.annee_scolaire)
        if self.depart_id == self.arrivee_id:
            raise ValidationError("Une compétence ne peut pas être reliée à elle-même, même dans deux versions.")
        for competence in (self.depart, self.arrivee):
            if competence.domaine.ecole_id != self.ecole_id:
                raise ValidationError("Les deux compétences doivent appartenir à l'école.")
        if self.classe_id and (self.classe.ecole_id != self.ecole_id or self.classe.annee_scolaire != self.annee_scolaire):
            raise ValidationError("Le lien doit appartenir à l'école et à l'année de la classe.")
        for version in (self.version_depart, self.version_arrivee):
            if version and version.source.ecole_id not in (None, self.ecole_id):
                raise ValidationError("Une version d'origine appartient à une autre école.")
        for origine, competence_id, version_id, reference in (
            (self.origine_depart, self.depart_id, self.version_depart_id, self.reference_depart),
            (self.origine_arrivee, self.arrivee_id, self.version_arrivee_id, self.reference_arrivee)):
            if not isinstance(origine, dict) or origine.get("competence_id") != competence_id or (
                    origine.get("version_id") != version_id or origine.get("reference") != reference):
                raise ValidationError("Les origines doivent correspondre aux compétences et versions reliées.")
        if not self.justification.strip():
            raise ValidationError("Expliquez pourquoi vous reliez ces apprentissages.")

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        if self.pk:
            ancienne = type(self).objects.get(pk=self.pk)
            champs = ("ecole_id", "annee_scolaire", "classe_id", "depart_id", "arrivee_id",
                "version_depart_id", "version_arrivee_id", "reference_depart", "reference_arrivee",
                "origine_depart", "origine_arrivee", "type_lien", "justification", "auteur_id", "cree_le")
            if any(getattr(self, c) != getattr(ancienne, c) for c in champs):
                raise ValidationError("Ce lien est conservé. Retirez-le puis créez un lien corrigé.")
        return super().save(*args, **kwargs)
