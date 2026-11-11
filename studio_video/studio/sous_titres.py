"""Sous-titres incrustes : decoupage de la narration et rendu en bandeaux PNG."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

LARGEUR_BANDEAU, HAUTEUR_BANDEAU = 1080, 420
POLICES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


@lru_cache(maxsize=16)
def police(taille: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for chemin in POLICES:
        if Path(chemin).is_file():
            try:
                return ImageFont.truetype(chemin, taille)
            except OSError:
                continue
    return ImageFont.load_default(size=taille)


def decouper(narration: str, mots_max: int = 4, lettres_max: int = 22) -> list[str]:
    """Regroupe les mots en courts segments lisibles d'un coup d'oeil."""
    segments: list[str] = []
    courant: list[str] = []
    for mot in narration.split():
        candidat = " ".join(courant + [mot])
        if courant and (len(courant) >= mots_max or len(candidat) > lettres_max):
            segments.append(" ".join(courant))
            courant = []
        courant.append(mot)
        if mot[-1] in ".!?…" and len(courant) > 1:
            segments.append(" ".join(courant))
            courant = []
    if courant:
        segments.append(" ".join(courant))
    return segments


def minuter(segments: list[str], duree: float) -> list[tuple[str, float, float]]:
    """Repartit les segments sur la duree parlee, au prorata de leur longueur."""
    total = sum(len(s) + 1 for s in segments)
    if not total or duree <= 0:
        return []
    minutage, debut = [], 0.0
    for segment in segments:
        fin = debut + duree * (len(segment) + 1) / total
        minutage.append((segment, round(debut, 3), round(fin, 3)))
        debut = fin
    return minutage


def rendre(texte: str, chemin: Path) -> None:
    """Ecrit un bandeau transparent avec le segment en gros caracteres contournes."""
    image = Image.new("RGBA", (LARGEUR_BANDEAU, HAUTEUR_BANDEAU), (0, 0, 0, 0))
    dessin = ImageDraw.Draw(image)
    texte = texte.upper()
    taille = 92
    while taille > 44:
        boite = dessin.textbbox((0, 0), texte, font=police(taille), stroke_width=8)
        if boite[2] - boite[0] <= LARGEUR_BANDEAU - 100:
            break
        taille -= 6
    dessin.text(
        (LARGEUR_BANDEAU / 2, HAUTEUR_BANDEAU / 2), texte, font=police(taille), anchor="mm",
        fill=(255, 255, 255, 255), stroke_width=8, stroke_fill=(0, 0, 0, 255),
    )
    image.save(chemin, "PNG")
