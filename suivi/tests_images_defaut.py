"""Images illustratives et photos : aucun arbitrage entre photos de traces."""
from datetime import date
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import override_settings
from django.urls import reverse

from .models import Classe, Competence, Ecole, Observation, ReglagePresentation
from .presentation import affichage_avec_photos
from .services.cloture_referentiels import clore
from .services.presentation import enregistrer_affichage, enregistrer_reglage
from .services.reprise_referentiels import reprendre
from .services.traces_communes import enregistrer_commune, personnaliser
from .tests import Base
from .tests_presentation import image_fictive


class ImagesDefaut(Base):
    def setUp(self):
        super().setUp()
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.reglages = override_settings(MEDIA_ROOT=self.media.name)
        self.reglages.enable()
        self.addCleanup(self.reglages.disable)
        self.competence.icone = "om-plante"
        self.competence.save()
        self.client.force_login(self.enseignant)

    def carnet(self, **options):
        return self.client.get(reverse("carnet", args=[self.eleve.pk]), {"contenu": "tout", **options})

    def test_sans_photo_illustration_avec_credit_unique(self):
        page = self.carnet()
        self.assertContains(page, 'class="icone-competence"', count=1)
        self.assertContains(page, '>OpenMoji</a>', count=1)
        self.assertContains(page, 'CC BY-SA 4.0', count=1)
        self.assertFalse(page.context['ecole'].illustration_avec_photos)
        Competence.objects.create(domaine=self.competence.domaine, code='FICTIF-02',
            libelle='Autre activité fictive', icone='om-crayon')
        page = self.carnet()
        self.assertContains(page, 'class="icone-competence"', count=2)
        self.assertContains(page, '>OpenMoji</a>', count=1)

    def test_photos_collective_et_personnelle_restent_toutes_les_deux(self):
        commune = enregistrer_commune(utilisateur=self.enseignant, classe=self.classe,
            competence=self.competence, ids=[self.eleve.pk], valeurs={
                "date_observation": date(2026, 10, 1), "photo": image_fictive('collective.png')})
        obs = Observation.objects.get(eleve=self.eleve, competence=self.competence)
        personnelle = self.creer_trace(observation=obs, date_observation=date(2026, 10, 2),
            photo=image_fictive('personnelle.png'))
        # La dernière trace sans photo ne doit pas cacher les photos antérieures.
        self.creer_trace(observation=obs, date_observation=date(2026, 10, 3), commentaire="Sans photo")
        page = self.carnet()
        self.assertContains(page, 'class="trace-photo"', count=2)
        self.assertNotContains(page, 'class="icone-competence"')
        self.assertNotContains(page, '>OpenMoji</a>')
        enregistrer_affichage(self.enseignant, self.ecole, self.classe, avec_photos=True)
        page = self.carnet()
        self.assertContains(page, 'class="trace-photo"', count=2)
        self.assertContains(page, 'class="icone-competence"', count=1)
        personnelle.refresh_from_db()
        self.assertTrue(personnelle.photo)
        self.assertTrue(commune.attributions.get().photo)

    def test_version_personnelle_sans_photo_ne_reprend_pas_celle_du_groupe(self):
        commune = enregistrer_commune(utilisateur=self.enseignant, classe=self.classe,
            competence=self.competence, ids=[self.eleve.pk], valeurs={
                "date_observation": date(2026, 10, 1), "photo": image_fictive()})
        trace = personnaliser(utilisateur=self.enseignant, trace=commune.attributions.get())
        trace.photo = None
        trace.save(update_fields=['photo'])
        page = self.carnet()
        self.assertContains(page, 'class="icone-competence"')
        self.assertNotContains(page, 'class="trace-photo"')

    def test_photos_masquees_retirees_et_hors_annee_ne_comptent_pas(self):
        from .models import AccesParcoursEleve, DemandeRapprochementEleve, Scolarite
        from django.utils import timezone
        obs = Observation.objects.create(eleve=self.eleve, competence=self.competence)
        self.creer_trace(observation=obs, photo=image_fictive('cachee.png'), visible_carnet=False)
        self.creer_trace(observation=obs, photo=image_fictive('retiree.png'), supprime_le=timezone.now())
        ancienne = Classe.objects.create(ecole=self.ecole, nom='Classe passée', annee_scolaire='2025-2026')
        sc = Scolarite.objects.create(eleve=self.eleve, classe=ancienne, annee_scolaire='2025-2026', niveau='PS')
        self.creer_trace(observation=obs, scolarite=sc, photo=image_fictive('ancienne.png'))
        self.assertContains(self.carnet(), 'class="icone-competence"')
        demande = DemandeRapprochementEleve.objects.create(ecole=self.ecole, classe=self.classe,
            prenom_propose='Lou', niveau_propose='PS', demande_par=self.enseignant,
            eleve_retenu=self.eleve, etat='validee')
        AccesParcoursEleve.objects.create(demande=demande, eleve=self.eleve,
            classe=self.classe, valide_par=self.direction)
        self.assertNotContains(self.carnet(), 'class="icone-competence"')
        self.assertContains(self.carnet(annee='2026-2027'), 'class="icone-competence"')

    def test_heritage_ecole_classe_et_desactivation_independante(self):
        enregistrer_affichage(self.direction, self.ecole, avec_photos=True)
        self.ecole.refresh_from_db()
        self.assertTrue(affichage_avec_photos(self.ecole, self.classe))
        self.classe = enregistrer_affichage(self.enseignant, self.ecole, self.classe, avec_photos=False)
        self.assertFalse(affichage_avec_photos(self.ecole, self.classe))
        self.classe = enregistrer_affichage(self.enseignant, self.ecole, self.classe, avec_photos=None)
        self.assertTrue(affichage_avec_photos(self.ecole, self.classe))
        enregistrer_reglage(self.enseignant, ReglagePresentation(ecole=self.ecole, classe=self.classe,
            competence=self.competence, mode='desactiver'))
        self.assertNotContains(self.carnet(), 'class="icone-competence"')
        enregistrer_reglage(self.direction, ReglagePresentation(ecole=self.ecole,
            competence=self.competence, mode='remplacer', icone='livre'))
        self.assertNotContains(self.carnet(), 'class="icone-competence"')

    def test_interface_droits_validation_et_retour_heritage(self):
        url = reverse('presentation_classe', args=[self.classe.pk])
        self.assertContains(self.client.get(url), 'Images proposées et photos')
        for choix, attendu in [('avec_photos', True), ('sans_photo', False), ('heriter', None)]:
            self.assertEqual(self.client.post(url, {'action': 'affichage', 'choix': choix}).status_code, 302)
            self.classe.refresh_from_db()
            self.assertIs(self.classe.illustration_avec_photos, attendu)
        page = self.client.post(url, {'action': 'affichage', 'choix': 'incorrect'})
        self.assertContains(page, "Vérifiez le choix d&#x27;affichage.")
        self.assertEqual(self.client.post(reverse('presentation_ecole'),
            {'action': 'affichage', 'choix': 'avec_photos'}).status_code, 403)
        autre = Ecole.objects.create(nom='Autre école fictive')
        autre_classe = Classe.objects.create(ecole=autre, nom='Autre classe')
        with self.assertRaises(PermissionDenied):
            enregistrer_affichage(self.direction, self.ecole, autre_classe, avec_photos=True)
        with self.assertRaises(ValueError):
            affichage_avec_photos(self.ecole, autre_classe)

    def test_cloture_fige_regle_et_credit_et_ancien_instantane_reste_lisible(self):
        self.creer_trace(photo=image_fictive())
        self.ecole.illustration_avec_photos = True
        self.ecole.save()
        reprendre(self.ecole.pk)
        self.classe.refresh_from_db()
        adoption = clore(utilisateur=self.enseignant, classe=self.classe)
        self.assertTrue(adoption.etat_final['illustration_avec_photos'])
        self.assertEqual(adoption.etat_final['illustrations'][str(self.competence.pk)]['credit'], 'openmoji')
        Ecole.objects.filter(pk=self.ecole.pk).update(illustration_avec_photos=False)
        self.assertContains(self.carnet(), 'class="icone-competence"')
        with self.assertRaises(PermissionDenied):
            enregistrer_affichage(self.enseignant, self.ecole, self.classe, avec_photos=False)
        # Ancien format : le fichier figé est identifié par ses octets.
        del adoption.etat_final['illustration_avec_photos']
        del adoption.etat_final['illustrations'][str(self.competence.pk)]['credit']
        adoption.save(update_fields=['etat_final'])
        page = self.carnet()
        self.assertContains(page, 'class="icone-competence"')
        self.assertContains(page, '>OpenMoji</a>', count=1)

    def test_web_et_pdf_partagent_affichage_et_credits_sans_reseau(self):
        self.creer_trace(photo=image_fictive())
        from .views import _generer_pdf
        with patch('suivi.views._generer_pdf', wraps=_generer_pdf) as generer:
            pdf = self.client.get(reverse('carnet_pdf', args=[self.eleve.pk]))
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b'%PDF'))
        html = generer.call_args.args[0]
        self.assertNotIn('class="icone-competence"', html)
        self.assertIn('class="trace-photo"', html)
        self.assertNotIn('>OpenMoji</a>', html)
        enregistrer_affichage(self.enseignant, self.ecole, self.classe, avec_photos=True)
        with patch('suivi.views._generer_pdf', wraps=_generer_pdf) as generer:
            pdf = self.client.get(reverse('carnet_pdf', args=[self.eleve.pk]))
        self.assertEqual(pdf.status_code, 200)
        html = generer.call_args.args[0]
        self.assertIn('class="icone-competence"', html)
        self.assertEqual(html.count('>OpenMoji</a>'), 1)
        self.assertNotIn('src="https://', html)
