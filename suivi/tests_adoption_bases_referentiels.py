from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings
from django.urls import reverse

from .models import AdaptationCompetence, AdoptionReferentiel, Classe, Competence, Eleve, EtatAnnuelObservation, Observation, Scolarite, Trace, TraceCommune, VersionSourceEcole
from .presentation import illustration_effective, propositions
from .referentiels import arbre_competences, observations_annee
from .services.adoption_bases_referentiels import apercu_adoption, adopter_base
from .services.choix_bases_referentiels import publier_choix_application
from .services.cloture_referentiels import clore
from .services.contextes_referentiels import usage_pour_saisie
from .services.pedagogie import modifier_etat
from .services.reprise_referentiels import reprendre
from .tests import Base
from .tests_import_sources_referentiels import document, importer


class AdoptionBases(Base):
    def setUp(self):
        super().setUp()
        reprendre(self.ecole.pk)
        doc = document()
        doc["domaines"][0]["competences"][0].update(icone="parler", formulations=[{"code": "p1", "texte": "<prénom> prend la parole."}])
        self.a = importer(doc)[0]
        self.b = importer(document("autre-fictive"))[0]
        publier_choix_application(annee=self.classe.annee_scolaire, versions_ids=[self.a.pk, self.b.pk],
            proposee_id=self.a.pk, revision_attendue=0)
        self.entrer()

    def adopter(self, version=None):
        version = version or self.a
        apercu = apercu_adoption(utilisateur=self.enseignant, classe=self.classe, version_id=version.pk)
        if apercu["garde"]["niveau"] == "rouge" and not apercu["meme"]:
            from .fixtures_garde_fous import ouvrir_exception_fictive
            ouvrir_exception_fictive(self.classe)
            apercu = apercu_adoption(utilisateur=self.enseignant, classe=self.classe, version_id=version.pk)
        return adopter_base(utilisateur=self.enseignant, classe=self.classe, version_id=version.pk,
            revisions_attendues=apercu["revisions"], adoption_attendue=apercu["adoption_id"],
            garde_attendue=apercu["garde"]["empreinte"])

    def test_deplacement_catalogue_local_et_retour_filtre(self):
        from .exports_classe import selection_classe
        from .models import Domaine, SousDomaine
        from .referentiels import contenu_adoption
        from .services.rubriques import enregistrer_rubrique

        adoption = self.adopter()
        competence = adoption.usages.get().competence
        modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=competence, statut="reussi")
        originale = competence.domaine_id
        options = dict(adoption_id=adoption.pk, rubrique_id=None, ordre=1, masquee=False)
        enregistrer_rubrique(self.enseignant, self.classe, genre="domaine", domaine_id=None, nom="Atelier", **options)
        domaine = Domaine.objects.get(nom="Atelier")
        enregistrer_rubrique(self.enseignant, self.classe, genre="sous_domaine", domaine_id=domaine.pk,
                             nom="Oral", **options)
        groupe = SousDomaine.objects.get(domaine=domaine)
        catalogue = reverse("catalogue_competences", args=[self.classe.pk])
        params = {"q": "parle", "domaine": "Langage", "deplacement": competence.pk}
        page = self.client.get(catalogue, params)
        self.assertContains(page, "Emplacement actuel · Langage")
        url = page.wsgi_request.get_full_path()
        reponse = self.client.post(url, {"domaine": domaine.pk, "sous_domaine": groupe.pk,
            "jeton": page.context["deplacement"]["jeton"]}, follow=True)
        self.assertContains(reponse, "Déplacée vers Atelier → Oral.")
        self.assertContains(reponse, "Voir dans la rubrique")
        self.assertIn("q=parle", reponse.context["url_deplacement"])
        ligne = next(c for c in contenu_adoption(adoption)["competences"] if c["id"] == competence.pk)
        self.assertEqual((ligne["domaine_id"], ligne["sous_domaine_id"]), (domaine.pk, groupe.pk))
        competence.refresh_from_db()
        self.assertEqual(competence.domaine_id, originale)
        self.assertTrue(Observation.objects.filter(competence=competence, statut="reussi").exists())
        selection, _ = selection_classe(self.classe, self.enseignant)
        self.assertTrue(SousDomaine.objects.filter(selection[SousDomaine], pk=groupe.pk).exists())

    def test_catalogue_masque_et_reaffiche_une_competence_ciblee(self):
        from .models import EleveApprentissage
        from .referentiels import competence_saisissable
        from .services.ajouts_referentiels import creer_ajout
        from .services.suivi_libre import associer

        adoption = self.adopter()
        locale = creer_ajout(utilisateur=self.enseignant, ecole=self.ecole, annee=self.classe.annee_scolaire,
            classe=self.classe, adoption_attendue=adoption.pk, domaine_id=adoption.contenu["domaines"][0]["id"],
            libelle="J’écoute mon voisin", niveau="PS", suivi_libre=True)
        associer(utilisateur=self.enseignant, classe=self.classe, locale=locale, ids=[self.eleve.pk],
                 adoption_attendue=adoption.pk)
        competence = locale.competence
        modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=competence, statut="reussi")
        url = reverse("catalogue_competences", args=[self.classe.pk])
        action = {"action": "visibilite_catalogue", "competence": competence.pk, "adoption": adoption.pk}
        self.assertRedirects(self.client.post(url, {**action, "visibilite": "masquer", "revision": 0}), url)
        self.assertNotContains(self.client.get(url), competence.libelle)
        filtre = f"{url}?inclure_competences_masquees=1"
        self.assertContains(self.client.get(filtre), competence.libelle)
        self.assertContains(self.client.get(filtre), "Réafficher")
        self.assertFalse(competence_saisissable(self.classe, competence, eleve=self.eleve))
        self.assertRedirects(self.client.post(filtre, {**action, "visibilite": "reafficher", "revision": 1}), filtre)
        self.assertTrue(competence_saisissable(self.classe, competence, eleve=self.eleve))
        self.assertTrue(EleveApprentissage.objects.filter(disponibilite__locale=locale, active=True).exists())
        self.assertTrue(Observation.objects.filter(competence=competence, statut="reussi").exists())

    def test_saisie_collective_cree_seulement_sans_correspondance(self):
        self.adopter()
        url = reverse("choisir_competence", args=[self.classe.pk])
        page = self.client.get(url, {"q": "parlé", "niveau": "GS", "fragment": 1})
        self.assertEqual(page.headers["X-Petits-Pas-Catalogue"], "1")
        self.assertContains(page, "Des compétences correspondent en dehors des filtres actuels.")
        self.assertFalse(page.context["creer_en_priorite"])
        page = self.client.get(url, {"q": "zqjx inventée"})
        self.assertContains(page, "Créer « zqjx inventée »")
        self.assertNotContains(page, "Configurer le référentiel de la classe")
        creation = self.client.get(page.context["url_creation_ciblee"])
        self.assertEqual(creation.context["form"].initial["libelle"], "zqjx inventée")
        self.assertContains(creation, f"{url}?q=")
        page = self.client.get(url, {"q": "parlé"})
        self.assertContains(page, "Ouvrir le suivi")
        detail = self.client.get(page.context["lignes"][0]["url"])
        self.assertEqual(detail.context["ariane"][-1][1], page.context["url_resultats"])

    def test_rubriques_classe_activation_masquage_et_cloture(self):
        from .exports_classe import selection_classe
        from .models import Domaine, RubriqueClasse, SousDomaine
        from .referentiels import contenu_adoption
        from .services.ajouts_referentiels import creer_ajout
        adoption = self.adopter()
        url = reverse("gerer_rubriques", args=[self.classe.pk])
        base = {"adoption_id": adoption.pk, "ordre": 2}
        self.assertRedirects(self.client.post(url, {**base, "genre": "domaine", "nom": "Projets"}), url)
        domaine = Domaine.objects.get(nom="Projets")
        self.assertRedirects(self.client.post(url, {**base, "genre": "sous_domaine", "domaine_id": domaine.pk,
            "nom": "Jardin"}), url)
        sous = SousDomaine.objects.get(domaine=domaine)
        self.assertTrue(RubriqueClasse.objects.filter(classe=self.classe, sous_domaine=sous, creee=True).exists())
        ajout = creer_ajout(utilisateur=self.enseignant, ecole=self.ecole, annee=self.classe.annee_scolaire,
            classe=self.classe, adoption_attendue=adoption.pk, domaine_id=domaine.pk, sous_domaine_id=sous.pk,
            libelle="Je plante une graine", niveau="PS")
        self.assertEqual(ajout.competence.sous_domaine_id, sous.pk)
        modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=ajout.competence, statut="reussi")
        self.assertRedirects(self.client.post(url, {**base, "genre": "domaine", "rubrique_id": domaine.pk,
            "nom": "Projets collectifs", "ordre": 1, "masquee": "on"}), url)
        collectif = reverse("choisir_competence", args=[self.classe.pk])
        self.assertNotContains(self.client.get(collectif), "Je plante une graine")
        self.assertContains(self.client.get(collectif, {"inclure_masquees": 1}), "Je plante une graine")
        self.assertTrue(Observation.objects.filter(competence=ajout.competence, statut="reussi").exists())
        self.assertEqual(next(d["nom"] for d in contenu_adoption(adoption)["domaines"] if d["id"] == domaine.pk),
                         "Projets collectifs")
        self.assertEqual(Domaine.objects.get(pk=domaine.pk).nom, "Projets")
        selection, _ = selection_classe(self.classe, self.enseignant)
        self.assertEqual(RubriqueClasse.objects.filter(selection[RubriqueClasse]).count(), 2)
        self.assertTrue(SousDomaine.objects.filter(selection[SousDomaine], pk=sous.pk).exists())
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            finale = clore(utilisateur=self.enseignant, classe=self.classe)
        self.assertTrue(any(d["nom"] == "Projets collectifs" for d in finale.etat_final["contenu"]["domaines"]))
        self.assertEqual(self.client.post(url, {**base, "genre": "domaine", "nom": "Trop tard"}).status_code, 400)

    def test_recherche_dynamique_reutilise_les_resultats_et_le_contexte(self):
        adoption = self.adopter()
        domaine = adoption.contenu["domaines"][0]
        catalogue = reverse("catalogue_competences", args=[self.classe.pk])
        criteres = {"q": "parlé", "ajouter": 1, "classement": domaine["id"], "eleve": self.eleve.pk}
        page = self.client.get(catalogue, criteres)
        fragment = self.client.get(catalogue, {**criteres, "fragment": 1})
        self.assertEqual(fragment.headers["X-Petits-Pas-Catalogue"], "1")
        self.assertTemplateUsed(page, "suivi/partiels/catalogue_resultats.html")
        self.assertContains(fragment, "Je parle")
        self.assertNotContains(fragment, "<!doctype html>")
        self.assertEqual(fragment.context["domaine"], domaine["nom"])
        creation = self.client.get(fragment.context["url_creation_ciblee"])
        self.assertEqual(creation.context["form"].initial["eleves"], [self.eleve.pk])
        self.assertEqual(creation.context["form"].initial["libelle"], "parlé")
        self.assertEqual(creation.context["form"]["domaine"].value(), str(domaine["id"]))

    def test_cocher_tous_les_eleves_ninclut_pas_les_futurs_inscrits(self):
        from .referentiels import competence_saisissable
        competence = self.adopter().usages.get().competence
        catalogue = reverse("catalogue_competences", args=[self.classe.pk])
        url = f"{catalogue}?ajouter=1&collectif=1&selection={competence.pk}"
        form = self.client.get(url).context["form"]
        self.assertEqual(form["portee"].value(), "eleves")
        self.assertEqual(form["eleves"].value(), [self.eleve.pk])
        self.assertEqual(self.client.post(url, {"jeton": form["jeton"].value(),
            "portee": "eleves", "eleves": [self.eleve.pk]}).status_code, 302)
        nouveau = Eleve.objects.create(ecole=self.ecole, prenom="Camille")
        Scolarite.objects.create(eleve=nouveau, classe=self.classe, annee_scolaire=self.classe.annee_scolaire, niveau="PS")
        self.assertFalse(competence_saisissable(self.classe, competence, eleve=nouveau))
        form = self.client.get(url).context["form"]
        self.assertEqual(self.client.post(url, {"jeton": form["jeton"].value(),
            "portee": "classe"}).status_code, 302)
        self.assertTrue(competence_saisissable(self.classe, competence, eleve=nouveau))
        self.assertFalse(Observation.objects.exists())

    def test_ajouter_depuis_un_autre_referentiel_autorise(self):
        adoption = self.adopter()
        catalogue = reverse("catalogue_competences", args=[self.classe.pk])
        url = f"{catalogue}?source=version-{self.b.pk}"
        reference = self.b.definitions.get().identite.identifiant
        self.assertContains(self.client.get(url), "Ajouter au suivi")
        self.assertRedirects(self.client.post(url, {"action": "ajouter_depuis_source",
            "adoption": adoption.pk, "reference": reference}), url)
        regle = AdaptationCompetence.objects.get(classe=self.classe)
        self.assertTrue(regle.ajout)
        self.assertEqual(regle.competence.origine_source.identite.source_id, self.b.source_id)
        self.assertEqual(usage_pour_saisie(self.classe, regle.competence).adoption_id, adoption.pk)
        self.assertFalse(Observation.objects.exists())
        self.assertEqual(self.client.get(f"{catalogue}?source=version-99999").status_code, 403)

    def test_reprendre_une_competence_dune_classe_accessible(self):
        adoption = self.adopter()
        destination = self.classe
        autre = Classe.objects.create(ecole=self.ecole, nom="Autre classe", annee_scolaire=destination.annee_scolaire)
        affectation = self.affecter_enseignant(autre)
        autre.activer()
        self.classe = autre
        origine = self.adopter(self.b)
        self.classe = destination
        competence = origine.usages.get().competence
        url = reverse("catalogue_competences", args=[destination.pk]) + f"?source=classe-{autre.pk}"
        self.assertContains(self.client.get(url), competence.libelle)
        self.assertRedirects(self.client.post(url, {"action": "ajouter_depuis_source",
            "adoption": adoption.pk, "reference": str(competence.pk)}), url)
        self.assertEqual(AdaptationCompetence.objects.get(classe=destination).competence_id, competence.pk)
        self.assertFalse(Observation.objects.exists())
        affectation.delete()
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {"action": "ajouter_depuis_source",
            "adoption": adoption.pk, "reference": str(competence.pk)}).status_code, 403)

    def test_choisir_les_eleves_du_catalogue_sans_perdre_les_observations(self):
        from .exports_classe import selection_classe
        from .models import EleveCompetenceSelectionnee, bornes_annee_scolaire
        from .referentiels import competence_saisissable
        from .services.pedagogie import enregistrer_trace
        adoption = self.adopter()
        competence = adoption.usages.get().competence
        autre = Eleve.objects.create(ecole=self.ecole, prenom="Camille")
        scolarite = Scolarite.objects.create(eleve=autre, classe=self.classe, annee_scolaire=self.classe.annee_scolaire, niveau="PS")
        modifier_etat(utilisateur=self.enseignant, eleve=autre, competence=competence, statut=Observation.REUSSI)
        trace = enregistrer_trace(utilisateur=self.enseignant, eleve=autre, competence=competence,
            scolarite=scolarite, valeurs={"commentaire": "Une trace conservée",
                                         "date_observation": bornes_annee_scolaire(self.classe.annee_scolaire)[0]})
        url = reverse("catalogue_competences", args=[self.classe.pk]) + f"?selection={competence.pk}"

        def regler(portee, eleves):
            formulaire = self.client.get(url).context["form"]
            return self.client.post(url, {"jeton": formulaire["jeton"].value(), "portee": portee, "eleves": eleves})

        self.assertEqual(regler("eleves", [self.eleve.pk]).status_code, 302)
        self.assertTrue(competence_saisissable(self.classe, competence, eleve=self.eleve))
        self.assertFalse(competence_saisissable(self.classe, competence, eleve=autre))
        with self.assertRaises(PermissionDenied):
            usage_pour_saisie(self.classe, competence, eleve=autre)
        ligne = next(c for d in arbre_competences(self.ecole, classe=self.classe, eleve=autre)
                     for c in d.visibles if c.pk == competence.pk)
        self.assertFalse(ligne.saisie_ouverte)
        self.assertEqual(Observation.objects.get(eleve=autre, competence=competence).statut, Observation.REUSSI)
        trace.refresh_from_db()
        self.assertIsNone(trace.supprime_le)
        self.assertEqual(trace.commentaire, "Une trace conservée")
        projection, *_ = selection_classe(self.classe, self.enseignant)
        self.assertEqual(EleveCompetenceSelectionnee.objects.filter(
            projection[EleveCompetenceSelectionnee]).get().scolarite_id, self.scolarite.pk)
        self.assertEqual(regler("classe", []).status_code, 302)
        self.assertTrue(competence_saisissable(self.classe, competence, eleve=autre))

    def test_ajouter_depuis_un_autre_referentiel_pour_un_eleve(self):
        self.adopter()
        reference = self.b.definitions.get().identite.identifiant
        url = reverse("catalogue_competences", args=[self.classe.pk]) + f"?source=version-{self.b.pk}&selection={reference}"
        form = self.client.get(url).context["form"]
        self.assertEqual(form["portee"].value(), "classe")
        self.assertFalse(AdaptationCompetence.objects.filter(classe=self.classe).exists())
        reponse = self.client.post(url, {"portee": "eleves", "eleves": [self.eleve.pk],
                                        "jeton": form["jeton"].value()})
        regle = AdaptationCompetence.objects.get(classe=self.classe)
        self.assertRedirects(reponse, reverse("saisie_competence", args=[self.classe.pk, regle.competence_id]))
        self.assertEqual(regle.eleves_selectionnes.get().scolarite_id, self.scolarite.pk)
        self.assertTrue(regle.selection_eleves)
        self.assertFalse(Observation.objects.exists())

    def test_catalogue_actif_a_la_carte_sans_creer_observation(self):
        self.client.force_login(self.direction)
        creation = reverse("creer_classe")
        page = self.client.get(creation, {"annee_scolaire": self.classe.annee_scolaire})
        self.assertContains(page, "Partir d’un suivi vide")
        reponse = self.client.post(creation, {"nom": "Classe fictive à la carte",
            "annee_scolaire": self.classe.annee_scolaire, "base": "ecole", "selection_manuelle": "on",
            "jeton_choix": page.context["formulaire"]["jeton_choix"].value()})
        self.assertEqual(reponse.status_code, 302)
        self.classe = Classe.objects.get(nom="Classe fictive à la carte")
        self.affecter_enseignant(self.classe)
        self.classe.activer()
        self.client.force_login(self.enseignant)
        adoption = AdoptionReferentiel.objects.get(classe=self.classe, courante=True)
        self.assertTrue(adoption.selection_manuelle)
        competence = adoption.usages.get().competence
        AdaptationCompetence.objects.create(ecole=self.ecole, annee_scolaire=self.classe.annee_scolaire,
                                           competence=competence, visible=True)
        catalogue = reverse("catalogue_competences", args=[self.classe.pk])
        page = self.client.get(catalogue, {"q": "Je parle"})
        self.assertContains(page, "Ajouter au suivi")
        self.assertFalse(any(d.visibles for d in arbre_competences(self.ecole, classe=self.classe)))
        with self.assertRaises(PermissionDenied):
            usage_pour_saisie(self.classe, competence)

        donnees = {"action": "ajouter_au_suivi", "adoption": adoption.pk, "revision": 0}
        self.client.post(catalogue, {**donnees, "competence": self.competence.pk})
        self.assertFalse(any(d.visibles for d in arbre_competences(self.ecole, classe=self.classe)))
        self.assertRedirects(self.client.post(catalogue + "?q=parle", {**donnees, "competence": competence.pk}),
                             catalogue + "?q=parle")
        self.assertEqual([c.pk for d in arbre_competences(self.ecole, classe=self.classe) for c in d.visibles],
                         [competence.pk])
        self.assertFalse(Observation.objects.exists())

        autre = self.adopter(self.b)
        self.assertTrue(autre.selection_manuelle)
        self.assertFalse(any(d.visibles for d in arbre_competences(self.ecole, classe=self.classe)))
        self.client.post(catalogue, {**donnees, "competence": competence.pk})
        self.assertFalse(any(d.visibles for d in arbre_competences(self.ecole, classe=self.classe)))

    def test_apercu_sans_ecriture_puis_identites_et_contexte(self):
        nombre = Competence.objects.count()
        apercu = apercu_adoption(utilisateur=self.enseignant, classe=self.classe, version_id=self.a.pk)
        self.assertEqual(apercu["communes"], 0)
        self.assertEqual(Competence.objects.count(), nombre)
        self.assertFalse(VersionSourceEcole.objects.exists())
        adoption = self.adopter()
        competence = Competence.objects.get(pk=adoption.contenu["competences"][0]["id"])
        self.assertTrue(adoption.usages.get().cle_definition.startswith("source-"))
        self.assertEqual(arbre_competences(self.ecole, classe=self.classe)[0].visibles[0].libelle, "Je parle")
        self.assertEqual(illustration_effective(self.ecole, competence, self.classe).icone, "parler")
        self.assertEqual(propositions(competence, self.classe)[0]["texte"], "<prénom> prend la parole.")
        modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=competence, statut="reussi")
        self.assertEqual(EtatAnnuelObservation.objects.get().usage.adoption_id, adoption.pk)
        with self.assertRaises(PermissionDenied): usage_pour_saisie(self.classe, self.competence)

    def test_deux_bases_sans_assimilation_et_retour_sans_doublon(self):
        a = self.adopter()
        b = self.adopter(self.b)
        retour = self.adopter()
        self.assertNotEqual(a.usages.get().competence_id, b.usages.get().competence_id)
        self.assertEqual(a.usages.get().competence_id, retour.usages.get().competence_id)
        self.assertEqual(AdoptionReferentiel.objects.filter(classe=self.classe, courante=True).count(), 1)
        self.assertEqual(Observation.objects.count(), 0)

    def test_changement_renseigne_conserve_trace_et_refuse_ancienne_saisie(self):
        self.creer_trace(commentaire="Trace conservée")
        avant = list(Trace.objects.values())
        observations = list(Observation.objects.values())
        annuels = list(EtatAnnuelObservation.objects.values())
        self.adopter()
        self.assertEqual(list(Trace.objects.values()), avant)
        self.assertEqual(list(Observation.objects.values()), observations)
        self.assertEqual(list(EtatAnnuelObservation.objects.values()), annuels)
        with self.assertRaises(PermissionDenied): usage_pour_saisie(self.classe, self.competence)
        page = self.client.get(reverse("carnet", args=[self.eleve.pk]), {"contenu": "tout"})
        self.assertContains(page, "Trace conservée")
        self.assertContains(page, self.competence.libelle)

    def test_changement_cloture_et_retour_conservent_acquis_et_presentation(self):
        premiere = self.adopter()
        competence = premiere.usages.get().competence
        modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=competence, statut="reussi")
        etat = EtatAnnuelObservation.objects.get()
        self.adopter(self.b)
        self.assertEqual(illustration_effective(self.ecole, competence, self.classe).icone, "parler")
        self.assertEqual(propositions(competence, self.classe)[0]["texte"], "<prénom> prend la parole.")
        self.assertFalse(Observation.objects.filter(competence=self.classe._adoption_referentiel_lecture.usages.get().competence).exists())
        retour = self.adopter()
        self.assertEqual(retour.usages.get().competence_id, competence.pk)
        etat.refresh_from_db()
        self.assertEqual(etat.usage.adoption_id, premiere.pk)
        self.adopter(self.b)
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            finale = clore(utilisateur=self.enseignant, classe=self.classe)
            ancien = next(c for c in finale.etat_final["contenu"]["competences"] if c["id"] == competence.pk)
            self.assertFalse(ancien["active"])
            self.assertEqual(finale.etat_final["etats"][0]["statut"], "reussi")
            self.assertTrue(illustration_effective(self.ecole, competence, self.classe).photo.endswith(".svg"))
            self.assertEqual(propositions(competence, self.classe)[0]["texte"], "<prénom> prend la parole.")
            self.assertIn(competence.pk, [c.pk for d in arbre_competences(self.ecole, classe=self.classe, inclure_ids=[competence.pk]) for c in d.visibles])
            EtatAnnuelObservation.objects.filter(pk=etat.pk).update(statut="en_cours")
            etats, _ = observations_annee(self.eleve, self.eleve.scolarites.get(classe=self.classe))
            self.assertEqual(etats[competence.pk].statut, "reussi")
            page = self.client.get(reverse("carnet", args=[self.eleve.pk]), {"contenu": "tout"})
            self.assertContains(page, "Je parle")
            pdf = self.client.get(reverse("carnet_pdf", args=[self.eleve.pk]), {"contenu": "tout"})
            self.assertEqual(pdf.status_code, 200)
            self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_changement_conserve_trace_commune_et_attributions(self):
        from .services.traces_communes import enregistrer_commune
        premiere = self.adopter()
        competence = premiere.usages.get().competence
        enregistrer_commune(utilisateur=self.enseignant, classe=self.classe,
            competence=competence, ids=[self.eleve.pk], valeurs={"commentaire": "Activité fictive partagée"})
        communes = list(TraceCommune.objects.values())
        personnelles = list(Trace.objects.values())
        self.adopter(self.b)
        self.assertEqual(list(TraceCommune.objects.values()), communes)
        self.assertEqual(list(Trace.objects.values()), personnelles)
        self.assertEqual(TraceCommune.objects.get().usage_referentiel.adoption_id, premiere.pk)
        page = self.client.get(reverse("carnet", args=[self.eleve.pk]), {"contenu": "tout"})
        self.assertContains(page, "Activité fictive partagée")

    def test_permission_revision_et_adoption_perimees(self):
        apercu = apercu_adoption(utilisateur=self.enseignant, classe=self.classe, version_id=self.a.pk)
        self.adopter(self.b)
        with self.assertRaises(ValidationError):
            adopter_base(utilisateur=self.enseignant, classe=self.classe, version_id=self.a.pk,
                revisions_attendues=apercu["revisions"], adoption_attendue=apercu["adoption_id"],
            garde_attendue=apercu["garde"]["empreinte"])
        with self.assertRaises(PermissionDenied):
            apercu_adoption(utilisateur=get_user_model().objects.create_user(username="sans-affectation-fictif"), classe=self.classe, version_id=self.a.pk)

    def test_nouvelle_classe_n_affiche_pas_tout_catalogue(self):
        self.adopter()
        nouvelle = Classe.objects.create(ecole=self.ecole, nom="Papillons", annee_scolaire=self.classe.annee_scolaire)
        self.assertEqual(arbre_competences(self.ecole, classe=nouvelle), [])
        with self.assertRaises(PermissionDenied): usage_pour_saisie(nouvelle, self.competence)
        self.assertFalse(AdoptionReferentiel.objects.filter(classe=nouvelle).exists())

    def test_interface_jeton_et_confirmation(self):
        url = reverse("referentiel_classe", args=[self.classe.pk])
        page = self.client.get(url)
        self.assertContains(page, "Choisir le référentiel de la classe")
        self.assertFalse(VersionSourceEcole.objects.exists())
        page = self.client.post(url, {"action": "apercu", "version": self.a.pk})
        jeton = page.context["jeton"]
        self.assertTrue(jeton)
        self.assertEqual(self.client.post(url, {"action": "confirmer", "mot_de_passe": "ens-mdp", "jeton": "invalide"}).status_code, 400)
        self.assertRedirects(self.client.post(url, {"action": "confirmer", "mot_de_passe": "ens-mdp", "jeton": jeton}),
                             reverse("classe_detail", args=[self.classe.pk]))
        self.assertEqual(AdoptionReferentiel.objects.get(classe=self.classe, courante=True).version_id, self.a.pk)
        self.assertEqual(self.client.post(url, {"action": "confirmer", "mot_de_passe": "ens-mdp", "jeton": jeton}).status_code, 400)

    def test_version_non_autorisee_refusee(self):
        hors = importer(document("hors-liste"))[0]
        with self.assertRaises(ValidationError): self.adopter(hors)
        self.assertEqual(self.client.post(reverse("referentiel_classe", args=[self.classe.pk]),
            {"action": "apercu", "version": hors.pk}).status_code, 400)

    def test_cloture_definitions_et_ressources_source(self):
        adoption = self.adopter()
        competence = adoption.usages.get().competence
        modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=competence, statut="en_cours")
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            finale = clore(utilisateur=self.enseignant, classe=self.classe)
            self.assertEqual(finale.etat_final["contenu"]["competences"][0]["libelle"], "Je parle")
            self.assertEqual(propositions(competence, self.classe)[0]["texte"], "<prénom> prend la parole.")
            with self.assertRaises(ValidationError): self.adopter(self.b)

    def test_acquisition_hors_base_reste_dans_parcours_complet(self):
        self.adopter()
        # Un élève arrivé plus tard peut avoir un apprentissage d'une autre base.
        self.creer_trace(commentaire="Acquisition fictive conservée")
        page = self.client.get(reverse("carnet", args=[self.eleve.pk]), {"contenu": "tout"})
        self.assertContains(page, "Acquisition fictive conservée")
        self.assertContains(page, self.competence.libelle)

    def test_deux_versions_gardent_leurs_images_et_phrases(self):
        premiere = self.adopter()
        doc = document(version="2")
        doc["domaines"][0]["competences"][0].update(icone="livre", formulations=[{"code": "p1", "texte": "Autre proposition fidèle."}])
        deux = importer(doc)[0]
        publier_choix_application(annee=self.classe.annee_scolaire, versions_ids=[self.a.pk, self.b.pk, deux.pk],
                                 proposee_id=self.a.pk, revision_attendue=1)
        autre = Classe.objects.create(ecole=self.ecole, nom="Hirondelles", annee_scolaire=self.classe.annee_scolaire)
        apercu = apercu_adoption(utilisateur=self.direction, classe=autre, version_id=deux.pk)
        adoption = adopter_base(utilisateur=self.direction, classe=autre, version_id=deux.pk,
                               revisions_attendues=apercu["revisions"], adoption_attendue=None,
                               garde_attendue=apercu["garde"]["empreinte"])
        competence = adoption.usages.get().competence
        self.assertEqual(competence.pk, premiere.usages.get().competence_id)
        self.assertEqual(illustration_effective(self.ecole, competence, self.classe).icone, "parler")
        self.assertEqual(illustration_effective(self.ecole, competence, autre).icone, "livre")
        self.assertEqual(propositions(competence, self.classe)[0]["texte"], "<prénom> prend la parole.")
        self.assertEqual(propositions(competence, autre)[0]["texte"], "Autre proposition fidèle.")

        # Une autre classe a adopté une définition plus récente ; elle ne doit
        # pas remplacer celle de notre parcours après un changement de base.
        self.adopter(self.b)
        self.assertEqual(illustration_effective(self.ecole, competence, self.classe).icone, "parler")
        self.assertEqual(propositions(competence, self.classe)[0]["texte"], "<prénom> prend la parole.")
        arbre = arbre_competences(self.ecole, classe=self.classe, inclure_ids=[competence.pk])
        ancienne = next(c for d in arbre for c in d.visibles if c.pk == competence.pk)
        self.assertEqual(ancienne.icone, "parler")
