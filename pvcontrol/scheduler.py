import asyncio
from contextlib import suppress
import datetime
import threading
from typing import Any, Callable, final
from collections.abc import Awaitable


@final
class Scheduler:
    def __init__(self, interval: float, function: Callable[[], None]):
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
        self._timer_thread = threading.Timer(interval=0, function=self.run)
        self._timer_thread.start()

    def stop(self) -> None:
        self._started = False
        self._last_started_at = None
        if self._timer_thread is not None:
            self._timer_thread.cancel()
        self._timer_thread = None

    def is_started(self) -> bool:
        return self._started


@final
class AsyncScheduler:
    def __init__(self, interval: float, coro: Callable[[], Awaitable[Any]]):
        self._interval = interval
        self._coro = coro
        self._task = None

    async def start(self):
        if self._task:
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            task = self._task
            self._task = None
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    def is_started(self) -> bool:
        return self._task is not None

    async def _run(self) -> None:
        while True:
            await asyncio.gather(
                self._coro(),
                asyncio.sleep(self._interval),
            )
