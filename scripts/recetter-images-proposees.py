#!/usr/bin/env python3
"""Crée huit carnets HTML/PDF fictifs, sans lire une base d'école existante.

Usage : python scripts/recetter-images-proposees.py --destination /tmp/images-fictives
La destination doit être nouvelle. Aucun compte ni média réel n'est utilisé.
"""
import argparse
import base64
from datetime import date
from io import BytesIO
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--avec-associations', action='store_true',
                        help='Ajouter un carnet fictif pour chacune des trois éditions fournies.')
    args = parser.parse_args()
    destination = args.destination.resolve()
    if destination.exists():
        parser.error('Choisissez une destination nouvelle.')
    destination.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='petits-pas-images-fictives-') as travail:
        travail = Path(travail)
        for cle in list(os.environ):
            if cle.startswith(('CARNET_', 'DATABASE_', 'DJANGO_', 'PETITS_PAS_')):
                del os.environ[cle]
        os.environ.update(DJANGO_SETTINGS_MODULE='carnet.settings',
            CARNET_SQLITE_PATH=str(travail / 'fictive.sqlite3'),
            CARNET_MEDIA_ROOT=str(travail / 'media'), CARNET_STATIC_ROOT=str(travail / 'static'),
            CARNET_EMAIL_DESACTIVE='oui', CARNET_ANTIBRUTEFORCE='non',
            CARNET_SECRET_KEY='uniquement-fictif-pour-la-recette-images')
        sys.path.insert(0, str(ROOT))
        import django
        django.setup()
        from django.contrib.staticfiles import finders
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.core.management import call_command
        from django.test import Client
        from django.urls import reverse
        from PIL import Image, ImageDraw
        from comptes.models import Utilisateur, AppartenanceEcole, AffectationClasse, ResponsabiliteEcole
        from suivi.models import Ecole, Classe, Domaine, Competence, Eleve, Scolarite
        from suivi.services.reprise_referentiels import reprendre
        from suivi.services.pedagogie import enregistrer_trace, modifier_etat
        from suivi.services.presentation import enregistrer_affichage
        from suivi.services.traces_communes import enregistrer_commune, personnaliser
        from suivi.services.medias_django import preparer_image
        from django.conf import settings

        call_command('migrate', verbosity=0)
        call_command('collectstatic', interactive=False, verbosity=0)
        ecole = Ecole.objects.create(nom='École fictive des Jardins')
        responsable = Utilisateur.objects.create_user(username='recette-images-fictive', password=None)
        membre = AppartenanceEcole.objects.create(ecole=ecole, utilisateur=responsable)
        ResponsabiliteEcole.objects.create(appartenance=membre, type='direction')
        classe = Classe.objects.create(ecole=ecole, nom='Les Semis', annee_scolaire='2026-2027')
        AffectationClasse.objects.create(appartenance=membre, classe=classe, type='responsable')
        classe.activer()
        domaine = Domaine.objects.create(ecole=ecole, code='JARDIN', nom='Découvrir les plantations')
        competence = Competence.objects.create(domaine=domaine, code='FICTIF-01',
            libelle='Je prends soin des plantations', icone='om-plante', niveau='PS')
        eleves, scolarites = {}, {}
        for prenom in ('Alix', 'Lou', 'Noé', 'Inès'):
            eleves[prenom] = Eleve.objects.create(ecole=ecole, prenom=prenom, nom='Fictif')
            scolarites[prenom] = Scolarite.objects.create(eleve=eleves[prenom], classe=classe,
                annee_scolaire=classe.annee_scolaire, niveau='PS')
        reprendre(ecole.pk)
        for eleve in eleves.values():
            modifier_etat(utilisateur=responsable, eleve=eleve, competence=competence, statut='en_cours')

        def image(nom, nombre):
            # Dessins synthétiques de réalisations, jamais de photo d'enfant.
            dessin = Image.new('RGB', (600, 400), '#eee7d3')
            pinceau = ImageDraw.Draw(dessin)
            pinceau.text((24, 22), 'REALISATION FICTIVE - ' + nom, fill='#243d32')
            for i in range(nombre):
                x = 80 + i * 160
                pinceau.polygon([(x-35, 280), (x+35, 280), (x+25, 350), (x-25, 350)], fill='#c67b50')
                pinceau.line((x, 280, x, 150-i*15), fill='#3a754e', width=10)
                pinceau.ellipse((x, 170-i*15, x+60, 210-i*15), fill='#689950')
                pinceau.ellipse((x-60, 220-i*15, x, 260-i*15), fill='#76a55b')
            b = BytesIO()
            dessin.save(b, format='PNG')
            return preparer_image(SimpleUploadedFile(nom+'.png', b.getvalue(), content_type='image/png'))

        commune = enregistrer_commune(utilisateur=responsable, classe=classe, competence=competence,
            ids=[eleves[p].pk for p in ('Lou', 'Noé', 'Inès')], valeurs={
                'date_observation': date(2026, 10, 1), 'commentaire': '<prenom> observe nos plantations.',
                'photo': image('plantations-communes', 3)})
        for prenom in ('Noé', 'Inès'):
            trace = personnaliser(utilisateur=responsable,
                trace=commune.attributions.get(observation__eleve=eleves[prenom]))
            enregistrer_trace(utilisateur=responsable, eleve=eleves[prenom], competence=competence,
                scolarite=scolarites[prenom], trace=trace, valeurs={
                    'photo': image('plantation-personnelle', 1) if prenom == 'Noé' else None,
                    'commentaire': prenom + ' décrit sa plantation (version personnelle fictive).'})
        enregistrer_trace(utilisateur=responsable, eleve=eleves['Lou'], competence=competence,
            scolarite=scolarites['Lou'], valeurs={'date_observation': date(2026, 10, 2),
                'photo': image('autre-realisation-personnelle', 1),
                'commentaire': 'Lou montre aussi sa réalisation personnelle (autre trace fictive).'})
        enregistrer_trace(utilisateur=responsable, eleve=eleves['Alix'], competence=competence,
            scolarite=scolarites['Alix'], valeurs={'commentaire': 'Alix raconte comment arroser, sans photo.'})
        client = Client()
        client.force_login(responsable)
        css = Path(finders.find('suivi/carnet.css')).read_text()

        def incorporer(match):
            url = match.group(1)
            chemin = urlsplit(url).path
            if chemin.startswith('/static/'):
                f = settings.STATIC_ROOT / chemin.removeprefix('/static/')
                contenu, mime = f.read_bytes(), 'image/svg+xml'
            else:
                reponse = client.get(url)
                if reponse.status_code != 200:
                    raise RuntimeError('Média fictif inaccessible : ' + url)
                mime = reponse['Content-Type']
                contenu = b''.join(reponse.streaming_content)
                reponse.close()
            return 'src="data:' + mime + ';base64,' + base64.b64encode(contenu).decode() + '"'

        rapport, liens = [], []

        def apercu_autonome(html, nom, prenom):
            article = re.search(r'<article class="carnet .*?</article>', html, flags=re.S).group()
            article = re.sub(r'src="([^"]+)"', incorporer, article)
            (destination / (nom+'.html')).write_text('<!doctype html><html lang="fr"><meta charset="utf-8">'
                '<title>Carnet fictif de '+prenom+'</title><style>'+css+'</style>'+article+'</html>')

        for avec_photos in (False, True):
            enregistrer_affichage(responsable, ecole, classe, avec_photos=avec_photos)
            for prenom, eleve in eleves.items():
                nom = {'Noé': 'noe', 'Inès': 'ines'}.get(prenom, prenom.lower())
                nom += '-avec-image' if avec_photos else '-image-seulement-sans-photo'
                options = {'contenu': 'observes', 'colonnes': '2'}
                web = client.get(reverse('carnet', args=[eleve.pk]), options)
                if web.status_code != 200:
                    raise RuntimeError('Carnet fictif inaccessible.')
                html = web.content.decode()
                photos = html.count('class="trace-photo"')
                images = html.count('class="icone-competence"')
                attendu = {'Alix': 0, 'Lou': 2, 'Noé': 1, 'Inès': 0}[prenom]
                assert photos == attendu, (prenom, photos)
                assert images == int(avec_photos or not photos), (prenom, images)
                assert html.count('>OpenMoji</a>') == images
                apercu_autonome(html, nom, prenom)
                pdf = client.get(reverse('carnet_pdf', args=[eleve.pk]), options)
                assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF')
                (destination / (nom+'.pdf')).write_bytes(pdf.content)
                rapport.append({'prenom_fictif': prenom, 'avec_image_et_photos': avec_photos,
                    'photos': photos, 'illustrations': images, 'pdf_octets': len(pdf.content)})
                liens.append(f'<li>{nom} : <a href="{nom}.html">carnet web</a> · <a href="{nom}.pdf">PDF</a></li>')
        if args.avec_associations:
            from suivi.models import ChoixApplicationAnnuel
            from suivi.referentiels import contenu_adoption
            from suivi.services.import_sources_referentiels import importer_source
            from suivi.services.choix_bases_referentiels import publier_choix_application
            from suivi.services.adoption_bases_referentiels import apercu_adoption, adopter_base
            versions = []
            for fichier, nom in [('cycle1/objectifs-programmes.yaml', 'objectifs'),
                                 ('cycle1/cycle1-etaye.yaml', 'etaye'),
                                 ('chatdecole/tableaux-cycle1.yaml', 'chatdecole')]:
                version = importer_source((ROOT / 'referentiel' / fichier).read_text())[0]
                versions.append((version, nom))
            politique = ChoixApplicationAnnuel.objects.filter(annee_scolaire=classe.annee_scolaire).first()
            publier_choix_application(annee=classe.annee_scolaire, versions_ids=[v.pk for v, _ in versions],
                proposee_id=versions[0][0].pk, revision_attendue=politique.revision if politique else 0)
            for version, nom in versions:
                exemple = Classe.objects.create(ecole=ecole, nom='Exemple fictif '+nom,
                    annee_scolaire=classe.annee_scolaire)
                AffectationClasse.objects.create(appartenance=membre, classe=exemple, type='responsable')
                exemple.activer()
                apercu = apercu_adoption(utilisateur=responsable, classe=exemple, version_id=version.pk)
                adoption = adopter_base(utilisateur=responsable, classe=exemple, version_id=version.pk,
                    revisions_attendues=apercu['revisions'], adoption_attendue=apercu['adoption_id'],
                    garde_attendue=apercu['garde']['empreinte'])
                eleve = Eleve.objects.create(ecole=ecole, prenom='Camille', nom='Fictif')
                Scolarite.objects.create(eleve=eleve, classe=exemple, annee_scolaire=classe.annee_scolaire, niveau='MS')
                selection = {'LANG-O062', 'LANG-O080', 'PHYS-O002', 'ARTS-O048', 'MATH-O066',
                             'LANG-O061', 'LANG-O066', 'TEMPS-O006', 'TEMPS-O010'}
                definitions = [c for c in contenu_adoption(adoption)['competences'] if c['code'] in selection]
                assert len(definitions) == len(selection)
                for definition in definitions:
                    modifier_etat(utilisateur=responsable, eleve=eleve,
                        competence=Competence.objects.get(pk=definition['id']), statut='en_cours')
                options = {'contenu': 'observes', 'colonnes': '2'}
                web = client.get(reverse('carnet', args=[eleve.pk]), options)
                assert web.status_code == 200
                html = web.content.decode()
                assert html.count('class="icone-competence"') == len(selection)
                assert html.count('>OpenMoji</a>') == 1
                apercu_autonome(html, nom, eleve.prenom)
                pdf = client.get(reverse('carnet_pdf', args=[eleve.pk]), options)
                assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF')
                (destination / (nom+'.pdf')).write_bytes(pdf.content)
                rapport.append({'source': version.source.identifiant, 'version': version.numero,
                    'photos': 0, 'illustrations': len(selection), 'credits_openmoji': 1, 'pdf_octets': len(pdf.content)})
                liens.append(f'<li>{nom}, édition {version.numero} : <a href="{nom}.html">carnet web</a> · <a href="{nom}.pdf">PDF</a></li>')
        (destination / 'rapport.json').write_text(json.dumps(rapport, ensure_ascii=False, indent=2))
        (destination / 'index.html').write_text('<!doctype html><html lang="fr"><meta charset="utf-8">'
            '<title>Comparer les images proposées</title><h1>Carnets entièrement fictifs</h1>'
            '<p>Alix : sans photo. Lou : photo commune et photo personnelle dans deux traces. '
            'Noé : version personnelle avec photo remplacée. Inès : version personnelle sans photo.</p>'
            '<p>Les carnets utilisent les vrais parcours web et PDF. Les aperçus HTML sont autonomes.</p><ul>'
            + ''.join(liens) + '</ul></html>')
    print(str(len(rapport))+' carnets HTML/PDF fictifs vérifiés : ' + str(destination))


if __name__ == '__main__':
    main()
