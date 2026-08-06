"""Les écarts de gouvernance, sans réseau.

Deux invariants à défendre, et ils comptent plus que le reste :

1. **Aucun écart sans source.** Fadlie recopie, il ne rédige pas. Une valeur qui
   n'a pas de jeu d'origine nommé ne doit pas pouvoir exister — pas même par
   accident de construction.
2. **Un désaccord n'est pas un écart.** Deux jumeaux qui affirment des choses
   différentes ne se départagent pas tout seuls, et surtout pas dans le sens de
   l'ordre alphabétique.
"""
from __future__ import annotations

import pytest

from fadlie.catalogue import Colonne, Jeu
from fadlie.ecart import Desaccord, Ecart, comparer, par_cible


def colonne(nom, *, etiquettes=(), termes=(), description=None) -> Colonne:
    return Colonne(nom=nom, type_natif="varchar", description=description,
                   etiquettes=frozenset(etiquettes), termes=frozenset(termes))


def jeu(plateforme, nom, colonnes, *, domaine=None, description=None,
        proprietaires=()) -> Jeu:
    return Jeu(
        urn=f"urn:li:dataset:(urn:li:dataPlatform:{plateforme},{nom},PROD)",
        nom=nom, plateforme=plateforme, description=description, domaine=domaine,
        proprietaires=tuple(proprietaires), etiquettes=frozenset(),
        termes=frozenset(), colonnes=tuple(colonnes),
    )


def urn(plateforme, nom="customers"):
    return f"urn:li:dataset:(urn:li:dataPlatform:{plateforme},{nom},PROD)"


class TestLInvariantDeSource:
    def test_un_ecart_sans_source_est_impossible(self):
        with pytest.raises(ValueError, match="recopie"):
            Ecart(cible="urn:a", source="", genre="domain", valeur="Ventes")

    def test_un_genre_inconnu_est_refuse(self):
        with pytest.raises(ValueError, match="genre inconnu"):
            Ecart(cible="urn:a", source="urn:b", genre="couleur", valeur="bleu")

    def test_tout_ecart_produit_porte_une_source_reelle(self):
        # Le cas mesuré : dbt gouverné, les trois autres nus.
        groupe = [
            jeu("dbt", "customers", [colonne("cust_email", termes=["urn:li:glossaryTerm:PII"])],
                domaine="Data Platform Team", description="Customer master",
                proprietaires=("urn:li:corpGroup:data-platform",)),
            jeu("postgres", "customers", [colonne("cust_email")]),
            jeu("s3", "customers", [colonne("cust_email")]),
        ]
        ecarts, desaccords = comparer(groupe)
        assert ecarts and not desaccords
        urns = {j.urn for j in groupe}
        assert all(e.source in urns and e.source != e.cible for e in ecarts)


