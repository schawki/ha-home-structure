"""WebSocket commands of the editor panel."""
import pytest
from homeassistant.helpers import area_registry as ar, entity_registry as er, floor_registry as fr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.home_structure.const import DOMAIN


@pytest.fixture
def home(hass):
    floor = fr.async_get(hass).async_create("Ground")
    reg = ar.async_get(hass)
    ids = {n: reg.async_create(n, floor_id=floor.floor_id).id for n in ("Living", "Kitchen", "Garden")}
    ids["Servers"] = reg.async_create("Servers").id
    return ids


async def setup(hass, options=None):
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options or {"zones": [], "connections": []}, title="Home Structure")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def call(client, type_, **kw):
    await client.send_json_auto_id({"type": f"{DOMAIN}/{type_}", **kw})
    return await client.receive_json()


async def test_get_lists_areas_with_floors_and_the_vocabulary(hass, hass_ws_client, home):
    entry = await setup(hass)
    r = (await call(await hass_ws_client(hass), "get"))["result"]
    by = {a["name"]: a for a in r["areas"]}
    assert by["Living"]["floor"] == "Ground" and by["Servers"]["floor"] is None
    assert r["options"] == {"zones": [], "connections": [], "excluded_areas": [], "layout": {}}
    assert "glass_door" in r["types"] and "hall" in r["kinds"] and r["in_home"]["garden"] is True and r["permanent"]["wall"] == "closed"


async def test_save_keeps_placed_areas_and_leaves_the_others_in_the_tray(hass, hass_ws_client, home):
    entry = await setup(hass)
    client = await hass_ws_client(hass)
    living, kitchen, garden, servers = (f"area:{home[n]}" for n in ("Living", "Kitchen", "Garden", "Servers"))
    options = {"zones": [{"id": garden, "kind": "garden", "in_home": True}],
               "connections": [{"id": "c1", "a": living, "b": kitchen, "separations": [{"id": "s1", "type": "opening"}]},
                               {"id": "c2", "a": living, "b": servers, "separations": [{"id": "s2", "type": "wall"}]}],
               "layout": {living: {"x": 10, "y": 20}, kitchen: {"x": 200, "y": 20}, garden: {"x": 10, "y": 200}}}
    r = await call(client, "save", options=options)
    assert r["success"] and r["result"]["rebuilt"] is True
    saved = hass.config_entries.async_get_entry(entry.entry_id).options
    assert saved["excluded_areas"] == [home["Servers"]]                                   # no position = in the tray
    assert [c["id"] for c in saved["connections"]] == ["c1"]                              # its connection went with it
    assert set(saved["layout"]) == {living, kitchen, garden}


async def test_moving_a_space_does_not_rebuild_the_sensors(hass, hass_ws_client, home):
    await setup(hass)
    client = await hass_ws_client(hass)
    living = f"area:{home['Living']}"
    base = {"zones": [], "connections": [], "layout": {living: {"x": 0, "y": 0}}}
    assert (await call(client, "save", options=base))["result"]["rebuilt"] is True
    moved = {**base, "layout": {living: {"x": 50, "y": 60}}}
    r = await call(client, "save", options=moved)
    assert r["result"]["rebuilt"] is False and r["result"]["options"]["layout"][living] == {"x": 50, "y": 60}


async def test_save_refuses_an_inconsistent_structure(hass, hass_ws_client, home):
    await setup(hass)
    living = f"area:{home['Living']}"
    r = await call(await hass_ws_client(hass), "save", options={
        "layout": {living: {"x": 0, "y": 0}}, "zones": [],
        "connections": [{"id": "c", "a": living, "b": living, "separations": [{"id": "s", "type": "door"}]}]})
    assert not r["success"] and r["error"]["code"] == "invalid" and "same_space" in r["error"]["message"]


async def test_candidates_are_door_like_entities_of_the_areas(hass, hass_ws_client, home):
    await setup(hass)
    reg = er.async_get(hass)
    door = reg.async_get_or_create("binary_sensor", "t", "d", suggested_object_id="kitchen_door", original_device_class="door")
    reg.async_update_entity(door.entity_id, area_id=home["Kitchen"])
    hass.states.async_set(door.entity_id, "off", {"friendly_name": "Kitchen door"})
    client = await hass_ws_client(hass)
    r = (await call(client, "candidates", area_ids=[home["Kitchen"], home["Living"]]))["result"]
    assert r["filtered"] and [s["entity_id"] for s in r["sensors"]] == [door.entity_id] and r["sensors"][0]["name"] == "Kitchen door"
    r = (await call(client, "candidates", area_ids=[home["Garden"]]))["result"]
    assert not r["filtered"] and any(s["entity_id"] == door.entity_id for s in r["sensors"])        # nothing there: everything is offered


async def test_removed_separations_leave_no_dead_sensor(hass, hass_ws_client, home):
    living, kitchen = f"area:{home['Living']}", f"area:{home['Kitchen']}"
    entry = await setup(hass, {"zones": [], "connections": [{"id": "c", "a": living, "b": kitchen, "separations": [{"id": "s", "type": "opening"}]}]})
    reg = er.async_get(hass)
    assert len(er.async_entries_for_config_entry(reg, entry.entry_id)) == 1
    await call(await hass_ws_client(hass), "save", options={"zones": [], "connections": [], "layout": {living: {"x": 0, "y": 0}, kitchen: {"x": 1, "y": 1}}})
    await hass.async_block_till_done()
    assert er.async_entries_for_config_entry(reg, entry.entry_id) == []
