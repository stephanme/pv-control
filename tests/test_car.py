import datetime
import json
import logging
import os
import unittest
from typing import Any, final, override
from unittest.mock import AsyncMock, MagicMock

from skoda_public_api.api_layer.exceptions import OpenApiAuthenticationError, OpenApiRateLimitError
from skoda_public_api.models.vehicle import VehicleResponse

from pvcontrol.car import (
    POLL_CHECK_INTERVAL,
    Car,
    CarConfig,
    CarData,
    CarPoller,
    SimulatedCar,
    SkodaCar,
    SkodaCarConfig,
)
from pvcontrol.wallbox import CarStatus, SimulatedWallbox, WallboxConfig

# pyright: reportUninitializedInstanceVariable=false
# pyright: reportPrivateUsage=false


logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
# logging.getLogger("urllib3.connectionpool").setLevel(logging.INFO)

# read config file
car_config_file = f"{os.path.dirname(__file__)}/car_test_config.json"
car_config: Any = {}
if os.path.isfile(car_config_file):
    with open(car_config_file) as f:
        car_config = json.load(f)


@final
class FakeClock:
    """Stand-in for the wall clock, so the poller schedule can be tested without waiting."""

    def __init__(self, now: datetime.datetime):
        self.now = now

    def __call__(self) -> datetime.datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += datetime.timedelta(seconds=seconds)


@final
class CountingCar(Car[CarConfig]):
    """Car that counts reads and can simulate a provider backoff like the Skoda rate limit."""

    def __init__(self, config: CarConfig):
        super().__init__(config)
        self.read_cnt = 0
        self.backoff_until: datetime.datetime | None = None

    @override
    async def _read_data(self) -> CarData:
        self.read_cnt += 1
        return CarData(data_captured_at=datetime.datetime.now(datetime.UTC), soc=50)

    @override
    def earliest_request_at(self) -> datetime.datetime | None:
        return self.backoff_until


@final
class CarPollerTest(unittest.IsolatedAsyncioTestCase):
    """Verifies the cycle times of CarPoller: fast while charging, slow when idle."""

    CYCLE_TIME = 900
    CYCLE_TIME_IDLE = 3600

    @override
    def setUp(self):
        self.clock = FakeClock(datetime.datetime(2026, 6, 29, 12, 0, tzinfo=datetime.UTC))
        self.car = CountingCar(CarConfig(cycle_time=self.CYCLE_TIME, cycle_time_idle=self.CYCLE_TIME_IDLE))
        self.wallbox = SimulatedWallbox(WallboxConfig())
        self.poller = CarPoller(self.car, self.wallbox, self.clock)

    def _set_charging(self, charging: bool) -> None:
        self.wallbox.set_car_status(CarStatus.Charging if charging else CarStatus.NoVehicle)

    async def _ticks(self, count: int) -> None:
        """Simulate count scheduler ticks of POLL_CHECK_INTERVAL seconds each."""
        for _ in range(count):
            await self.poller.poll_if_due()
            self.clock.advance(POLL_CHECK_INTERVAL)

    def _assert_next_poll_in(self, cycle_time: int) -> None:
        self.assertEqual(self.clock.now + datetime.timedelta(seconds=cycle_time), self.poller.next_poll_at)

    async def test_first_read_is_immediate(self):
        await self.poller.poll_if_due()
        self.assertEqual(1, self.car.read_cnt)

    async def test_idle_cycle_time(self):
        await self._ticks(60)  # t0 until t0 + 59 min
        self.assertEqual(1, self.car.read_cnt)

        await self.poller.poll_if_due()  # t0 + 60 min
        self.assertEqual(2, self.car.read_cnt)
        self._assert_next_poll_in(self.CYCLE_TIME_IDLE)

    async def test_charging_cycle_time(self):
        self._set_charging(True)
        await self._ticks(15)  # t0 until t0 + 14 min
        self.assertEqual(1, self.car.read_cnt)

        await self.poller.poll_if_due()  # t0 + 15 min
        self.assertEqual(2, self.car.read_cnt)
        self._assert_next_poll_in(self.CYCLE_TIME)

    async def test_read_immediately_on_charging_start(self):
        await self.poller.poll_if_due()  # idle read at t0, next one only at t0 + 60 min
        self.assertEqual(1, self.car.read_cnt)

        self.clock.advance(POLL_CHECK_INTERVAL)
        self._set_charging(True)
        await self.poller.poll_if_due()
        self.assertEqual(2, self.car.read_cnt)
        self._assert_next_poll_in(self.CYCLE_TIME)

    async def test_wallbox_error_is_not_charging(self):
        self.wallbox.inc_error_counter()  # wallbox data is not trusted, as in the charge controller
        self._set_charging(True)
        await self.poller.poll_if_due()
        self.assertEqual(1, self.car.read_cnt)
        self._assert_next_poll_in(self.CYCLE_TIME_IDLE)

    async def test_charging_stop_returns_to_idle_cycle_time(self):
        self._set_charging(True)
        await self._ticks(16)  # reads at t0 and t0 + 15 min
        self.assertEqual(2, self.car.read_cnt)

        self._set_charging(False)
        self.clock.advance(self.CYCLE_TIME - POLL_CHECK_INTERVAL)  # back at the scheduled read time
        await self.poller.poll_if_due()  # read and reschedule on the idle cycle time
        self.assertEqual(3, self.car.read_cnt)
        self._assert_next_poll_in(self.CYCLE_TIME_IDLE)

    async def test_no_read_and_no_error_when_not_due(self):
        await self._ticks(1)  # first read
        await self._ticks(10)
        self.assertEqual(1, self.car.read_cnt)
        self.assertEqual(0, self.car.get_error_counter())  # stale data on purpose is not an error

    async def test_provider_backoff_is_honored(self):
        self.car.backoff_until = self.clock.now + datetime.timedelta(seconds=30 * 60)
        await self._ticks(30)  # t0 until t0 + 29 min
        self.assertEqual(0, self.car.read_cnt)

        self.car.backoff_until = None
        await self.poller.poll_if_due()  # t0 + 30 min, backoff elapsed
        self.assertEqual(1, self.car.read_cnt)


