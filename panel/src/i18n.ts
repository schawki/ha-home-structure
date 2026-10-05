// English is the reference. To add a language, add a dictionary with the same keys.
const EN = {
  title: "Home Structure",
  loading: "Loading…",
  notLoaded: "Home Structure is not set up. Add the integration in Settings → Devices & services.",
  saving: "Saving…", saved: "Saved", saveFailed: "Could not save: {error}",
  undo: "Undo", reorganize: "Rearrange", addAll: "Add all", addZone: "+ Zone",
  trayTitle: "Not on the plan yet", trayHelp: "Drag a room onto the plan, or click it. Rooms left here are ignored.", trayEmpty: "Every area is on the plan.",
  planEmpty: "The plan is empty. Add your rooms from the left column.",
  noFloor: "no floor", floor: "floor",
  hint: "Drag a room to move it. Drag its ● handle onto another room to connect them. Click a link to say what separates them.",
  zoneName: "Name", zoneKind: "Type", partOfHome: "Part of the home", create: "Create", cancel: "Cancel",
  rt_bedroom: "Bedroom", rt_bathroom: "Bathroom", rt_toilet: "Toilet", rt_kitchen: "Kitchen", rt_living_room: "Living room", rt_dining_room: "Dining room",
  rt_office: "Office", rt_hallway: "Hallway", rt_entrance: "Entrance", rt_dressing: "Dressing room", rt_laundry: "Laundry room", rt_storage: "Storage", rt_utility_room: "Utility room",
  rt_master_bedroom: "Master bedroom", rt_child_bedroom: "Child's bedroom", rt_nursery: "Baby's room", rt_guest_room: "Guest room", rt_game_room: "Game room", rt_home_cinema: "Home cinema", rt_gym: "Gym",
  rt_workshop: "Workshop", rt_pantry: "Pantry", rt_cellar: "Cellar", rt_attic: "Attic", rt_staircase: "Staircase",
  rg_sleeping: "Sleeping", rg_living: "Living and leisure", rg_work: "Work", rg_water: "Bathrooms", rg_service: "Kitchen and utility", rg_circulation: "Circulation",
  typeNotSet: "Not specified", groupOutside: "Outside and shared",
  kind_room: "Room", kind_garden: "Garden", kind_balcony: "Balcony", kind_terrace: "Terrace", kind_courtyard: "Courtyard", kind_garage: "Garage",
  kind_hall: "Hall or landing", kind_stairwell: "Stairwell", kind_common_area: "Shared area of the building", kind_street: "Street", kind_neighbor: "Neighbouring home", kind_other: "Other",
  type_open_space: "open space", type_opening: "opening", type_door: "door", type_glass_door: "glass door", type_grille: "security grille", type_window: "window", type_shutter: "shutter", type_wall: "wall",
  state_open: "open", state_closed: "closed", state_partial: "partly open", state_unknown: "unknown",
  space: "Space", connections: "Connections", connectTo: "Connect to…", noConnections: "Not connected to anything yet.",
  removeFromPlan: "Put back in the list", deleteZone: "Delete this zone",
  link: "Link", separations: "What separates them", addSeparation: "+ Add a separation", removeLink: "Remove this link", removeSep: "Remove",
  sensor: "Opening sensor", noSensor: "No sensor", sensorsHere: "Door, window and cover entities of the two rooms", sensorsAll: "Nothing found in these rooms: every sensor of the home is listed",
  noSensorNeeded: "No sensor needed: this never changes.",
  shutter: "Shutter in front (optional)", noShutter: "No shutter", shutterShort: "shutter", shutterHint: "Roller shutters and blinds of the two rooms: a closed shutter behind a closed window blocks more sound.",
  close: "Close", list: "List", plan: "Plan",
} as const;
export type Key = keyof typeof EN;
type Dict = Record<Key, string>;

