import logging
from dataclasses import dataclass
import enum
import typing
import requests
import time
import prometheus_client
from pvcontrol.service import BaseConfig, BaseData, BaseService
from pvcontrol import relay

logger = logging.getLogger(__name__)


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
    phase_relay: bool = False  # on/off - mapping to 1 or 3 phases depends on relay type/wiring
    phases_in: int = 3  # 0..3
    phases_out: int = 0  # 0..3
    power: float = 0  # [W]
    charged_energy: float = 0  # [Wh], energy of last charging
    total_energy: float = 0  # [Wh], total charged energy
    # unlocked_by - RFID card id


C = typing.TypeVar("C", bound=WallboxConfig)  # type of configuration


class Wallbox(BaseService[C, WallboxData]):
    """Base class / interface for wallboxes"""

    _metrics_pvc_wallbox_car_status = prometheus_client.Gauge("pvcontrol_wallbox_car_status", "Wallbox car status")
    _metrics_pvc_wallbox_power = prometheus_client.Gauge("pvcontrol_wallbox_power_watts", "Wallbox total power")
    _metrics_pvc_wallbox_phases_in = prometheus_client.Gauge("pvcontrol_wallbox_phases_in", "Number of phases before wallbox (0..3)")
    _metrics_pvc_wallbox_phases_out = prometheus_client.Gauge(
        "pvcontrol_wallbox_phases_out", "Number of phases for charging after wallbox (0..3)"
    )
    _metrics_pvc_wallbox_max_current = prometheus_client.Gauge("pvcontrol_wallbox_max_current_amperes", "Max current per phase")
    _metrics_pvc_wallbox_allow_charging = prometheus_client.Gauge("pvcontrol_wallbox_allow_charging", "Wallbox allows charging")
    _metrics_pvc_wallbox_phase_relay = prometheus_client.Gauge("pvcontrol_wallbox_phase_relay", "Phase switch relay status (off/on)")

    def __init__(self, config: C):
        super().__init__(config)
        self._set_data(WallboxData())

    def read_data(self) -> WallboxData:
        """Read wallbox data and report metrics. The data is cached."""
        wb = self._read_data()
        self._set_data(wb)
        return wb

    def _read_data(self) -> WallboxData:
        """Override in sub classes"""
        return self.get_data()

    def _set_data(self, wb: WallboxData):
        super()._set_data(wb)
        Wallbox._metrics_pvc_wallbox_car_status.set(wb.car_status)
        Wallbox._metrics_pvc_wallbox_power.set(wb.power)
        Wallbox._metrics_pvc_wallbox_phases_in.set(wb.phases_in)
        Wallbox._metrics_pvc_wallbox_phases_out.set(wb.phases_out)
        Wallbox._metrics_pvc_wallbox_max_current.set(wb.max_current)
        Wallbox._metrics_pvc_wallbox_allow_charging.set(wb.allow_charging)
        Wallbox._metrics_pvc_wallbox_phase_relay.set(wb.phase_relay)

    # set wallbox registers

    def set_phases_in(self, phases: int):
        pass

    def set_max_current(self, max_current: int):
        pass

    def allow_charging(self, f: bool):
        pass

    def trigger_reset(self):
        pass


class SimulatedWallbox(Wallbox[WallboxConfig]):
    """A wallbox simulation for testing"""

    def __init__(self, config: WallboxConfig):
        super().__init__(config)
        self.trigger_reset_cnt = 0

    def _read_data(self) -> WallboxData:
        old = self.get_data()
        wb = WallboxData(**old.__dict__)
        if wb.allow_charging and wb.car_status != CarStatus.ChargingFinished:
            if not old.allow_charging:
                wb.charged_energy = 0
            wb.phases_out = wb.phases_in
            wb.power = wb.phases_out * wb.max_current * 230
            wb.charged_energy += wb.power / 120  # assumption 30s cycle time
            wb.total_energy += wb.power / 120
        else:
            wb.phases_out = 0
            wb.power = 0
        return wb

    def set_wb_error(self, err: WbError):
        self.get_data().wb_error = err

    def set_car_status(self, status: CarStatus):
        self.get_data().car_status = status

    def set_phases_in(self, phases: int):
        self.get_data().phases_in = phases
        self.get_data().phase_relay = phases == 1

    def set_max_current(self, max_current: int):
        self.get_data().max_current = max_current

    def allow_charging(self, f: bool):
        self.get_data().allow_charging = f

    def trigger_reset(self):
        self.trigger_reset_cnt += 1

    def decrement_charge_energy_for_tests(self):
        """needed for chargecontroller tests"""
        wb = self.get_data()
        if wb.allow_charging:
            wb.charged_energy -= wb.power / 120
            wb.total_energy -= wb.power / 120