@final
class SimulatedCarTest(unittest.IsolatedAsyncioTestCase):
    @override
    def setUp(self):
        self.car = SimulatedCar(CarConfig())

    async def test_energy_consumption(self):
        c = await self.car.read_data()
        self.assertEqual(50, c.soc)
        self.assertEqual(0, Car._metrics_pvc_car_energy_consumption._value.get())

        # driving
        self.car.set_data(CarData(soc=49))
        c = await self.car.read_data()
        self.assertEqual(49, c.soc)
        self.assertEqual(580, Car._metrics_pvc_car_energy_consumption._value.get())

        self.car.set_data(CarData(soc=40))
        c = await self.car.read_data()
        self.assertEqual(40, c.soc)
        self.assertEqual(5800, Car._metrics_pvc_car_energy_consumption._value.get())

        # not driving
        c = await self.car.read_data()
        self.assertEqual(40, c.soc)
        self.assertEqual(5800, Car._metrics_pvc_car_energy_consumption._value.get())

        # charging
        self.car.set_data(CarData(soc=50))
        c = await self.car.read_data()
        self.assertEqual(50, c.soc)
        self.assertEqual(5800, Car._metrics_pvc_car_energy_consumption._value.get())

        # driving
        self.car.set_data(CarData(soc=40))
        c = await self.car.read_data()
        self.assertEqual(40, c.soc)
        self.assertEqual(2 * 5800, Car._metrics_pvc_car_energy_consumption._value.get())


