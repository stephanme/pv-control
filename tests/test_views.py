import unittest
import unittest.mock as mock
import flask
from pvcontrol import views
from pvcontrol.charger import ChargerData
from pvcontrol.meter import MeterData


class StaticResourcesViewTest(unittest.TestCase):
    def setUp(self):
        app = flask.Flask(__name__)
        app.add_url_rule("/", view_func=views.StaticResourcesView.as_view("get_index"), defaults={"path": "index.html"})
        app.add_url_rule("/<path:path>", view_func=views.StaticResourcesView.as_view("get_static"))
        app.testing = True
        self.app = app.test_client()

    def test_index(self):
        r = self.app.get("/")
        self.assertEqual(200, r.status_code)
        self.assertIn("<title>PV Control</title>", str(r.data))
        r = self.app.get("/index.html")
        self.assertEqual(200, r.status_code)
        self.assertIn("<title>PV Control</title>", str(r.data))


class PvControlViewTest(unittest.TestCase):
    def setUp(self):
        app = flask.Flask(__name__)
        app.testing = True
        self.app = app.test_client()
        self.meter_data = MeterData(5000, 3000, 2000)
        self.charger_data = ChargerData(1, 2000, 10)
        meter = mock.Mock()
        meter.get_meter_data.return_value = self.meter_data
        charger = mock.Mock()
        charger.get_charger_data.return_value = self.charger_data
        app.add_url_rule("/api/pvcontrol", view_func=views.PvControlView.as_view("get_pvcontrol", meter, charger))

    def test_pvcontrol_api(self):
        r = self.app.get("/api/pvcontrol")
        self.assertEqual(200, r.status_code)
        self.assertEqual(self.meter_data.__dict__, r.json["meter"])
        self.assertEqual(self.charger_data.__dict__, r.json["charger"])


class PvControlChargerPhasesView(unittest.TestCase):
    def setUp(self):
        app = flask.Flask(__name__)
        app.testing = True
        self.app = app.test_client()
        self.charger_data = ChargerData(1, 2000, 10)
        self.charger = mock.Mock()
        app.add_url_rule(
            "/api/pvcontrol/charger/phases", view_func=views.PvControlChargerPhasesView.as_view("put_charger_phases", self.charger)
        )

    def test_put_charger_phases_api(self):
        r = self.app.put("/api/pvcontrol/charger/phases", json=1)
        self.assertEqual(204, r.status_code)
        self.charger.set_phases.assert_called_once_with(1)
        r = self.app.put("/api/pvcontrol/charger/phases", json=3)
        self.assertEqual(204, r.status_code)
        self.charger.set_phases.assert_called_with(3)

    def test_put_charger_phases_api_error(self):
        r = self.app.put("/api/pvcontrol/charger/phases", json=2)
        self.assertEqual(400, r.status_code)
        r = self.app.put("/api/pvcontrol/charger/phases", data="1")
        self.assertEqual(400, r.status_code)
        self.charger.set_phases.assert_not_called()
