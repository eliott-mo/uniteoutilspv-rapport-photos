"""
export_photomontage.py — Livrer à l'aval les fichiers d'origine des vues à monter.

La carte HTML est le seul endroit où vivent la position replacée à la main et le
cap calibré d'une prise de vue. C'est plus juste que l'EXIF brut du téléphone, et
c'est exactement ce dont part un photomontage.

Mais la carte ne porte que des vignettes : réduites à 1280 px et réencodées sans
métadonnées, pour qu'un rapport s'envoie par mail. Un photomontage, lui, a besoin
du FICHIER D'ORIGINE — sa définition, et surtout son optique. D'où cet export,
distinct du téléchargement de la carte : les originaux intacts, accompagnés d'un
JSON qui les rattache à leur position, leur cap et leur focale.

POURQUOI SEULEMENT CERTAINES VUES
---------------------------------
Une visite compte cinq à quarante clichés ; une ou deux servent de base à un
photomontage. Zipper le tout à pleine résolution n'aurait pas de sens sur
l'hébergement, et ne servirait à personne. La vue est désignée par son
commentaire (voir `est_vue_photomontage`).

D'OÙ VIENNENT LA POSITION ET LE CAP
-----------------------------------
Du POINT DE LA CARTE quand il existe, pas de la relecture du fichier : lui seul
porte le replacement à la main et la calibration de boussole. Relire l'EXIF
redonnerait justement ce que le photomontage cherche à ne pas utiliser.
"""

import io
import json
import os
import zipfile

MOT_PHOTOMONTAGE = "photomontage"

# Champs d'optique repris tels quels dans le descriptif (cf. lecture_exif).
CHAMPS_OPTIQUE = ("focale_eq35_mm", "focale_mm", "largeur_px", "hauteur_px",
                  "orientation", "digital_zoom", "appareil",
                  "vignette_gps_map_camera")


def est_vue_photomontage(commentaire):
    """Vrai si ce commentaire désigne une vue destinée à un photomontage.

    Test de PRÉSENCE, insensible à la casse et au pluriel — surtout pas une
    égalité. Relevé sur les quatre projets déjà livrés, le commentaire s'écrit
    « Photomontage » sur trois points et « Photomontages » sur deux : une
    comparaison stricte en laisserait passer la moitié. Les autres valeurs
    rencontrées — « DP7 », « DP8 », vide — ne contiennent pas le mot et restent
    donc dehors.
    """
    return MOT_PHOTOMONTAGE in str(commentaire or "").lower()


def vues_a_exporter(photos, donnees_existantes=None):
    """Vues à exporter, appariées à leur point de carte. Liste de (photo, point|None).

    DEUX ORIGINES POUR LE MARQUAGE, et il faut les deux :

    - la colonne Commentaire de l'application, pour un lot en cours ;
    - la carte déposée en mode Compléter, où le marquage a le plus souvent été
      fait dans l'éditeur HTML, donc APRÈS le passage dans l'application. C'est
      le cas des quatre projets déjà livrés : sans cette reprise, il faudrait
      retaper le marquage pour pouvoir exporter.

    L'appariement se fait sur le couple (nom, date), le même repère que le
    dédoublonnage de `generation_html.photos_nouvelles` — et avec la même limite
    connue : une photo renommée dans l'éditeur n'est plus reconnue.

    Une vue à la corbeille est ignorée : l'y avoir mise est une décision.
    """
    marques = {}
    if donnees_existantes:
        for point in donnees_existantes.get("points", []):
            if point.get("masque"):
                continue
            if est_vue_photomontage(point.get("commentaire")):
                marques[(point.get("nom"), point.get("date", ""))] = point

    retenues = []
    for photo in photos:
        point = marques.get((photo["nom"], photo.get("date_texte", "")))
        if point is not None or est_vue_photomontage(photo.get("commentaire")):
            retenues.append((photo, point))
    return retenues


def fiche_vue(photo, point, rang):
    """Ce que le descriptif dit d'une vue.

    Position, cap et identifiant viennent du point de carte dès qu'il existe :
    lui seul porte le replacement à la main et la calibration.
    """
    source = point if point is not None else photo
    optique = photo.get("optique") or {}
    fiche = {
        "id": point.get("id") if point is not None else rang,
        "nom": photo["nom"],
        "lat": source.get("lat"),
        "lon": source.get("lon"),
        "cap": source.get("cap"),
        "source_position": source.get("source_position"),
        "commentaire": (point or photo).get("commentaire", ""),
        "date": photo.get("date_texte", ""),
    }
    fiche.update({champ: optique.get(champ) for champ in CHAMPS_OPTIQUE})
    return fiche


def descriptif(vues, titre, donnees_existantes=None, outil="", format_carte=None):
    """Le JSON qui accompagne les fichiers, en clair (indenté, accents gardés).

    `calibration_deg` est reprise de la carte : sans elle, un lecteur ne saurait
    pas que les caps annoncés sont déjà corrigés.
    """
    return json.dumps({
        "titre": titre,
        "outil": outil,
        "format_carte": format_carte,
        "calibration_deg": (donnees_existantes or {}).get("offset", 0.0),
        "vues": [fiche_vue(photo, point, rang)
                 for rang, (photo, point) in enumerate(vues)],
    }, ensure_ascii=False, indent=2)


def construire_archive(chemins, texte_descriptif):
    """Zip des fichiers d'origine INTACTS, plus `photomontage.json`.

    ZIP_STORED et non ZIP_DEFLATED : un JPEG est déjà compressé, le déflater
    coûterait du temps pour quelques pour mille. Les octets sont recopiés tels
    quels — c'est aussi ce qui garantit que l'EXIF arrive entier de l'autre
    côté, ce que la carte ne peut pas offrir.

    Un nom déjà pris est suffixé plutôt qu'écrasé : deux photos homonymes venues
    de dossiers différents arriveraient sinon en une seule.
    """
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_STORED) as archive:
        pris = set()
        for chemin in chemins:
            nom = os.path.basename(chemin)
            base, extension = os.path.splitext(nom)
            compteur = 1
            while nom in pris:
                nom = f"{base}_{compteur}{extension}"
                compteur += 1
            pris.add(nom)
            archive.write(chemin, arcname=nom)
        archive.writestr("photomontage.json", texte_descriptif)
    return tampon.getvalue()
