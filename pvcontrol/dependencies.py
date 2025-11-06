import logging
from argparse import Namespace
from typing import Any

from pvcontrol.car import Car, CarFactory
from pvcontrol.chargecontroller import ChargeController, ChargeControllerFactory
from pvcontrol.meter import Meter, MeterFactory
from pvcontrol.relay import PhaseRelay, PhaseRelayFactory
from pvcontrol.scheduler import AsyncScheduler
from pvcontrol.wallbox import Wallbox, WallboxFactory

logger = logging.getLogger(__name__)

# version file is generated during build
version = "unknown"
try:
    with open("version") as f:
        version = f.read()
except Exception:
    pass

# Initialize the components in async funtion as some need a running event loop
relay: PhaseRelay = None  # pyright: ignore[reportAssignmentType]
wallbox: Wallbox[Any] = None  # pyright: ignore[reportAssignmentType]
meter: Meter[Any] = None  # pyright: ignore[reportAssignmentType]
controller: ChargeController = None  # pyright: ignore[reportAssignmentType]
car: Car[Any] = None  # pyright: ignore[reportAssignmentType]
controller_scheduler: AsyncScheduler = None  # pyright: ignore[reportAssignmentType]
car_scheduler: AsyncScheduler = None  # pyright: ignore[reportAssignmentType]


async def init(args: Namespace, config: dict[str, Any]) -> None:
    logger.info("Initializing depencencies.")
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


# shutdown components and event loop
async def shutdown():
    await controller_scheduler.stop()
    await car_scheduler.stop()
    # disable charging to play it safe
    # TODO: see ChargeMode.INIT handling
    logger.info("Set wallbox.allow_charging=False on shutdown.")
    await wallbox.allow_charging(False)
    await wallbox.close()
    await meter.close()
