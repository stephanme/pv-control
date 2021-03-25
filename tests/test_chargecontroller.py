import unittest
from pvcontrol.wallbox import SimulatedWallbox, WallboxData
from pvcontrol.meter import TestMeter, MeterData
from pvcontrol.chargecontroller import ChargeController, ChargeMode


class ChargeControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.wallbox = SimulatedWallbox()
        self.meter = TestMeter(self.wallbox)
        self.controller = ChargeController(self.meter, self.wallbox)

    def test_init_3P(self):
        self.wallbox.set_phases_in(3)
        self.controller.run()
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.OFF_3P, c.desired_mode)
        self.assertEqual(ChargeMode.OFF_3P, c.mode)

    def test_init_1P(self):
        self.wallbox.set_phases_in(1)
        self.controller.run()
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.OFF_1P, c.desired_mode)
        self.assertEqual(ChargeMode.OFF_1P, c.mode)

    def test_desired_phases(self):
        self.assertEqual(1, ChargeController._desired_phases(0, 1))


class ChargeControllerModeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.wallbox = SimulatedWallbox()
        self.meter = TestMeter(self.wallbox)
        self.controller = ChargeController(self.meter, self.wallbox)
        self.controller.run()  # init

    def test_mode_3P_1P_3P(self):
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.OFF_3P, c.mode)

        self.controller.set_desired_mode(ChargeMode.OFF_1P)
        self.assertEqual(ChargeMode.OFF_3P, c.mode)
        self.controller.run()
        self.assertEqual(ChargeMode.OFF_1P, c.mode)

        self.controller.set_desired_mode(ChargeMode.OFF_3P)
        self.assertEqual(ChargeMode.OFF_1P, c.mode)
        self.controller.run()
        self.assertEqual(ChargeMode.OFF_3P, c.mode)

    def test_mode_3P_1P_while_charging(self):
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.OFF_3P, c.mode)

        self.wallbox.allow_charging(True)
        self.controller.set_desired_mode(ChargeMode.OFF_1P)
        self.assertEqual(ChargeMode.OFF_3P, c.mode)
        self.controller.run()
        self.assertEqual(ChargeMode.OFF_3P, c.mode)
        wb = self.wallbox.get_data()
        self.assertFalse(wb.allow_charging)

        self.controller.run()
        wb = self.wallbox.get_data()
        self.assertEqual(0, wb.phases_out)
        self.assertEqual(ChargeMode.OFF_1P, c.mode)

    def test_mode_1P_3P_while_charging(self):
        self.controller.set_desired_mode(ChargeMode.OFF_1P)
        self.controller.run()
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.OFF_1P, c.mode)

        self.wallbox.allow_charging(True)
        self.controller.set_desired_mode(ChargeMode.OFF_3P)
        self.assertEqual(ChargeMode.OFF_1P, c.mode)
        self.controller.run()
        self.assertEqual(ChargeMode.OFF_1P, c.mode)
        wb = self.wallbox.get_data()
        self.assertFalse(wb.allow_charging)

        self.controller.run()
        wb = self.wallbox.get_data()
        self.assertEqual(0, wb.phases_out)
        self.assertEqual(ChargeMode.OFF_3P, c.mode)

    def test_mode_3P_PV(self):
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.OFF_3P, c.mode)

        self.controller.set_desired_mode(ChargeMode.PV_ONLY)
        self.assertEqual(ChargeMode.OFF_3P, c.mode)
        self.controller.run()
        self.assertEqual(ChargeMode.PV_ONLY, c.mode)

        self.controller.run()
        self.assertEqual(ChargeMode.PV_ONLY, c.mode)

        self.controller.set_desired_mode(ChargeMode.OFF_3P)
        self.controller.run()
        self.assertEqual(ChargeMode.OFF_3P, c.mode)


class ChargeControllerPVOnlyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.wallbox = SimulatedWallbox()
        self.meter = TestMeter(self.wallbox)
        self.controller = ChargeController(self.meter, self.wallbox)
        self.controller.run()  # init
        self.controller.set_desired_mode(ChargeMode.PV_ONLY)

    def test_charge_control_pv_only(self):
        data = [
            {
                "test": "Enable Mode, no PV",
                "pv": 0,
                "home": 0,
                "expected_m": MeterData(0, 0, 0),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False),
            },
            {
                "test": "1kW PV",
                "pv": 1000,
                "home": 0,
                "expected_m": MeterData(1000, 0, -1000),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False),
            },
            {
                "test": "3kW PV",
                "pv": 3000,
                "home": 0,
                "expected_m": MeterData(3000, 2990, -3000 + 2990),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=13, power=2990),
            },
            {
                "test": "3kW PV *",
                "pv": 3000,
                "home": 0,
                "expected_m": MeterData(3000, 2990, -3000 + 2990),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=13, power=2990),
            },
            {
                "test": "4kW PV, max 1x16A",
                "pv": 4000,
                "home": 0,
                "expected_m": MeterData(4000, 3680, -4000 + 3680),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=16, power=3680),
            },
            {
                "test": "4.5kW PV, 3x6A",
                "pv": 4500,
                "home": 0,
                "expected_m": MeterData(4500, 0, -4500),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=16, power=0),
            },
            {
                "test": "4.5kW PV, 3x6A *",
                "pv": 4500,
                "home": 0,
                "expected_m": MeterData(4500, 0, -4500),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=16, power=0),
            },
            {
                "test": "4.5kW PV, 3x6A **",
                "pv": 4500,
                "home": 0,
                "expected_m": MeterData(4500, 4140, -4500 + 4140),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=6, power=4140),
            },
            {
                "test": "6kW PV, 3x8A",
                "pv": 6000,
                "home": 0,
                "expected_m": MeterData(6000, 5520, -6000 + 5520),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=8, power=5520),
            },
        ]

        for idx, d in enumerate(data):
            with self.subTest(idx=idx, test=d["test"]):
                self.meter.set_data(d["pv"], d["home"])
                self.controller.run()
                # re-read meter and wallbox to avoid 1 cycle delay -> makes test data easier
                # order is important: simulated meter needs wallbox data
                wb = self.wallbox.read_data()
                m = self.meter.read_data()
                self.assertEqual(d["expected_m"], m)
                self.assertEqual(d["expected_wb"], wb)
