import logging
from pvcontrol import app, relay

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger(__name__)

logger.info("Starting pvcontrol")
app.app.run(host="0.0.0.0", port=8080)
relay.cleanup()
logger.info("Stopped pvcontrol")