class SimulatedWallboxWithRelay(SimulatedWallbox):
    def _read_data(self) -> WallboxData:
        ch = relay.readChannel1()
        wb = super()._read_data()
        wb.phases_in = 1 if ch else 3
        wb.phase_relay = ch
        return wb

    def set_phases_in(self, phases: int):
        # relay ON = 1 phase
        relay.writeChannel1(phases == 1)


@dataclass
class GoeWallboxConfig(WallboxConfig):
    url: str = "http://go-echarger.fritz.box"
    timeout: int = 5  # [s] request timeout
    switch_phases_reset_delay: int = 2  # [s] delay between switching phase relay and trigger WB reset


class GoeWallbox(Wallbox[GoeWallboxConfig]):
    def __init__(self, config: GoeWallboxConfig):
        super().__init__(config)
        self._status_url = f"{config.url}/status"
        self._mqtt_url = f"{config.url}/mqtt"
        self._timeout = config.timeout

    def set_phases_in(self, phases: int):
        errcnt = self.get_error_counter()
        phases_out = self.get_data().phases_out
        if errcnt == 0 and phases_out == 0:
            # relay ON = 1 phase
            relay.writeChannel1(phases == 1)
            logger.debug(f"set phases_in={phases}")
            time.sleep(self.get_config().switch_phases_reset_delay)
            self.trigger_reset()
        else:
            logger.warning(f"Rejected set_phases_in({phases}): phases_out={phases_out}, error_counter={errcnt}")

    def set_max_current(self, max_current: int):
        if max_current != self.get_data().max_current:
            try:
                logger.debug(f"set max_current={max_current}")
                res = requests.get(self._mqtt_url, timeout=self._timeout, params={"payload": f"amx={max_current}"})
                wb = GoeWallbox._json_2_wallbox_data(res.json(), relay.readChannel1())
                self._set_data(wb)
            except Exception as e:
                logger.error(e)

    def allow_charging(self, f: bool):
        if f != self.get_data().allow_charging:
            try:
                logger.debug(f"set allow_charging={f}")
                res = requests.get(self._mqtt_url, timeout=self._timeout, params={"payload": f"alw={int(f)}"})
                wb = GoeWallbox._json_2_wallbox_data(res.json(), relay.readChannel1())
                self._set_data(wb)
            except Exception as e:
                logger.error(e)

    def trigger_reset(self):
        try:
            logger.debug("trigger reset")
            requests.get(self._mqtt_url, timeout=self._timeout, params={"payload": "rst=1"})
        except Exception as e:
            logger.error(e)

    def _read_data(self) -> WallboxData:
        try:
            res = requests.get(self._status_url, timeout=self._timeout)
            wb = GoeWallbox._json_2_wallbox_data(res.json(), relay.readChannel1())
            self.reset_error_counter()
            return wb
        except Exception as e:
            logger.error(e)
            self.inc_error_counter()
            # always return last known data - there is no safe state that would somehow help
            return self.get_data()

    @classmethod
    def _json_2_wallbox_data(cls, json: typing.Dict, phase_relay: bool) -> WallboxData:
        wb_error = WbError(int(json["err"]))
        car_status = CarStatus(int(json["car"]))
        max_current = int(json["amp"])
        allow_charging = json["alw"] == "1"
        phases = int(json["pha"])
        phases_in = (phases >> 3) % 2 + (phases >> 4) % 2 + (phases >> 5) % 2
        phases_out = phases % 2 + (phases >> 1) % 2 + (phases >> 2) % 2  # TODO use current or power data not phases
        power = int(json["nrg"][11]) * 10
        charged_energy = int(json["dws"]) / 360.0
        total_energy = int(json["eto"]) * 100
        # check if phases_in is consistent with phase relay state, WB errors dominate
        if wb_error == WbError.OK or wb_error > WbError.INTERNAL:
            if not (phases_in == 3 and not phase_relay or phases_in == 1 and phase_relay):
                wb_error = WbError.PHASE_RELAY_ERR
        wb = WallboxData(
            0, wb_error, car_status, max_current, allow_charging, phase_relay, phases_in, phases_out, power, charged_energy, total_energy
        )
        return wb


class WallboxFactory:
    @classmethod
    def newWallbox(cls, type: str, **kwargs) -> Wallbox:
        if type == "SimulatedWallbox":
            return SimulatedWallbox(WallboxConfig(**kwargs))
        elif type == "SimulatedWallboxWithRelay":
            return SimulatedWallboxWithRelay(WallboxConfig(**kwargs))
        elif type == "GoeWallbox":
            return GoeWallbox(GoeWallboxConfig(**kwargs))
        else:
            raise ValueError(f"Bad wallbox type: {type}")
