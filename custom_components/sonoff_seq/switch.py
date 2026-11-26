"""Virtual fixed ON/OFF wall switch."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import SonoffSeqDeviceState, SonoffSeqManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one persistent virtual wall switch."""
    manager: SonoffSeqManager = hass.data[DOMAIN]
    state: SonoffSeqDeviceState = entry.runtime_data
    async_add_entities([SonoffVirtualWallSwitch(manager, state)])


class SonoffVirtualWallSwitch(SwitchEntity, RestoreEntity):
    """Represent S1/S2 as a persistent fixed ON/OFF rocker state.

    This entity does NOT operate the physical MINIR4M relay.
    """

    _attr_has_entity_name = True
    _attr_name = "Wandschalter"
    _attr_icon = "mdi:light-switch"
    _attr_should_poll = False

    def __init__(
        self,
        manager: SonoffSeqManager,
        state: SonoffSeqDeviceState,
    ) -> None:
        self._manager = manager
        self._state = state
        self._attr_unique_id = f"{state.device_id}_wall_switch"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, state.device_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=state.name,
        )

    @property
    def is_on(self) -> bool:
        """Return the virtual rocker state."""
        return self._state.virtual_on

    @property
    def extra_state_attributes(self) -> dict[str, str | bool]:
        """Expose diagnostics."""
        return {
            "device_id": self._state.device_id,
            "source": "ewelink_seq_virtual_state",
            "virtual_state": True,
        }

    async def async_added_to_hass(self) -> None:
        """Restore the last state and subscribe to live updates."""
        await super().async_added_to_hass()

        restored = await self.async_get_last_state()
        if restored is not None and restored.state in (STATE_ON, STATE_OFF):
            self._state.virtual_on = restored.state == STATE_ON
            self._state.virtual_initialized = True
        elif not self._state.virtual_initialized:
            self._state.virtual_on = False
            self._state.virtual_initialized = True

        self.async_on_remove(
            self._manager.async_subscribe(
                self._state.device_id,
                self._handle_update,
            )
        )
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        """Manually synchronise the virtual rocker to ON."""
        self._manager.async_set_virtual_state(self._state.device_id, True)

    async def async_turn_off(self, **kwargs) -> None:
        """Manually synchronise the virtual rocker to OFF."""
        self._manager.async_set_virtual_state(self._state.device_id, False)

    @callback
    def _handle_update(self) -> None:
        """Write an updated state."""
        self.async_write_ha_state()
