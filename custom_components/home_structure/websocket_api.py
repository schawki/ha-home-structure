"""WebSocket commands of the editor panel (administrators only): read everything the editor needs, and save the structure."""
from __future__ import annotations

import copy
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from . import groups as groups_mod, model, structure
from .const import DOMAIN, GROUPS_CHANGED, PERMANENT, SENSOR_DOMAINS, ROOM_TYPES, ROOM_TYPE_GROUPS, SEPARATION_TYPES, SHUTTER_HOSTS, ZONE_IN_HOME, ZONE_KINDS


def _entry(hass: HomeAssistant) -> ConfigEntry | None:
    entries = hass.config_entries.async_entries(DOMAIN)
    return entries[0] if entries else None


def _options(entry: ConfigEntry) -> dict:
    return copy.deepcopy({"zones": [], "connections": [], "excluded_areas": [], "layout": {}, "room_types": {}, "groups": [], **entry.options})


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
        "in_home": ZONE_IN_HOME, "permanent": PERMANENT, "sensor_domains": SENSOR_DOMAINS, "shutter_hosts": SHUTTER_HOSTS, "room_types": ROOM_TYPES, "room_type_groups": ROOM_TYPE_GROUPS,
        "group_modes": list(groups_mod.MODES),
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
    data["groups"] = copy.deepcopy(entry.options.get("groups", []))        # the groups have their own command: a plan saved late never overwrites them
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


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/save_groups", vol.Required("groups"): [dict]})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_save_groups(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Replaces the groups of rooms (their order is the order of the list).

    Areas that no longer exist and sensors that are no longer in the rooms of a group are taken out (`pruned` lists the groups concerned).
    The group sensors are added, updated or removed on the spot; nothing is reloaded."""
    entry = _entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_loaded", "Home Structure is not set up")
        return
    area_ids = {a["id"] for a in structure.areas(hass)}
    groups = [groups_mod.normalize(g) for g in msg["groups"]]
    taken = {g["id"] for g in groups if g["id"]}
    for g in groups:
        if not g["id"] and g["name"]:
            g["id"] = groups_mod.unique_id(g["name"], taken)
            taken.add(g["id"])
    groups_mod.prune_areas(groups, area_ids)
    pruned = []
    for g in groups:
        allowed = {k: {s["entity_id"] for s in structure.group_sensors(hass, g["areas"], k)} for k in groups_mod.KINDS}
        if groups_mod.prune_sensors(g, allowed):
            pruned.append(g["id"])
    errors = groups_mod.validate(groups, area_ids)
    if errors:
        connection.send_error(msg["id"], "invalid", ", ".join(errors))
        return
    hass.config_entries.async_update_entry(entry, options={**_options(entry), "groups": groups})
    async_dispatcher_send(hass, GROUPS_CHANGED.format(entry.entry_id))                       # the group sensors follow on the spot: no reload
    connection.send_result(msg["id"], {"groups": groups, "pruned": pruned})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/group_sensors", vol.Required("area_ids"): [str], vol.Required("kind"): vol.In(groups_mod.KINDS)})
@websocket_api.require_admin
@callback
def ws_group_sensors(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Temperature or humidity sensors of the given rooms (diagnostic entities left out), for the group editor."""
    connection.send_result(msg["id"], {"sensors": structure.group_sensors(hass, msg["area_ids"], msg["kind"])})


COMMANDS = (ws_get, ws_save, ws_candidates, ws_save_groups, ws_group_sensors)


def async_register(hass: HomeAssistant) -> None:
    for command in COMMANDS:
        websocket_api.async_register_command(hass, command)
