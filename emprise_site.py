"""
emprise_site.py — Lecture de l'emprise du site depuis un zip de shapefile.

Le chargé de projet exporte le périmètre du projet depuis son SIG : un `.zip`
contenant un shapefile (`.shp`, `.shx`, `.dbf`, `.prj`). Ce module en tire les
contours, convertis en WGS84, prêts à tracer sur la carte des photos. Les CDP y
situent les prises de vue par rapport au périmètre.

AUCUNE DÉPENDANCE GÉOSPATIALE
-----------------------------
Ni fiona, ni pyproj, ni shapely : le format shapefile est lu ici avec `struct`,
et la projection est convertie par la conique conforme inverse écrite plus bas
(math seul). C'est délibéré. `fiona` n'a pas de roue cp314 et réclame GDAL : il
a mis extraction-topo-rge et ceti-carte à l'arrêt sur Streamlit Cloud, où le
déploiement échoue dès qu'un paquet doit se compiler. Voir l'en-tête de
requirements.txt. La conversion a été recoupée avec pyproj sur les fichiers de
test : écart maximal 3 nm, et les contours épousent les limites parcellaires sur
l'ortho IGN au zoom 17-18.

CE QUI EST LU, CE QUI NE L'EST PAS
----------------------------------
Seule la géométrie compte : les attributs du `.dbf` ne sont pas ouverts. Ce que
la carte montre, c'est un contour — un nom de parcelle ou un code cadastral n'y
a pas de place.

DEUX PIÈGES DU FORMAT, VÉRIFIÉS SUR FICHIERS RÉELS
--------------------------------------------------
1. Un enregistrement peut porter PLUSIEURS anneaux, qui sont soit des poches
   disjointes, soit des trous — le format ne les distingue que par le sens de
   parcours (extérieur horaire, trou anti-horaire). Un projet réel contient un
   enregistrement à 4 anneaux tous horaires, c'est-à-dire 4 poches. Le passer
   tel quel à `L.polygon` en ferait une poche à 3 trous. Chaque anneau est donc
   tracé pour lui-même : c'est le rendu juste dans les deux cas, puisqu'on ne
   dessine qu'un contour, sans remplissage.
2. Un zip peut contenir PLUSIEURS couches (un export livre volontiers un
   `_polygone` ET un `_point`). La couche est choisie sur le type de géométrie
   déclaré dans l'en-tête du `.shp`, jamais sur son nom.

PROJECTIONS ACCEPTÉES
---------------------
Le Lambert-93 (RGF93, EPSG:2154), converti ici, et le WGS84 en degrés, repris
tel quel. Toute autre projection est refusée en la nommant : mieux vaut un refus
explicite qu'une emprise posée à côté, comme pour une photo hors de France.
"""

import math
import os
import re
import struct
import zipfile


class EmpriseIllisible(ValueError):
    """Le fichier fourni ne contient pas d'emprise exploitable."""


# Précision de sortie : 6 décimales valent environ 11 cm, très en deçà de celle
# d'un périmètre dessiné dans un SIG. Au-delà, on n'alourdirait le fichier que
# de chiffres sans signification.
DECIMALES = 6


# --------------------------------------------------------------------------
# Lambert-93 -> WGS84 : conique conforme de Lambert inverse
# --------------------------------------------------------------------------
# Formules de l'EPSG (guidance note 7-2, « Lambert Conic Conformal 2SP »),
# appliquées aux paramètres de l'EPSG:2154. La latitude est retrouvée par
# itération sur la définition même de t(phi) : quelques tours suffisent, et cela
# évite de recopier — donc de risquer de mal recopier — le développement en
# série habituel.

A = 6378137.0                       # demi-grand axe GRS80
_APLATISSEMENT = 1 / 298.257222101  # aplatissement GRS80
# Excentricité, déduite de l'aplatissement plutôt que recopiée : ce sont ces deux
# nombres-là, et eux seuls, que le .prj déclare et que la vérification compare.
E = math.sqrt(2 * _APLATISSEMENT - _APLATISSEMENT ** 2)
_LON0 = math.radians(3.0)           # méridien d'origine
_PHI0 = math.radians(46.5)          # latitude d'origine
_PHI1 = math.radians(49.0)          # 1er parallèle automécoïque
_PHI2 = math.radians(44.0)          # 2nd parallèle automécoïque
_FE, _FN = 700000.0, 6600000.0      # constantes translatoires


def _t(phi):
    """Fonction isométrique de la conique conforme."""
    s = E * math.sin(phi)
    return math.tan(math.pi / 4 - phi / 2) / ((1 - s) / (1 + s)) ** (E / 2)


