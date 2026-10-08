"""ZIP local → nouvelle école : projection sans capacités ni identités de connexion.

Le SQLite fourni est une source en lecture seule, jamais la base du service.
Chaque table et chaque structure JSON doivent être examinées explicitement.
"""
import copy
import hashlib
import json
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager, closing
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage, default_storage
from django.db import connections, models, transaction
from django.db.migrations.loader import MigrationLoader
from django.utils.dateparse import parse_datetime

from comptes.models import Utilisateur, AppartenanceEcole, ResponsabiliteEcole
from . import models as m
from .export_projection import validation_sur
from .exports_ecole import selections, verifier_couverture
from .paquet_local import preparer_restauration, TAILLE_MAX
from .sauvegardes_medias import _nom_valide

# Les politiques, appartenances, affectations, invitations et accès historiques
# sont à décider sur le service. Aucun journal importé ne devient son audit.
EXCLUS = {
    m.PolitiqueDoubleFacteurEcole, m.DemandeRapprochementEleve, m.AccesParcoursEleve,
    m.EvenementAudit, m.ChoixApplicationAnnuel, m.ChoixEcoleAnnuel,
    m.PermissionChangementClasse,
    *(apps.get_model('comptes', nom) for nom in (
        'AppartenanceEcole', 'ResponsabiliteEcole', 'AffectationClasse',
        'Invitation', 'AnomalieGouvernance')),
}
RUBRIQUES = {'domaines': m.Domaine, 'sous_domaines': m.SousDomaine,
             'attendus': m.Attendu, 'competences': m.Competence,
             'formulations': m.FormulationProposee}
REFERENCES = {'domaine_id': m.Domaine, 'sous_domaine_id': m.SousDomaine,
              'competence_id': m.Competence, 'classe_id': m.Classe,
              'origine_id': m.FormulationProposee, 'origine_locale_id': m.FormulationLocale,
              'observation_id': m.Observation, 'ressource_id': m.RessourceReferentiel,
              'depart_id': m.Competence, 'arrivee_id': m.Competence,
              'auteur_id': Utilisateur, 'version_id': m.VersionReferentiel,
              'locale_id': m.CompetenceLocale}
LIGNES_MAX = 200_000
BASE_MAX = 64 * 1024**2


def verifier_serveur():
    if settings.MODE_LOCAL or settings.ENVIRONNEMENT_EPHEMERE or settings.ENVIRONNEMENT_ATELIER:
        raise ValidationError("L'import exige un serveur persistant ordinaire.")


@contextmanager
def source_sqlite(chemin):
    alias = 'export_import_' + uuid4().hex
    config = copy.deepcopy(connections['default'].settings_dict)
    config.update(ENGINE='django.db.backends.sqlite3',
                  NAME=chemin.resolve().as_uri() + '?mode=ro',
                  OPTIONS={'uri': True}, ATOMIC_REQUESTS=False, CONN_MAX_AGE=0)
    connections.databases[alias] = config
    try:
        with connections[alias].cursor() as cursor:
            cursor.execute('PRAGMA query_only=ON')
            cursor.execute('PRAGMA trusted_schema=OFF')
        yield alias
    finally:
        connections[alias].close()
        del connections[alias]
        del connections.databases[alias]


