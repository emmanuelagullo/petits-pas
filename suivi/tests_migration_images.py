"""La mise à jour ne modifie pas silencieusement les anciens carnets."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MigrationImages(TransactionTestCase):
    def test_ecole_existante_garde_images_nouvelle_ecole_sans_photo(self):
        executor = MigrationExecutor(connection)
        avant = [('suivi', '0031_origine_initialisation_base_classe')]
        try:
            executor.migrate(avant)
            apps = executor.loader.project_state(avant).apps
            ancienne = apps.get_model('suivi', 'Ecole').objects.create(nom='École fictive existante')
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
            from .models import Ecole, Classe
            self.assertTrue(Ecole.objects.get(pk=ancienne.pk).illustration_avec_photos)
            nouvelle = Ecole.objects.create(nom='Nouvelle école fictive')
            self.assertFalse(nouvelle.illustration_avec_photos)
            self.assertIsNone(Classe.objects.create(ecole=nouvelle, nom='Classe fictive').illustration_avec_photos)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
