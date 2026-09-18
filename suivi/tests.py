import hashlib
import os
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    Bilan,
    Classe,
    Competence,
    Domaine,
    Ecole,
    Eleve,
    Observation,
    Scolarite,
    Trace,
)
from .views import _recuperateur_pdf


class Base(TestCase):
    def setUp(self):
        self.ecole = Ecole(nom="Les Tilleuls")
        self.ecole.definir_mots_de_passe("ens-mdp", "dir-mdp")
        self.ecole.save()
        self.classe = Classe.objects.create(ecole=self.ecole, nom="PS-MS")
        self.eleve = Eleve.objects.create(ecole=self.ecole, prenom="Lou")
        self.scolarite = Scolarite.objects.create(
            eleve=self.eleve,
            classe=self.classe,
            annee_scolaire=self.classe.annee_scolaire,
            niveau="PS",
        )
        domaine = Domaine.objects.create(ecole=self.ecole, code="LANG", nom="Langage")
        self.competence = Competence.objects.create(
            domaine=domaine, code="LANG-01", libelle="Je dis mon prénom", niveau="PS"
        )

    def entrer(self, mdp="ens-mdp"):
        return self.client.post(reverse("connexion"), {"mot_de_passe": mdp})

    def creer_trace(self, observation=None, **champs):
        observation = observation or Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
        )
        champs.setdefault("scolarite", self.scolarite)
        return Trace.objects.create(observation=observation, **champs)


class Acces(Base):
    @override_settings(
        ENVIRONNEMENT_ATELIER=True,
        VERSION_APPLICATION="0.3",
    )
    def test_l_atelier_est_signale_y_compris_sur_la_connexion(self):
        r = self.client.get(reverse("connexion"))

        self.assertContains(
            r, "Atelier pédagogique — données factices uniquement"
        )
        self.assertContains(r, "Version 0.3")

    @override_settings(
        ENVIRONNEMENT_ATELIER=False,
        ENVIRONNEMENT_EPHEMERE=True,
    )
    def test_la_demonstration_ephemere_est_signalee_sur_la_connexion(self):
        r = self.client.get(reverse("connexion"))

        self.assertContains(
            r, "Démonstration publique — données fictives uniquement"
        )
        self.assertContains(r, "peut être vu par les autres visiteurs")
        self.assertContains(r, "15 minutes sans aucune visite")

    def test_sans_mot_de_passe_on_est_renvoye_a_la_connexion(self):
        r = self.client.get(reverse("accueil"))
        self.assertRedirects(r, reverse("connexion"))

    def test_mot_de_passe_enseignant(self):
        self.entrer()
        self.assertEqual(self.client.session["role"], "enseignant")

    def test_mot_de_passe_direction(self):
        self.entrer("dir-mdp")
        self.assertEqual(self.client.session["role"], "direction")

    def test_mauvais_mot_de_passe(self):
        self.entrer("nimporte")
        self.assertNotIn("ecole_id", self.client.session)

    def test_la_gestion_est_fermee_aux_enseignants(self):
        self.entrer()
        self.assertEqual(self.client.get(reverse("gestion")).status_code, 403)

    def test_on_revient_sur_la_page_demandee_apres_connexion(self):
        cible = reverse("saisie_eleve", args=[self.eleve.pk])
        self.client.get(cible)
        r = self.entrer()
        self.assertRedirects(r, cible)


class Bascule(Base):
    def setUp(self):
        super().setUp()
        self.entrer()
        self.url = reverse("basculer", args=[self.eleve.pk, self.competence.pk])

    def etat(self):
        obs = Observation.objects.filter(
            eleve=self.eleve, competence=self.competence
        ).first()
        return obs.statut if obs else None

    def test_le_cycle_complet(self):
        self.client.post(self.url)
        self.assertEqual(self.etat(), "reussi")
        self.client.post(self.url)
        self.assertEqual(self.etat(), "en_cours")
        self.client.post(self.url)
        self.assertEqual(self.etat(), "non_debute")
        self.client.post(self.url)
        self.assertEqual(self.etat(), "reussi")

    def test_le_get_est_refuse(self):
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_on_ne_bascule_pas_un_eleve_d_une_autre_ecole(self):
        autre = Ecole(nom="Ailleurs")
        autre.definir_mots_de_passe("a", "b")
        autre.save()
        autre_classe = Classe.objects.create(ecole=autre, nom="GS")
        eleve = Eleve.objects.create(ecole=autre, prenom="Zoé")
        Scolarite.objects.create(
            eleve=eleve,
            classe=autre_classe,
            annee_scolaire=autre_classe.annee_scolaire,
            niveau="GS",
        )
        url = reverse("basculer", args=[eleve.pk, self.competence.pk])
        self.assertEqual(self.client.post(url).status_code, 404)

    def test_le_changement_de_statut_conserve_la_trace(self):
        obs = Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
            statut=Observation.REUSSI,
        )
        trace = self.creer_trace(
            obs,
            commentaire="Une première réussite",
            photo="traces/test.jpg",
        )

        self.client.post(self.url)
        self.client.post(self.url)

        obs.refresh_from_db()
        self.assertEqual(obs.statut, Observation.NON_DEBUTE)
        trace.refresh_from_db()
        self.assertEqual(trace.commentaire, "Une première réussite")
        self.assertEqual(trace.photo.name, "traces/test.jpg")


