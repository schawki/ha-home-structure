"""The structure as Home Assistant sees it now: the registries and the states are read, the model does the rest."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, entity_registry as er

from . import model
from .const import DOMAIN


def areas(hass: HomeAssistant) -> list[dict]:
    return sorted(({"id": a.id, "name": a.name} for a in ar.async_get(hass).async_list_areas()), key=lambda a: a["name"].casefold())


def current(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    registry = er.async_get(hass)

    def read(entity_id: str):
        st = hass.states.get(entity_id)
        return (st.state, dict(st.attributes)) if st else None

    return model.build(entry.options, areas(hass), read,
                       lambda sid: registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{sid}"))
