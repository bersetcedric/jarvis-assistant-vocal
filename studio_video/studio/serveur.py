"""Serveur local de Bobine : API JSON et interface web, sur 127.0.0.1 uniquement."""

from __future__ import annotations

import threading
import webbrowser
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import langues
from .config import Config, charger
from .scenario import (DUREE_MAX, DUREE_MAX_CLIPS, DUREE_MIN, FORMATS, MAX_EPISODES, RESOLUTIONS, STYLES,
                       Demande, plan_scenes)
from .sous_titres import COULEURS, FAMILLES, HABILLAGES, Style
from .taches import ID_VALIDE, Gestionnaire
from .visuels import image_utilisateur

STATIQUE = Path(__file__).resolve().parent / "static"
# Durees proposees dans l'interface, en secondes (de 15 s a 1 h).
DUREES = (15, 30, 45, 60, 90, 120, 180, 300, 600, 900, 1200, 1800, 2700, 3600)


class NouveauProjet(BaseModel):
    idee: str = Field(default="", max_length=1500)
    format: str = "video"
    episodes: int = Field(default=3, ge=1, le=MAX_EPISODES)
    duree: int = Field(default=30, ge=DUREE_MIN, le=DUREE_MAX)
    ratio: str = Field(default="9:16", max_length=8)
    resolution: str = Field(default="1080p", max_length=8)
    style: str = "cinematique"
    moteur: str = "images"
    voix: bool = True
    image: str | None = Field(default=None, max_length=12_000_000)
    langue: str = Field(default="Français", max_length=60)
    st_couleur: str = Field(default="#FFFFFF", max_length=20)
    st_police: str = Field(default="classique", max_length=20)
    st_habillage: str = Field(default="contour", max_length=20)


def creer_app(cfg: Config | None = None) -> FastAPI:
    cfg = cfg or charger()
    gestionnaire = Gestionnaire(cfg)
    app = FastAPI(title="Bobine", docs_url=None, redoc_url=None, openapi_url=None)

    def verifier(identifiant: str) -> str:
        if not ID_VALIDE.match(identifiant):
            raise HTTPException(404, "Projet introuvable.")
        return identifiant

    @app.get("/")
    def accueil():
        return FileResponse(STATIQUE / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/api/etat")
    def etat():
        voix = "elevenlabs" if cfg.cle_elevenlabs else "openai" if cfg.cle_openai else "aucune"
        return {"demo": cfg.demo, "images": cfg.images_ia, "clips": cfg.images_ia, "voix": voix, "styles": list(STYLES),
                "langues": list(langues.LANGUES), "couleurs": COULEURS, "polices": list(FAMILLES),
                "habillages": list(HABILLAGES),
                "max_episodes": MAX_EPISODES, "formats": list(FORMATS), "resolutions": list(RESOLUTIONS),
                "durees": {str(d): plan_scenes(d)[0] for d in DUREES}, "duree_max_clips": DUREE_MAX_CLIPS}

    @app.get("/api/projets")
    def projets():
        return gestionnaire.liste()

    @app.post("/api/projets", status_code=201)
    def nouveau(corps: NouveauProjet):
        try:
            image = image_utilisateur(corps.image) if corps.image else None
            return gestionnaire.creer(Demande(
                idee=corps.idee, format=corps.format, episodes=corps.episodes, duree=corps.duree,
                ratio=corps.ratio, resolution=corps.resolution,
                style=corps.style, moteur=corps.moteur, voix=corps.voix, image=image, langue=corps.langue,
                sous_titres=Style(corps.st_couleur, corps.st_police, corps.st_habillage)))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/api/projets/{identifiant}")
    def projet(identifiant: str):
        trouve = gestionnaire.lire(verifier(identifiant))
        if not trouve:
            raise HTTPException(404, "Projet introuvable.")
        return trouve

    @app.get("/api/projets/{identifiant}/episodes/{numero}/video")
    def video(identifiant: str, numero: int, telecharger: bool = False):
        chemin = gestionnaire.chemin_video(verifier(identifiant), numero)
        if not chemin:
            raise HTTPException(404, "Vidéo introuvable.")
        nom = f"bobine_{identifiant}_episode_{numero:02d}.mp4" if telecharger else None
        return FileResponse(chemin, media_type="video/mp4", filename=nom)

    @app.delete("/api/projets/{identifiant}")
    def supprimer(identifiant: str):
        if not gestionnaire.supprimer(verifier(identifiant)):
            raise HTTPException(409, "Projet introuvable ou encore en cours de génération.")
        return {"supprime": True}

    app.state.gestionnaire = gestionnaire
    return app


def lancer() -> None:
    import uvicorn

    cfg = charger()
    adresse = f"http://127.0.0.1:{cfg.port}"
    print(f"Bobine est prêt : {adresse}" + ("  (mode démo, aucune clé OpenAI)" if cfg.demo else ""))
    threading.Timer(1.0, webbrowser.open, args=(adresse,)).start()
    uvicorn.run(creer_app(cfg), host="127.0.0.1", port=cfg.port, log_level="warning")
