"""Configuration lue dans l'environnement et dans `studio_video/.env`.

Les cles ne sont jamais ecrites dans un fichier versionne ni renvoyees par l'API.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def _lire_env(chemin: Path) -> dict[str, str]:
    valeurs: dict[str, str] = {}
    if not chemin.is_file():
        return valeurs
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        nom, _, valeur = ligne.partition("=")
        valeurs[nom.strip()] = valeur.strip().strip('"').strip("'")
    return valeurs


@dataclass(frozen=True)
class Config:
    cle_openai: str = ""
    cle_elevenlabs: str = ""
    voix_elevenlabs: str = ""
    modele_script: str = "gpt-5.6-luna"
    modele_image: str = "gpt-image-1"
    modele_video: str = "sora-2"
    modele_voix_openai: str = "gpt-4o-mini-tts"
    voix_openai: str = "alloy"
    modele_voix_elevenlabs: str = "eleven_flash_v2_5"
    port: int = 8765
    dossier_projets: Path = RACINE / "projets"

    @property
    def demo(self) -> bool:
        return not self.cle_openai

    @property
    def voix_disponible(self) -> bool:
        return bool(self.cle_elevenlabs or self.cle_openai)


def charger(env: dict[str, str] | None = None) -> Config:
    """Construit la configuration ; l'environnement prime sur le fichier .env."""
    if env is None:
        env = {**_lire_env(RACINE / ".env"), **os.environ}

    def lire(nom: str, defaut: str = "") -> str:
        return (env.get(nom) or defaut).strip()

    base = Config()
    try:
        port = int(lire("STUDIO_PORT", str(base.port)))
    except ValueError:
        port = base.port
    dossier = lire("STUDIO_DOSSIER")
    return Config(
        cle_openai=lire("OPENAI_API_KEY"),
        cle_elevenlabs=lire("ELEVENLABS_API_KEY"),
        voix_elevenlabs=lire("ELEVENLABS_VOICE_ID"),
        modele_script=lire("STUDIO_MODELE_SCRIPT", base.modele_script),
        modele_image=lire("STUDIO_MODELE_IMAGE", base.modele_image),
        modele_video=lire("STUDIO_MODELE_VIDEO", base.modele_video),
        modele_voix_openai=lire("STUDIO_MODELE_VOIX_OPENAI", base.modele_voix_openai),
        voix_openai=lire("STUDIO_VOIX_OPENAI", base.voix_openai),
        modele_voix_elevenlabs=lire("STUDIO_MODELE_VOIX_ELEVENLABS", base.modele_voix_elevenlabs),
        port=port,
        dossier_projets=Path(dossier) if dossier else base.dossier_projets,
    )
