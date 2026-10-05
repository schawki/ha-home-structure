import { LitElement, css, html, nothing, svg } from "lit";
import { property, state } from "lit/decorators.js";
import { translator } from "./i18n";
import type { Key, T } from "./i18n";
import { BOX_H, BOX_W, autoLayout, clone, connOf, newId, nextFree, placedSpaces, sepState, shutterState, slug, trayAreas } from "./logic";
import type { Area, Bootstrap, Candidates, Conn, Hass, Options, Pos, Sep, SepState, Space } from "./types";

type Selection = { kind: "space" | "link"; id: string } | null;
const MOVE_THRESHOLD = 4;

class HomeStructurePanel extends LitElement {
  @property({ attribute: false }) hass!: Hass;
  @property({ type: Boolean }) narrow = false;
  @state() private boot: Bootstrap | null = null;
  @state() private opts!: Options;
  @state() private history: Options[] = [];
  @state() private status: "idle" | "saving" | "saved" | "error" = "idle";
  @state() private error = "";
  @state() private selection: Selection = null;
  @state() private live: { id: string; pos: Pos } | null = null;
  @state() private linking: { from: string; x: number; y: number } | null = null;
  @state() private zoneForm: { kind: string; name: string; in_home: boolean } | null = null;
  @state() private cands: Candidates | null = null;
  @state() private listMode: boolean | null = null;
  @state() private failed = false;
  private chain: Promise<unknown> = Promise.resolve();
  private candFor = "";

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
      const boot = await this.hass.callWS<Bootstrap>({ type: "home_structure/get" });
      this.boot = boot;
      this.opts = boot.options;
      this.placeLegacy();
    } catch {
      this.failed = true;
    }
  }

  /** Spaces that already take part in the structure (set up with the older screens) but have no position yet get one, silently. */
  private placeLegacy(): void {
    const o = clone(this.opts);
    const used = new Set<string>(o.zones.map((z) => z.id));
    o.connections.forEach((c) => { used.add(c.a); used.add(c.b); });
    const missing = [...used].filter((id) => !o.layout[id]);
    if (!missing.length) return;
    for (const id of missing) o.layout[id] = nextFree(o.layout);
    this.opts = o;
    this.persist(o);
  }

  private persist(o: Options): void {
    this.status = "saving";
    this.chain = this.chain.then(async () => {
      try {
        const r = await this.hass.callWS<{ options: Options }>({ type: "home_structure/save", options: o });
        if (o === this.opts) this.opts = r.options;
        this.status = "saved";
        this.error = "";
      } catch (err) {
        this.status = "error";
        this.error = String((err as { message?: string })?.message ?? err);
        await this.load();
      }
    });
  }

  private commit(next: Options, select?: Selection | undefined): void {
    this.history = [...this.history.slice(-49), clone(this.opts)];
    this.opts = next;
    if (select !== undefined) this.selection = select;
    this.persist(next);
  }

  private undo(): void {
    const prev = this.history.at(-1);
    if (!prev) return;
    this.history = this.history.slice(0, -1);
    this.opts = prev;
    if (this.selection && !this.exists(this.selection)) this.selection = null;
    this.persist(prev);
  }

  private exists(sel: NonNullable<Selection>): boolean {
    return sel.kind === "link" ? this.opts.connections.some((c) => c.id === sel.id) : placedSpaces(this.boot!, this.opts).some((s) => s.id === sel.id);
  }

  private spaces(): Space[] {
    const list = placedSpaces(this.boot!, this.opts);
    return this.live ? list.map((s) => (s.id === this.live!.id ? { ...s, pos: this.live!.pos } : s)) : list;
  }

  // ------------------------------------------------------------------ operations
  private placeArea(areaId: string, at?: Pos): void {
    const o = clone(this.opts);
    o.layout[`area:${areaId}`] = at ?? nextFree(o.layout);
    this.commit(o);
  }

  private addAll(): void {
    const tray = trayAreas(this.boot!, this.opts);
    if (!tray.length) return;
    const o = clone(this.opts);
    const placed = Object.values(o.layout);
    const dx = placed.length ? Math.max(...placed.map((p) => p.x)) + BOX_W + 56 - 24 : 0;
    for (const [id, p] of Object.entries(autoLayout(tray, []))) o.layout[id] = { x: p.x + dx, y: p.y };
    this.commit(o);
  }

  private reorganize(): void {
    const o = clone(this.opts);
    const areas = this.boot!.areas.filter((a) => o.layout[`area:${a.id}`]);
    o.layout = autoLayout(areas, o.zones.filter((z) => z.id.startsWith("zone:")).map((z) => z.id));
    this.commit(o);
  }

  private removeFromPlan(id: string): void {
    const o = clone(this.opts);
    delete o.layout[id];
    o.zones = o.zones.filter((z) => z.id !== id);
    o.connections = o.connections.filter((c) => c.a !== id && c.b !== id);
    this.commit(o, null);
  }

  private createZone(): void {
    const f = this.zoneForm;
    if (!f || !f.name.trim()) return;
    const o = clone(this.opts);
    const taken = new Set(o.zones.map((z) => z.id));
    let id = `zone:${slug(f.name)}`, n = 1;
    while (taken.has(id)) id = `zone:${slug(f.name)}_${++n}`;
    o.zones.push({ id, kind: f.kind, in_home: f.in_home, name: f.name.trim() });
    o.layout[id] = nextFree(o.layout);
    this.zoneForm = null;
    this.commit(o, { kind: "space", id });
  }

  private setKind(s: Space, kind: string): void {
    const o = clone(this.opts);
    const isArea = s.id.startsWith("area:");
    if (isArea && kind === "room") {
      o.zones = o.zones.filter((z) => z.id !== s.id);
    } else {
      const inHome = this.boot!.in_home[kind] ?? false;
      const z = o.zones.find((x) => x.id === s.id);
      if (z) Object.assign(z, { kind, in_home: inHome });
      else o.zones.push({ id: s.id, kind, in_home: inHome });
    }
    this.commit(o);
  }

  private setInHome(s: Space, value: boolean): void {
    const o = clone(this.opts);
    const z = o.zones.find((x) => x.id === s.id);
    if (!z) return;
    z.in_home = value;
    this.commit(o);
  }

  private renameZone(s: Space, name: string): void {
    const clean = name.trim();
    if (!clean || clean === s.name) return;
    const o = clone(this.opts);
    const z = o.zones.find((x) => x.id === s.id);
    if (z) z.name = clean;
    this.commit(o);
  }

  private connect(a: string, b: string): void {
    if (a === b) return;
    const have = connOf(this.opts, a, b);
    if (have) { this.selection = { kind: "link", id: have.id }; return; }
    const o = clone(this.opts);
    const conn: Conn = { id: newId(), a, b, separations: [{ id: newId(), type: "door" }] };
    o.connections.push(conn);
    this.commit(o, { kind: "link", id: conn.id });
  }

  private editConn(id: string, fn: (c: Conn, o: Options) => void, select?: Selection): void {
    const o = clone(this.opts);
    const c = o.connections.find((x) => x.id === id);
    if (!c) return;
    fn(c, o);
    this.commit(o, select);
  }

  private setSepType(cid: string, sid: string, type: string): void {
    this.editConn(cid, (c) => {
      const s = c.separations.find((x) => x.id === sid);
      if (!s) return;
      s.type = type;
      if (this.boot!.permanent[type]) delete s.sensor;
      if (!this.boot!.shutter_hosts.includes(type)) delete s.shutter;
    });
  }

  private setSepShutter(cid: string, sid: string, cover: string): void {
    this.editConn(cid, (c) => {
      const s = c.separations.find((x) => x.id === sid);
      if (!s) return;
      if (cover) s.shutter = cover; else delete s.shutter;
    });
  }

  private setSepSensor(cid: string, sid: string, sensor: string): void {
    this.editConn(cid, (c) => {
      const s = c.separations.find((x) => x.id === sid);
      if (!s) return;
      if (sensor) s.sensor = sensor; else delete s.sensor;
    });
  }

  // ------------------------------------------------------------------ pointer handling on the plan
  private planPoint(e: PointerEvent | DragEvent): Pos {
    const r = this.shadowRoot!.querySelector(".plan")!.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  private boxDown(e: PointerEvent, s: Space): void {
    if ((e.target as HTMLElement).closest(".handle")) return;
    e.preventDefault();
    const start = this.planPoint(e);
    const grab = { x: start.x - s.pos.x, y: start.y - s.pos.y };
    let moved = false;
    const move = (ev: PointerEvent): void => {
      const p = this.planPoint(ev);
      if (!moved && Math.hypot(p.x - start.x, p.y - start.y) < MOVE_THRESHOLD) return;
      moved = true;
      this.live = { id: s.id, pos: { x: Math.max(0, Math.round(p.x - grab.x)), y: Math.max(0, Math.round(p.y - grab.y)) } };
    };
    const up = (): void => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      const pos = this.live?.pos;
      this.live = null;
      if (moved && pos) {
        const o = clone(this.opts);
        o.layout[s.id] = pos;
        this.commit(o, { kind: "space", id: s.id });
      } else {
        this.selection = { kind: "space", id: s.id };
      }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  private handleDown(e: PointerEvent, s: Space): void {
    e.preventDefault();
    e.stopPropagation();
    const p0 = this.planPoint(e);
    this.linking = { from: s.id, x: p0.x, y: p0.y };
    const move = (ev: PointerEvent): void => {
      const p = this.planPoint(ev);
      this.linking = { from: s.id, x: p.x, y: p.y };
    };
    const up = (ev: PointerEvent): void => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      const p = this.planPoint(ev);
      this.linking = null;
      const target = this.spaces().find((t) => t.id !== s.id && p.x >= t.pos.x && p.x <= t.pos.x + BOX_W && p.y >= t.pos.y && p.y <= t.pos.y + BOX_H);
      if (target) this.connect(s.id, target.id);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  private drop(e: DragEvent): void {
    e.preventDefault();
    const id = e.dataTransfer?.getData("text/plain");
    if (!id || !this.boot?.areas.some((a) => a.id === id)) return;
    const p = this.planPoint(e);
    this.placeArea(id, { x: Math.max(0, Math.round(p.x - BOX_W / 2)), y: Math.max(0, Math.round(p.y - BOX_H / 2)) });
  }

  // ------------------------------------------------------------------ rendering
  private kindLabel(kind: string): string {
    return this.t(`kind_${kind}` as Key);
  }

  private stateOf(sep: Sep): SepState {
    return sepState(sep, this.boot!, this.hass);
  }

  private floorLabel(a: Area): string {
    return a.floor ? `${this.t("floor")} ${a.floor}` : this.t("noFloor");
  }

  private chip(sep: Sep) {
    const st = this.stateOf(sep);
    const sh = shutterState(sep, this.hass);
    return html`<span class="chip ${st}" title=${this.t(`state_${st}` as Key)}><i></i>${this.t(`type_${sep.type}` as Key)}${sh ? html`<i class="sh ${sh}" title="${this.t("shutterShort")}: ${this.t(`state_${sh}` as Key)}"></i>${this.t("shutterShort")}` : nothing}</span>`;
  }

  private renderTray() {
    const tray = trayAreas(this.boot!, this.opts);
    return html`<section class="tray" aria-label=${this.t("trayTitle")}>
      <h2>${this.t("trayTitle")}</h2>
      <p class="muted">${this.t("trayHelp")}</p>
      ${tray.length ? html`<button class="plain" data-action="add-all" @click=${this.addAll}>${this.t("addAll")}</button>` : nothing}
      <ul>${tray.map((a) => html`<li draggable="true" data-area=${a.id} @dragstart=${(e: DragEvent) => e.dataTransfer?.setData("text/plain", a.id)} @click=${() => this.placeArea(a.id)}>
        <span>${a.name}</span><small>${this.floorLabel(a)}</small></li>`)}</ul>
      ${tray.length ? nothing : html`<p class="muted">${this.t("trayEmpty")}</p>`}
    </section>`;
  }

  private renderPlan() {
    const spaces = this.spaces();
    const byId = new Map(spaces.map((s) => [s.id, s]));
    const width = Math.max(720, ...spaces.map((s) => s.pos.x + BOX_W + 60));
    const height = Math.max(420, ...spaces.map((s) => s.pos.y + BOX_H + 60));
    const center = (s: Space): Pos => ({ x: s.pos.x + BOX_W / 2, y: s.pos.y + BOX_H / 2 });
    const links = this.opts.connections.filter((c) => byId.has(c.a) && byId.has(c.b));
    const from = this.linking ? byId.get(this.linking.from) : undefined;
    return html`<div class="planwrap"><div class="plan" style="width:${width}px;height:${height}px" @dragover=${(e: DragEvent) => e.preventDefault()} @drop=${this.drop}>
      <svg width=${width} height=${height}>
        ${links.map((c) => {
          const a = center(byId.get(c.a)!), b = center(byId.get(c.b)!);
          const sel = this.selection?.kind === "link" && this.selection.id === c.id;
          return svg`<line class="wire ${sel ? "sel" : ""}" x1=${a.x} y1=${a.y} x2=${b.x} y2=${b.y}></line>
            <line class="hit" data-link=${c.id} x1=${a.x} y1=${a.y} x2=${b.x} y2=${b.y} @click=${() => (this.selection = { kind: "link", id: c.id })}></line>`;
        })}
        ${from && this.linking ? svg`<line class="wire temp" x1=${center(from).x} y1=${center(from).y} x2=${this.linking.x} y2=${this.linking.y}></line>` : nothing}
      </svg>
      ${links.map((c) => {
        const a = center(byId.get(c.a)!), b = center(byId.get(c.b)!);
        const sel = this.selection?.kind === "link" && this.selection.id === c.id;
        return html`<div class="pill ${sel ? "sel" : ""}" data-pill=${c.id} style="left:${(a.x + b.x) / 2}px;top:${(a.y + b.y) / 2}px" @click=${() => (this.selection = { kind: "link", id: c.id })}>${c.separations.map((s) => this.chip(s))}</div>`;
      })}
      ${spaces.map((s) => html`<div class="box ${s.in_home ? "" : "outside"} ${this.selection?.kind === "space" && this.selection.id === s.id ? "sel" : ""} ${s.kind === "room" ? "" : "zone"}"
        data-space=${s.id} style="left:${s.pos.x}px;top:${s.pos.y}px;width:${BOX_W}px;height:${BOX_H}px" @pointerdown=${(e: PointerEvent) => this.boxDown(e, s)}>
        <strong>${s.name}</strong>${s.kind === "room" ? nothing : html`<small>${this.kindLabel(s.kind)}${s.in_home ? "" : " ↗"}</small>`}
        <span class="handle" title=${this.t("hint")} @pointerdown=${(e: PointerEvent) => this.handleDown(e, s)}>●</span></div>`)}
      ${spaces.length ? nothing : html`<p class="empty">${this.t("planEmpty")}</p>`}
    </div></div>`;
  }

  private renderList() {
    const spaces = this.spaces();
    return html`<ul class="spaces">${spaces.map((s) => {
      const n = this.opts.connections.filter((c) => c.a === s.id || c.b === s.id).length;
      return html`<li data-space=${s.id} class=${this.selection?.kind === "space" && this.selection.id === s.id ? "sel" : ""} @click=${() => (this.selection = { kind: "space", id: s.id })}>
        <strong>${s.name}</strong><small>${s.kind === "room" ? "" : this.kindLabel(s.kind)} · ${n}</small></li>`;
    })}${spaces.length ? nothing : html`<li class="muted">${this.t("planEmpty")}</li>`}</ul>`;
  }

  private select<V extends string>(value: string, options: { value: V; label: string }[], onChange: (v: string) => void, cls = "") {
    return html`<select class=${cls} .value=${value} @change=${(e: Event) => onChange((e.target as HTMLSelectElement).value)}>
      ${options.map((o) => html`<option value=${o.value} ?selected=${o.value === value}>${o.label}</option>`)}</select>`;
  }

  private async loadCandidates(c: Conn): Promise<void> {
    const key = `${c.id}:${c.a}:${c.b}`;
    if (this.candFor === key) return;
    this.candFor = key;
    const ids = [c.a, c.b].filter((x) => x.startsWith("area:")).map((x) => x.slice(5));
    try {
      this.cands = await this.hass.callWS<Candidates>({ type: "home_structure/candidates", area_ids: ids });
    } catch {
      this.cands = null;
    }
  }

  private renderLinkDrawer(c: Conn) {
    void this.loadCandidates(c);
    const names = new Map(this.spaces().map((s) => [s.id, s.name]));
    const typeOptions = this.boot!.types.map((v) => ({ value: v, label: this.t(`type_${v}` as Key) }));
    const sensors = this.cands?.sensors ?? [];
    return html`<aside class="drawer" data-drawer="link">
      <header><h2>${names.get(c.a)} ↔ ${names.get(c.b)}</h2><button class="x" @click=${() => (this.selection = null)} aria-label=${this.t("close")}>×</button></header>
      <h3>${this.t("separations")}</h3>
      ${c.separations.map((s) => {
        const permanent = !!this.boot!.permanent[s.type];
        const opts = [{ value: "", label: this.t("noSensor") }, ...sensors.map((x) => ({ value: x.entity_id, label: x.name }))];
        if (s.sensor && !sensors.some((x) => x.entity_id === s.sensor)) opts.push({ value: s.sensor, label: s.sensor });
        const covers = sensors.filter((x) => x.entity_id.startsWith("cover."));
        const shutterOpts = [{ value: "", label: this.t("noShutter") }, ...covers.map((x) => ({ value: x.entity_id, label: x.name }))];
        if (s.shutter && !covers.some((x) => x.entity_id === s.shutter)) shutterOpts.push({ value: s.shutter, label: s.shutter });
        return html`<div class="sep" data-sep=${s.id}>
          ${this.select(s.type, typeOptions, (v) => this.setSepType(c.id, s.id, v), "type")}
          ${permanent ? html`<small class="muted">${this.t("noSensorNeeded")}</small>`
            : html`${this.select(s.sensor ?? "", opts, (v) => this.setSepSensor(c.id, s.id, v), "sensor")}
              <small class="muted">${this.cands ? (this.cands.filtered ? this.t("sensorsHere") : this.t("sensorsAll")) : ""}</small>`}
          ${this.boot!.shutter_hosts.includes(s.type) ? html`${this.select(s.shutter ?? "", shutterOpts, (v) => this.setSepShutter(c.id, s.id, v), "shutter")}<small class="muted">${this.t("shutterHint")}</small>` : nothing}
          <div class="row">${this.chip(s)}${c.separations.length > 1 ? html`<button class="plain danger" data-action="remove-sep" @click=${() => this.editConn(c.id, (x) => { x.separations = x.separations.filter((y) => y.id !== s.id); })}>${this.t("removeSep")}</button>` : nothing}</div>
        </div>`;
      })}
      <button class="plain" data-action="add-sep" @click=${() => this.editConn(c.id, (x) => x.separations.push({ id: newId(), type: "door" }))}>${this.t("addSeparation")}</button>
      <button class="plain danger" data-action="remove-link" @click=${() => { const id = c.id; const o = clone(this.opts); o.connections = o.connections.filter((x) => x.id !== id); this.commit(o, null); }}>${this.t("removeLink")}</button>
    </aside>`;
  }

  private renderSpaceDrawer(s: Space) {
    const names = new Map(this.spaces().map((x) => [x.id, x.name]));
    const mine = this.opts.connections.filter((c) => c.a === s.id || c.b === s.id);
    const linked = new Set(mine.flatMap((c) => [c.a, c.b]));
    const others = this.spaces().filter((x) => !linked.has(x.id));
    const isArea = s.id.startsWith("area:");
    const kinds = [{ value: "room", label: this.kindLabel("room") }, ...this.boot!.kinds.map((k) => ({ value: k, label: this.kindLabel(k) }))]
      .filter((k) => isArea || k.value !== "room");
    return html`<aside class="drawer" data-drawer="space">
      <header><h2>${s.name}</h2><button class="x" @click=${() => (this.selection = null)} aria-label=${this.t("close")}>×</button></header>
      ${isArea ? html`<p class="muted">${s.area ? this.floorLabel(s.area) : ""}</p>`
        : html`<label>${this.t("zoneName")}<input class="name" .value=${s.name} @change=${(e: Event) => this.renameZone(s, (e.target as HTMLInputElement).value)}></label>`}
      <label>${this.t("zoneKind")}${this.select(s.kind, kinds, (v) => this.setKind(s, v), "kind")}</label>
      ${s.kind === "room" ? nothing : html`<label class="check"><input type="checkbox" class="inhome" .checked=${s.in_home} @change=${(e: Event) => this.setInHome(s, (e.target as HTMLInputElement).checked)}>${this.t("partOfHome")}</label>`}
      <h3>${this.t("connections")}</h3>
      ${mine.length ? html`<ul class="neigh">${mine.map((c) => html`<li data-neighbour=${c.id} @click=${() => (this.selection = { kind: "link", id: c.id })}>
        <span>${names.get(c.a === s.id ? c.b : c.a)}</span>${c.separations.map((x) => this.chip(x))}</li>`)}</ul>` : html`<p class="muted">${this.t("noConnections")}</p>`}
      ${others.length ? this.select("", [{ value: "", label: this.t("connectTo") }, ...others.map((o) => ({ value: o.id, label: o.name }))], (v) => v && this.connect(s.id, v), "connect") : nothing}
      <button class="plain danger" data-action=${isArea ? "to-tray" : "delete-zone"} @click=${() => this.removeFromPlan(s.id)}>${this.t(isArea ? "removeFromPlan" : "deleteZone")}</button>
    </aside>`;
  }

  private renderDrawer() {
    const sel = this.selection;
    if (!sel) return html`<aside class="drawer idle"><p class="muted">${this.t("hint")}</p></aside>`;
    if (sel.kind === "link") {
      const c = this.opts.connections.find((x) => x.id === sel.id);
      return c ? this.renderLinkDrawer(c) : nothing;
    }
    const s = this.spaces().find((x) => x.id === sel.id);
    return s ? this.renderSpaceDrawer(s) : nothing;
  }

  private renderZoneForm() {
    const f = this.zoneForm;
    if (!f) return nothing;
    const kinds = this.boot!.kinds.map((k) => ({ value: k, label: this.kindLabel(k) }));
    return html`<div class="zoneform" role="dialog">
      <label>${this.t("zoneKind")}${this.select(f.kind, kinds, (v) => (this.zoneForm = { ...f, kind: v, in_home: this.boot!.in_home[v] ?? false, name: f.name === this.kindLabel(f.kind) ? this.kindLabel(v) : f.name }), "zkind")}</label>
      <label>${this.t("zoneName")}<input class="zname" .value=${f.name} @input=${(e: Event) => (this.zoneForm = { ...f, name: (e.target as HTMLInputElement).value })}></label>
      <label class="check"><input type="checkbox" class="zhome" .checked=${f.in_home} @change=${(e: Event) => (this.zoneForm = { ...f, in_home: (e.target as HTMLInputElement).checked })}>${this.t("partOfHome")}</label>
      <div class="row"><button class="primary" data-action="create-zone" @click=${this.createZone}>${this.t("create")}</button><button class="plain" @click=${() => (this.zoneForm = null)}>${this.t("cancel")}</button></div>
    </div>`;
  }

  private statusText(): string {
    return this.status === "saving" ? this.t("saving") : this.status === "saved" ? `✓ ${this.t("saved")}` : this.status === "error" ? this.t("saveFailed", { error: this.error }) : "";
  }

  render() {
    const t = this.t;
    if (this.failed) return html`<p class="msg">${t("notLoaded")}</p>`;
    if (!this.boot) return html`<p class="msg">${t("loading")}</p>`;
    const list = this.listMode ?? this.narrow;
    return html`
      <div class="bar">
        ${this.narrow ? html`<button class="menu" @click=${() => this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }))} aria-label="Menu">☰</button>` : nothing}
        <h1>${t("title")}</h1>
        <span class="status ${this.status}" role="status" data-status=${this.status}>${this.statusText()}</span>
        <span class="grow"></span>
        <button class="barbtn" data-action="undo" ?disabled=${!this.history.length} @click=${this.undo}>↶ ${t("undo")}</button>
        <button class="barbtn" data-action="reorganize" @click=${this.reorganize}>${t("reorganize")}</button>
        <button class="barbtn" data-action="add-zone" @click=${() => (this.zoneForm = { kind: "garden", name: this.kindLabel("garden"), in_home: this.boot!.in_home.garden ?? true })}>${t("addZone")}</button>
        <button class="barbtn" data-action="toggle-view" @click=${() => (this.listMode = !list)}>${list ? t("plan") : t("list")}</button>
      </div>
      ${this.renderZoneForm()}
      <div class="cols ${list ? "list" : ""}">
        ${this.renderTray()}
        <main>${list ? this.renderList() : this.renderPlan()}</main>
        ${this.renderDrawer()}
      </div>`;
  }

  static styles = css`
    :host { display: block; min-height: 100%; background: var(--primary-background-color); color: var(--primary-text-color); font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
    .bar { display: flex; align-items: center; gap: 8px; min-height: 56px; padding: 0 16px; flex-wrap: wrap; background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, var(--text-primary-color, #fff)); position: sticky; top: 0; z-index: 3; }
    h1 { font-size: 1.25rem; font-weight: 400; margin: 0; }
    .menu { background: none; border: 0; color: inherit; font-size: 1.4rem; cursor: pointer; padding: 8px; }
    .grow { flex: 1; }
    .status { font-size: .85rem; opacity: .9; margin-left: 8px; } .status.error { font-weight: 600; }
    .barbtn { font: inherit; color: inherit; background: rgba(255,255,255,.14); border: 1px solid rgba(255,255,255,.35); border-radius: 6px; padding: 5px 12px; cursor: pointer; }
    .barbtn:disabled { opacity: .45; cursor: default; }
    .msg { padding: 24px; }
    .cols { display: grid; grid-template-columns: 240px minmax(0, 1fr) 320px; gap: 12px; padding: 12px; align-items: start; }
    .cols.list { grid-template-columns: 1fr; }
    @media (max-width: 900px) { .cols { grid-template-columns: 1fr; } }
    h2 { font-size: 1rem; margin: 0 0 6px; } h3 { font-size: .85rem; margin: 14px 0 6px; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .04em; }
    .muted { color: var(--secondary-text-color); font-size: .85rem; margin: 4px 0 8px; }
    .tray, .drawer { background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: 10px; padding: 12px; box-sizing: border-box; }
    .tray ul, .spaces, .neigh { list-style: none; margin: 8px 0 0; padding: 0; }
    .tray li { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; padding: 7px 8px; border: 1px solid var(--divider-color); border-radius: 8px; margin-bottom: 6px; cursor: grab; background: var(--secondary-background-color); }
    .tray li small, .spaces small { color: var(--secondary-text-color); }
    .tray li:hover { border-color: var(--primary-color); }
    .planwrap { overflow: auto; background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: 10px; max-height: calc(100vh - 150px); }
    .plan { position: relative; touch-action: none; background-image: radial-gradient(var(--divider-color) 1px, transparent 1px); background-size: 24px 24px; }
    svg { position: absolute; inset: 0; pointer-events: none; }
    .wire { stroke: var(--secondary-text-color); stroke-width: 2; opacity: .55; } .wire.sel { stroke: var(--primary-color); stroke-width: 4; opacity: 1; } .wire.temp { stroke: var(--primary-color); stroke-dasharray: 6 4; opacity: 1; }
    .hit { stroke: transparent; stroke-width: 16; pointer-events: stroke; cursor: pointer; }
    .box { position: absolute; box-sizing: border-box; padding: 8px 26px 8px 10px; background: var(--card-background-color); border: 2px solid var(--primary-color); border-radius: 10px; cursor: grab; user-select: none; display: flex; flex-direction: column; justify-content: center; overflow: hidden; z-index: 2; }
    .box strong { font-size: .9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; } .box small { font-size: .72rem; color: var(--secondary-text-color); }
    .box.zone { background: var(--secondary-background-color); } .box.outside { border-style: dashed; border-color: var(--secondary-text-color); }
    .box.sel { box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary-color) 35%, transparent); }
    .handle { position: absolute; right: 4px; top: 50%; transform: translateY(-50%); width: 20px; height: 20px; line-height: 20px; text-align: center; color: var(--primary-color); cursor: crosshair; font-size: 1rem; }
    .pill { position: absolute; transform: translate(-50%, -50%); display: flex; gap: 4px; flex-wrap: wrap; justify-content: center; max-width: 150px; z-index: 4; cursor: pointer; padding: 2px; border-radius: 12px; }
    .pill.sel .chip { outline: 2px solid var(--primary-color); }
    .chip { display: inline-flex; align-items: center; gap: 5px; font-size: .72rem; padding: 2px 8px; border-radius: 999px; background: var(--card-background-color); border: 1px solid var(--divider-color); color: var(--primary-text-color); white-space: nowrap; }
    .chip i { width: 8px; height: 8px; border-radius: 50%; background: var(--disabled-color, #9e9e9e); display: inline-block; }
    .chip.open i { background: var(--success-color, #43a047); } .chip.closed i { background: var(--error-color, #db4437); } .chip.partial i { background: var(--warning-color, #ffa600); }
    .chip i.sh { border-radius: 2px; margin-left: 2px; width: 7px; height: 7px; } .chip i.sh.open { background: var(--success-color, #43a047); } .chip i.sh.closed { background: var(--error-color, #db4437); } .chip i.sh.partial { background: var(--warning-color, #ffa600); }
    .chip.unknown { border-style: dashed; }
    .empty { position: absolute; left: 24px; top: 24px; color: var(--secondary-text-color); }
    .spaces li { padding: 10px 12px; border: 1px solid var(--divider-color); border-radius: 8px; margin-bottom: 6px; display: flex; justify-content: space-between; background: var(--card-background-color); cursor: pointer; } .spaces li.sel { border-color: var(--primary-color); }
    .drawer header { display: flex; justify-content: space-between; align-items: start; gap: 8px; } .drawer.idle { color: var(--secondary-text-color); }
    .x { background: none; border: 0; color: var(--secondary-text-color); font-size: 1.4rem; cursor: pointer; line-height: 1; }
    label { display: block; font-size: .8rem; color: var(--secondary-text-color); margin: 8px 0; } label.check { display: flex; gap: 8px; align-items: center; color: var(--primary-text-color); font-size: .9rem; }
    select, input.name, input.zname { width: 100%; box-sizing: border-box; margin-top: 4px; font: inherit; padding: 7px 8px; border-radius: 6px; border: 1px solid var(--divider-color); background: var(--secondary-background-color); color: var(--primary-text-color); }
    .sep { padding: 8px 0; border-bottom: 1px solid var(--divider-color); display: grid; gap: 6px; } .row { display: flex; gap: 8px; align-items: center; justify-content: space-between; }
    .plain { font: inherit; background: none; border: 1px solid var(--divider-color); color: var(--primary-text-color); border-radius: 6px; padding: 6px 10px; cursor: pointer; margin-top: 8px; width: 100%; }
    .plain.danger { color: var(--error-color, #db4437); } .primary { font: inherit; background: var(--primary-color); color: var(--text-primary-color, #fff); border: 0; border-radius: 6px; padding: 7px 14px; cursor: pointer; }
    .neigh li { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; padding: 6px 0; border-bottom: 1px solid var(--divider-color); cursor: pointer; } .neigh li span { font-size: .9rem; margin-right: 4px; }
    .zoneform { position: fixed; top: 64px; right: 16px; z-index: 5; width: 280px; background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: 10px; padding: 14px; box-shadow: 0 6px 24px rgba(0,0,0,.35); }
  `;
}
customElements.define("home-structure-panel", HomeStructurePanel);
