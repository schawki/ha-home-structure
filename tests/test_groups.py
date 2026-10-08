"""Groups of rooms: the pure rules."""
import pytest

from custom_components.home_structure import groups as g

AREAS = {"bed": "Bedroom", "kids": "Kids", "hall": "Hall"}


def group(**kw):
    return g.normalize({"id": "night", "name": "Night", "areas": ["bed", "kids"], **kw})


def test_normalize_fills_every_field_and_cleans():
    out = g.normalize({"id": " night ", "name": " Night ", "level": 2, "icon": " mdi:bed ", "areas": ["bed", "bed", "", 3, "kids"],
                       "aliases": [" Nuit", "nuit", "", None, "Dodo"], "temperature": {"mode": "single", "entities": ["sensor.t", "sensor.t"]}, "junk": 1})
    assert out == {"id": "night", "name": "Night", "level": 2, "icon": "mdi:bed", "areas": ["bed", "kids"], "aliases": ["Nuit", "Dodo"],
                   "temperature": {"mode": "single", "entities": ["sensor.t"]}, "humidity": {"mode": "none", "entities": []}}
    blank = g.normalize({"name": "X", "level": True, "icon": 5, "areas": "no"})
    assert blank["level"] is None and blank["icon"] is None and blank["areas"] == [] and blank["id"] == ""


def test_unique_id_is_a_slug_with_a_suffix_when_taken():
    assert g.unique_id("Night part", set()) == "night_part"
    assert g.unique_id("Night part", {"night_part"}) == "night_part_2"
    assert g.unique_id("Chambres d'enfants", set()) == "chambres_d_enfants"


def test_validate():
    ids = set(AREAS)
    assert g.validate([group()], ids) == []
    assert g.validate([group(), group(name="Other")], ids) == ["duplicate_group_id"]
    assert g.validate([group(), g.normalize({"id": "x", "name": "night"})], ids) == ["duplicate_group_name"]
    assert g.validate([group(areas=["ghost"])], ids) == ["unknown_group_area"]
    assert g.validate([g.normalize({"id": "", "name": "A"})], ids) == ["invalid_group"]
    assert g.validate([group(temperature={"mode": "single", "entities": []})], ids) == ["invalid_group_sensor"]
    assert g.validate([group(temperature={"mode": "single", "entities": ["sensor.a", "sensor.b"]})], ids) == ["invalid_group_sensor"]
    assert g.validate([group(humidity={"mode": "selection", "entities": []})], ids) == ["invalid_group_sensor"]
    assert g.validate([group(humidity={"mode": "all", "entities": ["sensor.a"]})], ids) == ["invalid_group_sensor"]
    assert g.validate([group(humidity={"mode": "nope", "entities": []})], ids) == ["invalid_group_sensor"]
    assert g.validate([group(humidity={"mode": "single", "entities": ["light.a"]})], ids) == ["invalid_group_sensor"]
    assert g.validate([group(humidity={"mode": "selection", "entities": ["sensor.a", "sensor.b"]}, temperature={"mode": "all", "entities": []})], ids) == []


def test_a_room_can_be_in_several_groups_and_a_group_can_be_empty():
    assert g.validate([group(), g.normalize({"id": "kids", "name": "Kids", "areas": ["kids"]}), g.normalize({"id": "empty", "name": "Empty"})], set(AREAS)) == []


def test_prune_areas():
    groups = [group(areas=["bed", "gone", "kids"])]
    g.prune_areas(groups, set(AREAS))
    assert groups[0]["areas"] == ["bed", "kids"]


def test_prune_sensors():
    one = group(temperature={"mode": "single", "entities": ["sensor.a"]}, humidity={"mode": "selection", "entities": ["sensor.h1", "sensor.h2"]})
    assert g.prune_sensors(one, {"temperature": {"sensor.a"}, "humidity": {"sensor.h1", "sensor.h2"}}) == []
    assert g.prune_sensors(one, {"temperature": set(), "humidity": {"sensor.h2"}}) == ["temperature", "humidity"]
    assert one["temperature"] == {"mode": "none", "entities": []} and one["humidity"] == {"mode": "selection", "entities": ["sensor.h2"]}
    assert g.prune_sensors(one, {}) == ["humidity"] and one["humidity"] == {"mode": "none", "entities": []}
    every = group(temperature={"mode": "all", "entities": []})
    assert g.prune_sensors(every, {}) == [] and every["temperature"]["mode"] == "all"       # "all" is looked up every time: nothing to prune


def test_structural_ignores_the_order_of_the_groups_only():
    a, b = group(), g.normalize({"id": "day", "name": "Day"})
    assert g.structural([a, b]) == g.structural([b, a])
    assert g.structural([a]) != g.structural([group(areas=["kids", "bed"])])           # the order of the rooms shows in the attributes
    assert g.structural([a]) != g.structural([group(name="Nuit")])


def test_sources():
    assert g.sources({"mode": "none", "entities": []}, ["sensor.x"]) == []
    assert g.sources({"mode": "all", "entities": []}, ["sensor.x", "sensor.y"]) == ["sensor.x", "sensor.y"]
    assert g.sources({"mode": "single", "entities": ["sensor.a"]}, ["sensor.x"]) == ["sensor.a"]
    assert g.sources({"mode": "selection", "entities": ["sensor.a", "sensor.b"]}, ["sensor.x"]) == ["sensor.a", "sensor.b"]


@pytest.mark.parametrize("value,unit,expected", [(20, "°C", 20), (68, "°F", 20), (293.15, "K", 20), (20, None, 20)])
def test_temperature_units(value, unit, expected):
    assert g.to_unit("temperature", value, unit) == pytest.approx(expected)
    assert g.to_unit("humidity", 55, "%") == 55


def test_aggregate_averages_the_readable_sources():
    states = {"sensor.a": ("20", {"unit_of_measurement": "°C"}), "sensor.b": ("68", {"unit_of_measurement": "°F"}), "sensor.c": ("unavailable", {}),
              "sensor.d": ("unknown", {}), "sensor.e": ("abc", {}), "sensor.f": ("500", {}), "sensor.g": ("22", {})}
    value, used = g.aggregate("temperature", list(states) + ["sensor.gone"], states.get)
    assert value == 20.67 and used == ["sensor.a", "sensor.b", "sensor.g"]               # unavailable, text, absurd and missing ones are ignored
    assert g.aggregate("temperature", ["sensor.c"], states.get) == (None, [])
    assert g.aggregate("temperature", [], states.get) == (None, [])
    assert g.aggregate("temperature", ["sensor.b"], states.get) == (20.0, ["sensor.b"])
    assert g.aggregate("humidity", ["sensor.f", "sensor.g"], states.get) == (22.0, ["sensor.g"])    # 500 % is not a humidity


def test_view_lists_names_in_order_and_skips_gone_areas():
    gone = group(areas=["bed", "ghost", "kids"], temperature={"mode": "all", "entities": []}, aliases=["Nuit"], level=1, icon="mdi:bed")
    out = g.view([gone], [{"id": "bed", "name": "Bedroom"}, {"id": "kids", "name": "Kids"}], lambda gid, kind: f"sensor.{gid}_{kind}")
    assert out == [{"id": "night", "name": "Night", "level": 1, "icon": "mdi:bed", "aliases": ["Nuit"], "area_ids": ["bed", "kids"],
                    "areas": [{"id": "bed", "name": "Bedroom"}, {"id": "kids", "name": "Kids"}],
                    "temperature": {"mode": "all", "entities": [], "entity_id": "sensor.night_temperature"},
                    "humidity": {"mode": "none", "entities": [], "entity_id": None}}]
