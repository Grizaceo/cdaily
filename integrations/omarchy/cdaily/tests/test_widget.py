"""Regression contracts for the installed user-owned CDaily plugin."""
import importlib.util
import pathlib
import tempfile
import unittest
from unittest.mock import patch

PLUGIN = pathlib.Path(__file__).resolve().parents[1]

class WidgetTests(unittest.TestCase):
    def test_summary_slot_is_declared_and_sized(self):
        qml = (PLUGIN / 'Widget.qml').read_text()
        self.assertIn('id: summaryBox', qml)
        self.assertIn('implicitHeight: summaryText.implicitHeight + 10', qml)

    def test_remote_images_never_enter_qt_network_loader(self):
        qml = (PLUGIN / 'Widget.qml').read_text()
        self.assertNotIn('source: modelData.image_url ? modelData.image_url', qml)
        self.assertIn('root.thumbnailSources[modelData.image_url]', qml)

    def test_supported_shell_open_close_contract(self):
        qml = (PLUGIN / 'Widget.qml').read_text()
        self.assertIn('function open()', qml)
        self.assertIn('function close()', qml)

    def test_http_failure_does_not_leave_loading_forever(self):
        qml = (PLUGIN / 'Widget.qml').read_text()
        self.assertIn('function httpGet(url, onOk, onError)', qml)
        self.assertIn('root.loadError', qml)

    def test_posts_remain_posts_and_have_watchdog(self):
        qml = (PLUGIN / 'Widget.qml').read_text()
        post = qml.split('function httpPost(', 1)[1].split('function refresh()', 1)[0]
        self.assertIn('xhr.open("POST", url)', post)
        self.assertIn('Date.now() + 120000', post)
        self.assertIn('root.httpPending = root.httpPending.concat', post)

    def test_summary_failure_clears_busy(self):
        qml = (PLUGIN / 'Widget.qml').read_text()
        summary = qml.split('function summarize(', 1)[1].split('function open()', 1)[0]
        self.assertIn('function(message)', summary)
        self.assertIn('container.busy = false', summary.split('function(message)', 1)[1])

class ThumbnailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('thumbs', PLUGIN / 'thumbnail_cache.py')
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def test_reject_unsafe_urls(self):
        for url in ['file:///etc/passwd', 'http://127.0.0.1/x', 'https://localhost/x',
                    'http://[::1]/x', 'ftp://example.com/x', 'http://user:pass@example.com/x']:
            with self.subTest(url=url):
                self.assertFalse(self.m.is_public_url(url))

    def test_disallow_non_images(self):
        self.assertFalse(self.m.is_image(b'<html>not an image</html>'))
        self.assertFalse(self.m.is_image(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'))
        self.assertTrue(self.m.is_image(b'\x89PNG\r\n\x1a\n' + b'x' * 20))
        self.assertTrue(self.m.is_image(b'\xff\xd8\xff' + b'x' * 20))

    def test_cached_success_does_not_download(self):
        url = 'https://example.com/test.png'
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            target = root / self.m.cache_key(url)
            target.write_bytes(b'\x89PNG\r\n\x1a\n' + b'x' * 20)
            with patch.object(self.m, 'download', side_effect=AssertionError('network called')):
                self.assertEqual(self.m.get_thumbnail(url, root), target.as_uri())

    def test_failed_download_is_negative_cached(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            with patch.object(self.m, 'download', side_effect=OSError('offline')) as mock:
                self.assertEqual(self.m.get_thumbnail('https://example.com/dead.png', root), '')
                self.assertEqual(self.m.get_thumbnail('https://example.com/dead.png', root), '')
                self.assertEqual(mock.call_count, 1)

if __name__ == '__main__':
    unittest.main()
