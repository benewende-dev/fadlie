"""Configuration lue une fois, et jamais devinée.

Règle héritée de Naaba : pas de repli implicite sur une valeur qui *semble*
raisonnable. Un défaut silencieux se remarque le jour où il est faux, c'est-à-dire
trop tard. Ce qui manque lève, avec le nom de la variable à renseigner.
"""
from __future__ import annotations

import dataclasses
import os

# À Francfort, la plupart des modèles ne s'invoquent que par leur profil
# d'inférence régional : `eu.amazon.nova-micro-v1:0` répond, `amazon.nova-micro-v1:0`
# rend une ValidationException. Mesuré, pour Naaba puis à nouveau ici.
PREFIXES_PROFIL = {"eu-": "eu.", "us-": "us.", "ap-": "apac."}


class ConfigError(RuntimeError):
    """Une variable manque, ou son contenu ne tient pas debout."""


def _exiger(nom: str) -> str:
    valeur = os.environ.get(nom, "").strip()
    if not valeur:
        raise ConfigError(
            f"{nom} n'est pas renseignée. Voir .env.example ; charger avec "
            f"`set -a && . ./.env && set +a`."
        )
    return valeur


def profil_regional(modele: str, region: str) -> str:
    """Préfixe le modèle par le profil d'inférence de sa région, si besoin.

    Un identifiant déjà préfixé est rendu tel quel : on ne veut pas de
    `eu.eu.amazon…` si quelqu'un renseigne la forme complète.
    """
    if "." in modele.split(":")[0].split(".")[0] or modele.startswith(("eu.", "us.", "apac.")):
        return modele
    for debut, prefixe in PREFIXES_PROFIL.items():
        if region.startswith(debut):
            return prefixe + modele
    return modele


@dataclasses.dataclass(frozen=True)
class Config:
    gms_url: str
    gms_token: str
    region: str
    modele_juge: str
    # Au-dessus de ce recouvrement de colonnes, deux jeux sont *candidats*. Ce
    # n'est pas un verdict : mesuré, 3 groupes homonymes sur 15 ne sont pas la
    # même chose. C'est le juge qui trancherait. Voir docs/candidats.md.
    recouvrement_minimum: float = 0.6

    @classmethod
    def depuis_environnement(cls) -> "Config":
        region = os.environ.get("AWS_REGION", "").strip() or "eu-central-1"
        modele = os.environ.get("FADLIE_JUDGE_MODEL", "").strip() or "amazon.nova-micro-v1:0"
        recouvrement = os.environ.get("FADLIE_MIN_OVERLAP", "").strip()
        try:
            seuil = float(recouvrement) if recouvrement else 0.6
        except ValueError as e:
            raise ConfigError(f"FADLIE_MIN_OVERLAP n'est pas un nombre : {recouvrement!r}") from e
        if not 0.0 < seuil <= 1.0:
            raise ConfigError(f"FADLIE_MIN_OVERLAP doit être dans ]0, 1] ; reçu {seuil}")

        return cls(
            gms_url=_exiger("DATAHUB_GMS_URL").rstrip("/"),
            gms_token=_exiger("DATAHUB_GMS_TOKEN"),
            region=region,
            modele_juge=profil_regional(modele, region),
            recouvrement_minimum=seuil,
        )

    def resume(self) -> dict[str, str]:
        """De quoi vérifier la configuration sans jamais montrer le jeton.

        Le jeton DataHub ouvre l'écriture sur tout le catalogue. Il ne doit
        apparaître ni dans un journal, ni dans une sortie de commande, ni dans
        une réponse d'outil — un test l'impose.
        """
        return {
            "gms_url": self.gms_url,
            "gms_token": f"…{self.gms_token[-4:]} ({len(self.gms_token)} caractères)",
            "region": self.region,
            "modele_juge": self.modele_juge,
            "recouvrement_minimum": f"{self.recouvrement_minimum:.2f}",
        }
