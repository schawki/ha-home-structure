# Home Structure

A Home Assistant integration that describes **the structure of your home**: which spaces are next to each other, what separates them (open space, doorway, door, glass door, security grille, window, shutter, plain wall) and what the opening sensors say right now.

It does not do anything with sound, light, heat or presence. It only keeps the description of the home, so that any integration or automation can ask "is the living room open to the hall?" instead of each one asking you to describe your home again. [Sound Recognition](https://github.com/schawki/sound-recognition-ha) is the first one to use it.

*Français : [docs/README.fr.md](docs/README.fr.md)*

![The plan: rooms, links and what separates them](docs/images/plan.png)

## Install

Requires Home Assistant 2025.8 or later and your rooms defined as areas.

1. HACS → Custom repositories → `https://github.com/schawki/ha-home-structure` (category: Integration) → install, restart Home Assistant.
2. Settings → Devices & services → Add integration → **Home Structure**.
3. Click **Configure** to describe your home.

## The model

- **Spaces.** A room is a Home Assistant area. A **zone** is a space that is not an ordinary room, and it can be:
  - *inside your home*: garden, balcony, terrace, courtyard, garage;
  - *outside it*: the hall or landing, the stairwell, a shared area of the building, the street, a neighbouring home.

  If a zone already exists as a Home Assistant area (a garden with a camera, a building hall with a doorbell), you give that area a kind and say whether it is part of the home; its devices stay where they are. Zones with no area (the street, the neighbour) are created in Home Structure.
- **Types of room.** An ordinary room can be given a type, chosen by you and never guessed from its name: organised in groups: sleeping (bedroom, master bedroom, child's bedroom, baby's room, guest room), living and leisure (living room, dining room, game room, home cinema, gym), work (office, workshop), bathrooms (bathroom, toilet), kitchen and utility (kitchen, pantry, laundry room, utility room, dressing room, storage, cellar, attic) and circulation (hallway, entrance, staircase). A garage is a kind of zone. A released type is never removed. It is optional, and only rooms have one. Integrations read it as `room_type` to adapt to what a room is used for.
- **Connections.** Two spaces that are next to each other are connected. Two spaces with no connection are not adjacent.
- **Separations.** A connection has one or more separations, and each has a type:

  | Type | Meaning | State |
  |---|---|---|
  | `open_space` | no separation at all (a living room and a hall in one space) | always open |
  | `opening` | a passage with no door | always open |
  | `door` | a door | from its sensor |
  | `glass_door` | glass or sliding door | from its sensor |
  | `grille` | security grille or mesh door: a physical barrier that hardly stops sound | from its sensor if it has one |
  | `window` | a window | from its sensor |
  | `shutter` | roller shutter or blind | from its cover |
  | `wall` | a plain wall: adjacent, no passage | always closed |

  A door and a glass door between the same two spaces are two separations of one connection.
- **Sensors.** A separation that can change may have a `binary_sensor` (door or window contact) or a `cover` (shutter). Its state becomes `open`, `closed`, `partial` (a cover between 1 and 99 %, or moving) or `unknown` (no sensor, or it does not answer).
- **A shutter in front of a window or a door.** A door, glass door or window can also name the `cover` of the roller shutter or blind in front of it (the `shutter` field). The separation keeps its own state and reports the shutter next to it in the attributes `shutter`, `shutter_state` and `shutter_position`, so a consumer can combine the two. Use the separate `shutter` type only for a shutter that is the whole separation.

## Setting it up

Open **Home Structure** in the sidebar. You see a plan you arrange yourself, and everything you do is saved immediately and can be undone:

1. **Add your rooms.** The left column lists the Home Assistant areas that are not on the plan yet. Click **Add all** (they are laid out in one column per floor, which you can then move around), or drag or click only the ones you want. Areas left in the column are ignored. Nothing is guessed from names.
2. **Move them** wherever makes sense to you, so the plan looks like your home. **Rearrange** lays everything out again by floor.
3. **Connect them.** Drag the ● handle of a room onto the room next to it. Click the link to say what separates them (open space, door, glass door, grille, window, shutter, wall…), pick the opening sensor from the door, window and cover entities of the two rooms, pick the shutter in front of a window or door if there is one, and add a second separation if there is another. The link shows the live state of each separation (open, closed, partly open).
4. **Give each room its type** in its panel (bedroom, nursery, gym, dressing room…), or leave it unspecified. One list covers rooms and outside spaces.
5. **Add what is outside** with **+ Zone**: garden, balcony, hall, stairwell, street, a neighbouring home… The kind decides whether the zone is part of the home; you can change it. A room can also be turned into a zone kind (an area named "Garage" can be marked as a garage), and a room can be split by creating a zone next to it.

On a narrow screen the plan becomes a list with the same editing. The older configuration screens (*Configure* on the integration) still work and edit the same data.

## Groups of rooms

The **Groups** tab of the panel gathers rooms into groups of your own: the bedrooms, the night part of the home, the rooms that face the street… Home Assistant only groups areas by floor; a group has no such limit, so a **room can be in several groups** (or in none), and nothing is guessed from names.

![The Groups tab: groups of rooms laid out like the floors of the Areas page](docs/images/groups.png)

- The page works like the Areas page of Home Assistant: one section per group with a card per room, **+ Add** at the bottom right to create a group, and a ⋮ menu on each group (**Rearrange rooms**, **Edit group**, **Delete group**). The ⋮ menu at the top rearranges the groups themselves. The order you choose is kept.
- The ⋮ menu of a room card **moves it to another group**, **adds it to another group**, **removes it from this group** or **from all groups**. Rooms in no group are listed at the bottom.
- **Edit group** has an ID (set when the group is created, never changed), a name, an icon, the rooms (chips, with **Add a room**), aliases and a *level* (stored, not used by anything yet). Aliases are other names for your own templates and scripts: they appear in the service and the attributes below; Assist does not read them.
- **Temperature and humidity.** For each, choose *No sensor*, *One sensor* (among those of the rooms of the group), *Average of all the sensors of the rooms* or *Average of a selection*. Diagnostic and configuration entities are never offered, and the dialog shows each source with its value. "All" is looked up every time, so a sensor moved to or from one of these rooms is followed automatically. A group with a sensor gets a `sensor` entity (for example `sensor.home_structure_night_temperature`) with the attributes `group`, `mode`, `area_ids`, `sources` and `used_sources`. A source that is unavailable, not a number or absurd (a humidity above 100 %) is ignored rather than counted as zero; Fahrenheit and Kelvin sources are converted. If a room leaves a group, the sensors that are no longer in the group's rooms are taken out of its settings and the panel tells you.
- A group can be empty, and deleting a group never touches its rooms.

Use the rooms of a group wherever Home Assistant takes an area, by reading the list from the service:

```yaml
actions:
  - action: home_structure.get_groups
    response_variable: result
  - action: light.turn_off
    target:
      area_id: "{{ (result.groups | selectattr('id', 'eq', 'night') | first).area_ids }}"
```

Whether a device can act on areas depends on the device and its integration (a vacuum that cleans by room, for instance, depends on what its integration offers); Home Structure only supplies the list of areas.

Labels of Home Assistant also give several memberships and can be targeted, but they apply to anything. Groups only hold rooms, are arranged like floors, and can give a temperature and a humidity for the whole group.

## What you get

- **One sensor per separation**, for example `sensor.home_structure_living_room_building_hall_door`, with the state `open`, `closed` or `partial` (unknown when it cannot be read) and the attributes `type`, `space_a`, `space_b`, `name_a`, `name_b`, `sensor` and `position`. Use it in automations, templates and dashboards.
- **A service** `home_structure.get_structure`, which returns the whole structure with current states, for integrations:

```yaml
action: home_structure.get_structure
response_variable: home
```

```yaml
spaces:
  - {id: "area:living_room", name: Living room, kind: room, room_type: living_room, in_home: true, area_id: living_room}
  - {id: "area:hall", name: Building hall, kind: hall, room_type: null, in_home: false, area_id: hall}
  - {id: "zone:street", name: Street, kind: street, room_type: null, in_home: false, area_id: null}
connections:
  - id: 1f3a9c2e
    a: "area:living_room"
    b: "area:hall"
    a_name: Living room
    b_name: Building hall
    separations:
      - {id: 7be41d90, type: door, state: open, position: null, sensor: binary_sensor.hall_door, entity_id: sensor.home_structure_living_room_building_hall_door, shutter: null, shutter_state: null, shutter_position: null}
layout:   # positions on the editor plan, to draw it
  "area:living_room": {x: 24, y: 24}
  "area:hall": {x: 248, y: 24}
```

- **A service** `home_structure.get_groups`, which returns the groups of rooms: `id`, `name`, `level`, `icon`, `aliases`, `area_ids`, `areas` (id and name) and, for `temperature` and `humidity`, the `mode`, the `entities` chosen and the `entity_id` of the group sensor (null without one).

For an integration, reading the structure goes through this service and the `entity_id` of each separation: nothing to import, nothing to install beyond Home Structure.

## Using it in an automation

Each separation is a sensor, so the state of a door between two rooms is available like any other entity:

```yaml
triggers:
  - trigger: state
    entity_id: sensor.home_structure_living_room_building_hall_door
    to: open
actions:
  - action: notify.mobile_app_phone
    data: {message: "The door to the building hall is open."}
```

## Used by Sound Recognition

[Sound Recognition](https://github.com/schawki/sound-recognition-ha) reads the structure to know how much a sound passes from one room to the next (an open door lets it through, a closed door or shutter muffles it, a wall nearly stops it) and to include the devices of connected rooms. It is optional for Sound Recognition, and Home Structure does not need it.

## Troubleshooting

- *A room does not appear in the list on the left*: it is not a Home Assistant area yet, or it is already on the plan.
- *A separation shows `unknown`*: it has no sensor, or its sensor is unavailable. Doors and windows without a sensor stay `unknown`; only open spaces, openings and walls have a fixed state.
- *The sensor of a separation is not in the list*: only door, window and cover entities of the two rooms are offered; assign the entity to the right area first.
- *Everything looks wrong after a change*: use **Undo** in the panel; every change is saved immediately and can be undone.

## Languages

English is the reference. French is included. To add a language, see [CONTRIBUTING.md](CONTRIBUTING.md): it is one file to copy and translate.

## Status

Version 0.7, tested (backend and panel test suites run on every commit) and used with Sound Recognition. The home is described in the **Home Structure** panel of the sidebar (a plan you arrange, with autosave and undo); the *Configure* menus of the integration remain as a fallback. Groups of rooms are in the **Groups** tab. Feedback and issues are welcome.

## Licence

MIT.
