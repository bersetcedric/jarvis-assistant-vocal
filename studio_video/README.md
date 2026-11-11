# Bobine — studio vidéo IA local

Bobine transforme une idée, un texte ou une image en vidéo MP4 prête à
publier : script, visuels, voix, sous-titres incrustés et montage. Deux
formats : **vidéo unique** ou **mini-série** en plusieurs épisodes qui se
suivent, de 15 secondes à 1 heure, du 720p au 4K.

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

## Formats, qualité et durée

| Format | Usage | Taille en 1080p |
|---|---|---|
| 9:16 | TikTok, Reels, Shorts, stories | 1080 × 1920 |
| 16:9 | YouTube, web | 1920 × 1080 |
| 1:1 | Instagram carré | 1080 × 1080 |
| 4:5 | Instagram portrait | 1080 × 1350 |
| 3:4 | Instagram 3:4 | 1080 × 1440 |
| 4:3 | classique | 1440 × 1080 |
| 21:9 | cinéma | 2520 × 1080 |

- **Qualité** : 720p, 1080p, 1440p (2K) ou 4K. La résolution désigne le petit
  côté de l'image. Les images sont générées autour de 1024 à 1536 pixels puis
  agrandies : le 1440p et le 4K donnent un fichier plus net à l'encodage, pas
  plus de détail dans l'image.
- **Durée** : de 15 secondes à 1 heure, par vidéo ou par épisode. C'est une
  durée visée : la durée réelle dépend du débit de la voix.
- Une vidéo longue est écrite chapitre par chapitre. Une heure représente
  environ 300 scènes, donc 300 images et 300 voix : la génération dure
  longtemps et coûte cher en crédits API. Le formulaire affiche l'estimation
  avant de lancer.
- Les appels aux fournisseurs sont retentés en cas de panne passagère, et une
  image qui échoue est remplacée par la précédente plutôt que de tout arrêter.
- Les clips IA sont réservés aux vidéos de 5 minutes au plus.

## Langues

Le champ « Langue de la vidéo » règle la narration, la voix et les sous-titres.
Une liste d'environ 80 langues est proposée, et n'importe quelle autre peut
être saisie librement : le script est alors écrit dans cette langue.

- Chinois, japonais, thaï et autres écritures sans espaces sont découpés par
  nombre de signes.
- Arabe, persan, ourdou et hébreu sont affichés de droite à gauche.
- La police est choisie automatiquement parmi celles du PC si celle demandée ne
  contient pas l'écriture. Si aucune ne convient, un avertissement s'affiche.
- Hindi, tamoul, thaï et écritures voisines demandent la bibliothèque FriBiDi
  pour être parfaitement ligaturés ; sans elle, un avertissement s'affiche.
- La qualité de la voix dépend du fournisseur : toutes les langues ne sont pas
  prononcées aussi bien.
- En mode démo, le script gabarit reste en français.

## Sous-titres

Trois réglages, avec aperçu dans le formulaire : la **couleur** (sept teintes
ou une couleur libre), la **police** (classique, Impact, décontractée, serif,
machine à écrire) et l'**habillage** (contour, bandeau plein, ombre portée).

## Moteurs vidéo

- **Images animées** (par défaut) : une image générée par scène, animée par un
  zoom lent. Rapide et économique.
- **Clips IA** : chaque image est animée par un modèle vidéo. Plus lent, et
  facturé à chaque clip par le fournisseur. Si un clip échoue ou est refusé, la
  scène retombe sur son image et un avertissement s'affiche.

Chaque génération appelle des API payantes (une image et une voix par scène,
plus un clip par scène en mode Clips IA). Une série compte 6 épisodes au plus.

## Fonctionnement

| Fichier | Rôle |
|---|---|
| `studio/scenario.py` | écriture du scénario (ou gabarit en mode démo) |
| `studio/visuels.py` | images, image fournie, clips IA |
| `studio/voix.py` | voix off ElevenLabs ou OpenAI |
| `studio/sous_titres.py` | découpage, polices et rendu des sous-titres |
| `studio/langues.py` | langues proposées et codes pour la voix |
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
