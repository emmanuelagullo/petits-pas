#!/usr/bin/env python3
"""Lire les releases publiques GitHub ; ne jamais présenter un artefact CI comme publié."""
import json
from pathlib import Path
import re
import urllib.request
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
DESTINATION = ROOT / 'site/data/publications_generees.json'


def catalogue(releases):
    if not isinstance(releases,list):
        raise ValueError("Réponse de catalogue invalide.")
    result=[]
    for release in releases:
        tag=release['tag_name']
        if release.get('draft') or not release.get('published_at') or not re.fullmatch(r'[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:-[A-Za-z0-9.-]+)?',tag):
            continue
        assets={a['name']:a for a in release.get('assets',[])}
        windows=assets.get(f'PetitsPas-Setup-{tag}-x64.exe');linux=assets.get('PetitsPas-linux.tar.gz')
        entry={'version':tag,'date':release['published_at'][:10],
               'notes':f'https://github.com/emmanuelagullo/petits-pas/releases/tag/{tag}'}
        for mode,asset in [('windows',windows),('linux',linux)]:
            if asset and asset.get('size',0)>0:
                expected=f'https://github.com/emmanuelagullo/petits-pas/releases/download/{tag}/{asset["name"]}'
                if asset.get('browser_download_url') == expected:
                    entry[mode]=expected
        if 'windows' in entry or 'linux' in entry:result.append(entry)
    return {'versions':result,'verified_at':datetime.now(timezone.utc).isoformat()}


def main():
    try:
        request=urllib.request.Request('https://api.github.com/repos/emmanuelagullo/petits-pas/releases?per_page=20',headers={'User-Agent':'PetitsPas-site-public'})
        with urllib.request.urlopen(request,timeout=10) as response:
            raw=response.read(2*1024**2+1)
        if len(raw)>2*1024**2:raise ValueError('Catalogue trop volumineux.')
        record=catalogue(json.loads(raw))
        if not record['versions']:raise ValueError('Aucune version téléchargeable observée.')
        temporary=DESTINATION.with_suffix('.tmp')
        temporary.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        temporary.replace(DESTINATION)
        print('Catalogue des releases GitHub publiques actualisé.')
    except (OSError, ValueError, KeyError) as error:
        print('Catalogue non actualisé ; conserver les versions connues :',error)


if __name__=='__main__':main()
