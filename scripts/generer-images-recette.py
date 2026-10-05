#!/usr/bin/env python3
"""Génère des images fictives et déterministes pour la recette des médias."""

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw


VERSION = 1


def _bruit_deterministe(graine, taille=(640, 480)):
    longueur = taille[0] * taille[1] * 3
    donnees = hashlib.shake_256(graine.encode("ascii")).digest(longueur)
    return Image.frombytes("RGB", taille, donnees)


def _photo(graine, taille, numero):
    image = _bruit_deterministe(graine).resize(taille, Image.Resampling.LANCZOS)
    dessin = ImageDraw.Draw(image)
    largeur, hauteur = taille
    for indice, couleur in enumerate(("#f4c95d", "#73a580", "#d77a61", "#577590")):
        x = (numero * 173 + indice * 311) % max(largeur - 1, 1)
        y = (numero * 127 + indice * 229) % max(hauteur - 1, 1)
        rayon = max(min(largeur, hauteur) // (8 + indice), 20)
        dessin.ellipse((x - rayon, y - rayon, x + rayon, y + rayon), outline=couleur,
                       width=max(rayon // 12, 3))
    return image


def _exif(orientation=1):
    exif = Image.Exif()
    exif[274] = orientation
    exif[270] = "Production fictive pour la recette Petits Pas"
    exif[271] = "Appareil fictif"
    exif[272] = "Modele recette"
    exif[305] = "Petits Pas #J1"
    exif[315] = "Personne fictive"
    return exif


def _enregistrer_photo(chemin, graine, taille, numero, orientation=1, qualite=94):
    image = _photo(graine, taille, numero)
    image.save(chemin, "JPEG", quality=qualite, subsampling=0, exif=_exif(orientation))


def _enregistrer_transparente(chemin):
    image = Image.new("RGBA", (1600, 1200), (0, 0, 0, 0))
    dessin = ImageDraw.Draw(image)
    dessin.rounded_rectangle((120, 120, 1480, 1080), radius=120,
                             fill=(244, 201, 93, 180), outline=(87, 117, 144, 255), width=24)
    dessin.ellipse((420, 280, 1180, 1040), fill=(115, 165, 128, 150))
    image.save(chemin, "PNG", optimize=True)


def _description(chemin, role, particularites):
    donnees = chemin.read_bytes()
    entree = {
        "fichier": chemin.name,
        "role": role,
        "particularites": particularites,
        "octets": len(donnees),
        "sha256": hashlib.sha256(donnees).hexdigest(),
    }
    try:
        with Image.open(chemin) as image:
            entree.update(format=image.format, largeur=image.width, hauteur=image.height,
                          orientation_exif=image.getexif().get(274, 1))
    except Exception:
        entree.update(format=None, largeur=None, hauteur=None, orientation_exif=None)
    return entree


def generer(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    entrees = []

    for numero in range(1, 16):
        chemin = destination / f"trace-{numero:02d}.jpg"
        taille = (2048, 1536) if numero % 2 else (1536, 2048)
        orientation = 6 if numero == 2 else 1
        _enregistrer_photo(chemin, f"trace-{numero}", taille, numero, orientation)
        particularites = ["details-fins", "metadonnees-exif"]
        if orientation != 1:
            particularites.append("orientation-exif")
        entrees.append(_description(chemin, "trace", particularites))

    couverture = destination / "couverture-ecole-classe.jpg"
    _enregistrer_photo(couverture, "couverture", (3600, 2400), 31, qualite=96)
    entrees.append(_description(couverture, "couverture", ["grande", "metadonnees-exif"]))

    tres_grande = destination / "trace-tres-grande.jpg"
    _enregistrer_photo(tres_grande, "tres-grande", (6000, 4000), 47, qualite=96)
    entrees.append(_description(tres_grande, "trace", ["tres-grande", "metadonnees-exif"]))

    transparente = destination / "illustration-transparente.png"
    _enregistrer_transparente(transparente)
    entrees.append(_description(transparente, "illustration", ["transparence"]))

    invalide = destination / "image-invalide.jpg"
    invalide.write_bytes(b"Ceci n'est pas une image.\n")
    entrees.append(_description(invalide, "invalide", ["contenu-invalide", "extension-trompeuse"]))

    manifeste = {"format": "petits-pas-recette-medias", "version": VERSION, "images": entrees}
    (destination / "manifest.json").write_text(
        json.dumps(manifeste, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifeste


def main():
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--destination", type=Path, default=Path(".recette-medias/images"))
    arguments = analyseur.parse_args()
    manifeste = generer(arguments.destination)
    total = sum(image["octets"] for image in manifeste["images"])
    print(f"{len(manifeste['images'])} images générées dans {arguments.destination}")
    print(f"Volume total : {total} octets")


if __name__ == "__main__":
    main()

