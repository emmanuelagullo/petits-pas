"""Construction d'une base vide et validation isolée de la projection locale."""
import secrets
import sqlite3
from contextvars import ContextVar
from contextlib import closing, contextmanager

from django.db import connections

_alias_validation = ContextVar("alias_validation_export", default=None)


class RouteurProjection:
    # Les clean() métier utilisent aussi des managers sans .using(). Le contexte
    # ne concerne que cette requête/ce thread, jamais les lectures du service.
    def db_for_read(self, model, **hints):
        return _alias_validation.get()

    def db_for_write(self, model, **hints):
        return _alias_validation.get()


@contextmanager
def validation_sur(alias):
    token = _alias_validation.set(alias)
    try:
        yield
    finally:
        _alias_validation.reset(token)


def initialiser_projection(paquet):
    """SQLite/Pyodide : schéma seul, aucune copie des données de l'installation.

    PostgreSQL : les migrations du programme fournissent le schéma SQLite.
    """
    source = connections["default"]
    if source.vendor != "sqlite":
        from .exports_ecole import initialiser_base
        return initialiser_base(paquet)
    (paquet / "secret-key").write_text(secrets.token_urlsafe(50), encoding="utf-8")
    (paquet / "secret-key").chmod(0o600)
    with source.cursor() as cursor:
        cursor.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL "
                       "AND name NOT LIKE 'sqlite_%' ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END")
        schema = [row[0] for row in cursor.fetchall()]
        cursor.execute("SELECT app, name, applied FROM django_migrations ORDER BY id")
        migrations = cursor.fetchall()
    with closing(sqlite3.connect(paquet / "carnet.sqlite3")) as cible:
        for sql in schema:
            cible.execute(sql)
        cible.executemany("INSERT INTO django_migrations(app,name,applied) VALUES (?,?,?)", migrations)
        cible.commit()
