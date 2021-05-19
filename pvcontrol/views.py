import datetime
import logging
import os
import flask
import flask.views
import flask.json
from pvcontrol.service import BaseService
from pvcontrol.meter import Meter
from pvcontrol.wallbox import Wallbox
from pvcontrol.chargecontroller import ChargeController, ChargeMode, PhaseMode
from pvcontrol.car import Car

logger = logging.getLogger(__name__)


def jsonify_no_content():
    response = flask.make_response("", 204)
    response.mimetype = flask.current_app.config["JSONIFY_MIMETYPE"]
    return response


class JSONEncoder(flask.json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime.datetime):
            return o.isoformat()

        return super().default(o)


class StaticResourcesView(flask.views.MethodView):
    def get(self, path):
        return flask.send_from_directory("../ui/dist/ui", path)


class PvControlView(flask.views.MethodView):
    def __init__(self, meter: Meter, wb: Wallbox, controller: ChargeController, car: Car):
        self._meter = meter
        self._wb = wb
        self._controller = controller
        self._car = car
        self._version = os.getenv("COMMIT_SHA", "unknown")

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
