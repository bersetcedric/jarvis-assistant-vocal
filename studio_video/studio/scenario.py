"""Ecriture du scenario : une video unique ou une mini-serie en episodes.

Les videos courtes sont ecrites en un seul appel. Les videos longues (jusqu'a
une heure) sont d'abord decoupees en chapitres, puis ecrites chapitre par
chapitre pour rester coherentes sans depasser ce qu'un appel peut produire.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Callable

from . import langues
from .config import Config
from .http import ErreurFournisseur, requete
from .sous_titres import Style

MAX_EPISODES = 6
DUREE_MIN, DUREE_MAX = 15, 3600
DUREE_MAX_CLIPS = 300  # au-dela, les clips IA couteraient trop cher : images animees
SCENES_PAR_APPEL = 24
SCENES_PAR_CHAPITRE = 12
FORMATS = {"9:16": (9, 16), "4:5": (4, 5), "3:4": (3, 4), "1:1": (1, 1), "4:3": (4, 3),
           "16:9": (16, 9), "21:9": (21, 9)}
RESOLUTIONS = {"720p": 720, "1080p": 1080, "1440p": 1440, "4k": 2160}

STYLES = {
    "cinematique": "photographie cinematographique realiste, lumiere dramatique, grain de film",
    "anime": "illustration anime detaillee, couleurs vives, eclairage expressif",
    "aquarelle": "aquarelle douce, textures de papier, palette pastel",
    "3d": "rendu 3D stylise facon film d'animation, eclairage doux, formes rondes",
    "sombre": "ambiance sombre et mysterieuse, clair-obscur, brume, palette froide",
    "documentaire": "photo documentaire naturelle, lumiere du jour, cadrage sobre",
}

REGLES = """Tu es scenariste de videos courtes et longues pour TikTok, Instagram et YouTube.
Langue de la video : {langue}. Les champs "titre" et "narration" sont rediges dans cette langue,
dans son ecriture d'origine, avec un ton naturel pour un locuteur natif.
Tu reponds uniquement par un objet JSON.
Regles :
- "narration" : environ {mots} mots dits par une voix off (ou la longueur equivalente dans une
  langue sans espaces), sans emoji ni hashtag.
- "visuel" : description precise, en francais, d'une seule image {orientation}, sans texte ni logo.
- Les personnages recurrents sont decrits avec les memes traits a chaque scene."""

CONSIGNE = REGLES + """
Forme attendue :
{{"titre": str, "style_visuel": str, "episodes": [{{"titre": str, "scenes": [{{"narration": str, "visuel": str}}]}}]}}
- La premiere scene de chaque episode ouvre sur une accroche forte.
- "style_visuel" : une phrase qui fixe la direction artistique commune a toutes les images.
- Pour une mini-serie : les episodes se suivent, chacun (sauf le dernier) finit sur un suspense."""

CONSIGNE_PLAN = """Tu es scenariste de videos longues pour YouTube, TikTok et Instagram.
Langue de la video : {langue}. Les titres sont rediges dans cette langue.
Tu reponds uniquement par un objet JSON de la forme :
{{"titre": str, "style_visuel": str, "episodes": [{{"titre": str, "chapitres": [str]}}]}}
- "chapitres" : exactement {chapitres} resumes d'une ou deux phrases, en francais, qui se suivent
  et couvrent toute l'histoire de l'episode, du debut accrocheur a la conclusion.
- "style_visuel" : une phrase qui fixe la direction artistique commune a toutes les images.
- Pour une mini-serie : les episodes se suivent, chacun (sauf le dernier) finit sur un suspense."""

CONSIGNE_CHAPITRE = REGLES + """
Forme attendue : {{"scenes": [{{"narration": str, "visuel": str}}]}}
Tu ecris un seul chapitre d'une video plus longue : le recit continue celui des chapitres
precedents, sans resume ni salutation, et ne conclut que si c'est le dernier chapitre."""


def plan_scenes(duree: int) -> tuple[int, int]:
    """Nombre de scenes et mots par scene pour viser une duree (en secondes)."""
    par_scene = 5 if duree <= 90 else 8 if duree <= 600 else 12
    return max(3, round(duree / par_scene)), round(par_scene * 2.5)


