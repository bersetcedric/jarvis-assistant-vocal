"""Montage ffmpeg : une sequence par scene, puis assemblage de l'episode."""

from __future__ import annotations

import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

IPS = 30
Y_SOUS_TITRES = 1180


class ErreurMontage(RuntimeError):
    pass


@lru_cache(maxsize=1)
def ffmpeg() -> str:
    chemin = shutil.which("ffmpeg")
    if chemin:
        return chemin
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise ErreurMontage("ffmpeg est introuvable. Lance `uv sync` dans studio_video.") from None


def _lancer(arguments: list[str]) -> str:
    resultat = subprocess.run([ffmpeg(), "-hide_banner", "-y", *arguments],
                              capture_output=True, text=True, errors="replace")
    if resultat.returncode != 0:
        raise ErreurMontage("Le montage a échoué : " + resultat.stderr.strip()[-300:])
    return resultat.stderr


def duree_media(chemin: Path) -> float:
    sortie = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(chemin)],
                            capture_output=True, text=True, errors="replace").stderr
    trouve = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", sortie)
    if not trouve:
        raise ErreurMontage("Durée du média illisible.")
    heures, minutes, secondes = trouve.groups()
    return int(heures) * 3600 + int(minutes) * 60 + float(secondes)


def duree_estimee(narration: str) -> float:
    """Duree de lecture sans voix : environ 2,6 mots par seconde, ou 5 signes par
    seconde pour les ecritures sans espaces (chinois, japonais, thai...)."""
    signes = len(narration.replace(" ", ""))
    return max(2.5, len(narration.split()) / 2.6, signes / 5 if signes > 12 * len(narration.split()) else 0)


def rendre_scene(sortie: Path, *, duree: float, image: Path | None = None, clip: Path | None = None,
                 audio: Path | None = None, sous_titres: list[tuple[Path, float, float]] = (),
                 zoom_avant: bool = True) -> None:
    """Produit une sequence 1080x1920 : visuel anime, voix et sous-titres incrustes."""
    images = max(1, round(duree * IPS))
    if clip is not None:
        entrees = ["-stream_loop", "-1", "-i", str(clip)]
        filtre = (f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                  f"crop=1080:1920,fps={IPS},format=yuv420p[v0]")
    elif image is not None:
        entrees = ["-i", str(image)]
        zoom = f"1+0.10*on/{images}" if zoom_avant else f"1.10-0.10*on/{images}"
        filtre = (f"[0:v]scale=1620:2880:force_original_aspect_ratio=increase,crop=1620:2880,"
                  f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                  f"d={images}:s=1080x1920:fps={IPS},format=yuv420p[v0]")
    else:
        raise ErreurMontage("Scène sans visuel.")
    if audio is not None:
        entrees += ["-i", str(audio)]
    else:
        entrees += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    etiquette = "v0"
    for indice, (png, debut, fin) in enumerate(sous_titres):
        entrees += ["-i", str(png)]
        suivante = f"v{indice + 1}"
        filtre += (f";[{etiquette}][{indice + 2}:v]overlay=0:{Y_SOUS_TITRES}:"
                   f"enable='between(t,{debut:.3f},{fin:.3f})'[{suivante}]")
        etiquette = suivante
    filtre += ";[1:a]aresample=44100,apad[a]"
    _lancer([
        *entrees, "-filter_complex", filtre, "-map", f"[{etiquette}]", "-map", "[a]",
        "-t", f"{duree:.3f}", "-r", str(IPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", str(sortie),
    ])


def assembler(sequences: list[Path], sortie: Path) -> None:
    """Concatene les sequences d'un episode sans reencodage."""
    liste = sortie.with_suffix(".txt")
    liste.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in sequences), encoding="utf-8")
    try:
        _lancer(["-f", "concat", "-safe", "0", "-i", str(liste), "-c", "copy",
                 "-movflags", "+faststart", str(sortie)])
    finally:
        liste.unlink(missing_ok=True)
