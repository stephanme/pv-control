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
    Car,
    CarConfig,
    CarData,
    SimulatedCar,
    SkodaCar,
    SkodaCarConfig,
)

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
