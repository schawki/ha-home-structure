"""The structure of a home as plain data, and the functions that read it. Nothing here needs Home Assistant, so it is tested directly.

Data (stored in the options of the config entry):

    excluded_areas: [area id]    Home Assistant areas left out of the structure (technical groupings, for example); every other area is a room
    layout:      {space id: {x, y}}              where each space sits on the plan of the editor panel; a space without a position is not on the plan yet
    room_types:  {space id: type}               what an ordinary room is used for (bedroom, bathroom…), optional; only rooms have one
    room_occupants: {space id: [user id]}       the Home Assistant users who usually use an ordinary room, optional; only rooms have them
    zones:      [{id, kind, in_home, name?}]   spaces other than rooms; id is "zone:<slug>", or "area:<area id>" to give a kind to a Home Assistant area
    connections: [{id, a, b, separations: [{id, type, sensor?, shutter?, lock?, passage?}]}]   a and b are space ids; two spaces with no connection are not adjacent

A connection is stored once and holds in both directions, so adjacency is always reciprocal.
A separation may name a `lock` (door, glass door, grille) and, for the ambiguous types only (grille, window, shutter), a `passage` level that
replaces the one the type gives. Nothing here depends on whether a door is open or locked: that is for the integrations that read the structure.

A room is any Home Assistant area ("area:<area id>"); it needs no entry in `zones`.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from typing import Any

from .const import (LOCK_HOSTS, PASSAGE_AMBIGUOUS, PASSAGE_BY_TYPE, PASSAGE_LEVELS, PASSAGE_NONE, PASSAGE_NORMAL, PASSAGE_POSSIBLE, PERMANENT, ROOM_TYPES,
                    SEPARATION_TYPES, SHUTTER_HOSTS, ZONE_IN_HOME, ZONE_KINDS)

StateReader = Callable[[str], "tuple[str, dict] | None"]


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "zone"


def unique_zone_id(name: str, taken: set[str]) -> str:
    base, n = f"zone:{slug(name)}", 1
    zid = base
    while zid in taken:
        n += 1
        zid = f"{base}_{n}"
    return zid


def spaces(data: dict, areas: list[dict]) -> list[dict]:
    """Every space: the Home Assistant areas (rooms, unless given a kind as a zone) then the zones that are not an area.

    `areas` is [{"id", "name"}]. Each space is {id, name, kind, in_home, area_id, room_type, occupants}; `occupants` are the ids of the users who
    usually use the room (always empty for a zone)."""
    zones = {z["id"]: z for z in data.get("zones", [])}
    left_out = set(data.get("excluded_areas", []))
    types = data.get("room_types") or {}
    usual = data.get("room_occupants") or {}
    out = []
    for a in areas:
        if a["id"] in left_out:
            continue
        sid = f"area:{a['id']}"
        z = zones.get(sid)
        out.append({"id": sid, "name": (z or {}).get("name") or a["name"], "kind": z["kind"] if z else "room",
                    "in_home": z["in_home"] if z else True, "area_id": a["id"], "room_type": None if z else types.get(sid),
                    "occupants": [] if z else list(usual.get(sid, [])),
                    "floor": a.get("floor"), "floor_level": a.get("floor_level")})
    for z in data.get("zones", []):
        if not z["id"].startswith("area:"):
            out.append({"id": z["id"], "name": z["name"], "kind": z["kind"], "in_home": z["in_home"], "area_id": None, "room_type": None, "occupants": [], "floor": None, "floor_level": None})
    return out


def validate(data: dict, area_ids: set[str]) -> list[str]:
    """Error codes (also translation keys of the options flow); empty when the structure is consistent."""
    errors: list[str] = []
    known = {f"area:{a}" for a in area_ids if a not in set(data.get("excluded_areas", []))} | {z["id"] for z in data.get("zones", []) if z["id"].startswith("zone:")}
    zone_ids = {z["id"] for z in data.get("zones", [])}
    for sid, kind in (data.get("room_types") or {}).items():
        if kind not in ROOM_TYPES or sid not in known or sid in zone_ids:
            errors.append("invalid_room_type")
    for sid, users in (data.get("room_occupants") or {}).items():
        if sid not in known or sid in zone_ids or not isinstance(users, list) or any(not isinstance(u, str) or not u for u in users):
            errors.append("invalid_occupants")
    names = [z["name"].casefold() for z in data.get("zones", []) if z.get("name")]
    if len(names) != len(set(names)):
        errors.append("duplicate_zone_name")
    for z in data.get("zones", []):
        if z.get("kind") not in ZONE_KINDS or not isinstance(z.get("in_home"), bool):
            errors.append("invalid_zone")
        if z["id"].startswith("area:") and z["id"] not in known:
            errors.append("unknown_area")
    pairs = set()
    for c in data.get("connections", []):
        if c["a"] not in known or c["b"] not in known:
            errors.append("unknown_space")
        if c["a"] == c["b"]:
            errors.append("same_space")
        key = frozenset((c["a"], c["b"]))
        if key in pairs:
            errors.append("duplicate_connection")
        pairs.add(key)
        if not c.get("separations"):
            errors.append("no_separation")
        for s in c.get("separations", []):
            if s.get("type") not in SEPARATION_TYPES:
                errors.append("invalid_separation")
            elif s["type"] in PERMANENT and s.get("sensor"):
                errors.append("sensor_not_needed")
            if s.get("shutter") and (s.get("type") not in SHUTTER_HOSTS or not str(s["shutter"]).startswith("cover.")):
                errors.append("invalid_shutter")
            if s.get("lock") and (s.get("type") not in LOCK_HOSTS or not str(s["lock"]).startswith("lock.")):
                errors.append("invalid_lock")
            if s.get("passage") is not None:
                if s.get("type") not in PASSAGE_AMBIGUOUS:
                    errors.append("passage_not_needed")
                elif s["passage"] not in PASSAGE_LEVELS:
                    errors.append("invalid_passage")
    return sorted(set(errors))


def normalize(state: str | None, attrs: dict[str, Any]) -> tuple[str, int | None]:
    """State of an opening sensor or a cover as (open | closed | partial | unknown, position 0-100 or None).

    binary_sensor: on = open, off = closed. cover: the position when it reports one (0 closed, 100 open, in between partial), else its state."""
    if state is None or state in ("unavailable", "unknown"):
        return "unknown", None
    pos = attrs.get("current_position")
    if isinstance(pos, (int, float)) and not isinstance(pos, bool):
        pos = max(0, min(100, int(pos)))
        return ("closed" if pos == 0 else "open" if pos == 100 else "partial"), pos
    if state in ("on", "open", "opening"):
        return ("partial" if state == "opening" else "open"), None
    if state in ("off", "closed", "closing"):
        return ("partial" if state == "closing" else "closed"), None
    return "unknown", None


def separation_state(sep: dict, read: StateReader) -> tuple[str, int | None]:
    """Current state of a separation: fixed for an open space, an opening or a wall; read from its sensor otherwise ("unknown" without one)."""
    if sep["type"] in PERMANENT:
        return PERMANENT[sep["type"]], None
    sensor = sep.get("sensor")
    got = read(sensor) if sensor else None
    return normalize(got[0], got[1]) if got else ("unknown", None)


def shutter_state(sep: dict, read: StateReader) -> tuple[str, int | None]:
    """State of the shutter in front of a separation (a cover): ("unknown", None) when there is none or it cannot be read."""
    got = read(sep["shutter"]) if sep.get("shutter") else None
    return normalize(got[0], got[1]) if got else ("unknown", None)


def lock_state(sep: dict, read: StateReader) -> str:
    """State of the lock of a separation as locked | unlocked | jammed | unknown ("unknown" when there is none or it cannot be read).

    A latch pulled back (`open`) counts as unlocked: whether the door itself is open is for its opening sensor to say. `locking` and `unlocking`
    last a few seconds and are unknown."""
    got = read(sep["lock"]) if sep.get("lock") else None
    state = got[0] if got else None
    return {"locked": "locked", "unlocked": "unlocked", "open": "unlocked", "jammed": "jammed"}.get(state, "unknown")


def passage(sep: dict) -> str:
    """How far a person goes through a separation: none | possible | normal (see `const.PASSAGE_LEVELS`).

    The type decides; for the ambiguous types (grille, window, shutter) the user's own `passage` replaces it."""
    level = sep.get("passage")
    if sep["type"] in PASSAGE_AMBIGUOUS and level in PASSAGE_LEVELS:
        return level
    return PASSAGE_BY_TYPE.get(sep["type"], PASSAGE_NONE)


