"""
lecture_exif.py — Extraction de la position GPS, de la date, du cap et de l'optique.

Le cap EXIF (GPSImgDirection) n'est PAS écrit par GPS Map Camera : il est lu
ici uniquement pour le cas où l'équipe utiliserait une autre application
(iPhone, Open Camera, Solocator...). Quand il est présent, il est prioritaire sur
la détection par analyse d'image, qui reste la solution de repli.

L'import de `formats_images` enregistre le décodeur HEIC auprès de Pillow avant
tout Image.open : ce module lit donc les HEIC d'iPhone sans code spécifique.

L'OPTIQUE — POURQUOI ELLE EST LUE ICI
-------------------------------------
Focale, dimensions d'origine et appareil ne servent pas à la carte : ils servent
au photomontage, en aval, qui part des positions et des caps de la carte parce
qu'ils sont plus justes que l'EXIF brut. Il lui faut la focale en pixels :

    f_px = f35 × diagonale_px / 43,267

Sans focale déclarée, elle doit être résolue en même temps que la pose de
l'appareil, et les deux sont dégénérées — 6 % d'erreur de focale valent une
centaine de mètres de recul. D'où les allers-retours de validation que ces
quelques champs suppriment.

La DIAGONALE est celle du fichier d'origine, jamais celle de la vignette encodée
dans la carte : une photo réduite à 1280 px donnerait une focale fausse d'un
facteur 3. C'est tout l'intérêt de `largeur_px`/`hauteur_px`.

Elles sont REDRESSÉES, c'est-à-dire données après application de la rotation
EXIF — l'orientation sous laquelle l'image se voit, et celle de la vignette de
la carte. `orientation` transporte la valeur brute pour qui veut revenir au
fichier tel quel. La diagonale, elle, ne dépend pas de ce choix.

Un capteur 4:3 livré en 9:16 est un RECADRAGE : appliquer la formule à la
diagonale du fichier recadré se trompe de 9 % (mesuré sur un iPhone XS du lot
de test). C'est le rapport des dimensions qui le révèle, pas le nom de
l'application photo — contrairement à une idée reçue, un cliché GPS Map Camera
sort en 4:3 plein capteur.
"""

from datetime import datetime
from PIL import Image, ExifTags

import formats_images  # noqa: F401  (enregistre le décodeur HEIC — à garder en tête de fichier)

# Identifiants des sous-répertoires EXIF (constants du standard).
IFD_GPS = 0x8825
IFD_EXIF = 0x8769

# Codes des champs GPS utilisés.
GPS_LAT_REF, GPS_LAT = 1, 2
GPS_LON_REF, GPS_LON = 3, 4
GPS_DIR_REF, GPS_DIR = 16, 17
GPS_PRECISION = 31          # GPSHPositioningError : incertitude horizontale, en mètres

# Au-delà de cette incertitude, la position est signalée comme peu fiable dans le
# tableau de résultats. Elle n'est jamais écartée pour autant : elle reste souvent
# utile, et c'est au CDP de juger.
# Valeur calée sur l'usage : à l'échelle d'une visite de site, 100 m ne voulait
# plus rien dire (on change de parcelle). Un iPhone en bonne réception annonce
# environ 5 m, une fixation dégradée plusieurs milliers ; 20 m laisse donc passer
# une réception normale tout en signalant tout ce qui commence à dériver.
SEUIL_PRECISION_M = 20

# Champs d'optique, dans le sous-répertoire EXIF (codes du standard).
EXIF_FOCALE = 37386                 # FocalLength, en millimètres réels
EXIF_FOCALE_EQ35 = 41989            # FocalLengthIn35mmFilm, l'équivalent 35 mm
EXIF_ZOOM_NUMERIQUE = 41988         # DigitalZoomRatio
EXIF_ORIENTATION = 274              # Orientation, dans le répertoire principal
EXIF_MARQUE = 271                   # Make
EXIF_MODELE = 272                   # Model

# Valeurs d'orientation qui échangent largeur et hauteur (rotations de 90°).
ORIENTATIONS_PIVOTEES = (5, 6, 7, 8)

# GPS Map Camera signe ses clichés dans le modèle EXIF, par exemple
# « SM-S931B :: Captured by - GPS Map Camera ». C'est le repère le plus sûr de
# cette application : il ne dépend pas de l'image, contrairement à la détection
# de la vignette — laquelle n'est même pas tentée quand la photo porte un cap
# EXIF, la cascade s'arrêtant avant (voir lecture_photo._lire_cap).
MARQUEUR_GPS_MAP_CAMERA = "gps map camera"


def _nombre(valeur):
    """Convertit une valeur EXIF en flottant, ou None si elle n'en est pas un.

    Les focales arrivent en IFDRational ; certains appareils écrivent 0, ce qui
    ne désigne aucune optique et vaut donc « absent ».
    """
    try:
        nombre = float(valeur)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return nombre if nombre > 0 else None


def _appareil(marque, modele):
    """« Apple iPhone XS » à partir des champs Make et Model, ou None.

    La signature de GPS Map Camera est retirée du modèle : elle voyage dans
    `vignette_gps_map_camera`, et la laisser ici donnerait un nom d'appareil
    que personne ne reconnaîtrait.
    """
    marque = str(marque or "").strip()
    modele = str(modele or "").split("::")[0].strip()
    if modele.lower().startswith(marque.lower()) and marque:
        marque = ""
    entier = " ".join(morceau for morceau in (marque, modele) if morceau)
    return entier or None


