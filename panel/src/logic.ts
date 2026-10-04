import type { Area, Bootstrap, Conn, Hass, Options, Pos, Sep, SepState, Space } from "./types";

export const BOX_W = 168;
export const BOX_H = 58;
const COL_W = 224;
const ROW_H = 92;
const MARGIN = 24;

/** Same reading as the integration: binary_sensor on = open; cover by position when it has one, else by state. */
export function normalize(state: string | undefined, attrs: Record<string, unknown> = {}): SepState {
  if (state === undefined || state === "unavailable" || state === "unknown") return "unknown";
  const pos = attrs.current_position;
  if (typeof pos === "number") return pos <= 0 ? "closed" : pos >= 100 ? "open" : "partial";
  if (state === "on" || state === "open") return "open";
  if (state === "opening" || state === "closing") return "partial";
  if (state === "off" || state === "closed") return "closed";
  return "unknown";
}

export function sepState(sep: Sep, boot: Bootstrap, hass: Hass): SepState {
  const fixed = boot.permanent[sep.type];
  if (fixed) return fixed as SepState;
  const st = sep.sensor ? hass.states[sep.sensor] : undefined;
  return st ? normalize(st.state, st.attributes) : "unknown";
}

/** The spaces on the plan: areas that have a position (rooms, or zones when given a kind) and the virtual zones. */
export function placedSpaces(boot: Bootstrap, o: Options): Space[] {
  const zones = new Map(o.zones.map((z) => [z.id, z]));
  const out: Space[] = [];
  for (const a of boot.areas) {
    const id = `area:${a.id}`;
    const pos = o.layout[id];
    if (!pos) continue;
    const z = zones.get(id) ?? null;
    out.push({ id, name: z?.name || a.name, kind: z?.kind ?? "room", in_home: z ? z.in_home : true, area: a, zone: z, pos });
  }
  for (const z of o.zones) {
    if (z.id.startsWith("zone:")) out.push({ id: z.id, name: z.name ?? z.id, kind: z.kind, in_home: z.in_home, area: null, zone: z, pos: o.layout[z.id] ?? { x: MARGIN, y: MARGIN } });
  }
  return out;
}

export function trayAreas(boot: Bootstrap, o: Options): Area[] {
  return boot.areas.filter((a) => !o.layout[`area:${a.id}`]);
}

/** Columns by floor (areas without a floor last), virtual zones in a final column. Nothing is guessed from names. */
export function autoLayout(areas: Area[], zoneIds: string[]): Record<string, Pos> {
  const groups = new Map<string, string[]>();
  for (const a of [...areas].sort((p, q) => p.name.localeCompare(q.name))) {
    const key = a.floor ?? "\uffff";
    groups.set(key, [...(groups.get(key) ?? []), `area:${a.id}`]);
  }
  const cols = [...groups.entries()].sort(([p], [q]) => p.localeCompare(q)).map(([, ids]) => ids);
  if (zoneIds.length) cols.push(zoneIds);
  const out: Record<string, Pos> = {};
  cols.forEach((ids, c) => ids.forEach((id, row) => { out[id] = { x: MARGIN + c * COL_W, y: MARGIN + row * ROW_H }; }));
  return out;
}

/** First free spot for one more space: below the lowest box of the column it would belong to, else the next column. */
export function nextFree(layout: Record<string, Pos>): Pos {
  const ps = Object.values(layout);
  if (!ps.length) return { x: MARGIN, y: MARGIN };
  const maxX = Math.max(...ps.map((p) => p.x));
  const lowest = Math.max(...ps.filter((p) => p.x === maxX).map((p) => p.y));
  return lowest + ROW_H < 640 ? { x: maxX, y: lowest + ROW_H } : { x: maxX + COL_W, y: MARGIN };
}

export function connOf(o: Options, a: string, b: string): Conn | undefined {
  return o.connections.find((c) => (c.a === a && c.b === b) || (c.a === b && c.b === a));
}

export function newId(): string {
  return Math.random().toString(16).slice(2, 10);
}

export function slug(text: string): string {
  return text.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 40) || "zone";
}

export function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T;
}
