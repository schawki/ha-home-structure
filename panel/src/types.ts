export interface Area { id: string; name: string; floor: string | null }
export interface Sep { id: string; type: string; sensor?: string; shutter?: string }
export interface Conn { id: string; a: string; b: string; separations: Sep[] }
export interface Zone { id: string; kind: string; in_home: boolean; name?: string }
export interface Pos { x: number; y: number }
export interface Options { zones: Zone[]; connections: Conn[]; excluded_areas: string[]; layout: Record<string, Pos>; room_types: Record<string, string> }
export interface Bootstrap { areas: Area[]; options: Options; kinds: string[]; types: string[]; in_home: Record<string, boolean>; permanent: Record<string, string>; sensor_domains: string[]; shutter_hosts: string[]; room_types: string[] }
export interface Sensor { entity_id: string; name: string; state: string }
export interface Candidates { sensors: Sensor[]; filtered: boolean }
export interface Space { id: string; name: string; kind: string; room_type: string | null; in_home: boolean; area: Area | null; zone: Zone | null; pos: Pos }
export interface HassState { state: string; attributes: Record<string, unknown> }
export interface Hass { language: string; states: Record<string, HassState>; callWS<T>(msg: Record<string, unknown>): Promise<T> }
export type SepState = "open" | "closed" | "partial" | "unknown";
