import unittest
import json
from pvcontrol.relay import DisabledPhaseRelay, PhaseRelayConfig, SimulatedPhaseRelay
from pvcontrol.wallbox import CarStatus, SimulatedWallbox, WallboxConfig, WallboxData, WbError
from pvcontrol.meter import TestMeter, MeterData, TestMeterConfig
from pvcontrol.chargecontroller import ChargeController, ChargeControllerConfig, ChargeMode, PhaseMode, Priority


def reset_controller_metrics():
    ChargeController._metrics_pvc_controller_total_charged_energy._value.set(0)
    ChargeController._metrics_pvc_controller_charged_energy.labels("grid")._value.set(0)
    ChargeController._metrics_pvc_controller_charged_energy.labels("pv")._value.set(0)


class ChargeControllerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.relay = SimulatedPhaseRelay(PhaseRelayConfig())
        self.wallbox = SimulatedWallbox(WallboxConfig())
        self.meter = TestMeter(TestMeterConfig(), self.wallbox)
        self.controller = ChargeController(ChargeControllerConfig(), self.meter, self.wallbox, self.relay)
        reset_controller_metrics()

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
        self.assertEqual(3 * 6 * 230 + hys, ctl._pv_only_1_3_phase_threshold)
        self.assertEqual(3 * 6 * 230, ctl._pv_only_3_1_phase_threshold)
        self.assertEqual(ctl.get_config().pv_all_min_power, ctl._pv_all_on)
        self.assertEqual(ctl.get_config().pv_all_min_power - hys, ctl._pv_all_off)
        self.assertEqual(16 * 230, ctl._pv_all_1_3_phase_threshold)
        self.assertEqual(16 * 230 - hys, ctl._pv_all_3_1_phase_threshold)

    async def test_init(self):
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.OFF, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)
        self.assertEqual(PhaseMode.AUTO, c.phase_mode)
        self.assertEqual(Priority.AUTO, c.desired_priority)
        self.assertEqual(Priority.AUTO, c.priority)
        await self.wallbox.set_phases_in(3)
        await self.controller.run()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)
        self.assertEqual(PhaseMode.AUTO, c.phase_mode)
        self.assertEqual(Priority.AUTO, c.desired_priority)
        self.assertEqual(Priority.HOME_BATTERY, c.priority)

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

    def test_desired_phases_MAX(self):
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

    def test_desired_phases_PV_ONLY_disabled_auto_phase_switching(self):
        ctl = self.controller
        ctl.get_config().enable_auto_phase_switching = False
        ctl.set_desired_mode(ChargeMode.PV_ONLY)
        p = 3 * 6 * 230
        self.assertEqual(1, ctl._desired_phases(0, 1))
        self.assertEqual(1, ctl._desired_phases(p, 1))
        self.assertEqual(1, ctl._desired_phases(p + 200, 1))
        self.assertEqual(1, ctl._desired_phases(p + 200, 3))
        self.assertEqual(1, ctl._desired_phases(p, 3))
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

    def test_desired_phases_PV_ALL_disabled_auto_phase_switching(self):
        ctl = self.controller
        ctl.get_config().enable_auto_phase_switching = False
        ctl.set_desired_mode(ChargeMode.PV_ALL)
        p = 16 * 230
        self.assertEqual(1, ctl._desired_phases(0, 1))
        self.assertEqual(1, ctl._desired_phases(p - 1, 1))
        self.assertEqual(1, ctl._desired_phases(p, 1))
        self.assertEqual(1, ctl._desired_phases(p, 3))
        self.assertEqual(1, ctl._desired_phases(p - 200, 3))
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

    def test_priority_AUTO(self):
        ctl = self.controller
        ctl.set_desired_priority(Priority.AUTO)
        self.assertEqual(Priority.HOME_BATTERY, ctl._control_priority(MeterData(soc_battery=49)))
        self.assertEqual(Priority.AUTO, ctl.get_data().desired_priority)
        self.assertEqual(Priority.HOME_BATTERY, ctl.get_data().priority)
        self.assertEqual(Priority.CAR, ctl._control_priority(MeterData(soc_battery=50)))
        self.assertEqual(Priority.AUTO, ctl.get_data().desired_priority)
        self.assertEqual(Priority.CAR, ctl.get_data().priority)

    def test_priority_HOME_BATTERY(self):
        ctl = self.controller
        ctl.set_desired_priority(Priority.HOME_BATTERY)
        self.assertEqual(Priority.HOME_BATTERY, ctl._control_priority(MeterData()))
        self.assertEqual(Priority.HOME_BATTERY, ctl.get_data().desired_priority)
        self.assertEqual(Priority.HOME_BATTERY, ctl.get_data().priority)

    def test_priority_CAR(self):
        ctl = self.controller
        ctl.set_desired_priority(Priority.CAR)
        self.assertEqual(Priority.CAR, ctl._control_priority(MeterData()))
        self.assertEqual(Priority.CAR, ctl.get_data().desired_priority)
        self.assertEqual(Priority.CAR, ctl.get_data().priority)

    def test_meter_charged_energy(self):
        ctl = self.controller
        m = MeterData()
        wb = WallboxData()
        metric_value_total_charged_energy = ChargeController._metrics_pvc_controller_total_charged_energy._value
        metric_value_charged_energy_grid = ChargeController._metrics_pvc_controller_charged_energy.labels("grid")._value
        metric_value_charged_energy_pv = ChargeController._metrics_pvc_controller_charged_energy.labels("pv")._value

        ctl._meter_charged_energy(m, wb)
        self.assertEqual(0, metric_value_total_charged_energy.get())
        self.assertEqual(0, metric_value_charged_energy_grid.get())
        self.assertEqual(0, metric_value_charged_energy_pv.get())

        m.energy_consumption = 1000
        m.energy_consumption_grid = 1000
        ctl._meter_charged_energy(m, wb)
        self.assertEqual(0, metric_value_total_charged_energy.get())
        self.assertEqual(0, metric_value_charged_energy_grid.get())
        self.assertEqual(0, metric_value_charged_energy_pv.get())

        # start charging
        wb.allow_charging = True
        ctl._meter_charged_energy(m, wb)
        self.assertEqual(0, metric_value_total_charged_energy.get())
        self.assertEqual(0, metric_value_charged_energy_grid.get())
        self.assertEqual(0, metric_value_charged_energy_pv.get())

        wb.charged_energy = 100
        ctl._meter_charged_energy(m, wb)
        self.assertEqual(100, metric_value_total_charged_energy.get())
        self.assertEqual(0, metric_value_charged_energy_grid.get())
        self.assertEqual(0, metric_value_charged_energy_pv.get())

        wb.charged_energy = 200
        ctl._meter_charged_energy(m, wb)
        self.assertEqual(200, metric_value_total_charged_energy.get())
        self.assertEqual(0, metric_value_charged_energy_grid.get())
        self.assertEqual(0, metric_value_charged_energy_pv.get())

        # energy tick from meter
        m.energy_consumption += 300
        m.energy_consumption_grid += 100
        wb.charged_energy = 300
        ctl._meter_charged_energy(m, wb)
        self.assertEqual(300, metric_value_total_charged_energy.get())
        self.assertEqual(100, metric_value_charged_energy_grid.get())
        self.assertEqual(200, metric_value_charged_energy_pv.get())

        # Off, grid/pv != charged due to 5min energy resolution
        wb.allow_charging = False
        wb.charged_energy = 400
        ctl._meter_charged_energy(m, wb)
        self.assertEqual(400, metric_value_total_charged_energy.get())
        self.assertEqual(100, metric_value_charged_energy_grid.get())
        self.assertEqual(200, metric_value_charged_energy_pv.get())

        # home consumption but no charging
        m.energy_consumption += 400
        m.energy_consumption_grid += 400
        ctl._meter_charged_energy(m, wb)
        self.assertEqual(400, metric_value_total_charged_energy.get())
        self.assertEqual(100, metric_value_charged_energy_grid.get())
        self.assertEqual(200, metric_value_charged_energy_pv.get())

        # start charging again
        wb.allow_charging = True
        wb.charged_energy = 0
        ctl._meter_charged_energy(m, wb)
        self.assertEqual(400, metric_value_total_charged_energy.get())
        self.assertEqual(100, metric_value_charged_energy_grid.get())
        self.assertEqual(200, metric_value_charged_energy_pv.get())

        wb.charged_energy = 100
        ctl._meter_charged_energy(m, wb)
        self.assertEqual(500, metric_value_total_charged_energy.get())
        self.assertEqual(100, metric_value_charged_energy_grid.get())
        self.assertEqual(200, metric_value_charged_energy_pv.get())

        # charge from PV only
        m.energy_consumption += 300
        wb.charged_energy = 200
        ctl._meter_charged_energy(m, wb)
        self.assertEqual(600, metric_value_total_charged_energy.get())
        self.assertEqual(100, metric_value_charged_energy_grid.get())
        self.assertEqual(400, metric_value_charged_energy_pv.get())

    def test_meter_charged_energy_neg_energy_consumption_grid(self):
        # observed (very low) negative meter.energy_consumption_grid changes (which should not exist)
        ctl = self.controller
        m = MeterData()
        wb = WallboxData()
        metric_value_total_charged_energy = ChargeController._metrics_pvc_controller_total_charged_energy._value
        metric_value_charged_energy_grid = ChargeController._metrics_pvc_controller_charged_energy.labels("grid")._value
        metric_value_charged_energy_pv = ChargeController._metrics_pvc_controller_charged_energy.labels("pv")._value

        m.energy_consumption += 400
        m.energy_consumption_grid += 200
        ctl._meter_charged_energy(m, wb)
        self.assertEqual(0, metric_value_total_charged_energy.get())
        self.assertEqual(0, metric_value_charged_energy_grid.get())
        self.assertEqual(0, metric_value_charged_energy_pv.get())

        wb.allow_charging = True
        ctl._meter_charged_energy(m, wb)
        wb.charged_energy += 100
        m.energy_consumption += 100
        m.energy_consumption_grid -= 1
        ctl._meter_charged_energy(m, wb)
        self.assertEqual(100, metric_value_total_charged_energy.get())
        self.assertEqual(0, metric_value_charged_energy_grid.get())
        self.assertEqual(100, metric_value_charged_energy_pv.get())


