from dataclasses import dataclass
import math
import time
import prometheus_client

from pvcontrol.service import BaseConfig, BaseData, BaseService
from pvcontrol.wallbox import Wallbox

metrics_pvc_meter_power = prometheus_client.Gauge("pvcontrol_meter_power_watts", "Power from pv or grid", ["source"])
metrics_pvc_meter_power_consumption_total = prometheus_client.Gauge(
    "pvcontrol_meter_power_consumption_total_watts", "Total home power consumption"
)


@dataclass
class MeterData(BaseData):
    power_pv: float  # power delivered by PV [W]
    power_consumption: float  # power consumption [W] (including car charing)
    power_grid: float  # power from/to grid [W], + from grid, - to grid
    # power_consumption = power_pv + power_grid


class Meter(BaseService):
    """ Base class / interface for meters """

    def __init__(self):
        self._meter_data = MeterData(0, 0, 0)

    def get_data(self) -> MeterData:
        """ Get last cached meter data. """
        return self._meter_data

    def read_data(self) -> MeterData:
        """ Read meter data and report metrics. The data is cached. """
        m = self._read_data()
        self._meter_data = m
        metrics_pvc_meter_power.labels("pv").set(m.power_pv)
        metrics_pvc_meter_power.labels("grid").set(m.power_grid)
        metrics_pvc_meter_power_consumption_total.set(m.power_consumption)
        return m

    def _read_data(self) -> MeterData:
        return self._meter_data


@dataclass
class SimulatedMeterConfig(BaseConfig):
    pv_max: float = 7000  # [W]
    pv_period: float = 60 * 60  # [s]
    consumption_baseline: float = 500  # [W]
    consumption_max: float = 500  # [W] periodic consumption on top of baseline
    consumption_period: float = 5 * 60  # [s]


class SimulatedMeter(Meter):
    def __init__(self, config: SimulatedMeterConfig, wallbox: Wallbox):
        super().__init__()
        self._config = config
        self._wallbox = wallbox

    # config
    def get_config(self) -> SimulatedMeterConfig:
        return self._config

    def _read_data(self) -> MeterData:
        t = time.time()
        power_car = self._wallbox.get_data().power
        pv = math.floor(self._config.pv_max * math.fabs(math.sin(2 * math.pi * t / (self._config.pv_period))))
        consumption = (
            self._config.consumption_baseline
            + math.floor(self._config.consumption_max * math.fabs(math.sin(2 * math.pi * t / (self._config.consumption_period))))
            + power_car
        )
        grid = consumption - pv
        return MeterData(pv, consumption, grid)


class TestMeter(Meter):
    def __init__(self, wallbox: Wallbox):
        super().__init__()
        self._wallbox = wallbox
        self.set_data(0, 0)

    def _read_data(self) -> MeterData:
        power_car = self._wallbox.get_data().power
        pv = self._pv
        consumption = self._home + power_car
        grid = consumption - pv
        return MeterData(pv, consumption, grid)

    def set_data(self, pv: float, home: float) -> None:
        self._pv = pv
        self._home = home


class MeterFactory:
    @classmethod
    def newMeter(cls, type: str, wb: Wallbox, **kwargs) -> Meter:
        if type == "SimulatedMeter":
            return SimulatedMeter(SimulatedMeterConfig(**kwargs), wb)
        else:
            raise ValueError(f"Bad meter type: {type}")
