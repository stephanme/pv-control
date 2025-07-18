import enum
import logging
import prometheus_client
from dataclasses import dataclass

from pvcontrol.service import BaseConfig, BaseData, BaseService

logger = logging.getLogger(__name__)


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


class PhaseRelayFactory:
    # hostname - optional parameter to enable/disable phase switching depending on where pvcontrol runs (k8s hostname)
    @classmethod
    def newPhaseRelay(cls, type: str, hostname: str, **kwargs) -> PhaseRelay:
        config = PhaseRelayConfig(**kwargs)
        enabled = PhaseRelayFactory.is_relay_enabled(config, hostname)
        logger.info(f"PhaseRelay type={type}, enabled={enabled}")

        if enabled:
            if type == "RaspiPhaseRelay":
                # import only when configured and enabled = running on pi1 (RPi.GPIO module is not available on other platforms)
                from pvcontrol.raspi_relay import RaspiPhaseRelay

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
