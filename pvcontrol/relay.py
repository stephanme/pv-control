import enum
import os
import platform
import sys
import logging
import prometheus_client
from dataclasses import dataclass

from pvcontrol.service import BaseConfig, BaseData, BaseService

logger = logging.getLogger(__name__)

# GPIO is only awailable on raspi
# pyright: reportPossiblyUnboundVariable=false, reportMissingModuleSource=false
logger.info(f"Running on {platform.machine()} / {sys.platform}")
gpio_disabled = os.environ.get("DISABLE_GPIO") is not None
if gpio_disabled or "x86" in platform.machine() or "darwin" == sys.platform or "win32" == sys.platform:
    logger.warning("GPIO not available")
    if gpio_disabled:
        logger.warning("DISABLE_GPIO environment variable set")
    # uncomment for local dev if needed
    # from fake_rpi.RPi import GPIO
else:
    # raspi, arm7 or aarch64
    import RPi.GPIO as GPIO

    GPIO.setwarnings(True)
    GPIO.setmode(GPIO.BCM)


# https://www.waveshare.com/wiki/RPi_Relay_Board
# Relay OFF = false = GPIO.HIGH
# Relay ON = true = GPIO.LOW
class GPIORelay:
    CHANNEL_1 = 26
    CHANNEL_2 = 20
    CHANNEL_3 = 21

    def __init__(self, channel: int):
        self._channel = channel
        ch_function = GPIO.gpio_function(channel)
        logger.info(f"Before channel {channel} setup: function={ch_function}")
        if ch_function == GPIO.OUT:
            # keep state if channel is already OUT (= app restart)
            GPIO.setup(channel, GPIO.OUT)
        else:
            # init to GPIO.HIGH = OFF to avoid switching on reboot
            GPIO.setup(channel, GPIO.OUT, initial=GPIO.HIGH)
        logger.info(f"After channel {channel} setup : relay={GPIO.input(channel)}")

    def read(self) -> bool:
        return GPIO.input(self._channel) == GPIO.LOW

    def write(self, v: bool):
        logger.info(f"write channel {self._channel}={v}")
        GPIO.output(self._channel, GPIO.LOW if v else GPIO.HIGH)


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
        self._gpio_relay = GPIORelay(GPIORelay.CHANNEL_1)  # TODO: configurable
        self.get_phases()

    def get_phases(self):
        ch = self._gpio_relay.read()
        self._update_relay_state(ch)
        return self.get_data().phases

    def set_phases(self, phases: int):
        ch = self._phases_to_relay(phases)
        self._gpio_relay.write(ch)
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
