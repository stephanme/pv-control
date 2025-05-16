from dataclasses import dataclass
import logging
import math
import requests
import time
import typing
import prometheus_client
from pyModbusTCP.client import ModbusClient
import pyModbusTCP.utils as modbusUtils

from pvcontrol.service import BaseConfig, BaseData, BaseService
from pvcontrol.wallbox import Wallbox

logger = logging.getLogger(__name__)


@dataclass
class MeterData(BaseData):
    power_pv: float = 0  # power delivered by PV [W]
    power_consumption: float = 0  # power consumption [W] (including car charing)
    power_grid: float = 0  # power from/to grid [W], + from grid, - to grid
    # power_consumption = power_pv + power_grid
    energy_consumption: float = 0  # [Wh], energy data is needed by chargecontroller (energy charged from pv vs grid)
    energy_consumption_grid: float = 0  # [Wh]
    energy_consumption_pv: float = 0  # [Wh]


C = typing.TypeVar("C", bound=BaseConfig)  # type of configuration


class Meter(BaseService[C, MeterData]):
    """Base class / interface for meters"""

    _metrics_pvc_meter_power = prometheus_client.Gauge("pvcontrol_meter_power_watts", "Power from pv or grid", ["source"])
    _metrics_pvc_meter_power_consumption_total = prometheus_client.Gauge(
        "pvcontrol_meter_power_consumption_total_watts", "Total home power consumption"
    )

    def __init__(self, config: C):
        super().__init__(config)
        self._set_data(MeterData())

    async def read_data(self) -> MeterData:
        """Read meter data and report metrics. The data is cached."""
        m = await self._read_data()
        self._set_data(m)
        Meter._metrics_pvc_meter_power.labels("pv").set(m.power_pv)
        Meter._metrics_pvc_meter_power.labels("grid").set(m.power_grid)
        Meter._metrics_pvc_meter_power_consumption_total.set(m.power_consumption)
        return m

    async def _read_data(self) -> MeterData:
        return self.get_data()


@dataclass
class SimulatedMeterConfig(BaseConfig):
    pv_max: float = 7000  # [W]
    pv_period: float = 60 * 60  # [s]
    consumption_baseline: float = 500  # [W]
    consumption_max: float = 500  # [W] periodic consumption on top of baseline
    consumption_period: float = 5 * 60  # [s]


class SimulatedMeter(Meter[SimulatedMeterConfig]):
    def __init__(self, config: SimulatedMeterConfig, wallbox: Wallbox):
        super().__init__(config)
        self._wallbox = wallbox
        self._energy_grid = 0.0
        self._energy_pv = 0.0

    # config
    def get_config(self) -> SimulatedMeterConfig:
        return typing.cast(SimulatedMeterConfig, super().get_config())

    async def _read_data(self) -> MeterData:
        t = time.time()
        power_car = self._wallbox.get_data().power
        config = self.get_config()
        pv = math.floor(config.pv_max * math.fabs(math.sin(2 * math.pi * t / (config.pv_period))))
        consumption = (
            config.consumption_baseline
            + math.floor(config.consumption_max * math.fabs(math.sin(2 * math.pi * t / (config.consumption_period))))
            + power_car
        )
        grid = consumption - pv
        self._energy_grid += grid / 120  # assumption: 30s cycle time
        self._energy_pv += pv / 120
        return MeterData(0, pv, consumption, grid, self._energy_grid + self._energy_pv, self._energy_grid, self._energy_pv)


class TestMeter(Meter[BaseConfig]):
    def __init__(self, wallbox: Wallbox):
        super().__init__(BaseConfig())
        self._wallbox = wallbox
        self.set_data(0, 0)

    async def _read_data(self) -> MeterData:
        power_car = self._wallbox.get_data().power
        pv = self._pv
        consumption = self._home + power_car
        grid = consumption - pv
        return MeterData(
            0,
            pv,
            consumption,
            grid,
            self._energy_consumption_grid + self._energy_consumption_pv,
            self._energy_consumption_grid,
            self._energy_consumption_pv,
        )

    def set_data(self, pv: float, home: float, energy_consumption_grid: float = 0, energy_consumption_pv: float = 0) -> None:
        self._pv = pv
        self._home = home
        self._energy_consumption_grid = energy_consumption_grid
        self._energy_consumption_pv = energy_consumption_pv


@dataclass
class KostalMeterConfig(BaseConfig):
    host: str = "scb.fritz.box"
    port: int = 1502
    unit_id: int = 71


