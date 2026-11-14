import datetime
import json
import logging
import os
import unittest
from typing import Any, final, override
from unittest.mock import AsyncMock, MagicMock

from skoda_public_api.api_layer.exceptions import (
    OpenApiAuthenticationError,
    OpenApiRateLimitError,
    OpenApiResponseValidationError,
    OpenApiServerError,
    OpenApiTimeoutError,
)
from skoda_public_api.models.vehicle import VehicleResponse

from pvcontrol.car import (
    POLL_CHECK_INTERVAL,
    Car,
    CarConfig,
    CarData,
    CarPoller,
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

    def _request_count(self, status: str) -> float:
        return SkodaCar._metrics_pvc_car_api_requests.labels(status)._value.get()

    def _key_lifetime(self) -> float:
        return SkodaCar._metrics_pvc_car_api_key_lifetime._value.get()

    async def test_key_lifetime_initial(self):
        """A fresh SkodaCar reports -1 = unknown until the first response reveals the header."""
        SkodaCar(SkodaCarConfig(api_key="test-key", vin="TMBNH9NY5SF074743"))  # the constructor resets the gauge to unknown
        self.assertEqual(-1, self._key_lifetime())

    async def test_key_lifetime_unknown_header(self):
        self.assertIsNone(self.client.api_key_expires_at)
        # seed a positive value, so the test fails if a read with unknown header left the gauge stale instead of resetting it
        SkodaCar._metrics_pvc_car_api_key_lifetime.set(12345)
        await self.car.read_data()
        self.assertEqual(-1, self._key_lifetime())

    async def test_key_lifetime_far_future(self):
        now = datetime.datetime.now(datetime.UTC)
        self.client.api_key_expires_at = (now + datetime.timedelta(days=365)).isoformat()
        await self.car.read_data()
        self.assertGreater(self._key_lifetime(), 300 * 86400)

    async def test_key_lifetime_expired(self):
        now = datetime.datetime.now(datetime.UTC)
        self.client.api_key_expires_at = (now - datetime.timedelta(days=1)).isoformat()
        await self.car.read_data()
        self.assertLess(self._key_lifetime(), 0)

    async def test_key_expiry_metric_updates_after_warning(self):
        """The one-time expiry warning must not keep the gauge from updating on later reads."""
        now = datetime.datetime.now(datetime.UTC)
        self.client.api_key_expires_at = (now + datetime.timedelta(days=3)).isoformat()
        with self.assertLogs("pvcontrol.car", level="WARNING") as logs:
            await self.car.read_data()
        self.assertEqual(1, len([message for message in logs.output if "expires at" in message]))
        self.assertLess(self._key_lifetime(), 7 * 86400)

        self.client.api_key_expires_at = (now + datetime.timedelta(days=300)).isoformat()
        await self.car.read_data()  # no second warning, but the gauge follows the new expiry
        self.assertGreater(self._key_lifetime(), 299 * 86400)

    async def test_api_request_metrics_success(self):
        before = self._request_count("200")
        await self.car.read_data()
        self.assertEqual(before + 1, self._request_count("200"))

    async def test_api_request_metrics_error_codes(self):
        cases: list[tuple[Exception, str]] = [
            (OpenApiAuthenticationError(), "401"),
            (OpenApiRateLimitError(), "429"),
            (OpenApiServerError("server went away", status_code=503), "503"),
            (OpenApiTimeoutError(), "timeout"),
            (OpenApiResponseValidationError("could not parse the response"), "invalid_response"),
            (ConnectionError("no route to host"), "network"),
        ]
        for error, status in cases:
            with self.subTest(error=type(error).__name__, status=status):
                self.car._client = self.client  # error handlers close the client to force reconnects
                self.car._next_request_at = None  # a 429 schedules a rate limit backoff
                self.client.get_vehicle = AsyncMock(side_effect=error)
                before = self._request_count(status)
                await self.car.read_data()
                self.assertEqual(before + 1, self._request_count(status))

    async def test_api_request_metrics_skip_backoff(self):
        """Reads skipped during a rate limit backoff never hit the network and are not counted."""
        self.client.rate_limit_remaining = 0
        self.client.rate_limit_reset = 1500
        before_200 = self._request_count("200")
        before_timeout = self._request_count("timeout")
        await self.car.read_data()  # real request, quota now exhausted
        await self.car.read_data()  # skipped because of the backoff
        self.assertEqual(1, self.client.get_vehicle.await_count)
        self.assertEqual(before_200 + 1, self._request_count("200"))
        self.assertEqual(before_timeout, self._request_count("timeout"))

    async def test_api_request_metrics_not_counted_when_not_requested(self):
        """Disabled config and missing credentials must not count any request."""
        self.car.get_config().disabled = True
        before = self._request_count("200")
        await self.car.read_data()
        self.assertEqual(before, self._request_count("200"))

        car = SkodaCar(SkodaCarConfig(api_key="", vin=""))
        try:
            await car.read_data()
        finally:
            await car.close()
        self.assertEqual(before, self._request_count("200"))
