"""
generation_html.py — Génération de la carte HTML autoportante et éditable.

Le fichier produit contient les photos encodées en base64 : il est autonome et
peut être envoyé par mail ou déposé sur un serveur sans dossier annexe.
Seuls le fond de carte et la bibliothèque Leaflet sont chargés depuis Internet.

CARTE ÉDITABLE (version 2)
--------------------------
La page s'ouvre en consultation. Un bouton ✏️ bascule en mode édition, où le
chargé de projet peut renommer les points, les commenter, les réordonner, les
masquer et changer le titre, puis réenregistrer un fichier HTML complet.

Principe : tout l'état vit dans le bloc JSON `#donnees-carte`, jamais dans le
DOM. À l'enregistrement, la page reconstruit le document entier à partir de ce
bloc, du squelette (`<template id="squelette-carte">`), de la feuille de style
et du script — tous relus depuis la page elle-même. Un fichier réenregistré est
donc structurellement identique à un fichier fraîchement généré ici : il se
rouvre, se réédite et se retransmet sans limite, sans distinction entre
« original » et « déjà édité ».

FORMAT DU BLOC `#donnees-carte` (lu par l'étape 3 — réimport dans Streamlit)
---------------------------------------------------------------------------
C'est ce bloc qui fait foi, pas le DOM. Objet JSON :

    {
      "version": 2,                  entier, suit <meta name="carte-photos-version">
      "titre": "Visite de site",     titre de la carte, éditable dans la page
      "note": "",                    mention de calibration, "" si aucune
      "seuil_precision_m": 20,       seuil d'alerte de précision GPS, en mètres
      "centre": [lat, lon],          cadrage initial
      "fonds": { ... },              fonds de carte disponibles (cf. FONDS_DE_CARTE)
      "points": [
        {
          "id": 0,                   identifiant stable, jamais réattribué
          "nom": "IMG_0420.HEIC",    nom affiché, éditable
          "lat": 48.7343,
          "lon": 6.6516,
          "cap": 340.0,              direction en degrés, ou null
          "date": "18/06/2026 08:35",texte déjà mis en forme, ou ""
          "commentaire": "",         éditable dans la page
          "masque": false,           true = en corbeille (absent de la carte)
          "ordre": 0,                rang d'affichage, modifiable par ↑ / ↓
          "precision_m": 4260.8,     incertitude GPS annoncée, ou null si inconnue
          "image": "/9j/4AAQ..."     photo en base64 (JPEG), sans en-tête data:
        }
      ]
    }

Le champ `precision_m` voyage avec les données pour que l'alerte « position peu
fiable » survive au réenregistrement comme au réimport.
"""

import base64
import io
import json
from PIL import Image, ImageOps

from lecture_exif import SEUIL_PRECISION_M

# Version du format de fichier. À incrémenter si la structure du bloc
# #donnees-carte change, pour que le réimport sache à quoi il a affaire.
VERSION_CARTE = 2

# Fonds de carte. L'ortho IGN est la plus détaillée sur la France ;
# Esri sert de secours et couvre le monde entier (utile en outre-mer).
FONDS_DE_CARTE = {
    "Ortho IGN": {
        "url": ("https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
                "&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&TILEMATRIXSET=PM"
                "&FORMAT=image/jpeg&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}"),
        "attribution": "IGN-F/Géoportail",
        "zoom_max": 21,
    },
    "Satellite Esri": {
        "url": ("https://server.arcgisonline.com/ArcGIS/rest/services/"
                "World_Imagery/MapServer/tile/{z}/{y}/{x}"),
        "attribution": "Esri, Maxar, Earthstar Geographics",
        "zoom_max": 19,
    },
    "Plan IGN": {
        "url": ("https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
                "&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&STYLE=normal&TILEMATRIXSET=PM"
                "&FORMAT=image/png&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}"),
        "attribution": "IGN-F/Géoportail",
        "zoom_max": 19,
    },
}


def _image_en_base64(chemin, largeur_max, qualite):
    """Redimensionne une photo et la retourne en base64 prête à insérer en HTML.

    ImageOps.exif_transpose applique la rotation EXIF : sans cela, les photos
    prises en portrait s'afficheraient couchées.
    """
    with Image.open(chemin) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((largeur_max, largeur_max), Image.LANCZOS)
        tampon = io.BytesIO()
        image.save(tampon, format="JPEG", quality=qualite, optimize=True)
    return base64.b64encode(tampon.getvalue()).decode("ascii")


