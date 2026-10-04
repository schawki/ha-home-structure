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
  | `window` (fenêtre) | une fenêtre | selon son capteur |
  | `shutter` (volet) | volet roulant ou store | selon son volet (cover) |
  | `wall` (mur) | un mur plein : adjacent, sans passage | toujours fermé |

  Une porte et une porte vitrée entre les deux mêmes espaces sont deux séparations d'une seule liaison.
- **Capteurs.** Une séparation qui peut changer peut avoir un `binary_sensor` (contact de porte ou de fenêtre) ou un `cover` (volet). Son état devient `open`, `closed`, `partial` (un volet entre 1 et 99 %, ou en mouvement) ou `unknown` (pas de capteur, ou il ne répond pas).

## Ce que vous obtenez

- **Un capteur par séparation**, avec l'état ouvert, fermé ou partiel (inconnu quand il ne peut pas être lu) et les attributs `type`, `space_a`, `space_b`, `name_a`, `name_b`, `sensor` et `position`. Utilisable dans les automatisations, les modèles et les tableaux de bord.
- **Un service** `home_structure.get_structure`, qui renvoie toute la structure avec les états actuels, pour les intégrations (voir l'exemple dans le [README anglais](../README.md)).

## Langues

L'anglais est la référence, le français est inclus. Pour ajouter une langue, voir [CONTRIBUTING.md](../CONTRIBUTING.md) : un seul fichier à copier et traduire.

## Licence

MIT.
