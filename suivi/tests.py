from django.test import TestCase
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
        self.assertIsNone(self.etat())

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


class Carnet(Base):
    def test_le_carnet_ne_montre_que_les_competences_observees(self):
        self.entrer()
        url = reverse("carnet", args=[self.eleve.pk])
        self.assertNotContains(self.client.get(url), "Je dis mon prénom")
        Observation.objects.create(eleve=self.eleve, competence=self.competence)
        self.assertContains(self.client.get(url), "Je dis mon prénom")

    def test_le_carnet_complet_montre_tout(self):
        self.entrer()
        r = self.client.get(reverse("carnet", args=[self.eleve.pk]), {"tout": "1"})
        self.assertContains(r, "Je dis mon prénom")


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
