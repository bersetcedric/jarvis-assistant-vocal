"""Sous-titres incrustes : decoupage, choix de police selon l'ecriture, rendu PNG."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, features

W, M, L = "C:/Windows/Fonts/", "/System/Library/Fonts/", "/usr/share/fonts/"

# Polices proposees a l'utilisateur : fichiers Windows, puis macOS, puis Linux.
FAMILLES = {
    "classique": [W + "arialbd.ttf", M + "Supplemental/Arial Bold.ttf",
                  L + "truetype/dejavu/DejaVuSans-Bold.ttf", L + "truetype/liberation/LiberationSans-Bold.ttf"],
    "impact": [W + "impact.ttf", M + "Supplemental/Impact.ttf",
               L + "truetype/dejavu/DejaVuSansCondensed-Bold.ttf", L + "truetype/liberation/LiberationSansNarrow-Bold.ttf"],
    "decontracte": [W + "comicbd.ttf", M + "Supplemental/Comic Sans MS Bold.ttf",
                    L + "truetype/dejavu/DejaVuSans-Bold.ttf"],
    "serif": [W + "georgiab.ttf", W + "timesbd.ttf", M + "Supplemental/Georgia Bold.ttf",
              L + "truetype/dejavu/DejaVuSerif-Bold.ttf", L + "truetype/liberation/LiberationSerif-Bold.ttf"],
    "machine": [W + "courbd.ttf", W + "consolab.ttf", M + "Supplemental/Courier New Bold.ttf",
                L + "truetype/dejavu/DejaVuSansMono-Bold.ttf", L + "truetype/liberation/LiberationMono-Bold.ttf"],
}
# Polices de secours essayees quand la police choisie ne contient pas l'ecriture du texte.
SECOURS = [
    W + "segoeuib.ttf", W + "arialbd.ttf", W + "msyhbd.ttc", W + "msyh.ttc", W + "YuGothB.ttc",
    W + "meiryob.ttc", W + "malgunbd.ttf", W + "NirmalaB.ttf", W + "Nirmala.ttf", W + "LeelaUIb.ttf",
    W + "LeelawUI.ttf", W + "tahomabd.ttf", W + "ebrimabd.ttf", W + "msgothic.ttc",
    M + "Supplemental/Arial Unicode.ttf", M + "PingFang.ttc", M + "Hiragino Sans GB.ttc",
    M + "AppleSDGothicNeo.ttc", M + "Kohinoor.ttc", M + "Supplemental/Thonburi.ttc", M + "GeezaPro.ttc",
    L + "opentype/noto/NotoSansCJK-Bold.ttc", L + "opentype/noto/NotoSansCJK-Regular.ttc",
    L + "truetype/noto/NotoSansArabic-Bold.ttf", L + "truetype/noto/NotoSansDevanagari-Bold.ttf",
    L + "truetype/noto/NotoSansThai-Bold.ttf", L + "truetype/dejavu/DejaVuSans-Bold.ttf",
    L + "truetype/freefont/FreeSansBold.ttf",
]
COULEURS = {"blanc": "#FFFFFF", "jaune": "#FFE600", "vert": "#39FF14", "cyan": "#00E5FF",
            "rose": "#FF4FA3", "orange": "#FF8A1F", "rouge": "#FF3B30"}
HABILLAGES = ("contour", "bandeau", "ombre")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True)
class Style:
    couleur: str = "#FFFFFF"
    police: str = "classique"
    habillage: str = "contour"

    def valider(self) -> "Style":
        couleur = COULEURS.get(self.couleur, self.couleur)
        return Style(
            couleur=couleur.upper() if HEX.match(couleur or "") else "#FFFFFF",
            police=self.police if self.police in FAMILLES else "classique",
            habillage=self.habillage if self.habillage in HABILLAGES else "contour",
        )


# -- ecritures -----------------------------------------------------------
def ecriture(texte: str) -> str:
    """Famille d'ecriture dominante : sert au decoupage et a la mise en forme."""
    for caractere in texte:
        code = ord(caractere)
        if 0x0590 <= code <= 0x05FF:
            return "hebreu"
        if 0x0600 <= code <= 0x08FF or 0xFB50 <= code <= 0xFEFF:
            return "arabe"
        if 0x0900 <= code <= 0x0DFF:
            return "indienne"
        if 0x0E00 <= code <= 0x0EFF or 0x1000 <= code <= 0x109F or 0x1780 <= code <= 0x17FF:
            return "sans_espaces"  # thai, lao, birman, khmer
        if 0x3040 <= code <= 0x30FF or 0x3400 <= code <= 0x9FFF or 0xAC00 <= code <= 0xD7AF:
            return "cjc"
    return "autre"


