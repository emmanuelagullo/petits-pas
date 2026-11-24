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
        self.assertContains(page, "Catalogue de démonstration Petits Pas")
        self.assertContains(page, "Titre instance fictif", count=1)
        self.assertContains(page, f'?annee={annee}&amp;version={version.pk}')
        ChoixEcoleAnnuel.objects.update_or_create(ecole=self.ecole, annee_scolaire=annee,
                                                  defaults={"restreindre": True})
        page = self.client.get(url, {"annee": annee, "q": "titre instance fictif"})
        self.assertContains(page, "Hors des choix autorisés à l’école")
        self.assertNotContains(page, f'?annee={annee}&amp;version={version.pk}')
        self.assertNotContains(page, "Catalogue de démonstration Petits Pas")

    def test_suivre_un_catalogue_sans_suivre_encore_de_referentiel(self):
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
