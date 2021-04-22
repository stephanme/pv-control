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

    def test_data(self):
        self.assertEqual(self.controller._data, self.controller.get_data())
        self.controller.get_data().phase_mode = PhaseMode.CHARGE_1P
        self.assertEqual(self.controller._data, self.controller.get_data())
        self.controller.inc_error_counter()
        self.assertEqual(self.controller._data, self.controller.get_data())
        self.assertEqual(1, self.controller.get_data().error)
        self.assertEqual(1, self.controller._data.error)

    def test_ChargeControllerConfig(self):
        c = json.loads('{"power_hysteresis": 150}')
        cfg = ChargeControllerConfig(**c)
        self.assertEqual(150, cfg.power_hysteresis)
        self.assertEqual(ChargeControllerConfig(power_hysteresis=150), cfg)

    def test_config(self):
        ctl = self.controller
        self.assertEqual(6, ctl._min_supported_current)
        self.assertEqual(16, ctl._max_supported_current)
        hys = ctl.get_config().power_hysteresis
        self.assertEqual(6 * 230 + hys, ctl._pv_only_on)
        self.assertEqual(6 * 230, ctl._pv_only_off)
        self.assertEqual(3 * 6 * 230 + hys, ctl._pv_only_1_3_phase_theshold)
        self.assertEqual(3 * 6 * 230, ctl._pv_only_3_1_phase_theshold)
        self.assertEqual(ctl.get_config().pv_all_min_power, ctl._pv_all_on)
        self.assertEqual(ctl.get_config().pv_all_min_power - hys, ctl._pv_all_off)
        self.assertEqual(16 * 230, ctl._pv_all_1_3_phase_theshold)
        self.assertEqual(16 * 230 - hys, ctl._pv_all_3_1_phase_theshold)

    def test_init(self):
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.OFF, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)
        self.assertEqual(PhaseMode.AUTO, c.phase_mode)
        self.wallbox.set_phases_in(3)
        self.controller.run()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)
        self.assertEqual(PhaseMode.AUTO, c.phase_mode)

    def test_desired_phases_OFF(self):
        ctl = self.controller
        ctl.set_desired_mode(ChargeMode.OFF)
        self.assertEqual(1, ctl._desired_phases(0, 1))
        self.assertEqual(3, ctl._desired_phases(0, 3))
        self.assertEqual(1, ctl._desired_phases(5000, 1))
        self.assertEqual(3, ctl._desired_phases(5000, 3))

    def test_desired_phases_MANUAL(self):
        ctl = self.controller
        ctl.set_desired_mode(ChargeMode.MANUAL)
        self.assertEqual(1, ctl._desired_phases(0, 1))
        self.assertEqual(3, ctl._desired_phases(0, 3))
        self.assertEqual(1, ctl._desired_phases(5000, 1))
        self.assertEqual(3, ctl._desired_phases(5000, 3))

    def test_desired_phases_FULL_POWER(self):
        ctl = self.controller
        ctl.set_desired_mode(ChargeMode.MAX)
        self.assertEqual(3, ctl._desired_phases(0, 1))
        self.assertEqual(3, ctl._desired_phases(0, 3))
        self.assertEqual(3, ctl._desired_phases(5000, 1))
        self.assertEqual(3, ctl._desired_phases(5000, 3))

    def test_desired_phases_PV_ONLY(self):
        ctl = self.controller
        ctl.set_desired_mode(ChargeMode.PV_ONLY)
        p = 3 * 6 * 230
        self.assertEqual(1, ctl._desired_phases(0, 1))
        self.assertEqual(1, ctl._desired_phases(p, 1))
        self.assertEqual(3, ctl._desired_phases(p + 200, 1))
        self.assertEqual(3, ctl._desired_phases(p + 200, 3))
        self.assertEqual(3, ctl._desired_phases(p, 3))
        self.assertEqual(1, ctl._desired_phases(p - 1, 3))

    def test_desired_phases_PV_ALL(self):
        ctl = self.controller
        ctl.set_desired_mode(ChargeMode.PV_ALL)
        p = 16 * 230
        self.assertEqual(1, ctl._desired_phases(0, 1))
        self.assertEqual(1, ctl._desired_phases(p - 1, 1))
        self.assertEqual(3, ctl._desired_phases(p, 1))
        self.assertEqual(3, ctl._desired_phases(p, 3))
        self.assertEqual(3, ctl._desired_phases(p - 200, 3))
        self.assertEqual(1, ctl._desired_phases(p - 201, 3))

    def test_desired_phases_CHARGE_1P(self):
        ctl = self.controller
        ctl.set_phase_mode(PhaseMode.CHARGE_1P)
        for mode in ChargeMode:
            ctl.set_desired_mode(mode)
            self.assertEqual(1, ctl._desired_phases(0, 1))
            self.assertEqual(1, ctl._desired_phases(0, 3))
            self.assertEqual(1, ctl._desired_phases(5000, 1))
            self.assertEqual(1, ctl._desired_phases(5000, 3))

    def test_desired_phases_CHARGE_3P(self):
        ctl = self.controller
        ctl.set_phase_mode(PhaseMode.CHARGE_3P)
        for mode in ChargeMode:
            ctl.set_desired_mode(mode)
            self.assertEqual(3, ctl._desired_phases(0, 1))
            self.assertEqual(3, ctl._desired_phases(0, 3))
            self.assertEqual(3, ctl._desired_phases(5000, 1))
            self.assertEqual(3, ctl._desired_phases(5000, 3))


class ChargeControllerDisabledPhaseSwitchingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.wallbox = SimulatedWallbox(WallboxConfig())
        self.meter = TestMeter(self.wallbox)
        self.controller = ChargeController(ChargeControllerConfig(enable_phase_switching=False), self.meter, self.wallbox)

    def test_3P(self):
        self.controller.run()  # init

        c = self.controller.get_data()
        self.assertEqual(ChargeMode.OFF, c.mode)
        self.assertEqual(PhaseMode.CHARGE_3P, c.phase_mode)
        self.assertEqual(3, self.wallbox.get_data().phases_in)

        self.controller.set_phase_mode(PhaseMode.CHARGE_1P)
        self.controller.run()
        self.assertEqual(PhaseMode.CHARGE_3P, c.phase_mode)
        self.assertEqual(3, self.wallbox.get_data().phases_in)

    def test_1P(self):
        self.wallbox.set_phases_in(1)
        self.controller.run()  # init
        c = self.controller.get_data()

        self.assertEqual(ChargeMode.OFF, c.mode)
        self.assertEqual(PhaseMode.CHARGE_1P, c.phase_mode)
        self.assertEqual(1, self.wallbox.get_data().phases_in)

        self.controller.set_phase_mode(PhaseMode.AUTO)
        self.controller.run()
        self.assertEqual(PhaseMode.CHARGE_1P, c.phase_mode)
        self.assertEqual(1, self.wallbox.get_data().phases_in)


class ChargeControllerManualModeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.wallbox = SimulatedWallbox(WallboxConfig())
        self.meter = TestMeter(self.wallbox)
        self.controller = ChargeController(ChargeControllerConfig(), self.meter, self.wallbox)
        self.controller.run()  # init

    def test_mode_FULL_POWER(self):
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)
        self.assertEqual(PhaseMode.AUTO, c.phase_mode)
        self.assertEqual(3, self.wallbox.get_data().phases_in)

        self.controller.set_desired_mode(ChargeMode.MAX)
        self.controller.run()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.MAX, c.mode)

        self.controller.run()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.MAX, c.mode)
        self.assertEqual(3, self.wallbox.get_data().phases_out)

    def test_mode_MANUAL_OFF(self):
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)
        self.assertEqual(PhaseMode.AUTO, c.phase_mode)
        self.assertEqual(3, self.wallbox.get_data().phases_in)
        self.assertEqual(0, self.wallbox.get_data().phases_out)

        self.wallbox.allow_charging(True)
        self.wallbox.set_max_current(10)
        self.controller.run()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.MANUAL, c.mode)
        self.assertEqual(3, self.wallbox.get_data().phases_out)

        self.controller.set_desired_mode(ChargeMode.OFF)
        self.controller.run()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)

        self.controller.run()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)
        self.assertEqual(0, self.wallbox.get_data().phases_out)

    def test_mode_3P_1P_3P(self):
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)
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
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)
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
        self.assertEqual(ChargeMode.OFF, c.mode)

    def test_mode_1P_3P_while_charging(self):
        self.controller.set_phase_mode(PhaseMode.CHARGE_1P)
        self.controller.run()
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)
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
        self.controller.set_phase_mode(PhaseMode.CHARGE_3P)
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)

        self.controller.set_desired_mode(ChargeMode.PV_ONLY)
        self.assertEqual(ChargeMode.OFF, c.mode)
        self.controller.run()
        self.assertEqual(ChargeMode.PV_ONLY, c.mode)
        self.assertEqual(ChargeMode.PV_ONLY, c.desired_mode)

        self.controller.run()
        self.assertEqual(ChargeMode.PV_ONLY, c.mode)

        self.controller.set_desired_mode(ChargeMode.MANUAL)
        self.controller.run()
        self.assertEqual(ChargeMode.OFF, c.mode)
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)


