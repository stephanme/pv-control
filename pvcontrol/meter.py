from dataclasses import dataclass
import logging
import math
import time
import prometheus_client
from pyModbusTCP.client import ModbusClient
import pyModbusTCP.utils as modbusUtils

from pvcontrol.service import BaseConfig, BaseData, BaseService
from pvcontrol.wallbox import Wallbox

logger = logging.getLogger(__name__)

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


@dataclass
class KostalMeterConfig(BaseConfig):
    host: str = "scb.fritz.box"
    port: int = 1502
    unit_id: int = 71


class KostalMeter(Meter):
    def __init__(self, config: KostalMeterConfig):
        super().__init__()
        self._config = config
        self._modbusClient = ModbusClient(host=self._config.host, port=self._config.port, unit_id=self._config.unit_id, auto_open=True)

    # config
    def get_config(self) -> KostalMeterConfig:
        return self._config

    def _read_data(self) -> MeterData:
        # kpc_home_power_consumption_watts (grid=108, pv=116) -> consumption
        # kpc_ac_power_total_watts #172 -> pv
        # kpc_powermeter_total_watts #252 -> grid
        regs_grid = self._modbusClient.read_holding_registers(252, 2)
        regs_consumption = self._modbusClient.read_holding_registers(108, 10)
        regs_pv = self._modbusClient.read_holding_registers(172, 2)
        if regs_consumption and regs_pv and regs_grid:
            grid = modbusUtils.decode_ieee(modbusUtils.word_list_to_long(regs_grid)[0])
            consumption_l = modbusUtils.word_list_to_long(regs_consumption)
            consumption_grid = modbusUtils.decode_ieee(consumption_l[0])
            consumption_pv = modbusUtils.decode_ieee(consumption_l[4])
            pv = modbusUtils.decode_ieee(modbusUtils.word_list_to_long(regs_pv)[0])
            return MeterData(pv, consumption_grid + consumption_pv, grid)
        else:
            logger.error(f"Modbus error: {self._modbusClient.last_error_txt()}")
            return self._meter_data


class MeterFactory:
    @classmethod
    def newMeter(cls, type: str, wb: Wallbox, **kwargs) -> Meter:
        if type == "KostalMeter":
            return KostalMeter(KostalMeterConfig(**kwargs))
        if type == "SimulatedMeter":
            return SimulatedMeter(SimulatedMeterConfig(**kwargs), wb)
        else:
            raise ValueError(f"Bad meter type: {type}")
