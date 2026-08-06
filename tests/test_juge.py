"""Le juge, sans réseau ni facture.

L'invariant que ces tests défendent tient en une phrase : **une panne du juge ne
doit jamais ressembler à un verdict**. Dans Naaba, le juge rattrapait ses erreurs
et rendait « ce n'est pas un doublon » ; un rôle sans droit d'invoquer le modèle
éteignait donc la déduplication en silence. Ici la conséquence serait pire — un
juge muet rendrait « aucune copie trouvée », c'est-à-dire un catalogue en règle.
Une panne déguisée en bonne nouvelle est la panne qu'on ne cherche jamais.
"""
from __future__ import annotations

import io
import json

import pytest

from fadlie.candidats import Candidat
from fadlie.catalogue import Colonne, Jeu
from fadlie.config import Config
from fadlie.juge import Juge, JugeError, Verdict, message


def config() -> Config:
    return Config(gms_url="http://exemple:8080", gms_token="x" * 40,
                  region="eu-central-1", modele_juge="eu.amazon.nova-micro-v1:0")


def jeu(nom: str, plateforme: str, colonnes: list[str]) -> Jeu:
    return Jeu(
        urn=f"urn:li:dataset:(urn:li:dataPlatform:{plateforme},{nom},PROD)",
        nom=nom, plateforme=plateforme, description=None, domaine=None,
        proprietaires=(), etiquettes=frozenset(), termes=frozenset(),
        colonnes=tuple(Colonne(nom=c, type_natif="varchar", description=None,
                               etiquettes=frozenset(), termes=frozenset())
                       for c in colonnes),
    )


def candidat(gauche: Jeu, droite: Jeu) -> Candidat:
    communes = gauche.noms_colonnes & droite.noms_colonnes
    return Candidat(gauche=gauche, droite=droite,
                    recouvrement=len(communes) / len(gauche.noms_colonnes | droite.noms_colonnes),
                    meme_nom=gauche.nom.lower() == droite.nom.lower(),
                    colonnes_communes=tuple(sorted(communes)),
                    colonnes_propres_gauche=(), colonnes_propres_droite=())


class ClientFactice:
    """Rend ce qu'on lui dit, ou lève ce qu'on lui donne."""

    def __init__(self, texte: str | None = None, erreur: Exception | None = None):
        self.texte, self.erreur = texte, erreur
        self.appels: list[dict] = []

    def invoke_model(self, **kwargs):
        self.appels.append(kwargs)
        if self.erreur:
            raise self.erreur
        charge = {"output": {"message": {"content": [{"text": self.texte}]}}}
        return {"body": io.BytesIO(json.dumps(charge).encode())}


COUPLE = None


@pytest.fixture
def couple():
    return candidat(jeu("customers", "dbt", ["customer_id", "cust_email"]),
                    jeu("customers", "postgres", ["customer_id", "cust_email"]))


class TestLecture:
    def test_un_verdict_propre(self, couple):
        client = ClientFactice('{"same": true, "confidence": "high", "reason": "same columns"}')
        v = Juge(config(), client).meme_donnee(couple)
        assert v == Verdict(identiques=True, raison="same columns", confiance="high")

    def test_le_json_enveloppe_de_texte_est_lu(self, couple):
        # Un modèle ajoute volontiers une clôture Markdown ou une phrase. Exiger
        # la propreté ferait échouer un verdict parfaitement valide.
        client = ClientFactice(
            'Here is my answer:\n```json\n{"same": false, "reason": "different entities"}\n```')
        v = Juge(config(), client).meme_donnee(couple)
        assert not v.identiques
        assert v.raison == "different entities"
        assert v.confiance == "unknown"

    def test_sans_json_le_juge_leve(self, couple):
        with pytest.raises(JugeError, match="pas rendu de JSON"):
            Juge(config(), ClientFactice("They look the same to me.")).meme_donnee(couple)

    def test_un_json_tronque_na_pas_de_json_a_lire(self, couple):
        # Sans accolade fermante, il n'y a rien à extraire : c'est l'autre
        # chemin d'erreur, et il lève aussi.
        with pytest.raises(JugeError, match="pas rendu de JSON"):
            Juge(config(), ClientFactice('{"same": tru')).meme_donnee(couple)

    def test_json_bien_delimite_mais_invalide_leve(self, couple):
        with pytest.raises(JugeError, match="JSON illisible"):
            Juge(config(), ClientFactice('{"same": tru}')).meme_donnee(couple)

    def test_sans_champ_same_leve(self, couple):
        with pytest.raises(JugeError, match="sans .* same"):
            Juge(config(), ClientFactice('{"reason": "hmm"}')).meme_donnee(couple)

    def test_same_non_booleen_leve(self, couple):
        # « "same": "yes" » est vrai au sens de Python. Sans ce contrôle, une
        # chaîne vide vaudrait « distinct » et « no » vaudrait « même ».
        for valeur in ('"yes"', '"no"', '1', '"true"'):
            with pytest.raises(JugeError, match="booléen"):
                Juge(config(), ClientFactice(
                    '{"same": %s, "reason": "x"}' % valeur)).meme_donnee(couple)