class Carnet(Base):
    @patch(
        "suivi.views.default_storage.open",
        return_value=BytesIO(b"contenu-photo"),
    )
    def test_le_recuperateur_pdf_lit_un_media_autorise_dans_le_stockage(
        self, ouvrir
    ):
        recuperer = _recuperateur_pdf(["traces/photo école.jpg"])

        resultat = recuperer(
            "petits-pas-media:traces%2Fphoto%20%C3%A9cole.jpg"
        )

        ouvrir.assert_called_once_with("traces/photo école.jpg", "rb")
        self.assertEqual(resultat["file_obj"].read(), b"contenu-photo")
        self.assertEqual(resultat["mime_type"], "image/jpeg")

    def test_le_recuperateur_pdf_refuse_un_media_hors_du_carnet(self):
        recuperer = _recuperateur_pdf([])

        with self.assertRaisesMessage(ValueError, "Média non autorisé"):
            recuperer("petits-pas-media:traces%2Fautre.jpg")

    def test_le_pdf_exige_une_connexion(self):
        r = self.client.get(reverse("carnet_pdf", args=[self.eleve.pk]))

        self.assertRedirects(r, reverse("connexion"))

    def test_la_couverture_identifie_le_carnet(self):
        self.eleve.nom = "Martin"
        self.eleve.save(update_fields=["nom"])
        self.entrer()

        r = self.client.get(reverse("carnet", args=[self.eleve.pk]))

        self.assertContains(r, "Carnet de suivi des apprentissages")
        self.assertContains(r, self.ecole.nom)
        self.assertContains(r, self.classe.nom)
        self.assertContains(r, self.eleve.get_niveau_display())
        self.assertContains(r, self.classe.annee_scolaire)
        self.assertContains(r, "Lou M.")
        self.assertNotContains(r, "Lou Martin")

    def test_le_carnet_montre_par_defaut_les_apprentissages_observes(self):
        self.entrer()
        url = reverse("carnet", args=[self.eleve.pk])
        self.assertNotContains(self.client.get(url), "Je dis mon prénom")

        observation = Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
            statut=Observation.EN_COURS,
        )
        self.assertContains(self.client.get(url), "Je dis mon prénom")

        observation.statut = Observation.REUSSI
        observation.save()
        self.assertContains(self.client.get(url), "Je dis mon prénom")

    def test_le_mode_observes_montre_les_apprentissages_en_cours(self):
        self.entrer()
        Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
            statut=Observation.EN_COURS,
        )

        r = self.client.get(
            reverse("carnet", args=[self.eleve.pk]),
            {"contenu": "observes"},
        )

        self.assertContains(r, "Je dis mon prénom")
        self.assertContains(r, "Je suis en train d'apprendre")
        self.assertContains(r, "En cours d'apprentissage")

    def test_la_mise_en_page_peut_utiliser_une_ou_deux_colonnes(self):
        self.entrer()
        url = reverse("carnet", args=[self.eleve.pk])

        self.assertContains(self.client.get(url), 'class="carnet colonnes-2"')
        self.assertContains(
            self.client.get(url, {"colonnes": "1"}),
            'class="carnet colonnes-1"',
        )
        self.assertContains(
            self.client.get(url, {"colonnes": "inconnu"}),
            'class="carnet colonnes-2"',
        )

    def test_une_reussite_montre_son_commentaire_sans_date_exacte(self):
        self.entrer()
        observation = Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
            statut=Observation.REUSSI,
            date_observation="2026-09-16",
        )
        self.creer_trace(
            observation,
            date_observation="2026-09-16",
            commentaire="Lou a raconté son arrivée à l'école.",
        )

        r = self.client.get(reverse("carnet", args=[self.eleve.pk]))

        self.assertNotContains(r, "Observé le 16 septembre 2026")
        self.assertContains(r, "Lou a raconté son arrivée")
        self.assertContains(r, "école.")

    def test_le_mode_complet_montre_tout(self):
        self.entrer()
        r = self.client.get(
            reverse("carnet", args=[self.eleve.pk]), {"contenu": "tout"}
        )
        self.assertContains(r, "Je dis mon prénom")

    def test_l_ancien_lien_tout_reste_compatible(self):
        self.entrer()
        r = self.client.get(reverse("carnet", args=[self.eleve.pk]), {"tout": "1"})
        self.assertContains(r, "Je dis mon prénom")

    def test_un_mode_inconnu_revient_aux_apprentissages_observes(self):
        self.entrer()
        Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
            statut=Observation.EN_COURS,
        )
        r = self.client.get(
            reverse("carnet", args=[self.eleve.pk]), {"contenu": "inconnu"}
        )
        self.assertContains(r, "Je dis mon prénom")

    def test_le_pdf_est_telechargeable_avec_un_nom_neutre(self):
        self.eleve.nom = "Martin"
        self.eleve.save(update_fields=["nom"])
        Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
            statut=Observation.REUSSI,
        )
        self.entrer()

        r = self.client.get(
            reverse("carnet_pdf", args=[self.eleve.pk]),
            {"contenu": "reussites", "colonnes": "1"},
        )

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertEqual(
            r["Content-Disposition"],
            'attachment; filename="carnet-lou-m.pdf"',
        )
        self.assertIn("no-store", r["Cache-Control"])
        self.assertIn("private", r["Cache-Control"])
        self.assertTrue(r.content.startswith(b"%PDF-"))
        self.assertLess(len(r.content), 1_000_000)

    @patch("suivi.views._generer_pdf", return_value=b"%PDF-factice")
    def test_le_pdf_reutilise_les_filtres_et_ne_devoile_pas_le_nom(
        self, generer_pdf
    ):
        self.eleve.nom = "Martin"
        self.eleve.save(update_fields=["nom"])
        Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
            statut=Observation.EN_COURS,
        )
        self.entrer()

        self.client.get(
            reverse("carnet_pdf", args=[self.eleve.pk]),
            {"contenu": "observes", "colonnes": "1"},
        )

        rendu = generer_pdf.call_args.args[0]
        self.assertIn("Lou M.", rendu)
        self.assertNotIn("Lou Martin", rendu)
        self.assertIn("En cours d'apprentissage", rendu)
        self.assertIn('class="carnet colonnes-1"', rendu)

    @patch("suivi.views._generer_pdf", return_value=b"%PDF-factice")
    def test_le_pdf_lit_les_photos_depuis_le_stockage_prive(self, generer_pdf):
        observation = Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
            statut=Observation.REUSSI,
        )
        self.creer_trace(
            observation,
            photo="traces/photo école.jpg",
        )
        self.entrer()

        self.client.get(reverse("carnet_pdf", args=[self.eleve.pk]))

        rendu, _base_url, _feuille_style, noms_media = generer_pdf.call_args.args
        self.assertIn(
            'src="petits-pas-media:traces%2Fphoto%20%C3%A9cole.jpg"', rendu
        )
        self.assertNotIn("/media/traces/", rendu)
        self.assertEqual(noms_media, ["traces/photo école.jpg"])

    def test_le_pdf_d_un_eleve_d_une_autre_ecole_est_introuvable(self):
        autre = Ecole.objects.create(nom="Ailleurs")
        autre_classe = Classe.objects.create(ecole=autre, nom="MS")
        autre_eleve = Eleve.objects.create(ecole=autre, prenom="Zoé")
        Scolarite.objects.create(
            eleve=autre_eleve,
            classe=autre_classe,
            annee_scolaire=autre_classe.annee_scolaire,
            niveau="MS",
        )
        self.entrer()

        r = self.client.get(reverse("carnet_pdf", args=[autre_eleve.pk]))

        self.assertEqual(r.status_code, 404)


