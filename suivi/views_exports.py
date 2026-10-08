"""Sortie complète d'école : permission distincte, POST confirmé, flux borné."""
import re
from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from .audit import journaliser
from .contexte_ecole import ecole_courante
from .exports_ecole import autorise_export, dossier, racine
from .models import Ecole, ExportEcole


class ExportForm(forms.Form):
    mot_de_passe = forms.CharField(label="Votre mot de passe sur ce service", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))
    mot_de_passe_local = forms.CharField(label="Nouveau mot de passe pour la copie locale", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    confirmation_locale = forms.CharField(label="Répétez le nouveau mot de passe", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    confirme = forms.BooleanField(label="Je comprends que le ZIP contient les données privées de toutes les classes, y compris les contenus internes.")

    def __init__(self, *args, utilisateur, **kwargs):
        super().__init__(*args, **kwargs)
        self.utilisateur = utilisateur

    def clean(self):
        donnees = super().clean()
        local = donnees.get("mot_de_passe_local")
        if local:
            validate_password(local, self.utilisateur)
            if self.utilisateur.check_password(local):
                raise ValidationError("Choisissez un mot de passe différent de votre mot de passe actuel.")
            if local != donnees.get("confirmation_locale"):
                raise ValidationError("Les nouveaux mots de passe ne correspondent pas.")
        return donnees


def _ecole(request):
    if not request.user.is_authenticated:
        raise Http404
    ecole = ecole_courante(request)
    if not autorise_export(request.user, ecole):
        raise Http404
    return ecole


def _confirmer(request, mot_de_passe):
    # Les mêmes backends et limites de tentatives que la connexion.
    user = authenticate(request, username=request.user.get_username(), password=mot_de_passe)
    return bool(user and user.pk == request.user.pk)


@never_cache
@require_http_methods(["GET", "POST"])
def exporter_ecole(request):
    ecole = _ecole(request)
    formulaire = ExportForm(request.POST or None, utilisateur=request.user)
    export = ExportEcole.objects.filter(ecole=ecole).first()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "preparer" and formulaire.is_valid():
            if not _confirmer(request, formulaire.cleaned_data["mot_de_passe"]):
                formulaire.add_error("mot_de_passe", "Le mot de passe n'a pas permis de confirmer cette opération.")
            else:
                try:
                    racine()
                    with transaction.atomic():
                        Ecole.objects.select_for_update().get(pk=ecole.pk)
                        ancien = ExportEcole.objects.filter(ecole=ecole).first()
                        if ancien and (ancien.etat == "preparation" or
                                      (ancien.etat in {"attente", "pret"} and ancien.expire_le > timezone.now())):
                            raise ValidationError("Un export est déjà en préparation ou disponible.")
                        if ancien:
                            # Le worker nettoie le dossier périmé ; ne pas effacer
                            # ici les fichiers d'un traitement concurrent.
                            ancien.delete()
                        export = ExportEcole.objects.create(ecole=ecole, demande_par=request.user,
                            mot_de_passe_local=make_password(formulaire.cleaned_data["mot_de_passe_local"]),
                            expire_le=timezone.now() + timedelta(hours=24))
                        journaliser(request.user, "ecole.export_demande", export,
                                    nouvelles={"export": str(export.identifiant)})
                    request.session["export_confirme"] = str(export.identifiant)
                    return redirect("exporter_ecole")
                except ValidationError as exc:
                    formulaire.add_error(None, exc)
        elif action == "telecharger" and export and export.etat == "pret" and export.expire_le > timezone.now():
            if _confirmer(request, request.POST.get("mot_de_passe", "")):
                request.session["export_confirme"] = str(export.identifiant)
                return redirect("telecharger_export_ecole", identifiant=export.identifiant)
            messages.error(request, "Le mot de passe n'a pas permis de confirmer le téléchargement.")
    actif = bool(export and export.expire_le > timezone.now() and export.etat in {"attente", "preparation", "pret"})
    return render(request, "suivi/exporter_ecole.html", {
        "formulaire": formulaire, "export": export, "actif": actif,
        "expire": bool(export and export.expire_le <= timezone.now()),
    })


def _plage(valeur, taille):
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", valeur)
    if not match or not any(match.groups()) or taille == 0:
        raise ValueError
    gauche, droite = match.groups()
    if not gauche:
        nombre = int(droite)
        if nombre == 0:
            raise ValueError
        return max(0, taille - nombre), taille - 1
    debut = int(gauche)
    fin = min(int(droite), taille - 1) if droite else taille - 1
    if debut >= taille or fin < debut:
        raise ValueError
    return debut, fin


def _flux(fichier, debut, longueur):
    try:
        fichier.seek(debut)
        while longueur:
            bloc = fichier.read(min(1024**2, longueur))
            if not bloc:
                break
            longueur -= len(bloc)
            yield bloc
    finally:
        fichier.close()


@never_cache
@require_safe
def telecharger_export_ecole(request, identifiant):
    ecole = _ecole(request)
    export = ExportEcole.objects.filter(ecole=ecole, identifiant=identifiant,
        etat="pret", expire_le__gt=timezone.now()).first()
    if not export:
        raise Http404
    if request.session.get("export_confirme") != str(identifiant):
        return redirect("exporter_ecole")
    return servir_export(request, export, f"ecole-{ecole.pk}", "ecole.export_telecharge")


def servir_export(request, export, nom, evenement):
    identifiant = export.identifiant
    try:
        fichier = (dossier(export) / "ecole.zip").open("rb")
    except FileNotFoundError:
        raise Http404
    etag = '"' + export.empreinte + '"'
    debut, fin, statut = 0, export.taille_zip - 1, 200
    plage = request.headers.get("Range")
    if plage and request.headers.get("If-Range", etag) == etag:
        try:
            debut, fin = _plage(plage, export.taille_zip)
            statut = 206
        except (ValueError, OverflowError):
            fichier.close()
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{export.taille_zip}"
            return response
    longueur = fin - debut + 1
    if request.method == "HEAD":
        fichier.close()
        response = HttpResponse(status=statut, content_type="application/zip")
    else:
        # L'ouverture précède le retour : un nettoyage Linux n'interrompt pas
        # un téléchargement déjà commencé. Aucun ZIP chargé en mémoire.
        journaliser(request.user, evenement, export,
                    nouvelles={"export": str(identifiant), "debut": debut, "octets": longueur})
        response = StreamingHttpResponse(_flux(fichier, debut, longueur), status=statut,
                                         content_type="application/zip")
        response._resource_closers.append(fichier.close)
    response["Content-Length"] = str(longueur)
    response["Accept-Ranges"] = "bytes"
    response["ETag"] = etag
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Disposition"] = f'attachment; filename="petits-pas-{nom}-{export.cree_le:%Y%m%d}.zip"'
    if statut == 206:
        response["Content-Range"] = f"bytes {debut}-{fin}/{export.taille_zip}"
    return response
