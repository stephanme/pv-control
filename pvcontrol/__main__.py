import logging
import flask
import argparse
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


def controlloop():
    if meter.is_simulated():
        c = charger.get_charger_data()
        meter.set_charger_data_for_simulation(c.phases * c.current_setpoint * 230)
    m = meter.read_meter()
    charger.read_charger_and_calc_setpoint(m)


scheduler = Scheduler(30, controlloop)
scheduler.start()

app = flask.Flask(__name__)
app.add_url_rule("/", view_func=views.StaticResourcesView.as_view("get_index"), defaults={"path": "index.html"})
app.add_url_rule("/<path:path>", view_func=views.StaticResourcesView.as_view("get_static"))
app.add_url_rule("/api/pvcontrol", view_func=views.PvControlView.as_view("get_pvcontrol", meter, charger))
app.add_url_rule("/api/pvcontrol/charger/phases", view_func=views.PvControlChargerPhasesView.as_view("put_charger_phases", charger))

app.run(host="0.0.0.0", port=8080)
scheduler.stop()
relay.cleanup()
logger.info("Stopped pvcontrol")
