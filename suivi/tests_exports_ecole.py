"""Écoles fictives : projection, autorisations, secrets, reprise et échecs."""
import json
import sqlite3
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from comptes.models import AppartenanceEcole, ResponsabiliteEcole, Utilisateur, DoubleFacteurCompte, Invitation
from .exports_ecole import dossier, produire, selections, verifier_couverture
from .models import (Classe, Ecole, Eleve, Competence, Scolarite, Observation, Trace, ExportEcole,
                     TraceCommune, ReferentielAnnuel, UsageCompetence, ChoixEcoleAnnuel,
                     ChoixApplicationAnnuel)
from .paquet_local import preparer_restauration


class BasesExport(frozenset):
    # Alias créés uniquement par la projection dans le dossier temporaire.
    def __contains__(self, alias):
        return super().__contains__(alias) or alias.startswith("export_")


class ExportEcoleTests(TransactionTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        permission = patch.object(type(self), "databases", BasesExport(self.databases))
        permission.start()
        self.addCleanup(permission.stop)
        self.ecole = Ecole.objects.create(nom="École fictive A")
        self.autre = Ecole.objects.create(nom="École privée B")
        self.direction = Utilisateur.objects.create_user(username="direction", email="direction@example.invalid",
            password="Serveur!Fictif2026", is_staff=True, is_superuser=True)
        self.prof = Utilisateur.objects.create_user(username="enseignant", password="Secret!Enseignant2026")
        appartenance = AppartenanceEcole.objects.create(utilisateur=self.direction, ecole=self.ecole)
        ResponsabiliteEcole.objects.create(appartenance=appartenance)
        AppartenanceEcole.objects.create(utilisateur=self.prof, ecole=self.ecole)
        AppartenanceEcole.objects.create(utilisateur=self.prof, ecole=self.autre, motif="Motif privé autre école")
        self.reglages = override_settings(EXPORT_ECOLES={self.ecole.pk}, EXPORT_ROOT=str(self.root / "exports"),
            MEDIA_ROOT=str(self.root / "media"), ANTIBRUTEFORCE_ACTIF=False,
            AUTHENTICATION_BACKENDS=["django.contrib.auth.backends.ModelBackend"],
            MODE_LOCAL=False, STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
            })
        self.reglages.enable()
        self.addCleanup(self.reglages.disable)
        self.addCleanup(self.temp.cleanup)
        self.client.force_login(self.direction)

    def demande(self):
        return ExportEcole.objects.create(ecole=self.ecole, demande_par=self.direction,
            mot_de_passe_local=make_password("Copie!Fictive2026"),
            expire_le=timezone.now() + timedelta(hours=24))

    def test_projection_complete_isolee_et_secrets_exclus(self):
        call_command("charger_referentiel", "referentiel/trame-cycle1.yaml", ecole=self.ecole.pk, verbosity=0)
        from .services.reprise_referentiels import preparer_nouvelle_ecole
        classe = Classe.objects.create(ecole=self.ecole, nom="Classe fictive", annee_scolaire="2026-2027")
        preparer_nouvelle_ecole(self.ecole)
        annuel = ReferentielAnnuel.objects.get(ecole=self.ecole)
        choix = ChoixEcoleAnnuel.objects.create(ecole=self.ecole, annee_scolaire="2026-2027",
                                               version_proposee=annuel.version_proposee)
        choix.versions_autorisees.add(annuel.version_proposee)
        application = ChoixApplicationAnnuel.objects.create(annee_scolaire="2026-2027",
            historique_permissions=[{"motif": "SECRET_HISTORIQUE_GLOBAL"}])
        application.versions_autorisees.add(annuel.version_proposee)
        Invitation.objects.create(ecole=self.ecole, email="invite@example.invalid", cree_par=self.direction,
            expire_le=timezone.now() + timedelta(days=1), empreinte_jeton="EMPREINTE_PRIVEE")
        eleve = Eleve.objects.create(ecole=self.ecole, prenom="Fictif")
        scolarite = Scolarite.objects.create(eleve=eleve, classe=classe, annee_scolaire="2026-2027", niveau="PS")
        competence = Competence.objects.filter(domaine__ecole=self.ecole).first()
        observation = Observation.objects.create(eleve=eleve, competence=competence)
        trace = Trace.objects.create(observation=observation, scolarite=scolarite, auteur=self.prof,
                                     commentaire="Historique fictif", visible_carnet=False,
                                     supprime_le=timezone.now())
        trace.photo.save("fictif.bin", ContentFile(b"media-fictif"))
        usage = UsageCompetence.objects.get(adoption__classe=classe, competence=competence)
        commune = TraceCommune.objects.create(classe=classe, competence=competence, auteur=self.prof,
            usage_referentiel=usage, photo=trace.photo.name, commentaire="Trace partagée fictive")
        trace.origine_commune = commune
        trace.usage_referentiel = usage
        trace.save(update_fields=["origine_commune", "usage_referentiel"])
        # Un média sans référence ne doit pas sortir du service.
        (self.root / "media" / "autre-ecole.bin").write_bytes(b"prive-autre")
        Eleve.objects.create(ecole=self.autre, prenom="SECRET_AUTRE_ECOLE")
        DoubleFacteurCompte.objects.create(utilisateur=self.direction, cle_chiffree="TOTP_PRIVE")
        export = self.demande()
        produire(export)
        export.refresh_from_db()
        self.assertEqual(export.etat, "pret")
        self.assertEqual(export.mot_de_passe_local, "")
        self.assertTrue(export.compatible_pwa)
        archive = dossier(export) / "ecole.zip"
        preparation = preparer_restauration(archive, self.root)
        with ZipFile(archive) as z:
            manifeste = json.loads(z.read("manifest.json"))
            self.assertEqual(manifeste["export_ecole"]["perimetre"], "ecole_complete")
            self.assertNotIn("media/autre-ecole.bin", z.namelist())
        with sqlite3.connect(preparation.etape / "carnet.sqlite3") as db:
            self.assertEqual(db.execute("select nom from suivi_ecole").fetchall(), [("École fictive A",)])
            self.assertEqual(db.execute("select prenom from suivi_eleve").fetchall(), [("Fictif",)])
            comptes = dict((nom, (pwd, active, staff, admin)) for nom, pwd, active, staff, admin in
                db.execute("select username,password,is_active,is_staff,is_superuser from comptes_utilisateur"))
            self.assertTrue(check_password("Copie!Fictive2026", comptes["direction"][0]))
            self.assertFalse(check_password("Serveur!Fictif2026", comptes["direction"][0]))
            self.assertEqual(comptes["direction"][1:], (1, 0, 0))
            self.assertEqual(comptes["enseignant"], ("!", 0, 0, 0))
            self.assertEqual(db.execute("select count(*) from comptes_doublefacteurcompte").fetchone()[0], 0)
            self.assertEqual(db.execute("select count(*) from django_session").fetchone()[0], 0)
            self.assertEqual(db.execute("select count(*) from suivi_exportecole").fetchone()[0], 0)
            self.assertEqual(db.execute("select visible_carnet,commentaire from suivi_trace").fetchone(), (0, "Historique fictif"))
            self.assertEqual(db.execute("select origine_commune_id from suivi_trace").fetchone()[0], commune.pk)
            self.assertEqual(db.execute("select count(*) from suivi_choixecoleannuel_versions_autorisees").fetchone()[0], 1)
            self.assertEqual(db.execute("select historique_permissions from suivi_choixapplicationannuel").fetchone()[0], "[]")
            self.assertEqual(db.execute("select etat,empreinte_jeton from comptes_invitation").fetchone(), ("revoquee", ""))
            self.assertFalse(db.execute("pragma foreign_key_check").fetchall())
        self.direction.refresh_from_db()
        self.assertTrue(self.direction.check_password("Serveur!Fictif2026"))
        self.assertTrue(self.direction.is_superuser)
        self.assertTrue(Eleve.objects.filter(ecole=self.autre, prenom="SECRET_AUTRE_ECOLE").exists())

    def test_refus_relation_vers_une_autre_ecole(self):
        classe = Classe.objects.create(ecole=self.autre, nom="Privée", annee_scolaire="2026-2027")
        eleve = Eleve.objects.create(ecole=self.ecole, prenom="Fictif")
        Scolarite.objects.create(eleve=eleve, classe=classe, annee_scolaire="2026-2027", niveau="PS")
        export = self.demande()
        with self.assertRaisesMessage(ValidationError, "relation sort"):
            produire(export)
        self.assertFalse(dossier(export).exists())

    def test_permission_distincte_et_mode_local(self):
        url = reverse("exporter_ecole")
        self.assertEqual(self.client.get(url).status_code, 200)
        with override_settings(EXPORT_ECOLES=set()):
            self.assertEqual(self.client.get(url).status_code, 404)
        with override_settings(MODE_LOCAL=True):
            self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.prof)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_preparation_confirmee_et_une_seule_demande(self):
        donnees = {"action": "preparer", "mot_de_passe": "Serveur!Fictif2026",
            "mot_de_passe_local": "Copie!Fictive2026", "confirmation_locale": "Copie!Fictive2026", "confirme": "on"}
        self.assertEqual(self.client.post(reverse("exporter_ecole"), donnees).status_code, 302)
        self.assertEqual(ExportEcole.objects.count(), 1)
        self.assertContains(self.client.post(reverse("exporter_ecole"), donnees), "déjà")
        self.assertEqual(ExportEcole.objects.count(), 1)

    def test_csrf_et_mot_de_passe_distinct(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.direction)
        self.assertEqual(client.post(reverse("exporter_ecole"), {"action": "preparer"}).status_code, 403)
        response = self.client.post(reverse("exporter_ecole"), {"action": "preparer",
            "mot_de_passe": "Serveur!Fictif2026", "mot_de_passe_local": "Serveur!Fictif2026",
            "confirmation_locale": "Serveur!Fictif2026", "confirme": "on"})
        self.assertContains(response, "différent")
        self.assertFalse(ExportEcole.objects.exists())

    def pret(self):
        export = self.demande()
        export.etat = "pret"
        export.empreinte = "a" * 64
        export.taille_zip = 10
        export.save()
        dossier(export).mkdir()
        (dossier(export) / "ecole.zip").write_bytes(b"0123456789")
        session = self.client.session
        session["export_confirme"] = str(export.identifiant)
        session.save()
        return export, reverse("telecharger_export_ecole", args=[export.identifiant])

    def test_telechargement_reprise_et_if_range(self):
        export, url = self.pret()
        response = self.client.get(url, HTTP_RANGE="bytes=4-6", HTTP_IF_RANGE='"' + export.empreinte + '"')
        self.assertEqual(response.status_code, 206)
        self.assertEqual(b"".join(response.streaming_content), b"456")
        self.assertEqual(response["Content-Range"], "bytes 4-6/10")
        self.assertEqual(response["Content-Length"], "3")
        response = self.client.get(url, HTTP_RANGE="bytes=-2")
        self.assertEqual(b"".join(response.streaming_content), b"89")
        response = self.client.get(url, HTTP_RANGE="bytes=4-", HTTP_IF_RANGE='"ancien"')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"0123456789")
        self.assertEqual(self.client.head(url)["Content-Length"], "10")
        for valeur in ("bytes=10-", "bytes=0-2,4-6", "bytes=-0", "bytes=6-4"):
            self.assertEqual(self.client.get(url, HTTP_RANGE=valeur).status_code, 416)

    def test_reprise_refusee_apres_retrait_permission_ou_expiration(self):
        export, url = self.pret()
        with override_settings(EXPORT_ECOLES=set()):
            self.assertEqual(self.client.get(url, HTTP_RANGE="bytes=5-").status_code, 404)
        export.expire_le = timezone.now() - timedelta(seconds=1)
        export.save()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_aucun_acces_inter_ecoles_et_confirmation_requise(self):
        export, url = self.pret()
        session = self.client.session
        session.pop("export_confirme")
        session.save()
        self.assertEqual(self.client.get(url).status_code, 302)
        with override_settings(EXPORT_ECOLES={self.ecole.pk, self.autre.pk}):
            appartenance = AppartenanceEcole.objects.create(utilisateur=self.direction, ecole=self.autre)
            ResponsabiliteEcole.objects.create(appartenance=appartenance)
            session = self.client.session
            session["ecole_id"] = self.autre.pk
            session["export_confirme"] = str(export.identifiant)
            session.save()
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_worker_interruption_expiration_et_erreur_sans_secret(self):
        export = self.demande()
        with patch("suivi.management.commands.preparer_exports_ecoles.produire", side_effect=RuntimeError("SECRET")):
            call_command("preparer_exports_ecoles")
        export.refresh_from_db()
        self.assertEqual(export.etat, "echec")
        self.assertNotIn("SECRET", export.erreur)
        self.assertEqual(export.mot_de_passe_local, "")
        export.etat = "preparation"
        export.save()
        dossier(export).mkdir()
        call_command("preparer_exports_ecoles")
        export.refresh_from_db()
        self.assertEqual(export.etat, "echec")
        self.assertFalse(dossier(export).exists())

    def test_couverture_schema(self):
        verifier_couverture(selections(self.ecole.pk))

    def test_espace_insuffisant_avant_copie(self):
        export = self.demande()
        with patch("suivi.exports_ecole.shutil.disk_usage") as usage:
            usage.return_value.free = 0
            with self.assertRaisesMessage(ValidationError, "Espace temporaire"):
                produire(export)
        self.assertFalse(dossier(export).exists())
