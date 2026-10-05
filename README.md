# Home Structure

A Home Assistant integration that describes **the structure of your home**: which spaces are next to each other, what separates them (open space, doorway, door, glass door, security grille, window, shutter, plain wall) and what the opening sensors say right now.

It does not do anything with sound, light, heat or presence. It only keeps the description of the home, so that any integration or automation can ask "is the living room open to the hall?" instead of each one asking you to describe your home again. [Sound Recognition](https://github.com/schawki/sound-recognition-ha) is the first one to use it.

*Français : [docs/README.fr.md](docs/README.fr.md)*

## Install

1. HACS → Custom repositories → `https://github.com/schawki/ha-home-structure` (category: Integration) → install, restart Home Assistant.
2. Settings → Devices & services → Add integration → **Home Structure**.
3. Click **Configure** to describe your home.

## The model

- **Spaces.** A room is a Home Assistant area. A **zone** is a space that is not an ordinary room, and it can be:
  - *inside your home*: garden, balcony, terrace, courtyard, garage;
  - *outside it*: the hall or landing, the stairwell, a shared area of the building, the street, a neighbouring home.

  If a zone already exists as a Home Assistant area (a garden with a camera, a building hall with a doorbell), you give that area a kind and say whether it is part of the home; its devices stay where they are. Zones with no area (the street, the neighbour) are created in Home Structure.
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
4. **Add what is outside** with **+ Zone**: garden, balcony, hall, stairwell, street, a neighbouring home… The kind decides whether the zone is part of the home; you can change it. A room can also be turned into a zone kind (an area named "Garage" can be marked as a garage), and a room can be split by creating a zone next to it.

On a narrow screen the plan becomes a list with the same editing. The older configuration screens (*Configure* on the integration) still work and edit the same data.

## What you get

- **One sensor per separation**, for example `sensor.home_structure_living_room_building_hall_door`, with the state `open`, `closed` or `partial` (unknown when it cannot be read) and the attributes `type`, `space_a`, `space_b`, `name_a`, `name_b`, `sensor` and `position`. Use it in automations, templates and dashboards.
- **A service** `home_structure.get_structure`, which returns the whole structure with current states, for integrations:

```yaml
action: home_structure.get_structure
response_variable: home
```

```yaml
spaces:
  - {id: "area:living_room", name: Living room, kind: room, in_home: true, area_id: living_room}
  - {id: "area:hall", name: Building hall, kind: hall, in_home: false, area_id: hall}
  - {id: "zone:street", name: Street, kind: street, in_home: false, area_id: null}
connections:
  - id: 1f3a9c2e
    a: "area:living_room"
    b: "area:hall"
    a_name: Living room
    b_name: Building hall
    separations:
      - {id: 7be41d90, type: door, state: open, position: null, sensor: binary_sensor.hall_door, entity_id: sensor.home_structure_living_room_building_hall_door}
```

For an integration, reading the structure goes through this service and the `entity_id` of each separation: nothing to import, nothing to install beyond Home Structure.

## Languages

English is the reference. French is included. To add a language, see [CONTRIBUTING.md](CONTRIBUTING.md): it is one file to copy and translate.

## Status

Version 0.1. Describing the home is done in Configure (menus). A visual editor may come later.

## Licence

MIT.
