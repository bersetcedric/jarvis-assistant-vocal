"""Appels HTTP aux fournisseurs, avec des erreurs lisibles et sans secret."""

from __future__ import annotations

import time

import httpx

PAUSES = (2.0, 6.0, 15.0)  # attente avant chaque nouvel essai
STATUTS_PASSAGERS = {408, 409, 429, 500, 502, 503, 504}


class ErreurFournisseur(RuntimeError):
    """Echec d'un fournisseur cloud ; le message est affichable tel quel."""


def _detail(reponse: httpx.Response) -> str:
    try:
        corps = reponse.json()
    except ValueError:
        return reponse.text[:200]
    erreur = corps.get("error") if isinstance(corps, dict) else None
    if isinstance(erreur, dict):
        return str(erreur.get("message", ""))[:300]
    if isinstance(corps, dict) and "detail" in corps:
        detail = corps["detail"]
        if isinstance(detail, dict):
            detail = detail.get("message", "")
        return str(detail)[:300]
    return str(erreur or "")[:300]


def requete(methode: str, url: str, *, nom: str, timeout: float = 180.0, essais: int = 3,
            **kwargs) -> httpx.Response:
    """Execute une requete et leve `ErreurFournisseur` si elle echoue. Les pannes
    passageres (reseau, surcharge, quota momentane) sont retentees : une video
    longue ne doit pas echouer sur un incident de quelques secondes."""
    for essai in range(essais):
        dernier = essai == essais - 1
        try:
            reponse = httpx.request(methode, url, timeout=timeout, **kwargs)
        except httpx.HTTPError as exc:
            if dernier:
                raise ErreurFournisseur(f"{nom} injoignable ({type(exc).__name__}).") from None
        else:
            if reponse.status_code < 400:
                return reponse
            if dernier or reponse.status_code not in STATUTS_PASSAGERS:
                raise ErreurFournisseur(f"{nom} a répondu {reponse.status_code} : {_detail(reponse)}")
        time.sleep(PAUSES[min(essai, len(PAUSES) - 1)])
    raise ErreurFournisseur(f"{nom} injoignable.")
