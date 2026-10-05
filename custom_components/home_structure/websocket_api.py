"""WebSocket commands of the editor panel (administrators only): read everything the editor needs, and save the structure."""
from __future__ import annotations

import copy
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from . import model, structure
from .const import DOMAIN, PERMANENT, SENSOR_DOMAINS, ROOM_TYPES, SEPARATION_TYPES, SHUTTER_HOSTS, ZONE_IN_HOME, ZONE_KINDS


def _entry(hass: HomeAssistant) -> ConfigEntry | None:
    entries = hass.config_entries.async_entries(DOMAIN)
    return entries[0] if entries else None


def _options(entry: ConfigEntry) -> dict:
    return copy.deepcopy({"zones": [], "connections": [], "excluded_areas": [], "layout": {}, "room_types": {}, **entry.options})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/get"})
@websocket_api.require_admin
@callback
def ws_get(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    entry = _entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_loaded", "Home Structure is not set up")
        return
    connection.send_result(msg["id"], {
        "areas": structure.areas(hass), "options": _options(entry), "kinds": ZONE_KINDS, "types": SEPARATION_TYPES,
        "in_home": ZONE_IN_HOME, "permanent": PERMANENT, "sensor_domains": SENSOR_DOMAINS, "shutter_hosts": SHUTTER_HOSTS, "room_types": ROOM_TYPES,
    })


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/save", vol.Required("options"): dict})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_save(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Replaces the structure. The sensors are rebuilt only when something other than the positions on the plan changed."""
    entry = _entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_loaded", "Home Structure is not set up")
        return
    data = {"zones": [], "connections": [], "excluded_areas": [], "layout": {}, "room_types": {}, **copy.deepcopy(msg["options"])}
    area_ids = {a["id"] for a in structure.areas(hass)}
    model.apply_layout(data, area_ids)
    errors = model.validate(data, area_ids)
    if errors:
        connection.send_error(msg["id"], "invalid", ", ".join(errors))
        return
    rebuild = model.structural(data) != model.structural(_options(entry))
    hass.config_entries.async_update_entry(entry, options=data)
    if rebuild:
        hass.config_entries.async_schedule_reload(entry.entry_id)
    connection.send_result(msg["id"], {"options": data, "rebuilt": rebuild})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/candidates", vol.Required("area_ids"): [str]})
@websocket_api.require_admin
@callback
def ws_candidates(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Door, window and cover entities of the areas; every such entity of the home when there is none (the editor says which)."""
    found = structure.sensor_candidates(hass, msg["area_ids"])
    connection.send_result(msg["id"], {"sensors": found or structure.all_sensors(hass), "filtered": bool(found)})


COMMANDS = (ws_get, ws_save, ws_candidates)


def async_register(hass: HomeAssistant) -> None:
    for command in COMMANDS:
        websocket_api.async_register_command(hass, command)
