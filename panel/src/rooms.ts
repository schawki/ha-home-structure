import { LitElement, css, html, nothing } from "lit";
import { property, state } from "lit/decorators.js";
import { translator } from "./i18n";
import type { T } from "./i18n";
import type { Hass, RoomsView, RoomSensor, User } from "./types";

/** The "Rooms" page of the panel: the sensors of each room by type, and what is exposed to Assist, HomeKit and Matter. Read only for now. */
class HomeStructureRooms extends LitElement {
  @property({ attribute: false }) hass!: Hass;
  @state() private data: RoomsView | null = null;
  @state() private users: User[] = [];
  @state() private failed = false;
  private t: T = translator("en");

  protected willUpdate(): void {
    if (this.hass) this.t = translator(this.hass.language);
  }

  connectedCallback(): void {
    super.connectedCallback();
    void this.load();
  }

  private async load(): Promise<void> {
    try {
      const [view, boot] = await Promise.all([
        this.hass.callWS<RoomsView>({ type: "home_structure/room_sensors" }),
        this.hass.callWS<{ users: User[] }>({ type: "home_structure/get" }),
      ]);
      this.data = view;
      this.users = boot.users ?? [];
    } catch {
      this.failed = true;
    }
  }

  /** The name of a device class: Home Assistant's own translation when the page can reach it, else the class made readable. */
  private typeName(domain: string, cls: string): string {
    if (cls === "other") return this.t("typeOther");
    const loc = (this.hass as unknown as { localize?: (k: string) => string }).localize;
    const own = loc?.(`component.${domain}.entity_component.${cls}.name`);
    return own || cls.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
  }

  private badges(s: RoomSensor) {
    const t = this.t;
    return html`<span class="badges">
      <label class="assist" title=${t("assistHelp")}><input type="checkbox" class="assist-box" disabled .checked=${s.assist}>${t("assist")}</label>
      ${s.homekit.length ? html`<span class="chip homekit" data-badge="homekit" title=${s.homekit.join(", ")}>HomeKit</span>` : nothing}
      ${s.matter.length ? html`<span class="chip matter" data-badge="matter" title=${s.matter.join(", ")}>Matter</span>` : nothing}
    </span>`;
  }

  private sensor(s: RoomSensor, rank: number | null) {
    return html`<li data-entity=${s.entity_id}>
      ${rank === null ? nothing : html`<span class="rank" aria-label=${this.t("priority", { n: rank })}>${rank}</span>`}
      <span class="name"><strong>${s.name}</strong><small>${s.entity_id}${s.device_name ? ` · ${s.device_name}` : ""}</small></span>
      <span class="value">${s.state}${s.unit ? ` ${s.unit}` : ""}</span>
      ${this.badges(s)}
    </li>`;
  }

  private renderRoom(r: RoomsView["rooms"][number]) {
    const t = this.t;
    const names = r.occupants.map((id) => this.users.find((u) => u.id === id)?.name).filter(Boolean).join(", ");
    return html`<section class="room" data-room=${r.area_id}>
      <header><h2>${r.name}</h2>${names ? html`<span class="muted occupants">${t("occupantsLabel")} ${names}</span>` : nothing}</header>
      ${r.types.length ? r.types.map((g) => html`<div class="type" data-type=${g.type}>
          <h3>${this.typeName(g.domain, g.type)}</h3>
          <ul>${g.sensors.map((s, i) => this.sensor(s, g.ordered ? i + 1 : null))}</ul>
          ${g.assist_first === false ? html`<p class="muted note" data-note="not-first">ⓘ ${t("notFirst")}</p>` : nothing}
        </div>`) : html`<p class="muted">${t("noSensorsInRoom")}</p>`}
    </section>`;
  }

  protected render() {
    const t = this.t;
    if (this.failed) return html`<p class="msg">${t("notLoaded")}</p>`;
    if (!this.data) return html`<p class="msg">${t("loading")}</p>`;
    const d = this.data;
    return html`<p class="muted intro">${t("roomsHelp")}${d.matter.available ? nothing : html` ${t("matterUnavailable")}`}</p>
      ${d.rooms.length ? d.rooms.map((r) => this.renderRoom(r)) : html`<p class="muted" data-empty>${t("roomsEmpty")}</p>`}
      ${d.unassigned.length ? html`<details class="unassigned" data-unassigned>
        <summary>${t("unassignedTitle")} (${d.unassigned.length})</summary>
        <p class="muted">${t("unassignedHelp")}</p>
        <ul>${d.unassigned.map((s) => html`<li data-entity=${s.entity_id}>
          <span class="name"><strong>${s.name}</strong><small>${s.entity_id} · ${this.typeName(s.domain, s.type)}</small></span>
          <span class="value">${s.state}${s.unit ? ` ${s.unit}` : ""}</span>${this.badges(s)}</li>`)}</ul>
      </details>` : nothing}`;
  }

  static styles = css`
    :host { display: block; padding: 8px 16px 48px; box-sizing: border-box; color: var(--primary-text-color); }
    .msg, .intro { padding: 12px 8px; } .muted { color: var(--secondary-text-color); font-size: .85rem; }
    .room { background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: 12px; padding: 4px 16px 12px; margin: 0 0 16px; }
    .room header { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; } .room h2 { font-size: 1.1rem; font-weight: 500; margin: 12px 0 4px; }
    h3 { font-size: .8rem; font-weight: 500; text-transform: uppercase; letter-spacing: .04em; color: var(--secondary-text-color); margin: 12px 0 2px; }
    ul { list-style: none; margin: 0; padding: 0; }
    li { display: flex; align-items: center; gap: 12px; padding: 6px 0; border-top: 1px solid var(--divider-color); flex-wrap: wrap; } li:first-child { border-top: 0; }
    .name { flex: 1 1 220px; min-width: 0; } .name strong { font-weight: 400; display: block; overflow-wrap: anywhere; } small { color: var(--secondary-text-color); font-size: .75rem; overflow-wrap: anywhere; }
    .rank { width: 22px; height: 22px; border-radius: 50%; background: var(--secondary-background-color); display: inline-flex; align-items: center; justify-content: center; font-size: .75rem; flex: none; }
    .value { min-width: 70px; text-align: right; font-variant-numeric: tabular-nums; }
    .badges { display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .assist { display: inline-flex; align-items: center; gap: 4px; font-size: .85rem; } .assist input { margin: 0; }
    .chip { font-size: .72rem; padding: 2px 8px; border-radius: 10px; background: var(--secondary-background-color); border: 1px solid var(--divider-color); }
    .note { margin: 2px 0 0; } .occupants { margin: 0; }
    details { background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: 12px; padding: 8px 16px; } summary { cursor: pointer; font-weight: 500; padding: 4px 0; }
  `;
}

if (!customElements.get("home-structure-rooms")) customElements.define("home-structure-rooms", HomeStructureRooms);
