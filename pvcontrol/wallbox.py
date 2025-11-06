import asyncio
import enum
import logging
from dataclasses import dataclass
from typing import Any, override

import aiohttp
from prometheus_client import Gauge

from pvcontrol.relay import PhaseRelay
from pvcontrol.service import BaseConfig, BaseData, BaseService
from pvcontrol.utils import aiohttp_trace_config

logger = logging.getLogger(__name__)

type WallboxConfigTypes = WallboxConfig | GoeWallboxConfig


@dataclass
class WallboxConfig(BaseConfig):
    min_supported_current: int = 6
    max_supported_current: int = 16


@enum.unique
class CarStatus(enum.IntEnum):
    NoVehicle = 1  # charging station ready, no vehicle
    Charging = 2  # vehicle loads
    WaitingForVehicle = 3  # Waiting for vehicle
    ChargingFinished = 4  # Charge finished, vehicle still connected


@enum.unique
class WbError(enum.IntEnum):
    OK = 0
    RCCB = 1  # RCCB (Residual Current Device)
    PHASE = 3  # phase disturbance
    NO_GROUND = 8  # earthing detection
    INTERNAL = 10  # other
    # 20 seems to be alw=1 (no error)
    PHASE_RELAY_ERR = 100  # inconsistency between phase relay and phases-in


@dataclass
class WallboxData(BaseData):
    wb_error: WbError = WbError.OK  # wb error status (!= error which means communication error)
    car_status: CarStatus = CarStatus.NoVehicle
    max_current: int = 16  # [A]
    allow_charging: bool = False
    phases_in: int = 1  # 0..3
    phases_out: int = 0  # 0..3
    power: float = 0  # [W]
    charged_energy: float = 0  # [Wh], energy of last charging
    total_energy: float = 0  # [Wh], total charged energy
    temperature: float = 0  # grad celsius
    # unlocked_by - RFID card id


class Wallbox[C: WallboxConfig](BaseService[C, WallboxData]):
    """Base class / interface for wallboxes"""

    _metrics_pvc_wallbox_car_status: Gauge = Gauge("pvcontrol_wallbox_car_status", "Wallbox car status")
    _metrics_pvc_wallbox_power: Gauge = Gauge("pvcontrol_wallbox_power_watts", "Wallbox total power")
    _metrics_pvc_wallbox_phases_in: Gauge = Gauge("pvcontrol_wallbox_phases_in", "Number of phases before wallbox (0..3)")
    _metrics_pvc_wallbox_phases_out: Gauge = Gauge("pvcontrol_wallbox_phases_out", "Number of phases for charging after wallbox (0..3)")
    _metrics_pvc_wallbox_max_current: Gauge = Gauge("pvcontrol_wallbox_max_current_amperes", "Max current per phase")
    _metrics_pvc_wallbox_allow_charging: Gauge = Gauge("pvcontrol_wallbox_allow_charging", "Wallbox allows charging")
    _metrics_pvc_wallbox_temperature: Gauge = Gauge("pvcontrol_wallbox_temperature_celsius", "Wallbox temperature")

    def __init__(self, config: C):
        super().__init__(config, WallboxData())

    async def read_data(self) -> WallboxData:
        """Read wallbox data and report metrics. The data is cached."""
        wb = await self._read_data()
        self._set_data(wb)
        return wb

    async def _read_data(self) -> WallboxData:
        """Override in sub classes"""
        return self.get_data()

    @override
    def _set_data(self, data: WallboxData):
        super()._set_data(data)
        Wallbox._metrics_pvc_wallbox_car_status.set(data.car_status)
        Wallbox._metrics_pvc_wallbox_power.set(data.power)
        Wallbox._metrics_pvc_wallbox_phases_in.set(data.phases_in)
        Wallbox._metrics_pvc_wallbox_phases_out.set(data.phases_out)
        Wallbox._metrics_pvc_wallbox_max_current.set(data.max_current)
        Wallbox._metrics_pvc_wallbox_allow_charging.set(data.allow_charging)
        Wallbox._metrics_pvc_wallbox_temperature.set(data.temperature)

    # set wallbox registers

    async def set_phases_in(self, _phases: int):
        pass

    async def set_max_current(self, _max_current: int):
        pass

    async def allow_charging(self, _f: bool):
        pass

    async def trigger_reset(self):
        pass

    async def close(self):
        pass


