"""What other integrations read from `home_structure.get_structure` (Sound Recognition today).

These keys and values are a contract: they may be added to, never renamed, removed or given another meaning. If one of these tests has to change,
the integrations that read the structure have to change with it."""
from custom_components.home_structure import const, model

AREAS = [{"id": "salon", "name": "Salon"}, {"id": "hall", "name": "Hall"}]
DATA = {"zones": [{"id": "area:hall", "kind": "hall", "in_home": False}, {"id": "zone:rue", "name": "Rue", "kind": "street", "in_home": False}],
        "layout": {"area:salon": {"x": 10, "y": 20}},
        "room_types": {"area:salon": "living_room"},
        "connections": [{"id": "c1", "a": "area:salon", "b": "area:hall", "separations": [
            {"id": "s1", "type": "glass_door", "sensor": "binary_sensor.baie", "shutter": "cover.volet"}, {"id": "s2", "type": "wall"}]}]}
STATES = {"binary_sensor.baie": ("off", {}), "cover.volet": ("open", {"current_position": 100})}


def structure():
    return model.build(DATA, AREAS, STATES.get, {"s1": "sensor.home_structure_baie"}.get)


def test_the_structure_keeps_the_keys_consumers_read():
    out = structure()
    assert {"spaces", "connections", "layout"} <= set(out)
    for space in out["spaces"]:
        assert {"id", "name", "kind", "in_home", "area_id", "room_type", "occupants"} <= set(space)
    assert {"id", "a", "b", "a_name", "b_name", "separations"} <= set(out["connections"][0])
    for sep in out["connections"][0]["separations"]:
        assert {"id", "type", "state", "position", "sensor", "entity_id", "shutter", "shutter_state", "shutter_position"} <= set(sep)
    assert out["layout"] == {"area:salon": {"x": 10, "y": 20}}


def test_the_values_consumers_rely_on_keep_their_meaning():
    out = structure()
    ids = {s["id"]: s for s in out["spaces"]}
    assert ids["area:salon"]["area_id"] == "salon" and ids["area:salon"]["kind"] == "room" and ids["area:salon"]["room_type"] == "living_room"
    assert ids["area:hall"]["kind"] == "hall" and ids["area:hall"]["in_home"] is False and ids["zone:rue"]["area_id"] is None
    glass, wall = out["connections"][0]["separations"]
    assert (glass["state"], glass["sensor"], glass["entity_id"], glass["shutter"], glass["shutter_state"]) == ("closed", "binary_sensor.baie", "sensor.home_structure_baie", "cover.volet", "open")
    assert (wall["state"], wall["sensor"], wall["shutter"], wall["shutter_state"]) == ("closed", None, None, None)          # a wall is closed, adjacent, with no sensor


def test_the_vocabulary_only_grows():
    assert {"open_space", "opening", "door", "glass_door", "grille", "window", "shutter", "wall"} <= set(const.SEPARATION_TYPES)
    assert const.STATES == ["open", "closed", "partial"]
    assert {"garden", "balcony", "terrace", "courtyard", "garage", "hall", "stairwell", "common_area", "street", "neighbor", "other"} <= set(const.ZONE_KINDS)