def _json_pour_html(objet):
    """Sérialise en JSON insérable dans une balise <script>.

    Le « < » est échappé : sans cela, un commentaire contenant « </script> »
    fermerait la balise et casserait le fichier. La page applique exactement la
    même transformation quand elle se réenregistre.
    """
    return json.dumps(objet, ensure_ascii=False).replace("<", "\\u003c")


def _echapper(texte):
    """Échappement HTML minimal, identique à celui du JavaScript de la page."""
    return (str(texte).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def construire_carte(photos, titre, largeur_max=1600, qualite=80, note="",
                     seuil_precision=SEUIL_PRECISION_M):
    """Construit le HTML complet de la carte.

    photos : liste de dictionnaires contenant au minimum
             chemin, nom, lat, lon, cap (cap peut valoir None) ; precision_m
             est repris quand il est présent.
    note   : mention affichée dans le panneau latéral, utilisée notamment pour
             tracer la correction de boussole appliquée.
    Retourne la chaîne HTML.
    """
    points = []
    for index, photo in enumerate(photos):
        points.append({
            "id": index,
            "nom": photo["nom"],
            "lat": photo["lat"],
            "lon": photo["lon"],
            "cap": photo.get("cap"),
            "date": photo.get("date_texte", ""),
            "commentaire": photo.get("commentaire", ""),
            "masque": False,
            "ordre": index,
            "precision_m": photo.get("precision_m"),
            "image": _image_en_base64(photo["chemin"], largeur_max, qualite),
        })

    latitudes = [p["lat"] for p in points]
    longitudes = [p["lon"] for p in points]
    centre = [sum(latitudes) / len(latitudes), sum(longitudes) / len(longitudes)]

    donnees = {
        "version": VERSION_CARTE,
        "titre": titre,
        "note": note,
        "seuil_precision_m": seuil_precision,
        "centre": centre,
        "fonds": FONDS_DE_CARTE,
        "points": points,
    }

    return (_GABARIT.replace("__TITRE__", _echapper(titre))
                    .replace("__DONNEES__", _json_pour_html(donnees)))


# Le gabarit utilise des marqueurs __XXX__ plutôt que le formatage Python,
# pour ne pas avoir à échapper les nombreuses accolades du CSS et du JavaScript.
#
# ATTENTION : la structure ci-dessous (ordre et découpage des lignes de l'en-tête,
# identifiants #style-carte / #squelette-carte / #donnees-carte / #script-carte)
# est reproduite à l'identique par la fonction JavaScript documentComplet().
# Modifier l'une sans l'autre ferait diverger le fichier réenregistré.
_GABARIT = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="carte-photos-version" content="2">
<title>__TITRE__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style id="style-carte">
  * { box-sizing: border-box; }
  html, body { margin:0; padding:0; height:100%; font-family:Segoe UI,Roboto,Arial,sans-serif; }
  /* Leaflet exige une hauteur explicite propagée de proche en proche. #app est
     le seul enfant rendu de <body> (le squelette vit dans un <template>, inerte) :
     sans height:100% ici, la chaîne casse et la carte se réduit à la hauteur du
     panneau, laissant une bande grise en bas. */
  #app { height:100%; }
  #conteneur { display:flex; height:100%; }
  #panneau { width:300px; flex-shrink:0; background:#1e2a38; color:#e8eef4;
             overflow-y:auto; display:flex; flex-direction:column; min-height:0; }
  #entete { display:flex; align-items:flex-start; gap:6px; background:#16202b;
            border-bottom:1px solid #2c3e50; padding:12px 10px 12px 16px; }
  #titre-carte { font-size:15px; margin:0; flex:1; line-height:1.35; outline:none; }
  body.edition #titre-carte { background:#22303f; border:1px dashed #5b7a99;
                              border-radius:3px; padding:3px 5px; }
  #panneau .aide { font-size:11px; color:#93a5b8; padding:10px 16px; line-height:1.5;
                   border-bottom:1px solid #2c3e50; }
  #panneau .note { font-size:11px; color:#ffc46b; padding:9px 16px; line-height:1.5;
                   background:#2a2110; border-bottom:1px solid #2c3e50; }
  .vignette { display:flex; gap:10px; align-items:center; padding:9px 12px; cursor:pointer;
              border-bottom:1px solid #2a3a4a; transition:background .12s; }
  .vignette:hover { background:#27384a; }
  .vignette img { width:54px; height:40px; object-fit:cover; border-radius:3px; flex-shrink:0; }
  .vignette .txt { font-size:11px; line-height:1.4; overflow:hidden; flex:1; }
  .vignette .nom { font-weight:600; white-space:nowrap; overflow:hidden;
                   text-overflow:ellipsis; display:block; }
  .vignette .meta { color:#93a5b8; display:block; }
  .vignette .commentaire { color:#cfe0f0; font-style:italic; display:block; margin-top:2px;
                           overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  /* min-height:0 : sans lui, un enfant flex refuse de descendre sous la hauteur
     de son contenu, ce qui rognerait la carte en disposition colonne (mobile). */
  #carte { flex:1; min-height:0; }
  /* Le cône est dessiné en SVG et pivoté par CSS : il garde une taille
     constante quel que soit le niveau de zoom, contrairement à un polygone. */
  .cone-icone svg { display:block; overflow:visible; }
  .popup-photo { width:270px; cursor:zoom-in; border-radius:3px; display:block; }
  .popup-titre { font-weight:600; font-size:12px; margin:6px 0 2px; }
  .popup-meta { font-size:11px; color:#555; }
  .popup-commentaire { font-size:11px; color:#1e2a38; font-style:italic; margin-top:4px; }
  .leaflet-popup-content { margin:9px 11px; }
  /* Alerte de précision GPS : la position vient d'une fixation dégradée. */
  .alerte { color:#ff9d3c; font-weight:600; display:block; margin-top:2px; }
  .popup-alerte { margin-top:5px; padding:4px 6px; border-radius:3px; font-size:11px;
                  font-weight:600; color:#8a3b00; background:#ffe9d1;
                  border:1px solid #ffb066; }
  /* Barre d'édition, masquée en consultation */
  #btn-mode { background:#2c3e50; color:#e8eef4; border:1px solid #3d556e; border-radius:4px;
              cursor:pointer; font-size:14px; padding:4px 8px; line-height:1.2; }
  #btn-mode:hover { background:#3a5570; }
  #barre-edition, #corbeille, .outils { display:none; }
  body.edition #barre-edition { display:block; }
  body.edition .outils { display:flex; }
  #barre-edition { padding:10px 12px; border-bottom:1px solid #2c3e50; background:#202d3b; }
  #barre-edition .rappel { font-size:11px; color:#ffc46b; line-height:1.45; margin-bottom:8px; }
  #barre-edition button { width:100%; margin-bottom:6px; padding:7px 8px; font-size:12px;
                          border:none; border-radius:4px; cursor:pointer; font-weight:600; }
  #btn-enregistrer { background:#2e7d32; color:#fff; }
  #btn-enregistrer:hover { background:#388e3c; }
  #btn-epurer { background:#37474f; color:#e8eef4; }
  #btn-epurer:hover { background:#455a64; }
  .outils { gap:3px; flex-shrink:0; flex-direction:column; }
  .outils button { background:#2c3e50; color:#e8eef4; border:none; border-radius:3px;
                   cursor:pointer; font-size:11px; padding:2px 5px; line-height:1.3; }
  .outils button:hover { background:#43607d; }
  #corbeille { border-top:1px solid #2c3e50; }
  body.edition #corbeille.remplie { display:block; }
  #corbeille h2 { font-size:11px; text-transform:uppercase; letter-spacing:.06em;
                  color:#93a5b8; margin:0; padding:10px 16px 4px; }
  .masquee { display:flex; align-items:center; gap:8px; padding:6px 12px; font-size:11px;
             color:#93a5b8; border-bottom:1px solid #2a3a4a; }
  .masquee span { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .masquee button { background:#2c3e50; color:#e8eef4; border:none; border-radius:3px;
                    cursor:pointer; font-size:11px; padding:3px 7px; }
  .masquee button:hover { background:#43607d; }
  /* Visionneuse plein écran */
  #visionneuse { position:fixed; inset:0; background:rgba(0,0,0,.93); display:none;
                 z-index:2000; align-items:center; justify-content:center; }
  #visionneuse img { max-width:94%; max-height:88%; object-fit:contain; }
  #vis-legende { position:absolute; bottom:14px; left:0; right:0; text-align:center;
                 color:#fff; font-size:13px; text-shadow:0 1px 4px #000; }
  .vis-btn { position:absolute; background:rgba(255,255,255,.14); color:#fff; border:none;
             cursor:pointer; font-size:26px; padding:14px 18px; border-radius:5px;
             line-height:1; user-select:none; }
  .vis-btn:hover { background:rgba(255,255,255,.28); }
  #vis-prec { left:18px; top:50%; transform:translateY(-50%); }
  #vis-suiv { right:18px; top:50%; transform:translateY(-50%); }
  #vis-fermer { right:18px; top:18px; font-size:22px; }
  /* Fenêtre de saisie (nom + commentaire) */
  #modale { position:fixed; inset:0; background:rgba(0,0,0,.55); display:none;
            z-index:3000; align-items:center; justify-content:center; }
  #modale .boite { background:#fff; border-radius:6px; padding:16px 18px; width:340px;
                   max-width:92%; font-size:13px; color:#1e2a38; }
  #modale h3 { margin:0 0 10px; font-size:14px; }
  #modale label { display:block; font-size:11px; color:#555; margin:8px 0 3px; }
  #modale input, #modale textarea { width:100%; padding:6px 7px; font-size:13px;
                                    border:1px solid #bbc7d3; border-radius:3px;
                                    font-family:inherit; }
  #modale textarea { height:80px; resize:vertical; }
  #modale .actions { display:flex; gap:8px; justify-content:flex-end; margin-top:14px; }
  #modale .actions button { padding:6px 14px; font-size:12px; border:none; border-radius:4px;
                            cursor:pointer; font-weight:600; }
  #modale-valider { background:#2e7d32; color:#fff; }
  #modale-annuler { background:#e0e6ec; color:#1e2a38; }
  @media (max-width:700px) { #conteneur{flex-direction:column;} #panneau{width:100%;height:45%;} }
</style>
</head>
<body>
<template id="squelette-carte"><div id="conteneur">
  <div id="panneau">
    <div id="entete">
      <h1 id="titre-carte"></h1>
      <button id="btn-mode" type="button" title="Passer en mode édition">✏️</button>
    </div>
    <div class="aide">Cliquez sur un point de la carte ou sur une photo de la liste.
      Le cône indique la direction de prise de vue. Le bouton ✏️ permet de modifier
      cette carte (commentaires, noms, ordre, titre) puis de l'enregistrer.</div>
    <div id="note" class="note" hidden></div>
    <div id="barre-edition">
      <div class="rappel">Mode édition. Pensez à <b>Enregistrer</b> avant de fermer :
        les modifications ne sont pas sauvegardées automatiquement.</div>
      <button id="btn-enregistrer" type="button">💾 Enregistrer</button>
      <button id="btn-epurer" type="button">📦 Enregistrer en version épurée</button>
    </div>
    <div id="liste"></div>
    <div id="corbeille"><h2>Corbeille</h2><div id="liste-masquees"></div></div>
  </div>
  <div id="carte"></div>
</div>

<div id="visionneuse">
  <button class="vis-btn" id="vis-prec" type="button">&#10094;</button>
  <img id="vis-image" alt="">
  <button class="vis-btn" id="vis-suiv" type="button">&#10095;</button>
  <button class="vis-btn" id="vis-fermer" type="button">&#10005;</button>
  <div id="vis-legende"></div>
</div>

<div id="modale">
  <div class="boite">
    <h3 id="modale-titre">Modifier la photo</h3>
    <label for="modale-nom">Nom affiché</label>
    <input id="modale-nom" type="text">
    <label for="modale-commentaire">Commentaire</label>
    <textarea id="modale-commentaire" placeholder="Observation, repère, point de vigilance…"></textarea>
    <div class="actions">
      <button id="modale-annuler" type="button">Annuler</button>
      <button id="modale-valider" type="button">Valider</button>
    </div>
  </div>
</div></template>
<div id="app"></div>
<script id="donnees-carte" type="application/json">__DONNEES__</script>
<script id="script-carte">
/* ------------------------------------------------------------------------
   État de la carte
   ------------------------------------------------------------------------
   Tout vit dans DONNEES, relu depuis le bloc JSON #donnees-carte. Les
   éditions modifient DONNEES puis redessinent ; le DOM n'est jamais la
   source de vérité. À l'enregistrement, le document est reconstruit à
   partir de DONNEES, ce qui rend le fichier réenregistré identique en
   structure à un fichier fraîchement généré.
   ------------------------------------------------------------------------ */
const DONNEES = JSON.parse(document.getElementById('donnees-carte').textContent);
const SEUIL_PRECISION = DONNEES.seuil_precision_m;

// Le squelette est inerte dans <template> : Leaflet ne peut donc pas l'altérer,
// et il se recopie tel quel d'un enregistrement à l'autre.
document.getElementById('app').innerHTML =
  document.getElementById('squelette-carte').innerHTML;

let modeEdition = false;
let premierRendu = true;
let courant = 0;              // index dans la liste visible, pour la visionneuse

function echapper(texte) {
  return String(texte === null || texte === undefined ? '' : texte)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function pointsVisibles() {
  return DONNEES.points.filter(p => !p.masque).sort((a, b) => a.ordre - b.ordre);
}

function pointsMasques() {
  return DONNEES.points.filter(p => p.masque).sort((a, b) => a.ordre - b.ordre);
}

function pointParId(id) {
  return DONNEES.points.find(p => p.id === id);
}

function srcImage(p) { return 'data:image/jpeg;base64,' + p.image; }

/* Précision GPS : une valeur absente signifie « inconnue », jamais « mauvaise ».
   Seule une incertitude annoncée au-delà du seuil déclenche l'alerte. */
function precisionDouteuse(p) {
  return p.precision_m !== null && p.precision_m !== undefined
         && p.precision_m > SEUIL_PRECISION;
}

function texteAlerte(p) {
  return 'Position peu fiable — ±' + Math.round(p.precision_m) + ' m';
}

function texteCap(cap) {
  if (cap === null || cap === undefined) return 'direction inconnue';
  const roses = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSO','SO','OSO','O','ONO','NO','NNO'];
  return roses[Math.round(cap / 22.5) % 16] + ' (' + Math.round(cap) + '°)';
}

/* ---------------------------- Carte Leaflet ---------------------------- */

const carte = L.map('carte', { center: DONNEES.centre, zoom: 16 });

// Construction des fonds de carte ; le premier déclaré est affiché par défaut.
const couches = {};
let premier = true;
for (const [nom, f] of Object.entries(DONNEES.fonds)) {
  const couche = L.tileLayer(f.url, {
    attribution: f.attribution, maxNativeZoom: f.zoom_max, maxZoom: 22
  });
  couches[nom] = couche;
  if (premier) { couche.addTo(carte); premier = false; }
}
L.control.layers(couches, null, { position: 'topright' }).addTo(carte);
L.control.scale({ imperial: false }).addTo(carte);

const coucheMarqueurs = L.layerGroup().addTo(carte);
let marqueurs = [];

/* Leaflet mémorise la taille de son conteneur : toute modification de la mise
   en page (bascule édition, ouverture de la corbeille, liste qui s'allonge)
   doit être suivie d'un invalidateSize, faute de quoi il continue de dessiner
   sur l'ancienne taille et laisse une bande grise.
   L'appel est fait deux fois : immédiatement, car c'est le seul qui soit garanti
   (les minuteurs sont ralentis, voire suspendus, tant que l'onglet est masqué —
   et requestAnimationFrame, lui, ne part pas du tout dans ce cas) ; puis en
   différé, pour rattraper une mise en page qui se stabilise après coup (barre de
   défilement du panneau, polices, images). */
function rafraichirCarte() {
  carte.invalidateSize();
  setTimeout(() => carte.invalidateSize(), 0);
}

/* Filet de sécurité principal : ResizeObserver se déclenche dès que la boîte du
   conteneur change — y compris au tout premier calcul de mise en page, cas d'un
   fichier ouvert dans un onglet d'arrière-plan. Contrairement aux minuteurs et à
   requestAnimationFrame, il ne dépend pas de la visibilité de la page.
   invalidateSize ne modifie pas la taille du conteneur : pas de boucle possible. */
if (window.ResizeObserver) {
  new ResizeObserver(() => carte.invalidateSize())
    .observe(document.getElementById('carte'));
}

// Leaflet réagit déjà au redimensionnement de la fenêtre, mais par
// requestAnimationFrame : redimensionner pendant que l'onglet est masqué le
// laisserait sur l'ancienne taille. Ces deux écoutes reprennent la main.
window.addEventListener('resize', rafraichirCarte);
document.addEventListener('visibilitychange', function () {
  if (document.visibilityState === 'visible') rafraichirCarte();
});

/* Icône : un cône orienté (si le cap est connu) surmonté d'une pastille.
   La rotation est appliquée au groupe SVG, autour du centre de l'icône. */
function iconeCone(cap, numero) {
  const T = 64, C = T / 2;
  let cone = '';
  if (cap !== null && cap !== undefined) {
    // Secteur de 50° d'ouverture, sommet au centre, pointant vers le haut.
    const demi = 25 * Math.PI / 180, R = 30;
    const x1 = C + R * Math.sin(-demi), y1 = C - R * Math.cos(-demi);
    const x2 = C + R * Math.sin(demi),  y2 = C - R * Math.cos(demi);
    cone = `<g transform="rotate(${cap} ${C} ${C})">
              <path d="M ${C} ${C} L ${x1.toFixed(1)} ${y1.toFixed(1)}
                       A ${R} ${R} 0 0 1 ${x2.toFixed(1)} ${y2.toFixed(1)} Z"
                    fill="#ff8a00" fill-opacity="0.55"
                    stroke="#ff8a00" stroke-width="1.5"/>
            </g>`;
  }
  return L.divIcon({
    className: 'cone-icone', iconSize: [T, T], iconAnchor: [C, C], popupAnchor: [0, -12],
    html: `<svg width="${T}" height="${T}">${cone}
             <circle cx="${C}" cy="${C}" r="9" fill="#d32f2f" stroke="#fff" stroke-width="2.5"/>
             <text x="${C}" y="${C + 3.5}" text-anchor="middle" font-size="10"
                   font-weight="700" fill="#fff" font-family="Arial">${numero}</text>
           </svg>`
  });
}

function contenuPopup(p, numero) {
  const alerte = precisionDouteuse(p)
    ? `<div class="popup-alerte">⚠️ ${echapper(texteAlerte(p))}</div>` : '';
  const commentaire = p.commentaire
    ? `<div class="popup-commentaire">${echapper(p.commentaire)}</div>` : '';
  return `<img class="popup-photo" src="${srcImage(p)}" data-ouvrir="${numero - 1}">
     <div class="popup-titre">${numero}. ${echapper(p.nom)}</div>
     <div class="popup-meta">${p.date ? echapper(p.date) + '<br>' : ''}${texteCap(p.cap)}</div>
     ${commentaire}${alerte}`;
}

function rendreMarqueurs() {
  coucheMarqueurs.clearLayers();
  marqueurs = [];
  pointsVisibles().forEach((p, i) => {
    const m = L.marker([p.lat, p.lon], { icon: iconeCone(p.cap, i + 1) });
    m.bindPopup(contenuPopup(p, i + 1), { maxWidth: 300 });
    coucheMarqueurs.addLayer(m);
    marqueurs.push(m);
  });
}

/* ------------------------------ Panneau ------------------------------- */

function rendreTitre() {
  document.getElementById('titre-carte').textContent = DONNEES.titre;
  document.title = DONNEES.titre;
  const note = document.getElementById('note');
  note.textContent = DONNEES.note || '';
  note.hidden = !DONNEES.note;
}

function rendreListe() {
  const liste = document.getElementById('liste');
  liste.innerHTML = '';
  pointsVisibles().forEach((p, i) => {
    const ligne = document.createElement('div');
    ligne.className = 'vignette';
    ligne.dataset.rang = i;
    ligne.innerHTML = `
      <img src="${srcImage(p)}" alt="">
      <div class="txt">
        <span class="nom">${i + 1}. ${echapper(p.nom)}</span>
        <span class="meta">${texteCap(p.cap)}</span>
        ${precisionDouteuse(p)
          ? `<span class="alerte" title="${echapper(texteAlerte(p))} — incertitude GPS annoncée par l'appareil">⚠️ ±${Math.round(p.precision_m)} m</span>`
          : ''}
        ${p.commentaire ? `<span class="commentaire">${echapper(p.commentaire)}</span>` : ''}
      </div>
      <div class="outils">
        <button type="button" data-action="monter" data-id="${p.id}" title="Monter">↑</button>
        <button type="button" data-action="descendre" data-id="${p.id}" title="Descendre">↓</button>
        <button type="button" data-action="modifier" data-id="${p.id}" title="Renommer / commenter">✎</button>
        <button type="button" data-action="masquer" data-id="${p.id}" title="Masquer (corbeille)">🗑</button>
      </div>`;
    liste.appendChild(ligne);
  });
}

function rendreCorbeille() {
  const corbeille = document.getElementById('corbeille');
  const contenu = document.getElementById('liste-masquees');
  const masquees = pointsMasques();
  corbeille.classList.toggle('remplie', masquees.length > 0);
  contenu.innerHTML = '';
  masquees.forEach(p => {
    const ligne = document.createElement('div');
    ligne.className = 'masquee';
    ligne.innerHTML = `<span>${echapper(p.nom)}</span>
      <button type="button" data-action="retablir" data-id="${p.id}">Rétablir</button>`;
    contenu.appendChild(ligne);
  });
}

function rendu() {
  rendreTitre();
  rendreListe();
  rendreMarqueurs();
  rendreCorbeille();
  rafraichirCarte();
  if (premierRendu) {
    const visibles = pointsVisibles();
    if (visibles.length > 1) {
      carte.fitBounds(L.latLngBounds(visibles.map(p => [p.lat, p.lon])), { padding: [60, 60] });
    }
    premierRendu = false;
  }
}

/* ------------------------------ Édition -------------------------------- */

function basculerEdition() {
  modeEdition = !modeEdition;
  document.body.classList.toggle('edition', modeEdition);
  const titre = document.getElementById('titre-carte');
  titre.contentEditable = modeEdition ? 'true' : 'false';
  const bouton = document.getElementById('btn-mode');
  bouton.textContent = modeEdition ? '✔️' : '✏️';
  bouton.title = modeEdition ? 'Quitter le mode édition' : 'Passer en mode édition';
  rafraichirCarte();
}

/* Réordonnancement : on échange le rang du point avec celui de son voisin
   visible. Les points masqués gardent leur rang et ne gênent pas le calcul. */
function deplacer(id, sens) {
  const visibles = pointsVisibles();
  const position = visibles.findIndex(p => p.id === id);
  const cible = position + sens;
  if (position < 0 || cible < 0 || cible >= visibles.length) return;
  const a = visibles[position], b = visibles[cible];
  const ordre = a.ordre; a.ordre = b.ordre; b.ordre = ordre;
  rendu();
}

let idEnCours = null;

function ouvrirModale(id) {
  const p = pointParId(id);
  idEnCours = id;
  document.getElementById('modale-titre').textContent = 'Modifier « ' + p.nom + ' »';
  document.getElementById('modale-nom').value = p.nom;
  document.getElementById('modale-commentaire').value = p.commentaire || '';
  document.getElementById('modale').style.display = 'flex';
  document.getElementById('modale-nom').focus();
}

function fermerModale() {
  document.getElementById('modale').style.display = 'none';
  idEnCours = null;
}

function validerModale() {
  const p = pointParId(idEnCours);
  if (p) {
    const nom = document.getElementById('modale-nom').value.trim();
    p.nom = nom || p.nom;
    p.commentaire = document.getElementById('modale-commentaire').value.trim();
  }
  fermerModale();
  rendu();
}

/* --------------------------- Enregistrement ---------------------------- */

/* Reconstruit le document entier. Le squelette, la feuille de style et ce
   script sont relus depuis la page : le fichier produit a donc exactement la
   même structure que celui généré par Python, et reste ré-éditable. */
function documentComplet(donnees) {
  const json = JSON.stringify(donnees).split('<').join('\\u003c');
  return [
    '<!DOCTYPE html>',
    '<html lang="fr">',
    '<head>',
    '<meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    '<meta name="carte-photos-version" content="' + donnees.version + '">',
    '<title>' + echapper(donnees.titre) + '</title>',
    '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">',
    '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"><\/script>',
    '<style id="style-carte">' + document.getElementById('style-carte').textContent + '</style>',
    '</head>',
    '<body>',
    '<template id="squelette-carte">' +
      document.getElementById('squelette-carte').innerHTML + '</template>',
    '<div id="app"></div>',
    '<script id="donnees-carte" type="application/json">' + json + '<\/script>',
    '<script id="script-carte">' + document.getElementById('script-carte').textContent + '<\/script>',
    '</body>',
    '</html>',
    ''
  ].join('\n');
}

function nomFichier(titre) {
  const propre = String(titre).replace(/[^\p{L}\p{N} \-_]/gu, '_').trim();
  return (propre || 'carte') + '.html';
}

function enregistrer(epurer) {
  const points = (epurer ? DONNEES.points.filter(p => !p.masque) : DONNEES.points)
    .slice().sort((a, b) => a.ordre - b.ordre)
    .map((p, i) => Object.assign({}, p, { ordre: i }));   // rangs remis au propre

  if (epurer) {
    const retirees = DONNEES.points.length - points.length;
    if (retirees > 0 && !confirm(
        retirees + ' photo(s) de la corbeille seront définitivement retirées de ce ' +
        'fichier. La carte actuelle, elle, n\'est pas modifiée.\n\nContinuer ?')) return;
  }

  const donnees = Object.assign({}, DONNEES, { points: points });
  const html = documentComplet(donnees);
  const lien = document.createElement('a');
  lien.href = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }));
  lien.download = nomFichier(DONNEES.titre);
  document.body.appendChild(lien);
  lien.click();
  document.body.removeChild(lien);
  setTimeout(() => URL.revokeObjectURL(lien.href), 10000);
}

/* ------------------------------ Écoutes -------------------------------- */

document.getElementById('btn-mode').onclick = basculerEdition;
document.getElementById('btn-enregistrer').onclick = () => enregistrer(false);
document.getElementById('btn-epurer').onclick = () => enregistrer(true);
document.getElementById('modale-annuler').onclick = fermerModale;
document.getElementById('modale-valider').onclick = validerModale;

document.getElementById('titre-carte').addEventListener('input', function () {
  DONNEES.titre = this.textContent.trim();
  document.title = DONNEES.titre;
});

// Un seul écouteur pour toute la liste : les lignes sont redessinées à chaque
// modification, des écouteurs individuels seraient perdus à chaque rendu.
document.getElementById('liste').addEventListener('click', function (evenement) {
  const bouton = evenement.target.closest('button[data-action]');
  const ligne = evenement.target.closest('.vignette');
  if (bouton) {
    evenement.stopPropagation();
    const id = Number(bouton.dataset.id);
    if (bouton.dataset.action === 'monter')    deplacer(id, -1);
    if (bouton.dataset.action === 'descendre') deplacer(id, 1);
    if (bouton.dataset.action === 'modifier')  ouvrirModale(id);
    if (bouton.dataset.action === 'masquer')   { pointParId(id).masque = true; rendu(); }
    return;
  }
  if (ligne) {
    const rang = Number(ligne.dataset.rang);
    const p = pointsVisibles()[rang];
    carte.setView([p.lat, p.lon], Math.max(carte.getZoom(), 17));
    marqueurs[rang].openPopup();
  }
});

document.getElementById('liste-masquees').addEventListener('click', function (evenement) {
  const bouton = evenement.target.closest('button[data-action="retablir"]');
  if (!bouton) return;
  pointParId(Number(bouton.dataset.id)).masque = false;
  rendu();
});

// La photo des popups est recréée à chaque ouverture : écoute déléguée aussi.
document.addEventListener('click', function (evenement) {
  const image = evenement.target.closest('img[data-ouvrir]');
  if (image) ouvrir(Number(image.dataset.ouvrir));
});

/* --------------------------- Visionneuse ------------------------------- */

const vis = document.getElementById('visionneuse');

function ouvrir(rang) {
  const visibles = pointsVisibles();
  if (!visibles.length) return;
  courant = (rang + visibles.length) % visibles.length;
  const p = visibles[courant];
  document.getElementById('vis-image').src = srcImage(p);
  document.getElementById('vis-legende').textContent =
    (courant + 1) + '. ' + p.nom + '  —  ' + texteCap(p.cap) +
    (p.date ? '  —  ' + p.date : '') +
    (precisionDouteuse(p) ? '  —  ⚠️ ' + texteAlerte(p) : '') +
    (p.commentaire ? '  —  ' + p.commentaire : '');
  vis.style.display = 'flex';
}

function decaler(pas) { ouvrir(courant + pas); }

document.getElementById('vis-fermer').onclick = () => vis.style.display = 'none';
document.getElementById('vis-prec').onclick = e => { e.stopPropagation(); decaler(-1); };
document.getElementById('vis-suiv').onclick = e => { e.stopPropagation(); decaler(1); };
vis.onclick = e => { if (e.target === vis) vis.style.display = 'none'; };
document.addEventListener('keydown', e => {
  if (document.getElementById('modale').style.display === 'flex' && e.key === 'Escape') {
    fermerModale();
    return;
  }
  if (vis.style.display !== 'flex') return;
  if (e.key === 'Escape')     vis.style.display = 'none';
  if (e.key === 'ArrowLeft')  decaler(-1);
  if (e.key === 'ArrowRight') decaler(1);
});

rendu();
</script>
</body>
</html>
"""
