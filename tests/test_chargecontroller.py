import unittest
import json
from pvcontrol.wallbox import CarStatus, SimulatedWallbox, WallboxConfig, WallboxData
from pvcontrol.meter import TestMeter, MeterData
from pvcontrol.chargecontroller import ChargeController, ChargeControllerConfig, ChargeMode, PhaseMode


class ChargeControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.wallbox = SimulatedWallbox(WallboxConfig())
        self.meter = TestMeter(self.wallbox)
        self.controller = ChargeController(ChargeControllerConfig(), self.meter, self.wallbox)

    def test_ChargeControllerConfig(self):
        c = json.loads('{"power_hysteresis": 150}')
        cfg = ChargeControllerConfig(**c)
        self.assertEqual(150, cfg.power_hysteresis)
        self.assertEqual(ChargeControllerConfig(power_hysteresis=150), cfg)

    def test_config(self):
        ctl = self.controller
        self.assertEqual(6, ctl._min_supported_current)
        self.assertEqual(16, ctl._max_supported_current)
        hys = ctl._config.power_hysteresis
        self.assertEqual(6 * 230 + hys, ctl._pv_only_on)
        self.assertEqual(6 * 230, ctl._pv_only_off)
        self.assertEqual(3 * 6 * 230 + hys, ctl._pv_only_1_3_phase_theshold)
        self.assertEqual(3 * 6 * 230, ctl._pv_only_3_1_phase_theshold)
        self.assertEqual(ctl._config.pv_all_min_power, ctl._pv_all_on)
        self.assertEqual(ctl._config.pv_all_min_power - hys, ctl._pv_all_off)
        self.assertEqual(16 * 230, ctl._pv_all_1_3_phase_theshold)
        self.assertEqual(16 * 230 - hys, ctl._pv_all_3_1_phase_theshold)

    def test_init(self):
        self.wallbox.set_phases_in(3)
        self.controller.run()
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.MANUAL, c.mode)
        self.assertEqual(PhaseMode.AUTO, c.phase_mode)

    def test_desired_phases_INIT(self):
        ctl = self.controller
        self.assertEqual(1, ctl._desired_phases(0, 1))
        self.assertEqual(3, ctl._desired_phases(0, 3))
        self.assertEqual(1, ctl._desired_phases(5000, 1))
        self.assertEqual(3, ctl._desired_phases(5000, 3))

    def test_desired_phases_MANUAL(self):
        ctl = self.controller
        ctl._data.mode = ChargeMode.MANUAL
        self.assertEqual(1, ctl._desired_phases(0, 1))
        self.assertEqual(3, ctl._desired_phases(0, 3))
        self.assertEqual(1, ctl._desired_phases(5000, 1))
        self.assertEqual(3, ctl._desired_phases(5000, 3))

    def test_desired_phases_PV_ONLY(self):
        ctl = self.controller
        ctl._data.mode = ChargeMode.PV_ONLY
        p = 3 * 6 * 230
        self.assertEqual(1, ctl._desired_phases(0, 1))
        self.assertEqual(1, ctl._desired_phases(p, 1))
        self.assertEqual(3, ctl._desired_phases(p + 200, 1))
        self.assertEqual(3, ctl._desired_phases(p + 200, 3))
        self.assertEqual(3, ctl._desired_phases(p, 3))
        self.assertEqual(1, ctl._desired_phases(p - 1, 3))

    def test_desired_phases_PV_ALL(self):
        ctl = self.controller
        ctl._data.mode = ChargeMode.PV_ALL
        p = 16 * 230
        self.assertEqual(1, ctl._desired_phases(0, 1))
        self.assertEqual(1, ctl._desired_phases(p - 1, 1))
        self.assertEqual(3, ctl._desired_phases(p, 1))
        self.assertEqual(3, ctl._desired_phases(p, 3))
        self.assertEqual(3, ctl._desired_phases(p - 200, 3))
        self.assertEqual(1, ctl._desired_phases(p - 201, 3))

    def test_desired_phases_CHARGE_1P(self):
        ctl = self.controller
        ctl._data.phase_mode = PhaseMode.CHARGE_1P
        for mode in [ChargeMode.MANUAL, ChargeMode.PV_ONLY, ChargeMode.PV_ALL]:
            ctl._data.mode = mode
            self.assertEqual(1, ctl._desired_phases(0, 1))
            self.assertEqual(1, ctl._desired_phases(0, 3))
            self.assertEqual(1, ctl._desired_phases(5000, 1))
            self.assertEqual(1, ctl._desired_phases(5000, 3))

    def test_desired_phases_CHARGE_3P(self):
        ctl = self.controller
        ctl._data.phase_mode = PhaseMode.CHARGE_3P
        for mode in [ChargeMode.MANUAL, ChargeMode.PV_ONLY, ChargeMode.PV_ALL]:
            ctl._data.mode = mode
            self.assertEqual(3, ctl._desired_phases(0, 1))
            self.assertEqual(3, ctl._desired_phases(0, 3))
            self.assertEqual(3, ctl._desired_phases(5000, 1))
            self.assertEqual(3, ctl._desired_phases(5000, 3))


class ChargeControllerManualModeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.wallbox = SimulatedWallbox(WallboxConfig())
        self.meter = TestMeter(self.wallbox)
        self.controller = ChargeController(ChargeControllerConfig(), self.meter, self.wallbox)
        self.controller.run()  # init

    def test_mode_3P_1P_3P(self):
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.MANUAL, c.mode)
        self.assertEqual(PhaseMode.AUTO, c.phase_mode)
        self.assertEqual(3, self.wallbox.get_data().phases_in)

        self.controller.set_phase_mode(PhaseMode.CHARGE_1P)
        self.controller.run()
        self.assertEqual(1, self.wallbox.get_data().phases_in)

        self.controller.set_phase_mode(PhaseMode.CHARGE_3P)
        self.controller.run()
        self.assertEqual(3, self.wallbox.get_data().phases_in)

    def test_mode_3P_1P_while_charging(self):
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.MANUAL, c.mode)
        self.assertEqual(PhaseMode.AUTO, c.phase_mode)
        wb = self.wallbox.get_data()
        self.assertEqual(3, wb.phases_in)

        self.wallbox.allow_charging(True)
        self.controller.set_phase_mode(PhaseMode.CHARGE_1P)
        self.controller.run()
        wb = self.wallbox.get_data()
        self.assertEqual(3, wb.phases_in)
        self.assertFalse(wb.allow_charging)

        self.controller.run()
        wb = self.wallbox.get_data()
        self.assertEqual(1, wb.phases_in)
        self.assertEqual(0, wb.phases_out)

    def test_mode_1P_3P_while_charging(self):
        self.controller.set_phase_mode(PhaseMode.CHARGE_1P)
        self.controller.run()
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.MANUAL, c.mode)
        wb = self.wallbox.get_data()
        self.assertEqual(1, wb.phases_in)

        self.wallbox.allow_charging(True)
        self.controller.set_phase_mode(PhaseMode.CHARGE_3P)
        self.controller.run()
        wb = self.wallbox.get_data()
        self.assertEqual(1, wb.phases_in)
        self.assertFalse(wb.allow_charging)

        self.controller.run()
        wb = self.wallbox.get_data()
        self.assertEqual(3, wb.phases_in)
        self.assertEqual(0, wb.phases_out)

    def test_mode_3P_PV(self):
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.MANUAL, c.mode)

        self.controller.set_desired_mode(ChargeMode.PV_ONLY)
        self.assertEqual(ChargeMode.MANUAL, c.mode)
        self.controller.run()
        self.assertEqual(ChargeMode.PV_ONLY, c.mode)

        self.controller.run()
        self.assertEqual(ChargeMode.PV_ONLY, c.mode)

        self.controller.set_desired_mode(ChargeMode.MANUAL)
        self.controller.run()
        self.assertEqual(ChargeMode.MANUAL, c.mode)