def connection_passage(separations: list[dict]) -> str:
    """The highest passage among the separations of a connection: one door between two rooms is enough to go from one to the other."""
    return max((passage(s) for s in separations), key=PASSAGE_LEVELS.index, default=PASSAGE_NONE)


def build(data: dict, areas: list[dict], read: StateReader, entity_of: Callable[[str], str | None] = lambda _sid: None) -> dict:
    """The whole structure as the service returns it: spaces, and connections with the current state of each separation.

    `entity_of(separation id)` gives the Home Structure entity of a separation, when there is one."""
    all_spaces = spaces(data, areas)
    names = {s["id"]: s["name"] for s in all_spaces}
    conns = []
    for c in data.get("connections", []):
        seps = []
        for s in c["separations"]:
            state, pos = separation_state(s, read)
            shutter = s.get("shutter")
            sh_state, sh_pos = shutter_state(s, read)
            lock = s.get("lock")
            seps.append({"id": s["id"], "type": s["type"], "state": state, "position": pos, "sensor": s.get("sensor"), "entity_id": entity_of(s["id"]),
                         "shutter": shutter, "shutter_state": sh_state if shutter else None, "shutter_position": sh_pos,
                         "passage": passage(s), "lock": lock, "lock_state": lock_state(s, read) if lock else None})
        conns.append({"id": c["id"], "a": c["a"], "b": c["b"], "a_name": names.get(c["a"], c["a"]), "b_name": names.get(c["b"], c["b"]),
                      "passage": connection_passage(c["separations"]), "separations": seps})
    return {"spaces": all_spaces, "connections": conns, "layout": {k: dict(v) for k, v in (data.get("layout") or {}).items()}}


