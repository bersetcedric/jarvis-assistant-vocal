"""Appels HTTP aux fournisseurs, avec des erreurs lisibles et sans secret."""

from __future__ import annotations

import httpx


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


def requete(methode: str, url: str, *, nom: str, timeout: float = 180.0, **kwargs) -> httpx.Response:
    """Execute une requete et leve `ErreurFournisseur` si elle echoue."""
    try:
        reponse = httpx.request(methode, url, timeout=timeout, **kwargs)
    except httpx.HTTPError as exc:
        raise ErreurFournisseur(f"{nom} injoignable ({type(exc).__name__}).") from None
    if reponse.status_code >= 400:
        raise ErreurFournisseur(f"{nom} a répondu {reponse.status_code} : {_detail(reponse)}")
    return reponse
