"""Groups of rooms as plain data, and the functions that read them. Nothing here needs Home Assistant, so it is tested directly.

A group is a named set of Home Assistant areas, for example the bedrooms or the night part of a home. A room can be in several groups or in none.
Data (stored in the options of the config entry, key `groups`, in the order the user arranged them):

    {id, name, level?, icon?, areas: [area id], aliases: [text],
     temperature: {mode, entities}, humidity: {mode, entities}}

`areas` is ordered too. `level` is stored for whoever wants it and has no effect. A sensor setting has a `mode`:

    none        no sensor for the group
    single      `entities` holds the one sensor to show
    all         the average of every temperature (or humidity) sensor of the rooms of the group, found by Home Assistant every time
    selection   the average of the sensors listed in `entities`
"""
from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from .model import slug

KINDS = ("temperature", "humidity")      # what a group can aggregate
MODES = ("none", "single", "all", "selection")
UNIT = {"temperature": "°C", "humidity": "%"}
STATE_RANGE = {"temperature": (-90.0, 150.0), "humidity": (0.0, 100.0)}   # outside: a broken sensor, ignored

StateReader = Callable[[str], "tuple[str, dict] | None"]


def unique_id(name: str, taken: set[str]) -> str:
    base, n = slug(name), 1
    gid = base
    while gid in taken:
        n += 1
        gid = f"{base}_{n}"
    return gid


def empty_sensor() -> dict:
    return {"mode": "none", "entities": []}


def normalize(group: dict) -> dict:
    """The group with every field present and cleaned (blank texts dropped, duplicates removed, order kept). Unknown keys are dropped."""
    def texts(values: Any) -> list[str]:
        seen, out = set(), []
        for v in values if isinstance(values, list) else []:
            v = v.strip() if isinstance(v, str) else ""
            if v and v.casefold() not in seen:
                seen.add(v.casefold())
                out.append(v)
        return out

    icon = group.get("icon")
    icon = (icon.strip() or None) if isinstance(icon, str) else None
    out: dict = {"id": str(group.get("id", "")).strip(), "name": str(group.get("name", "")).strip(),
                 "level": group.get("level") if isinstance(group.get("level"), int) and not isinstance(group.get("level"), bool) else None,
                 "icon": icon,
                 "areas": [], "aliases": texts(group.get("aliases"))}
    for a in group.get("areas") if isinstance(group.get("areas"), list) else []:
        if isinstance(a, str) and a and a not in out["areas"]:
            out["areas"].append(a)
    for kind in KINDS:
        cfg = group.get(kind) if isinstance(group.get(kind), dict) else {}
        entities = []
        for e in cfg.get("entities") if isinstance(cfg.get("entities"), list) else []:
            if isinstance(e, str) and e and e not in entities:
                entities.append(e)
        out[kind] = {"mode": cfg.get("mode", "none"), "entities": entities}
    return out


def validate(groups: list, area_ids: set[str]) -> list[str]:
    """Error codes; empty when the groups are consistent. Expects normalized groups."""
    errors: list[str] = []
    ids, names = set(), set()
    for g in groups:
        if not isinstance(g, dict) or not g.get("id") or not g.get("name"):
            errors.append("invalid_group")
            continue
        if g["id"] in ids:
            errors.append("duplicate_group_id")
        ids.add(g["id"])
        if g["name"].casefold() in names:
            errors.append("duplicate_group_name")
        names.add(g["name"].casefold())
        if any(a not in area_ids for a in g["areas"]):
            errors.append("unknown_group_area")
        for kind in KINDS:
            cfg = g[kind]
            n, mode = len(cfg["entities"]), cfg["mode"]
            if mode not in MODES or (mode == "single" and n != 1) or (mode == "selection" and n < 1) or (mode in ("none", "all") and n) \
                    or any(not e.startswith("sensor.") for e in cfg["entities"]):
                errors.append("invalid_group_sensor")
    return sorted(set(errors))


def prune_areas(groups: list[dict], area_ids: set[str]) -> None:
    """Drops the areas that no longer exist (deleted in Home Assistant) from every group."""
    for g in groups:
        g["areas"] = [a for a in g["areas"] if a in area_ids]


def prune_sensors(group: dict, allowed: dict[str, set[str]]) -> list[str]:
    """Takes out of the group the sensors that are no longer in its rooms. `allowed[kind]` are the candidates of the group's rooms now.

    A selection loses the entries that left (it becomes `none` when nothing remains); a single sensor that left makes the mode `none`.
    Returns the kinds that changed."""
    changed = []
    for kind in KINDS:
        cfg = group[kind]
        if cfg["mode"] not in ("single", "selection"):
            continue
        keep = [e for e in cfg["entities"] if e in allowed.get(kind, set())]
        if keep == cfg["entities"]:
            continue
        group[kind] = {"mode": cfg["mode"] if keep else "none", "entities": keep if keep else []}
        changed.append(kind)
    return changed


def structural(groups: list[dict]) -> list[dict]:
    """What the entities and the service depend on: everything but the order of the groups."""
    return sorted(groups, key=lambda g: g["id"])


def sources(cfg: dict, candidates: list[str]) -> list[str]:
    """The entities a group reads for one kind, given the candidates of its rooms."""
    mode = cfg.get("mode", "none")
    if mode == "all":
        return list(candidates)
    if mode in ("single", "selection"):
        return list(cfg.get("entities", []))
    return []


def to_unit(kind: str, value: float, unit: str | None) -> float:
    """A reading in the unit of the group (°C for temperature, % for humidity)."""
    if kind == "temperature":
        if unit == "°F":
            return (value - 32) * 5 / 9
        if unit == "K":
            return value - 273.15
    return value


def aggregate(kind: str, entity_ids: list[str], read: StateReader) -> tuple[float | None, list[str]]:
    """(average of the readable sources, the sources that were used). None when no source can be read.

    A source that is unavailable, not a number or outside a believable range is ignored, not counted as zero."""
    lo, hi = STATE_RANGE[kind]
    values, used = [], []
    for entity_id in entity_ids:
        got = read(entity_id)
        if not got:
            continue
        try:
            value = to_unit(kind, float(got[0]), (got[1] or {}).get("unit_of_measurement"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and lo <= value <= hi:
            values.append(value)
            used.append(entity_id)
    return (round(sum(values) / len(values), 2) if values else None), used


def view(groups: list[dict], areas: list[dict], entity_of: Callable[[str, str], str | None]) -> list[dict]:
    """The groups as the service returns them. `entity_of(group id, kind)` gives the entity of a group's sensor, when it has one."""
    names = {a["id"]: a["name"] for a in areas}
    out = []
    for g in groups:
        ids = [a for a in g["areas"] if a in names]
        item = {"id": g["id"], "name": g["name"], "level": g.get("level"), "icon": g.get("icon"), "aliases": list(g.get("aliases", [])),
                "area_ids": ids, "areas": [{"id": a, "name": names[a]} for a in ids]}
        for kind in KINDS:
            cfg = g[kind]
            item[kind] = {"mode": cfg["mode"], "entities": list(cfg["entities"]), "entity_id": entity_of(g["id"], kind) if cfg["mode"] != "none" else None}
        out.append(item)
    return out
