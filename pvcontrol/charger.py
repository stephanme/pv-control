import math
from dataclasses import dataclass
from pvcontrol import relay
from pvcontrol.meter import MeterData


@dataclass
class ChargerData:
    phases: int  # 1 or 3
    power_car: float  # [W]
    current_setpoint: int  # [A]


# TODO: read from go-e box
class Charger:
    def __init__(self, simulation=False):
        """ simulation=True -> no access to relay and wallbox, car power is simulated """
        self._charger_data = ChargerData(3, 0, 0)
        self._simulation = simulation

    def get_charger_data(self) -> ChargerData:
        """ Get last cached charger data. """
        return self._charger_data

    def read_charger_and_calc_setpoint(self, meter: MeterData) -> ChargerData:
        """ Read charger data from wallbox and calculate set point """

        # simulate last measurement from wallbox
        power_car = self._charger_data.current_setpoint * self._charger_data.phases * 230
        if self._simulation:
            ch = self._charger_data.phases == 1
        else:
            ch = relay.readChannel1()

        phases = 1 if ch else 3
        available_power = -meter.power_grid + power_car
        new_el_current_setpoint = math.floor(available_power / 230 / phases)
        if new_el_current_setpoint < 6:
            new_el_current_setpoint = 0
        elif new_el_current_setpoint > 16:
            new_el_current_setpoint = 16
        self._charger_data = ChargerData(phases, power_car, new_el_current_setpoint)
        return self._charger_data

    # TODO: replace by control loop
    def set_phases(self, phases: int) -> None:
        # relay ON = 1 phase
        relay.writeChannel1(phases == 1)
        self._charger_data.phases = phases

    def is_simulated(self):
        return self._simulation
