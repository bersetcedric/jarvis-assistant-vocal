"""Visuels des scenes : images generees, image fournie, clips IA, repli demo."""

from __future__ import annotations

import base64
import io
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from .config import Config
from .http import ErreurFournisseur, requete
from .sous_titres import police

LARGEUR, HAUTEUR = 1080, 1920
TAILLE_MAX_IMAGE = 8 * 1024 * 1024
PALETTES = [
    ("#1b1035", "#e2583e"), ("#06283d", "#47b5ff"), ("#1a2e1a", "#e3b23c"),
    ("#2b0a3d", "#f06292"), ("#0b132b", "#5bc0be"), ("#3d0c11", "#f4a259"),
]
OPENAI = "https://api.openai.com/v1"


def cadrer(image: Image.Image, largeur: int = LARGEUR, hauteur: int = HAUTEUR) -> Image.Image:
    """Recadre en remplissant le format vertical, sans deformer."""
    return ImageOps.fit(image.convert("RGB"), (largeur, hauteur), Image.Resampling.LANCZOS)


def image_utilisateur(data_url: str) -> bytes:
    """Valide une image envoyee par le navigateur et la renvoie en PNG verticale."""
    if not data_url.startswith("data:image/") or ";base64," not in data_url:
        raise ValueError("Image invalide.")
    try:
        brut = base64.b64decode(data_url.split(";base64,", 1)[1], validate=True)
    except ValueError:
        raise ValueError("Image invalide.") from None
    if len(brut) > TAILLE_MAX_IMAGE:
        raise ValueError("Image trop lourde (8 Mo maximum).")
    try:
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(brut)))
        image.load()
    except Exception:
        raise ValueError("Image illisible.") from None
    tampon = io.BytesIO()
    cadrer(image).save(tampon, "PNG")
    return tampon.getvalue()


def image_demo(texte: str, numero: int, chemin: Path) -> None:
    """Visuel abstrait local : un degrade et le numero du plan."""
    sombre, clair = PALETTES[(numero - 1) % len(PALETTES)]
    grand = Image.linear_gradient("L").resize((2800, 2800)).rotate(25 * numero)
    degrade = grand.crop((860, 440, 860 + LARGEUR, 440 + HAUTEUR))
    image = ImageOps.colorize(degrade, sombre, clair)
    dessin = ImageDraw.Draw(image, "RGBA")
    for i in range(5):
        rayon = 140 + 90 * i
        cx, cy = 200 + (numero * 173 + i * 211) % 700, 300 + (numero * 97 + i * 331) % 1100
        dessin.ellipse((cx - rayon, cy - rayon, cx + rayon, cy + rayon), outline=(255, 255, 255, 38), width=4)
    dessin.text((80, 110), f"PLAN {numero:02d}", font=police(64), fill=(255, 255, 255, 220))
    dessin.text((80, 200), texte[:38], font=police(38), fill=(255, 255, 255, 150))
    image.save(chemin, "PNG")


def image_openai(prompt: str, chemin: Path, cfg: Config) -> None:
    reponse = requete(
        "POST",
        f"{OPENAI}/images/generations",
        nom="OpenAI (image)",
        timeout=300.0,
        headers={"Authorization": f"Bearer {cfg.cle_openai}"},
        json={"model": cfg.modele_image, "prompt": prompt[:3500], "size": "1024x1536", "n": 1},
    )
    try:
        donnee = reponse.json()["data"][0]
    except (KeyError, IndexError, TypeError, ValueError):
        raise ErreurFournisseur("Réponse inattendue du modèle d'image.") from None
    if donnee.get("b64_json"):
        brut = base64.b64decode(donnee["b64_json"])
    elif donnee.get("url"):
        brut = requete("GET", donnee["url"], nom="OpenAI (image)").content
    else:
        raise ErreurFournisseur("Le modèle d'image n'a rien renvoyé.")
    cadrer(Image.open(io.BytesIO(brut))).save(chemin, "PNG")


def clip_openai(prompt: str, chemin: Path, cfg: Config, reference: Path | None, secondes: int,
                attente_max: float = 900.0, pause: float = 6.0) -> None:
    """Anime une scene avec le modele video (image de reference -> clip vertical)."""
    entete = {"Authorization": f"Bearer {cfg.cle_openai}"}
    champs = {"model": cfg.modele_video, "prompt": prompt[:3500], "size": "720x1280", "seconds": str(secondes)}
    fichiers = None
    if reference is not None:
        tampon = io.BytesIO()
        cadrer(Image.open(reference), 720, 1280).save(tampon, "PNG")
        fichiers = {"input_reference": ("reference.png", tampon.getvalue(), "image/png")}
    else:  # force l'encodage multipart meme sans fichier
        fichiers = {cle: (None, valeur) for cle, valeur in champs.items()}
        champs = {}
    tache = requete("POST", f"{OPENAI}/videos", nom="OpenAI (vidéo)", headers=entete,
                    data=champs or None, files=fichiers).json()
    identifiant = tache.get("id")
    if not identifiant:
        raise ErreurFournisseur("Le modèle vidéo n'a pas démarré.")
    debut = time.monotonic()
    while tache.get("status") in ("queued", "in_progress"):
        if time.monotonic() - debut > attente_max:
            raise ErreurFournisseur("Le modèle vidéo met trop de temps à répondre.")
        time.sleep(pause)
        tache = requete("GET", f"{OPENAI}/videos/{identifiant}", nom="OpenAI (vidéo)", headers=entete).json()
    if tache.get("status") != "completed":
        erreur = tache.get("error") or {}
        detail = erreur.get("message", "") if isinstance(erreur, dict) else str(erreur)
        raise ErreurFournisseur(f"Clip refusé ou échoué. {detail}"[:300])
    contenu = requete("GET", f"{OPENAI}/videos/{identifiant}/content", nom="OpenAI (vidéo)",
                      headers=entete, timeout=300.0).content
    chemin.write_bytes(contenu)
