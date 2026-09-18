from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone

NIVEAUX = [
    ("PS", "Petite section"),
    ("MS", "Moyenne section"),
    ("GS", "Grande section"),
]


class Ecole(models.Model):
    """Une école. La V0 n'en héberge qu'une, mais tout est déjà rattaché à
    l'école pour que l'ouverture à plusieurs établissements ne demande pas
    de migration douloureuse."""

    nom = models.CharField(max_length=200)
    commune = models.CharField(max_length=200, blank=True)
    mdp_enseignant = models.CharField(max_length=256, editable=False)
    mdp_direction = models.CharField(max_length=256, editable=False)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "école"
        verbose_name_plural = "écoles"

    def __str__(self):
        return self.nom

    def definir_mots_de_passe(self, enseignant, direction):
        self.mdp_enseignant = make_password(enseignant)
        self.mdp_direction = make_password(direction)

    def verifier(self, mot_de_passe):
        """Renvoie 'direction', 'enseignant' ou None."""
        if self.mdp_direction and check_password(mot_de_passe, self.mdp_direction):
            return "direction"
        if self.mdp_enseignant and check_password(mot_de_passe, self.mdp_enseignant):
            return "enseignant"
        return None


class Classe(models.Model):
    ecole = models.ForeignKey(Ecole, on_delete=models.CASCADE, related_name="classes")
    nom = models.CharField(max_length=100, help_text="Par exemple : PS-MS de Nadia")
    annee_scolaire = models.CharField(max_length=9, default="2026-2027")
    ordre = models.PositiveSmallIntegerField(default=0)

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

    @property
    def eleves(self):
        return Eleve.objects.filter(
            scolarites__classe=self,
            archive_le__isnull=True,
        ).distinct()


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


class Bilan(models.Model):
    scolarite = models.ForeignKey(
        Scolarite, on_delete=models.CASCADE, related_name="bilans"
    )
    date_bilan = models.DateField()
    texte = models.TextField()
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


class Competence(models.Model):
    domaine = models.ForeignKey(
        Domaine, on_delete=models.CASCADE, related_name="competences"
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
    statut = models.CharField(max_length=10, choices=STATUTS, default=REUSSI)
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
                traces_prefaites,
                key=lambda trace: (trace.date_observation, trace.pk),
                default=None,
            )
        return self.traces.order_by("-date_observation", "-pk").first()

    @property
    def commentaire(self):
        trace = self.trace_courante
        return trace.commentaire if trace else ""

    @property
    def photo(self):
        trace = self.trace_courante
        return trace.photo if trace else None


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
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date_observation", "pk"]

    def __str__(self):
        return f"{self.observation.eleve} — {self.date_observation:%d/%m/%Y}"