class ChargeControllerDisabledPhaseSwitchingTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.relay = DisabledPhaseRelay(PhaseRelayConfig(enable_phase_switching=False))
        self.wallbox = SimulatedWallbox(WallboxConfig())
        self.meter = TestMeter(TestMeterConfig(), self.wallbox)
        self.controller = ChargeController(ChargeControllerConfig(), self.meter, self.wallbox, self.relay)
        reset_controller_metrics()

    async def test_3P(self):
        await self.wallbox.set_phases_in(3)
        await self.controller.run()  # init

        c = self.controller.get_data()
        self.assertEqual(ChargeMode.OFF, c.mode)
        self.assertEqual(PhaseMode.DISABLED, c.phase_mode)
        self.assertEqual(3, self.wallbox.get_data().phases_in)

        self.controller.set_phase_mode(PhaseMode.CHARGE_1P)
        await self.controller.run()
        self.assertEqual(PhaseMode.DISABLED, c.phase_mode)
        self.assertEqual(3, self.wallbox.get_data().phases_in)

    async def test_1P(self):
        await self.controller.run()  # init
        c = self.controller.get_data()

        self.assertEqual(ChargeMode.OFF, c.mode)
        self.assertEqual(PhaseMode.DISABLED, c.phase_mode)
        self.assertEqual(1, self.wallbox.get_data().phases_in)

        self.controller.set_phase_mode(PhaseMode.AUTO)
        await self.controller.run()
        self.assertEqual(PhaseMode.DISABLED, c.phase_mode)
        self.assertEqual(1, self.wallbox.get_data().phases_in)


class ChargeControllerManualModeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.relay = SimulatedPhaseRelay(PhaseRelayConfig())
        self.wallbox = SimulatedWallbox(WallboxConfig())
        self.wallbox.set_car_status(CarStatus.Charging)  # enable simulation by default
        self.meter = TestMeter(TestMeterConfig(), self.wallbox)
        self.controller = ChargeController(ChargeControllerConfig(), self.meter, self.wallbox, self.relay)
        reset_controller_metrics()
        await self.controller.run()  # init

    async def test_mode_FULL_POWER(self):
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)
        self.assertEqual(PhaseMode.AUTO, c.phase_mode)
        self.assertEqual(1, self.wallbox.get_data().phases_in)

        self.controller.set_desired_mode(ChargeMode.MAX)
        # 1 to 3 phase switch
        await self.controller.run()
        self.assertEqual(ChargeMode.MAX, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)

        await self.controller.run()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.MAX, c.mode)

        await self.controller.run()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.MAX, c.mode)
        self.assertEqual(3, self.wallbox.get_data().phases_out)

    async def test_mode_MANUAL_OFF(self):
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)
        self.assertEqual(PhaseMode.AUTO, c.phase_mode)
        self.assertEqual(1, self.wallbox.get_data().phases_in)
        self.assertEqual(0, self.wallbox.get_data().phases_out)

        await self.wallbox.allow_charging(True)
        await self.wallbox.set_max_current(10)
        await self.controller.run()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.MANUAL, c.mode)
        self.assertEqual(1, self.wallbox.get_data().phases_out)

        self.controller.set_desired_mode(ChargeMode.OFF)
        await self.controller.run()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)

        await self.controller.run()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)
        self.assertEqual(0, self.wallbox.get_data().phases_out)

    async def test_mode_1P_3P_1P(self):
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)
        self.assertEqual(PhaseMode.AUTO, c.phase_mode)
        self.assertEqual(1, self.wallbox.get_data().phases_in)

        self.controller.set_phase_mode(PhaseMode.CHARGE_3P)
        await self.controller.run()
        self.assertEqual(3, self.wallbox.get_data().phases_in)

        self.controller.set_phase_mode(PhaseMode.CHARGE_1P)
        await self.controller.run()
        self.assertEqual(1, self.wallbox.get_data().phases_in)

    async def test_mode_1P_3P_while_charging(self):
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)
        self.assertEqual(PhaseMode.AUTO, c.phase_mode)
        wb = self.wallbox.get_data()
        self.assertEqual(1, wb.phases_in)

        await self.wallbox.allow_charging(True)
        self.controller.set_phase_mode(PhaseMode.CHARGE_3P)
        await self.controller.run()
        wb = self.wallbox.get_data()
        self.assertEqual(1, wb.phases_in)
        self.assertFalse(wb.allow_charging)

        await self.controller.run()
        wb = self.wallbox.get_data()
        self.assertEqual(3, wb.phases_in)
        self.assertEqual(0, wb.phases_out)
        self.assertEqual(ChargeMode.OFF, c.mode)

    async def test_mode_3P_1P_while_charging(self):
        self.controller.set_phase_mode(PhaseMode.CHARGE_3P)
        await self.controller.run()
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)
        wb = self.wallbox.get_data()
        self.assertEqual(3, wb.phases_in)

        await self.wallbox.allow_charging(True)
        self.controller.set_phase_mode(PhaseMode.CHARGE_1P)
        await self.controller.run()
        wb = self.wallbox.get_data()
        self.assertEqual(3, wb.phases_in)
        self.assertFalse(wb.allow_charging)

        await self.controller.run()
        wb = self.wallbox.get_data()
        self.assertEqual(1, wb.phases_in)
        self.assertEqual(0, wb.phases_out)

    async def test_mode_1P_PV(self):
        self.controller.set_phase_mode(PhaseMode.CHARGE_1P)
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)

        self.controller.set_desired_mode(ChargeMode.PV_ONLY)
        self.assertEqual(ChargeMode.OFF, c.mode)
        await self.controller.run()
        self.assertEqual(ChargeMode.PV_ONLY, c.mode)
        self.assertEqual(ChargeMode.PV_ONLY, c.desired_mode)

        await self.controller.run()
        self.assertEqual(ChargeMode.PV_ONLY, c.mode)

        self.controller.set_desired_mode(ChargeMode.MANUAL)
        await self.controller.run()
        self.assertEqual(ChargeMode.OFF, c.mode)
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)

    async def test_mode_1P_3P_phase_err(self):
        self.controller.set_phase_mode(PhaseMode.CHARGE_1P)
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)
        self.assertEqual(1, self.wallbox.get_data().phases_in)

        self.controller.set_phase_mode(PhaseMode.CHARGE_3P)
        await self.controller.run()
        self.assertEqual(3, self.wallbox.get_data().phases_in)

        self.wallbox.set_wb_error(WbError.PHASE)
        await self.controller.run()
        self.assertEqual(1, self.wallbox.trigger_reset_cnt)

    async def test_inconsistent_phase_relay_err(self):
        self.controller.set_phase_mode(PhaseMode.CHARGE_1P)
        c = self.controller.get_data()
        self.assertEqual(ChargeMode.MANUAL, c.desired_mode)
        self.assertEqual(ChargeMode.OFF, c.mode)
        self.assertEqual(1, self.wallbox.get_data().phases_in)

        self.wallbox.set_wb_error(WbError.PHASE_RELAY_ERR)
        await self.controller.run()
        self.assertEqual(1, self.wallbox.trigger_reset_cnt)


class ChargeControllerPVTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.relay = SimulatedPhaseRelay(PhaseRelayConfig())
        self.wallbox = SimulatedWallbox(WallboxConfig())
        self.meter = TestMeter(TestMeterConfig(), self.wallbox)
        self.controller = ChargeController(ChargeControllerConfig(pv_allow_charging_delay=0), self.meter, self.wallbox, self.relay)
        reset_controller_metrics()
        await self.controller.run()  # init

    async def run_controller_test(self, data: list[dict]):
        for idx, d in enumerate(data):
            with self.subTest(idx=idx, test=d["test"]):
                self.meter.set_data(d["pv"], d["home"], d.get("soc", -1))
                await self.meter.tick()
                if "car" in d:
                    self.wallbox.set_car_status(d["car"])
                await self.controller.run()
                # re-read meter and wallbox to avoid 1 cycle delay -> makes test data easier
                # order is important: test meter needs wallbox data
                wb = await self.wallbox.read_data()
                self.wallbox.decrement_charge_energy_for_tests()  # TODO: replace by tick()
                m = await self.meter.read_data()
                print(f"Test idx={idx}: Meter: {m}, Wallbox: {wb}")
                expected_m = d["expected_m"]
                # skip checking of energy consumption if not explicitly specified
                if expected_m.energy_consumption == 0:
                    m.energy_consumption = 0
                    m.energy_consumption_grid = 0
                    m.energy_consumption_pv = 0
                expected_wb = d["expected_wb"]
                # skip checking of car_status by setting it to wb value
                expected_wb.car_status = wb.car_status
                # skip checking charged_energy if not explicitly specified
                if expected_wb.charged_energy == 0:
                    wb.charged_energy = 0
                    wb.total_energy = 0
                self.assertEqual(expected_m, m)
                self.assertEqual(expected_wb, wb)

    async def test_charge_control_pv_only_auto(self):
        self.controller.set_desired_mode(ChargeMode.PV_ONLY)
        self.controller.set_phase_mode(PhaseMode.AUTO)
        data = [
            {
                "test": "Enable Mode, no PV",
                "pv": 0,
                "home": 0,
                "expected_m": MeterData(power_pv=0, power_consumption=0, power_grid=0),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6),
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
                "car": CarStatus.Charging,
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
                "car": CarStatus.Charging,
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
                "car": CarStatus.ChargingFinished,
                "expected_m": MeterData(power_pv=1000, power_consumption=0, power_grid=-1000),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6, power=0),
            },
        ]
        await self.run_controller_test(data)

    async def test_charge_control_pv_only_1p(self):
        self.controller.set_desired_mode(ChargeMode.PV_ONLY)
        self.controller.set_phase_mode(PhaseMode.CHARGE_1P)
        data = [
            {
                "test": "Enable Mode, no PV",
                "pv": 0,
                "home": 0,
                "expected_m": MeterData(power_pv=0, power_consumption=0, power_grid=0),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6),
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
                "car": CarStatus.Charging,
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
        await self.run_controller_test(data)

    async def test_charge_control_pv_only_3P(self):
        self.controller.set_desired_mode(ChargeMode.PV_ONLY)
        self.controller.set_phase_mode(PhaseMode.CHARGE_3P)
        data = [
            {
                "test": "Enable Mode, no PV",
                "pv": 0,
                "home": 0,
                "expected_m": MeterData(power_pv=0, power_consumption=0, power_grid=0),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=16),
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
                "car": CarStatus.Charging,
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
        await self.run_controller_test(data)

    async def test_charge_control_pv_only_off_after_novehicle(self):
        self.controller.set_desired_mode(ChargeMode.PV_ONLY)
        self.controller.set_phase_mode(PhaseMode.CHARGE_3P)
        data = [
            {
                "test": "Enable Mode, no PV",
                "pv": 0,
                "home": 0,
                "expected_m": MeterData(power_pv=0, power_consumption=0, power_grid=0),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=16),
            },
            {
                "test": "Enable Mode, no PV",
                "pv": 0,
                "home": 0,
                "expected_m": MeterData(power_pv=0, power_consumption=0, power_grid=0),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=6),
            },
            {
                "test": "6kW PV, 3x8A, NoVehicle",
                "pv": 6000,
                "home": 0,
                "car": CarStatus.NoVehicle,  # reported by car not because PV switched off
                "expected_m": MeterData(power_pv=6000, power_consumption=0, power_grid=-6000),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=8),
            },
            {
                "test": "6kW PV, 3x8A, car connected",
                "pv": 6000,
                "home": 0,
                "car": CarStatus.Charging,  # plugged in
                "expected_m": MeterData(power_pv=6000, power_consumption=5520, power_grid=-6000 + 5520),
                "expected_wb": WallboxData(phases_in=3, phases_out=3, allow_charging=True, max_current=8, power=5520),
            },
            {
                "test": "6kW PV, 3x8A, finished by car",
                "pv": 6000,
                "home": 0,
                "car": CarStatus.ChargingFinished,  # reported by car not because PV switched off
                "expected_m": MeterData(power_pv=6000, power_consumption=0, power_grid=-6000),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=True, max_current=8, power=0),
            },
            {
                "test": "6kW PV, 3x8A, unplugged",
                "pv": 6000,
                "home": 0,
                "car": CarStatus.NoVehicle,  # unplugged car
                "expected_m": MeterData(power_pv=6000, power_consumption=0, power_grid=-6000),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=8, power=0),
            },
        ]
        # 5 min delay until charge mode OFF
        d_finished = data[-1]
        for _ in range(0, 9):  # 10*NoVehicle
            data.append(d_finished)
        await self.run_controller_test(data)
        self.assertEqual(ChargeMode.MANUAL, self.controller.get_data().desired_mode)
        self.assertEqual(ChargeMode.OFF, self.controller.get_data().mode)

    async def test_charge_control_pv_only_when_car_connected(self):
        self.controller.set_desired_mode(ChargeMode.OFF)
        self.controller.set_phase_mode(PhaseMode.CHARGE_1P)
        self.controller.get_config().enable_charging_when_connecting_car = ChargeMode.PV_ONLY
        data = [
            {
                "test": "OFF, 1.4kW PV, no car",
                "pv": 2000,
                "home": 0,
                "expected_m": MeterData(power_pv=2000, power_consumption=0, power_grid=-2000),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=16),
            },
            {
                "test": "OFF, 1.4kW PV, car connected -> PV_ONLY",
                "pv": 2000,
                "home": 0,
                "car": CarStatus.WaitingForVehicle,
                "expected_m": MeterData(power_pv=2000, power_consumption=1840, power_grid=-2000 + 1840),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=8, power=1840),
            },
            {
                "test": "PV_ONLY, 1.4kW PV, 1x6A, charging with PV_ONLY",
                "pv": 2000,
                "home": 0,
                "car": CarStatus.Charging,  # reported by car not because PV switched off
                "expected_m": MeterData(power_pv=2000, power_consumption=1840, power_grid=-2000 + 1840),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=8, power=1840),
            },
        ]
        await self.run_controller_test(data)
        self.assertEqual(ChargeMode.PV_ONLY, self.controller.get_data().desired_mode)
        self.assertEqual(ChargeMode.PV_ONLY, self.controller.get_data().mode)

    async def test_charge_control_pv_all(self):
        self.controller.set_desired_mode(ChargeMode.PV_ALL)
        data = [
            {
                "test": "Enable Mode, no PV",
                "pv": 0,
                "home": 0,
                "expected_m": MeterData(power_pv=0, power_consumption=0, power_grid=0),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6),
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
                "car": CarStatus.Charging,
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
        await self.run_controller_test(data)

    async def test_charge_control_pv_all_3P(self):
        self.controller.set_desired_mode(ChargeMode.PV_ALL)
        self.controller.set_phase_mode(PhaseMode.CHARGE_3P)
        data = [
            {
                "test": "Enable Mode, no PV, phase switching",
                "pv": 0,
                "home": 0,
                "expected_m": MeterData(power_pv=0, power_consumption=0, power_grid=0),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=16),
            },
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
                "car": CarStatus.Charging,
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
                "car": CarStatus.ChargingFinished,
                "expected_m": MeterData(power_pv=200, power_consumption=0, power_grid=-200),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=6),
            },
        ]
        await self.run_controller_test(data)

    async def test_charge_control_pv_all_3P_allow_charging_delay(self):
        self.controller.set_desired_mode(ChargeMode.PV_ALL)
        self.controller.set_phase_mode(PhaseMode.CHARGE_3P)
        self.controller.get_config().pv_allow_charging_delay = 60
        data = [
            {
                "test": "Enable Mode, 6kW PV, 3x9A, phase switching",
                "pv": 6000,
                "home": 0,
                "car": CarStatus.Charging,
                "expected_m": MeterData(power_pv=6000, power_consumption=0, power_grid=-6000),
                "expected_wb": WallboxData(phases_in=3, phases_out=0, allow_charging=False, max_current=16),
            },
            {
                "test": "Enable Mode, 6kW PV, 3x9A, no allow_charging delay",
                "pv": 6000,
                "home": 0,
                "car": CarStatus.Charging,
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
        await self.run_controller_test(data)

    async def test_charge_control_meter_charged_energy(self):
        self.controller.set_desired_mode(ChargeMode.MAX)
        self.controller.set_phase_mode(PhaseMode.CHARGE_3P)
        pmax = 11040
        energy_inc = pmax / 120  # 30s cycle time

        data = [
            {
                "test": "6kW PV, #0, phase switching",
                "pv": 6000,
                "home": 0,
                "car": CarStatus.Charging,
                "expected_m": MeterData(power_pv=6000, power_consumption=0, power_grid=-6000),
                "expected_wb": WallboxData(
                    phases_in=3,
                    phases_out=0,
                    allow_charging=False,
                    max_current=16,
                    power=0,
                ),
            },
            {
                "test": "6kW PV, #1",
                "pv": 6000,
                "home": 0,
                "car": CarStatus.Charging,
                "expected_m": MeterData(power_pv=6000, power_consumption=pmax, power_grid=-6000 + pmax),
                "expected_wb": WallboxData(
                    phases_in=3,
                    phases_out=3,
                    allow_charging=True,
                    max_current=16,
                    power=pmax,
                ),
            },
            {
                "test": "6kW PV, #2",
                "pv": 6000,
                "home": 0,
                "expected_m": MeterData(power_pv=6000, power_consumption=11040, power_grid=-6000 + 11040),
                "expected_wb": WallboxData(
                    phases_in=3,
                    phases_out=3,
                    allow_charging=True,
                    max_current=16,
                    power=11040,
                    charged_energy=1 * energy_inc,
                    total_energy=1 * energy_inc,
                ),
            },
            {
                "test": "6kW PV, #3",
                "pv": 6000,
                "home": 0,
                "expected_m": MeterData(power_pv=6000, power_consumption=11040, power_grid=-6000 + 11040),
                "expected_wb": WallboxData(
                    phases_in=3,
                    phases_out=3,
                    allow_charging=True,
                    max_current=16,
                    power=11040,
                    charged_energy=2 * energy_inc,
                    total_energy=2 * energy_inc,
                ),
            },
            {
                "test": "6kW PV, #4",
                "pv": 6000,
                "home": 0,
                "expected_m": MeterData(power_pv=6000, power_consumption=11040, power_grid=-6000 + 11040),
                "expected_wb": WallboxData(
                    phases_in=3,
                    phases_out=3,
                    allow_charging=True,
                    max_current=16,
                    power=11040,
                    charged_energy=3 * energy_inc,
                    total_energy=3 * energy_inc,
                ),
            },
            {
                "test": "6kW PV, #5",
                "pv": 6000,
                "home": 0,
                "expected_m": MeterData(power_pv=6000, power_consumption=11040, power_grid=-6000 + 11040),
                "expected_wb": WallboxData(
                    phases_in=3,
                    phases_out=3,
                    allow_charging=True,
                    max_current=16,
                    power=11040,
                    charged_energy=4 * energy_inc,
                    total_energy=4 * energy_inc,
                ),
            },
            {
                "test": "6kW PV, #6, meter reports new energy data",
                "pv": 6000,
                "home": 0,
                "expected_m": MeterData(
                    power_pv=6000,
                    power_consumption=11040,
                    power_grid=-6000 + 11040,
                    energy_consumption=11040 * 5 / 120,
                    energy_consumption_grid=(-6000 + 11040) * 5 / 120,
                    energy_consumption_pv=6000 * 5 / 120,
                ),
                "expected_wb": WallboxData(
                    phases_in=3,
                    phases_out=3,
                    allow_charging=True,
                    max_current=16,
                    power=11040,
                    charged_energy=5 * energy_inc,
                    total_energy=5 * energy_inc,
                ),
            },
        ]
        await self.run_controller_test(data)
        total_charged_energy_metric = ChargeController._metrics_pvc_controller_total_charged_energy._value.get()
        charged_energy_grid_metric = ChargeController._metrics_pvc_controller_charged_energy.labels("grid")._value.get()
        charged_energy_pv_metric = ChargeController._metrics_pvc_controller_charged_energy.labels("pv")._value.get()
        self.assertEqual(5 * energy_inc, total_charged_energy_metric)
        self.assertEqual(5 * (-6000 + pmax) / 120, charged_energy_grid_metric)
        self.assertEqual(5 * 6000 / 120, charged_energy_pv_metric)

    async def test_charge_control_pv_only_1p_prio_car(self):
        self.controller.set_desired_mode(ChargeMode.PV_ONLY)
        self.controller.set_phase_mode(PhaseMode.CHARGE_1P)
        self.controller.set_desired_priority(Priority.CAR)
        self.meter.get_config().battery_capacity = 833  # 1kw ~ 1% in 30s
        self.meter.get_config().battery_max = 1000
        # meter simulates battery before charge controller -> expected_m.soc_battery increases when pv increases, wb consumption doesn't count for soc
        # Priority.CAR = power_battery is close to 0
        data = [
            {
                "test": "Enable Mode, no PV",
                "pv": 0,
                "home": 0,
                "expected_m": MeterData(power_pv=0, power_consumption=0, power_grid=0, power_battery=0),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6),
            },
            {
                "test": "1.4kW PV, off",
                "pv": 1400,
                "home": 0,
                "expected_m": MeterData(power_pv=1400, power_consumption=0, power_grid=-400, power_battery=-1000, soc_battery=1),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6),
            },
            {
                "test": "3kW PV, 1x13A",
                "pv": 3000,
                "home": 0,
                "car": CarStatus.Charging,
                "expected_m": MeterData(power_pv=3000, power_consumption=2990, power_grid=0, power_battery=-3000 + 2990, soc_battery=2),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=13, power=2990),
            },
            {
                "test": "2kW PV, 1x8A",
                "pv": 2000,
                "home": 0,
                "expected_m": MeterData(power_pv=2000, power_consumption=1840, power_grid=0, power_battery=-2000 + 1840, soc_battery=1.01),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=8, power=1840),
            },
            {
                "test": "2kW PV, 1x8A *",
                "pv": 2000,
                "home": 0,
                "expected_m": MeterData(power_pv=2000, power_consumption=1840, power_grid=0, power_battery=-2000 + 1840, soc_battery=1.17),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=8, power=1840),
            },
            {
                "test": "3kW PV, 1x13A",
                "pv": 3000,
                "home": 0,
                "expected_m": MeterData(power_pv=3000, power_consumption=2990, power_grid=0, power_battery=-3000 + 2990, soc_battery=2.17),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=13, power=2990),
            },
            {
                "test": "3kW PV, 1x13A *",
                "pv": 3000,
                "home": 0,
                "car": CarStatus.Charging,
                "expected_m": MeterData(power_pv=3000, power_consumption=2990, power_grid=0, power_battery=-3000 + 2990, soc_battery=2.18),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=13, power=2990),
            },
            {
                "test": "4kW PV, 1x16A",
                "pv": 4000,
                "home": 0,
                "expected_m": MeterData(power_pv=4000, power_consumption=3680, power_grid=0, power_battery=-4000 + 3680, soc_battery=3.18),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=16, power=3680),
            },
        ]
        await self.run_controller_test(data)

    async def test_charge_control_pv_only_1p_prio_home_battery(self):
        self.controller.set_desired_mode(ChargeMode.PV_ONLY)
        self.controller.set_phase_mode(PhaseMode.CHARGE_1P)
        self.controller.set_desired_priority(Priority.HOME_BATTERY)
        self.meter.get_config().battery_capacity = 833  # 1kw ~ 1% in 30s
        self.meter.get_config().battery_max = 1000
        # meter simulates battery before charge controller -> expected_m.soc_battery increases when pv increases, wb consumption doesn't count for soc
        # Priority.HOME_BATTERY = charge battery until soc=100
        data = [
            {
                "test": "Enable Mode, no PV",
                "pv": 0,
                "home": 0,
                "expected_m": MeterData(power_pv=0, power_consumption=0, power_grid=0, power_battery=0),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6),
            },
            {
                "test": "1kW PV, -1kW Batt, off",
                "pv": 1000,
                "home": 0,
                "expected_m": MeterData(power_pv=1000, power_consumption=0, power_grid=0, power_battery=-1000, soc_battery=1),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6),
            },
            {
                "test": "2kW PV, -1kW Batt, off",
                "pv": 2000,
                "home": 0,
                "expected_m": MeterData(power_pv=2000, power_consumption=0, power_grid=-1000, power_battery=-1000, soc_battery=2),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6),
            },
            {
                "test": "2.4kW PV, -1kW Batt, off",
                "pv": 2400,
                "home": 0,
                "expected_m": MeterData(power_pv=2400, power_consumption=0, power_grid=-1400, power_battery=-1000, soc_battery=3),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6),
            },
            {
                "test": "3kW PV, -1kW Batt, 1x8A",
                "pv": 3000,
                "home": 0,
                "car": CarStatus.Charging,
                "expected_m": MeterData(
                    power_pv=3000, power_consumption=1840, power_grid=-3000 + 1000 + 1840, power_battery=-1000, soc_battery=4
                ),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=8, power=1840),
            },
            {
                "test": "3kW PV, 0kW Batt, 1x13A",  # battery full
                "pv": 3000,
                "home": 0,
                "soc": 100,
                "expected_m": MeterData(power_pv=3000, power_consumption=2990, power_grid=-3000 + 2990, power_battery=0, soc_battery=100),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=13, power=2990),
            },
        ]
        await self.run_controller_test(data)

    async def test_charge_control_pv_only_1p_prio_auto(self):
        self.controller.set_desired_mode(ChargeMode.PV_ONLY)
        self.controller.set_phase_mode(PhaseMode.CHARGE_1P)
        self.controller.set_desired_priority(Priority.AUTO)
        self.meter.get_config().battery_capacity = 833  # 1kw ~ 1% in 30s
        self.meter.get_config().battery_max = 1000
        # meter simulates battery before charge controller -> expected_m.soc_battery increases when pv increases, wb consumption doesn't count for soc
        # Priority.AUTO = prefer home battery until soc=50, then prefer car
        data = [
            {
                "test": "Enable Mode, no PV",
                "pv": 0,
                "home": 0,
                "expected_m": MeterData(power_pv=0, power_consumption=0, power_grid=0, power_battery=0),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6),
            },
            {
                "test": "1kW PV, -1kW Batt, off",
                "pv": 1000,
                "home": 0,
                "expected_m": MeterData(power_pv=1000, power_consumption=0, power_grid=0, power_battery=-1000, soc_battery=1),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6),
            },
            {
                "test": "2kW PV, -1kW Batt, off",
                "pv": 2000,
                "home": 0,
                "expected_m": MeterData(power_pv=2000, power_consumption=0, power_grid=-1000, power_battery=-1000, soc_battery=2),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6),
            },
            {
                "test": "2.4kW PV, -1kW Batt, off",
                "pv": 2400,
                "home": 0,
                "expected_m": MeterData(power_pv=2400, power_consumption=0, power_grid=-1400, power_battery=-1000, soc_battery=3),
                "expected_wb": WallboxData(phases_in=1, phases_out=0, allow_charging=False, max_current=6),
            },
            {
                "test": "3kW PV, -1kW Batt, 1x8A",
                "pv": 3000,
                "home": 0,
                "car": CarStatus.Charging,
                "expected_m": MeterData(
                    power_pv=3000, power_consumption=1840, power_grid=-3000 + 1000 + 1840, power_battery=-1000, soc_battery=4
                ),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=8, power=1840),
            },
            {
                "test": "3kW PV, -1kW Batt, 1x8A *",
                "pv": 3000,
                "home": 0,
                "soc": 48,
                "expected_m": MeterData(
                    power_pv=3000, power_consumption=1840, power_grid=-3000 + 1000 + 1840, power_battery=-1000, soc_battery=49
                ),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=8, power=1840),
            },
            {
                "test": "3kW PV, 0kW Batt, 1x13A",  # HOME_BATTERY -> CAR
                "pv": 3000,
                "home": 0,
                "expected_m": MeterData(power_pv=3000, power_consumption=2990, power_grid=0, power_battery=-3000 + 2990, soc_battery=50),
                "expected_wb": WallboxData(phases_in=1, phases_out=1, allow_charging=True, max_current=13, power=2990),
            },
        ]
        await self.run_controller_test(data)