class ChargeControllerPVTest(unittest.TestCase):
    def setUp(self) -> None:
        self.wallbox = SimulatedWallbox(WallboxConfig())
        self.meter = TestMeter(self.wallbox)
        self.controller = ChargeController(ChargeControllerConfig(), self.meter, self.wallbox)
        self.controller.run()  # init

    def runControllerTest(self, data):
        for idx, d in enumerate(data):
            with self.subTest(idx=idx, test=d["test"]):
                self.meter.set_data(d["pv"], d["home"])
                if "car" in d:
                    self.wallbox.set_car_status(d["car"])
                self.controller.run()
                # re-read meter and wallbox to avoid 1 cycle delay -> makes test data easier
                # order is important: simulated meter needs wallbox data
                wb = self.wallbox.read_data()
                m = self.meter.read_data()
                self.assertEqual(d["expected_m"], m)
                self.assertEqual(d["expected_wb"], wb)

    def test_charge_control_pv_only_auto(self):
        self.controller.set_desired_mode(ChargeMode.PV_ONLY)
        self.controller.set_phase_mode(PhaseMode.AUTO)
        data = [
            {
                "test": "Enable Mode, no PV",
                "pv": 0,
                "home": 0,
                "expected_m": MeterData(0, 0, 0),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False),
            },
            {
                "test": "1.4kW PV, off",
                "pv": 1400,
                "home": 0,
                "expected_m": MeterData(1400, 0, -1400),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False),
            },
            {
                "test": "3kW PV, 1x13A",
                "pv": 3000,
                "home": 0,
                "expected_m": MeterData(3000, 2990, -3000 + 2990),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=13, power=2990),
            },
            {
                "test": "3kW PV, 1x13A *",
                "pv": 3000,
                "home": 0,
                "expected_m": MeterData(3000, 2990, -3000 + 2990),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=13, power=2990),
            },
            {
                "test": "4kW PV, 1x16A",
                "pv": 4000,
                "home": 0,
                "expected_m": MeterData(4000, 3680, -4000 + 3680),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=16, power=3680),
            },
            {
                "test": "4.3kW PV, 1x16A",
                "pv": 4300,
                "home": 0,
                "expected_m": MeterData(4300, 3680, -4300 + 3680),
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
            {
                "test": "4.3kW PV, 3x6A",
                "pv": 4300,
                "home": 0,
                "expected_m": MeterData(4300, 4140, -4300 + 4140),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=6, power=4140),
            },
            {
                "test": "4kW PV, 1x16A",
                "pv": 4000,
                "home": 0,
                "expected_m": MeterData(4000, 0, -4000),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=6, power=0),
            },
            {
                "test": "4kW PV, 1x16A *",
                "pv": 4000,
                "home": 0,
                "expected_m": MeterData(4000, 0, -4000),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6, power=0),
            },
            {
                "test": "4kW PV, 1x16A *",
                "pv": 4000,
                "home": 0,
                "expected_m": MeterData(4000, 3680, -4000 + 3680),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=16, power=3680),
            },
            {
                "test": "1.4kW PV, 1x6A",
                "pv": 1400,
                "home": 0,
                "expected_m": MeterData(1400, 1380, -1400 + 1380),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=6, power=1380),
            },
            {
                "test": "1kW PV, off",
                "pv": 1000,
                "home": 0,
                "expected_m": MeterData(1000, 0, -1000),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6, power=0),
            },
        ]
        self.runControllerTest(data)

    def test_charge_control_pv_only_1p(self):
        self.controller.set_desired_mode(ChargeMode.PV_ONLY)
        self.controller.set_phase_mode(PhaseMode.CHARGE_1P)
        data = [
            {
                "test": "Enable Mode, no PV",
                "pv": 0,
                "home": 0,
                "expected_m": MeterData(0, 0, 0),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False),
            },
            {
                "test": "1.4kW PV, off",
                "pv": 1400,
                "home": 0,
                "expected_m": MeterData(1400, 0, -1400),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False),
            },
            {
                "test": "3kW PV, 1x13A",
                "pv": 3000,
                "home": 0,
                "expected_m": MeterData(3000, 2990, -3000 + 2990),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=13, power=2990),
            },
            {
                "test": "3kW PV, 1x13A *",
                "pv": 3000,
                "home": 0,
                "expected_m": MeterData(3000, 2990, -3000 + 2990),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=13, power=2990),
            },
            {
                "test": "4kW PV, 1x16A",
                "pv": 4000,
                "home": 0,
                "expected_m": MeterData(4000, 3680, -4000 + 3680),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=16, power=3680),
            },
            {
                "test": "5kW PV, 1x16A",
                "pv": 5000,
                "home": 0,
                "expected_m": MeterData(5000, 3680, -5000 + 3680),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=16, power=3680),
            },
            {
                "test": "10kW PV, 1x16A",
                "pv": 10000,
                "home": 0,
                "expected_m": MeterData(10000, 3680, -10000 + 3680),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=16, power=3680),
            },
            {
                "test": "1.4kW PV, 1x6A",
                "pv": 1400,
                "home": 0,
                "expected_m": MeterData(1400, 1380, -1400 + 1380),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=6, power=1380),
            },
            {
                "test": "1kW PV, off",
                "pv": 1000,
                "home": 0,
                "expected_m": MeterData(1000, 0, -1000),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6, power=0),
            },
        ]
        self.runControllerTest(data)

    def test_charge_control_pv_only_3P(self):
        self.controller.set_desired_mode(ChargeMode.PV_ONLY)
        self.controller.set_phase_mode(PhaseMode.CHARGE_3P)
        data = [
            {
                "test": "Enable Mode, no PV",
                "pv": 0,
                "home": 0,
                "expected_m": MeterData(0, 0, 0),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False),
            },
            {
                "test": "1.4kW PV, off",
                "pv": 1400,
                "home": 0,
                "expected_m": MeterData(1400, 0, -1400),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False),
            },
            {
                "test": "4.3kW PV, 3x6A",
                "pv": 4300,
                "home": 0,
                "expected_m": MeterData(4300, 4140, -4300 + 4140),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=6, power=4140),
            },
            {
                "test": "6kW PV, 3x8A",
                "pv": 6000,
                "home": 0,
                "expected_m": MeterData(6000, 5520, -6000 + 5520),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=8, power=5520),
            },
            {
                "test": "4.3kW PV, 3x6A",
                "pv": 4300,
                "home": 0,
                "expected_m": MeterData(4300, 4140, -4300 + 4140),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=6, power=4140),
            },
            {
                "test": "4kW PV, off",
                "pv": 4000,
                "home": 0,
                "expected_m": MeterData(4000, 0, -4000),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=6, power=0),
            },
            {
                "test": "1.4kW PV, off",
                "pv": 1400,
                "home": 0,
                "expected_m": MeterData(1400, 0, -1400),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=6, power=0),
            },
            {
                "test": "1kW PV, off",
                "pv": 1000,
                "home": 0,
                "expected_m": MeterData(1000, 0, -1000),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=6, power=0),
            },
        ]
        self.runControllerTest(data)

    def test_charge_control_pv_only_manual_after_finished(self):
        self.controller.set_desired_mode(ChargeMode.PV_ONLY)
        self.controller.set_phase_mode(PhaseMode.CHARGE_3P)
        data = [
            {
                "test": "Enable Mode, no PV",
                "pv": 0,
                "home": 0,
                "expected_m": MeterData(0, 0, 0),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False),
            },
            {
                "test": "6kW PV, 3x8A",
                "pv": 6000,
                "home": 0,
                "expected_m": MeterData(6000, 5520, -6000 + 5520),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=8, power=5520),
            },
            {
                "test": "6kW PV, 3x8A",
                "pv": 6000,
                "home": 0,
                "expected_m": MeterData(6000, 5520, -6000 + 5520),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=8, power=5520),
            },
            {
                "test": "6kW PV, 3x8A",
                "pv": 6000,
                "home": 0,
                "car": CarStatus.ChargingFinished,
                "expected_m": MeterData(6000, 0, -6000),
                "expected_wb": WallboxData(
                    car_status=CarStatus.ChargingFinished, phases_in=3, phases_out=0, allow_charging=False, max_current=8, power=0
                ),
            },
        ]
        self.runControllerTest(data)
        self.assertEqual(ChargeMode.MANUAL, self.controller.get_data().desired_mode)
        self.assertEqual(ChargeMode.MANUAL, self.controller.get_data().mode)

    def test_charge_control_pv_all(self):
        self.controller.set_desired_mode(ChargeMode.PV_ALL)
        data = [
            {
                "test": "Enable Mode, no PV",
                "pv": 0,
                "home": 0,
                "expected_m": MeterData(0, 0, 0),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False),
            },
            {
                "test": "0.3kW PV, off",
                "pv": 300,
                "home": 0,
                "expected_m": MeterData(300, 0, -300),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False),
            },
            {
                "test": "3kW PV, 1x13A",
                "pv": 3000,
                "home": 0,
                "expected_m": MeterData(3000, 2990, -3000 + 2990),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=13, power=2990),
            },
            {
                "test": "3kW PV, 1x13A *",
                "pv": 3000,
                "home": 0,
                "expected_m": MeterData(3000, 2990, -3000 + 2990),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=13, power=2990),
            },
            {
                "test": "3.5kW PV, 1x16A",
                "pv": 3500,
                "home": 0,
                "expected_m": MeterData(3500, 3680, -3500 + 3680),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=16, power=3680),
            },
            {
                "test": "4.3kW PV, 3x7A",
                "pv": 4300,
                "home": 0,
                "expected_m": MeterData(4300, 0, -4300),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=16, power=0),
            },
            {
                "test": "4.3kW PV, 3x7A *",
                "pv": 4300,
                "home": 0,
                "expected_m": MeterData(4300, 0, -4300),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=16, power=0),
            },
            {
                "test": "4.3kW PV, 3x7A **",
                "pv": 4300,
                "home": 0,
                "expected_m": MeterData(4300, 4830, -4300 + 4830),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=7, power=4830),
            },
            {
                "test": "4.89kW PV, 3x7A (0.1A rounding offset)",
                "pv": 4890,
                "home": 0,
                "expected_m": MeterData(4890, 4830, -4890 + 4830),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=7, power=4830),
            },
            {
                "test": "6kW PV, 3x9A",
                "pv": 6000,
                "home": 0,
                "expected_m": MeterData(6000, 6210, -6000 + 6210),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=9, power=6210),
            },
            {
                "test": "3.5kW PV, 3x6A",
                "pv": 3500,
                "home": 0,
                "expected_m": MeterData(3500, 4140, -3500 + 4140),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=6, power=4140),
            },
            {
                "test": "3kW PV, 1x13A",
                "pv": 3000,
                "home": 0,
                "expected_m": MeterData(3000, 0, -3000),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=6, power=0),
            },
            {
                "test": "3kW PV, 1x13A *",
                "pv": 3000,
                "home": 0,
                "expected_m": MeterData(3000, 0, -3000),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6, power=0),
            },
            {
                "test": "3kW PV, 1x13A **",
                "pv": 3000,
                "home": 0,
                "expected_m": MeterData(3000, 2990, -3000 + 2990),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=13, power=2990),
            },
            {
                "test": "0.4kW PV, 1x6A",
                "pv": 400,
                "home": 0,
                "expected_m": MeterData(400, 1380, -400 + 1380),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=6, power=1380),
            },
            {
                "test": "0.2kW PV, off",
                "pv": 200,
                "home": 0,
                "expected_m": MeterData(200, 0, -200),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6),
            },
        ]
        self.runControllerTest(data)
