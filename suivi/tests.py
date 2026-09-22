import hashlib
import os
from datetime import date
from zipfile import ZipFile
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from comptes.models import (
    AffectationClasse,
    AnomalieGouvernance,
    AppartenanceEcole,
    Invitation,
    ResponsabiliteEcole,
)
from django.core.exceptions import PermissionDenied, ValidationError

from .models import (
    Attendu,
    Bilan,
    Classe,
    Competence,
    Domaine,
    Ecole,
    Eleve,
    FormulationProposee,
    Observation,
    ParametresCarnet,
    Scolarite,
    SousDomaine,
    Trace,
    annee_scolaire_pour,
    bornes_annee_scolaire,
    statut_annee_scolaire,
)
from .views import _recuperateur_pdf
from .services.equipe import accepter_invitation, inviter, terminer_affectation
from .services.pedagogie import modifier_etat


class AnneeScolaireUtilitaires(TestCase):
    def test_le_1er_septembre_ouvre_la_nouvelle_annee_scolaire(self):
        self.assertEqual(
            annee_scolaire_pour(date(2026, 9, 1)), "2026-2027"
        )

    def test_le_31_aout_appartient_encore_a_l_annee_precedente(self):
        self.assertEqual(
            annee_scolaire_pour(date(2027, 8, 31)), "2026-2027"
        )

    def test_bornes_annee_scolaire_va_du_1er_septembre_au_31_aout(self):
        self.assertEqual(
            bornes_annee_scolaire("2026-2027"),
            (date(2026, 9, 1), date(2027, 8, 31)),
        )

    def test_statut_annee_scolaire_situe_par_rapport_a_une_reference(self):
        self.assertEqual(
            statut_annee_scolaire("2026-2027", annee_reference="2026-2027"),
            "courante",
        )
        self.assertEqual(
            statut_annee_scolaire("2027-2028", annee_reference="2026-2027"),
            "future",
        )
        self.assertEqual(
            statut_annee_scolaire("2025-2026", annee_reference="2026-2027"),
            "passee",
        )
        self.assertEqual(
            statut_annee_scolaire("2020-2021", annee_reference="2026-2027"),
            "ancienne",
        )


class Base(TestCase):
    def setUp(self):
        self.ecole = Ecole.objects.create(nom="Les Tilleuls")
        Utilisateur = get_user_model()
        self.enseignant = Utilisateur.objects.create_user(
            username="enseignant-test",
            password="ens-mdp",
        )
        self.direction = Utilisateur.objects.create_user(
            username="direction-test",
            password="dir-mdp",
        )
        self.classe = Classe.objects.create(ecole=self.ecole, nom="PS-MS")
        self.appartenance_enseignant = AppartenanceEcole.objects.create(
            utilisateur=self.enseignant, ecole=self.ecole
        )
        self.appartenance_direction = AppartenanceEcole.objects.create(
            utilisateur=self.direction, ecole=self.ecole
        )
        ResponsabiliteEcole.objects.create(
            appartenance=self.appartenance_direction,
            type=ResponsabiliteEcole.DIRECTION,
        )
        AffectationClasse.objects.create(
            appartenance=self.appartenance_enseignant,
            classe=self.classe,
            type=AffectationClasse.RESPONSABLE,
        )
        self.classe.activer()
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

    def entrer(self, mdp="ens-mdp", nom_utilisateur=None):
        if nom_utilisateur is None:
            nom_utilisateur = (
                self.direction.username if mdp == "dir-mdp" else self.enseignant.username
            )
        return self.client.post(
            reverse("connexion"),
            {"nom_utilisateur": nom_utilisateur, "mot_de_passe": mdp},
        )

    def affecter_enseignant(self, classe, type=AffectationClasse.RESPONSABLE):
        return AffectationClasse.objects.create(
            appartenance=self.appartenance_enseignant,
            classe=classe,
            type=type,
        )

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

    def test_sans_compte_on_est_renvoye_a_la_connexion(self):
        r = self.client.get(reverse("accueil"))
        self.assertRedirects(r, reverse("connexion"))

    def test_compte_enseignant(self):
        self.entrer()
        self.assertEqual(self.client.session["_auth_user_id"], str(self.enseignant.pk))
        self.assertNotIn("role", self.client.session)

    def test_compte_direction(self):
        self.entrer("dir-mdp")
        self.assertEqual(self.client.session["_auth_user_id"], str(self.direction.pk))
        self.assertNotIn("role", self.client.session)

    def test_mauvais_mot_de_passe(self):
        self.entrer("nimporte")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_compte_desactive_refuse(self):
        self.enseignant.is_active = False
        self.enseignant.save(update_fields=["is_active"])

        reponse = self.entrer()

        self.assertEqual(reponse.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(reponse, "Nom d&#x27;utilisateur ou mot de passe incorrect")

    def test_compte_sans_ecole_refuse(self):
        Utilisateur = get_user_model()
        Utilisateur.objects.create_user(
            username="sans-ecole",
            password="secret-test",
        )

        reponse = self.entrer("secret-test", "sans-ecole")

        self.assertEqual(reponse.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_identite_individuelle_est_affichee(self):
        self.enseignant.first_name = "Alice"
        self.enseignant.last_name = "Martin"
        self.enseignant.save(update_fields=["first_name", "last_name"])
        self.entrer()

        self.assertContains(self.client.get(reverse("accueil")), "Alice Martin")

    def test_la_gestion_est_fermee_aux_enseignants(self):
        self.entrer()
        self.assertEqual(self.client.get(reverse("gestion")).status_code, 403)

    def test_l_enseignant_arrive_sur_les_classes_sans_actions_de_direction(self):
        self.entrer()

        accueil = self.client.get(reverse("accueil"))

        self.assertContains(accueil, "Les classes")
        self.assertContains(
            accueil, reverse("classe_detail", args=[self.classe.pk])
        )
        self.assertNotContains(accueil, "Créer une classe")
        self.assertNotContains(accueil, "Paramétrer le carnet")
        self.assertEqual(
            self.client.get(
                reverse("classe_detail", args=[self.classe.pk])
            ).status_code,
            200,
        )

    def test_la_direction_dispose_d_un_ecran_de_gestion_fonctionnel(self):
        self.entrer("dir-mdp")

        gestion = self.client.get(reverse("gestion"))

        self.assertContains(gestion, "Gérer l'école")
        self.assertContains(gestion, "Créer une classe")
        self.assertContains(gestion, "Paramétrer le carnet")
        self.assertContains(
            gestion, reverse("importer_eleves", args=[self.classe.pk])
        )

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
        autre = Ecole.objects.create(nom="Ailleurs")
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


class EditionClasse(Base):
    def setUp(self):
        super().setUp()
        self.autre_eleve = Eleve.objects.create(
            ecole=self.ecole, prenom="Malo", nom="Martin"
        )
        Scolarite.objects.create(
            eleve=self.autre_eleve,
            classe=self.classe,
            annee_scolaire=self.classe.annee_scolaire,
            niveau="PS",
        )
        self.entrer()
        self.url = reverse("preparer_edition", args=[self.classe.pk])

    def test_la_page_permet_de_selectionner_la_classe_et_les_options(self):
        reponse = self.client.get(self.url)

        self.assertContains(reponse, "Sélectionner toute la classe")
        self.assertContains(reponse, self.eleve.nom_court)
        self.assertContains(reponse, self.autre_eleve.nom_court)
        self.assertContains(reponse, "Regrouper les acquisitions")

    @patch("suivi.views._generer_pdf", return_value=b"%PDF-factice")
    def test_une_selection_produit_un_pdf_par_eleve_dans_un_zip(self, generer):
        reponse = self.client.post(
            self.url,
            {
                "eleves": [self.eleve.pk, self.autre_eleve.pk],
                "contenu": "reussites",
                "regroupement": "mensuel",
                "colonnes": "1",
                "bilans": "on",
            },
        )

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse["Content-Type"], "application/zip")
        self.assertIn("no-store", reponse["Cache-Control"])
        with ZipFile(BytesIO(reponse.content)) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {"carnet-lou.pdf", "carnet-malo-m.pdf"},
            )
            self.assertTrue(
                all(archive.read(nom) == b"%PDF-factice" for nom in archive.namelist())
            )
        self.assertEqual(generer.call_count, 2)
        for appel in generer.call_args_list:
            html = appel.args[0]
            self.assertIn('class="carnet colonnes-1"', html)

    @patch("suivi.views._generer_pdf", return_value=b"%PDF-factice")
    def test_un_eleve_hors_de_la_classe_est_ignore(self, generer):
        autre_classe = Classe.objects.create(
            ecole=self.ecole,
            nom="GS",
            annee_scolaire=self.classe.annee_scolaire,
        )
        hors_classe = Eleve.objects.create(ecole=self.ecole, prenom="Zoé")
        Scolarite.objects.create(
            eleve=hors_classe,
            classe=autre_classe,
            annee_scolaire=autre_classe.annee_scolaire,
            niveau="GS",
        )

        reponse = self.client.post(
            self.url,
            {
                "eleves": [self.eleve.pk, hors_classe.pk],
                "contenu": "observes",
                "regroupement": "aucun",
                "colonnes": "2",
            },
        )

        with ZipFile(BytesIO(reponse.content)) as archive:
            self.assertEqual(archive.namelist(), ["carnet-lou.pdf"])
        self.assertEqual(generer.call_count, 1)

    @patch("suivi.views._generer_pdf")
    def test_une_selection_vide_ne_genere_rien(self, generer):
        reponse = self.client.post(self.url, {})

        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "Sélectionnez au moins un enfant")
        generer.assert_not_called()


