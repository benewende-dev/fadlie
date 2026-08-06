"""L'application des écarts, sans écrire nulle part.

Ce qui est défendu ici : **à blanc par défaut**, et **un échec partiel se dit**.
Écrire 580 valeurs, c'est 580 occasions d'échouer ; rendre « appliqué » parce que
la boucle est allée au bout serait un mensonge qu'on ne découvre qu'en ouvrant
le catalogue.
"""
from __future__ import annotations

import pytest

from fadlie.catalogue import CatalogueError
from fadlie.ecart import Ecart
from fadlie.reparer import Resultat, appliquer


class CatalogueFactice:
    """Note ce qu'on lui demande, échoue sur ce qu'on lui dit d'échouer."""

    def __init__(self, echouer_sur: set[str] | None = None):
        self.appels: list[tuple] = []
        self.echouer_sur = echouer_sur or set()

    def _noter(self, quoi, urn, *reste):
        if urn in self.echouer_sur:
            raise CatalogueError(f"refus simulé sur {urn}")
        self.appels.append((quoi, urn, *reste))

    def poser_proprietaires(self, urn, p, type_de_role="TECHNICAL_OWNER"):
        self._noter("owner", urn, tuple(p))

    def poser_description(self, urn, d, colonne=None):
        self._noter("description", urn, d, colonne)

    def poser_etiquettes(self, urn, e, colonne=None):
        self._noter("tag", urn, tuple(e), colonne)

    def poser_termes(self, urn, t, colonne=None):
        self._noter("term", urn, tuple(t), colonne)

    def poser_domaine(self, urn, d):
        self._noter("domain", urn, d)


def ecart(genre="column_tag", cible="urn:cible", valeur="urn:li:tag:PII_Data",
          colonne="cust_email") -> Ecart:
    return Ecart(cible=cible, source="urn:source", genre=genre,
                 valeur=valeur, colonne=colonne)


class TestABlancParDefaut:
    def test_sans_rien_dire_on_necrit_pas(self):
        # Le défaut est dans le code, pas seulement dans l'interface : un appel
        # qui oublie le paramètre ne doit rien écrire.
        catalogue = CatalogueFactice()
        r = appliquer(catalogue, [ecart(), ecart()])
        assert catalogue.appels == []
        assert (r.poses, r.simules) == (0, 2)
        assert "rien n'a été écrit" in r.resume()

    def test_pour_de_vrai_ecrit(self):
        catalogue = CatalogueFactice()
        r = appliquer(catalogue, [ecart()], pour_de_vrai=True)
        assert catalogue.appels == [
            ("tag", "urn:cible", ("urn:li:tag:PII_Data",), "cust_email")]
        assert (r.poses, r.simules) == (1, 0)


class TestChaqueGenreVaAuBonEndroit:
    @pytest.mark.parametrize("genre,attendu", [
        ("owner", "owner"),
        ("description", "description"),
        ("column_description", "description"),
        ("column_tag", "tag"),
        ("column_term", "term"),
        ("domain", "domain"),
    ])
    def test_le_genre_choisit_la_mutation(self, genre, attendu):
        catalogue = CatalogueFactice()
        appliquer(catalogue, [ecart(genre=genre)], pour_de_vrai=True)
        assert catalogue.appels[0][0] == attendu

    def test_une_description_de_jeu_ne_vise_pas_une_colonne(self):
        catalogue = CatalogueFactice()
        appliquer(catalogue, [ecart(genre="description", valeur="Master")],
                  pour_de_vrai=True)
        assert catalogue.appels[0] == ("description", "urn:cible", "Master", None)

    def test_une_description_de_colonne_vise_la_colonne(self):
        catalogue = CatalogueFactice()
        appliquer(catalogue, [ecart(genre="column_description", valeur="Primary key")],
                  pour_de_vrai=True)
        assert catalogue.appels[0][3] == "cust_email"


class TestUnEchecPartielSeDit:
    def test_un_refus_narrete_pas_les_autres(self):
        catalogue = CatalogueFactice(echouer_sur={"urn:fache"})
        ecarts = [ecart(cible="urn:a"), ecart(cible="urn:fache"), ecart(cible="urn:b")]
        r = appliquer(catalogue, ecarts, pour_de_vrai=True)
        assert r.poses == 2
        assert len(r.echecs) == 1
        assert r.echecs[0][0].cible == "urn:fache"
        assert "partiellement" in r.resume()

    def test_le_total_reste_juste(self):
        catalogue = CatalogueFactice(echouer_sur={"urn:fache"})
        r = appliquer(catalogue, [ecart(cible="urn:a"), ecart(cible="urn:fache")],
                      pour_de_vrai=True)
        assert r.total == 2

    def test_tout_reussi_ne_parle_pas_dechec(self):
        r = appliquer(CatalogueFactice(), [ecart()], pour_de_vrai=True)
        assert "échec" not in r.resume()
        assert r.resume() == "1 écarts posés"


class TestRienAFaire:
    def test_aucun_ecart(self):
        r = appliquer(CatalogueFactice(), [], pour_de_vrai=True)
        assert (r.poses, r.simules, r.echecs, r.total) == (0, 0, (), 0)


def test_le_resume_des_outils_est_en_anglais():
    """Une réponse d'outil MCP se lit par n'importe qui.

    Piège déjà vu et déjà corrigé pour les désaccords : la prose française
    d'une aide de travail s'était retrouvée dans une surface publique.
    `resume()` reste français, `summary()` ne l'est pas.
    """
    r = Resultat(poses=3, simules=0, echecs=())
    assert r.summary() == "3 gaps written"
    assert "écarts" in r.resume()

    blanc = Resultat(poses=0, simules=7, echecs=())
    assert blanc.summary() == "7 gaps simulated, nothing was written"