class IndicateursTrace(Base):
    def setUp(self):
        super().setUp()
        self.entrer()

    def page_eleve(self):
        return self.client.get(reverse("saisie_eleve", args=[self.eleve.pk]))

    def test_un_commentaire_est_signale_par_un_crayon(self):
        observation = Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
        )
        self.creer_trace(observation, commentaire="Une remarque")

        r = self.page_eleve()

        self.assertContains(r, 'class="indicateur-commentaire"')
        self.assertNotContains(r, 'class="indicateur-photo"')

    def test_une_photo_est_signalee_independamment_du_commentaire(self):
        observation = Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
        )
        self.creer_trace(
            observation,
            commentaire="Une remarque",
            photo="traces/test.jpg",
        )

        r = self.page_eleve()

        self.assertContains(r, 'class="indicateur-commentaire"')
        self.assertContains(r, 'class="indicateur-photo"')

    def test_les_indicateurs_considerent_toutes_les_traces(self):
        observation = Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
        )
        self.creer_trace(
            observation,
            date_observation="2026-09-01",
            commentaire="Une ancienne remarque",
            photo="traces/ancienne.jpg",
        )
        self.creer_trace(
            observation,
            date_observation="2026-10-01",
        )

        r = self.page_eleve()

        self.assertContains(r, 'class="indicateur-commentaire"')
        self.assertContains(r, 'class="indicateur-photo"')


