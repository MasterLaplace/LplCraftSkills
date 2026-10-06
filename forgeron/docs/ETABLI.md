# `forgeron etabli` : poser la config déclarée d'un dépôt et d'un projet

Le verbe applique la première couche de `tenir-la-forge` (section 2) : la config déclarée dans un
fichier, appliquée par un outil qui montre son plan avant d'écrire. Il couvre les étiquettes, les
réglages du dépôt, sa sécurité et ses règles de branche, et pour un projet GitHub ses réglages, ses
champs, ses vues et ses liens vers les dépôts.

```bash
cd forgeron
python3 -m forgeron etabli --file ~/.forgeron/etabli.json                 # le plan, rien n'est écrit
python3 -m forgeron etabli --file ~/.forgeron/etabli.json --repo OWNER/NAME --only labels
python3 -m forgeron etabli --file ~/.forgeron/etabli.json --project "OWNER/TITLE"   # un projet seul
python3 -m forgeron etabli --file ~/.forgeron/etabli.json --write         # applique, puis relit
python3 -m forgeron --json etabli --file ~/.forgeron/etabli.json          # la sortie machine
```

Les options et les codes de sortie sont dans `python3 -m forgeron etabli --help`, et nulle part
ailleurs.

## Ce qu'il fait

```mermaid
flowchart LR
  F["declared file"] --> P["plan<br/><i>pure, no I/O</i>"]
  O["observe the repository<br/><i>gh api</i>"] --> P
  P -->|"without --write"| S["print the plan"]
  P -->|"--write"| A["apply each change"]
  A --> O2["observe again"] --> P2["plan again"] --> S2["print what is left"]
```

- **le plan est une fonction pure** de la config et de l'état observé (`etabli.plan`), comme
  `states.decide` pour la boucle : chaque cas bizarre devient une donnée de test ;
- **sans `--write`, les lectures sont réelles et aucune écriture n'a lieu.** Le code de sortie dit s'il
  reste quelque chose à appliquer ;
- **avec `--write`, le verbe relit le dépôt après avoir écrit, et replanifie.** Un second plan qui
  propose encore quelque chose veut dire que l'outil et la forge ne sont pas d'accord sur l'état : le
  verbe le montre et sort en erreur, au lieu d'annoncer un succès sur la foi de ses propres écritures.

## Le fichier

Le format est celui de [`../etabli.example.json`](../etabli.example.json), qu'un test charge à chaque
passage de la suite : un exemple qui ne se charge plus casse la suite.

- `defaults` s'applique à chaque dépôt ; une entrée de `repos` y **ajoute** ses étiquettes, ses
  renommages, ses réglages et sa sécurité, et **remplace** la liste des rulesets si elle en déclare
  une ;
- `required_checks` ajoute la règle des checks requis à chaque ruleset de branche du dépôt : les
  noms de checks changent d'un dépôt à l'autre, pas la règle. Un nom seul accepte le check de
  n'importe quelle source ; `{"context", "integration_id"}` l'épingle à une application. Sans ruleset
  de branche, ou avec un ruleset qui déclare déjà ses checks, le fichier est refusé ;
- `renames` migre un vocabulaire sans perdre les items qui portent l'ancienne étiquette ;
- `unlisted_labels` vaut `report` (par défaut : les étiquettes non déclarées sont listées) ou
  `delete-unused` (celles qu'aucune issue ni PR ne porte sont supprimées, les autres jamais). Les
  discussions portent aussi des étiquettes, et l'API ne les compte pas : sur un dépôt où elles sont
  actives, rien n'est supprimé. Une étiquette nommée dans un fichier (un formulaire d'issue,
  `dependabot.yml`, un workflow) n'est pas comptée non plus : lire ces fichiers avant de choisir
  `delete-unused` ;
- `only` restreint un dépôt à certains domaines. C'est le cas d'un dépôt qui garde son propre
  vocabulaire d'étiquettes et reçoit seulement les réglages, la sécurité et les règles.

