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
    INIT = "INIT"
    MANUAL = "MANUAL"  # wallbox may be controlled via app
    PV_ONLY = "PV_ONLY"
    PV_ALL = "PV_ALL"


@enum.unique
class PhaseMode(str, enum.Enum):
    AUTO = "AUTO"  # PV switches between 1 and 3 phases
    CHARGE_1P = "CHARGE_1P"
    CHARGE_3P = "CHARGE_3P"


@dataclass
class ChargeControllerData(BaseData):
    mode: ChargeMode = ChargeMode.INIT
    desired_mode: ChargeMode = ChargeMode.MANUAL
    phase_mode: PhaseMode = PhaseMode.AUTO


@dataclass
class ChargeControllerConfig(BaseConfig):
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
        self.get_data().desired_mode = mode

    def set_phase_mode(self, mode: PhaseMode) -> None:
        self.get_data().phase_mode = mode

    @metrics_pvc_controller_processing.time()
    def run(self) -> None:
        """ Read charger data from wallbox and calculate set point """

        # read current state: order is important for simulation
        wb = self._wallbox.read_data()
        m = self._meter.read_data()

        self._convergeMode(wb)
        metrics_pvc_controller_mode.state(self.get_data().mode)

        self._charge_control_pv(m, wb)

    def _convergeMode(self, wb: WallboxData) -> None:
        # switch to manual when car charging finished
        # TODO: also for NoVehicle?
        if wb.car_status == CarStatus.ChargingFinished:
            self.set_desired_mode(ChargeMode.MANUAL)

        data = self.get_data()
        mode = data.mode
        desired_mode = data.desired_mode

        if mode != desired_mode:
            if desired_mode == ChargeMode.MANUAL:
                # switch off any running charging
                # TODO: means that in mode MANUAL a restart aborts a running charging (e.g. triggered via app or wallbox)
                # See also shutdown procedure in __main__.py
                self._wallbox.allow_charging(False)
                data.mode = desired_mode
                logger.info(f"mode: {mode} -> {data.mode}")
            elif desired_mode == ChargeMode.PV_ALL or desired_mode == ChargeMode.PV_ONLY:
                # control loop takes over
                data.mode = desired_mode
                logger.info(f"mode: {mode} -> {data.mode}")
            else:
                logger.error(f"Unsupported desired mode: {desired_mode}")

    def _charge_control_pv(self, m: MeterData, wb: WallboxData) -> None:
        config = self.get_config()
        mode = self.get_data().mode
        available_power = -m.power_grid + wb.power
        desired_phases = self._desired_phases(available_power, wb.phases_in)
        if desired_phases != wb.phases_in:
            # switch phase relay only if charging is off
            if wb.phases_out == 0:
                self._wallbox.set_phases_in(desired_phases)
            else:
                # charging off and wait one cylce
                self._wallbox.allow_charging(False)
        elif mode != ChargeMode.MANUAL:
            phases = wb.phases_out
            if phases == 0:
                phases = wb.phases_in

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
                max_current = 0

            if max_current > self._max_supported_current:
                max_current = self._max_supported_current
            if max_current > 0:
                self._wallbox.set_max_current(max_current)
                self._wallbox.allow_charging(True)
            else:
                self._wallbox.allow_charging(False)

    def _desired_phases(self, available_power: float, current_phases: int):
        # TODO 2 phase charging
        mode = self.get_data().mode
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
            else:  # MANUAL
                return current_phases


class ChargeControllerFactory:
    @classmethod
    def newController(cls, meter: Meter, wb: Wallbox, **kwargs) -> ChargeController:
        return ChargeController(ChargeControllerConfig(**kwargs), meter, wb)
