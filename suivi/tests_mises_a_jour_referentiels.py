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
        self.assertContains(page_classe, '<summary class="bouton bouton-depliant discret">Informations de partage</summary>')
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

    def test_selection_des_competences_de_la_classe_et_d_un_autre_referentiel(self):
        adoption = self.adopter()
        competence = adoption.usages.get().competence
        catalogue = reverse("catalogue_competences", args=[self.classe.pk])
        export = reverse("paquets_referentiels_classe", args=[self.classe.pk])
        page = self.client.get(catalogue, {"q": "inexistant"})
        self.assertContains(page, "Exporter le référentiel de la classe")
        page = self.client.get(catalogue, {"source": f"version-{self.b.pk}"})
        self.assertNotContains(page, "Ajouter aux catalogues de la classe")
        self.assertContains(page, f'value="version-{self.b.pk}:')
        from .identites_referentiels import competences_document, reference_competence
        externe = reference_competence(next(competences_document(self.b.contenu)))
        retour = catalogue + "?q=parle#partager-competences"
        references = [f"classe:{competence.pk}", f"version-{self.b.pk}:{externe}"]
        donnees = {"action": "preparer-selection-classe", "competence_partagee": references}
        page = self.client.post(export, donnees, query_params={"retour": retour})
        self.assertContains(page, "Sélection de compétences – 2 sources")
        self.assertEqual(page.context["retour_competences"], retour)
        self.assertContains(page, "Télécharger le ZIP de la sélection")
        paquet = self.client.post(export, {
            **donnees, "action": "telecharger-selection-classe",
            "empreinte": page.context["empreinte_selection"], "titre_selection": "Ma sélection",
        })
        from .services.import_sources_referentiels import lire_source
        contenu, _ = lire_source(lire_paquet(paquet.content))
        self.assertEqual(contenu["source"]["titre"], "Ma sélection")
        self.assertTrue(contenu["source"]["identifiant"].startswith("selection-"))
        self.assertEqual(len(list(competences_document(contenu))), 2)
        refus = self.client.post(export, {**donnees, "competence_partagee": [*references, "classe:999999"]})
        self.assertContains(refus, "ne sont plus partageables", status_code=400)

    def test_selection_mixte_conserve_les_licences_apres_import_et_reexport(self):
        from .identites_referentiels import competences_document, reference_competence
        from .services.import_sources_referentiels import lire_source
        from .services.licences_diffusion import droits_competence
        from .services.paquets_referentiels import exporter_selection
        from .services.publications_grist import contenu_grist
        import json

        adhesion = self.adopter()
        doc = document("licences-mixtes-fictives")
        doc["source"]["licence"] = "CC-BY-4.0"
        autre = importer(doc)[0]
        publier_choix_application(annee=self.classe.annee_scolaire,
            versions_ids=[self.a.pk, autre.pk], proposee_id=self.a.pk, revision_attendue=1)
        choix = reference_competence(next(competences_document(autre.contenu)))
        references = [f"classe:{adhesion.usages.get().competence_id}", f"version-{autre.pk}:{choix}"]
        url = reverse("paquets_referentiels_classe", args=[self.classe.pk])
        donnees = {"competence_partagee": references}
        page = self.client.post(url, {**donnees, "action": "preparer-selection-classe"})
        self.assertContains(page, "2 licences conservées")
        paquet = self.client.post(url, {**donnees, "action": "telecharger-selection-classe",
                                        "empreinte": page.context["empreinte_selection"]})
        self.assertEqual(paquet.status_code, 200)
        texte = lire_paquet(paquet.content)
        portable, _ = lire_source(texte)
        document_grist = json.loads(contenu_grist(portable))
        self.assertEqual(document_grist["droits"], portable["droits"])
        self.assertEqual({droits_competence(portable, c)[0] for c in competences_document(portable)},
                         {"CC-BY-4.0", "CC-BY-SA-4.0"})
        from .services.import_sources_referentiels import importer_source
        importe, _, _ = importer_source(texte, ecole=self.ecole)
        ref = next(reference_competence(c) for c in competences_document(importe.contenu)
                   if droits_competence(importe.contenu, c)[0] == "CC-BY-4.0")
        repris, _ = lire_source(lire_paquet(exporter_selection(importe, [ref])))
        [competence] = list(competences_document(repris))
        self.assertEqual(droits_competence(repris, competence)[0], "CC-BY-4.0")

    def test_notice_majoritaire_sans_reference_par_competence(self):
        from .services.licences_diffusion import droits_competence, encoder_droits

        commun = ("CC-BY-SA-4.0", "Crédits du référentiel")
        exception = ("CC-BY-4.0", "Crédits de l’autre référentiel")
        competences = [{"code": "C1", "source_origine": "origine"},
                       {"code": "C2", "source_origine": "origine"},
                       {"code": "C3", "source_origine": "autre"}]
        document = {"source": {"licence": commun[0], "provenance": commun[1]},
                    "domaines": [{"competences": competences}]}
        encoder_droits(document, {"C1": commun, "C2": commun, "C3": exception})
        self.assertEqual(document["droits"], {"autre": exception})
        self.assertTrue(all("droits" not in c for c in competences))
        self.assertEqual([droits_competence(document, c) for c in competences], [commun, commun, exception])

    def test_selection_avec_licence_manquante_ou_personnalisee_exporte_tout(self):
        from .identites_referentiels import competences_document, reference_competence

        adhesion = self.adopter()
        doc = document("licence-inconnue-fictive")
        del doc["source"]["licence"]
        autre = importer(doc)[0]
        conditions = "Chat d’école : usage classe/formation, origine à mentionner. https://www.chatdecole.site/a-propos/"
        doc = document("licence-chat-fictive")
        doc["source"]["licence"] = conditions
        chat = importer(doc)[0]
        publier_choix_application(annee=self.classe.annee_scolaire,
            versions_ids=[self.a.pk, autre.pk, chat.pk], proposee_id=self.a.pk, revision_attendue=1)
        references = [f"classe:{adhesion.usages.get().competence_id}"]
        for version in (autre, chat):
            ref = reference_competence(next(competences_document(version.contenu)))
            references.append(f"version-{version.pk}:{ref}")
        url = reverse("paquets_referentiels_classe", args=[self.classe.pk])
        donnees = {"competence_partagee": references, "action": "preparer-selection-classe"}
        page = self.client.post(url, donnees)
        self.assertContains(page, "Télécharger le ZIP de la sélection")
        self.assertContains(page, "Licence d’origine non renseignée · 1")
        self.assertEqual(page.context["nombre_exportable"], 3)
        export = {**donnees, "action": "telecharger-selection-classe", "empreinte": page.context["empreinte_selection"]}
        from .services.licences_diffusion import droits_competence, LICENCE_ORIGINE_NON_RENSEIGNEE
        from .services.import_sources_referentiels import lire_source

        for choix, attendue in (("", LICENCE_ORIGINE_NON_RENSEIGNEE), ("CC-BY-4.0", "CC-BY-4.0")):
            zip_exporte = self.client.post(url, {**export, "licence_confirmee": choix})
            self.assertEqual(zip_exporte["Content-Type"], "application/zip")
            contenu, _ = lire_source(lire_paquet(zip_exporte.content))
            self.assertEqual({droits_competence(contenu, c)[0] for c in competences_document(contenu)},
                             {conditions, "CC-BY-SA-4.0", attendue})

    def test_selection_demande_une_definition_si_deux_editions_divergent(self):
        self.adopter()
        from .identites_referentiels import competences_document, reference_competence

        autre = document("autre-fictive", version="2")
        autre["domaines"][0]["competences"][0]["libelle"] = "Je reformule"
        nouvelle = importer(autre)[0]
        publier_choix_application(annee=self.classe.annee_scolaire,
            versions_ids=[self.a.pk, self.b.pk, nouvelle.pk], proposee_id=self.a.pk, revision_attendue=1)
        cle = reference_competence(next(competences_document(self.b.contenu)))
        premiere = f"version-{self.b.pk}:{cle}"
        seconde = f"version-{nouvelle.pk}:{cle}"
        export = reverse("paquets_referentiels_classe", args=[self.classe.pk])
        donnees = {"action": "preparer-selection-classe", "competence_partagee": [premiere, seconde]}
        page = self.client.post(export, donnees)
        self.assertContains(page, "Confirmer les définitions")
        self.assertNotContains(page, "Télécharger le ZIP de la sélection")
        resolu = self.client.post(export, {**donnees, "definition_1": seconde})
        self.assertContains(resolu, "Télécharger le ZIP de la sélection")
        [competence] = resolu.context["apercu_selection"]["competences_importees"]
        self.assertEqual(competence["libelle"], "Je reformule")
        self.assertEqual(resolu.context["definitions_selection"], [seconde])

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
        self.assertContains(page, "data-export-zip")
        self.assertContains(page, "Options d’export", count=1)
        self.assertNotContains(page, "Télécharger un ZIP d’icônes seules")
        ariane = page.content.decode().split('aria-label="Fil d’Ariane"', 1)[1].split("</nav>", 1)[0]
        self.assertIn("Compétences", ariane)
        self.assertNotIn("Catalogues et partage", ariane)
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
            apercu = self.client.post(echange, {**donnees, "action": "voir-grist"})
            self.assertEqual(apercu.context["edition_prevue"], 1)
            publier.assert_not_called()
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
            catalogues = reverse("suivis_referentiels_classe", args=[self.classe.pk])
            page = self.client.get(catalogues)
            self.assertContains(page, 'id="destinations-publication"')
            self.assertContains(page, "Publier de nouveau", count=2)
            premiere = page.context["destinations_publication"][0]
            entree_export = self.client.get(premiere["republier"])
            self.assertContains(entree_export, 'data-preparer-destination="1"')
            from html import unescape
            import re

            lien_export = re.search(r'data-partager-classe href="([^"]+)"', entree_export.content.decode())[1]
            retour_export = self.client.get(unescape(lien_export))
            self.assertEqual(retour_export.context["choix_catalogue_grist"], autre)
            self.assertContains(retour_export, "Retour à Catalogues et partage", count=1)
            self.classe.refresh_from_db()
            self.assertFalse(self.classe.catalogues_propres)

            selection = {"reference": "selection-fictive", "titre": "Sélection · Langage", "editions": [1]}
            catalogue = {"nom": "Ressources Cycle 1", "url": url, "referentiels": [selection]}
            with patch("suivi.views_catalogues_referentiels.lire_catalogue_grist", return_value=catalogue):
                page = self.client.post(catalogues, {"action": "ajouter", "url": url}, follow=True)
            self.assertEqual(len(page.context["destinations_publication"]), 1)
            self.assertContains(page, "Publication de la classe le", count=2)
            self.assertContains(page, "Sélection de compétences")
            destination["editions"].append({"Numero": 1, "Referentiel": selection["reference"],
                                           "Titre": selection["titre"], "Contenu": "{}"})
            refus = self.client.post(echange, {**donnees, "reference_grist": selection["reference"]})
            self.assertContains(refus, "Une sélection de compétences ne peut pas recevoir une édition")
            reprise = self.client.post(echange, {"action": "publier-grist", "destination_grist": url,
                                                "nom_catalogue_grist": "Ressources de l’équipe"})
            self.assertContains(reprise, "Édition 1 déjà publiée")
            self.assertContains(reprise, "Nouvelle édition")
            self.assertEqual(reprise.context["derniere_destination"].url, url)
            self.assertEqual(reprise.context["derniere_destination"].nom, destination["nom"])
            publier.assert_called_once()
            self.adapter(adoption, classe=True, texte="Nouvelle formulation")
            apercu = self.client.post(echange, {"action": "voir-grist", "destination_grist": url})
            self.assertEqual(apercu.context["edition_prevue"], 2)
            publier.assert_called_once()
            revision = self.client.post(echange, {"action": "publier-grist", "destination_grist": url})
            self.assertContains(revision, "Édition 2 publiée")
            self.assertContains(revision, destination["nom"])
            self.assertEqual(publier.call_args.args[3], 2)

    def test_icones_zip_et_grist_utilisent_les_options_de_leur_action(self):
        from copy import deepcopy
        from io import BytesIO

        from PIL import Image

        from .icones_partagees import encoder_icone
        from .services.paquets_referentiels import lire_paquet_icones

        self.adopter()
        echange = reverse("paquets_referentiels_classe", args=[self.classe.pk])
        image = BytesIO()
        Image.new("RGBA", (1, 1)).save(image, format="PNG")
        projection = document("projection-fictive")
        projection["format"] = 2
        projection["domaines"][0]["competences"][0]["icone_png"] = encoder_icone(image.getvalue())
        url = "https://grist.numerique.gouv.fr/o/docs/document-fictif"
        destination = {"url": url, "nom": "Ressources", "espace": "docs", "editions": [],
                       "mode_contenu": "complet"}
        with patch("suivi.views_paquets_referentiels.preparer_referentiel_classe", side_effect=lambda *args: deepcopy(projection)):
            page = self.client.get(echange)
            self.assertContains(page, "Télécharger un ZIP d’icônes seules")
            icones = self.client.post(echange, {"action": "telecharger-icones-classe"})
            self.assertEqual(len(lire_paquet_icones(icones.content)), 1)
            archive = self.client.post(echange, {"action": "telecharger-classe"})
            self.assertNotIn("icone_png", lire_paquet(archive.content))
            archive = self.client.post(echange, {"action": "telecharger-classe", "inclure_icones": "oui"})
            self.assertIn("icone_png", lire_paquet(archive.content))
            with patch("suivi.publication_grist.destination_grist", return_value=destination), patch(
                "suivi.publication_grist.publier_edition_grist",
            ) as publier, patch("suivi.publication_grist.enregistrer_mode_catalogue_grist") as enregistrer:
                reponse = self.client.post(echange, {"action": "publier-grist", "url_grist": url,
                                                      "mode_contenu_grist": "competences"})
                self.assertContains(reponse, "Édition 1 publiée")
                self.assertIn("icone_png", contenu_grist(publier.call_args.args[-1]))
                enregistrer.assert_not_called()

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
