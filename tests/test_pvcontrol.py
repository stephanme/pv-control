import unittest

from pvcontrol import app


class PvControlTest(unittest.TestCase):
    def setUp(self):
        app.app.testing = True
        self.app = app.app.test_client()

    def test_index(self):
        r = self.app.get("/")
        self.assertEqual(200, r.status_code)
        self.assertIn("<title>PV Control</title>", str(r.data))
