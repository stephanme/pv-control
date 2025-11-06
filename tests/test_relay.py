from typing import final, override
import unittest

from pvcontrol.relay import DisabledPhaseRelay, PhaseRelayConfig, PhaseRelayData, PhaseRelayFactory, RelayType, SimulatedPhaseRelay

# pyright: reportUninitializedInstanceVariable=false
# pyright: reportPrivateUsage=false


@final
class PhaseRelayTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.relay = SimulatedPhaseRelay(PhaseRelayConfig())

    def test_phases_to_relay_NC(self):
        self.relay.get_config().phase_relay_type = RelayType.NC
        self.assertTrue(self.relay._phases_to_relay(1))
        self.assertFalse(self.relay._phases_to_relay(3))
        self.assertFalse(self.relay._phases_to_relay(2))

    def test_relay_to_phases_NC(self):
        self.relay.get_config().phase_relay_type = RelayType.NC
        self.assertEqual(3, self.relay._relay_to_phases(False))
        self.assertEqual(1, self.relay._relay_to_phases(True))

    def test_phases_to_relay_NO(self):
        self.assertFalse(self.relay._phases_to_relay(1))
        self.assertTrue(self.relay._phases_to_relay(3))
        self.assertFalse(self.relay._phases_to_relay(2))

    def test_relay_to_phases_NO(self):
        self.assertEqual(1, self.relay._relay_to_phases(False))
        self.assertEqual(3, self.relay._relay_to_phases(True))

    def test_get_data(self):
        self.assertEqual(PhaseRelayData(error=0, enabled=True, phase_relay=False, phases=1), self.relay.get_data())


class PhaseRelayFactoryTest(unittest.TestCase):
    def test_disabled(self):
        relay = PhaseRelayFactory.newPhaseRelay("", "pi1", enable_phase_switching=False)
        self.assertIsInstance(relay, DisabledPhaseRelay)

    def test_disabled_by_hostname(self):
        relay = PhaseRelayFactory.newPhaseRelay("", "pi2", enable_phase_switching=True, installed_on_host="pi1")
        self.assertIsInstance(relay, DisabledPhaseRelay)

    def test_enabled(self):
        relay = PhaseRelayFactory.newPhaseRelay("SimulatedPhaseRelay", "pi1", enable_phase_switching=True, installed_on_host="pi1")
        self.assertIsInstance(relay, SimulatedPhaseRelay)
