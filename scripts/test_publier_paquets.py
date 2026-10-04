"""Promotion GitHub exacte, sans accès aux forges ni publication réelle."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

spec=importlib.util.spec_from_file_location('publisher',Path(__file__).with_name('publier-paquets.py'))
publisher=importlib.util.module_from_spec(spec);spec.loader.exec_module(publisher)
SHA='a'*40

class PublicationTests(unittest.TestCase):
    def run_info(self):
        return {'conclusion':'success','status':'completed','path':publisher.WORKFLOW,
                'head_branch':'0.8','head_sha':SHA,'event':'push','run_attempt':1}

    def test_run_exact_tag_et_workflow(self):
        self.assertEqual(publisher.verify_run(self.run_info(),'0.8'),SHA)
        for key,value in [('conclusion','failure'),('head_branch','main'),('path','autre.yml'),('status','in_progress')]:
            run=self.run_info();run[key]=value
            with self.assertRaises(ValueError):publisher.verify_run(run,'0.8')

    def test_tags_concordants_et_tag_annote(self):
        lines='b'*40+'\trefs/tags/0.8\n'+SHA+'\trefs/tags/0.8^{}\n'
        with patch.object(publisher.subprocess,'check_output',return_value=lines) as request:
            publisher.verify_tags('0.8',SHA);self.assertEqual(request.call_count,2)
        with patch.object(publisher.subprocess,'check_output',return_value='b'*40+'\trefs/tags/0.8\n'):
            with self.assertRaises(ValueError):publisher.verify_tags('0.8',SHA)

    def test_chemins_et_doublons_refuses(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive=root/'artefact.zip'
            for name in ['../fichier','sous/fichier','a\\b']:
                with ZipFile(archive,'w') as z:z.writestr(name,b'fictif')
                with self.assertRaises(ValueError):publisher.unpack(archive,root)
            with ZipFile(archive,'w') as z:z.writestr('fichier',b'fictif')
            publisher.unpack(archive,root)
            with ZipFile(archive,'w') as z:z.writestr('fichier',b'altere')
            with self.assertRaises(ValueError):publisher.unpack(archive,root)

    def test_artefact_expire_ou_ambigu_avant_publication(self):
        for artifacts in [[{'name':'PetitsPas-linux','expired':True}],
                          [{'name':'PetitsPas-linux','expired':False}]*2, []]:
            with tempfile.TemporaryDirectory() as temp, patch.object(publisher,'verify_tags'), patch.object(publisher,'api',side_effect=[self.run_info(),{'artifacts':artifacts}]), patch.object(publisher,'gh') as gh:
                with self.assertRaises(ValueError):publisher.prepare('123','0.8',Path(temp))
                gh.assert_not_called()

    def test_promotion_selects_exact_ids_and_verifies_manifests(self):
        import os
        from publication import manifest, sha256
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.mkdir();destination=root/'destination';destination.mkdir()
            for name in ['PetitsPas-linux.tar.gz','PetitsPas-windows.zip','PetitsPas-Setup-0.8-x64.exe','notes-version.md']:
                (source/name).write_bytes(b'fictif '+name.encode())
            artifacts=[];blobs={}
            for job,target,names in [('linux','linux-ubuntu24.04-x86_64',['PetitsPas-linux.tar.gz','notes-version.md']),('windows','windows-x64',['PetitsPas-windows.zip','PetitsPas-Setup-0.8-x64.exe','notes-version.md'])]:
                with patch.dict(os.environ,{'GITHUB_SHA':SHA,'GITHUB_REF_TYPE':'tag','GITHUB_REF_NAME':'0.8','GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':job},clear=True):
                    record=manifest('programme',target,[source/n for n in names])
                (source/('publication-'+job+'.json')).write_text(json.dumps(record))
            for id,name,names in [(1,'PetitsPas-linux',['PetitsPas-linux.tar.gz','publication-linux.json','notes-version.md']),(2,'PetitsPas-windows',['PetitsPas-windows.zip','publication-windows.json','notes-version.md']),(3,'PetitsPas-Setup-windows',['PetitsPas-Setup-0.8-x64.exe'])]:
                blob=io.BytesIO()
                with ZipFile(blob,'w') as z:
                    for filename in names:z.writestr(filename,(source/filename).read_bytes())
                blobs[id]=blob.getvalue();artifacts.append({'id':id,'name':name,'expired':False})
            downloaded=[]
            def gh(*args,**kwargs):
                id=int(args[1].split('/artifacts/')[1].split('/')[0]);downloaded.append(id)
                kwargs['stdout'].write(blobs[id])
            with patch.object(publisher,'verify_tags'),patch.object(publisher,'api',side_effect=[self.run_info(),{'artifacts':artifacts},self.run_info()]),patch.object(publisher,'gh',side_effect=gh):
                files,commit=publisher.prepare('123','0.8',destination)
            self.assertEqual(downloaded,[1,2,3]);self.assertEqual(commit,SHA)
            self.assertIn('SHA256SUMS',{p.name for p in files})
            # Un autre fichier après construction est refusé avant toute release.
            destination2=root/'altered';destination2.mkdir()
            with ZipFile(io.BytesIO(blobs[1])) as z:
                blob=io.BytesIO()
                with ZipFile(blob,'w') as output:
                    for name in z.namelist():output.writestr(name,b'altere' if name=='PetitsPas-linux.tar.gz' else z.read(name))
            blobs[1]=blob.getvalue()
            with patch.object(publisher,'verify_tags'),patch.object(publisher,'api',side_effect=[self.run_info(),{'artifacts':artifacts}]),patch.object(publisher,'gh',side_effect=gh):
                with self.assertRaises(ValueError):publisher.prepare('123','0.8',destination2)

    def test_brouillon_verifie_avant_publication(self):
        import shutil
        import subprocess
        for altered in [False,True]:
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);file=root/'programme.zip';file.write_bytes(b'fictif')
                notes=root/'notes-version.md';notes.write_text('Notes fictives')
                def prepare(run,tag,folder):
                    shutil.copyfile(notes,folder/notes.name)
                    return [file],SHA
                commands=[]
                def gh(*args,**kwargs):
                    commands.append(args)
                    if args[:2]==('release','download'):
                        folder=Path(args[args.index('--dir')+1]);(folder/file.name).write_bytes(b'altere' if altered else b'fictif')
                with patch.object(publisher,'prepare',side_effect=prepare),patch.object(publisher,'gh',side_effect=gh),patch.object(publisher.subprocess,'run',return_value=subprocess.CompletedProcess([],1)),patch('sys.argv',['publier','123','0.8']):
                    if altered:
                        with self.assertRaises(ValueError):publisher.main()
                    else:publisher.main()
                self.assertEqual(any(command[:2]==('release','edit') for command in commands),not altered)
                self.assertTrue(any(command[:2]==('release','create') and '--draft' in command for command in commands))
