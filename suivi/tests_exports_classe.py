"""Isolation annuelle, droits et transports d'une copie de classe fictive."""
import io
import copy
import json
import sqlite3
from datetime import timedelta, date
from unittest.mock import patch
from unittest import skipUnless
from zipfile import ZipFile

from django.contrib.auth.hashers import check_password, make_password
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse
from django.db import connections, connection
from django.utils import timezone

from comptes.models import AffectationClasse, AppartenanceEcole
from . import models as m
from .exports_classe import autorise_export_classe, produire_classe, creer_zip_classe, construire_classe
from .exports_ecole import dossier
from . import tests_exports_ecole


class ExportClasseTests(TransactionTestCase):
    def setUp(self):
        tests_exports_ecole.ExportEcoleTests.setUp(self)
        self.classe = m.Classe.objects.create(ecole=self.ecole, nom="Classe exportable", annee_scolaire="2026-2027")
        self.voisine = m.Classe.objects.create(ecole=self.ecole, nom="AUTRE_CLASSE_PRIVEE", annee_scolaire="2026-2027")
        appartenance = AppartenanceEcole.objects.get(utilisateur=self.prof, ecole=self.ecole)
        self.affectation = AffectationClasse.objects.create(appartenance=appartenance, classe=self.classe,
            type=AffectationClasse.RESPONSABLE)
        self.classe.activer()
        self.client.force_login(self.prof)
        self.params = override_settings(EXPORT_CLASSES={self.ecole.pk})
        self.params.enable()
        self.addCleanup(self.params.disable)
        call_command("charger_referentiel", "referentiel/trame-cycle1.yaml", ecole=self.ecole.pk, verbosity=0)
        self.competence = m.Competence.objects.filter(domaine__ecole=self.ecole).first()
        self.eleve = m.Eleve.objects.create(ecole=self.ecole, prenom="Enfant exportable")
        self.sc = m.Scolarite.objects.create(eleve=self.eleve, classe=self.classe, annee_scolaire="2026-2027", niveau="MS")
        self.obs = m.Observation.objects.create(eleve=self.eleve, competence=self.competence,
            statut="en_cours", date_observation=date(2026, 10, 1))
        self.trace = m.Trace.objects.create(observation=self.obs, scolarite=self.sc, auteur=self.prof,
            commentaire="Trace interne exportable", visible_carnet=False)
        self.trace.photo.save("classe.bin", ContentFile(b"photo-de-realisation-fictive"))
        self.secret = m.Eleve.objects.create(ecole=self.ecole, prenom="AUTRE_ENFANT_PRIVE")
        self.secret_sc = m.Scolarite.objects.create(eleve=self.secret, classe=self.voisine, annee_scolaire="2026-2027", niveau="PS")
        self.secret_obs = m.Observation.objects.create(eleve=self.secret, competence=self.competence)
        self.secret_trace = m.Trace.objects.create(observation=self.secret_obs, scolarite=self.secret_sc,
            commentaire="AUTRE_TRACE_PRIVEE", auteur=self.direction)
        self.secret_trace.photo.save("secret.bin", ContentFile(b"AUTRE_MEDIA_PRIVE"))

    def demande(self):
        return m.ExportClasse.objects.create(classe=self.classe, demande_par=self.prof,
            mot_de_passe_local=make_password("Copie!Fictive2026"),
            expire_le=timezone.now() + timedelta(hours=24))

    def donnees(self):
        return {"action": "preparer", "mot_de_passe": "Secret!Enseignant2026",
                "mot_de_passe_local": "Copie!Fictive2026", "confirmation_locale": "Copie!Fictive2026", "confirme": "on"}

    def lire(self, archive):
        with ZipFile(archive) as z:
            contenu = z.read("carnet.sqlite3")
            manifest = json.loads(z.read("manifest.json"))
            noms = z.namelist()
        chemin = self.root / "verification.sqlite3"
        chemin.write_bytes(contenu)
        return sqlite3.connect(chemin), manifest, noms

    def test_projection_isolee_et_compte_local_administrable(self):
        from .services.reprise_referentiels import preparer_nouvelle_ecole
        # La reprise annuelle conserve normalement les réglages de toutes les classes.
        m.ReglagePresentation.objects.create(ecole=self.ecole, classe=self.voisine, mode="desactiver")
        m.FormulationLocale.objects.create(ecole=self.ecole, classe=self.voisine,
            competence=self.competence, texte="FORMULATION_AUTRE_CLASSE_PRIVEE")
        preparer_nouvelle_ecole(self.ecole)
        commune = m.TraceCommune.objects.create(classe=self.classe, competence=self.competence,
            auteur=self.prof, commentaire="Origine commune", photo=self.trace.photo.name)
        self.trace.commune = commune
        self.trace.save(update_fields=["commune"])
        m.Trace.objects.create(observation=self.obs, scolarite=self.sc, auteur=self.prof,
            commentaire="TRACE_SUPPRIMEE", supprime_le=timezone.now(), photo=self.secret_trace.photo.name)
        self.trace.auteur = self.direction
        self.trace.save(update_fields=["auteur"])
        export = self.demande()
        produire_classe(export)
        export.refresh_from_db()
        self.assertEqual(export.etat, "pret")
        db, manifest, noms = self.lire(dossier(export) / "ecole.zip")
        with db:
            self.assertEqual(db.execute("select nom from suivi_classe").fetchall(), [(self.classe.nom,)])
            self.assertEqual(db.execute("select prenom from suivi_eleve").fetchall(), [(self.eleve.prenom,)])
            self.assertEqual(db.execute("select commentaire,commune_id,origine_commune_id from suivi_trace").fetchall(), [(self.trace.commentaire, None, None)])
            self.assertEqual(db.execute("select count(*) from suivi_tracecommune").fetchone()[0], 0)
            self.assertEqual(db.execute("select count(*) from suivi_evenementaudit").fetchone()[0], 0)
            self.assertEqual(db.execute("select count(*) from comptes_invitation").fetchone()[0], 0)
            self.assertEqual(db.execute("select count(*) from suivi_exportclasse").fetchone()[0], 0)
            self.assertFalse(db.execute("pragma foreign_key_check").fetchall())
            mdp, actif, staff, superuser = db.execute("select password,is_active,is_staff,is_superuser from comptes_utilisateur where id=?", (self.prof.pk,)).fetchone()
            self.assertTrue(check_password("Copie!Fictive2026", mdp))
            self.assertFalse(check_password("Secret!Enseignant2026", mdp))
            self.assertEqual((actif,staff,superuser), (1,0,0))
            historique = db.execute("select username,first_name,email,password,is_active,is_staff,is_superuser from comptes_utilisateur where id=?", (self.direction.pk,)).fetchone()
            self.assertNotEqual(historique[0], self.direction.username)
            self.assertEqual(historique[1:], (self.direction.username, "", "!", 0, 0, 0))
            self.assertEqual(db.execute("select count(*) from comptes_responsabiliteecole").fetchone()[0], 1)
            initial = db.execute("select etat_initial from suivi_referentielannuel").fetchone()[0]
            self.assertNotIn("FORMULATION_AUTRE_CLASSE_PRIVEE", initial)
            self.assertNotIn(str(self.voisine.pk), [str(r.get("classe_id")) for r in json.loads(initial)["reglages"]])
        db.close()
        self.assertIn("media/" + self.trace.photo.name, noms)
        self.assertNotIn("media/" + self.secret_trace.photo.name, noms)
        self.assertEqual(manifest["export_classe"]["annee_scolaire"], "2026-2027")
        self.assertEqual(m.Classe.objects.count(), 2)
        self.assertFalse(m.ExportEcole.objects.exists())

    def test_autorisations_independantes_et_joker(self):
        self.assertTrue(autorise_export_classe(self.prof, self.classe))
        self.assertFalse(autorise_export_classe(self.direction, self.classe))
        self.assertFalse(autorise_export_classe(self.prof, self.voisine))
        with override_settings(EXPORT_ECOLES="*", EXPORT_CLASSES=set()):
            self.assertFalse(autorise_export_classe(self.prof, self.classe))
        with override_settings(EXPORT_ECOLES=set(), EXPORT_CLASSES="*"):
            self.assertTrue(autorise_export_classe(self.prof, self.classe))
        with override_settings(MODE_LOCAL=True, EXPORT_CLASSES=set()):
            self.assertTrue(autorise_export_classe(self.prof, self.classe))
        self.affectation.type = AffectationClasse.ENSEIGNANT_ASSOCIE
        self.affectation.save()
        self.assertFalse(autorise_export_classe(self.prof, self.classe))

    def test_suppression_autorisation_avant_traitement_et_telechargement(self):
        export = self.demande()
        with override_settings(EXPORT_CLASSES=set()):
            call_command("preparer_exports_ecoles", verbosity=0)
        export.refresh_from_db()
        self.assertEqual(export.etat, "echec")
        self.assertEqual(export.mot_de_passe_local, "")
        self.assertFalse(dossier(export).exists())

    def test_transport_csrf_confirmation_doublon_et_reprise(self):
        url = reverse("exporter_classe", args=[self.classe.pk])
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.prof)
        self.assertEqual(client.post(url, self.donnees()).status_code, 403)
        mauvaise = {**self.donnees(), "mot_de_passe": "incorrect"}
        self.assertEqual(self.client.post(url, mauvaise).status_code, 200)
        self.assertFalse(m.ExportClasse.objects.exists())
        self.assertEqual(self.client.post(url, self.donnees()).status_code, 302)
        export = m.ExportClasse.objects.get()
        self.assertEqual(self.client.post(url, self.donnees()).status_code, 200)
        self.assertEqual(m.ExportClasse.objects.count(), 1)
        call_command("preparer_exports_ecoles", verbosity=0)
        export.refresh_from_db()
        self.assertEqual(export.etat, "pret", export.erreur)
        telecharger = reverse("telecharger_export_classe", args=[self.classe.pk, export.identifiant])
        response = self.client.get(telecharger, HTTP_RANGE="bytes=100-199")
        self.assertEqual(response.status_code, 206)
        contenu = b"".join(response.streaming_content)
        response.close()
        self.assertEqual(len(contenu), 100)
        self.assertEqual(contenu, (dossier(export) / "ecole.zip").read_bytes()[100:200])
        with override_settings(EXPORT_CLASSES=set()):
            self.assertEqual(self.client.get(telecharger).status_code, 404)
        export.expire_le = timezone.now() - timedelta(seconds=1)
        export.save(update_fields=["expire_le"])
        self.assertEqual(self.client.get(telecharger).status_code, 404)

    @skipUnless(connection.vendor == "sqlite", "Le poste local/PWA utilise SQLite, sans sous-processus.")
    def test_local_sans_sous_processus_et_sans_modifier_la_sauvegarde(self):
        from .paquet_local import suivi_export
        avant = suivi_export(self.root)
        with override_settings(MODE_LOCAL=True, EXPORT_CLASSES=set()), patch("subprocess.run", side_effect=AssertionError("sous-processus interdit")):
            response = self.client.post(reverse("exporter_classe", args=[self.classe.pk]), self.donnees())
            self.assertEqual(response.status_code, 200)
            archive = io.BytesIO(b"".join(response.streaming_content))
            response.close()
            db, manifest, noms = self.lire(archive)
            self.assertFalse(db.execute("pragma foreign_key_check").fetchall())
            db.close()
        self.assertEqual(suivi_export(self.root), avant)
        self.assertFalse(m.ExportClasse.objects.exists())
        self.assertEqual(m.Eleve.objects.count(), 2)

    def test_etat_annee_et_media_non_telechargeable_exclus(self):
        from .services.reprise_referentiels import preparer_nouvelle_ecole
        preparer_nouvelle_ecole(self.ecole)
        ancienne = self.classe.annee_scolaire
        # L'élève a depuis une nouvelle scolarité ; l'état courant est privé
        # pour le périmètre de l'ancienne année et ne doit pas remplacer son état.
        self.voisine.annee_scolaire = "2027-2028"
        self.voisine.save()
        m.Scolarite.objects.create(eleve=self.eleve, classe=self.voisine, annee_scolaire="2027-2028", niveau="GS")
        annuel = m.EtatAnnuelObservation.objects.get(observation=self.obs, annee_scolaire=ancienne)
        annuel.statut, annuel.date_observation, annuel.connu = "en_cours", date(2026,10,1), True
        annuel.save()
        self.obs.statut, self.obs.date_observation = "reussi", date(2027,10,2)
        self.obs.save()
        export = self.demande()
        produire_classe(export)
        db, _, noms = self.lire(dossier(export) / "ecole.zip")
        self.assertEqual(db.execute("select statut,date_observation from suivi_observation where id=?", (self.obs.pk,)).fetchone(), ("en_cours","2026-10-01"))
        self.assertEqual(db.execute("select count(*) from suivi_trace").fetchone()[0], 0)
        self.assertNotIn("media/" + self.trace.photo.name, noms)
        db.close()

    @skipUnless(connection.vendor == "sqlite", "La PWA utilise SQLite, sans sous-processus.")
    def test_pwa_flux_opfs_et_plafonds(self):
        export = m.ExportClasse(classe=self.classe, demande_par=self.prof, mot_de_passe_local=make_password("Copie!Fictive2026"))
        travail = self.root / "projection-pwa"
        travail.mkdir()
        # Le chemin commun PWA ne doit ni lancer Python ni copier de média en MEMFS.
        with override_settings(MODE_LOCAL=True, MODE_PWA=True), patch("subprocess.run", side_effect=AssertionError("sous-processus interdit")):
            archive = io.BytesIO()
            creer_zip_classe(export, travail, archive)
        self.assertFalse(list((travail / "paquet" / "media").rglob("*")))
        db, _, noms = self.lire(archive)
        db.close()
        self.assertIn("media/" + self.trace.photo.name, noms)
        travail2 = self.root / "pwa-trop-grand"
        travail2.mkdir()
        with override_settings(MODE_LOCAL=True, MODE_PWA=True), patch("pwa.limits.ZIP_BYTES", 10):
            with self.assertRaisesMessage(Exception, "limites actuelles du navigateur"):
                creer_zip_classe(export, travail2, io.BytesIO())

    def test_lien_discret_et_absence_dans_les_sauvegardes(self):
        response = self.client.get(reverse("classe_detail", args=[self.classe.pk]))
        self.assertContains(response, "<summary>Transférer cette classe</summary>")
        self.assertContains(response, reverse("exporter_classe", args=[self.classe.pk]))
        with override_settings(EXPORT_CLASSES=set()):
            self.assertNotContains(self.client.get(reverse("classe_detail", args=[self.classe.pk])), "Transférer cette classe")

    def test_etat_ancien_inconnu_reste_inconnu_jusqua_une_nouvelle_saisie(self):
        from .services.reprise_referentiels import preparer_nouvelle_ecole
        from .export_projection import validation_sur
        from .referentiels import observations_classe
        preparer_nouvelle_ecole(self.ecole)
        self.voisine.annee_scolaire = "2027-2028"
        self.voisine.save()
        m.Scolarite.objects.create(eleve=self.eleve, classe=self.voisine, annee_scolaire="2027-2028", niveau="GS")
        travail = self.root / "inconnu"
        travail.mkdir()
        export = self.demande()
        paquet, _, _, _ = construire_classe(export, travail)
        alias = "export_lecture_inconnue"
        config = copy.deepcopy(connections["default"].settings_dict)
        config.update(ENGINE="django.db.backends.sqlite3", NAME=str(paquet / "carnet.sqlite3"), OPTIONS={})
        connections.databases[alias] = config
        try:
            with validation_sur(alias), override_settings(MODE_LOCAL=True):
                classe = m.Classe.objects.get()
                lecture = observations_classe(classe).get(pk=self.obs.pk)
                self.assertIsNone(lecture.statut_lecture)
                self.assertIsNone(lecture.date_lecture)
                self.assertFalse(lecture.connu_lecture)
                observation = m.Observation.objects.get(pk=self.obs.pk)
                observation.statut = "reussi"
                observation.date_observation = date(2026,10,8)
                observation.save()
                lecture = observations_classe(classe).get(pk=self.obs.pk)
                self.assertEqual(lecture.statut_lecture, "reussi")
                self.assertEqual(lecture.date_lecture, date(2026,10,8))
                self.assertTrue(lecture.connu_lecture)
        finally:
            connections[alias].close()
            del connections[alias]
            del connections.databases[alias]
        self.obs.refresh_from_db()
        self.assertEqual(self.obs.statut, "en_cours")

    def test_retrait_du_droit_pendant_la_preparation_locale_ne_livre_pas_le_zip(self):
        from .paquet_local import creer_sauvegarde
        def retrait(*args, **kwargs):
            creer_sauvegarde(*args, **kwargs)
            AffectationClasse.objects.filter(pk=self.affectation.pk).update(etat="suspendue")
        with override_settings(MODE_LOCAL=True), patch("suivi.exports_classe.creer_sauvegarde", side_effect=retrait):
            response = self.client.post(reverse("exporter_classe", args=[self.classe.pk]), self.donnees())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "L&#x27;autorisation d&#x27;export de la classe n&#x27;est plus disponible.")
        self.assertIn("text/html", response["Content-Type"])
        self.assertFalse(m.ExportClasse.objects.exists())