Le fichier est refusé en entier, avec le chemin exact de ce qui ne va pas, pour une clé inconnue, une
valeur du mauvais type, une couleur mal formée, une étiquette sans description, un renommage vers une
étiquette non déclarée, deux noms qui ne diffèrent que par la casse, un ruleset sans `bypass_actors` ou
sans les paramètres que la forge exige, ou une paire de messages de fusion invalide. Rien n'est à
moitié appliqué.

**Les messages de fusion vont par paire.** `merge_commit_title` et `merge_commit_message` se déclarent
ensemble, et la forge n'accepte que certaines combinaisons, listées dans le message d'erreur ; même
chose pour les deux clés du squash. Les réglages d'un dépôt partent en une seule écriture, pour que la
forge voie la paire entière.

## Les projets

Un projet couvre plusieurs dépôts, donc il a sa propre section, `projects`, à côté de `repos`. Sa clé
est `OWNER/TITLE` : le titre est ce qui identifie le projet, puisque son numéro n'existe qu'une fois
créé.

- `readme` est le chemin d'un fichier Markdown, relatif au fichier de config : le mode d'emploi du
  projet se relit dans une PR, comme le reste. Le chemin ne sort pas du dossier de la config, puisque
  son contenu est publié sur le projet ;
- `repositories` liste les dépôts où le projet apparaît, dans l'onglet Projects. La forge n'y accepte
  que les dépôts du même propriétaire que le projet, donc le fichier refuse les autres ;
- `fields` déclare les champs, de type `single_select`, `date`, `number` ou `text`. Les champs intégrés
  (Title, Assignees, Labels, Repository…) existent sur tout projet et ne se déclarent pas, sauf
  `Status`, dont on déclare les options ;
- `views` déclare les vues, avec leur `layout` (`table`, `board` ou `roadmap`). Le filtre, les champs
  visibles, le tri, le regroupement et les colonnes d'un board ne sont tenus que s'ils sont déclarés :
  ce que la déclaration ne dit pas reste tel que l'interface l'a réglé. Les champs visibles se
  comparent comme un ensemble, parce que l'API les rend dans l'ordre du projet et non dans celui de la
  vue ;
- `workflows` dit, pour chaque workflow nommé, s'il doit être actif ou éteint. L'API sait les lire,
  pas les écrire : un écart bloque, et le message donne l'adresse où le corriger. Un workflow jamais
  configuré compte comme éteint.

| Élément | Absent | Différent | Non déclaré |
|---|---|---|---|
| le projet | créé, puis rempli dans le même passage ; sans `--write`, le plan montre aussi ce qui suivra la création | visibilité, description, README mis à jour | |
| un lien | posé | | listé, jamais retiré |
| un champ | créé | options mises à jour, avec leurs identifiants, donc les items gardent leur valeur | listé, jamais supprimé |
| une vue | créée | filtre, disposition et champs visibles mis à jour sur place ; tri et regroupement en la recréant puis en supprimant l'ancienne, puisqu'elle ne contient aucune donnée | listée |
| un workflow | bloqué | bloqué | ignoré |

**Recréer une vue a un prix.** La nouvelle vue reprend ce que la déclaration ne dit pas et que l'API
sait poser (champs visibles, tri, regroupement, colonnes), mais elle perd ce que l'API ne porte pas :
les dates d'une feuille de route, les sommes, la découpe. Elle change aussi de numéro, donc d'adresse.
Elle est créée avant que l'ancienne soit supprimée : si la création échoue, l'ancienne reste.

Un projet se retrouve par son titre : deux projets du même propriétaire avec le même titre sont
refusés, plutôt que d'en choisir un. Une sélection (`--repo`, `--project`, `--only`) qui ne laisse rien
à vérifier est une erreur d'usage, pas un succès.

## Les choix de l'exemple

- **fusion en squash seulement**, titre et message pris de la PR (`PR_TITLE`, `PR_BODY`) : avec des
  PR petites, une intention chacune, personne ne relit l'historique interne d'une branche après la
  fusion, et les tours de revue d'un bot y ajoutent du bruit (`tracer-le-travail`, section 9). Le
  titre de la PR devient donc le commit sur la branche principale, et il suit les commits
  conventionnels ;
