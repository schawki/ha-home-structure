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


BULK_KINDS = [k for k in ZONE_KINDS if k not in ("street", "neighbor")]     # kinds that can be an existing Home Assistant area
VIRTUAL = {"street": {"en": "Street", "fr": "Rue"}, "neighbor": {"en": "Neighbouring home", "fr": "Logement voisin"}}
FLOOR_TEXT = {"en": ("floor", "no floor"), "fr": ("étage", "sans étage")}
NEEDS_SENSOR = [t for t in SEPARATION_TYPES if t not in PERMANENT]


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
        self._origin: str | None = None       # space whose neighbours are being given (quick connect)
        self._refine: list[str] = []          # connections just created, waiting for their sensor

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
        menu = ["choose_spaces", "zones_bulk", "quick_connect", "add_zone"]
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

    # ------------------------------------------------------------------ which areas are part of the structure
    def _floor_label(self, a: dict) -> str:
        word, none = FLOOR_TEXT.get(self.hass.config.language.split("-")[0], FLOOR_TEXT["en"])
        return f"{a['name']} · {word} {a['floor']}" if a.get("floor") else f"{a['name']} · {none}"

    async def async_step_choose_spaces(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Tick the Home Assistant areas that belong to the structure; every area is ticked until the user says otherwise."""
        all_areas = structure.areas(self.hass)
        if user_input is not None:
            chosen = set(user_input["areas"])
            model.exclude_areas(self._data, {a["id"] for a in all_areas if a["id"] not in chosen})
            return await self.async_step_init()
        left_out = set(self._data.get("excluded_areas", []))
        options = [{"value": a["id"], "label": self._floor_label(a)} for a in all_areas]
        default = [a["id"] for a in all_areas if a["id"] not in left_out]
        schema = vol.Schema({vol.Required("areas", default=default): _select(options, multiple=True)})
        return self.async_show_form(step_id="choose_spaces", data_schema=schema)

    # ------------------------------------------------------------------ zones in bulk
    async def async_step_zones_bulk(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """One field per kind of zone: pick the areas that are gardens, halls, balconies… in one go."""
        errors: dict[str, str] = {}
        lang = self.hass.config.language.split("-")[0]
        current = {k: [z["id"][5:] for z in self._data["zones"] if z["id"].startswith("area:") and z["kind"] == k] for k in BULK_KINDS}
        virtual = {k: next((z for z in self._data["zones"] if z["id"].startswith("zone:") and z["kind"] == k), None) for k in VIRTUAL}
        if user_input is not None:
            kinds = {k: list(user_input.get(k, [])) for k in BULK_KINDS}
            picked = [a for ids in kinds.values() for a in ids]
            if len(picked) != len(set(picked)):
                errors["base"] = "area_in_two_kinds"
            else:
                model.set_area_kinds(self._data, kinds, keep=set())
                for k, names in VIRTUAL.items():
                    want, have = bool(user_input.get(k)), virtual[k]
                    if want and not have:
                        name = names.get(lang, names["en"])
                        self._data["zones"].append({"id": model.unique_zone_id(name, {z["id"] for z in self._data["zones"]}), "kind": k,
                                                    "in_home": False, "name": name})
                    elif have and not want:
                        self._data["zones"] = [z for z in self._data["zones"] if z["id"] != have["id"]]
                        self._data["connections"] = [c for c in self._data["connections"] if have["id"] not in (c["a"], c["b"])]
                return await self.async_step_init()
        left_out = set(self._data.get("excluded_areas", []))
        options = [{"value": a["id"], "label": self._floor_label(a)} for a in structure.areas(self.hass) if a["id"] not in left_out]
        fields: dict = {vol.Optional(k, default=current[k]): _select(options, multiple=True) for k in BULK_KINDS}
        fields.update({vol.Optional(k, default=bool(virtual[k])): bool for k in VIRTUAL})
        return self.async_show_form(step_id="zones_bulk", data_schema=vol.Schema(fields), errors=errors)

    # ------------------------------------------------------------------ connections in bulk
    async def async_step_quick_connect(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 1: the space whose neighbours are about to be given."""
        if user_input is not None:
            self._origin = user_input["origin"]
            return await self.async_step_quick_targets()
        schema = vol.Schema({vol.Required("origin"): _select(self._space_options())})
        return self.async_show_form(step_id="quick_connect", data_schema=schema)

    async def async_step_quick_targets(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 2: every space that touches it, and what separates them (one type for the lot; refine afterwards)."""
        assert self._origin
        if user_input is not None:
            created = model.connect_many(self._data, self._origin, user_input["targets"], user_input["type"], _new_id)
            self._refine = [c["id"] for c in created if c["separations"][0]["type"] in NEEDS_SENSOR]
            self._origin = None
            return await self.async_step_refine()
        linked = {c["b"] if c["a"] == self._origin else c["a"] for c in self._data["connections"] if self._origin in (c["a"], c["b"])}
        options = [o for o in self._space_options() if o["value"] != self._origin and o["value"] not in linked]
        if not options:
            return await self.async_step_init()
        schema = vol.Schema({vol.Required("targets"): _select(options, multiple=True),
                             vol.Required("type", default="door"): _select(SEPARATION_TYPES, "separation_type")})
        return self.async_show_form(step_id="quick_targets", data_schema=schema, description_placeholders={
            "origin": self._name(self._origin), "linked": ", ".join(sorted(self._name(s) for s in linked)) or "-"})

    def _sensor_selector(self, conn: dict) -> sel.EntitySelector:
        """Door, window and cover entities of the two areas when there are some; every such entity of the home otherwise."""
        areas = [s[5:] for s in (conn["a"], conn["b"]) if s.startswith("area:")]
        found = structure.candidate_sensors(self.hass, areas) if areas else []
        return sel.EntitySelector(sel.EntitySelectorConfig(include_entities=found) if found else sel.EntitySelectorConfig(domain=SENSOR_DOMAINS))

    async def async_step_refine(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The connections just created, one at a time: correct the type and tell which sensor says whether it is open (empty = leave as is)."""
        while self._refine and not any(c["id"] == self._refine[0] for c in self._data["connections"]):
            self._refine.pop(0)
        if not self._refine:
            return await self.async_step_init()
        conn = next(c for c in self._data["connections"] if c["id"] == self._refine[0])
        sep = conn["separations"][0]
        errors: dict[str, str] = {}
        if user_input is not None:
            kind, sensor = user_input["type"], user_input.get("sensor")
            if kind in PERMANENT and sensor:
                errors["sensor"] = "sensor_not_needed"
            else:
                sep["type"] = kind
                if sensor:
                    sep["sensor"] = sensor
                else:
                    sep.pop("sensor", None)
                self._refine.pop(0)
                return await self.async_step_refine()
        fields: dict = {vol.Required("type", default=sep["type"]): _select(SEPARATION_TYPES, "separation_type")}
        fields[vol.Optional("sensor")] = self._sensor_selector(conn)
        return self.async_show_form(step_id="refine", data_schema=vol.Schema(fields), errors=errors,
                                    description_placeholders={"connection": self._label(conn), "left": str(len(self._refine))})

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
            vol.Optional("sensor"): self._sensor_selector(self._conn),
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
