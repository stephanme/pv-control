# configure logging before initializing further modules
import logging

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT)
