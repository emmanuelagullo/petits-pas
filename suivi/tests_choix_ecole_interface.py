import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.urls import reverse

from comptes.models import AppartenanceEcole, ResponsabiliteEcole
from .models import (AdoptionReferentiel, ChoixEcoleAnnuel, Ecole, EtatAnnuelObservation,
                     Observation, Trace, VersionSourceEcole)
from .services.choix_bases_referentiels import choix_bases, publier_choix_application
from .services.reprise_referentiels import reprendre
from .tests import Base
from .tests_import_sources_referentiels import document, importer


class ChoixEcoleInterface(Base):
    def setUp(self):
        super().setUp()
        self.creer_trace(commentaire="Parcours fictif conservé")
        reprendre(self.ecole.pk)
        self.a = importer(document("fictive-a"))[0]
        self.b = importer(document("fictive-b"))[0]
        self.annee = self.classe.annee_scolaire
        publier_choix_application(annee=self.annee, versions_ids=[self.a.pk, self.b.pk],
                                 proposee_id=self.a.pk, revision_attendue=0)
        self.client.force_login(self.direction)
        self.url = reverse("referentiels_ecole")

    def apercu(self, **options):
        valeurs = {"action": "apercu", "annee": self.annee,
                   "autorisations": "garder", "proposee": ""}
        valeurs.update(options)
        return self.client.post(self.url, valeurs)

    def confirmer(self, page, **options):
        valeurs = {"action": "confirmer", "annee": self.annee, "jeton": page.context["jeton"]}
        valeurs.update(options)
        return self.client.post(self.url, valeurs)

    def test_lecture_apercu_et_confirmation_sans_bascule(self):
        avant = {model: list(model.objects.values()) for model in
            (AdoptionReferentiel, Observation, EtatAnnuelObservation, Trace)}
        page = self.client.get(self.url, {"annee": self.annee})
        self.assertContains(page, "Référentiels de l'école")
        self.assertFalse(ChoixEcoleAnnuel.objects.exists())
        page = self.apercu(autorisations="restreindre", versions=[self.b.pk], proposee=self.b.pk)
        self.assertEqual(page.status_code, 200)
        self.assertTrue(page.context["jeton"])
        self.assertContains(page, self.classe.libelle_avec_annee)
        self.assertFalse(ChoixEcoleAnnuel.objects.exists())
        self.assertFalse(VersionSourceEcole.objects.exists())
        # Les choix confirmés viennent de l'aperçu signé, pas des champs ajoutés.
        self.assertRedirects(self.confirmer(page, versions=[self.a.pk], proposee=self.a.pk),
                             f"{self.url}?annee={self.annee}")
        choix = choix_bases(self.ecole, self.annee)
        self.assertEqual([v.pk for v in choix.versions], [self.b.pk])
        self.assertEqual(choix.proposee.pk, self.b.pk)
        for model, donnees in avant.items():
            self.assertEqual(list(model.objects.values()), donnees)
        self.assertEqual(self.confirmer(page).status_code, 400)

    def test_defaut_ecole_distinct_de_restriction_et_retour_a_heritage(self):
        self.confirmer(self.apercu(proposee=self.b.pk))
        choix = choix_bases(self.ecole, self.annee)
        self.assertEqual(len(choix.versions), 2)
        self.assertEqual(choix.proposee.pk, self.b.pk)
        self.confirmer(self.apercu(versions=[self.b.pk]))
        local = ChoixEcoleAnnuel.objects.get()
        self.assertFalse(local.restreindre)
        self.assertFalse(local.versions_autorisees.exists())
        self.assertIsNone(local.version_proposee_id)
        self.assertEqual(choix_bases(self.ecole, self.annee).proposee.pk, self.a.pk)

    def test_aucune_base_explication_et_anciennes_classes_conservees(self):
        page = self.apercu(autorisations="restreindre")
        self.assertContains(page, "Aucune base ne pourra être choisie")
        self.assertEqual(page.context["apercu"]["classes_conservees"][0].classe_id, self.classe.pk)
        self.assertEqual(self.confirmer(page).status_code, 302)
        self.assertFalse(choix_bases(self.ecole, self.annee).versions)
        self.assertTrue(AdoptionReferentiel.objects.filter(classe=self.classe, courante=True).exists())

    def test_refus_defaut_hors_liste_ou_source_non_autorisee(self):
        hors = importer(document("fictive-hors-liste"))[0]
        for options in ({"autorisations": "restreindre", "versions": [self.b.pk]},
                        {"autorisations": "restreindre", "versions": [self.a.pk], "proposee": self.b.pk},
                        {"proposee": hors.pk}, {"autorisations": "restreindre", "versions": [hors.pk]},
                        {"autorisations": "invalide"}):
            with self.subTest(options=options):
                page = self.apercu(**options)
                self.assertEqual(page.status_code, 400)
                self.assertIsNone(page.context["jeton"])
        self.assertFalse(ChoixEcoleAnnuel.objects.exists())

    def test_confirmation_perimee_application_ou_ecole(self):
        page = self.apercu()
        publier_choix_application(annee=self.annee, versions_ids=[self.a.pk, self.b.pk],
                                 proposee_id=self.b.pk, revision_attendue=1)
        self.assertEqual(self.confirmer(page).status_code, 400)
        self.assertFalse(ChoixEcoleAnnuel.objects.exists())
        page = self.apercu()
        self.confirmer(self.apercu(proposee=self.a.pk))
        self.assertEqual(self.confirmer(page).status_code, 400)
        self.assertEqual(ChoixEcoleAnnuel.objects.get().version_proposee_id, self.a.pk)

    def test_apercu_lie_au_compte_a_l_ecole_et_a_l_annee(self):
        page = self.apercu()
        self.assertEqual(self.confirmer(page, jeton="invalide").status_code, 400)
        self.assertEqual(self.confirmer(page, annee="2024-2025").status_code, 400)
        autre_direction = get_user_model().objects.create_user(username="direction-fictive-autre")
        appartenance = AppartenanceEcole.objects.create(ecole=self.ecole, utilisateur=autre_direction)
        ResponsabiliteEcole.objects.create(appartenance=appartenance, type=ResponsabiliteEcole.DIRECTION)
        self.client.force_login(autre_direction)
        self.assertEqual(self.confirmer(page).status_code, 400)
        autre = Ecole.objects.create(nom="École fictive des Lilas")
        appartenance = AppartenanceEcole.objects.create(ecole=autre, utilisateur=self.direction)
        ResponsabiliteEcole.objects.create(appartenance=appartenance, type=ResponsabiliteEcole.DIRECTION)
        self.client.force_login(self.direction)
        session = self.client.session
        session["ecole_id"] = autre.pk
        session.save()
        self.assertEqual(self.confirmer(page).status_code, 400)
        self.assertFalse(ChoixEcoleAnnuel.objects.exists())

    def test_direction_seule_et_annee_invalide(self):
        self.client.force_login(self.enseignant)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.apercu().status_code, 403)
        self.client.force_login(self.direction)
        self.assertContains(self.client.get(reverse("gestion")), "Référentiels de l’école")
        for annee in ("2026", "2026-2028", "abcd-efgh"):
            with self.subTest(annee=annee):
                self.assertEqual(self.client.get(self.url, {"annee": annee}).status_code, 400)
                self.assertEqual(self.apercu(annee=annee).status_code, 400)
        self.assertFalse(ChoixEcoleAnnuel.objects.exists())

    def test_choix_deux_annees_independants(self):
        self.confirmer(self.apercu(proposee=self.b.pk))
        autre_annee = "2024-2025" if self.annee != "2024-2025" else "2023-2024"
        publier_choix_application(annee=autre_annee, versions_ids=[self.a.pk],
                                 proposee_id=self.a.pk, revision_attendue=0)
        page = self.apercu(annee=autre_annee)
        self.assertEqual(self.confirmer(page, annee=autre_annee).status_code, 302)
        self.assertEqual(choix_bases(self.ecole, self.annee).proposee.pk, self.b.pk)
        self.assertEqual(choix_bases(self.ecole, autre_annee).proposee.pk, self.a.pk)

    def test_apercu_expire_sans_enregistrement(self):
        ancienne_date = signing.b62_encode(int(time.time()) - 1900)
        with patch("django.core.signing.TimestampSigner.timestamp", return_value=ancienne_date):
            page = self.apercu()
        self.assertEqual(self.confirmer(page).status_code, 400)
        self.assertFalse(ChoixEcoleAnnuel.objects.exists())
