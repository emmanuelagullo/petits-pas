"""Copie indépendante d'une classe/année ; aucune extension des droits source."""
import copy
import hashlib
import shutil
from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.core import serializers
from django.core.exceptions import ValidationError
from django.db import connections, models, transaction
from django.db.models import Q
from django.utils import timezone

from comptes.models import Utilisateur, AppartenanceEcole, ResponsabiliteEcole, AffectationClasse
from . import models as m
from .autorisations import affectation_active, peut_telecharger_media_original, autorise, VOIR_SUIVI
from .export_projection import initialiser_projection, validation_sur
from .exports_ecole import dossier, selections, verifier_couverture, _place
from .paquet_local import creer_sauvegarde, preparer_restauration
from .referentiels import arbre_competences, observations_classe
from .sauvegardes_medias import _nom_valide


def autorise_export_classe(utilisateur, classe):
    if not classe or not utilisateur or not utilisateur.is_authenticated:
        return False
    permis = settings.EXPORT_CLASSES
    return bool((settings.MODE_LOCAL or permis == "*" or classe.ecole_id in permis)
                and affectation_active(utilisateur, classe, [AffectationClasse.RESPONSABLE]))


def _ids(queryset):
    return set(queryset.values_list("pk", flat=True))


def selection_classe(classe, utilisateur):
    """Liste blanche et fermeture du référentiel de la seule classe choisie."""
    selection = selections(classe.ecole_id)
    verifier_couverture(selection)
    resultat = {model: Q(pk__in=[]) for model in selection}
    eleves = _ids(classe.eleves)
    observations = observations_classe(classe).filter(eleve_id__in=eleves)
    etats = {o.pk: (o.statut_lecture, o.date_lecture, bool(o.connu_lecture)) for o in observations}
    textes = Q(pk__in=[])
    for eleve in classe.eleves:
        courante = eleve.scolarite_courante()
        if courante and courante.classe_id == classe.pk:
            textes |= Q(scolarite__eleve_id=eleve.pk)
        elif (courante and autorise(utilisateur, VOIR_SUIVI, courante.classe)
              and m.AccesParcoursEleve.objects.filter(eleve=eleve, classe=courante.classe).exists()):
            textes |= Q(scolarite__eleve_id=eleve.pk, visible_carnet=True)
    adoptions = m.AdoptionReferentiel.objects.filter(classe=classe)
    competences = {c.pk for d in arbre_competences(classe.ecole, classe=classe) for c in d.visibles}
    competences.update(observations.values_list("competence_id", flat=True))
    competences.update(m.UsageCompetence.objects.filter(adoption__in=adoptions).values_list("competence_id", flat=True))
    correspondances = m.CorrespondanceCompetence.objects.filter(
        Q(classe=classe) | Q(classe__isnull=True), ecole_id=classe.ecole_id,
        annee_scolaire=classe.annee_scolaire, active=True)
    # Les correspondances visibles peuvent relier une compétence d'une ancienne base.
    competences.update(correspondances.values_list("depart_id", flat=True))
    competences.update(correspondances.values_list("arrivee_id", flat=True))
    annuels = m.ReferentielAnnuel.objects.filter(pk__in=adoptions.values("annuel_id"))
    versions = set(adoptions.values_list("version_id", flat=True))
    versions.update(annuels.values_list("version_proposee_id", flat=True))
    versions.update(v for pair in correspondances.values_list("version_depart_id", "version_arrivee_id") for v in pair if v)
    origines = m.CompetenceSourceEcole.objects.filter(ecole_id=classe.ecole_id, competence_id__in=competences)
    definitions = m.DefinitionSourceCompetence.objects.filter(version_id__in=versions)
    identites = set(definitions.values_list("identite_id", flat=True))
    identites.update(origines.values_list("identite_id", flat=True))
    sources = set(m.VersionReferentiel.objects.filter(pk__in=versions).values_list("source_id", flat=True))
    sources.update(m.IdentiteSourceCompetence.objects.filter(pk__in=identites).values_list("source_id", flat=True))
    perimetre = Q(classe=classe) | Q(classe__isnull=True)
    resultat.update({
        m.Ecole: Q(pk=classe.ecole_id), m.ParametresCarnet: Q(ecole_id=classe.ecole_id),
        m.Classe: Q(pk=classe.pk), m.Eleve: Q(pk__in=eleves),
        m.Scolarite: Q(classe=classe, eleve_id__in=eleves),
        m.Observation: Q(pk__in=etats),
        m.Trace: textes & Q(scolarite__classe=classe, observation_id__in=etats, supprime_le__isnull=True),
        m.Bilan: textes & Q(scolarite__classe=classe, scolarite__eleve_id__in=eleves, supprime_le__isnull=True),
        m.Competence: Q(pk__in=competences),
        m.Domaine: Q(pk__in=m.Competence.objects.filter(pk__in=competences).values("domaine_id")),
        m.SousDomaine: Q(pk__in=m.Competence.objects.filter(pk__in=competences).values("sous_domaine_id")),
        m.Attendu: Q(domaine_id__in=m.Competence.objects.filter(pk__in=competences).values("domaine_id")),
        m.FormulationProposee: Q(competence_id__in=competences),
        m.ReglagePresentation: perimetre & Q(ecole_id=classe.ecole_id) & (Q(competence_id__in=competences) | Q(competence__isnull=True)),
        m.FormulationLocale: perimetre & Q(ecole_id=classe.ecole_id, competence_id__in=competences),
        m.SourceReferentiel: Q(pk__in=sources), m.VersionReferentiel: Q(pk__in=versions),
        m.IdentiteSourceCompetence: Q(pk__in=identites), m.DefinitionSourceCompetence: Q(pk__in=definitions.values("pk")),
        m.CompetenceSourceEcole: Q(pk__in=origines.values("pk")),
        m.VersionSourceEcole: Q(ecole_id=classe.ecole_id, version_id__in=versions),
        m.ReferentielAnnuel: Q(pk__in=annuels.values("pk")),
        m.AdoptionReferentiel: Q(classe=classe), m.UsageCompetence: Q(adoption__classe=classe),
        m.EtatAnnuelObservation: Q(observation_id__in=etats, annee_scolaire=classe.annee_scolaire),
        m.AdaptationCompetence: perimetre & Q(ecole_id=classe.ecole_id, annee_scolaire=classe.annee_scolaire, competence_id__in=competences),
        m.CompetenceLocale: Q(ecole_id=classe.ecole_id, competence_id__in=competences),
        m.DisponibiliteCompetenceLocale: perimetre & Q(locale__competence_id__in=competences, annee_scolaire=classe.annee_scolaire),
        m.CorrespondanceCompetence: Q(pk__in=correspondances.values("pk")),
    })
    # Ressources historiques : seulement les fichiers réellement désignés par
    # les présentations de cette classe. Un annuel peut servir plusieurs classes.
    ressources, photos = set(), set()
    for adoption in adoptions:
        final = adoption.etat_final
        ressources.update(final.get("ressources", []))
        for image in list(final.get("illustrations", {}).values()) + [final.get("couverture", {})]:
            if image.get("ressource_id"):
                ressources.add(image["ressource_id"])
        for reglage in adoption.annuel.etat_initial.get("reglages", []):
            if reglage.get("classe_id") in (None, classe.pk) and reglage.get("competence_id") in competences | {None}:
                if reglage.get("photo") and reglage.get("mode") == "remplacer":
                    photos.add(reglage["photo"])
    candidates = m.RessourceReferentiel.objects.filter(Q(annuel__in=annuels) & (Q(pk__in=ressources) | Q(fichier__in=photos)))
    autorisees = set()
    # Reprendre les conditions de media_referentiel : une ressource annuelle
    # n'est pas téléchargeable sur la seule foi d'une affectation historique.
    for eleve in classe.eleves:
        courante = eleve.scolarite_courante()
        if not courante or not autorise(utilisateur, VOIR_SUIVI, courante.classe):
            continue
        scolarites = eleve.scolarites.filter(pk=courante.pk)
        if m.AccesParcoursEleve.objects.filter(eleve=eleve, classe=courante.classe).exists():
            scolarites = eleve.scolarites.all()
        finales = m.AdoptionReferentiel.objects.filter(classe_id__in=scolarites.values("classe_id"), clos=True)
        for ressource in candidates:
            finale = any(ressource.pk in a.etat_final.get("ressources", []) for a in finales)
            initiale = any(sc.annee_scolaire == ressource.annuel.annee_scolaire
                and any(r.get("photo") == ressource.fichier.name and r.get("mode") == "remplacer"
                        and r.get("classe_id") in (None, sc.classe_id)
                        for r in ressource.annuel.etat_initial.get("reglages", [])) for sc in scolarites)
            if finale or initiale:
                autorisees.add(ressource.pk)
    resultat[m.RessourceReferentiel] = Q(pk__in=autorisees)
    return resultat, etats


