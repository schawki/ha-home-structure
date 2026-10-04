# Home Structure

A Home Assistant integration that describes **the structure of your home**: which spaces are next to each other, what separates them (open space, doorway, door, glass door, window, shutter, plain wall) and what the opening sensors say right now.

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
  | `window` | a window | from its sensor |
  | `shutter` | roller shutter or blind | from its cover |
  | `wall` | a plain wall: adjacent, no passage | always closed |

  A door and a glass door between the same two spaces are two separations of one connection.
- **Sensors.** A separation that can change may have a `binary_sensor` (door or window contact) or a `cover` (shutter). Its state becomes `open`, `closed`, `partial` (a cover between 1 and 99 %, or moving) or `unknown` (no sensor, or it does not answer).

## Setting it up

*Settings → Devices & services → Home Structure → Configure*, three quick steps, then **Save and close**:

1. **Choose the spaces.** Every Home Assistant area is ticked; untick the ones that are not places of your home. The floor of each area is shown to help you choose. Nothing is guessed from names or floors.
2. **Mark gardens, halls and other zones** in one screen: one list per kind (gardens, balconies, terraces, courtyards, garages, halls, stairwells, shared areas), plus two switches for the street and a neighbouring home. The kind decides whether the zone is part of the home (a garden is, a building hall is not); change it zone by zone if needed.
3. **Connect spaces quickly.** Pick a space, tick everything that touches it, say what separates them; then refine each new connection (type and opening sensor). Only door, window and cover entities of the two areas are offered as sensors.

The older one-by-one screens remain available.

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
