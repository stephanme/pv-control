from dataclasses import dataclass
import enum
from pvcontrol.service import BaseConfig, BaseData, BaseService
import prometheus_client
from pvcontrol import relay

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
        self._wallbox_data = wb
        metrics_pvc_wallbox_power.set(wb.power)
        metrics_pvc_wallbox_phases_in.set(wb.phases_in)
        metrics_pvc_wallbox_phases_out.set(wb.phases_out)
        metrics_pvc_wallbox_max_current.set(wb.max_current)
        metrics_pvc_wallbox_allow_charging.set(wb.allow_charging)
        return wb

    def _read_data(self) -> WallboxData:
        return self._wallbox_data

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


class WallboxFactory:
    @classmethod
    def newWallbox(cls, type: str, **kwargs) -> Wallbox:
        if type == "SimulatedWallbox":
            return SimulatedWallbox(WallboxConfig(**kwargs))
        elif type == "SimulatedWallboxWithRelay":
            return SimulatedWallboxWithRelay(WallboxConfig(**kwargs))
        else:
            raise ValueError(f"Bad wallbox type: {type}")