- **un contournement admin qui ne passe que par une PR** (`bypass_mode: pull_request`), et des commits
  signés : le mainteneur ouvre une PR comme tout le monde, et un bot qui parle avec son jeton n'hérite
  d'aucun push direct. Ajouter un contournement à un ruleset qui existe est un affaiblissement, que le
  verbe refuse ; on le pose donc une fois à la main, et le fichier le déclare ensuite ;
- **les étiquettes du pilote s'appellent `forgeron` et `forgeron:hold`** : une étiquette nomme
  l'outil du projet, pas le modèle qui tourne derrière.

## Ce qu'il refuse, et pourquoi

| Refus | Pourquoi |
|---|---|
| un dépôt que le fichier ne déclare pas | le jeton atteint tous tes dépôts ; la liste de ceux qu'on règle est une décision, pas une conséquence du jeton |
| supprimer une étiquette encore portée | supprimer l'efface de toutes les issues ; on renomme, ou on la reporte à la main |
| renommer vers une étiquette qui existe déjà | deux étiquettes à fusionner, c'est des items à reporter : l'outil le dit, il ne choisit pas |
| retirer une protection de sécurité | désactiver la protection au push ou les alertes se fait à la main, avec sa raison écrite (`garder-les-frontieres`) |
| supprimer un ruleset non déclaré | il est listé, jamais supprimé |
| lire un état de sécurité illisible comme « inactif » | un état qu'on ne lit pas ne prouve rien : le point est bloqué, pas corrigé |
| affaiblir un ruleset | baisser son application, lui retirer une règle, lui ajouter un contournement : même raison que pour la sécurité |
| perdre un paramètre que seule la forge porte | une mise à jour remplace le ruleset en entier : le plan nomme le paramètre, qu'il faut déclarer pour le garder ou retirer à la main |
| toucher un dépôt archivé | il est en lecture seule : tout est sauté, et la sortie dit que rien n'a été vérifié |
| supprimer un champ de projet non déclaré | un champ supprimé emporte la valeur qu'il portait sur chaque item |
| retirer une option qu'un item peut porter | l'option disparaît de chaque item qui la porte ; sur un projet sans item, archivés compris, rien n'est perdu et le retrait passe |
| changer le type d'un champ | la forge ne le permet qu'en le recréant, donc en perdant ses valeurs |
| régler un workflow de projet | l'API ne sait que le lire ; un écart est bloqué, avec l'adresse de la page où le régler |
| lier un projet au dépôt d'un autre propriétaire | la forge ne liste un projet que chez son propriétaire |

Les rulesets hérités d'une organisation ne sont ni lus ni modifiés : ils appartiennent à qui les a
posés.

## Les droits, et la trace

Le verbe passe par `gh`, donc par ta session : aucun jeton dans la config, rien à fuiter. Il lit
`permissions` sur le dépôt avant de planifier :

- sans droit d'écriture, les étiquettes sont sautées ;
- sans le rôle admin, les réglages, la sécurité et les rulesets sont sautés, et le plan le dit.

C'est le cas d'un dépôt dont on n'est que collaborateur : ses étiquettes se posent, le reste revient
à son propriétaire.

Chaque écriture, réussie, refusée ou restée sans réponse, laisse une ligne `etabli_applied` ou
`etabli_failed` dans le journal de forgeron (`journal.jsonl` sous son `home`), avec l'avant et l'après.
Pour un ruleset, l'avant est le ruleset entier tel que la forge l'a rendu, donc de quoi le reposer. C'est la réponse à « qui a changé ce réglage, et
quand » que la forge ne donne qu'à moitié.

## Ce qu'il ne fait pas, délibérément

- **les workflows et les graphiques d'un projet.** Ils n'ont pas d'API d'écriture : on les règle une
  fois dans l'interface, et le fichier déclare l'état attendu des workflows pour qu'un écart se voie ;
- **les items d'un projet et ses points d'étape** : c'est le travail, pas la config. Que forgeron
  les tienne au fil de son travail est prévu, pas encore fait ;
