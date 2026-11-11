"""Tests de Bobine : aucun appel reseau, tout tourne en mode demo."""

import base64
import io
import time

import pytest
from PIL import Image

from studio import langues, montage, sous_titres
from studio.config import charger
from studio.scenario import Demande, dimensions, generer_scenario, normaliser, plan_scenes
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
    demande = Demande(idee="  un chat  astronaute ", format="serie", episodes=99, duree=1,
                      style="inconnu", moteur="autre", ratio="7:3", resolution="8k").valider()
    assert (demande.idee, demande.episodes, demande.duree, demande.scenes) == ("un chat astronaute", 6, 15, 3)
    assert (demande.ratio, demande.resolution) == ("9:16", "1080p")
    assert Demande(idee="une idee", duree=99999).valider().duree == 3600
    assert (demande.style, demande.moteur) == ("cinematique", "images")
    assert Demande(idee="une idee", format="video", episodes=4).valider().episodes == 1
    with pytest.raises(ValueError):
        Demande(idee=" ").valider()


def test_scenario_demo_respecte_le_format(tmp_path):
    scenario = generer_scenario(Demande(idee="Un phare hante", format="serie", episodes=3, duree=20).valider(),
                                _cfg(tmp_path))
    assert [e["numero"] for e in scenario["episodes"]] == [1, 2, 3]
    assert all(len(e["scenes"]) == 4 for e in scenario["episodes"])


def test_normaliser_tolere_une_reponse_bancale():
    demande = Demande(idee="test", duree=15).valider()
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
    assert Image.open(io.BytesIO(png)).size == (640, 480)
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
                                               "episodes": 2, "duree": 15, "moteur": "clips",
                                               "ratio": "16:9", "resolution": "720p"}).json()
    limite = time.time() + 240
    while projet["etat"] in ("en_attente", "en_cours") and time.time() < limite:
        time.sleep(0.5)
        projet = client.get(f"/api/projets/{projet['id']}").json()
    assert projet["etat"] == "termine", projet["erreur"]
    assert projet["progression"] == 100 and len(projet["episodes"]) == 2
    assert any("Clips IA indisponibles" in a for a in projet["avertissements"])
    video = client.get(f"/api/projets/{projet['id']}/episodes/2/video")
    assert video.status_code == 200 and video.content[4:8] == b"ftyp"
    assert all(12 < e["duree"] < 19 for e in projet["episodes"])
    dossier = tmp_path / "projets" / projet["id"]
    import subprocess
    infos = subprocess.run([montage.ffmpeg(), "-hide_banner", "-i", str(dossier / "episode_02.mp4")],
                           capture_output=True, text=True).stderr
    assert "1280x720" in infos
    assert sorted(f.name for f in dossier.iterdir()) == ["episode_01.mp4", "episode_02.mp4", "projet.json"]
    assert client.delete(f"/api/projets/{projet['id']}").json() == {"supprime": True}
    assert not (tmp_path / "projets" / projet["id"]).exists()


def test_langue_normalisee_et_code_vocal():
    assert langues.normaliser("  english ") == "English"
    assert langues.normaliser("") == "Français"
    assert langues.normaliser("Occitan <script>{x}") == "Occitan scriptx"
    assert langues.code_voix("日本語") == "ja"
    assert langues.code_voix("Kiswahili") is None and langues.code_voix("Occitan") is None
    assert Demande(idee="une idee", langue="DEUTSCH").valider().langue == "Deutsch"


def test_style_de_sous_titres_valide():
    style = sous_titres.Style("jaune", "impact", "bandeau").valider()
    assert (style.couleur, style.police, style.habillage) == ("#FFE600", "impact", "bandeau")
    assert sous_titres.Style("#12ab9f", "x", "y").valider() == sous_titres.Style("#12AB9F", "classique", "contour")
    assert sous_titres.Style("red; drop", "serif", "ombre").valider().couleur == "#FFFFFF"


def test_decoupage_des_ecritures_sans_espaces():
    segments = sous_titres.decouper("这是一个关于未来城市的故事每个人都在寻找答案")
    assert len(segments) == 3 and all(len(s) <= 9 for s in segments)
    assert sous_titres.ecriture("مرحبا بالعالم") == "arabe"
    assert sous_titres.ecriture("नमस्ते") == "indienne" and sous_titres.ecriture("Привет") == "autre"
    assert montage.duree_estimee("这是一个关于未来城市的故事每个人都在寻找答案这是一个关于未来城市的故事") > 5


def test_arabe_remis_en_ordre_visuel_sans_libraqm():
    brut = "مرحبا بالعالم"
    assert sous_titres.preparer(brut, moteur_complet=True) == brut
    visuel = sous_titres.preparer(brut, moteur_complet=False)
    assert visuel != brut and len(visuel.split()) == 2
    assert sous_titres.preparer("Bonjour", moteur_complet=False) == "Bonjour"