def dimensions(ratio: str, resolution: str) -> tuple[int, int]:
    """Largeur et hauteur en pixels : la resolution designe le petit cote."""
    a, b = FORMATS.get(ratio, FORMATS["9:16"])
    petit = RESOLUTIONS.get(resolution, 1080)
    largeur, hauteur = (petit, petit * b / a) if a < b else (petit * a / b, petit)
    return 2 * round(largeur / 2), 2 * round(hauteur / 2)


@dataclass(frozen=True)
class Demande:
    idee: str
    format: str = "video"  # video | serie
    episodes: int = 1
    duree: int = 30  # secondes visees par video (ou par episode)
    style: str = "cinematique"
    moteur: str = "images"  # images | clips
    voix: bool = True
    image: bytes | None = None  # PNG de reference fournie par l'utilisateur
    langue: str = "Français"
    sous_titres: Style = Style()
    ratio: str = "9:16"
    resolution: str = "1080p"

    @property
    def scenes(self) -> int:
        return plan_scenes(self.duree)[0]

    @property
    def mots(self) -> int:
        return plan_scenes(self.duree)[1]

    @property
    def orientation(self) -> str:
        largeur, hauteur = dimensions(self.ratio, self.resolution)
        return "verticale" if largeur < hauteur else "carree" if largeur == hauteur else "horizontale"

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
            duree=max(DUREE_MIN, min(DUREE_MAX, int(self.duree))),
            style=self.style if self.style in STYLES else "cinematique",
            moteur=self.moteur if self.moteur in ("images", "clips") else "images",
            voix=bool(self.voix),
            image=self.image,
            langue=langues.normaliser(self.langue),
            sous_titres=self.sous_titres.valider(),
            ratio=self.ratio if self.ratio in FORMATS else "9:16",
            resolution=self.resolution if self.resolution in RESOLUTIONS else "1080p",
        )


def _texte(valeur, limite: int) -> str:
    return " ".join(str(valeur or "").split())[:limite]


def _scenes(brutes, maximum: int) -> list[dict]:
    scenes = []
    for scene in brutes if isinstance(brutes, list) else []:
        if not isinstance(scene, dict) or len(scenes) >= maximum:
            continue
        narration = _texte(scene.get("narration"), 600)
        if narration:
            scenes.append({"narration": narration, "visuel": _texte(scene.get("visuel"), 600) or narration})
    return scenes


def normaliser(brut: dict, demande: Demande) -> dict:
    """Ramene la reponse du modele au format attendu, quoi qu'il ait renvoye."""
    episodes = []
    for episode in (brut.get("episodes") or [])[: demande.episodes]:
        if not isinstance(episode, dict):
            continue
        scenes = _scenes(episode.get("scenes"), demande.scenes)
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
        "Chaque détail compte, et le décor change peu à peu sous nos yeux.",
        "Puis arrive le moment où tout bascule, sans prévenir.",
        "Il faut alors choisir : reculer, ou aller jusqu'au bout.",
        "La réponse se trouvait là depuis le départ, cachée en pleine lumière.",
        "Ce qui semblait impossible devient soudain évident.",
        "Et l'histoire ne fait que commencer.",
    ]
    repetitions = max(1, round(demande.mots / 12))
    episodes = []
    for numero in range(1, demande.episodes + 1):
        scenes = []
        for i in range(demande.scenes):
            narration = " ".join(trames[(i + k) % len(trames)] for k in range(repetitions)).format(s=sujet)
            if demande.episodes > 1 and i == 0:
                narration = f"Épisode {numero}. " + narration
            scenes.append({"narration": narration, "visuel": f"{sujet}, plan {i + 1}"})
        titre = f"Épisode {numero}" if demande.episodes > 1 else sujet[:60]
        episodes.append({"numero": numero, "titre": titre, "scenes": scenes})
    return {"titre": sujet[:80], "style_visuel": STYLES[demande.style], "episodes": episodes}


def _extraire_json(texte: str) -> dict:
    try:
        resultat = json.loads(texte)
    except ValueError:
        trouve = re.search(r"\{.*\}", texte, re.S)
        try:
            resultat = json.loads(trouve.group(0)) if trouve else None
        except ValueError:
            resultat = None
    if not isinstance(resultat, dict):
        raise ErreurFournisseur("Le modèle n'a pas renvoyé un scénario lisible.")
    return resultat


