"""Shared mDNS listener for SONOFF/eWeLink sequence updates."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import time
from typing import Any

from zeroconf import ServiceStateChange, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo

from homeassistant.components import zeroconf
from homeassistant.core import HomeAssistant, callback

from .const import (
    EVENT_SEQ_CHANGE,
    RECONNECT_BASELINE_SECONDS,
    SERVICE_PREFIX,
    SERVICE_TYPE,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class SonoffSeqDeviceState:
    """Runtime state for one configured relay."""

    entry_id: str
    device_id: str
    name: str
    seq: str | None = None
    previous_seq: str | None = None
    last_seen: datetime | None = None
    removed_at: float | None = None
    virtual_on: bool = False
    virtual_initialized: bool = False
    listeners: set[Callable[[], None]] = field(default_factory=set)


class SonoffSeqManager:
    """One shared Zeroconf browser for all configured relays."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.devices: dict[str, SonoffSeqDeviceState] = {}
        self._browser: AsyncServiceBrowser | None = None
        self._aiozc = None
        self._start_lock = asyncio.Lock()

    async def async_start(self) -> None:
        """Start the single shared eWeLink browser."""
        async with self._start_lock:
            if self._browser is not None:
                return

            self._aiozc = await zeroconf.async_get_async_instance(self.hass)
            self._browser = AsyncServiceBrowser(
                self._aiozc.zeroconf,
                SERVICE_TYPE,
                handlers=[self._service_state_changed],
            )
            _LOGGER.debug("Started shared %s browser", SERVICE_TYPE)

    async def async_stop(self) -> None:
        """Stop the browser."""
        async with self._start_lock:
            if self._browser is not None:
                await self._browser.async_cancel()
                self._browser = None
            self._aiozc = None

    async def async_add_device(
        self, entry_id: str, device_id: str, name: str
    ) -> SonoffSeqDeviceState:
        """Register one device and establish its current sequence as baseline."""
        device_id = device_id.lower()
        state = SonoffSeqDeviceState(
            entry_id=entry_id,
            device_id=device_id,
            name=name,
        )
        self.devices[device_id] = state

        await self.async_start()
        await self._async_resolve(
            self._service_name(device_id),
            force_baseline=True,
        )
        return state

    def remove_device(self, device_id: str) -> None:
        """Remove one configured device from the shared listener."""
        self.devices.pop(device_id.lower(), None)

    @property
    def has_devices(self) -> bool:
        """Return whether at least one configured device remains."""
        return bool(self.devices)

    @callback
    def async_subscribe(
        self, device_id: str, listener: Callable[[], None]
    ) -> Callable[[], None]:
        """Subscribe an entity to state changes."""
        state = self.devices[device_id.lower()]
        state.listeners.add(listener)

        @callback
        def _unsubscribe() -> None:
            state.listeners.discard(listener)

        return _unsubscribe

    @callback
    def _notify(self, state: SonoffSeqDeviceState) -> None:
        """Notify all entities for one device."""
        for listener in tuple(state.listeners):
            listener()

    @staticmethod
    def _service_name(device_id: str) -> str:
        return f"eWeLink_{device_id}.{SERVICE_TYPE}"

    @staticmethod
    def _device_id_from_service(name: str) -> str | None:
        first_label = name.split(".", 1)[0].lower()
        if not first_label.startswith(SERVICE_PREFIX):
            return None
        return first_label[len(SERVICE_PREFIX):]

    @callback
    def _service_state_changed(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        """Handle Zeroconf add/update/remove callbacks."""
        device_id = self._device_id_from_service(name)
        if device_id is None or device_id not in self.devices:
            return

        state = self.devices[device_id]

        if state_change is ServiceStateChange.Removed:
            state.removed_at = time.monotonic()
            return

        self.hass.async_create_task(
            self._async_resolve(name),
            f"sonoff_seq_{device_id}",
        )

    async def _async_resolve(
        self, name: str, force_baseline: bool = False
    ) -> None:
        """Resolve TXT properties and process an unencrypted seq value."""
        if self._aiozc is None:
            return

        device_id = self._device_id_from_service(name)
        if device_id is None:
            return

        state = self.devices.get(device_id)
        if state is None:
            return

        info = AsyncServiceInfo(SERVICE_TYPE, name)
        if not await info.async_request(self._aiozc.zeroconf, 2000):
            _LOGGER.debug("Could not resolve %s", name)
            return

        props = self._decode_properties(info.properties)
        seq = props.get("seq")
        if seq is None:
            return

        now = datetime.now(timezone.utc)
        state.last_seen = now

        # A real offline/reconnect cycle should not toggle a lamp just because
        # the firmware publishes a new baseline. Very short remove/add cycles
        # are common during mDNS updates and are treated as normal updates.
        reconnect_baseline = False
        if state.removed_at is not None:
            reconnect_baseline = (
                time.monotonic() - state.removed_at
                >= RECONNECT_BASELINE_SECONDS
            )
            state.removed_at = None

        if force_baseline or state.seq is None or reconnect_baseline:
            state.previous_seq = state.seq
            state.seq = seq
            self._notify(state)
            _LOGGER.debug(
                "Baseline for %s (%s): seq=%s",
                state.name,
                state.device_id,
                seq,
            )
            return

        # IPv4/IPv6 duplicates and repeated advertisements carry the same seq.
        if seq == state.seq:
            return

        old_seq = state.seq
        state.previous_seq = old_seq
        state.seq = seq

        # We cannot decrypt the external switch direction. For a normal
        # rocker switch, keep a persistent virtual ON/OFF state and flip it
        # for every confirmed sequence change.
        state.virtual_on = not state.virtual_on
        state.virtual_initialized = True

        self._notify(state)

        _LOGGER.debug(
            "Sequence change for %s (%s): %s -> %s; virtual switch=%s",
            state.name,
            state.device_id,
            old_seq,
            seq,
            "on" if state.virtual_on else "off",
        )

        self.hass.bus.async_fire(
            EVENT_SEQ_CHANGE,
            {
                "entry_id": state.entry_id,
                "device_id": state.device_id,
                "name": state.name,
                "old_seq": old_seq,
                "seq": seq,
                "switch_state": "on" if state.virtual_on else "off",
            },
        )

    @callback
    def async_set_virtual_state(self, device_id: str, is_on: bool) -> None:
        """Manually synchronise the virtual rocker state."""
        state = self.devices[device_id.lower()]
        if state.virtual_on == is_on and state.virtual_initialized:
            return

        state.virtual_on = is_on
        state.virtual_initialized = True
        self._notify(state)

        _LOGGER.debug(
            "Virtual switch for %s (%s) manually synchronised to %s",
            state.name,
            state.device_id,
            "on" if is_on else "off",
        )

    @staticmethod
    def _decode_properties(
        properties: dict[bytes | str, bytes | str | None] | None,
    ) -> dict[str, str]:
        """Decode Zeroconf TXT properties."""
        if not properties:
            return {}

        result: dict[str, str] = {}
        for key, value in properties.items():
            if isinstance(key, bytes):
                key_text = key.decode(errors="ignore")
            else:
                key_text = str(key)

            if value is None:
                value_text = ""
            elif isinstance(value, bytes):
                value_text = value.decode(errors="ignore")
            else:
                value_text = str(value)

            result[key_text] = value_text

        return result
