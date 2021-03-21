from dataclasses import dataclass
import math
import time


@dataclass
class MeterData:
    power_pv: float  # power delivered by PV [W]
    power_consumption: float  # power consumption [W] (including car charing)
    power_grid: float  # power from/to grid [W], + from grid, - to grid
    # power_consumption = power_pv + power_grid


class Meter:
    _simulation = False

    def __init__(self):
        self._meter_data = MeterData(0, 0, 0)
        self._power_car = 0

    def get_meter_data(self) -> MeterData:
        """ Get last cached meter data. """
        return self._meter_data

    def read_meter(self) -> MeterData:
        """ Read meter data via modbus from Kostal. The data is cached. """
        # TODO: read via modbus from Kostal
        self._meter_data = self._simulate_meter()
        return self._meter_data

    def _simulate_meter(self) -> MeterData:
        t = time.time()
        pv = math.floor(5000 * math.fabs(math.sin(2 * math.pi * t / (60 * 60))))
        consumption = 500 + math.floor(500 * math.fabs(math.sin(2 * math.pi * t / (60 * 5)))) + self._power_car
        grid = consumption - pv
        return MeterData(pv, consumption, grid)

    def set_charger_data_for_simulation(self, power_car: float):
        """ only for simulation """
        self._power_car = power_car
