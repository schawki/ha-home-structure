"""The structure as Home Assistant sees it now: the registries and the states are read, the model does the rest."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er, floor_registry as fr

from . import model
from .const import DOMAIN


def areas(hass: HomeAssistant) -> list[dict]:
    """Every Home Assistant area, with the name of its floor (None when it has none)."""
    floors = {f.floor_id: f.name for f in fr.async_get(hass).async_list_floors()}
    return sorted(({"id": a.id, "name": a.name, "floor": floors.get(a.floor_id)} for a in ar.async_get(hass).async_list_areas()),
                  key=lambda a: a["name"].casefold())


OPENING_CLASSES = {"door", "window", "garage_door", "opening"}   # not "lock": an unlocked door is not an open one


def candidate_sensors(hass: HomeAssistant, area_ids: list[str]) -> list[str]:
    """Door, window and cover entities that sit in the given areas (on the entity itself or on its device).

    Used to shorten the sensor list of a separation; empty when nothing is found, in which case every sensor is offered."""
    entities, devices = er.async_get(hass), dr.async_get(hass)
    wanted, found = set(area_ids), []
    for e in entities.entities.values():
        if e.domain not in ("binary_sensor", "cover") or e.disabled:
            continue
        area = e.area_id or (devices.async_get(e.device_id).area_id if e.device_id and devices.async_get(e.device_id) else None)
        if area not in wanted:
            continue
        if e.domain == "binary_sensor":
            state = hass.states.get(e.entity_id)
            cls = e.device_class or e.original_device_class or (state.attributes.get("device_class") if state else None)
            if cls not in OPENING_CLASSES:
                continue
        found.append(e.entity_id)
    return sorted(found)


def current(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    registry = er.async_get(hass)

    def read(entity_id: str):
        st = hass.states.get(entity_id)
        return (st.state, dict(st.attributes)) if st else None

    return model.build(entry.options, areas(hass), read,
                       lambda sid: registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{sid}"))