def _transformer(objet, fields, classe, utilisateur, etats, ids, photos_autorisees, instantane):
    model = type(objet)
    if model is m.Trace:
        # Une attribution partagée contient déjà le texte individualisé. On
        # détache l'origine pour ne pas transporter ses autres attributions.
        fields.update(commune=None, origine_commune=None, supprime_par=None)
        if objet.photo and not peut_telecharger_media_original(utilisateur, objet):
            fields["photo"] = ""
    elif model is m.ReglagePresentation and objet.mode != m.ReglagePresentation.REMPLACER:
        fields["photo"] = ""
    elif model is m.Observation:
        statut, date, connu = etats[objet.pk]
        fields.update(statut=statut, date_observation=(date or m.bornes_annee_scolaire(classe.annee_scolaire)[0]).isoformat(),
                      modifie_le=instantane.isoformat())
    elif model is m.EtatAnnuelObservation:
        statut, date, connu = etats[objet.observation_id]
        fields.update(statut=statut, date_observation=date.isoformat() if date else None, connu=connu)
    elif model is m.CompetenceLocale and objet.classe_origine_id != classe.pk:
        fields["classe_origine"] = None
    elif model is m.ReferentielAnnuel:
        ancien = objet.etat_initial
        fields["etat_initial"] = {
            "reglages": [dict(r, photo=r.get("photo", "") if r.get("photo") in photos_autorisees and r.get("mode") == "remplacer" else "") for r in ancien.get("reglages", [])
                         if r.get("classe_id") in (None, classe.pk)
                         and r.get("competence_id") in ids[m.Competence] | {None}],
            "formulations_locales": [r for r in ancien.get("formulations_locales", [])
                                     if r.get("classe_id") in (None, classe.pk)
                                     and r.get("competence_id") in ids[m.Competence]],
        }
    elif model is m.AdoptionReferentiel:
        final = {nom: copy.deepcopy(valeur) for nom, valeur in objet.etat_final.items()
                 if nom in {"contenu", "illustrations", "propositions", "couverture", "etats", "correspondances", "ressources"}}
        if "etats" in final:
            final["etats"] = [e for e in final["etats"] if e.get("observation_id") in ids[m.Observation]]
        if "ressources" in final:
            final["ressources"] = [pk for pk in final["ressources"] if pk in ids[m.RessourceReferentiel]]
        for image in list(final.get("illustrations", {}).values()) + [final.get("couverture", {})]:
            if image.get("ressource_id") not in ids[m.RessourceReferentiel]:
                image.update(photo="", ressource_id=None)
        if objet.courante and not objet.clos:
            final["export_classe"] = {"instantane_le": instantane.isoformat()}
        fields["etat_final"] = final


