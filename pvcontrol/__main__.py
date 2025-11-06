import argparse
import json
import logging
import platform
import sys

import uvicorn
import uvicorn.config

from pvcontrol import LOG_FORMAT, app, dependencies

logging.getLogger("pymodbus.logging").setLevel(logging.INFO)
logging.getLogger("aiohttp.trace").setLevel(logging.INFO)
logging.getLogger("pysmaplus").setLevel(logging.INFO)

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
args = parser.parse_args()

logger.info(f"Starting pvcontrol, version={dependencies.version}")
logger.info(f"Meter:   {args.meter}")
logger.info(f"Wallbox: {args.wallbox}")
logger.info(f"Relay:   {args.relay}")
logger.info(f"Car:     {args.car}")
logger.info(f"config:  {args.config}")
logger.info(f"hostname:{args.hostname}")
logger.info(f"Running on {platform.machine()} / {sys.platform}")
config = json.loads(args.config)
for c in ["wallbox", "meter", "car", "controller", "relay"]:
    if c not in config:
        config[c] = {}

app.args = args
app.config = config

log_config = uvicorn.config.LOGGING_CONFIG
log_config["formatters"]["default"]["fmt"] = LOG_FORMAT
log_config["formatters"]["access"]["fmt"] = LOG_FORMAT
uvicorn.run("pvcontrol.app:app", host=args.host, port=args.port, log_config=log_config)
