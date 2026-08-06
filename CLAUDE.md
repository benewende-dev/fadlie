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

> **Deux corrections du 6 août 2026, sur la même question.** Une première
> version affirmait « 24 jeux n'ont aucun lignage » : mesure lancée pendant que
> l'index se remplissait. Une seconde affirmait « 58 couples sur 88 n'ont aucun
> chemin » : le parcours ne gardait que les arêtes entre *jeux de données*, or
> `postgres/customers` n'a qu'un voisin et c'est un **traitement**,
> `export_table_customers_to_s3`, qui mène droit à `s3/customers`. Les deux
> chiffres étaient plausibles et faux, dans deux directions opposées.
> **La vérité est l'inverse : tout est relié.** Ce qui suit est re-mesuré, index
> stabilisé, traitements compris.

- **Le lignage ne dit rien sur « est-ce la même donnée ».** Le graphe est d'un
  seul tenant : 103 sommets, 161 arêtes, **0 jeu isolé**, et les **88 couples
  d'homonymes sont tous reliés** — à distance 2 ou 4. Or la distance médiane
  entre deux jeux **pris au hasard** est de 4. Les jumeaux sont donc à la même
  distance que n'importe quel couple : la connexité ne porte aucune information.
  C'est ce qui rend un juge nécessaire, et c'est mesuré, pas supposé.
- **Et pourtant rien ne propage.** `snowflake/CUSTOMERS` est joignable depuis
  `dbt/customers` en deux sauts et n'a ni propriétaire, ni domaine, ni
  description. Le catalogue *contient* le chemin ; personne ne le parcourt.
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

- **`datahub docker quickstart` livre GMS sans authentification.**
  `METADATA_SERVICE_AUTH_ENABLED=false` : mesuré le 6 août 2026, une requête
  GraphQL *sans en-tête* rendait 200, et une mutation `createTag` **sans aucune
  identité** a créé l'étiquette. Le jeton d'accès personnel était décoratif. Le
  réglage est maintenant à `true` ; vérifié : 401 sans jeton, 401 avec un jeton
  inventé, 401 avec un jeton émis avant le changement de clé. Ne jamais exposer
  8080 ni 9002 sur un quickstart qu'on n'a pas d'abord vérifié.
- **Redémarrer un service de la composition sans son `.env` casse tout en
  silence.** La composition attend `DATAHUB_VERSION`,
  `UI_INGESTION_DEFAULT_CLI_VERSION`, `DATAHUB_TOKEN_SERVICE_SALT` et
  `DATAHUB_TOKEN_SERVICE_SIGNING_KEY`. Absentes, docker compose les remplace par
  la chaîne vide : étiquette d'image vide, **clé de signature vide** — tous les
  jetons deviennent invalides sans un mot d'erreur. Un `.env` complet est
  maintenant écrit dans `~/.datahub/quickstart/` sur l'instance.
- Le service s'appelle **`datahub-gms-quickstart`**, pas `datahub-gms`, et le
  frontal **`frontend-quickstart`**. Les deux lisent la clé de signature.
- **Toutes les écritures dont l'agent a besoin fonctionnent** (vérifiées puis
  défaites, sur `postgres/countries` remise à son état d'origine) : `addTags`,
  `addOwners`, `updateDescription`, et surtout `addTags` / `addTerms` **au
  niveau colonne** via `subResource` + `subResourceType: DATASET_FIELD`. Les
  variantes `batchAddTags`, `batchAddTerms`, `batchAddOwners`, `batchSetDomain`
  existent — les préférer.
  Piège de nommage : `removeTerm` prend un **`TermAssociationInput`**, pas un
  `RemoveTermInput` comme la symétrie le laisse croire.
- **Bedrock : `eu.amazon.nova-micro-v1:0` s'invoque à Francfort, l'identifiant
  nu échoue** (`ValidationException`, « on-demand… »). Exactement comme pour
  Naaba : le préfixe régional du profil d'inférence est obligatoire.
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
- **L'index est alimenté en différé, et le graphe de lignage bien plus lentement
  que la recherche.** Juste après le chargement, `search` rend 3 jeux ; 67 après
  deux minutes. Mais le **lignage** n'était toujours pas matérialisé une demi-
  heure plus tard : 24 jeux paraissaient n'avoir aucune arête, ils en ont tous.
  Ce piège a produit une conclusion fausse, écrite et committée. Il ne lève rien,
  ne prévient de rien, et rend un chiffre parfaitement plausible. **Mesurer le
  lignage seulement après avoir vérifié qu'il est stable — deux mesures
  identiques à dix minutes d'écart.**
- **Un traitement relie deux jeux sans être un jeu.** Ne garder que les arêtes
  de type `DATASET` coupe le chemin exactement là où il passe :
  `postgres/customers` n'a qu'un seul voisin dans tout le graphe, le DataJob
  `export_table_customers_to_s3`, qui mène à `s3/customers`. Un parcours qui
  filtre les traitements fabrique des îlots qui n'existent pas — et le résultat
  ressemble à une découverte. Suivre `DATASET` **et** `DATA_JOB`, et interroger
  le lignage par `entity(urn:)`, pas par `dataset(urn:)`.
- **Se méfier d'un résultat qui arrange.** Les deux erreurs ci-dessus allaient
  toutes les deux dans le sens de la thèse du moment. C'est le signe qu'il faut
  re-mesurer autrement, pas écrire plus vite.
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

## Le juge (`mesurer-le-juge.py`)

