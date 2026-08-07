import asyncio
import json
import unittest
from typing import Any, final, override
from unittest.mock import AsyncMock, MagicMock, patch

from pvcontrol.car import CarData
from pvcontrol.chargecontroller import ChargeControllerData, ChargeMode, PhaseMode, Priority
from pvcontrol.meter import MeterData
from pvcontrol.mqtt import ENTITY_DEFINITIONS, MqttConfig, MqttPublisher
from pvcontrol.relay import PhaseRelayData
from pvcontrol.wallbox import CarStatus, WallboxData, WbError


@final
class MqttConfigTest(unittest.TestCase):
    def test_defaults(self):
        config = MqttConfig()
        self.assertEqual("localhost", config.broker)
        self.assertEqual(1883, config.port)
        self.assertEqual("", config.username)
        self.assertEqual("", config.password)
        self.assertEqual("pvcontrol", config.topic_prefix)
        self.assertEqual("homeassistant", config.ha_discovery_prefix)

    def test_from_kwargs(self):
        config = MqttConfig(broker="192.168.1.100", port=8883, username="user", password="pass")
        self.assertEqual("192.168.1.100", config.broker)
        self.assertEqual(8883, config.port)
        self.assertEqual("user", config.username)
        self.assertEqual("pass", config.password)


@final
class EntityDefinitionsTest(unittest.TestCase):
    def test_all_entities_have_required_fields(self):
        for entity in ENTITY_DEFINITIONS:
            self.assertIn(entity.component, ("sensor", "binary_sensor", "select"))
            self.assertTrue(entity.object_id)
            self.assertTrue(entity.name)
            self.assertTrue(entity.value_template)

    def test_unique_object_ids(self):
        ids = [e.object_id for e in ENTITY_DEFINITIONS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_enum_sensors_have_options(self):
        enum_entities = [e for e in ENTITY_DEFINITIONS if e.device_class == "enum"]
        for entity in enum_entities:
            self.assertTrue(entity.options, f"{entity.object_id} has device_class=enum but no options")

    def test_charge_mode_options(self):
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "controller_mode")
        self.assertEqual(entity.options, [m.value for m in ChargeMode])

    def test_car_status_options(self):
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "wallbox_car_status")
        self.assertEqual(entity.options, [s.name for s in CarStatus])

    def test_wb_error_options(self):
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "wallbox_wb_error")
        self.assertEqual(entity.options, [e.name for e in WbError])


