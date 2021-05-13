import enum
import math
from dataclasses import dataclass
import logging
import prometheus_client

from pvcontrol.service import BaseConfig, BaseData, BaseService
from pvcontrol.meter import Meter, MeterData
from pvcontrol.wallbox import CarStatus, Wallbox, WallboxData, WbError

logger = logging.getLogger(__name__)


@enum.unique
class ChargeMode(str, enum.Enum):
    """
    Charge mode

    OFF, MAX and MANUAL
    Charge controller just switches into this mode but otherwise doesn't interfere.
    Desired mode is adapted if e.g. the current is changed by go-e app or on the box or if charging finished.

    PV_ONLY
    Charge controller tries to use only PV for charging. Grid current is avoided even if this means
    switch of charging.

    PV_ALL
    Charge controller tries to use all available PV for charging. Grid current is used to fill up so that all PV can be used.
    """

    OFF = "OFF"
    PV_ONLY = "PV_ONLY"
    PV_ALL = "PV_ALL"
    MAX = "MAX"  # 1/3x16A
    MANUAL = "MANUAL"  # wallbox may be controlled via app


@enum.unique
class PhaseMode(str, enum.Enum):
    AUTO = "AUTO"  # PV switches between 1 and 3 phases
    CHARGE_1P = "CHARGE_1P"
    CHARGE_3P = "CHARGE_3P"


@dataclass
class ChargeControllerData(BaseData):
    mode: ChargeMode = ChargeMode.OFF
    desired_mode: ChargeMode = ChargeMode.OFF
    phase_mode: PhaseMode = PhaseMode.AUTO


@dataclass
class ChargeControllerConfig(BaseConfig):
    cycle_time: int = 30  # [s] control loop cycle time, used by scheduler
    enable_phase_switching: bool = True  # set to False of phase relay is not in operation
    enable_auto_phase_switching: bool = True  # automatic phase switching depending on available PV
    line_voltage: float = 230  # [V]
    current_rounding_offset: float = 0.1  # [A] offset for max_current rounding
    power_hysteresis: float = 200  # [W] hysteresis for switching on/off and between 1 and 3 phases
    pv_all_min_power: float = 500  # [W] min available power for charging in mode PV_ALL
    pv_allow_charging_delay: int = 120  # [s] min stable allow_charging time before switching on/off (PV modes only)


# metrics - used as annotation -> can't move into class
_metrics_pvc_controller_processing = prometheus_client.Summary(
    "pvcontrol_controller_processing_seconds", "Time spent processing control loop"
)


