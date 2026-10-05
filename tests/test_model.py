"""The model: spaces, validation, states of separations."""
import pytest

from custom_components.home_structure import model

AREAS = [{"id": "salon", "name": "Salon"}, {"id": "entree", "name": "Entrée"}, {"id": "jardin", "name": "Jardin"}, {"id": "hall", "name": "Entrée (extérieur)"}]
DATA = {
    "zones": [{"id": "area:jardin", "kind": "garden", "in_home": True}, {"id": "area:hall", "kind": "hall", "in_home": False},
              {"id": "zone:rue", "name": "Rue", "kind": "street", "in_home": False}],
    "connections": [
        {"id": "c1", "a": "area:salon", "b": "area:entree", "separations": [{"id": "s1", "type": "open_space"}]},
        {"id": "c2", "a": "area:entree", "b": "area:hall", "separations": [{"id": "s2", "type": "door", "sensor": "binary_sensor.porte"}, {"id": "s3", "type": "wall"}]},
        {"id": "c3", "a": "area:salon", "b": "area:jardin", "separations": [{"id": "s4", "type": "glass_door", "sensor": "cover.baie"}, {"id": "s5", "type": "shutter", "sensor": "cover.volet"}]},
    ],
}


def test_spaces_rooms_areas_with_a_kind_and_virtual_zones():
    by = {s["id"]: s for s in model.spaces(DATA, AREAS)}
    assert by["area:salon"]["kind"] == "room" and by["area:salon"]["in_home"] is True
    assert by["area:jardin"]["kind"] == "garden" and by["area:jardin"]["in_home"] is True and by["area:jardin"]["name"] == "Jardin"
    assert by["area:hall"]["kind"] == "hall" and by["area:hall"]["in_home"] is False and by["area:hall"]["name"] == "Entrée (extérieur)"
    assert by["zone:rue"] == {"id": "zone:rue", "name": "Rue", "kind": "street", "in_home": False, "area_id": None}
    assert len(by) == 5


def test_zone_ids_are_unique_slugs():
    assert model.unique_zone_id("Appartement Voisin", set()) == "zone:appartement_voisin"
    assert model.unique_zone_id("Rue", {"zone:rue"}) == "zone:rue_2"
    assert model.unique_zone_id("é!", set()) == "zone:e"


def test_validate():
    ids = {a["id"] for a in AREAS}
    assert model.validate(DATA, ids) == []
    bad = {"zones": [{"id": "zone:a", "name": "A", "kind": "garden", "in_home": True}, {"id": "zone:b", "name": "a", "kind": "nope", "in_home": True}],
           "connections": [{"id": "x", "a": "zone:a", "b": "zone:a", "separations": []}, {"id": "y", "a": "zone:a", "b": "area:ghost", "separations": [{"id": "1", "type": "wall", "sensor": "binary_sensor.x"}, {"id": "2", "type": "teleporter"}]}]}
    assert model.validate(bad, ids) == ["duplicate_zone_name", "invalid_separation", "invalid_zone", "no_separation", "same_space", "sensor_not_needed", "unknown_space"]
    twice = {"zones": [], "connections": [{"id": "1", "a": "area:salon", "b": "area:entree", "separations": [{"id": "s", "type": "wall"}]},
                      {"id": "2", "a": "area:entree", "b": "area:salon", "separations": [{"id": "t", "type": "wall"}]}]}
    assert model.validate(twice, ids) == ["duplicate_connection"]
    assert model.validate({"zones": [{"id": "area:gone", "kind": "garden", "in_home": True}], "connections": []}, ids) == ["unknown_area"]


@pytest.mark.parametrize("state,attrs,expected", [
    ("on", {}, ("open", None)), ("off", {}, ("closed", None)), ("unavailable", {}, ("unknown", None)), ("unknown", {}, ("unknown", None)), (None, {}, ("unknown", None)),
    ("open", {}, ("open", None)), ("closed", {}, ("closed", None)), ("opening", {}, ("partial", None)), ("closing", {}, ("partial", None)),
    ("open", {"current_position": 100}, ("open", 100)), ("closed", {"current_position": 0}, ("closed", 0)),
    ("open", {"current_position": 40}, ("partial", 40)), ("open", {"current_position": 250}, ("open", 100)), ("closed", {"current_position": -3}, ("closed", 0)),
    ("weird", {}, ("unknown", None)),
])
def test_normalize(state, attrs, expected):
    assert model.normalize(state, attrs) == expected


