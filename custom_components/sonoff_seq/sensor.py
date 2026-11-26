"""Diagnostic sequence sensor for SONOFF eWeLink Sequence Listener."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DOMAIN, EVENT_SEQ_CHANGE, MANUFACTURER, MODEL
from .coordinator import SonoffSeqDeviceState, SonoffSeqManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one diagnostic sequence sensor."""
    manager: SonoffSeqManager = hass.data[DOMAIN]
    state: SonoffSeqDeviceState = entry.runtime_data
    async_add_entities([SonoffSeqSensor(manager, state)])


class SonoffSeqSensor(SensorEntity):
    """Show the last observed eWeLink sequence number."""

    _attr_has_entity_name = True
    _attr_name = "Sequence"
    _attr_icon = "mdi:counter"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(
        self,
        manager: SonoffSeqManager,
        state: SonoffSeqDeviceState,
    ) -> None:
        self._manager = manager
        self._state = state
        self._attr_unique_id = f"{state.device_id}_sequence"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, state.device_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=state.name,
        )

    @property
    def native_value(self) -> StateType:
        """Return the current sequence value."""
        if self._state.seq is None:
            return None
        try:
            return int(self._state.seq)
        except ValueError:
            return self._state.seq

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Expose useful diagnostics."""
        return {
            "device_id": self._state.device_id,
            "previous_seq": self._state.previous_seq,
            "last_seen": (
                self._state.last_seen.isoformat()
                if self._state.last_seen is not None
                else None
            ),
            "event_type": EVENT_SEQ_CHANGE,
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to manager updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._manager.async_subscribe(
                self._state.device_id,
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        """Write updated state to Home Assistant."""
        self.async_write_ha_state()
