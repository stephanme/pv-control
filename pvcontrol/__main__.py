import asyncio
import logging
import threading
from typing import cast

# configure logging before initializing further modules
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logging.getLogger("urllib3.connectionpool").setLevel(logging.INFO)
logging.getLogger("pymodbus.logging").setLevel(logging.INFO)
logging.getLogger("aiohttp.trace").setLevel(logging.INFO)

import argparse
import json
import flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
import prometheus_client

from pvcontrol import views
from pvcontrol.meter import Meter, MeterFactory
from pvcontrol.chargecontroller import ChargeController, ChargeControllerFactory
from pvcontrol.wallbox import Wallbox, WallboxFactory
from pvcontrol.relay import PhaseRelay, PhaseRelayFactory
from pvcontrol.car import Car, CarFactory
from pvcontrol.scheduler import AsyncScheduler

logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser(description="PV Control")
parser.add_argument("-m", "--meter", default="SimulatedMeter")
parser.add_argument("-w", "--wallbox", default="SimulatedWallbox")
parser.add_argument("-r", "--relay", default="SimulatedPhaseRelay")
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
logger.info(f"Relay:   {args.relay}")
logger.info(f"Car:     {args.car}")
logger.info(f"config:  {args.config}")
logger.info(f"hostname:{args.hostname}")
config = json.loads(args.config)
for c in ["wallbox", "meter", "car", "controller", "relay"]:
    if c not in config:
        config[c] = {}


# start event loop in a separate thread (because flask is blocking)
def start_event_loop():
    asyncio.set_event_loop(event_loop)
    event_loop.run_forever()


event_loop = asyncio.new_event_loop()
threading.Thread(target=start_event_loop, daemon=True).start()

# Initialize the components in async funtion as some need a running event loop
# see https://github.com/microsoft/pyright/discussions/2033 how to make pyright happy
relay: PhaseRelay = cast(PhaseRelay, None)
wallbox: Wallbox = cast(Wallbox, None)
meter: Meter = cast(Meter, None)
controller: ChargeController = cast(ChargeController, None)
car: Car = cast(Car, None)
controller_scheduler: AsyncScheduler = cast(AsyncScheduler, None)
car_scheduler: AsyncScheduler = cast(AsyncScheduler, None)


async def async_init():
    global controller_scheduler, car_scheduler, relay, wallbox, meter, car, controller
    relay = PhaseRelayFactory.newPhaseRelay(args.relay, args.hostname, **config["relay"])
    wallbox = WallboxFactory.newWallbox(args.wallbox, relay, **config["wallbox"])
    meter = MeterFactory.newMeter(args.meter, wallbox, **config["meter"])
    car = CarFactory.newCar(args.car, **config["car"])
    controller = ChargeControllerFactory.newController(meter, wallbox, relay, **config["controller"])

    controller_scheduler = AsyncScheduler(controller.get_config().cycle_time, controller.run)
    car_scheduler = AsyncScheduler(car.get_config().cycle_time, car.read_data)
    await controller_scheduler.start()
    await car_scheduler.start()


asyncio.run_coroutine_threadsafe(async_init(), event_loop).result()
assert isinstance(relay, PhaseRelay)
assert isinstance(wallbox, Wallbox)
assert isinstance(meter, Meter)
assert isinstance(car, Car)
assert isinstance(controller, ChargeController)
assert isinstance(controller_scheduler, AsyncScheduler)
assert isinstance(car_scheduler, AsyncScheduler)

# setup web server
flask.Flask.json_provider_class = views.JSONProvider
app = flask.Flask(__name__)
app.after_request(views.add_no_cache_header)

app.add_url_rule("/", view_func=views.StaticResourcesView.as_view("get_index"), defaults={"path": "index.html"})
app.add_url_rule("/<path:path>", view_func=views.StaticResourcesView.as_view("get_static"))
app.add_url_rule("/api/pvcontrol", view_func=views.PvControlView.as_view("get_pvcontrol", version, meter, wallbox, relay, controller, car))
app.add_url_rule("/api/pvcontrol/controller", view_func=views.PvControlConfigDataView.as_view("get_controller", controller))
app.add_url_rule("/api/pvcontrol/controller/desired_mode", view_func=views.PvControlChargeModeView.as_view("put_desired_mode", controller))
app.add_url_rule("/api/pvcontrol/controller/phase_mode", view_func=views.PvControlPhaseModeView.as_view("put_phase_mode", controller))
app.add_url_rule("/api/pvcontrol/meter", view_func=views.PvControlConfigDataView.as_view("get_meter", meter))
app.add_url_rule("/api/pvcontrol/wallbox", view_func=views.PvControlConfigDataView.as_view("get_wallbox", wallbox))
app.add_url_rule("/api/pvcontrol/relay", view_func=views.PvControlConfigDataView.as_view("get_relay", relay))
app.add_url_rule("/api/pvcontrol/car", view_func=views.PvControlConfigDataView.as_view("get_car", car))
# for testing only
app.add_url_rule("/api/pvcontrol/wallbox/car_status", view_func=views.PvControlCarStatusView.as_view("put_car_status", wallbox))


# Add prometheus wsgi middleware to route /metrics requests
app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {"/metrics": prometheus_client.make_wsgi_app()})
# prefix urls to match 'base href' config of ng build, needed for stand-alone operation only
if args.basehref:
    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {args.basehref: app.wsgi_app})

# run web server, blocks until shutdown
app.run(host=args.host, port=args.port)


# shutdown components and event loop
async def async_shutdown():
    await controller_scheduler.stop()
    await car_scheduler.stop()
    # disable charging to play it safe
    # TODO: see ChargeMode.INIT handling
    logger.info("Set wallbox.allow_charging=False on shutdown.")
    await wallbox.allow_charging(False)
    await wallbox.close()
    await meter.close()


asyncio.run_coroutine_threadsafe(async_shutdown(), event_loop).result(timeout=1)
event_loop.stop()
# TODO: unclear why loop doesn't stop, waiting 1s doesn't help
# event_loop.close()
logger.info("Stopped pvcontrol")
