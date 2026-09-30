# GitHub : ce que la plateforme permet, vérifié le 2026-09-30

Les règles de `tenir-la-forge` valent pour toute forge. Ce fichier dit comment GitHub les rend
possibles, ou pas, à une date donnée. Chaque fait porte sa source : quand une limite change, on la
relit à la source et on corrige ici, jamais de mémoire.

Sources : la documentation (docs.github.com), le journal des changements (github.blog/changelog), et le
schéma GraphQL public (https://docs.github.com/public/fpt/schema.docs.graphql), lu le 2026-09-30.

## Compte personnel ou organisation

| Besoin | Compte personnel | Organisation (offre gratuite comprise) |
|---|---|---|
| un projet (board) qui couvre plusieurs dépôts | oui | oui |
| champs du projet : statut, priorité, taille, itération | oui | oui |
| sous-issues, dépendances « blocked by » | oui | oui |
| règles de branche (rulesets) sur un dépôt public | oui | oui |
| fichiers communautaires par défaut, par un dépôt `.github` public | oui | oui |
| types d'issues natifs | non | oui, jusqu'à 25 |
| champs d'issue (Priority, Effort, dates), portés par l'issue et non par un projet | non | oui, disponibles depuis le 2026-07-02 |
| modèles de projet | non, mais copier un projet donne le même résultat | oui |
| file de fusion (*merge queue*) | non | oui, sur les dépôts publics |
| étiquettes par défaut des nouveaux dépôts | non | oui |
| accès d'une GitHub App à un projet | non | oui |

Sources : types d'issues https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/managing-issue-types-in-an-organization ;
champs d'issue https://github.blog/changelog/2026-07-02-issue-fields-are-now-generally-available/ ;
modèles https://docs.github.com/en/issues/planning-and-tracking-with-projects/managing-your-project/managing-project-templates-in-your-organization ;
file de fusion https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue ;
étiquettes par défaut https://docs.github.com/en/organizations/managing-organization-settings/managing-default-labels-for-repositories-in-your-organization.

## Projets

- **Les workflows d'un projet** (statut à l'ajout, à la fusion, à l'approbation, archivage automatique,
  ajout automatique…) **ne se créent, ne s'activent et ne se configurent que dans l'interface.** L'API
  expose `ProjectV2Workflow` en lecture (`name`, `number`, `enabled`), et la seule mutation est
  `deleteProjectV2Workflow`. Source : le schéma GraphQL et son journal 2026,
  https://docs.github.com/en/graphql/overview/changelog/2026 ;
- **copier un projet garde les vues, les champs, les graphiques, les workflows configurés sauf
  l'ajout automatique**, et les brouillons si on le demande. Ni les items, ni les collaborateurs, ni les liens
  vers les dépôts. `copyProjectV2` accepte un compte personnel comme destination (`gh project copy`).
  Source : https://docs.github.com/en/issues/planning-and-tracking-with-projects/creating-projects/copying-an-existing-project ;
- **les vues se créent par l'API depuis 2026**, en REST depuis le 2026-01-15, avec filtre, tri et
  regroupement (`POST /users/{user_id}/projectsV2/{number}/views`) ; en GraphQL depuis le 2026-07-28
  (`createProjectV2View`, nom, disposition et champs visibles seulement). Le point d'entrée REST des
  projets d'un compte personnel refuse les GitHub Apps et les jetons à portée fine. Source :
  https://docs.github.com/en/rest/projects/views ;
- **ajout automatique : un workflow par dépôt suivi**, et le nombre dépend de l'offre : 1 en Free, 5 en
  Pro et Team, 20 en Enterprise. Il n'ajoute pas les items qui existaient avant lui. Source :
  https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/adding-items-automatically ;
- un projet porte au plus 50 000 items ; l'archivage automatique filtre sur `is`, `reason` et `updated`.
  Source : https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/archiving-items-automatically ;