@final
class MqttPublisherTest(unittest.IsolatedAsyncioTestCase):
    @override
    def setUp(self):
        self.config = MqttConfig(broker="testhost", port=1883)
        self.mock_controller = MagicMock()
        self.mock_meter = MagicMock()
        self.mock_wallbox = MagicMock()
        self.mock_relay = MagicMock()
        self.mock_car = MagicMock()
        self.mock_controller.get_data.return_value = ChargeControllerData()
        self.mock_meter.get_data.return_value = MeterData()
        self.mock_wallbox.get_data.return_value = WallboxData()
        self.mock_relay.get_data.return_value = PhaseRelayData()
        self.mock_car.get_data.return_value = CarData()
        self.publisher = MqttPublisher(
            self.config,
            "1.0.0",
            controller=self.mock_controller,
            meter=self.mock_meter,
            wallbox=self.mock_wallbox,
            relay=self.mock_relay,
            car=self.mock_car,
        )
        self.publisher._state_restore_timeout_s = 0  # skip wait in tests

    @patch("pvcontrol.mqtt.aiomqtt.Client")
    async def test_start_connects_and_publishes_discovery(self, mock_client_cls: Any):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.publish = AsyncMock()
        mock_client_cls.return_value = mock_client

        await self.publisher.start()

        mock_client_cls.assert_called_once()
        call_kwargs = mock_client_cls.call_args.kwargs
        self.assertEqual("testhost", call_kwargs["hostname"])
        self.assertEqual(1883, call_kwargs["port"])

        # Should publish online status + all discovery messages
        expected_publish_count = 1 + len(ENTITY_DEFINITIONS)
        self.assertEqual(expected_publish_count, mock_client.publish.call_count)

        # First call should be the online status
        first_call = mock_client.publish.call_args_list[0]
        self.assertEqual("pvcontrol/status", first_call.args[0] if first_call.args else first_call.kwargs.get("topic"))

    @patch("pvcontrol.mqtt.aiomqtt.Client")
    async def test_discovery_payload_structure(self, mock_client_cls: Any):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.publish = AsyncMock()
        mock_client_cls.return_value = mock_client

        await self.publisher.start()

        # Check a discovery publish (skip first which is online status)
        discovery_call = mock_client.publish.call_args_list[1]
        topic: str = discovery_call.args[0] if discovery_call.args else discovery_call.kwargs["topic"]
        payload_str = discovery_call.kwargs.get("payload") or discovery_call.args[1]
        payload = json.loads(payload_str)

        self.assertIn("homeassistant/", topic)
        self.assertIn("name", payload)
        self.assertIn("unique_id", payload)
        self.assertIn("state_topic", payload)
        self.assertIn("value_template", payload)
        self.assertIn("device", payload)
        self.assertIn("availability", payload)
        self.assertEqual("pvcontrol/state", payload["state_topic"])
        self.assertEqual("1.0.0", payload["device"]["sw_version"])

    @patch("pvcontrol.mqtt.aiomqtt.Client")
    async def test_start_failure_does_not_crash(self, mock_client_cls: Any):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=OSError("Connection refused"))
        mock_client_cls.return_value = mock_client

        self.publisher._retry_window_s = 0  # skip retry loop immediately
        await self.publisher.start()
        self.assertIsNone(self.publisher._client)

    @patch("pvcontrol.mqtt.asyncio.sleep", new_callable=AsyncMock)
    @patch("pvcontrol.mqtt.time.time")
    @patch("pvcontrol.mqtt.aiomqtt.Client")
    async def test_start_retry_exhaustion_logs_error(self, mock_client_cls: Any, mock_time: MagicMock, mock_sleep: AsyncMock):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=OSError("Connection refused"))
        mock_client_cls.return_value = mock_client

        # Drive the clock: set deadline at t=0, allow one retry at t=0, then jump past the window.
        mock_time.side_effect = [0.0, 0.0, 100.0]
        self.publisher._retry_window_s = 60

        with self.assertLogs("pvcontrol.mqtt", level="ERROR") as logs:
            await self.publisher.start()

        self.assertIsNone(self.publisher._client)
        self.assertEqual(mock_client_cls.call_count, 2)  # initial attempt + one retry
        mock_sleep.assert_awaited_once()
        self.assertTrue(any("retry window" in msg for msg in logs.output))

    @patch("pvcontrol.mqtt.asyncio.sleep", new_callable=AsyncMock)
    @patch("pvcontrol.mqtt.aiomqtt.Client")
    async def test_start_eventually_succeeds(self, mock_client_cls: Any, mock_sleep: AsyncMock):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.publish = AsyncMock()
        mock_client_cls.return_value = mock_client

        # First call fails, second call succeeds
        mock_client.__aenter__.side_effect = [OSError("Connection refused"), mock_client]
        await self.publisher.start()
        self.assertIsNotNone(self.publisher._client)
        self.assertEqual(mock_client_cls.call_count, 2)

    @patch("pvcontrol.mqtt.aiomqtt.Client")
    async def test_stop_publishes_offline(self, mock_client_cls: Any):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.publish = AsyncMock()
        mock_client_cls.return_value = mock_client

        await self.publisher.start()
        mock_client.publish.reset_mock()
        await self.publisher.stop()

        mock_client.publish.assert_called_once()
        call_kwargs = mock_client.publish.call_args.kwargs
        self.assertEqual("pvcontrol/status", mock_client.publish.call_args.args[0])
        self.assertEqual("offline", call_kwargs["payload"])

    @patch("pvcontrol.mqtt.aiomqtt.Client")
    async def test_publish_state_converts_enums_to_names(self, mock_client_cls: Any):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.publish = AsyncMock()
        mock_client_cls.return_value = mock_client

        await self.publisher.start()
        mock_client.publish.reset_mock()

        self.mock_wallbox.get_data.return_value = WallboxData(car_status=CarStatus.Charging, wb_error=WbError.OK, power=3000)

        await self.publisher.publish_state()

        mock_client.publish.assert_called_once()
        call_kwargs = mock_client.publish.call_args.kwargs
        payload = json.loads(call_kwargs["payload"])
        self.assertEqual("Charging", payload["wallbox"]["car_status"])
        self.assertEqual("OK", payload["wallbox"]["wb_error"])
        self.assertTrue(call_kwargs["retain"])

    async def test_publish_state_without_connection_does_not_crash(self):
        self.publisher._client = None
        # Should not raise even without connection (reconnect also fails silently)
        with patch.object(self.publisher, "_try_reconnect", new_callable=AsyncMock):
            await self.publisher.publish_state()

    @patch("pvcontrol.mqtt.aiomqtt.Client")
    async def test_lwt_configured(self, mock_client_cls: Any):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.publish = AsyncMock()
        mock_client_cls.return_value = mock_client

        await self.publisher.start()

        call_kwargs = mock_client_cls.call_args.kwargs
        will = call_kwargs["will"]
        self.assertEqual("pvcontrol/status", str(will.topic))
        self.assertEqual("offline", will.payload)

    @patch("pvcontrol.mqtt.aiomqtt.Client")
    async def test_restore_state_applies_retained_values(self, mock_client_cls: Any):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.publish = AsyncMock()
        mock_client.subscribe = AsyncMock()
        mock_client.unsubscribe = AsyncMock()
        mock_client_cls.return_value = mock_client

        retained_payload = json.dumps(
            {
                "controller": {
                    "desired_mode": "PV_ONLY",
                    "phase_mode": "CHARGE_1P",
                    "desired_priority": "CAR",
                }
            }
        )

        async def mock_messages():
            yield MagicMock(payload=retained_payload.encode(), topic="pvcontrol/state")
            # Don't exhaust - wait forever like a real MQTT connection
            await asyncio.Event().wait()

        mock_client.messages = mock_messages()

        self.publisher._state_restore_timeout_s = 0.5  # short timeout for this test
        await self.publisher.start()

        self.mock_controller.set_desired_mode.assert_called_once_with(ChargeMode.PV_ONLY)
        self.mock_controller.set_phase_mode.assert_called_once_with(PhaseMode.CHARGE_1P)
        self.mock_controller.set_desired_priority.assert_called_once_with(Priority.CAR)

        # unsubscribed after processing retained message
        mock_client.unsubscribe.assert_called_once_with("pvcontrol/state")

    @patch("pvcontrol.mqtt.aiomqtt.Client")
    async def test_restore_state_timeout_does_not_crash(self, mock_client_cls: Any):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.publish = AsyncMock()
        mock_client.subscribe = AsyncMock()
        mock_client.unsubscribe = AsyncMock()
        mock_client_cls.return_value = mock_client

        async def mock_messages():
            # No messages - wait forever (simulates timeout)
            await asyncio.Event().wait()
            yield  # make it a generator

        mock_client.messages = mock_messages()

        self.publisher._state_restore_timeout_s = 0.1  # short timeout
        await self.publisher.start()
        mock_client.unsubscribe.assert_called_once_with("pvcontrol/state")

    # Don't restore phase_mode if it's DISABLED. DISABLED is set only if phase switching relay is not available
    # when pvcontrol was deployed on a node without it.
    @patch("pvcontrol.mqtt.aiomqtt.Client")
    async def test_restore_state_ignore_disabled_phase_mode(self, mock_client_cls: Any):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.publish = AsyncMock()
        mock_client.subscribe = AsyncMock()
        mock_client.unsubscribe = AsyncMock()
        mock_client_cls.return_value = mock_client

        retained_payload = json.dumps(
            {
                "controller": {
                    "desired_mode": "PV_ONLY",
                    "phase_mode": "DISABLED",
                    "desired_priority": "CAR",
                }
            }
        )

        async def mock_messages():
            yield MagicMock(payload=retained_payload.encode(), topic="pvcontrol/state")
            # Don't exhaust - wait forever like a real MQTT connection
            await asyncio.Event().wait()

        mock_client.messages = mock_messages()

        self.publisher._state_restore_timeout_s = 0.5  # short timeout for this test
        await self.publisher.start()

        self.mock_controller.set_desired_mode.assert_called_once_with(ChargeMode.PV_ONLY)
        self.mock_controller.set_phase_mode.assert_not_called()
        self.mock_controller.set_desired_priority.assert_called_once_with(Priority.CAR)


