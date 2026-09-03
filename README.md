# Carte des photos de terrain

Génère une carte HTML interactive à partir d'un lot de photos géolocalisées :
chaque photo est positionnée avec sa direction de prise de vue.

## Utilisation

1. Photographier sur le terrain avec une application qui géolocalise
   (GPS Map Camera de préférence : sa vignette carte fournit aussi la direction).
2. Déposer les photos dans l'application — **directement** (sélection multiple)
   ou dans un **`.zip`**, les deux modes cohabitent. **Le dépôt ne traite rien** :
   on peut déposer en plusieurs fois, le compteur indique ce qui est en attente.
3. Cliquer **« Traiter les photos »** pour lancer l'analyse.
4. Vérifier les directions détectées, puis générer la carte.
5. Ouvrir la carte et, en mode édition (**✏️**), **calibrer la boussole** sur le
   fond satellite et ajuster les directions : c'est là qu'un décalage se juge.

L'application ne produit que des directions **brutes**, telles que détectées.
Toute retouche — calibration globale, correction d'une photo — se fait ensuite
dans la carte HTML : un décalage de boussole ne se voit qu'en regardant les cônes
sur le fond satellite (voir *Carte éditable*).

### Compléter un lot déjà traité

Déposer de nouvelles photos après un premier traitement ouvre deux choix :

| Bouton | Effet |
|---|---|
| **➕ Ajouter au lot** | Les nouvelles photos s'ajoutent aux résultats. Les photos déjà traitées ne sont **jamais réanalysées** ; calibration et saisies manuelles sont conservées et suivent leur photo malgré le retri chronologique. |
| **♻️ Remplacer le lot** | On repart de zéro : seules les nouvelles photos sont traitées, calibration et saisies manuelles remises à neuf. |

Le suivi se fait fichier par fichier (nom + taille) dans `st.session_state`, et non
par une signature globale du dépôt : c'est ce qui permet d'ajouter sans tout
relancer. Retirer un fichier du déposoir le rend à nouveau traitable.

Aucun octet d'image n'est conservé en mémoire : les photos sont écrites une fois
dans un dossier temporaire et seul leur chemin est gardé. L'image de la carte
n'est encodée qu'à la génération, quand la qualité choisie est connue.

### Limite de poids d'un lot

Décoder tout un lot d'un coup gonfle la RAM ; au-delà de ce que l'hébergement
offre (~1 Go sur le plan gratuit Streamlit Cloud), l'application planterait et
demanderait un redémarrage manuel. Deux garde-fous, tous deux en Mo — le poids,
pas le nombre de photos, car 100 photos de téléphone (~3 Mo) pèsent moins en RAM
que 30 photos de drone (~15 Mo) :

- **Par lot** : `app.SEUIL_LOT_MO` (**350 Mo**). Au-delà, le dépôt affiche un
  message et le bouton *Traiter* est désactivé — **avant tout décodage**, calculé
  sur les octets déjà reçus (`.size` de chaque fichier). Un indicateur discret
  (« Lot : 180 / 350 Mo ») laisse anticiper. La parade est de **découper** :
  déposer une première partie, la traiter, puis ajouter le reste en mode *Ajouter*.
  Le déposoir étant vidé après chaque traitement, seul le base64 réduit
  (~0,4 Mo/photo) subsiste d'un lot à l'autre : le découpage contourne donc
  réellement la limite mémoire.
- **Par fichier** : `.streamlit/config.toml` → `maxUploadSize = 350`, aligné sur
  `SEUIL_LOT_MO`. Streamlit refuse un fichier plus lourd **côté navigateur**,
  avant tout envoi : ses octets n'atteignent jamais la RAM du serveur. C'est
  pourquoi on ne relève **pas** cette valeur pour « laisser monter » un gros ZIP —
  le simple upload de ses octets bruts saturerait la mémoire. L'app acceptant des
  ZIP (un site entier en un fichier), un plafond trop bas bloquerait des ZIP
  légitimes ; 350 Mo est le compromis.

