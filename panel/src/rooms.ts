import { LitElement, css, html, nothing } from "lit";
import type { TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import { live } from "lit/directives/live.js";
import { translator } from "./i18n";
import type { Key, T } from "./i18n";
import type { HistoryEntry, Hass, MovePreview, Refs, RoomSensor, RoomsView, User } from "./types";

const ERRORS = ["nothing_to_change", "assistant_unavailable", "unknown_entity", "unknown_area", "no_device", "changed_since", "already_undone", "unknown_entry", "invalid_order", "unauthorized", "native_rejected"];
type Lock = "assist" | "move" | "order";
type Assistant = "conversation" | "alexa" | "google";
type Dialog =
  | { kind: "exposure"; sensor: RoomSensor; assistant: Assistant; value: boolean }
  | { kind: "move"; sensor: RoomSensor; area: string; scope: "entity" | "device"; preview: MovePreview | null }
  | { kind: "undo"; entry: HistoryEntry };

/** The "Rooms" page of the panel: the sensors of each room by type, what they are exposed to, their priority, and (behind padlocks) the changes. */
class HomeStructureRooms extends LitElement {
  @property({ attribute: false }) hass!: Hass;
  @state() private data: RoomsView | null = null;
  @property() area = "";      // the room this page shows
  @state() private users: User[] = [];
  @state() private failed = false;
  @state() private locks: Record<Lock, boolean> = { assist: true, move: true, order: true };      // every section is locked at each opening
  @state() private dialog: Dialog | null = null;
  @state() private busy = false;
  @state() private error = "";
  @state() private history: HistoryEntry[] = [];
  @state() private historyOpen = false;
  @state() private showSounds = false;      // sound detections and the sensors that do not describe a room are hidden at each opening
  @state() private showOther = false;
  private drag: { area: string; key: string; entity: string } | null = null;
  private t: T = translator("en");

  protected willUpdate(): void {
    if (this.hass) this.t = translator(this.hass.language);
  }

  connectedCallback(): void {
    super.connectedCallback();
    void this.load(true);
  }

  private async load(withUsers = false): Promise<void> {
    try {
      const jobs: [Promise<RoomsView>, Promise<{ users: User[] }> | null] = [
        this.hass.callWS<RoomsView>({ type: "home_structure/room_sensors" }),
        withUsers ? this.hass.callWS<{ users: User[] }>({ type: "home_structure/get" }) : null];
      this.data = await jobs[0];
      if (jobs[1]) this.users = (await jobs[1]).users ?? [];
      if (this.historyOpen) await this.loadHistory();
    } catch {
      this.failed = true;
    }
  }

  private async loadHistory(): Promise<void> {
    try {
      this.history = (await this.hass.callWS<{ entries: HistoryEntry[] }>({ type: "home_structure/history" })).entries;
    } catch {
      this.history = [];
    }
  }

  /** Runs one write, then reads everything again so that the page shows what Home Assistant now says. Errors stay in the dialog. */
  private async write(msg: Record<string, unknown>): Promise<boolean> {
    this.busy = true;
    this.error = "";
    try {
      await this.hass.callWS(msg);
      await this.load();
      return true;
    } catch (e) {
      const code = (e as { code?: string }).code ?? "";
      const detail = (e as { message?: string }).message ?? String(e);
      this.error = code === "native_rejected" ? this.t("err_native_rejected", { error: detail }) : ERRORS.includes(code) ? this.t(`err_${code}` as Key) : this.t("err_generic", { error: detail });
      return false;
    } finally {
      this.busy = false;
    }
  }

  private roomName(id: string | null): string {
    return (id && this.data?.rooms.find((r) => r.area_id === id)?.name) || id || this.t("noRoom");
  }

  /** The name of a device class: Home Assistant's own translation when the page can reach it, else the class made readable. */
  private typeName(domain: string, cls: string): string {
    if (cls === "other") return this.t("typeOther");
    const loc = (this.hass as unknown as { localize?: (k: string) => string }).localize;
    const own = loc?.(`component.${domain}.entity_component.${cls}.name`);
    return own || cls.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
  }

  // ---- order

  private async saveOrder(area: string, key: string, ids: string[]): Promise<void> {
    if (this.locks.order) return;
    await this.write({ type: "home_structure/save_order", area_id: area, key, entity_ids: ids });
  }

  private nudge(area: string, key: string, ids: string[], i: number, by: -1 | 1): void {
    const next = [...ids];
    const j = i + by;
    if (j < 0 || j >= next.length) return;
    [next[i], next[j]] = [next[j], next[i]];
    void this.saveOrder(area, key, next);
  }

  private dropOn(area: string, key: string, ids: string[], target: string): void {
    const d = this.drag;
    this.drag = null;
    if (!d || d.area !== area || d.key !== key || d.entity === target) return;
    const to = ids.indexOf(target);          // the sensor takes the place of the one it is dropped on
    const next = ids.filter((x) => x !== d.entity);
    next.splice(to, 0, d.entity);
    void this.saveOrder(area, key, next);
  }

  // ---- exposure and moves

  private askExposure(sensor: RoomSensor, assistant: Assistant, value: boolean): void {
    this.error = "";
    this.dialog = { kind: "exposure", sensor, assistant, value };
  }

  private async askMove(sensor: RoomSensor): Promise<void> {
    this.error = "";
    const first = this.data!.rooms.find((r) => r.area_id !== sensor.area_id)?.area_id ?? "";
    this.dialog = { kind: "move", sensor, area: first, scope: "entity", preview: null };
    if (first) await this.preview();
  }

  private async preview(): Promise<void> {
    const d = this.dialog;
    if (!d || d.kind !== "move" || !d.area) return;
    try {
      const preview = await this.hass.callWS<MovePreview>({ type: "home_structure/move_preview", entity_id: d.sensor.entity_id, area_id: d.area });
      if (this.dialog === d) this.dialog = { ...d, preview };
    } catch (e) {
      this.error = this.t("err_generic", { error: (e as { message?: string }).message ?? String(e) });
    }
  }

  private async confirm(): Promise<void> {
    const d = this.dialog;
    if (!d || this.busy) return;
    const ok = d.kind === "exposure" ? await this.write({ type: "home_structure/exposure_set", entity_id: d.sensor.entity_id, changes: { [d.assistant]: d.value } })
      : d.kind === "move" ? await this.write({ type: "home_structure/move_apply", entity_id: d.sensor.entity_id, area_id: d.area, scope: d.scope })
      : await this.write({ type: "home_structure/undo", entry_id: d.entry.id });
    if (ok) this.dialog = null;
  }

  private cancel(): void {
    this.dialog = null;
    this.error = "";
    this.data = this.data ? { ...this.data } : this.data;      // the boxes show Home Assistant's state again
  }

  // ---- rendering

  private badges(s: RoomSensor) {
    const t = this.t;
    const off = this.locks.assist;
    const box = (cls: string, label: string, on: boolean, who: Assistant, title: string) =>
      html`<label class="assist" title=${title}><input type="checkbox" class=${cls} data-assistant=${who} ?disabled=${off} .checked=${live(on)} @change=${(e: Event) => this.askExposure(s, who, (e.target as HTMLInputElement).checked)}>${label}</label>`;
    return html`<span class="badges">
      ${box("assist-box", t("assist"), s.assist, "conversation", t("assistHelp"))}
      ${this.data!.assistants.alexa ? box("alexa-box", "Alexa", s.alexa, "alexa", t("alexaHelp")) : nothing}
      ${this.data!.assistants.google ? box("google-box", "Google", s.google, "google", t("googleHelp")) : nothing}
      ${s.homekit.length ? html`<span class="chip homekit" data-badge="homekit" title=${s.homekit.join(", ")}>HomeKit</span>` : nothing}
      ${s.matter.length ? html`<span class="chip matter" data-badge="matter" title=${s.matter.join(", ")}>Matter</span>` : nothing}
      ${this.locks.move ? nothing : html`<button class="small" data-action="move" @click=${() => void this.askMove(s)}>${t("moveButton")}</button>`}
    </span>`;
  }

  private sensor(s: RoomSensor, g: { key: string; ordered: boolean; sensors: RoomSensor[] } | null, i: number, area: string) {
    const ids = g?.sensors.map((x) => x.entity_id) ?? [];
    const arrows = g?.ordered && !this.locks.order;
    return html`<li data-entity=${s.entity_id} draggable=${arrows ? "true" : "false"}
        @dragstart=${() => (this.drag = { area, key: g!.key, entity: s.entity_id })} @dragover=${(e: Event) => { if (arrows) e.preventDefault(); }} @drop=${(e: Event) => { e.preventDefault(); if (g) this.dropOn(area, g.key, ids, s.entity_id); }}>
      ${g?.ordered ? html`<span class="rank" aria-label=${this.t("priority", { n: i + 1 })}>${i + 1}</span>` : nothing}
      ${arrows ? html`<span class="arrows"><button class="small up" data-action="up" ?disabled=${i === 0} aria-label=${this.t("moveUp")} @click=${() => this.nudge(area, g!.key, ids, i, -1)}>▲</button><button class="small down" data-action="down" ?disabled=${i === ids.length - 1} aria-label=${this.t("moveDown")} @click=${() => this.nudge(area, g!.key, ids, i, 1)}>▼</button></span>` : nothing}
      <span class="name"><strong>${s.name}</strong><small>${s.entity_id}${s.device_name ? ` · ${s.device_name}` : ""}</small></span>
      <span class="value">${s.state}${s.unit ? ` ${s.unit}` : ""}</span>
      ${this.badges(s)}
    </li>`;
  }

  /** Is the sensor listed? Hidden ones come back with their filter; while the order is unlocked every sensor of a type is listed (the order covers them all). */
  private listed(s: RoomSensor): boolean {
    return !s.hidden || (s.hidden === "sound" ? this.showSounds : this.showOther) || !this.locks.order;
  }

  private hiddenIn(sensors: RoomSensor[]): number {
    return sensors.filter((s) => s.hidden && !(s.hidden === "sound" ? this.showSounds : this.showOther)).length;
  }

  private async choose(area: string, key: string, entity: string): Promise<void> {
    if (this.locks.order) return;
    await this.write({ type: "home_structure/primary_set", area_id: area, key, entity_id: entity || null });
  }

  private async setSync(value: boolean): Promise<void> {
    if (this.locks.order) return;
    await this.write({ type: "home_structure/primary_sync", value });
  }

  private chooser(area: string, g: RoomsView["rooms"][number]["types"][number]) {
    if (g.sensors.every((s) => s.hidden)) return nothing;      // only the categories that describe a room have a chosen sensor
    const t = this.t, picked = g.primary_source === "chosen" || g.primary_source === "native" ? g.primary ?? "" : "";
    const why = g.primary_source === "native" ? t("chosenFromHa") : g.primary_source === "assist" ? t("chosenFromAssist") : "";
    const def = g.primary_source === "assist" ? g.sensors.find((s) => s.entity_id === g.primary)?.name : undefined;
    return html`<label class="chooser">${t("chosenSensor")}
      <select data-action="choose" data-key=${g.key} ?disabled=${this.locks.order || this.busy} .value=${live(picked)} @change=${(e: Event) => void this.choose(area, g.key, (e.target as HTMLSelectElement).value)}>
        <option value="" ?selected=${picked === ""}>${t("chosenDefault")}${def ? ` (${def})` : ""}</option>
        ${g.sensors.map((s) => html`<option value=${s.entity_id} ?selected=${s.entity_id === picked}>${s.name}</option>`)}
      </select>${why ? html`<span class="muted why">${why}</span>` : nothing}</label>`;
  }

  private roomBody(r: RoomsView["rooms"][number]) {
    const t = this.t;
    return html`<div class="body" data-room=${r.area_id}>
      ${r.types.some((g) => g.sensors.some((s) => this.listed(s))) ? r.types.filter((g) => g.sensors.some((s) => this.listed(s))).map((g) => html`<div class="type" data-type=${g.type}>
          <h3>${this.typeName(g.domain, g.type)}${g.saved && !this.locks.order ? html` <button class="link" data-action="reset-order" @click=${() => void this.saveOrder(r.area_id, g.key, [])}>${t("autoOrder")}</button>` : nothing}</h3>
          ${this.chooser(r.area_id, g)}
          <ul>${g.sensors.map((s, i) => (this.listed(s) ? this.sensor(s, g, i, r.area_id) : nothing))}</ul>
          ${g.assist_first === false ? html`<p class="muted note" data-note="not-first">ⓘ ${t("notFirst")}</p>` : nothing}
        </div>`) : html`<p class="muted">${t("noSensorsInRoom")}</p>`}
    </div>`;
  }

  /** The page of one room: its name and usual occupants, then its sensors by type. */
  private renderPage(r: RoomsView["rooms"][number] | undefined) {
    const t = this.t;
    const hidden = r ? this.hiddenIn(r.types.flatMap((g) => g.sensors)) : 0;
    const names = r ? r.occupants.map((id) => this.users.find((u) => u.id === id)?.name).filter(Boolean).join(", ") : "";
    return html`<div class="pagehead"><button class="back" data-action="back" aria-label=${t("backToRooms")} @click=${() => this.dispatchEvent(new CustomEvent("back", { bubbles: true, composed: true }))}>←</button>
      <h1>${r?.name ?? ""}</h1>${names ? html`<span class="muted occupants">${t("occupantsLabel")} ${names}</span>` : nothing}${hidden ? html`<span class="muted count">${t("hiddenCount", { n: hidden })}</span>` : nothing}</div>
    ${r ? html`<section class="room open" data-room-row=${r.area_id}>${this.roomBody(r)}</section>` : html`<p class="muted" data-notonplan>${t("notOnPlan")}</p>`}`;
  }

  private lockBar() {
    const t = this.t;
    const btn = (k: Lock, label: string) => html`<button class="lock ${this.locks[k] ? "on" : ""}" data-lock=${k} aria-pressed=${this.locks[k]} title=${this.locks[k] ? t("unlockSection") : t("lockSection")} @click=${() => (this.locks = { ...this.locks, [k]: !this.locks[k] })}>${this.locks[k] ? "🔒" : "🔓"} ${label}</button>`;
    return html`<div class="locks" role="group" aria-label=${t("locksLabel")}>${btn("assist", t("lockAssist"))}${btn("move", t("lockMove"))}${btn("order", t("lockOrder"))}</div>`;
  }

  private refs(r: Refs | null) {
    if (!r) return nothing;
    const t = this.t;
    const rows = (label: Key, items: Refs["automation"]) => items.length ? html`<li><strong>${t(label)}</strong>: ${items.map((i) => i.name).join(", ")}</li>` : nothing;
    const any = r.automation.length || r.script.length || r.scene.length;
    return any ? html`<div class="refs" data-refs><p class="warn">⚠ ${t("refsFound")}</p><ul>${rows("refAutomations", r.automation)}${rows("refScripts", r.script)}${rows("refScenes", r.scene)}</ul></div>` : nothing;
  }

  private describe(e: HistoryEntry): string {
    const t = this.t;
    if (e.kind === "exposure") {
      const [who, val] = Object.entries(e.after)[0] ?? ["conversation", false];
      return t(val ? "hExposeOn" : "hExposeOff", { entity: e.entity_id, who: who === "conversation" ? "Assist" : who === "alexa" ? "Alexa" : "Google" });
    }
    if (e.kind === "primary") {
      const [domain, ...cls] = (e.key ?? "").split(".");
      const type = this.typeName(domain, cls.join("."));
      const chosen = (e.after as { chosen?: string | null }).chosen;
      return chosen ? t("hPrimaryOn", { entity: chosen, type, room: this.roomName(e.area_id ?? null) }) : t("hPrimaryOff", { type, room: this.roomName(e.area_id ?? null) });
    }
    return t(e.scope === "device" ? "hMoveDevice" : "hMoveEntity", { entity: e.entity_id, room: this.roomName(e.area_id ?? null) });
  }

  private renderDialog() {
    const d = this.dialog;
    if (!d) return nothing;
    const t = this.t;
    let body: TemplateResult;
    let can = true;
    if (d.kind === "exposure") {
      const who = d.assistant === "conversation" ? "Assist" : d.assistant === "alexa" ? "Alexa" : "Google";
      body = html`<h2>${t("confirmTitle")}</h2><p>${t(d.value ? "confirmExposeOn" : "confirmExposeOff", { name: d.sensor.name, who })}</p>`;
    } else if (d.kind === "undo") {
      body = html`<h2>${t("undoTitle")}</h2><p>${this.describe(d.entry)}</p><p class="muted">${t("undoHelp")}</p>`;
    } else {
      const p = d.preview;
      const shared = p?.device && p.device.others.length > 0;
      can = !!d.area && !!p;
      body = html`<h2>${t("moveTitle", { name: d.sensor.name })}</h2>
        <p class="muted">${t("moveFrom")} ${this.roomName(d.sensor.area_id)}</p>
        <label>${t("moveToRoom")} <select class="move-room" @change=${(e: Event) => { this.dialog = { ...d, area: (e.target as HTMLSelectElement).value, preview: null }; void this.preview(); }}>
          ${this.data!.rooms.filter((r) => r.area_id !== d.sensor.area_id).map((r) => html`<option value=${r.area_id} ?selected=${r.area_id === d.area}>${r.name}</option>`)}</select></label>
        ${shared ? html`<fieldset class="scope" data-scope><legend>${t("scopeTitle", { device: p!.device!.name, n: p!.device!.others.length })}</legend>
          <label><input type="radio" name="scope" value="entity" ?checked=${d.scope === "entity"} @change=${() => (this.dialog = { ...d, scope: "entity" })}>${t("scopeEntity")}</label>
          <label><input type="radio" name="scope" value="device" ?checked=${d.scope === "device"} @change=${() => (this.dialog = { ...d, scope: "device" })}>${t("scopeDevice")}</label>
          <p class="muted">${d.scope === "device" ? t("scopeDeviceHelp", { others: p!.device!.others.map((o) => o.name).join(", ") }) : t("scopeEntityHelp")}</p></fieldset>` : nothing}
        ${p ? this.refs(d.scope === "device" && p.device_refs ? p.device_refs : p.sensor) : html`<p class="muted">${t("loading")}</p>`}
        <p class="muted">${t("moveTemplates")} ${t("moveOthers")}</p>`;
    }
    return html`<div class="scrim" data-dialog><div class="dialog" role="dialog" aria-modal="true">${body}
      ${this.error ? html`<p class="warn" data-error role="alert">${this.error}</p>` : nothing}
      <div class="actions"><button data-action="cancel" @click=${() => this.cancel()}>${t("cancel")}</button>
        <button class="primary" data-action="confirm" ?disabled=${this.busy || !can} @click=${() => void this.confirm()}>${t("confirm")}</button></div></div></div>`;
  }

  private renderHistory() {
    const t = this.t;
    return html`<details class="history" data-history ?open=${this.historyOpen} @toggle=${(e: Event) => { this.historyOpen = (e.target as HTMLDetailsElement).open; if (this.historyOpen) void this.loadHistory(); }}>
      <summary>${t("historyTitle")}</summary>
      ${this.history.length ? html`<ul>${this.history.map((e) => html`<li data-entry=${e.id}><span class="name"><strong>${this.describe(e)}</strong><small>${e.time.slice(0, 16).replace("T", " ")}${e.undone ? ` · ${t("undone")}` : ""}</small></span>
        <button class="small" data-action="undo-entry" ?disabled=${e.undone || this.locks[e.kind === "exposure" ? "assist" : "move"]} @click=${() => { this.error = ""; this.dialog = { kind: "undo", entry: e }; }}>${t("undoButton")}</button></li>`)}</ul>` : html`<p class="muted">${t("historyEmpty")}</p>`}
    </details>`;
  }

  protected render() {
    const t = this.t;
    if (this.failed) return html`<p class="msg">${t("notLoaded")}</p>`;
    if (!this.data) return html`<p class="msg">${t("loading")}</p>`;
    const d = this.data;
    return html`<p class="muted intro">${t("roomsHelp")}${d.matter.available ? nothing : html` ${t("matterUnavailable")}`}</p>
      ${this.lockBar()}
      <div class="filters" data-filters>
        <label><input type="checkbox" data-filter="sounds" .checked=${live(this.showSounds)} @change=${(e: Event) => (this.showSounds = (e.target as HTMLInputElement).checked)}>${t("filterSounds")}</label>
        <label><input type="checkbox" data-filter="other" .checked=${live(this.showOther)} @change=${(e: Event) => (this.showOther = (e.target as HTMLInputElement).checked)}>${t("filterOther")}</label>
        <label title=${t("primarySync")}><input type="checkbox" data-action="primary-sync" ?disabled=${this.locks.order || this.busy} .checked=${live(d.primary_sync !== false)} @change=${(e: Event) => void this.setSync((e.target as HTMLInputElement).checked)}>${t("primarySync")}</label>
      </div>
      ${this.locks.order ? nothing : html`<p class="muted note" data-note="order-shows-all">${t("orderShowsAll")}</p>`}
      ${this.renderPage(d.rooms.find((r) => r.area_id === this.area))}
      ${d.unassigned.some((s) => this.listed(s)) ? html`<details class="unassigned" data-unassigned>
        <summary>${t("unassignedTitle")} (${d.unassigned.filter((s) => this.listed(s)).length})</summary>
        <p class="muted">${t("unassignedHelp")}</p>
        <ul>${d.unassigned.filter((s) => this.listed(s)).map((s) => html`<li data-entity=${s.entity_id}>
          <span class="name"><strong>${s.name}</strong><small>${s.entity_id} · ${this.typeName(s.domain, s.type)}</small></span>
          <span class="value">${s.state}${s.unit ? ` ${s.unit}` : ""}</span>${this.badges(s)}</li>`)}</ul>
      </details>` : nothing}
      ${this.renderHistory()}
      ${this.renderDialog()}`;
  }

  static styles = css`
    :host { display: block; padding: 8px 16px 48px; box-sizing: border-box; color: var(--primary-text-color); }
    .pagehead { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin: 0 0 12px; } .pagehead h1 { font-size: 1.4rem; font-weight: 400; margin: 0; }
    .back { font: inherit; font-size: 1.4rem; line-height: 1; background: none; border: 0; color: inherit; cursor: pointer; padding: 6px 12px; border-radius: 50%; } .back:hover { background: var(--secondary-background-color); }
    .msg, .intro { padding: 12px 8px; } .muted { color: var(--secondary-text-color); font-size: .85rem; } .warn { color: var(--error-color, #db4437); font-size: .9rem; }
    .locks { display: flex; gap: 8px; flex-wrap: wrap; margin: 0 0 12px; }
    .lock { font: inherit; font-size: .85rem; color: inherit; background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: 16px; padding: 4px 12px; cursor: pointer; }
    .lock.on { background: var(--secondary-background-color); } .lock:not(.on) { border-color: var(--primary-color); }
    .room, details { background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: 12px; padding: 4px 16px 12px; margin: 0 0 16px; }
    .room { padding-bottom: 4px; margin-bottom: 8px; } .room.open { padding-bottom: 12px; }
    .roomhead { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; width: 100%; font: inherit; color: inherit; background: none; border: 0; text-align: left; cursor: pointer; padding: 0; }
    .roomhead h2 { font-size: 1.1rem; font-weight: 500; margin: 12px 0 8px; } .chev { width: 1em; color: var(--secondary-text-color); } .count { margin-left: auto; }
    h3.floortitle { margin: 16px 4px 6px; }
    h3 { font-size: .8rem; font-weight: 500; text-transform: uppercase; letter-spacing: .04em; color: var(--secondary-text-color); margin: 12px 0 2px; }
    ul { list-style: none; margin: 0; padding: 0; }
    li { display: flex; align-items: center; gap: 12px; padding: 6px 0; border-top: 1px solid var(--divider-color); flex-wrap: wrap; } li:first-child { border-top: 0; } li[draggable=true] { cursor: grab; }
    .name { flex: 1 1 220px; min-width: 0; } .name strong { font-weight: 400; display: block; overflow-wrap: anywhere; } small { color: var(--secondary-text-color); font-size: .75rem; overflow-wrap: anywhere; }
    .rank { width: 22px; height: 22px; border-radius: 50%; background: var(--secondary-background-color); display: inline-flex; align-items: center; justify-content: center; font-size: .75rem; flex: none; }
    .arrows { display: inline-flex; gap: 2px; }
    .value { min-width: 70px; text-align: right; font-variant-numeric: tabular-nums; }
    .badges { display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .assist { display: inline-flex; align-items: center; gap: 4px; font-size: .85rem; } .assist input { margin: 0; }
    .chip { font-size: .72rem; padding: 2px 8px; border-radius: 10px; background: var(--secondary-background-color); border: 1px solid var(--divider-color); }
    button.small, button.link { font: inherit; font-size: .8rem; color: var(--primary-color); background: none; border: 1px solid var(--divider-color); border-radius: 8px; padding: 2px 8px; cursor: pointer; } button.small:disabled { opacity: .4; cursor: default; }
    button.link { border: 0; text-transform: none; letter-spacing: 0; text-decoration: underline; padding: 0 4px; }
    .filters { display: flex; flex-wrap: wrap; gap: 4px 20px; margin: 0 0 12px; font-size: .9rem; } .filters label { display: inline-flex; gap: 6px; align-items: center; }
    .chooser { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: .85rem; margin: 2px 0 6px; } .chooser select { font: inherit; max-width: 100%; } .why { margin-left: 4px; }
    .note { margin: 2px 0 0; } .occupants { margin: 0; }
    summary { cursor: pointer; font-weight: 500; padding: 4px 0; }
    .scrim { position: fixed; inset: 0; z-index: 30; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; padding: 16px; }
    .dialog { background: var(--card-background-color); color: var(--primary-text-color); border-radius: 12px; padding: 16px 20px; max-width: 520px; width: 100%; max-height: 90vh; overflow: auto; box-sizing: border-box; }
    .dialog h2 { margin: 0 0 8px; font-size: 1.1rem; font-weight: 500; } .dialog select { font: inherit; margin-left: 8px; max-width: 100%; }
    fieldset.scope { border: 1px solid var(--divider-color); border-radius: 8px; margin: 12px 0; } fieldset.scope label { display: block; padding: 2px 0; }
    .refs ul li { border: 0; padding: 2px 0; display: block; }
    .actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
    .actions button { font: inherit; padding: 6px 16px; border-radius: 8px; border: 1px solid var(--divider-color); background: none; color: inherit; cursor: pointer; }
    .actions button.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: transparent; } .actions button:disabled { opacity: .5; cursor: default; }
  `;
}

if (!customElements.get("home-structure-rooms")) customElements.define("home-structure-rooms", HomeStructureRooms);