@final
class EntityDefinitionsSelectTest(unittest.TestCase):
    """Tests for the new select entities for MQTT control."""

    def test_select_entities_exist_and_have_command_topic(self):
        """Verify the three select entities are defined."""
        select_entities = [e for e in ENTITY_DEFINITIONS if e.component == "select"]
        self.assertEqual(len(select_entities), 3)

        object_ids = {e.object_id for e in select_entities}
        self.assertIn("controller_desired_mode", object_ids)
        self.assertIn("controller_phase_mode", object_ids)
        self.assertIn("controller_desired_priority", object_ids)
        for entity in select_entities:
            self.assertIsNotNone(entity.command_topic, f"{entity.object_id} missing command_topic")
            assert entity.command_topic is not None
            self.assertTrue(entity.command_topic.startswith("controller/"))

    def test_desired_mode_select_options(self):
        """Desired mode select should have all ChargeMode values as options."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "controller_desired_mode")
        self.assertEqual(entity.options, [m.value for m in ChargeMode])
        self.assertEqual(entity.command_topic, "controller/desired_mode/set")

    def test_phase_mode_select_options(self):
        """Phase mode select should have all PhaseMode values as options."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "controller_phase_mode")
        self.assertEqual(entity.options, [m.value for m in PhaseMode])
        self.assertEqual(entity.command_topic, "controller/phase_mode/set")

    def test_desired_priority_select_options(self):
        """Desired priority select should have all Priority values as options."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "controller_desired_priority")
        self.assertEqual(entity.options, [m.value for m in Priority])
        self.assertEqual(entity.command_topic, "controller/desired_priority/set")


@final
class MqttPublisherCommandTest(unittest.IsolatedAsyncioTestCase):
    """Tests for MQTT command handling functionality."""

    @override
    def setUp(self):
        self.config = MqttConfig(broker="testhost", port=1883)
        self.mock_controller = MagicMock()
        self.mock_meter = MagicMock()
        self.mock_wallbox = MagicMock()
        self.mock_relay = MagicMock()
        self.mock_car = MagicMock()
        self.mock_controller.get_data.return_value = ChargeControllerData()
        self.mock_meter.get_data.return_value = MeterData()
        self.mock_wallbox.get_data.return_value = WallboxData()
        self.mock_relay.get_data.return_value = PhaseRelayData()
        self.mock_car.get_data.return_value = CarData()
        self.publisher = MqttPublisher(
            self.config,
            "1.0.0",
            controller=self.mock_controller,
            meter=self.mock_meter,
            wallbox=self.mock_wallbox,
            relay=self.mock_relay,
            car=self.mock_car,
        )
        self.publisher._state_restore_timeout_s = 0  # skip wait in tests

    @patch("pvcontrol.mqtt.aiomqtt.Client")
    async def test_start_subscribes_to_command_topics(self, mock_client_cls: Any):
        """Verify command topics are subscribed on connect."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.publish = AsyncMock()
        mock_client.subscribe = AsyncMock()
        mock_client_cls.return_value = mock_client

        await self.publisher.start()

        # Should subscribe to all 3 command topics
        expected_topics = [
            "pvcontrol/controller/desired_mode/set",
            "pvcontrol/controller/phase_mode/set",
            "pvcontrol/controller/desired_priority/set",
        ]
        subscribed_topics = [call.args[0] for call in mock_client.subscribe.call_args_list]
        for topic in expected_topics:
            self.assertIn(topic, subscribed_topics, f"Topic {topic} not subscribed")

    @patch("pvcontrol.mqtt.aiomqtt.Client")
    async def test_discovery_includes_command_topic_for_select(self, mock_client_cls: Any):
        """Discovery payload for select entities should include command_topic."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.publish = AsyncMock()
        mock_client_cls.return_value = mock_client

        await self.publisher.start()

        # Find select entity discovery calls
        select_discovery_calls = []
        for call in mock_client.publish.call_args_list[1:]:  # skip online status
            topic = call.args[0] if call.args else call.kwargs.get("topic", "")
            if "/select/" in topic:
                payload_str = call.kwargs.get("payload") or call.args[1]
                payload = json.loads(payload_str)
                select_discovery_calls.append(payload)

        self.assertEqual(len(select_discovery_calls), 3)
        for payload in select_discovery_calls:
            self.assertIn("command_topic", payload)
            self.assertTrue(payload["command_topic"].startswith("pvcontrol/controller/"))

    @patch("pvcontrol.mqtt.aiomqtt.Client")
    async def test_message_handler_sets_desired_mode(self, mock_client_cls: Any):
        """Message handler should call set_desired_mode for desired_mode command."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.publish = AsyncMock()
        mock_client.subscribe = AsyncMock()
        mock_client_cls.return_value = mock_client

        # Simulate receiving a message on the desired_mode command topic (no state message)
        async def mock_messages():
            yield MagicMock(payload=b"PV_ONLY", topic="pvcontrol/controller/desired_mode/set")

        mock_client.messages = mock_messages()

        await self.publisher.start()
        # Give message handler time to process
        await asyncio.sleep(0.01)

        self.mock_controller.set_desired_mode.assert_called_with(ChargeMode.PV_ONLY)

    @patch("pvcontrol.mqtt.aiomqtt.Client")
    async def test_message_handler_sets_phase_mode(self, mock_client_cls: Any):
        """Message handler should call set_phase_mode for phase_mode command."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.publish = AsyncMock()
        mock_client.subscribe = AsyncMock()
        mock_client_cls.return_value = mock_client

        async def mock_messages():
            yield MagicMock(payload=b"CHARGE_1P", topic="pvcontrol/controller/phase_mode/set")

        mock_client.messages = mock_messages()

        await self.publisher.start()
        await asyncio.sleep(0.01)

        self.mock_controller.set_phase_mode.assert_called_with(PhaseMode.CHARGE_1P)

    @patch("pvcontrol.mqtt.aiomqtt.Client")
    async def test_message_handler_sets_desired_priority(self, mock_client_cls: Any):
        """Message handler should call set_desired_priority for desired_priority command."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.publish = AsyncMock()
        mock_client.subscribe = AsyncMock()
        mock_client_cls.return_value = mock_client

        async def mock_messages():
            yield MagicMock(payload=b"CAR", topic="pvcontrol/controller/desired_priority/set")

        mock_client.messages = mock_messages()

        await self.publisher.start()
        await asyncio.sleep(0.01)

        self.mock_controller.set_desired_priority.assert_called_with(Priority.CAR)

    @patch("pvcontrol.mqtt.aiomqtt.Client")
    async def test_message_handler_ignores_disabled_phase_mode(self, mock_client_cls: Any):
        """Message handler should ignore DISABLED phase_mode (consistent with restore_state)."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.publish = AsyncMock()
        mock_client.subscribe = AsyncMock()
        mock_client_cls.return_value = mock_client

        async def mock_messages():
            yield MagicMock(payload=b"DISABLED", topic="pvcontrol/controller/phase_mode/set")

        mock_client.messages = mock_messages()

        await self.publisher.start()
        await asyncio.sleep(0.01)

        self.mock_controller.set_phase_mode.assert_not_called()

    @patch("pvcontrol.mqtt.aiomqtt.Client")
    async def test_message_handler_invalid_value_logs_warning(self, mock_client_cls: Any):
        """Message handler should log warning for invalid enum values."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.publish = AsyncMock()
        mock_client.subscribe = AsyncMock()
        mock_client_cls.return_value = mock_client

        async def mock_messages():
            yield MagicMock(payload=b"INVALID_MODE", topic="pvcontrol/controller/desired_mode/set")

        mock_client.messages = mock_messages()

        with self.assertLogs("pvcontrol.mqtt", level="WARNING") as logs:
            await self.publisher.start()
            await asyncio.sleep(0.01)

        # Log includes the full topic suffix as prefix
        self.assertTrue(any("Invalid controller/desired_mode/set value" in msg for msg in logs.output))
        self.mock_controller.set_desired_mode.assert_not_called()

    @patch("pvcontrol.mqtt.aiomqtt.Client")
    async def test_stop_cancels_message_handler(self, mock_client_cls: Any):
        """Stop should cancel the message handler task."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.publish = AsyncMock()
        mock_client.subscribe = AsyncMock()
        mock_client_cls.return_value = mock_client

        # Create an async generator that waits forever (like a real MQTT connection)
        async def mock_messages():
            await asyncio.Event().wait()
            yield  # make it a generator

        mock_client.messages = mock_messages()

        await self.publisher.start()
        message_task = self.publisher._message_task
        self.assertIsNotNone(message_task)
        assert message_task is not None
        self.assertFalse(message_task.done())

        await self.publisher.stop()

        self.assertTrue(message_task.done())

    @patch("pvcontrol.mqtt.aiomqtt.Client")
    async def test_reconnect_restarts_message_handler(self, mock_client_cls: Any):
        """Message handler should restart after reconnection."""
        # Create two different mock clients to simulate disconnect/reconnect
        mock_client1 = AsyncMock()
        mock_client1.__aenter__ = AsyncMock(return_value=mock_client1)
        mock_client1.__aexit__ = AsyncMock(return_value=None)
        mock_client1.publish = AsyncMock()
        mock_client1.subscribe = AsyncMock()
        mock_client1.messages = AsyncMock()  # empty async iterator

        mock_client2 = AsyncMock()
        mock_client2.__aenter__ = AsyncMock(return_value=mock_client2)
        mock_client2.__aexit__ = AsyncMock(return_value=None)
        mock_client2.publish = AsyncMock()
        mock_client2.subscribe = AsyncMock()
        mock_client2.messages = AsyncMock()

        # First call returns client1, second returns client2
        mock_client_cls.side_effect = [mock_client1, mock_client2]

        await self.publisher.start()
        self.assertIsNotNone(self.publisher._message_task)

        # Simulate disconnection and reconnection
        self.publisher._client = None
        await self.publisher.publish_state()
        self.publisher._next_reconnect_at = 0  # Force immediate retry

        await self.publisher._try_reconnect()

        # Message handler task should be restarted (new task)
        self.assertIsNotNone(self.publisher._message_task)
