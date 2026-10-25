"""The writes of the Rooms page: exposure to Assist, rooms, history and undo, and the saved order of sensors."""
import pytest
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.home_structure.const import DOMAIN


async def call(client, type_, **kw):
    await client.send_json_auto_id({"type": f"{DOMAIN}/{type_}", **kw})
    return await client.receive_json()


@pytest.fixture
async def home(hass):
    assert await async_setup_component(hass, "homeassistant", {})
    areas, devices, ents = ar.async_get(hass), dr.async_get(hass), er.async_get(hass)
    salon, cuisine = areas.async_create("Salon").id, areas.async_create("Cuisine").id
    cfg = MockConfigEntry(domain="test")
    cfg.add_to_hass(hass)
    dev = devices.async_get_or_create(config_entry_id=cfg.entry_id, identifiers={("test", "d1")}, name="Thermo")
    devices.async_update_device(dev.id, area_id=salon)
    ents.async_get_or_create("sensor", "test", "t1", device_id=dev.id, original_device_class="temperature", suggested_object_id="thermo_temp")
    ents.async_get_or_create("sensor", "test", "h1", device_id=dev.id, original_device_class="humidity", suggested_object_id="thermo_hum")
    ents.async_get_or_create("sensor", "test", "t2", original_device_class="temperature", suggested_object_id="loose_temp")
    ents.async_update_entity("sensor.loose_temp", area_id=salon)
    entry = MockConfigEntry(domain=DOMAIN, data={}, title="Home Structure", options={
        "zones": [], "connections": [], "layout": {f"area:{salon}": {"x": 0, "y": 0}, f"area:{cuisine}": {"x": 1, "y": 0}}})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return {"salon": salon, "cuisine": cuisine, "device": dev.id, "entry": entry}


async def test_assist_exposure_is_written_in_home_assistant_and_undone(hass, hass_ws_client, home):
    from homeassistant.components.homeassistant.exposed_entities import async_should_expose
    client = await hass_ws_client(hass)
    from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
    async_expose_entity(hass, "conversation", "sensor.thermo_temp", False)
    async_expose_entity(hass, "conversation", "sensor.loose_temp", False)
    assert not async_should_expose(hass, "conversation", "sensor.thermo_temp")
    r = await call(client, "exposure_set", entity_id="sensor.thermo_temp", changes={"conversation": True})
    assert r["success"] and async_should_expose(hass, "conversation", "sensor.thermo_temp")
    again = await call(client, "exposure_set", entity_id="sensor.thermo_temp", changes={"conversation": True})
    assert not again["success"] and again["error"]["code"] == "nothing_to_change"
    no_alexa = await call(client, "exposure_set", entity_id="sensor.thermo_temp", changes={"alexa": True})
    assert not no_alexa["success"] and no_alexa["error"]["code"] == "assistant_unavailable"          # not enabled in the cloud
    view = (await call(client, "room_sensors"))["result"]
    first = next(r for r in view["rooms"] if r["area_id"] == home["salon"])["types"]
    assert next(g for g in first if g["type"] == "temperature")["sensors"][0]["entity_id"] == "sensor.thermo_temp"      # the exposed one comes first
    assert view["assistants"] == {"alexa": False, "google": False}
    entries = (await call(client, "history"))["result"]["entries"]
    assert entries[0]["kind"] == "exposure" and entries[0]["before"] == {"conversation": False} and entries[0]["after"] == {"conversation": True}
    undone = await call(client, "undo", entry_id=entries[0]["id"])
    assert undone["success"] and not async_should_expose(hass, "conversation", "sensor.thermo_temp")
    assert (await call(client, "undo", entry_id=entries[0]["id"]))["error"]["code"] == "already_undone"


async def test_undo_is_refused_when_the_state_changed_since(hass, hass_ws_client, home):
    from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
    client = await hass_ws_client(hass)
    async_expose_entity(hass, "conversation", "sensor.thermo_temp", False)
    r = await call(client, "exposure_set", entity_id="sensor.thermo_temp", changes={"conversation": True})
    async_expose_entity(hass, "conversation", "sensor.thermo_temp", False)                         # someone changes it in Home Assistant
    refused = await call(client, "undo", entry_id=r["result"]["id"])
    assert not refused["success"] and refused["error"]["code"] == "changed_since"


