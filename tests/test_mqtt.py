import json
import unittest
from typing import Any, final, override
from unittest.mock import AsyncMock, MagicMock, patch

from pvcontrol.chargecontroller import ChargeMode, PhaseMode, Priority
from pvcontrol.mqtt import ENTITY_DEFINITIONS, MqttConfig, MqttPublisher
from pvcontrol.wallbox import CarStatus, WbError


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
            self.assertIn(entity.component, ("sensor", "binary_sensor"))
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
        self.publisher = MqttPublisher(self.config, "1.0.0")

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

        await self.publisher.start()
        self.assertIsNone(self.publisher._client)

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

    async def test_publish_state_without_connection_does_not_crash(self):
        self.publisher._client = None
        # Should not raise even without connection (reconnect also fails silently)
        with patch.object(self.publisher, "_try_reconnect", new_callable=AsyncMock):
            await self.publisher.publish_state()

    def test_build_state_converts_int_enums(self):
        deps = MagicMock()
        deps.version = "1.0.0"

        controller_data = MagicMock()
        controller_data.mode = ChargeMode.PV_ONLY
        controller_data.desired_mode = ChargeMode.PV_ONLY
        controller_data.phase_mode = PhaseMode.AUTO
        controller_data.priority = Priority.AUTO
        controller_data.desired_priority = Priority.AUTO
        controller_data.error = 0
        deps.controller.get_data.return_value = controller_data

        meter_data = MagicMock()
        meter_data.power_pv = 3000.0
        deps.meter.get_data.return_value = meter_data

        wallbox_data = MagicMock()
        wallbox_data.car_status = CarStatus.Charging
        wallbox_data.wb_error = WbError.OK
        deps.wallbox.get_data.return_value = wallbox_data

        relay_data = MagicMock()
        deps.relay.get_data.return_value = relay_data

        car_data = MagicMock()
        deps.car.get_data.return_value = car_data

        with patch("pvcontrol.api.PvcontrolResponse") as mock_response_cls:
            mock_response = MagicMock()
            mock_response.model_dump.return_value = {
                "version": "1.0.0",
                "controller": {"mode": "PV_ONLY", "error": 0},
                "meter": {"power_pv": 3000.0},
                "wallbox": {"car_status": 2, "wb_error": 0},
                "relay": {},
                "car": {},
            }
            mock_response_cls.return_value = mock_response

            state = self.publisher._build_state(deps)

        self.assertEqual("Charging", state["wallbox"]["car_status"])
        self.assertEqual("OK", state["wallbox"]["wb_error"])

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
