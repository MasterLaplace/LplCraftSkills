# forgeron

Un pilote qui écoute les issues GitHub étiquetées, ouvre une **pull request en brouillon avant
d'écrire une ligne**, code la solution en suivant les [LplCraftSkills](../README.md), **attend
l'intégration continue**, demande la revue, et boucle sur tes commentaires jusqu'à ce que tu fusionnes.
Puis il clôt la session.

Preuve de concept locale. Zéro infrastructure : `gh`, `git`, `claude`, Python 3, et `node` pour les hooks de l'agent.

## En une image

```mermaid
stateDiagram-v2
    [*] --> queued : etiquette "claude" posee
    queued --> planning
    planning --> awaiting_answer : le plan a des questions
    awaiting_answer --> planning : un humain repond
    planning --> drafted : branche + commit vide + PR brouillon
    drafted --> implementing
    implementing --> implemented
    implemented --> awaiting_checks
    awaiting_checks --> fixing_checks : CI rouge
    fixing_checks --> awaiting_checks : correctif pousse
    awaiting_checks --> resolving : conflit avec la base
    awaiting_checks --> awaiting_checks : en retard, GitHub rebase
    resolving --> implemented : conflit resolu, revue redemandee
    awaiting_checks --> in_review : CI verte, revue demandee
    in_review --> revising : commentaire / request changes
    in_review --> fixing_checks : la CI passe au rouge
    in_review --> resolving : main a bouge, conflit
    in_review --> in_review : en retard, GitHub fusionne
    revising --> revised
    revised --> awaiting_checks
    in_review --> done : fusionnee par un humain
    awaiting_checks --> blocked : CI en echec 3 fois, ou trop lente
    revising --> blocked : plafond de tours ou de depense
    blocked --> revising : un humain commente
    done --> [*]
    note right of in_review
        Demander la revue EST la notification :
        GitHub sait deja te joindre.
    end note
```

Quatre choses qu'il ne fait jamais : ajouter un co-auteur agent, pousser sur `main`, fusionner, et `push --force` — la seule
réécriture autorisée est un `--force-with-lease` sur sa propre branche, après un rebase, et seulement
quand le pilote a vérifié qu'il ne reste aucun fichier en conflit.

## Installer

Il faut `git`, `python3` (3.10+), `gh` et `claude`, plus `node` pour les hooks de l'agent `artisan`.
Rien d'autre : pas de dépendance à installer, pas de jeton à copier. Docker et Kubernetes sont
**optionnels** et ne débloquent que le parallélisme sur plusieurs machines.

Si l'un d'eux manque, ou si tu veux la partie Docker / Kubernetes expliquée depuis zéro :
**[docs/INSTALLATION.md](docs/INSTALLATION.md)** — écrit et vérifié pour Ubuntu 26.04 sous WSL2, y
compris la façon d'authentifier `claude` **sur ton abonnement** plutôt qu'avec une clé d'API facturée
en plus.

```bash
./install.sh                    # depuis la RACINE du depot : les skills ET l'agent artisan
cd forgeron
./tests/run.sh                  # la porte complete : suite + sondes de mutation, hors ligne
python3 -m forgeron doctor      # verifie gh, git, claude, les portees du jeton
python3 -m forgeron config --init
```

Puis éditer `~/.forgeron/config.json` : au minimum le `slug` du dépôt, le `path` de son clone local,
et `reviewers` (toi). Le dépôt doit être dans cette **liste blanche** : un jeton peut atteindre tous
tes dépôts, et « sur lesquels un bot a le droit d'ouvrir une pull request » n'est pas une question
qu'un jeton sait trancher.

## La méthode vient de l'agent, les rails restent au pilote

Chaque run part en `claude -p --agent artisan`. L'agent
([`../agents/artisan.md`](../agents/artisan.md)) porte la **méthode** : charger `cycle-de-dev`, puis le
skill de chaque étape, et prouver chaque porte de sortie. Deux hooks en font des rails : aucune écriture
avant la carte, aucun arrêt sur un fichier modifié après la dernière commande. Le pilote garde ce qui
ne se délègue pas : la branche, le push, les outils de chaque phase, et tout ce qu'il vérifie contre le
monde.

L'agent doit être installé **au niveau utilisateur** par `../install.sh` : posé dans le `.claude/agents/`
d'un projet, il perd ses hooks. `doctor` le vérifie avant la première dépense. Pour s'en passer :
`"agent": ""` dans la configuration, et le contrat seul part comme avant.

## Lancer

```bash
python3 -m forgeron once                    # une passe, SANS ecrire : dit ce qu'il ferait
python3 -m forgeron once --write            # une passe, pour de vrai
python3 -m forgeron run --write --interval 60   # la boucle
python3 -m forgeron status                  # ou en est chaque issue
```

Sans `--write`, les lectures sont réelles et les écritures sont refusées et journalisées. Ce n'est
pas une simulation à moitié : une simulation qui truquerait aussi les lectures exercerait le faux,
alors que la panne intéressante est une vraie issue dont l'état réel mène quelque part d'inattendu.

Le reste des options : `python3 -m forgeron --help`. Elles ne sont pas recopiées ici, parce qu'une
liste d'options dans un README finit toujours par mentir — c'est ce que dit le skill
[`doc-derivee`](../skills/doc-derivee/SKILL.md).

## Comment tu t'en sers, côté humain

1. tu ouvres une issue et tu lui mets l'étiquette `claude` ;
2. quelques secondes plus tard une **pull request en brouillon** apparaît, avec le plan et des
   critères d'acceptation cochables. Si le cadrage a buté sur une ambiguïté, tu reçois **des
   questions sur l'issue et aucune branche** : rien n'est construit avant réponse ;