class HistoriqueTraces(Base):
    def setUp(self):
        super().setUp()
        self.entrer()
        self.url = reverse("trace", args=[self.eleve.pk, self.competence.pk])

    def test_plusieurs_traces_sont_conservees_pour_une_competence(self):
        self.client.post(
            self.url,
            {
                "date_observation": "2026-10-03",
                "commentaire": "Première trace",
                "visible_carnet": "on",
            },
        )
        self.client.post(
            self.url,
            {
                "date_observation": "2027-01-12",
                "commentaire": "Deuxième trace",
                "visible_carnet": "on",
            },
        )

        observation = Observation.objects.get(
            eleve=self.eleve, competence=self.competence
        )
        self.assertEqual(observation.traces.count(), 2)
        page = self.client.get(self.url)
        self.assertContains(page, "Première trace")
        self.assertContains(page, "Deuxième trace")

    def test_modifier_une_trace_necrase_pas_les_autres(self):
        observation = Observation.objects.create(
            eleve=self.eleve, competence=self.competence
        )
        premiere = self.creer_trace(observation, commentaire="Première")
        seconde = self.creer_trace(observation, commentaire="Deuxième")

        page_edition = self.client.get(
            reverse(
                "modifier_trace",
                args=[self.eleve.pk, self.competence.pk, premiere.pk],
            )
        )

        self.assertContains(page_edition, "Première", count=1)
        self.assertContains(page_edition, "Deuxième", count=1)
        self.assertContains(page_edition, 'class="trace-conservee en-edition"')

        self.client.post(
            reverse(
                "modifier_trace",
                args=[self.eleve.pk, self.competence.pk, premiere.pk],
            ),
            {
                "date_observation": "2026-11-01",
                "commentaire": "Première corrigée",
                "visible_carnet": "on",
            },
        )

        premiere.refresh_from_db()
        seconde.refresh_from_db()
        self.assertEqual(premiere.commentaire, "Première corrigée")
        self.assertEqual(seconde.commentaire, "Deuxième")

    def test_une_trace_masquee_reste_conservee_sans_apparaitre_dans_le_carnet(self):
        observation = Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
            statut=Observation.REUSSI,
        )
        self.creer_trace(
            observation,
            commentaire="Pour l'équipe seulement",
            visible_carnet=False,
        )
        self.creer_trace(
            observation,
            commentaire="Pour la famille",
            visible_carnet=True,
        )

        carnet = self.client.get(reverse("carnet", args=[self.eleve.pk]))

        self.assertNotContains(carnet, "Pour l'équipe seulement")
        self.assertContains(carnet, "Pour la famille")

    @patch("suivi.views.default_storage.delete")
    def test_supprimer_une_trace_supprime_aussi_son_media_prive(self, supprimer):
        observation = Observation.objects.create(
            eleve=self.eleve, competence=self.competence
        )
        trace = self.creer_trace(
            observation,
            commentaire="À supprimer",
            photo="traces/a-supprimer.jpg",
        )

        with self.captureOnCommitCallbacks(execute=True):
            reponse = self.client.post(
                reverse(
                    "supprimer_trace",
                    args=[self.eleve.pk, self.competence.pk, trace.pk],
                )
            )

        self.assertRedirects(reponse, self.url)
        self.assertFalse(Trace.objects.filter(pk=trace.pk).exists())
        supprimer.assert_called_once_with("traces/a-supprimer.jpg")
        self.assertTrue(Observation.objects.filter(pk=observation.pk).exists())

    def test_supprimer_une_trace_exige_post(self):
        observation = Observation.objects.create(
            eleve=self.eleve, competence=self.competence
        )
        trace = self.creer_trace(observation)
        url = reverse(
            "supprimer_trace",
            args=[self.eleve.pk, self.competence.pk, trace.pk],
        )

        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertTrue(Trace.objects.filter(pk=trace.pk).exists())

    def test_la_visibilite_d_une_trace_se_bascule_depuis_l_historique(self):
        observation = Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
            statut=Observation.REUSSI,
        )
        trace = self.creer_trace(
            observation,
            commentaire="Une trace à publier",
            visible_carnet=True,
        )
        url = reverse(
            "basculer_visibilite_trace",
            args=[self.eleve.pk, self.competence.pk, trace.pk],
        )

        historique = self.client.get(self.url)
        self.assertContains(historique, "✓ Affichée dans le carnet")

        reponse = self.client.post(url)
        self.assertRedirects(reponse, self.url)
        trace.refresh_from_db()
        self.assertFalse(trace.visible_carnet)
        self.assertNotContains(
            self.client.get(reverse("carnet", args=[self.eleve.pk])),
            "Une trace à publier",
        )
        self.assertContains(self.client.get(self.url), "○ Masquée du carnet")

        self.client.post(url)
        trace.refresh_from_db()
        self.assertTrue(trace.visible_carnet)
        self.assertContains(
            self.client.get(reverse("carnet", args=[self.eleve.pk])),
            "Une trace à publier",
        )

    def test_basculer_la_visibilite_exige_post(self):
        observation = Observation.objects.create(
            eleve=self.eleve, competence=self.competence
        )
        trace = self.creer_trace(observation)
        url = reverse(
            "basculer_visibilite_trace",
            args=[self.eleve.pk, self.competence.pk, trace.pk],
        )

        self.assertEqual(self.client.get(url).status_code, 403)
        trace.refresh_from_db()
        self.assertTrue(trace.visible_carnet)


class Import(Base):
    def test_coller_une_liste_cree_les_eleves(self):
        self.entrer("dir-mdp")
        self.client.post(
            reverse("importer_eleves", args=[self.classe.pk]),
            {"liste": "Camille\nSofiane ; Benali ; MS ; 2021\n\n  Lou  ", "niveau": "PS"},
        )
        noms = set(self.classe.eleves.values_list("prenom", flat=True))
        self.assertEqual(noms, {"Lou", "Camille", "Sofiane"})
        self.assertEqual(self.classe.eleves.get(prenom="Sofiane").niveau, "MS")
        self.assertEqual(
            self.classe.eleves.get(prenom="Sofiane").annee_naissance, 2021
        )
        self.assertEqual(self.classe.eleves.get(prenom="Camille").niveau, "PS")


