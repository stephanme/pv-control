import enum
import math
from dataclasses import dataclass
import logging
import prometheus_client

from pvcontrol.meter import Meter, MeterData
from pvcontrol.wallbox import Wallbox, WallboxData

logger = logging.getLogger(__name__)

# metrics
metrics_pvc_processing = prometheus_client.Summary("pvcontrol_processing_seconds", "Time spent processing control loop")


@enum.unique
class ChargeMode(str, enum.Enum):
    INIT = "INIT"
    OFF_1P = "OFF_1P"  # off = controller is off, wallbox may charge via app
    OFF_3P = "OFF_3P"
    PV_ONLY = "PV_ONLY"
    PV_ALL = "PV_ALL"


@dataclass
class ChargeControllerData:
    mode: ChargeMode = ChargeMode.INIT
    desired_mode: ChargeMode = ChargeMode.OFF_3P


class ChargeController:
    LINE_VOLTAGE = 230
    WB_MIN_CURRENT = 6
    WB_MAX_CURRENT = 16

    def __init__(self, meter: Meter, wallbox: Wallbox):
        self._data = ChargeControllerData()
        self._meter = meter
        self._wallbox = wallbox

    def get_data(self) -> ChargeControllerData:
        """ Get last charge controller data. """
        return self._data

    def set_desired_mode(self, mode: ChargeMode) -> None:
        self._data.desired_mode = mode

    def is_mode_converged(self):
        return self._data.mode == self._data.desired_mode

    @metrics_pvc_processing.time()
    def run(self) -> None:
        """ Read charger data from wallbox and calculate set point """

        # read current state: order is important for simulation
        wb = self._wallbox.read_data()
        m = self._meter.read_data()

        if not self.is_mode_converged():
            self._convergeMode(wb)

        if self._data.mode == ChargeMode.PV_ONLY:
            self._charge_control_pv_only(m, wb)

    def _convergeMode(self, wb: WallboxData) -> None:
        mode = self._data.mode
        desired_mode = self._data.desired_mode

        # initialization
        if mode == ChargeMode.INIT:
            # goto Off with current # of phases
            self._data.mode = ChargeMode.OFF_1P if wb.phases_in == 1 else ChargeMode.OFF_3P
            self._data.desired_mode = self._data.mode
            # safe state = no charging (e.g. on reboot while in PV mode)
            self._wallbox.allow_charging(False)
            return

        if desired_mode == ChargeMode.OFF_3P or desired_mode == ChargeMode.OFF_1P:
            # switch phase relay only if charging is off
            if wb.phases_out == 0:
                self._wallbox.set_phases_in(1 if desired_mode == ChargeMode.OFF_1P else 3)
                self._data.mode = desired_mode
            else:
                # charging off and wait one cylce
                self._wallbox.allow_charging(False)
        elif desired_mode == ChargeMode.PV_ALL or desired_mode == ChargeMode.PV_ONLY:
            # control loop takes over
            self._data.mode = desired_mode
        else:
            logger.error(f"Unsupported desired mode: {desired_mode}")

    def _charge_control_pv_only(self, m: MeterData, wb: WallboxData) -> None:
        available_power = -m.power_grid + wb.power
        desired_phases = ChargeController._desired_phases(available_power, wb.phases_in)
        if desired_phases != wb.phases_in:
            # switch phase relay only if charging is off
            if wb.phases_out == 0:
                self._wallbox.set_phases_in(desired_phases)
            else:
                # charging off and wait one cylce
                self._wallbox.allow_charging(False)
        else:
            phases = wb.phases_out
            if phases == 0:
                phases = wb.phases_in
            max_current = math.floor(available_power / ChargeController.LINE_VOLTAGE / phases)
            if max_current < ChargeController.WB_MIN_CURRENT:
                max_current = 0
            elif max_current > ChargeController.WB_MAX_CURRENT:
                max_current = ChargeController.WB_MAX_CURRENT
            if max_current > 0:
                self._wallbox.set_max_current(max_current)
                self._wallbox.allow_charging(True)
            else:
                self._wallbox.allow_charging(False)

    @classmethod
    def _desired_phases(cls, available_power: float, current_phases: int):
        # TODO use available_power + current phases + hysteresis
        # 3 * 6A * 230V = 4140W
        # 3 * 7A * 230V = 4830W
        if available_power >= 4140:
            return 3
        else:
            return 1
