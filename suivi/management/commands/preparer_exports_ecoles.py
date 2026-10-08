"""Traitement périodique, sans threads WSGI ni file d'attente externe."""
import shutil
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from django.utils import timezone

from suivi.audit import journaliser
from suivi.exports_ecole import autorise_export, dossier, produire, racine
from suivi.models import ExportEcole, ExportClasse
from suivi.exports_classe import autorise_export_classe, produire_classe


class Command(BaseCommand):
    help = "Préparer les exports demandés et effacer les copies expirées (serveur Linux)."

    def handle(self, **options):
        # Le verrou OS est libéré même après SIGKILL. Une invocation concurrente
        # ne nettoie jamais les fichiers du processus actif. Racine partagée
        # obligatoire entre web et traitement ; un seul serveur de traitement.
        import fcntl
        try:
            root = racine()
        except ValidationError as exc:
            raise CommandError(exc.messages[0]) from exc
        with (root / "traitement.lock").open("a") as verrou:
            try:
                fcntl.flock(verrou, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                self.stdout.write("Un traitement est déjà en cours.")
                return
            self._traiter(ExportEcole, lambda export: autorise_export(export.demande_par, export.ecole),
                          produire, root, "ecole")
            self._traiter(ExportClasse, lambda export: autorise_export_classe(export.demande_par, export.classe),
                          produire_classe, root, "classe")

    def _traiter(self, modele, autorisation, producteur, root, perimetre):
        # Une préparation encore marquée active après acquisition du verrou
        # provient d'une interruption. Pas de reprise automatique ambiguë.
        for export in modele.objects.filter(etat="preparation"):
            shutil.rmtree(dossier(export), ignore_errors=True)
            modele.objects.filter(pk=export.pk).update(etat="echec", mot_de_passe_local="",
                erreur="Préparation interrompue. Vous pouvez demander un nouvel export.")
        for export in modele.objects.filter(expire_le__lte=timezone.now()):
            shutil.rmtree(dossier(export), ignore_errors=True)
            # Conserver la ligne pour informer l'écran jusqu'à la prochaine demande.
            modele.objects.filter(pk=export.pk).update(mot_de_passe_local="", etat="echec")
        connus = {str(v) for model in (ExportEcole, ExportClasse)
                  for v in model.objects.values_list("identifiant", flat=True)}
        for chemin in root.iterdir():
            try:
                UUID(chemin.name)
            except ValueError:
                continue
            if chemin.name not in connus and chemin.is_dir() and not chemin.is_symlink():
                shutil.rmtree(chemin)
        for export in modele.objects.filter(etat="attente", expire_le__gt=timezone.now()).order_by("cree_le"):
            if not autorisation(export):
                modele.objects.filter(pk=export.pk).update(etat="echec", mot_de_passe_local="",
                    erreur="L'autorisation d'export n'est plus disponible.")
                continue
            if not modele.objects.filter(pk=export.pk, etat="attente",
                    expire_le__gt=timezone.now()).update(etat="preparation"):
                continue
            try:
                producteur(export)
            except Exception as exc:
                # Ne jamais publier la trace, un nom de média privé, une URL
                # signée du stockage ou un secret contenu dans une exception.
                message = "La préparation a échoué. Contactez la personne chargée du service."
                if isinstance(exc, ValidationError):
                    message = exc.messages[0]
                modele.objects.filter(pk=export.pk).update(etat="echec", mot_de_passe_local="", erreur=message)
                journaliser(export.demande_par, f"{perimetre}.export_echec", export,
                            nouvelles={"export": str(export.identifiant), "cause": type(exc).__name__})
                self.stderr.write(f"Export {export.identifiant} : échec ({type(exc).__name__}).")
            else:
                journaliser(export.demande_par, f"{perimetre}.export_prepare", export,
                            nouvelles={"export": str(export.identifiant)})
                self.stdout.write(f"Export {export.identifiant} prêt.")
