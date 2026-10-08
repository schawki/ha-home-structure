"""Groups of rooms against a real (test) Home Assistant: the commands of the panel, the sensors and the service."""
import pytest
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.home_structure.const import DOMAIN


@pytest.fixture
def home(hass):
    reg = ar.async_get(hass)
    return {n: reg.async_create(n).id for n in ("Bedroom", "Kids", "Living", "Office")}


def add_sensor(hass, home, name, area, device_class, state, unit=None, **reg_kw):
    reg = er.async_get(hass)
    ent = reg.async_get_or_create("sensor", "test", name, suggested_object_id=name, original_device_class=device_class)
    reg.async_update_entity(ent.entity_id, area_id=home[area] if area else None, **reg_kw)
    attrs = {"friendly_name": name, **({"unit_of_measurement": unit} if unit else {})}
    hass.states.async_set(ent.entity_id, state, attrs)
    return ent.entity_id


async def setup(hass, groups=None):
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={"zones": [], "connections": [], **({"groups": groups} if groups is not None else {})}, title="Home Structure")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def call(client, type_, **kw):
    await client.send_json_auto_id({"type": f"{DOMAIN}/{type_}", **kw})
    return await client.receive_json()


def group(gid, name, areas, **kw):
    return {"id": gid, "name": name, "areas": areas, **kw}


async def test_get_returns_the_groups_and_the_modes(hass, hass_ws_client, home):
    await setup(hass)
    r = (await call(await hass_ws_client(hass), "get"))["result"]
    assert r["options"]["groups"] == [] and r["group_modes"] == ["none", "single", "all", "selection"]


async def test_save_groups_normalizes_gives_ids_and_keeps_the_order(hass, hass_ws_client, home):
    entry = await setup(hass)
    client = await hass_ws_client(hass)
    r = await call(client, "save_groups", groups=[group("", " Night part ", [home["Bedroom"], home["Kids"]], aliases=["Nuit"], level=1),
                                                  group("day", "Day", [home["Living"], home["Bedroom"]])])      # a room in two groups
    assert r["success"] and r["result"]["pruned"] == []
    saved = hass.config_entries.async_get_entry(entry.entry_id).options["groups"]
    assert [g["id"] for g in saved] == ["night_part", "day"] and saved[0]["name"] == "Night part" and saved[0]["aliases"] == ["Nuit"] and saved[0]["level"] == 1
    assert saved[1]["areas"] == [home["Living"], home["Bedroom"]] and saved[0]["temperature"] == {"mode": "none", "entities": []}
    again = await call(client, "save_groups", groups=list(reversed(saved)))
    assert again["success"] and again["result"]["rebuilt"] is False                       # only the order changed: nothing is rebuilt
    assert [g["id"] for g in hass.config_entries.async_get_entry(entry.entry_id).options["groups"]] == ["day", "night_part"]


async def test_save_groups_refuses_inconsistent_groups_and_drops_gone_areas(hass, hass_ws_client, home):
    entry = await setup(hass)
    client = await hass_ws_client(hass)
    bad = await call(client, "save_groups", groups=[group("a", "Same", []), group("b", "same", [])])
    assert not bad["success"] and bad["error"]["code"] == "invalid" and "duplicate_group_name" in bad["error"]["message"]
    bad = await call(client, "save_groups", groups=[group("a", "A", [], temperature={"mode": "single", "entities": []})])
    assert not bad["success"] and "invalid_group_sensor" in bad["error"]["message"]
    ok = await call(client, "save_groups", groups=[group("a", "A", [home["Office"], "deleted_area"])])
    assert ok["success"] and ok["result"]["groups"][0]["areas"] == [home["Office"]]        # an area deleted in Home Assistant is simply dropped


async def test_saving_the_plan_never_overwrites_the_groups(hass, hass_ws_client, home):
    entry = await setup(hass, [group("night", "Night", [home["Bedroom"]], aliases=[], level=None, icon=None,
                                     temperature={"mode": "none", "entities": []}, humidity={"mode": "none", "entities": []})])
    client = await hass_ws_client(hass)
    r = await call(client, "save", options={"zones": [], "connections": [], "layout": {f"area:{home['Living']}": {"x": 0, "y": 0}}})
    assert r["success"] and r["result"]["options"]["groups"][0]["id"] == "night"
    assert hass.config_entries.async_get_entry(entry.entry_id).options["groups"][0]["areas"] == [home["Bedroom"]]
    await call(client, "save_groups", groups=[])
    r = await call(client, "save", options={"zones": [], "connections": [], "groups": [group("old", "Old", [])], "layout": {}})
    assert hass.config_entries.async_get_entry(entry.entry_id).options["groups"] == []     # the groups of a plan save are ignored


