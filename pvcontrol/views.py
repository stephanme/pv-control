import datetime
import logging
import re
import flask
import flask.views
import flask.json
from pvcontrol.service import BaseService
from pvcontrol.meter import Meter
from pvcontrol.wallbox import CarStatus, SimulatedWallbox, Wallbox
from pvcontrol.chargecontroller import ChargeController, ChargeMode, PhaseMode
from pvcontrol.car import Car

logger = logging.getLogger(__name__)


def jsonify_no_content():
    response = flask.make_response("", 204)
    response.mimetype = flask.json.provider.DefaultJSONProvider.mimetype
    return response


def add_no_cache_header(response: flask.Response):
    if "Cache-Control" not in response.headers:
        response.headers["Cache-Control"] = "no-cache, no-store"
    return response


class JSONProvider(flask.json.provider.DefaultJSONProvider):
    def default(self, o):
        if isinstance(o, datetime.datetime):
            return o.isoformat()
        return super().default(o)


class StaticResourcesView(flask.views.MethodView):
    def get(self, path):
        max_age = 31536000 if StaticResourcesView.is_immutable_resource(path) else None  # 1y in seconds 365*24*60*60
        return flask.send_from_directory("../ui/dist/ui", path, max_age=max_age)

    _angular_hashed_files_pattern = re.compile(r"\w+\.[0-9a-fA-F]{16,}\.\w+")

    @classmethod
    def is_immutable_resource(cls, path: str) -> bool:
        # short cut for
        if path == "index.html":
            return False
        return True if StaticResourcesView._angular_hashed_files_pattern.match(path) is not None else False


class PvControlView(flask.views.MethodView):
    def __init__(self, version: str, meter: Meter, wb: Wallbox, controller: ChargeController, car: Car):
        self._meter = meter
        self._wb = wb
        self._controller = controller
        self._car = car
        self._version = version

    def get(self) -> flask.Response:
        res = {
            "version": self._version,
            "controller": self._controller.get_data(),
            "meter": self._meter.get_data(),
            "wallbox": self._wb.get_data(),
            "car": self._car.get_data(),
        }
        return flask.jsonify(res)


# shows type, config and data of standard PvControl entities
class PvControlConfigDataView(flask.views.MethodView):
    def __init__(self, instance: BaseService):
        self._instance = instance

    def get(self) -> flask.Response:
        res = {
            "type": type(self._instance).__name__,
            "config": self._instance.get_config(),
            "data": self._instance.get_data(),
        }
        return flask.jsonify(res)


# curl -X PUT http://localhost:8080/api/pvcontrol/controller/desired_mode -H 'Content-Type: application/json' --data 'PV_ONLY'
class PvControlChargeModeView(flask.views.MethodView):
    def __init__(self, controller: ChargeController):
        self._controller = controller

    def put(self):
        v = flask.request.json
        try:
            mode = ChargeMode(v)
            self._controller.set_desired_mode(mode)
            return jsonify_no_content()
        except ValueError:
            flask.abort(400)


# curl -X PUT http://localhost:8080/api/pvcontrol/controller/phase_mode -H 'Content-Type: application/json' --data 'CHARGE_1P'
class PvControlPhaseModeView(flask.views.MethodView):
    def __init__(self, controller: ChargeController):
        self._controller = controller

    def put(self):
        v = flask.request.json
        try:
            mode = PhaseMode(v)
            self._controller.set_phase_mode(mode)
            return jsonify_no_content()
        except ValueError:
            flask.abort(400)


# for testing only: SimulatedWallbox
# curl -X PUT http://localhost:8080/api/pvcontrol/wallbox/car_status -H 'Content-Type: application/json' --data 1..4
# 1=NoVehicle, 2=Charging, 3=WaitingForVehicle, 4=ChargingFinished
class PvControlCarStatusView(flask.views.MethodView):
    def __init__(self, wallbox: SimulatedWallbox):
        self._wallbox = wallbox

    def put(self):
        v = flask.request.json
        try:
            if v is not None:
                status = CarStatus(v)
                self._wallbox.set_car_status(status)
                return jsonify_no_content()
            else:
                flask.abort(400)
        except ValueError:
            flask.abort(400)
