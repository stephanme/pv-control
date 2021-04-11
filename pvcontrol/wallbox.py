import logging
from dataclasses import dataclass
import enum
import typing
import requests
import prometheus_client
from pvcontrol.service import BaseConfig, BaseData, BaseService
from pvcontrol import relay

logger = logging.getLogger(__name__)

# TODO: more metrics: car status etc
metrics_pvc_wallbox_power = prometheus_client.Gauge("pvcontrol_wallbox_power_watts", "Wallbox total power")
metrics_pvc_wallbox_phases_in = prometheus_client.Gauge("pvcontrol_wallbox_phases_in", "Number of phases before wallbox (0..3)")
metrics_pvc_wallbox_phases_out = prometheus_client.Gauge(
    "pvcontrol_wallbox_phases_out", "Number of phases for charging after wallbox (0..3)"
)
metrics_pvc_wallbox_max_current = prometheus_client.Gauge("pvcontrol_wallbox_max_current_amperes", "Max current per phase")
metrics_pvc_wallbox_allow_charging = prometheus_client.Gauge("metrics_pvc_wallbox_allow_charging", "Wallbox allows charging")


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


@dataclass
class WallboxData(BaseData):
    car_status: CarStatus = CarStatus.NoVehicle
    max_current: int = 16  # [A]
    allow_charging: bool = False
    phases_in: int = 3  # 0..3
    phases_out: int = 0  # 0..3
    power: float = 0  # [W]
    # energy? - may be wrong when switching off in between
    # unlocked_by - RFID card id


class Wallbox(BaseService):
    """ Base class / interface for wallboxes """

    def __init__(self, config: WallboxConfig):
        super().__init__()
        self._wallbox_data = WallboxData()
        self._config = config

    # config
    def get_config(self) -> WallboxConfig:
        return self._config

    # read wallbox data

    def get_data(self) -> WallboxData:
        """ Get last cached wallbox data. """
        return self._wallbox_data

    def read_data(self) -> WallboxData:
        """ Read wallbox data and report metrics. The data is cached. """
        wb = self._read_data()
        self._set_data(wb)
        return wb

    def _read_data(self) -> WallboxData:
        """ Override in sub classes """
        return self._wallbox_data

    def _set_data(self, wb: WallboxData) -> None:
        self._wallbox_data = wb
        metrics_pvc_wallbox_power.set(wb.power)
        metrics_pvc_wallbox_phases_in.set(wb.phases_in)
        metrics_pvc_wallbox_phases_out.set(wb.phases_out)
        metrics_pvc_wallbox_max_current.set(wb.max_current)
        metrics_pvc_wallbox_allow_charging.set(wb.allow_charging)

    # set wallbox registers

    def set_phases_in(self, phases: int) -> None:
        pass

    def set_max_current(self, max_current: int) -> None:
        pass

    def allow_charging(self, f: bool) -> None:
        pass


class SimulatedWallbox(Wallbox):
    """ A wallbox simulation for testing """

    def _read_data(self) -> WallboxData:
        old = self._wallbox_data
        wb = WallboxData(**old.__dict__)
        if wb.allow_charging:
            wb.phases_out = wb.phases_in
            wb.power = wb.phases_out * wb.max_current * 230
        else:
            wb.phases_out = 0
            wb.power = 0
        return wb

    def set_car_status(self, status: CarStatus) -> None:
        self._wallbox_data.car_status = status

    def set_phases_in(self, phases: int) -> None:
        self._wallbox_data.phases_in = phases

    def set_max_current(self, max_current: int) -> None:
        self._wallbox_data.max_current = max_current

    def allow_charging(self, f: bool) -> None:
        self._wallbox_data.allow_charging = f


class SimulatedWallboxWithRelay(SimulatedWallbox):
    def _read_data(self) -> WallboxData:
        ch = relay.readChannel1()
        wb = super()._read_data()
        wb.phases_in = 1 if ch else 3
        return wb

    def set_phases_in(self, phases: int) -> None:
        # relay ON = 1 phase
        relay.writeChannel1(phases == 1)


@dataclass
class GoeWallboxConfig(WallboxConfig):
    url: str = "http://go-echarger.fritz.box"
    timeout: int = 5  # request timeout


class GoeWallbox(Wallbox):
    def __init__(self, config: GoeWallboxConfig):
        super().__init__(config)
        self._status_url = f"{config.url}/status"
        self._mqtt_url = f"{config.url}/mqtt"
        self._timeout = config.timeout

    # config with correct type
    def get_config(self) -> GoeWallboxConfig:
        return typing.cast(GoeWallboxConfig, super().get_config())

    def set_phases_in(self, phases: int) -> None:
        errcnt = self.get_error_counter()
        phases_out = self._wallbox_data.phases_out
        if errcnt == 0 and phases_out == 0:
            # relay ON = 1 phase
            relay.writeChannel1(phases == 1)
            logger.debug(f"set phases_in={phases}")
        else:
            logger.warn(f"Rejected set_phases_in({phases}): phases_out={phases_out}, error_counter={errcnt}")

    def set_max_current(self, max_current: int) -> None:
        if max_current != self._wallbox_data.max_current:
            try:
                logger.debug(f"set max_current={max_current}")
                res = requests.get(self._mqtt_url, timeout=self._timeout, params={"payload": f"amx={max_current}"})
                wb = GoeWallbox._json_2_wallbox_data(res.json())
                self._set_data(wb)
            except Exception as e:
                logger.error(e)

    def allow_charging(self, f: bool) -> None:
        if f != self._wallbox_data.allow_charging:
            try:
                logger.debug(f"set allow_charging={f}")
                res = requests.get(self._mqtt_url, timeout=self._timeout, params={"payload": f"alw={int(f)}"})
                wb = GoeWallbox._json_2_wallbox_data(res.json())
                self._set_data(wb)
            except Exception as e:
                logger.error(e)

    def _read_data(self) -> WallboxData:
        try:
            res = requests.get(self._status_url, timeout=self._timeout)
            wb = GoeWallbox._json_2_wallbox_data(res.json())
            self.reset_error_counter()
            return wb
        except Exception as e:
            logger.error(e)
            errcnt = self.inc_error_counter()
            if errcnt > 3:
                return WallboxData(errcnt)
            else:
                self._wallbox_data.error = errcnt
                return self._wallbox_data

    @classmethod
    def _json_2_wallbox_data(cls, json) -> WallboxData:
        car_status = CarStatus(int(json["car"]))
        max_current = int(json["amp"])
        allow_charging = json["alw"] == "1"
        phases = int(json["pha"])
        phases_in = (phases >> 3) % 2 + (phases >> 4) % 2 + (phases >> 5) % 2
        phases_out = phases % 2 + (phases >> 1) % 2 + (phases >> 2) % 2  # TODO use current or power data not phases
        power = int(json["nrg"][11]) * 10
        wb = WallboxData(0, car_status, max_current, allow_charging, phases_in, phases_out, power)
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
