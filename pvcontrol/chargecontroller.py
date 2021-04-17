import enum
import math
from dataclasses import dataclass
import logging
import prometheus_client

from pvcontrol.service import BaseConfig, BaseData, BaseService
from pvcontrol.meter import Meter, MeterData
from pvcontrol.wallbox import CarStatus, Wallbox, WallboxData

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
    enable_phase_switching: bool = True  # set to False of phase relay is not in operation
    line_voltage: float = 230  # [V]
    current_rounding_offset: float = 0.1  # [A] offset for max_current rounding
    power_hysteresis: float = 200  # [W] hysteresis for switching on/off and between 1 and 3 phases
    pv_all_min_power: float = 500  # [W] min available power for charging in mode PV_ALL


# metrics
metrics_pvc_controller_processing = prometheus_client.Summary(
    "pvcontrol_controller_processing_seconds", "Time spent processing control loop"
)
metrics_pvc_controller_mode = prometheus_client.Enum(
    "pvcontrol_controller_mode", "Charge controller mode", states=list(ChargeMode.__members__.values())
)


class ChargeController(BaseService[ChargeControllerConfig, ChargeControllerData]):
    def __init__(self, config: ChargeControllerConfig, meter: Meter, wallbox: Wallbox):
        super().__init__(config)
        self._meter = meter
        self._wallbox = wallbox
        self._set_data(ChargeControllerData())
        # config
        self._min_supported_current = wallbox.get_config().min_supported_current
        self._max_supported_current = wallbox.get_config().max_supported_current
        self._allow_phase_switching = config.enable_phase_switching
        min_power_1phase = self._min_supported_current * config.line_voltage
        max_power_1phase = self._max_supported_current * config.line_voltage
        min_power_3phases = 3 * self._min_supported_current * config.line_voltage
        self._pv_only_on = min_power_1phase + config.power_hysteresis
        self._pv_only_off = min_power_1phase
        self._pv_only_1_3_phase_theshold = min_power_3phases + config.power_hysteresis
        self._pv_only_3_1_phase_theshold = min_power_3phases
        self._pv_all_on = config.pv_all_min_power
        self._pv_all_off = max(config.pv_all_min_power - config.power_hysteresis, 100)
        self._pv_all_1_3_phase_theshold = max_power_1phase
        self._pv_all_3_1_phase_theshold = max_power_1phase - config.power_hysteresis

    def set_desired_mode(self, mode: ChargeMode) -> None:
        logger.info(f"set_desired_mode: {self.get_data().desired_mode} -> {mode}")
        self.get_data().desired_mode = mode

    def set_phase_mode(self, mode: PhaseMode) -> None:
        self.get_data().phase_mode = mode

    @metrics_pvc_controller_processing.time()
    def run(self) -> None:
        """ Read charger data from wallbox and calculate set point """

        # read current state: order is important for simulation
        wb = self._wallbox.read_data()
        m = self._meter.read_data()

        self._control_charge_mode(wb)
        # skip one cycle whe switching phases
        if not self._converge_phases(m, wb):
            self._control_charging(m, wb)

        # metrics
        metrics_pvc_controller_mode.state(self.get_data().mode)

    # TODO rename
    def _control_charge_mode(self, wb: WallboxData) -> None:
        # switch to OFF when car charging finished
        # TODO: also for NoVehicle?
        if wb.car_status == CarStatus.ChargingFinished:
            self.set_desired_mode(ChargeMode.OFF)
        # TODO: enable charging when RFID is recognized
        # !!! RFID sets allow_charging (but a phase switching may be needed)

    # TODO: prevent too fast switching, use energy to grid and time instead of power
    def _converge_phases(self, m: MeterData, wb: WallboxData) -> bool:
        if self._allow_phase_switching:
            available_power = -m.power_grid + wb.power
            desired_phases = self._desired_phases(available_power, wb.phases_in)
            if desired_phases != wb.phases_in:
                # switch phase relay only if charging is off
                if wb.phases_out == 0:
                    self._wallbox.set_phases_in(desired_phases)
                else:
                    # charging off and wait one cylce
                    self._wallbox.allow_charging(False)
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
            if mode == ChargeMode.PV_ONLY:
                if current_phases == 1:
                    if available_power >= self._pv_only_1_3_phase_theshold:
                        return 3
                    else:
                        return 1
                else:
                    if available_power >= self._pv_only_3_1_phase_theshold:
                        return 3
                    else:
                        return 1
            elif mode == ChargeMode.PV_ALL:
                if current_phases == 1:
                    if available_power >= self._pv_all_1_3_phase_theshold:
                        return 3
                    else:
                        return 1
                else:
                    if available_power >= self._pv_all_3_1_phase_theshold:
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
            self._wallbox.allow_charging(False)
            self.set_desired_mode(ChargeMode.MANUAL)
        elif mode == ChargeMode.MAX:
            self._wallbox.set_max_current(self._max_supported_current)
            self._wallbox.allow_charging(True)
            self.set_desired_mode(ChargeMode.MANUAL)
        elif mode == ChargeMode.MANUAL:
            # calc effective (manual) mode for UI
            if not wb.allow_charging:
                mode = ChargeMode.OFF
            elif wb.max_current == self._max_supported_current:
                mode = ChargeMode.MAX
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

            if max_current > self._max_supported_current:
                max_current = self._max_supported_current
            if max_current > 0:
                self._wallbox.set_max_current(max_current)
                self._wallbox.allow_charging(True)
            else:
                self._wallbox.allow_charging(False)

        self.get_data().mode = mode


class ChargeControllerFactory:
    @classmethod
    def newController(cls, meter: Meter, wb: Wallbox, **kwargs) -> ChargeController:
        return ChargeController(ChargeControllerConfig(**kwargs), meter, wb)
