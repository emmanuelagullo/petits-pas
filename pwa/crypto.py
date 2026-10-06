"""PBKDF2 compatible Django lorsque hashlib n'embarque pas OpenSSL (Python 3.14).

Aucun changement d'algorithme, de nombre d'itérations ou de mot de passe stocké.
PyCryptodome fournit le calcul natif WASM ; pas de boucle Python de dérivation.
"""
import hashlib


def pbkdf2_hmac(hash_name, password, salt, iterations, dklen=None):
    from Crypto.Hash import SHA1, SHA256, SHA512
    from Crypto.Protocol.KDF import PBKDF2
    algorithms = {"sha1": SHA1, "sha256": SHA256, "sha512": SHA512}
    try:
        algorithm = algorithms[hash_name.lower()]
    except KeyError:
        raise ValueError(f"Dérivation PBKDF2 non prise en charge : {hash_name}") from None
    if iterations < 1 or (dklen is not None and dklen < 1):
        raise ValueError("Les itérations et la longueur doivent être positives.")
    return PBKDF2(bytes(password), bytes(salt), dkLen=dklen or algorithm.digest_size,
                  count=iterations, hmac_hash_module=algorithm)


def configure():
    if not hasattr(hashlib, "pbkdf2_hmac"):
        hashlib.pbkdf2_hmac = pbkdf2_hmac
    if not hasattr(hashlib, "scrypt"):
        hashlib.scrypt = scrypt


def scrypt(password, *, salt, n, r, p, maxmem=0, dklen=64):
    from Crypto.Protocol.KDF import scrypt as derive
    if n < 2 or n & (n - 1) or min(r, p, dklen) < 1 or maxmem < 0:
        raise ValueError("Paramètres scrypt invalides.")
    # Même borne de travail que le défaut OpenSSL (32 Mio).
    if 128 * r * (n + p + 2) > (maxmem or 32 * 1024**2):
        raise ValueError("Mémoire scrypt insuffisante.")
    return derive(bytes(password), bytes(salt), dklen, n, r, p)
