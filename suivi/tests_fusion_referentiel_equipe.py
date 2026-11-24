from copy import deepcopy

from django.test import SimpleTestCase

from .services.fusion_referentiel_equipe import fusionner_referentiel_equipe


class FusionReferentielEquipe(SimpleTestCase):
    def setUp(self):
        self.base = {
            "version": "1", "format": 2, "structure_seule": False,
            "source": {"identifiant": "equipe", "titre": "Équipe"},
            "domaines": [{"code": "LANG", "nom": "Langage", "sous_domaines": [],
                          "competences": [{"identite": "a", "libelle": "Écouter", "niveau": "PS"}]},
                         {"code": "ART", "nom": "Arts", "competences": []},
                         {"code": "MOT", "nom": "Motricité", "competences": []}],
        }
        self.locale, self.distante = deepcopy(self.base), deepcopy(self.base)
        self.a = self.locale["domaines"][0]["competences"]
        self.b = self.distante["domaines"][0]["competences"]

    def test_ajouts_concurrents_et_renommage(self):
        self.a.append({"identite": "b", "libelle": "Raconter"})
        self.b.append({"identite": "c", "libelle": "Décrire"})
        self.a[0]["libelle"] = "Écouter autrui"
        self.b[0]["niveau"] = "MS"
        resultat, conflits = fusionner_referentiel_equipe(self.base, self.locale, self.distante)
        self.assertEqual(conflits, [])
        competences = resultat["domaines"][0]["competences"]
        self.assertEqual({c["identite"] for c in competences}, {"a", "b", "c"})
        self.assertEqual(competences[0], {"identite": "a", "libelle": "Écouter autrui", "niveau": "MS"})
        self.assertNotIn("version", resultat)
        self.assertEqual(fusionner_referentiel_equipe(self.base, self.distante, self.locale),
                         (resultat, []))

    def test_edition_et_retrait_concurrents(self):
        self.a.clear()
        self.b[0]["libelle"] = "Écouter le récit"
        resultat, conflits = fusionner_referentiel_equipe(self.base, self.locale, self.distante)
        self.assertIsNone(resultat)
        self.assertEqual(conflits[0].chemin, ("domaines", "LANG", "competences", "a"))
        self.assertIsNone(conflits[0].locale)
        self.assertEqual(conflits[0].distante["libelle"], "Écouter le récit")

    def test_deplacements_incompatibles(self):
        self.locale["domaines"][1]["competences"].append(self.a.pop())
        self.distante["domaines"][2]["competences"].append(self.b.pop())
        resultat, conflits = fusionner_referentiel_equipe(self.base, self.locale, self.distante)
        self.assertIsNone(resultat)
        self.assertEqual(conflits[0].chemin, ("competences", "a", "emplacement"))

    def test_resolution_du_libelle_conserve_les_autres_modifications(self):
        self.a[0]["libelle"] = "Écouter l’autre"
        self.b[0]["libelle"] = "Écouter le récit"
        self.b[0]["niveau"] = "GS"
        resultat, conflits = fusionner_referentiel_equipe(self.base, self.locale, self.distante)
        self.assertIsNone(resultat)
        resultat, conflits = fusionner_referentiel_equipe(
            self.base, self.locale, self.distante, choix={conflits[0].chemin: "locale"},
        )
        self.assertEqual(conflits, [])
        self.assertEqual(resultat["domaines"][0]["competences"][0]["libelle"], "Écouter l’autre")
        self.assertEqual(resultat["domaines"][0]["competences"][0]["niveau"], "GS")
