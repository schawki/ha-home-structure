import { LitElement, css, html, nothing } from "lit";
import { property, state } from "lit/decorators.js";
import { translator } from "./i18n";
import type { Key, T } from "./i18n";
import { repeat } from "lit/directives/repeat.js";
import { addRoom, clone, groupsOf, inside, moveGroup, moveRoom, moveRoomInGroup, nearestIndex, newGroupId, removeFromAll, removeRoom, reorder, setGroupOrder, setRoomOrder, ungrouped } from "./logic";
import type { Area, Group, GroupKind, GroupSensor, Hass, SensorCfg, SensorMode } from "./types";

const KINDS: GroupKind[] = ["temperature", "humidity"];
const MODES: SensorMode[] = ["none", "single", "all", "selection"];

type Menu = { kind: "page" } | { kind: "group"; gid: string } | { kind: "room"; gid: string | null; aid: string } | null;
type Mover = { mode: "move" | "add"; gid: string | null; aid: string; target: string } | null;
interface Drag { kind: "room" | "group"; gid: string; id: string; order: string[] }
interface Draft { original: string | null; id: string; name: string; level: string; icon: string; areas: string[]; aliases: string[]; alias: string; temperature: SensorCfg; humidity: SensorCfg; picker: boolean; aliasOpen: boolean; panel: boolean }


// Paths of the Material Design Icons used by the page (inline, so nothing has to be loaded).
const ICON = {
  close: "M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z",
  dots: "M12,16A2,2 0 0,1 14,18A2,2 0 0,1 12,20A2,2 0 0,1 10,18A2,2 0 0,1 12,16M12,10A2,2 0 0,1 14,12A2,2 0 0,1 12,14A2,2 0 0,1 10,12A2,2 0 0,1 12,10M12,4A2,2 0 0,1 14,6A2,2 0 0,1 12,8A2,2 0 0,1 10,6A2,2 0 0,1 12,4Z",
  pencil: "M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.12,5.12L18.87,8.87M3,17.25V21H6.75L17.81,9.93L14.06,6.18L3,17.25Z",
  delete: "M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z",
  plus: "M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z",
  minus: "M19,13H5V11H19V13Z",
  arrow: "M4,11V13H16L10.5,18.5L11.92,19.92L19.84,12L11.92,4.08L10.5,5.5L16,11H4Z",
  sort: "M10,13V11H18V13H10M10,19V17H14V19H10M10,7V5H22V7H10M6,17H8.5L5,20.5L1.5,17H4V7H1.5L5,3.5L8.5,7H6V17Z",
  caret: "M7,10L12,15L17,10H7Z",
  chevron: "M7.41,15.41L12,10.83L16.59,15.41L18,14L12,8L6,14L7.41,15.41Z",
  playlistPlus: "M3,16H10V14H3M18,14V10H16V14H12V16H16V20H18V16H22V14M14,6H3V8H14M14,10H3V12H14V10Z",
};

