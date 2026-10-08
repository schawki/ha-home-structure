"""One sensor per separation: open, closed or partial (unknown when its sensor cannot be read)."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from . import groups as groups_mod, model, structure
from .const import DOMAIN, PERMANENT, STATES


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    names = {s["id"]: s["name"] for s in model.spaces(entry.options, structure.areas(hass))}
    wanted = {f"{entry.entry_id}_{s['id']}" for c in entry.options.get("connections", []) for s in c["separations"]}
    group_sensors = [(g, kind) for g in entry.options.get("groups", []) for kind in groups_mod.KINDS if g[kind]["mode"] != "none"]
    wanted |= {f"{entry.entry_id}_group_{g['id']}_{kind}" for g, kind in group_sensors}
    registry = er.async_get(hass)
    for reg in er.async_entries_for_config_entry(registry, entry.entry_id):       # separations that were removed leave no dead entity behind
        if reg.unique_id not in wanted:
            registry.async_remove(reg.entity_id)
    async_add_entities(
        SeparationSensor(entry, c, s, names.get(c["a"], c["a"]), names.get(c["b"], c["b"]))
        for c in entry.options.get("connections", []) for s in c["separations"]
    )
    async_add_entities(GroupSensor(entry, g, kind) for g, kind in group_sensors)


class SeparationSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATES

    def __init__(self, entry: ConfigEntry, connection: dict, sep: dict, a_name: str, b_name: str) -> None:
        self._sep, self._connection = sep, connection
        self._attr_unique_id = f"{entry.entry_id}_{sep['id']}"
        self._attr_translation_key = f"sep_{sep['type']}"
        self._attr_translation_placeholders = {"connection": f"{a_name} ↔ {b_name}"}
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name="Home Structure", entry_type=DeviceEntryType.SERVICE)
        self._names = (a_name, b_name)
        self._position: int | None = None
        self._shutter: tuple[str, int | None] = ("unknown", None)
        self._refresh()

    def _read(self, entity_id: str):
        st = self.hass.states.get(entity_id) if self.hass else None
        return (st.state, dict(st.attributes)) if st else None

    def _refresh(self) -> None:
        state, self._position = model.separation_state(self._sep, self._read)
        self._attr_native_value = state if state in STATES else None
        self._shutter = model.shutter_state(self._sep, self._read)

    @property
    def extra_state_attributes(self) -> dict:
        return {"type": self._sep["type"], "space_a": self._connection["a"], "space_b": self._connection["b"],
                "name_a": self._names[0], "name_b": self._names[1], "sensor": self._sep.get("sensor"), "position": self._position,
                "shutter": self._sep.get("shutter"), "shutter_state": self._shutter[0] if self._sep.get("shutter") else None,
                "shutter_position": self._shutter[1]}

    async def async_added_to_hass(self) -> None:
        self._refresh()
        watched = [e for e in (self._sep.get("sensor") if self._sep["type"] not in PERMANENT else None, self._sep.get("shutter")) if e]
        if watched:
            @callback
            def changed(_event) -> None:
                self._refresh()
                self.async_write_ha_state()

            self.async_on_remove(async_track_state_change_event(self.hass, watched, changed))


class GroupSensor(SensorEntity):
    """The temperature or the humidity of a group of rooms: one sensor, or the average of several (unavailable sources are ignored)."""
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: ConfigEntry, group: dict, kind: str) -> None:
        self._group, self._kind, self._cfg = group, kind, group[kind]
        self._attr_unique_id = f"{entry.entry_id}_group_{group['id']}_{kind}"
        self._attr_translation_key = f"group_{kind}"
        self._attr_translation_placeholders = {"group": group["name"]}
        self._attr_device_class = SensorDeviceClass.TEMPERATURE if kind == "temperature" else SensorDeviceClass.HUMIDITY
        self._attr_native_unit_of_measurement = groups_mod.UNIT[kind]
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name="Home Structure", entry_type=DeviceEntryType.SERVICE)
        self._sources: list[str] = []
        self._used: list[str] = []
        self._unsub_states = None

    def _read(self, entity_id: str):
        st = self.hass.states.get(entity_id)
        return (st.state, dict(st.attributes)) if st else None

    def _find_sources(self) -> list[str]:
        candidates = [s["entity_id"] for s in structure.group_sensors(self.hass, self._group["areas"], self._kind)] if self._cfg["mode"] == "all" else []
        return groups_mod.sources(self._cfg, candidates)

    def _refresh(self) -> None:
        self._attr_native_value, self._used = groups_mod.aggregate(self._kind, self._sources, self._read)

    @property
    def extra_state_attributes(self) -> dict:
        return {"group": self._group["id"], "mode": self._cfg["mode"], "area_ids": list(self._group["areas"]),
                "sources": list(self._sources), "used_sources": list(self._used)}

    def _watch(self) -> None:
        if self._unsub_states:
            self._unsub_states()
            self._unsub_states = None
        if self._sources:
            self._unsub_states = async_track_state_change_event(self.hass, self._sources, self._on_state)

    @callback
    def _on_state(self, _event) -> None:
        self._refresh()
        self.async_write_ha_state()

    @callback
    def _on_registry(self, _event) -> None:
        """An entity or a device moved to another area: the sources of an average over all the sensors of the rooms may have changed."""
        found = self._find_sources()
        if found != self._sources:
            self._sources = found
            self._watch()
            self._refresh()
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self._sources = self._find_sources()
        self._watch()
        self._refresh()
        self.async_on_remove(lambda: self._unsub_states and self._unsub_states())
        if self._cfg["mode"] == "all":
            self.async_on_remove(self.hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, self._on_registry))
            self.async_on_remove(self.hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, self._on_registry))
