"""Config flow (one click) and options flow: zones outside the rooms, connections between spaces, and what separates them.

The options flow works on a copy of the structure and saves it when the user chooses "Save and close"."""
from __future__ import annotations

import copy
import uuid
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers import selector as sel

from . import model, structure
from .const import DOMAIN, PERMANENT, SENSOR_DOMAINS, SEPARATION_TYPES, ZONE_KINDS


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _select(options: list, key: str | None = None, multiple: bool = False) -> sel.SelectSelector:
    cfg: dict = {"options": options, "multiple": multiple, "mode": sel.SelectSelectorMode.DROPDOWN}
    if key:
        cfg["translation_key"] = key
    return sel.SelectSelector(sel.SelectSelectorConfig(**cfg))


class HomeStructureConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Home Structure", data={}, options={"zones": [], "connections": []})
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> HomeStructureOptionsFlow:
        return HomeStructureOptionsFlow()


class HomeStructureOptionsFlow(OptionsFlowWithReload):
    def __init__(self) -> None:
        self._data: dict = {}
        self._zone: dict | None = None        # zone being added
        self._edit_zone: str | None = None
        self._conn: dict | None = None        # connection receiving separations
        self._kind = ""

    # ------------------------------------------------------------------ helpers
    @property
    def data(self) -> dict:
        return self._data

    def _spaces(self) -> list[dict]:
        return model.spaces(self._data, structure.areas(self.hass))

    def _space_options(self) -> list[dict]:
        return [{"value": s["id"], "label": s["name"]} for s in sorted(self._spaces(), key=lambda s: s["name"].casefold())]

    def _name(self, space_id: str) -> str:
        return next((s["name"] for s in self._spaces() if s["id"] == space_id), space_id)

    def _label(self, c: dict) -> str:
        return f"{self._name(c['a'])} ↔ {self._name(c['b'])}"

    # ------------------------------------------------------------------ menu
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not self._data:
            self._data = copy.deepcopy({"zones": [], "connections": [], **self.config_entry.options})
        menu = ["add_zone"]
        if self._data["zones"]:
            menu.append("choose_zone")
        menu.append("add_connection")
        if self._data["connections"]:
            menu.append("choose_connection")
        menu.append("finish")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_finish(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors = model.validate(self._data, {a["id"] for a in structure.areas(self.hass)})
        if errors:
            return self.async_abort(reason=errors[0])
        return self.async_create_entry(data=self._data)

    # ------------------------------------------------------------------ zones
    async def async_step_add_zone(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Kind of the new zone, and the Home Assistant area it is, if it already exists as one (garden, balcony…)."""
        if user_input is not None:
            self._zone = {"kind": user_input["kind"], "area": user_input.get("area")}
            return await self.async_step_zone_details()
        schema = vol.Schema({vol.Required("kind", default="garden"): _select(ZONE_KINDS, "zone_kind"),
                             vol.Optional("area"): sel.AreaSelector()})
        return self.async_show_form(step_id="add_zone", data_schema=schema)

    async def async_step_zone_details(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._zone is not None
        errors: dict[str, str] = {}
        area = self._zone["area"]
        if user_input is not None:
            name = (user_input.get("name") or "").strip()
            taken = {s["name"].casefold() for s in self._spaces()}
            if not area and not name:
                errors["name"] = "name_required"
            elif name and name.casefold() in taken and not (area and name.casefold() == self._name(f"area:{area}").casefold()):
                errors["name"] = "duplicate_zone_name"
            elif area and f"area:{area}" in {z["id"] for z in self._data["zones"]}:
                errors["base"] = "area_already_zone"
            if not errors:
                zid = f"area:{area}" if area else model.unique_zone_id(name, {z["id"] for z in self._data["zones"]})
                zone = {"id": zid, "kind": self._zone["kind"], "in_home": user_input["in_home"]}
                if name:
                    zone["name"] = name
                self._data["zones"].append(zone)
                self._zone = None
                return await self.async_step_init()
        schema = vol.Schema({
            vol.Required("name") if not area else vol.Optional("name"): str,
            vol.Required("in_home", default=model.default_in_home(self._zone["kind"])): bool,
        })
        return self.async_show_form(step_id="zone_details", data_schema=schema, errors=errors,
                                    description_placeholders={"area": self._name(f"area:{area}") if area else ""})

    async def async_step_choose_zone(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._edit_zone = user_input["zone"]
            return await self.async_step_edit_zone()
        options = [{"value": z["id"], "label": self._name(z["id"])} for z in self._data["zones"]]
        return self.async_show_form(step_id="choose_zone", data_schema=vol.Schema({vol.Required("zone"): _select(options)}))

    async def async_step_edit_zone(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        zone = next(z for z in self._data["zones"] if z["id"] == self._edit_zone)
        if user_input is not None:
            if user_input.get("remove"):
                self._data["zones"] = [z for z in self._data["zones"] if z["id"] != zone["id"]]
                self._data["connections"] = [c for c in self._data["connections"] if zone["id"] not in (c["a"], c["b"])] \
                    if not zone["id"].startswith("area:") else self._data["connections"]
            else:
                zone["kind"], zone["in_home"] = user_input["kind"], user_input["in_home"]
                if not zone["id"].startswith("area:") and user_input.get("name", "").strip():
                    zone["name"] = user_input["name"].strip()
            return await self.async_step_init()
        fields: dict = {}
        if not zone["id"].startswith("area:"):
            fields[vol.Required("name", default=zone["name"])] = str
        fields[vol.Required("kind", default=zone["kind"])] = _select(ZONE_KINDS, "zone_kind")
        fields[vol.Required("in_home", default=zone["in_home"])] = bool
        fields[vol.Optional("remove", default=False)] = bool
        return self.async_show_form(step_id="edit_zone", data_schema=vol.Schema(fields), description_placeholders={"name": self._name(zone["id"])})

    # ------------------------------------------------------------------ connections
    async def async_step_add_connection(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            a, b = user_input["a"], user_input["b"]
            if a == b:
                errors["base"] = "same_space"
            else:
                existing = next((c for c in self._data["connections"] if {c["a"], c["b"]} == {a, b}), None)
                if existing is None:
                    existing = {"id": _new_id(), "a": a, "b": b, "separations": []}
                    self._data["connections"].append(existing)
                self._conn = existing
                return await self.async_step_separation()
        options = self._space_options()
        schema = vol.Schema({vol.Required("a"): _select(options), vol.Required("b"): _select(options)})
        return self.async_show_form(step_id="add_connection", data_schema=schema, errors=errors)

    async def async_step_separation(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """One separation of the connection being edited: its type and, when it can change, the sensor that tells if it is open."""
        assert self._conn is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            kind, sensor = user_input["type"], user_input.get("sensor")
            if kind in PERMANENT and sensor:
                errors["sensor"] = "sensor_not_needed"
            else:
                sep = {"id": _new_id(), "type": kind}
                if sensor:
                    sep["sensor"] = sensor
                self._conn["separations"].append(sep)
                if user_input.get("add_another"):
                    return await self.async_step_separation()
                self._conn = None
                return await self.async_step_init()
        schema = vol.Schema({
            vol.Required("type", default="door"): _select(SEPARATION_TYPES, "separation_type"),
            vol.Optional("sensor"): sel.EntitySelector(sel.EntitySelectorConfig(domain=SENSOR_DOMAINS)),
            vol.Optional("add_another", default=False): bool,
        })
        return self.async_show_form(step_id="separation", data_schema=schema, errors=errors,
                                    description_placeholders={"connection": self._label(self._conn)})

    async def async_step_choose_connection(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._conn = next(c for c in self._data["connections"] if c["id"] == user_input["connection"])
            return await self.async_step_edit_connection()
        options = [{"value": c["id"], "label": self._label(c)} for c in self._data["connections"]]
        return self.async_show_form(step_id="choose_connection", data_schema=vol.Schema({vol.Required("connection"): _select(options)}))

    async def async_step_edit_connection(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._conn is not None
        conn = self._conn
        if user_input is not None:
            if user_input.get("remove_connection"):
                self._data["connections"] = [c for c in self._data["connections"] if c["id"] != conn["id"]]
                self._conn = None
                return await self.async_step_init()
            drop = set(user_input.get("remove_separations", []))
            conn["separations"] = [s for s in conn["separations"] if s["id"] not in drop]
            if user_input.get("add_separation") or not conn["separations"]:
                return await self.async_step_separation()
            self._conn = None
            return await self.async_step_init()
        options = [{"value": s["id"], "label": f"{s['type']}" + (f" · {s['sensor']}" if s.get("sensor") else "")} for s in conn["separations"]]
        schema = vol.Schema({
            vol.Optional("remove_separations", default=[]): _select(options, multiple=True),
            vol.Optional("add_separation", default=False): bool,
            vol.Optional("remove_connection", default=False): bool,
        })
        return self.async_show_form(step_id="edit_connection", data_schema=schema, description_placeholders={"connection": self._label(conn)})