Conséquence assumée : un **ZIP unique** au-delà de 350 Mo est refusé par le
message générique de Streamlit (non personnalisable, puisqu'il agit avant le code
de l'app). Une consigne affichée en permanence sous le déposoir explique la
marche à suivre en amont : faire plusieurs ZIP plus petits, ou déposer les photos
directement en plusieurs fois. Le message personnalisé « Lot trop volumineux »,
lui, sert aux dépôts de **plusieurs fichiers** dont la somme dépasse le seuil.

`SEUIL_LOT_MO` est un point de départ à affiner empiriquement selon la RAM
réellement disponible.

### Compléter une carte existante

Une carte HTML déjà produite peut être **rechargée pour y ajouter des photos**,
sans rien perdre de ce qui y a été édité dans le navigateur (commentaires, noms,
ordre, corbeille, calibration, directions figées). En tête d'interface, choisir
*Compléter une carte existante* fait apparaître d'abord l'uploader HTML, puis
celui des photos.

Le bloc `#donnees-carte` fait foi : il est relu, enrichi des points des photos
absentes, puis le HTML est réémis depuis cet objet. Les photos déjà présentes
sont dédoublonnées sur le couple **(nom de fichier, date)** et ne sont ni
retraitées ni ré-encodées — leur base64 est repris tel quel. La calibration de la
carte s'applique aussi aux directions des nouvelles photos. Le **titre** est
pré-rempli avec celui de la carte importée et reste modifiable (pour dater une
nouvelle version) ; note, calibration, seuil de précision et fonds de carte sont
conservés tels quels.

Deux limites à connaître : une photo **renommée** dans l'éditeur a perdu son nom
de fichier et sera réajoutée si on la redépose ; une carte réenregistrée depuis le
seul navigateur (bouton 💾) garde son `zoom_max` d'origine tant qu'elle n'est pas
repassée par l'application.

## Formats acceptés

JPEG, PNG, WEBP, TIFF et **HEIC** (format par défaut des iPhone), ainsi que les
ZIP contenant ces images.

## Position et direction : deux cascades

**Position** (`lecture_photo.lire_photo`)

1. Coordonnées GPS des **métadonnées EXIF** → source « EXIF ».
2. Sinon, **texte incrusté dans l'image** lu par OCR → source « OCR ».
   Certaines applications iPhone (bandeau « Work Progress ») n'écrivent pas
   l'EXIF : les coordonnées ne figurent que dans le bandeau.
3. Sinon, photo écartée avec le motif « position introuvable ».

Un **garde-fou géographique** s'applique aux deux sources : seule une position en
France métropolitaine (41 ≤ lat ≤ 51,6 et −5,5 ≤ lon ≤ 9,8) est acceptée. Une
coordonnée hors bornes est rejetée plutôt que placée au mauvais endroit — à
élargir dans `ocr_position.BORNES_FRANCE` en cas de mission hors métropole.

**Direction**

1. Cap des métadonnées (`GPSImgDirection`, écrit par les iPhone, Open Camera…)
   → source « EXIF ».
2. Sinon, cône bleu de la vignette GPS Map Camera → source « Vignette ».
3. Sinon, pas de direction : la photo est placée sans cône (ce n'est pas une
   erreur — un drone n'en fournit aucune) → source « — ».

Les deux provenances sont affichées dans le tableau de vérification, colonnes
**Source pos.** et **Source cap**.

### Précision de la position

Certains appareils écrivent dans l'EXIF l'incertitude de leur fixation GPS
(`GPSHPositioningError`). Elle est reprise dans la colonne **Précision (m)** et,
au-delà de `lecture_exif.SEUIL_PRECISION_M` (**20 m**), la photo est signalée en
haut de page et marquée ⚠️ dans le tableau. Le seuil est calé sur l'échelle d'une
visite de site : au-delà de 20 m, on n'est plus sûr d'être sur la bonne parcelle.

Deux règles à garder en tête :

- **Champ absent = inconnu, pas mauvais.** La plupart des applications ne
  l'écrivent pas ; la colonne reste alors vide et rien n'est signalé.
- **Signalement, jamais exclusion.** Une photo imprécise reste placée sur la
  carte : sa position peut rester utile, c'est au chargé de projet de juger.

Un iPhone en bonne réception annonce environ 5 m ; une fixation dégradée peut
annoncer plusieurs milliers de mètres — cas réellement rencontré, à l'origine
d'une photo placée à 4 km de son emplacement.

### Ajouter un format de coordonnées

Les formats reconnus par l'OCR sont déclarés dans `ocr_position.FORMATS_COORD`,
une liste de `(nom, fonction)`. Chaque fonction reçoit le texte OCR et retourne
`(lat, lon)` ou `None` ; les formats sont essayés dans l'ordre et le premier
résultat qui passe le garde-fou est retenu.

Prendre en charge une nouvelle application = écrire une fonction et ajouter une
ligne à la liste. Rien d'autre à modifier. Deux formats sont fournis :

| Nom | Exemple | État |
|---|---|---|
| `decimal` | `Lat 48.508951° Long 1.232363°`, `Latitude: 48,4459 Longitude: 4,5031` | validé sur photos réelles |
| `dms` | `48°30'32.1"N 1°13'56"E` | **à revalider sur cas réel** (testé sur texte synthétique seulement) |

Cas connu non couvert : cardinal placé avant les chiffres (`N 48° 26' 45"`).

## Calibration de la boussole

Un téléphone mal calibré décale toutes les directions du même angle (couramment
30 à 40°). Cette correction ne se fait **pas** dans Streamlit mais **dans la carte
HTML, en mode édition** : un décalage de boussole ne se juge qu'en voyant les
cônes sur le fond satellite, en vérifiant s'ils pointent vers les bons éléments
du paysage. L'application, elle, ne fournit que les directions brutes détectées.

Dans l'éditeur de la carte, deux niveaux de réglage :

- **Calibration globale** — curseur, boutons ±5°, ou déduction depuis une photo
  repère (indiquer sa direction réelle, ou viser sur la carte) : l'écart est
  appliqué à tout le lot.
- **Correction d'une photo** — direction saisie ou visée à la main. Une direction
  ainsi figée ne suit plus la calibration globale.

La règle du cap est unique et appliquée partout (Python comme JavaScript) :
`cap_manuel` s'il existe, sinon `cap_brut + offset`, sinon pas de cône. La
calibration appliquée est rappelée dans la carte, pour que le lecteur sache que
les directions ont été retouchées.

Le côté Streamlit conserve seulement un **aperçu en rose des vents** dans
l'expander *Vérifier visuellement une photo* : il ne sert qu'à valider la
**détection** (le cône dessiné doit correspondre à celui de la vignette
incrustée), pas à régler quoi que ce soit.

Pour éviter le problème à la source : sur le terrain, ouvrir Google Maps, toucher
le point bleu, choisir *Étalonner la boussole* et dessiner un 8 en l'air.

Le fichier HTML produit est autonome : il s'ouvre par double-clic et peut être
envoyé par mail.

### Ce que « autonome » veut dire exactement

Sont **embarqués dans le fichier** : les photos (base64) et **Leaflet lui-même**
— bibliothèque, feuille de style et ses trois images, en `data:` URI (voir
[`vendor/leaflet-1.9.4/PROVENANCE.md`](vendor/leaflet-1.9.4/PROVENANCE.md)).
La carte ne fait donc **aucune requête vers un CDN**.

C'est délibéré : ces cartes sont des livrables ouverts sur des réseaux qu'on ne
maîtrise pas. Tant que Leaflet venait d'un CDN, un proxy d'entreprise qui le
bloquait — ou une panne — donnait une page blanche et
`Uncaught ReferenceError: L is not defined`. Cette classe de pannes a disparu.

Reste tributaire d'Internet, par nature : le **fond de carte** (tuiles IGN /
Esri). Sans réseau, la carte s'ouvre et reste pleinement utilisable — photos,
cônes, bulles, édition, enregistrement — sur un fond gris.

Le fichier réenregistré depuis le navigateur reste tout aussi autonome :
`documentComplet()` relit les blocs Leaflet depuis la page et les réémet, comme
il le fait déjà pour la feuille de style et le script de la carte.

## Carte éditable (format version 3)

La carte s'ouvre en consultation. Le bouton **✏️** du panneau active le mode
édition, où l'on peut, sans aucun outil ni serveur :

- renommer un point et lui ajouter un **commentaire** (repris dans la popup, le
  panneau et la visionneuse plein écran) ;
- **réordonner** les points (↑ / ↓) — la numérotation des marqueurs suit ;
- **masquer** une photo : elle quitte la carte et le panneau mais reste dans le
  fichier, listée en **corbeille** avec un bouton *Rétablir* ;
- modifier le **titre** de la carte.

Deux boutons d'enregistrement produisent un nouveau fichier HTML :

| Bouton | Contenu |
|---|---|
| 💾 **Enregistrer** | Toutes les modifications, photos masquées comprises (conservées en réserve) |
| 📦 **Enregistrer en version épurée** | Idem sans les photos masquées — fichier allégé pour envoi, après confirmation |

Rien n'est sauvegardé automatiquement : le fichier doit être réenregistré avant
fermeture. Aucun `localStorage` n'est utilisé — les modifications voyagent avec
le fichier, ce qui est le but.

### Comment l'enregistrement fonctionne

L'état vit dans le bloc `<script id="donnees-carte" type="application/json">`,
jamais dans le DOM. À l'enregistrement, la page **reconstruit le document
entier** à partir de ce bloc, du squelette (`<template id="squelette-carte">`),
de la feuille de style et du script — tous relus depuis la page elle-même.

Conséquence : un fichier réenregistré est structurellement identique à un fichier
fraîchement généré par Python. Il se rouvre, se réédite et se retransmet sans
limite, sans distinction entre « original » et « déjà édité ». Vérifié : deux
cycles d'enregistrement successifs sans modification donnent des fichiers
**identiques octet pour octet**.

L'en-tête porte `<meta name="carte-photos-version" content="3">` et le bloc JSON
contient le même numéro de version. Le format de ce bloc est documenté en tête de
`generation_html.py` — c'est lui qui **fait foi** pour le réimport (voir
*Compléter une carte existante*), pas la structure HTML. Une carte au format 2 est
convertie à l'ouverture comme au réimport, sans changer d'apparence
(`cap_brut = cap`, `cap_manuel = null`, `offset = 0`).

