"""
lecture_photo.py — Cascades de lecture d'une photo : d'abord la position, puis le cap.

Ce module n'invente rien : il APPELLE dans un ordre fixé les briques existantes
(`lecture_exif`, `ocr_position`, `detection_cap`) et rend un enregistrement
unique, prêt à alimenter le tableau et la carte.

CASCADE DE POSITION (ordre impératif)
  1. position EXIF valide            → source « EXIF » ;
  2. sinon, texte incrusté lu en OCR → source « OCR » ;
  3. sinon, photo écartée avec le motif « position introuvable ».
Dans les deux premiers cas, la position doit passer le garde-fou géographique
(France métropolitaine) : une coordonnée hors bornes est rejetée, jamais placée.

Une photo écartée n'est pas perdue pour autant : le chargé de projet peut lui
donner sa position dans l'application, et `lire_photo_positionnee` la relit
alors sans cascade de position — source « Saisie ». Le garde-fou géographique
s'applique là aussi, en amont, chez l'appelant.

CASCADE DE CAP
  1. cap EXIF (GPSImgDirection), écrit par les iPhone et Open Camera → « EXIF » ;
  2. sinon, cône bleu de la vignette GPS Map Camera                  → « Vignette » ;
  3. sinon, pas de cap → le marqueur sera affiché sans cône.
L'absence de cap n'est PAS une erreur : un drone ou un bandeau « Work Progress »
n'en fournit aucun, et la carte sait déjà l'afficher.
"""

import os
import shutil
import tempfile

from PIL import Image, ImageOps

import formats_images
from detection_cap import detecter_cap
from lecture_exif import OPTIQUE_INCONNUE, lire_metadonnees
from ocr_position import lire_position_ocr, position_valide

SANS_CAP = "—"

# Provenance d'une position donnée à la main, par opposition à « EXIF » et
# « OCR » qui, eux, ont été mesurés. La distinction voyage jusque dans la carte :
# un lecteur du rapport doit pouvoir savoir qu'une position a été déclarée.
SOURCE_SAISIE = "Saisie"


def _chemin_lisible_par_opencv(chemin_image):
    """Retourne un chemin qu'OpenCV sait ouvrir, et True si c'est un fichier temporaire.

    `detection_cap` travaille avec cv2.imread, qui bute sur deux cas :
      - le HEIC, qu'il ne sait pas décoder → copie ré-encodée en JPEG ;
      - un chemin contenant des accents, qu'il n'ouvre pas sous Windows (il rend
        None sans message explicite, donnant à tort « image illisible ») → simple
        recopie sous un nom neutre, sans ré-encodage.

    Passer par une copie évite de modifier le module de détection, dont le
    fonctionnement reste inchangé.
    """
    heic = formats_images.est_heic(chemin_image)
    chemin_accentue = not str(chemin_image).isascii()
    if not (heic or chemin_accentue):
        return chemin_image, False

    extension = ".jpg" if heic else os.path.splitext(chemin_image)[1]
    descripteur, temporaire = tempfile.mkstemp(suffix=extension, prefix="cap_")
    os.close(descripteur)

    if heic:
        with Image.open(chemin_image) as brut:
            ImageOps.exif_transpose(brut).convert("RGB").save(temporaire, "JPEG", quality=92)
    else:
        # Recopie à l'identique : la détection doit voir les pixels d'origine.
        shutil.copyfile(chemin_image, temporaire)
    return temporaire, True


def _lire_cap(chemin_image, cap_exif):
    """Applique la cascade de cap. Retourne (cap, confiance, source, message, vignette).

    `vignette` n'est vrai que si un CÔNE a réellement été mesuré, et pas au
    simple repérage du marqueur. Le repérage seul produit des faux positifs :
    d'autres applications incrustent aussi une vignette carte — celle d'un
    iPhone du lot de test, avec son épingle rouge, le déclenche sans être du
    GPS Map Camera. Pour le cap cela reste sans conséquence (aucun cône
    exploitable n'en sort), mais en faire un identifiant d'application serait
    faux. Le cône bleu, lui, est propre à cette application.

    Le drapeau vaut aussi False quand le cap EXIF a suffi : la détection n'est
    alors même pas tentée. D'où la signature EXIF de l'application, que
    l'appelant lit de son côté — seul repère disponible dans tous les cas.
    """
    # 1. Le cap EXIF vient directement de la boussole : plus fiable que l'analyse
    #    d'image, qui passe par le rendu de la vignette.
    if cap_exif is not None:
        return cap_exif, 1.0, "EXIF", "", False

    # 2. Repli sur le cône bleu de la vignette GPS Map Camera.
    chemin, temporaire = _chemin_lisible_par_opencv(chemin_image)
    try:
        detection = detecter_cap(chemin)
    finally:
        if temporaire:
            os.remove(chemin)

    if detection["cap"] is not None:
        return (detection["cap"], detection["confiance"], "Vignette", "",
                detection.get("marqueur", True))

    # 3. Pas de cône (drone, bandeau sans boussole) : simple absence de cap.
    return None, None, SANS_CAP, detection["message"], False


