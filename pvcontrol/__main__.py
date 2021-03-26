import logging
import argparse
import flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
import prometheus_client

from pvcontrol import views, relay
from pvcontrol.meter import MeterFactory
from pvcontrol.chargecontroller import ChargeController, ChargeControllerConfig
from pvcontrol.wallbox import WallboxFactory
from pvcontrol.scheduler import Scheduler

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser(description="PV Control")
parser.add_argument("-m", "--meter", default="SimulatedMeter")
parser.add_argument("-w", "--wallbox", default="SimulatedWallbox")
args = parser.parse_args()

logger.info("Starting pvcontrol")
logger.info(f"Meter:   {args.meter}")
logger.info(f"Wallbox: {args.wallbox}")
wallbox = WallboxFactory.newWallbox(args.wallbox)
meter = MeterFactory.newMeter(args.meter, wallbox)
controller = ChargeController(ChargeControllerConfig(), meter, wallbox)

scheduler = Scheduler(30, controller.run)
scheduler.start()

app = flask.Flask(__name__)
app.add_url_rule("/", view_func=views.StaticResourcesView.as_view("get_index"), defaults={"path": "index.html"})
app.add_url_rule("/<path:path>", view_func=views.StaticResourcesView.as_view("get_static"))
app.add_url_rule("/api/pvcontrol", view_func=views.PvControlView.as_view("get_pvcontrol", meter, wallbox, controller))
app.add_url_rule("/api/pvcontrol/controller/desired_mode", view_func=views.PvControlChargeModeView.as_view("put_desired_mode", controller))

# Add prometheus wsgi middleware to route /metrics requests
app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {"/metrics": prometheus_client.make_wsgi_app()})

app.run(host="0.0.0.0", port=8080)
scheduler.stop()
relay.cleanup()
logger.info("Stopped pvcontrol")
