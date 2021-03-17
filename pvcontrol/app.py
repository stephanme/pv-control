import logging
import flask
import pvcontrol.relay as relay

logger = logging.getLogger(__name__)
app = flask.Flask(__name__)


def jsonify_no_content():
    response = flask.make_response("", 204)
    response.mimetype = app.config["JSONIFY_MIMETYPE"]
    return response


@app.route("/")
def index():
    return flask.send_from_directory("../ui/dist/ui", "index.html")


@app.route("/<path:path>")
def send_static_content(path):
    return flask.send_from_directory("../ui/dist/ui", path)


@app.route("/api/pvcontrol")
def get_charge_control():
    ch = relay.readChannel1()
    return flask.jsonify({"phases": 1 if ch else 3})


# curl -X PUT http://localhost:8080/api/pvcontrol/phases -H 'Content-Type: application/json' --data '1'
@app.route("/api/pvcontrol/phases", methods=["PUT"])
def put_charge_control():
    v = flask.request.json
    if v == 1 or v == 3:
        # relay ON = 1 phase
        relay.writeChannel1(v == 1)
        return jsonify_no_content()
    else:
        return flask.abort(400)
