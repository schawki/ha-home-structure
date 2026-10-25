"""The sensors of each room, grouped by type, with what is exposed to Assist, HomeKit and Matter. Read-only: nothing here changes Home Assistant.

Only `sensor` and `binary_sensor` entities count. Diagnostic and configuration entities, disabled and hidden entities and the sensors of Home Structure
itself are left out. An entity belongs to the area it has itself, or else the area of its device."""
from __future__ import annotations

import fnmatch
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DOMAINS = ("sensor", "binary_sensor")
OTHER = "other"      # a sensor with no device class
ASSIST = "conversation"
MATTER_TIMEOUT = 4

# The categories that describe a room: shown by default. Every other sensor is hidden as "other"; sound detections are hidden as "sound".
SHOWN = {("sensor", t) for t in ("temperature", "humidity", "illuminance", "carbon_dioxide", "pressure", "atmospheric_pressure", "sound_pressure", "pm25", "pm10",
                                  "volatile_organic_compounds", "volatile_organic_compounds_parts")} | {("binary_sensor", t) for t in ("motion", "occupancy", "presence")}
SOUND_PLATFORMS = ("sound_recognition",)      # integrations whose sensors are detections of sounds; any binary sensor of class `sound` counts too
NATIVE_FIELDS = {"sensor.temperature": "temperature_entity_id", "sensor.humidity": "humidity_entity_id"}      # what Home Assistant itself keeps on an area


# ---- what is exposed

def assist_exposed(hass: HomeAssistant, entity_id: str) -> bool:
    """Is the entity exposed to Assist (the conversation assistant)? Home Assistant stays the only place where this is stored."""
    try:
        from homeassistant.components.homeassistant.exposed_entities import async_should_expose
        return bool(async_should_expose(hass, ASSIST, entity_id))
    except Exception:       # the exposure registry is not available: the badge is simply not shown as ticked
        return False


def homekit_filters(hass: HomeAssistant) -> list[dict]:
    """The entity filter of each HomeKit bridge or accessory (from its config entry): [{title, mode, include_*, exclude_*}]."""
    out = []
    for entry in hass.config_entries.async_entries("homekit"):
        raw = {**(entry.data.get("filter") or {}), **(entry.options.get("filter") or {})}
        out.append({"title": entry.title, "mode": entry.data.get("mode", "bridge"), "include_domains": list(raw.get("include_domains") or []),
                    "exclude_domains": list(raw.get("exclude_domains") or []), "include_entities": list(raw.get("include_entities") or []),
                    "exclude_entities": list(raw.get("exclude_entities") or []), "include_entity_globs": list(raw.get("include_entity_globs") or []),
                    "exclude_entity_globs": list(raw.get("exclude_entity_globs") or [])})
    return out


def _listed(f: dict, kind: str, entity_id: str) -> bool:
    domain = entity_id.split(".", 1)[0]
    return (entity_id in f[f"{kind}_entities"] or domain in f[f"{kind}_domains"]
            or any(fnmatch.fnmatchcase(entity_id, g) for g in f[f"{kind}_entity_globs"]))


def homekit_exposes(flt: dict, entity_id: str) -> bool:
    """Does the filter of a HomeKit entry let the entity through? Same rules as Home Assistant's entity filter.

    An accessory exposes only the entities it lists. With no `include` at all everything is let through except what is excluded; with some,
    only what they list (an entity listed by id is kept even if its domain is excluded)."""
    if flt["mode"] != "bridge":
        return entity_id in flt["include_entities"]
    if entity_id in flt["include_entities"]:
        return True
    if entity_id in flt["exclude_entities"] or any(fnmatch.fnmatchcase(entity_id, g) for g in flt["exclude_entity_globs"]):
        return False
    has_include = bool(flt["include_domains"] or flt["include_entities"] or flt["include_entity_globs"])
    if has_include:
        return _listed(flt, "include", entity_id) and entity_id.split(".", 1)[0] not in flt["exclude_domains"]
    return entity_id.split(".", 1)[0] not in flt["exclude_domains"]


