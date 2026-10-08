#!/usr/bin/env python3
"""Banc fictif indépendant : projection, ZIP, reprise HTTP et restauration.

Sans connexion à une base existante. --mio 3072 exerce plusieurs Gio ; le
volume par défaut prépare une petite archive pour les essais PWA.
"""
import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import random
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mio", type=int, default=1, help="Volume minimal des médias fictifs")
    parser.add_argument("--destination", type=Path, required=True, help="Nouveau ZIP fictif à conserver")
    args = parser.parse_args()
    if not 1 <= args.mio <= 8192:
        parser.error("Volume attendu entre 1 et 8192 Mio.")
    destination = args.destination.resolve()
    if destination.exists() or destination.with_suffix(".json").exists():
        parser.error("La destination ou son rapport existe déjà.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="petits-pas-export-fictif-") as folder:
        root = Path(folder)
        # Définir les paramètres AVANT tout import Django ; aucun secret hérité.
        for key in list(os.environ):
            if key.startswith(("CARNET_", "DATABASE_", "DJANGO_", "PETITS_PAS_")):
                del os.environ[key]
        os.environ.update(DJANGO_SETTINGS_MODULE="carnet.settings", CARNET_MODE_LOCAL="non",
            CARNET_SQLITE_PATH=str(root / "source.sqlite3"), CARNET_MEDIA_ROOT=str(root / "media"),
            CARNET_EMAIL_DESACTIVE="oui", CARNET_ANTIBRUTEFORCE="non",
            CARNET_SECRET_KEY="fictif-qualification-jamais-un-secret-reel",
            CARNET_EXPORT_ROOT=str(root / "exports"))
        sys.path.insert(0, str(ROOT))
        import django
        django.setup()
        from django.conf import settings
        from django.contrib.auth.hashers import make_password
        from django.core.management import call_command
        from django.test import Client
        from django.urls import reverse
        from django.utils import timezone
        from datetime import timedelta
        from comptes.models import Utilisateur, AppartenanceEcole, ResponsabiliteEcole
        from suivi.models import Ecole, Classe, Domaine, Competence, Eleve, Scolarite, Observation, Trace, ExportEcole
        from suivi.exports_ecole import dossier, produire
        from suivi.paquet_local import preparer_restauration
        from PIL import Image

        call_command("migrate", verbosity=0)
        ecole = Ecole.objects.create(nom="École fictive export")
        settings.EXPORT_ECOLES = {ecole.pk}
        user = Utilisateur.objects.create_user(username="export-fictif", password="Service!Fictif2026")
        appartenance = AppartenanceEcole.objects.create(ecole=ecole, utilisateur=user)
        ResponsabiliteEcole.objects.create(appartenance=appartenance)
        classe = Classe.objects.create(ecole=ecole, nom="Classe fictive", annee_scolaire="2026-2027")
        domaine = Domaine.objects.create(ecole=ecole, code="fictif", nom="Domaine fictif")
        competence = Competence.objects.create(domaine=domaine, code="fictif", libelle="Compétence fictive")
        eleve = Eleve.objects.create(ecole=ecole, prenom="Fictif")
        scolarite = Scolarite.objects.create(eleve=eleve, classe=classe, annee_scolaire="2026-2027", niveau="PS")
        observation = Observation.objects.create(eleve=eleve, competence=competence)
        jpeg = io.BytesIO()
        Image.frombytes("RGB", (1024, 1024), random.Random(2026).randbytes(1024 * 1024 * 3)).save(jpeg, format="JPEG", quality=85)
        image = jpeg.getvalue()
        nombre = math.ceil(args.mio * 1024**2 / len(image))
        stockage = root / "media" / "traces"
        stockage.mkdir(parents=True)
        for numero in range(nombre):
            nom = f"traces/fictif-{numero:05d}.jpg"
            (root / "media" / nom).write_bytes(image)
            Trace.objects.create(observation=observation, scolarite=scolarite, auteur=user, photo=nom,
                                 commentaire="Réalisation synthétique fictive")
        export = ExportEcole.objects.create(ecole=ecole, demande_par=user,
            mot_de_passe_local=make_password("Copie!Fictive2026"), expire_le=timezone.now() + timedelta(hours=24))
        debut = time.monotonic()
        produire(export)
        export.refresh_from_db()
        assert export.etat == "pret", export.erreur
        preparation_secondes = time.monotonic() - debut
        # Le Client WSGI consomme le flux Django par blocs ; ce n'est pas une
        # mesure de débit Internet ni des timeouts du mandataire inverse.
        client = Client()
        client.force_login(user)
        session = client.session
        session["export_confirme"] = str(export.identifiant)
        session.save()
        url = reverse("telecharger_export_ecole", args=[export.identifiant])
        telechargement = root / "telecharge.zip"
        premier = client.get(url)
        assert premier.status_code == 200
        flux = iter(premier.streaming_content)
        bloc = next(flux)
        with telechargement.open("wb") as sortie:
            sortie.write(bloc)
        premier.close()  # Interruption explicite après le premier bloc.
        suite = client.get(url, HTTP_RANGE=f"bytes={len(bloc)}-", HTTP_IF_RANGE=premier["ETag"])
        assert suite.status_code == 206
        with telechargement.open("ab") as sortie:
            for bloc in suite.streaming_content:
                assert len(bloc) <= 1024**2
                sortie.write(bloc)
        suite.close()
        with telechargement.open("rb") as fichier:
            assert hashlib.file_digest(fichier, "sha256").hexdigest() == export.empreinte
        debut_restauration = time.monotonic()
        copie = preparer_restauration(telechargement, root)
        assert copie.nombre_medias == nombre
        for chemin in (copie.etape / "media").rglob("*.jpg"):
            with chemin.open("rb") as fichier:
                assert hashlib.file_digest(fichier, "sha256").hexdigest() == hashlib.sha256(image).hexdigest()
        try:
            import resource
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        except ImportError:
            rss = None
        rapport = {"donnees": "fictives uniquement", "mio_demandes": args.mio,
            "nombre_medias": nombre, "octets_zip": export.taille_zip,
            "octets_decompresses": export.taille_decompressee,
            "compatible_pwa": export.compatible_pwa,
            "preparation_secondes": round(preparation_secondes, 2),
            "restauration_secondes": round(time.monotonic() - debut_restauration, 2),
            "rss_max_kio_linux": rss if sys.platform == "linux" else None,
            "sha256": export.empreinte,
            "reprise_http_wsgi": True, "connexion_locale": "export-fictif",
            "mot_de_passe_local_fictif": "Copie!Fictive2026"}
        shutil.copyfile(dossier(export) / "ecole.zip", destination)
        destination.with_suffix(".json").write_text(json.dumps(rapport, indent=2), encoding="utf-8")
        print(json.dumps(rapport, indent=2))


if __name__ == "__main__":
    main()