### Alerte de précision dans la carte

Une photo dont l'incertitude GPS dépasse `SEUIL_PRECISION_M` porte l'avertissement
« ⚠️ Position peu fiable — ±N m » dans sa popup et un repère ⚠️ dans le panneau.
Le marqueur, lui, reste identique aux autres : le cône est déjà porteur de sens,
le surcharger nuirait à la lecture. Le champ `precision_m` voyage dans les données
pour que l'alerte survive au réenregistrement.

### Photos prises depuis un même emplacement

Plusieurs déclenchements depuis un même point de station donnent des marqueurs
**superposés** : un seul est cliquable, les autres sont inaccessibles à la souris.
Le cas est invisible à l'œil quand les photos **n'ont pas de cône** — rien ne
distingue alors une pile d'un marqueur isolé.

Deux repères le traitent, sans jamais déplacer les points :

- **Compteur sur le marqueur** — « ×3 » tant que les marqueurs se recouvrent.
  Écrit « ×N » et non « N » pour ne pas se confondre avec le numéro de la photo.
  **Un seul compteur par groupe**, porté par le marqueur le plus au sud, celui
  que Leaflet dessine au-dessus : en afficher un par membre donnait autant de
  pastilles que de photos empilées — deux « ×2 » pour une unique paire, illisible
  et contredit par les marqueurs bien visibles à côté.
