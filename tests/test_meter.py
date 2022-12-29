import unittest
import json
import os

from pvcontrol.meter import MeterData, SolarWattMeter, SolarWattMeterConfig


class SolarWattMeterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.meter = SolarWattMeter(SolarWattMeterConfig(location_guid="a7460c34-1f6b-45dc-a909-7341753f9802"))

    def test_json_2_meter_data(self):
        dir = os.path.dirname(os.path.abspath(__file__))
        with open(dir + "/solarwatt-devices.json", "r") as stream:
            solarwatt_json = json.load(stream)
        meter_data = self.meter._json_2_meter_data(solarwatt_json)
        self.assertEqual(MeterData(0, 0, 640, 640, 25272547.582334433, 16948644.65421216, 8323902.928122882), meter_data)
