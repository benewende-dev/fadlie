# La vidéo — moins de trois minutes

**Faite, le 6 août 2026 : 2 min 40, 1080p, voix Liam, sous-titres anglais.**
Ce fichier a servi à la tourner ; il est gardé parce qu'il dit *pourquoi* chaque
plan est là, ce que la vidéo finie ne dit pas.

Ce qui a changé en cours de route, et qui vaut d'être su :

- **Le plan principal est passé de `customers` à `products`.** `customers` avait
  été réparé par Fadlie lui-même pendant les essais, donc il n'avait plus rien à
  montrer. `--jeu` existe pour ça.
- **Le premier montage coupait le bas de l'image.** La fenêtre de lignes était
  fixée à trente-quatre alors que vingt-quatre seulement tiennent à cette taille.
  Ce qui disparaissait, c'étaient exactement les deux lignes que la voix
  annonçait : « 53 values written » et « gaps now: 0 ». La fenêtre est maintenant
  **calculée** depuis la hauteur de ligne, pas estimée.
- **La voix du segment 1 démentait son image** — elle disait encore « order
  table » et « two owners » après le passage à `products`. Ce sont les
  **sous-titres** qui l'ont attrapé, pas l'oreille : ils écrivent noir sur blanc
  ce que la voix a dit. Les générer avant de valider le montage, toujours.

Ce fichier dit **quoi filmer**. [`docs/narration.md`](narration.md) dit **quoi
dire**, mot à mot, en anglais. `scripts/demo.py` joue la séquence contre l'URL
déployée.

Brouillon à couper, pas un script à réciter. Les minutages sont des budgets :
s'ils sont dépassés, c'est la section qui maigrit, pas le débit.

**Règle qui tient tout : rien d'affirmé qui ne soit montré à l'écran.** C'est la
règle du README. Un jury qui a vu vingt démonstrations reconnaît la capture
d'écran d'une promesse.

**Personne à l'image.** Voix de synthèse (Liam), capture d'écran, rien d'autre.
Pas de logo, pas de titre animé, pas de présentation de soi : la première phrase
est le problème.

---

## Ce qui est déjà prêt

`scripts/demo.py` tourne contre `https://yvh3rv2qmp.eu-central-1.awsapprunner.com/mcp`
et sort exactement les chiffres de la narration. Vérifié le 6 août 2026 :

    97 pairs examined, 83 hold the same data
    18 groups of copies across platforms
    580 governance gaps on 48 datasets
    1 disagreement the agent refused to settle
    → dbt/customers, postgres/customers, s3/customers, snowflake/CUSTOMERS
    → 102 gaps on the customers copies alone
    → dry run: 102 values would be written, 0 written

Chaque ligne vient d'un appel MCP réel. Si le serveur répond autre chose, la
démonstration le montre — c'est voulu.

## La contrainte qui décide de l'ordre des prises

**La démonstration est destructrice.** Une fois `apply_governance` passé pour de
vrai, les cent deux écarts de `customers` n'existent plus, et la scène ne peut
plus être rejouée à l'identique.

Donc, dans cet ordre, sans exception :

1. **Répéter entièrement** avec `--repetition` : tout se joue, l'écriture réelle
   est sautée. Autant de fois qu'il faut.
2. **Tourner la prise réelle une seule fois**, sans `--repetition`.
3. S'il faut absolument refaire ce plan : `customers` est consommé, prendre un
   autre groupe de jumeaux — il en reste dix-sept, et quatre cent soixante-dix-huit
   écarts ailleurs.

Après la prise réelle, les chiffres du dépôt bougent : cinq cent quatre-vingts
écarts deviennent quatre cent soixante-dix-huit. **Relancer
`scripts/mesurer-jumeaux.py` et corriger le README** — il affirme que chacun de
ses chiffres est reproductible, et c'est vrai seulement si on le tient.

Bénéfice secondaire : les juges qui essaieront l'URL pendant la notation
trouveront un catalogue où il reste beaucoup à réparer. C'est ce qu'on veut.

## Vérifier les chiffres **sur la prise**, pas avant

La narration énonce des nombres, et le juge est un modèle : rien dans le
principe ne garantit qu'une analyse fraîche redonne ceux de la veille.