def construire_classe(export, travail):
    classe, utilisateur = export.classe, export.demande_par
    if not autorise_export_classe(utilisateur, classe):
        raise ValidationError("L'autorisation d'export de la classe n'est plus disponible.")
    paquet = travail / "paquet"
    paquet.mkdir(mode=0o700)
    (paquet / "media").mkdir()
    initialiser_projection(paquet)
    alias = "export_" + uuid4().hex
    config = copy.deepcopy(connections["default"].settings_dict)
    config.update(ENGINE="django.db.backends.sqlite3", NAME=str(paquet / "carnet.sqlite3"),
                  OPTIONS={}, ATOMIC_REQUESTS=False, CONN_MAX_AGE=0)
    connections.databases[alias] = config
    cible = connections[alias]
    medias, personnes = {}, {utilisateur.pk}
    try:
        with transaction.atomic():
            if connections["default"].vendor == "postgresql":
                with connections["default"].cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            classe = m.Classe.objects.select_related("ecole").get(pk=export.classe_id)
            utilisateur = Utilisateur.objects.get(pk=export.demande_par_id)
            export.classe, export.demande_par = classe, utilisateur
            # Droits et contenu relus dans le même snapshot.
            if not autorise_export_classe(utilisateur, classe):
                raise ValidationError("L'autorisation d'export de la classe n'est plus disponible.")
            instantane = timezone.now()
            selection, etats = selection_classe(classe, utilisateur)
            ids = {model: _ids(model.objects.filter(condition)) for model, condition in selection.items()}
            photos_autorisees = set(m.RessourceReferentiel.objects.filter(selection[m.RessourceReferentiel]).values_list("fichier", flat=True))
            with cible.constraint_checks_disabled(), transaction.atomic(using=alias):
                for model, condition in selection.items():
                    for objet in model.objects.filter(condition).order_by("pk").iterator(chunk_size=200):
                        record = serializers.serialize("python", [objet])[0]
                        fields = record["fields"]
                        _transformer(objet, fields, classe, utilisateur, etats, ids, photos_autorisees, instantane)
                        for field in model._meta.concrete_fields:
                            if field.is_relation:
                                pk = fields.get(field.name)
                                if pk is not None:
                                    if field.related_model is Utilisateur:
                                        personnes.add(pk)
                                    elif pk not in ids.get(field.related_model, set()):
                                        raise ValidationError("Une relation sort du périmètre de la classe ; export refusé.")
                            if isinstance(field, models.FileField) and fields.get(field.name):
                                nom = fields[field.name]
                                if not _nom_valide(nom):
                                    raise ValidationError("Un chemin de média est invalide.")
                                medias[nom] = field.storage
                        for field in model._meta.many_to_many:
                            if any(pk not in ids.get(field.related_model, set()) for pk in fields[field.name]):
                                raise ValidationError("Une relation sort du périmètre de la classe ; export refusé.")
                        for obj in serializers.deserialize("python", [record], using=alias):
                            obj.save(using=alias)
                annuels = set(m.EtatAnnuelObservation.objects.using(alias).filter(
                    annee_scolaire=classe.annee_scolaire).values_list("observation_id", flat=True))
                m.EtatAnnuelObservation.objects.using(alias).bulk_create([
                    m.EtatAnnuelObservation(observation_id=pk, annee_scolaire=classe.annee_scolaire,
                        statut=statut, date_observation=date, connu=connu)
                    for pk, (statut, date, connu) in etats.items() if pk not in annuels])
                identifiant = None
                for personne in Utilisateur.objects.filter(pk__in=personnes).iterator(chunk_size=200):
                    courant = personne.pk == utilisateur.pk
                    if courant:
                        identifiant = personne.get_username()
                    fields = {"username": personne.username if courant else (f"historique-{personne.pk}" + ("-copie" if utilisateur.username.casefold() == f"historique-{personne.pk}" else "")),
                              "first_name": personne.first_name if courant or personne.get_full_name() else personne.username,
                              "last_name": personne.last_name,
                              "email": "", "date_joined": instantane,
                              "password": export.mot_de_passe_local if courant else "!",
                              "is_active": courant, "is_staff": False, "is_superuser": False, "last_login": None}
                    for obj in serializers.deserialize("python", [{"model": "comptes.utilisateur", "pk": personne.pk, "fields": fields}], using=alias):
                        obj.save(using=alias)
                # La copie indépendante doit être administrable. Ces droits
                # nouveaux ne concernent que la copie, pas l'école source.
                appartenance = AppartenanceEcole(utilisateur_id=utilisateur.pk, ecole_id=classe.ecole_id,
                    date_debut=timezone.localdate(), attribue_le=instantane)
                appartenance.save_base(raw=True, using=alias)
                direction = ResponsabiliteEcole(appartenance=appartenance, date_debut=timezone.localdate(), attribue_le=instantane)
                direction.save_base(raw=True, using=alias)
                affectation = AffectationClasse(appartenance=appartenance, classe_id=classe.pk,
                    type=AffectationClasse.RESPONSABLE, acces_historique=True,
                    date_debut=timezone.localdate(), attribue_le=instantane)
                affectation.save_base(raw=True, using=alias)
                cible.check_constraints()
            with validation_sur(alias):
                for model in selection:
                    for objet in model.objects.using(alias).all().iterator(chunk_size=200):
                        objet.clean()
                for model in (AppartenanceEcole, ResponsabiliteEcole, AffectationClasse):
                    for objet in model.objects.using(alias).all():
                        objet.clean()
        cible.close()
        return paquet, medias, instantane, identifiant
    finally:
        cible.close()
        del connections[alias]
        del connections.databases[alias]


