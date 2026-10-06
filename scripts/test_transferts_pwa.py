"""Contrat fichier utilisé par ZipFile, sans navigateur ni données réelles."""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pwa.transfers import OpfsFile


class Api:
    def __init__(self):
        self.data = bytearray(b"avantZIPapres")
        self.flushed = 0

    def size(self, key):
        return len(self.data)

    def read(self, key, buffer, at):
        block = self.data[at:at + len(buffer)]
        buffer[:len(block)] = block
        return len(block)

    def write(self, key, buffer, at):
        self.data[at:at + len(buffer)] = buffer
        return len(buffer)

    def flush(self, key):
        self.flushed += 1


class TransfertsTests(unittest.TestCase):
    def test_segment_seek_fin_fermeture_et_limite_avant_allocation(self):
        api = Api()
        with patch.dict(sys.modules, {"js": SimpleNamespace(pwaIO=api)}):
            source = OpfsFile("upload", start=5, length=3)
            self.assertEqual(source.read(), b"ZIP")
            self.assertEqual(source.read(100), b"")
            source.seek(-2, 2)
            target = bytearray(10)
            self.assertEqual(source.readinto(target), 2)
            self.assertEqual(target[:2], b"IP")
            source.seek(0)
            source.max_read = 2
            with self.assertRaisesRegex(ValueError, "complète"):
                source.read()
            with self.assertRaisesRegex(ValueError, "Bloc"):
                source.read(2**31)
            source.close()
            self.assertEqual(api.flushed, 1)
            with self.assertRaises(ValueError):
                source.read(1)

    def test_ecriture_et_seek_sans_copie_archive(self):
        api = Api()
        with patch.dict(sys.modules, {"js": SimpleNamespace(pwaIO=api)}):
            with OpfsFile("export", start=5) as target:
                self.assertEqual(target.write(b"fictif"), 6)
                target.seek(0)
                self.assertEqual(target.read(6), b"fictif")
            self.assertEqual(api.data[:5], b"avant")
