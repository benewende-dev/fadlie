# Fadlie — notes de travail

Un agent qui trouve **la même donnée vivant dans plusieurs systèmes que le
graphe ne relie pas** — et la gouvernance qui s'arrête à cette frontière
invisible. Écrit pour le hackathon
**Build with DataHub — The Agent Hackathon**, échéance **10 août 2026, 17 h 00
EDT**. Notation du **17 au 31 août** : la démonstration doit vivre jusque-là,
pas jusqu'à la remise.

## Le problème, mesuré sur le vrai graphe

Jeu `showcase-ecommerce` (le jeu de démonstration fourni par le concours),
chargé sur notre propre instance DataHub Core v1.7.0. Mesures du 6 août 2026 —
**`scripts/mesurer-catalogue.py` les refait toutes**. Un chiffre qu'on ne peut
pas refaire tourner est une opinion.

- **67 jeux de données, 7 plateformes** : snowflake (14), dbt (13), postgres
  (12), s3 (12), tableau (8), powerbi (6), looker (2).
- **Le lignage est dense** : 40 jeux sondés, 40 reliés. `order_details` a 24
  ascendants et 17 descendants.
- **Le sens manque** : 80 % des jeux sans description, 70 % sans propriétaire,
  76 % sans domaine, 21 % des colonnes décrites (175 / 816).
- **Deux jeux sur 67 portent l'étiquette `PII_Data`. Trois marquages en tout.**
  Or **20 jeux sur 67** contiennent des colonnes qui en ont l'air — un écart de
  18. `order_details` à lui seul porte 17 colonnes de noms, e-mails, téléphones
  et adresses, présentes sur quatre plateformes à la fois.
- Le cas qui résume tout : `ORDER_DETAILS_REPLICA` (snowflake), descendant
  direct, 55 colonnes dont 17 sensibles, **aucune déclaration**. Une copie
  littérale de la donnée personnelle, invisible à qui interroge le catalogue.

Conséquence nommable : on ne peut pas honorer une demande d'effacement sur une
donnée qu'on ignore être personnelle. Et le catalogue ne dit pas « je ne sais
pas » — il répond « deux jeux », avec l'assurance de celui qui a cherché.

## Où est vraiment le trou (`mesurer-jumeaux.py`)

Une première hypothèse a été **écartée par la mesure** : « le nom de colonne ne
survit pas au lignage, il faut un modèle pour apparier ». Faux. Là où le lignage
relie et où le schéma est recopié, l'égalité de noms suffit — 18 colonnes
marquées sur 18 retrouvées dans `ORDER_DETAILS_REPLICA` et `looker/order_details`,
et 18 sur 18 à la casse près dans `powerbi/ORDER_DETAILS`. Ne pas rebâtir ce
problème : il n'existe pas.

Le trou est ailleurs, et il est plus grave.

- **24 jeux sur 67 n'ont aucun lignage** — les 12 tables postgres et les 12
  tables s3, dans aucun sens. Aucune propagation ne les atteindra jamais.
- **11 tables existent à l'identique sur quatre plateformes** : dbt, snowflake,
  postgres, s3, recouvrement de colonnes **100 %**. `customers` : 22 colonnes
  des deux côtés, au nom près. Rien dans le graphe ne dit que c'est la même
  donnée.
- **La gouvernance s'arrête à dbt.** 11 groupes sur 12 sont gouvernés
  inégalement : `dbt/customers` a 3 propriétaires, un domaine et une
  description ; ses trois jumeaux ont **zéro, aucun, aucune**.
- **12 colonnes identiques sont marquées d'un côté et nues de l'autre.**
  `customers.zipcode`, `customers.town_city`, `addresses.zipcode` : annotées
  chez dbt, rien chez snowflake ni postgres. `customers.customer_id` ne porte
  `PII_Data` **que** sur postgres.
