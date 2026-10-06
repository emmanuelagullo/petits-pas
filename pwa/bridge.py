"""Pont WSGI du prototype. Ne lance aucun serveur et garde CSRF/droits Django."""
import base64
import hashlib
import io
import json
import os
import secrets
import shutil
import sqlite3
import sys
import traceback
from contextlib import closing
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile

DATA = Path("/data")
COOKIES = {}
APPLICATION = None
SCRIPT_NAME = "/app"
PREVIOUS_PACKAGE = None
MEDIA_INDEX = {}
FULL_MEDIA_SCAN = True
RESPONSE_BODY = b""
PENDING_RESPONSE = None


def initialize(origin, version, base="/", essai=False, apercu=False):
    global APPLICATION, SCRIPT_NAME
    SCRIPT_NAME = base.rstrip("/") + "/app"
    DATA.mkdir(exist_ok=True)
    (DATA / "media").mkdir(exist_ok=True)
    key = DATA / "secret-key"
    if not key.exists():
        key.write_text(secrets.token_urlsafe(48))
    os.environ.update({
        # Pyodide possède une boucle JS active. Les appels synchrones sont
        # néanmoins exclusifs : worker unique et file JS sans réentrance.
        "DJANGO_ALLOW_ASYNC_UNSAFE": "true",
        "PWA_BASE_PATH": base,
        "DJANGO_SETTINGS_MODULE": "pwa.settings", "CARNET_DEBUG": "0",
        "CARNET_MODE_LOCAL": "oui", "CARNET_ESPACE_ESSAI": "oui" if essai else "non", "CARNET_EMAIL_DESACTIVE": "oui",
        "CARNET_ESPACE_APERCU": "oui" if apercu else "non",
        "CARNET_ANTIBRUTEFORCE": "non", "CARNET_VERSION": version,
        "CARNET_HOSTS": urlsplit(origin).hostname,
        "CARNET_CSRF_ORIGINS": origin,
        "CARNET_SECRET_KEY": key.read_text(),
        "CARNET_SQLITE_PATH": str(DATA / "carnet.sqlite3"),
        "CARNET_MEDIA_ROOT": str(DATA / "media"),
    })
    from django.core.wsgi import get_wsgi_application
    from django.core.management import call_command
    from django.core.signals import got_request_exception
    got_request_exception.connect(lambda **kwargs: traceback.print_exc(file=sys.stderr), weak=False)
    APPLICATION = get_wsgi_application()
    validate_migrations(DATA / "carnet.sqlite3")
    call_command("migrate", interactive=False, verbosity=0)
    with closing(sqlite3.connect(DATA / "carnet.sqlite3")) as db:
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("Base locale endommagée : ouverture refusée.")
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise RuntimeError("Relations de la base locale invalides.")


def restore_demo(snapshot):
    from suivi.essai_local import installer_ecole_fictive
    installer_ecole_fictive(bytes(snapshot), DATA)


def restore(snapshot):
    with ZipFile(io.BytesIO(bytes(snapshot))) as archive:
        for name in archive.namelist():
            if name == "manifest.json":
                continue
            if name not in {"carnet.sqlite3", "secret-key", "suivi-sauvegarde.json"} and not name.startswith("media/"):
                raise ValueError("Instantané local invalide")
            parts = Path(name).parts
            if name.startswith("/") or ".." in parts or "\\" in name:
                raise ValueError("Chemin invalide")
            target = DATA / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))


def restore_file(name, content):
    """Fichiers vérifiés par OPFS ; pas de migration dans le Worker de secours."""
    parts = Path(name).parts
    if (name not in {"carnet.sqlite3", "secret-key", "suivi-sauvegarde.json"}
            and not name.startswith("media/")) or name.startswith("/") or ".." in parts or "\\" in name:
        raise ValueError("Chemin local invalide")
    target = DATA / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(bytes(content))


def describe(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024**2):
            digest.update(block)
    return {"hash": digest.hexdigest(), "size": path.stat().st_size}


def restore_media_index(encoded):
    """Empreintes déjà vérifiées par OPFS ; ne pas recopier les photos en Python."""
    global MEDIA_INDEX, FULL_MEDIA_SCAN
    MEDIA_INDEX = {name: {"hash": entry["hash"], "size": entry["size"]}
                   for name, entry in json.loads(encoded).items() if name.startswith("media/")}
    FULL_MEDIA_SCAN = False


def inventory_apercu():
    from suivi.apercu_local import preparation
    copie = preparation()
    if copie is None:
        raise ValueError("Aucune copie prête.")
    files = {name: describe(copie.etape / name) for name in ["carnet.sqlite3", "secret-key"]}
    files.update({p.relative_to(copie.etape).as_posix(): describe(p)
                  for p in (copie.etape / "media").rglob("*") if p.is_file()})
    from suivi.paquet_local import FORMAT, VERSION
    manifeste = json.dumps({"format": FORMAT, "version": VERSION,
        "created_at": "2000-01-01T00:00:00+00:00", "files": {k: v["hash"] for k, v in files.items()}})
    return json.dumps({"files": files, "bytes": sum(f["size"] for f in files.values()) + len(manifeste.encode())})