def _m(phi):
    """Rayon relatif du parallèle de latitude phi."""
    return math.cos(phi) / math.sqrt(1 - (E * math.sin(phi)) ** 2)


_N = (math.log(_m(_PHI1)) - math.log(_m(_PHI2))) / (math.log(_t(_PHI1)) - math.log(_t(_PHI2)))
_F = _m(_PHI1) / (_N * _t(_PHI1) ** _N)
_R0 = A * _F * _t(_PHI0) ** _N


def vers_wgs84(x, y):
    """Convertit un couple Lambert-93 (mètres) en (latitude, longitude) WGS84."""
    dx, dy = x - _FE, _R0 - (y - _FN)
    rayon = math.copysign(math.hypot(dx, dy), _N)
    theta = math.atan2(dx, dy)
    t = (rayon / (A * _F)) ** (1 / _N)

    # Latitude conforme, puis latitude géodésique par points fixes. La suite
    # converge en cinq ou six tours ; la borne est un garde-fou, pas une limite
    # utile.
    phi = math.pi / 2 - 2 * math.atan(t)
    for _ in range(12):
        s = E * math.sin(phi)
        suivante = math.pi / 2 - 2 * math.atan(t * ((1 - s) / (1 + s)) ** (E / 2))
        if abs(suivante - phi) < 1e-13:
            phi = suivante
            break
        phi = suivante

    return math.degrees(phi), math.degrees(theta / _N + _LON0)


# --------------------------------------------------------------------------
# Lecture du .prj : quelle projection ce shapefile annonce-t-il ?
# --------------------------------------------------------------------------
# La reconnaissance porte sur les PARAMÈTRES, pas sur le libellé : « Lambert-93 »
# s'écrit « RGF_1993_Lambert_93 » chez l'un, « RGF93 v1 / Lambert-93 » chez
# l'autre, et un nom ne prouve de toute façon rien. Ce sont le méridien, les
# parallèles, l'origine et les constantes translatoires qui définissent la
# projection que convertit le code ci-dessus.

_LAMBERT_93 = {"x0": 700000.0, "y0": 6600000.0, "lon0": 3.0,
               "lat0": 46.5, "phi1": 49.0, "phi2": 44.0}

# Les mêmes paramètres portent deux jeux de noms : ceux du WKT1 ESRI, écrit par
# GDAL dans les .prj de shapefile, et ceux du WKT2, qu'un SIG récent peut
# produire. Les deux mènent au même repère.
_ALIAS_PARAMETRES = {
    "falseeasting": "x0",              "eastingatfalseorigin": "x0",
    "falsenorthing": "y0",             "northingatfalseorigin": "y0",
    "centralmeridian": "lon0",         "longitudeoffalseorigin": "lon0",
    "latitudeoforigin": "lat0",        "latitudeoffalseorigin": "lat0",
    "standardparallel1": "phi1",       "latitudeof1ststandardparallel": "phi1",
    "standardparallel2": "phi2",       "latitudeof2ndstandardparallel": "phi2",
}

# Systèmes géodésiques dont les coordonnées en degrés se confondent avec le
# WGS84 à l'échelle d'un site (quelques centimètres d'écart).
_GEODESIQUES_WGS84 = ("wgs84", "wgs1984", "rgf93", "rgf1993", "etrs89", "etrs1989")


def _aplatir(texte):
    """Réduit un libellé WKT à ses lettres et chiffres, en minuscules.

    « Lambert_Conformal_Conic », « Lambert Conic Conformal (2SP) » et
    « LAMBERT_CONFORMAL_CONIC » désignent la même projection : la ponctuation et
    la casse ne portent aucune information.
    """
    return re.sub(r"[^a-z0-9]", "", texte.lower())


def _nom_declare(texte):
    """Nom du système annoncé par le .prj, pour pouvoir le citer dans un refus."""
    trouve = re.search(r'(?:PROJCS|PROJCRS|GEOGCS|GEOGCRS)\s*\[\s*"([^"]+)"', texte)
    return trouve.group(1) if trouve else "système sans nom"


def _parametres(texte):
    """Paramètres de projection du .prj, ramenés aux noms de _LAMBERT_93."""
    valeurs = {}
    for nom, valeur in re.findall(
            r'PARAMETER\s*\[\s*"([^"]+)"\s*,\s*(-?[0-9.]+(?:[eE][-+]?[0-9]+)?)', texte):
        cle = _ALIAS_PARAMETRES.get(_aplatir(nom))
        if cle:
            valeurs[cle] = float(valeur)
    return valeurs