def mise_en_forme_complete() -> bool:
    """Vrai si Pillow sait ligaturer et ordonner les ecritures complexes (libraqm)."""
    return bool(features.check("raqm"))


def preparer(texte: str, moteur_complet: bool | None = None) -> str:
    """Adapte le texte au moteur de rendu : sans libraqm, l'arabe et l'hebreu
    sont ligatures et remis dans l'ordre visuel par des bibliotheques Python."""
    if mise_en_forme_complete() if moteur_complet is None else moteur_complet:
        return texte
    genre = ecriture(texte)
    if genre not in ("arabe", "hebreu"):
        return texte
    try:
        from bidi.algorithm import get_display

        if genre == "arabe":
            import arabic_reshaper

            texte = arabic_reshaper.reshape(texte)
        return get_display(texte)
    except Exception:
        return texte


def rendu_approximatif(texte: str) -> bool:
    """Vrai si l'ecriture demande libraqm et qu'il manque (ex. hindi, tamoul, thai)."""
    return ecriture(texte) in ("indienne", "sans_espaces") and not mise_en_forme_complete()


# -- polices -------------------------------------------------------------
@lru_cache(maxsize=64)
def _charger(chemin: str, taille: int):
    moteur = ImageFont.Layout.RAQM if mise_en_forme_complete() else ImageFont.Layout.BASIC
    return ImageFont.truetype(chemin, taille, layout_engine=moteur)


@lru_cache(maxsize=512)
def _couvre(chemin: str, echantillon: str) -> bool:
    """Vrai si la police dessine ces caracteres autrement que par son glyphe « inconnu »."""
    try:
        fonte = ImageFont.truetype(chemin, 40, layout_engine=ImageFont.Layout.BASIC)
        vide = bytes(fonte.getmask("\uffff"))
        return all(bytes(fonte.getmask(c)) != vide for c in echantillon)
    except Exception:
        return False