class TestPropagation:
    def test_le_domaine_et_la_description_se_propagent(self):
        groupe = [
            jeu("dbt", "customers", [colonne("id")], domaine="E-Commerce",
                description="Customer master"),
            jeu("postgres", "customers", [colonne("id")]),
        ]
        ecarts, _ = comparer(groupe)
        genres = {(e.genre, e.valeur, e.cible) for e in ecarts}
        assert ("domain", "E-Commerce", urn("postgres")) in genres
        assert ("description", "Customer master", urn("postgres")) in genres

    def test_les_proprietaires_sunissent_dans_les_deux_sens(self):
        # Deux propriétaires différents ne se contredisent pas : chacun reçoit
        # celui de l'autre. On n'en retire jamais.
        groupe = [
            jeu("dbt", "customers", [colonne("id")], proprietaires=("urn:li:corpuser:alice",)),
            jeu("s3", "customers", [colonne("id")], proprietaires=("urn:li:corpuser:bob",)),
        ]
        ecarts, desaccords = comparer(groupe)
        assert not desaccords
        attendus = {(urn("dbt"), "urn:li:corpuser:bob"),
                    (urn("s3"), "urn:li:corpuser:alice")}
        assert {(e.cible, e.valeur) for e in ecarts if e.genre == "owner"} == attendus

    def test_une_etiquette_de_colonne_traverse(self):
        # Le cas mesuré : customers.customer_id ne porte PII_Data que sur postgres.
        pii = "urn:li:tag:PII_Data"
        groupe = [
            jeu("postgres", "customers", [colonne("customer_id", etiquettes=[pii])]),
            jeu("dbt", "customers", [colonne("customer_id")]),
            jeu("s3", "customers", [colonne("customer_id")]),
        ]
        ecarts, _ = comparer(groupe)
        cibles = {e.cible for e in ecarts if e.genre == "column_tag" and e.valeur == pii}
        assert cibles == {urn("dbt"), urn("s3")}
        assert all(e.source == urn("postgres")
                   for e in ecarts if e.genre == "column_tag")

    def test_seules_les_colonnes_communes_sont_comparees(self):
        # Une colonne qui n'existe que d'un côté ne « manque » pas de l'autre.
        groupe = [
            jeu("dbt", "customers", [colonne("id"), colonne("extra", etiquettes=["urn:li:tag:x"])]),
            jeu("s3", "customers", [colonne("id")]),
        ]
        ecarts, _ = comparer(groupe)
        assert not [e for e in ecarts if e.colonne == "extra"]

    def test_la_casse_de_la_colonne_cible_est_respectee(self):
        # On compare `CUST_EMAIL` et `cust_email` comme la même colonne, mais on
        # écrit sur le chemin tel que le jeu cible le porte : DataHub n'écrirait
        # rien sur un chemin qui n'existe pas chez lui.
        groupe = [
            jeu("dbt", "customers", [colonne("cust_email", etiquettes=["urn:li:tag:PII_Data"])]),
            jeu("snowflake", "CUSTOMERS", [colonne("CUST_EMAIL")]),
        ]
        ecarts, _ = comparer(groupe)
        chez_snowflake = [e for e in ecarts if e.cible == urn("snowflake", "CUSTOMERS")]
        assert chez_snowflake
        assert all(e.colonne == "CUST_EMAIL" for e in chez_snowflake if e.colonne)


class TestDesaccord:
    def test_deux_domaines_differents_ne_se_departagent_pas(self):
        groupe = [
            jeu("dbt", "customers", [colonne("id")], domaine="E-Commerce"),
            jeu("snowflake", "customers", [colonne("id")], domaine="Ecommerce Operations"),
            jeu("s3", "customers", [colonne("id")]),
        ]
        ecarts, desaccords = comparer(groupe)
        assert not [e for e in ecarts if e.genre == "domain"]
        assert len([d for d in desaccords if d.genre == "domain"]) == 1

    def test_deux_descriptions_de_colonne_differentes_aussi(self):
        groupe = [
            jeu("dbt", "customers", [colonne("id", description="Primary key")]),
            jeu("s3", "customers", [colonne("id", description="Row identifier")]),
        ]
        _, desaccords = comparer(groupe)
        assert [d.genre for d in desaccords] == ["column_description"]
        assert desaccords[0].colonne == "id"

    def test_un_desaccord_nempeche_pas_le_reste_de_passer(self):
        groupe = [
            jeu("dbt", "customers", [colonne("id", etiquettes=["urn:li:tag:PII_Data"])],
                domaine="E-Commerce"),
            jeu("s3", "customers", [colonne("id")], domaine="Autre"),
        ]
        ecarts, desaccords = comparer(groupe)
        assert desaccords
        assert [e.genre for e in ecarts] == ["column_tag"]


class TestDeterminisme:
    def test_deux_appels_rendent_le_meme_plan(self):
        groupe = [
            jeu("dbt", "customers", [colonne("id", termes=["urn:li:glossaryTerm:A"])],
                domaine="E-Commerce", proprietaires=("urn:li:corpuser:alice",)),
            jeu("s3", "customers", [colonne("id")]),
            jeu("postgres", "customers", [colonne("id")]),
        ]
        premier, _ = comparer(groupe)
        second, _ = comparer(list(reversed(groupe)))
        assert premier == second


class TestGroupement:
    def test_par_cible_regroupe(self):
        groupe = [
            jeu("dbt", "customers", [colonne("id")], domaine="E-Commerce",
                description="Master"),
            jeu("s3", "customers", [colonne("id")]),
        ]
        ecarts, _ = comparer(groupe)
        groupes = par_cible(ecarts)
        assert set(groupes) == {urn("s3")}
        assert len(groupes[urn("s3")]) == 2


class TestGroupeTropPetit:
    def test_un_seul_jeu_na_pas_decart(self):
        assert comparer([jeu("dbt", "customers", [colonne("id")])]) == ([], [])
