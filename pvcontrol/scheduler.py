import datetime
import threading
from typing import Callable


class Scheduler:
    def __init__(self, interval: float, function: Callable):
        self._last_started_at = None
        self._started = False
        self._timer_thread = None
        self._interval = interval
        self._function = function

    def run(self) -> None:
        self._last_started_at = datetime.datetime.now()
        self._timer_thread = threading.Timer(interval=self._interval, function=self.run)
        self._timer_thread.start()

        self._function()

    def start(self):
        if self._started is True:
            return

        self._started = True
        self.__timer_thread = threading.Timer(interval=0, function=self.run)
        self.__timer_thread.start()

    def stop(self) -> None:
        self._started = False
        self._last_started_at = None
        if self._timer_thread is not None:
            self._timer_thread.cancel()
        self._timer_thread = None

    def is_started(self) -> bool:
        return self._started