def adjacency(structure: dict, level: str = PASSAGE_NORMAL) -> dict[str, list[str]]:
    """The Home Assistant areas a person can go to from each area: {area id: [area id]}, from a structure as `build` returns it.

    `level` is the lowest passage that counts: "normal" (everyday routes, the default) or "possible" (also the ways through that are not
    everyday, a window for example). A connection holds in both directions, so the result is symmetric. Spaces that are not Home Assistant
    areas (street, neighbour…) are left out, and an area with no way through is there with an empty list."""
    if level not in (PASSAGE_POSSIBLE, PASSAGE_NORMAL):
        raise ValueError(level)
    counted = PASSAGE_LEVELS[PASSAGE_LEVELS.index(level):]
    out: dict[str, set[str]] = {s["area_id"]: set() for s in structure["spaces"] if s.get("area_id")}
    for c in structure["connections"]:
        if c["passage"] in counted and c["a"].startswith("area:") and c["b"].startswith("area:"):
            a, b = c["a"][5:], c["b"][5:]
            if a in out and b in out:
                out[a].add(b)
                out[b].add(a)
    return {area: sorted(others) for area, others in sorted(out.items())}


def neighbours(structure: dict, space_id: str) -> list[str]:
    """Space ids adjacent to a space."""
    return sorted({c["b"] if c["a"] == space_id else c["a"] for c in structure["connections"] if space_id in (c["a"], c["b"])})


def default_in_home(kind: str) -> bool:
    return ZONE_IN_HOME.get(kind, False)


def exclude_areas(data: dict, area_ids: set[str]) -> None:
    """Leaves the given areas out of the structure, with their zone entry and their connections."""
    data["excluded_areas"] = sorted(area_ids)
    gone = {f"area:{a}" for a in area_ids}
    data["zones"] = [z for z in data.get("zones", []) if z["id"] not in gone]
    data["connections"] = [c for c in data.get("connections", []) if c["a"] not in gone and c["b"] not in gone]
    data["room_types"] = {k: v for k, v in (data.get("room_types") or {}).items() if k not in gone}
    data["room_occupants"] = {k: v for k, v in (data.get("room_occupants") or {}).items() if k not in gone}


def set_area_kinds(data: dict, kinds: dict[str, list[str]], keep: set[str]) -> None:
    """Gives each listed area its zone kind (garden, hall…) in one go. `kinds` is {kind: [area id]}.

    An area that already has a zone entry of the same kind keeps it (name, in_home); one that is no longer listed loses its entry, except
    the ids in `keep`. in_home follows the kind (default_in_home), and can be changed afterwards zone by zone."""
    wanted = {f"area:{a}": k for k, ids in kinds.items() for a in ids}
    old = {z["id"]: z for z in data.get("zones", [])}
    zones = [z for z in data.get("zones", []) if not z["id"].startswith("area:") or z["id"] in keep]
    for sid, kind in wanted.items():
        if sid in keep:
            continue
        prev = old.get(sid)
        zones.append(prev if prev and prev["kind"] == kind else {"id": sid, "kind": kind, "in_home": default_in_home(kind),
                                                                  **({"name": prev["name"]} if prev and prev.get("name") else {})})
    data["zones"] = zones


