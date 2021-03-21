import logging
import flask
import flask.views
from pvcontrol.meter import Meter
from pvcontrol.charger import Charger

logger = logging.getLogger(__name__)


def jsonify_no_content():
    response = flask.make_response("", 204)
    response.mimetype = flask.current_app.config["JSONIFY_MIMETYPE"]
    return response


class StaticResourcesView(flask.views.MethodView):
    def get(self, path):
        return flask.send_from_directory("../ui/dist/ui", path)


class PvControlView(flask.views.MethodView):
    def __init__(self, meter: Meter, charger: Charger):
        self._meter = meter
        self._charger = charger

    def get(self) -> flask.Response:
        res = {
            "meter": self._meter.get_meter_data(),
            "charger": self._charger.get_charger_data(),
        }
        return flask.jsonify(res)


# curl -X PUT http://localhost:8080/api/pvcontrol/charger/phases -H 'Content-Type: application/json' --data '1'
class PvControlChargerPhasesView(flask.views.MethodView):
    def __init__(self, charger: Charger):
        self._charger = charger

    def put(self):
        v = flask.request.json
        if v == 1 or v == 3:
            self._charger.set_phases(v)
            return jsonify_no_content()
        else:
            flask.abort(400)
