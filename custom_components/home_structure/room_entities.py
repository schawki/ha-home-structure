"""The entities of each room, by type (lights, media players, switches…): what the service `get_room_entities` returns. Read-only.

Home Structure only says what is in each room. What it means (a media player that can be heard next door, a light that can be seen) is for the
integration that reads it. An entity belongs to the area it has itself, or else the area of its device. Diagnostic and configuration entities,
disabled and hidden entities and the entities of Home Structure itself are left out."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN

SENSOR_DOMAINS = ("sensor", "binary_sensor")      # these have their own service, `get_room_sensors`, which also gives their order and exposure


def collect(hass: HomeAssistant, domains: list[str] | None) -> list[dict]:
    """The entities worth showing as {entity_id, name, state, domain, area_id, device_id, device_name}.

    `domains` limits them to those domains (sensors included when they are named); without it every domain is returned except `sensor` and `binary_sensor`."""
    wanted = {d.strip().lower() for d in domains if d and d.strip()} if domains else None
    entities, devices = er.async_get(hass), dr.async_get(hass)
    out = []
    for e in entities.entities.values():
        if e.platform == DOMAIN or e.disabled or e.hidden_by or e.entity_category is not None:
            continue
        if (e.domain not in wanted) if wanted else (e.domain in SENSOR_DOMAINS):
            continue
        device = devices.async_get(e.device_id) if e.device_id else None
        state = hass.states.get(e.entity_id)
        out.append({"entity_id": e.entity_id, "name": (state.name if state else None) or e.name or e.original_name or e.entity_id,
                    "state": state.state if state else "unknown", "domain": e.domain, "area_id": e.area_id or (device.area_id if device else None),
                    "device_id": e.device_id, "device_name": (device.name_by_user or device.name) if device else None})
    return out


def by_domain(entities: list[dict]) -> dict[str, list[dict]]:
    """{domain: [entity]}, domains and entities sorted (by name), the domain and area left out of each entity as they are in the key."""
    out: dict[str, list[dict]] = {}
    for e in sorted(entities, key=lambda e: (e["domain"], e["name"].casefold(), e["entity_id"])):
        out.setdefault(e["domain"], []).append({k: v for k, v in e.items() if k not in ("domain", "area_id")})
    return out


def view(hass: HomeAssistant, spaces: list[dict], domains: list[str] | None) -> dict:
    """{rooms: [{id, area_id, name, kind, entities: {domain: [...]}}], unassigned: {domain: [...]}}.

    `rooms` follows `spaces` (the ones that are Home Assistant areas); `unassigned` are the entities that are in no area (an entity of an area that
    is not on the plan is not listed)."""
    found = collect(hass, domains)
    by_area: dict[str | None, list[dict]] = {}
    for e in found:
        by_area.setdefault(e["area_id"], []).append(e)
    rooms = [{"id": sp["id"], "area_id": sp["area_id"], "name": sp["name"], "kind": sp["kind"], "entities": by_domain(by_area.get(sp["area_id"], []))}
             for sp in spaces if sp.get("area_id")]
    return {"rooms": rooms, "unassigned": by_domain(by_area.get(None, []))}