def file_bytes_apercu(name):
    from suivi.apercu_local import preparation
    return (preparation().etape / name).read_bytes()


def nettoyer_apercu():
    from suivi.apercu_local import annuler
    annuler()


def inventory(force_scan=False):
    """Base cohérente, sans ZIP ; ne relire que les médias écrits/supprimés.

    Le SQLite sauvegardé est comparé même après un GET : sessions, audit et
    écritures hors ORM sont ainsi couverts. La file JS reste exclusive.
    """
    global MEDIA_INDEX, FULL_MEDIA_SCAN
    from pwa.media_storage import changed
    if force_scan or FULL_MEDIA_SCAN:
        MEDIA_INDEX = {p.relative_to(DATA).as_posix(): describe(p)
                       for p in (DATA / "media").rglob("*") if p.is_file()}
        FULL_MEDIA_SCAN = False
    else:
        for name in changed:
            path = DATA / "media" / name
            key = path.relative_to(DATA).as_posix()
            if path.is_file():
                MEDIA_INDEX[key] = describe(path)
            else:
                MEDIA_INDEX.pop(key, None)
    changed.clear()
    # Garder cette copie jusqu'au prochain inventaire, pour les transferts JS.
    copy = DATA.parent / ".pwa-sqlite-copy"
    copy.unlink(missing_ok=True)
    with closing(sqlite3.connect(DATA / "carnet.sqlite3")) as source:
        with closing(sqlite3.connect(copy)) as target:
            source.backup(target)
    files = {**MEDIA_INDEX, "carnet.sqlite3": describe(copy),
             "secret-key": describe(DATA / "secret-key")}
    suivi = DATA / "suivi-sauvegarde.json"
    if suivi.exists():
        files[suivi.name] = describe(suivi)
    from suivi.paquet_local import FORMAT, VERSION
    # Même sérialisation et longueur de date que l'export public. Compter le
    # manifeste, y compris les noms Unicode échappés, dans la limite d'import.
    manifest_size = len(json.dumps({"format": FORMAT, "version": VERSION,
        "created_at": "2000-01-01T00:00:00+00:00",
        "files": {name: entry["hash"] for name, entry in files.items()}}).encode())
    if manifest_size > 1024**2:
        raise ValueError("Manifeste de sauvegarde trop volumineux.")
    return json.dumps({"files": files, "bytes": sum(f["size"] for f in files.values()) + manifest_size})


def file_bytes(name):
    return ((DATA.parent / ".pwa-sqlite-copy") if name == "carnet.sqlite3"
            else DATA / name).read_bytes()


def validate_migrations(path):
    from django.db.migrations.loader import MigrationLoader
    if not path.exists():
        return
    with closing(sqlite3.connect(path)) as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='django_migrations'").fetchone():
            applied = set(db.execute("SELECT app, name FROM django_migrations"))
            if applied - set(MigrationLoader(None).disk_migrations):
                raise ValueError("Base issue d'une version plus récente ou incompatible. Exportez un état de récupération.")


def snapshot():
    """Même format public que le paquet autonome, base/clé/médias/manifeste."""
    from suivi.paquet_local import creer_sauvegarde
    from .transfers import OpfsFile
    with OpfsFile("export") as output:
        creer_sauvegarde(DATA, output, taille_bloc=1024**2)


def transfer_step():
    from . import transfers
    return transfers.etape()


def finish_transfer(encoded):
    global PENDING_RESPONSE
    request = PENDING_RESPONSE.pwa_request
    from django.http import HttpResponseRedirect
    response = HttpResponseRedirect(SCRIPT_NAME + ("/gestion/sauvegardes-locales/"
        if request.path.endswith("/sauvegardes-locales/") else "/verifier-zip/"))
    request._messages.update(response)
    if request.session.modified:
        request.session.save()
    for name, morsel in response.cookies.items():
        if morsel["max-age"] == "0":
            COOKIES.pop(name, None)
        else:
            COOKIES[name] = morsel.value
    PENDING_RESPONSE.close()
    PENDING_RESPONSE = None
    result = json.loads(encoded)
    result.update(status=302, headers=[["Location", response.url], ["Cache-Control", "no-store"]], job=False)
    return json.dumps(result)


def has_preparation():
    from suivi import paquet_local, apercu_local
    return bool(paquet_local.preparation_en_attente() or paquet_local.restauration_en_attente()
                or apercu_local.preparation())


def metrics():
    files = [p for p in (DATA / "media").rglob("*") if p.is_file()]
    return json.dumps({"databaseBytes": (DATA / "carnet.sqlite3").stat().st_size,
                       "mediaBytes": sum(p.stat().st_size for p in files),
                       "mediaFiles": len(files)})