/** The "Groups" page of the panel: groups of rooms laid out like the floors of Home Assistant's Areas page. */
class HomeStructureGroups extends LitElement {
  @property({ attribute: false }) hass!: Hass;
  @state() private areas: Area[] = [];
  @state() private groups: Group[] = [];
  @state() private ready = false;
  @state() private failed = false;
  @state() private status: "idle" | "saving" | "saved" | "error" = "idle";
  @state() private error = "";
  @state() private notice = false;
  @state() private menu: Menu = null;
  @state() private mover: Mover = null;
  @state() private draft: Draft | null = null;
  @state() private confirm: string | null = null;
  @state() private reorderGroups = false;
  @state() private reorderRooms: string | null = null;
  @state() private drag: Drag | null = null;
  @state() private cands: Record<GroupKind, GroupSensor[]> = { temperature: [], humidity: [] };
  private chain: Promise<unknown> = Promise.resolve();
  private seq: Record<GroupKind, number> = { temperature: 0, humidity: 0 };
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
      const boot = await this.hass.callWS<{ areas: Area[]; options: { groups?: Group[] } }>({ type: "home_structure/get" });
      this.areas = boot.areas;
      this.groups = boot.options.groups ?? [];
      this.ready = true;
    } catch {
      this.failed = true;
    }
  }

  private persist(next: Group[]): void {
    this.groups = next;
    this.status = "saving";
    this.chain = this.chain.then(async () => {
      try {
        const r = await this.hass.callWS<{ groups: Group[]; pruned: string[] }>({ type: "home_structure/save_groups", groups: next });
        if (next === this.groups) this.groups = r.groups;
        if (r.pruned.length) this.notice = true;
        this.status = "saved";
        this.error = "";
      } catch (err) {
        this.status = "error";
        this.error = String((err as { message?: string })?.message ?? err);
        await this.load();
      }
    });
  }

  private areaName(id: string): string {
    return this.areas.find((a) => a.id === id)?.name ?? id;
  }

  private known(ids: string[]): Area[] {
    return ids.map((id) => this.areas.find((a) => a.id === id)).filter((a): a is Area => !!a);
  }

  /** The grey line under a room's name, worded like Home Assistant's Areas page: "5 devices, 1 service and 1 entity" (the floor when it holds nothing). */
  private caption(a: Area): string {
    const parts: string[] = [];
    if (a.devices) parts.push(a.devices === 1 ? this.t("capDevicesOne") : this.t("capDevicesMany", { n: a.devices }));
    if (a.services) parts.push(a.services === 1 ? this.t("capServicesOne") : this.t("capServicesMany", { n: a.services }));
    if (a.entities) parts.push(a.entities === 1 ? this.t("capEntitiesOne") : this.t("capEntitiesMany", { n: a.entities }));
    if (!parts.length) return a.floor ?? "";
    return parts.length < 2 ? parts[0] : `${parts.slice(0, -1).join(", ")} ${this.t("capAnd")} ${parts.at(-1)}`;
  }

  // ------------------------------------------------------------------ operations of the cards and menus
  private act(fn: () => void): void {
    this.menu = null;
    fn();
  }

  private openMover(mode: "move" | "add", gid: string | null, aid: string): void {
    const target = this.groups.find((g) => g.id !== gid && !g.areas.includes(aid));
    this.menu = null;
    if (target) this.mover = { mode, gid, aid, target: target.id };
  }

  private applyMover(): void {
    const m = this.mover;
    if (!m) return;
    this.mover = null;
    this.persist(m.mode === "move" && m.gid ? moveRoom(this.groups, m.gid, m.target, m.aid) : addRoom(this.groups, m.target, m.aid));
  }

  private deleteGroup(gid: string): void {
    this.confirm = null;
    this.persist(this.groups.filter((g) => g.id !== gid));
  }

  // ------------------------------------------------------------------ the edit dialog
  private blank(): Draft {
    const none = (): SensorCfg => ({ mode: "none", entities: [] });
    return { original: null, id: "", name: "", level: "", icon: "", areas: [], aliases: [], alias: "", temperature: none(), humidity: none(), picker: false, aliasOpen: false, panel: true };
  }

  private openDialog(gid: string | null): void {
    this.menu = null;
    const g = gid ? this.groups.find((x) => x.id === gid) : null;
    this.draft = g ? { original: g.id, id: g.id, name: g.name, level: g.level === null ? "" : String(g.level), icon: g.icon ?? "", areas: this.known(g.areas).map((a) => a.id),
      aliases: [...g.aliases], alias: "", temperature: clone(g.temperature), humidity: clone(g.humidity), picker: false, aliasOpen: false, panel: true } : this.blank();
    for (const k of KINDS) void this.loadSensors(k);
  }

  private async loadSensors(kind: GroupKind): Promise<void> {
    const d = this.draft;
    if (!d) return;
    const n = ++this.seq[kind];
    let found: GroupSensor[] = [];
    try {
      found = d.areas.length ? (await this.hass.callWS<{ sensors: GroupSensor[] }>({ type: "home_structure/group_sensors", area_ids: d.areas, kind })).sensors : [];
    } catch {
      found = [];
    }
    if (n !== this.seq[kind] || !this.draft) return;
    this.cands = { ...this.cands, [kind]: found };
    const ids = new Set(found.map((s) => s.entity_id));
    const cfg = this.draft[kind];
    const keep = cfg.entities.filter((e) => ids.has(e));        // a sensor that is no longer in the rooms leaves the draft
    if (keep.length !== cfg.entities.length) this.setSensor(kind, { mode: keep.length ? cfg.mode : "none", entities: keep });
  }

  private patch(p: Partial<Draft>): void {
    if (this.draft) this.draft = { ...this.draft, ...p };
  }

  private setSensor(kind: GroupKind, cfg: SensorCfg): void {
    this.patch({ [kind]: cfg } as Partial<Draft>);
  }

  private setMode(kind: GroupKind, mode: SensorMode): void {
    const all = this.cands[kind].map((s) => s.entity_id);
    this.setSensor(kind, { mode, entities: mode === "single" ? all.slice(0, 1) : mode === "selection" ? all : [] });
  }

  private toggleSensor(kind: GroupKind, id: string, on: boolean): void {
    const cur = this.draft![kind].entities.filter((e) => e !== id);
    this.setSensor(kind, { mode: "selection", entities: on ? this.cands[kind].map((s) => s.entity_id).filter((e) => e === id || cur.includes(e)) : cur });
  }

  private changeRooms(areas: string[]): void {
    this.patch({ areas });
    for (const k of KINDS) void this.loadSensors(k);
  }

  private addAlias(): void {
    const d = this.draft;
    const v = d?.alias.trim();
    if (!d || !v) return;
    this.patch({ aliases: d.aliases.some((a) => a.toLowerCase() === v.toLowerCase()) ? d.aliases : [...d.aliases, v], alias: "" });
  }

  private valid(d: Draft): boolean {
    const clash = this.groups.some((g) => g.id !== d.original && g.name.trim().toLowerCase() === d.name.trim().toLowerCase());
    const sensorsOk = KINDS.every((k) => (d[k].mode !== "single" || d[k].entities.length === 1) && (d[k].mode !== "selection" || d[k].entities.length > 0));
    return !!d.name.trim() && !clash && sensorsOk && (d.level.trim() === "" || Number.isInteger(Number(d.level)));
  }

  private saveDialog(): void {
    const d = this.draft;
    if (!d || !this.valid(d)) return;
    const pending = d.alias.trim();
    const aliases = pending && !d.aliases.some((a) => a.toLowerCase() === pending.toLowerCase()) ? [...d.aliases, pending] : d.aliases;
    const g: Group = { id: d.original ?? newGroupId(d.name.trim(), this.groups), name: d.name.trim(), level: d.level.trim() === "" ? null : Number(d.level),
      icon: d.icon.trim() || null, areas: d.areas, aliases, temperature: d.temperature, humidity: d.humidity };
    this.draft = null;
    this.persist(d.original ? this.groups.map((x) => (x.id === d.original ? g : x)) : [...this.groups, g]);
  }


  // ------------------------------------------------------------------ rendering helpers
  private statusText(): string {
    return this.status === "saving" ? this.t("saving") : this.status === "saved" ? `✓ ${this.t("saved")}` : this.status === "error" ? this.t("saveFailed", { error: this.error }) : "";
  }

  private count(n: number): string {
    return n === 1 ? this.t("roomsOne") : this.t("roomsMany", { n });
  }

  private svg(path: string) {
    return html`<svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true"><path d=${path}></path></svg>`;
  }

  private roomIcon(a: Area) {
    return html`<ha-icon .icon=${a.icon || "mdi:texture-box"}></ha-icon>`;
  }

  private menuItem(action: string, icon: string, label: string, fn: () => void, danger = false) {
    return html`<button class="item ${danger ? "danger" : ""}" role="menuitem" data-action=${action} @click=${() => this.act(fn)}>${this.svg(icon)}<span>${label}</span></button>`;
  }

  private renderMenu(m: NonNullable<Menu>) {
    const items = [];
    if (m.kind === "page") {
      items.push(this.menuItem("reorder-groups", ICON.sort, this.t("rearrangeGroups"), () => (this.reorderGroups = true)));
    } else if (m.kind === "group") {
      items.push(this.menuItem("reorder-rooms", ICON.sort, this.t("rearrangeRooms"), () => (this.reorderRooms = m.gid)));
      items.push(html`<hr>`);
      items.push(this.menuItem("edit-group", ICON.pencil, this.t("editGroup"), () => this.openDialog(m.gid)));
      items.push(this.menuItem("delete-group", ICON.delete, this.t("deleteGroup"), () => (this.confirm = m.gid), true));
    } else {
      const others = this.groups.some((g) => g.id !== m.gid && !g.areas.includes(m.aid));
      const several = groupsOf(this.groups, m.aid).length > 1;
      if (others && m.gid) items.push(this.menuItem("move-room", ICON.arrow, this.t("moveTo"), () => this.openMover("move", m.gid, m.aid)));
      if (others) items.push(this.menuItem("add-room", ICON.plus, this.t("addTo"), () => this.openMover("add", m.gid, m.aid)));
      if (m.gid) items.push(this.menuItem("remove-room", ICON.minus, this.t("removeFromGroup"), () => this.persist(removeRoom(this.groups, m.gid!, m.aid))));
      if (several) items.push(this.menuItem("remove-all", ICON.close, this.t("removeFromAll"), () => this.persist(removeFromAll(this.groups, m.aid)), true));
    }
    return html`<div class="scrim" @click=${() => (this.menu = null)}></div><div class="menu" role="menu">${items}</div>`;
  }

  private menuButton(menu: NonNullable<Menu>, action: string) {
    const open = this.menu && JSON.stringify(this.menu) === JSON.stringify(menu);
    return html`<span class="menuwrap"><button class="iconbtn" data-action=${action} aria-label=${this.t("more")} aria-haspopup="menu" @click=${() => (this.menu = open ? null : menu)}>${this.svg(ICON.dots)}</button>${open ? this.renderMenu(menu) : nothing}</span>`;
  }

  // ------------------------------------------------------------------ drag and drop (pointer events, so it works with a finger too)
  private startDrag(e: PointerEvent, kind: "room" | "group", gid: string, id: string, order: string[]): void {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    e.preventDefault();
    this.drag = { kind, gid, id, order: [...order] };
    const start = order.join();
    const root = this.shadowRoot!;
    const items = (): HTMLElement[] => [...root.querySelectorAll<HTMLElement>(kind === "room" ? `[data-group="${gid}"] [data-room]` : "[data-group]:not(.ungrouped)")];
    const area = (): DOMRect => (kind === "room" ? root.querySelector(`[data-group="${gid}"]`)! : this).getBoundingClientRect();
    const stop = (): void => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", cancel);
      window.removeEventListener("keydown", key);
    };
    const move = (ev: PointerEvent): void => {
      const d = this.drag;
      if (!d) return;
      const target = nearestIndex(items().map((el) => el.getBoundingClientRect()), ev.clientX, ev.clientY, kind === "group");
      const from = d.order.indexOf(d.id);
      if (target >= 0 && target !== from) this.drag = { ...d, order: reorder(d.order, from, target) };
    };
    const up = (ev: PointerEvent): void => {
      stop();
      const d = this.drag;
      this.drag = null;
      if (!d || d.order.join() === start || !inside(area(), ev.clientX, ev.clientY, 24)) return;     // released outside: nothing changes
      this.persist(kind === "room" ? setRoomOrder(this.groups, gid, d.order) : setGroupOrder(this.groups, d.order));
    };
    const cancel = (): void => { stop(); this.drag = null; };
    const key = (ev: KeyboardEvent): void => { if (ev.key === "Escape") cancel(); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", cancel);
    window.addEventListener("keydown", key);
  }

  /** The arrow keys move a focused handle: the keyboard way to rearrange. */
  private handleKey(e: KeyboardEvent, kind: "room" | "group", gid: string, id: string): void {
    const delta = e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : 0;
    if (!delta) return;
    e.preventDefault();
    this.persist(kind === "room" ? moveRoomInGroup(this.groups, gid, id, delta) : moveGroup(this.groups, id, delta));
  }

  // ------------------------------------------------------------------ the page: sections of cards like the floors of the Areas page
  private renderCard(a: Area, g: Group | null) {
    const rearranging = !!g && this.reorderRooms === g.id;
    const dragging = this.drag?.kind === "room" && this.drag.id === a.id && this.drag.gid === g?.id;
    const caption = this.caption(a);
    return html`<div class="card ${rearranging ? "sortable" : ""} ${dragging ? "dragging" : ""}" data-room=${a.id}
      @pointerdown=${rearranging ? (e: PointerEvent) => this.startDrag(e, "room", g!.id, a.id, this.known(g!.areas).map((x) => x.id)) : nothing}>
      <div class="picture">${this.roomIcon(a)}</div>
      <div class="info">
        <div class="line"><strong>${a.name}</strong>
          ${rearranging ? html`<span class="grip" role="button" tabindex="0" data-action="room-handle" aria-label=${this.t("moveItem")} @keydown=${(e: KeyboardEvent) => this.handleKey(e, "room", g!.id, a.id)}>⋮⋮</span>`
            : this.menuButton({ kind: "room", gid: g?.id ?? null, aid: a.id }, "room-menu")}</div>
        ${caption ? html`<small>${caption}</small>` : nothing}
      </div>
    </div>`;
  }

  private renderGroup(g: Group) {
    const order = this.drag?.kind === "room" && this.drag.gid === g.id ? this.drag.order : g.areas;
    const rooms = this.known(order);
    const rearranging = this.reorderRooms === g.id;
    const dragging = this.drag?.kind === "group" && this.drag.id === g.id;
    return html`<section class="group ${this.reorderGroups ? "compact" : ""} ${dragging ? "dragging" : ""}" data-group=${g.id}>
      <header class=${this.reorderGroups ? "sortable" : ""} @pointerdown=${this.reorderGroups ? (e: PointerEvent) => this.startDrag(e, "group", "", g.id, this.groups.map((x) => x.id)) : nothing}>
        ${g.icon ? html`<ha-icon .icon=${g.icon}></ha-icon>` : nothing}
        <h2>${g.name}</h2>
        <span class="grow"></span>
        ${this.reorderGroups ? html`<span class="grip" role="button" tabindex="0" data-action="group-handle" aria-label=${this.t("moveItem")} @keydown=${(e: KeyboardEvent) => this.handleKey(e, "group", "", g.id)}>⋮⋮</span>`
          : rearranging ? html`<button class="textbtn" data-action="rooms-done" @click=${() => (this.reorderRooms = null)}>${this.t("done")}</button>` : this.menuButton({ kind: "group", gid: g.id }, "group-menu")}
      </header>
      ${this.reorderGroups ? nothing : html`<div class="cards">${repeat(rooms, (a) => a.id, (a) => this.renderCard(a, g))}${rooms.length ? nothing : html`<p class="muted">${this.t("emptyGroup")}</p>`}</div>`}
    </section>`;
  }

  private shownGroups(): Group[] {
    const d = this.drag;
    return d?.kind === "group" ? d.order.flatMap((id) => this.groups.filter((g) => g.id === id)) : this.groups;
  }

  private renderUngrouped() {
    const rest = ungrouped(this.areas, this.groups);
    if (!rest.length || !this.groups.length) return nothing;
    return html`<section class="group ungrouped" data-group="">
      <header><h2>${this.t("ungrouped")}</h2></header>
      <div class="cards">${rest.map((a) => this.renderCard(a, null))}</div></section>`;
  }

  // ------------------------------------------------------------------ the edit dialog, like "Edit floor" / "Update area"
  private field(label: string, cls: string, value: string, onInput: (v: string) => void, extra: { type?: string; placeholder?: string; disabled?: boolean } = {}) {
    return html`<label class="field"><span class="flabel">${label}</span>
      <input class=${cls} type=${extra.type ?? "text"} placeholder=${extra.placeholder ?? ""} ?disabled=${extra.disabled} .value=${value} @input=${(e: Event) => onInput((e.target as HTMLInputElement).value)}></label>`;
  }

  private renderIconField(d: Draft) {
    const icon = d.icon.trim();
    const picker = customElements.get("ha-icon-picker");
    if (picker) {
      return html`<ha-icon-picker class="gicon" .hass=${this.hass} .label=${this.t("gicon")} .value=${d.icon} @value-changed=${(e: CustomEvent) => this.patch({ icon: e.detail.value ?? "" })}></ha-icon-picker>`;
    }
    return html`<label class="field withicon"><span class="lead">${icon ? html`<ha-icon .icon=${icon}></ha-icon>` : nothing}</span>
      <span class="flabel">${this.t("gicon")}</span>
      <input class="gicon" placeholder="mdi:sofa-outline" .value=${d.icon} @input=${(e: Event) => this.patch({ icon: (e.target as HTMLInputElement).value })}>
      ${icon ? html`<button class="iconbtn clear" aria-label=${this.t("removeItem")} @click=${(e: Event) => { e.preventDefault(); this.patch({ icon: "" }); }}>${this.svg(ICON.close)}</button>` : nothing}</label>`;
  }

  private renderSensor(kind: GroupKind, d: Draft) {
    const cfg = d[kind], cands = this.cands[kind];
    const label = (s: GroupSensor) => `${s.name} · ${s.area} · ${s.state} ${s.state === "unavailable" || s.state === "unknown" ? "" : s.unit}`.trim();
    return html`<div class="sensorbox" data-kind=${kind}>
      <div class="sensortitle">${this.t(`gs_${kind}` as Key)}</div>
      <label class="field selectfield"><span class="flabel">${this.t("gsource")}</span>
        <select class="mode" @change=${(e: Event) => this.setMode(kind, (e.target as HTMLSelectElement).value as SensorMode)}>
          ${MODES.map((m) => html`<option value=${m} ?selected=${m === cfg.mode}>${this.t(`gm_${m}` as Key)}</option>`)}</select><span class="caret">${this.svg(ICON.caret)}</span></label>
      <div class="helper">${this.t(`gh_${kind}` as Key)}</div>
      ${cfg.mode === "single" ? html`<label class="field selectfield"><span class="flabel">${this.t("gsensor")}</span>
        <select class="sensor" @change=${(e: Event) => this.setSensor(kind, { mode: "single", entities: [(e.target as HTMLSelectElement).value].filter(Boolean) })}>
          <option value="" ?selected=${!cfg.entities.length}>${this.t("pickSensor")}</option>
          ${cands.map((s) => html`<option value=${s.entity_id} ?selected=${cfg.entities[0] === s.entity_id}>${label(s)}</option>`)}</select><span class="caret">${this.svg(ICON.caret)}</span></label>` : nothing}
      ${cfg.mode === "selection" ? html`<div class="helper">${this.t("sensorsSelectionHelp")}</div>
        <ul class="sensors">${cands.map((s) => html`<li><label class="check"><input type="checkbox" .checked=${cfg.entities.includes(s.entity_id)} data-sensor=${s.entity_id}
          @change=${(e: Event) => this.toggleSensor(kind, s.entity_id, (e.target as HTMLInputElement).checked)}>${label(s)}</label></li>`)}</ul>` : nothing}
      ${cfg.mode === "all" ? html`<div class="helper">${this.t("sensorsAllHelp")}</div>
        <ul class="sensors readonly">${cands.map((s) => html`<li data-source=${s.entity_id}>${label(s)}</li>`)}</ul>` : nothing}
      ${cfg.mode !== "none" && !cands.length ? html`<div class="helper">${this.t("noSensorsHere")}</div>` : nothing}
    </div>`;
  }

  private renderDialog() {
    const d = this.draft;
    if (!d) return nothing;
    const id = d.original ?? (d.name.trim() ? newGroupId(d.name.trim(), this.groups) : "");
    const addable = this.areas.filter((a) => !d.areas.includes(a.id));
    const sensorsBad = KINDS.some((k) => (d[k].mode === "single" && d[k].entities.length !== 1) || (d[k].mode === "selection" && !d[k].entities.length));
    const title = this.t(d.original ? "editGroup" : "createGroup");
    return html`<div class="overlay" @click=${(e: Event) => e.target === e.currentTarget && (this.draft = null)}><div class="dialog" role="dialog" aria-label=${title}>
      <header><button class="iconbtn" data-action="dialog-close" aria-label=${this.t("close")} @click=${() => (this.draft = null)}>${this.svg(ICON.close)}</button><h2>${title}</h2></header>
      <div class="idrow"><div class="idlabel">${this.t("gidLabel")}</div><div class="gid">${id}</div></div>
      ${this.field(`${this.t("gname")}*`, "gname", d.name, (v) => this.patch({ name: v }))}
      ${this.field(this.t("glevel"), "glevel", d.level, (v) => this.patch({ level: v }), { type: "number" })}
      <div class="helper indent">${this.t("levelHelp")}</div>
      ${this.renderIconField(d)}
      <h3>${this.t("grooms")}</h3>
      <div class="chips" data-field="rooms">${this.known(d.areas).map((a) => html`<span class="chip" data-chip=${a.id}>${a.icon ? html`<ha-icon .icon=${a.icon}></ha-icon>` : nothing}${a.name}<button class="chipx" aria-label="${this.t("removeItem")} ${a.name}" @click=${() => this.changeRooms(d.areas.filter((x) => x !== a.id))}>${this.svg(ICON.close)}</button></span>`)}</div>
      ${addable.length ? html`<div class="menuwrap"><button class="tonal" data-action="room-picker" @click=${() => this.patch({ picker: !d.picker })}>${this.svg(ICON.playlistPlus)}${this.t("addRoom")}</button>
        ${d.picker ? html`<div class="scrim" @click=${() => this.patch({ picker: false })}></div><div class="menu picker" role="listbox">${addable.map((a) => {
          const inside = groupsOf(this.groups, a.id).filter((g) => g.id !== d.original).map((g) => g.name);
          return html`<button class="item" role="option" data-pick=${a.id} @click=${() => { this.patch({ picker: false }); this.changeRooms([...d.areas, a.id]); }}><span>${a.name}${inside.length ? html`<small> (${this.t("inGroups", { groups: inside.join(", ") })})</small>` : nothing}</span></button>`;
        })}</div>` : nothing}</div>` : nothing}
      <h3>${this.t("galiases")}</h3>
      <p class="text">${this.t("aliasHint")}</p>
      <div class="chips" data-field="aliases">${d.aliases.map((al) => html`<span class="chip" data-alias=${al}>${al}<button class="chipx" aria-label="${this.t("removeItem")} ${al}" @click=${() => this.patch({ aliases: d.aliases.filter((x) => x !== al) })}>${this.svg(ICON.close)}</button></span>`)}</div>
      ${d.aliasOpen ? html`<div class="aliasrow"><label class="field"><span class="flabel">${this.t("addAliasHint")}</span><input class="alias" .value=${d.alias} @input=${(e: Event) => this.patch({ alias: (e.target as HTMLInputElement).value })}
        @keydown=${(e: KeyboardEvent) => { if (e.key === "Enter") { e.preventDefault(); this.addAlias(); } }}></label>
        <button class="tonal" data-action="alias-add" @click=${this.addAlias}>${this.svg(ICON.plus)}</button></div>`
        : html`<button class="tonal" data-action="alias-open" @click=${() => this.patch({ aliasOpen: true })}>${this.svg(ICON.plus)}${this.t("addAlias")}</button>`}
      <section class="expansion" data-panel>
        <button class="exphead" aria-expanded=${d.panel} @click=${() => this.patch({ panel: !d.panel })}><span>${this.t("sensorsPanel")}</span><span class="chev ${d.panel ? "open" : ""}">${this.svg(ICON.chevron)}</span></button>
        ${d.panel ? html`<div class="expbody">${KINDS.map((k) => this.renderSensor(k, d))}${sensorsBad ? html`<div class="helper warn">${this.t("needSensor")}</div>` : nothing}</div>` : nothing}
      </section>
      <footer><button class="textbtn" data-action="dialog-cancel" @click=${() => (this.draft = null)}>${this.t("cancel")}</button>
        <button class="filled" data-action="dialog-save" ?disabled=${!this.valid(d)} @click=${this.saveDialog}>${this.t("save")}</button></footer>
    </div></div>`;
  }

  private renderMover() {
    const m = this.mover;
    if (!m) return nothing;
    const targets = this.groups.filter((g) => g.id !== m.gid && !g.areas.includes(m.aid));
    return html`<div class="overlay" @click=${(e: Event) => e.target === e.currentTarget && (this.mover = null)}><div class="dialog small" role="dialog">
      <header><button class="iconbtn" aria-label=${this.t("close")} @click=${() => (this.mover = null)}>${this.svg(ICON.close)}</button><h2>${this.areaName(m.aid)}</h2></header>
      <label class="field selectfield"><span class="flabel">${this.t("chooseGroup")}</span><select class="target" @change=${(e: Event) => (this.mover = { ...m, target: (e.target as HTMLSelectElement).value })}>
        ${targets.map((g) => html`<option value=${g.id} ?selected=${g.id === m.target}>${g.name}</option>`)}</select><span class="caret">${this.svg(ICON.caret)}</span></label>
      <footer><button class="textbtn" @click=${() => (this.mover = null)}>${this.t("cancel")}</button><button class="filled" data-action="mover-ok" @click=${this.applyMover}>${this.t("ok")}</button></footer>
    </div></div>`;
  }

  private renderConfirm() {
    const g = this.groups.find((x) => x.id === this.confirm);
    if (!g) return nothing;
    return html`<div class="overlay"><div class="dialog small" role="alertdialog">
      <header><h2>${this.t("deleteTitle", { name: g.name })}</h2></header><p class="text">${this.t("deleteText")}</p>
      <footer><button class="textbtn" data-action="confirm-cancel" @click=${() => (this.confirm = null)}>${this.t("cancel")}</button>
        <button class="filled danger" data-action="confirm-delete" @click=${() => this.deleteGroup(g.id)}>${this.t("delete")}</button></footer>
    </div></div>`;
  }

  render() {
    if (this.failed) return html`<p class="msg">${this.t("notLoaded")}</p>`;
    if (!this.ready) return html`<p class="msg">${this.t("loading")}</p>`;
    return html`
      <div class="head">
        ${this.reorderGroups ? html`<button class="textbtn" data-action="groups-done" @click=${() => (this.reorderGroups = false)}>${this.t("done")}</button>` : this.groups.length > 1 ? this.menuButton({ kind: "page" }, "page-menu") : nothing}
      </div>
      ${this.notice ? html`<p class="notice" data-notice role="status">${this.t("prunedNotice")} <button class="iconbtn" aria-label=${this.t("close")} @click=${() => (this.notice = false)}>${this.svg(ICON.close)}</button></p>` : nothing}
      <div class="groups">${repeat(this.shownGroups(), (g) => g.id, (g) => this.renderGroup(g))}</div>
      ${this.groups.length ? nothing : html`<p class="muted empty" data-empty>${this.t("noGroups")}</p>`}
      ${this.renderUngrouped()}
      <button class="fab" data-action="add-group" @click=${() => this.openDialog(null)}>${this.svg(ICON.plus)}${this.t("add")}</button>
      <span class="status ${this.status}" role="status" data-status=${this.status}>${this.statusText()}</span>
      ${this.renderDialog()}${this.renderMover()}${this.renderConfirm()}`;
  }

  static styles = css`
    :host { display: block; padding: 8px 16px 96px; box-sizing: border-box; color: var(--primary-text-color); }
    svg { fill: currentColor; flex: none; }
    .msg { padding: 24px; } .muted { color: var(--secondary-text-color); font-size: .85rem; } .empty { padding: 24px 8px; } .warn { color: var(--error-color, #db4437); }
    .head { display: flex; justify-content: flex-end; align-items: center; min-height: 40px; }
    .grow { flex: 1; }
    .status { position: fixed; left: 24px; bottom: 20px; z-index: 12; padding: 8px 14px; border-radius: 8px; background: var(--card-background-color); border: 1px solid var(--divider-color); font-size: .85rem; color: var(--secondary-text-color); box-shadow: 0 2px 8px rgba(0,0,0,.25); }
    .status.idle, .status:empty { display: none; } .status.error { color: var(--error-color, #db4437); font-weight: 600; }
    .notice { background: var(--secondary-background-color); border-radius: 8px; padding: 4px 8px 4px 14px; font-size: .9rem; display: flex; align-items: center; gap: 8px; justify-content: space-between; }
    /* sections and cards, like the floors of the Areas page */
    .group { margin: 0 0 22px; }
    .group header { display: flex; align-items: center; gap: 8px; min-height: 40px; }
    .group header ha-icon { --mdc-icon-size: 18px; color: var(--secondary-text-color); }
    .group header h2 { margin: 0; font-size: .85rem; font-weight: 400; color: var(--secondary-text-color); }
    .cards { display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-start; padding-top: 4px; }
    .card { width: 180px; background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: 12px; overflow: hidden; box-sizing: border-box; }
    .picture { height: 100px; display: flex; align-items: center; justify-content: center; background: var(--secondary-background-color); color: var(--primary-text-color); }
    .picture ha-icon { --mdc-icon-size: 40px; }
    .info { padding: 8px 8px 14px 16px; min-height: 66px; box-sizing: border-box; }
    .line { display: flex; align-items: center; justify-content: space-between; gap: 4px; min-height: 40px; }
    .line strong { font-size: 1rem; font-weight: 400; line-height: 1.2; overflow-wrap: anywhere; }
    .info small { display: block; color: var(--secondary-text-color); font-size: .75rem; padding-right: 8px; margin-top: 2px; }
    .menuwrap { position: relative; display: inline-flex; }
    .iconbtn, .chipx { display: inline-flex; align-items: center; justify-content: center; width: 40px; height: 40px; padding: 0; background: none; border: 0; border-radius: 50%; color: var(--secondary-text-color); cursor: pointer; }
    .iconbtn:hover { background: var(--secondary-background-color); } .iconbtn svg { width: 24px; height: 24px; }
    .sortable { cursor: grab; touch-action: none; user-select: none; -webkit-user-select: none; }
    .grip { color: var(--secondary-text-color); font-size: 1.2rem; letter-spacing: -3px; padding: 6px 10px; border-radius: 6px; cursor: grab; } .grip:focus-visible { outline: 2px solid var(--primary-color); }
    .card.dragging, .group.dragging { opacity: .55; box-shadow: 0 6px 18px rgba(0,0,0,.35); border-color: var(--primary-color); }
    .group.compact { margin: 6px 0; } .group.compact header { padding: 4px 8px 4px 16px; background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: 12px; }
    /* menus */
    .scrim { position: fixed; inset: 0; z-index: 20; }
    .menu { position: absolute; right: 0; top: 100%; z-index: 21; min-width: 250px; background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: 12px; box-shadow: 0 6px 24px rgba(0,0,0,.4); padding: 6px 0; overflow: hidden; }
    .menu hr { border: 0; border-top: 1px solid var(--divider-color); margin: 6px 0; }
    .item { display: flex; align-items: center; gap: 16px; width: 100%; text-align: left; font: inherit; background: none; border: 0; color: var(--primary-text-color); padding: 12px 20px; cursor: pointer; }
    .item svg { color: var(--secondary-text-color); } .item:hover { background: var(--secondary-background-color); } .item.danger, .item.danger svg { color: var(--error-color, #db4437); }
    .menu.picker { right: auto; left: 0; max-height: 300px; overflow-y: auto; } .menu.picker .item { padding: 10px 20px; } .menu.picker small { color: var(--secondary-text-color); }
    .fab { position: fixed; right: 20px; bottom: 20px; z-index: 10; display: inline-flex; align-items: center; gap: 8px; font: inherit; font-weight: 500; background: var(--primary-color); color: var(--text-primary-color, #fff); border: 0; border-radius: 16px; height: 56px; padding: 0 20px 0 16px; cursor: pointer; box-shadow: 0 3px 10px rgba(0,0,0,.4); }
    /* dialogs */
    .overlay { position: fixed; inset: 0; z-index: 30; background: rgba(0,0,0,.55); display: flex; align-items: flex-start; justify-content: center; overflow-y: auto; padding: 24px 12px; box-sizing: border-box; }
    .dialog { width: 100%; max-width: 580px; background: var(--ha-dialog-surface-background, var(--mdc-theme-surface, var(--card-background-color))); color: var(--primary-text-color); border-radius: 28px; padding: 16px 24px 20px; box-sizing: border-box; box-shadow: 0 10px 40px rgba(0,0,0,.5); }
    .dialog.small { max-width: 400px; margin-top: 15vh; }
    .dialog header { display: flex; align-items: center; gap: 12px; min-height: 56px; margin-left: -8px; } .dialog header h2 { margin: 0; font-size: 1.4rem; font-weight: 400; }
    .idrow { padding: 8px 16px 10px; } .idlabel { font-size: 1rem; } .gid { color: var(--secondary-text-color); font-size: .9rem; min-height: 1.2em; }
    .field { position: relative; display: block; margin: 12px 0 4px; background: color-mix(in srgb, var(--primary-text-color) 8%, var(--card-background-color)); border-radius: 4px 4px 0 0; border-bottom: 1px solid var(--secondary-text-color); }
    .field:focus-within { border-bottom: 2px solid var(--primary-color); } .field:focus-within .flabel { color: var(--primary-color); }
    .flabel { position: absolute; left: 16px; top: 8px; font-size: .75rem; color: var(--secondary-text-color); pointer-events: none; }
    .field input, .field select { display: block; width: 100%; box-sizing: border-box; background: none; border: 0; outline: none; color: var(--primary-text-color); font: inherit; padding: 26px 16px 8px; min-height: 56px; appearance: none; -webkit-appearance: none; }
    .field select option { background: var(--card-background-color); }
    .field.withicon { display: flex; align-items: center; } .field.withicon input { flex: 1; padding-left: 0; } .field.withicon .flabel { left: 56px; }
    .lead { width: 56px; display: inline-flex; justify-content: center; color: var(--secondary-text-color); flex: none; } .field.withicon .iconbtn.clear { margin-right: 4px; }
    .selectfield .caret { position: absolute; right: 12px; top: 50%; transform: translateY(-50%); pointer-events: none; color: var(--secondary-text-color); display: inline-flex; }
    .helper { font-size: .75rem; color: var(--secondary-text-color); padding: 4px 16px 0; } .helper.indent { padding-bottom: 8px; }
    ha-icon-picker { display: block; margin: 12px 0; }
    .dialog h3 { margin: 22px 0 10px; font-size: 1.25rem; font-weight: 400; color: var(--primary-text-color); text-transform: none; letter-spacing: 0; }
    .text { margin: 0 0 12px; line-height: 1.45; }
    .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
    .chip { display: inline-flex; align-items: center; gap: 8px; height: 32px; padding: 0 4px 0 12px; border-radius: 16px; border: 1px solid var(--divider-color); font-size: .9rem; } .chip ha-icon { --mdc-icon-size: 20px; color: var(--secondary-text-color); }
    .chipx { width: 28px; height: 28px; color: var(--primary-text-color); } .chipx svg { width: 18px; height: 18px; }
    .tonal { display: inline-flex; align-items: center; gap: 8px; height: 40px; padding: 0 20px 0 14px; border: 0; border-radius: 20px; background: color-mix(in srgb, var(--primary-color) 18%, var(--card-background-color)); color: var(--primary-color); font: inherit; font-weight: 500; cursor: pointer; }
    .aliasrow { display: flex; align-items: center; gap: 8px; } .aliasrow .field { flex: 1; }
    .expansion { margin-top: 24px; border: 1px solid var(--divider-color); border-radius: 12px; }
    .exphead { display: flex; width: 100%; align-items: center; justify-content: space-between; background: none; border: 0; color: var(--primary-text-color); font: inherit; font-weight: 500; padding: 14px 16px; cursor: pointer; }
    .chev { display: inline-flex; transition: transform .15s; transform: rotate(180deg); } .chev.open { transform: none; }
    .expbody { padding: 0 16px 16px; } .sensorbox { margin-top: 8px; } .sensortitle { font-size: 1rem; margin: 10px 0 0; }
    .sensors { list-style: none; margin: 8px 0; padding: 0 16px; font-size: .9rem; } .sensors.readonly li { padding: 4px 0; color: var(--secondary-text-color); }
    label.check { display: flex; gap: 8px; align-items: center; padding: 4px 0; }
    footer { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-top: 26px; }
    .textbtn { background: none; border: 0; color: var(--primary-color); font: inherit; font-weight: 500; padding: 10px 14px; border-radius: 20px; cursor: pointer; }
    .filled { font: inherit; font-weight: 500; background: var(--primary-color); color: var(--text-primary-color, #fff); border: 0; border-radius: 20px; padding: 10px 24px; cursor: pointer; }
    .filled:disabled { background: color-mix(in srgb, var(--primary-text-color) 12%, transparent); color: color-mix(in srgb, var(--primary-text-color) 38%, transparent); cursor: default; } .filled.danger { background: var(--error-color, #db4437); }
  `;
}
if (!customElements.get("home-structure-groups")) customElements.define("home-structure-groups", HomeStructureGroups);
