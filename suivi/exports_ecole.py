"""Projection explicite d'une école vers le paquet local commun.

Les PK restent identiques dans cette base indépendante : les instantanés JSON
conservent ainsi leur sens. Aucune suppression ni écriture dans la base source.
"""
import copy
import hashlib
import os
import secrets
import shutil
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.exceptions import ValidationError
from django.db import connections, models, transaction
from django.db.models import Q
from django.utils import timezone

from comptes.models import Utilisateur
from . import models as m
from .autorisations import est_direction
from .paquet_local import creer_sauvegarde, preparer_restauration
from .sauvegardes_medias import _nom_valide


def autorise_export(utilisateur, ecole):
    return bool(not settings.MODE_LOCAL and ecole and (settings.EXPORT_ECOLES == "*" or ecole.pk in settings.EXPORT_ECOLES)
                and est_direction(utilisateur, ecole))


def racine():
    chemin = Path(settings.EXPORT_ROOT)
    if not settings.EXPORT_ROOT or not chemin.is_absolute():
        raise ValidationError("Le dossier privé des exports n'est pas configuré.")
    chemin = chemin.resolve()
    # Les exports ne doivent jamais être servis comme des médias ou statiques.
    for interdit in (settings.MEDIA_ROOT, settings.STATIC_ROOT):
        if interdit and chemin.is_relative_to(Path(interdit).resolve()):
            raise ValidationError("Le dossier des exports doit être hors des médias et des statiques.")
    chemin.mkdir(mode=0o700, parents=True, exist_ok=True)
    chemin.chmod(0o700)
    return chemin


def dossier(export):
    return racine() / str(export.identifiant)


def selections(ecole_id):
    """Liste blanche : chaque nouvelle table métier exige une décision explicite."""
    e = Q(ecole_id=ecole_id)
    sources = Q(source__ecole_id=ecole_id) | Q(source__ecole__isnull=True)
    annees = set(m.Classe.objects.filter(ecole_id=ecole_id).values_list("annee_scolaire", flat=True))
    annees.update(m.ChoixEcoleAnnuel.objects.filter(ecole_id=ecole_id).values_list("annee_scolaire", flat=True))
    annees.update(m.ReferentielAnnuel.objects.filter(ecole_id=ecole_id).values_list("annee_scolaire", flat=True))
    return {
        m.Ecole: Q(pk=ecole_id), m.ParametresCarnet: e,
        m.PolitiqueDoubleFacteurEcole: e, m.Classe: e, m.Eleve: e,
        m.Scolarite: Q(eleve__ecole_id=ecole_id),
        m.DemandeRapprochementEleve: e,
        m.AccesParcoursEleve: Q(eleve__ecole_id=ecole_id),
        m.Bilan: Q(scolarite__eleve__ecole_id=ecole_id),
        m.Domaine: e, m.SousDomaine: Q(domaine__ecole_id=ecole_id),
        m.Attendu: Q(domaine__ecole_id=ecole_id),
        m.Competence: Q(domaine__ecole_id=ecole_id),
        m.FormulationProposee: Q(competence__domaine__ecole_id=ecole_id),
        m.ReglagePresentation: e, m.FormulationLocale: e,
        m.Observation: Q(eleve__ecole_id=ecole_id),
        m.TraceCommune: Q(classe__ecole_id=ecole_id),
        m.Trace: Q(observation__eleve__ecole_id=ecole_id),
        m.EvenementAudit: e,
        m.SourceReferentiel: e | Q(ecole__isnull=True),
        m.VersionReferentiel: sources,
        m.IdentiteSourceCompetence: sources,
        m.DefinitionSourceCompetence: Q(version__source__ecole_id=ecole_id) | Q(version__source__ecole__isnull=True),
        m.CompetenceSourceEcole: e, m.VersionSourceEcole: e,
        m.ChoixApplicationAnnuel: Q(annee_scolaire__in=annees),
        m.ChoixEcoleAnnuel: e,
        m.PermissionChangementClasse: Q(classe__ecole_id=ecole_id),
        m.ReferentielAnnuel: e,
        m.AdoptionReferentiel: Q(classe__ecole_id=ecole_id),
        m.UsageCompetence: Q(adoption__classe__ecole_id=ecole_id),
        m.EtatAnnuelObservation: Q(observation__eleve__ecole_id=ecole_id),
        m.RessourceReferentiel: Q(annuel__ecole_id=ecole_id),
        m.AdaptationCompetence: e, m.CompetenceLocale: e,
        m.DisponibiliteCompetenceLocale: Q(locale__ecole_id=ecole_id),
        m.CorrespondanceCompetence: e,
        apps.get_model("comptes", "AppartenanceEcole"): e,
        apps.get_model("comptes", "ResponsabiliteEcole"): Q(appartenance__ecole_id=ecole_id),
        apps.get_model("comptes", "AffectationClasse"): Q(classe__ecole_id=ecole_id),
        apps.get_model("comptes", "Invitation"): e,
        apps.get_model("comptes", "AnomalieGouvernance"): e,
    }