def _refus_projection(nom):
    return EmpriseIllisible(
        f"Ce shapefile est en « {nom} ». L'outil n'accepte que le Lambert-93 "
        "(RGF93, EPSG:2154) ou le WGS84 en degrés. Reprojetez la couche dans "
        "votre SIG avant de l'exporter."
    )


def projection(texte):
    """Retourne « lambert93 » ou « wgs84 ». Lève EmpriseIllisible sinon.

    Un .prj absent est un refus, pas une occasion de deviner : sans projection
    déclarée, l'emprise serait posée au jugé — le contraire de ce que l'outil
    fait pour une photo, qu'il écarte plutôt que de la placer au mauvais endroit.
    """
    if texte is None:
        raise EmpriseIllisible(
            "Ce shapefile ne déclare pas sa projection : le fichier .prj manque "
            "dans le zip. Réexportez la couche depuis votre SIG en demandant "
            "l'export du système de coordonnées."
        )

    nom = _nom_declare(texte)
    plat = _aplatir(texte)

    # Pas de système projeté : des degrés. Seul le repère géodésique importe
    # alors, et il doit se confondre avec le WGS84 de la carte.
    if "projcs" not in plat and "projcrs" not in plat:
        if any(geodesique in plat for geodesique in _GEODESIQUES_WGS84):
            return "wgs84"
        raise _refus_projection(nom)

    methode = re.search(r'(?:PROJECTION|METHOD)\s*\[\s*"([^"]+)"', texte)
    if not methode or "lambert" not in _aplatir(methode.group(1)):
        raise _refus_projection(nom)

    # Le Lambert-93 est défini sur le GRS80. Les mêmes paramètres posés sur un
    # autre ellipsoïde (Clarke 1880, par exemple) donneraient un tout autre lieu.
    ellipsoide = re.search(r'(?:SPHEROID|ELLIPSOID)\s*\[\s*"[^"]+"\s*,\s*([0-9.]+)', texte)
    if not ellipsoide or abs(float(ellipsoide.group(1)) - A) > 1.0:
        raise _refus_projection(nom)

    lus = _parametres(texte)
    if any(abs(lus.get(cle, 1e9) - attendue) > 1e-6
           for cle, attendue in _LAMBERT_93.items()):
        raise _refus_projection(nom)
    return "lambert93"


# --------------------------------------------------------------------------
# Lecture du .shp
# --------------------------------------------------------------------------

# Types de géométrie du format shapefile. Seuls les polygones nous intéressent ;
# les variantes 3D (Z) et mesurées (M) rangent leurs coordonnées X/Y exactement
# comme la variante plane, les colonnes supplémentaires étant ajoutées à la
# suite : elles se lisent donc sans code particulier.
TYPES_POLYGONE = (5, 15, 25)

NOMS_TYPES = {0: "aucune géométrie", 1: "des points", 3: "des lignes",
              5: "des polygones", 8: "des semis de points",
              11: "des points 3D", 13: "des lignes 3D", 15: "des polygones 3D",
              18: "des semis de points 3D", 21: "des points mesurés",
              23: "des lignes mesurées", 25: "des polygones mesurés",
              28: "des semis de points mesurés"}


def _type_de_couche(octets):
    """Type de géométrie déclaré dans l'en-tête d'un .shp, ou None s'il n'en est pas un."""
    if len(octets) < 100:
        return None
    code, = struct.unpack(">i", octets[0:4])
    if code != 9994:                    # signature du format
        return None
    return struct.unpack("<i", octets[32:36])[0]


