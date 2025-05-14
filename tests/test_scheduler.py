import asyncio
import unittest
import time
from pvcontrol.scheduler import AsyncScheduler, Scheduler


class Task:
    def __init__(self):
        self.call_cnt = 0

    def fnc(self):
        self.call_cnt += 1

    async def async_fnc(self):
        self.fnc()


class SchedulerTest(unittest.TestCase):
    def setUp(self):
        self.task = Task()
        self.scheduler = Scheduler(0.1, self.task.fnc)

    def test_scheduling(self):
        self.assertFalse(self.scheduler.is_started())
        self.scheduler.start()
        self.assertTrue(self.scheduler.is_started())

        time.sleep(1)
        self.scheduler.stop()
        self.assertFalse(self.scheduler.is_started())

        self.assertLessEqual(self.task.call_cnt, 11)
        self.assertGreaterEqual(self.task.call_cnt, 9)

        time.sleep(0.3)
        self.assertLessEqual(self.task.call_cnt, 11)


class AsyncSchedulerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.task = Task()
        self.scheduler = AsyncScheduler(0.1, self.task.async_fnc)

    async def test_scheduling(self):
        self.assertFalse(self.scheduler.is_started())
        await self.scheduler.start()
        self.assertTrue(self.scheduler.is_started())

        await asyncio.sleep(1)
        await self.scheduler.stop()
        self.assertFalse(self.scheduler.is_started())

        self.assertLessEqual(self.task.call_cnt, 11)
        self.assertGreaterEqual(self.task.call_cnt, 9)

        await asyncio.sleep(0.3)
        self.assertLessEqual(self.task.call_cnt, 11)