def connect_many(data: dict, origin: str, targets: list[str], separation_type: str, new_id: Callable[[], str]) -> list[dict]:
    """Connects `origin` to every target with one separation of the given type. Pairs that are already connected are left as they are.

    Returns the connections created."""
    have = {frozenset((c["a"], c["b"])) for c in data.get("connections", [])}
    created = []
    for t in targets:
        if t == origin or frozenset((origin, t)) in have:
            continue
        conn = {"id": new_id(), "a": origin, "b": t, "separations": [{"id": new_id(), "type": separation_type}]}
        data.setdefault("connections", []).append(conn)
        created.append(conn)
        have.add(frozenset((origin, t)))
    return created


def apply_layout(data: dict, area_ids: set[str]) -> None:
    """Called when the editor panel saves: an area with no position on the plan is not part of the structure (it waits in the tray).

    It is left out, with its zone entry and its connections; every other area stays a room. Virtual zones always have a position."""
    layout = data.get("layout") or {}
    data["layout"] = {k: v for k, v in layout.items() if isinstance(v, dict) and isinstance(v.get("x"), (int, float)) and isinstance(v.get("y"), (int, float))}
    exclude_areas(data, {a for a in area_ids if f"area:{a}" not in data["layout"]})
    known = {f"area:{a}" for a in area_ids if a not in set(data["excluded_areas"])} | {z["id"] for z in data["zones"] if z["id"].startswith("zone:")}
    data["layout"] = {k: v for k, v in data["layout"].items() if k in known}
    zone_ids = {z["id"] for z in data["zones"]}
    data["room_types"] = {k: v for k, v in (data.get("room_types") or {}).items() if k in known and k not in zone_ids and v in ROOM_TYPES}   # only rooms have one
    usual = {}
    for k, users in (data.get("room_occupants") or {}).items():
        if k not in known or k in zone_ids:
            continue                                      # only rooms have usual occupants
        if isinstance(users, list):
            users = list(dict.fromkeys(u for u in users if isinstance(u, str) and u))      # no duplicates, no blanks, order kept
            if not users:
                continue                                  # nobody: the same as no entry
        usual[k] = users                                  # a malformed value is kept so that validate reports it
    data["room_occupants"] = usual


def prune_occupants(data: dict, user_ids: set[str]) -> None:
    """Takes the users that no longer exist (deleted in Home Assistant) out of the usual occupants; a room left with nobody loses its entry."""
    kept = {k: [u for u in users if u in user_ids] for k, users in (data.get("room_occupants") or {}).items() if isinstance(users, list)}
    data["room_occupants"] = {k: users for k, users in kept.items() if users}


def occupants(structure: dict) -> dict[str, list[str]]:
    """The usual occupants of each room as user ids: {area id: [user id]}, from a structure as `build` returns it. Rooms with nobody are left out."""
    return {s["area_id"]: list(s["occupants"]) for s in structure["spaces"] if s.get("area_id") and s.get("occupants")}


def rooms_of_users(by_room: dict[str, list[str]]) -> dict[str, list[str]]:
    """The other way round: {user id: [area id]}, from `occupants`."""
    out: dict[str, list[str]] = {}
    for area, users in by_room.items():
        for u in users:
            out.setdefault(u, []).append(area)
    return {u: sorted(areas) for u, areas in out.items()}


def drop_default_passage(data: dict) -> None:
    """Removes a `passage` that is just what the type gives, so that the separation keeps following the type if its default ever changes."""
    for c in data.get("connections", []):
        for s in c.get("separations", []):
            if s.get("type") in PASSAGE_AMBIGUOUS and s.get("passage") == PASSAGE_BY_TYPE[s["type"]]:
                del s["passage"]


def structural(data: dict) -> dict:
    """The part of the data that the sensors and other integrations depend on (everything but the positions on the plan and the types of room)."""
    return {k: data.get(k) for k in ("zones", "connections", "excluded_areas")}
