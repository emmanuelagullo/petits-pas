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

    def __str__(self):
        return self.nom


class Eleve(models.Model):
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name="eleves")
    prenom = models.CharField(max_length=100)
    nom = models.CharField(max_length=100, blank=True)
    niveau = models.CharField(max_length=2, choices=NIVEAUX, default="PS")

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
    commentaire = models.TextField(blank=True)
    photo = models.ImageField(upload_to="traces/%Y/%m/", blank=True, null=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("eleve", "competence")]
        ordering = ["-date_observation"]

    def __str__(self):
        return f"{self.eleve} — {self.competence} ({self.get_statut_display()})"
