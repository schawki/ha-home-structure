"""Constants and vocabulary of Home Structure."""
DOMAIN = "home_structure"
PLATFORMS = ["sensor"]

# What separates two adjacent spaces. The vocabulary is fixed so that every integration reading the structure speaks the same language.
OPEN_SPACE = "open_space"      # no separation at all: one space split in zones (living room and hall)
OPENING = "opening"            # a passage with no door (archway, doorway)
DOOR = "door"
GLASS_DOOR = "glass_door"      # glass or sliding door
WINDOW = "window"
SHUTTER = "shutter"            # roller shutter, blind
WALL = "wall"                  # plain wall: adjacent, no passage
SEPARATION_TYPES = [OPEN_SPACE, OPENING, DOOR, GLASS_DOOR, WINDOW, SHUTTER, WALL]
PERMANENT = {OPEN_SPACE: "open", OPENING: "open", WALL: "closed"}   # types whose state never changes
SENSOR_DOMAINS = ["binary_sensor", "cover"]

# Spaces other than rooms. A zone can be inside the home (garden, balcony) or outside it (street, building hall, neighbour).
ZONE_KINDS = ["garden", "balcony", "terrace", "courtyard", "garage", "hall", "stairwell", "common_area", "street", "neighbor", "other"]
ZONE_IN_HOME = {"garden": True, "balcony": True, "terrace": True, "courtyard": True, "garage": True,
                "hall": False, "stairwell": False, "common_area": False, "street": False, "neighbor": False, "other": False}

STATES = ["open", "closed", "partial"]   # a separation whose state cannot be read is "unknown"
