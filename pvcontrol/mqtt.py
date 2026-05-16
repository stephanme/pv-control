import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

import aiomqtt

from pvcontrol.chargecontroller import ChargeMode, PhaseMode, Priority
from pvcontrol.wallbox import CarStatus, WbError

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
        "sensor",
        "controller_desired_mode",
        "Desired Charge Mode",
        "{{ value_json.controller.desired_mode }}",
        device_class="enum",
        options=[m.value for m in ChargeMode],
    ),
    EntityDef(
        "sensor",
        "controller_phase_mode",
        "Phase Mode",
        "{{ value_json.controller.phase_mode }}",
        device_class="enum",
        options=[m.value for m in PhaseMode],
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
        "sensor",
        "controller_desired_priority",
        "Desired Priority",
        "{{ value_json.controller.desired_priority }}",
        device_class="enum",
        options=[m.value for m in Priority],
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


class MqttPublisher:
    def __init__(self, config: MqttConfig, version: str):
        self._config = config
        self._version = version
        self._client: aiomqtt.Client | None = None
        self._next_reconnect_at: float = 0

    async def start(self) -> None:
        try:
            self._client = aiomqtt.Client(
                hostname=self._config.broker,
                port=self._config.port,
                username=self._config.username or None,
                password=self._config.password or None,
                identifier="pvcontrol",
                will=aiomqtt.Will(
                    topic=f"{self._config.topic_prefix}/status",
                    payload="offline",
                    retain=True,
                ),
            )
            await self._client.__aenter__()
            await self._client.publish(f"{self._config.topic_prefix}/status", payload="online", retain=True)
            await self._publish_discovery()
            self._next_reconnect_at = 0
            logger.info(f"MQTT connected to {self._config.broker}:{self._config.port}")
        except Exception:
            logger.exception("MQTT connection failed")
            await self._disconnect()

    async def stop(self) -> None:
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
            import pvcontrol.api as api

            response = await api.get_root()
            state = response.model_dump(mode="json")
            state["wallbox"]["car_status"] = CarStatus(state["wallbox"]["car_status"]).name
            state["wallbox"]["wb_error"] = WbError(state["wallbox"]["wb_error"]).name

            payload = json.dumps(state)
            await self._client.publish(f"{self._config.topic_prefix}/state", payload=payload, retain=True)
        except aiomqtt.MqttError as e:
            logger.warning(f"MQTT publish failed: {e}")
            await self._disconnect()
        except Exception:
            logger.exception("MQTT publish error")

    async def _disconnect(self) -> None:
        if self._client:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception:
                pass
            self._client = None

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
            await self._client.publish(topic, payload=json.dumps(payload), retain=True)

    async def _try_reconnect(self) -> None:
        import time

        now = time.monotonic()
        if now < self._next_reconnect_at:
            return
        self._next_reconnect_at = now + 60
        await self.start()

    async def restore_state(self) -> None:
        if self._client is None:
            return
        topic = f"{self._config.topic_prefix}/state"
        try:
            await self._client.subscribe(topic)
            msg = await asyncio.wait_for(anext(self._client.messages), timeout=2.0)
            payload = json.loads(msg.payload)
            await self._apply_controller_state(payload)
        except TimeoutError:
            logger.info("No retained MQTT state found, starting with defaults")
        except Exception:
            logger.exception("Failed to restore state from MQTT")
        finally:
            try:
                if self._client is not None:
                    await self._client.unsubscribe(topic)
            except Exception:
                pass

    async def _apply_controller_state(self, payload: dict[str, Any]) -> None:
        import pvcontrol.api as api

        controller_state = payload.get("controller", {})
        if desired_mode := controller_state.get("desired_mode"):
            try:
                await api.put_controller_desired_mode(ChargeMode(desired_mode))
                logger.info(f"Restored desired_mode: {desired_mode}")
            except ValueError:
                logger.warning(f"Ignoring invalid desired_mode from retained state: {desired_mode!r}")
        if phase_mode := controller_state.get("phase_mode"):
            try:
                await api.put_controller_phase_mode(PhaseMode(phase_mode))
                logger.info(f"Restored phase_mode: {phase_mode}")
            except ValueError:
                logger.warning(f"Ignoring invalid phase_mode from retained state: {phase_mode!r}")
        if desired_priority := controller_state.get("desired_priority"):
            try:
                await api.put_controller_desired_priority(Priority(desired_priority))
                logger.info(f"Restored desired_priority: {desired_priority}")
            except ValueError:
                logger.warning(f"Ignoring invalid desired_priority from retained state: {desired_priority!r}")
