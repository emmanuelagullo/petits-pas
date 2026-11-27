from unittest.mock import patch

from django.urls import reverse

from .models import AdoptionReferentiel, ChoixApplicationAnnuel, ChoixEcoleAnnuel, DestinationPublicationGrist, Observation, SourceReferentiel, VersionReferentiel
from .services.catalogues_externes import CATALOGUE_DEMONSTRATION, identite_grist
from .services.pedagogie import modifier_etat
from .tests import Base
from . import tests_adoption_bases_referentiels as adoption_fixtures


class CataloguesReferentiels(Base):
    adopter = adoption_fixtures.AdoptionBases.adopter

    def test_decouverte_depuis_import_ecole_conserve_le_retour(self):
        self.entrer("dir-mdp")
        annee = self.classe.annee_scolaire
        echange = reverse("paquets_referentiels_ecole")
        decouvrir = reverse("decouvrir_referentiels")
        self.assertContains(self.client.get(echange, {"annee": annee}),
                            f'href="{decouvrir}?annee={annee}&amp;depuis=echange"')
        page = self.client.get(decouvrir, {"annee": annee, "depuis": "echange", "q": "langage"})
        self.assertContains(page, f'href="{echange}?annee={annee}#import-referentiel"')
        self.assertContains(page, 'name="depuis" value="echange"')
        self.assertIn("depuis=echange", page.context["examen_grist"])
        retour = self.client.get(page.context["examen_grist"]).context["retour_decouverte"]
        self.assertIn("depuis=echange", retour)
        self.assertIn("q=langage", retour)

    def test_catalogue_instance_consulte_selon_les_choix_de_lecole(self):
        self.entrer("dir-mdp")
        annee = self.classe.annee_scolaire
        source = SourceReferentiel.objects.create(identifiant="instance-test", titre="Titre instance fictif")
        version = VersionReferentiel.objects.create(source=source, numero="1", empreinte="a" * 64,
                                                     contenu={"origine": "source_declaree"})
        choix, _ = ChoixApplicationAnnuel.objects.update_or_create(annee_scolaire=annee,
                                                                   defaults={"configure": True})
        choix.versions_autorisees.add(version)
        url = reverse("decouvrir_referentiels")
        page = self.client.get(url, {"annee": annee})
        self.assertContains(page, "Catalogue de cette instance Petits Pas")
        self.assertNotContains(page, "Catalogue d’essai")
        self.assertContains(page, "Titre instance fictif", count=1)
        self.assertContains(page, f'?annee={annee}&amp;version={version.pk}')
        ChoixEcoleAnnuel.objects.update_or_create(ecole=self.ecole, annee_scolaire=annee,
                                                  defaults={"restreindre": True})
        page = self.client.get(url, {"annee": annee, "q": "titre instance fictif"})
        self.assertContains(page, "Hors des choix autorisés à l’école")
        self.assertNotContains(page, f'?annee={annee}&amp;version={version.pk}')
        self.assertNotContains(page, "Catalogue d’essai")

    def test_ajout_catalogue_propose_le_suivi_et_conserve_un_refus(self):
        self.entrer("dir-mdp")
        url = reverse("decouvrir_referentiels")
        grist = "https://grist.numerique.gouv.fr/o/docs/catalogue-fictif"
        donnees = {"action": "ajouter", "url": grist, "suivre_catalogue": "oui"}
        self.assertContains(self.client.get(url), 'name="suivre_catalogue" value="oui" checked')
        with patch("suivi.views_catalogues_referentiels.lire_catalogue_grist", return_value={
            "nom": "Catalogue fictif", "url": grist, "referentiels": [],
        }):
            self.assertContains(self.client.post(url, donnees), "Catalogue disponible pour l’école.")
            self.ecole.refresh_from_db()
            self.assertTrue(self.ecole.catalogues_referentiels[grist]["suivre_catalogue"])
            self.client.post(url, {"action": "ne-plus-suivre-catalogue", "catalogue": grist})
            self.client.post(url, donnees)
            self.ecole.refresh_from_db()
            self.assertFalse(self.ecole.catalogues_referentiels[grist]["suivre_catalogue"])

    def test_responsable_gere_ses_catalogues_et_retrouve_le_choix_ecole(self):
        self.entrer()
        url = reverse("decouvrir_referentiels") + f"?classe={self.classe.pk}&gestion=classe"
        grist = "https://grist.numerique.gouv.fr/o/docs/catalogue-classe"
        with patch("suivi.views_catalogues_referentiels.lire_catalogue_grist", return_value={
            "nom": "Catalogue de test", "url": grist, "referentiels": [],
        }):
            page = self.client.post(url, {"action": "ajouter", "url": grist, "suivre_catalogue": "oui"})
        self.assertContains(page, "Géré par la classe")
        self.classe.refresh_from_db()
        self.ecole.refresh_from_db()
        self.assertTrue(self.classe.catalogues_propres[grist]["suivre_catalogue"])
        self.assertNotIn(grist, self.ecole.catalogues_referentiels)
        self.ecole.catalogues_referentiels[grist] = {"catalogue": {
            "nom": "Catalogue commun", "url": grist, "referentiels": [],
        }, "suivre_catalogue": False}
        self.ecole.save(update_fields=["catalogues_referentiels"])
        self.assertContains(self.client.get(url), "Reprendre le choix de l’école")
        self.assertContains(self.client.post(url, {"action": "heriter-catalogue", "catalogue": grist}),
                            "Catalogue commun")
        self.classe.refresh_from_db()
        self.assertNotIn(grist, self.classe.catalogues_propres)

    def test_ajouter_et_actualiser_un_catalogue_depuis_la_classe(self):
        self.entrer()
        url = reverse("suivis_referentiels_classe", args=[self.classe.pk])
        grist = "https://grist.numerique.gouv.fr/o/docs/catalogue-classe"
        catalogue = {"nom": "Catalogue de recette", "url": grist, "referentiels": [
            {"reference": "recette", "titre": "Référentiel de recette", "editions": [1]},
        ]}
        page = self.client.post(url, {"action": "ajouter", "url": "lien-invalide"})
        self.assertContains(page, 'id="ajouter-catalogue" open', status_code=400)
        self.assertContains(page, 'value="lien-invalide"', status_code=400)
        with patch("suivi.views_catalogues_referentiels.lire_catalogue_grist", return_value=catalogue):
            page = self.client.post(url, {"action": "ajouter", "url": grist}, follow=True)
            self.assertContains(page, "Catalogue enregistré.")
            self.assertContains(page, "Référentiel de recette")
            self.assertContains(page, "Examiner l’édition")
            self.assertNotContains(page, "Importer un ZIP pour la classe")
            catalogue["referentiels"][0]["editions"] = [2, 1]
            page = self.client.post(url, {"action": "actualiser-catalogue", "catalogue": grist}, follow=True)
            self.assertContains(page, "Catalogue actualisé.")
            self.assertContains(page, 'name="numero" value="2"')

    def test_catalogue_presente_le_contenu_de_la_classe_sans_import(self):
        from .models import PartageGristClasse

        self.entrer()
        grist = "https://grist.numerique.gouv.fr/o/docs/catalogue-fictif"
        partage = PartageGristClasse.objects.create(classe=self.classe, url=grist, licence="CC0-1.0")
        reference = f"classe-grist-{partage.identifiant}"
        catalogue = {"nom": "Catalogue extérieur", "url": grist, "referentiels": [
            {"reference": reference, "titre": "Contenu de la classe", "editions": ["a" * 64],
             "contenu_courant": True},
        ]}
        suivis = reverse("suivis_referentiels_classe", args=[self.classe.pk])
        with patch("suivi.views_catalogues_referentiels.lire_catalogue_grist", return_value=catalogue):
            page = self.client.post(suivis, {"action": "ajouter", "url": grist}, follow=True)
        self.assertContains(page, "Partagé par votre classe")
        self.assertNotContains(page, "Examiner le contenu courant")
        echange = reverse("paquets_referentiels_classe", args=[self.classe.pk]) + "?volet=importer&destination=classe"
        refus = self.client.post(echange, {"action": "apercu-grist", "catalogue": grist,
                                         "reference": reference, "numero": "a" * 64})
        self.assertContains(refus, "Ce référentiel est déjà disponible", status_code=400)

    def test_proposition_depuis_le_referentiel_courant(self):
        from .models import PropositionReferentiel

        from .services.choix_bases_referentiels import publier_choix_application
        from .tests_import_sources_referentiels import document, importer

        self.entrer()
        version = importer(document())[0]
        publier_choix_application(annee=self.classe.annee_scolaire, versions_ids=[version.pk],
                                  proposee_id=version.pk, revision_attendue=0)
        self.adopter(version)
        competence = reverse("catalogue_competences", args=[self.classe.pk])
        self.assertContains(self.client.get(competence), "Proposer au catalogue de l’école")
        proposition = reverse("proposer_referentiel_classe", args=[self.classe.pk])
        apercu = self.client.post(proposition, {"action": "examiner-classe"})
        self.assertContains(apercu, "Envoyer la proposition")
        self.assertFalse(PropositionReferentiel.objects.exists())
        self.assertRedirects(self.client.post(proposition, {"action": "proposer", "jeton": apercu.context["jeton"]}),
                             competence + "#actions-referentiel-classe")
        self.assertEqual(PropositionReferentiel.objects.get().classe, self.classe)

    def test_catalogue_fourni_est_reserve_au_mode_essai(self):
        self.entrer()
        url = reverse("suivis_referentiels_classe", args=[self.classe.pk])
        self.assertNotContains(self.client.get(url), "Catalogue d’essai")
        with self.settings(ESPACE_ESSAI=True):
            self.assertContains(self.client.get(url), "Catalogue d’essai")
            self.assertContains(self.client.get(url), "Référentiel des Chardonnerets")

    def test_lien_de_catalogue_modifiable_sans_changer_identite_ni_mode(self):
        self.entrer()
        url = reverse("suivis_referentiels_classe", args=[self.classe.pk])
        grist = "https://grist.numerique.gouv.fr/o/docs/catalogue-classe"
        self.classe.catalogues_propres = {grist: {"suivre_catalogue": True, "catalogue": {
            "nom": "Catalogue de la classe", "url": grist, "referentiels": [],
        }}}
        self.classe.save(update_fields=["catalogues_propres"])
        donnees = {"action": "modifier-lien-catalogue", "catalogue": grist, "url": grist + "/ressources"}
        with patch("suivi.views_catalogues_referentiels.lire_catalogue_grist", return_value={
            "nom": "Untitled document", "url": grist, "referentiels": [],
        }) as lire:
            page = self.client.post(url, donnees, follow=True)
            self.assertContains(page, "Catalogue de la classe")
            self.assertContains(page, donnees["url"])
            self.assertNotContains(page, "Untitled document")
            self.assertContains(page, 'value="suivre-catalogue" checked')
            refus = self.client.post(url, {**donnees, "url": grist.replace("catalogue-classe", "autre-catalogue")})
            self.assertContains(refus, "Ce lien désigne un autre document", status_code=400)
            lire.assert_called_once_with(donnees["url"])
        self.classe.refresh_from_db()
        self.assertEqual(list(self.classe.catalogues_propres), [grist])
        self.assertTrue(self.classe.catalogues_propres[grist]["suivre_catalogue"])

    def test_import_prive_reserve_a_la_classe_et_au_contexte_confirme(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from .models import SourceReferentiel
        from .services.choix_bases_referentiels import choix_bases
        from .services.paquets_referentiels import empaqueter
        from .tests_import_sources_referentiels import document

        self.entrer()
        echange = reverse("paquets_referentiels_classe", args=[self.classe.pk])
        url = echange + "?volet=importer&destination=classe"
        paquet = SimpleUploadedFile("exemple.zip", empaqueter(document("prive-classe")))
        page = self.client.post(url, {"action": "apercu", "paquet": paquet})
        self.assertContains(page, "Confirmer l’import")
        self.assertContains(page, "Proposer au catalogue de l’école")
        proposition = reverse("proposer_referentiel_classe", args=[self.classe.pk])
        apercu = self.client.post(proposition, {"action": "reprendre-apercu", "jeton_import": page.context["jeton"]})
        self.assertContains(apercu, "Note à la direction")
        self.assertContains(apercu, "Importer une édition")
        retour = self.client.get(apercu.context["retour_import"])
        self.assertEqual(retour.context["jeton"], page.context["jeton"])
        self.assertContains(retour, "Confirmer l’import")

        confirmation = {"action": "importer", "jeton": page.context["jeton"]}
        self.assertEqual(self.client.post(echange, confirmation).status_code, 403)
        self.assertContains(self.client.post(url, confirmation), "Édition ajoutée au catalogue de la classe.")
        source = SourceReferentiel.objects.get(identifiant_diffusion="prive-classe")
        self.assertEqual(source.classe_privee_id, self.classe.pk)
        self.assertNotIn(source.versions.get(), choix_bases(self.ecole, self.classe.annee_scolaire).versions)

    def test_examiner_et_importer_grist_sur_place(self):
        import yaml

        from .tests_import_sources_referentiels import document

        self.entrer()
        echange = reverse("paquets_referentiels_classe", args=[self.classe.pk])
        url = echange + "?volet=importer&destination=classe&depuis=catalogues&catalogue=catalogue-123abcdef456"
        with patch("suivi.views_paquets_referentiels.edition_grist", return_value=(
            yaml.safe_dump(document("source-grist-fictive")), {"mode_contenu": "complet"},
        )):
            apercu = self.client.post(url, {"action": "apercu-grist", "numero": "1", "fragment_catalogue": "1"},
                                      HTTP_HX_REQUEST="true")
        self.assertContains(apercu, "Importer pour la classe")
        self.assertNotContains(apercu, "<html")
        confirme = self.client.post(url, {"action": "importer", "jeton": apercu.context["jeton"],
                                              "fragment_catalogue": "1"}, HTTP_HX_REQUEST="true")
        self.assertContains(confirme, "Édition ajoutée au catalogue de la classe.")
        self.assertNotContains(confirme, "<html")

    def test_actualisation_recoit_les_editions_connues_dans_le_perimetre_classe(self):
        import yaml

        from .services.actualisation_catalogues import actualiser_catalogues_classe
        from .services.catalogues_externes import identite_grist
        from .tests_import_sources_referentiels import document, importer

        url = "https://grist.numerique.gouv.fr/o/docs/catalogue-classe"
        reference = "progression"
        identifiant = identite_grist(url, reference)
        version, _, _ = importer(document(identifiant), ecole=self.ecole, classe=self.classe)
        catalogue = {"url": url, "nom": "Catalogue fictif", "referentiels": [
            {"reference": reference, "editions": [2, 1]},
            {"reference": "inconnu", "editions": [1]},
        ]}
        self.classe.catalogues_propres = {url: {"suivre_catalogue": True, "catalogue": catalogue}}
        self.classe.save(update_fields=["catalogues_propres"])
        with patch("suivi.services.actualisation_catalogues.lire_catalogue_grist", return_value=catalogue), patch(
            "suivi.services.actualisation_catalogues.edition_grist",
            return_value=yaml.safe_dump(document(identifiant, "2"), allow_unicode=True),
        ) as lire:
            self.assertEqual(actualiser_catalogues_classe(self.enseignant, self.classe), (1, []))
            self.assertEqual(actualiser_catalogues_classe(self.enseignant, self.classe), (0, []))
        lire.assert_called_once_with(url, reference, 2)
        self.assertEqual(set(version.source.versions.values_list("numero", flat=True)), {"1", "2"})

    def test_suivre_un_catalogue_sans_suivre_encore_de_referentiel(self):
        self.ecole.catalogues_referentiels = {CATALOGUE_DEMONSTRATION: {"catalogue": {
            "url": CATALOGUE_DEMONSTRATION, "nom": "Catalogue fictif",
            "referentiels": [{"reference": "demo-cycle1", "titre": "Langage en maternelle", "editions": [2, 1]}],
        }}}
        self.ecole.save(update_fields=["catalogues_referentiels"])
        self.entrer("dir-mdp")
        url = reverse("decouvrir_referentiels")
        reponse = self.client.post(url, {"action": "suivre-catalogue", "catalogue": CATALOGUE_DEMONSTRATION})
        self.assertEqual(reponse.status_code, 302)
        with patch("suivi.views_catalogues_referentiels.lire_catalogue_grist", return_value={
            "nom": "Catalogue fictif", "url": CATALOGUE_DEMONSTRATION,
            "referentiels": [{"reference": "nouveau", "titre": "Nouveau référentiel", "editions": [1]}],
        }) as lire:
            page = self.client.post(url, {"action": "verifier"})
        lire.assert_called_once_with(CATALOGUE_DEMONSTRATION)
        self.assertContains(page, "Nouveau référentiel")
        self.assertTrue(page.context["groupes"][-1]["lignes"][0]["nouveau"])

    def test_decouvrir_suivre_importer_et_adopter_une_revision_grist(self):
        self.ecole.catalogues_referentiels = {CATALOGUE_DEMONSTRATION: {"catalogue": {
            "url": CATALOGUE_DEMONSTRATION, "nom": "Catalogue fictif",
            "referentiels": [{"reference": "demo-cycle1", "titre": "Langage en maternelle", "editions": [2, 1]}],
        }}}
        self.ecole.save(update_fields=["catalogues_referentiels"])
        self.entrer("dir-mdp")
        annee = self.classe.annee_scolaire
        decouvrir = reverse("decouvrir_referentiels") + f"?annee={annee}&q=langage"
        echange = reverse("paquets_referentiels_ecole") + f"?annee={annee}&origine=decouverte&q=langage"
        metadata = {"name": "Catalogue fictif", "id": CATALOGUE_DEMONSTRATION.rsplit("/", 1)[-1]}
        editions = [{"Referentiel": "demo-cycle1", "Numero": n, "Titre": "Langage en maternelle"} for n in (1, 2)]
        competences = [
            {"Edition": n, "Rubrique": "Langage", "Code": code, "Libelle": libelle}
            for n, code, libelle in [
                (1, "LANG-01", "Raconter un événement"),
                (2, "LANG-01", "Raconter un événement vécu"),
                (2, "LANG-02", "Décrire une image"),
            ]
        ]

        def reponse_api(prefixe, document, chemin=""):
            if not chemin:
                return metadata
            if chemin == "/tables":
                return {"tables": [{"id": "Editions"}, {"id": "Competences"}]}
            lignes = editions if "/Editions/" in chemin else competences
            return {"records": [{"fields": ligne} for ligne in lignes]}

        def importer(numero):
            self.client.force_login(self.direction)
            page = self.client.post(echange, {
                "action": "apercu-grist", "catalogue": CATALOGUE_DEMONSTRATION,
                "reference": "demo-cycle1", "numero": numero,
            })
            self.assertContains(page, "Confirmer l’import")
            self.assertContains(page, "Retour à Découvrir des référentiels")
            self.assertIn("q=langage", page.context["retour_decouverte"])
            if numero == 2:
                self.assertEqual(page.context["edition_comparee"], "1")
            resultat = self.client.post(echange, {"action": "importer", "jeton": page.context["jeton"]})
            self.assertContains(resultat, "Édition ajoutée au catalogue")
            identite = identite_grist(CATALOGUE_DEMONSTRATION, "demo-cycle1")
            return SourceReferentiel.objects.get(ecole=self.ecole, identifiant_diffusion=identite).versions.get(numero=numero)

        with patch("suivi.services.catalogues_externes.lire_api", side_effect=reponse_api) as api:
            self.assertContains(self.client.get(decouvrir), "Langage en maternelle")
            api.assert_not_called()
            page = self.client.post(decouvrir, {"action": "ajouter", "url": CATALOGUE_DEMONSTRATION})
            self.assertContains(page, "Catalogue fictif")
            self.assertRedirects(self.client.post(decouvrir, {
                "action": "suivre", "catalogue": CATALOGUE_DEMONSTRATION, "reference": "demo-cycle1",
            }), decouvrir + "&filtre=")
            self.assertContains(self.client.get(decouvrir + "&filtre=suivis"), "Langage en maternelle")
            url_import = reverse("paquets_referentiels_ecole") + f"?annee={annee}"
            page = self.client.get(url_import)
            self.assertContains(page, "Référentiels à importer depuis un catalogue")
            self.assertContains(page, "Langage en maternelle")
            autre_catalogue = "https://grist.numerique.gouv.fr/o/docs/catalogue-publie"
            DestinationPublicationGrist.objects.create(
                ecole=self.ecole, auteur=self.direction, classe=self.classe, url=autre_catalogue,
                nom="Catalogue de publication", identifiant_local="langage", reference="demo-cycle1",
            )
            api.reset_mock()
            page = self.client.get(url_import)
            self.assertContains(page, "Catalogue de publication")
            self.assertNotContains(page, f'value="{autre_catalogue}" selected')
            api.assert_not_called()
            page = self.client.get(url_import, {"catalogue_import": autre_catalogue})
            self.assertContains(page, "Examiner cette édition")
            api.assert_called()
            page = self.client.post(url_import, {"action": "ouvrir-catalogue-grist",
                                                  "lien_catalogue_import": CATALOGUE_DEMONSTRATION})
            self.assertContains(page, "Examiner cette édition")
            premiere = importer(1)
            initiale = self.adopter(premiere)
            echange_classe = reverse("paquets_referentiels_classe", args=[self.classe.pk])
            self.client.force_login(self.direction)
            page = self.client.get(echange_classe)
            self.assertContains(page, "Source du référentiel de la classe")
            self.assertEqual(page.context["editions_import"][0]["reference"], "demo-cycle1")
            page = self.client.post(echange_classe, {"action": "apercu-grist",
                "catalogue": CATALOGUE_DEMONSTRATION, "reference": "demo-cycle1", "numero": 2})
            self.assertContains(page, "Confirmer l’import")
            competence = initiale.usages.get().competence
            modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=competence, statut="reussi")
            observations = list(Observation.objects.values())
            self.assertTrue(observations)
            seconde = importer(2)
            self.assertTrue(AdoptionReferentiel.objects.get(pk=initiale.pk).courante)
            actuelle = self.adopter(seconde)
            self.assertTrue(actuelle.usages.filter(competence=competence).exists())
            self.assertEqual(list(Observation.objects.values()), observations)
