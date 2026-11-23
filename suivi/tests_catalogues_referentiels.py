from unittest.mock import patch

from django.urls import reverse

from .models import AdoptionReferentiel, Observation, SourceReferentiel
from .services.catalogues_externes import CATALOGUE_DEMONSTRATION, identite_grist
from .services.pedagogie import modifier_etat
from .tests import Base
from . import tests_adoption_bases_referentiels as adoption_fixtures


class CataloguesReferentiels(Base):
    adopter = adoption_fixtures.AdoptionBases.adopter

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
            premiere = importer(1)
            initiale = self.adopter(premiere)
            competence = initiale.usages.get().competence
            modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=competence, statut="reussi")
            observations = list(Observation.objects.values())
            self.assertTrue(observations)
            seconde = importer(2)
            self.assertTrue(AdoptionReferentiel.objects.get(pk=initiale.pk).courante)
            actuelle = self.adopter(seconde)
            self.assertTrue(actuelle.usages.filter(competence=competence).exists())
            self.assertEqual(list(Observation.objects.values()), observations)
