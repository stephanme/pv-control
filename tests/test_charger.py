from pvcontrol.meter import MeterData
from pvcontrol.charger import Charger, ChargerData
import unittest


class ChargerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.charger = Charger(simulation=True)

    @classmethod
    def calcMeterData(cls, pv: float, home: float, c: ChargerData):
        car = c.phases * c.max_current * 230
        return MeterData(pv, home + car, home + car - pv)

    def test_read_charger_and_calc_setpoint(self):
        c = self.charger.get_charger_data()
        self.assertEqual(ChargerData(3, 0, 0), c)
        c = self.charger.read_charger_and_calc_setpoint(ChargerTest.calcMeterData(10000, 1000, c))
        self.assertEqual(ChargerData(3, 0, 13), c)
        c = self.charger.read_charger_and_calc_setpoint(ChargerTest.calcMeterData(10000, 1000, c))
        self.assertEqual(ChargerData(3, 8970, 13), c)

    def test_read_charger_and_calc_setpoint_max16A(self):
        c = self.charger.get_charger_data()
        c = self.charger.read_charger_and_calc_setpoint(ChargerTest.calcMeterData(15000, 0, c))
        self.assertEqual(ChargerData(3, 0, 16), c)
        c = self.charger.read_charger_and_calc_setpoint(ChargerTest.calcMeterData(15000, 0, c))
        self.assertEqual(ChargerData(3, 11040, 16), c)

    def test_read_charger_and_calc_setpoint_min6A(self):
        self.charger.set_phases(1)
        c = self.charger.get_charger_data()
        c = self.charger.read_charger_and_calc_setpoint(ChargerTest.calcMeterData(1400, 0, c))
        self.assertEqual(ChargerData(1, 0, 6), c)
        c = self.charger.read_charger_and_calc_setpoint(ChargerTest.calcMeterData(1400, 0, c))
        self.assertEqual(ChargerData(1, 1380, 6), c)
        c = self.charger.read_charger_and_calc_setpoint(ChargerTest.calcMeterData(1300, 0, c))
        self.assertEqual(ChargerData(1, 1380, 0), c)
        c = self.charger.read_charger_and_calc_setpoint(ChargerTest.calcMeterData(1300, 0, c))
        self.assertEqual(ChargerData(1, 0, 0), c)
        c = self.charger.read_charger_and_calc_setpoint(ChargerTest.calcMeterData(1300, 0, c))
        self.assertEqual(ChargerData(1, 0, 0), c)
