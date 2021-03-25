import logging
import flask
import flask.views
from pvcontrol.meter import Meter
from pvcontrol.wallbox import Wallbox
from pvcontrol.chargecontroller import ChargeController, ChargeMode

logger = logging.getLogger(__name__)


def jsonify_no_content():
    response = flask.make_response("", 204)
    response.mimetype = flask.current_app.config["JSONIFY_MIMETYPE"]
    return response


class StaticResourcesView(flask.views.MethodView):
    def get(self, path):
        return flask.send_from_directory("../ui/dist/ui", path)


class PvControlView(flask.views.MethodView):
    def __init__(self, meter: Meter, wb: Wallbox, controller: ChargeController):
        self._meter = meter
        self._wb = wb
        self._controller = controller

    def get(self) -> flask.Response:
        res = {
            "controller": self._controller.get_data(),
            "meter": self._meter.get_data(),
            "wallbox": self._wb.get_data(),
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
