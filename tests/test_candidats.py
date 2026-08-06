"""Les tests de la présélection : aucun réseau, aucune facture.

Ce qu'ils défendent, ce sont les faits *mesurés* sur le vrai graphe. Chaque cas
porte le nom du jeu qui l'a produit, pour qu'on sache d'où vient la règle.
"""
from __future__ import annotations

import itertools

import pytest

from fadlie.candidats import Candidat, normaliser, preselectionner, recouvrement
from fadlie.catalogue import Colonne, Jeu


_compteur = itertools.count()


def jeu(nom: str, plateforme: str, colonnes: list[str], *, amont=0, aval=0) -> Jeu:
    # Le chemin porte un numéro : dans le vrai graphe, les quatre jeux tableau
    # nommés « Custom SQL Query » ont des URN distincts. Sans ce détail, deux
    # jeux du même nom sur la même plateforme partageraient un URN et la garde
    # « un jeu ne se compare pas à lui-même » les écarterait à tort.
    return Jeu(
        urn=f"urn:li:dataset:(urn:li:dataPlatform:{plateforme},"
            f"db.schema.{nom}_{next(_compteur)},PROD)",
        nom=nom,
        plateforme=plateforme,
        description=None,
        domaine=None,
        proprietaires=(),
        etiquettes=frozenset(),
        termes=frozenset(),
        colonnes=tuple(
            Colonne(nom=c, type_natif="varchar", description=None,
                    etiquettes=frozenset(), termes=frozenset())
            for c in colonnes
        ),
        lignage_amont=amont,
        lignage_aval=aval,
    )


CLIENTS = ["customer_id", "cust_first_name", "cust_last_name", "cust_email",
           "phone_number", "town_city", "zipcode"]


class TestNormaliser:
    def test_la_casse_et_les_separateurs_ne_distinguent_pas(self):
        assert normaliser("ORDER_DETAILS") == normaliser("order_details")
        assert normaliser("Order Details") == normaliser("order_details")

    def test_un_suffixe_de_copie_est_retire(self):
        # Mesuré : ORDER_DETAILS_REPLICA est une copie littérale de order_details.
        assert normaliser("ORDER_DETAILS_REPLICA") == "order_details"
        assert normaliser("customers_staging") == "customers"

    def test_un_seul_suffixe_est_retire(self):
        # Sinon `orders_raw_old` finirait sur `order`, et deux jeux distincts se
        # confondraient par érosion.
        assert normaliser("orders_raw_old") == "orders_raw"


class TestRecouvrement:
    def test_la_casse_ne_cree_pas_un_ecart(self):
        # Mesuré : les 18 colonnes marquées de dbt/order_details se retrouvent une
        # pour une dans powerbi/ORDER_DETAILS, à la seule casse près.
        a = jeu("order_details", "dbt", CLIENTS)
        b = jeu("ORDER_DETAILS", "powerbi", [c.upper() for c in CLIENTS])
        assert recouvrement(a, b) == 1.0

    def test_deux_jeux_sans_colonne_commune(self):
        assert recouvrement(jeu("a", "dbt", ["x"]), jeu("b", "s3", ["y"])) == 0.0

    def test_un_jeu_sans_colonne_ne_ressemble_a_rien(self):
        # Un schéma absent n'est pas un schéma vide identique à un autre : sans
        # cette garde, tous les jeux sans schéma seraient jumeaux entre eux.
        assert recouvrement(jeu("a", "dbt", []), jeu("b", "s3", [])) == 0.0


class TestPreselection:
    def test_les_jumeaux_sur_quatre_plateformes_sont_retenus(self):
        jeux = [jeu("customers", p, CLIENTS) for p in ("dbt", "snowflake", "postgres", "s3")]
        candidats = preselectionner(jeux)
        # Quatre jeux identiques : les six couples.
        assert len(candidats) == 6
        assert all(c.recouvrement == 1.0 and c.meme_nom for c in candidats)

    def test_le_meme_nom_suffit_a_retenir_meme_sans_recouvrement(self):
        # Mesuré : `custom_sql_query` réunit quatre jeux tableau du même nom dont
        # les colonnes ne se recouvrent pas. On les *retient* — c'est au juge de
        # dire non, pas à la présélection.
        a = jeu("custom_sql_query", "tableau", ["mesure_1", "date"])
        b = jeu("custom_sql_query", "tableau", ["pays", "ventes"])
        candidats = preselectionner([a, b])
        assert len(candidats) == 1
        assert candidats[0].recouvrement == 0.0
        assert candidats[0].meme_nom

    def test_un_recouvrement_fort_suffit_sans_le_nom(self):
        # Une copie renommée : le nom ne dit rien, la structure si.
        a = jeu("customers", "postgres", CLIENTS)
        b = jeu("clients_export", "s3", CLIENTS)
        candidats = preselectionner([a, b])
        assert len(candidats) == 1
        assert not candidats[0].meme_nom

    def test_deux_jeux_etrangers_ne_sont_pas_retenus(self):
        a = jeu("customers", "dbt", CLIENTS)
        b = jeu("warehouses", "dbt", ["warehouse_id", "warehouse_name"])
        assert preselectionner([a, b]) == []

    def test_le_seuil_est_respecte(self):
        a = jeu("a", "dbt", ["x1", "x2", "x3", "x4"])
        b = jeu("b", "s3", ["x1", "x2", "y3", "y4"])   # Jaccard = 2/6 ≈ 0,33
        assert preselectionner([a, b], seuil=0.3) != []
        assert preselectionner([a, b], seuil=0.4) == []


    def test_un_jeu_ne_se_compare_pas_a_lui_meme(self):
        assert preselectionner([jeu("customers", "dbt", CLIENTS)]) == []