@unittest.skipUnless(bool(car_config.get("api_key") and car_config.get("vin")), "needs car_test_config.json with api_key and vin")
@final
class SkodaCarTest(unittest.IsolatedAsyncioTestCase):
    @override
    def setUp(self):
        cfg = SkodaCarConfig(**car_config)
        self.car = SkodaCar(cfg)

    @override
    async def asyncTearDown(self):
        await self.car.disconnect()

    async def test_read_data(self):
        c = await self.car.read_data()
        print(f"car_data={c}")
        self.assertGreater(c.soc, 0)
        self.assertGreater(c.cruising_range, 0)
        self.assertEqual(0, c.error)
        self.assertIsInstance(c.data_captured_at, datetime.datetime)
        self.assertGreater(c.mileage, 0)

    async def test_disabled(self):
        self.car.get_config().disabled = True
        c = await self.car.read_data()
        self.assertEqual(1, c.error)
        self.assertEqual(0, c.soc)


@final
class SkodaCarOfflineTest(unittest.IsolatedAsyncioTestCase):
    """Verifies the mapping of a Skoda Public API response without network access."""

    response: dict[str, Any] = {
        "vehicle": {
            "vin": "TMBNH9NY5SF074743",
            "odometer": {"mileageInKm": 5395, "carCapturedTimestamp": "2026-06-29T08:00:00Z"},
            "charging": {
                "isVehicleInSavedLocation": False,
                "carCapturedTimestamp": "2026-06-29T08:00:00Z",
                "status": {"battery": {"remainingCruisingRangeInMeters": 60000, "stateOfChargeInPercent": 20}},
            },
        },
        "errors": [],
    }

    @override
    def setUp(self):
        self.car = SkodaCar(SkodaCarConfig(api_key="test-key", vin="TMBNH9NY5SF074743"))
        self.client = MagicMock()
        self.client.api_key_expires_at = None
        self.client.rate_limit_remaining = 15
        self.client.rate_limit_reset = 900
        self.client.get_vehicle = AsyncMock(return_value=VehicleResponse.model_validate(self.response))
        self.car._client = self.client

    async def test_read_data(self):
        c = await self.car.read_data()
        self.assertEqual(0, c.error)
        self.assertEqual(20, c.soc)
        self.assertEqual(60, c.cruising_range)
        self.assertEqual(5395, c.mileage)
        self.assertEqual(datetime.datetime(2026, 6, 29, 8, 0, tzinfo=datetime.UTC), c.data_captured_at)
        self.client.get_vehicle.assert_awaited_once_with("TMBNH9NY5SF074743", include=["charging", "odometer"])

    async def test_no_data(self):
        self.client.get_vehicle = AsyncMock(return_value=VehicleResponse.model_validate({"vehicle": {"vin": "TMBNH9NY5SF074743"}}))
        c = await self.car.read_data()
        self.assertGreaterEqual(c.error, 1)

    async def test_expired_api_key(self):
        self.client.get_vehicle = AsyncMock(side_effect=OpenApiAuthenticationError())
        c = await self.car.read_data()
        self.assertGreaterEqual(c.error, 1)

    async def test_earliest_request_at(self):
        """CarPoller asks for this to keep away from rate limit backoffs."""
        self.assertIsNone(self.car.earliest_request_at())

        self.client.rate_limit_remaining = 0
        self.client.rate_limit_reset = 1500
        await self.car.read_data()
        self.assertEqual(self.car._next_request_at, self.car.earliest_request_at())

    async def test_rate_limit_exhausted_quota(self):
        self.client.rate_limit_remaining = 0
        self.client.rate_limit_reset = 1500
        c = await self.car.read_data()
        self.assertEqual(0, c.error)  # the response itself was fine
        self.assertIsNotNone(self.car._next_request_at)

        c = await self.car.read_data()
        self.assertGreaterEqual(c.error, 1)  # stale data reported as error while waiting for the new window
        self.assertEqual(1, self.client.get_vehicle.await_count)  # second cycle skipped the request

    async def test_rate_limit_backoff(self):
        self.client.rate_limit_remaining = None  # no quota headers
        self.client.get_vehicle = AsyncMock(side_effect=OpenApiRateLimitError())
        c = await self.car.read_data()
        self.assertGreaterEqual(c.error, 1)
        self.assertIsNotNone(self.car._next_request_at)

        c = await self.car.read_data()
        self.assertGreaterEqual(c.error, 2)
        self.assertEqual(1, self.client.get_vehicle.await_count)  # second cycle skipped the request
