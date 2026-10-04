"""Reprises TLS/réseau, fichier complet et cache de reconstruction."""
import hashlib
import http.client
import importlib.util
import io
import ssl
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('construire_pwa', Path(__file__).with_name('construire-pwa.py'))
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class Response(io.BytesIO):
    def __init__(self, body, length=None):
        super().__init__(body)
        self.headers = {'Content-Length': str(len(body) if length is None else length)}


class DownloadTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.target = self.root / 'runtime.wasm'
        self.url = 'https://runtime-fictif.example/runtime.wasm'

    def test_tls_decode_error_is_retried_then_cached_without_network(self):
        failure = urllib.error.URLError(ssl.SSLError('TLSV1_ALERT_DECODE_ERROR'))
        with patch.object(builder.urllib.request, 'urlopen', side_effect=[failure, Response(b'complet')]) as request, patch.object(builder.time, 'sleep'):
            builder.telecharger(self.url, self.target)
            builder.telecharger(self.url, self.target)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(self.target.read_bytes(), b'complet')
        self.assertEqual(list(self.root.iterdir()), [self.target])

    def test_failed_download_preserves_old_file_and_removes_partial_files(self):
        self.target.write_bytes(b'ancien')
        expected = hashlib.sha256(b'complet').hexdigest()
        with patch.object(builder.urllib.request, 'urlopen', side_effect=urllib.error.URLError('fictif')), patch.object(builder.time, 'sleep'):
            with self.assertRaises(urllib.error.URLError):
                builder.telecharger(self.url, self.target, expected, tentatives=2)
        self.assertEqual(self.target.read_bytes(), b'ancien')
        self.assertEqual(list(self.root.iterdir()), [self.target])

    def test_truncated_response_is_retried(self):
        with patch.object(builder.urllib.request, 'urlopen', side_effect=[Response(b'partiel', 100), Response(b'complet')]) as request, patch.object(builder.time, 'sleep'):
            builder.telecharger(self.url, self.target)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(self.target.read_bytes(), b'complet')

    def test_invalid_cached_wheel_is_replaced_using_expected_hash(self):
        self.target.write_bytes(b'altere')
        with patch.object(builder.urllib.request, 'urlopen', return_value=Response(b'complet')):
            builder.telecharger(self.url, self.target, hashlib.sha256(b'complet').hexdigest())
        self.assertEqual(self.target.read_bytes(), b'complet')

    def test_bad_certificate_or_http_404_are_not_retried(self):
        for failure in [urllib.error.URLError(ssl.SSLCertVerificationError('fictif')),
                        urllib.error.HTTPError(self.url, 404, 'fictif', {}, None)]:
            with self.subTest(failure=failure), patch.object(builder.urllib.request, 'urlopen', side_effect=failure) as request, patch.object(builder.time, 'sleep') as delay:
                with self.assertRaises(urllib.error.URLError):
                    builder.telecharger(self.url, self.target)
                request.assert_called_once()
                delay.assert_not_called()
                self.assertEqual(list(self.root.iterdir()), [])

    def test_bad_hash_is_rejected_without_committing_partial_data(self):
        with patch.object(builder.urllib.request, 'urlopen', return_value=Response(b'altere')):
            with self.assertRaisesRegex(RuntimeError, 'Empreinte incorrecte'):
                builder.telecharger(self.url, self.target, hashlib.sha256(b'complet').hexdigest())
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
