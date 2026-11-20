"""Sélection de classe commune à la grille et aux éditions."""
from dataclasses import dataclass
from itertools import groupby

from django import forms
from django.http import QueryDict

from .lectures_eleves import avec_scolarites_pour_lecture
from .models import Observation, Trace, bornes_annee_scolaire
from .referentiels import arbre_competences, observations_classe
from .templatetags.suivi_libre import groupes_suivi


@dataclass(frozen=True)
class Colonne:
    numero: int
    competence: object
    rubrique: str
    sous_rubrique: str
    groupe: str


class FiltresEdition(forms.Form):
    modes = (
        ("observes", "Compétences observées cette année"),
        ("tout", "Toutes les compétences suivies"),
        ("periode", "Observations sur une période"),
        ("reussites", "Réussites constatées sur une période"),
    )
    sections = [("PS", "PS"), ("MS", "MS"), ("GS", "GS")]
    eleves = forms.MultipleChoiceField(required=False)
    sections_eleves = forms.MultipleChoiceField(label="Section des élèves", required=False,
                                                choices=sections, widget=forms.CheckboxSelectMultiple)
    rubriques = forms.MultipleChoiceField(label="Rubriques et sous-rubriques", required=False, widget=forms.CheckboxSelectMultiple)
    competences = forms.MultipleChoiceField(label="Compétences précises", required=False, widget=forms.CheckboxSelectMultiple)
    niveaux = forms.MultipleChoiceField(label="Section de classement des compétences", required=False,
                                        choices=sections, widget=forms.CheckboxSelectMultiple)
    observations = forms.ChoiceField(choices=(("", "Selon la sélection"), *modes), required=False)
    debut = forms.DateField(label="Du", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    fin = forms.DateField(label="Au", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    compacte = forms.ChoiceField(label="Présentation de la grille", required=False, choices=(
        ("", "Automatique"), ("oui", "Compacte"), ("non", "Libellés complets"), ("lecture", "Une compétence à la fois"),
    ))

    def __init__(self, classe, donnees, *, competence=None, initial=None):
        super().__init__(donnees, initial=initial)
        self.classe = classe
        self.eleves = list(avec_scolarites_pour_lecture(classe.eleves))
        self.fields["eleves"].choices = [(str(e.pk), e.nom_court) for e in self.eleves]
        self.colonnes = []
        rubriques = []
        for domaine in arbre_competences(classe.ecole, classe=classe,
                inclure_ids=[competence.pk] if competence else ()):
            racine = str(domaine.pk)
            rubriques.append((racine, domaine.nom))
            for cle, nom, lignes in groupes_suivi(domaine, domaine.visibles):
                if not lignes:
                    continue
                groupe = f"{racine}/{cle}" if cle else racine
                if cle:
                    rubriques.append((groupe, f"{domaine.nom} › {nom}"))
                self.colonnes.extend(Colonne(0, c, domaine.nom, nom, groupe) for c in lignes)
        self.fields["rubriques"].choices = list(dict(rubriques).items())
        self.fields["competences"].choices = list({str(c.competence.pk): c.competence.libelle for c in self.colonnes}.items())

    def clean(self):
        valeurs = super().clean()
        mode = valeurs.get("observations")
        debut, fin = valeurs.get("debut"), valeurs.get("fin")
        if mode in {"periode", "reussites"}:
            if not debut:
                self.add_error("debut", "Indiquez le début de la période.")
            if not fin:
                self.add_error("fin", "Indiquez la fin de la période.")
            if debut and fin and fin < debut:
                self.add_error("fin", "La fin doit suivre le début.")
        else:
            valeurs["debut"] = valeurs["fin"] = None
        return valeurs

    def parametres(self):
        resultat = QueryDict(mutable=True)
        if self.is_valid():
            for cle, valeur in self.cleaned_data.items():
                if valeur:
                    valeurs = valeur if isinstance(valeur, list) else [valeur]
                    resultat.setlist(cle, [str(v) for v in valeurs])
        return resultat

    def enfants(self, *, tous=False):
        ids = set(self.cleaned_data.get("eleves") or ())
        sections = set(self.cleaned_data.get("sections_eleves") or ())
        enfants = [e for e in self.eleves if (tous and not ids) or str(e.pk) in ids]
        if not sections:
            return enfants
        niveaux = dict(self.classe.scolarites.values_list("eleve_id", "niveau"))
        return [e for e in enfants if niveaux.get(e.pk) in sections]

    def competences_retenues(self, eleves, *, force=None):
        donnees = self.cleaned_data
        ids = set(donnees.get("competences") or ())
        rubriques = set(donnees.get("rubriques") or ())
        niveaux = set(donnees.get("niveaux") or ())
        colonnes = [c for c in self.colonnes if (
            c.competence.pk == force.pk if force else (
                (not niveaux or c.competence.niveau in niveaux) and (
                    not (ids or rubriques) or str(c.competence.pk) in ids
                    or c.groupe in rubriques or c.groupe.split("/")[0] in rubriques)
            ))]
        mode = donnees.get("observations") or ("tout" if ids or rubriques or force else "observes")
        if mode != "tout" and not force:
            enfants = [e.pk for e in eleves]
            traces = Trace.objects.filter(scolarite__classe=self.classe,
                observation__eleve_id__in=enfants, supprime_le__isnull=True)
            etats = observations_classe(self.classe).filter(eleve_id__in=enfants, connu_lecture=True)
            if mode in {"periode", "reussites"}:
                debut_annee, fin_annee = bornes_annee_scolaire(self.classe.annee_scolaire)
                intervalle = (max(donnees["debut"], debut_annee), min(donnees["fin"], fin_annee))
                traces = traces.filter(date_observation__range=intervalle)
                if mode == "reussites":
                    traces = traces.filter(reussite=True)
                    etats = etats.filter(reussite_datee_lecture__range=intervalle)
                else:
                    etats = etats.filter(date_lecture__range=intervalle)
            if mode != "reussites":
                etats = etats.filter(statut_lecture__in=(Observation.EN_COURS, Observation.REUSSI))
            signalees = set(traces.values_list("observation__competence_id", flat=True))
            signalees.update(etats.values_list("competence_id", flat=True))
            colonnes = [c for c in colonnes if c.competence.pk in signalees]
        uniques = {}
        for colonne in colonnes:
            uniques.setdefault(colonne.competence.pk, colonne)
        return [Colonne(i, c.competence, c.rubrique, c.sous_rubrique, c.groupe)
                for i, c in enumerate(uniques.values(), 1)]


def groupes_colonnes(colonnes, maximum):
    """Découpe aux frontières des sous-rubriques et plafonne chaque groupe."""
    for _, groupe in groupby(colonnes, key=lambda c: c.groupe):
        groupe = list(groupe)
        for debut in range(0, len(groupe), maximum):
            yield groupe[debut:debut + maximum]


def en_tetes(colonnes, attribut):
    return [(nom, len(list(groupe))) for nom, groupe in groupby(
        colonnes, key=lambda c: getattr(c, attribut))]


def planches_cartes(carnets, options, filtres):
    """Conserve chaque carte entière dans une planche de dimensions régulières."""
    cartes = []
    periode = filtres.get("observations") in {"periode", "reussites"}
    par_competence = options.get("unite") == "competence"
    for carnet in carnets:
        deja = set()
        for domaine, groupes in carnet["domaines"]:
            for _, lignes in groupes:
                for competence, observation in lignes:
                    if competence.pk in deja:
                        continue
                    deja.add(competence.pk)
                    traces = list(getattr(observation, "traces_carnet", ()))
                    if periode:
                        traces = [t for t in traces if filtres["debut"] <= t.date_observation <= filtres["fin"]
                                  and (filtres["observations"] != "reussites" or t.reussite)]
                    for trace in ([None] if par_competence else traces):
                        cartes.append({"eleve": carnet["eleve"], "rubrique": domaine.nom,
                                       "rubrique_id": domaine.pk, "competence": competence, "trace": trace})
    compact = "planches_compactes" in options
    if compact and options.get("ordre_cartes") == "rubrique":
        ordre_rubriques = {identifiant: i for i, identifiant in enumerate(
            dict.fromkeys(c["rubrique_id"] for c in cartes))}
        cartes.sort(key=lambda c: (ordre_rubriques[c["rubrique_id"]], c["eleve"].nom_court))
    taille = 4 if "grandes_cartes" in options else 8
    groupes = [cartes] if compact else [list(g) for _, g in groupby(cartes, key=lambda c: c["eleve"].pk)]
    return [g[i:i + taille] for g in groupes for i in range(0, len(g), taille)]


def options_carnet(donnees, parametres, *, cases_postees=False):
    """Normalise les options de lecture et de rendu, pour un élève ou un lot."""
    options = {}
    for cle, defaut, valeurs, repli in (
        ("contenu", parametres.contenu_par_defaut, {"reussites", "observes", "tout"}, "observes"),
        ("colonnes", str(parametres.colonnes_par_defaut), {"1", "2"}, "2"),
        ("regroupement", parametres.regroupement_par_defaut, {"aucun", "annuel", "mensuel", "bilan"}, "aucun"),
    ):
        valeur = donnees.get(cle, defaut)
        options[cle] = valeur if valeur in valeurs else repli
    if donnees.get("tout") == "1":
        options["contenu"] = "tout"
    for cle, defaut in (
        ("attendus", parametres.afficher_attendus),
        ("sous_domaines", parametres.afficher_sous_domaines),
        ("bilans", parametres.inclure_bilans),
    ):
        valeur = donnees.get(cle)
        active = valeur in {"1", "on"} if valeur is not None else defaut and not cases_postees
        options[cle] = "1" if active else "0"
    return options