def test_build_reads_states_and_fixed_types():
    states = {"binary_sensor.porte": ("on", {}), "cover.volet": ("open", {"current_position": 30})}
    out = model.build(DATA, AREAS, states.get, {"s1": "sensor.a"}.get)
    c = {c["id"]: c for c in out["connections"]}
    assert c["c1"]["separations"][0] == {"id": "s1", "type": "open_space", "state": "open", "position": None, "sensor": None, "entity_id": "sensor.a",
                                            "shutter": None, "shutter_state": None, "shutter_position": None}
    s2, s3 = c["c2"]["separations"]
    assert (s2["state"], s3["state"]) == ("open", "closed")                                  # door open, plain wall: adjacent, no passage
    glass, shutter = c["c3"]["separations"]
    assert glass["state"] == "unknown"                                                       # sensor missing from the states
    assert (shutter["state"], shutter["position"]) == ("partial", 30)
    assert c["c2"]["a_name"] == "Entrée" and c["c2"]["b_name"] == "Entrée (extérieur)"
    assert out["layout"] == {}                                                              # positions on the editor plan, for consumers that draw it
    assert model.neighbours(out, "area:salon") == ["area:entree", "area:jardin"]
    assert model.neighbours(out, "zone:rue") == []


def test_defaults_by_kind():
    assert model.default_in_home("garden") and model.default_in_home("balcony")
    assert not model.default_in_home("street") and not model.default_in_home("hall") and not model.default_in_home("neighbor")


def test_excluded_areas_are_not_spaces_and_their_connections_go():
    data = {k: list(v) for k, v in DATA.items()}
    model.exclude_areas(data, {"jardin"})
    ids = {s["id"] for s in model.spaces(data, AREAS)}
    assert "area:jardin" not in ids and data["excluded_areas"] == ["jardin"]
    assert all("area:jardin" not in (c["a"], c["b"]) for c in data["connections"]) and "area:jardin" not in {z["id"] for z in data["zones"]}
    assert model.validate(data, {a["id"] for a in AREAS}) == []


def test_set_area_kinds_in_bulk_keeps_what_is_unchanged():
    data = {"zones": [{"id": "area:jardin", "kind": "garden", "in_home": False, "name": "Mon jardin"}], "connections": []}
    model.set_area_kinds(data, {"garden": ["jardin"], "hall": ["hall"]}, keep=set())
    by = {z["id"]: z for z in data["zones"]}
    assert by["area:jardin"]["in_home"] is False and by["area:jardin"]["name"] == "Mon jardin"   # same kind: untouched
    assert by["area:hall"] == {"id": "area:hall", "kind": "hall", "in_home": False}              # in_home follows the kind
    model.set_area_kinds(data, {"garden": []}, keep=set())
    assert data["zones"] == []


def test_connect_many_skips_existing_pairs():
    data = {"zones": [], "connections": [{"id": "c", "a": "area:salon", "b": "area:entree", "separations": [{"id": "s", "type": "wall"}]}]}
    n = iter(range(100))
    made = model.connect_many(data, "area:salon", ["area:entree", "area:jardin", "area:salon"], "opening", lambda: f"i{next(n)}")
    assert [(c["a"], c["b"]) for c in made] == [("area:salon", "area:jardin")] and len(data["connections"]) == 2
    assert data["connections"][0]["separations"] == [{"id": "s", "type": "wall"}]                # untouched


def test_a_shutter_sits_in_front_of_a_door_a_glass_door_or_a_window():
    data = {"zones": [], "connections": [{"id": "c", "a": "area:salon", "b": "area:jardin", "separations": [
        {"id": "s1", "type": "glass_door", "sensor": "binary_sensor.baie", "shutter": "cover.volet"}, {"id": "s2", "type": "grille"}]}]}
    assert model.validate(data, {"salon", "jardin"}) == []
    states = {"binary_sensor.baie": ("off", {}), "cover.volet": ("open", {"current_position": 40})}
    glass, grille = model.build(data, AREAS, states.get)["connections"][0]["separations"]
    assert glass["state"] == "closed" and glass["shutter"] == "cover.volet" and glass["shutter_state"] == "partial" and glass["shutter_position"] == 40
    assert grille["state"] == "unknown" and grille["shutter"] is None and grille["shutter_state"] is None   # a grille may have a sensor but its state barely matters
    assert model.shutter_state({"shutter": "cover.volet"}, {}.get) == ("unknown", None)                       # cover missing


@pytest.mark.parametrize("sep", [{"type": "wall", "shutter": "cover.v"}, {"type": "grille", "shutter": "cover.v"}, {"type": "door", "shutter": "binary_sensor.v"}])
def test_a_shutter_must_be_a_cover_on_a_door_or_window(sep):
    data = {"zones": [], "connections": [{"id": "c", "a": "area:salon", "b": "area:jardin", "separations": [{"id": "s", **sep}]}]}
    assert model.validate(data, {"salon", "jardin"}) == ["invalid_shutter"]
