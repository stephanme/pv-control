import enum
import math
from dataclasses import dataclass
import logging
import prometheus_client

from pvcontrol.relay import PhaseRelay
from pvcontrol.service import BaseConfig, BaseData, BaseService
from pvcontrol.meter import Meter, MeterData
from pvcontrol.wallbox import CarStatus, Wallbox, WallboxData, WbError

logger = logging.getLogger(__name__)


@enum.unique
class ChargeMode(str, enum.Enum):
    """
    Charge Controller operation mode:

    - **OFF**: Indicates that charging is switched off and charge controller is passive.
      When set, charge controller switches charging off and then doesn't interfere/control anymore.
    - **MAX**: Indicates that charging runs on max power (1x or 3x max current) and charge controller is passive.
      When set, charge controller switches charging on to max power and then doesn't interfere/control anymore.
    - **MANUAL**: Indicates that charging is switched on and charge controller is passive. Charging power is controlled externally, e.g. by wallbox app.
      When set, charge controller stops controlling charging power, last wallbox power setting is kept.
    - **PV_ONLY**: Charge controller tries to use only PV for charging. Grid power is avoided even if this means switching off charging.
    - **PV_ALL**: Charge controller tries to use all available PV for charging. Grid power is used to fill up so that all PV can be used.
    """

    OFF = "OFF"
    PV_ONLY = "PV_ONLY"
    PV_ALL = "PV_ALL"
    MAX = "MAX"  # 1/3x16A
    MANUAL = "MANUAL"  # wallbox may be controlled via app


@enum.unique
class PhaseMode(str, enum.Enum):
    DISABLED = "DISABLED"  # phase relay is not in operation
    AUTO = "AUTO"  # PV switches between 1 and 3 phases
    CHARGE_1P = "CHARGE_1P"
    CHARGE_3P = "CHARGE_3P"


@enum.unique
class Priority(str, enum.Enum):
    AUTO = "AUTO"  # balance between home battery and car
    HOME_BATTERY = "HOME_BATTERY"  # load home battery before car
    CAR = "CAR"  # load car before home battery


@dataclass
class ChargeControllerData(BaseData):
    """
    Charge controller data:
    - mode: current charge mode, converges to desired_mode
    - desired_mode: desired charge mode as set by user
    - phase_mode: current phase mode
    - priority: currently used priority for charging (HOME_BATTERY, CAR)
    - desired_priority: priority as set by user (AUTO, HOME, CAR), used to decide whether to charge home battery or car first
    """

    mode: ChargeMode = ChargeMode.OFF
    desired_mode: ChargeMode = ChargeMode.OFF
    phase_mode: PhaseMode = PhaseMode.AUTO
    priority: Priority = Priority.AUTO
    desired_priority: Priority = Priority.AUTO


