#!/usr/bin/env python3
"""Mesures locales sur un paquet temporaire exclusivement fictif.

Usage : python scripts/auditer-performance.py --sortie /tmp/mesures.json
Aucune base ni configuration d'exploitation n'est utilisée.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import statistics
import sys
from tempfile import TemporaryDirectory
import time
from collections import Counter
from io import StringIO

ROOT = Path(os.environ.get('AUDIT_RACINE', Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(ROOT))


def run(args, paquet):
    for key in list(os.environ):
        if key.startswith(('CARNET_', 'PETITS_PAS_', 'RENDER_', 'DJANGO_')) or key == 'DATABASE_URL':
            del os.environ[key]
    os.environ.update(DJANGO_SETTINGS_MODULE='carnet.settings', CARNET_MODE_LOCAL='oui',
        CARNET_EMAIL_DESACTIVE='oui', CARNET_VERSION='audit-fictif', CARNET_SQLITE_PATH=str(paquet / 'carnet.sqlite3'),
        CARNET_MEDIA_ROOT=str(paquet / 'media'), CARNET_STATIC_ROOT=str(paquet / 'staticfiles'), CARNET_DEBUG='0')
    import django
    django.setup()
    from django.contrib.auth import get_user_model
    from django.core.management import call_command
    from django.db import connection
    from django.test import Client, override_settings
    from django.test.utils import CaptureQueriesContext
    from django.urls import reverse
    from django.utils import timezone
    from comptes.models import AffectationClasse, AppartenanceEcole, ResponsabiliteEcole
    from suivi.models import Ecole, Classe, Eleve, Scolarite, Observation, Trace, Bilan
    from suivi.services.import_sources_referentiels import importer_source
    from suivi.services.choix_bases_referentiels import publier_choix_application
    from suivi.services.adoption_bases_referentiels import apercu_adoption, adopter_base
    from suivi.services.traces_communes import enregistrer_commune
    import yaml

    call_command('migrate', verbosity=0, stdout=StringIO())
    call_command('collectstatic', verbosity=0, interactive=False, stdout=StringIO())
    paquet.joinpath('media').mkdir()
    paquet.joinpath('secret-key').write_text('cle-publique-fictive-pour-audit-seulement')
    # Données binaires fictives : 2 Mio pour inclure la compression du ZIP.
    import random
    paquet.joinpath('media/fictif.bin').write_bytes(random.Random(17).randbytes(2 * 1024**2))
    doc = {'format': 1, 'source': {'identifiant': 'performance-fictive', 'titre': 'Progression fictive',
        'provenance': 'Audit fictif', 'licence': 'CC-BY-SA-4.0', 'provisoire': True}, 'version': '1',
        'domaines': [{'code': 'LANG', 'nom': 'Langage', 'competences': [
            {'identite': f'c-{i}', 'code': f'C{i}', 'libelle': f'Compétence fictive {i}', 'niveau': ['PS','MS','GS'][i%3]}
            for i in range(20)]}]}
    small = importer_source(yaml.safe_dump(doc, allow_unicode=True))[0]
    large = importer_source(ROOT.joinpath('referentiel/chatdecole/tableaux-cycle1.yaml').read_text())[0]
    annee = f'{timezone.localdate().year}-{timezone.localdate().year + 1}'
    publier_choix_application(annee=annee, versions_ids=[small.pk, large.pk], proposee_id=small.pk, revision_attendue=0)
    results = []
    scenarios = ([(5, large, 1), (30, large, 10)] if args.complements else
                 [(5, small, 1), (30, small, 1), (5, large, 1), (30, large, 1), (30, large, 10)])
    for n, version, traces_count in scenarios:
        label = f'{n}e-{version.definitions.count()}c-{traces_count}t'
        print('Préparation ' + label, flush=True)
        ecole = Ecole.objects.create(nom='École fictive ' + label)
        teacher = get_user_model().objects.create_user(username='responsable-' + label)
        director = get_user_model().objects.create_user(username='direction-' + label)
        contributor = get_user_model().objects.create_user(username='contributeur-' + label)
        membre = AppartenanceEcole.objects.create(utilisateur=teacher, ecole=ecole)
        ResponsabiliteEcole.objects.create(appartenance=AppartenanceEcole.objects.create(utilisateur=director, ecole=ecole), type='direction')
        classe = Classe.objects.create(ecole=ecole, nom='Classe fictive', annee_scolaire=annee)
        AffectationClasse.objects.create(appartenance=membre, classe=classe, type='responsable')
        AffectationClasse.objects.create(appartenance=AppartenanceEcole.objects.create(utilisateur=contributor, ecole=ecole), classe=classe, type='contributeur')
        classe.activer()
        apercu = apercu_adoption(utilisateur=teacher, classe=classe, version_id=version.pk)
        adoption = adopter_base(utilisateur=teacher, classe=classe, version_id=version.pk,
            revisions_attendues=apercu['revisions'], adoption_attendue=apercu['adoption_id'], garde_attendue=apercu['garde']['empreinte'])
        classe.activer()
        competences = list(adoption.usages.select_related('competence').order_by('competence_id'))
        pupils = []
        for i in range(n):
            pupil = Eleve.objects.create(ecole=ecole, prenom=f'Fictif {i:02d}')
            pupils.append(pupil)
            sc = Scolarite.objects.create(eleve=pupil, classe=classe, annee_scolaire=annee, niveau=['PS','MS','GS'][i%3])
            Bilan.objects.create(scolarite=sc, date_bilan=timezone.localdate(), texte='Bilan fictif pour les mesures.')
            for usage in competences[:min(20, len(competences))]:
                obs = Observation.objects.create(eleve=pupil, competence=usage.competence, statut='reussi')
                Trace.objects.bulk_create([Trace(observation=obs, scolarite=sc, commentaire='Trace fictive.', auteur=teacher) for _ in range(traces_count)])
        pupil, comp = pupils[0], competences[0].competence
        commune = enregistrer_commune(utilisateur=teacher, classe=classe, competence=comp,
            ids=[e.pk for e in pupils], valeurs={'commentaire': 'Activité fictive partagée'})
        routes = [
            ('accueil','accueil',[],'responsable',{}), ('classe','classe_detail',[classe.pk],'responsable',{}),
            ('classe-tous','classe_detail',[classe.pk],'responsable',{'niveaux':'tous'}),
            ('individuel','saisie_eleve',[pupil.pk],'responsable',{}),
            ('contribution','contribuer_eleve',[pupil.pk],'contributeur',{}),
            ('competences','choisir_competence',[classe.pk],'responsable',{}),
            ('collectif','saisie_competence',[classe.pk,comp.pk],'responsable',{}),
            ('grille','grille_competence',[classe.pk,comp.pk],'responsable',{}),
            ('trace','trace',[pupil.pk,comp.pk],'responsable',{}),
            ('traces-partagees','traces_communes',[classe.pk,comp.pk],'responsable',{}),
            ('trace-partagee','modifier_trace_commune',[classe.pk,comp.pk,commune.pk],'responsable',{}),
            ('referentiel','referentiel_classe',[classe.pk],'responsable',{}),
            ('consulter','consulter_referentiels_classe',[classe.pk],'responsable',{}),
            ('adaptations','adaptations_classe',[classe.pk],'responsable',{}),
            ('presentation','presentation_classe',[classe.pk],'responsable',{}),
            ('ajouts','ajouts_classe',[classe.pk],'responsable',{}),
            ('correspondances','correspondances_classe',[classe.pk],'responsable',{}),
            ('permissions','permissions_referentiels_classe',[classe.pk],'responsable',{}),
            ('carnet','carnet',[pupil.pk],'responsable',{}),
            ('carnet-tout','carnet',[pupil.pk],'responsable',{'contenu':'tout'}),
            ('carnet-annuel','carnet',[pupil.pk],'responsable',{'regroupement':'annuel'}),
            ('carnet-bilans','carnet',[pupil.pk],'responsable',{'regroupement':'bilan'}),
            ('bilans','bilans_eleve',[pupil.pk],'responsable',{}),
            ('edition','preparer_edition',[classe.pk],'responsable',{}),
            ('gestion','gestion',[],'direction',{}), ('equipe','equipe_ecole',[],'direction',{}),
            ('annuaire','annuaire_eleves',[],'direction',{}),
            ('composition','importer_eleves',[classe.pk],'direction',{}),
            ('parcours','parcours_eleve',[pupil.pk],'direction',{}),
            ('referentiels-ecole','referentiels_ecole',[],'direction',{}),
            ('sauvegardes','sauvegardes_locales',[],'direction',{}),
            ('htmx-individuel','basculer',[pupil.pk,comp.pk],'responsable',{}),
            ('htmx-collectif','basculer',[pupil.pk,comp.pk],'responsable',{'vue':'classe'}),
            ('zip-sauvegarde','sauvegardes_locales',[],'direction',{'action':'sauvegarder'}),
        ]
        if args.pdf:
            routes += [('pdf','carnet_pdf',[pupil.pk],'responsable',{}),
                ('pdf-grille','grille_competence_pdf',[classe.pk,comp.pk],'responsable',{}),
                ('zip-pdf','preparer_edition',[classe.pk],'responsable',{'eleves':[str(e.pk) for e in pupils]})]
        if args.complements:
            from PIL import Image
            from io import BytesIO
            from django.core.files.base import ContentFile
            from django.core.files.storage import default_storage
            image = BytesIO()
            Image.new('RGB', (640, 480), (80, 160, 200)).save(image, format='PNG')
            nom = default_storage.save('rectangle-fictif.png', ContentFile(image.getvalue()))
            Trace.objects.filter(observation__eleve__in=pupils, observation__competence=comp).update(photo=nom)
            for i in range(n):
                user = get_user_model().objects.create_user(username=f'equipe-{label}-{i}')
                autre = Classe.objects.create(ecole=ecole, nom=f'Classe fictive {i}', annee_scolaire=annee)
                AffectationClasse.objects.create(appartenance=AppartenanceEcole.objects.create(utilisateur=user, ecole=ecole),
                    classe=autre, type='responsable')
                autre.activer()
            photo = Trace.objects.filter(observation__eleve=pupil, photo=nom).first()
            routes = [('trace-photo','trace',[pupil.pk,comp.pk],'responsable',{}),
                ('equipe-large','equipe_ecole',[],'direction',{}),
                ('gestion-large','gestion',[],'direction',{}),
                ('media-photo','afficher_media_trace',[photo.pk],'responsable',{}),
                ('original-photo','telecharger_media_trace',[photo.pk],'responsable',{}),
                ('post-trace','trace',[pupil.pk,comp.pk],'contributeur',
                    {'commentaire':'Contribution fictive.', 'visible_carnet':'on'}),
                ('post-partage','modifier_trace_commune',[classe.pk,comp.pk,commune.pk],'responsable',
                    {'commentaire':'Activité fictive.', 'date_observation':timezone.localdate().isoformat(),
                     'eleves':[str(e.pk) for e in pupils]}),
                ('post-restauration','sauvegardes_locales',[],'direction',{}),
                ('consulter-source','consulter_referentiels_classe',[classe.pk],'responsable',{'version':version.pk}),
                ('consulter-adapte','consulter_referentiels_classe',[classe.pk],'responsable',{'version':version.pk,'lecture':'classe'})]
        if args.complements:
            from suivi.paquet_local import creer_sauvegarde
            archive_fictive = BytesIO()
            creer_sauvegarde(paquet, archive_fictive)
        clients = {}
        for role, user in [('responsable',teacher),('direction',director),('contributeur',contributor)]:
            client = Client()
            client.force_login(user)
            clients[role] = client
        for name, route, ids, role, data in routes:
            url = reverse(route, args=ids)
            post = name.startswith(('htmx', 'zip-', 'post-'))
            if name == 'htmx-collectif':
                url += '?vue=classe'
                data = {}
            def request():
                payload = data
                if name == 'post-restauration':
                    from django.core.files.uploadedfile import SimpleUploadedFile
                    payload = {'action':'restaurer', 'archive':SimpleUploadedFile('fictif.zip', archive_fictive.getvalue())}
                response = clients[role].post(url, payload, HTTP_HX_REQUEST='true') if post else clients[role].get(url, data)
                if response.status_code != (302 if name.startswith('post-') else 200):
                    raise RuntimeError(f'{label}/{name}: HTTP {response.status_code}')
                body = b''.join(response.streaming_content) if response.streaming else response.content
                response.close()
                if name == 'post-restauration':
                    from suivi.paquet_local import annuler_preparation, preparation_en_attente
                    if preparation_en_attente() is None:
                        raise RuntimeError('La vérification de restauration a échoué.')
                    annuler_preparation()  # Aucune confirmation ni remplacement du paquet.
                return len(body)
            # Les écritures complémentaires sont mesurées dans une transaction
            # annulée ; ni croissance des traces ni changement de session durable.
            if name.startswith('post-'):
                from django.db import transaction
                original = request
                def request():
                    with transaction.atomic():
                        size = original()
                        transaction.set_rollback(True)
                    return size
            request()  # chauffe : gabarits, imports PDF, session ; hors statistiques
            timings = []
            for _ in range(args.repetitions):
                with CaptureQueriesContext(connection) as queries:
                    t = time.perf_counter()
                    size = request()
                    timings.append(time.perf_counter() - t)
            patterns = Counter(re.sub(r"\b\d+\b", '?', q['sql']) for q in queries)
            results.append(dict(scenario=label, parcours=name, secondes_mediane=round(statistics.median(timings),6),
                secondes_min=round(min(timings),6), secondes_max=round(max(timings),6), requetes=len(queries), octets=size,
                sql_secondes=sum(float(q['time']) for q in queries),
                repetitions_sql=[{'nombre':count,'sql':sql} for sql,count in patterns.most_common(5)]))
            print(f'{label} {name}: {results[-1]["secondes_mediane"]:.3f}s / {len(queries)} SQL / {size} o', flush=True)
    return dict(environnement=dict(python=platform.python_version(), django=django.get_version(), base='SQLite temporaire',
        repetitions=args.repetitions, chauffe=1, navigateur=False, debug=False, sql_instrumente=True), mesures=results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sortie', type=Path, required=True)
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--pdf', action='store_true')
    parser.add_argument('--complements', action='store_true', help='Photos synthétiques, grande équipe, écritures et consultation adaptée.')
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error('--repetitions doit être positif')
    with TemporaryDirectory(prefix='petits-pas-performance-') as directory:
        result = run(args, Path(directory))
    args.sortie.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
