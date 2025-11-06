# pyright: reportImportCycles=false
# this module is imported by PhaseRelayFactory to avoid import cycles
import logging
from typing import final, override

# GPIO is only awailable on raspi
import RPi.GPIO as GPIO  # pyright: ignore[reportMissingModuleSource]

from pvcontrol.relay import PhaseRelay, PhaseRelayConfig, PhaseRelayData

logger = logging.getLogger(__name__)

logger.info("Initializing RPi.GPIO")
GPIO.setwarnings(True)
GPIO.setmode(GPIO.BCM)


# https://www.waveshare.com/wiki/RPi_Relay_Board
# Relay OFF = false = GPIO.HIGH
# Relay ON = true = GPIO.LOW
@final
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


class RaspiPhaseRelay(PhaseRelay):
    def __init__(self, config: PhaseRelayConfig):
        super().__init__(config, PhaseRelayData(enabled=True))
        self._gpio_relay: GPIORelay = GPIORelay(GPIORelay.CHANNEL_1)  # TODO: configurable
        self.get_phases()

    @override
    def get_phases(self):
        ch = self._gpio_relay.read()
        self._update_relay_state(ch)
        return self.get_data().phases

    @override
    def set_phases(self, phases: int):
        ch = self._phases_to_relay(phases)
        self._gpio_relay.write(ch)
        self._update_relay_state(ch)
