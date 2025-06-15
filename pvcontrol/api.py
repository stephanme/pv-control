from typing import Annotated
import logging
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from pvcontrol import dependencies
from pvcontrol.car import CarConfigTypes, CarData
from pvcontrol.chargecontroller import ChargeControllerConfig, ChargeControllerData, ChargeMode, PhaseMode
from pvcontrol.meter import MeterConfigTypes, MeterData
from pvcontrol.relay import PhaseRelayConfig, PhaseRelayData
from pvcontrol.service import BaseConfig, BaseData, BaseService
from pvcontrol.wallbox import CarStatus, SimulatedWallbox, WallboxConfigTypes, WallboxData

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pvcontrol", tags=["pvcontrol"])


class ServiceResponse[C: BaseConfig, D: BaseData](BaseModel):
    type: str
    config: C
    data: D

    def __init__(self, service: BaseService[C, D]):
        super().__init__(type=type(service).__name__, config=service.get_config(), data=service.get_data())


class PvcontrolResponse(BaseModel):
    version: str = "unknown"
    controller: ChargeControllerData
    meter: MeterData
    wallbox: WallboxData
    relay: PhaseRelayData
    car: CarData


@router.get("")
async def get_root() -> PvcontrolResponse:
    return PvcontrolResponse(
        version=dependencies.version,
        controller=dependencies.controller.get_data(),
        meter=dependencies.meter.get_data(),
        wallbox=dependencies.wallbox.get_data(),
        relay=dependencies.relay.get_data(),
        car=dependencies.car.get_data(),
    )


@router.get("/controller")
async def get_controller() -> ServiceResponse[ChargeControllerConfig, ChargeControllerData]:
    return ServiceResponse[ChargeControllerConfig, ChargeControllerData](dependencies.controller)


# curl -X PUT http://localhost:8080/api/pvcontrol/controller/desired_mode -H 'Content-Type: application/json' --data '"PV_ONLY"'
@router.put("/controller/desired_mode", status_code=204)
async def put_controller_desired_mode(mode: Annotated[ChargeMode, Body()]) -> None:
    dependencies.controller.set_desired_mode(mode)


# curl -X PUT http://localhost:8080/api/pvcontrol/controller/phase_mode -H 'Content-Type: application/json' --data '"CHARGE_1P"'
@router.put("/controller/phase_mode", status_code=204)
async def put_controller_phase_mode(mode: Annotated[PhaseMode, Body()]) -> None:
    dependencies.controller.set_phase_mode(mode)


@router.get("/meter")
async def get_meter() -> ServiceResponse[MeterConfigTypes, MeterData]:
    return ServiceResponse[MeterConfigTypes, MeterData](dependencies.meter)


@router.get("/wallbox")
async def get_wallbox() -> ServiceResponse[WallboxConfigTypes, WallboxData]:
    return ServiceResponse[WallboxConfigTypes, WallboxData](dependencies.wallbox)


# for testing only: SimulatedWallbox
# curl -X PUT http://localhost:8080/api/pvcontrol/wallbox/car_status -H 'Content-Type: application/json' --data 1..4
# 1=NoVehicle, 2=Charging, 3=WaitingForVehicle, 4=ChargingFinished
@router.put("/controller/wallbox/car_status", status_code=204)
async def put_wallbox_car_status(car_status: Annotated[CarStatus, Body()]) -> None:
    if isinstance(dependencies.wallbox, SimulatedWallbox):
        dependencies.wallbox.set_car_status(car_status)
    else:
        raise HTTPException(status_code=422, detail="This endpoint is only available for SimulatedWallbox.")


@router.get("/relay")
async def get_relay() -> ServiceResponse[PhaseRelayConfig, PhaseRelayData]:
    return ServiceResponse[PhaseRelayConfig, PhaseRelayData](dependencies.relay)


@router.get("/car")
async def get_car() -> ServiceResponse[CarConfigTypes, CarData]:
    return ServiceResponse[CarConfigTypes, CarData](dependencies.car)
