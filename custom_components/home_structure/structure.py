"""The structure as Home Assistant sees it now: the registries and the states are read, the model does the rest."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er, floor_registry as fr

from . import groups as groups_mod, model
from .const import DOMAIN


def areas(hass: HomeAssistant) -> list[dict]:
    """Every Home Assistant area, with the name of its floor (None when it has none)."""
    floors = {f.floor_id: f.name for f in fr.async_get(hass).async_list_floors()}
    return sorted(({"id": a.id, "name": a.name, "floor": floors.get(a.floor_id)} for a in ar.async_get(hass).async_list_areas()),
                  key=lambda a: a["name"].casefold())


def area_details(hass: HomeAssistant) -> list[dict]:
    """The areas of `areas()` plus what the Groups page shows on a room's card: its icon and what it holds, counted as Home Assistant's Areas page does.

    `devices` are the devices of the area (`services` counts those that are services, not included in `devices`), `entities` the entities placed in
    the area by themselves (not through a device of that area)."""
    devices, entities = dr.async_get(hass), er.async_get(hass)
    registry = {a.id: a for a in ar.async_get(hass).async_list_areas()}
    device_area = {d.id: d.area_id for d in devices.devices.values()}
    out = []
    for a in areas(hass):
        mine = [d for d in devices.devices.values() if d.area_id == a["id"]]
        services = sum(1 for d in mine if d.entry_type is dr.DeviceEntryType.SERVICE)
        alone = sum(1 for e in entities.entities.values() if e.area_id == a["id"] and not e.disabled and device_area.get(e.device_id) != a["id"])
        out.append({**a, "icon": registry[a["id"]].icon, "devices": len(mine) - services, "services": services, "entities": alone})
    return out


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


def sensor_candidates(hass: HomeAssistant, area_ids: list[str]) -> list[dict]:
    """Door, window and cover entities of the given areas, for the editor panel."""
    registry = er.async_get(hass)
    out = []
    for entity_id in candidate_sensors(hass, area_ids):
        st = hass.states.get(entity_id)
        reg = registry.async_get(entity_id)
        out.append({"entity_id": entity_id, "name": (st.name if st else None) or (reg.name or reg.original_name if reg else None) or entity_id,
                    "state": st.state if st else "unknown"})
    return out


def all_sensors(hass: HomeAssistant) -> list[dict]:
    """Every binary_sensor and cover (fallback when no candidate is found in the two areas)."""
    return [{"entity_id": s.entity_id, "name": s.name, "state": s.state} for s in sorted(
        (*hass.states.async_all("binary_sensor"), *hass.states.async_all("cover")), key=lambda s: s.name.casefold())]


def group_sensors(hass: HomeAssistant, area_ids: list[str], kind: str) -> list[dict]:
    """The temperature or humidity sensors of the given areas (on the entity itself or on its device), for the groups.

    Diagnostic and configuration entities, disabled and hidden entities and the sensors of Home Structure itself are left out.
    Sorted by area then name; each is {entity_id, name, state, unit, area_id}."""
    entities, devices, areas_reg = er.async_get(hass), dr.async_get(hass), ar.async_get(hass)
    wanted, out = set(area_ids), []
    for e in entities.entities.values():
        if e.domain != "sensor" or e.platform == DOMAIN or e.disabled or e.hidden_by or e.entity_category is not None:
            continue
        device = devices.async_get(e.device_id) if e.device_id else None
        area = e.area_id or (device.area_id if device else None)
        if area not in wanted:
            continue
        state = hass.states.get(e.entity_id)
        if (e.device_class or e.original_device_class or (state.attributes.get("device_class") if state else None)) != kind:
            continue
        found = areas_reg.async_get_area(area)
        out.append({"entity_id": e.entity_id, "name": (state.name if state else None) or e.name or e.original_name or e.entity_id,
                    "state": state.state if state else "unknown",
                    "unit": (state.attributes.get("unit_of_measurement") if state else None) or groups_mod.UNIT[kind],
                    "area_id": area, "area": found.name if found else area})
    return sorted(out, key=lambda s: (s["area"].casefold(), s["name"].casefold()))


def group_view(hass: HomeAssistant, entry: ConfigEntry) -> list[dict]:
    """The groups with the entity of each group sensor: what the service `get_groups` returns."""
    registry = er.async_get(hass)
    return groups_mod.view(entry.options.get("groups", []), areas(hass),
                           lambda gid, kind: registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_group_{gid}_{kind}"))