def _anneaux(octets):
    """Anneaux de tous les enregistrements d'un .shp polygonal, en coordonnées source.

    Chaque anneau est rendu pour lui-même : un enregistrement à quatre anneaux
    donne quatre contours, qu'ils soient poches disjointes ou trous (cf.
    en-tête). Le doublon de fermeture du format est retiré — Leaflet referme
    ses polygones tout seul, le conserver n'alourdirait le fichier pour rien.
    """
    anneaux = []
    position = 100                      # après l'en-tête de fichier
    try:
        while position + 8 <= len(octets):
            _, longueur = struct.unpack(">ii", octets[position:position + 8])
            contenu = octets[position + 8:position + 8 + longueur * 2]
            position += 8 + longueur * 2
            if len(contenu) < 4:
                continue
            type_forme, = struct.unpack("<i", contenu[0:4])
            if type_forme not in TYPES_POLYGONE:
                continue                # enregistrement nul (type 0), ou autre

            nb_parties, nb_sommets = struct.unpack("<ii", contenu[36:44])
            debuts = struct.unpack(f"<{nb_parties}i", contenu[44:44 + 4 * nb_parties])
            origine = 44 + 4 * nb_parties
            plats = struct.unpack(f"<{2 * nb_sommets}d",
                                  contenu[origine:origine + 16 * nb_sommets])

            for rang, debut in enumerate(debuts):
                fin = debuts[rang + 1] if rang + 1 < nb_parties else nb_sommets
                anneau = [(plats[2 * k], plats[2 * k + 1]) for k in range(debut, fin)]
                if len(anneau) > 1 and anneau[0] == anneau[-1]:
                    anneau.pop()
                if len(anneau) >= 3:    # en deçà, pas de contour à tracer
                    anneaux.append(anneau)
    except struct.error:
        raise EmpriseIllisible(
            "Le fichier .shp de ce zip est abîmé : sa lecture s'arrête en cours "
            "d'enregistrement. Réexportez la couche depuis votre SIG."
        ) from None
    return anneaux


# --------------------------------------------------------------------------
# Surface
# --------------------------------------------------------------------------

def surface_ha(anneaux, systeme):
    """Surface totale de l'emprise, en hectares, calculée sur les coordonnées SOURCE.

    Sert au chargé de projet à vérifier d'un coup d'œil qu'il a déposé le bon
    export : la surface est la première chose que son SIG lui annonce. C'est
    pourquoi elle se calcule avant conversion, dans le repère du fichier — celui
    dans lequel le SIG l'a lui-même mesurée. La calculer sur les degrés
    convertis donnerait la surface géodésique, plus juste dans l'absolu mais
    supérieure d'un millième au chiffre affiché par le SIG : de quoi faire douter
    d'un fichier pourtant bon.

    En Lambert-93 les coordonnées sont déjà des mètres. En WGS84, un degré est
    ramené à des mètres à la latitude du site, sur le GRS80.

    Les aires sont SIGNÉES et sommées selon le sens de parcours du format : un
    anneau extérieur (horaire) ajoute, un trou (anti-horaire) retranche. La
    surface annoncée est donc nette, que le SIG ait exporté des poches
    disjointes ou une poche trouée.
    """
    sommets = [sommet for anneau in anneaux for sommet in anneau]
    if not sommets:
        return 0.0
    x0 = sum(x for x, _ in sommets) / len(sommets)
    y0 = sum(y for _, y in sommets) / len(sommets)

    if systeme == "lambert93":
        echelle_x = echelle_y = 1.0
    else:
        radians = math.radians(y0)
        w = math.sqrt(1 - (E * math.sin(radians)) ** 2)
        echelle_x = math.radians(1) * A * math.cos(radians) / w
        echelle_y = math.radians(1) * A * (1 - E ** 2) / w ** 3

    total = 0.0
    for anneau in anneaux:
        # Coordonnées ramenées au barycentre avant mise à l'échelle : sans ce
        # recentrage, la formule des lacets soustrairait des produits de l'ordre
        # de 10^13 pour un résultat de l'ordre de 10^5.
        plan = [((x - x0) * echelle_x, (y - y0) * echelle_y) for x, y in anneau]
        aire = 0.0
        for rang in range(len(plan)):
            (x1, y1), (x2, y2) = plan[rang], plan[(rang + 1) % len(plan)]
            aire += x1 * y2 - x2 * y1
        total -= aire / 2               # horaire = extérieur : compté positivement
    return abs(total) / 10000


# --------------------------------------------------------------------------
# Lecture d'un zip complet
# --------------------------------------------------------------------------

def _couches(archive):
    """Regroupe les membres du zip par couche : {chemin sans extension: {.ext: membre}}.

    La clé garde le chemin complet : deux couches homonymes dans des
    sous-dossiers différents restent distinctes.
    """
    couches = {}
    for membre in archive.namelist():
        nom = os.path.basename(membre)
        if not nom or membre.startswith("__MACOSX") or nom.startswith("."):
            continue
        tige, extension = os.path.splitext(membre)
        couches.setdefault(tige, {})[extension.lower()] = membre
    return couches


