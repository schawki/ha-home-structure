"""The only place where Home Structure writes to Home Assistant: what a sensor is exposed to, and which room a sensor or device is in.

Everything here is reached through WebSocket commands that need an administrator; there is no service that writes. Home Assistant stays the single
source of truth: exposure is read and written through its own registry (nothing is copied), and a room is changed in its entity or device registry.
Each change is written to a short history (the 50 latest) with the state before and after, so it can be undone, unless the state has changed since."""
from __future__ import annotations

import uuid
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, EVENT_CHANGED, REASON_SAVED_STRUCTURE

ASSISTANTS = {"conversation": "conversation", "alexa": "cloud.alexa", "google": "cloud.google_assistant"}
HISTORY_LIMIT = 50
STORE_VERSION = 1


class ExposureError(Exception):
    """A request that cannot be done; `code` says why (the panel translates it)."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code, self.detail = code, detail


# ---- what is exposed

def available(hass: HomeAssistant) -> dict[str, bool]:
    """Which assistants can be set: Assist always, Alexa and Google only when they are enabled in Home Assistant Cloud (voice assistants)."""
    out = {"conversation": True, "alexa": False, "google": False}
    try:
        from homeassistant.components import cloud
        if cloud.async_active_subscription(hass):
            prefs = hass.data[cloud.DATA_CLOUD].client.prefs
            out["alexa"], out["google"] = bool(prefs.alexa_enabled), bool(prefs.google_enabled)
    except Exception:       # no cloud, or a version that answers differently: only Assist can be set
        pass
    return out


def exposed(hass: HomeAssistant, entity_id: str, assistants: dict[str, bool] | None = None) -> dict[str, bool]:
    """What the entity is exposed to, for the assistants that can be set."""
    from homeassistant.components.homeassistant.exposed_entities import async_should_expose
    can = assistants or available(hass)
    out = {}
    for k, ok in can.items():
        if not ok:
            continue
        try:
            out[k] = bool(async_should_expose(hass, ASSISTANTS[k], entity_id))
        except Exception:       # the exposure registry is not loaded: shown as not exposed
            out[k] = False
    return out


def _check_entity(hass: HomeAssistant, entity_id: str) -> er.RegistryEntry:
    entry = er.async_get(hass).async_get(entity_id)
    if entry is None:
        raise ExposureError("unknown_entity", entity_id)
    return entry


def _write_exposure(hass: HomeAssistant, entity_id: str, wanted: dict[str, bool]) -> None:
    from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
    for key, value in wanted.items():
        async_expose_entity(hass, ASSISTANTS[key], entity_id, bool(value))


def set_exposure(hass: HomeAssistant, entity_id: str, changes: dict[str, bool]) -> dict:
    """Sets what a sensor is exposed to. `changes` is {assistant: bool} with assistants among conversation, alexa, google.

    Returns the history entry (before and after, only for what was asked). An assistant that is not available, or a change that changes nothing, is refused."""
    _check_entity(hass, entity_id)
    can = available(hass)
    for key in changes:
        if key not in ASSISTANTS or not can.get(key):
            raise ExposureError("assistant_unavailable", key)
    before = {k: v for k, v in exposed(hass, entity_id, can).items() if k in changes}
    wanted = {k: bool(v) for k, v in changes.items()}
    if before == wanted:
        raise ExposureError("nothing_to_change")
    _write_exposure(hass, entity_id, wanted)
    return {"kind": "exposure", "entity_id": entity_id, "before": before, "after": wanted}


# ---- which room

def effective_area(hass: HomeAssistant, entity_id: str) -> str | None:
    entry = er.async_get(hass).async_get(entity_id)
    if entry is None:
        return None
    device = dr.async_get(hass).async_get(entry.device_id) if entry.device_id else None
    return entry.area_id or (device.area_id if device else None)


def move_info(hass: HomeAssistant, entity_id: str) -> dict:
    """Where the entity is and what shares its device: {area_id, own_area, device: None | {id, name, area_id, others: [{entity_id, name, area_id}]}}.

    `others` are the other entities of the device that are shown (not disabled, hidden, diagnostic or configuration), because moving the whole
    device moves them too, unless they have a room of their own."""
    entities, devices = er.async_get(hass), dr.async_get(hass)
    entry = _check_entity(hass, entity_id)
    device = devices.async_get(entry.device_id) if entry.device_id else None
    out: dict[str, Any] = {"entity_id": entity_id, "area_id": effective_area(hass, entity_id), "own_area": entry.area_id, "device": None}
    if device:
        others = []
        for e in er.async_entries_for_device(entities, device.id):
            if e.entity_id == entity_id or e.disabled or e.hidden_by or e.entity_category is not None:
                continue
            state = hass.states.get(e.entity_id)
            others.append({"entity_id": e.entity_id, "name": (state.name if state else None) or e.name or e.original_name or e.entity_id, "area_id": effective_area(hass, e.entity_id)})
        out["device"] = {"id": device.id, "name": device.name_by_user or device.name or device.id, "area_id": device.area_id, "others": sorted(others, key=lambda o: o["name"].casefold())}
    return out


def _named(hass: HomeAssistant, entity_ids: list[str]) -> list[dict]:
    out = []
    for eid in sorted(set(entity_ids)):
        state = hass.states.get(eid)
        out.append({"entity_id": eid, "name": state.name if state else eid})
    return out


def references(hass: HomeAssistant, entity_ids: list[str], device_id: str | None = None, area_ids: list[str] | None = None) -> dict[str, list[dict]]:
    """The automations, scripts and scenes that use the entities, the device or the rooms (as targets): {automation, script, scene}.

    Home Assistant finds what is written in clear (entities, devices, areas). What is built by a template cannot be found: the panel says so."""
    found: dict[str, list[str]] = {"automation": [], "script": [], "scene": []}
    try:
        from homeassistant.components import automation
        for eid in entity_ids:
            found["automation"] += automation.automations_with_entity(hass, eid)
        if device_id:
            found["automation"] += automation.automations_with_device(hass, device_id)
        for a in area_ids or []:
            found["automation"] += automation.automations_with_area(hass, a)
    except Exception:
        pass
    try:
        from homeassistant.components import script
        for eid in entity_ids:
            found["script"] += script.scripts_with_entity(hass, eid)
        if device_id:
            found["script"] += script.scripts_with_device(hass, device_id)
        for a in area_ids or []:
            found["script"] += script.scripts_with_area(hass, a)
    except Exception:
        pass
    try:
        from homeassistant.components import scene
        for eid in entity_ids:
            found["scene"] += scene.scenes_with_entity(hass, eid)
    except Exception:
        pass
    return {k: _named(hass, v) for k, v in found.items()}


def _check_area(hass: HomeAssistant, area_id: str) -> None:
    if ar.async_get(hass).async_get_area(area_id) is None:
        raise ExposureError("unknown_area", area_id)


def _snapshot(hass: HomeAssistant, entity_id: str) -> dict:
    entry = _check_entity(hass, entity_id)
    device = dr.async_get(hass).async_get(entry.device_id) if entry.device_id else None
    return {"entity_area": entry.area_id, "device_id": device.id if device else None, "device_area": device.area_id if device else None}


def _write_move(hass: HomeAssistant, entity_id: str, state: dict) -> None:
    er.async_get(hass).async_update_entity(entity_id, area_id=state["entity_area"])
    if state.get("device_id"):
        dr.async_get(hass).async_update_device(state["device_id"], area_id=state["device_area"])


def move(hass: HomeAssistant, entity_id: str, area_id: str, scope: str) -> dict:
    """Puts a sensor, or the whole device it belongs to, in a room. `scope` is "entity" or "device".

    For the sensor alone the room is set on the entity (it no longer follows its device), unless the room is the one of its device, in which case it
    follows the device again. For the device, the room is set on the device and the sensor follows it. Returns the history entry."""
    _check_area(hass, area_id)
    before = _snapshot(hass, entity_id)
    if scope == "device" and not before["device_id"]:
        raise ExposureError("no_device")
    if scope not in ("entity", "device"):
        raise ExposureError("invalid_scope")
    after = dict(before)
    if scope == "device":
        after["device_area"], after["entity_area"] = area_id, None
    else:
        after["entity_area"] = None if before["device_id"] and before["device_area"] == area_id else area_id
    if after == before:
        raise ExposureError("nothing_to_change")
    _write_move(hass, entity_id, after)
    return {"kind": "move", "entity_id": entity_id, "scope": scope, "area_id": area_id, "before": before, "after": after}


# ---- history

def _store(hass: HomeAssistant) -> Store:
    key = f"{DOMAIN}_history_store"
    if key not in hass.data:
        hass.data[key] = Store(hass, STORE_VERSION, f"{DOMAIN}.history")
    return hass.data[key]


async def history(hass: HomeAssistant) -> list[dict]:
    """The latest changes made from the panel, newest first."""
    data = await _store(hass).async_load() or {}
    return list(data.get("entries", []))


async def _save_history(hass: HomeAssistant, entries: list[dict]) -> None:
    await _store(hass).async_save({"entries": entries[:HISTORY_LIMIT]})


async def record(hass: HomeAssistant, entry: dict, user_id: str | None) -> dict:
    entry = {"id": uuid.uuid4().hex, "time": dt_util.utcnow().isoformat(), "user_id": user_id, "undone": False, **entry}
    await _save_history(hass, [entry, *await history(hass)])
    return entry


def _current(hass: HomeAssistant, entry: dict) -> dict:
    if entry["kind"] == "primary":
        from . import primary
        config = primary._entry(hass)
        return primary.current(hass, config, entry["area_id"], entry["key"], "native" in entry["after"])
    if entry["kind"] == "exposure":
        return {k: v for k, v in exposed(hass, entry["entity_id"]).items() if k in entry["after"]}
    return _snapshot(hass, entry["entity_id"])


async def undo(hass: HomeAssistant, entry_id: str) -> dict:
    """Puts back the state before a change. Refused when the change was undone already or when the state is no longer the one it left."""
    entries = await history(hass)
    entry = next((e for e in entries if e["id"] == entry_id), None)
    if entry is None:
        raise ExposureError("unknown_entry")
    if entry["undone"]:
        raise ExposureError("already_undone")
    try:
        now = _current(hass, entry)
    except ExposureError:
        raise ExposureError("changed_since")
    if now != entry["after"]:
        raise ExposureError("changed_since")
    if entry["kind"] == "exposure":
        _write_exposure(hass, entry["entity_id"], entry["before"])
    elif entry["kind"] == "primary":
        from . import primary
        primary.write(hass, primary._entry(hass), entry["area_id"], entry["key"], entry["before"])
        _changed(hass)
    else:
        _write_move(hass, entry["entity_id"], entry["before"])
    entry["undone"] = True
    await _save_history(hass, entries)
    return entry


# ---- WebSocket commands (administrators only)

def _fail(connection: websocket_api.ActiveConnection, msg: dict, err: ExposureError) -> None:
    connection.send_error(msg["id"], err.code, err.detail or err.code)


def _changed(hass: HomeAssistant) -> None:
    hass.bus.async_fire(EVENT_CHANGED, {"reason": REASON_SAVED_STRUCTURE})      # a room changed: consumers read the services again


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/exposure_set", vol.Required("entity_id"): str,
                                  vol.Required("changes"): {vol.In(list(ASSISTANTS)): bool}})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_exposure_set(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    try:
        done = set_exposure(hass, msg["entity_id"], msg["changes"])
    except ExposureError as err:
        _fail(connection, msg, err)
        return
    connection.send_result(msg["id"], await record(hass, done, connection.user.id))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/move_preview", vol.Required("entity_id"): str, vol.Required("area_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_move_preview(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """What moving a sensor to a room would touch, for the confirmation: the device it shares, and the automations, scripts and scenes that use it or the rooms."""
    try:
        _check_area(hass, msg["area_id"])
        info = move_info(hass, msg["entity_id"])
    except ExposureError as err:
        _fail(connection, msg, err)
        return
    device = info["device"]
    ids = [msg["entity_id"], *(o["entity_id"] for o in (device["others"] if device else []))]
    old = [a for a in (info["area_id"],) if a]
    connection.send_result(msg["id"], {**info, "target_area": msg["area_id"],
                                       "sensor": references(hass, [msg["entity_id"]], area_ids=[*old, msg["area_id"]]),
                                       "device_refs": references(hass, ids, device_id=device["id"] if device else None, area_ids=[*old, msg["area_id"]]) if device and device["others"] else None})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/move_apply", vol.Required("entity_id"): str, vol.Required("area_id"): str,
                                  vol.Required("scope"): vol.In(["entity", "device"])})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_move_apply(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    try:
        done = move(hass, msg["entity_id"], msg["area_id"], msg["scope"])
    except ExposureError as err:
        _fail(connection, msg, err)
        return
    entry = await record(hass, done, connection.user.id)
    _changed(hass)
    connection.send_result(msg["id"], entry)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/history"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_history(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    connection.send_result(msg["id"], {"entries": await history(hass)})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/undo", vol.Required("entry_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_undo(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    try:
        entry = await undo(hass, msg["entry_id"])
    except ExposureError as err:
        _fail(connection, msg, err)
        return
    if entry["kind"] == "move":
        _changed(hass)
    connection.send_result(msg["id"], entry)


COMMANDS = (ws_exposure_set, ws_move_preview, ws_move_apply, ws_history, ws_undo)


def async_register(hass: HomeAssistant) -> None:
    from . import primary
    for command in (*COMMANDS, *primary.COMMANDS):
        websocket_api.async_register_command(hass, command)