class GrilleCompetence(Base):
    def setUp(self):
        super().setUp()
        self.en_cours = Eleve.objects.create(ecole=self.ecole, prenom="Malo")
        self.reussi = Eleve.objects.create(ecole=self.ecole, prenom="Inès")
        for eleve in (self.en_cours, self.reussi):
            Scolarite.objects.create(
                eleve=eleve,
                classe=self.classe,
                annee_scolaire=self.classe.annee_scolaire,
                niveau="PS",
            )
        Observation.objects.create(
            eleve=self.en_cours,
            competence=self.competence,
            statut=Observation.EN_COURS,
        )
        Observation.objects.create(
            eleve=self.reussi,
            competence=self.competence,
            statut=Observation.REUSSI,
        )
        self.entrer()
        self.url = reverse(
            "grille_competence", args=[self.classe.pk, self.competence.pk]
        )

    def test_la_grille_repartit_tous_les_eleves_selon_leur_etat(self):
        reponse = self.client.get(self.url)

        self.assertContains(reponse, self.eleve.prenom)
        self.assertContains(reponse, self.en_cours.prenom)
        self.assertContains(reponse, self.reussi.prenom)
        self.assertContains(reponse, "<strong>1</strong> à observer", html=True)
        self.assertContains(reponse, "<strong>1</strong> en cours", html=True)
        self.assertContains(reponse, "<strong>1</strong> réussite", html=True)
        self.assertContains(reponse, "document interne à l'équipe pédagogique")

    @patch("suivi.views._generer_pdf", return_value=b"%PDF-grille")
    def test_la_grille_est_exportable_en_pdf(self, generer):
        reponse = self.client.get(
            reverse(
                "grille_competence_pdf",
                args=[self.classe.pk, self.competence.pk],
            )
        )

        self.assertEqual(reponse["Content-Type"], "application/pdf")
        self.assertEqual(reponse.content, b"%PDF-grille")
        self.assertIn("no-store", reponse["Cache-Control"])
        self.assertIn("grille-ps-ms-lang-01.pdf", reponse["Content-Disposition"])
        html = generer.call_args.args[0]
        self.assertIn("Malo", html)
        self.assertIn("Inès", html)

    def test_une_competence_d_une_autre_ecole_est_introuvable(self):
        autre = Ecole.objects.create(nom="Ailleurs")
        autre_domaine = Domaine.objects.create(
            ecole=autre, code="AUTRE", nom="Autre domaine"
        )
        autre_competence = Competence.objects.create(
            domaine=autre_domaine,
            code="AUTRE-01",
            libelle="Autre compétence",
        )

        reponse = self.client.get(
            reverse(
                "grille_competence",
                args=[self.classe.pk, autre_competence.pk],
            )
        )

        self.assertEqual(reponse.status_code, 404)


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

    def test_une_formulation_proposee_est_personnalisee_et_reste_modifiable(self):
        FormulationProposee.objects.create(
            competence=self.competence,
            code="LANG-01-F01",
            texte="{prenom} sait raconter un événement vécu.",
        )

        page = self.client.get(self.url)

        self.assertContains(page, "Lou sait raconter un événement vécu.")
        self.client.post(
            self.url,
            {
                "date_observation": "2026-10-03",
                "commentaire": "Lou raconte maintenant avec beaucoup de précision.",
                "visible_carnet": "on",
            },
        )
        self.assertEqual(
            Trace.objects.get().commentaire,
            "Lou raconte maintenant avec beaucoup de précision.",
        )

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
    def test_retirer_une_trace_conserve_son_media_pour_restauration(self, supprimer):
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
        trace.refresh_from_db()
        self.assertIsNotNone(trace.supprime_le)
        self.assertEqual(trace.photo.name, "traces/a-supprimer.jpg")
        supprimer.assert_not_called()
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


class ClasseStatutAnnee(Base):
    def test_le_statut_annee_d_une_classe_suit_statut_annee_scolaire(self):
        classe_future = Classe.objects.create(
            ecole=self.ecole, nom="Rentrée", annee_scolaire="2027-2028"
        )
        classe_ancienne = Classe.objects.create(
            ecole=self.ecole, nom="Ancienne", annee_scolaire="2020-2021"
        )

        self.assertEqual(self.classe.statut_annee, "courante")
        self.assertEqual(classe_future.statut_annee, "future")
        self.assertEqual(classe_ancienne.statut_annee, "ancienne")