class KostalMeter(Meter[KostalMeterConfig]):
    def __init__(self, config: KostalMeterConfig):
        super().__init__(config)
        self._modbusClient = ModbusClient(host=config.host, port=config.port, unit_id=config.unit_id, auto_open=True)

    async def _read_data(self) -> MeterData:
        # kpc_home_power_consumption_watts (grid=108, pv=116) -> consumption
        # kpc_ac_power_total_watts #172 -> pv
        # kpc_powermeter_total_watts #252 -> grid
        regs_grid = self._modbusClient.read_holding_registers(252, 2)
        regs_consumption = self._modbusClient.read_holding_registers(108, 12)
        regs_pv = self._modbusClient.read_holding_registers(172, 2)
        if regs_consumption and regs_pv and regs_grid:
            grid = modbusUtils.decode_ieee(modbusUtils.word_list_to_long(regs_grid)[0])
            consumption_l = modbusUtils.word_list_to_long(regs_consumption)
            consumption_grid = modbusUtils.decode_ieee(consumption_l[0])
            energy_consumption_grid = modbusUtils.decode_ieee(consumption_l[2])
            energy_consumption_pv = modbusUtils.decode_ieee(consumption_l[3])
            consumption_pv = modbusUtils.decode_ieee(consumption_l[4])
            energy_consumption = modbusUtils.decode_ieee(consumption_l[5])
            pv = modbusUtils.decode_ieee(modbusUtils.word_list_to_long(regs_pv)[0])
            self.reset_error_counter()
            return MeterData(
                0, pv, consumption_grid + consumption_pv, grid, energy_consumption, energy_consumption_grid, energy_consumption_pv
            )
        else:
            logger.error(f"Modbus error: {self._modbusClient.last_error_txt()}")
            errcnt = self.inc_error_counter()
            if errcnt > 3:
                return MeterData(errcnt)
            else:
                return self.get_data()


@dataclass
class FroniusMeterConfig(BaseConfig):
    url: str = "http://fronius.fritz.box"
    timeout: int = 5  # [s] request timeout


class FroniusMeter(Meter[FroniusMeterConfig]):
    def __init__(self, config: FroniusMeterConfig):
        super().__init__(config)
        self._power_flow_url = f"{config.url}/solar_api/v1/GetPowerFlowRealtimeData.fcgi"
        self._timeout = config.timeout

    async def _read_data(self) -> MeterData:
        try:
            res = requests.get(self._power_flow_url, timeout=self._timeout)
            res.raise_for_status()
            power_flow_data = res.json()
            power_flow_status = power_flow_data["Head"]["Status"]
            if power_flow_status["Code"] != 0:
                raise Exception(
                    f"GetPowerFlowRealtimeData failed: {power_flow_status['Code']}, {power_flow_status['Reason']}, {power_flow_status['UserMessage']}"
                )
            power_flow_site = power_flow_data["Body"]["Data"]["Site"]
            pv = float(power_flow_site["P_PV"])
            grid = float(power_flow_site["P_Grid"])  # + from grid, - to grid
            consumption = float(power_flow_site["P_Load"])  # TODO: check value and sign
            # TODO where to get energy_consumption data? Needed for metrics only (energy to car: pv vs grid)
            energy_consumption = 0
            energy_consumption_grid = 0
            energy_consumption_pv = 0
            self.reset_error_counter()
            return MeterData(0, pv, consumption, grid, energy_consumption, energy_consumption_grid, energy_consumption_pv)
        except Exception as e:
            logger.error(e)
            errcnt = self.inc_error_counter()
            if errcnt > 3:
                return MeterData(errcnt)
            else:
                return self.get_data()


@dataclass
class SolarWattMeterConfig(BaseConfig):
    url: str = "http://solarwatt.fritz.box"
    location_guid: str = ""
    timeout: int = 5  # [s] request timeout


class SolarWattMeter(Meter[SolarWattMeterConfig]):
    def __init__(self, config: SolarWattMeterConfig):
        super().__init__(config)
        self._power_flow_url = f"{config.url}/rest/kiwigrid/wizard/devices"
        self._location_guid = config.location_guid
        self._timeout = config.timeout

    async def _read_data(self) -> MeterData:
        try:
            res = requests.get(self._power_flow_url, timeout=self._timeout)
            res.raise_for_status()
            meter_data = self._json_2_meter_data(res.json())
            self.reset_error_counter()
            return meter_data
        except Exception as e:
            logger.error(e)
            errcnt = self.inc_error_counter()
            if errcnt > 3:
                return MeterData(errcnt)
            else:
                return self.get_data()

    def _json_2_meter_data(self, json: typing.Dict) -> MeterData:
        location_data = next(i for i in json["result"]["items"] if i["guid"] == self._location_guid)["tagValues"]
        pv = location_data["PowerProduced"]["value"]
        consumption = location_data["PowerConsumed"]["value"]
        grid = location_data["PowerConsumedFromGrid"]["value"]  # + from grid, - to grid
        grid -= location_data["PowerOut"]["value"]
        energy_consumption = location_data["WorkConsumed"]["value"]
        energy_consumption_grid = location_data["WorkConsumedFromGrid"]["value"]
        energy_consumption_pv = location_data["WorkConsumedFromProducers"]["value"]
        return MeterData(0, pv, consumption, grid, energy_consumption, energy_consumption_grid, energy_consumption_pv)


class MeterFactory:
    @classmethod
    def newMeter(cls, type: str, wb: Wallbox, **kwargs) -> Meter:
        if type == "KostalMeter":
            return KostalMeter(KostalMeterConfig(**kwargs))
        if type == "FroniusMeter":
            return FroniusMeter(FroniusMeterConfig(**kwargs))
        if type == "SolarWattMeter":
            return SolarWattMeter(SolarWattMeterConfig(**kwargs))
        if type == "SimulatedMeter":
            return SimulatedMeter(SimulatedMeterConfig(**kwargs), wb)
        else:
            raise ValueError(f"Bad meter type: {type}")
