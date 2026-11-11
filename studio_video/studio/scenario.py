"""Ecriture du scenario : une video unique ou une mini-serie en episodes."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .config import Config
from .http import ErreurFournisseur, requete

MAX_EPISODES = 6
MIN_SCENES, MAX_SCENES = 3, 8

STYLES = {
    "cinematique": "photographie cinematographique realiste, lumiere dramatique, grain de film",
    "anime": "illustration anime detaillee, couleurs vives, eclairage expressif",
    "aquarelle": "aquarelle douce, textures de papier, palette pastel",
    "3d": "rendu 3D stylise facon film d'animation, eclairage doux, formes rondes",
    "sombre": "ambiance sombre et mysterieuse, clair-obscur, brume, palette froide",
    "documentaire": "photo documentaire naturelle, lumiere du jour, cadrage sobre",
}

CONSIGNE = """Tu es scenariste de videos verticales courtes en francais (TikTok, Reels, Shorts).
Tu reponds uniquement par un objet JSON de la forme :
{"titre": str, "style_visuel": str, "episodes": [{"titre": str, "scenes": [{"narration": str, "visuel": str}]}]}
Regles :
- La premiere scene de chaque episode ouvre sur une accroche forte.
- "narration" : 15 a 28 mots dits par une voix off, en francais naturel, sans emoji ni hashtag.
- "visuel" : description precise d'une seule image verticale, sans texte ni logo dans l'image.
- Les personnages recurrents sont decrits avec les memes traits a chaque scene.
- "style_visuel" : une phrase qui fixe la direction artistique commune a toutes les images.
- Pour une mini-serie : les episodes se suivent, chacun (sauf le dernier) finit sur un suspense."""


@dataclass(frozen=True)
class Demande:
    idee: str
    format: str = "video"  # video | serie
    episodes: int = 1
    scenes: int = 5
    style: str = "cinematique"
    moteur: str = "images"  # images | clips
    voix: bool = True
    image: bytes | None = None  # PNG de reference fournie par l'utilisateur

    def valider(self) -> "Demande":
        idee = " ".join(self.idee.split())[:1500]
        if len(idee) < 3 and self.image is None:
            raise ValueError("Décris ton idée en quelques mots ou ajoute une image.")
        format_ = self.format if self.format in ("video", "serie") else "video"
        episodes = 1 if format_ == "video" else max(2, min(MAX_EPISODES, int(self.episodes)))
        return Demande(
            idee=idee or "Raconte une histoire inspirée de cette image.",
            format=format_,
            episodes=episodes,
            scenes=max(MIN_SCENES, min(MAX_SCENES, int(self.scenes))),
            style=self.style if self.style in STYLES else "cinematique",
            moteur=self.moteur if self.moteur in ("images", "clips") else "images",
            voix=bool(self.voix),
            image=self.image,
        )


def _texte(valeur, limite: int) -> str:
    return " ".join(str(valeur or "").split())[:limite]


def normaliser(brut: dict, demande: Demande) -> dict:
    """Ramene la reponse du modele au format attendu, quoi qu'il ait renvoye."""
    episodes = []
    for episode in (brut.get("episodes") or [])[: demande.episodes]:
        if not isinstance(episode, dict):
            continue
        scenes = []
        for scene in episode.get("scenes") or []:
            if not isinstance(scene, dict) or len(scenes) >= demande.scenes:
                continue
            narration = _texte(scene.get("narration"), 400)
            if narration:
                scenes.append({"narration": narration, "visuel": _texte(scene.get("visuel"), 600) or narration})
        if scenes:
            episodes.append({
                "numero": len(episodes) + 1,
                "titre": _texte(episode.get("titre"), 120) or f"Épisode {len(episodes) + 1}",
                "scenes": scenes,
            })
    if not episodes:
        raise ErreurFournisseur("Le modèle n'a renvoyé aucune scène exploitable.")
    return {
        "titre": _texte(brut.get("titre"), 120) or demande.idee[:60],
        "style_visuel": _texte(brut.get("style_visuel"), 300) or STYLES[demande.style],
        "episodes": episodes,
    }


def scenario_demo(demande: Demande) -> dict:
    """Scenario gabarit, sans appel reseau, pour tester l'installation."""
    sujet = demande.idee.rstrip(".!? ")
    trames = [
        "Et si tout commençait par une seule idée : {s} ?",
        "Au début, personne n'y croit vraiment. Pourtant, quelque chose se met en mouvement.",
        "Chaque détail compte, et le décor change peu a peu sous nos yeux.",
        "Puis arrive le moment où tout bascule, sans prévenir.",
        "Il faut alors choisir : reculer, ou aller jusqu'au bout.",
        "La réponse se trouvait là depuis le départ, cachée en pleine lumière.",
        "Ce qui semblait impossible devient soudain évident.",
        "Et l'histoire ne fait que commencer.",
    ]
    episodes = []
    for numero in range(1, demande.episodes + 1):
        scenes = []
        for i in range(demande.scenes):
            narration = trames[i % len(trames)].format(s=sujet)
            if demande.episodes > 1 and i == 0:
                narration = f"Épisode {numero}. " + narration
            scenes.append({"narration": narration, "visuel": f"{sujet}, plan {i + 1}"})
        titre = f"Épisode {numero}" if demande.episodes > 1 else sujet[:60]
        episodes.append({"numero": numero, "titre": titre, "scenes": scenes})
    return {"titre": sujet[:80], "style_visuel": STYLES[demande.style], "episodes": episodes}


def _extraire_json(texte: str) -> dict:
    try:
        return json.loads(texte)
    except ValueError:
        trouve = re.search(r"\{.*\}", texte, re.S)
        if trouve:
            try:
                return json.loads(trouve.group(0))
            except ValueError:
                pass
    raise ErreurFournisseur("Le modèle n'a pas renvoyé un scénario lisible.")


def generer_scenario(demande: Demande, cfg: Config, image_data_url: str | None = None) -> dict:
    if cfg.demo:
        return scenario_demo(demande)
    if demande.format == "serie":
        commande = f"Ecris une mini-serie de {demande.episodes} episodes de {demande.scenes} scenes chacun."
    else:
        commande = f"Ecris une video unique de {demande.scenes} scenes (un seul episode)."
    texte = f"{commande}\nIdee : {demande.idee}\nDirection artistique souhaitee : {STYLES[demande.style]}"
    contenu: list[dict] = [{"type": "text", "text": texte}]
    if image_data_url:
        contenu[0]["text"] += "\nL'image jointe est le point de depart : elle illustre la premiere scene."
        contenu.append({"type": "image_url", "image_url": {"url": image_data_url}})
    reponse = requete(
        "POST",
        "https://api.openai.com/v1/chat/completions",
        nom="OpenAI (script)",
        headers={"Authorization": f"Bearer {cfg.cle_openai}"},
        json={
            "model": cfg.modele_script,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": CONSIGNE},
                {"role": "user", "content": contenu},
            ],
        },
    )
    try:
        message = reponse.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError):
        raise ErreurFournisseur("Réponse inattendue du modèle de script.") from None
    return normaliser(_extraire_json(message or ""), demande)
