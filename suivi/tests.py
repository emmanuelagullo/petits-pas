import hashlib
import os
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Classe, Competence, Domaine, Ecole, Eleve, Observation


class Base(TestCase):
    def setUp(self):
        self.ecole = Ecole(nom="Les Tilleuls")
        self.ecole.definir_mots_de_passe("ens-mdp", "dir-mdp")
        self.ecole.save()
        self.classe = Classe.objects.create(ecole=self.ecole, nom="PS-MS")
        self.eleve = Eleve.objects.create(classe=self.classe, prenom="Lou", niveau="PS")
        domaine = Domaine.objects.create(ecole=self.ecole, code="LANG", nom="Langage")
        self.competence = Competence.objects.create(
            domaine=domaine, code="LANG-01", libelle="Je dis mon prénom", niveau="PS"
        )

    def entrer(self, mdp="ens-mdp"):
        return self.client.post(reverse("connexion"), {"mot_de_passe": mdp})


class Acces(Base):
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
        eleve = Eleve.objects.create(
            classe=Classe.objects.create(ecole=autre, nom="GS"), prenom="Zoé"
        )
        url = reverse("basculer", args=[eleve.pk, self.competence.pk])
        self.assertEqual(self.client.post(url).status_code, 404)

    def test_le_changement_de_statut_conserve_la_trace(self):
        obs = Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
            statut=Observation.REUSSI,
            commentaire="Une première réussite",
            photo="traces/test.jpg",
        )

        self.client.post(self.url)
        self.client.post(self.url)

        obs.refresh_from_db()
        self.assertEqual(obs.statut, Observation.NON_DEBUTE)
        self.assertEqual(obs.commentaire, "Une première réussite")
        self.assertEqual(obs.photo.name, "traces/test.jpg")


class Carnet(Base):
    def test_la_couverture_identifie_le_carnet(self):
        self.entrer()

        r = self.client.get(reverse("carnet", args=[self.eleve.pk]))

        self.assertContains(r, "Carnet de suivi des apprentissages")
        self.assertContains(r, self.ecole.nom)
        self.assertContains(r, self.classe.nom)
        self.assertContains(r, self.eleve.get_niveau_display())
        self.assertContains(r, self.classe.annee_scolaire)

    def test_le_carnet_ne_montre_par_defaut_que_les_reussites(self):
        self.entrer()
        url = reverse("carnet", args=[self.eleve.pk])
        self.assertNotContains(self.client.get(url), "Je dis mon prénom")

        observation = Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
            statut=Observation.EN_COURS,
        )
        self.assertNotContains(self.client.get(url), "Je dis mon prénom")

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

    def test_une_reussite_montre_sa_date_et_son_commentaire(self):
        self.entrer()
        Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
            statut=Observation.REUSSI,
            date_observation="2026-09-16",
            commentaire="Lou a raconté son arrivée à l'école.",
        )

        r = self.client.get(reverse("carnet", args=[self.eleve.pk]))

        self.assertContains(r, "Observé le 16 septembre 2026")
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

    def test_un_mode_inconnu_revient_aux_reussites(self):
        self.entrer()
        Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
            statut=Observation.EN_COURS,
        )
        r = self.client.get(
            reverse("carnet", args=[self.eleve.pk]), {"contenu": "inconnu"}
        )
        self.assertNotContains(r, "Je dis mon prénom")


class IndicateursTrace(Base):
    def setUp(self):
        super().setUp()
        self.entrer()

    def page_eleve(self):
        return self.client.get(reverse("saisie_eleve", args=[self.eleve.pk]))

    def test_un_commentaire_est_signale_par_un_crayon(self):
        Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
            commentaire="Une remarque",
        )

        r = self.page_eleve()

        self.assertContains(r, 'class="indicateur-commentaire"')
        self.assertNotContains(r, 'class="indicateur-photo"')

    def test_une_photo_est_signalee_independamment_du_commentaire(self):
        Observation.objects.create(
            eleve=self.eleve,
            competence=self.competence,
            commentaire="Une remarque",
            photo="traces/test.jpg",
        )

        r = self.page_eleve()

        self.assertContains(r, 'class="indicateur-commentaire"')
        self.assertContains(r, 'class="indicateur-photo"')


class Import(Base):
    def test_coller_une_liste_cree_les_eleves(self):
        self.entrer("dir-mdp")
        self.client.post(
            reverse("importer_eleves", args=[self.classe.pk]),
            {"liste": "Camille\nSofiane ; Benali ; MS\n\n  Lou  ", "niveau": "PS"},
        )
        noms = set(self.classe.eleves.values_list("prenom", flat=True))
        self.assertEqual(noms, {"Lou", "Camille", "Sofiane"})
        self.assertEqual(self.classe.eleves.get(prenom="Sofiane").niveau, "MS")
        self.assertEqual(self.classe.eleves.get(prenom="Camille").niveau, "PS")


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

    def test_refuse_un_profil_incomplet_quand_le_persistant_est_exige(self):
        with self.assertRaises(CommandError):
            call_command(
                "diagnostiquer_deploiement",
                "--exiger-persistant",
                stdout=StringIO(),
                stderr=StringIO(),
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
            Observation.objects.create(
                eleve=self.eleve,
                competence=self.competence,
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
            Observation.objects.create(
                eleve=self.eleve,
                competence=self.competence,
                photo="traces/absente.jpg",
            )

            with self.assertRaises(CommandError):
                call_command(
                    "verifier_reprise_restauree",
                    stdout=StringIO(),
                )