class ParcoursLongitudinal(Base):
    def test_la_creation_d_une_classe_demande_son_annee(self):
        self.entrer("dir-mdp")

        reponse = self.client.post(
            reverse("creer_classe"),
            {"nom": "MS-GS", "annee_scolaire": "2027-2028"},
        )

        classe = Classe.objects.get(nom="MS-GS")
        self.assertEqual(classe.annee_scolaire, "2027-2028")
        self.assertRedirects(reponse, reverse("importer_eleves", args=[classe.pk]))

    def test_la_rentree_ajoute_une_scolarite_sans_effacer_la_precedente(self):
        classe_suivante = Classe.objects.create(
            ecole=self.ecole,
            nom="MS",
            annee_scolaire="2027-2028",
        )
        self.entrer("dir-mdp")

        self.client.post(
            reverse("parcours_eleve", args=[self.eleve.pk]),
            {
                "action": "scolarite",
                "classe": classe_suivante.pk,
                "niveau": "MS",
            },
        )

        self.assertEqual(self.eleve.scolarites.count(), 2)
        self.assertEqual(
            self.eleve.scolarites.get(annee_scolaire="2027-2028").niveau,
            "MS",
        )
        self.assertTrue(
            self.eleve.scolarites.filter(annee_scolaire="2026-2027").exists()
        )

    def test_un_enseignant_ne_peut_pas_modifier_le_parcours_administratif(self):
        self.entrer()

        reponse = self.client.get(reverse("parcours_eleve", args=[self.eleve.pk]))

        self.assertEqual(reponse.status_code, 403)

    def test_un_eleve_ne_peut_avoir_deux_scolarites_la_meme_annee(self):
        autre_classe = Classe.objects.create(
            ecole=self.ecole,
            nom="Autre classe",
            annee_scolaire=self.classe.annee_scolaire,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Scolarite.objects.create(
                eleve=self.eleve,
                classe=autre_classe,
                annee_scolaire=self.classe.annee_scolaire,
                niveau="PS",
            )

    def test_une_classe_historique_ne_peut_pas_etre_supprimee(self):
        with self.assertRaises(ProtectedError):
            self.classe.delete()

    def test_archiver_masque_l_eleve_sans_supprimer_son_parcours(self):
        self.entrer("dir-mdp")

        self.client.post(reverse("archiver_eleve", args=[self.eleve.pk]))

        self.eleve.refresh_from_db()
        self.assertIsNotNone(self.eleve.archive_le)
        self.assertEqual(Scolarite.objects.filter(eleve=self.eleve).count(), 1)
        self.assertContains(
            self.client.get(reverse("classe_detail", args=[self.classe.pk])),
            "0 enfants",
        )

    def test_un_eleve_archive_peut_etre_reactive(self):
        self.eleve.archive_le = timezone.now()
        self.eleve.save(update_fields=["archive_le"])
        self.entrer("dir-mdp")

        self.client.post(reverse("desarchiver_eleve", args=[self.eleve.pk]))

        self.eleve.refresh_from_db()
        self.assertIsNone(self.eleve.archive_le)


class BilansEtPeriodes(Base):
    def setUp(self):
        super().setUp()
        self.entrer()

    def test_un_bilan_date_est_affiche_dans_le_carnet(self):
        Bilan.objects.create(
            scolarite=self.scolarite,
            date_bilan="2027-01-15",
            texte="Lou avance avec confiance.",
        )

        r = self.client.get(reverse("carnet", args=[self.eleve.pk]))

        self.assertContains(r, "Quelques mots sur mon parcours")
        self.assertContains(r, "Lou avance avec confiance")

    def test_le_regroupement_mensuel_utilise_la_date_reelle(self):
        Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
            date_observation="2026-10-18",
        )

        r = self.client.get(
            reverse("carnet", args=[self.eleve.pk]),
            {"regroupement": "mensuel"},
        )

        self.assertContains(r, "Octobre 2026")

    def test_le_regroupement_par_bilan_utilise_le_premier_bilan_suivant(self):
        Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
            date_observation="2026-10-18",
        )
        Bilan.objects.create(
            scolarite=self.scolarite,
            date_bilan="2027-01-15",
            texte="Premier bilan",
        )

        r = self.client.get(
            reverse("carnet", args=[self.eleve.pk]),
            {"regroupement": "bilan"},
        )

        self.assertContains(r, "Mes acquisitions — janvier 2027")

    def test_deux_bilans_a_la_meme_date_sont_refuses(self):
        Bilan.objects.create(
            scolarite=self.scolarite,
            date_bilan="2027-01-15",
            texte="Premier bilan",
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Bilan.objects.create(
                scolarite=self.scolarite,
                date_bilan="2027-01-15",
                texte="Doublon",
            )


class Referentiel(Base):
    def test_le_rechargement_conserve_les_observations(self):
        from io import StringIO
        from tempfile import NamedTemporaryFile

        from django.core.management import call_command

        Observation.objects.create(eleve=self.eleve, competence=self.competence)
        with NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(
                "domaines:\n"
                "  - code: LANG\n"
                "    nom: Langage\n"
                "    competences:\n"
                "      - { code: LANG-01, niveau: PS, libelle: 'Je dis mon prénom et celui des autres' }\n"
            )
            chemin = f.name
        call_command("charger_referentiel", chemin, ecole=self.ecole.pk, stdout=StringIO())
        self.competence.refresh_from_db()
        self.assertEqual(self.competence.libelle, "Je dis mon prénom et celui des autres")
        self.assertEqual(Observation.objects.count(), 1)


class DiagnosticDeploiement(TestCase):
    @override_settings(
        DEBUG=True,
        SECRET_KEY="dev-seulement-a-changer-avant-toute-mise-en-ligne",
        ALLOWED_HOSTS=["*"],
        CSRF_TRUSTED_ORIGINS=[],
        STORAGES={
            "default": {
                "BACKEND": "django.core.files.storage.FileSystemStorage",
            },
            "staticfiles": {
                "BACKEND": (
                    "django.contrib.staticfiles.storage.StaticFilesStorage"
                ),
            },
        },
    )
    def test_identifie_le_profil_de_demonstration_sans_afficher_la_cle(self):
        sortie = StringIO()
        call_command("diagnostiquer_deploiement", stdout=sortie)
        texte = sortie.getvalue()

        self.assertIn("FileSystemStorage", texte)
        self.assertIn("Mode debug : activé", texte)
        self.assertNotIn(settings.SECRET_KEY, texte)

    @override_settings(
        DEBUG=False,
        SECRET_KEY="une-cle-distincte-et-secrete",
        ALLOWED_HOSTS=["petits-pas.inria.fr"],
        CSRF_TRUSTED_ORIGINS=["https://petits-pas.inria.fr"],
        ENVIRONNEMENT_ATELIER=False,
        ENVIRONNEMENT_EPHEMERE=False,
        VERSION_APPLICATION="",
        SECURE_PROXY_SSL_HEADER=(
            "HTTP_X_FORWARDED_PROTO",
            "https",
        ),
        STORAGES={
            "default": {
                "BACKEND": "storages.backends.s3.S3Storage",
            },
            "staticfiles": {
                "BACKEND": (
                    "django.contrib.staticfiles.storage.StaticFilesStorage"
                ),
            },
        },
    )
    @patch.object(
        settings,
        "DATABASES",
        {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "petits_pas",
            }
        },
    )
    def test_accepte_un_profil_persistant_complet(self):
        sortie = StringIO()

        call_command(
            "diagnostiquer_deploiement",
            "--exiger-persistant",
            stdout=sortie,
        )

        self.assertIn("Profil persistant valide", sortie.getvalue())

    @override_settings(
        DEBUG=False,
        SECRET_KEY="une-cle-distincte-et-secrete",
        ALLOWED_HOSTS=["atelier.petits-pas.inria.fr"],
        CSRF_TRUSTED_ORIGINS=["https://atelier.petits-pas.inria.fr"],
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
        ENVIRONNEMENT_ATELIER=True,
        ENVIRONNEMENT_EPHEMERE=False,
        VERSION_APPLICATION="0.3",
        STORAGES={
            "default": {"BACKEND": "storages.backends.s3.S3Storage"},
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
            },
        },
    )
    @patch.object(
        settings,
        "DATABASES",
        {"default": {"ENGINE": "django.db.backends.postgresql"}},
    )
    def test_accepte_un_atelier_persistant_explicitement_identifie(self):
        sortie = StringIO()

        call_command(
            "diagnostiquer_deploiement",
            "--exiger-atelier",
            stdout=sortie,
        )

        self.assertIn("Profil atelier valide", sortie.getvalue())
        self.assertIn("Version affichée : 0.3", sortie.getvalue())

    @override_settings(ENVIRONNEMENT_ATELIER=False)
    def test_refuse_l_initialisation_d_atelier_non_confirmee(self):
        with self.assertRaisesMessage(
            CommandError, "CARNET_ENVIRONNEMENT_ATELIER"
        ):
            call_command("initialiser_atelier", stdout=StringIO())

    def test_refuse_un_profil_incomplet_quand_le_persistant_est_exige(self):
        with self.assertRaises(CommandError):
            call_command(
                "diagnostiquer_deploiement",
                "--exiger-persistant",
                stdout=StringIO(),
                stderr=StringIO(),
            )