class SimulatedWallbox(Wallbox[WallboxConfig]):
    """A wallbox simulation for testing"""

    def __init__(self, config: WallboxConfig):
        super().__init__(config)
        self.trigger_reset_cnt: int = 0

    @override
    async def _read_data(self) -> WallboxData:
        old = self.get_data()
        wb = WallboxData(**old.__dict__)
        if wb.allow_charging and wb.car_status not in [CarStatus.NoVehicle, CarStatus.ChargingFinished]:
            if not old.allow_charging:
                wb.charged_energy = 0
            wb.phases_out = wb.phases_in
            wb.power = wb.phases_out * wb.max_current * 230
            wb.charged_energy += wb.power / 120  # assumption 30s cycle time
            wb.total_energy += wb.power / 120
        else:
            wb.phases_out = 0
            wb.power = 0
            if wb.car_status == CarStatus.NoVehicle:
                wb.allow_charging = False
        return wb

    def set_wb_error(self, err: WbError):
        self.get_data().wb_error = err

    def set_car_status(self, status: CarStatus):
        self.get_data().car_status = status

    @override
    async def set_phases_in(self, phases: int):
        self.get_data().phases_in = phases

    @override
    async def set_max_current(self, max_current: int):
        self.get_data().max_current = max_current

    @override
    async def allow_charging(self, f: bool):
        self.get_data().allow_charging = f

    @override
    async def trigger_reset(self):
        self.trigger_reset_cnt += 1

    def decrement_charge_energy_for_tests(self):
        """needed for chargecontroller tests"""
        wb = self.get_data()
        if wb.allow_charging:
            wb.charged_energy -= wb.power / 120
            wb.total_energy -= wb.power / 120


class SimulatedWallboxWithRelay(SimulatedWallbox):
    def __init__(self, config: WallboxConfig, relay: PhaseRelay):
        super().__init__(config)
        self._relay: PhaseRelay = relay
        self.trigger_reset_cnt: int = 0

    @override
    async def _read_data(self) -> WallboxData:
        wb = await super()._read_data()
        wb.phases_in = self._relay.get_phases()
        return wb

    @override
    async def set_phases_in(self, phases: int):
        self._relay.set_phases(phases)


@dataclass
class GoeWallboxConfig(WallboxConfig):
    url: str = "http://go-echarger.fritz.box"
    timeout: int = 5  # [s] request timeout
    switch_phases_reset_delay: int = 2  # [s] delay between switching phase relay and trigger WB reset