def _couche_polygonale(archive):
    """Choisit la couche de polygones du zip. Retourne (tige, membres, octets du .shp).

    Le choix se fait sur le type déclaré dans l'en-tête du .shp, jamais sur le
    nom du fichier : un export livre volontiers un `_polygone` ET un `_point`, et
    rien ne garantit ces suffixes.
    """
    polygonales, autres = [], []
    for tige, membres in sorted(_couches(archive).items()):
        if ".shp" not in membres:
            continue
        octets = archive.read(membres[".shp"])
        type_couche = _type_de_couche(octets)
        if type_couche is None:
            continue
        if type_couche in TYPES_POLYGONE:
            polygonales.append((tige, membres, octets))
        else:
            autres.append((os.path.basename(tige), type_couche))

    if len(polygonales) == 1:
        return polygonales[0]

    if not polygonales:
        if autres:
            detail = ", ".join(f"« {nom} » contient "
                               f"{NOMS_TYPES.get(type_couche, 'une géométrie inconnue')}"
                               for nom, type_couche in autres)
            raise EmpriseIllisible(
                f"Ce zip ne contient aucune couche de polygones : {detail}. "
                "L'emprise doit être exportée en polygones."
            )
        raise EmpriseIllisible(
            "Ce zip ne contient pas de shapefile : aucun fichier .shp lisible "
            "n'y a été trouvé. Déposez l'export complet de votre SIG "
            "(.shp, .shx, .dbf, .prj), zippé."
        )

    noms = ", ".join(f"« {os.path.basename(tige)} »" for tige, _, _ in polygonales)
    raise EmpriseIllisible(
        f"Ce zip contient plusieurs couches de polygones ({noms}). Exportez la "
        "seule emprise : l'outil ne peut pas deviner laquelle dessine le "
        "périmètre du projet."
    )


def _verifier_coordonnees(sommets, systeme):
    """Refuse un fichier dont les coordonnées démentent la projection annoncée.

    Le cas réel est une couche déjà reprojetée en degrés, exportée avec le .prj
    Lambert-93 d'origine : les coordonnées passent alors pour des mètres et
    l'emprise atterrit au milieu de l'Atlantique, sans que rien ne le signale.
    """
    for x, y in sommets:
        if systeme == "lambert93":
            plausible = 0 <= x <= 1300000 and 5900000 <= y <= 7300000
        else:
            plausible = abs(x) <= 180 and abs(y) <= 90
        if not plausible:
            annonce = "du Lambert-93 (mètres)" if systeme == "lambert93" else "des degrés"
            raise EmpriseIllisible(
                f"Les coordonnées de ce shapefile ({x:.1f}, {y:.1f}) ne sont pas "
                f"{annonce}, alors que son .prj l'annonce : le fichier et sa "
                "projection ne concordent pas. Réexportez la couche."
            )


def lire_emprise(source):
    """Lit l'emprise d'un zip de shapefile. `source` : un chemin ou un objet fichier.

    Retourne le bloc prêt à ranger dans les données de la carte :

        {"nom": "alr_22_guerledan-emprise-cadastr_polygone",
         "poches": [[[lat, lon], ...], ...],     un anneau du shapefile par poche
         "surface_ha": 19.37}

    Lève EmpriseIllisible, avec un message adressé au chargé de projet, si le
    fichier n'est pas exploitable.
    """
    # Une archive abîmée se signale aussi bien à l'ouverture qu'à la lecture d'un
    # membre : les deux sont dans le même bloc pour ne pas laisser passer la
    # seconde. Les refus d'EmpriseIllisible, eux, traversent (ce sont des
    # ValueError) et gardent leur message.
    try:
        with zipfile.ZipFile(source) as archive:
            tige, membres, octets = _couche_polygonale(archive)
            prj = membres.get(".prj")
            texte_prj = archive.read(prj).decode("utf-8", "replace") if prj else None
    except zipfile.BadZipFile:
        raise EmpriseIllisible(
            "Ce fichier n'est pas une archive zip lisible. Déposez le zip "
            "d'export de votre SIG, tel qu'il l'a produit."
        ) from None

    systeme = projection(texte_prj)
    anneaux = _anneaux(octets)

    if not anneaux:
        raise EmpriseIllisible(
            "Cette couche de polygones ne contient aucun contour : le fichier "
            "est vide. Vérifiez l'export de votre SIG."
        )

    _verifier_coordonnees([sommet for anneau in anneaux for sommet in anneau], systeme)

    poches = []
    for anneau in anneaux:
        if systeme == "lambert93":
            convertis = [vers_wgs84(x, y) for x, y in anneau]
        else:
            convertis = [(y, x) for x, y in anneau]     # le shapefile range x=lon, y=lat
        poches.append([[round(lat, DECIMALES), round(lon, DECIMALES)]
                       for lat, lon in convertis])

    return {"nom": os.path.basename(tige),
            "poches": poches,
            "surface_ha": round(surface_ha(anneaux, systeme), 2)}