const FR: Dict = {
  title: "Home Structure",
  loading: "Chargement…",
  notLoaded: "Home Structure n'est pas configuré. Ajoutez l'intégration dans Paramètres → Appareils et services.",
  saving: "Enregistrement…", saved: "Enregistré", saveFailed: "Enregistrement impossible : {error}",
  undo: "Annuler", reorganize: "Réorganiser", addAll: "Tout ajouter", addZone: "+ Zone",
  trayTitle: "Pas encore sur le plan", trayHelp: "Glissez une pièce sur le plan, ou cliquez dessus. Les pièces laissées ici sont ignorées.", trayEmpty: "Toutes les pièces sont sur le plan.",
  planEmpty: "Le plan est vide. Ajoutez vos pièces depuis la colonne de gauche.",
  noFloor: "sans étage", floor: "étage",
  hint: "Glissez une pièce pour la déplacer. Glissez sa poignée ● sur une autre pièce pour les relier. Cliquez sur un lien pour dire ce qui les sépare.",
  zoneName: "Nom", zoneKind: "Type", partOfHome: "Fait partie du logement", create: "Créer", cancel: "Annuler",
  rt_bedroom: "Chambre", rt_bathroom: "Salle de bains", rt_toilet: "Toilettes", rt_kitchen: "Cuisine", rt_living_room: "Salon", rt_dining_room: "Salle à manger",
  rt_office: "Bureau", rt_hallway: "Couloir", rt_entrance: "Entrée", rt_dressing: "Dressing", rt_laundry: "Buanderie", rt_storage: "Rangement", rt_utility_room: "Local technique",
  rt_master_bedroom: "Chambre parentale", rt_child_bedroom: "Chambre d'enfant", rt_nursery: "Chambre de bébé", rt_guest_room: "Chambre d'amis", rt_game_room: "Salle de jeux", rt_home_cinema: "Salle de cinéma", rt_gym: "Salle de sport",
  rt_workshop: "Atelier", rt_pantry: "Cellier", rt_cellar: "Cave", rt_attic: "Grenier", rt_staircase: "Escalier",
  rg_sleeping: "Dormir", rg_living: "Vie et loisirs", rg_work: "Travail", rg_water: "Salles d'eau", rg_service: "Cuisine et services", rg_circulation: "Circulation",
  typeNotSet: "Non précisé", groupOutside: "Extérieur et parties communes",
  kind_room: "Pièce", kind_garden: "Jardin", kind_balcony: "Balcon", kind_terrace: "Terrasse", kind_courtyard: "Cour", kind_garage: "Garage",
  kind_hall: "Hall ou palier", kind_stairwell: "Cage d'escalier", kind_common_area: "Partie commune de l'immeuble", kind_street: "Rue", kind_neighbor: "Logement voisin", kind_other: "Autre",
  type_open_space: "espace ouvert", type_opening: "ouverture", type_door: "porte", type_glass_door: "porte vitrée", type_grille: "grille", type_window: "fenêtre", type_shutter: "volet", type_wall: "mur",
  state_open: "ouvert", state_closed: "fermé", state_partial: "entrouvert", state_unknown: "inconnu",
  space: "Espace", connections: "Liaisons", connectTo: "Relier à…", noConnections: "Pas encore relié à autre chose.",
  removeFromPlan: "Remettre dans la liste", deleteZone: "Supprimer cette zone",
  link: "Liaison", separations: "Ce qui les sépare", addSeparation: "+ Ajouter une séparation", removeLink: "Supprimer cette liaison", removeSep: "Retirer",
  sensor: "Capteur d'ouverture", noSensor: "Aucun capteur", sensorsHere: "Portes, fenêtres et volets des deux pièces", sensorsAll: "Rien trouvé dans ces pièces : tous les capteurs de la maison sont listés",
  noSensorNeeded: "Pas de capteur nécessaire : cela ne change jamais.",
  shutter: "Volet devant (facultatif)", noShutter: "Aucun volet", shutterShort: "volet", shutterHint: "Volets roulants et stores des deux pièces : un volet fermé devant une fenêtre fermée arrête davantage le son.",
  close: "Fermer", list: "Liste", plan: "Plan",
};

const LANGS: Record<string, Dict> = { en: EN as unknown as Dict, fr: FR };

export function translator(language: string) {
  const dict = LANGS[language.toLowerCase().split("-")[0]] ?? LANGS.en;
  return (key: Key, vars: Record<string, string | number> = {}): string => (dict[key] ?? LANGS.en[key]).replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ""));
}
export type T = ReturnType<typeof translator>;