def test_rendu_des_styles_et_repli_de_police(tmp_path):
    from PIL import Image

    images = {}
    for habillage in sous_titres.HABILLAGES:
        chemin = tmp_path / f"{habillage}.png"
        sous_titres.rendre("Привет мир", chemin, sous_titres.Style("rose", "serif", habillage))
        images[habillage] = Image.open(chemin).convert("RGBA")
        assert images[habillage].size == (1080, 420) and images[habillage].getbbox() is not None
    boite = images["bandeau"].getbbox()
    assert images["bandeau"].getpixel((boite[0] + 40, 210)) == (255, 79, 163, 255)
    assert len({bytes(i.tobytes()) for i in images.values()}) == 3
    chemin, couvert = sous_titres.choisir_police("Привет", "serif")
    if chemin is not None:  # une police systeme existe : elle couvre le cyrillique, pas un signe prive
        assert couvert and sous_titres._couvre(chemin, "Пр")
        assert not sous_titres._couvre(chemin, "\U000f0000")


def test_api_transmet_langue_et_style(tmp_path):
    from fastapi.testclient import TestClient

    from studio.serveur import creer_app

    client = TestClient(creer_app(_cfg(tmp_path)))
    etat = client.get("/api/etat").json()
    assert "日本語" in etat["langues"] and "impact" in etat["polices"] and etat["couleurs"]["jaune"] == "#FFE600"
    projet = client.post("/api/projets", json={"idee": "Un test de style", "langue": "español", "duree": 15,
                                               "st_couleur": "#39ff14", "st_police": "machine",
                                               "st_habillage": "ombre"}).json()
    assert projet["langue"] == "Español"
    assert projet["sous_titres"] == {"couleur": "#39FF14", "police": "machine", "habillage": "ombre"}


def test_formats_resolutions_et_durees():
    assert dimensions("9:16", "1080p") == (1080, 1920) and dimensions("16:9", "4k") == (3840, 2160)
    assert dimensions("1:1", "720p") == (720, 720) and dimensions("4:5", "1440p") == (1440, 1800)
    assert all(l % 2 == 0 and h % 2 == 0 for l, h in (dimensions(r, "720p") for r in ("21:9", "3:4", "4:3")))
    assert plan_scenes(15) == (3, 12) and plan_scenes(3600) == (300, 30)
    longue = Demande(idee="Une longue histoire", duree=3600).valider()
    scenario = generer_scenario(longue, charger({}))
    assert len(scenario["episodes"][0]["scenes"]) == 300
    paysage, vertical = sous_titres.geometrie(1920, 1080), sous_titres.geometrie(1080, 1920)
    assert vertical.y == 1172 and vertical.echelle == 1.0 and paysage.lettres_max > vertical.lettres_max
    assert paysage.y + paysage.hauteur <= 1080 and paysage.largeur == 1920


def test_scenario_long_ecrit_par_chapitres(tmp_path, monkeypatch):
    from studio import scenario

    appels = []

    def faux_appel(cfg, consigne, contenu):
        appels.append(contenu[0]["text"])
        if '"chapitres"' in consigne:
            return {"titre": "Titre", "style_visuel": "style", "episodes": [{"titre": "Unique", "chapitres": ["a", "b"]}]}
        nombre = int(contenu[0]["text"].split("Ecris exactement ")[1].split()[0])
        return {"scenes": [{"narration": f"scene {len(appels)}-{i}", "visuel": "v"} for i in range(nombre + 3)]}

    monkeypatch.setattr(scenario, "_appel", faux_appel)
    demande = Demande(idee="Une saga", duree=300).valider()  # 38 scenes -> 4 chapitres
    etapes = []
    resultat = scenario.generer_scenario(demande, _cfg(tmp_path, OPENAI_API_KEY="factice"), None,
                                         lambda fait, total: etapes.append((fait, total)))
    assert len(resultat["episodes"][0]["scenes"]) == demande.scenes == 38
    assert len(appels) == 5 and etapes[-1] == (4, 4)
    assert "Fin du chapitre precedent : scene 2-" in appels[2] and "dernier chapitre" in appels[-1]


def test_requete_retente_les_pannes_passageres(monkeypatch):
    import httpx

    from studio import http

    reponses = [httpx.Response(503), httpx.Response(429), httpx.Response(200, json={"ok": True})]
    monkeypatch.setattr(http, "PAUSES", (0, 0, 0))
    monkeypatch.setattr(httpx, "request", lambda *a, **k: reponses.pop(0))
    assert http.requete("GET", "https://exemple.invalid", nom="Test").json() == {"ok": True}
    monkeypatch.setattr(httpx, "request", lambda *a, **k: httpx.Response(401, json={"error": {"message": "cle"}}))
    with pytest.raises(http.ErreurFournisseur, match="401"):
        http.requete("GET", "https://exemple.invalid", nom="Test")
