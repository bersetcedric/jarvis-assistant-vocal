"""Rend le paquet `studio` importable, que pytest soit lance d'ici ou de la racine."""

import sys
from pathlib import Path

RACINE = str(Path(__file__).resolve().parent)
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)
