import unittest
import logging
import datetime
import json
import os
from pvcontrol.car import (
    Car,
    CarConfig,
    CarData,
    SkodaCar,
    SkodaCarConfig,
    SimulatedCar,
)

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
# logging.getLogger("urllib3.connectionpool").setLevel(logging.INFO)

# read config file
car_config_file = f"{os.path.dirname(__file__)}/car_test_config.json"
car_config = {}
if os.path.isfile(car_config_file):
    with open(car_config_file, "r") as f:
        car_config = json.load(f)


class SimulatedCarTest(unittest.IsolatedAsyncioTestCase):
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


@unittest.skipUnless(len(car_config) > 0, "needs car_test_config.json")
class SkodaCarTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        cfg = SkodaCarConfig(**car_config)
        self.car = SkodaCar(cfg)

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