async def test_group_sensors_lists_the_temperature_sensors_of_the_rooms_without_diagnostics(hass, hass_ws_client, home):
    await setup(hass)
    t = add_sensor(hass, home, "bed_temp", "Bedroom", "temperature", "21", "°C")
    kids = add_sensor(hass, home, "kids_temp", "Kids", "temperature", "70", "°F")
    add_sensor(hass, home, "bed_cpu", "Bedroom", "temperature", "50", "°C", entity_category=er.EntityCategory.DIAGNOSTIC)
    add_sensor(hass, home, "bed_hidden", "Bedroom", "temperature", "50", "°C", hidden_by=er.RegistryEntryHider.USER)
    add_sensor(hass, home, "living_temp", "Living", "temperature", "23", "°C")
    add_sensor(hass, home, "bed_hum", "Bedroom", "humidity", "50", "%")
    add_sensor(hass, home, "nowhere", None, "temperature", "19", "°C")
    client = await hass_ws_client(hass)
    r = (await call(client, "group_sensors", area_ids=[home["Bedroom"], home["Kids"]], kind="temperature"))["result"]["sensors"]
    assert [s["entity_id"] for s in r] == [t, kids] and r[1]["unit"] == "°F" and r[0]["area"] == "Bedroom" and r[0]["state"] == "21"
    assert [s["entity_id"] for s in (await call(client, "group_sensors", area_ids=[home["Bedroom"]], kind="humidity"))["result"]["sensors"]] == ["sensor.bed_hum"]
    assert not (await call(client, "group_sensors", area_ids=[], kind="pressure"))["success"]


async def test_a_sensor_of_the_device_counts_for_the_area_of_the_device(hass, hass_ws_client, home):
    await setup(hass)
    entry = MockConfigEntry(domain="test")
    entry.add_to_hass(hass)
    dev = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, identifiers={("test", "d")})
    dr.async_get(hass).async_update_device(dev.id, area_id=home["Kids"])
    ent = er.async_get(hass).async_get_or_create("sensor", "test", "dev_temp", suggested_object_id="dev_temp", device_id=dev.id, original_device_class="temperature")
    hass.states.async_set(ent.entity_id, "20", {"unit_of_measurement": "°C"})
    r = (await call(await hass_ws_client(hass), "group_sensors", area_ids=[home["Kids"]], kind="temperature"))["result"]["sensors"]
    assert [s["entity_id"] for s in r] == [ent.entity_id]


async def test_removing_a_room_drops_the_sensors_that_left_with_it(hass, hass_ws_client, home):
    await setup(hass)
    t1 = add_sensor(hass, home, "bed_temp", "Bedroom", "temperature", "21", "°C")
    t2 = add_sensor(hass, home, "kids_temp", "Kids", "temperature", "23", "°C")
    h = add_sensor(hass, home, "bed_hum", "Bedroom", "humidity", "50", "%")
    client = await hass_ws_client(hass)
    full = group("night", "Night", [home["Bedroom"], home["Kids"]], temperature={"mode": "selection", "entities": [t1, t2]}, humidity={"mode": "single", "entities": [h]})
    assert (await call(client, "save_groups", groups=[full]))["result"]["pruned"] == []
    r = (await call(client, "save_groups", groups=[{**full, "areas": [home["Kids"]]}]))["result"]
    g = r["groups"][0]
    assert r["pruned"] == ["night"] and g["temperature"] == {"mode": "selection", "entities": [t2]} and g["humidity"] == {"mode": "none", "entities": []}


