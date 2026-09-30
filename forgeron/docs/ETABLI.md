# `forgeron etabli` : poser la config déclarée d'un dépôt

Le verbe applique la première couche de `tenir-la-forge` (section 2) : la config déclarée dans un
fichier, appliquée par un outil qui montre son plan avant d'écrire. Il couvre les étiquettes, les
réglages du dépôt, sa sécurité et ses règles de branche.

```bash
cd forgeron
python3 -m forgeron etabli --file ~/.forgeron/etabli.json                 # le plan, rien n'est écrit
python3 -m forgeron etabli --file ~/.forgeron/etabli.json --repo OWNER/NAME --only labels
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
  noms de checks changent d'un dépôt à l'autre, pas la règle ;
- `renames` migre un vocabulaire sans perdre les items qui portent l'ancienne étiquette ;
- `unlisted_labels` vaut `report` (par défaut : les étiquettes non déclarées sont listées) ou
  `delete-unused` (celles qu'aucun item ne porte sont supprimées, les autres jamais) ;
- `only` restreint un dépôt à certains domaines. C'est le cas d'un dépôt qui garde son propre
  vocabulaire d'étiquettes et reçoit seulement les réglages, la sécurité et les règles.

Une clé inconnue, une couleur mal formée, une étiquette sans description ou un renommage vers une
étiquette non déclarée refusent tout le fichier, avec le chemin exact de ce qui ne va pas. Rien n'est
à moitié appliqué.

## Ce qu'il refuse, et pourquoi

| Refus | Pourquoi |
|---|---|
| un dépôt que le fichier ne déclare pas | le jeton atteint tous tes dépôts ; la liste de ceux qu'on règle est une décision, pas une conséquence du jeton |
| supprimer une étiquette encore portée | supprimer l'efface de toutes les issues ; on renomme, ou on la reporte à la main |
| renommer vers une étiquette qui existe déjà | deux étiquettes à fusionner, c'est des items à reporter : l'outil le dit, il ne choisit pas |
| retirer une protection de sécurité | désactiver la protection au push ou les alertes se fait à la main, avec sa raison écrite (`garder-les-frontieres`) |
| supprimer un ruleset non déclaré | il est listé, jamais supprimé |
| lire un état de sécurité illisible comme « inactif » | un état qu'on ne lit pas ne prouve rien : le point est bloqué, pas corrigé |

Les rulesets hérités d'une organisation ne sont ni lus ni modifiés : ils appartiennent à qui les a
posés.

## Les droits, et la trace

Le verbe passe par `gh`, donc par ta session : aucun jeton dans la config, rien à fuiter. Il lit
`permissions` sur le dépôt avant de planifier :

- sans droit d'écriture, les étiquettes sont sautées ;
- sans le rôle admin, les réglages, la sécurité et les rulesets sont sautés, et le plan le dit.

C'est le cas d'un dépôt dont on n'est que collaborateur : ses étiquettes se posent, le reste revient
à son propriétaire.

Chaque écriture, réussie ou refusée, laisse une ligne `etabli_applied` ou `etabli_failed` dans
`~/.forgeron/journal.jsonl`, avec l'avant et l'après. C'est la réponse à « qui a changé ce réglage, et
quand » que la forge ne donne qu'à moitié.

## Ce qu'il ne fait pas, délibérément

- **le board.** La portée `project` manque au jeton tant qu'on ne l'a pas demandée
  (`gh auth refresh -s project`), et les workflows d'un projet n'ont pas d'API : ils se règlent sur un
  projet de référence, puis se copient (`tenir-la-forge`, `references/github.md`). C'est le prochain
  domaine ;
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

Lus le 2026-09-30 sur six dépôts réels, en lecture seule, avec la session `gh` d'un compte personnel
(portées `repo`, `read:org`, `gist`, `admin:public_key`, `read:packages`) :

- les nombres d'items par étiquette viennent d'une seule requête GraphQL paginée
  (`labels { issues { totalCount } pullRequests { totalCount } }`), au lieu d'une recherche par
  étiquette que la limite de l'API de recherche (30 par minute) rendrait lente ;
- `GET /repos/{o}/{r}/vulnerability-alerts` sort de `gh api` en code 1 avec `HTTP 404` quand les
  alertes sont inactives, et en code 0 sans corps quand elles sont actives ;
- `automated-security-fixes` et `private-vulnerability-reporting` répondent `{"enabled": false}` sur un
  dépôt où ils sont inactifs, et les deux champs de `security_and_analysis` sont lisibles par l'admin ;
- sur un dépôt dont on n'a que l'écriture, `permissions.admin` est faux et les étiquettes restent
  lisibles.

Pas encore vérifié : **le chemin d'écriture**, qui attend le premier `--write` sur le dépôt pilote.
