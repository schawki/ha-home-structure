"""Home Structure: which spaces of a home are adjacent, what separates them, and what the opening sensors say.

It describes the home and nothing else (no sound, light or heat): other integrations decide what a door or a wall means for them."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.typing import ConfigType

from . import structure
from .const import DOMAIN, PLATFORMS

SERVICE_GET_STRUCTURE = "get_structure"
CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def get_structure(call: ServiceCall) -> dict:
        entries = [e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED]
        if not entries:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_loaded")
        return structure.current(hass, entries[0])

    hass.services.async_register(DOMAIN, SERVICE_GET_STRUCTURE, get_structure, supports_response=SupportsResponse.ONLY)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