class Projection:
    def __init__(self, alias, paquet):
        self.alias, self.paquet = alias, paquet
        with validation_sur(alias):
            if m.Ecole.objects.count() != 1:
                raise ValidationError("Le ZIP doit contenir exactement une école.")
            self.ecole = m.Ecole.objects.get()
            selection = selections(self.ecole.pk)
            verifier_couverture(selection)
            self.modeles = set(selection) - EXCLUS
            self.lignes = {}
            total = 0
            for model in self.modeles:
                # Refuser aussi les lignes hors école qui seraient cachées par le filtre.
                compte = model.objects.count()
                if model.objects.filter(selection[model]).count() != compte:
                    raise ValidationError("Des données sortent du périmètre de l'école.")
                total += compte
                if total > LIGNES_MAX:
                    raise ValidationError("Le ZIP dépasse la limite de lignes de cet import.")
                self.lignes[model] = list(model.objects.order_by('pk').values())
            personnes = set()
            for model, lignes in self.lignes.items():
                for champ in model._meta.concrete_fields:
                    if champ.is_relation and champ.related_model is Utilisateur:
                        personnes.update(r[champ.attname] for r in lignes if r[champ.attname] is not None)
            # Les comptes sans relation pédagogique ne sont pas transportés.
            self.lignes[Utilisateur] = list(Utilisateur.objects.filter(pk__in=personnes).values(
                'id', 'first_name', 'last_name', 'username'))
            if len(self.lignes[Utilisateur]) != len(personnes):
                raise ValidationError("Une identité historique est introuvable.")
        self.ids = {model: {r['id']: r['id'] for r in lignes} for model, lignes in self.lignes.items()}
        for model, lignes in self.lignes.items():
            if model is Utilisateur:
                continue
            for r in lignes:
                for champ in model._meta.concrete_fields:
                    if champ.is_relation:
                        self.ref(champ.related_model, r[champ.attname])
        self.medias = {}
        for model, lignes in self.lignes.items():
            for champ in model._meta.concrete_fields:
                if isinstance(champ, models.FileField):
                    for r in lignes:
                        self.media(r[champ.attname])
        # Validation des JSON et de leurs références avant toute écriture serveur.
        self.transformer_json()
        with validation_sur(alias):
            for model in self.modeles:
                for r in self.lignes[model]:
                    objet = model(**r)
                    objet._state.adding = False
                    objet._state.db = alias
                    if model is m.Classe and objet.etat != m.Classe.ARCHIVEE:
                        objet.etat = m.Classe.PREPARATION
                    self.valider(objet)
        self.rapport = {
            'ecole': self.ecole.nom, 'commune': self.ecole.commune,
            'classes': len(self.lignes[m.Classe]), 'eleves': len(self.lignes[m.Eleve]),
            'traces': len(self.lignes[m.Trace]), 'bilans': len(self.lignes[m.Bilan]),
            'annees': sorted({r['annee_scolaire'] for r in self.lignes[m.Classe]}),
            'medias': len(self.medias),
            'octets_medias': sum((paquet / 'media' / nom).stat().st_size for nom in self.medias),
            'auteurs_historiques': len(self.lignes[Utilisateur]),
        }

    @staticmethod
    def valider(objet):
        # Certains instantanés existants ont un JSON vide malgré blank=False.
        # Leurs structures sont contrôlées séparément, pas par le validateur de vide.
        exclus = [f.name for f in objet._meta.concrete_fields
                  if isinstance(f, models.JSONField) and getattr(objet, f.name) in ({}, [])]
        objet.full_clean(exclude=exclus)
        if isinstance(objet, m.Observation) and objet.eleve.ecole_id != objet.competence.domaine.ecole_id:
            raise ValidationError("Une observation sort de son école.")
        if isinstance(objet, m.Trace) and (objet.observation.eleve_id != objet.scolarite.eleve_id
                or objet.observation.eleve.ecole_id != objet.scolarite.classe.ecole_id):
            raise ValidationError("Une trace sort de son élève ou de son école.")
        if isinstance(objet, (m.Trace, m.TraceCommune)):
            classe_id = objet.scolarite.classe_id if isinstance(objet, m.Trace) else objet.classe_id
            competence_id = objet.observation.competence_id if isinstance(objet, m.Trace) else objet.competence_id
            if objet.usage_referentiel_id and (
                    objet.usage_referentiel.adoption.classe_id != classe_id
                    or objet.usage_referentiel.competence_id != competence_id):
                raise ValidationError("Le contexte d'une trace est incohérent.")
            if isinstance(objet, m.Trace):
                for commune in (objet.commune, objet.origine_commune):
                    if commune and (commune.classe_id != classe_id or commune.competence_id != competence_id):
                        raise ValidationError("L'origine partagée d'une trace est incohérente.")

    def ref(self, model, valeur):
        if valeur is None:
            return None
        if type(valeur) is not int or valeur not in self.ids.get(model, {}):
            raise ValidationError("Une référence du ZIP est absente ou hors périmètre.")
        return self.ids[model][valeur]

    def media(self, nom):
        if not nom:
            return nom
        if not _nom_valide(nom) or not (self.paquet / 'media' / nom).is_file():
            raise ValidationError("Un média référencé est invalide ou absent du ZIP.")
        return self.medias.setdefault(nom, nom)

    def cle(self, valeur):
        if not isinstance(valeur, str):
            raise ValidationError("Clé de définition invalide.")
        for prefixe, model in (('locale-', m.Competence), ('source-', m.IdentiteSourceCompetence)):
            if valeur.startswith(prefixe):
                try:
                    return prefixe + str(self.ref(model, int(valeur[len(prefixe):])))
                except ValueError:
                    break
        raise ValidationError("Clé de définition inconnue.")

    def reference(self, valeur):
        morceaux = valeur.split(':')
        try:
            if len(morceaux) == 2 and morceaux[0] == 'ajout':
                return 'ajout:' + str(self.ref(m.CompetenceLocale, int(morceaux[1])))
            if len(morceaux) == 3 and morceaux[0] == 'base':
                return f'base:{self.ref(m.VersionReferentiel, int(morceaux[1]))}:{self.ref(m.Competence, int(morceaux[2]))}'
        except (ValueError, TypeError):
            pass
        raise ValidationError("Référence de correspondance inconnue.")

    def ligne_json(self, valeur, model=None):
        if not isinstance(valeur, dict):
            raise ValidationError("Ligne d'instantané invalide.")
        permis = ({f.attname for f in model._meta.concrete_fields} | {'cle_definition', 'type_libelle'}
                  if model else set(REFERENCES) | {
                      'reference', 'libelle', 'code', 'niveau', 'origine',
                      'provenance', 'icone', 'photo', 'statut', 'date_observation', 'connu'})
        if set(valeur) - permis:
            raise ValidationError("Champs d'instantané non pris en charge.")
        if model:
            for champ in model._meta.concrete_fields:
                if (champ.attname in valeur and not champ.is_relation
                        and not isinstance(champ, (models.JSONField, models.FileField))):
                    champ.clean(valeur[champ.attname], None)
        resultat = copy.deepcopy(valeur)
        for cle, val in valeur.items():
            if cle == 'id' and model:
                resultat[cle] = self.ref(model, val)
            elif cle in REFERENCES:
                resultat[cle] = self.ref(REFERENCES[cle], val)
            elif cle.endswith('_id') or cle == 'id':
                raise ValidationError("Identifiant d'instantané non pris en charge.")
            elif cle == 'photo':
                resultat[cle] = self.media(val)
            elif cle == 'cle_definition':
                resultat[cle] = self.cle(val)
            elif cle == 'reference':
                resultat[cle] = self.reference(val)
            elif cle in ('origine_depart', 'origine_arrivee'):
                resultat[cle] = self.ligne_json(val)
        return resultat

    def contenu(self, valeur):
        if not isinstance(valeur, dict):
            raise ValidationError("Contenu de référentiel invalide.")
        resultat = copy.deepcopy(valeur)
        # Les définitions fournies déclarées ont des identités textuelles,
        # tandis que leurs projections d'école ont des PK dans les listes plates.
        if valeur.get('origine') == 'source_declaree' and 'competences' not in valeur:
            from .services.import_sources_referentiels import normaliser
            normaliser({k: v for k, v in valeur.items() if k != 'origine'})
            return resultat
        if set(valeur) - set(RUBRIQUES) - {'format', 'origine', 'source'}:
            raise ValidationError("Structure de référentiel non prise en charge.")
        for rubrique, model in RUBRIQUES.items():
            if rubrique in valeur:
                resultat[rubrique] = [self.ligne_json(r, model) for r in valeur[rubrique]]
        return resultat

    def initial(self, valeur):
        if not isinstance(valeur, dict) or set(valeur) - {'reglages', 'formulations_locales', 'avertissement'}:
            raise ValidationError("Instantané initial non pris en charge.")
        resultat = copy.deepcopy(valeur)
        for cle, model in (('reglages', m.ReglagePresentation), ('formulations_locales', m.FormulationLocale)):
            if cle in valeur:
                resultat[cle] = [self.ligne_json(r, model) for r in valeur[cle]]
        return resultat

    def final(self, valeur):
        if not isinstance(valeur, dict) or set(valeur) - {
                'contenu', 'illustrations', 'propositions', 'couverture', 'etats',
                'correspondances', 'ressources', 'export_classe'}:
            raise ValidationError("Instantané final non pris en charge.")
        resultat = copy.deepcopy(valeur)
        for cle, val in valeur.items():
            if cle == 'contenu':
                resultat[cle] = self.contenu(val)
            elif cle in ('illustrations', 'propositions'):
                resultat[cle] = {str(self.ref(m.Competence, int(pk))):
                    self.ligne_json(v) if cle == 'illustrations' else [self.proposition(p) for p in v]
                    for pk, v in val.items()}
            elif cle == 'couverture':
                resultat[cle] = self.ligne_json(val)
            elif cle == 'etats':
                resultat[cle] = [self.ligne_json(e) for e in val]
            elif cle == 'correspondances':
                resultat[cle] = [self.ligne_json(e, m.CorrespondanceCompetence) for e in val]
            elif cle == 'ressources':
                resultat[cle] = [self.ref(m.RessourceReferentiel, pk) for pk in val]
            elif cle == 'export_classe':
                if (set(val) != {'instantane_le'} or not isinstance(val['instantane_le'], str)
                        or parse_datetime(val['instantane_le']) is None):
                    raise ValidationError("Date d'extraction de classe invalide.")
        return resultat

    def proposition(self, valeur):
        if not isinstance(valeur, dict) or set(valeur) - {
                'cle', 'texte', 'provenance', 'masquee', 'mode', 'ajoutee_ici', 'texte_local'}:
            raise ValidationError("Proposition finale non prise en charge.")
        resultat = copy.deepcopy(valeur)
        cle = valeur.get('cle', '')
        for prefixe, model in (('base-', m.FormulationProposee), ('locale-', m.FormulationLocale)):
            if cle.startswith(prefixe):
                resultat['cle'] = prefixe + str(self.ref(model, int(cle[len(prefixe):])))
                return resultat
        raise ValidationError("Clé de proposition finale inconnue.")

    def transformer_json(self):
        resultat = {}
        for model, lignes in self.lignes.items():
            for r in lignes:
                champs = {}
                for champ in model._meta.concrete_fields:
                    if not isinstance(champ, models.JSONField):
                        continue
                    valeur = r[champ.attname]
                    if model is m.ReferentielAnnuel:
                        champs[champ.attname] = self.initial(valeur)
                    elif model is m.AdoptionReferentiel and champ.name == 'etat_final':
                        champs[champ.attname] = self.final(valeur)
                    elif model is m.CorrespondanceCompetence:
                        champs[champ.attname] = self.ligne_json(valeur)
                    else:
                        champs[champ.attname] = self.contenu(valeur)
                if model is m.UsageCompetence:
                    champs['cle_definition'] = self.cle(r['cle_definition'])
                if model is m.CorrespondanceCompetence:
                    for champ in ('reference_depart', 'reference_arrivee'):
                        champs[champ] = self.reference(r[champ])
                resultat[(model, r['id'])] = champs
        return resultat

    def importer(self, direction, nom, commune, operateur):
        from .reprise_import import verrou_imports, journaliser
        verifier_serveur()
        with verrou_imports() as racine:
            identifiant = uuid4().hex
            # Écrit et synchronisé avant tout média et toute transaction.
            # Le succès se déduit exclusivement de l'audit SQL atomique.
            journaliser(racine, identifiant, etat='commence', sha256=self.rapport['sha256'])
            return self._importer(direction, nom, commune, operateur, identifiant)

    def _importer(self, direction, nom, commune, operateur, identifiant):
        verifier_serveur()
        if not isinstance(default_storage, FileSystemStorage):
            raise ValidationError("Cette première version de l'import exige des médias sur disque local.")
        direction_creee = direction.pk is None
        destination = Path(default_storage.path('imports/' + identifiant))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.mkdir(mode=0o700)
        # Nouveau préfixe non devinable ; aucun fichier existant n'est remplacé.
        try:
            with transaction.atomic():
                if connections['default'].vendor == 'postgresql':
                    with connections['default'].cursor() as cursor:
                        # Coordination des imports concurrents du déploiement.
                        cursor.execute('SELECT pg_advisory_xact_lock(1886417001, 1)')
                operateur = Utilisateur.objects.select_for_update().get(pk=operateur.pk)
                if not operateur.is_active or not operateur.is_staff:
                    raise ValidationError("L'opérateur doit être un compte technique actif.")
                if direction.pk is None:
                    direction.full_clean()
                    direction.save()
                direction = Utilisateur.objects.select_for_update().get(pk=direction.pk)
                if not direction.is_active:
                    raise ValidationError("Le compte de direction doit être actif.")
                if m.Ecole.objects.filter(nom__iexact=nom, commune__iexact=commune).exists():
                    raise ValidationError("Une école de même nom et commune existe déjà.")
                if m.EvenementAudit.objects.filter(action='ecole.import_zip',
                        nouvelles_valeurs__sha256=self.rapport['sha256']).exists():
                    raise ValidationError("Ce ZIP a déjà été importé ; consulter l'école créée.")
                self.ids = {model: {} for model in self.lignes}
                # Les callbacks save() décrivent des éditions utilisateur, pas
                # cette projection. Champs, contraintes et clean() sont contrôlés
                # après insertion, avant la validation de la transaction.
                restants = set(self.lignes)
                while restants:
                    prets = [model for model in restants if all(
                        not f.is_relation or f.related_model is model
                        or f.related_model not in restants for f in model._meta.concrete_fields)]
                    if not prets:
                        raise ValidationError("Cycle de relations non pris en charge par l'import.")
                    for model in sorted(prets, key=lambda mod: mod._meta.label_lower):
                        for r in self.lignes[model]:
                            if model is Utilisateur:
                                values = dict(username=f'historique-{identifiant}-{r["id"]}',
                                    first_name=r['first_name'] or (r['username'] if not r['last_name'] else ''),
                                    last_name=r['last_name'], email='', password='!',
                                    is_active=False, is_staff=False, is_superuser=False)
                                # L'ancien nom de connexion n'est jamais utilisable.
                                values['first_name'] = values['first_name'][:150]
                            else:
                                values = {k: copy.deepcopy(v) for k, v in r.items() if k != 'id'}
                                for f in model._meta.concrete_fields:
                                    if f.is_relation:
                                        values[f.attname] = None if f.related_model is model else self.ref(f.related_model, r[f.attname])
                                    elif isinstance(f, models.JSONField):
                                        values[f.attname] = {}
                                    elif isinstance(f, models.FileField):
                                        values[f.attname] = self.media(r[f.attname])
                                if model is m.Ecole:
                                    values.update(nom=nom, commune=commune, etat=m.Ecole.ACTIVE)
                                elif model is m.Classe and values['etat'] != m.Classe.ARCHIVEE:
                                    values['etat'] = m.Classe.PREPARATION
                                elif model is m.SourceReferentiel:
                                    values['ecole_id'] = self.ref(m.Ecole, self.ecole.pk)
                                    values['identifiant'] = (f'reprise-ecole-{values["ecole_id"]}'
                                        if r['identifiant'] == f'reprise-ecole-{self.ecole.pk}'
                                        else f'import-{identifiant}-{r["id"]}')
                            objet = model(**values)
                            model.objects.bulk_create([objet])
                            self.ids[model][r['id']] = objet.pk
                            # pre_save() remplace les dates automatiques pendant
                            # bulk_create ; restaurer explicitement les dates historiques.
                            dates = {f.attname: r[f.attname] for f in model._meta.concrete_fields
                                     if (getattr(f, 'auto_now', False) or getattr(f, 'auto_now_add', False))
                                     and f.attname in r}
                            if dates:
                                model.objects.filter(pk=objet.pk).update(**dates)
                        restants.remove(model)
                self.medias = {nom: f'imports/{identifiant}/{uuid4().hex}{Path(nom).suffix[:16]}'
                               for nom in self.medias}
                jsons = self.transformer_json()
                for model, lignes in self.lignes.items():
                    for r in lignes:
                        changements = jsons[(model, r['id'])]
                        for f in model._meta.concrete_fields:
                            if f.is_relation and f.related_model is model:
                                changements[f.attname] = self.ref(model, r[f.attname])
                            if isinstance(f, models.FileField):
                                changements[f.attname] = self.media(r[f.attname])
                        if model is m.VersionReferentiel:
                            changements['empreinte'] = hashlib.sha256(json.dumps(
                                changements['contenu'], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                        if changements:
                            model.objects.filter(pk=self.ids[model][r['id']]).update(**changements)
                for model in self.lignes:
                    for objet in model.objects.filter(pk__in=self.ids[model].values()).iterator(chunk_size=200):
                        self.valider(objet)
                ecole = m.Ecole.objects.get(pk=self.ref(m.Ecole, self.ecole.pk))
                appartenance = AppartenanceEcole.objects.create(utilisateur=direction, ecole=ecole,
                    attribue_par=operateur, motif="Import d'un ZIP local vers une nouvelle école")
                ResponsabiliteEcole.objects.create(appartenance=appartenance,
                    type=ResponsabiliteEcole.DIRECTION, attribue_par=operateur)
                from .acces_double_facteur import poser_echeance_si_besoin, fermer_sessions_compte
                poser_echeance_si_besoin(direction, delai_de_grace=False)
                if settings.DOUBLE_FACTEUR_DISPONIBLE:
                    fermer_sessions_compte(direction)
                # Les médias restent progressifs et privés, sans recompression.
                for ancien, nouveau in self.medias.items():
                    cible = Path(default_storage.path(nouveau))
                    cible.parent.mkdir(parents=True, exist_ok=True)
                    with (self.paquet / 'media' / ancien).open('rb') as entree, cible.open('xb') as sortie:
                        shutil.copyfileobj(entree, sortie, length=1024**2)
                    cible.chmod(0o600)
                m.EvenementAudit.objects.create(ecole=ecole, acteur=operateur,
                    action='ecole.import_zip', modele=m.Ecole._meta.label_lower, objet_id=str(ecole.pk),
                    nouvelles_valeurs={'sha256': self.rapport['sha256'], 'classes': self.rapport['classes'],
                                      'eleves': self.rapport['eleves'], 'droits_recrees': False,
                                      'direction_id': direction.pk,
                                      'direction_creee': direction_creee,
                                      'medias_prefixe': f'imports/{identifiant}/'})
            return ecole
        except BaseException:
            shutil.rmtree(destination)
            raise


@contextmanager
def verifier_zip(archive, parent):
    verifier_serveur()
    # Copie privée et hash d'un même flux : l'opérateur confirme exactement ces octets.
    with tempfile.TemporaryDirectory(prefix='import-ecole-', dir=parent) as dossier:
        root = Path(dossier)
        somme = hashlib.sha256()
        with Path(archive).open('rb') as entree, (root / 'source.zip').open('xb') as sortie:
            taille = 0
            while bloc := entree.read(1024**2):
                taille += len(bloc)
                if taille > TAILLE_MAX + 128 * 1024**2:
                    raise ValidationError("Le ZIP dépasse la limite d'import.")
                sortie.write(bloc)
                somme.update(bloc)
        # Le validateur commun lit la clé en texte après décompression. Borner
        # aussi cette petite entrée avant son ouverture, même pour un ZIP hostile.
        with ZipFile(root / 'source.zip') as archive_zip:
            if archive_zip.getinfo('secret-key').file_size > 4096:
                raise ValidationError("La clé du paquet dépasse la taille autorisée.")
            if archive_zip.getinfo('carnet.sqlite3').file_size > BASE_MAX:
                raise ValidationError("La base SQLite dépasse le plafond d'import de 64 Mio.")
        preparation = preparer_restauration(root / 'source.zip', root)
        db = preparation.etape / 'carnet.sqlite3'
        if db.stat().st_size > BASE_MAX:
            raise ValidationError("La base SQLite dépasse le plafond d'import de 64 Mio.")
        with closing(sqlite3.connect(db)) as source:
            source.execute('PRAGMA trusted_schema=OFF')
            if source.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view')").fetchone():
                raise ValidationError("Le SQLite contient des vues ou déclencheurs non autorisés.")
            appliquees = set(source.execute('SELECT app,name FROM django_migrations').fetchall())
            connues = set(MigrationLoader(connections['default']).disk_migrations)
            if appliquees - connues or {p for p in connues if p[0] in ('suivi', 'comptes')} - appliquees:
                raise ValidationError("Version du ZIP incompatible : utiliser les mêmes migrations métier que le serveur.")
        with source_sqlite(db) as alias:
            projection = Projection(alias, preparation.etape)
            projection.rapport['sha256'] = somme.hexdigest()
            projection.rapport['deja_importe_ecoles'] = list(m.EvenementAudit.objects.filter(
                action='ecole.import_zip', nouvelles_valeurs__sha256=somme.hexdigest()).values_list('ecole_id', flat=True))
            yield projection