class InitialisationAtelier(TestCase):
    @override_settings(
        ENVIRONNEMENT_ATELIER=True,
        ENVIRONNEMENT_EPHEMERE=False,
    )
    def test_initialise_une_fois_des_donnees_exclusivement_fictives(self):
        variables = {
            "CARNET_ATELIER_MDP_ENSEIGNANT": "enseignant-factice",
            "CARNET_ATELIER_MDP_DIRECTION": "direction-factice",
        }
        with patch.dict(os.environ, variables):
            call_command("initialiser_atelier", stdout=StringIO())

        ecole = Ecole.objects.get(nom="École fictive Petits Pas")
        classe = ecole.classes.get(nom="PS-MS-GS de Nadia")
        nombres = (
            Domaine.objects.count(),
            Competence.objects.count(),
            Eleve.objects.count(),
            Observation.objects.count(),
            Trace.objects.count(),
        )
        self.assertEqual(classe.eleves.count(), 16)
        self.assertGreater(nombres[0], 0)
        self.assertGreater(nombres[1], 0)
        self.assertGreater(nombres[3], 0)
        self.assertGreater(nombres[4], 0)
        self.assertEqual(ecole.verifier("enseignant-factice"), "enseignant")

        sortie = StringIO()
        call_command("initialiser_atelier", stdout=sortie)

        self.assertIn("aucune donnée modifiée", sortie.getvalue())
        self.assertEqual(
            nombres,
            (
                Domaine.objects.count(),
                Competence.objects.count(),
                Eleve.objects.count(),
                Observation.objects.count(),
                Trace.objects.count(),
            ),
        )

    @override_settings(
        ENVIRONNEMENT_ATELIER=True,
        ENVIRONNEMENT_EPHEMERE=False,
    )
    def test_refuse_une_base_non_vide_sans_la_modifier(self):
        Ecole.objects.create(nom="École existante")

        with self.assertRaisesMessage(CommandError, "Aucune donnée"):
            call_command("initialiser_atelier", stdout=StringIO())

        self.assertEqual(
            list(Ecole.objects.values_list("nom", flat=True)),
            ["École existante"],
        )