def _echantillon(texte: str) -> str:
    lettres = sorted({c for c in texte if c.isalpha()})
    return "".join(lettres[:: max(1, len(lettres) // 6)][:6])


def choisir_police(texte: str, famille: str = "classique") -> tuple[str | None, bool]:
    """Renvoie (fichier de police, couverture) : la police choisie si elle contient
    l'ecriture du texte, sinon la premiere police de secours qui la contient."""
    candidates = [c for c in FAMILLES.get(famille, FAMILLES["classique"]) + SECOURS if Path(c).is_file()]
    echantillon = _echantillon(texte)
    for chemin in candidates:
        if not echantillon or _couvre(chemin, echantillon):
            return chemin, True
    return (candidates[0] if candidates else None), False


def police(taille: int, famille: str = "classique", texte: str = ""):
    chemin, _ = choisir_police(texte, famille)
    if chemin:
        try:
            return _charger(chemin, taille)
        except OSError:
            pass
    return ImageFont.load_default(size=taille)


# -- decoupage -----------------------------------------------------------
def decouper(narration: str, mots_max: int = 4, lettres_max: int = 22) -> list[str]:
    """Regroupe les mots en courts segments lisibles d'un coup d'oeil. Les ecritures
    sans espaces (chinois, japonais, thai...) sont coupees par nombre de signes."""
    genre = ecriture(narration)
    if genre in ("cjc", "sans_espaces"):
        limite = 9 if genre == "cjc" else 16
        mots = []
        for bloc in narration.split():
            mots += [bloc[i:i + limite] for i in range(0, len(bloc), limite)]
        return mots
    segments: list[str] = []
    courant: list[str] = []
    for mot in narration.split():
        candidat = " ".join(courant + [mot])
        if courant and (len(courant) >= mots_max or len(candidat) > lettres_max):
            segments.append(" ".join(courant))
            courant = []
        courant.append(mot)
        if mot[-1] in ".!?…。؟।" and len(courant) > 1:
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


# -- rendu ---------------------------------------------------------------
def _rvb(couleur: str) -> tuple[int, int, int]:
    return tuple(int(couleur[i:i + 2], 16) for i in (1, 3, 5))


def _contraste(couleur: tuple[int, int, int]) -> tuple[int, int, int]:
    """Noir sur une couleur claire, blanc sur une couleur sombre."""
    rouge, vert, bleu = couleur
    return (0, 0, 0) if 0.299 * rouge + 0.587 * vert + 0.114 * bleu > 110 else (255, 255, 255)


@dataclass(frozen=True)
class Geometrie:
    """Placement des sous-titres selon le format de la video."""
    largeur: int
    hauteur: int
    echelle: float  # 1.0 pour une video verticale de 1080 px de large
    y: int  # position verticale du bandeau dans la video
    lettres_max: int
    mots_max: int


def geometrie(largeur: int, hauteur: int) -> Geometrie:
    """En vertical, les sous-titres sont gros et centres bas ; en carre ou en
    paysage, ils sont un peu plus petits, plus longs et places en bas."""
    vertical = largeur < hauteur
    echelle = min(largeur, hauteur) / 1080 * (1.0 if vertical else 0.78)
    bande = 2 * round(420 * echelle / 2)
    centre = hauteur * (0.72 if vertical else 0.84)
    y = max(0, min(hauteur - bande, round(centre - bande / 2)))
    large = largeur / hauteur > 1.5
    return Geometrie(largeur, bande, echelle, y, 22 if vertical else 32 if large else 24,
                     4 if vertical else 6 if large else 5)


def rendre(texte: str, chemin: Path, style: Style = Style(), geo: Geometrie | None = None) -> None:
    """Ecrit un bandeau transparent avec le segment dans le style choisi."""
    style = style.valider()
    geo = geo or geometrie(1080, 1920)
    e = geo.echelle
    LARGEUR_BANDEAU, HAUTEUR_BANDEAU = geo.largeur, geo.hauteur
    image = Image.new("RGBA", (LARGEUR_BANDEAU, HAUTEUR_BANDEAU), (0, 0, 0, 0))
    dessin = ImageDraw.Draw(image)
    brut = texte.upper()
    texte = preparer(brut)
    couleur = _rvb(style.couleur)
    trait = round({"contour": 8, "bandeau": 0, "ombre": 2}[style.habillage] * e)
    centre = (LARGEUR_BANDEAU / 2, HAUTEUR_BANDEAU / 2)
    taille, mini = round(92 * e), round(40 * e)
    while True:
        fonte = police(taille, style.police, brut)
        boite = dessin.textbbox(centre, texte, font=fonte, anchor="mm", stroke_width=trait)
        if boite[2] - boite[0] <= LARGEUR_BANDEAU - 120 * e or taille <= mini:
            break
        taille -= max(1, round(6 * e))
    if style.habillage == "bandeau":
        dessin.rounded_rectangle((boite[0] - 34 * e, boite[1] - 22 * e, boite[2] + 34 * e, boite[3] + 22 * e),
                                 radius=26 * e, fill=(*couleur, 255))
        dessin.text(centre, texte, font=fonte, anchor="mm", fill=(*_contraste(couleur), 255))
    elif style.habillage == "ombre":
        dessin.text((centre[0] + 7 * e, centre[1] + 7 * e), texte, font=fonte, anchor="mm", fill=(0, 0, 0, 215),
                    stroke_width=trait, stroke_fill=(0, 0, 0, 215))
        dessin.text(centre, texte, font=fonte, anchor="mm", fill=(*couleur, 255),
                    stroke_width=trait, stroke_fill=(*_contraste(couleur), 255))
    else:
        dessin.text(centre, texte, font=fonte, anchor="mm", fill=(*couleur, 255),
                    stroke_width=trait, stroke_fill=(*_contraste(couleur), 255))
    image.save(chemin, "PNG")