def release_previous_package():
    global PREVIOUS_PACKAGE
    if PREVIOUS_PACKAGE is not None:
        shutil.rmtree(PREVIOUS_PACKAGE, ignore_errors=True)
        PREVIOUS_PACKAGE = None


def apply_pending_restore():
    global PREVIOUS_PACKAGE, FULL_MEDIA_SCAN
    from django.conf import settings
    from django.core.management import call_command
    from django.db import connections
    from suivi import paquet_local
    preparation = paquet_local.restauration_en_attente()
    if preparation is None:
        return False
    connections.close_all()
    # Le précédent OPFS reste actif tant que le worker n'a pas validé le nouveau.
    PREVIOUS_PACKAGE = paquet_local.appliquer_restauration(DATA, preparation)
    FULL_MEDIA_SCAN = True
    validate_migrations(DATA / "carnet.sqlite3")
    settings.SECRET_KEY = (DATA / "secret-key").read_text()
    call_command("migrate", interactive=False, verbosity=0)
    COOKIES.clear()
    # Réinitialiser seulement les attentes du module, après activation en mémoire.
    import importlib
    importlib.reload(paquet_local)
    return True


def response_bytes():
    global RESPONSE_BODY
    content, RESPONSE_BODY = RESPONSE_BODY, b""
    return content


def handle(encoded, raw_body=None):
    global RESPONSE_BODY, PENDING_RESPONSE
    request = json.loads(encoded)
    url = urlsplit(request["url"])
    path = url.path.removeprefix(SCRIPT_NAME) or "/"
    from .transfers import OpfsFile
    body = None if request.get("opfs_input") else bytes(raw_body) if raw_body is not None else base64.b64decode(request["body"])
    input_file = OpfsFile("request") if body is None else io.BytesIO(body)
    input_size = input_file.seek(0, 2) if body is None else len(body)
    input_file.seek(0)
    environ = {
        "REQUEST_METHOD": request["method"], "PATH_INFO": path,
        "QUERY_STRING": url.query, "SCRIPT_NAME": SCRIPT_NAME,
        "SERVER_NAME": url.hostname, "SERVER_PORT": str(url.port or 443),
        "SERVER_PROTOCOL": "HTTP/1.1", "REMOTE_ADDR": "127.0.0.1",
        "wsgi.version": (1, 0), "wsgi.url_scheme": url.scheme,
        "wsgi.input": input_file, "wsgi.errors": sys.stderr,
        "wsgi.multithread": False, "wsgi.multiprocess": False, "wsgi.run_once": False,
        "CONTENT_LENGTH": str(input_size),
        "HTTP_COOKIE": "; ".join(f"{k}={v}" for k, v in COOKIES.items()),
    }
    for key, value in request["headers"]:
        key = key.upper().replace("-", "_")
        if key in {"COOKIE", "HOST", "CONTENT_LENGTH"}:
            continue
        environ[key if key == "CONTENT_TYPE" else "HTTP_" + key] = value
    environ["HTTP_HOST"] = url.netloc
    response = {}

    def start_response(status, headers, exc_info=None):
        response.update(status=int(status.split()[0]), headers=headers)

    iterable = APPLICATION(environ, start_response)
    from . import transfers
    job = transfers.JOB is not None
    if job:
        iterable.pwa_request = transfers.JOB["request"]
        PENDING_RESPONSE = iterable
    try:
        content = b"".join(iterable)
    finally:
        input_file.close()
        if not job and hasattr(iterable, "close"):
            iterable.close()
    headers = []
    for key, value in response["headers"]:
        if key.lower() == "set-cookie":
            cookies = SimpleCookie(value)
            for name, morsel in cookies.items():
                if morsel["max-age"] == "0":
                    COOKIES.pop(name, None)
                else:
                    COOKIES[name] = morsel.value
        else:
            headers.append([key, value])
    # Token CSRF virtuel ; aucune clé de session dans le DOM/localStorage.
    if any(k.lower() == "content-type" and v.startswith("text/html") for k, v in headers):
        injection = ('<script>document.addEventListener("htmx:configRequest",function(e){'
                     'e.detail.headers["X-CSRFToken"]=' + json.dumps(COOKIES.get("csrftoken", "")) + ';});</script>')
        content = content.replace(b"</head>", injection.encode() + b"</head>", 1)
        headers = [[k, v] for k, v in headers if k.lower() != "content-length"]
    restored = apply_pending_restore()
    if restored:
        response["status"] = 302
        headers = [["Location", SCRIPT_NAME + "/connexion/"], ["Cache-Control", "no-store"]]
        content = b""
    RESPONSE_BODY = content
    from suivi.apercu_local import ouverture_demandee
    response.update(headers=headers, restored=restored, ouvrir_apercu=ouverture_demandee(),
                    job=job, export=bool(getattr(iterable, "pwa_export", False)))
    return json.dumps(response)
