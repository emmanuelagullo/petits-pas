"""Imports fictifs : identité neuve, projection annuelle et annulation complète."""
import hashlib
import io
import json
import sqlite3
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.db import connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from comptes.models import Utilisateur, AppartenanceEcole, AffectationClasse, ResponsabiliteEcole
from . import models as m
from .imports_ecole import verifier_zip
from .exports_ecole import produire, dossier
from . import tests_exports_classe
from .exports_classe import produire_classe


@override_settings(ENVIRONNEMENT_EPHEMERE=False, ENVIRONNEMENT_ATELIER=False)
class ImportEcoleTests(TransactionTestCase):
    def setUp(self):
        tests_exports_classe.ExportClasseTests.setUp(self)
        # Dans le ZIP d'école, seule la direction exportatrice reste active.
        AffectationClasse.objects.create(
            appartenance=AppartenanceEcole.objects.get(utilisateur=self.direction, ecole=self.ecole),
            classe=self.classe, type=AffectationClasse.RESPONSABLE)
        from .services.reprise_referentiels import preparer_nouvelle_ecole
        preparer_nouvelle_ecole(self.ecole)
        self.compte = Utilisateur.objects.create_user(username='nouvelle-direction', password='Nouveau!Fictif2026')
        self.ecole_source = self.ecole
        export = m.ExportEcole.objects.create(ecole=self.ecole, demande_par=self.direction,
            mot_de_passe_local='!', expire_le=timezone.now() + timedelta(hours=24))
        produire(export)
        self.archive = dossier(export) / 'ecole.zip'

    def importer(self, projection, nom='École importée fictive'):
        return projection.importer(self.compte, nom, 'Commune fictive', self.direction)

    def test_verification_seule_ne_modifie_rien_et_refuse_empreinte_differente(self):
        comptes = Utilisateur.objects.count()
        sortie = io.StringIO()
        call_command('importer_ecole_zip', str(self.archive), travail=str(self.root), stdout=sortie)
        self.assertIn('sha256', sortie.getvalue())
        self.assertEqual(m.Ecole.objects.count(), 2)
        self.assertEqual(Utilisateur.objects.count(), comptes)
        with self.assertRaisesMessage(CommandError, "L'empreinte diffère"):
            call_command('importer_ecole_zip', str(self.archive), travail=str(self.root), confirmer=True,
                sha256='0'*64, ecole='Fictive', direction=self.compte.username,
                operateur=self.direction.username, stdout=io.StringIO())
        self.assertEqual(m.Ecole.objects.count(), 2)

    def test_import_conserve_donnees_et_isole_ecoles_comptes_medias_et_json(self):
        avant = list(m.Trace.objects.order_by('pk').values())
        with verifier_zip(self.archive, self.root) as projection:
            ecole = self.importer(projection)
        self.assertNotEqual(ecole.pk, self.ecole_source.pk)
        self.assertEqual(m.Trace.objects.filter(observation__eleve__ecole=self.ecole_source).count(), 2)
        self.assertEqual(list(m.Trace.objects.filter(pk__in=[r['id'] for r in avant]).order_by('pk').values()), avant)
        nouvelle = m.Classe.objects.get(ecole=ecole, nom=self.classe.nom)
        self.assertEqual(nouvelle.etat, m.Classe.PREPARATION)
        self.assertFalse(AffectationClasse.objects.filter(classe__ecole=ecole).exists())
        self.assertEqual(list(AppartenanceEcole.objects.filter(ecole=ecole).values_list('utilisateur_id', flat=True)), [self.compte.pk])
        self.assertTrue(ResponsabiliteEcole.objects.filter(appartenance__ecole=ecole, type='direction').exists())
        trace = m.Trace.objects.get(observation__eleve__ecole=ecole, commentaire=self.trace.commentaire)
        self.assertNotEqual(trace.pk, self.trace.pk)
        self.assertNotEqual(trace.auteur_id, self.prof.pk)
        self.assertFalse(trace.auteur.is_active)
        self.assertEqual(trace.auteur.password, '!')
        self.assertEqual(trace.auteur.email, '')
        self.assertFalse(trace.auteur.is_staff or trace.auteur.is_superuser)
        self.assertTrue(trace.photo.name.startswith('imports/'))
        self.assertNotEqual(trace.photo.name, self.trace.photo.name)
        with trace.photo.open('rb') as f:
            self.assertEqual(f.read(), b'photo-de-realisation-fictive')
        adoption = m.AdoptionReferentiel.objects.get(classe=nouvelle, courante=True)
        contenu = adoption.version.contenu
        nouvelles_competences = set(m.Competence.objects.filter(domaine__ecole=ecole).values_list('pk', flat=True))
        self.assertEqual({c['id'] for c in contenu['competences']}, nouvelles_competences)
        for c in contenu['competences']:
            self.assertEqual(m.Domaine.objects.get(pk=c['domaine_id']).ecole_id, ecole.pk)
        self.assertFalse(m.ChoixApplicationAnnuel.objects.filter(versions_autorisees__source__ecole=ecole).exists())
        self.assertEqual(m.EvenementAudit.objects.filter(ecole=ecole).count(), 1)
        self.assertEqual(m.EvenementAudit.objects.get(ecole=ecole).action, 'ecole.import_zip')
        self.assertEqual(m.ExportEcole.objects.filter(ecole=ecole).count(), 0)
        self.assertTrue(self.compte.check_password('Nouveau!Fictif2026'))
        # Le deuxième appel est refusé sans écrasement.
        with verifier_zip(self.archive, self.root) as projection, self.assertRaises(ValidationError):
            self.importer(projection)
        with verifier_zip(self.archive, self.root) as projection:
            self.assertEqual(projection.rapport['deja_importe_ecoles'], [ecole.pk])
            with self.assertRaisesMessage(ValidationError, "Ce ZIP a déjà été importé"):
                self.importer(projection, nom='Doublon de copie fictive')
        self.assertEqual(m.Ecole.objects.count(), 3)

    def test_exception_copie_medias_annule_donnees_et_fichiers(self):
        comptes = Utilisateur.objects.count()
        with verifier_zip(self.archive, self.root) as projection:
            with patch('suivi.imports_ecole.shutil.copyfileobj', side_effect=OSError('panne fictive')):
                with self.assertRaises(OSError):
                    self.importer(projection)
        self.assertEqual(m.Ecole.objects.count(), 2)
        self.assertEqual(Utilisateur.objects.count(), comptes)
        self.assertFalse(list((self.root / 'media' / 'imports').glob('*')))

    def test_cloture_ajout_correspondance_et_presentations_remappes(self):
        from .services.ajouts_referentiels import creer_ajout
        from .services.correspondances_referentiels import relier_competences
        from .services.cloture_referentiels import clore
        adoption = m.AdoptionReferentiel.objects.get(classe=self.classe, courante=True)
        locale = creer_ajout(utilisateur=self.prof, ecole=self.ecole, annee=self.classe.annee_scolaire,
            classe=self.classe, adoption_attendue=adoption.pk, domaine_id=self.competence.domaine_id,
            libelle='Ajout pédagogique fictif', niveau='MS')
        lien = relier_competences(utilisateur=self.prof, ecole=self.ecole, annee=self.classe.annee_scolaire,
            classe=self.classe, adoption_attendue=adoption.pk,
            reference_depart=f'base:{adoption.version_id}:{self.competence.pk}',
            reference_arrivee=f'ajout:{locale.pk}', type_lien='lien', justification='Lien fictif')
        m.ReglagePresentation.objects.create(ecole=self.ecole, classe=self.classe,
            competence=self.competence, mode='remplacer', photo=self.trace.photo.name)
        m.FormulationLocale.objects.create(ecole=self.ecole, classe=self.classe,
            competence=self.competence, texte='Une formulation fictive')
        clore(utilisateur=self.prof, classe=self.classe)
        export = m.ExportEcole.objects.get(ecole=self.ecole)
        # Une nouvelle demande a un dossier distinct du ZIP déjà préparé.
        from uuid import uuid4
        export.identifiant = uuid4()
        export.save()
        produire(export)
        with verifier_zip(dossier(export) / 'ecole.zip', self.root) as projection:
            ecole = self.importer(projection)
        classe = m.Classe.objects.get(ecole=ecole, nom=self.classe.nom)
        finale = m.AdoptionReferentiel.objects.get(classe=classe, courante=True)
        ajout = m.CompetenceLocale.objects.get(ecole=ecole)
        nouvelle_competence = m.Competence.objects.get(domaine__ecole=ecole, code=self.competence.code)
        nouveau_lien = m.CorrespondanceCompetence.objects.get(ecole=ecole)
        self.assertEqual(nouveau_lien.reference_arrivee, f'ajout:{ajout.pk}')
        self.assertNotEqual(nouveau_lien.pk, lien.pk)
        self.assertEqual(finale.etat_final['correspondances'][0]['id'], nouveau_lien.pk)
        self.assertEqual(finale.etat_final['correspondances'][0]['origine_arrivee']['locale_id'], ajout.pk)
        image = finale.etat_final['illustrations'][str(nouvelle_competence.pk)]
        self.assertTrue(image['photo'].startswith('imports/'))
        self.assertEqual(m.RessourceReferentiel.objects.get(pk=image['ressource_id']).annuel.ecole_id, ecole.pk)
        proposition = finale.etat_final['propositions'][str(nouvelle_competence.pk)][-1]
        self.assertEqual(proposition['cle'], 'locale-' + str(m.FormulationLocale.objects.get(ecole=ecole).pk))
        from .referentiels import arbre_competences
        self.assertTrue(arbre_competences(ecole, classe=classe))

    def reecrire(self, sql=None, modifier=None):
        paquet = self.root / 'modifier.sqlite3'
        with ZipFile(self.archive) as z:
            fichiers = {n: z.read(n) for n in z.namelist()}
        paquet.write_bytes(fichiers['carnet.sqlite3'])
        with closing(sqlite3.connect(paquet)) as db, db:
            if sql:
                db.executescript(sql)
            if modifier:
                modifier(db)
        fichiers['carnet.sqlite3'] = paquet.read_bytes()
        manifeste = json.loads(fichiers['manifest.json'])
        manifeste['files']['carnet.sqlite3'] = hashlib.sha256(fichiers['carnet.sqlite3']).hexdigest()
        fichiers['manifest.json'] = json.dumps(manifeste).encode()
        cible = self.root / 'modifie.zip'
        with ZipFile(cible, 'w') as z:
            for n, data in fichiers.items():
                z.writestr(n, data)
        return cible

    def test_refus_de_schema_futur_declencheur_plusieurs_ecoles_et_json_inconnu(self):
        for sql in (
            "INSERT INTO django_migrations(app,name,applied) VALUES ('suivi','9999_future','2026-01-01');",
            "CREATE TRIGGER surprise AFTER UPDATE ON suivi_ecole BEGIN DELETE FROM suivi_trace; END;",
            "INSERT INTO suivi_ecole(nom,commune,etat,cree_le) VALUES('autre','', 'active','2026-01-01');",
            "UPDATE suivi_adoptionreferentiel SET etat_final='{\"structure_future\": 1}';",
        ):
            with self.subTest(sql=sql):
                archive = self.reecrire(sql)
                with self.assertRaises(ValidationError), verifier_zip(archive, self.root):
                    pass
        self.assertEqual(m.Ecole.objects.count(), 2)

    def test_refus_reference_json_invalide_et_media_absent(self):
        for sql in (
            "UPDATE suivi_referentielannuel SET etat_initial='{\"reglages\":[{\"id\":9999,\"photo\":\"\"}]}';",
            "UPDATE suivi_trace SET photo='traces/manquant.png';",
            "UPDATE suivi_trace SET photo='../hors-media.png';",
        ):
            with self.subTest(sql=sql):
                with self.assertRaises(ValidationError), verifier_zip(self.reecrire(sql), self.root):
                    pass

    def test_import_classe_preserve_etat_inconnu_sur_serveur(self):
        export = m.ExportClasse.objects.create(classe=self.classe, demande_par=self.prof,
            mot_de_passe_local='!', expire_le=timezone.now() + timedelta(hours=24))
        m.EtatAnnuelObservation.objects.filter(observation=self.obs).update(connu=False, statut=None, date_observation=None)
        future = m.Classe.objects.create(ecole=self.ecole, nom='Classe future fictive', annee_scolaire='2027-2028')
        m.Scolarite.objects.create(eleve=self.eleve, classe=future, annee_scolaire='2027-2028', niveau='GS')
        produire_classe(export)
        with verifier_zip(dossier(export) / 'ecole.zip', self.root) as projection:
            ecole = self.importer(projection)
        from .referentiels import observations_classe
        classe = m.Classe.objects.get(ecole=ecole)
        etat = observations_classe(classe).get(eleve__prenom=self.eleve.prenom, competence__code=self.competence.code)
        self.assertFalse(etat.connu_lecture)
        self.assertIsNone(etat.statut_lecture)
        # Une nouvelle saisie devient un état connu ordinaire.
        etat.statut = 'reussi'
        etat.save()
        self.assertTrue(observations_classe(classe).get(pk=etat.pk).connu_lecture)

    def test_commande_cree_direction_et_rollback_du_nouveau_compte(self):
        with verifier_zip(self.archive, self.root) as projection:
            somme = projection.rapport['sha256']
        options = dict(travail=str(self.root), confirmer=True, sha256=somme,
            ecole='École importée fictive', direction='direction-creee', creer_direction=True,
            prenom='Prénom fictif', nom='Nom fictif', operateur=self.direction.username,
            stdout=io.StringIO())
        with patch('suivi.management.commands.importer_ecole_zip.getpass', return_value='Nouveau!Personnel2026'):
            call_command('importer_ecole_zip', str(self.archive), **options)
        compte = Utilisateur.objects.get(username='direction-creee')
        self.assertTrue(compte.check_password('Nouveau!Personnel2026'))
        self.assertFalse(compte.is_staff or compte.is_superuser)
        options.update(ecole='Autre copie fictive', direction='direction-annulee')
        # Une nouvelle archive permet d'exercer la panne de stockage ; le même
        # ZIP serait désormais refusé comme import déjà réussi.
        nouvelle_archive = self.reecrire("UPDATE suivi_ecole SET nom='Nouvelle copie fictive';")
        with verifier_zip(nouvelle_archive, self.root) as projection:
            options['sha256'] = projection.rapport['sha256']
        with patch('suivi.management.commands.importer_ecole_zip.getpass', return_value='Nouveau!Personnel2026'), \
                patch('suivi.imports_ecole.shutil.copyfileobj', side_effect=OSError('panne fictive')):
            with self.assertRaises(CommandError):
                call_command('importer_ecole_zip', str(nouvelle_archive), **options)
        self.assertFalse(Utilisateur.objects.filter(username='direction-annulee').exists())

    def test_zip_sans_metadonnees_export_et_catalogue_public_intact(self):
        from .tests_import_sources_referentiels import importer, document
        from .services.versions_sources_ecoles import definir_version_ecole
        version, _, _ = importer(document())
        contenu = definir_version_ecole(self.ecole, version)
        adoption = m.AdoptionReferentiel.objects.get(classe=self.classe, courante=True)
        adoption.version = version
        adoption.contenu = contenu
        adoption.save()
        for c in contenu['competences']:
            m.UsageCompetence.objects.create(adoption=adoption, competence_id=c['id'],
                cle_definition=c['cle_definition'])
        original = version.contenu
        export = m.ExportEcole.objects.get(ecole=self.ecole)
        from uuid import uuid4
        export.identifiant = uuid4()
        export.save()
        produire(export)
        # Une sauvegarde ordinaire PWA/programme n'a pas de métadonnée export.
        with ZipFile(dossier(export) / 'ecole.zip') as z:
            fichiers = {n: z.read(n) for n in z.namelist()}
        manifeste = json.loads(fichiers['manifest.json'])
        manifeste.pop('export_ecole')
        fichiers['manifest.json'] = json.dumps(manifeste).encode()
        archive = self.root / 'sauvegarde-locale.zip'
        with ZipFile(archive, 'w') as z:
            for n, data in fichiers.items():
                z.writestr(n, data)
        with verifier_zip(archive, self.root) as projection:
            ecole = self.importer(projection)
        version.refresh_from_db()
        self.assertEqual(version.contenu, original)
        self.assertIsNone(version.source.ecole_id)
        nouvelle = m.AdoptionReferentiel.objects.get(classe__ecole=ecole, classe__nom=self.classe.nom)
        self.assertNotEqual(nouvelle.version_id, version.pk)
        self.assertEqual(nouvelle.version.source.ecole_id, ecole.pk)
        self.assertEqual(nouvelle.version.contenu, original)
        for ligne in nouvelle.contenu['competences']:
            self.assertEqual(m.Competence.objects.get(pk=ligne['id']).domaine.ecole_id, ecole.pk)
            identite = int(ligne['cle_definition'].removeprefix('source-'))
            self.assertEqual(m.IdentiteSourceCompetence.objects.get(pk=identite).source.ecole_id, ecole.pk)

    def test_mode_local_et_operateur_non_technique_refuses(self):
        with override_settings(MODE_LOCAL=True), self.assertRaises(ValidationError), verifier_zip(self.archive, self.root):
            pass
        with verifier_zip(self.archive, self.root) as projection, self.assertRaises(ValidationError):
            projection.importer(self.compte, 'Fictive', '', self.prof)
        self.assertEqual(m.Ecole.objects.count(), 2)
