import { LitElement, css, html, nothing } from "lit";
import { property, state } from "lit/decorators.js";
import { live } from "lit/directives/live.js";
import { ICON, pageCss } from "./styles";
import { translator } from "./i18n";
import type { Key, T } from "./i18n";
import type { Hass, RoomSensor, RoomType, RoomsView } from "./types";

type Assistant = "conversation" | "alexa" | "google";
const WHO: Record<Assistant, string> = { conversation: "Assist", alexa: "Alexa", google: "Google" };
const ERRORS = ["nothing_to_change", "assistant_unavailable", "unknown_entity", "unknown_area", "changed_since", "invalid_order", "unauthorized"];

/** The form that orders the sensors of a room, category by category, and shows what each one is exposed to (Assist, Alexa, Google). Opened from the room editor. */
class HomeStructureOrder extends LitElement {
  @property({ attribute: false }) hass!: Hass;
  @property() area = "";
  @state() private room: RoomsView["rooms"][number] | null = null;
  @state() private assistants = { alexa: false, google: false };
  @state() private confirm: { sensor: RoomSensor; who: Assistant; value: boolean } | null = null;
  @state() private error = "";
  @state() private busy = false;
  private drag: { key: string; entity: string } | null = null;
  private t: T = translator("en");

  protected willUpdate(): void {
    if (this.hass) this.t = translator(this.hass.language);
  }

  connectedCallback(): void {
    super.connectedCallback();
    void this.load();
  }

  private async load(): Promise<void> {
    const view = await this.hass.callWS<RoomsView>({ type: "home_structure/room_sensors" });
    this.assistants = view.assistants;
    this.room = view.rooms.find((r) => r.area_id === this.area) ?? null;
  }

  private groups(): RoomType[] {
    return (this.room?.types ?? []).filter((g) => g.sensors.some((s) => !s.hidden));      // the categories that describe a room (a type is ordered as a whole)
  }

  private async run(msg: Record<string, unknown>): Promise<boolean> {
    this.busy = true;
    this.error = "";
    try {
      await this.hass.callWS(msg);
      await this.load();
      return true;
    } catch (e) {
      const code = (e as { code?: string }).code ?? "";
      this.error = ERRORS.includes(code) ? this.t(`err_${code}` as Key) : this.t("err_generic", { error: (e as { message?: string }).message ?? String(e) });
      return false;
    } finally {
      this.busy = false;
    }
  }

  private save(key: string, ids: string[]): void {
    void this.run({ type: "home_structure/save_order", area_id: this.area, key, entity_ids: ids });
  }

  private nudge(g: RoomType, i: number, by: -1 | 1): void {
    const ids = g.sensors.map((s) => s.entity_id), j = i + by;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    this.save(g.key, ids);
  }

  private dropOn(g: RoomType, target: string): void {
    const d = this.drag;
    this.drag = null;
    if (!d || d.key !== g.key || d.entity === target) return;
    const ids = g.sensors.map((s) => s.entity_id).filter((x) => x !== d.entity);
    ids.splice(ids.indexOf(target), 0, d.entity);
    this.save(g.key, ids);
  }

  private async apply(): Promise<void> {
    const c = this.confirm;
    if (!c || this.busy) return;
    if (await this.run({ type: "home_structure/exposure_set", entity_id: c.sensor.entity_id, changes: { [c.who]: c.value } })) this.confirm = null;
  }

  private box(s: RoomSensor, who: Assistant, on: boolean) {
    return html`<label class="assist"><input type="checkbox" data-assistant=${who} .checked=${live(on)} @change=${(e: Event) => (this.confirm = { sensor: s, who, value: (e.target as HTMLInputElement).checked })}>${WHO[who]}</label>`;
  }

  private row(g: RoomType, s: RoomSensor, i: number) {
    return html`<li data-entity=${s.entity_id} draggable="true" @dragstart=${() => (this.drag = { key: g.key, entity: s.entity_id })} @dragover=${(e: Event) => e.preventDefault()} @drop=${(e: Event) => { e.preventDefault(); this.dropOn(g, s.entity_id); }}>
      <span class="rank">${i + 1}</span>
      <span class="arrows"><button class="small up" data-action="up" ?disabled=${i === 0 || this.busy} aria-label=${this.t("moveUp")} @click=${() => this.nudge(g, i, -1)}>▲</button><button class="small down" data-action="down" ?disabled=${i === g.sensors.length - 1 || this.busy} aria-label=${this.t("moveDown")} @click=${() => this.nudge(g, i, 1)}>▼</button></span>
      <span class="name"><strong>${s.name}</strong><small>${s.entity_id}</small></span>
      <span class="value">${s.state}${s.unit ? ` ${s.unit}` : ""}</span>
      <span class="badges">${this.box(s, "conversation", s.assist)}${this.assistants.alexa ? this.box(s, "alexa", s.alexa) : nothing}${this.assistants.google ? this.box(s, "google", s.google) : nothing}
        ${s.homekit.length ? html`<span class="chip" title=${s.homekit.join(", ")}>HomeKit</span>` : nothing}${s.matter.length ? html`<span class="chip" title=${s.matter.join(", ")}>Matter</span>` : nothing}</span>
    </li>`;
  }

