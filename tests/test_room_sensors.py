"""The Rooms page: sensors of each room by type, with Assist, HomeKit and Matter exposure (read only)."""
import pytest
from homeassistant.const import EntityCategory
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.home_structure import room_sensors as rs
from custom_components.home_structure.const import DOMAIN


def flt(**kw):
    base = {"title": "Bridge", "mode": "bridge", "include_domains": [], "exclude_domains": [], "include_entities": [], "exclude_entities": [],
            "include_entity_globs": [], "exclude_entity_globs": []}
    return {**base, **kw}


def test_homekit_filter_follows_home_assistants_rules():
    assert rs.homekit_exposes(flt(), "sensor.a")                                               # no rule: everything
    assert not rs.homekit_exposes(flt(exclude_domains=["sensor"]), "sensor.a")
    assert not rs.homekit_exposes(flt(exclude_entities=["sensor.a"]), "sensor.a")
    assert rs.homekit_exposes(flt(include_domains=["light"]), "light.x") and not rs.homekit_exposes(flt(include_domains=["light"]), "sensor.a")
    assert rs.homekit_exposes(flt(include_entities=["sensor.a"]), "sensor.a") and not rs.homekit_exposes(flt(include_entities=["sensor.a"]), "sensor.b")
    assert rs.homekit_exposes(flt(include_domains=["sensor"], exclude_entities=["sensor.b"]), "sensor.a") and not rs.homekit_exposes(flt(include_domains=["sensor"], exclude_entities=["sensor.b"]), "sensor.b")
    assert rs.homekit_exposes(flt(include_entity_globs=["sensor.salon_*"]), "sensor.salon_temp") and not rs.homekit_exposes(flt(include_entity_globs=["sensor.salon_*"]), "sensor.cuisine_temp")
    assert rs.homekit_exposes(flt(mode="accessory", include_entities=["sensor.a"]), "sensor.a") and not rs.homekit_exposes(flt(mode="accessory", include_domains=["sensor"]), "sensor.a")
    assert rs.homekit_titles([flt(title="A", include_domains=["light"]), flt(title="B")], "sensor.a") == ["B"]


def test_matter_answer_is_read_defensively():
    assert rs.parse_matter_bridges({"error": 1}) is None and rs.parse_matter_bridges(["x"]) is None
    bridges = rs.parse_matter_bridges([{"name": "Hub", "filter": {"include": [{"type": "domain", "value": "sensor"}, {"type": "mystery", "value": 1}],
                                                                  "exclude": [{"type": "pattern", "value": "sensor.hidden_*"}]}}, {"id": "empty"}])
    info = {"entity_id": "sensor.a", "domain": "sensor", "platform": "x", "device_class": None, "area_id": None, "device_id": None, "labels": []}
    assert rs.matter_titles(bridges, info) == ["Hub"]
    assert rs.matter_titles(bridges, {**info, "entity_id": "sensor.hidden_b"}) == []
    assert rs.matter_titles(bridges, {**info, "entity_id": "light.a", "domain": "light"}) == []      # a rule that is not understood matches nothing
    assert rs.matter_titles(bridges[1:], info) == []                                                    # a bridge with no include exposes nothing


def test_grouping_puts_the_assist_sensor_first_and_orders_only_pairs():
    def s(i, cls, assist, name=None):
        return {"entity_id": f"sensor.{i}", "name": name or i, "domain": "sensor", "type": cls, "assist": assist}
    groups = rs.grouped([s("b", "temperature", False), s("a", "temperature", False), s("z", "temperature", True), s("h", "humidity", False), s("x", rs.OTHER, False)])
    by = {g["type"]: g for g in groups}
    assert [x["entity_id"] for x in by["temperature"]["sensors"]] == ["sensor.z", "sensor.a", "sensor.b"]
    assert by["temperature"]["ordered"] and by["temperature"]["assist_first"] is True
    assert not by["humidity"]["ordered"] and by["humidity"]["assist_first"] is None
    assert groups[-1]["type"] == rs.OTHER                                                               # sensors with no class come last


