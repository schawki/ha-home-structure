"""Home Structure: which spaces of a home are adjacent, what separates them, and what the opening sensors say.

It describes the home and nothing else (no sound, light or heat): other integrations decide what a door or a wall means for them."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.typing import ConfigType

from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig

from . import structure, websocket_api as panel_ws
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


PANEL_DIR = Path(__file__).parent / "frontend"
PANEL_FILE = "home-structure-panel.js"
PANEL_URL = "/home_structure_panel"
PANEL_PATH = "home-structure"


async def _async_register_panel(hass: HomeAssistant) -> None:
    """Sidebar panel (administrators only), once however many times the entry is reloaded."""
    if hass.data.get(f"{DOMAIN}_panel"):
        return
    hass.data[f"{DOMAIN}_panel"] = True
    panel_ws.async_register(hass)
    await hass.http.async_register_static_paths([StaticPathConfig(PANEL_URL, str(PANEL_DIR), cache_headers=False)])
    version = (PANEL_DIR / PANEL_FILE).stat().st_mtime_ns if (PANEL_DIR / PANEL_FILE).exists() else 0
    await panel_custom.async_register_panel(
        hass, webcomponent_name="home-structure-panel", frontend_url_path=PANEL_PATH, module_url=f"{PANEL_URL}/{PANEL_FILE}?v={version}",
        sidebar_title="Home Structure", sidebar_icon="mdi:floor-plan", require_admin=True, config={}, embed_iframe=False)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await _async_register_panel(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Entry deleted: take the panel out of the sidebar."""
    if hass.data.pop(f"{DOMAIN}_panel", None):
        frontend.async_remove_panel(hass, PANEL_PATH)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