def creer_zip_classe(export, travail, destination):
    paquet, medias, instantane, identifiant = construire_classe(export, travail)
    # Médias immuables lus directement par blocs : pas de copie MEMFS en PWA.
    externes = {"media/" + nom: (stockage.size(nom), lambda s=stockage, n=nom: s.open(n, "rb"))
                for nom, stockage in medias.items()}
    volume = sum(taille for taille, ouvrir in externes.values()) + (paquet / "carnet.sqlite3").stat().st_size
    if volume > settings.EXPORT_TAILLE_MAX:
        raise ValidationError("Le volume dépasse la limite d'export.")
    if getattr(settings, "MODE_PWA", False):
        from pwa.limits import ZIP_BYTES, DATABASE_BYTES, MEDIA_FILE_BYTES, FILES
        if (volume + 1024**2 > ZIP_BYTES or len(externes) + 3 > FILES
                or (paquet / "carnet.sqlite3").stat().st_size > DATABASE_BYTES
                or any(taille > MEDIA_FILE_BYTES for taille, _ in externes.values())):
            raise ValidationError("Le volume dépasse les limites actuelles du navigateur. Utilisez le programme Windows/Linux.")
    else:
        _place(travail, volume * 2)
    creer_sauvegarde(paquet, destination, taille_bloc=1024**2, fichiers_externes=externes,
        export_classe={"version_application": settings.VERSION_APPLICATION,
            "identifiant": str(export.identifiant), "ecole_id_origine": export.ecole_id,
            "classe_id_origine": export.classe_id, "annee_scolaire": export.classe.annee_scolaire,
            "instantane_le": instantane.isoformat(), "connexion_locale": identifiant,
            "perimetre": "classe_annee", "synchronisation": False})
    export.demande_par.refresh_from_db()
    export.classe.refresh_from_db()
    if not autorise_export_classe(export.demande_par, export.classe):
        raise ValidationError("L'autorisation d'export de la classe n'est plus disponible.")
    return instantane, identifiant


