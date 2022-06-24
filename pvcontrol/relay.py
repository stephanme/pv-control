import platform
import sys
import logging

logger = logging.getLogger(__name__)

logger.info(f"Running on {platform.machine()} / {sys.platform}")
if "x86" in platform.machine() or "darwin" == sys.platform:
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


def readChannel1() -> bool:
    return GPIO.input(Relay_Ch1) == GPIO.LOW


def writeChannel1(v: bool):
    logger.info(f"writeChannel1={v}")
    GPIO.output(Relay_Ch1, GPIO.LOW if v else GPIO.HIGH)


def cleanup():
    logger.info("skip cleanup to keep relay state")
    # GPIO.cleanup()