class VerificationStockage(TestCase):
    def test_ecrit_lit_et_supprime_un_objet(self):
        sortie = StringIO()

        with TemporaryDirectory() as media_root, override_settings(
            MEDIA_ROOT=media_root,
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                },
            },
        ):
            call_command("verifier_stockage_objet", stdout=sortie)
            self.assertEqual(list(Path(media_root).rglob("*.txt")), [])

        self.assertIn(
            "Écriture, lecture, URL et suppression vérifiées",
            sortie.getvalue(),
        )


class Sante(TestCase):
    def test_signale_que_django_et_la_base_sont_disponibles(self):
        reponse = self.client.get(reverse("health"))

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.json(), {"status": "ok"})

    @patch("suivi.views.connection.cursor")
    def test_signale_une_base_indisponible_sans_exposer_l_erreur(
        self, cursor
    ):
        cursor.side_effect = DatabaseError("mot-de-passe-secret")

        reponse = self.client.get(reverse("health"))

        self.assertEqual(reponse.status_code, 503)
        self.assertEqual(reponse.json(), {"status": "unavailable"})
        self.assertNotContains(
            reponse,
            "mot-de-passe-secret",
            status_code=503,
        )

    def test_refuse_une_requete_non_sure(self):
        self.assertEqual(
            self.client.post(reverse("health")).status_code,
            405,
        )


class SauvegardeMedias(TestCase):
    def configuration_stockage(self, repertoire):
        return override_settings(
            MEDIA_ROOT=repertoire,
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                },
            },
        )

    def creer_sauvegarde(self, medias, sauvegardes):
        destination = Path(sauvegardes) / "sauvegarde"
        with self.configuration_stockage(medias):
            default_storage.save(
                "traces/classe/a.txt", ContentFile(b"premier contenu")
            )
            default_storage.save(
                "traces/b.txt", ContentFile(b"deuxieme contenu")
            )
            call_command("sauvegarder_medias", str(destination), stdout=StringIO())
        return destination

    def test_sauvegarde_verification_et_restauration(self):
        with (
            TemporaryDirectory() as medias,
            TemporaryDirectory() as sauvegardes,
            TemporaryDirectory() as restauration,
        ):
            destination = self.creer_sauvegarde(medias, sauvegardes)
            call_command(
                "verifier_sauvegarde_medias",
                str(destination),
                stdout=StringIO(),
            )

            with (
                self.configuration_stockage(restauration),
                patch.dict(
                    os.environ,
                    {"CARNET_AUTORISER_RESTAURATION_MEDIAS": "oui"},
                ),
            ):
                call_command(
                    "restaurer_medias",
                    str(destination),
                    stdout=StringIO(),
                )
                with default_storage.open("traces/classe/a.txt", "rb") as fichier:
                    self.assertEqual(fichier.read(), b"premier contenu")
                with default_storage.open("traces/b.txt", "rb") as fichier:
                    self.assertEqual(fichier.read(), b"deuxieme contenu")

    def test_detecte_une_sauvegarde_corrompue(self):
        with (
            TemporaryDirectory() as medias,
            TemporaryDirectory() as sauvegardes,
        ):
            destination = self.creer_sauvegarde(medias, sauvegardes)
            (destination / "objets/traces/b.txt").write_bytes(b"corrompu")

            with self.assertRaises(CommandError):
                call_command(
                    "verifier_sauvegarde_medias",
                    str(destination),
                    stdout=StringIO(),
                )

    def test_refuse_d_ecraser_un_media_existant(self):
        with (
            TemporaryDirectory() as medias,
            TemporaryDirectory() as sauvegardes,
            TemporaryDirectory() as restauration,
        ):
            destination = self.creer_sauvegarde(medias, sauvegardes)

            with (
                self.configuration_stockage(restauration),
                patch.dict(
                    os.environ,
                    {"CARNET_AUTORISER_RESTAURATION_MEDIAS": "oui"},
                ),
            ):
                default_storage.save(
                    "traces/b.txt", ContentFile(b"a conserver")
                )
                with self.assertRaises(CommandError):
                    call_command(
                        "restaurer_medias",
                        str(destination),
                        stdout=StringIO(),
                    )
                with default_storage.open("traces/b.txt", "rb") as fichier:
                    self.assertEqual(fichier.read(), b"a conserver")

    def test_exige_une_autorisation_explicite_pour_restaurer(self):
        with (
            TemporaryDirectory() as medias,
            TemporaryDirectory() as sauvegardes,
            TemporaryDirectory() as restauration,
        ):
            destination = self.creer_sauvegarde(medias, sauvegardes)

            with (
                self.configuration_stockage(restauration),
                patch.dict(
                    os.environ,
                    {"CARNET_AUTORISER_RESTAURATION_MEDIAS": ""},
                ),
                self.assertRaises(CommandError),
            ):
                call_command(
                    "restaurer_medias",
                    str(destination),
                    stdout=StringIO(),
                )


