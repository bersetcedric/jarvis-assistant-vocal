"""Tests de Bobine : aucun appel reseau, tout tourne en mode demo."""

import base64
import io
import time

import pytest
from PIL import Image

from studio import montage, sous_titres
from studio.config import charger
from studio.scenario import Demande, generer_scenario, normaliser
from studio.visuels import image_utilisateur


def _cfg(tmp_path, **env):
    return charger({"STUDIO_DOSSIER": str(tmp_path / "projets"), **env})


def _ffmpeg_present():
    try:
        montage.ffmpeg()
        return True
    except montage.ErreurMontage:
        return False


def test_config_sans_cle_est_en_demo(tmp_path):
    cfg = _cfg(tmp_path)
    assert cfg.demo and not cfg.voix_disponible
    assert not _cfg(tmp_path, OPENAI_API_KEY="factice").demo


def test_demande_bornee():
    demande = Demande(idee="  un chat  astronaute ", format="serie", episodes=99, scenes=1,
                      style="inconnu", moteur="autre").valider()
    assert (demande.idee, demande.episodes, demande.scenes) == ("un chat astronaute", 6, 3)
    assert (demande.style, demande.moteur) == ("cinematique", "images")
    assert Demande(idee="une idee", format="video", episodes=4).valider().episodes == 1
    with pytest.raises(ValueError):
        Demande(idee=" ").valider()


def test_scenario_demo_respecte_le_format(tmp_path):
    scenario = generer_scenario(Demande(idee="Un phare hante", format="serie", episodes=3, scenes=4).valider(),
                                _cfg(tmp_path))
    assert [e["numero"] for e in scenario["episodes"]] == [1, 2, 3]
    assert all(len(e["scenes"]) == 4 for e in scenario["episodes"])


def test_normaliser_tolere_une_reponse_bancale():
    demande = Demande(idee="test", scenes=3).valider()
    brut = {"episodes": [{"scenes": [{"narration": " Bonjour   le monde "}, {"narration": ""}, "x",
                                     {"narration": "a"}, {"narration": "b"}, {"narration": "c"}]},
                         {"scenes": [{"narration": "episode en trop"}]}]}
    scenario = normaliser(brut, demande)
    assert len(scenario["episodes"]) == 1
    scenes = scenario["episodes"][0]["scenes"]
    assert scenes[0] == {"narration": "Bonjour le monde", "visuel": "Bonjour le monde"}
    assert [s["narration"] for s in scenes] == ["Bonjour le monde", "a", "b"]


def test_sous_titres_couvrent_toute_la_duree():
    segments = sous_titres.decouper("Et si tout commencait par une seule idee ? Personne n'y croit vraiment.")
    assert all(len(s.split()) <= 4 for s in segments)
    assert " ".join(segments).startswith("Et si tout")
    minutage = sous_titres.minuter(segments, 6.0)
    assert minutage[0][1] == 0.0 and minutage[-1][2] == pytest.approx(6.0)
    assert all(a[2] == pytest.approx(b[1]) for a, b in zip(minutage, minutage[1:]))


def test_image_utilisateur_validee_et_recadree():
    tampon = io.BytesIO()
    Image.new("RGB", (640, 480), "red").save(tampon, "JPEG")
    png = image_utilisateur("data:image/jpeg;base64," + base64.b64encode(tampon.getvalue()).decode())
    assert Image.open(io.BytesIO(png)).size == (1080, 1920)
    for invalide in ("http://exemple/img.png", "data:image/png;base64,@@@", "data:image/png;base64,AAAA"):
        with pytest.raises(ValueError):
            image_utilisateur(invalide)


def test_api_ne_revele_aucune_cle_et_filtre_les_identifiants(tmp_path):
    from fastapi.testclient import TestClient

    from studio.serveur import creer_app

    secret = "sk-test-NE-DOIT-PAS-SORTIR"
    client = TestClient(creer_app(_cfg(tmp_path, OPENAI_API_KEY=secret, ELEVENLABS_API_KEY=secret)))
    etat = client.get("/api/etat")
    assert etat.json()["voix"] == "elevenlabs" and secret not in etat.text
    assert client.get("/api/projets/..%2F..%2Fetc").status_code == 404
    assert client.get("/api/projets/abcdefabcdef").status_code == 404
    assert client.delete("/api/projets/abcdefabcdef").status_code == 409
    assert client.post("/api/projets", json={"idee": ""}).status_code == 422
    assert client.get("/").status_code == 200


@pytest.mark.skipif(not _ffmpeg_present(), reason="ffmpeg indisponible")
def test_generation_demo_de_bout_en_bout(tmp_path):
    from fastapi.testclient import TestClient

    from studio.serveur import creer_app

    client = TestClient(creer_app(_cfg(tmp_path)))
    projet = client.post("/api/projets", json={"idee": "Un renard explore la ville la nuit", "format": "serie",
                                               "episodes": 2, "scenes": 3, "moteur": "clips"}).json()
    limite = time.time() + 240
    while projet["etat"] in ("en_attente", "en_cours") and time.time() < limite:
        time.sleep(0.5)
        projet = client.get(f"/api/projets/{projet['id']}").json()
    assert projet["etat"] == "termine", projet["erreur"]
    assert projet["progression"] == 100 and len(projet["episodes"]) == 2
    assert any("Clips IA indisponibles" in a for a in projet["avertissements"])
    video = client.get(f"/api/projets/{projet['id']}/episodes/2/video")
    assert video.status_code == 200 and video.content[4:8] == b"ftyp"
    assert all(e["duree"] > 7 for e in projet["episodes"])
    assert client.delete(f"/api/projets/{projet['id']}").json() == {"supprime": True}
    assert not (tmp_path / "projets" / projet["id"]).exists()