@pytest.fixture
def home(hass):
    areas, devices, ents = ar.async_get(hass), dr.async_get(hass), er.async_get(hass)
    salon = areas.async_create("Salon")
    entry = MockConfigEntry(domain="test")
    entry.add_to_hass(hass)
    dev = devices.async_get_or_create(config_entry_id=entry.entry_id, identifiers={("test", "d1")}, name="Thermo")
    devices.async_update_device(dev.id, area_id=salon.id)
    ents.async_get_or_create("sensor", "test", "t1", device_id=dev.id, original_device_class="temperature", suggested_object_id="thermo_temp")
    ents.async_get_or_create("sensor", "test", "t2", original_device_class="temperature", suggested_object_id="other_temp")
    ents.async_update_entity("sensor.other_temp", area_id=salon.id)
    ents.async_get_or_create("sensor", "test", "diag", device_id=dev.id, entity_category=EntityCategory.DIAGNOSTIC, suggested_object_id="thermo_diag")
    ents.async_get_or_create("binary_sensor", "test", "m1", original_device_class="motion", suggested_object_id="loose_motion")
    return salon.id


async def test_service_lists_rooms_types_and_loose_sensors(hass, home):
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={"zones": [], "connections": [], "layout": {f"area:{home}": {"x": 0, "y": 0}}, "room_occupants": {f"area:{home}": ["u"]}}, title="Home Structure")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    view = await hass.services.async_call(DOMAIN, "get_room_sensors", {}, blocking=True, return_response=True)
    room = next(r for r in view["rooms"] if r["area_id"] == home)
    assert [t["type"] for t in room["types"]] == ["temperature"] and {s["entity_id"] for s in room["types"][0]["sensors"]} == {"sensor.thermo_temp", "sensor.other_temp"}
    assert room["types"][0]["ordered"] and room["occupants"] == []        # "u" is not a user: unknown users are left out
    assert [s["entity_id"] for s in view["unassigned"]] == ["binary_sensor.loose_motion"]
    assert "sensor.thermo_diag" not in str(view)                           # diagnostic entities are left out
    assert view["matter"] == {"available": False, "bridges": []} and view["homekit"] == []


async def test_room_entities_by_type_with_their_room_and_the_exclusions(hass):
    from homeassistant.const import EntityCategory
    areas, devices, ents = ar.async_get(hass), dr.async_get(hass), er.async_get(hass)
    salon, cuisine = areas.async_create("Salon").id, areas.async_create("Cuisine").id
    cfg = MockConfigEntry(domain="test")
    cfg.add_to_hass(hass)
    dev = devices.async_get_or_create(config_entry_id=cfg.entry_id, identifiers={("test", "tv")}, name="TV")
    devices.async_update_device(dev.id, area_id=salon)
    ents.async_get_or_create("media_player", "test", "tv", device_id=dev.id, suggested_object_id="tv")
    ents.async_get_or_create("light", "test", "l1", suggested_object_id="lamp")
    ents.async_update_entity("light.lamp", area_id=cuisine)
    ents.async_get_or_create("light", "test", "l2", suggested_object_id="loose_light")
    ents.async_get_or_create("switch", "test", "s1", entity_category=EntityCategory.CONFIG, suggested_object_id="tv_setting")
    ents.async_get_or_create("sensor", "test", "x", suggested_object_id="temp")
    entry = MockConfigEntry(domain=DOMAIN, data={}, title="Home Structure", options={"zones": [], "connections": [], "layout": {f"area:{salon}": {"x": 0, "y": 0}, f"area:{cuisine}": {"x": 1, "y": 0}}})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    view = await hass.services.async_call(DOMAIN, "get_room_entities", {}, blocking=True, return_response=True)
    room = {r["area_id"]: r for r in view["rooms"]}
    assert [e["entity_id"] for e in room[salon]["entities"]["media_player"]] == ["media_player.tv"]                  # through its device
    assert room[salon]["entities"]["media_player"][0]["device_name"] == "TV" and "domain" not in room[salon]["entities"]["media_player"][0]
    assert [e["entity_id"] for e in room[cuisine]["entities"]["light"]] == ["light.lamp"]                              # its own room
    assert [e["entity_id"] for e in view["unassigned"]["light"]] == ["light.loose_light"]
    assert "switch" not in str(view) and "sensor" not in str(view)                                                    # configuration entities and sensors are left out
    only = await hass.services.async_call(DOMAIN, "get_room_entities", {"domains": ["LIGHT"]}, blocking=True, return_response=True)
    assert set(room_domains := {d for r in only["rooms"] for d in r["entities"]}) == {"light"}
    both = await hass.services.async_call(DOMAIN, "get_room_entities", {"domains": ["sensor", "media_player"]}, blocking=True, return_response=True)
    assert {d for r in both["rooms"] for d in r["entities"]} | set(both["unassigned"]) == {"sensor", "media_player"}