def _appel(cfg: Config, consigne: str, contenu: list[dict]) -> dict:
    reponse = requete(
        "POST",
        "https://api.openai.com/v1/chat/completions",
        nom="OpenAI (script)",
        headers={"Authorization": f"Bearer {cfg.cle_openai}"},
        json={
            "model": cfg.modele_script,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": consigne}, {"role": "user", "content": contenu}],
        },
    )
    try:
        message = reponse.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError):
        raise ErreurFournisseur("Réponse inattendue du modèle de script.") from None
    return _extraire_json(message or "")


def _demande_en_texte(demande: Demande, image_data_url: str | None) -> list[dict]:
    if demande.format == "serie":
        commande = f"Mini-serie de {demande.episodes} episodes de {demande.scenes} scenes chacun."
    else:
        commande = f"Video unique de {demande.scenes} scenes (un seul episode)."
    texte = f"{commande}\nIdee : {demande.idee}\nDirection artistique souhaitee : {STYLES[demande.style]}"
    contenu: list[dict] = [{"type": "text", "text": texte}]
    if image_data_url:
        contenu[0]["text"] += "\nL'image jointe est le point de depart : elle illustre la premiere scene."
        contenu.append({"type": "image_url", "image_url": {"url": image_data_url}})
    return contenu


def _scenario_long(demande: Demande, cfg: Config, image_data_url: str | None,
                   suivi: Callable[[int, int], None]) -> dict:
    """Plan en chapitres, puis ecriture chapitre par chapitre."""
    regles = {"langue": demande.langue, "mots": demande.mots, "orientation": demande.orientation}
    chapitres = math.ceil(demande.scenes / SCENES_PAR_CHAPITRE)
    plan = _appel(cfg, CONSIGNE_PLAN.format(langue=demande.langue, chapitres=chapitres),
                  _demande_en_texte(demande, image_data_url))
    titre = _texte(plan.get("titre"), 120) or demande.idee[:60]
    style = _texte(plan.get("style_visuel"), 300) or STYLES[demande.style]
    plans = [e for e in (plan.get("episodes") or []) if isinstance(e, dict)][: demande.episodes]
    if not plans:
        raise ErreurFournisseur("Le modèle n'a pas renvoyé de plan exploitable.")
    total, fait, episodes = len(plans) * chapitres, 0, []
    for numero, plan_episode in enumerate(plans, start=1):
        titre_episode = _texte(plan_episode.get("titre"), 120) or f"Épisode {numero}"
        resumes = [_texte(r, 400) for r in (plan_episode.get("chapitres") or []) if _texte(r, 400)]
        scenes: list[dict] = []
        for indice in range(chapitres):
            manquantes = demande.scenes - len(scenes)
            if manquantes <= 0:
                break
            nombre = min(SCENES_PAR_CHAPITRE, manquantes)
            resume = resumes[indice] if indice < len(resumes) else "Poursuis l'histoire dans la continuite."
            precedent = " ".join(s["narration"] for s in scenes[-2:]) or "(debut de l'episode)"
            texte = (
                f"Video : {titre}. Idee : {demande.idee}\nEpisode {numero} sur {len(plans)} : {titre_episode}\n"
                f"Chapitre {indice + 1} sur {chapitres} : {resume}\nFin du chapitre precedent : {precedent}\n"
                f"Ecris exactement {nombre} scenes."
                + (" La premiere scene ouvre sur une accroche forte." if indice == 0 else "")
                + (" C'est le dernier chapitre de l'episode." if indice == chapitres - 1 else "")
            )
            brut = _appel(cfg, CONSIGNE_CHAPITRE.format(**regles), [{"type": "text", "text": texte}])
            scenes += _scenes(brut.get("scenes"), nombre)
            fait += 1
            suivi(fait, total)
        if not scenes:
            raise ErreurFournisseur("Le modèle n'a renvoyé aucune scène exploitable.")
        episodes.append({"numero": numero, "titre": titre_episode, "scenes": scenes})
    return {"titre": titre, "style_visuel": style, "episodes": episodes}


def generer_scenario(demande: Demande, cfg: Config, image_data_url: str | None = None,
                     suivi: Callable[[int, int], None] = lambda fait, total: None) -> dict:
    if cfg.demo:
        return scenario_demo(demande)
    if demande.episodes * demande.scenes > SCENES_PAR_APPEL:
        return _scenario_long(demande, cfg, image_data_url, suivi)
    consigne = CONSIGNE.format(langue=demande.langue, mots=demande.mots, orientation=demande.orientation)
    return normaliser(_appel(cfg, consigne, _demande_en_texte(demande, image_data_url)), demande)
