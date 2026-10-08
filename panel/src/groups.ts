import { LitElement, css, html, nothing } from "lit";
import { property, state } from "lit/decorators.js";
import { translator } from "./i18n";
import type { Key, T } from "./i18n";
import { addRoom, clone, groupsOf, moveGroup, moveRoom, moveRoomInGroup, newGroupId, removeFromAll, removeRoom, ungrouped } from "./logic";
import type { Area, Group, GroupKind, GroupSensor, Hass, SensorCfg, SensorMode } from "./types";

const KINDS: GroupKind[] = ["temperature", "humidity"];
const MODES: SensorMode[] = ["none", "single", "all", "selection"];

type Menu = { kind: "page" } | { kind: "group"; gid: string } | { kind: "room"; gid: string | null; aid: string } | null;
type Mover = { mode: "move" | "add"; gid: string | null; aid: string; target: string } | null;
interface Draft { original: string | null; id: string; name: string; level: string; icon: string; areas: string[]; aliases: string[]; alias: string; temperature: SensorCfg; humidity: SensorCfg }

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

  private floorLabel(a: Area): string {
    return a.floor ?? "";
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
    return { original: null, id: "", name: "", level: "", icon: "", areas: [], aliases: [], alias: "", temperature: none(), humidity: none() };
  }

  private openDialog(gid: string | null): void {
    this.menu = null;
    const g = gid ? this.groups.find((x) => x.id === gid) : null;
    this.draft = g ? { original: g.id, id: g.id, name: g.name, level: g.level === null ? "" : String(g.level), icon: g.icon ?? "", areas: this.known(g.areas).map((a) => a.id),
      aliases: [...g.aliases], alias: "", temperature: clone(g.temperature), humidity: clone(g.humidity) } : this.blank();
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

  // ------------------------------------------------------------------ rendering
  private statusText(): string {
    return this.status === "saving" ? this.t("saving") : this.status === "saved" ? `✓ ${this.t("saved")}` : this.status === "error" ? this.t("saveFailed", { error: this.error }) : "";
  }

  private count(n: number): string {
    return n === 1 ? this.t("roomsOne") : this.t("roomsMany", { n });
  }

  private menuItem(action: string, label: string, fn: () => void, danger = false) {
    return html`<button class="item ${danger ? "danger" : ""}" role="menuitem" data-action=${action} @click=${() => this.act(fn)}>${label}</button>`;
  }

  private renderMenu(m: NonNullable<Menu>) {
    const items = [];
    if (m.kind === "page") {
      items.push(this.menuItem("reorder-groups", this.t("rearrangeGroups"), () => (this.reorderGroups = true)));
    } else if (m.kind === "group") {
      items.push(this.menuItem("reorder-rooms", this.t("rearrangeRooms"), () => (this.reorderRooms = m.gid)));
      items.push(this.menuItem("edit-group", this.t("editGroup"), () => this.openDialog(m.gid)));
      items.push(this.menuItem("delete-group", this.t("deleteGroup"), () => (this.confirm = m.gid), true));
    } else {
      const others = this.groups.some((g) => g.id !== m.gid && !g.areas.includes(m.aid));
      const several = groupsOf(this.groups, m.aid).length > 1;
      if (others && m.gid) items.push(this.menuItem("move-room", this.t("moveTo"), () => this.openMover("move", m.gid, m.aid)));
      if (others) items.push(this.menuItem("add-room", this.t("addTo"), () => this.openMover("add", m.gid, m.aid)));
      if (m.gid) items.push(this.menuItem("remove-room", this.t("removeFromGroup"), () => this.persist(removeRoom(this.groups, m.gid!, m.aid))));
      if (several) items.push(this.menuItem("remove-all", this.t("removeFromAll"), () => this.persist(removeFromAll(this.groups, m.aid))));
    }
    return html`<div class="scrim" @click=${() => (this.menu = null)}></div><div class="menu" role="menu">${items}</div>`;
  }

  private menuButton(menu: NonNullable<Menu>, action: string) {
    const open = this.menu && JSON.stringify(this.menu) === JSON.stringify(menu);
    return html`<span class="menuwrap"><button class="dots" data-action=${action} aria-label=${this.t("more")} aria-haspopup="menu" @click=${() => (this.menu = open ? null : menu)}>⋮</button>${open ? this.renderMenu(menu) : nothing}</span>`;
  }

  private renderCard(a: Area, g: Group | null, index: number, total: number) {
    const rearranging = !!g && this.reorderRooms === g.id;
    return html`<div class="card" data-room=${a.id}>
      <div class="cardtext"><strong>${a.name}</strong>${this.floorLabel(a) ? html`<small>${this.floorLabel(a)}</small>` : nothing}</div>
      ${rearranging ? html`<span class="arrows">
        <button class="arrow" data-action="room-earlier" ?disabled=${index === 0} aria-label=${this.t("earlier")} @click=${() => this.persist(moveRoomInGroup(this.groups, g!.id, a.id, -1))}>◀</button>
        <button class="arrow" data-action="room-later" ?disabled=${index === total - 1} aria-label=${this.t("later")} @click=${() => this.persist(moveRoomInGroup(this.groups, g!.id, a.id, 1))}>▶</button></span>`
        : this.menuButton({ kind: "room", gid: g?.id ?? null, aid: a.id }, "room-menu")}
    </div>`;
  }

  private renderGroup(g: Group, index: number) {
    const rooms = this.known(g.areas);
    const rearranging = this.reorderRooms === g.id;
    return html`<section class="group" data-group=${g.id}>
      <header>
        ${g.icon ? html`<ha-icon .icon=${g.icon}></ha-icon>` : nothing}
        <h2>${g.name}</h2><small class="muted">${this.count(rooms.length)}</small>
        <span class="grow"></span>
        ${this.reorderGroups ? html`<button class="arrow" data-action="group-up" ?disabled=${index === 0} aria-label=${this.t("earlier")} @click=${() => this.persist(moveGroup(this.groups, g.id, -1))}>▲</button>
          <button class="arrow" data-action="group-down" ?disabled=${index === this.groups.length - 1} aria-label=${this.t("later")} @click=${() => this.persist(moveGroup(this.groups, g.id, 1))}>▼</button>`
          : rearranging ? html`<button class="plain" data-action="rooms-done" @click=${() => (this.reorderRooms = null)}>${this.t("done")}</button>` : this.menuButton({ kind: "group", gid: g.id }, "group-menu")}
      </header>
      <div class="cards">${rooms.map((a, i) => this.renderCard(a, g, i, rooms.length))}${rooms.length ? nothing : html`<p class="muted">${this.t("emptyGroup")}</p>`}</div>
    </section>`;
  }

  private renderUngrouped() {
    const rest = ungrouped(this.areas, this.groups);
    if (!rest.length || !this.groups.length) return nothing;
    return html`<section class="group ungrouped" data-group="">
      <header><h2>${this.t("ungrouped")}</h2><small class="muted">${this.count(rest.length)}</small></header>
      <div class="cards">${rest.map((a, i) => this.renderCard(a, null, i, rest.length))}</div></section>`;
  }

  private renderSensor(kind: GroupKind, d: Draft) {
    const cfg = d[kind], cands = this.cands[kind];
    const label = (s: GroupSensor) => `${s.name} · ${s.area} · ${s.state} ${s.state === "unavailable" || s.state === "unknown" ? "" : s.unit}`.trim();
    return html`<div class="sensorbox" data-kind=${kind}>
      <label>${this.t(`gs_${kind}` as Key)}<select class="mode" @change=${(e: Event) => this.setMode(kind, (e.target as HTMLSelectElement).value as SensorMode)}>
        ${MODES.map((m) => html`<option value=${m} ?selected=${m === cfg.mode}>${this.t(`gm_${m}` as Key)}</option>`)}</select></label>
      ${cfg.mode === "single" ? html`<select class="sensor" @change=${(e: Event) => this.setSensor(kind, { mode: "single", entities: [(e.target as HTMLSelectElement).value].filter(Boolean) })}>
        <option value="" ?selected=${!cfg.entities.length}>${this.t("pickSensor")}</option>
        ${cands.map((s) => html`<option value=${s.entity_id} ?selected=${cfg.entities[0] === s.entity_id}>${label(s)}</option>`)}</select>` : nothing}
      ${cfg.mode === "selection" ? html`<small class="muted">${this.t("sensorsSelectionHelp")}</small>
        <ul class="sensors">${cands.map((s) => html`<li><label class="check"><input type="checkbox" .checked=${cfg.entities.includes(s.entity_id)} data-sensor=${s.entity_id}
          @change=${(e: Event) => this.toggleSensor(kind, s.entity_id, (e.target as HTMLInputElement).checked)}>${label(s)}</label></li>`)}</ul>` : nothing}
      ${cfg.mode === "all" ? html`<small class="muted">${this.t("sensorsAllHelp")}</small>
        <ul class="sensors readonly">${cands.map((s) => html`<li data-source=${s.entity_id}>${label(s)}</li>`)}</ul>` : nothing}
      ${cfg.mode !== "none" && !cands.length ? html`<small class="muted">${this.t("noSensorsHere")}</small>` : nothing}
    </div>`;
  }

  private renderDialog() {
    const d = this.draft;
    if (!d) return nothing;
    const id = d.original ?? (d.name.trim() ? newGroupId(d.name.trim(), this.groups) : "");
    const addable = this.areas.filter((a) => !d.areas.includes(a.id));
    const sensorsBad = KINDS.some((k) => (d[k].mode === "single" && d[k].entities.length !== 1) || (d[k].mode === "selection" && !d[k].entities.length));
    return html`<div class="overlay" @click=${(e: Event) => e.target === e.currentTarget && (this.draft = null)}><div class="dialog" role="dialog" aria-label=${this.t(d.original ? "editGroup" : "createGroup")}>
      <header><h2>${this.t(d.original ? "editGroup" : "createGroup")}</h2><button class="x" data-action="dialog-close" aria-label=${this.t("close")} @click=${() => (this.draft = null)}>×</button></header>
      <label>${this.t("gid")}<input class="gid" disabled .value=${id}></label>
      <label>${this.t("gname")}<input class="gname" .value=${d.name} @input=${(e: Event) => this.patch({ name: (e.target as HTMLInputElement).value })}></label>
      <label>${this.t("glevel")}<input class="glevel" type="number" step="1" .value=${d.level} @input=${(e: Event) => this.patch({ level: (e.target as HTMLInputElement).value })}></label>
      <label>${this.t("gicon")}<span class="iconrow"><input class="gicon" placeholder="mdi:bed" .value=${d.icon} @input=${(e: Event) => this.patch({ icon: (e.target as HTMLInputElement).value })}>${d.icon.trim() ? html`<ha-icon .icon=${d.icon.trim()}></ha-icon>` : nothing}</span></label>
      <h3>${this.t("grooms")}</h3>
      <div class="chips" data-field="rooms">${this.known(d.areas).map((a) => html`<span class="chip" data-chip=${a.id}>${a.name}<button class="chipx" aria-label="${this.t("removeItem")} ${a.name}" @click=${() => this.changeRooms(d.areas.filter((x) => x !== a.id))}>×</button></span>`)}</div>
      ${addable.length ? html`<select class="addroom" @change=${(e: Event) => { const v = (e.target as HTMLSelectElement).value; (e.target as HTMLSelectElement).value = ""; if (v) this.changeRooms([...d.areas, v]); }}>
        <option value="">${this.t("addRoom")}</option>
        ${addable.map((a) => { const inside = groupsOf(this.groups, a.id).filter((g) => g.id !== d.original).map((g) => g.name); return html`<option value=${a.id}>${a.name}${inside.length ? ` (${this.t("inGroups", { groups: inside.join(", ") })})` : ""}</option>`; })}</select>` : nothing}
      <h3>${this.t("galiases")}</h3>
      <div class="chips" data-field="aliases">${d.aliases.map((al) => html`<span class="chip" data-alias=${al}>${al}<button class="chipx" aria-label="${this.t("removeItem")} ${al}" @click=${() => this.patch({ aliases: d.aliases.filter((x) => x !== al) })}>×</button></span>`)}</div>
      <div class="iconrow"><input class="alias" placeholder=${this.t("addAlias")} .value=${d.alias} @input=${(e: Event) => this.patch({ alias: (e.target as HTMLInputElement).value })}
        @keydown=${(e: KeyboardEvent) => { if (e.key === "Enter") { e.preventDefault(); this.addAlias(); } }}><button class="plain narrowbtn" data-action="alias-add" @click=${this.addAlias}>+</button></div>
      <small class="muted">${this.t("aliasHint")}</small>
      ${KINDS.map((k) => this.renderSensor(k, d))}
      ${sensorsBad ? html`<p class="muted warn">${this.t("needSensor")}</p>` : nothing}
      <div class="row"><button class="plain" data-action="dialog-cancel" @click=${() => (this.draft = null)}>${this.t("cancel")}</button>
        <button class="primary" data-action="dialog-save" ?disabled=${!this.valid(d)} @click=${this.saveDialog}>${this.t("save")}</button></div>
    </div></div>`;
  }

  private renderMover() {
    const m = this.mover;
    if (!m) return nothing;
    const targets = this.groups.filter((g) => g.id !== m.gid && !g.areas.includes(m.aid));
    return html`<div class="overlay" @click=${(e: Event) => e.target === e.currentTarget && (this.mover = null)}><div class="dialog small" role="dialog">
      <header><h2>${this.areaName(m.aid)}</h2><button class="x" aria-label=${this.t("close")} @click=${() => (this.mover = null)}>×</button></header>
      <label>${this.t("chooseGroup")}<select class="target" @change=${(e: Event) => (this.mover = { ...m, target: (e.target as HTMLSelectElement).value })}>
        ${targets.map((g) => html`<option value=${g.id} ?selected=${g.id === m.target}>${g.name}</option>`)}</select></label>
      <div class="row"><button class="plain" @click=${() => (this.mover = null)}>${this.t("cancel")}</button><button class="primary" data-action="mover-ok" @click=${this.applyMover}>${this.t("ok")}</button></div>
    </div></div>`;
  }

  private renderConfirm() {
    const g = this.groups.find((x) => x.id === this.confirm);
    if (!g) return nothing;
    return html`<div class="overlay"><div class="dialog small" role="alertdialog">
      <header><h2>${this.t("deleteTitle", { name: g.name })}</h2></header><p>${this.t("deleteText")}</p>
      <div class="row"><button class="plain" data-action="confirm-cancel" @click=${() => (this.confirm = null)}>${this.t("cancel")}</button>
        <button class="primary danger" data-action="confirm-delete" @click=${() => this.deleteGroup(g.id)}>${this.t("delete")}</button></div>
    </div></div>`;
  }

  render() {
    if (this.failed) return html`<p class="msg">${this.t("notLoaded")}</p>`;
    if (!this.ready) return html`<p class="msg">${this.t("loading")}</p>`;
    const reordering = this.reorderGroups;
    return html`
      <div class="head"><h1>${this.t("groupsTitle")}</h1>
        <span class="status ${this.status}" role="status" data-status=${this.status}>${this.statusText()}</span><span class="grow"></span>
        ${reordering ? html`<button class="plain" data-action="groups-done" @click=${() => (this.reorderGroups = false)}>${this.t("done")}</button>` : this.groups.length > 1 ? this.menuButton({ kind: "page" }, "page-menu") : nothing}
      </div>
      ${this.notice ? html`<p class="notice" data-notice role="status">${this.t("prunedNotice")} <button class="plain narrowbtn" @click=${() => (this.notice = false)}>×</button></p>` : nothing}
      ${this.groups.map((g, i) => this.renderGroup(g, i))}
      ${this.groups.length ? nothing : html`<p class="muted empty" data-empty>${this.t("noGroups")}</p>`}
      ${this.renderUngrouped()}
      <button class="fab" data-action="add-group" @click=${() => this.openDialog(null)}>＋ ${this.t("add")}</button>
      ${this.renderDialog()}${this.renderMover()}${this.renderConfirm()}`;
  }

  static styles = css`
    :host { display: block; padding: 12px 16px 96px; max-width: 1100px; margin: 0 auto; box-sizing: border-box; }
    .msg { padding: 24px; }
    .head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; } .grow { flex: 1; }
    h1 { font-size: 1.25rem; font-weight: 400; margin: 0; }
    h2 { font-size: 1.05rem; font-weight: 500; margin: 0; } h3 { font-size: .85rem; margin: 14px 0 6px; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .04em; }
    .muted { color: var(--secondary-text-color); font-size: .85rem; } .warn { color: var(--error-color, #db4437); }
    .status { font-size: .85rem; color: var(--secondary-text-color); margin-left: 8px; } .status.error { color: var(--error-color, #db4437); font-weight: 600; }
    .notice { background: var(--secondary-background-color); border-radius: 8px; padding: 8px 12px; font-size: .9rem; display: flex; align-items: center; gap: 8px; justify-content: space-between; }
    .group { margin: 18px 0 8px; } .group header { display: flex; align-items: center; gap: 10px; padding-bottom: 8px; border-bottom: 1px solid var(--divider-color); margin-bottom: 12px; }
    .group header ha-icon { color: var(--secondary-text-color); }
    .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 12px; }
    .card { display: flex; align-items: center; justify-content: space-between; gap: 6px; min-height: 56px; padding: 8px 6px 8px 14px; background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: 12px; }
    .cardtext { display: flex; flex-direction: column; min-width: 0; } .cardtext strong { font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } .cardtext small { color: var(--secondary-text-color); }
    .menuwrap { position: relative; display: inline-block; }
    .dots, .arrow, .x, .chipx { background: none; border: 0; color: var(--secondary-text-color); cursor: pointer; font: inherit; font-size: 1.3rem; line-height: 1; padding: 6px 8px; border-radius: 50%; }
    .arrow { font-size: .95rem; } .arrow:disabled { opacity: .3; cursor: default; } .dots:hover, .arrow:hover:not(:disabled) { background: var(--secondary-background-color); }
    .arrows { display: flex; }
    .scrim { position: fixed; inset: 0; z-index: 20; }
    .menu { position: absolute; right: 0; top: 100%; z-index: 21; min-width: 230px; background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: 8px; box-shadow: 0 6px 24px rgba(0,0,0,.3); padding: 4px 0; }
    .item { display: block; width: 100%; text-align: left; font: inherit; background: none; border: 0; color: var(--primary-text-color); padding: 10px 16px; cursor: pointer; } .item:hover { background: var(--secondary-background-color); } .item.danger { color: var(--error-color, #db4437); }
    .fab { position: fixed; right: 24px; bottom: 24px; z-index: 10; font: inherit; font-weight: 500; background: var(--primary-color); color: var(--text-primary-color, #fff); border: 0; border-radius: 16px; padding: 16px 22px; cursor: pointer; box-shadow: 0 4px 14px rgba(0,0,0,.35); }
    .empty { padding: 24px 0; }
    .overlay { position: fixed; inset: 0; z-index: 30; background: rgba(0,0,0,.45); display: flex; align-items: flex-start; justify-content: center; overflow-y: auto; padding: 24px 12px; box-sizing: border-box; }
    .dialog { width: 100%; max-width: 560px; background: var(--card-background-color); color: var(--primary-text-color); border-radius: 14px; padding: 16px 20px 20px; box-sizing: border-box; box-shadow: 0 10px 40px rgba(0,0,0,.4); } .dialog.small { max-width: 380px; margin-top: 15vh; }
    .dialog header { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 8px; }
    label { display: block; font-size: .8rem; color: var(--secondary-text-color); margin: 10px 0; } label.check { display: flex; gap: 8px; align-items: center; color: var(--primary-text-color); font-size: .9rem; margin: 4px 0; }
    input:not([type=checkbox]), select { width: 100%; box-sizing: border-box; margin-top: 4px; font: inherit; padding: 8px 10px; border-radius: 6px; border: 1px solid var(--divider-color); background: var(--secondary-background-color); color: var(--primary-text-color); }
    input:disabled { opacity: .7; }
    .iconrow { display: flex; align-items: center; gap: 8px; } .iconrow input { margin-top: 0; } label .iconrow { margin-top: 4px; }
    .chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 4px 0 8px; }
    .chip { display: inline-flex; align-items: center; gap: 2px; padding: 2px 4px 2px 12px; border-radius: 999px; background: var(--secondary-background-color); border: 1px solid var(--divider-color); font-size: .9rem; } .chipx { font-size: 1.1rem; padding: 2px 8px; }
    .sensorbox { margin-top: 14px; padding-top: 4px; border-top: 1px solid var(--divider-color); } .sensorbox select.sensor { margin: 6px 0; }
    .sensors { list-style: none; margin: 6px 0; padding: 0; font-size: .9rem; } .sensors.readonly li { padding: 4px 0; color: var(--secondary-text-color); }
    .row { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; }
    .plain { font: inherit; background: none; border: 1px solid var(--divider-color); color: var(--primary-text-color); border-radius: 6px; padding: 7px 14px; cursor: pointer; } .narrowbtn { padding: 6px 10px; }
    .primary { font: inherit; background: var(--primary-color); color: var(--text-primary-color, #fff); border: 0; border-radius: 6px; padding: 8px 18px; cursor: pointer; } .primary:disabled { opacity: .45; cursor: default; } .primary.danger { background: var(--error-color, #db4437); }
  `;
}
if (!customElements.get("home-structure-groups")) customElements.define("home-structure-groups", HomeStructureGroups);
