import json
from io import StringIO
from tempfile import TemporaryDirectory

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase, override_settings

from .models import Classe, Competence, Domaine, Ecole, Observation, Scolarite, Trace


class DiagnosticStockage(TestCase):
    def test_compte_une_seule_fois_un_media_partage(self):
        with TemporaryDirectory() as dossier, override_settings(MEDIA_ROOT=dossier):
            ecole = Ecole.objects.create(nom="École fictive")
            classe = Classe.objects.create(ecole=ecole, nom="Classe")
            domaine = Domaine.objects.create(ecole=ecole, nom="Domaine")
            competence = Competence.objects.create(domaine=domaine, libelle="Compétence")
            from .models import Eleve
            eleve = Eleve.objects.create(ecole=ecole, prenom="Lou")
            scolarite = Scolarite.objects.create(
                eleve=eleve, classe=classe, annee_scolaire=classe.annee_scolaire, niveau="PS"
            )
            observation = Observation.objects.create(eleve=eleve, competence=competence)
            trace = Trace.objects.create(observation=observation, scolarite=scolarite)
            trace.photo.save("image.jpg", ContentFile(b"image-fictive"), save=True)
            Trace.objects.create(
                observation=observation, scolarite=scolarite, photo=trace.photo.name
            )
            sortie = StringIO()
            call_command("diagnostiquer_stockage", json=True, stdout=sortie)
            rapport = json.loads(sortie.getvalue())
            self.assertEqual(rapport["medias"]["objets_uniques"], 1)
            self.assertEqual(rapport["medias"]["octets_uniques"], len(b"image-fictive"))
            self.assertEqual(rapport["medias"]["par_usage"]["traces"]["references"], 1)