- **Navigateur dans la bulle** — « ‹ 2/3 photos superposées › » pour feuilleter
  le groupe sans fermer la bulle. Disponible **en consultation** : c'est de la
  lecture, pas une retouche.

Le critère est une distance **à l'écran** (`TOLERANCE_GROUPE_PX`, 20 px — la
largeur de la pastille rouge, liseré compris), pas au sol, et il est **recalculé
à chaque zoom**. En deçà, les pastilles se confondent et l'une masque réellement
l'autre ; au-delà, chaque marqueur se voit et se clique, un compteur n'y
signalerait qu'un empêchement imaginaire. C'est essentiel : un seuil en mètres
serait trompeur — une fois zoomé, les photos se séparent visuellement et un
compteur figé laisserait croire que chacune en cache encore d'autres. En zoomant,
les groupes se scindent puis les compteurs disparaissent d'eux-mêmes.

Corollaire : seules les **parties dessinées** du marqueur captent le clic
(`pointer-events`). Sans cela, sa boîte transparente de 64×64 masquerait ses
voisins bien avant qu'ils ne se recouvrent, et le compteur serait en retard sur
ce que l'utilisateur voit.

Le choix d'écarter les marqueurs en éventail (*spiderfy*) a été écarté : il
déplacerait les marqueurs hors de leurs vraies coordonnées, ce qui n'est pas
acceptable sur un rapport de visite qui fait office de preuve. Le problème n'est
pas la visibilité mais l'accès au clic — c'est donc l'accès qui est corrigé.

À noter : le panneau latéral donne **déjà** accès à n'importe quelle photo, même
masquée derrière une autre — cliquer sa vignette ouvre sa bulle.

## Lancement en local

```bash
pip install -r requirements.txt
streamlit run app.py
```

**Tesseract doit en plus être installé sur la machine** : `pytesseract` n'est
qu'un pilote, le moteur OCR est un programme séparé.

