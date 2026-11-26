"""Config flow for SONOFF eWeLink Sequence Listener."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_NAME

from .const import CONF_DEVICE_ID, DOMAIN

_DEVICE_ID_RE = re.compile(r"^[0-9A-Za-z]{10,32}$")


class SonoffSeqConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure one SONOFF/eWeLink relay."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual device setup."""
        errors: dict[str, str] = {}

        if user_input is not None:
            device_id = str(user_input[CONF_DEVICE_ID]).strip().lower()
            name = str(user_input[CONF_NAME]).strip()

            if not _DEVICE_ID_RE.fullmatch(device_id):
                errors[CONF_DEVICE_ID] = "invalid_device_id"
            elif not name:
                errors[CONF_NAME] = "name_required"
            else:
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=name,
                    data={CONF_DEVICE_ID: device_id},
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DEVICE_ID,
                    default=(
                        user_input.get(CONF_DEVICE_ID, "")
                        if user_input
                        else ""
                    ),
                ): str,
                vol.Required(
                    CONF_NAME,
                    default=(
                        user_input.get(CONF_NAME, "")
                        if user_input
                        else ""
                    ),
                ): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