- **les fichiers du dépôt** (`CODEOWNERS`, gabarits, `SECURITY.md`) : ce sont des fichiers, ils passent
  par une PR relue comme le code, pas par l'API des réglages ;
- **reporter les items d'une étiquette sur une autre**, créer ou supprimer un dépôt.

## Les alternatives écartées

| Alternative | Pourquoi pas ici |
|---|---|
| l'application *Settings* (`.github/settings.yml`) | une application tierce avec les droits admin sur chaque dépôt, et un push de `settings.yml` sur la branche principale agit en admin ; elle ne couvre pas le board |
| le fournisseur Terraform `integrations/github` | aucune ressource Projects v2, et un fichier d'état à garder quelque part |
| `gh label clone` | copie les étiquettes d'un dépôt, sans renommer, sans dire ce qui diverge, et sans le reste |
| une Action avec un jeton classique | le jeton qui ouvre tous les dépôts, rangé en secret dans chacun (`tenir-la-forge`, section 7) |

## Les faits mesurés

Lus le 2026-09-30 sur six dépôts réels (cinq pour ce qui demande d'être admin), en lecture seule, avec la session `gh` d'un compte personnel
(portées `repo`, `read:org`, `gist`, `admin:public_key`, `read:packages`) :

- les nombres d'items par étiquette viennent d'une seule requête GraphQL paginée
  (`labels { issues { totalCount } pullRequests { totalCount } }`), au lieu d'une recherche par
  étiquette que la limite de l'API de recherche (30 par minute) rendrait lente ;
- `GET /repos/{o}/{r}/vulnerability-alerts` sort de `gh api` en code 1 avec
  `Vulnerability alerts are disabled. (HTTP 404)` quand les alertes sont inactives, et en code 0 sans
  corps quand elles sont actives. Un autre 404 ne dit rien de l'état ;
- `automated-security-fixes` et `private-vulnerability-reporting` répondent `{"enabled": false}` sur un
  dépôt où ils sont inactifs, et les deux champs de `security_and_analysis` sont lisibles par l'admin ;
- sur un dépôt dont on n'a que l'écriture, `permissions.admin` est faux et les étiquettes restent
  lisibles.

Lus et écrits le 2026-10-01, avec la portée `project` en plus, sur le projet `MasterLaplace/Laplace`
en lecture seule puis sur un projet jetable, créé et supprimé pour l'occasion :

- la déclaration du projet Laplace, rejouée contre le vrai projet, ne propose aucun changement ;
- sur un premier projet jetable, un seul `--write` a créé le projet puis posé ses réglages, son lien,
  ses champs et ses vues, puis une mise à jour d'option, un filtre changé sur place et un tri
  reconstruit. Sur un second, après la relecture séparée, la vue recréée a gardé le regroupement que
  la déclaration ne disait pas, et les champs visibles comme la disposition ont changé sur place.
  Chaque relecture n'a plus rien proposé ;
- un projet neuf arrive avec `Status` à trois options (Todo, In Progress, Done) et une vue « View 1 » ;
- l'API REST des vues prend le login du propriétaire dans le chemin
  (`users/MasterLaplace/projectsV2/7/views`) : l'identifiant numérique que nomme la documentation répond
  404. Elle refuse Created, Updated et Closed dans une vue (`400 unsupported_ids`), et sa liste de
  champs les omet, alors que GraphQL les liste.

Le premier `--write`, sur le dépôt pilote `MasterLaplace/LplCraftSkills` le 2026-09-30, a fait
17 écritures sans échec, et la relecture n'a plus rien proposé. Il a appris un fait : **la forge ajoute
d'elle-même `require_extra_approval_for_unattributed_changes: true` à une règle `pull_request`
neuve.** Non déclaré, ce paramètre bloquerait la mise à jour suivante du ruleset, puisque la perdre
affaiblirait la règle : l'exemple le déclare donc.

**Sur un dépôt d'un compte personnel, GitHub refuse GitHub Actions comme contournement** (`422 Actor
GitHub Actions integration must be part of the ruleset source or owner organization`) : un workflow
n'y passe une règle qu'avec le jeton d'une application GitHub à soi.