- Windows : installeur [UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki)
  (cocher l'ajout au `PATH`) ;
- macOS : `brew install tesseract` ;
- Linux : `sudo apt-get install tesseract-ocr`.

Seul le pack de langue `eng` est nécessaire (les coordonnées sont numériques).
Sans Tesseract, l'application démarre quand même et affiche un avertissement :
les photos géolocalisées par EXIF restent traitées, seules celles dont la
position n'existe que dans le bandeau incrusté sont écartées.

## Déploiement Streamlit Community Cloud

`packages.txt` installe `tesseract-ocr`, indispensable à l'OCR en ligne : sans ce
fichier, la lecture des positions incrustées échoue sur le Cloud.

`opencv-python-headless` évite la dépendance système `libGL` qui fait échouer
`opencv-python` sur le Cloud.

`.streamlit/config.toml` fixe la limite d'envoi par fichier à un plafond
**aligné sur la RAM**, au lieu des 200 Mo par défaut :

```toml
[server]
maxUploadSize = 350
```

Ce n'est ni une simple extension ni une réduction, mais un plafond calé sur ce
que la mémoire (~1 Go, plan gratuit) peut encaisser : assez haut pour laisser
passer un ZIP de site réaliste (200 Mo aurait bloqué des ZIP légitimes), assez
bas pour qu'un fichier surdimensionné soit refusé côté navigateur avant de
saturer la RAM. Voir *Limite de poids d'un lot* pour le raisonnement complet et
le second garde-fou, par lot cette fois (`app.SEUIL_LOT_MO`).

## Structure

| Fichier | Rôle |
|---|---|
| `app.py` | Interface Streamlit |
| `formats_images.py` | Extensions acceptées et enregistrement du décodeur HEIC |
| `lecture_photo.py` | Cascades de lecture : position (EXIF → OCR), cap (EXIF → vignette) |
| `lecture_exif.py` | Position GPS, date, cap EXIF |
| `ocr_position.py` | Lecture OCR de la position incrustée + formats de coordonnées |
| `detection_cap.py` | Détection du cône bleu dans la vignette |
| `apercu_boussole.py` | Rose des vents (image Pillow) affichée pendant la calibration |
| `generation_html.py` | Construction de la carte Leaflet, et relecture/complétion d'une carte existante (réimport) |

## Réglages utiles

- `detection_cap.SEUIL_CONFIANCE` : seuil au-delà duquel une direction est jugée fiable.
- L'aperçu est dessiné avec Pillow, non en SVG : Streamlit filtre les balises
  `<svg>` passées à `st.html()`, alors que `st.image()` affiche un objet Pillow
  de façon garantie.
- `apercu_boussole.ORANGE` / `ROUGE` : couleurs du cône et de la pastille. Elles doivent
  rester identiques à celles de `generation_html.py` pour que l'aperçu corresponde
  à la carte finale.
- `detection_cap.RAYON_CONE` : rayon d'analyse du cône (en hauteurs de marqueur).
  Ne pas dépasser 4 : au-delà, le masque sort de la vignette.
- `ocr_position.FORMATS_COORD` : formats de coordonnées reconnus par l'OCR (voir
  plus haut pour en ajouter un).
- `ocr_position.BORNES_FRANCE` : garde-fou géographique.
- La hauteur de la carte repose sur la chaîne `html, body, #app, #conteneur` en
  `height:100%`. **Ne pas insérer d'élément dans cette chaîne sans lui donner de
  hauteur** : Leaflet se réduirait alors à la hauteur du panneau, laissant une
  bande grise. Un `ResizeObserver` sur `#carte` rattrape tout changement de mise
  en page (bascule édition, corbeille, redimensionnement) par `invalidateSize()`.
- `lecture_exif.SEUIL_PRECISION_M` : incertitude GPS au-delà de laquelle une photo
  est signalée (elle reste placée).
- `app.SEUIL_LOT_MO` : poids maximal d'un lot déposé en une fois (garde-fou
  mémoire) ; complété par `maxUploadSize` dans `.streamlit/config.toml` pour le
  plafond par fichier (voir *Limite de poids d'un lot*).
- `TOLERANCE_GROUPE_PX` (JavaScript de la carte) : distance **à l'écran** (20 px,
  la largeur de la pastille) en deçà de laquelle deux marqueurs sont considérés
  superposés — pilote le compteur « ×N » et le navigateur de la bulle. Recalculé
  à chaque zoom. L'augmenter fait apparaître des compteurs sur des marqueurs
  pourtant distincts et cliquables.
- `generation_html.FONDS_DE_CARTE` : fonds disponibles (ortho IGN, Esri, plan IGN).
  Le `zoom_max` de chaque fond est le dernier niveau réellement servi ; au-delà,
  Leaflet agrandit la dernière tuile (flou, jamais gris). L'ortho IGN plafonne à
  **19** (mesuré : 404 dès le niveau 20, partout).