@dataclass
class ChargeControllerConfig(BaseConfig):
    cycle_time: int = 30  # [s] control loop cycle time, used by scheduler
    enable_auto_phase_switching: bool = True  # automatic phase switching depending on available PV
    enable_charging_when_connecting_car: ChargeMode = ChargeMode.OFF
    line_voltage: float = 230  # [V]
    current_rounding_offset: float = 0.1  # [A] offset for max_current rounding
    power_hysteresis: float = 200  # [W] hysteresis for switching on/off and between 1 and 3 phases
    pv_all_min_power: float = 500  # [W] min available power for charging in mode PV_ALL
    pv_allow_charging_delay: int = 120  # [s] min stable allow_charging time before switching on/off (PV modes only)
    prio_auto_soc_threshold: float = 50  # [%] threshold for switching between CAR and HOME_BATTERY prio in AUTO mode


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

    # hostname - optional parameter to enable/disable phase switching depending on where pvcontrol runs (k8s hostname)
    def __init__(self, config: ChargeControllerConfig, meter: Meter, wallbox: Wallbox, relay: PhaseRelay):
        super().__init__(config)
        self._meter = meter
        self._wallbox = wallbox
        self._relay = relay
        self._set_data(ChargeControllerData())
        self._charge_mode_pv_to_off_delay = 5 * 60  # configurable?
        self._pv_allow_charging_value = False
        self._pv_allow_charging_delay = 0
        self._last_charged_energy = None  # reset on every charging cycle, None = needs initialization on first cycle
        self._last_charged_energy_5m = 0.0  # charged energy in last 5m (cycle when meter energy data is updated)
        self._last_energy_consumption = 0.0  # total counter value, must be initialized first with data from meter
        self._last_energy_consumption_grid = 0.0  # total counter value, must be initialized first with data from meter
        # config
        self._enable_phase_switching = self._relay.is_enabled()
        if not self._enable_phase_switching:
            self.set_phase_mode(PhaseMode.DISABLED)
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
        if not self._enable_phase_switching:
            mode = PhaseMode.DISABLED
        self.get_data().phase_mode = mode

    def set_desired_priority(self, priority: Priority) -> None:
        self.get_data().desired_priority = priority

    @_metrics_pvc_controller_processing.time()
    async def run(self) -> None:
        """Read charger data from wallbox and calculate set point"""

        # read current state: order is important for simulation
        wb = await self._wallbox.read_data()
        m = await self._meter.read_data()

        self._meter_charged_energy(m, wb)
        self._control_charge_mode(wb)
        self._control_priority(m)
        # skip one cycle whe switching phases
        if not await self._converge_phases(m, wb):
            await self._control_charging(m, wb)

        # metrics
        ChargeController._metrics_pvc_controller_mode.state(self.get_data().mode)

    def _meter_charged_energy(self, m: MeterData, wb: WallboxData):
        """Calculates energy charged into car by source and updates metrics."""
        if self._last_charged_energy is not None:
            energy_inc = wb.charged_energy - self._last_charged_energy
            # charged_energy reset
            if energy_inc < -1.0:
                energy_inc = wb.charged_energy
            energy_inc = max(energy_inc, 0.0)
            ChargeController._metrics_pvc_controller_total_charged_energy.inc(energy_inc)

            # note: energy values are updates every 5 min only
            # assumption: all energy values are incremented at the same time
            if wb.allow_charging:
                consumed_energy_inc = m.energy_consumption - self._last_energy_consumption
                if consumed_energy_inc > 1.0:
                    consumed_energy_grid_inc = m.energy_consumption_grid - self._last_energy_consumption_grid
                    # no neg allowed (but observed very small negative increments)
                    consumed_energy_grid_inc = max(consumed_energy_grid_inc, 0.0)
                    # Any energy consumed from grid while charging car is accounted to "charged from grid",
                    # the remaining part as "charged from PV"
                    charged_energy_5m = wb.charged_energy - self._last_charged_energy_5m
                    if charged_energy_5m < -1.0:
                        charged_energy_5m = wb.charged_energy
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
                    self._last_charged_energy_5m = wb.charged_energy
            else:
                self._last_charged_energy_5m = wb.charged_energy
        else:
            self._last_charged_energy_5m = wb.charged_energy

        self._last_energy_consumption = m.energy_consumption
        self._last_energy_consumption_grid = m.energy_consumption_grid
        self._last_charged_energy = wb.charged_energy

    # TODO rename
    def _control_charge_mode(self, wb: WallboxData) -> None:
        ctl = self.get_data()
        # Switch to OFF when car gets unplugged (NoVehicle)
        # 5 min delay to allow PV mode before connecting car
        if ctl.mode in [ChargeMode.PV_ONLY, ChargeMode.PV_ALL] and wb.error == 0 and wb.car_status == CarStatus.NoVehicle:
            self._charge_mode_pv_to_off_delay -= self.get_config().cycle_time
            if self._charge_mode_pv_to_off_delay <= 0:
                self.set_desired_mode(ChargeMode.OFF)
        else:
            self._charge_mode_pv_to_off_delay = 5 * 60  # configurable?

        # enable charging if configured and car gets connected (WaitingForVehicle)
        if (
            ctl.mode == ChargeMode.OFF
            and wb.error == 0
            and wb.car_status == CarStatus.WaitingForVehicle
            and self.get_config().enable_charging_when_connecting_car != ChargeMode.OFF
        ):
            self.set_desired_mode(self.get_config().enable_charging_when_connecting_car)

    def _control_priority(self, m: MeterData) -> Priority:
        config = self.get_config()
        priority = self.get_data().desired_priority
        # priority AUTO: charge home battery until 50% and then prefer car
        if priority == Priority.AUTO:
            priority = Priority.HOME_BATTERY if m.soc_battery < config.prio_auto_soc_threshold else Priority.CAR
        self.get_data().priority = priority
        return priority

    # TODO: prevent too fast switching, use energy to grid and time instead of power
    async def _converge_phases(self, m: MeterData, wb: WallboxData) -> bool:
        if wb.error == 0 and wb.wb_error in [WbError.PHASE, WbError.PHASE_RELAY_ERR]:
            # may happen on raspberry reboot -> phase relay is switched off
            # TODO: back-off needed?
            await self._wallbox.trigger_reset()
            return True

        if self._enable_phase_switching:
            available_power = -m.power_grid + wb.power
            desired_phases = self._desired_phases(available_power, wb.phases_in)
            if wb.error == 0 and desired_phases != wb.phases_in:
                # switch phase relay only if charging is off
                if wb.phases_out == 0:
                    await self._wallbox.set_phases_in(desired_phases)
                else:
                    # charging off and wait one cylce
                    await self._set_allow_charging(False, skip_delay=True)
                return True
        return False

    def _desired_phases(self, available_power: float, current_phases: int):
        mode = self.get_data().desired_mode
        phase_mode = self.get_data().phase_mode

        if phase_mode == PhaseMode.CHARGE_1P:
            return 1
        elif phase_mode == PhaseMode.CHARGE_3P:
            return 3
        else:  # AUTO
            if mode == ChargeMode.PV_ONLY:
                if not self.get_config().enable_auto_phase_switching:
                    return 1
                elif current_phases == 1:
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
                if not self.get_config().enable_auto_phase_switching:
                    return 1
                elif current_phases == 1:
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

    async def _control_charging(self, m: MeterData, wb: WallboxData) -> None:
        mode = self.get_data().desired_mode
        if mode == ChargeMode.OFF:
            await self._set_allow_charging(False, skip_delay=True)
            self.set_desired_mode(ChargeMode.MANUAL)
        elif mode == ChargeMode.MAX:
            await self._wallbox.set_max_current(self._max_supported_current)
            await self._set_allow_charging(True, skip_delay=True)
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
            config = self.get_config()

            priority = self.get_data().priority
            if priority == Priority.CAR:
                # Priority.CAR neither charge nor discharge home battery
                available_power = -m.power_grid + wb.power - m.power_battery
            else:  # Priority.HOME_BATTERY
                available_power = -m.power_grid + wb.power
                if m.power_battery > 0:
                    # don't discharge home battery
                    available_power -= m.power_battery
                else:
                    # TODO: reduce a little to allow home battery to increase charging power
                    pass

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
            await self._wallbox.set_max_current(max_current)

            # set allow_charging if changed for at least allow_charging_delay
            if wb.allow_charging != desired_allow_charging:
                self._pv_allow_charging_delay -= config.cycle_time
                if self._pv_allow_charging_delay <= 0:
                    await self._set_allow_charging(desired_allow_charging)
            else:
                self._pv_allow_charging_delay = config.pv_allow_charging_delay

        self.get_data().mode = mode

    async def _set_allow_charging(self, v: bool, skip_delay: bool = False):
        self._pv_allow_charging_value = v  # remember last set allow_charging value set by PV control
        self._pv_allow_charging_delay = self.get_config().pv_allow_charging_delay if not skip_delay else 0
        await self._wallbox.allow_charging(v)


class ChargeControllerFactory:
    @classmethod
    def newController(cls, meter: Meter, wb: Wallbox, relay: PhaseRelay, **kwargs) -> ChargeController:
        return ChargeController(ChargeControllerConfig(**kwargs), meter, wb, relay)
