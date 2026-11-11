"""Voix off : ElevenLabs si configure, sinon OpenAI, sinon aucune."""

from __future__ import annotations

from pathlib import Path

from .config import Config
from .http import ErreurFournisseur, requete

ELEVENLABS = "https://api.elevenlabs.io/v1"
_voix_par_defaut: dict[str, str] = {}


def _voix_elevenlabs(cfg: Config) -> str:
    if cfg.voix_elevenlabs:
        return cfg.voix_elevenlabs
    if cfg.cle_elevenlabs not in _voix_par_defaut:
        voix = requete("GET", f"{ELEVENLABS}/voices", nom="ElevenLabs",
                       headers={"xi-api-key": cfg.cle_elevenlabs}).json().get("voices") or []
        if not voix:
            raise ErreurFournisseur("Aucune voix disponible sur le compte ElevenLabs.")
        _voix_par_defaut[cfg.cle_elevenlabs] = voix[0]["voice_id"]
    return _voix_par_defaut[cfg.cle_elevenlabs]


def synthetiser(texte: str, chemin: Path, cfg: Config) -> bool:
    """Ecrit la narration en MP3. Renvoie False si aucun fournisseur de voix."""
    if cfg.cle_elevenlabs:
        corps = {"text": texte, "model_id": cfg.modele_voix_elevenlabs}
        if "v2_5" in cfg.modele_voix_elevenlabs:
            corps["language_code"] = "fr"
        audio = requete(
            "POST", f"{ELEVENLABS}/text-to-speech/{_voix_elevenlabs(cfg)}", nom="ElevenLabs",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": cfg.cle_elevenlabs}, json=corps,
        ).content
    elif cfg.cle_openai:
        audio = requete(
            "POST", "https://api.openai.com/v1/audio/speech", nom="OpenAI (voix)",
            headers={"Authorization": f"Bearer {cfg.cle_openai}"},
            json={"model": cfg.modele_voix_openai, "voice": cfg.voix_openai,
                  "input": texte, "response_format": "mp3"},
        ).content
    else:
        return False
    chemin.write_bytes(audio)
    return True