def homekit_titles(filters: list[dict], entity_id: str) -> list[str]:
    """The titles of the HomeKit bridges or accessories that expose the entity (empty when none)."""
    return [f["title"] for f in filters if homekit_exposes(f, entity_id)]


# ---- Matter Hub (the add-on keeps its bridges to itself: its web API is asked, and nothing is shown when it cannot be read)

def matter_hub_urls(hass: HomeAssistant) -> list[str]:
    """Where the Matter Hub add-on may answer, found through the Supervisor (empty without one or without the add-on)."""
    try:
        from homeassistant.components.hassio import get_addons_info
        addons = get_addons_info(hass) or {}
    except Exception:
        return []
    urls = []
    for slug, info in addons.items():
        text = f"{slug} {info.get('name', '')} {info.get('url', '') or ''}".lower()
        if "matter-hub" not in text and "matter_hub" not in text and not slug.endswith("_hamh"):
            continue
        if info.get("state") != "started":
            continue
        port = info.get("ingress_port")
        hosts = [h for h in (info.get("hostname"), info.get("ip_address")) if h]
        urls += [f"http://{h}:{port}" for h in hosts if port]
    return urls


async def matter_bridges(hass: HomeAssistant) -> list[dict] | None:
    """The bridges of the Matter Hub add-on as {name, filter}, or None when they cannot be read (no add-on, not started, unexpected answer)."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession
    session = async_get_clientsession(hass)
    for base in matter_hub_urls(hass):
        try:
            async with session.get(f"{base}/api/matter/bridges", timeout=MATTER_TIMEOUT) as resp:
                if resp.status != 200:
                    continue
                parsed = parse_matter_bridges(await resp.json(content_type=None))
        except Exception as err:       # network, timeout, not JSON: this badge is optional
            _LOGGER.debug("Matter Hub not readable at %s: %s", base, err)
            continue
        if parsed is not None:
            return parsed
    return None


def parse_matter_bridges(payload: Any) -> list[dict] | None:
    """[{name, include: [{type, value}], exclude: [...]}] from the answer of the add-on, or None when it does not look like a list of bridges."""
    if not isinstance(payload, list):
        return None
    out = []
    for b in payload:
        if not isinstance(b, dict):
            return None
        flt = b.get("filter") if isinstance(b.get("filter"), dict) else {}
        rules = {k: [r for r in (flt.get(k) or []) if isinstance(r, dict)] for k in ("include", "exclude")}
        out.append({"name": str(b.get("name") or b.get("id") or "Matter"), **rules})
    return out


def matter_rule_matches(rule: dict, info: dict) -> bool | None:
    """Does one rule of a Matter Hub filter match the entity? None when the rule is of a kind that is not understood."""
    kind, value = str(rule.get("type", "")), rule.get("value")
    if kind == "domain":
        return info["domain"] == value
    if kind in ("entity_id", "entity"):
        return info["entity_id"] == value
    if kind == "pattern":
        return isinstance(value, str) and fnmatch.fnmatchcase(info["entity_id"], value)
    if kind == "platform":
        return info["platform"] == value
    if kind == "device_class":
        return info["device_class"] == value
    if kind == "area":
        return info["area_id"] == value
    if kind == "device_id":
        return info["device_id"] == value
    if kind == "label":
        return value in info["labels"]
    return None


def matter_titles(bridges: list[dict], info: dict) -> list[str]:
    """The names of the Matter bridges that expose the entity. A bridge with no `include` rule exposes nothing, as in the add-on."""
    out = []
    for b in bridges:
        if not b["include"]:
            continue
        inc = [matter_rule_matches(r, info) for r in b["include"]]
        exc = [matter_rule_matches(r, info) for r in b["exclude"]]
        if any(m for m in inc if m is not None) and not any(m for m in exc if m is not None):
            out.append(b["name"])
    return out


# ---- the sensors

def _device_class(e, state) -> str:
    return e.device_class or e.original_device_class or (state.attributes.get("device_class") if state else None) or OTHER


def collect(hass: HomeAssistant) -> list[dict]:
    """Every sensor and binary sensor worth showing, as {entity_id, name, state, unit, domain, type, area_id, device_id, device_name, platform, labels}."""
    entities, devices = er.async_get(hass), dr.async_get(hass)
    out = []
    for e in entities.entities.values():
        if e.domain not in DOMAINS or e.platform == DOMAIN or e.disabled or e.hidden_by or e.entity_category is not None:
            continue
        device = devices.async_get(e.device_id) if e.device_id else None
        state = hass.states.get(e.entity_id)
        out.append({"entity_id": e.entity_id, "name": (state.name if state else None) or e.name or e.original_name or e.entity_id,
                    "state": state.state if state else "unknown", "unit": (state.attributes.get("unit_of_measurement") if state else None),
                    "domain": e.domain, "type": _device_class(e, state), "area_id": e.area_id or (device.area_id if device else None),
                    "device_id": e.device_id, "device_name": (device.name_by_user or device.name) if device else None,
                    "platform": e.platform, "labels": sorted(e.labels), "unique_id": str(e.unique_id or "")})
    return out


def hidden_kind(s: dict) -> str | None:
    """Why a sensor is hidden by default: "sound" (a detection of a sound), "other" (not a category that describes a room), or None (shown)."""
    if s["platform"] in SOUND_PLATFORMS or (s["domain"] == "binary_sensor" and s["type"] == "sound") or (s["platform"] == "frigate" and ":audio_sensor:" in s["unique_id"]):
        return "sound"
    return None if (s["domain"], s["type"]) in SHOWN else "other"


def type_key(domain: str, kind: str) -> str:
    """The key of a type of sensors in a room, used to store its order: "sensor.temperature", "binary_sensor.motion"."""
    return f"{domain}.{kind}"


def _sort_key(s: dict) -> tuple:
    return (not s["assist"], s["name"].casefold(), s["entity_id"])      # the sensor exposed to Assist comes first, until the user saves an order


def pick_primary(items: list[dict], chosen: str | None, native: str | None, sync: bool) -> tuple[str | None, str | None]:
    """The sensor that stands for the category in the room, and why: ("entity_id", "native" | "chosen" | "assist") or (None, None).

    With the sync on, the one Home Assistant keeps on the area (temperature, humidity) comes first; then the one chosen here; then the first one
    exposed to Assist (`items` are in their order). Only a sensor of the group can be picked."""
    ids = {s["entity_id"] for s in items}
    if sync and native in ids:
        return native, "native"
    if chosen in ids:
        return chosen, "chosen"
    first = next((s["entity_id"] for s in items if s["assist"]), None)
    return (first, "assist") if first else (None, None)


def grouped(sensors: list[dict], saved: dict[str, list[str]] | None = None, chosen: dict[str, str] | None = None, native: dict[str, str | None] | None = None,
            sync: bool = True) -> list[dict]:
    """The sensors of one room by type: [{key, type, domain, sensors, ordered, saved, assist_first}].

    `ordered` is true when there are at least two sensors of the type (only then does their order mean something). `saved` is true when the user
    saved an order for it (`saved` is {type key: [entity id]}): that order is kept, a sensor it does not list comes after, in the automatic order.
    Without a saved order the sensor exposed to Assist comes first. `assist_first` tells whether the first sensor is the one exposed to Assist, or
    None when none is exposed or there is nothing to compare."""
    saved = saved or {}
    chosen, native = chosen or {}, native or {}
    buckets: dict[tuple[str, str], list[dict]] = {}
    for s in sensors:
        buckets.setdefault((s["domain"], s["type"]), []).append(s)
    out = []
    for (domain, kind), items in sorted(buckets.items(), key=lambda kv: (kv[0][1] == OTHER, kv[0][1], kv[0][0])):
        key = type_key(domain, kind)
        items = sorted(items, key=_sort_key)
        mine = saved.get(key)
        if mine:
            rank = {eid: i for i, eid in enumerate(mine)}
            items = sorted(items, key=lambda s: rank.get(s["entity_id"], len(rank)))      # stable: the unlisted ones keep the automatic order
        ordered = len(items) >= 2
        exposed = [s for s in items if s["assist"]]
        primary, source = pick_primary(items, chosen.get(key), native.get(key), sync)
        out.append({"key": key, "type": kind, "domain": domain, "sensors": items, "ordered": ordered, "saved": bool(mine) and ordered,
                    "assist_first": (items[0]["assist"] if exposed else None) if ordered else None, "primary": primary, "primary_source": source})
    return out


def native_choices(hass: HomeAssistant, area_id: str | None) -> dict[str, str | None]:
    """The temperature and humidity sensors Home Assistant keeps on the area: {"sensor.temperature": entity id or None, ...}."""
    area = ar.async_get(hass).async_get_area(area_id) if area_id else None
    return {key: getattr(area, field, None) if area else None for key, field in NATIVE_FIELDS.items()}


def view(hass: HomeAssistant, spaces: list[dict], bridges: list[dict] | None, order: dict[str, dict[str, list[str]]] | None = None,
         chosen: dict[str, dict[str, str]] | None = None, sync: bool = True) -> dict:
    """What the Rooms panel and the service `get_room_sensors` return.

    `rooms` follows `spaces` (the ones that are Home Assistant areas), each with its `occupants`; `unassigned` lists the sensors that are in no area
    (a sensor of an area that is not on the plan is not listed). `homekit` lists the HomeKit entries and `matter` is {available, bridges} (`bridges` are names; available is false when the
    add-on could not be read, in which case no sensor carries a Matter badge)."""
    from .exposure import available, exposed
    filters, can = homekit_filters(hass), available(hass)
    order = order or {}
    found = collect(hass)
    for s in found:
        flags = exposed(hass, s["entity_id"], can)
        s["assist"], s["alexa"], s["google"] = flags.get("conversation", False), flags.get("alexa", False), flags.get("google", False)
        s["homekit"] = homekit_titles(filters, s["entity_id"])
        s["matter"] = matter_titles(bridges, {"entity_id": s["entity_id"], "domain": s["domain"], "platform": s["platform"], "device_class": None if s["type"] == OTHER else s["type"],
                                              "area_id": s["area_id"], "device_id": s["device_id"], "labels": s["labels"]}) if bridges is not None else []
        s["hidden"] = hidden_kind(s)
        del s["labels"], s["platform"], s["unique_id"]
    by_area: dict[str | None, list[dict]] = {}
    for s in found:
        by_area.setdefault(s["area_id"], []).append(s)
    rooms = [{"id": sp["id"], "area_id": sp["area_id"], "name": sp["name"], "kind": sp["kind"], "occupants": sp.get("occupants", []),
              "floor": sp.get("floor"), "floor_level": sp.get("floor_level"), "types": grouped(by_area.get(sp["area_id"], []), order.get(sp["area_id"]), (chosen or {}).get(sp["area_id"]),
                                               native_choices(hass, sp["area_id"]), sync)} for sp in spaces if sp.get("area_id")]
    loose = [s for s in found if s["area_id"] is None]
    return {"rooms": rooms, "unassigned": sorted(loose, key=lambda s: (s["type"], s["name"].casefold())),
            "homekit": [{"title": f["title"], "mode": f["mode"]} for f in filters], "assistants": {"alexa": can["alexa"], "google": can["google"]},
            "primary_sync": sync, "matter": {"available": bridges is not None, "bridges": [b["name"] for b in bridges] if bridges is not None else []}}
