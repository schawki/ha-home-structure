import { LitElement, css, html, nothing } from "lit";
import type { TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import { repeat } from "lit/directives/repeat.js";
import "./order";
import "./rooms";
import { translator } from "./i18n";
import type { Key, T } from "./i18n";
import { inside, nearestIndex, reorder, slug } from "./logic";
import { ICON, pageCss } from "./styles";
import type { Area, AreaReg, Floor, Hass, Label, RoomsView } from "./types";

type Menu = { kind: "page" } | { kind: "floor"; fid: string } | { kind: "fab" } | null;
interface Drag { kind: "room" | "floor"; gid: string; id: string; order: string[] }
interface Cat { key: string; domain: string; type: string; sensors: { entity_id: string; name: string }[]; initial: string }
interface RoomDraft { original: string | null; name: string; icon: string; floor: string; labels: string[]; aliases: string[]; alias: string; aliasOpen: boolean; picture: string | null;
  labelPicker: boolean; newLabel: string; occupants: string[]; occPicker: boolean; panel: boolean; choices: Record<string, string>; iconOpen: boolean; uploading: boolean }
interface FloorDraft { original: string | null; name: string; icon: string; level: string; aliases: string[]; alias: string; aliasOpen: boolean; iconOpen: boolean }

const ALWAYS = ["sensor.temperature", "sensor.humidity"];      // Home Assistant keeps these two on the room itself: they are always offered
const COLORS: Record<string, string> = { primary: "--primary-color", accent: "--accent-color", disabled: "--disabled-color", red: "--red-color", pink: "--pink-color", purple: "--purple-color",
  "deep-purple": "--deep-purple-color", indigo: "--indigo-color", blue: "--blue-color", "light-blue": "--light-blue-color", cyan: "--cyan-color", teal: "--teal-color", green: "--green-color",
  "light-green": "--light-green-color", lime: "--lime-color", yellow: "--yellow-color", amber: "--amber-color", orange: "--orange-color", "deep-orange": "--deep-orange-color", brown: "--brown-color",
  "light-grey": "--light-grey-color", grey: "--grey-color", "dark-grey": "--dark-grey-color", "blue-grey": "--blue-grey-color", black: "--black-color", white: "--white-color" };

/** The "Rooms" page of the panel: the floors and rooms of Home Assistant, laid out and edited like its Areas page. Everything written goes to Home Assistant's own registries. */
class HomeStructureFloors extends LitElement {
  @property({ attribute: false }) hass!: Hass;
  @state() private floors: Floor[] = [];
  @state() private areas: AreaReg[] = [];
  @state() private labels: Label[] = [];
  @state() private counts: Area[] = [];
  @state() private users: { id: string; name: string }[] = [];
  private options: { room_occupants?: Record<string, string[]> } = {};
  @state() private ready = false;
  @state() private failed = false;
  @state() private status: "idle" | "saving" | "saved" | "error" = "idle";
  @state() private error = "";
  @state() private menu: Menu = null;
  @state() private view: string | null = null;
  @state() private reorderRooms: string | null = null;
  @state() private reorderFloors = false;
  @state() private drag: Drag | null = null;
  @state() private room: RoomDraft | null = null;
  @state() private floor: FloorDraft | null = null;
  @state() private cats: Cat[] = [];
  @state() private dialogError = "";
  @state() private busy = false;
  @state() private orderFor: string | null = null;
  @state() private iconList: { name: string; keywords: string[] }[] | null = null;
  private t: T = translator("en");

  protected willUpdate(): void {
    if (this.hass) this.t = translator(this.hass.language);
  }

  connectedCallback(): void {
    super.connectedCallback();
    void this.load();
  }

  // ------------------------------------------------------------------ data
  private async load(): Promise<void> {
    try {
      const [floors, areas, labels, boot] = await Promise.all([
        this.hass.callWS<Floor[]>({ type: "config/floor_registry/list" }), this.hass.callWS<AreaReg[]>({ type: "config/area_registry/list" }),
        this.hass.callWS<Label[]>({ type: "config/label_registry/list" }), this.hass.callWS<{ areas: Area[]; users: { id: string; name: string }[]; options: { room_occupants?: Record<string, string[]> } }>({ type: "home_structure/get" })]);
      this.floors = floors;
      this.areas = areas;
      this.labels = labels;
      this.counts = boot.areas;
      this.users = boot.users ?? [];
      this.options = boot.options ?? {};
      this.ready = true;
    } catch {
      this.failed = true;
    }
  }

  /** One write to Home Assistant, then everything is read again so that the page shows what it now says. */
  private async write(msg: Record<string, unknown>): Promise<boolean> {
    this.status = "saving";
    try {
      await this.hass.callWS(msg);
      await this.load();
      this.status = "saved";
      this.error = "";
      return true;
    } catch (e) {
      this.status = "error";
      this.error = String((e as { message?: string })?.message ?? e);
      await this.load();
      return false;
    }
  }

  private inFloor(fid: string | null): AreaReg[] {
    const known = new Set(this.floors.map((f) => f.floor_id));
    return this.areas.filter((a) => (fid === null ? !a.floor_id || !known.has(a.floor_id) : a.floor_id === fid));
  }

  private caption(id: string): string {
    const a = this.counts.find((x) => x.id === id);
    const parts: string[] = [];
    if (a?.devices) parts.push(a.devices === 1 ? this.t("capDevicesOne") : this.t("capDevicesMany", { n: a.devices }));
    if (a?.services) parts.push(a.services === 1 ? this.t("capServicesOne") : this.t("capServicesMany", { n: a.services }));
    if (a?.entities) parts.push(a.entities === 1 ? this.t("capEntitiesOne") : this.t("capEntitiesMany", { n: a.entities }));
    return parts.length < 2 ? parts[0] ?? "" : `${parts.slice(0, -1).join(", ")} ${this.t("capAnd")} ${parts.at(-1)}`;
  }

  // ------------------------------------------------------------------ order of rooms and floors (the registries keep one global list)
  private async applyOrder(kind: "room" | "floor", gid: string, order: string[]): Promise<void> {
    if (kind === "floor") {
      await this.write({ type: "config/floor_registry/reorder", floor_ids: order });
      return;
    }
    const members = new Set(order);
    let k = 0;
    await this.write({ type: "config/area_registry/reorder", area_ids: this.areas.map((a) => (members.has(a.area_id) ? order[k++] : a.area_id)) });
  }

  private startDrag(e: PointerEvent, kind: "room" | "floor", gid: string, id: string, order: string[]): void {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    e.preventDefault();
    this.drag = { kind, gid, id, order: [...order] };
    const start = order.join();
    const root = this.shadowRoot!;
    const items = (): HTMLElement[] => [...root.querySelectorAll<HTMLElement>(kind === "room" ? `[data-floor="${gid}"] [data-room]` : "section.floor:not(.unassigned)")];
    const area = (): DOMRect => (kind === "room" ? root.querySelector(`[data-floor="${gid}"]`)! : this).getBoundingClientRect();
    const stop = (): void => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", cancel);
      window.removeEventListener("keydown", key);
    };
    const move = (ev: PointerEvent): void => {
      const d = this.drag;
      if (!d) return;
      const target = nearestIndex(items().map((el) => el.getBoundingClientRect()), ev.clientX, ev.clientY, kind === "floor");
      const from = d.order.indexOf(d.id);
      if (target >= 0 && target !== from) this.drag = { ...d, order: reorder(d.order, from, target) };
    };
    const up = (ev: PointerEvent): void => {
      stop();
      const d = this.drag;
      this.drag = null;
      if (!d || d.order.join() === start || !inside(area(), ev.clientX, ev.clientY, 24)) return;
      void this.applyOrder(kind, gid, d.order);
    };
    const cancel = (): void => { stop(); this.drag = null; };
    const key = (ev: KeyboardEvent): void => { if (ev.key === "Escape") cancel(); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", cancel);
    window.addEventListener("keydown", key);
  }

  private handleKey(e: KeyboardEvent, kind: "room" | "floor", gid: string, id: string, order: string[]): void {
    const delta = e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : 0;
    if (!delta) return;
    e.preventDefault();
    void this.applyOrder(kind, gid, reorder(order, order.indexOf(id), order.indexOf(id) + delta));
  }

  // ------------------------------------------------------------------ icons
  private async loadIcons(): Promise<void> {
    if (this.iconList) return;
    try {
      this.iconList = (await (await fetch("/static/mdi/iconList.json")).json()) as { name: string; keywords: string[] }[];
    } catch {
      this.iconList = [];
    }
  }

  private iconMatches(text: string): string[] {
    const q = text.replace(/^mdi:/, "").trim().toLowerCase();
    if (!q || !this.iconList) return [];
    return this.iconList.filter((i) => i.name.includes(q) || i.keywords.some((k) => k.includes(q))).slice(0, 30).map((i) => i.name);
  }

  private iconField(value: string, open: boolean, set: (v: string, open: boolean) => void) {
    const matches = open ? this.iconMatches(value) : [];
    return html`<div class="menuwrap iconwrap"><label class="field withicon"><span class="lead">${value ? html`<ha-icon .icon=${value}></ha-icon>` : nothing}</span>
      <span class="flabel">${this.t("ricon")}</span>
      <input class="ricon" placeholder="mdi:sofa-outline" .value=${value} @focus=${() => void this.loadIcons()} @input=${(e: Event) => { void this.loadIcons(); set((e.target as HTMLInputElement).value, true); }}>
      ${value ? html`<button class="iconbtn clear" aria-label=${this.t("removeItem")} @click=${(e: Event) => { e.preventDefault(); set("", false); }}>${this.svg(ICON.close)}</button>` : nothing}</label>
      ${matches.length ? html`<div class="scrim" @click=${() => set(value, false)}></div><div class="menu picker icons" role="listbox">${matches.map((n) => html`<button class="item" role="option" data-icon=${n}
        @click=${() => set(`mdi:${n}`, false)}><ha-icon .icon=${`mdi:${n}`}></ha-icon><span>${n}</span></button>`)}</div>` : nothing}</div>`;
  }

  // ------------------------------------------------------------------ the room dialog, like "Update area"
  private async openRoom(id: string | null): Promise<void> {
    this.menu = null;
    this.dialogError = "";
    const a = id ? this.areas.find((x) => x.area_id === id) : null;
    this.cats = [];
    this.room = { original: a?.area_id ?? null, name: a?.name ?? "", icon: a?.icon ?? "", floor: a?.floor_id ?? "", labels: [...(a?.labels ?? [])], aliases: [...(a?.aliases ?? [])], alias: "", aliasOpen: false,
      picture: a?.picture ?? null, labelPicker: false, newLabel: "", occupants: [...(this.options.room_occupants?.[`area:${a?.area_id}`] ?? [])].filter((u) => this.users.some((x) => x.id === u)), occPicker: false, panel: true, choices: {}, iconOpen: false, uploading: false };
    if (a) await this.loadCats(a.area_id, true);
  }

  private async loadCats(area: string, reset: boolean): Promise<void> {
    try {
      const view = await this.hass.callWS<RoomsView>({ type: "home_structure/room_sensors" });
      const room = view.rooms.find((r) => r.area_id === area);
      const cats: Cat[] = (room?.types ?? []).filter((g) => g.sensors.some((s) => !s.hidden)).map((g) => ({ key: g.key, domain: g.domain, type: g.type, sensors: g.sensors.map((s) => ({ entity_id: s.entity_id, name: s.name })),
        initial: g.primary_source === "chosen" || g.primary_source === "native" ? g.primary ?? "" : "" }));
      for (const key of ALWAYS) if (!cats.some((c) => c.key === key)) cats.push({ key, domain: "sensor", type: key.split(".")[1], sensors: [], initial: "" });
      cats.sort((a, b) => (ALWAYS.indexOf(a.key) < 0 ? 9 : ALWAYS.indexOf(a.key)) - (ALWAYS.indexOf(b.key) < 0 ? 9 : ALWAYS.indexOf(b.key)) || a.key.localeCompare(b.key));
      this.cats = cats;
      if (this.room && reset) this.room = { ...this.room, choices: Object.fromEntries(cats.map((c) => [c.key, c.initial])) };
    } catch {
      this.cats = [];
    }
  }

  private patchRoom(p: Partial<RoomDraft>): void {
    if (this.room) this.room = { ...this.room, ...p };
  }

  private async upload(file: File): Promise<void> {
    this.patchRoom({ uploading: true });
    this.dialogError = "";
    try {
      const body = new FormData();
      body.append("file", file);
      const hass = this.hass;
      const res = hass.fetchWithAuth ? await hass.fetchWithAuth("/api/image/upload", { method: "POST", body })
        : await fetch("/api/image/upload", { method: "POST", body, headers: { Authorization: `Bearer ${hass.auth?.data?.access_token ?? ""}` } });
      if (!res.ok) throw new Error(String(res.status));
      const json = (await res.json()) as { id: string };
      this.patchRoom({ picture: `/api/image/serve/${json.id}/512x512`, uploading: false });
    } catch (e) {
      this.dialogError = this.t("uploadFailed", { error: String((e as { message?: string })?.message ?? e) });
      this.patchRoom({ uploading: false });
    }
  }

  private addRoomAlias(): void {
    const d = this.room;
    const v = d?.alias.trim();
    if (!d || !v) return;
    this.patchRoom({ aliases: d.aliases.some((a) => a.toLowerCase() === v.toLowerCase()) ? d.aliases : [...d.aliases, v], alias: "" });
  }

  private async createLabel(): Promise<void> {
    const d = this.room;
    const name = d?.newLabel.trim();
    if (!d || !name) return;
    try {
      const made = await this.hass.callWS<Label>({ type: "config/label_registry/create", name });
      this.labels = [...this.labels, made];
      this.patchRoom({ labels: [...d.labels, made.label_id], newLabel: "", labelPicker: false });
    } catch (e) {
      this.dialogError = String((e as { message?: string })?.message ?? e);
    }
  }

  private roomValid(d: RoomDraft): boolean {
    const clash = this.areas.some((a) => a.area_id !== d.original && a.name.trim().toLowerCase() === d.name.trim().toLowerCase());
    return !!d.name.trim() && !clash && !d.uploading;
  }

  private async saveRoom(): Promise<void> {
    const d = this.room;
    if (!d || !this.roomValid(d) || this.busy) return;
    this.busy = true;
    this.dialogError = "";
    const pending = d.alias.trim();
    const aliases = pending && !d.aliases.some((a) => a.toLowerCase() === pending.toLowerCase()) ? [...d.aliases, pending] : d.aliases;
    try {
      if (d.original) {
        await this.hass.callWS({ type: "config/area_registry/update", area_id: d.original, name: d.name.trim(), icon: d.icon.trim() || null, floor_id: d.floor || null, labels: d.labels, aliases, picture: d.picture });
        const key = `area:${d.original}`;
        const before = (this.options.room_occupants?.[key] ?? []).filter((u) => this.users.some((x) => x.id === u));
        if (before.join() !== d.occupants.join()) {      // the usual occupants are Home Structure's own: read the options afresh, change this room, save
          const fresh = await this.hass.callWS<{ options: { room_occupants?: Record<string, string[]> } }>({ type: "home_structure/get" });
          const o = { ...fresh.options, room_occupants: { ...(fresh.options.room_occupants ?? {}) } };
          if (d.occupants.length) o.room_occupants[key] = d.occupants; else delete o.room_occupants[key];
          await this.hass.callWS({ type: "home_structure/save", options: o });
        }
        for (const c of this.cats) {
          const choice = d.choices[c.key] ?? "";
          if (choice !== c.initial) await this.hass.callWS({ type: "home_structure/primary_set", area_id: d.original, key: c.key, entity_id: choice || null });
        }
      } else {
        await this.hass.callWS({ type: "config/area_registry/create", name: d.name.trim(), ...(d.icon.trim() ? { icon: d.icon.trim() } : {}), ...(d.floor ? { floor_id: d.floor } : {}), labels: d.labels, aliases, picture: d.picture });
      }
      this.room = null;
      await this.load();
      this.status = "saved";
    } catch (e) {
      this.dialogError = String((e as { message?: string })?.message ?? e);
    } finally {
      this.busy = false;
    }
  }

  // ------------------------------------------------------------------ the floor dialog, like "Edit floor"
  private openFloor(id: string | null): void {
    this.menu = null;
    this.dialogError = "";
    const f = id ? this.floors.find((x) => x.floor_id === id) : null;
    this.floor = { original: f?.floor_id ?? null, name: f?.name ?? "", icon: f?.icon ?? "", level: f?.level == null ? "" : String(f.level), aliases: [...(f?.aliases ?? [])], alias: "", aliasOpen: false, iconOpen: false };
  }

  private patchFloor(p: Partial<FloorDraft>): void {
    if (this.floor) this.floor = { ...this.floor, ...p };
  }

  private floorValid(d: FloorDraft): boolean {
    const clash = this.floors.some((f) => f.floor_id !== d.original && f.name.trim().toLowerCase() === d.name.trim().toLowerCase());
    return !!d.name.trim() && !clash && (d.level.trim() === "" || Number.isInteger(Number(d.level)));
  }

  private async saveFloor(): Promise<void> {
    const d = this.floor;
    if (!d || !this.floorValid(d) || this.busy) return;
    this.busy = true;
    this.dialogError = "";
    const pending = d.alias.trim();
    const aliases = pending && !d.aliases.some((a) => a.toLowerCase() === pending.toLowerCase()) ? [...d.aliases, pending] : d.aliases;
    const data = { name: d.name.trim(), icon: d.icon.trim() || null, level: d.level.trim() === "" ? null : Number(d.level), aliases };
    try {
      await this.hass.callWS(d.original ? { type: "config/floor_registry/update", floor_id: d.original, ...data } : { type: "config/floor_registry/create", ...data });
      this.floor = null;
      await this.load();
      this.status = "saved";
    } catch (e) {
      this.dialogError = String((e as { message?: string })?.message ?? e);
    } finally {
      this.busy = false;
    }
  }

  // ------------------------------------------------------------------ rendering helpers
  private svg(path: string) {
    return html`<svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true"><path d=${path}></path></svg>`;
  }

  private statusText(): string {
    return this.status === "saving" ? this.t("saving") : this.status === "saved" ? `✓ ${this.t("saved")}` : this.status === "error" ? this.t("saveFailed", { error: this.error }) : "";
  }

  private menuItem(action: string, icon: string, label: string, fn: () => void) {
    return html`<button class="item" role="menuitem" data-action=${action} @click=${() => { this.menu = null; fn(); }}>${this.svg(icon)}<span>${label}</span></button>`;
  }

  private renderMenu(m: NonNullable<Menu>) {
    const items: TemplateResult[] = [];
    if (m.kind === "page") items.push(this.menuItem("reorder-floors", ICON.sort, this.t("rearrangeFloors"), () => (this.reorderFloors = true)));
    else if (m.kind === "floor") {
      items.push(this.menuItem("reorder-rooms", ICON.sort, this.t("rearrangeRooms"), () => (this.reorderRooms = m.fid)));
      items.push(html`<hr>`, this.menuItem("edit-floor", ICON.pencil, this.t("editFloor"), () => this.openFloor(m.fid)));
    } else {
      items.push(this.menuItem("create-floor", ICON.plus, this.t("createFloor"), () => this.openFloor(null)), this.menuItem("create-room", ICON.plus, this.t("createRoom"), () => void this.openRoom(null)));
    }
    return html`<div class="scrim" @click=${() => (this.menu = null)}></div><div class="menu ${m.kind === "fab" ? "up" : ""}" role="menu">${items}</div>`;
  }

  private menuButton(menu: NonNullable<Menu>, action: string) {
    const open = this.menu && JSON.stringify(this.menu) === JSON.stringify(menu);
    return html`<span class="menuwrap"><button class="iconbtn" data-action=${action} aria-label=${this.t("more")} aria-haspopup="menu" @click=${() => (this.menu = open ? null : menu)}>${this.svg(ICON.dots)}</button>${open ? this.renderMenu(menu) : nothing}</span>`;
  }

  private renderCard(a: AreaReg, fid: string, order: string[]) {
    const rearranging = this.reorderRooms === fid;
    const dragging = this.drag?.kind === "room" && this.drag.id === a.area_id;
    const caption = this.caption(a.area_id);
    return html`<div class="card ${rearranging ? "sortable" : "clickable"} ${dragging ? "dragging" : ""}" data-room=${a.area_id}
      @pointerdown=${rearranging ? (e: PointerEvent) => this.startDrag(e, "room", fid, a.area_id, order) : nothing}
      @click=${rearranging ? nothing : (e: Event) => { if (!(e.target as HTMLElement).closest(".iconbtn")) this.view = a.area_id; }}>
      <div class="picture" style=${a.picture ? `background-image:url(${a.picture})` : ""}>${a.picture ? nothing : html`<ha-icon .icon=${a.icon || "mdi:texture-box"}></ha-icon>`}</div>
      <div class="info"><div class="line"><strong>${a.name}</strong>
        ${rearranging ? html`<span class="grip" role="button" tabindex="0" data-action="room-handle" aria-label=${this.t("moveItem")} @keydown=${(e: KeyboardEvent) => this.handleKey(e, "room", fid, a.area_id, order)}>⋮⋮</span>`
          : html`<button class="iconbtn" data-action="edit-room" aria-label=${this.t("editRoom")} @click=${() => void this.openRoom(a.area_id)}>${this.svg(ICON.pencil)}</button>`}</div>
        ${caption ? html`<small>${caption}</small>` : nothing}</div></div>`;
  }

  private renderFloor(f: Floor) {
    const own = this.inFloor(f.floor_id).map((a) => a.area_id);
    const order = this.drag?.kind === "room" && this.drag.gid === f.floor_id ? this.drag.order : own;
    const rooms = order.map((id) => this.areas.find((a) => a.area_id === id)).filter((a): a is AreaReg => !!a);
    const rearranging = this.reorderRooms === f.floor_id;
    const dragging = this.drag?.kind === "floor" && this.drag.id === f.floor_id;
    return html`<section class="floor group ${this.reorderFloors ? "compact" : ""} ${dragging ? "dragging" : ""}" data-floor=${f.floor_id}>
      <header class=${this.reorderFloors ? "sortable" : ""} @pointerdown=${this.reorderFloors ? (e: PointerEvent) => this.startDrag(e, "floor", "", f.floor_id, this.floors.map((x) => x.floor_id)) : nothing}>
        ${f.icon ? html`<ha-icon .icon=${f.icon}></ha-icon>` : nothing}<h2>${f.name}</h2><span class="grow"></span>
        ${this.reorderFloors ? html`<span class="grip" role="button" tabindex="0" data-action="floor-handle" aria-label=${this.t("moveItem")} @keydown=${(e: KeyboardEvent) => this.handleKey(e, "floor", "", f.floor_id, this.floors.map((x) => x.floor_id))}>⋮⋮</span>`
          : rearranging ? html`<button class="textbtn" data-action="rooms-done" @click=${() => (this.reorderRooms = null)}>${this.t("done")}</button>` : this.menuButton({ kind: "floor", fid: f.floor_id }, "floor-menu")}
      </header>
      ${this.reorderFloors ? nothing : html`<div class="cards">${repeat(rooms, (a) => a.area_id, (a) => this.renderCard(a, f.floor_id, order))}${rooms.length ? nothing : html`<p class="muted">${this.t("emptyGroup")}</p>`}</div>`}
    </section>`;
  }

  private renderUnassigned() {
    const rest = this.inFloor(null);
    if (!rest.length) return nothing;
    return html`<section class="floor group unassigned" data-floor="">${this.floors.length ? html`<header><h2>${this.t("unassignedRooms")}</h2></header>` : nothing}
      <div class="cards">${rest.map((a) => this.renderCard(a, "", rest.map((x) => x.area_id)))}</div></section>`;
  }

  // ------------------------------------------------------------------ dialogs
  private text(label: string, cls: string, value: string, on: (v: string) => void, type = "text") {
    return html`<label class="field"><span class="flabel">${label}</span><input class=${cls} type=${type} .value=${value} @input=${(e: Event) => on((e.target as HTMLInputElement).value)}></label>`;
  }

  private aliasBlock(d: { aliases: string[]; alias: string; aliasOpen: boolean }, set: (p: { aliases?: string[]; alias?: string; aliasOpen?: boolean }) => void, add: () => void, help: string) {
    return html`<h3>${this.t("galiases")}</h3><p class="text">${help}</p>
      <div class="chips" data-field="aliases">${d.aliases.map((al) => html`<span class="chip" data-alias=${al}>${al}<button class="chipx" aria-label="${this.t("removeItem")} ${al}" @click=${() => set({ aliases: d.aliases.filter((x) => x !== al) })}>${this.svg(ICON.close)}</button></span>`)}</div>
      ${d.aliasOpen ? html`<div class="aliasrow"><label class="field"><span class="flabel">${this.t("addAliasHint")}</span><input class="alias" .value=${d.alias} @input=${(e: Event) => set({ alias: (e.target as HTMLInputElement).value })}
        @keydown=${(e: KeyboardEvent) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}></label><button class="tonal" data-action="alias-add" @click=${add}>${this.svg(ICON.plus)}</button></div>`
        : html`<button class="tonal" data-action="alias-open" @click=${() => set({ aliasOpen: true })}>${this.svg(ICON.plus)}${this.t("addAlias")}</button>`}`;
  }

  private labelChip(l: Label, removable: boolean, d?: RoomDraft) {
    const color = l.color && COLORS[l.color] ? `var(${COLORS[l.color]})` : "var(--secondary-text-color)";
    return html`<span class="chip label" data-label=${l.label_id} style="--c:${color}">${l.icon ? html`<ha-icon .icon=${l.icon}></ha-icon>` : nothing}${l.name}
      ${removable && d ? html`<button class="chipx" aria-label="${this.t("removeItem")} ${l.name}" @click=${() => this.patchRoom({ labels: d.labels.filter((x) => x !== l.label_id) })}>${this.svg(ICON.close)}</button>` : nothing}</span>`;
  }

  private catLabel(c: Cat): string {
    if (c.key === "sensor.temperature") return this.t("gs_temperature");
    if (c.key === "sensor.humidity") return this.t("gs_humidity");
    const loc = (this.hass as unknown as { localize?: (k: string) => string }).localize;
    const type = loc?.(`component.${c.domain}.entity_component.${c.type}.name`) || c.type.replace(/_/g, " ").replace(/^./, (x) => x.toUpperCase());
    return this.t("catSensor", { type });
  }

  private occupantBlock(d: RoomDraft) {
    const t = this.t;
    const free = this.users.filter((u) => !d.occupants.includes(u.id));
    return html`<h3>${t("occupantsTitle")}</h3><p class="text">${t("occupantsHint")}</p>
      <div class="chips" data-field="occupants">${d.occupants.map((id) => this.users.find((u) => u.id === id)).filter((u): u is { id: string; name: string } => !!u).map((u) => html`<span class="chip" data-occupant=${u.id}>${u.name}<button class="chipx" aria-label="${t("removeItem")} ${u.name}" @click=${() => this.patchRoom({ occupants: d.occupants.filter((x) => x !== u.id) })}>${this.svg(ICON.close)}</button></span>`)}</div>
      ${free.length ? html`<div class="menuwrap"><button class="tonal" data-action="occupant-open" @click=${() => this.patchRoom({ occPicker: !d.occPicker })}>${this.svg(ICON.plus)}${t("addOccupant")}</button>
        ${d.occPicker ? html`<div class="scrim" @click=${() => this.patchRoom({ occPicker: false })}></div><div class="menu picker" role="listbox">${free.map((u) => html`<button class="item" role="option" data-pick-occupant=${u.id}
          @click=${() => this.patchRoom({ occupants: [...d.occupants, u.id], occPicker: false })}><span>${u.name}</span></button>`)}</div>` : nothing}</div>` : nothing}`;
  }

  private renderRoomDialog() {
    const d = this.room;
    if (!d) return nothing;
    const t = this.t;
    const id = d.original ?? (d.name.trim() ? slug(d.name.trim()) : "");
    const free = this.labels.filter((l) => !d.labels.includes(l.label_id));
    const title = t(d.original ? "updateRoom" : "createRoom");
    return html`<div class="overlay" @click=${(e: Event) => e.target === e.currentTarget && (this.room = null)}><div class="dialog" role="dialog" aria-label=${title} data-room-dialog>
      <header><button class="iconbtn" data-action="dialog-close" aria-label=${t("close")} @click=${() => (this.room = null)}>${this.svg(ICON.close)}</button><h2>${title}</h2></header>
      <div class="idrow"><div class="idlabel">${t("roomIdLabel")}</div><div class="gid">${id}</div></div>
      ${this.text(`${t("rname")}*`, "rname", d.name, (v) => this.patchRoom({ name: v }))}
      ${this.iconField(d.icon, d.iconOpen, (v, open) => this.patchRoom({ icon: v, iconOpen: open }))}
      <label class="field selectfield"><span class="flabel">${t("rfloor")}</span><select class="rfloor" @change=${(e: Event) => this.patchRoom({ floor: (e.target as HTMLSelectElement).value })}>
        <option value="" ?selected=${!d.floor}>${t("noFloorOpt")}</option>${this.floors.map((f) => html`<option value=${f.floor_id} ?selected=${f.floor_id === d.floor}>${f.name}</option>`)}</select><span class="caret">${this.svg(ICON.caret)}</span></label>
      <h3>${t("labelsTitle")}</h3>
      <div class="chips" data-field="labels">${d.labels.map((lid) => this.labels.find((l) => l.label_id === lid)).filter((l): l is Label => !!l).map((l) => this.labelChip(l, true, d))}</div>
      <div class="menuwrap"><button class="tonal" data-action="label-open" @click=${() => this.patchRoom({ labelPicker: !d.labelPicker })}>${this.svg(ICON.playlistPlus)}${t("addLabel")}</button>
        ${d.labelPicker ? html`<div class="scrim" @click=${() => this.patchRoom({ labelPicker: false })}></div><div class="menu picker" role="listbox">
          ${free.map((l) => html`<button class="item" role="option" data-pick-label=${l.label_id} @click=${() => this.patchRoom({ labels: [...d.labels, l.label_id], labelPicker: false })}>${this.labelChip(l, false)}</button>`)}
          <div class="newlabel"><input class="newlabelinput" placeholder=${t("newLabelHint")} .value=${d.newLabel} @input=${(e: Event) => this.patchRoom({ newLabel: (e.target as HTMLInputElement).value })}
            @keydown=${(e: KeyboardEvent) => { if (e.key === "Enter") { e.preventDefault(); void this.createLabel(); } }}><button class="textbtn" data-action="label-create" @click=${() => void this.createLabel()}>${t("createLabel")}</button></div></div>` : nothing}</div>
      <h3>${t("pictureTitle")}</h3>
      <div class="drop" data-field="picture" @dragover=${(e: Event) => e.preventDefault()} @drop=${(e: DragEvent) => { e.preventDefault(); const f = e.dataTransfer?.files?.[0]; if (f) void this.upload(f); }}>
        ${d.picture ? html`<img class="preview" src=${d.picture} alt=""><button class="textbtn" data-action="picture-remove" @click=${() => this.patchRoom({ picture: null })}>${t("removePicture")}</button>`
          : html`<label class="tonal filebtn" data-action="picture-add">${this.svg(ICON.plus)}${d.uploading ? t("saving") : t("addPicture")}<input class="file" type="file" accept="image/jpeg,image/png,image/gif" hidden
            @change=${(e: Event) => { const f = (e.target as HTMLInputElement).files?.[0]; if (f) void this.upload(f); }}></label><p class="helper">${t("pictureHelp")}</p>`}</div>
      ${this.aliasBlock(d, (p) => this.patchRoom(p), () => this.addRoomAlias(), t("roomAliasesHelp"))}
      ${d.original && this.users.length ? this.occupantBlock(d) : nothing}
      ${d.original ? html`<section class="expansion" data-panel>
        <button class="exphead" aria-expanded=${d.panel} @click=${() => this.patchRoom({ panel: !d.panel })}><span>${t("sensorsPanel")}</span><span class="chev ${d.panel ? "open" : ""}">${this.svg(ICON.chevron)}</span></button>
        ${d.panel ? html`<div class="expbody">${this.cats.map((c) => html`<div class="sensorbox" data-cat=${c.key}><div class="sensortitle">${this.catLabel(c)}</div>
          <label class="field selectfield"><span class="flabel">${t("chosenSensor")}</span><select class="choose" data-key=${c.key} ?disabled=${!c.sensors.length} @change=${(e: Event) => this.patchRoom({ choices: { ...d.choices, [c.key]: (e.target as HTMLSelectElement).value } })}>
            <option value="" ?selected=${!d.choices[c.key]}>${c.sensors.length ? t("chosenDefault") : t("noSensorInRoom")}</option>${c.sensors.map((s) => html`<option value=${s.entity_id} ?selected=${d.choices[c.key] === s.entity_id}>${s.name}</option>`)}</select><span class="caret">${this.svg(ICON.caret)}</span></label>
          <div class="helper">${t("sensorHelp")}</div></div>`)}
          <button class="tonal" data-action="order-open" @click=${() => (this.orderFor = d.original)}>${this.svg(ICON.sort)}${t("orderSensors")}</button></div>` : nothing}</section>` : nothing}
      ${this.dialogError ? html`<p class="warn" data-error role="alert">${this.dialogError}</p>` : nothing}
      <footer><button class="textbtn" data-action="dialog-cancel" @click=${() => (this.room = null)}>${t("cancel")}</button>
        <button class="filled" data-action="dialog-save" ?disabled=${!this.roomValid(d) || this.busy} @click=${() => void this.saveRoom()}>${t("save")}</button></footer>
    </div></div>`;
  }

  private renderFloorDialog() {
    const d = this.floor;
    if (!d) return nothing;
    const t = this.t;
    const id = d.original ?? (d.name.trim() ? slug(d.name.trim()) : "");
    const title = t(d.original ? "editFloor" : "createFloor");
    return html`<div class="overlay" @click=${(e: Event) => e.target === e.currentTarget && (this.floor = null)}><div class="dialog" role="dialog" aria-label=${title} data-floor-dialog>
      <header><button class="iconbtn" data-action="dialog-close" aria-label=${t("close")} @click=${() => (this.floor = null)}>${this.svg(ICON.close)}</button><h2>${title}</h2></header>
      <div class="idrow"><div class="idlabel">${t("floorIdLabel")}</div><div class="gid">${id}</div></div>
      ${this.text(`${t("rname")}*`, "fname", d.name, (v) => this.patchFloor({ name: v }))}
      ${this.iconField(d.icon, d.iconOpen, (v, open) => this.patchFloor({ icon: v, iconOpen: open }))}
      ${this.text(t("floorLevel"), "flevel", d.level, (v) => this.patchFloor({ level: v }), "number")}<div class="helper indent">${t("floorLevelHelp")}</div>
      ${this.aliasBlock(d, (p) => this.patchFloor(p), () => { const v = d.alias.trim(); if (v) this.patchFloor({ aliases: d.aliases.some((a) => a.toLowerCase() === v.toLowerCase()) ? d.aliases : [...d.aliases, v], alias: "" }); }, t("roomAliasesHelp").replace(/room|pièce/, (m) => (m === "room" ? "floor" : "étage")))}
      ${this.dialogError ? html`<p class="warn" data-error role="alert">${this.dialogError}</p>` : nothing}
      <footer><button class="textbtn" data-action="dialog-cancel" @click=${() => (this.floor = null)}>${t("cancel")}</button>
        <button class="filled" data-action="dialog-save" ?disabled=${!this.floorValid(d) || this.busy} @click=${() => void this.saveFloor()}>${t("save")}</button></footer>
    </div></div>`;
  }

  render() {
    if (this.failed) return html`<p class="msg">${this.t("notLoaded")}</p>`;
    if (!this.ready) return html`<p class="msg">${this.t("loading")}</p>`;
    if (this.view) return html`<home-structure-rooms .hass=${this.hass} .area=${this.view} @back=${() => { this.view = null; void this.load(); }}></home-structure-rooms>`;
    const empty = !this.areas.length && !this.floors.length;
    const floors = this.drag?.kind === "floor" ? this.drag.order.map((id) => this.floors.find((f) => f.floor_id === id)).filter((f): f is Floor => !!f) : this.floors;
    return html`
      <div class="head">${this.reorderFloors ? html`<button class="textbtn" data-action="floors-done" @click=${() => (this.reorderFloors = false)}>${this.t("done")}</button>` : this.floors.length > 1 ? this.menuButton({ kind: "page" }, "page-menu") : nothing}</div>
      <div class="groups">${repeat(floors, (f) => f.floor_id, (f) => this.renderFloor(f))}</div>
      ${this.reorderFloors ? nothing : this.renderUnassigned()}
      ${empty ? html`<p class="muted empty" data-empty>${this.t("noRoomsAtAll")}</p>` : nothing}
      <span class="menuwrap fabwrap"><button class="fab" data-action="add" @click=${() => (this.menu = this.menu?.kind === "fab" ? null : { kind: "fab" })}>${this.svg(ICON.plus)}${this.t("add")}</button>${this.menu?.kind === "fab" ? this.renderMenu(this.menu) : nothing}</span>
      <span class="status ${this.status}" role="status" data-status=${this.status}>${this.statusText()}</span>
      ${this.renderRoomDialog()}${this.renderFloorDialog()}
      ${this.orderFor ? html`<home-structure-order .hass=${this.hass} .area=${this.orderFor} @closed=${() => { const a = this.orderFor!; this.orderFor = null; void this.loadCats(a, false); void this.load(); }}></home-structure-order>` : nothing}`;
  }

  static styles = [pageCss, css`
    .card.clickable { cursor: pointer; } .card.clickable:hover { border-color: var(--primary-color); }
    .picture { background-size: cover; background-position: center; }
    .fabwrap { position: fixed; right: 20px; bottom: 20px; z-index: 10; } .fabwrap .fab { position: static; } .menu.up { top: auto; bottom: calc(100% + 8px); right: 0; }
    .chip.label { border-color: var(--c); background: color-mix(in srgb, var(--c) 18%, transparent); padding-right: 12px; } .chip.label ha-icon { color: var(--c); }
    .chip.label:has(.chipx) { padding-right: 4px; } .menu.picker .item .chip { height: 28px; }
    .newlabel { display: flex; gap: 8px; align-items: center; padding: 8px 12px; border-top: 1px solid var(--divider-color); } .newlabel input { flex: 1; font: inherit; padding: 8px; background: none; color: inherit; border: 1px solid var(--divider-color); border-radius: 8px; min-width: 0; }
    .drop { border: 1px dashed var(--divider-color); border-radius: 12px; padding: 16px; text-align: center; margin-bottom: 8px; } .drop .preview { max-width: 100%; max-height: 180px; border-radius: 8px; display: block; margin: 0 auto 8px; }
    .filebtn { cursor: pointer; } .iconwrap { display: block; } .iconwrap .field { margin-top: 12px; } .menu.icons { max-height: 260px; left: 0; right: auto; width: 100%; } .menu.icons .item { padding: 8px 16px; }
    .dialog .warn { color: var(--error-color, #db4437); } .text { color: var(--secondary-text-color); }
  `];
}
if (!customElements.get("home-structure-floors")) customElements.define("home-structure-floors", HomeStructureFloors);
