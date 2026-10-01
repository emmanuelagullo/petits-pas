from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from .models import (AdoptionReferentiel, ChoixApplicationAnnuel, ChoixEcoleAnnuel,
                     Classe, EtatAnnuelObservation, Observation, PermissionChangementClasse)
from .tests import Base
from .tests_import_sources_referentiels import document, importer
from .services.reprise_referentiels import reprendre
from .services.choix_bases_referentiels import publier_choix_application
from .services.adoption_bases_referentiels import apercu_adoption, adopter_base
from .services.garde_fous_referentiels import (permissions, regler_permission,
                                              regler_permission_application, saisies_classe)
from .services.pedagogie import modifier_etat


class GardeFous(Base):
    def setUp(self):
        super().setUp()
        reprendre(self.ecole.pk)
        self.a = importer(document())[0]
        self.b = importer(document("autre-base-fictive"))[0]
        publier_choix_application(annee=self.classe.annee_scolaire, versions_ids=[self.a.pk, self.b.pk],
                                 proposee_id=self.a.pk, revision_attendue=0)
        self.adopter(self.a)
        self.competence = AdoptionReferentiel.objects.get(classe=self.classe, courante=True).usages.get().competence
        self.entrer()

    def apercu(self, version=None):
        return apercu_adoption(utilisateur=self.enseignant, classe=self.classe, version_id=(version or self.b).pk)

    def appliquer(self, apercu):
        return adopter_base(utilisateur=self.enseignant, classe=self.classe, version_id=apercu["version"].pk,
            adoption_attendue=apercu["adoption_id"], revisions_attendues=apercu["revisions"],
            garde_attendue=apercu["garde"]["empreinte"])

    def adopter(self, version):
        return self.appliquer(self.apercu(version))

    def saisir(self):
        modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=self.competence, statut="reussi")

    def permission(self, ouverte=True, classe=False, utilisateur=None):
        return regler_permission(utilisateur=utilisateur or (self.enseignant if classe else self.direction),
            ecole=self.ecole, annee=self.classe.annee_scolaire, classe=self.classe if classe else None,
            ouverte=ouverte, empreinte_attendue=permissions(self.ecole, self.classe.annee_scolaire,
                                                           self.classe if classe else None)["empreinte"])

    def application(self, ouverte=True):
        regle = ChoixApplicationAnnuel.objects.get(annee_scolaire=self.classe.annee_scolaire)
        return regler_permission_application(annee=regle.annee_scolaire, ouverte=ouverte,
                                            revision_attendue=regle.revision, confirmer=True)

    def ouvrir(self):
        self.application()
        self.permission()
        self.permission(classe=True)

    def test_seuil_saisies_et_refus_aux_trois_niveaux(self):
        self.assertEqual(self.apercu()["garde"]["niveau"], "orange")
        self.assertFalse(PermissionChangementClasse.objects.exists())
        self.saisir()
        self.assertEqual(self.apercu()["garde"]["niveau"], "rouge")
        for ouvrir in (self.application, self.permission, lambda: self.permission(classe=True)):
            with self.assertRaises(ValidationError):
                self.appliquer(self.apercu())
            ouvrir()
        etats = list(EtatAnnuelObservation.objects.values())
        observations = list(Observation.objects.values())
        self.appliquer(self.apercu())
        self.assertEqual(list(EtatAnnuelObservation.objects.values()), etats)
        self.assertEqual(list(Observation.objects.values()), observations)
        self.assertFalse(PermissionChangementClasse.objects.get(classe=self.classe).ouverte)
        with self.assertRaises(ValidationError):
            self.adopter(self.a)

    def test_pas_de_depassement_du_niveau_superieur_ni_du_role(self):
        with self.assertRaises(ValidationError): self.permission()
        with self.assertRaises(ValidationError): self.permission(classe=True)
        self.application()
        with self.assertRaises(PermissionDenied): self.permission(utilisateur=self.enseignant)
        self.permission()
        self.permission(classe=True)
        self.application(False)
        self.assertFalse(permissions(self.ecole, self.classe.annee_scolaire, self.classe)["effective"])
        # Fermer reste possible lorsque le supérieur a retiré sa permission.
        self.permission(False, classe=True)
        self.permission(False)

    def test_premiere_saisie_apres_apercu_refuse_confirmation_orange(self):
        ancien = self.apercu()
        self.saisir()
        self.ouvrir()
        with self.assertRaises(ValidationError): self.appliquer(ancien)
        self.assertEqual(AdoptionReferentiel.objects.get(classe=self.classe, courante=True).version_id, self.a.pk)

    def test_retrait_ecole_et_confirmation_perimee(self):
        self.saisir()
        self.ouvrir()
        ancien = self.apercu()
        self.permission(False)
        with self.assertRaises(ValidationError): self.appliquer(ancien)
        with self.assertRaises(ValidationError): self.appliquer(self.apercu())
        self.assertTrue(PermissionChangementClasse.objects.get(classe=self.classe).ouverte)

    def test_meme_base_ne_consomme_pas_exception(self):
        self.saisir()
        self.ouvrir()
        self.adopter(self.a)
        self.assertTrue(PermissionChangementClasse.objects.get(classe=self.classe).ouverte)

    def test_trace_supprimee_et_eleve_deplace_restent_des_saisies(self):
        trace = self.creer_trace()
        trace.usage_referentiel = AdoptionReferentiel.objects.get(classe=self.classe, courante=True).usages.get()
        from django.utils import timezone
        trace.supprime_le = timezone.now()
        trace.visible_carnet = False
        trace.save()
        from .models import Scolarite
        autre = Classe.objects.create(ecole=self.ecole, nom="Autre classe fictive", annee_scolaire=self.classe.annee_scolaire)
        Scolarite.objects.filter(eleve=self.eleve, classe=self.classe).update(classe=autre)
        self.assertTrue(saisies_classe(self.classe)["presentes"])

    def test_etat_sans_annee_connue_est_signale(self):
        Observation.objects.create(eleve=self.eleve, competence=self.competence)
        self.assertTrue(saisies_classe(self.classe)["ambigu"])
        self.assertEqual(self.apercu()["garde"]["niveau"], "rouge")

    def test_permissions_non_reconduites_a_la_nouvelle_annee(self):
        self.ouvrir()
        prochaine = Classe.objects.create(ecole=self.ecole, nom="Lucioles fictives", annee_scolaire="2027-2028")
        self.assertFalse(permissions(self.ecole, prochaine.annee_scolaire, prochaine)["effective"])
        self.assertFalse(saisies_classe(prochaine)["presentes"])

    def test_commande_exige_confirmation_et_journalise_application(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from io import StringIO
        with self.assertRaises(CommandError):
            call_command("regler_changements_referentiels", annee=self.classe.annee_scolaire,
                         ouvrir=True, revision_attendue=1, stdout=StringIO())
        regle = self.application()
        self.assertEqual(regle.historique_permissions[-1]["apres"], True)
        self.assertEqual(regle.revision, 2)

    def test_confirmation_orange_exige_mot_de_passe_sans_changer_les_donnees(self):
        url = reverse("referentiel_classe", args=[self.classe.pk])
        page = self.client.post(url, {"action": "apercu", "version": self.b.pk})
        self.assertContains(page, "Votre mot de passe")
        jeton = page.context["jeton"]
        avant = AdoptionReferentiel.objects.count()
        for mdp in ("", "mot-de-passe-errone"):
            self.assertEqual(self.client.post(url, {"action": "confirmer", "jeton": jeton, "mot_de_passe": mdp}).status_code, 400)
        self.assertEqual(AdoptionReferentiel.objects.count(), avant)
        self.assertEqual(self.client.post(url, {"action": "confirmer", "jeton": jeton, "mot_de_passe": "ens-mdp"}).status_code, 302)

    def test_ouvertures_et_changement_rouge_demandent_chacun_le_mot_de_passe(self):
        self.saisir()
        self.application()
        self.client.logout()
        self.entrer("dir-mdp")
        ecole = reverse("permissions_referentiels_ecole")
        page = self.client.get(ecole, {"annee": self.classe.annee_scolaire})
        jeton = page.context["jeton"]
        post = {"annee": self.classe.annee_scolaire, "action": "confirmer", "jeton": jeton}
        self.assertEqual(self.client.post(ecole, post).status_code, 400)
        self.assertEqual(self.client.post(ecole, {**post, "mot_de_passe": "dir-mdp"}).status_code, 302)
        self.client.logout()
        self.entrer()
        classe = reverse("permissions_referentiels_classe", args=[self.classe.pk])
        jeton = self.client.get(classe).context["jeton"]
        post = {"action": "confirmer", "jeton": jeton}
        self.assertEqual(self.client.post(classe, post).status_code, 400)
        self.assertEqual(self.client.post(classe, {**post, "mot_de_passe": "ens-mdp"}).status_code, 302)
        url = reverse("referentiel_classe", args=[self.classe.pk])
        page = self.client.post(url, {"action": "apercu", "version": self.b.pk})
        self.assertContains(page, "Avertissement majeur")
        jeton = page.context["jeton"]
        self.assertEqual(self.client.post(url, {"action": "confirmer", "jeton": jeton}).status_code, 400)
        self.assertEqual(self.client.post(url, {"action": "confirmer", "jeton": jeton, "mot_de_passe": "ens-mdp"}).status_code, 302)
        self.assertFalse(PermissionChangementClasse.objects.get(classe=self.classe).ouverte)

    def test_ouverture_signee_expire_et_ne_peut_servir_a_une_autre_classe(self):
        from unittest.mock import patch
        self.application()
        self.permission()
        url = reverse("permissions_referentiels_classe", args=[self.classe.pk])
        jeton = self.client.get(url).context["jeton"]
        post = {"action": "confirmer", "jeton": jeton, "mot_de_passe": "ens-mdp"}
        with patch("django.core.signing.time.time", return_value=9999999999):
            self.assertEqual(self.client.post(url, post).status_code, 400)
        autre = Classe.objects.create(ecole=self.ecole, nom="Classe témoin fictive", annee_scolaire=self.classe.annee_scolaire)
        self.affecter_enseignant(autre)
        autre.activer()
        self.assertEqual(self.client.post(reverse("permissions_referentiels_classe", args=[autre.pk]), post).status_code, 400)
        self.assertFalse(PermissionChangementClasse.objects.exists())

    def test_confirmation_memebase_et_fermeture_sans_mot_de_passe(self):
        self.ouvrir()
        url = reverse("referentiel_classe", args=[self.classe.pk])
        jeton = self.client.post(url, {"action": "apercu", "version": self.a.pk}).context["jeton"]
        self.assertEqual(self.client.post(url, {"action": "confirmer", "jeton": jeton}).status_code, 302)
        url = reverse("permissions_referentiels_classe", args=[self.classe.pk])
        jeton = self.client.get(url).context["jeton"]
        self.assertEqual(self.client.post(url, {"action": "confirmer", "jeton": jeton}).status_code, 302)
        self.assertFalse(PermissionChangementClasse.objects.get(classe=self.classe).ouverte)

    def test_reauthentification_limite_les_tentatives(self):
        from datetime import timedelta
        from django.test import override_settings
        url = reverse("referentiel_classe", args=[self.classe.pk])
        jeton = self.client.post(url, {"action": "apercu", "version": self.b.pk}).context["jeton"]
        with override_settings(AXES_FAILURE_LIMIT=3, AXES_COOLOFF_TIME=timedelta(minutes=15)):
            for _ in range(3):
                self.client.post(url, {"action": "confirmer", "jeton": jeton, "mot_de_passe": "errone"})
            reponse = self.client.post(url, {"action": "confirmer", "jeton": jeton, "mot_de_passe": "ens-mdp"})
            self.assertEqual(reponse.status_code, 429)
        self.assertEqual(AdoptionReferentiel.objects.get(classe=self.classe, courante=True).version_id, self.a.pk)

    def test_premier_choix_propose_sans_reauthentification_et_classe_close_refuse(self):
        from .services.cloture_referentiels import clore
        nouvelle = Classe.objects.create(ecole=self.ecole, nom="Nouvelle classe fictive", annee_scolaire=self.classe.annee_scolaire)
        self.affecter_enseignant(nouvelle)
        nouvelle.activer()
        url = reverse("referentiel_classe", args=[nouvelle.pk])
        page = self.client.post(url, {"action": "apercu", "version": self.a.pk})
        self.assertEqual(page.context["apercu"]["garde"]["niveau"], "info")
        self.assertNotContains(page, "Votre mot de passe")
        self.assertEqual(self.client.post(url, {"action": "confirmer", "jeton": page.context["jeton"]}).status_code, 302)
        self.ouvrir()
        clore(utilisateur=self.enseignant, classe=self.classe)
        with self.assertRaises(ValidationError): self.permission(classe=True)
        page = self.client.get(reverse("permissions_referentiels_classe", args=[self.classe.pk]))
        self.assertTrue(page.context["clos"])
        self.assertFalse(page.context["jeton"])

    def test_mise_a_jour_de_source_apres_saisies_reste_bloquee(self):
        self.saisir()
        nouvelle = importer(document(version="2"))[0]
        publier_choix_application(annee=self.classe.annee_scolaire, versions_ids=[self.a.pk, nouvelle.pk],
                                 proposee_id=nouvelle.pk, revision_attendue=1)
        apercu = self.apercu(nouvelle)
        self.assertTrue(apercu["mise_a_jour"])
        self.assertEqual(apercu["garde"]["niveau"], "rouge")
        with self.assertRaises(ValidationError): self.appliquer(apercu)

    def test_consultation_adaptee_et_source_restent_distinctes(self):
        from .services.adaptations_referentiels import enregistrer_adaptation
        adoption = AdoptionReferentiel.objects.get(classe=self.classe, courante=True)
        enregistrer_adaptation(utilisateur=self.enseignant, ecole=self.ecole, classe=self.classe,
            annee=self.classe.annee_scolaire, competence=self.competence, adoption_attendue=adoption.pk,
            libelle="Mon libellé fictif", visible=False, revision_attendue=0)
        url = reverse("consulter_referentiels_classe", args=[self.classe.pk])
        self.assertContains(self.client.get(url, {"version": self.a.pk, "lecture": "classe"}), "Mon libellé fictif")
        page = self.client.get(url, {"version": self.a.pk})
        self.assertContains(page, "Je parle")
        self.assertNotContains(page, "Mon libellé fictif")

    def test_exception_de_classe_est_consommee_meme_si_changement_avant_saisies(self):
        self.ouvrir()
        self.adopter(self.b)
        self.assertFalse(PermissionChangementClasse.objects.get(classe=self.classe).ouverte)
