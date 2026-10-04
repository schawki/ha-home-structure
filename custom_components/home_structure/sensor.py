"""One sensor per separation: open, closed or partial (unknown when its sensor cannot be read)."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from . import model, structure
from .const import DOMAIN, PERMANENT, STATES


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    names = {s["id"]: s["name"] for s in model.spaces(entry.options, structure.areas(hass))}
    wanted = {f"{entry.entry_id}_{s['id']}" for c in entry.options.get("connections", []) for s in c["separations"]}
    registry = er.async_get(hass)
    for reg in er.async_entries_for_config_entry(registry, entry.entry_id):       # separations that were removed leave no dead entity behind
        if reg.unique_id not in wanted:
            registry.async_remove(reg.entity_id)
    async_add_entities(
        SeparationSensor(entry, c, s, names.get(c["a"], c["a"]), names.get(c["b"], c["b"]))
        for c in entry.options.get("connections", []) for s in c["separations"]
    )


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
        self._refresh()

    def _read(self, entity_id: str):
        st = self.hass.states.get(entity_id) if self.hass else None
        return (st.state, dict(st.attributes)) if st else None

    def _refresh(self) -> None:
        state, self._position = model.separation_state(self._sep, self._read)
        self._attr_native_value = state if state in STATES else None

    @property
    def extra_state_attributes(self) -> dict:
        return {"type": self._sep["type"], "space_a": self._connection["a"], "space_b": self._connection["b"],
                "name_a": self._names[0], "name_b": self._names[1], "sensor": self._sep.get("sensor"), "position": self._position}

    async def async_added_to_hass(self) -> None:
        self._refresh()
        sensor = self._sep.get("sensor")
        if sensor and self._sep["type"] not in PERMANENT:
            @callback
            def changed(_event) -> None:
                self._refresh()
                self.async_write_ha_state()

            self.async_on_remove(async_track_state_change_event(self.hass, [sensor], changed))