class ChargeControllerPVTest(unittest.TestCase):
    def setUp(self) -> None:
        self.wallbox = SimulatedWallbox(WallboxConfig())
        self.meter = TestMeter(self.wallbox)
        self.controller = ChargeController(ChargeControllerConfig(pv_allow_charging_delay=0), self.meter, self.wallbox)
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
                "expected_m": MeterData(power_pv=0, power_consumption=0, power_grid=0),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False),
            },
            {
                "test": "1.4kW PV, off",
                "pv": 1400,
                "home": 0,
                "expected_m": MeterData(power_pv=1400, power_consumption=0, power_grid=-1400),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6),
            },
            {
                "test": "3kW PV, 1x13A",
                "pv": 3000,
                "home": 0,
                "expected_m": MeterData(power_pv=3000, power_consumption=2990, power_grid=-3000 + 2990),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=13, power=2990),
            },
            {
                "test": "3kW PV, 1x13A *",
                "pv": 3000,
                "home": 0,
                "expected_m": MeterData(power_pv=3000, power_consumption=2990, power_grid=-3000 + 2990),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=13, power=2990),
            },
            {
                "test": "4kW PV, 1x16A",
                "pv": 4000,
                "home": 0,
                "expected_m": MeterData(power_pv=4000, power_consumption=3680, power_grid=-4000 + 3680),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=16, power=3680),
            },
            {
                "test": "4.3kW PV, 1x16A",
                "pv": 4300,
                "home": 0,
                "expected_m": MeterData(power_pv=4300, power_consumption=3680, power_grid=-4300 + 3680),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=16, power=3680),
            },
            {
                "test": "4.5kW PV, 3x6A",
                "pv": 4500,
                "home": 0,
                "expected_m": MeterData(power_pv=4500, power_consumption=0, power_grid=-4500),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=16, power=0),
            },
            {
                "test": "4.5kW PV, 3x6A *",
                "pv": 4500,
                "home": 0,
                "expected_m": MeterData(power_pv=4500, power_consumption=0, power_grid=-4500),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=16, power=0),
            },
            {
                "test": "4.5kW PV, 3x6A **",
                "pv": 4500,
                "home": 0,
                "expected_m": MeterData(power_pv=4500, power_consumption=4140, power_grid=-4500 + 4140),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=6, power=4140),
            },
            {
                "test": "6kW PV, 3x8A",
                "pv": 6000,
                "home": 0,
                "expected_m": MeterData(power_pv=6000, power_consumption=5520, power_grid=-6000 + 5520),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=8, power=5520),
            },
            {
                "test": "4.3kW PV, 3x6A",
                "pv": 4300,
                "home": 0,
                "expected_m": MeterData(power_pv=4300, power_consumption=4140, power_grid=-4300 + 4140),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=6, power=4140),
            },
            {
                "test": "4kW PV, 1x16A",
                "pv": 4000,
                "home": 0,
                "expected_m": MeterData(power_pv=4000, power_consumption=0, power_grid=-4000),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=6, power=0),
            },
            {
                "test": "4kW PV, 1x16A *",
                "pv": 4000,
                "home": 0,
                "expected_m": MeterData(power_pv=4000, power_consumption=0, power_grid=-4000),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6, power=0),
            },
            {
                "test": "4kW PV, 1x16A *",
                "pv": 4000,
                "home": 0,
                "expected_m": MeterData(power_pv=4000, power_consumption=3680, power_grid=-4000 + 3680),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=16, power=3680),
            },
            {
                "test": "1.4kW PV, 1x6A",
                "pv": 1400,
                "home": 0,
                "expected_m": MeterData(power_pv=1400, power_consumption=1380, power_grid=-1400 + 1380),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=6, power=1380),
            },
            {
                "test": "1kW PV, off",
                "pv": 1000,
                "home": 0,
                "expected_m": MeterData(power_pv=1000, power_consumption=0, power_grid=-1000),
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
                "expected_m": MeterData(power_pv=0, power_consumption=0, power_grid=0),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False),
            },
            {
                "test": "1.4kW PV, off",
                "pv": 1400,
                "home": 0,
                "expected_m": MeterData(power_pv=1400, power_consumption=0, power_grid=-1400),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6),
            },
            {
                "test": "3kW PV, 1x13A",
                "pv": 3000,
                "home": 0,
                "expected_m": MeterData(power_pv=3000, power_consumption=2990, power_grid=-3000 + 2990),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=13, power=2990),
            },
            {
                "test": "3kW PV, 1x13A *",
                "pv": 3000,
                "home": 0,
                "expected_m": MeterData(power_pv=3000, power_consumption=2990, power_grid=-3000 + 2990),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=13, power=2990),
            },
            {
                "test": "4kW PV, 1x16A",
                "pv": 4000,
                "home": 0,
                "expected_m": MeterData(power_pv=4000, power_consumption=3680, power_grid=-4000 + 3680),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=16, power=3680),
            },
            {
                "test": "5kW PV, 1x16A",
                "pv": 5000,
                "home": 0,
                "expected_m": MeterData(power_pv=5000, power_consumption=3680, power_grid=-5000 + 3680),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=16, power=3680),
            },
            {
                "test": "10kW PV, 1x16A",
                "pv": 10000,
                "home": 0,
                "expected_m": MeterData(power_pv=10000, power_consumption=3680, power_grid=-10000 + 3680),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=16, power=3680),
            },
            {
                "test": "1.4kW PV, 1x6A",
                "pv": 1400,
                "home": 0,
                "expected_m": MeterData(power_pv=1400, power_consumption=1380, power_grid=-1400 + 1380),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=6, power=1380),
            },
            {
                "test": "1kW PV, off",
                "pv": 1000,
                "home": 0,
                "expected_m": MeterData(power_pv=1000, power_consumption=0, power_grid=-1000),
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
                "expected_m": MeterData(power_pv=0, power_consumption=0, power_grid=0),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=6),
            },
            {
                "test": "1.4kW PV, off",
                "pv": 1400,
                "home": 0,
                "expected_m": MeterData(power_pv=1400, power_consumption=0, power_grid=-1400),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=6),
            },
            {
                "test": "4.3kW PV, 3x6A",
                "pv": 4300,
                "home": 0,
                "expected_m": MeterData(power_pv=4300, power_consumption=4140, power_grid=-4300 + 4140),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=6, power=4140),
            },
            {
                "test": "6kW PV, 3x8A",
                "pv": 6000,
                "home": 0,
                "expected_m": MeterData(power_pv=6000, power_consumption=5520, power_grid=-6000 + 5520),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=8, power=5520),
            },
            {
                "test": "4.3kW PV, 3x6A",
                "pv": 4300,
                "home": 0,
                "expected_m": MeterData(power_pv=4300, power_consumption=4140, power_grid=-4300 + 4140),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=6, power=4140),
            },
            {
                "test": "4kW PV, off",
                "pv": 4000,
                "home": 0,
                "expected_m": MeterData(power_pv=4000, power_consumption=0, power_grid=-4000),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=6, power=0),
            },
            {
                "test": "1.4kW PV, off",
                "pv": 1400,
                "home": 0,
                "expected_m": MeterData(power_pv=1400, power_consumption=0, power_grid=-1400),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=6, power=0),
            },
            {
                "test": "1kW PV, off",
                "pv": 1000,
                "home": 0,
                "expected_m": MeterData(power_pv=1000, power_consumption=0, power_grid=-1000),
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
                "expected_m": MeterData(power_pv=0, power_consumption=0, power_grid=0),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=6),
            },
            {
                "test": "6kW PV, 3x8A",
                "pv": 6000,
                "home": 0,
                "expected_m": MeterData(power_pv=6000, power_consumption=5520, power_grid=-6000 + 5520),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=8, power=5520),
            },
            {
                "test": "6kW PV, 3x8A",
                "pv": 6000,
                "home": 0,
                "expected_m": MeterData(power_pv=6000, power_consumption=5520, power_grid=-6000 + 5520),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=8, power=5520),
            },
            {
                "test": "6kW PV, 3x8A",
                "pv": 6000,
                "home": 0,
                "car": CarStatus.ChargingFinished,
                "expected_m": MeterData(power_pv=6000, power_consumption=0, power_grid=-6000),
                "expected_wb": WallboxData(
                    car_status=CarStatus.ChargingFinished, phases_in=3, phases_out=0, allow_charging=False, max_current=8, power=0
                ),
            },
        ]
        self.runControllerTest(data)
        self.assertEqual(ChargeMode.MANUAL, self.controller.get_data().desired_mode)
        self.assertEqual(ChargeMode.OFF, self.controller.get_data().mode)

    def test_charge_control_pv_all(self):
        self.controller.set_desired_mode(ChargeMode.PV_ALL)
        data = [
            {
                "test": "Enable Mode, no PV",
                "pv": 0,
                "home": 0,
                "expected_m": MeterData(power_pv=0, power_consumption=0, power_grid=0),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False),
            },
            {
                "test": "0.3kW PV, off",
                "pv": 300,
                "home": 0,
                "expected_m": MeterData(power_pv=300, power_consumption=0, power_grid=-300),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6),
            },
            {
                "test": "3kW PV, 1x13A",
                "pv": 3000,
                "home": 0,
                "expected_m": MeterData(power_pv=3000, power_consumption=2990, power_grid=-3000 + 2990),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=13, power=2990),
            },
            {
                "test": "3kW PV, 1x13A *",
                "pv": 3000,
                "home": 0,
                "expected_m": MeterData(power_pv=3000, power_consumption=2990, power_grid=-3000 + 2990),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=13, power=2990),
            },
            {
                "test": "3.5kW PV, 1x16A",
                "pv": 3500,
                "home": 0,
                "expected_m": MeterData(power_pv=3500, power_consumption=3680, power_grid=-3500 + 3680),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=16, power=3680),
            },
            {
                "test": "4.3kW PV, 3x7A",
                "pv": 4300,
                "home": 0,
                "expected_m": MeterData(power_pv=4300, power_consumption=0, power_grid=-4300),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=16, power=0),
            },
            {
                "test": "4.3kW PV, 3x7A *",
                "pv": 4300,
                "home": 0,
                "expected_m": MeterData(power_pv=4300, power_consumption=0, power_grid=-4300),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=16, power=0),
            },
            {
                "test": "4.3kW PV, 3x7A **",
                "pv": 4300,
                "home": 0,
                "expected_m": MeterData(power_pv=4300, power_consumption=4830, power_grid=-4300 + 4830),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=7, power=4830),
            },
            {
                "test": "4.89kW PV, 3x7A (0.1A rounding offset)",
                "pv": 4890,
                "home": 0,
                "expected_m": MeterData(power_pv=4890, power_consumption=4830, power_grid=-4890 + 4830),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=7, power=4830),
            },
            {
                "test": "6kW PV, 3x9A",
                "pv": 6000,
                "home": 0,
                "expected_m": MeterData(power_pv=6000, power_consumption=6210, power_grid=-6000 + 6210),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=9, power=6210),
            },
            {
                "test": "3.5kW PV, 3x6A",
                "pv": 3500,
                "home": 0,
                "expected_m": MeterData(power_pv=3500, power_consumption=4140, power_grid=-3500 + 4140),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=6, power=4140),
            },
            {
                "test": "3kW PV, 1x13A",
                "pv": 3000,
                "home": 0,
                "expected_m": MeterData(power_pv=3000, power_consumption=0, power_grid=-3000),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=6, power=0),
            },
            {
                "test": "3kW PV, 1x13A *",
                "pv": 3000,
                "home": 0,
                "expected_m": MeterData(power_pv=3000, power_consumption=0, power_grid=-3000),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6, power=0),
            },
            {
                "test": "3kW PV, 1x13A **",
                "pv": 3000,
                "home": 0,
                "expected_m": MeterData(power_pv=3000, power_consumption=2990, power_grid=-3000 + 2990),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=13, power=2990),
            },
            {
                "test": "0.4kW PV, 1x6A",
                "pv": 400,
                "home": 0,
                "expected_m": MeterData(power_pv=400, power_consumption=1380, power_grid=-400 + 1380),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=6, power=1380),
            },
            {
                "test": "0.2kW PV, off",
                "pv": 200,
                "home": 0,
                "expected_m": MeterData(power_pv=200, power_consumption=0, power_grid=-200),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6),
            },
        ]
        self.runControllerTest(data)

    def test_charge_control_pv_all_3P(self):
        self.controller.set_desired_mode(ChargeMode.PV_ALL)
        self.controller.set_phase_mode(PhaseMode.CHARGE_3P)
        data = [
            {
                "test": "Enable Mode, no PV",
                "pv": 0,
                "home": 0,
                "expected_m": MeterData(power_pv=0, power_consumption=0, power_grid=0),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=6),
            },
            {
                "test": "0.3kW PV, off",
                "pv": 300,
                "home": 0,
                "expected_m": MeterData(power_pv=300, power_consumption=0, power_grid=-300),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=6),
            },
            {
                "test": "1kW PV, 3x6A",
                "pv": 1000,
                "home": 0,
                "expected_m": MeterData(power_pv=1000, power_consumption=4140, power_grid=-1000 + 4140),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=6, power=4140),
            },
            {
                "test": "4kW PV, 3x6A",
                "pv": 4000,
                "home": 0,
                "expected_m": MeterData(power_pv=4000, power_consumption=4140, power_grid=-4000 + 4140),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=6, power=4140),
            },
            {
                "test": "4.3kW PV, 3x7A **",
                "pv": 4300,
                "home": 0,
                "expected_m": MeterData(power_pv=4300, power_consumption=4830, power_grid=-4300 + 4830),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=7, power=4830),
            },
            {
                "test": "4.89kW PV, 3x7A (0.1A rounding offset)",
                "pv": 4890,
                "home": 0,
                "expected_m": MeterData(power_pv=4890, power_consumption=4830, power_grid=-4890 + 4830),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=7, power=4830),
            },
            {
                "test": "6kW PV, 3x9A",
                "pv": 6000,
                "home": 0,
                "expected_m": MeterData(power_pv=6000, power_consumption=6210, power_grid=-6000 + 6210),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=9, power=6210),
            },
            {
                "test": "3.5kW PV, 3x6A",
                "pv": 3500,
                "home": 0,
                "expected_m": MeterData(power_pv=3500, power_consumption=4140, power_grid=-3500 + 4140),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=6, power=4140),
            },
            {
                "test": "1kW PV, 3x6A",
                "pv": 1000,
                "home": 0,
                "expected_m": MeterData(power_pv=1000, power_consumption=4140, power_grid=-1000 + 4140),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=6, power=4140),
            },
            {
                "test": "0.2kW PV, off",
                "pv": 200,
                "home": 0,
                "expected_m": MeterData(power_pv=200, power_consumption=0, power_grid=-200),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=6),
            },
        ]
        self.runControllerTest(data)

    def test_charge_control_pv_all_3P_allow_charging_delay(self):
        self.controller.set_desired_mode(ChargeMode.PV_ALL)
        self.controller.set_phase_mode(PhaseMode.CHARGE_3P)
        self.controller.get_config().pv_allow_charging_delay = 60
        data = [
            {
                "test": "Enable Mode, 6kW PV, 3x9A, no allow_charging delay",
                "pv": 6000,
                "home": 0,
                "expected_m": MeterData(power_pv=6000, power_consumption=6210, power_grid=-6000 + 6210),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=9, power=6210),
            },
            {
                "test": "6kW PV, 3x9A",
                "pv": 6000,
                "home": 0,
                "expected_m": MeterData(power_pv=6000, power_consumption=6210, power_grid=-6000 + 6210),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=9, power=6210),
            },
            {
                "test": "0.2kW PV, 3x6A (allow_charging delay)",
                "pv": 200,
                "home": 0,
                "expected_m": MeterData(power_pv=200, power_consumption=4140, power_grid=-200 + 4140),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=6, power=4140),
            },
            {
                "test": "0.2kW PV, off",
                "pv": 200,
                "home": 0,
                "expected_m": MeterData(power_pv=200, power_consumption=0, power_grid=-200),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=6),
            },
            {
                "test": "6kW PV, off (allow_charging delay)",
                "pv": 6000,
                "home": 0,
                "expected_m": MeterData(power_pv=6000, power_consumption=0, power_grid=-6000),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=9),
            },
            {
                "test": "6kW PV, 3x9A",
                "pv": 6000,
                "home": 0,
                "expected_m": MeterData(power_pv=6000, power_consumption=6210, power_grid=-6000 + 6210),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=9, power=6210),
            },
            {
                "test": "0.2kW PV, 3x6A (allow_charging delay)",
                "pv": 200,
                "home": 0,
                "expected_m": MeterData(power_pv=200, power_consumption=4140, power_grid=-200 + 4140),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=6, power=4140),
            },
            {
                "test": "6kW PV, 3x9A",
                "pv": 6000,
                "home": 0,
                "expected_m": MeterData(power_pv=6000, power_consumption=6210, power_grid=-6000 + 6210),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=9, power=6210),
            },
        ]
        self.runControllerTest(data)
