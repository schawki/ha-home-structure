# Home Structure

Une intégration Home Assistant qui décrit **la structure de votre logement** : quels espaces sont voisins, ce qui les sépare (espace ouvert, ouverture sans porte, porte, porte vitrée, fenêtre, volet, mur plein) et ce que disent les capteurs d'ouverture à l'instant.

Elle ne fait rien du son, de la lumière, de la chaleur ni de la présence. Elle garde seulement la description du logement, pour que n'importe quelle intégration ou automatisation puisse demander « le salon est-il ouvert sur l'entrée ? » au lieu que chacune vous demande de décrire votre logement. [Sound Recognition](https://github.com/schawki/sound-recognition-ha) est la première à s'en servir.

## Installation

1. HACS → Dépôts personnalisés → `https://github.com/schawki/ha-home-structure` (catégorie : Intégration) → installer, redémarrer Home Assistant.
2. Paramètres → Appareils et services → Ajouter une intégration → **Home Structure**.
3. Cliquez sur **Configurer** pour décrire votre logement.

## Le modèle

- **Espaces.** Une pièce est une pièce (area) Home Assistant. Une **zone** est un espace qui n'est pas une pièce ordinaire, et elle peut être :
  - *dans votre logement* : jardin, balcon, terrasse, cour, garage ;
  - *en dehors* : hall ou palier, cage d'escalier, partie commune de l'immeuble, rue, logement voisin.

  Si une zone existe déjà comme pièce Home Assistant (un jardin avec une caméra, un hall d'immeuble avec une sonnette), vous donnez un type à cette pièce et indiquez si elle fait partie du logement ; ses appareils restent en place. Les zones sans pièce (la rue, le voisin) sont créées dans Home Structure.
- **Liaisons.** Deux espaces voisins sont reliés. Deux espaces sans liaison ne sont pas adjacents.
- **Séparations.** Une liaison a une ou plusieurs séparations, chacune d'un type :

  | Type | Sens | État |
  |---|---|---|
  | `open_space` (espace ouvert) | aucune séparation (un salon et une entrée en un seul espace) | toujours ouvert |
  | `opening` (ouverture) | un passage sans porte | toujours ouvert |
  | `door` (porte) | une porte | selon son capteur |
  | `glass_door` (porte vitrée) | porte vitrée ou coulissante | selon son capteur |
  | `grille` (grille / porte grillagée) | grille de sécurité ou porte grillagée : une barrière physique qui n'arrête presque pas le son | selon son capteur s'il y en a un |
  | `window` (fenêtre) | une fenêtre | selon son capteur |
  | `shutter` (volet) | volet roulant ou store | selon son volet (cover) |
  | `wall` (mur) | un mur plein : adjacent, sans passage | toujours fermé |

  Une porte et une porte vitrée entre les deux mêmes espaces sont deux séparations d'une seule liaison.
- **Capteurs.** Une séparation qui peut changer peut avoir un `binary_sensor` (contact de porte ou de fenêtre) ou un `cover` (volet). Son état devient `open`, `closed`, `partial` (un volet entre 1 et 99 %, ou en mouvement) ou `unknown` (pas de capteur, ou il ne répond pas).
- **Un volet devant une fenêtre ou une porte.** Une porte, une porte vitrée ou une fenêtre peut aussi indiquer le `cover` du volet roulant ou du store placé devant elle (champ `shutter`). La séparation garde son propre état et signale le volet à côté, dans les attributs `shutter`, `shutter_state` et `shutter_position` : un consommateur peut combiner les deux. Le type `shutter` seul ne sert que pour un volet qui est toute la séparation.

## Configuration

Ouvrez **Home Structure** dans la barre latérale. Vous voyez un plan que vous organisez vous-même ; tout ce que vous faites est enregistré immédiatement et annulable :

1. **Ajouter vos pièces.** La colonne de gauche liste les pièces Home Assistant qui ne sont pas encore sur le plan. Cliquez sur **Tout ajouter** (elles sont rangées en une colonne par étage, que vous déplacez ensuite), ou glissez ou cliquez seulement celles que vous voulez. Les pièces laissées dans la colonne sont ignorées. Rien n'est deviné d'après les noms.
2. **Les déplacer** où vous voulez, pour que le plan ressemble à votre logement. **Réorganiser** remet tout en ordre par étage.
3. **Les relier.** Glissez la poignée ● d'une pièce sur la pièce voisine. Cliquez sur le lien pour dire ce qui les sépare (espace ouvert, porte, porte vitrée, fenêtre, volet, mur…), choisissez le capteur d'ouverture parmi les portes, fenêtres et volets des deux pièces, choisissez le volet placé devant une fenêtre ou une porte s'il y en a un, et ajoutez une deuxième séparation s'il y en a une autre. Le lien affiche l'état en direct de chaque séparation (ouvert, fermé, partiel).
4. **Ajouter l'extérieur** avec **+ Zone** : jardin, balcon, hall, cage d'escalier, rue, logement voisin… Le type décide si la zone fait partie du logement ; modifiable. Une pièce peut aussi devenir un type de zone (une pièce « Garage » peut être marquée garage), et une pièce peut être scindée en créant une zone à côté.

Sur un écran étroit, le plan devient une liste avec les mêmes possibilités. Les anciens écrans (*Configurer* sur l'intégration) fonctionnent toujours et modifient les mêmes données.

## Ce que vous obtenez

- **Un capteur par séparation**, avec l'état ouvert, fermé ou partiel (inconnu quand il ne peut pas être lu) et les attributs `type`, `space_a`, `space_b`, `name_a`, `name_b`, `sensor` et `position`. Utilisable dans les automatisations, les modèles et les tableaux de bord.
- **Un service** `home_structure.get_structure`, qui renvoie toute la structure avec les états actuels, pour les intégrations (voir l'exemple dans le [README anglais](../README.md)).

## Langues

L'anglais est la référence, le français est inclus. Pour ajouter une langue, voir [CONTRIBUTING.md](../CONTRIBUTING.md) : un seul fichier à copier et traduire.

## Licence

MIT.
