import logging
from typing import cast

from pvcontrol.meter import Meter, MeterFactory
from pvcontrol.chargecontroller import ChargeController, ChargeControllerFactory
from pvcontrol.wallbox import Wallbox, WallboxFactory
from pvcontrol.relay import PhaseRelay, PhaseRelayFactory
from pvcontrol.car import Car, CarFactory
from pvcontrol.scheduler import AsyncScheduler

logger = logging.getLogger(__name__)

# version file is generated during build
version = "unknown"
try:
    with open("version", "r") as f:
        version = f.read()
except Exception:
    pass

# Initialize the components in async funtion as some need a running event loop
# see https://github.com/microsoft/pyright/discussions/2033 how to make pyright happy
relay: PhaseRelay = cast(PhaseRelay, None)
wallbox: Wallbox = cast(Wallbox, None)
meter: Meter = cast(Meter, None)
controller: ChargeController = cast(ChargeController, None)
car: Car = cast(Car, None)
controller_scheduler: AsyncScheduler = cast(AsyncScheduler, None)
car_scheduler: AsyncScheduler = cast(AsyncScheduler, None)


async def init(args, config: dict) -> None:
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
