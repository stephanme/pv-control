import unittest

from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient

from pvcontrol import dependencies
from pvcontrol.app import app


class PvcontrolApiTest(unittest.TestCase):
    def setUp(self):
        self.app = app

    def test_get_root(self):
        with TestClient(self.app) as client:
            response = client.get("/api/pvcontrol")
            self.assertEqual(200, response.status_code)
            json = response.json()
            self.assertEqual("unknown", json["version"])
            self.assertEqual(jsonable_encoder(dependencies.meter.get_data()), json["meter"])
            self.assertEqual(jsonable_encoder(dependencies.wallbox.get_data()), json["wallbox"])
            self.assertEqual(jsonable_encoder(dependencies.relay.get_data()), json["relay"])
            self.assertEqual(jsonable_encoder(dependencies.controller.get_data()), json["controller"])
            self.assertEqual(jsonable_encoder(dependencies.car.get_data()), json["car"])
            # check iso format, optional milliseconds and TZ
            self.assertRegex(json["car"]["data_captured_at"], r"\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d[\d.+:]*")

    def test_get_controller(self):
        with TestClient(self.app) as client:
            response = client.get("/api/pvcontrol/controller")
            self.assertEqual(200, response.status_code)
            json = response.json()
            self.assertEqual("ChargeController", json["type"])
            self.assertEqual(jsonable_encoder(dependencies.controller.get_config()), json["config"])
            self.assertEqual(jsonable_encoder(dependencies.controller.get_data()), json["data"])

    def test_put_controller_desired_mode(self):
        with TestClient(self.app) as client:
            response = client.put("/api/pvcontrol/controller/desired_mode", json="MANUAL")
            self.assertEqual(204, response.status_code)
            self.assertEqual(dependencies.controller.get_data().desired_mode, "MANUAL")
            response = client.put("/api/pvcontrol/controller/desired_mode", json="PV_ONLY")
            self.assertEqual(204, response.status_code)
            self.assertEqual(dependencies.controller.get_data().desired_mode, "PV_ONLY")

            response = client.put("/api/pvcontrol/controller/desired_mode", json="invalid")
            self.assertEqual(422, response.status_code)
            self.assertEqual(dependencies.controller.get_data().desired_mode, "PV_ONLY")

    def test_put_controller_phase_mode(self):
        with TestClient(self.app) as client:
            response = client.put("/api/pvcontrol/controller/phase_mode", json="AUTO")
            self.assertEqual(204, response.status_code)
            self.assertEqual(dependencies.controller.get_data().phase_mode, "AUTO")
            response = client.put("/api/pvcontrol/controller/phase_mode", json="CHARGE_1P")
            self.assertEqual(204, response.status_code)
            self.assertEqual(dependencies.controller.get_data().phase_mode, "CHARGE_1P")

            response = client.put("/api/pvcontrol/controller/phase_mode", json="invalid")
            self.assertEqual(422, response.status_code)
            self.assertEqual(dependencies.controller.get_data().phase_mode, "CHARGE_1P")

    def test_put_controller_priority(self):
        with TestClient(self.app) as client:
            response = client.put("/api/pvcontrol/controller/desired_priority", json="AUTO")
            self.assertEqual(204, response.status_code)
            self.assertEqual(dependencies.controller.get_data().desired_priority, "AUTO")
            response = client.put("/api/pvcontrol/controller/desired_priority", json="CAR")
            self.assertEqual(204, response.status_code)
            self.assertEqual(dependencies.controller.get_data().desired_priority, "CAR")
            response = client.put("/api/pvcontrol/controller/desired_priority", json="HOME_BATTERY")
            self.assertEqual(204, response.status_code)
            self.assertEqual(dependencies.controller.get_data().desired_priority, "HOME_BATTERY")

            response = client.put("/api/pvcontrol/controller/desired_priority", json="invalid")
            self.assertEqual(422, response.status_code)
            self.assertEqual(dependencies.controller.get_data().desired_priority, "HOME_BATTERY")

    def test_get_meter(self):
        with TestClient(self.app) as client:
            response = client.get("/api/pvcontrol/meter")
            self.assertEqual(200, response.status_code)
            json = response.json()
            self.assertEqual("SimulatedMeter", json["type"])
            self.assertEqual(jsonable_encoder(dependencies.meter.get_config()), json["config"])
            self.assertEqual(jsonable_encoder(dependencies.meter.get_data()), json["data"])

    def test_get_wallbox(self):
        with TestClient(self.app) as client:
            response = client.get("/api/pvcontrol/wallbox")
            self.assertEqual(200, response.status_code)
            json = response.json()
            self.assertEqual("SimulatedWallbox", json["type"])
            self.assertEqual(jsonable_encoder(dependencies.wallbox.get_config()), json["config"])
            self.assertEqual(jsonable_encoder(dependencies.wallbox.get_data()), json["data"])

    def test_get_relay(self):
        with TestClient(self.app) as client:
            response = client.get("/api/pvcontrol/relay")
            self.assertEqual(200, response.status_code)
            json = response.json()
            self.assertEqual("SimulatedPhaseRelay", json["type"])
            self.assertEqual(jsonable_encoder(dependencies.relay.get_config()), json["config"])
            self.assertEqual(jsonable_encoder(dependencies.relay.get_data()), json["data"])

    def test_get_car(self):
        with TestClient(self.app) as client:
            response = client.get("/api/pvcontrol/car")
            self.assertEqual(200, response.status_code)
            json = response.json()
            self.assertEqual("SimulatedCar", json["type"])
            self.assertEqual(jsonable_encoder(dependencies.car.get_config()), json["config"])
            self.assertEqual(jsonable_encoder(dependencies.car.get_data()), json["data"])
