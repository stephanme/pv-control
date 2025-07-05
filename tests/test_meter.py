import unittest
import json
import os

from pvcontrol.meter import (
    MeterData,
    SmaTripowerMeter,
    SmaTripowerMeterConfig,
    SolarWattMeter,
    SolarWattMeterConfig,
    TestMeter,
    TestMeterConfig,
)
from pvcontrol.wallbox import SimulatedWallbox, WallboxConfig

# read config file
sma_tripower_meter_config_file = f"{os.path.dirname(__file__)}/sma_tripower_meter_test_config.json"
sma_tripower_meter_config = {}
if os.path.isfile(sma_tripower_meter_config_file):
    with open(sma_tripower_meter_config_file, "r") as f:
        sma_tripower_meter_config = json.load(f)


class TestMeterNoBatteryTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.wallbox = SimulatedWallbox(WallboxConfig())
        self.meter = TestMeter(TestMeterConfig(battery_max=0, battery_capacity=0), self.wallbox)

    async def asyncTearDown(self):
        await self.meter.close()

    async def test_read_data(self):
        self.assertEqual(MeterData(), await self.meter.read_data())
        self.meter.set_data(pv=0, home=1000)
        await self.meter.tick()
        self.assertEqual(
            MeterData(
                power_pv=0,
                power_consumption=1000,
                power_grid=1000,
                power_battery=0,
                energy_consumption=1000 / 120,
                energy_consumption_grid=1000 / 120,
                energy_consumption_pv=0,
            ),
            await self.meter.read_data(),
        )
        self.meter.set_data(pv=500, home=1000)
        await self.meter.tick()
        self.assertEqual(
            MeterData(
                power_pv=500,
                power_consumption=1000,
                power_grid=500,
                power_battery=0,
                energy_consumption=2000 / 120,
                energy_consumption_grid=1500 / 120,
                energy_consumption_pv=500 / 120,
            ),
            await self.meter.read_data(),
        )
        self.meter.set_data(pv=1000, home=1000)
        await self.meter.tick()
        self.assertEqual(
            MeterData(
                power_pv=1000,
                power_consumption=1000,
                power_grid=0,
                power_battery=0,
                energy_consumption=3000 / 120,
                energy_consumption_grid=1500 / 120,
                energy_consumption_pv=1500 / 120,
            ),
            await self.meter.read_data(),
        )
        self.meter.set_data(pv=2000, home=1000)
        await self.meter.tick()
        for _ in range(2):  # read_data() shall be idempotent
            self.assertEqual(
                MeterData(
                    power_pv=2000,
                    power_consumption=1000,
                    power_grid=-1000,
                    power_battery=0,
                    energy_consumption=4000 / 120,
                    energy_consumption_grid=1500 / 120,
                    energy_consumption_pv=2500 / 120,
                ),
                await self.meter.read_data(),
            )


class TestMeterBatteryTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.wallbox = SimulatedWallbox(WallboxConfig())
        self.meter = TestMeter(TestMeterConfig(battery_max=1000, battery_capacity=5000 / 120), self.wallbox)

    async def asyncTearDown(self):
        await self.meter.close()

    async def test_read_data(self):
        self.assertEqual(MeterData(), await self.meter.read_data())
        # no pv
        self.meter.set_data(pv=0, home=1000)
        await self.meter.tick()
        self.assertEqual(
            MeterData(
                power_pv=0,
                power_consumption=1000,
                power_grid=1000,
                power_battery=0,
                soc_battery=0,
                energy_consumption=1000 / 120,
                energy_consumption_grid=1000 / 120,
                energy_consumption_pv=0,
            ),
            await self.meter.read_data(),
        )
        # pv starts
        self.meter.set_data(pv=1000, home=1000)
        await self.meter.tick()
        self.assertEqual(
            MeterData(
                power_pv=1000,
                power_consumption=1000,
                power_grid=0,
                power_battery=0,
                soc_battery=0,
                energy_consumption=2000 / 120,
                energy_consumption_grid=1000 / 120,
                energy_consumption_pv=1000 / 120,
            ),
            await self.meter.read_data(),
        )
        # charging battery
        self.meter.set_data(pv=2000, home=1000)
        await self.meter.tick()
        self.assertEqual(
            MeterData(
                power_pv=2000,
                power_consumption=1000,
                power_grid=0,
                power_battery=-1000,
                soc_battery=20,
                energy_consumption=3000 / 120,
                energy_consumption_grid=1000 / 120,
                energy_consumption_pv=2000 / 120,
            ),
            await self.meter.read_data(),
        )
        self.meter.set_data(pv=3000, home=1000)
        await self.meter.tick()
        self.assertEqual(
            MeterData(
                power_pv=3000,
                power_consumption=1000,
                power_grid=-1000,
                power_battery=-1000,
                soc_battery=40,
                energy_consumption=4000 / 120,
                energy_consumption_grid=1000 / 120,
                energy_consumption_pv=3000 / 120,
            ),
            await self.meter.read_data(),
        )
        # battery full
        self.meter.set_data(pv=3000, home=1000, soc=80)
        await self.meter.tick()
        self.assertEqual(
            MeterData(
                power_pv=3000,
                power_consumption=1000,
                power_grid=-2000,
                power_battery=0,
                soc_battery=100,
                energy_consumption=5000 / 120,
                energy_consumption_grid=1000 / 120,
                energy_consumption_pv=4000 / 120,
            ),
            await self.meter.read_data(),
        )
        self.meter.set_data(pv=2000, home=1000)
        await self.meter.tick()
        self.assertEqual(
            MeterData(
                power_pv=2000,
                power_consumption=1000,
                power_grid=-1000,
                power_battery=0,
                soc_battery=100,
                energy_consumption=6000 / 120,
                energy_consumption_grid=1000 / 120,
                energy_consumption_pv=5000 / 120,
            ),
            await self.meter.read_data(),
        )
        self.meter.set_data(pv=1000, home=1000)
        await self.meter.tick()
        self.assertEqual(
            MeterData(
                power_pv=1000,
                power_consumption=1000,
                power_grid=0,
                power_battery=0,
                soc_battery=100,
                energy_consumption=7000 / 120,
                energy_consumption_grid=1000 / 120,
                energy_consumption_pv=6000 / 120,
            ),
            await self.meter.read_data(),
        )
        # no pv, battery discharges
        self.meter.set_data(pv=0, home=1000)
        await self.meter.tick()
        self.assertEqual(
            MeterData(
                power_pv=0,
                power_consumption=1000,
                power_grid=0,
                power_battery=1000,
                soc_battery=80,
                energy_consumption=8000 / 120,
                energy_consumption_grid=1000 / 120,
                energy_consumption_pv=7000 / 120,
            ),
            await self.meter.read_data(),
        )
        self.meter.set_data(pv=0, home=2000)
        await self.meter.tick()
        self.assertEqual(
            MeterData(
                power_pv=0,
                power_consumption=2000,
                power_grid=1000,
                power_battery=1000,
                soc_battery=60,
                energy_consumption=10000 / 120,
                energy_consumption_grid=2000 / 120,
                energy_consumption_pv=8000 / 120,
            ),
            await self.meter.read_data(),
        )
        # battery empty
        self.meter.set_data(pv=0, home=2000, soc=20)
        await self.meter.tick()
        self.assertEqual(
            MeterData(
                power_pv=0,
                power_consumption=2000,
                power_grid=2000,
                power_battery=0,
                soc_battery=0,
                energy_consumption=12000 / 120,
                energy_consumption_grid=3000 / 120,
                energy_consumption_pv=9000 / 120,
            ),
            await self.meter.read_data(),
        )
        self.meter.set_data(pv=0, home=2000)
        await self.meter.tick()
        for _ in range(2):  # read_data() shall be idempotent
            self.assertEqual(
                MeterData(
                    power_pv=0,
                    power_consumption=2000,
                    power_grid=2000,
                    power_battery=0,
                    soc_battery=0,
                    energy_consumption=14000 / 120,
                    energy_consumption_grid=5000 / 120,
                    energy_consumption_pv=9000 / 120,
                ),
                await self.meter.read_data(),
            )


class SolarWattMeterTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.meter = SolarWattMeter(SolarWattMeterConfig(location_guid="a7460c34-1f6b-45dc-a909-7341753f9802"))

    async def asyncTearDown(self):
        await self.meter.close()

    async def test_json_2_meter_data(self):
        dir = os.path.dirname(os.path.abspath(__file__))
        with open(dir + "/solarwatt-devices.json", "r") as stream:
            solarwatt_json = json.load(stream)
        meter_data = self.meter._json_2_meter_data(solarwatt_json)
        self.assertEqual(MeterData(0, 0, 640, 640, 0, 0, 25272547.582334433, 16948644.65421216, 8323902.928122882), meter_data)


@unittest.skip("needs access to SMA Tripower Inverter")
@unittest.skipUnless(len(sma_tripower_meter_config) > 0, "needs sma_tripower_meter_config.json")
class SmaTripowerMeterTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.meter = SmaTripowerMeter(SmaTripowerMeterConfig(**sma_tripower_meter_config))

    async def asyncTearDown(self):
        await self.meter.close()

    async def test_read_data(self):
        data = await self.meter.read_data()
        print(data)
        self.assertEqual(0, data.error)
        # second request should not read sensor metadata again -> check logs
        data = await self.meter.read_data()
        print(data)
        self.assertEqual(0, data.error)
