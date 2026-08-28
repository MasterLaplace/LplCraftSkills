# Jeton, App, webhooks : ce qu'il faut, quand

## Faut-il un jeton alors que `gh` est déjà configuré ?

**Non, pas pour cette preuve de concept.** `gh_forge.py` ne manipule aucun secret : il lance `gh`,
qui porte déjà un jeton OAuth. Il n'y a donc **rien à mettre dans un fichier de configuration**,
donc rien à fuiter. `gh auth token` l'imprime si un autre outil en a besoin.

Le prix de ce choix est écrit dans le fichier : **le bot parle en ton nom**. Les commits, la pull
request et les commentaires sont les tiens. Pour cette PoC c'est un avantage — aucune identité à
provisionner — et c'est la seule classe qui changerait pour en sortir.

Il faut un vrai jeton ou une App dans trois cas, et trois seulement :

1. **une identité de bot séparée** : que la PR soit signée `forgeron[bot]` et pas toi. → GitHub App,
   jeton d'installation ;
2. **des webhooks** : que GitHub te pousse les événements au lieu que tu les scrutes. →
   portée `admin:repo_hook`, ou une App ;
3. **tourner sans session interactive** (cluster, CI) : il n'y a pas de `gh auth login` là-bas.
   → clé privée d'App → jeton d'installation, ou un PAT à portée fine dans un Secret.

### Ce que ton jeton actuel peut et ne peut pas

Mesuré ici : portées `admin:public_key`, `gist`, `read:org`, `repo`.

- `repo` **suffit** pour tout ce que fait forgeron : issues, branches, pull requests, reviews,
  commentaires, agrégat de checks, journaux de jobs ;
- ⚠ `workflow` est **absente**, et c'est une bonne nouvelle : l'agent **ne peut pas** pousser une
  modification de `.github/workflows/`. GitHub refuse le push. C'est un garde-fou appliqué par le
  serveur, pas par un prompt — le seul genre qui tienne. Ne l'ajoute pas « au cas où » ;
- `admin:repo_hook` est absente : c'est ce qui bloque l'option 2 ci-dessous.

## Le notifier : les deux directions, et une seule est à construire

**Vers toi : rien à construire.** Demander une revue *est* la notification — GitHub sait déjà te
joindre sur tous tes appareils. C'est ce que fait `request_review`. Écrire un notifieur à côté en
ferait un deuxième, moins bon. Si tu veux en plus un toast local, `notify_command` dans la
configuration est un gabarit shell avec `{title}` et `{url}`.

**Vers forgeron : quatre étages, par coût d'infrastructure croissant.**

### 1. Scrutation (aujourd'hui, zéro infrastructure)

```bash
python3 -m forgeron run --write --interval 60
```

Latence : la moitié de l'intervalle en moyenne. Coût d'API : ~4 appels par passe et par issue
suivie, contre un plafond de **5000 par heure** (mesuré : 5000 restants, 0 utilisé). Un intervalle
de 60 s tient donc une vingtaine d'issues vivantes avant d'approcher le plafond.

C'est suffisant, et ce n'est pas un compromis honteux : le pilote réconcilie depuis l'état observé,
donc pousser les événements ne change **que la latence**, jamais la justesse.

### 2. `gh webhook forward` (événements poussés, toujours sans adresse publique)

L'extension officielle ouvre un webhook temporaire et relaie vers ton `localhost`. Ni ngrok, ni IP
publique, ni ouverture de port.

```bash
gh auth refresh -s admin:repo_hook          # la portee qui manque aujourd'hui
gh extension install cli/gh-webhook
gh webhook forward \
  --repo OWNER/NAME \
  --events issues,issue_comment,pull_request_review,pull_request_review_comment,check_suite \
  --url http://127.0.0.1:8787/hook
```

Côté forgeron, c'est [`WebhookTrigger`](../forgeron/sources.py) : **un stub délibéré**, dont le
docstring porte ces deux routes. Un déclencheur sans receveur est une fonctionnalité que personne ne
lance, et comme la boucle réconcilie déjà, il n'y a rien à gagner tant que la latence ne gêne pas.
`ticks()` est un serveur HTTP qui rend un tick par livraison : une trentaine de lignes, le jour où
la latence devient le problème.

### 3. GitHub App (l'étape « vrai système »)

Ce qu'elle apporte, et qu'aucune des deux précédentes ne peut donner :

- **une identité de bot** : PR, commits et commentaires signés par l'App ;
- **des permissions par dépôt**, installées dépôt par dépôt, au lieu d'un jeton qui atteint tout ;
- **l'API Checks** : le verdict de l'agent devient un *check run* sur le commit, pas un commentaire.
  Une pull request dont la case « forgeron : critères tenus » est verte se relit autrement ;
- un webhook vers une adresse publique — en cluster, une Ingress.

Permissions minimales : `contents: write`, `pull_requests: write`, `issues: write`,
`actions: read` (les journaux), `checks: read` (ou `write` pour publier le verdict). Pas de
`workflows`, pour la raison ci-dessus.

### 4. Faire tourner la boucle ENTIÈRE dans GitHub Actions

