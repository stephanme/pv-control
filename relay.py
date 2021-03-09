import platform, sys, logging

logger = logging.getLogger(__name__)

logger.info(f'Running on {platform.machine()}')
if ('x86' in platform.machine()):
  logger.warning('Using fake_rpi')
  import fake_rpi
  from fake_rpi.RPi import GPIO
else:
 import RPi.GPIO as GPIO

Relay_Ch1 = 26
# Relay_Ch2 = 20
# Relay_Ch3 = 21

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

GPIO.setup(Relay_Ch1,GPIO.OUT)
# GPIO.setup(Relay_Ch2,GPIO.OUT)
# GPIO.setup(Relay_Ch3,GPIO.OUT)

def readChannel1():
  return GPIO.input(Relay_Ch1)

def writeChannel1(v):
  logger.info(f'writeChannel1={v}')
  GPIO.output(Relay_Ch1, v)