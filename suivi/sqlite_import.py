"""Lecture seule du SQLite importé, y compris JSON_VALID avec SQLite ancien."""
import sqlite3


def securiser_lecture(connection):
    connection.execute('PRAGMA query_only=ON')
    connection.execute('PRAGMA trusted_schema=OFF')
    fonctions = list(connection.execute('PRAGMA function_list'))
    # JSON1 de certaines versions anciennes oublie SQLITE_INNOCUOUS. Ne pas
    # confondre cette anomalie avec une fonction Python enregistrée par Django.
    json_valid = [r for r in fonctions if r[0].lower() == 'json_valid' and r[1]]
    if json_valid and not all(r[5] & 0x200000 for r in json_valid):
        autorisees = {r[0].lower() for r in fonctions if r[1] and r[5] & 0x200000}
        autorisees.add('json_valid')  # Fonction native pure, aucun accès externe.
        # Ne pas autoriser une surcharge applicative du même nom qu'un builtin.
        autorisees.difference_update(r[0].lower() for r in fonctions if not r[1])

        def autoriser(action, arg1, arg2, base, origine):
            if action == sqlite3.SQLITE_FUNCTION and (arg2 or '').lower() not in autorisees:
                return sqlite3.SQLITE_DENY
            if action in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        # Toujours lecture seule ; extensions non chargées ; toute fonction
        # applicative/non innocente reste interdite, même dans un schéma fourni.
        connection.execute('PRAGMA trusted_schema=ON')
        connection.set_authorizer(autoriser)
