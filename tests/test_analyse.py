"""Le cache d'analyse : il ne fait jamais attendre, et il ne ment jamais.

App Runner coupe toute requête à cent vingt secondes — mesuré, `504 upstream
request timeout` à 120,58 s. Une analyse complète en dure environ deux cent
quarante. Toute version qui *attend* une analyse dans une requête est donc
cassée en production, et elle l'est de la pire façon : le travail a lieu, et
l'appelant lit une panne.

Ces contrôles tiennent les quatre propriétés qui en découlent.
"""
from __future__ import annotations

import threading
import time

import pytest

from fadlie.agent import Rapport
from fadlie.ecart import Ecart
from fadlie.serveur import AnalyseEnCours, _Analyse


def _ecart(cible: str, genre: str = "owner") -> Ecart:
    return Ecart(cible=cible, source="urn:jumeau", genre=genre, valeur="urn:v")


def _rapport(*ecarts: Ecart) -> Rapport:
    return Rapport(groupes=(), ecarts=ecarts, desaccords=(),
                   couples_examines=2, couples_confirmes=1)


class AgentFactice:
    """Un agent dont l'analyse est lente, comptée, et éventuellement en panne."""

    def __init__(self, rapport=None, duree=0.0, erreur=None) -> None:
        self._rapport = rapport if rapport is not None else _rapport(_ecart("a"))
        self.duree = duree
        self.erreur = erreur
        self.appels = 0
        self.catalogue = None

    def analyser(self):
        self.appels += 1
        time.sleep(self.duree)
        if self.erreur is not None:
            raise self.erreur
        return self._rapport


def _attendre_que(predicat, limite=5.0):
    fin = time.time() + limite
    while time.time() < fin:
        if predicat():
            return True
        time.sleep(0.02)
    return False


def test_un_rapport_vieilli_est_rendu_tout_de_suite(monkeypatch):
    """Le cœur du correctif : vieilli se sert, il ne s'attend pas.

    Sans ça, chaque expiration du cache offrait un 504 au premier appelant.
    """
    monkeypatch.setattr("fadlie.serveur.DUREE_CACHE", 0)
    agent = AgentFactice(duree=2.0)
    analyse = _Analyse(agent)
    analyse.prechauffer()
    assert _attendre_que(lambda: analyse._rapport is not None, limite=6)

    debut = time.time()
    r = analyse.rapport()          # le cache est expiré : recalcul déclenché
    ecoule = time.time() - debut

    assert r is not None
    assert ecoule < 0.5, "un rapport connu doit être rendu sans attendre"


def test_sans_rien_a_servir_on_attend_mais_pas_indefiniment(monkeypatch):
    monkeypatch.setattr("fadlie.serveur.DELAI_ATTENTE", 1)
    analyse = _Analyse(AgentFactice(duree=30.0))
    with pytest.raises(AnalyseEnCours):
        analyse.rapport()


def test_une_analyse_en_panne_remonte_a_l_appelant():
    """Un juge mort doit lever, jamais devenir « aucun doublon »."""
    analyse = _Analyse(AgentFactice(erreur=RuntimeError("le juge est mort")))
    with pytest.raises(RuntimeError, match="le juge est mort"):
        analyse.rapport()


def test_deux_appels_simultanes_ne_lancent_qu_une_analyse():
    agent = AgentFactice(duree=0.5)
    analyse = _Analyse(agent)
    fils = [threading.Thread(target=lambda: analyse.rapport()) for _ in range(5)]
    for f in fils:
        f.start()
    for f in fils:
        f.join(timeout=10)
    assert agent.appels == 1


def test_retirer_enleve_les_ecarts_combles_sans_recalculer():
    a, b = _ecart("a"), _ecart("b")
    agent = AgentFactice(rapport=_rapport(a, b))
    analyse = _Analyse(agent)
    analyse.prechauffer()
    assert _attendre_que(lambda: analyse._rapport is not None)

    # Le rafraîchissement de fond est rendu lent exprès : sans ça il finit avant
    # l'assertion et réécrit le rapport avec celui de l'agent factice, qui rend
    # toujours les deux écarts. On veut observer le retrait, pas le recalcul.
    agent.duree = 5.0

    debut = time.time()
    analyse.retirer({a})
    ecoule = time.time() - debut

    assert analyse._rapport.ecarts == (b,)
    # Un recalcul part bien derrière — c'est voulu — mais `retirer` lui-même
    # rend la main tout de suite. C'est toute la différence entre une requête
    # qui aboutit et un 504.
    assert ecoule < 0.5, "le retrait ne doit pas attendre l'analyse"


def test_retirer_ne_touche_pas_a_ce_qui_a_echoue():
    a, b = _ecart("a"), _ecart("b")
    agent = AgentFactice(rapport=_rapport(a, b))
    analyse = _Analyse(agent)
    analyse.prechauffer()
    assert _attendre_que(lambda: analyse._rapport is not None)
    agent.duree = 5.0

    analyse.retirer(set())          # rien n'a été écrit

    assert set(analyse._rapport.ecarts) == {a, b}