- Et le nom seul ne peut pas trancher : **3 groupes homonymes sur 15 ne sont pas
  la même chose** — `custom_sql_query` (4 jeux tableau, recouvrement 0 %),
  `order_details` (0 %), `promotions` (9 %). Le nom présélectionne ; il ne
  tranche pas. C'est exactement la place d'un juge, et elle est *gagnée* par la
  mesure, pas supposée.

## Ce qui est vérifié (ne pas re-supposer)

- **Il n'y a pas de lignage à la colonne dans ce graphe : 0 sur 67.** Mesuré via
  l'aspect `upstreamLineage` (OpenAPI v2) sur chaque jeu ; `fineGrainedLineages`
  est absent partout. Donc **aucune propagation mécanique n'est possible**. Le
  lignage présélectionne au niveau du jeu ; l'appariement des colonnes puis le
  verdict demandent autre chose. Ne pas écrire de code qui suppose du lignage
  fin.
- Le point d'entrée GraphQL qui marche est **`GMS:8080/api/graphql`**. Par le
  frontal (`9002/api/v2/graphql`) l'authentification par jeton porteur est
  refusée — 400. Ne pas y revenir.
- `datahub docker quickstart` **ne charge plus de données d'exemple** : le
  graphe sort vide (1 seule entité, l'utilisateur `datahub`). Le jeu du concours
  se charge par `datahub datapack load showcase-ecommerce`.
- **L'index de recherche est alimenté en différé.** Juste après le chargement,
  `search` rend 3 jeux ; il en rend 67 après deux minutes. Un contrôle écrit
  juste après une écriture mesure le vide et le prend pour un échec.
- `datahub datapack --help` **plante** (ressource `DATAPACK_AGENT_CONTEXT.md`
  absente du paquet). `datapack list` et `datapack load` fonctionnent. Défaut
  d'empaquetage du CLI, sans conséquence.
- **Le fournisseur d'accès fait sortir le SSH et le HTTPS par deux adresses
  différentes.** `checkip` rend celle du HTTPS. Un pare-feu verrouillé sur ce
  seul /32 a l'air juste et refuse la connexion, sans rien dire. Documenté dans
  `scripts/preparer-ec2.sh`, qui ouvre les deux.
- **Le tunnel SSH tombe en silence après quelques minutes d'inactivité.** Le
  symptôme est un `ConnectionResetError` au milieu d'une mesure, qui ressemble à
  une panne de DataHub. `scripts/tunnel.sh` pose `ServerAliveInterval` et se
  ré-ouvre tout seul ; l'appeler avant toute mesure.

## Infrastructure

- DataHub Core v1.7.0, instance EC2 `i-0fb64e9417800d75f` (`t3.large`,
  eu-central-1, 40 Go). Quatorze conteneurs.
- **Le port 9002 n'est pas exposé.** Accès par tunnel :
  `ssh -f -N -i ~/.ssh/fadlie-datahub.pem -L 9002:localhost:9002 -L 8080:localhost:8080 ubuntu@<ip>`
- Utilisateur AWS `fadlie`, distinct de celui de Naaba : deux projets déployés,
  deux jeux de clés. Une révocation d'un côté n'emporte pas l'autre.

## Conventions

Les mêmes que Naaba, et pour les mêmes raisons.

- **Fichiers publics en anglais** (README, LICENSE). **Docs de travail,
  docstrings et commentaires Python en français.**
- **Aucun chiffre non mesuré n'entre dans le README.**
- **Ne jamais nommer un produit concurrent.**
- **Les secrets ne transitent jamais par la conversation.**
- **Un pas à la fois** : mesuré, écrit, committé, relu, puis le suivant.
- Machine à 8 Go : jamais Docker et autre chose en même temps. C'est pour ça que
  DataHub tourne sur EC2 et pas ici.

## Où en est le projet

Fait : instance debout, jeu du concours chargé, graphe mesuré, problème établi
sur des chiffres.

À faire : la mesure fondatrice (l'appariement par nom de colonne suffit-il ?),
puis l'agent, le serveur MCP, le déploiement, la vidéo, le dépôt.
