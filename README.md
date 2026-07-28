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
4. Calibrer la boussole si nécessaire, vérifier les directions, générer la carte.

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

Un aperçu en rose des vents montre en direct, pendant le réglage, le cône orange
et la pastille rouge tels qu'ils apparaîtront sur la carte : le cône gris
pointillé rappelle la direction détectée, l'arc fléché matérialise la rotation
appliquée. Il n'est donc pas nécessaire de générer la carte pour juger du réglage.


Un téléphone mal calibré décale toutes les directions du même angle (couramment
30 à 40°). L'application propose deux façons de corriger l'ensemble du lot :

- **Photo repère** : choisir une photo dont on connaît la direction réelle et
  indiquer celle-ci ; l'écart est déduit et appliqué à toutes les autres.
- **Curseur manuel** : ajuster finement la correction.

Une direction saisie à la main dans le tableau est figée : elle ne suit plus les
variations de la calibration. La correction appliquée est inscrite dans la carte
produite, pour que le lecteur sache que les directions ont été retouchées.

Pour éviter le problème à la source : sur le terrain, ouvrir Google Maps, toucher
le point bleu, choisir *Étalonner la boussole* et dessiner un 8 en l'air.

Le fichier HTML produit est autonome (photos intégrées) : il s'ouvre par
double-clic et peut être envoyé par mail.

## Carte éditable (format version 2)

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

L'en-tête porte `<meta name="carte-photos-version" content="2">` et le bloc JSON
contient le même numéro de version. Le format de ce bloc est documenté en tête de
`generation_html.py` — c'est lui qui fera foi pour le réimport (étape 3), pas la
structure HTML.

### Alerte de précision dans la carte

Une photo dont l'incertitude GPS dépasse `SEUIL_PRECISION_M` porte l'avertissement
« ⚠️ Position peu fiable — ±N m » dans sa popup et un repère ⚠️ dans le panneau.
Le marqueur, lui, reste identique aux autres : le cône est déjà porteur de sens,
le surcharger nuirait à la lecture. Le champ `precision_m` voyage dans les données
pour que l'alerte survive au réenregistrement.

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

Pour accepter des dépôts de plus de 200 Mo, créer `.streamlit/config.toml` :

```toml
[server]
maxUploadSize = 500
```

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
| `generation_html.py` | Construction de la carte Leaflet |

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
- `generation_html.FONDS_DE_CARTE` : fonds disponibles (ortho IGN, Esri, plan IGN).