- le workflow « un item est ajouté » se règle par type d'item (issue ou pull request), ce qui permet
  deux statuts d'entrée différents dans le même projet. Constaté dans l'interface, pas dans la doc ;
- le workflow « pull request liée à une issue » existe depuis le 2025-11-06 et passe
  l'issue « en cours ». Source : https://github.blog/changelog/2025-11-06-improved-onboarding-flow-for-github-projects/ ;
- les points d'étape (*status updates*) se publient par l'API (`createProjectV2StatusUpdate`) ; les
  graphiques (*Insights*) n'ont pas d'API. Sources :
  https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/sharing-project-updates ,
  https://docs.github.com/en/issues/planning-and-tracking-with-projects/viewing-insights-from-your-project/about-insights-for-projects .

## Issues

- une issue a jusqu'à 100 **sous-issues**, sur 8 niveaux, y compris dans d'autres dépôts. Une
  sous-issue hérite par défaut du projet et du jalon de son parent (2025-09-11). REST `.../issues/{n}/sub_issues`, GraphQL
  `addSubIssue`, `gh issue create --parent` depuis gh 2.94. Sources :
  https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues ,
  https://github.blog/changelog/2025-09-11-a-rest-api-for-github-projects-sub-issues-improvements-and-more/ ;
- **dépendances** « blocked by » et « blocking » : disponibles depuis le 2025-08-21, 50 par sens, en
  REST, GraphQL et `gh --blocked-by`. Source : https://github.blog/changelog/2025-08-21-dependencies-on-issues/ ;
- les **formulaires d'issue** sont encore en préversion publique. Clés `name`, `description`, `title`,
  `labels`, `assignees`, `type`, `projects`, `body`. Une étiquette absente du dépôt n'est pas posée ;
  `projects:` exige que l'auteur ait le droit d'écrire sur le projet ; `type:` suppose des types
  d'issues, donc une organisation. Source :
  https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms .

## Règles de branche (rulesets)

- disponibles sur les dépôts publics en offre gratuite, jusqu'à 75 par dépôt. Source :
  https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets ;
- règles utiles à un mainteneur seul : `pull_request` (dont `required_approving_review_count`,
  `allowed_merge_methods`, `dismiss_stale_reviews_on_push`), `required_status_checks`,
  `non_fast_forward`, `deletion`, `required_linear_history`, `required_signatures`. Source :
  https://docs.github.com/en/rest/repos/rules ;
- **un auteur ne peut pas approuver sa propre PR.** Le contournement se déclare dans
  `bypass_actors` : le rôle admin du dépôt est `{"actor_type": "RepositoryRole", "actor_id": 5}`, et
  `"bypass_mode": "pull_request"` limite le contournement aux PR. Source :
  https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/approving-a-pull-request-with-required-reviews ;
  l'identifiant 5 n'est pas écrit dans la doc de l'API, il se lit dans l'export JSON d'un ruleset créé
  dans l'interface ;