def verifier_couverture(selection):
    excludes = {m.ExportEcole, Utilisateur,
                apps.get_model("comptes", "DoubleFacteurCompte"),
                apps.get_model("comptes", "CodeSecoursDoubleFacteur")}
    metier = {model for label in ("suivi", "comptes")
              for model in apps.get_app_config(label).get_models()}
    if metier != set(selection) | excludes:
        raise ValidationError("Le périmètre d'export doit être actualisé pour ce schéma.")


def _environnement_local(paquet):
    # Un processus local indépendant : pas d'axes ni de paramètres hébergés.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("CARNET_", "DATABASE_", "DJANGO_", "PETITS_PAS_"))}
    env.update(CARNET_MODE_LOCAL="oui", CARNET_ANTIBRUTEFORCE="non",
               CARNET_SQLITE_PATH=str(paquet / "carnet.sqlite3"),
               CARNET_MEDIA_ROOT=str(paquet / "media"),
               CARNET_SECRET_KEY=(paquet / "secret-key").read_text(encoding="utf-8"),
               CARNET_EMAIL_DESACTIVE="oui", DJANGO_SETTINGS_MODULE="carnet.settings")
    return env


def initialiser_base(paquet):
    cle = secrets.token_urlsafe(50)
    (paquet / "secret-key").write_text(cle, encoding="utf-8")
    (paquet / "secret-key").chmod(0o600)
    subprocess.run([sys.executable, str(settings.BASE_DIR / "manage.py"), "migrate", "--noinput"],
                   cwd=settings.BASE_DIR, env=_environnement_local(paquet), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def _place(root, octets):
    if shutil.disk_usage(root).free < octets + 128 * 1024**2:
        raise ValidationError("Espace temporaire insuffisant pour préparer l'export.")


def construire(export, travail):
    """Snapshot SQL cohérent ; médias référencés copiés avant fin du snapshot.

    Un média supprimé ou modifié pendant sa lecture fait échouer la copie.
    Les écritures ordinaires créent de nouveaux objets, sans modifier en place.
    """
    paquet = travail / "paquet"
    paquet.mkdir(mode=0o700)
    (paquet / "media").mkdir()
    initialiser_base(paquet)
    alias = "export_" + uuid4().hex
    config = copy.deepcopy(connections["default"].settings_dict)
    config.update(ENGINE="django.db.backends.sqlite3", NAME=str(paquet / "carnet.sqlite3"),
                  OPTIONS={}, ATOMIC_REQUESTS=False, CONN_MAX_AGE=0)
    connections.databases[alias] = config
    cible = connections[alias]
    utilisateurs = {export.demande_par_id}
    medias = {}
    total = 0
    try:
        with transaction.atomic(using="default"):
            source = connections["default"]
            if source.vendor == "postgresql":
                with source.cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            instantane = timezone.now()
            selection = selections(export.ecole_id)
            verifier_couverture(selection)
            ids = {model: set(model.objects.filter(condition).values_list("pk", flat=True))
                   for model, condition in selection.items()}
            # Fermer les relations vers les personnes sans suivre leurs écoles.
            # Une FK vers un objet d'une autre école est une anomalie : refus.
            with cible.constraint_checks_disabled(), transaction.atomic(using=alias):
                for model, condition in selection.items():
                    for objet in model.objects.filter(condition).order_by("pk").iterator(chunk_size=200):
                        record = serializers.serialize("python", [objet])[0]
                        fields = record["fields"]
                        for field in model._meta.concrete_fields:
                            if field.is_relation:
                                pk = getattr(objet, field.attname)
                                if pk is None:
                                    continue
                                if field.related_model is Utilisateur:
                                    utilisateurs.add(pk)
                                elif pk not in ids.get(field.related_model, set()):
                                    raise ValidationError("Une relation sort du périmètre de l'école ; export refusé.")
                            if isinstance(field, models.FileField):
                                fichier = getattr(objet, field.name)
                                if fichier.name:
                                    if not _nom_valide(fichier.name):
                                        raise ValidationError("Un chemin de média est invalide.")
                                    medias[fichier.name] = field.storage
                        for field in model._meta.many_to_many:
                            pks = fields[field.name]
                            if model is m.ChoixApplicationAnnuel:
                                fields[field.name] = [pk for pk in pks if pk in ids[field.related_model]]
                            elif any(pk not in ids.get(field.related_model, set()) for pk in pks):
                                raise ValidationError("Une relation sort du périmètre de l'école ; export refusé.")
                        if model is m.ChoixApplicationAnnuel:
                            fields["historique_permissions"] = []
                        if model._meta.label_lower == "comptes.invitation":
                            fields.update(etat="revoquee", selecteur=str(uuid4()), empreinte_jeton="")
                        for obj in serializers.deserialize("python", [record], using=alias):
                            obj.save(using=alias)
                for personne in Utilisateur.objects.filter(pk__in=utilisateurs).iterator(chunk_size=200):
                    # Liste blanche des attributs d'identité : pas de privilèges,
                    # sessions, groupes, permissions ou empreinte serveur.
                    fields = {nom: getattr(personne, nom) for nom in
                              ("username", "first_name", "last_name", "email", "date_joined")}
                    fields.update(password=export.mot_de_passe_local if personne.pk == export.demande_par_id else "!",
                                  is_active=personne.pk == export.demande_par_id,
                                  is_staff=False, is_superuser=False, last_login=None)
                    record = {"model": "comptes.utilisateur", "pk": personne.pk, "fields": fields}
                    for obj in serializers.deserialize("python", [record], using=alias):
                        obj.save(using=alias)
                cible.check_constraints()
            # Le snapshot doit rester ouvert jusqu'à la copie des médias.
            for nom, stockage in medias.items():
                taille = stockage.size(nom)
                total += taille
                if total > settings.EXPORT_TAILLE_MAX:
                    raise ValidationError("Le volume dépasse la limite d'export du service.")
                _place(travail, taille * 2 + total)
                chemin = paquet / "media" / nom
                chemin.parent.mkdir(parents=True, exist_ok=True)
                with stockage.open(nom, "rb") as entree, chemin.open("xb") as sortie:
                    # Lecture bornée, y compris si le storage renvoie un objet
                    # différent de celui annoncé par size().
                    copies = 0
                    while bloc := entree.read(1024**2):
                        copies += len(bloc)
                        if copies > taille:
                            raise ValidationError("Un média a changé pendant l'export.")
                        sortie.write(bloc)
                if copies != taille or stockage.size(nom) != taille:
                    raise ValidationError("Un média a changé pendant l'export.")
        cible.close()
        # Les clean() existants utilisent parfois le manager par défaut.
        # Les exécuter avec une connexion default indépendante de la source.
        subprocess.run([sys.executable, str(settings.BASE_DIR / "manage.py"), "shell", "-c",
                        "from suivi.exports_ecole import verifier_copie; verifier_copie()"],
                       cwd=settings.BASE_DIR, env=_environnement_local(paquet), check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        identifiant_local = Utilisateur.objects.using(alias).get(pk=export.demande_par_id).get_username()
        return paquet, instantane, identifiant_local
    finally:
        cible.close()
        del connections[alias]
        del connections.databases[alias]


def verifier_copie():
    if not settings.MODE_LOCAL or m.Ecole.objects.count() != 1:
        raise ValidationError("La copie doit contenir exactement une école.")
    selection = selections(m.Ecole.objects.get().pk)
    verifier_couverture(selection)
    for model in selection:
        if model is m.EvenementAudit:
            continue
        for objet in model.objects.all().iterator(chunk_size=200):
            objet.clean()


def produire(export):
    travail = dossier(export)
    travail.mkdir(mode=0o700)
    try:
        _place(travail, 128 * 1024**2)
        paquet, instantane, identifiant_local = construire(export, travail)
        volume = sum(p.stat().st_size for p in paquet.rglob("*") if p.is_file())
        if volume > settings.EXPORT_TAILLE_MAX:
            raise ValidationError("Le volume dépasse la limite d'export du service.")
        _place(travail, volume)
        archive = travail / "ecole.zip"
        creer_sauvegarde(paquet, archive, export_ecole={
            "version_application": settings.VERSION_APPLICATION,
            "identifiant": str(export.identifiant), "ecole_id_origine": export.ecole_id,
            "instantane_le": instantane.isoformat(),
            "connexion_locale": identifiant_local,
            "perimetre": "ecole_complete", "synchronisation": False,
        })
        # Validation commune réelle ; la copie vérifiée est immédiatement supprimée.
        _place(travail, volume)
        verifie = preparer_restauration(archive, travail, taille_max=settings.EXPORT_TAILLE_MAX)
        shutil.rmtree(verifie.etape)
        with archive.open("rb") as fichier:
            empreinte = hashlib.file_digest(fichier, "sha256").hexdigest()
        from pwa.limits import DATABASE_BYTES, MEDIA_FILE_BYTES, ZIP_BYTES, FILES
        fichiers = [p for p in paquet.rglob("*") if p.is_file()]
        # Le manifeste est aussi une entrée et compte dans le plafond total.
        from zipfile import ZipFile
        with ZipFile(archive) as z:
            volume_zip = sum(e.file_size for e in z.infolist())
            nombre = len(z.infolist())
        compatible = (volume_zip <= ZIP_BYTES and nombre <= FILES
                      and (paquet / "carnet.sqlite3").stat().st_size <= DATABASE_BYTES
                      and all(p.stat().st_size <= MEDIA_FILE_BYTES for p in fichiers))
        export.demande_par.refresh_from_db()
        export.ecole.refresh_from_db()
        if not autorise_export(export.demande_par, export.ecole):
            raise ValidationError("L'autorisation d'export n'est plus disponible.")
        m.ExportEcole.objects.filter(pk=export.pk, identifiant=export.identifiant).update(
            etat="pret", mot_de_passe_local="", identifiant_local=identifiant_local, instantane_le=instantane,
            expire_le=timezone.now() + timedelta(hours=24), taille_zip=archive.stat().st_size,
            taille_decompressee=volume_zip, fichiers=nombre, compatible_pwa=compatible,
            empreinte=empreinte, erreur="")
        archive.chmod(0o600)
        shutil.rmtree(paquet)
    except BaseException:
        shutil.rmtree(travail, ignore_errors=True)
        raise