async def test_moving_a_sensor_alone_or_with_its_device(hass, hass_ws_client, home):
    ents, devices = er.async_get(hass), dr.async_get(hass)
    client = await hass_ws_client(hass)
    info = await call(client, "move_preview", entity_id="sensor.thermo_temp", area_id=home["cuisine"])
    dev = info["result"]["device"]
    assert dev["id"] == home["device"] and [o["entity_id"] for o in dev["others"]] == ["sensor.thermo_hum"]
    assert info["result"]["area_id"] == home["salon"]
    alone = await call(client, "move_apply", entity_id="sensor.thermo_temp", area_id=home["cuisine"], scope="entity")
    assert alone["success"] and ents.async_get("sensor.thermo_temp").area_id == home["cuisine"] and devices.async_get(home["device"]).area_id == home["salon"]
    back = await call(client, "move_apply", entity_id="sensor.thermo_temp", area_id=home["salon"], scope="entity")      # the room of its device: it follows the device again
    assert back["success"] and ents.async_get("sensor.thermo_temp").area_id is None
    whole = await call(client, "move_apply", entity_id="sensor.thermo_temp", area_id=home["cuisine"], scope="device")
    assert whole["success"] and devices.async_get(home["device"]).area_id == home["cuisine"] and ents.async_get("sensor.thermo_hum").area_id is None
    undone = await call(client, "undo", entry_id=whole["result"]["id"])
    assert undone["success"] and devices.async_get(home["device"]).area_id == home["salon"]
    assert (await call(client, "move_apply", entity_id="sensor.loose_temp", area_id=home["cuisine"], scope="device"))["error"]["code"] == "no_device"
    assert (await call(client, "move_apply", entity_id="sensor.thermo_temp", area_id="nowhere", scope="entity"))["error"]["code"] == "unknown_area"


async def test_the_preview_lists_automations_scripts_and_scenes_that_use_the_sensor(hass, hass_ws_client, home):
    assert await async_setup_component(hass, "automation", {"automation": [{"alias": "Cold", "trigger": {"platform": "state", "entity_id": "sensor.loose_temp"}, "action": []}]})
    assert await async_setup_component(hass, "script", {"script": {"warm": {"sequence": [{"service": "light.turn_on", "target": {"area_id": home["salon"]}}]}}})
    await hass.async_block_till_done()
    client = await hass_ws_client(hass)
    r = (await call(client, "move_preview", entity_id="sensor.loose_temp", area_id=home["cuisine"]))["result"]
    assert [a["name"] for a in r["sensor"]["automation"]] == ["Cold"]
    assert [s["entity_id"] for s in r["sensor"]["script"]] == ["script.warm"]          # it targets the room the sensor leaves
    assert r["device"] is None and r["device_refs"] is None


async def test_the_order_of_sensors_is_saved_checked_and_kept(hass, hass_ws_client, home):
    client = await hass_ws_client(hass)
    key = "sensor.temperature"
    bad = await call(client, "save_order", area_id=home["salon"], key=key, entity_ids=["sensor.thermo_temp"])
    assert not bad["success"] and bad["error"]["code"] == "invalid_order"
    ok = await call(client, "save_order", area_id=home["salon"], key=key, entity_ids=["sensor.thermo_temp", "sensor.loose_temp"])
    assert ok["success"]
    def temp(view):
        room = next(r for r in view["rooms"] if r["area_id"] == home["salon"])
        return next(g for g in room["types"] if g["key"] == key)
    g = temp((await call(client, "room_sensors"))["result"])
    assert [s["entity_id"] for s in g["sensors"]] == ["sensor.thermo_temp", "sensor.loose_temp"] and g["saved"] and g["ordered"]
    await call(client, "save", options={"zones": [], "connections": [], "layout": home["entry"].options["layout"]})      # saving the plan keeps the order
    assert home["entry"].options["sensor_order"][home["salon"]][key][0] == "sensor.thermo_temp"
    await call(client, "save_order", area_id=home["salon"], key=key, entity_ids=[])
    g = temp((await call(client, "room_sensors"))["result"])
    assert not g["saved"] and "sensor_order" in home["entry"].options and home["entry"].options["sensor_order"] == {}


async def test_only_administrators_can_write(hass, hass_ws_client, hass_read_only_access_token, home):
    client = await hass_ws_client(hass, hass_read_only_access_token)
    for type_, kw in (("exposure_set", {"entity_id": "sensor.thermo_temp", "changes": {"conversation": True}}), ("move_apply", {"entity_id": "sensor.thermo_temp", "area_id": home["cuisine"], "scope": "entity"}),
                      ("save_order", {"area_id": home["salon"], "key": "sensor.temperature", "entity_ids": []}), ("undo", {"entry_id": "x"}), ("history", {})):
        r = await call(client, type_, **kw)
        assert not r["success"] and r["error"]["code"] == "unauthorized", type_


def _group(view, area, key):
    room = next(r for r in view["rooms"] if r["area_id"] == area)
    return next(g for g in room["types"] if g["key"] == key)


async def test_sound_detections_and_other_sensors_are_hidden_by_default(hass, hass_ws_client, home):
    ents = er.async_get(hass)
    ents.async_get_or_create("binary_sensor", "frigate", "e1:audio_sensor:cam_bark", original_device_class="sound", suggested_object_id="cam_bark_sound")
    ents.async_get_or_create("binary_sensor", "sound_recognition", "sr1", suggested_object_id="sr_dog")
    ents.async_get_or_create("sensor", "test", "x1", suggested_object_id="angle_x")
    ents.async_get_or_create("binary_sensor", "test", "m1", original_device_class="motion", suggested_object_id="hall_motion")
    for eid in ("binary_sensor.cam_bark_sound", "binary_sensor.sr_dog", "sensor.angle_x", "binary_sensor.hall_motion"):
        ents.async_update_entity(eid, area_id=home["salon"])
    client = await hass_ws_client(hass)
    view = (await call(client, "room_sensors"))["result"]
    room = next(r for r in view["rooms"] if r["area_id"] == home["salon"])
    hidden = {s["entity_id"]: s["hidden"] for g in room["types"] for s in g["sensors"]}
    assert hidden["binary_sensor.cam_bark_sound"] == "sound" and hidden["binary_sensor.sr_dog"] == "sound"
    assert hidden["sensor.angle_x"] == "other"
    assert hidden["binary_sensor.hall_motion"] is None and hidden["sensor.thermo_temp"] is None and hidden["sensor.thermo_hum"] is None


