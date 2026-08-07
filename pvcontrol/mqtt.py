import asyncio
import dataclasses
import enum
import json
import logging
import time
import uuid
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import aiomqtt

from pvcontrol.car import Car
from pvcontrol.chargecontroller import ChargeController, ChargeMode, PhaseMode, Priority
from pvcontrol.meter import Meter
from pvcontrol.relay import PhaseRelay
from pvcontrol.wallbox import CarStatus, Wallbox, WbError

logger = logging.getLogger(__name__)


@dataclass
class MqttConfig:
    broker: str = "localhost"
    port: int = 1883
    username: str = ""
    password: str = ""
    topic_prefix: str = "pvcontrol"
    ha_discovery_prefix: str = "homeassistant"


@dataclass
class EntityDef:
    component: str
    object_id: str
    name: str
    value_template: str
    device_class: str | None = None
    state_class: str | None = None
    unit_of_measurement: str | None = None
    entity_category: str | None = None
    options: list[str] = field(default_factory=list)
    command_topic: str | None = None
    handler: Callable[[ChargeController, str], None] | None = None


ENTITY_DEFINITIONS: list[EntityDef] = [
    # Meter
    EntityDef(
        "sensor",
        "meter_power_pv",
        "PV Power",
        "{{ value_json.meter.power_pv | round(0) }}",
        device_class="power",
        state_class="measurement",
        unit_of_measurement="W",
    ),
    EntityDef(
        "sensor",
        "meter_power_consumption",
        "Consumption Power",
        "{{ value_json.meter.power_consumption | round(0) }}",
        device_class="power",
        state_class="measurement",
        unit_of_measurement="W",
    ),
    EntityDef(
        "sensor",
        "meter_power_grid",
        "Grid Power",
        "{{ value_json.meter.power_grid | round(0) }}",
        device_class="power",
        state_class="measurement",
        unit_of_measurement="W",
    ),
    EntityDef(
        "sensor",
        "meter_power_battery",
        "Battery Power",
        "{{ value_json.meter.power_battery | round(0) }}",
        device_class="power",
        state_class="measurement",
        unit_of_measurement="W",
    ),
    EntityDef(
        "sensor",
        "meter_soc_battery",
        "Battery SoC",
        "{{ value_json.meter.soc_battery | round(0) }}",
        device_class="battery",
        state_class="measurement",
        unit_of_measurement="%",
    ),
    EntityDef(
        "sensor",
        "meter_energy_consumption",
        "Energy Consumption",
        "{{ value_json.meter.energy_consumption | round(0) }}",
        device_class="energy",
        state_class="total_increasing",
        unit_of_measurement="Wh",
    ),
    EntityDef(
        "sensor",
        "meter_energy_consumption_grid",
        "Energy Consumption Grid",
        "{{ value_json.meter.energy_consumption_grid | round(0) }}",
        device_class="energy",
        state_class="total_increasing",
        unit_of_measurement="Wh",
    ),
    EntityDef(
        "sensor",
        "meter_energy_consumption_pv",
        "Energy Consumption PV",
        "{{ value_json.meter.energy_consumption_pv | round(0) }}",
        device_class="energy",
        state_class="total_increasing",
        unit_of_measurement="Wh",
    ),
    # Wallbox
    EntityDef(
        "sensor",
        "wallbox_car_status",
        "Car Status",
        "{{ value_json.wallbox.car_status }}",
        device_class="enum",
        options=[s.name for s in CarStatus],
    ),
    EntityDef(
        "sensor",
        "wallbox_max_current",
        "Max Current",
        "{{ value_json.wallbox.max_current }}",
        device_class="current",
        state_class="measurement",
        unit_of_measurement="A",
    ),
    EntityDef("binary_sensor", "wallbox_allow_charging", "Allow Charging", "{{ 'ON' if value_json.wallbox.allow_charging else 'OFF' }}"),
    EntityDef("sensor", "wallbox_phases_in", "Phases In", "{{ value_json.wallbox.phases_in }}", state_class="measurement"),
    EntityDef("sensor", "wallbox_phases_out", "Phases Out", "{{ value_json.wallbox.phases_out }}", state_class="measurement"),
    EntityDef(
        "sensor",
        "wallbox_power",
        "Wallbox Power",
        "{{ value_json.wallbox.power | round(0) }}",
        device_class="power",
        state_class="measurement",
        unit_of_measurement="W",
    ),
    EntityDef(
        "sensor",
        "wallbox_charged_energy",
        "Charged Energy",
        "{{ value_json.wallbox.charged_energy | round(0) }}",
        device_class="energy",
        state_class="total_increasing",
        unit_of_measurement="Wh",
    ),
    EntityDef(
        "sensor",
        "wallbox_total_energy",
        "Total Energy",
        "{{ value_json.wallbox.total_energy | round(0) }}",
        device_class="energy",
        state_class="total_increasing",
        unit_of_measurement="Wh",
    ),
    EntityDef(
        "sensor",
        "wallbox_temperature",
        "Wallbox Temperature",
        "{{ value_json.wallbox.temperature }}",
        device_class="temperature",
        state_class="measurement",
        unit_of_measurement="°C",
    ),
    # Relay
    EntityDef("binary_sensor", "relay_enabled", "Phase Relay Enabled", "{{ 'ON' if value_json.relay.enabled else 'OFF' }}"),
    EntityDef("sensor", "relay_phases", "Relay Phases", "{{ value_json.relay.phases }}", state_class="measurement"),
    # Controller
    EntityDef(
        "sensor",
        "controller_mode",
        "Charge Mode",
        "{{ value_json.controller.mode }}",
        device_class="enum",
        options=[m.value for m in ChargeMode],
    ),
    EntityDef(
        "select",
        "controller_desired_mode",
        "Desired Charge Mode",
        "{{ value_json.controller.desired_mode }}",
        device_class="enum",
        options=[m.value for m in ChargeMode],
        command_topic="controller/desired_mode/set",
        handler=lambda c, v: _validate_enum_and_set(v, ChargeMode, c.set_desired_mode, "controller/desired_mode/set"),
    ),
    EntityDef(
        "select",
        "controller_phase_mode",
        "Phase Mode",
        "{{ value_json.controller.phase_mode }}",
        device_class="enum",
        options=[m.value for m in PhaseMode],
        command_topic="controller/phase_mode/set",
        handler=lambda c, v: _validate_enum_and_set(
            v, PhaseMode, c.set_phase_mode, "controller/phase_mode/set", lambda m: m != PhaseMode.DISABLED
        ),
    ),
    EntityDef(
        "sensor",
        "controller_priority",
        "Priority",
        "{{ value_json.controller.priority }}",
        device_class="enum",
        options=[m.value for m in Priority],
    ),
    EntityDef(
        "select",
        "controller_desired_priority",
        "Desired Priority",
        "{{ value_json.controller.desired_priority }}",
        device_class="enum",
        options=[m.value for m in Priority],
        command_topic="controller/desired_priority/set",
        handler=lambda c, v: _validate_enum_and_set(v, Priority, c.set_desired_priority, "controller/desired_priority/set"),
    ),
    # Car
    EntityDef(
        "sensor",
        "car_soc",
        "Car SoC",
        "{{ value_json.car.soc | round(0) }}",
        device_class="battery",
        state_class="measurement",
        unit_of_measurement="%",
    ),
    EntityDef(
        "sensor",
        "car_cruising_range",
        "Car Cruising Range",
        "{{ value_json.car.cruising_range }}",
        device_class="distance",
        state_class="measurement",
        unit_of_measurement="km",
    ),
    EntityDef(
        "sensor",
        "car_mileage",
        "Car Mileage",
        "{{ value_json.car.mileage }}",
        device_class="distance",
        state_class="total_increasing",
        unit_of_measurement="km",
    ),
    # Diagnostics
    EntityDef(
        "sensor", "meter_error", "Meter Errors", "{{ value_json.meter.error }}", state_class="measurement", entity_category="diagnostic"
    ),
    EntityDef(
        "sensor",
        "wallbox_wb_error",
        "Wallbox Error",
        "{{ value_json.wallbox.wb_error }}",
        device_class="enum",
        entity_category="diagnostic",
        options=[e.name for e in WbError],
    ),
    EntityDef(
        "sensor",
        "wallbox_error",
        "Wallbox Error Count",
        "{{ value_json.wallbox.error }}",
        state_class="measurement",
        entity_category="diagnostic",
    ),
    EntityDef(
        "sensor", "relay_error", "Relay Errors", "{{ value_json.relay.error }}", state_class="measurement", entity_category="diagnostic"
    ),
    EntityDef(
        "sensor",
        "controller_error",
        "Controller Errors",
        "{{ value_json.controller.error }}",
        state_class="measurement",
        entity_category="diagnostic",
    ),
    EntityDef("sensor", "car_error", "Car Errors", "{{ value_json.car.error }}", state_class="measurement", entity_category="diagnostic"),
    EntityDef(
        "sensor",
        "car_data_captured_at",
        "Car Data Captured At",
        "{{ value_json.car.data_captured_at }}",
        device_class="timestamp",
        entity_category="diagnostic",
    ),
]


