"""La protection d'hôte : elle doit rester allumée, et connaître le domaine.

Le SDK MCP valide l'en-tête `Host`, et l'active tout seul dès que `host` vaut
`127.0.0.1` — ce qui est son défaut. Déployé derrière App Runner, le serveur
recevait donc toute session MCP par un « 421 Invalid Host header », pendant que
`/health` et le refus sans jeton restaient parfaitement verts.

Ces contrôles tiennent les deux moitiés du piège : que le domaine déclaré soit
accepté, et que la protection ne s'éteigne jamais parce qu'une variable manque.
"""
from __future__ import annotations

import pytest

from fadlie.serveur import _securite_transport


@pytest.fixture(autouse=True)
def _sans_variable(monkeypatch):
    monkeypatch.delenv("FADLIE_ALLOWED_HOSTS", raising=False)


def test_sans_variable_on_garde_les_formes_locales():
    s = _securite_transport()
    assert s.enable_dns_rebinding_protection is True
    assert "127.0.0.1:*" in s.allowed_hosts


def test_une_variable_vide_n_ouvre_pas_tout():
    """Le mode de panne qui compte : la variable existe mais ne dit rien.

    Un serveur qui accepterait alors n'importe quel `Host` n'aurait plus de
    protection du tout, et répondrait exactement comme un serveur sain.
    """
    import os

    os.environ["FADLIE_ALLOWED_HOSTS"] = "  ,  "
    try:
        s = _securite_transport()
    finally:
        del os.environ["FADLIE_ALLOWED_HOSTS"]
    assert s.allowed_hosts == ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    assert "*" not in s.allowed_hosts


def test_le_domaine_declare_est_accepte_avec_et_sans_port(monkeypatch):
    """Derrière un proxy, `Host` porte parfois `:443` et parfois rien."""
    monkeypatch.setenv("FADLIE_ALLOWED_HOSTS", "yvh3rv2qmp.eu-central-1.awsapprunner.com")
    s = _securite_transport()

    from mcp.server.transport_security import TransportSecurityMiddleware

    valider = TransportSecurityMiddleware(s)._validate_host
    assert valider("yvh3rv2qmp.eu-central-1.awsapprunner.com")
    assert valider("yvh3rv2qmp.eu-central-1.awsapprunner.com:443")
    assert not valider("attaquant.example.com")
    assert not valider(None)


def test_plusieurs_hotes(monkeypatch):
    monkeypatch.setenv("FADLIE_ALLOWED_HOSTS", "a.example.com, b.example.com")
    s = _securite_transport()
    assert "a.example.com" in s.allowed_hosts
    assert "b.example.com" in s.allowed_hosts
