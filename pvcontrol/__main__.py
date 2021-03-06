import logging

# configure logging before initializing further modules
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logging.getLogger("urllib3.connectionpool").setLevel(logging.INFO)

import argparse
import json
import flask
import flask_compress
from werkzeug.middleware.dispatcher import DispatcherMiddleware
import prometheus_client

from pvcontrol import views, relay
from pvcontrol.meter import MeterFactory
from pvcontrol.chargecontroller import ChargeControllerFactory
from pvcontrol.wallbox import WallboxFactory
from pvcontrol.car import CarFactory
from pvcontrol.scheduler import Scheduler

logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser(description="PV Control")
parser.add_argument("-m", "--meter", default="SimulatedMeter")
parser.add_argument("-w", "--wallbox", default="SimulatedWallbox")
parser.add_argument("-a", "--car", default="SimulatedCar")
parser.add_argument("-c", "--config", default="{}")
args = parser.parse_args()

logger.info("Starting pvcontrol")
logger.info(f"Meter:   {args.meter}")
logger.info(f"Wallbox: {args.wallbox}")
logger.info(f"Car:     {args.car}")
logger.info(f"config:  {args.config}")
config = json.loads(args.config)
for c in ["wallbox", "meter", "car", "controller"]:
    if c not in config:
        config[c] = {}

wallbox = WallboxFactory.newWallbox(args.wallbox, **config["wallbox"])
meter = MeterFactory.newMeter(args.meter, wallbox, **config["meter"])
car = CarFactory.newCar(args.car, **config["car"])
controller = ChargeControllerFactory.newController(meter, wallbox, **config["controller"])

controller_scheduler = Scheduler(controller.get_config().cycle_time, controller.run)
controller_scheduler.start()
car_scheduler = Scheduler(car.get_config().cycle_time, car.read_data)
car_scheduler.start()

app = flask.Flask(__name__)
app.json_encoder = views.JSONEncoder
app.after_request(views.add_no_cache_header)
app.config["COMPRESS_MIN_SIZE"] = 2048
app.config["COMPRESS_MIMETYPES"] = ["text/html", "text/css", "application/json", "application/javascript", "image/vnd.microsoft.icon"]
compress = flask_compress.Compress()
compress.init_app(app)

app.add_url_rule("/", view_func=views.StaticResourcesView.as_view("get_index"), defaults={"path": "index.html"})
app.add_url_rule("/<path:path>", view_func=views.StaticResourcesView.as_view("get_static"))
app.add_url_rule("/api/pvcontrol", view_func=views.PvControlView.as_view("get_pvcontrol", meter, wallbox, controller, car))
app.add_url_rule("/api/pvcontrol/controller", view_func=views.PvControlConfigDataView.as_view("get_controller", controller))
app.add_url_rule("/api/pvcontrol/controller/desired_mode", view_func=views.PvControlChargeModeView.as_view("put_desired_mode", controller))
app.add_url_rule("/api/pvcontrol/controller/phase_mode", view_func=views.PvControlPhaseModeView.as_view("put_phase_mode", controller))
app.add_url_rule("/api/pvcontrol/meter", view_func=views.PvControlConfigDataView.as_view("get_meter", meter))
app.add_url_rule("/api/pvcontrol/wallbox", view_func=views.PvControlConfigDataView.as_view("get_wallbox", wallbox))
app.add_url_rule("/api/pvcontrol/car", view_func=views.PvControlConfigDataView.as_view("get_car", car))
# for testing only
app.add_url_rule("/api/pvcontrol/wallbox/car_status", view_func=views.PvControlCarStatusView.as_view("put_car_status", wallbox))


# Add prometheus wsgi middleware to route /metrics requests
app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {"/metrics": prometheus_client.make_wsgi_app()})

app.run(host="0.0.0.0", port=8080)
controller_scheduler.stop()
car_scheduler.stop()
# disable charging to play it safe
# TODO: see ChargeMode.INIT handling
logger.info("Set wallbox.allow_charging=False on shutdown.")
wallbox.allow_charging(False)
relay.cleanup()
logger.info("Stopped pvcontrol")
