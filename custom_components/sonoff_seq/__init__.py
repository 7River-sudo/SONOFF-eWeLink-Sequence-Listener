"""SONOFF eWeLink Sequence Listener integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_DEVICE_ID, DOMAIN
from .coordinator import SonoffSeqDeviceState, SonoffSeqManager

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one configured relay."""
    manager: SonoffSeqManager = hass.data.setdefault(
        DOMAIN, SonoffSeqManager(hass)
    )

    device_id = str(entry.data[CONF_DEVICE_ID]).lower()
    state = await manager.async_add_device(
        entry_id=entry.entry_id,
        device_id=device_id,
        name=entry.title,
    )
    entry.runtime_data = state

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload one configured relay."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    manager: SonoffSeqManager | None = hass.data.get(DOMAIN)
    if manager is None:
        return True

    state: SonoffSeqDeviceState = entry.runtime_data
    manager.remove_device(state.device_id)

    if not manager.has_devices:
        await manager.async_stop()
        hass.data.pop(DOMAIN, None)

    return True