def lire_optique(image, exif, bloc_exif):
    """Optique d'une photo déjà ouverte : focale, dimensions, appareil.

    Prend l'image ouverte plutôt que son chemin : la lecture EXIF a déjà tout
    en main, rouvrir le fichier serait le décoder une seconde fois.

    Tout champ absent vaut None — « cherché et non trouvé », jamais « inconnu
    par défaut ». Beaucoup de clichés n'ont pas d'équivalent 35 mm, et l'aval
    sait le gérer à condition que la distinction lui parvienne.
    """
    orientation = exif.get(EXIF_ORIENTATION)
    largeur, hauteur = image.size
    if orientation in ORIENTATIONS_PIVOTEES:
        largeur, hauteur = hauteur, largeur

    modele = exif.get(EXIF_MODELE)
    return {
        "focale_eq35_mm": _nombre(bloc_exif.get(EXIF_FOCALE_EQ35)),
        "focale_mm": _nombre(bloc_exif.get(EXIF_FOCALE)),
        "largeur_px": largeur,
        "hauteur_px": hauteur,
        "orientation": int(orientation) if orientation else None,
        "digital_zoom": _nombre(bloc_exif.get(EXIF_ZOOM_NUMERIQUE)),
        "appareil": _appareil(exif.get(EXIF_MARQUE), modele),
        "vignette_gps_map_camera":
            MARQUEUR_GPS_MAP_CAMERA in str(modele or "").lower(),
    }


# Optique d'une photo dont l'EXIF n'a rien donné : tout est absent, et les
# dimensions elles-mêmes sont inconnues. Un dictionnaire plutôt qu'un None
# évite à chaque appelant de se demander s'il doit tester.
OPTIQUE_INCONNUE = {
    "focale_eq35_mm": None, "focale_mm": None,
    "largeur_px": None, "hauteur_px": None, "orientation": None,
    "digital_zoom": None, "appareil": None,
    "vignette_gps_map_camera": False,
}


def _dms_vers_degres(dms, reference):
    """Convertit une coordonnée EXIF (degrés, minutes, secondes) en degrés décimaux."""
    degres, minutes, secondes = [float(x) for x in dms]
    valeur = degres + minutes / 60.0 + secondes / 3600.0
    if reference in ("S", "W"):
        valeur = -valeur
    return valeur


def lire_metadonnees(chemin_image):
    """Retourne : lat, lon, cap_exif, precision_m, date, message, optique.

    lat/lon valent None si la photo n'est pas géolocalisée : elle sera alors
    écartée de la carte, avec un message explicite pour l'utilisateur.

    precision_m est l'incertitude annoncée par le téléphone lui-même. La plupart
    des applications ne l'écrivent pas : None signifie « inconnue », surtout pas
    « mauvaise ».

    `optique` est lue AVANT les sorties anticipées de la cascade GPS, et c'est
    volontaire : une photo non géolocalisée sort d'ici sans position, mais le
    chargé de projet peut la lui donner à la main. Elle rejoindra alors la carte
    — et il serait absurde qu'elle y arrive sans sa focale, pour la seule raison
    que son GPS était muet. Même motif que pour precision_m, juste au-dessus.
    """
    resultat = {"lat": None, "lon": None, "cap_exif": None,
                "precision_m": None, "date": None, "message": "",
                "optique": dict(OPTIQUE_INCONNUE)}

    try:
        with Image.open(chemin_image) as image:
            exif = image.getexif()
            gps = exif.get_ifd(IFD_GPS)
            bloc_exif = exif.get_ifd(IFD_EXIF)
            resultat["optique"] = lire_optique(image, exif, bloc_exif)
    except Exception as erreur:
        resultat["message"] = f"Lecture impossible ({erreur})"
        return resultat

    # Incertitude horizontale annoncée par l'appareil (GPSHPositioningError).
    # Lue avant les coordonnées : le champ existe indépendamment d'elles.
    if gps and gps.get(GPS_PRECISION) is not None:
        try:
            resultat["precision_m"] = float(gps[GPS_PRECISION])
        except Exception:
            pass                        # champ illisible : on reste sur « inconnue »

    if not gps or GPS_LAT not in gps or GPS_LON not in gps:
        resultat["message"] = "Photo non géolocalisée (pas de coordonnées GPS)"
        return resultat

    try:
        resultat["lat"] = _dms_vers_degres(gps[GPS_LAT], gps.get(GPS_LAT_REF, "N"))
        resultat["lon"] = _dms_vers_degres(gps[GPS_LON], gps.get(GPS_LON_REF, "E"))
    except Exception:
        resultat["message"] = "Coordonnées GPS illisibles"
        return resultat

    # Cap EXIF, si l'application photo l'a écrit.
    if GPS_DIR in gps:
        try:
            cap = float(gps[GPS_DIR]) % 360.0
            reference = gps.get(GPS_DIR_REF, "T")  # T = nord géographique, M = magnétique
            resultat["cap_exif"] = round(cap, 1)
            resultat["cap_exif_ref"] = "magnétique" if reference == "M" else "géographique"
        except Exception:
            pass

    # Date de prise de vue : on privilégie DateTimeOriginal (36867).
    brut = bloc_exif.get(36867) or exif.get(306)
    if brut:
        try:
            resultat["date"] = datetime.strptime(str(brut), "%Y:%m:%d %H:%M:%S")
        except Exception:
            pass

    return resultat
