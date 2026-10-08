"""Constants and vocabulary of Home Structure."""
DOMAIN = "home_structure"
PLATFORMS = ["sensor"]
GROUPS_CHANGED = DOMAIN + "_groups_changed_{}"      # dispatcher signal (per config entry id): the groups were saved, the group sensors follow

# What separates two adjacent spaces. The vocabulary is fixed so that every integration reading the structure speaks the same language.
OPEN_SPACE = "open_space"      # no separation at all: one space split in zones (living room and hall)
OPENING = "opening"            # a passage with no door (archway, doorway)
DOOR = "door"
GLASS_DOOR = "glass_door"      # glass or sliding door
WINDOW = "window"
SHUTTER = "shutter"            # roller shutter, blind
WALL = "wall"                  # plain wall: adjacent, no passage
GRILLE = "grille"              # security grille or mesh door: a physical barrier that hardly stops sound
SEPARATION_TYPES = [OPEN_SPACE, OPENING, DOOR, GLASS_DOOR, GRILLE, WINDOW, SHUTTER, WALL]
PERMANENT = {OPEN_SPACE: "open", OPENING: "open", WALL: "closed"}   # types whose state never changes
SENSOR_DOMAINS = ["binary_sensor", "cover"]
SHUTTER_HOSTS = [DOOR, GLASS_DOOR, WINDOW]   # separations that can have a roller shutter or blind in front of them (a cover entity)

# Spaces other than rooms. A zone can be inside the home (garden, balcony) or outside it (street, building hall, neighbour).
ZONE_KINDS = ["garden", "balcony", "terrace", "courtyard", "garage", "hall", "stairwell", "common_area", "street", "neighbor", "other"]
ZONE_IN_HOME = {"garden": True, "balcony": True, "terrace": True, "courtyard": True, "garage": True,
                "hall": False, "stairwell": False, "common_area": False, "street": False, "neighbor": False, "other": False}

# What an ordinary room is used for (optional, chosen by the user, never guessed from a name), organised in groups.
# Zones have their own kinds above. Integrations read the type as `room_type`; a type is never removed once released.
ROOM_TYPE_GROUPS = {
    "sleeping": ["bedroom", "master_bedroom", "child_bedroom", "nursery", "guest_room"],
    "living": ["living_room", "dining_room", "game_room", "home_cinema", "gym"],
    "work": ["office", "workshop"],
    "water": ["bathroom", "toilet"],
    "service": ["kitchen", "pantry", "laundry", "utility_room", "dressing", "storage", "cellar", "attic"],
    "circulation": ["hallway", "entrance", "staircase"],
}
ROOM_TYPES = [t for group in ROOM_TYPE_GROUPS.values() for t in group]

STATES = ["open", "closed", "partial"]   # a separation whose state cannot be read is "unknown"
