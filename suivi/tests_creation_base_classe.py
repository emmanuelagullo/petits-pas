"""Le défaut prépare une base fixe, sans confirmation séparée ni acquis."""
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.urls import reverse

from .tests import Base
from .tests_import_sources_referentiels import document, importer
from .services.reprise_referentiels import reprendre
from .models import AdoptionReferentiel, Classe, Observation, EtatAnnuelObservation
from .services.choix_bases_referentiels import (choix_bases, enregistrer_choix_ecole,
                                              publier_choix_application)
from .services.garde_fous_referentiels import demarrage_ecole
from .services.creation_classe import creer_classe_avec_base
from .services.adoption_bases_referentiels import adopter_base, apercu_adoption


class CreationBaseClasse(Base):
    def setUp(self):
        super().setUp()
        reprendre(self.ecole.pk)
        self.annee = self.classe.annee_scolaire
        self.a = importer(document("creation-a"))[0]
        self.b = importer(document("creation-b"))[0]
        publier_choix_application(annee=self.annee, versions_ids=[self.a.pk, self.b.pk],
                                 proposee_id=self.a.pk, revision_attendue=0)
        self.client.force_login(self.direction)
        self.creation = reverse("creer_classe")

    def creer(self, **options):
        page = self.client.get(self.creation, {"annee_scolaire": self.annee})
        donnees = dict(nom="Nouvelle classe fictive", annee_scolaire=self.annee, base="ecole",
                       jeton_choix=page.context["formulaire"]["jeton_choix"].value())
        donnees.update(options)
        return self.client.post(self.creation, donnees)

    def test_echange_depuis_ecole_et_classe(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from suivi.services.paquets_referentiels import lire_paquet
        from suivi.models import SourceReferentiel

        ecole = reverse("paquets_referentiels_ecole") + f"?annee={self.annee}&edition={self.a.pk}"
        classe = reverse("paquets_referentiels_classe", args=[self.classe.pk]) + f"?edition={self.a.pk}"
        for url in (ecole, classe):
            page = self.client.get(url)
            self.assertContains(page, "Télécharger la sélection")
            self.assertContains(page, 'data-sommaire-page')
            self.assertContains(page, 'data-memoire-filtre="partage-export"')
            fichier = self.client.post(url, {"action": "selection", "competence": "oser-parler"})
            self.assertEqual(fichier["Content-Type"], "application/zip")
        donnees = fichier.content

        def examiner(destination="ecole"):
            return self.client.post(ecole, {"action": "apercu", "destination": destination,
                "paquet": SimpleUploadedFile("selection.zip", donnees)})

        self.assertEqual(examiner("application").status_code, 403)
        apercu = examiner()
        self.assertContains(apercu, "Confirmer l’import")
        self.assertFalse(SourceReferentiel.objects.filter(identifiant_diffusion__startswith="selection-").exists())
        confirmation = {"action": "importer", "jeton": apercu.context["jeton"]}
        resultat = self.client.post(ecole, confirmation)
        self.assertContains(resultat, "Édition ajoutée au catalogue de l’école")
        self.assertContains(resultat, f"Cette édition fait partie des choix autorisés pour {self.annee}.")
        source = SourceReferentiel.objects.get(identifiant_diffusion__startswith="selection-")
        self.assertEqual(source.ecole_id, self.ecole.pk)
        self.assertIn(source.versions.get(), choix_bases(self.ecole, self.annee).versions)
        self.assertEqual(self.client.post(ecole, confirmation).status_code, 400)
        confirmation["jeton"] = examiner().context["jeton"]
        self.assertContains(self.client.post(ecole, confirmation), "figure déjà")
        self.assertIn("source_origine: creation-a", lire_paquet(donnees))

    def test_echange_presente_la_base_de_classe_et_explique_le_droit_import(self):
        self.creer()
        classe = Classe.objects.get(nom="Nouvelle classe fictive")
        url = reverse("paquets_referentiels_classe", args=[classe.pk])
        self.assertEqual(self.client.get(url).context["edition"], self.a)
        self.assertEqual(self.client.get(url, {"edition": self.b.pk}).context["edition"], self.b)

        reglages = reverse("referentiel_classe", args=[self.classe.pk])
        self.assertContains(self.client.get(reglages), "Importer dans le catalogue de l’école")
        self.client.force_login(self.enseignant)
        page = self.client.get(reglages)
        self.assertContains(page, "Exporter un référentiel")
        self.assertContains(page, "Proposer au catalogue de l’école")
        self.assertNotContains(page, "#import-referentiel")
        page = self.client.get(reverse("paquets_referentiels_classe", args=[self.classe.pk]))
        self.assertContains(page, ">Partager le référentiel de la classe</h1>")
        self.assertContains(page, '<section id="export-referentiel"')
        self.assertNotContains(page, '<details id="export-referentiel"')
        self.assertNotContains(page, "Transmettez-le à une personne qui gère l’école")
        self.assertNotContains(page, "data-sommaire-page")
        self.assertNotContains(page, 'id="import-referentiel"')

    def test_import_signale_une_edition_non_autorisee_par_les_choix_annuels(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .models import ChoixEcoleAnnuel
        from .services.paquets_referentiels import empaqueter

        ChoixEcoleAnnuel.objects.update_or_create(ecole=self.ecole, annee_scolaire=self.annee,
                                                  defaults={"restreindre": True})
        url = reverse("paquets_referentiels_classe", args=[self.classe.pk])
        fichier = SimpleUploadedFile("nouvelle.zip", empaqueter(document("nouvelle-fictive")))
        apercu = self.client.post(url, {"action": "apercu", "paquet": fichier})
        page = self.client.post(url, {"action": "importer", "jeton": apercu.context["jeton"]},
                                headers={"HX-Request": "true"})
        self.assertContains(page, "Édition ajoutée au catalogue de l’école")
        lien = reverse("referentiels_ecole") + f"?annee={self.annee}#choix-ecole"
        self.assertContains(page, f'href="{lien}"')
        self.assertNotContains(page, "Examiner l’adoption pour la classe")

    def test_delegation_import_depuis_la_classe_et_revocation_avant_confirmation(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .models import ChoixEcoleAnnuel, SourceReferentiel
        from .services.paquets_referentiels import empaqueter

        reglages = reverse("referentiels_ecole")
        echange = reverse("paquets_referentiels_classe", args=[self.classe.pk])
        ChoixEcoleAnnuel.objects.update_or_create(ecole=self.ecole, annee_scolaire=self.annee,
                                                  defaults={"restreindre": True})

        def deleguer(autoriser):
            return self.client.post(reglages, {"action": "deleguer_import", "annee": self.annee,
                "delegation": "oui" if autoriser else "", "mot_de_passe": "dir-mdp"})

        def examiner(destination="ecole"):
            paquet = SimpleUploadedFile("nouvelle.zip", empaqueter(document("nouvelle-deleguee")))
            return self.client.post(echange, {"action": "apercu", "destination": destination, "paquet": paquet})

        self.assertContains(self.client.get(reglages), "Autoriser les responsables de classe à importer")
        self.client.force_login(self.enseignant)
        self.assertEqual(examiner().status_code, 403)
        self.assertEqual(deleguer(True).status_code, 403)

        self.client.force_login(self.direction)
        self.assertEqual(deleguer(True).status_code, 302)
        self.client.force_login(self.enseignant)
        self.assertContains(self.client.get(reverse("referentiel_classe", args=[self.classe.pk])),
                            "Importer dans le catalogue de l’école")
        self.assertEqual(self.client.get(reverse("paquets_referentiels_ecole")).status_code, 403)
        self.assertEqual(examiner("application").status_code, 403)
        jeton = examiner().context["jeton"]

        self.client.force_login(self.direction)
        self.assertEqual(deleguer(False).status_code, 302)
        self.client.force_login(self.enseignant)
        self.assertEqual(self.client.post(echange, {"action": "importer", "jeton": jeton}).status_code, 403)
        self.assertFalse(SourceReferentiel.objects.filter(ecole=self.ecole,
            identifiant_diffusion="nouvelle-deleguee").exists())

        self.client.force_login(self.direction)
        self.assertEqual(deleguer(True).status_code, 302)
        self.client.force_login(self.enseignant)
        jeton = examiner().context["jeton"]
        page = self.client.post(echange, {"action": "importer", "jeton": jeton})
        self.assertContains(page, "Une personne qui gère l’école doit autoriser cette édition")
        self.assertNotContains(page, "Ouvrir les choix annuels de l’école")
        source = SourceReferentiel.objects.get(ecole=self.ecole, identifiant_diffusion="nouvelle-deleguee")
        self.assertNotIn(source.versions.get(), choix_bases(self.ecole, self.annee).versions)

    def test_proposer_un_zip_avertit_la_direction_et_attend_sa_decision(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from comptes.models import AppartenanceEcole, ResponsabiliteEcole
        from .models import Ecole, PropositionReferentiel, SourceReferentiel
        from .services.paquets_referentiels import empaqueter

        proposer = reverse("proposer_referentiel_classe", args=[self.classe.pk])
        recevoir = reverse("propositions_referentiels_ecole")
        self.client.force_login(self.enseignant)
        self.assertEqual(self.client.get(recevoir).status_code, 403)
        autre_ecole = Ecole.objects.create(nom="Autre école fictive")
        appartenance = AppartenanceEcole.objects.create(utilisateur=self.direction, ecole=autre_ecole)
        ResponsabiliteEcole.objects.create(appartenance=appartenance)
        for numero, action, etat in (("1", "accepter", "Ajoutée au catalogue"),
                                      ("2", "refuser", "Refusée")):
            fichier = SimpleUploadedFile("proposition.zip", empaqueter(document("proposition-fictive", numero)))
            page = self.client.post(proposer, {"action": "examiner", "paquet": fichier})
            self.assertContains(page, "Je parle")
            self.assertEqual(self.client.post(proposer, {"action": "proposer",
                "jeton": page.context["jeton"], "note": "À examiner"}).status_code, 302)
            proposition = PropositionReferentiel.objects.get(numero=numero)
            self.assertEqual(proposition.etat, PropositionReferentiel.ATTENTE)
            examen = reverse("examiner_proposition_referentiel", args=[proposition.pk])
            self.assertEqual(self.client.post(examen, {"action": "accepter"}).status_code, 403)
            self.assertFalse(SourceReferentiel.objects.filter(ecole=self.ecole,
                identifiant_diffusion="proposition-fictive", versions__numero=numero).exists())

            self.client.force_login(self.direction)
            session = self.client.session
            session["ecole_id"] = autre_ecole.pk
            session.save()
            self.assertNotContains(self.client.get(recevoir), "Propositions reçues (1)")
            self.assertEqual(self.client.get(examen).status_code, 404)
            session = self.client.session
            session["ecole_id"] = self.ecole.pk
            session.save()
            self.assertContains(self.client.get(recevoir), "Propositions reçues (1)")
            self.assertContains(self.client.get(examen), "À examiner")
            self.assertEqual(self.client.post(examen, {"action": action}).status_code, 302)
            self.assertNotContains(self.client.get(recevoir), "Propositions reçues (1)")
            self.assertEqual(self.client.post(examen, {"action": action}).status_code, 400)
            self.assertEqual(SourceReferentiel.objects.filter(ecole=self.ecole,
                identifiant_diffusion="proposition-fictive", versions__numero=numero).exists(), action == "accepter")
            proposition.refresh_from_db()
            self.assertEqual(proposition.document, "")
            self.client.force_login(self.enseignant)
            self.assertContains(self.client.get(proposer), etat)

    def test_brouillon_de_composition_repris_avec_plusieurs_rubriques(self):
        from suivi.services.import_sources_referentiels import lire_source
        from suivi.services.paquets_referentiels import lire_paquet

        url = reverse("paquets_referentiels_ecole") + f"?annee={self.annee}"
        champs = {"identifiant": "brouillon", "titre": "Brouillon fictif", "version": "1",
                  "provenance": "Équipe", "licence": "CC-BY-SA-4.0", "rubrique": "Langage",
                  "reprise": [f"{self.a.pk}:oser-parler"],
                  "creation_rubrique": ["Explorer"], "creation_libelle": ["Compter"],
                  "creation_identite": ["compter"], "creation_niveau": ["MS"]}
        self.assertContains(self.client.post(url, {**champs, "action": "enregistrer_composition"}),
                            "Brouillon enregistré")
        self.client.logout()
        self.client.force_login(self.direction)
        page = self.client.get(url)
        self.assertContains(page, 'value="Compter"')
        self.assertEqual(self.client.post(url, {**champs, "action": "composer"}).status_code, 400)
        reponse = self.client.post(url, {**champs, "action": "composer",
                                        "revision_brouillon": page.context["revision_brouillon"]})
        self.assertEqual(reponse["Content-Type"], "application/zip")
        contenu, _ = lire_source(lire_paquet(reponse.content))
        self.assertEqual([d["nom"] for d in contenu["domaines"]], ["Langage", "Explorer"])

    def test_composer_importer_puis_publier_depuis_ecole(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from suivi.models import VersionReferentiel

        url = reverse("paquets_referentiels_ecole") + f"?annee={self.annee}"
        composition = self.client.post(url, {
            "action": "composer", "identifiant": "parcours-compose", "titre": "Parcours composé",
            "version": "1", "provenance": "Exemple de test", "licence": "CC-BY-SA-4.0",
            "rubrique": "Langage", "reprise": [f"{self.a.pk}:oser-parler"],
            "nouvelle": "Présenter une idée", "identite_nouvelle": "presenter", "niveau_nouvelle": "PS",
        })
        self.assertEqual(composition["Content-Type"], "application/zip")
        self.direction.is_superuser = True
        self.direction.save(update_fields=["is_superuser"])

        apercu = self.client.post(url, {"action": "apercu", "destination": "application",
            "paquet": SimpleUploadedFile("edition.zip", composition.content)})
        self.assertContains(apercu, "Présenter une idée")
        self.assertContains(self.client.post(url, {"action": "importer", "jeton": apercu.context["jeton"]}),
                            "Édition ajoutée")
        version = VersionReferentiel.objects.get(source__identifiant="parcours-compose")
        choix_avant = choix_bases(self.ecole, self.annee)
        self.assertNotIn(version, choix_avant.versions)
        page = self.client.get(url)
        publication = self.client.post(url, {"action": "publier", "publier_edition": version.pk,
            "jeton_publication": page.context["jeton_publication"]})
        self.assertContains(publication, "Édition autorisée pour l’année")
        choix_apres = choix_bases(self.ecole, self.annee)
        self.assertIn(version, choix_apres.versions)
        self.assertEqual(choix_avant.proposee, choix_apres.proposee)
        self.assertEqual(version.definitions.count(), 2)
        self.assertTrue(version.definitions.filter(identite=self.a.definitions.get().identite).exists())

    def test_defaut_adopte_a_la_creation_sans_mot_de_passe_ni_saisie(self):
        page = self.creer()
        classe = Classe.objects.get(nom="Nouvelle classe fictive")
        self.assertRedirects(page, reverse("importer_eleves", args=[classe.pk]))
        adoption = AdoptionReferentiel.objects.get(classe=classe)
        self.assertEqual(adoption.version_id, self.a.pk)
        self.assertTrue(adoption.initialisee_depuis_ecole)
        self.assertEqual(adoption.auteur_id, self.direction.pk)
        self.assertTrue(adoption.usages.exists())
        self.assertFalse(Observation.objects.exists())
        self.assertFalse(EtatAnnuelObservation.objects.exists())
        self.assertTrue(demarrage_ecole(self.ecole))
        self.assertFalse(classe.responsables_actifs().exists())
        self.assertEqual(classe.etat, Classe.PREPARATION)
        # Une proposition d'école ultérieure ne remplace pas cette adoption.
        choix = choix_bases(self.ecole, self.annee)
        enregistrer_choix_ecole(utilisateur=self.direction, ecole=self.ecole, annee=self.annee,
            restreindre=False, versions_ids=[], proposee_id=self.b.pk, revisions_attendues=choix.revisions)
        adoption.refresh_from_db()
        self.assertEqual(adoption.version_id, self.a.pk)
        self.assertEqual(AdoptionReferentiel.objects.filter(classe=classe).count(), 1)

    def test_creation_ne_propose_pas_de_choix_independant_et_refuse_un_post_forge(self):
        page = self.client.get(self.creation, {"annee_scolaire": self.annee})
        self.assertContains(page, self.a.source.titre)
        self.assertNotContains(page, "Choix indépendant")
        self.assertNotContains(page, 'name="mot_de_passe"')
        self.assertNotContains(page, '<select')
        for version in (self.a, self.b):
            page = self.creer(base=str(version.pk), mot_de_passe="dir-mdp")
            self.assertContains(page, "Sélectionnez un choix valide")
            self.assertFalse(Classe.objects.filter(nom="Nouvelle classe fictive").exists())
            with self.assertRaises(ValidationError):
                creer_classe_avec_base(utilisateur=self.direction, ecole=self.ecole,
                    nom="Interdite", annee=self.annee, base=str(version.pk),
                    revisions_attendues=choix_bases(self.ecole, self.annee).revisions)
            self.assertFalse(Classe.objects.filter(nom="Interdite").exists())

    def test_changement_reste_avance_risque_et_confirme_sans_droit_pedagogique(self):
        self.creer()
        classe = Classe.objects.get(nom="Nouvelle classe fictive")
        url = reverse("referentiel_classe", args=[classe.pk])
        page = self.client.get(url)
        self.assertContains(page, "Avancé — changer la base de compétences")
        self.assertContains(page, "référentiel commun de l’école")
        page = self.client.post(url, {"action": "apercu", "version": self.b.pk})
        jeton = page.context["jeton"]
        self.assertEqual(page.context["apercu"]["garde"]["niveau"], "orange")
        self.assertEqual(self.client.post(url, {"action": "confirmer", "jeton": jeton}).status_code, 400)
        self.assertEqual(AdoptionReferentiel.objects.get(classe=classe).version_id, self.a.pk)
        self.assertEqual(self.client.post(url, {"action": "confirmer", "jeton": jeton,
            "mot_de_passe": "dir-mdp"}).status_code, 302)
        adoption = AdoptionReferentiel.objects.get(classe=classe, courante=True)
        self.assertEqual(AdoptionReferentiel.objects.filter(classe=classe).count(), 2)
        self.assertTrue(AdoptionReferentiel.objects.filter(classe=classe, version=self.a, courante=False).exists())
        self.assertEqual(adoption.version_id, self.b.pk)
        self.assertFalse(adoption.initialisee_depuis_ecole)
        self.assertFalse(demarrage_ecole(self.ecole))
        self.assertFalse(classe.responsables_actifs().exists())

    def test_absence_de_catalogue_n_empeche_pas_preparation_sans_base(self):
        self.annee = "2027-2028"
        # La reprise locale reste proposée tant qu'aucune politique n'est publiée.
        publier_choix_application(annee=self.annee, versions_ids=[], proposee_id=None, revision_attendue=0)
        self.creer(base="plus_tard")
        classe = Classe.objects.get(nom="Nouvelle classe fictive")
        self.assertEqual(classe.annee_scolaire, self.annee)
        self.assertFalse(AdoptionReferentiel.objects.filter(classe=classe).exists())

    def test_restriction_et_annee_cible_controlees(self):
        choix = choix_bases(self.ecole, self.annee)
        enregistrer_choix_ecole(utilisateur=self.direction, ecole=self.ecole, annee=self.annee,
            restreindre=True, versions_ids=[self.a.pk], proposee_id=self.a.pk,
            revisions_attendues=choix.revisions)
        page = self.creer(base=str(self.b.pk), mot_de_passe="dir-mdp")
        self.assertFalse(Classe.objects.filter(nom="Nouvelle classe fictive").exists())
        self.assertContains(page, "Sélectionnez un choix valide")
        publier_choix_application(annee="2027-2028", versions_ids=[self.b.pk],
                                 proposee_id=self.b.pk, revision_attendue=0)
        self.annee = "2027-2028"
        self.creer()
        self.assertEqual(AdoptionReferentiel.objects.get(classe__nom="Nouvelle classe fictive").version_id, self.b.pk)

    def test_jeton_perime_et_annee_modifiee_ne_creent_rien(self):
        page = self.client.get(self.creation, {"annee_scolaire": self.annee})
        jeton = page.context["formulaire"]["jeton_choix"].value()
        publier_choix_application(annee=self.annee, versions_ids=[self.a.pk, self.b.pk],
                                 proposee_id=self.b.pk, revision_attendue=1)
        for donnees in (dict(annee_scolaire=self.annee, base="ecole"),
                        dict(annee_scolaire="2027-2028", base="ecole")):
            reponse = self.client.post(self.creation, dict(nom="Refusée", jeton_choix=jeton, **donnees))
            self.assertContains(reponse, "Vérifiez")
            self.assertFalse(Classe.objects.filter(nom="Refusée").exists())

    def test_echec_adoption_annule_creation_et_nom_duplique_ne_modifie_pas(self):
        with patch("suivi.services.creation_classe.adopter_base", side_effect=ValidationError("Refus fictif")):
            self.assertContains(self.creer(), "Refus fictif")
        self.assertFalse(Classe.objects.filter(nom="Nouvelle classe fictive").exists())
        self.creer()
        avant = list(AdoptionReferentiel.objects.values())
        self.assertContains(self.creer(), "Cette classe existe déjà")
        self.assertEqual(list(AdoptionReferentiel.objects.values()), avant)

    def test_origine_initiale_ne_peut_pas_etre_utilisee_pour_un_remplacement(self):
        self.creer()
        classe = Classe.objects.get(nom="Nouvelle classe fictive")
        apercu = apercu_adoption(utilisateur=self.direction, classe=classe, version_id=self.b.pk)
        with self.assertRaises(ValidationError):
            adopter_base(utilisateur=self.direction, classe=classe, version_id=self.b.pk,
                revisions_attendues=apercu["revisions"], adoption_attendue=apercu["adoption_id"],
                garde_attendue=apercu["garde"]["empreinte"], initialisee_depuis_ecole=True)
        self.assertEqual(AdoptionReferentiel.objects.get(classe=classe).version_id, self.a.pk)

    def test_creation_reste_reservee_direction(self):
        self.client.force_login(self.enseignant)
        self.assertEqual(self.client.get(self.creation).status_code, 403)
        self.assertEqual(self.client.post(self.creation, {"nom": "Interdite"}).status_code, 403)