`eu.amazon.nova-micro-v1:0`, température 0. **10 couples sur 10 correctement
tranchés**, tous tirés du vrai catalogue et choisis pour être difficiles :
quatre copies que la structure ne suffit pas à reconnaître (casse différente,
deux colonnes de plus), six ressemblances trompeuses (tables de référence de
même forme, homonymes à 9 % de recouvrement, mesures calculées en aval,
`orders` contre `order_items`).

- **Une panne du juge ne doit jamais ressembler à un verdict.** Ici, un juge muet
  rendrait « aucune copie trouvée » — un catalogue en règle. La panne se
  déguiserait en bonne nouvelle, et personne ne va vérifier une bonne nouvelle.
  D'où `JugeError` systématique, et une sonde qui invoque vraiment le modèle
  avant le premier verdict. Vérifié dans les deux modes de panne réels :
  identifiant nu (`ValidationException`) et identifiants sans droit Bedrock
  (`UnrecognizedClientException`). C'est le piège 8 de Naaba, corrigé à la
  source plutôt que rattrapé.
- **Le juge ne voit ni le recouvrement calculé ni la distance de lignage.** Un
  nombre l'ancrerait, et la distance est mesurée sans valeur pour cette question.
  Un test l'impose.
- **Les raisons rendues sont parfois factuellement fausses même quand le verdict
  est juste** : pour `dbt/customers` ≟ `postgres/customers` il écrit « same
  platform », ce qui est faux. Le verdict tient, la justification est un
  commentaire — ne jamais la présenter comme un fait vérifié, et ne jamais
  l'écrire telle quelle dans le catalogue.

## Ce que l'agent trouve, bout en bout

Sur le vrai catalogue, un passage complet : **97 couples présélectionnés sur
2 211, 84 confirmés, 18 groupes de jumeaux, 580 écarts de gouvernance sur 48
jeux, 1 désaccord.** Répartition : 291 descriptions de colonne, 127
propriétaires, 55 étiquettes de colonne, 39 descriptions, 34 domaines, 34 termes.

Le seul désaccord est instructif : `snowflake/ORDER_DETAILS` est dans
« Ecommerce Operations » quand ses quatre jumeaux sont dans « Data Platform
Team ». Fadlie **ne tranche pas** — quelqu'un a décidé, ou quelqu'un s'est
trompé, et ce n'est pas à un agent de choisir.

Deux corrections nées de ce passage :

- **Un espace vaut un tiret bas.** `tableau/Top Product Category` porte
  `Category Name` là où la requête qui l'alimente porte `CATEGORY_NAME` : le
  recouvrement tombait de 80 % à 50 %, sous le seuil, et le couple disparaissait
  sans un mot. `cle_colonne` normalise casse *et* séparateurs — et pas plus
  loin : rapprocher `cust_email` de `email` serait deviner, et deviner est le
  travail du juge.
- **Un groupe qui porte deux noms porte deux noms.** L'étiquette affichait
  `jeux[0].nom`, donc le premier par urn : le groupe
  « Promotions ≟ Custom SQL Query » s'affichait « Custom SQL Query » et donnait
  l'impression d'une confusion. Le résultat était juste, l'étiquette mentait. Une
  deuxième version départageait par une règle qui nommait « Custom SQL Query »
  dans le code — une donnée de ce catalogue-ci glissée dans la bibliothèque. Il
  n'y a pas de bon départage : on montre tous les noms.

## Infrastructure

- DataHub Core v1.7.0, instance EC2 `i-0fb64e9417800d75f` (`t3.large`,
  eu-central-1, 40 Go). Quatorze conteneurs.
- **Adresse fixe : `63.186.160.88`** (Elastic IP `fadlie-datahub`). Sans elle,
  éteindre l'instance pour économiser change l'adresse — et l'URL déposée sur
  Devpost casserait pendant la notation, du 17 au 31 août. Ne pas la libérer.
- **Ouvert, mais gardé.** Décision du 6 août : GMS (`8080`) et l'interface
  (`9002`) sont joignables depuis l'internet, parce que les juges doivent
  pouvoir essayer Fadlie *et* vérifier de leurs yeux ce qu'il a écrit. C'est
  tenable seulement grâce à trois choses vérifiées avant l'ouverture :
  1. GMS exige un jeton (401 sans, 401 avec un faux) ;
  2. le compte `datahub/datahub` est mort ; l'administrateur a un mot de passe
     fort, et un compte `judge` en rôle **Reader** lit sans pouvoir écrire
     (403 sur `createTag`, vérifié) ;
  3. **l'instance ne porte aucun identifiant AWS** — pas de rôle, rien dans
     `~/.aws`. L'entamer ne donne accès à rien d'autre. Et elle ne contient que
     le jeu de démonstration public du concours.
  Le SSH, lui, reste réservé aux deux adresses du poste de travail.
- Les comptes sont dans `~/.datahub/plugins/frontend/auth/user.props` sur
  l'instance, **monté par-dessus** `/datahub-frontend/conf/user.props`. Piège :
  `jaas.conf` déclare les deux fichiers `sufficient`, donc *ajouter* des comptes
  ne retire pas celui par défaut — il faut recouvrir le fichier de l'image.
  Autre piège : le conteneur tourne sous un autre utilisateur, un `chmod 600`
  rend le fichier illisible et l'authentification retombe silencieusement sur le
  défaut. 644, et 755 sur les dossiers.
- Un utilisateur créé dans `user.props` ne peut pas se connecter tant que son
  entité n'existe pas dans GMS : le frontal rend **500**, « Session token denied
  by Metadata Service ». Émettre un `CorpUserInfo` d'abord, puis
  `batchAssignRole`.
- `scripts/tunnel.sh` reste utile pour le travail local, mais n'est plus
  nécessaire : `DATAHUB_GMS_URL` pointe sur l'adresse publique.
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
