import platform, logging

logger = logging.getLogger(__name__)

logger.info(f"Running on {platform.machine()}")
if "x86" in platform.machine():
    logger.warning("Using fake_rpi")
    from fake_rpi.RPi import GPIO
else:
    import RPi.GPIO as GPIO

Relay_Ch1 = 26
# Relay_Ch2 = 20
# Relay_Ch3 = 21

GPIO.setwarnings(True)
GPIO.setmode(GPIO.BCM)

# no initial value = keep state (on reboot: behaves as if GPIO.HIGH)
GPIO.setup(Relay_Ch1, GPIO.OUT)
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
    logger.info("cleanup")
    GPIO.cleanup()
