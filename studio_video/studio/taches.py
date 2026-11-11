"""Projets de generation : file d'attente, progression et stockage local."""

from __future__ import annotations

import base64
import json
import re
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import langues, montage, sous_titres, visuels, voix
from .config import Config
from .http import ErreurFournisseur
from .scenario import Demande, generer_scenario

ID_VALIDE = re.compile(r"^[0-9a-f]{12}$")


class Gestionnaire:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.dossier = cfg.dossier_projets
        self.dossier.mkdir(parents=True, exist_ok=True)
        self._verrou = threading.Lock()
        self._file = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bobine")
        self._projets: dict[str, dict] = {}
        for fiche in self.dossier.glob("*/projet.json"):
            try:
                projet = json.loads(fiche.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not ID_VALIDE.match(str(projet.get("id", ""))):
                continue
            if projet.get("etat") in ("en_attente", "en_cours"):
                projet["etat"], projet["erreur"] = "erreur", "Génération interrompue par un redémarrage."
            self._projets[projet["id"]] = projet

    # -- lecture ---------------------------------------------------------
    def liste(self) -> list[dict]:
        with self._verrou:
            return sorted((dict(p) for p in self._projets.values()), key=lambda p: p["cree"], reverse=True)

    def lire(self, identifiant: str) -> dict | None:
        with self._verrou:
            projet = self._projets.get(identifiant)
            return json.loads(json.dumps(projet)) if projet else None

    def chemin_video(self, identifiant: str, numero: int) -> Path | None:
        projet = self.lire(identifiant)
        if not projet:
            return None
        for episode in projet["episodes"]:
            if episode["numero"] == numero and episode.get("pret"):
                chemin = self.dossier / identifiant / f"episode_{numero:02d}.mp4"
                return chemin if chemin.is_file() else None
        return None

    # -- ecriture --------------------------------------------------------
    def _maj(self, identifiant: str, **champs) -> None:
        with self._verrou:
            projet = self._projets.get(identifiant)
            if projet is None:
                return
            projet.update(champs)
            fiche = self.dossier / identifiant / "projet.json"
            if fiche.parent.is_dir():
                fiche.write_text(json.dumps(projet, ensure_ascii=False, indent=1), encoding="utf-8")

    def creer(self, demande: Demande) -> dict:
        demande = demande.valider()
        identifiant = uuid.uuid4().hex[:12]
        (self.dossier / identifiant).mkdir(parents=True)
        projet = {
            "id": identifiant, "cree": time.time(), "idee": demande.idee, "format": demande.format,
            "style": demande.style, "moteur": demande.moteur, "voix": demande.voix, "langue": demande.langue,
            "sous_titres": {"couleur": demande.sous_titres.couleur, "police": demande.sous_titres.police,
                            "habillage": demande.sous_titres.habillage},
            "avec_image": demande.image is not None, "etat": "en_attente", "etape": "En file d'attente",
            "progression": 0, "titre": demande.idee[:80], "episodes": [], "avertissements": [], "erreur": "",
        }
        with self._verrou:
            self._projets[identifiant] = projet
        self._maj(identifiant)
        self._file.submit(self._executer, identifiant, demande)
        return self.lire(identifiant)

    def supprimer(self, identifiant: str) -> bool:
        with self._verrou:
            projet = self._projets.get(identifiant)
            if projet is None or projet["etat"] in ("en_attente", "en_cours"):
                return False
            del self._projets[identifiant]
        shutil.rmtree(self.dossier / identifiant, ignore_errors=True)
        return True

    # -- generation ------------------------------------------------------
    def _executer(self, identifiant: str, demande: Demande) -> None:
        try:
            self._generer(identifiant, demande)
        except (ErreurFournisseur, montage.ErreurMontage, ValueError) as exc:
            self._maj(identifiant, etat="erreur", erreur=str(exc), etape="Échec")
        except Exception as exc:  # ne jamais laisser un projet bloque "en cours"
            self._maj(identifiant, etat="erreur", erreur=f"Erreur inattendue ({type(exc).__name__}).", etape="Échec")

    def _generer(self, identifiant: str, demande: Demande) -> None:
        cfg, dossier = self.cfg, self.dossier / identifiant
        avertissements: list[str] = []

        def avertir(message: str) -> None:
            if message not in avertissements:
                avertissements.append(message)
                self._maj(identifiant, avertissements=list(avertissements))

        if cfg.demo:
            avertir("Mode démo : aucune clé OpenAI, script gabarit et visuels abstraits.")
        if cfg.demo and demande.langue != "Français":
            avertir("Mode démo : le script gabarit reste en français, quelle que soit la langue choisie.")
        if demande.voix and not cfg.voix_disponible:
            avertir("Aucune voix configurée : vidéo muette avec sous-titres.")
        clips = demande.moteur == "clips" and not cfg.demo
        if demande.moteur == "clips" and cfg.demo:
            avertir("Clips IA indisponibles sans clé OpenAI : montage d'images utilisé.")

        self._maj(identifiant, etat="en_cours", etape="Écriture du scénario", progression=2)
        data_url = None
        if demande.image is not None:
            (dossier / "reference.png").write_bytes(demande.image)
            data_url = "data:image/png;base64," + base64.b64encode(demande.image).decode()
        scenario = generer_scenario(demande, cfg, data_url)
        episodes = [{**e, "pret": False} for e in scenario["episodes"]]
        self._maj(identifiant, titre=scenario["titre"], style_visuel=scenario["style_visuel"], episodes=episodes)

        total = sum(len(e["scenes"]) for e in episodes) + len(episodes)
        fait = 0

        def avancer(etape: str) -> None:
            self._maj(identifiant, etape=etape, progression=min(99, 5 + round(94 * fait / total)))

        for episode in episodes:
            numero, sequences = episode["numero"], []
            for indice, scene in enumerate(episode["scenes"], start=1):
                prefixe = f"Épisode {numero}, " if len(episodes) > 1 else ""
                avancer(f"{prefixe}scène {indice} sur {len(episode['scenes'])}")
                base = dossier / f"e{numero:02d}_s{indice:02d}"
                image, clip = base.with_suffix(".png"), None

                if demande.image is not None and numero == 1 and indice == 1:
                    image.write_bytes(demande.image)
                elif cfg.demo:
                    visuels.image_demo(scene["visuel"], indice, image)
                else:
                    visuels.image_openai(f"{scenario['style_visuel']}. {scene['visuel']}. "
                                         "Image verticale, sans texte ni logo.", image, cfg)

                audio = base.with_suffix(".mp3")
                if not (demande.voix and voix.synthetiser(scene["narration"], audio, cfg, langues.code_voix(demande.langue))):
                    audio = None
                parle = montage.duree_media(audio) if audio else montage.duree_estimee(scene["narration"])
                duree = max(2.5, parle + 0.35)

                if clips:
                    try:
                        clip = base.with_name(base.name + "_clip.mp4")
                        visuels.clip_openai(f"{scenario['style_visuel']}. {scene['visuel']}. "
                                            "Mouvement de camera lent et fluide.", clip, cfg, image,
                                            4 if duree <= 5 else 8)
                    except ErreurFournisseur as exc:
                        clip = None
                        avertir(f"Clip IA indisponible pour une scene, image utilisée à la place. ({exc})")

                if not sous_titres.choisir_police(scene["narration"], demande.sous_titres.police)[1]:
                    avertir("Aucune police installée ne contient cette écriture : les sous-titres "
                            "peuvent afficher des carrés vides.")
                if sous_titres.rendu_approximatif(scene["narration"]):
                    avertir("Écriture complexe (ex. hindi, tamoul, thaï) : sans la bibliothèque FriBiDi, "
                            "les sous-titres peuvent être mal ligaturés.")
                bandeaux = []
                for k, (texte, debut, fin) in enumerate(
                        sous_titres.minuter(sous_titres.decouper(scene["narration"]), parle)):
                    png = base.with_name(f"{base.name}_st{k:02d}.png")
                    sous_titres.rendre(texte, png, demande.sous_titres)
                    bandeaux.append((png, debut, fin))

                sequence = base.with_name(base.name + "_seq.mp4")
                montage.rendre_scene(sequence, duree=duree, image=image, clip=clip, audio=audio,
                                     sous_titres=bandeaux, zoom_avant=indice % 2 == 1)
                sequences.append(sequence)
                fait += 1

            avancer(f"Assemblage de l'épisode {numero}" if len(episodes) > 1 else "Assemblage final")
            sortie = dossier / f"episode_{numero:02d}.mp4"
            montage.assembler(sequences, sortie)
            episode["pret"], episode["duree"] = True, round(montage.duree_media(sortie), 1)
            fait += 1
            self._maj(identifiant, episodes=episodes)
            for fichier in dossier.glob(f"e{numero:02d}_s*"):
                fichier.unlink(missing_ok=True)

        self._maj(identifiant, etat="termine", etape="Terminé", progression=100)