async def test_sensors_of_a_group(hass, hass_ws_client, home):
    t1 = add_sensor(hass, home, "bed_temp", "Bedroom", "temperature", "21", "°C")
    t2 = add_sensor(hass, home, "kids_temp", "Kids", "temperature", "70", "°F")
    add_sensor(hass, home, "bed_cpu", "Bedroom", "temperature", "99", "°C", entity_category=er.EntityCategory.DIAGNOSTIC)
    h1 = add_sensor(hass, home, "bed_hum", "Bedroom", "humidity", "40", "%")
    h2 = add_sensor(hass, home, "kids_hum", "Kids", "humidity", "60", "%")
    areas = [home["Bedroom"], home["Kids"]]
    entry = await setup(hass, [])
    client = await hass_ws_client(hass)
    r = await call(client, "save_groups", groups=[
        group("avg", "Everything", areas, temperature={"mode": "all", "entities": []}, humidity={"mode": "selection", "entities": [h1, h2]}),
        group("one", "One", areas, temperature={"mode": "single", "entities": [t1]}),
        group("quiet", "Quiet", areas)])
    assert r["success"] and r["result"]["rebuilt"] is True
    await hass.async_block_till_done()
    reg = er.async_get(hass)
    ids = {e.unique_id: e.entity_id for e in er.async_entries_for_config_entry(reg, entry.entry_id)}
    assert set(ids) == {f"{entry.entry_id}_group_avg_temperature", f"{entry.entry_id}_group_avg_humidity", f"{entry.entry_id}_group_one_temperature"}   # none: no entity
    avg = hass.states.get(ids[f"{entry.entry_id}_group_avg_temperature"])
    assert float(avg.state) == pytest.approx(21.06, abs=0.01)                 # 21 °C and 70 °F (= 21.11 °C); the diagnostic sensor is not read
    assert avg.attributes["sources"] == [t1, t2] and avg.attributes["mode"] == "all" and avg.attributes["area_ids"] == areas and avg.attributes["group"] == "avg"
    assert avg.attributes["device_class"] == "temperature"
    assert float(hass.states.get(ids[f"{entry.entry_id}_group_avg_humidity"]).state) == 50.0
    one = hass.states.get(ids[f"{entry.entry_id}_group_one_temperature"])
    assert float(one.state) == 21.0 and one.attributes["sources"] == [t1]
    assert one.name == "Home Structure One · temperature" or one.name.endswith("One · temperature")
    # live: a source changes, another becomes unavailable
    hass.states.async_set(t1, "23", {"unit_of_measurement": "°C"})
    hass.states.async_set(t2, "unavailable", {})
    await hass.async_block_till_done()
    avg = hass.states.get(ids[f"{entry.entry_id}_group_avg_temperature"])
    assert float(avg.state) == 23.0 and avg.attributes["used_sources"] == [t1]
    hass.states.async_set(t1, "unavailable", {})
    await hass.async_block_till_done()
    assert hass.states.get(ids[f"{entry.entry_id}_group_avg_temperature"]).state == "unknown"


async def test_average_over_all_follows_sensors_moved_between_rooms(hass, hass_ws_client, home):
    t1 = add_sensor(hass, home, "bed_temp", "Bedroom", "temperature", "20", "°C")
    t2 = add_sensor(hass, home, "living_temp", "Living", "temperature", "30", "°C")
    entry = await setup(hass, [])
    await call(await hass_ws_client(hass), "save_groups", groups=[group("night", "Night", [home["Bedroom"]], temperature={"mode": "all", "entities": []})])
    await hass.async_block_till_done()
    entity = next(e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id))
    assert float(hass.states.get(entity).state) == 20.0
    er.async_get(hass).async_update_entity(t2, area_id=home["Bedroom"])        # the living-room sensor is moved into the bedroom
    await hass.async_block_till_done()
    assert float(hass.states.get(entity).state) == 25.0 and hass.states.get(entity).attributes["sources"] == [t1, t2]


async def test_removed_groups_leave_no_dead_entity(hass, hass_ws_client, home):
    t = add_sensor(hass, home, "bed_temp", "Bedroom", "temperature", "20", "°C")
    entry = await setup(hass, [])
    client = await hass_ws_client(hass)
    await call(client, "save_groups", groups=[group("night", "Night", [home["Bedroom"]], temperature={"mode": "single", "entities": [t]})])
    await hass.async_block_till_done()
    assert len(er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)) == 1
    await call(client, "save_groups", groups=[])
    await hass.async_block_till_done()
    assert er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id) == []


async def test_get_groups_service(hass, hass_ws_client, home):
    t = add_sensor(hass, home, "bed_temp", "Bedroom", "temperature", "20", "°C")
    entry = await setup(hass, [])
    await call(await hass_ws_client(hass), "save_groups", groups=[
        group("night", "Night", [home["Kids"], home["Bedroom"]], aliases=["Nuit"], icon="mdi:bed", temperature={"mode": "single", "entities": [t]}),
        group("empty", "Empty", [])])
    await hass.async_block_till_done()
    out = await hass.services.async_call(DOMAIN, "get_groups", {}, blocking=True, return_response=True)
    night, empty = out["groups"]
    assert night["area_ids"] == [home["Kids"], home["Bedroom"]] and [a["name"] for a in night["areas"]] == ["Kids", "Bedroom"] and night["aliases"] == ["Nuit"]
    assert night["temperature"]["entity_id"].startswith("sensor.") and night["temperature"]["mode"] == "single" and night["humidity"]["entity_id"] is None
    assert empty["area_ids"] == [] and empty["icon"] is None