  private typeName(g: RoomType): string {
    const loc = (this.hass as unknown as { localize?: (k: string) => string }).localize;
    return loc?.(`component.${g.domain}.entity_component.${g.type}.name`) || g.type.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
  }

  private close(): void {
    this.dispatchEvent(new CustomEvent("closed", { bubbles: true, composed: true }));
  }

  render() {
    const t = this.t;
    const c = this.confirm;
    return html`<div class="overlay" @click=${(e: Event) => e.target === e.currentTarget && this.close()}><div class="dialog wide" role="dialog" data-order>
      <header><button class="iconbtn" data-action="order-close" aria-label=${t("close")} @click=${this.close}><svg viewBox="0 0 24 24" width="24" height="24"><path d=${ICON.close}></path></svg></button>
        <h2>${t("orderTitle", { room: this.room?.name ?? "" })}</h2></header>
      <p class="helper">${t("orderHelp")}</p>
      ${this.room ? this.groups().map((g) => html`<div class="type" data-type=${g.type}><h3>${this.typeName(g)}</h3><ul>${g.sensors.map((s, i) => this.row(g, s, i))}</ul></div>`) : html`<p class="muted">${t("loading")}</p>`}
      ${this.error && !c ? html`<p class="warn" data-error role="alert">${this.error}</p>` : nothing}
      <footer><button class="filled" data-action="order-done" @click=${this.close}>${t("orderClose")}</button></footer>
      ${c ? html`<div class="overlay inner" data-dialog><div class="dialog small" role="alertdialog"><header><h2>${t("confirmTitle")}</h2></header>
        <p class="text">${t(c.value ? "confirmExposeOn" : "confirmExposeOff", { name: c.sensor.name, who: WHO[c.who] })}</p>
        ${this.error ? html`<p class="warn" data-error role="alert">${this.error}</p>` : nothing}
        <footer><button class="textbtn" data-action="cancel" @click=${() => { this.confirm = null; this.error = ""; void this.load(); }}>${t("cancel")}</button>
          <button class="filled" data-action="confirm" ?disabled=${this.busy} @click=${() => void this.apply()}>${t("confirm")}</button></footer></div></div>` : nothing}
    </div></div>`;
  }

  static styles = [pageCss, css`
    .dialog.wide { max-width: 760px; } .type h3 { margin: 18px 0 4px; } .muted { color: var(--secondary-text-color); } .warn { color: var(--error-color, #db4437); }
    ul { list-style: none; margin: 0; padding: 0; }
    li { display: flex; align-items: center; gap: 12px; padding: 6px 0; border-top: 1px solid var(--divider-color); flex-wrap: wrap; cursor: grab; } li:first-child { border-top: 0; }
    .rank { width: 22px; height: 22px; border-radius: 50%; background: var(--secondary-background-color); display: inline-flex; align-items: center; justify-content: center; font-size: .75rem; flex: none; }
    .arrows { display: inline-flex; gap: 2px; } .name { flex: 1 1 200px; min-width: 0; } .name strong { font-weight: 400; display: block; overflow-wrap: anywhere; } small { color: var(--secondary-text-color); font-size: .75rem; overflow-wrap: anywhere; }
    .value { min-width: 60px; text-align: right; font-variant-numeric: tabular-nums; } .badges { display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .assist { display: inline-flex; align-items: center; gap: 4px; font-size: .85rem; } .assist input { margin: 0; }
    .chip { font-size: .72rem; padding: 2px 8px; height: auto; border-radius: 10px; background: var(--secondary-background-color); border: 1px solid var(--divider-color); }
    button.small { font: inherit; font-size: .8rem; color: var(--primary-color); background: none; border: 1px solid var(--divider-color); border-radius: 8px; padding: 2px 8px; cursor: pointer; } button.small:disabled { opacity: .4; cursor: default; }
    .overlay.inner { z-index: 40; position: fixed; }
  `];
}
if (!customElements.get("home-structure-order")) customElements.define("home-structure-order", HomeStructureOrder);
