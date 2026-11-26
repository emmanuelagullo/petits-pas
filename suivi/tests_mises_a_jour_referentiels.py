from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from .tests import Base
from . import tests_adoption_bases_referentiels as fixtures
from .tests_import_sources_referentiels import document, importer
from .models import AdoptionReferentiel, Competence, DestinationPublicationGrist, EtatAnnuelObservation, Observation, SourceReferentiel, Trace, VersionSourceEcole
from .services.adoption_bases_referentiels import apercu_adoption
from .services.choix_bases_referentiels import publier_choix_application
from .services.adaptations_referentiels import enregistrer_adaptation
from .services.contextes_referentiels import usage_pour_saisie
from .services.pedagogie import enregistrer_trace, modifier_etat
from .services.publications_grist import contenu_grist
from .services.paquets_referentiels import lire_paquet
from .referentiels import contenu_adoption


class MisesAJour(Base):
    def setUp(self):
        super().setUp()
        from .services.reprise_referentiels import reprendre
        reprendre(self.ecole.pk)
        doc = document()
        doc["domaines"][0]["competences"][0].update(icone="parler",
            formulations=[{"code": "p1", "texte": "<prénom> prend la parole."}])
        self.a = importer(doc)[0]
        self.b = importer(document("autre-fictive"))[0]
        publier_choix_application(annee=self.classe.annee_scolaire,
            versions_ids=[self.a.pk, self.b.pk], proposee_id=self.a.pk, revision_attendue=0)
        self.entrer()

    adopter = fixtures.AdoptionBases.adopter

    def preparer(self, retirer=False, phrases=False):
        ancienne = self.adopter()
        doc = document(version="2")
        c = doc["domaines"][0]["competences"][0]
        c.update(libelle="Je prends la parole", code="L02", icone="livre")
        if phrases:
            c["formulations"] = [{"code": "p1", "texte": "<prénom> partage une découverte."}]
        if retirer:
            c["identite"] = "autre-apprentissage"
        doc["domaines"][0]["competences"].insert(0, {"identite": "ecouter", "code": "L03",
            "libelle": "J’écoute mes camarades", "niveau": "PS"})
        nouvelle = importer(doc)[0]
        publier_choix_application(annee=self.classe.annee_scolaire,
            versions_ids=[self.a.pk, nouvelle.pk], proposee_id=nouvelle.pk, revision_attendue=1)
        return ancienne, nouvelle

    def adapter(self, ancienne, classe=True, texte="Mon texte fictif"):
        return enregistrer_adaptation(utilisateur=self.enseignant if classe else self.direction,
            ecole=self.ecole, annee=self.classe.annee_scolaire,
            competence=ancienne.usages.get().competence, classe=self.classe if classe else None,
            adoption_attendue=ancienne.pk if classe else None,
            revision_attendue=0, libelle=texte, visible=False if classe else None)

    def test_zip_au_catalogue_puis_revision_de_classe_conserve_le_suivi(self):
        echange = reverse("paquets_referentiels_ecole") + f"?annee={self.classe.annee_scolaire}"
        classe = reverse("referentiel_classe", args=[self.classe.pk])

        def recevoir(version, deja_recue=False):
            self.client.force_login(self.direction)
            fichier = self.client.post(echange + f"&edition={version.pk}", {"action": "edition"})
            self.assertEqual(fichier["Content-Type"], "application/zip")
            page = self.client.post(echange, {"action": "apercu", "destination": "ecole",
                "paquet": SimpleUploadedFile("referentiel.zip", fichier.content)})
            self.assertContains(page, "Confirmer l’import")
            if version.numero != self.a.numero:
                self.assertEqual(page.context["edition_comparee"], self.a.numero)
            resultat = self.client.post(echange, {"action": "importer", "jeton": page.context["jeton"]})
            self.assertContains(resultat, "figure déjà" if deja_recue else "Édition ajoutée au catalogue")
            return SourceReferentiel.objects.get(
                ecole=self.ecole, identifiant_diffusion=version.contenu["source"]["identifiant"]
            ).versions.get(numero=version.numero)

        locale = recevoir(self.a)
        self.client.force_login(self.enseignant)
        ancienne = self.adopter(locale)
        competence = ancienne.usages.get().competence
        modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=competence, statut="reussi")
        enregistrer_trace(utilisateur=self.enseignant, eleve=self.eleve, competence=competence,
            scolarite=self.eleve.scolarites.get(classe=self.classe), valeurs={"commentaire": "Trace fictive privée"})
        self.adapter(ancienne)
        etats = list(EtatAnnuelObservation.objects.values())
        observations = list(Observation.objects.values())

        traces = list(Trace.objects.values())
        sortie = self.client.post(reverse("paquets_referentiels_classe", args=[self.classe.pk]),
                                  {"action": "edition"})
        self.assertEqual(sortie["Content-Type"], "application/zip")
        self.assertNotIn("Trace fictive privée", lire_paquet(sortie.content))

        doc = document(version="2")
        doc["domaines"][0]["competences"][0].update(libelle="Je prends la parole", icone="livre")
        nouvelle = importer(doc)[0]
        publier_choix_application(annee=self.classe.annee_scolaire,
            versions_ids=[self.a.pk, nouvelle.pk], proposee_id=nouvelle.pk, revision_attendue=1)
        revision = recevoir(nouvelle)
        self.assertEqual(recevoir(nouvelle, deja_recue=True), revision)
        self.assertTrue(AdoptionReferentiel.objects.filter(pk=ancienne.pk, courante=True).exists())

        self.client.force_login(self.enseignant)
        page = self.client.post(classe, {"action": "apercu", "version": revision.pk})
        self.assertContains(page, "Je prends la parole")
        self.assertContains(page, "Mon texte fictif")
        confirmation = self.client.post(classe, {"action": "confirmer", "jeton": page.context["jeton"]})
        self.assertEqual(confirmation.status_code, 302)
        actuelle = AdoptionReferentiel.objects.get(classe=self.classe, courante=True)
        self.assertEqual(actuelle.version_id, revision.pk)
        self.assertEqual(actuelle.usages.get().competence_id, competence.pk)
        self.assertEqual(contenu_adoption(actuelle)["competences"][0]["libelle"], "Mon texte fictif")
        self.assertEqual(list(EtatAnnuelObservation.objects.values()), etats)
        self.assertEqual(list(Observation.objects.values()), observations)
        self.assertEqual(list(Trace.objects.values()), traces)

    def test_partager_la_base_courante_exporte_le_libelle_adapte(self):
        ancienne = self.adopter()
        self.adapter(ancienne, classe=False, texte="Libellé commun adapté")
        echange = reverse("paquets_referentiels_classe", args=[self.classe.pk])
        self.client.force_login(self.direction)
        page_ecole = self.client.get(reverse("paquets_referentiels_ecole"), {
            "annee": self.classe.annee_scolaire, "volet": "exporter",
        })
        self.assertContains(page_ecole, f'href="{echange}?volet=exporter&amp;depuis=export-ecole#export-referentiel"')
        page_classe = self.client.get(echange, {"volet": "exporter"})
        self.assertContains(page_classe, "Partager le référentiel courant de cette classe")
        self.assertContains(page_classe, "Publier dans Grist")
        self.assertNotContains(page_classe, 'id="edition"')
        self.assertContains(page_ecole, 'id="edition"')
        self.assertContains(page_classe, '<summary class="bouton bouton-depliant discret">Modifier les informations</summary>')
        self.assertContains(page_classe, "Référentiel de " + self.classe.nom)
        depuis_ecole = self.client.get(echange, {"volet": "exporter", "depuis": "export-ecole"})
        self.assertContains(depuis_ecole, "Choisir une autre classe")
        self.assertContains(depuis_ecole, "Exporter depuis l’école")
        direct = self.client.post(echange, {"action": "telecharger-classe"})
        self.assertEqual(direct["Content-Type"], "application/zip")
        self.client.force_login(self.enseignant)
        donnees = {"action": "apercu-classe", "titre": "Référentiel partagé", "identifiant": "collectif-test",
                   "version": "1", "provenance": "Équipe fictive", "licence": "CC0-1.0"}
        page = self.client.post(echange, donnees)
        self.assertContains(page, "Libellé commun adapté")
        sortie = self.client.post(echange, {"action": "exporter-classe", "jeton_partage": page.context["jeton_partage"]})
        self.assertEqual(sortie["Content-Type"], "application/zip")
        document = lire_paquet(sortie.content)
        self.assertIn("Libellé commun adapté", document)
        self.assertIn("source_origine", document)
        self.assertNotIn(self.eleve.prenom, document)
        self.adapter(ancienne, classe=True, texte="Libellé modifié après aperçu")
        refus = self.client.post(echange, {"action": "exporter-classe", "jeton_partage": page.context["jeton_partage"]})
        self.assertContains(refus, "Le référentiel a changé", status_code=400)

    def test_publication_grist_directe_memorise_la_destination_et_ne_duplique_pas(self):
        adoption = self.adopter()
        echange = reverse("paquets_referentiels_classe", args=[self.classe.pk])
        url = "https://grist.numerique.gouv.fr/o/docs/document-fictif"
        destination = {"url": url, "nom": "Ressources Cycle 1", "espace": "docs", "editions": [
            {"Numero": 7, "Referentiel": "autre", "Titre": "Autre", "Contenu": "{}"},
        ]}
        page = self.client.get(echange, {"volet": "exporter"})
        self.assertContains(page, 'value="publier-grist"')
        self.assertContains(page, 'id="url-grist"')
        self.assertContains(page, "Voir le contenu à partager")
        self.assertContains(page, "Télécharger le ZIP", count=1)
        self.assertContains(page, 'value="telecharger-classe" formnovalidate')
        self.assertNotContains(page, "Vous avez reçu un fichier ZIP")
        self.assertNotContains(self.client.get(echange), "Vous avez reçu un fichier ZIP")
        self.assertNotContains(page, "Examiner le contenu")
        donnees = {"action": "publier-grist", "url_grist": url}
        with patch("suivi.publication_grist.destination_grist", return_value=destination), patch(
                "suivi.publication_grist.publier_edition_grist") as publier:
            publier.side_effect = ValidationError("Grist refuse l’écriture.")
            refus = self.client.post(echange, donnees)
            self.assertContains(refus, "Grist refuse l’écriture.")
            self.assertContains(refus, f'value="{url}"')
            self.assertFalse(refus.context["destinations_grist"])
            publier.reset_mock()
            publier.side_effect = None
            publication = self.client.post(echange, donnees)
            self.assertContains(publication, "Édition 1 publiée")
            self.assertContains(publication, destination["nom"])
            _, reference, titre, numero, document = publier.call_args.args
            self.assertEqual(numero, 1)
            destination["editions"].append({"Numero": 1, "Referentiel": reference, "Titre": titre,
                                        "Contenu": contenu_grist(document)})
            autre = "https://grist.numerique.gouv.fr/o/docs/autre-catalogue"
            DestinationPublicationGrist.objects.create(
                ecole=self.ecole, auteur=self.enseignant, classe=self.classe, url=autre,
                nom="Dernier catalogue utilisé", identifiant_local="autre", reference="autre",
            )
            page = self.client.get(echange, {"volet": "exporter"})
            self.assertContains(page, f'value="{url}" selected')
            self.assertContains(page, "Dernier catalogue utilisé")
            self.assertNotContains(page, f'value="{autre}" selected')
            reprise = self.client.post(echange, {"action": "publier-grist", "destination_grist": url,
                                                "nom_catalogue_grist": "Ressources de l’équipe"})
            self.assertContains(reprise, "Édition 1 déjà publiée")
            self.assertContains(reprise, "Nouvelle édition")
            self.assertEqual(reprise.context["derniere_destination"].url, url)
            self.assertEqual(reprise.context["derniere_destination"].nom, destination["nom"])
            publier.assert_called_once()
            self.adapter(adoption, classe=True, texte="Nouvelle formulation")
            revision = self.client.post(echange, {"action": "publier-grist", "destination_grist": url})
            self.assertContains(revision, "Édition 2 publiée")
            self.assertContains(revision, destination["nom"])
            self.assertEqual(publier.call_args.args[3], 2)

    def test_apercu_sans_projection_et_adaptation_prioritaire(self):
        ancienne, nouvelle = self.preparer()
        self.adapter(ancienne, classe=False, texte="Proposition école fictive")
        self.adapter(ancienne)
        nombre = Competence.objects.count()
        apercu = apercu_adoption(utilisateur=self.enseignant, classe=self.classe, version_id=nouvelle.pk)
        self.assertEqual(Competence.objects.count(), nombre)
        self.assertFalse(VersionSourceEcole.objects.filter(version=nouvelle).exists())
        detail = apercu["mise_a_jour"]
        self.assertEqual(detail["modifiees"][0]["avant"], "Je parle")
        self.assertIn("Phrases proposées", detail["modifiees"][0]["changements"])
        self.assertNotIn("Ordre de présentation", detail["modifiees"][0]["changements"])
        self.assertEqual(detail["ajoutees"], ["J’écoute mes camarades"])
        self.assertEqual(detail["retirees"], [])
        self.assertEqual(detail["adaptations"][0]["libelle"], "Mon texte fictif")
        self.assertFalse(detail["adaptations"][0]["visible"])
        adoption = self.adopter(nouvelle)
        self.assertEqual(ancienne.usages.get().competence_id,
            next(c["id"] for c in adoption.contenu["competences"] if c["code"] == "L02"))
        effective = next(c for c in contenu_adoption(adoption)["competences"] if c["code"] == "L02")
        self.assertEqual(effective["libelle"], "Mon texte fictif")
        self.assertFalse(effective["active"])

    def test_retrait_et_nouveau_sens_conservent_ancien_etat(self):
        ancienne, nouvelle = self.preparer(retirer=True)
        competence = ancienne.usages.get().competence
        modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=competence, statut="reussi")
        etats = list(EtatAnnuelObservation.objects.values())
        observations = list(Observation.objects.values())
        apercu = apercu_adoption(utilisateur=self.enseignant, classe=self.classe, version_id=nouvelle.pk)
        self.assertEqual(apercu["mise_a_jour"]["retirees"], ["Je parle"])
        self.adopter(nouvelle)
        self.assertEqual(list(EtatAnnuelObservation.objects.values()), etats)
        self.assertEqual(list(Observation.objects.values()), observations)
        with self.assertRaises(PermissionDenied):
            usage_pour_saisie(self.classe, competence)
        page = self.client.get(reverse("carnet", args=[self.eleve.pk]), {"contenu": "tout"})
        self.assertContains(page, "Je parle")
        self.adopter(self.a)
        self.assertEqual(self.classe._adoption_referentiel_lecture.usages.get().competence_id, competence.pk)

    def test_reprendre_libelle_classe_conserve_masquage_et_choix_ecole(self):
        ancienne, nouvelle = self.preparer()
        self.adapter(ancienne, classe=False, texte="Libellé école")
        self.adapter(ancienne)
        competence_id = ancienne.usages.get().competence_id
        url = reverse("referentiel_classe", args=[self.classe.pk])
        page = self.client.post(url, {"action": "apercu", "version": nouvelle.pk})
        self.assertContains(page, "Reprendre « Libellé école »")
        donnees = {"action": "confirmer", "jeton": page.context["jeton"]}
        refus = self.client.post(url, {**donnees, "reprendre_libelle": ["inconnu"]})
        self.assertEqual(refus.status_code, 400)
        confirmation = self.client.post(url, {**donnees, "reprendre_libelle": [str(competence_id)]})
        self.assertEqual(confirmation.status_code, 302)
        adoption = AdoptionReferentiel.objects.get(classe=self.classe, courante=True)
        effective = next(c for c in contenu_adoption(adoption)["competences"] if c["id"] == competence_id)
        self.assertEqual(effective["libelle"], "Libellé école")
        self.assertFalse(effective["active"])

    def test_reprendre_phrase_proposee(self):
        from .services.presentation import enregistrer_formulation
        from .presentation import formulations_effectives

        ancienne, nouvelle = self.preparer(phrases=True)
        competence = ancienne.usages.get().competence
        phrase = competence.formulations.get(code="p1")
        enregistrer_formulation(utilisateur=self.enseignant, competence=competence,
                                classe=self.classe, cle=f"base-{phrase.pk}", texte="Choix de la classe")
        url = reverse("referentiel_classe", args=[self.classe.pk])
        apercu = self.client.post(url, {"action": "apercu", "version": nouvelle.pk})
        self.assertContains(apercu, 'name="reprendre_phrase"')
        confirmation = self.client.post(url, {"action": "confirmer", "jeton": apercu.context["jeton"],
                                              "reprendre_phrase": str(phrase.pk)})
        self.assertEqual(confirmation.status_code, 302)
        self.classe.refresh_from_db()
        self.classe.__dict__.pop("_adoption_referentiel_lecture", None)
        self.assertIn("<prénom> partage une découverte.", formulations_effectives(competence, self.classe))

    def test_reprendre_illustration_sans_effacer_le_libelle_adapte(self):
        from .models import ReglagePresentation
        from .presentation import illustration_effective

        ancienne, nouvelle = self.preparer()
        competence = ancienne.usages.get().competence
        self.adapter(ancienne)
        illustration = ReglagePresentation.objects.create(
            ecole=self.ecole, classe=self.classe, competence=competence,
            mode=ReglagePresentation.REMPLACER, icone="parler",
        )
        url = reverse("referentiel_classe", args=[self.classe.pk])
        apercu = self.client.post(url, {"action": "apercu", "version": nouvelle.pk})
        self.assertContains(apercu, 'name="reprendre_illustration"')
        reponse = self.client.post(url, {"action": "confirmer", "jeton": apercu.context["jeton"],
                                         "reprendre_illustration": str(illustration.pk)})
        self.assertEqual(reponse.status_code, 302)
        self.classe.refresh_from_db()
        self.classe.__dict__.pop("_adoption_referentiel_lecture", None)
        self.assertEqual(illustration_effective(self.ecole, competence, self.classe).icone, "livre")
        adoption = AdoptionReferentiel.objects.get(classe=self.classe, courante=True)
        definition = next(c for c in contenu_adoption(adoption)["competences"] if c["id"] == competence.pk)
        self.assertEqual(definition["libelle"], "Mon texte fictif")
        self.assertFalse(definition["active"])

    def test_une_rubrique_masquee_est_absente_de_la_vue_commune_et_du_partage(self):
        from .models import RubriqueClasse
        from .services.partage_referentiel_classe import contenu_commun_classe, preparer_referentiel_classe

        adoption = self.adopter()
        domaine = contenu_adoption(adoption)["domaines"][0]
        RubriqueClasse.objects.create(classe=self.classe, domaine_id=domaine["id"],
                                      nom=domaine["nom"], ordre=domaine["ordre"], masquee=True)
        self.assertEqual(contenu_commun_classe(adoption)["competences"], [])
        paquet = preparer_referentiel_classe(self.classe, {"identifiant": "classe-fictive"}, "1")
        self.assertEqual(paquet["domaines"], [])

    def test_suivi_de_source_signale_une_edition_sans_l_adopter(self):
        from .models import SuiviSourceClasse

        ancienne = self.adopter()
        url = reverse("suivis_referentiels_classe", args=[self.classe.pk])
        page = self.client.get(url)
        self.assertNotContains(page, "Changements et décisions")
        self.assertContains(page, 'id="decouvrir-referentiels"')
        reference = f"source-{self.a.source_id}"
        self.assertRedirects(self.client.post(url, {"action": "suivre", "source": reference}), url + "#referentiels-suivis")
        doc = document(version="2")
        doc["domaines"][0]["competences"][0]["libelle"] = "Je prends la parole"
        version = importer(doc)[0]
        publier_choix_application(annee=self.classe.annee_scolaire,
            versions_ids=[self.a.pk, version.pk], proposee_id=version.pk, revision_attendue=1)
        page = self.client.get(url)
        self.assertContains(page, 'id="decouvrir-referentiels"')
        self.assertNotContains(page, "Ne plus suivre les nouveautés")
        self.assertContains(page, "0 ajout · 1 modification · 0 retrait")
        self.assertContains(page, "Nouvelle édition disponible")
        self.assertTrue(AdoptionReferentiel.objects.get(pk=ancienne.pk).courante)
        ligne = next(l for l in page.context["lignes"] if l["reference"] == reference)
        self.assertRedirects(self.client.post(url, {"action": "marquer-vu", "source": reference,
                                                  "empreinte": ligne["empreinte"]}), url + "#referentiels-suivis")
        self.assertContains(self.client.get(url), "Aucun changement depuis votre dernière consultation")
        self.assertTrue(SuiviSourceClasse.objects.filter(classe=self.classe, reference=reference).exists())

    def test_ecarter_une_source_du_selecteur_conserve_la_consultation(self):
        self.adopter()
        url = reverse("suivis_referentiels_classe", args=[self.classe.pk])
        catalogue = reverse("catalogue_competences", args=[self.classe.pk])
        source = f"version-{self.b.pk}"
        self.assertContains(self.client.get(catalogue), f'value="{source}"')
        self.assertEqual(self.client.post(url, {"action": "ecarter-ajout", "source": f"source-{self.b.source_id}"}).status_code, 302)
        self.assertNotContains(self.client.get(catalogue), f'value="{source}"')
        self.assertContains(self.client.get(url), "Proposer les compétences de ce référentiel à l’ajout")
        self.assertEqual(self.client.get(catalogue, {"source": source}).status_code, 200)

    def test_mise_a_jour_depuis_le_resume_sans_ouvrir_la_comparaison(self):
        ancienne, nouvelle = self.preparer()
        url = reverse("referentiel_classe", args=[self.classe.pk])
        page = self.client.get(url)
        self.assertContains(page, "1 ajout · 1 modification · 0 retrait")
        self.assertContains(page, "Voir les changements")
        self.assertContains(page, "Mettre à jour le référentiel de la classe")
        self.assertNotContains(page, 'name="mot_de_passe"')
        self.assertTrue(AdoptionReferentiel.objects.get(pk=ancienne.pk).courante)
        self.assertFalse(VersionSourceEcole.objects.filter(version=nouvelle).exists())
        reponse = self.client.post(url, {"action": "confirmer", "jeton": page.context["jeton"]})
        self.assertEqual(reponse.status_code, 302)
        self.assertTrue(AdoptionReferentiel.objects.filter(classe=self.classe, version=nouvelle, courante=True).exists())

    def test_confirmation_refuse_adaptation_changee(self):
        ancienne, nouvelle = self.preparer()
        url = reverse("referentiel_classe", args=[self.classe.pk])
        page = self.client.post(url, {"action": "apercu", "version": nouvelle.pk})
        self.assertContains(page, "Mettre à jour le référentiel de la classe")
        self.assertContains(page, 'data-apercu-ecarts')
        self.assertContains(page, "Édition utilisée")
        self.assertContains(page, "Édition proposée")
        self.assertContains(page, 'class="icone-liste"', count=2)
        jeton = page.context["jeton"]
        self.adapter(ancienne)
        page = self.client.post(url, {"action": "confirmer", "mot_de_passe": "ens-mdp", "jeton": jeton})
        self.assertEqual(page.status_code, 400)
        self.assertContains(page, "Les adaptations ont changé", status_code=400)
        self.assertFalse(VersionSourceEcole.objects.filter(version=nouvelle).exists())
        page = self.client.post(url, {"action": "apercu", "version": nouvelle.pk})
        self.assertEqual(self.client.post(url, {"action": "confirmer", "mot_de_passe": "ens-mdp", "jeton": page.context["jeton"]}).status_code, 302)

    def test_autre_source_et_meme_version_ne_sont_pas_mises_a_jour(self):
        self.adopter()
        for version in (self.a, self.b):
            self.assertIsNone(apercu_adoption(utilisateur=self.enseignant,
                classe=self.classe, version_id=version.pk)["mise_a_jour"])

    def test_propositions_suivent_version_et_choix_personnels_restent(self):
        from .models import ReglagePresentation
        from .presentation import illustration_effective, propositions
        from .services.presentation import enregistrer_formulation, enregistrer_reglage
        ancienne, nouvelle = self.preparer(phrases=True)
        competence = ancienne.usages.get().competence
        cle = propositions(competence, self.classe)[0]["cle"]
        enregistrer_formulation(utilisateur=self.enseignant, competence=competence,
            classe=self.classe, cle=cle, texte="Ma phrase fictive conservée")
        enregistrer_reglage(self.enseignant, ReglagePresentation(ecole=self.ecole,
            classe=self.classe, competence=competence, mode="remplacer", icone="parler"))
        self.adopter(nouvelle)
        self.assertEqual(illustration_effective(self.ecole, competence, self.classe).icone, "parler")
        self.assertEqual(propositions(competence, self.classe)[0]["texte"], "Ma phrase fictive conservée")
        self.assertEqual(ancienne.contenu["formulations"][0]["texte"], "<prénom> prend la parole.")

    def test_phrase_retiree_conserve_adaptation_pour_retour(self):
        from .models import FormulationLocale
        from .presentation import propositions
        from .services.presentation import enregistrer_formulation
        ancienne, nouvelle = self.preparer()
        competence = ancienne.usages.get().competence
        enregistrer_formulation(utilisateur=self.enseignant, competence=competence,
            classe=self.classe, cle=propositions(competence, self.classe)[0]["cle"],
            texte="Ma phrase adaptée fictive")
        self.adopter(nouvelle)
        self.assertEqual(propositions(competence, self.classe), [])
        self.assertEqual(FormulationLocale.objects.get().texte, "Ma phrase adaptée fictive")
        self.adopter(self.a)
        self.assertEqual(propositions(competence, self.classe)[0]["texte"], "Ma phrase adaptée fictive")