class GoeWallbox(Wallbox[GoeWallboxConfig]):
    def __init__(self, config: GoeWallboxConfig, relay: PhaseRelay):
        super().__init__(config)
        self._relay: PhaseRelay = relay
        self._status_url: str = f"{config.url}/status"
        self._mqtt_url: str = f"{config.url}/mqtt"
        self._timeout: aiohttp.ClientTimeout = aiohttp.ClientTimeout(total=config.timeout)
        self._session: aiohttp.ClientSession = aiohttp.ClientSession(trace_configs=[aiohttp_trace_config])

    @override
    async def set_phases_in(self, phases: int):
        errcnt = self.get_error_counter()
        phases_out = self.get_data().phases_out
        if errcnt == 0 and phases_out == 0:
            # relay ON = 1 phase
            self._relay.set_phases(phases)
            logger.debug(f"set phases_in={phases}")
            await asyncio.sleep(self.get_config().switch_phases_reset_delay)
            await self.trigger_reset()
        else:
            logger.warning(f"Rejected set_phases_in({phases}): phases_out={phases_out}, error_counter={errcnt}")

    @override
    async def set_max_current(self, max_current: int):
        if max_current != self.get_data().max_current:
            try:
                logger.debug(f"set max_current={max_current}")
                async with self._session.get(self._mqtt_url, timeout=self._timeout, params={"payload": f"amx={max_current}"}) as res:
                    res.raise_for_status()
                    wb = self._json_2_wallbox_data(await res.json())
                    self._set_data(wb)
            except Exception as e:
                logger.error(e)

    @override
    async def allow_charging(self, f: bool):
        if f != self.get_data().allow_charging:
            try:
                logger.debug(f"set allow_charging={f}")
                async with self._session.get(self._mqtt_url, timeout=self._timeout, params={"payload": f"alw={int(f)}"}) as res:
                    res.raise_for_status()
                    wb = self._json_2_wallbox_data(await res.json())
                    self._set_data(wb)
            except Exception as e:
                logger.error(e)

    @override
    async def trigger_reset(self):
        try:
            logger.debug("trigger reset")
            async with self._session.get(self._mqtt_url, timeout=self._timeout, params={"payload": "rst=1"}) as res:
                res.raise_for_status()
                wb = self._json_2_wallbox_data(await res.json())
                self._set_data(wb)
        except Exception as e:
            logger.error(e)

    @override
    async def _read_data(self) -> WallboxData:
        try:
            async with self._session.get(self._status_url, timeout=self._timeout) as res:
                res.raise_for_status()
                wb = self._json_2_wallbox_data(await res.json())
                self.reset_error_counter()
                return wb
        except Exception as e:
            logger.error(e)
            self.inc_error_counter()
            # always return last known data - there is no safe state that would somehow help
            return self.get_data()

    def _json_2_wallbox_data(self, json: dict[str, Any]) -> WallboxData:
        wb_error = WbError(int(json["err"]))
        car_status = CarStatus(int(json["car"]))
        max_current = int(json["amp"])
        allow_charging = json["alw"] == "1"
        phases = int(json["pha"])
        phases_in = (phases >> 3) % 2 + (phases >> 4) % 2 + (phases >> 5) % 2
        phases_out = phases % 2 + (phases >> 1) % 2 + (phases >> 2) % 2  # TODO use current or power data not phases
        # can't have phases_out > phases_in (older go-e has problems here on low currents)
        phases_out = min(phases_out, phases_in)
        power = int(json["nrg"][11]) * 10
        charged_energy = int(json["dws"]) / 360.0
        total_energy = int(json["eto"]) * 100
        # v2: tmp
        # v3: tma is an array of different temperatures, exact meaning is not specified
        # use the lowest temperature that should match the outside temperature as good as possible
        if "tma" in json:
            temperature = min(json["tma"])
        else:
            temperature = int(json["tmp"])
        # check if phases_in is consistent with phase relay state (if enabled), WB errors dominate
        if self._relay.is_enabled() and (wb_error == WbError.OK or wb_error > WbError.INTERNAL):
            if phases_in != self._relay.get_phases():
                wb_error = WbError.PHASE_RELAY_ERR
        wb = WallboxData(
            0,
            wb_error,
            car_status,
            max_current,
            allow_charging,
            phases_in,
            phases_out,
            power,
            charged_energy,
            total_energy,
            temperature,
        )
        return wb

    @override
    async def close(self):
        await self._session.close()


class WallboxFactory:
    @classmethod
    def newWallbox(cls, type: str, relay: PhaseRelay, **kwargs: Any) -> Wallbox[Any]:
        if type == "SimulatedWallbox":
            return SimulatedWallbox(WallboxConfig(**kwargs))
        elif type == "SimulatedWallboxWithRelay":
            return SimulatedWallboxWithRelay(WallboxConfig(**kwargs), relay)
        elif type == "GoeWallbox":
            return GoeWallbox(GoeWallboxConfig(**kwargs), relay)
        else:
            raise ValueError(f"Bad wallbox type: {type}")
