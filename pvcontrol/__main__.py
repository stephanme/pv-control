import logging
import argparse
import flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
import prometheus_client

from pvcontrol import views, relay
from pvcontrol.meter import Meter
from pvcontrol.charger import Charger
from pvcontrol.scheduler import Scheduler

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser(description="PV Control")
parser.add_argument("-m", "--simulate-meter", default=False, action="store_true")
parser.add_argument("-c", "--simulate-charger", default=False, action="store_true")
args = parser.parse_args()

logger.info("Starting pvcontrol")
meter = Meter(simulation=args.simulate_meter)
charger = Charger(simulation=args.simulate_charger)
logger.debug(f"Meter simulation  : {meter.is_simulated()}")
logger.debug(f"Charger simulation: {charger.is_simulated()}")


# metrics
metrics_pvc_meter_power = prometheus_client.Gauge("pvcontrol_meter_power_watts", "Power from pv or grid", ["source"])
metrics_pvc_meter_power_consumption_total = prometheus_client.Gauge(
    "pvcontrol_meter_power_consumption_total_watts", "Total home power consumption"
)
metrics_pvc_charger_power = prometheus_client.Gauge("pvcontrol_charger_power_watts", "Charger power")
metrics_pvc_charger_phases = prometheus_client.Gauge("pvcontrol_charger_phases", "Number of used current phases for charger (1 or 3)")
metrics_pvc_charger_max_current = prometheus_client.Gauge("pvcontrol_charger_max_current_amperes", "Max charger current per phase")
metrics_pvc_processing = prometheus_client.Summary("pvcontrol_processing_seconds", "Time spent processing control loop")


@metrics_pvc_processing.time()
def controlloop():
    if meter.is_simulated():
        c = charger.get_charger_data()
        meter.set_charger_data_for_simulation(c.phases * c.max_current * 230)
    m = meter.read_meter()
    c = charger.read_charger_and_calc_setpoint(m)
    # report metrics
    metrics_pvc_meter_power.labels("pv").set(m.power_pv)
    metrics_pvc_meter_power.labels("grid").set(m.power_grid)
    metrics_pvc_meter_power_consumption_total.set(m.power_consumption)
    metrics_pvc_charger_power.set(c.power_car)
    metrics_pvc_charger_phases.set(c.phases)
    metrics_pvc_charger_max_current.set(c.max_current)


scheduler = Scheduler(30, controlloop)
scheduler.start()

app = flask.Flask(__name__)
app.add_url_rule("/", view_func=views.StaticResourcesView.as_view("get_index"), defaults={"path": "index.html"})
app.add_url_rule("/<path:path>", view_func=views.StaticResourcesView.as_view("get_static"))
app.add_url_rule("/api/pvcontrol", view_func=views.PvControlView.as_view("get_pvcontrol", meter, charger))
app.add_url_rule("/api/pvcontrol/charger/phases", view_func=views.PvControlChargerPhasesView.as_view("put_charger_phases", charger))

# Add prometheus wsgi middleware to route /metrics requests
app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {"/metrics": prometheus_client.make_wsgi_app()})

app.run(host="0.0.0.0", port=8080)
scheduler.stop()
relay.cleanup()
logger.info("Stopped pvcontrol")