3. le brouillon devient prêt quand la CI est verte, et tu es ajouté comme relecteur ;
4. tu relis **normalement** : commentaires en ligne, *request changes*, *approve*. Chaque retour
   déclenche un tour, avec **un seul commentaire** en réponse : une ligne par remarque, puis le
   tableau critère / tenu / preuve ;
4a. si le changement se **voit** mieux qu'il ne se lit, la pull request porte une image ou une
   vidéo. Et jamais une capture d'écran : l'agent doit déclarer la commande qui produit le fichier,
   le pilote **écarte le fichier, relance la commande et exige qu'il revienne**, et la commande est
   publiée sous l'image. Un visuel qui ne se régénère pas est écarté, avec sa raison. Demande
   `gh` ≥ 2.99 ;
4b. si quelqu'un fusionne autre chose sur `main` pendant ce temps, la branche se met à jour toute
   seule : **rebase tant que personne ne l'a relue, fusion dès qu'un relecteur est passé** — rebaser
   sous ses yeux effacerait le « ce qui a changé depuis ta dernière relecture » qu'il utilise. En cas
   de conflit, l'agent le résout en lisant les deux intentions, puis **la revue est redemandée même si
   la PR était approuvée** : une résolution n'a été relue par personne ;
5. tu fusionnes. Toujours toi : `approve` ne fusionne pas ;
6. il poste un résumé, supprime son worktree, et ferme la session.

Pour reprendre la main sans rien casser : étiquette `claude:hold`. Pour tout arrêter : ferme l'issue.

## Ce qui est vérifié, et ce qui ne l'est pas

Vérifié hors ligne, à chaque `./tests/run.sh` : **129 tests** dont le trajet complet issue → fusion
avec un build rouge et un tour de revue au milieu, plus **22 sondes de mutation** qui cassent une
règle chacune et vérifient que la suite s'en aperçoit. Une suite verte au premier coup ne prouve
rien ; c'est la sonde qui prouve qu'elle *pouvait* échouer.

Vérifié contre un vrai disque : le vérificateur de visuels, dont le contrôle qui compte est
qu'une commande **qui ne fait rien** est refusée. Sans la mise à l'écart du fichier avant de
relancer, elle passerait, puisque le fichier était déjà là.

Vérifié contre un vrai `git` : le worktree par issue, le renommage de branche avant premier push, le
fait que **le checkout de l'humain reste propre**, la reprise d'une branche déjà poussée, `is_synced`
qui distingue « poussé » de « commité seulement », et **un vrai conflit** — vrais marqueurs, rebase
laissé en cours pour que l'agent le voie, `--force-with-lease` requis là où un push ordinaire est
refusé, et `abort` qui repose la branche exactement où elle était. Un dépôt bare local joue `origin`,
donc aucun réseau.

Vérifié contre le vrai GitHub, en lecture seule : identité, liste d'issues, recherche de pull
request, agrégat de checks, et **récupération des journaux d'un job en échec**.

Vérifié contre le vrai `claude` : la sortie structurée (`--json-schema` → champ `structured_output`),
la **reprise de conversation d'un processus à l'autre** (`--session-id` puis `--resume`), et ce que
fait `--agent` là où la documentation se tait : un nom inconnu échoue bruyamment, l'agent s'ajoute au
prompt système au lieu de le remplacer, un `tools:` dans l'agent l'emporte sur `--tools` et fait
disparaître la sortie structurée, et ses hooks ne se déclenchent qu'au niveau utilisateur
([`tests/probes/probe_claude_agent.sh`](tests/probes/probe_claude_agent.sh)).

Sous Windows natif, **4 tests échouent** parce qu'ils supposent un shell POSIX : un script de hook
lancé directement, et un `;` qui n'est pas un séparateur pour `cmd.exe`. forgeron vise Linux et WSL, où
ils passent ; les 125 autres passent aussi sous Windows.

**Pas encore vérifié de bout en bout**, et c'est dit à chaque fois dans les fichiers concernés :
le chemin d'**écriture** sur la forge (créer le brouillon, le passer prêt, commenter), qui demande un
dépôt bac à sable — voir [docs/GITHUB.md](docs/GITHUB.md) ; et le **Job Kubernetes**
([k8s/](k8s/)), jamais appliqué, puisqu'il agirait sur un vrai dépôt. L'**image**, elle, a été
construite et vérifiée sous WSL (Docker 29.8) : elle installe le pack, `claude` y reconnaît l'agent
`artisan`, les tests de ses hooks y passent, et l'entrypoint refuse de démarrer sans authentification.
À chaque `./tests/run.sh`, 16 tests relisent le `ConfigMap` avec le vrai chargeur de configuration,
comparent les chemins montés à ceux que la configuration nomme, refusent qu'un secret soit cuit dans
l'image, et interdisent au `ConfigMap` de nommer un agent si le `Dockerfile` cesse d'installer le pack
ou `node`.

## Lire la suite

- [docs/INSTALLATION.md](docs/INSTALLATION.md) — installer et configurer les quatre outils
  obligatoires, puis Docker et Kubernetes en local si tu veux les apprendre ; l'authentification de
  `claude` sur abonnement, et les pièges propres à WSL2 ;
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — les coutures, la machine à états, et les faits
  mesurés sur `claude -p` et `gh` qui ont décidé de la forme du code ;
- [docs/GITHUB.md](docs/GITHUB.md) — jeton, GitHub App, webhooks : ce qui est nécessaire quand, et
  les commandes exactes ;
- [docs/CLUSTER.md](docs/CLUSTER.md) — ce qui change en Kubernetes, et pourquoi la réponse n'est pas
  un volume partagé.