def lire_photo(chemin_image):
    """Lit une photo de bout en bout : position, cap, date et provenances.

    Retourne un dictionnaire :
        lat, lon         : position en degrés décimaux, ou None si photo à écarter
        source_position  : « EXIF » ou « OCR »
        format_position  : nom du format de coordonnées reconnu par l'OCR, sinon None
        precision_m      : incertitude annoncée par l'appareil, ou None si inconnue
        cap              : cap brut en degrés, ou None
        confiance        : indice de confiance de la détection du cap, ou None
        source_cap       : « EXIF », « Vignette » ou « — »
        date             : datetime de prise de vue, ou None
        message          : motif du rejet, ou explication de l'absence de cap
        optique          : focale, dimensions d'origine, appareil (cf. lecture_exif)
    """
    resultat = {
        "lat": None, "lon": None, "source_position": None, "format_position": None,
        "precision_m": None, "cap": None, "confiance": None, "source_cap": SANS_CAP,
        "date": None, "message": "", "optique": dict(OPTIQUE_INCONNUE),
    }

    meta = lire_metadonnees(chemin_image)
    resultat["date"] = meta["date"]
    resultat["optique"] = meta["optique"]

    # --- Cascade de position ---------------------------------------------
    if position_valide(meta["lat"], meta["lon"]):
        resultat["lat"], resultat["lon"] = meta["lat"], meta["lon"]
        resultat["source_position"] = "EXIF"
        # L'incertitude EXIF décrit la fixation GPS de l'appareil : elle n'a de
        # sens que pour une position issue de cette même fixation, donc pas pour
        # une position relue par OCR dans le bandeau.
        resultat["precision_m"] = meta["precision_m"]
    else:
        # Position EXIF absente, illisible ou hors France : on tente le texte
        # incrusté. Le motif EXIF est conservé pour l'expliquer en cas d'échec.
        if meta["lat"] is not None:
            motif_exif = "position EXIF hors France métropolitaine"
        else:
            motif_exif = meta["message"] or "pas de position EXIF"

        ocr = lire_position_ocr(chemin_image)
        if ocr["lat"] is not None:
            resultat["lat"], resultat["lon"] = ocr["lat"], ocr["lon"]
            resultat["source_position"] = "OCR"
            resultat["format_position"] = ocr["format"]
        else:
            resultat["message"] = (
                f"Position introuvable (ni EXIF ni texte lisible) — "
                f"{motif_exif} ; {ocr['message'].lower()}"
            )
            return resultat

    # --- Cascade de cap ---------------------------------------------------
    (resultat["cap"], resultat["confiance"], resultat["source_cap"],
     message_cap, vignette) = _lire_cap(chemin_image, meta["cap_exif"])
    if resultat["cap"] is None:
        resultat["message"] = message_cap
    # Deux repères pour une même question, et il faut les deux : la signature
    # EXIF survit à tout mais disparaît si les métadonnées ont été effacées ; la
    # détection voit la vignette dans les pixels mais n'est pas tentée quand un
    # cap EXIF a déjà répondu.
    if vignette:
        resultat["optique"]["vignette_gps_map_camera"] = True

    return resultat


def lire_photo_positionnee(chemin_image, lat, lon):
    """Lit une photo dont la position est DONNÉE, et non détectée.

    Même enregistrement que `lire_photo`, à ceci près que la cascade de position
    est court-circuitée : la position vient de la saisie du chargé de projet,
    d'où la source « Saisie ». À lui de l'avoir validée (garde-fou France) avant
    d'appeler.

    LA CASCADE DE CAP, ELLE, EST BIEN JOUÉE — et c'est tout l'intérêt de passer
    par ici plutôt que de recoller une position sur un enregistrement écarté.
    Elle ne l'avait jamais été : quand la position manque, `lire_photo` rend la
    main avant d'y arriver. Or une photo repêchée a très bien pu être écartée
    parce que l'OCR n'a pas su relire le bandeau, alors que la vignette GPS Map
    Camera y est — avec son cône — ou que le cap EXIF est renseigné. La
    direction vient donc gratuitement, sans que personne ait à la saisir.
    """
    meta = lire_metadonnees(chemin_image)
    resultat = {
        "lat": lat, "lon": lon, "source_position": SOURCE_SAISIE,
        "format_position": None, "precision_m": None,
        "cap": None, "confiance": None, "source_cap": SANS_CAP,
        "date": meta["date"], "message": "", "optique": meta["optique"],
    }
    # Pas de precision_m : l'incertitude EXIF décrit une fixation GPS, et il n'y
    # en a pas eu. Une position saisie ne prétend pas non plus à une précision
    # connue — la mention « ± n m » serait une invention.
    (resultat["cap"], resultat["confiance"], resultat["source_cap"],
     message_cap, vignette) = _lire_cap(chemin_image, meta["cap_exif"])
    if resultat["cap"] is None:
        resultat["message"] = message_cap
    if vignette:
        resultat["optique"]["vignette_gps_map_camera"] = True
    return resultat
