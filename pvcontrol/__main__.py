import logging

# configure logging before initializing further modules
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logging.getLogger("urllib3.connectionpool").setLevel(logging.INFO)

import argparse
import json
import flask
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
parser.add_argument("--hostname", default="", help="server hostname, can be used to enable/disable phase relay on k8s")
parser.add_argument("--host", default="0.0.0.0", help="server host (default: 0.0.0.0)")
parser.add_argument("--port", type=int, default=8080, help="server port (default: 8080)")
parser.add_argument("--basehref", help="URL prefix to match ng base-href param (no leading /)")
args = parser.parse_args()

# version file is generated during build
version = "unknown"
try:
    with open("version", "r") as f:
        version = f.read()
except Exception:
    pass

logger.info(f"Starting pvcontrol, version={version}")
logger.info(f"Meter:   {args.meter}")
logger.info(f"Wallbox: {args.wallbox}")
logger.info(f"Car:     {args.car}")
logger.info(f"config:  {args.config}")
logger.info(f"hostname:{args.hostname}")
config = json.loads(args.config)
for c in ["wallbox", "meter", "car", "controller"]:
    if c not in config:
        config[c] = {}

wallbox = WallboxFactory.newWallbox(args.wallbox, **config["wallbox"])
meter = MeterFactory.newMeter(args.meter, wallbox, **config["meter"])
car = CarFactory.newCar(args.car, **config["car"])
controller = ChargeControllerFactory.newController(meter, wallbox, args.hostname, **config["controller"])

controller_scheduler = Scheduler(controller.get_config().cycle_time, controller.run)
controller_scheduler.start()
car_scheduler = Scheduler(car.get_config().cycle_time, car.read_data)
car_scheduler.start()

flask.Flask.json_provider_class = views.JSONProvider
app = flask.Flask(__name__)
app.after_request(views.add_no_cache_header)

app.add_url_rule("/", view_func=views.StaticResourcesView.as_view("get_index"), defaults={"path": "index.html"})
app.add_url_rule("/<path:path>", view_func=views.StaticResourcesView.as_view("get_static"))
app.add_url_rule("/api/pvcontrol", view_func=views.PvControlView.as_view("get_pvcontrol", version, meter, wallbox, controller, car))
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
# prefix urls to match 'base href' config of ng build, needed for stand-alone operation only
if args.basehref:
    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {args.basehref: app.wsgi_app})

app.run(host=args.host, port=args.port)
controller_scheduler.stop()
car_scheduler.stop()
# disable charging to play it safe
# TODO: see ChargeMode.INIT handling
logger.info("Set wallbox.allow_charging=False on shutdown.")
wallbox.allow_charging(False)
relay.cleanup()
logger.info("Stopped pvcontrol")
