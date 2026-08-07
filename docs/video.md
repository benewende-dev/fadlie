# La vidéo — moins de trois minutes

**Faite et publiée le 6 août 2026 : 2 min 40, 1080p, voix Liam, sous-titres
anglais.** <https://youtu.be/YXff0HNRAwU>

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

**Règle qui tient tout : rien d'affirmé qui ne soit montré à l'écran.** C'est la
règle du README. Un jury qui a vu vingt démonstrations reconnaît la capture
d'écran d'une promesse.

**Personne à l'image.** Voix de synthèse (Liam), capture d'écran, rien d'autre.
Pas de logo, pas de titre animé, pas de présentation de soi : la première phrase
est le problème.

---

## La contrainte qui a décidé de l'ordre des prises

**La démonstration est destructrice.** Une fois `apply_governance` passé pour de
vrai, les écarts du groupe visé n'existent plus, et la scène ne peut plus être
rejouée à l'identique. C'est arrivé deux fois : `customers` d'abord, consommé par
les essais ; `orders` ensuite, consommé par une prise que le décalage d'une ligne
d'affichage a rendue inutilisable.

Donc, dans cet ordre, sans exception :

1. **Répéter entièrement** avec `--repetition` : tout se joue, l'écriture réelle
   est sautée. Autant de fois qu'il faut, et c'est là qu'on regarde le cadrage.
2. **Tourner la prise réelle une seule fois**, sans `--repetition`.
3. S'il faut refaire ce plan : le groupe est consommé, en viser un autre avec
   `--jeu`. Il en reste quinze.

Après chaque prise réelle, les comptes du catalogue changent. **Ils se relisent
sur la prise, jamais depuis la veille** — voir la note sur la variabilité du juge
dans `CLAUDE.md`.

Bénéfice secondaire : les juges qui essaieront l'URL pendant la notation
trouveront un catalogue où il reste largement de quoi faire.

## Le piège vécu au tournage de Naaba

Une légende écrite d'avance — « merged, not added » — s'affichait quel que soit
le résultat du serveur. Filmée, elle démentait la ligne juste au-dessus, et il a
fallu refaire la prise.

`demo.py` conditionne déjà sa légende au résultat réel (`if reste["total"] <
ecarts["total"]`). **Ne pas la décâbler pour « faire plus propre » au montage.**

## Le montage, tel qu'il est

Six segments, chacun de la durée exacte de son audio. Le texte mot à mot et les
durées mesurées sont dans [`docs/narration.md`](narration.md).

| | plan | à l'écran |
|---|---|---|
| s1 | 0:00 – 0:22 | les quatre tables `products`, et ce que chacune porte |
| s2 | 0:22 – 0:47 | une composante, 103 nœuds, et les deux distances égales |
| s3 | 0:47 – 1:14 | les quatre `Custom SQL Query`, les couches, le 16/16 |
| s4 | 1:14 – 1:50 | le terminal, révélé section par section |
| s5 | 1:50 – 2:18 | un écart avec sa source ; à blanc puis pour de vrai |
| s6 | 2:18 – 2:40 | le désaccord sur `order_details`, puis le juge qui lève |

Seul le segment 4 est animé : le terminal se dévoile par sections, calées sur les
phrases de la narration. Le reste est fixe — ce qui est à l'écran doit avoir le
temps d'être lu, pas d'être balayé.

Le plan qui porte tout est le dernier du segment 4 : `53 values written to
DataHub (11s)` en vert, puis `gaps on products now: 0 (was 53)`. Le passage à
zéro est **vu**, pas raconté.

## Capture

- **1080p**, terminal plein cadre, police assez grosse pour être lisible sur un
  téléphone — c'est comme ça qu'un juge regarde en réalité.
- Fond sombre, la palette de `demo.py` est faite pour ça (rouge sur les écarts,
  jaune sur les genres manquants, vert sur ce qui a été écrit).
- `--vite` **seulement** pour les répétitions. La prise réelle garde les pauses :
  elles sont calibrées pour qu'on ait le temps de lire.
- Les silences pendant que le serveur travaille ne sont pas des trous. C'est là
  qu'on regarde au lieu d'écouter. Ne pas les couper au montage.

## Le GIF du README

`docs/images/demo.gif` — 900 × 506, 144 images, 173 Ko. Il n'est pas rejoué : il
est **découpé dans la vidéo publiée**, de 1:32,5 à 1:48,5, c'est-à-dire du
`catalog_summary()` jusqu'à `gaps on products now: 0`. Tout l'arc en seize
secondes, sans une image reconstituée.

```bash
ffmpeg -ss 92.5 -t 16 -i fadlie.mp4 \
    -vf "fps=9,scale=900:-1:flags=lanczos,palettegen=max_colors=64:stats_mode=diff" \
    palette.png
ffmpeg -ss 92.5 -t 16 -i fadlie.mp4 -i palette.png \
    -lavfi "fps=9,scale=900:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" \
    docs/images/demo.gif
```

**Neuf images par seconde suffisent** : le plan ne bouge que par sauts, section
par section. À trente, le fichier est vingt fois plus lourd pour exactement la
même chose à l'œil. La palette de soixante-quatre couleurs tient parce que le
terminal n'en emploie que cinq.

## Sous-titres

En anglais, comme la narration, et **générés depuis le texte prononcé**, pas
depuis une transcription automatique : le texte est déjà écrit, autant qu'il soit
exact. Le minutage vient de la durée réelle de chaque piste, réparti au prorata
du texte de chaque réplique.

Ils font le chemin inverse de la voix : la narration écrit *four hundred and
twenty* pour que le moteur le prononce bien, le sous-titre affiche `420` pour que
l'œil le retrouve à l'écran.

**Les générer avant de valider le montage.** Ce sont eux qui ont attrapé la seule
erreur de fond du tournage — un segment dont la voix nommait encore l'ancien
groupe. À l'oreille, ça passait.
