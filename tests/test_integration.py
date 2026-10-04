"""Config flow, options flow, the sensors and the service, against a real (test) Home Assistant."""
import json
import pathlib

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import area_registry as ar, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.home_structure.const import DOMAIN, SEPARATION_TYPES, ZONE_KINDS

TRANSLATIONS = pathlib.Path(__file__).parent.parent / "custom_components" / "home_structure" / "translations"


@pytest.fixture
def areas(hass):
    reg = ar.async_get(hass)
    return {n: reg.async_create(n).id for n in ("Salon", "Entrée", "Jardin", "Entrée (extérieur)")}


async def make_entry(hass, options=None):
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options if options is not None else {"zones": [], "connections": []}, title="Home Structure")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def step(hass, flow, **kw):
    return await hass.config_entries.options.async_configure(flow["flow_id"], kw)


# ------------------------------------------------------------------------------------------------ config flow
async def test_config_flow_is_one_click_and_single(hass):
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert r["type"] is FlowResultType.FORM
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
    assert r["type"] is FlowResultType.CREATE_ENTRY and r["options"] == {"zones": [], "connections": []}
    again = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert again["type"] is FlowResultType.ABORT and again["reason"] == "single_instance_allowed"


# ------------------------------------------------------------------------------------------------ options flow
async def test_describe_a_home_with_the_options_flow(hass, areas):
    entry = await make_entry(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert flow["type"] is FlowResultType.MENU and flow["menu_options"] == ["add_zone", "add_connection", "finish"]

    # the garden is a Home Assistant area: give it a kind, no new space
    r = await step(hass, flow, next_step_id="add_zone")
    r = await step(hass, r, kind="garden", area=areas["Jardin"])
    assert r["step_id"] == "zone_details"
    r = await step(hass, r, in_home=True)
    assert r["type"] is FlowResultType.MENU and "choose_zone" in r["menu_options"]
    # the building hall too, but it is not part of the home; and the street has no area at all
    r = await step(hass, r, next_step_id="add_zone")
    r = await step(hass, r, kind="hall", area=areas["Entrée (extérieur)"])
    r = await step(hass, r, in_home=False)
    r = await step(hass, r, next_step_id="add_zone")
    r = await step(hass, r, kind="street")
    r = await step(hass, r, name="  ", in_home=False)
    assert r["errors"] == {"name": "name_required"}
    r = await step(hass, r, name="Rue", in_home=False)
    # open space between living room and hall
    r = await step(hass, r, next_step_id="add_connection")
    r = await step(hass, r, a=f"area:{areas['Salon']}", b=f"area:{areas['Entrée']}")
    r = await step(hass, r, type="open_space")
    # hall door: a door with a sensor and a plain wall next to it, in one connection
    r = await step(hass, r, next_step_id="add_connection")
    r = await step(hass, r, a=f"area:{areas['Entrée']}", b=f"area:{areas['Entrée (extérieur)']}")
    r = await step(hass, r, type="door", sensor="binary_sensor.porte", add_another=True)
    assert r["step_id"] == "separation"
    r = await step(hass, r, type="wall")
    # garden: glass door and shutter
    r = await step(hass, r, next_step_id="add_connection")
    r = await step(hass, r, a=f"area:{areas['Salon']}", b=f"area:{areas['Jardin']}")
    r = await step(hass, r, type="glass_door", sensor="binary_sensor.baie", add_another=True)
    r = await step(hass, r, type="shutter", sensor="cover.volet")
    r = await step(hass, r, next_step_id="finish")
    assert r["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    opts = entry.options
    assert [(z["id"].split(":")[0], z["kind"], z["in_home"]) for z in opts["zones"]] == [("area", "garden", True), ("area", "hall", False), ("zone", "street", False)]
    assert opts["zones"][2]["name"] == "Rue"
    assert [[s["type"] for s in c["separations"]] for c in opts["connections"]] == [["open_space"], ["door", "wall"], ["glass_door", "shutter"]]
    assert opts["connections"][1]["separations"][0]["sensor"] == "binary_sensor.porte"
    # saving reloaded the entry: one sensor per separation
    assert len(hass.states.async_entity_ids("sensor")) == 5


async def test_option_errors(hass, areas):
    entry = await make_entry(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    r = await step(hass, flow, next_step_id="add_connection")
    r = await step(hass, r, a=f"area:{areas['Salon']}", b=f"area:{areas['Salon']}")
    assert r["errors"] == {"base": "same_space"}
    r = await step(hass, r, a=f"area:{areas['Salon']}", b=f"area:{areas['Entrée']}")
    r = await step(hass, r, type="wall", sensor="binary_sensor.x")
    assert r["errors"] == {"sensor": "sensor_not_needed"}
    r = await step(hass, r, type="wall")
    r = await step(hass, r, next_step_id="add_zone")
    r = await step(hass, r, kind="garden", area=areas["Jardin"])
    r = await step(hass, r, in_home=True)
    r = await step(hass, r, next_step_id="add_zone")
    r = await step(hass, r, kind="garden", area=areas["Jardin"])
    r = await step(hass, r, in_home=True)
    assert r["errors"] == {"base": "area_already_zone"}
    r = await step(hass, r, name="Salon", in_home=True)
    assert r["step_id"] == "zone_details"


async def test_same_pair_reuses_the_connection_and_edit_remove(hass, areas):
    s, e = f"area:{areas['Salon']}", f"area:{areas['Entrée']}"
    entry = await make_entry(hass, {"zones": [{"id": "zone:rue", "name": "Rue", "kind": "street", "in_home": False}],
                                    "connections": [{"id": "c1", "a": s, "b": e, "separations": [{"id": "s1", "type": "wall"}]}]})
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    r = await step(hass, flow, next_step_id="add_connection")
    r = await step(hass, r, a=e, b=s)                                     # same pair, reversed: separation added to the same connection
    r = await step(hass, r, type="door")
    r = await step(hass, r, next_step_id="choose_connection")
    r = await step(hass, r, connection="c1")
    assert r["step_id"] == "edit_connection"
    r = await step(hass, r, remove_separations=["s1"])
    r = await step(hass, r, next_step_id="finish")
    assert [x["type"] for x in entry.options["connections"][0]["separations"]] == ["door"] and len(entry.options["connections"]) == 1
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    r = await step(hass, flow, next_step_id="choose_connection")
    r = await step(hass, r, connection="c1")
    r = await step(hass, r, remove_connection=True)
    r = await step(hass, r, next_step_id="choose_zone")
    r = await step(hass, r, zone="zone:rue")
    r = await step(hass, r, remove=True)
    r = await step(hass, r, next_step_id="finish")
    assert entry.options == {"zones": [], "connections": []}


async def test_removing_a_zone_removes_its_connections(hass, areas):
    entry = await make_entry(hass, {"zones": [{"id": "zone:rue", "name": "Rue", "kind": "street", "in_home": False}],
                                    "connections": [{"id": "c1", "a": f"area:{areas['Salon']}", "b": "zone:rue", "separations": [{"id": "s1", "type": "window", "sensor": "binary_sensor.f"}]}]})
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    r = await step(hass, flow, next_step_id="choose_zone")
    r = await step(hass, r, zone="zone:rue")
    r = await step(hass, r, name="Rue", kind="street", in_home=False, remove=True)
    r = await step(hass, r, next_step_id="finish")
    assert entry.options["connections"] == [] and entry.options["zones"] == []


# ------------------------------------------------------------------------------------------------ sensors and service
async def test_sensors_follow_the_opening_sensors_and_the_service_answers(hass, areas):
    s, e, h = f"area:{areas['Salon']}", f"area:{areas['Entrée']}", f"area:{areas['Entrée (extérieur)']}"
    hass.states.async_set("binary_sensor.porte", "off")
    hass.states.async_set("cover.volet", "open", {"current_position": 100})
    entry = await make_entry(hass, {
        "zones": [{"id": f"area:{areas['Entrée (extérieur)']}", "kind": "hall", "in_home": False}],
        "connections": [{"id": "c1", "a": s, "b": e, "separations": [{"id": "s1", "type": "open_space"}]},
                        {"id": "c2", "a": e, "b": h, "separations": [{"id": "s2", "type": "door", "sensor": "binary_sensor.porte"}, {"id": "s3", "type": "shutter", "sensor": "cover.volet"}]}]})
    reg = er.async_get(hass)
    door = reg.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_s2")
    assert hass.states.get(door).state == "closed"
    assert hass.states.get(door).attributes["type"] == "door" and hass.states.get(door).attributes["name_b"] == "Entrée (extérieur)"
    assert hass.states.get(reg.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_s1")).state == "open"
    hass.states.async_set("binary_sensor.porte", "on")
    await hass.async_block_till_done()
    assert hass.states.get(door).state == "open"
    hass.states.async_set("binary_sensor.porte", "unavailable")
    await hass.async_block_till_done()
    assert hass.states.get(door).state == "unknown"
    hass.states.async_set("cover.volet", "open", {"current_position": 20})
    await hass.async_block_till_done()
    shutter = hass.states.get(reg.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_s3"))
    assert shutter.state == "partial" and shutter.attributes["position"] == 20
    assert hass.states.get(door).name.endswith("· door")

    hass.states.async_set("binary_sensor.porte", "on")
    out = await hass.services.async_call(DOMAIN, "get_structure", {}, blocking=True, return_response=True)
    sp = {x["id"]: x for x in out["spaces"]}
    assert sp[h]["kind"] == "hall" and sp[h]["in_home"] is False and sp[s]["kind"] == "room"
    seps = {x["id"]: x for c in out["connections"] for x in c["separations"]}
    assert seps["s2"]["state"] == "open" and seps["s2"]["entity_id"] == door and seps["s2"]["sensor"] == "binary_sensor.porte"
    assert seps["s3"]["state"] == "partial" and seps["s3"]["position"] == 20 and seps["s1"]["state"] == "open"


async def test_service_without_a_loaded_entry(hass):
    from homeassistant.exceptions import ServiceValidationError
    from homeassistant.setup import async_setup_component
    assert await async_setup_component(hass, DOMAIN, {})
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "get_structure", {}, blocking=True, return_response=True)


# ------------------------------------------------------------------------------------------------ translations
def _keys(d, prefix=""):
    out = set()
    for k, v in d.items():
        out |= _keys(v, f"{prefix}{k}.") if isinstance(v, dict) else {f"{prefix}{k}"}
    return out


@pytest.mark.parametrize("lang", sorted(p.stem for p in TRANSLATIONS.glob("*.json") if p.stem != "en"))
def test_every_language_has_the_keys_of_english(lang):
    en = json.loads((TRANSLATIONS / "en.json").read_text())
    other = json.loads((TRANSLATIONS / f"{lang}.json").read_text())
    assert _keys(other) == _keys(en), sorted(_keys(en) ^ _keys(other))


def test_english_covers_the_vocabulary():
    en = json.loads((TRANSLATIONS / "en.json").read_text())
    assert set(en["selector"]["zone_kind"]["options"]) == set(ZONE_KINDS)
    assert set(en["selector"]["separation_type"]["options"]) == set(SEPARATION_TYPES)
    assert {f"sep_{t}" for t in SEPARATION_TYPES} == set(en["entity"]["sensor"])
