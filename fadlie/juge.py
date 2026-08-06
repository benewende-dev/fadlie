"""Le juge : deux jeux portent-ils la même donnée ?

C'est la seule couche qui décide, et elle existe parce que la mesure l'exige.

- Le **nom** ne tranche pas : trois groupes homonymes sur quinze ne sont pas la
  même chose (`custom_sql_query` recouvre 0 % de ses colonnes, `promotions` 9 %).
- Le **lignage** ne tranche pas davantage : le graphe est d'un seul tenant, et
  deux copies d'une même table sont à la même distance que deux jeux pris au
  hasard.
- La **structure** ne suffit pas seule : `countries`, `regions`, `warehouses` et
  `product_categories` ont toutes quatre colonnes de forme voisine sans être la
  même donnée.

Une règle d'échec, héritée de Naaba et retournée. Là-bas, le juge rattrapait ses
propres pannes et rendait « ce n'est pas un doublon » — si bien qu'un rôle sans
droit d'invoquer le modèle éteignait la déduplication sans une ligne d'erreur.
Ici l'équivalent serait pire : un juge muet rendrait « aucune copie trouvée »,
c'est-à-dire **un catalogue en règle**. La panne se déguiserait en bonne
nouvelle. Donc `JugeError`, toujours, et un contrôle qui invoque vraiment le
modèle avant de rendre le moindre verdict.
"""
from __future__ import annotations

import dataclasses
import json
import re

from .candidats import Candidat
from .config import Config


class JugeError(RuntimeError):
    """Le juge n'a pas pu se prononcer. Jamais confondre avec « non »."""


@dataclasses.dataclass(frozen=True)
class Verdict:
    identiques: bool
    raison: str
    confiance: str  # "high" | "medium" | "low", tel que rendu par le modèle

    def __str__(self) -> str:
        return f"{'même donnée' if self.identiques else 'données distinctes'} — {self.raison}"


# Le modèle voit ce qu'un humain regarderait : les noms, les systèmes, et les
# colonnes avec leurs types. Pas le recouvrement calculé — un nombre l'ancrerait,
# alors qu'on veut son jugement sur le fond. Il ne voit pas non plus la distance
# de lignage, mesurée sans valeur pour cette question.
_CONSIGNE = """You compare two datasets from a data catalog and decide whether \
they hold THE SAME DATA — the same rows about the same real-world entities — \
possibly copied, replicated, or exported between systems.

Answer "same" when one is a copy, replica, export, or re-materialisation of the \
other, even across different platforms and even if column names differ in case \
or minor spelling.

Answer "different" when they merely resemble each other: reference tables with \
similar shapes, unrelated tables that share a generic name, aggregates or \
metrics derived from a table rather than a copy of it, or a subset of columns \
describing a different entity.

Reply with JSON only, no prose around it:
{"same": true|false, "confidence": "high"|"medium"|"low", "reason": "<one short sentence>"}"""


def _decrire(jeu, colonnes_max: int = 40) -> str:
    colonnes = jeu.colonnes[:colonnes_max]
    lignes = "\n".join(f"  - {c.nom} ({c.type_natif or 'unknown'})" for c in colonnes)
    reste = len(jeu.colonnes) - len(colonnes)
    if reste > 0:
        lignes += f"\n  … and {reste} more columns"
    return (f"platform: {jeu.plateforme}\n"
            f"name: {jeu.nom}\n"
            f"columns ({len(jeu.colonnes)}):\n{lignes}")


def message(candidat: Candidat) -> str:
    return (f"Dataset A\n{_decrire(candidat.gauche)}\n\n"
            f"Dataset B\n{_decrire(candidat.droite)}")


class Juge:
    """Un verdict par couple, rendu par un modèle, jamais deviné."""

    def __init__(self, config: Config, client=None) -> None:
        self.config = config
        self._client = client  # injectable : les tests ne facturent rien

    @property
    def client(self):
        if self._client is None:
            import boto3  # importé tard : le paquet n'est pas requis pour les tests

            self._client = boto3.client("bedrock-runtime", region_name=self.config.region)
        return self._client

    def _invoquer(self, texte: str) -> str:
        corps = {
            "system": [{"text": _CONSIGNE}],
            "messages": [{"role": "user", "content": [{"text": texte}]}],
            # Température nulle : deux exécutions sur le même couple doivent
            # rendre le même verdict, sinon la démonstration n'est pas
            # reproductible et le rapport n'est pas vérifiable.
            "inferenceConfig": {"maxTokens": 200, "temperature": 0.0},
        }
        try:
            reponse = self.client.invoke_model(
                modelId=self.config.modele_juge,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(corps),
            )
            charge = json.loads(reponse["body"].read())
        except Exception as e:  # noqa: BLE001 — on relaie, on n'avale pas
            # Ne surtout pas rendre « different » ici : ce serait un catalogue
            # déclaré sain par une panne.
            raise JugeError(
                f"le juge n'a pas pu se prononcer ({type(e).__name__}: {e}). "
                f"Modèle {self.config.modele_juge} en {self.config.region}. "
                f"À Francfort, l'identifiant nu échoue — il faut le profil "
                f"d'inférence régional."
            ) from e
        try:
            return charge["output"]["message"]["content"][0]["text"]
        except (KeyError, IndexError) as e:
            raise JugeError(f"réponse inattendue du modèle : {str(charge)[:200]}") from e

    @staticmethod
    def _lire(texte: str) -> Verdict:
        # Un modèle enveloppe volontiers son JSON dans du texte ou une clôture
        # Markdown. On extrait le premier objet plutôt que d'exiger la propreté.
        trouve = re.search(r"\{.*\}", texte, re.S)
        if not trouve:
            raise JugeError(f"le juge n'a pas rendu de JSON : {texte[:200]!r}")
        try:
            d = json.loads(trouve.group(0))
        except json.JSONDecodeError as e:
            raise JugeError(f"JSON illisible du juge : {trouve.group(0)[:200]!r}") from e
        if "same" not in d:
            raise JugeError(f"verdict sans champ « same » : {d}")
        if not isinstance(d["same"], bool):
            raise JugeError(f"« same » n'est pas un booléen : {d['same']!r}")
        return Verdict(
            identiques=d["same"],
            raison=str(d.get("reason", "")).strip() or "no reason given",
            confiance=str(d.get("confidence", "")).strip().lower() or "unknown",
        )

    def meme_donnee(self, candidat: Candidat) -> Verdict:
        return self._lire(self._invoquer(message(candidat)))

    def sonder(self) -> None:
        """Vérifie que le juge répond vraiment, avant tout verdict.

        Sans ce contrôle, un rôle qui ne peut pas invoquer le modèle produirait
        des rapports parfaitement vraisemblables — et vides. Un catalogue sans
        copies, c'est exactement ce qu'un client veut lire ; personne n'irait
        vérifier.
        """
        texte = self._invoquer(
            "Dataset A\nplatform: test\nname: probe\ncolumns (1):\n  - id (int)\n\n"
            "Dataset B\nplatform: test\nname: probe\ncolumns (1):\n  - id (int)"
        )
        self._lire(texte)  # lève si le modèle ne rend pas un verdict lisible
