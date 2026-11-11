# Bobine — studio vidéo IA local

Bobine transforme une idée, un texte ou une image en vidéo verticale prête à
publier (1080×1920, MP4) : script, visuels, voix française, sous-titres
incrustés et montage. Deux formats : **vidéo unique** ou **mini-série** en
plusieurs épisodes qui se suivent.

L'application est autonome : elle vit dans ce dossier, ne dépend pas du code de
Jarvis et ne partage ni sa configuration ni ses clés.

## Lancer

```powershell
cd studio_video
uv sync
uv run python -m studio
```

Ou double-clic sur `lancer_studio.bat`. Le navigateur s'ouvre sur
`http://127.0.0.1:8765`. Le serveur n'écoute que sur la machine locale.
ffmpeg est fourni par la dépendance `imageio-ffmpeg`, rien à installer à part.

## Clés

Copier `.env.example` en `.env` (ignoré par git) et renseigner :

| Variable | Rôle |
|---|---|
| `OPENAI_API_KEY` | script, images, clips IA, voix de repli |
| `ELEVENLABS_API_KEY` | voix française (facultatif) |
| `ELEVENLABS_VOICE_ID` | voix choisie ; vide = première voix du compte |

Sans aucune clé, Bobine tourne en **mode démo** : script gabarit, visuels
abstraits, vidéo muette sous-titrée. Cela suffit pour vérifier l'installation
et le montage.

## Moteurs vidéo

- **Images animées** (par défaut) : une image générée par scène, animée par un
  zoom lent. Rapide et économique.
- **Clips IA** : chaque image est animée par un modèle vidéo. Plus lent, et
  facturé à chaque clip par le fournisseur. Si un clip échoue ou est refusé, la
  scène retombe sur son image et un avertissement s'affiche.

Chaque génération appelle des API payantes (une image et une voix par scène,
plus un clip par scène en mode Clips IA). Les limites sont de 8 scènes par
vidéo et 6 épisodes par série.

## Fonctionnement

| Fichier | Rôle |
|---|---|
| `studio/scenario.py` | écriture du scénario (ou gabarit en mode démo) |
| `studio/visuels.py` | images, image fournie, clips IA |
| `studio/voix.py` | voix off ElevenLabs ou OpenAI |
| `studio/sous_titres.py` | découpage et rendu des sous-titres |
| `studio/montage.py` | montage ffmpeg |
| `studio/taches.py` | file d'attente, progression, stockage |
| `studio/serveur.py` | API locale et interface (`studio/static/index.html`) |

Les projets et leurs vidéos sont enregistrés dans `projets/` (ignoré par git).

## Tests

```powershell
uv run pytest
```

Les tests n'appellent aucun service externe : ils couvrent la validation des
demandes, les sous-titres, l'API et une génération complète en mode démo.

## État de validation

Le parcours complet est vérifié en mode démo. Les appels réels (script, images,
voix, clips) suivent les API publiques d'OpenAI et d'ElevenLabs mais n'ont pas
encore été exercés avec un compte réel : le premier essai avec tes clés peut
demander d'ajuster un nom de modèle dans `.env`.
