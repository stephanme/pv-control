import unittest
import unittest.mock as mock
import flask
from pvcontrol import views
from pvcontrol.service import BaseConfig, BaseData, BaseService
from pvcontrol.meter import MeterData
from pvcontrol.wallbox import WallboxData
from pvcontrol.chargecontroller import ChargeControllerData, ChargeMode, PhaseMode


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
        r.close()
        r = self.app.get("/index.html")
        self.assertEqual(200, r.status_code)
        self.assertIn("<title>PV Control</title>", str(r.data))
        r.close()


class PvControlViewTest(unittest.TestCase):
    def setUp(self):
        app = flask.Flask(__name__)
        app.testing = True
        self.app = app.test_client()
        self.meter_data = MeterData(5000, 3000, 2000)
        self.wb_data = WallboxData()
        self.controller_data = ChargeControllerData()
        meter = mock.Mock()
        meter.get_data.return_value = self.meter_data
        wb = mock.Mock()
        wb.get_data.return_value = self.wb_data
        controller = mock.Mock()
        controller.get_data.return_value = self.controller_data
        app.add_url_rule("/api/pvcontrol", view_func=views.PvControlView.as_view("get_pvcontrol", meter, wb, controller))

    def test_pvcontrol_api(self):
        r = self.app.get("/api/pvcontrol")
        self.assertEqual(200, r.status_code)
        self.assertEqual(self.meter_data.__dict__, r.json["meter"])
        self.assertEqual(self.wb_data.__dict__, r.json["wallbox"])
        self.assertEqual(self.controller_data.__dict__, r.json["controller"])
        self.assertEqual("unknown", r.json["version"])


class PvControlConfigDataViewTest(unittest.TestCase):
    def setUp(self):
        app = flask.Flask(__name__)
        app.testing = True
        self.app = app.test_client()
        service = BaseService(BaseConfig())
        service._set_data(BaseData())
        app.add_url_rule(
            "/api/pvcontrol/controller",
            view_func=views.PvControlConfigDataView.as_view("get_wallbox", service),
        )

    def test_pvcontrol_api(self):
        r = self.app.get("/api/pvcontrol/controller")
        self.assertEqual(200, r.status_code)
        self.assertEqual("BaseService", r.json["type"])
        self.assertEqual({}, r.json["config"])
        self.assertEqual({"error": 0}, r.json["data"])


class PvControlChargeModeViewTest(unittest.TestCase):
    def setUp(self):
        app = flask.Flask(__name__)
        app.testing = True
        self.app = app.test_client()
        self.charger_data = ChargeControllerData()
        self.controller = mock.Mock()
        app.add_url_rule(
            "/api/pvcontrol/controller/desired_mode",
            view_func=views.PvControlChargeModeView.as_view("put_desired_mode", self.controller),
        )

    def test_put_charger_phases_api(self):
        r = self.app.put("/api/pvcontrol/controller/desired_mode", json="MANUAL")
        self.assertEqual(204, r.status_code)
        self.controller.set_desired_mode.assert_called_once_with(ChargeMode.MANUAL)
        r = self.app.put("/api/pvcontrol/controller/desired_mode", json="PV_ONLY")
        self.assertEqual(204, r.status_code)
        self.controller.set_desired_mode.assert_called_with(ChargeMode.PV_ONLY)

    def test_put_charger_phases_api_error(self):
        r = self.app.put("/api/pvcontrol/controller/desired_mode", json="invalid")
        self.assertEqual(400, r.status_code)
        r = self.app.put("/api/pvcontrol/controller/desired_mode", data="invalid")
        self.assertEqual(400, r.status_code)
        self.controller.set_desired_mode.assert_not_called()


class PvControlPhaseModeViewTest(unittest.TestCase):
    def setUp(self):
        app = flask.Flask(__name__)
        app.testing = True
        self.app = app.test_client()
        self.charger_data = ChargeControllerData()
        self.controller = mock.Mock()
        app.add_url_rule(
            "/api/pvcontrol/controller/phase_mode",
            view_func=views.PvControlPhaseModeView.as_view("put_phase_mode", self.controller),
        )

    def test_put_charger_phases_api(self):
        r = self.app.put("/api/pvcontrol/controller/phase_mode", json="CHARGE_1P")
        self.assertEqual(204, r.status_code)
        self.controller.set_phase_mode.assert_called_once_with(PhaseMode.CHARGE_1P)
        r = self.app.put("/api/pvcontrol/controller/phase_mode", json="AUTO")
        self.assertEqual(204, r.status_code)
        self.controller.set_phase_mode.assert_called_with(PhaseMode.AUTO)

    def test_put_charger_phases_api_error(self):
        r = self.app.put("/api/pvcontrol/controller/phase_mode", json="invalid")
        self.assertEqual(400, r.status_code)
        r = self.app.put("/api/pvcontrol/controller/phase_mode", data="invalid")
        self.assertEqual(400, r.status_code)
        self.controller.set_phase_mode.assert_not_called()
