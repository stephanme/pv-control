import enum
import platform
import sys
import logging
import prometheus_client
from dataclasses import dataclass

from pvcontrol.service import BaseConfig, BaseData, BaseService

logger = logging.getLogger(__name__)

logger.info(f"Running on {platform.machine()} / {sys.platform}")
if "x86" in platform.machine() or "darwin" == sys.platform or "win32" == sys.platform:
    logger.warning("Using fake_rpi")
    from fake_rpi.RPi import GPIO
else:
    import RPi.GPIO as GPIO

Relay_Ch1 = 26
# Relay_Ch2 = 20
# Relay_Ch3 = 21

GPIO.setwarnings(True)
GPIO.setmode(GPIO.BCM)

_ch1_function = GPIO.gpio_function(Relay_Ch1)
logger.info(f"Before channel setup: ch1 function={_ch1_function}")
if _ch1_function == GPIO.OUT:
    # keep state if channel is already OUT (= app restart)
    GPIO.setup(Relay_Ch1, GPIO.OUT)
else:
    # init to GPIO.HIGH = OFF to avoid switching on reboot
    GPIO.setup(Relay_Ch1, GPIO.OUT, initial=GPIO.HIGH)
logger.info(f"After channel setup : ch1={GPIO.input(Relay_Ch1)}")

# GPIO.setup(Relay_Ch2,GPIO.OUT)
# GPIO.setup(Relay_Ch3,GPIO.OUT)

# https://www.waveshare.com/wiki/RPi_Relay_Board
# Relay OFF = false = GPIO.HIGH
# Relay ON = true = GPIO.LOW


def _readChannel1() -> bool:
    return GPIO.input(Relay_Ch1) == GPIO.LOW


def _writeChannel1(v: bool):
    logger.info(f"writeChannel1={v}")
    GPIO.output(Relay_Ch1, GPIO.LOW if v else GPIO.HIGH)


def _cleanup():
    logger.info("skip cleanup to keep relay state")
    # GPIO.cleanup()


class RelayType(str, enum.Enum):
    NO = "NO"  # normally open
    NC = "NC"  # normally closed


@dataclass
class PhaseRelayConfig(BaseConfig):
    enable_phase_switching: bool = True  # set to False of phase relay is not in operation
    installed_on_host: str = ""  # if set, phase switching is only allowed when running on specified host (passed to pvcontrol via --hostname option, e.g. k8s nodeName)
    phase_relay_type: RelayType = RelayType.NO


@dataclass
class PhaseRelayData(BaseData):
    enabled: bool = False  # indicates if phase relay is available
    phase_relay: bool = False  # on/off - mapping to 1 or 3 phases depends on relay type/wiring
    phases: int = 0  # number of phases according to relay, 0 if disabled


class PhaseRelay(BaseService[PhaseRelayConfig, PhaseRelayData]):
    _metrics_pvc_phase_relay = prometheus_client.Gauge("pvcontrol_phase_relay", "Phase switch relay status (off/on)")
    _metrics_pvc_phase_relay_phases = prometheus_client.Gauge(
        "pvcontrol_phase_relay_phases", "Number of phases according to relay (0=disabled)"
    )

    def __init__(self, config: PhaseRelayConfig):
        super().__init__(config)

    def is_enabled(self) -> bool:
        return self.get_data().enabled

    def get_phases(self):
        return self.get_data().phases

    def set_phases(self, phases: int):
        pass

    def _update_relay_state(self, ch: bool):
        phases = self._relay_to_phases(ch)
        enabled = self.get_data().enabled
        self._set_data(PhaseRelayData(enabled=enabled, phase_relay=ch, phases=phases))
        PhaseRelay._metrics_pvc_phase_relay.set(ch)
        PhaseRelay._metrics_pvc_phase_relay_phases.set(phases)

    def _relay_to_phases(self, ch: bool) -> int:
        if self.get_config().phase_relay_type == RelayType.NO:
            return 3 if ch else 1
        else:
            return 1 if ch else 3

    def _phases_to_relay(self, phases: int) -> bool:
        if self.get_config().phase_relay_type == RelayType.NO:
            return phases == 3
        else:
            return phases == 1


class DisabledPhaseRelay(PhaseRelay):
    def __init__(self, config: PhaseRelayConfig):
        super().__init__(config)
        self._set_data(PhaseRelayData(enabled=False))
        self._update_relay_state(False)


class SimulatedPhaseRelay(PhaseRelay):
    def __init__(self, config: PhaseRelayConfig):
        super().__init__(config)
        self._set_data(PhaseRelayData(enabled=True))
        self._update_relay_state(False)

    def set_phases(self, phases: int):
        ch = self._phases_to_relay(phases)
        self._update_relay_state(ch)


class RaspiPhaseRelay(PhaseRelay):
    def __init__(self, config: PhaseRelayConfig):
        super().__init__(config)
        self._set_data(PhaseRelayData(enabled=True))
        self.get_phases()

    def get_phases(self):
        ch = _readChannel1()
        self._update_relay_state(ch)
        return self.get_data().phases

    def set_phases(self, phases: int):
        ch = self._phases_to_relay(phases)
        _writeChannel1(ch)
        self._update_relay_state(ch)


class PhaseRelayFactory:
    # hostname - optional parameter to enable/disable phase switching depending on where pvcontrol runs (k8s hostname)
    @classmethod
    def newPhaseRelay(cls, type: str, hostname: str, **kwargs) -> PhaseRelay:
        config = PhaseRelayConfig(**kwargs)
        enabled = PhaseRelayFactory.is_relay_enabled(config, hostname)
        logger.info(f"PhaseRelay enabled={enabled}")

        if enabled:
            if type == "RaspiPhaseRelay":
                return RaspiPhaseRelay(config)
            elif type == "SimulatedPhaseRelay":
                return SimulatedPhaseRelay(config)
            else:
                raise ValueError(f"Bad phase relay type: {type}")
        else:
            return DisabledPhaseRelay(config)

    @classmethod
    def is_relay_enabled(cls, config: PhaseRelayConfig, hostname: str) -> bool:
        enabled = config.enable_phase_switching
        if enabled:
            require_hostname = config.installed_on_host
            enabled = not require_hostname or require_hostname == hostname
        return enabled