class ChargeController(BaseService[ChargeControllerConfig, ChargeControllerData]):
    # metrics
    _metrics_pvc_controller_mode = prometheus_client.Enum(
        "pvcontrol_controller_mode", "Charge controller mode", states=list(ChargeMode.__members__.values())
    )
    _metrics_pvc_controller_total_charged_energy = prometheus_client.Counter(
        "pvcontrol_controller_total_charged_energy_wh_total", "Total energy charged into car"
    )
    _metrics_pvc_controller_charged_energy = prometheus_client.Counter(
        "pvcontrol_controller_charged_energy_wh_total", "Energy charged into car by source", ["source"]
    )

    def __init__(self, config: ChargeControllerConfig, meter: Meter, wallbox: Wallbox):
        super().__init__(config)
        self._meter = meter
        self._wallbox = wallbox
        self._set_data(ChargeControllerData())
        self._charge_mode_pv_to_off_delay = 5 * 60  # configurable?
        self._pv_allow_charging_value = False
        self._pv_allow_charging_delay = 0
        self._last_charged_energy = None  # reset on every charging cycle, None = needs initialization on first cycle
        self._last_charged_energy_5m = 0.0  # charged energy in last 5m (cycle when meter energy data is updated)
        self._last_energy_consumption = 0.0  # total counter value, must be initialized first with data from meter
        self._last_energy_consumption_grid = 0.0  # total counter value, must be initialized first with data from meter
        # config
        self._min_supported_current = wallbox.get_config().min_supported_current
        self._max_supported_current = wallbox.get_config().max_supported_current
        min_power_1phase = self._min_supported_current * config.line_voltage
        max_power_1phase = self._max_supported_current * config.line_voltage
        min_power_3phases = 3 * self._min_supported_current * config.line_voltage
        self._pv_only_on = min_power_1phase + config.power_hysteresis
        self._pv_only_off = min_power_1phase
        self._pv_only_1_3_phase_threshold = min_power_3phases + config.power_hysteresis
        self._pv_only_3_1_phase_threshold = min_power_3phases
        self._pv_all_on = config.pv_all_min_power
        self._pv_all_off = max(config.pv_all_min_power - config.power_hysteresis, 100)
        self._pv_all_1_3_phase_threshold = max_power_1phase
        self._pv_all_3_1_phase_threshold = max_power_1phase - config.power_hysteresis
        # init metrics with labels
        ChargeController._metrics_pvc_controller_charged_energy.labels("grid")
        ChargeController._metrics_pvc_controller_charged_energy.labels("pv")

    def set_desired_mode(self, mode: ChargeMode) -> None:
        logger.info(f"set_desired_mode: {self.get_data().desired_mode} -> {mode}")
        self.get_data().desired_mode = mode

    def set_phase_mode(self, mode: PhaseMode) -> None:
        self.get_data().phase_mode = mode

    @_metrics_pvc_controller_processing.time()
    def run(self) -> None:
        """Read charger data from wallbox and calculate set point"""

        # read current state: order is important for simulation
        wb = self._wallbox.read_data()
        m = self._meter.read_data()

        self._meter_charged_energy(m, wb)
        self._control_charge_mode(wb)
        # skip one cycle whe switching phases
        if not self._converge_phases(m, wb):
            self._control_charging(m, wb)

        # metrics
        ChargeController._metrics_pvc_controller_mode.state(self.get_data().mode)

    def _meter_charged_energy(self, m: MeterData, wb: WallboxData):
        """Calculates energy charged into car by source and updates metrics."""
        if self._last_charged_energy is not None:
            energy_inc = wb.charged_energy - self._last_charged_energy
            # charged_energy reset
            if energy_inc < -1.0:
                energy_inc = wb.charged_energy
            ChargeController._metrics_pvc_controller_total_charged_energy.inc(energy_inc)

            # note: energy values are updates every 5 min only
            # assumption: all energy values are incremented at the same time
            if wb.allow_charging:
                consumed_energy_inc = m.energy_consumption - self._last_energy_consumption
                if consumed_energy_inc > 1.0:
                    consumed_energy_grid_inc = m.energy_consumption_grid - self._last_energy_consumption_grid
                    # Any energy consumed from grid while charging car is accounted to "charged from grid",
                    # the remaining part as "charged from PV"
                    charged_energy_5m = wb.charged_energy - self._last_charged_energy_5m
                    if charged_energy_5m < 1.0:
                        charged_energy_5m = wb.charged_energy
                    self._last_charged_energy_5m = wb.charged_energy
                    charged_energy_5m = max(charged_energy_5m, 0.0)
                    charged_from_grid = min(consumed_energy_grid_inc, charged_energy_5m)
                    charged_from_pv = charged_energy_5m - charged_from_grid
                    if charged_from_grid < 0.0 or charged_from_pv < 0.0:
                        logger.error(
                            f"Negative charged energy incr.: charged_from_grid={charged_from_grid}, charged_from_pv={charged_from_pv}"
                        )
                        logger.error(f"  m={m}")
                        logger.error(f"  wb={wb}")
                        logger.error(f"  _last_energy_consumption={self._last_energy_consumption}")
                        logger.error(f"  _last_energy_consumption_grid={self._last_energy_consumption_grid}")
                        logger.error(f"  _last_charged_energy={self._last_charged_energy}")
                        logger.error(f"  _last_charged_energy_5m={self._last_charged_energy_5m}")
                    else:
                        ChargeController._metrics_pvc_controller_charged_energy.labels("grid").inc(charged_from_grid)
                        ChargeController._metrics_pvc_controller_charged_energy.labels("pv").inc(charged_from_pv)
            else:
                self._last_charged_energy_5m = wb.charged_energy
        else:
            self._last_charged_energy_5m = wb.charged_energy

        self._last_energy_consumption = m.energy_consumption
        self._last_energy_consumption_grid = m.energy_consumption_grid
        self._last_charged_energy = wb.charged_energy

    # TODO rename
    def _control_charge_mode(self, wb: WallboxData) -> None:
        # Switch to OFF when car charging finished in PV mode (and it was not the PV control loop that switched off).
        # Needs a delay to avoid OFF when car doesn't switch fast enough from Finished to Charging.
        # Stay in PV mode if control loop switched charging off (alw=0) -> results in CarStatus.ChargingFinished as well
        ctl = self.get_data()
        if (
            (ctl.mode == ChargeMode.PV_ONLY or ctl.mode == ChargeMode.PV_ALL)
            and wb.error == 0
            and wb.car_status == CarStatus.ChargingFinished
            and self._pv_allow_charging_value
        ):
            self._charge_mode_pv_to_off_delay -= self.get_config().cycle_time
            if self._charge_mode_pv_to_off_delay <= 0:
                self.set_desired_mode(ChargeMode.OFF)
        else:
            self._charge_mode_pv_to_off_delay = 5 * 60  # configurable?

        # TODO: enable charging when RFID is recognized
        # !!! RFID sets allow_charging (but a phase switching may be needed)

    # TODO: prevent too fast switching, use energy to grid and time instead of power
    def _converge_phases(self, m: MeterData, wb: WallboxData) -> bool:
        if wb.error == 0 and wb.wb_error == WbError.PHASE:
            # should not happen anymore since reset is triggered by wallbox.set_phases_in()
            # TODO: back-off needed?
            self._wallbox.trigger_reset()
            return True

        config = self.get_config()
        if config.enable_phase_switching:
            available_power = -m.power_grid + wb.power
            desired_phases = self._desired_phases(available_power, wb.phases_in)
            if wb.error == 0 and desired_phases != wb.phases_in:
                # switch phase relay only if charging is off
                if wb.phases_out == 0:
                    self._wallbox.set_phases_in(desired_phases)
                else:
                    # charging off and wait one cylce
                    self._set_allow_charging(False, skip_delay=True)
                return True
            else:
                return False
        else:
            self.set_phase_mode(PhaseMode.CHARGE_1P if wb.phases_in == 1 else PhaseMode.CHARGE_3P)
            return False

    def _desired_phases(self, available_power: float, current_phases: int):
        # TODO 2 phase charging
        mode = self.get_data().desired_mode
        phase_mode = self.get_data().phase_mode

        if phase_mode == PhaseMode.CHARGE_1P:
            return 1
        elif phase_mode == PhaseMode.CHARGE_3P:
            return 3
        else:  # AUTO
            if not self.get_config().enable_auto_phase_switching:
                return current_phases
            elif mode == ChargeMode.PV_ONLY:
                if current_phases == 1:
                    if available_power >= self._pv_only_1_3_phase_threshold:
                        return 3
                    else:
                        return 1
                else:
                    if available_power >= self._pv_only_3_1_phase_threshold:
                        return 3
                    else:
                        return 1
            elif mode == ChargeMode.PV_ALL:
                if current_phases == 1:
                    if available_power >= self._pv_all_1_3_phase_threshold:
                        return 3
                    else:
                        return 1
                else:
                    if available_power >= self._pv_all_3_1_phase_threshold:
                        return 3
                    else:
                        return 1
            elif mode == ChargeMode.MAX:
                return 3
            else:  # OFF, MANUAL
                return current_phases

    def _control_charging(self, m: MeterData, wb: WallboxData) -> None:
        mode = self.get_data().desired_mode
        if mode == ChargeMode.OFF:
            self._set_allow_charging(False, skip_delay=True)
            self.set_desired_mode(ChargeMode.MANUAL)
        elif mode == ChargeMode.MAX:
            self._wallbox.set_max_current(self._max_supported_current)
            self._set_allow_charging(True, skip_delay=True)
            self.set_desired_mode(ChargeMode.MANUAL)
        elif mode == ChargeMode.MANUAL:
            # calc effective (manual) mode for UI
            if not wb.allow_charging:
                mode = ChargeMode.OFF
            elif wb.max_current == self._max_supported_current:
                mode = ChargeMode.MAX
            self._pv_allow_charging_delay = 0
        else:
            phases = wb.phases_out
            if phases == 0:
                phases = wb.phases_in
            available_power = -m.power_grid + wb.power
            config = self.get_config()

            if mode == ChargeMode.PV_ONLY:
                if not wb.allow_charging and available_power < self._pv_only_on:
                    max_current = 0
                else:
                    max_current = math.floor(available_power / config.line_voltage / phases + config.current_rounding_offset)
                    if max_current < self._min_supported_current:
                        max_current = 0
            elif mode == ChargeMode.PV_ALL:
                if (not wb.allow_charging and available_power < self._pv_all_on) or available_power < self._pv_all_off:
                    max_current = 0
                else:
                    max_current = math.ceil(available_power / config.line_voltage / phases - config.current_rounding_offset)
                    if max_current < self._min_supported_current:
                        max_current = self._min_supported_current
            else:
                # should not happen
                logger.warning(f"Unexpected/unhandled charge mode: {mode}")
                max_current = 0

            # set max_current
            if max_current > self._max_supported_current:
                max_current = self._max_supported_current
            if max_current > 0:
                desired_allow_charging = True
            else:
                max_current = self._min_supported_current
                desired_allow_charging = False
            self._wallbox.set_max_current(max_current)

            # set allow_charging if changed for at least allow_charging_delay
            if wb.allow_charging != desired_allow_charging:
                self._pv_allow_charging_delay -= config.cycle_time
                if self._pv_allow_charging_delay <= 0:
                    self._set_allow_charging(desired_allow_charging)
            else:
                self._pv_allow_charging_delay = config.pv_allow_charging_delay

        self.get_data().mode = mode

    def _set_allow_charging(self, v: bool, skip_delay: bool = False):
        self._pv_allow_charging_value = v  # remember last set allow_charging value set by PV control
        self._pv_allow_charging_delay = self.get_config().pv_allow_charging_delay if not skip_delay else 0
        self._wallbox.allow_charging(v)


class ChargeControllerFactory:
    @classmethod
    def newController(cls, meter: Meter, wb: Wallbox, **kwargs) -> ChargeController:
        return ChargeController(ChargeControllerConfig(**kwargs), meter, wb)
