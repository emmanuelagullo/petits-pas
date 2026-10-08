"""Export de classe : même formulaire et projection sur serveur et en local."""
import tempfile
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from .audit import journaliser
from .contexte_ecole import ecole_courante
from .exports_classe import autorise_export_classe, creer_zip_classe
from .exports_ecole import racine
from .models import Classe, ExportClasse
from .paquet_local import preparer_restauration
from .views_exports import ExportForm, _confirmer, servir_export


class ExportClasseForm(ExportForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mot_de_passe"].label = "Votre mot de passe sur cet appareil" if settings.MODE_LOCAL else "Votre mot de passe sur ce service"
        self.fields["confirme"].label = "Je comprends que cette copie contient des données privées et évoluera indépendamment."


def _classe(request, pk):
    if not request.user.is_authenticated:
        raise Http404
    classe = get_object_or_404(Classe, pk=pk, ecole=ecole_courante(request))
    if not autorise_export_classe(request.user, classe):
        raise Http404
    return classe


def _copie_locale(request, classe, empreinte):
    export = ExportClasse(classe=classe, demande_par=request.user, mot_de_passe_local=empreinte)
    with tempfile.TemporaryDirectory(prefix=".export-classe-") as dossier:
        travail = Path(dossier)
        if getattr(settings, "MODE_PWA", False):
            from pwa.transfers import OpfsFile
            with OpfsFile("export") as fichier:
                creer_zip_classe(export, travail, fichier)
            response = HttpResponse(content_type="application/zip")
            response.pwa_export = True
        else:
            fichier = tempfile.TemporaryFile()
            try:
                creer_zip_classe(export, travail, fichier)
                fichier.seek(0)
                verifie = preparer_restauration(File(fichier, name="classe.zip"), travail, taille_max=settings.EXPORT_TAILLE_MAX)
                import shutil
                shutil.rmtree(verifie.etape)
                fichier.seek(0)
                response = FileResponse(fichier, as_attachment=True,
                    filename=f"petits-pas-classe-{classe.pk}-{timezone.now():%Y%m%d}.zip")
            except BaseException:
                fichier.close()
                raise
        response["Content-Disposition"] = f'attachment; filename="petits-pas-classe-{classe.pk}-{timezone.now():%Y%m%d}.zip"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        # Cette extraction ne renouvelle pas le rappel de sauvegarde complète.
        journaliser(request.user, "classe.export_local", classe)
        return response


@never_cache
@require_http_methods(["GET", "POST"])
def exporter_classe(request, pk):
    classe = _classe(request, pk)
    formulaire = ExportClasseForm(request.POST or None, utilisateur=request.user)
    export = None if settings.MODE_LOCAL else ExportClasse.objects.filter(classe=classe).first()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "preparer" and formulaire.is_valid():
            if not _confirmer(request, formulaire.cleaned_data["mot_de_passe"]):
                formulaire.add_error("mot_de_passe", "Le mot de passe n'a pas permis de confirmer cette opération.")
            else:
                try:
                    empreinte = make_password(formulaire.cleaned_data["mot_de_passe_local"])
                    if settings.MODE_LOCAL:
                        return _copie_locale(request, classe, empreinte)
                    racine()
                    with transaction.atomic():
                        Classe.objects.select_for_update().get(pk=classe.pk)
                        ancien = ExportClasse.objects.filter(classe=classe).first()
                        if ancien and (ancien.etat == "preparation" or
                                (ancien.etat in {"attente", "pret"} and ancien.expire_le > timezone.now())):
                            raise ValidationError("Un export de cette classe est déjà en préparation ou disponible.")
                        if ancien:
                            ancien.delete()
                        export = ExportClasse.objects.create(classe=classe, demande_par=request.user,
                            mot_de_passe_local=empreinte, expire_le=timezone.now() + timedelta(hours=24))
                        journaliser(request.user, "classe.export_demande", classe,
                            nouvelles={"export": str(export.identifiant)})
                    request.session["export_classe_confirme"] = str(export.identifiant)
                    return redirect("exporter_classe", pk=classe.pk)
                except ValidationError as exc:
                    formulaire.add_error(None, exc)
                except (OSError, ValueError):
                    # Pas de chemin privé ou de message du stockage dans l'écran.
                    formulaire.add_error(None, "La préparation a échoué. Vérifiez l'espace disponible et réessayez.")
        elif action == "telecharger" and export and export.etat == "pret" and export.expire_le > timezone.now():
            if _confirmer(request, request.POST.get("mot_de_passe", "")):
                request.session["export_classe_confirme"] = str(export.identifiant)
                return redirect("telecharger_export_classe", pk=classe.pk, identifiant=export.identifiant)
            formulaire.add_error(None, "Le mot de passe n'a pas permis de confirmer le téléchargement.")
    actif = bool(export and export.expire_le > timezone.now() and export.etat in {"attente", "preparation", "pret"})
    return render(request, "suivi/exporter_classe.html", {"classe": classe,
        "formulaire": formulaire, "export": export, "actif": actif,
        "expire": bool(export and export.expire_le <= timezone.now())})


@never_cache
@require_safe
def telecharger_export_classe(request, pk, identifiant):
    if settings.MODE_LOCAL:
        raise Http404
    classe = _classe(request, pk)
    export = get_object_or_404(ExportClasse, classe=classe, identifiant=identifiant,
        etat="pret", expire_le__gt=timezone.now())
    if request.session.get("export_classe_confirme") != str(identifiant):
        return redirect("exporter_classe", pk=classe.pk)
    return servir_export(request, export, f"classe-{classe.pk}", "classe.export_telecharge")