class TableauDeClasse(Base):
    def setUp(self):
        super().setUp()
        self.entrer()
        domaine = self.competence.domaine
        self.competence_ms = Competence.objects.create(
            domaine=domaine, code="LANG-02", libelle="Je raconte une histoire",
            niveau="MS",
        )
        self.eleve_ms = Eleve.objects.create(ecole=self.ecole, prenom="Nino")
        self.scolarite_ms = Scolarite.objects.create(
            eleve=self.eleve_ms,
            classe=self.classe,
            annee_scolaire=self.classe.annee_scolaire,
            niveau="MS",
        )
        Observation.objects.create(
            eleve=self.eleve, competence=self.competence, statut="reussi"
        )
        Observation.objects.create(
            eleve=self.eleve_ms, competence=self.competence_ms, statut="reussi"
        )
        Bilan.objects.create(
            scolarite=self.scolarite_ms, date_bilan="2027-01-10", texte="Bon départ"
        )

    def test_annee_de_classe_compte_les_competences_du_niveau_propre(self):
        r = self.client.get(reverse("classe_detail", args=[self.classe.pk]))

        self.assertContains(r, "1/1 réussite")
        self.assertContains(r, "0 bilan")
        self.assertContains(r, "1 bilan")

    def test_tout_le_cycle_compte_toutes_les_competences(self):
        r = self.client.get(
            reverse("classe_detail", args=[self.classe.pk]), {"niveaux": "tous"}
        )

        self.assertContains(r, "1/2 réussite")

    def test_un_niveau_explicite_ne_compte_que_ses_competences(self):
        r = self.client.get(
            reverse("classe_detail", args=[self.classe.pk]), {"niveaux": "MS"}
        )

        self.assertContains(r, "0/1 réussite")
        self.assertContains(r, "1/1 réussite")

    def test_un_filtre_inconnu_retombe_sur_annee_de_classe(self):
        r = self.client.get(
            reverse("classe_detail", args=[self.classe.pk]), {"niveaux": "XX"}
        )

        self.assertContains(r, 'aria-current="true">Année de classe')

    def test_annee_de_classe_ignore_un_bilan_date_hors_de_l_annee_de_la_classe(self):
        Bilan.objects.create(
            scolarite=self.scolarite_ms, date_bilan="2025-06-01", texte="Bilan égaré"
        )

        r = self.client.get(reverse("classe_detail", args=[self.classe.pk]))

        self.assertContains(r, "1 bilan")
        self.assertNotContains(r, "2 bilan")

    def test_tout_le_cycle_compte_tous_les_bilans_de_l_eleve(self):
        classe_precedente = Classe.objects.create(
            ecole=self.ecole, nom="Autre", annee_scolaire="2025-2026"
        )
        scolarite_ancienne = Scolarite.objects.create(
            eleve=self.eleve_ms,
            classe=classe_precedente,
            annee_scolaire="2025-2026",
            niveau="PS",
        )
        Bilan.objects.create(
            scolarite=scolarite_ancienne, date_bilan="2026-03-01", texte="Bilan PS"
        )

        r = self.client.get(
            reverse("classe_detail", args=[self.classe.pk]), {"niveaux": "tous"}
        )

        self.assertContains(r, "2 bilan")

    def test_un_niveau_explicite_compte_les_bilans_de_toutes_les_scolarites_a_ce_niveau(
        self,
    ):
        classe_precedente = Classe.objects.create(
            ecole=self.ecole, nom="PS d'avant", annee_scolaire="2025-2026"
        )
        scolarite_ps_ancienne = Scolarite.objects.create(
            eleve=self.eleve_ms,
            classe=classe_precedente,
            annee_scolaire="2025-2026",
            niveau="PS",
        )
        Bilan.objects.create(
            scolarite=scolarite_ps_ancienne, date_bilan="2026-03-01", texte="Bilan PS"
        )

        r = self.client.get(
            reverse("classe_detail", args=[self.classe.pk]), {"niveaux": "PS"}
        )

        self.assertContains(r, "1 bilan")


class PageDesClasses(Base):
    def setUp(self):
        super().setUp()
        self.entrer()

    def test_le_groupe_de_l_annee_courante_est_mis_en_valeur(self):
        r = self.client.get(reverse("accueil"))

        self.assertContains(r, "groupe-annee-courante")
        self.assertContains(r, self.classe.annee_scolaire)

    def test_une_classe_future_est_signalee_et_groupee_avant_la_courante(self):
        classe = Classe.objects.create(
            ecole=self.ecole, nom="Rentrée", annee_scolaire="2027-2028"
        )
        self.affecter_enseignant(classe)

        r = self.client.get(reverse("accueil"))

        self.assertContains(r, "Rentrée")
        self.assertContains(r, "à venir")
        self.assertLess(
            r.content.find(b"2027-2028"), r.content.find(b"2026-2027")
        )

    def test_par_defaut_les_annees_passees_sont_masquees(self):
        classe = Classe.objects.create(
            ecole=self.ecole, nom="Ancienne", annee_scolaire="2024-2025"
        )
        self.affecter_enseignant(classe)

        r = self.client.get(reverse("accueil"))

        self.assertNotContains(r, "Ancienne")
        self.assertContains(r, "Voir aussi les années précédentes")

    def test_le_lien_affiche_aussi_les_annees_passees(self):
        classe = Classe.objects.create(
            ecole=self.ecole, nom="Ancienne", annee_scolaire="2024-2025"
        )
        self.affecter_enseignant(classe)

        r = self.client.get(reverse("accueil"), {"toutes": "1"})

        self.assertContains(r, "Ancienne")
        self.assertContains(r, "années antérieures")
        self.assertContains(r, "Revenir aux classes à partir de l'année en cours")

    def test_une_annee_precedente_immediate_est_distinguee_des_plus_anciennes(self):
        classe_1 = Classe.objects.create(
            ecole=self.ecole, nom="Année-1", annee_scolaire="2025-2026"
        )
        classe_3 = Classe.objects.create(
            ecole=self.ecole, nom="Année-3", annee_scolaire="2023-2024"
        )
        self.affecter_enseignant(classe_1)
        self.affecter_enseignant(classe_3)

        r = self.client.get(reverse("accueil"), {"toutes": "1"})

        self.assertContains(r, "année précédente")
        self.assertContains(r, "années antérieures")