async def test_the_chosen_sensor_defaults_to_assist_then_follows_the_choice_and_home_assistant(hass, hass_ws_client, home):
    from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
    client, salon, key = await hass_ws_client(hass), home["salon"], "sensor.temperature"
    async_expose_entity(hass, "conversation", "sensor.loose_temp", True)
    async_expose_entity(hass, "conversation", "sensor.thermo_temp", False)
    for eid in ("sensor.thermo_temp", "sensor.loose_temp"):
        hass.states.async_set(eid, "20", {"device_class": "temperature"})      # Home Assistant checks the sensor before keeping it on an area
    g = _group((await call(client, "room_sensors"))["result"], salon, key)
    assert (g["primary"], g["primary_source"]) == ("sensor.loose_temp", "assist")
    bad = await call(client, "primary_set", area_id=salon, key=key, entity_id="sensor.thermo_hum")
    assert not bad["success"] and bad["error"]["code"] == "unknown_entity"                       # only a sensor of that category in that room
    done = await call(client, "primary_set", area_id=salon, key=key, entity_id="sensor.thermo_temp")
    assert done["success"]
    g = _group((await call(client, "room_sensors"))["result"], salon, key)
    assert (g["primary"], g["primary_source"]) == ("sensor.thermo_temp", "native")
    assert ar.async_get(hass).async_get_area(salon).temperature_entity_id == "sensor.thermo_temp"      # written to Home Assistant itself
    assert not async_should_expose_conv(hass, "sensor.thermo_temp")                                    # exposure untouched
    hass.states.async_remove("sensor.loose_temp")
    refused = await call(client, "primary_set", area_id=salon, key=key, entity_id="sensor.loose_temp")              # a sensor Home Assistant refuses: nothing is saved
    assert not refused["success"] and refused["error"]["code"] == "native_rejected"
    assert home["entry"].options["primary_sensor"][salon][key] == "sensor.thermo_temp"
    hass.states.async_set("sensor.loose_temp", "20", {"device_class": "temperature"})
    ar.async_get(hass).async_update(salon, temperature_entity_id="sensor.loose_temp")                  # changed in Home Assistant afterwards: followed
    g = _group((await call(client, "room_sensors"))["result"], salon, key)
    assert g["primary"] == "sensor.loose_temp"
    ar.async_get(hass).async_update(salon, temperature_entity_id="sensor.thermo_temp")
    undo = await call(client, "undo", entry_id=done["result"]["id"])
    assert undo["success"] and ar.async_get(hass).async_get_area(salon).temperature_entity_id is None
    assert "sensor.thermo_temp" not in str(home["entry"].options.get("primary_sensor"))


def async_should_expose_conv(hass, eid):
    from homeassistant.components.homeassistant.exposed_entities import async_should_expose
    return async_should_expose(hass, "conversation", eid)


async def test_without_the_sync_the_choice_stays_in_home_structure_and_is_kept_when_the_plan_is_saved(hass, hass_ws_client, home):
    client, salon, key = await hass_ws_client(hass), home["salon"], "sensor.temperature"
    assert (await call(client, "primary_sync", value=False))["success"]
    assert (await call(client, "primary_set", area_id=salon, key=key, entity_id="sensor.loose_temp"))["success"]
    assert ar.async_get(hass).async_get_area(salon).temperature_entity_id is None
    view = (await call(client, "room_sensors"))["result"]
    assert view["primary_sync"] is False and _group(view, salon, key)["primary"] == "sensor.loose_temp" and _group(view, salon, key)["primary_source"] == "chosen"
    await call(client, "save", options={"zones": [], "connections": [], "layout": home["entry"].options["layout"]})
    assert home["entry"].options["primary_sensor"][salon][key] == "sensor.loose_temp" and home["entry"].options["primary_sync"] is False
    assert (await call(client, "primary_set", area_id=salon, key=key, entity_id=None))["success"]      # back to the default
    assert "primary_sensor" in home["entry"].options and home["entry"].options["primary_sensor"] == {}
    assert not (await call(client, "primary_set", area_id=salon, key=key, entity_id=None))["success"]


async def test_only_administrators_can_choose(hass, hass_ws_client, hass_read_only_access_token, home):
    client = await hass_ws_client(hass, hass_read_only_access_token)
    for type_, kw in (("primary_set", {"area_id": home["salon"], "key": "sensor.temperature", "entity_id": None}), ("primary_sync", {"value": False})):
        r = await call(client, type_, **kw)
        assert not r["success"] and r["error"]["code"] == "unauthorized", type_
