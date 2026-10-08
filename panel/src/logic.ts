import type { Area, Bootstrap, Conn, Group, Hass, Options, Pos, Sep, SepState, Space } from "./types";

export const BOX_W = 168;
export const BOX_H = 58;
const COL_W = 290;
const ROW_H = 120;
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

/** State of the shutter in front of a separation; null when it has none. */
export function shutterState(sep: Sep, hass: Hass): SepState | null {
  if (!sep.shutter) return null;
  const st = hass.states[sep.shutter];
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
    out.push({ id, name: z?.name || a.name, kind: z?.kind ?? "room", room_type: z ? null : o.room_types[id] ?? null, in_home: z ? z.in_home : true, area: a, zone: z, pos });
  }
  for (const z of o.zones) {
    if (z.id.startsWith("zone:")) out.push({ id: z.id, name: z.name ?? z.id, kind: z.kind, room_type: null, in_home: z.in_home, area: null, zone: z, pos: o.layout[z.id] ?? { x: MARGIN, y: MARGIN } });
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


// ---------------------------------------------------------------------------------------------- groups of rooms
export function groupsOf(groups: Group[], areaId: string): Group[] {
  return groups.filter((g) => g.areas.includes(areaId));
}

/** Rooms that are in no group. */
export function ungrouped(areas: Area[], groups: Group[]): Area[] {
  return areas.filter((a) => !groups.some((g) => g.areas.includes(a.id)));
}

function edit(groups: Group[], gid: string, fn: (g: Group) => void): Group[] {
  const out = clone(groups);
  const g = out.find((x) => x.id === gid);
  if (g) fn(g);
  return out;
}

export function addRoom(groups: Group[], gid: string, areaId: string): Group[] {
  return edit(groups, gid, (g) => { if (!g.areas.includes(areaId)) g.areas.push(areaId); });
}

export function removeRoom(groups: Group[], gid: string, areaId: string): Group[] {
  return edit(groups, gid, (g) => { g.areas = g.areas.filter((a) => a !== areaId); });
}

export function removeFromAll(groups: Group[], areaId: string): Group[] {
  return groups.reduce((acc, g) => removeRoom(acc, g.id, areaId), groups);
}

export function moveRoom(groups: Group[], from: string, to: string, areaId: string): Group[] {
  return addRoom(removeRoom(groups, from, areaId), to, areaId);
}

/** Moves an item one place earlier (-1) or later (+1) in a list; the list is returned as it is at either end. */
export function shift<T>(list: T[], index: number, delta: -1 | 1): T[] {
  const to = index + delta;
  if (index < 0 || to < 0 || to >= list.length) return list;
  const out = [...list];
  [out[index], out[to]] = [out[to], out[index]];
  return out;
}

export function moveGroup(groups: Group[], gid: string, delta: -1 | 1): Group[] {
  return shift(groups, groups.findIndex((g) => g.id === gid), delta);
}

export function moveRoomInGroup(groups: Group[], gid: string, areaId: string, delta: -1 | 1): Group[] {
  return edit(groups, gid, (g) => { g.areas = shift(g.areas, g.areas.indexOf(areaId), delta); });
}

/** Id of a new group: the slug of its name, with a number when taken (the integration builds the same one). */
export function newGroupId(name: string, groups: Group[]): string {
  const base = slug(name);
  let id = base, n = 1;
  while (groups.some((g) => g.id === id)) id = `${base}_${++n}`;
  return id;
}

/** The list with the item at `from` taken out and put back at `to`. */
export function reorder<T>(list: T[], from: number, to: number): T[] {
  if (from < 0 || to < 0 || from >= list.length || to >= list.length || from === to) return list;
  const out = [...list];
  out.splice(to, 0, ...out.splice(from, 1));
  return out;
}

export interface Box { left: number; top: number; right: number; bottom: number }

/** Index of the box under the point, else of the nearest one (by its centre; only vertically when `vertical`). -1 without boxes. */
export function nearestIndex(boxes: Box[], x: number, y: number, vertical = false): number {
  let best = -1, bestDistance = Infinity;
  boxes.forEach((b, i) => {
    if (vertical ? y >= b.top && y <= b.bottom : x >= b.left && x <= b.right && y >= b.top && y <= b.bottom) { best = i; bestDistance = -1; return; }
    if (bestDistance < 0) return;
    const dx = vertical ? 0 : (b.left + b.right) / 2 - x, dy = (b.top + b.bottom) / 2 - y;
    const d = Math.hypot(dx, dy);
    if (d < bestDistance) { best = i; bestDistance = d; }
  });
  return best;
}

export function inside(b: Box, x: number, y: number, margin = 0): boolean {
  return x >= b.left - margin && x <= b.right + margin && y >= b.top - margin && y <= b.bottom + margin;
}

/** The rooms of a group in the given order (rooms not listed keep their place at the end). */
export function setRoomOrder(groups: Group[], gid: string, order: string[]): Group[] {
  return edit(groups, gid, (g) => { g.areas = [...order, ...g.areas.filter((a) => !order.includes(a))]; });
}

export function setGroupOrder(groups: Group[], order: string[]): Group[] {
  const by = new Map(groups.map((g) => [g.id, g]));
  return [...order.flatMap((id) => (by.has(id) ? [by.get(id)!] : [])), ...groups.filter((g) => !order.includes(g.id))];
}
