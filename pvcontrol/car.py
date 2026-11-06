import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, override

from aiohttp import ClientSession, ClientTimeout
from prometheus_client import Counter, Gauge
from skoda_public_api.api_layer.const import BETA_URL
from skoda_public_api.api_layer.exceptions import OpenApiAuthenticationError, OpenApiError, OpenApiRateLimitError
from skoda_public_api.api_layer.open_api_client import OpenAPIClient
from skoda_public_api.models.vehicle import VehicleResponse

from pvcontrol.service import BaseConfig, BaseData, BaseService

logger = logging.getLogger(__name__)

# one request per cycle fetches everything we need: the Skoda Public API is rate limited to ~20 requests per hour and vehicle
_API_INCLUDES = ["charging", "odometer"]
_API_KEY_HELP = "Create a new API key in the MySkoda app (https://go.skoda.eu/api-keys) and update the car configuration."
_API_KEY_WARNING_DAYS = 7


def _parse_timestamp(timestamp: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp of the Skoda Public API, e.g. '2026-06-29T08:00:00Z'."""
    if not timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        logger.warning(f"Could not parse Skoda API timestamp: {timestamp}")
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


type CarConfigTypes = CarConfig | SkodaCarConfig


@dataclass
class CarData(BaseData):
    data_captured_at: datetime = datetime.min
    soc: float = 0  # [%] state of charge
    cruising_range: int = 0  # [km]
    mileage: int = 0  # [km]


@dataclass
class CarConfig(BaseConfig):
    # the Skoda Public API allows only ~20 requests per hour and vehicle, so cycle_time should not be lower than 180s
    cycle_time: int = 5 * 60  # [s] cycle time for reading car data, used by scheduler
    energy_one_percent_soc: int = 580  # [Wh]


class Car[C: CarConfig](BaseService[C, CarData]):
    """Base class / interface for cars"""

    _metrics_pvc_car_soc: Gauge = Gauge("pvcontrol_car_soc_ratio", "State of Charge")
    _metrics_pvc_car_range: Gauge = Gauge("pvcontrol_car_cruising_range_meters", "Remaining cruising range")
    _metrics_pvc_car_mileage: Gauge = Gauge("pvcontrol_car_mileage_meters", "Mileage")
    _metrics_pvc_car_energy_consumption: Counter = Counter("pvcontrol_car_energy_consumption_wh", "Energy Consumption")

    def __init__(self, config: C):
        super().__init__(config, CarData())
        self._last_soc: float = 0

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

    async def close(self) -> None:
        """Close connections. Overridden by implementations which hold resources."""

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

    @override
    async def _read_data(self) -> CarData:
        return CarData(data_captured_at=datetime.now())


@dataclass
class SkodaCarConfig(CarConfig):
    api_key: str = ""  # API key created in the MySkoda app
    vin: str = ""
    endpoint: str = BETA_URL  # Skoda Public API endpoint
    timeout: int = 10  # request timeout [s]
    rate_limit_backoff: int = 15 * 60  # [s] fallback pause after a rate limit error (429), if the quota headers are unknown
    disabled: bool = False


class SkodaCar(Car[SkodaCarConfig]):
    """Reads car data from the Skoda Public API (https://public.api.connect.skoda-auto.cz/docs).

    The API authenticates with an API key instead of user credentials and is rate limited per vehicle,
    therefore a single request per cycle fetches charging and odometer data at once.
    """

    def __init__(self, config: SkodaCarConfig):
        super().__init__(config)
        self._session: ClientSession | None = None
        self._client: OpenAPIClient | None = None
        self._next_request_at: datetime | None = None
        self._key_expiry_warning_logged = False

    @override
    async def _read_data(self) -> CarData:
        cfg = self.get_config()
        if cfg.disabled:
            self.inc_error_counter()
            return CarData()

        if not cfg.api_key or not cfg.vin:
            logger.error("Skoda car is not configured: both api_key and vin are required.")
            self.inc_error_counter()
            return self.get_data()

        if self._next_request_at is not None and datetime.now(UTC) < self._next_request_at:
            logger.info(f"Skipping Skoda API request because of rate limit backoff, retrying after {self._next_request_at}.")
            self.inc_error_counter()
            return self.get_data()

        try:
            if self._client is None:
                self._client = self._connect()

            response: VehicleResponse = await self._client.get_vehicle(cfg.vin, include=_API_INCLUDES)
            self._log_api_errors(response)
            self._log_key_expiry()
            self._track_rate_limit()

            charging = response.vehicle.charging
            odometer = response.vehicle.odometer
            if charging is None and odometer is None:
                logger.error(
                    f"Skoda API returned neither charging nor odometer data for VIN {cfg.vin}: {[e.type for e in response.errors]}"
                )
                self.inc_error_counter()
                return self.get_data()

            soc = 0
            cruising_range = 0
            if charging is not None and charging.status is not None and charging.status.battery is not None:
                battery = charging.status.battery
                soc = battery.state_of_charge_in_percent or 0
                cruising_range = (battery.remaining_cruising_range_in_meters or 0) // 1000

            data_captured_at = _parse_timestamp(charging.car_captured_timestamp if charging is not None else None)
            if data_captured_at is None and odometer is not None:
                data_captured_at = _parse_timestamp(odometer.car_captured_timestamp)
            if data_captured_at is None:
                data_captured_at = datetime.now()

            mileage = odometer.mileage_in_km if odometer is not None else 0

            self.reset_error_counter()
            return CarData(
                error=0,
                data_captured_at=data_captured_at,
                soc=soc,
                cruising_range=cruising_range,
                mileage=mileage,
            )
        except OpenApiAuthenticationError as e:
            logger.error(f"Skoda API rejected the API key: {e} {_API_KEY_HELP}")
            self.inc_error_counter()
        except OpenApiRateLimitError as e:
            self._set_next_request_at(timedelta(seconds=cfg.rate_limit_backoff))
            logger.warning(f"Skoda API rate limit exceeded: {e} Requesting car data again after {self._next_request_at}.")
            self.inc_error_counter()
        except OpenApiError as e:
            logger.error(repr(e))
            self.inc_error_counter()
            await self.close()  # enforce reconnection
        except Exception as e:
            logger.error(repr(e))
            self.inc_error_counter()
            await self.close()  # enforce reconnection

        return self.get_data()

    def _connect(self) -> OpenAPIClient:
        cfg = self.get_config()
        self._session = ClientSession(timeout=ClientTimeout(total=cfg.timeout))
        logger.info(f"Connecting to Skoda Public API at {cfg.endpoint} for VIN {cfg.vin}.")
        return OpenAPIClient(api_key=cfg.api_key, session=self._session, base_url=cfg.endpoint)

    @staticmethod
    def _log_api_errors(response: VehicleResponse) -> None:
        """The API reports data it could not deliver as informational errors, the request itself succeeded."""
        for error in response.errors:
            logger.warning(f"Skoda API reported {error.type}: {error.description}")

    def _track_rate_limit(self) -> None:
        """Schedule the next request from the RateLimit headers of the last successful response.

        The API returns Retry-After on a 429, but skoda-public-api discards the headers of error
        responses, so we use RateLimit-Remaining/RateLimit-Reset of the requests that succeeded to
        stop polling before the quota is exhausted, and fall back to rate_limit_backoff on a 429.
        """
        if self._client is None:
            return
        remaining = self._client.rate_limit_remaining
        reset = self._client.rate_limit_reset
        logger.debug(f"Skoda API quota: {remaining} requests left, window resets in {reset}s.")
        if remaining is None or reset is None or remaining > 0 or reset <= 0:
            return
        self._set_next_request_at(timedelta(seconds=reset))
        logger.warning(f"Skoda API request quota exhausted, requesting car data again after {self._next_request_at}.")

    def _set_next_request_at(self, pause: timedelta) -> None:
        """Remember the earliest time to request car data again, never shortening a pending pause."""
        next_request_at = datetime.now(UTC) + pause
        if self._next_request_at is None or next_request_at > self._next_request_at:
            self._next_request_at = next_request_at

    def _log_key_expiry(self) -> None:
        if self._key_expiry_warning_logged or self._client is None:
            return
        expires_at = _parse_timestamp(self._client.api_key_expires_at)
        if expires_at is not None and expires_at <= datetime.now(UTC) + timedelta(days=_API_KEY_WARNING_DAYS):
            logger.warning(f"The Skoda API key expires at {expires_at}. {_API_KEY_HELP}")
            self._key_expiry_warning_logged = True

    async def close(self) -> None:
        self._client = None
        if self._session:
            await self._session.close()
            self._session = None

    async def disconnect(self) -> None:
        """Alias of close() for backwards compatibility."""
        await self.close()


class CarFactory:
    @classmethod
    def newCar(cls, type: str, **kwargs: Any) -> Car[Any]:
        if type == "SimulatedCar":
            return SimulatedCar(CarConfig(**kwargs))
        if type == "NoCar":
            return NoCar(CarConfig(**kwargs))
        elif type == "SkodaCar":
            return SkodaCar(SkodaCarConfig(**kwargs))
        else:
            raise ValueError(f"Bad car type: {type}")
