"""Ouvertures explicites pour les scénarios de conservation des données en test."""
from suivi.models import ChoixApplicationAnnuel, ChoixEcoleAnnuel, PermissionChangementClasse


def ouvrir_exception_fictive(classe):
    ChoixApplicationAnnuel.objects.filter(annee_scolaire=classe.annee_scolaire).update(changements_apres_saisies=True)
    ecole, _ = ChoixEcoleAnnuel.objects.get_or_create(ecole=classe.ecole, annee_scolaire=classe.annee_scolaire)
    ecole.changements_apres_saisies = True
    ecole.save(update_fields=["changements_apres_saisies"])
    permission, _ = PermissionChangementClasse.objects.get_or_create(classe=classe)
    permission.ouverte = True
    permission.revision += 1
    permission.save()
