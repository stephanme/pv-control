import unittest
from typing import final, override

from fastapi.testclient import TestClient

from pvcontrol.app import AngularAppStaticFiles, app

# pyright: reportUninitializedInstanceVariable=false


class AngularAppStaticFilesTest(unittest.TestCase):
    def test_is_immutable_resource(self):
        self.assertFalse(AngularAppStaticFiles.is_immutable_resource(""))
        self.assertFalse(AngularAppStaticFiles.is_immutable_resource("index.html"))
        self.assertFalse(AngularAppStaticFiles.is_immutable_resource("main.js"))
        self.assertFalse(AngularAppStaticFiles.is_immutable_resource("assets/android-chrome-192x192.png"))
        self.assertTrue(AngularAppStaticFiles.is_immutable_resource("main-CJJAB4LV.js"))
        self.assertTrue(AngularAppStaticFiles.is_immutable_resource("chunk-NSPGX3AG.js"))
        self.assertTrue(AngularAppStaticFiles.is_immutable_resource("styles-KDI3WURQ.css"))
        self.assertTrue(AngularAppStaticFiles.is_immutable_resource("media/matsymbols-U55GHSFU.woff2"))


@final
class PvcontrolAppTest(unittest.TestCase):
    @override
    def setUp(self):
        self.app = app
        self.client = TestClient(app)

    def test_index(self):
        r = self.client.get("/")
        self.assertEqual(200, r.status_code)
        self.assertIn("<title>PV Control</title>", r.text)
        r.close()
        r = self.client.get("/index.html")
        self.assertEqual(200, r.status_code)
        self.assertIn("<title>PV Control</title>", r.text)
        r.close()

    def test_metrics(self):
        r = self.client.get("/metrics")
        self.assertEqual(200, r.status_code)
        self.assertIn("python_info", r.text)
        r.close()