**Mesuré le 6 août 2026 : elle les redonne.** Deux analyses complètes et
indépendantes, la seconde relancée après expiration du cache et lue à deux
secondes d'âge, ont rendu exactement `97 / 83 / 18 / 580 / 48 / 1`. La
température zéro tient, sur cent invocations.

La précaution reste bonne marché : **enregistrer le segment 4 en dernier**, une
fois la capture faite, et lire les nombres réellement à l'écran. Les six
segments sont séparés exactement pour que ça coûte vingt secondes au lieu de
trois minutes.

Une voix qui dit un nombre que l'image dément est le seul défaut qu'un jury
remarque à coup sûr.

## Le piège vécu au tournage de Naaba

Une légende écrite d'avance — « merged, not added » — s'affichait quel que soit
le résultat du serveur. Filmée, elle démentait la ligne juste au-dessus, et il a
fallu refaire la prise.

`demo.py` conditionne déjà sa légende au résultat réel (`if reste["total"] <
ecarts["total"]`). **Ne pas la décâbler pour « faire plus propre » au montage.**

## Le plan, section par section

### 0:00 – 0:20 — le problème, en une image

**À l'écran** : les quatre `customers` côte à côte — `dbt`, `postgres`, `s3`,
`snowflake` — et sous chacune, ce qu'elle porte. Trois owners, un domaine, une
description d'un côté. Rien, rien, rien des trois autres.

C'est l'image la plus forte du projet. Elle doit tenir vingt secondes sans
commentaire supplémentaire.

### 0:20 – 0:45 — pourquoi le lignage ne répond pas

**À l'écran** : la sortie de `mesurer-jumeaux.py` sur le graphe — une composante,
cent trois nœuds, cent soixante et une arêtes ; les distances des couples
homonymes ; et la distance médiane entre deux jeux tirés au hasard.

Les deux nombres doivent être visibles **en même temps**, gros. Tout le segment
repose sur le fait qu'ils sont égaux.

C'est la mesure que personne d'autre n'aura faite. Elle vaut qu'on lui donne
vingt-cinq secondes.

### 0:45 – 1:15 — les noms mentent aussi, donc un modèle tranche

**À l'écran** : les quatre `Custom SQL Query` de Tableau et leur zéro pour cent
de colonnes communes. Puis le tableau des couches du README —
`catalogue → candidats → juge → ecart` — avec « 2 211 → 97 » lisible.

Finir sur le seize sur seize de `mesurer-le-juge.py`.

### 1:15 – 1:55 — l'agent déployé, en direct

**À l'écran** : `scripts/demo.py`, sections 1 à 3. Terminal plein cadre.

Laisser respirer sur la raison du juge — c'est une phrase en anglais lisible,
elle prouve à elle seule qu'un modèle a tranché et pas une règle.

Puis les cinq écarts, avec leur `copied from` : c'est là que se voit la deuxième
règle sans qu'on ait besoin de la dire.

### 1:55 – 2:30 — les deux règles

**À l'écran** : la scène « Fixing it » de `demo.py` — le `dry run` d'abord, puis
l'écriture réelle et son décompte.

Le passage de cent deux à zéro doit être **vu**, pas raconté.

### 2:30 – 2:55 — ce qu'il refuse de faire

**À l'écran** : la scène « What it will not do » — le désaccord sur
`order_details`, les quatre valeurs affichées côte à côte.

Dernière image : le message d'erreur du juge quand il ne peut pas invoquer le
modèle. Pas de plan de fin, pas de logo, pas d'appel à l'action.

## Capture

- **1080p**, terminal plein cadre, police assez grosse pour être lisible sur un
  téléphone — c'est comme ça qu'un juge regarde en réalité.
- Fond sombre, la palette de `demo.py` est faite pour ça (rouge sur les écarts,
  jaune sur les genres manquants, vert sur ce qui a été écrit).
- `--vite` **seulement** pour les répétitions. La prise réelle garde les pauses :
  elles sont calibrées pour qu'on ait le temps de lire.
- Les silences pendant que le serveur travaille ne sont pas des trous. C'est là
  qu'on regarde au lieu d'écouter. Ne pas les couper au montage.

## Sous-titres

En anglais, comme la narration. Générés depuis `narration.md`, pas depuis la
transcription automatique : le texte est déjà écrit, autant qu'il soit exact.