class GestionClassesGroupees(Base):
    def setUp(self):
        super().setUp()
        self.entrer("dir-mdp")

    def test_les_classes_de_gestion_sont_aussi_groupees_par_annee(self):
        r = self.client.get(reverse("gestion"))

        self.assertContains(r, "groupe-annee-courante")
        self.assertContains(
            r, reverse("importer_eleves", args=[self.classe.pk])
        )
        self.assertContains(r, "ajouter des enfants")

    def test_les_annees_passees_sont_masquees_par_defaut_dans_la_gestion(self):
        Classe.objects.create(
            ecole=self.ecole, nom="Ancienne", annee_scolaire="2024-2025"
        )

        r = self.client.get(reverse("gestion"))

        self.assertNotContains(r, "Ancienne")
        self.assertContains(r, "Voir aussi les années précédentes")

        r = self.client.get(reverse("gestion"), {"toutes": "1"})

        self.assertContains(r, "Ancienne")
        self.assertContains(r, "années antérieures")

    def test_la_direction_active_une_classe_apres_attribution_d_un_responsable(self):
        classe = Classe.objects.create(
            ecole=self.ecole,
            nom="MS-GS",
            annee_scolaire="2027-2028",
        )
        r = self.client.get(reverse("gestion"))
        self.assertContains(r, "Attribuez d’abord un responsable")
        self.assertNotContains(r, reverse("activer_classe", args=[classe.pk]))

        AffectationClasse.objects.create(
            appartenance=self.appartenance_enseignant,
            classe=classe,
            type=AffectationClasse.RESPONSABLE,
        )
        r = self.client.get(reverse("gestion"))
        self.assertContains(r, reverse("activer_classe", args=[classe.pk]))

        r = self.client.post(
            reverse("activer_classe", args=[classe.pk]), follow=True
        )
        classe.refresh_from_db()
        self.assertEqual(classe.etat, Classe.ACTIVE)
        self.assertContains(r, "est maintenant active")

    def test_activer_une_classe_exige_post_et_un_responsable(self):
        classe = Classe.objects.create(ecole=self.ecole, nom="MS-GS")
        url = reverse("activer_classe", args=[classe.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        r = self.client.post(url, follow=True)
        classe.refresh_from_db()
        self.assertEqual(classe.etat, Classe.PREPARATION)
        self.assertContains(r, "doit avoir un responsable actif")


class CompositionClasse(Base):
    def setUp(self):
        super().setUp()
        self.entrer("dir-mdp")
        self.url = reverse("importer_eleves", args=[self.classe.pk])

    def test_la_composition_actuelle_est_affichee_avec_ses_actions(self):
        r = self.client.get(self.url)

        self.assertContains(r, "Composition actuelle de la classe")
        self.assertContains(r, "Lou")
        self.assertContains(r, "Modifier le niveau")
        self.assertContains(r, "Retirer de la classe")
        self.assertContains(r, "Retirer et archiver")

    def test_modifier_le_niveau_d_un_eleve_deja_dans_la_classe(self):
        self.client.post(
            self.url,
            {"action": "affecter_existant", "eleve": self.eleve.pk, "niveau": "GS"},
        )

        self.scolarite.refresh_from_db()
        self.assertEqual(self.scolarite.niveau, "GS")
        self.assertEqual(self.scolarite.classe, self.classe)

    def test_retirer_supprime_la_scolarite_et_libere_l_eleve(self):
        self.client.post(self.url, {"action": "retirer", "eleve": self.eleve.pk})

        self.assertFalse(
            self.eleve.scolarites.filter(annee_scolaire="2026-2027").exists()
        )
        self.assertContains(self.client.get(self.url), "sans classe en 2026-2027")

    def test_retirer_est_refuse_si_des_bilans_existent(self):
        Bilan.objects.create(
            scolarite=self.scolarite, date_bilan="2027-01-10", texte="Un bilan"
        )

        self.client.post(self.url, {"action": "retirer", "eleve": self.eleve.pk})

        self.assertTrue(
            self.eleve.scolarites.filter(annee_scolaire="2026-2027").exists()
        )

    def test_retirer_est_refuse_si_des_traces_existent(self):
        observation = Observation.objects.create(
            eleve=self.eleve, competence=self.competence, statut="reussi"
        )
        Trace.objects.create(observation=observation, scolarite=self.scolarite)

        self.client.post(self.url, {"action": "retirer", "eleve": self.eleve.pk})

        self.assertTrue(
            self.eleve.scolarites.filter(annee_scolaire="2026-2027").exists()
        )

    def test_retirer_et_archiver_conserve_la_scolarite(self):
        self.client.post(
            self.url, {"action": "retirer_et_archiver", "eleve": self.eleve.pk}
        )

        self.eleve.refresh_from_db()
        self.assertIsNotNone(self.eleve.archive_le)
        self.assertTrue(
            self.eleve.scolarites.filter(annee_scolaire="2026-2027").exists()
        )

    def test_deplacer_change_la_classe_de_la_scolarite(self):
        autre_classe = Classe.objects.create(
            ecole=self.ecole, nom="Autre", annee_scolaire=self.classe.annee_scolaire
        )

        self.client.post(
            self.url,
            {
                "action": "deplacer",
                "eleve": self.eleve.pk,
                "classe_destination": autre_classe.pk,
            },
        )

        self.scolarite.refresh_from_db()
        self.assertEqual(self.scolarite.classe, autre_classe)

    def test_le_niveau_est_pre_positionne_sur_le_niveau_suivant(self):
        eleve = Eleve.objects.create(ecole=self.ecole, prenom="Nino")
        classe_precedente = Classe.objects.create(
            ecole=self.ecole, nom="MS d'avant", annee_scolaire="2025-2026"
        )
        Scolarite.objects.create(
            eleve=eleve,
            classe=classe_precedente,
            annee_scolaire="2025-2026",
            niveau="MS",
        )
        nouvelle_classe = Classe.objects.create(
            ecole=self.ecole, nom="GS", annee_scolaire="2026-2027"
        )

        r = self.client.get(reverse("importer_eleves", args=[nouvelle_classe.pk]))

        self.assertContains(r, 'value="GS" selected>GS')

    def test_pas_de_pre_positionnement_sans_scolarite_l_annee_precedente(self):
        Eleve.objects.create(ecole=self.ecole, prenom="Sami")
        nouvelle_classe = Classe.objects.create(
            ecole=self.ecole, nom="GS", annee_scolaire="2026-2027"
        )

        r = self.client.get(reverse("importer_eleves", args=[nouvelle_classe.pk]))

        self.assertContains(r, 'value="" selected>Niveau par')

    def test_pas_de_niveau_suivant_apres_la_gs(self):
        eleve = Eleve.objects.create(ecole=self.ecole, prenom="Elio")
        classe_precedente = Classe.objects.create(
            ecole=self.ecole, nom="GS d'avant", annee_scolaire="2025-2026"
        )
        Scolarite.objects.create(
            eleve=eleve,
            classe=classe_precedente,
            annee_scolaire="2025-2026",
            niveau="GS",
        )
        nouvelle_classe = Classe.objects.create(
            ecole=self.ecole, nom="Autre", annee_scolaire="2026-2027"
        )

        r = self.client.get(reverse("importer_eleves", args=[nouvelle_classe.pk]))

        self.assertContains(r, 'value="" selected>Niveau par')

    def test_un_niveau_absent_retombe_sur_ps(self):
        eleve = Eleve.objects.create(ecole=self.ecole, prenom="Malo")

        self.client.post(
            self.url, {"action": "affecter_existant", "eleve": eleve.pk, "niveau": ""}
        )

        self.assertEqual(
            eleve.scolarites.get(annee_scolaire="2026-2027").niveau, "PS"
        )

    def test_un_niveau_absent_retombe_sur_le_niveau_par_defaut_de_la_page(self):
        eleve = Eleve.objects.create(ecole=self.ecole, prenom="Malo")

        self.client.post(
            self.url,
            {
                "action": "affecter_existant",
                "eleve": eleve.pk,
                "niveau": "",
                "niveau_defaut": "MS",
            },
        )

        self.assertEqual(
            eleve.scolarites.get(annee_scolaire="2026-2027").niveau, "MS"
        )

    def test_le_reglage_niveau_par_defaut_pre_selectionne_la_page(self):
        r = self.client.get(self.url, {"niveau_defaut": "GS"})

        self.assertContains(r, 'value="GS" selected>Grande section')

    def test_le_nom_de_l_eleve_de_la_composition_mene_a_son_parcours(self):
        r = self.client.get(self.url)

        self.assertContains(
            r,
            f'href="{reverse("parcours_eleve", args=[self.eleve.pk])}?retour={self.classe.pk}"',
        )

    def test_la_composition_a_son_propre_titre_avec_date_de_naissance(self):
        self.eleve.annee_naissance = 2021
        self.eleve.save(update_fields=["annee_naissance"])

        r = self.client.get(self.url)

        self.assertContains(r, f"<h1>Composition de {self.classe.nom}</h1>")
        self.assertContains(r, "Né(e) en 2021")

    def test_le_parcours_ramene_vers_la_classe_d_origine(self):
        r = self.client.get(
            reverse("parcours_eleve", args=[self.eleve.pk]), {"retour": self.classe.pk}
        )

        self.assertContains(
            r, f'href="{reverse("importer_eleves", args=[self.classe.pk])}"'
        )
        self.assertContains(r, self.classe.nom)


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

    def test_un_eleve_existant_sans_classe_cette_annee_peut_etre_affecte(self):
        eleve = Eleve.objects.create(
            ecole=self.ecole, prenom="Malo", nom="Martin", annee_naissance=2021
        )
        self.entrer("dir-mdp")
        url = reverse("importer_eleves", args=[self.classe.pk])

        page = self.client.get(url)
        self.assertContains(page, "Malo M.")
        self.assertContains(page, "sans classe en 2026-2027")

        self.client.post(
            url,
            {
                "action": "affecter_existant",
                "eleve": eleve.pk,
                "niveau": "MS",
            },
        )

        self.assertEqual(Eleve.objects.filter(prenom="Malo").count(), 1)
        scolarite = eleve.scolarites.get(annee_scolaire="2026-2027")
        self.assertEqual(scolarite.classe, self.classe)
        self.assertEqual(scolarite.niveau, "MS")

    def test_le_deplacement_depuis_une_autre_classe_est_explicite(self):
        autre_classe = Classe.objects.create(
            ecole=self.ecole,
            nom="Autre PS",
            annee_scolaire=self.classe.annee_scolaire,
        )
        eleve = Eleve.objects.create(ecole=self.ecole, prenom="Inès")
        scolarite = Scolarite.objects.create(
            eleve=eleve,
            classe=autre_classe,
            annee_scolaire=autre_classe.annee_scolaire,
            niveau="PS",
        )
        self.entrer("dir-mdp")
        url = reverse("importer_eleves", args=[self.classe.pk])

        self.client.post(
            url,
            {
                "action": "affecter_existant",
                "eleve": eleve.pk,
                "niveau": "MS",
            },
        )
        scolarite.refresh_from_db()
        self.assertEqual(scolarite.classe, autre_classe)

        self.client.post(
            url,
            {
                "action": "affecter_existant",
                "eleve": eleve.pk,
                "niveau": "MS",
                "confirmer_deplacement": "on",
            },
        )
        scolarite.refresh_from_db()
        self.assertEqual(scolarite.classe, self.classe)
        self.assertEqual(scolarite.niveau, "MS")
        self.assertEqual(eleve.scolarites.count(), 1)

    def test_un_eleve_archive_est_reactive_explicitement(self):
        eleve = Eleve.objects.create(
            ecole=self.ecole,
            prenom="Sami",
            archive_le=timezone.now(),
        )
        self.entrer("dir-mdp")
        url = reverse("importer_eleves", args=[self.classe.pk])

        self.assertContains(self.client.get(url), "Réactiver et ajouter")
        self.client.post(
            url,
            {
                "action": "affecter_existant",
                "eleve": eleve.pk,
                "niveau": "GS",
                "reactiver": "on",
            },
        )

        eleve.refresh_from_db()
        self.assertIsNone(eleve.archive_le)
        self.assertTrue(
            eleve.scolarites.filter(classe=self.classe, niveau="GS").exists()
        )

    def test_un_eleve_d_une_autre_ecole_ne_peut_pas_etre_affecte(self):
        autre = Ecole.objects.create(nom="Ailleurs")
        eleve = Eleve.objects.create(ecole=autre, prenom="Zoé")
        self.entrer("dir-mdp")

        reponse = self.client.post(
            reverse("importer_eleves", args=[self.classe.pk]),
            {
                "action": "affecter_existant",
                "eleve": eleve.pk,
                "niveau": "PS",
            },
        )

        self.assertEqual(reponse.status_code, 404)
        self.assertFalse(eleve.scolarites.exists())


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

    def test_une_annee_invalide_conserve_le_nom_deja_saisi(self):
        self.entrer("dir-mdp")

        reponse = self.client.post(
            reverse("creer_classe"),
            {"nom": "MS-GS", "annee_scolaire": "annee-bidon"},
        )

        self.assertContains(reponse, 'value="MS-GS"')
        self.assertContains(reponse, 'value="annee-bidon"')
        self.assertFalse(Classe.objects.filter(nom="MS-GS").exists())

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

    def test_un_responsable_peut_corriger_identite_sans_voir_le_passe(self):
        self.entrer()

        reponse = self.client.get(reverse("parcours_eleve", args=[self.eleve.pk]))

        self.assertEqual(reponse.status_code, 200)
        self.assertNotContains(reponse, "Scolarités conservées")
        self.assertNotContains(reponse, "Préparer une année scolaire")

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

    def test_desarchiver_indique_la_classe_de_reaffectation(self):
        self.eleve.archive_le = timezone.now()
        self.eleve.save(update_fields=["archive_le"])
        self.entrer("dir-mdp")

        r = self.client.post(
            reverse("desarchiver_eleve", args=[self.eleve.pk]), follow=True
        )

        self.assertContains(r, str(self.classe))

    def test_un_eleve_peut_etre_reactive_depuis_son_parcours(self):
        self.eleve.archive_le = timezone.now()
        self.eleve.save(update_fields=["archive_le"])
        self.entrer("dir-mdp")
        url = reverse("parcours_eleve", args=[self.eleve.pk])

        self.assertContains(self.client.get(url), "Réactiver cet élève")

        r = self.client.post(url, {"action": "reactiver"}, follow=True)

        self.eleve.refresh_from_db()
        self.assertIsNone(self.eleve.archive_le)
        self.assertContains(r, str(self.classe))

    def test_un_eleve_reactive_sans_scolarite_courante_le_signale(self):
        eleve = Eleve.objects.create(
            ecole=self.ecole, prenom="Sami", archive_le=timezone.now()
        )
        self.entrer("dir-mdp")

        r = self.client.post(
            reverse("parcours_eleve", args=[eleve.pk]),
            {"action": "reactiver"},
            follow=True,
        )

        self.assertContains(r, "encore de scolarité")


class AnnuaireEleves(Base):
    def setUp(self):
        super().setUp()
        self.entrer("dir-mdp")
        self.classe_suivante = Classe.objects.create(
            ecole=self.ecole, nom="MS-GS", annee_scolaire="2027-2028"
        )
        self.eleve_archive = Eleve.objects.create(
            ecole=self.ecole, prenom="Malo", archive_le=timezone.now()
        )
        self.eleve_sans_classe = Eleve.objects.create(
            ecole=self.ecole, prenom="Zoé"
        )

    def test_la_gestion_est_fermee_aux_enseignants(self):
        self.client.get(reverse("deconnexion"))
        self.entrer()

        self.assertEqual(
            self.client.get(reverse("annuaire_eleves")).status_code, 403
        )

    def test_par_defaut_seuls_les_eleves_actifs_de_l_annee_recente_sont_montres(self):
        r = self.client.get(reverse("annuaire_eleves"))

        self.assertContains(r, "Lou")
        self.assertContains(r, "PS-MS")
        self.assertNotContains(r, "Malo")
        self.assertContains(r, "sans scolarité en 2026-2027")

    def test_le_filtre_archives_montre_les_eleves_archives(self):
        r = self.client.get(reverse("annuaire_eleves"), {"etat": "archives"})

        self.assertContains(r, "Malo")
        self.assertContains(r, "archivé")
        self.assertNotContains(r, "Lou")

    def test_le_filtre_niveau_exclut_les_eleves_d_un_autre_niveau(self):
        r = self.client.get(
            reverse("annuaire_eleves"),
            {"annee": self.classe.annee_scolaire, "niveau": "MS"},
        )

        self.assertNotContains(r, "Lou")

    def test_le_filtre_par_annee_montre_la_scolarite_de_cette_annee(self):
        r = self.client.get(
            reverse("annuaire_eleves"), {"annee": self.classe.annee_scolaire}
        )

        self.assertContains(r, "PS-MS")


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

    def test_le_formulaire_propose_la_date_du_jour(self):
        reponse = self.client.get(reverse("bilans_eleve", args=[self.eleve.pk]))

        self.assertContains(
            reponse,
            f'value="{timezone.localdate().isoformat()}"',
        )

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

    def test_un_bilan_peut_etre_modifie_sans_en_creer_un_second(self):
        bilan = Bilan.objects.create(
            scolarite=self.scolarite,
            date_bilan="2027-01-15",
            texte="Premier texte",
        )

        self.client.post(
            reverse("modifier_bilan", args=[self.eleve.pk, bilan.pk]),
            {
                "scolarite": self.scolarite.pk,
                "date_bilan": "2027-02-01",
                "texte": "Texte corrigé",
                "visible_carnet": "on",
            },
        )

        bilan.refresh_from_db()
        self.assertEqual(Bilan.objects.count(), 1)
        self.assertEqual(str(bilan.date_bilan), "2027-02-01")
        self.assertEqual(bilan.texte, "Texte corrigé")

    def test_un_conflit_de_date_conserve_le_brouillon_sans_ecraser_le_bilan(self):
        existant = Bilan.objects.create(
            scolarite=self.scolarite,
            date_bilan="2027-01-15",
            texte="Texte déjà enregistré",
        )

        reponse = self.client.post(
            reverse("bilans_eleve", args=[self.eleve.pk]),
            {
                "scolarite": self.scolarite.pk,
                "date_bilan": "2027-01-15",
                "texte": "Brouillon en cours de saisie",
                "visible_carnet": "on",
            },
        )

        existant.refresh_from_db()
        self.assertEqual(existant.texte, "Texte déjà enregistré")
        self.assertContains(reponse, "Brouillon en cours de saisie")
        self.assertContains(reponse, "Un bilan existe déjà à cette date")
        self.assertEqual(Bilan.objects.count(), 1)

    def test_un_bilan_est_modifie_a_sa_place_dans_l_historique(self):
        bilan = Bilan.objects.create(
            scolarite=self.scolarite,
            date_bilan="2027-01-15",
            texte="Texte à reprendre",
        )

        reponse = self.client.get(
            reverse("modifier_bilan", args=[self.eleve.pk, bilan.pk])
        )

        self.assertContains(reponse, "Texte à reprendre", count=1)
        self.assertContains(reponse, 'class="trace-conservee en-edition"')
        self.assertNotContains(reponse, "Ajouter un bilan")

    def test_la_visibilite_d_un_bilan_se_bascule_depuis_l_historique(self):
        bilan = Bilan.objects.create(
            scolarite=self.scolarite,
            date_bilan="2027-01-15",
            texte="Bilan à publier",
        )
        url = reverse(
            "basculer_visibilite_bilan", args=[self.eleve.pk, bilan.pk]
        )

        self.assertContains(
            self.client.get(reverse("bilans_eleve", args=[self.eleve.pk])),
            "✓ Affiché dans le carnet",
        )
        self.client.post(url)

        bilan.refresh_from_db()
        self.assertFalse(bilan.visible_carnet)
        self.assertNotContains(
            self.client.get(reverse("carnet", args=[self.eleve.pk])),
            "Bilan à publier",
        )
        self.assertContains(
            self.client.get(reverse("bilans_eleve", args=[self.eleve.pk])),
            "○ Masqué du carnet",
        )

    def test_basculer_la_visibilite_d_un_bilan_exige_post(self):
        bilan = Bilan.objects.create(
            scolarite=self.scolarite,
            date_bilan="2027-01-15",
            texte="À conserver",
        )

        reponse = self.client.get(
            reverse(
                "basculer_visibilite_bilan", args=[self.eleve.pk, bilan.pk]
            )
        )

        self.assertEqual(reponse.status_code, 403)
        bilan.refresh_from_db()
        self.assertTrue(bilan.visible_carnet)

    def test_un_bilan_peut_etre_supprime_logiquement(self):
        bilan = Bilan.objects.create(
            scolarite=self.scolarite,
            date_bilan="2027-01-15",
            texte="À supprimer",
        )

        reponse = self.client.post(
            reverse("supprimer_bilan", args=[self.eleve.pk, bilan.pk])
        )

        self.assertRedirects(reponse, reverse("bilans_eleve", args=[self.eleve.pk]))
        bilan.refresh_from_db()
        self.assertIsNotNone(bilan.supprime_le)

    def test_supprimer_un_bilan_exige_post(self):
        bilan = Bilan.objects.create(
            scolarite=self.scolarite,
            date_bilan="2027-01-15",
            texte="À conserver",
        )

        reponse = self.client.get(
            reverse("supprimer_bilan", args=[self.eleve.pk, bilan.pk])
        )

        self.assertEqual(reponse.status_code, 403)
        self.assertTrue(Bilan.objects.filter(pk=bilan.pk).exists())


class ParametrageCarnet(Base):
    def setUp(self):
        super().setUp()
        self.entrer("dir-mdp")

    def test_la_direction_definit_les_valeurs_par_defaut_du_carnet(self):
        self.client.post(
            reverse("parametres_carnet"),
            {
                "titre_couverture": "Mes petits pas",
                "texte_couverture": "École des Tilleuls",
                "contenu_par_defaut": "reussites",
                "regroupement_par_defaut": "mensuel",
                "colonnes_par_defaut": "1",
                "afficher_attendus": "on",
                "afficher_sous_domaines": "on",
            },
        )

        parametres = ParametresCarnet.objects.get(ecole=self.ecole)
        self.assertEqual(parametres.titre_couverture, "Mes petits pas")
        self.assertEqual(parametres.contenu_par_defaut, "reussites")
        self.assertEqual(parametres.regroupement_par_defaut, "mensuel")
        self.assertEqual(parametres.colonnes_par_defaut, 1)
        self.assertTrue(parametres.afficher_attendus)
        self.assertFalse(parametres.inclure_bilans)

    def test_attendus_et_sous_domaine_sont_optionnels_dans_le_carnet(self):
        self.client.logout()
        self.entrer()
        sous_domaine = SousDomaine.objects.create(
            domaine=self.competence.domaine,
            code="ORAL",
            nom="L'oral",
        )
        self.competence.sous_domaine = sous_domaine
        self.competence.save(update_fields=["sous_domaine"])
        Attendu.objects.create(
            domaine=self.competence.domaine,
            code="LANG-ATT-01",
            texte="Communiquer avec les adultes et les autres enfants.",
        )
        Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
            statut=Observation.REUSSI,
        )
        url = reverse("carnet", args=[self.eleve.pk])

        affiche = self.client.get(
            url,
            {"attendus": "1", "sous_domaines": "1"},
        )
        masque = self.client.get(
            url,
            {"attendus": "0", "sous_domaines": "0"},
        )

        self.assertContains(affiche, "Communiquer avec les adultes")
        self.assertContains(affiche, "L&#x27;oral")
        self.assertNotContains(masque, "Communiquer avec les adultes")
        self.assertNotContains(masque, "L&#x27;oral")


class Referentiel(Base):
    def test_charge_les_attendus_et_les_sous_domaines(self):
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(
                "domaines:\n"
                "  - code: LANG\n"
                "    nom: Langage\n"
                "    attendus:\n"
                "      - { code: LANG-A1, texte: 'Communiquer avec les autres.' }\n"
                "    sous_domaines:\n"
                "      - code: ORAL\n"
                "        nom: L'oral\n"
                "        competences:\n"
                "          - { code: LANG-02, niveau: PS, libelle: 'Je parle.' }\n"
            )
            chemin = f.name

        call_command(
            "charger_referentiel",
            chemin,
            ecole=self.ecole.pk,
            stdout=StringIO(),
        )

        competence = Competence.objects.get(code="LANG-02")
        self.assertEqual(competence.sous_domaine.code, "ORAL")
        self.assertEqual(
            Attendu.objects.get(code="LANG-A1").texte,
            "Communiquer avec les autres.",
        )

    def test_charge_et_desactive_les_formulations_proposees(self):
        from tempfile import NamedTemporaryFile

        def charger(formulations):
            with NamedTemporaryFile(
                "w", suffix=".yaml", delete=False, encoding="utf-8"
            ) as fichier:
                fichier.write(
                    "domaines:\n"
                    "  - code: LANG\n"
                    "    nom: Langage\n"
                    "    competences:\n"
                    "      - code: LANG-01\n"
                    "        niveau: PS\n"
                    "        libelle: Je dis mon prénom\n"
                    f"        formulations: {formulations}\n"
                )
                chemin = fichier.name
            call_command(
                "charger_referentiel",
                chemin,
                ecole=self.ecole.pk,
                stdout=StringIO(),
            )

        charger("[{ code: F01, texte: '{prenom} sait se présenter.' }]")
        formulation = FormulationProposee.objects.get(code="F01")
        self.assertTrue(formulation.active)

        charger("[]")
        formulation.refresh_from_db()
        self.assertFalse(formulation.active)

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
    def test_confirme_le_retrait_des_acces_historiques_et_de_l_admin_web(self):
        sortie = StringIO()

        call_command("diagnostiquer_deploiement", stdout=sortie)

        texte = sortie.getvalue()
        self.assertIn("Identités individuelles : configurées", texte)
        self.assertIn("Accès partagés persistants : absents", texte)
        self.assertIn("Administration Django sur le Web : fermée", texte)
        self.assertEqual(self.client.get("/admin/").status_code, 404)

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
        SECURE_SSL_REDIRECT=True,
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
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
        SECURE_SSL_REDIRECT=True,
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
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


class DurcissementAutorisations(Base):
    def test_la_session_ne_porte_aucun_role_textuel(self):
        self.entrer("dir-mdp")

        self.assertNotIn("role", self.client.session)
        self.assertNotIn("ecole_role", self.client.session)

    def test_le_modele_ecole_ne_porte_plus_les_secrets_historiques(self):
        champs = {champ.name for champ in Ecole._meta.get_fields()}

        self.assertNotIn("mdp_enseignant", champs)
        self.assertNotIn("mdp_direction", champs)
        self.assertFalse(hasattr(Ecole, "verifier"))

    def test_une_erreur_d_audit_annule_la_mutation(self):
        with (
            patch(
                "suivi.services.pedagogie.journaliser",
                side_effect=RuntimeError("audit indisponible"),
            ),
            self.assertRaises(RuntimeError),
        ):
            modifier_etat(
                utilisateur=self.enseignant,
                eleve=self.eleve,
                competence=self.competence,
                statut=Observation.REUSSI,
            )

        self.assertFalse(
            Observation.objects.filter(
                eleve=self.eleve, competence=self.competence
            ).exists()
        )

    def test_les_urls_de_mutation_refusent_get(self):
        self.entrer("dir-mdp")
        observation = Observation.objects.create(
            eleve=self.eleve, competence=self.competence
        )
        trace = self.creer_trace(observation)
        trace_supprimee = self.creer_trace(observation)
        trace_supprimee.supprime_le = timezone.now()
        trace_supprimee.save(update_fields=["supprime_le"])
        bilan = Bilan.objects.create(
            scolarite=self.scolarite,
            date_bilan="2027-01-15",
            texte="Bilan inchangé",
        )
        urls = [
            reverse("basculer", args=[self.eleve.pk, self.competence.pk]),
            reverse(
                "supprimer_trace",
                args=[self.eleve.pk, self.competence.pk, trace.pk],
            ),
            reverse(
                "basculer_visibilite_trace",
                args=[self.eleve.pk, self.competence.pk, trace.pk],
            ),
            reverse(
                "restaurer_trace",
                args=[
                    self.eleve.pk,
                    self.competence.pk,
                    trace_supprimee.pk,
                ],
            ),
            reverse("supprimer_bilan", args=[self.eleve.pk, bilan.pk]),
            reverse(
                "basculer_visibilite_bilan", args=[self.eleve.pk, bilan.pk]
            ),
            reverse("archiver_eleve", args=[self.eleve.pk]),
            reverse("desarchiver_eleve", args=[self.eleve.pk]),
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

        self.eleve.refresh_from_db()
        trace.refresh_from_db()
        trace_supprimee.refresh_from_db()
        bilan.refresh_from_db()
        self.assertIsNone(self.eleve.archive_le)
        self.assertIsNone(trace.supprime_le)
        self.assertIsNotNone(trace_supprimee.supprime_le)
        self.assertTrue(trace.visible_carnet)
        self.assertTrue(bilan.visible_carnet)


class JeuDemoLarge(TestCase):
    def _charger_referentiel_demo(self, ecole):
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(
                "domaines:\n"
                "  - code: LANG\n"
                "    nom: Langage\n"
                "    competences:\n"
                "      - { code: LANG-PS-01, niveau: PS, libelle: 'Compétence PS 1' }\n"
                "      - { code: LANG-PS-02, niveau: PS, libelle: 'Compétence PS 2' }\n"
                "      - { code: LANG-MS-01, niveau: MS, libelle: 'Compétence MS 1' }\n"
                "      - { code: LANG-MS-02, niveau: MS, libelle: 'Compétence MS 2' }\n"
                "      - { code: LANG-GS-01, niveau: GS, libelle: 'Compétence GS 1' }\n"
                "      - { code: LANG-GS-02, niveau: GS, libelle: 'Compétence GS 2' }\n"
            )
            chemin = f.name
        call_command("charger_referentiel", chemin, ecole=ecole.pk, stdout=StringIO())

    def setUp(self):
        self.ecole = Ecole.objects.create(nom="École de démo")
        self._charger_referentiel_demo(self.ecole)

    def _creer_comptes_initiaux(self):
        Utilisateur = get_user_model()
        enseignant = Utilisateur.objects.create_user(
            username="enseignant-demo", password="demo-factice"
        )
        direction = Utilisateur.objects.create_user(
            username="direction-demo", password="direction-factice"
        )
        AppartenanceEcole.objects.create(
            utilisateur=enseignant, ecole=self.ecole
        )
        appartenance_direction = AppartenanceEcole.objects.create(
            utilisateur=direction, ecole=self.ecole
        )
        ResponsabiliteEcole.objects.create(
            appartenance=appartenance_direction,
            type=ResponsabiliteEcole.DIRECTION,
        )

    def test_genere_cinq_annees_avec_plusieurs_classes_chacune(self):
        call_command("jeu_demo_large", stdout=StringIO())

        annees = set(self.ecole.classes.values_list("annee_scolaire", flat=True))
        self.assertEqual(
            annees,
            {"2022-2023", "2023-2024", "2024-2025", "2025-2026", "2026-2027"},
        )
        for annee in annees:
            self.assertEqual(self.ecole.classes.filter(annee_scolaire=annee).count(), 2)

    def test_les_enfants_nes_en_2019_et_2020_sont_archives(self):
        call_command("jeu_demo_large", stdout=StringIO())

        self.assertTrue(
            Eleve.objects.filter(ecole=self.ecole, annee_naissance=2019)
            .exclude(archive_le__isnull=True)
            .exists()
        )
        self.assertFalse(
            Eleve.objects.filter(ecole=self.ecole, annee_naissance=2023)
            .exclude(archive_le__isnull=True)
            .exists()
        )

    def test_les_trois_parcours_non_standards_sont_crees(self):
        call_command("jeu_demo_large", stdout=StringIO())

        redouble = Eleve.objects.get(ecole=self.ecole, prenom="Redouble")
        self.assertEqual(
            list(redouble.scolarites.order_by("annee_scolaire").values_list("niveau", flat=True)),
            ["PS", "PS", "MS", "GS"],
        )
        self.assertIsNone(redouble.archive_le)

        direct = Eleve.objects.get(ecole=self.ecole, prenom="Direct")
        self.assertEqual(direct.scolarites.count(), 2)
        self.assertFalse(direct.scolarites.filter(niveau="PS").exists())

        retour = Eleve.objects.get(ecole=self.ecole, prenom="Retour")
        self.assertIsNone(retour.archive_le)
        self.assertEqual(
            set(retour.scolarites.values_list("annee_scolaire", flat=True)),
            {"2024-2025", "2026-2027"},
        )

    def test_des_bilans_sont_crees(self):
        call_command("jeu_demo_large", stdout=StringIO())

        self.assertTrue(Bilan.objects.filter(scolarite__eleve__ecole=self.ecole).exists())

    def test_ajoute_une_hierarchie_de_demonstration(self):
        call_command("jeu_demo_large", stdout=StringIO())

        self.assertTrue(SousDomaine.objects.filter(domaine__ecole=self.ecole).exists())
        self.assertTrue(Attendu.objects.filter(domaine__ecole=self.ecole).exists())
        self.assertTrue(
            Competence.objects.filter(
                domaine__ecole=self.ecole, sous_domaine__isnull=False
            ).exists()
        )

    def test_loption_sans_hierarchie_n_ajoute_rien(self):
        call_command("jeu_demo_large", "--sans-hierarchie", stdout=StringIO())

        self.assertFalse(SousDomaine.objects.filter(domaine__ecole=self.ecole).exists())
        self.assertFalse(Attendu.objects.filter(domaine__ecole=self.ecole).exists())

    def test_un_second_lancement_est_refuse(self):
        call_command("jeu_demo_large", stdout=StringIO())

        with self.assertRaises(CommandError):
            call_command("jeu_demo_large", stdout=StringIO())

    def test_cree_un_scenario_d_equipe_riche(self):
        self._creer_comptes_initiaux()
        call_command("jeu_demo_large", stdout=StringIO())

        call_command(
            "jeu_demo_equipe",
            "--mot-de-passe",
            "demo-factice",
            "--confirmer-donnees-fictives",
            stdout=StringIO(),
        )

        Utilisateur = get_user_model()
        nadia = Utilisateur.objects.get(username="nadia-demo")
        samir = Utilisateur.objects.get(username="samir-demo")
        lea = Utilisateur.objects.get(username="lea-demo")
        marc = Utilisateur.objects.get(username="marc-demo")
        alice = Utilisateur.objects.get(username="alice-demo")
        self.assertEqual(nadia.first_name, "Nadia")
        self.assertEqual(nadia.last_name, "Co-titulaire")
        self.assertEqual(
            AffectationClasse.objects.filter(
                appartenance__utilisateur=nadia,
                type=AffectationClasse.RESPONSABLE,
            ).count(),
            2,
        )
        self.assertEqual(
            set(
                AffectationClasse.objects.filter(
                    appartenance__utilisateur=samir
                ).values_list("type", flat=True)
            ),
            {
                AffectationClasse.ENSEIGNANT_ASSOCIE,
                AffectationClasse.CONTRIBUTEUR,
            },
        )
        temporaire = AffectationClasse.objects.get(
            appartenance__utilisateur=lea
        )
        self.assertIsNotNone(temporaire.date_fin)
        self.assertIn("temporaire", temporaire.motif)
        self.assertFalse(
            AffectationClasse.objects.filter(appartenance__utilisateur=marc).exists()
        )
        self.assertTrue(
            AffectationClasse.objects.filter(
                appartenance__utilisateur=alice,
                etat=AffectationClasse.TERMINEE,
            ).exists()
        )
        self.assertEqual(Invitation.objects.filter(ecole=self.ecole).count(), 2)
        self.assertTrue(
            AnomalieGouvernance.objects.filter(
                ecole=self.ecole,
                type=AnomalieGouvernance.CLASSE_SANS_RESPONSABLE,
                resolue_le__isnull=True,
            ).exists()
        )
        self.assertEqual(
            self.ecole.classes.filter(
                annee_scolaire="2026-2027", etat=Classe.ACTIVE
            ).count(),
            2,
        )
        self.assertFalse(
            Trace.objects.filter(
                scolarite__classe__annee_scolaire="2026-2027",
                auteur__isnull=True,
            ).exists()
        )
        for username in ("amina-demo", "cora-demo", "samir-demo"):
            self.assertTrue(
                Trace.objects.filter(auteur__username=username).exists(), username
            )
        self.assertFalse(
            Bilan.objects.filter(
                scolarite__classe__annee_scolaire="2026-2027",
                auteur__isnull=True,
            ).exists()
        )

    def test_refuse_le_scenario_d_equipe_sans_confirmation_fictive(self):
        with self.assertRaisesMessage(CommandError, "donnée réelle"):
            call_command(
                "jeu_demo_equipe",
                "--mot-de-passe",
                "demo-factice",
                stdout=StringIO(),
            )

    def test_configuration_publique_decrit_neuf_profils_valides(self):
        from django.conf import settings

        from suivi.configuration_demo import charger_configuration_demo

        configuration = charger_configuration_demo(
            settings.BASE_DIR / "site" / "data" / "demonstration.yaml"
        )

        self.assertEqual(len(configuration["profils"]), 9)
        self.assertEqual(
            {profil["id"] for profil in configuration["profils"]},
            {"diane", "remi", "nadia", "amina", "cora", "samir", "lea", "marc", "alice"},
        )
        alice = next(
            profil for profil in configuration["profils"] if profil["id"] == "alice"
        )
        self.assertEqual(alice["affectations"][0]["periode"], "terminee")
        self.assertEqual(len(configuration["scenarios"]), 11)
        self.assertEqual(
            {scenario["profil"] for scenario in configuration["scenarios"]},
            {"diane", "nadia", "cora", "samir"},
        )
        self.assertEqual(
            sum("capture_mobile" in scenario for scenario in configuration["scenarios"]),
            3,
        )
        self.assertEqual(
            {
                scenario["cible"]
                for scenario in configuration["scenarios"]
                if "cible" in scenario
            },
            {
                "#membre-lea-demo",
                "#membre-alice-demo",
                "#membre-marc-demo",
                "#invitations",
                "#gouvernance",
            },
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
        Utilisateur = get_user_model()
        self.assertTrue(
            Utilisateur.objects.get(username="enseignant-atelier").check_password(
                "enseignant-factice"
            )
        )
        self.assertEqual(
            Utilisateur.objects.get(
                username="direction-atelier"
            ).appartenances_ecoles.get().ecole,
            ecole,
        )

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


class EquipeEtGouvernance(Base):
    def setUp(self):
        super().setUp()
        self.direction.first_name = "Diane"
        self.direction.last_name = "Direction"
        self.direction.email = "diane@example.test"
        self.direction.save()
        self.enseignant.first_name = "Rémi"
        self.enseignant.last_name = "Responsable"
        self.enseignant.email = "remi@example.test"
        self.enseignant.save()
        Utilisateur = get_user_model()
        self.cora = Utilisateur.objects.create_user(
            "cora", "cora@example.test", "cora-mdp",
            first_name="Cora", last_name="Contribution",
        )
        appartenance = AppartenanceEcole.objects.create(
            utilisateur=self.cora, ecole=self.ecole
        )
        AffectationClasse.objects.create(
            appartenance=appartenance,
            classe=self.classe,
            type=AffectationClasse.CONTRIBUTEUR,
        )
        self.marc = Utilisateur.objects.create_user(
            "marc", "marc@example.test", "marc-mdp",
            first_name="Marc", last_name="Sans affectation",
        )
        AppartenanceEcole.objects.create(utilisateur=self.marc, ecole=self.ecole)

    def test_t080_direction_voit_toute_l_equipe_et_les_coordonnees(self):
        self.entrer("dir-mdp")
        reponse = self.client.get(reverse("equipe_ecole"))
        self.assertContains(reponse, "Rémi Responsable")
        self.assertContains(reponse, "remi@example.test")
        self.assertContains(reponse, "Responsable de classe")

    def test_t081_responsable_ne_voit_pas_l_equipe_complete(self):
        self.entrer()
        self.assertEqual(self.client.get(reverse("equipe_ecole")).status_code, 403)

    def test_t082_responsable_voit_les_collaborateurs_sans_coordonnees(self):
        self.entrer()
        reponse = self.client.get(reverse("collaborateurs_classe", args=[self.classe.pk]))
        self.assertContains(reponse, "Cora Contribution")
        self.assertContains(reponse, "Contributeur")
        self.assertNotContains(reponse, "cora@example.test")

    def test_t083_t084_contributrice_voit_la_liste_limitee(self):
        self.entrer("cora-mdp", "cora")
        reponse = self.client.get(reverse("collaborateurs_classe", args=[self.classe.pk]))
        self.assertContains(reponse, "Rémi Responsable")
        self.assertNotContains(reponse, "remi@example.test")
        self.assertEqual(self.client.get(reverse("equipe_ecole")).status_code, 403)

    def test_t085_membre_sans_affectation_ne_voit_pas_les_collaborateurs(self):
        self.client.force_login(self.marc)
        reponse = self.client.get(reverse("collaborateurs_classe", args=[self.classe.pk]))
        self.assertIn(reponse.status_code, (403, 404))

    def test_invitation_est_hachee_et_liee_a_l_adresse(self):
        invitation, jeton = inviter(
            utilisateur=self.direction,
            ecole=self.ecole,
            email="invitee@example.test",
        )
        self.assertNotEqual(invitation.empreinte_jeton, jeton)
        invitee = get_user_model().objects.create_user(
            "invitee", "invitee@example.test", "secret"
        )
        accepter_invitation(utilisateur=invitee, invitation=invitation, jeton=jeton)
        self.assertTrue(
            AppartenanceEcole.objects.filter(utilisateur=invitee, ecole=self.ecole).exists()
        )

    def test_derniere_affectation_responsable_ne_peut_etre_terminee(self):
        affectation = AffectationClasse.objects.get(
            classe=self.classe, type=AffectationClasse.RESPONSABLE
        )
        with self.assertRaises(ValidationError):
            terminer_affectation(utilisateur=self.direction, affectation=affectation)
