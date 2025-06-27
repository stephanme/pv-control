import unittest
import json
import os

from pvcontrol.meter import MeterData, SmaTripowerMeter, SmaTripowerMeterConfig, SolarWattMeter, SolarWattMeterConfig

# read config file
sma_tripower_meter_config_file = f"{os.path.dirname(__file__)}/sma_tripower_meter_test_config.json"
sma_tripower_meter_config = {}
if os.path.isfile(sma_tripower_meter_config_file):
    with open(sma_tripower_meter_config_file, "r") as f:
        sma_tripower_meter_config = json.load(f)


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
