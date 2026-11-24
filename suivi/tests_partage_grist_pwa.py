import json

from django.test import override_settings
from django.urls import reverse

from pwa.partage_grist import empreinte
from .models import PartageGristClasse, VersionReferentiel
from . import tests_mises_a_jour_referentiels as fixtures
from .tests import Base


@override_settings(ROOT_URLCONF="pwa.urls", MODE_LOCAL=True)
class PartageGristPWA(Base):
    adopter = fixtures.MisesAJour.adopter

    def setUp(self):
        # Préparer la même source versionnée que les recettes d’adoption.
        super().setUp()
        from .tests_import_sources_referentiels import document, importer
        from .services.choix_bases_referentiels import publier_choix_application
        self.a = importer(document())[0]
        publier_choix_application(annee=self.classe.annee_scolaire, versions_ids=[self.a.pk],
                                 proposee_id=self.a.pk, revision_attendue=0)
        self.entrer()

    def test_propre_identifiant_ignore_et_confirmation_idempotente(self):
        from uuid import uuid4

        self.adopter()
        espace = reverse("espace_grist_classe", args=[self.classe.pk])
        grist = "https://grist.numerique.gouv.fr/o/docs/document-fictif"
        self.assertContains(self.client.get(espace, {"grist": grist}), grist)
        self.assertFalse(PartageGristClasse.objects.exists())
        suivis = reverse("suivis_referentiels_classe", args=[self.classe.pk])
        self.assertRedirects(self.client.post(espace, {"grist": grist, "confirmer": "oui"}),
                             suivis + "#espace-partage")
        url = reverse("synchroniser_grist")
        données = self.client.get(url).json()
        travail = données["partages"][0]
        self.assertEqual(données["propres"], [travail["id"]])
        self.assertEqual(travail["empreinte"], empreinte(travail["contenu"]))
        distant = str(uuid4())
        reçu = json.loads(travail["contenu"])
        reçu["source"]["titre"] = "Référentiel du collègue"
        lignes = [{"Identifiant": travail["id"], "Contenu": "ne doit jamais être importé"},
                  {"Identifiant": distant, "Contenu": json.dumps(reçu)}]
        confirmation = {"id": travail["id"], "api": travail["api"], "lignes": lignes,
                        "nom": "Mon École partagée", "confirme": travail["empreinte"]}
        for _ in range(2):
            self.assertEqual(self.client.post(url, confirmation, content_type="application/json").json(),
                             {"erreurs": 0, "nom": "Mon École partagée"})
        self.assertEqual(VersionReferentiel.objects.filter(source__titre="Référentiel du collègue").count(), 1)
        self.assertIsNone(self.client.get(url).json()["partages"][0]["contenu"])
        self.client.post(espace, {"action": "suspendre"})
        self.assertEqual(self.client.get(url).json()["partages"], [])
        self.client.post(espace, {"grist": grist, "confirmer": "oui"})
        self.assertEqual(self.client.get(url).json()["partages"][0]["id"], travail["id"])

    def test_licence_manquante_indique_la_source_sans_connecter_la_classe(self):
        self.adopter()
        self.a.source.licence = "Non renseignée"
        self.a.source.save(update_fields=["licence"])
        espace = reverse("espace_grist_classe", args=[self.classe.pk])
        grist = "https://grist.numerique.gouv.fr/o/docs/document-fictif"
        reponse = self.client.post(espace, {"grist": grist, "confirmer": "oui", "nom_espace": "Équipe"})
        self.assertContains(reponse, "Licence à vérifier pour " + self.a.source.titre, status_code=400)
        self.assertContains(reponse, 'value="Équipe"', status_code=400)
        self.assertFalse(PartageGristClasse.objects.exists())

    def test_invitation_prefill_sans_ecriture_puis_reouverture_sans_effet(self):
        self.adopter()
        invitation = reverse("invitation_grist")
        espace = reverse("espace_grist_classe", args=[self.classe.pk])
        grist = "https://grist.numerique.gouv.fr/o/docs/document-fictif"
        destination = self.client.get(invitation, {"grist": grist}, follow=True)
        self.assertContains(destination, grist)
        self.assertFalse(PartageGristClasse.objects.exists())
        self.assertContains(self.client.get(invitation, {"grist": "https://example.org/abc"}),
                            "Collez le lien", status_code=400)
        self.client.post(espace, {"grist": grist, "confirmer": "oui"})
        partage = PartageGristClasse.objects.get()
        identifiant = partage.identifiant
        self.client.post(espace, {"action": "suspendre"})
        self.assertRedirects(self.client.get(espace, {"grist": grist}), espace)
        self.assertRedirects(self.client.get(espace, {"grist": grist.replace("/o/docs", "")}), espace)
        partage.refresh_from_db()
        self.assertEqual(partage.identifiant, identifiant)
        self.assertFalse(partage.actif)

    def test_invitation_conservee_par_le_parcours_de_connexion(self):
        self.client.logout()
        invitation = reverse("invitation_grist")
        reponse = self.client.get(invitation, {"grist": "https://grist.numerique.gouv.fr/document-fictif"})
        self.assertRedirects(reponse, reverse("connexion"))
        self.assertTrue(self.client.session["suivant"].startswith(invitation + "?grist="))