def _json_default(o: Any) -> Any:
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, enum.Enum):
        return o.value
    raise TypeError(repr(o))


def _validate_enum_and_set(
    value_str: str,
    enum_cls: type[enum.Enum],
    setter: Callable[[Any], None],
    log_prefix: str,
    filter_fn: Callable[[enum.Enum], bool] | None = None,
) -> None:
    """Validate string as enum, apply optional filter, and call setter."""
    try:
        value = enum_cls(value_str)
    except ValueError:
        logger.warning("Invalid %s value: %r", log_prefix, value_str)
        return
    if filter_fn is not None and not filter_fn(value):
        logger.info("Ignoring %s for %s (filtered)", value, log_prefix)
        return
    setter(value)


# Command topic handlers for live MQTT commands and state restore
# Maps command topic (e.g., "controller/desired_mode/set") to handler function
_COMMAND_HANDLERS: dict[str, Callable[[ChargeController, str], None]] = {
    e.command_topic: e.handler for e in ENTITY_DEFINITIONS if e.command_topic and e.handler
}


class MqttPublisher:
    def __init__(
        self,
        config: MqttConfig,
        version: str,
        controller: ChargeController,
        meter: Meter,
        wallbox: Wallbox,
        relay: PhaseRelay,
        car: Car,
    ):
        self._config = config
        self._version = version
        self._controller = controller
        self._meter = meter
        self._wallbox = wallbox
        self._relay = relay
        self._car = car
        self._client: aiomqtt.Client | None = None
        self._next_reconnect_at: float = 0
        self._client_id: str = uuid.uuid4().hex[:8]
        self._connected = asyncio.Event()  # signals when client is connected
        self._retained_state: dict[str, Any] | None = None
        self._state_received = asyncio.Event()  # signals when retained state message received
        self._state_restore_timeout_s: float = 2.0  # tests can set to 0 to skip waiting
        # Use module-level command handlers (single source of truth)
        self._command_handlers = _COMMAND_HANDLERS
        # Message handler runs as background task after connection
        self._message_task: asyncio.Task | None = None
        # Retry window (seconds) for the initial connect; tests set it to 0 to disable retrying.
        self._retry_window_s: float = 300

    async def start(self) -> None:
        """Connect to the broker, retrying failed attempts until the retry window expires."""
        deadline = time.time() + self._retry_window_s
        while not await self._connect_once():
            remaining = deadline - time.time()
            if remaining <= 0:
                logger.error("MQTT connection failed after %.0fs retry window", self._retry_window_s)
                return
            logger.warning("MQTT connection attempt failed, %.0fs remaining of retry window", remaining)
            await asyncio.sleep(min(remaining, 10))
        # Subscribe to state topic BEFORE starting message handler to catch retained message
        if self._client:
            await self._client.subscribe(f"{self._config.topic_prefix}/state")
        # Start message handler as background task
        self._message_task = asyncio.create_task(self._message_handler())
        # Wait for retained state message (configurable timeout; 0 = skip waiting)
        if self._state_restore_timeout_s > 0:
            try:
                await asyncio.wait_for(self._state_received.wait(), timeout=self._state_restore_timeout_s)
                if self._retained_state is not None:
                    self._apply_controller_state(self._retained_state)
            except TimeoutError:
                logger.info("No retained MQTT state found, starting with defaults")
        # Unsubscribe from state topic - we only needed it for the retained message at startup
        if self._client:
            try:
                await self._client.unsubscribe(f"{self._config.topic_prefix}/state")
            except Exception:
                logger.debug("Failed to unsubscribe from state topic")

    async def stop(self) -> None:
        # Stop message handler task
        if self._message_task:
            self._message_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._message_task
            self._message_task = None

        if self._client:
            try:
                await self._client.publish(f"{self._config.topic_prefix}/status", payload="offline", retain=True)
            except Exception:
                pass
            await self._disconnect()

    async def publish_state(self) -> None:
        if self._client is None:
            await self._try_reconnect()
        if self._client is None:
            return
        try:
            state = {
                "version": self._version,
                "controller": dataclasses.asdict(self._controller.get_data()),
                "meter": dataclasses.asdict(self._meter.get_data()),
                "wallbox": dataclasses.asdict(self._wallbox.get_data()),
                "relay": dataclasses.asdict(self._relay.get_data()),
                "car": dataclasses.asdict(self._car.get_data()),
            }
            state["wallbox"]["car_status"] = CarStatus(state["wallbox"]["car_status"]).name
            state["wallbox"]["wb_error"] = WbError(state["wallbox"]["wb_error"]).name

            payload = json.dumps(state, default=_json_default)
            await self._client.publish(f"{self._config.topic_prefix}/state", payload=payload, retain=True)
        except aiomqtt.MqttError as e:
            logger.warning("MQTT publish failed: %s", e)
            await self._disconnect()
        except Exception:
            logger.exception("MQTT publish error")

    async def _connect_once(self) -> bool:
        """Attempt a single connection. Returns True on success, False on failure."""
        try:
            self._client = aiomqtt.Client(
                hostname=self._config.broker,
                port=self._config.port,
                username=self._config.username or None,
                password=self._config.password or None,
                identifier=f"pvcontrol-{self._client_id}",
                will=aiomqtt.Will(
                    topic=f"{self._config.topic_prefix}/status",
                    payload="offline",
                    retain=True,
                ),
            )
            await self._client.__aenter__()
            await self._client.publish(f"{self._config.topic_prefix}/status", payload="online", retain=True)
            await self._publish_discovery()
            # Subscribe to command topics for MQTT control
            for topic in self._command_handlers:
                await self._client.subscribe(f"{self._config.topic_prefix}/{topic}")
            self._next_reconnect_at = 0
            self._connected.set()  # Signal that we're connected
            logger.info("MQTT connected to %s:%d", self._config.broker, self._config.port)
            return True
        except Exception:
            await self._disconnect()
            return False

    async def _try_reconnect(self) -> None:
        now = time.time()
        if now < self._next_reconnect_at:
            return
        self._next_reconnect_at = now + 60
        if await self._connect_once():
            # Restart message handler after successful reconnection
            if self._message_task and not self._message_task.done():
                self._message_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._message_task
            self._message_task = asyncio.create_task(self._message_handler())

    async def _disconnect(self) -> None:
        if self._client:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception:
                pass
            self._client = None
        self._connected.clear()  # Signal that we're disconnected

    async def _publish_discovery(self) -> None:
        if self._client is None:
            return
        device_info = {
            "identifiers": ["pvcontrol"],
            "name": "PV Control",
            "manufacturer": "pv-control",
            "sw_version": self._version,
        }
        availability = {
            "topic": f"{self._config.topic_prefix}/status",
            "payload_available": "online",
            "payload_not_available": "offline",
        }
        for entity in ENTITY_DEFINITIONS:
            topic = f"{self._config.ha_discovery_prefix}/{entity.component}/pvcontrol_{entity.object_id}/config"
            payload: dict[str, Any] = {
                "name": entity.name,
                "unique_id": f"pvcontrol_{entity.object_id}",
                "object_id": f"pvcontrol_{entity.object_id}",
                "state_topic": f"{self._config.topic_prefix}/state",
                "value_template": entity.value_template,
                "device": device_info,
                "availability": availability,
            }
            if entity.device_class:
                payload["device_class"] = entity.device_class
            if entity.state_class:
                payload["state_class"] = entity.state_class
            if entity.unit_of_measurement:
                payload["unit_of_measurement"] = entity.unit_of_measurement
            if entity.entity_category:
                payload["entity_category"] = entity.entity_category
            if entity.options:
                payload["options"] = entity.options
            if entity.command_topic:
                payload["command_topic"] = f"{self._config.topic_prefix}/{entity.command_topic}"
            await self._client.publish(topic, payload=json.dumps(payload), retain=True)

    async def _message_handler(self) -> None:
        """Handle incoming MQTT command messages."""
        # Wait until connected
        await self._connected.wait()
        assert self._client is not None  # _connected.set() only called after successful connect
        # Hoist prefix computation outside the hot loop
        prefix = f"{self._config.topic_prefix}/"
        prefix_len = len(prefix)
        state_topic = f"{self._config.topic_prefix}/state"
        try:
            async for msg in self._client.messages:
                topic = str(msg.topic)
                payload = msg.payload.decode() if isinstance(msg.payload, bytes) else str(msg.payload)
                logger.info("Received MQTT command: %s = %s", topic, payload)

                # Handle retained state message for startup restore
                if topic == state_topic:
                    try:
                        self._retained_state = json.loads(payload)
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse retained state payload: %s", payload)
                    # Signal that retained state was received
                    self._state_received.set()
                    continue  # Don't process state topic as command

                # Extract topic suffix (after prefix/) for command topics
                if topic.startswith(prefix):
                    topic_suffix = topic[prefix_len:]
                    handler = self._command_handlers.get(topic_suffix)
                    if handler:
                        handler(self._controller, payload)
        except asyncio.CancelledError:
            logger.debug("MQTT message handler cancelled")
            raise
        except Exception:
            logger.exception("MQTT message handler error")

    def _apply_controller_state(self, payload: dict[str, Any]) -> None:
        controller_state = payload.get("controller", {})
        for key, value_str in controller_state.items():
            topic = f"controller/{key}/set"
            handler = _COMMAND_HANDLERS.get(topic)
            if handler:
                handler(self._controller, value_str)
                logger.info("Restored %s: %s", key, value_str)
