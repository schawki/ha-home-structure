"""The sensor chosen for each category of a room (temperature, humidity, CO2, presence…).

By default it is the first sensor of the category exposed to Assist. Choosing another one is saved here (option `primary_sensor`, {area id: {type key: entity id}});
for temperature and humidity it is also written to the area itself in Home Assistant (`temperature_entity_id`, `humidity_entity_id`) while the option
`primary_sync` is on (the default), so Home Assistant and its cards see the same sensor. Choosing never changes what is exposed to an assistant."""
from __future__ import annotations

import copy
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar

from . import room_sensors
from .const import DOMAIN, EVENT_CHANGED, REASON_SAVED_STRUCTURE
from .exposure import ExposureError, _fail, record


def _entry(hass: HomeAssistant) -> ConfigEntry:
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        raise ExposureError("not_loaded")
    return entries[0]


def sync_on(entry: ConfigEntry) -> bool:
    return bool(entry.options.get("primary_sync", True))


def current(hass: HomeAssistant, entry: ConfigEntry, area_id: str, key: str, sync: bool) -> dict:
    """What is stored now for a category of a room: {"chosen": entity id or None} plus {"native": ...} when it is also kept by Home Assistant (sync on)."""
    out: dict[str, Any] = {"chosen": ((entry.options.get("primary_sensor") or {}).get(area_id) or {}).get(key)}
    if sync and key in room_sensors.NATIVE_FIELDS:
        out["native"] = room_sensors.native_choices(hass, area_id)[key]
    return out


def write(hass: HomeAssistant, entry: ConfigEntry, area_id: str, key: str, state: dict) -> None:
    """Saves the state; Home Assistant's area is written first because it checks the sensor (it must exist and have the right class)."""
    if "native" in state:
        try:
            ar.async_get(hass).async_update(area_id, **{room_sensors.NATIVE_FIELDS[key]: state["native"]})
        except ValueError as err:
            raise ExposureError("native_rejected", str(err)) from err
    saved = copy.deepcopy(entry.options.get("primary_sensor") or {})
    if state.get("chosen"):
        saved.setdefault(area_id, {})[key] = state["chosen"]
    else:
        saved.get(area_id, {}).pop(key, None)
        if not saved.get(area_id):
            saved.pop(area_id, None)
    hass.config_entries.async_update_entry(entry, options={**entry.options, "primary_sensor": saved})


def set_primary(hass: HomeAssistant, area_id: str, key: str, entity_id: str | None) -> dict:
    """Chooses the sensor of a category in a room (None goes back to the default). Returns the history entry."""
    entry = _entry(hass)
    if ar.async_get(hass).async_get_area(area_id) is None:
        raise ExposureError("unknown_area", area_id)
    members = [s for s in room_sensors.collect(hass) if s["area_id"] == area_id and room_sensors.type_key(s["domain"], s["type"]) == key]
    if entity_id is not None and entity_id not in {s["entity_id"] for s in members}:
        raise ExposureError("unknown_entity", entity_id)
    if entity_id is None and not members and key not in room_sensors.NATIVE_FIELDS:
        raise ExposureError("nothing_to_change")
    sync = sync_on(entry)
    before = current(hass, entry, area_id, key, sync)
    after = {"chosen": entity_id, **({"native": entity_id} if "native" in before else {})}
    if after == before:
        raise ExposureError("nothing_to_change")
    write(hass, entry, area_id, key, after)
    return {"kind": "primary", "entity_id": entity_id or before.get("chosen") or before.get("native") or "", "area_id": area_id, "key": key, "sync": sync,
            "before": before, "after": after}


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/primary_set", vol.Required("area_id"): str, vol.Required("key"): str,
                                  vol.Required("entity_id"): vol.Any(str, None)})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_primary_set(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    try:
        done = set_primary(hass, msg["area_id"], msg["key"], msg["entity_id"])
    except ExposureError as err:
        _fail(connection, msg, err)
        return
    entry = await record(hass, done, connection.user.id)
    hass.bus.async_fire(EVENT_CHANGED, {"reason": REASON_SAVED_STRUCTURE})
    connection.send_result(msg["id"], entry)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/primary_sync", vol.Required("value"): bool})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_primary_sync(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Turns on or off the writing of the temperature and humidity choices to Home Assistant's own areas."""
    try:
        entry = _entry(hass)
    except ExposureError as err:
        _fail(connection, msg, err)
        return
    hass.config_entries.async_update_entry(entry, options={**entry.options, "primary_sync": msg["value"]})
    hass.bus.async_fire(EVENT_CHANGED, {"reason": REASON_SAVED_STRUCTURE})
    connection.send_result(msg["id"], {"primary_sync": msg["value"]})


COMMANDS = (ws_primary_set, ws_primary_sync)