- **un `PUT` sur un ruleset remplace la règle en entier**, contournements et paramètres compris.
  C'est rapporté par des outils qui l'ont payé (https://github.com/rjwalters/loom/pull/8271), la doc de
  l'API n'en dit rien. On envoie donc toujours la règle complète, et on relit avant d'écrire les
  paramètres que la forge porte sans qu'on les ait déclarés : une réponse réelle en contient que l'OpenAPI
  ne décrit pas (`require_extra_approval_for_unattributed_changes`, lu sur `vercel/next.js`) ;
- **un commit non signé sur la branche d'une PR peut bloquer la fusion, même en squash**, alors que
  GitHub signerait le commit final ; la première sortie documentée est de réécrire et signer ces commits.
  Les commits qu'un bot ou une App crée par l'API, sans auteur ni signature fournis, sont signés par
  GitHub, voir aussi
  https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification . Source :
  https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches ;
- `gh ruleset` ne sait que lister, afficher et vérifier : la création passe par
  `gh api repos/{owner}/{repo}/rulesets`, avec le rôle admin sur le dépôt.

## Fichiers communautaires par défaut

Un dépôt public nommé `.github`, sur un compte personnel comme sur une organisation, donne ses fichiers
à tous les dépôts publics du compte qui n'en ont pas : `CODE_OF_CONDUCT`, `CONTRIBUTING`, `FUNDING.yml`,
les gabarits d'issue et de PR avec leur `config.yml`, `SECURITY`, `SUPPORT`, les formulaires de
discussion. **Ni la licence, ni les étiquettes.** Le repli se fait par type : un dépôt qui a son dossier
`ISSUE_TEMPLATE` n'hérite d'aucun gabarit d'issue. Source :
https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/creating-a-default-community-health-file .

Un formulaire de discussion vit dans `.github/DISCUSSION_TEMPLATE/<catégorie>.yml`, où `<catégorie>` est
le *slug* d'une catégorie de discussions du dépôt. Les discussions s'activent par l'API
(`updateRepository`, champ `hasDiscussionsEnabled` en GraphQL ; le `PATCH` REST ne l'accepte pas), mais
**une catégorie ne se crée qu'à la main** : le schéma GraphQL n'a aucune mutation pour ça (lu le
2026-09-30). Sans la catégorie, le formulaire ne sert à rien. L'héritage d'un formulaire depuis le
dépôt `.github` est documenté pour une organisation ; pour un compte personnel, la doc des formulaires
ne le dit pas (non vérifié), donc on pose aussi le formulaire dans chaque dépôt qui a la catégorie.
Source :
https://docs.github.com/en/discussions/managing-discussions-for-your-community/creating-discussion-category-forms .

## Où la plateforme lit ses fichiers

| Fichier | Où GitHub le cherche |
|---|---|
| `CODEOWNERS` | `.github/`, puis la racine, puis `docs/` : le premier trouvé gagne. Jamais hérité du dépôt `.github` du compte |
| `CONTRIBUTING`, `CODE_OF_CONDUCT`, `SECURITY`, `SUPPORT` | `.github/`, la racine ou `docs/` |
| gabarit de PR | `.github/`, la racine ou `docs/`, ou un dossier `PULL_REQUEST_TEMPLATE/` |
| gabarits et formulaires d'issue | `.github/ISSUE_TEMPLATE/` seulement |
| `FUNDING.yml`, `dependabot.yml`, les workflows | `.github/` seulement |
| `LICENSE` | la racine : c'est là que la détection de licence regarde |

Les noms cités dans `CODEOWNERS` doivent avoir le droit d'écrire sur le dépôt. Sources :
https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners ,
https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/creating-a-default-community-health-file ,
https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository .

## Sécurité d'un dépôt public

| Réglage | Lecture | Écriture |
|---|---|---|
| détection de secrets, protection au push | `GET /repos/{o}/{r}`, champ `security_and_analysis` | `PATCH /repos/{o}/{r}` avec `security_and_analysis` |
| alertes Dependabot | `GET /repos/{o}/{r}/vulnerability-alerts` (204 actif ; 404 avec « Vulnerability alerts are disabled » inactif ; tout autre 404 ne dit rien) | `PUT` au même chemin |
| mises à jour de sécurité Dependabot | `GET /repos/{o}/{r}/automated-security-fixes` | `PUT` au même chemin |
| signalement privé d'une faille | `GET /repos/{o}/{r}/private-vulnerability-reporting` | `PUT` au même chemin |

Tous demandent le rôle admin sur le dépôt.

Un signalement privé ouvre un avis de sécurité (*security advisory*) en brouillon, visible du seul
mainteneur et de qui a signalé. On peut y corriger la faille dans un fork privé temporaire, puis
publier l'avis avec la version corrigée. GitHub est une autorité de numérotation CVE : il attribue un
identifiant CVE à l'avis d'un dépôt public, sans autre démarche. Source :
https://docs.github.com/en/code-security/security-advisories/working-with-repository-security-advisories/about-repository-security-advisories .
Le TLP 2.0 et ses quatre niveaux (RED, AMBER, GREEN, CLEAR) : https://www.first.org/tlp/ .

## Ce qu'un workflow voit, et ce qu'il déclenche

- sur un événement `pull_request`, `GITHUB_SHA` est le commit de fusion que GitHub fabrique entre la
  branche et sa base, pas le dernier commit de la branche. Un contrôle qui lit `git log -n 1 $GITHUB_SHA`
  lit donc un message « Merge … into … ». Source :
  https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request ;
- un push fait avec le `GITHUB_TOKEN` ne déclenche aucun autre workflow, sauf `workflow_dispatch` et
  `repository_dispatch` : c'est la façon documentée d'enchaîner deux workflows. Source :
  https://docs.github.com/en/actions/concepts/security/github_token ;
- `${{ github.event.pull_request.body }}` écrit tel quel dans un `run:` est une injection : le texte
  devient du shell. On le passe par une variable d'environnement. Source :
  https://docs.github.com/en/actions/concepts/security/script-injections ;
- Dependabot étiquette ses PR `dependencies` et le nom de l'écosystème, qui s'écrit `github_actions`
  pour les actions (lu sur les PR d'un dépôt réel), et il couvre aussi les sous-modules
  (`gitsubmodule`). Source :
  https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference .

## Jetons

- `gh project` demande la portée `project` (`read:project` pour lire) : `gh auth refresh -s project`.
  Source : https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-api-to-manage-projects ;
- le `GITHUB_TOKEN` d'un workflow n'a pas accès aux projets, et un jeton à portée fine n'a pas accès
  aux projets d'un compte personnel. Pour alimenter le board d'un compte personnel depuis une Action, il
  ne reste que le jeton classique, qui ouvre tous les dépôts. Sources :
  https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/automating-projects-using-actions ,
  https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens ;
- les portées sont celles d'un jeton OAuth ou d'un jeton personnel, utilisé en HTTPS ou par l'API. Un
  push par SSH s'authentifie par la clé, qui n'a pas de portée.

## Pull requests empilées

Préversion publique depuis le 2026-07-30 (`gh extension install github/gh-stack`, commandes `init`,
`add`, `submit`, `rebase`, `sync`, `merge`). Une pile se fusionne par le bas, en bloc contigu ; les PR
du dessus sont rebasées et reciblées par la plateforme ; les règles de branche s'appliquent à chaque
étage. Toutes les branches vivent dans le même dépôt (pas de pile depuis un fork), la fusion
automatique n'est pas prise en charge, et un squash donne un commit par PR. Sources :
https://github.blog/changelog/2026-07-30-stacked-pull-requests-are-now-in-public-preview/ ,
https://docs.github.com/en/pull-requests/get-started/about-stacked-prs ,
https://docs.github.com/en/pull-requests/reference/stacked-pull-requests .

## Outils de config déclarée, état au 2026-09-30

| Outil | Ce qu'il couvre | Ce qu'il faut savoir |
|---|---|---|
| `gh` 2.102 | étiquettes (`gh label clone`), réglages (`gh repo edit`), projets (`gh project create`, `copy`, `field-create`, `item-add`, `link`) | ni vues ni workflows de projet ; rulesets en lecture seule |
| fournisseur Terraform `integrations/github` 6.13 | rulesets, étiquettes, jalons, dépôts | **aucune ressource Projects v2** ; un fichier d'état à garder |
| application *Settings* (`repository-settings/app`) 5.0.14 | réglages, étiquettes, jalons, rulesets, héritage `_extends` | pas les projets ; un push de `.github/settings.yml` sur la branche principale agit en admin |
| `github/safe-settings` | la même chose, à l'échelle d'une organisation | organisation seulement |
| `actions/add-to-project` 2.0 | ajouter des items à un projet depuis une Action | un jeton classique avec `repo` et `project` |
| `release-please` 5.0, `release-drafter` 7.7 | la PR de version, les notes de version | la PR de version survit à une règle « PR obligatoire », un push direct non |