class TestUnePanneNestPasUnVerdict:
    """Le cœur : aucune panne ne doit se lire comme « données distinctes »."""

    def test_une_panne_du_client_leve(self, couple):
        juge = Juge(config(), ClientFactice(erreur=RuntimeError("AccessDenied")))
        with pytest.raises(JugeError) as e:
            juge.meme_donnee(couple)
        assert "AccessDenied" in str(e.value)

    def test_le_message_de_panne_oriente_vers_le_profil_regional(self, couple):
        # La façon dont le juge meurt vraiment à Francfort : l'identifiant nu.
        juge = Juge(config(), ClientFactice(erreur=RuntimeError("ValidationException")))
        with pytest.raises(JugeError, match="profil"):
            juge.meme_donnee(couple)

    def test_une_reponse_sans_contenu_leve(self, couple):
        class Vide:
            def invoke_model(self, **_):
                return {"body": io.BytesIO(b'{"output": {}}')}

        with pytest.raises(JugeError, match="inattendue"):
            Juge(config(), Vide()).meme_donnee(couple)

    def test_la_sonde_leve_quand_le_juge_est_mort(self):
        with pytest.raises(JugeError):
            Juge(config(), ClientFactice(erreur=RuntimeError("nope"))).sonder()

    def test_la_sonde_passe_quand_le_juge_repond(self):
        Juge(config(), ClientFactice('{"same": true, "reason": "ok"}')).sonder()


class TestMessage:
    def test_le_message_porte_les_deux_jeux(self, couple):
        texte = message(couple)
        assert "platform: dbt" in texte and "platform: postgres" in texte
        assert texte.count("customer_id") == 2

    def test_les_colonnes_sont_tronquees_avec_leur_compte(self):
        large = jeu("large", "snowflake", [f"c{i}" for i in range(60)])
        texte = message(candidat(large, jeu("autre", "dbt", ["c0"])))
        assert "columns (60)" in texte
        assert "and 20 more columns" in texte

    def test_le_recouvrement_calcule_nest_pas_donne_au_juge(self, couple):
        # On veut son jugement sur le fond ; un nombre l'ancrerait. La distance
        # de lignage non plus : mesurée sans valeur pour cette question.
        texte = message(couple)
        assert "100%" not in texte and "overlap" not in texte.lower()
        assert "lineage" not in texte.lower() and "distance" not in texte.lower()


class TestInvocation:
    def test_la_temperature_est_nulle(self, couple):
        # Deux exécutions sur le même couple doivent rendre le même verdict,
        # sinon un rapport n'est pas vérifiable.
        client = ClientFactice('{"same": true, "reason": "ok"}')
        Juge(config(), client).meme_donnee(couple)
        corps = json.loads(client.appels[0]["body"])
        assert corps["inferenceConfig"]["temperature"] == 0.0

    def test_le_modele_appele_est_celui_de_la_configuration(self, couple):
        client = ClientFactice('{"same": true, "reason": "ok"}')
        Juge(config(), client).meme_donnee(couple)
        assert client.appels[0]["modelId"] == "eu.amazon.nova-micro-v1:0"
