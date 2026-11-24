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
                             suivis + "?espace=1#espace-partage")
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
        page = self.client.get(suivis, {"decouvrir": "1", "groupe": "document-fictif"})
        self.assertContains(page, "Voir les référentiels de cet espace")
        self.assertContains(page, 'id="referentiels-espace-document-fictif" open')
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

    def test_journal_equipe_offline_et_fusion_apres_reception_des_branches(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from .models import ContributionReferentielEquipe
        from .services.journal_referentiel_equipe import contribution, identifiant_contribution
        from .services.paquets_referentiels import empaqueter
        from .tests_import_sources_referentiels import document

        self.adopter()
        espace = reverse("espace_grist_classe", args=[self.classe.pk])
        adresse = "https://grist.numerique.gouv.fr/o/docs/document-fictif"
        self.client.post(espace, {"grist": adresse, "confirmer": "oui"})
        equipe = reverse("referentiel_equipe_grist", args=[self.classe.pk])
        transfert = reverse("transfert_equipe_grist", args=[self.classe.pk]) + "?espace=document-fictif"
        depart = document()
        fichier = SimpleUploadedFile("equipe.zip", empaqueter(depart))
        self.assertRedirects(self.client.post(equipe, {"action": "ajouter", "paquet": fichier}), equipe)
        base = self.client.get(transfert).json()["a_envoyer"][0]
        self.assertEqual(ContributionReferentielEquipe.objects.count(), 1)
        self.assertFalse(ContributionReferentielEquipe.objects.get().envoyee)
        self.assertEqual(self.client.post(transfert, base, content_type="application/json").status_code, 200)

        têtes = []
        for n in (3, 2):
            doc = document(version=str(n))
            doc["domaines"][0]["competences"].append(
                {"identite": f"ajout-{n}", "code": f"A{n}", "libelle": f"Ajout {n}", "niveau": "PS"},
            )
            edition = contribution([base["empreinte"]], doc)
            cle = identifiant_contribution(edition)
            têtes.append(cle)
            for _ in range(2):
                self.assertEqual(self.client.post(transfert, {"edition": edition, "empreinte": cle},
                                                  content_type="application/json").status_code, 200)
        self.assertEqual(ContributionReferentielEquipe.objects.count(), 3)
        self.assertRedirects(self.client.post(equipe, {"action": "fusionner", "parent": sorted(têtes)}), equipe)
        a_envoyer = self.client.get(transfert).json()["a_envoyer"]
        self.assertEqual(len(a_envoyer), 1)
        fusion = a_envoyer[0]["edition"]
        self.assertEqual(fusion["parents"], sorted(têtes))
        self.assertEqual({c["identite"] for c in fusion["document"]["domaines"][0]["competences"]},
                         {"oser-parler", "ajout-2", "ajout-3"})
        self.assertEqual(VersionReferentiel.objects.count(), 1)
        self.assertRedirects(self.client.post(equipe, {"action": "catalogue", "edition": a_envoyer[0]["empreinte"]}),
                             equipe)
        self.assertEqual(VersionReferentiel.objects.filter(source__identifiant_diffusion="equipe-grist-document-fictif").count(), 1)
        self.assertEqual(self.client.get(transfert.replace("document-fictif", "autre-document")).status_code, 409)

    @override_settings(ROOT_URLCONF="carnet.urls")
    def test_routes_partage_communes_en_mode_binaire_et_protegees_sur_serveur(self):
        self.adopter()
        espace = reverse("espace_grist_classe", args=[self.classe.pk])
        self.assertContains(self.client.get(espace), "Rejoindre l’espace de partage")
        with self.settings(MODE_LOCAL=False, MODE_PWA=False):
            self.assertEqual(self.client.get(espace).status_code, 404)


    def test_ariane_et_confirmation_du_partage(self):
        self.adopter()
        suivis = reverse("suivis_referentiels_classe", args=[self.classe.pk])
        espace = reverse("espace_grist_classe", args=[self.classe.pk])
        page = self.client.get(suivis)
        self.assertContains(page, '<li aria-current="page">Catalogues et partage</li>')
        ariane = page.content.decode().split('aria-label="Fil d’Ariane"', 1)[1].split("</nav>", 1)[0]
        self.assertIn("Compétences", ariane)
        self.assertNotIn("Réglages du référentiel", ariane)
        self.assertContains(self.client.get(espace), "automatique")
        erreur = self.client.post(espace, {"grist": "https://grist.numerique.gouv.fr/document-fictif"})
        self.assertContains(erreur, "Cochez cette case pour confirmer", status_code=400)
        self.assertContains(erreur, 'aria-required="true" aria-invalid="true"', status_code=400)
        self.assertFalse(PartageGristClasse.objects.exists())

    @override_settings(ROOT_URLCONF="carnet.urls", MODE_LOCAL=False, MODE_PWA=False)
    def test_edition_directe_du_referentiel_equipe_sur_le_serveur(self):
        from .models import ContributionReferentielEquipe
        from .services.journal_referentiel_equipe import terminaisons

        adoption = self.adopter()
        equipe = reverse("referentiel_equipe_grist", args=[self.classe.pk])
        self.assertRedirects(self.client.post(equipe, {"action": "initialiser"}), equipe)
        base = ContributionReferentielEquipe.objects.get()
        self.assertEqual(base.document_grist, "")
        self.assertRedirects(self.client.post(equipe, {
            "action": "ajouter-competence", "parent": base.empreinte, "rubrique": "LANG",
            "libelle": "Ajout commun", "niveau": "GS",
        }), equipe)
        modifiee = ContributionReferentielEquipe.objects.exclude(pk=base.pk).get()
        competence = next(c for c in modifiee.edition["document"]["domaines"][0]["competences"]
                          if c["libelle"] == "Ajout commun")
        self.assertRedirects(self.client.post(equipe, {
            "action": "modifier-competence", "parent": modifiee.empreinte,
            "reference": competence["identite"], "libelle": "Ajout renommé", "niveau": "GS",
        }), equipe)
        page = self.client.get(equipe)
        self.assertContains(page, "Ajout renommé")
        editions = dict(ContributionReferentielEquipe.objects.values_list("empreinte", "edition"))
        nouvelle = editions[terminaisons(editions)[0]]["document"]
        self.assertTrue(any(c["identite"] == competence["identite"] and c["libelle"] == "Ajout renommé"
                            for c in nouvelle["domaines"][0]["competences"]))
        adoption.refresh_from_db()
        self.assertTrue(adoption.courante)