def produire_classe(export):
    travail = dossier(export)
    travail.mkdir(mode=0o700)
    try:
        archive = travail / "ecole.zip"  # Nom interne partagé avec le transport.
        instantane, identifiant = creer_zip_classe(export, travail, archive)
        verifie = preparer_restauration(archive, travail, taille_max=settings.EXPORT_TAILLE_MAX)
        shutil.rmtree(verifie.etape)
        from zipfile import ZipFile
        from pwa.limits import ZIP_BYTES, DATABASE_BYTES, MEDIA_FILE_BYTES, FILES
        with ZipFile(archive) as z:
            infos = z.infolist()
            volume = sum(e.file_size for e in infos)
            compatible = (volume <= ZIP_BYTES and len(infos) <= FILES
                and z.getinfo("carnet.sqlite3").file_size <= DATABASE_BYTES
                and all(e.file_size <= MEDIA_FILE_BYTES for e in infos))
        export.demande_par.refresh_from_db()
        export.classe.refresh_from_db()
        if not autorise_export_classe(export.demande_par, export.classe):
            raise ValidationError("L'autorisation d'export de la classe n'est plus disponible.")
        with archive.open("rb") as f:
            empreinte = hashlib.file_digest(f, "sha256").hexdigest()
        m.ExportClasse.objects.filter(pk=export.pk, identifiant=export.identifiant).update(
            etat="pret", mot_de_passe_local="", identifiant_local=identifiant,
            instantane_le=instantane, expire_le=timezone.now() + timedelta(hours=24),
            taille_zip=archive.stat().st_size, taille_decompressee=volume,
            fichiers=len(infos), compatible_pwa=compatible, empreinte=empreinte, erreur="")
        archive.chmod(0o600)
        shutil.rmtree(travail / "paquet")
    except BaseException:
        shutil.rmtree(travail, ignore_errors=True)
        raise
