from tempfile import TemporaryDirectory
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings
from .models import AdoptionReferentiel, CorrespondanceCompetence, EtatAnnuelObservation, Observation, Trace, UsageCompetence
from .correspondances_referentiels import correspondances_classe
from .services.correspondances_referentiels import catalogue_liens, relier_competences, retirer_correspondance
from .services.cloture_referentiels import clore
from .services.pedagogie import modifier_etat
from . import tests_adoption_bases_referentiels as fixtures
from .tests import Base


class Correspondances(Base):
    def setUp(self):
        super().setUp()
        from .services.reprise_referentiels import reprendre
        from .services.choix_bases_referentiels import publier_choix_application
        from .tests_import_sources_referentiels import document, importer
        reprendre(self.ecole.pk)
        self.a = importer(document())[0]
        self.b = importer(document("autre-fictive"))[0]
        publier_choix_application(annee=self.classe.annee_scolaire, versions_ids=[self.a.pk, self.b.pk],
            proposee_id=self.a.pk, revision_attendue=0)
        self.entrer()
        self.adopter(self.a)
        self.adoption = self.adopter(self.b)
        self.annee = self.classe.annee_scolaire
        self.catalogue = catalogue_liens(utilisateur=self.enseignant, ecole=self.ecole, annee=self.annee, classe=self.classe)
        self.ra = next(r for r, c in self.catalogue.items() if c["version_id"] == self.a.pk)
        self.rb = next(r for r, c in self.catalogue.items() if c["version_id"] == self.b.pk)

    adopter = fixtures.AdoptionBases.adopter

    def relier(self, depart=None, arrivee=None, type_lien="lien", ecole=False, **options):
        return relier_competences(utilisateur=self.direction if ecole else self.enseignant, ecole=self.ecole,
            annee=self.annee, classe=None if ecole else self.classe,
            adoption_attendue=None if ecole else self.adoption.pk,
            reference_depart=depart or self.rb, reference_arrivee=arrivee or self.ra,
            type_lien=type_lien, justification="Rapprochement fictif à discuter en équipe.", **options)

    def test_liens_orientes_multiples_sans_transfert_ni_symetrie(self):
        from .models import Competence
        competence = Competence.objects.get(pk=self.catalogue[self.rb]["competence_id"])
        modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=competence, statut="reussi")
        avant = {m: list(m.objects.values()) for m in (Observation, EtatAnnuelObservation, Trace, UsageCompetence)}
        for type_lien in ("lien", "precise", "remplace"):
            lien = self.relier(type_lien=type_lien)
            self.assertEqual(lien.depart_id, competence.pk)
        self.assertEqual(CorrespondanceCompetence.objects.count(), 3)
        for model, valeurs in avant.items(): self.assertEqual(list(model.objects.values()), valeurs)
        self.assertEqual(len(correspondances_classe(self.classe, competence.pk)), 3)
        with self.assertRaises(ValidationError): self.relier()
        self.assertFalse(CorrespondanceCompetence.objects.filter(depart_id=self.catalogue[self.ra]["competence_id"]).exists())

    def test_cycles_school_et_classe_et_retrait_reversible_sans_effacer(self):
        premier = self.relier(type_lien="remplace", ecole=True)
        with self.assertRaises(ValidationError): self.relier(depart=self.ra, arrivee=self.rb, type_lien="remplace")
        # La boucle est aussi refusée si le lien d'école est ajouté après celui de classe.
        retirer_correspondance(utilisateur=self.direction, ecole=self.ecole, annee=self.annee,
            lien_id=premier.pk, revision_attendue=0)
        self.relier(depart=self.ra, arrivee=self.rb, type_lien="remplace")
        with self.assertRaises(ValidationError): self.relier(type_lien="remplace", ecole=True)
        premier.refresh_from_db()
        self.assertFalse(premier.active)
        self.assertEqual(premier.revision, 1)
        self.assertIsNotNone(premier.retire_le)
        with self.assertRaises(ValidationError):
            retirer_correspondance(utilisateur=self.direction, ecole=self.ecole, annee=self.annee,
                lien_id=premier.pk, revision_attendue=0)

    def test_pas_vers_soi_meme_autre_version_et_liens_locaux(self):
        with self.assertRaises(ValidationError): self.relier(depart=self.ra, arrivee=self.ra)
        from .services.ajouts_referentiels import creer_ajout
        locale = creer_ajout(utilisateur=self.enseignant, ecole=self.ecole, annee=self.annee,
            classe=self.classe, adoption_attendue=self.adoption.pk,
            domaine_id=self.adoption.contenu["domaines"][0]["id"], libelle="Je parle", niveau="PS")
        lien = self.relier(depart=f"ajout:{locale.pk}", type_lien="precise")
        self.assertEqual(lien.depart_id, locale.competence_id)
        self.assertNotEqual(lien.depart_id, lien.arrivee_id)
        self.assertEqual(lien.origine_depart["locale_id"], locale.pk)
        self.assertIsNone(lien.version_depart)
        self.assertFalse(Observation.objects.exists())

    def test_cloture_fixe_liens_et_origines_puis_annee_suivante_vide(self):
        lien = self.relier(ecole=True)
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            finale = clore(utilisateur=self.enseignant, classe=self.classe)
        avant = correspondances_classe(self.classe)
        retirer_correspondance(utilisateur=self.direction, ecole=self.ecole, annee=self.annee,
            lien_id=lien.pk, revision_attendue=0)
        self.assertEqual(correspondances_classe(self.classe), avant)
        self.assertEqual(finale.etat_final["correspondances"], avant)
        with self.assertRaises(ValidationError): self.relier()
        from .models import Classe
        nouvelle = Classe.objects.create(ecole=self.ecole, nom="Nouvelle classe fictive", annee_scolaire="2027-2028")
        self.assertEqual(correspondances_classe(nouvelle), [])
        lien.justification = "Justification réécrite"
        with self.assertRaises(ValidationError): lien.save()

    def test_droits_perimetres_contexte_et_catalogue_lecture_seule(self):
        avant = CorrespondanceCompetence.objects.count()
        self.assertEqual(catalogue_liens(utilisateur=self.enseignant, ecole=self.ecole, annee=self.annee,
            classe=self.classe), self.catalogue)
        self.assertEqual(CorrespondanceCompetence.objects.count(), avant)
        with self.assertRaises(PermissionDenied):
            catalogue_liens(utilisateur=self.enseignant, ecole=self.ecole, annee=self.annee)
        with self.assertRaises(PermissionDenied): self.relier(depart="base:99999:99999")
        lien = self.relier(ecole=True)
        with self.assertRaises(PermissionDenied):
            retirer_correspondance(utilisateur=self.enseignant, ecole=self.ecole, annee=self.annee,
                classe=self.classe, adoption_attendue=self.adoption.pk, lien_id=lien.pk, revision_attendue=0)
        with self.assertRaises(ValidationError):
            relier_competences(utilisateur=self.enseignant, ecole=self.ecole, annee=self.annee, classe=self.classe,
                adoption_attendue=-1, reference_depart=self.ra, reference_arrivee=self.rb,
                type_lien="lien", justification="Fictif")

    def test_cycle_long_et_classes_separees(self):
        from .models import Classe
        from .services.ajouts_referentiels import creer_ajout
        locale = creer_ajout(utilisateur=self.direction, ecole=self.ecole, annee=self.annee,
            domaine_id=self.adoption.contenu["domaines"][0]["id"], libelle="Un troisième apprentissage fictif", niveau="PS")
        rc = f"ajout:{locale.pk}"
        self.relier(type_lien="remplace")
        self.relier(depart=self.ra, arrivee=rc, type_lien="remplace", ecole=True)
        with self.assertRaises(ValidationError): self.relier(depart=rc, arrivee=self.rb, type_lien="remplace")
        autre = Classe.objects.create(ecole=self.ecole, nom="Autre classe fictive", annee_scolaire=self.annee)
        adoption = AdoptionReferentiel.objects.create(classe=autre, annuel=self.adoption.annuel,
            version=self.adoption.version, contenu=self.adoption.contenu)
        lien = relier_competences(utilisateur=self.direction, ecole=self.ecole, annee=self.annee,
            classe=autre, adoption_attendue=adoption.pk, reference_depart=self.ra, reference_arrivee=self.rb,
            type_lien="remplace", justification="Dans cette autre classe fictive.")
        self.assertEqual(lien.classe_id, autre.pk)
        # Les chemins privés de deux classes ne sont pas combinés pour inventer un cycle.
        self.assertEqual(CorrespondanceCompetence.objects.filter(active=True).count(), 3)