class TestDistanceDeLignage:
    """Le cœur de la correction du 6 août 2026.

    La question n'est pas « ce jeu a-t-il du lignage » — ils en ont tous — mais
    « existe-t-il un chemin entre ces deux copies ». Mesuré : pour les 11 tables
    répliquées sur quatre plateformes, un seul couple sur six est relié, toujours
    dbt ↔ snowflake à distance 2, et les copies postgres et s3 sont dans une
    autre composante. La première version de ces notes disait « 24 jeux sans
    lignage » : c'était l'index qui n'avait pas fini de se remplir.
    """

    def test_sans_graphe_on_ne_pretend_rien(self):
        # Ne pas confondre « pas de chemin » et « je n'ai pas regardé ». C'est
        # cette confusion-là qui a produit la mesure fausse.
        c = preselectionner([jeu("customers", "postgres", CLIENTS),
                             jeu("customers", "s3", CLIENTS)])[0]
        assert not c.distance_connue
        assert not c.sans_lien
        assert "lignage" not in c.resume()

    def test_deux_copies_dans_des_composantes_differentes(self):
        a = jeu("customers", "postgres", CLIENTS)
        b = jeu("customers", "s3", CLIENTS)
        # Chacune a du lignage — vers ailleurs. C'est le cas réel.
        graphe = {a.urn: {"urn:autre:1"}, "urn:autre:1": {a.urn},
                  b.urn: {"urn:autre:2"}, "urn:autre:2": {b.urn}}
        c = preselectionner([a, b], graphe=graphe)[0]
        assert c.distance_connue
        assert c.distance_lignage is None
        assert c.sans_lien
        assert "aucun chemin de lignage" in c.resume()

    def test_deux_copies_reliees_en_passant(self):
        # dbt ↔ snowflake : reliés, mais à distance 2, jamais directement.
        a = jeu("customers", "dbt", CLIENTS)
        b = jeu("customers", "snowflake", CLIENTS)
        pivot = "urn:li:dataset:(urn:li:dataPlatform:dbt,pivot,PROD)"
        graphe = {a.urn: {pivot}, pivot: {a.urn, b.urn}, b.urn: {pivot}}
        c = preselectionner([a, b], graphe=graphe)[0]
        assert c.distance_lignage == 2
        assert not c.sans_lien
        assert "distance 2" in c.resume()

    def test_les_couples_sans_chemin_viennent_en_tete(self):
        # C'est là qu'est le trou : ce qu'aucune propagation n'atteindra.
        relies = [jeu("orders", "dbt", ["order_id", "total"]),
                  jeu("orders", "snowflake", ["order_id", "total"])]
        coupes = [jeu("customers", "postgres", CLIENTS),
                  jeu("customers", "s3", CLIENTS)]
        graphe = {relies[0].urn: {relies[1].urn}, relies[1].urn: {relies[0].urn},
                  coupes[0].urn: set(), coupes[1].urn: set()}
        candidats = preselectionner(relies + coupes, graphe=graphe)
        assert candidats[0].sans_lien
        assert not candidats[-1].sans_lien


class TestCandidatResume:
    def test_le_resume_dit_ce_qui_compte(self):
        a = jeu("customers", "postgres", CLIENTS)
        b = jeu("customers", "s3", CLIENTS)
        c = preselectionner([a, b], graphe={a.urn: set(), b.urn: set()})[0]
        texte = c.resume()
        assert "postgres/customers" in texte
        assert "s3/customers" in texte
        assert "100%" in texte
        assert "aucun chemin de lignage" in texte