class PaquetReprise(TestCase):
    HORODATAGES = {
        "started_at": "2026-09-16T10:00:00Z",
        "database_completed_at": "2026-09-16T10:00:01Z",
        "media_completed_at": "2026-09-16T10:00:02Z",
        "completed_at": "2026-09-16T10:00:03Z",
    }

    def creer_paquet(self, racine, mode="online"):
        paquet = Path(racine) / "reprise"
        postgresql = paquet / "postgresql"
        medias = paquet / "medias"
        postgresql.mkdir(parents=True)
        medias.mkdir()

        dump = postgresql / "petits-pas-test.dump"
        dump.write_bytes(b"archive PostgreSQL de test")
        somme = hashlib.sha256(dump.read_bytes()).hexdigest()
        (postgresql / "petits-pas-test.dump.sha256").write_text(
            f"{somme}  {dump.name}\n",
            encoding="utf-8",
        )

        with TemporaryDirectory() as stockage, override_settings(
            MEDIA_ROOT=stockage,
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                },
            },
        ):
            default_storage.save("traces/a.txt", ContentFile(b"media de test"))
            call_command(
                "sauvegarder_medias",
                str(medias / "petits-pas-medias-test"),
                stdout=StringIO(),
            )

        environnement = (
            {"CARNET_ECRITURES_SUSPENDUES": "oui"}
            if mode == "writes-suspended"
            else {}
        )
        with patch.dict(os.environ, environnement):
            call_command(
                "creer_manifeste_reprise",
                str(paquet),
                mode=mode,
                stdout=StringIO(),
                **self.HORODATAGES,
            )
        return paquet

    @patch("suivi.management.commands.verifier_reprise.subprocess.run")
    def test_cree_et_verifie_un_paquet_coordonne(self, executer):
        with TemporaryDirectory() as racine:
            paquet = self.creer_paquet(racine)

            call_command("verifier_reprise", str(paquet), stdout=StringIO())

            executer.assert_called_once()

    def test_detecte_une_archive_postgresql_modifiee(self):
        with TemporaryDirectory() as racine:
            paquet = self.creer_paquet(racine)
            dump = next((paquet / "postgresql").glob("*.dump"))
            dump.write_bytes(b"archive corrompue")

            with self.assertRaises(CommandError):
                call_command("verifier_reprise", str(paquet), stdout=StringIO())

    def test_exige_la_confirmation_des_ecritures_suspendues(self):
        with TemporaryDirectory() as racine:
            paquet = Path(racine) / "reprise"
            paquet.mkdir()
            with (
                patch.dict(
                    os.environ,
                    {"CARNET_ECRITURES_SUSPENDUES": ""},
                ),
                self.assertRaises(CommandError),
            ):
                call_command(
                    "creer_manifeste_reprise",
                    str(paquet),
                    mode="writes-suspended",
                    stdout=StringIO(),
                    **self.HORODATAGES,
                )


class VerificationRepriseRestauree(Base):
    def test_accepte_tous_les_medias_references(self):
        with TemporaryDirectory() as medias, override_settings(
            MEDIA_ROOT=medias,
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                },
            },
        ):
            photo = default_storage.save(
                "traces/photo.txt", ContentFile(b"photo restauree")
            )
            observation = Observation.objects.create(
                eleve=self.eleve,
                competence=self.competence,
            )
            self.creer_trace(
                observation,
                photo=photo,
            )

            sortie = StringIO()
            call_command("verifier_reprise_restauree", stdout=sortie)

        self.assertIn("1 média(s) référencé(s)", sortie.getvalue())

    def test_refuse_un_media_reference_absent(self):
        with TemporaryDirectory() as medias, override_settings(
            MEDIA_ROOT=medias,
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                },
            },
        ):
            observation = Observation.objects.create(
                eleve=self.eleve,
                competence=self.competence,
            )
            self.creer_trace(
                observation,
                photo="traces/absente.jpg",
            )

            with self.assertRaises(CommandError):
                call_command(
                    "verifier_reprise_restauree",
                    stdout=StringIO(),
                )
