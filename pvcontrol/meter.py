from contextlib import suppress
from dataclasses import dataclass
import logging
import math
import time
import typing
import aiohttp
import pysmaplus
import pysmaplus.definitions_webconnect
import pysmaplus.sensor
import prometheus_client
from pymodbus.client import AsyncModbusTcpClient

from pvcontrol.service import BaseConfig, BaseData, BaseService
from pvcontrol.wallbox import Wallbox
from pvcontrol.utils import aiohttp_trace_config

logger = logging.getLogger(__name__)

type MeterConfigTypes = KostalMeterConfig | SimulatedMeterConfig | SolarWattMeterConfig | SmaTripowerMeterConfig


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

    async def close(self):
        pass


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
        self._modbusClient = AsyncModbusTcpClient(config.host, port=config.port)
        self._unit = config.unit_id

    async def _read_data(self) -> MeterData:
        try:
            if not self._modbusClient.connected:
                await self._modbusClient.connect()

            # kpc_home_power_consumption_watts (grid=108, pv=116) -> consumption
            # kpc_ac_power_total_watts #172 -> pv
            # kpc_powermeter_total_watts #252 -> grid
            regs_grid = await self._modbusClient.read_holding_registers(252, count=2, slave=self._unit)
            if regs_grid.isError():
                raise Exception(f"Error reading grid data: {regs_grid}")
            regs_consumption = await self._modbusClient.read_holding_registers(108, count=12, slave=self._unit)
            if regs_consumption.isError():
                raise Exception(f"Error reading consumption data: {regs_grid}")
            regs_pv = await self._modbusClient.read_holding_registers(172, count=2, slave=self._unit)
            if regs_pv.isError():
                raise Exception(f"Error reading pv data: {regs_grid}")

            grid = typing.cast(
                float, AsyncModbusTcpClient.convert_from_registers(regs_grid.registers, AsyncModbusTcpClient.DATATYPE.FLOAT32)
            )
            consumption = typing.cast(
                list[float], AsyncModbusTcpClient.convert_from_registers(regs_consumption.registers, AsyncModbusTcpClient.DATATYPE.FLOAT32)
            )
            consumption_grid = consumption[0]
            energy_consumption_grid = consumption[2]
            energy_consumption_pv = consumption[3]
            consumption_pv = consumption[4]
            energy_consumption = consumption[5]
            pv = typing.cast(float, AsyncModbusTcpClient.convert_from_registers(regs_pv.registers, AsyncModbusTcpClient.DATATYPE.FLOAT32))
            self.reset_error_counter()
            return MeterData(
                0, pv, consumption_grid + consumption_pv, grid, energy_consumption, energy_consumption_grid, energy_consumption_pv
            )
        except Exception as e:
            logger.error(e)
            errcnt = self.inc_error_counter()
            if errcnt > 3:
                return MeterData(errcnt)
            else:
                return self.get_data()

    async def close(self):
        self._modbusClient.close()


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
        self._timeout = aiohttp.ClientTimeout(total=config.timeout)
        self._session = aiohttp.ClientSession(trace_configs=[aiohttp_trace_config])

    async def _read_data(self) -> MeterData:
        try:
            async with self._session.get(self._power_flow_url, timeout=self._timeout) as res:
                res.raise_for_status()
                meter_data = self._json_2_meter_data(await res.json())
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

    async def close(self):
        await self._session.close()


@dataclass
class SmaTripowerMeterConfig(BaseConfig):
    url: str = "http://sma.fritz.box"
    verify_ssl: bool = False  # don't verify SSL certificate, useful for self-signed certificates
    password: str = ""
    device_id: str = ""  # device id of the tripower inverter


class SmaTripowerMeter(Meter[SmaTripowerMeterConfig]):
    def __init__(self, config: SmaTripowerMeterConfig):
        super().__init__(config)
        self._session = aiohttp.ClientSession(trace_configs=[aiohttp_trace_config], connector=aiohttp.TCPConnector(ssl=config.verify_ssl))
        self._smaDevice = pysmaplus.SMAwebconnect(self._session, config.url, password=config.password)
        self._deviceId = config.device_id
        self._sensors = pysmaplus.sensor.Sensors(
            [
                pysmaplus.definitions_webconnect.grid_power,
                pysmaplus.definitions_webconnect.pv_power,
                pysmaplus.definitions_webconnect.metering_power_absorbed,
                pysmaplus.definitions_webconnect.metering_power_supplied,
                pysmaplus.definitions_webconnect.total_yield,
                pysmaplus.definitions_webconnect.metering_total_yield,
                pysmaplus.definitions_webconnect.metering_total_absorbed,
            ]
        )
        for sensor in self._sensors:
            sensor.enabled = True  # enable all sensors

    async def _read_data(self) -> MeterData:
        try:
            if self._smaDevice._sid is None:
                await self._smaDevice.new_session()
            await self._smaDevice.read(self._sensors, self._deviceId)
            meter_data = self._sensors_2_meter_data()
            self.reset_error_counter()
            return meter_data
        except Exception as e:
            logger.error(e)
            with suppress(Exception):
                await self._smaDevice.close_session()
            errcnt = self.inc_error_counter()
            if errcnt > 3:
                return MeterData(errcnt)
            else:
                return self.get_data()

    def _sensors_2_meter_data(self) -> MeterData:
        overall_power = self._sensors[pysmaplus.definitions_webconnect.grid_power.key].value
        power_from_grid = self._sensors[pysmaplus.definitions_webconnect.metering_power_absorbed.key].value
        power_to_grid = self._sensors[pysmaplus.definitions_webconnect.metering_power_supplied.key].value

        pv = self._sensors[pysmaplus.definitions_webconnect.pv_power.key].value

        # + from grid, - to grid
        grid = power_from_grid - power_to_grid

        consumption = overall_power - power_to_grid

        # battery charging is considered as home consumption
        energy_to_grid = self._sensors[pysmaplus.definitions_webconnect.metering_total_yield.key].value * 1000
        energy_pv = self._sensors[pysmaplus.definitions_webconnect.total_yield.key].value * 1000
        energy_consumption_grid = self._sensors[pysmaplus.definitions_webconnect.metering_total_absorbed.key].value * 1000
        energy_consumption_pv = energy_pv - energy_to_grid
        energy_consumption = energy_consumption_grid + energy_consumption_pv
        return MeterData(0, pv, consumption, grid, energy_consumption, energy_consumption_grid, energy_consumption_pv)

    async def close(self):
        await self._smaDevice.close_session()
        await self._session.close()


class MeterFactory:
    @classmethod
    def newMeter(cls, type: str, wb: Wallbox, **kwargs) -> Meter:
        if type == "KostalMeter":
            return KostalMeter(KostalMeterConfig(**kwargs))
        if type == "SolarWattMeter":
            return SolarWattMeter(SolarWattMeterConfig(**kwargs))
        if type == "SmaTripowerMeter":
            return SmaTripowerMeter(SmaTripowerMeterConfig(**kwargs))
        if type == "SimulatedMeter":
            return SimulatedMeter(SimulatedMeterConfig(**kwargs), wb)
        else:
            raise ValueError(f"Bad meter type: {type}")
