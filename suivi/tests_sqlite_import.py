import sqlite3
from contextlib import closing
from unittest import TestCase

from .sqlite_import import securiser_lecture


class SQLiteImportTests(TestCase):
    def test_compatibilite_ancien_json_native_et_refus_fonction_applicative(self):
        with closing(sqlite3.connect(':memory:')) as db:
            db.execute('CREATE TABLE donnee (contenu TEXT CHECK(JSON_VALID(contenu)))')
            db.execute("INSERT INTO donnee VALUES ('{}')")
            db.commit()
            appels = []
            db.create_function('fonction_applicative', 0, lambda: appels.append(True) or 1)
            db.create_function('length', 1, lambda valeur: appels.append(True) or 1)

            class AncienSQLite:
                def execute(self, sql):
                    resultat = db.execute(sql)
                    if sql == 'PRAGMA function_list':
                        return [tuple(r[:5]) + (r[5] & ~0x200000,) if r[0] == 'json_valid'
                                else r for r in resultat]
                    return resultat

                def set_authorizer(self, callback):
                    db.set_authorizer(callback)

            securiser_lecture(AncienSQLite())
            self.assertEqual(db.execute('SELECT contenu FROM donnee').fetchone()[0], '{}')
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute('SELECT fonction_applicative()')
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute("SELECT length('x')")
            self.assertEqual(appels, [])
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute("INSERT INTO donnee VALUES ('{}')")
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute("ATTACH ':memory:' AS autre")

    def test_lecture_schema_json_native(self):
        db = sqlite3.connect(':memory:')
        try:
            db.execute('CREATE TABLE donnee (contenu TEXT CHECK(JSON_VALID(contenu)))')
            db.execute("INSERT INTO donnee VALUES ('{}')")
            db.commit()
            securiser_lecture(db)
            self.assertEqual(db.execute('SELECT contenu FROM donnee').fetchone()[0], '{}')
        finally:
            db.close()
