# Leaflet 1.9.4 — copie embarquée

Fichiers repris **tels quels** depuis
`https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/` :

| Fichier | Taille |
|---|---|
| `leaflet.js` | 147 552 o |
| `leaflet.css` | 14 806 o |
| `images/layers.png` | 696 o |
| `images/layers-2x.png` | 1 259 o |
| `images/marker-icon.png` | 1 466 o |

## Pourquoi une copie plutôt qu'un CDN

Les cartes produites sont des **livrables envoyés par mail**, ouverts sur des
réseaux qu'on ne maîtrise pas. Tant que Leaflet venait d'un CDN, un proxy
d'entreprise qui le bloque — ou une panne du CDN — rendait la carte inutilisable :
page blanche et `Uncaught ReferenceError: L is not defined`. Embarquer la
bibliothèque supprime cette classe de pannes.

Effet de bord utile : la carte devient prévisualisable dans les aperçus qui
restreignent les scripts externes.

Reste tributaire d'Internet : le **fond de carte** (tuiles IGN / Esri), par
nature. Sans réseau, la carte s'ouvre et reste pleinement utilisable — photos,
cônes, bulles, édition — avec un fond gris.

## Version figée

La version est volontairement épinglée dans le dépôt : une mise à jour amont ne
peut plus modifier le comportement d'une carte **déjà diffusée**. Pour changer de
version, remplacer les fichiers ci-dessus et mettre à jour ce document.

## Licence

Leaflet est publié sous licence **BSD-2-Clause** (© Volodymyr Agafonkin,
CloudMade). Le texte de licence figure en tête de `leaflet.js`, conservé intact.
L'attribution « Leaflet » reste affichée dans le coin de chaque carte.
