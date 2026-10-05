"""Validation et normalisation des images privées.

Ce module ne connaît ni les modèles ni le stockage Django. Il produit des
octets prêts à enregistrer afin que les parcours d'import puissent partager
exactement les mêmes protections.
"""

from dataclasses import dataclass
from io import BytesIO
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError


MIO = 1024 * 1024
FORMATS_ACCEPTES = {"JPEG", "PNG", "WEBP"}


class ImagePriveeInvalide(ValueError):
    """Erreur présentable à la personne qui a choisi le fichier."""


@dataclass(frozen=True)
class RegleImage:
    dimension_maximale: int
    qualite: int
    qualite_minimale: int
    objectif_octets: int


@dataclass(frozen=True)
class PolitiqueImages:
    limite_brute_octets: int
    limite_pixels: int
    trace_principale: RegleImage
    trace_pdf: RegleImage
    couverture_principale: RegleImage
    couverture_pdf: RegleImage


@dataclass(frozen=True)
class ImageNormalisee:
    contenu: bytes
    largeur: int
    hauteur: int
    qualite: int
    objectif_atteint: bool
    format: str = "JPEG"
    extension: str = ".jpg"
    type_mime: str = "image/jpeg"


POLITIQUE_EQUILIBREE = PolitiqueImages(
    # Limite identique pour les traces et couvertures : le relâchement de la
    # couverture porte sur la qualité utile, pas sur la protection du serveur.
    limite_brute_octets=25 * MIO,
    limite_pixels=40_000_000,
    trace_principale=RegleImage(1600, 85, 72, 1_000_000),
    trace_pdf=RegleImage(600, 80, 70, 180_000),
    couverture_principale=RegleImage(2400, 88, 75, 1_800_000),
    couverture_pdf=RegleImage(1800, 85, 72, 1_000_000),
)


def _lire_borne(source, limite):
    if isinstance(source, (bytes, bytearray, memoryview)):
        contenu = bytes(source)
    else:
        morceaux = []
        total = 0
        chunks = getattr(source, "chunks", None)
        iterable = chunks() if callable(chunks) else iter(lambda: source.read(64 * 1024), b"")
        for morceau in iterable:
            total += len(morceau)
            if total > limite:
                raise ImagePriveeInvalide("L’image choisie est trop volumineuse avant préparation.")
            morceaux.append(morceau)
        contenu = b"".join(morceaux)
    if len(contenu) > limite:
        raise ImagePriveeInvalide("L’image choisie est trop volumineuse avant préparation.")
    if not contenu:
        raise ImagePriveeInvalide("Le fichier choisi est vide.")
    return contenu


def _regle(politique, famille, variante):
    if famille not in {"trace", "couverture"}:
        raise ValueError(f"Famille d’image inconnue : {famille}")
    if variante not in {"principale", "pdf"}:
        raise ValueError(f"Variante d’image inconnue : {variante}")
    return getattr(politique, f"{famille}_{variante}")


def _aplatir_sur_blanc(image):
    if image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    ):
        transparente = image.convert("RGBA")
        fond = Image.new("RGBA", transparente.size, "white")
        fond.alpha_composite(transparente)
        return fond.convert("RGB")
    return image.convert("RGB")


def _encoder(image, regle):
    dernier = None
    derniere_qualite = regle.qualite_minimale
    qualites = list(range(regle.qualite, regle.qualite_minimale - 1, -2))
    if qualites[-1] != regle.qualite_minimale:
        qualites.append(regle.qualite_minimale)
    for qualite in qualites:
        sortie = BytesIO()
        image.save(
            sortie,
            "JPEG",
            quality=qualite,
            optimize=True,
            progressive=True,
            subsampling="4:2:0",
        )
        dernier = sortie.getvalue()
        derniere_qualite = qualite
        if len(dernier) <= regle.objectif_octets:
            break
    return dernier, derniere_qualite


def normaliser_image(source, *, famille="trace", variante="principale",
                     politique=POLITIQUE_EQUILIBREE):
    """Décode, oriente, nettoie et redimensionne une image privée.

    Le poids cible guide la qualité JPEG sans être une limite destructrice :
    si la qualité minimale est atteinte, l'image est conservée telle quelle.
    """
    regle = _regle(politique, famille, variante)
    contenu = _lire_borne(source, politique.limite_brute_octets)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(contenu)) as ouverte:
                if ouverte.format not in FORMATS_ACCEPTES:
                    raise ImagePriveeInvalide(
                        "Choisissez une image JPEG, PNG ou WebP."
                    )
                if getattr(ouverte, "is_animated", False):
                    raise ImagePriveeInvalide("Les images animées ne sont pas acceptées.")
                largeur, hauteur = ouverte.size
                if largeur < 1 or hauteur < 1 or largeur * hauteur > politique.limite_pixels:
                    raise ImagePriveeInvalide("L’image choisie contient trop de pixels.")
                ouverte.load()
                image = ImageOps.exif_transpose(ouverte)
                image = _aplatir_sur_blanc(image)
    except ImagePriveeInvalide:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ImagePriveeInvalide("L’image choisie contient trop de pixels.") from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise ImagePriveeInvalide("Le fichier choisi n’est pas une image JPEG, PNG ou WebP valide.") from None

    image.thumbnail(
        (regle.dimension_maximale, regle.dimension_maximale),
        Image.Resampling.LANCZOS,
    )
    sortie, qualite = _encoder(image, regle)
    return ImageNormalisee(
        contenu=sortie,
        largeur=image.width,
        hauteur=image.height,
        qualite=qualite,
        objectif_atteint=len(sortie) <= regle.objectif_octets,
    )