L'idée : un workflow `on: issues` qui lance `forgeron once` sur un runner GitHub, donc ce sont les
serveurs de GitHub qui paient le calcul. C'est faisable, et voici les cinq choses à savoir avant.

⚠⚠ **Le bloqueur, et il est silencieux.** Un push fait avec le `GITHUB_TOKEN` du workflow **ne
déclenche aucun autre workflow** — c'est la protection anti-récursion de GitHub, documentée mot pour
mot : *« events triggered by the GITHUB_TOKEN will not create a new workflow run »*, avec pour seules
exceptions `workflow_dispatch`, `repository_dispatch` et certains types d'activité de
`pull_request`. Conséquence pour `forgeron` : la branche qu'il pousse **n'a jamais de checks**, la
porte de CI attend, le délai de grâce expire, et le pilote conclut « ce dépôt n'a pas de CI » puis
demande une revue sur une branche que rien n'a testée. Tout a l'air de marcher. Le remède est un
**PAT** ou un **jeton d'installation d'App** à la place du `GITHUB_TOKEN`.

⚠ **Le secret est le vrai sujet, pas le calcul.** Un secret de dépôt est lisible par quiconque peut
pousser un workflow dessus. Y mettre ton `CLAUDE_CODE_OAUTH_TOKEN`, c'est-à-dire une clé de ton
abonnement, veut dire : **dépôt privé obligatoire**, jamais de déclencheur `pull_request` venant d'un
fork, et un collaborateur avec le droit de push peut l'exfiltrer en trois lignes de YAML.

⚠ **« GitHub paie » n'est vrai qu'à moitié** : GitHub paie le CPU du runner, mais le modèle tourne
toujours sur **ton** abonnement, avec **tes** limites de débit. Le calcul déménage, la consommation
non.

Deux limites de plateforme à connaître : **6 heures maximum** par job, et les minutes Actions sont
gratuites sur un dépôt public mais comptées sur un dépôt privé — or on vient de voir que le dépôt doit
être privé.

Et une contrainte de conception, celle qui est intéressante : **le runner est vierge à chaque fois**,
donc `~/.forgeron/state` n'existe pas. C'est exactement le cas que `continuity: "rebuild"` prévoit —
et l'état lui-même se relit depuis la forge, puisque la branche, la pull request et ses commentaires
sont déjà tout ce qu'il faut. Un `forgeron` qui tourne en Actions est un `forgeron` **sans mémoire
locale**, ce qui est la version la plus honnête de sa propre architecture.

⚠ **Il existe une cinquième route, tentante et à éviter** : un workflow qui se contente de relayer
l'événement vers ta machine par `repository_dispatch`. Elle exige la portée `workflow` — celle qu'on
garde absente exprès — et elle met le déclencheur du bot **dans le dépôt que le bot modifie**.

## Le dépôt bac à sable, pour exercer le chemin d'écriture

C'est la seule partie non vérifiée de bout en bout, et elle demande un dépôt jetable. À lancer dans
ton terminal, aucun `sudo` :

```bash
# 1. un depot prive jetable, avec un workflow qui echoue exprès une fois
gh repo create forgeron-sandbox --private --clone --add-readme
cd forgeron-sandbox
mkdir -p .github/workflows src
cat > .github/workflows/ci.yml <<'YML'
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: python -m unittest discover -s . -p 'test_*.py' -v
YML
cat > src/__init__.py <<'PY'
PY
cat > test_smoke.py <<'PY'
import unittest

class Smoke(unittest.TestCase):
    def test_it_runs(self):
        self.assertTrue(True)
PY
git add -A && git commit -m "chore: amorce du bac a sable" && git push

# 2. une issue etiquetee, et l'etiquette de pause pour pouvoir reprendre la main
gh label create claude --color 5319e7 --description "confie a forgeron"
gh label create claude:hold --color b60205 --description "forgeron ne touche plus"
gh issue create --label claude \
  --title "Ajouter un cache LRU borne dans src/cache.py" \
  --body "Les lectures repetees coutent trop cher. Il faut un cache LRU a capacite fixe,
avec une eviction du moins recemment utilise, et des tests qui couvrent l'eviction."
```

Puis, côté forgeron :

```bash
cd ~/LplCraftSkills/forgeron
python3 -m forgeron config --init            # puis editer ~/.forgeron/config.json :
                                             #   slug "TON_LOGIN/forgeron-sandbox"
                                             #   path "$HOME/forgeron-sandbox"
                                             #   reviewers ["TON_LOGIN"]
python3 -m forgeron doctor                   # doit etre vert sur les 6 requises
python3 -m forgeron once                     # SANS --write : dit ce qu'il ferait
python3 -m forgeron once --write             # cadrage + brouillon
python3 -m forgeron run --write --interval 30
```

⚠ **Ne pointe pas la PoC sur `LplKernel` pour un premier essai.** Deux raisons concrètes : le dépôt
porte un **sous-module** (`LplPlugin`), et les worktrees plus les sous-modules demandent un
`git submodule update --init` par worktree que `git_workspace.py` ne fait pas encore ; et sa CI
construit un cross-toolchain, donc une passe d'attente de CI y coûte des dizaines de minutes contre
les 45 du plafond par défaut.
