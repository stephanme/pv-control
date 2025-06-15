from dataclasses import dataclass
from datetime import datetime
import logging
import typing
import prometheus_client
from pvcontrol.service import BaseConfig, BaseData, BaseService
from aiohttp import ClientSession
from myskoda import MySkoda
from myskoda.models.charging import Charging
from myskoda.models.health import Health

logger = logging.getLogger(__name__)

type CarConfigTypes = CarConfig | SkodaCarConfig


@dataclass
class CarData(BaseData):
    data_captured_at: datetime = datetime.min
    soc: float = 0  # [%] state of charge
    cruising_range: int = 0  # [km]
    mileage: int = 0  # [km]


@dataclass
class CarConfig(BaseConfig):
    cycle_time: int = 5 * 60  # [s] cycle time for reading car data, used by scheduler
    energy_one_percent_soc: int = 580  # [Wh]


C = typing.TypeVar("C", bound=CarConfig)  # type of configuration


class Car(BaseService[C, CarData]):
    """Base class / interface for cars"""

    _metrics_pvc_car_soc = prometheus_client.Gauge("pvcontrol_car_soc_ratio", "State of Charge")
    _metrics_pvc_car_range = prometheus_client.Gauge("pvcontrol_car_cruising_range_meters", "Remaining cruising range")
    _metrics_pvc_car_mileage = prometheus_client.Gauge("pvcontrol_car_mileage_meters", "Mileage")
    _metrics_pvc_car_energy_consumption = prometheus_client.Counter("pvcontrol_car_energy_consumption_wh", "Energy Consumption")

    def __init__(self, config: C):
        super().__init__(config)
        self._set_data(CarData())
        self._last_soc = 0

    async def read_data(self) -> CarData:
        """Read meter data and report metrics. The data is cached."""
        d = await self._read_data()
        self._set_data(d)
        Car._metrics_pvc_car_soc.set(d.soc / 100)
        Car._metrics_pvc_car_range.set(d.cruising_range * 1000)
        Car._metrics_pvc_car_mileage.set(d.mileage * 1000)
        if d.soc < self._last_soc:
            # soc [0..100%], 100% = 58kWh = 58.000 Wh
            Car._metrics_pvc_car_energy_consumption.inc((self._last_soc - d.soc) * self.get_config().energy_one_percent_soc)
        self._last_soc = d.soc
        return d

    async def _read_data(self) -> CarData:
        return self.get_data()


class SimulatedCar(Car[CarConfig]):
    def __init__(self, config: CarConfig):
        super().__init__(config)
        self.set_data(CarData(error=0, data_captured_at=datetime.now(), cruising_range=150, soc=50, mileage=10000))

    def set_data(self, d: CarData):
        self._set_data(d)


# just to permanently grey out car SOC in UI
class NoCar(Car[CarConfig]):
    def __init__(self, config: CarConfig):
        super().__init__(config)
        self.inc_error_counter()
        self.inc_error_counter()
        self.inc_error_counter()
        self.inc_error_counter()

    async def _read_data(self) -> CarData:
        return CarData(data_captured_at=datetime.now())


@dataclass
class SkodaCarConfig(CarConfig):
    user: str = ""
    password: str = ""
    vin: str = ""
    timeout: int = 10  # request timeout
    disabled: bool = False


# myskoda lib uses asyncio, so it assumes a running event loop
class SkodaCar(Car[SkodaCarConfig]):
    def __init__(self, config: SkodaCarConfig):
        super().__init__(config)
        self._session = None
        self._myskoda: MySkoda | None = None

    async def _read_data(self) -> CarData:
        if self.get_config().disabled:
            self.inc_error_counter()
            return CarData()

        try:
            if self._myskoda is None:
                self._myskoda = await self._connect()

            cfg = self.get_config()
            charging: Charging = await self._myskoda.get_charging(cfg.vin)
            health: Health = await self._myskoda.get_health(cfg.vin)

            soc = 0
            cruising_range = 0
            if charging.car_captured_timestamp is not None:
                # convert to datetime
                car_captured_timestamp = charging.car_captured_timestamp
            else:
                car_captured_timestamp = datetime.now()
            if charging.status is not None:
                if charging.status.battery.state_of_charge_in_percent is not None:
                    soc = charging.status.battery.state_of_charge_in_percent
                if charging.status.battery.remaining_cruising_range_in_meters is not None:
                    cruising_range = charging.status.battery.remaining_cruising_range_in_meters // 1000
            if health.mileage_in_km is not None:
                mileage = health.mileage_in_km
            else:
                mileage = 0
            self.reset_error_counter()
            return CarData(
                error=0,
                data_captured_at=car_captured_timestamp,
                soc=soc,
                cruising_range=cruising_range,
                mileage=mileage,
            )
        except Exception as e:
            logger.error(repr(e))
            self.inc_error_counter()
            await self.disconnect()  # enforce reconnection

        return self.get_data()

    async def _connect(self) -> MySkoda:
        cfg = self.get_config()
        self._session = ClientSession()
        self._myskoda = MySkoda(self._session, mqtt_enabled=False)
        await self._myskoda.connect(cfg.user, cfg.password)
        return self._myskoda

    async def disconnect(self):
        if self._myskoda:
            await self._myskoda.disconnect()
            self._myskoda = None
        if self._session:
            await self._session.close()
            self._session = None


class CarFactory:
    @classmethod
    def newCar(cls, type: str, **kwargs) -> Car:
        if type == "SimulatedCar":
            return SimulatedCar(CarConfig(**kwargs))
        if type == "NoCar":
            return NoCar(CarConfig(**kwargs))
        elif type == "SkodaCar":
            return SkodaCar(SkodaCarConfig(**kwargs))
        else:
            raise ValueError(f"Bad car type: {type}")
